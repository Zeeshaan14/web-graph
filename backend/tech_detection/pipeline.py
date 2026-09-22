# Orchestrates the whole two-stage flow: cheap HTTP evidence first, then
# a Playwright browser pass only if fallback.should_use_browser() says the
# HTTP evidence wasn't enough, then an inference pass over whichever
# direct-detection result turned out to be final. Every piece here
# (fetching, evidence construction, detection, the fallback decision,
# browser collection, inference) was already built and tested standalone
# — this file just wires them together in order.
#
# Inference always runs on the FINAL direct-detection pass, not the first
# HTTP-only one: when browser enrichment happens, http_technologies is
# used only to decide whether to launch the browser at all — it never
# feeds inference directly, only final_technologies (the post-merge
# result) does.
#
# detect_website_technologies() never raises. This becomes a FastAPI
# endpoint eventually, and a caller of an API can't be expected to catch
# arbitrary Python exceptions — it needs one predictable response shape
# either way.
#
# browser_status is always one of three strings, never null — "null"
# would ambiguously mean either "a browser was never needed" or "a
# browser was tried and failed," which are very different things for a
# caller to act on:
#   "not_launched" -> fallback decided HTTP evidence was enough (or we
#                     never got far enough to even make that decision)
#   "ok"           -> browser ran and contributed evidence
#   "failed"       -> browser was attempted but errored/timed out
#
#   {"status": "success", "http_status": 200, "browser_status": "not_launched" or "ok",
#    "url": ..., "evidence_source": ..., "technologies": [...], "errors": []}
#
#   {"status": "partial", "http_status": 200, "browser_status": "failed", "url": ...,
#    "evidence_source": "http", "technologies": [...http-only...],
#    "errors": [{"type": "browser_failed", "message": ...}]}
#   -> HTTP evidence was fine; fallback wanted a browser pass but it
#      failed/timed out. The valid HTTP result is still returned rather
#      than thrown away, just flagged as incomplete.
#
#   {"status": "failed", "http_status": None or int, "browser_status": "not_launched",
#    "url": ..., "evidence_source": None, "technologies": [],
#    "errors": [{"type", "message"}]}
#   -> Nothing usable at all (bad URL, connection failure, or an
#      unexpected error before we had any HTTP result to fall back to).

import requests

from .fetcher import fetch_url
from .evidence import build_evidence, merge_evidence
from .engine import detect_technologies
from .fallback import should_use_browser
from .browser import collect_browser_evidence
from .inference import add_inferred_technologies


# Substring markers for a DNS resolution failure, checked against a
# ConnectionError's own str() -- the real underlying exception (urllib3's
# NameResolutionError, wrapping a socket.gaierror) is buried inside
# ConnectionError.args, not exposed as its own catchable type, so this is
# the standard way to detect it. Covers the OS-specific errno wording:
# Windows' "getaddrinfo failed", Linux's "Name or service not known",
# macOS's "nodename nor servname".
_DNS_FAILURE_MARKERS = (
    "NameResolutionError",
    "getaddrinfo failed",
    "Name or service not known",
    "nodename nor servname",
)


def _friendly_connection_error(url: str, exc: requests.exceptions.ConnectionError) -> str:
    """requests' own str(exc) for a ConnectionError is an internal repr --
    "HTTPSConnectionPool(host=..., port=443): Max retries exceeded with
    url: / (Caused by NameResolutionError(...))" -- technically accurate,
    not something worth showing someone who just typed a URL into a form."""
    if any(marker in str(exc) for marker in _DNS_FAILURE_MARKERS):
        return f"Could not resolve '{url}' -- check the domain and try again."
    return f"Could not connect to '{url}'."


def _failed_result(url, error_type, message, http_status=None):
    return {
        "url": url,
        "status": "failed",
        "http_status": http_status,
        "browser_status": "not_launched",
        "evidence_source": None,
        "technologies": [],
        "errors": [{"type": error_type, "message": message}],
    }


def detect_website_technologies(url: str):
    # 1. Cheap HTTP path first — anything that goes wrong here means we
    # never got a response at all, so http_status stays None.
    try:
        response, session = fetch_url(url)
    except requests.exceptions.MissingSchema:
        return _failed_result(url, "invalid_url", f"'{url}' is not a valid URL (missing scheme, e.g. https://)")
    except requests.exceptions.ConnectionError as exc:
        return _failed_result(url, "connection_error", _friendly_connection_error(url, exc))
    except requests.exceptions.Timeout:
        return _failed_result(url, "timeout", f"Request to '{url}' timed out")
    except requests.exceptions.RequestException as exc:
        return _failed_result(url, "request_error", str(exc))

    # From here on we DID get a response (even a 4xx/5xx one is a normal,
    # analyzable result — see fallback.py's status_code >= 400 check for
    # why we still skip the browser for those). Any unexpected failure
    # past this point still shouldn't escape as a raw exception.
    try:
        http_evidence = build_evidence(
            response,
            session,
        )

        http_technologies = detect_technologies(
            http_evidence
        )

        # 2. Decide whether Chromium is worth launching
        if not should_use_browser(
            http_evidence,
            http_technologies,
        ):
            return {
                "url": response.url,
                "status": "success",
                "http_status": response.status_code,
                "browser_status": "not_launched",
                "evidence_source": "http",
                "technologies": add_inferred_technologies(http_technologies),
                "errors": [],
            }

        # 3. Browser enrichment — wrapped in its own try/except: the HTTP
        # result above is already valid on its own, so a Playwright
        # failure/timeout here shouldn't discard it. Fall back to the
        # HTTP-only result, flagged as "partial" rather than lost.
        try:
            browser_evidence = collect_browser_evidence(
                response.url
            )

            merged_evidence = merge_evidence(
                http_evidence,
                browser_evidence,
                base_url=response.url,
            )

            final_technologies = detect_technologies(
                merged_evidence
            )

            return {
                "url": response.url,
                "status": "success",
                "http_status": response.status_code,
                "browser_status": "ok",
                "evidence_source": "http+browser",
                "technologies": add_inferred_technologies(final_technologies),
                "errors": [],
            }
        except Exception as exc:
            return {
                "url": response.url,
                "status": "partial",
                "http_status": response.status_code,
                "browser_status": "failed",
                "evidence_source": "http",
                "technologies": add_inferred_technologies(http_technologies),
                "errors": [{"type": "browser_failed", "message": str(exc)}],
            }
    except Exception as exc:
        return _failed_result(
            url,
            "internal_error",
            f"Unexpected error analyzing '{url}': {exc}",
            http_status=response.status_code,
        )
