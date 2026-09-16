# Request/response shape ONLY -- see api/schemas/tech_detection.py for the
# same principle. This one's a single-resource result (one URL in, one
# extraction out), so unlike the other two features' contracts there's no
# batch status ("partial") and errors is a single nullable field, not a
# list -- matching content_extraction.content_extraction.extract_content()'s
# own return shape exactly.

from pydantic import BaseModel


class ExtractRequest(BaseModel):
    url: str


class ContentBlock(BaseModel):
    # "heading", "paragraph", or "list_item" -- kept as an ordered list
    # rather than separate headings/paragraphs arrays so a heading and the
    # content that followed it in the source document stay linked together,
    # in reading order, instead of being collapsed into disconnected lists.
    type: str
    level: int | None = None
    text: str


class ExtractResponse(BaseModel):
    status: str
    url: str
    title: str | None
    blocks: list[ContentBlock]
    error: str | None
