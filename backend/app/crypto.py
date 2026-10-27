"""Employee data encrypted at rest (NFR-11, TC-SEC-08).

Employee names and emails are stored encrypted in the users table. EncryptedString is a column
type that encrypts on write and decrypts on read, so the rest of the code (login, emails, user
admin) keeps working with plain text, while the database, its backups and anyone reading the
tables directly see only ciphertext such as "enc:v1:gAAAAAB...".

Cipher: Fernet from the `cryptography` package (AES-128-CBC + HMAC-SHA256, a random IV per value),
so the same email stored twice gives two different ciphertexts.

Key: DATA_ENCRYPTION_KEY, a Fernet key (make one with `python -m app.crypto`). For key rotation
it may hold several keys separated by commas: the first encrypts new values, all of them decrypt.
If it is empty, a key is derived from JWT_SECRET so local work needs no extra setting; set a
real key everywhere else, and keep it out of the database and its backups.

Values written before NFR-11 (plain text, no "enc:v1:" prefix) are still read as they are, and
each is encrypted when it is next changed. To encrypt everything at once, reset the database
(the tables are recreated at startup with these columns).
"""

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.config import get_settings

log = logging.getLogger("pms.security")

PREFIX = "enc:v1:"


class DecryptionError(RuntimeError):
    """The value was encrypted with a key we don't have (wrong or missing DATA_ENCRYPTION_KEY)."""


@lru_cache
def _fernet() -> MultiFernet:
    s = get_settings()
    keys = [k.strip() for k in s.data_encryption_key.split(",") if k.strip()]
    if not keys:
        # Local work only: derived from JWT_SECRET, so it changes if JWT_SECRET changes.
        digest = hashlib.sha256(f"pms-nfr-11:{s.jwt_secret}".encode()).digest()
        keys = [base64.urlsafe_b64encode(digest).decode()]
        log.warning("DATA_ENCRYPTION_KEY is empty: using a key derived from JWT_SECRET "
                    "(local development only)")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def reset_key_cache() -> None:
    """Re-read DATA_ENCRYPTION_KEY (tests change it)."""
    _fernet.cache_clear()


def encrypt(value: str) -> str:
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(stored: str) -> str:
    if not stored.startswith(PREFIX):
        return stored  # written before NFR-11; encrypted when next changed
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("Cannot decrypt employee data: wrong DATA_ENCRYPTION_KEY?") from exc


class EncryptedString(TypeDecorator):
    """A text column stored encrypted. Not searchable or sortable in SQL: filter in Python."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value)


if __name__ == "__main__":  # python -m app.crypto  -> prints a new key for DATA_ENCRYPTION_KEY
    print(Fernet.generate_key().decode())
