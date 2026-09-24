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
import re
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor
from concurrent.futures import wait as wait_futures
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import requests
from playwright.sync_api import sync_playwright

from security.ssrf_guard import UnsafeURLError, assert_safe_url

from .browser import render_page_html, should_render_with_browser
from .fetcher import fetch, new_session
from .link_extraction import extract_canonical, extract_links, is_same_site, normalize_url

logger = logging.getLogger(__name__)

# We don't crawl under a registered bot identity, so there's no specific
# User-agent group in a robots.txt for us to match -- checking "*" is what
# every generic crawler checks against: the rules meant for everyone.
ROBOTS_USER_AGENT = "*"

# A hard ceiling on how many pages get a browser render in ONE crawl. Unlike
# tech_detection (one page, one possible browser launch), a crawl can visit
# up to max_pages pages -- if EVERY one of them looked like an unrendered
# SPA shell, launching Chromium that many times would make an otherwise
# fast crawl take minutes instead of seconds. Not caller-configurable in
# V1, same as MAX_CONCURRENT_EXTRACTIONS in website_processing: a small,
# fixed safety valve, not a knob.
MAX_BROWSER_RENDERS_PER_CRAWL = 10

# Substring markers for a DNS resolution failure, checked against a
# ConnectionError's own str() -- the real underlying exception (urllib3's
# NameResolutionError, wrapping a socket.gaierror) is buried inside
# ConnectionError.args, not exposed as its own catchable type, so this is
# the standard way to detect it. Covers the OS-specific errno wording:
# Windows' "getaddrinfo failed", Linux's "Name or service not known",
# macOS's "nodename nor servname".
_DNS_FAILURE_MARKERS = (
    "NameResolutionError",
    "getaddrinfo failed",
    "Name or service not known",
    "nodename nor servname",
)


def _friendly_fetch_error(url: str, exc: requests.RequestException | UnsafeURLError) -> str:
    """requests' own str(exc) for a ConnectionError is an internal repr --
    "HTTPSConnectionPool(host=..., port=443): Max retries exceeded with
    url: / (Caused by NameResolutionError(...))" -- technically accurate,
    not something worth showing someone who just typed a URL into a form.
    Anything else (HTTPError, Timeout, UnsafeURLError, ...) already has a
    reasonably clean str() of its own, left as-is."""
    if isinstance(exc, requests.exceptions.ConnectionError) and any(
        marker in str(exc) for marker in _DNS_FAILURE_MARKERS
    ):
        return f"Could not resolve '{url}' -- check the domain and try again."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"Could not connect to '{url}'."
    return str(exc)


def _compile_path_patterns(patterns: list[str] | None) -> list[re.Pattern]:
    return [re.compile(p) for p in patterns] if patterns else []


def _in_scope(
    url: str,
    include_patterns: list[re.Pattern],
    exclude_patterns: list[re.Pattern],
    regex_on_full_url: bool,
    start_path: str,
    restrict_to_start_path: bool,
) -> bool:
    """Whether a candidate same-site URL (a sitemap entry or a link found
    on a page) should be queued for traversal at all -- checked once,
    before it ever reaches the queue, so an out-of-scope URL never costs
    a wasted HTTP request. Never applied to the start URL itself, which
    is always crawled regardless of these filters -- a caller who asked
    to crawl a specific URL gets that URL, even if it wouldn't otherwise
    match its own include/exclude/restrict rules.

    Exclude wins over include when a URL matches both, same precedence
    Firecrawl's own includePaths/excludePaths use. regex_on_full_url
    matches against the whole URL (query string included) instead of
    just the path -- off by default, since a path-only match is what a
    caller most often means by "only crawl /blog/*"."""
    target = url if regex_on_full_url else urlparse(url).path

    if restrict_to_start_path and not urlparse(url).path.startswith(start_path):
        return False

    if exclude_patterns and any(pattern.search(target) for pattern in exclude_patterns):
        return False

    if include_patterns and not any(pattern.search(target) for pattern in include_patterns):
        return False

    return True


