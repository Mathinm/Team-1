import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { asBackground } from "../api/background.js";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { canOpen } from "../config/roles.js";
import { Icon } from "../components/Layout.jsx";
import ProductThumb from "../components/ProductThumb.jsx";
import { Banner, EmptyState, Loading, SeverityTag, money } from "../components/ui.jsx";
import { describeDaysToExpiry, formatDateTime } from "../lib/dates.js";

const REFRESH_MS = 15000; // live data refreshes without a manual reload (UIN-6)
const SLIDE_MS = 6000;
const SLIDES = [
  { src: "/img/login.jpg", label: "Store floor" },
  { src: "/img/hero-fruits.jpg", label: "Fruits aisle" },
  { src: "/img/hero-veg.jpg", label: "Vegetables aisle" },
];
const LEAVES = [8, 22, 41, 57, 73, 88];

const TILE_ICONS = {
  sales: "M3 3h2l2.4 12.4a2 2 0 0 0 2 1.6h8.2a2 2 0 0 0 2-1.6L21 7H6 M9 21h.01 M18 21h.01",
  stock: "M21 8l-9-5-9 5 9 5 9-5z M3 8v8l9 5 9-5V8",
  low: "M3 3v18h18 M7 9l4 4 4-4 4 4",
  expiry: "M12 7v5l3 3 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  alerts: "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9 M10.3 21a1.94 1.94 0 0 0 3.4 0",
  waste: "M3 6h18 M8 6V4h8v2 M6 6l1 14h10l1-14",
};

