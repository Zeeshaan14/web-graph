# Regression suite for fetcher.py: politeness pacing and the 429
# retry/backoff mechanics. Fully offline -- session.get() is mocked.

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from url_discovery import fetcher
from url_discovery.fetcher import BROWSER_HEADERS, fetch, new_session


def make_response(status, headers=None, text="ok"):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.text = text
    r.raise_for_status.side_effect = requests.HTTPError(f"{status} error") if status >= 400 else None
    return r


class TestParseRetryAfter:
    def test_numeric_seconds(self):
        assert fetcher._parse_retry_after("5") == 5.0

    def test_missing_returns_none(self):
        assert fetcher._parse_retry_after(None) is None

    def test_empty_string_returns_none(self):
        assert fetcher._parse_retry_after("") is None

    def test_garbage_returns_none(self):
        assert fetcher._parse_retry_after("not-a-date") is None

    def test_http_date_in_the_future(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        result = fetcher._parse_retry_after(format_datetime(future))
        assert 110 <= result <= 120


class TestNewSession:
    def test_applies_browser_headers(self):
        session = new_session()
        for key, value in BROWSER_HEADERS.items():
            assert session.headers[key] == value


class TestFetch:
    def test_success_needs_no_retry(self):
        session = MagicMock()
        session.get.side_effect = [make_response(200, text="hello")]

        with patch("url_discovery.fetcher.time.sleep"):
            response = fetch(session, "https://example.com/")

        assert response.status_code == 200
        assert session.get.call_count == 1

    def test_429_with_retry_after_waits_exactly_that_long_then_retries(self):
        session = MagicMock()
        session.get.side_effect = [
            make_response(429, headers={"Retry-After": "2"}),
            make_response(200, text="ok"),
        ]

        with patch("url_discovery.fetcher.time.sleep") as sleep_mock:
            response = fetch(session, "https://example.com/")

        assert response.status_code == 200
        assert session.get.call_count == 2
        assert sleep_mock.call_args_list[0].args[0] == 2.0

    def test_429_without_retry_after_uses_fallback_backoff(self):
        session = MagicMock()
        session.get.side_effect = [
            make_response(429, headers={}),
            make_response(200, text="ok"),
        ]

        with patch("url_discovery.fetcher.time.sleep") as sleep_mock:
            response = fetch(session, "https://example.com/")

        assert response.status_code == 200
        assert sleep_mock.call_args_list[0].args[0] == fetcher.RETRY_FALLBACK_SECONDS

    def test_persistent_429_raises_after_exactly_one_retry(self):
        session = MagicMock()
        session.get.side_effect = [
            make_response(429, headers={"Retry-After": "1"}),
            make_response(429, headers={"Retry-After": "1"}),
        ]

        with patch("url_discovery.fetcher.time.sleep"):
            with pytest.raises(requests.RequestException):
                fetch(session, "https://example.com/")

        # Exactly 2 calls -- initial + one retry, never a retry loop.
        assert session.get.call_count == 2

    def test_non_429_error_does_not_trigger_retry_logic(self):
        session = MagicMock()
        session.get.side_effect = [make_response(500)]

        with patch("url_discovery.fetcher.time.sleep"):
            with pytest.raises(requests.RequestException):
                fetch(session, "https://example.com/")

        assert session.get.call_count == 1

    def test_pacing_delay_applied_on_success(self):
        session = MagicMock()
        session.get.side_effect = [make_response(200)]

        with patch("url_discovery.fetcher.time.sleep") as sleep_mock:
            fetch(session, "https://example.com/")

        sleep_mock.assert_called_with(fetcher.REQUEST_DELAY_SECONDS)

    def test_pacing_delay_applied_even_on_failure(self):
        session = MagicMock()
        session.get.side_effect = [make_response(500)]

        with patch("url_discovery.fetcher.time.sleep") as sleep_mock:
            with pytest.raises(requests.RequestException):
                fetch(session, "https://example.com/")

        sleep_mock.assert_called_with(fetcher.REQUEST_DELAY_SECONDS)
