# Root conftest.py: having this file here (next to pyproject.toml, with no
# __init__.py anywhere) makes pytest add the project root to sys.path, so
# every test file can `from engine import ...` etc. regardless of which
# subdirectory it lives in.

from unittest.mock import patch

import pytest

# A fake, always-succeeds getaddrinfo() returning a benign public IP,
# regardless of hostname -- security.ssrf_guard.assert_safe_url() now runs
# ahead of nearly every fetch in this codebase (see safe_get() in
# tech_detection/fetcher.py, url_discovery/fetcher.py, and
# content_extraction/content_extraction.py), so without this, every one
# of those tests would need real network access just to resolve
# "example.com" and friends before ever reaching the mocked HTTP layer
# they're actually testing.
_FAKE_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]


@pytest.fixture(autouse=True)
def _fake_dns_resolution(request):
    """Autouse for every OFFLINE test (the default -- see this file's
    `-m 'not network'` addopts) so no test has to remember to patch this
    itself. A test marked `network` (real DNS/HTTP on purpose, e.g.
    tests/security/test_ssrf_guard.py's TestRealNetwork) opts out and
    hits real DNS as intended. A test that specifically wants to
    exercise a REAL resolution failure (see
    tests/url_discovery/test_crawler.py's DNS-failure tests) patches
    security.ssrf_guard.socket.getaddrinfo itself, locally, which simply
    overrides this outer patch for the duration of that one test."""
    if request.node.get_closest_marker("network"):
        yield
        return

    with patch("security.ssrf_guard.socket.getaddrinfo", return_value=_FAKE_ADDRINFO):
        yield
