"""S3-1: edge-case tests for the tricky cases the other tests do not cover.

Some of these cases are not handled correctly yet. Those tests are marked
`@gap("S3-n", ...)`, which means "expected to fail until story S3-n is done". CI stays green
while the gap exists. When someone fixes it, the test starts passing, strict mode turns CI red,
and the person who fixed it deletes the `@gap` line in the same PR. That proves the fix works.

Tests without `@gap` check nearby behaviour that works today and must keep working.

  edge case 1   sale dated in the future              S3-2
  edge case 2   offline sale from before midnight     S3-2
  edge case 3   CSV over the row limit                S3-2
  edge case 4   fridge limit changed                  S3-2
  edge case 5   batch received in the future          S3-3
  edge case 6   discount rule with product + category S3-3
  edge case 7   expiry alert after batch sold out     S3-3
  edge case 8   background refresh and idle logout    S3-4
  edge case 9   user edit with null                   S3-4
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.errors import ApiError
from app.models import Alert, Batch, Markdown, Sale, UserSession
from app.notifications.service import create_expiry_notifications
from app.sales.fefo import record_sale, store_today
from tests.conftest import auth, make_user

IST = ZoneInfo("Asia/Kolkata")
FAR_FUTURE = "2099-01-01T10:00:00+05:30"
# S3-4 proposes that automatic refreshes send this header. Change it here if the team decides on
# another way to tell a background refresh from a person's click.
BACKGROUND = {"X-Background-Refresh": "1"}


def gap(story: str, why: str):
    """Expected to fail until `story` is done; then delete this line (strict = CI tells you)."""
    return pytest.mark.xfail(strict=True, reason=f"{story}: {why}")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def upload_csv(client, headers, text: str):
    return client.post("/api/sales/csv", headers=headers,
                       files={"file": ("sales.csv", text.encode(), "text/csv")})


def send_reading(client, key, unit, kind, value, when=None):
    return client.post("/api/device/readings", headers={"X-Device-Key": key}, json={
        "eventId": f"edge-{uuid4()}", "unitId": unit, "type": kind, "value": value,
        "recordedAt": (when or now_utc()).isoformat()})


def open_alerts(Session, alert_type: str) -> int:
    with Session() as db:
        return db.scalar(select(func.count()).select_from(Alert).where(
            Alert.type == alert_type, Alert.status != "resolved"))


def count_sales(Session) -> int:
    with Session() as db:
        return db.scalar(select(func.count()).select_from(Sale))


# ============================================ 1. sale dated in the future
def test_edge_1_sale_dated_in_the_future_is_refused(client, seeded, cashier, pos_key):
    manual = client.post("/api/sales", headers=cashier,
                         json={"sku": "TOM-01", "quantity": 1, "soldAt": FAR_FUTURE})
    device = client.post("/api/device/sales", headers={"X-Device-Key": pos_key},
                         json={"eventId": "e1", "sku": "TOM-01", "quantity": 1,
                               "soldAt": FAR_FUTURE})
    csv_row = upload_csv(client, cashier, "sku,quantity,soldAt\nTOM-01,1,2099-01-01T10:00\n")
    assert manual.status_code == 400, "manual sale"
    assert device.status_code == 400, "POS device sale"
    assert csv_row.json()["imported"] == 0, "CSV row"


def test_edge_1_sale_a_minute_ahead_is_still_accepted(client, seeded, cashier):
    """A till or sensor clock a little ahead must not make sales fail."""
    ahead = (now_utc() + timedelta(minutes=1)).isoformat()
    r = client.post("/api/sales", headers=cashier,
                    json={"sku": "TOM-01", "quantity": 1, "soldAt": ahead})
    assert r.status_code == 201, r.json()


# ============================================ 2. offline sale across midnight
def yesterday_evening() -> datetime:
    return datetime.combine(store_today() - timedelta(days=1), time(18, 0), tzinfo=IST)


def test_edge_2_offline_sale_from_before_midnight_is_accepted_after_midnight(
        client, seeded, pos_key):
    """Bread's only batch was valid through yesterday. The sale happened yesterday evening."""
    r = client.post("/api/device/sales", headers={"X-Device-Key": pos_key}, json={
        "eventId": "e2", "sku": "BRD-01", "quantity": 1,
        "soldAt": yesterday_evening().isoformat()})
    assert r.status_code == 201, r.json()


def test_edge_2_sale_made_after_the_batch_expired_is_still_refused(client, seeded, pos_key):
    r = client.post("/api/device/sales", headers={"X-Device-Key": pos_key}, json={
        "eventId": "e2b", "sku": "BRD-01", "quantity": 1, "soldAt": now_utc().isoformat()})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "BATCH_EXPIRED")


