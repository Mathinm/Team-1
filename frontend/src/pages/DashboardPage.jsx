import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { canOpen } from "../config/roles.js";
import { Banner, EmptyState, ExpiryBadge, Loading, PageHeader, money } from "../components/ui.jsx";
import { describeDaysToExpiry, formatDateTime } from "../lib/dates.js";

const REFRESH_MS = 15000; // live data refreshes without a manual reload (UIN-6)

export default function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await api.dashboard());
      setUpdatedAt(new Date());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const link = (path, text) => (canOpen(user.role, path) ? <Link to={path}>{text}</Link> : null);

  return (
    <section>
      <PageHeader
        title="Dashboard"
        subtitle={updatedAt ? `Updated ${updatedAt.toLocaleTimeString("en-IN")} · refreshes automatically` : "Store overview"}
        actions={<button className="btn" onClick={load}>Refresh</button>}
      />
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      {!data ? (
        <Loading />
      ) : (
        <>
          <div className="tiles">
            <Tile label="Sales today" value={money(data.salesToday.amount)} note={`${data.salesToday.count} sale${data.salesToday.count === 1 ? "" : "s"}`} />
            <Tile label="Stock value (cost)" value={money(data.stockValue)} />
            <Tile
              label="Low-stock items"
              value={data.lowStock.length}
              tone={data.lowStock.length ? "warn" : "ok"}
            />
            <Tile
              label="Expiring in 2 days"
              value={data.expiringSoon.length}
              tone={data.expiringSoon.length ? "warn" : "ok"}
              note="incl. already expired"
            />
            <Tile
              label="Active alerts"
              value={data.activeAlerts.count}
              tone={data.activeAlerts.critical ? "danger" : data.activeAlerts.count ? "warn" : "ok"}
              note={data.activeAlerts.critical ? `${data.activeAlerts.critical} critical` : undefined}
            />
            <Tile
              label="Waste, last 7 days"
              value={money(data.wasteLast7Days.value)}
              note={`${data.wasteLast7Days.removals} removal${data.wasteLast7Days.removals === 1 ? "" : "s"}`}
              tone={data.wasteLast7Days.value ? "warn" : "ok"}
            />
          </div>

          <div className="two-col">
            <div className="card">
              <div className="card__head">
                <h2>Low stock</h2>
                {link("/stock", "Open stock")}
              </div>
              {data.lowStock.length === 0 ? (
                <EmptyState>Everything is above its threshold.</EmptyState>
              ) : (
                <ul className="list">
                  {data.lowStock.map((p) => (
                    <li key={p.productId}>
                      <span>
                        <strong>{p.name}</strong>
                        <span className="muted small"> · threshold {p.threshold} {p.unit}</span>
                      </span>
                      <span className={`badge ${p.stock <= 0 ? "badge--expired" : "badge--near"}`}>
                        {p.stock} {p.unit} left
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card">
              <div className="card__head">
                <h2>Expiring soon</h2>
                {link("/stock", "Open stock")}
              </div>
              {data.expiringSoon.length === 0 ? (
                <EmptyState>Nothing expires in the next 2 days.</EmptyState>
              ) : (
                <ul className="list">
                  {data.expiringSoon.map((b) => (
                    <li key={b.batchId}>
                      <span>
                        <strong>{b.productName}</strong>
                        <span className="muted small"> · B-{b.batchId} · {b.quantity} {b.unit} · {describeDaysToExpiry(b.daysToExpiry)}</span>
                      </span>
                      <ExpiryBadge daysToExpiry={b.daysToExpiry} />
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card two-col__wide">
              <div className="card__head">
                <h2>Latest active alerts</h2>
                {link("/alerts", "All alerts")}
              </div>
              {data.activeAlerts.latest.length === 0 ? (
                <EmptyState>No active alerts.</EmptyState>
              ) : (
                <ul className="list">
                  {data.activeAlerts.latest.map((a) => (
                    <li key={a.alertId}>
                      <span>
                        <SeverityTag severity={a.severity} /> {a.message}
                      </span>
                      <span className="muted small">{formatDateTime(a.createdAt)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Tile({ label, value, note, tone = "neutral" }) {
  return (
    <div className={`tile tile--${tone}`}>
      <span className="tile__label">{label}</span>
      <span className="tile__value">{value}</span>
      {note && <span className="tile__note">{note}</span>}
    </div>
  );
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
