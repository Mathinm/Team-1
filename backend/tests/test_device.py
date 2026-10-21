"""Device API: device keys, eventId de-duplication, POS sales, sensor readings (FR-17, FR-19)."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.device.auth import create_device, hash_key
from app.models import Device, Sale, SensorReading
from tests.conftest import stock

NOW = datetime.now(timezone.utc).isoformat()


def key(k):
    return {"X-Device-Key": k}


def pos_sale(client, k, event="e1", **over):
    body = {"eventId": event, "sku": "TOM-01", "quantity": 5, "unit": "kg", "soldAt": NOW}
    body.update(over)
    return client.post("/api/device/sales", json=body, headers=key(k))


def reading(client, k, event="r1", **over):
    body = {"eventId": event, "unitId": "Fridge-1", "type": "temperature", "value": 4.5,
            "recordedAt": NOW}
    body.update(over)
    return client.post("/api/device/readings", json=body, headers=key(k))


# ---- device key (TC-REF-06, STRIDE spoofing) --------------------------------------------
def test_missing_or_wrong_key_is_401_and_nothing_is_stored(client, seeded, sensor_key):
    for headers in ({}, key("wrong"), key("")):
        r = client.post("/api/device/readings", headers=headers, json={
            "eventId": "x", "unitId": "F", "type": "temperature", "value": 4, "recordedAt": NOW})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_DEVICE_KEY"
    assert seeded.scalar(select(func.count()).select_from(SensorReading)) == 0


def test_user_login_token_does_not_work_as_device_key(client, seeded, pos_key):
    from tests.conftest import auth

    r = client.post("/api/device/sales", headers=auth("admin", "Admin"),
                    json={"eventId": "x", "sku": "TOM-01", "quantity": 1})
    assert r.status_code == 401


def test_only_a_hash_of_the_key_is_stored(db, pos_key):
    dev = db.scalars(select(Device)).one()
    assert dev.key_hash == hash_key(pos_key) and pos_key not in dev.key_hash


def test_deactivated_device_is_rejected(client, seeded, pos_key):
    seeded.scalars(select(Device)).one().active = False
    seeded.commit()
    assert pos_sale(client, pos_key).status_code == 401


def test_each_key_only_works_for_its_own_kind(client, seeded, pos_key, sensor_key):
    assert reading(client, pos_key).status_code == 403
    assert pos_sale(client, sensor_key).status_code == 403
    assert stock(seeded, 1) == 37


def test_create_device_rejects_unknown_kind(db):
    import pytest

    with pytest.raises(ValueError):
        create_device(db, "x", "toaster")


# ---- POS sales --------------------------------------------------------------------------
def test_pos_sale_uses_fefo_like_manual_sales(client, seeded, pos_key):
    r = pos_sale(client, pos_key, quantity=15)
    assert r.status_code == 201
    body = r.json()
    assert [(b["batchId"], b["qty"]) for b in body["batchesUsed"]] == [(101, 12), (102, 3)]
    assert body["remainingStock"] == 22 and body["saleId"]
    sale = seeded.scalars(select(Sale)).one()
    assert (sale.source, sale.recorded_by, sale.event_id) == ("device", "device:pos-1", "e1")


def test_pos_sale_blocks_expired_and_insufficient(client, seeded, pos_key):
    r = pos_sale(client, pos_key, event="a", sku="BRD-01", quantity=1, unit="piece")
    assert (r.status_code, r.json()["error"]["code"]) == (422, "BATCH_EXPIRED")
    r = pos_sale(client, pos_key, event="b", quantity=40)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "INSUFFICIENT_STOCK")
    assert stock(seeded, 1) == 37


def test_sold_at_is_optional_and_original_time_is_kept(client, seeded, pos_key):
    r = pos_sale(client, pos_key, event="old", soldAt="2026-10-18T08:15:00Z")
    assert r.status_code == 201
    sale = seeded.scalars(select(Sale)).one()
    assert (sale.sold_at.year, sale.sold_at.month, sale.sold_at.day, sale.sold_at.hour) == (
        2026, 10, 18, 8)
    body = {"eventId": "nots", "sku": "TOM-01", "quantity": 1}
    assert client.post("/api/device/sales", json=body, headers=key(pos_key)).status_code == 201


# ---- eventId de-duplication (FR-19, ADR-5) ----------------------------------------------
def test_resent_sale_is_409_and_does_not_deduct_twice(client, seeded, pos_key):
    assert pos_sale(client, pos_key, event="dup", quantity=5).status_code == 201
    r = pos_sale(client, pos_key, event="dup", quantity=5)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_EVENT"
    assert stock(seeded, 1) == 32
    assert seeded.scalar(select(func.count()).select_from(Sale)) == 1


def test_same_event_id_from_two_devices_is_not_a_duplicate(client, seeded, pos_key):
    other = create_device(seeded, "pos-2", "pos")
    assert pos_sale(client, pos_key, event="1", quantity=1).status_code == 201
    assert pos_sale(client, other, event="1", quantity=1).status_code == 201


def test_rejected_sale_does_not_burn_its_event_id(client, seeded, pos_key):
    assert pos_sale(client, pos_key, event="retry", quantity=40).status_code == 422
    assert pos_sale(client, pos_key, event="retry", quantity=5).status_code == 201


def test_malformed_sale_is_400(client, seeded, pos_key):
    for over in ({"quantity": "abc"}, {"quantity": 0}, {"eventId": ""}, {"soldAt": "not a time"}):
        r = pos_sale(client, pos_key, **over)
        assert r.status_code == 400 and r.json()["error"]["code"] in ("VALIDATION", "INVALID")
    no_event = {"sku": "TOM-01", "quantity": 1}
    r = client.post("/api/device/sales", json=no_event, headers=key(pos_key))
    assert r.status_code == 400  # eventId missing
    assert stock(seeded, 1) == 37


# ---- sensor readings (TC-REF-05, TC-REF-07) ---------------------------------------------
def test_valid_temperature_reading_is_stored(client, seeded, sensor_key):
    r = reading(client, sensor_key)
    assert r.status_code == 200
    assert r.json() == {"status": "stored", "alertRaised": False}
    row = seeded.scalars(select(SensorReading)).one()
    assert (row.unit_id, row.type, row.value_num, row.event_id) == ("Fridge-1", "temperature",
                                                                    4.5, "r1")


def test_numeric_string_temperature_is_accepted(client, seeded, sensor_key):
    assert reading(client, sensor_key, value="-18.5").status_code == 200


def test_door_and_power_readings(client, seeded, sensor_key):
    assert reading(client, sensor_key, event="d", type="door", value="open").status_code == 200
    assert reading(client, sensor_key, event="p", type="power", value="OFF").status_code == 200
    rows = {r.type: r.value_text for r in seeded.scalars(select(SensorReading))}
    assert rows == {"door": "OPEN", "power": "OFF"}


def test_malformed_readings_are_400_with_message_and_not_stored(client, seeded, sensor_key):
    bad = [
        {"value": "abc"}, {"value": 500}, {"value": "nan"}, {"type": "humidity"},
        {"type": "door", "value": "ajar"}, {"type": "power", "value": 1}, {"recordedAt": "x"},
        {"unitId": ""},
    ]
    for i, over in enumerate(bad):
        r = reading(client, sensor_key, event=f"b{i}", **over)
        assert r.status_code == 400, over
        assert r.json()["error"]["message"]
    r = reading(client, sensor_key, value="abc")
    assert "Temperature must be a number" in r.json()["error"]["message"]
    assert seeded.scalar(select(func.count()).select_from(SensorReading)) == 0


def test_resent_reading_is_409_and_stored_once(client, seeded, sensor_key):
    assert reading(client, sensor_key, event="same").status_code == 200
    r = reading(client, sensor_key, event="same")
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_EVENT"
    assert seeded.scalar(select(func.count()).select_from(SensorReading)) == 1


def test_buffered_reading_keeps_original_timestamp(client, seeded, sensor_key):
    reading(client, sensor_key, recordedAt="2026-10-20T01:00:00+05:30")
    row = seeded.scalars(select(SensorReading)).one()
    assert (row.recorded_at.day, row.recorded_at.hour, row.recorded_at.minute) == (19, 19, 30)
