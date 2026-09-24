# A process-wide cap on how many expensive requests (crawl/extract/
# detect) run AT ONCE, independent of any single request's own
# concurrency -- e.g. a /discover-urls call's max_concurrency only
# bounds fan-out WITHIN that one crawl. Without this, N simultaneous
# requests each launching their own crawl/browser work has no ceiling at
# all (see PRODUCTION_READINESS.md's P0 "nothing bounds a request's
# cost" item).
#
# A plain threading.Semaphore, not asyncio -- every route in this API is
# a sync `def`, run in Starlette's thread pool, so this is the right
# primitive for the same reason the rest of this codebase stays
# thread-based rather than async.

import threading
from contextlib import contextmanager

from fastapi import HTTPException

from .config import settings

_semaphore = threading.Semaphore(settings.max_concurrent_requests)


def _busy_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            f"Server is busy handling {settings.max_concurrent_requests} "
            "concurrent requests already -- try again shortly."
        ),
    )


@contextmanager
def limit_concurrency():
    """Wrap a route's actual work in `with limit_concurrency():`. Raises
    a 503 immediately (a non-blocking acquire) rather than queuing a
    request behind however many are already running -- a caller getting
    a fast, clear "server is busy" response is better than a request
    silently waiting behind a full queue with no way to tell why it's
    slow.

    Not usable for a StreamingResponse route -- see
    acquire_concurrency_slot()/release_concurrency_slot() below for why."""
    if not _semaphore.acquire(blocking=False):
        raise _busy_error()
    try:
        yield
    finally:
        _semaphore.release()


def acquire_concurrency_slot() -> None:
    """For a StreamingResponse route specifically -- limit_concurrency()'s
    context-manager form doesn't work there: Starlette sends the response
    status/headers BEFORE it starts iterating the body generator, so an
    HTTPException raised from inside that generator arrives too late to
    become a clean 503 -- the client would just see a broken/incomplete
    200 instead. Call this BEFORE constructing the StreamingResponse (so
    a busy server still raises a normal, clean 503), and
    release_concurrency_slot() from a `finally` inside the generator body
    once it's actually done."""
    if not _semaphore.acquire(blocking=False):
        raise _busy_error()


def release_concurrency_slot() -> None:
    _semaphore.release()
