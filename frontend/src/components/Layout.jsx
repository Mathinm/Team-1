import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { canOpen, menuFor } from "../config/roles.js";
import { api } from "../api/endpoints.js";
import { USE_MOCK } from "../api/client.js";

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const items = menuFor(user.role);
  const activeAlerts = useActiveAlertCount(canOpen(user.role, "/alerts"));

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
          ☰
        </button>
        <span className="topbar__brand">PMS</span>
        <span className="topbar__title">Perishables Management System</span>
        {USE_MOCK && <span className="tag topbar__demo" title="Using built-in demo data">Demo data</span>}
        <div className="topbar__user">
          <span className="topbar__name">{user.name}</span>
          <span className="tag tag--role">{user.role}</span>
          <button type="button" className="btn btn--ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      <nav className={`sidenav${open ? " sidenav--open" : ""}`} aria-label="Main">
        {items.map((m) => (
          <NavLink key={m.path} to={m.path} onClick={() => setOpen(false)}>
            {m.label}
            {m.path === "/alerts" && activeAlerts > 0 && (
              <span className="nav-count" aria-label={`${activeAlerts} active alerts`}>{activeAlerts}</span>
            )}
          </NavLink>
        ))}
      </nav>

      <main className="content">
        <Outlet />
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
    const id = setInterval(load, 15000);
    window.addEventListener(ALERTS_CHANGED, load); // refresh at once after an acknowledge
    return () => {
      alive = false;
      clearInterval(id);
      window.removeEventListener(ALERTS_CHANGED, load);
    };
  }, [enabled]);
  return count;
}
