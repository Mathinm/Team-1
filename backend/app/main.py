from fastapi import FastAPI

app = FastAPI(title="PMS - Perishables Management System", version="0.1.0")


@app.get("/api/health")
def health():
    """Used by Docker healthcheck, CI and the availability test (NFR-4)."""
    return {"status": "ok"}
