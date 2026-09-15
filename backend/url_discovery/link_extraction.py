from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, parse_qsl, urlencode

# Known tracking params to strip so ?utm_source=twitter and ?utm_source=fb
# don't make the same page look like two different URLs to discover.
# Case-insensitive match against the param NAME only (not the value).
TRACKING_PARAMS = {
    # UTM campaign tracking
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    # ad-platform click IDs
    "gclid", "fbclid", "msclkid", "dclid", "yclid", "twclid",
    # misc referral/email tracking
    "igshid", "mc_cid", "mc_eid", "ref", "ref_src",
}

def normalize_url(url: str, path_specific_strip: dict[str, set[str]] | None = None) -> str:
    """path_specific_strip lets a CALLER supply extra query params to
    strip on specific paths -- e.g. a site-specific noisy param like
    realpython.com's /feedback/realpython-com/?d=<per-page-token>. This
    stays generic on purpose: no site's quirks are hardcoded in here, so
    the same function works unmodified for any site being crawled.
    Format: {"/exact/path/": {"param_name", ...}}."""
    parsed = urlsplit(url)

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port

    if port is None:
        netloc = hostname
    elif scheme == "http" and port == 80:
        netloc = hostname
    elif scheme == "https" and port == 443:
        netloc = hostname
    else:
        netloc = f"{hostname}:{port}"

    extra_strip = (path_specific_strip or {}).get(parsed.path, set())
    strip_params = TRACKING_PARAMS | extra_strip

    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    clean_params = [
        (key, value)
        for key, value in query_params
        if key.lower() not in strip_params
    ]
    clean_query = urlencode(clean_params)

    return urlunsplit(
        (
            scheme,
            netloc,
            parsed.path,
            clean_query,
            "",  # remove fragment
        )
    )


def extract_links(
    html: str,
    base_url: str,
    path_specific_strip: dict[str, set[str]] | None = None,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    normalized_base = normalize_url(base_url, path_specific_strip)
    base_domain = urlparse(normalized_base).netloc

    links = []
    seen = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"]

        absolute_url = urljoin(base_url, href)
        clean_url = normalize_url(absolute_url, path_specific_strip)

        parsed = urlparse(clean_url)

        # Ignore external domains
        if parsed.netloc != base_domain:
            continue

        # Ignore duplicate URLs
        if clean_url in seen:
            continue

        seen.add(clean_url)
        links.append(clean_url)

    return links


def extract_canonical(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    tag = soup.find("link", rel=lambda value: value and "canonical" in value)

    if not tag or not tag.get("href"):
        return None

    return urljoin(base_url, tag["href"])


def _demo():
    test_urls = [
        # only tracking params -> query should disappear entirely
        "https://example.com/page?utm_source=twitter&utm_medium=social",
        # real param + tracking params mixed -> keep only the real one
        "https://example.com/search?q=shoes&utm_campaign=summer&gclid=abc123",
        # ad-click-id only, no utm params
        "https://example.com/product?id=42&fbclid=xyz789",
        # no query at all -> unchanged
        "https://example.com/about",
        # tracking param + fragment together -> both stripped
        "https://example.com/page?utm_source=fb#section",
        # mixed-case tracking key -> still stripped (case-insensitive match)
        "https://example.com/page?UTM_Source=newsletter&Ref=abc",
        # non-tracking param that just looks similar -> must NOT be stripped
        "https://example.com/page?category=utm_source",
    ]

    print("normalize_url() tracking-param stripping:")
    for url in test_urls:
        print(f"  {url}")
        print(f"  -> {normalize_url(url)}")
        print()

    html = """
    <html>
        <body>
            <a href="/about">About</a>
            <a href="https://example.com/contact">Contact</a>
            <a href="../blog">Blog</a>
            <a href="#pricing">Pricing</a>
            <a href="https://google.com">Google</a>

            <a href="/about">About</a>
            <a href="/about">About again</a>
            <a href="/about#team">About team</a>
            <a href="/pricing?utm_source=twitter&utm_medium=social">Pricing (via twitter)</a>
            <a href="/pricing?utm_source=newsletter">Pricing (via newsletter)</a>
        </body>
    </html>
    """

    print("extract_links():")
    links = extract_links(html, "https://example.com/company/team")

    for link in links:
        print(f"  {link}")


if __name__ == "__main__":
    _demo()