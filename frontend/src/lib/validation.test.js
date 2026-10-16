import { describe, expect, it } from "vitest";
import { validateBatch, validateProduct, validateSale } from "./validation.js";
import { expiryStatus, daysBetween } from "./dates.js";
import { parseCsv, toCsv } from "./csv.js";

const goodProduct = {
  name: "Tomato", sku: "TOM-01", category: "Vegetables", unit: "kg",
  shelfLifeDays: "5", storageType: "Chilled", tempMin: "8", tempMax: "12",
  costPrice: "20", sellingPrice: "30", lowStockThreshold: "10",
};

describe("validateProduct (FR-1, TC-PROD-01)", () => {
  it("accepts a complete product", () => {
    expect(validateProduct(goodProduct)).toEqual({});
  });
  it("flags a missing shelf-life", () => {
    expect(validateProduct({ ...goodProduct, shelfLifeDays: "" })).toHaveProperty("shelfLifeDays");
  });
  it("rejects min temperature above max and negative price", () => {
    const e = validateProduct({ ...goodProduct, tempMin: "12", tempMax: "8", sellingPrice: "-5" });
    expect(e.tempMax).toMatch(/higher than minimum/);
    expect(e.sellingPrice).toBeDefined();
  });
});

describe("validateBatch (FR-2)", () => {
  const base = { productId: "1", supplierId: "1", quantity: "50", receivedAt: "2026-10-16T10:00" };
  it("rejects expiry before receipt", () => {
    expect(validateBatch({ ...base, expiryDate: "2026-10-15" }).expiryDate).toMatch(/after received/);
  });
  it("rejects zero and negative quantity", () => {
    expect(validateBatch({ ...base, expiryDate: "2026-10-20", quantity: "0" }).quantity).toBeDefined();
    expect(validateBatch({ ...base, expiryDate: "2026-10-20", quantity: "-5" }).quantity).toBeDefined();
  });
  it("accepts a valid batch", () => {
    expect(validateBatch({ ...base, expiryDate: "2026-10-20" })).toEqual({});
  });
});

describe("validateSale", () => {
  it("needs a product and positive quantity", () => {
    expect(Object.keys(validateSale({ sku: "", quantity: "0" }))).toEqual(["sku", "quantity"]);
  });
});

describe("dates", () => {
  it("counts calendar days", () => {
    expect(daysBetween("2026-10-16T23:00", "2026-10-18T01:00")).toBe(2);
  });
  it("classifies expiry status", () => {
    expect(expiryStatus(-1)).toBe("expired");
    expect(expiryStatus(2)).toBe("near");
    expect(expiryStatus(3)).toBe("fresh");
  });
});

describe("csv", () => {
  it("parses with line numbers and skips blank lines", () => {
    const { headers, rows } = parseCsv("sku,quantity\nTOM-01,2\n\nBAN-01,3\n");
    expect(headers).toEqual(["sku", "quantity"]);
    expect(rows.map((r) => r.line)).toEqual([2, 4]);
    expect(rows[1].values).toEqual({ sku: "BAN-01", quantity: "3" });
  });
  it("round-trips quoted cells", () => {
    const text = toCsv([{ key: "a", label: "A" }], [{ a: 'He said "hi", ok' }]);
    expect(parseCsv(text).rows[0].values.a).toBe('He said "hi", ok');
  });
});
