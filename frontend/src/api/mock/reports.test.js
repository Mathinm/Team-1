import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";
import { REPORT_TYPES } from "../../config/reports.js";
import { reportToCsv } from "../../lib/reportExport.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, token) => mockRequest(method, path, undefined, token, NOW);
let manager;
let staff;

beforeEach(async () => {
  resetMockDb(NOW);
  manager = (await mockRequest("POST", "/auth/login", { userId: "manager1", password: "manager123" }, null, NOW)).body.token;
  staff = (await mockRequest("POST", "/auth/login", { userId: "staff1", password: "staff123" }, null, NOW)).body.token;
});

describe("reports (FR-18, TC-REP-01)", () => {
  it("returns every report type with columns for a 30-day range", async () => {
    for (const { type } of REPORT_TYPES) {
      const res = await call("GET", `/reports/${type}?from=2026-09-21&to=2026-10-20`, manager);
      expect(res.status, type).toBe(200);
      expect(res.body.columns.length, type).toBeGreaterThan(0);
      expect(res.body.rows.length, type).toBeGreaterThan(0);
    }
  });

  it("calculates waste % and money lost", async () => {
    const res = await call("GET", "/reports/wastage?from=2026-10-14&to=2026-10-20", manager);
    const tomato = res.body.rows.find((r) => r.product === "Tomato");
    // 3 kg damaged (2 days ago) + 2.5 kg expired (6 days ago), cost Rs 20/kg
    expect(tomato.wasted).toBe(5.5);
    expect(tomato.moneyLost).toBe(110);
    expect(tomato.wastePct).toBeGreaterThan(0);
  });

  it("returns no rows for a range with no data", async () => {
    const res = await call("GET", "/reports/removals?from=2025-01-01&to=2025-01-31", manager);
    expect(res.status).toBe(200);
    expect(res.body.rows).toEqual([]);
  });

  it("rejects a reversed date range (400)", async () => {
    const res = await call("GET", "/reports/wastage?from=2026-10-20&to=2026-10-01", manager);
    expect(res.status).toBe(400);
  });

  it("is Manager/Admin only (403 for Inventory Staff)", async () => {
    const res = await call("GET", "/reports/wastage?from=2026-10-14&to=2026-10-20", staff);
    expect(res.status).toBe(403);
  });

  it("exports CSV with a header row and one line per row", async () => {
    const res = await call("GET", "/reports/sellers?from=2026-10-14&to=2026-10-20", manager);
    const lines = reportToCsv(res.body).trim().split("\n");
    expect(lines[0]).toBe("Rank,Product,Quantity sold,Unit,Revenue (Rs),");
    expect(lines).toHaveLength(res.body.rows.length + 1);
  });
});

describe("dashboard", () => {
  it("summarises low stock, expiring batches and active alerts", async () => {
    const res = await call("GET", "/dashboard", staff);
    expect(res.status).toBe(200);
    expect(res.body.lowStock.map((p) => p.name)).toEqual(expect.arrayContaining(["Bread Loaf", "Spinach"]));
    expect(res.body.expiringSoon[0].daysToExpiry).toBe(-1); // expired milk first
    expect(res.body.activeAlerts.count).toBe(6);
  });
});
