import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Batch, Product, Supplier
from app.sales.fefo import store_today
from tests.conftest import auth


@pytest.fixture()
def curd_product(db):
    """Seed Curd product (price 50) and Supplier."""
    supp = Supplier(supplier_id=1, name="Dairy Co")
    prod = Product(
        product_id=10,
        sku="CURD-01",
        name="Curd",
        category="Dairy",
        unit="piece",
        shelf_life_days=5,
        storage_type="Chilled",
        temp_min=2.0,
        temp_max=8.0,
        cost_price=Decimal("30.00"),
        selling_price=Decimal("50.00"),
        low_stock_threshold=5,
        active=True,
    )
    db.add_all([supp, prod])
    db.commit()
    return prod


def test_tc_exp_06_markdown_applied_by_rule(client, db, curd_product, caplog):
    """TC-EXP-06: Rule: 20% off at 1 day left; max 40%; Curd price 50.
    Run markdown check on Curd batch with 1 day left -> price = 40; markdown logged.
    """
    today = store_today()
    batch = Batch(
        batch_id=101,
        store_id=1,
        product_id=curd_product.product_id,
        supplier_id=1,
        quantity=Decimal("10"),
        initial_quantity=Decimal("10"),
        received_at=datetime.now(timezone.utc) - timedelta(days=4),
        expiry_date=today + timedelta(days=1),  # 1 day left
    )
    db.add(batch)
    db.commit()

    # Manager creates rule: 20% off at 1 day left
    mgr = auth("mgr1", "Manager")
    r = client.post(
        "/api/markdown-rules",
        json={"productId": curd_product.product_id, "daysBeforeExpiry": 1, "discountPercent": 20.0},
        headers=mgr,
    )
    assert r.status_code == 201
    assert r.json()["discountPercent"] == 20.0
    assert r.json()["daysBeforeExpiry"] == 1

    # Run markdown check
    with caplog.at_level(logging.INFO, logger="pms.markdowns"):
        res = client.post("/api/markdowns/apply", headers=mgr)
    assert res.status_code == 200
    data = res.json()
    assert data["applied"] == 1
    md = data["markdowns"][0]
    assert md["batchId"] == 101
    assert md["productName"] == "Curd"
    assert md["originalPrice"] == 50.0
    assert md["discountPercent"] == 20.0
    assert md["discountedPrice"] == 40.0  # 50 - 20% = 40
    assert md["initialQuantity"] == 10.0

    # Verify markdown logged
    assert any("MARKDOWN_APPLIED" in m and "Curd" in m and "40" in m for m in caplog.messages)


