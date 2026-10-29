"""Refrigeration monitoring (FR-15, FR-16, FR-17; SAD flow 3, use cases UC-31, UC-32, UC-34).

Every stored sensor reading updates the state of its unit and may raise or close alerts:

  power OFF            unit status FAILED + critical UNIT_FAILURE alert ("Fridge-2 failed")
  power ON             status OK again; the alert is closed and logged (TC-REF-02)
  door OPEN too long   DOOR_OPEN alarm once the door has been open for the unit's limit (FR-16)
  door CLOSED          closes the alarm
  temperature outside  TEMPERATURE alert while the latest reading is outside the safe range
  the safe range       (default 0-8 deg C), closed when a reading is back inside

Offline sync (FR-19, NFR-5): all time maths uses the reading's own recorded_at, never the time
it arrived. Readings replayed after an outage therefore give the same alerts as if they had
arrived live (a door open for 1 min raises nothing, one open for 10 min raises and closes an
alarm), and a late older reading never overwrites newer state.

The scheduler also calls check_open_doors() so a door left open still raises its alarm when the
sensor sends nothing more.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alerts.service import (
    DOOR_OPEN,
    TEMPERATURE,
    UNIT_FAILURE,
    as_utc,
    now_utc,
    raise_alert,
    resolve_alert,
)
from app.config import get_settings
from app.models import Alert, RefrigerationUnit, SensorReading

log = logging.getLogger("pms.refrigeration")


def effective_limits(unit: RefrigerationUnit) -> tuple[int, float, float]:
    """(door limit in minutes, min deg C, max deg C): the unit's own setting or the default."""
    s = get_settings()
    door = unit.door_open_limit_minutes or s.door_open_limit_minutes
    lo = s.unit_temp_min_c if unit.temp_min is None else unit.temp_min
    hi = s.unit_temp_max_c if unit.temp_max is None else unit.temp_max
    return door, lo, hi


def get_or_create_unit(db: Session, unit_id: str) -> RefrigerationUnit:
    """The unit row, locked for update (two readings of one fridge are applied one at a time)."""
    store_id = get_settings().store_id

    def find() -> RefrigerationUnit | None:
        return db.scalar(
            select(RefrigerationUnit)
            .where(RefrigerationUnit.store_id == store_id, RefrigerationUnit.unit_id == unit_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    unit = find()
    if unit is None:
        try:
            with db.begin_nested():
                db.add(RefrigerationUnit(store_id=store_id, unit_id=unit_id, status="OK"))
                db.flush()
        except IntegrityError:  # another reading created it first
            pass
        unit = find()
    return unit


def _newer(stamp: datetime | None, t: datetime) -> bool:
    return stamp is None or t >= as_utc(stamp)


# ------------------------------------------------------------------ door
def _check_door(db: Session, unit: RefrigerationUnit, as_of: datetime) -> list[Alert]:
    """Raise the door alarm if the door has been open for the limit as of `as_of`."""
    if unit.door != "OPEN" or unit.door_open_since is None:
        return []
    limit, _, _ = effective_limits(unit)
    since = as_utc(unit.door_open_since)
    open_for = as_of - since
    if open_for < timedelta(minutes=limit):
        return []
    minutes = int(open_for.total_seconds() // 60)
    alert = raise_alert(
        db, type=DOOR_OPEN, key=f"door_open:{unit.unit_id}", severity="warning",
        message=f"{unit.unit_id} door has been open for {minutes} min (limit {limit} min)",
        unit_id=unit.unit_id, triggered_at=since + timedelta(minutes=limit),
    )
    return [alert] if alert else []


def check_open_doors(db: Session, now: datetime | None = None) -> int:
    """Scheduler job: alarm for every door that is still open past its limit. Returns count."""
    now = now or now_utc()
    units = db.scalars(
        select(RefrigerationUnit).where(
            RefrigerationUnit.store_id == get_settings().store_id,
            RefrigerationUnit.door == "OPEN",
        )
    ).all()
    return sum(len(_check_door(db, u, now)) for u in units)


# ------------------------------------------------------------------ readings
def apply_reading(
    db: Session, reading: SensorReading, now: datetime | None = None
) -> list[Alert]:
    """Update the unit from one stored reading. Returns the alerts this reading raised.

    Runs in the caller's transaction; the caller commits.
    """
    now = now or now_utc()
    t = as_utc(reading.recorded_at)
    unit = get_or_create_unit(db, reading.unit_id)
    unit.last_received_at = now
    if _newer(unit.last_event_at, t):
        unit.last_event_at = t
    raised: list[Alert] = []

    if reading.type == "temperature" and _newer(unit.temperature_at, t):
        unit.temperature, unit.temperature_at = reading.value_num, t
        _, lo, hi = effective_limits(unit)
        key = f"temperature:{unit.unit_id}"
        if reading.value_num > hi or reading.value_num < lo:
            alert = raise_alert(
                db, type=TEMPERATURE, key=key, severity="critical", unit_id=unit.unit_id,
                message=(f"{unit.unit_id} temperature {reading.value_num:g} °C is outside "
                         f"{lo:g} to {hi:g} °C"),
                triggered_at=t,
            )
            raised += [alert] if alert else []
        else:
            resolve_alert(db, key, f"Temperature back to {reading.value_num:g} °C", resolved_at=t)

    elif reading.type == "power" and _newer(unit.power_at, t):
        unit.power, unit.power_at = reading.value_text, t
        key = f"unit_failure:{unit.unit_id}"
        if reading.value_text == "OFF":
            unit.status = "FAILED"
            alert = raise_alert(
                db, type=UNIT_FAILURE, key=key, severity="critical", unit_id=unit.unit_id,
                message=f"{unit.unit_id} failed: power lost", triggered_at=t,
            )
            raised += [alert] if alert else []
        else:
            unit.status = "OK"
            resolve_alert(db, key, "Power restored: unit is working again", resolved_at=t)

    elif reading.type == "door" and _newer(unit.door_at, t):
        if reading.value_text == "OPEN":
            if unit.door != "OPEN" or unit.door_open_since is None:
                unit.door_open_since = t
            unit.door, unit.door_at = "OPEN", t
        else:
            # A door that was open past its limit and is only now reported closed still
            # deserves its alarm (raised, then closed straight away so the history shows it).
            raised += _check_door(db, unit, t)
            unit.door, unit.door_at, unit.door_open_since = "CLOSED", t, None
            resolve_alert(db, f"door_open:{unit.unit_id}", "Door closed", resolved_at=t)

    raised += _check_door(db, unit, as_utc(unit.last_event_at))
    return raised
