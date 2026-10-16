import { useState } from "react";
import { api } from "../api/endpoints.js";
import { Banner, Field, Loading, PageHeader } from "../components/ui.jsx";
import { REPORT_TYPES } from "../config/reports.js";
import { addDays, toISODate } from "../lib/dates.js";
import { exportReportCsv, exportReportPdf, formatCell } from "../lib/reportExport.js";

export default function ReportsPage() {
  const today = new Date();
  const [form, setForm] = useState({
    type: "wastage",
    from: toISODate(addDays(today, -6)),
    to: toISODate(today),
  });
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState("");
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const meta = REPORT_TYPES.find((t) => t.type === form.type);
  const rangeError = form.from && form.to && form.from > form.to ? "From date must be on or before To date" : "";

  function quickRange(days) {
    setForm((f) => ({ ...f, from: toISODate(addDays(new Date(), -(days - 1))), to: toISODate(new Date()) }));
  }

  async function run(e) {
    e?.preventDefault();
    if (rangeError || !form.from || !form.to) return;
    setLoading(true);
    setError("");
    setReport(null);
    try {
      setReport(await api.report(form.type, form.from, form.to));
    } catch (ex) {
      setError(ex.message);
    } finally {
      setLoading(false);
    }
  }

  async function exportAs(kind) {
    setExporting(kind);
    setError("");
    try {
      if (kind === "csv") exportReportCsv(report);
      else await exportReportPdf(report);
    } catch (ex) {
      setError(`Export failed: ${ex.message}`);
    } finally {
      setExporting("");
    }
  }

  const empty = report && report.rows.length === 0;

  return (
    <section>
      <PageHeader title="Reports" subtitle="Choose a report and date range, then export to PDF or CSV" />
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      <form className="card form" onSubmit={run} noValidate>
        <div className="grid">
          <Field label="Report" hint={meta?.help} id="rep-type">
            <select id="rep-type" value={form.type} onChange={set("type")}>
              {REPORT_TYPES.map((t) => <option key={t.type} value={t.type}>{t.title}</option>)}
            </select>
          </Field>
          <Field label="From" id="rep-from">
            <input id="rep-from" type="date" value={form.from} max={form.to} onChange={set("from")} />
          </Field>
          <Field label="To" error={rangeError} id="rep-to">
            <input id="rep-to" type="date" value={form.to} min={form.from} onChange={set("to")} />
          </Field>
        </div>
        <div className="form__actions form__actions--split">
          <div className="chips">
            <button type="button" className="btn btn--small btn--ghost" onClick={() => quickRange(1)}>Today</button>
            <button type="button" className="btn btn--small btn--ghost" onClick={() => quickRange(7)}>Last 7 days</button>
            <button type="button" className="btn btn--small btn--ghost" onClick={() => quickRange(30)}>Last 30 days</button>
          </div>
          <button type="submit" className="btn btn--primary" disabled={loading || Boolean(rangeError)}>
            {loading ? "Loading…" : "Show report"}
          </button>
        </div>
      </form>

      {loading && <Loading />}

      {report && (
        <div className="card">
          <div className="card__head">
            <div>
              <h2>{report.title}</h2>
              <p className="muted small">{report.from} to {report.to}</p>
            </div>
            <div className="page-header__actions">
              <button className="btn" onClick={() => exportAs("csv")} disabled={empty || Boolean(exporting)}>
                {exporting === "csv" ? "Exporting…" : "Export CSV"}
              </button>
              <button className="btn" onClick={() => exportAs("pdf")} disabled={empty || Boolean(exporting)}>
                {exporting === "pdf" ? "Exporting…" : "Export PDF"}
              </button>
            </div>
          </div>

          {empty ? (
            <p className="empty">No data for this period</p>
          ) : (
            <>
              {report.summary?.length > 0 && (
                <div className="report-summary">
                  {report.summary.map((s) => (
                    <div key={s.label}>
                      <span className="muted small">{s.label}</span>
                      <strong>{s.value}</strong>
                    </div>
                  ))}
                </div>
              )}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {report.columns.map((c) => (
                        <th key={c.key} className={c.numeric ? "num" : ""}>{c.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.rows.map((r, i) => (
                      <tr key={i}>
                        {report.columns.map((c) => (
                          <td key={c.key} data-label={c.label || " "} className={c.numeric ? "num" : ""}>
                            {formatCell(r[c.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
