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
| `POST /auth/login` | public | `{userId, password, otpCode?}` | 200 `{token, role, expiresIn, name, userId}` **(added: name, userId)**; 401 wrong credentials; 423 `ACCOUNT_LOCKED` after 5 wrong passwords in a row; **Manager/Admin: right password without `otpCode` emails a 6-digit code and answers 401 `OTP_REQUIRED` with `details.sentTo` (masked email); wrong, used or expired code 401 `INVALID_OTP`** | #3, #18 |
| `POST /auth/logout` | any | – | 204 | #3 |
| `GET /auth/me` **(added)** | any | – | 200 `{userId, name, role, menu[]}` (`menu` = screens the role may open) | #3 |
| `POST /auth/password-reset` **(added)** | public | `{userId}` | 202 `{message}` (same answer for unknown users); emails `{FRONTEND_URL}/reset-password?token=...` | #18 |
| `POST /auth/password-reset/confirm` **(added)** | public | `{token, newPassword}` | 200 `{message}`; 400 `RESET_LINK_INVALID` (unknown, used or expired link) | #18 |
| `GET /users` | Admin | – | 200 `[{userId, name, email, role, active, storeId}]` (name/email stored encrypted, returned readable; each read audit-logged) | #3, #18 |
| `POST /users` | Admin | `{userId, name, email, role, password}` | 201 user; 409 `USER_EXISTS` | #3 |
| `PUT /users/{userId}` | Admin | `{name?, email?, role?}` | 200 user | #3 |
| `PATCH /users/{userId}/deactivate` / `activate` | Admin | – | 200 user | #3 |
| `PATCH /users/{userId}/unlock` **(added)** | Admin | – | 200 user; users now include `locked` | #18 |
| `GET /products` **(added)** | any | – | 200 `[{productId, sku, name, category, unit, shelfLifeDays, storageType, tempMin, tempMax, costPrice, sellingPrice, lowStockThreshold, active, stock}]` (`stock` = total on hand) | #5 |
| `POST /products` | Admin, Manager | product fields + **`sku` (added)** | 201 product | #5 |
| `PUT /products/{id}` | Admin, Manager | product fields | 200 product | #5 |
| `PATCH /products/{id}/deactivate` | Admin, Manager | – | 200 product | #5 |
| `PATCH /products/{id}/activate` **(added)** | Admin, Manager | – | 200 product | #5 |
| `GET /suppliers` **(added)** | any | – | 200 `[{supplierId, name}]` | #5 |
| `POST /suppliers` **(added)** | Admin, Manager | `{name}` | 201 `{supplierId, name}`; 409 `DUPLICATE_SUPPLIER` if the name exists (ignoring case and extra spaces); 400 empty or > 120 characters | #30 |
| `POST /batches` | Admin, Manager, Inventory Staff | `{productId, supplierId, quantity, unit, receivedAt, expiryDate}` | 201 `{batchId, newStock}` | #6 |
| `POST /restocks` | Admin, Manager, Inventory Staff | `{productId, quantity, unit}` | 201 `{newStock}` | #6 |
| `GET /batches/fefo?productId={id}` | any | – | 200 `[{batchId, quantity, unit, supplier, receivedAt, expiryDate, daysInStore, daysToExpiry}]`, expiry ascending, only batches with quantity > 0 **(added: unit, supplier, receivedAt)** | #6 |
| `POST /sales` | Admin, Cashier | `{sku, quantity, unit}` | 201 `{saleId, batchesUsed:[{batchId, qty, expiryDate}], remainingStock, productName, unit, amount}` **(added: expiryDate, productName, unit, amount)** | #7 |
| `POST /sales/csv` | Admin, Cashier | multipart, field `file`; columns `sku,quantity,soldAt` | 200 `{imported, failed, errors:[{line, message}]}` | #7 |

## Sprint 2 — Stock management (issue #10)

| Method & path | Who (SEC-2) | Request | Response | Owner issue |
|---|---|---|---|---|
| `POST /removals` **(added)** | Admin, Manager, Inventory Staff | `{batchId, qty, reason}`; reason 1–40 characters, e.g. Damaged, Temperature breach, Other | 201 `{removalId, batchId, qty, reason, recordedBy, recordedAt, remainingQuantity}`; 400 invalid input; 404 unknown batch; 422 `INSUFFICIENT_STOCK` if quantity exceeds available stock | #10 |
| `POST /stock-counts` **(added)** | Admin, Manager, Inventory Staff | `{batchId, countedQuantity, reason}`; `countedQuantity` ≥ 0; reason 1–255 characters | 201 `{stockCountId, batchId, systemQuantity, countedQuantity, variance, reason, recordedBy, recordedAt}`; variance = counted − system; batch quantity updated to counted quantity; 400 invalid input; 404 unknown batch | #10 |

## Sprint 2 — Alerts and refrigeration (issues #13, #14, #15)

