// In-browser data store for mock mode. Seeded with a small realistic store so
// every screen has something to show. Saved to localStorage so a demo survives
// a page reload; call resetMockDb() (or clear site data) to start over.

import { addDays, toISODate } from "../../lib/dates.js";

const STORAGE_KEY = "pms.mockdb.v2";

export const MOCK_USERS = [
  { userId: "admin", name: "Asha Admin", role: "Admin", password: "admin123" },
  { userId: "manager1", name: "Manoj Manager", role: "Manager", password: "manager123" },
  { userId: "staff1", name: "Sita Staff", role: "Inventory Staff", password: "staff123" },
  { userId: "cashier1", name: "Kiran Cashier", role: "Cashier", password: "cashier123" },
];

function seed(now = new Date()) {
  const suppliers = [
    { supplierId: 1, name: "Fresh Farms" },
    { supplierId: 2, name: "Green Valley Produce" },
    { supplierId: 3, name: "Daily Dairy Co." },
    { supplierId: 4, name: "City Bakers" },
  ];

  const products = [
    p(1, "TOM-01", "Tomato", "Vegetables", "kg", 5, "Chilled", 8, 12, 20, 30, 10),
    p(2, "BAN-01", "Banana", "Fruits", "piece", 6, "Ambient", 13, 18, 4, 6, 24),
    p(3, "MLK-01", "Milk 1L", "Dairy", "l", 3, "Refrigerated", 2, 6, 22, 28, 15),
    p(4, "PAN-01", "Paneer", "Dairy", "kg", 7, "Refrigerated", 2, 4, 280, 360, 5),
    p(5, "BRD-01", "Bread Loaf", "Bakery", "piece", 3, "Ambient", 15, 25, 25, 40, 10),
    p(6, "SPN-01", "Spinach", "Vegetables", "kg", 3, "Chilled", 2, 6, 30, 45, 5),
  ];

  // [productId, supplierId, qty, receivedDaysAgo, expiresInDays]
  const batchSpec = [
    [1, 1, 12, 3, 2],
    [1, 2, 25, 1, 5],
    [2, 2, 60, 2, 4],
    [3, 3, 8, 4, -1], // expired: shows the "blocked" case
    [3, 3, 30, 1, 3],
    [4, 3, 6, 2, 6],
    [5, 4, 7, 1, 1],
    [6, 1, 4, 2, 1],
  ];
  const batches = batchSpec.map(([productId, supplierId, qty, ago, expiresIn], i) => {
    const product = products.find((x) => x.productId === productId);
    return {
      batchId: 101 + i,
      productId,
      supplierId,
      quantity: qty,
      initialQuantity: qty,
      unit: product.unit,
      receivedAt: addDays(now, -ago).toISOString(),
      expiryDate: toISODate(addDays(now, expiresIn)),
    };
  });

  const history = seedHistory(now, products, batches);

  return {
    nextIds: {
      product: 7,
      batch: 101 + batches.length,
      sale: 5001,
      removal: history.removals.length + 1,
      alert: history.alerts.length + 1,
    },
    suppliers,
    products,
    batches,
    ...history,
  };
}

