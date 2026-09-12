# Regression suite for the fingerprint engine: locks in the exact
# scoring/confidence behavior for every technology, so a future fingerprint
# addition or engine refactor can't silently change an existing result.
# All offline — no network, no browser.

from tech_detection.engine import detect
from tech_detection.evidence import build_evidence_from_parts
from tech_detection.fingerprints import FINGERPRINTS


def run(headers=None, html="", cookies=None):
    context = build_evidence_from_parts(headers or {}, html, cookies)
    return detect(FINGERPRINTS, context)


def find(results, technology):
    return next((r for r in results if r["technology"] == technology), None)


class TestCloudflare:
    def test_strong_all_signals(self):
        match = find(run(headers={
            "server": "cloudflare", "cf-ray": "8a1b2c3d4e5f", "cf-cache-status": "HIT",
        }), "Cloudflare")
        assert match["confidence"] == "strong"
        assert match["confidence_score"] == 80
        assert match["browser_enrichable"] is False

    def test_server_header_alone_is_not_enough(self):
        assert find(run(headers={"server": "cloudflare"}), "Cloudflare") is None

    def test_no_signals(self):
        assert find(run(headers={"server": "nginx"}), "Cloudflare") is None

    def test_bot_management_cookie_alone_is_not_enough(self):
        assert find(run(cookies={"cf_clearance": "abc"}), "Cloudflare") is None

    def test_edge_header_plus_cookie_stacks(self):
        match = find(run(headers={"cf-ray": "abc"}, cookies={"cf_clearance": "abc"}), "Cloudflare")
        assert match["confidence_score"] == 80


class TestVercel:
    def test_strong(self):
        match = find(run(headers={
            "server": "vercel", "x-vercel-id": "cle1::abcde", "x-vercel-cache": "HIT",
        }), "Vercel")
        assert match["confidence"] == "strong"
        assert match["confidence_score"] == 90

    def test_server_header_alone_is_not_enough(self):
        assert find(run(headers={"server": "vercel"}), "Vercel") is None


class TestNextJs:
    def test_strong_headers_and_html(self):
        html = ('<script src="/_next/static/chunks/main.js"></script>'
                '<script id="__NEXT_DATA__">{}</script>')
        match = find(run(headers={"x-nextjs-prerender": "1"}, html=html), "Next.js")
        assert match["confidence"] == "strong"
        assert match["confidence_score"] == 100
        assert match["browser_enrichable"] is True

    def test_static_path_alone_is_detectable(self):
        # Regression: /_next/static/ used to require __NEXT_DATA__ too
        # (an "all" group), which caused false negatives on real sites
        # (lakshx.in has the static path but not __NEXT_DATA__). Fixed to
        # "any" — either marker alone should be "possible".
        html = '<script src="/_next/static/chunks/main.js"></script>'
        match = find(run(html=html), "Next.js")
        assert match["confidence"] == "possible"
        assert match["confidence_score"] == 40

    def test_static_path_must_be_a_real_script_src_not_just_anywhere_in_html(self):
        # Regression: this rule uses source "script_src" (parsed <script
        # src>), not a raw HTML substring search — a stray mention of the
        # path in text should NOT match.
        html = "<p>we use /_next/static/ style paths in our docs</p>"
        assert find(run(html=html), "Next.js") is None

    def test_no_signals(self):
        assert find(run(html="<html><body>hello</body></html>"), "Next.js") is None


class TestWordPress:
    def test_strong_both_html_markers(self):
        html = '<link href="/wp-content/x.css"><script src="/wp-includes/x.js"></script>'
        match = find(run(html=html), "WordPress")
        assert match["confidence"] == "strong"
        assert match["confidence_score"] == 80
        assert match["browser_enrichable"] is False

    def test_generator_meta_tag_alone(self):
        html = '<meta name="generator" content="WordPress 6.4.2">'
        match = find(run(html=html), "WordPress")
        assert match["confidence"] == "likely"
        assert match["confidence_score"] == 70

    def test_generator_meta_is_case_insensitive_via_html_extraction(self):
        # evidence.py's extract_html_signals already lowercases meta
        # content at extraction time, so this exercises the case-folding
        # end to end through the real HTML-parsing path.
        html = '<meta name="generator" content="WordPress 7.2-alpha">'
        assert find(run(html=html), "WordPress") is not None

    def test_evaluate_condition_itself_is_case_insensitive(self):
        # Regression, isolated at the layer it actually lives in:
        # evaluate_condition's contains/equals used to be case-sensitive.
        # evidence.py happens to lowercase meta content before engine.py
        # ever sees it, which would silently hide this bug coming back —
        # so this bypasses evidence.py entirely and feeds engine.py a
        # mixed-case value directly, the way it would see it if that
        # upstream normalization were ever removed or changed.
        from tech_detection.engine import evaluate_condition

        assert evaluate_condition("WordPress 7.2-alpha", "contains", "wordpress") is True
        assert evaluate_condition("WordPress", "equals", "wordpress") is True

    def test_generator_condition_requires_same_tag(self):
        # The "conditions" rule requires name==generator AND content
        # contains wordpress on the SAME tag — an unrelated tag named
        # "generator" with different content should not match.
        html = ('<meta name="generator" content="Hugo 0.1">'
                '<meta name="description" content="a wordpress fan blog">')
        assert find(run(html=html), "WordPress") is None

    def test_no_signals(self):
        assert find(run(html="<html><body>hello</body></html>"), "WordPress") is None


