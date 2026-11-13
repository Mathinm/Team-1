from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Notification
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, require_roles

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
viewers = require_roles(ADMIN, MANAGER, STAFF)


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@router.get("")
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(viewers),
):
    """Return the newest notifications for the configured store."""
    store_id = get_settings().store_id

    notifications = db.scalars(
        select(Notification)
        .where(Notification.store_id == store_id)
        .order_by(
            Notification.created_at.desc(),
            Notification.notification_id.desc(),
        )
        .limit(limit)
    ).all()

    return [
        {
            "notificationId": item.notification_id,
            "storeId": item.store_id,
            "batchId": item.batch_id,
            "removalId": item.removal_id,
            "notificationType": item.notification_type,
            "title": item.title,
            "message": item.message,
            "createdAt": _timestamp(item.created_at),
        }
        for item in notifications
    ]
