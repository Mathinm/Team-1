
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.alerts.router import router as alerts_router
from app.auth.reset import router as reset_router
from app.auth.router import router as auth_router
from app.auth.seed import seed_users
from app.batches.router import router as batches_router
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.device.router import router as device_router
from app.errors import register_error_handlers
from app.markdowns.router import router as markdowns_router
from app.notifications.router import router as notifications_router
from app.notifications.service import run_notification_scheduler
from app.products.router import router as products_router
from app.refrigeration.router import router as refrigeration_router
from app.sales.router import router as sales_router
from app.scheduler import Scheduler
from app.stock.router import router as stock_router
from app.users.router import router as users_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_users(db)

    # Existing scheduler for alerts, low stock and refrigeration.
    scheduler = Scheduler() if get_settings().scheduler_enabled else None
    if scheduler:
        scheduler.start()

    # S2-2 expiry notification scheduler.
    stop_event = asyncio.Event()
    notification_task = (
        asyncio.create_task(run_notification_scheduler(stop_event))
        if get_settings().scheduler_enabled
        else None
    )

    try:
        yield
    finally:
        stop_event.set()
        if notification_task:
            await notification_task

        if scheduler:
            scheduler.stop()


app = FastAPI(
    title="PMS - Perishables Management System",
    version="0.1.0",
    lifespan=lifespan,
)
register_error_handlers(app)

app.include_router(auth_router)
app.include_router(reset_router)
app.include_router(stock_router)
app.include_router(sales_router)
app.include_router(device_router)
app.include_router(users_router)
app.include_router(products_router)
app.include_router(batches_router)
app.include_router(notifications_router)
app.include_router(alerts_router)
app.include_router(refrigeration_router)
app.include_router(markdowns_router)


@app.get("/api/health")
def health():
    """Used by Docker healthcheck, CI and the availability test (NFR-4)."""
    return {"status": "ok"}
