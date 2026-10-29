"""Device API (FR-17, FR-19, ADR-5): the only entry for POS and sensor data.

Every event carries an eventId. A resend (offline sync) of an event that is already stored
answers 409 and changes nothing, so retries never double-count a sale or a reading.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alerts.service import guarded
from app.config import get_settings
from app.db import get_db
from app.device.auth import device_of_kind
from app.device.schemas import DeviceSaleIn, ReadingIn, ReadingOut, parse_reading_value
from app.errors import ApiError
from app.models import Device, Sale, SensorReading
from app.refrigeration.service import apply_reading
from app.sales.fefo import record_sale, to_utc
from app.sales.schemas import SaleOut, sale_out

router = APIRouter(prefix="/api/device", tags=["device"])


def _duplicate(event_id: str) -> ApiError:
    return ApiError(409, "DUPLICATE_EVENT", f"Event {event_id} was already received")


@router.post("/sales", status_code=201, response_model=SaleOut)
def device_sale(
    body: DeviceSaleIn,
    device: Device = Depends(device_of_kind("pos")),
    db: Session = Depends(get_db),
):
    """POS sale: same FEFO deduction and expired-batch blocking as a manual sale."""
    if db.scalar(select(Sale.sale_id).where(Sale.device_id == device.device_id,
                                            Sale.event_id == body.eventId)):
        raise _duplicate(body.eventId)
    try:
        result = record_sale(
            db,
            sku=body.sku,
            quantity=body.quantity,
            unit=body.unit,
            sold_at=body.soldAt,
            source="device",
            recorded_by=f"device:{device.name}",
            device_id=device.device_id,
            event_id=body.eventId,
        )
        db.commit()
    except IntegrityError:  # two copies of the same event arrived at once
        db.rollback()
        raise _duplicate(body.eventId) from None
    return sale_out(result)


@router.post("/readings", response_model=ReadingOut)
def device_reading(
    body: ReadingIn,
    device: Device = Depends(device_of_kind("sensor")),
    db: Session = Depends(get_db),
):
    """Temperature / door / power reading (FR-17). Stored, then checked for unit-failure,
    door-open and temperature alerts (FR-15, FR-16); `alertRaised` says if it raised any."""
    num, text = parse_reading_value(body.type, body.value)
    if db.scalar(select(SensorReading.reading_id).where(
            SensorReading.device_id == device.device_id, SensorReading.event_id == body.eventId)):
        raise _duplicate(body.eventId)
    reading_row = SensorReading(
        store_id=get_settings().store_id,
        device_id=device.device_id,
        event_id=body.eventId,
        unit_id=body.unitId.strip(),
        type=body.type,
        value_num=num,
        value_text=text,
        recorded_at=to_utc(body.recordedAt),
        received_at=datetime.now(timezone.utc),
    )
    db.add(reading_row)
    try:
        db.flush()  # a duplicate (device, eventId) fails here, before any alert is evaluated
        raised = guarded(db, apply_reading, reading_row) or []
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate(body.eventId) from None
    return ReadingOut(status="stored", alertRaised=bool(raised))
