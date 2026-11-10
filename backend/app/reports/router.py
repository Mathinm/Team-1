"""GET /api/dashboard and GET /api/reports/{type} (FR-18, issue #47 B1).
Contract: docs/frontend-api-contract.md, "Sprint 2: dashboard and reports"."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, require_roles
from app.reports.service import BUILDERS, build_dashboard, build_report

router = APIRouter(prefix="/api", tags=["reports"])
dashboard_users = require_roles(ADMIN, MANAGER, STAFF)
report_users = require_roles(ADMIN, MANAGER)

MAX_DAYS = 366  # a year at most per report, so one request stays fast


@router.get("/dashboard")
def dashboard(_user: CurrentUser = Depends(dashboard_users), db: Session = Depends(get_db)):
    """Store overview: sales today, stock value, low stock, expiring soon, alerts, waste."""
    return build_dashboard(db)


@router.get("/reports/{report_type}")
def report(
    report_type: str,
    from_: date = Query(alias="from"),
    to: date = Query(),
    _user: CurrentUser = Depends(report_users),
    db: Session = Depends(get_db),
):
    """One FR-18 report for the whole days from..to (store time zone)."""
    if report_type not in BUILDERS:
        raise ApiError(404, "NOT_FOUND", f"Unknown report type '{report_type}'")
    if from_ > to:
        raise ApiError(400, "VALIDATION", "From date must be on or before To date")
    if (to - from_).days >= MAX_DAYS:
        raise ApiError(400, "VALIDATION", f"Choose a range of at most {MAX_DAYS} days")
    return build_report(db, report_type, from_, to)
