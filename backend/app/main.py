import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.auth.seed import seed_users
from app.db import Base, SessionLocal, engine
from app.device.router import router as device_router
from app.errors import register_error_handlers
from app.sales.router import router as sales_router
from app.users.router import router as users_router

# Show INFO lines from our own loggers (login, audit); uvicorn only sets up its own.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # No migration tool yet: create any missing tables at startup.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_users(db)
    yield


app = FastAPI(title="PMS - Perishables Management System", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(sales_router)
app.include_router(device_router)
app.include_router(users_router)


@app.get("/api/health")
def health():
    """Used by Docker healthcheck, CI and the availability test (NFR-4)."""
    return {"status": "ok"}
