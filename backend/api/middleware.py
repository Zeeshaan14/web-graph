# One middleware, two jobs that both need to wrap every request the same
# way: assign/propagate a request ID (see request_context.py) and log one
# line per request with the outcome. Kept together rather than as two
# separate middlewares purely so there's only one place computing the
# request's duration and only one place both need it.

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .request_context import new_request_id, request_id_var

logger = logging.getLogger("api.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Honors an inbound X-Request-ID (a caller/proxy that already
        # assigned one) rather than always minting a fresh one -- lets a
        # request be traced end to end across whatever sits in front of
        # this API too, not just within it.
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        token = request_id_var.set(request_id)
        start = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            # Belt-and-suspenders only -- a route's own exception is
            # normally already turned into a response (a clean 500) by
            # main.py's unhandled_exception_handler, which also logs the
            # full traceback, before it ever reaches this middleware.
            # This branch is for something escaping even THAT (a genuine
            # ASGI-level failure), which still deserves an access log
            # line and a correctly-reset context var rather than a
            # request ID silently leaking into whatever runs next.
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.warning(
                "%s %s -> unhandled exception (%.1fms)",
                request.method, request.url.path, duration_ms,
            )
            request_id_var.reset(token)
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        request_id_var.reset(token)
        return response
