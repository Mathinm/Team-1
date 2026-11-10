import { beforeEach, describe, expect, it } from "vitest";
import { mockRequest } from "./handlers.js";
import { resetMockDb } from "./db.js";

const NOW = new Date("2026-10-20T10:00:00");
const call = (method, path, body, token) => mockRequest(method, path, body, token, NOW);
const tokenFor = async (userId, password) => (await call("POST", "/auth/login", { userId, password })).body.token;

beforeEach(() => resetMockDb(NOW));

describe("batch shelf-life validation (FR-2 mock API)", () => {
  it("accepts expiry on the last shelf-life day and rejects the following day", async () => {
    const manager = await tokenFor("manager1", "manager123");
    const allowed = await call("POST", "/batches", {
      productId: 1, supplierId: 1, quantity: 2, unit: "kg",
      receivedAt: NOW.toISOString(), expiryDate: "2026-10-25",
    }, manager);
    expect(allowed.status).toBe(201);

    const rejected = await call("POST", "/batches", {
      productId: 1, supplierId: 1, quantity: 2, unit: "kg",
      receivedAt: NOW.toISOString(), expiryDate: "2026-10-26",
    }, manager);
    expect(rejected.status).toBe(400);
    expect(rejected.body.error.message).toMatch(/5-day shelf-life/);
  });
});
