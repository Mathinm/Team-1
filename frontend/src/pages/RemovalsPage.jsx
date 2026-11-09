import { useState } from "react";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { can } from "../config/roles.js";
import { ALERTS_CHANGED } from "../components/Layout.jsx";
import { Banner, Field, PageHeader } from "../components/ui.jsx";
import {
  BatchPicker, ChoiceChips, ProductPicker, SessionLog, Step, clock, useBatchPicker,
} from "../components/StockOps.jsx";
import {
  REMOVAL_OTHER_MAX, REMOVAL_REASONS, removalReasonText, validateRemoval,
} from "../lib/validation.js";

const EMPTY = { qty: "", reason: "", detail: "" };

/** FR-13: record spoiled, damaged or temperature-breached stock and take it out of the batch. */
export default function RemovalsPage() {
  const { user } = useAuth();
  const allowed = can(user.role, "recordRemoval");
  const pick = useBatchPicker();
  const { product, batch } = pick;
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);

  const unit = batch?.unit ?? product?.unit ?? "";
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const qty = Number(form.qty);
  const showAfter = batch && form.qty !== "" && Number.isFinite(qty) && qty > 0 && qty <= batch.quantity;
  const after = showAfter ? Math.round((batch.quantity - qty) * 1000) / 1000 : null;

  function chooseProduct(id) {
    pick.setProductId(id);
    setForm(EMPTY);
    setErrors({});
  }

  async function submit(e) {
    e.preventDefault();
    const errs = validateRemoval({
      batchId: pick.batchId, qty: form.qty, reason: form.reason, detail: form.detail,
      available: batch?.quantity, unit: batch?.unit ?? product?.unit,
    });
    setErrors(errs);
    setError("");
    setMessage("");
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const reason = removalReasonText(form.reason, form.detail);
      const res = await api.recordRemoval({ batchId: Number(pick.batchId), qty, reason });
      const text = `${qty} ${unit} of ${product?.name} removed from B-${res.batchId} (${reason}). ${res.remainingQuantity} ${unit} left in the batch.`;
      setMessage(text);
      setLog((l) => [{ id: res.removalId, time: clock(res.recordedAt), text }, ...l]);
      setForm(EMPTY);
      pick.refresh();
      window.dispatchEvent(new Event(ALERTS_CHANGED)); // a removal raises an info alert
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ops-v2">
      <PageHeader
        title="Waste & removals"
        subtitle="Record stock lost to damage, spoilage or a temperature breach. It is taken out of the batch at once."
      />
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => { setError(""); pick.setError(""); }}>{error || pick.error}</Banner>

      {!allowed ? (
        <Banner kind="error">Your role ({user.role}) cannot record removals.</Banner>
      ) : (
        <>
          <Step n="1" title="Choose the product">
            <ProductPicker
              id="rm-product" products={pick.products} productId={pick.productId}
              onChange={chooseProduct} product={product}
            />
          </Step>

          <Step n="2" title="Choose the batch" hint="Soonest expiry first. Pick the batch the stock came from.">
            <BatchPicker
              batches={pick.batches} unit={product?.unit} selectedId={pick.batchId}
              onSelect={pick.setBatchId} error={errors.batchId}
            />
          </Step>

          {batch && (
            <Step n="3" title="What was lost?">
              <form className="opanel" onSubmit={submit} noValidate>
                <div className="opanel__grid">
                  <Field label={`Quantity removed (${unit})`} error={errors.qty} id="rm-qty"
                    hint={`Up to ${batch.quantity} ${unit} in B-${batch.batchId}`}>
                    <div className="qty-row">
                      <input
                        id="rm-qty" type="number" inputMode="decimal" min="0"
                        step={unit === "piece" ? "1" : "any"} value={form.qty} onChange={set("qty")}
                      />
                      <button
                        type="button" className="btn btn--small"
                        onClick={() => setForm((f) => ({ ...f, qty: String(batch.quantity) }))}
                      >
                        All
                      </button>
                    </div>
                  </Field>

                  <div className="field">
                    <span className="field__label" id="rm-reason-label">Reason</span>
                    <ChoiceChips
                      label="Reason" options={REMOVAL_REASONS} tone="red" value={form.reason}
                      onChange={(reason) => setForm((f) => ({ ...f, reason }))}
                    />
                    {errors.reason && <span className="field__error" role="alert">{errors.reason}</span>}
                  </div>

                  {form.reason === "Other" && (
                    <Field label="Describe it (optional)" id="rm-detail" hint={`Up to ${REMOVAL_OTHER_MAX} characters`}>
                      <input
                        id="rm-detail" maxLength={REMOVAL_OTHER_MAX} value={form.detail}
                        onChange={set("detail")} autoFocus
                      />
                    </Field>
                  )}
                </div>

                {after !== null && (
                  <p className={`opreview${after === 0 ? " opreview--empty" : ""}`} aria-live="polite">
                    B-{batch.batchId}: <strong>{batch.quantity} {unit}</strong> → <strong>{after} {unit}</strong>
                    {after === 0 && " (batch will be empty)"}
                  </p>
                )}

                <div className="form__actions">
                  <button type="button" className="btn btn--ghost" onClick={() => { setForm(EMPTY); setErrors({}); }}>
                    Clear
                  </button>
                  <button type="submit" className="btn btn--danger" disabled={busy}>
                    {busy ? "Saving…" : "Record removal"}
                  </button>
                </div>
              </form>
            </Step>
          )}

          <SessionLog title="Recorded this session" items={log} />
        </>
      )}
    </section>
  );
}
