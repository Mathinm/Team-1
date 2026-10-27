import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);
const login = async (userId, password) =>
  (await call("POST", "/auth/login", { userId, password })).body.token;

beforeEach(() => resetMockDb(NOW));

describe("add supplier (issue #30)", () => {
  it("lets a Manager add a supplier that can then receive a batch", async () => {
    const manager = await login("manager1", "manager123");
    const res = await call("POST", "/suppliers", { name: "  New   Farm " }, manager);
    expect(res.status).toBe(201);
    expect(res.body.name).toBe("New Farm");
    const batch = await call("POST", "/batches", {
      productId: 1, supplierId: res.body.supplierId, quantity: 5,
      receivedAt: "2026-10-20T09:00:00", expiryDate: "2026-10-24",
    }, manager);
    expect(batch.status).toBe(201);
  });

  it("rejects a duplicate name, ignoring case (409)", async () => {
    const manager = await login("manager1", "manager123");
    const res = await call("POST", "/suppliers", { name: "fresh farms" }, manager);
    expect(res.status).toBe(409);
  });

  it("is Manager/Admin only (403 for Inventory Staff)", async () => {
    const staff = await login("staff1", "staff123");
    expect((await call("POST", "/suppliers", { name: "X" }, staff)).status).toBe(403);
  });
});
