# Regression suite for the logging/error-tracking additions:
# api/logging_config.py's JSONFormatter, api/request_context.py +
# api/middleware.py's request-ID propagation, main.py's unhandled_exception_handler,
# and that Sentry only initializes when SENTRY_DSN is actually set. Fully
# offline -- no real Sentry project, no real log aggregator.

import json
import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.error_tracking import init_error_tracking
from api.logging_config import JSONFormatter
from api.main import app
from api.request_context import request_id_var

client = TestClient(app)


def _make_record(level=logging.INFO, message="hello", exc_info=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


class TestJSONFormatter:
    def test_produces_valid_json_with_the_expected_fields(self):
        formatter = JSONFormatter()
        record = _make_record(message="something happened")

        payload = json.loads(formatter.format(record))

        assert payload["level"] == "INFO"
        assert payload["logger"] == "test.logger"
        assert payload["message"] == "something happened"
        assert "timestamp" in payload
        assert "request_id" in payload

    def test_includes_the_current_request_id_when_set(self):
        formatter = JSONFormatter()
        token = request_id_var.set("abc-123")
        try:
            payload = json.loads(formatter.format(_make_record()))
        finally:
            request_id_var.reset(token)

        assert payload["request_id"] == "abc-123"

    def test_defaults_to_a_placeholder_when_no_request_id_is_set(self):
        formatter = JSONFormatter()
        payload = json.loads(formatter.format(_make_record()))
        assert payload["request_id"] == "-"

    def test_includes_a_formatted_traceback_when_exc_info_is_present(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = _make_record(exc_info=sys.exc_info())

        payload = json.loads(formatter.format(record))
        assert "exception" in payload
        assert "ValueError: boom" in payload["exception"]


class TestRequestIdPropagation:
    def test_response_carries_an_x_request_id_header(self):
        response = client.get("/health")
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) > 0

    def test_a_fresh_request_id_is_generated_when_none_is_supplied(self):
        r1 = client.get("/health")
        r2 = client.get("/health")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]

    def test_an_inbound_x_request_id_is_echoed_back_unchanged(self):
        response = client.get("/health", headers={"X-Request-ID": "caller-supplied-id"})
        assert response.headers["x-request-id"] == "caller-supplied-id"


class TestUnhandledExceptionHandler:
    # raise_server_exceptions=False -- TestClient's default
    # (raise_server_exceptions=True) re-raises a server-side exception
    # IN THE TEST PROCESS for easier debugging, bypassing the registered
    # exception_handler entirely. That's the right default everywhere
    # else in this file (a genuine bug should surface loudly, not get
    # silently swallowed into "well, it returned 500") -- but here the
    # handler's own behavior is exactly what's under test.
    error_client = TestClient(app, raise_server_exceptions=False)

    def test_an_unexpected_exception_returns_a_generic_500_not_the_raw_message(self):
        # detect_website_technologies() itself never raises (see its own
        # tests) -- this simulates something escaping the API layer
        # ABOVE that guarantee (a genuine bug), which is exactly what
        # this handler exists for.
        with patch(
            "api.routes.tech_detection.detect_website_technologies",
            side_effect=RuntimeError("some internal secret detail"),
        ):
            response = self.error_client.post("/detect-tech", json={"url": "https://example.com/"})

        assert response.status_code == 500
        body = response.json()
        assert body == {"detail": "Internal server error."}
        assert "some internal secret detail" not in response.text

    def test_the_exception_is_logged_with_a_traceback(self, caplog):
        with patch(
            "api.routes.tech_detection.detect_website_technologies",
            side_effect=RuntimeError("boom"),
        ):
            with caplog.at_level(logging.ERROR, logger="api.main"):
                self.error_client.post("/detect-tech", json={"url": "https://example.com/"})

        assert any("Unhandled exception" in record.message for record in caplog.records)
        assert any(record.exc_info for record in caplog.records)


class TestSentryInitialization:
    # init_error_tracking() is a standalone function (api/error_tracking.py),
    # deliberately pulled out of main.py so it's testable directly here
    # without reloading the whole FastAPI app/module-import machinery.

    def test_no_dsn_means_sentry_init_is_never_called(self):
        with patch("sentry_sdk.init") as mock_init:
            init_error_tracking(None)

        mock_init.assert_not_called()

    def test_empty_string_dsn_is_also_treated_as_not_configured(self):
        with patch("sentry_sdk.init") as mock_init:
            init_error_tracking("")

        mock_init.assert_not_called()

    def test_a_real_dsn_initializes_sentry_with_it(self):
        with patch("sentry_sdk.init") as mock_init:
            init_error_tracking("https://fake@sentry.example/1")

        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["dsn"] == "https://fake@sentry.example/1"

    def test_pii_is_not_sent_by_default(self):
        with patch("sentry_sdk.init") as mock_init:
            init_error_tracking("https://fake@sentry.example/1")

        assert mock_init.call_args.kwargs["send_default_pii"] is False
