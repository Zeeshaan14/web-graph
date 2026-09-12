# Decides whether the cheap HTTP evidence is good enough, or whether it's
# worth paying for a full Playwright browser launch. Looks only at what
# the HTTP pass already produced (the evidence dict and detect_technologies()
# output) — it doesn't fetch anything and doesn't know how to collect
# browser evidence itself, so it stays swappable/testable on its own.

from bs4 import BeautifulSoup

# Calibrated against real pages, not guessed: example.com's actual page
# text is 139 chars (a couple of sentences — genuinely sparse, but real
# content) and a bare SPA shell (<div id="root"></div> + a script tag)
# measures 0. 80 sits comfortably between the two.
MIN_VISIBLE_TEXT_LENGTH = 80


def _visible_text_length(html):
    """Text a human would actually see — <script>/<style> bodies don't
    count, since inline JS/CSS can be long without being visible content
    (which would otherwise make an empty SPA shell look "full" of text)."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    return len(soup.get_text(strip=True))


def should_use_browser(evidence, technologies):
    # No detections at all: HTTP evidence told us nothing — worth a
    # browser pass in case the real signals are client-rendered.
    if not technologies:
        return True

    # Every detection is only "possible": HTTP evidence is present but
    # thin/ambiguous everywhere, not confidently confirming anything.
    if all(tech["confidence"] == "possible" for tech in technologies):
        return True

    # Very little visible text is a proxy for "this HTML is mostly an
    # unrendered app shell" (e.g. <div id="root"></div> + a script tag) —
    # the real evidence likely only exists after JS runs.
    if _visible_text_length(evidence.get("html", "")) < MIN_VISIBLE_TEXT_LENGTH:
        return True

    return False
