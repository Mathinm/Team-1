// Fake backend for mock mode. Every route follows the SAD 4.3 contract
// (paths, bodies, status codes, error format {error: {code, message}}),
// so switching to the real backend needs no UI change.

import { getDb, saveDb, MOCK_USERS } from "./db.js";
import { addDays, daysBetween, toISODate } from "../../lib/dates.js";
import { parseCsv } from "../../lib/csv.js";
import { buildDashboard, buildReport, parseRange } from "./reports.js";

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

/** Accounts in the mock store (the demo users, plus any added on the Users screen). */
function usersOf(db) {
  if (!db.users) {
    db.users = MOCK_USERS.map((u) => ({
      ...u, email: `${u.userId}@example.com`, active: true, locked: false, storeId: 1,
    }));
  }
  return db.users;
}

function userFromToken(token) {
  if (!token?.startsWith("mock.")) return null;
  const userId = token.slice(5);
  return usersOf(getDb()).find((u) => u.userId === userId && u.active) ?? null;
}

function login({ userId, password } = {}) {
  if (!userId || !password) fail(400, "MISSING_FIELD", "User ID and password are required");
  const user = usersOf(getDb()).find(
    (u) => u.userId === userId && u.password === password && u.active,
  );
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
  if (Number(b.sellingPrice) < Number(b.costPrice))
    fail(400, "INVALID", "Selling price cannot be lower than cost price");
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
  let billed = 0;
  const batchesUsed = [];
  for (const b of eligible) {
    if (left <= 0) break;
    const take = Math.min(b.quantity, left);
    b.quantity = round(b.quantity - take);
    left = round(left - take);
    batchesUsed.push({ batchId: b.batchId, qty: take, expiryDate: b.expiryDate });
    // FR-14: a batch with an active markdown is billed at its discounted price.
    const md = activeMarkdown(db, b.batchId);
    if (md) {
      billed += take * md.discountedPrice;
      md.quantitySold = round(md.quantitySold + take);
      if (b.quantity <= 0) md.status = "sold_out";
    } else {
      billed += take * product.sellingPrice;
    }
  }

  const sale = {
    saleId: db.nextIds.sale++,
    sku: product.sku,
    productId: product.productId,
    quantity: qty,
    unit: product.unit,
    soldAt: soldAt ? new Date(soldAt).toISOString() : now.toISOString(),
    batchesUsed,
    amount: Math.round(billed * 100) / 100,
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

// ---------- markdown rules (FR-14) ----------
// Mirrors backend/app/markdowns/service.py: a rule marks down batches that are close
// to expiry; the best matching rule wins (product rule > category rule > store-wide rule).

const MAX_MARKDOWN_PERCENT = 40; // backend setting max_markdown_percent
const cents = (n) => Math.round(n * 100) / 100;

function activeMarkdown(db, batchId) {
  return (db.markdowns ?? []).find((m) => m.batchId === batchId && m.status === "active");
}

function createMarkdownRule(db, body, user, now) {
  const { productId, category, name } = body;
  const discount = Number(body.discountPercent);
  const days = body.daysBeforeExpiry === undefined || body.daysBeforeExpiry === "" ? 1 : Number(body.daysBeforeExpiry);
  if (!Number.isFinite(discount) || discount <= 0) fail(422, "VALIDATION", "Input should be greater than 0");
  if (!Number.isInteger(days) || days < 0) fail(422, "VALIDATION", "Input should be a whole number of days, 0 or more");
  if (discount > MAX_MARKDOWN_PERCENT)
    fail(422, "DISCOUNT_EXCEEDS_MAX", `Discount exceeds maximum ${MAX_MARKDOWN_PERCENT}%`);
  const hasProduct = productId !== undefined && productId !== null && productId !== "";
  if (hasProduct && !db.products.some((p) => p.productId === Number(productId)))
    fail(404, "NOT_FOUND", `Product #${productId} not found`);

  db.markdownRules ??= [];
  db.nextIds.markdownRule ??= 1;
  const rule = {
    ruleId: db.nextIds.markdownRule++,
    productId: hasProduct ? Number(productId) : null,
    category: category ? String(category) : null,
    daysBeforeExpiry: days,
    discountPercent: discount,
    name: name?.trim() || `${discount}% off at ${days}d to expiry`,
    active: true,
    createdBy: user.userId,
    createdAt: now.toISOString(),
  };
  db.markdownRules.push(rule);
  return rule;
}

const activeRules = (db) => (db.markdownRules ?? []).filter((r) => r.active).sort((a, b) => b.ruleId - a.ruleId);

function deleteMarkdownRule(db, id) {
  const rule = (db.markdownRules ?? []).find((r) => r.ruleId === Number(id) && r.active);
  if (!rule) fail(404, "NOT_FOUND", `Markdown rule #${id} not found`);
  rule.active = false; // soft delete, like the backend; markdowns already applied stay
  return { deleted: true, ruleId: rule.ruleId };
}

function markdownOut(db, m) {
  const product = db.products.find((p) => p.productId === m.productId);
  const batch = db.batches.find((b) => b.batchId === m.batchId);
  return {
    markdownId: m.markdownId,
    batchId: m.batchId,
    productId: m.productId,
    productName: product?.name ?? "",
    sku: product?.sku ?? "",
    originalPrice: m.originalPrice,
    discountPercent: m.discountPercent,
    discountedPrice: m.discountedPrice,
    initialQuantity: m.initialQuantity,
    quantitySold: m.quantitySold,
    remainingQuantity: batch?.quantity ?? 0,
    sellThroughPercent: m.initialQuantity > 0 ? Math.round((m.quantitySold / m.initialQuantity) * 1000) / 10 : 0,
    status: m.status,
    markedDownAt: m.markedDownAt,
  };
}

function listMarkdowns(db, ids) {
  return (db.markdowns ?? [])
    .filter((m) => !ids || ids.includes(m.markdownId))
    .sort((a, b) => b.markedDownAt.localeCompare(a.markedDownAt) || b.markdownId - a.markdownId)
    .map((m) => markdownOut(db, m));
}

function applyMarkdowns(db, now) {
  const rules = activeRules(db);
  db.markdowns ??= [];
  db.nextIds.markdown ??= 1;
  const touched = [];
  if (rules.length === 0) return { applied: 0, markdowns: [] };

  const batches = db.batches
    .filter((b) => b.quantity > 0 && daysBetween(now, b.expiryDate) >= 0)
    .sort((a, b) => a.expiryDate.localeCompare(b.expiryDate) || a.batchId - b.batchId);

  for (const batch of batches) {
    const product = db.products.find((p) => p.productId === batch.productId);
    if (!product || !product.active) continue;
    const daysLeft = daysBetween(now, batch.expiryDate);

    const matches = [];
    for (const r of rules) {
      if (daysLeft > r.daysBeforeExpiry) continue;
      if (r.productId !== null) {
        if (r.productId === product.productId) matches.push([3, r.discountPercent, r]);
      } else if (r.category) {
        if (r.category.toLowerCase() === product.category.toLowerCase()) matches.push([2, r.discountPercent, r]);
      } else {
        matches.push([1, r.discountPercent, r]);
      }
    }
    if (matches.length === 0) continue;
    matches.sort((a, b) => b[0] - a[0] || b[1] - a[1]);
    const best = matches[0][2];
    const discountedPrice = cents((product.sellingPrice * (100 - best.discountPercent)) / 100);

    const existing = activeMarkdown(db, batch.batchId);
    if (existing) {
      if (best.discountPercent <= existing.discountPercent) continue;
      existing.ruleId = best.ruleId;
      existing.discountPercent = best.discountPercent;
      existing.discountedPrice = discountedPrice;
      touched.push(existing.markdownId);
    } else {
      const md = {
        markdownId: db.nextIds.markdown++,
        batchId: batch.batchId,
        productId: product.productId,
        ruleId: best.ruleId,
        originalPrice: product.sellingPrice,
        discountPercent: best.discountPercent,
        discountedPrice,
        initialQuantity: batch.quantity,
        quantitySold: 0,
        status: "active",
        markedDownAt: now.toISOString(),
      };
      db.markdowns.push(md);
      touched.push(md.markdownId);
    }
  }
  return { applied: touched.length, markdowns: listMarkdowns(db, touched) };
}

// ---------- removals (FR-13) and stock counts (FR-9) ----------

function batchById(db, id) {
  const batch = db.batches.find((b) => b.batchId === Number(id));
  if (!batch) fail(404, "NOT_FOUND", "Unknown batch");
  return batch;
}

function checkReason(value, max) {
  const reason = String(value ?? "").trim();
  if (!reason || reason.length > max) fail(400, "VALIDATION", `reason must contain 1 to ${max} characters`);
  return reason;
}

/** Same rules as the backend: number, at most 3 decimals, whole pieces for "piece" units. */
function checkQty(value, product, { allowZero }) {
  const qty = Number(value);
  if (value === "" || value === null || value === undefined || !Number.isFinite(qty))
    fail(400, "INVALID", `Quantity must be a number (got '${value}')`);
  if (qty < 0 || (qty === 0 && !allowZero)) fail(400, "INVALID", "Quantity must be greater than 0");
  if (round(qty) !== qty) fail(400, "INVALID", "Quantity can have at most 3 decimal places");
  if (qty > 0 && product.unit === "piece" && !Number.isInteger(qty))
    fail(400, "INVALID", `${product.name} requires a whole-number quantity`);
  return qty;
}

function recordRemoval(db, { batchId, qty: rawQty, reason: rawReason } = {}, user, now) {
  const reason = checkReason(rawReason, 40);
  const batch = batchById(db, batchId);
  const product = productById(db, batch.productId);
  const qty = checkQty(rawQty, product, { allowZero: false });
  if (qty > batch.quantity)
    fail(422, "INSUFFICIENT_STOCK", `Insufficient stock: only ${batch.quantity} available in this batch`);

  batch.quantity = round(batch.quantity - qty);
  const removal = {
    removalId: db.nextIds.removal++,
    batchId: batch.batchId,
    productId: product.productId,
    supplierId: batch.supplierId,
    quantity: qty,
    unit: product.unit,
    reason,
    worker: user.userId,
    removedAt: now.toISOString(),
    value: round(qty * product.costPrice),
  };
  db.removals.push(removal);
  raise(db, now, {
    type: "removal",
    severity: "info",
    message: `${qty} ${product.unit} ${product.name} removed (${reason}) by ${user.userId}`,
    productId: product.productId,
  });
  return {
    removalId: removal.removalId,
    batchId: batch.batchId,
    qty,
    reason,
    recordedBy: user.userId,
    recordedAt: removal.removedAt,
    remainingQuantity: batch.quantity,
  };
}

function recordStockCount(db, { batchId, countedQuantity, reason: rawReason } = {}, user, now) {
  const reason = checkReason(rawReason, 255);
  const batch = batchById(db, batchId);
  const product = productById(db, batch.productId);
  const counted = checkQty(countedQuantity, product, { allowZero: true });

  const system = batch.quantity;
  const variance = round(counted - system);
  batch.quantity = counted;
  db.stockCounts ??= [];
  db.nextIds.stockCount ??= 1;
  const record = {
    stockCountId: db.nextIds.stockCount++,
    batchId: batch.batchId,
    productId: product.productId,
    systemQuantity: system,
    countedQuantity: counted,
    variance,
    reason,
    recordedBy: user.userId,
    recordedAt: now.toISOString(),
  };
  db.stockCounts.push(record);
  return {
    stockCountId: record.stockCountId,
    batchId: batch.batchId,
    systemQuantity: system,
    countedQuantity: counted,
    variance,
    reason,
    recordedBy: user.userId,
    recordedAt: record.recordedAt,
  };
}

// ---------- password reset (SEC-5) ----------
// Mock mode has no email: the link is printed to the browser console instead.

const RESET_SENT = "If that user ID exists, a reset link has been sent to its registered email.";
const RESET_INVALID = "This reset link is invalid or has expired. Ask for a new one.";

function requestReset(db, { userId } = {}, now) {
  const user = usersOf(db).find((u) => u.userId === String(userId ?? "").trim() && u.active);
  if (user) {
    const token = `demo-${Math.random().toString(36).slice(2, 12)}`;
    db.resets = [...(db.resets ?? []).filter((r) => r.userId !== user.userId),
      { token, userId: user.userId, expires: now.getTime() + 30 * 60 * 1000 }];
    console.info(`[mock email to ${user.email}] Reset link: /reset-password?token=${token}`);
  }
  return { message: RESET_SENT };
}

function confirmReset(db, { token, newPassword } = {}, now) {
  if ((newPassword ?? "").length < 8) fail(400, "INVALID", "Password must be at least 8 characters");
  const reset = (db.resets ?? []).find((r) => r.token === token && r.expires > now.getTime());
  const user = reset && usersOf(db).find((u) => u.userId === reset.userId && u.active);
  if (!user) fail(400, "RESET_LINK_INVALID", RESET_INVALID);
  // T5: same rule as the backend; the link stays usable so another password can be tried
  if (newPassword === user.password)
    fail(400, "SAME_PASSWORD", "New password must be different from your current password");
  user.password = newPassword;
  db.resets = db.resets.filter((r) => r !== reset);
  return { message: "Your password has been changed. Log in with the new password." };
}

// ---------- users (SEC-4): Admin only ----------

const userOut = ({ password: _pw, ...u }) => u;

function findUser(db, userId) {
  const user = usersOf(db).find((u) => u.userId === userId);
  if (!user) fail(404, "NOT_FOUND", "User not found");
  return user;
}

function createUser(db, b = {}) {
  const roles = [ADMIN, MANAGER, STAFF, CASHIER];
  if (!/^[A-Za-z0-9_.-]{3,50}$/.test(b.userId ?? "")) fail(400, "INVALID", "User ID: 3-50 letters, numbers, _ . -");
  if (!b.name?.trim()) fail(400, "INVALID", "Name is required");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(b.email ?? "")) fail(400, "INVALID", "Enter a valid email");
  if (!roles.includes(b.role)) fail(400, "INVALID", "Unknown role");
  if ((b.password ?? "").length < 8) fail(400, "INVALID", "Password must be at least 8 characters");
  if (usersOf(db).some((u) => u.userId === b.userId)) fail(409, "USER_EXISTS", "User ID already exists");
  const user = {
    userId: b.userId, name: b.name.trim(), email: b.email, role: b.role, password: b.password,
    active: true, locked: false, storeId: 1,
  };
  db.users.push(user);
  return userOut(user);
}

// ---------- routes ----------

const routes = [
  ["POST", /^\/auth\/login$/, "public", (_m, body) => login(body)],
  ["POST", /^\/auth\/logout$/, ANY, () => null],
  ["POST", /^\/auth\/password-reset$/, "public", (_m, body, _u, db, now) => requestReset(db, body, now)],
  ["POST", /^\/auth\/password-reset\/confirm$/, "public", (_m, body, _u, db, now) => confirmReset(db, body, now)],
  ["GET", /^\/auth\/me$/, ANY, (_m, _b, user) => ({ userId: user.userId, name: user.name, role: user.role })],

  ["GET", /^\/users$/, [ADMIN], (_m, _b, _u, db) => usersOf(db).map(userOut)],
  ["POST", /^\/users$/, [ADMIN], (_m, body, _u, db) => createUser(db, body)],
  ["PUT", /^\/users\/([A-Za-z0-9_.-]+)$/, [ADMIN], ([, id], b = {}, admin, db) => {
    const user = findUser(db, id);
    if (b.role !== undefined && b.role !== user.role) {
      if (user.userId === admin.userId) fail(400, "SELF_DEMOTION", "You cannot remove your own Admin role");
      user.role = b.role;
    }
    if (b.name !== undefined) user.name = String(b.name).trim() || user.name;
    if (b.email !== undefined) user.email = b.email;
    return userOut(user);
  }],
  ["PATCH", /^\/users\/([A-Za-z0-9_.-]+)\/(deactivate|activate)$/, [ADMIN], ([, id, action], _b, admin, db) => {
    const user = findUser(db, id);
    if (action === "deactivate" && user.userId === admin.userId)
      fail(400, "SELF_DEACTIVATION", "You cannot deactivate your own account");
    user.active = action === "activate";
    return userOut(user);
  }],
  ["PATCH", /^\/users\/([A-Za-z0-9_.-]+)\/unlock$/, [ADMIN], ([, id], _b, _u, db) => {
    findUser(db, id).locked = false;
    return userOut(findUser(db, id));
  }],

  ["GET", /^\/suppliers$/, ANY, (_m, _b, _u, db) => db.suppliers],
  ["POST", /^\/suppliers$/, [ADMIN, MANAGER], (_m, body, _u, db) => {
    const name = String(body?.name ?? "").split(/\s+/).filter(Boolean).join(" ");
    if (!name) fail(400, "VALIDATION", "Supplier name is required");
    if (name.length > 120) fail(400, "VALIDATION", "Supplier name is too long");
    if (db.suppliers.some((x) => x.name.toLowerCase() === name.toLowerCase()))
      fail(409, "DUPLICATE_SUPPLIER", "A supplier with this name already exists");
    const supplier = { supplierId: Math.max(0, ...db.suppliers.map((x) => x.supplierId)) + 1, name };
    db.suppliers.push(supplier);
    return supplier;
  }],

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
    if (body.unit && body.unit !== product.unit) {
      const stock = totalStock(db, product.productId);
      if (stock > 0) fail(400, "INVALID", `Cannot change unit of '${product.name}' while it has stock`);
    }
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
  ["POST", /^\/batches$/, [ADMIN, MANAGER, STAFF], (_m, body, _u, db, now) => {
    const product = productById(db, body?.productId);
    if (!product.active) fail(422, "INACTIVE", `${product.name} is deactivated`);
    if (!db.suppliers.some((s) => s.supplierId === Number(body.supplierId)))
      fail(400, "INVALID", "Unknown supplier");
    if (!(Number(body.quantity) > 0)) fail(400, "INVALID", "Quantity must be greater than 0");
    if (!body.receivedAt || !body.expiryDate) fail(400, "MISSING_FIELD", "Received date and expiry date are required");
    if (new Date(`${body.expiryDate}T23:59:59`) <= new Date(body.receivedAt))
      fail(400, "INVALID", "Expiry date must be after received date");
    const latestExpiry = toISODate(addDays(new Date(body.receivedAt), product.shelfLifeDays));
    if (body.expiryDate > latestExpiry)
      fail(400, "INVALID", `Expiry date cannot be later than ${latestExpiry} (${product.shelfLifeDays}-day shelf-life)`);
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
    if (body.expiryDate <= toISODate(now)) {
      raise(db, now, {
        type: "expired",
        severity: "critical",
        productId: product.productId,
        message: `${product.name} batch ${batch.batchId} expired on ${batch.expiryDate}`,
      });
    }
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

  // Waste / removals (FR-13): deducts from one batch and keeps a record with reason and worker.
  ["POST", /^\/removals$/, [ADMIN, MANAGER, STAFF], (_m, body, user, db, now) => recordRemoval(db, body ?? {}, user, now)],
  // Physical stock count (FR-9): the batch takes the counted quantity; variance is kept for audit.
  ["POST", /^\/stock-counts$/, [ADMIN, MANAGER, STAFF], (_m, body, user, db, now) => recordStockCount(db, body ?? {}, user, now)],

  // Markdown rules and marked-down batches (FR-14)
  ["GET", /^\/markdown-rules$/, [ADMIN, MANAGER, STAFF], (_m, _b, _u, db) => activeRules(db)],
  ["POST", /^\/markdown-rules$/, [ADMIN, MANAGER], (_m, body, user, db, now) => createMarkdownRule(db, body ?? {}, user, now)],
  ["DELETE", /^\/markdown-rules\/(\d+)$/, [ADMIN, MANAGER], ([, id], _b, _u, db) => deleteMarkdownRule(db, id)],
  ["POST", /^\/markdowns\/apply$/, [ADMIN, MANAGER, STAFF], (_m, _b, _u, db, now) => applyMarkdowns(db, now)],
  ["GET", /^\/markdowns$/, [ADMIN, MANAGER, STAFF], (_m, _b, _u, db) => listMarkdowns(db)],

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

  // Alerts (FR-10..FR-16, UI-4)
  ["GET", /^\/alerts(?:\?status=(active|acknowledged|resolved|open|all))?$/, [ADMIN, MANAGER, STAFF], ([, status = "all"], _b, _u, db) =>
    db.alerts
      .filter((a) => status === "all" || a.status === status || (status === "open" && a.status !== "resolved"))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))],
  ["POST", /^\/alerts\/(\d+)\/acknowledge$/, [ADMIN, MANAGER], ([, id], _b, user, db, now) => {
    const alert = db.alerts.find((a) => a.alertId === Number(id));
    if (!alert) fail(404, "NOT_FOUND", "Unknown alert");
    // Same as the backend: repeating is harmless and a resolved alert stays resolved.
    if (!alert.acknowledgedAt) {
      Object.assign(alert, { acknowledgedBy: user.userId, acknowledgedAt: now.toISOString() });
      if (alert.status === "active") alert.status = "acknowledged";
    }
    return alert;
  }],

  // Refrigeration units (FR-15, FR-16)
  ["PUT", /^\/refrigeration\/units\/([A-Za-z0-9-]+)$/, [ADMIN, MANAGER], ([, id], body = {}, _u, db, now) => {
    const unit = db.units.find((u) => u.unitId.toLowerCase() === id.toLowerCase());
    if (!unit) fail(404, "NOT_FOUND", "Unknown refrigeration unit");
    const nextMin = body.tempMin === undefined ? unit.tempMin : Number(body.tempMin);
    const nextMax = body.tempMax === undefined ? unit.tempMax : Number(body.tempMax);
    const nextDoorLimit = body.doorOpenLimitMinutes === undefined
      ? (unit.doorOpenLimitMinutes ?? 5) : Number(body.doorOpenLimitMinutes);
    if (![nextMin, nextMax].every(Number.isFinite) || nextMin < -60 || nextMin > 100 || nextMax < -60 || nextMax > 100 || nextMin >= nextMax)
      fail(400, "INVALID", "Minimum temperature must be below maximum");
    if (!Number.isInteger(nextDoorLimit) || nextDoorLimit < 1 || nextDoorLimit > 240)
      fail(400, "INVALID", "Door-open limit must be a whole number from 1 to 240 minutes");
    unit.tempMin = nextMin;
    unit.tempMax = nextMax;
    unit.doorOpenLimitMinutes = nextDoorLimit;
    const latest = latestReading(db, unit.unitId);
    const outside = latest && (latest.value < nextMin || latest.value > nextMax);
    const existing = db.alerts.find((a) => a.unitId && a.unitId.toLowerCase() === unit.unitId.toLowerCase() && a.type === "temperature" && a.status !== "resolved");
    if (outside && !existing) {
      raise(db, now, { type: "temperature", severity: "critical", unitId: unit.unitId,
        message: `${unit.name} temperature ${latest.value} °C is outside ${nextMin} to ${nextMax} °C` });
    } else if (!outside && existing) {
      existing.status = "resolved";
      existing.resolvedAt = now.toISOString();
      existing.resolution = "Safe range changed: current temperature is now in range";
    }
    return unitView(db, unit);
  }],
  ["GET", /^\/refrigeration\/units$/, [ADMIN, MANAGER, STAFF], (_m, _b, _u, db) => db.units.map((u) => unitView(db, u))],
  ["GET", /^\/refrigeration\/units\/([A-Za-z0-9-]+)\/readings\?hours=(\d+)$/, [ADMIN, MANAGER, STAFF], ([, id, hours], _b, _u, db, now) => {
    const unit = db.units.find((u) => u.unitId.toLowerCase() === id.toLowerCase());
    if (!unit) fail(404, "NOT_FOUND", "Unknown unit");
    const since = now.getTime() - Number(hours) * 3600000;
    return db.readings
      .filter((r) => r.unitId.toLowerCase() === unit.unitId.toLowerCase() && r.type === "temperature" && new Date(r.recordedAt).getTime() >= since)
      .map((r) => ({ recordedAt: r.recordedAt, value: r.value }));
  }],

  // Device API stand-in (owned by #4). Mock only: no device key, used by the
  // demo controls on the Refrigeration page to trigger alerts.
  ["POST", /^\/device\/readings$/, "public", (_m, body, _u, db, now) => deviceReading(db, body ?? {}, now)],

  // Dashboard and reports (FR-18)
  ["GET", /^\/dashboard$/, [ADMIN, MANAGER, STAFF], (_m, _b, _u, db, now) => buildDashboard(db, now)],
  ["GET", /^\/reports\/([a-z-]+)\?(.*)$/, [ADMIN, MANAGER], ([, type, qs], _b, _u, db, now) => {
    const params = new URLSearchParams(qs);
    const range = parseRange(params.get("from"), params.get("to"));
    if (!range) fail(400, "INVALID_RANGE", "Choose a valid date range (from must be on or before to)");
    const report = buildReport(db, type, range, now);
    if (!report) fail(404, "NOT_FOUND", `Unknown report: ${type}`);
    return { ...report, from: params.get("from"), to: params.get("to") };
  }],
];

function latestReading(db, unitId) {
  for (let i = db.readings.length - 1; i >= 0; i--) {
    const r = db.readings[i];
    if (r.unitId === unitId && r.type === "temperature") return r;
  }
  return null;
}

function unitView(db, u) {
  const last = latestReading(db, u.unitId);
  return {
    unitId: u.unitId,
    name: u.name,
    tempMin: u.tempMin,
    tempMax: u.tempMax,
    doorOpenLimitMinutes: u.doorOpenLimitMinutes ?? 5,
    status: u.status,
    doorOpen: u.doorOpen,
    currentTemp: last?.value ?? null,
    lastReadingAt: last?.recordedAt ?? null,
    inRange: last ? last.value >= u.tempMin && last.value <= u.tempMax : null,
  };
}

function raise(db, now, alert) {
  db.alerts.push({
    alertId: db.nextIds.alert++,
    createdAt: now.toISOString(),
    status: "active",
    acknowledgedBy: null,
    acknowledgedAt: null,
    unitId: null,
    productId: null,
    ...alert,
  });
}

/** {unitId, type: temperature|door|status, value} -> stores it and raises alerts. */
function deviceReading(db, { unitId, type, value, recordedAt }, now) {
  if (recordedAt) {
    const rec = new Date(recordedAt);
    if (rec.getTime() > now.getTime() + 5 * 60 * 1000) {
      fail(400, "INVALID", "Reading time cannot be in the future");
    }
  }
  const timestamp = recordedAt ? new Date(recordedAt).toISOString() : now.toISOString();
  const unit = db.units.find((u) => u.unitId === unitId);
  if (!unit) fail(400, "INVALID", "Unknown unit");
  let alertRaised = false;
  if (type === "temperature") {
    const v = Number(value);
    if (!Number.isFinite(v)) fail(400, "INVALID", `Temperature must be a number, got "${value}"`);
    db.readings.push({ unitId, type, value: v, recordedAt: timestamp });
    if (v < unit.tempMin || v > unit.tempMax) {
      raise(db, now, { type: "temperature", severity: "warning", unitId, message: `${unit.name} at ${v} °C, outside ${unit.tempMin} to ${unit.tempMax} °C` });
      alertRaised = true;
    }
  } else if (type === "door") {
    unit.doorOpen = value === true || value === "open";
    if (unit.doorOpen) {
      raise(db, now, { type: "door_open", severity: "warning", unitId, message: `${unit.name} door open for more than 2 minutes` });
      alertRaised = true;
    }
  } else if (type === "status") {
    const failed = value === "failed";
    if (failed && unit.status !== "failed") {
      raise(db, now, { type: "unit_failure", severity: "critical", unitId, message: `${unit.name} has failed` });
      alertRaised = true;
    }
    unit.status = failed ? "failed" : "ok";
  } else {
    fail(400, "INVALID", "type must be temperature, door or status");
  }
  return { status: "stored", alertRaised };
}

const DELAY_MS = 150;
// POST routes that create a resource answer 201 (login, CSV import answer 200).
const CREATED = new Set(["/products", "/suppliers", "/batches", "/restocks", "/sales", "/users", "/removals", "/stock-counts", "/markdown-rules"]);

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
