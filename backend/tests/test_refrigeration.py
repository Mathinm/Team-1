"""Fridge failure, door-open alarm, temperature alerts, scheduler (S2-5: FR-15, FR-16, FR-17).

Maps to TC-REF-01..04 (and keeps TC-REF-05..07 working in test_device.py).
"""

import itertools
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import scheduler
from app.models import Alert, RefrigerationUnit, SensorReading
from app.refrigeration.service import check_open_doors
from tests.conftest import auth

_ids = itertools.count(1)


def now():
    return datetime.now(timezone.utc)


def send(client, key, kind, value, unit="Fridge-2", at=None):
    body = {"eventId": f"ev-{next(_ids)}", "unitId": unit, "type": kind, "value": value,
            "recordedAt": (at or now()).isoformat()}
    r = client.post("/api/device/readings", json=body, headers={"X-Device-Key": key})
    assert r.status_code == 200, r.text
    return r.json()


def alerts(client, **params):
    r = client.get("/api/alerts", params=params, headers=auth("manager1", "Manager"))
    return r.json()


def units(client):
    r = client.get("/api/refrigeration/units", headers=auth("manager1", "Manager"))
    assert r.status_code == 200, r.text
    return {u["unitId"]: u for u in r.json()}


def make_unit(client, key, unit="Fridge-2"):
    """Create the unit with an old reading, so later readings are the newest ones."""
    send(client, key, "temperature", 4.0, unit=unit, at=now() - timedelta(hours=1))


def set_door_limit(client, unit, minutes):
    r = client.put(f"/api/refrigeration/units/{unit}", json={"doorOpenLimitMinutes": minutes},
                   headers=auth("manager1", "Manager"))
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- FR-15 unit failure
def test_unit_failure_changes_status_and_raises_alarm(client, db, sensor_key):
    """TC-REF-01: Fridge-2 is OK, then the simulator reports power OFF."""
    assert send(client, sensor_key, "power", "ON")["alertRaised"] is False
    assert units(client)["Fridge-2"]["status"] == "OK"
    out = send(client, sensor_key, "power", "OFF")
    assert out == {"status": "stored", "alertRaised": True}
    assert units(client)["Fridge-2"]["status"] == "FAILED"
    a = alerts(client, status="active")
    assert len(a) == 1
    assert (a[0]["type"], a[0]["severity"], a[0]["unitId"]) == ("UNIT_FAILURE", "critical",
                                                                "Fridge-2")
    assert a[0]["message"] == "Fridge-2 failed: power lost"
    assert units(client)["Fridge-2"]["openAlerts"] == 1


def test_repeated_failure_reports_do_not_duplicate_the_alarm(client, db, sensor_key):
    send(client, sensor_key, "power", "OFF")
    assert send(client, sensor_key, "power", "OFF")["alertRaised"] is False
    assert len(alerts(client)) == 1


def test_recovery_clears_and_logs_the_alarm(client, db, sensor_key):
    """TC-REF-02."""
    send(client, sensor_key, "power", "OFF")
    send(client, sensor_key, "power", "ON")
    assert units(client)["Fridge-2"]["status"] == "OK"
    a = alerts(client)
    assert len(a) == 1 and a[0]["status"] == "resolved" and a[0]["resolvedAt"]
    assert "Power restored" in a[0]["resolution"]
    assert alerts(client, status="open") == []
    # a second failure later is a new alarm; the history keeps both
    send(client, sensor_key, "power", "OFF")
    assert len(alerts(client)) == 2


def test_other_fridges_are_not_affected(client, db, sensor_key):
    send(client, sensor_key, "power", "ON", unit="Fridge-1")
    send(client, sensor_key, "power", "OFF", unit="Fridge-2")
    got = units(client)
    assert got["Fridge-1"]["status"] == "OK" and got["Fridge-2"]["status"] == "FAILED"


# ---------------------------------------------------------------- FR-16 door open too long
def test_door_open_longer_than_limit_raises_alarm(client, db, sensor_key):
    """TC-REF-03: limit 2 min, door open for 3 min."""
    make_unit(client, sensor_key)
    set_door_limit(client, "Fridge-2", 2)
    t0 = now() - timedelta(minutes=3)
    assert send(client, sensor_key, "door", "OPEN", at=t0)["alertRaised"] is False
    out = send(client, sensor_key, "temperature", 4.2)  # the next reading, 3 min later
    assert out["alertRaised"] is True
    a = alerts(client, status="active")
    assert len(a) == 1 and a[0]["type"] == "DOOR_OPEN" and a[0]["unitId"] == "Fridge-2"
    assert "open for 3 min (limit 2 min)" in a[0]["message"]
    # the alarm is stamped when the limit was crossed, not when it was noticed
    raised_at = datetime.fromisoformat(a[0]["triggeredAt"].replace("Z", "+00:00"))
    assert abs((raised_at - (t0 + timedelta(minutes=2))).total_seconds()) < 1