// Small deterministic random generator so the demo data is the same every time.
function rng(seedValue) {
  let a = seedValue;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const atHour = (date, h, m = 0) => {
  const d = new Date(date);
  d.setHours(h, m, 0, 0);
  return d;
};

/** 30 days of sales, removals, fridge readings, power events and alerts. */
function seedHistory(now, products, batches) {
  const rand = rng(42);
  const dailyBase = { 1: 6, 2: 18, 3: 9, 4: 1.5, 5: 5, 6: 1.2 };

  // Past sales (one line per product per day). Today's sales come from the UI.
  const sales = [];
  let saleId = 1001;
  for (let ago = 30; ago >= 1; ago--) {
    const day = addDays(now, -ago);
    const weekend = [0, 6].includes(day.getDay()) ? 1.4 : 1;
    for (const product of products) {
      const qty = Math.round(dailyBase[product.productId] * weekend * (0.6 + rand() * 0.8) * 10) / 10;
      if (qty <= 0) continue;
      sales.push({
        saleId: saleId++,
        productId: product.productId,
        sku: product.sku,
        quantity: qty,
        unit: product.unit,
        soldAt: atHour(day, 10 + Math.floor(rand() * 9)).toISOString(),
        batchesUsed: [],
        amount: Math.round(qty * product.sellingPrice * 100) / 100,
      });
    }
  }

  // Removals with supplier attribution (supplier quality report).
  const workers = ["staff1", "manager1"];
  // [productId, supplierId, qty, daysAgo, reason]
  const removalSpec = [
    [1, 2, 3, 2, "Damaged"], [1, 1, 2.5, 6, "Expired"], [3, 3, 6, 4, "Expired"],
    [5, 4, 4, 1, "Expired"], [6, 1, 1.5, 3, "Temperature breach"], [2, 2, 8, 9, "Damaged"],
    [4, 3, 0.5, 12, "Expired"], [6, 1, 1, 15, "Expired"], [1, 2, 4, 20, "Temperature breach"],
    [5, 4, 3, 22, "Expired"], [3, 3, 4, 26, "Expired"], [2, 2, 6, 28, "Other"],
  ];
  const removals = removalSpec.map(([productId, supplierId, quantity, ago, reason], i) => {
    const product = products.find((x) => x.productId === productId);
    return {
      removalId: i + 1,
      batchId: 90 - i, // older, already-emptied batches
      productId,
      supplierId,
      quantity,
      unit: product.unit,
      reason,
      worker: workers[i % 2],
      removedAt: atHour(addDays(now, -ago), 9 + (i % 8)).toISOString(),
      value: Math.round(quantity * product.costPrice * 100) / 100,
    };
  });

  // Supplier deliveries over the month (for supplier quality: received vs wasted).
  const deliveries = [];
  for (const b of batches) deliveries.push({ supplierId: b.supplierId, productId: b.productId, quantity: b.initialQuantity, receivedAt: b.receivedAt });
  for (let ago = 28; ago >= 5; ago -= 4) {
    for (const product of products) {
      const supplierId = { 1: ago % 8 === 0 ? 1 : 2, 2: 2, 3: 3, 4: 3, 5: 4, 6: 1 }[product.productId];
      deliveries.push({
        supplierId,
        productId: product.productId,
        quantity: Math.round(dailyBase[product.productId] * 4 * 1.1),
        receivedAt: atHour(addDays(now, -ago), 7).toISOString(),
      });
    }
  }

  // Refrigeration units and readings every 30 min for the last 7 days.
  const units = [
    { unitId: "FR-1", name: "Fridge 1 (Dairy)", tempMin: 2, tempMax: 6, status: "ok", doorOpen: false },
    { unitId: "CH-1", name: "Chiller (Produce)", tempMin: 4, tempMax: 10, status: "ok", doorOpen: false },
    { unitId: "FR-2", name: "Fridge 2 (Backup)", tempMin: 2, tempMax: 6, status: "failed", doorOpen: false },
  ];
  const readings = [];
  const start = addDays(now, -7);
  for (let t = start.getTime(); t <= now.getTime(); t += 30 * 60 * 1000) {
    for (const u of units) {
      const mid = (u.tempMin + u.tempMax) / 2;
      let value = mid + (rand() - 0.5) * (u.tempMax - u.tempMin) * 0.7;
      const hoursAgo = (now.getTime() - t) / 3600000;
      // Chiller breach yesterday afternoon (door left open).
      if (u.unitId === "CH-1" && hoursAgo > 20 && hoursAgo < 22) value = u.tempMax + 1.5 + rand();
      // Fridge 2 failed 3 hours ago and is warming up.
      if (u.unitId === "FR-2" && hoursAgo < 3) value = u.tempMax + (3 - hoursAgo) * 2.2;
      readings.push({ unitId: u.unitId, type: "temperature", value: Math.round(value * 10) / 10, recordedAt: new Date(t).toISOString() });
    }
  }

  const powerEvents = [
    { eventId: 1, startedAt: atHour(addDays(now, -11), 14, 5).toISOString(), endedAt: atHour(addDays(now, -11), 14, 47).toISOString(), backupTakeoverSeconds: 6, note: "Mains failure, backup generator took over" },
    { eventId: 2, startedAt: atHour(addDays(now, -3), 19, 30).toISOString(), endedAt: atHour(addDays(now, -3), 19, 41).toISOString(), backupTakeoverSeconds: 14, note: "Mains failure, backup slow to start" },
  ];

  const hoursAgo = (h) => new Date(now.getTime() - h * 3600000).toISOString();
  const alerts = [
    { type: "unit_failure", severity: "critical", message: "Fridge 2 (Backup) has failed", unitId: "FR-2", createdAt: hoursAgo(3), status: "active" },
    { type: "expired", severity: "critical", message: "Milk 1L batch B-104 has expired - remove it from the shelf", productId: 3, createdAt: hoursAgo(9), status: "active" },
    { type: "low_stock", severity: "warning", message: "Bread Loaf is below its low-stock threshold (7 of 10)", productId: 5, createdAt: hoursAgo(5), status: "active" },
    { type: "low_stock", severity: "warning", message: "Spinach is below its low-stock threshold (4 of 5)", productId: 6, createdAt: hoursAgo(6), status: "active" },
    { type: "expiry_soon", severity: "warning", message: "Bread Loaf batch B-107 expires tomorrow", productId: 5, createdAt: hoursAgo(10), status: "active" },
    { type: "projected_low_stock", severity: "info", message: "Tomato is projected to fall below 10 kg tomorrow", productId: 1, createdAt: hoursAgo(11), status: "active" },
    { type: "temperature", severity: "warning", message: "Chiller (Produce) at 11.9 °C, above 10 °C", unitId: "CH-1", createdAt: hoursAgo(21), status: "acknowledged", acknowledgedBy: "manager1", acknowledgedAt: hoursAgo(20.5) },
    { type: "door_open", severity: "warning", message: "Chiller (Produce) door open for more than 2 minutes", unitId: "CH-1", createdAt: hoursAgo(21.5), status: "acknowledged", acknowledgedBy: "staff1", acknowledgedAt: hoursAgo(21.3) },
    { type: "power", severity: "warning", message: "Mains power failure; backup took 14 s to take over", createdAt: atHour(addDays(now, -3), 19, 30).toISOString(), status: "acknowledged", acknowledgedBy: "manager1", acknowledgedAt: atHour(addDays(now, -3), 19, 45).toISOString() },
    { type: "removal", severity: "info", message: "3 kg Tomato removed (Damaged) by staff1", productId: 1, createdAt: removals[0].removedAt, status: "acknowledged", acknowledgedBy: "manager1", acknowledgedAt: removals[0].removedAt },
  ].map((a, i) => ({ alertId: i + 1, acknowledgedBy: null, acknowledgedAt: null, unitId: null, productId: null, ...a }));

  return { sales, removals, deliveries, units, readings, powerEvents, alerts };
}

function p(id, sku, name, category, unit, shelf, storage, tMin, tMax, cost, price, threshold) {
  return {
    productId: id,
    sku,
    name,
    category,
    unit,
    shelfLifeDays: shelf,
    storageType: storage,
    tempMin: tMin,
    tempMax: tMax,
    costPrice: cost,
    sellingPrice: price,
    lowStockThreshold: threshold,
    active: true,
  };
}

let db = null;

export function getDb() {
  if (db) return db;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) db = JSON.parse(saved);
  } catch {
    /* ignore: fall back to a fresh seed */
  }
  if (!db) db = seed();
  return db;
}

export function saveDb() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(db));
  } catch {
    /* storage unavailable: data lives until reload */
  }
}

export function resetMockDb(now) {
  db = seed(now);
  saveDb();
  return db;
}
