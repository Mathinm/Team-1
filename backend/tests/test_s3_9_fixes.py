"""Sprint 3 fixes from issue #72 (S3-9): dev seed ids and data (N3, T6), stock report says it
is a snapshot (N15), dashboard fridge health (N19), rupee formatting (N20), sales history
report (T7)."""

from datetime import datetime, timedelta, timezone

from app.dev_seed import DEMO
from app.reports.service import inr
from app.sales.fefo import store_today
from tests.conftest import auth
from tests.test_reports import mgr, report, sell, send


# ---- N20: money -----------------------------------------------------------------------
def test_inr_formats_rupees_with_indian_grouping():
    assert inr(0) == "₹0.00"
    assert inr(177) == "₹177.00"
    assert inr(4.5) == "₹4.50"
    assert inr(1234.567) == "₹1,234.57"
    assert inr(123456.5) == "₹1,23,456.50"
    assert inr(12345678) == "₹1,23,45,678.00"
    assert inr(-50) == "-₹50.00"


def test_report_money_columns_are_marked_and_labelled_in_rupees(client, seeded):
    r = report(client, "stock").json()
    value = next(c for c in r["columns"] if c["key"] == "value")
    assert value["money"] is True and value["label"] == "Value at cost (₹)"
    assert all("Rs" not in c["label"] for c in r["columns"])


# ---- N15: the stock report is "as of now" --------------------------------------------
def test_stock_report_says_it_is_a_snapshot(client, seeded):
    start = (store_today() - timedelta(days=30)).isoformat()
    r = report(client, "stock", start=start).json()
    as_of = datetime.fromisoformat(r["asOf"])
    assert abs((datetime.now(timezone.utc) - as_of).total_seconds()) < 60


def test_ranged_reports_have_no_as_of(client, seeded):
    assert report(client, "wastage").json()["asOf"] is None


# ---- T7: sales history ----------------------------------------------------------------
def test_sales_history_lists_each_sale_newest_first(client, seeded):
    sell(client, "TOM-01", 2)
    sell(client, "BAN-01", 3)
    r = report(client, "sales")
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["title"] == "Sales history"
    assert [(x["product"], x["quantity"], x["amount"]) for x in r["rows"]] == [
        ("Banana", 3, 18.0), ("Tomato", 2, 60.0)]
    first = r["rows"][0]
    assert (first["unit"], first["unitPrice"], first["source"], first["recordedBy"]) == (
        "piece", 6.0, "Manual", "cashier1")
    assert r["summary"] == [{"label": "Sales", "value": "2"},
                            {"label": "Total revenue", "value": "₹78.00"}]


def test_sales_history_respects_the_date_range(client, seeded):
    sell(client, "TOM-01", 1)
    old = (store_today() - timedelta(days=5)).isoformat()
    assert report(client, "sales", start=old, end=old).json()["rows"] == []


def test_sales_history_is_for_managers(client, seeded):
    r = report(client, "sales", headers=auth("cashier1", "Cashier"))
    assert r.status_code == 403


# ---- N19: dashboard fridge health -----------------------------------------------------
def units(client):
    return {u["unitId"]: u for u in client.get("/api/dashboard", headers=mgr()).json()["units"]}


def test_fridge_in_range_is_ok(client, seeded, sensor_key):
    send(client, sensor_key, "temperature", 4, unit="Fridge-7")
    assert units(client)["Fridge-7"] == {"unitId": "Fridge-7", "name": "Fridge-7",
                                         "status": "ok", "problem": None}


def test_fridge_too_warm_is_not_working(client, seeded, sensor_key):
    send(client, sensor_key, "temperature", 25, unit="Fridge-9")
    u = units(client)["Fridge-9"]
    assert u["status"] == "alert"
    assert u["problem"].startswith("25 °C, too warm")


def test_fridge_power_off_is_failed(client, seeded, sensor_key):
    send(client, sensor_key, "power", "OFF", unit="Fridge-1")
    assert units(client)["Fridge-1"]["status"] == "failed"
    assert units(client)["Fridge-1"]["problem"] == "Power off"


def test_fridge_door_open_past_limit_is_an_alert(client, seeded, sensor_key):
    long_ago = datetime.now(timezone.utc) - timedelta(minutes=30)
    send(client, sensor_key, "door", "OPEN", unit="Fridge-3", at=long_ago)
    u = units(client)["Fridge-3"]
    assert u["status"] == "alert" and u["problem"].startswith("Door open")


def test_fridge_door_just_opened_is_still_ok(client, seeded, sensor_key):
    send(client, sensor_key, "door", "OPEN", unit="Fridge-4")
    assert units(client)["Fridge-4"]["status"] == "ok"


# ---- T6: seed data keeps the shelf-life rule and has real cost prices -----------------
def test_seed_batches_keep_the_shelf_life_rule_and_costs_are_below_prices():
    for sku, _name, _cat, _unit, cost, price, shelf, batches in DEMO:
        assert 1 < cost < price, sku
        for _qty, days_since_received, days_left in batches:
            assert days_since_received + days_left <= shelf, sku
