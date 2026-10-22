"""Login sessions and role checks for user-facing endpoints (SEC-1, SEC-2).

A token is an HS256 JWT signed with JWT_SECRET with the claims sub = userId, role, name,
sid = session id and exp = expiry. Every request also checks the session row in the
database, so logout and deactivation end a token at once. Endpoints just call
require_roles(...) or get_current_user.
"""

import logging
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import User, UserSession

log = logging.getLogger("pms.security")

ADMIN, MANAGER, STAFF, CASHIER = "Admin", "Manager", "Inventory Staff", "Cashier"
SESSION_ENDED = "Your session has ended. Please log in again."


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    role: str
    name: str


def create_access_token(
    user_id: str, role: str, name: str = "", expires_in: int = 3600, sid: str = ""
) -> str:
    """Sign a token. Login passes the session id; a token without a live session is refused."""
    now = int(time.time())
    claims = {"sub": user_id, "role": role, "name": name, "sid": sid,
              "iat": now, "exp": now + expires_in}
    return jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")


def get_current_session(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> UserSession:
    """401 unless the token is valid AND its session is still open AND the user is active."""
    secret = get_settings().jwt_secret
    scheme, _, token = (authorization or "").partition(" ")
    if not secret or scheme.lower() != "bearer" or not token:
        raise ApiError(401, "UNAUTHORIZED", SESSION_ENDED)
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"], options={"require": ["sub", "exp", "sid"]}
        )
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", SESSION_ENDED) from None

    session = db.scalar(select(UserSession).where(UserSession.sid == claims["sid"]))
    user = db.get(User, session.user_pk) if session else None
    if (session is None or session.ended_at is not None or user is None or not user.active
            or user.user_id != claims["sub"]):
        raise ApiError(401, "UNAUTHORIZED", SESSION_ENDED)
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session), db: Session = Depends(get_db)
) -> CurrentUser:
    # Role and name come from the database, so a role change applies on the next request.
    user = db.get(User, session.user_pk)
    return CurrentUser(user_id=user.user_id, role=user.role, name=user.name)


def require_roles(*roles: str):
    """Dependency: 401 without a valid session, 403 (logged) for the wrong role."""

    def check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            log.warning("access denied: user=%s role=%s, needs %s", user.user_id, user.role, roles)
            raise ApiError(403, "FORBIDDEN", "You don't have permission to do that.")
        return user

    return check
