# ASGI app entry point. Run with:
#   uv run uvicorn api.main:app --reload

from fastapi import FastAPI

from .routes.tech_detection import router as tech_detection_router
from .routes.url_discovery import router as url_discovery_router
from .routes.content_extraction import router as content_extraction_router
from .routes.website_processing import router as website_processing_router

app = FastAPI(
    title="web-graph",
    description="Website technology detection, URL discovery, content extraction, and combined discover+extract API",
    version="0.1.0",
)

app.include_router(tech_detection_router)
app.include_router(url_discovery_router)
app.include_router(content_extraction_router)
app.include_router(website_processing_router)


@app.get("/health")
def health():
    return {"status": "ok"}
