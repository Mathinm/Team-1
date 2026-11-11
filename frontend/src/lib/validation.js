// Client-side validation. Mirrors the backend rules in SAD 4.3 so users see
// errors next to the field before submitting. The backend still re-checks.

export const UNITS = ["kg", "piece", "l"];
export const CATEGORIES = ["Vegetables", "Fruits", "Dairy", "Bakery", "Meat & Fish", "Other"];
export const STORAGE_TYPES = ["Ambient", "Chilled", "Refrigerated", "Frozen"];
export const DEFAULT_LOW_STOCK_THRESHOLD = 10;

function isBlank(v) {
  return v === undefined || v === null || String(v).trim() === "";
}

function num(v) {
  return isBlank(v) ? NaN : Number(v);
}

/** FR-1 product fields. Returns {field: message}; empty object = valid. */
export function validateProduct(p) {
  const e = {};
  if (isBlank(p.name)) e.name = "Name is required";
  if (isBlank(p.sku)) e.sku = "SKU is required";
  else if (!/^[A-Za-z0-9-]{2,20}$/.test(String(p.sku).trim()))
    e.sku = "Use 2-20 letters, digits or dashes";
  if (isBlank(p.category)) e.category = "Category is required";
  if (!UNITS.includes(p.unit)) e.unit = "Choose kg, piece or l";
  if (isBlank(p.storageType)) e.storageType = "Storage type is required";

  const shelf = num(p.shelfLifeDays);
  if (!Number.isInteger(shelf) || shelf < 1) e.shelfLifeDays = "Whole number of days, at least 1";

  const tMin = num(p.tempMin);
  const tMax = num(p.tempMax);
  if (Number.isNaN(tMin)) e.tempMin = "Required";
  if (Number.isNaN(tMax)) e.tempMax = "Required";
  if (!e.tempMin && !e.tempMax && tMin >= tMax)
    e.tempMax = "Maximum must be higher than minimum";

  const cost = num(p.costPrice);
  const price = num(p.sellingPrice);
  if (Number.isNaN(cost) || cost <= 0) e.costPrice = "Must be a positive amount";
  if (Number.isNaN(price) || price <= 0) e.sellingPrice = "Must be a positive amount";

  const threshold = num(p.lowStockThreshold);
  if (!Number.isInteger(threshold) || threshold < 0)
    e.lowStockThreshold = "Whole number, 0 or more";
  return e;
}

/** FR-2 batch receipt. */
export function validateBatch(b, product) {
  const e = {};
  if (isBlank(b.productId)) e.productId = "Choose a product";
  if (isBlank(b.supplierId)) e.supplierId = "Choose a supplier";
  const qty = num(b.quantity);
  if (Number.isNaN(qty) || qty <= 0) e.quantity = "Quantity must be greater than 0";
  if (isBlank(b.receivedAt)) e.receivedAt = "Required";
  if (isBlank(b.expiryDate)) e.expiryDate = "Required";
  if (!e.receivedAt && !e.expiryDate) {
    const received = new Date(b.receivedAt);
    const expiry = new Date(`${b.expiryDate}T23:59:59`);
    if (expiry <= received) e.expiryDate = "Expiry date must be after received date";
    if (!e.expiryDate && product && Number.isInteger(Number(product.shelfLifeDays))) {
      const receivedDay = b.receivedAt.slice(0, 10);
      const [year, month, day] = receivedDay.split("-").map(Number);
      const latest = new Date(Date.UTC(year, month - 1, day + Number(product.shelfLifeDays)));
      const latestAllowed = latest.toISOString().slice(0, 10);
      if (b.expiryDate > latestAllowed) {
        e.expiryDate = `Expiry date cannot be later than ${latestAllowed} (${product.shelfLifeDays}-day shelf-life)`;
      }
    }
  }
  return e;
}

/** FR-4 restock. */
export function validateRestock(r) {
  const e = {};
  if (isBlank(r.productId)) e.productId = "Choose a product";
  const qty = num(r.quantity);
  if (Number.isNaN(qty) || qty <= 0) e.quantity = "Quantity must be greater than 0";
  return e;
}

