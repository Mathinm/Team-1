import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { menuFor } from "../config/roles.js";
import { USE_MOCK } from "../api/client.js";

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const items = menuFor(user.role);

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
          </NavLink>
        ))}
      </nav>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
