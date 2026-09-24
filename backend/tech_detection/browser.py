# Browser-side evidence collector. Same job as evidence.py's HTTP path —
# produce evidence, don't detect anything — just backed by a real rendered
# page instead of a raw HTTP response. Deliberately not wired into main.py
# yet; this is standalone until fallback.py decides when to call it.

from playwright.sync_api import sync_playwright

from security.ssrf_guard import assert_safe_url, install_navigation_guard


def collect_browser_evidence(url: str):
    # Validated up front (fails before Chromium ever launches) and again
    # on every navigation the page makes (catches a redirect DURING
    # rendering) -- see security.ssrf_guard. pipeline.py's own try/except
    # around this call already falls back to the HTTP-only result on any
    # browser failure, so either one failing needs no caller-side change.
    assert_safe_url(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        install_navigation_guard(page)

        try:
            page.goto(
                url,
                wait_until="networkidle",
                timeout=30_000,
            )

            rendered_html = page.content()

            runtime_scripts = page.locator(
                "script[src]"
            ).evaluate_all(
                "(elements) => elements.map(el => el.src)"
            )

            runtime_stylesheets = page.locator(
                'link[rel="stylesheet"][href]'
            ).evaluate_all(
                "(elements) => elements.map(el => el.href)"
            )

            cookies = {
                item["name"].lower(): item["value"]
                for item in context.cookies()
            }

            globals_to_check = [
                "__NEXT_DATA__",
                "__NUXT__",
                "React",
                "Vue",
                "jQuery",
                "$",
                "Shopify",
                "dataLayer",
                "gtag",
            ]

            javascript_globals = []

            for name in globals_to_check:
                exists = page.evaluate(
                    "(name) => typeof window[name] !== 'undefined'",
                    name,
                )

                if exists:
                    javascript_globals.append(name.lower())

            return {
                "html": rendered_html.lower(),
                "script_src": [
                    src.lower()
                    for src in runtime_scripts
                ],
                "stylesheet_href": [
                    href.lower()
                    for href in runtime_stylesheets
                ],
                "cookies": cookies,
                "javascript_globals": javascript_globals,
            }

        finally:
            browser.close()


if __name__ == "__main__":
    evidence = collect_browser_evidence("https://lakshx.in/")

    print("Key counts:")
    for key, value in evidence.items():
        if isinstance(value, (list, dict)):
            print(f"  {key}: {len(value)}")
        else:
            print(f"  {key}: {len(value)} chars")

    print()
    print("script_src:", evidence["script_src"])
    print()
    print("stylesheet_href:", evidence["stylesheet_href"])
    print()
    print("cookies:", evidence["cookies"])
    print()
    print("javascript_globals:", evidence["javascript_globals"])
    print()
    print("html preview:", evidence["html"][:300].encode("ascii", "replace").decode())
