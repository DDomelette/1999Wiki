# Huiji Browser Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only browser-backed transport for the Huiji res1999 crawler so a manually verified browser session can issue MediaWiki API queries when direct `requests` calls are blocked by Cloudflare.

**Architecture:** Keep the current crawler pipeline unchanged and add a second API client implementation with the same `query/get_userinfo/get_siteinfo/close` surface. The CLI and launcher choose between `requests` and `browser`; browser mode launches a visible persistent Chromium profile, waits for manual verification, then calls API URLs via browser `fetch`.

**Tech Stack:** Python 3.11/3.12, pytest, Playwright for Python as an optional dependency, PowerShell launcher.

---

## File Structure

- Create `src/huijiwiki/browser_client.py`: Playwright-backed API client, lazy dependency import, manual verification wait, host/read-only guards, response parsing.
- Modify `src/huijiwiki/client.py`: add no-op `close()` for lifecycle symmetry.
- Modify `src/huijiwiki/crawler.py`: add browser transport config and choose the correct client.
- Modify `scripts/crawl_huiji_res1999.py`: add browser transport CLI flags and pass them into `CrawlConfig`.
- Modify `crawl_huiji_res1999.ps1`: add `-Transport`, browser profile/headless/verify flags, and forward them.
- Modify tests:
  - `tests/test_huiji_browser_client.py`
  - `tests/test_huiji_cli.py`
  - `tests/test_huiji_start_script.py`

## Task 1: CLI and Config Surface

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huijiwiki\crawler.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\crawl_huiji_res1999.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_cli.py`

- [ ] **Step 1: Write failing CLI/config tests**

Add tests:

```python
def test_cli_accepts_browser_transport_options(tmp_path):
    parser = build_parser()
    args = parser.parse_args([
        "--transport",
        "browser",
        "--browser-profile",
        str(tmp_path / "profile"),
        "--browser-headless",
        "--no-browser-verify",
    ])

    assert args.transport == "browser"
    assert args.browser_profile == tmp_path / "profile"
    assert args.browser_headless is True
    assert args.browser_verify is False


def test_crawl_config_defaults_to_requests_transport(tmp_path):
    config = CrawlConfig(
        robot_root=tmp_path / "robot",
        out=tmp_path / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
    )

    assert config.transport == "requests"
    assert config.browser_profile is None
    assert config.browser_headless is False
    assert config.browser_verify is True
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests\test_huiji_cli.py::test_cli_accepts_browser_transport_options tests\test_huiji_cli.py::test_crawl_config_defaults_to_requests_transport -q
```

Expected: fail because parser/config do not yet define those fields.

- [ ] **Step 3: Implement config and parser flags**

Add fields to `CrawlConfig`:

```python
transport: str = "requests"
browser_profile: Path | None = None
browser_headless: bool = False
browser_verify: bool = True
```

Add parser args:

```python
parser.add_argument("--transport", choices=["requests", "browser"], default="requests")
parser.add_argument("--browser-profile", type=Path, default=None)
parser.add_argument("--browser-headless", action="store_true")
parser.add_argument("--no-browser-verify", action="store_false", dest="browser_verify", default=True)
```

Pass those values into `CrawlConfig`.

- [ ] **Step 4: Run tests and confirm pass**

Run the same command. Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git -C D:\PycharmProjects\nlp add -- LangChain/1999Search/src/huijiwiki/crawler.py LangChain/1999Search/scripts/crawl_huiji_res1999.py LangChain/1999Search/tests/test_huiji_cli.py
git -C D:\PycharmProjects\nlp commit -m "feat: add huiji transport cli options"
```

## Task 2: Browser API Client

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huijiwiki\browser_client.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huijiwiki\client.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_browser_client.py`

- [ ] **Step 1: Write failing browser client tests**

Create `tests/test_huiji_browser_client.py`:

```python
import pytest

from src.huijiwiki.browser_client import BrowserApiClient, MissingPlaywrightError, parse_browser_payload
from src.huijiwiki.errors import ApiResponseError, HostViolation, ReadOnlyViolation, SessionExpiredError


class FakePage:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def evaluate(self, script, params):
        self.calls.append((script, params))
        return self.payload


def test_parse_browser_payload_returns_json_payload():
    assert parse_browser_payload({"ok": True, "status": 200, "contentType": "application/json", "body": {"query": {}}}) == {
        "query": {}
    }


def test_parse_browser_payload_rejects_cloudflare_html():
    with pytest.raises(SessionExpiredError):
        parse_browser_payload({
            "ok": False,
            "status": 403,
            "contentType": "text/html",
            "text": "<html>Just a moment...</html>",
        })


