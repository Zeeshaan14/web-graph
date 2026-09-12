# The entire job of this layer: validate the request (schemas.py /
# FastAPI does that), call the pipeline, return its result. No fetching,
# no evidence building, no scoring, no fallback decisions -- all of that
# stays in tech_detection.pipeline, exactly as it was before an API ever
# existed. This file should never grow an if/else that changes what gets
# detected or how.

from fastapi import APIRouter

from tech_detection.pipeline import detect_website_technologies

from .schemas import DetectRequest, DetectResponse

router = APIRouter()


@router.post("/detect-tech", response_model=DetectResponse)
def detect_tech(request: DetectRequest) -> DetectResponse:
    result = detect_website_technologies(request.url)
    return DetectResponse(**result)
