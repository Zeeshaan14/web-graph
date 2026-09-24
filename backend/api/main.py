# ASGI app entry point. Run with:
#   uv run uvicorn api.main:app --reload
#
# Every route below except /health requires require_api_key + rate_limit
# (see api/auth.py, api/rate_limiting.py) -- applied per-router via
# `dependencies=`, not globally on `app`, specifically so /health stays
# reachable with no API key for an uptime check/load balancer probe.
# Auth itself is a no-op unless API_KEY is set (api/config.py) -- local
# dev via `uv run uvicorn api.main:app --reload` is unaffected either way.

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_api_key
from .config import settings
from .rate_limiting import rate_limit
from .routes.tech_detection import router as tech_detection_router
from .routes.url_discovery import router as url_discovery_router
from .routes.content_extraction import router as content_extraction_router
from .routes.website_processing import router as website_processing_router

logger = logging.getLogger(__name__)

if settings.api_key is None:
    logger.warning(
        "API_KEY is not set -- every route is unauthenticated. Set the API_KEY "
        "environment variable before deploying this anywhere it isn't purely local."
    )

app = FastAPI(
    title="web-graph",
    description="Website technology detection, URL discovery, content extraction, and combined discover+extract API",
    version="0.1.0",
)

# Origins come from CORS_ALLOWED_ORIGINS (api/config.py) -- defaults to
# the local Next.js dev server, same as before this was made configurable.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

_protected = [Depends(require_api_key), Depends(rate_limit)]

app.include_router(tech_detection_router, dependencies=_protected)
app.include_router(url_discovery_router, dependencies=_protected)
app.include_router(content_extraction_router, dependencies=_protected)
app.include_router(website_processing_router, dependencies=_protected)


@app.get("/health")
def health():
    return {"status": "ok"}
