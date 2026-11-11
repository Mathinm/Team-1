import { describe, expect, it } from "vitest";
import { pageArtKey } from "./ui.jsx";

describe("page banner lookup", () => {
  it("picks the most specific path, not the first prefix", () => {
    expect(pageArtKey("/stock-count")).toBe("/stock-count");
    expect(pageArtKey("/stock")).toBe("/stock");
  });

  it("matches sub-paths but not look-alike paths", () => {
    expect(pageArtKey("/products/12")).toBe("/products");
    expect(pageArtKey("/stockroom")).toBeUndefined();
    expect(pageArtKey("/dashboard")).toBeUndefined();
  });

  it("finds every screen that has a banner", () => {
    for (const p of ["/reports", "/products", "/stock", "/stock-count", "/removals", "/markdowns", "/sales", "/alerts", "/refrigeration", "/users"]) {
      expect(pageArtKey(p)).toBe(p);
    }
  });
});
