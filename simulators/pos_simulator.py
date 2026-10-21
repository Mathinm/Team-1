#!/usr/bin/env python3
"""POS simulator: sends sales to POST /api/device/sales.

    export PMS_DEVICE_KEY=<key from: python -m app.device.provision pos-sim pos>
    python pos_simulator.py                       # random sales every 2 s until Ctrl+C
    python pos_simulator.py --count 20 --interval 0.5 --skus TOM-01,BAN-01
    python pos_simulator.py --once --sku TOM-01 --quantity 2     # one specific sale

Stop the backend while it runs: sales pile up in pos-buffer.jsonl and are sent, once each,
when the backend is back.
"""

import argparse
import os
import random
import time
import uuid
from datetime import datetime, timezone

from device_client import DEFAULT_URL, DeviceClient

# sku -> (unit, smallest, largest quantity of one sale)
DEFAULT_CATALOG = {
    "TOM-01": ("kg", 0.5, 3.0),
    "BAN-01": ("piece", 1, 12),
    "MLK-01": ("l", 1, 4),
    "PAN-01": ("kg", 0.25, 1.0),
    "BRD-01": ("piece", 1, 3),
    "SPN-01": ("kg", 0.25, 1.5),
}


def make_event(sku: str, quantity: float, unit: str | None) -> dict:
    event = {
        "eventId": str(uuid.uuid4()),
        "sku": sku,
        "quantity": quantity,
        "soldAt": datetime.now(timezone.utc).isoformat(),
    }
    if unit:
        event["unit"] = unit
    return event


def random_sale(skus: list[str]) -> dict:
    sku = random.choice(skus)
    unit, lo, hi = DEFAULT_CATALOG.get(sku, ("kg", 0.5, 3.0))
    qty = random.randint(int(lo), int(hi)) if unit == "piece" else round(random.uniform(lo, hi), 2)
    return make_event(sku, qty, unit)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--url", default=os.getenv("PMS_URL", DEFAULT_URL))
    p.add_argument("--key", default=os.getenv("PMS_DEVICE_KEY"))
    p.add_argument("--interval", type=float, default=2.0, help="seconds between sales")
    p.add_argument("--count", type=int, default=0, help="stop after N sales (0 = run forever)")
    p.add_argument("--skus", default=",".join(DEFAULT_CATALOG))
    p.add_argument("--once", action="store_true", help="send one sale (needs --sku, --quantity)")
    p.add_argument("--sku")
    p.add_argument("--quantity", type=float)
    p.add_argument("--unit")
    p.add_argument("--buffer", default="pos-buffer.jsonl")
    a = p.parse_args()
    if not a.key:
        p.error("set PMS_DEVICE_KEY or pass --key")

    client = DeviceClient(a.url, a.key, a.buffer)
    if a.once:
        if not a.sku or a.quantity is None:
            p.error("--once needs --sku and --quantity")
        event = make_event(a.sku, a.quantity, a.unit)
        print(f"{event['sku']} x {event['quantity']}: {client.send('/api/device/sales', event)}")
        return

    skus = [s.strip() for s in a.skus.split(",") if s.strip()]
    sent = 0
    try:
        while not a.count or sent < a.count:
            event = random_sale(skus)
            outcome = client.send("/api/device/sales", event)
            sent += 1
            print(f"[{sent}] {event['sku']} x {event['quantity']}: {outcome}"
                  f" (buffered: {len(client.pending())})")
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    print(f"Stopped. {len(client.pending())} event(s) still waiting in {a.buffer}.")


if __name__ == "__main__":
    main()
