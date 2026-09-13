# web-graph

A website intelligence system built from scratch, mainly to learn the engineering
behind tools like Firecrawl/Wappalyzer rather than to copy their architecture.

The eventual goal: take a URL and (1) detect the technologies it's built with, and
(2) discover its public URLs and extract their content. Both are underway:
**tech stack detection** (`tech_detection/`) is done through the API; **URL
discovery** (`url_discovery/`) has its crawler and API route, with content
extraction from those discovered URLs still to come.

The project is organized by feature, not by generic layers: `tech_detection/`
and `url_discovery/` are each self-contained, independent business logic —
`api/` stays a thin layer that routes to whichever feature it's exposing
(`api/routes/tech_detection.py`, `api/routes/url_discovery.py`), never a
dumping ground for logic from either one.

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

## Feature 2: URL discovery (V1)

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
- Structured `success` / `partial` / `failed` outcomes — a handful of broken
  pages inside an otherwise-working crawl is `partial`, not `failed`; nothing
  ever raises a raw exception out of `discover_urls()`
- `POST /discover-urls` — `max_pages` capped `1–100` at the API layer (the
  library itself allows unbounded for direct callers; the public endpoint
  does not), `max_depth` optional

### What V1 does *not* promise yet

- **No content extraction** — this discovers URLs only; reading the content
  at each URL is the next planned piece of this feature, not built yet.
- **No JavaScript-rendered links** — pure static-HTML `<a href>` parsing, no
  browser rendering step (unlike `tech_detection`, this feature has no
  Playwright fallback). Links only added to the DOM by client-side JS will
  not be discovered.
- **No `robots.txt` or `sitemap.xml` awareness** — the crawler doesn't check
  either; it discovers purely by following on-page links.
- **No content-type check before parsing** — a link to a PDF/image would be
  fed to the HTML link extractor as-is (likely yields no links, but wastes a
  request); `tech_detection`'s evidence pipeline does this check, this one
  doesn't yet.
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

## Folder structure

```
web-graph/
├── api/                       # thin FastAPI layer -- validate, call feature, return
│   ├── main.py                #   FastAPI() app + /health, includes both routers
│   ├── routes/
│   │   ├── tech_detection.py   #   POST /detect-tech
│   │   └── url_discovery.py    #   POST /discover-urls
│   └── schemas/
│       ├── tech_detection.py   #   request/response models for feature 1, no logic
│       └── url_discovery.py    #   same for feature 2 -- also where production
│                                #   safety caps (max_pages/max_depth bounds) live
│
├── tech_detection/            # feature 1: all detection business logic
│   ├── pipeline.py             #   orchestrates the two-stage flow end to end
│   ├── fetcher.py               #   HTTP fetching only
│   ├── evidence.py              #   HTML parsing + evidence-dict construction, merge_evidence()
│   ├── browser.py               #   Playwright browser evidence collector
│   ├── fallback.py              #   HTTP-alone-enough? decision
│   ├── engine.py                #   generic fingerprint rule evaluator/scorer
│   ├── fingerprints.py          #   the fingerprint definitions (11 technologies)
│   ├── relationships.py         #   what a direct detection implies (Next.js -> React)
│   └── inference.py             #   applies relationships.py, keeps evidence separate
│
├── url_discovery/              # feature 2: crawls a site for its public URLs
│   ├── crawler.py               #   crawl() = BFS traversal engine; discover_urls() =
│   │                             #   feature contract + safety boundary around it
│   ├── fetcher.py               #   browser-shaped session, pacing, 429 retry
│   └── link_extraction.py       #   normalize_url(), extract_links(), extract_canonical()
│
├── cli.py                     # local CLI entry point (prints to terminal)
│
├── tests/
│   ├── api/                    # API-layer tests -- each feature's entry point is mocked
│   ├── tech_detection/         # offline regression suite for the detection logic
│   │   └── network/            #   real-site/real-browser checks (marked, opt-in)
│   ├── url_discovery/          # offline regression suite for the crawler
│   └── fakes.py                # shared FakeResponse/FakeSession test helpers
│
└── testing/                   # manual dev-inspection tools, not regression tests
    ├── test.py                 #   dump raw scripts/stylesheets/meta for a URL
    └── playwright-test.py       #   standalone Playwright prototype/reference
```

`api/` never contains business logic — every route validates the request via a
Pydantic schema, calls straight into the feature's own entry point
(`tech_detection.pipeline.detect_website_technologies` /
`url_discovery.crawler.discover_urls`), and returns whatever it got back
unchanged. Nothing in `api/` should ever need to know a confidence score, a
fingerprint, or what a canonical URL is — the one exception is production-safety
*bounds* on request parameters (e.g. capping `max_pages`), which is a
request-validation concern and belongs at the API boundary, not inside the
crawler itself.

## Running it

```bash
uv run cli.py                          # CLI: detect technologies on the two live test sites
uv run uvicorn api.main:app --reload   # API: serve on http://127.0.0.1:8000
uv run testing/test.py                 # dump raw scripts/stylesheets/meta for a URL
```

```bash
curl -X POST http://127.0.0.1:8000/detect-tech \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lakshx.in/"}'

curl -X POST http://127.0.0.1:8000/discover-urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.python.org/3/tutorial/", "max_pages": 20, "max_depth": 2}'
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
uv run pytest tests/              # fast offline regression suite (no network)
uv run pytest tests/ -m network   # + real sites and a real Chromium launch
```

The offline suite (`tests/tech_detection/*.py`, `tests/url_discovery/*.py`,
`tests/api/*.py`) is fully synthetic — no HTTP, no browser — so it runs in well
under a second and is what should catch a regression (a broken fingerprint, a
fallback miscalculation, a crawler traversal bug, an API wiring bug) before it
ships. `tests/tech_detection/network/` holds a small set of real-site/real-browser
checks, excluded by default, for occasionally confirming the whole system still
works against the live internet.
