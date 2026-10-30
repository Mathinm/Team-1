"""Offline buffering and synchronisation, including a 30-minute outage (S2-6: FR-19, NFR-5).

Maps to TC-REP-06, TC-REP-07 and TC-NFR-07 (SRS TC-REP-02, TC-REL-02).

The real simulators' DeviceClient (simulators/device_client.py) is used unchanged. Only its
network call is replaced by the in-process API, so "the network" can be switched off and the
30 minutes are simulated: every event carries the time it would have had, and the whole test
takes seconds. simulators/outage_test.py repeats this against the running Docker stack in real time.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.alerts.service import fmt
from app.models import Alert, Batch, Sale, SensorReading
from tests.conftest import auth, stock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "simulators"))
from device_client import DeviceClient  # noqa: E402


class FakeNetwork(DeviceClient):
    """The simulator's client, wired to the test API instead of the internet."""

    def __init__(self, http, key, buffer_file):
        super().__init__("http://pms.test", key, buffer_file)
        self.http = http
        self.online = True
        self.posts = 0

    def _post(self, path, payload):
        if not self.online:
            return 0, {}
        self.posts += 1
        r = self.http.post(path, json=payload, headers={"X-Device-Key": self.key})
        return r.status_code, (r.json() if r.content else {})


@pytest.fixture()
def pos(client, pos_key, tmp_path):
    return FakeNetwork(client, pos_key, tmp_path / "pos-buffer.jsonl")


@pytest.fixture()
def sensors(client, sensor_key, tmp_path):
    return FakeNetwork(client, sensor_key, tmp_path / "sensor-buffer.jsonl")


def sale_event(n, when, qty=1, sku="TOM-01"):
    return {"eventId": f"sale-{n}", "sku": sku, "quantity": qty, "unit": "kg",
            "soldAt": when.isoformat()}


def reading_event(n, unit, kind, value, when):
    return {"eventId": f"rd-{n}", "unitId": unit, "type": kind, "value": value,
            "recordedAt": when.isoformat()}


SALES, READINGS = "/api/device/sales", "/api/device/readings"


def count(db, model):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


# ---------------------------------------------------------------- the client itself
def test_events_wait_in_the_buffer_while_offline_and_arrive_in_order(client, seeded, pos):
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    pos.online = False
    for i in range(3):  # TC-REP-06: disconnect, record 3 sales
        assert pos.send(SALES, sale_event(i, base + timedelta(minutes=i))) == "buffered"
    assert pos.pending_count() == 3 and count(seeded, Sale) == 0
    pos.online = True  # reconnect: they go out on the next event, oldest first
    assert pos.send(SALES, sale_event(3, base + timedelta(minutes=3))) == "delivered"
    assert pos.pending_count() == 0
    order = seeded.scalars(select(Sale.event_id).order_by(Sale.sale_id)).all()
    assert order == ["sale-0", "sale-1", "sale-2", "sale-3"]  # no duplicates, same order
    assert stock(seeded, 1) == Decimal(37 - 4)  # stock is correct


def test_a_new_event_never_overtakes_the_waiting_ones(client, seeded, pos):
    pos.online = False
    pos.send(SALES, sale_event(0, datetime.now(timezone.utc)))
    assert pos.send(SALES, sale_event(1, datetime.now(timezone.utc))) == "buffered"
    assert [i["event"]["eventId"] for i in pos.pending()] == ["sale-0", "sale-1"]
    assert pos.posts == 0  # while offline nothing is even attempted twice per event


def test_buffer_survives_a_restart_of_the_simulator(client, seeded, pos, tmp_path):
    pos.online = False
    pos.send(SALES, sale_event(0, datetime.now(timezone.utc)))
    reborn = FakeNetwork(client, pos.key, tmp_path / "pos-buffer.jsonl")  # new process
    assert reborn.pending_count() == 1
    assert reborn.flush() == 1 and count(seeded, Sale) == 1


