import requests
from bs4 import BeautifulSoup

# Same fix as url_discovery/fetcher.py's BROWSER_HEADERS -- some sites (we
# already saw this with realpython.com) reject requests that look like a
# bare script rather than a browser. Kept as its own local copy rather than
# imported from url_discovery: each feature package stays self-contained,
# so a change to one feature's HTTP behavior can't silently affect another.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _failed(url: str, error: str) -> dict:
    return {
        "status": "failed",
        "url": url,
        "title": None,
        "headings": [],
        "paragraphs": [],
        "error": error,
    }


def extract_content(url: str):
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if "text/html" not in content_type.lower():
            return _failed(url, f"Response is not HTML: {content_type or 'unknown content type'}")

        soup = BeautifulSoup(response.text, "html.parser")

        # aside alongside script/style/noscript/nav/footer -- sidebars,
        # related-post widgets, and similar boilerplate commonly live in
        # <aside>, and their <p> tags would otherwise get pulled in as if
        # they were real article content.
        for tag in soup(["script", "style", "noscript", "nav", "footer", "aside"]):
            tag.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else None

        article = soup.find("article")
        main = soup.find("main")

        if article:
            content_root = article
        elif main:
            content_root = main
        else:
            content_root = soup

        headings = [
            tag.get_text(" ", strip=True)
            for tag in content_root.find_all(["h1", "h2", "h3"])
            if tag.get_text(" ", strip=True)
        ]

        paragraphs = [
            tag.get_text(" ", strip=True)
            for tag in content_root.find_all("p")
            if tag.get_text(" ", strip=True)
        ]

        return {
            "status": "success",
            "url": url,
            "title": title,
            "headings": headings,
            "paragraphs": paragraphs,
            "error": None,
        }

    except requests.RequestException as exc:
        return _failed(url, str(exc))


if __name__ == "__main__":
    url = "https://www.smashingmagazine.com/2021/12/core-web-vitals-case-study-smashing-magazine/"

    result = extract_content(url)

    # Scraped article text can contain characters a Windows terminal's
    # default cp1252 console can't print (curly quotes, arrows, etc.) --
    # same issue hit with browser.py's demo output earlier in this project.
    safe = {
        key: (value.encode("ascii", "replace").decode() if isinstance(value, str) else value)
        for key, value in result.items()
    }
    safe["headings"] = [h.encode("ascii", "replace").decode() for h in result["headings"]]
    safe["paragraphs"] = [p.encode("ascii", "replace").decode() for p in result["paragraphs"]]

    print(safe)
