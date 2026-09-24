# Regression suite for security/ssrf_guard.py. Fully offline -- mocks
# socket.getaddrinfo and requests.Session.get, so no real DNS/network I/O
# happens here. A small set of genuinely network tests (marked, opt-in)
# confirm the whole thing still behaves against real DNS/HTTP.

from unittest.mock import MagicMock, patch

import pytest
import requests

from security.ssrf_guard import MAX_REDIRECTS, UnsafeURLError, assert_safe_url, safe_get

GETADDRINFO_TARGET = "security.ssrf_guard.socket.getaddrinfo"


def _addrinfo(*ips):
    """Builds a fake socket.getaddrinfo() return value for one or more
    IPv4 addresses -- the real function returns a list of
    (family, type, proto, canonname, sockaddr) tuples; only sockaddr[0]
    (the IP) is ever read by assert_safe_url()."""
    return [(2, 1, 6, "", (ip, 0)) for ip in ips]


class TestAssertSafeUrl:
    def test_public_ip_is_allowed(self):
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34")):
            assert_safe_url("https://example.com/")  # does not raise

    def test_loopback_is_rejected(self):
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("127.0.0.1")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://localhost/")

    def test_ipv6_loopback_is_rejected(self):
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("::1")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://localhost/")

    def test_private_10_range_is_rejected(self):
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("10.0.0.5")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://internal.example.com/")

    def test_private_192_168_range_is_rejected(self):
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("192.168.1.1")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://router.local/")

    def test_cloud_metadata_link_local_ip_is_rejected(self):
        # 169.254.169.254 -- the AWS/GCP/Azure instance metadata endpoint.
        # Covered generically by the link-local check (169.254.0.0/16),
        # not a special case of its own.
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("169.254.169.254")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://169.254.169.254/latest/meta-data/")

    def test_multicast_is_rejected(self):
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("224.0.0.1")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://example.com/")

    def test_unspecified_is_rejected(self):
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("0.0.0.0")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://example.com/")

    def test_one_unsafe_ip_among_several_rejects_the_whole_hostname(self):
        # A caller can't control which of several resolved IPs a real
        # connection ends up using -- one bad candidate is enough.
        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34", "127.0.0.1")):
            with pytest.raises(UnsafeURLError):
                assert_safe_url("http://example.com/")

    def test_non_http_scheme_is_rejected_before_any_dns_lookup(self):
        with patch(GETADDRINFO_TARGET) as mock_getaddrinfo:
            with pytest.raises(UnsafeURLError):
                assert_safe_url("file:///etc/passwd")

        mock_getaddrinfo.assert_not_called()

    def test_ftp_scheme_is_rejected(self):
        with pytest.raises(UnsafeURLError):
            assert_safe_url("ftp://example.com/")

    def test_url_with_no_hostname_is_rejected(self):
        with pytest.raises(UnsafeURLError):
            assert_safe_url("http:///path")

    def test_unresolvable_hostname_is_not_treated_as_unsafe(self):
        # No IP to judge as unsafe here -- an unresolvable hostname is a
        # "can't reach it" problem, not a safety-policy one. The actual
        # request attempt moments later is what raises (a real
        # requests.ConnectionError), with its own already-friendly
        # DNS-failure handling -- this must not raise anything itself.
        import socket as socket_module

        with patch(GETADDRINFO_TARGET, side_effect=socket_module.gaierror("nope")):
            assert_safe_url("http://nope.invalid/")  # does not raise


def _response(status_code, url, headers=None):
    response = MagicMock(spec=requests.Response)
    response.status_code = status_code
    response.url = url
    response.headers = headers or {}
    response.is_redirect = "Location" in (headers or {}) and 300 <= status_code < 400
    return response


