# Single-shared-secret auth, gating every route except /health. Checked
# on an X-API-Key header -- the simplest mechanism that actually gates
# access; this project has no multi-user/billing model yet that would
# justify anything more (see PRODUCTION_READINESS.md's P0 auth item).
#
# Off entirely when API_KEY isn't set (api/config.py's default) -- see
# that module for why.

from fastapi import Header, HTTPException

from .config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key is None:
        return  # auth disabled -- see module docstring

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")
