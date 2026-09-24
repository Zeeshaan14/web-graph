# Every existing route test in this directory calls the real API
# repeatedly (many times per file) against a shared, module-level
# TestClient -- from TestClient's own perspective, every one of those
# requests comes from the same "testclient" pseudo-host. Without this,
# a big test run would trip api.rate_limiting.rate_limit's real 30/minute
# default purely as a side effect of the test suite's own request volume,
# nothing to do with whatever each test is actually checking.
#
# Auth (api.auth.require_api_key) is already a no-op with the default
# API_KEY=None, so it doesn't strictly need overriding here too -- but
# overriding both keeps this file the one place a future test author
# looks to understand why route tests don't need to think about either
# one. tests/api/test_auth_and_rate_limiting.py restores the real
# dependencies to test them directly.

import pytest

from api.main import app
from api.auth import require_api_key
from api.rate_limiting import rate_limit


@pytest.fixture(autouse=True)
def _bypass_auth_and_rate_limiting():
    app.dependency_overrides[require_api_key] = lambda: None
    app.dependency_overrides[rate_limit] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_api_key, None)
        app.dependency_overrides.pop(rate_limit, None)
