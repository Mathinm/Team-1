import { useState } from "react";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { can } from "../config/roles.js";
import { Banner, Field, PageHeader } from "../components/ui.jsx";
import {
  BatchPicker, ChoiceChips, ProductPicker, SessionLog, Step, VarianceChip, clock, useBatchPicker,
} from "../components/StockOps.jsx";
import { COUNT_REASON_HINTS, COUNT_REASON_MAX, countVariance, validateStockCount } from "../lib/validation.js";

const EMPTY = { counted: "", reason: "" };

/** FR-9: physical stock count. Shows the variance from the system quantity and records the adjustment. */
export default function StockCountPage() {
  const { user } = useAuth();
  const allowed = can(user.role, "recordStockCount");
  const pick = useBatchPicker();
  const { product, batch } = pick;
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);

  const unit = batch?.unit ?? product?.unit ?? "";
  const hasCount = form.counted !== "" && Number.isFinite(Number(form.counted)) && Number(form.counted) >= 0;
  const variance = batch && hasCount ? countVariance(batch.quantity, form.counted) : null;

  function chooseProduct(id) {
    pick.setProductId(id);
    setForm(EMPTY);
    setErrors({});
  }

  async function submit(e) {
    e.preventDefault();
    const errs = validateStockCount({
      batchId: pick.batchId, counted: form.counted, reason: form.reason, unit: batch?.unit ?? product?.unit,
    });
    setErrors(errs);
    setError("");
    setMessage("");
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const res = await api.recordStockCount({
        batchId: Number(pick.batchId),
        countedQuantity: Number(form.counted),
        reason: form.reason.trim(),
      });
      const sign = res.variance > 0 ? "+" : "";
      const text = `B-${res.batchId} (${product?.name}) counted: system ${res.systemQuantity} ${unit}, counted ${res.countedQuantity} ${unit}, variance ${sign}${res.variance} ${unit}.`;
      setMessage(text);
      setLog((l) => [{ id: res.stockCountId, time: clock(res.recordedAt), text }, ...l]);
      setForm(EMPTY);
      pick.refresh();
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ops-v2">
      <PageHeader
        title="Stock count"
        subtitle="Count what is on the shelf, see the difference from the system, and record the adjustment with a reason."
      />
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => { setError(""); pick.setError(""); }}>{error || pick.error}</Banner>

      {!allowed ? (
        <Banner kind="error">Your role ({user.role}) cannot record stock counts.</Banner>
      ) : (
        <>
          <Step n="1" title="Choose the product">
            <ProductPicker
              id="sc-product" products={pick.products} productId={pick.productId}
              onChange={chooseProduct} product={product}
            />
          </Step>

          <Step n="2" title="Choose the batch you counted" hint="Count one batch at a time.">
            <BatchPicker
              batches={pick.batches} unit={product?.unit} selectedId={pick.batchId}
              onSelect={pick.setBatchId} error={errors.batchId}
            />
          </Step>

          {batch && (
            <Step n="3" title="Enter your count">
              <form className="opanel" onSubmit={submit} noValidate>
                <div className="count-compare">
                  <div className="count-compare__cell">
                    <span className="muted small">System says</span>
                    <strong>{batch.quantity} <small>{unit}</small></strong>
                  </div>
                  <div className="count-compare__cell count-compare__cell--input">
                    <Field label={`You counted (${unit})`} error={errors.counted} id="sc-counted">
                      <input
                        id="sc-counted" type="number" inputMode="decimal" min="0"
                        step={unit === "piece" ? "1" : "any"} value={form.counted}
                        onChange={(e) => setForm((f) => ({ ...f, counted: e.target.value }))}
                        autoFocus
                      />
                    </Field>
                  </div>
                  <div className="count-compare__cell" aria-live="polite">
                    <span className="muted small">Variance</span>
                    {variance === null ? <span className="muted">Enter a count</span> : <VarianceChip variance={variance} unit={unit} />}
                  </div>
                </div>

                {hasCount && Number(form.counted) === 0 && batch.quantity > 0 && (
                  <Banner kind="warn">Counting 0 empties this batch and removes it from the stock list.</Banner>
                )}

                <Field
                  label="Reason" error={errors.reason} id="sc-reason"
                  hint="Saved with your name and the time. Pick a suggestion or type your own."
                >
                  <input
                    id="sc-reason" maxLength={COUNT_REASON_MAX} value={form.reason}
                    onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
                  />
                </Field>
                <ChoiceChips
                  label="Suggested reasons" options={COUNT_REASON_HINTS} value={form.reason}
                  onChange={(reason) => setForm((f) => ({ ...f, reason }))}
                />

                <div className="form__actions">
                  <button type="button" className="btn btn--ghost" onClick={() => { setForm(EMPTY); setErrors({}); }}>
                    Clear
                  </button>
                  <button type="submit" className="btn btn--primary" disabled={busy}>
                    {busy ? "Saving…" : "Save count"}
                  </button>
                </div>
              </form>
            </Step>
          )}

          <SessionLog title="Counted this session" items={log} />
        </>
      )}
    </section>
  );
}
