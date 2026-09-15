# Lightweight stand-ins for requests.Response/Session, used to test
# pipeline.py's control flow (error handling, fallback branching) without
# any real network I/O.


class FakeCookieJar:
    def __init__(self, cookies):
        self._cookies = cookies

    def get_dict(self):
        return self._cookies


class FakeSession:
    def __init__(self, cookies=None):
        self.cookies = FakeCookieJar(cookies or {})


class FakeResponse:
    def __init__(self, url, status_code=200, headers=None, text=""):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
