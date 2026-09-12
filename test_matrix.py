# Tiny offline test matrix: no HTTP requests.
#
# For each technology we build three synthetic contexts (strong / partial /
# none) by hand, run them through the same engine.detect() used for real
# responses, and print the resulting score/confidence. This is how we probe
# scoring questions (should one strong rule be enough? should some rules be
# mandatory? etc.) without needing a live site to change its headers.

from engine import detect, make_context
from fingerprints import FINGERPRINTS

TEST_CASES = [
    {
        "technology": "Cloudflare",
        "case": "strong",
        "headers": {"server": "cloudflare", "cf-ray": "8a1b2c3d4e5f", "cf-cache-status": "HIT"},
        "html": "<html><body>hello</body></html>",
    },
    {
        "technology": "Cloudflare",
        "case": "partial",
        "headers": {"server": "cloudflare"},
        "html": "<html><body>hello</body></html>",
    },
    {
        "technology": "Cloudflare",
        "case": "none",
        "headers": {"server": "nginx"},
        "html": "<html><body>hello</body></html>",
    },
    {
        "technology": "Vercel",
        "case": "strong",
        "headers": {"server": "vercel", "x-vercel-id": "cle1::abcde-123", "x-vercel-cache": "HIT"},
        "html": "<html><body>hello</body></html>",
    },
    {
        "technology": "Vercel",
        "case": "partial",
        "headers": {"server": "vercel"},
        "html": "<html><body>hello</body></html>",
    },
    {
        "technology": "Vercel",
        "case": "none",
        "headers": {"server": "apache"},
        "html": "<html><body>hello</body></html>",
    },
    {
        "technology": "Next.js",
        "case": "strong",
        "headers": {"x-nextjs-prerender": "1", "x-nextjs-stale-time": "4294967294"},
        "html": '<html><body><script src="/_next/static/chunks/main.js"></script>'
                '<script id="__NEXT_DATA__">{}</script></body></html>',
    },
    {
        "technology": "Next.js",
        "case": "partial",
        "headers": {},
        "html": '<html><body><script src="/_next/static/chunks/main.js"></script></body></html>',
    },
    {
        "technology": "Next.js",
        "case": "none",
        "headers": {},
        "html": "<html><body>hello</body></html>",
    },
    {
        "technology": "WordPress",
        "case": "strong",
        "headers": {},
        "html": '<html><body><link href="/wp-content/themes/x/style.css">'
                '<script src="/wp-includes/js/jquery.js"></script></body></html>',
    },
    {
        "technology": "WordPress",
        "case": "partial",
        "headers": {},
        "html": '<html><body><link href="/wp-content/themes/x/style.css"></body></html>',
    },
    {
        "technology": "WordPress",
        "case": "none",
        "headers": {},
        "html": "<html><body>hello</body></html>",
    },
    {
        # Only the meta-generator signal fires, no wp-content/wp-includes
        # paths at all — checks that the new "meta" source works on its
        # own and is weighted high enough to reach "strong" alone.
        "technology": "WordPress",
        "case": "meta_only",
        "headers": {},
        "html": '<html><head><meta name="generator" content="WordPress 6.4.2"></head>'
                "<body>hello</body></html>",
    },
    {
        # cf_clearance alone: bonus signal only, must NOT clear threshold
        # by itself (this is the first case that actually exercises the
        # "cookie" source end to end).
        "technology": "Cloudflare",
        "case": "cookie_only",
        "headers": {},
        "html": "<html><body>hello</body></html>",
        "cookies": {"cf_clearance": "abc123"},
    },
    {
        # Same edge headers as the "strong" case, plus the cookie — score
        # should be higher than "strong" alone (60+20+20=100 vs 80).
        "technology": "Cloudflare",
        "case": "headers_and_cookie",
        "headers": {"cf-ray": "8a1b2c3d4e5f"},
        "html": "<html><body>hello</body></html>",
        "cookies": {"cf_clearance": "abc123"},
    },
    {
        # wordpress_test_cookie alone: also below threshold by itself, and
        # in practice this cookie only shows up from wp-login.php, not a
        # homepage GET — see the comment in fingerprints.py.
        "technology": "WordPress",
        "case": "cookie_only",
        "headers": {},
        "html": "<html><body>hello</body></html>",
        "cookies": {"wordpress_test_cookie": "WP Cookie check"},
    },
    {
        # next-size-adjust alone: below threshold by itself, same pattern
        # as every other single weak signal in this matrix.
        "technology": "Next.js",
        "case": "meta_only",
        "headers": {},
        "html": '<html><head><meta name="next-size-adjust" content=""></head>'
                "<body>hello</body></html>",
    },
]


def run_matrix():
    for test in TEST_CASES:
        context = make_context(test["headers"], test["html"], test.get("cookies"))

        results = detect(FINGERPRINTS, context)
        match = next((r for r in results if r["technology"] == test["technology"]), None)

        print(f"{test['technology']:<10} [{test['case']:<7}] -> ", end="")

        if match is None:
            print("NOT DETECTED (score below threshold or no rules matched)")
        else:
            print(f"score={match['confidence_score']:<4} confidence={match['confidence']}")
            for line in match["evidence"]:
                print(f"    - {line}")


# Focused cases probing the Next.js group boundaries specifically:
# the "any" header group vs. the "all" html-marker group, and every
# combination of the two groups firing/not firing.
NEXTJS_GROUP_CASES = [
    {
        "name": "headers_only",
        "headers": {
            "x-nextjs-prerender": "1",
        },
        "html": "",
    },
    {
        "name": "static_only",
        "headers": {},
        "html": '<script src="/_next/static/chunks/app.js"></script>',
    },
    {
        "name": "both_html_markers",
        "headers": {},
        "html": '<script src="/_next/static/chunks/app.js"></script><script id="__NEXT_DATA__"></script>',
    },
    {
        "name": "headers_and_html",
        "headers": {
            "x-nextjs-prerender": "1",
        },
        "html": '<script src="/_next/static/chunks/app.js"></script><script id="__NEXT_DATA__"></script>',
    },
]


def run_nextjs_group_cases():
    for case in NEXTJS_GROUP_CASES:
        context = make_context(case["headers"], case["html"])

        results = detect(FINGERPRINTS, context)
        match = next((r for r in results if r["technology"] == "Next.js"), None)

        print(f"{case['name']:<18} -> ", end="")

        if match is None:
            print("NOT DETECTED")
        else:
            print(f"score={match['confidence_score']:<4} confidence={match['confidence']}")
            for line in match["evidence"]:
                print(f"    - {line}")


if __name__ == "__main__":
    run_matrix()
    print()
    print("Next.js group-logic cases:")
    run_nextjs_group_cases()
