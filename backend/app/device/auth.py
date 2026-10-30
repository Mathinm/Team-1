"""Device key authentication (FR-17, SAD 3.9): header  X-Device-Key: <key>.

Each POS / sensor has its own key. Only the SHA-256 of a key is stored, and keys are never
logged. A POS key can only send sales; a sensor key can only send readings.
"""

import hashlib
import logging
import secrets

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Device

log = logging.getLogger("pms.device")
KINDS = ("pos", "sensor")


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_device(db: Session, name: str, kind: str) -> str:
    """Register a device and return its key. The key cannot be recovered later."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    key = secrets.token_urlsafe(32)
    db.add(Device(store_id=get_settings().store_id, name=name, kind=kind, key_hash=hash_key(key)))
    db.commit()
    return key


def _authenticate(x_device_key: str | None, db: Session) -> Device:
    device = None
    if x_device_key:
        device = db.scalar(
            select(Device).where(Device.key_hash == hash_key(x_device_key), Device.active.is_(True))
        )
    if device is None:
        log.warning("Device API: rejected request with a missing or invalid device key")
        raise ApiError(401, "INVALID_DEVICE_KEY", "Invalid or missing device key")
    return device


def device_of_kind(kind: str):
    """Dependency factory: authenticate the key, then require the right kind of device."""

    def dep(
        x_device_key: str | None = Header(default=None), db: Session = Depends(get_db)
    ) -> Device:
        device = _authenticate(x_device_key, db)
        if device.kind != kind:
            log.warning("Device API: %s device '%s' tried to use a %s endpoint", device.kind,
                        device.name, kind)
            raise ApiError(403, "FORBIDDEN", f"This device is not allowed to send {kind} data")
        return device

    return dep