def test_door_closed_within_limit_gives_no_alarm(client, db, sensor_key):
    """TC-REF-04: limit 2 min, open then closed after 1 min."""
    make_unit(client, sensor_key)
    set_door_limit(client, "Fridge-2", 2)
    t0 = now() - timedelta(minutes=1)
    send(client, sensor_key, "door", "OPEN", at=t0)
    send(client, sensor_key, "door", "CLOSED", at=now())
    assert alerts(client) == []
    assert units(client)["Fridge-2"]["door"] == "CLOSED"


def test_door_exactly_at_limit_raises_alarm(client, db, sensor_key):
    make_unit(client, sensor_key)
    set_door_limit(client, "Fridge-2", 2)
    t0 = now() - timedelta(minutes=2)
    send(client, sensor_key, "door", "OPEN", at=t0)
    assert send(client, sensor_key, "temperature", 4.0, at=t0 + timedelta(minutes=2))[
        "alertRaised"] is True


def test_closing_the_door_closes_the_alarm(client, db, sensor_key):
    make_unit(client, sensor_key)
    set_door_limit(client, "Fridge-2", 2)
    send(client, sensor_key, "door", "OPEN", at=now() - timedelta(minutes=4))
    send(client, sensor_key, "temperature", 4.0)
    assert len(alerts(client, status="active")) == 1
    send(client, sensor_key, "door", "CLOSED")
    a = alerts(client)
    assert len(a) == 1 and a[0]["status"] == "resolved" and a[0]["resolution"] == "Door closed"


def test_door_open_a_long_time_and_only_then_reported_closed_still_alarms(client, db, sensor_key):
    """After an outage the first thing the backend hears may be OPEN ... 10 min ... CLOSED."""
    base = now() - timedelta(minutes=30)
    send(client, sensor_key, "door", "OPEN", at=base)  # default limit 5 min
    send(client, sensor_key, "door", "CLOSED", at=base + timedelta(minutes=10))
    a = alerts(client)
    assert len(a) == 1 and a[0]["type"] == "DOOR_OPEN" and a[0]["status"] == "resolved"
    assert "open for 10 min" in a[0]["message"]


def test_scheduler_alarms_for_a_door_left_open_when_the_sensor_goes_quiet(client, db, sensor_key):
    """The simulator sent OPEN once and nothing else (FR-16): the scheduler raises the alarm."""
    send(client, sensor_key, "door", "OPEN", at=now() - timedelta(minutes=6))
    assert alerts(client) == []
    assert check_open_doors(db, now()) == 1
    db.commit()
    assert [a["type"] for a in alerts(client, status="active")] == ["DOOR_OPEN"]
    assert check_open_doors(db, now()) == 0  # not raised twice


def test_scheduler_round_runs_all_jobs_and_reports(client, db, sensor_key, Session):
    send(client, sensor_key, "door", "OPEN", at=now() - timedelta(minutes=6))
    results = scheduler.run_once(session_factory=Session)
    assert results["doors"] == 1
    assert set(results) == {"doors", "low_stock", "markdowns", "notifications"}
    assert all(v is not None for v in results.values())


def test_one_failing_job_does_not_stop_the_others(Session, monkeypatch):
    def broken(db, at):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler, "JOBS", [("a", broken), ("b", lambda db, at: "ran")])
    assert scheduler.run_once(session_factory=Session) == {"a": None, "b": "ran"}


# ---------------------------------------------------------------- temperature
def test_temperature_outside_range_alerts_until_back_in_range(client, db, sensor_key):
    assert send(client, sensor_key, "temperature", 4.5)["alertRaised"] is False
    out = send(client, sensor_key, "temperature", 11.5)
    assert out["alertRaised"] is True
    a = alerts(client, status="active")
    assert a[0]["type"] == "TEMPERATURE" and "11.5 °C is outside 0 to 8 °C" in a[0]["message"]
    assert send(client, sensor_key, "temperature", 12.0)["alertRaised"] is False  # same breach
    send(client, sensor_key, "temperature", 5.0)
    assert alerts(client, status="open") == []
    assert alerts(client)[0]["status"] == "resolved"


def test_unit_temperature_limits_can_be_changed(client, db, sensor_key):
    send(client, sensor_key, "temperature", 4.0, unit="Freezer-1")
    r = client.put("/api/refrigeration/units/Freezer-1", json={"tempMin": -25, "tempMax": -15},
                   headers=auth("manager1", "Manager"))
    assert r.status_code == 200 and (r.json()["tempMin"], r.json()["tempMax"]) == (-25, -15)
    assert send(client, sensor_key, "temperature", -18, unit="Freezer-1")["alertRaised"] is False
    assert send(client, sensor_key, "temperature", -5, unit="Freezer-1")["alertRaised"] is True


# ---------------------------------------------------------------- late and out-of-order readings
def test_older_reading_never_overwrites_newer_state(client, db, sensor_key):
    send(client, sensor_key, "temperature", 4.0)
    out = send(client, sensor_key, "temperature", 20.0, at=now() - timedelta(minutes=10))
    assert out["alertRaised"] is False  # stale: the unit has newer data
    u = units(client)["Fridge-2"]
    assert u["temperature"] == 4.0
    assert db.scalar(select(SensorReading.reading_id).where(SensorReading.value_num == 20.0))
    assert alerts(client) == []


