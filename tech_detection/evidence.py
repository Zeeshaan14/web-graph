# Owns HTML parsing and evidence-object construction. Takes fetched
# response/session data (or hand-built parts, for offline tests) and turns
# it into the flat evidence dict engine.py evaluates fingerprints against:
#
#   {headers, cookies, html, script_src, stylesheet_href, meta}
#
# engine.py never parses HTML or touches requests/BeautifulSoup itself —
# it only ever sees this already-normalized shape, regardless of whether
# it came from a plain HTTP fetch or (later) a browser-enriched one.

from urllib.parse import urljoin

from bs4 import BeautifulSoup


def normalize(value):
    if isinstance(value, str):
        return value.strip().lower()

    return value


def extract_html_signals(html: str):
    soup = BeautifulSoup(html, "html.parser")

    scripts = []
    stylesheets = []
    meta = []

    for script in soup.find_all("script"):
        src = script.get("src")

        if src:
            scripts.append(normalize(src))

    for link in soup.find_all("link"):
        href = link.get("href")
        rel = link.get("rel", [])

        if href and "stylesheet" in rel:
            stylesheets.append(normalize(href))

    for tag in soup.find_all("meta"):
        meta.append({
            "name": normalize(tag.get("name")),
            "property": normalize(tag.get("property")),
            "content": normalize(tag.get("content")),
        })

    return {
        "script_src": scripts,
        "stylesheet_href": stylesheets,
        "meta": meta,
    }


def build_evidence_from_parts(headers, html, cookies=None, status_code=None):
    html_signals = extract_html_signals(html)

    return {
        "headers": {
            key.lower(): value.lower()
            for key, value in headers.items()
        },
        "cookies": {
            key.lower(): value
            for key, value in (cookies or {}).items()
        },
        "html": html.lower(),
        "status_code": status_code,
        **html_signals,
    }


def build_evidence(response, session):
    return build_evidence_from_parts(
        headers=response.headers,
        html=response.text,
        cookies=session.cookies.get_dict(),
        status_code=response.status_code,
    )


def _normalize_urls(urls, base_url):
    """Resolves each URL against base_url so a relative HTTP-side path
    ("/app.js") and an absolute browser-side one ("https://site/app.js")
    become the exact same string and can be deduplicated correctly."""
    return {urljoin(base_url, url).lower() for url in urls}


def merge_evidence(http_evidence, browser_evidence, base_url):
    """Combines HTTP evidence with browser evidence into one evidence dict
    of the same shape engine.py already expects — merging is still just
    evidence construction, so the engine doesn't need to know two sources
    were involved at all.

    Field-by-field merge rules:
      headers            -> HTTP only (a browser doesn't expose these)
      html               -> prefer browser (fully rendered, post-JS)
      cookies            -> both, browser wins on a name collision
                            (it reflects the final, JS-set cookie jar)
      script_src         -> union of both, deduplicated after resolving
                            relative HTTP paths against base_url
      stylesheet_href     -> same as script_src
      meta               -> HTTP only for now (browser.py doesn't collect
                            meta tags yet)
      javascript_globals -> browser only (HTTP has no concept of this)
    """
    merged_scripts = _normalize_urls(http_evidence.get("script_src", []), base_url) \
        | _normalize_urls(browser_evidence.get("script_src", []), base_url)

    merged_stylesheets = _normalize_urls(http_evidence.get("stylesheet_href", []), base_url) \
        | _normalize_urls(browser_evidence.get("stylesheet_href", []), base_url)

    return {
        "headers": http_evidence.get("headers", {}),
        "status_code": http_evidence.get("status_code"),
        "html": browser_evidence.get("html") or http_evidence.get("html", ""),
        "cookies": {
            **http_evidence.get("cookies", {}),
            **browser_evidence.get("cookies", {}),
        },
        "script_src": sorted(merged_scripts),
        "stylesheet_href": sorted(merged_stylesheets),
        "meta": http_evidence.get("meta", []),
        "javascript_globals": browser_evidence.get("javascript_globals", []),
    }
