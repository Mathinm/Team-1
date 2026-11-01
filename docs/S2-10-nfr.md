# S2-10 Non-functional requirement checks (#19, #31)

Requirements (SRS v1.0): NFR-1, NFR-2, NFR-3, NFR-4a, NFR-6, NFR-8, NFR-13.

| NFR | What | Test case | Where |
|---|---|---|---|
| NFR-4a | `restart: unless-stopped` and health checks on every service; a crashed container comes back by itself | TC-REL-01 | `docker-compose.yml`, CI job `docker` |
| NFR-13 | Daily `pg_dump` backup and a tested restore | TC-REL-03 | `ops/pms-backup.sh`, service `backup`, CI job `docker` |

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
