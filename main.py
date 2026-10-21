import calendar
import json
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func

from auth import (
    assert_section_access,
    create_access_token,
    get_current_user,
    get_user_from_token_unsafe,
    get_user_sections,
    hash_password,
    require_active_subscription,
    require_owner,
    require_superadmin,
    verify_password,
)
from models import (
    Attendance,
    AuditLog,
    Client,
    GroupSchedule,
    Membership,
    MembershipResource,
    Record,
    Resource,
    Section,
    SessionLocal,
    Subscription,
    Tenant,
    Trainer,
    TrainerResource,
    TrialLesson,
    User,
    UserSection,
)

VALID_TEMPLATES = {"time_slot", "date_range", "queue", "club"}

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


# ============================== Audit log ==============================
# A generic middleware instead of instrumenting each endpoint individually —
# guarantees every current and future create/update/delete is captured
# without anyone having to remember to add a log call to a new route.

AUDIT_ACTION_BY_METHOD = {"POST": "create", "PUT": "update", "DELETE": "delete"}
AUDIT_SKIP_PREFIXES = ("/auth", "/admin", "/audit_logs")
AUDIT_SUMMARY_FIELDS = ["full_name", "label", "username", "phone", "status"]
# A DELETE's response body never carries the deleted row's own data, so the
# usual "pull a label from the response JSON" trick can't work for it — this
# maps a path's first segment to the model/field to look up *before* the
# delete runs, for entities that carry a natural label on their own row.
AUDIT_DELETE_SUMMARY_SOURCES = {
    "trainers": (Trainer, "full_name"),
    "resources": (Resource, "label"),
    "clients": (Client, "full_name"),
    "trial_lessons": (TrialLesson, "full_name"),
    "users": (User, "username"),
    "sections": (Section, "label"),
}


def _lookup_delete_summary(path: str):
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2 or not segments[-1].isdigit():
        return None
    model_field = AUDIT_DELETE_SUMMARY_SOURCES.get(segments[0])
    if not model_field:
        return None
    model, field = model_field
    db = SessionLocal()
    try:
        row = db.query(model).filter(model.id == int(segments[-1])).first()
        return getattr(row, field, None) if row else None
    finally:
        db.close()


def _audit_summary(data):
    if isinstance(data, dict):
        for field in AUDIT_SUMMARY_FIELDS:
            value = data.get(field)
            if value:
                return str(value)[:200]
    return None


ATTENDANCE_STATUS_LABELS = {
    "present": "был",
    "absent": "пропуск",
    "trainer_cancelled": "отменил тренер",
    "makeup": "отработка",
}


def _attendance_summary(request: Request, request_data, response_data):
    # Attendance marks don't carry the client's name themselves (just
    # membership_id) — a plain field pull would only ever show the raw
    # status, which is meaningless without knowing whose it is.
    membership_id = None
    status = None
    for data in (request_data, response_data):
        if isinstance(data, dict):
            membership_id = membership_id or data.get("membership_id")
            status = status or data.get("status")
    if membership_id is None:
        membership_id = request.query_params.get("membership_id")
    if not membership_id:
        return None

    db = SessionLocal()
    try:
        membership = db.query(Membership).filter(Membership.id == int(membership_id)).first()
        if membership is None:
            return None
        client = db.query(Client).filter(Client.id == membership.client_id).first()
        if client is None:
            return None
        status_label = ATTENDANCE_STATUS_LABELS.get(status, status)
        return f"{client.full_name} — {status_label}" if status_label else client.full_name
    finally:
        db.close()


