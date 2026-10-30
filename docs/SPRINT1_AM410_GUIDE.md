# Sprint 1 work for PES1UG24AM410 - what was done and how to check it

Tasks: **S1-5 (#7)** Sales: FEFO deduction, block expired batch, manual + CSV
and **S1-2 (#4)** Device API (device key, eventId) and POS/sensor simulators.

---------------------------------------------------------------------------------------------
## 1. What the project already had (before my changes)

| Part | State |
|---|---|
| `frontend/` | Complete React app (login, role menu, products, batches, sales screens). By default it runs on a **built-in mock backend** (`VITE_USE_MOCK=true`), so it never calls the real API yet. |
| `backend/` | Only a skeleton: `GET /api/health` and one test. **No database code, no login, no products/batches tables.** |
| `docs/` | SRS, SAD, architecture, test cases, and `frontend-api-contract.md`, the agreement between frontend and backend. |
| CI / Docker | `docker-compose.yml` (db + backend + frontend), CI running `ruff` and `pytest`. |

The other Sprint 1 tasks (login #3, database schema #5, batches #6) belong to teammates and are
not in the zip. My code therefore needed a few stand-ins (section 4).

## 2. What I added

**S1-5 Sales** (`backend/app/sales/`)
- `POST /api/sales` (Admin, Cashier): one manual sale. Stock is taken from the batch that expires
  first (ties: older batch). A sale can span several batches. Expired batches are never touched.
- `POST /api/sales/csv`: many sales from a file with columns `sku,quantity[,soldAt]`. Good rows are
  imported; bad rows are returned with their line number.
- Whole sale or nothing: if the stock can't cover it, no batch changes (`INSUFFICIENT_STOCK`).
  If all stock is expired: `BATCH_EXPIRED`. Row locks stop two simultaneous sales overselling.
- Every sale stores who recorded it, the price at the time, and which batches it came from.

**S1-2 Device API** (`backend/app/device/`)
- `POST /api/device/sales` (POS devices) and `POST /api/device/readings` (sensors).
- Each device has its own key in header `X-Device-Key` (only a hash is stored). A POS key can't send
  readings and a sensor key can't send sales.
- Every event has an `eventId`. Sending the same one again returns 409 and changes nothing.
- Readings are validated: temperature must be a number (-60..100), door OPEN/CLOSED, power ON/OFF.
  Bad readings are rejected with a message and not stored.
- `simulators/`: `pos_simulator.py`, `sensor_simulator.py`. If the backend is down they save events to
  a file and resend them later without duplicates.

**Shared plumbing**: `config.py`, `db.py`, `models.py` (tables), `errors.py` (error format from the
SAD; malformed requests return 400), `rbac.py` (role check), `dev_seed.py` (dev-only demo data).
Also: 51 tests (`backend/tests/`), docs updated, `.env.example` fixed (see 4), 3 packages added to
`requirements.txt`.

## 3. How to run on Windows + VS Code

### One-time installs
1. **Docker Desktop** (turn on WSL 2 when asked) - for the full app.
2. **Python 3.12** from python.org (tick "Add python.exe to PATH") - for tests and simulators.
3. **VS Code** with the *Python* extension.
4. Unzip the project and open the folder in VS Code (File > Open Folder). Use the terminal
   `Terminal > New Terminal` (PowerShell).

### A. Quickest check: automatic tests (no Docker, no database)
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python -m pytest -q                  # expect: 51 passed
ruff check .                         # expect: All checks passed!
```
In VS Code press `Ctrl+Shift+P` > "Python: Select Interpreter" > pick `backend\.venv`.

### B. Run the real app
From the project root (start Docker Desktop first):
```powershell
copy .env.example .env
docker compose up --build
```
- Web app http://localhost:3000 (still uses demo data in dev mode; the real backend has no login yet)
- API docs http://localhost:8000/docs  <- use this to try my endpoints
- Health http://localhost:8000/api/health

In a **second terminal**, load the demo shop and get login tokens:
```powershell
docker compose exec backend python -m app.dev_seed
```
It prints a Cashier token and an Admin token (valid 8 hours).

### C. Try the Sales API (Swagger, easiest)
1. Open http://localhost:8000/docs, expand **POST /api/sales** > *Try it out*.
2. In the `authorization` box type `Bearer ` followed by the Cashier token.
3. Body examples, and what to expect:

| Body | Expect |
|---|---|
| `{"sku":"TOM-01","quantity":5}` | 201, uses batch of 12 kg (expires first), `remainingStock` 32 |
| `{"sku":"TOM-01","quantity":15}` | 201, `batchesUsed` has two batches |
| `{"sku":"TOM-01","quantity":500}` | 422 `INSUFFICIENT_STOCK` ("only N kg available"), nothing deducted |
| `{"sku":"BRD-01","quantity":1}` | 422 `BATCH_EXPIRED` (bread has only expired stock) |
| `{"sku":"MLK-01","quantity":4}` | 201 from the 30 l batch; the expired 8 l batch is skipped |
| `{"sku":"NOPE","quantity":1}` | 404 Unknown SKU |
| `{"sku":"TOM-01","quantity":0}` | 400 |
| no `authorization` | 401 |

CSV: make `sales.csv` in VS Code:
```
sku,quantity
TOM-01,1
NOPE-1,2
BAN-01,3
```
then **POST /api/sales/csv** > choose the file. Expect `imported 2, failed 1`, error on `line 3`.

### D. Try the Device API and simulators
```powershell
docker compose exec backend python -m app.device.provision pos-sim pos
docker compose exec backend python -m app.device.provision fridge-sensors sensor
```
Each prints a key **once**: copy them. Then, in a terminal at the project root:
```powershell
$env:PMS_DEVICE_KEY = "<the pos key>"
py simulators\pos_simulator.py --count 5 --interval 1
py simulators\pos_simulator.py --once --sku TOM-01 --quantity 2

$env:PMS_DEVICE_KEY = "<the sensor key>"
py simulators\sensor_simulator.py --count 2 --interval 1
py simulators\sensor_simulator.py --once --unit Fridge-1 --type temperature --value abc   # rejected, 400
```
Offline test: start `pos_simulator.py` with no `--count`, run `docker compose stop backend`, wait
10 s, run `docker compose start backend`. The simulator shows `buffered`, then delivers the backlog.
Repeating an eventId can be tried in Swagger on **POST /api/device/sales** with the `x-device-key`
box: send the same `eventId` twice; the second gives 409.

### E. See what was stored
```powershell
docker compose exec db psql -U pms pms -c "select sale_id, sku, quantity, amount, recorded_by from sales"
docker compose exec db psql -U pms pms -c "select batch_id, product_id, quantity, expiry_date from batches order by batch_id"
docker compose exec db psql -U pms pms -c "select unit_id, type, value_num, value_text from sensor_readings"
```
Start clean: `docker compose down -v` (deletes the database).

## 4. Things you must know / may need to adjust

1. **Login (#3):** my endpoints expect an HS256 JWT signed with `JWT_SECRET` and claims `sub`,
   `role`, `name`, `exp`. If #3 issues something else, change only `get_current_user()` in `rbac.py`.
2. **Products and batches (#5, #6):** `Product`, `Batch`, `Supplier` in `models.py` are
   **temporary**. When the teammates merge theirs, delete mine and import theirs (the code only
   needs `sku, name, unit, active, selling_price` on products and `quantity, expiry_date,
   product_id` on batches). Also delete `dev_seed.py`.
3. **Tables** are created automatically at startup (no migration tool in the project yet).
4. **`.env.example` bug fixed:** `DATABASE_URL` used password `change_me` but the database used
   `password`. I also set a default `JWT_SECRET` for local use. Change it for real deployments.
5. **Rules I chose** (tell me if the team wants different):
   - a batch is sellable **through** its expiry date (store timezone, default Asia/Kolkata);
   - expiry is checked against today, not the sale's own `soldAt`;
   - `piece` products need whole numbers; a `unit` that doesn't match the product is a 400;
   - re-uploading the same CSV records the sales twice (CSV rows have no event ID).
6. **Not done:** rate limiting on the Device API, alerts from sensor readings (later sprint:
   `alertRaised` is always false), switching the frontend off mock mode (wait until login exists).

## 5. How I verified it
- 51 automated tests (all pass) mirror the frontend mock's scenarios and the test cases
  TC-STK-04/05/06/10/11/13/14 and TC-REF-05/06/07.
- I broke three rules on purpose (sell expired, wrong order, no stock check) and the tests failed
  each time.
- On a real PostgreSQL 16: 60 simultaneous sales against 38 items gave exactly 38 sold and 22
  refused, stock ended at 0; 20 simultaneous copies of one eventId gave 1 sale and 19 x 409; a
  simulated outage with 9 buffered sales delivered the valid ones in order and logged the rejected.
- **Not tested here:** the Docker image build and the frontend (no Docker in my environment).
  If `docker compose up --build` fails, send me the error text.
