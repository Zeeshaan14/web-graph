# Regression suite for content_extraction.py. Fully offline -- requests.get
# is mocked, nothing here touches the network.

from unittest.mock import MagicMock, patch

import pytest
import requests

from content_extraction.content_extraction import (
    BROWSER_HEADERS,
    MAX_RESPONSE_BYTES,
    REQUEST_DELAY_SECONDS,
    RETRY_FALLBACK_SECONDS,
    extract_content,
)

PATCH_TARGET = "content_extraction.content_extraction.requests.get"
SLEEP_TARGET = "content_extraction.content_extraction.time.sleep"
SHOULD_RENDER_TARGET = "content_extraction.content_extraction.should_render_with_browser"


@pytest.fixture(autouse=True)
def no_real_sleep():
    # extract_content() now paces every fetch with a real time.sleep() --
    # autouse so every test in this file gets that mocked out without
    # having to say so itself; tests that care about the sleep CALLS
    # (TestPacingAndRetry) request their own patch on the same target,
    # which layers cleanly on top of this one for their duration.
    with patch(SLEEP_TARGET):
        yield


@pytest.fixture(autouse=True)
def no_real_browser():
    # extract_content() now decides whether the fetched HTML looks like an
    # unrendered SPA shell and is worth a browser render -- every fixture
    # in this file is tiny HTML, which would trip that heuristic and try
    # to launch a real Chromium browser during an "offline" test run.
    # Autouse so every test defaults to "never render"; TestBrowserFallback
    # overrides this patch locally for the tests actually exercising the
    # browser-rendering path itself.
    with patch(SHOULD_RENDER_TARGET, return_value=False):
        yield


def make_response(html, status=200, content_type="text/html; charset=utf-8"):
    response = MagicMock()
    response.status_code = status
    response.text = html
    response.headers = {"content-type": content_type}
    response.iter_content.return_value = [html.encode("utf-8")]
    response.raise_for_status.side_effect = (
        requests.HTTPError(f"{status} error") if status >= 400 else None
    )
    return response


class TestExtractContentSuccess:
    def test_extracts_title_headings_and_paragraphs(self):
        html = """
        <html><head><title>My Article</title></head>
        <body>
            <article>
                <h1>Main Heading</h1>
                <p>First paragraph.</p>
                <h2>Sub Heading</h2>
                <p>Second paragraph.</p>
            </article>
        </body></html>
        """
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/article")

        assert result["status"] == "success"
        assert result["url"] == "https://example.com/article"
        assert result["title"] == "My Article"
        assert result["headings"] == ["Main Heading", "Sub Heading"]
        assert result["paragraphs"] == ["First paragraph.", "Second paragraph."]
        assert result["error"] is None

    def test_falls_back_to_whole_page_when_no_article_or_main(self):
        html = "<html><body><div><p>Just a paragraph.</p></div></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["paragraphs"] == ["Just a paragraph."]

    def test_title_is_none_when_missing(self):
        html = "<html><body><article><p>Text.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["title"] is None

    def test_empty_and_whitespace_only_tags_are_excluded(self):
        html = """
        <html><body><article>
            <h2></h2>
            <h2>   </h2>
            <p></p>
            <p>Real paragraph.</p>
        </article></body></html>
        """
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["headings"] == []
        assert result["paragraphs"] == ["Real paragraph."]

    def test_only_h1_h2_h3_are_collected(self):
        html = "<html><body><article><h1>H1</h1><h4>H4</h4><h2>H2</h2></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["headings"] == ["H1", "H2"]


class TestBoilerplateStripping:
    def test_script_style_noscript_nav_footer_aside_are_removed(self):
        html = """
        <html><body><article>
            <script>var x = "script paragraph should not appear";</script>
            <style>.p { color: red; }</style>
            <nav><p>Nav paragraph.</p></nav>
            <footer><p>Footer paragraph.</p></footer>
            <aside><p>Aside paragraph.</p></aside>
            <p>Real content.</p>
        </article></body></html>
        """
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["paragraphs"] == ["Real content."]

    def test_boilerplate_disguised_as_a_real_tag_is_still_excluded(self):
        # The actual bug that motivated switching to trafilatura: a real
        # newsletter-signup CTA on Smashing Magazine survived the OLD
        # tag-list stripper because it was a <div class="...aside...">,
        # not an actual <aside> element -- a fixed tag list can never
        # catch that; content-density scoring can. This recreates that
        # exact shape (a CTA nested INSIDE the article via a CSS class
        # that merely looks like an aside) alongside a real <aside> and
        # normal nav/footer, with enough real paragraph text for
        # trafilatura's density heuristics to actually have something to
        # judge -- a one-line paragraph gives it no signal either way.
        html = """
        <html><body>
            <nav><a href="/">Home</a></nav>
            <article>
                <h1>How Core Web Vitals Work</h1>
                <p>Core Web Vitals are a set of specific factors that Google
                considers important in a webpage's overall user experience.
                They measure dimensions of web usability such as load time,
                interactivity, and the stability of content as it loads.</p>
                <p>The three current Core Web Vitals metrics measure loading
                performance, interactivity, and visual stability, and each
                one maps to a concrete, measurable moment in a page's life
                cycle rather than a vague notion of "feels fast."</p>
                <div class="c-garfield-aside--meta">
                    <h3>Get The Newsletter</h3>
                    <p>Subscribe to our weekly newsletter for the latest
                    articles on web performance delivered to your inbox.</p>
                </div>
            </article>
            <aside>
                <h3>Related Posts</h3>
                <p>Check out our other articles on performance optimization.</p>
            </aside>
            <footer><p>Copyright 2024 Example Site.</p></footer>
        </body></html>
        """
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/core-web-vitals")

        assert result["headings"] == ["How Core Web Vitals Work"]
        assert len(result["paragraphs"]) == 2
        combined = " ".join(result["paragraphs"]).lower()
        assert "newsletter" not in combined
        assert "related posts" not in combined
        assert "copyright" not in combined


