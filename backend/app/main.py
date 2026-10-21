from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine
from app.device.router import router as device_router
from app.errors import register_error_handlers
from app.sales.router import router as sales_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # No migration tool yet: create any missing tables at startup.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="PMS - Perishables Management System", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(sales_router)
app.include_router(device_router)


@app.get("/api/health")
def health():
    """Used by Docker healthcheck, CI and the availability test (NFR-4)."""
    return {"status": "ok"}
