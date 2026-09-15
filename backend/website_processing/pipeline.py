# Lets this file be run directly (uv run website_processing/pipeline.py)
# regardless of the current working directory -- without it, Python only
# puts THIS file's own folder on sys.path, not the repo root where the
# url_discovery/ and content_extraction/ sibling packages actually live.
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from url_discovery.crawler import discover_urls
from content_extraction.content_extraction import extract_content

# A small, fixed ceiling on how many extract_content() calls run at once --
# not "as many as there are pages," since every one of them targets the
# SAME site the crawl just finished hitting. extract_content() already
# paces and retries each of ITS OWN requests (see content_extraction.py),
# but that's a per-call guarantee, not an aggregate-rate one: running this
# many of those calls in parallel means the site sees roughly this many
# requests per second, not one. This is the deliberate limit on how far
# "parallel" is allowed to go here.
MAX_CONCURRENT_EXTRACTIONS = 5


def discover_and_extract(
    start_url: str,
    max_pages: int = 10,
    max_depth: int | None = None,
):
    discovery_result = discover_urls(
        start_url=start_url,
        max_pages=max_pages,
        max_depth=max_depth,
    )

    if discovery_result["status"] == "failed":
        return {
            "status": "failed",
            "start_url": start_url,
            "discovery": discovery_result,
            "pages": [],
        }

    urls = discovery_result["discovered_urls"]

    if urls:
        # ThreadPoolExecutor.map() is the right tool for bounded-concurrent
        # I/O-bound work in a synchronous codebase -- extract_content()
        # spends nearly all its time blocked on network I/O, so threads
        # (not asyncio, not multiprocessing) give real overlap without a
        # rewrite. map() guarantees the RESULT order matches url order
        # even though the underlying calls can complete in any order.
        with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_EXTRACTIONS, len(urls))) as executor:
            pages = list(executor.map(extract_content, urls))
    else:
        pages = []

    # pages is guaranteed non-empty here: discover_urls() only reports
    # "success"/"partial" (never "failed", handled above) when at least
    # one page was actually discovered.
    succeeded_extractions = [page for page in pages if page["status"] == "success"]
    failed_extractions = [page for page in pages if page["status"] == "failed"]

    if not succeeded_extractions:
        # Every single extraction failed -- even if discovery itself was
        # only "partial", ending up with zero usable content is a worse
        # outcome than "partial" implies, so this takes priority over a
        # merely-partial discovery below.
        status = "failed"
    elif discovery_result["status"] == "partial" or failed_extractions:
        status = "partial"
    else:
        # discovery_result["status"] == "success" and every extraction
        # succeeded -- the only remaining combination.
        status = "success"

    return {
        "status": status,
        "start_url": start_url,
        "discovery": discovery_result,
        "pages": pages,
    }

def _safe_for_console(value):
    """Recursively replaces characters a Windows terminal's default cp1252
    console can't print (curly quotes, arrows, etc.) -- same issue hit
    with browser.py's and content_extraction.py's demo output. Scraped
    article text routinely contains these, and this result is a nested
    structure (discovery dict + a list of per-page dicts), so a flat
    str.encode() fix isn't enough here -- this walks the whole thing."""
    if isinstance(value, str):
        return value.encode("ascii", "replace").decode()
    if isinstance(value, list):
        return [_safe_for_console(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe_for_console(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    result = discover_and_extract(
        "https://lakshx.in/",
        max_pages=5,
    )

    print(_safe_for_console(result))