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
export function validateBatch(b) {
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