class TestFailureHandling:
    def test_connection_error_returns_failed(self):
        with patch(PATCH_TARGET, side_effect=requests.ConnectionError("boom")):
            result = extract_content("https://example.com/")

        assert result == {
            "status": "failed",
            "url": "https://example.com/",
            "title": None,
            "headings": [],
            "paragraphs": [],
            "error": "boom",
        }

    def test_timeout_returns_failed(self):
        with patch(PATCH_TARGET, side_effect=requests.Timeout("timed out")):
            result = extract_content("https://example.com/")

        assert result["status"] == "failed"
        assert result["error"] == "timed out"

    def test_http_error_status_returns_failed(self):
        with patch(PATCH_TARGET, return_value=make_response("", status=404)):
            result = extract_content("https://example.com/missing")

        assert result["status"] == "failed"
        assert "404" in result["error"]

    def test_non_html_content_type_returns_failed_without_parsing(self):
        with patch(PATCH_TARGET, return_value=make_response("", content_type="image/png")):
            result = extract_content("https://example.com/photo.png")

        assert result["status"] == "failed"
        assert "image/png" in result["error"]
        assert result["headings"] == []
        assert result["paragraphs"] == []

    def test_content_type_check_is_case_insensitive(self):
        html = "<html><body><article><p>Text.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html, content_type="TEXT/HTML; CHARSET=UTF-8")):
            result = extract_content("https://example.com/")

        assert result["status"] == "success"

    def test_missing_content_type_header_returns_failed(self):
        response = make_response("<html></html>")
        response.headers = {}  # no content-type at all
        with patch(PATCH_TARGET, return_value=response):
            result = extract_content("https://example.com/")

        assert result["status"] == "failed"
        assert "unknown content type" in result["error"]


class TestResponseSizeLimit:
    def test_content_length_header_over_cap_returns_failed_without_reading_body(self):
        response = make_response("<html>small</html>")
        response.headers["content-length"] = str(MAX_RESPONSE_BYTES + 1)
        with patch(PATCH_TARGET, return_value=response):
            result = extract_content("https://example.com/huge")

        assert result["status"] == "failed"
        assert "too large" in result["error"].lower()
        response.iter_content.assert_not_called()

    def test_body_exceeding_cap_while_streaming_is_caught_even_without_a_content_length_header(self):
        response = make_response("<html></html>")
        response.iter_content.return_value = [b"x" * (MAX_RESPONSE_BYTES + 1)]
        with patch(PATCH_TARGET, return_value=response):
            result = extract_content("https://example.com/huge")

        assert result["status"] == "failed"
        assert "exceed" in result["error"].lower()
        assert result["paragraphs"] == []

    def test_body_within_the_cap_is_parsed_normally(self):
        html = "<html><body><article><p>Small page.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["status"] == "success"
        assert result["paragraphs"] == ["Small page."]

    def test_malformed_content_length_header_is_ignored_not_fatal(self):
        response = make_response("<html><body><article><p>Fine.</p></article></body></html>")
        response.headers["content-length"] = "not-a-number"
        with patch(PATCH_TARGET, return_value=response):
            result = extract_content("https://example.com/")

        assert result["status"] == "success"
        assert result["paragraphs"] == ["Fine."]


class TestRequestConfiguration:
    def test_sends_browser_headers(self):
        html = "<html><body><article><p>Text.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)) as mock_get:
            extract_content("https://example.com/")

        assert mock_get.call_args.kwargs["headers"] == BROWSER_HEADERS

    def test_sends_a_timeout(self):
        html = "<html><body><article><p>Text.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)) as mock_get:
            extract_content("https://example.com/")

        assert mock_get.call_args.kwargs["timeout"] == 10

    def test_streams_the_response_instead_of_buffering_it_whole(self):
        html = "<html><body><article><p>Text.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)) as mock_get:
            extract_content("https://example.com/")

        assert mock_get.call_args.kwargs["stream"] is True


