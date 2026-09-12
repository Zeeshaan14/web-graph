from tech_detection.pipeline import detect_website_technologies


def print_result(result):
    print("=" * 70)
    print("URL:", result["url"])
    print(f"Status: {result['status']} | HTTP status: {result['http_status']} | "
          f"Browser status: {result['browser_status']}")

    for err in result["errors"]:
        print(f"  ERROR [{err['type']}]: {err['message']}")

    if result["status"] == "failed":
        return

    print("Evidence source:", result["evidence_source"])

    if not result["technologies"]:
        print("No technologies detected")
        return

    for item in result["technologies"]:
        if item["detection_type"] == "inferred":
            print(f"\n{item['technology']} (inferred from {item['inferred_from']})")
            continue

        print(f"\n{item['technology']} ({item['category']})")
        print(f"  confidence: {item['confidence']} ({item['confidence_score']})")

        for line in item["evidence"]:
            print(f"  - {line}")


print_result(detect_website_technologies("https://example.com"))
print_result(detect_website_technologies("https://lakshx.in/"))