def _load_robots_policy(session, scheme: str, domain: str) -> tuple[RobotFileParser, str | None]:
    """Fetches and parses robots.txt for the site being crawled -- always
    on, not a caller-toggled option, same as the politeness pacing in
    fetcher.py. Mirrors the standard library's own RobotFileParser.read()
    convention for what a fetch failure means: 401/403 -> the whole site is
    off-limits (disallow_all), any other error (404, connection failure,
    timeout, ...) -> no robots.txt to restrict us (allow_all). This one
    fetch doesn't count toward max_pages/pages_traversed -- it's crawler
    policy, not a discovered page.

    Returns (policy, disallow_reason) -- disallow_reason is a human
    -readable explanation, non-None only when disallow_all just got set.
    Without this, a whole-site block from robots.txt made every
    subsequent page skip SILENTLY (dispatch()'s robots.txt check is a
    bare `continue`, by design, since an ordinary per-path Disallow rule
    isn't worth an error entry of its own) -- for a 401/403 specifically,
    that meant a crawl could come back as status "failed" with an empty
    errors list and no way to tell why. A real, reproduced case: a site
    behind Cloudflare returning 403 on /robots.txt itself (bot-challenge
    blocking the crawler's own request, not a deliberate policy from the
    site's real robots.txt), which this rule -- correctly, per the
    RobotFileParser convention it mirrors -- still treats as "site says
    stay out"."""
    policy = RobotFileParser()
    robots_url = f"{scheme}://{domain}/robots.txt"

    try:
        response = fetch(session, robots_url)
        policy.parse(response.text.splitlines())
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403):
            policy.disallow_all = True
            return policy, (
                f"'{robots_url}' returned {status} -- treating the whole site as "
                "off-limits (a 401/403 on robots.txt itself conventionally means "
                "\"don't crawl this site\", the same rule Python's own robotparser "
                "follows). If this is unexpected, the response may be a bot-challenge "
                "page (e.g. Cloudflare) rather than the site's real robots.txt policy."
            )
        policy.allow_all = True
    except (requests.RequestException, UnsafeURLError):
        # UnsafeURLError here would mean robots_url -- built from
        # start_url's own already-validated scheme+domain -- resolved
        # somewhere unsafe on THIS lookup despite start_url passing
        # earlier; same treatment as any other fetch failure.
        policy.allow_all = True

    return policy, None


def _discover_sitemap_urls(
    session,
    scheme: str,
    domain: str,
    robots_policy: RobotFileParser,
    path_specific_strip: dict[str, set[str]] | None,
    ignore_query_parameters: bool = False,
    allow_subdomains: bool = False,
) -> list[str]:
    """Seeds extra same-site URLs from ONE sitemap -- the first one robots.txt
    declares via a `Sitemap:` line, or the conventional /sitemap.xml if it
    declares none. Deliberately scoped to a single, non-index sitemap file:
    a real sitemap can be a <sitemapindex> pointing at many child sitemaps,
    which this does not follow -- chasing an index is a bigger feature than
    "read the sitemap," not attempted here. Never raises: a missing or
    unparseable sitemap just means nothing extra to seed, not a crawl
    failure."""
    declared = robots_policy.site_maps()
    sitemap_url = declared[0] if declared else f"{scheme}://{domain}/sitemap.xml"

    try:
        response = fetch(session, sitemap_url)
    except (requests.RequestException, UnsafeURLError):
        return []

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError:
        logger.debug("Sitemap at %s is not valid XML, ignoring", sitemap_url)
        return []

    urls = []

    for element in root.iter():
        # Namespace-agnostic: a real sitemap's tags are namespaced
        # (e.g. "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"), and
        # ElementTree keeps that namespace as part of .tag.
        if element.tag.endswith("loc") and element.text:
            clean_url = normalize_url(element.text.strip(), path_specific_strip, ignore_query_parameters)
            if is_same_site(urlparse(clean_url).netloc, domain, allow_subdomains):
                urls.append(clean_url)

    return urls


