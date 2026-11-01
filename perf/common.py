"""Shared helpers for the S2-10 performance scripts (NFR-1, NFR-2, NFR-3)."""

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the project folder


def load_seed(path: str) -> dict:
    """Read the JSON printed by `python -m app.load_seed --yes`.

    Windows PowerShell 5 saves `> file` as UTF-16, so accept that as well as UTF-8.
    """
    raw = Path(path).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    return json.loads(text[text.index("{"):])  # skip anything printed before the JSON


def frontend_constant(file: str, name: str, default: int) -> int:
    """Read a number like `const REFRESH_MS = 10000;` from a frontend file, so the scripts
    always use the refresh rates the screens really use."""
    try:
        text = (ROOT / "frontend" / "src" / file).read_text(encoding="utf-8")
    except OSError:
        return default
    m = re.search(rf"{name}\s*=\s*(\d+)", text)
    return int(m.group(1)) if m else default


def login(client, user_id: str, password: str) -> None:
    r = client.post("/api/auth/login", json={"userId": user_id, "password": password})
    r.raise_for_status()
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile: the value below which p% of the values fall."""
    if not values:
        return math.inf
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def summary(name: str, latencies: list[float], limit: float, need: float = 0.95,
            extra_limits: tuple[float, ...] = ()) -> bool:
    """Print one result line and return True when at least `need` of them are within `limit`.
    A missing measurement is math.inf, so it counts as a failure."""
    n = len(latencies)
    ok = sum(v <= limit for v in latencies)
    finite = [v for v in latencies if math.isfinite(v)]
    passed = n > 0 and ok / n >= need
    extras = "".join(
        f", within {e:g} s: {sum(v <= e for v in latencies)}/{n}" for e in extra_limits
    )
    print(
        f"{name}: {n} measured, within {limit:g} s: {ok}/{n} ({100 * ok / max(n, 1):.0f}%)"
        f"{extras}, median {percentile(finite, 50):.2f} s, 95th {percentile(latencies, 95):.2f} s,"
        f" max {max(latencies, default=math.inf):.2f} s -> {'PASS' if passed else 'FAIL'}"
    )
    return passed
