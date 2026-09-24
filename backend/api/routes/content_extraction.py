# Same rule as the other two features' routes: validate, call
# extract_content(), return exactly what it gives back. No parsing logic,
# no boilerplate-stripping decisions -- all of that lives in
# content_extraction.content_extraction.

from fastapi import APIRouter

from content_extraction.content_extraction import extract_content

from ..concurrency import limit_concurrency
from ..schemas.content_extraction import ExtractRequest, ExtractResponse

router = APIRouter()


@router.post("/extract-content", response_model=ExtractResponse)
def extract_content_route(request: ExtractRequest) -> ExtractResponse:
    with limit_concurrency():
        result = extract_content(request.url)
    return ExtractResponse(**result)