def _write_audit_log(request: Request, body_bytes: bytes, resp_bytes: bytes, pre_delete_summary=None) -> None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return
    token = auth_header[7:]

    db = SessionLocal()
    try:
        user = get_user_from_token_unsafe(token, db)
        if user is None:
            return

        segments = [s for s in request.url.path.split("/") if s]
        if not segments:
            return
        entity_type = segments[0]
        entity_id = None
        action = AUDIT_ACTION_BY_METHOD[request.method]
        if segments[-1].isdigit():
            entity_id = int(segments[-1])
        elif len(segments) >= 3 and segments[-2].isdigit():
            # e.g. /memberships/12/renew — id is the second-to-last segment,
            # the trailing word is a more specific action than the HTTP verb.
            entity_id = int(segments[-2])
            action = segments[-1]

        request_data = response_data = None
        try:
            request_data = json.loads(body_bytes) if body_bytes else None
        except (ValueError, UnicodeDecodeError):
            pass
        try:
            response_data = json.loads(resp_bytes) if resp_bytes else None
        except (ValueError, UnicodeDecodeError):
            pass

        if entity_id is None and isinstance(response_data, dict):
            entity_id = response_data.get("id")

        if entity_type == "attendance":
            summary = _attendance_summary(request, request_data, response_data)
        else:
            summary = _audit_summary(response_data) or _audit_summary(request_data) or pre_delete_summary

        db.add(AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            username=user.username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            section=request.query_params.get("section"),
            summary=summary,
            # Stored as naive UTC regardless of the DB server's timezone setting;
            # /audit_logs tags it as UTC so browsers show their local time.
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.commit()
    finally:
        db.close()


@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    if request.method not in AUDIT_ACTION_BY_METHOD or request.url.path.startswith(AUDIT_SKIP_PREFIXES):
        return await call_next(request)

    body_bytes = await request.body()

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    request._receive = receive  # replay the body we just consumed for the real route handler

    pre_delete_summary = None
    if request.method == "DELETE":
        try:
            pre_delete_summary = _lookup_delete_summary(request.url.path)
        except Exception:
            pass

    response = await call_next(request)

    resp_bytes = b""
    async for chunk in response.body_iterator:
        resp_bytes += chunk

    async def new_body_iterator():
        yield resp_bytes

    response.body_iterator = new_body_iterator()

    if 200 <= response.status_code < 300:
        try:
            _write_audit_log(request, body_bytes, resp_bytes, pre_delete_summary)
        except Exception:
            pass  # logging must never break the actual request

    return response


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
    # Код компании и логин не обязаны совпадать по регистру — сравниваем в нижнем
    # регистре, чтобы "Urban-sport"/"Raushan" находили tenant/user так же, как
    # "urban-sport"/"raushan".
    tenant = db.query(Tenant).filter(func.lower(Tenant.slug) == data.tenant_slug.strip().lower()).first()
    invalid = HTTPException(status_code=401, detail="Неверный код компании, логин или пароль")
    if tenant is None:
        db.close()
        raise invalid

    user = (
        db.query(User)
        .filter(
            User.tenant_id == tenant.id,
            func.lower(User.username) == data.username.strip().lower(),
            User.is_active == True,
        )
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


# ============================== Platform admin (superadmin-only) ==============================

VALID_SUBSCRIPTION_STATUSES = {"trial", "active", "expired"}


class AdminTenantOut(BaseModel):
    id: int
    name: str
    slug: str
    subscription_status: str
    subscription_expires_at: Optional[datetime] = None
    subscription_notes: Optional[str] = None
    owner_username: Optional[str] = None


class AdminTenantCreate(BaseModel):
    name: str
    slug: str
    owner_username: str
    owner_password: str
    subscription_status: str = "trial"
    subscription_expires_at: str


class AdminSubscriptionUpdate(BaseModel):
    status: str
    expires_at: str
    notes: Optional[str] = None


class AdminUserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool


class AdminPasswordUpdate(BaseModel):
    password: str


def admin_tenant_out(db, tenant: Tenant) -> AdminTenantOut:
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
    owner = (
        db.query(User)
        .filter(User.tenant_id == tenant.id, User.role == "owner")
        .order_by(User.id)
        .first()
    )
    return AdminTenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        subscription_status=sub.status if sub else "expired",
        subscription_expires_at=sub.expires_at if sub else None,
        subscription_notes=sub.notes if sub else None,
        owner_username=owner.username if owner else None,
    )


@app.get("/admin/tenants", response_model=List[AdminTenantOut])
def admin_list_tenants(current_user: User = Depends(require_superadmin)):
    db = SessionLocal()
    tenants = db.query(Tenant).filter(Tenant.slug != "jmb").order_by(Tenant.id).all()
    result = [admin_tenant_out(db, t) for t in tenants]
    db.close()
    return result


@app.post("/admin/tenants", response_model=AdminTenantOut)
def admin_create_tenant(data: AdminTenantCreate, current_user: User = Depends(require_superadmin)):
    if data.subscription_status not in VALID_SUBSCRIPTION_STATUSES:
        raise HTTPException(status_code=400, detail="Недопустимый статус подписки")
    db = SessionLocal()
    existing = db.query(Tenant).filter(Tenant.slug == data.slug).first()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Такой код компании уже занят")
    try:
        expires_at = datetime.fromisoformat(data.subscription_expires_at)
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Неверный формат даты окончания подписки")

    tenant = Tenant(name=data.name.strip(), slug=data.slug.strip())
    db.add(tenant)
    db.flush()
    db.add(Subscription(tenant_id=tenant.id, status=data.subscription_status, expires_at=expires_at))
    db.add(
        User(
            tenant_id=tenant.id,
            username=data.owner_username.strip(),
            password_hash=hash_password(data.owner_password),
            role="owner",
            is_active=True,
            read_only=False,
        )
    )
    db.commit()
    result = admin_tenant_out(db, tenant)
    db.close()
    return result


@app.put("/admin/tenants/{tenant_id}/subscription", response_model=AdminTenantOut)
def admin_update_subscription(
    tenant_id: int, data: AdminSubscriptionUpdate, current_user: User = Depends(require_superadmin)
):
    if data.status not in VALID_SUBSCRIPTION_STATUSES:
        raise HTTPException(status_code=400, detail="Недопустимый статус подписки")
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        db.close()
        raise HTTPException(status_code=404, detail="Компания не найдена")
    try:
        expires_at = datetime.fromisoformat(data.expires_at)
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Неверный формат даты окончания подписки")

    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub is None:
        sub = Subscription(tenant_id=tenant_id, status=data.status, expires_at=expires_at, notes=data.notes)
        db.add(sub)
    else:
        sub.status = data.status
        sub.expires_at = expires_at
        sub.notes = data.notes
    db.commit()
    result = admin_tenant_out(db, tenant)
    db.close()
    return result


@app.get("/admin/tenants/{tenant_id}/users", response_model=List[AdminUserOut])
def admin_list_tenant_users(tenant_id: int, current_user: User = Depends(require_superadmin)):
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        db.close()
        raise HTTPException(status_code=404, detail="Компания не найдена")
    users = db.query(User).filter(User.tenant_id == tenant_id).order_by(User.id).all()
    result = [AdminUserOut(id=u.id, username=u.username, role=u.role, is_active=u.is_active) for u in users]
    db.close()
    return result


@app.put("/admin/users/{user_id}/password")
def admin_reset_password(user_id: int, data: AdminPasswordUpdate, current_user: User = Depends(require_superadmin)):
    if not data.password:
        raise HTTPException(status_code=400, detail="Введите новый пароль")
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        db.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.password_hash = hash_password(data.password)
    db.commit()
    db.close()
    return "Пароль обновлён"


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

class TrainerCreate(BaseModel):
    section: str
    full_name: str
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    resource_ids: List[int] = []


class TrainerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    is_active: Optional[bool] = None
    resource_ids: Optional[List[int]] = None


class TrainerOut(BaseModel):
    id: int
    section: str
    full_name: str
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    is_active: bool
    resource_ids: List[int]


def trainer_out(t: Trainer, resource_ids: List[int]) -> dict:
    return {
        "id": t.id,
        "section": t.section,
        "full_name": t.full_name,
        "phone": t.phone,
        "photo_url": t.photo_url,
        "is_active": t.is_active,
        "resource_ids": resource_ids,
    }


def get_trainer_resource_ids(db, trainer_ids: List[int]) -> dict:
    result = {tid: [] for tid in trainer_ids}
    if not trainer_ids:
        return result
    rows = db.query(TrainerResource).filter(TrainerResource.trainer_id.in_(trainer_ids)).all()
    for row in rows:
        result[row.trainer_id].append(row.resource_id)
    return result


@app.get("/trainers", response_model=List[TrainerOut])
def list_trainers(section: Optional[str] = None, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    query = db.query(Trainer).filter(Trainer.tenant_id == current_user.tenant_id, Trainer.is_active == True)
    if section:
        query = query.filter(Trainer.section == section)
    items = query.all()
    resource_map = get_trainer_resource_ids(db, [t.id for t in items])
    result = [trainer_out(t, resource_map[t.id]) for t in items]
    db.close()
    return result


@app.post("/trainers", response_model=TrainerOut)
def create_trainer(data: TrainerCreate, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = Trainer(
        tenant_id=current_user.tenant_id,
        section=data.section,
        full_name=data.full_name,
        phone=data.phone,
        photo_url=data.photo_url,
        is_active=True,
    )
    db.add(item)
    db.flush()
    for resource_id in data.resource_ids:
        db.add(TrainerResource(trainer_id=item.id, resource_id=resource_id))
    db.commit()
    db.refresh(item)
    result = trainer_out(item, data.resource_ids)
    db.close()
    return result


@app.put("/trainers/{item_id}", response_model=TrainerOut)
def update_trainer(item_id: int, data: TrainerUpdate, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = db.query(Trainer).filter(Trainer.id == item_id, Trainer.tenant_id == current_user.tenant_id).first()
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    if data.full_name is not None:
        item.full_name = data.full_name
    if data.phone is not None:
        item.phone = data.phone
    if data.photo_url is not None:
        item.photo_url = data.photo_url
    if data.is_active is not None:
        item.is_active = data.is_active
    if data.resource_ids is not None:
        db.query(TrainerResource).filter(TrainerResource.trainer_id == item.id).delete()
        for resource_id in data.resource_ids:
            db.add(TrainerResource(trainer_id=item.id, resource_id=resource_id))
    db.commit()
    db.refresh(item)
    resource_ids = get_trainer_resource_ids(db, [item.id])[item.id]
    result = trainer_out(item, resource_ids)
    db.close()
    return result


@app.delete("/trainers/{item_id}")
def delete_trainer(item_id: int, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = db.query(Trainer).filter(Trainer.id == item_id, Trainer.tenant_id == current_user.tenant_id).first()
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    # Soft delete — groups may still reference this trainer via trainer_resources.
    item.is_active = False
    db.commit()
    db.close()
    return "Удалено"


VALID_RESOURCE_KINDS = {"group", "room"}


class ResourceCreate(BaseModel):
    section: str
    label: str
    color: str
    sort_order: int = 0
    kind: str = "group"


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
    kind: str


@app.get("/resources", response_model=List[ResourceOut])
def list_resources(
    section: Optional[str] = None, kind: Optional[str] = None, current_user: User = Depends(require_active_subscription)
):
    db = SessionLocal()
    query = db.query(Resource).filter(Resource.tenant_id == current_user.tenant_id, Resource.is_active == True)
    if section:
        query = query.filter(Resource.section == section)
    if kind:
        query = query.filter(Resource.kind == kind)
    items = query.order_by(Resource.sort_order).all()
    db.close()
    return items


@app.post("/resources", response_model=ResourceOut)
def create_resource(data: ResourceCreate, current_user: User = Depends(require_owner)):
    if data.kind not in VALID_RESOURCE_KINDS:
        raise HTTPException(status_code=400, detail="Недопустимый тип ресурса")
    db = SessionLocal()
    item = Resource(
        tenant_id=current_user.tenant_id,
        section=data.section,
        label=data.label,
        color=data.color,
        sort_order=data.sort_order,
        is_active=True,
        kind=data.kind,
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


class DayTime(BaseModel):
    day: int
    start_time: str
    end_time: str


class GroupScheduleCreate(BaseModel):
    resource_id: int
    room_id: int
    day_times: List[DayTime]


class GroupScheduleUpdate(BaseModel):
    resource_id: Optional[int] = None
    room_id: Optional[int] = None
    day_times: Optional[List[DayTime]] = None


def schedule_out(s: GroupSchedule) -> dict:
    return {
        "id": s.id,
        "section": s.section,
        "resource_id": s.resource_id,
        "room_id": s.room_id,
        "day_times": s.day_times,
    }


def validate_day_times(day_times: List[DayTime]):
    if not day_times:
        raise HTTPException(status_code=400, detail="Выберите хотя бы один день")
    seen_days = set()
    for dt in day_times:
        if dt.day < 0 or dt.day > 6:
            raise HTTPException(status_code=400, detail="Некорректный день недели")
        if dt.day in seen_days:
            raise HTTPException(status_code=400, detail="День недели указан дважды")
        seen_days.add(dt.day)
        if not dt.start_time or not dt.end_time or dt.start_time >= dt.end_time:
            raise HTTPException(status_code=400, detail="Некорректное время")


@app.get("/group_schedules")
def list_group_schedules(section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    items = (
        db.query(GroupSchedule)
        .filter(GroupSchedule.tenant_id == current_user.tenant_id, GroupSchedule.section == section)
        .all()
    )
    result = [schedule_out(s) for s in items]
    db.close()
    return result


@app.post("/group_schedules")
def create_group_schedule(section: str, data: GroupScheduleCreate, current_user: User = Depends(require_owner)):
    validate_day_times(data.day_times)
    db = SessionLocal()
    item = GroupSchedule(
        tenant_id=current_user.tenant_id,
        section=section,
        resource_id=data.resource_id,
        room_id=data.room_id,
        day_times=[dt.dict() for dt in data.day_times],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    result = schedule_out(item)
    db.close()
    return result


@app.put("/group_schedules/{item_id}")
def update_group_schedule(
    item_id: int, section: str, data: GroupScheduleUpdate, current_user: User = Depends(require_owner)
):
    db = SessionLocal()
    item = (
        db.query(GroupSchedule)
        .filter(GroupSchedule.id == item_id, GroupSchedule.tenant_id == current_user.tenant_id, GroupSchedule.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    if data.resource_id is not None:
        item.resource_id = data.resource_id
    if data.room_id is not None:
        item.room_id = data.room_id
    if data.day_times is not None:
        validate_day_times(data.day_times)
        item.day_times = [dt.dict() for dt in data.day_times]
    db.commit()
    db.refresh(item)
    result = schedule_out(item)
    db.close()
    return result


@app.delete("/group_schedules/{item_id}")
def delete_group_schedule(item_id: int, section: str, current_user: User = Depends(require_owner)):
    db = SessionLocal()
    item = (
        db.query(GroupSchedule)
        .filter(GroupSchedule.id == item_id, GroupSchedule.tenant_id == current_user.tenant_id, GroupSchedule.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    db.delete(item)
    db.commit()
    db.close()
    return "Удалено"


# ============================== Sections (разделы бизнеса) ==============================

VALID_SLOT_STEPS = {15, 30, 60}
VALID_GUEST_FIELDS = {"none", "single", "split"}


class SectionCreate(BaseModel):
    label: str
    icon: str
    template: str  # "time_slot" | "date_range" | "queue"
    slot_step_minutes: int = 30
    guest_fields: str = "none"


class SectionUpdate(BaseModel):
    label: Optional[str] = None
    icon: Optional[str] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = None
    slot_step_minutes: Optional[int] = None
    guest_fields: Optional[str] = None


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
    guest_fields: str


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
    if data.guest_fields not in VALID_GUEST_FIELDS:
        raise HTTPException(status_code=400, detail="Недопустимый режим учёта людей")
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
        guest_fields=data.guest_fields,
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
    if data.guest_fields is not None:
        if data.guest_fields not in VALID_GUEST_FIELDS:
            db.close()
            raise HTTPException(status_code=400, detail="Недопустимый режим учёта людей")
        item.guest_fields = data.guest_fields
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

    has_trainers = (
        db.query(Trainer)
        .filter(Trainer.tenant_id == current_user.tenant_id, Trainer.section == item.key, Trainer.is_active == True)
        .first()
        is not None
    )
    if has_trainers:
        db.close()
        raise HTTPException(status_code=400, detail="Сначала удалите тренеров этого раздела")

    # Records referencing an already-deactivated resource are invisible in
    # every UI (resource lists filter is_active=True) — there is no way for
    # an owner to find and delete them by hand, so they'd block section
    # deletion forever. has_resources above already guarantees no *active*
    # resource remains, so any record with a resource_id here can only point
    # at an inactive one — safe to clean up together with the section.
    # Records with no resource_id (queue template) are real reachable
    # history and still block deletion.
    blocking_record = (
        db.query(Record)
        .filter(Record.tenant_id == current_user.tenant_id, Record.section == item.key)
        .filter(Record.resource_id.is_(None))
        .first()
    )
    if blocking_record is not None:
        db.close()
        raise HTTPException(status_code=400, detail="Сначала удалите записи этого раздела")

    # Trial lessons never have a resource_id (club template has no per-group
    # capacity concept, see trial_lessons table) — same reasoning as queue
    # records above, they're always reachable history and must block deletion.
    blocking_trial = (
        db.query(TrialLesson)
        .filter(TrialLesson.tenant_id == current_user.tenant_id, TrialLesson.section == item.key)
        .first()
    )
    if blocking_trial is not None:
        db.close()
        raise HTTPException(status_code=400, detail="Сначала удалите записи на пробные занятия этого раздела")

    # Memberships can only reference an inactive group at this point
    # (has_resources above already guarantees no active one remains) —
    # same as inactive-resource records, safe to clean up together with the section.
    membership_ids = [
        m.id
        for m in db.query(Membership.id)
        .filter(Membership.tenant_id == current_user.tenant_id, Membership.section == item.key)
        .all()
    ]
    if membership_ids:
        db.query(Attendance).filter(Attendance.membership_id.in_(membership_ids)).delete(synchronize_session=False)
        db.query(MembershipResource).filter(MembershipResource.membership_id.in_(membership_ids)).delete(synchronize_session=False)
        db.query(Membership).filter(Membership.id.in_(membership_ids)).delete(synchronize_session=False)

    db.query(Client).filter(Client.tenant_id == current_user.tenant_id, Client.section == item.key).delete()
    db.query(GroupSchedule).filter(GroupSchedule.tenant_id == current_user.tenant_id, GroupSchedule.section == item.key).delete()

    db.query(Record).filter(Record.tenant_id == current_user.tenant_id, Record.section == item.key).delete()
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
def list_records(
    section: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    current_user: User = Depends(require_active_subscription),
):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=False)
    query = db.query(Record).filter(Record.tenant_id == current_user.tenant_id, Record.section == section)
    if start is not None:
        query = query.filter(Record.start >= datetime.fromisoformat(start.replace(" ", "T")))
    if end is not None:
        query = query.filter(Record.start < datetime.fromisoformat(end.replace(" ", "T")))
    items = query.all()
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


# ============================== Club module (клиенты/абонементы, посещаемость, пробные) ==============================

VALID_MEMBERSHIP_STATUSES = {"active", "expired", "frozen"}
# "trainer_cancelled" marks a day the trainer cancelled (own color in the journal);
# "makeup" marks an unrelated day the client attended to compensate for a cancelled
# one — it's a plain visual tag, not linked to a specific cancelled date.
VALID_ATTENDANCE_STATUSES = {"present", "absent", "trainer_cancelled", "makeup"}


def auto_membership_end_date(start_date) -> datetime:
    """A month out from start_date, minus a day — e.g. Sep 16 -> Oct 15."""
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date[:10], "%Y-%m-%d")
    year = start_date.year + (1 if start_date.month == 12 else 0)
    month = 1 if start_date.month == 12 else start_date.month + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return start_date.replace(year=year, month=month, day=day) - timedelta(days=1)
VALID_TRIAL_STATUSES = {"scheduled", "came", "no_show", "bought", "thinking", "declined"}


def client_age(c: Client) -> Optional[int]:
    """Age from the birth date when known, else the legacy manually typed age."""
    if c.birth_date is None:
        return c.age
    today = date.today()
    had_birthday = (today.month, today.day) >= (c.birth_date.month, c.birth_date.day)
    return today.year - c.birth_date.year - (0 if had_birthday else 1)


def parse_birth_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверная дата рождения")
    if parsed > date.today():
        raise HTTPException(status_code=400, detail="Дата рождения не может быть в будущем")
    return parsed


def client_out(c: Client) -> dict:
    return {
        "id": c.id,
        "section": c.section,
        "full_name": c.full_name,
        "phone": c.phone,
        "age": client_age(c),
        "birth_date": c.birth_date.isoformat() if c.birth_date else None,
        "parent_name": c.parent_name,
        "contract_number": c.contract_number,
        "contract_date": c.contract_date,
        "note": c.note,
    }


class ClientCreate(BaseModel):
    full_name: str
    phone: str
    age: Optional[int] = None
    birth_date: Optional[str] = None
    parent_name: Optional[str] = None
    contract_number: Optional[str] = None
    contract_date: Optional[str] = None
    note: Optional[str] = None


class ClientUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    birth_date: Optional[str] = None  # "" clears it
    parent_name: Optional[str] = None
    contract_number: Optional[str] = None
    contract_date: Optional[str] = None
    note: Optional[str] = None


@app.get("/clients")
def list_clients(section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=False)
    rows = (
        db.query(Client)
        .filter(Client.tenant_id == current_user.tenant_id, Client.section == section)
        .order_by(Client.full_name)
        .all()
    )
    result = [client_out(c) for c in rows]
    db.close()
    return result


@app.post("/clients")
def create_client(section: str, data: ClientCreate, current_user: User = Depends(require_active_subscription)):
    birth_date = parse_birth_date(data.birth_date)
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    if data.contract_number:
        existing = (
            db.query(Client)
            .filter(
                Client.tenant_id == current_user.tenant_id,
                Client.section == section,
                Client.contract_number == data.contract_number,
            )
            .first()
        )
        if existing is not None:
            db.close()
            raise HTTPException(status_code=400, detail="Клиент с таким номером договора уже есть в этом разделе")
    item = Client(
        tenant_id=current_user.tenant_id,
        section=section,
        full_name=data.full_name,
        phone=data.phone,
        age=data.age,
        birth_date=birth_date,
        parent_name=data.parent_name,
        contract_number=data.contract_number,
        contract_date=data.contract_date or None,
        note=(data.note or "").strip() or None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    result = client_out(item)
    db.close()
    return result


@app.put("/clients/{client_id}")
def update_client(
    client_id: int, section: str, data: ClientUpdate, current_user: User = Depends(require_active_subscription)
):
    birth_date = parse_birth_date(data.birth_date)
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(Client)
        .filter(Client.id == client_id, Client.tenant_id == current_user.tenant_id, Client.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    if data.full_name is not None:
        item.full_name = data.full_name
    if data.phone is not None:
        item.phone = data.phone
    if data.age is not None:
        item.age = data.age
    if data.birth_date is not None:
        item.birth_date = birth_date
    if data.parent_name is not None:
        item.parent_name = data.parent_name
    if data.contract_number is not None:
        if data.contract_number and data.contract_number != item.contract_number:
            existing = (
                db.query(Client)
                .filter(
                    Client.tenant_id == current_user.tenant_id,
                    Client.section == section,
                    Client.contract_number == data.contract_number,
                    Client.id != item.id,
                )
                .first()
            )
            if existing is not None:
                db.close()
                raise HTTPException(status_code=400, detail="Клиент с таким номером договора уже есть в этом разделе")
        item.contract_number = data.contract_number
    if data.contract_date is not None:
        item.contract_date = data.contract_date or None
    if data.note is not None:
        item.note = data.note.strip() or None
    db.commit()
    db.refresh(item)
    result = client_out(item)
    db.close()
    return result


@app.delete("/clients/{client_id}")
def delete_client(client_id: int, section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(Client)
        .filter(Client.id == client_id, Client.tenant_id == current_user.tenant_id, Client.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    membership_ids = [
        m.id for m in db.query(Membership.id).filter(Membership.tenant_id == current_user.tenant_id, Membership.client_id == item.id).all()
    ]
    if membership_ids:
        db.query(Attendance).filter(Attendance.membership_id.in_(membership_ids)).delete(synchronize_session=False)
        db.query(MembershipResource).filter(MembershipResource.membership_id.in_(membership_ids)).delete(synchronize_session=False)
        db.query(Membership).filter(Membership.id.in_(membership_ids)).delete(synchronize_session=False)
    db.delete(item)
    db.commit()
    db.close()
    return "Клиент удалён"


def membership_out(m: Membership, c: Client, resource_ids: List[int]) -> dict:
    return {
        "id": m.id,
        "client_id": c.id,
        "full_name": c.full_name,
        "phone": c.phone,
        "age": client_age(c),
        "parent_name": c.parent_name,
        "contract_number": c.contract_number,
        "section": m.section,
        "resource_ids": resource_ids,
        "payment_date": m.payment_date,
        "start_date": m.start_date,
        "end_date": m.end_date,
        "price": m.price,
        "status": m.status,
        "frozen_at": m.frozen_at,
        "paid": m.paid,
    }


def get_membership_resource_ids(db, membership_ids: List[int]) -> dict:
    result = {mid: [] for mid in membership_ids}
    if not membership_ids:
        return result
    rows = db.query(MembershipResource).filter(MembershipResource.membership_id.in_(membership_ids)).all()
    for row in rows:
        result[row.membership_id].append(row.resource_id)
    return result


class MembershipCreate(BaseModel):
    client_id: int
    resource_ids: List[int]
    payment_date: Optional[str] = None
    start_date: str
    end_date: str
    price: Optional[int] = None
    status: str = "active"
    paid: bool = True


class MembershipUpdate(BaseModel):
    resource_ids: Optional[List[int]] = None
    payment_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    price: Optional[int] = None
    status: Optional[str] = None
    paid: Optional[bool] = None


class MembershipRenew(BaseModel):
    resource_ids: List[int]
    payment_date: Optional[str] = None
    start_date: str
    end_date: str
    price: Optional[int] = None
    paid: bool = True


@app.get("/memberships")
def list_memberships(
    section: str, client_id: Optional[int] = None, current_user: User = Depends(require_active_subscription)
):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=False)
    query = (
        db.query(Membership, Client)
        .join(Client, Client.id == Membership.client_id)
        .filter(Membership.tenant_id == current_user.tenant_id, Membership.section == section)
    )
    if client_id is not None:
        query = query.filter(Membership.client_id == client_id)
    rows = query.all()
    resource_map = get_membership_resource_ids(db, [m.id for m, c in rows])
    result = [membership_out(m, c, resource_map[m.id]) for m, c in rows]
    db.close()
    return result


@app.post("/memberships")
def create_membership(section: str, data: MembershipCreate, current_user: User = Depends(require_active_subscription)):
    if data.status not in VALID_MEMBERSHIP_STATUSES:
        raise HTTPException(status_code=400, detail="Недопустимый статус абонемента")
    if not data.resource_ids:
        raise HTTPException(status_code=400, detail="Выберите хотя бы одну группу")
    if current_user.role != "owner":
        expected_end = auto_membership_end_date(data.start_date)
        if datetime.strptime(data.end_date[:10], "%Y-%m-%d").date() != expected_end.date():
            raise HTTPException(status_code=403, detail="Дату окончания абонемента может менять только владелец")
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    client = (
        db.query(Client)
        .filter(Client.id == data.client_id, Client.tenant_id == current_user.tenant_id, Client.section == section)
        .first()
    )
    if client is None:
        db.close()
        raise HTTPException(status_code=404, detail="Клиент не найден")
    item = Membership(
        tenant_id=current_user.tenant_id,
        client_id=client.id,
        section=section,
        payment_date=data.payment_date,
        start_date=data.start_date,
        end_date=data.end_date,
        price=data.price,
        status=data.status,
        paid=data.paid,
    )
    db.add(item)
    db.flush()
    for resource_id in data.resource_ids:
        db.add(MembershipResource(membership_id=item.id, resource_id=resource_id))
    db.commit()
    db.refresh(item)
    result = membership_out(item, client, data.resource_ids)
    db.close()
    return result


@app.put("/memberships/{item_id}")
def update_membership(
    item_id: int, section: str, data: MembershipUpdate, current_user: User = Depends(require_active_subscription)
):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(Membership)
        .filter(Membership.id == item_id, Membership.tenant_id == current_user.tenant_id, Membership.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    client = db.query(Client).filter(Client.id == item.client_id).first()
    if data.resource_ids is not None:
        if not data.resource_ids:
            db.close()
            raise HTTPException(status_code=400, detail="Выберите хотя бы одну группу")
        db.query(MembershipResource).filter(MembershipResource.membership_id == item.id).delete()
        for resource_id in data.resource_ids:
            db.add(MembershipResource(membership_id=item.id, resource_id=resource_id))
    if data.payment_date is not None:
        item.payment_date = data.payment_date
    if data.start_date is not None:
        item.start_date = data.start_date
    # Captured before any reassignment below — used as the shift base if this
    # request also unfreezes the membership.
    original_end_date = item.end_date
    if data.end_date is not None:
        if current_user.role != "owner":
            # Не сравниваем с прежней датой напрямую: смена "с" легитимно
            # пересчитывает "по" на фронте и должна проходить у сотрудника тоже —
            # запрещаем только отклонение от формулы "месяц минус день".
            effective_start = data.start_date if data.start_date is not None else item.start_date
            expected_end = auto_membership_end_date(effective_start)
            new_end = datetime.strptime(data.end_date[:10], "%Y-%m-%d")
            if new_end.date() != expected_end.date():
                db.close()
                raise HTTPException(status_code=403, detail="Дату окончания абонемента может менять только владелец")
        item.end_date = data.end_date
    if data.price is not None:
        item.price = data.price
    if data.status is not None:
        if data.status not in VALID_MEMBERSHIP_STATUSES:
            db.close()
            raise HTTPException(status_code=400, detail="Недопустимый статус абонемента")
        if data.status == "frozen" and item.status != "frozen":
            item.frozen_at = datetime.utcnow()
        elif item.status == "frozen" and data.status != "frozen":
            # Push the end date back by however many days the membership sat
            # frozen, so the client doesn't lose paid-for days.
            if item.frozen_at is not None:
                frozen_days = (datetime.utcnow().date() - item.frozen_at.date()).days
                if frozen_days > 0:
                    base_end = original_end_date
                    if isinstance(base_end, str):
                        base_end = datetime.strptime(base_end[:10], "%Y-%m-%d")
                    item.end_date = base_end + timedelta(days=frozen_days)
            item.frozen_at = None
        item.status = data.status
    if data.paid is not None:
        item.paid = data.paid
    db.commit()
    db.refresh(item)
    resource_ids = get_membership_resource_ids(db, [item.id])[item.id]
    result = membership_out(item, client, resource_ids)
    db.close()
    return result


@app.delete("/memberships/{item_id}")
def delete_membership(item_id: int, section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(Membership)
        .filter(Membership.id == item_id, Membership.tenant_id == current_user.tenant_id, Membership.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    db.query(Attendance).filter(Attendance.membership_id == item.id).delete()
    db.query(MembershipResource).filter(MembershipResource.membership_id == item.id).delete()
    db.delete(item)
    db.commit()
    db.close()
    return "Абонемент удалён"


@app.post("/memberships/{item_id}/renew")
def renew_membership(
    item_id: int, section: str, data: MembershipRenew, current_user: User = Depends(require_active_subscription)
):
    if not data.resource_ids:
        raise HTTPException(status_code=400, detail="Выберите хотя бы одну группу")
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    old_item = (
        db.query(Membership)
        .filter(Membership.id == item_id, Membership.tenant_id == current_user.tenant_id, Membership.section == section)
        .first()
    )
    if old_item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    client = db.query(Client).filter(Client.id == old_item.client_id).first()
    # Renewal keeps the old membership around (status flips to "expired") instead of
    # overwriting its dates in place, so past Касса revenue stays attributed to the
    # day it was actually paid and attendance history stays attached to its own period.
    old_item.status = "expired"
    new_item = Membership(
        tenant_id=current_user.tenant_id,
        client_id=old_item.client_id,
        section=section,
        payment_date=data.payment_date,
        start_date=data.start_date,
        end_date=data.end_date,
        price=data.price,
        status="active",
        paid=data.paid,
    )
    db.add(new_item)
    db.flush()
    for resource_id in data.resource_ids:
        db.add(MembershipResource(membership_id=new_item.id, resource_id=resource_id))
    db.commit()
    db.refresh(new_item)
    resource_ids = get_membership_resource_ids(db, [new_item.id])[new_item.id]
    result = membership_out(new_item, client, resource_ids)
    db.close()
    return result


@app.get("/attendance")
def list_attendance(
    section: str,
    resource_id: int,
    start_date: str,
    end_date: str,
    current_user: User = Depends(require_active_subscription),
):
    try:
        range_start = datetime.strptime(start_date, "%Y-%m-%d")
        range_end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты, ожидается YYYY-MM-DD")

    db = SessionLocal()
    assert_section_access(db, current_user, section, write=False)
    rows = (
        db.query(Membership, Client)
        .join(Client, Client.id == Membership.client_id)
        .join(MembershipResource, MembershipResource.membership_id == Membership.id)
        .filter(
            Membership.tenant_id == current_user.tenant_id,
            Membership.section == section,
            Membership.status != "expired",
            MembershipResource.resource_id == resource_id,
            Membership.start_date < range_end,
            Membership.end_date >= range_start,
        )
        .all()
    )
    membership_ids = [m.id for m, c in rows]
    resource_map = get_membership_resource_ids(db, membership_ids)
    memberships = [membership_out(m, c, resource_map[m.id]) for m, c in rows]
    marks = (
        db.query(Attendance)
        .filter(
            Attendance.tenant_id == current_user.tenant_id,
            Attendance.membership_id.in_(membership_ids),
            Attendance.date >= range_start,
            Attendance.date < range_end,
        )
        .all()
        if membership_ids
        else []
    )
    db.close()
    return {"memberships": memberships, "attendance": marks}


class AttendanceMark(BaseModel):
    membership_id: int
    date: str
    status: str


@app.post("/attendance")
def mark_attendance(section: str, data: AttendanceMark, current_user: User = Depends(require_active_subscription)):
    if data.status not in VALID_ATTENDANCE_STATUSES:
        raise HTTPException(status_code=400, detail="Недопустимый статус посещения")
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    membership = (
        db.query(Membership)
        .filter(
            Membership.id == data.membership_id,
            Membership.tenant_id == current_user.tenant_id,
            Membership.section == section,
        )
        .first()
    )
    if membership is None:
        db.close()
        raise HTTPException(status_code=404, detail="Абонемент не найден")
    try:
        mark_date = datetime.fromisoformat(data.date)
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Неверный формат даты")
    existing = (
        db.query(Attendance)
        .filter(Attendance.membership_id == data.membership_id, Attendance.date == mark_date)
        .first()
    )
    if existing is not None:
        existing.status = data.status
    else:
        existing = Attendance(
            tenant_id=current_user.tenant_id,
            membership_id=data.membership_id,
            date=mark_date,
            status=data.status,
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    db.close()
    return existing


@app.delete("/attendance")
def unmark_attendance(
    section: str, membership_id: int, date: str, current_user: User = Depends(require_active_subscription)
):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    membership = (
        db.query(Membership)
        .filter(
            Membership.id == membership_id,
            Membership.tenant_id == current_user.tenant_id,
            Membership.section == section,
        )
        .first()
    )
    if membership is None:
        db.close()
        raise HTTPException(status_code=404, detail="Абонемент не найден")
    try:
        mark_date = datetime.fromisoformat(date)
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Неверный формат даты")
    db.query(Attendance).filter(Attendance.membership_id == membership_id, Attendance.date == mark_date).delete()
    db.commit()
    db.close()
    return "Отметка снята"


class TrialLessonCreate(BaseModel):
    full_name: str
    phone: str
    age: Optional[int] = None
    resource_id: Optional[int] = None
    scheduled_at: str
    status: str = "scheduled"


class TrialLessonUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    resource_id: Optional[int] = None
    scheduled_at: Optional[str] = None
    status: Optional[str] = None


@app.get("/trial_lessons")
def list_trial_lessons(section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=False)
    items = (
        db.query(TrialLesson)
        .filter(TrialLesson.tenant_id == current_user.tenant_id, TrialLesson.section == section)
        .all()
    )
    db.close()
    return items


@app.post("/trial_lessons")
def create_trial_lesson(
    section: str, data: TrialLessonCreate, current_user: User = Depends(require_active_subscription)
):
    if data.status not in VALID_TRIAL_STATUSES:
        raise HTTPException(status_code=400, detail="Недопустимый статус пробного занятия")
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = TrialLesson(
        tenant_id=current_user.tenant_id,
        section=section,
        full_name=data.full_name,
        phone=data.phone,
        age=data.age,
        resource_id=data.resource_id,
        scheduled_at=data.scheduled_at,
        status=data.status,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    db.close()
    return item


@app.put("/trial_lessons/{item_id}")
def update_trial_lesson(
    item_id: int, section: str, data: TrialLessonUpdate, current_user: User = Depends(require_active_subscription)
):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(TrialLesson)
        .filter(TrialLesson.id == item_id, TrialLesson.tenant_id == current_user.tenant_id, TrialLesson.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    if data.full_name is not None:
        item.full_name = data.full_name
    if data.phone is not None:
        item.phone = data.phone
    if data.age is not None:
        item.age = data.age
    if data.resource_id is not None:
        item.resource_id = data.resource_id
    if data.scheduled_at is not None:
        item.scheduled_at = data.scheduled_at
    if data.status is not None:
        if data.status not in VALID_TRIAL_STATUSES:
            db.close()
            raise HTTPException(status_code=400, detail="Недопустимый статус пробного занятия")
        item.status = data.status
    db.commit()
    db.refresh(item)
    db.close()
    return item


@app.delete("/trial_lessons/{item_id}")
def delete_trial_lesson(item_id: int, section: str, current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    assert_section_access(db, current_user, section, write=True)
    item = (
        db.query(TrialLesson)
        .filter(TrialLesson.id == item_id, TrialLesson.tenant_id == current_user.tenant_id, TrialLesson.section == section)
        .first()
    )
    if item is None:
        db.close()
        raise HTTPException(status_code=404, detail="Не найдено")
    db.delete(item)
    db.commit()
    db.close()
    return "Запись удалена"


# ============================== Журнал событий ==============================

class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    section: Optional[str] = None
    section_label: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime


@app.get("/audit_logs", response_model=List[AuditLogOut])
def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    section: Optional[str] = None,
    # Browser's offset from UTC (e.g. 300 for Kazakhstan), so start/end dates
    # mean the user's local calendar days rather than UTC days.
    utc_offset_minutes: int = 0,
    current_user: User = Depends(require_owner),
):
    db = SessionLocal()
    query = db.query(AuditLog).filter(AuditLog.tenant_id == current_user.tenant_id)
    local_to_utc = timedelta(minutes=utc_offset_minutes)
    if start_date:
        query = query.filter(AuditLog.created_at >= datetime.fromisoformat(start_date) - local_to_utc)
    if end_date:
        query = query.filter(AuditLog.created_at < datetime.fromisoformat(end_date) + timedelta(days=1) - local_to_utc)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if section:
        query = query.filter(AuditLog.section == section)
    limit = min(max(limit, 1), 500)
    rows = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    sections = {
        s.key: s.label
        for s in db.query(Section).filter(Section.tenant_id == current_user.tenant_id).all()
    }
    result = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "username": r.username,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "section": r.section,
            "section_label": sections.get(r.section) if r.section else None,
            "summary": r.summary,
            "created_at": r.created_at.replace(tzinfo=timezone.utc),
        }
        for r in rows
    ]
    db.close()
    return result


# ============================== Уведомления по абонементам ==============================
# Aggregated across every club-template section the user can see — the sidebar bell is a
# global element, not scoped to whichever section happens to be open right now.

MEMBERSHIP_WARNING_LABELS = {"debt": "Долг", "frozen": "Заморожен", "expiring": "Скоро закончится"}
MEMBERSHIP_WARNING_ORDER = {"debt": 0, "frozen": 1, "expiring": 2}


@app.get("/membership_warnings")
def list_membership_warnings(current_user: User = Depends(require_active_subscription)):
    db = SessionLocal()
    sections = (
        db.query(Section)
        .filter(Section.tenant_id == current_user.tenant_id, Section.template == "club", Section.enabled == True)
        .all()
    )
    if current_user.role != "owner":
        allowed_keys = set(get_user_sections(db, current_user))
        sections = [s for s in sections if s.key in allowed_keys]
    if not sections:
        db.close()
        return []

    section_keys = [s.key for s in sections]
    section_labels = {s.key: s.label for s in sections}

    rows = (
        db.query(Membership, Client)
        .join(Client, Client.id == Membership.client_id)
        .filter(
            Membership.tenant_id == current_user.tenant_id,
            Membership.section.in_(section_keys),
            Membership.status.in_(["active", "frozen"]),
        )
        .all()
    )
    resource_map = get_membership_resource_ids(db, [m.id for m, c in rows])
    resource_labels = {
        r.id: r.label for r in db.query(Resource).filter(Resource.tenant_id == current_user.tenant_id).all()
    }

    today = datetime.utcnow().date()
    result = []
    for m, c in rows:
        days_left = (m.end_date.date() - today).days
        if not m.paid:
            status = "debt"
        elif m.status == "frozen":
            status = "frozen"
        elif 0 <= days_left <= 3:
            status = "expiring"
        else:
            continue
        result.append({
            "membership_id": m.id,
            "client_id": c.id,
            "client_name": c.full_name,
            "section_key": m.section,
            "section_label": section_labels.get(m.section, m.section),
            "group_labels": ", ".join(resource_labels.get(rid, "—") for rid in resource_map.get(m.id, [])),
            "status": status,
            "status_label": MEMBERSHIP_WARNING_LABELS[status],
            "end_date": m.end_date,
            "days_left": days_left,
        })

    result.sort(key=lambda w: (MEMBERSHIP_WARNING_ORDER[w["status"]], w["days_left"]))
    db.close()
    return result
