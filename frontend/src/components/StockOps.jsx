// Shared pieces for the Waste & removals (FR-13) and Stock count (FR-9) screens:
// one hook that loads products and batches, plus the product card, batch picker,
// variance chip and "recorded this session" list. Both screens look and behave alike.

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/endpoints.js";
import { describeDaysToExpiry, formatDate } from "../lib/dates.js";
import { useLiveRefresh } from "../lib/liveRefresh.js";
import { EmptyState, ExpiryBadge, Loading, StockBadge } from "./ui.jsx";
import ProductThumb from "./ProductThumb.jsx";
import "../pages/products-login.css"; // fonts + .pthumb (shared with Products)
import "../pages/stock-ops.css";

/** Active products, the batches of the chosen product, and which batch is picked. */
export function useBatchPicker() {
  const [products, setProducts] = useState(null);
  const [productId, setProductId] = useState("");
  const [batches, setBatches] = useState(null);
  const [batchId, setBatchId] = useState("");
  const [error, setError] = useState("");
  const current = useRef(productId); // the product on screen right now
  useEffect(() => {
    current.current = productId;
  }, [productId]);

  const sortActive = (list) => list.filter((p) => p.active).sort((a, b) => a.name.localeCompare(b.name));

  const loadProducts = useCallback(async () => {
    try {
      const active = sortActive(await api.listProducts());
      setProducts(active);
      setProductId((cur) => cur || String(active[0]?.productId ?? ""));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  // quiet = background refresh: no spinner, and a failure keeps the list on screen.
  const loadBatches = useCallback(async (id, quiet = false) => {
    if (!id) return;
    if (!quiet) setBatches(null);
    try {
      const list = await api.fefo(id);
      if (quiet && current.current !== id) return; // another product was picked meanwhile
      setBatches(list);
    } catch (e) {
      if (quiet) return;
      setError(e.message);
      setBatches([]);
    }
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  useEffect(() => {
    setBatchId("");
    loadBatches(productId);
  }, [productId, loadBatches]);

  // NFR-1: sales and deliveries made elsewhere show here without a reload.
  useLiveRefresh(async () => {
    const pending = loadBatches(current.current, true);
    const ps = await api.listProducts();
    setProducts(sortActive(ps));
    await pending;
  });

  // One batch: pick it for the worker. A picked batch that sold out or was emptied: drop it.
  useEffect(() => {
    if (!batches) return;
    if (batchId && !batches.some((b) => String(b.batchId) === batchId)) setBatchId("");
    else if (!batchId && batches.length === 1) setBatchId(String(batches[0].batchId));
  }, [batches, batchId]);

  const product = products?.find((p) => String(p.productId) === productId) ?? null;
  const batch = batches?.find((b) => String(b.batchId) === batchId) ?? null;
  const refresh = useCallback(() => {
    loadProducts();
    loadBatches(current.current);
  }, [loadProducts, loadBatches]);

  return { products, productId, setProductId, product, batches, batchId, setBatchId, batch, error, setError, refresh };
}

/** Step heading: a numbered 3D badge and a title. */
export function Step({ n, title, hint, children }) {
  return (
    <section className="ostep">
      <header className="ostep__head">
        <span className="ostep__n" aria-hidden="true">{n}</span>
        <div>
          <h2>{title}</h2>
          {hint && <p className="muted small">{hint}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

/** Product choice plus a card with photo, stock on hand and stock status. */
export function ProductPicker({ id, products, productId, onChange, product }) {
  if (!products) return <Loading />;
  if (products.length === 0) return <EmptyState>No active products yet. Add one on the Products page.</EmptyState>;
  const full = product ? Math.max(product.lowStockThreshold * 2, 1) : 1;
  const level = product ? Math.max(0, Math.min(100, (product.stock / full) * 100)) : 0;
  return (
    <div className="oproduct">
      <div className="field">
        <label htmlFor={id}>Product</label>
        <select id={id} value={productId} onChange={(e) => onChange(e.target.value)}>
          {products.map((p) => (
            <option key={p.productId} value={p.productId}>
              {p.name} ({p.sku})
            </option>
          ))}
        </select>
      </div>
      {product && (
        <div className="ocard">
          <ProductThumb name={product.name} sku={product.sku} category={product.category} />
          <div className="ocard__main">
            <strong>{product.name}</strong>
            <span className="muted small">{product.sku} · {product.category}</span>
          </div>
          <div className="ocard__stock">
            <span className="muted small">On hand</span>
            <strong>{product.stock} {product.unit}</strong>
            <span className={`sbar${product.stock < product.lowStockThreshold ? " sbar--low" : ""}`} aria-hidden="true">
              <span style={{ width: `${level}%` }} />
            </span>
          </div>
          <StockBadge stock={product.stock} threshold={product.lowStockThreshold} />
        </div>
      )}
    </div>
  );
}

/** Batches of the product, soonest expiry first. Click a row or its button to pick it. */
export function BatchPicker({ batches, unit, selectedId, onSelect, error }) {
  if (!batches) return <Loading />;
  if (batches.length === 0) return <EmptyState>No stock on hand for this product, so there is nothing to select.</EmptyState>;
  return (
    <>
      {error && <p className="field__error" role="alert">{error}</p>}
      <div className="table-wrap otable">
        <table>
          <thead>
            <tr>
              <th>Batch</th>
              <th>Supplier</th>
              <th className="num">System quantity</th>
              <th>Expiry</th>
              <th>Status</th>
              <th aria-label="Select" />
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => {
              const picked = String(b.batchId) === selectedId;
              return (
                <tr
                  key={b.batchId}
                  className={picked ? "is-selected" : ""}
                  onClick={() => onSelect(String(b.batchId))}
                >
                  <td data-label="Batch"><strong>B-{b.batchId}</strong></td>
                  <td data-label="Supplier">{b.supplier ?? "-"}</td>
                  <td data-label="System quantity" className="num"><strong>{b.quantity}</strong> {b.unit ?? unit}</td>
                  <td data-label="Expiry">
                    {formatDate(b.expiryDate)}
                    <div className="muted small">{describeDaysToExpiry(b.daysToExpiry)}</div>
                  </td>
                  <td data-label="Status"><ExpiryBadge daysToExpiry={b.daysToExpiry} /></td>
                  <td className="actions">
                    <button
                      type="button"
                      className={`btn btn--small${picked ? " btn--primary" : ""}`}
                      aria-pressed={picked}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(String(b.batchId));
                      }}
                    >
                      {picked ? "✓ Selected" : "Select"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Counted minus system: none, short (red) or over (cream). Icon and words, never colour alone. */
export function VarianceChip({ variance, unit }) {
  if (variance === 0) return <span className="badge badge--fresh"><span aria-hidden="true">●</span> No variance</span>;
  const short = variance < 0;
  return (
    <span className={`badge ${short ? "badge--expired" : "badge--surplus"}`}>
      <span aria-hidden="true">{short ? "■" : "▲"}</span> {short ? "Short by" : "Over by"} {Math.abs(variance)} {unit}
    </span>
  );
}

/** Pill buttons that behave as a radio group (reasons). */
export function ChoiceChips({ label, options, value, onChange, tone = "green" }) {
  return (
    <div className="chips-field" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o}
          type="button"
          role="radio"
          aria-checked={value === o}
          className={`chip chip--${tone}${value === o ? " is-on" : ""}`}
          onClick={() => onChange(o)}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

/** What this person recorded since opening the screen (nothing stored; the server has the record). */
export function SessionLog({ title, items }) {
  if (items.length === 0) return null;
  return (
    <section className="olog" aria-label={title}>
      <h2>{title}</h2>
      <ul>
        {items.map((it) => (
          <li key={it.id}>
            <span className="olog__time muted small">{it.time}</span>
            <span>{it.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export const clock = (iso) =>
  new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
