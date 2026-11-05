"""The stores table (NFR-14): make sure the configured store exists.

Every table's store_id points at stores.store_id, so the row for settings.store_id must exist
before anything else is inserted. Called wherever tables are created. Safe to call repeatedly,
and safe if two backend workers start at the same moment.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Store


def ensure_default_store(db: Session) -> Store:
    s = get_settings()
    store = db.get(Store, s.store_id)
    if store is None:
        try:
            with db.begin_nested():
                store = Store(store_id=s.store_id, name=s.store_name, timezone=s.store_timezone)
                db.add(store)
                db.flush()
        except IntegrityError:  # another worker created it first
            store = db.get(Store, s.store_id)
        db.commit()
    return store
