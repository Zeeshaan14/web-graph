# Regression suite for website_processing/pipeline.py: the combined
# status-derivation logic and orchestration. Fully offline -- both
# discover_urls() and fetch_and_prepare() are mocked entirely, so this
# never exercises real crawling/extraction/HTTP (that's each feature's
# own suite's job). Shared-content detection itself is exercised for real
# here (not mocked) since it's pipeline.py's own orchestration wiring that
# this file is about -- see test_shared_content.py for the algorithm's own
# dedicated unit tests.

import threading
import time
from unittest.mock import patch

from bs4 import BeautifulSoup

from website_processing.pipeline import (
    MAX_CONCURRENT_EXTRACTIONS,
    discover_and_extract,
    discover_and_extract_stream,
)

DISCOVER_TARGET = "website_processing.pipeline.discover_urls_stream"
EXTRACT_TARGET = "website_processing.pipeline.fetch_and_prepare"


def discovery(status, urls, errors=None):
    return {
        "status": status,
        "start_url": "https://example.com/",
        "discovered_urls": urls,
        "pages_traversed": len(urls),
        "errors": errors or [],
    }


def stream_of(result):
    """discover_urls_stream() is a generator ending in a "complete" event
    carrying its final result -- this is the minimal replay a mocked call
    needs (no intermediate "url_discovered" events) for tests that only
    care about the final discovery result, which is everything below
    except TestUrlDiscoveredEvents."""
    return iter([{"event": "complete", "result": result}])


def make_body(inner_html: str) -> BeautifulSoup:
    return BeautifulSoup(f"<html><body>{inner_html}</body></html>", "html.parser").body


def page(status, url="https://example.com/p", error=None, body_html="<p>P</p>"):
    # A plain, link-free paragraph by default -- shared-content detection
    # only ever looks at nav/aside/header/footer tags (see
    # shared_content.CANDIDATE_TAGS), so ordinary fixture content like
    # this is never a dedup candidate, even if several test pages happen
    # to use the exact same default body_html.
    if status == "success":
        return {"status": "success", "url": url, "title": "Title", "body": make_body(body_html), "error": None}
    return {"status": "failed", "url": url, "title": None, "body": None, "error": error}


def run(discovery_result, page_results, **kwargs):
    with patch(DISCOVER_TARGET, return_value=stream_of(discovery_result)), \
         patch(EXTRACT_TARGET, side_effect=page_results) as mock_extract:
        result = discover_and_extract("https://example.com/", **kwargs)
    return result, mock_extract


class TestDiscoveryFailedShortCircuit:
    def test_discovery_failed_returns_failed_without_calling_extract_content(self):
        disc = discovery("failed", [], errors=[{"url": "https://example.com/", "error": "timeout"}])

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), patch(EXTRACT_TARGET) as mock_extract:
            result = discover_and_extract("https://example.com/")

        mock_extract.assert_not_called()
        assert result == {
            "status": "failed",
            "start_url": "https://example.com/",
            "discovery": disc,
            "pages": [],
            "shared_content_markdown": "",
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
        # threads calls fetch_and_prepare() first is not deterministic.
        # What IS guaranteed, and what matters, is that each URL is
        # extracted exactly once; output ORDER is covered separately below.
        disc = discovery("success", ["https://example.com/a", "https://example.com/b"])
        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, side_effect=lambda url: page("success", url=url)) as mock_extract:
            discover_and_extract("https://example.com/")

        called_urls = {call.args[0] for call in mock_extract.call_args_list}
        assert called_urls == {"https://example.com/a", "https://example.com/b"}
        assert mock_extract.call_count == 2

    def test_discover_urls_receives_max_pages_and_max_depth(self):
        disc = discovery("success", ["a"])
        with patch(DISCOVER_TARGET, return_value=stream_of(disc)) as mock_discover, \
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
        results_by_url = {
            "a": page("success", url="https://example.com/a", body_html="<p>A content</p>"),
            "b": page("failed", url="https://example.com/b", error="404"),
        }

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, side_effect=lambda url: results_by_url[url]):
            result = discover_and_extract("https://example.com/")

        assert result["pages"] == [
            {
                "status": "success",
                "url": "https://example.com/a",
                "title": "Title",
                "content_markdown": "A content",
                "error": None,
            },
            {
                "status": "failed",
                "url": "https://example.com/b",
                "title": None,
                "content_markdown": "",
                "error": "404",
            },
        ]


