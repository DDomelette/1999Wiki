from io import StringIO

import pytest

from src.huijiwiki.browser_client import (
    BrowserLaunchError,
    BrowserApiClient,
    MissingPlaywrightError,
    build_edge_launch_args,
    create_edge_cdp_browser_client,
    launch_persistent_context_with_fallback,
    parse_browser_payload,
)
from src.huijiwiki.errors import (
    AccountMismatchError,
    ApiResponseError,
    HostViolation,
    ReadOnlyViolation,
    SessionExpiredError,
)


class FakePage:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def evaluate(self, script, params):
        self.calls.append((script, params))
        return self.payload


class SequentialPage:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def evaluate(self, script, params):
        self.calls.append((script, params))
        payload = self.payloads.pop(0)
        if isinstance(payload, BaseException):
            raise payload
        return payload


class TimeoutAwarePage(FakePage):
    def __init__(self, payload):
        super().__init__(payload)
        self.default_timeout = None

    def set_default_timeout(self, timeout_ms):
        self.default_timeout = timeout_ms


class CookieContext:
    def __init__(self, cookies):
        self.raw_cookies = list(cookies)
        self.urls = []

    def cookies(self, urls):
        self.urls.append(list(urls))
        return list(self.raw_cookies)


class FakePlaywrightFactory:
    def __init__(self, page=None):
        self.started = False
        self.connect_urls = []
        self.page = page if page is not None else object()
        self.context_closed = False

    def start(self):
        self.started = True
        return self

    def stop(self):
        self.started = False

    @property
    def chromium(self):
        return self

    def connect_over_cdp(self, url):
        self.connect_urls.append(url)
        factory = self

        class Context:
            pages = [factory.page]

            def close(self):
                factory.context_closed = True

        context = Context()
        return type("Browser", (), {"contexts": [context]})()


def test_parse_browser_payload_returns_json_payload():
    payload = parse_browser_payload(
        {
            "ok": True,
            "status": 200,
            "contentType": "application/json",
            "body": {"query": {}},
        }
    )

    assert payload == {"query": {}}


def test_browser_api_client_exposes_context_cookies_for_exact_url():
    context = CookieContext([{"name": "x", "value": "y"}])
    client = BrowserApiClient(
        page=FakePage({"ok": True, "status": 200, "contentType": "application/json", "body": {}}),
        context=context,
    )

    cookies = client.get_cookies("https://res1999.huijiwiki.com/wiki/test")

    assert cookies == [{"name": "x", "value": "y"}]
    assert context.urls == [["https://res1999.huijiwiki.com/wiki/test"]]


def test_parse_browser_payload_rejects_cloudflare_html():
    with pytest.raises(SessionExpiredError):
        parse_browser_payload(
            {
                "ok": False,
                "status": 403,
                "contentType": "text/html",
                "text": "<html>Just a moment...</html>",
            }
        )


def test_parse_browser_payload_raises_api_error():
    with pytest.raises(ApiResponseError):
        parse_browser_payload(
            {
                "ok": True,
                "status": 200,
                "contentType": "application/json",
                "body": {"error": {"code": "bad", "info": "Bad request"}},
            }
        )


def test_browser_client_guards_readonly_action_before_page_call():
    client = BrowserApiClient(
        page=FakePage({"ok": True, "status": 200, "contentType": "application/json", "body": {}})
    )

    with pytest.raises(ReadOnlyViolation):
        client.query({"action": "edit"})

    assert client.page.calls == []


def test_browser_client_guards_api_host():
    client = BrowserApiClient(
        page=FakePage({"ok": True, "status": 200, "contentType": "application/json", "body": {}}),
        api_url="https://example.com/api.php",
    )

    with pytest.raises(HostViolation):
        client.query({"meta": "userinfo"})


