"""NFR-9: passwords are stored only as salted hashes (TC-SEC-06). SRS v1.0 test IDs."""

import logging

from argon2 import PasswordHasher
from sqlalchemy import select

from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.models import User
from tests.conftest import PASSWORD, login, make_user


def test_tc_sec_06_same_password_gives_different_salted_hashes(client, db):
    make_user("userA", "Cashier", password="SamePass123!")
    make_user("userB", "Cashier", password="SamePass123!")
    a, b = (db.scalar(select(User).where(User.user_id == u)) for u in ("userA", "userB"))
    assert a.password_hash != b.password_hash  # a different random salt each time
    assert a.password_hash.startswith("$argon2id$")
    assert "SamePass123!" not in a.password_hash  # no plaintext


def test_tc_sec_06_no_plaintext_anywhere_in_users_table(client, db):
    make_user("userA", "Cashier", password="Visible-If-Bad-1")
    row = db.execute(select(User.__table__)).mappings().one()
    assert all("Visible-If-Bad-1" not in str(v) for v in row.values())


def test_tc_sec_06_hash_verifies_only_the_right_password():
    h = hash_password("Correct-Horse-1")
    assert verify_password("Correct-Horse-1", h)
    assert not verify_password("correct-horse-1", h)
    assert not verify_password("anything", "not-a-hash")


def test_tc_sec_06_passwords_never_logged(client, caplog):
    make_user("cash2", "Cashier")
    with caplog.at_level(logging.DEBUG):
        assert login(client, "cash2").status_code == 200
        assert login(client, "cash2", "Wrong-Pass-123").status_code == 401
    assert PASSWORD not in caplog.text
    assert "Wrong-Pass-123" not in caplog.text


def test_tc_sec_06_weak_old_hash_is_upgraded_on_login(client, db):
    weak = PasswordHasher(time_cost=1, memory_cost=8192).hash(PASSWORD)
    make_user("old1", "Cashier")
    user = db.scalar(select(User).where(User.user_id == "old1"))
    user.password_hash = weak
    db.commit()
    assert needs_rehash(weak)

    assert login(client, "old1").status_code == 200
    db.expire_all()
    new_hash = db.scalar(select(User.password_hash).where(User.user_id == "old1"))
    assert new_hash != weak and not needs_rehash(new_hash)
