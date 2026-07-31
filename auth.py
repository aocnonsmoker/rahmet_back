import os
from datetime import datetime, timedelta, timezone
from typing import List

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from models import Subscription, User, UserSection, get_db

load_dotenv()

JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 14  # 2 weeks — staff devices stay logged in

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user: User, sections: List[str]) -> str:
    payload = {
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "role": user.role,
        "sections": sections,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось подтвердить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise credentials_error

    # Re-load from DB rather than trusting the token payload alone — role/is_active
    # may have changed (e.g. owner deactivated the employee) since the token was issued.
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_active_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    subscription = db.query(Subscription).filter(Subscription.tenant_id == user.tenant_id).first()
    is_active = (
        subscription is not None
        and subscription.status in ("trial", "active")
        and subscription.expires_at > datetime.utcnow()
    )
    if not is_active:
        raise HTTPException(status_code=402, detail="Подписка неактивна. Обратитесь к администратору.")
    return user


def require_owner(user: User = Depends(require_active_subscription)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Доступно только владельцу")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    # Platform-level access, deliberately independent of require_active_subscription —
    # the admin's own tenant is a service account, not a paying customer.
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Доступно только администратору платформы")
    return user


def require_section(section: str, write: bool = False):
    """Owner always passes; an employee must have this section assigned.
    When write=True, a read_only employee is rejected even if the section matches
    (used on create/update/delete endpoints — GET stays available to read_only staff)."""

    def _check(user: User = Depends(require_active_subscription), db: Session = Depends(get_db)) -> User:
        if user.role == "owner":
            return user
        allowed = (
            db.query(UserSection)
            .filter(UserSection.user_id == user.id, UserSection.section == section)
            .first()
        )
        if allowed is None:
            raise HTTPException(status_code=403, detail="Нет доступа к этому разделу")
        if write and user.read_only:
            raise HTTPException(status_code=403, detail="Доступ только для просмотра")
        return user

    return _check


def assert_section_access(db: Session, user: User, section: str, write: bool = False) -> None:
    """Same rule as require_section(), but callable directly for endpoints (like /records)
    where the section is a runtime query parameter rather than fixed at route-declaration time."""
    if user.role == "owner":
        return
    allowed = (
        db.query(UserSection)
        .filter(UserSection.user_id == user.id, UserSection.section == section)
        .first()
    )
    if allowed is None:
        raise HTTPException(status_code=403, detail="Нет доступа к этому разделу")
    if write and user.read_only:
        raise HTTPException(status_code=403, detail="Доступ только для просмотра")


def get_user_sections(db: Session, user: User) -> List[str]:
    return [s.section for s in db.query(UserSection).filter(UserSection.user_id == user.id).all()]
