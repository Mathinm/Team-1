// Small shared UI pieces used across screens.

import { describeDaysToExpiry, expiryStatus } from "../lib/dates.js";

export function Field({ label, error, hint, children, id }) {
  return (
    <div className={`field${error ? " field--error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error ? (
        <span className="field__error" role="alert">{error}</span>
      ) : hint ? (
        <span className="field__hint">{hint}</span>
      ) : null}
    </div>
  );
}

/** Banner for success / error / info messages. */
export function Banner({ kind = "info", children, onClose }) {
  if (!children) return null;
  return (
    <div className={`banner banner--${kind}`} role={kind === "error" ? "alert" : "status"}>
      <span>{children}</span>
      {onClose && (
        <button type="button" className="banner__close" onClick={onClose} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}

const STATUS_TEXT = { fresh: "Fresh", near: "Near expiry", expired: "Expired" };
const STATUS_ICON = { fresh: "●", near: "▲", expired: "■" };

/** Expiry badge: colour plus icon plus text, so status never relies on colour alone. */
export function ExpiryBadge({ daysToExpiry }) {
  const status = expiryStatus(daysToExpiry);
  return (
    <span className={`badge badge--${status}`} title={describeDaysToExpiry(daysToExpiry)}>
      <span aria-hidden="true">{STATUS_ICON[status]}</span> {STATUS_TEXT[status]}
    </span>
  );
}

export function StockBadge({ stock, threshold }) {
  const low = stock < threshold;
  const out = stock <= 0;
  const status = out ? "expired" : low ? "near" : "fresh";
  const text = out ? "Out of stock" : low ? "Low stock" : "In stock";
  return (
    <span className={`badge badge--${status}`}>
      <span aria-hidden="true">{STATUS_ICON[status]}</span> {text}
    </span>
  );
}

export function Loading({ label = "Loading…" }) {
  return <p className="muted" role="status">{label}</p>;
}

export function EmptyState({ children }) {
  return <p className="empty">{children}</p>;
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

export function money(n) {
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
