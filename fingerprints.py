# Fingerprint definitions: pure data, no detection logic.
#
# Each fingerprint has a technology, a category, and a list of rule GROUPS.
# A group is the unit that earns points — individual rules inside a group
# no longer carry their own weight, the group does:
#
#   logic  -> "any" (OR: satisfied if at least one rule in the group matches)
#           | "all" (AND: satisfied only if every rule in the group matches)
#   weight -> points added to the score when the group is satisfied
#             (awarded once per group, not once per matching rule)
#   rules  -> list of {source, key, operator, value}
#             source   -> "header" | "cookie" | "html"
#                       | "script_src"     (any <script src="...">)
#                       | "stylesheet_href" (any <link rel="stylesheet" href="...">)
#                       | "meta"           (a <meta name=".."/property="..">'s content)
#             key      -> required for "header", "cookie", "meta"
#             operator -> "exists" | "contains" | "equals"
#             value    -> required for "contains" and "equals"

FINGERPRINTS = [
    {
        "technology": "Cloudflare",
        "category": "CDN / Security",
        "groups": [
            {
                # Cloudflare-specific edge headers. Either one alone is
                # already fairly conclusive, and having both isn't "more
                # true" than having one, so they're grouped as alternatives
                # (any) rather than summed.
                "logic": "any",
                "weight": 60,
                "rules": [
                    {"source": "header", "key": "cf-ray", "operator": "exists"},
                    {"source": "header", "key": "cf-cache-status", "operator": "exists"},
                ],
            },
            {
                # A generic "Server: cloudflare" string is operator-settable
                # and proves little by itself, so it's capped low enough
                # that it can never clear MIN_DETECTION_SCORE on its own.
                "logic": "any",
                "weight": 20,
                "rules": [
                    {"source": "header", "key": "server", "operator": "contains", "value": "cloudflare"},
                ],
            },
            {
                # cf_clearance / __cf_bm are only set when Cloudflare's bot
                # management or JS challenge is actively engaged, not on
                # every Cloudflare-fronted site (confirmed: example.com sets
                # neither). So this is a bonus signal, not a baseline one —
                # weighted low, but it's genuine, hard-to-fake evidence
                # when it IS present.
                "logic": "any",
                "weight": 20,
                "rules": [
                    {"source": "cookie", "key": "cf_clearance", "operator": "exists"},
                    {"source": "cookie", "key": "__cf_bm", "operator": "exists"},
                ],
            },
        ],
    },
    {
        "technology": "Vercel",
        "category": "Hosting / Platform",
        "groups": [
            {
                "logic": "any",
                "weight": 70,
                "rules": [
                    {"source": "header", "key": "x-vercel-id", "operator": "exists"},
                    {"source": "header", "key": "x-vercel-cache", "operator": "exists"},
                ],
            },
            {
                # Same reasoning as Cloudflare's server-header group: weak
                # on its own, deliberately kept under threshold alone.
                "logic": "any",
                "weight": 20,
                "rules": [
                    {"source": "header", "key": "server", "operator": "contains", "value": "vercel"},
                ],
            },
        ],
    },
    {
        "technology": "Next.js",
        "category": "Web Framework",
        "groups": [
            {
                # Next.js-specific response headers are hard to fake and
                # strong evidence even alone.
                "logic": "any",
                "weight": 70,
                "rules": [
                    {"source": "header", "key": "x-nextjs-prerender", "operator": "exists"},
                    {"source": "header", "key": "x-nextjs-stale-time", "operator": "exists"},
                ],
            },
            {
                # "/_next/static/" is already a structural, framework-specific
                # marker on its own (confirmed by lakshx.in, which has it but
                # not __NEXT_DATA__) — requiring both caused real false
                # negatives. Each is decent independent evidence, so "any".
                #
                # Checked against actual <script src> and <link href> values
                # (not raw HTML text) so a stray mention of the string
                # elsewhere on the page can't trigger it — lakshx.in showed
                # the same "/_next/static/" path in both scripts and CSS
                # chunk stylesheets.
                "logic": "any",
                "weight": 40,
                "rules": [
                    {"source": "script_src", "operator": "contains", "value": "/_next/static/"},
                    {"source": "stylesheet_href", "operator": "contains", "value": "/_next/static/"},
                    {"source": "html", "operator": "contains", "value": "__NEXT_DATA__"},
                ],
            },
            {
                # "next-size-adjust" is a meta tag next/font (Next.js's font
                # optimization module) injects — seen on lakshx.in. Unlike
                # WordPress's generator tag it's not an explicit self-ID, and
                # we haven't verified how consistently next/font is used
                # across Next.js sites, so it's a low-weight bonus signal
                # rather than a primary one.
                "logic": "any",
                "weight": 20,
                "rules": [
                    {"source": "meta", "key": "next-size-adjust", "operator": "exists"},
                ],
            },
        ],
    },
    {
        "technology": "WordPress",
        "category": "CMS",
        "groups": [
            # wp-content and wp-includes are independent markers (theme
            # assets vs core assets), not duplicates of the same signal,
            # so each gets its own group and they add up when both appear.
            {
                "logic": "any",
                "weight": 40,
                "rules": [
                    {"source": "html", "operator": "contains", "value": "/wp-content/"},
                ],
            },
            {
                "logic": "any",
                "weight": 40,
                "rules": [
                    {"source": "html", "operator": "contains", "value": "/wp-includes/"},
                ],
            },
            {
                # WordPress self-identifies via <meta name="generator">.
                # This is about as close to ground truth as passive
                # fingerprinting gets, so it's weighted high enough to
                # reach "strong" almost on its own.
                "logic": "any",
                "weight": 90,
                "rules": [
                    {"source": "meta", "key": "generator", "operator": "contains", "value": "wordpress"},
                ],
            },
            {
                # wordpress_test_cookie is set by WordPress's login flow
                # (wp-login.php), not the homepage — so a plain single GET
                # to the site root will usually NOT see it. Kept as a weak
                # bonus signal for crawlers that do touch the login page,
                # not something to rely on.
                "logic": "any",
                "weight": 20,
                "rules": [
                    {"source": "cookie", "key": "wordpress_test_cookie", "operator": "exists"},
                ],
            },
        ],
    },
]
