# Regression suite for link_extraction.py: URL normalization, link
# discovery, and canonical-tag extraction. Fully offline.

from url_discovery.link_extraction import extract_canonical, extract_links, normalize_url


class TestNormalizeUrl:
    def test_strips_default_http_port(self):
        assert normalize_url("http://example.com:80/path") == "http://example.com/path"

    def test_strips_default_https_port(self):
        assert normalize_url("https://example.com:443/path") == "https://example.com/path"

    def test_keeps_non_default_port(self):
        assert normalize_url("http://example.com:8080/path") == "http://example.com:8080/path"

    def test_lowercases_scheme_and_host_but_not_path(self):
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_removes_fragment(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_tracking_params(self):
        url = "https://example.com/page?utm_source=x&utm_medium=y"
        assert normalize_url(url) == "https://example.com/page"

    def test_keeps_non_tracking_params(self):
        url = "https://example.com/search?q=shoes&utm_campaign=summer"
        assert normalize_url(url) == "https://example.com/search?q=shoes"

    def test_tracking_param_match_is_case_insensitive(self):
        assert normalize_url("https://example.com/page?UTM_Source=x") == "https://example.com/page"

    def test_lookalike_param_value_not_stripped(self):
        # A param NAMED "category" whose VALUE happens to be "utm_source"
        # must survive -- matching is on the key, never the value.
        url = "https://example.com/page?category=utm_source"
        assert normalize_url(url) == url

    def test_no_query_unchanged(self):
        assert normalize_url("https://example.com/about") == "https://example.com/about"

    def test_defaults_to_no_path_specific_rules(self):
        # Without an explicit path_specific_strip, normalize_url must
        # stay fully generic -- no site's quirks hardcoded in.
        url = "https://realpython.com/feedback/realpython-com/?d=AAA"
        assert normalize_url(url) == url

    def test_path_specific_strip_only_applies_to_matching_path(self):
        rules = {"/feedback/x/": {"d"}}
        assert normalize_url("https://example.com/feedback/x/?d=AAA", rules) == "https://example.com/feedback/x/"
        # A DIFFERENT path with the same param name is untouched.
        other = "https://example.com/other/?d=AAA"
        assert normalize_url(other, rules) == other

    def test_path_specific_strip_keeps_other_params_on_same_path(self):
        rules = {"/feedback/x/": {"d"}}
        url = "https://example.com/feedback/x/?d=AAA&lang=en"
        assert normalize_url(url, rules) == "https://example.com/feedback/x/?lang=en"

    def test_two_different_tokens_on_stripped_path_collapse_to_same_url(self):
        rules = {"/feedback/x/": {"d"}}
        a = normalize_url("https://example.com/feedback/x/?d=AAA", rules)
        b = normalize_url("https://example.com/feedback/x/?d=BBB", rules)
        assert a == b


class TestExtractLinks:
    def test_resolves_relative_links(self):
        html = '<a href="/about">About</a>'
        assert extract_links(html, "https://example.com/") == ["https://example.com/about"]

    def test_resolves_dotdot_relative_links(self):
        html = '<a href="../blog">Blog</a>'
        assert extract_links(html, "https://example.com/company/team") == ["https://example.com/blog"]

    def test_filters_external_domains(self):
        html = '<a href="https://other.com/page">Other</a>'
        assert extract_links(html, "https://example.com/") == []

    def test_dedupes_within_the_same_page(self):
        html = '<a href="/a">1</a><a href="/a">2</a><a href="/a#frag">3</a>'
        assert extract_links(html, "https://example.com/") == ["https://example.com/a"]

    def test_ignores_links_without_href(self):
        html = "<a>No href</a>"
        assert extract_links(html, "https://example.com/") == []

    def test_path_specific_strip_collapses_discovered_link_variants(self):
        rules = {"/feedback/x/": {"d"}}
        html = '<a href="/feedback/x/?d=AAA">FB1</a><a href="/feedback/x/?d=BBB">FB2</a>'
        assert extract_links(html, "https://example.com/", rules) == ["https://example.com/feedback/x/"]


class TestExtractCanonical:
    def test_finds_canonical_link(self):
        html = '<link rel="canonical" href="/tutorial/index.html">'
        result = extract_canonical(html, "https://example.com/tutorial/")
        assert result == "https://example.com/tutorial/index.html"

    def test_resolves_relative_canonical_against_base_url(self):
        html = '<link rel="canonical" href="index.html">'
        result = extract_canonical(html, "https://example.com/tutorial/")
        assert result == "https://example.com/tutorial/index.html"

    def test_returns_none_when_no_canonical_tag(self):
        assert extract_canonical("<html></html>", "https://example.com/") is None

    def test_returns_none_when_href_missing(self):
        assert extract_canonical('<link rel="canonical">', "https://example.com/") is None
