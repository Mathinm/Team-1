# Sprint 2 work for PES1UG24AM410 - S2-4 (#13), S2-5 (#14), S2-6 (#15)

| Task | What it delivers | SRS / SAD |
|---|---|---|
| **S2-4 (#13)** Low-stock and projected low-stock alerts | Alerts module (table, list, acknowledge, delivery), immediate LOW_STOCK, daily PROJECTED_LOW_STOCK | FR-10, FR-11, NFR-2, UC-21/22/24/33, SAD Alerts + Scheduler |
| **S2-5 (#14)** Fridge failure and door-open alarms | Unit state from sensor readings, UNIT_FAILURE / DOOR_OPEN / TEMPERATURE alerts, refrigeration screen API | FR-15, FR-16, FR-17, UC-31/32/34, SAD flow 3 |
| **S2-6 (#15)** Offline buffering, sync, 30-min outage test | Hardened simulator buffer, late-data-safe alert logic, automated + real-time 30-minute outage tests | FR-19, NFR-5, UC-29, TC-REP-06/07, TC-NFR-07 |

## 1. What was added (all new code is in new files; existing files got 1-3 line hooks)

New backend modules
- `app/alerts/` - `service.py` (raise/resolve alerts, low-stock rules, daily job), `notifier.py` (Notification interface, simulated gateway, retries), `router.py` + `schemas.py` (`GET /api/alerts`, `POST /api/alerts/{id}/acknowledge`, `POST /api/alerts/run-low-stock-check`).
- `app/refrigeration/` - `service.py` (reading -> unit state + alerts), `router.py` (`GET /api/refrigeration/units`, `PUT /api/refrigeration/units/{unitId}` door limit and temperature range).
- `app/scheduler.py` - background loop every 10 s: open doors, daily low-stock check, alert delivery.
- `app/models.py` - 3 new tables at the end: `alerts`, `refrigeration_units`, `job_runs` (created automatically at startup; no existing table changed).
- `app/config.py` - new optional settings (see `.env.example`).

Small hooks in existing files (search for `refresh_after_change` / `apply_reading`)
- `sales/fefo.py`, `stock/router.py` (removal, stock count), `batches/router.py` (batch, restock), `products/router.py` (edit, activate/deactivate): call `refresh_after_change` so stock changes raise or close LOW_STOCK in the same transaction. It never raises, so a sale is never blocked by an alert problem.
- `device/router.py`: after storing a reading, `apply_reading`; `alertRaised` is now real.
- `main.py`: routers + scheduler start/stop. `tests/conftest.py`: `SCHEDULER_ENABLED=false`.

Simulators: `device_client.py` (append-only crash-safe buffer, strict ordering, tolerant of a corrupt last line, fewer rewrites, `pending_count()`), `sensor_simulator.py` (`--ago`), `outage_test.py` (new).

Docs: `docs/frontend-api-contract.md` (new "Sprint 2 - Alerts and refrigeration" section: **Mathin needs this for S2-7/S2-8**), `simulators/README.md`.

## 2. Rules I chose (change if the team wants otherwise)
- Low stock uses total on hand (same number as the Products screen). Exactly at the threshold is NOT an alert (TC-LOW-05). Threshold 0 never alerts.
- Projection: `stock - (sold in last 7 days / 7) < threshold` while stock is still >= threshold. Runs daily at `LOW_STOCK_CHECK_TIME` (06:00 store time), once per day even across restarts, or on demand.
- The Device API has only temperature/door/power (SAD 4.3), so "unit failed" = `power OFF` reading. Temperature outside 0-8 C (per-unit override) is a separate TEMPERATURE alert.
- Door limit default 5 min, per-unit override (FR-16 "configured threshold").
- Who is notified: active Managers by email (simulated: written to the backend log). Who acknowledges: Manager/Admin. Who can view: Admin, Manager, Inventory Staff.
- Offline: all timing uses the reading's own `recordedAt`. A door open 1 min raises nothing; open 10 min and reported late raises the alarm and closes it, with the original time.
- Known limit: if a door OPEN reached the server and its CLOSED is held back by an outage, the alarm appears after the limit (the server cannot know) and closes itself when the CLOSED arrives.

## 3. Coordinate with the team (important)
- **Alerts table is shared.** #11 (Expiry notifications, pandu2006-28) and #17 (frontend alerts, Mathinm) should USE this module, not create another: call `raise_alert(db, type=..., key=..., message=..., ...)` and `resolve_alert(...)` from `app/alerts/service.py`; add a scheduler job with one line in `JOBS` in `app/scheduler.py`; add recipients with a line in `RECIPIENT_ROLES` in `alerts/notifier.py`. Merge this PR first, or tell them before they start.
- #17 frontend: endpoints and fields are in the contract doc. The menu in `rbac.py` `ROLE_MENUS` has no alerts/refrigeration entry yet; whoever builds the screens adds it (and in `frontend/src/config/roles.js`).

## 4. Windows + VS Code + Git: what to do

### A. Get the code in
1. Open PowerShell in your clone of the repo (VS Code: Terminal > New Terminal).
2. `git checkout main` then `git pull`
3. One branch per task is the team rule, but these three share the Alerts module, so use one branch:
   `git checkout -b s2-4-5-6-alerts-refrigeration-offline`
4. Unzip `sprint2-am410-changes.zip` **into the project root, choose Replace for existing files**. It contains only new/changed files, same folder layout.
5. VS Code Source Control (Ctrl+Shift+G) should list the changed files; glance through them.

### B. Check it (no Docker needed)
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python -m pytest -q               # expect: 240 passed
ruff check .                      # expect: All checks passed!
```
The 30-minute outage is also tested here in seconds: `python -m pytest tests/test_offline_sync.py -v`.

### C. Run the real system and try it
```powershell
cd ..                              # project root
copy .env.example .env             # skip if .env exists
docker compose up --build          # Docker Desktop must be running
```
Second terminal:
```powershell
docker compose exec backend python -m app.dev_seed
docker compose exec backend python -m app.device.provision pos-sim pos
docker compose exec backend python -m app.device.provision fridge-sensors sensor
```
Keys are shown once: copy them. Open http://localhost:8000/docs, log in via **POST /api/auth/login** as `manager1` / `manager123` and use the token with the Authorize button (`Bearer <token>` in the `authorization` field of each call).

| Test case | Do | Expect |
|---|---|---|
| TC-LOW-04 | `$env:PMS_DEVICE_KEY="<pos key>"; py simulators\pos_simulator.py --once --sku TOM-01 --quantity 30` (stock 37) | `GET /api/alerts` shows LOW_STOCK "Tomato is low: 7 kg left", delivered; backend log shows a `NOTIFY` line within ~10 s |
| TC-LOW-05 | `docker compose down -v`, reseed, sell 27 | no alert at exactly 10; one more kg -> alert |
| TC-LOW-01..03 | Swagger **POST /api/alerts/run-low-stock-check** after selling a few days' worth (or the automated tests `tests/test_alerts.py`) | PROJECTED_LOW_STOCK "projected below 10 tomorrow" |
| TC-REF-01 | `$env:PMS_DEVICE_KEY="<sensor key>"; py simulators\sensor_simulator.py --once --unit Fridge-2 --type power --value OFF` | `GET /api/refrigeration/units`: Fridge-2 FAILED; critical UNIT_FAILURE alert |
| TC-REF-02 | same with `--value ON` | Fridge-2 OK, alert `resolved`, resolution "Power restored..." |
| TC-REF-03 | `... --unit Fridge-1 --type door --value OPEN --ago 600` | DOOR_OPEN alarm within ~10 s ("open for 10 min (limit 5 min)") |
| TC-REF-04 | `PUT /api/refrigeration/units/Fridge-1` `{"doorOpenLimitMinutes":2}`, then OPEN `--ago 60`, then CLOSED | no alarm |
| UC-33 | **POST /api/alerts/{id}/acknowledge** as manager1 | status `acknowledged`, acknowledgedBy `manager1`; as `cashier1` -> 403 |
| TC-REP-06/07 | run `pos_simulator.py` (no `--count`), `docker compose stop backend`, wait 30 s, `docker compose start backend` | "buffered" then everything delivered, no duplicates |
| **TC-NFR-07 (30 min)** | `$env:PMS_POS_KEY="<pos key>"; $env:PMS_SENSOR_KEY="<sensor key>"; py simulators\outage_test.py --minutes 2 --interval 2` rehearsal, then `--minutes 30` | all lines PASS, `RESULT: PASS`. Screenshot it for the report |

Look inside the database: `docker compose exec db psql -U pms pms -c "select alert_id,type,status,delivery_status,message from alerts"`.

### D. Commit and open the PR
```powershell
git add -A
git status                         # make sure no .env, .venv or *.jsonl are listed
git commit -m "S2-4/S2-5/S2-6: alerts, low-stock, fridge and door alarms, offline sync (#13 #14 #15)"
git push -u origin s2-4-5-6-alerts-refrigeration-offline
```
On GitHub open the PR to `main`, body: `Closes #13, closes #14, closes #15`. CI (ruff, pytest, frontend build) must be green. In the Sprint board the three items move to Done when the PR merges.

## 5. How it was verified
- 240 tests pass (184 before, 56 new). Three rules were broken on purpose (alert at threshold, door time from arrival time, old reading overwriting new) and the tests failed each time.
- On a real PostgreSQL 16 with the real simulators: low-stock, unit-failure, temperature and door alerts raised, delivered in about 1 s; events buffered while the backend was down were delivered after it came back; a 1-minute run of `outage_test.py` (stop/start backend) gave 66 of 66 events stored once, stock exact.
- Not tested here: the Docker image build, the frontend, and the full 30-minute real-time run (the same logic is covered by the simulated 30-minute test and the 1-minute real run).
