# web-graph — Architecture & File Guide

This doc explains **how the project is built** and **what every file does**.
For **what's supported vs. not yet** per feature, see `README.md` — this
file is about structure and mechanics, not feature status.

## The big picture

```
Client (browser / curl)
   |
   v
frontend/  (Next.js)  ---- fetch() ---->  backend/api/  (FastAPI)
                                              |
                                              v
                                  feature package (tech_detection /
                                  url_discovery / content_extraction /
                                  website_processing)
                                              |
                                              v
                                    requests (HTTP)  +  Playwright (browser,
                                    only when the cheap HTTP pass looks
                                    insufficient)
                                              |
                                              v
                                    structured result dict, never a
                                    raised exception
```

Two top-level folders, run and versioned independently:

- **`backend/`** — Python. All four features, the FastAPI layer, tests.
  Everything below "Backend" in this doc lives here.
- **`frontend/`** — Next.js. A thin client over the API, one page per
  feature. The frontend never imports backend code — it only calls the
  HTTP endpoints.

### The one idea that repeats everywhere

Every feature is organized as **evidence/fetch → generic engine → results**,
and the *engine* part never knows about the *specific site or technology*
it's looking at. That knowledge lives in data (fingerprint definitions,
relationship tables), not in `if`-branches. This is why `tech_detection`
can support 11 technologies without the detection logic itself mentioning
"WordPress" or "Cloudflare" anywhere.

The second idea that repeats: **every feature-level entry point returns a
predictable dict shape and never raises.** A caller (the API layer, or you
at a REPL) never needs a `try/except` around `detect_website_technologies()`,
`discover_urls()`, `extract_content()`, or `discover_and_extract()` — they
always return `{"status": "success" | "partial" | "failed", ...}` (or, for
`extract_content()`, just `"success" | "failed"`, since it's single-resource,
not a batch).

### The other repeated idea: HTTP first, browser only if needed

Three of the four features (`tech_detection`, `url_discovery`,
`content_extraction`) can fall back to a real headless Chromium browser
(via Playwright) when a plain HTTP fetch isn't enough — e.g. a
JavaScript-rendered single-page app whose raw HTML is just an empty shell.
Each has its own `browser.py`, and each duplicates (never imports across
features) a small "is this worth rendering?" heuristic: strip
`<script>`/`<style>` tags, count the remaining visible text, and if it's
under ~80 characters, treat the page as an unrendered shell worth a
browser pass. That threshold was calibrated once (a real bare SPA shell
measures 0 visible characters; example.com's real page measures 139; 80
sits between the two) and reused identically in all three copies.

Why duplicated instead of shared? Every feature package is meant to stay
**self-contained** — a change to how `url_discovery` fetches pages should
never silently change how `content_extraction` fetches pages. This is a
deliberate, repeated architectural choice stated explicitly in the code's
own comments each time it happens, not an oversight.

---

## Backend — top level

| File | What it does |
|---|---|
| `backend/pyproject.toml` | Dependencies (`requests`, `beautifulsoup4`, `playwright`, `markdownify`, `fastapi`, `uvicorn`) + pytest config. `addopts = "-m 'not network'"` excludes real-network tests by default. |
| `backend/uv.lock` | Locked dependency versions (uv-managed). |
| `backend/conftest.py` | Empty except a comment — its mere presence (with no `__init__.py` anywhere in `tests/`) makes pytest add the repo root to `sys.path`, so every test file can import feature packages regardless of which subfolder it's in. |
| `backend/cli.py` | A 3-line manual smoke test: runs `detect_website_technologies()` against two real sites and pretty-prints the result. Not a real CLI tool, just a quick way to eyeball output during development. |
| `backend/testing/test.py` | Dev-only script: dumps a URL's raw scripts/stylesheets/meta tags to inspect what evidence *would* be available, without running detection. |
| `backend/testing/playwright-test.py` | Standalone Playwright prototype/reference — predates `tech_detection/browser.py`, kept as a reference example. |

---

## Feature 1: `tech_detection/` — tech stack detection

**What it does:** given a URL, returns the technologies the site is built
with (frameworks, CDNs, hosting, analytics), each with a confidence level
and the evidence that led to it.

**The pipeline (two-stage: HTTP, then browser if needed):**

