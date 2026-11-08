import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { USER_ROLES } from "../config/roles.js";
import { Banner, EmptyState, Field, Loading, PageHeader } from "../components/ui.jsx";
import "./products-login.css";

/** Users (SEC-4, SEC-3 unlock). Admin only: add accounts, assign roles, deactivate people who
 *  have left (accounts are never deleted, so their records keep their author) and unlock. */
export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [editing, setEditing] = useState(null); // null | "new" | user

  const load = useCallback(async () => {
    try {
      setUsers(await api.listUsers());
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    if (!users) return [];
    const q = query.trim().toLowerCase();
    return users
      .filter((u) => showInactive || u.active)
      .filter((u) => !q || [u.userId, u.name, u.email, u.role].some((v) => v.toLowerCase().includes(q)))
      .sort((a, b) => a.role.localeCompare(b.role) || a.name.localeCompare(b.name));
  }, [users, query, showInactive]);

  async function run(action, done) {
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(done);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  const toggleActive = (u) =>
    run(
      () => (u.active ? api.deactivateUser(u.userId) : api.activateUser(u.userId)),
      `${u.name} ${u.active ? "deactivated: they can no longer log in" : "re-activated"}.`,
    );
  const unlock = (u) => run(() => api.unlockUser(u.userId), `${u.name} unlocked.`);

  function saved(u, isNew) {
    setEditing(null);
    setMessage(`${u.name} ${isNew ? "added" : "updated"}.`);
    load();
  }

  return (
    <section className="products-v2 users-v2">
      <PageHeader
        title="Users"
        subtitle="Add staff accounts, assign roles and deactivate people who have left"
        actions={
          <button className="btn btn--primary" onClick={() => setEditing("new")}>
            + Add user
          </button>
        }
      />
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      {editing && (
        <UserForm
          user={editing === "new" ? null : editing}
          me={me}
          onCancel={() => setEditing(null)}
          onSaved={saved}
        />
      )}

      <div className="toolbar">
        <input
          type="search"
          placeholder="Search name, user ID, email or role"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search users"
        />
        <label className="check">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          Show deactivated
        </label>
      </div>

      {!users ? (
        <Loading />
      ) : visible.length === 0 ? (
        <EmptyState>No users match.</EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {visible.map((u) => {
                const self = u.userId === me.userId;
                return (
                  <tr key={u.userId} className={u.active ? "" : "row--inactive"}>
                    <td data-label="User">
                      <div className="pcell">
                        <span className="avatar" aria-hidden="true">{initials(u.name)}</span>
                        <div>
                          <strong>{u.name}</strong>
                          <div className="muted small">{u.userId}{self ? " (you)" : ""}</div>
                        </div>
                      </div>
                    </td>
                    <td data-label="Email" className="users-v2__email">{u.email}</td>
                    <td data-label="Role"><span className="tag tag--role">{u.role}</span></td>
                    <td data-label="Status">
                      {!u.active ? (
                        <span className="tag">Deactivated</span>
                      ) : u.locked ? (
                        <span className="badge badge--expired"><span aria-hidden="true">■</span> Locked</span>
                      ) : (
                        <span className="badge badge--fresh"><span aria-hidden="true">●</span> Active</span>
                      )}
                    </td>
                    <td className="actions">
                      <button className="btn btn--small" onClick={() => setEditing(u)}>Edit</button>
                      {u.locked && u.active && (
                        <button className="btn btn--small" onClick={() => unlock(u)}>Unlock</button>
                      )}
                      {!self && (
                        <button className="btn btn--small btn--ghost" onClick={() => toggleActive(u)}>
                          {u.active ? "Deactivate" : "Activate"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function initials(name = "") {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
}

const USER_ID = /^[A-Za-z0-9_.-]{3,50}$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Add or edit a user. New users get a first password that they should change. */
function UserForm({ user, me, onCancel, onSaved }) {
  const isNew = !user;
  const [form, setForm] = useState({
    userId: user?.userId ?? "",
    name: user?.name ?? "",
    email: user?.email ?? "",
    role: user?.role ?? "Cashier",
    password: "",
  });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function validate() {
    const e = {};
    if (isNew && !USER_ID.test(form.userId)) e.userId = "3–50 letters, numbers, _ . or -";
    if (!form.name.trim()) e.name = "Enter a name";
    if (!EMAIL.test(form.email.trim())) e.email = "Enter a valid email";
    if (isNew && form.password.length < 8) e.password = "At least 8 characters";
    return e;
  }

  async function submit(ev) {
    ev.preventDefault();
    const errs = validate();
    setErrors(errs);
    setError("");
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      let saved;
      if (isNew) {
        saved = await api.createUser({ ...form, name: form.name.trim(), email: form.email.trim() });
      } else {
        const body = { name: form.name.trim(), email: form.email.trim() };
        if (form.role !== user.role) body.role = form.role;
        saved = await api.updateUser(user.userId, body);
      }
      onSaved(saved, isNew);
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  const self = !isNew && user.userId === me.userId;
  return (
    <form className="card form pform" onSubmit={submit} noValidate>
      <h2>{isNew ? "Add user" : `Edit ${user.name}`}</h2>
      <Banner kind="error">{error}</Banner>
      <div className="grid">
        <Field label="User ID" error={errors.userId} hint={isNew ? "Used to log in, e.g. cashier2" : "Can't be changed"} id="u-id">
          <input id="u-id" value={form.userId} onChange={set("userId")} disabled={!isNew} autoComplete="off" />
        </Field>
        <Field label="Full name" error={errors.name} id="u-name">
          <input id="u-name" value={form.name} onChange={set("name")} autoComplete="off" />
        </Field>
        <Field label="Email" error={errors.email} id="u-email">
          <input id="u-email" type="email" value={form.email} onChange={set("email")} autoComplete="off" />
        </Field>
        <Field
          label="Role"
          error={errors.role}
          hint={self ? "You can't remove your own Admin role" : undefined}
          id="u-role"
        >
          <select id="u-role" value={form.role} onChange={set("role")} disabled={self}>
            {USER_ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Field>
        {isNew && (
          <Field label="First password" error={errors.password} hint="At least 8 characters. Ask them to change it." id="u-pw">
            <input id="u-pw" type="password" value={form.password} onChange={set("password")} autoComplete="new-password" />
          </Field>
        )}
      </div>
      <div className="form__actions">
        <button type="button" className="btn btn--ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? "Saving…" : isNew ? "Add user" : "Save changes"}
        </button>
      </div>
    </form>
  );
}
