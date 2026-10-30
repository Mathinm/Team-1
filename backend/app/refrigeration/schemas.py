from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UnitOut(BaseModel):
    unitId: str
    status: str  # OK | FAILED
    power: str | None
    door: str | None  # OPEN | CLOSED
    doorOpenSince: datetime | None
    temperature: float | None
    temperatureAt: datetime | None
    lastReadingAt: datetime | None  # time of the newest reading (the sensor's own clock)
    lastReceivedAt: datetime | None  # when PMS last heard from the sensor
    doorOpenLimitMinutes: int
    tempMin: float
    tempMax: float
    openAlerts: int  # alerts about this unit that are not resolved


class UnitSettingsIn(BaseModel):
    doorOpenLimitMinutes: int | None = Field(default=None, ge=1, le=240)
    tempMin: float | None = Field(default=None, ge=-60, le=100)
    tempMax: float | None = Field(default=None, ge=-60, le=100)

    @field_validator("tempMin", "tempMax")
    @classmethod
    def _finite(cls, v):
        if v is not None and v != v:
            raise ValueError("must be a number")
        return v
