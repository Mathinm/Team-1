"""Account lockout and idle logout (SEC-3, TC-AUTH-03).

Lockout: every wrong password for an existing account adds 1 to users.failed_logins; a
correct password resets it to 0. When it reaches MAX_FAILED_LOGINS (default 5) the account is
locked and every login answers 423 "Account locked, contact Admin" until an Admin unlocks it.

Idle logout: user_sessions.last_seen_at is updated on each request. A session that has had no
request for IDLE_TIMEOUT_MINUTES (default 30) is ended and its token is refused (401).
"""

import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.errors import ApiError
from app.models import User, UserSession

log = logging.getLogger("pms.security")

ACCOUNT_LOCKED = "Account locked, contact Admin"
# Write last_seen_at at most this often, so busy screens don't update the row on every call.
_TOUCH_EVERY = timedelta(seconds=30)


def _aware(dt: datetime) -> datetime:
    """Times are stored in UTC; SQLite (tests) hands them back without a timezone."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def locked_error() -> ApiError:
    return ApiError(423, "ACCOUNT_LOCKED", ACCOUNT_LOCKED)


def is_locked(user: User) -> bool:
    return user.locked_at is not None


def record_failed_login(user: User, now: datetime | None = None) -> bool:
    """Count one wrong password. Returns True if this attempt locked the account."""
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins >= get_settings().max_failed_logins and not is_locked(user):
        user.locked_at = now or datetime.now(timezone.utc)
        log.warning("ACCOUNT_LOCKED user=%s after %s failed logins", user.user_id,
                    user.failed_logins)
        return True
    return False


def reset_failed_logins(user: User) -> None:
    user.failed_logins = 0


def unlock(user: User) -> None:
    user.failed_logins = 0
    user.locked_at = None


def session_is_idle(session: UserSession, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    limit = timedelta(minutes=get_settings().idle_timeout_minutes)
    return now - _aware(session.last_seen_at) > limit


def touch(session: UserSession, now: datetime | None = None) -> bool:
    """Mark the session as used now. Returns True if the row changed (caller commits)."""
    now = now or datetime.now(timezone.utc)
    if now - _aware(session.last_seen_at) >= _TOUCH_EVERY:
        session.last_seen_at = now
        return True
    return False
