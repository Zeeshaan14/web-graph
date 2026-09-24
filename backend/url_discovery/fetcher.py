# Owns talking to the network for the crawler: a browser-shaped session,
# politeness pacing between requests, and one controlled retry on 429.
# crawler.py just calls fetch(session, url) and doesn't need to know any
# of these details -- same separation tech_detection/fetcher.py draws
# between "how we fetch" and "what we do with the result".

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from security.ssrf_guard import safe_get

# Some sites (realpython.com among them) reject requests that look like a
# bare script rather than a browser -- default `python-requests/x.x.x`
# gets a flat 403. A real browser sends a full header set, not just a
# User-Agent, so this matches that shape rather than just the one field.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Politeness pacing: a small gap after every request, regardless of
# outcome, so we're not hammering the server request after request.
REQUEST_DELAY_SECONDS = 1.0

# Used only when a 429 has no (or an unparsable) Retry-After header -- a
# modest wait, distinct from the routine pacing above.
RETRY_FALLBACK_SECONDS = 5.0


def new_session() -> requests.Session:
    """A reusable, browser-shaped session -- cookies and connections
    carry across requests within one crawl, closer to how a real browser
    session behaves site to site."""
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    return session


def _parse_retry_after(value: str | None) -> float | None:
    """Retry-After is either a plain integer number of seconds, or an
    HTTP-date (RFC 7231) naming when to retry. Returns None if the header
    is absent or doesn't parse as either form."""
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


def fetch(session: requests.Session, url: str, delay_seconds: float | None = None) -> requests.Response:
    """One polite GET: a controlled retry on 429 (Retry-After if present,
    otherwise a fallback backoff, then exactly one retry), and a pacing
    delay after every attempt regardless of outcome. Raises
    requests.RequestException if it's still failing after the retry --
    the caller skips and moves on, no further retries here.

    delay_seconds overrides the default REQUEST_DELAY_SECONDS pacing gap
    -- None (the default) keeps the standard pacing; a caller running
    fetch() concurrently across several worker threads passes its own
    per-call delay this way rather than mutating the module constant.

    Also raises security.ssrf_guard.UnsafeURLError -- via safe_get(), not
    a bare session.get() -- if url (or a redirect it leads to) resolves
    to a loopback/private/link-local/metadata address. Callers already
    handling RequestException for a per-page failure should handle this
    the same way: a discovered link pointing somewhere unsafe is a normal
    thing a real crawl can encounter, not a bug in this code."""
    try:
        response = safe_get(session, url, timeout=10)

        if response.status_code == 429:
            wait_seconds = _parse_retry_after(response.headers.get("Retry-After"))

            if wait_seconds is None:
                wait_seconds = RETRY_FALLBACK_SECONDS

            print(f"429 rate limited: {url} -- waiting {wait_seconds:.1f}s before one retry")
            time.sleep(wait_seconds)

            response = safe_get(session, url, timeout=10)

        response.raise_for_status()
        return response
    finally:
        # Pace every request attempt, success or failure -- this is
        # about the server's rate limit, not about our outcome.
        time.sleep(REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds)
