from datetime import datetime

from pydantic import BaseModel

from app.alerts.service import as_utc
from app.models import Alert


class AlertOut(BaseModel):
    alertId: int
    type: str
    severity: str
    message: str
    productId: int | None
    unitId: str | None
    status: str  # active | acknowledged | resolved
    triggeredAt: datetime
    createdAt: datetime
    acknowledgedBy: str | None
    acknowledgedAt: datetime | None
    resolvedAt: datetime | None
    resolution: str | None
    deliveryStatus: str  # pending | sent | failed | skipped
    deliveredAt: datetime | None


class RunCheckOut(BaseModel):
    raised: int
    resolved: int


def alert_out(a: Alert) -> AlertOut:
    return AlertOut(
        alertId=a.alert_id, type=a.type, severity=a.severity, message=a.message,
        productId=a.product_id, unitId=a.unit_id, status=a.status,
        triggeredAt=as_utc(a.triggered_at), createdAt=as_utc(a.created_at),
        acknowledgedBy=a.acknowledged_by, acknowledgedAt=as_utc(a.acknowledged_at),
        resolvedAt=as_utc(a.resolved_at), resolution=a.resolution,
        deliveryStatus=a.delivery_status, deliveredAt=as_utc(a.delivered_at),
    )
