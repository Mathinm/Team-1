"""Password reset by email (SEC-5, UC-04, TC-AUTH-05; Test Case Document TC-AUTH-13 and -14).

1. POST /api/auth/password-reset {userId}
   Emails a one-time link to the user's registered email. The answer is always the same 202,
   whether the user ID exists or not, so nobody can use this page to find valid user IDs.
2. The user opens the link: {FRONTEND_URL}/reset-password?token=...
3. POST /api/auth/password-reset/confirm {token, newPassword}
   Sets the new password. The link works once and expires after PASSWORD_RESET_EXPIRE_MINUTES
   (default 30). Used, expired or unknown links answer 400 RESET_LINK_INVALID.

Only a SHA-256 hash of the token is stored, so a database copy cannot be used to reset anyone's
password. A successful reset ends all the user's sessions (a stolen login is thrown out). A
locked account stays locked: SEC-3 says only an Admin unlocks it.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import PasswordReset, User, UserSession
from app.notify import send_email

router = APIRouter(prefix="/api/auth/password-reset", tags=["auth"])
audit = logging.getLogger("pms.audit")

SENT = "If that user ID exists, a reset link has been sent to its registered email."
LINK_INVALID = "This reset link is invalid, already used or expired. Ask for a new one."


class ResetRequestIn(BaseModel):
    userId: str = Field(min_length=1, max_length=50)


class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    newPassword: str = Field(min_length=8, max_length=128)  # same rule as a new user (SEC-4)


class MessageOut(BaseModel):
    message: str


def _aware(dt: datetime) -> datetime:
    """Times are stored in UTC; SQLite (tests) hands them back without a timezone."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _cancel_open_links(db: Session, user: User, now: datetime) -> None:
    """Only the newest link works: older unused ones are marked used."""
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_pk == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )


@router.post("", status_code=202, response_model=MessageOut)
def request_reset(body: ResetRequestIn, db: Session = Depends(get_db)):
    s = get_settings()
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.user_id == body.userId.strip()))
    if user is None or not user.active:
        audit.info("PASSWORD_RESET_REQUESTED user=%s result=no-such-active-user", body.userId)
        return MessageOut(message=SENT)  # same answer: don't reveal which user IDs exist

    last = db.scalar(
        select(PasswordReset.created_at)
        .where(PasswordReset.user_pk == user.id)
        .order_by(PasswordReset.id.desc())
        .limit(1)
    )
    if last and now - _aware(last) < timedelta(seconds=s.password_reset_resend_seconds):
        # A link was sent a moment ago: don't flood the inbox; that link still works.
        audit.info("PASSWORD_RESET_REQUESTED user=%s result=too-soon", user.user_id)
        return MessageOut(message=SENT)

    token = secrets.token_urlsafe(32)
    _cancel_open_links(db, user, now)
    db.add(PasswordReset(user_pk=user.id, token_hash=_hash(token), created_at=now,
                         expires_at=now + timedelta(minutes=s.password_reset_expire_minutes)))
    db.commit()

    link = f"{s.frontend_url.rstrip('/')}/reset-password?token={token}"
    send_email(
        user.email,
        "Reset your PMS password",
        f"Hello {user.name},\n\n"
        f"Someone (hopefully you) asked to reset the password for PMS user ID {user.user_id}.\n"
        f"Open this link to choose a new password:\n\n{link}\n\n"
        f"The link works once and expires in {s.password_reset_expire_minutes} minutes. If you "
        f"did not ask for this, ignore this email; your password stays the same.\n",
    )
    audit.info("PASSWORD_RESET_REQUESTED user=%s result=emailed", user.user_id)  # never the link
    return MessageOut(message=SENT)


@router.post("/confirm", response_model=MessageOut)
def confirm_reset(body: ResetConfirmIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _hash(body.token)))
    if reset is None or reset.used_at is not None or now > _aware(reset.expires_at):
        audit.info("PASSWORD_RESET_FAILED reason=link-invalid")
        raise ApiError(400, "RESET_LINK_INVALID", LINK_INVALID)
    user = db.get(User, reset.user_pk)
    if user is None or not user.active:
        reset.used_at = now
        db.commit()
        raise ApiError(400, "RESET_LINK_INVALID", LINK_INVALID)

    user.password_hash = hash_password(body.newPassword)
    user.failed_logins = 0
    reset.used_at = now
    _cancel_open_links(db, user, now)
    db.execute(  # log out everywhere: whoever knew the old password is thrown out
        update(UserSession)
        .where(UserSession.user_pk == user.id, UserSession.ended_at.is_(None))
        .values(ended_at=now)
    )
    db.commit()
    audit.info("PASSWORD_RESET_DONE user=%s", user.user_id)
    return MessageOut(message="Your password has been changed. Log in with the new password.")
