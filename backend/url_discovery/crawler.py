# Breadth-first crawl of a single site, starting from one URL. Owns the
# traversal (queue, depth, page-identity resolution, dedup) only -- how
# requests are actually made lives in fetcher.py, and HTML/URL parsing
# lives in link_extraction.py. This file shouldn't need to know what a
# 429 is or what "browser-shaped headers" means.
#
# Logging, not print(): this runs inside a server process (the API
# route calls discover_urls() directly), so per-page trace output must
# be opt-in via logging configuration, not something that always writes
# to stdout. Genuine failures are WARNING (visible with zero config,
# via logging's last-resort handler); routine per-page trace is DEBUG
# (silent unless someone turns on verbose logging).

import logging
import time
from collections import deque
from urllib.parse import urlparse

import requests

from .fetcher import fetch, new_session
from .link_extraction import extract_canonical, extract_links, normalize_url

logger = logging.getLogger(__name__)


def crawl(
    start_url: str,
    max_pages: int | None = 10,
    max_depth: int | None = None,
    path_specific_strip: dict[str, set[str]] | None = None,
    timeout_seconds: float | None = None,
) -> dict:
    """path_specific_strip: optional site-specific noisy query params to
    strip, e.g. {"/feedback/realpython-com/": {"d"}}. See
    link_extraction.normalize_url() -- kept as an explicit argument here
    rather than hardcoded, since crawl() is meant to work for any site,
    not just the one quirk we've seen so far.

    timeout_seconds: an optional wall-clock budget for the whole crawl,
    checked the same way max_pages is -- before starting the next page,
    never by interrupting a fetch already in flight. None (the default)
    means unbounded, same as max_depth; max_pages alone can still take a
    long time on a slow site, since it says nothing about how long each
    page takes.

    Returns internal traversal data, NOT the public API contract --
    {"urls": [...], "pages_traversed": N, "errors": [...]}. Shaping this
    into a {status, start_url, discovered_urls, ...} response is
    discover_urls()'s job, not this function's: crawl() only ever
    records EXPECTED per-page failures (a RequestException) and keeps
    going -- it never decides what those failures mean for the crawl as
    a whole, and it never catches anything else. An unexpected exception
    here is meant to propagate out to discover_urls()."""
    start_url = normalize_url(start_url, path_specific_strip)
    start_domain = urlparse(start_url).netloc

    session = new_session()

    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds

    # Each queue entry carries its depth alongside the URL: start_url is
    # depth 0, pages it links to are depth 1, pages those link to are
    # depth 2, and so on.
    queue = deque([(start_url, 0)])

    # URLs already added to the queue.
    # Prevents the same URL being queued multiple times.
    seen = {start_url}

    # TRAVERSAL identity: which final destinations we've actually
    # fetched and expanded. /articles/ and /articles/page/2/ are
    # different traversal URLs even though they may share a canonical --
    # each gets fetched and parsed for its own links.
    visited_traversal = set()

    # OUTPUT identity: the preferred URL to report for each page (final
    # URL, or its canonical when one exists). Deliberately a SEPARATE
    # set/list from traversal -- /articles/ and /articles/page/2/ can
    # both be traversed while only /articles/ ends up in the output.
    output_seen = set()
    discovered_output = []

    # EXPECTED per-page failures only -- a RequestException means we
    # tried and the request itself failed (404/500, timeout, connection
    # error, a 429 that didn't recover after fetcher's one retry). This
    # is not a reason to stop the crawl; it's data for discover_urls()
    # to decide what the overall outcome means.
    errors = []

    while queue and (
        max_pages is None or len(visited_traversal) < max_pages
    ):
        if deadline is not None and time.monotonic() >= deadline:
            logger.debug("Wall-clock timeout reached, stopping crawl (%.0fs budget)", timeout_seconds)
            break

        current_url, depth = queue.popleft()

        if current_url in visited_traversal:
            # Already reached this exact URL earlier -- e.g. it was
            # sitting in the queue when a DIFFERENT queued URL redirected
            # to it and got marked visited first. Don't waste an HTTP
            # request confirming what we already know.
            continue

        logger.debug("Visiting (depth %d): %s", depth, current_url)

        try:
            response = fetch(session, current_url)
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", current_url, exc)
            errors.append({"url": current_url, "error": str(exc)})
            continue

        # The server may have redirected us -- the final destination,
        # not the URL we requested, is this page's identity so far.
        final_url = normalize_url(response.url, path_specific_strip)
        final_domain = urlparse(final_url).netloc

        # Same-site checking happens twice: once when a link is
        # discovered (extract_links() below only returns links matching
        # the CURRENT page's domain), and again here, because a redirect
        # can move us outside the crawl boundary even when the URL we
        # REQUESTED was legitimately in scope -- e.g.
        # realpython.com/merch -> realpython.threadless.com. The
        # requested URL is already in `seen` (it got there before being
        # queued), so it won't be retried -- but the external
        # destination itself is never recorded or expanded.
        if final_domain != start_domain:
            logger.debug("External redirect, stopping: %s -> %s", current_url, final_url)
            continue

        # final_url is the ONLY thing that decides whether we've already
        # processed this page and whether we bother extracting its links.
        # A canonical tag is a claim the PAGE makes about its preferred
        # URL, not proof we've already fetched and expanded that other
        # URL -- so it must never gate traversal, only the output below.
        if final_url in visited_traversal:
            # Already reached this exact final destination earlier -- a
            # different requested URL or redirect chain led here too.
            # Nothing new here -- don't record it again or re-expand it.
            logger.debug("Already traversed: %s -> %s", current_url, final_url)
            continue

        visited_traversal.add(final_url)

        # Both the requested URL and the final destination now count as
        # seen -- a future link matching EITHER form should be skipped
        # rather than re-queued and re-fetched as if it were new.
        seen.add(current_url)
        seen.add(final_url)

        # A non-HTML response (PDF, image, ...) has no canonical tag and
        # no <a> links to extract -- feeding it to the HTML parser would
        # just waste cycles finding nothing. A MISSING content-type
        # header is treated as HTML (not as a reason to skip): unlike
        # content_extraction's single-resource contract, getting this
        # wrong here only means we attempt a parse that finds nothing,
        # not that we drop a page we should have discovered.
        content_type = response.headers.get("content-type", "")
        is_html_page = content_type == "" or "text/html" in content_type.lower()

        if not is_html_page:
            logger.debug("Non-HTML content-type, skipping parse: %s (%s)", final_url, content_type)

        # The preferred URL to REPORT for this page -- starts as
        # final_url, but a same-site canonical (independent of any HTTP
        # redirect) can override it. E.g. /articles/page/2/ and
        # /articles/page/3/ both traverse separately, but if both declare
        # canonical=/articles/, they should all report as one output URL.
        output_url = final_url

        canonical_url = extract_canonical(response.text, response.url) if is_html_page else None

        if canonical_url:
            canonical_url = normalize_url(canonical_url, path_specific_strip)
            canonical_domain = urlparse(canonical_url).netloc

            logger.debug("Canonical: %s -> %s", final_url, canonical_url)

            if canonical_domain == start_domain:
                output_url = canonical_url

        if output_url not in output_seen:
            output_seen.add(output_url)
            discovered_output.append(output_url)

        # Links found on this page are one hop further out than this
        # page itself -- don't even queue them if that would exceed
        # max_depth, same as we already skip already-seen links.
        if max_depth is not None and depth >= max_depth:
            continue

        if not is_html_page:
            continue

        # Always extract links from the page we actually just fetched,
        # regardless of whether output_url was already seen -- /articles/
        # and /articles/page/2/ share an output URL but do NOT share
        # content. Gating this on output_seen would silently stop the
        # crawl from ever reaching /articles/page/3/ and beyond.
        links = extract_links(
            response.text,
            response.url,
            path_specific_strip,
        )

        for link in links:
            if link in seen:
                continue

            seen.add(link)
            queue.append((link, depth + 1))

    return {
        "urls": discovered_output,
        "pages_traversed": len(visited_traversal),
        "errors": errors,
    }