def test_edge_2_expiry_flips_at_midnight_in_store_time_not_utc(seeded):
    """Batch valid through 1 Nov: sellable at 23:30 IST (18:00 UTC), expired at 00:30 IST."""
    db = seeded
    for b in db.scalars(select(Batch).where(Batch.product_id == 1)):
        b.quantity = Decimal(0)
    db.add(Batch(batch_id=300, product_id=1, supplier_id=1, quantity=Decimal(5),
                 initial_quantity=Decimal(5), received_at=now_utc(),
                 expiry_date=datetime(2026, 11, 1).date()))
    db.commit()
    before = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)  # 23:30 IST on 1 Nov
    after = datetime(2026, 11, 1, 19, 0, tzinfo=timezone.utc)   # 00:30 IST on 2 Nov
    assert record_sale(db, sku="TOM-01", quantity=1, source="manual", recorded_by="t",
                       now=before).batches_used[0].batch_id == 300
    db.rollback()
    with pytest.raises(ApiError) as e:
        record_sale(db, sku="TOM-01", quantity=1, source="manual", recorded_by="t", now=after)
    assert e.value.code == "BATCH_EXPIRED"


# ============================================ 3. CSV over the row limit
def test_edge_3_csv_over_the_row_limit_saves_nothing(client, seeded, cashier, Session):
    r = upload_csv(client, cashier, "sku,quantity\n" + "TOM-01,0.001\n" * 5001)
    assert r.status_code == 400
    assert count_sales(Session) == 0, "the file was refused but some rows were saved"


def test_edge_3_csv_with_exactly_5000_rows_imports_every_row(client, seeded, cashier, Session):
    r = upload_csv(client, cashier, "sku,quantity\n" + "TOM-01,0.001\n" * 5000)
    assert r.status_code == 200 and r.json()["imported"] == 5000
    assert count_sales(Session) == 5000


# ============================================ 4. fridge limit changed
def test_edge_4_tightening_a_fridge_limit_alerts_on_the_current_temperature(
        client, seeded, sensor_key, Session):
    send_reading(client, sensor_key, "Fridge-9", "temperature", 7.0)  # inside the default 0-8
    assert open_alerts(Session, "TEMPERATURE") == 0
    r = client.put("/api/refrigeration/units/Fridge-9", json={"tempMax": 5},
                   headers=auth("mgr9", "Manager"))
    assert r.status_code == 200
    assert open_alerts(Session, "TEMPERATURE") == 1, "7 C is now outside 0-5 C but nobody was told"


# ============================================ 5. batch received in the future
def new_batch(received_at: str, expiry: str) -> dict:
    return {"productId": 1, "supplierId": 1, "quantity": 5, "unit": "kg",
            "receivedAt": received_at, "expiryDate": expiry}


def test_edge_5_batch_received_in_the_future_is_refused(client, seeded):
    r = client.post("/api/batches", headers=auth("staff9", "Inventory Staff"),
                    json=new_batch("2030-01-01T10:00:00+05:30", "2030-01-05"))
    assert r.status_code == 400, r.json()


def test_edge_5_batch_received_a_minute_ahead_is_still_accepted(client, seeded):
    """A device or phone clock a little ahead must not stop a delivery being recorded."""
    r = client.post("/api/batches", headers=auth("staff9", "Inventory Staff"), json=new_batch(
        (now_utc() + timedelta(minutes=1)).isoformat(),
        (store_today() + timedelta(days=3)).isoformat()))
    assert r.status_code == 201, r.json()


# ============================================ 6. discount rule scope
def products_marked_down(db) -> set[int]:
    db.expire_all()
    return set(db.scalars(select(Markdown.product_id)).all())


def test_edge_6_rule_with_product_and_category_applies_to_that_product_only(client, seeded):
    mgr = auth("mgr9", "Manager")
    r = client.post("/api/markdown-rules", headers=mgr, json={
        "productId": 1, "category": "Test", "daysBeforeExpiry": 10, "discountPercent": 20})
    assert r.status_code in (200, 201), r.json()
    client.post("/api/markdowns/apply", headers=mgr)
    assert products_marked_down(seeded) == {1}


def test_edge_6_category_only_rule_still_applies_to_the_whole_category(client, seeded):
    """Must keep working when the rule above is fixed (every seeded product is category Test)."""
    mgr = auth("mgr9", "Manager")
    client.post("/api/markdown-rules", headers=mgr, json={
        "category": "Test", "daysBeforeExpiry": 10, "discountPercent": 20})
    client.post("/api/markdowns/apply", headers=mgr)
    assert products_marked_down(seeded) == {1, 2, 3}


