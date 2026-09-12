from playwright.sync_api import sync_playwright


def inspect_browser(url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(
                url,
                wait_until="networkidle",
                timeout=30_000,
            )

            print("=" * 70)
            print("Final URL:", page.url)

            # ---------------------------------------------------------
            # 1. Rendered HTML
            # ---------------------------------------------------------

            rendered_html = page.content()

            print("\nRendered HTML size:", len(rendered_html))

            print("\nRendered HTML preview:")
            print(rendered_html[:1000])

            # ---------------------------------------------------------
            # 2. JavaScript globals
            # ---------------------------------------------------------

            globals_to_check = [
                "__NEXT_DATA__",
                "__NUXT__",
                "React",
                "jQuery",
                "$",
                "Shopify",
            ]

            print("\nJAVASCRIPT GLOBALS:")

            for name in globals_to_check:
                exists = page.evaluate(
                    """
                    (name) => typeof window[name] !== "undefined"
                    """,
                    name,
                )

                print(f"{name:<20} -> {exists}")

            # ---------------------------------------------------------
            # 3. Browser cookies
            # ---------------------------------------------------------

            cookies = context.cookies()

            print("\nBROWSER COOKIES:")

            if not cookies:
                print("None")
            else:
                for cookie in cookies:
                    name = cookie.get("name")
                    value = cookie.get("value", "")

                    print(
                        f"{name} = {value[:80]}"
                    )

            # ---------------------------------------------------------
            # 4. Runtime script URLs
            # ---------------------------------------------------------

            runtime_scripts = page.locator(
                "script[src]"
            ).evaluate_all(
                """
                (elements) =>
                    elements.map(element => element.src)
                """
            )

            print("\nRUNTIME SCRIPT SOURCES:")

            if not runtime_scripts:
                print("None")
            else:
                for src in runtime_scripts:
                    print(" -", src)

            # ---------------------------------------------------------
            # 5. Runtime stylesheet URLs
            # ---------------------------------------------------------

            runtime_stylesheets = page.locator(
                'link[rel="stylesheet"][href]'
            ).evaluate_all(
                """
                (elements) =>
                    elements.map(element => element.href)
                """
            )

            print("\nRUNTIME STYLESHEETS:")

            if not runtime_stylesheets:
                print("None")
            else:
                for href in runtime_stylesheets:
                    print(" -", href)

        except Exception as exc:
            print("Browser inspection failed:", exc)

        finally:
            browser.close()


inspect_browser("https://lakshx.in/")