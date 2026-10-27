"""NFR-10: two-factor login for Manager and Admin by emailed code (TC-SEC-07).

Test Case Document steps (TC-NFR-13): log in as a Manager with the right password, enter a wrong
code (rejected), then the right code (access granted).
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth.otp import mask_email
from app.config import get_settings
from app.models import User
from app.notify import OUTBOX
from tests.conftest import PASSWORD, make_user


@pytest.fixture(autouse=True)
def empty_outbox():
    OUTBOX.clear()
    yield
    OUTBOX.clear()


def login2(client, user_id, code=None, password=PASSWORD):
    body = {"userId": user_id, "password": password}
    if code is not None:
        body["otpCode"] = code
    return client.post("/api/auth/login", json=body)


def emailed_code(to):
    """The code in the last email sent to `to`."""
    mail = [m for m in OUTBOX if m.to == to][-1]
    return re.search(r"\b(\d{6})\b", mail.body).group(1)


def wrong(code):
    return "000000" if code != "000000" else "111111"


def error_code(r):
    return r.json()["error"]["code"]


def ask_for_code(client, user_id="manager1"):
    r = login2(client, user_id)
    assert r.status_code == 401 and error_code(r) == "OTP_REQUIRED"
    return emailed_code(f"{user_id}@example.com")


def age_code(db, user_id, minutes):
    """Pretend the code was sent `minutes` ago."""
    db.expire_all()
    user = db.scalar(select(User).where(User.user_id == user_id))
    back = timedelta(minutes=minutes)
    user.otp_sent_at = user.otp_sent_at - back
    user.otp_expires_at = user.otp_expires_at - back
    db.commit()


# ---- TC-SEC-07 -----------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["Manager", "Admin"])
def test_tc_sec_07_password_alone_is_not_enough_and_a_code_is_emailed(client, role):
    make_user("boss1", role)
    r = login2(client, "boss1")
    assert r.status_code == 401 and error_code(r) == "OTP_REQUIRED"
    assert "token" not in r.json()
    assert r.json()["error"]["details"] == {"sentTo": "b****@example.com"}
    assert len(OUTBOX) == 1 and OUTBOX[0].to == "boss1@example.com"
    assert OUTBOX[0].subject == "Your PMS login code"


def test_tc_sec_07_wrong_code_rejected_then_correct_code_grants_access(client):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    bad = login2(client, "manager1", wrong(code))
    assert bad.status_code == 401 and error_code(bad) == "INVALID_OTP"
    ok = login2(client, "manager1", code)
    assert ok.status_code == 200 and ok.json()["role"] == "Manager"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {ok.json()['token']}"})
    assert me.status_code == 200


def test_tc_sec_07_other_roles_need_no_code_and_get_no_email(client):
    make_user("cashier1", "Cashier")
    make_user("staff1", "Inventory Staff")
    assert login2(client, "cashier1").status_code == 200
    assert login2(client, "staff1").status_code == 200
    assert len(OUTBOX) == 0


def test_wrong_password_sends_no_email(client):
    make_user("manager1", "Manager")
    r = login2(client, "manager1", password="Wrong-Pass-1")
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"
    assert len(OUTBOX) == 0


def test_right_code_with_wrong_password_is_refused(client):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    r = login2(client, "manager1", code, password="Wrong-Pass-1")
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"


# ---- the code ------------------------------------------------------------------------------
def test_a_code_works_only_once(client):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    assert login2(client, "manager1", code).status_code == 200
    again = login2(client, "manager1", code)
    assert again.status_code == 401 and error_code(again) == "INVALID_OTP"


def test_code_expires_after_5_minutes(client, db):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    age_code(db, "manager1", 6)
    r = login2(client, "manager1", code)
    assert r.status_code == 401 and error_code(r) == "INVALID_OTP"


def test_code_with_spaces_is_accepted(client):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    assert login2(client, "manager1", f"{code[:3]} {code[3:]}").status_code == 200


@pytest.mark.parametrize("bad", ["12345", "1234567", "abcdef"])
def test_malformed_codes_are_rejected(client, bad):
    make_user("manager1", "Manager")
    ask_for_code(client)
    r = login2(client, "manager1", bad)
    assert r.status_code == 401 and error_code(r) == "INVALID_OTP"


def test_code_before_any_email_is_rejected(client):
    make_user("manager1", "Manager")
    r = login2(client, "manager1", "123456")
    assert r.status_code == 401 and error_code(r) == "INVALID_OTP"


def test_only_a_hash_of_the_code_is_stored(client, db):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    db.expire_all()
    user = db.scalar(select(User).where(User.user_id == "manager1"))
    assert user.otp_code_hash and code not in user.otp_code_hash


def test_code_is_never_written_to_the_logs_when_smtp_is_used(client, caplog, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr("app.notify.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    caplog.set_level("DEBUG")
    make_user("manager1", "Manager")
    login2(client, "manager1")
    assert len(sent) == 1 and sent[0]["To"] == "manager1@example.com"
    code = re.search(r"\b(\d{6})\b", sent[0].get_content()).group(1)
    assert code not in caplog.text
    assert login2(client, "manager1", code).status_code == 200


# ---- resend --------------------------------------------------------------------------------
def test_asking_again_within_30_seconds_sends_no_second_email(client):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    assert login2(client, "manager1").status_code == 401
    assert len(OUTBOX) == 1
    assert login2(client, "manager1", code).status_code == 200  # first code still works


def test_asking_again_later_sends_a_new_code_and_the_old_one_stops_working(client, db):
    make_user("manager1", "Manager")
    old = ask_for_code(client)
    age_code(db, "manager1", 1)
    new = ask_for_code(client)
    assert len(OUTBOX) == 2
    if new != old:
        assert login2(client, "manager1", old).status_code == 401
    assert login2(client, "manager1", new).status_code == 200


# ---- lockout (SEC-3) -----------------------------------------------------------------------
def test_five_wrong_codes_lock_the_account(client):
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    results = [login2(client, "manager1", wrong(code)).status_code for _ in range(5)]
    assert results == [401, 401, 401, 401, 423]
    r = login2(client, "manager1", code)
    assert r.status_code == 423 and error_code(r) == "ACCOUNT_LOCKED"


def test_asking_for_a_code_does_not_count_as_a_failure(client, db):
    make_user("manager1", "Manager")
    for _ in range(6):
        assert login2(client, "manager1").status_code == 401
    db.expire_all()
    assert db.scalar(select(User.failed_logins).where(User.user_id == "manager1")) == 0


def test_locked_account_gets_no_email(client):
    make_user("manager1", "Manager")
    for _ in range(5):
        login2(client, "manager1", password="Wrong-Pass-1")
    assert login2(client, "manager1").status_code == 423
    assert len(OUTBOX) == 0


# ---- settings ------------------------------------------------------------------------------
def test_2fa_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "require_2fa", False)
    make_user("manager1", "Manager")
    assert login2(client, "manager1").status_code == 200
    assert len(OUTBOX) == 0


def test_mask_email():
    assert mask_email("manager1@example.com") == "m*******@example.com"
    assert mask_email("a@b.com") == "a*@b.com"


def test_expiry_is_configurable(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "otp_expire_minutes", 10)
    make_user("manager1", "Manager")
    code = ask_for_code(client)
    db.expire_all()
    user = db.scalar(select(User).where(User.user_id == "manager1"))
    expires = user.otp_expires_at.replace(tzinfo=timezone.utc)
    left = expires - datetime.now(timezone.utc)
    assert timedelta(minutes=9) < left <= timedelta(minutes=10)
    assert login2(client, "manager1", code).status_code == 200
