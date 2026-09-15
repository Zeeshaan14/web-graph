# Browser-side rendering for JS-heavy pages -- same job split as
# tech_detection/browser.py and url_discovery/browser.py: render a page,
# judge whether a page is worth rendering, but never decide WHEN to
# actually do it -- that's extract_content()'s call, made once per call
# the same way tech_detection's pipeline.py owns when Playwright launches.
#
# Unlike url_discovery (a crawl visits many pages, so browser.py there
# also has to manage a browser's LIFECYCLE across all of them),
# content_extraction only ever handles ONE URL per call -- there's no
# lifecycle to manage, so this is a single-shot launch/render/close, the
# same shape as tech_detection/browser.py.

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Same proxy and threshold tech_detection/fallback.py calibrated against
# real pages (and url_discovery/browser.py duplicates for the same
# reason): a bare SPA shell measures 0 visible text, example.com's real
# content measures 139. 80 sits between the two. Duplicated rather than
# imported -- each feature stays self-contained, same reasoning as
# BROWSER_HEADERS elsewhere in this file.
MIN_VISIBLE_TEXT_LENGTH = 80


def should_render_with_browser(html: str) -> bool:
    """True when the raw HTTP HTML looks like an unrendered app shell --
    little to no visible text is a proxy for "the real content only
    exists after JS runs." A pure function on a string -- no Playwright
    involved, so this is cheap to test without a browser."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    return len(soup.get_text(strip=True)) < MIN_VISIBLE_TEXT_LENGTH


def render_page_html(url: str) -> str:
    """Launches Chromium, renders one URL, returns its content, closes
    Chromium -- single-shot, since content_extraction only ever handles
    one URL per call and there's no reason to keep a browser alive
    between calls the way a multi-page crawl would."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            return page.content()
        finally:
            browser.close()
