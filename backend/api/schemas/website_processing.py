# Request/response shape ONLY -- see api/schemas/tech_detection.py for the
# same principle. discovery/pages are typed against url_discovery's and
# content_extraction's OWN response models, not loosely as dict -- that's
# valid (not just convenient) here because website_processing.pipeline.
# discover_and_extract() literally stores discover_urls()'s and
# extract_content()'s return values verbatim under those keys, so reusing
# the models is precise, not a guess at their shape.

from pydantic import BaseModel, Field, field_validator

from .content_extraction import ExtractResponse
from .url_discovery import DiscoverResponse, _validate_path_patterns


class DiscoverAndExtractRequest(BaseModel):
    url: str
    max_pages: int = Field(
        default=10, ge=1, le=100,
        description="Same cap as /discover-urls -- see api/schemas/url_discovery.py.",
    )
    max_depth: int | None = Field(default=None, ge=0, le=50)
    # Same crawl-scope options as DiscoverRequest, reused directly rather
    # than redefined -- this workflow's discovery phase IS
    # url_discovery.crawler under the hood, so the same options mean the
    # same thing here. See api/schemas/url_discovery.py for what each does.
    include_paths: list[str] | None = Field(default=None)
    exclude_paths: list[str] | None = Field(default=None)
    regex_on_full_url: bool = Field(default=False)
    restrict_to_start_path: bool = Field(default=False)
    allow_subdomains: bool = Field(default=False)
    allow_external_links: bool = Field(default=False)
    ignore_query_parameters: bool = Field(default=False)
    ignore_robots_txt: bool = Field(default=False)

    _validate_paths = field_validator("include_paths", "exclude_paths")(_validate_path_patterns)


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
