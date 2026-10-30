"""Batches: receive, restock, age / days left and FEFO order (FR-2, FR-4, FR-5, FR-6)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Batch, Supplier
from app.sales.fefo import store_today
from tests.conftest import auth, stock

STAFF = ("staff1", "Inventory Staff")


def receive(client, headers=None, **over):
    today = store_today()
    body = {
        "productId": 1,
        "supplierId": 1,
        "quantity": 20,
        "unit": "kg",
        "receivedAt": datetime.now(timezone.utc).isoformat(),
        "expiryDate": str(today + timedelta(days=4)),
    }
    body.update(over)
    return client.post("/api/batches", json=body, headers=headers or auth(*STAFF))


def fefo(client, product_id=1, headers=None):
    return client.get(f"/api/batches/fefo?productId={product_id}",
                      headers=headers or auth(*STAFF))


# ---- receive a batch (TC-STK-01) ----------------------------------------------------------

def test_tc_stk_01_received_batch_keeps_all_receipt_data(client, seeded):
    r = receive(client, quantity=20, expiryDate=str(store_today() + timedelta(days=4)))
    assert r.status_code == 201
    body = r.json()
    assert body["newStock"] == 57  # 37 kg tomato already in stock
    seeded.expire_all()
    batch = seeded.get(Batch, body["batchId"])
    assert (batch.product_id, batch.supplier_id, batch.quantity, batch.initial_quantity) == (
        1, 1, 20, 20)
    assert batch.expiry_date == store_today() + timedelta(days=4)
    assert batch.received_at is not None and batch.store_id == 1


def test_tc_stk_01_expiry_before_received_date_is_400(client, seeded):
    r = receive(client, expiryDate=str(store_today() - timedelta(days=1)))
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "Expiry date must be after received date"
    assert stock(seeded, 1) == 37


def test_tc_stk_01_expiring_on_the_day_received_is_allowed(client, seeded):
    assert receive(client, expiryDate=str(store_today())).status_code == 201


@pytest.mark.parametrize("quantity", [0, -5, "abc", 0.0005])
def test_tc_stk_01_bad_quantity_is_400(client, seeded, quantity):
    assert receive(client, quantity=quantity).status_code == 400
    assert stock(seeded, 1) == 37


def test_pieces_must_be_whole_and_unit_must_match(client, seeded):
    assert receive(client, productId=2, unit="piece", quantity=2.5).status_code == 400
    r = receive(client, productId=1, unit="piece")
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNIT_MISMATCH"


def test_unknown_product_404_unknown_supplier_400_inactive_422(client, seeded):
    assert receive(client, productId=999).status_code == 404
    r = receive(client, supplierId=999)
    assert r.status_code == 400 and r.json()["error"]["message"] == "Unknown supplier"
    r = receive(client, productId=6)  # "Retired item" is deactivated
    assert r.status_code == 422 and r.json()["error"]["code"] == "INACTIVE"


def test_missing_fields_are_400(client, seeded):
    r = client.post("/api/batches", json={"productId": 1}, headers=auth(*STAFF))
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION"


# ---- restock (TC-STK-03) --------------------------------------------------------------------

def test_tc_stk_03_restock_adds_stock_with_shelf_life_expiry(client, seeded):
    r = client.post("/api/restocks", json={"productId": 1, "quantity": 10},
                    headers=auth(*STAFF))
    assert r.status_code == 201 and r.json()["newStock"] == 47
    seeded.expire_all()
    batch = seeded.get(Batch, r.json()["batchId"])
    assert batch.expiry_date == store_today() + timedelta(days=5)  # tomato shelf-life 5 days
    assert batch.supplier_id == 1  # taken from the latest batch


def test_restock_with_another_supplier(client, seeded):
    seeded.add(Supplier(supplier_id=2, name="Green Valley"))
    seeded.commit()
    r = client.post("/api/restocks", json={"productId": 1, "quantity": 3, "supplierId": 2},
                    headers=auth(*STAFF))
    assert r.status_code == 201
    seeded.expire_all()
    assert seeded.get(Batch, r.json()["batchId"]).supplier_id == 2


def test_restock_without_any_earlier_batch_needs_a_supplier(client, seeded):
    seeded.query(Batch).filter(Batch.product_id == 1).delete()
    seeded.commit()
    r = client.post("/api/restocks", json={"productId": 1, "quantity": 3}, headers=auth(*STAFF))
    assert r.status_code == 400


def test_restock_bad_quantity_is_400(client, seeded):
    r = client.post("/api/restocks", json={"productId": 1, "quantity": 0}, headers=auth(*STAFF))
    assert r.status_code == 400
    assert stock(seeded, 1) == 37


# ---- age, days left and FEFO order (TC-STK-04, TC-STK-05) -----------------------------------

def test_tc_stk_04_age_and_days_left(client, seeded):
    rows = fefo(client).json()
    first = rows[0]
    assert first["batchId"] == 101
    assert first["daysInStore"] == 2 and first["daysToExpiry"] == 2  # seeded 2 days ago
    assert first["supplier"] == "Fresh Farms" and first["unit"] == "kg"
    assert first["quantity"] == 12


def test_tc_stk_05_batches_in_ascending_expiry_order(client, seeded):
    receive(client, quantity=5, expiryDate=str(store_today() + timedelta(days=1)))
    rows = fefo(client).json()
    expiries = [r["expiryDate"] for r in rows]
    assert expiries == sorted(expiries)
    assert [r["batchId"] for r in rows][1:] == [101, 102]  # the new 1-day batch comes first


def test_tc_stk_05_expired_batches_are_listed_and_empty_ones_are_not(client, seeded):
    rows = fefo(client, product_id=3).json()  # milk: 8 l expired, 30 l fresh
    assert [(r["batchId"], r["daysToExpiry"] < 0) for r in rows] == [(104, True), (105, False)]
    seeded.get(Batch, 105).quantity = 0
    seeded.commit()
    assert [r["batchId"] for r in fefo(client, product_id=3).json()] == [104]


def test_tc_stk_05_unknown_product_404(client, seeded):
    r = fefo(client, product_id=999)
    assert r.status_code == 404 and r.json()["error"]["message"] == "Unknown product"


def test_fefo_needs_a_product_id(client, seeded):
    r = client.get("/api/batches/fefo", headers=auth(*STAFF))
    assert r.status_code == 400


# ---- roles (SEC-2) and the link to sales ----------------------------------------------------

@pytest.mark.parametrize("role,expected", [
    ("Admin", 201), ("Manager", 201), ("Inventory Staff", 201), ("Cashier", 403),
])
def test_who_may_receive_and_restock(client, seeded, role, expected):
    headers = auth("u1", role)
    assert receive(client, headers=headers).status_code == expected
    r = client.post("/api/restocks", json={"productId": 1, "quantity": 1}, headers=headers)
    assert r.status_code == expected


def test_batch_endpoints_need_login(client, seeded):
    assert client.post("/api/batches", json={}).status_code == 401
    assert client.post("/api/restocks", json={}).status_code == 401
    assert client.get("/api/batches/fefo?productId=1").status_code == 401


def test_received_batch_is_sold_in_fefo_order(client, seeded, cashier):
    new = receive(client, quantity=4, expiryDate=str(store_today() + timedelta(days=1)))
    sale = client.post("/api/sales", json={"sku": "TOM-01", "quantity": 6}, headers=cashier)
    assert sale.status_code == 201
    used = [(b["batchId"], b["qty"]) for b in sale.json()["batchesUsed"]]
    assert used == [(new.json()["batchId"], 4), (101, 2)]


def test_batches_belong_to_the_store(client, seeded):
    r = receive(client)
    seeded.expire_all()
    assert seeded.scalar(select(Batch.store_id).where(Batch.batch_id == r.json()["batchId"])) == 1
