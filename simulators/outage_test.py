#!/usr/bin/env python3
r"""Network-outage test against the running system (NFR-5, FR-19; TC-NFR-07, TC-REP-06/07).

Stops the backend for N minutes while a POS and two fridge sensors keep producing events, starts
it again, lets the simulators synchronise, then PROVES that nothing was lost or duplicated:

  1. every event is sent once more; the backend must answer 409 (= "already stored") to all of
     them - a 201/200 would mean that event had never arrived;
  2. no event was refused, and nothing is left waiting in the buffers;
  3. the stock of the sold product went down by exactly the quantity sold.

    # PowerShell, from the project root (Docker running, devices registered, see README)
    $env:PMS_POS_KEY    = "<pos key>"
    $env:PMS_SENSOR_KEY = "<sensor key>"
    py simulators\outage_test.py --minutes 30          # the real test (takes ~32 minutes)
    py simulators\outage_test.py --minutes 2 --interval 2   # quick rehearsal

By default it runs `docker compose stop backend` / `start backend` itself. To cut the network
another way use --manual (it asks you to press Enter at each step) or --stop-cmd / --start-cmd.
Uses a stock check through the API: needs the Admin login (--admin-user / --admin-password).
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from device_client import DEFAULT_URL, DeviceClient

ROOT = Path(__file__).resolve().parent.parent


def http(method, url, body=None, token=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError):
        return 0, {}


def wait_healthy(base, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if http("GET", base + "/api/health")[0] == 200:
            return True
        time.sleep(2)
    return False


def stock_of(base, token, sku):
    status, products = http("GET", base + "/api/products", token=token)
    if status != 200:
        return None
    return next((p["stock"] for p in products if p["sku"].upper() == sku.upper()), None)


def run_cmd(cmd):
    print(f"  $ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=ROOT).returncode == 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--url", default=os.getenv("PMS_URL", DEFAULT_URL))
    p.add_argument("--pos-key", default=os.getenv("PMS_POS_KEY"))
    p.add_argument("--sensor-key", default=os.getenv("PMS_SENSOR_KEY"))
    p.add_argument("--minutes", type=float, default=30, help="length of the outage")
    p.add_argument("--interval", type=float, default=5, help="seconds between rounds")
    p.add_argument("--sale-every", type=int, default=10, help="one sale every N rounds")
    p.add_argument("--sku", default="TOM-01")
    p.add_argument("--sale-qty", type=float, default=0.5)
    p.add_argument("--admin-user", default="admin")
    p.add_argument("--admin-password", default=os.getenv("ADMIN_PASSWORD", "admin123"))
    p.add_argument("--manual", action="store_true", help="you cut and restore the network")
    p.add_argument("--stop-cmd", default="docker compose stop backend")
    p.add_argument("--start-cmd", default="docker compose start backend")
    a = p.parse_args()
    if not (a.pos_key and a.sensor_key):
        p.error("set PMS_POS_KEY and PMS_SENSOR_KEY (or --pos-key / --sensor-key)")
    base = a.url.rstrip("/")

    if not wait_healthy(base, 10):
        print("The backend is not answering. Start it first: docker compose up")
        return 2
    status, body = http("POST", base + "/api/auth/login",
                        {"userId": a.admin_user, "password": a.admin_password})
    token = body.get("token") if status == 200 else None
    before = stock_of(base, token, a.sku) if token else None
    print(f"Stock of {a.sku} before: {before}" if before is not None
          else "Admin login failed: the stock check will be skipped.")

    run = uuid.uuid4().hex[:8]
    here = Path(__file__).resolve().parent
    pos = DeviceClient(base, a.pos_key, str(here / f"outage-pos-{run}.jsonl"))
    sensors = DeviceClient(base, a.sensor_key, str(here / f"outage-sensor-{run}.jsonl"))
    sent: list[tuple[str, dict, DeviceClient]] = []  # (path, event, client) of every event made
    sold = 0.0

    def make(path, client, event):
        sent.append((path, event, client))
        return client.send(path, event)

    def stamp():
        return datetime.now(timezone.utc).isoformat()

    # ---- 1. cut the network
    print(f"\n[1/4] Cutting the network for {a.minutes:g} minutes ...")
    if a.manual:
        input("  Stop the backend / disconnect now, then press Enter. ")
    elif not run_cmd(a.stop_cmd):
        print("Could not stop the backend.")
        return 2
    time.sleep(1)

    # ---- 2. keep producing events
    print("[2/4] Sensors and POS keep working (everything is buffered) ...")
    end, n, rounds = time.time() + a.minutes * 60, 0, 0
    while time.time() < end:
        rounds += 1
        for unit in ("Fridge-1", "Fridge-2"):
            n += 1
            make("/api/device/readings", sensors, {
                "eventId": f"outage-{run}-r{n}", "unitId": unit, "type": "temperature",
                "value": 4.2, "recordedAt": stamp()})
        if rounds % a.sale_every == 0:
            n += 1
            make("/api/device/sales", pos, {
                "eventId": f"outage-{run}-s{n}", "sku": a.sku, "quantity": a.sale_qty,
                "soldAt": stamp()})
            sold += a.sale_qty
        left = int(end - time.time())
        print(f"\r  {left // 60:02d}:{left % 60:02d} left | events made {len(sent)} | "
              f"waiting: pos {pos.pending_count()}, sensors {sensors.pending_count()}   ",
              end="", flush=True)
        time.sleep(a.interval)
    print()

    # ---- 3. network back: synchronise
    print("[3/4] Restoring the network and synchronising ...")
    if a.manual:
        input("  Start the backend / reconnect now, then press Enter. ")
    elif not run_cmd(a.start_cmd):
        print("Could not start the backend.")
        return 2
    if not wait_healthy(base, 180):
        print("FAIL: the backend did not come back within 3 minutes.")
        return 1
    started = time.time()
    while (pos.pending_count() or sensors.pending_count()) and time.time() - started < 300:
        pos.flush()
        sensors.flush()
        time.sleep(1)
    print(f"  synchronised in {time.time() - started:.0f} s")

    # ---- 4. prove it
    print("[4/4] Checking that every event arrived exactly once ...")
    missing = 0
    for path, event, client in sent:
        code, _ = client._post(path, event)  # the resend: 409 = it is stored (once)
        if code != 409:
            missing += 1
    waiting = pos.pending_count() + sensors.pending_count()
    refused = sum(1 for c in (pos, sensors) if c.rejected.exists())
    after = stock_of(base, token, a.sku) if token else None
    stock_ok = None
    if before is not None and after is not None:
        stock_ok = abs((before - sold) - after) < 0.001

    results = [
        (f"all {len(sent)} events stored (none missing)", missing == 0),
        ("nothing left in the buffers", waiting == 0),
        ("no event refused by the backend", refused == 0),
    ]
    if stock_ok is not None:
        results.append((f"stock {before:g} - sold {sold:g} = {after:g}", stock_ok))
    print()
    for text, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {text}")
    ok = all(r for _, r in results)
    if ok:  # tidy up the temporary buffers of this run
        for c in (pos, sensors):
            c.buffer.unlink(missing_ok=True)
    print("\nRESULT:", "PASS - no data lost in the outage" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
