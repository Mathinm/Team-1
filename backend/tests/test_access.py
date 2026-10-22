"""SEC-2: role-based access control on every endpoint (TC-AUTH-02). SRS v1.0 test IDs."""

import logging
import re

import pytest
from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import auth

# Endpoints anyone may call. Device endpoints use a device key instead of a login, and
# still answer 401 without one. Add a path here ONLY if it must work without logging in.
PUBLIC = {("GET", "/api/health"), ("POST", "/api/auth/login")}

API_ROUTES = sorted(
    (method, route.path)
    for route in app.routes
    if isinstance(route, APIRoute) and route.path.startswith("/api")
    for method in route.methods
)


@pytest.mark.parametrize("method,path", [r for r in API_ROUTES if r not in PUBLIC])
def test_tc_auth_02_every_api_endpoint_refuses_anonymous_calls(client, method, path):
    url = re.sub(r"\{[^}]+\}", "1", path)
    assert client.request(method, url).status_code == 401, f"{method} {path} is not protected"


@pytest.mark.parametrize("role,menu", [
    ("Cashier", ["sales"]),
    ("Inventory Staff", ["products", "stock"]),
    ("Manager", ["products", "stock"]),
    ("Admin", ["products", "stock", "sales", "users"]),
])
def test_tc_auth_02_menu_shows_only_the_role_screens(client, role, menu):
    me = client.get("/api/auth/me", headers=auth("u1", role)).json()
    assert me["role"] == role and me["menu"] == menu


def test_tc_auth_02_out_of_role_call_is_403_and_logged(client, seeded, caplog):
    with caplog.at_level(logging.WARNING, logger="pms.security"):
        r = client.post("/api/sales", json={"sku": "TOM-01", "quantity": 1},
                        headers=auth("mgr1", "Manager"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert any("ACCESS_DENIED" in m and "user=mgr1" in m and "path=/api/sales" in m
               for m in caplog.messages)


def test_tc_auth_02_role_change_applies_on_next_request(client, seeded):
    h = auth("u2", "Cashier")
    body = {"sku": "TOM-01", "quantity": 1}
    assert client.post("/api/sales", json=body, headers=h).status_code == 201
    auth("u2", "Manager")  # Admin changes the role; the same token is now a Manager's
    assert client.post("/api/sales", json=body, headers=h).status_code == 403
