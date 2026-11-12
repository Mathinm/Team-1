import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);
const tokenFor = async (userId, password) => (await call("POST", "/auth/login", { userId, password })).body.token;

beforeEach(() => resetMockDb(NOW));

describe("refrigeration safety limits (FR-15 mock API)", () => {
  it("allows a Manager to save limits and raises an alert if the latest reading is outside", async () => {
    const manager = await tokenFor("manager1", "manager123");
    const before = await call("GET", "/refrigeration/units", undefined, manager);
    const unit = before.body.find((u) => u.unitId === "FR-1");
    expect(unit.currentTemp).not.toBeNull();

    const updated = await call("PUT", "/refrigeration/units/FR-1", {
      tempMin: unit.currentTemp - 1,
      tempMax: unit.currentTemp - 0.1,
      doorOpenLimitMinutes: 4,
    }, manager);
    expect(updated.status).toBe(200);
    expect(updated.body).toMatchObject({ tempMax: unit.currentTemp - 0.1, doorOpenLimitMinutes: 4, inRange: false });

    const active = await call("GET", "/alerts?status=active", undefined, manager);
    expect(active.body.some((a) => a.type === "temperature" && a.unitId === "FR-1")).toBe(true);
  });

  it("rejects settings changes by Inventory Staff", async () => {
    const staff = await tokenFor("staff1", "staff123");
    const response = await call("PUT", "/refrigeration/units/FR-1", {
      tempMin: 1, tempMax: 5, doorOpenLimitMinutes: 5,
    }, staff);
    expect(response.status).toBe(403);
  });

  it("rejects an invalid temperature range and an invalid door limit", async () => {
    const manager = await tokenFor("manager1", "manager123");
    const invalidRange = await call("PUT", "/refrigeration/units/FR-1", { tempMin: 8, tempMax: 2 }, manager);
    expect(invalidRange.status).toBe(400);
    const invalidDoorLimit = await call("PUT", "/refrigeration/units/FR-1", {
      tempMin: 1, tempMax: 5, doorOpenLimitMinutes: 0,
    }, manager);
    expect(invalidDoorLimit.status).toBe(400);
  });

  it("edits limits with case-insensitive unit id (N12)", async () => {
    const manager = await tokenFor("manager1", "manager123");
    const updated = await call("PUT", "/refrigeration/units/fr-1", {
      tempMin: 2, tempMax: 6,
    }, manager);
    expect(updated.status).toBe(200);
    expect(updated.body.tempMin).toBe(2);
  });

  it("rejects future sensor readings (N2)", async () => {
    const future = new Date(NOW.getTime() + 10 * 60 * 1000).toISOString();
    const res = await call("POST", "/device/readings", {
      unitId: "FR-1", type: "temperature", value: 4, recordedAt: future,
    });
    expect(res.status).toBe(400);
    expect(res.body.error.message).toMatch(/future/);
  });
});
