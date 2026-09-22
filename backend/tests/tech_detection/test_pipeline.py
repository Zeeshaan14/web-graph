# Regression suite for pipeline.py's orchestration and error-handling
# contract. Mocks only the network boundary (fetch_url, collect_browser_
# evidence) so evidence-building/detection/fallback/inference all run for
# real -- this is what actually exercises the wiring between them.

from unittest.mock import patch

import requests

import tech_detection.pipeline as pipeline
from tests.fakes import FakeResponse, FakeSession

CLOUDFLARE_HEADERS = {"cf-ray": "abc123", "server": "cloudflare"}


class TestFetchFailuresNeverRaise:
    """detect_website_technologies() must never let a raw exception
    escape -- every failure becomes a structured 'failed' result."""

    def test_invalid_url(self):
        with patch("tech_detection.pipeline.fetch_url", side_effect=requests.exceptions.MissingSchema("bad")):
            result = pipeline.detect_website_technologies("not-a-url")

        assert result["status"] == "failed"
        assert result["http_status"] is None
        assert result["browser_status"] == "not_launched"
        assert result["evidence_source"] is None
        assert result["technologies"] == []
        assert result["errors"][0]["type"] == "invalid_url"

    def test_connection_error(self):
        with patch("tech_detection.pipeline.fetch_url", side_effect=requests.exceptions.ConnectionError("no dns")):
            result = pipeline.detect_website_technologies("https://nope.invalid")

        assert result["status"] == "failed"
        assert result["errors"][0]["type"] == "connection_error"
        assert result["errors"][0]["message"] == "Could not connect to 'https://nope.invalid'."

    def test_dns_failure_returns_friendly_message(self):
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='nope.invalid', port=443): Max retries exceeded "
            "with url: / (Caused by NameResolutionError(\"Failed to resolve 'nope.invalid' "
            "([Errno 11001] getaddrinfo failed)\"))"
        )
        with patch("tech_detection.pipeline.fetch_url", side_effect=exc):
            result = pipeline.detect_website_technologies("https://nope.invalid")

        assert result["status"] == "failed"
        assert (
            result["errors"][0]["message"]
            == "Could not resolve 'https://nope.invalid' -- check the domain and try again."
        )

    def test_timeout(self):
        with patch("tech_detection.pipeline.fetch_url", side_effect=requests.exceptions.Timeout("slow")):
            result = pipeline.detect_website_technologies("https://slow.example")

        assert result["status"] == "failed"
        assert result["errors"][0]["type"] == "timeout"

    def test_generic_request_exception(self):
        with patch("tech_detection.pipeline.fetch_url", side_effect=requests.exceptions.RequestException("weird")):
            result = pipeline.detect_website_technologies("https://weird.example")

        assert result["status"] == "failed"
        assert result["errors"][0]["type"] == "request_error"

    def test_unexpected_exception_after_response_obtained_still_returns_structured_result(self):
        response = FakeResponse("https://example.com/", status_code=200, headers=CLOUDFLARE_HEADERS)
        session = FakeSession()

        with patch("tech_detection.pipeline.fetch_url", return_value=(response, session)), \
             patch("tech_detection.pipeline.build_evidence", side_effect=RuntimeError("boom")):
            result = pipeline.detect_website_technologies("https://example.com")

        assert result["status"] == "failed"
        assert result["errors"][0]["type"] == "internal_error"
        # We DID get a response before the crash, so http_status is known.
        assert result["http_status"] == 200