def crawl_stream(
    start_url: str,
    max_pages: int | None = 10,
    max_depth: int | None = None,
    path_specific_strip: dict[str, set[str]] | None = None,
    timeout_seconds: float | None = None,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    regex_on_full_url: bool = False,
    restrict_to_start_path: bool = False,
    allow_subdomains: bool = False,
    allow_external_links: bool = False,
    ignore_query_parameters: bool = False,
    ignore_robots_txt: bool = False,
    max_concurrency: int = 1,
    delay_seconds: float | None = None,
):
    """The traversal engine, as a generator of progress events -- crawl()
    below is just this, exhausted for its final event. Split out for the
    same reason content_extraction/website_processing's streaming pieces
    were: a caller waiting on the WHOLE crawl before hearing about even
    the first discovered URL has no way to show real progress, and a BFS
    crawl of a real site commonly takes several seconds with nothing to
    report until it's entirely done.

    Yields {"event": "url_discovered", "url": str, "count": int} once per
    URL as it's added to the crawl's output (same moment crawl()'s old
    discovered_output.append() ran), then finally
    {"event": "complete", "result": {"urls": [...], "pages_traversed": N,
    "errors": [...]}} -- the exact dict crawl() has always returned.

    path_specific_strip: optional site-specific noisy query params to
    strip, e.g. {"/feedback/realpython-com/": {"d"}}. See
    link_extraction.normalize_url() -- kept as an explicit argument here
    rather than hardcoded, since this is meant to work for any site, not
    just the one quirk we've seen so far.

    timeout_seconds: an optional wall-clock budget for the whole crawl,
    checked the same way max_pages is -- before starting the next page,
    never by interrupting a fetch already in flight. None (the default)
    means unbounded, same as max_depth; max_pages alone can still take a
    long time on a slow site, since it says nothing about how long each
    page takes.

    include_paths / exclude_paths: regex patterns (matched against a
    candidate URL's path, or the full URL if regex_on_full_url=True) that
    gate whether a discovered link or sitemap URL is queued for
    traversal at all -- never applied to start_url itself, which is
    always crawled. exclude wins when both match. Checked once, before a
    URL ever reaches the queue, so an out-of-scope link never costs a
    wasted HTTP request.

    restrict_to_start_path: when True, only URLs whose path starts with
    start_url's own path are queued -- e.g. starting a crawl at
    "/docs/" stays under "/docs/" instead of the whole site. Off by
    default (whole-domain crawl), matching this crawler's behavior
    before this option existed.

    allow_subdomains: widens same-site matching (see
    link_extraction.is_same_site()) so blog.example.com,
    docs.example.com, etc. all count as the current site instead of
    just a leading "www." alias.

    allow_external_links: when True, a link to a different site is still
    recorded as a discovered URL, but as a leaf -- fetched once (to
    confirm it resolves and follow any redirect), never parsed for its
    own links or canonical tag, and never expanded further. Off by
    default, matching this crawler's site-boundary behavior before this
    option existed: an external link (or an internal page that redirects
    externally) is simply dropped. Note: this crawl's own robots.txt
    policy (loaded for start_url's domain) is never applied to an
    external URL -- checking a *different* site's robots.txt would mean
    fetching and caching a policy per external domain, out of scope for
    what is deliberately a one-hop, unexpanded record.

    ignore_query_parameters: when True, every URL's query string is
    dropped entirely during normalization (traversal identity, output
    identity, and link discovery all use the query-stripped form) --
    for a caller who knows query params never distinguish a genuinely
    different page on this site. See link_extraction.normalize_url().

    ignore_robots_txt: when True, robots.txt is still fetched (its
    sitemap declarations are still useful) but never enforced -- every
    same-site URL is treated as allowed. Off by default: this crawler
    obeys robots.txt unconditionally unless a caller explicitly opts out.

    max_concurrency: how many pages get fetched at once instead of one
    at a time. 1 (the default) is the original strictly-sequential
    behavior. Only the network fetch itself runs on a worker thread --
    everything that touches shared traversal state (the queue, seen/
    visited sets, browser rendering, output) still runs on this
    generator's own thread, one completed fetch at a time, so none of it
    needs a lock. The one honestly-documented trade-off: two same-site
    URLs that both redirect to the same final destination can both be
    in flight at once (at max_concurrency > 1) before either has
    resolved, costing one wasted duplicate fetch -- correctness isn't
    affected (the existing "already traversed" check after each fetch
    still catches it), just a small amount of wasted work, and only above
    the sequential default.

    delay_seconds: an explicit pause between fetches, overriding
    fetcher.py's default pacing. Passing this FORCES max_concurrency
    back to 1, the same rule Firecrawl's own delay/maxConcurrency follow
    -- "wait N seconds between each one" only means something one fetch
    at a time.

    The final event's result is internal traversal data, NOT the public
    API contract -- shaping it into a {status, start_url, discovered_urls,
    ...} response is discover_urls_stream()'s job, not this function's:
    this only ever records EXPECTED per-page failures (a RequestException)
    and keeps going -- it never decides what those failures mean for the
    crawl as a whole, and it never catches anything else. An unexpected
    exception here is meant to propagate out to discover_urls_stream()."""
    if delay_seconds is not None:
        max_concurrency = 1

    start_url = normalize_url(start_url, path_specific_strip, ignore_query_parameters)

    # Validated once, up front, rather than only where fetch() happens to
    # be called from -- a caller asking to crawl a loopback/private/
    # link-local/metadata target should get one clean failure, not a
    # confusing error surfacing from deep inside robots.txt/sitemap
    # fetching. Left uncaught here on purpose: this propagates out to
    # discover_urls_stream()'s own except Exception, which turns it into
    # a normal status: "failed" result -- the same path a totally-
    # unreachable start_url already takes.
    assert_safe_url(start_url)

    start_parsed = urlparse(start_url)
    start_domain = start_parsed.netloc
    start_path = start_parsed.path or "/"

    include_patterns = _compile_path_patterns(include_paths)
    exclude_patterns = _compile_path_patterns(exclude_paths)

    def in_scope(url: str) -> bool:
        return _in_scope(url, include_patterns, exclude_patterns, regex_on_full_url, start_path, restrict_to_start_path)

    session = new_session()

    robots_policy, robots_disallow_reason = _load_robots_policy(session, start_parsed.scheme, start_domain)
    sitemap_urls = _discover_sitemap_urls(
        session, start_parsed.scheme, start_domain, robots_policy, path_specific_strip,
        ignore_query_parameters, allow_subdomains,
    )

    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds

    # Each queue entry carries its depth and whether it was reached via an
    # external (cross-site) link alongside the URL: start_url is depth 0,
    # not external; pages it links to are depth 1, pages those link to
    # are depth 2, and so on. Sitemap-sourced URLs are seeded at depth 0
    # too -- they're a direct hint from the site itself, not something
    # reached by following a link, so they shouldn't be penalized as
    # "deeper." Sitemap URLs are never external -- _discover_sitemap_urls()
    # already filters to same-site only.
    queue = deque([(start_url, 0, False)])

    # URLs already added to the queue.
    # Prevents the same URL being queued multiple times.
    seen = {start_url}

    for sitemap_url in sitemap_urls:
        if sitemap_url not in seen and in_scope(sitemap_url):
            seen.add(sitemap_url)
            queue.append((sitemap_url, 0, False))

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
    #
    # Seeded with the robots.txt block reason, if there was one -- every
    # subsequent per-page robots.txt skip in dispatch() below stays a
    # silent `continue` (an ordinary per-path Disallow rule isn't worth
    # its own error entry), but a whole-SITE 401/403 block deserves one
    # explicit entry explaining why nothing got crawled, instead of a
    # "failed" result with nothing in errors to say why. Skipped when
    # ignore_robots_txt=True -- the crawl proceeds anyway in that case,
    # so surfacing this would just be a confusing, irrelevant message.
    errors = (
        [{"url": start_url, "error": robots_disallow_reason}]
        if robots_disallow_reason and not ignore_robots_txt
        else []
    )

    # Browser lifecycle for this crawl: launched lazily (most sites never
    # need it), reused across every page that does, and closed once at the
    # end -- not started/stopped per page, which would pay Chromium's
    # startup cost over and over. browser_unavailable is sticky: once the
    # LAUNCH itself fails, stop trying for the rest of this crawl instead
    # of re-attempting (and re-failing) on every subsequent page.
    playwright_cm = None
    browser = None
    browser_unavailable = False
    browser_render_count = 0

    # deadline_logged: dispatch() below is called repeatedly (once before
    # the drain loop, once after each batch of completions), and each call
    # re-checks the deadline once -- this just keeps the "stopping crawl"
    # debug line to a single log line instead of one per dispatch() call
    # once the deadline has passed.
    deadline_logged = False

    def dispatch(executor, in_flight: dict) -> None:
        """Fills available concurrency slots from the queue -- pops,
        applies the same robots.txt/already-visited pre-checks the old
        sequential loop applied before every fetch, and submits a fetch
        for anything that survives both. Only the network fetch itself
        runs on a worker thread; queue/seen/visited/in_flight are only
        ever touched from this generator's own thread (dispatch() and the
        drain loop below both run here), so none of them need a lock."""
        nonlocal deadline_logged

        if deadline is not None and time.monotonic() >= deadline:
            if not deadline_logged:
                logger.debug("Wall-clock timeout reached, stopping crawl (%.0fs budget)", timeout_seconds)
                deadline_logged = True
            return

        while (
            queue
            and len(in_flight) < max_concurrency
            # in-flight fetches count toward the budget too, so a burst of
            # dispatches doesn't launch far more fetches than max_pages
            # could ever end up needing.
            and (max_pages is None or len(visited_traversal) + len(in_flight) < max_pages)
        ):
            current_url, depth, queued_as_external = queue.popleft()

            # robots_policy was loaded for start_url's domain -- it has
            # nothing valid to say about an external URL, so it's never
            # consulted for one, regardless of ignore_robots_txt.
            if (
                not queued_as_external
                and not ignore_robots_txt
                and not robots_policy.can_fetch(ROBOTS_USER_AGENT, current_url)
            ):
                logger.debug("Disallowed by robots.txt: %s", current_url)
                continue

            if current_url in visited_traversal:
                # Already reached this exact URL earlier -- e.g. it was
                # sitting in the queue when a DIFFERENT queued URL redirected
                # to it and got marked visited first. Don't waste an HTTP
                # request confirming what we already know. Note: under
                # concurrency (max_concurrency > 1), a second URL that
                # redirects to the same destination CAN still slip past
                # this check while the first is still in flight -- the
                # "Already traversed" check further down catches that
                # case instead, at the cost of one wasted duplicate fetch,
                # never a correctness problem.
                continue

            logger.debug("Visiting (depth %d): %s", depth, current_url)
            future = executor.submit(fetch, session, current_url, delay_seconds)
            in_flight[future] = (current_url, depth, queued_as_external)

    try:
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            in_flight: dict = {}
            dispatch(executor, in_flight)

            while in_flight:
                done, _ = wait_futures(in_flight, return_when=FIRST_COMPLETED)

                for future in done:
                    current_url, depth, queued_as_external = in_flight.pop(future)

                    try:
                        response = future.result()
                    except (requests.RequestException, UnsafeURLError) as exc:
                        # UnsafeURLError (a discovered link resolving to a
                        # loopback/private/link-local/metadata address, or
                        # redirecting to one) is treated exactly like any
                        # other per-page fetch failure -- recorded, crawl
                        # continues. A malicious or misconfigured link on
                        # someone else's page is an expected thing a real
                        # crawl can encounter, not a bug in this code.
                        logger.warning("Failed to fetch %s: %s", current_url, exc)
                        errors.append({"url": current_url, "error": _friendly_fetch_error(current_url, exc)})
                        continue

                    # The server may have redirected us -- the final destination,
                    # not the URL we requested, is this page's identity so far.
                    final_url = normalize_url(response.url, path_specific_strip, ignore_query_parameters)
                    final_domain = urlparse(final_url).netloc

                    # Same-site checking happens twice: once when a link is
                    # discovered (extract_links() below only returns links matching
                    # the CURRENT page's domain, unless allow_external_links widens
                    # that), and again here, because a redirect can move us outside
                    # the crawl boundary even when the URL we REQUESTED was
                    # legitimately in scope -- e.g.
                    # realpython.com/merch -> realpython.threadless.com. The
                    # requested URL is already in `seen` (it got there before being
                    # queued), so it won't be retried.
                    page_is_external = not is_same_site(final_domain, start_domain, allow_subdomains)

                    if page_is_external and not allow_external_links:
                        # Default behavior, unchanged: the external destination is
                        # never recorded or expanded.
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

                    if page_is_external:
                        # allow_external_links=True and we got here: record it as a
                        # discovered URL, but as a leaf -- never parsed for its own
                        # canonical tag or links, never expanded. One HTTP request
                        # (the one that just ran) is the full cost of an external
                        # URL, same as Firecrawl's "scraped once without further
                        # link discovery."
                        if final_url not in output_seen:
                            output_seen.add(final_url)
                            discovered_output.append(final_url)
                            yield {"event": "url_discovered", "url": final_url, "count": len(discovered_output)}
                        continue

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

                    # page_html is what canonical/link extraction below actually
                    # reads -- defaults to the raw HTTP HTML, but gets replaced
                    # with a rendered version when this page looks like an
                    # unrendered SPA shell, we haven't hit this crawl's render
                    # cap, and a browser is available (or can still be launched).
                    # A rendered page is treated as a full replacement, not merged
                    # with the raw HTML -- the rendered DOM already contains
                    # whatever the raw HTML had, plus whatever JS added.
                    page_html = response.text

                    if (
                        is_html_page
                        and not browser_unavailable
                        and browser_render_count < MAX_BROWSER_RENDERS_PER_CRAWL
                        and should_render_with_browser(response.text)
                    ):
                        try:
                            if browser is None:
                                playwright_cm = sync_playwright().start()
                                browser = playwright_cm.chromium.launch(headless=True)

                            page_html = render_page_html(browser, response.url)
                            browser_render_count += 1
                            logger.debug("Rendered with browser (%d/%d): %s",
                                         browser_render_count, MAX_BROWSER_RENDERS_PER_CRAWL, final_url)
                        except Exception as exc:
                            logger.warning("Browser render failed for %s: %s", final_url, exc)
                            if browser is None:
                                # The LAUNCH itself failed (missing Chromium
                                # install, etc.) -- give up on browser rendering
                                # for the rest of this crawl rather than retrying
                                # (and re-failing) on every subsequent page.
                                browser_unavailable = True
                            # page_html already defaults to the raw HTML above --
                            # this page's discovery still proceeds on that basis.

                    # The preferred URL to REPORT for this page -- starts as
                    # final_url, but a same-site canonical (independent of any HTTP
                    # redirect) can override it. E.g. /articles/page/2/ and
                    # /articles/page/3/ both traverse separately, but if both declare
                    # canonical=/articles/, they should all report as one output URL.
                    output_url = final_url

                    canonical_url = extract_canonical(page_html, response.url) if is_html_page else None

                    if canonical_url:
                        canonical_url = normalize_url(canonical_url, path_specific_strip, ignore_query_parameters)
                        canonical_domain = urlparse(canonical_url).netloc

                        logger.debug("Canonical: %s -> %s", final_url, canonical_url)

                        if is_same_site(canonical_domain, start_domain, allow_subdomains):
                            output_url = canonical_url

                    if output_url not in output_seen:
                        output_seen.add(output_url)
                        discovered_output.append(output_url)
                        yield {"event": "url_discovered", "url": output_url, "count": len(discovered_output)}

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
                    same_site_links, external_links = extract_links(
                        page_html,
                        response.url,
                        path_specific_strip,
                        ignore_query_parameters,
                        allow_subdomains,
                        allow_external_links,
                    )

                    for link in same_site_links:
                        if link in seen:
                            continue
                        if not in_scope(link):
                            continue

                        seen.add(link)
                        queue.append((link, depth + 1, False))

                    for link in external_links:
                        # include/exclude/restrict_to_start_path describe THIS
                        # site's own path structure -- they say nothing about a
                        # different domain's paths, so they're never applied here.
                        if link in seen:
                            continue

                        seen.add(link)
                        queue.append((link, depth + 1, True))

                dispatch(executor, in_flight)
    finally:
        if browser is not None:
            browser.close()
        if playwright_cm is not None:
            playwright_cm.stop()

    yield {
        "event": "complete",
        "result": {
            "urls": discovered_output,
            "pages_traversed": len(visited_traversal),
            "errors": errors,
        },
    }


