# Browser-side rendering for JS-heavy pages -- same split tech_detection
# draws between browser.py (collect) and fallback.py (decide): this file
# renders a page and judges whether a page is worth rendering, but never
# decides WHEN to actually do it or how many times per crawl -- that
# lifecycle (launching Chromium once and reusing it, capping how many
# renders one crawl gets) belongs to crawler.py, the same way tech_detection's
# pipeline.py -- not browser.py -- owns when Playwright gets launched.

from bs4 import BeautifulSoup
from playwright.sync_api import Browser

# Same proxy and threshold tech_detection/fallback.py already calibrated
# against real pages: a bare SPA shell (<div id="root"></div> + a script
# tag) measures 0 visible text, example.com's real (if sparse) content
# measures 139. 80 sits between the two. Duplicated rather than imported --
# each feature stays self-contained, same reasoning as BROWSER_HEADERS
# elsewhere in this repo.
MIN_VISIBLE_TEXT_LENGTH = 80


def should_render_with_browser(html: str) -> bool:
    """True when the raw HTTP HTML looks like an unrendered app shell --
    little to no visible text is a proxy for "the real content, and any
    real navigation links, only exist after JS runs." A pure function on
    a string -- no Playwright involved, so this is cheap to call on every
    page and cheap to test without a browser."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    return len(soup.get_text(strip=True)) < MIN_VISIBLE_TEXT_LENGTH


def render_page_html(browser: Browser, url: str) -> str:
    """Renders one URL using an already-running browser instance -- the
    caller owns the browser's lifecycle (launched once, reused across
    every page in a crawl that needs rendering, rather than paying
    Chromium startup cost per page). Its own context is opened and closed
    per call so pages don't share cookies/storage with each other."""
    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(url, wait_until="networkidle", timeout=30_000)
        return page.content()
    finally:
        context.close()
