# Regression suite for fallback.should_use_browser(). All synthetic —
# real-site behavior for this logic is covered separately under
# tests/network/ (marked, not run by default).

from tech_detection.evidence import build_evidence_from_parts
from tech_detection.engine import detect_technologies
from tech_detection.fallback import should_use_browser


def evidence_and_technologies(headers=None, html="", status_code=200):
    evidence = build_evidence_from_parts(headers or {}, html, status_code=status_code)
    return evidence, detect_technologies(evidence)


REAL_PAGE_TEXT = (
    "<p>This is a real page with enough visible prose that the "
    "visible-text-length check does not itself trigger a browser pass, "
    "so each test below is isolated to the condition it actually probes.</p>"
)


class TestErrorStatusSkipsBrowser:
    """Regression: an error response (4xx/5xx) already explains itself —
    a browser pass can't improve it and just wastes Chromium."""

    def test_404_never_triggers_browser_even_with_zero_detections(self):
        evidence, technologies = evidence_and_technologies(status_code=404)
        assert technologies == []
        assert should_use_browser(evidence, technologies) is False

    def test_500_never_triggers_browser(self):
        evidence, technologies = evidence_and_technologies(
            headers={"cf-ray": "abc"}, html=REAL_PAGE_TEXT, status_code=500,
        )
        assert should_use_browser(evidence, technologies) is False

    def test_200_with_no_detections_still_triggers_browser(self):
        # Confirms the 400+ check doesn't accidentally suppress the
        # legitimate "no technologies detected" trigger for a normal 200.
        evidence, technologies = evidence_and_technologies(status_code=200, html="")
        assert technologies == []
        assert should_use_browser(evidence, technologies) is True


class TestPossibleConfidenceGatedByBrowserEnrichable:
    """Regression: nginx/Apache landing on "possible" used to always
    trigger a browser launch that could never actually help them."""

    def test_nginx_possible_alone_does_not_trigger_browser(self):
        evidence, technologies = evidence_and_technologies(
            headers={"server": "nginx/1.18.0"}, html=REAL_PAGE_TEXT,
        )
        assert [t["confidence"] for t in technologies] == ["possible"]
        assert should_use_browser(evidence, technologies) is False

    def test_apache_possible_alone_does_not_trigger_browser(self):
        evidence, technologies = evidence_and_technologies(
            headers={"server": "Apache/2.4.41"}, html=REAL_PAGE_TEXT,
        )
        assert should_use_browser(evidence, technologies) is False

    def test_react_possible_alone_does_trigger_browser(self):
        # React IS browser_enrichable, so the same "all possible" shape
        # that skips nginx/Apache must still fire here.
        evidence, technologies = evidence_and_technologies(
            html='<div data-reactroot="">' + REAL_PAGE_TEXT + "</div>",
        )
        assert [t["confidence"] for t in technologies] == ["possible"]
        assert should_use_browser(evidence, technologies) is True


class TestNoDetections:
    def test_empty_page_triggers_browser(self):
        evidence, technologies = evidence_and_technologies(html="")
        assert should_use_browser(evidence, technologies) is True


class TestLittleVisibleText:
    def test_fake_spa_shell_triggers_browser(self):
        evidence, technologies = evidence_and_technologies(
            html='<div id="root"></div><script src="/app.js"></script>',
        )
        assert technologies == []
        assert should_use_browser(evidence, technologies) is True

    def test_strong_detection_with_sparse_real_content_does_not(self):
        # Regression: example.com's real page text is only 139 chars —
        # genuinely sparse but real. A strong direct detection (Cloudflare
        # headers) must short-circuit before the text-length check would
        # otherwise flag this page as "shell-like".
        evidence, technologies = evidence_and_technologies(
            headers={"cf-ray": "abc", "cf-cache-status": "HIT", "server": "cloudflare"},
            html=("<html><body>Example Domain. This domain is for use in illustrative "
                  "examples in documents. You may use this domain in literature without "
                  "prior coordination or asking for permission.</body></html>"),
        )
        assert technologies[0]["confidence"] == "strong"
        assert should_use_browser(evidence, technologies) is False