export default function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const now = useClock();
  const [slide, setSlide] = useState(0);

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
    const id = setInterval(() => asBackground(load), REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setSlide((s) => (s + 1) % SLIDES.length), SLIDE_MS);
    return () => clearInterval(id);
  }, []);

  const can = (path) => canOpen(user.role, path);
  const link = (path, text) => (can(path) ? <Link to={path}>{text}</Link> : null);

  const firstName = (user.name || "").split(" ")[0];
  const hour = Number(now.toLocaleString("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }));
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const today = now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata" });
  const clock = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Kolkata" });

  const units = data?.units ?? [];
  const working = units.filter((u) => u.status !== "failed").length;
  const nextExpiry = data ? [...data.expiringSoon].sort((a, b) => a.daysToExpiry - b.daysToExpiry)[0] : null;
  const needYou = data ? data.lowStock.length + data.expiringSoon.length + data.activeAlerts.count : 0;

  return (
    <section>
      <header className="dash-hero">
        {SLIDES.map((s, i) => (
          <span
            key={s.src}
            className={`dash-hero__slide${i === slide ? " dash-hero__slide--on" : ""}`}
            style={{ backgroundImage: `url(${s.src})` }}
            aria-hidden="true"
          />
        ))}
        <span className="dash-hero__shade" aria-hidden="true" />
        {LEAVES.map((left, i) => (
          <svg key={left} className="dash-hero__leaf" viewBox="0 0 24 24" aria-hidden="true"
            style={{ left: `${left}%`, animationDelay: `${i * 1.5}s`, animationDuration: `${8 + (i % 3) * 2}s`, width: 14 + (i % 3) * 5 }}>
            <path d="M11 20A7 7 0 0 1 4 13c0-5 4-9 16-9 0 12-4 16-9 16z" />
          </svg>
        ))}

        <div className="dash-hero__body">
          <div className="dash-hero__top">
            <div>
              <span className="dash-hero__live"><span className="pulse-dot" aria-hidden="true" />Live · {clock} IST</span>
              <h1>{greeting}{firstName ? `, ${firstName}` : ""}</h1>
              <p>
                {today} ·{" "}
                {!data ? "loading your store…" : needYou ? `${needYou} thing${needYou === 1 ? "" : "s"} need${needYou === 1 ? "s" : ""} you today.` : "all clear today."}
              </p>
            </div>
            <div className="dash-hero__actions">
              <button type="button" className="btn btn--glass" onClick={load}>Refresh</button>
              {can("/stock") && <Link to="/stock" className="btn btn--primary btn--shine">+ Receive batch</Link>}
            </div>
          </div>

          <div className="dash-hero__bottom">
            <div className="dash-hero__stats">
              <div className="glass-stat">
                <span>Next expiry</span>
                <strong>{nextExpiry ? `${nextExpiry.productName} · ${describeDaysToExpiry(nextExpiry.daysToExpiry)}` : "Nothing in 2 days"}</strong>
              </div>
              <div className={`glass-stat${units.length && working < units.length ? " glass-stat--bad" : ""}`}>
                <span>Fridges</span>
                <strong>{units.length ? `${working} of ${units.length} working` : "No units"}</strong>
              </div>
              <div className="glass-stat">
                <span>Updated</span>
                <strong>{updatedAt ? updatedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "…"}</strong>
              </div>
            </div>
            <div className="dash-hero__dots">
              <span>{SLIDES[slide].label}</span>
              {SLIDES.map((s, i) => (
                <button key={s.src} type="button" aria-label={`Show ${s.label}`} aria-pressed={i === slide}
                  className={`dash-hero__dot${i === slide ? " dash-hero__dot--on" : ""}`} onClick={() => setSlide(i)} />
              ))}
            </div>
          </div>
        </div>
      </header>

      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      {!data ? (
        <Loading />
      ) : (
        <>
          <div className="tiles">
            <Tile icon="sales" label="Sales today" value={data.salesToday.amount} isMoney note={`${data.salesToday.count} sale${data.salesToday.count === 1 ? "" : "s"}`} />
            <Tile icon="stock" label="Stock value (cost)" value={data.stockValue} isMoney />
            <Tile icon="low" label="Low-stock items" value={data.lowStock.length} tone={data.lowStock.length ? "warn" : "ok"} />
            <Tile icon="expiry" label="Expiring in 2 days" value={data.expiringSoon.length} tone={data.expiringSoon.length ? "warn" : "ok"} note="incl. already expired" />
            <Tile icon="alerts" label="Active alerts" value={data.activeAlerts.count}
              tone={data.activeAlerts.critical ? "danger" : data.activeAlerts.count ? "warn" : "ok"}
              note={data.activeAlerts.critical ? `${data.activeAlerts.critical} critical` : undefined} />
            <Tile icon="waste" label="Waste, last 7 days" value={data.wasteLast7Days.value} isMoney
              note={`${data.wasteLast7Days.removals} removal${data.wasteLast7Days.removals === 1 ? "" : "s"}`}
              tone={data.wasteLast7Days.value ? "warn" : "ok"} />
          </div>

          <div className="dash-grid">
            <div className="card dash-grid__main">
              <div className="card__head">
                <h2>Act now</h2>
                <span className="muted small">{data.expiringSoon.length + data.lowStock.length} items · soonest first</span>
              </div>
              {data.expiringSoon.length + data.lowStock.length === 0 ? (
                <EmptyState>All clear. Nothing is expiring or running low.</EmptyState>
              ) : (
                <ul className="act-list">
                  {[...data.expiringSoon].sort((a, b) => a.daysToExpiry - b.daysToExpiry).map((b) => (
                    <li key={`b${b.batchId}`}>
                      <ProductThumb name={b.productName} />
                      <span className="act-list__text">
                        <strong>{b.productName}</strong> <span className="muted small">· B-{b.batchId}</span>
                        <span className="muted small act-list__detail">{b.quantity} {b.unit} · {describeDaysToExpiry(b.daysToExpiry)}</span>
                      </span>
                      <span className={`pill ${b.daysToExpiry < 0 ? "pill--bad" : b.daysToExpiry === 0 ? "pill--bad" : "pill--warn"}`}>
                        {b.daysToExpiry < 0 ? "Expired" : b.daysToExpiry === 0 ? "Today" : `${b.daysToExpiry} day${b.daysToExpiry === 1 ? "" : "s"}`}
                      </span>
                      {can(b.daysToExpiry < 0 ? "/removals" : "/stock") && (
                        <Link className="btn btn--small" to={b.daysToExpiry < 0 ? "/removals" : "/stock"}>
                          {b.daysToExpiry < 0 ? "Remove" : "View batch"}
                        </Link>
                      )}
                    </li>
                  ))}
                  {data.lowStock.map((p) => (
                    <li key={`p${p.productId}`}>
                      <ProductThumb name={p.name} />
                      <span className="act-list__text">
                        <strong>{p.name}</strong>
                        <span className="muted small act-list__detail">{p.stock} {p.unit} left · minimum is {p.threshold} {p.unit}</span>
                      </span>
                      <span className={`pill ${p.stock <= 0 ? "pill--bad" : "pill--info"}`}>{p.stock <= 0 ? "Out of stock" : "Low stock"}</span>
                      {can("/stock") && <Link className="btn btn--small" to="/stock">Restock</Link>}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card dash-grid__side">
              <div className="card__head">
                <h2>Fridges</h2>
                {link("/refrigeration", "Open")}
              </div>
              {units.length === 0 ? (
                <EmptyState>No fridge units yet.</EmptyState>
              ) : (
                <ul className="unit-mini">
                  {units.map((u) => (
                    <li key={u.unitId} className={u.status === "failed" ? "unit-mini--bad" : ""}>
                      <span className={`pulse-dot${u.status === "failed" ? " pulse-dot--bad" : ""}`} aria-hidden="true" />
                      <strong>{u.name}</strong>
                      <span className={`pill ${u.status === "failed" ? "pill--solid-bad" : "pill--ok"}`}>
                        {u.status === "failed" ? "Failed" : "Working"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card dash-grid__wide">
              <div className="card__head">
                <h2>Latest active alerts <span className="muted small">(critical first)</span></h2>
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
                      <span className="muted small list__time">{formatDateTime(a.triggeredAt ?? a.createdAt)}</span>
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

function Tile({ icon, label, value, note, tone = "neutral", isMoney = false }) {
  const shown = useCountUp(Number(value) || 0);
  const final = shown === (Number(value) || 0);
  return (
    <div className={`tile tile--${tone}`}>
      <span className="tile__top">
        <span className="tile__label">{label}</span>
        <span className="tile__icon"><Icon d={TILE_ICONS[icon]} size={16} /></span>
      </span>
      <span className="tile__value">{isMoney ? money(final ? value : Math.round(shown)) : Math.round(shown)}</span>
      {note && <span className="tile__note">{note}</span>}
    </div>
  );
}

/** Ticks once a second for the live clock. */
function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/** Animates a number from its last value to the new one (look only). */
function useCountUp(target, ms = 900) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      from.current = target;
      setShown(target);
      return undefined;
    }
    const start = performance.now();
    const begin = from.current;
    let raf;
    const step = (t) => {
      const p = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - p, 3);
      const v = p < 1 ? begin + (target - begin) * e : target;
      setShown(v);
      if (p < 1) raf = requestAnimationFrame(step);
      else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return shown;
}