class TestSharedContentWiring:
    """pipeline.py's own use of shared_content.find_shared_containers() /
    remove_shared_containers() -- the dedup algorithm's own behavior
    (thresholds, similarity matching, ...) has its dedicated unit tests in
    test_shared_content.py. This is about wiring: does the pipeline
    actually strip what's found, report it once, and leave genuinely
    unique per-page content alone."""

    # Absolute hrefs -- real fetch_and_prepare() output always is (it
    # resolves relative URLs itself), and this test mocks that function
    # out entirely, so nothing else would resolve a relative one here.
    NAV = '<nav><a href="https://example.com/">Home</a><a href="https://example.com/docs">Docs</a></nav>'

    def test_content_repeated_across_pages_is_stripped_and_reported_once(self):
        disc = discovery("success", ["a", "b", "c"])
        pages = [
            page("success", url="https://example.com/a", body_html=f"{self.NAV}<p>Page A body.</p>"),
            page("success", url="https://example.com/b", body_html=f"{self.NAV}<p>Page B body.</p>"),
            page("success", url="https://example.com/c", body_html=f"{self.NAV}<p>Page C body.</p>"),
        ]

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), patch(EXTRACT_TARGET, side_effect=pages):
            result = discover_and_extract("https://example.com/")

        for extracted_page, label in zip(result["pages"], ["A", "B", "C"]):
            assert "[Home]" not in extracted_page["content_markdown"]
            assert f"Page {label} body." in extracted_page["content_markdown"]

        assert "[Home](https://example.com/)" in result["shared_content_markdown"]
        assert "[Docs](https://example.com/docs)" in result["shared_content_markdown"]

    def test_content_unique_to_one_page_is_left_alone(self):
        disc = discovery("success", ["a", "b"])
        pages = [
            page("success", url="https://example.com/a", body_html='<nav><a href="/x">X</a><a href="/y">Y</a></nav>'),
            page("success", url="https://example.com/b", body_html="<p>Nothing nav-like here.</p>"),
        ]

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), patch(EXTRACT_TARGET, side_effect=pages):
            result = discover_and_extract("https://example.com/")

        assert "[X]" in result["pages"][0]["content_markdown"]
        assert result["shared_content_markdown"] == ""

    def test_a_single_successful_page_never_triggers_dedup(self):
        disc = discovery("success", ["a"])
        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, return_value=page("success", body_html=self.NAV)):
            result = discover_and_extract("https://example.com/")

        assert "[Home]" in result["pages"][0]["content_markdown"]
        assert result["shared_content_markdown"] == ""


class TestParallelExtraction:
    def test_extractions_actually_overlap_instead_of_running_sequentially(self):
        urls = [f"https://example.com/{i}" for i in range(5)]
        disc = discovery("success", urls)

        def slow_extract(url):
            time.sleep(0.2)
            return page("success", url=url)

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
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

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
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

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
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


