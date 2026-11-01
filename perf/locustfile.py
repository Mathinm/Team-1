"""TC-PERF-03 (NFR-3): 50 concurrent users, 5,000 batches and 100 sensors, response targets met.

Needs the test data from `python -m app.load_seed --yes` (5,000 batches, 100 sensors, 50 users).
Simulated load:
  - 25 Inventory Staff: their screens reload products every few seconds, open the FEFO batch
    list, alerts and fridges, and sometimes record a restock;
  - 25 Cashiers: reload products and record sales;
  - 1 "sensor fleet": the 100 sensors, each sending a temperature or door reading every
    PMS_SENSOR_EVERY seconds (default 30), so about 3 readings a second in total.
LT-001 is left alone, so perf/stock_latency.py can measure NFR-1 during the load.

Pass/fail (checked when the test ends; exit code 1 = FAIL):
  - no failed requests ("No errors", TC-PERF-03);
  - 95% of requests answered within 2,000 ms. Why 2 s: a screen reloads every 3 s
    (LIVE_REFRESH_MS), so a stock change is visible within 3 s + one request; with requests
    under 2 s that stays within NFR-1's 5 s.

    locust -f perf/locustfile.py --host http://localhost:3000 --headless -u 51 -r 10 -t 15m
(-u 51 = 50 people + the sensor fleet.) Without --headless, open http://localhost:8089.
"""

import itertools
import os
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from locust import HttpUser, between, constant_pacing, events, task

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_seed  # noqa: E402

SEED = load_seed(os.environ.get("PMS_SEED", "perf/seed.json"))
P95_LIMIT_MS = float(os.environ.get("PMS_P95_LIMIT_MS", "2000"))
SENSOR_EVERY = float(os.environ.get("PMS_SENSOR_EVERY", "30"))
SKUS = [s for s in SEED["loadSkus"] if s != "LT-001"]  # LT-001 is for stock_latency.py
_accounts = {
    role: itertools.cycle([u["userId"] for u in SEED["users"] if u["role"] == role])
    for role in ("Inventory Staff", "Cashier")
}
_sensors = itertools.cycle(SEED["sensors"])
_product_ids: list[int] = []  # filled at the first login, from GET /api/products


class StoreUser(HttpUser):
    abstract = True
    role = ""
    wait_time = between(1, 3)  # a person reading the screen, plus the 3 s screen refresh

    def on_start(self) -> None:
        r = self.client.post("/api/auth/login", name="/api/auth/login",
                             json={"userId": next(_accounts[self.role]),
                                   "password": SEED["password"]})
        r.raise_for_status()
        self.client.headers["Authorization"] = f"Bearer {r.json()['token']}"
        if not _product_ids:
            products = self.client.get("/api/products").json()
            _product_ids.extend(p["productId"] for p in products if p["sku"] in SKUS)

    @task(6)
    def products_screen(self) -> None:
        self.client.get("/api/products")


class InventoryStaff(StoreUser):
    role = "Inventory Staff"

    @task(3)
    def fefo_list(self) -> None:
        self.client.get(f"/api/batches/fefo?productId={random.choice(_product_ids)}",
                        name="/api/batches/fefo?productId=[id]")

    @task(2)
    def alerts_screen(self) -> None:
        self.client.get("/api/alerts?status=open")

    @task(2)
    def fridges_screen(self) -> None:
        self.client.get("/api/refrigeration/units")

    @task(1)
    def restock(self) -> None:
        self.client.post("/api/restocks", json={"productId": random.choice(_product_ids),
                                                "quantity": 5, "supplierId": SEED["supplierId"]})


class Cashier(StoreUser):
    role = "Cashier"

    @task(3)
    def sale(self) -> None:
        self.client.post("/api/sales", json={"sku": random.choice(SKUS), "quantity": 0.5})


class SensorFleet(HttpUser):
    """All 100 sensors together: one reading every SENSOR_EVERY / 100 seconds."""

    fixed_count = 1
    wait_time = constant_pacing(SENSOR_EVERY / max(1, len(SEED["sensors"])))

    @task
    def reading(self) -> None:
        sensor = next(_sensors)
        door = random.random() < 0.1
        self.client.post(
            "/api/device/readings", name="/api/device/readings",
            headers={"X-Device-Key": sensor["key"]},
            json={"eventId": f"load-{uuid.uuid4()}", "unitId": sensor["unitId"],
                  "type": "door" if door else "temperature",
                  "value": "CLOSED" if door else round(random.uniform(2.5, 6.5), 1),
                  "recordedAt": datetime.now(timezone.utc).isoformat()},
        )


@events.quitting.add_listener
def check_targets(environment, **_kwargs) -> None:
    """Turn the run into PASS/FAIL (exit code) against the TC-PERF-03 targets."""
    total = environment.stats.total
    p95 = total.get_response_time_percentile(0.95) or 0
    print(f"\nTC-PERF-03: {total.num_requests} requests, {total.num_failures} failed, "
          f"median {total.median_response_time:.0f} ms, 95th {p95:.0f} ms "
          f"(limit {P95_LIMIT_MS:.0f} ms), {total.total_rps:.1f} requests/s")
    problems = []
    if total.num_requests == 0:
        problems.append("no requests were made")
    if total.num_failures:
        problems.append(f"{total.num_failures} failed requests")
    if p95 > P95_LIMIT_MS:
        problems.append(f"95th percentile {p95:.0f} ms is over {P95_LIMIT_MS:.0f} ms")
    for name, entry in environment.stats.entries.items():
        entry_p95 = entry.get_response_time_percentile(0.95) or 0
        if entry_p95 > P95_LIMIT_MS:
            problems.append(f"{name[1]} {name[0]}: 95th percentile {entry_p95:.0f} ms")
    print("RESULT:", "FAIL - " + "; ".join(problems) if problems else "PASS")
    environment.process_exit_code = 1 if problems else 0
