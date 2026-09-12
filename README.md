# web-graph

A website intelligence system built from scratch, mainly to learn the engineering
behind tools like Firecrawl/Wappalyzer rather than to copy their architecture.

The eventual goal: take a URL and (1) detect the technologies it's built with, and
(2) discover its public URLs and extract their content. Right now, only the first
piece — **tech stack detection** — is being built.

The project is organized by feature, not by generic layers: `tech_detection/` is
the first feature's business logic, complete and independent. When feature 2
(URL discovery + content extraction) starts, it becomes its own sibling package
(e.g. `url_discovery/`) — `api/` stays a thin layer that routes to whichever
feature it's exposing, never a dumping ground for logic from either one.

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

## Folder structure

```
web-graph/
├── api/                       # thin FastAPI layer -- validate, call pipeline, return
│   ├── main.py                #   FastAPI() app + /health
│   ├── routes.py               #   POST /detect-tech
│   └── schemas.py              #   request/response models only, no logic
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
├── cli.py                     # local CLI entry point (prints to terminal)
│
├── tests/
│   ├── api/                    # API-layer tests -- pipeline is mocked entirely
│   ├── tech_detection/         # offline regression suite for the detection logic
│   │   └── network/            #   real-site/real-browser checks (marked, opt-in)
│   └── fakes.py                # shared FakeResponse/FakeSession test helpers
│
└── testing/                   # manual dev-inspection tools, not regression tests
    ├── test.py                 #   dump raw scripts/stylesheets/meta for a URL
    └── playwright-test.py       #   standalone Playwright prototype/reference
```

`api/` never contains detection logic — every route validates the request via a
Pydantic schema, calls straight into `tech_detection.pipeline`, and returns
whatever it got back unchanged. Nothing in `api/` should ever need to know a
confidence score, a fingerprint, or what "possible" means.

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
```

A `"failed"` or `"partial"` detection (bad URL, DNS failure, Playwright timeout)
still comes back as a normal `200` with a structured body — it's a valid result,
not a server error. See `tech_detection/pipeline.py`'s module docstring for the
full result-shape contract.

## Testing

```bash
uv run pytest tests/              # fast offline regression suite (no network)
uv run pytest tests/ -m network   # + real sites and a real Chromium launch
```

The offline suite (`tests/tech_detection/*.py`, `tests/api/*.py`) is fully
synthetic — no HTTP, no browser — so it runs in well under a second and is what
should catch a regression (a broken fingerprint, a fallback miscalculation, a
pipeline or API wiring bug) before it ships. `tests/tech_detection/network/`
holds a small set of real-site/real-browser checks, excluded by default, for
occasionally confirming the whole system still works against the live internet.
