"""Notification API for PMS Sprint 2, Issue #11."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Notification
from app.rbac import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
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
            "notification_id": item.notification_id,
            "store_id": item.store_id,
            "batch_id": item.batch_id,
            "removal_id": item.removal_id,
            "notification_type": item.notification_type,
            "title": item.title,
            "message": item.message,
            "created_at": item.created_at,
        }
        for item in notifications
    ]
