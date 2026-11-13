// Issue #69 (S3-6) against the mock backend: back-dated sales (N1), price per batch (T8),
// sellable stock (N7), markdowns ended by removals (N8), duplicate CSV (N10), category
// rules (N11) and removal messages (N16, N21). Mirrors backend/tests/test_s3_6_fixes.py.
import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);
const tokenFor = async (userId, password) => (await call("POST", "/auth/login", { userId, password })).body.token;
const cashier = () => tokenFor("cashier1", "cashier123");
const manager = () => tokenFor("manager1", "manager123");
const staff = () => tokenFor("staff1", "staff123");
const hoursAgo = (h) => new Date(NOW.getTime() - h * 3600 * 1000).toISOString();
const csv = (text) => { const f = new FormData(); f.append("file", text); return f; };

beforeEach(() => resetMockDb(NOW));

describe("N1: back-dated sales", () => {
  it("refuses a soldAt older than 48 hours", async () => {
    const res = await call("POST", "/sales", { sku: "TOM-01", quantity: 1, soldAt: "2026-01-01" }, await cashier());
    expect(res.status).toBe(400);
    expect(res.body.error.message).toMatch(/too far in the past/);
  });

  it("accepts an offline sale from yesterday", async () => {
    const res = await call("POST", "/sales", { sku: "TOM-01", quantity: 1, soldAt: hoursAgo(20) }, await cashier());
    expect(res.status).toBe(201);
  });

  it("reports an old CSV row as a row error", async () => {
    const res = await call("POST", "/sales/csv", csv("sku,quantity,soldAt\nTOM-01,1,2020-01-01\nTOM-01,1,\n"), await cashier());
    expect(res.body.imported).toBe(1);
    expect(res.body.errors[0].message).toMatch(/too far in the past/);
  });
});

describe("T8 and N7", () => {
  it("shows the marked-down price per batch", async () => {
    const m = await manager();
    await call("POST", "/markdown-rules", { productId: 1, daysBeforeExpiry: 3, discountPercent: 25 }, m);
    await call("POST", "/markdowns/apply", undefined, m);
    const res = await call("POST", "/sales", { sku: "TOM-01", quantity: 14 }, await cashier());
    expect(res.body.batchesUsed[0]).toMatchObject({ batchId: 101, unitPrice: 22.5, originalPrice: 30, discountPercent: 25 });
    expect(res.body.batchesUsed[1]).toMatchObject({ batchId: 102, unitPrice: 30, discountPercent: null });
  });

  it("lists sellable stock without expired batches", async () => {
    const list = (await call("GET", "/products", undefined, await cashier())).body;
    const milk = list.find((p) => p.sku === "MLK-01");
    expect(milk.stock).toBeGreaterThan(milk.sellableStock);
  });
});

describe("N10: duplicate CSV", () => {
  it("refuses the same file twice", async () => {
    const t = await cashier();
    expect((await call("POST", "/sales/csv", csv("sku,quantity\nTOM-01,1\n"), t)).body.imported).toBe(1);
    const again = await call("POST", "/sales/csv", csv("sku,quantity\nTOM-01,1\n"), t);
    expect(again.status).toBe(409);
    expect(again.body.error.code).toBe("DUPLICATE_FILE");
  });
});

describe("N8, N11, N16, N21", () => {
  it("ends the markdown of a batch removed to zero", async () => {
    const m = await manager();
    await call("POST", "/markdown-rules", { productId: 1, daysBeforeExpiry: 3, discountPercent: 25 }, m);
    await call("POST", "/markdowns/apply", undefined, m);
    await call("POST", "/removals", { batchId: 101, qty: 12, reason: "Damaged" }, await staff());
    const md = (await call("GET", "/markdowns", undefined, m)).body.find((x) => x.batchId === 101);
    expect(md.status).toBe("ended");
  });

  it("refuses an unknown category and a contradicting product+category", async () => {
    const m = await manager();
    const a = await call("POST", "/markdown-rules", { category: "Daiyr", daysBeforeExpiry: 2, discountPercent: 10 }, m);
    expect(a.status).toBe(400);
    expect(a.body.error.message).toBe("Unknown category 'Daiyr'");
    const b = await call("POST", "/markdown-rules", { productId: 1, category: "Dairy", daysBeforeExpiry: 2, discountPercent: 10 }, m);
    expect(b.status).toBe(400);
  });

  it("gives a readable over-stock removal message", async () => {
    const res = await call("POST", "/removals", { batchId: 101, qty: 13, reason: "Damaged" }, await staff());
    expect(res.body.error.message).toBe("Insufficient stock: only 12 kg left in B-101");
  });
});
