"""TC-PERF-02 (NFR-2): alerts reach staff within 60 s for 95% of triggered alerts.

Triggers 20 real alerts, 5 of each kind named in the test case, through the same paths the
store uses, one every --gap seconds:
  temperature   a sensor reports 15 C for a fridge (safe range 0-8 C)     -> TEMPERATURE
  unit fault    a sensor reports power OFF for a fridge                    -> UNIT_FAILURE
  low stock     the POS sells 3 kg of LS-n, taking it from 12 to 9 (< 10)  -> LOW_STOCK
  expiry        a batch that expires today is received                     -> EXPIRY

For each alert it measures, from the moment the trigger was sent:
  delivered   until the alert's notification was sent to staff (deliveryStatus "sent");
  on screen   until the alert is in GET /api/alerts, plus one Alerts-screen refresh
              (REFRESH_MS in frontend/src/pages/AlertsPage.jsx), the worst case for a
              screen that is already open.
Both must be within 60 s for 95% of the alerts.

    python perf/alert_latency.py --base http://localhost:3000 --seed perf/seed.json

Needs the stack running with the scheduler on (the default). Exit code 0 = PASS, 1 = FAIL.
"""

import argparse
import math
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from common import frontend_constant, load_seed, login, summary

KINDS = ("temperature", "unit fault", "low stock", "expiry")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description="TC-PERF-02: alert delivery time (NFR-2)")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--seed", default="perf/seed.json")
    ap.add_argument("--per-kind", type=int, default=5, help="alerts of each kind (5 x 4 = 20)")
    ap.add_argument("--gap", type=float, default=2.0, help="seconds between triggers")
    ap.add_argument("--limit", type=float, default=60.0, help="NFR-2 target in seconds")
    ap.add_argument("--timeout", type=float, default=150.0, help="give up on an alert after")
    ap.add_argument("--store-tz", default="Asia/Kolkata", help="STORE_TIMEZONE of the backend")
    args = ap.parse_args()

    seed = load_seed(args.seed)
    screen_refresh = frontend_constant("pages/AlertsPage.jsx", "REFRESH_MS", 10000) / 1000
    staff_user = next(u["userId"] for u in seed["users"] if u["role"] == "Inventory Staff")
    staff = httpx.Client(base_url=args.base, timeout=15)
    login(staff, staff_user, seed["password"])
    pos = httpx.Client(base_url=args.base, timeout=15, headers={"X-Device-Key": seed["posKey"]})
    run = uuid.uuid4().hex[:6]  # new fridge names every run, so earlier alerts don't interfere

    def sell(sku: str, qty: float) -> httpx.Response:
        return pos.post("/api/device/sales",
                        json={"eventId": f"alert-{uuid.uuid4()}", "sku": sku, "quantity": qty})

    def reading(i: int, unit: str, kind: str, value) -> httpx.Response:
        sensor = seed["sensors"][i % len(seed["sensors"])]
        return httpx.post(f"{args.base}/api/device/readings", timeout=15,
                          headers={"X-Device-Key": sensor["key"]},
                          json={"eventId": f"alert-{uuid.uuid4()}", "unitId": unit,
                                "type": kind, "value": value, "recordedAt": now_iso()})

    # Low-stock products start at exactly 12 kg, so selling 3 crosses the threshold of 10.
    low = seed["lowStock"][: args.per_kind]
    stock = {p["sku"]: p["stock"] for p in staff.get("/api/products").raise_for_status().json()}
    for p in low:
        have = stock[p["sku"]]
        if have > 12:
            sell(p["sku"], round(have - 12, 3)).raise_for_status()
        elif have < 12:
            staff.post("/api/restocks", json={"productId": p["productId"],
                                              "quantity": round(12 - have, 3),
                                              "supplierId": seed["supplierId"]}).raise_for_status()
    time.sleep(1)

    today = datetime.now(ZoneInfo(args.store_tz)).date().isoformat()
    expiry_product = next(p for p in staff.get("/api/products").json() if p["sku"] == "LT-002")

    # Only alerts created from now on count: remember the newest alert number (newest first).
    newest = staff.get("/api/alerts", params={"limit": 1}).raise_for_status().json()
    start_id = newest[0]["alertId"] if newest else 0

    # Each trigger: (kind, time sent, how to recognise its alert in GET /api/alerts)
    triggers: list[tuple[str, float, callable]] = []
    seen: dict[int, float] = {}
    delivered: dict[int, float] = {}
    status: dict[int, str] = {}
    all_sent = threading.Event()

    def watch() -> None:
        """Look at the alert list once a second, from the first trigger on, like a person
        watching; note when each alert first appears and when it is delivered."""
        watcher = httpx.Client(base_url=args.base, timeout=15)
        login(watcher, staff_user, seed["password"])
        while True:
            done_sending = all_sent.is_set()
            current = list(triggers)
            alerts = watcher.get("/api/alerts", params={"limit": 500}).raise_for_status().json()
            now = time.monotonic()
            for n, (_kind, sent, match) in enumerate(current):
                a = next((a for a in alerts if a["alertId"] > start_id and match(a)), None)
                if a is None:
                    continue
                seen.setdefault(n, now - sent)
                status[n] = a["deliveryStatus"]
                if a["deliveryStatus"] == "sent":
                    delivered.setdefault(n, now - sent)
            if done_sending and (len(delivered) == len(current)
                                 or now > current[-1][1] + args.timeout):
                return
            time.sleep(1)

    watcher_thread = threading.Thread(target=watch, daemon=True)
    watcher_thread.start()
    print(f"Triggering {args.per_kind * len(KINDS)} alerts, one every {args.gap:g} s...")
    for i in range(args.per_kind):
        for kind in KINDS:
            sent = time.monotonic()
            if kind == "temperature":
                unit = f"PT-{run}-T{i + 1}"
                r = reading(i, unit, "temperature", 15.0)
                match = lambda a, u=unit: a["type"] == "TEMPERATURE" and a["unitId"] == u  # noqa: E731
            elif kind == "unit fault":
                unit = f"PT-{run}-P{i + 1}"
                r = reading(i, unit, "power", "OFF")
                match = lambda a, u=unit: a["type"] == "UNIT_FAILURE" and a["unitId"] == u  # noqa: E731
            elif kind == "low stock":
                pid = low[i]["productId"]
                r = sell(low[i]["sku"], 3)
                match = lambda a, p=pid: a["type"] == "LOW_STOCK" and a["productId"] == p  # noqa: E731
            else:
                r = staff.post("/api/batches", json={
                    "productId": expiry_product["productId"], "supplierId": seed["supplierId"],
                    "quantity": 1, "unit": expiry_product["unit"], "receivedAt": now_iso(),
                    "expiryDate": today})
                batch = r.json().get("batchId") if r.status_code == 201 else None
                match = lambda a, b=batch: (  # noqa: E731
                    a["type"] == "EXPIRY" and f"batch {b} " in a["message"])
            if r.status_code not in (200, 201):
                print(f"  {kind} trigger failed: {r.status_code} {r.text[:150]}")
                match = lambda a: False  # noqa: E731  (counts as never arrived)
            triggers.append((kind, sent, match))
            time.sleep(max(0.0, args.gap - (time.monotonic() - sent)))

    all_sent.set()
    watcher_thread.join()

    # Tidy up: fridges back to normal, low-stock products back to 12 (closes their alerts).
    for i in range(args.per_kind):
        reading(i, f"PT-{run}-T{i + 1}", "temperature", 4.0)
        reading(i, f"PT-{run}-P{i + 1}", "power", "ON")
        staff.post("/api/restocks", json={"productId": low[i]["productId"], "quantity": 3,
                                          "supplierId": seed["supplierId"]})

    n = len(triggers)
    on_screen = [seen.get(i, math.inf) + screen_refresh for i in range(n)]
    sent_to_staff = [delivered.get(i, math.inf) for i in range(n)]
    print(f"Alerts screen refreshes every {screen_refresh:g} s (added to 'on screen').")
    for kind in KINDS:
        idx = [i for i in range(n) if triggers[i][0] == kind]
        d = ", ".join(f"{delivered.get(i, math.inf):.0f}" for i in idx)
        print(f"  {kind:12s} delivered after (s): {d}")
    for i in range(n):
        if i not in delivered:
            print(f"  alert {i + 1} ({triggers[i][0]}): never delivered, "
                  f"status {status.get(i, 'not raised')}")
    ok = summary("Delivered to staff", sent_to_staff, args.limit)
    ok &= summary("Visible on Alerts screen", on_screen, args.limit)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
