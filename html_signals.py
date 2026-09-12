# Structured HTML signal extraction, built on BeautifulSoup.
#
# Pulls out the pieces of a page that are more precise to fingerprint
# against than a raw text search: actual <script src="...">, <link
# rel="stylesheet" href="...">, and <meta> tags (name/property + content).

from bs4 import BeautifulSoup


def extract_html_signals(html: str):
    soup = BeautifulSoup(html, "html.parser")

    scripts = []
    stylesheets = []
    meta_tags = []

    for script in soup.find_all("script"):
        src = script.get("src")

        if src:
            scripts.append(src)

    for link in soup.find_all("link"):
        href = link.get("href")
        rel = link.get("rel", [])

        if href and "stylesheet" in rel:
            stylesheets.append(href)

    for meta in soup.find_all("meta"):
        meta_tags.append({
            "name": meta.get("name"),
            "property": meta.get("property"),
            "content": meta.get("content"),
        })

    return {
        "scripts": scripts,
        "stylesheets": stylesheets,
        "meta": meta_tags,
    }
