# Owns network fetching only. No parsing, no detection knowledge.

import requests


def fetch_url(url: str):
    session = requests.Session()

    response = session.get(
        url,
        timeout=10,
    )

    return response, session
