from datetime import timedelta

from sqlalchemy import select

from app.models import Batch, Notification
from app.notifications.service import create_expiry_notifications
from app.sales.fefo import store_today
from tests.conftest import auth


def test_pre_expiry_notification_created(client, seeded, db):
    """A batch expiring tomorrow receives one pre-expiry notification."""
    batch = db.get(Batch, 101)
    assert batch is not None
    batch.expiry_date = store_today() + timedelta(days=1)
    db.commit()

    created = create_expiry_notifications(db, today=store_today())

    assert created >= 1
    notification = db.scalar(
        select(Notification).where(
            Notification.batch_id == 101,
            Notification.notification_type == "pre_expiry",
        )
    )
    assert notification is not None
    assert "tomorrow" in notification.title.lower()


def test_expiry_notification_created_on_expiry_date(client, seeded, db):
    """A batch expiring today receives an expiry notification."""
    batch = db.get(Batch, 101)
    assert batch is not None
    batch.expiry_date = store_today()
    db.commit()

    create_expiry_notifications(db, today=store_today())

    notification = db.scalar(
        select(Notification).where(
            Notification.batch_id == 101,
            Notification.notification_type == "expiry",
        )
    )
    assert notification is not None
    assert "today" in notification.title.lower()


def test_expiry_notifications_are_not_duplicated(client, seeded, db):
    """Repeated scheduler passes must not duplicate expiry notifications."""
    batch = db.get(Batch, 101)
    assert batch is not None
    batch.expiry_date = store_today() + timedelta(days=1)
    db.commit()

    first_created = create_expiry_notifications(db, today=store_today())
    second_created = create_expiry_notifications(db, today=store_today())

    assert first_created >= 1
    assert second_created == 0

    matches = db.scalars(
        select(Notification).where(
            Notification.batch_id == 101,
            Notification.notification_type == "pre_expiry",
        )
    ).all()
    assert len(matches) == 1


def test_notifications_endpoint_requires_authentication(client):
    """Anonymous requests must not read notifications."""
    response = client.get("/api/notifications")
    assert response.status_code == 401


def test_authenticated_user_can_list_notifications(client, seeded):
    """An authenticated user can access the notifications endpoint."""
    response = client.get(
        "/api/notifications",
        headers=auth("notification-reader", "Inventory Staff"),
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