def test_resending_everything_after_a_crash_creates_no_duplicates(client, seeded, pos, tmp_path):
    """The simulator delivered the events but died before it rewrote the buffer."""
    pos.online = False
    base = datetime.now(timezone.utc) - timedelta(minutes=5)
    for i in range(5):
        pos.send(SALES, sale_event(i, base + timedelta(seconds=i)))
    saved = pos.buffer.read_text()
    pos.online = True
    assert pos.flush() == 5
    pos.buffer.write_text(saved)  # the crash: the buffer still lists all 5
    assert pos.flush() == 5  # every one is answered 409 and dropped
    assert count(seeded, Sale) == 5 and stock(seeded, 1) == Decimal(32)
    assert pos.pending_count() == 0 and not pos.rejected.exists()


def test_half_written_last_line_does_not_stop_the_simulator(client, seeded, pos):
    pos.online = False
    pos.send(SALES, sale_event(0, datetime.now(timezone.utc)))
    with pos.buffer.open("a") as f:
        f.write('{"path": "/api/device/sa')  # power cut in the middle of a write
    pos.online = True
    assert pos.flush() == 1
    assert count(seeded, Sale) == 1
    assert pos.corrupt.read_text().startswith('{"path": "/api/device/sa')
    assert pos.pending_count() == 0


def test_server_errors_keep_the_event_and_rejections_do_not_block_the_queue(client, seeded, pos):
    now = datetime.now(timezone.utc)
    pos.online = False
    pos.send(SALES, sale_event(0, now, sku="NOPE-1"))  # will be refused for good (404)
    pos.send(SALES, sale_event(1, now))
    pos.online = True
    assert pos.flush() == 2
    assert count(seeded, Sale) == 1  # the good one arrived behind the refused one
    rejected = [json.loads(x) for x in pos.rejected.read_text().splitlines()]
    assert len(rejected) == 1 and rejected[0]["status"] == 404  # kept for the operator


def test_wrong_key_is_not_buffered_forever(client, seeded, pos):
    pos.key = "wrong"
    with pytest.raises(SystemExit):
        pos.send(SALES, sale_event(0, datetime.now(timezone.utc)))


