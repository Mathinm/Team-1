"""Expiry notification service for PMS Sprint 2, Issue #11."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.alerts.service import as_utc, raise_alert
from app.config import get_settings
from app.db import SessionLocal
from app.models import Batch, Notification, Product

logger = logging.getLogger(__name__)


def create_expiry_notifications(db: Session, today: date | None = None) -> int:
    """Create pre-expiry and expiry notifications without duplicates."""
    settings = get_settings()

    if today is None:
        today = datetime.now(ZoneInfo(settings.store_timezone)).date()

    targets = (
        (today + timedelta(days=1), "pre_expiry", "Batch expiring tomorrow"),
        (today, "expiry", "Batch expires today"),
    )

    created = 0
    dialect = db.get_bind().dialect.name

    for expiry_date, notification_type, title in targets:
        batches = db.execute(
            select(Batch, Product)
            .join(Product, Product.product_id == Batch.product_id)
            .where(
                Batch.expiry_date == expiry_date,
                Batch.store_id == settings.store_id,
                Batch.quantity > 0,
            )
        ).all()

        for batch, product in batches:
            unit_str = product.unit if product and product.unit else "units"
            qty_str = format(Decimal(str(batch.quantity)).normalize(), "f")
            time_str = "tomorrow" if notification_type == "pre_expiry" else "today"

            values = {
                "store_id": settings.store_id,
                "batch_id": batch.batch_id,
                "removal_id": None,
                "notification_type": notification_type,
                "title": title,
                "message": (
                    f"{product.name} batch {batch.batch_id} expires on "
                    f"{batch.expiry_date.isoformat()}. "
                    f"Remaining quantity: {qty_str} {unit_str}."
                ),
            }

            # SAD 3.4 / ADR-7: raise alert so it appears in /api/alerts and is delivered to staff
            alert_type = "PRE_EXPIRY" if notification_type == "pre_expiry" else "EXPIRY"
            severity = "warning" if notification_type == "pre_expiry" else "critical"
            alert_key = f"{notification_type}:{batch.batch_id}"
            alert_msg = (
                f"{product.name} batch {batch.batch_id} expires {time_str} "
                f"({qty_str} {unit_str} remaining)"
            )
            raise_alert(
                db,
                type=alert_type,
                key=alert_key,
                message=alert_msg,
                severity=severity,
                product_id=batch.product_id,
                triggered_at=as_utc(datetime.now(timezone.utc)),
            )

            if dialect == "postgresql":
                statement = (
                    pg_insert(Notification)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=[
                            Notification.store_id,
                            Notification.batch_id,
                            Notification.notification_type,
                        ],
                        index_where=text(
                            "notification_type IN ('pre_expiry', 'expiry')"
                        ),
                    )
                    .returning(Notification.notification_id)
                )
                if db.execute(statement).scalar_one_or_none() is not None:
                    created += 1

            elif dialect == "sqlite":
                statement = (
                    sqlite_insert(Notification)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=[
                            Notification.store_id,
                            Notification.batch_id,
                            Notification.notification_type,
                        ],
                        index_where=text(
                            "notification_type IN ('pre_expiry', 'expiry')"
                        ),
                    )
                    .returning(Notification.notification_id)
                )
                if db.execute(statement).scalar_one_or_none() is not None:
                    created += 1

            else:
                existing = db.scalar(
                    select(Notification.notification_id).where(
                        Notification.store_id == settings.store_id,
                        Notification.batch_id == batch.batch_id,
                        Notification.notification_type == notification_type,
                    )
                )
                if existing is None:
                    db.add(Notification(**values))
                    db.flush()
                    created += 1

    db.commit()
    return created


def run_expiry_check() -> int:
    """Run one expiry check using a dedicated database session."""
    with SessionLocal() as db:
        return create_expiry_notifications(db)


async def run_notification_scheduler(stop_event: asyncio.Event) -> None:
    """Check expiry dates every 60 seconds until the application shuts down."""
    while not stop_event.is_set():
        try:
            created = await asyncio.to_thread(run_expiry_check)
            if created:
                logger.info("Created %s expiry notifications", created)
        except Exception:
            logger.exception("Expiry notification scheduler failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except TimeoutError:
            continue
