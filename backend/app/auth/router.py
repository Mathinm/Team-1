"""Login and logout (SEC-1, TC-AUTH-01), lockout (SEC-3), emailed 2FA code (NFR-10)."""

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.lockout import (
    is_locked,
    locked_error,
    record_failed_login,
    reset_failed_logins,
)
from app.auth.otp import mask_email, requires_otp, send_code, verify_code
from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.schemas import LoginIn, LoginOut, MeOut
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import User, UserSession
from app.rbac import (
    ROLE_MENUS,
    CurrentUser,
    create_access_token,
    get_current_session,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("pms.security")

INVALID_LOGIN = "Invalid user ID or password"


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    """One 401 message for unknown user, wrong password and deactivated user.

    A locked account answers 423 even with the right password (SEC-3).
    """
    user = db.scalar(select(User).where(User.user_id == body.userId.strip()))
    ok = verify_password(body.password, user.password_hash if user else None)
    if user is not None and user.active and is_locked(user):
        log.info("login refused, account locked: user=%s", user.user_id)
        raise locked_error()
    if not ok or user is None or not user.active:
        log.info("login failed: user=%s", body.userId)  # never log the password
        if user is not None and user.active and record_failed_login(user):
            db.commit()
            raise locked_error()  # this was the 5th wrong password in a row
        db.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", INVALID_LOGIN)

    if requires_otp(user):  # NFR-10: Manager and Admin also need the code we email them
        if not body.otpCode:
            send_code(user)
            db.commit()
            raise ApiError(401, "OTP_REQUIRED",
                           f"We emailed a login code to {mask_email(user.email)}. Enter it below.",
                           details={"sentTo": mask_email(user.email)})
        if not verify_code(user, body.otpCode):
            log.info("login failed, wrong 2FA code: user=%s", user.user_id)
            if record_failed_login(user):  # codes count like passwords, so they can't be guessed
                db.commit()
                raise locked_error()
            db.commit()
            raise ApiError(401, "INVALID_OTP", "Invalid or expired code")

    reset_failed_logins(user)

    if needs_rehash(user.password_hash):  # keep stored hashes at today's strength (NFR-9)
        user.password_hash = hash_password(body.password)

    sid = secrets.token_urlsafe(24)
    db.add(UserSession(sid=sid, user_pk=user.id))
    db.commit()
    expires_in = get_settings().token_expire_minutes * 60
    token = create_access_token(user.user_id, user.role, user.name, expires_in, sid=sid)
    log.info("login ok: user=%s role=%s", user.user_id, user.role)
    return LoginOut(token=token, role=user.role, expiresIn=expires_in, name=user.name,
                    userId=user.user_id)


@router.post("/logout", status_code=204)
def logout(session: UserSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Ends this session; the same token is refused afterwards. Other devices stay logged in."""
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user)):
    return MeOut(userId=user.user_id, name=user.name, role=user.role,
                 menu=ROLE_MENUS.get(user.role, []))
