# Real end-to-end checks against actual sites and a real Chromium launch.
# NOT run by default (pytest.ini's addopts excludes -m network) -- run
# explicitly with: uv run pytest -m network
#
# These exist to catch drift the offline suite can't: a real site changing
# its headers/HTML, or Playwright itself breaking. The offline suite in
# tests/ is what should catch logic regressions day to day.

import pytest

from tech_detection.pipeline import detect_website_technologies

pytestmark = pytest.mark.network


def technology_names(result):
    return {t["technology"] for t in result["technologies"]}


def test_example_com_detects_cloudflare_via_http_only():
    result = detect_website_technologies("https://example.com")

    assert result["status"] == "success"
    assert result["evidence_source"] == "http"
    assert "Cloudflare" in technology_names(result)


def test_lakshx_in_detects_vercel_nextjs_and_infers_react():
    result = detect_website_technologies("https://lakshx.in/")

    assert result["status"] == "success"
    names = technology_names(result)
    assert "Vercel" in names
    assert "Next.js" in names
    assert "React" in names

    react = next(t for t in result["technologies"] if t["technology"] == "React")
    assert react["detection_type"] == "inferred"


def test_wordpress_org_detects_wordpress():
    result = detect_website_technologies("https://wordpress.org")

    assert result["status"] == "success"
    assert "WordPress" in technology_names(result)


def test_nginx_org_does_not_launch_browser_for_a_lone_possible_detection():
    result = detect_website_technologies("https://nginx.org")

    assert result["status"] == "success"
    assert result["evidence_source"] == "http"


def test_invalid_domain_returns_failed_not_an_exception():
    result = detect_website_technologies("https://this-domain-should-not-exist-xyz-12345.com")

    assert result["status"] == "failed"
    assert result["errors"][0]["type"] == "connection_error"
