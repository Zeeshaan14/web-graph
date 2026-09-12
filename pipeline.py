# Orchestrates the whole two-stage flow: cheap HTTP evidence first, then
# a Playwright browser pass only if fallback.should_use_browser() says the
# HTTP evidence wasn't enough. Every piece here (fetching, evidence
# construction, detection, the fallback decision, browser collection) was
# already built and tested standalone — this file just wires them together
# in order.

from fetcher import fetch_url
from evidence import build_evidence, merge_evidence
from engine import detect_technologies
from fallback import should_use_browser
from browser import collect_browser_evidence


def detect_website_technologies(url: str):
    # 1. Cheap HTTP path first
    response, session = fetch_url(url)

    http_evidence = build_evidence(
        response,
        session,
    )

    http_technologies = detect_technologies(
        http_evidence
    )

    # 2. Decide whether Chromium is worth launching
    if not should_use_browser(
        http_evidence,
        http_technologies,
    ):
        return {
            "url": response.url,
            "technologies": http_technologies,
            "evidence_source": "http",
        }

    # 3. Browser enrichment
    browser_evidence = collect_browser_evidence(
        response.url
    )

    merged_evidence = merge_evidence(
        http_evidence,
        browser_evidence,
        base_url=response.url,
    )

    final_technologies = detect_technologies(
        merged_evidence
    )

    return {
        "url": response.url,
        "technologies": final_technologies,
        "evidence_source": "http+browser",
    }
