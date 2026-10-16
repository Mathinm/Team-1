import { useState } from "react";
import { api } from "../api/endpoints.js";
import { Banner, Field } from "../components/ui.jsx";
import {
  CATEGORIES,
  DEFAULT_LOW_STOCK_THRESHOLD,
  STORAGE_TYPES,
  UNITS,
  productToPayload,
  validateProduct,
} from "../lib/validation.js";

const EMPTY = {
  name: "",
  sku: "",
  category: "",
  unit: "kg",
  shelfLifeDays: "",
  storageType: "",
  tempMin: "",
  tempMax: "",
  costPrice: "",
  sellingPrice: "",
  lowStockThreshold: String(DEFAULT_LOW_STOCK_THRESHOLD),
};

function toForm(p) {
  if (!p) return EMPTY;
  return Object.fromEntries(Object.keys(EMPTY).map((k) => [k, String(p[k] ?? "")]));
}

/** Add / edit product (FR-1). */
export default function ProductForm({ product, onCancel, onSaved }) {
  const isNew = !product;
  const [form, setForm] = useState(() => toForm(product));
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const err = (k) => errors[k];

  async function submit(e) {
    e.preventDefault();
    const errs = validateProduct(form);
    setErrors(errs);
    setError("");
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const body = productToPayload(form);
      const saved = isNew
        ? await api.createProduct(body)
        : await api.updateProduct(product.productId, body);
      onSaved(saved, isNew);
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <h2>{isNew ? "Add product" : `Edit ${product.name}`}</h2>
      <Banner kind="error">{error}</Banner>

      <div className="grid">
        <Field label="Name" error={err("name")} id="p-name">
          <input id="p-name" value={form.name} onChange={set("name")} />
        </Field>
        <Field label="SKU" error={err("sku")} hint="Code used at the till, e.g. TOM-01" id="p-sku">
          <input id="p-sku" value={form.sku} onChange={set("sku")} />
        </Field>
        <Field label="Category" error={err("category")} id="p-cat">
          <select id="p-cat" value={form.category} onChange={set("category")}>
            <option value="">Choose…</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Unit of measure" error={err("unit")} id="p-unit">
          <select id="p-unit" value={form.unit} onChange={set("unit")}>
            {UNITS.map((u) => <option key={u}>{u}</option>)}
          </select>
        </Field>
        <Field label="Standard shelf-life (days)" error={err("shelfLifeDays")} id="p-shelf">
          <input id="p-shelf" type="number" min="1" step="1" value={form.shelfLifeDays} onChange={set("shelfLifeDays")} />
        </Field>
        <Field label="Storage type" error={err("storageType")} id="p-storage">
          <select id="p-storage" value={form.storageType} onChange={set("storageType")}>
            <option value="">Choose…</option>
            {STORAGE_TYPES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Min temperature (°C)" error={err("tempMin")} id="p-tmin">
          <input id="p-tmin" type="number" step="0.5" value={form.tempMin} onChange={set("tempMin")} />
        </Field>
        <Field label="Max temperature (°C)" error={err("tempMax")} id="p-tmax">
          <input id="p-tmax" type="number" step="0.5" value={form.tempMax} onChange={set("tempMax")} />
        </Field>
        <Field label="Cost price (₹)" error={err("costPrice")} id="p-cost">
          <input id="p-cost" type="number" min="0" step="0.01" value={form.costPrice} onChange={set("costPrice")} />
        </Field>
        <Field label="Selling price (₹)" error={err("sellingPrice")} id="p-price">
          <input id="p-price" type="number" min="0" step="0.01" value={form.sellingPrice} onChange={set("sellingPrice")} />
        </Field>
        <Field label="Low-stock threshold" error={err("lowStockThreshold")} hint="Default 10 units" id="p-thr">
          <input id="p-thr" type="number" min="0" step="1" value={form.lowStockThreshold} onChange={set("lowStockThreshold")} />
        </Field>
      </div>

      <div className="form__actions">
        <button type="button" className="btn btn--ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? "Saving…" : isNew ? "Add product" : "Save changes"}
        </button>
      </div>
    </form>
  );
}
