import { useEffect, useRef, useState } from "react";
import { api } from "../api/endpoints.js";
import { Banner, Field, PageHeader, money } from "../components/ui.jsx";
import { formatDate } from "../lib/dates.js";
import { downloadText } from "../lib/csv.js";
import { validateSale } from "../lib/validation.js";

const SAMPLE_CSV = "sku,quantity,soldAt\nTOM-01,2,\nBAN-01,6,\nMLK-01,3,\n";

export default function SalesPage() {
  const [products, setProducts] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listProducts()
      .then((ps) => setProducts(ps.filter((p) => p.active).sort((a, b) => a.name.localeCompare(b.name))))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <section>
      <PageHeader title="Sales" subtitle="Record a sale by hand or upload a CSV. Stock is taken from the earliest-expiring batch first." />
      <Banner kind="error" onClose={() => setError("")}>{error}</Banner>
      <div className="two-col">
        <ManualSale products={products} />
        <CsvUpload />
      </div>
    </section>
  );
}

function ManualSale({ products }) {
  const [form, setForm] = useState({ sku: "", quantity: "" });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const product = products.find((p) => p.sku === form.sku);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    const errs = validateSale(form);
    setErrors(errs);
    setError("");
    setResult(null);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const res = await api.recordSale({ sku: form.sku, quantity: Number(form.quantity), unit: product?.unit });
      setResult({ ...res, productName: res.productName ?? product?.name, unit: res.unit ?? product?.unit });
      setForm((f) => ({ ...f, quantity: "" }));
    } catch (ex) {
      // 422 Insufficient stock / Batch expired are shown as they come from the API.
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <h2>Manual sale</h2>
      <Banner kind="error">{error}</Banner>
      <Field label="Product" error={errors.sku} id="sale-sku">
        <select id="sale-sku" value={form.sku} onChange={set("sku")}>
          <option value="">Choose…</option>
          {products.map((p) => (
            <option key={p.productId} value={p.sku}>
              {p.name} ({p.sku}) · {money(p.sellingPrice)}/{p.unit}
            </option>
          ))}
        </select>
      </Field>
      <Field
        label={`Quantity${product ? ` (${product.unit})` : ""}`}
        error={errors.quantity}
        hint={product ? `On hand: ${product.stock} ${product.unit}` : undefined}
        id="sale-qty"
      >
        <input id="sale-qty" type="number" min="0" step="any" value={form.quantity} onChange={set("quantity")} />
      </Field>
      <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
        {busy ? "Recording…" : "Record sale"}
      </button>

      {result && (
        <div className="result" role="status">
          <h3>Sale #{result.saleId} recorded{result.amount ? ` · ${money(result.amount)}` : ""}</h3>
          <p className="muted small">Batches used (FEFO):</p>
          <ul className="plain">
            {result.batchesUsed.map((b) => (
              <li key={b.batchId}>
                B-{b.batchId}: {b.qty} {result.unit}
                {b.expiryDate ? <span className="muted"> · expires {formatDate(b.expiryDate)}</span> : null}
              </li>
            ))}
          </ul>
          <p>
            Remaining stock of {result.productName}: <strong>{result.remainingStock} {result.unit}</strong>
          </p>
        </div>
      )}
    </form>
  );
}

function CsvUpload() {
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setResult(null);
    if (!file) {
      setError("Choose a CSV file first");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("The file must be a .csv");
      return;
    }
    setBusy(true);
    try {
      setResult(await api.uploadSalesCsv(file));
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <h2>Upload sales CSV</h2>
      <p className="muted small">
        Columns: <code>sku,quantity,soldAt</code> (soldAt optional).{" "}
        <button type="button" className="link" onClick={() => downloadText("sales-sample.csv", SAMPLE_CSV)}>
          Download a sample
        </button>
      </p>
      <Banner kind="error">{error}</Banner>
      <Field label="CSV file" id="sale-csv">
        <input id="sale-csv" ref={fileRef} type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
        {busy ? "Uploading…" : "Upload"}
      </button>

      {result && (
        <div className="result" role="status">
          <h3>
            {result.imported} imported · {result.failed} failed
          </h3>
          {result.errors?.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Line</th><th>Problem</th></tr>
                </thead>
                <tbody>
                  {result.errors.map((er) => (
                    <tr key={er.line}>
                      <td data-label="Line">{er.line}</td>
                      <td data-label="Problem">{er.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </form>
  );
}
