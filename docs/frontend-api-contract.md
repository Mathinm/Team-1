# Frontend ↔ Backend API contract

What the React app calls, based on **SAD 4.3**. Backend owners: please match
these paths, field names and status codes so the screens work without changes.
Items marked **(added)** are not in the SAD yet; the UI needs them.

All paths are under `/api`. Every call except login sends
`Authorization: Bearer <token>`. Errors use SAD 4.4:

```json
{ "error": { "code": "INSUFFICIENT_STOCK", "message": "Insufficient stock: only 30 l available", "details": null } }
```

The UI shows `error.message` to the user, so write it as a sentence a store worker
understands. FastAPI's default `{"detail": "..."}` also works. Any **401** logs the
user out and sends them to the login page.

## Sprint 1 (issue #8)

| Method & path | Who (SEC-2) | Request | Response | Owner issue |
|---|---|---|---|---|
| `POST /auth/login` | public | `{userId, password, otpCode?}` | 200 `{token, role, expiresIn, name, userId}` **(added: name, userId)** | #3 |
| `POST /auth/logout` | any | – | 204 | #3 |
| `GET /products` **(added)** | any | – | 200 `[{productId, sku, name, category, unit, shelfLifeDays, storageType, tempMin, tempMax, costPrice, sellingPrice, lowStockThreshold, active, stock}]` (`stock` = total on hand) | #5 |
| `POST /products` | Admin, Manager | product fields + **`sku` (added)** | 201 product | #5 |
| `PUT /products/{id}` | Admin, Manager | product fields | 200 product | #5 |
| `PATCH /products/{id}/deactivate` | Admin, Manager | – | 200 product | #5 |
| `PATCH /products/{id}/activate` **(added)** | Admin, Manager | – | 200 product | #5 |
| `GET /suppliers` **(added)** | any | – | 200 `[{supplierId, name}]` | #5 |
| `POST /batches` | Admin, Manager, Inventory Staff | `{productId, supplierId, quantity, unit, receivedAt, expiryDate}` | 201 `{batchId, newStock}` | #6 |
| `POST /restocks` | Admin, Manager, Inventory Staff | `{productId, quantity, unit}` | 201 `{newStock}` | #6 |
| `GET /batches/fefo?productId={id}` | any | – | 200 `[{batchId, quantity, unit, supplier, receivedAt, expiryDate, daysInStore, daysToExpiry}]`, expiry ascending, only batches with quantity > 0 **(added: unit, supplier, receivedAt)** | #6 |
| `POST /sales` | Admin, Cashier | `{sku, quantity, unit}` | 201 `{saleId, batchesUsed:[{batchId, qty, expiryDate}], remainingStock, productName, unit, amount}` **(added: expiryDate, productName, unit, amount)** | #7 |
| `POST /sales/csv` | Admin, Cashier | multipart, field `file`; columns `sku,quantity,soldAt` | 200 `{imported, failed, errors:[{line, message}]}` | #7 |

Notes
- **SKU** is the product code used at the till and in CSV files (e.g. `TOM-01`). It must be unique; return 409 if it isn't.
- **Expired stock**: `/batches/fefo` still lists expired batches (the UI marks them "Do not sell") until they are removed.
- **Sales**: 422 with code `INSUFFICIENT_STOCK` or `BATCH_EXPIRED` (FR-7).
- **Restock**: the UI sends no expiry; the backend sets it from the product's shelf-life.

## Sprint 2: dashboard and reports (issue #16)

| Method & path | Who | Response |
|---|---|---|
| `GET /dashboard` **(added)** | Admin, Manager, Inventory Staff | `{salesToday:{count, amount}, stockValue, wasteLast7Days:{value, removals}, lowStock:[{productId, name, stock, threshold, unit}], expiringSoon:[{batchId, productName, quantity, unit, expiryDate, daysToExpiry}] (≤ 2 days, incl. expired), activeAlerts:{count, critical, latest:[alert]}}` |
| `GET /reports/{type}?from=YYYY-MM-DD&to=YYYY-MM-DD` | Admin, Manager | `{type, title, from, to, columns:[{key, label, numeric?}], rows:[{...}], summary:[{label, value}]}`; 400 if from > to; 404 unknown type |

Report `type` values and what each must contain (reference implementation:
`frontend/src/api/mock/reports.js`):

| type | Rows |
|---|---|
| `stock` | per product: on hand, batches, next expiry, value at cost, status |
| `wastage` | per product in range: sold, wasted, waste % = wasted / (sold + wasted), money lost = Σ removal qty × cost price |
| `sellers` | products ranked by revenue, tagged best / worst |
| `supplier-quality` | per supplier: deliveries, units received, units wasted, waste rate % |
| `removals` | every removal: date, product, batch, qty, reason, worker, value |
| `temperature` | per unit per day: allowed range, min / avg / max, readings out of range |
| `power-events` | mains failure start, restored, duration, backup take-over seconds |
| `alerts` | raised time, severity, message, status, acknowledged by |

An empty range returns `rows: []`; the UI shows "No data for this period".
PDF and CSV are generated in the browser from this JSON, so the backend only
returns JSON (the SAD's `format=pdf|csv` parameter is optional).

## Demo mode

`npm run dev` uses a built-in fake backend (`frontend/src/api/mock/`) that follows
this contract, controlled by `VITE_USE_MOCK` in `frontend/.env.development`. Set it to
`false` once the real endpoints are merged. Docker builds always use the real backend.

Demo accounts: `admin/admin123`, `manager1/manager123`, `staff1/staff123`, `cashier1/cashier123`.
