import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LIVE_REFRESH_MS, startLiveRefresh } from "./liveRefresh.js";

// A stand-in for the browser's `document`: lets the test hide/show the tab.
function fakeDoc() {
  const listeners = new Set();
  return {
    visibilityState: "visible",
    addEventListener: (_type, fn) => listeners.add(fn),
    removeEventListener: (_type, fn) => listeners.delete(fn),
    set(state) {
      this.visibilityState = state;
      listeners.forEach((fn) => fn());
    },
    listeners,
  };
}

const flush = () => vi.advanceTimersByTimeAsync(0); // let finished promises run

describe("live refresh (NFR-1)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("keeps the 5 s promise: refresh interval plus a slow 2 s request is within 5 s", () => {
    expect(LIVE_REFRESH_MS + 2000).toBeLessThanOrEqual(5000);
  });

  it("reloads every interval", async () => {
    const load = vi.fn().mockResolvedValue();
    const stop = startLiveRefresh(load, { ms: 3000, doc: fakeDoc() });
    await vi.advanceTimersByTimeAsync(2999);
    expect(load).toHaveBeenCalledTimes(0); // the screen did its own first load already
    await vi.advanceTimersByTimeAsync(1);
    expect(load).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(6000);
    expect(load).toHaveBeenCalledTimes(3);
    stop();
  });

  it("stops when the screen closes", async () => {
    const load = vi.fn().mockResolvedValue();
    const doc = fakeDoc();
    const stop = startLiveRefresh(load, { ms: 3000, doc });
    stop();
    await vi.advanceTimersByTimeAsync(10000);
    expect(load).not.toHaveBeenCalled();
    expect(doc.listeners.size).toBe(0);
  });

  it("pauses while the tab is hidden and reloads at once when it is shown", async () => {
    const load = vi.fn().mockResolvedValue();
    const doc = fakeDoc();
    const stop = startLiveRefresh(load, { ms: 3000, doc });
    doc.set("hidden");
    await vi.advanceTimersByTimeAsync(9000);
    expect(load).not.toHaveBeenCalled();
    doc.set("visible");
    await flush();
    expect(load).toHaveBeenCalledTimes(1);
    stop();
  });

  it("never starts a second load while one is still running", async () => {
    let finish;
    const load = vi.fn(() => new Promise((resolve) => (finish = resolve)));
    const stop = startLiveRefresh(load, { ms: 1000, doc: fakeDoc() });
    await vi.advanceTimersByTimeAsync(5000); // a very slow server
    expect(load).toHaveBeenCalledTimes(1);
    finish();
    await flush();
    await vi.advanceTimersByTimeAsync(1000);
    expect(load).toHaveBeenCalledTimes(2);
    stop();
  });

  it("keeps going after a failed load", async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue();
    const stop = startLiveRefresh(load, { ms: 1000, doc: fakeDoc() });
    await vi.advanceTimersByTimeAsync(3000);
    expect(load).toHaveBeenCalledTimes(3);
    stop();
  });

  it("works where there is no document (tests, server)", async () => {
    const load = vi.fn().mockResolvedValue();
    const stop = startLiveRefresh(load, { ms: 1000, doc: undefined });
    await vi.advanceTimersByTimeAsync(1000);
    expect(load).toHaveBeenCalledTimes(1);
    stop();
  });
});
