# Same rule as the other three routes: validate, call
# discover_and_extract(), return exactly what it gives back. No
# orchestration logic here -- that's website_processing.pipeline's job.

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from website_processing.pipeline import discover_and_extract, discover_and_extract_stream

from ..schemas.website_processing import DiscoverAndExtractRequest, DiscoverAndExtractResponse

router = APIRouter()


@router.post("/discover-and-extract", response_model=DiscoverAndExtractResponse)
def discover_and_extract_route(request: DiscoverAndExtractRequest) -> DiscoverAndExtractResponse:
    result = discover_and_extract(
        request.url,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
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
    fetch_and_prepare() underneath makes blocking `requests` calls."""

    def event_stream():
        for event in discover_and_extract_stream(
            request.url,
            max_pages=request.max_pages,
            max_depth=request.max_depth,
        ):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