```
fetcher.py: fetch_url()
       |
       v
evidence.py: build_evidence()  -->  {headers, cookies, html, script_src,
       |                             stylesheet_href, meta}
       v
engine.py: detect_technologies()  -->  direct detections (HTTP-only)
       |
       v
fallback.py: should_use_browser()?  --- no --->  done, return HTTP-only result
       | yes
       v
browser.py: collect_browser_evidence()  (real Chromium launch)
       |
       v
evidence.py: merge_evidence()  -->  combined HTTP + browser evidence
       |
       v
engine.py: detect_technologies()  -->  final direct detections
       |
       v
inference.py: add_inferred_technologies()  -->  + implied techs (e.g. React from Next.js)
       |
       v
{status, http_status, browser_status, evidence_source, technologies, errors}
```

| File | What it does |
|---|---|
| `pipeline.py` | **Orchestrates the whole flow above.** `detect_website_technologies(url)` is the public entry point — the only function that ever gets called from outside this package (the API route, `cli.py`). Wraps every stage in `try/except` so it never raises; a browser failure mid-flow doesn't discard the already-valid HTTP result, it's returned as `status: "partial"` instead. |
| `fetcher.py` | `fetch_url(url)` — plain `requests.get()`, nothing else. No retry, no pacing (unlike `url_discovery`'s fetcher, this only ever fetches one page). |
| `evidence.py` | Turns a raw HTTP response (or raw HTML string, for tests) into the flat evidence dict `engine.py` evaluates: `{headers, cookies, html, script_src, stylesheet_href, meta}`. Also owns `merge_evidence()`, which combines HTTP evidence with browser evidence field-by-field (e.g. `html` prefers the browser's fully-rendered version; `cookies` merges both, browser wins on collision; `javascript_globals` is browser-only). |
| `browser.py` | `collect_browser_evidence(url)` — launches headless Chromium via Playwright, renders the page, and collects the same evidence shape plus `javascript_globals` (checks `window.React`, `window.__NEXT_DATA__`, etc. after JS has run). One-shot: launch, collect, close — this feature only ever analyzes one URL per call. |
| `fallback.py` | `should_use_browser(evidence, technologies)` — the decision logic, kept **separate** from `browser.py` (which only knows how to *collect*, not *decide*). Says yes if: no technologies were detected at all, or every detection is only "possible" confidence *and* at least one of them could gain more evidence from a browser pass, or the page's visible text is under 80 characters (looks like an unrendered app shell). Says no immediately for any 4xx/5xx response — no browser is going to reveal more from an error page. |
| `engine.py` | The **generic** rule evaluator. Knows how to check `exists`/`contains`/`equals` against an evidence dict and turn matched rule-group weights into a 0–100 confidence score (`strong` ≥80, `likely` ≥60, `possible` ≥40). Knows nothing about any specific technology — `fingerprints.py` is the only file that does. `detect_technologies(evidence)` is the entry point; `detect(fingerprints, context)` is the underlying generic form used directly by tests. |
| `fingerprints.py` | **Data, not logic.** The 11 fingerprint definitions (Cloudflare, Vercel, Next.js, WordPress, React, Vue, Angular, Shopify, nginx, Apache, Google Tag Manager/Analytics), each a list of weighted rule groups (`any`=OR / `all`=AND logic) that `engine.py` evaluates generically. |
| `relationships.py` | A tiny table of what a direct detection *implies* — currently just `{"Next.js": ["React"]}`. Deliberately kept small: only add an entry once it's genuinely near-certain, not a loose correlation. |
| `inference.py` | Applies `relationships.py` to a set of direct detections, producing extra entries tagged `detection_type: "inferred"` (no confidence/evidence of their own — inference is a claim about the ecosystem, not observed evidence). Runs as a separate pass *after* `engine.py`, which never knows inference exists. |

**Result contract:**
```
{
  "url", "status": "success"|"partial"|"failed",
  "http_status": int | None,
  "browser_status": "not_launched" | "ok" | "failed",   # never null
  "evidence_source": "http" | "http+browser" | None,
  "technologies": [...],  # each direct or inferred, see below
  "errors": [{"type", "message"}]
}
```
A **direct** technology entry: `{technology, category, confidence_score, confidence, evidence, browser_enrichable, detection_type: "direct"}`.
An **inferred** entry: `{technology, detection_type: "inferred", inferred_from}` — no confidence or evidence fields at all.

---

## Feature 2A: `url_discovery/` — crawl a site for its public URLs

**What it does:** starting from one URL, breadth-first crawls a site
(staying same-domain) and returns every public URL it found.

**The pipeline:**

```
crawler.py: crawl()
   |
   ├── fetcher.py: fetch()          -- one polite GET per page (pacing + 429 retry)
   ├── _load_robots_policy()        -- fetched once, not per page
   ├── _discover_sitemap_urls()     -- fetched once, seeds extra URLs at depth 0
   │
   └── per page in the BFS loop:
         ├── robots_policy.can_fetch()?           -- skip if disallowed
         ├── browser.py: should_render_with_browser()?  -- thin page? maybe render
         ├── link_extraction.py: extract_canonical(), extract_links()
         └── queue newly-found same-site links
   |
   v
{urls, pages_traversed, errors}   (crawl()'s internal shape)
   |
   v
discover_urls()  -->  {status, start_url, discovered_urls, pages_traversed, errors}
```

| File | What it does |
|---|---|
| `crawler.py` | **The traversal engine.** `crawl()` owns the BFS queue, depth tracking, and the critical **traversal identity vs. output identity** split: `visited_traversal` (keyed on the final URL after redirects — decides what gets fetched/expanded) is kept separate from `discovered_output` (prefers a same-site `<link rel="canonical">` — decides what gets *reported*). A canonical tag can make several pages collapse into one reported URL, but it must never stop traversal — `/articles/page/2/` still gets fetched and its links followed even though it *reports* as `/articles/`. Also owns the crawl-scoped browser lifecycle (see below) and the wall-clock timeout / `max_pages` / `max_depth` budgets. `discover_urls()` wraps `crawl()` with the public contract: derives `status` (`failed` if nothing was ever fetched, `partial` if some pages errored, else `success`) and guarantees nothing ever raises out. |
| `fetcher.py` | `fetch(session, url)` — one GET with browser-shaped headers (`BROWSER_HEADERS`, needed because some sites 403 a bare `python-requests` UA), a 1-second politeness delay after *every* attempt, and a controlled one-time retry on `429` (using the `Retry-After` header if present, else a 5-second fallback). |
| `link_extraction.py` | Pure URL/HTML functions, no network: `normalize_url()` (lowercases scheme/host, strips default ports and tracking params like `utm_*`, supports a caller-supplied `path_specific_strip` for site-specific noisy params), `extract_links()` (parses `<a href>`, resolves relative URLs, filters to same-site), `extract_canonical()` (reads `<link rel="canonical">`), and `is_same_site()` (treats a leading `www.` as a cosmetic alias but *not* any other subdomain — `blog.x.com` stays a different site from `x.com`). |
| `browser.py` | `should_render_with_browser(html)` (the shared visible-text heuristic) and `render_page_html(browser, url)` (renders one page using an **already-running** browser instance — `crawler.py` owns launching/closing it, not this file). |

**The crawl-scoped browser lifecycle** (in `crawler.py`, not `browser.py`) is
the one place this feature genuinely differs from `tech_detection`'s
single-page version: a crawl can visit many pages, so launching a fresh
Chromium process per thin page would be wasteful and slow. Instead:
Chromium is launched **lazily** (only when the first page actually needs
it), **reused** across every subsequent page in that same crawl that also
needs it, and **closed once** at the end. A hard cap
(`MAX_BROWSER_RENDERS_PER_CRAWL = 10`, not caller-configurable) bounds how
many pages get rendered in one crawl. Failure is handled at two levels: one
page's render failing falls back to that page's raw HTML (not an error);
the initial browser *launch* failing sets a sticky `browser_unavailable`
flag so the rest of the crawl doesn't keep retrying (and re-failing) a
launch that's already known to be broken.

**robots.txt and sitemap.xml** are both crawl-scoped, fetched once (via the
same `fetch()`, so they get the same pacing/retry/headers as any page), and
never count toward `max_pages`/`pages_traversed` — they're crawler
infrastructure, not discovered pages. A robots.txt fetch failure defaults
to "allowed" unless it's a `401`/`403` (mirrors Python's own
`urllib.robotparser` convention). A sitemap is read from the first
`Sitemap:` line in robots.txt, or the conventional `/sitemap.xml` if none
is declared — deliberately scoped to one non-index sitemap file, not a
`<sitemapindex>` chasing multiple child sitemaps.

**Result contract:** `{status, start_url, discovered_urls: [str], pages_traversed: int, errors: [{url, error}]}`.

---

## Feature 2B: `content_extraction/` — pull one page's content

**What it does:** given a URL, fetches it and converts its whole `<body>`
to Markdown — headings, links, images, bold/italic, lists, nav and footer
included. Not density-scored "main content" picking; a direct structural
conversion of whatever was actually on the page.

**The pipeline (all in one file, `content_extraction.py`):**

```
_fetch(url)                         -- polite GET, streamed, 429-retried
   |
   v
content-type check                  -- non-HTML -> failed immediately
   |
   v
content-length check + _decode_bounded()   -- 5 MB cap enforced WHILE streaming
   |
   v
should_render_with_browser(html)?  --- yes --->  render_page_html(url), replace html entirely
   |
   v
soup.title  -->  title
   |
   v
soup.body (falls back to the whole soup if there's no <body>)
   |
   v
_resolve_relative_urls(body, url)   -- <a href>/<img src> rewritten to absolute
   |
   v
markdownify(str(body), heading_style="ATX", bullets="-")  -->  content_markdown
   |
   v
{status, url, title, content_markdown, error}
```

| File | What it does |
|---|---|
| `content_extraction.py` | Everything: `_fetch()` (streamed GET with the same politeness-pacing + 429-retry policy as `url_discovery/fetcher.py`, duplicated not imported), `_decode_bounded()` (reads the response in 64 KB chunks, aborting if it exceeds `MAX_RESPONSE_BYTES` = 5 MB — this is why the fetch is `stream=True`: without it the whole body would already be buffered before a size check could do anything), `_resolve_relative_urls()`, and `extract_content(url)`, the single public entry point for the standalone feature. Internally that's two composable halves, also exported: `fetch_and_prepare(url)` (fetch through resolving relative URLs, stops short of converting to Markdown, hands back the parsed `<body>`) and `render_markdown(body)` (the Markdown conversion alone). `extract_content()` just calls both back-to-back; `website_processing/pipeline.py` calls them separately, with its own cross-page shared-content pass running in between. |
| `browser.py` | Same two functions as `url_discovery/browser.py` (`should_render_with_browser`, `render_page_html`), but **single-shot** here — this feature only ever handles one URL per call, so there's no lifecycle to manage: launch Chromium, render, close, same shape as `tech_detection/browser.py`. |

**Why `markdownify` (full-page conversion) instead of `trafilatura`
(boilerplate-stripped "article" extraction):** an earlier version used
`trafilatura`'s content-density scoring to pick out just the "main"
article content, deliberately dropping nav/footer/aside as boilerplate.
That was itself a fix for an even earlier hand-rolled tag-search version
that missed disguised boilerplate (a newsletter CTA in a `<div
class="...aside...">`, not a real `<aside>` element). But a direct
comparison against another extraction tool's output on the same page
showed the `trafilatura` approach silently dropping content a caller
reasonably expects back when they ask to extract a page — its own nav
links, a hero image, footer links. `markdownify` converts the whole
`<body>`'s DOM structure directly, with no judgment call about what
counts as "real" content; `<script>`/`<style>` text is already excluded
by `markdownify` itself (it's code, not content), so nothing further
needs stripping first. This trades away the "no boilerplate" property
entirely, on purpose — see `README.md`'s Feature 2B section.

**Why title extraction stays separate from the body conversion:**
`soup.title` is read from whichever HTML ends up in play (raw, or
rendered if the browser fallback triggered), and the Markdown conversion
is scoped to `soup.body` specifically — `markdownify` has no notion of
`<head>` being non-content, so converting the whole document would leak
`<title>` text into `content_markdown` too, duplicating `title` above.

**Result contract (single-resource, not a batch — no `"partial"` state):**
`{status: "success"|"failed", url, title: str|None, content_markdown: str, error: str|None}`.

---

## Feature 2C: `website_processing/` — combined discover + extract

**What it does:** runs URL discovery, then runs content extraction on
every discovered URL — with a cross-page pass in between that detects and
strips nav/sidebar/footer content repeated across the crawl's own pages —
then derives one combined status. Owns **no** HTTP logic itself, and its
only DOM-level logic (`shared_content.py`) is specific to *comparing
already-parsed pages against each other*, not to parsing or fetching any
one of them.

| File | What it does |
|---|---|
| `pipeline.py` | `discover_and_extract(start_url, max_pages, max_depth)`. Calls `discover_urls()`; if that failed outright, short-circuits and returns immediately (no point extracting from zero URLs). Otherwise **prepares** every discovered URL **concurrently** — up to `MAX_CONCURRENT_EXTRACTIONS` (5) at once via `concurrent.futures.ThreadPoolExecutor` (chosen over `asyncio` specifically because `requests` is a blocking library; threads get real I/O overlap without rewriting the HTTP layer to `httpx`/async) — using `content_extraction.fetch_and_prepare()` rather than `extract_content()`: it stops short of converting to Markdown, handing back each page's parsed `<body>` instead. Those bodies go through `shared_content.find_shared_containers()`, matched signatures get stripped from each page via `remove_shared_containers()`, and only *then* does each page (and each detected shared container) get converted to Markdown via `content_extraction.render_markdown()`. `executor.map()` guarantees the result order matches `discovered_urls` order even though the underlying calls can complete in any order. The concurrency cap is deliberately small and fixed: every extraction targets the *same* site the crawl just hit, and `content_extraction`'s own per-call pacing is a per-call guarantee, not an aggregate-rate one — 5 concurrent calls means the site sees roughly 5 requests/second, not one. |
| `shared_content.py` | `find_shared_containers(bodies)` / `remove_shared_containers(body, signatures)` / `signature(container)`. Looks at every `<nav>`/`<aside>`/`<header>`/`<footer>` tag (`CANDIDATE_TAGS`) across all successfully-prepared pages, fingerprints each by its set of `(link text, href)` pairs (`signature()`), and groups fingerprints by **similarity** (Jaccard overlap ≥ `SIMILARITY_THRESHOLD`, 0.75), not exact equality — verified directly against lakshx.in that real nav/sidebar markup is rarely byte-identical across pages even when it's the same template (the current page's own link is often highlighted differently, or one extra page-specific link like a self-referential title is mixed in). A group counts as "shared" once it's matched on at least `MIN_OCCURRENCES` (2) pages, with `SHARED_CONTENT_THRESHOLD` (a low 0.1) as a secondary floor that only starts to matter on much larger crawls — an absolute minimum, not a percentage of the whole crawl, is what actually holds up in practice: a real site commonly runs several page *templates* at once (marketing/docs/legal sections each composing their header differently, confirmed against lakshx.in), so no single container is likely to hit a high percentage of a mixed-template crawl even when it's genuinely repeated chrome within its own section. |

**The status-combination rule** (the one genuinely tricky piece of logic in
this file):
- `failed` — discovery failed outright, **or** pages were discovered but
  *every single* extraction failed. (Ending up with zero usable content
  is worse than "partial" implies, so this takes priority over a
  merely-partial discovery.)
- `partial` — discovery was itself partial, **or** extraction results are
  a mix of success/failure.
- `success` — discovery succeeded **and** every extraction succeeded.

**Result contract:** `{status, start_url, discovery: <DiscoverResponse verbatim>, pages: [<ExtractResponse verbatim, with shared content already stripped>], shared_content_markdown: str}` — `discovery` and each page are the *actual* sub-feature results (minus whatever got detected as shared), not a re-derived summary. `shared_content_markdown` is `""` when nothing met the repetition bar (including every single-page crawl, which never runs this pass at all).

---

## `api/` — the FastAPI layer

**Rule that's enforced, not just described:** every route validates the
request via a Pydantic schema, calls straight into the feature's own entry
point, and returns whatever it got back unchanged. No route file ever
computes a confidence score, decides what a canonical URL is, or contains
any business logic — the one deliberate exception is **production-safety
bounds** on request parameters (capping `max_pages`, `timeout_seconds`),
which is a request-validation concern that belongs at the API boundary.

```
api/
├── main.py                      FastAPI() app, CORS (localhost:3000 only,
│                                 for the frontend), /health, includes all
│                                 four routers
├── routes/
│   ├── tech_detection.py         POST /detect-tech
│   ├── url_discovery.py          POST /discover-urls
│   ├── content_extraction.py     POST /extract-content
│   └── website_processing.py     POST /discover-and-extract
└── schemas/
    ├── tech_detection.py         DetectRequest / DetectResponse
    ├── url_discovery.py          DiscoverRequest / DiscoverResponse --
    │                              max_pages capped 1-100, timeout_seconds
    │                              capped 1-300, both non-nullable (the
    │                              library itself allows unbounded for
    │                              direct/CLI callers; the public endpoint
    │                              does not); path_specific_strip accepted
    │                              as {path: [params]} and converted to
    │                              sets before reaching discover_urls()
    ├── content_extraction.py     ExtractRequest / ExtractResponse
    └── website_processing.py     DiscoverAndExtractRequest / Response --
                                   reuses DiscoverResponse and
                                   ExtractResponse directly for its nested
                                   fields (not loose dicts), since
                                   discover_and_extract() literally stores
                                   those exact return values
```

`DetectResponse.technologies` is typed as `list[dict[str, Any]]`
deliberately, not a rigid model — direct and inferred entries have
different shapes, and deciding that shape is `tech_detection`'s job, not
the API layer's.

---

## `tests/` — how the suite is organized

- **Offline, default suite** (`uv run pytest tests/`): every feature's own
  folder (`tech_detection/`, `url_discovery/`, `content_extraction/`,
  `website_processing/`), plus `api/` (mocks each feature's entry point
  entirely — never exercises real crawling/extraction/detection logic).
  Fully synthetic, no real HTTP, no real browser — runs in a couple of
  seconds.
- **`tests/*/network/`** (`uv run pytest -m network`, excluded by default):
  real-site and real-Chromium checks. `tech_detection/network/` and
  `content_extraction/network/`/`url_discovery/network/` differ in one
  way: the latter two also spin up a tiny local `http.server` serving a
  genuinely bare SPA shell, because real-world investigation found that
  actual JS-heavy sites almost always carry enough server-rendered
  chrome (nav/header/footer text) to never trip the "visible text length"
  browser-fallback heuristic in the first place — a truly bare shell is
  hard to find and keep finding on the live internet, so serving one
  locally keeps the browser-render code path a real, repeatable check
  instead of hoping an external site stays shaped the right way.
- **`tests/fakes.py`** / **`tests/url_discovery/helpers.py`**: shared
  `FakeResponse`/`FakeSession`/`make_fake_get()` mocking helpers so
  individual test files don't each reinvent a fake HTTP layer.
- **Autouse fixtures**: both `test_content_extraction.py` and
  `test_crawler.py` have autouse pytest fixtures that patch
  `should_render_with_browser` to always return `False` by default —
  without this, the tiny HTML fixtures used throughout those files would
  trip the real heuristic and try to launch actual Chromium during the
  "offline" suite. Tests that specifically exercise the browser-fallback
  path override this patch locally.

---

## `frontend/` — the Next.js UI

Next.js 16 (App Router), TypeScript, Tailwind, shadcn/ui. One route per
feature, plus an overview page. Talks to the backend over plain `fetch` at
`NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8000`) — never
imports backend code.

