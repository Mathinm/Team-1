// Fake backend for mock mode. Every route follows the SAD 4.3 contract
// (paths, bodies, status codes, error format {error: {code, message}}),
// so switching to the real backend needs no UI change.

import { getDb, saveDb, MOCK_USERS } from "./db.js";
import { addDays, daysBetween, toISODate } from "../../lib/dates.js";
import { parseCsv } from "../../lib/csv.js";

const { ADMIN, MANAGER, STAFF, CASHIER } = {
  ADMIN: "Admin",
  MANAGER: "Manager",
  STAFF: "Inventory Staff",
  CASHIER: "Cashier",
};
const ANY = null; // any logged-in user

class HttpError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const fail = (status, code, message) => {
  throw new HttpError(status, code, message);
};

// ---------- auth ----------

function userFromToken(token) {
  if (!token?.startsWith("mock.")) return null;
  const userId = token.slice(5);
  return MOCK_USERS.find((u) => u.userId === userId) ?? null;
}

function login({ userId, password } = {}) {
  if (!userId || !password) fail(400, "MISSING_FIELD", "User ID and password are required");
  const user = MOCK_USERS.find((u) => u.userId === userId && u.password === password);
  // Same message for unknown user and wrong password (SAD 4.3).
  if (!user) fail(401, "INVALID_CREDENTIALS", "Invalid user ID or password");
  return {
    token: `mock.${user.userId}`,
    role: user.role,
    name: user.name,
    userId: user.userId,
    expiresIn: 3600,
  };
}

// ---------- helpers ----------

function productById(db, id) {
  const product = db.products.find((x) => x.productId === Number(id));
  if (!product) fail(404, "NOT_FOUND", "Unknown product");
  return product;
}

function stockOf(db, productId) {
  return db.batches
    .filter((b) => b.productId === productId)
    .reduce((sum, b) => sum + b.quantity, 0);
}

function sellableStock(db, productId, now) {
  return db.batches
    .filter((b) => b.productId === productId && daysBetween(now, b.expiryDate) >= 0)
    .reduce((sum, b) => sum + b.quantity, 0);
}

function withStock(db, product) {
  return { ...product, stock: round(stockOf(db, product.productId)) };
}

const round = (n) => Math.round(n * 1000) / 1000;

function checkProductBody(b) {
  const required = [
    "name", "sku", "category", "unit", "shelfLifeDays", "storageType",
    "tempMin", "tempMax", "costPrice", "sellingPrice",
  ];
  for (const k of required) {
    if (b?.[k] === undefined || b[k] === null || b[k] === "")
      fail(400, "MISSING_FIELD", `Missing field: ${k}`);
  }
  if (!["kg", "piece", "l"].includes(b.unit)) fail(400, "INVALID", "Unit must be kg, piece or l");
  if (Number(b.tempMin) >= Number(b.tempMax))
    fail(400, "INVALID", "Minimum temperature must be below maximum");
  if (Number(b.costPrice) <= 0 || Number(b.sellingPrice) <= 0)
    fail(400, "INVALID", "Prices must be positive");
}

/** FEFO deduction (FR-3, FR-7). Shared by manual, CSV and device sales. */
export function recordSale(db, { sku, quantity, soldAt }, now = new Date()) {
  const qty = Number(quantity);
  if (!sku || !Number.isFinite(qty) || qty <= 0)
    fail(400, "INVALID", "SKU and a quantity greater than 0 are required");
  const product = db.products.find((x) => x.sku === String(sku).trim().toUpperCase());
  if (!product) fail(404, "NOT_FOUND", `Unknown SKU ${sku}`);
  if (!product.active) fail(422, "INACTIVE", `${product.name} is deactivated`);

  const total = stockOf(db, product.productId);
  const sellable = sellableStock(db, product.productId, now);
  if (sellable <= 0 && total > 0) fail(422, "BATCH_EXPIRED", "Batch expired: no unexpired stock to sell");
  if (qty > sellable) fail(422, "INSUFFICIENT_STOCK", `Insufficient stock: only ${round(sellable)} ${product.unit} available`);

  const eligible = db.batches
    .filter((b) => b.productId === product.productId && b.quantity > 0 && daysBetween(now, b.expiryDate) >= 0)
    .sort((a, b) => a.expiryDate.localeCompare(b.expiryDate) || a.batchId - b.batchId);

  let left = qty;
  const batchesUsed = [];
  for (const b of eligible) {
    if (left <= 0) break;
    const take = Math.min(b.quantity, left);
    b.quantity = round(b.quantity - take);
    left = round(left - take);
    batchesUsed.push({ batchId: b.batchId, qty: take, expiryDate: b.expiryDate });
  }

  const sale = {
    saleId: db.nextIds.sale++,
    sku: product.sku,
    productId: product.productId,
    quantity: qty,
    unit: product.unit,
    soldAt: soldAt ? new Date(soldAt).toISOString() : now.toISOString(),
    batchesUsed,
    amount: round(qty * product.sellingPrice),
  };
  db.sales.push(sale);
  return {
    saleId: sale.saleId,
    productName: product.name,
    unit: product.unit,
    amount: sale.amount,
    batchesUsed,
    remainingStock: round(stockOf(db, product.productId)),
  };
}

