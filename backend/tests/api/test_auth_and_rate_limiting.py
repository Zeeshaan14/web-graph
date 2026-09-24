# Tests the REAL require_api_key/rate_limit/concurrency dependencies --
# every other file in this directory relies on tests/api/conftest.py's
# autouse override to bypass both, so this is the one place they're
# actually exercised. Fully offline: detect_website_technologies() itself
# is mocked, since these tests are about the API-layer gate, not the
# feature behind it.

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.auth import require_api_key
from api.concurrency import _semaphore
from api.rate_limiting import _requests_by_ip, rate_limit
import api.config as config_module

SUCCESS_RESULT = {
    "url": "https://example.com/",
    "status": "success",
    "http_status": 200,
    "browser_status": "not_launched",
    "evidence_source": "http",
    "technologies": [],
    "errors": [],
}


@pytest.fixture(autouse=True)
def _use_real_dependencies():
    # Overrides these two specifically -- app.dependency_overrides is a
    # dict keyed by the dependency callable, so popping just these two
    # restores the REAL require_api_key/rate_limit for this file's own
    # tests without needing to touch anything else conftest.py set up
    # (there isn't anything else, but this stays correct if that changes).
    app.dependency_overrides.pop(require_api_key, None)
    app.dependency_overrides.pop(rate_limit, None)
    _requests_by_ip.clear()
    yield
    _requests_by_ip.clear()


client = TestClient(app)


class TestApiKeyAuth:
    def test_no_api_key_configured_allows_every_request(self):
        with patch.object(config_module.settings, "api_key", None), \
             patch("api.routes.tech_detection.detect_website_technologies", return_value=SUCCESS_RESULT):
            response = client.post("/detect-tech", json={"url": "https://example.com/"})

        assert response.status_code == 200

    def test_missing_header_is_rejected_when_a_key_is_configured(self):
        with patch.object(config_module.settings, "api_key", "secret123"):
            response = client.post("/detect-tech", json={"url": "https://example.com/"})

        assert response.status_code == 401

    def test_wrong_key_is_rejected(self):
        with patch.object(config_module.settings, "api_key", "secret123"):
            response = client.post(
                "/detect-tech",
                json={"url": "https://example.com/"},
                headers={"X-API-Key": "wrong"},
            )

        assert response.status_code == 401

    def test_correct_key_is_accepted(self):
        with patch.object(config_module.settings, "api_key", "secret123"), \
             patch("api.routes.tech_detection.detect_website_technologies", return_value=SUCCESS_RESULT):
            response = client.post(
                "/detect-tech",
                json={"url": "https://example.com/"},
                headers={"X-API-Key": "secret123"},
            )

        assert response.status_code == 200

    def test_health_never_requires_a_key(self):
        with patch.object(config_module.settings, "api_key", "secret123"):
            response = client.get("/health")

        assert response.status_code == 200


class TestRateLimiting:
    def test_requests_under_the_limit_all_succeed(self):
        with patch.object(config_module.settings, "rate_limit_per_minute", 5), \
             patch("api.routes.tech_detection.detect_website_technologies", return_value=SUCCESS_RESULT):
            for _ in range(5):
                response = client.post("/detect-tech", json={"url": "https://example.com/"})
                assert response.status_code == 200

    def test_the_request_past_the_limit_is_rejected_with_429(self):
        with patch.object(config_module.settings, "rate_limit_per_minute", 3), \
             patch("api.routes.tech_detection.detect_website_technologies", return_value=SUCCESS_RESULT):
            for _ in range(3):
                assert client.post("/detect-tech", json={"url": "https://example.com/"}).status_code == 200

            response = client.post("/detect-tech", json={"url": "https://example.com/"})

        assert response.status_code == 429

    def test_the_limit_is_per_route_group_shared_across_all_four_apis(self):
        # rate_limit keys purely by client IP, not by route -- a caller
        # can't dodge the cap by spreading requests across
        # /detect-tech, /discover-urls, etc.
        with patch.object(config_module.settings, "rate_limit_per_minute", 2), \
             patch("api.routes.tech_detection.detect_website_technologies", return_value=SUCCESS_RESULT), \
             patch("api.routes.content_extraction.extract_content", return_value={
                 "status": "success", "url": "https://example.com/", "title": None,
                 "content_markdown": "", "error": None,
             }):
            assert client.post("/detect-tech", json={"url": "https://example.com/"}).status_code == 200
            assert client.post("/extract-content", json={"url": "https://example.com/"}).status_code == 200

            response = client.post("/detect-tech", json={"url": "https://example.com/"})

        assert response.status_code == 429


class TestConcurrencyCap:
    def test_a_slot_is_released_after_a_successful_request_so_the_next_one_succeeds(self):
        with patch("api.routes.tech_detection.detect_website_technologies", return_value=SUCCESS_RESULT):
            first = client.post("/detect-tech", json={"url": "https://example.com/"})
            second = client.post("/detect-tech", json={"url": "https://example.com/"})

        assert first.status_code == 200
        assert second.status_code == 200

    def test_no_permanently_exhausted_server_wide_capacity_across_many_requests(self):
        # A regression guard for a leaked semaphore slot: if any single
        # request failed to release its slot, this many sequential
        # requests (well under MAX_CONCURRENT_REQUESTS' default of 10,
        # but more than one full acquire/release cycle) would eventually
        # start failing with 503s even though nothing is actually
        # running concurrently.
        with patch("api.routes.tech_detection.detect_website_technologies", return_value=SUCCESS_RESULT):
            for _ in range(20):
                response = client.post("/detect-tech", json={"url": "https://example.com/"})
                assert response.status_code == 200

    def test_server_busy_response_when_every_slot_is_already_taken(self):
        # Simulates every slot already being in use by another in-flight
        # request, without needing genuine thread concurrency to prove
        # the 503 path -- acquire every slot up front, then confirm the
        # next request is rejected, then release them all again so this
        # test doesn't leak state into whatever runs after it.
        acquired = 0
        while _semaphore.acquire(blocking=False):
            acquired += 1

        try:
            response = client.post("/detect-tech", json={"url": "https://example.com/"})
            assert response.status_code == 503
        finally:
            for _ in range(acquired):
                _semaphore.release()
