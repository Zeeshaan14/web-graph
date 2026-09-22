# web-graph

A website intelligence system built from scratch, mainly to learn the engineering
behind tools like Firecrawl/Wappalyzer rather than to copy their architecture.

The eventual goal: take a URL and (1) detect the technologies it's built with,
(2) discover its public URLs, and (3) extract their content. All three exist as
working V1s with API endpoints, plus a combined workflow that chains discovery
and extraction together:

| Feature | Status | Endpoint |
|---|---|---|
| Tech stack detection | V1 done | `POST /detect-tech` |
| URL discovery | V1 done | `POST /discover-urls` |
| Content extraction | V1 done | `POST /extract-content` |
| Discover + extract (combined) | V1 done | `POST /discover-and-extract` |
| Discover + extract (streaming) | V1 done | `POST /discover-and-extract/stream` |
| Frontend (Next.js) | V1 done | `frontend/` -- one page per feature |

"V1 done" means each one works end to end and is regression-tested — not that
nothing's left. See each feature's own section below for exactly what it does
and doesn't promise yet; nothing here should be assumed more complete than
what's actually written down.

The repo is split into two top-level folders: `backend/` (Python, FastAPI --
everything below) and `frontend/` (Next.js -- see [Frontend](#frontend-v1)).
They're independently run and independently versioned; the frontend only
talks to the backend over HTTP, never by importing it.

Within `backend/`, the project is organized by feature, not by generic
layers: `tech_detection/`, `url_discovery/`, and `content_extraction/` are
each self-contained, independent business logic — `website_processing/` sits
one level up and *composes* two of them (discovery + extraction) without
owning any HTTP/parsing logic itself. `api/` stays a thin layer that routes
to whichever feature (or composition) it's exposing, never a dumping ground
for logic from any of them.

## How it works

```
HTTP response
   |
   v
evidence extraction (headers, cookies, HTML, scripts, stylesheets, meta tags)
   |
   v
{ headers, cookies, html, scripts, stylesheets, meta }
   |
   v
generic fingerprint engine (rule groups: ANY / ALL logic, weighted scoring)
   |
   v
technology results (name, category, confidence score, confidence label, evidence)
```

Detection is data-driven: `fingerprints.py` holds pure data (which technology,
which signals, how much each is worth), and `engine.py` holds the generic logic
that evaluates any fingerprint against any evidence dict. The engine has no idea
what Cloudflare, Vercel, Next.js, or WordPress are — it just knows how to check
`exists` / `contains` / `equals` against a signal source.

The full pipeline is two-stage: a cheap HTTP fetch runs first, and a real
Playwright browser pass only happens if `fallback.py` decides the HTTP evidence
alone wasn't good enough (nothing detected, only weak "possible" confidence on
a technology that could actually benefit from a browser, or the page looks like
an unrendered SPA shell). An `inference.py` pass then adds technologies implied
by what was directly detected (e.g. Next.js implies React) without fabricating
evidence for them. `pipeline.py` wires all of this into one
`detect_website_technologies(url)` call that never raises — every outcome
(success, partial, failed) comes back as one predictable result shape.

### Evidence sources

- `header` / `cookie` — exact key lookup
- `html` — raw page text (last resort — easy to get false positives from)
- `script_src` — every `<script src="...">` on the page
- `stylesheet_href` — every `<link rel="stylesheet" href="...">` on the page
- `meta` — a `<meta name="..">` / `<meta property="..">` tag's `content`

### Rule groups: ANY vs ALL

Rules are grouped, and each group carries one weight, awarded once:

- **`any`** (OR) — satisfied if at least one rule in the group matches. Used when
  multiple rules are alternative ways of observing the *same* underlying signal
  (e.g. either Cloudflare edge header is independently strong evidence).
- **`all`** (AND) — satisfied only if every rule in the group matches; a partial
  match earns nothing. Used only when individual signals are genuinely too weak
  to stand alone — not just because a fingerprint happens to have multiple rules.

Confidence score is the sum of satisfied groups' weights, capped at 100, and
mapped to a label: `strong` (>=80), `likely` (>=60), `possible` (>=40), or not
detected at all below `MIN_DETECTION_SCORE` (40).

### What V1 actually supports

- 11 fingerprinted technologies across categories (CDN/hosting, frameworks,
  CMS/commerce, servers, analytics) — added deliberately as a stress test
  across categories, not for broad coverage
- Two-stage detection: cheap HTTP first, a real Playwright browser pass only
  when `fallback.py` decides HTTP evidence wasn't enough
- Inference for technologies implied but not directly observed (Next.js
  implies React), kept strictly separate from real evidence
- Structured `success` / `partial` / `failed` outcomes; `detect_website_technologies()`
  never raises
- Human-readable error messages, not a raw exception repr — a DNS failure
  (`requests`' own `NameResolutionError`/`getaddrinfo failed`) becomes
  `"Could not resolve '<url>' -- check the domain and try again."`, any
  other connection failure becomes `"Could not connect to '<url>'."`. The
  same classifier is duplicated (not imported) into `url_discovery/crawler.py`
  and `content_extraction/content_extraction.py`, matching this codebase's
  existing convention of keeping each feature package self-contained
- `POST /detect-tech`

### What V1 does *not* promise yet

- **Not comprehensive technology coverage** — 11 fingerprints is a deliberately
  small, varied sample, not an attempt to match a real fingerprint database's size.
- **Passive detection has real, known blind spots** — confirmed during
  development: modern bundled React is often invisible to passive fingerprinting
  even with a browser pass, since production builds frequently expose nothing
  identifiable on `window`.
- **Synchronous only** — same limitation as the other features below; a slow
  browser-fallback detection ties up the request for its full duration.

## Feature 2A: URL discovery (V1)

`url_discovery.crawler.discover_urls(url)` does a breadth-first crawl of a
single site starting from one URL and returns every public URL it found. Two
identities are tracked separately throughout, which is the core design idea
of this feature:

- **Traversal identity** (`visited_traversal`) — the actual final URL a
  request landed on, after following redirects. This is what decides whether
  a page gets fetched and its links extracted. `/articles/` and
  `/articles/page/2/` are different traversal URLs even if they end up
  reporting as the same page below.
- **Output identity** (`discovered_output`) — the preferred URL to *report*
  for a page: its traversal URL, unless the page declares a same-site
  `<link rel="canonical">`, in which case the canonical wins. A canonical tag
  can make several traversed pages collapse into one reported URL, but it
  **never stops traversal** — `/articles/page/2/` still gets fetched and
  parsed for links even though it reports as `/articles/`, because page 2
  can (and does, on real sites) link to pages page 1 never mentions.

### What V1 actually supports

- Same-site BFS discovery, bounded by `max_pages` and (optionally) `max_depth`
- Relative URL resolution (`../blog`, `#fragment`, protocol-relative, etc.)
- URL normalization: default ports, case-folding scheme/host, fragment
  stripping, known tracking-param removal (`utm_*`, `gclid`, `fbclid`, ...),
  and optional per-site/per-path noisy-param rules (`path_specific_strip`)
- Redirect handling — an internal URL redirecting off-site stops there and is
  never recorded or expanded; two different requested URLs redirecting to the
  same destination collapse into one traversal
- Canonical-based output dedup, without ever blocking traversal (see above)
- A politeness delay between every request, plus a `Retry-After`-aware retry
  (one retry) on `429`
- Content-type check before parsing — a non-HTML response (PDF, image, ...)
  is still traversed and reported in the output, but is never fed to the
  HTML canonical/link parser; a missing content-type header is treated as
  HTML (not skipped), since the failure mode of guessing wrong here is just
  a wasted parse, not a dropped page
- Structured `success` / `partial` / `failed` outcomes — a handful of broken
  pages inside an otherwise-working crawl is `partial`, not `failed`; nothing
  ever raises a raw exception out of `discover_urls()`
- A wall-clock timeout for the whole crawl (`timeout_seconds`), checked the
  same way `max_pages` is — before starting the next page, never by
  interrupting a fetch already in flight; `max_pages` alone bounds *how many*
  pages get fetched, not how long a slow site takes doing it
- `POST /discover-urls` — `max_pages` capped `1–100` and `timeout_seconds`
  capped `1–300` at the API layer (the library itself allows both unbounded
  for direct callers; the public endpoint does not), `max_depth` optional,
  `path_specific_strip` accepted as `{path: [params]}` and converted to sets
  before reaching `discover_urls()`
- `robots.txt` awareness — always on, not caller-toggled: fetched once per
  crawl (not counted toward `max_pages`/`pages_traversed`), checked against
  the `User-agent: *` group before every fetch, including the start URL.
  Mirrors Python's own `robotparser` convention for a bad fetch: `401`/`403`
  blocks the whole crawl, anything else (`404`, connection failure, ...)
  means nothing is disallowed
- `sitemap.xml` support — one sitemap (the first one `robots.txt` declares
  via `Sitemap:`, or the conventional `/sitemap.xml` if it declares none) is
  fetched once and its URLs seeded into the crawl at depth 0, same-site-
  filtered like any other URL. Deliberately scoped to a single, non-index
  sitemap file — a `<sitemapindex>` pointing at several child sitemaps is
  not followed. A missing or unparseable sitemap just means nothing extra
  to seed, never a crawl failure
- Same-site scope treats a leading `www.` as a cosmetic alias — `www.site.com`
  and `site.com` count as the same site for redirects, canonicals, and link
  filtering. No broader subdomain match is assumed: `blog.site.com` and
  `site.com` are still treated as different sites, since that's genuinely
  ambiguous and a generic crawler shouldn't guess
- A Playwright browser fallback for JS-rendered links, mirroring
  `tech_detection`'s HTTP-then-browser split (`url_discovery/browser.py`):
  per page, not per crawl — a page's raw HTML is checked with the same
  "visible text length" heuristic `tech_detection/fallback.py` already
  calibrated (little to no visible text is a proxy for an unrendered app
  shell), and only pages that trip it get rendered. Unlike `tech_detection`
  (one page, one possible browser launch), a crawl can visit many pages, so
  this adds real lifecycle management the single-page version never needed:
  one Chromium instance launched lazily and reused across every page in the
  crawl that needs it (not relaunched per page), a hard cap
  (`MAX_BROWSER_RENDERS_PER_CRAWL = 10`, not caller-configurable in V1) on
  how many pages get rendered in one crawl, and graceful degradation at two
  levels — a single page's render failing falls back to that page's raw
  HTML, and the initial browser launch itself failing disables rendering
  for the rest of that crawl rather than retrying (and re-failing) on every
  subsequent page. Verified against a real, locally-served bare SPA shell
  (`tests/url_discovery/network/`): 1 page found with rendering off, all 3
  (including two links that exist only after its JS runs) with it on.
  Real-world finding, documented honestly: today's actual SPA-shell sites
  almost always carry enough server-rendered chrome (nav/header/footer
  text) to sit above the heuristic's threshold even when their real content
  is JS-rendered — a genuinely bare shell is hard to find on the live
  internet now, which is exactly why the regression test serves its own
  fixture rather than depending on one

### What V1 does *not* promise yet

- **Content extraction is a separate feature, not built into this one** —
  `discover_urls()` only returns URLs; reading the content at each one is
  `content_extraction/` (below), wired together by `website_processing/`.
- **The browser fallback only catches a fully unrendered shell, not a
  hybrid page** — real chrome (nav/header/footer) with JS-rendered *main*
  content sits above the visible-text threshold and never triggers a
  render, even though its real links are still JS-only. See the supports
  section above for why this is an inherited, honestly-documented
  limitation of the heuristic, not new to this feature.
- **Synchronous only** — a crawl runs inline within one HTTP request; there's
  no background-job/poll pattern yet (see the API section below for why that
  matters for production).

## Feature 2B: Content extraction (V1)

`content_extraction.content_extraction.extract_content(url)` fetches one URL
and converts its whole `<body>` to Markdown. Unlike the other two features,
this is a single-resource result, not a batch — so its contract is a plain
`{status: "success" | "failed", url, title, content_markdown, error}` with no
`"partial"` state and a single nullable `error` field rather than a list.

### What V1 actually supports

- Full-page HTML-to-Markdown conversion via
  [`markdownify`](https://github.com/matthewwithanm/python-markdownify) —
  not density-scored "main content" picking. Nav links, footer links,
  images, and real inline formatting (bold/italic/links) all come through,
  in document order; only `<script>`/`<style>` text is excluded, since
  that's code, not content. This replaced an earlier `trafilatura`-based
  "article extractor" that deliberately stripped boilerplate — a direct
  comparison against another extraction tool showed that approach silently
  dropping a page's own nav, hero image, and footer links, which is real
  content a caller who asked to extract a page would reasonably expect back
- Relative `<a href>`/`<img src>` are resolved to absolute URLs before
  conversion — a downloaded/standalone `.md` file has no page context left
  to resolve `/docs` against once it's out of the DOM
- Title still comes straight from the raw HTML `<title>` tag, independent of
  the body conversion, and scoped out of `content_markdown` itself (which is
  built from `<body>` only) so it isn't duplicated
- A browser-shaped request (headers alone got us past a real `403` on
  `realpython.com` during development) — kept as its own local copy rather
  than importing `url_discovery/fetcher.py`, so the two features stay
  independent of each other
- Content-type check before parsing — a non-HTML response (confirmed against
  a real image URL) returns `"failed"` with a clear error instead of trying
  to soup-parse binary data
- A response-size cap (5 MB) enforced while streaming, not just trusted from
  a `Content-Length` header — a response that's larger than declared, or
  served with no `Content-Length` at all, is still caught and stopped mid-
  download rather than fully buffered into memory first
- A politeness delay and `Retry-After`-aware `429` retry (one retry) around
  every fetch this module makes — its own local copy of the same policy
  `url_discovery/fetcher.py` applies, so a standalone `/extract-content`
  call and every call made during the combined workflow both get it
- A Playwright browser fallback for JS-rendered content, mirroring
  `tech_detection`'s HTTP-then-browser split and `url_discovery`'s own
  per-page version (`content_extraction/browser.py`): the same "visible
  text length" heuristic decides if the raw HTML looks like an unrendered
  app shell, and if so the rendered page **replaces** it entirely —
  including for title extraction, not just body content, since an SPA
  shell's static `<title>` is often a generic placeholder set for real only
  after JS runs. Simpler than `url_discovery`'s version: this feature
  handles one URL per call, so there's no crawl-spanning lifecycle to
  manage — launch Chromium, render, close, same single-shot shape as
  `tech_detection/browser.py`. A render failure falls back to the raw HTML
  rather than failing the request. Verified against a real, locally-served
  bare SPA shell (`tests/content_extraction/network/`): `"Loading..."` /
  no content with rendering off, the real rendered title/heading/paragraph
  with it on
- `POST /extract-content`

### What V1 does *not* promise yet

- **No boilerplate filtering at all, by design** — a link-grid index page,
  a docs landing page, a listing page: all convert in full now, nav and
  footer included, which is the whole point of this approach. The
  trade-off runs the other way from before: a caller who specifically
  wants just an article's prose, with chrome stripped out, doesn't get
  that here — they get the whole page, same as viewing "page source" but
  as Markdown instead of raw HTML.
- **The browser fallback only catches a fully unrendered shell, not a
  hybrid page** — same inherited heuristic limitation as `url_discovery`'s
  version: real chrome (nav/header/footer) with JS-rendered *main* content
  sits above the visible-text threshold and never triggers a render, even
  though the real content is still JS-only.

## Feature 2C: Discover + extract (combined workflow, V1)

`website_processing.pipeline.discover_and_extract(url)` chains the two
features above: run discovery, then run extraction on every discovered URL,
then derive one combined status from both stages. It owns no HTTP or parsing
logic itself — just orchestration and status combination.

### What V1 actually supports

- Combined `{status, start_url, discovery, pages}` contract — `discovery` and
  `pages` are the *actual* `discover_urls()`/`extract_content()` results,
  not a re-derived summary
- A three-way status rule that accounts for **both** stages, not just
  extraction:
  - `failed` — discovery failed outright, **or** pages were discovered but
    every single extraction failed (this takes priority over a merely-partial
    discovery — ending up with zero usable content is worse than "partial" implies)
  - `partial` — discovery was itself partial, **or** extraction results are mixed
  - `success` — discovery succeeded **and** every extraction succeeded
- Pacing/retry during the extraction phase — closed at its source:
  `extract_content()` itself now paces and retries every fetch it makes
  (see Feature 2B above), so this phase gets the same protection the crawl
  phase always had, without `website_processing` needing to know anything
  about HTTP
- Bounded parallel extraction — up to 5 pages extracted at once
  (`MAX_CONCURRENT_EXTRACTIONS` in `website_processing/pipeline.py`) via a
  `ThreadPoolExecutor`, instead of one at a time. Deliberately a small,
  fixed ceiling, not "as many as there are pages": every extraction targets
  the *same* site the crawl just finished hitting, and `extract_content()`'s
  own per-call pacing is a per-call guarantee, not an aggregate-rate one --
  running `N` of them at once means the site sees roughly `N` requests per
  second, not one. Output order still matches `discovered_urls` order
  regardless of which extraction finishes first
- Cross-page shared-content dedup (`website_processing/shared_content.py`)
  — nav bars, sidebars, and footers repeated across a site's own pages are
  detected and pulled out once, into a new `shared_content_markdown`
  field, instead of duplicated verbatim on every single page. This exists
  for feeding a crawl's output into a RAG pipeline, where the same
  boilerplate chunk showing up in every document is pure noise. Built on
  an observed-repetition signal, not a per-page guess (the thing
  Feature 2B's own extraction strategy deliberately moved away from, see
  above): a `<nav>`/`<aside>`/`<header>`/`<footer>` is only ever removed
  because it was seen matching on *multiple other pages of the same
  crawl*, never because of how it looks in isolation. Matching is by link
  overlap (which places a container points to), not exact HTML/text
  equality — verified directly against lakshx.in, where the same sidebar
  is rarely byte-identical across pages (the current page's own entry is
  usually highlighted differently). A crawl needs at least 2 successfully
  extracted pages before this runs at all; a single-page crawl is never
  touched
- `POST /discover-and-extract`
- `POST /discover-and-extract/stream` — the same workflow, as newline-
  delimited JSON (one `{"event": ..., ...}` object per line) instead of one
  final response. `discover_and_extract_stream()` wraps `discover_urls_stream()`
  and `extract_content()`'s per-page work as a generator, so a caller sees
  progress as it actually happens rather than one blocking wait:
  `discovery_started` -> a `url_discovered` event for each URL the crawl
  finds (not batched until the crawl finishes) -> `discovery_done` -> a
  `page_fetched` event per page as extraction completes it -> `dedup_done`
  once shared-content removal runs -> a `page_rendered` event per page's
  final Markdown -> `complete` with the same result shape
  `/discover-and-extract` returns non-streamed. `/discover-and-extract`
  itself is a thin wrapper that exhausts the same generator for its
  `complete` event — one implementation, two ways to consume it. This is
  what the frontend's Discover + Extract page actually uses (see Frontend
  section below); the plain endpoint still exists for callers that just
  want the final result in one response.

### What V1 does *not* promise yet

- Inherits every "not yet" item listed above for discovery and extraction
  individually — this feature doesn't paper over either one's gaps.
- Shared-content detection only looks at real `<nav>`/`<aside>`/`<header>`/
  `<footer>` landmark tags, not a link-density guess over arbitrary `<div>`s
  -- a site whose sidebar is a bare, unmarked `<div>` won't be caught.
  Deliberate: a link-density heuristic over arbitrary elements is exactly
  the kind of per-page guessing this project moved away from elsewhere.

## Folder structure

```
web-graph/
├── backend/                   # Python / FastAPI -- everything below is run from here
│   ├── api/                       # thin FastAPI layer -- validate, call feature, return
│   │   ├── main.py                #   FastAPI() app + /health, includes all four routers
│   │   ├── routes/
│   │   │   ├── tech_detection.py   #   POST /detect-tech
│   │   │   ├── url_discovery.py    #   POST /discover-urls
│   │   │   ├── content_extraction.py #  POST /extract-content
│   │   │   └── website_processing.py # POST /discover-and-extract
│   │   └── schemas/
│   │       ├── tech_detection.py   #   request/response models per feature, no logic
│   │       ├── url_discovery.py    #   also where production safety caps live
│   │       │                        #   (max_pages/max_depth bounds)
│   │       ├── content_extraction.py
│   │       └── website_processing.py # reuses url_discovery's + content_extraction's
│   │                                  # own response models for its nested fields
│   │
│   ├── tech_detection/            # feature 1: all detection business logic
│   │   ├── pipeline.py             #   orchestrates the two-stage flow end to end
│   │   ├── fetcher.py               #   HTTP fetching only
│   │   ├── evidence.py              #   HTML parsing + evidence-dict construction, merge_evidence()
│   │   ├── browser.py               #   Playwright browser evidence collector
│   │   ├── fallback.py              #   HTTP-alone-enough? decision
│   │   ├── engine.py                #   generic fingerprint rule evaluator/scorer
│   │   ├── fingerprints.py          #   the fingerprint definitions (11 technologies)
│   │   ├── relationships.py         #   what a direct detection implies (Next.js -> React)
│   │   └── inference.py             #   applies relationships.py, keeps evidence separate
│   │
│   ├── url_discovery/              # feature 2A: crawls a site for its public URLs
│   │   ├── crawler.py               #   crawl() = BFS traversal engine; discover_urls() =
│   │   │                             #   feature contract + safety boundary around it
│   │   ├── fetcher.py               #   browser-shaped session, pacing, 429 retry
│   │   ├── link_extraction.py       #   normalize_url(), extract_links(), extract_canonical()
│   │   └── browser.py               #   Playwright fallback -- render + should-render heuristic;
│   │                                 #   crawler.py owns the browser's LIFECYCLE across the crawl
│   │
│   ├── content_extraction/         # feature 2B: converts one URL's title + full body to Markdown
│   │   ├── content_extraction.py    #   extract_content() -- single file, single-resource contract
│   │   └── browser.py               #   Playwright fallback -- single-shot (one URL per call,
│   │                                 #   unlike url_discovery, so no lifecycle to manage)
│   │
│   ├── website_processing/         # feature 2C: composes 2A + 2B, owns no HTTP/parsing itself
│   │   └── pipeline.py               #   discover_and_extract() -- combined status derivation
│   │
│   ├── cli.py                     # local CLI entry point (prints to terminal)
│   ├── pyproject.toml             # backend deps + pytest config (uv-managed)
│   ├── uv.lock
│   │
│   ├── tests/
│   │   ├── api/                    # API-layer tests -- each feature's entry point is mocked
│   │   ├── tech_detection/         # offline regression suite for the detection logic
│   │   │   └── network/            #   real-site/real-browser checks (marked, opt-in)
│   │   ├── url_discovery/          # offline regression suite for the crawler
│   │   │   └── network/            #   + a locally-served bare-SPA-shell browser check
│   │   ├── content_extraction/     # offline regression suite for content extraction
│   │   │   └── network/            #   + a locally-served bare-SPA-shell browser check
│   │   ├── website_processing/     # offline regression suite for the combined workflow
│   │   └── fakes.py                # shared FakeResponse/FakeSession test helpers
│   │
│   └── testing/                   # manual dev-inspection tools, not regression tests
│       ├── test.py                 #   dump raw scripts/stylesheets/meta for a URL
│       └── playwright-test.py       #   standalone Playwright prototype/reference
│
└── frontend/                  # Next.js UI -- see Frontend section below
    └── src/app/*/page.tsx         # one route per feature, thin client over the API
```

`api/` never contains business logic — every route validates the request via a
Pydantic schema, calls straight into the feature's own entry point
(`tech_detection.pipeline.detect_website_technologies` /
`url_discovery.crawler.discover_urls` / `content_extraction.content_extraction.extract_content`
/ `website_processing.pipeline.discover_and_extract`), and returns whatever it
got back unchanged. Nothing in `api/` should ever need to know a confidence
score, a fingerprint, or what a canonical URL is — the one exception is
production-safety *bounds* on request parameters (e.g. capping `max_pages`),
which is a request-validation concern and belongs at the API boundary, not
inside the crawler itself.

## Frontend (V1)

`frontend/` is a Next.js (App Router, TypeScript, Tailwind, shadcn/ui) app
with one page per feature -- Tech Detection, URL Discovery, Content
Extraction, Discover + Extract -- plus an overview/landing page. Each page is
a thin client over the matching API endpoint: a form, a typed fetch call
(`frontend/src/lib/api.ts`, whose types mirror `backend/api/schemas/*.py`
exactly),
and a result view built from shadcn components (status/confidence badges,
accordions for evidence and per-page extracted content, tables/lists for
discovered URLs). It supports light/dark mode and shows a live backend
health indicator in the header.

It talks to the backend over plain `fetch` at `NEXT_PUBLIC_API_BASE_URL`
(defaults to `http://127.0.0.1:8000`, see `frontend/.env.local.example`), so
the FastAPI app needs `CORSMiddleware` enabled for `localhost:3000` -- see
`backend/api/main.py`. This is a local-dev CORS policy only, not a
deployed-service one.

**What V1 actually supports:** all four workflows end to end against real
sites, loading/error states (network failure, validation errors, non-2xx
responses) surfaced as toasts, and a responsive layout down to phone width.
The Discover + Extract page specifically drives `/discover-and-extract/stream`
(`frontend/src/lib/api.ts`'s `discoverAndExtractStream()` -- `fetch()` +
`ReadableStream` reader, manually line-buffered across chunk boundaries) and
renders each URL, page, and the dedup pass as it actually streams in, instead
of a single spinner-then-everything-at-once wait. Every URL field across all
four pages also accepts a bare domain (`lakshx.in`, not just
`https://lakshx.in`) or a partial scheme (`www.example.com`) --
`frontend/src/lib/url.ts`'s `normalizeUrlInput()` adds `https://` before the
request goes out, so the native `type="url"` input (which rejects anything
without a scheme at the browser level) had to be swapped for `type="text"` +
`inputMode="url"` everywhere a URL is entered.

**What V1 does *not* promise yet:** no auth, no persistence of past
results (a refresh loses them), and no automated frontend tests -- it was
verified with a live smoke test against a real site instead.

## Running it

```bash
cd backend
uv run cli.py                          # CLI: detect technologies on the two live test sites
uv run uvicorn api.main:app --reload   # API: serve on http://127.0.0.1:8000
uv run testing/test.py                 # dump raw scripts/stylesheets/meta for a URL

cd ../frontend && npm run dev          # Frontend: serve on http://localhost:3000
```

All `uv run` commands assume `backend/` as the working directory -- that's
where `pyproject.toml` and `uv.lock` live, so `uv` resolves and runs against
that virtualenv specifically, not the frontend's Node one.

```bash
curl -X POST http://127.0.0.1:8000/detect-tech \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lakshx.in/"}'

curl -X POST http://127.0.0.1:8000/discover-urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.python.org/3/tutorial/", "max_pages": 20, "max_depth": 2}'

curl -X POST http://127.0.0.1:8000/extract-content \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lakshx.in/"}'

curl -X POST http://127.0.0.1:8000/discover-and-extract \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lakshx.in/", "max_pages": 5}'
```

A `"failed"` or `"partial"` result (bad URL, DNS failure, Playwright timeout, a
handful of broken pages mid-crawl) still comes back as a normal `200` with a
structured body — it's a valid result, not a server error. See
`tech_detection/pipeline.py`'s and `url_discovery/crawler.py`'s module
docstrings for the full result-shape contracts.

`max_pages` for `/discover-urls` is capped at 100 and cannot be omitted-as-null
at the API layer, even though `url_discovery.crawler.discover_urls()` itself
allows an unbounded crawl for direct/CLI callers — a public endpoint must not
let a caller request an effectively unlimited crawl, since with the crawler's
~1s politeness delay per page that ties up a synchronous request for a very
long time.

## Testing

```bash
cd backend
uv run pytest tests/              # fast offline regression suite (no network)
uv run pytest tests/ -m network   # + real sites and a real Chromium launch
```

The offline suite (`tests/tech_detection/*.py`, `tests/url_discovery/*.py`,
`tests/content_extraction/*.py`, `tests/website_processing/*.py`,
`tests/api/*.py`) is fully synthetic — no HTTP, no browser — so it runs in well
under a second and is what should catch a regression (a broken fingerprint, a
fallback miscalculation, a crawler traversal bug, an extraction parsing bug, a
combined-status derivation bug, an API wiring bug) before it ships.
`tests/tech_detection/network/`, `tests/url_discovery/network/`, and
`tests/content_extraction/network/` each hold a small set of real-site/
real-browser checks, excluded by default, for occasionally confirming the
whole system still works against the live internet. The two newer ones also
each serve their own minimal SPA shell locally to verify the browser-fallback
render path stays exercised as a real, repeatable check — real-world SPA
shells were found to almost always carry enough server-rendered chrome to
never trip the fallback heuristic in the first place, so depending on one
external site to keep proving the mechanism works wasn't reliable.
