"""Notification interface (SAD 3.4): deliver stored alerts to staff by email.

Alerts go out through the team's one mail function, app.notify.send_email(): over SMTP when
SMTP_HOST is set, otherwise written to the log and kept in notify.OUTBOX. send_email raises when
the mail server refuses or is unreachable, which is what marks an alert "failed" so it is retried
(up to MAX_ATTEMPTS). Alerts are stored first, so a failing mail server never hides an alert.
"""

import logging
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.alerts.service import as_utc, now_utc
from app.config import get_settings
from app.models import Alert, User
from app.notify import send_email

log = logging.getLogger("pms.notify")

MAX_ATTEMPTS = 5
RETRY_GAP = timedelta(seconds=30)
BATCH_SIZE = 50

# Who is told about which alert type. Other modules add their own line (e.g. expiry -> staff).
DEFAULT_RECIPIENT_ROLES = ("Manager",)
RECIPIENT_ROLES: dict[str, tuple[str, ...]] = {
    "EXPIRY": ("Manager", "Inventory Staff"),
    "PRE_EXPIRY": ("Manager", "Inventory Staff"),
    "REMOVAL": ("Manager", "Inventory Staff"),
    "STOCK_REMOVAL": ("Manager", "Inventory Staff"),
}


class Notifier(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None:
        """Deliver one message. Raise any exception if it could not be delivered."""

class EmailNotifier:
    """Sends through the shared app.notify.send_email (SMTP, or the log when SMTP is not set)."""

    def send(self, recipient: str, subject: str, body: str) -> None:
        send_email(recipient, subject, body)


_notifier: Notifier = EmailNotifier()

def get_notifier() -> Notifier:
    return _notifier


def set_notifier(notifier: Notifier) -> None:
    global _notifier
    _notifier = notifier


def _recipients(db: Session, alert_type: str) -> list[str]:
    roles = RECIPIENT_ROLES.get(alert_type, DEFAULT_RECIPIENT_ROLES)
    rows = db.scalars(
        select(User.email).where(
            User.store_id == get_settings().store_id, User.active.is_(True), User.role.in_(roles)
        )
    ).all()
    return sorted({e for e in rows if e})


def dispatch_pending(db: Session, now: datetime | None = None) -> int:
    """Send every alert that is waiting for delivery (or failed and is due for a retry).

    Returns how many alerts were delivered in this call. The caller commits.
    """
    now = now or now_utc()
    due = db.scalars(
        select(Alert)
        .where(
            Alert.store_id == get_settings().store_id,
            Alert.delivery_status.in_(("pending", "failed")),
            Alert.delivery_attempts < MAX_ATTEMPTS,
            or_(Alert.last_attempt_at.is_(None), Alert.last_attempt_at <= now - RETRY_GAP),
        )
        .order_by(Alert.alert_id)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)  # two backend copies never send the same alert
    ).all()
    delivered = 0
    for alert in due:
        alert.delivery_attempts += 1
        alert.last_attempt_at = now
        recipients = _recipients(db, alert.type)
        if not recipients:
            alert.delivery_status = "skipped"  # nobody to tell; still visible in the app
            log.warning("Alert %s has no recipients; shown in the app only", alert.alert_id)
            continue
        try:
            for recipient in recipients:
                get_notifier().send(recipient, f"PMS alert: {alert.type}", alert.message)
        except Exception:
            alert.delivery_status = "failed"
            log.exception("Delivery of alert %s failed (attempt %s)", alert.alert_id,
                          alert.delivery_attempts)
            continue
        alert.delivery_status = "sent"
        alert.delivered_at = now
        delivered += 1
        seconds = (now - as_utc(alert.created_at or now)).total_seconds()
        log.info("ALERT_DELIVERED id=%s after=%.1fs", alert.alert_id, seconds)  # NFR-2 monitoring
    return delivered
