"""User administration (SEC-4, TC-AUTH-04). Every endpoint here is Admin-only."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import User, UserSession
from app.rbac import ADMIN, CurrentUser, require_roles
from app.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])
admin_only = require_roles(ADMIN)
audit = logging.getLogger("pms.audit")


def _out(u: User) -> UserOut:
    return UserOut(userId=u.user_id, name=u.name, email=u.email, role=u.role, active=u.active,
                   storeId=u.store_id)


def _find(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.user_id == user_id))
    if user is None:
        raise ApiError(404, "NOT_FOUND", "User not found")
    return user


def _end_sessions(db: Session, user: User) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.user_pk == user.id, UserSession.ended_at.is_(None))
        .values(ended_at=datetime.now(timezone.utc))
    )


@router.get("", response_model=list[UserOut])
def list_users(admin: CurrentUser = Depends(admin_only), db: Session = Depends(get_db)):
    return [_out(u) for u in db.scalars(select(User).order_by(User.user_id))]


@router.post("", status_code=201, response_model=UserOut)
def create_user(body: UserCreate, admin: CurrentUser = Depends(admin_only),
                db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.user_id == body.userId)):
        raise ApiError(409, "USER_EXISTS", "User ID already exists")
    user = User(store_id=get_settings().store_id, user_id=body.userId, name=body.name,
                email=body.email, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    audit.info("USER_CREATED by=%s user=%s role=%s", admin.user_id, user.user_id, user.role)
    return _out(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, admin: CurrentUser = Depends(admin_only),
                db: Session = Depends(get_db)):
    """Edit name/email or assign a new role. A role change applies on the user's next request."""
    user = _find(db, user_id)
    if user.user_id == admin.user_id and body.role not in (None, ADMIN):
        raise ApiError(400, "SELF_DEMOTION", "You cannot remove your own Admin role")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    audit.info("USER_UPDATED by=%s user=%s fields=%s", admin.user_id, user.user_id,
               ",".join(changes))
    return _out(user)


@router.patch("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: str, admin: CurrentUser = Depends(admin_only),
                    db: Session = Depends(get_db)):
    """Login is refused and open sessions end now; the user's past records are kept."""
    user = _find(db, user_id)
    if user.user_id == admin.user_id:
        raise ApiError(400, "SELF_DEACTIVATION", "You cannot deactivate your own account")
    user.active = False
    _end_sessions(db, user)
    db.commit()
    audit.info("USER_DEACTIVATED by=%s user=%s", admin.user_id, user.user_id)
    return _out(user)


@router.patch("/{user_id}/activate", response_model=UserOut)
def activate_user(user_id: str, admin: CurrentUser = Depends(admin_only),
                  db: Session = Depends(get_db)):
    user = _find(db, user_id)
    user.active = True
    db.commit()
    audit.info("USER_ACTIVATED by=%s user=%s", admin.user_id, user.user_id)
    return _out(user)
