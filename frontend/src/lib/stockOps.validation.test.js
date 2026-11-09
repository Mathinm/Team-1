import { describe, expect, it } from "vitest";
import {
  countVariance, removalReasonText, validateRemoval, validateStockCount,
} from "./validation.js";

const ok = { batchId: "101", qty: "3", reason: "Damaged", detail: "", available: 12, unit: "kg" };

describe("validateRemoval (FR-13)", () => {
  it("accepts a normal removal", () => expect(validateRemoval(ok)).toEqual({}));
  it("accepts removing the whole batch", () => expect(validateRemoval({ ...ok, qty: "12" })).toEqual({}));
  it("needs a batch", () => expect(validateRemoval({ ...ok, batchId: "" }).batchId).toBeTruthy());
  it("needs a reason", () => expect(validateRemoval({ ...ok, reason: "" }).reason).toBeTruthy());
  it.each(["", "0", "-2", "abc"])("rejects quantity %j", (qty) =>
    expect(validateRemoval({ ...ok, qty }).qty).toBeTruthy());
  it("rejects more than the batch holds", () =>
    expect(validateRemoval({ ...ok, qty: "12.5" }).qty).toMatch(/12/));
  it("rejects more than 3 decimals", () =>
    expect(validateRemoval({ ...ok, qty: "1.2345" }).qty).toMatch(/3 decimal/));
  it("pieces must be whole", () =>
    expect(validateRemoval({ ...ok, unit: "piece", qty: "2.5" }).qty).toMatch(/Whole/));
  it("keeps the reason inside 40 characters", () =>
    expect(validateRemoval({ ...ok, reason: "Other", detail: "x".repeat(40) }).reason).toBeTruthy());
});

describe("removalReasonText", () => {
  it("passes a preset reason through", () => expect(removalReasonText("Damaged")).toBe("Damaged"));
  it("adds the note to Other", () => expect(removalReasonText("Other", "  dropped  ")).toBe("Other: dropped"));
  it("Other with no note stays Other", () => expect(removalReasonText("Other", "")).toBe("Other"));
  it("ignores a note on a preset reason", () => expect(removalReasonText("Spoilage", "x")).toBe("Spoilage"));
});

describe("validateStockCount (FR-9)", () => {
  const good = { batchId: "101", counted: "10", reason: "Routine count", unit: "kg" };
  it("accepts a count", () => expect(validateStockCount(good)).toEqual({}));
  it("accepts 0", () => expect(validateStockCount({ ...good, counted: "0" })).toEqual({}));
  it.each(["", "-1", "abc"])("rejects count %j", (counted) =>
    expect(validateStockCount({ ...good, counted }).counted).toBeTruthy());
  it("needs a reason", () => expect(validateStockCount({ ...good, reason: "  " }).reason).toBeTruthy());
  it("caps the reason at 255", () =>
    expect(validateStockCount({ ...good, reason: "x".repeat(256) }).reason).toBeTruthy());
  it("pieces must be whole", () =>
    expect(validateStockCount({ ...good, unit: "piece", counted: "4.5" }).counted).toBeTruthy());
});

describe("countVariance", () => {
  it("is counted minus system", () => {
    expect(countVariance(12, 10)).toBe(-2);
    expect(countVariance(12, 13.5)).toBe(1.5);
    expect(countVariance(12, 12)).toBe(0);
  });
  it("hides floating point noise", () => expect(countVariance(0.1, 0.3)).toBe(0.2));
});
