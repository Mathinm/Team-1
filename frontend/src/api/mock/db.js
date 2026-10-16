// In-browser data store for mock mode. Seeded with a small realistic store so
// every screen has something to show. Saved to localStorage so a demo survives
// a page reload; call resetMockDb() (or clear site data) to start over.

import { addDays, toISODate } from "../../lib/dates.js";

const STORAGE_KEY = "pms.mockdb.v1";

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

  return {
    nextIds: { product: 7, batch: 101 + batches.length, sale: 5001 },
    suppliers,
    products,
    batches,
    sales: [],
  };
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