// ---------- routes ----------

const routes = [
  ["POST", /^\/auth\/login$/, "public", (_m, body) => login(body)],
  ["POST", /^\/auth\/logout$/, ANY, () => null],
  ["GET", /^\/auth\/me$/, ANY, (_m, _b, user) => ({ userId: user.userId, name: user.name, role: user.role })],

  ["GET", /^\/suppliers$/, ANY, (_m, _b, _u, db) => db.suppliers],

  ["GET", /^\/products$/, ANY, (_m, _b, _u, db) => db.products.map((x) => withStock(db, x))],
  ["POST", /^\/products$/, [ADMIN, MANAGER], (_m, body, _u, db) => {
    checkProductBody(body);
    const sku = String(body.sku).trim().toUpperCase();
    if (db.products.some((x) => x.sku === sku)) fail(409, "DUPLICATE", `SKU ${sku} already exists`);
    const product = {
      ...body,
      sku,
      productId: db.nextIds.product++,
      lowStockThreshold: body.lowStockThreshold ?? 10,
      active: true,
    };
    db.products.push(product);
    return withStock(db, product);
  }],
  ["PUT", /^\/products\/(\d+)$/, [ADMIN, MANAGER], ([, id], body, _u, db) => {
    checkProductBody(body);
    const product = productById(db, id);
    const sku = String(body.sku).trim().toUpperCase();
    if (db.products.some((x) => x.sku === sku && x.productId !== product.productId))
      fail(409, "DUPLICATE", `SKU ${sku} already exists`);
    Object.assign(product, body, { sku, productId: product.productId, active: product.active });
    return withStock(db, product);
  }],
  ["PATCH", /^\/products\/(\d+)\/deactivate$/, [ADMIN, MANAGER], ([, id], _b, _u, db) => {
    const product = productById(db, id);
    product.active = false;
    return withStock(db, product);
  }],
  ["PATCH", /^\/products\/(\d+)\/activate$/, [ADMIN, MANAGER], ([, id], _b, _u, db) => {
    const product = productById(db, id);
    product.active = true;
    return withStock(db, product);
  }],

  ["GET", /^\/batches\/fefo\?productId=(\d+)$/, ANY, ([, id], _b, _u, db, now) => {
    productById(db, id);
    return db.batches
      .filter((b) => b.productId === Number(id) && b.quantity > 0)
      .sort((a, b) => a.expiryDate.localeCompare(b.expiryDate) || a.batchId - b.batchId)
      .map((b) => ({
        batchId: b.batchId,
        quantity: b.quantity,
        unit: b.unit,
        supplier: db.suppliers.find((s) => s.supplierId === b.supplierId)?.name ?? "-",
        receivedAt: b.receivedAt,
        expiryDate: b.expiryDate,
        daysInStore: daysBetween(b.receivedAt, now),
        daysToExpiry: daysBetween(now, b.expiryDate),
      }));
  }],
  ["POST", /^\/batches$/, [ADMIN, MANAGER, STAFF], (_m, body, _u, db) => {
    const product = productById(db, body?.productId);
    if (!product.active) fail(422, "INACTIVE", `${product.name} is deactivated`);
    if (!db.suppliers.some((s) => s.supplierId === Number(body.supplierId)))
      fail(400, "INVALID", "Unknown supplier");
    if (!(Number(body.quantity) > 0)) fail(400, "INVALID", "Quantity must be greater than 0");
    if (!body.receivedAt || !body.expiryDate) fail(400, "MISSING_FIELD", "Received date and expiry date are required");
    if (new Date(`${body.expiryDate}T23:59:59`) <= new Date(body.receivedAt))
      fail(400, "INVALID", "Expiry date must be after received date");
    const batch = {
      batchId: db.nextIds.batch++,
      productId: product.productId,
      supplierId: Number(body.supplierId),
      quantity: Number(body.quantity),
      initialQuantity: Number(body.quantity),
      unit: product.unit,
      receivedAt: new Date(body.receivedAt).toISOString(),
      expiryDate: body.expiryDate,
    };
    db.batches.push(batch);
    return { batchId: batch.batchId, newStock: round(stockOf(db, product.productId)) };
  }],
  // Restock (FR-4): a top-up without its own expiry label; expiry comes from
  // the product's standard shelf-life. Supplier defaults to the last one used.
  ["POST", /^\/restocks$/, [ADMIN, MANAGER, STAFF], (_m, body, _u, db, now) => {
    const product = productById(db, body?.productId);
    if (!(Number(body.quantity) > 0)) fail(400, "INVALID", "Quantity must be greater than 0");
    const last = [...db.batches].reverse().find((b) => b.productId === product.productId);
    const batch = {
      batchId: db.nextIds.batch++,
      productId: product.productId,
      supplierId: Number(body.supplierId ?? last?.supplierId ?? db.suppliers[0].supplierId),
      quantity: Number(body.quantity),
      initialQuantity: Number(body.quantity),
      unit: product.unit,
      receivedAt: now.toISOString(),
      expiryDate: toISODate(addDays(now, product.shelfLifeDays)),
    };
    db.batches.push(batch);
    return { batchId: batch.batchId, newStock: round(stockOf(db, product.productId)) };
  }],

  ["POST", /^\/sales$/, [ADMIN, CASHIER], (_m, body, _u, db, now) => recordSale(db, body ?? {}, now)],
  ["POST", /^\/sales\/csv$/, [ADMIN, CASHIER], async (_m, body, _u, db, now) => {
    const file = body instanceof FormData ? body.get("file") : null;
    if (!file) fail(400, "MISSING_FIELD", "Choose a CSV file");
    const text = typeof file === "string" ? file : await file.text();
    const { headers, rows } = parseCsv(text);
    if (!headers.includes("sku") || !headers.includes("quantity"))
      fail(400, "INVALID", "CSV must have the columns sku and quantity");
    const errors = [];
    let imported = 0;
    for (const { line, values } of rows) {
      try {
        recordSale(db, { sku: values.sku, quantity: values.quantity, soldAt: values.soldat || undefined }, now);
        imported++;
      } catch (e) {
        if (!(e instanceof HttpError)) throw e;
        errors.push({ line, message: e.message });
      }
    }
    return { imported, failed: errors.length, errors };
  }],
];

