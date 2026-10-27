from decimal import Decimal

from sqlalchemy import select

from app.models import Batch, Removal, StockCount
from tests.conftest import auth


def test_removal_deducts_stock_and_records_audit(client, seeded):
    db = seeded
    batch = db.scalar(select(Batch).where(Batch.batch_id == 101))
    assert batch is not None
    original_quantity = Decimal(str(batch.quantity))

    response = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 2, "reason": "damaged"},
        headers=auth("stock-tester", "Inventory Staff"),
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["batchId"] == 101
    assert data["qty"] == 2.0
    assert data["remainingQuantity"] == float(original_quantity - 2)
    assert data["recordedBy"] == "stock-tester"

    db.refresh(batch)
    assert Decimal(str(batch.quantity)) == original_quantity - 2

    record = db.scalar(select(Removal).where(Removal.removal_id == data["removalId"]))
    assert record is not None
    assert record.reason == "damaged"
    assert record.recorded_by == "stock-tester"
    assert record.recorded_at is not None


def test_removal_rejects_quantity_above_batch_stock(client, seeded):
    db = seeded
    batch = db.scalar(select(Batch).where(Batch.batch_id == 101))
    assert batch is not None
    original_quantity = Decimal(str(batch.quantity))

    response = client.post(
        "/api/removals",
        json={
            "batchId": 101,
            "qty": float(original_quantity + 1),
            "reason": "damaged",
        },
        headers=auth("stock-tester", "Inventory Staff"),
    )

    assert response.status_code == 422, response.text
    db.refresh(batch)
    assert Decimal(str(batch.quantity)) == original_quantity


def test_removal_rejects_missing_fields(client):
    response = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 1},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert response.status_code == 400, response.text


def test_removal_rejects_zero_quantity(client):
    response = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 0, "reason": "damaged"},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert response.status_code == 400, response.text


def test_removal_rejects_unknown_batch(client, seeded):
    response = client.post(
        "/api/removals",
        json={"batchId": 999999, "qty": 1, "reason": "damaged"},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert response.status_code == 404, response.text


def test_stock_count_records_variance_and_adjusts_stock(client, seeded):
    db = seeded
    batch = db.scalar(select(Batch).where(Batch.batch_id == 101))
    assert batch is not None
    original_quantity = Decimal(str(batch.quantity))
    counted_quantity = original_quantity + Decimal("3")

    response = client.post(
        "/api/stock-counts",
        json={
            "batchId": 101,
            "countedQuantity": str(counted_quantity),
            "reason": "physical stock count",
        },
        headers=auth("stock-tester", "Inventory Staff"),
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["systemQuantity"] == float(original_quantity)
    assert data["countedQuantity"] == float(counted_quantity)
    assert data["variance"] == 3.0
    assert data["recordedBy"] == "stock-tester"

    db.refresh(batch)
    assert Decimal(str(batch.quantity)) == counted_quantity

    record = db.scalar(select(StockCount).where(StockCount.stock_count_id == data["stockCountId"]))
    assert record is not None
    assert Decimal(str(record.variance)) == Decimal("3")
    assert record.reason == "physical stock count"
    assert record.recorded_by == "stock-tester"
    assert record.recorded_at is not None


def test_stock_count_allows_zero_quantity(client, seeded):
    db = seeded
    response = client.post(
        "/api/stock-counts",
        json={
            "batchId": 101,
            "countedQuantity": 0,
            "reason": "counted zero remaining",
        },
        headers=auth("stock-tester", "Inventory Staff"),
    )

    assert response.status_code == 201, response.text
    assert response.json()["countedQuantity"] == 0.0

    batch = db.scalar(select(Batch).where(Batch.batch_id == 101))
    assert batch is not None
    db.refresh(batch)
    assert Decimal(str(batch.quantity)) == Decimal("0")


def test_stock_count_rejects_negative_quantity(client, seeded):
    response = client.post(
        "/api/stock-counts",
        json={
            "batchId": 101,
            "countedQuantity": -1,
            "reason": "invalid count",
        },
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert response.status_code == 400, response.text


def test_cashier_cannot_record_removals(client):
    response = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 1, "reason": "damaged"},
        headers=auth("cashier-tester", "Cashier"),
    )
    assert response.status_code == 403, response.text


def test_cashier_cannot_record_stock_counts(client):
    response = client.post(
        "/api/stock-counts",
        json={
            "batchId": 101,
            "countedQuantity": 10,
            "reason": "physical count",
        },
        headers=auth("cashier-tester", "Cashier"),
    )
    assert response.status_code == 403, response.text


def test_stock_count_rejects_quantity_above_max(client, seeded):
    response = client.post(
        "/api/stock-counts",
        json={
            "batchId": 101,
            "countedQuantity": 1000000000000,
            "reason": "recount",
        },
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert response.status_code == 400, response.text


def test_removal_rejects_decimal_batch_id(client, seeded):
    response = client.post(
        "/api/removals",
        json={"batchId": 101.9, "qty": 1, "reason": "damaged"},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert response.status_code == 400, response.text


def test_removal_rejects_blank_reason(client, seeded):
    response = client.post(
        "/api/removals",
        json={"batchId": 101, "qty": 1, "reason": "   "},
        headers=auth("stock-tester", "Inventory Staff"),
    )
    assert response.status_code == 400, response.text
