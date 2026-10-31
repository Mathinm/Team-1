// Report and dashboard calculations for mock mode (FR-18). The backend owner
// can use these as the reference for what each report must contain.

import { daysBetween } from "../../lib/dates.js";
import { REPORT_TYPES } from "../../config/reports.js";

export { REPORT_TYPES };

const r2 = (n) => Math.round(n * 100) / 100;
const pct = (part, whole) => (whole > 0 ? r2((part / whole) * 100) : 0);

function inRange(iso, from, to) {
  const t = new Date(iso).getTime();
  return t >= from.getTime() && t <= to.getTime();
}

/** from/to are yyyy-mm-dd strings; the whole of both days is included. */
export function parseRange(fromStr, toStr) {
  const from = new Date(`${fromStr}T00:00:00`);
  const to = new Date(`${toStr}T23:59:59.999`);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || from > to) return null;
  return { from, to };
}

function productName(db, id) {
  return db.products.find((p) => p.productId === id)?.name ?? `#${id}`;
}

const builders = {
  stock(db, _range, now) {
    const columns = [
      { key: "product", label: "Product" },
      { key: "category", label: "Category" },
      { key: "onHand", label: "On hand", numeric: true },
      { key: "unit", label: "Unit" },
      { key: "batches", label: "Batches", numeric: true },
      { key: "nextExpiry", label: "Next expiry" },
      { key: "value", label: "Value at cost (Rs)", numeric: true },
      { key: "status", label: "Status" },
    ];
    const rows = db.products
      .filter((p) => p.active)
      .map((p) => {
        const batches = db.batches.filter((b) => b.productId === p.productId && b.quantity > 0);
        const onHand = r2(batches.reduce((s, b) => s + b.quantity, 0));
        const next = batches.map((b) => b.expiryDate).sort()[0];
        return {
          product: p.name,
          category: p.category,
          onHand,
          unit: p.unit,
          batches: batches.length,
          nextExpiry: next ?? "-",
          value: r2(onHand * p.costPrice),
          status: onHand <= 0 ? "Out of stock" : onHand < p.lowStockThreshold ? "Low stock" : next && daysBetween(now, next) < 0 ? "Has expired stock" : "OK",
        };
      });
    const total = r2(rows.reduce((s, r) => s + r.value, 0));
    return { columns, rows, summary: [{ label: "Total stock value", value: `Rs ${total}` }] };
  },

  wastage(db, { from, to }) {
    const columns = [
      { key: "product", label: "Product" },
      { key: "sold", label: "Sold", numeric: true },
      { key: "wasted", label: "Wasted", numeric: true },
      { key: "unit", label: "Unit" },
      { key: "wastePct", label: "Waste %", numeric: true },
      { key: "moneyLost", label: "Money lost (Rs)", numeric: true },
    ];
    const rows = db.products
      .map((p) => {
        const sold = db.sales.filter((s) => s.productId === p.productId && inRange(s.soldAt, from, to)).reduce((a, s) => a + s.quantity, 0);
        const rem = db.removals.filter((x) => x.productId === p.productId && inRange(x.removedAt, from, to));
        const wasted = rem.reduce((a, x) => a + x.quantity, 0);
        return {
          product: p.name,
          sold: r2(sold),
          wasted: r2(wasted),
          unit: p.unit,
          wastePct: pct(wasted, sold + wasted),
          moneyLost: r2(rem.reduce((a, x) => a + x.value, 0)),
        };
      })
      .filter((r) => r.sold > 0 || r.wasted > 0)
      .sort((a, b) => b.moneyLost - a.moneyLost);
    const lost = r2(rows.reduce((s, r) => s + r.moneyLost, 0));
    return { columns, rows, summary: [{ label: "Total money lost to waste", value: `Rs ${lost}` }] };
  },

  sellers(db, { from, to }) {
    const columns = [
      { key: "rank", label: "Rank", numeric: true },
      { key: "product", label: "Product" },
      { key: "quantity", label: "Quantity sold", numeric: true },
      { key: "unit", label: "Unit" },
      { key: "revenue", label: "Revenue (Rs)", numeric: true },
      { key: "tag", label: "" },
    ];
    const rows = db.products
      .map((p) => {
        const s = db.sales.filter((x) => x.productId === p.productId && inRange(x.soldAt, from, to));
        return { product: p.name, quantity: r2(s.reduce((a, x) => a + x.quantity, 0)), unit: p.unit, revenue: r2(s.reduce((a, x) => a + x.amount, 0)) };
      })
      .filter((r) => r.quantity > 0)
      .sort((a, b) => b.revenue - a.revenue)
      .map((r, i, all) => ({ rank: i + 1, ...r, tag: i < 3 ? "Best seller" : i >= all.length - 2 && all.length > 4 ? "Worst seller" : "" }));
    const revenue = r2(rows.reduce((s, r) => s + r.revenue, 0));
    return { columns, rows, summary: [{ label: "Total revenue", value: `Rs ${revenue}` }] };
  },

  "supplier-quality"(db, { from, to }) {
    const columns = [
      { key: "supplier", label: "Supplier" },
      { key: "deliveries", label: "Deliveries", numeric: true },
      { key: "received", label: "Units received", numeric: true },
      { key: "wasted", label: "Units wasted", numeric: true },
      { key: "wasteRate", label: "Waste rate %", numeric: true },
    ];
    const rows = db.suppliers
      .map((s) => {
        const d = db.deliveries.filter((x) => x.supplierId === s.supplierId && inRange(x.receivedAt, from, to));
        const received = d.reduce((a, x) => a + x.quantity, 0);
        const wasted = db.removals.filter((x) => x.supplierId === s.supplierId && inRange(x.removedAt, from, to)).reduce((a, x) => a + x.quantity, 0);
        return { supplier: s.name, deliveries: d.length, received: r2(received), wasted: r2(wasted), wasteRate: pct(wasted, received) };
      })
      .filter((r) => r.deliveries > 0 || r.wasted > 0)
      .sort((a, b) => b.wasteRate - a.wasteRate);
    return { columns, rows };
  },

  removals(db, { from, to }) {
    const columns = [
      { key: "date", label: "Date" },
      { key: "product", label: "Product" },
      { key: "batch", label: "Batch" },
      { key: "quantity", label: "Quantity", numeric: true },
      { key: "unit", label: "Unit" },
      { key: "reason", label: "Reason" },
      { key: "worker", label: "Removed by" },
      { key: "value", label: "Value (Rs)", numeric: true },
    ];
    const rows = db.removals
      .filter((x) => inRange(x.removedAt, from, to))
      .sort((a, b) => b.removedAt.localeCompare(a.removedAt))
      .map((x) => ({ date: x.removedAt, product: productName(db, x.productId), batch: `B-${x.batchId}`, quantity: x.quantity, unit: x.unit, reason: x.reason, worker: x.worker, value: x.value }));
    return { columns, rows };
  },

  temperature(db, { from, to }) {
    const columns = [
      { key: "day", label: "Day" },
      { key: "unit", label: "Unit" },
      { key: "allowed", label: "Allowed (°C)" },
      { key: "min", label: "Min °C", numeric: true },
      { key: "avg", label: "Avg °C", numeric: true },
      { key: "max", label: "Max °C", numeric: true },
      { key: "outOfRange", label: "Readings out of range", numeric: true },
    ];
    const groups = new Map();
    for (const r of db.readings ?? []) {
      if (r.type !== "temperature" || !inRange(r.recordedAt, from, to)) continue;
      const day = r.recordedAt.slice(0, 10);
      const key = `${day}|${r.unitId}`;
      if (!groups.has(key)) groups.set(key, { day, unitId: r.unitId, values: [] });
      groups.get(key).values.push(r.value);
    }
    const rows = [...groups.values()]
      .sort((a, b) => b.day.localeCompare(a.day) || a.unitId.localeCompare(b.unitId))
      .map((g) => {
        const u = db.units.find((x) => x.unitId === g.unitId);
        const out = g.values.filter((v) => v < u.tempMin || v > u.tempMax).length;
        return {
          day: g.day,
          unit: u.name,
          allowed: `${u.tempMin} to ${u.tempMax}`,
          min: Math.min(...g.values),
          avg: r2(g.values.reduce((a, v) => a + v, 0) / g.values.length),
          max: Math.max(...g.values),
          outOfRange: out,
        };
      });
    return { columns, rows };
  },

  "power-events"(db, { from, to }) {
    const columns = [
      { key: "start", label: "Mains failed" },
      { key: "end", label: "Restored" },
      { key: "minutes", label: "Duration (min)", numeric: true },
      { key: "takeover", label: "Backup took over (s)", numeric: true },
      { key: "note", label: "Note" },
    ];
    const rows = (db.powerEvents ?? [])
      .filter((e) => inRange(e.startedAt, from, to))
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
      .map((e) => ({
        start: e.startedAt,
        end: e.endedAt ?? "ongoing",
        minutes: e.endedAt ? Math.round((new Date(e.endedAt) - new Date(e.startedAt)) / 60000) : "-",
        takeover: e.backupTakeoverSeconds,
        note: e.backupTakeoverSeconds > 10 ? `${e.note} (over 10 s)` : e.note,
      }));
    return { columns, rows };
  },

  alerts(db, { from, to }) {
    const columns = [
      { key: "raised", label: "Raised" },
      { key: "severity", label: "Severity" },
      { key: "message", label: "Alert" },
      { key: "status", label: "Status" },
      { key: "ackBy", label: "Acknowledged by" },
    ];
    const rows = (db.alerts ?? [])
      .filter((a) => inRange(a.createdAt, from, to))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map((a) => ({ raised: a.createdAt, severity: a.severity, message: a.message, status: a.status, ackBy: a.acknowledgedBy ?? "-" }));
    return { columns, rows };
  },
};

