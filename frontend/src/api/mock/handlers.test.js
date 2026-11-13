import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);

async function tokenFor(userId, password) {
  const res = await call("POST", "/auth/login", { userId, password });
  return res.body.token;
}

beforeEach(() => {
  resetMockDb(NOW);
});

describe("auth (SEC-1, SEC-2)", () => {
  it("logs in with valid credentials and returns the role", async () => {
    const res = await call("POST", "/auth/login", { userId: "staff1", password: "staff123" });
    expect(res.status).toBe(200);
    expect(res.body.role).toBe("Inventory Staff");
  });

  it("gives the same message for unknown user and wrong password", async () => {
    const a = await call("POST", "/auth/login", { userId: "ghost99", password: "x" });
    const b = await call("POST", "/auth/login", { userId: "staff1", password: "wrong" });
    expect(a.status).toBe(401);
    expect(a.body.error.message).toBe(b.body.error.message);
  });

  it("blocks a cashier from creating products (403)", async () => {
    const t = await tokenFor("cashier1", "cashier123");
    const res = await call("POST", "/products", { name: "X" }, t);
    expect(res.status).toBe(403);
  });

  it("rejects calls without a token (401)", async () => {
    const res = await call("GET", "/products");
    expect(res.status).toBe(401);
  });
});

describe("sales with FEFO (FR-3, FR-7, TC-STK-07)", () => {
  it("takes stock from the earliest-expiring batch first", async () => {
    const t = await tokenFor("cashier1", "cashier123");
    // Tomato: batch 101 has 12 kg expiring in 2 days, batch 102 has 25 kg in 5 days.
    const res = await call("POST", "/sales", { sku: "TOM-01", quantity: 5 }, t);
    expect(res.status).toBe(201);
    expect(res.body.batchesUsed).toEqual([{
      batchId: 101, qty: 5, expiryDate: expect.any(String),
      unitPrice: 30, originalPrice: 30, discountPercent: null,
    }]);
    expect(res.body.remainingStock).toBe(32);
  });

  it("spans two batches when the first runs out", async () => {
    const t = await tokenFor("cashier1", "cashier123");
    const res = await call("POST", "/sales", { sku: "TOM-01", quantity: 15 }, t);
    expect(res.body.batchesUsed.map((b) => [b.batchId, b.qty])).toEqual([[101, 12], [102, 3]]);
  });

  it("never sells from an expired batch", async () => {
    const t = await tokenFor("cashier1", "cashier123");
    // Milk: batch 104 (8 l) expired yesterday, batch 105 (30 l) is fine.
    const res = await call("POST", "/sales", { sku: "MLK-01", quantity: 4 }, t);
    expect(res.body.batchesUsed.map((b) => b.batchId)).toEqual([105]);
  });

  it("rejects a sale larger than unexpired stock (422)", async () => {
    const t = await tokenFor("cashier1", "cashier123");
    const res = await call("POST", "/sales", { sku: "MLK-01", quantity: 31 }, t);
    expect(res.status).toBe(422);
    expect(res.body.error.message).toMatch(/Insufficient stock/);
  });

  it("imports valid CSV rows and reports bad ones with line numbers", async () => {
    const t = await tokenFor("cashier1", "cashier123");
    const form = new FormData();
    form.append("file", "sku,quantity\nTOM-01,1\nNOPE-1,2\nBAN-01,3\n");
    const res = await call("POST", "/sales/csv", form, t);
    expect(res.status).toBe(200);
    expect(res.body.imported).toBe(2);
    expect(res.body.errors).toEqual([{ line: 3, message: "Unknown SKU NOPE-1" }]);
  });
});

