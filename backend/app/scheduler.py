"""Scheduler (SAD 3.4): a background loop that calls the Alert Service on a timetable.

Every SCHEDULER_INTERVAL_SECONDS (default 10 s) it runs the jobs in JOBS, each in its own
transaction, so one failing job never stops the others:

  doors         alarm for any fridge door still open past its limit (FR-16)
  low_stock     the once-a-day projected low-stock check (FR-10), at LOW_STOCK_CHECK_TIME
  markdowns     apply rule-based discounts to nearing-expiry batches (FR-14)
  notifications deliver new alerts to staff and retry failed deliveries (NFR-2: within 60 s)

To add a job (for example the expiry check), write `def my_job(db, now): ...` and add one line
to JOBS. Jobs must be safe to run twice; the loop commits for them.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.alerts.notifier import dispatch_pending
from app.alerts.service import now_utc, run_daily_low_stock_job
from app.config import get_settings
from app.db import SessionLocal
from app.markdowns.service import apply_markdown_rules
from app.refrigeration.service import check_open_doors

log = logging.getLogger("pms.scheduler")

Job = Callable[[Session, datetime], object]

# Order matters a little: notifications last, so alerts raised in this round go out at once.
JOBS: list[tuple[str, Job]] = [
    ("doors", check_open_doors),
    ("low_stock", run_daily_low_stock_job),
    ("markdowns", apply_markdown_rules),
    ("notifications", dispatch_pending),
]


def run_once(now: datetime | None = None, session_factory=SessionLocal) -> dict[str, object]:
    """Run every job once. Returns each job's result (None when a job failed)."""
    now = now or now_utc()
    results: dict[str, object] = {}
    for name, job in JOBS:
        with session_factory() as db:
            try:
                results[name] = job(db, now)
                db.commit()
            except Exception:
                db.rollback()
                results[name] = None
                log.exception("Scheduler job '%s' failed; it will run again next round", name)
    return results


class Scheduler:
    def __init__(self, interval: float | None = None):
        self.interval = interval or get_settings().scheduler_interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="pms-scheduler", daemon=True)
        self._thread.start()
        log.info("Scheduler started (every %s s)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_once()
            except Exception:  # never let the thread die
                log.exception("Scheduler round failed")
            self._stop.wait(self.interval)
