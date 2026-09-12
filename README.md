# web-graph

A website intelligence system built from scratch, mainly to learn the engineering
behind tools like Firecrawl/Wappalyzer rather than to copy their architecture.

The eventual goal: take a URL and (1) detect the technologies it's built with, and
(2) discover its public URLs and extract their content. Right now, only the first
piece — **tech stack detection** — is being built.

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
that evaluates any fingerprint against any HTTP response. The engine has no idea
what Cloudflare, Vercel, Next.js, or WordPress are — it just knows how to check
`exists` / `contains` / `equals` against a signal source.

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

## Files

- `main.py` — fetches a URL and prints its detected technologies.
- `engine.py` — the generic rule evaluator and scorer (no technology-specific logic).
- `fingerprints.py` — the fingerprint definitions (Cloudflare, Vercel, Next.js, WordPress).
- `html_signals.py` — parses HTML into structured signals (scripts, stylesheets, meta tags).
- `test.py` — CLI tool to inspect a URL's raw structured HTML signals.
- `test_matrix.py` — offline test matrix (no HTTP requests) that exercises every
  fingerprint's strong/partial/none cases directly against synthetic contexts.

## Running it

```bash
uv run main.py          # detect technologies on the two live test sites
uv run test.py           # dump raw scripts/stylesheets/meta for a URL
uv run test_matrix.py     # run the offline fingerprint test matrix
```
