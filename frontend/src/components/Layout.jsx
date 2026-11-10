import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { canOpen, menuFor } from "../config/roles.js";
import { asBackground } from "../api/background.js";
import { api } from "../api/endpoints.js";
import { USE_MOCK } from "../api/client.js";

// Menu sections, in order. Each menu entry from roles.js lands in the first section that lists it.
const SECTIONS = [
  { label: "Overview", paths: ["/dashboard", "/reports"] },
  { label: "Inventory", paths: ["/products", "/stock", "/stock-count", "/removals", "/sales"] },
  { label: "Monitoring", paths: ["/alerts", "/refrigeration"] },
  { label: "Admin", paths: ["/users"] },
];

// Line icons (24x24, stroke). Decorative: the label next to each icon carries the meaning.
const ICONS = {
  "/dashboard": "M3 3h7v9H3z M14 3h7v5h-7z M14 12h7v9h-7z M3 16h7v5H3z",
  "/reports": "M3 3v18h18 M7 15l4-4 3 3 5-6",
  "/products": "M21 8l-9-5-9 5 9 5 9-5z M3 8v8l9 5 9-5V8 M12 13v8",
  "/stock": "M12 2l9 5-9 5-9-5 9-5z M3 12l9 5 9-5 M3 17l9 5 9-5",
  "/stock-count": "M9 11l3 3 8-8 M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9",
  "/removals": "M3 6h18 M8 6V4h8v2 M6 6l1 14h10l1-14",
  "/sales": "M3 3h2l2.4 12.4a2 2 0 0 0 2 1.6h8.2a2 2 0 0 0 2-1.6L21 7H6 M9 21h.01 M18 21h.01",
  "/alerts": "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9 M10.3 21a1.94 1.94 0 0 0 3.4 0",
  "/refrigeration": "M5 2h14v20H5z M5 10h14 M9 5v2 M9 13v4",
  "/users": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75",
};

export function Icon({ d, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function initials(name = "") {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
}

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const items = menuFor(user.role);
  const activeAlerts = useActiveAlertCount(canOpen(user.role, "/alerts"));
  const navRef = useRef(null);
  const [pill, setPill] = useState(null);

  const sections = SECTIONS.map((s) => ({
    label: s.label,
    items: items.filter((m) => s.paths.includes(m.path)),
  })).filter((s) => s.items.length);

  // The white highlight slides to the active menu entry.
  useLayoutEffect(() => {
    const place = () => {
      const el = navRef.current?.querySelector("a.active");
      setPill(el ? { top: el.offsetTop, height: el.offsetHeight } : null);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [location.pathname, items.length]);

  // New page starts at the top.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="shell">
      <header className="topbar">
        <button
          type="button"
          className="topbar__menu"
          aria-label="Open menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <Icon d="M3 6h18 M3 12h18 M3 18h18" size={22} />
        </button>
        <span className="topbar__brand">PMS</span>
        <span className="topbar__title">Perishables</span>
        <div className="topbar__user">
          <span className="avatar-sm" aria-hidden="true">{initials(user.name)}</span>
          <button type="button" className="btn btn--ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      {open && <button type="button" className="sidenav-scrim" aria-label="Close menu" onClick={() => setOpen(false)} />}

      <nav className={`sidenav${open ? " sidenav--open" : ""}`} aria-label="Main">
        <div className="sidenav__brand">
          <span className="sidenav__logo">PMS</span>
          <span className="sidenav__name">Perishables</span>
          {USE_MOCK && <span className="sidenav__demo" title="Using built-in demo data">Demo</span>}
        </div>

        <div className="sidenav__links" ref={navRef}>
          {pill && <span className="sidenav__pill" style={{ top: pill.top, height: pill.height }} aria-hidden="true" />}
          {sections.map((s) => (
            <div key={s.label} className="sidenav__section">
              <span className="sidenav__label">{s.label}</span>
              {s.items.map((m) => (
                <NavLink key={m.path} to={m.path} onClick={() => setOpen(false)}>
                  <Icon d={ICONS[m.path] ?? ICONS["/dashboard"]} />
                  <span className="sidenav__text">{m.label}</span>
                  {m.path === "/alerts" && activeAlerts > 0 && (
                    <span className="nav-count" aria-label={`${activeAlerts} active alerts`}>{activeAlerts}</span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </div>

        <div className="sidenav__user">
          <span className="avatar-sm" aria-hidden="true">{initials(user.name)}</span>
          <span className="sidenav__who">
            <strong>{user.name}</strong>
            <span>{user.role}</span>
          </span>
          <button type="button" className="sidenav__logout" onClick={logout} aria-label="Log out" title="Log out">
            <Icon d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9" />
          </button>
        </div>
      </nav>

      <main className="content">
        <span key={`bar-${location.pathname}`} className="route-progress" aria-hidden="true" />
        <div key={location.pathname} className="page-enter">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export const ALERTS_CHANGED = "pms:alerts-changed";

/** Polls the number of active alerts so the menu shows a live count (NFR-2). */
function useActiveAlertCount(enabled) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    const load = () =>
      api
        .alerts("active")
        .then((list) => alive && setCount(list.length))
        .catch(() => {});
    load();
    const id = setInterval(() => asBackground(load), 15000);
    window.addEventListener(ALERTS_CHANGED, load); // refresh at once after an acknowledge
    return () => {
      alive = false;
      clearInterval(id);
      window.removeEventListener(ALERTS_CHANGED, load);
    };
  }, [enabled]);
  return count;
}
