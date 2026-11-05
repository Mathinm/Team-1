# DB-1: Stores table and the migrations decision (issue #32)

## 1. Stores table (NFR-14, TC-SCAL-01)

**Before:** every table had a plain `store_id` integer (default 1), but nothing said what a store
*is*, so a typo like `store_id = 99` was accepted silently.

**Now:** `stores(store_id PK, name, timezone, created_at)` exists and every `store_id` column
(15 tables) is a foreign key to it. The default store (`STORE_ID`, `STORE_NAME`, `STORE_TIMEZONE`
in `.env`) is created by `app/stores.py: ensure_default_store()` when the backend starts, and by
`load_seed`, `dev_seed` and `device.provision`.

Adding a second store is one `INSERT INTO stores ...` and no table changes. This is shown by
`tests/test_stores.py::test_a_second_store_needs_no_schema_change`, which turns foreign keys on in
SQLite so it behaves like PostgreSQL.

Store ids are chosen by us, never auto-generated (`autoincrement=False`), so id 1 cannot collide
with a generated id.

## 2. Migrations decision

| | `create_all` at startup (today) | Alembic migrations |
|---|---|---|
| Setup | none | new folder, env config, one revision per change |
| Changing an existing table | not possible: `create_all` only creates missing tables | scripted and reversible |
| Fit for this project | needs a rule for schema changes | extra tool for a short project; a bad revision can block start-up |

**Decision: keep `create_all` through the Sprint 3 release, with these rules.**
1. Schema changes are additive: new tables, or new columns that are nullable or have a default.
2. A change to an existing table is written in the PR description with its SQL and applied by hand
   on a running database (or the dev database is recreated).
3. Dev and demo databases are throw-away: `docker compose down -v`, then `docker compose up --build`
   rebuilds everything, including the default store row.
4. If this ever becomes a real multi-store product, add Alembic first, starting from the current
   models as revision 0.

A PostgreSQL database created before this change already has its tables. `create_all` will create
`stores` but will not add the foreign keys to the old tables. A fresh database gets them automatically.

## 3. Upgrading an existing PostgreSQL database (optional)

Skip this if you recreate the database. Otherwise start the backend once after updating (so
`stores` and its default row exist), then run:

```sql
ALTER TABLE alerts ADD CONSTRAINT fk_alerts_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE batches ADD CONSTRAINT fk_batches_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE devices ADD CONSTRAINT fk_devices_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE job_runs ADD CONSTRAINT fk_job_runs_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE markdown_rules ADD CONSTRAINT fk_markdown_rules_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE markdowns ADD CONSTRAINT fk_markdowns_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE products ADD CONSTRAINT fk_products_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE refrigeration_units ADD CONSTRAINT fk_refrigeration_units_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE removals ADD CONSTRAINT fk_removals_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE sales ADD CONSTRAINT fk_sales_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE sensor_readings ADD CONSTRAINT fk_sensor_readings_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE stock_counts ADD CONSTRAINT fk_stock_counts_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE suppliers ADD CONSTRAINT fk_suppliers_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
ALTER TABLE users ADD CONSTRAINT fk_users_store FOREIGN KEY (store_id) REFERENCES stores (store_id);
```

If a statement fails with a foreign-key violation, some rows use a store_id that is not in
`stores`. Insert that store first: `INSERT INTO stores (store_id, name) VALUES (<id>, '<name>');`

## 4. Sprint 0 leftovers cleaned up (repo skeleton, #2)
- `.gitignore`: removed `simulators/__pycache__/` (already covered by `__pycache__/`) and
  `pgdata/` (the database lives in the Docker named volume `pgdata`, so no such folder exists).
- `.github/workflows/ci.yml`: the restore test no longer repeats the database user and name
  (`psql -U pms -d pms`); it reads `POSTGRES_USER` and `POSTGRES_DB` from the db container, so
  the credentials are set in one place only (`.env`).
