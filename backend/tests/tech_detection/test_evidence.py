# Regression suite for evidence.py: extraction, normalization, and the
# HTTP+browser merge logic. Fully synthetic/offline.

from tech_detection.evidence import extract_html_signals, build_evidence_from_parts, merge_evidence


class TestExtractHtmlSignals:
    def test_collects_script_src_stylesheet_href_and_meta(self):
        html = (
            '<script src="/app.js"></script>'
            '<link rel="stylesheet" href="/app.css">'
            '<meta name="generator" content="Test 1.0">'
        )
        signals = extract_html_signals(html)

        assert signals["script_src"] == ["/app.js"]
        assert signals["stylesheet_href"] == ["/app.css"]
        assert signals["meta"] == [{"name": "generator", "property": None, "content": "test 1.0"}]

    def test_inline_script_without_src_is_ignored(self):
        html = '<script>console.log("hi")</script>'
        assert extract_html_signals(html)["script_src"] == []

    def test_link_without_stylesheet_rel_is_ignored(self):
        html = '<link rel="icon" href="/favicon.ico">'
        assert extract_html_signals(html)["stylesheet_href"] == []


class TestBuildEvidenceFromParts:
    def test_normalizes_header_keys_and_values_to_lowercase(self):
        evidence = build_evidence_from_parts({"Server": "NGINX/1.18"}, "<html></html>")
        assert evidence["headers"] == {"server": "nginx/1.18"}

    def test_carries_status_code_through(self):
        evidence = build_evidence_from_parts({}, "<html></html>", status_code=404)
        assert evidence["status_code"] == 404

    def test_status_code_defaults_to_none(self):
        evidence = build_evidence_from_parts({}, "<html></html>")
        assert evidence["status_code"] is None


class TestMergeEvidence:
    def test_relative_http_url_and_absolute_browser_url_deduplicate(self):
        # Regression: without urljoin() normalization, "/app.js" (HTTP)
        # and "https://site.com/app.js" (browser) look like two different
        # scripts and wouldn't merge at all.
        http_evidence = build_evidence_from_parts({}, '<script src="/app.js"></script>')
        browser_evidence = {"html": "", "script_src": ["https://site.com/app.js"],
                             "stylesheet_href": [], "cookies": {}, "javascript_globals": []}

        merged = merge_evidence(http_evidence, browser_evidence, base_url="https://site.com/")

        assert merged["script_src"] == ["https://site.com/app.js"]

    def test_browser_only_scripts_are_added(self):
        http_evidence = build_evidence_from_parts({}, '<script src="/a.js"></script>')
        browser_evidence = {"html": "", "script_src": ["https://site.com/a.js", "https://site.com/b.js"],
                             "stylesheet_href": [], "cookies": {}, "javascript_globals": []}

        merged = merge_evidence(http_evidence, browser_evidence, base_url="https://site.com/")

        assert merged["script_src"] == ["https://site.com/a.js", "https://site.com/b.js"]

    def test_html_prefers_browser_when_present(self):
        http_evidence = build_evidence_from_parts({}, "<html>http version</html>")
        browser_evidence = {"html": "<html>browser version</html>", "script_src": [],
                             "stylesheet_href": [], "cookies": {}, "javascript_globals": []}

        merged = merge_evidence(http_evidence, browser_evidence, base_url="https://site.com/")

        assert merged["html"] == "<html>browser version</html>"

    def test_html_falls_back_to_http_when_browser_html_empty(self):
        http_evidence = build_evidence_from_parts({}, "<html>http version</html>")
        browser_evidence = {"html": "", "script_src": [], "stylesheet_href": [],
                             "cookies": {}, "javascript_globals": []}

        merged = merge_evidence(http_evidence, browser_evidence, base_url="https://site.com/")

        assert merged["html"] == "<html>http version</html>"

    def test_cookies_merge_with_browser_winning_on_collision(self):
        http_evidence = build_evidence_from_parts({}, "<html></html>", cookies={"a": "http", "b": "http"})
        browser_evidence = {"html": "", "script_src": [], "stylesheet_href": [],
                             "cookies": {"a": "browser", "c": "browser"}, "javascript_globals": []}

        merged = merge_evidence(http_evidence, browser_evidence, base_url="https://site.com/")

        assert merged["cookies"] == {"a": "browser", "b": "http", "c": "browser"}

    def test_javascript_globals_comes_from_browser_only(self):
        http_evidence = build_evidence_from_parts({}, "<html></html>")
        browser_evidence = {"html": "", "script_src": [], "stylesheet_href": [],
                             "cookies": {}, "javascript_globals": ["react", "datalayer"]}

        merged = merge_evidence(http_evidence, browser_evidence, base_url="https://site.com/")

        assert merged["javascript_globals"] == ["react", "datalayer"]

    def test_status_code_carries_through_from_http_evidence(self):
        http_evidence = build_evidence_from_parts({}, "<html></html>", status_code=200)
        browser_evidence = {"html": "", "script_src": [], "stylesheet_href": [],
                             "cookies": {}, "javascript_globals": []}

        merged = merge_evidence(http_evidence, browser_evidence, base_url="https://site.com/")

        assert merged["status_code"] == 200
