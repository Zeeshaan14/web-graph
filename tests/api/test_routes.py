# Tests the API layer only: request validation and response shape.
# Mocks detect_website_technologies() entirely -- this file must NOT
# exercise real detection logic (that's tech_detection's own suite's
# job). If these tests need to know about confidence scores or evidence
# to pass, that's a sign business logic leaked into the API layer.

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

SUCCESS_RESULT = {
    "url": "https://example.com/",
    "status": "success",
    "http_status": 200,
    "browser_status": "not_launched",
    "evidence_source": "http",
    "technologies": [
        {
            "technology": "Cloudflare",
            "category": "CDN / Security",
            "confidence_score": 80,
            "confidence": "strong",
            "evidence": ["[any +60] header 'cf-ray' exists"],
            "browser_enrichable": False,
            "detection_type": "direct",
        },
    ],
    "errors": [],
}

FAILED_RESULT = {
    "url": "not-a-url",
    "status": "failed",
    "http_status": None,
    "browser_status": "not_launched",
    "evidence_source": None,
    "technologies": [],
    "errors": [{"type": "invalid_url", "message": "'not-a-url' is not a valid URL"}],
}


class TestDetectTechRoute:
    def test_calls_pipeline_with_the_submitted_url_and_returns_its_result(self):
        with patch("api.routes.detect_website_technologies", return_value=SUCCESS_RESULT) as mock_detect:
            response = client.post("/detect-tech", json={"url": "https://example.com"})

        mock_detect.assert_called_once_with("https://example.com")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["technologies"][0]["technology"] == "Cloudflare"

    def test_passes_through_a_failed_pipeline_result_as_200_not_500(self):
        # A "failed" detection (bad URL, DNS failure) is a normal,
        # well-formed API response -- it's not a server error, so this
        # should NOT come back as an HTTP 500.
        with patch("api.routes.detect_website_technologies", return_value=FAILED_RESULT):
            response = client.post("/detect-tech", json={"url": "not-a-url"})

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["errors"][0]["type"] == "invalid_url"

    def test_missing_url_field_is_rejected_before_pipeline_is_called(self):
        with patch("api.routes.detect_website_technologies") as mock_detect:
            response = client.post("/detect-tech", json={})

        mock_detect.assert_not_called()
        assert response.status_code == 422

    def test_route_does_not_alter_the_technologies_list(self):
        # The route must pass evidence/scores through unchanged -- it's
        # not allowed to filter, re-score, or reshape them.
        with patch("api.routes.detect_website_technologies", return_value=SUCCESS_RESULT):
            response = client.post("/detect-tech", json={"url": "https://example.com"})

        assert response.json()["technologies"] == SUCCESS_RESULT["technologies"]


class TestHealthRoute:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
