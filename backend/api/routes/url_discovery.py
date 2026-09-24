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
    path_specific_strip = (
        {path: set(params) for path, params in request.path_specific_strip.items()}
        if request.path_specific_strip is not None
        else None
    )

    result = discover_urls(
        request.url,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
        path_specific_strip=path_specific_strip,
        timeout_seconds=request.timeout_seconds,
        include_paths=request.include_paths,
        exclude_paths=request.exclude_paths,
        regex_on_full_url=request.regex_on_full_url,
        restrict_to_start_path=request.restrict_to_start_path,
        allow_subdomains=request.allow_subdomains,
        allow_external_links=request.allow_external_links,
        ignore_query_parameters=request.ignore_query_parameters,
        ignore_robots_txt=request.ignore_robots_txt,
        max_concurrency=request.max_concurrency,
        delay_seconds=request.delay_seconds,
    )
    return DiscoverResponse(**result)
