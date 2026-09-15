# Request/response shape ONLY -- see api/schemas/tech_detection.py for
# the same principle. The one thing this file actually enforces (not just
# describes) is production safety: max_pages is deliberately NOT
# nullable here even though url_discovery.crawler.discover_urls() itself
# allows max_pages=None (unbounded) for direct/CLI callers who own their
# own risk. A public API must not expose "crawl this site with no page
# limit" -- with the crawler's own ~1s politeness delay per page, an
# unbounded or very large crawl ties up a synchronous request for a very
# long time. Capping it here is the API layer doing its actual job:
# validating the request before it ever reaches the crawler.

from pydantic import BaseModel, Field


class DiscoverRequest(BaseModel):
    url: str
    max_pages: int = Field(
        default=10, ge=1, le=100,
        description="Hard-capped for a synchronous request -- see module comment.",
    )
    max_depth: int | None = Field(
        default=None, ge=0, le=50,
        description="None means unbounded depth, still capped in total by max_pages.",
    )


class CrawlErrorDetail(BaseModel):
    url: str
    error: str


class DiscoverResponse(BaseModel):
    status: str
    start_url: str
    discovered_urls: list[str]
    pages_traversed: int
    errors: list[CrawlErrorDetail]
