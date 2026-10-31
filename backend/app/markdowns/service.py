import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.markdowns.schemas import MarkdownRuleCreate
from app.models import Batch, Markdown, MarkdownRule, Product

log = logging.getLogger("pms.markdowns")


def store_today(now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(get_settings().store_timezone)).date()


def rule_to_out(r: MarkdownRule) -> dict:
    return {
        "ruleId": r.rule_id,
        "productId": r.product_id,
        "category": r.category,
        "daysBeforeExpiry": r.days_before_expiry,
        "discountPercent": float(r.discount_percent),
        "name": r.name,
        "active": r.active,
        "createdBy": r.created_by,
        "createdAt": r.created_at,
    }


def create_rule(db: Session, data: MarkdownRuleCreate, user_id: str) -> dict:
    store_id = get_settings().store_id
    max_pct = Decimal(str(get_settings().max_markdown_percent))

    if data.discountPercent > max_pct:
        pct_display = f"{int(max_pct)}%" if max_pct == int(max_pct) else f"{max_pct}%"
        raise ApiError(
            422,
            "DISCOUNT_EXCEEDS_MAX",
            f"Discount exceeds maximum {pct_display}",
        )

    if data.productId is not None:
        product = db.get(Product, data.productId)
        if product is None:
            raise ApiError(404, "NOT_FOUND", f"Product #{data.productId} not found")

    name = data.name or f"{data.discountPercent}% off at {data.daysBeforeExpiry}d to expiry"
    rule = MarkdownRule(
        store_id=store_id,
        name=name,
        product_id=data.productId,
        category=data.category,
        days_before_expiry=data.daysBeforeExpiry,
        discount_percent=data.discountPercent,
        active=True,
        created_by=user_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log.info("MARKDOWN_RULE_CREATED id=%s product=%s discount=%s%% by=%s",
             rule.rule_id, rule.product_id, rule.discount_percent, user_id)
    return rule_to_out(rule)


def list_rules(db: Session) -> list[dict]:
    store_id = get_settings().store_id
    rules = db.scalars(
        select(MarkdownRule)
        .where(MarkdownRule.store_id == store_id, MarkdownRule.active.is_(True))
        .order_by(MarkdownRule.rule_id.desc())
    ).all()
    return [rule_to_out(r) for r in rules]


def delete_rule(db: Session, rule_id: int) -> bool:
    rule = db.get(MarkdownRule, rule_id)
    if rule is None or not rule.active:
        raise ApiError(404, "NOT_FOUND", f"Markdown rule #{rule_id} not found")
    rule.active = False
    db.commit()
    log.info("MARKDOWN_RULE_DELETED id=%s", rule_id)
    return True


def apply_markdown_rules(db: Session, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    store_id = get_settings().store_id
    today = store_today(now)

    rules = list(
        db.scalars(
            select(MarkdownRule)
            .where(MarkdownRule.store_id == store_id, MarkdownRule.active.is_(True))
        ).all()
    )
    if not rules:
        return []

    batches = list(
        db.scalars(
            select(Batch)
            .where(
                Batch.store_id == store_id,
                Batch.quantity > 0,
                Batch.expiry_date >= today,
            )
            .order_by(Batch.expiry_date, Batch.batch_id)
        ).all()
    )

    applied_ids = []
    for batch in batches:
        product = db.get(Product, batch.product_id)
        if product is None or not product.active:
            continue

        days_left = (batch.expiry_date - today).days

        # Match rules that apply to this batch
        matching_rules = []
        for r in rules:
            if days_left > r.days_before_expiry:
                continue
            if r.product_id is not None and r.product_id == product.product_id:
                matching_rules.append((3, r.discount_percent, r))
            elif r.category and r.category.lower() == product.category.lower():
                matching_rules.append((2, r.discount_percent, r))
            elif r.product_id is None and not r.category:
                matching_rules.append((1, r.discount_percent, r))

        if not matching_rules:
            continue

        matching_rules.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best_rule = matching_rules[0][2]

        existing_md = db.scalar(
            select(Markdown).where(
                Markdown.batch_id == batch.batch_id,
                Markdown.status == "active",
            )
        )

        discount_multiplier = Decimal(1) - (best_rule.discount_percent / Decimal(100))
        discounted_price = (product.selling_price * discount_multiplier).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )

        if existing_md:
            if best_rule.discount_percent <= existing_md.discount_percent:
                continue
            existing_md.rule_id = best_rule.rule_id
            existing_md.discount_percent = best_rule.discount_percent
            existing_md.discounted_price = discounted_price
            applied_ids.append(existing_md.markdown_id)
        else:
            md = Markdown(
                store_id=store_id,
                batch_id=batch.batch_id,
                product_id=product.product_id,
                rule_id=best_rule.rule_id,
                original_price=product.selling_price,
                discount_percent=best_rule.discount_percent,
                discounted_price=discounted_price,
                initial_quantity=batch.quantity,
                quantity_sold=Decimal(0),
                status="active",
                marked_down_at=now,
            )
            db.add(md)
            db.flush()
            applied_ids.append(md.markdown_id)
            log.info(
                "MARKDOWN_APPLIED batch=%s product=%s discount=%s%% price=%s",
                batch.batch_id, product.name, best_rule.discount_percent, discounted_price,
            )

    db.commit()
    return list_markdowns(db, markdown_ids=applied_ids)


def list_markdowns(
    db: Session,
    markdown_ids: list[int] | None = None,
) -> list[dict]:
    store_id = get_settings().store_id
    query = (
        select(Markdown, Product, Batch)
        .join(Product, Markdown.product_id == Product.product_id)
        .join(Batch, Markdown.batch_id == Batch.batch_id)
        .where(Markdown.store_id == store_id)
    )
    if markdown_ids is not None:
        query = query.where(Markdown.markdown_id.in_(markdown_ids))

    query = query.order_by(Markdown.marked_down_at.desc(), Markdown.markdown_id.desc())

    records = db.execute(query).all()
    results = []
    for md, product, batch in records:
        initial = float(md.initial_quantity)
        sold = float(md.quantity_sold)
        remaining = float(batch.quantity)
        sell_through = round((sold / initial) * 100.0, 1) if initial > 0 else 0.0

        results.append({
            "markdownId": md.markdown_id,
            "batchId": md.batch_id,
            "productId": md.product_id,
            "productName": product.name,
            "sku": product.sku,
            "originalPrice": float(md.original_price),
            "discountPercent": float(md.discount_percent),
            "discountedPrice": float(md.discounted_price),
            "initialQuantity": initial,
            "quantitySold": sold,
            "remainingQuantity": remaining,
            "sellThroughPercent": sell_through,
            "status": md.status,
            "markedDownAt": md.marked_down_at,
        })
    return results


def get_active_batch_markdown(db: Session, batch_id: int) -> Markdown | None:
    return db.scalar(
        select(Markdown).where(
            Markdown.batch_id == batch_id,
            Markdown.status == "active",
        )
    )


def record_markdown_sale(db: Session, batch_id: int, quantity_sold: Decimal):
    md = get_active_batch_markdown(db, batch_id)
    if md is None:
        return
    md.quantity_sold += quantity_sold
    batch = db.get(Batch, batch_id)
    if batch and batch.quantity <= 0:
        md.status = "sold_out"
    db.flush()
