"""NFR-11: employee data encrypted at rest (TC-SEC-08).

Test Case Document style: inspect the users table directly -> names and emails are not readable;
the Admin screen still shows them in plain text.
"""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app import crypto
from app.config import get_settings
from app.crypto import PREFIX, DecryptionError, decrypt, encrypt
from app.notify import OUTBOX
from tests.conftest import auth, login

NEW = {"userId": "cash2", "name": "Ravi Kumar", "email": "ravi.kumar@example.com",
       "role": "Cashier", "password": "Cash2Pass!"}


@pytest.fixture(autouse=True)
def fresh_key_cache():
    crypto.reset_key_cache()
    yield
    crypto.reset_key_cache()


def raw_row(db, user_id):
    """What someone reading the database directly (or a backup) sees."""
    return db.execute(text("SELECT name, email FROM users WHERE user_id = :u"),
                      {"u": user_id}).one()


# ---- TC-SEC-08 -----------------------------------------------------------------------------
def test_tc_sec_08_name_and_email_are_not_readable_in_the_database(client, db):
    client.post("/api/users", json=NEW, headers=auth("admin1", "Admin"))
    name, email = raw_row(db, "cash2")
    assert name.startswith(PREFIX) and email.startswith(PREFIX)
    for secret in ("Ravi", "Kumar", "ravi.kumar", "example.com"):
        assert secret not in name and secret not in email


def test_tc_sec_08_admin_sees_name_and_email_in_plain_text(client):
    admin = auth("admin1", "Admin")
    client.post("/api/users", json=NEW, headers=admin)
    users = {u["userId"]: u for u in client.get("/api/users", headers=admin).json()}
    assert users["cash2"]["name"] == "Ravi Kumar"
    assert users["cash2"]["email"] == "ravi.kumar@example.com"


def test_tc_sec_08_other_roles_cannot_read_employee_data(client):
    for role in ("Manager", "Inventory Staff", "Cashier"):
        r = client.get("/api/users", headers=auth(f"u-{role[:3]}", role))
        assert r.status_code == 403


def test_admin_reads_are_written_to_the_audit_log(client, caplog):
    caplog.set_level("INFO")
    client.get("/api/users", headers=auth("admin1", "Admin"))
    assert "EMPLOYEE_DATA_READ by=admin1" in caplog.text


def test_edited_name_and_email_are_stored_encrypted_too(client, db):
    admin = auth("admin1", "Admin")
    client.post("/api/users", json=NEW, headers=admin)
    r = client.put("/api/users/cash2", json={"name": "Ravi K", "email": "rk@example.com"},
                   headers=admin)
    assert r.json()["name"] == "Ravi K" and r.json()["email"] == "rk@example.com"
    name, email = raw_row(db, "cash2")
    assert "Ravi" not in name and "rk@" not in email and email.startswith(PREFIX)


def test_same_email_twice_gives_different_ciphertext(client, db):
    admin = auth("admin1", "Admin")
    client.post("/api/users", json=NEW, headers=admin)
    client.post("/api/users", json={**NEW, "userId": "cash3"}, headers=admin)
    assert raw_row(db, "cash2").email != raw_row(db, "cash3").email  # random IV per value


# ---- the rest of the app keeps working with plain text --------------------------------------
def test_login_returns_the_decrypted_name(client):
    client.post("/api/users", json=NEW, headers=auth("admin1", "Admin"))
    r = login(client, "cash2", "Cash2Pass!")
    assert r.status_code == 200 and r.json()["name"] == "Ravi Kumar"


def test_emails_go_to_the_decrypted_address(client):
    OUTBOX.clear()
    client.post("/api/users", json=NEW, headers=auth("admin1", "Admin"))
    client.post("/api/auth/password-reset", json={"userId": "cash2"})
    assert OUTBOX[-1].to == "ravi.kumar@example.com"
    assert "Hello Ravi Kumar" in OUTBOX[-1].body
    OUTBOX.clear()


# ---- keys ----------------------------------------------------------------------------------
def test_round_trip():
    assert decrypt(encrypt("Asha Admin")) == "Asha Admin"
    assert decrypt(encrypt("")) == ""
    assert decrypt(encrypt("ನಮಸ್ಕಾರ")) == "ನಮಸ್ಕಾರ"  # non-English names are fine


def test_wrong_key_cannot_decrypt(monkeypatch):
    stored = encrypt("ravi.kumar@example.com")
    monkeypatch.setattr(get_settings(), "data_encryption_key", Fernet.generate_key().decode())
    crypto.reset_key_cache()
    with pytest.raises(DecryptionError):
        decrypt(stored)


def test_configured_key_is_used(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "data_encryption_key", key)
    crypto.reset_key_cache()
    stored = encrypt("Sita Staff")
    assert Fernet(key.encode()).decrypt(stored[len(PREFIX):].encode()) == b"Sita Staff"


def test_key_rotation_old_values_still_readable(monkeypatch):
    old = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "data_encryption_key", old)
    crypto.reset_key_cache()
    stored_with_old = encrypt("Kiran Cashier")

    new = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "data_encryption_key", f"{new},{old}")
    crypto.reset_key_cache()
    assert decrypt(stored_with_old) == "Kiran Cashier"  # old key still decrypts
    fresh = encrypt("Kiran Cashier")
    assert Fernet(new.encode()).decrypt(fresh[len(PREFIX):].encode()) == b"Kiran Cashier"


# ---- rows written before NFR-11 ------------------------------------------------------------
def test_plain_text_rows_from_before_nfr_11_are_read_and_encrypted_when_changed(client, db):
    admin = auth("admin1", "Admin")
    client.post("/api/users", json=NEW, headers=admin)
    db.execute(text("UPDATE users SET name = 'Old Name', email = 'old@example.com' "
                    "WHERE user_id = 'cash2'"))
    db.commit()
    users = {u["userId"]: u for u in client.get("/api/users", headers=admin).json()}
    assert users["cash2"]["email"] == "old@example.com"  # still readable

    client.put("/api/users/cash2", json={"name": "New Name"}, headers=admin)
    name, email = raw_row(db, "cash2")
    assert name.startswith(PREFIX) and "New Name" not in name  # changed field now encrypted
    assert email == "old@example.com"  # untouched field stays as it was until changed
