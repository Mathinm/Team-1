from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.markdowns import service
from app.markdowns.schemas import (
    MarkdownApplyResponse,
    MarkdownOut,
    MarkdownRuleCreate,
    MarkdownRuleOut,
)
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, require_roles

router = APIRouter(prefix="/api", tags=["markdowns"])


@router.post(
    "/markdown-rules",
    response_model=MarkdownRuleOut,
    status_code=status.HTTP_201_CREATED,
)
def create_markdown_rule(
    body: MarkdownRuleCreate,
    user: CurrentUser = Depends(require_roles(MANAGER, ADMIN)),
    db: Session = Depends(get_db),
):
    """Manager configures a near-expiry markdown rule (FR-14, TC-EXP-07)."""
    return service.create_rule(db, body, user.user_id)


@router.get("/markdown-rules", response_model=list[MarkdownRuleOut])
def list_markdown_rules(
    _: CurrentUser = Depends(require_roles(MANAGER, ADMIN, STAFF)),
    db: Session = Depends(get_db),
):
    return service.list_rules(db)


@router.delete("/markdown-rules/{rule_id}")
def delete_markdown_rule(
    rule_id: int,
    _: CurrentUser = Depends(require_roles(MANAGER, ADMIN)),
    db: Session = Depends(get_db),
):
    service.delete_rule(db, rule_id)
    return {"deleted": True, "ruleId": rule_id}


@router.post("/markdowns/apply", response_model=MarkdownApplyResponse)
def apply_markdowns(
    _: CurrentUser = Depends(require_roles(MANAGER, ADMIN, STAFF)),
    db: Session = Depends(get_db),
):
    """Evaluate active rules and apply discounts to qualifying near-expiry batches (TC-EXP-06)."""
    applied = service.apply_markdown_rules(db)
    return {"applied": len(applied), "markdowns": applied}


@router.get("/markdowns", response_model=list[MarkdownOut])
def list_markdowns(
    _: CurrentUser = Depends(require_roles(MANAGER, ADMIN, STAFF)),
    db: Session = Depends(get_db),
):
    """View marked-down batches and their sell-through percentage (TC-EXP-08)."""
    return service.list_markdowns(db)
