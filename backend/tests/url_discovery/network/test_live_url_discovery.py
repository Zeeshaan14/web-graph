# Real end-to-end checks: a real site crawl, and a real Chromium launch
# against a real (if locally-served) bare SPA shell. NOT run by default
# (pytest.ini's addopts excludes -m network) -- run explicitly with:
#   uv run pytest -m network
#
# The bare-shell case is served locally rather than from a real external
# site on purpose: real-world investigation (see this suite's own dev
# notes) found that today's actual SPA-shell sites almost always carry
# enough server-rendered chrome (nav/header/footer text) to sit above
# MIN_VISIBLE_TEXT_LENGTH even when their real content is JS-rendered --
# a genuinely bare shell (<div id="root"></div> + a script tag, nothing
# else) is hard to find and keep finding on the live internet. Serving one
# locally is the only way to reliably keep exercising the actual
# browser-render code path -- launching Chromium, running goto(), reading
# page.content() -- as a real, repeatable regression check, rather than
# hoping some external site keeps being shaped the right way forever.

import http.server
import threading

import pytest

from url_discovery.crawler import discover_urls

pytestmark = pytest.mark.network

SPA_SHELL_HTML = b"""<!DOCTYPE html>
<html><head><title>SPA Shell</title></head>
<body>
<div id="root"></div>
<script>
  document.getElementById('root').innerHTML =
    '<nav><a href="/page-a.html">Page A</a><a href="/page-b.html">Page B</a></nav>';
</script>
</body></html>
"""

PAGE_A_HTML = b"<html><head><title>Page A</title></head><body><h1>Page A</h1><p>Real content on page A.</p></body></html>"
PAGE_B_HTML = b"<html><head><title>Page B</title></head><body><h1>Page B</h1><p>Real content on page B.</p></body></html>"

PAGES = {
    "/": SPA_SHELL_HTML,
    "/page-a.html": PAGE_A_HTML,
    "/page-b.html": PAGE_B_HTML,
}


class _SpaShellHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

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


def test_bare_spa_shell_links_are_only_found_via_a_real_browser_render(spa_shell_server):
    result = discover_urls(spa_shell_server, max_pages=10, max_depth=1)

    assert result["status"] == "success"
    assert result["pages_traversed"] == 3
    assert result["discovered_urls"] == [
        spa_shell_server,
        f"{spa_shell_server}page-a.html",
        f"{spa_shell_server}page-b.html",
    ]


def test_lakshx_in_crawls_successfully_with_browser_fallback_wired_in():
    # Confirms the new browser-fallback code path doesn't break a normal,
    # fully server-rendered site -- lakshx.in has real visible content on
    # every page, so this should never trigger a browser render at all.
    result = discover_urls("https://lakshx.in/", max_pages=5, max_depth=1)

    assert result["status"] == "success"
    assert result["pages_traversed"] == 5
    assert "https://lakshx.in/" in result["discovered_urls"]
