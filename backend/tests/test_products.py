"""Tests for the product and supplier master API (Issue #5)."""

import pytest

from tests.conftest import auth


def product_payload(sku="TEST-01"):
    return {
        "sku": sku,
        "name": "Test Apple",
        "category": "Fruits",
        "unit": "kg",
        "shelfLifeDays": 7,
        "storageType": "Chilled",
        "tempMin": 2,
        "tempMax": 8,
        "costPrice": 10,
        "sellingPrice": 15,
        "lowStockThreshold": 10,
    }


def test_products_requires_login(client):
    assert client.get("/api/products").status_code == 401


def test_list_products_includes_stock_and_camel_case_fields(client, seeded):
    response = client.get("/api/products", headers=auth("staff1", "Inventory Staff"))
    assert response.status_code == 200
    tomato = next(item for item in response.json() if item["sku"] == "TOM-01")
    assert tomato["productId"] == 1
    assert tomato["shelfLifeDays"] == 5
    assert tomato["lowStockThreshold"] == 10
    assert tomato["stock"] == 37


def test_manager_can_create_product(client, db):
    response = client.post(
        "/api/products",
        json=product_payload(),
        headers=auth("manager1", "Manager"),
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "TEST-01"
    assert response.json()["stock"] == 0


def test_duplicate_sku_returns_conflict(client, seeded):
    response = client.post(
        "/api/products",
        json=product_payload("TOM-01"),
        headers=auth("manager1", "Manager"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_SKU"


def test_cashier_cannot_create_product(client):
    response = client.post(
        "/api/products",
        json=product_payload(),
        headers=auth("cashier1", "Cashier"),
    )
    assert response.status_code == 403


def test_product_can_be_deactivated_and_reactivated(client, seeded):
    headers = auth("manager1", "Manager")
    deactivated = client.patch("/api/products/1/deactivate", headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    activated = client.patch("/api/products/1/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["active"] is True


def test_suppliers_are_available_to_logged_in_users(client, seeded):
    response = client.get("/api/suppliers", headers=auth("staff1", "Inventory Staff"))
    assert response.status_code == 200
    assert response.json() == [{"supplierId": 1, "name": "Fresh Farms"}]


def test_sku_is_stored_uppercase_and_case_duplicates_conflict(client, seeded):
    headers = auth("manager1", "Manager")
    created = client.post("/api/products", json=product_payload("new-01"), headers=headers)
    assert created.status_code == 201
    assert created.json()["sku"] == "NEW-01"
    duplicate = client.post("/api/products", json=product_payload("tom-01"), headers=headers)
    assert duplicate.status_code == 409


@pytest.mark.parametrize("override", [
    {"costPrice": 0},
    {"sellingPrice": 0},
    {"sellingPrice": -5},
    {"tempMin": 5, "tempMax": 5},
    {"tempMin": 12, "tempMax": 8},
    {"storageType": "Warehouse"},
    {"unit": "dozen"},
    {"shelfLifeDays": 0},
])
def test_invalid_product_is_400(client, seeded, override):
    response = client.post(
        "/api/products",
        json={**product_payload("BAD-01"), **override},
        headers=auth("manager1", "Manager"),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION"


def test_manager_can_edit_product(client, seeded):
    body = {**product_payload("TOM-01"), "name": "Tomato (local)", "sellingPrice": 32}
    response = client.put("/api/products/1", json=body, headers=auth("manager1", "Manager"))
    assert response.status_code == 200
    assert response.json()["name"] == "Tomato (local)"
    assert response.json()["sellingPrice"] == 32


def test_edit_unknown_product_is_404(client, seeded):
    response = client.put(
        "/api/products/999", json=product_payload("Z-01"), headers=auth("manager1", "Manager")
    )
    assert response.status_code == 404
