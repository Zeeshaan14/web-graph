# Same rule as the other three routes: validate, call
# discover_and_extract(), return exactly what it gives back. No
# orchestration logic here -- that's website_processing.pipeline's job.

from fastapi import APIRouter

from website_processing.pipeline import discover_and_extract

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
