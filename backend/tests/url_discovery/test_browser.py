# Regression suite for should_render_with_browser() only -- a pure
# function on an HTML string, no Playwright involved, so this needs no
# mocking. render_page_html() itself needs a real (or at least
# Playwright-shaped) Browser object to do anything meaningful, so it's
# covered by test_crawler.py's TestBrowserFallback (mocked) and
# tests/url_discovery/network/ (a real browser) instead.

from url_discovery.browser import should_render_with_browser


class TestShouldRenderWithBrowser:
    def test_bare_spa_shell_needs_a_browser(self):
        html = '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'
        assert should_render_with_browser(html) is True

    def test_a_real_if_sparse_page_does_not(self):
        # Calibrated the same way tech_detection/fallback.py was: real
        # example.com content measures 139 visible characters, comfortably
        # over the 80-character threshold.
        html = (
            "<html><body><h1>Example Domain</h1>"
            "<p>This domain is for use in illustrative examples in documents. "
            "You may use this domain in literature without prior coordination "
            "or asking for permission.</p></body></html>"
        )
        assert should_render_with_browser(html) is False

    def test_script_and_style_text_does_not_count_as_visible_content(self):
        # A long inline script/style block could make an otherwise-empty
        # shell LOOK full of text if it weren't excluded first -- that
        # would defeat the whole point of the heuristic.
        html = (
            "<html><head><style>" + ("body { color: red; } " * 20) + "</style></head>"
            "<body><div id=\"root\"></div>"
            "<script>" + ("console.log('hi');" * 20) + "</script></body></html>"
        )
        assert should_render_with_browser(html) is True

    def test_empty_html_needs_a_browser(self):
        assert should_render_with_browser("") is True
