// FR-14 markdown rules against the mock backend, which follows backend/app/markdowns
// and docs/frontend-api-contract.md (Sprint 2 markdowns section).
import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";
import { can, canOpen, menuFor } from "../../config/roles.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);
const tokenFor = async (userId, password) => (await call("POST", "/auth/login", { userId, password })).body.token;
const manager = () => tokenFor("manager1", "manager123");
const staff = () => tokenFor("staff1", "staff123");
const cashier = () => tokenFor("cashier1", "cashier123");
const admin = () => tokenFor("admin", "admin123");

// Seed (today = NOW): Tomato 30/kg has B-101 12 kg (2 days left) and B-102 25 kg (5 days left);
// Milk (Dairy) B-104 is expired, B-105 30 l has 3 days left; Paneer (Dairy) B-106 has 6 days left.
const TOMATO = 1;
const MILK = 3;
const addRule = (token, body) => call("POST", "/markdown-rules", body, token);

beforeEach(() => resetMockDb(NOW));

describe("adding rules (FR-14)", () => {
  it("lets a Manager add a product rule and lists it for staff", async () => {
    const m = await manager();
    const res = await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 25 });
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({
      productId: TOMATO, category: null, daysBeforeExpiry: 2, discountPercent: 25, active: true, createdBy: "manager1",
    });
    expect(res.body.ruleId).toEqual(expect.any(Number));
    expect(res.body.name).toMatch(/25% off/);

    const list = await call("GET", "/markdown-rules", undefined, await staff());
    expect(list.status).toBe(200);
    expect(list.body.map((r) => r.ruleId)).toEqual([res.body.ruleId]);
  });

  it("lets an Admin add a category rule with a name", async () => {
    const res = await addRule(await admin(), { category: "Dairy", daysBeforeExpiry: 3, discountPercent: 15, name: "Dairy week" });
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ productId: null, category: "Dairy", name: "Dairy week" });
  });

  it("rejects a discount over the maximum with 422 and saves nothing", async () => {
    const m = await manager();
    const res = await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 41 });
    expect(res.status).toBe(422);
    expect(res.body.error.code).toBe("DISCOUNT_EXCEEDS_MAX");
    expect(res.body.error.message).toBe("Discount exceeds maximum 40%");
    expect((await call("GET", "/markdown-rules", undefined, m)).body).toEqual([]);
  });

  it("accepts exactly the maximum (40%)", async () => {
    expect((await addRule(await manager(), { productId: TOMATO, daysBeforeExpiry: 1, discountPercent: 40 })).status).toBe(201);
  });

  it.each([
    [{ productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 0 }, "zero discount"],
    [{ productId: TOMATO, daysBeforeExpiry: 2, discountPercent: -5 }, "negative discount"],
    [{ productId: TOMATO, daysBeforeExpiry: 2 }, "missing discount"],
    [{ productId: TOMATO, daysBeforeExpiry: -1, discountPercent: 10 }, "negative days"],
    [{ productId: TOMATO, daysBeforeExpiry: 1.5, discountPercent: 10 }, "fractional days"],
  ])("rejects %j (%s) with 422", async (body) => {
    expect((await addRule(await manager(), body)).status).toBe(422);
  });

  it("404 for an unknown product", async () => {
    expect((await addRule(await manager(), { productId: 999, daysBeforeExpiry: 2, discountPercent: 10 })).status).toBe(404);
  });
});

describe("who can do what (SEC-2)", () => {
  it("Inventory Staff cannot add or delete rules, but can view them and apply", async () => {
    const m = await manager();
    const s = await staff();
    const rule = (await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 20 })).body;
    expect((await addRule(s, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 20 })).status).toBe(403);
    expect((await call("DELETE", `/markdown-rules/${rule.ruleId}`, undefined, s)).status).toBe(403);
    expect((await call("GET", "/markdown-rules", undefined, s)).status).toBe(200);
    expect((await call("POST", "/markdowns/apply", undefined, s)).status).toBe(200);
    expect((await call("GET", "/markdowns", undefined, s)).status).toBe(200);
  });

  it("a Cashier can use none of it, and no token gets 401", async () => {
    const c = await cashier();
    expect((await call("GET", "/markdown-rules", undefined, c)).status).toBe(403);
    expect((await call("POST", "/markdowns/apply", undefined, c)).status).toBe(403);
    expect((await call("GET", "/markdowns", undefined, c)).status).toBe(403);
    expect((await call("GET", "/markdown-rules")).status).toBe(401);
  });

  it("the menu and permissions follow the same rules", () => {
    for (const role of ["Admin", "Manager", "Inventory Staff"]) expect(canOpen(role, "/markdowns")).toBe(true);
    expect(canOpen("Cashier", "/markdowns")).toBe(false);
    expect(menuFor("Cashier").map((m) => m.path)).toEqual(["/sales"]);
    expect(can("Manager", "manageMarkdownRules")).toBe(true);
    expect(can("Admin", "manageMarkdownRules")).toBe(true);
    expect(can("Inventory Staff", "manageMarkdownRules")).toBe(false);
    expect(can("Inventory Staff", "applyMarkdowns")).toBe(true);
    expect(can("Cashier", "applyMarkdowns")).toBe(false);
  });
});

