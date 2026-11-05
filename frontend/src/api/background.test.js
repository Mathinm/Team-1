import { afterEach, describe, expect, it, vi } from "vitest";
import { asBackground, isBackground } from "./background.js";
import { request } from "./client.js";
import { startLiveRefresh } from "../lib/liveRefresh.js";

// S3-4: automatic refreshes are marked so the backend does not count them as activity.
function stubFetch() {
  const calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url, init) => {
    calls.push({ url, headers: init.headers });
    return new Response("[]", { status: 200, headers: { "content-type": "application/json" } });
  }));
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("background refresh flag (S3-4)", () => {
  it("is only on while the wrapped function starts", () => {
    expect(isBackground()).toBe(false);
    let inside;
    asBackground(() => {
      inside = isBackground();
    });
    expect(inside).toBe(true);
    expect(isBackground()).toBe(false);
  });

  it("is reset even if the function throws", () => {
    expect(() => asBackground(() => { throw new Error("x"); })).toThrow("x");
    expect(isBackground()).toBe(false);
  });

  it("marks requests started in the background, not a person's requests", async () => {
    const calls = stubFetch();
    await request("GET", "/products");
    await asBackground(() => request("GET", "/products"));
    expect(calls[0].headers["X-Background-Refresh"]).toBeUndefined();
    expect(calls[1].headers["X-Background-Refresh"]).toBe("1");
  });

  it("live refresh sends its reloads as background requests", async () => {
    vi.useFakeTimers();
    const calls = stubFetch();
    const stop = startLiveRefresh(() => request("GET", "/products"), { ms: 1000, doc: null });
    await vi.advanceTimersByTimeAsync(1000);
    stop();
    expect(calls).toHaveLength(1);
    expect(calls[0].headers["X-Background-Refresh"]).toBe("1");
  });
});
