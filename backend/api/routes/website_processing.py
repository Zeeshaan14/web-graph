# Same rule as the other three routes: validate, call
# discover_and_extract(), return exactly what it gives back. No
# orchestration logic here -- that's website_processing.pipeline's job.

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from website_processing.pipeline import discover_and_extract, discover_and_extract_stream

from ..concurrency import acquire_concurrency_slot, limit_concurrency, release_concurrency_slot
from ..schemas.website_processing import DiscoverAndExtractRequest, DiscoverAndExtractResponse

router = APIRouter()


def _crawl_scope_kwargs(request: DiscoverAndExtractRequest) -> dict:
    return {
        "include_paths": request.include_paths,
        "exclude_paths": request.exclude_paths,
        "regex_on_full_url": request.regex_on_full_url,
        "restrict_to_start_path": request.restrict_to_start_path,
        "allow_subdomains": request.allow_subdomains,
        "allow_external_links": request.allow_external_links,
        "ignore_query_parameters": request.ignore_query_parameters,
        "ignore_robots_txt": request.ignore_robots_txt,
        "max_concurrency": request.max_concurrency,
        "delay_seconds": request.delay_seconds,
    }


@router.post("/discover-and-extract", response_model=DiscoverAndExtractResponse)
def discover_and_extract_route(request: DiscoverAndExtractRequest) -> DiscoverAndExtractResponse:
    with limit_concurrency():
        result = discover_and_extract(
            request.url,
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            **_crawl_scope_kwargs(request),
        )
    return DiscoverAndExtractResponse(**result)


@router.post("/discover-and-extract/stream")
def discover_and_extract_stream_route(request: DiscoverAndExtractRequest) -> StreamingResponse:
    """Same call, progress events instead of one final response -- see
    discover_and_extract_stream()'s own docstring for the event sequence.
    One JSON object per line (newline-delimited, not Server-Sent Events'
    "data: ...\\n\\n" framing -- there's no need for SSE's reconnect/retry
    machinery here: this is a one-shot request/response stream, not a
    long-lived subscription, so a client just reads the body as it
    arrives). A plain `def` (not `async def`), same as every other route
    in this API -- Starlette runs a sync generator body in a thread pool
    automatically, so this doesn't block the event loop even though
    fetch_and_prepare() underneath makes blocking `requests` calls.

    Concurrency-limited via acquire/release, not `with limit_concurrency():`
    -- see api/concurrency.py's acquire_concurrency_slot() docstring: a
    StreamingResponse's status/headers go out before its body generator
    ever runs, so the slot has to be acquired here, synchronously, before
    the response is even constructed, for a busy server to still come
    back as a clean 503 instead of a broken 200."""
    acquire_concurrency_slot()

    def event_stream():
        try:
            for event in discover_and_extract_stream(
                request.url,
                max_pages=request.max_pages,
                max_depth=request.max_depth,
                **_crawl_scope_kwargs(request),
            ):
                yield json.dumps(event) + "\n"
        finally:
            release_concurrency_slot()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
