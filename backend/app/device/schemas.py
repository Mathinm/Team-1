from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.errors import ApiError

READING_TYPES = ("temperature", "door", "power")
DOOR_VALUES = ("OPEN", "CLOSED")
POWER_VALUES = ("ON", "OFF")
TEMP_RANGE = (-60.0, 100.0)  # deg C; outside this the sensor is faulty or the value is junk


class DeviceSaleIn(BaseModel):
    eventId: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=40)
    quantity: Decimal
    unit: str | None = Field(default=None, max_length=10)
    soldAt: datetime | None = None


class ReadingIn(BaseModel):
    eventId: str = Field(min_length=1, max_length=64)
    unitId: str = Field(min_length=1, max_length=64)
    type: str
    value: str | int | float
    recordedAt: datetime


class ReadingOut(BaseModel):
    status: str = "stored"
    alertRaised: bool = False


def parse_reading_value(kind: str, value) -> tuple[float | None, str | None]:
    """Return (value_num, value_text) or raise 400 so a malformed reading is never stored."""
    if kind not in READING_TYPES:
        raise ApiError(400, "INVALID", f"type must be one of: {', '.join(READING_TYPES)}")
    if kind == "temperature":
        try:
            num = float(value)
        except (TypeError, ValueError):
            msg = f"Temperature must be a number (got '{value}')"
            raise ApiError(400, "INVALID", msg) from None
        if num != num or not (TEMP_RANGE[0] <= num <= TEMP_RANGE[1]):
            raise ApiError(400, "INVALID", f"Temperature must be between {TEMP_RANGE[0]:g} and "
                           f"{TEMP_RANGE[1]:g} °C (got '{value}')")
        return num, None
    allowed = DOOR_VALUES if kind == "door" else POWER_VALUES
    text = str(value).strip().upper()
    if text not in allowed:
        msg = f"A {kind} reading must be {' or '.join(allowed)} (got '{value}')"
        raise ApiError(400, "INVALID", msg)
    return None, text
