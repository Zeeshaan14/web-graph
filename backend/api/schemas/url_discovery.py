# Request/response shape ONLY -- see api/schemas/tech_detection.py for
# the same principle. The one thing this file actually enforces (not just
# describes) is production safety: max_pages and timeout_seconds are
# deliberately NOT nullable here even though url_discovery.crawler.
# discover_urls() itself allows both None (unbounded) for direct/CLI
# callers who own their own risk. A public API must not expose "crawl
# this site with no page limit" or "...no time limit" -- with the
# crawler's own ~1s politeness delay per page, an unbounded or very large
# crawl ties up a synchronous request for a very long time, and a page
# count alone says nothing about how long each page takes to fetch.
# Capping both here is the API layer doing its actual job: validating
# the request before it ever reaches the crawler.

import re

from pydantic import BaseModel, Field, field_validator

# A generous cap on how many regex patterns one request can supply --
# matches Firecrawl's own includePaths/excludePaths limit (1000 patterns).
# Not about trusting the caller's regex complexity (that's ReDoS territory
# regardless of count), just a sane bound on request size.
MAX_PATH_PATTERNS = 1000


def _validate_path_patterns(patterns: list[str] | None) -> list[str] | None:
    """Compiling here, at the API boundary, means a bad regex fails fast
    with a clean 422 instead of surfacing deep inside a crawl -- same
    principle as max_pages/timeout_seconds being validated in this file
    rather than left to the crawler itself."""
    if patterns is None:
        return None
    if len(patterns) > MAX_PATH_PATTERNS:
        raise ValueError(f"at most {MAX_PATH_PATTERNS} patterns allowed, got {len(patterns)}")
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"'{pattern}' is not a valid regex: {exc}") from exc
    return patterns


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
    timeout_seconds: float = Field(
        default=60.0, ge=1.0, le=300.0,
        description=(
            "Wall-clock budget for the whole crawl. Also NOT nullable here, for "
            "the same reason as max_pages: max_pages alone bounds how MANY pages "
            "get fetched, not how long a slow site can take doing it."
        ),
    )
    path_specific_strip: dict[str, list[str]] | None = Field(
        default=None,
        description=(
            "Optional per-path noisy query params to strip during crawling, e.g. "
            '{"/feedback/": ["d"]}. Lists here become sets before reaching '
            "discover_urls() -- see url_discovery.link_extraction.normalize_url()."
        ),
    )
    include_paths: list[str] | None = Field(
        default=None,
        description="Regex patterns -- only a discovered link matching at least one is queued.",
    )
    exclude_paths: list[str] | None = Field(
        default=None,
        description="Regex patterns -- a discovered link matching any of these is never queued, even if it also matches include_paths.",
    )
    regex_on_full_url: bool = Field(
        default=False,
        description="Match include_paths/exclude_paths against the full URL (query string included) instead of just the path.",
    )
    restrict_to_start_path: bool = Field(
        default=False,
        description="Stay under start_url's own path (e.g. starting at /docs/ stays under /docs/) instead of crawling the whole domain.",
    )
    allow_subdomains: bool = Field(
        default=False,
        description="Treat any subdomain of the same site as in-scope, not just a leading www. alias.",
    )
    allow_external_links: bool = Field(
        default=False,
        description="Record a cross-site link as a discovered URL, fetched once, never expanded further.",
    )
    ignore_query_parameters: bool = Field(
        default=False,
        description="Drop every URL's query string entirely when deciding if two URLs are the same page.",
    )
    ignore_robots_txt: bool = Field(
        default=False,
        description="Crawl every same-site URL regardless of robots.txt. Off by default -- this crawler obeys robots.txt unless a caller explicitly opts out.",
    )

    _validate_paths = field_validator("include_paths", "exclude_paths")(_validate_path_patterns)


class CrawlErrorDetail(BaseModel):
    url: str
    error: str


class DiscoverResponse(BaseModel):
    status: str
    start_url: str
    discovered_urls: list[str]
    pages_traversed: int
    errors: list[CrawlErrorDetail]