const DELAY_MS = 150;
// POST routes that create a resource answer 201 (login, CSV import answer 200).
const CREATED = new Set(["/products", "/batches", "/restocks", "/sales"]);

/** Mock transport: returns {status, body} like an HTTP response. */
export async function mockRequest(method, path, body, token, now = new Date()) {
  await new Promise((r) => setTimeout(r, DELAY_MS));
  const db = getDb();
  for (const [m, pattern, roles, handler] of routes) {
    if (m !== method) continue;
    const match = path.match(pattern);
    if (!match) continue;
    try {
      let user = null;
      if (roles !== "public") {
        user = userFromToken(token);
        if (!user) fail(401, "UNAUTHORIZED", "Your session has ended. Please log in again.");
        if (roles && !roles.includes(user.role))
          fail(403, "FORBIDDEN", "You don't have permission to do that.");
      }
      const result = await handler(match, body, user, db, now);
      if (method !== "GET") saveDb();
      const created = method === "POST" && CREATED.has(path);
      return { status: created ? 201 : 200, body: result };
    } catch (e) {
      if (e instanceof HttpError) {
        return { status: e.status, body: { error: { code: e.code, message: e.message } } };
      }
      throw e;
    }
  }
  return { status: 404, body: { error: { code: "NOT_FOUND", message: `No mock route for ${method} ${path}` } } };
}

export const __test = { HttpError, routes };
