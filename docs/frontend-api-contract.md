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
- `eventId` (string, max 64) must be unique per device. Re-sending a stored event returns **409
  `DUPLICATE_EVENT`** and changes nothing, so senders may retry safely after an outage.
- Errors: 401 `INVALID_DEVICE_KEY`; 403 wrong kind of device for the endpoint; 400 malformed data
  (reading is not stored); sales also return 422 `INSUFFICIENT_STOCK` / `BATCH_EXPIRED`.
- `alertRaised` is always `false` until the Alerts module (later sprint) evaluates readings.

## Demo mode

`npm run dev` uses a built-in fake backend (`frontend/src/api/mock/`) that follows
this contract, controlled by `VITE_USE_MOCK` in `frontend/.env.development`. Set it to
`false` once the real endpoints are merged. Docker builds always use the real backend.

Demo accounts: `admin/admin123`, `manager1/manager123`, `staff1/staff123`, `cashier1/cashier123`.
