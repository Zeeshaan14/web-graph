import requests

from engine import build_context, detect
from fingerprints import FINGERPRINTS


def inspect_url(url: str):
    try:
        response = requests.get(url, timeout=10)
    except requests.exceptions.RequestException as exc:
        print("Request failed:", exc)
        return

    print("=" * 70)
    print("Requested URL:", url)
    print("Final URL:", response.url)
    print("Status:", response.status_code)

    context = build_context(response)
    technologies = detect(FINGERPRINTS, context)

    print("\nDetected Technologies:")

    if not technologies:
        print("None detected")
        return

    for item in technologies:
        print(f"\n{item['technology']} ({item['category']})")
        print(f"  confidence: {item['confidence']} ({item['confidence_score']})")

        for evidence in item["evidence"]:
            print(f"  - {evidence}")


inspect_url("https://example.com")
inspect_url("https://lakshx.in/")