describe("batches (FR-2, FR-5, FR-6)", () => {
  it("rejects expiry before the received date", async () => {
    const t = await tokenFor("staff1", "staff123");
    const res = await call("POST", "/batches", {
      productId: 1, supplierId: 1, quantity: 10,
      receivedAt: "2026-10-20T09:00:00", expiryDate: "2026-10-19",
    }, t);
    expect(res.status).toBe(400);
  });

  it("lists batches in expiry order with age and days left", async () => {
    const t = await tokenFor("staff1", "staff123");
    const res = await call("GET", "/batches/fefo?productId=1", undefined, t);
    expect(res.body.map((b) => b.batchId)).toEqual([101, 102]);
    expect(res.body[0]).toMatchObject({ daysInStore: 3, daysToExpiry: 2 });
  });

  it("restock adds stock", async () => {
    const t = await tokenFor("staff1", "staff123");
    const res = await call("POST", "/restocks", { productId: 1, quantity: 10 }, t);
    expect(res.status).toBe(201);
    expect(res.body.newStock).toBe(47);
  });
});

describe("users (SEC-4): Admin only", () => {
  const NEW = { userId: "cash2", name: "Cashier Two", email: "cash2@example.com", role: "Cashier", password: "Cash2Pass!" };

  it("an Admin adds a user who can then log in, and no password comes back", async () => {
    const t = await tokenFor("admin", "admin123");
    const res = await call("POST", "/users", NEW, t);
    expect(res.status).toBe(201);
    expect(res.body.password).toBeUndefined();
    expect((await call("POST", "/auth/login", { userId: "cash2", password: "Cash2Pass!" })).status).toBe(200);
  });

  it("an Admin changes a role and deactivates a user (login refused)", async () => {
    const t = await tokenFor("admin", "admin123");
    expect((await call("PUT", "/users/staff1", { role: "Cashier" }, t)).body.role).toBe("Cashier");
    expect((await call("PATCH", "/users/cashier1/deactivate", null, t)).status).toBe(200);
    expect((await call("POST", "/auth/login", { userId: "cashier1", password: "cashier123" })).status).toBe(401);
    expect((await call("PATCH", "/users/admin/deactivate", null, t)).status).toBe(400);
  });

  it.each([["manager1", "manager123"], ["staff1", "staff123"], ["cashier1", "cashier123"]])(
    "%s gets 403 on every user endpoint",
    async (userId, password) => {
      const t = await tokenFor(userId, password);
      expect((await call("GET", "/users", null, t)).status).toBe(403);
      expect((await call("POST", "/users", NEW, t)).status).toBe(403);
      expect((await call("PATCH", "/users/cashier1/deactivate", null, t)).status).toBe(403);
    },
  );
});

describe("password reset (SEC-5)", () => {
  it("gives the same answer for unknown and real user IDs, and the link sets a new password", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    const unknown = await call("POST", "/auth/password-reset", { userId: "ghost99" });
    const real = await call("POST", "/auth/password-reset", { userId: "staff1" });
    expect(unknown.body.message).toBe(real.body.message);
    const token = log.mock.calls.at(-1)[0].match(/token=(\S+)/)[1];
    log.mockRestore();

    expect((await call("POST", "/auth/password-reset/confirm", { token, newPassword: "NewPass123" })).status).toBe(200);
    expect((await call("POST", "/auth/login", { userId: "staff1", password: "NewPass123" })).status).toBe(200);
    // a link works only once
    expect((await call("POST", "/auth/password-reset/confirm", { token, newPassword: "Other1234" })).status).toBe(400);
  });

  it("refuses the current password as the new one, and the link still works after", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    await call("POST", "/auth/password-reset", { userId: "staff1" });
    const token = log.mock.calls.at(-1)[0].match(/token=(\S+)/)[1];
    log.mockRestore();

    const same = await call("POST", "/auth/password-reset/confirm", { token, newPassword: "staff123" });
    expect(same.status).toBe(400);
    expect(same.body.error.code).toBe("SAME_PASSWORD");
    expect((await call("POST", "/auth/password-reset/confirm", { token, newPassword: "NewPass123" })).status).toBe(200);
  });

  it("refuses a made-up link", async () => {
    const res = await call("POST", "/auth/password-reset/confirm", { token: "nope", newPassword: "NewPass123" });
    expect(res.status).toBe(400);
  });
});
