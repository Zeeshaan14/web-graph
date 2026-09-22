# Tests the API layer only: request validation and response passthrough.
# Mocks discover_and_extract()/discover_and_extract_stream() entirely --
# this file must NOT exercise real discovery/extraction/status-combination
# logic (that's website_processing's own suite's job).

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

SUCCESS_RESULT = {
    "status": "success",
    "start_url": "https://example.com/",
    "discovery": {
        "status": "success",
        "start_url": "https://example.com/",
        "discovered_urls": ["https://example.com/", "https://example.com/about/"],
        "pages_traversed": 2,
        "errors": [],
    },
    "pages": [
        {
            "status": "success",
            "url": "https://example.com/",
            "title": "Home",
            "content_markdown": "# Welcome\n\nHello.",
            "error": None,
        },
        {
            "status": "success",
            "url": "https://example.com/about/",
            "title": "About",
            "content_markdown": "# About Us\n\nWe do things.",
            "error": None,
        },
    ],
    "shared_content_markdown": "",
}

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

FAILED_RESULT = {
    "status": "failed",
    "start_url": "https://example.com/",
    "discovery": {
        "status": "failed",
        "start_url": "https://example.com/",
        "discovered_urls": [],
        "pages_traversed": 0,
        "errors": [{"url": "https://example.com/", "error": "Connection timed out"}],
    },
    "pages": [],
    "shared_content_markdown": "",
}


