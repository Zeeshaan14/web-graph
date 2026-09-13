# Shared mocking helper for url_discovery tests: builds a fake
# requests.Session.get() replacement from a simple {requested_url: (final_url,
# html)} map, so crawler tests can define a tiny fake "site" without any
# real network I/O.

from unittest.mock import MagicMock

import requests


def make_fake_get(pages, call_log=None):
    """pages: {requested_url: (final_url, html)} or (final_url, html, status_code).
    call_log, if given, gets every requested URL appended to it in order."""

    def fake_get(url, timeout=10):
        if call_log is not None:
            call_log.append(url)

        entry = pages[url]
        final_url, html = entry[0], entry[1]
        status_code = entry[2] if len(entry) > 2 else 200

        response = MagicMock()
        response.status_code = status_code
        response.url = final_url
        response.text = html
        response.headers = {}

        if status_code >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
        else:
            response.raise_for_status.side_effect = None

        return response

    return fake_get
