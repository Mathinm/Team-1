"""Dashboard and reports on the real backend (FR-18, TC-REP-01, issue #47 B1).

The seeded shop (tests/conftest.py) has cost price 1 for every product, so money values are easy
to check by hand: value = quantity x 1.
"""

import itertools
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Removal
from app.sales.fefo import store_today
from tests.conftest import auth

_ids = itertools.count(1)
MANAGER = ("manager1", "Manager")


def mgr():
    return auth(*MANAGER)


def today():
    return store_today().isoformat()


def report(client, kind, start=None, end=None, headers=None):
    params = {"from": start or today(), "to": end or today()}
    return client.get(f"/api/reports/{kind}", params=params, headers=headers or mgr())


def sell(client, sku, qty):
    r = client.post("/api/sales", json={"sku": sku, "quantity": qty}, headers=auth())
    assert r.status_code == 201, r.text


def remove(client, batch_id, qty, reason="Damaged"):
    r = client.post("/api/removals", json={"batchId": batch_id, "qty": qty, "reason": reason},
                    headers=auth("staff1", "Inventory Staff"))
    assert r.status_code == 201, r.text


def send(client, key, kind, value, unit="Fridge-2", at=None):
    body = {"eventId": f"rep-{next(_ids)}", "unitId": unit, "type": kind, "value": value,
            "recordedAt": (at or datetime.now(timezone.utc)).isoformat()}
    r = client.post("/api/device/readings", json=body, headers={"X-Device-Key": key})
    assert r.status_code == 200, r.text


def by(rows, key, value):
    return next(r for r in rows if r[key] == value)


# ---------------------------------------------------------------- dashboard


def test_dashboard_numbers_on_the_seeded_shop(client, seeded):
    sell(client, "TOM-01", 2)
    remove(client, 102, 1)
    d = client.get("/api/dashboard", headers=mgr())
    assert d.status_code == 200, d.text
    d = d.json()

    assert d["salesToday"] == {"count": 1, "amount": 60.0}
    # active products only: tomato 37-2-1, banana 60, milk 38, bread 7 (retired item left out)
    assert d["stockValue"] == 34 + 60 + 38 + 7
    assert d["wasteLast7Days"] == {"value": 1.0, "removals": 1}
    assert [p["name"] for p in d["lowStock"]] == ["Bread Loaf"]
    assert d["lowStock"][0] == {"productId": 5, "name": "Bread Loaf", "stock": 7,
                                "threshold": 10, "unit": "piece"}
    # 2 days or less, expired included, retired product left out; soonest first
    assert [(b["batchId"], b["daysToExpiry"]) for b in d["expiringSoon"]] == [
        (104, -1), (107, -1), (101, 2)]
    assert d["activeAlerts"]["count"] == len(d["activeAlerts"]["latest"])


def test_dashboard_lists_active_alerts_newest_first(client, seeded, sensor_key):
    send(client, sensor_key, "power", "OFF", unit="Fridge-1")
    send(client, sensor_key, "temperature", 12, unit="Fridge-2")
    a = client.get("/api/dashboard", headers=mgr()).json()["activeAlerts"]
    assert a["count"] == 2
    assert a["critical"] == sum(1 for x in a["latest"] if x["severity"] == "critical") >= 1
    assert {x["type"] for x in a["latest"]} == {"UNIT_FAILURE", "TEMPERATURE"}
    ranks = {"critical": 0, "warning": 1, "info": 2}
    order = [ranks[x["severity"]] for x in a["latest"]]
    assert order == sorted(order)  # critical first
    assert {"alertId", "severity", "message", "createdAt", "triggeredAt"} <= set(a["latest"][0])


def test_dashboard_roles(client, seeded):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers=auth()).status_code == 403  # cashier
    for role in [("staff1", "Inventory Staff"), MANAGER, ("admin1", "Admin")]:
        assert client.get("/api/dashboard", headers=auth(*role)).status_code == 200


# ---------------------------------------------------------------- reports


def test_stock_report(client, seeded):
    r = report(client, "stock").json()
    assert r["type"] == "stock" and r["title"] == "Stock on hand"
    names = [row["product"] for row in r["rows"]]
    assert "Retired item" not in names
    tomato = by(r["rows"], "product", "Tomato")
    assert tomato["onHand"] == 37 and tomato["batches"] == 2 and tomato["status"] == "OK"
    assert by(r["rows"], "product", "Bread Loaf")["status"] == "Low stock"
    assert by(r["rows"], "product", "Milk 1L")["status"] == "Has expired stock"
    assert r["summary"] == [{"label": "Total stock value", "value": "Rs 142.0"}]
    assert [c["key"] for c in r["columns"]][:3] == ["product", "category", "onHand"]


def test_wastage_report_waste_percent_and_money_lost(client, seeded):
    sell(client, "TOM-01", 2)
    remove(client, 102, 1)
    remove(client, 103, 3, "Temperature breach")
    r = report(client, "wastage").json()
    tomato = by(r["rows"], "product", "Tomato")
    assert tomato == {"product": "Tomato", "sold": 2, "wasted": 1, "unit": "kg",
                      "wastePct": 33.33, "moneyLost": 1.0}
    banana = by(r["rows"], "product", "Banana")
    assert banana["wastePct"] == 100.0 and banana["moneyLost"] == 3.0
    assert r["rows"][0]["product"] == "Banana"  # most money lost first
    assert r["summary"] == [{"label": "Total money lost to waste", "value": "Rs 4.0"}]


