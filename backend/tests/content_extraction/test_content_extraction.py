# Regression suite for content_extraction.py. Fully offline -- requests.get
# is mocked, nothing here touches the network.

from unittest.mock import MagicMock, patch

import requests

from content_extraction.content_extraction import (
    BROWSER_HEADERS,
    MAX_RESPONSE_BYTES,
    extract_content,
)

PATCH_TARGET = "content_extraction.content_extraction.requests.get"


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

    def test_prefers_article_over_main_and_whole_page(self):
        html = """
        <html><body>
            <main><p>Main content paragraph.</p></main>
            <article><p>Article content paragraph.</p></article>
            <p>Stray page paragraph.</p>
        </body></html>
        """
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["paragraphs"] == ["Article content paragraph."]

    def test_falls_back_to_main_when_no_article(self):
        html = "<html><body><main><p>Main content.</p></main><p>Stray.</p></body></html>"
        with patch(PATCH_TARGET, return_value=make_response(html)):
            result = extract_content("https://example.com/")

        assert result["paragraphs"] == ["Main content."]

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
