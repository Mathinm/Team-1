import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { asBackground } from "../api/background.js";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { can } from "../config/roles.js";
import { USE_MOCK } from "../api/client.js";
import { Banner, Loading, PageHeader } from "../components/ui.jsx";
import TempChart from "../components/TempChart.jsx";
import { formatDateTime } from "../lib/dates.js";
import { ALERTS_CHANGED } from "../components/Layout.jsx";

const REFRESH_MS = 10000;
const HOUR_OPTIONS = [6, 24, 72, 168];

export default function RefrigerationPage() {
  const [units, setUnits] = useState(null);
  const [selected, setSelected] = useState("");
  const [hours, setHours] = useState(24);
  const [readings, setReadings] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const { user } = useAuth();
  const canEditLimits = can(user.role, "editFridgeLimits");
  const [limits, setLimits] = useState({ tempMin: "", tempMax: "", doorOpenLimitMinutes: "" });
  const [savingLimits, setSavingLimits] = useState(false);

  const loadUnits = useCallback(async () => {
    try {
      const list = await api.units();
      setUnits(list);
      setSelected((cur) => cur || list[0]?.unitId || "");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const loadReadings = useCallback(async () => {
    if (!selected) return;
    try {
      setReadings(await api.unitReadings(selected, hours));
    } catch (e) {
      setError(e.message);
    }
  }, [selected, hours]);

  useEffect(() => {
    loadUnits();
    const id = setInterval(() => asBackground(loadUnits), REFRESH_MS);
    return () => clearInterval(id);
  }, [loadUnits]);

  useEffect(() => {
    setReadings(null);
    loadReadings();
    const id = setInterval(() => asBackground(loadReadings), REFRESH_MS);
    return () => clearInterval(id);
  }, [loadReadings]);

  const unit = units?.find((u) => u.unitId === selected);

  useEffect(() => {
    if (!unit) return;
    setLimits({
      tempMin: String(unit.tempMin),
      tempMax: String(unit.tempMax),
      doorOpenLimitMinutes: String(unit.doorOpenLimitMinutes ?? 5),
    });
  }, [unit?.unitId, unit?.tempMin, unit?.tempMax, unit?.doorOpenLimitMinutes]);

  async function saveLimits(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    const tempMin = Number(limits.tempMin);
    const tempMax = Number(limits.tempMax);
    const doorOpenLimitMinutes = Number(limits.doorOpenLimitMinutes);
    if (limits.tempMin.trim() === "" || limits.tempMax.trim() === "" ||
        ![tempMin, tempMax].every(Number.isFinite) || tempMin < -60 || tempMin > 100 ||
        tempMax < -60 || tempMax > 100 || tempMin >= tempMax) {
      setError("Enter temperatures from -60 to 100 °C, with minimum lower than maximum.");
      return;
    }
    if (!Number.isInteger(doorOpenLimitMinutes) || doorOpenLimitMinutes < 1 || doorOpenLimitMinutes > 240) {
      setError("Door-open limit must be a whole number from 1 to 240 minutes.");
      return;
    }
    setSavingLimits(true);
    try {
      const updated = await api.updateUnitSettings(unit.unitId, { tempMin, tempMax, doorOpenLimitMinutes });
      setUnits((current) => current?.map((item) => item.unitId === updated.unitId ? updated : item) ?? current);
      setMessage(`Safety limits saved for ${unit.name}.${updated.inRange === false ? " The current temperature is outside the new range; an alert has been raised." : ""}`);
      window.dispatchEvent(new Event(ALERTS_CHANGED));
    } catch (e2) {
      setError(e2.message);
    } finally {
      setSavingLimits(false);
    }
  }

  async function simulate(body, text) {
    setError("");
    try {
      const res = await api.simulateReading(body);
      setMessage(`${text}${res.alertRaised ? " An alert was raised." : ""}`);
      window.dispatchEvent(new Event(ALERTS_CHANGED));
      loadUnits();
      loadReadings();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <section>
      <PageHeader
        title="Refrigeration"
        subtitle="Status, current temperature and history for each unit. Refreshes automatically."
        actions={<Link className="btn" to="/alerts">View alerts</Link>}
      />
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      {!units ? (
        <Loading />
      ) : (
        <>
          <div className="unit-grid refrigeration-units" aria-label="Refrigeration units">
            {units.map((u) => (
              <button
                key={u.unitId}
                type="button"
                className={`unit-card refrigeration-unit${u.unitId === selected ? " unit-card--selected" : ""} unit-card--${unitTone(u)}`}
                onClick={() => setSelected(u.unitId)}
                aria-pressed={u.unitId === selected}
              >
                <span className="unit-card__name">{u.name}</span>
                <span className="unit-card__temp">{u.currentTemp === null ? "–" : `${fmtTemp(u.currentTemp)} °C`}</span>
                <span className="muted small">Allowed {u.tempMin} to {u.tempMax} °C</span>
                <span className="unit-card__status">
                  <StatusPill unit={u} />
                </span>
                <span className="muted small">
                  {u.lastReadingAt ? `Last reading ${formatDateTime(u.lastReadingAt)}` : "No readings yet"}
                </span>
              </button>
            ))}
          </div>

          {unit && (
            <>
            <div className="card refrigeration-panel refrigeration-limits">
              <div className="card__head">
                <div>
                  <span className="refrigeration-eyebrow">Configuration</span>
                  <h2>{unit.name}: safety limits</h2>
                  <p className="muted small">Configured limits used by refrigeration monitoring.</p>
                </div>
                {!canEditLimits && <span className="badge badge--info">View only</span>}
              </div>
              <form className="form refrigeration-limits__form" onSubmit={saveLimits}>
                <div className="grid">
                  <label className="field">
                    <span>Minimum temperature (°C)</span>
                    <input type="number" min="-60" max="100" step="0.1" required value={limits.tempMin} disabled={!canEditLimits || savingLimits}
                      onChange={(e) => setLimits((v) => ({ ...v, tempMin: e.target.value }))} />
                  </label>
                  <label className="field">
                    <span>Maximum temperature (°C)</span>
                    <input type="number" min="-60" max="100" step="0.1" required value={limits.tempMax} disabled={!canEditLimits || savingLimits}
                      onChange={(e) => setLimits((v) => ({ ...v, tempMax: e.target.value }))} />
                  </label>
                  <label className="field">
                    <span>Door-open limit (minutes)</span>
                    <input type="number" min="1" max="240" step="1" required value={limits.doorOpenLimitMinutes}
                      disabled={!canEditLimits || savingLimits}
                      onChange={(e) => setLimits((v) => ({ ...v, doorOpenLimitMinutes: e.target.value }))} />
                  </label>
                </div>
                {canEditLimits && (
                  <div className="form__actions">
                    <button className="btn btn--primary" type="submit" disabled={savingLimits}>
                      {savingLimits ? "Saving…" : "Save safety limits"}
                    </button>
                  </div>
                )}
              </form>
            </div>

            <div className="card refrigeration-panel refrigeration-history">
              <div className="card__head">
                <div>
                  <span className="refrigeration-eyebrow">Sensor trends</span>
                  <h2>{unit.name}: temperature history</h2>
                  <p className="muted small">Shaded band = allowed range. Red dots = readings outside it.</p>
                </div>
                <div className="chips" role="group" aria-label="Period">
                  {HOUR_OPTIONS.map((h) => (
                    <button
                      key={h}
                      type="button"
                      className={`btn btn--small ${h === hours ? "btn--primary" : "btn--ghost"}`}
                      onClick={() => setHours(h)}
                    >
                      {h < 48 ? `${h} h` : `${h / 24} days`}
                    </button>
                  ))}
                </div>
              </div>
              {!readings ? (
                <Loading />
              ) : (
                <>
                  <TempChart readings={readings} tempMin={unit.tempMin} tempMax={unit.tempMax} />
                  <ChartStats readings={readings} unit={unit} />
                </>
              )}
            </div>
            </>
          )}

          {USE_MOCK && unit && (
            <div className="card demo-controls refrigeration-panel">
              <h2>Demo controls</h2>
              <p className="muted small">
                Demo data only. Simulates the sensor simulator sending readings for {unit.name}, so you can show alerts being raised.
              </p>
              <div className="chips">
                <button className="btn btn--small" onClick={() => simulate({ unitId: unit.unitId, type: "temperature", value: unit.tempMax + 3 }, `Sent ${unit.tempMax + 3} °C.`)}>
                  Too warm
                </button>
                <button className="btn btn--small" onClick={() => simulate({ unitId: unit.unitId, type: "temperature", value: (unit.tempMin + unit.tempMax) / 2 }, "Sent a normal reading.")}>
                  Normal reading
                </button>
                <button className="btn btn--small" onClick={() => simulate({ unitId: unit.unitId, type: "door", value: "open" }, "Door left open.")}>
                  Door left open
                </button>
                <button className="btn btn--small" onClick={() => simulate({ unitId: unit.unitId, type: "door", value: "closed" }, "Door closed.")}>
                  Close door
                </button>
                <button className="btn btn--small" onClick={() => simulate({ unitId: unit.unitId, type: "status", value: "failed" }, "Unit failure sent.")}>
                  Unit fails
                </button>
                <button className="btn btn--small" onClick={() => simulate({ unitId: unit.unitId, type: "status", value: "ok" }, "Unit back to normal.")}>
                  Unit OK
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** 4 -> "4", 4.6666 -> "4.7" (sensors may send many decimals). */
function fmtTemp(v) {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function unitTone(u) {
  if (u.status === "failed") return "danger";
  if (u.doorOpen || u.inRange === false) return "warn";
  return "ok";
}

function StatusPill({ unit }) {
  return (
    <>
      {unit.status === "failed" ? (
        <span className="badge badge--expired">■ Failed</span>
      ) : (
        <span className="badge badge--fresh">● Working</span>
      )}
      {unit.status !== "failed" && unit.inRange === false && <span className="badge badge--near">▲ Out of range</span>}
      {unit.doorOpen && <span className="badge badge--near">▲ Door open</span>}
    </>
  );
}

function ChartStats({ readings, unit }) {
  if (!readings.length) return null;
  const values = readings.map((r) => r.value);
  const out = values.filter((v) => v < unit.tempMin || v > unit.tempMax).length;
  const avg = values.reduce((a, v) => a + v, 0) / values.length;
  return (
    <div className="report-summary chart-stats">
      <div><span className="muted small">Min</span><strong>{fmtTemp(Math.min(...values))} °C</strong></div>
      <div><span className="muted small">Average</span><strong>{avg.toFixed(1)} °C</strong></div>
      <div><span className="muted small">Max</span><strong>{fmtTemp(Math.max(...values))} °C</strong></div>
      <div><span className="muted small">Out of range</span><strong>{out} of {values.length}</strong></div>
    </div>
  );
}