# ---------------------------------------------------------------- the 30-minute outage
def test_30_minute_outage_loses_nothing(client, seeded, pos, sensors):
    """TC-NFR-07 / NFR-5: 30 minutes without network while sales and readings keep coming."""
    manager = auth("manager1", "Manager")
    start = datetime.now(timezone.utc) - timedelta(minutes=40)
    sales_sent = readings_sent = 0
    sold_kg = Decimal(0)
    n = 0

    def at(seconds):
        return start + timedelta(seconds=seconds)

    # 0-5 min: the network is up; events arrive live.
    for sec in range(0, 300, 5):
        n += 1
        assert sensors.send(READINGS, reading_event(n, "Fridge-1", "temperature", 4.0, at(sec))) \
            == "delivered"
        readings_sent += 1
    assert pos.send(SALES, sale_event("live", at(10), qty=1)) == "delivered"
    sales_sent, sold_kg = 1, Decimal(1)

    # 5-35 min: the OUTAGE. A reading of each unit every 5 s, a sale every 50 s, plus a story:
    #   Fridge-2 door open 10:00-12:00 (2 min: fine), Fridge-1 door open 20:00-27:00 (7 min:
    #   alarm), Fridge-2 power off 15:00-16:00 (failure), Fridge-1 too warm 28:20-29:00.
    pos.online = sensors.online = False
    story = {
        600: ("Fridge-2", "door", "OPEN"), 720: ("Fridge-2", "door", "CLOSED"),
        900: ("Fridge-2", "power", "OFF"), 960: ("Fridge-2", "power", "ON"),
        1200: ("Fridge-1", "door", "OPEN"), 1620: ("Fridge-1", "door", "CLOSED"),
        1700: ("Fridge-1", "temperature", 11.0), 1740: ("Fridge-1", "temperature", 4.0),
    }
    for sec in range(300, 300 + 30 * 60, 5):
        for unit in ("Fridge-1", "Fridge-2"):
            n += 1
            if (sec - 300) in story and story[sec - 300][0] == unit:
                _, kind, value = story[sec - 300]
            else:
                kind, value = "temperature", 4.2
            assert sensors.send(READINGS, reading_event(n, unit, kind, value, at(sec))) \
                == "buffered"
            readings_sent += 1
        if (sec - 300) % 50 == 0:
            assert pos.send(SALES, sale_event(sec, at(sec), qty=0.5)) == "buffered"
            sales_sent += 1
            sold_kg += Decimal("0.5")
    assert count(seeded, SensorReading) == 60 and count(seeded, Sale) == 1  # nothing got through
    assert sensors.pending_count() == readings_sent - 60 and pos.pending_count() == 36

    # 35 min: the network is back. The next event of each source flushes its backlog.
    pos.online = sensors.online = True
    assert sensors.send(READINGS, reading_event("after", "Fridge-1", "temperature", 4.1,
                                                at(300 + 1800 + 5))) == "delivered"
    readings_sent += 1
    assert pos.flush() == 36

    # Nothing lost, nothing doubled, nothing rejected, queues empty.
    assert count(seeded, SensorReading) == readings_sent
    assert count(seeded, Sale) == sales_sent
    assert sensors.pending_count() == pos.pending_count() == 0
    assert not sensors.rejected.exists() and not pos.rejected.exists()
    assert seeded.scalar(select(func.count(func.distinct(SensorReading.event_id)))) == readings_sent
    # Stock matches what was sold; every sale kept its original time.
    assert stock(seeded, 1) == Decimal(37) - sold_kg
    first_blocked = seeded.scalars(select(Sale).where(Sale.event_id == "sale-300")).one()
    assert abs((first_blocked.sold_at.replace(tzinfo=timezone.utc) - at(300)).total_seconds()) < 1
    held_back = seeded.scalars(select(SensorReading).where(SensorReading.event_id == "rd-61")).one()
    recorded = held_back.recorded_at.replace(tzinfo=timezone.utc)
    received = held_back.received_at.replace(tzinfo=timezone.utc)
    assert abs((recorded - at(300)).total_seconds()) < 1  # kept its own time ...
    assert received - recorded > timedelta(minutes=30)  # ... although it arrived 30+ min later

    # The alerts are what a live system would have produced, with the original times.
    rows = client.get("/api/alerts", headers=manager).json()
    kinds = sorted((a["type"], a["unitId"]) for a in rows)
    assert kinds == [("DOOR_OPEN", "Fridge-1"), ("TEMPERATURE", "Fridge-1"),
                     ("UNIT_FAILURE", "Fridge-2")]  # the 2-minute door open raised nothing
    assert all(a["status"] == "resolved" for a in rows)  # everything ended during the outage
    door = next(a for a in rows if a["type"] == "DOOR_OPEN")
    triggered = datetime.fromisoformat(door["triggeredAt"].replace("Z", "+00:00"))
    assert abs((triggered - (at(300 + 1200) + timedelta(minutes=5))).total_seconds()) < 1
    # and the units show their final state
    units = {u["unitId"]: u for u in client.get("/api/refrigeration/units", headers=manager).json()}
    assert units["Fridge-1"]["door"] == "CLOSED" and units["Fridge-2"]["status"] == "OK"
    assert seeded.scalar(select(func.count()).select_from(Alert)) == 3
    assert fmt(seeded.scalar(select(func.sum(Batch.quantity)).where(Batch.product_id == 1))) == \
        fmt(Decimal(37) - sold_kg)


def test_outage_with_low_stock_alert_raised_during_sync(client, seeded, pos):
    """Sales recorded offline still trigger the low-stock alert when they are synchronised."""
    pos.online = False
    base = datetime.now(timezone.utc) - timedelta(minutes=20)
    for i in range(30):
        pos.send(SALES, sale_event(i, base + timedelta(seconds=i * 30)))  # 30 kg, stock 37 -> 7
    manager = auth("manager1", "Manager")
    assert client.get("/api/alerts", headers=manager).json() == []
    pos.online = True
    assert pos.flush() == 30
    rows = client.get("/api/alerts", headers=manager).json()
    assert [a["type"] for a in rows] == ["LOW_STOCK"]  # raised once, when stock first dropped to 9
    assert "Tomato is low: 9 kg left" in rows[0]["message"]
