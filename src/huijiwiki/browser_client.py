from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, TextIO
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from src.huiji_crawler_tool.discovery import find_edge_executable

from .errors import AccountMismatchError, ApiResponseError, HostViolation, HuijiCrawlerError, SessionExpiredError
from .models import API_URL, ensure_read_only_action

HOMEPAGE_URL = "https://res1999.huijiwiki.com/wiki/%E9%A6%96%E9%A1%B5"
USERINFO_PARAMS = {"action": "query", "meta": "userinfo", "format": "json"}
BROWSER_QUERY_RETRIES = 3


class MissingPlaywrightError(HuijiCrawlerError):
    def __str__(self) -> str:
        return (
            f"{super().__str__()}\n"
            "Install the crawler dependencies from the tool root with:\n"
            "  install.cmd"
        )


class BrowserLaunchError(HuijiCrawlerError):
    """Raised when an installed browser cannot be launched or connected."""


def _resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _terminate_process(process: Any) -> None:
    terminate = getattr(process, "terminate", None)
    if not callable(terminate):
        return
    try:
        terminate()
    except OSError:
        return
    wait = getattr(process, "wait", None)
    if callable(wait):
        try:
            wait(timeout=5)
        except Exception:
            kill = getattr(process, "kill", None)
            if callable(kill):
                kill()


def _looks_like_missing_playwright_browser(exc: Exception) -> bool:
    message = str(exc).lower()
    return "executable doesn't exist" in message or "playwright install" in message


def launch_persistent_context_with_fallback(chromium: Any, **kwargs: Any) -> Any:
    try:
        return chromium.launch_persistent_context(**kwargs)
    except Exception as exc:
        if not _looks_like_missing_playwright_browser(exc):
            raise
        errors = [str(exc)]

    for channel in ("msedge", "chrome"):
        try:
            return chromium.launch_persistent_context(**kwargs, channel=channel)
        except Exception as exc:
            errors.append(f"{channel}: {exc}")

    raise MissingPlaywrightError(
        "Could not launch Playwright Chromium or an installed Edge/Chrome browser.\n"
        + "\n".join(errors)
    )


def build_edge_launch_args(edge_executable: Path, profile: Path, port: int) -> list[str]:
    return [
        str(edge_executable),
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={int(port)}",
        f"--user-data-dir={profile}",
        "--new-window",
        HOMEPAGE_URL,
    ]


