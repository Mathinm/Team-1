import { useCallback, useEffect, useState } from "react";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { can } from "../config/roles.js";
import { Banner, EmptyState, ExpiryBadge, Field, Loading, PageHeader, StockBadge } from "../components/ui.jsx";
import { describeDaysToExpiry, formatDate, toISODate, toLocalDateTime, addDays } from "../lib/dates.js";
import { validateBatch, validateRestock } from "../lib/validation.js";

export default function StockPage() {
  const { user } = useAuth();
  const canReceive = can(user.role, "receiveBatch");
  const [products, setProducts] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [productId, setProductId] = useState("");
  const [batches, setBatches] = useState(null);
  const [panel, setPanel] = useState(null); // null | "receive" | "restock"
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadProducts = useCallback(async () => {
    try {
      const [ps, ss] = await Promise.all([api.listProducts(), api.listSuppliers()]);
      const active = ps.filter((p) => p.active).sort((a, b) => a.name.localeCompare(b.name));
      setProducts(active);
      setSuppliers(ss);
      setProductId((cur) => cur || String(active[0]?.productId ?? ""));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const loadBatches = useCallback(async (id) => {
    if (!id) return;
    setBatches(null);
    try {
      setBatches(await api.fefo(id));
    } catch (e) {
      setError(e.message);
      setBatches([]);
    }
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  useEffect(() => {
    loadBatches(productId);
  }, [productId, loadBatches]);

  const product = products?.find((p) => String(p.productId) === productId);

  function done(text, id) {
    setPanel(null);
    setMessage(text);
    setError("");
    if (id) setProductId(String(id));
    loadProducts();
    loadBatches(id ? String(id) : productId);
  }

  return (
    <section>
      <PageHeader
        title="Stock & FEFO"
        subtitle="Batches in First-Expired-First-Out order, with time in store and time left"
        actions={
          canReceive && (
            <>
              <button className="btn btn--primary" onClick={() => setPanel(panel === "receive" ? null : "receive")}>
                Receive batch
              </button>
              <button className="btn" onClick={() => setPanel(panel === "restock" ? null : "restock")}>
                Restock
              </button>
            </>
          )
        }
      />
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      {panel === "receive" && products && (
        <ReceiveBatchForm
          products={products}
          suppliers={suppliers}
          defaultProductId={productId}
          onCancel={() => setPanel(null)}
          onDone={done}
        />
      )}
      {panel === "restock" && products && (
        <RestockForm
          products={products}
          defaultProductId={productId}
          onCancel={() => setPanel(null)}
          onDone={done}
        />
      )}

      {!products ? (
        <Loading />
      ) : products.length === 0 ? (
        <EmptyState>No active products yet. Add one on the Products page.</EmptyState>
      ) : (
        <>
          <div className="toolbar">
            <Field label="Product" id="s-product">
              <select id="s-product" value={productId} onChange={(e) => setProductId(e.target.value)}>
                {products.map((p) => (
                  <option key={p.productId} value={p.productId}>
                    {p.name} ({p.sku})
                  </option>
                ))}
              </select>
            </Field>
            {product && (
              <div className="summary">
                <div>
                  <span className="muted small">On hand</span>
                  <strong>{product.stock} {product.unit}</strong>
                </div>
                <StockBadge stock={product.stock} threshold={product.lowStockThreshold} />
              </div>
            )}
          </div>

          {!batches ? (
            <Loading />
          ) : batches.length === 0 ? (
            <EmptyState>No stock for this product.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Sell order</th>
                    <th>Batch</th>
                    <th>Supplier</th>
                    <th className="num">Quantity</th>
                    <th>In store</th>
                    <th>Expiry</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {batches.map((b, i) => (
                    <tr key={b.batchId}>
                      <td data-label="Sell order">
                        {b.daysToExpiry < 0 ? <span className="muted">Do not sell</span> : <strong>#{fefoRank(batches, i)}</strong>}
                      </td>
                      <td data-label="Batch">B-{b.batchId}</td>
                      <td data-label="Supplier">{b.supplier ?? "-"}</td>
                      <td data-label="Quantity" className="num">{b.quantity} {b.unit ?? product?.unit}</td>
                      <td data-label="In store">{b.daysInStore} day{b.daysInStore === 1 ? "" : "s"}</td>
                      <td data-label="Expiry">
                        {formatDate(b.expiryDate)}
                        <div className="muted small">{describeDaysToExpiry(b.daysToExpiry)}</div>
                      </td>
                      <td data-label="Status"><ExpiryBadge daysToExpiry={b.daysToExpiry} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** Position among the sellable (unexpired) batches, 1 = sell first. */
function fefoRank(batches, index) {
  return batches.slice(0, index + 1).filter((b) => b.daysToExpiry >= 0).length;
}

function ReceiveBatchForm({ products, suppliers, defaultProductId, onCancel, onDone }) {
  const [form, setForm] = useState(() => {
    const p = products.find((x) => String(x.productId) === defaultProductId);
    const now = new Date();
    return {
      productId: defaultProductId,
      supplierId: "",
      quantity: "",
      receivedAt: toLocalDateTime(now),
      expiryDate: p ? toISODate(addDays(now, p.shelfLifeDays)) : "",
    };
  });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const product = products.find((p) => String(p.productId) === form.productId);

  const set = (k) => (e) => {
    const value = e.target.value;
    setForm((f) => {
      const next = { ...f, [k]: value };
      // Suggest expiry from the product's standard shelf-life when the product changes.
      if (k === "productId") {
        const p = products.find((x) => String(x.productId) === value);
        if (p) next.expiryDate = toISODate(addDays(new Date(f.receivedAt || Date.now()), p.shelfLifeDays));
      }
      return next;
    });
  };

  async function submit(e) {
    e.preventDefault();
    const errs = validateBatch(form);
    setErrors(errs);
    setError("");
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const res = await api.receiveBatch({
        productId: Number(form.productId),
        supplierId: Number(form.supplierId),
        quantity: Number(form.quantity),
        unit: product?.unit,
        receivedAt: new Date(form.receivedAt).toISOString(),
        expiryDate: form.expiryDate,
      });
      onDone(`Batch B-${res.batchId} received: ${form.quantity} ${product?.unit} of ${product?.name}.`, form.productId);
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <h2>Receive batch</h2>
      <Banner kind="error">{error}</Banner>
      <div className="grid">
        <Field label="Product" error={errors.productId} id="b-product">
          <select id="b-product" value={form.productId} onChange={set("productId")}>
            <option value="">Choose…</option>
            {products.map((p) => <option key={p.productId} value={p.productId}>{p.name} ({p.sku})</option>)}
          </select>
        </Field>
        <Field label="Supplier" error={errors.supplierId} id="b-supplier">
          <select id="b-supplier" value={form.supplierId} onChange={set("supplierId")}>
            <option value="">Choose…</option>
            {suppliers.map((s) => <option key={s.supplierId} value={s.supplierId}>{s.name}</option>)}
          </select>
        </Field>
        <Field label={`Quantity${product ? ` (${product.unit})` : ""}`} error={errors.quantity} id="b-qty">
          <input id="b-qty" type="number" min="0" step="any" value={form.quantity} onChange={set("quantity")} />
        </Field>
        <Field label="Received at" error={errors.receivedAt} id="b-recv">
          <input id="b-recv" type="datetime-local" value={form.receivedAt} onChange={set("receivedAt")} />
        </Field>
        <Field
          label="Expiry date"
          error={errors.expiryDate}
          hint={product ? `Suggested from ${product.shelfLifeDays}-day shelf-life` : undefined}
          id="b-exp"
        >
          <input id="b-exp" type="date" value={form.expiryDate} onChange={set("expiryDate")} />
        </Field>
      </div>
      <div className="form__actions">
        <button type="button" className="btn btn--ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn--primary" disabled={busy}>{busy ? "Saving…" : "Save batch"}</button>
      </div>
    </form>
  );
}

function RestockForm({ products, defaultProductId, onCancel, onDone }) {
  const [form, setForm] = useState({ productId: defaultProductId, quantity: "" });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const product = products.find((p) => String(p.productId) === form.productId);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    const errs = validateRestock(form);
    setErrors(errs);
    setError("");
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const res = await api.restock({
        productId: Number(form.productId),
        quantity: Number(form.quantity),
        unit: product?.unit,
      });
      onDone(`Restocked ${form.quantity} ${product?.unit} of ${product?.name}. Stock is now ${res.newStock} ${product?.unit}.`, form.productId);
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <h2>Restock</h2>
      <p className="muted small">Adds stock with expiry set from the product's standard shelf-life.</p>
      <Banner kind="error">{error}</Banner>
      <div className="grid">
        <Field label="Product" error={errors.productId} id="r-product">
          <select id="r-product" value={form.productId} onChange={set("productId")}>
            <option value="">Choose…</option>
            {products.map((p) => <option key={p.productId} value={p.productId}>{p.name} ({p.sku})</option>)}
          </select>
        </Field>
        <Field label={`Quantity${product ? ` (${product.unit})` : ""}`} error={errors.quantity} id="r-qty">
          <input id="r-qty" type="number" min="0" step="any" value={form.quantity} onChange={set("quantity")} />
        </Field>
      </div>
      <div className="form__actions">
        <button type="button" className="btn btn--ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn--primary" disabled={busy}>{busy ? "Saving…" : "Restock"}</button>
      </div>
    </form>
  );
}
