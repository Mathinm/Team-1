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
    // 3 kg damaged (2 days ago) + 2.5 kg expired (6 days ago), cost ₹20/kg
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
    expect(lines[0]).toBe("Rank,Product,Quantity sold,Unit,Revenue (₹),");
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

// Issue #72 (S3-9): rupees (N20), stock report "as of now" (N15), sales history (T7),
// fridge health on the dashboard (N19). Mirrors backend/tests/test_s3_9_fixes.py.
import { inr } from "./reports.js";
import { formatCell, reportPeriod } from "../../lib/reportExport.js";

describe("S3-9 report fixes", () => {
  it("formats rupees with Indian grouping and two decimals (N20)", () => {
    expect(inr(0)).toBe("₹0.00");
    expect(inr(177)).toBe("₹177.00");
    expect(inr(123456.5)).toBe("₹1,23,456.50");
    expect(formatCell(4.5, { money: true })).toBe("₹4.50");
    expect(formatCell(4.5, { numeric: true })).toBe("4.5");
  });

  it("shows money columns and summaries in ₹, never Rs", async () => {
    for (const { type } of REPORT_TYPES) {
      const res = await call("GET", `/reports/${type}?from=2026-09-21&to=2026-10-20`, manager);
      expect(JSON.stringify(res.body.columns) + JSON.stringify(res.body.summary), type).not.toMatch(/Rs/);
    }
    const stock = await call("GET", "/reports/stock?from=2026-10-14&to=2026-10-20", manager);
    expect(stock.body.summary[0].value).toMatch(/^₹[\d,]+\.\d\d$/);
  });

  it("labels the stock report as a snapshot, not the chosen range (N15)", async () => {
    const stock = await call("GET", "/reports/stock?from=2026-10-01&to=2026-10-07", manager);
    expect(stock.body.asOf).toBe(NOW.toISOString());
    expect(reportPeriod(stock.body)).toMatch(/^As of /);
    const waste = await call("GET", "/reports/wastage?from=2026-10-01&to=2026-10-07", manager);
    expect(waste.body.asOf).toBeNull();
    expect(reportPeriod(waste.body)).toBe("2026-10-01 to 2026-10-07");
  });

  it("lists every sale in the range, newest first (T7)", async () => {
    const res = await call("GET", "/reports/sales?from=2026-10-19&to=2026-10-19", manager);
    expect(res.status).toBe(200);
    expect(res.body.title).toBe("Sales history");
    expect(res.body.rows.length).toBeGreaterThan(0);
    const times = res.body.rows.map((r) => r.date);
    expect([...times].sort().reverse()).toEqual(times);
    expect(times.every((t) => t.startsWith("2026-10-19"))).toBe(true);
    const total = res.body.rows.reduce((a, r) => a + r.amount, 0);
    expect(res.body.summary[0]).toEqual({ label: "Sales", value: String(res.body.rows.length) });
    expect(res.body.summary[1].value).toBe(inr(total));
  });
});

describe("dashboard fridge health (N19)", () => {
  const sensor = (body) => mockRequest("POST", "/device/readings", body, null, NOW);
  const units = async () => Object.fromEntries((await call("GET", "/dashboard", staff)).body.units.map((u) => [u.unitId, u]));

  it("counts a too-warm fridge as not working", async () => {
    await sensor({ unitId: "FR-1", type: "temperature", value: 25 });
    const u = (await units())["FR-1"];
    expect(u.status).toBe("alert");
    expect(u.problem).toMatch(/^25 °C, too warm/);
  });

  it("counts an open door as not working", async () => {
    await sensor({ unitId: "CH-1", type: "temperature", value: 6 });
    await sensor({ unitId: "CH-1", type: "door", value: "open" });
    expect((await units())["CH-1"]).toMatchObject({ status: "alert", problem: "Door open" });
  });

  it("keeps failed units failed and healthy ones ok", async () => {
    await sensor({ unitId: "FR-1", type: "temperature", value: 4 });
    const all = await units();
    expect(all["FR-2"].status).toBe("failed");
    expect(all["FR-1"]).toMatchObject({ status: "ok", problem: null });
  });
});
