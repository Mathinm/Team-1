// Small shared UI pieces used across screens.

import { useLocation } from "react-router-dom";
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

// Page banner: section name, title and a slowly zooming store photo per screen (look only).
const PAGE_ART = {
  "/reports": ["Overview", "/img/hero-fruits.jpg"],
  "/products": ["Inventory", "/img/hero-fruits.jpg"],
  "/stock": ["Inventory", "/img/hero-veg.jpg"],
  "/stock-count": ["Inventory", "/img/login.jpg"],
  "/removals": ["Inventory", "/img/hero-veg.jpg"],
  "/markdowns": ["Inventory", "/img/categories/fruits.jpg"],
  "/sales": ["Inventory", "/img/hero-fruits.jpg"],
  "/alerts": ["Monitoring", "/img/login.jpg"],
  "/refrigeration": ["Monitoring", "/img/categories/dairy.jpg"],
  "/users": ["Admin", "/img/login.jpg"],
};

/** Banner key for a path: exact match or a sub-path, longest first ("/stock-count" never falls to "/stock"). */
export function pageArtKey(pathname) {
  return Object.keys(PAGE_ART)
    .sort((a, b) => b.length - a.length)
    .find((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function PageHeader({ title, subtitle, actions }) {
  const { pathname } = useLocation();
  const key = pageArtKey(pathname);
  const [section, img] = PAGE_ART[key] ?? ["Overview", "/img/login.jpg"];
  return (
    <header className="page-hero">
      <img className="page-hero__img" src={img} alt="" aria-hidden="true" onError={(e) => { e.currentTarget.style.display = "none"; }} />
      <span className="page-hero__shade" aria-hidden="true" />
      <div className="page-hero__body">
        <div className="page-hero__text">
          <span className="page-hero__crumb">{section} › {title}</span>
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {actions && <div className="page-hero__actions">{actions}</div>}
      </div>
    </header>
  );
}

export function money(n) {
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

const SEVERITY = {
  critical: { cls: "badge--expired", icon: "■", text: "Critical" },
  warning: { cls: "badge--near", icon: "▲", text: "Warning" },
  info: { cls: "badge--info", icon: "●", text: "Info" },
};

export function SeverityTag({ severity }) {
  const s = SEVERITY[severity] ?? SEVERITY.info;
  return (
    <span className={`badge ${s.cls}`}>
      <span aria-hidden="true">{s.icon}</span> {s.text}
    </span>
  );
}