def test_sellers_report_ranks_by_revenue(client, seeded):
    sell(client, "BAN-01", 2)   # 12
    sell(client, "TOM-01", 1)   # 30
    sell(client, "MLK-01", 1)   # 28
    rows = report(client, "sellers").json()["rows"]
    assert [(x["rank"], x["product"], x["revenue"]) for x in rows] == [
        (1, "Tomato", 30.0), (2, "Milk 1L", 28.0), (3, "Banana", 12.0)]
    assert rows[0]["tag"] == "Best seller"


def test_supplier_quality_report(client, seeded):
    remove(client, 103, 6)
    start = (store_today() - timedelta(days=3)).isoformat()
    rows = report(client, "supplier-quality", start=start).json()["rows"]
    farms = by(rows, "supplier", "Fresh Farms")
    # seeded batches were received 2 days ago: 12+25+60+8+30+7+5 = 147 units in 7 deliveries
    assert farms["deliveries"] == 7 and farms["received"] == 147
    assert farms["wasted"] == 6 and farms["wasteRate"] == round(6 / 147 * 100, 2)


def test_removals_report_lists_reason_worker_and_value(client, seeded):
    remove(client, 101, 2, "Damaged")
    rows = report(client, "removals").json()["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["product"] == "Tomato" and row["batch"] == "B-101" and row["quantity"] == 2
    assert row["reason"] == "Damaged" and row["worker"] == "staff1" and row["value"] == 2.0
    assert row["date"][:4].isdigit() and "T" in row["date"]


def test_temperature_report_daily_min_avg_max(client, seeded, sensor_key):
    for v in (3, 5, 10):
        send(client, sensor_key, "temperature", v, unit="Fridge-2")
    send(client, sensor_key, "door", "OPEN", unit="Fridge-2")  # not a temperature
    rows = report(client, "temperature").json()["rows"]
    assert rows == [{"day": today(), "unit": "Fridge-2", "allowed": "0 to 8",
                     "min": 3, "avg": 6.0, "max": 10, "outOfRange": 1}]


def test_power_events_report(client, seeded, sensor_key):
    start = datetime.now(timezone.utc) - timedelta(minutes=30)
    send(client, sensor_key, "power", "OFF", unit="Fridge-1", at=start)
    send(client, sensor_key, "power", "ON", unit="Fridge-1", at=start + timedelta(minutes=12))
    send(client, sensor_key, "power", "OFF", unit="Fridge-2")
    rows = report(client, "power-events").json()["rows"]
    fridge1 = by(rows, "unit", "Fridge-1")
    assert fridge1["minutes"] == 12 and fridge1["end"] != "ongoing"
    assert by(rows, "unit", "Fridge-2")["end"] == "ongoing"


def test_alerts_report(client, seeded, sensor_key):
    send(client, sensor_key, "power", "OFF", unit="Fridge-1")
    rows = report(client, "alerts").json()["rows"]
    assert len(rows) == 1
    assert rows[0]["type"] == "UNIT_FAILURE" and rows[0]["severity"] == "critical"
    assert rows[0]["ackBy"] == "-"


def test_date_range_covers_whole_days_and_excludes_others(client, seeded, db):
    remove(client, 101, 1)
    old = db.query(Removal).one()
    old.recorded_at = datetime.now(timezone.utc) - timedelta(days=10)
    db.commit()
    assert report(client, "removals").json()["rows"] == []
    start = (store_today() - timedelta(days=11)).isoformat()
    assert len(report(client, "removals", start=start).json()["rows"]) == 1


def test_empty_period_returns_no_rows(client, seeded):
    r = report(client, "wastage", start="2020-01-01", end="2020-01-31")
    assert r.status_code == 200
    assert r.json()["rows"] == [] and r.json()["from"] == "2020-01-01"


@pytest.mark.parametrize("params, code", [
    ({"from": "2026-11-10", "to": "2026-11-01"}, 400),   # from after to
    ({"to": "2026-11-01"}, 400),                         # from missing
    ({"from": "2026-13-01", "to": "2026-11-01"}, 400),   # not a date
    ({"from": "2024-01-01", "to": "2026-01-01"}, 400),   # more than a year
])
def test_report_date_validation(client, seeded, params, code):
    r = client.get("/api/reports/wastage", params=params, headers=mgr())
    assert r.status_code == code, r.text


def test_unknown_report_type_is_404(client, seeded):
    assert report(client, "nonsense").status_code == 404


def test_report_roles(client, seeded):
    assert client.get("/api/reports/stock?from=2026-11-01&to=2026-11-01").status_code == 401
    assert report(client, "stock", headers=auth("staff1", "Inventory Staff")).status_code == 403
    assert report(client, "stock", headers=auth()).status_code == 403
    assert report(client, "stock", headers=auth("admin1", "Admin")).status_code == 200
