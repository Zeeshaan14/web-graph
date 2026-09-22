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

# The default value of every new crawl-scope option -- appended to an
# expected discover_urls() call whenever a test doesn't submit any of
# them itself, so this file doesn't have to spell out all eight on every
# unrelated assertion.
DEFAULT_SCOPE_KWARGS = {
    "include_paths": None,
    "exclude_paths": None,
    "regex_on_full_url": False,
    "restrict_to_start_path": False,
    "allow_subdomains": False,
    "allow_external_links": False,
    "ignore_query_parameters": False,
    "ignore_robots_txt": False,
}


class TestDiscoverUrlsRoute:
    def test_calls_discover_urls_with_submitted_params_and_returns_its_result(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            response = client.post(
                "/discover-urls",
                json={"url": "https://example.com/", "max_pages": 20, "max_depth": 2},
            )

        mock_discover.assert_called_once_with(
            "https://example.com/",
            max_pages=20,
            max_depth=2,
            path_specific_strip=None,
            timeout_seconds=60.0,
            **DEFAULT_SCOPE_KWARGS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["discovered_urls"] == SUCCESS_RESULT["discovered_urls"]

    def test_max_pages_and_max_depth_are_optional_and_default(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post("/discover-urls", json={"url": "https://example.com/"})

        mock_discover.assert_called_once_with(
            "https://example.com/",
            max_pages=10,
            max_depth=None,
            path_specific_strip=None,
            timeout_seconds=60.0,
            **DEFAULT_SCOPE_KWARGS,
        )

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

        mock_discover.assert_called_once_with(
            "https://example.com/",
            max_pages=10,
            max_depth=None,
            path_specific_strip=None,
            timeout_seconds=60.0,
            **DEFAULT_SCOPE_KWARGS,
        )
        assert response.status_code == 200


class TestTimeoutSecondsValidation:
    def test_defaults_to_sixty_seconds(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post("/discover-urls", json={"url": "https://example.com/"})

        assert mock_discover.call_args.kwargs["timeout_seconds"] == 60.0

    def test_custom_timeout_is_forwarded(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post("/discover-urls", json={"url": "https://example.com/", "timeout_seconds": 30})

        assert mock_discover.call_args.kwargs["timeout_seconds"] == 30.0

    def test_above_the_cap_is_rejected(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post(
                "/discover-urls", json={"url": "https://example.com/", "timeout_seconds": 301}
            )

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_below_one_second_is_rejected(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post(
                "/discover-urls", json={"url": "https://example.com/", "timeout_seconds": 0}
            )

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_unbounded_null_is_rejected(self):
        # Same reasoning as max_pages -- a public endpoint must not expose
        # the library's own "no time limit" option.
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post(
                "/discover-urls", json={"url": "https://example.com/", "timeout_seconds": None}
            )

        mock_discover.assert_not_called()
        assert response.status_code == 422


class TestPathSpecificStripValidation:
    def test_defaults_to_none(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post("/discover-urls", json={"url": "https://example.com/"})

        assert mock_discover.call_args.kwargs["path_specific_strip"] is None

    def test_submitted_lists_are_converted_to_sets_before_reaching_discover_urls(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post(
                "/discover-urls",
                json={
                    "url": "https://example.com/",
                    "path_specific_strip": {"/feedback/": ["d", "ref"]},
                },
            )

        forwarded = mock_discover.call_args.kwargs["path_specific_strip"]
        assert forwarded == {"/feedback/": {"d", "ref"}}
        assert isinstance(forwarded["/feedback/"], set)


class TestScopeControlOptions:
    def test_defaults_match_prior_behavior(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post("/discover-urls", json={"url": "https://example.com/"})

        for key, value in DEFAULT_SCOPE_KWARGS.items():
            assert mock_discover.call_args.kwargs[key] == value

    def test_submitted_scope_options_are_forwarded(self):
        with patch("api.routes.url_discovery.discover_urls", return_value=SUCCESS_RESULT) as mock_discover:
            client.post(
                "/discover-urls",
                json={
                    "url": "https://example.com/",
                    "include_paths": ["^/blog/"],
                    "exclude_paths": ["draft"],
                    "regex_on_full_url": True,
                    "restrict_to_start_path": True,
                    "allow_subdomains": True,
                    "allow_external_links": True,
                    "ignore_query_parameters": True,
                    "ignore_robots_txt": True,
                },
            )

        kwargs = mock_discover.call_args.kwargs
        assert kwargs["include_paths"] == ["^/blog/"]
        assert kwargs["exclude_paths"] == ["draft"]
        assert kwargs["regex_on_full_url"] is True
        assert kwargs["restrict_to_start_path"] is True
        assert kwargs["allow_subdomains"] is True
        assert kwargs["allow_external_links"] is True
        assert kwargs["ignore_query_parameters"] is True
        assert kwargs["ignore_robots_txt"] is True

    def test_invalid_include_paths_regex_is_rejected_before_discover_urls_is_called(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post(
                "/discover-urls",
                json={"url": "https://example.com/", "include_paths": ["(unclosed"]},
            )

        mock_discover.assert_not_called()
        assert response.status_code == 422

    def test_invalid_exclude_paths_regex_is_rejected_before_discover_urls_is_called(self):
        with patch("api.routes.url_discovery.discover_urls") as mock_discover:
            response = client.post(
                "/discover-urls",
                json={"url": "https://example.com/", "exclude_paths": ["(unclosed"]},
            )

        mock_discover.assert_not_called()
        assert response.status_code == 422
