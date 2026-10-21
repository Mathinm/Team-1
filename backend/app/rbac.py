"""Role checks for user-facing endpoints (SEC-2).

INTEGRATION WITH #3 (auth): login must return an HS256 JWT signed with JWT_SECRET and the
claims  sub = userId,  role = "Admin" | "Manager" | "Inventory Staff" | "Cashier",
name = display name,  exp = expiry. If #3 issues tokens differently, change only
get_current_user() below; the endpoints just call require_roles(...).
"""

import logging
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header

from app.config import get_settings
from app.errors import ApiError

log = logging.getLogger("pms.security")

ADMIN, MANAGER, STAFF, CASHIER = "Admin", "Manager", "Inventory Staff", "Cashier"
SESSION_ENDED = "Your session has ended. Please log in again."


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    role: str
    name: str


def create_access_token(user_id: str, role: str, name: str = "", expires_in: int = 3600) -> str:
    """Mint a token in the format get_current_user() accepts (used by tests and tools)."""
    now = int(time.time())
    claims = {"sub": user_id, "role": role, "name": name, "iat": now, "exp": now + expires_in}
    return jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    secret = get_settings().jwt_secret
    scheme, _, token = (authorization or "").partition(" ")
    if not secret or scheme.lower() != "bearer" or not token:
        raise ApiError(401, "UNAUTHORIZED", SESSION_ENDED)
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"], options={"require": ["sub", "exp"]}
        )
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", SESSION_ENDED) from None
    return CurrentUser(user_id=str(claims["sub"]), role=str(claims.get("role", "")),
                       name=str(claims.get("name", "")))


def require_roles(*roles: str):
    """Dependency: 401 without a valid session, 403 (logged) for the wrong role."""

    def check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            log.warning("access denied: user=%s role=%s, needs %s", user.user_id, user.role, roles)
            raise ApiError(403, "FORBIDDEN", "You don't have permission to do that.")
        return user

    return check
