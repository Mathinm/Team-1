import { useCallback, useEffect, useState } from "react";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { can } from "../config/roles.js";
import { Banner, EmptyState, Field, Loading, PageHeader, money } from "../components/ui.jsx";
import { formatDateTime } from "../lib/dates.js";
import { useLiveRefresh } from "../lib/liveRefresh.js";
import { MARKDOWN_MAX_HINT, validateMarkdownRule } from "../lib/validation.js";

const EMPTY = { scope: "product", productId: "", category: "", days: "2", discount: "", name: "" };
const qty = (n) => String(Math.round(Number(n) * 1000) / 1000);

/** FR-14: near-expiry markdown rules, and the batches those rules have marked down. */
export default function MarkdownsPage() {
  const { user } = useAuth();
  const canManage = can(user.role, "manageMarkdownRules");
  const canApply = can(user.role, "applyMarkdowns");

  const [rules, setRules] = useState(null);
  const [markdowns, setMarkdowns] = useState(null);
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [confirmId, setConfirmId] = useState(null); // rule waiting for "Confirm delete"

  const loadRules = useCallback(async () => {
    try {
      setRules(await api.markdownRules());
    } catch (e) {
      setError(e.message);
      setRules((r) => r ?? []);
    }
  }, []);
  const loadMarkdowns = useCallback(async () => {
    try {
      setMarkdowns(await api.markdowns());
    } catch (e) {
      setError(e.message);
      setMarkdowns((m) => m ?? []);
    }
  }, []);
  const loadProducts = useCallback(async () => {
    try {
      const list = await api.listProducts();
      setProducts(list.filter((p) => p.active).sort((a, b) => a.name.localeCompare(b.name)));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadRules();
    loadMarkdowns();
    loadProducts();
  }, [loadRules, loadMarkdowns, loadProducts]);

  // NFR-1: sales change sold / remaining and sell-through, so this table follows them.
  useLiveRefresh(async () => {
    const [r, m] = await Promise.all([api.markdownRules(), api.markdowns()]);
    setRules(r);
    setMarkdowns(m);
  });

  const productById = (id) => products.find((p) => p.productId === id);
  const categories = [...new Set(products.map((p) => p.category))].sort();
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function addRule(e) {
    e.preventDefault();
    const errs = validateMarkdownRule(form);
    setErrors(errs);
    setError("");
    setMessage("");
    if (Object.keys(errs).length) return;
    setSaving(true);
    try {
      const body = {
        daysBeforeExpiry: Number(form.days),
        discountPercent: Number(form.discount),
      };
      if (form.scope === "category") body.category = form.category;
      else body.productId = Number(form.productId);
      if (form.name.trim()) body.name = form.name.trim();
      const rule = await api.createMarkdownRule(body);
      setMessage(`Rule saved: ${rule.name}. Press "Apply markdowns" to use it on batches now.`);
      setForm((f) => ({ ...EMPTY, scope: f.scope }));
      loadRules();
    } catch (ex) {
      // 422 "Discount exceeds maximum 40%": show the server's words next to the discount box.
      if (ex.code === "DISCOUNT_EXCEEDS_MAX") {
        setErrors({ discount: ex.message });
        setError("The rule was not saved. Lower the discount and try again.");
      } else {
        setError(ex.message);
      }
    } finally {
      setSaving(false);
    }
  }

  async function removeRule(rule) {
    setError("");
    setMessage("");
    try {
      await api.deleteMarkdownRule(rule.ruleId);
      setConfirmId(null);
      setMessage(`Rule deleted: ${rule.name}. Batches that are already marked down keep their discount.`);
      loadRules();
    } catch (ex) {
      setConfirmId(null);
      setError(ex.message);
      loadRules();
    }
  }

  async function apply() {
    setError("");
    setMessage("");
    setApplying(true);
    try {
      const res = await api.applyMarkdowns();
      setMessage(
        res.applied > 0
          ? `${res.applied} batch${res.applied === 1 ? "" : "es"} marked down.`
          : rules?.length
            ? "No batch needs a new markdown right now."
            : "There are no rules yet, so nothing was marked down. Add a rule first.",
      );
      loadMarkdowns();
    } catch (ex) {
      setError(ex.message);
    } finally {
      setApplying(false);
    }
  }

  const appliesTo = (r) =>
    r.productId != null
      ? productById(r.productId)?.name ?? `Product #${r.productId}`
      : r.category
        ? `Category: ${r.category}`
        : "All products";

  return (
    <section className="markdowns">
      <PageHeader
        title="Markdowns"
        subtitle="Discount stock that is close to expiry so it sells before it is wasted."
        actions={
          canApply && (
            <button type="button" className="btn btn--primary" onClick={apply} disabled={applying}>
              {applying ? "Applying…" : "Apply markdowns"}
            </button>
          )
        }
      />
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      <div className="card">
        <div className="card__head">
          <div>
            <h2>Markdown rules</h2>
            <p className="muted small">
              A rule marks down a batch when it has this many days or fewer left. If several rules fit,
              the most specific one wins: product, then category.
            </p>
          </div>
          {!canManage && <span className="badge badge--info">View only</span>}
        </div>

        {canManage && (
          <form className="form markdown-form" onSubmit={addRule} noValidate>
            <fieldset className="scope-choice">
              <legend>This rule applies to</legend>
              <label>
                <input type="radio" name="md-scope" value="product" checked={form.scope === "product"} onChange={set("scope")} />
                One product
              </label>
              <label>
                <input type="radio" name="md-scope" value="category" checked={form.scope === "category"} onChange={set("scope")} />
                A category
              </label>
            </fieldset>

            <div className="grid">
              {form.scope === "product" ? (
                <Field label="Product" error={errors.productId} id="md-product">
                  <select id="md-product" value={form.productId} onChange={set("productId")}>
                    <option value="">Choose a product…</option>
                    {products.map((p) => (
                      <option key={p.productId} value={p.productId}>{p.name} ({p.sku})</option>
                    ))}
                  </select>
                </Field>
              ) : (
                <Field label="Category" error={errors.category} id="md-category">
                  <select id="md-category" value={form.category} onChange={set("category")}>
                    <option value="">Choose a category…</option>
                    {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </Field>
              )}
              <Field label="Days before expiry" error={errors.days} id="md-days" hint="Marks down at this many days left, or fewer">
                <input id="md-days" type="number" inputMode="numeric" min="0" step="1" value={form.days} onChange={set("days")} />
              </Field>
              <Field label="Discount (%)" error={errors.discount} id="md-discount" hint={`Store maximum is ${MARKDOWN_MAX_HINT}%`}>
                <input id="md-discount" type="number" inputMode="decimal" min="0" step="any" value={form.discount} onChange={set("discount")} aria-invalid={Boolean(errors.discount)} />
              </Field>
              <Field label="Name (optional)" id="md-name" hint="Shown in the list below">
                <input id="md-name" maxLength={80} value={form.name} onChange={set("name")} />
              </Field>
            </div>
            <div className="form__actions">
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? "Saving…" : "Add rule"}
              </button>
            </div>
          </form>
        )}

        {!rules ? (
          <Loading />
        ) : rules.length === 0 ? (
          <EmptyState>No rules yet.{canManage ? " Add one above." : " A Manager or Admin can add rules."}</EmptyState>
        ) : (
          <div className="table-wrap rules-table">
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Applies to</th>
                  <th className="num">Days left</th>
                  <th className="num">Discount</th>
                  <th>Added by</th>
                  {canManage && <th aria-label="Actions" />}
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.ruleId}>
                    <td data-label="Rule">{r.name}</td>
                    <td data-label="Applies to">{appliesTo(r)}</td>
                    <td data-label="Days left" className="num">{r.daysBeforeExpiry} or fewer</td>
                    <td data-label="Discount" className="num"><strong>{r.discountPercent}%</strong></td>
                    <td data-label="Added by">{r.createdBy}</td>
                    {canManage && (
                      <td className="actions">
                        {confirmId === r.ruleId ? (
                          <>
                            <button type="button" className="btn btn--small btn--danger" onClick={() => removeRule(r)}>
                              Confirm delete
                            </button>
                            <button type="button" className="btn btn--small" onClick={() => setConfirmId(null)}>Cancel</button>
                          </>
                        ) : (
                          <button type="button" className="btn btn--small" onClick={() => setConfirmId(r.ruleId)}>
                            Delete
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card__head">
          <div>
            <h2>Marked-down batches</h2>
            <p className="muted small">Sales of these batches are billed at the discounted price.</p>
          </div>
        </div>
        {!markdowns ? (
          <Loading />
        ) : markdowns.length === 0 ? (
          <EmptyState>No batch is marked down yet. Add a rule, then press “Apply markdowns”.</EmptyState>
        ) : (
          <div className="table-wrap markdown-table">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th className="num">Original price</th>
                  <th className="num">Discounted price</th>
                  <th className="num">Sold / remaining</th>
                  <th>Sell-through</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {markdowns.map((m) => {
                  const unit = productById(m.productId)?.unit ?? "";
                  const pct = Math.max(0, Math.min(100, m.sellThroughPercent));
                  return (
                    <tr key={m.markdownId}>
                      <td data-label="Product">
                        <strong>{m.productName}</strong>
                        <div className="muted small">B-{m.batchId} · {m.sku} · {formatDateTime(m.markedDownAt)}</div>
                      </td>
                      <td data-label="Original price" className="num"><span className="price-old">{money(m.originalPrice)}</span></td>
                      <td data-label="Discounted price" className="num">
                        <span className="price-new">{money(m.discountedPrice)}</span>
                        <div className="muted small">{m.discountPercent}% off</div>
                      </td>
                      <td data-label="Sold / remaining" className="num">
                        {qty(m.quantitySold)} sold / {qty(m.remainingQuantity)} left {unit}
                      </td>
                      <td data-label="Sell-through">
                        <div className="sellthru" role="img" aria-label={`${m.sellThroughPercent}% sold`}>
                          <span className="sellthru__bar"><span style={{ width: `${pct}%` }} /></span>
                          <strong>{m.sellThroughPercent}%</strong>
                        </div>
                      </td>
                      <td data-label="Status">
                        {m.status === "active" ? (
                          <span className="badge badge--fresh"><span aria-hidden="true">●</span> Active</span>
                        ) : m.status === "sold_out" ? (
                          <span className="badge badge--info"><span aria-hidden="true">●</span> Sold out</span>
                        ) : m.status === "ended" ? (
                          <span className="badge badge--info" title="The batch was removed or counted to zero">
                            <span aria-hidden="true">●</span> Ended
                          </span>
                        ) : (
                          <span className="badge badge--info">{m.status}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
