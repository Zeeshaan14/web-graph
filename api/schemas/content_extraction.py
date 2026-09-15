# Request/response shape ONLY -- see api/schemas/tech_detection.py for the
# same principle. This one's a single-resource result (one URL in, one
# extraction out), so unlike the other two features' contracts there's no
# batch status ("partial") and errors is a single nullable field, not a
# list -- matching content_extraction.content_extraction.extract_content()'s
# own return shape exactly.

from pydantic import BaseModel


class ExtractRequest(BaseModel):
    url: str


class ExtractResponse(BaseModel):
    status: str
    url: str
    title: str | None
    headings: list[str]
    paragraphs: list[str]
    error: str | None
