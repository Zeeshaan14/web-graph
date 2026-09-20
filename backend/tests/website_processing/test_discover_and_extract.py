# Regression suite for website_processing/pipeline.py: the combined
# status-derivation logic and orchestration. Fully offline -- both
# discover_urls() and extract_content() are mocked entirely, so this
# never exercises real crawling/extraction/HTTP (that's each feature's
# own suite's job).

import threading
import time
from unittest.mock import patch

from website_processing.pipeline import MAX_CONCURRENT_EXTRACTIONS, discover_and_extract

DISCOVER_TARGET = "website_processing.pipeline.discover_urls"
EXTRACT_TARGET = "website_processing.pipeline.extract_content"


def discovery(status, urls, errors=None):
    return {
        "status": status,
        "start_url": "https://example.com/",
        "discovered_urls": urls,
        "pages_traversed": len(urls),
        "errors": errors or [],
    }


def page(status, url="https://example.com/p", error=None):
    return {
        "status": status,
        "url": url,
        "title": "Title" if status == "success" else None,
        "content_markdown": "P" if status == "success" else "",
        "error": error,
    }


def run(discovery_result, page_results, **kwargs):
    with patch(DISCOVER_TARGET, return_value=discovery_result), \
         patch(EXTRACT_TARGET, side_effect=page_results) as mock_extract:
        result = discover_and_extract("https://example.com/", **kwargs)
    return result, mock_extract


class TestDiscoveryFailedShortCircuit:
    def test_discovery_failed_returns_failed_without_calling_extract_content(self):
        disc = discovery("failed", [], errors=[{"url": "https://example.com/", "error": "timeout"}])

        with patch(DISCOVER_TARGET, return_value=disc), patch(EXTRACT_TARGET) as mock_extract:
            result = discover_and_extract("https://example.com/")

        mock_extract.assert_not_called()
        assert result == {
            "status": "failed",
            "start_url": "https://example.com/",
            "discovery": disc,
            "pages": [],
        }


class TestCombinedStatusLogic:
    def test_discovery_success_all_extractions_succeed_is_success(self):
        result, _ = run(discovery("success", ["a", "b"]), [page("success"), page("success")])
        assert result["status"] == "success"

    def test_discovery_success_mixed_extractions_is_partial(self):
        result, _ = run(discovery("success", ["a", "b"]), [page("success"), page("failed")])
        assert result["status"] == "partial"

    def test_discovery_success_all_extractions_fail_is_failed(self):
        result, _ = run(discovery("success", ["a", "b"]), [page("failed"), page("failed")])
        assert result["status"] == "failed"

    def test_discovery_partial_all_extractions_succeed_is_partial(self):
        result, _ = run(discovery("partial", ["a", "b"]), [page("success"), page("success")])
        assert result["status"] == "partial"

    def test_discovery_partial_mixed_extractions_is_partial(self):
        result, _ = run(discovery("partial", ["a", "b"]), [page("success"), page("failed")])
        assert result["status"] == "partial"

    def test_discovery_partial_all_extractions_fail_is_failed(self):
        # The one ambiguous case in the original spec: a merely-partial
        # discovery combined with zero usable extracted content should
        # not read as "partial" -- that would imply some real content
        # came through, when none did.
        result, _ = run(discovery("partial", ["a", "b"]), [page("failed"), page("failed")])
        assert result["status"] == "failed"

    def test_single_page_success_is_success(self):
        result, _ = run(discovery("success", ["a"]), [page("success")])
        assert result["status"] == "success"

    def test_single_page_failure_is_failed_not_partial(self):
        # One page, and it failed -- that's "every extraction failed",
        # not a mix, so it must be "failed".
        result, _ = run(discovery("success", ["a"]), [page("failed")])
        assert result["status"] == "failed"


