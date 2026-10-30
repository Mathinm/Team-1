"""SEC-3: account lockout after 5 failed logins and idle-session logout (TC-AUTH-03).

Test IDs follow the SRS v1.0 RTM. The Test Case Document steps are TC-AUTH-07 (4 failures then
success), TC-AUTH-08 (lockout after 5) and TC-AUTH-09 (idle logout).
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import User, UserSession
from tests.conftest import auth, login, make_user

LOCKED = "Account locked, contact Admin"


def failures(client, user_id, n):
    return [login(client, user_id, "wrong-password").status_code for _ in range(n)]


def failed_count(db, user_id):
    db.expire_all()
    return db.scalar(select(User.failed_logins).where(User.user_id == user_id))


# ---- lockout ------------------------------------------------------------------------------
def test_tc_auth_03_four_failures_then_success_resets_counter(client, db):
    make_user("staff1", "Inventory Staff")
    assert failures(client, "staff1", 4) == [401, 401, 401, 401]
    assert failed_count(db, "staff1") == 4
    assert login(client, "staff1").status_code == 200
    assert failed_count(db, "staff1") == 0


def test_tc_auth_03_fifth_failure_locks_account(client):
    make_user("staff1", "Inventory Staff")
    assert failures(client, "staff1", 5) == [401, 401, 401, 401, 423]
    r = login(client, "staff1")  # even the correct password is refused now
    assert r.status_code == 423
    assert r.json()["error"] == {"code": "ACCOUNT_LOCKED", "message": LOCKED, "details": None}


def test_tc_auth_03_only_consecutive_failures_count(client):
    make_user("staff1", "Inventory Staff")
    failures(client, "staff1", 4)
    assert login(client, "staff1").status_code == 200
    assert failures(client, "staff1", 4) == [401, 401, 401, 401]  # counter started again
    assert login(client, "staff1").status_code == 200


def test_tc_auth_03_unknown_user_never_shows_locked(client):
    assert set(failures(client, "ghost99", 7)) == {401}  # does not reveal that IDs exist


def test_tc_auth_03_lock_is_logged(client, caplog):
    make_user("staff1", "Inventory Staff")
    with caplog.at_level(logging.WARNING, logger="pms.security"):
        failures(client, "staff1", 5)
    assert any("ACCOUNT_LOCKED user=staff1" in m for m in caplog.messages)


def test_tc_auth_03_admin_unlocks_account(client):
    make_user("staff1", "Inventory Staff")
    failures(client, "staff1", 5)
    admin = auth("admin", "Admin")
    users = {u["userId"]: u for u in client.get("/api/users", headers=admin).json()}
    assert users["staff1"]["locked"] is True

    r = client.patch("/api/users/staff1/unlock", headers=admin)
    assert r.status_code == 200 and r.json()["locked"] is False
    assert login(client, "staff1").status_code == 200


@pytest.mark.parametrize("role", ["Manager", "Inventory Staff", "Cashier"])
def test_tc_auth_03_only_admin_can_unlock(client, role):
    make_user("staff1", "Inventory Staff")
    r = client.patch("/api/users/staff1/unlock", headers=auth("u1", role))
    assert r.status_code == 403


def test_tc_auth_03_lock_limit_is_configurable(client):
    make_user("staff1", "Inventory Staff")
    settings = get_settings()
    old = settings.max_failed_logins
    settings.max_failed_logins = 3
    try:
        assert failures(client, "staff1", 3) == [401, 401, 423]
    finally:
        settings.max_failed_logins = old


# ---- idle logout ----------------------------------------------------------------------------
def token_of(client, user_id):
    return {"Authorization": f"Bearer {login(client, user_id).json()['token']}"}


def go_idle(db, minutes):
    """Pretend the last request on every session was `minutes` ago."""
    for s in db.scalars(select(UserSession)):
        s.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    db.commit()


def test_tc_auth_03_idle_session_is_ended(client, db):
    make_user("staff1", "Inventory Staff")
    h = token_of(client, "staff1")
    go_idle(db, get_settings().idle_timeout_minutes + 1)
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Your session has ended. Please log in again."
    go_idle(db, 0)  # coming back later does not reopen it
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_tc_auth_03_active_session_stays_open(client, db):
    make_user("staff1", "Inventory Staff")
    h = token_of(client, "staff1")
    go_idle(db, get_settings().idle_timeout_minutes - 1)
    assert client.get("/api/auth/me", headers=h).status_code == 200
    db.expire_all()
    last = db.scalar(select(UserSession.last_seen_at))
    last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
    assert datetime.now(timezone.utc) - last < timedelta(minutes=1)  # activity was recorded


def test_tc_auth_03_idle_timeout_is_configurable(client, db):
    """TC-AUTH-09: idle timeout set to 1 minute for the test."""
    make_user("staff1", "Inventory Staff")
    h = token_of(client, "staff1")
    settings = get_settings()
    old = settings.idle_timeout_minutes
    settings.idle_timeout_minutes = 1
    try:
        go_idle(db, 2)
        assert client.get("/api/auth/me", headers=h).status_code == 401
    finally:
        settings.idle_timeout_minutes = old
