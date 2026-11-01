# S2-10 Non-functional requirement checks (#19, #31)

Requirements (SRS v1.0): NFR-1, NFR-2, NFR-3, NFR-4a, NFR-6, NFR-8, NFR-13.

| NFR | What | Test case | Where |
|---|---|---|---|
| NFR-4a | `restart: unless-stopped` and health checks on every service; a crashed container comes back by itself | TC-REL-01 | `docker-compose.yml`, CI job `docker` |
| NFR-13 | Daily `pg_dump` backup and a tested restore | TC-REL-03 | `ops/pms-backup.sh`, service `backup`, CI job `docker` |
| NFR-1 | Stock changes on all screens within 5 s (95%) | TC-PERF-01 | `frontend/src/lib/liveRefresh.js`, `perf/stock_latency.py` |
| NFR-2 | Alerts reach staff within 60 s (95%) | TC-PERF-02 | `EXPIRY_CHECK_SECONDS`, `perf/alert_latency.py` |
| NFR-3 | 50 users, 5,000 batches, 100 sensors, targets still met | TC-PERF-03 | `backend/app/load_seed.py`, `perf/locustfile.py` |

## NFR-4a Restart policy and health checks (TC-REL-01)

Every service in `docker-compose.yml` has `restart: unless-stopped` (Docker restarts it after a
crash, but not after you stop it yourself) and a health check:

| Service | Health check | Healthy means |
|---|---|---|
| db | `pg_isready` | PostgreSQL accepts connections |
| backend | Python opens `http://127.0.0.1:8000/api/health` | the API answers 200 |
| frontend | `wget --spider http://127.0.0.1/` | nginx serves the web app |
| backup | `.last_success` is less than 25 hours old | a backup succeeded in the last day |

