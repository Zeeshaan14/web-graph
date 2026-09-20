# Request/response shape ONLY -- see api/schemas/tech_detection.py for the
# same principle. discovery/pages are typed against url_discovery's and
# content_extraction's OWN response models, not loosely as dict -- that's
# valid (not just convenient) here because website_processing.pipeline.
# discover_and_extract() literally stores discover_urls()'s and
# extract_content()'s return values verbatim under those keys, so reusing
# the models is precise, not a guess at their shape.

from pydantic import BaseModel, Field

from .content_extraction import ExtractResponse
from .url_discovery import DiscoverResponse


class DiscoverAndExtractRequest(BaseModel):
    url: str
    max_pages: int = Field(
        default=10, ge=1, le=100,
        description="Same cap as /discover-urls -- see api/schemas/url_discovery.py.",
    )
    max_depth: int | None = Field(default=None, ge=0, le=50)


class DiscoverAndExtractResponse(BaseModel):
    status: str
    start_url: str
    discovery: DiscoverResponse
    pages: list[ExtractResponse]
    # Nav/sidebar/footer content observed to repeat across several of this
    # crawl's own pages -- pulled out of each page above and reported here
    # once instead. Empty string when nothing met that bar (a 1-page
    # crawl, or a site with no consistently-repeated chrome).
    shared_content_markdown: str
