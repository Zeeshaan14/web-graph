# Owns network fetching only. No parsing, no detection knowledge.

import requests

from security.ssrf_guard import safe_get


def fetch_url(url: str):
    session = requests.Session()

    # safe_get(), not session.get() -- validates url (and every redirect
    # hop it follows) isn't a loopback/private/link-local/metadata
    # address before fetching it. See security/ssrf_guard.py for why
    # this is a shared check, not duplicated per feature package like
    # this file's other helpers.
    response = safe_get(
        session,
        url,
        timeout=10,
    )

    return response, session
