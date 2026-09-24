# Blocks server-side requests to loopback, private, link-local, and other
# non-public IP ranges. All three feature packages (tech_detection,
# url_discovery, content_extraction) fetch a URL a caller supplies
# directly -- two of them also launch a headless browser against it --
# so without this, a caller can point the server at itself
# (127.0.0.1/localhost), another host on its private network, or a cloud
# metadata endpoint (169.254.169.254) and have the server fetch it on
# their behalf.
#
# Deliberately NOT duplicated per feature package the way this project's
# other small helpers are (pacing constants, browser headers, DNS-failure
# markers). Those are duplicated on purpose so each feature stays
# independently modifiable -- a security check is the opposite case: a
# fix applied to one copy and missed in the other two is a live
# vulnerability, not just an inconsistency. One shared module, one place
# to get this right.
#
# Resolve-time checking, not full DNS-rebinding protection: assert_safe_url()
# validates the hostname's resolved IP(s) before a request is made, and
# safe_get() below re-validates before following every redirect hop too --
# which stops the overwhelming majority of real SSRF attempts (a direct
# internal URL, or a public URL that redirects to one). It does NOT pin
# the exact IP resolved here to the IP the underlying socket actually
# connects to, so a narrow TOCTOU window against an attacker running
# their own fast-flip DNS server is not fully closed -- closing that
# needs a custom transport that resolves and connects as one atomic step,
# a bigger change than this pass scoped.

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

ALLOWED_SCHEMES = {"http", "https"}

# A hard ceiling on how many redirect hops safe_get() will follow for one
# call -- same purpose as requests' own default (30), just smaller: this
# is about bounding a request's cost, not about matching requests' exact
# number.
MAX_REDIRECTS = 10


class UnsafeURLError(ValueError):
    """Raised when a URL fails the SSRF safety check. A ValueError
    subclass so an existing `except ValueError` (e.g. Pydantic's own
    validation-adjacent error handling) still catches it as a validation
    failure, while a caller that specifically cares about SSRF can catch
    this exact type instead."""


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_safe_url(url: str) -> None:
    """Raises UnsafeURLError if url isn't safe to fetch server-side.
    Checked scheme first (cheap, no network I/O), then every IP the
    hostname resolves to -- rejecting on ANY unsafe candidate, not just
    the first one returned, since a caller can't control which of
    several resolved IPs a real connection ends up using."""
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"'{url}' uses an unsupported scheme -- only http/https are fetched")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError(f"'{url}' has no hostname to resolve")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Can't resolve it at all -- not a safety concern (there's no IP
        # to judge as unsafe here), just an unreachable target. Returning
        # rather than raising lets the ACTUAL request attempt fail on its
        # own moments later with requests' own ConnectionError, which
        # every caller of this already has friendly, well-tested
        # DNS-failure handling for (see e.g. tech_detection/pipeline.py's
        # _friendly_connection_error()) -- duplicating that here under a
        # different, misleading "unsafe_url" category would just be
        # confusing for a plain typo'd or nonexistent domain.
        return

    for _family, _type, _proto, _canonname, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_unsafe_ip(ip):
            raise UnsafeURLError(
                f"'{hostname}' resolves to {ip}, a non-public address -- refusing to fetch it"
            )


def safe_get(session, url: str, **kwargs):
    """Drop-in replacement for session.get(url, ...) (or requests.get(url,
    ...) when session is None) that validates the target before every
    request AND before following every redirect hop. requests' own
    allow_redirects=True follows a whole redirect chain with no chance to
    inspect an intermediate hop first -- exactly the gap that turns "the
    caller's URL was safe" into "the server ends up fetching something
    unsafe anyway" (a public URL that redirects to an internal one).

    allow_redirects in kwargs is ignored -- this function always owns
    following redirects itself, since that's the whole point of it.
    Every other kwarg (timeout, headers, stream, ...) is passed through
    to each individual request unchanged. Returns the final response,
    same as a normal session.get(url, allow_redirects=True) call would --
    response.url, .status_code, .headers, .text, .raise_for_status() all
    behave identically to today's un-guarded calls."""
    getter = session.get if session is not None else requests.get
    request_kwargs = {**kwargs, "allow_redirects": False}

    current_url = url

    for _ in range(MAX_REDIRECTS + 1):
        assert_safe_url(current_url)
        response = getter(current_url, **request_kwargs)

        if not response.is_redirect:
            return response

        location = response.headers.get("Location")
        if not location:
            return response

        current_url = urljoin(current_url, location)

    raise UnsafeURLError(f"'{url}' redirected more than {MAX_REDIRECTS} times")


def install_navigation_guard(page) -> None:
    """Aborts any top-level navigation -- including every redirect hop --
    whose target fails assert_safe_url(). Playwright follows redirects
    internally during page.goto(), with no built-in hook to inspect an
    intermediate hop before it's followed, so this uses page.route() to
    intercept every request the page makes and validate the ones that
    are actual navigations (resource_type == "document") before letting
    them through.

    Deliberately scoped to navigation requests only, not every
    subresource (images, scripts, stylesheets, XHR/fetch calls a loaded
    page makes on its own) -- what this guards against is the SERVER's
    own process being made to fetch an internal target via navigation,
    not an ordinary page's asset loading, and intercepting every
    subresource risks breaking legitimate pages for no added safety
    here.

    Call this once, right after creating the page and before the first
    page.goto() -- an aborted navigation surfaces to the caller as a
    normal Playwright navigation error, which every browser.py caller in
    this codebase already catches and falls back from."""

    def handle_route(route, request):
        if request.resource_type == "document":
            try:
                assert_safe_url(request.url)
            except UnsafeURLError:
                route.abort()
                return
        route.continue_()

    page.route("**/*", handle_route)