def test_browser_client_query_uses_fetch_and_request_defaults():
    page = FakePage(
        {
            "ok": True,
            "status": 200,
            "contentType": "application/json",
            "body": {"query": {"userinfo": {"name": "POTATO BOT"}}},
        }
    )
    client = BrowserApiClient(page=page)

    payload = client.get_userinfo()

    assert payload["query"]["userinfo"]["name"] == "POTATO BOT"
    assert "fetch" in page.calls[0][0]
    assert page.calls[0][1]["action"] == "query"
    assert page.calls[0][1]["format"] == "json"
    assert page.calls[0][1]["formatversion"] == "2"


def test_browser_client_query_retries_after_transient_navigation():
    page = SequentialPage(
        [
            RuntimeError("Execution context was destroyed, most likely because of a navigation"),
            {
                "ok": True,
                "status": 200,
                "contentType": "application/json",
                "body": {"query": {"userinfo": {"name": "POTATO BOT"}}},
            },
        ]
    )
    sleeps = []
    client = BrowserApiClient(page=page, sleep_fn=sleeps.append)

    payload = client.get_userinfo()

    assert payload["query"]["userinfo"]["name"] == "POTATO BOT"
    assert len(page.calls) == 2
    assert sleeps == [0.5]


def test_browser_client_fetch_script_has_abort_timeout():
    page = FakePage({"ok": True, "status": 200, "contentType": "application/json", "body": {"query": {}}})
    client = BrowserApiClient(page=page, fetch_timeout_ms=1234)

    client.query({"meta": "userinfo"})

    assert "AbortController" in page.calls[0][0]
    assert "1234" in page.calls[0][0]


def test_browser_client_fetch_script_disables_browser_cache():
    page = FakePage({"ok": True, "status": 200, "contentType": "application/json", "body": {"query": {}}})
    client = BrowserApiClient(page=page)

    client.query({"meta": "userinfo"})

    assert 'cache: "no-store"' in page.calls[0][0]
    assert '"Cache-Control": "no-cache"' in page.calls[0][0]
    assert '"Pragma": "no-cache"' in page.calls[0][0]


def test_browser_client_sets_playwright_page_timeout_when_supported():
    page = TimeoutAwarePage({"ok": True, "status": 200, "contentType": "application/json", "body": {"query": {}}})

    BrowserApiClient(page=page, fetch_timeout_ms=1234)

    assert page.default_timeout == 6234


def test_missing_playwright_error_includes_install_command():
    message = str(MissingPlaywrightError("playwright is not installed"))

    assert "install.cmd" in message
    assert "conda" not in message.lower()


