from pipeline import detect_website_technologies


def print_result(result):
    print("=" * 70)
    print("URL:", result["url"])
    print("Evidence source:", result["evidence_source"])

    if not result["technologies"]:
        print("No technologies detected")
        return

    for item in result["technologies"]:
        print(f"\n{item['technology']} ({item['category']})")
        print(f"  confidence: {item['confidence']} ({item['confidence_score']})")

        for line in item["evidence"]:
            print(f"  - {line}")


print_result(detect_website_technologies("https://example.com"))
print_result(detect_website_technologies("https://lakshx.in/"))
