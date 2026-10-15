# PMS - Perishables Management System (Team 1)

FastAPI + PostgreSQL + React, run with Docker.

## Run
    cp .env.example .env
    docker compose up --build

- Web app: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/api/health

## Folders
- `backend/` FastAPI
- `frontend/` React
- `simulators/` POS and sensor simulators
- `docs/` SRS, SAD, test cases


## Test
    cd backend && pip install -r requirements.txt && python -m pytest -q
    cd backend && ruff check .
    cd frontend && npm install && npm run build

## Workflow
Branch per issue (e.g. `s1-1-auth`), open a PR to `main`; CI must pass before merge.
