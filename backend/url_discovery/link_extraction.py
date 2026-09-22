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

def normalize_url(
    url: str,
    path_specific_strip: dict[str, set[str]] | None = None,
    ignore_query_parameters: bool = False,
) -> str:
    """path_specific_strip lets a CALLER supply extra query params to
    strip on specific paths -- e.g. a site-specific noisy param like
    realpython.com's /feedback/realpython-com/?d=<per-page-token>. This
    stays generic on purpose: no site's quirks are hardcoded in here, so
    the same function works unmodified for any site being crawled.
    Format: {"/exact/path/": {"param_name", ...}}.

    ignore_query_parameters drops the ENTIRE query string unconditionally
    -- a blanket "two URLs differing only in query params are the same
    page" for a caller who knows that's true site-wide (e.g. every query
    param is a session/sort/filter token, not a distinct resource).
    path_specific_strip stays useful even when this is on, for stripping
    params from a path this doesn't fully collapse -- but in practice
    it's redundant with ignore_query_parameters=True, since that already
    drops everything."""
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

    if ignore_query_parameters:
        clean_query = ""
    else:
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


def is_same_site(netloc_a: str, netloc_b: str, allow_subdomains: bool = False) -> bool:
    """True if two already-normalized (lowercased) netlocs count as the
    same site for crawl-scope purposes. A leading "www." is treated as a
    cosmetic alias -- www.example.com and example.com are the same site --
    but no other subdomain difference is collapsed by default:
    blog.example.com and example.com are genuinely different
    sections/systems as often as they are the same site, and a generic
    crawler assuming otherwise would silently widen its own scope in a way
    a caller can't opt out of.

    allow_subdomains widens that on purpose, for a caller who DOES want
    blog.example.com, docs.example.com, etc. treated as one site: true if
    either netloc (after stripping a leading "www.") is the other, or is a
    subdomain of it. A naive endswith(".root") check, not real public-
    suffix-list parsing -- same level of pragmatism as the www-alias
    check above, not an attempt to correctly handle every multi-part TLD
    (co.uk, etc.)."""

    def _strip_www(netloc: str) -> str:
        return netloc[4:] if netloc.startswith("www.") else netloc

    root_a = _strip_www(netloc_a)
    root_b = _strip_www(netloc_b)

    if root_a == root_b:
        return True

    if not allow_subdomains:
        return False

    return root_a.endswith(f".{root_b}") or root_b.endswith(f".{root_a}")


def extract_links(
    html: str,
    base_url: str,
    path_specific_strip: dict[str, set[str]] | None = None,
    ignore_query_parameters: bool = False,
    allow_subdomains: bool = False,
    include_external: bool = False,
) -> tuple[list[str], list[str]]:
    """Returns (same_site_links, external_links) -- external_links is
    always [] unless include_external=True. Kept as two separate lists
    rather than one list with a per-item flag: the crawler treats the two
    categories completely differently (normal traversal vs. a one-hop,
    never-expanded record), so the caller would immediately split them
    apart anyway."""
    soup = BeautifulSoup(html, "html.parser")

    normalized_base = normalize_url(base_url, path_specific_strip, ignore_query_parameters)
    base_domain = urlparse(normalized_base).netloc

    same_site_links = []
    external_links = []
    seen = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"]

        absolute_url = urljoin(base_url, href)
        clean_url = normalize_url(absolute_url, path_specific_strip, ignore_query_parameters)

        parsed = urlparse(clean_url)

        # Ignore duplicate URLs
        if clean_url in seen:
            continue

        if is_same_site(parsed.netloc, base_domain, allow_subdomains):
            seen.add(clean_url)
            same_site_links.append(clean_url)
        elif include_external:
            seen.add(clean_url)
            external_links.append(clean_url)

    return same_site_links, external_links


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
    same_site_links, _ = extract_links(html, "https://example.com/company/team")

    for link in same_site_links:
        print(f"  {link}")


if __name__ == "__main__":
    _demo()