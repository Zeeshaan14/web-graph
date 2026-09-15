import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests
import trafilatura
from bs4 import BeautifulSoup

from .browser import render_page_html, should_render_with_browser

logger = logging.getLogger(__name__)

# A generous cap for an article/blog-post page, not a file download -- large
# enough that no real page we've tested against comes close, small enough
# that a mislinked video/archive/dump can't be pulled fully into memory.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# Same fix as url_discovery/fetcher.py's BROWSER_HEADERS -- some sites (we
# already saw this with realpython.com) reject requests that look like a
# bare script rather than a browser. Kept as its own local copy rather than
# imported from url_discovery: each feature package stays self-contained,
# so a change to one feature's HTTP behavior can't silently affect another.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Politeness pacing and 429 handling, applied to every fetch this module
# makes -- same values, same one-retry policy, and same reasoning as
# url_discovery/fetcher.py's REQUEST_DELAY_SECONDS/RETRY_FALLBACK_SECONDS.
# Duplicated rather than imported for the same self-containment reason as
# BROWSER_HEADERS above: this is what closes the README gap where
# website_processing's extraction phase called extract_content() once per
# URL back-to-back with none of the crawl phase's rate-limit protection --
# fixing it here, at the source of every HTTP call this module makes,
# means every caller (the standalone /extract-content endpoint included)
# gets it, not just the combined workflow.
REQUEST_DELAY_SECONDS = 1.0
RETRY_FALLBACK_SECONDS = 5.0


def _parse_retry_after(value: str | None) -> float | None:
    """Same parsing as url_discovery/fetcher.py's version: Retry-After is
    either a plain integer number of seconds, or an HTTP-date. Returns None
    if the header is absent or doesn't parse as either form."""
    if not value:
        return None

    value = value.strip()

    if value.isdigit():
        return float(value)

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)

    return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0)


def _fetch(url: str) -> requests.Response:
    """One polite GET: a controlled retry on 429 (Retry-After if present,
    otherwise a fallback backoff, then exactly one retry), and a pacing
    delay after every attempt regardless of outcome. Does NOT call
    raise_for_status() -- that's extract_content()'s job, same division as
    url_discovery: this owns fetching, the caller owns what a bad status
    means."""
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=10, stream=True)

        if response.status_code == 429:
            wait_seconds = _parse_retry_after(response.headers.get("Retry-After"))

            if wait_seconds is None:
                wait_seconds = RETRY_FALLBACK_SECONDS

            time.sleep(wait_seconds)

            response = requests.get(url, headers=BROWSER_HEADERS, timeout=10, stream=True)

        return response
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)


def _failed(url: str, error: str) -> dict:
    return {
        "status": "failed",
        "url": url,
        "title": None,
        "headings": [],
        "paragraphs": [],
        "error": error,
    }


def _decode_bounded(response: requests.Response, max_bytes: int) -> str | None:
    """Reads the response body in chunks, stopping (and returning None) the
    moment max_bytes is exceeded -- unlike a Content-Length header, this
    catches a body that's simply larger than declared or served without one
    at all. requests.Response.text isn't used here: it would already have
    buffered the whole thing into memory before we got a chance to check."""
    body = bytearray()

    for chunk in response.iter_content(chunk_size=65536):
        body.extend(chunk)
        if len(body) > max_bytes:
            return None

    charset_match = re.search(
        r"charset=([\w-]+)", response.headers.get("content-type", ""), re.IGNORECASE
    )
    encoding = charset_match.group(1) if charset_match else "utf-8"

    try:
        return bytes(body).decode(encoding, errors="replace")
    except LookupError:
        # An unrecognized charset name (typo'd or made up) -- fall back
        # rather than fail a page over a header we can't trust anyway.
        return bytes(body).decode("utf-8", errors="replace")


# Heading levels we report -- matches what the old hand-rolled selector
# collected (h1-h3, no h4-h6 subsection minutiae), even though
# trafilatura's own output can include deeper levels.
HEADING_LEVELS = {"h1", "h2", "h3"}


