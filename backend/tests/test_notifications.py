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
    """An authenticated user can access the notifications endpoint with clean camelCase fields."""
    response = client.get(
        "/api/notifications",
        headers=auth("notification-reader", "Inventory Staff"),
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "notificationId" in item
        assert "notification_id" not in item
        assert "createdAt" in item
        assert "created_at" not in item


def test_expiry_notification_ignores_zero_quantity_batch(client, seeded, db):
    """Batches with 0 quantity must not generate expiry notifications."""
    batch = db.get(Batch, 101)
    assert batch is not None
    batch.quantity = 0
    batch.expiry_date = store_today()
    db.commit()

    created = create_expiry_notifications(db, today=store_today())
    assert created == 0
    notification = db.scalar(
        select(Notification).where(
            Notification.batch_id == 101,
            Notification.notification_type == "expiry",
        )
    )
    assert notification is None


def test_multiple_removals_same_batch_create_separate_notifications(client, seeded, db):
    """Multiple removals on the same batch must succeed and record notifications."""
    r1 = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 1, "reason": "damaged"},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 1, "reason": "spilled"},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert r2.status_code == 201

    notifications = db.scalars(
        select(Notification)
        .where(
            Notification.batch_id == 101,
            Notification.notification_type == "removal",
        )
        .order_by(Notification.notification_id.asc())
    ).all()

    assert len(notifications) == 2
    assert notifications[0].removal_id == r1.json()["removalId"]
    assert notifications[1].removal_id == r2.json()["removalId"]


def test_removals_appear_in_alerts_with_correct_unit(client, seeded, db):
    """NFR-12: stock removals appear in /api/alerts and messages use the product unit (e.g. kg)."""
    r = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 2, "reason": "damaged"},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert r.status_code == 201

    # Check the notification message uses 'kg' instead of 'units'
    notif = db.scalar(
        select(Notification).where(
            Notification.removal_id == r.json()["removalId"]
        )
    )
    assert notif is not None
    assert "2 kg" in notif.message
    assert "units" not in notif.message

    # Check /api/alerts shows the removal alert
    alerts_res = client.get("/api/alerts", headers=auth("alert-reader", "Manager"))
    assert alerts_res.status_code == 200
    alert_items = alerts_res.json()
    removal_alerts = [a for a in alert_items if a["type"] == "STOCK_REMOVAL"]
    assert len(removal_alerts) >= 1
    assert "2 kg" in removal_alerts[0]["message"]
    assert removal_alerts[0]["deliveryStatus"] == "pending"


def test_expiry_notifications_appear_in_alerts(client, seeded, db):
    """Expiry checks raise alerts visible in /api/alerts."""
    batch = db.get(Batch, 101)
    assert batch is not None
    batch.expiry_date = store_today()
    db.commit()

    create_expiry_notifications(db, today=store_today())

    alerts_res = client.get("/api/alerts", headers=auth("alert-reader", "Manager"))
    assert alerts_res.status_code == 200
    expiry_alerts = [a for a in alerts_res.json() if a["type"] == "EXPIRY"]
    assert len(expiry_alerts) >= 1
    assert "Tomato" in expiry_alerts[0]["message"]
