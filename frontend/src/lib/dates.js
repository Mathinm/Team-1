const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

/** Whole calendar days from `from` to `to` (negative if `to` is earlier). */
export function daysBetween(from, to) {
  return Math.round((startOfDay(to) - startOfDay(from)) / DAY_MS);
}

export function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

/** yyyy-mm-dd in local time (for <input type="date"> and API dates). */
export function toISODate(date) {
  const d = new Date(date);
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

/** yyyy-mm-ddThh:mm in local time (for <input type="datetime-local">). */
export function toLocalDateTime(date) {
  const d = new Date(date);
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${toISODate(d)}T${h}:${min}`;
}

export function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Expiry status used for the colour-coded badges (green / amber / red).
 * near = expires within `nearDays` days (default 2).
 */
export function expiryStatus(daysToExpiry, nearDays = 2) {
  if (daysToExpiry < 0) return "expired";
  if (daysToExpiry <= nearDays) return "near";
  return "fresh";
}

export function describeDaysToExpiry(days) {
  if (days < 0) return `Expired ${-days} day${days === -1 ? "" : "s"} ago`;
  if (days === 0) return "Expires today";
  if (days === 1) return "Expires tomorrow";
  return `${days} days left`;
}
