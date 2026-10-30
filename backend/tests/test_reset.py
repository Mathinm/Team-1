"""SEC-5: password reset by email (TC-AUTH-05).

Test Case Document steps: TC-AUTH-13 (forgot password -> emailed link -> new password works,
old one rejected) and TC-AUTH-14 (a used link is rejected).
"""

import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import PasswordReset, User
from app.notify import OUTBOX
from tests.conftest import PASSWORD, auth, login, make_user

NEW_PASSWORD = "N3w-Passw0rd!"
SENT = "If that user ID exists, a reset link has been sent to its registered email."
REQUEST = "/api/auth/password-reset"
CONFIRM = "/api/auth/password-reset/confirm"


@pytest.fixture(autouse=True)
def empty_outbox():
    OUTBOX.clear()
    yield
    OUTBOX.clear()


def ask(client, user_id="staff1"):
    return client.post(REQUEST, json={"userId": user_id})


def link_token(to="staff1@example.com"):
    """The token from the last reset email sent to `to`."""
    mail = [m for m in OUTBOX if m.to == to][-1]
    return re.search(r"/reset-password\?token=([A-Za-z0-9_\-]+)", mail.body).group(1)


def confirm(client, token, password=NEW_PASSWORD):
    return client.post(CONFIRM, json={"token": token, "newPassword": password})


def error_code(r):
    return r.json()["error"]["code"]


def age_links(db, user_id, minutes):
    """Pretend every link of this user was created `minutes` ago."""
    db.expire_all()
    pk = db.scalar(select(User.id).where(User.user_id == user_id))
    for reset in db.scalars(select(PasswordReset).where(PasswordReset.user_pk == pk)):
        reset.created_at -= timedelta(minutes=minutes)
        reset.expires_at -= timedelta(minutes=minutes)
    db.commit()


# ---- TC-AUTH-05 / TC-AUTH-13 ---------------------------------------------------------------
def test_tc_auth_05_reset_email_sent_and_new_password_works_old_rejected(client):
    make_user("staff1", "Inventory Staff")
    r = ask(client)
    assert r.status_code == 202 and r.json() == {"message": SENT}
    assert len(OUTBOX) == 1
    mail = OUTBOX[0]
    assert mail.to == "staff1@example.com" and mail.subject == "Reset your PMS password"
    assert "http://localhost:5173/reset-password?token=" in mail.body

    r = confirm(client, link_token())
    assert r.status_code == 200
    assert login(client, "staff1", NEW_PASSWORD).status_code == 200
    old = login(client, "staff1", PASSWORD)
    assert old.status_code == 401 and error_code(old) == "INVALID_CREDENTIALS"


def test_tc_auth_14_used_link_is_rejected(client):
    make_user("staff1", "Inventory Staff")
    ask(client)
    token = link_token()
    assert confirm(client, token).status_code == 200
    again = confirm(client, token, "Another-Pass-9")
    assert again.status_code == 400 and error_code(again) == "RESET_LINK_INVALID"
    assert login(client, "staff1", NEW_PASSWORD).status_code == 200  # unchanged by 2nd try


# ---- no user enumeration -------------------------------------------------------------------
def test_unknown_user_gets_the_same_answer_and_no_email(client):
    r = ask(client, "ghost99")
    assert r.status_code == 202 and r.json() == {"message": SENT}
    assert len(OUTBOX) == 0


def test_deactivated_user_gets_no_email(client):
    make_user("old1", "Cashier", active=False)
    assert ask(client, "old1").status_code == 202
    assert len(OUTBOX) == 0


def test_missing_user_id_is_400(client):
    assert client.post(REQUEST, json={}).status_code == 400


# ---- the link ------------------------------------------------------------------------------
def test_link_expires_after_30_minutes(client, db):
    make_user("staff1", "Inventory Staff")
    ask(client)
    token = link_token()
    age_links(db, "staff1", 31)
    r = confirm(client, token)
    assert r.status_code == 400 and error_code(r) == "RESET_LINK_INVALID"
    assert login(client, "staff1", PASSWORD).status_code == 200  # password unchanged