describe("deleting rules", () => {
  it("removes the rule from the list; deleting it again is 404", async () => {
    const m = await manager();
    const rule = (await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 20 })).body;
    const del = await call("DELETE", `/markdown-rules/${rule.ruleId}`, undefined, m);
    expect(del.status).toBe(200);
    expect(del.body).toEqual({ deleted: true, ruleId: rule.ruleId });
    expect((await call("GET", "/markdown-rules", undefined, m)).body).toEqual([]);
    expect((await call("DELETE", `/markdown-rules/${rule.ruleId}`, undefined, m)).status).toBe(404);
  });

  it("a deleted rule no longer marks anything down", async () => {
    const m = await manager();
    const rule = (await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 20 })).body;
    await call("DELETE", `/markdown-rules/${rule.ruleId}`, undefined, m);
    expect((await call("POST", "/markdowns/apply", undefined, m)).body).toEqual({ applied: 0, markdowns: [] });
  });
});

describe("applying rules and the marked-down list", () => {
  it("marks down only the batch inside the window, with original and discounted price", async () => {
    const m = await manager();
    await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 25 });
    const res = await call("POST", "/markdowns/apply", undefined, m);
    expect(res.status).toBe(200);
    expect(res.body.applied).toBe(1);
    expect(res.body.markdowns[0]).toMatchObject({
      batchId: 101, productId: TOMATO, productName: "Tomato", sku: "TOM-01",
      originalPrice: 30, discountPercent: 25, discountedPrice: 22.5,
      initialQuantity: 12, quantitySold: 0, remainingQuantity: 12, sellThroughPercent: 0, status: "active",
    });
    const list = (await call("GET", "/markdowns", undefined, m)).body;
    expect(list.map((x) => x.batchId)).toEqual([101]); // B-102 has 5 days left
  });

  it("applying again does not duplicate", async () => {
    const m = await manager();
    await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 25 });
    await call("POST", "/markdowns/apply", undefined, m);
    expect((await call("POST", "/markdowns/apply", undefined, m)).body.applied).toBe(0);
    expect((await call("GET", "/markdowns", undefined, m)).body).toHaveLength(1);
  });

  it("a product rule beats a category rule; expired and far-off batches are skipped", async () => {
    const m = await manager();
    await addRule(m, { category: "Dairy", daysBeforeExpiry: 3, discountPercent: 40 });
    await addRule(m, { productId: MILK, daysBeforeExpiry: 3, discountPercent: 10 });
    const list = (await call("POST", "/markdowns/apply", undefined, m)).body.markdowns;
    expect(list.map((x) => x.batchId)).toEqual([105]); // B-104 expired, Paneer B-106 has 6 days
    expect(list[0]).toMatchObject({ discountPercent: 10, discountedPrice: 25.2 }); // product rule wins even though lower
  });

  it("a stronger rule upgrades an existing markdown; a weaker one does not", async () => {
    const m = await manager();
    await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 20 });
    await call("POST", "/markdowns/apply", undefined, m);
    await addRule(m, { category: "Vegetables", daysBeforeExpiry: 2, discountPercent: 10 }); // loses to the product rule on Tomato
    const weaker = await call("POST", "/markdowns/apply", undefined, m);
    expect(weaker.body.markdowns.map((x) => x.batchId)).toEqual([108]); // only Spinach (also Vegetables) is new
    const tomato = (await call("GET", "/markdowns", undefined, m)).body.find((x) => x.batchId === 101);
    expect(tomato.discountPercent).toBe(20);
    await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 35 });
    const up = await call("POST", "/markdowns/apply", undefined, m);
    expect(up.body.applied).toBe(1);
    expect(up.body.markdowns[0]).toMatchObject({ batchId: 101, discountPercent: 35, discountedPrice: 19.5 });
    expect((await call("GET", "/markdowns", undefined, m)).body.filter((x) => x.batchId === 101)).toHaveLength(1);
  });

  it("applying with no rules does nothing", async () => {
    expect((await call("POST", "/markdowns/apply", undefined, await manager())).body).toEqual({ applied: 0, markdowns: [] });
  });
});

describe("a sale of a marked-down batch (FR-14, TC-EXP-08)", () => {
  async function markTomato(m) {
    await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 25 });
    await call("POST", "/markdowns/apply", undefined, m);
  }
  const sell = (c, sku, quantity) => call("POST", "/sales", { sku, quantity }, c);

  it("is billed at the discounted price and fills in sold / remaining / sell-through", async () => {
    const m = await manager();
    await markTomato(m);
    const sale = await sell(await cashier(), "TOM-01", 6); // all from B-101 (soonest expiry)
    expect(sale.status).toBe(201);
    expect(sale.body.amount).toBe(135); // 6 x 22.50, not 6 x 30
    const row = (await call("GET", "/markdowns", undefined, m)).body[0];
    expect(row).toMatchObject({ quantitySold: 6, remainingQuantity: 6, sellThroughPercent: 50, status: "active" });
  });

  it("bills the marked-down part at the discount and the rest at full price", async () => {
    const m = await manager();
    await markTomato(m);
    const sale = await sell(await cashier(), "TOM-01", 15); // 12 from B-101 + 3 from B-102
    expect(sale.body.amount).toBe(12 * 22.5 + 3 * 30);
    const row = (await call("GET", "/markdowns", undefined, m)).body[0];
    expect(row).toMatchObject({ quantitySold: 12, remainingQuantity: 0, sellThroughPercent: 100, status: "sold_out" });
  });

  it("leaves other products at the normal price", async () => {
    await markTomato(await manager());
    expect((await sell(await cashier(), "BAN-01", 5)).body.amount).toBe(30);
  });

  it("deleting the rule keeps the discount on batches already marked down", async () => {
    const m = await manager();
    const rule = (await addRule(m, { productId: TOMATO, daysBeforeExpiry: 2, discountPercent: 25 })).body;
    await call("POST", "/markdowns/apply", undefined, m);
    await call("DELETE", `/markdown-rules/${rule.ruleId}`, undefined, m);
    expect((await sell(await cashier(), "TOM-01", 4)).body.amount).toBe(90);
  });
});
