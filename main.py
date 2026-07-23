from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func

from auth import (
    assert_section_access,
    create_access_token,
    get_current_user,
    get_user_sections,
    hash_password,
    require_active_subscription,
    require_owner,
    verify_password,
)
from models import Record, Resource, Section, SessionLocal, Subscription, Tenant, User, UserSection

VALID_TEMPLATES = {"time_slot", "date_range", "queue"}

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def slugify(label: str) -> str:
    chars = []
    for ch in label.lower():
        if ch in TRANSLIT:
            chars.append(TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            chars.append(ch)
        else:
            chars.append("-")
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "section"


def unique_section_key(db, tenant_id: int, label: str) -> str:
    base = slugify(label)
    key = base
    suffix = 2
    while db.query(Section).filter(Section.tenant_id == tenant_id, Section.key == key).first() is not None:
        key = f"{base}-{suffix}"
        suffix += 1
    return key


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Accept requests from any origin
    allow_credentials=True,  # Allow cookies and authentication
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)


@app.get("/")
def read_root():
    return {"Hello": "World"}


# ============================== Auth ==============================

class LoginRequest(BaseModel):
    tenant_slug: str
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    sections: List[str]
    read_only: bool
    tenant_name: str
    subscription_status: str


class MeResponse(BaseModel):
    username: str
    role: str
    sections: List[str]
    read_only: bool
    tenant_name: str
    subscription_status: str


@app.post("/auth/login", response_model=LoginResponse)
def login(data: LoginRequest):
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.slug == data.tenant_slug).first()
    invalid = HTTPException(status_code=401, detail="Неверный код компании, логин или пароль")
    if tenant is None:
        db.close()
        raise invalid

    user = (
        db.query(User)
        .filter(User.tenant_id == tenant.id, User.username == data.username, User.is_active == True)
        .first()
    )
    if user is None or not verify_password(data.password, user.password_hash):
        db.close()
        raise invalid

    sections = get_user_sections(db, user)
    subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
    token = create_access_token(user, sections)
    db.close()
    return LoginResponse(
        access_token=token,
        role=user.role,
        sections=sections,
        read_only=user.read_only,
        tenant_name=tenant.name,
        subscription_status=subscription.status if subscription else "expired",
    )


