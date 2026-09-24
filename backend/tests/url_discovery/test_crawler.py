# Regression suite for crawler.py: the BFS traversal, the
# traversal-vs-output identity split, redirect handling, canonical
# handling, the fallback-fetch integration, and the discover_urls()
# feature-contract wrapper. Fully offline -- mocks only the network
# boundary (Session.get / time.sleep), so the real traversal/queue/dedup
# logic all runs for real.

import threading
from unittest.mock import MagicMock, patch

import pytest
import requests

from url_discovery.crawler import crawl, crawl_stream, discover_urls, discover_urls_stream
from tests.url_discovery.helpers import make_fake_get, make_not_found_response

SHOULD_RENDER_TARGET = "url_discovery.crawler.should_render_with_browser"


@pytest.fixture(autouse=True)
def no_real_browser():
    # crawl() now decides per-page whether a page looks like an unrendered
    # SPA shell and is worth a browser render -- every fixture in this file
    # is tiny HTML, which would trip that heuristic and try to launch a
    # real Chromium browser during an "offline" test run. Autouse so every
    # test defaults to "never render," the same way no_real_sleep in
    # test_content_extraction.py defaults every test out of a real sleep;
    # TestBrowserFallback overrides this patch locally for the tests that
    # are actually testing the browser-rendering path itself.
    with patch(SHOULD_RENDER_TARGET, return_value=False):
        yield


def run(pages, call_log=None, **kwargs):
    """Runs crawl() and returns its internal result dict:
    {"urls", "pages_traversed", "errors"}."""
    fake_get = make_fake_get(pages, call_log)
    with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
         patch("url_discovery.fetcher.time.sleep"):
        return crawl(**kwargs)


class TestRedirectAlias:
    def test_two_requested_urls_redirecting_to_same_destination_collapse(self):
        call_log = []
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/old-bugs.html">Old</a><a href="/bugs.html">New</a>',
            ),
            "https://example.com/old-bugs.html": ("https://example.com/bugs.html", "<html>bugs</html>"),
            "https://example.com/bugs.html": ("https://example.com/bugs.html", "<html>bugs</html>"),
        }
        result = run(pages, call_log, start_url="https://example.com/", max_pages=10, max_depth=1)

        # /bugs.html never gets its own HTTP request -- the pre-request
        # visited_traversal check catches it once /old-bugs.html's
        # redirect already marked that destination visited.
        assert call_log == ["https://example.com/", "https://example.com/old-bugs.html"]
        assert result["urls"] == ["https://example.com/", "https://example.com/bugs.html"]
        assert result["pages_traversed"] == 2
        assert result["errors"] == []

    def test_requested_url_that_redirects_is_not_retried_if_linked_again(self):
        call_log = []
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/old-bugs.html">Old</a><a href="/other/">Other</a>',
            ),
            "https://example.com/old-bugs.html": ("https://example.com/bugs.html", "<html>bugs</html>"),
            "https://example.com/other/": (
                "https://example.com/other/",
                '<a href="/old-bugs.html">Old again</a>',
            ),
        }
        run(pages, call_log, start_url="https://example.com/", max_pages=10, max_depth=2)

        assert call_log.count("https://example.com/old-bugs.html") == 1


class TestExternalRedirect:
    def test_internal_link_redirecting_off_domain_is_dropped_entirely(self):
        pages = {
            "https://realpython.com/": (
                "https://realpython.com/",
                '<a href="/merch">Merch</a><a href="/about/">About</a>',
            ),
            "https://realpython.com/merch": (
                "https://realpython.threadless.com/",
                '<a href="https://realpython.threadless.com/hoodie">Hoodie</a>',
            ),
            "https://realpython.com/about/": ("https://realpython.com/about/", "<html>about</html>"),
        }
        result = run(pages, start_url="https://realpython.com/", max_pages=10, max_depth=1)

        assert result["urls"] == ["https://realpython.com/", "https://realpython.com/about/"]
        assert not any("threadless" in u for u in result["urls"])
        # An external redirect is expected control flow, not a failure.
        assert result["errors"] == []

    def test_external_redirect_source_url_is_not_retried(self):
        call_log = []
        pages = {
            "https://realpython.com/": (
                "https://realpython.com/",
                '<a href="/merch">Merch</a><a href="/other/">Other</a>',
            ),
            "https://realpython.com/merch": ("https://realpython.threadless.com/", "<html>external</html>"),
            "https://realpython.com/other/": (
                "https://realpython.com/other/",
                '<a href="/merch">Merch again</a>',
            ),
        }
        run(pages, call_log, start_url="https://realpython.com/", max_pages=10, max_depth=2)

        assert call_log.count("https://realpython.com/merch") == 1


class TestSharedCanonicalAndOutputDedup:
    def test_two_non_redirecting_pages_sharing_canonical_both_traversed_but_output_collapses(self):
        call_log = []
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/tutorial/">T1</a><a href="/tutorial/index.html">T2</a>',
            ),
            "https://example.com/tutorial/": (
                "https://example.com/tutorial/",
                '<link rel="canonical" href="/tutorial/index.html">',
            ),
            "https://example.com/tutorial/index.html": (
                "https://example.com/tutorial/index.html",
                '<link rel="canonical" href="/tutorial/index.html">',
            ),
        }
        result = run(pages, call_log, start_url="https://example.com/", max_pages=10, max_depth=1)

        # Both actually fetched -- traversal keys on final_url, and
        # neither of these redirects, so they're genuinely different
        # traversal entries.
        assert call_log.count("https://example.com/tutorial/") == 1
        assert call_log.count("https://example.com/tutorial/index.html") == 1
        assert result["pages_traversed"] == 3  # start + both tutorial variants

        # But the output list has exactly one tutorial entry.
        tutorial_entries = [u for u in result["urls"] if "tutorial" in u]
        assert tutorial_entries == ["https://example.com/tutorial/index.html"]