def wait_for_cdp_endpoint(
    debug_url: str,
    timeout: float = 20.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(f"{debug_url}/json/version", timeout=1.0) as response:
                if response.status == 200:
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        sleep_fn(0.5)
    raise BrowserLaunchError(f"Edge CDP endpoint did not become ready at {debug_url}: {last_error}")


def parse_browser_payload(payload: dict[str, Any]) -> dict[str, Any]:
    content_type = str(payload.get("contentType", ""))
    text = str(payload.get("text", ""))
    status = int(payload.get("status", 0) or 0)
    if status == 403 or "Just a moment" in text or "cloudflare" in text.lower():
        raise SessionExpiredError("Cloudflare or login session blocked the browser API response")
    if "html" in content_type.lower() and "json" not in content_type.lower():
        raise SessionExpiredError("Expected JSON from browser API fetch but received HTML")

    body = payload.get("body")
    if body is None and text:
        try:
            body = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SessionExpiredError("Expected JSON from browser API fetch but response could not be decoded") from exc
    if not isinstance(body, dict):
        raise SessionExpiredError("Expected JSON object from browser API fetch")

    if "error" in body:
        error = body["error"]
        if isinstance(error, dict):
            raise ApiResponseError(f"{error.get('code')}: {error.get('info')}")
        raise ApiResponseError(str(error))
    if status >= 400:
        raise ApiResponseError(f"HTTP {status}")
    return body


class BrowserApiClient:
    def __init__(
        self,
        page: Any,
        api_url: str = API_URL,
        request_delay: float = 0.0,
        fetch_timeout_ms: int = 30000,
        sleep_fn: Callable[[float], None] = time.sleep,
        context: Any | None = None,
        playwright: Any | None = None,
        edge_process: Any | None = None,
    ) -> None:
        self.page = page
        self.api_url = api_url
        self.request_delay = request_delay
        self.fetch_timeout_ms = int(fetch_timeout_ms)
        self.sleep_fn = sleep_fn
        self.context = context
        self.playwright = playwright
        self.edge_process = edge_process
        set_default_timeout = getattr(self.page, "set_default_timeout", None)
        if callable(set_default_timeout):
            set_default_timeout(self.fetch_timeout_ms + 5000)

    def _guard_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "res1999.huijiwiki.com" or parsed.path != "/api.php":
            raise HostViolation(f"Blocked API host: {url}")

    def query(self, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        request_params.setdefault("action", "query")
        request_params.setdefault("format", "json")
        request_params.setdefault("formatversion", "2")
        ensure_read_only_action(request_params)
        self._guard_url(self.api_url)

        last_error: Exception | None = None
        for attempt in range(BROWSER_QUERY_RETRIES + 1):
            try:
                payload = self.page.evaluate(self._fetch_script(), request_params)
                break
            except Exception as exc:
                last_error = exc
                if attempt >= BROWSER_QUERY_RETRIES or not _is_transient_browser_navigation_error(exc):
                    raise
                self.sleep_fn(0.5)
        else:
            raise last_error or RuntimeError("Browser API query retry loop ended without a response")
        parsed = parse_browser_payload(payload)
        if self.request_delay > 0:
            self.sleep_fn(self.request_delay)
        return parsed

    def get_siteinfo(self) -> dict[str, Any]:
        return self.query(
            {
                "meta": "siteinfo",
                "siprop": "general|namespaces|statistics",
            }
        )

    def get_userinfo(self) -> dict[str, Any]:
        return self.query(
            {
                "meta": "userinfo",
                "uiprop": "groups|rights",
            }
        )

    def get_cookies(self, url: str) -> list[dict[str, Any]]:
        if self.context is None or not callable(getattr(self.context, "cookies", None)):
            raise BrowserLaunchError("Browser context does not expose cookies")
        return list(self.context.cookies([url]))

    def close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
        finally:
            try:
                if self.playwright is not None:
                    self.playwright.stop()
            finally:
                if self.edge_process is not None:
                    _terminate_process(self.edge_process)

    def _fetch_script(self) -> str:
        api_url_json = json.dumps(self.api_url)
        timeout_ms = int(self.fetch_timeout_ms)
        return f"""
            async (params) => {{
                const url = new URL({api_url_json});
                for (const [key, value] of Object.entries(params)) {{
                    url.searchParams.set(key, String(value));
                }}
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), {timeout_ms});
                try {{
                    const response = await fetch(url.toString(), {{
                        cache: "no-store",
                        credentials: "include",
                        signal: controller.signal,
                        headers: {{
                            "Accept": "application/json",
                            "Cache-Control": "no-cache",
                            "Pragma": "no-cache"
                        }}
                    }});
                    const text = await response.text();
                    let body = null;
                    try {{
                        body = JSON.parse(text);
                    }} catch (error) {{
                        body = null;
                    }}
                    return {{
                        ok: response.ok,
                        status: response.status,
                        contentType: response.headers.get("content-type") || "",
                        text,
                        body
                    }};
                }} catch (error) {{
                    return {{
                        ok: false,
                        status: 0,
                        contentType: "",
                        text: String(error),
                        body: null
                    }};
                }} finally {{
                    clearTimeout(timeoutId);
                }}
            }}
        """


def _extract_userinfo_name(payload: dict[str, Any]) -> str:
    return str(payload.get("query", {}).get("userinfo", {}).get("name", ""))


def _is_transient_browser_navigation_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "execution context was destroyed" in message and "navigation" in message


def wait_for_expected_browser_account(
    client: BrowserApiClient,
    expected_user: str | None,
    input_fn: Callable[[str], str],
    output: TextIO,
    label: str,
) -> str | None:
    expected = str(expected_user or "")
    if not expected:
        return None

    while True:
        try:
            actual = _extract_userinfo_name(client.get_userinfo())
        except SessionExpiredError as exc:
            actual = ""
            print(
                f"[{label}] Browser API check is blocked: {exc}",
                file=output,
                flush=True,
            )
        except Exception as exc:
            if not _is_transient_browser_navigation_error(exc):
                raise
            actual = ""
            print(
                f"[{label}] Browser API check is waiting for page navigation to finish: {exc}",
                file=output,
                flush=True,
            )
        else:
            if actual == expected:
                print(f"[{label}] Browser API account verified: {actual}", file=output, flush=True)
                return actual
            print(
                f"[{label}] Browser API account is {actual!r}; expected {expected!r}.",
                file=output,
                flush=True,
            )

        try:
            answer = input_fn(
                f"[{label}] Log in as {expected} in this browser, then press Enter to retry, or type q to quit: "
            )
        except EOFError as exc:
            raise AccountMismatchError(
                f"Authenticated HuijiWiki account is {actual!r}; expected {expected!r}. "
                "Browser account verification did not receive retry input."
            ) from exc
        if answer.strip().lower() == "q":
            raise AccountMismatchError(
                f"Authenticated HuijiWiki account is {actual!r}; expected {expected!r}."
            )


def create_verified_browser_client(
    config: Any,
    input_fn: Callable[[str], str] = input,
    stream: TextIO | None = None,
) -> BrowserApiClient:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise MissingPlaywrightError("playwright is not installed") from exc

    output = stream or sys.stderr
    profile = (
        _resolve_path(config.browser_profile)
        if config.browser_profile
        else _resolve_path(Path(config.out) / "browser_profile")
    )
    profile.mkdir(parents=True, exist_ok=True)

    playwright = sync_playwright().start()
    try:
        context = launch_persistent_context_with_fallback(
            playwright.chromium,
            user_data_dir=str(profile),
            headless=bool(config.browser_headless),
            viewport={"width": 1280, "height": 900},
        )
    except Exception as exc:
        playwright.stop()
        if isinstance(exc, MissingPlaywrightError):
            raise
        raise

    page = context.pages[0] if context.pages else context.new_page()
    page.goto(HOMEPAGE_URL, wait_until="domcontentloaded")
    page.goto(f"{API_URL}?{urlencode(USERINFO_PARAMS)}", wait_until="domcontentloaded")
    client = BrowserApiClient(
        page=page,
        api_url=API_URL,
        request_delay=config.sleep,
        context=context,
        playwright=playwright,
    )
    try:
        if config.browser_verify:
            wait_for_expected_browser_account(
                client,
                getattr(config, "expected_user", None),
                input_fn,
                output,
                "browser",
            )
        return client
    except Exception:
        client.close()
        raise


def create_edge_cdp_browser_client(
    config: Any,
    input_fn: Callable[[str], str] = input,
    stream: TextIO | None = None,
    popen_fn: Callable[[list[str]], Any] = subprocess.Popen,
    wait_for_cdp_fn: Callable[[str, float], None] = wait_for_cdp_endpoint,
    sync_playwright_factory: Callable[[], Any] | None = None,
) -> BrowserApiClient:
    if sync_playwright_factory is None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise MissingPlaywrightError("playwright is not installed") from exc
        sync_playwright_factory = sync_playwright

    output = stream or sys.stderr
    edge_executable = find_edge_executable(getattr(config, "edge_executable", None))
    profile = (
        _resolve_path(config.edge_profile)
        if getattr(config, "edge_profile", None)
        else _resolve_path(Path(config.out) / "edge_profile")
    )
    profile.mkdir(parents=True, exist_ok=True)
    port = int(getattr(config, "edge_port", 9222))
    debug_url = f"http://127.0.0.1:{port}"

    print(f"[edge] Edge profile: {profile}", file=output, flush=True)
    print(f"[edge] Debug endpoint: {debug_url}", file=output, flush=True)
    print("[edge] Opened homepage only; API checks use no-cache browser fetch.", file=output, flush=True)

    edge_process = popen_fn(build_edge_launch_args(edge_executable, profile, port))
    playwright = None
    try:
        wait_for_cdp_fn(debug_url, 20.0)

        playwright = sync_playwright_factory().start()
        browser = playwright.chromium.connect_over_cdp(debug_url)
        if not browser.contexts:
            raise BrowserLaunchError("Connected to Edge CDP but found no browser contexts")
        context = browser.contexts[0]
        page = context.pages[-1] if context.pages else context.new_page()
        client = BrowserApiClient(
            page=page,
            api_url=API_URL,
            request_delay=config.sleep,
            context=context,
            playwright=playwright,
            edge_process=edge_process,
        )
        if config.browser_verify:
            wait_for_expected_browser_account(
                client,
                getattr(config, "expected_user", None),
                input_fn,
                output,
                "edge",
            )
        return client
    except Exception:
        if "client" in locals():
            client.close()
        elif playwright is not None:
            playwright.stop()
            _terminate_process(edge_process)
        else:
            _terminate_process(edge_process)
        raise