def test_tc_exp_07_rule_above_maximum_discount_rejected(client, db, curd_product):
    """TC-EXP-07: Max discount 40%. Manager enters rule of 60% off ->
    Rejected 'Discount exceeds maximum 40%' (HTTP 422).
    """
    mgr = auth("mgr1", "Manager")
    r = client.post(
        "/api/markdown-rules",
        json={"productId": curd_product.product_id, "daysBeforeExpiry": 1, "discountPercent": 60.0},
        headers=mgr,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "DISCOUNT_EXCEEDS_MAX"
    assert "Discount exceeds maximum 40%" in body["error"]["message"]


def test_tc_exp_08_markdown_sell_through_tracked(client, db, curd_product):
    """TC-EXP-08: 10 units of Curd marked down.
    Sell 8 marked-down units.
    Open markdown report -> Shows 8 of 10 sold (80%).
    """
    today = store_today()
    batch = Batch(
        batch_id=102,
        store_id=1,
        product_id=curd_product.product_id,
        supplier_id=1,
        quantity=Decimal("10"),
        initial_quantity=Decimal("10"),
        received_at=datetime.now(timezone.utc) - timedelta(days=4),
        expiry_date=today + timedelta(days=1),
    )
    db.add(batch)
    db.commit()

    # Manager rule: 20% discount
    mgr = auth("mgr1", "Manager")
    client.post(
        "/api/markdown-rules",
        json={"productId": curd_product.product_id, "daysBeforeExpiry": 1, "discountPercent": 20.0},
        headers=mgr,
    )
    client.post("/api/markdowns/apply", headers=mgr)

    # Cashier sells 8 units
    cashier = auth("cash1", "Cashier")
    sale_resp = client.post(
        "/api/sales",
        json={"sku": "CURD-01", "quantity": 8},
        headers=cashier,
    )
    assert sale_resp.status_code == 201
    # Billed at discounted price: 8 * 40.00 = 320.00
    assert float(sale_resp.json()["amount"]) == 320.00

    # Check markdown report / sell-through
    rep = client.get("/api/markdowns", headers=mgr)
    assert rep.status_code == 200
    items = rep.json()
    item = next(x for x in items if x["batchId"] == 102)
    assert item["initialQuantity"] == 10.0
    assert item["quantitySold"] == 8.0
    assert item["remainingQuantity"] == 2.0
    assert item["sellThroughPercent"] == 80.0


def test_markdown_access_control(client, db, curd_product, caplog):
    """Only Manager and Admin can create or delete rules; Cashier and Staff get 403."""
    staff = auth("staff1", "Inventory Staff")
    cashier = auth("cash1", "Cashier")

    # Staff tries to create a rule -> 403
    with caplog.at_level(logging.WARNING, logger="pms.security"):
        r = client.post(
            "/api/markdown-rules",
            json={
                "productId": curd_product.product_id,
                "daysBeforeExpiry": 2,
                "discountPercent": 15.0,
            },
            headers=staff,
        )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    assert any("ACCESS_DENIED" in m and "user=staff1" in m for m in caplog.messages)

    # Cashier tries to create a rule -> 403
    r = client.post(
        "/api/markdown-rules",
        json={
            "productId": curd_product.product_id,
            "daysBeforeExpiry": 2,
            "discountPercent": 15.0,
        },
        headers=cashier,
    )
    assert r.status_code == 403

    # Admin can create rule -> 201
    admin = auth("admin1", "Admin")
    r = client.post(
        "/api/markdown-rules",
        json={
            "productId": curd_product.product_id,
            "daysBeforeExpiry": 2,
            "discountPercent": 15.0,
        },
        headers=admin,
    )
    assert r.status_code == 201
    rule_id = r.json()["ruleId"]

    # Delete rule: Manager can delete -> 200
    mgr = auth("mgr1", "Manager")
    del_res = client.delete(f"/api/markdown-rules/{rule_id}", headers=mgr)
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


def test_fefo_spans_marked_down_and_regular_batches(client, db, curd_product):
    """FEFO sale correctly charges marked-down batch at discount and regular batch at full price."""
    today = store_today()
    # Batch 1: expires tomorrow, 4 units, marked down 20% (price 40)
    b1 = Batch(
        batch_id=201,
        store_id=1,
        product_id=curd_product.product_id,
        supplier_id=1,
        quantity=Decimal("4"),
        initial_quantity=Decimal("4"),
        received_at=datetime.now(timezone.utc) - timedelta(days=4),
        expiry_date=today + timedelta(days=1),
    )
    # Batch 2: expires in 5 days, 10 units, regular price (50)
    b2 = Batch(
        batch_id=202,
        store_id=1,
        product_id=curd_product.product_id,
        supplier_id=1,
        quantity=Decimal("10"),
        initial_quantity=Decimal("10"),
        received_at=datetime.now(timezone.utc),
        expiry_date=today + timedelta(days=5),
    )
    db.add_all([b1, b2])
    db.commit()

    mgr = auth("mgr1", "Manager")
    client.post(
        "/api/markdown-rules",
        json={"productId": curd_product.product_id, "daysBeforeExpiry": 1, "discountPercent": 20.0},
        headers=mgr,
    )
    client.post("/api/markdowns/apply", headers=mgr)

    # Cashier sells 6 units (4 from b1 @ 40 + 2 from b2 @ 50 = 160 + 100 = 260)
    cashier = auth("cash1", "Cashier")
    sale_resp = client.post(
        "/api/sales",
        json={"sku": "CURD-01", "quantity": 6},
        headers=cashier,
    )
    assert sale_resp.status_code == 201
    assert float(sale_resp.json()["amount"]) == 260.00