class TestPaginationWithSameCanonical:
    def test_pagination_chain_shares_canonical_but_each_page_still_reveals_new_links(self):
        call_log = []
        pages = {
            "https://example.com/articles/": (
                "https://example.com/articles/",
                '<a href="/articles/page/2/">Page 2</a>',
            ),
            "https://example.com/articles/page/2/": (
                "https://example.com/articles/page/2/",
                '<link rel="canonical" href="/articles/">'
                '<a href="/articles/page/3/">Page 3</a>'
                '<a href="/article-a/">Article A</a>',
            ),
            "https://example.com/articles/page/3/": (
                "https://example.com/articles/page/3/",
                '<link rel="canonical" href="/articles/">'
                '<a href="/article-b/">Article B</a>',
            ),
            "https://example.com/article-a/": ("https://example.com/article-a/", "<html>a</html>"),
            "https://example.com/article-b/": ("https://example.com/article-b/", "<html>b</html>"),
        }
        result = run(pages, call_log, start_url="https://example.com/articles/", max_pages=10, max_depth=None)

        # All 5 pages genuinely traversed -- pagination pages were not
        # skipped just because their canonical was already output.
        assert len(call_log) == 5
        assert result["pages_traversed"] == 5

        # Output collapses all 3 /articles/ variants into 1, plus the
        # two real articles that were only reachable by continuing past
        # the canonically-duplicate pagination pages.
        assert result["urls"] == [
            "https://example.com/articles/",
            "https://example.com/article-a/",
            "https://example.com/article-b/",
        ]


class TestCanonicalDoesNotBlockTraversal:
    def test_links_still_extracted_when_this_pages_output_url_is_already_seen(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/page-2/">Page 2</a>'),
            "https://example.com/page-2/": (
                "https://example.com/page-2/",
                # canonical points back to the already-output homepage
                '<link rel="canonical" href="/">'
                '<a href="/brand-new-page/">New</a>',
            ),
            "https://example.com/brand-new-page/": ("https://example.com/brand-new-page/", "<html>new</html>"),
        }
        call_log = []
        result = run(pages, call_log, start_url="https://example.com/", max_pages=10, max_depth=None)

        assert "https://example.com/brand-new-page/" in call_log
        assert "https://example.com/brand-new-page/" in result["urls"]


class TestQueryParamNormalizationDuringCrawl:
    def test_utm_variants_of_the_same_link_collapse_at_discovery(self):
        call_log = []
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/pricing?utm_source=twitter">P1</a>'
                '<a href="/pricing?utm_source=newsletter">P2</a>',
            ),
            "https://example.com/pricing": ("https://example.com/pricing", "<html>pricing</html>"),
        }
        result = run(pages, call_log, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert call_log.count("https://example.com/pricing") == 1
        assert result["urls"] == ["https://example.com/", "https://example.com/pricing"]

    def test_path_specific_strip_rule_is_threaded_through_the_whole_crawl(self):
        call_log = []
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/feedback/?d=AAA">FB1</a><a href="/feedback/?d=BBB">FB2</a>',
            ),
            "https://example.com/feedback/": ("https://example.com/feedback/", "<html>feedback</html>"),
        }
        rules = {"/feedback/": {"d"}}
        result = run(
            pages, call_log,
            start_url="https://example.com/", max_pages=10, max_depth=1,
            path_specific_strip=rules,
        )

        assert call_log.count("https://example.com/feedback/") == 1
        assert result["urls"] == ["https://example.com/", "https://example.com/feedback/"]


class TestRetryDuringCrawl:
    def test_429_mid_crawl_recovers_via_fetcher_and_traversal_continues(self):
        resp_home = MagicMock(status_code=200, url="https://example.com/", text='<a href="/slow/">Slow</a>', headers={})
        resp_home.raise_for_status.side_effect = None

        resp_slow_429 = MagicMock(status_code=429, headers={"Retry-After": "1"})

        resp_slow_200 = MagicMock(status_code=200, url="https://example.com/slow/", text="<html>loaded</html>", headers={})
        resp_slow_200.raise_for_status.side_effect = None

        session_get = MagicMock(
            side_effect=[
                make_not_found_response("https://example.com/robots.txt"),
                make_not_found_response("https://example.com/sitemap.xml"),
                resp_home,
                resp_slow_429,
                resp_slow_200,
            ]
        )

        with patch("url_discovery.fetcher.requests.Session.get", session_get), \
             patch("url_discovery.fetcher.time.sleep") as sleep_mock:
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert "https://example.com/slow/" in result["urls"]
        assert result["errors"] == []  # recovered -- not a recorded failure
        assert session_get.call_count == 5  # robots.txt + sitemap.xml + home + 429 + retry
        assert any(call.args and call.args[0] == 1.0 for call in sleep_mock.call_args_list)


