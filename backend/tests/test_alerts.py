"""Low-stock and projected low-stock alerts, acknowledging, delivery (S2-4: FR-10, FR-11, NFR-2).

Maps to TC-LOW-01..05 of the test case document.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.alerts import notifier
from app.alerts.service import (
    LOW_STOCK_JOB,
    run_daily_low_stock_job,
    run_low_stock_check,
)
from app.models import Alert, Batch, JobRun, Product, Sale, Supplier
from app.sales.fefo import store_today
from tests.conftest import auth


def sell(client, sku="TOM-01", qty=1, who="cashier1"):
    return client.post("/api/sales", json={"sku": sku, "quantity": qty}, headers=auth(who))


def alerts(client, **params):
    r = client.get("/api/alerts", params=params, headers=auth("manager1", "Manager"))
    assert r.status_code == 200, r.text
    return r.json()


def of_type(rows, kind):
    return [a for a in rows if a["type"] == kind]


# ---------------------------------------------------------------- FR-11 low stock
def test_alert_when_sale_takes_stock_below_threshold(client, seeded):
    """TC-LOW-04: tomato threshold 10, stock 37 -> sell 29 -> 8 left -> immediate alert."""
    assert sell(client, qty=29).status_code == 201
    rows = of_type(alerts(client), "LOW_STOCK")
    assert len(rows) == 1
    a = rows[0]
    assert a["productId"] == 1 and a["status"] == "active" and a["severity"] == "warning"
    assert "Tomato is low: 8 kg left (threshold 10)" in a["message"]


def test_no_alert_when_stock_is_exactly_at_threshold(client, seeded):
    """TC-LOW-05: stock 10 is not below 10 -> no alert; one more unit -> alert."""
    sell(client, qty=27)  # 37 - 27 = 10
    assert of_type(alerts(client), "LOW_STOCK") == []
    sell(client, qty=1)  # 9
    assert len(of_type(alerts(client), "LOW_STOCK")) == 1


def test_no_duplicate_alert_while_stock_stays_low(client, seeded):
    sell(client, qty=29)
    sell(client, qty=1)
    sell(client, qty=1)
    assert len(of_type(alerts(client), "LOW_STOCK")) == 1


def test_acknowledged_alert_is_not_raised_again_until_stock_recovers(client, seeded):
    sell(client, qty=29)
    alert_id = alerts(client)[0]["alertId"]
    client.post(f"/api/alerts/{alert_id}/acknowledge", headers=auth("manager1", "Manager"))
    sell(client, qty=1)
    assert len(of_type(alerts(client), "LOW_STOCK")) == 1


def test_alert_closes_and_can_come_back_after_restock(client, seeded):
    sell(client, qty=29)
    r = client.post("/api/restocks", json={"productId": 1, "quantity": 20},
                    headers=auth("staff1", "Inventory Staff"))
    assert r.status_code == 201
    rows = alerts(client)
    assert rows[0]["status"] == "resolved" and rows[0]["resolvedAt"]
    assert "back to" in rows[0]["resolution"]
    assert alerts(client, status="open") == []
    sell(client, qty=20)  # 28 -> 8 again: a NEW alert (history keeps the old one)
    assert len(of_type(alerts(client), "LOW_STOCK")) == 2
    assert len(alerts(client, status="active")) == 1


def test_removal_and_stock_count_can_raise_low_stock(client, seeded):
    staff = auth("staff1", "Inventory Staff")
    # Banana: 60 pieces. Remove 55 -> 5 left.
    r = client.post("/api/removals", json={"batchId": 103, "qty": 55, "reason": "Damaged"},
                    headers=staff)
    assert r.status_code == 201
    assert len(of_type(alerts(client), "LOW_STOCK")) == 1
    # Tomato: count says only 3 kg are left in batch 101 and 25 in 102 -> 28, no alert; then 2.
    r = client.post("/api/stock-counts", json={"batchId": 102, "countedQuantity": 0,
                                               "reason": "spillage"}, headers=staff)
    assert r.status_code == 201
    r = client.post("/api/stock-counts", json={"batchId": 101, "countedQuantity": 3,
                                               "reason": "recount"}, headers=staff)
    assert r.status_code == 201
    names = [a["message"] for a in of_type(alerts(client), "LOW_STOCK")]
    assert any(m.startswith("Tomato") for m in names) and any(m.startswith("Banana") for m in names)


def test_editing_the_threshold_applies_at_once(client, seeded):
    """TC-MD-04: raise the tomato threshold from 10 to 40 while 37 kg are in stock."""
    body = {"sku": "TOM-01", "name": "Tomato", "category": "Test", "unit": "kg",
            "shelfLifeDays": 5, "storageType": "Chilled", "tempMin": 2, "tempMax": 8,
            "costPrice": 1, "sellingPrice": 30, "lowStockThreshold": 40}
    r = client.put("/api/products/1", json=body, headers=auth("manager1", "Manager"))
    assert r.status_code == 200
    rows = of_type(alerts(client), "LOW_STOCK")
    assert len(rows) == 1 and "threshold 40" in rows[0]["message"]
    body["lowStockThreshold"] = 10  # and back: the alert closes
    client.put("/api/products/1", json=body, headers=auth("manager1", "Manager"))
    assert alerts(client, status="open") == []


def test_deactivated_product_alert_is_closed(client, seeded):
    sell(client, qty=29)
    client.patch("/api/products/1/deactivate", headers=auth("manager1", "Manager"))
    assert alerts(client, status="open") == []


def test_failed_alert_check_never_blocks_a_sale(client, seeded, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("alert engine down")

    monkeypatch.setattr("app.alerts.service.refresh_stock_alerts", boom)
    r = sell(client, qty=29)
    assert r.status_code == 201 and r.json()["remainingStock"] == 8
    assert alerts(client) == []


# ---------------------------------------------------------------- access and acknowledging
def test_alert_access_rules(client, seeded):
    sell(client, qty=29)
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/alerts", headers=auth("cashier1")).status_code == 403
    assert client.get("/api/alerts", headers=auth("staff1", "Inventory Staff")).status_code == 200
    r = client.get("/api/alerts", params={"status": "nope"}, headers=auth("manager1", "Manager"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID"


def test_manager_acknowledges_alarm_and_it_is_audited(client, seeded):
    """UC-33."""
    sell(client, qty=29)
    alert_id = alerts(client)[0]["alertId"]
    # Staff can see alerts but only a Manager/Admin acknowledges.
    staff = auth("staff1", "Inventory Staff")
    r = client.post(f"/api/alerts/{alert_id}/acknowledge", headers=staff)
    assert r.status_code == 403
    r = client.post(f"/api/alerts/{alert_id}/acknowledge", headers=auth("manager1", "Manager"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "acknowledged" and body["acknowledgedBy"] == "manager1"
    assert body["acknowledgedAt"]
    assert [a["alertId"] for a in alerts(client, status="acknowledged")] == [alert_id]
    assert alerts(client, status="active") == []
    # repeating is harmless and keeps the first acknowledger
    r = client.post(f"/api/alerts/{alert_id}/acknowledge", headers=auth("admin1", "Admin"))
    assert r.status_code == 200 and r.json()["acknowledgedBy"] == "manager1"


def test_acknowledge_unknown_alert_is_404(client, seeded):
    r = client.post("/api/alerts/999/acknowledge", headers=auth("manager1", "Manager"))
    assert r.status_code == 404


def test_acknowledging_a_resolved_alert_keeps_it_resolved(client, seeded):
    sell(client, qty=29)
    alert_id = alerts(client)[0]["alertId"]
    client.post("/api/restocks", json={"productId": 1, "quantity": 20},
                headers=auth("staff1", "Inventory Staff"))
    r = client.post(f"/api/alerts/{alert_id}/acknowledge", headers=auth("manager1", "Manager"))
    assert r.json()["status"] == "resolved" and r.json()["acknowledgedBy"] == "manager1"


# ---------------------------------------------------------------- FR-10 projected low stock
def _item(db, pid, sku, name, stock, threshold, sold_per_day, days=7, unit="kg"):
    """A product with `stock` on hand and sales of `sold_per_day` on each of the last `days`."""
    now = datetime.now(timezone.utc)
    if db.get(Supplier, 1) is None:
        db.add(Supplier(supplier_id=1, name="Fresh Farms"))
    db.add(Product(
        product_id=pid, sku=sku, name=name, category="Test", unit=unit, shelf_life_days=5,
        storage_type="Chilled", temp_min=2, temp_max=8, cost_price=Decimal(1),
        selling_price=Decimal(10), low_stock_threshold=threshold))
    db.flush()
    db.add(Batch(product_id=pid, supplier_id=1, quantity=Decimal(stock),
                 initial_quantity=Decimal(stock), received_at=now - timedelta(days=9),
                 expiry_date=store_today() + timedelta(days=5)))
    for d in range(1, days + 1):
        db.add(Sale(product_id=pid, sku=sku, quantity=Decimal(sold_per_day), unit=unit,
                    unit_price=Decimal(10), amount=Decimal(10) * sold_per_day,
                    sold_at=now - timedelta(days=d, hours=1), source="manual", recorded_by="x"))
    db.commit()


def test_projected_alert_one_day_before_falling_below(client, db):
    """TC-LOW-01: threshold 10, stock 15, average 6/day -> 15 - 6 = 9 < 10 -> alert."""
    _item(db, 1, "TOM-01", "Tomato", 15, 10, 6)
    result = run_low_stock_check(db)
    db.commit()
    assert result["raised"] == 1
    rows = of_type(alerts(client), "PROJECTED_LOW_STOCK")
    assert len(rows) == 1
    assert rows[0]["message"].startswith("Tomato projected below 10 tomorrow")
    assert of_type(alerts(client), "LOW_STOCK") == []  # not short yet


def test_no_projected_alert_when_stock_is_enough(client, db):
    """TC-LOW-02: stock 40, 6/day -> 34 >= 10."""
    _item(db, 1, "TOM-01", "Tomato", 40, 10, 6)
    run_low_stock_check(db)
    db.commit()
    assert alerts(client) == []


def test_projection_uses_the_items_own_threshold(client, db):
    """TC-LOW-03: onion threshold 25, stock 30, 8/day -> 22 < 25 (the default 10 would not fire)."""
    _item(db, 2, "ONI-01", "Onion", 30, 25, 8)
    run_low_stock_check(db)
    db.commit()
    assert len(of_type(alerts(client), "PROJECTED_LOW_STOCK")) == 1


def test_average_is_over_the_last_7_days_only(client, db):
    """Sales older than 7 days do not count: 6/day on days 8-14 only means an average of 0."""
    now = datetime.now(timezone.utc)
    _item(db, 1, "TOM-01", "Tomato", 15, 10, 0, days=0)
    for d in range(8, 15):
        db.add(Sale(product_id=1, sku="TOM-01", quantity=Decimal(6), unit="kg",
                    unit_price=Decimal(10), amount=Decimal(60),
                    sold_at=now - timedelta(days=d), source="manual", recorded_by="x"))
    db.commit()
    assert run_low_stock_check(db)["raised"] == 0


def test_projected_alert_is_closed_when_it_no_longer_applies_and_is_not_duplicated(client, db):
    _item(db, 1, "TOM-01", "Tomato", 15, 10, 6)
    run_low_stock_check(db)
    run_low_stock_check(db)
    db.commit()
    assert len(of_type(alerts(client), "PROJECTED_LOW_STOCK")) == 1
    db.get(Batch, 1).quantity = Decimal(100)  # restocked
    db.commit()
    assert run_low_stock_check(db)["resolved"] == 1
    db.commit()
    assert alerts(client, status="open") == []


def test_real_shortage_replaces_the_projection(client, db):
    _item(db, 1, "TOM-01", "Tomato", 15, 10, 6)
    run_low_stock_check(db)
    db.commit()
    assert sell(client, qty=6).status_code == 201  # 9 left: below 10
    rows = alerts(client)
    assert [a["status"] for a in of_type(rows, "PROJECTED_LOW_STOCK")] == ["resolved"]
    assert len(of_type(rows, "LOW_STOCK")) == 1


def test_daily_check_also_catches_items_already_below_threshold(client, seeded):
    """Bread starts at 7 (< 10) with no sale ever recorded: the daily check raises it."""
    run_low_stock_check(seeded)
    seeded.commit()
    names = [a["message"] for a in of_type(alerts(client), "LOW_STOCK")]
    assert any(m.startswith("Bread Loaf") for m in names)


def test_manager_can_run_the_check_on_demand(client, db):
    _item(db, 1, "TOM-01", "Tomato", 15, 10, 6)
    r = client.post("/api/alerts/run-low-stock-check", headers=auth("manager1", "Manager"))
    assert r.status_code == 200 and r.json() == {"raised": 1, "resolved": 0}
    r = client.post("/api/alerts/run-low-stock-check", headers=auth("staff1", "Inventory Staff"))
    assert r.status_code == 403


# ---------------------------------------------------------------- daily timetable
def _at(hour, minute=0, day=0):
    """A UTC instant that is hour:minute on a fixed store-local day (Asia/Kolkata, UTC+5:30)."""
    local = datetime(2026, 10, 20, hour, minute, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    return (local + timedelta(days=day)).astimezone(timezone.utc)


def test_daily_job_runs_once_per_day_at_the_configured_time(db):
    assert run_daily_low_stock_job(db, _at(5, 59)) is False  # before 06:00
    assert run_daily_low_stock_job(db, _at(6, 0)) is True
    db.commit()
    assert run_daily_low_stock_job(db, _at(9, 0)) is False  # already ran today
    assert run_daily_low_stock_job(db, _at(6, 0, day=1)) is True  # next day
    db.commit()
    assert db.scalar(select(JobRun.last_run_on).where(JobRun.job == LOW_STOCK_JOB)).day == 21


def test_daily_job_catches_up_after_a_restart_later_in_the_day(db):
    assert run_daily_low_stock_job(db, _at(14, 30)) is True


# ---------------------------------------------------------------- delivery (NFR-2, ADR-7)
class Recorder:
    def __init__(self, fail=0):
        self.sent, self.fail = [], fail

    def send(self, recipient, subject, body):
        if self.fail:
            self.fail -= 1
            raise ConnectionError("gateway down")
        self.sent.append((recipient, subject, body))


@pytest.fixture()
def gateway():
    rec = Recorder()
    notifier.set_notifier(rec)
    yield rec
    notifier.set_notifier(notifier.EmailNotifier())


def test_new_alert_is_delivered_to_managers_only(client, seeded, gateway):
    auth("manager1", "Manager")
    auth("manager2", "Manager")
    auth("staff1", "Inventory Staff")
    sell(client, qty=29)
    assert notifier.dispatch_pending(seeded) == 1
    seeded.commit()
    assert sorted(r for r, _, _ in gateway.sent) == ["manager1@example.com", "manager2@example.com"]
    assert "Tomato is low" in gateway.sent[0][2]
    a = alerts(client)[0]
    assert a["deliveryStatus"] == "sent" and a["deliveredAt"]
    assert notifier.dispatch_pending(seeded) == 0  # nothing is sent twice


def test_failed_delivery_keeps_the_alert_visible_and_is_retried(client, seeded):
    auth("manager1", "Manager")
    rec = Recorder(fail=1)
    notifier.set_notifier(rec)
    try:
        sell(client, qty=29)
        now = datetime.now(timezone.utc)
        assert notifier.dispatch_pending(seeded, now) == 0
        seeded.commit()
        a = alerts(client)[0]
        assert a["deliveryStatus"] == "failed" and a["status"] == "active"  # still shown
        assert notifier.dispatch_pending(seeded, now + timedelta(seconds=5)) == 0  # too soon
        assert notifier.dispatch_pending(seeded, now + notifier.RETRY_GAP * 2) == 1
        seeded.commit()
        assert alerts(client)[0]["deliveryStatus"] == "sent"
    finally:
        notifier.set_notifier(notifier.EmailNotifier())


def test_delivery_gives_up_after_max_attempts(client, seeded):
    auth("manager1", "Manager")
    notifier.set_notifier(Recorder(fail=99))
    try:
        sell(client, qty=29)
        now = datetime.now(timezone.utc)
        for i in range(notifier.MAX_ATTEMPTS + 2):
            notifier.dispatch_pending(seeded, now + i * notifier.RETRY_GAP * 2)
            seeded.commit()  # the scheduler commits after every round
        row = seeded.scalar(select(Alert))
        assert row.delivery_attempts == notifier.MAX_ATTEMPTS and row.delivery_status == "failed"
    finally:
        notifier.set_notifier(notifier.EmailNotifier())


def test_alert_without_any_manager_is_marked_skipped(client, seeded, gateway):
    sell(client, qty=29)  # only a cashier exists
    notifier.dispatch_pending(seeded)
    seeded.commit()
    assert alerts_row(seeded).delivery_status == "skipped" and gateway.sent == []


def alerts_row(db):
    db.expire_all()
    return db.scalar(select(Alert))

def test_default_delivery_uses_the_shared_email_sender(client, seeded):
    """Without a fake gateway, a manager alert goes out through app.notify.send_email."""
    from app.notify import OUTBOX

    auth("manager1", "Manager")
    OUTBOX.clear()
    sell(client, qty=29)
    assert notifier.dispatch_pending(seeded) == 1
    seeded.commit()
    assert [(m.to, m.subject) for m in OUTBOX] == [("manager1@example.com",
                                                    "PMS alert: LOW_STOCK")]
    assert "Tomato is low: 8 kg left" in OUTBOX[0].body


def test_mail_server_failure_marks_the_alert_failed_for_retry(client, seeded, monkeypatch):
    auth("manager1", "Manager")

    def refuse(to, subject, body):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr("app.alerts.notifier.send_email", refuse)
    sell(client, qty=29)
    assert notifier.dispatch_pending(seeded) == 0
    seeded.commit()
    a = alerts(client)[0]
    assert a["deliveryStatus"] == "failed" and a["status"] == "active"