def discover_urls(
    start_url: str,
    max_pages: int | None = 10,
    max_depth: int | None = None,
    path_specific_strip: dict[str, set[str]] | None = None,
    timeout_seconds: float | None = None,
) -> dict:
    """The feature-level entry point -- this is what the API layer will
    eventually call. crawl() is the traversal engine; this is the
    contract + safety boundary around it: it decides what a crawl's
    outcome MEANS (success/partial/failed) and guarantees nothing ever
    raises out of here, the same lesson from tech_detection's pipeline.py
    (a caller of an API can't be expected to catch arbitrary Python
    exceptions -- it needs one predictable response shape either way).

    crawl() itself only ever records expected per-page failures
    (RequestException) and keeps going. Anything else escaping crawl()
    -- a real bug, not a bad page -- is caught here and reported the
    same way a totally-unreachable start_url would be: status "failed".
    """
    try:
        result = crawl(
            start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            path_specific_strip=path_specific_strip,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "start_url": start_url,
            "discovered_urls": [],
            "pages_traversed": 0,
            "errors": [{"url": start_url, "error": str(exc)}],
        }

    if result["pages_traversed"] == 0:
        # Nothing was ever successfully fetched -- not even the start
        # URL itself. A handful of individually-broken pages inside an
        # otherwise-working crawl is "partial", not this: this is "we
        # could not meaningfully crawl the site at all."
        status = "failed"
    elif result["errors"]:
        status = "partial"
    else:
        status = "success"

    return {
        "status": status,
        "start_url": start_url,
        "discovered_urls": result["urls"],
        "pages_traversed": result["pages_traversed"],
        "errors": result["errors"],
    }


if __name__ == "__main__":
    # Only when run directly (python -m url_discovery.crawler) do we
    # want the verbose per-page trace on screen -- a caller embedding
    # discover_urls() in a server should configure logging itself,
    # or not, entirely on its own terms.
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    # Site-specific knowledge belongs at the call site, not inside the
    # generic crawler/normalizer -- see link_extraction.normalize_url().
    REALPYTHON_NOISY_PARAMS = {
        "/feedback/realpython-com/": {"d"},
    }

    result = discover_urls(
        "https://www.smashingmagazine.com/",
        max_pages=20,
        max_depth=2,
        path_specific_strip=REALPYTHON_NOISY_PARAMS,
    )

    print(f"\nStatus: {result['status']} | pages traversed: {result['pages_traversed']}")

    if result["errors"]:
        print("\nErrors:")
        for err in result["errors"]:
            print(f"  {err['url']} -> {err['error']}")

    print("\nDiscovered URLs:")

    for url in result["discovered_urls"]:
        print(url)
