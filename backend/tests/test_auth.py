"""SEC-1 login (TC-AUTH-01). Test IDs follow the SRS v1.0 RTM."""

from tests.conftest import login, make_user


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_tc_auth_01_valid_login_creates_session(client):
    make_user("staff1", "Inventory Staff")
    r = login(client, "staff1")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "Inventory Staff" and body["userId"] == "staff1"
    assert body["name"] == "staff1" and body["token"] and body["expiresIn"] > 0

    me = client.get("/api/auth/me", headers=bearer(body["token"]))
    assert me.status_code == 200 and me.json()["userId"] == "staff1"


def test_tc_auth_01_wrong_password_generic_401(client):
    make_user("staff1", "Inventory Staff")
    r = login(client, "staff1", "wrong-password")
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid user ID or password"


def test_tc_auth_01_unknown_user_same_error(client):
    make_user("staff1", "Inventory Staff")
    wrong_pw = login(client, "staff1", "wrong-password")
    unknown = login(client, "ghost99", "anything")
    assert unknown.status_code == wrong_pw.status_code == 401
    assert unknown.json() == wrong_pw.json()  # does not reveal which field was wrong


def test_tc_auth_01_deactivated_user_cannot_log_in(client):
    make_user("old1", "Cashier", active=False)
    r = login(client, "old1")
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid user ID or password"


def test_tc_auth_01_logout_ends_session(client):
    make_user("staff1", "Inventory Staff")
    h = bearer(login(client, "staff1").json()["token"])
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_tc_auth_01_two_logins_are_separate_sessions(client):
    make_user("staff1", "Inventory Staff")
    phone = bearer(login(client, "staff1").json()["token"])
    tablet = bearer(login(client, "staff1").json()["token"])
    client.post("/api/auth/logout", headers=phone)
    assert client.get("/api/auth/me", headers=tablet).status_code == 200


def test_tc_auth_01_token_without_session_is_refused(client):
    from app.rbac import create_access_token

    make_user("staff1", "Inventory Staff")
    forged = create_access_token("staff1", "Admin", "x")  # signed, but no login behind it
    assert client.get("/api/auth/me", headers=bearer(forged)).status_code == 401


def test_tc_auth_01_no_token_or_bad_token_401(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=bearer("not.a.token")).status_code == 401


def test_tc_auth_01_missing_field_400(client):
    r = client.post("/api/auth/login", json={"userId": "staff1"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION"
