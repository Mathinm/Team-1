"""Dashboard and reports (FR-18, issue #47 B1).

The numbers follow frontend/src/api/mock/reports.js, so demo mode and the real backend agree:
  * money lost to waste = quantity removed x the product's cost price
  * stock value = quantity on hand x cost price
  * a report's date range covers the whole of both days, in the store's time zone
  * money is shown as rupees with two decimals, e.g. "₹1,234.50" (N20)
  * the stock report is a snapshot of now and ignores the range; it says so with asOf (N15)
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.schemas import alert_out
from app.alerts.service import UNIT_FAILURE, as_utc
from app.config import get_settings
from app.models import (
    Alert,
    Batch,
    Product,
    RefrigerationUnit,
    Removal,
    Sale,
    SensorReading,
    Supplier,
)
from app.refrigeration.service import effective_limits
from app.sales.fefo import store_today

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

REPORT_TITLES = {
    "stock": "Stock on hand",
    "sales": "Sales history",
    "wastage": "Wastage and money lost",
    "sellers": "Best and worst sellers",
    "supplier-quality": "Supplier quality",
    "removals": "Removals",
    "temperature": "Temperature history",
    "power-events": "Power events",
    "alerts": "Alerts",
}


def r2(value) -> float:
    return round(float(value), 2)


def inr(value) -> str:
    """Rupees with Indian digit grouping and two decimals: 123456.5 -> '₹1,23,456.50' (N20)."""
    q = Decimal(str(value)).quantize(Decimal("0.01"))
    sign = "-" if q < 0 else ""
    whole, frac = f"{abs(q):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}.{frac}"


def pct(part, whole) -> float:
    return r2(float(part) / float(whole) * 100) if whole else 0.0


def num(value: Decimal | float) -> float | int:
    """3 -> 3, 2.5 -> 2.5 (quantities are shown without trailing zeros)."""
    f = float(value)
    return int(f) if f == int(f) else round(f, 3)


def iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat() if dt else None


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().store_timezone)


def day_range(start: date, end: date) -> tuple[datetime, datetime]:
    """Whole store-local days start..end as a UTC [from, to) pair."""
    tz = _tz()
    lo = datetime.combine(start, time.min, tzinfo=tz).astimezone(timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return lo, hi


def _within(dt: datetime, lo: datetime, hi: datetime) -> bool:
    return lo <= as_utc(dt) < hi


def _store_id() -> int:
    return get_settings().store_id


def _products(db: Session) -> dict[int, Product]:
    rows = db.scalars(select(Product).where(Product.store_id == _store_id()))
    return {p.product_id: p for p in rows}


def _batches(db: Session) -> list[Batch]:
    return list(db.scalars(select(Batch).where(Batch.store_id == _store_id())))


def _removals(db: Session, lo: datetime, hi: datetime) -> list[Removal]:
    rows = db.scalars(select(Removal).where(Removal.store_id == _store_id()))
    return [r for r in rows if _within(r.recorded_at, lo, hi)]


def _sales(db: Session, lo: datetime, hi: datetime) -> list[Sale]:
    rows = db.scalars(select(Sale).where(Sale.store_id == _store_id()))
    return [s for s in rows if _within(s.sold_at, lo, hi)]


# ---------------------------------------------------------------- reports


def _stock(db: Session, _lo, _hi, today: date) -> dict:
    columns = [
        {"key": "product", "label": "Product"},
        {"key": "category", "label": "Category"},
        {"key": "onHand", "label": "On hand", "numeric": True},
        {"key": "unit", "label": "Unit"},
        {"key": "batches", "label": "Batches", "numeric": True},
        {"key": "nextExpiry", "label": "Next expiry"},
        {"key": "value", "money": True, "label": "Value at cost (₹)", "numeric": True},
        {"key": "status", "label": "Status"},
    ]
    by_product = defaultdict(list)
    for b in _batches(db):
        if b.quantity > 0:
            by_product[b.product_id].append(b)
    rows = []
    for p in sorted(_products(db).values(), key=lambda p: p.name):
        if not p.active:
            continue
        batches = by_product[p.product_id]
        on_hand = sum((b.quantity for b in batches), Decimal(0))
        nxt = min((b.expiry_date for b in batches), default=None)
        if on_hand <= 0:
            status = "Out of stock"
        elif on_hand < p.low_stock_threshold:
            status = "Low stock"
        elif nxt is not None and nxt < today:
            status = "Has expired stock"
        else:
            status = "OK"
        rows.append({
            "product": p.name, "category": p.category, "onHand": num(on_hand), "unit": p.unit,
            "batches": len(batches), "nextExpiry": nxt.isoformat() if nxt else "-",
            "value": r2(on_hand * p.cost_price), "status": status,
        })
    total = r2(sum(r["value"] for r in rows))
    return {"columns": columns, "rows": rows,
            "summary": [{"label": "Total stock value", "value": inr(total)}]}


def _wastage(db: Session, lo, hi, _today) -> dict:
    columns = [
        {"key": "product", "label": "Product"},
        {"key": "sold", "label": "Sold", "numeric": True},
        {"key": "wasted", "label": "Wasted", "numeric": True},
        {"key": "unit", "label": "Unit"},
        {"key": "wastePct", "label": "Waste %", "numeric": True},
        {"key": "moneyLost", "money": True, "label": "Money lost (₹)", "numeric": True},
    ]
    products = _products(db)
    batch_product = {b.batch_id: b.product_id for b in _batches(db)}
    sold = defaultdict(Decimal)
    for s in _sales(db, lo, hi):
        sold[s.product_id] += s.quantity
    wasted = defaultdict(Decimal)
    lost = defaultdict(Decimal)
    for r in _removals(db, lo, hi):
        pid = batch_product[r.batch_id]
        wasted[pid] += r.quantity
        lost[pid] += r.quantity * products[pid].cost_price
    rows = []
    for pid in set(sold) | set(wasted):
        p = products[pid]
        rows.append({
            "product": p.name, "sold": num(sold[pid]), "wasted": num(wasted[pid]), "unit": p.unit,
            "wastePct": pct(wasted[pid], sold[pid] + wasted[pid]), "moneyLost": r2(lost[pid]),
        })
    rows.sort(key=lambda r: (-r["moneyLost"], r["product"]))
    total = r2(sum(r["moneyLost"] for r in rows))
    return {"columns": columns, "rows": rows,
            "summary": [{"label": "Total money lost to waste", "value": inr(total)}]}


def _sellers(db: Session, lo, hi, _today) -> dict:
    columns = [
        {"key": "rank", "label": "Rank", "numeric": True},
        {"key": "product", "label": "Product"},
        {"key": "quantity", "label": "Quantity sold", "numeric": True},
        {"key": "unit", "label": "Unit"},
        {"key": "revenue", "money": True, "label": "Revenue (₹)", "numeric": True},
        {"key": "tag", "label": ""},
    ]
    products = _products(db)
    qty = defaultdict(Decimal)
    revenue = defaultdict(Decimal)
    for s in _sales(db, lo, hi):
        qty[s.product_id] += s.quantity
        revenue[s.product_id] += s.amount
    ranked = sorted(qty, key=lambda pid: (-revenue[pid], products[pid].name))
    n = len(ranked)
    rows = []
    for i, pid in enumerate(ranked):
        tag = "Best seller" if i < 3 else "Worst seller" if n > 4 and i >= n - 2 else ""
        rows.append({
            "rank": i + 1, "product": products[pid].name, "quantity": num(qty[pid]),
            "unit": products[pid].unit, "revenue": r2(revenue[pid]), "tag": tag,
        })
    total = r2(sum(r["revenue"] for r in rows))
    return {"columns": columns, "rows": rows,
            "summary": [{"label": "Total revenue", "value": inr(total)}]}


def _sales_history(db: Session, lo, hi, _today) -> dict:
    """Every sale in the range, newest first (T7): when, what, how much, how it came in."""
    columns = [
        {"key": "date", "label": "Sold at"},
        {"key": "saleId", "label": "Sale", "numeric": True},
        {"key": "product", "label": "Product"},
        {"key": "quantity", "label": "Quantity", "numeric": True},
        {"key": "unit", "label": "Unit"},
        {"key": "unitPrice", "money": True, "label": "Unit price (₹)", "numeric": True},
        {"key": "amount", "money": True, "label": "Amount (₹)", "numeric": True},
        {"key": "source", "label": "Source"},
        {"key": "recordedBy", "label": "Recorded by"},
    ]
    products = _products(db)
    sources = {"manual": "Manual", "csv": "CSV", "device": "POS"}
    sales = sorted(_sales(db, lo, hi), key=lambda s: (as_utc(s.sold_at), s.sale_id), reverse=True)
    rows = [
        {"date": iso(s.sold_at), "saleId": s.sale_id,
         "product": products[s.product_id].name if s.product_id in products else s.sku,
         "quantity": num(s.quantity), "unit": s.unit, "unitPrice": r2(s.unit_price),
         "amount": r2(s.amount), "source": sources.get(s.source, s.source),
         "recordedBy": s.recorded_by}
        for s in sales
    ]
    total = r2(sum((s.amount for s in sales), Decimal(0)))
    return {"columns": columns, "rows": rows, "summary": [
        {"label": "Sales", "value": str(len(rows))},
        {"label": "Total revenue", "value": inr(total)},
    ]}


def _supplier_quality(db: Session, lo, hi, _today) -> dict:
    columns = [
        {"key": "supplier", "label": "Supplier"},
        {"key": "deliveries", "label": "Deliveries", "numeric": True},
        {"key": "received", "label": "Units received", "numeric": True},
        {"key": "wasted", "label": "Units wasted", "numeric": True},
        {"key": "wasteRate", "label": "Waste rate %", "numeric": True},
    ]
    batches = _batches(db)
    batch_supplier = {b.batch_id: b.supplier_id for b in batches}
    deliveries = defaultdict(int)
    received = defaultdict(Decimal)
    for b in batches:
        if _within(b.received_at, lo, hi):
            deliveries[b.supplier_id] += 1
            received[b.supplier_id] += b.initial_quantity
    wasted = defaultdict(Decimal)
    for r in _removals(db, lo, hi):
        wasted[batch_supplier[r.batch_id]] += r.quantity
    names = {s.supplier_id: s.name for s in db.scalars(
        select(Supplier).where(Supplier.store_id == _store_id()))}
    rows = [
        {"supplier": names.get(sid, f"#{sid}"), "deliveries": deliveries[sid],
         "received": num(received[sid]), "wasted": num(wasted[sid]),
         "wasteRate": pct(wasted[sid], received[sid])}
        for sid in set(deliveries) | set(wasted)
    ]
    rows.sort(key=lambda r: (-r["wasteRate"], r["supplier"]))
    return {"columns": columns, "rows": rows}


def _removal_rows(db: Session, lo, hi, _today) -> dict:
    columns = [
        {"key": "date", "label": "Date"},
        {"key": "product", "label": "Product"},
        {"key": "batch", "label": "Batch"},
        {"key": "quantity", "label": "Quantity", "numeric": True},
        {"key": "unit", "label": "Unit"},
        {"key": "reason", "label": "Reason"},
        {"key": "worker", "label": "Removed by"},
        {"key": "value", "money": True, "label": "Value (₹)", "numeric": True},
    ]
    products = _products(db)
    batch_product = {b.batch_id: b.product_id for b in _batches(db)}
    rows = []
    for r in sorted(_removals(db, lo, hi), key=lambda r: as_utc(r.recorded_at), reverse=True):
        p = products[batch_product[r.batch_id]]
        rows.append({
            "date": iso(r.recorded_at), "product": p.name, "batch": f"B-{r.batch_id}",
            "quantity": num(r.quantity), "unit": p.unit, "reason": r.reason,
            "worker": r.recorded_by, "value": r2(r.quantity * p.cost_price),
        })
    return {"columns": columns, "rows": rows}


def _temperature(db: Session, lo, hi, _today) -> dict:
    columns = [
        {"key": "day", "label": "Day"},
        {"key": "unit", "label": "Unit"},
        {"key": "allowed", "label": "Allowed (°C)"},
        {"key": "min", "label": "Min °C", "numeric": True},
        {"key": "avg", "label": "Avg °C", "numeric": True},
        {"key": "max", "label": "Max °C", "numeric": True},
        {"key": "outOfRange", "label": "Readings out of range", "numeric": True},
    ]
    units = {u.unit_id: u for u in db.scalars(
        select(RefrigerationUnit).where(RefrigerationUnit.store_id == _store_id()))}
    tz = _tz()
    groups = defaultdict(list)
    readings = db.scalars(select(SensorReading).where(
        SensorReading.store_id == _store_id(), SensorReading.type == "temperature",
        SensorReading.value_num.is_not(None)))
    for r in readings:
        if _within(r.recorded_at, lo, hi):
            day = as_utc(r.recorded_at).astimezone(tz).date().isoformat()
            groups[(day, r.unit_id)].append(r.value_num)
    rows = []
    for (day, unit_id), values in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        unit = units.get(unit_id)
        if unit is not None:
            _, t_min, t_max = effective_limits(unit)
        else:
            t_min, t_max = get_settings().unit_temp_min_c, get_settings().unit_temp_max_c
        rows.append({
            "day": day, "unit": unit_id, "allowed": f"{t_min:g} to {t_max:g}",
            "min": round(min(values), 1), "avg": round(sum(values) / len(values), 1),
            "max": round(max(values), 1),
            "outOfRange": sum(1 for v in values if v < t_min or v > t_max),
        })
    rows.sort(key=lambda r: r["unit"])
    rows.sort(key=lambda r: r["day"], reverse=True)  # newest day first, units A-Z
    return {"columns": columns, "rows": rows}


def _power_events(db: Session, lo, hi, _today) -> dict:
    """A power event is a UNIT_FAILURE alert: raised on power OFF, resolved on power ON."""
    columns = [
        {"key": "unit", "label": "Unit"},
        {"key": "start", "label": "Power lost"},
        {"key": "end", "label": "Restored"},
        {"key": "minutes", "label": "Duration (min)", "numeric": True},
    ]
    alerts = db.scalars(select(Alert).where(
        Alert.store_id == _store_id(), Alert.type == UNIT_FAILURE))
    rows = []
    for a in sorted(alerts, key=lambda a: as_utc(a.triggered_at), reverse=True):
        if not _within(a.triggered_at, lo, hi):
            continue
        end = as_utc(a.resolved_at)
        minutes = round((end - as_utc(a.triggered_at)).total_seconds() / 60) if end else "-"
        rows.append({"unit": a.unit_id or "-", "start": iso(a.triggered_at),
                     "end": iso(end) if end else "ongoing", "minutes": minutes})
    return {"columns": columns, "rows": rows}


def _alerts(db: Session, lo, hi, _today) -> dict:
    columns = [
        {"key": "raised", "label": "Raised"},
        {"key": "type", "label": "Type"},
        {"key": "severity", "label": "Severity"},
        {"key": "message", "label": "Alert"},
        {"key": "status", "label": "Status"},
        {"key": "ackBy", "label": "Acknowledged by"},
    ]
    alerts = db.scalars(select(Alert).where(Alert.store_id == _store_id()))
    rows = [
        {"raised": iso(a.triggered_at), "type": a.type, "severity": a.severity,
         "message": a.message, "status": a.status, "ackBy": a.acknowledged_by or "-"}
        for a in sorted(alerts, key=lambda a: as_utc(a.triggered_at), reverse=True)
        if _within(a.triggered_at, lo, hi)
    ]
    return {"columns": columns, "rows": rows}


BUILDERS = {
    "stock": _stock,
    "sales": _sales_history,
    "wastage": _wastage,
    "sellers": _sellers,
    "supplier-quality": _supplier_quality,
    "removals": _removal_rows,
    "temperature": _temperature,
    "power-events": _power_events,
    "alerts": _alerts,
}


SNAPSHOT_REPORTS = {"stock"}  # show the state now; the date range does not apply (N15)


def build_report(db: Session, report_type: str, start: date, end: date,
                 now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    lo, hi = day_range(start, end)
    body = BUILDERS[report_type](db, lo, hi, store_today(now))
    return {"type": report_type, "title": REPORT_TITLES[report_type],
            "from": start.isoformat(), "to": end.isoformat(),
            "asOf": now.isoformat() if report_type in SNAPSHOT_REPORTS else None,
            "summary": [], **body}


# ---------------------------------------------------------------- dashboard


def unit_health(unit: RefrigerationUnit, now: datetime) -> tuple[str, str | None]:
    """("ok" | "failed" | "alert", what is wrong) from power, temperature and door (N19).

    A fridge that is powered but too warm, or whose door has been open past its limit, is not
    "working" on the dashboard even though its status field still says OK.
    """
    door_limit, t_min, t_max = effective_limits(unit)
    if unit.status == "FAILED" or unit.power == "OFF":
        return "failed", "Power off" if unit.power == "OFF" else "Unit failed"
    if unit.temperature is not None and not (t_min <= unit.temperature <= t_max):
        side = "too warm" if unit.temperature > t_max else "too cold"
        return "alert", f"{unit.temperature:g} °C, {side} (allowed {t_min:g} to {t_max:g})"
    if unit.door == "OPEN" and unit.door_open_since is not None:
        minutes = int((now - as_utc(unit.door_open_since)).total_seconds() // 60)
        if minutes >= door_limit:
            return "alert", f"Door open {minutes} min"
    return "ok", None



def build_dashboard(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = store_today(now)
    products = {pid: p for pid, p in _products(db).items() if p.active}
    batches = [b for b in _batches(db) if b.product_id in products]

    on_hand = defaultdict(Decimal)
    for b in batches:
        on_hand[b.product_id] += b.quantity

    low = [
        {"productId": p.product_id, "name": p.name, "stock": num(on_hand[pid]),
         "threshold": p.low_stock_threshold, "unit": p.unit}
        for pid, p in products.items() if on_hand[pid] < p.low_stock_threshold
    ]
    low.sort(key=lambda x: (x["stock"] / (x["threshold"] or 1), x["name"]))

    expiring = []
    for b in batches:
        days = (b.expiry_date - today).days
        if b.quantity > 0 and days <= 2:
            p = products[b.product_id]
            expiring.append({
                "batchId": b.batch_id, "productName": p.name, "quantity": num(b.quantity),
                "unit": p.unit, "expiryDate": b.expiry_date.isoformat(), "daysToExpiry": days,
            })
    expiring.sort(key=lambda x: (x["daysToExpiry"], x["batchId"]))

    day_lo, day_hi = day_range(today, today)
    sales_today = _sales(db, day_lo, day_hi)
    week_lo = now - timedelta(days=7)
    all_products = _products(db)
    batch_product = {b.batch_id: b.product_id for b in _batches(db)}
    waste = _removals(db, week_lo, now + timedelta(seconds=1))
    waste_value = sum((r.quantity * all_products[batch_product[r.batch_id]].cost_price
                       for r in waste), Decimal(0))

    active = list(db.scalars(select(Alert).where(
        Alert.store_id == _store_id(), Alert.status == "active")))
    # critical first, then newest (same order as the demo backend)
    active.sort(key=lambda a: as_utc(a.triggered_at), reverse=True)
    active.sort(key=lambda a: SEVERITY_RANK.get(a.severity, 3))
    units = db.scalars(select(RefrigerationUnit).where(
        RefrigerationUnit.store_id == _store_id()).order_by(RefrigerationUnit.unit_id))

    return {
        "salesToday": {"count": len(sales_today),
                       "amount": r2(sum((s.amount for s in sales_today), Decimal(0)))},
        "stockValue": r2(sum((on_hand[pid] * p.cost_price for pid, p in products.items()),
                             Decimal(0))),
        "wasteLast7Days": {"value": r2(waste_value), "removals": len(waste)},
        "lowStock": low,
        "expiringSoon": expiring,
        "activeAlerts": {
            "count": len(active),
            "critical": sum(1 for a in active if a.severity == "critical"),
            "latest": [alert_out(a).model_dump(mode="json") for a in active[:5]],
        },
        "units": [
            {"unitId": u.unit_id, "name": u.unit_id, "status": st, "problem": problem}
            for u in units
            for st, problem in [unit_health(u, now)]
        ],
    }
