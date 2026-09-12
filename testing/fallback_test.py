# Tests should_use_browser() against: two real, HTTP-sufficient sites
# (expect False) and one synthetic SPA shell with no real HTTP evidence
# (expect True).

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetcher import fetch_url
from evidence import build_evidence, build_evidence_from_parts
from engine import detect_technologies
from fallback import should_use_browser

FAKE_SPA_HTML = '<div id="root"></div><script src="/app.js"></script>'


def check_real_url(url):
    response, session = fetch_url(url)
    evidence = build_evidence(response, session)
    technologies = detect_technologies(evidence)

    print(f"{url}")
    print(f"  technologies: {[(t['technology'], t['confidence']) for t in technologies]}")
    print(f"  should_use_browser: {should_use_browser(evidence, technologies)}")


def check_fake_spa():
    evidence = build_evidence_from_parts(headers={}, html=FAKE_SPA_HTML)
    technologies = detect_technologies(evidence)

    print("fake SPA shell")
    print(f"  technologies: {[(t['technology'], t['confidence']) for t in technologies]}")
    print(f"  should_use_browser: {should_use_browser(evidence, technologies)}")


if __name__ == "__main__":
    check_real_url("https://example.com")
    print()
    check_real_url("https://lakshx.in/")
    print()
    check_fake_spa()
