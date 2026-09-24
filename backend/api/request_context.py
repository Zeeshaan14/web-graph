# A request ID, threaded through every log line a request's handling
# produces -- without this, a crawl's own dozen-plus log lines (fetch
# failures, robots.txt decisions, browser-render fallbacks, ...) have no
# way to be grouped back to the one request that caused them once
# several requests are in flight at once. See PRODUCTION_READINESS.md's
# "no observability" item.
#
# contextvars, not thread-locals: every route in this API is a sync
# `def`, run via Starlette's run_in_threadpool -- which copies the
# current contextvars.Context into the worker thread (via
# anyio.to_thread.run_sync), so a value set here in the ASGI middleware
# (see api/main.py's RequestContextMiddleware) is correctly visible
# inside the route/pipeline code running in that thread, with no manual
# passing required.

import contextvars
import uuid

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def new_request_id() -> str:
    return str(uuid.uuid4())
