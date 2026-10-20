from fastapi import FastAPI
from app.routers import products, stores

app = FastAPI(
    title="Perishables Management System API",
    version="1.0.0",
    description="Store-scoped product master data APIs (S1-3 / Issue #5)",
)
app.include_router(stores.router, prefix="/api")
app.include_router(products.router, prefix="/api")


@app.get("/health", tags=["health"])
@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
