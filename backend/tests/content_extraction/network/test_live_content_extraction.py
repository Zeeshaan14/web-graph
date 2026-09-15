# Real end-to-end checks: a real site fetch, and a real Chromium launch
# against a real (if locally-served) bare SPA shell. NOT run by default
# (pytest.ini's addopts excludes -m network) -- run explicitly with:
#   uv run pytest -m network
#
# Served locally for the same reason url_discovery's equivalent test is:
# a genuinely bare SPA shell (no real title, no real content, until JS
# runs) is hard to find and keep finding on the live internet -- most
# real sites carry enough server-rendered chrome to never trip the
# "little visible text" heuristic in the first place. Serving one locally
# keeps this a real, repeatable check of the actual browser-render code
# path (launch Chromium, goto(), read rendered content) instead of hoping
# an external site stays shaped the right way forever.

import http.server
import threading

import pytest

from content_extraction.content_extraction import extract_content

pytestmark = pytest.mark.network

SPA_SHELL_HTML = b"""<!DOCTYPE html>
<html><head><title>Loading...</title></head>
<body>
<div id="root"></div>
<script>
  document.title = 'Real Rendered Title';
  document.getElementById('root').innerHTML =
    '<article><h1>Real Heading From JS</h1>' +
    '<p>This paragraph only exists after JavaScript runs and populates the DOM.</p>' +
    '</article>';
</script>
</body></html>
"""


class _SpaShellHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(SPA_SHELL_HTML)

    def log_message(self, *args):
        pass  # keep test output quiet


@pytest.fixture
def spa_shell_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _SpaShellHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_bare_spa_shell_content_is_only_found_via_a_real_browser_render(spa_shell_server):
    result = extract_content(spa_shell_server)

    assert result["status"] == "success"
    assert result["title"] == "Real Rendered Title"
    assert result["headings"] == ["Real Heading From JS"]
    assert result["paragraphs"] == [
        "This paragraph only exists after JavaScript runs and populates the DOM."
    ]


def test_lakshx_in_extracts_successfully_with_browser_fallback_wired_in():
    # Confirms the new browser-fallback code path doesn't break a normal,
    # fully server-rendered page -- lakshx.in/docs has real visible
    # content, so this should never trigger a browser render at all.
    result = extract_content("https://lakshx.in/docs")

    assert result["status"] == "success"
    assert result["title"]
    assert len(result["paragraphs"]) > 0