def test_parse_browser_payload_raises_api_error():
    with pytest.raises(ApiResponseError):
        parse_browser_payload({
            "ok": True,
            "status": 200,
            "contentType": "application/json",
            "body": {"error": {"code": "bad", "info": "Bad request"}},
        })


def test_browser_client_guards_readonly_action_before_page_call():
    client = BrowserApiClient(page=FakePage({"ok": True, "status": 200, "contentType": "application/json", "body": {}}))

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
    page = FakePage({"ok": True, "status": 200, "contentType": "application/json", "body": {"query": {"userinfo": {"name": "POTATO BOT"}}}})
    client = BrowserApiClient(page=page)

    payload = client.get_userinfo()

    assert payload["query"]["userinfo"]["name"] == "POTATO BOT"
    assert page.calls[0][1]["action"] == "query"
    assert page.calls[0][1]["format"] == "json"
    assert page.calls[0][1]["formatversion"] == "2"


def test_missing_playwright_error_includes_install_command():
    message = str(MissingPlaywrightError("playwright is not installed"))

    assert "pip install playwright" in message
    assert "playwright install chromium" in message
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests\test_huiji_browser_client.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement `browser_client.py`**

Implement:

```python
class MissingPlaywrightError(HuijiCrawlerError): ...
class BrowserApiClient:
    def __init__(..., page=None, api_url=API_URL, request_delay=0.0, ...): ...
    def query(self, params: dict[str, Any]) -> dict[str, Any]: ...
    def get_siteinfo(self) -> dict[str, Any]: ...
    def get_userinfo(self) -> dict[str, Any]: ...
    def close(self) -> None: ...
```

`query()` must:

1. copy params,
2. set `action=query`, `format=json`, `formatversion=2`,
3. call `ensure_read_only_action`,
4. call the same host guard as the requests client,
5. run page `evaluate` with a browser `fetch` script,
6. parse through `parse_browser_payload`,
7. sleep `request_delay` if configured.

`create_verified_browser_client(config, input_fn=input, stream=sys.stderr)` must:

1. lazily import `playwright.sync_api.sync_playwright`,
2. launch persistent Chromium with the configured profile,
3. open homepage and userinfo URL,
4. prompt the user to complete verification and press Enter when `browser_verify=True`,
5. return `BrowserApiClient` with the active page/context/playwright handles.

- [ ] **Step 4: Add `close()` to requests client**

Add:

```python
def close(self) -> None:
    close = getattr(self.session, "close", None)
    if callable(close):
        close()
```

- [ ] **Step 5: Run tests and confirm pass**

Run:

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests\test_huiji_browser_client.py tests\test_huiji_client.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git -C D:\PycharmProjects\nlp add -- LangChain/1999Search/src/huijiwiki/browser_client.py LangChain/1999Search/src/huijiwiki/client.py LangChain/1999Search/tests/test_huiji_browser_client.py
git -C D:\PycharmProjects\nlp commit -m "feat: add huiji browser api client"
```

## Task 3: Wire Browser Transport Into Crawler

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huijiwiki\crawler.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\crawl_huiji_res1999.py`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_cli.py`

- [ ] **Step 1: Write failing transport selection tests**

Add tests:

```python
def test_build_default_client_uses_browser_transport(monkeypatch, tmp_path):
    import src.huijiwiki.crawler as crawler

    created = []

    class BrowserClient:
        pass

    def fake_create(config):
        created.append(config)
        return BrowserClient()

    monkeypatch.setattr(crawler, "create_verified_browser_client", fake_create)
    config = CrawlConfig(
        robot_root=tmp_path / "robot",
        out=tmp_path / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
        transport="browser",
        browser_profile=tmp_path / "profile",
    )

    client = crawler.build_default_client(config)

    assert isinstance(client, BrowserClient)
    assert created == [config]


def test_run_crawl_closes_default_client(monkeypatch, tmp_path):
    import src.huijiwiki.crawler as crawler

    class CloseAwareClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.closed = False

        def close(self):
            self.closed = True

    client = CloseAwareClient()
    monkeypatch.setattr(crawler, "build_default_client", lambda config: client)
    config = CrawlConfig(
        robot_root=tmp_path / "robot",
        out=tmp_path / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
        transport="browser",
    )

    run_crawl(config)

    assert client.closed is True
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests\test_huiji_cli.py::test_build_default_client_uses_browser_transport tests\test_huiji_cli.py::test_run_crawl_closes_default_client -q
```

Expected: fail because `build_default_client` does not branch by transport and `run_crawl` does not close default clients.

- [ ] **Step 3: Implement transport selection and lifecycle**

In `crawler.py`:

```python
def build_default_client(config: CrawlConfig) -> Any:
    if config.transport == "browser":
        from .browser_client import create_verified_browser_client

        return create_verified_browser_client(config)
    cookies, _ = load_default_cookies(config)
    return HuijiApiClient(cookies=cookies, request_delay=config.sleep)