```
frontend/src/
├── app/
│   ├── page.tsx                      Overview/landing page, links to all four
│   ├── layout.tsx                    Root layout: header, nav, theme provider,
│   │                                  backend health indicator, toast host
│   ├── tech-detection/page.tsx       Form -> POST /detect-tech -> result view
│   ├── url-discovery/page.tsx        Form -> POST /discover-urls -> result view
│   ├── content-extraction/page.tsx   Form -> POST /extract-content -> result view
│   └── discover-and-extract/page.tsx Form -> POST /discover-and-extract -> result view
├── components/
│   ├── nav.tsx                       Top nav with active-route highlighting
│   ├── backend-status.tsx            Polls /health every 15s, shows online/offline
│   ├── status-badge.tsx              Color-coded status/confidence badges
│   ├── theme-provider.tsx / theme-toggle.tsx   Light/dark mode (next-themes)
│   └── ui/*.tsx                      shadcn/ui primitives (button, card, tabs, ...)
└── lib/
    ├── api.ts                        Typed fetch client -- every interface here
    │                                  mirrors a backend/api/schemas/*.py model
    │                                  exactly (DetectResponse, DiscoverResponse,
    │                                  ExtractResponse, DiscoverAndExtractResponse,
    │                                  Technology as a discriminated union of
    │                                  DirectTechnology | InferredTechnology)
    └── utils.ts                      cn() className-merge helper (shadcn convention)
```

Each page follows the same shape: a form (URL + feature-specific params),
a loading state, a typed API call from `lib/api.ts`, and a result view
built from shared components (`StatusBadge`, `ConfidenceBadge`, accordions
for evidence/per-page content). Errors (network failure, 422 validation,
non-2xx) surface as toast notifications, never a blank screen.
