# Lets this file be run directly (uv run website_processing/pipeline.py)
# regardless of the current working directory -- without it, Python only
# puts THIS file's own folder on sys.path, not the repo root where the
# url_discovery/ and content_extraction/ sibling packages actually live.
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from url_discovery.crawler import discover_urls_stream
from content_extraction.content_extraction import fetch_and_prepare, render_markdown
from website_processing.shared_content import find_shared_containers, remove_shared_containers, signature

# A small, fixed ceiling on how many fetch_and_prepare() calls run at once --
# not "as many as there are pages," since every one of them targets the
# SAME site the crawl just finished hitting. fetch_and_prepare() already
# paces and retries each of ITS OWN requests (see content_extraction.py),
# but that's a per-call guarantee, not an aggregate-rate one: running this
# many of those calls in parallel means the site sees roughly this many
# requests per second, not one. This is the deliberate limit on how far
# "parallel" is allowed to go here.
MAX_CONCURRENT_EXTRACTIONS = 5


def discover_and_extract_stream(
    start_url: str,
    max_pages: int = 10,
    max_depth: int | None = None,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    regex_on_full_url: bool = False,
    restrict_to_start_path: bool = False,
    allow_subdomains: bool = False,
    allow_external_links: bool = False,
    ignore_query_parameters: bool = False,
    ignore_robots_txt: bool = False,
):
    """The real implementation, as a generator of progress events --
    discover_and_extract() below is just this, exhausted for its final
    "complete" event. Split out because the old single "wait for
    everything, then return one dict" shape gives a caller nothing to show
    while a multi-page crawl is running, which is the whole reason this
    exists: an event per real milestone (discovery finishing, each page's
    fetch finishing, dedup finishing, each page's final render finishing),
    not a fake progress bar.

    Every event is {"event": <name>, ...}. In order:
      discovery_started
      url_discovered   {url, count}   -- one per URL, as discover_urls_stream()
                                          actually finds it during the BFS
                                          crawl, not all at once when the
                                          whole crawl finishes
      discovery_done   {discovery}
      page_fetched     {url, status}  -- one per page, as fetch_and_prepare()
                                          actually completes (real concurrent
                                          order, not discovery order)
      dedup_done       {shared_content_markdown}
      page_rendered    {page}         -- one per page, final ExtractResponse-
                                          shaped dict, AFTER dedup has
                                          stripped shared content from it
      complete         {result}       -- the exact same shape
                                          discover_and_extract() has always
                                          returned

    include_paths / exclude_paths / regex_on_full_url / restrict_to_start_path /
    allow_subdomains / allow_external_links / ignore_query_parameters /
    ignore_robots_txt are forwarded straight to discover_urls_stream() --
    see url_discovery.crawler.crawl_stream() for what each one does. This
    function owns no scope-decision logic of its own; it only orchestrates
    discovery + extraction + dedup.
    """
    yield {"event": "discovery_started"}

    discovery_result = None
    for event in discover_urls_stream(
        start_url=start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        regex_on_full_url=regex_on_full_url,
        restrict_to_start_path=restrict_to_start_path,
        allow_subdomains=allow_subdomains,
        allow_external_links=allow_external_links,
        ignore_query_parameters=ignore_query_parameters,
        ignore_robots_txt=ignore_robots_txt,
    ):
        if event["event"] == "url_discovered":
            yield event
        else:
            discovery_result = event["result"]

    yield {"event": "discovery_done", "discovery": discovery_result}

    if discovery_result["status"] == "failed":
        result = {
            "status": "failed",
            "start_url": start_url,
            "discovery": discovery_result,
            "pages": [],
            "shared_content_markdown": "",
        }
        yield {"event": "complete", "result": result}
        return

    urls = discovery_result["discovered_urls"]
    prepared_by_url = {}

    if urls:
        # submit() + as_completed(), not map() -- map() only ever hands
        # back results once ALL of them are done (it's just a for loop
        # over an ordered iterator of futures), which is exactly the "wait
        # for everything" shape this function exists to avoid. Concurrency
        # itself is identical either way: a ThreadPoolExecutor(max_workers=N)
        # runs at most N at once regardless of which of these submits all
        # the work upfront.
        #
        # fetch_and_prepare() stops short of converting to Markdown on
        # purpose -- shared nav/sidebar/footer content needs to be found
        # and stripped from each page's own parsed <body> BEFORE that
        # page's Markdown gets rendered, not after (there's no structure
        # left to detect or preserve in flat text).
        with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_EXTRACTIONS, len(urls))) as executor:
            future_to_url = {executor.submit(fetch_and_prepare, url): url for url in urls}
            for future in as_completed(future_to_url):
                # Keyed by the URL WE submitted (future_to_url), not by
                # whatever url field the result itself carries -- in real
                # use fetch_and_prepare() always echoes its own input back,
                # but nothing here should have to assume that.
                submitted_url = future_to_url[future]
                page = future.result()
                prepared_by_url[submitted_url] = page
                yield {"event": "page_fetched", "url": submitted_url, "status": page["status"]}

    # Back into discovery order -- as_completed() above yields in whatever
    # order threads actually finished in, but the final `pages` list (and
    # every page_rendered event below) keeps the same order guarantee
    # executor.map() used to give directly.
    prepared = [prepared_by_url[url] for url in urls]

    successful = [page for page in prepared if page["status"] == "success"]

    shared_containers = find_shared_containers([page["body"] for page in successful])
    shared_signatures = [signature(container) for container in shared_containers]

    # Rendered BEFORE any pruning below -- each representative Tag is a
    # live reference into one of the pages' own body trees, and that same
    # page gets pruned right after this: converting it to Markdown first
    # avoids handing render_markdown() an already-emptied (decompose()'d)
    # tag.
    shared_content_markdown = "\n\n---\n\n".join(
        render_markdown(container) for container in shared_containers
    )

    for page in successful:
        remove_shared_containers(page["body"], shared_signatures)

    yield {"event": "dedup_done", "shared_content_markdown": shared_content_markdown}

    pages = []
    for page in prepared:
        if page["status"] == "success":
            rendered = {
                "status": "success",
                "url": page["url"],
                "title": page["title"],
                "content_markdown": render_markdown(page["body"]),
                "error": None,
            }
        else:
            rendered = {
                "status": "failed",
                "url": page["url"],
                "title": None,
                "content_markdown": "",
                "error": page["error"],
            }
        pages.append(rendered)
        yield {"event": "page_rendered", "page": rendered}

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

    result = {
        "status": status,
        "start_url": start_url,
        "discovery": discovery_result,
        "pages": pages,
        "shared_content_markdown": shared_content_markdown,
    }

    yield {"event": "complete", "result": result}


def discover_and_extract(
    start_url: str,
    max_pages: int = 10,
    max_depth: int | None = None,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    regex_on_full_url: bool = False,
    restrict_to_start_path: bool = False,
    allow_subdomains: bool = False,
    allow_external_links: bool = False,
    ignore_query_parameters: bool = False,
    ignore_robots_txt: bool = False,
):
    """Non-streaming convenience wrapper, same contract this had before
    streaming existed -- exhausts discover_and_extract_stream() and
    returns just its final result. Used by anything that doesn't care
    about progress (tests, the __main__ block below, any future non-HTTP
    caller)."""
    for event in discover_and_extract_stream(
        start_url,
        max_pages,
        max_depth,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        regex_on_full_url=regex_on_full_url,
        restrict_to_start_path=restrict_to_start_path,
        allow_subdomains=allow_subdomains,
        allow_external_links=allow_external_links,
        ignore_query_parameters=ignore_query_parameters,
        ignore_robots_txt=ignore_robots_txt,
    ):
        if event["event"] == "complete":
            return event["result"]


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
    for event in discover_and_extract_stream("https://lakshx.in/", max_pages=5):
        print(_safe_for_console(event))
