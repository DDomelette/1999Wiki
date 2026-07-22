import pytest
from requests.cookies import RequestsCookieJar

from src.huijiwiki.client import HuijiApiClient
from src.huijiwiki.errors import ApiResponseError, HostViolation, ReadOnlyViolation, SessionExpiredError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else ""
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


class CookieSession(FakeSession):
    def __init__(self):
        super().__init__([])
        self.cookies = RequestsCookieJar()
        self.headers = {}


def test_client_preserves_same_name_cookies_with_different_domain_or_path():
    source = RequestsCookieJar()
    source.set("shared", "parent", domain=".huijiwiki.com", path="/")
    source.set("shared", "site", domain="res1999.huijiwiki.com", path="/api.php")
    session = CookieSession()

    HuijiApiClient(cookies=source, session=session)

    assert sorted((cookie.name, cookie.value, cookie.domain, cookie.path) for cookie in session.cookies) == [
        ("shared", "parent", ".huijiwiki.com", "/"),
        ("shared", "site", "res1999.huijiwiki.com", "/api.php"),
    ]


def test_client_blocks_write_action_and_wrong_host():
    client = HuijiApiClient(session=FakeSession([]), sleep_fn=lambda _: None)

    with pytest.raises(ReadOnlyViolation):
        client.query({"action": "edit"})

    with pytest.raises(HostViolation):
        client._guard_url("https://example.com/api.php")


def test_client_defaults_to_query_and_returns_json():
    session = FakeSession([FakeResponse(payload={"query": {"general": {"sitename": "x"}}})])
    client = HuijiApiClient(session=session, sleep_fn=lambda _: None)

    payload = client.query({"meta": "siteinfo"})

    assert payload["query"]["general"]["sitename"] == "x"
    assert session.calls[0][1]["action"] == "query"
    assert session.calls[0][1]["format"] == "json"


def test_client_fetches_userinfo_with_readonly_query():
    session = FakeSession([FakeResponse(payload={"query": {"userinfo": {"name": "POTATO BOT"}}})])
    client = HuijiApiClient(session=session, sleep_fn=lambda _: None)

    payload = client.get_userinfo()

    assert payload["query"]["userinfo"]["name"] == "POTATO BOT"
    assert session.calls[0][1]["meta"] == "userinfo"


def test_client_detects_cloudflare_html_and_403():
    html = "<html><title>Just a moment...</title></html>"
    client = HuijiApiClient(
        session=FakeSession([FakeResponse(status_code=403, text=html, headers={"content-type": "text/html"})]),
        sleep_fn=lambda _: None,
    )

    with pytest.raises(SessionExpiredError):
        client.query({"meta": "siteinfo"})


def test_client_raises_mediawiki_api_error():
    client = HuijiApiClient(
        session=FakeSession([FakeResponse(payload={"error": {"code": "badvalue", "info": "Bad value"}})]),
        sleep_fn=lambda _: None,
    )

    with pytest.raises(ApiResponseError):
        client.query({"meta": "siteinfo"})


def test_client_retries_transient_status_then_succeeds():
    sleeps = []
    session = FakeSession(
        [
            FakeResponse(status_code=503, payload={"error": "temporary"}),
            FakeResponse(payload={"query": {"ok": True}}),
        ]
    )
    client = HuijiApiClient(session=session, sleep_fn=sleeps.append, max_retries=2)

    assert client.query({"meta": "siteinfo"}) == {"query": {"ok": True}}
    assert sleeps == [1.0]
    assert len(session.calls) == 2


def test_client_applies_request_delay_after_successful_query():
    sleeps = []
    session = FakeSession([FakeResponse(payload={"query": {"ok": True}})])
    client = HuijiApiClient(session=session, sleep_fn=sleeps.append, request_delay=0.5)

    assert client.query({"meta": "siteinfo"}) == {"query": {"ok": True}}
    assert sleeps == [0.5]
