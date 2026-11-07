import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { can } from "../config/roles.js";
import { Banner, EmptyState, Loading, PageHeader, StockBadge, money } from "../components/ui.jsx";
import { useLiveRefresh } from "../lib/liveRefresh.js";
import ProductForm from "./ProductForm.jsx";
import ProductThumb from "../components/ProductThumb.jsx";
import "./products-login.css";

/** Width of the stock bar: full at twice the low-stock threshold. Look only. */
function stockLevel(stock, threshold) {
  const full = Math.max(threshold * 2, 1);
  return Math.max(0, Math.min(100, (stock / full) * 100));
}

export default function ProductsPage() {
  const { user } = useAuth();
  const canEdit = can(user.role, "editProducts");
  const [products, setProducts] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [editing, setEditing] = useState(null); // null | "new" | product

  const load = useCallback(async () => {
    try {
      setProducts(await api.listProducts());
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useLiveRefresh(load); // NFR-1: stock changes from other screens and devices show within 5 s

  const visible = useMemo(() => {
    if (!products) return [];
    const q = query.trim().toLowerCase();
    return products
      .filter((p) => showInactive || p.active)
      .filter((p) => !q || [p.name, p.sku, p.category].some((v) => v.toLowerCase().includes(q)))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [products, query, showInactive]);

  // Counts for the summary tiles, from the list already loaded (same rules as StockBadge).
  const counts = useMemo(() => {
    const active = (products ?? []).filter((p) => p.active);
    const out = active.filter((p) => p.stock <= 0).length;
    const low = active.filter((p) => p.stock > 0 && p.stock < p.lowStockThreshold).length;
    return { total: active.length, ok: active.length - out - low, low, out };
  }, [products]);

  async function toggleActive(p) {
    setError("");
    setMessage("");
    try {
      if (p.active) await api.deactivateProduct(p.productId);
      else await api.activateProduct(p.productId);
      setMessage(`${p.name} ${p.active ? "deactivated" : "re-activated"}.`);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  function saved(p, isNew) {
    setEditing(null);
    setMessage(`${p.name} ${isNew ? "added" : "updated"}.`);
    load();
  }

  return (
    <section className="products-v2">
      <PageHeader
        title="Products"
        subtitle="Product master data: shelf-life, storage, prices and low-stock threshold"
        actions={
          canEdit && (
            <button className="btn btn--primary" onClick={() => setEditing("new")}>
              + Add product
            </button>
          )
        }
      />
      {products && (
        <div className="ptiles">
          <div className="ptile"><span className="ptile__label">Products</span><strong>{counts.total}</strong><span className="ptile__note">active</span></div>
          <div className="ptile ptile--ok"><span className="ptile__label">In stock</span><strong>{counts.ok}</strong><span className="ptile__note">above minimum</span></div>
          <div className={`ptile${counts.low ? " ptile--low" : ""}`}><span className="ptile__label">Low stock</span><strong>{counts.low}</strong><span className="ptile__note">below minimum</span></div>
          <div className={`ptile${counts.out ? " ptile--out" : ""}`}><span className="ptile__label">Out of stock</span><strong>{counts.out}</strong><span className="ptile__note">none left</span></div>
        </div>
      )}
      <Banner kind="success" onClose={() => setMessage("")}>{message}</Banner>
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>

      {editing && (
        <ProductForm
          product={editing === "new" ? null : editing}
          onCancel={() => setEditing(null)}
          onSaved={saved}
        />
      )}

      <div className="toolbar">
        <input
          type="search"
          placeholder="Search name, SKU or category"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search products"
        />
        <label className="check">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          Show deactivated
        </label>
      </div>

      {!products ? (
        <Loading />
      ) : visible.length === 0 ? (
        <EmptyState>No products match.</EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th>Shelf-life · storage</th>
                <th className="num">Price</th>
                <th className="num">Stock</th>
                <th>Status</th>
                {canEdit && <th aria-label="Actions" />}
              </tr>
            </thead>
            <tbody>
              {visible.map((p) => (
                <tr key={p.productId} className={p.active ? "" : "row--inactive"}>
                  <td data-label="Product">
                    <div className="pcell">
                      <ProductThumb name={p.name} sku={p.sku} category={p.category} />
                      <div>
                        <strong>{p.name}</strong>
                        <div className="muted small">{p.sku}</div>
                      </div>
                    </div>
                  </td>
                  <td data-label="Category">{p.category}</td>
                  <td data-label="Shelf-life · storage">
                    {p.shelfLifeDays} days
                    <div className="muted small">{p.storageType} · {p.tempMin}–{p.tempMax} °C</div>
                  </td>
                  <td data-label="Price" className="num">
                    {money(p.sellingPrice)} / {p.unit}
                    <div className="muted small">cost {money(p.costPrice)}</div>
                  </td>
                  <td data-label="Stock" className="num">
                    {p.stock} {p.unit}
                    <div className="muted small">min {p.lowStockThreshold}</div>
                    <span
                      className={`sbar${p.stock < p.lowStockThreshold ? " sbar--low" : ""}`}
                      aria-hidden="true"
                    >
                      <span style={{ width: `${stockLevel(p.stock, p.lowStockThreshold)}%` }} />
                    </span>
                  </td>
                  <td data-label="Status">
                    {p.active ? <StockBadge stock={p.stock} threshold={p.lowStockThreshold} /> : <span className="tag">Deactivated</span>}
                  </td>
                  {canEdit && (
                    <td className="actions">
                      <button className="btn btn--small" onClick={() => setEditing(p)}>Edit</button>
                      <button className="btn btn--small btn--ghost" onClick={() => toggleActive(p)}>
                        {p.active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