def test_made_up_token_is_rejected(client):
    r = confirm(client, "not-a-real-token")
    assert r.status_code == 400 and error_code(r) == "RESET_LINK_INVALID"


def test_only_a_hash_of_the_token_is_stored(client, db):
    make_user("staff1", "Inventory Staff")
    ask(client)
    token = link_token()
    stored = db.scalar(select(PasswordReset.token_hash))
    assert stored and token not in stored and len(stored) == 64


def test_new_link_cancels_the_older_one(client, db):
    make_user("staff1", "Inventory Staff")
    ask(client)
    first = link_token()
    age_links(db, "staff1", 2)  # past the 60 s resend wait
    ask(client)
    second = link_token()
    assert len(OUTBOX) == 2 and first != second
    assert confirm(client, first).status_code == 400
    assert confirm(client, second).status_code == 200


def test_asking_again_within_60_seconds_sends_no_second_email(client):
    make_user("staff1", "Inventory Staff")
    ask(client)
    token = link_token()
    assert ask(client).json() == {"message": SENT}
    assert len(OUTBOX) == 1
    assert confirm(client, token).status_code == 200  # the first link still works


@pytest.mark.parametrize("short", ["", "1234567"])
def test_new_password_must_be_at_least_8_characters(client, short):
    make_user("staff1", "Inventory Staff")
    ask(client)
    r = confirm(client, link_token(), short)
    assert r.status_code == 400
    assert confirm(client, link_token()).status_code == 200  # link not used up by the 400


# ---- after the reset -----------------------------------------------------------------------
def test_reset_logs_the_user_out_everywhere(client):
    make_user("staff1", "Inventory Staff")
    headers = auth("staff1", "Inventory Staff")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    ask(client)
    confirm(client, link_token())
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_new_password_is_stored_as_argon2_hash(client, db):
    make_user("staff1", "Inventory Staff")
    ask(client)
    confirm(client, link_token())
    db.expire_all()
    stored = db.scalar(select(User.password_hash).where(User.user_id == "staff1"))
    assert stored.startswith("$argon2id$") and NEW_PASSWORD not in stored


def test_locked_account_stays_locked_after_reset(client):
    make_user("staff1", "Inventory Staff")
    for _ in range(5):
        login(client, "staff1", "wrong-password")
    ask(client)
    assert confirm(client, link_token()).status_code == 200
    r = login(client, "staff1", NEW_PASSWORD)
    assert r.status_code == 423  # SEC-3: only an Admin unlocks


def test_user_deactivated_after_the_email_cannot_use_the_link(client):
    make_user("staff1", "Inventory Staff")
    ask(client)
    token = link_token()
    admin = auth("admin1", "Admin")
    client.patch("/api/users/staff1/deactivate", headers=admin)
    r = confirm(client, token)
    assert r.status_code == 400 and error_code(r) == "RESET_LINK_INVALID"


def test_manager_still_needs_the_2fa_code_after_a_reset(client):
    make_user("manager1", "Manager")
    ask(client, "manager1")
    confirm(client, link_token("manager1@example.com"))
    r = login(client, "manager1", NEW_PASSWORD)
    assert r.status_code == 401 and error_code(r) == "OTP_REQUIRED"


def test_link_and_token_never_written_to_the_logs(client, caplog, monkeypatch):
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
    make_user("staff1", "Inventory Staff")
    ask(client)
    token = re.search(r"token=([A-Za-z0-9_\-]+)", sent[0].get_content()).group(1)
    confirm(client, token)
    assert token not in caplog.text
    assert "PASSWORD_RESET_DONE user=staff1" in caplog.text


def test_frontend_url_is_configurable(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "frontend_url", "https://pms.example.com/")
    make_user("staff1", "Inventory Staff")
    ask(client)
    assert "https://pms.example.com/reset-password?token=" in OUTBOX[0].body
