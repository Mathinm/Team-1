"""Password hashing (NFR-9): argon2id with a random salt per password.

The salt and the settings are stored inside the hash string, so two users with the same
password still get different hashes. Passwords are never stored or logged in plain text.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2id, 16-byte random salt

# Checked when the user ID is unknown, so "unknown user" and "wrong password" take about
# the same time and an attacker cannot tell which user IDs exist (TC-AUTH-01).
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with weaker settings than today's (e.g. after an upgrade)."""
    return _hasher.check_needs_rehash(password_hash)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        ok = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and password_hash is not None
