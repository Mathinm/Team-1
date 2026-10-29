"""Alerts API (SAD 4.3): list alerts, acknowledge an alarm (UC-33), run the low-stock check."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.schemas import AlertOut, RunCheckOut, alert_out
from app.alerts.service import now_utc, run_low_stock_check
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Alert
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, require_roles

log = logging.getLogger("pms.alerts")
router = APIRouter(prefix="/api/alerts", tags=["alerts"])

viewers = require_roles(ADMIN, MANAGER, STAFF)
managers = require_roles(ADMIN, MANAGER)

STATUSES = ("active", "acknowledged", "resolved")


@router.get("", response_model=list[AlertOut])
def list_alerts(
    status: str | None = None,
    type: str | None = None,
    limit: int = 200,
    _user: CurrentUser = Depends(viewers),
    db: Session = Depends(get_db),
):
    """Newest first. status = active | acknowledged | resolved | open (active + acknowledged,
    i.e. the condition still exists) | all (default)."""
    if status not in (None, "all", "open", *STATUSES):
        raise ApiError(400, "INVALID", "status must be one of: active, acknowledged, "
                       "resolved, open, all")
    if not 1 <= limit <= 500:
        raise ApiError(400, "INVALID", "limit must be between 1 and 500")
    query = select(Alert).where(Alert.store_id == get_settings().store_id)
    if status == "open":
        query = query.where(Alert.status.in_(("active", "acknowledged")))
    elif status in STATUSES:
        query = query.where(Alert.status == status)
    if type:
        query = query.where(Alert.type == type)
    rows = db.scalars(query.order_by(Alert.triggered_at.desc(), Alert.alert_id.desc()).limit(limit))
    return [alert_out(a) for a in rows]


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(
    alert_id: int,
    user: CurrentUser = Depends(managers),
    db: Session = Depends(get_db),
):
    """UC-33: a Manager (or Admin) confirms they have seen the alarm. Safe to repeat."""
    alert = db.scalar(
        select(Alert)
        .where(Alert.alert_id == alert_id, Alert.store_id == get_settings().store_id)
        .with_for_update()
    )
    if alert is None:
        raise ApiError(404, "NOT_FOUND", "Alert not found")
    if alert.acknowledged_at is None:
        alert.acknowledged_by = user.user_id
        alert.acknowledged_at = now_utc()
        if alert.status == "active":
            alert.status = "acknowledged"  # a resolved alert stays resolved
        db.commit()
        log.info("ALERT_ACKNOWLEDGED id=%s by=%s", alert.alert_id, user.user_id)
    return alert_out(alert)


@router.post("/run-low-stock-check", response_model=RunCheckOut)
def run_check_now(_user: CurrentUser = Depends(managers), db: Session = Depends(get_db)):
    """Run the daily projected low-stock check now (it also runs by itself every day)."""
    result = run_low_stock_check(db)
    db.commit()
    return RunCheckOut(**result)
