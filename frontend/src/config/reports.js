// Report types (FR-18). `type` is the path segment in GET /api/reports/{type}.
export const REPORT_TYPES = [
  { type: "stock", title: "Stock on hand", help: "Current stock, value and next expiry per product (ignores dates)" },
  { type: "wastage", title: "Wastage and money lost", help: "Sold vs wasted per product, waste % and money lost" },
  { type: "sellers", title: "Best and worst sellers", help: "Products ranked by revenue" },
  { type: "supplier-quality", title: "Supplier quality", help: "Waste rate per supplier" },
  { type: "removals", title: "Removals", help: "Every removal with reason, worker and value" },
  { type: "temperature", title: "Temperature history", help: "Daily min / avg / max per refrigeration unit" },
  { type: "power-events", title: "Power events", help: "Mains failures and backup take-over time" },
  { type: "alerts", title: "Alerts", help: "All alerts raised and who acknowledged them" },
];
