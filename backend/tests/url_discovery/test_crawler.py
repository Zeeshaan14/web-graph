# Regression suite for crawler.py: the BFS traversal, the
# traversal-vs-output identity split, redirect handling, canonical
# handling, the fallback-fetch integration, and the discover_urls()
# feature-contract wrapper. Fully offline -- mocks only the network
# boundary (Session.get / time.sleep), so the real traversal/queue/dedup
# logic all runs for real.

from unittest.mock import MagicMock, patch

import requests

from url_discovery.crawler import crawl, discover_urls
from tests.url_discovery.helpers import make_fake_get


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

        session_get = MagicMock(side_effect=[resp_home, resp_slow_429, resp_slow_200])

        with patch("url_discovery.fetcher.requests.Session.get", session_get), \
             patch("url_discovery.fetcher.time.sleep") as sleep_mock:
            result = crawl("https://example.com/", max_pages=10, max_depth=1)

        assert "https://example.com/slow/" in result["urls"]
        assert result["errors"] == []  # recovered -- not a recorded failure
        assert session_get.call_count == 3
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


class TestFailedRequestIsRecordedNotFatal:
    def test_a_persistently_failing_link_is_recorded_as_an_error_and_does_not_stop_the_crawl(self):
        def fake_get(url, timeout=10):
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
        assert result["errors"] == [{"url": "https://example.com/broken/", "error": "boom"}]
        # The start page and /ok/ both succeeded -- 2 traversed, 1 recorded failure.
        assert result["pages_traversed"] == 2

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
        assert result["errors"] == [{"url": "https://example.com/broken/", "error": "boom"}]
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
            "errors": [{"url": "https://example.com/", "error": "Connection timed out"}],
        }

    def test_one_stale_link_among_many_good_pages_is_partial_not_failed(self):
        # The specific rule called out explicitly: a single 404 deep in
        # an otherwise-successful crawl must not be treated the same as
        # "we couldn't meaningfully crawl the site at all."
        def fake_get(url, timeout=10):
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
        # A bug/unexpected exception INSIDE crawl() (not a per-page
        # RequestException) must never escape discover_urls() as a raw
        # Python exception -- same lesson as tech_detection's pipeline.py.
        with patch("url_discovery.crawler.crawl", side_effect=RuntimeError("unexpected bug")):
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