class TestOrchestration:
    def test_extract_content_called_once_per_discovered_url(self):
        # NOT asserting CALL order here -- extractions now run concurrently
        # (see TestParallelExtraction below), so which of several worker
        # threads calls extract_content() first is not deterministic. What
        # IS guaranteed, and what matters, is that each URL is extracted
        # exactly once; output ORDER is covered separately below.
        disc = discovery("success", ["https://example.com/a", "https://example.com/b"])
        with patch(DISCOVER_TARGET, return_value=disc), \
             patch(EXTRACT_TARGET, side_effect=lambda url: page("success", url=url)) as mock_extract:
            discover_and_extract("https://example.com/")

        called_urls = {call.args[0] for call in mock_extract.call_args_list}
        assert called_urls == {"https://example.com/a", "https://example.com/b"}
        assert mock_extract.call_count == 2

    def test_discover_urls_receives_max_pages_and_max_depth(self):
        disc = discovery("success", ["a"])
        with patch(DISCOVER_TARGET, return_value=disc) as mock_discover, \
             patch(EXTRACT_TARGET, return_value=page("success")):
            discover_and_extract("https://example.com/", max_pages=25, max_depth=3)

        mock_discover.assert_called_once_with(
            start_url="https://example.com/", max_pages=25, max_depth=3
        )

    def test_discovery_field_carries_the_raw_discovery_result_verbatim(self):
        disc = discovery("success", ["a"])
        result, _ = run(disc, [page("success")])

        assert result["discovery"] == disc

    def test_pages_field_matches_extraction_results_in_order(self):
        # Results are looked up BY the url each mock call actually
        # received, not by call sequence -- with real concurrent
        # extraction, which thread calls first isn't deterministic, but
        # executor.map()'s output order matching input order is exactly
        # the guarantee this test exists to prove.
        disc = discovery("success", ["a", "b"])
        page_a = page("success", url="https://example.com/a")
        page_b = page("failed", url="https://example.com/b", error="404")
        results_by_url = {"a": page_a, "b": page_b}

        with patch(DISCOVER_TARGET, return_value=disc), \
             patch(EXTRACT_TARGET, side_effect=lambda url: results_by_url[url]):
            result = discover_and_extract("https://example.com/")

        assert result["pages"] == [page_a, page_b]


class TestParallelExtraction:
    def test_extractions_actually_overlap_instead_of_running_sequentially(self):
        urls = [f"https://example.com/{i}" for i in range(5)]
        disc = discovery("success", urls)

        def slow_extract(url):
            time.sleep(0.2)
            return page("success", url=url)

        with patch(DISCOVER_TARGET, return_value=disc), \
             patch(EXTRACT_TARGET, side_effect=slow_extract):
            started = time.monotonic()
            discover_and_extract("https://example.com/")
            elapsed = time.monotonic() - started

        # 5 pages at 0.2s each would be ~1.0s run one at a time; real
        # overlap should finish well under that even with scheduling
        # overhead. This is a real wall-clock assertion, not a mock-call
        # check -- it's the only way to actually prove concurrency
        # happened rather than just being plausible-looking sequential code.
        assert elapsed < 0.8

    def test_concurrency_is_bounded_not_unlimited(self):
        urls = [f"https://example.com/{i}" for i in range(20)]
        disc = discovery("success", urls)

        lock = threading.Lock()
        in_flight = 0
        max_in_flight = 0

        def tracking_extract(url):
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            return page("success", url=url)

        with patch(DISCOVER_TARGET, return_value=disc), \
             patch(EXTRACT_TARGET, side_effect=tracking_extract):
            discover_and_extract("https://example.com/")

        # More than one at once (it's actually parallel) but never more
        # than the declared ceiling (it's not "fire all 20 at once").
        assert 1 < max_in_flight <= MAX_CONCURRENT_EXTRACTIONS

    def test_a_handful_of_urls_uses_fewer_workers_than_the_ceiling(self):
        # min(MAX_CONCURRENT_EXTRACTIONS, len(urls)) -- 2 URLs should never
        # observe more than 2 concurrent extractions, ceiling notwithstanding.
        urls = ["https://example.com/a", "https://example.com/b"]
        disc = discovery("success", urls)

        lock = threading.Lock()
        in_flight = 0
        max_in_flight = 0

        def tracking_extract(url):
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            return page("success", url=url)

        with patch(DISCOVER_TARGET, return_value=disc), \
             patch(EXTRACT_TARGET, side_effect=tracking_extract):
            discover_and_extract("https://example.com/")

        assert max_in_flight == 2

    def test_zero_discovered_urls_with_non_failed_status_still_returns_a_status(self):
        # Not expected in practice (discover_urls() only reports
        # success/partial when pages_traversed > 0, which guarantees at
        # least one discovered URL) -- but the loop over an empty list
        # must not crash, and "no successes" correctly means "failed".
        disc = discovery("success", [])
        result, mock_extract = run(disc, [])

        mock_extract.assert_not_called()
        assert result["status"] == "failed"
        assert result["pages"] == []