The backend starts only when db is healthy, and the frontend only when the backend is healthy.
The database password is set once (`POSTGRES_PASSWORD`); the backend's `DATABASE_URL` is built
from it (#31).

**Automated test:** the CI job `docker` starts the stack, waits until every service is healthy,
then crashes each container with `kill -9` and checks it is healthy again with a higher restart
count. Look for lines like `backend: restarts 0 -> 1, health healthy, back after ~12 s`.

**By hand** (Docker Desktop running, project folder):
```powershell
docker compose up -d --build
docker compose ps                                   # STATUS shows (healthy) for all four
docker compose exec backend sh -c "kill -INT 1"     # make the backend's main process exit
Start-Sleep 30; docker compose ps                   # backend is back and (healthy)
```
Don't use `docker kill` or `docker stop` for this test: Docker counts those as stopped on
purpose and, with `unless-stopped`, leaves the container down.

## NFR-13 Daily backup and tested restore (TC-REL-03)

**How it works.** The `backup` service runs `ops/pms-backup.sh loop`. Every minute it checks
whether a backup is due and, if so, runs `pg_dump --format=custom` into `./backups` (a folder
in the project, ignored by git). A backup is due:
- at `BACKUP_TIME` (default 02:00 store time) if today's backup is not done yet,
- straight away if the newest backup is older than yesterday (the computer was off at 02:00),
- straight away on the very first start.

Files are named `pms_YYYY-MM-DD_HHMMSS.dump`; backups older than `BACKUP_KEEP_DAYS` (default 7)
are deleted. A failed dump leaves no file behind and is retried a minute later. The backups are
in a normal folder, not a Docker volume, so `docker compose down -v` does not delete them. For a
real store, also copy `./backups` to another machine or cloud drive.

**Take a backup now / see backups**
```powershell
docker compose exec backup sh /scripts/pms-backup.sh now
docker compose exec backup sh /scripts/pms-backup.sh list
```

**Restore** (replaces everything in the database with the backup):
```powershell
docker compose stop backend                         # no app writing while we restore
docker compose exec backup sh /scripts/pms-backup.sh restore pms_2026-11-01_020000.dump
docker compose start backend
```
The script refuses to restore while the backend is still connected. The restore runs in one
transaction: if anything fails, the database stays exactly as it was.

**Tested restore.** The CI job `docker` (step "TC-REL-03") does a full drill on every push:
1. counts the users and lists their login IDs,
2. takes a backup,
3. wipes the database (`DROP SCHEMA public CASCADE`), checks 0 tables are left,
4. stops the backend, restores the backup, starts the backend,
5. checks the same users are back and `cashier1` can log in through the web server.

Before handing in, also do the drill once by hand with the commands above and screenshot
`list`, the restore output and a successful login.

## Performance checks: test data and tools (NFR-1, NFR-2, NFR-3)

All three use the same test data and run against the real stack (backend, PostgreSQL, nginx).

```powershell
docker compose up -d --build
# 100 products x 50 batches = 5,000 batches, 100 sensors, 50 users, a POS; prints keys as JSON
docker compose exec -T backend python -m app.load_seed --yes > perf\seed.json
py -m venv perf\.venv; perf\.venv\Scripts\pip install -r perf\requirements.txt
```
`perf/seed.json` holds device keys: it is in `.gitignore`, never commit it. The seed is safe to
run again (it only adds what is missing and gives the devices new keys). Use port 3000 (nginx,
what browsers use) or 8000 (backend directly) in `--base` / `--host` below.

The CI job `docker` runs all three on every push (Locust for 3 minutes instead of 15) and keeps
the Locust HTML report as a download ("Artifacts", `locust-report`).

## NFR-1 Stock changes visible on all screens within 5 s (TC-PERF-01)

**Problem found.** The Products and Stock screens loaded their data once, when opened. A sale on
the POS or another screen only appeared after a manual reload, so NFR-1 was not met however fast
the backend was.

**Change.** `frontend/src/lib/liveRefresh.js` (hook `useLiveRefresh`) reloads a screen's data
every `LIVE_REFRESH_MS` = 3,000 ms; Products and Stock & FEFO use it. It pauses while the browser
tab is hidden (and reloads at once when shown again) and never starts a reload while one is
still running. The Stock screen refreshes quietly (no spinner) and ignores a late answer for a
product that is no longer selected.

**Why it meets 5 s.** A change made just after a reload appears at the next one: at most 3 s plus
one request (10-50 ms measured). Average about 1.5 s. Polling was chosen over WebSockets: it is a
few lines, works through nginx unchanged, and 3 s is well inside the target.

**Faster products list.** Every open screen now asks for `GET /api/products` every 3 s. It used to
run one stock query per product (106 queries for the test data, about 65 ms); it now gets all
stock totals in one grouped query (about 10 ms), with the same results. Test:
`test_nfr3_products_list_query_count_does_not_grow_with_products`.

**Test** (the test case: 2 screens, 100 sales from the simulator):
```powershell
perf\.venv\Scripts\python perf\stock_latency.py --base http://localhost:3000 --seed perf\seed.json
```
Two "screens" log in as different users and reload the products list every 3 s like the web app;
100 POS sales of LT-001 are sent one per second; for every sale and screen it measures the time
until that screen shows the new stock. PASS = at least 95% within 5 s on every screen. It also
reports how many were within 3 s (the older test-case document's figure).

| Measured (development machine, 1 Nov 2026) | Within 5 s | Median | Max |
|---|---|---|---|
| 2 screens, 20 sales, no other load | 100% | 1.4-1.5 s | 3.0 s |
| 2 screens, 60 sales, during the 51-user Locust load | 100% | 1.6-1.8 s | 3.0 s |
| Real browser (Chromium), Products + Stock screens, 10 sales, under load | 100% | 1.5-1.7 s | 2.9 s |

## NFR-2 Alerts reach staff within 60 s (TC-PERF-02)

**How an alert travels.** Low-stock (sale), temperature and unit-failure (sensor reading) alerts
are raised in the same request. Expiry alerts are raised by the expiry check. The scheduler then
sends new alerts every `SCHEDULER_INTERVAL_SECONDS` (10 s) and the Alerts screen reloads every
10 s.

**Problem found.** The expiry check ran every 60 s (fixed in the code), so an expiry alert could
take 60 + 10 = 70 s to be sent, and 80 s to be on screen. Now `EXPIRY_CHECK_SECONDS` (default 20)
sets it: worst case 20 + 10 = 30 s sent, 40 s on screen. Test:
`test_nfr2_worst_case_alert_time_is_within_60_s` adds up the waits from the real settings.

**Test** (the test case: 20 alerts of 4 kinds):
```powershell
perf\.venv\Scripts\python perf\alert_latency.py --base http://localhost:3000 --seed perf\seed.json
```
Sends 5 x temperature 15 C, 5 x power OFF, 5 x sales taking LS-n below its threshold, 5 x a batch
received that expires today. From each trigger it measures the time until the alert is
**delivered** (notification sent) and until it is **on the Alerts screen** (in the list, plus one
10 s screen refresh). PASS = 95% of both within 60 s. Afterwards it puts the fridges and LS
products back to normal.

| Measured (development machine, 1 Nov 2026) | Delivered: median / max | On screen: median / max | Within 60 s |
|---|---|---|---|
| 20 alerts, `EXPIRY_CHECK_SECONDS=20` | 5.3 s / 18.5 s | 10.5 s / 28.5 s | 20/20 |
| 8 alerts, old fixed 60 s expiry check | expiry alerts 56-60 s | expiry alerts up to 69 s | 6/8 on screen |

## NFR-3 Load test: 50 users, 5,000 batches, 100 sensors (TC-PERF-03)

**Load** (`perf/locustfile.py`): 25 Inventory Staff (products every few seconds, FEFO lists,
alerts, fridges, restocks), 25 Cashiers (products, sales) and the 100 sensors (one reading each
every 30 s). LT-001 is left alone so TC-PERF-01 can run during the load.

**Targets.** No failed requests (TC-PERF-03 "no errors"), and 95% of requests within 2,000 ms:
with a 3 s screen refresh, that keeps stock changes within NFR-1's 5 s. Locust exits with code 1
when a target is missed. Run TC-PERF-01 in a second window during the load to confirm NFR-1.

```powershell
perf\.venv\Scripts\locust -f perf\locustfile.py --host http://localhost:3000 --headless -u 51 -r 1 -t 15m --html locust-report.html
```
`-u 51` = 50 people + the sensor fleet; `-r 1` = one person logs in per second. Leave out
`--headless` to watch live charts at http://localhost:8089.

**Finding: everyone logging in at once.** With `-r 10` (50 logins within 5 s) logins took 3-6 s
and briefly slowed other requests: each login checks the password with argon2id, which is slow
on purpose (NFR-9). Spread over 50 s (`-r 1`, closer to a shift starting) a login takes about
180 ms and nothing slows down.

| Measured (development machine, 1 Nov 2026, 1 backend process) | Requests | Failed | Median | 95th | Max |
|---|---|---|---|---|---|
| 2 min, `-r 1` | 2,816 | 0 | 17 ms | 36 ms | 230 ms |
| 15 min, `-r 1` | 24,671 | 0 | 17 ms | 34 ms | 270 ms |

Before handing in, run it once by hand for 15 minutes and keep `locust-report.html`.