class TestSuccessfulHttpOnlyPath:
    def test_status_code_400_plus_skips_browser_and_still_succeeds(self):
        response = FakeResponse("https://example.com/missing", status_code=404, headers={}, text="")
        session = FakeSession()

        with patch("tech_detection.pipeline.fetch_url", return_value=(response, session)), \
             patch("tech_detection.pipeline.collect_browser_evidence") as browser_mock:
            result = pipeline.detect_website_technologies("https://example.com/missing")

        browser_mock.assert_not_called()
        assert result["status"] == "success"
        assert result["http_status"] == 404
        assert result["browser_status"] == "not_launched"
        assert result["evidence_source"] == "http"
        assert result["technologies"] == []
        assert result["errors"] == []

    def test_strong_detection_skips_browser(self):
        response = FakeResponse(
            "https://example.com/", status_code=200, headers=CLOUDFLARE_HEADERS,
            text=("<html><body>Example Domain. This domain is for use in illustrative "
                  "examples in documents. You may use this domain in literature without "
                  "prior coordination or asking for permission.</body></html>"),
        )
        session = FakeSession()

        with patch("tech_detection.pipeline.fetch_url", return_value=(response, session)), \
             patch("tech_detection.pipeline.collect_browser_evidence") as browser_mock:
            result = pipeline.detect_website_technologies("https://example.com")

        browser_mock.assert_not_called()
        assert result["status"] == "success"
        assert result["evidence_source"] == "http"
        assert any(t["technology"] == "Cloudflare" for t in result["technologies"])


class TestBrowserEnrichmentPath:
    def test_successful_browser_pass(self):
        response = FakeResponse(
            "https://example.com/",
            status_code=200,
            headers={"x-nextjs-prerender": "1"},
            text="<html><body>empty</body></html>",
        )
        session = FakeSession()
        browser_evidence = {
            "html": "<html><body>rendered</body></html>",
            "script_src": [], "stylesheet_href": [], "cookies": {}, "javascript_globals": [],
        }

        with patch("tech_detection.pipeline.fetch_url", return_value=(response, session)), \
             patch("tech_detection.pipeline.should_use_browser", return_value=True), \
             patch("tech_detection.pipeline.collect_browser_evidence", return_value=browser_evidence):
            result = pipeline.detect_website_technologies("https://example.com")

        assert result["status"] == "success"
        assert result["browser_status"] == "ok"
        assert result["evidence_source"] == "http+browser"

    def test_inference_runs_on_final_not_first_pass(self):
        # Regression: inference must use the POST-merge direct result, not
        # http_technologies (which is only used for the fallback decision
        # once browser enrichment happens).
        response = FakeResponse(
            "https://example.com/", status_code=200, headers={},
            text="<html><body>empty shell</body></html>",
        )
        session = FakeSession()
        # Next.js only becomes detectable after the browser pass here.
        browser_evidence = {
            "html": "",
            "script_src": ["https://example.com/_next/static/chunks/x.js"],
            "stylesheet_href": [], "cookies": {},
            "javascript_globals": [],
        }

        with patch("tech_detection.pipeline.fetch_url", return_value=(response, session)), \
             patch("tech_detection.pipeline.should_use_browser", return_value=True), \
             patch("tech_detection.pipeline.collect_browser_evidence", return_value=browser_evidence):
            result = pipeline.detect_website_technologies("https://example.com")

        names = {t["technology"] for t in result["technologies"]}
        assert "Next.js" in names
        assert "React" in names  # inferred from the post-merge Next.js detection

    def test_browser_failure_preserves_http_result_as_partial(self):
        response = FakeResponse(
            "https://example.com/", status_code=200, headers=CLOUDFLARE_HEADERS,
            text="<html><body>a real page with plenty of text content here</body></html>",
        )
        session = FakeSession()

        with patch("tech_detection.pipeline.fetch_url", return_value=(response, session)), \
             patch("tech_detection.pipeline.should_use_browser", return_value=True), \
             patch("tech_detection.pipeline.collect_browser_evidence", side_effect=RuntimeError("Playwright timed out")):
            result = pipeline.detect_website_technologies("https://example.com")

        assert result["status"] == "partial"
        assert result["http_status"] == 200
        assert result["browser_status"] == "failed"
        assert result["evidence_source"] == "http"
        assert any(t["technology"] == "Cloudflare" for t in result["technologies"])
        assert result["errors"] == [{"type": "browser_failed", "message": "Playwright timed out"}]
