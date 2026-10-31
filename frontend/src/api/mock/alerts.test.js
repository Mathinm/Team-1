import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);
const login = async (userId, password) => (await call("POST", "/auth/login", { userId, password })).body.token;

let manager;
let staff;
beforeEach(async () => {
  resetMockDb(NOW);
  manager = await login("manager1", "manager123");
  staff = await login("staff1", "staff123");
});

describe("alerts and acknowledgement (UI-4, TC-SEN-01)", () => {
  it("lists only active alerts, newest first", async () => {
    const res = await call("GET", "/alerts?status=active", undefined, staff);
    expect(res.status).toBe(200);
    expect(res.body.every((a) => a.status === "active")).toBe(true);
    const times = res.body.map((a) => a.createdAt);
    expect([...times].sort().reverse()).toEqual(times);
  });

  it("lets a Manager acknowledge and records who and when", async () => {
    const res = await call("POST", "/alerts/1/acknowledge", undefined, manager);
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ status: "acknowledged", acknowledgedBy: "manager1", acknowledgedAt: NOW.toISOString() });
    const again = await call("POST", "/alerts/1/acknowledge", undefined, manager);
    expect(again.status).toBe(200); // repeating is harmless, like the backend
    expect(again.body.acknowledgedAt).toBe(NOW.toISOString());
  });

  it("does not let Inventory Staff acknowledge (403)", async () => {
    const res = await call("POST", "/alerts/1/acknowledge", undefined, staff);
    expect(res.status).toBe(403);
  });
});

describe("refrigeration units (FR-15, FR-16)", () => {
  it("shows unit status, current temperature and range", async () => {
    const res = await call("GET", "/refrigeration/units", undefined, staff);
    const fr2 = res.body.find((u) => u.unitId === "FR-2");
    expect(fr2).toMatchObject({ status: "failed", tempMin: 2, tempMax: 6, inRange: false });
    expect(typeof fr2.currentTemp).toBe("number");
  });

  it("returns readings for the requested window only", async () => {
    const day = await call("GET", "/refrigeration/units/FR-1/readings?hours=24", undefined, staff);
    const week = await call("GET", "/refrigeration/units/FR-1/readings?hours=168", undefined, staff);
    expect(day.body.length).toBeGreaterThan(40);
    expect(week.body.length).toBeGreaterThan(day.body.length * 6);
  });

  it("raises a fridge-failure alert when a unit reports failed", async () => {
    const res = await call("POST", "/device/readings", { unitId: "FR-1", type: "status", value: "failed" });
    expect(res.body.alertRaised).toBe(true);
    const alerts = await call("GET", "/alerts?status=active", undefined, manager);
    expect(alerts.body[0]).toMatchObject({ type: "unit_failure", severity: "critical", unitId: "FR-1" });
  });

  it("raises a door-open alarm and a temperature alert", async () => {
    const door = await call("POST", "/device/readings", { unitId: "CH-1", type: "door", value: "open" });
    const temp = await call("POST", "/device/readings", { unitId: "CH-1", type: "temperature", value: 14 });
    expect(door.body.alertRaised).toBe(true);
    expect(temp.body.alertRaised).toBe(true);
  });

  it("rejects a malformed temperature (400)", async () => {
    const res = await call("POST", "/device/readings", { unitId: "FR-1", type: "temperature", value: "abc" });
    expect(res.status).toBe(400);
  });
});
