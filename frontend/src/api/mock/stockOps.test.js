// FR-13 (waste / removals) and FR-9 (stock counts) against the mock backend,
// which follows docs/frontend-api-contract.md (POST /removals, POST /stock-counts).
import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";
import { canOpen, can, menuFor } from "../../config/roles.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);
const tokenFor = async (userId, password) => (await call("POST", "/auth/login", { userId, password })).body.token;
const batchQty = async (token, productId, batchId) =>
  (await call("GET", `/batches/fefo?productId=${productId}`, undefined, token)).body.find((b) => b.batchId === batchId)?.quantity;

beforeEach(() => resetMockDb(NOW));

describe("removals (FR-13)", () => {
  it("deducts from the batch and returns the contract fields", async () => {
    const t = await tokenFor("staff1", "staff123");
    const res = await call("POST", "/removals", { batchId: 101, qty: 3, reason: "Damaged" }, t);
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ batchId: 101, qty: 3, reason: "Damaged", recordedBy: "staff1", remainingQuantity: 9 });
    expect(res.body.removalId).toEqual(expect.any(Number));
    expect(await batchQty(t, 1, 101)).toBe(9);
  });

  it("lowers the product's stock and shows up in the removals report with the worker", async () => {
    const staff = await tokenFor("staff1", "staff123");
    const manager = await tokenFor("manager1", "manager123");
    await call("POST", "/removals", { batchId: 101, qty: 2, reason: "Temperature breach" }, staff);
    const products = (await call("GET", "/products", undefined, staff)).body;
    expect(products.find((p) => p.productId === 1).stock).toBe(35); // 37 - 2
    const report = await call("GET", "/reports/removals?from=2026-10-20&to=2026-10-20", undefined, manager);
    expect(JSON.stringify(report.body)).toContain("Temperature breach");
  });

  it("raises an info alert on the Alerts screen", async () => {
    const t = await tokenFor("manager1", "manager123");
    await call("POST", "/removals", { batchId: 101, qty: 1, reason: "Spoilage" }, t);
    const alerts = (await call("GET", "/alerts?status=active", undefined, t)).body;
    expect(alerts.some((a) => a.type === "removal" && /Spoilage/.test(a.message))).toBe(true);
  });

  it("refuses more than the batch holds (422 INSUFFICIENT_STOCK) and changes nothing", async () => {
    const t = await tokenFor("staff1", "staff123");
    const res = await call("POST", "/removals", { batchId: 101, qty: 13, reason: "Damaged" }, t);
    expect(res.status).toBe(422);
    expect(res.body.error.code).toBe("INSUFFICIENT_STOCK");
    expect(await batchQty(t, 1, 101)).toBe(12);
  });

  it.each([
    [{ batchId: 101, qty: 0, reason: "Damaged" }, "zero quantity"],
    [{ batchId: 101, qty: -1, reason: "Damaged" }, "negative quantity"],
    [{ batchId: 101, qty: "abc", reason: "Damaged" }, "non-numeric quantity"],
    [{ batchId: 101, qty: 1, reason: "   " }, "blank reason"],
    [{ batchId: 101, qty: 1, reason: "x".repeat(41) }, "reason over 40 characters"],
    [{ batchId: 101, qty: 1.2345, reason: "Damaged" }, "more than 3 decimals"],
  ])("rejects %j (%s) with 400", async (body) => {
    const t = await tokenFor("staff1", "staff123");
    expect((await call("POST", "/removals", body, t)).status).toBe(400);
  });

  it("needs whole numbers for piece products (Banana, batch 103)", async () => {
    const t = await tokenFor("staff1", "staff123");
    expect((await call("POST", "/removals", { batchId: 103, qty: 2.5, reason: "Damaged" }, t)).status).toBe(400);
    expect((await call("POST", "/removals", { batchId: 103, qty: 2, reason: "Damaged" }, t)).status).toBe(201);
  });

  it("404 for an unknown batch; 403 for a cashier; 401 without a token", async () => {
    const staff = await tokenFor("staff1", "staff123");
    const cashier = await tokenFor("cashier1", "cashier123");
    expect((await call("POST", "/removals", { batchId: 9999, qty: 1, reason: "Damaged" }, staff)).status).toBe(404);
    expect((await call("POST", "/removals", { batchId: 101, qty: 1, reason: "Damaged" }, cashier)).status).toBe(403);
    expect((await call("POST", "/removals", { batchId: 101, qty: 1, reason: "Damaged" })).status).toBe(401);
  });

  it("removing the whole batch takes it off the FEFO list", async () => {
    const t = await tokenFor("staff1", "staff123");
    await call("POST", "/removals", { batchId: 101, qty: 12, reason: "Spoilage" }, t);
    expect(await batchQty(t, 1, 101)).toBeUndefined();
  });
});

