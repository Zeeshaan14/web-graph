# Per-client-IP rate limiting, fixed-window, in-memory. Hand-rolled
# rather than a third-party library (slowapi, etc.) -- every route in
# this API already takes a Pydantic body parameter named `request`
# (FastAPI convention), which collides with the `request: Request`
# parameter name most rate-limiter decorators expect on the WRAPPED
# function itself. A plain FastAPI dependency sidesteps that entirely --
# dependencies resolve their own parameters independently of the route
# they're attached to -- and matches this project's existing preference
# for a small, self-contained implementation over a new dependency for
# something this contained (see security/ssrf_guard.py, or the
# pacing/retry logic duplicated across each fetcher.py).
#
# In-memory means per-PROCESS, not cluster-wide -- fine for the current
# single-process deployment model (see PRODUCTION_READINESS.md's
# "single-process assumption" note); a multi-worker/multi-replica
# deployment would need a shared store (Redis, etc.) instead.

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings

_lock = threading.Lock()
_requests_by_ip: dict[str, deque] = defaultdict(deque)

_WINDOW_SECONDS = 60.0


def rate_limit(request: Request) -> None:
    """A FastAPI dependency -- add to a route's `dependencies=[...]` to
    enforce settings.rate_limit_per_minute requests per minute, per
    client IP. Fixed 60-second sliding window: each call drops
    timestamps older than the window from that IP's own history, then
    checks the remaining count before recording this one."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS

    with _lock:
        history = _requests_by_ip[client_ip]

        while history and history[0] < window_start:
            history.popleft()

        if len(history) >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: {settings.rate_limit_per_minute} requests "
                    "per minute per client. Try again shortly."
                ),
            )

        history.append(now)

    # Known, accepted limitation: an IP that stops making requests
    # entirely leaves its (eventually-stale) deque resident in
    # _requests_by_ip for the life of the process -- nothing sweeps a
    # dead entry unless that SAME IP happens to call again. Bounded in
    # practice by how many distinct client IPs this process realistically
    # sees; a real fix (periodic sweep, or an actual rate-limit store)
    # is the same "in-memory, single-process" limitation this whole
    # module already accepts (see module docstring).