class TestReact:
    def test_data_reactroot_alone(self):
        match = find(run(html='<div data-reactroot=""></div>'), "React")
        assert match["confidence"] == "possible"
        assert match["confidence_score"] == 40
        assert match["browser_enrichable"] is True

    def test_no_signals_is_the_common_case(self):
        # React is honestly weak-to-invisible on most real, bundled
        # production sites — this asserts the ENGINE doesn't over-detect,
        # not that React should somehow always be found.
        assert find(run(html="<html><body>hello</body></html>"), "React") is None


class TestVue:
    def test_scoped_css_marker(self):
        match = find(run(html='<div data-v-7ba5bd90=""></div>'), "Vue")
        assert match["confidence"] == "likely"
        assert match["confidence_score"] == 60


class TestAngular:
    def test_ng_version_is_strong_alone(self):
        match = find(run(html='<app-root ng-version="17.0.2"></app-root>'), "Angular")
        assert match["confidence"] == "strong"
        assert match["confidence_score"] == 80


class TestShopify:
    def test_cdn_script_src(self):
        html = '<script src="https://cdn.shopify.com/s/files/1/theme.js"></script>'
        match = find(run(html=html), "Shopify")
        assert match["confidence"] == "likely"
        assert match["confidence_score"] == 70
        assert match["browser_enrichable"] is True


class TestServers:
    def test_nginx_possible_alone(self):
        match = find(run(headers={"server": "nginx/1.18.0"}), "nginx")
        assert match["confidence"] == "possible"
        assert match["confidence_score"] == 50
        assert match["browser_enrichable"] is False

    def test_apache_possible_alone(self):
        match = find(run(headers={"server": "Apache/2.4.41 (Ubuntu)"}), "Apache")
        assert match["confidence"] == "possible"
        assert match["confidence_score"] == 50
        assert match["browser_enrichable"] is False


class TestAnalytics:
    def test_gtm_script_in_html(self):
        html = '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-XXXX"></script>'
        match = find(run(html=html), "Google Tag Manager / Google Analytics")
        assert match["confidence"] == "likely"
        assert match["confidence_score"] == 60
        assert match["browser_enrichable"] is True


class TestJavascriptGlobalsSource:
    """javascript_globals only ever exists after a browser pass — these
    confirm the engine evaluates it correctly when present, and that its
    absence from plain HTTP evidence never crashes anything."""

    def test_react_global_detected_when_present(self):
        context = build_evidence_from_parts({}, "<html></html>")
        context["javascript_globals"] = ["react"]
        match = find(detect(FINGERPRINTS, context), "React")
        assert match["confidence_score"] == 40

    def test_absent_javascript_globals_key_does_not_crash(self):
        # Plain HTTP evidence (build_evidence_from_parts) never sets this
        # key at all -- engine.py must default it to [], not KeyError.
        context = build_evidence_from_parts({}, "<html></html>")
        assert "javascript_globals" not in context
        assert detect(FINGERPRINTS, context) == []


class TestBrowserEnrichableMetadata:
    """Every fingerprint must declare browser_enrichable -- this is what
    fallback.py uses to avoid launching Chromium for server-side tech
    (nginx/Apache) that a browser pass can never improve."""

    EXPECTED = {
        "Cloudflare": False,
        "Vercel": False,
        "Next.js": True,
        "WordPress": False,
        "React": True,
        "Vue": True,
        "Angular": True,
        "Shopify": True,
        "nginx": False,
        "Apache": False,
        "Google Tag Manager / Google Analytics": True,
    }

    def test_every_known_fingerprint_has_the_expected_flag(self):
        by_name = {fp["technology"]: fp for fp in FINGERPRINTS}

        for technology, expected in self.EXPECTED.items():
            assert technology in by_name, f"{technology} fingerprint missing entirely"
            assert by_name[technology]["browser_enrichable"] == expected, technology

    def test_no_fingerprint_is_missing_the_field(self):
        for fp in FINGERPRINTS:
            assert "browser_enrichable" in fp, f"{fp['technology']} has no browser_enrichable flag"
