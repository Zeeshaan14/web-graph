# Shared mocking helper for url_discovery tests: builds a fake
# requests.Session.get() replacement from a simple {requested_url: (final_url,
# html)} map, so crawler tests can define a tiny fake "site" without any
# real network I/O.

from unittest.mock import MagicMock

import requests


def make_not_found_response(url):
    """A 404 shell response, for URLs crawl() fetches as infrastructure
    (robots.txt, sitemap.xml) rather than as a page a test set up -- their
    absence is a normal, non-fatal case (allow everything / nothing extra
    to seed), not a reason for a test's fake_get to blow up."""
    response = MagicMock()
    response.status_code = 404
    response.url = url
    response.text = ""
    response.headers = {}
    error = requests.HTTPError("404 error")
    error.response = response
    response.raise_for_status.side_effect = error
    return response


def make_fake_get(pages, call_log=None):
    """pages: {requested_url: (final_url, html)}, (final_url, html, status_code),
    or (final_url, html, status_code, content_type).
    call_log, if given, gets every requested PAGE url appended to it in
    order -- robots.txt/sitemap.xml requests are deliberately excluded
    (see below), since call_log exists to assert on page-traversal
    control flow, and every test written before crawl() fetched either
    of those would otherwise need updating for a call it isn't testing.

    A robots.txt/sitemap.xml request NOT explicitly present in pages
    quietly 404s rather than raising KeyError -- crawl() always fetches
    both, and most tests here aren't testing robots.txt/sitemap behavior
    at all, so they'd otherwise all need a page they don't care about."""

    def fake_get(url, timeout=10):
        is_infra_request = url.endswith("/robots.txt") or url.endswith("/sitemap.xml")

        if call_log is not None and not is_infra_request:
            call_log.append(url)

        if url not in pages and is_infra_request:
            return make_not_found_response(url)

        entry = pages[url]
        final_url, html = entry[0], entry[1]
        status_code = entry[2] if len(entry) > 2 else 200
        content_type = entry[3] if len(entry) > 3 else None

        response = MagicMock()
        response.status_code = status_code
        response.url = final_url
        response.text = html
        response.headers = {"content-type": content_type} if content_type else {}

        if status_code >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
        else:
            response.raise_for_status.side_effect = None

        return response

    return fake_get