@app.get("/auth/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    sections = get_user_sections(db, current_user)
    subscription = db.query(Subscription).filter(Subscription.tenant_id == current_user.tenant_id).first()
    db.close()
    return MeResponse(
        username=current_user.username,
        role=current_user.role,
        sections=sections,
        read_only=current_user.read_only,
        tenant_name=tenant.name,
        subscription_status=subscription.status if subscription else "expired",
    )


# ============================== Employees (owner-only) ==============================

class UserCreate(BaseModel):
    username: str
    password: str
    role: str  # "owner" | "employee"
    sections: List[str] = []
    read_only: bool = False


class UserUpdate(BaseModel):
    role: Optional[str] = None
    sections: Optional[List[str]] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    read_only: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    sections: List[str]
    is_active: bool
    read_only: bool


@app.get("/users", response_model=List[UserOut])
def list_users(current_user: User = Depends(require_owner)):
    db = SessionLocal()
    users = db.query(User).filter(User.tenant_id == current_user.tenant_id).all()
    result = [
        UserOut(id=u.id, username=u.username, role=u.role, sections=get_user_sections(db, u), is_active=u.is_active, read_only=u.read_only)
        for u in users
    ]
    db.close()
    return result


@app.post("/users", response_model=UserOut)
def create_user(data: UserCreate, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    existing = (
        db.query(User)
        .filter(User.tenant_id == current_user.tenant_id, User.username == data.username)
        .first()
    )
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Такой логин уже существует")

    new_user = User(
        tenant_id=current_user.tenant_id,
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=True,
        read_only=data.read_only,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    for section in data.sections:
        db.add(UserSection(user_id=new_user.id, section=section))
    db.commit()
    result = UserOut(id=new_user.id, username=new_user.username, role=new_user.role, sections=data.sections, is_active=True, read_only=new_user.read_only)
    db.close()
    return result


@app.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if user is None:
        db.close()
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    if data.role is not None:
        user.role = data.role
    if data.password:
        user.password_hash = hash_password(data.password)
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.read_only is not None:
        user.read_only = data.read_only
    db.commit()

    if data.sections is not None:
        db.query(UserSection).filter(UserSection.user_id == user.id).delete()
        for section in data.sections:
            db.add(UserSection(user_id=user.id, section=section))
        db.commit()

    result = UserOut(id=user.id, username=user.username, role=user.role, sections=get_user_sections(db, user), is_active=user.is_active, read_only=user.read_only)
    db.close()
    return result


@app.delete("/users/{user_id}")
def deactivate_user(user_id: int, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if user is None:
        db.close()
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    user.is_active = False
    db.commit()
    db.close()
    return "Сотрудник деактивирован"


# ============================== Resources (номера/боксы/сауны) ==============================

class ResourceCreate(BaseModel):
    section: str
    label: str
    color: str
    sort_order: int = 0


class ResourceUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section: str
    label: str
    color: str
    sort_order: int
    is_active: bool


@app.get("/resources", response_model=List[ResourceOut])
def list_resources(section: Optional[str] = None, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    query = db.query(Resource).filter(Resource.tenant_id == current_user.tenant_id, Resource.is_active == True)
    if section:
        query = query.filter(Resource.section == section)
    items = query.order_by(Resource.sort_order).all()
    db.close()
    return items


@app.post("/resources", response_model=ResourceOut)
def create_resource(data: ResourceCreate, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = Resource(
        tenant_id=current_user.tenant_id,
        section=data.section,
        label=data.label,
        color=data.color,
        sort_order=data.sort_order,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    db.close()
    return item


@app.put("/resources/{item_id}", response_model=ResourceOut)
def update_resource(item_id: int, data: ResourceUpdate, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = db.query(Resource).filter(Resource.id == item_id, Resource.tenant_id == current_user.tenant_id).first()
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    if data.label is not None:
        item.label = data.label
    if data.color is not None:
        item.color = data.color
    if data.sort_order is not None:
        item.sort_order = data.sort_order
    if data.is_active is not None:
        item.is_active = data.is_active
    db.commit()
    db.refresh(item)
    db.close()
    return item


@app.delete("/resources/{item_id}")
def delete_resource(item_id: int, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = db.query(Resource).filter(Resource.id == item_id, Resource.tenant_id == current_user.tenant_id).first()
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    # Soft delete — historical records may still reference this id via resource_id.
    item.is_active = False
    db.commit()
    db.close()
    return "Удалено"


# ============================== Sections (разделы бизнеса) ==============================

VALID_SLOT_STEPS = {15, 30, 60}


class SectionCreate(BaseModel):
    label: str
    icon: str
    template: str  # "time_slot" | "date_range" | "queue"
    slot_step_minutes: int = 30


class SectionUpdate(BaseModel):
    label: Optional[str] = None
    icon: Optional[str] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = None
    slot_step_minutes: Optional[int] = None


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    label: str
    icon: str
    template: str
    enabled: bool
    sort_order: int
    slot_step_minutes: int


@app.get("/sections", response_model=List[SectionOut])
def list_sections(current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    items = (
        db.query(Section)
        .filter(Section.tenant_id == current_user.tenant_id)
        .order_by(Section.sort_order)
        .all()
    )
    db.close()
    return items


@app.post("/sections", response_model=SectionOut)
def create_section(data: SectionCreate, current_user: User = Depends(require_owner)):
    if data.template not in VALID_TEMPLATES:
        raise HTTPException(status_code=400, detail="Неизвестный шаблон раздела")
    if data.slot_step_minutes not in VALID_SLOT_STEPS:
        raise HTTPException(status_code=400, detail="Недопустимый шаг времени")
    db = SessionLocal()
    key = unique_section_key(db, current_user.tenant_id, data.label)
    max_order = (
        db.query(func.max(Section.sort_order)).filter(Section.tenant_id == current_user.tenant_id).scalar() or 0
    )
    item = Section(
        tenant_id=current_user.tenant_id,
        key=key,
        label=data.label,
        icon=data.icon,
        template=data.template,
        enabled=True,
        sort_order=max_order + 1,
        slot_step_minutes=data.slot_step_minutes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    db.close()
    return item


@app.put("/sections/{section_id}", response_model=SectionOut)
def update_section(section_id: int, data: SectionUpdate, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = db.query(Section).filter(Section.id == section_id, Section.tenant_id == current_user.tenant_id).first()
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Раздел не найден")
    if data.label is not None:
        item.label = data.label
    if data.icon is not None:
        item.icon = data.icon
    if data.enabled is not None:
        item.enabled = data.enabled
    if data.sort_order is not None:
        item.sort_order = data.sort_order
    if data.slot_step_minutes is not None:
        if data.slot_step_minutes not in VALID_SLOT_STEPS:
            db.close()
            raise HTTPException(status_code=400, detail="Недопустимый шаг времени")
        item.slot_step_minutes = data.slot_step_minutes
    db.commit()
    db.refresh(item)
    db.close()
    return item


@app.delete("/sections/{section_id}")
def delete_section(section_id: int, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = db.query(Section).filter(Section.id == section_id, Section.tenant_id == current_user.tenant_id).first()
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Раздел не найден")

    has_resources = (
        db.query(Resource)
        .filter(Resource.tenant_id == current_user.tenant_id, Resource.section == item.key, Resource.is_active == True)
        .first()
        is not None
    )
    if has_resources:
        db.close()
        raise HTTPException(status_code=400, detail="Сначала удалите номера/боксы этого раздела")

    has_records = (
        db.query(Record)
        .filter(Record.tenant_id == current_user.tenant_id, Record.section == item.key)
        .first()
        is not None
    )
    if has_records:
        db.close()
        raise HTTPException(status_code=400, detail="Сначала удалите записи этого раздела")

    db.delete(item)
    db.commit()
    db.close()
    return "Раздел удалён"


# ============================== Records (записи любого раздела) ==============================

class RecordCreate(BaseModel):
    title: str
    resource_id: Optional[int] = None
    price: Optional[int] = None
    start: str
    end: Optional[str] = None
    adult: Optional[int] = None
    child: Optional[int] = None


class RecordUpdate(BaseModel):
    title: str
    resource_id: Optional[int] = None
    price: Optional[int] = None
    start: str
    end: Optional[str] = None
    adult: Optional[int] = None
    child: Optional[int] = None


@app.get("/records")
def list_records(section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=False)
    items = (
        db.query(Record)
        .filter(Record.tenant_id == current_user.tenant_id, Record.section == section)
        .all()
    )
    db.close()
    return items


@app.post("/records")
def create_record(section: str, data: RecordCreate, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = Record(
        tenant_id=current_user.tenant_id,
        section=section,
        resource_id=data.resource_id,
        title=data.title,
        price=data.price,
        start=data.start,
        end=data.end,
        adult=data.adult,
        child=data.child,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    db.close()
    return "Запись добавлена"


@app.put("/records/{item_id}")
def update_record(item_id: int, section: str, data: RecordUpdate, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(Record)
        .filter(Record.id == item_id, Record.tenant_id == current_user.tenant_id, Record.section == section)
        .first()
    )
    if item is None:
        db.close()
        return {"error": "Record not found"}
    item.title = data.title
    item.resource_id = data.resource_id
    item.price = data.price
    item.start = data.start
    item.end = data.end
    item.adult = data.adult
    item.child = data.child
    db.commit()
    db.close()
    return "Запись отредактирована"


@app.delete("/records/{item_id}")
def delete_record(item_id: int, section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(Record)
        .filter(Record.id == item_id, Record.tenant_id == current_user.tenant_id, Record.section == section)
        .first()
    )
    if item is None:
        db.close()
        return {"error": "Record not found"}
    db.delete(item)
    db.commit()
    db.close()
    return "Запись удалена"
