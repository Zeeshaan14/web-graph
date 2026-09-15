# ASGI app entry point. Run with:
#   uv run uvicorn api.main:app --reload

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.tech_detection import router as tech_detection_router
from .routes.url_discovery import router as url_discovery_router
from .routes.content_extraction import router as content_extraction_router
from .routes.website_processing import router as website_processing_router

app = FastAPI(
    title="web-graph",
    description="Website technology detection, URL discovery, content extraction, and combined discover+extract API",
    version="0.1.0",
)

# Local Next.js dev server only -- this is a local dev convenience, not a
# deployed-service CORS policy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tech_detection_router)
app.include_router(url_discovery_router)
app.include_router(content_extraction_router)
app.include_router(website_processing_router)


@app.get("/health")
def health():
    return {"status": "ok"}