def crawl(
    start_url: str,
    max_pages: int | None = 10,
    max_depth: int | None = None,
    path_specific_strip: dict[str, set[str]] | None = None,
    timeout_seconds: float | None = None,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    regex_on_full_url: bool = False,
    restrict_to_start_path: bool = False,
    allow_subdomains: bool = False,
    allow_external_links: bool = False,
    ignore_query_parameters: bool = False,
    ignore_robots_txt: bool = False,
    max_concurrency: int = 1,
    delay_seconds: float | None = None,
) -> dict:
    """Non-streaming convenience wrapper, same contract this had before
    streaming existed -- exhausts crawl_stream() and returns just its
    final result. See crawl_stream() for what each parameter does."""
    for event in crawl_stream(
        start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        path_specific_strip=path_specific_strip,
        timeout_seconds=timeout_seconds,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        regex_on_full_url=regex_on_full_url,
        restrict_to_start_path=restrict_to_start_path,
        allow_subdomains=allow_subdomains,
        allow_external_links=allow_external_links,
        ignore_query_parameters=ignore_query_parameters,
        ignore_robots_txt=ignore_robots_txt,
        max_concurrency=max_concurrency,
        delay_seconds=delay_seconds,
    ):
        if event["event"] == "complete":
            return event["result"]


