# Request/response shape ONLY -- no detection logic lives here. The
# "technologies" field is deliberately typed loosely (list[dict]) rather
# than a rigid per-technology model: direct entries and inferred entries
# have different shapes (see tech_detection/inference.py), and deciding
# that shape is tech_detection's job, not the API layer's. Pinning it down
# here would mean re-encoding business knowledge FastAPI has no business
# knowing.

from typing import Any

from pydantic import BaseModel


class DetectRequest(BaseModel):
    url: str


class ErrorDetail(BaseModel):
    type: str
    message: str


class DetectResponse(BaseModel):
    url: str
    status: str
    http_status: int | None
    browser_status: str  # "not_launched" | "ok" | "failed" -- never null
    evidence_source: str | None
    technologies: list[dict[str, Any]]
    errors: list[ErrorDetail]
