"""SEC-4: Admin user management (TC-AUTH-04). SRS v1.0 test IDs."""

import logging

import pytest

from tests.conftest import auth, login

NEW = {"userId": "cash2", "name": "Cashier Two", "email": "cash2@example.com",
       "role": "Cashier", "password": "Cash2Pass!"}


@pytest.fixture()
def admin(Session):
    return auth("admin", "Admin")


def test_tc_auth_04_admin_creates_user_who_can_log_in(client, admin):
    r = client.post("/api/users", json=NEW, headers=admin)
    assert r.status_code == 201
    assert r.json() == {"userId": "cash2", "name": "Cashier Two", "email": "cash2@example.com",
                        "role": "Cashier", "active": True, "locked": False,
                        "storeId": 1}
    r = login(client, "cash2", "Cash2Pass!")
    assert r.status_code == 200 and r.json()["role"] == "Cashier"


def test_tc_auth_04_duplicate_user_id_409(client, admin):
    client.post("/api/users", json=NEW, headers=admin)
    r = client.post("/api/users", json=NEW, headers=admin)
    assert r.status_code == 409 and r.json()["error"]["message"] == "User ID already exists"


def test_tc_auth_04_admin_edits_and_assigns_role(client, admin):
    client.post("/api/users", json=NEW, headers=admin)
    r = client.put("/api/users/cash2", json={"role": "Inventory Staff", "name": "C Two"},
                   headers=admin)
    assert r.status_code == 200
    assert r.json()["role"] == "Inventory Staff" and r.json()["name"] == "C Two"
    assert login(client, "cash2", "Cash2Pass!").json()["role"] == "Inventory Staff"


def test_tc_auth_04_deactivate_refuses_login_ends_sessions_keeps_record(client, admin):
    client.post("/api/users", json=NEW, headers=admin)
    token = login(client, "cash2", "Cash2Pass!").json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    r = client.patch("/api/users/cash2/deactivate", headers=admin)
    assert r.status_code == 200 and r.json()["active"] is False
    assert login(client, "cash2", "Cash2Pass!").status_code == 401  # login refused
    assert client.get("/api/auth/me", headers=h).status_code == 401  # open session ended
    users = client.get("/api/users", headers=admin).json()
    assert {"userId": "cash2", "active": False}.items() <= next(
        u for u in users if u["userId"] == "cash2").items()  # record kept

    assert client.patch("/api/users/cash2/activate", headers=admin).json()["active"] is True
    assert login(client, "cash2", "Cash2Pass!").status_code == 200


@pytest.mark.parametrize("role", ["Manager", "Inventory Staff", "Cashier"])
def test_tc_auth_04_non_admins_get_403(client, role):
    h = auth("u1", role)
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.post("/api/users", json=NEW, headers=h).status_code == 403
    assert client.put("/api/users/u1", json={"name": "x"}, headers=h).status_code == 403
    assert client.patch("/api/users/u1/deactivate", headers=h).status_code == 403
    assert client.patch("/api/users/u1/activate", headers=h).status_code == 403


@pytest.mark.parametrize("bad", [
    {"role": "Superuser"}, {"email": "not-an-email"}, {"password": "short"},
    {"userId": "a b"}, {"name": ""},
])
def test_tc_auth_04_invalid_input_is_400(client, admin, bad):
    assert client.post("/api/users", json={**NEW, **bad}, headers=admin).status_code == 400


def test_tc_auth_04_admin_cannot_lock_themselves_out(client, admin):
    assert client.patch("/api/users/admin/deactivate", headers=admin).status_code == 400
    r = client.put("/api/users/admin", json={"role": "Cashier"}, headers=admin)
    assert r.status_code == 400


def test_tc_auth_04_unknown_user_404(client, admin):
    assert client.put("/api/users/nobody", json={"name": "x"}, headers=admin).status_code == 404


def test_tc_auth_04_changes_are_audit_logged_without_passwords(client, admin, caplog):
    with caplog.at_level(logging.INFO, logger="pms.audit"):
        client.post("/api/users", json=NEW, headers=admin)
        client.patch("/api/users/cash2/deactivate", headers=admin)
    assert any("USER_CREATED by=admin user=cash2" in m for m in caplog.messages)
    assert any("USER_DEACTIVATED by=admin user=cash2" in m for m in caplog.messages)
    assert "Cash2Pass!" not in caplog.text
