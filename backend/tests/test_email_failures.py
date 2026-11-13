"""Sprint 3 fixes from the 12 Nov test run: login, 2FA and password reset when email fails.

T3  The login code can't be emailed (wrong SMTP password, network down): a clean 503
    "Couldn't send the login code, try again", not a 500 "Server error".
N4  Password reset while email is down: the same 202 as for an unknown user ID, so the answer
    does not reveal which user IDs exist; the failure is written to the audit log.
T5  Password reset refuses the current password as the new one (400 SAME_PASSWORD).
"""

import logging
import re
import smtplib

import pytest
from sqlalchemy import select

from app import notify
from app.config import get_settings
from app.models import PasswordReset, User
from app.notify import OUTBOX, EmailError, send_email
from tests.conftest import PASSWORD, login, make_user

REQUEST = "/api/auth/password-reset"
CONFIRM = "/api/auth/password-reset/confirm"
SENT = "If that user ID exists, a reset link has been sent to its registered email."


@pytest.fixture(autouse=True)
def empty_outbox():
    OUTBOX.clear()
    yield
    OUTBOX.clear()


class BrokenSMTP:
    """Stands in for smtplib.SMTP: fails the way a real server does."""

    error: Exception = smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    def __init__(self, *args, **kwargs):
        raise BrokenSMTP.error


@pytest.fixture()
def email_down(monkeypatch):
    """SMTP is configured but every send fails (like a wrong Gmail app password)."""
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    monkeypatch.setattr(notify.smtplib, "SMTP", BrokenSMTP)


def email_back_up(monkeypatch):
    """SMTP fixed again: back to "write to the log", which the tests can read in OUTBOX."""
    monkeypatch.setattr(get_settings(), "smtp_host", "")


def error_code(r):
    return r.json()["error"]["code"]


# ---- the shared mail function ------------------------------------------------------------------
@pytest.mark.parametrize("error", [
    smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted"),
    ConnectionRefusedError("connection refused"),
    TimeoutError("timed out"),
])
def test_send_email_raises_email_error_and_logs_the_reason(email_down, caplog, error):
    BrokenSMTP.error = error
    with caplog.at_level(logging.WARNING, logger="pms.email"):
        with pytest.raises(EmailError):
            send_email("x@example.com", "Subject", "secret body 123456")
    assert any("EMAIL FAILED" in m for m in caplog.messages)
    assert not any("123456" in m for m in caplog.messages)  # the body (codes) is never logged


# ---- T3: login code email fails ---------------------------------------------------------------
def test_t3_login_code_email_failure_is_503_not_500(client, db, email_down):
    make_user("manager1", "Manager")
    r = login(client, "manager1")
    assert r.status_code == 503
    assert error_code(r) == "EMAIL_UNAVAILABLE"
    assert r.json()["error"]["message"] == "Couldn't send the login code, try again in a minute"
    user = db.scalar(select(User).where(User.user_id == "manager1"))
    assert user.otp_code_hash is None and user.otp_sent_at is None  # no code nobody received
    assert user.failed_logins == 0  # the password was right: not counted as a failure


def test_t3_after_email_works_again_the_code_is_sent_at_once(client, email_down, monkeypatch):
    make_user("manager1", "Manager")
    assert login(client, "manager1").status_code == 503
    email_back_up(monkeypatch)
    r = login(client, "manager1")  # no 30-second resend wait after a failed send
    assert r.status_code == 401 and error_code(r) == "OTP_REQUIRED"
    code = re.search(r"\b(\d{6})\b", OUTBOX[-1].body).group(1)
    ok = client.post("/api/auth/login",
                     json={"userId": "manager1", "password": PASSWORD, "otpCode": code})
    assert ok.status_code == 200


def test_t3_wrong_password_still_401_when_email_is_down(client, email_down):
    make_user("manager1", "Manager")
    r = login(client, "manager1", "wrong-password")
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"


# ---- N4: reset while email is down ------------------------------------------------------------
def test_n4_reset_answer_is_the_same_for_real_and_unknown_users_when_email_is_down(
        client, email_down):
    make_user("staff1", "Inventory Staff")
    real = client.post(REQUEST, json={"userId": "staff1"})
    unknown = client.post(REQUEST, json={"userId": "ghost99"})
    assert real.status_code == unknown.status_code == 202
    assert real.json() == unknown.json() == {"message": SENT}


def test_n4_failed_reset_email_is_audit_logged_and_leaves_no_link(client, db, email_down,
                                                                  caplog):
    make_user("staff1", "Inventory Staff")
    with caplog.at_level(logging.INFO, logger="pms.audit"):
        client.post(REQUEST, json={"userId": "staff1"})
    assert any("PASSWORD_RESET_REQUESTED user=staff1 result=email-failed" in m
               for m in caplog.messages)
    assert db.scalars(select(PasswordReset)).all() == []  # no link that nobody received


def test_n4_after_email_works_again_a_link_is_sent_at_once(client, email_down, monkeypatch):
    make_user("staff1", "Inventory Staff")
    client.post(REQUEST, json={"userId": "staff1"})
    email_back_up(monkeypatch)
    assert client.post(REQUEST, json={"userId": "staff1"}).status_code == 202
    assert [m.to for m in OUTBOX] == ["staff1@example.com"]  # not held back by the resend wait


# ---- T5: new password = current password ------------------------------------------------------
def reset_token(client, user_id="staff1"):
    client.post(REQUEST, json={"userId": user_id})
    return re.search(r"token=([A-Za-z0-9_\-]+)", OUTBOX[-1].body).group(1)


def test_t5_reset_refuses_the_current_password(client):
    make_user("staff1", "Inventory Staff")
    token = reset_token(client)
    r = client.post(CONFIRM, json={"token": token, "newPassword": PASSWORD})
    assert r.status_code == 400
    assert error_code(r) == "SAME_PASSWORD"
    assert r.json()["error"]["message"] == (
        "New password must be different from your current password")
    assert login(client, "staff1").status_code == 200  # current password still works


def test_t5_the_link_still_works_with_a_different_password(client):
    make_user("staff1", "Inventory Staff")
    token = reset_token(client)
    client.post(CONFIRM, json={"token": token, "newPassword": PASSWORD})
    r = client.post(CONFIRM, json={"token": token, "newPassword": "Diff3rent-Pass!"})
    assert r.status_code == 200
    assert login(client, "staff1", "Diff3rent-Pass!").status_code == 200
    assert login(client, "staff1").status_code == 401  # the old one no longer works
