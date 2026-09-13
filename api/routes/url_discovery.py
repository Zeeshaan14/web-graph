# Same rule as tech_detection's route: validate, call discover_urls(),
# return exactly what it gives back. No traversal logic, no status
# derivation -- that all lives in url_discovery.crawler.discover_urls(),
# which already returns the public contract shape verbatim.

from fastapi import APIRouter

from url_discovery.crawler import discover_urls

from ..schemas.url_discovery import DiscoverRequest, DiscoverResponse

router = APIRouter()


@router.post("/discover-urls", response_model=DiscoverResponse)
def discover_urls_route(request: DiscoverRequest) -> DiscoverResponse:
    result = discover_urls(
        request.url,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
    )
    return DiscoverResponse(**result)
