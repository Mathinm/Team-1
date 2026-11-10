import { useCallback, useEffect, useState } from "react";
import { asBackground } from "../api/background.js";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { can } from "../config/roles.js";
import { Banner, EmptyState, Loading, SeverityTag } from "../components/ui.jsx";
import { formatDateTime } from "../lib/dates.js";
import { ALERTS_CHANGED } from "../components/Layout.jsx";

const REFRESH_MS = 10000; // new alerts appear without a reload (NFR-2: within 60 s)

export const ALERT_TYPES = {
  low_stock: "Low stock",
  projected_low_stock: "Projected low stock",
  expiry_soon: "Expiring soon",
  expired: "Expiry",
  removal: "Removal",
  unit_failure: "Fridge failure",
  door_open: "Door open",
  temperature: "Temperature",
  power: "Power",
};

const TABS = [
  { key: "active", label: "Active" },
  { key: "acknowledged", label: "Acknowledged" },
  { key: "resolved", label: "Resolved" },
  { key: "all", label: "All" },
];

export default function AlertsPage() {
  const { user } = useAuth();
  const canAck = can(user.role, "acknowledgeAlerts");
  const [tab, setTab] = useState("active");
  const [type, setType] = useState("");
  const [alerts, setAlerts] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      setAlerts(await api.alerts(tab));
    } catch (e) {
      setError(e.message);
    }
  }, [tab]);

  useEffect(() => {
    setAlerts(null);
    load();
    const id = setInterval(() => asBackground(load), REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  async function acknowledge(a) {
    setBusyId(a.alertId);
    setError("");
    try {
      await api.acknowledgeAlert(a.alertId);
      window.dispatchEvent(new Event(ALERTS_CHANGED));
      setMessage(`Acknowledged: ${a.message}`);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  const visible = (alerts ?? []).filter((a) => !type || a.type === type);
  const typesPresent = [...new Set((alerts ?? []).map((a) => a.type))];

  return (
    <section>
      <header className="monitor-page-hero monitor-page-hero--alerts">
        <img src="/img/login.jpg" alt="" aria-hidden="true" />
        <span className="monitor-page-hero__shade" aria-hidden="true" />
        <div className="monitor-page-hero__body">
          <span className="monitor-page-hero__crumb">Monitoring / Safety centre</span>
          <h1>Alerts</h1>
          <p>Low stock, expiry, fridge, door, temperature and power alerts. Refreshes automatically.</p>
        </div>
      </header>
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>
      {!canAck && <Banner kind="info">Only a Manager or Admin can acknowledge alerts.</Banner>}

      <div className="alerts-toolbar card">
        <div className="tabs alerts-tabs" role="tablist" aria-label="Alert status">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={`tab${tab === t.key ? " tab--active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <label className="alerts-filter"><span className="alerts-filter__label">Filter by type</span><select aria-label="Alert type" value={type} onChange={(e) => setType(e.target.value)} className="select">
          <option value="">All types</option>
          {typesPresent.map((t) => <option key={t} value={t}>{ALERT_TYPES[t] ?? t}</option>)}
        </select></label>
      </div>

      {!alerts ? (
        <Loading />
      ) : visible.length === 0 ? (
        <EmptyState>{tab === "active" ? "No active alerts. All clear." : "No alerts to show."}</EmptyState>
      ) : (
        <ul className="alert-list alerts-list">
          {visible.map((a) => (
            <li key={a.alertId} className={`alert-item alerts-card alert-item--${a.severity}${a.status !== "active" ? " alert-item--done" : ""}`}>
              <div className="alert-item__main alerts-card__main">
                <div className="alert-item__tags">
                  <SeverityTag severity={a.severity} />
                  <span className="tag">{ALERT_TYPES[a.type] ?? a.type}</span>
                </div>
                <p className="alert-item__msg alerts-card__message">{a.message}</p>
                <p className="muted small">
                  Raised {formatDateTime(a.createdAt)}
                  {a.acknowledgedAt && ` · acknowledged by ${a.acknowledgedBy} at ${formatDateTime(a.acknowledgedAt)}`}
                  {a.status === "resolved" && ` · resolved ${formatDateTime(a.resolvedAt)}${a.resolution ? ` (${a.resolution})` : ""}`}
                </p>
              </div>
              {a.status === "active" && canAck && (
                <button className="btn btn--primary btn--small" disabled={busyId === a.alertId} onClick={() => acknowledge(a)}>
                  {busyId === a.alertId ? "Saving…" : "Acknowledge"}
                </button>
              )}
              {a.status === "acknowledged" && <span className="badge badge--fresh">✓ Acknowledged</span>}
              {a.status === "resolved" && <span className="badge badge--fresh">✓ Resolved</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
