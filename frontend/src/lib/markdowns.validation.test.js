import { describe, expect, it } from "vitest";
import { validateMarkdownRule } from "./validation.js";

const ok = { scope: "product", productId: "1", category: "", days: "2", discount: "25" };

describe("validateMarkdownRule (FR-14)", () => {
  it("accepts a product rule and a category rule", () => {
    expect(validateMarkdownRule(ok)).toEqual({});
    expect(validateMarkdownRule({ ...ok, scope: "category", productId: "", category: "Dairy" })).toEqual({});
  });
  it("needs the product or the category that the scope asks for", () => {
    expect(validateMarkdownRule({ ...ok, productId: "" }).productId).toBeTruthy();
    expect(validateMarkdownRule({ ...ok, scope: "category", category: "" }).category).toBeTruthy();
    // a leftover product choice does not satisfy a category rule
    expect(validateMarkdownRule({ ...ok, scope: "category", category: "" }).productId).toBeUndefined();
  });
  it.each(["", "-1", "1.5", "abc", "366"])("rejects days %j", (days) =>
    expect(validateMarkdownRule({ ...ok, days }).days).toBeTruthy());
  it("allows 0 days (marks down on the last day)", () => expect(validateMarkdownRule({ ...ok, days: "0" })).toEqual({}));
  it.each(["", "0", "-5", "abc", "101", "12.345"])("rejects discount %j", (discount) =>
    expect(validateMarkdownRule({ ...ok, discount }).discount).toBeTruthy());
  it("leaves the store maximum to the server (41% passes here, the API answers 422)", () =>
    expect(validateMarkdownRule({ ...ok, discount: "41" })).toEqual({}));
});