class TestDiscoverAndExtractRoute:
    def test_calls_discover_and_extract_with_submitted_params_and_returns_its_result(self):
        with patch(
            "api.routes.website_processing.discover_and_extract", return_value=SUCCESS_RESULT
        ) as mock_call:
            response = client.post(
                "/discover-and-extract",
                json={"url": "https://example.com/", "max_pages": 20, "max_depth": 2},
            )

        mock_call.assert_called_once_with(
            "https://example.com/", max_pages=20, max_depth=2, **DEFAULT_SCOPE_KWARGS
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert len(body["pages"]) == 2
        assert body["discovery"]["pages_traversed"] == 2

    def test_max_pages_and_max_depth_are_optional_and_default(self):
        with patch(
            "api.routes.website_processing.discover_and_extract", return_value=SUCCESS_RESULT
        ) as mock_call:
            client.post("/discover-and-extract", json={"url": "https://example.com/"})

        mock_call.assert_called_once_with(
            "https://example.com/", max_pages=10, max_depth=None, **DEFAULT_SCOPE_KWARGS
        )

    def test_scope_options_are_forwarded(self):
        with patch(
            "api.routes.website_processing.discover_and_extract", return_value=SUCCESS_RESULT
        ) as mock_call:
            client.post(
                "/discover-and-extract",
                json={
                    "url": "https://example.com/",
                    "include_paths": ["^/blog/"],
                    "allow_subdomains": True,
                    "ignore_robots_txt": True,
                },
            )

        kwargs = mock_call.call_args.kwargs
        assert kwargs["include_paths"] == ["^/blog/"]
        assert kwargs["allow_subdomains"] is True
        assert kwargs["ignore_robots_txt"] is True

    def test_invalid_regex_is_rejected_before_discover_and_extract_is_called(self):
        with patch("api.routes.website_processing.discover_and_extract") as mock_call:
            response = client.post(
                "/discover-and-extract",
                json={"url": "https://example.com/", "exclude_paths": ["(unclosed"]},
            )

        mock_call.assert_not_called()
        assert response.status_code == 422

    def test_passes_through_a_failed_result_as_200_not_500(self):
        with patch("api.routes.website_processing.discover_and_extract", return_value=FAILED_RESULT):
            response = client.post("/discover-and-extract", json={"url": "https://example.com/"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["pages"] == []
        assert body["discovery"]["errors"][0]["error"] == "Connection timed out"

    def test_missing_url_is_rejected_before_discover_and_extract_is_called(self):
        with patch("api.routes.website_processing.discover_and_extract") as mock_call:
            response = client.post("/discover-and-extract", json={})

        mock_call.assert_not_called()
        assert response.status_code == 422

    def test_max_pages_above_the_cap_is_rejected(self):
        with patch("api.routes.website_processing.discover_and_extract") as mock_call:
            response = client.post(
                "/discover-and-extract", json={"url": "https://example.com/", "max_pages": 101}
            )

        mock_call.assert_not_called()
        assert response.status_code == 422

    def test_max_pages_unbounded_null_is_rejected(self):
        with patch("api.routes.website_processing.discover_and_extract") as mock_call:
            response = client.post(
                "/discover-and-extract", json={"url": "https://example.com/", "max_pages": None}
            )

        mock_call.assert_not_called()
        assert response.status_code == 422

    def test_route_does_not_alter_nested_discovery_or_pages_data(self):
        with patch("api.routes.website_processing.discover_and_extract", return_value=SUCCESS_RESULT):
            response = client.post("/discover-and-extract", json={"url": "https://example.com/"})

        body = response.json()
        assert body["discovery"]["discovered_urls"] == SUCCESS_RESULT["discovery"]["discovered_urls"]
        assert body["pages"] == SUCCESS_RESULT["pages"]


STREAM_EVENTS = [
    {"event": "discovery_started"},
    {"event": "discovery_done", "discovery": SUCCESS_RESULT["discovery"]},
    {"event": "page_fetched", "url": "https://example.com/", "status": "success"},
    {"event": "page_fetched", "url": "https://example.com/about/", "status": "success"},
    {"event": "dedup_done", "shared_content_markdown": ""},
    {"event": "page_rendered", "page": SUCCESS_RESULT["pages"][0]},
    {"event": "page_rendered", "page": SUCCESS_RESULT["pages"][1]},
    {"event": "complete", "result": SUCCESS_RESULT},
]


class TestDiscoverAndExtractStreamRoute:
    def test_calls_discover_and_extract_stream_with_submitted_params(self):
        with patch(
            "api.routes.website_processing.discover_and_extract_stream", return_value=iter(STREAM_EVENTS)
        ) as mock_call:
            response = client.post(
                "/discover-and-extract/stream",
                json={"url": "https://example.com/", "max_pages": 20, "max_depth": 2},
            )

        mock_call.assert_called_once_with(
            "https://example.com/", max_pages=20, max_depth=2, **DEFAULT_SCOPE_KWARGS
        )
        assert response.status_code == 200

    def test_response_is_one_json_object_per_line_in_order(self):
        with patch(
            "api.routes.website_processing.discover_and_extract_stream", return_value=iter(STREAM_EVENTS)
        ):
            response = client.post("/discover-and-extract/stream", json={"url": "https://example.com/"})

        lines = [line for line in response.text.splitlines() if line.strip()]
        parsed = [json.loads(line) for line in lines]
        assert parsed == STREAM_EVENTS

    def test_content_type_is_ndjson(self):
        with patch(
            "api.routes.website_processing.discover_and_extract_stream", return_value=iter(STREAM_EVENTS)
        ):
            response = client.post("/discover-and-extract/stream", json={"url": "https://example.com/"})

        assert response.headers["content-type"] == "application/x-ndjson"

    def test_final_line_is_a_complete_event_with_the_full_result(self):
        with patch(
            "api.routes.website_processing.discover_and_extract_stream", return_value=iter(STREAM_EVENTS)
        ):
            response = client.post("/discover-and-extract/stream", json={"url": "https://example.com/"})

        lines = [line for line in response.text.splitlines() if line.strip()]
        last_event = json.loads(lines[-1])
        assert last_event["event"] == "complete"
        assert last_event["result"] == SUCCESS_RESULT

    def test_missing_url_is_rejected_before_streaming_starts(self):
        with patch("api.routes.website_processing.discover_and_extract_stream") as mock_call:
            response = client.post("/discover-and-extract/stream", json={})

        mock_call.assert_not_called()
        assert response.status_code == 422