class TestMaxPagesBoundary:
    def test_stops_at_exact_budget(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a><a href="/b/">B</a><a href="/c/">C</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
            "https://example.com/c/": ("https://example.com/c/", "<html>c</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=2, max_depth=1)
        assert len(result["urls"]) == 2
        assert result["pages_traversed"] == 2

    def test_none_is_unbounded_by_page_count(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=None, max_depth=None)
        assert len(result["urls"]) == 2


class TestMaxDepthBoundary:
    def test_depth_zero_only_fetches_the_start_url(self):
        call_log = []
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        result = run(pages, call_log, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert call_log == ["https://example.com/"]
        assert result["urls"] == ["https://example.com/"]

    def test_none_explores_fully_within_the_page_budget(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", '<a href="/b/">B</a>'),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=None)

        assert result["urls"] == [
            "https://example.com/",
            "https://example.com/a/",
            "https://example.com/b/",
        ]


class TestNonHtmlContentType:
    def test_non_html_page_is_still_reported_but_not_parsed_for_links_or_canonical(self):
        call_log = []
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/report.pdf">Report</a><a href="/about/">About</a>',
            ),
            "https://example.com/report.pdf": (
                "https://example.com/report.pdf",
                # If this were parsed as HTML, this link would be discovered
                # and this content-type-checking test would be pointless.
                '<a href="/hidden-in-a-pdf/">Should never be queued</a>',
                200,
                "application/pdf",
            ),
            "https://example.com/about/": ("https://example.com/about/", "<html>about</html>"),
        }
        result = run(pages, call_log, start_url="https://example.com/", max_pages=10, max_depth=2)

        assert "https://example.com/report.pdf" in result["urls"]
        assert "https://example.com/about/" in result["urls"]
        assert "https://example.com/hidden-in-a-pdf/" not in call_log
        assert result["pages_traversed"] == 3
        assert result["errors"] == []

    def test_missing_content_type_header_is_treated_as_html_not_skipped(self):
        # Regression: a page with no content-type header at all (the
        # default shape of every other fixture in this file) must keep
        # being parsed as HTML -- missing is not evidence of non-HTML.
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert result["urls"] == ["https://example.com/", "https://example.com/a/"]

    def test_content_type_check_is_case_insensitive_and_ignores_charset(self):
        # Proven by the crawl actually finding /a/ -- if the odd-cased,
        # charset-suffixed content-type were misread as non-HTML, the
        # link on the home page would never be extracted.
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a>',
                200,
                "TEXT/HTML; charset=UTF-8",
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }

        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert result["urls"] == ["https://example.com/", "https://example.com/a/"]


class TestWallClockTimeout:
    def test_timeout_stops_the_crawl_before_the_page_or_depth_budget_is_reached(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a><a href="/b/">B</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch("url_discovery.crawler.time.monotonic", side_effect=[0, 0, 1000]):
            # side_effect: [deadline calc, 1st loop check (proceed), 2nd
            # loop check (deadline blown -- stop before /a/ or /b/)].
            result = crawl(
                "https://example.com/", max_pages=10, max_depth=2, timeout_seconds=10,
            )

        assert result["pages_traversed"] == 1
        assert result["urls"] == ["https://example.com/"]

    def test_none_is_unbounded_by_wall_clock_time(self):
        # Regression: passing timeout_seconds=None (the default) must
        # never call time.monotonic() at all, let alone stop the crawl --
        # same "None means unbounded" contract as max_pages/max_depth.
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch("url_discovery.crawler.time.monotonic") as monotonic_mock:
            result = crawl("https://example.com/", max_pages=10, max_depth=1, timeout_seconds=None)

        monotonic_mock.assert_not_called()
        assert result["pages_traversed"] == 2


class TestFailedRequestIsRecordedNotFatal:
    def test_a_persistently_failing_link_is_recorded_as_an_error_and_does_not_stop_the_crawl(self):
        def fake_get(url, timeout=10):
            if url in ("https://example.com/robots.txt", "https://example.com/sitemap.xml"):
                return make_not_found_response(url)

            if url == "https://example.com/broken/":
                raise requests.ConnectionError("boom")

            pages = {
                "https://example.com/": (
                    "https://example.com/",
                    '<a href="/broken/">Broken</a><a href="/ok/">OK</a>',
                ),
                "https://example.com/ok/": ("https://example.com/ok/", "<html>ok</html>"),
            }
            final_url, html = pages[url]
            resp = MagicMock(status_code=200, url=final_url, text=html, headers={})
            resp.raise_for_status.side_effect = None
            return resp

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert "https://example.com/broken/" not in result["urls"]
        assert "https://example.com/ok/" in result["urls"]
        assert result["errors"] == [
            {"url": "https://example.com/broken/", "error": "Could not connect to 'https://example.com/broken/'."}
        ]
        # The start page and /ok/ both succeeded -- 2 traversed, 1 recorded failure.
        assert result["pages_traversed"] == 2

    def test_dns_failure_is_recorded_with_a_friendly_message(self):
        def fake_get(url, timeout=10):
            if url in ("https://example.com/robots.txt", "https://example.com/sitemap.xml"):
                return make_not_found_response(url)

            if url == "https://example.com/broken/":
                raise requests.ConnectionError(
                    "HTTPSConnectionPool(host='broken', port=443): Max retries exceeded "
                    "with url: / (Caused by NameResolutionError(\"Failed to resolve 'broken' "
                    "([Errno 11001] getaddrinfo failed)\"))"
                )

            pages = {
                "https://example.com/": (
                    "https://example.com/",
                    '<a href="/broken/">Broken</a>',
                ),
            }
            final_url, html = pages[url]
            resp = MagicMock(status_code=200, url=final_url, text=html, headers={})
            resp.raise_for_status.side_effect = None
            return resp

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert result["errors"] == [
            {
                "url": "https://example.com/broken/",
                "error": "Could not resolve 'https://example.com/broken/' -- check the domain and try again.",
            }
        ]

    def test_external_redirects_and_already_traversed_skips_are_never_recorded_as_errors(self):
        # Regression: only a genuine RequestException is an "error" --
        # normal control-flow skips (external redirect, already
        # traversed) must never leak into the errors list.
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/external/">External</a><a href="/dup/">Dup1</a><a href="/dup2/">Dup2</a>',
            ),
            "https://example.com/external/": ("https://other.com/", "<html>elsewhere</html>"),
            "https://example.com/dup/": ("https://example.com/same/", "<html>same</html>"),
            "https://example.com/dup2/": ("https://example.com/same/", "<html>same</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert result["errors"] == []


class TestDiscoverUrls:
    def test_success_when_everything_works(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/about/">About</a>'),
            "https://example.com/about/": ("https://example.com/about/", "<html>about</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = discover_urls("https://example.com/", max_pages=10, max_depth=1)

        assert result == {
            "status": "success",
            "start_url": "https://example.com/",
            "discovered_urls": ["https://example.com/", "https://example.com/about/"],
            "pages_traversed": 2,
            "errors": [],
        }

    def test_partial_when_some_pages_fail_but_others_succeed(self):
        def fake_get(url, timeout=10):
            if url in ("https://example.com/robots.txt", "https://example.com/sitemap.xml"):
                return make_not_found_response(url)

            if url == "https://example.com/broken/":
                raise requests.ConnectionError("boom")
            pages = {
                "https://example.com/": (
                    "https://example.com/",
                    '<a href="/broken/">Broken</a><a href="/ok/">OK</a>',
                ),
                "https://example.com/ok/": ("https://example.com/ok/", "<html>ok</html>"),
            }
            final_url, html = pages[url]
            resp = MagicMock(status_code=200, url=final_url, text=html, headers={})
            resp.raise_for_status.side_effect = None
            return resp

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = discover_urls("https://example.com/", max_pages=10, max_depth=1)

        assert result["status"] == "partial"
        assert result["pages_traversed"] == 2
        assert result["errors"] == [
            {"url": "https://example.com/broken/", "error": "Could not connect to 'https://example.com/broken/'."}
        ]
        assert "https://example.com/ok/" in result["discovered_urls"]

    def test_failed_when_start_url_itself_fails(self):
        def fake_get(url, timeout=10):
            raise requests.ConnectionError("Connection timed out")

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = discover_urls("https://example.com/", max_pages=10, max_depth=1)

        assert result == {
            "status": "failed",
            "start_url": "https://example.com/",
            "discovered_urls": [],
            "pages_traversed": 0,
            "errors": [{"url": "https://example.com/", "error": "Could not connect to 'https://example.com/'."}],
        }

    def test_one_stale_link_among_many_good_pages_is_partial_not_failed(self):
        # The specific rule called out explicitly: a single 404 deep in
        # an otherwise-successful crawl must not be treated the same as
        # "we couldn't meaningfully crawl the site at all."
        def fake_get(url, timeout=10):
            if url in ("https://example.com/robots.txt", "https://example.com/sitemap.xml"):
                return make_not_found_response(url)

            if url == "https://example.com/old-page/":
                raise requests.HTTPError("404 Client Error")
            pages = {
                "https://example.com/": (
                    "https://example.com/",
                    '<a href="/a/">A</a><a href="/old-page/">Old</a>',
                ),
                "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
            }
            final_url, html = pages[url]
            resp = MagicMock(status_code=200, url=final_url, text=html, headers={})
            resp.raise_for_status.side_effect = None
            return resp

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = discover_urls("https://example.com/", max_pages=10, max_depth=1)

        assert result["status"] == "partial"
        assert result["pages_traversed"] == 2

    def test_unexpected_exception_inside_crawl_is_caught_as_failed(self):
        # A bug/unexpected exception INSIDE crawl_stream() (not a per-page
        # RequestException) must never escape discover_urls() as a raw
        # Python exception -- same lesson as tech_detection's pipeline.py.
        with patch("url_discovery.crawler.crawl_stream", side_effect=RuntimeError("unexpected bug")):
            result = discover_urls("https://example.com/", max_pages=10, max_depth=1)

        assert result == {
            "status": "failed",
            "start_url": "https://example.com/",
            "discovered_urls": [],
            "pages_traversed": 0,
            "errors": [{"url": "https://example.com/", "error": "unexpected bug"}],
        }

    def test_start_url_reported_is_the_raw_input_not_a_normalized_form(self):
        # crawl() normalizes start_url internally BEFORE ever fetching
        # (stripping the utm_source here), so the actual request goes to
        # the normalized form -- but discover_urls() should still report
        # back exactly what the caller passed in.
        pages = {
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = discover_urls("https://example.com/?utm_source=test", max_pages=10, max_depth=0)

        assert result["start_url"] == "https://example.com/?utm_source=test"


class TestStreamingEvents:
    """crawl()/discover_urls() (tested everywhere above) are just
    crawl_stream()/discover_urls_stream() exhausted for their final
    "complete" event -- these tests are about the events themselves."""

    def test_crawl_stream_yields_one_url_discovered_event_per_page_in_order(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a><a href="/b/">B</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            events = list(crawl_stream("https://example.com/", max_pages=10, max_depth=1))

        discovered = [e for e in events if e["event"] == "url_discovered"]
        assert [e["url"] for e in discovered] == [
            "https://example.com/",
            "https://example.com/a/",
            "https://example.com/b/",
        ]
        assert [e["count"] for e in discovered] == [1, 2, 3]

        assert events[-1]["event"] == "complete"
        assert events[-1]["result"]["urls"] == [e["url"] for e in discovered]

    def test_crawl_stream_final_event_matches_crawl_return_value(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            events = list(crawl_stream("https://example.com/", max_pages=10, max_depth=1))
            direct_result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert events[-1]["result"] == direct_result

    def test_discover_urls_stream_passes_url_discovered_events_through(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            events = list(discover_urls_stream("https://example.com/", max_pages=10, max_depth=1))

        assert [e["event"] for e in events] == ["url_discovered", "url_discovered", "complete"]

    def test_discover_urls_stream_complete_event_matches_discover_urls_return_value(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            events = list(discover_urls_stream("https://example.com/", max_pages=10, max_depth=1))
            direct_result = discover_urls("https://example.com/", max_pages=10, max_depth=1)

        assert events[-1]["result"] == direct_result

    def test_discover_urls_stream_failure_still_goes_straight_to_a_failed_complete_event(self):
        def fake_get(url, timeout=10):
            raise requests.ConnectionError("Connection timed out")

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            events = list(discover_urls_stream("https://example.com/", max_pages=10, max_depth=1))

        assert [e["event"] for e in events] == ["complete"]
        assert events[0]["result"]["status"] == "failed"

    def test_unexpected_exception_mid_crawl_is_still_caught_as_a_failed_complete_event(self):
        with patch("url_discovery.crawler.crawl_stream", side_effect=RuntimeError("unexpected bug")):
            events = list(discover_urls_stream("https://example.com/", max_pages=10, max_depth=1))

        assert [e["event"] for e in events] == ["complete"]
        assert events[0]["result"] == {
            "status": "failed",
            "start_url": "https://example.com/",
            "discovered_urls": [],
            "pages_traversed": 0,
            "errors": [{"url": "https://example.com/", "error": "unexpected bug"}],
        }


class TestRobotsTxt:
    def test_disallowed_path_is_never_fetched_or_reported(self):
        pages = {
            "https://example.com/robots.txt": (
                "https://example.com/robots.txt",
                "User-agent: *\nDisallow: /private/\n",
            ),
            "https://example.com/": (
                "https://example.com/",
                '<a href="/private/">Private</a><a href="/public/">Public</a>',
            ),
            "https://example.com/public/": ("https://example.com/public/", "<html>public</html>"),
        }
        call_log = []
        fake_get = make_fake_get(pages, call_log)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert "https://example.com/private/" not in call_log
        assert "https://example.com/private/" not in result["urls"]
        assert "https://example.com/public/" in result["urls"]

    def test_robots_txt_fetch_itself_is_not_counted_as_a_traversed_page(self):
        pages = {
            "https://example.com/robots.txt": (
                "https://example.com/robots.txt", "User-agent: *\nDisallow:\n",
            ),
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert result["pages_traversed"] == 1
        assert result["urls"] == ["https://example.com/"]

    def test_missing_robots_txt_allows_everything(self):
        # No explicit robots.txt entry -- make_fake_get's default 404
        # fallback kicks in, which must mean "nothing disallowed," the
        # same convention Python's own robotparser.read() follows.
        pages = {
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://example.com/"]

    def test_403_on_robots_txt_blocks_the_entire_crawl(self):
        def fake_get(url, timeout=10):
            if url == "https://example.com/robots.txt":
                response = MagicMock(status_code=403, headers={})
                error = requests.HTTPError("403 error")
                error.response = response
                response.raise_for_status.side_effect = error
                return response
            if url == "https://example.com/sitemap.xml":
                return make_not_found_response(url)
            raise AssertionError(f"unexpected fetch while robots.txt should have blocked everything: {url}")

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert result["urls"] == []
        assert result["pages_traversed"] == 0

    def test_connection_error_fetching_robots_txt_does_not_block_the_crawl(self):
        # Erring toward "allowed" here: a network hiccup fetching
        # robots.txt itself is not evidence the site wants nothing
        # crawled, and silently killing the whole crawl over it would be
        # a worse failure mode than proceeding.
        def fake_get(url, timeout=10):
            if url == "https://example.com/robots.txt":
                raise requests.ConnectionError("robots.txt unreachable")
            if url == "https://example.com/sitemap.xml":
                return make_not_found_response(url)
            pages = {"https://example.com/": ("https://example.com/", "<html>home</html>")}
            final_url, html = pages[url]
            resp = MagicMock(status_code=200, url=final_url, text=html, headers={})
            resp.raise_for_status.side_effect = None
            return resp

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://example.com/"]


class TestSitemap:
    SITEMAP_XML = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://example.com/from-sitemap-1/</loc></url>"
        "<url><loc>https://example.com/from-sitemap-2/</loc></url>"
        "</urlset>"
    )

    def test_sitemap_urls_are_seeded_and_traversed(self):
        pages = {
            "https://example.com/sitemap.xml": ("https://example.com/sitemap.xml", self.SITEMAP_XML),
            "https://example.com/": ("https://example.com/", "<html>home, no links</html>"),
            "https://example.com/from-sitemap-1/": ("https://example.com/from-sitemap-1/", "<html>1</html>"),
            "https://example.com/from-sitemap-2/": ("https://example.com/from-sitemap-2/", "<html>2</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert "https://example.com/from-sitemap-1/" in result["urls"]
        assert "https://example.com/from-sitemap-2/" in result["urls"]
        # home + 2 sitemap urls -- the sitemap.xml fetch itself doesn't count.
        assert result["pages_traversed"] == 3

    def test_sitemap_fetch_itself_never_appears_in_output(self):
        pages = {
            "https://example.com/sitemap.xml": ("https://example.com/sitemap.xml", self.SITEMAP_XML),
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
            "https://example.com/from-sitemap-1/": ("https://example.com/from-sitemap-1/", "<html>1</html>"),
            "https://example.com/from-sitemap-2/": ("https://example.com/from-sitemap-2/", "<html>2</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert "https://example.com/sitemap.xml" not in result["urls"]

    def test_robots_txt_declared_sitemap_takes_precedence_over_default_path(self):
        pages = {
            "https://example.com/robots.txt": (
                "https://example.com/robots.txt",
                "User-agent: *\nDisallow:\nSitemap: https://example.com/custom-sitemap.xml\n",
            ),
            "https://example.com/custom-sitemap.xml": (
                "https://example.com/custom-sitemap.xml",
                "<urlset><url><loc>https://example.com/from-custom/</loc></url></urlset>",
            ),
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
            "https://example.com/from-custom/": ("https://example.com/from-custom/", "<html>custom</html>"),
        }
        fake_get = make_fake_get(pages)
        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get) as mock_get, \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=0)

        assert "https://example.com/from-custom/" in result["urls"]
        # The default /sitemap.xml path is never requested once robots.txt
        # names a specific one.
        requested_urls = [call.args[0] for call in mock_get.call_args_list]
        assert "https://example.com/sitemap.xml" not in requested_urls
        assert "https://example.com/custom-sitemap.xml" in requested_urls

    def test_off_site_sitemap_entries_are_not_seeded(self):
        pages = {
            "https://example.com/sitemap.xml": (
                "https://example.com/sitemap.xml",
                "<urlset><url><loc>https://other.com/elsewhere/</loc></url></urlset>",
            ),
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://example.com/"]

    def test_malformed_sitemap_xml_does_not_break_the_crawl(self):
        pages = {
            "https://example.com/sitemap.xml": ("https://example.com/sitemap.xml", "not valid xml <<<"),
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://example.com/"]
        assert result["pages_traversed"] == 1

    def test_no_sitemap_present_crawls_normally(self):
        pages = {
            "https://example.com/": ("https://example.com/", '<a href="/a/">A</a>'),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert result["urls"] == ["https://example.com/", "https://example.com/a/"]


class TestWwwIsSameSiteDuringCrawl:
    def test_redirect_to_www_variant_is_not_treated_as_external(self):
        pages = {
            "https://example.com/": ("https://www.example.com/", "<html>home</html>"),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://www.example.com/"]
        assert result["errors"] == []

    def test_canonical_pointing_to_www_variant_is_honored(self):
        pages = {
            "https://example.com/page": (
                "https://example.com/page",
                '<link rel="canonical" href="https://www.example.com/page">',
            ),
        }
        result = run(pages, start_url="https://example.com/page", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://www.example.com/page"]


def _mock_playwright(mock_sync_playwright, launch_side_effect=None):
    """Wires up sync_playwright()'s call chain so crawler.py's
    `sync_playwright().start()` / `.chromium.launch(headless=True)` /
    `.close()` / `.stop()` calls all land on inspectable mocks, without a
    real browser anywhere. Returns (playwright_obj, browser)."""
    playwright_obj = MagicMock()
    mock_sync_playwright.return_value.start.return_value = playwright_obj

    browser = MagicMock()
    if launch_side_effect is not None:
        playwright_obj.chromium.launch.side_effect = launch_side_effect
    else:
        playwright_obj.chromium.launch.return_value = browser

    return playwright_obj, browser


class TestBrowserFallback:
    def test_thin_page_is_rendered_and_its_links_are_discovered(self):
        # The raw HTML has no links at all (a bare shell); only the
        # RENDERED html has the real navigation -- proving the fallback
        # actually contributes links a pure-HTTP crawl would have missed.
        pages = {
            "https://example.com/": (
                "https://example.com/", '<div id="root"></div><script src="/app.js"></script>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
        }
        fake_get = make_fake_get(pages)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright, \
             patch(
                 "url_discovery.crawler.render_page_html",
                 return_value='<a href="/a/">A</a>',
             ):
            _mock_playwright(mock_sync_playwright)
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert "https://example.com/a/" in result["urls"]

    def test_browser_is_launched_once_and_reused_across_pages(self):
        pages = {
            "https://example.com/": (
                "https://example.com/", '<a href="/a/">A</a><a href="/b/">B</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "thin a"),
            "https://example.com/b/": ("https://example.com/b/", "thin b"),
        }
        fake_get = make_fake_get(pages)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright, \
             patch("url_discovery.crawler.render_page_html", return_value="<html>rendered</html>"):
            playwright_obj, _ = _mock_playwright(mock_sync_playwright)
            crawl("https://example.com/", max_pages=10, max_depth=1)

        assert mock_sync_playwright.call_count == 1
        assert playwright_obj.chromium.launch.call_count == 1

    def test_render_cap_stops_further_renders_but_not_the_crawl(self):
        pages = {
            "https://example.com/": (
                "https://example.com/", '<a href="/a/">A</a><a href="/b/">B</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "thin a"),
            "https://example.com/b/": ("https://example.com/b/", "thin b"),
        }
        fake_get = make_fake_get(pages)
        render_calls = []

        def fake_render(browser, url):
            # Returns the SAME links the raw HTML already had -- rendering
            # doesn't change what's discoverable here, it's only being
            # exercised to prove the render CAP itself, not to add links.
            render_calls.append(url)
            return '<a href="/a/">A</a><a href="/b/">B</a>'

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright, \
             patch("url_discovery.crawler.render_page_html", side_effect=fake_render), \
             patch("url_discovery.crawler.MAX_BROWSER_RENDERS_PER_CRAWL", 1):
            _mock_playwright(mock_sync_playwright)
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        # Only the start page (the only one queued before the cap is hit)
        # gets rendered -- the cap does not stop the crawl itself, just
        # further rendering; /a/ and /b/ still get traversed on raw HTML.
        assert len(render_calls) == 1
        assert result["pages_traversed"] == 3

    def test_render_failure_for_one_page_falls_back_to_raw_html_not_an_error(self):
        pages = {
            "https://example.com/": ("https://example.com/", "thin start page"),
        }
        fake_get = make_fake_get(pages)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright, \
             patch("url_discovery.crawler.render_page_html", side_effect=RuntimeError("page.goto timed out")):
            _mock_playwright(mock_sync_playwright)
            result = crawl("https://example.com/", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://example.com/"]
        assert result["pages_traversed"] == 1
        assert result["errors"] == []  # a render failure is not a page-fetch error

    def test_launch_failure_disables_browser_for_the_rest_of_the_crawl(self):
        pages = {
            "https://example.com/": (
                "https://example.com/", '<a href="/a/">A</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "thin a"),
        }
        fake_get = make_fake_get(pages)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright, \
             patch("url_discovery.crawler.render_page_html") as mock_render:
            playwright_obj, _ = _mock_playwright(
                mock_sync_playwright, launch_side_effect=RuntimeError("Executable doesn't exist")
            )
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        # The launch was only attempted once, not once per thin page --
        # and the crawl still completed on raw HTML for both pages.
        assert playwright_obj.chromium.launch.call_count == 1
        mock_render.assert_not_called()
        assert result["pages_traversed"] == 2

    def test_browser_and_playwright_are_closed_after_the_crawl(self):
        pages = {
            "https://example.com/": ("https://example.com/", "thin start page"),
        }
        fake_get = make_fake_get(pages)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright, \
             patch("url_discovery.crawler.render_page_html", return_value="<html>rendered</html>"):
            playwright_obj, browser = _mock_playwright(mock_sync_playwright)
            crawl("https://example.com/", max_pages=10, max_depth=0)

        browser.close.assert_called_once()
        playwright_obj.stop.assert_called_once()

    def test_canonical_tag_only_present_in_rendered_html_is_honored(self):
        pages = {
            "https://example.com/page": ("https://example.com/page", "thin page"),
        }
        fake_get = make_fake_get(pages)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright, \
             patch(
                 "url_discovery.crawler.render_page_html",
                 return_value='<link rel="canonical" href="https://example.com/canonical-page">',
             ):
            _mock_playwright(mock_sync_playwright)
            result = crawl("https://example.com/page", max_pages=10, max_depth=0)

        assert result["urls"] == ["https://example.com/canonical-page"]

    def test_a_page_with_enough_visible_text_never_launches_a_browser(self):
        # Regression: this test does NOT override should_render_with_browser
        # (autouse patches it to always return False) -- if crawl() ever
        # called it wrong (e.g. inverted the condition), sync_playwright
        # would get called here and this assertion would catch it.
        pages = {
            "https://example.com/": ("https://example.com/", "<html>plenty of real content</html>"),
        }
        fake_get = make_fake_get(pages)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"), \
             patch("url_discovery.crawler.sync_playwright") as mock_sync_playwright:
            crawl("https://example.com/", max_pages=10, max_depth=0)

        mock_sync_playwright.assert_not_called()


class TestIncludeExcludePaths:
    def test_exclude_paths_stops_a_link_from_ever_being_queued(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/blog/post">Post</a><a href="/legal/terms">Terms</a>',
            ),
            "https://example.com/blog/post": ("https://example.com/blog/post", "<html>post</html>"),
        }
        call_log = []
        result = run(
            pages, call_log,
            start_url="https://example.com/", max_pages=10, max_depth=1,
            exclude_paths=[r"^/legal/"],
        )

        assert "https://example.com/legal/terms" not in call_log
        assert result["urls"] == ["https://example.com/", "https://example.com/blog/post"]

    def test_include_paths_only_queues_matching_links(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/blog/post">Post</a><a href="/about">About</a>',
            ),
            "https://example.com/blog/post": ("https://example.com/blog/post", "<html>post</html>"),
        }
        call_log = []
        result = run(
            pages, call_log,
            start_url="https://example.com/", max_pages=10, max_depth=1,
            include_paths=[r"^/blog/"],
        )

        assert "https://example.com/about" not in call_log
        assert result["urls"] == ["https://example.com/", "https://example.com/blog/post"]

    def test_start_url_is_crawled_even_if_it_would_not_match_include_paths(self):
        # The filter only ever gates DISCOVERED links -- the URL a caller
        # explicitly asked to crawl is never subject to its own rules.
        pages = {
            "https://example.com/": ("https://example.com/", "<html>home</html>"),
        }
        result = run(
            pages, start_url="https://example.com/", max_pages=10, max_depth=0,
            include_paths=[r"^/blog/"],
        )

        assert result["urls"] == ["https://example.com/"]

    def test_exclude_wins_when_a_link_matches_both_include_and_exclude(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/blog/draft">Draft</a>',
            ),
        }
        call_log = []
        result = run(
            pages, call_log,
            start_url="https://example.com/", max_pages=10, max_depth=1,
            include_paths=[r"^/blog/"], exclude_paths=[r"draft"],
        )

        assert "https://example.com/blog/draft" not in call_log
        assert result["urls"] == ["https://example.com/"]


class TestRestrictToStartPath:
    def test_restrict_to_start_path_stays_under_the_starting_directory(self):
        pages = {
            "https://example.com/docs/": (
                "https://example.com/docs/",
                '<a href="/docs/guide">Guide</a><a href="/pricing">Pricing</a>',
            ),
            "https://example.com/docs/guide": ("https://example.com/docs/guide", "<html>guide</html>"),
        }
        call_log = []
        result = run(
            pages, call_log,
            start_url="https://example.com/docs/", max_pages=10, max_depth=1,
            restrict_to_start_path=True,
        )

        assert "https://example.com/pricing" not in call_log
        assert result["urls"] == ["https://example.com/docs/", "https://example.com/docs/guide"]

    def test_off_by_default_crawls_the_whole_domain(self):
        pages = {
            "https://example.com/docs/": (
                "https://example.com/docs/",
                '<a href="/pricing">Pricing</a>',
            ),
            "https://example.com/pricing": ("https://example.com/pricing", "<html>pricing</html>"),
        }
        result = run(pages, start_url="https://example.com/docs/", max_pages=10, max_depth=1)

        assert "https://example.com/pricing" in result["urls"]


class TestAllowSubdomains:
    def test_off_by_default_a_subdomain_link_is_dropped(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="https://blog.example.com/post">Post</a>',
            ),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert result["urls"] == ["https://example.com/"]

    def test_allow_subdomains_true_follows_and_traverses_a_subdomain_link(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="https://blog.example.com/post">Post</a>',
            ),
            "https://blog.example.com/post": ("https://blog.example.com/post", "<html>post</html>"),
        }
        result = run(
            pages, start_url="https://example.com/", max_pages=10, max_depth=1,
            allow_subdomains=True,
        )

        assert result["urls"] == ["https://example.com/", "https://blog.example.com/post"]


class TestAllowExternalLinks:
    def test_off_by_default_an_external_link_is_never_recorded(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="https://other.com/page">Other</a>',
            ),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert result["urls"] == ["https://example.com/"]
        assert result["pages_traversed"] == 1

    def test_allow_external_links_records_it_but_never_expands_it(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="https://other.com/page">Other</a>',
            ),
            "https://other.com/page": (
                "https://other.com/page",
                '<a href="https://other.com/never-reached">Nope</a>',
            ),
        }
        call_log = []
        result = run(
            pages, call_log,
            start_url="https://example.com/", max_pages=10, max_depth=2,
            allow_external_links=True,
        )

        assert result["urls"] == ["https://example.com/", "https://other.com/page"]
        assert "https://other.com/never-reached" not in call_log

    def test_allow_external_links_does_not_apply_start_domain_robots_txt_to_it(self):
        # robots.txt was loaded for example.com -- it says nothing valid
        # about other.com, so it must never be consulted for it, even
        # though example.com's own robots.txt happens to disallow the
        # exact path the external link uses.
        pages = {
            "https://example.com/robots.txt": (
                "https://example.com/robots.txt",
                "User-agent: *\nDisallow: /page\n",
            ),
            "https://example.com/": (
                "https://example.com/",
                '<a href="https://other.com/page">Other</a>',
            ),
            "https://other.com/page": ("https://other.com/page", "<html>other</html>"),
        }
        result = run(
            pages, start_url="https://example.com/", max_pages=10, max_depth=1,
            allow_external_links=True,
        )

        assert "https://other.com/page" in result["urls"]


class TestIgnoreQueryParameters:
    def test_two_links_differing_only_by_query_collapse_to_one_traversal(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/search?q=shoes">Shoes</a><a href="/search?q=boots">Boots</a>',
            ),
            "https://example.com/search": ("https://example.com/search", "<html>search</html>"),
        }
        call_log = []
        result = run(
            pages, call_log,
            start_url="https://example.com/", max_pages=10, max_depth=1,
            ignore_query_parameters=True,
        )

        assert call_log.count("https://example.com/search") == 1
        assert result["urls"] == ["https://example.com/", "https://example.com/search"]


class TestIgnoreRobotsTxt:
    def test_off_by_default_a_disallowed_path_is_still_blocked(self):
        pages = {
            "https://example.com/robots.txt": (
                "https://example.com/robots.txt",
                "User-agent: *\nDisallow: /private/\n",
            ),
            "https://example.com/": (
                "https://example.com/",
                '<a href="/private/">Private</a>',
            ),
        }
        result = run(pages, start_url="https://example.com/", max_pages=10, max_depth=1)

        assert "https://example.com/private/" not in result["urls"]

    def test_ignore_robots_txt_true_crawls_a_disallowed_path_anyway(self):
        pages = {
            "https://example.com/robots.txt": (
                "https://example.com/robots.txt",
                "User-agent: *\nDisallow: /private/\n",
            ),
            "https://example.com/": (
                "https://example.com/",
                '<a href="/private/">Private</a>',
            ),
            "https://example.com/private/": ("https://example.com/private/", "<html>private</html>"),
        }
        result = run(
            pages, start_url="https://example.com/", max_pages=10, max_depth=1,
            ignore_robots_txt=True,
        )

        assert "https://example.com/private/" in result["urls"]


class TestConcurrentDiscovery:
    """Uses a lock-guarded in-flight counter (with a real, short
    threading.Event().wait() inside the fake network call -- NOT
    time.sleep(), since every test here patches
    url_discovery.fetcher.time.sleep to skip the crawler's own pacing,
    and time.sleep is one shared function on the time module, so that
    patch would silently neutralize a plain time.sleep() call anywhere
    in the process, this fake included) to prove genuine overlap, not
    just correct end results. A result-only test would pass even if
    max_concurrency silently did nothing, since the sequential code path
    already produces correct output -- these confirm fetches actually
    ran in parallel."""

    def _tracking_fake_get(self, pages, in_flight_holder):
        lock = threading.Lock()

        def fake_get(url, timeout=10):
            if url in ("https://example.com/robots.txt", "https://example.com/sitemap.xml"):
                return make_not_found_response(url)

            with lock:
                in_flight_holder["current"] += 1
                in_flight_holder["max"] = max(in_flight_holder["max"], in_flight_holder["current"])

            # NOT time.sleep(): every test in this file patches
            # url_discovery.fetcher.time.sleep to skip the crawler's own
            # pacing -- but time.sleep is a single shared function on the
            # (singleton) time module, so patching it through ANY import
            # path replaces it everywhere in the process, including a
            # plain time.sleep() called right here. threading.Event().wait()
            # is a different primitive entirely, unaffected by that patch,
            # so it's what actually creates a real overlap window to
            # detect below.
            threading.Event().wait(0.05)

            with lock:
                in_flight_holder["current"] -= 1

            final_url, html = pages[url]
            response = MagicMock(status_code=200, url=final_url, text=html, headers={})
            response.raise_for_status.side_effect = None
            return response

        return fake_get

    def test_max_concurrency_default_is_strictly_sequential(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a><a href="/b/">B</a><a href="/c/">C</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
            "https://example.com/c/": ("https://example.com/c/", "<html>c</html>"),
        }
        in_flight = {"current": 0, "max": 0}
        fake_get = self._tracking_fake_get(pages, in_flight)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert in_flight["max"] == 1
        assert len(result["urls"]) == 4

    def test_max_concurrency_above_one_genuinely_overlaps_fetches(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a><a href="/b/">B</a><a href="/c/">C</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
            "https://example.com/c/": ("https://example.com/c/", "<html>c</html>"),
        }
        in_flight = {"current": 0, "max": 0}
        fake_get = self._tracking_fake_get(pages, in_flight)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            result = crawl("https://example.com/", max_pages=10, max_depth=1, max_concurrency=3)

        # Lenient bound (>=2, not ==3) -- proves real overlap without the
        # test depending on exact thread-scheduling timing.
        assert in_flight["max"] >= 2
        assert len(result["urls"]) == 4

    def test_concurrent_and_sequential_crawls_discover_the_same_urls(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a><a href="/b/">B</a><a href="/c/">C</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", '<a href="/d/">D</a>'),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
            "https://example.com/c/": ("https://example.com/c/", "<html>c</html>"),
            "https://example.com/d/": ("https://example.com/d/", "<html>d</html>"),
        }

        sequential = run(dict(pages), start_url="https://example.com/", max_pages=10, max_depth=2)
        concurrent_result = run(
            dict(pages), start_url="https://example.com/", max_pages=10, max_depth=2,
            max_concurrency=4,
        )

        assert set(sequential["urls"]) == set(concurrent_result["urls"])
        assert sequential["pages_traversed"] == concurrent_result["pages_traversed"]

    def test_delay_seconds_forces_max_concurrency_back_to_one(self):
        pages = {
            "https://example.com/": (
                "https://example.com/",
                '<a href="/a/">A</a><a href="/b/">B</a>',
            ),
            "https://example.com/a/": ("https://example.com/a/", "<html>a</html>"),
            "https://example.com/b/": ("https://example.com/b/", "<html>b</html>"),
        }
        in_flight = {"current": 0, "max": 0}
        fake_get = self._tracking_fake_get(pages, in_flight)

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=fake_get), \
             patch("url_discovery.fetcher.time.sleep"):
            crawl(
                "https://example.com/", max_pages=10, max_depth=1,
                max_concurrency=5, delay_seconds=0.01,
            )

        assert in_flight["max"] == 1

    def test_delay_seconds_overrides_the_default_pacing_gap(self):
        # robots.txt/sitemap.xml are fetched outside the queue-driven
        # dispatch loop and don't take delay_seconds -- only the actual
        # page fetch does, so this checks that call specifically rather
        # than asserting every sleep call used the custom delay.
        pages = {"https://example.com/": ("https://example.com/", "<html>home</html>")}

        with patch("url_discovery.fetcher.requests.Session.get", side_effect=make_fake_get(pages)), \
             patch("url_discovery.fetcher.time.sleep") as mock_sleep:
            crawl("https://example.com/", max_pages=10, max_depth=0, delay_seconds=2.5)

        assert any(call.args == (2.5,) for call in mock_sleep.call_args_list)
