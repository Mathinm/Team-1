"""Shared client for the POS and sensor simulators (stdlib only).

Sends events to the Device API with the X-Device-Key header. If the backend cannot be
reached (or answers 5xx) the event is kept in a local file and resent, oldest first, on the
next attempt (FR-19, NFR-5). Every event has an eventId, so a resend that already arrived is
answered 409 and simply dropped from the buffer: no duplicates.

The buffer is a plain text file with one JSON event per line:
  * a new event is only ever APPENDED (and forced to disk), so a crash or power cut cannot
    damage the events already waiting;
  * a half-written last line (power cut mid-write) is set aside in <buffer>.corrupt.jsonl
    instead of stopping the simulator;
  * after a successful delivery the buffer is rewritten every SAVE_EVERY events and when the
    resend stops. If the program dies in between, the events delivered since the last rewrite
    are sent again and answered 409, which is harmless.
Order is kept: events are always delivered oldest first, and a new event never overtakes
the ones waiting, so the backend sees them in the order they happened.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://localhost:8000"
SAVE_EVERY = 50  # rewrite the buffer after this many delivered events during a resend


class DeviceClient:
    def __init__(self, base_url: str, key: str, buffer_file: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.buffer = Path(buffer_file)
        self.rejected = self.buffer.with_suffix(".rejected.jsonl")
        self.corrupt = self.buffer.with_suffix(".corrupt.jsonl")
        self.timeout = timeout

    # ---- buffer -------------------------------------------------------------------
    def _load(self) -> tuple[list[dict], list[str]]:
        """(valid events, unreadable lines)."""
        if not self.buffer.exists():
            return [], []
        items: list[dict] = []
        bad: list[str] = []
        for line in self.buffer.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if not isinstance(item, dict) or "path" not in item or "event" not in item:
                    raise ValueError("not an event")
                items.append(item)
            except ValueError:
                bad.append(line)
        return items, bad

    def pending(self) -> list[dict]:
        return self._load()[0]

    def pending_count(self) -> int:
        """How many events are waiting to be synchronised (the offline-sync queue size)."""
        return len(self.pending())

    def _append(self, item: dict) -> None:
        with self.buffer.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _save(self, items: list[dict]) -> None:
        tmp = self.buffer.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write("".join(json.dumps(i) + "\n" for i in items))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.buffer)  # atomic: a crash never leaves a half-written buffer

    def _quarantine(self, bad: list[str]) -> None:
        with self.corrupt.open("a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in bad))
        print(f"  {len(bad)} unreadable line(s) moved to {self.corrupt}")

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
        if self.pending_count():  # the backend is still unreachable: join the queue, in order
            self._append({"path": path, "event": event})
            return "buffered"
        return self._deliver(path, event, queue_on_failure=True)

    def flush(self) -> int:
        """Resend buffered events in order; stops at the first one the backend can't take yet.

        Returns how many events were taken off the buffer (delivered, duplicate or rejected).
        """
        items, bad = self._load()
        if bad:
            self._quarantine(bad)
            self._save(items)
        done = saved_at = 0
        try:
            while done < len(items):
                item = items[done]
                if self._deliver(item["path"], item["event"], queue_on_failure=False) == "buffered":
                    break
                done += 1
                if done - saved_at >= SAVE_EVERY:
                    self._save(items[done:])
                    saved_at = done
        finally:  # also when a 401 stops the program: what is left stays on disk
            if done > saved_at:
                self._save(items[done:])
        return done

    def _deliver(self, path: str, event: dict, queue_on_failure: bool) -> str:
        status, body = self._post(path, event)
        if status in (200, 201):
            return "delivered"
        if status == 409:
            return "duplicate"  # already stored by an earlier attempt
        if status == 0 or status >= 500:
            if queue_on_failure:
                self._append({"path": path, "event": event})
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
