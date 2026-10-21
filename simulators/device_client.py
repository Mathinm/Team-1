"""Shared client for the POS and sensor simulators (stdlib only).

Sends events to the Device API with the X-Device-Key header. If the backend cannot be
reached (or answers 5xx) the event is kept in a local file and resent, oldest first, on the
next attempt (FR-19). Every event has an eventId, so a resend that already arrived is
answered 409 and simply dropped from the buffer: no duplicates.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://localhost:8000"


class DeviceClient:
    def __init__(self, base_url: str, key: str, buffer_file: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.buffer = Path(buffer_file)
        self.rejected = self.buffer.with_suffix(".rejected.jsonl")
        self.timeout = timeout

    # ---- buffer -------------------------------------------------------------------
    def pending(self) -> list[dict]:
        if not self.buffer.exists():
            return []
        return [json.loads(x) for x in self.buffer.read_text().splitlines() if x.strip()]

    def _save(self, items: list[dict]) -> None:
        tmp = self.buffer.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(i) + "\n" for i in items))
        os.replace(tmp, self.buffer)  # atomic: a crash never leaves a half-written buffer

    # ---- transport ----------------------------------------------------------------
    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        """Returns (status, body); status 0 = backend unreachable."""
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Device-Key": self.key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            return 0, {}

    # ---- public -------------------------------------------------------------------
    def send(self, path: str, event: dict) -> str:
        """Send one event after any buffered ones. Returns delivered|duplicate|buffered|rejected."""
        self.flush()
        return self._deliver(path, event, queue_on_failure=True)

    def flush(self) -> int:
        """Resend buffered events in order; stops at the first one the backend can't take yet."""
        items = self.pending()
        done = 0
        while items:
            item = items[0]
            outcome = self._deliver(item["path"], item["event"], queue_on_failure=False)
            if outcome == "buffered":
                break
            items.pop(0)
            done += 1
            self._save(items)
        return done

    def _deliver(self, path: str, event: dict, queue_on_failure: bool) -> str:
        status, body = self._post(path, event)
        if status in (200, 201):
            return "delivered"
        if status == 409:
            return "duplicate"  # already stored by an earlier attempt
        if status == 0 or status >= 500:
            if queue_on_failure:
                self._save(self.pending() + [{"path": path, "event": event}])
            return "buffered"
        if status == 401:
            raise SystemExit("The backend rejected the device key (401). Check PMS_DEVICE_KEY.")
        # 400 / 403 / 404 / 422: retrying cannot help. Keep a record and move on.
        message = body.get("error", {}).get("message", f"HTTP {status}")
        with self.rejected.open("a") as f:
            f.write(json.dumps({"path": path, "event": event, "status": status,
                                "message": message}) + "\n")
        print(f"  rejected ({status}): {message}")
        return "rejected"
