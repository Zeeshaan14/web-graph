# ASGI app entry point. Run with:
#   uv run uvicorn api.main:app --reload

from fastapi import FastAPI

from .routes import router

app = FastAPI(
    title="web-graph",
    description="Website technology detection API",
    version="0.1.0",
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
