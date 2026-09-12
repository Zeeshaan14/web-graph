import requests

from html_signals import extract_html_signals


def inspect_html_signals(url: str):
    try:
        response = requests.get(url, timeout=10)
    except requests.exceptions.RequestException as exc:
        print("Request failed:", exc)
        return

    content_type = response.headers.get("content-type", "")

    if "text/html" not in content_type.lower():
        print("Response is not HTML:", content_type)
        return

    signals = extract_html_signals(response.text)

    print("=" * 70)
    print("URL:", response.url)

    print("\nSCRIPTS:")
    if not signals["scripts"]:
        print("None")
    else:
        for script in signals["scripts"]:
            print(" -", script)

    print("\nSTYLESHEETS:")
    if not signals["stylesheets"]:
        print("None")
    else:
        for stylesheet in signals["stylesheets"]:
            print(" -", stylesheet)

    print("\nMETA TAGS:")
    if not signals["meta"]:
        print("None")
    else:
        for meta in signals["meta"]:
            print(
                f" - name={meta['name']!r}, "
                f"property={meta['property']!r}, "
                f"content={meta['content']!r}"
            )


if __name__ == "__main__":
    inspect_html_signals("https://lakshx.in/")