/** FR-8 manual sale. */
export function validateSale(s) {
  const e = {};
  if (isBlank(s.sku)) e.sku = "Choose a product";
  const qty = num(s.quantity);
  if (Number.isNaN(qty) || qty <= 0) e.quantity = "Quantity must be greater than 0";
  return e;
}

/** Turn form strings into the numeric body the API expects. */
export function productToPayload(p) {
  return {
    name: p.name.trim(),
    sku: String(p.sku).trim().toUpperCase(),
    category: p.category,
    unit: p.unit,
    shelfLifeDays: Number(p.shelfLifeDays),
    storageType: p.storageType,
    tempMin: Number(p.tempMin),
    tempMax: Number(p.tempMax),
    costPrice: Number(p.costPrice),
    sellingPrice: Number(p.sellingPrice),
    lowStockThreshold: Number(p.lowStockThreshold),
  };
}

// ---------- Waste / removals (FR-13) and stock counts (FR-9) ----------

export const MAX_QTY = 999999.999; // same ceiling as the backend (check_quantity)
export const REMOVAL_REASONS = ["Damaged", "Spoilage", "Temperature breach", "Expired", "Other"];
export const REMOVAL_REASON_MAX = 40; // backend: reason is 1-40 characters
export const REMOVAL_OTHER_MAX = 30; // leaves room for the "Other: " prefix inside the 40
export const COUNT_REASON_MAX = 255; // backend: reason is 1-255 characters
export const COUNT_REASON_HINTS = [
  "Routine count",
  "Miscount at receiving",
  "Damaged stock found",
  "Shrinkage / loss",
];

/** The reason string sent to the API: "Other" plus the worker's note becomes "Other: note". */
export function removalReasonText(reason, detail = "") {
  const note = String(detail ?? "").trim();
  return reason === "Other" && note ? `Other: ${note}` : String(reason ?? "").trim();
}

function quantityProblem(value, unit, { allowZero }) {
  const qty = num(value);
  if (Number.isNaN(qty)) return "Enter a number";
  if (qty < 0 || (qty === 0 && !allowZero)) return allowZero ? "Cannot be negative" : "Quantity must be greater than 0";
  if (qty > MAX_QTY) return `At most ${MAX_QTY}`;
  if (Math.round(qty * 1000) / 1000 !== qty) return "At most 3 decimal places";
  if (unit === "piece" && !Number.isInteger(qty)) return "Whole pieces only";
  return null;
}

/** FR-13 removal. `available` = quantity left in the chosen batch. */
export function validateRemoval({ batchId, qty, reason, detail, available, unit }) {
  const e = {};
  if (isBlank(batchId)) e.batchId = "Choose the batch to remove from";
  const problem = quantityProblem(qty, unit, { allowZero: false });
  if (problem) e.qty = problem;
  else if (available !== undefined && Number(qty) > available)
    e.qty = `Only ${available} ${unit ?? ""} left in this batch`.trim();
  if (isBlank(reason)) e.reason = "Choose a reason";
  else if (removalReasonText(reason, detail).length > REMOVAL_REASON_MAX)
    e.reason = `At most ${REMOVAL_REASON_MAX} characters`;
  return e;
}

/** FR-9 stock count. Zero is allowed: the shelf is empty. */
export function validateStockCount({ batchId, counted, reason, unit }) {
  const e = {};
  if (isBlank(batchId)) e.batchId = "Choose the batch you counted";
  const problem = quantityProblem(counted, unit, { allowZero: true });
  if (problem) e.counted = problem;
  if (isBlank(reason)) e.reason = "Give a reason for the count";
  else if (String(reason).trim().length > COUNT_REASON_MAX)
    e.reason = `At most ${COUNT_REASON_MAX} characters`;
  return e;
}

/** counted - system, rounded so 0.1 + 0.2 style noise never shows. */
export function countVariance(system, counted) {
  return Math.round((Number(counted) - Number(system)) * 1000) / 1000;
}