Alerts are created only by the backend (ADR-7). Roles: view = Admin, Manager, Inventory Staff;
acknowledge / settings / run-check = Admin, Manager. Cashier gets 403.

| Method & path | Request | Response |
|---|---|---|
| `GET /alerts?status=&type=&limit=` | `status` = `active` (needs attention), `acknowledged`, `resolved`, `open` (= active + acknowledged, the problem still exists), `all` (default); `limit` 1-500 (default 200) | 200 `[Alert]`, newest first; 400 bad `status` |
| `POST /alerts/{id}/acknowledge` | – | 200 `Alert` (`status: acknowledged`, `acknowledgedBy`, `acknowledgedAt`). Repeating is harmless; a resolved alert stays `resolved`. 404 unknown id |
| `POST /alerts/run-low-stock-check` | – | 200 `{raised, resolved}`; runs the daily projected low-stock check now |
| `GET /refrigeration/units` | – | 200 `[Unit]` of every fridge that has reported, by `unitId` |
| `PUT /refrigeration/units/{unitId}` | `{doorOpenLimitMinutes?: 1-240, tempMin?, tempMax?}` | 200 `Unit`; 400 invalid (min must be below max); 404 unknown unit |

`Alert` = `{alertId, type, severity, message, productId|null, unitId|null, status, triggeredAt,
createdAt, acknowledgedBy|null, acknowledgedAt|null, resolvedAt|null, resolution|null,
deliveryStatus, deliveredAt|null}`

- `type`: `LOW_STOCK`, `PROJECTED_LOW_STOCK`, `UNIT_FAILURE`, `DOOR_OPEN`, `TEMPERATURE` (other modules add their own, e.g. expiry).
- `severity`: `info` / `warning` / `critical`. `deliveryStatus`: `pending` / `sent` / `failed` / `skipped` (informational; the alert is always visible).
- `message` is a sentence for staff, e.g. "Tomato is low: 8 kg left (threshold 10)", "Fridge-2 failed: power lost".
- An alert closes by itself (`status: resolved`, `resolution` says why) when the problem ends: stock back at or above the threshold, power restored, door closed, temperature back in range. Resolved alerts stay in the history.

`Unit` = `{unitId, status: "OK"|"FAILED", power: "ON"|"OFF"|null, door: "OPEN"|"CLOSED"|null,
doorOpenSince|null, temperature|null, temperatureAt|null, lastReadingAt|null, lastReceivedAt|null,
doorOpenLimitMinutes, tempMin, tempMax, openAlerts}`

Rules:
- **Low stock (FR-11):** stock below `lowStockThreshold` (exactly equal is fine) raises `LOW_STOCK` at once after a sale, removal, stock count, batch/restock or threshold edit. "Stock" = everything on hand, the same `stock` number as `GET /products`.
- **Projected (FR-10):** once a day (`LOW_STOCK_CHECK_TIME`, default 06:00 store time), an item whose `stock - average daily sales of the last 7 days` is below the threshold raises `PROJECTED_LOW_STOCK` ("Tomato projected below 10 tomorrow").
- **Fridge failure (FR-15):** a `power OFF` reading makes the unit `FAILED` and raises a critical `UNIT_FAILURE`; `power ON` makes it `OK` and closes the alert.
- **Door (FR-16):** open longer than `doorOpenLimitMinutes` (default 5) raises `DOOR_OPEN`; closing closes it.
- **Temperature:** a reading outside `tempMin`..`tempMax` (default 0-8 °C) raises a critical `TEMPERATURE` alert.
- **Delivery:** new alerts are sent to the active Managers' emails within about 10 s and retried up to 5 times; delivery is simulated (written to the backend log).
- **Offline sync:** readings are judged by their own `recordedAt`, so data that arrives late gives the same alerts as live data.
- `POST /device/readings` now answers `alertRaised: true` when that reading raised an alert (it was always `false` before).

## Notes

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
## Batches behaviour (issue #6)

- `POST /batches` (Admin, Manager, Inventory Staff): `{productId, supplierId, quantity, unit?, receivedAt, expiryDate}`
  -> 201 `{batchId, newStock}`. `receivedAt` without a timezone is store time. The expiry date may not be
  before the day the batch was received (400 "Expiry date must be after received date"); a batch that
  expires on the day it arrives is allowed.
- `POST /restocks` (same roles): `{productId, quantity, unit?, supplierId?}` -> 201 `{batchId, newStock}`.
  A restock is a new batch received now; expiry = today + the product's shelf-life. Without `supplierId`
  the supplier of the product's latest batch is used (400 if the product has never had a batch).
- Both: quantity > 0 with at most 3 decimals, `piece` products need whole numbers, `unit` (if sent) must
  match the product (`UNIT_MISMATCH`). 404 unknown product, 400 unknown supplier, 422 `INACTIVE` for a
  deactivated product, 403 for Cashier.