def discover_urls_stream(
    start_url: str,
    max_pages: int | None = 10,
    max_depth: int | None = None,
    path_specific_strip: dict[str, set[str]] | None = None,
    timeout_seconds: float | None = None,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    regex_on_full_url: bool = False,
    restrict_to_start_path: bool = False,
    allow_subdomains: bool = False,
    allow_external_links: bool = False,
    ignore_query_parameters: bool = False,
    ignore_robots_txt: bool = False,
    max_concurrency: int = 1,
    delay_seconds: float | None = None,
):
    """The feature-level streaming entry point -- crawl_stream() is the
    traversal engine; this is the contract + safety boundary around it,
    same division as discover_urls() always had: it decides what a
    crawl's outcome MEANS (success/partial/failed) and guarantees nothing
    ever raises out of here, the same lesson from tech_detection's
    pipeline.py (a caller of an API can't be expected to catch arbitrary
    Python exceptions -- it needs one predictable response shape either
    way).

    Passes every "url_discovered" event through unchanged, then yields
    its OWN "complete" event carrying the full public contract --
    {status, start_url, discovered_urls, pages_traversed, errors} -- the
    same shape discover_urls() has always returned. See crawl_stream()
    for what each parameter does.

    crawl_stream() itself only ever records expected per-page failures
    (RequestException) and keeps going. Anything else escaping it -- a
    real bug, not a bad page -- is caught here and reported the same way
    a totally-unreachable start_url would be: status "failed"."""
    try:
        result = None
        for event in crawl_stream(
            start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            path_specific_strip=path_specific_strip,
            timeout_seconds=timeout_seconds,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            regex_on_full_url=regex_on_full_url,
            restrict_to_start_path=restrict_to_start_path,
            allow_subdomains=allow_subdomains,
            allow_external_links=allow_external_links,
            ignore_query_parameters=ignore_query_parameters,
            ignore_robots_txt=ignore_robots_txt,
            max_concurrency=max_concurrency,
            delay_seconds=delay_seconds,
        ):
            if event["event"] == "url_discovered":
                yield event
            else:
                result = event["result"]
    except Exception as exc:
        yield {
            "event": "complete",
            "result": {
                "status": "failed",
                "start_url": start_url,
                "discovered_urls": [],
                "pages_traversed": 0,
                "errors": [{"url": start_url, "error": str(exc)}],
            },
        }
        return

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

    yield {
        "event": "complete",
        "result": {
            "status": status,
            "start_url": start_url,
            "discovered_urls": result["urls"],
            "pages_traversed": result["pages_traversed"],
            "errors": result["errors"],
        },
    }