export function buildReport(db, type, range, now = new Date()) {
  const meta = REPORT_TYPES.find((t) => t.type === type);
  if (!meta) return null;
  const report = builders[type](db, range, now);
  return { type, title: meta.title, ...report, summary: report.summary ?? [] };
}

export function buildDashboard(db, now = new Date()) {
  const products = db.products.filter((p) => p.active);
  const onHand = (p) => db.batches.filter((b) => b.productId === p.productId).reduce((s, b) => s + b.quantity, 0);

  const lowStock = products
    .map((p) => ({ productId: p.productId, name: p.name, stock: r2(onHand(p)), threshold: p.lowStockThreshold, unit: p.unit }))
    .filter((p) => p.stock < p.threshold)
    .sort((a, b) => a.stock / (a.threshold || 1) - b.stock / (b.threshold || 1));

  const expiringSoon = db.batches
    .filter((b) => b.quantity > 0 && daysBetween(now, b.expiryDate) <= 2)
    .map((b) => {
      const p = db.products.find((x) => x.productId === b.productId);
      return { batchId: b.batchId, productName: p?.name, quantity: b.quantity, unit: b.unit, expiryDate: b.expiryDate, daysToExpiry: daysBetween(now, b.expiryDate) };
    })
    .sort((a, b) => a.daysToExpiry - b.daysToExpiry);

  const today = now.toDateString();
  const salesToday = db.sales.filter((s) => new Date(s.soldAt).toDateString() === today);
  const weekAgo = new Date(now.getTime() - 7 * 86400000);
  const wasteWeek = db.removals.filter((x) => new Date(x.removedAt) >= weekAgo);
  const activeAlerts = (db.alerts ?? []).filter((a) => a.status === "active");

  return {
    salesToday: { count: salesToday.length, amount: r2(salesToday.reduce((s, x) => s + x.amount, 0)) },
    stockValue: r2(products.reduce((s, p) => s + onHand(p) * p.costPrice, 0)),
    wasteLast7Days: { value: r2(wasteWeek.reduce((s, x) => s + x.value, 0)), removals: wasteWeek.length },
    lowStock,
    expiringSoon,
    activeAlerts: {
      count: activeAlerts.length,
      critical: activeAlerts.filter((a) => a.severity === "critical").length,
      latest: [...activeAlerts].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 5),
    },
    units: (db.units ?? []).map((u) => ({ unitId: u.unitId, name: u.name, status: u.status })),
  };
}

