#!/usr/bin/env python3
"""Sensor simulator: sends temperature, door and power readings to POST /api/device/readings.

    export PMS_DEVICE_KEY=<key from: python -m app.device.provision fridge-sensors sensor>
    python sensor_simulator.py                          # 3 fridges, a reading every 5 s
    python sensor_simulator.py --units Fridge-1,Fridge-2 --interval 1 --count 30
    python sensor_simulator.py --once --unit Fridge-2 --type door --value OPEN
    python sensor_simulator.py --once --unit Fridge-2 --type power --value OFF
    python sensor_simulator.py --once --unit Fridge-1 --type temperature --value 11.5
    python sensor_simulator.py --once --unit Fridge-1 --type door --value OPEN --ago 600
        # --ago S: the reading is stamped S seconds in the past (door "opened 10 min ago")

Readings made while the backend is down are kept in sensor-buffer.jsonl and sent later with
their original timestamps.
"""

import argparse
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from device_client import DEFAULT_URL, DeviceClient


def make_event(unit_id: str, kind: str, value, ago: float = 0) -> dict:
    recorded = datetime.now(timezone.utc) - timedelta(seconds=ago)
    return {
        "eventId": str(uuid.uuid4()),
        "unitId": unit_id,
        "type": kind,
        "value": value,
        "recordedAt": recorded.isoformat(),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--url", default=os.getenv("PMS_URL", DEFAULT_URL))
    p.add_argument("--key", default=os.getenv("PMS_DEVICE_KEY"))
    p.add_argument("--units", default="Fridge-1,Fridge-2,Fridge-3")
    p.add_argument("--interval", type=float, default=5.0, help="seconds between rounds")
    p.add_argument("--count", type=int, default=0, help="stop after N rounds (0 = run forever)")
    p.add_argument("--once", action="store_true", help="send one reading")
    p.add_argument("--unit")
    p.add_argument("--type", choices=["temperature", "door", "power"])
    p.add_argument("--value")
    p.add_argument("--ago", type=float, default=0, help="--once only: stamp the reading S seconds ago")
    p.add_argument("--buffer", default="sensor-buffer.jsonl")
    a = p.parse_args()
    if not a.key:
        p.error("set PMS_DEVICE_KEY or pass --key")

    client = DeviceClient(a.url, a.key, a.buffer)
    path = "/api/device/readings"
    if a.once:
        if not (a.unit and a.type and a.value is not None):
            p.error("--once needs --unit, --type and --value")
        value = a.value  # sent as typed so bad values (e.g. "abc") can be tried on purpose
        if a.type == "temperature":
            try:
                value = float(a.value)
            except ValueError:
                pass
        outcome = client.send(path, make_event(a.unit, a.type, value, a.ago))
        print(f"{a.unit} {a.type}={a.value}: {outcome}")
        return

    units = [u.strip() for u in a.units.split(",") if u.strip()]
    temps = {u: random.uniform(3.0, 5.0) for u in units}
    door_open = dict.fromkeys(units, False)
    rounds = 0
    try:
        while not a.count or rounds < a.count:
            rounds += 1
            for u in units:
                temps[u] = min(7.5, max(1.5, temps[u] + random.uniform(-0.4, 0.4)))
                events = [make_event(u, "temperature", round(temps[u], 1))]
                if random.random() < 0.1:  # doors open now and then, and are closed again
                    door_open[u] = not door_open[u]
                    events.append(make_event(u, "door", "OPEN" if door_open[u] else "CLOSED"))
                events.append(make_event(u, "power", "ON"))
                for e in events:
                    outcome = client.send(path, e)
                    waiting = f" (waiting to sync: {client.pending_count()})" if outcome == "buffered" else ""
                    print(f"[{rounds}] {u} {e['type']}={e['value']}: {outcome}{waiting}")
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    print(f"Stopped. {client.pending_count()} reading(s) still waiting in {a.buffer}.")


if __name__ == "__main__":
    main()
