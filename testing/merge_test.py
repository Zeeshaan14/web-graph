# Proves HTTP evidence + browser evidence can merge into one clean
# evidence object with no duplicate script/stylesheet URLs, even though
# HTTP gives relative paths and the browser gives absolute ones.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetcher import fetch_url
from evidence import build_evidence, merge_evidence
from browser import collect_browser_evidence

URL = "https://lakshx.in/"


def main():
    response, session = fetch_url(URL)
    http_evidence = build_evidence(response, session)

    browser_evidence = collect_browser_evidence(URL)

    merged = merge_evidence(http_evidence, browser_evidence, base_url=response.url)

    print(f"HTTP scripts: {len(http_evidence['script_src'])}")
    print(f"Browser scripts: {len(browser_evidence['script_src'])}")
    print(f"Merged scripts: {len(merged['script_src'])}")
    print()
    print(f"HTTP stylesheets: {len(http_evidence['stylesheet_href'])}")
    print(f"Browser stylesheets: {len(browser_evidence['stylesheet_href'])}")
    print(f"Merged stylesheets: {len(merged['stylesheet_href'])}")
    print()
    print(f"HTTP cookies: {len(http_evidence['cookies'])}")
    print(f"Browser cookies: {len(browser_evidence['cookies'])}")
    print(f"Merged cookies: {len(merged['cookies'])}")
    print()
    print("javascript_globals:", merged["javascript_globals"])


if __name__ == "__main__":
    main()