# ============================================ 7. expiry alert and sold-out batch
def expiry_alert_for_batch_expiring_today(db) -> Alert:
    """A 2 kg Tomato batch that expires today; it sells first because it expires first."""
    db.add(Batch(batch_id=200, product_id=1, supplier_id=1, quantity=Decimal(2),
                 initial_quantity=Decimal(2), received_at=now_utc(), expiry_date=store_today()))
    db.commit()
    create_expiry_notifications(db)
    alert = db.scalar(select(Alert).where(Alert.type == "EXPIRY"))
    assert alert is not None and alert.status == "active"
    return alert


def expiry_alert_status(db) -> str:
    db.expire_all()
    return db.scalar(select(Alert.status).where(Alert.type == "EXPIRY"))


def test_edge_7_expiry_alert_closes_when_a_sale_empties_the_batch(client, seeded, cashier):
    expiry_alert_for_batch_expiring_today(seeded)
    r = client.post("/api/sales", headers=cashier, json={"sku": "TOM-01", "quantity": 2})
    assert r.status_code == 201 and r.json()["batchesUsed"][0]["batchId"] == 200
    assert expiry_alert_status(seeded) == "resolved"


def test_edge_7_expiry_alert_closes_when_a_stock_count_empties_the_batch(client, seeded):
    expiry_alert_for_batch_expiring_today(seeded)
    r = client.post("/api/stock-counts", headers=auth("staff9", "Inventory Staff"),
                    json={"batchId": 200, "countedQuantity": 0, "reason": "none left"})
    assert r.status_code == 201, r.json()
    assert expiry_alert_status(seeded) == "resolved"


def test_edge_7_expiry_alert_closes_when_a_removal_empties_the_batch(client, seeded):
    """Already works; the sale and stock count above should behave the same way."""
    expiry_alert_for_batch_expiring_today(seeded)
    r = client.post("/api/removals", headers=auth("staff9", "Inventory Staff"),
                    json={"batchId": 200, "qty": 2, "reason": "damaged"})
    assert r.status_code == 201, r.json()
    assert expiry_alert_status(seeded) == "resolved"


# ============================================ 8. idle logout and background refresh
def go_idle(db, minutes: float) -> None:
    """Pretend the last request on every session was `minutes` ago."""
    for s in db.scalars(select(UserSession)):
        s.last_seen_at = now_utc() - timedelta(minutes=minutes)
    db.commit()


def minutes_since_last_seen(db) -> float:
    db.expire_all()
    seen = db.scalar(select(UserSession.last_seen_at))
    seen = seen if seen.tzinfo else seen.replace(tzinfo=timezone.utc)
    return (now_utc() - seen).total_seconds() / 60


def test_edge_8_background_refresh_does_not_keep_the_session_alive(client, db):
    headers = auth("staff1", "Inventory Staff")
    go_idle(db, get_settings().idle_timeout_minutes - 1)  # one minute from being logged out
    r = client.get("/api/auth/me", headers={**headers, **BACKGROUND})
    assert r.status_code == 200
    assert minutes_since_last_seen(db) > get_settings().idle_timeout_minutes - 2


def test_edge_8_a_persons_request_keeps_the_session_alive(client, db):
    headers = auth("staff1", "Inventory Staff")
    go_idle(db, get_settings().idle_timeout_minutes - 1)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert minutes_since_last_seen(db) < 1


def test_edge_8_idle_session_is_ended_even_for_a_background_refresh(client, db):
    headers = auth("staff1", "Inventory Staff")
    go_idle(db, get_settings().idle_timeout_minutes + 1)
    assert client.get("/api/auth/me", headers={**headers, **BACKGROUND}).status_code == 401


# ============================================ 9. user edit with null
@pytest.mark.parametrize("field", ["name", "role", "email"])
def test_edge_9_user_edit_with_null_is_400_not_500(client, seeded, field):
    make_user("bob", "Cashier")
    soft = TestClient(client.app, raise_server_exceptions=False)  # a 500 comes back as a response
    r = soft.put("/api/users/bob", headers=auth("admin9", "Admin"), json={field: None})
    assert r.status_code == 400, (r.status_code, r.text[:100])


# ============================================ sale quantity edge values (works today)
@pytest.mark.parametrize("quantity", ["0", "-1", "0.0001", "1000000", "NaN", "Infinity",
                                      "abc", " "])
def test_sale_quantity_edge_values_are_refused(client, seeded, cashier, quantity):
    r = client.post("/api/sales", headers=cashier, json={"sku": "TOM-01", "quantity": quantity})
    assert r.status_code == 400, (quantity, r.status_code)