class TestSafeGet:
    def test_allowed_url_is_fetched_normally(self):
        session = MagicMock()
        session.get.return_value = _response(200, "https://example.com/")

        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34")):
            response = safe_get(session, "https://example.com/", timeout=10)

        assert response.status_code == 200
        session.get.assert_called_once_with("https://example.com/", timeout=10, allow_redirects=False)

    def test_unsafe_url_is_rejected_before_any_request(self):
        session = MagicMock()

        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("127.0.0.1")):
            with pytest.raises(UnsafeURLError):
                safe_get(session, "http://localhost/")

        session.get.assert_not_called()

    def test_redirect_to_a_safe_url_is_followed(self):
        session = MagicMock()
        session.get.side_effect = [
            _response(302, "https://example.com/old", {"Location": "/new"}),
            _response(200, "https://example.com/new"),
        ]

        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34")):
            response = safe_get(session, "https://example.com/old")

        assert response.status_code == 200
        assert response.url == "https://example.com/new"
        assert session.get.call_count == 2

    def test_redirect_to_an_unsafe_url_is_rejected_and_never_followed(self):
        session = MagicMock()
        session.get.return_value = _response(
            302, "https://example.com/", {"Location": "http://169.254.169.254/latest/meta-data/"}
        )

        def fake_getaddrinfo(hostname, *_args, **_kwargs):
            if hostname == "169.254.169.254":
                return _addrinfo("169.254.169.254")
            return _addrinfo("93.184.216.34")

        with patch(GETADDRINFO_TARGET, side_effect=fake_getaddrinfo):
            with pytest.raises(UnsafeURLError):
                safe_get(session, "https://example.com/")

        # Only the first (safe) hop was actually requested -- the
        # redirect target was rejected before a second request was made.
        assert session.get.call_count == 1

    def test_allow_redirects_kwarg_is_always_overridden_to_false(self):
        session = MagicMock()
        session.get.return_value = _response(200, "https://example.com/")

        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34")):
            safe_get(session, "https://example.com/", allow_redirects=True)

        assert session.get.call_args.kwargs["allow_redirects"] is False

    def test_more_than_max_redirects_is_rejected(self):
        session = MagicMock()
        session.get.side_effect = [
            _response(302, f"https://example.com/{i}", {"Location": f"/{i + 1}"})
            for i in range(MAX_REDIRECTS + 5)
        ]

        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34")):
            with pytest.raises(UnsafeURLError):
                safe_get(session, "https://example.com/0")

    def test_no_session_uses_requests_module_directly(self):
        with patch("security.ssrf_guard.requests.get", return_value=_response(200, "https://example.com/")) as mock_get, \
             patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34")):
            response = safe_get(None, "https://example.com/", timeout=10)

        assert response.status_code == 200
        mock_get.assert_called_once_with("https://example.com/", timeout=10, allow_redirects=False)


class TestInstallNavigationGuard:
    def test_document_request_to_a_safe_url_is_allowed_through(self):
        from security.ssrf_guard import install_navigation_guard

        page = MagicMock()
        install_navigation_guard(page)
        handler = page.route.call_args.args[1]

        route = MagicMock()
        request = MagicMock(resource_type="document", url="https://example.com/")

        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("93.184.216.34")):
            handler(route, request)

        route.continue_.assert_called_once()
        route.abort.assert_not_called()

    def test_document_request_to_an_unsafe_url_is_aborted(self):
        from security.ssrf_guard import install_navigation_guard

        page = MagicMock()
        install_navigation_guard(page)
        handler = page.route.call_args.args[1]

        route = MagicMock()
        request = MagicMock(resource_type="document", url="http://169.254.169.254/")

        with patch(GETADDRINFO_TARGET, return_value=_addrinfo("169.254.169.254")):
            handler(route, request)

        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    def test_non_document_subresource_is_never_validated_or_blocked(self):
        from security.ssrf_guard import install_navigation_guard

        page = MagicMock()
        install_navigation_guard(page)
        handler = page.route.call_args.args[1]

        route = MagicMock()
        request = MagicMock(resource_type="image", url="http://169.254.169.254/pixel.png")

        with patch(GETADDRINFO_TARGET) as mock_getaddrinfo:
            handler(route, request)

        mock_getaddrinfo.assert_not_called()
        route.continue_.assert_called_once()
        route.abort.assert_not_called()


@pytest.mark.network
class TestRealNetwork:
    def test_a_real_public_hostname_resolves_as_safe(self):
        assert_safe_url("https://example.com/")  # does not raise

    def test_localhost_is_rejected_via_real_resolution(self):
        with pytest.raises(UnsafeURLError):
            assert_safe_url("http://localhost/")

    def test_safe_get_fetches_a_real_site(self):
        session = requests.Session()
        response = safe_get(session, "https://example.com/", timeout=10)
        assert response.status_code == 200
