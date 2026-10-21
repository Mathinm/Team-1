"""Register a device and print its key once.

    python -m app.device.provision pos-sim pos
    python -m app.device.provision fridge-sensors sensor

In Docker:  docker compose exec backend python -m app.device.provision pos-sim pos
"""

import sys

from sqlalchemy.exc import IntegrityError

from app.db import Base, SessionLocal, engine
from app.device.auth import KINDS, create_device


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in KINDS:
        print(f"usage: python -m app.device.provision <name> <{'|'.join(KINDS)}>")
        return 2
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        try:
            key = create_device(db, argv[0], argv[1])
        except IntegrityError:
            db.rollback()
            print(f"A device named '{argv[0]}' already exists.")
            return 1
    print(f"Device '{argv[0]}' ({argv[1]}) registered.")
    print(f"Key (shown once, send it as the X-Device-Key header):\n{key}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
