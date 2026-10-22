"""Create the first Admin (only when there are no users) and, optionally, the demo users."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import get_settings
from app.models import User

log = logging.getLogger("pms")

# Same logins as the frontend demo mode (frontend/src/api/mock/db.js)
DEMO_USERS = [
    ("manager1", "Manoj Manager", "Manager", "manager123"),
    ("staff1", "Sita Staff", "Inventory Staff", "staff123"),
    ("cashier1", "Kiran Cashier", "Cashier", "cashier123"),
]


def seed_users(db: Session) -> None:
    s = get_settings()
    if db.scalar(select(func.count()).select_from(User)) == 0:
        db.add(User(store_id=s.store_id, user_id=s.admin_user_id, name="Asha Admin",
                    email=s.admin_email, role="Admin",
                    password_hash=hash_password(s.admin_password)))
        db.commit()
        log.warning("Created the first Admin '%s'. Change its password.", s.admin_user_id)

    if s.seed_demo_users:
        for user_id, name, role, password in DEMO_USERS:
            if db.scalar(select(User).where(User.user_id == user_id)) is None:
                db.add(User(store_id=s.store_id, user_id=user_id, name=name,
                            email=f"{user_id}@example.com", role=role,
                            password_hash=hash_password(password)))
        db.commit()