- `GET /batches/fefo?productId=` (any logged-in user): batches with stock, expired ones included,
  earliest expiry first (ties: older batch first). `daysInStore` and `daysToExpiry` are whole store
  calendar days; `daysToExpiry` < 0 means expired. 404 unknown product, 400 without `productId`.

## Sales behaviour (issue #7)

- Stock is taken **earliest expiry first**; ties go to the older batch. A batch is sellable
  **through its expiry date** (store calendar day, `STORE_TIMEZONE`), so "expires today" can still be sold.
- Whole sale or nothing: if it can't be covered, no batch changes.
- `422 BATCH_EXPIRED` when stock exists but all of it is expired; `422 INSUFFICIENT_STOCK` when the
  quantity is more than the unexpired stock ("Insufficient stock: only 30 l available");
  `422 INACTIVE` for a deactivated product; `404` unknown SKU (SKU matching ignores case/spaces).
- `400`: quantity not > 0 or more than 3 decimals; `piece` products need a whole number; `unit`, if sent,
  must match the product's unit (`UNIT_MISMATCH`). Malformed bodies also return **400** (not FastAPI's 422)
  with `error.code = "VALIDATION"`.
- `remainingStock` = total on hand across all batches (same number as `stock` in `GET /products`).
- CSV: header names are case-insensitive, UTF-8 (Excel BOM ok), `soldAt` optional (`2026-10-20` or
  `2026-10-20T14:30`, no timezone = store time), max 1 MB / 5000 rows. Each row is independent;
  `errors[].line` is the line in the file (header = line 1).
- Roles: `/sales` and `/sales/csv` need a session token with role Admin or Cashier (401 / 403 otherwise).
  Tokens are HS256 JWTs signed with `JWT_SECRET`, claims `sub` (userId), `role`, `name`, `exp`.

## Device API (issue #4; SAD 4.3)

For the POS and sensor simulators (and later real devices). No login token: send the device key in
header `X-Device-Key`. Get a key with `python -m app.device.provision <name> <pos|sensor>`.

| Method & path | Device kind | Request | Response |
|---|---|---|---|
| `POST /device/sales` | pos | `{eventId, sku, quantity, unit?, soldAt?}` | 201, same body as `POST /sales` |
| `POST /device/readings` | sensor | `{eventId, unitId, type, value, recordedAt}` | 200 `{status:"stored", alertRaised}` |

- `type` / `value`: `temperature` = number in °C (-60..100); `door` = `OPEN` or `CLOSED`; `power` = `ON` or `OFF`.
- `eventId` (string, max 64) must be unique per device. Re-sending a stored event returns **409 `DUPLICATE_EVENT`** and changes nothing, so senders may retry safely after an outage.
- Errors: 401 `INVALID_DEVICE_KEY`; 403 wrong kind of device for the endpoint; 400 malformed data (reading is not stored); sales also return 422 `INSUFFICIENT_STOCK` / `BATCH_EXPIRED`.
- `alertRaised` is `true` when the reading raised an alert (see Sprint 2 — Alerts and refrigeration).

## Sprint 2: alerts and refrigeration screens (issue #17)

The Alerts and Refrigeration screens use the backend endpoints above (issues #11, #13-#15) plus one
added for the temperature chart:

| Method & path | Who | Request | Response |
|---|---|---|---|
| `GET /refrigeration/units/{unitId}/readings?hours=24` **(added)** | Admin, Manager, Inventory Staff | `hours` 1-168 (default 24) | 200 `[{recordedAt, value}]` temperature readings by the sensor's own time, oldest first; 404 unknown unit; 400 bad `hours` |

- The screens poll `GET /alerts` every 10-15 s, which keeps alerts on screen within NFR-2's 60 s. Tabs: active, acknowledged, resolved, all.
- Alert types shown with a label: `LOW_STOCK`, `PROJECTED_LOW_STOCK`, `PRE_EXPIRY`, `EXPIRY`, `STOCK_REMOVAL`, `UNIT_FAILURE`, `DOOR_OPEN`, `TEMPERATURE`; any other type is shown as it is.
- `frontend/src/api/normalize.js` turns backend alerts and units into the screens' shape (e.g. `door: "OPEN"` -> door-open flag, temperature vs `tempMin`/`tempMax` -> out-of-range flag).
- Demo mode only: the Refrigeration page has buttons that simulate sensor readings to show alerts being raised.

## Demo mode

`npm run dev` uses a built-in fake backend (`frontend/src/api/mock/`) that follows this contract, controlled by `VITE_USE_MOCK` in `frontend/.env.development`. Set it to `false` once the real endpoints are merged. Docker builds always use the real backend.

Demo accounts: `admin/admin123`, `manager1/manager123`, `staff1/staff123`, `cashier1/cashier123`.