def _element_text(element) -> str:
    """Joins ALL of an element's text, including any nested inline
    elements (links, bold, ...) -- trafilatura's XML output is normally
    already flat plain text, but this is the same defensive join
    BeautifulSoup's get_text() gave us before, so nothing regresses if
    that's ever not true. Whitespace is collapsed the same way too."""
    return " ".join("".join(element.itertext()).split())


def extract_content(url: str):
    try:
        response = _fetch(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if "text/html" not in content_type.lower():
            return _failed(url, f"Response is not HTML: {content_type or 'unknown content type'}")

        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_RESPONSE_BYTES:
                    return _failed(
                        url,
                        f"Response too large: {content_length} bytes exceeds "
                        f"{MAX_RESPONSE_BYTES}-byte limit",
                    )
            except ValueError:
                pass  # not a valid integer -- fall through to the real cap below

        html = _decode_bounded(response, MAX_RESPONSE_BYTES)
        if html is None:
            return _failed(url, f"Response exceeded {MAX_RESPONSE_BYTES}-byte limit while downloading")

        # If the raw HTML looks like an unrendered app shell, replace it
        # with a browser-rendered version before extracting ANYTHING from
        # it -- title included, not just body content: once we've decided
        # the raw HTML doesn't represent the real page, there's no reason
        # to trust its <title> either (an SPA's static shell often has a
        # generic placeholder title, set for real only after JS runs). A
        # render failure isn't fatal -- html just stays the raw HTML and
        # extraction proceeds on that basis, same fallback shape as
        # url_discovery's per-page browser fallback.
        if should_render_with_browser(html):
            try:
                html = render_page_html(url)
            except Exception as exc:
                logger.warning("Browser render failed for %s: %s", url, exc)

        # Title comes straight from the HTML above -- this was never the
        # problem the Smashing Magazine gap was about, and it's
        # independent of whether trafilatura finds any body content.
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else None

        # trafilatura replaces the old hand-rolled article/main-picking +
        # script/style/nav/footer/aside-stripping logic entirely -- real
        # content-density scoring (link ratio, tag/class signals, DOM
        # structure) instead of "strip this fixed list of tag names and
        # hope." favor_precision=True is trafilatura's own documented
        # setting for biasing toward excluding borderline content rather
        # than maximizing recall -- matches our goal here, though it isn't
        # what makes the specific newsletter-CTA test below pass (that one
        # turns out to hold either way; the density scoring itself is
        # doing the real work there).
        extracted_xml = trafilatura.extract(
            html,
            url=url,
            output_format="xml",
            with_metadata=False,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )

        headings = []
        paragraphs = []

        if extracted_xml:
            main = ElementTree.fromstring(extracted_xml).find("main")
            if main is not None:
                headings = [
                    _element_text(el)
                    for el in main.iter("head")
                    if el.get("rend") in HEADING_LEVELS and _element_text(el)
                ]
                paragraphs = [
                    _element_text(el) for el in main.iter("p") if _element_text(el)
                ]

        return {
            "status": "success",
            "url": url,
            "title": title,
            "headings": headings,
            "paragraphs": paragraphs,
            "error": None,
        }

    except requests.RequestException as exc:
        return _failed(url, str(exc))


if __name__ == "__main__":
    url = "https://www.smashingmagazine.com/2021/12/core-web-vitals-case-study-smashing-magazine/"

    result = extract_content(url)

    # Scraped article text can contain characters a Windows terminal's
    # default cp1252 console can't print (curly quotes, arrows, etc.) --
    # same issue hit with browser.py's demo output earlier in this project.
    safe = {
        key: (value.encode("ascii", "replace").decode() if isinstance(value, str) else value)
        for key, value in result.items()
    }
    safe["headings"] = [h.encode("ascii", "replace").decode() for h in result["headings"]]
    safe["paragraphs"] = [p.encode("ascii", "replace").decode() for p in result["paragraphs"]]

    print(safe)
