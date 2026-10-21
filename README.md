# PMS - Perishables Management System (Team 1)

FastAPI + PostgreSQL + React, run with Docker.

## Run
    cp .env.example .env
    docker compose up --build

- Web app: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/api/health

## Simulators (POS and sensors)
Both talk to the Device API with a per-device key. Register a device once, then run:

    docker compose exec backend python -m app.device.provision pos-sim pos
    docker compose exec backend python -m app.device.provision fridge-sensors sensor
    export PMS_DEVICE_KEY=<key printed above>
    python simulators/pos_simulator.py        # needs no install, Python 3.10+
    python simulators/sensor_simulator.py

See `simulators/README.md` for options (one-off events, outage buffering).

## Folders
- `backend/` FastAPI
- `frontend/` React
- `simulators/` POS and sensor simulators
- `docs/` SRS, SAD, test cases


## Test
    cd backend && pip install -r requirements.txt && python -m pytest -q
    cd backend && ruff check .
    cd frontend && npm install && npm test && npm run build

## Frontend without the backend
    cd frontend && npm install && npm run dev     # http://localhost:5173

`npm run dev` uses built-in demo data (`VITE_USE_MOCK=true` in `frontend/.env.development`).
Demo logins: admin/admin123, manager1/manager123, staff1/staff123, cashier1/cashier123.
API the screens expect: `docs/frontend-api-contract.md`.

## Workflow
Branch per issue (e.g. `s1-1-auth`), open a PR to `main`; CI must pass before merge.