class TestStreamingEvents:
    """discover_and_extract() (tested everywhere above) is just this
    generator exhausted for its final event -- these tests are about the
    events themselves: which ones fire, in what order, carrying what."""

    def test_event_sequence_for_a_successful_two_page_crawl(self):
        disc = discovery("success", ["a", "b"])
        discovery_stream_events = iter([
            {"event": "url_discovered", "url": "a", "count": 1},
            {"event": "url_discovered", "url": "b", "count": 2},
            {"event": "complete", "result": disc},
        ])
        pages = {
            "a": page("success", url="a", body_html="<p>A</p>"),
            "b": page("success", url="b", body_html="<p>B</p>"),
        }

        with patch(DISCOVER_TARGET, return_value=discovery_stream_events), \
             patch(EXTRACT_TARGET, side_effect=lambda url: pages[url]):
            events = list(discover_and_extract_stream("https://example.com/"))

        event_names = [e["event"] for e in events]
        assert event_names == [
            "discovery_started",
            "url_discovered",
            "url_discovered",
            "discovery_done",
            "page_fetched",
            "page_fetched",
            "dedup_done",
            "page_rendered",
            "page_rendered",
            "complete",
        ]

    def test_url_discovered_events_pass_through_unchanged(self):
        disc = discovery("success", ["a", "b"])
        discovery_stream_events = iter([
            {"event": "url_discovered", "url": "a", "count": 1},
            {"event": "url_discovered", "url": "b", "count": 2},
            {"event": "complete", "result": disc},
        ])
        pages = {
            "a": page("success", url="a"),
            "b": page("success", url="b"),
        }

        with patch(DISCOVER_TARGET, return_value=discovery_stream_events), \
             patch(EXTRACT_TARGET, side_effect=lambda url: pages[url]):
            events = list(discover_and_extract_stream("https://example.com/"))

        discovered = [e for e in events if e["event"] == "url_discovered"]
        assert discovered == [
            {"event": "url_discovered", "url": "a", "count": 1},
            {"event": "url_discovered", "url": "b", "count": 2},
        ]

    def test_discovery_done_carries_the_discovery_result(self):
        disc = discovery("success", ["a"])
        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, return_value=page("success", url="a")):
            events = list(discover_and_extract_stream("https://example.com/"))

        discovery_done = next(e for e in events if e["event"] == "discovery_done")
        assert discovery_done["discovery"] == disc

    def test_page_fetched_fires_once_per_url_with_its_status(self):
        disc = discovery("success", ["a", "b"])
        pages = {
            "a": page("success", url="a"),
            "b": page("failed", url="b", error="404"),
        }

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, side_effect=lambda url: pages[url]):
            events = list(discover_and_extract_stream("https://example.com/"))

        fetched = {(e["url"], e["status"]) for e in events if e["event"] == "page_fetched"}
        assert fetched == {("a", "success"), ("b", "failed")}

    def test_page_rendered_carries_shared_content_already_stripped(self):
        disc = discovery("success", ["a", "b", "c"])
        nav = '<nav><a href="https://example.com/">Home</a><a href="https://example.com/x">X</a></nav>'
        pages = {
            "a": page("success", url="a", body_html=f"{nav}<p>A body.</p>"),
            "b": page("success", url="b", body_html=f"{nav}<p>B body.</p>"),
            "c": page("success", url="c", body_html=f"{nav}<p>C body.</p>"),
        }

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, side_effect=lambda url: pages[url]):
            events = list(discover_and_extract_stream("https://example.com/"))

        rendered = [e["page"] for e in events if e["event"] == "page_rendered"]
        assert len(rendered) == 3
        for p in rendered:
            assert "[Home]" not in p["content_markdown"]

        dedup_done = next(e for e in events if e["event"] == "dedup_done")
        assert "[Home](https://example.com/)" in dedup_done["shared_content_markdown"]

    def test_complete_result_matches_the_non_streaming_return_value(self):
        # Keyed by the ACTUAL url each concurrent call receives, not a
        # positional side_effect list -- with real concurrent execution,
        # which thread's call reaches a positional list first isn't
        # deterministic, so a keyed lookup is what makes this comparison
        # reliable rather than occasionally flaky.
        disc = discovery("success", ["a", "b"])
        pages = {
            "a": page("success", url="a", body_html="<p>A</p>"),
            "b": page("failed", url="b", error="timeout"),
        }

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, side_effect=lambda url: pages[url]):
            events = list(discover_and_extract_stream("https://example.com/"))

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), \
             patch(EXTRACT_TARGET, side_effect=lambda url: pages[url]):
            direct_result = discover_and_extract("https://example.com/")

        streamed_result = next(e for e in events if e["event"] == "complete")["result"]
        assert streamed_result == direct_result

    def test_discovery_failure_short_circuits_straight_to_complete(self):
        disc = discovery("failed", [], errors=[{"url": "https://example.com/", "error": "timeout"}])

        with patch(DISCOVER_TARGET, return_value=stream_of(disc)), patch(EXTRACT_TARGET) as mock_extract:
            events = list(discover_and_extract_stream("https://example.com/"))

        mock_extract.assert_not_called()
        assert [e["event"] for e in events] == ["discovery_started", "discovery_done", "complete"]
        assert events[-1]["result"]["status"] == "failed"