```

In `run_crawl`, track whether the client was created internally and call `close()` in `finally`.

- [ ] **Step 4: Run tests and confirm pass**

Run the same command. Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git -C D:\PycharmProjects\nlp add -- LangChain/1999Search/src/huijiwiki/crawler.py LangChain/1999Search/tests/test_huiji_cli.py
git -C D:\PycharmProjects\nlp commit -m "feat: wire huiji browser transport"
```

## Task 4: PowerShell Launcher Support

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\crawl_huiji_res1999.ps1`
- Test: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_start_script.py`

- [ ] **Step 1: Write failing launcher test**

Add assertions:

```python
assert "[ValidateSet(\"Requests\", \"Browser\")]" in text
assert "$Transport" in text
assert "--transport" in text
assert "--browser-profile" in text
assert "--browser-headless" in text
assert "--no-browser-verify" in text
assert "BrowserProfile" in text
```

- [ ] **Step 2: Run test and confirm it fails**

Run:

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests\test_huiji_start_script.py -q
```

Expected: fail because launcher does not have browser flags.

- [ ] **Step 3: Implement launcher flags**

Add params:

```powershell
[ValidateSet("Requests", "Browser")]
[string]$Transport = "Requests",
[string]$BrowserProfile = "",
[switch]$BrowserHeadless,
[switch]$NoBrowserVerify,
```

Forward args:

```powershell
"--transport", $Transport.ToLowerInvariant()
```

If `$BrowserProfile` is set, append `--browser-profile`. Forward `--browser-headless` and `--no-browser-verify` for their switches.

- [ ] **Step 4: Run test and parser checks**

Run:

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests\test_huiji_start_script.py -q
$errors = $null; $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw 'crawl_huiji_res1999.ps1'), [ref]$errors); if ($errors) { $errors; exit 1 } else { 'parse-ok' }
```

Expected: tests pass and PowerShell parser prints `parse-ok`.

- [ ] **Step 5: Commit**

```powershell
git -C D:\PycharmProjects\nlp add -- LangChain/1999Search/crawl_huiji_res1999.ps1 LangChain/1999Search/tests/test_huiji_start_script.py
git -C D:\PycharmProjects\nlp commit -m "feat: add huiji browser launcher mode"
```

## Task 5: Verification

**Files:**
- All files touched above.

- [ ] **Step 1: Run Huiji test suite**

Run:

```powershell
$files = rg --files tests | rg 'test_huiji_.*\.py'
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest @($files) -q
```

Expected: all Huiji tests pass.

- [ ] **Step 2: Check batch line endings**

Run:

```powershell
$data = [System.IO.File]::ReadAllBytes('crawl_huiji_res1999.bat'); $lf = ($data | Where-Object { $_ -eq 10 }).Count; $crlf = ([regex]::Matches([System.Text.Encoding]::UTF8.GetString($data), "`r`n")).Count; "crlf=$crlf barelf=$($lf - $crlf)"
```

Expected: `barelf=0`.

- [ ] **Step 3: Dependency behavior dry run**

Run:

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe scripts\crawl_huiji_res1999.py --transport browser --dry-run --no-browser-verify
```

Expected before Playwright install: clear missing dependency message with install commands and exit code `1`.

- [ ] **Step 4: Optional live browser dry-run after installing Playwright**

Run:

```powershell
conda activate 1999wiki
pip install playwright
python -m playwright install chromium
cd D:\PycharmProjects\nlp\LangChain\1999Search
.\crawl_huiji_res1999.bat -Mode DryRun -Transport Browser
```

Expected: visible browser opens, user manually verifies, terminal resumes after Enter, and dry-run validates `POTATO BOT`.

- [ ] **Step 5: Final commit if any verification-only fixes were needed**

```powershell
git -C D:\PycharmProjects\nlp status --short
git -C D:\PycharmProjects\nlp add -- <only-browser-transport-files>
git -C D:\PycharmProjects\nlp commit -m "fix: stabilize huiji browser transport"
```

## Self-Review Notes

- Spec coverage: every goal maps to one or more tasks: transport config in Task 1, browser client in Task 2, crawler reuse in Task 3, launcher in Task 4, verification in Task 5.
- Placeholder scan: no task depends on undefined future work; optional live browser install is explicitly marked optional because dependency installation may be user-controlled.
- Type consistency: `transport`, `browser_profile`, `browser_headless`, and `browser_verify` are used consistently across config, CLI, and launcher.