def test_late_replay_in_order_gives_the_same_alerts_as_live(client, db, sensor_key):
    """Power OFF at minute 2, ON at minute 4, replayed 30 minutes later (offline sync)."""
    base = now() - timedelta(minutes=30)
    send(client, sensor_key, "power", "ON", at=base)
    send(client, sensor_key, "power", "OFF", at=base + timedelta(minutes=2))
    send(client, sensor_key, "power", "ON", at=base + timedelta(minutes=4))
    a = alerts(client)
    assert len(a) == 1 and a[0]["status"] == "resolved"
    assert a[0]["triggeredAt"].startswith((base + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M"))
    assert units(client)["Fridge-2"]["status"] == "OK"


# ---------------------------------------------------------------- screens and access
def test_units_endpoint_shows_latest_state(client, db, sensor_key):
    send(client, sensor_key, "temperature", 4.5)
    send(client, sensor_key, "door", "CLOSED")
    send(client, sensor_key, "power", "ON")
    u = units(client)["Fridge-2"]  # TC-REF-05: stored and shown on the refrigeration screen
    assert (u["status"], u["temperature"], u["door"], u["power"]) == ("OK", 4.5, "CLOSED", "ON")
    assert (u["doorOpenLimitMinutes"], u["tempMin"], u["tempMax"]) == (5, 0, 8)
    assert u["lastReadingAt"] and u["lastReceivedAt"] and u["openAlerts"] == 0


def test_refrigeration_access_and_validation(client, db, sensor_key):
    send(client, sensor_key, "temperature", 4.0)
    assert client.get("/api/refrigeration/units").status_code == 401
    assert client.get("/api/refrigeration/units", headers=auth("cashier1")).status_code == 403
    staff = auth("staff1", "Inventory Staff")
    assert client.get("/api/refrigeration/units", headers=staff).status_code == 200
    assert client.put("/api/refrigeration/units/Fridge-2", json={"doorOpenLimitMinutes": 3},
                      headers=staff).status_code == 403
    mgr = auth("manager1", "Manager")
    for bad in ({"doorOpenLimitMinutes": 0}, {"doorOpenLimitMinutes": "x"}, {"tempMin": 9},
                {"tempMax": -1}):
        r = client.put("/api/refrigeration/units/Fridge-2", json=bad, headers=mgr)
        assert r.status_code == 400, bad
    assert client.put("/api/refrigeration/units/Nope", json={"doorOpenLimitMinutes": 3},
                      headers=mgr).status_code == 404


def test_rejected_reading_changes_nothing(client, db, sensor_key):
    r = client.post("/api/device/readings", headers={"X-Device-Key": sensor_key}, json={
        "eventId": "bad", "unitId": "Fridge-9", "type": "temperature", "value": "abc",
        "recordedAt": now().isoformat()})
    assert r.status_code == 400
    assert db.scalar(select(RefrigerationUnit.id)) is None
    assert db.scalar(select(Alert.alert_id)) is None


def test_duplicate_reading_does_not_apply_twice(client, db, sensor_key):
    body = {"eventId": "same", "unitId": "Fridge-2", "type": "power", "value": "OFF",
            "recordedAt": now().isoformat()}
    h = {"X-Device-Key": sensor_key}
    assert client.post("/api/device/readings", json=body, headers=h).status_code == 200
    assert client.post("/api/device/readings", json=body, headers=h).status_code == 409
    assert len(alerts(client)) == 1


# ---------------------------------------------------------------- temperature history (UI-4)
def readings(client, unit, hours=None, role=("manager1", "Manager")):
    params = {} if hours is None else {"hours": hours}
    return client.get(f"/api/refrigeration/units/{unit}/readings", params=params,
                      headers=auth(*role))


def test_temperature_history_is_oldest_first_and_limited_to_the_window(client, db, sensor_key):
    send(client, sensor_key, "temperature", 3.0, at=now() - timedelta(hours=30))
    send(client, sensor_key, "temperature", 5.0, at=now() - timedelta(minutes=10))
    send(client, sensor_key, "temperature", 4.0, at=now() - timedelta(hours=2))
    send(client, sensor_key, "door", "OPEN", at=now() - timedelta(minutes=5))

    r = readings(client, "Fridge-2")
    assert r.status_code == 200, r.text
    assert [p["value"] for p in r.json()] == [4.0, 5.0]  # last 24 h, oldest first, no door

    week = readings(client, "Fridge-2", hours=168).json()
    assert [p["value"] for p in week] == [3.0, 4.0, 5.0]


def test_temperature_history_rules(client, db, sensor_key):
    make_unit(client, sensor_key)
    assert readings(client, "Fridge-9").status_code == 404
    assert readings(client, "Fridge-2", hours=0).status_code == 400
    assert readings(client, "Fridge-2", hours=169).status_code == 400
    assert readings(client, "Fridge-2", role=("staff1", "Inventory Staff")).status_code == 200
    assert readings(client, "Fridge-2", role=("cashier1", "Cashier")).status_code == 403
