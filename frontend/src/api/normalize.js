// The screens use one shape for alerts and fridges. These turn the backend's
// answers (docs/frontend-api-contract.md, issues #13-#15, #11) into that shape.
// Data that is already in the screen shape (the demo backend) passes through.

const ALERT_TYPE_KEYS = {
  LOW_STOCK: "low_stock",
  PROJECTED_LOW_STOCK: "projected_low_stock",
  PRE_EXPIRY: "expiry_soon",
  EXPIRY: "expired",
  STOCK_REMOVAL: "removal",
  REMOVAL: "removal",
  UNIT_FAILURE: "unit_failure",
  DOOR_OPEN: "door_open",
  TEMPERATURE: "temperature",
  POWER: "power",
};

export function normalizeAlert(a) {
  const type = ALERT_TYPE_KEYS[a.type] ?? String(a.type ?? "").toLowerCase();
  return { ...a, type, createdAt: a.triggeredAt ?? a.createdAt };
}

export function normalizeUnit(u) {
  if ("currentTemp" in u) return u; // already in screen shape
  const temp = u.temperature ?? null;
  return {
    ...u,
    name: u.name ?? u.unitId,
    status: String(u.status ?? "").toUpperCase() === "FAILED" ? "failed" : "ok",
    doorOpen: u.door === "OPEN",
    currentTemp: temp,
    inRange: temp === null ? null : temp >= u.tempMin && temp <= u.tempMax,
  };
}