def discover_urls(
    start_url: str,
    max_pages: int | None = 10,
    max_depth: int | None = None,
    path_specific_strip: dict[str, set[str]] | None = None,
    timeout_seconds: float | None = None,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    regex_on_full_url: bool = False,
    restrict_to_start_path: bool = False,
    allow_subdomains: bool = False,
    allow_external_links: bool = False,
    ignore_query_parameters: bool = False,
    ignore_robots_txt: bool = False,
    max_concurrency: int = 1,
    delay_seconds: float | None = None,
) -> dict:
    """Non-streaming convenience wrapper, same contract this had before
    streaming existed -- exhausts discover_urls_stream() and returns just
    its final result. See crawl_stream() for what each parameter does."""
    for event in discover_urls_stream(
        start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        path_specific_strip=path_specific_strip,
        timeout_seconds=timeout_seconds,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        regex_on_full_url=regex_on_full_url,
        restrict_to_start_path=restrict_to_start_path,
        allow_subdomains=allow_subdomains,
        allow_external_links=allow_external_links,
        ignore_query_parameters=ignore_query_parameters,
        ignore_robots_txt=ignore_robots_txt,
        max_concurrency=max_concurrency,
        delay_seconds=delay_seconds,
    ):
        if event["event"] == "complete":
            return event["result"]


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
