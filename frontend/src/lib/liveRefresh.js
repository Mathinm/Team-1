// NFR-1: a stock change (sale, restock, removal) must show on every screen within 5 seconds.
// Screens that show stock reload their data every LIVE_REFRESH_MS. A change made just after a
// reload shows at the next one, so it is visible after at most LIVE_REFRESH_MS plus the time
// of one request (about 10-50 ms, see docs/S2-10-nfr.md): under 3.1 s, well inside 5 s.
// backend/tests/test_nfr_timing.py reads this number, so changing it re-checks NFR-1.
import { useEffect, useRef } from "react";
import { asBackground } from "../api/background.js";

export const LIVE_REFRESH_MS = 3000;

// Call load() every `ms`, but:
//  - not while the browser tab is hidden (no point loading what nobody sees), and load at once
//    when the tab becomes visible again, so the screen is never shown stale;
//  - not while the previous load is still running, so a slow server never gets a pile-up.
// Returns a function that stops it. Plain JS (no React) so it can be unit-tested.
export function startLiveRefresh(load, { ms = LIVE_REFRESH_MS, doc = globalThis.document } = {}) {
  let running = false;
  const hidden = () => doc?.visibilityState === "hidden";
  const tick = () => {
    if (running || hidden()) return;
    running = true;
    Promise.resolve()
      .then(() => asBackground(load)) // an automatic reload, not a person: no idle-logout reset
      .catch(() => {}) // each screen shows its own errors; a failed refresh just tries again
      .finally(() => {
        running = false;
      });
  };
  const onVisibility = () => {
    if (!hidden()) tick();
  };
  const id = setInterval(tick, ms);
  doc?.addEventListener?.("visibilitychange", onVisibility);
  return () => {
    clearInterval(id);
    doc?.removeEventListener?.("visibilitychange", onVisibility);
  };
}

// React hook: keep re-running `load` while the screen is open. The screen still does its own
// first load; this only adds the refreshes. Always calls the newest `load`.
export function useLiveRefresh(load, ms = LIVE_REFRESH_MS) {
  const latest = useRef(load);
  useEffect(() => {
    latest.current = load;
  }, [load]);
  useEffect(() => startLiveRefresh(() => latest.current(), { ms }), [ms]);
}
