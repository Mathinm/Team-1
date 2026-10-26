"""Suppliers: create one so stock can be received on a fresh install (Issue #30)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.sales.fefo import store_today
from tests.conftest import auth


def add_supplier(client, name="Green Valley", role="Manager"):
    return client.post("/api/suppliers", json={"name": name}, headers=auth("u1", role))


def test_manager_creates_a_supplier_and_it_is_listed(client, seeded):
    r = add_supplier(client, "  Green   Valley ")
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Green Valley" and isinstance(body["supplierId"], int)
    listed = client.get("/api/suppliers", headers=auth("s1", "Inventory Staff")).json()
    names = [s["name"] for s in listed]
    assert names == ["Fresh Farms", "Green Valley"]


def test_admin_can_create_a_supplier(client, seeded):
    assert add_supplier(client, "City Bakers", role="Admin").status_code == 201


@pytest.mark.parametrize("name", ["Fresh Farms", "fresh farms", "  FRESH  FARMS  "])
def test_duplicate_name_is_409(client, seeded, name):
    r = add_supplier(client, name)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "DUPLICATE_SUPPLIER"


@pytest.mark.parametrize("role", ["Inventory Staff", "Cashier"])
def test_other_roles_get_403(client, seeded, role):
    assert add_supplier(client, role=role).status_code == 403


def test_login_required(client, seeded):
    assert client.post("/api/suppliers", json={"name": "X"}).status_code == 401


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 121}])
def test_invalid_name_is_400(client, seeded, body):
    r = client.post("/api/suppliers", json=body, headers=auth("u1", "Manager"))
    assert r.status_code == 400


def test_receive_a_batch_on_an_empty_database(client):
    manager = auth("m1", "Manager")
    assert client.get("/api/suppliers", headers=manager).json() == []
    supplier = add_supplier(client, "Fresh Farms").json()
    product = client.post("/api/products", headers=manager, json={
        "sku": "TOM-01", "name": "Tomato", "category": "Vegetables", "unit": "kg",
        "shelfLifeDays": 5, "storageType": "Chilled", "tempMin": 8, "tempMax": 12,
        "costPrice": 20, "sellingPrice": 30,
    }).json()
    r = client.post("/api/batches", headers=auth("s1", "Inventory Staff"), json={
        "productId": product["productId"], "supplierId": supplier["supplierId"], "quantity": 10,
        "unit": "kg", "receivedAt": datetime.now(timezone.utc).isoformat(),
        "expiryDate": str(store_today() + timedelta(days=5)),
    })
    assert r.status_code == 201 and r.json()["newStock"] == 10
    restock = client.post("/api/restocks", headers=auth("s1", "Inventory Staff"),
                          json={"productId": product["productId"], "quantity": 2})
    assert restock.status_code == 201 and restock.json()["newStock"] == 12
