import { describe, expect, it } from "vitest";
import { normalizeAlert, normalizeUnit } from "./normalize.js";

describe("backend alerts and units in the screen shape (UI-4)", () => {
  it("maps backend alert types and uses the time the problem happened", () => {
    const a = normalizeAlert({
      alertId: 7, type: "DOOR_OPEN", severity: "warning", status: "active",
      triggeredAt: "2026-10-31T05:00:00+00:00", createdAt: "2026-10-31T05:00:03+00:00",
    });
    expect(a).toMatchObject({ alertId: 7, type: "door_open", createdAt: "2026-10-31T05:00:00+00:00" });
    expect(normalizeAlert({ type: "PRE_EXPIRY" }).type).toBe("expiry_soon");
    expect(normalizeAlert({ type: "EXPIRY" }).type).toBe("expired");
    expect(normalizeAlert({ type: "STOCK_REMOVAL" }).type).toBe("removal");
    expect(normalizeAlert({ type: "SOMETHING_NEW" }).type).toBe("something_new");
  });

  it("leaves demo-backend alerts unchanged", () => {
    const a = { alertId: 1, type: "low_stock", createdAt: "2026-10-20T10:00:00Z" };
    expect(normalizeAlert(a)).toEqual(a);
  });

  it("turns a backend unit into status, door and in-range flags", () => {
    const u = normalizeUnit({
      unitId: "Fridge-2", status: "FAILED", door: "OPEN", temperature: 9.5, tempMin: 0, tempMax: 8,
      lastReadingAt: "2026-10-31T05:00:00+00:00",
    });
    expect(u).toMatchObject({ name: "Fridge-2", status: "failed", doorOpen: true, currentTemp: 9.5, inRange: false });
    const ok = normalizeUnit({ unitId: "Fridge-1", status: "OK", door: "CLOSED", temperature: null, tempMin: 0, tempMax: 8 });
    expect(ok).toMatchObject({ status: "ok", doorOpen: false, currentTemp: null, inRange: null });
  });

  it("leaves demo-backend units unchanged", () => {
    const u = { unitId: "FR-1", name: "Freezer", currentTemp: -18, inRange: true, status: "ok" };
    expect(normalizeUnit(u)).toEqual(u);
  });
});