def test_launch_persistent_context_falls_back_to_edge_when_bundled_browser_missing():
    class FakeChromium:
        def __init__(self):
            self.calls = []

        def launch_persistent_context(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise RuntimeError("Executable doesn't exist at chromium\nPlease run playwright install")
            if kwargs.get("channel") == "msedge":
                return "edge-context"
            raise RuntimeError("unexpected fallback")

    chromium = FakeChromium()

    context = launch_persistent_context_with_fallback(
        chromium,
        user_data_dir="profile",
        headless=False,
        viewport={"width": 1280, "height": 900},
    )

    assert context == "edge-context"
    assert chromium.calls[0].get("channel") is None
    assert chromium.calls[1]["channel"] == "msedge"


def test_build_edge_launch_args_uses_local_debug_port_and_profile(tmp_path):
    args = build_edge_launch_args(
        edge_executable=tmp_path / "msedge.exe",
        profile=tmp_path / "edge-profile",
        port=9333,
    )

    assert str(tmp_path / "msedge.exe") == args[0]
    assert "--remote-debugging-address=127.0.0.1" in args
    assert "--remote-debugging-port=9333" in args
    assert f"--user-data-dir={tmp_path / 'edge-profile'}" in args
    assert "https://res1999.huijiwiki.com/wiki/%E9%A6%96%E9%A1%B5" in args
    assert not any("/api.php" in arg for arg in args)


def test_create_edge_cdp_browser_client_launches_edge_and_connects(tmp_path):
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")
    launches = []
    playwright_factory = FakePlaywrightFactory()

    class Config:
        out = tmp_path / "out"
        sleep = 0.0
        browser_verify = False
        edge_profile = tmp_path / "edge-profile"
        edge_port = 9333
        edge_executable = edge_exe

    def fake_popen(args):
        launches.append(args)
        return object()

    client = create_edge_cdp_browser_client(
        Config(),
        popen_fn=fake_popen,
        wait_for_cdp_fn=lambda url, timeout: None,
        sync_playwright_factory=lambda: playwright_factory,
    )

    assert isinstance(client, BrowserApiClient)
    assert client.page is playwright_factory.page
    assert launches
    assert "--remote-debugging-port=9333" in launches[0]
    assert playwright_factory.connect_urls == ["http://127.0.0.1:9333"]


def test_create_edge_cdp_browser_client_resolves_relative_profile_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")
    launches = []
    playwright_factory = FakePlaywrightFactory()

    class Config:
        out = "relative-out"
        sleep = 0.0
        browser_verify = False
        edge_profile = None
        edge_port = 9333
        edge_executable = edge_exe

    def fake_popen(args):
        launches.append(args)
        return object()

    create_edge_cdp_browser_client(
        Config(),
        popen_fn=fake_popen,
        wait_for_cdp_fn=lambda url, timeout: None,
        sync_playwright_factory=lambda: playwright_factory,
    )

    expected_profile = tmp_path / "relative-out" / "edge_profile"
    assert f"--user-data-dir={expected_profile}" in launches[0]


def test_edge_cdp_launch_failure_cleans_up_process_and_uses_launch_error(tmp_path):
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")

    class FakeProcess:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True

    fake_process = FakeProcess()

    class Config:
        out = tmp_path / "out"
        sleep = 0.0
        browser_verify = False
        edge_profile = tmp_path / "edge-profile"
        edge_port = 9333
        edge_executable = edge_exe

    def fail_wait(url, timeout):
        raise BrowserLaunchError("Edge CDP endpoint did not become ready")

    with pytest.raises(BrowserLaunchError) as excinfo:
        create_edge_cdp_browser_client(
            Config(),
            popen_fn=lambda args: fake_process,
            wait_for_cdp_fn=fail_wait,
            sync_playwright_factory=lambda: FakePlaywrightFactory(),
        )

    assert fake_process.terminated is True
    assert fake_process.waited is True
    assert "pip install playwright" not in str(excinfo.value)


def test_edge_cdp_browser_client_close_terminates_launched_process(tmp_path):
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")

    class FakeProcess:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True

    fake_process = FakeProcess()
    playwright_factory = FakePlaywrightFactory()

    class Config:
        out = tmp_path / "out"
        sleep = 0.0
        browser_verify = False
        edge_profile = tmp_path / "edge-profile"
        edge_port = 9333
        edge_executable = edge_exe

    client = create_edge_cdp_browser_client(
        Config(),
        popen_fn=lambda args: fake_process,
        wait_for_cdp_fn=lambda url, timeout: None,
        sync_playwright_factory=lambda: playwright_factory,
    )

    client.close()

    assert fake_process.terminated is True
    assert fake_process.waited is True


def test_edge_cdp_browser_client_prompts_until_expected_account(tmp_path):
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")
    page = SequentialPage(
        [
            {
                "ok": True,
                "status": 200,
                "contentType": "application/json",
                "body": {"query": {"userinfo": {"name": "14.19.26.41"}}},
            },
            {
                "ok": True,
                "status": 200,
                "contentType": "application/json",
                "body": {"query": {"userinfo": {"name": "POTATO BOT"}}},
            },
        ]
    )
    playwright_factory = FakePlaywrightFactory(page=page)
    prompts = []
    stream = StringIO()

    class Config:
        out = tmp_path / "out"
        sleep = 0.0
        browser_verify = True
        expected_user = "POTATO BOT"
        edge_profile = tmp_path / "edge-profile"
        edge_port = 9333
        edge_executable = edge_exe

    client = create_edge_cdp_browser_client(
        Config(),
        input_fn=lambda prompt: prompts.append(prompt) or "",
        stream=stream,
        popen_fn=lambda args: object(),
        wait_for_cdp_fn=lambda url, timeout: None,
        sync_playwright_factory=lambda: playwright_factory,
    )

    assert client.page is page
    assert len(page.calls) == 2
    assert len(prompts) == 1
    assert "14.19.26.41" in stream.getvalue()
    assert "POTATO BOT" in stream.getvalue()


def test_edge_cdp_browser_client_retries_account_check_after_navigation(tmp_path):
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")
    page = SequentialPage(
        [
            RuntimeError("Execution context was destroyed, most likely because of a navigation"),
            {
                "ok": True,
                "status": 200,
                "contentType": "application/json",
                "body": {"query": {"userinfo": {"name": "POTATO BOT"}}},
            },
        ]
    )
    playwright_factory = FakePlaywrightFactory(page=page)
    prompts = []
    stream = StringIO()

    class Config:
        out = tmp_path / "out"
        sleep = 0.0
        browser_verify = True
        expected_user = "POTATO BOT"
        edge_profile = tmp_path / "edge-profile"
        edge_port = 9333
        edge_executable = edge_exe

    client = create_edge_cdp_browser_client(
        Config(),
        input_fn=lambda prompt: prompts.append(prompt) or "",
        stream=stream,
        popen_fn=lambda args: object(),
        wait_for_cdp_fn=lambda url, timeout: None,
        sync_playwright_factory=lambda: playwright_factory,
    )

    assert client.page is page
    assert len(page.calls) == 2
    assert len(prompts) == 0
    assert "POTATO BOT" in stream.getvalue()


def test_edge_cdp_browser_client_quit_during_account_prompt_cleans_up_process(tmp_path):
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")
    page = SequentialPage(
        [
            {
                "ok": True,
                "status": 200,
                "contentType": "application/json",
                "body": {"query": {"userinfo": {"name": "14.19.26.41"}}},
            }
        ]
    )
    playwright_factory = FakePlaywrightFactory(page=page)

    class FakeProcess:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True

    fake_process = FakeProcess()

    class Config:
        out = tmp_path / "out"
        sleep = 0.0
        browser_verify = True
        expected_user = "POTATO BOT"
        edge_profile = tmp_path / "edge-profile"
        edge_port = 9333
        edge_executable = edge_exe

    with pytest.raises(AccountMismatchError):
        create_edge_cdp_browser_client(
            Config(),
            input_fn=lambda prompt: "q",
            stream=StringIO(),
            popen_fn=lambda args: fake_process,
            wait_for_cdp_fn=lambda url, timeout: None,
            sync_playwright_factory=lambda: playwright_factory,
        )

    assert fake_process.terminated is True
    assert fake_process.waited is True
    assert playwright_factory.context_closed is True


def test_edge_cdp_browser_client_eof_during_account_prompt_cleans_up_process(tmp_path):
    edge_exe = tmp_path / "msedge.exe"
    edge_exe.write_text("", encoding="utf-8")
    page = SequentialPage(
        [
            {
                "ok": True,
                "status": 200,
                "contentType": "application/json",
                "body": {"query": {"userinfo": {"name": "14.19.26.41"}}},
            }
        ]
    )
    playwright_factory = FakePlaywrightFactory(page=page)

    class FakeProcess:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True

    fake_process = FakeProcess()

    class Config:
        out = tmp_path / "out"
        sleep = 0.0
        browser_verify = True
        expected_user = "POTATO BOT"
        edge_profile = tmp_path / "edge-profile"
        edge_port = 9333
        edge_executable = edge_exe

    def raise_eof(prompt):
        raise EOFError

    with pytest.raises(AccountMismatchError):
        create_edge_cdp_browser_client(
            Config(),
            input_fn=raise_eof,
            stream=StringIO(),
            popen_fn=lambda args: fake_process,
            wait_for_cdp_fn=lambda url, timeout: None,
            sync_playwright_factory=lambda: playwright_factory,
        )

    assert fake_process.terminated is True
    assert fake_process.waited is True
    assert playwright_factory.context_closed is True
