"""Refrigeration screen data (UC-34) and per-unit settings (FR-16 "configured threshold")."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts.service import as_utc
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Alert, RefrigerationUnit, SensorReading
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, require_roles
from app.refrigeration.schemas import ReadingPoint, UnitOut, UnitSettingsIn
from app.refrigeration.service import effective_limits

router = APIRouter(prefix="/api/refrigeration", tags=["refrigeration"])
viewers = require_roles(ADMIN, MANAGER, STAFF)
managers = require_roles(ADMIN, MANAGER)


def _open_alert_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Alert.unit_id, func.count())
        .where(Alert.store_id == get_settings().store_id, Alert.unit_id.is_not(None),
               Alert.status.in_(("active", "acknowledged")))
        .group_by(Alert.unit_id)
    ).all()
    return {unit_id: n for unit_id, n in rows}


def _out(unit: RefrigerationUnit, open_alerts: int) -> UnitOut:
    door_limit, lo, hi = effective_limits(unit)
    return UnitOut(
        unitId=unit.unit_id, status=unit.status, power=unit.power, door=unit.door,
        doorOpenSince=as_utc(unit.door_open_since), temperature=unit.temperature,
        temperatureAt=as_utc(unit.temperature_at), lastReadingAt=as_utc(unit.last_event_at),
        lastReceivedAt=as_utc(unit.last_received_at), doorOpenLimitMinutes=door_limit,
        tempMin=lo, tempMax=hi, openAlerts=open_alerts,
    )


@router.get("/units", response_model=list[UnitOut])
def list_units(_user: CurrentUser = Depends(viewers), db: Session = Depends(get_db)):
    """Working status, latest temperature, door and power of every fridge that has reported."""
    counts = _open_alert_counts(db)
    units = db.scalars(
        select(RefrigerationUnit)
        .where(RefrigerationUnit.store_id == get_settings().store_id)
        .order_by(RefrigerationUnit.unit_id)
    )
    return [_out(u, counts.get(u.unit_id, 0)) for u in units]


@router.put("/units/{unit_id}", response_model=UnitOut)
def update_unit_settings(
    unit_id: str,
    body: UnitSettingsIn,
    _user: CurrentUser = Depends(managers),
    db: Session = Depends(get_db),
):
    """Set how long the door may stay open and the safe temperature range for one fridge."""
    unit = db.scalar(
        select(RefrigerationUnit).where(
            RefrigerationUnit.store_id == get_settings().store_id,
            RefrigerationUnit.unit_id == unit_id,
        )
    )
    if unit is None:
        raise ApiError(404, "NOT_FOUND", f"Unknown refrigeration unit {unit_id}")
    sent = body.model_fields_set
    if "doorOpenLimitMinutes" in sent:
        unit.door_open_limit_minutes = body.doorOpenLimitMinutes
    if "tempMin" in sent:
        unit.temp_min = body.tempMin
    if "tempMax" in sent:
        unit.temp_max = body.tempMax
    _, lo, hi = effective_limits(unit)
    if lo >= hi:
        db.rollback()
        raise ApiError(400, "INVALID", "Minimum temperature must be below maximum")
    db.commit()
    return _out(unit, _open_alert_counts(db).get(unit.unit_id, 0))


@router.get("/units/{unit_id}/readings", response_model=list[ReadingPoint])
def unit_readings(
    unit_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    _user: CurrentUser = Depends(viewers),
    db: Session = Depends(get_db),
):
    """Temperature history for the Refrigeration screen chart (UI-4), oldest first.

    Uses each reading's own recorded_at, so readings that arrived late after an outage are
    shown at the time they were taken.
    """
    store_id = get_settings().store_id
    known = db.scalar(
        select(RefrigerationUnit.id).where(
            RefrigerationUnit.store_id == store_id, RefrigerationUnit.unit_id == unit_id
        )
    )
    if known is None:
        raise ApiError(404, "NOT_FOUND", f"Unknown refrigeration unit {unit_id}")
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute(
        select(SensorReading.recorded_at, SensorReading.value_num)
        .where(
            SensorReading.store_id == store_id,
            SensorReading.unit_id == unit_id,
            SensorReading.type == "temperature",
            SensorReading.recorded_at >= since,
        )
        .order_by(SensorReading.recorded_at, SensorReading.reading_id)
    ).all()
    return [ReadingPoint(recordedAt=as_utc(at), value=value) for at, value in rows]
