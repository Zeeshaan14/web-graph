# Tests the API layer only: request validation and response passthrough.
# Mocks extract_content() entirely -- this file must NOT exercise real
# HTML-parsing/boilerplate-stripping logic (that's content_extraction's
# own suite's job). If these tests need to know about article/main
# fallback behavior to pass, business logic leaked into the API layer.

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

SUCCESS_RESULT = {
    "status": "success",
    "url": "https://example.com/article",
    "title": "An Article",
    "headings": ["Intro", "Conclusion"],
    "paragraphs": ["First paragraph.", "Second paragraph."],
    "error": None,
}

FAILED_RESULT = {
    "status": "failed",
    "url": "https://example.com/missing",
    "title": None,
    "headings": [],
    "paragraphs": [],
    "error": "404 Client Error",
}


class TestExtractContentRoute:
    def test_calls_extract_content_with_the_submitted_url_and_returns_its_result(self):
        with patch(
            "api.routes.content_extraction.extract_content", return_value=SUCCESS_RESULT
        ) as mock_extract:
            response = client.post("/extract-content", json={"url": "https://example.com/article"})

        mock_extract.assert_called_once_with("https://example.com/article")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["title"] == "An Article"
        assert body["headings"] == SUCCESS_RESULT["headings"]
        assert body["paragraphs"] == SUCCESS_RESULT["paragraphs"]

    def test_passes_through_a_failed_result_as_200_not_500(self):
        # A "failed" extraction (404, non-HTML, connection error) is a
        # normal, well-formed API response -- not a server error.
        with patch("api.routes.content_extraction.extract_content", return_value=FAILED_RESULT):
            response = client.post("/extract-content", json={"url": "https://example.com/missing"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["error"] == "404 Client Error"
        assert body["headings"] == []
        assert body["paragraphs"] == []

    def test_missing_url_field_is_rejected_before_extract_content_is_called(self):
        with patch("api.routes.content_extraction.extract_content") as mock_extract:
            response = client.post("/extract-content", json={})

        mock_extract.assert_not_called()
        assert response.status_code == 422

    def test_route_does_not_alter_headings_or_paragraphs(self):
        with patch("api.routes.content_extraction.extract_content", return_value=SUCCESS_RESULT):
            response = client.post("/extract-content", json={"url": "https://example.com/article"})

        body = response.json()
        assert body["headings"] == SUCCESS_RESULT["headings"]
        assert body["paragraphs"] == SUCCESS_RESULT["paragraphs"]