class TestPacingAndRetry:
    def test_pacing_delay_follows_every_request(self):
        html = "<html><body><article><p>Text.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)), \
             patch(SLEEP_TARGET) as mock_sleep:
            extract_content("https://example.com/")

        assert any(call.args and call.args[0] == REQUEST_DELAY_SECONDS for call in mock_sleep.call_args_list)

    def test_429_with_retry_after_header_waits_then_succeeds(self):
        response_429 = make_response("", status=429)
        response_429.headers["Retry-After"] = "2"
        response_200 = make_response("<html><body><article><p>Recovered.</p></article></body></html>")

        with patch(PATCH_TARGET, side_effect=[response_429, response_200]) as mock_get, \
             patch(SLEEP_TARGET) as mock_sleep:
            result = extract_content("https://example.com/")

        assert result["status"] == "success"
        assert result["paragraphs"] == ["Recovered."]
        assert mock_get.call_count == 2
        assert any(call.args and call.args[0] == 2.0 for call in mock_sleep.call_args_list)

    def test_429_without_retry_after_uses_the_fallback_wait(self):
        response_429 = make_response("", status=429)
        response_200 = make_response("<html><body><article><p>Recovered.</p></article></body></html>")

        with patch(PATCH_TARGET, side_effect=[response_429, response_200]), \
             patch(SLEEP_TARGET) as mock_sleep:
            result = extract_content("https://example.com/")

        assert result["status"] == "success"
        assert any(
            call.args and call.args[0] == RETRY_FALLBACK_SECONDS for call in mock_sleep.call_args_list
        )

    def test_persistent_429_is_reported_as_failed_after_exactly_one_retry(self):
        response_429_first = make_response("", status=429)
        response_429_second = make_response("", status=429)

        with patch(PATCH_TARGET, side_effect=[response_429_first, response_429_second]) as mock_get:
            result = extract_content("https://example.com/")

        assert result["status"] == "failed"
        assert mock_get.call_count == 2  # exactly one retry, not a retry loop

    def test_non_429_failure_is_not_retried(self):
        with patch(PATCH_TARGET, return_value=make_response("", status=500)) as mock_get:
            result = extract_content("https://example.com/")

        assert result["status"] == "failed"
        assert mock_get.call_count == 1


class TestBrowserFallback:
    RENDER_TARGET = "content_extraction.content_extraction.render_page_html"

    def test_thin_page_is_rendered_and_its_content_is_extracted(self):
        # Raw HTML is a bare shell with no real content at all; only the
        # RENDERED html has a real article -- proving the fallback
        # actually contributes content a pure-HTTP fetch would have missed.
        shell_html = '<div id="root"></div><script src="/app.js"></script>'
        rendered_html = (
            "<html><head><title>Rendered Title</title></head>"
            "<body><article><h1>Real Heading</h1>"
            "<p>Real paragraph that only exists after JS runs.</p>"
            "</article></body></html>"
        )
        with patch(PATCH_TARGET, return_value=make_response(shell_html)), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch(self.RENDER_TARGET, return_value=rendered_html) as mock_render:
            result = extract_content("https://example.com/app")

        mock_render.assert_called_once_with("https://example.com/app")
        assert result["status"] == "success"
        assert result["title"] == "Rendered Title"
        assert result["headings"] == ["Real Heading"]
        assert result["paragraphs"] == ["Real paragraph that only exists after JS runs."]

    def test_render_failure_falls_back_to_the_raw_html_not_a_failed_result(self):
        shell_html = '<html><head><title>Shell Title</title></head><body><div id="root"></div></body></html>'
        with patch(PATCH_TARGET, return_value=make_response(shell_html)), \
             patch(SHOULD_RENDER_TARGET, return_value=True), \
             patch(self.RENDER_TARGET, side_effect=RuntimeError("page.goto timed out")):
            result = extract_content("https://example.com/app")

        # Not a failure -- the raw HTML was still a valid fetch, extraction
        # just proceeds on it instead of a rendered version.
        assert result["status"] == "success"
        assert result["title"] == "Shell Title"
        assert result["paragraphs"] == []

    def test_a_page_with_enough_visible_text_never_launches_a_browser(self):
        # Regression: this test does NOT override should_render_with_browser
        # (autouse patches it to always return False) -- if extract_content()
        # ever called it wrong, render_page_html would get called here and
        # this assertion would catch it.
        html = "<html><body><article><p>Plenty of real, substantial content here.</p></article></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)), \
             patch(self.RENDER_TARGET) as mock_render:
            extract_content("https://example.com/")

        mock_render.assert_not_called()
