"""Two-factor login for Manager and Admin by emailed code (NFR-10, TC-SEC-07).

1. Manager/Admin sends user ID + password. If they are right, a random 6-digit code is emailed
   to the user's address and the login answers 401 OTP_REQUIRED (the login page then shows the
   code box).
2. The user sends user ID + password + otpCode. The right code within OTP_EXPIRE_MINUTES
   (default 10) logs in; it works once only.

Only a keyed hash of the code is stored. A wrong code counts like a wrong password (SEC-3), so
five wrong codes lock the account and the code cannot be guessed by trial. Asking again within
OTP_RESEND_SECONDS (default 30) does not send another email, so the login button cannot be used
to flood someone's inbox.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.models import User
from app.notify import send_email

log = logging.getLogger("pms.security")

TWO_FACTOR_ROLES = ("Manager", "Admin")
DIGITS = 6


def _aware(dt: datetime) -> datetime:
    """Times are stored in UTC; SQLite (tests) hands them back without a timezone."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def requires_otp(user: User) -> bool:
    return get_settings().require_2fa and user.role in TWO_FACTOR_ROLES


def _hash(user: User, code: str) -> str:
    """HMAC with the server secret, tied to the user, so a database leak alone gives nothing."""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"{user.id}:{code}".encode(), hashlib.sha256).hexdigest()


def mask_email(email: str) -> str:
    """m******@example.com: tells the user where to look without showing the whole address."""
    name, _, domain = email.partition("@")
    return f"{name[:1]}{'*' * max(len(name) - 1, 1)}@{domain}"


def send_code(user: User, now: datetime | None = None) -> bool:
    """Email a new code unless one was sent in the last OTP_RESEND_SECONDS. True if sent."""
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    if user.otp_sent_at and now - _aware(user.otp_sent_at) < timedelta(
            seconds=s.otp_resend_seconds):
        return False
    code = f"{secrets.randbelow(10**DIGITS):0{DIGITS}d}"
    user.otp_code_hash = _hash(user, code)
    user.otp_sent_at = now
    user.otp_expires_at = now + timedelta(minutes=s.otp_expire_minutes)
    send_email(
        user.email,
        "Your PMS login code",
        f"Hello {user.name},\n\n"
        f"Your login code is {code}\n\n"
        f"It expires in {s.otp_expire_minutes} minutes and works once. If you did not just try "
        f"to log in to PMS, someone knows your password: tell your Admin and change it.\n",
    )
    log.info("2FA code emailed: user=%s", user.user_id)  # never log the code
    return True


def verify_code(user: User, code: str | None, now: datetime | None = None) -> bool:
    """True if `code` is the last code emailed to this user and has not expired. Single use."""
    now = now or datetime.now(timezone.utc)
    if not code or not user.otp_code_hash or not user.otp_expires_at:
        return False
    code = code.replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return False
    if now > _aware(user.otp_expires_at):
        return False
    if not hmac.compare_digest(_hash(user, code), user.otp_code_hash):
        return False
    clear_code(user)
    return True


def clear_code(user: User) -> None:
    user.otp_code_hash = None
    user.otp_expires_at = None
    user.otp_sent_at = None
