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
#   rules  -> list of rules, in one of two shapes:
#
#     {source, key, operator, value} — single-field lookup
#             source   -> "header" | "cookie" | "html"
#                       | "script_src"     (any <script src="...">)
#                       | "stylesheet_href" (any <link rel="stylesheet" href="...">)
#                       | "meta"           (a <meta name=".."/property="..">'s content)
#                       | "javascript_globals" (browser-only — names found on
#                         window; absent entirely from HTTP-only evidence, so
#                         rules using it only ever match after a browser pass)
#             key      -> required for "header", "cookie", "meta"
#             operator -> "exists" | "contains" | "equals"
#             value    -> required for "contains" and "equals"
#
#     {source: "meta", conditions: [...]} — multi-field lookup, meta only.
#             Matches if some SINGLE meta tag satisfies every condition at
#             once (e.g. that tag's "name" equals "generator" AND its
#             "content" contains "wordpress") — stronger than checking each
#             field independently, since both must be true of the same tag.
#             Each condition is {field, operator, value}, where field is
#             "name" | "property" | "content".

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
                # This uses the "conditions" meta rule shape: both
                # conditions must hold on the SAME tag (its name IS
                # "generator" AND its content mentions WordPress) rather
                # than checking name and content independently across the
                # whole meta list, so a page with an unrelated tag named
                # "generator" and a different tag mentioning WordPress
                # elsewhere would NOT match.
                "logic": "any",
                "weight": 70,
                "rules": [
                    {
                        "source": "meta",
                        "conditions": [
                            {"field": "name", "operator": "equals", "value": "generator"},
                            {"field": "content", "operator": "contains", "value": "wordpress"},
                        ],
                    },
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

    # ---- Frontend/framework -------------------------------------------
    # Deliberately a mix of difficulties: Angular self-identifies almost
    # as clearly as WordPress does; React strips nearly everything a
    # production build would otherwise leave behind, so it's honestly
    # weak-to-invisible on most real sites — that's the correct outcome,
    # not a fingerprint that needs "fixing."
    {
        "technology": "React",
        "category": "Frontend Framework",
        "groups": [
            {
                # data-reactroot was React's own SSR hydration marker —
                # removed in React 18, so this only fires on older apps.
                "logic": "any",
                "weight": 40,
                "rules": [
                    {"source": "html", "operator": "contains", "value": "data-reactroot"},
                ],
            },
            {
                # window.React only exists if the build exposes it (UMD/
                # CDN-style loads, or unminified dev builds) — most bundled
                # production apps tree-shake this away entirely, so absence
                # proves nothing either way. Browser-only.
                "logic": "any",
                "weight": 40,
                "rules": [
                    {"source": "javascript_globals", "operator": "equals", "value": "react"},
                ],
            },
            {
                # Catches the rarer CDN/UMD case (e.g. unpkg.com/react).
                "logic": "any",
                "weight": 20,
                "rules": [
                    {"source": "script_src", "operator": "contains", "value": "react"},
                ],
            },
        ],
    },
    {
        "technology": "Vue",
        "category": "Frontend Framework",
        "groups": [
            {
                # data-v-xxxxxxxx is Vue's single-file-component scoped-CSS
                # compiler output — survives production builds (unlike
                # React's markers), so it's meaningfully more reliable than
                # anything React leaves behind.
                "logic": "any",
                "weight": 60,
                "rules": [
                    {"source": "html", "operator": "contains", "value": "data-v-"},
                ],
            },
            {
                # Same caveat as window.React: only present for UMD/dev
                # builds. Browser-only.
                "logic": "any",
                "weight": 40,
                "rules": [
                    {"source": "javascript_globals", "operator": "equals", "value": "vue"},
                ],
            },
        ],
    },
    {
        "technology": "Angular",
        "category": "Frontend Framework",
        "groups": [
            {
                # Angular writes ng-version="x.y.z" onto its root element in
                # every production build — an explicit, unambiguous
                # self-identification, closer to WordPress's generator tag
                # than to anything React/Vue expose.
                "logic": "any",
                "weight": 80,
                "rules": [
                    {"source": "html", "operator": "contains", "value": "ng-version"},
                ],
            },
        ],
    },

    # ---- CMS / commerce -------------------------------------------------
    {
        "technology": "Shopify",
        "category": "Ecommerce Platform",
        "groups": [
            {
                # Shopify storefronts serve theme JS/CSS from Shopify's own
                # CDN domain — consistent across virtually every storefront,
                # regardless of theme. Structural, hard to fake.
                "logic": "any",
                "weight": 70,
                "rules": [
                    {"source": "script_src", "operator": "contains", "value": "cdn.shopify.com"},
                    {"source": "stylesheet_href", "operator": "contains", "value": "cdn.shopify.com"},
                ],
            },
            {
                # The storefront JS API exposes window.Shopify at runtime.
                # Browser-only.
                "logic": "any",
                "weight": 40,
                "rules": [
                    {"source": "javascript_globals", "operator": "equals", "value": "shopify"},
                ],
            },
        ],
    },

    # ---- Server -----------------------------------------------------
    # The Server header is the ONLY passive signal a base web server
    # typically offers — no equivalent to a generator tag or a CDN path.
    # It's also the easiest header to spoof or strip, which is exactly why
    # it's capped at "possible" (40) rather than pushed higher: real, but
    # not proof by itself. This differs from how Cloudflare/Vercel's own
    # Server-text rule was weighted (20, deliberately below threshold) —
    # those had a much stronger corroborating header available (cf-ray,
    # x-vercel-id), so their Server text was redundant filler. nginx/Apache
    # have no such alternative, so treating it identically weak would make
    # them nearly undetectable via HTTP evidence at all.
    {
        "technology": "nginx",
        "category": "Web Server",
        "groups": [
            {
                "logic": "any",
                "weight": 50,
                "rules": [
                    {"source": "header", "key": "server", "operator": "contains", "value": "nginx"},
                ],
            },
        ],
    },
    {
        "technology": "Apache",
        "category": "Web Server",
        "groups": [
            {
                "logic": "any",
                "weight": 50,
                "rules": [
                    {"source": "header", "key": "server", "operator": "contains", "value": "apache"},
                ],
            },
        ],
    },

    # ---- Analytics --------------------------------------------------
    # Represented as one combined entry rather than two separate ones:
    # GTM is usually the delivery mechanism GA loads through, and at the
    # passive-fingerprint level the two are largely indistinguishable
    # (same loader domain, same runtime globals) — splitting them would
    # fabricate a precision the evidence doesn't actually support.
    {
        "technology": "Google Tag Manager / Google Analytics",
        "category": "Analytics",
        "groups": [
            {
                # The loader script (gtm.js / gtag.js / legacy analytics.js)
                # and GTM's <noscript> iframe fallback both show up in raw
                # server-rendered HTML, so this is detectable via HTTP
                # evidence alone, not just after a browser pass.
                "logic": "any",
                "weight": 60,
                "rules": [
                    {"source": "script_src", "operator": "contains", "value": "googletagmanager.com"},
                    {"source": "script_src", "operator": "contains", "value": "google-analytics.com"},
                    {"source": "html", "operator": "contains", "value": "googletagmanager.com"},
                ],
            },
            {
                # dataLayer / gtag are runtime globals GTM/gtag.js create —
                # bonus corroboration once a browser pass has run.
                "logic": "any",
                "weight": 30,
                "rules": [
                    {"source": "javascript_globals", "operator": "equals", "value": "datalayer"},
                    {"source": "javascript_globals", "operator": "equals", "value": "gtag"},
                ],
            },
        ],
    },
]
