import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from tech_detection.evidence import extract_html_signals


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
    if not signals["script_src"]:
        print("None")
    else:
        for script in signals["script_src"]:
            print(" -", script)

    print("\nSTYLESHEETS:")
    if not signals["stylesheet_href"]:
        print("None")
    else:
        for stylesheet in signals["stylesheet_href"]:
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