describe("stock counts (FR-9)", () => {
  it("sets the batch to the counted quantity and returns the variance", async () => {
    const t = await tokenFor("staff1", "staff123");
    const res = await call("POST", "/stock-counts", { batchId: 101, countedQuantity: 10, reason: "Routine count" }, t);
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({
      batchId: 101, systemQuantity: 12, countedQuantity: 10, variance: -2,
      reason: "Routine count", recordedBy: "staff1",
    });
    expect(res.body.stockCountId).toEqual(expect.any(Number));
    expect(await batchQty(t, 1, 101)).toBe(10);
  });

  it("variance is positive when more is found than the system says", async () => {
    const t = await tokenFor("manager1", "manager123");
    const res = await call("POST", "/stock-counts", { batchId: 101, countedQuantity: 13.5, reason: "Miscount at receiving" }, t);
    expect(res.body.variance).toBe(1.5);
  });

  it("allows a count of 0 and the batch leaves the stock list", async () => {
    const t = await tokenFor("staff1", "staff123");
    const res = await call("POST", "/stock-counts", { batchId: 101, countedQuantity: 0, reason: "Shelf empty" }, t);
    expect(res.status).toBe(201);
    expect(res.body.variance).toBe(-12);
    expect(await batchQty(t, 1, 101)).toBeUndefined();
  });

  it("numbers each count (ids go up)", async () => {
    const t = await tokenFor("staff1", "staff123");
    const a = await call("POST", "/stock-counts", { batchId: 101, countedQuantity: 11, reason: "Routine count" }, t);
    const b = await call("POST", "/stock-counts", { batchId: 102, countedQuantity: 24, reason: "Routine count" }, t);
    expect(b.body.stockCountId).toBe(a.body.stockCountId + 1);
  });

  it.each([
    [{ batchId: 101, countedQuantity: -1, reason: "r" }, "negative count"],
    [{ batchId: 101, countedQuantity: "", reason: "r" }, "empty count"],
    [{ batchId: 101, countedQuantity: 5, reason: "" }, "missing reason"],
    [{ batchId: 101, countedQuantity: 5, reason: "x".repeat(256) }, "reason over 255 characters"],
    [{ batchId: 103, countedQuantity: 5.5, reason: "r" }, "fractional pieces"],
  ])("rejects %j (%s) with 400", async (body) => {
    const t = await tokenFor("staff1", "staff123");
    expect((await call("POST", "/stock-counts", body, t)).status).toBe(400);
  });

  it("404 for an unknown batch; 403 for a cashier", async () => {
    const staff = await tokenFor("staff1", "staff123");
    const cashier = await tokenFor("cashier1", "cashier123");
    expect((await call("POST", "/stock-counts", { batchId: 9999, countedQuantity: 1, reason: "r" }, staff)).status).toBe(404);
    expect((await call("POST", "/stock-counts", { batchId: 101, countedQuantity: 1, reason: "r" }, cashier)).status).toBe(403);
  });
});

describe("access to the new screens (SEC-2)", () => {
  it("Admin, Manager and Inventory Staff get both menu entries; Cashier gets neither", () => {
    for (const role of ["Admin", "Manager", "Inventory Staff"]) {
      expect(canOpen(role, "/stock-count")).toBe(true);
      expect(canOpen(role, "/removals")).toBe(true);
      expect(can(role, "recordRemoval") && can(role, "recordStockCount")).toBe(true);
    }
    expect(canOpen("Cashier", "/stock-count")).toBe(false);
    expect(canOpen("Cashier", "/removals")).toBe(false);
    expect(menuFor("Cashier").map((m) => m.path)).toEqual(["/sales"]);
  });
});
