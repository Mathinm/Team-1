"""TC-PERF-01 (NFR-1): stock changes appear on all screens within 5 s for 95% of updates.

What it does, like the test case (2 browsers on the stock screen, 100 sales from the simulator):
  - opens N "screens": each logs in as its own user and reloads GET /api/products every
    LIVE_REFRESH_MS (read from frontend/src/lib/liveRefresh.js), exactly like the web app;
  - sends 100 sales of LT-001 through the POS Device API, one every --gap seconds;
  - for every sale and every screen, measures the time from sending the sale until that
    screen first shows the new stock (or less).

    python perf/stock_latency.py --base http://localhost:3000 --seed perf/seed.json

Exit code 0 = PASS (>= 95% within 5 s on every screen), 1 = FAIL.
"""

import argparse
import math
import random
import sys
import threading
import time
import uuid

import httpx
from common import frontend_constant, load_seed, login, summary


class Screen(threading.Thread):
    """One browser tab on the Products/Stock screen."""

    def __init__(self, base: str, user: str, password: str, sku: str, every: float):
        super().__init__(daemon=True)
        self.client = httpx.Client(base_url=base, timeout=10)
        login(self.client, user, password)
        self.user, self.sku, self.every = user, sku, every
        self.seen: list[tuple[float, float]] = []  # (time the answer arrived, stock shown)
        self.errors = 0
        self.stop = threading.Event()

    def run(self) -> None:
        self.stop.wait(random.uniform(0, self.every))  # tabs were opened at different moments
        while not self.stop.is_set():
            try:
                r = self.client.get("/api/products")
                r.raise_for_status()
                stock = next(p["stock"] for p in r.json() if p["sku"] == self.sku)
                self.seen.append((time.monotonic(), stock))
            except Exception:
                self.errors += 1
            self.stop.wait(self.every)

    def first_seen(self, sent: float, stock: float) -> float:
        """Seconds from `sent` until this screen showed `stock` or lower (inf if never)."""
        for at, shown in self.seen:
            if at >= sent and shown <= stock + 1e-6:
                return at - sent
        return math.inf


def main() -> int:
    ap = argparse.ArgumentParser(description="TC-PERF-01: stock update visibility (NFR-1)")
    ap.add_argument("--base", default="http://localhost:8000", help="backend or web server URL")
    ap.add_argument("--seed", default="perf/seed.json")
    ap.add_argument("--count", type=int, default=100, help="number of sales (test case: 100)")
    ap.add_argument("--gap", type=float, default=1.0, help="seconds between sales")
    ap.add_argument("--screens", type=int, default=2, help="screens watching (test case: 2)")
    ap.add_argument("--sku", default="LT-001")
    ap.add_argument("--limit", type=float, default=5.0, help="NFR-1 target in seconds")
    args = ap.parse_args()

    seed = load_seed(args.seed)
    every = frontend_constant("lib/liveRefresh.js", "LIVE_REFRESH_MS", 3000) / 1000
    pos = httpx.Client(base_url=args.base, timeout=10, headers={"X-Device-Key": seed["posKey"]})
    screens = [
        Screen(args.base, u["userId"], seed["password"], args.sku, every)
        for u in seed["users"][: args.screens]
    ]
    print(f"{len(screens)} screens reloading every {every:g} s; {args.count} sales of "
          f"{args.sku}, one every {args.gap:g} s (about {args.count * args.gap:.0f} s)...")
    for s in screens:
        s.start()
    time.sleep(every + 0.5)

    sales: list[tuple[float, float]] = []  # (time sent, stock after the sale)
    failed = 0
    for _ in range(args.count):
        sent = time.monotonic()
        r = pos.post("/api/device/sales",
                     json={"eventId": f"perf-{uuid.uuid4()}", "sku": args.sku, "quantity": 0.5})
        if r.status_code == 201:
            sales.append((sent, r.json()["remainingStock"]))
        else:
            failed += 1
            print(f"  sale failed: {r.status_code} {r.text[:120]}")
        time.sleep(max(0.0, args.gap - (time.monotonic() - sent)))

    time.sleep(every + 2)  # give the screens time to show the last sale
    for s in screens:
        s.stop.set()

    ok = failed == 0
    print(f"Sales sent: {len(sales)} ok, {failed} failed")
    for i, s in enumerate(screens, 1):
        latencies = [s.first_seen(sent, stock) for sent, stock in sales]
        ok &= summary(f"Screen {i} ({s.user})", latencies, args.limit, extra_limits=(3.0,))
        if s.errors:
            print(f"  screen {i}: {s.errors} failed reloads")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
