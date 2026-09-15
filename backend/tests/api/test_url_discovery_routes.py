# Tests the API layer only: request validation, defaults/bounds
# enforcement, and response passthrough. Mocks discover_urls() entirely
# -- this file must NOT exercise real crawling logic (that's
# url_discovery's own suite's job). If these tests need to know about
# traversal/canonical behavior to pass, that's a sign business logic
# leaked into the API layer.

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

SUCCESS_RESULT = {
    "status": "success",
    "start_url": "https://example.com/",
    "discovered_urls": ["https://example.com/", "https://example.com/about/"],
    "pages_traversed": 2,
    "errors": [],
}

PARTIAL_RESULT = {
    "status": "partial",
    "start_url": "https://example.com/",
    "discovered_urls": ["https://example.com/"],
    "pages_traversed": 2,
    "errors": [{"url": "https://example.com/old-page/", "error": "404 Client Error"}],
}


class TestDiscoverUrlsRoute:
    def test_calls_discover_urls_with_submitted_params_and_returns_its_result(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            response = client.post(
                "/discover-urls",
                json={"url": "https://example.com/", "max_pages": 20, "max_depth": 2},
            )

        mock_discover.assert_called_once_with("https://example.com/", max_pages=20, max_depth=2)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["discovered_urls"] == SUCCESS_RESULT["discovered_urls"]

    def test_max_pages_and_max_depth_are_optional_and_default(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post("/discover-urls", json={"url": "https://example.com/"})

        mock_discover.assert_called_once_with("https://example.com/", max_pages=10, max_depth=None)

    def test_passes_through_a_partial_result_as_200_not_500(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=PARTIAL_RESULT):
            response = client.post("/discover-urls", json={"url": "https://example.com/"})

        assert response.status_code == 200
        assert response.json()["status"] == "partial"
        assert response.json()["errors"][0]["url"] == "https://example.com/old-page/"

    def test_missing_url_is_rejected_before_discover_urls_is_called(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post("/discover-urls", json={})

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_max_pages_above_the_cap_is_rejected(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post("/discover-urls", json={"url": "https://example.com/", "max_pages": 101})

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_max_pages_below_one_is_rejected(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post("/discover-urls", json={"url": "https://example.com/", "max_pages": 0})

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_max_pages_unbounded_null_is_rejected(self):
        # The API must NOT expose the library's own max_pages=None
        # (unbounded) option -- that's the exact abuse vector this cap
        # exists to prevent.
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post("/discover-urls", json={"url": "https://example.com/", "max_pages": None})

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_negative_max_depth_is_rejected(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post("/discover-urls", json={"url": "https://example.com/", "max_depth": -1})

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_max_depth_null_is_allowed(self):
        # Unlike max_pages, unbounded DEPTH is safe -- max_pages already
        # caps total requests regardless of how deep the crawl goes.
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            response = client.post("/discover-urls", json={"url": "https://example.com/", "max_depth": None})

        mock_discover.assert_called_once_with("https://example.com/", max_pages=10, max_depth=None)
        assert response.status_code == 200
