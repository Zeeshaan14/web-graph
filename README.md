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
- `POST /discover-urls` — `max_pages` capped `1–100` at the API layer (the
  library itself allows unbounded for direct callers; the public endpoint
  does not), `max_depth` optional

### What V1 does *not* promise yet

- **Content extraction is a separate feature, not built into this one** —
  `discover_urls()` only returns URLs; reading the content at each one is
  `content_extraction/` (below), wired together by `website_processing/`.
- **No JavaScript-rendered links** — pure static-HTML `<a href>` parsing, no
  browser rendering step (unlike `tech_detection`, this feature has no
  Playwright fallback). Links only added to the DOM by client-side JS will
  not be discovered.
- **No `robots.txt` or `sitemap.xml` awareness** — the crawler doesn't check
  either; it discovers purely by following on-page links.
- **No `path_specific_strip` via the API** — the noisy-query-param override
  exists in `discover_urls()`/`crawl()` for direct/CLI callers only; the
  public `/discover-urls` endpoint has no field for it yet.
- **Subdomains are treated as different domains** — scope is an exact
  hostname match against the start URL, so `www.site.com` and `site.com`
  (or any other subdomain) are never treated as the same site, even if a
  real visitor would consider them one.
- **No wall-clock timeout** — bounded by page count and depth only; a slow
  site can still take a long time within that budget.
- **Synchronous only** — a crawl runs inline within one HTTP request; there's
  no background-job/poll pattern yet (see the API section below for why that
  matters for production).

## Feature 2B: Content extraction (V1)

`content_extraction.content_extraction.extract_content(url)` fetches one URL
and pulls out its title, headings (`h1`–`h3`), and paragraph text. Unlike the
other two features, this is a single-resource result, not a batch — so its
contract is a plain `{status: "success" | "failed", url, title, headings,
paragraphs, error}` with no `"partial"` state and a single nullable `error`
field rather than a list.

### What V1 actually supports

- `article` > `main` > whole-page fallback for where to look for content
- Boilerplate stripping: `script`/`style`/`noscript`/`nav`/`footer`/`aside`
  removed before extraction
- A browser-shaped request (headers alone got us past a real `403` on
  `realpython.com` during development) — kept as its own local copy rather
  than importing `url_discovery/fetcher.py`, so the two features stay
  independent of each other
- Content-type check before parsing — a non-HTML response (confirmed against
  a real image URL) returns `"failed"` with a clear error instead of trying
  to soup-parse binary data
- `POST /extract-content`

### What V1 does *not* promise yet

- **No generic boilerplate/ad/widget removal beyond semantic HTML tags** —
  confirmed directly during development: a real newsletter-signup CTA on
  Smashing Magazine survived extraction because it's a `<div>` with "aside"
  only in a CSS class name, not an actual `<aside>` element, nested inside
  the article itself. Catching that reliably needs a much more involved
  approach (what tools like Readability.js/trafilatura exist for) — not
  attempted here.
- **Only the first `<article>`/`<main>` is used** — a listing/index page with
  multiple article previews would extract just the first one, not all of them.
- **No response-size limit** — a very large page is downloaded and parsed in
  full; no streaming or size cap.
- **No JavaScript-rendered content** — same limitation as URL discovery, pure
  static HTML only.

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
- `POST /discover-and-extract`

### What V1 does *not* promise yet

- **No pacing/retry during the extraction phase** — `discover_urls()` has a
  politeness delay and `429` retry built in for the *crawl*; once discovery
  finishes, `extract_content()` is called once per URL back-to-back with
  none of that protection. A real crawl feeding many URLs into extraction
  from the same site could get itself rate-limited during that phase with
  nothing to recover.
- **No parallelism** — pages are extracted one at a time, sequentially; a
  20-page combined request means 20 sequential extraction fetches on top of
  the crawl itself.
- Inherits every "not yet" item listed above for discovery and extraction
  individually — this feature doesn't paper over either one's gaps.

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
│   │   └── link_extraction.py       #   normalize_url(), extract_links(), extract_canonical()
│   │
│   ├── content_extraction/         # feature 2B: pulls title/headings/paragraphs from one URL
│   │   └── content_extraction.py    #   extract_content() -- single file, single-resource contract
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
│   │   ├── content_extraction/     # offline regression suite for content extraction
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

**What V1 does *not* promise yet:** no auth, no persistence of past
results (a refresh loses them), no polling/streaming for the slower
discover-and-extract workflow (the request just blocks until it's done), and
no automated frontend tests -- it was verified with a live smoke test against
a real site instead.

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
`tests/tech_detection/network/` holds a small set of real-site/real-browser
checks, excluded by default, for occasionally confirming the whole system still
works against the live internet.
