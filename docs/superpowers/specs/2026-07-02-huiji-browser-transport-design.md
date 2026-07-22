# Huiji Res1999 Browser Transport Design

## Background

The current HuijiWiki crawler uses `requests` with cookies loaded from the HuijiWiki GUI tool's `config.dat`. The robot account is valid and the cookie metadata can refresh, but direct Python HTTP requests still receive a Cloudflare challenge response. The in-browser session can reach the wiki and userinfo endpoint after the user completes verification.

This design adds a browser-backed transport for the existing read-only crawler. It does not replace the current `requests` transport. It gives the user a controlled path where they manually verify Cloudflare in a visible browser, then the crawler issues the same read-only MediaWiki API queries from that verified browser context.

## Goals

- Add a `browser` transport mode for `res1999.huijiwiki.com` only.
- Preserve the existing crawler pipeline: namespace enumeration, revision fetching, file manifest placeholders, SQLite resume state, JSONL output, progress logs, and expected account guard.
- Keep all MediaWiki requests read-only by reusing the existing `ensure_read_only_action` guard.
- Let the user manually solve Cloudflare or login prompts in a visible browser window.
- Stop cleanly when the browser session is blocked, challenged, closed, missing dependencies, or authenticated as the wrong account.
- Keep the existing `requests` transport available as the default.

## Non-Goals

- Do not bypass, solve, or automate Cloudflare challenges.
- Do not write to HuijiWiki.
- Do not download binary image or video assets in this phase.
- Do not build a crawler around page scraping when the MediaWiki API is reachable from the browser.
- Do not depend on the Codex in-app browser; the one-click local script must work from PowerShell.

## User Flow

The user runs:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
.\crawl_huiji_res1999.bat -Mode Full -Transport Browser
```

The launcher passes `--transport browser` to the Python CLI. The Python crawler opens a visible persistent browser window with a local profile directory under the crawler output area. It opens the res1999 homepage and a read-only userinfo API URL, then waits for the user to press Enter in the terminal. The user completes any browser-side verification first.

After Enter, the crawler calls the same read-only API queries through browser `fetch`. It validates the authenticated user is `POTATO BOT`, writes `siteinfo.json`, then proceeds with the existing crawl pipeline.

## Architecture

### Transport Selection

`CrawlConfig` gains:

- `transport: str`, default `requests`
- `browser_profile: Path | None`
- `browser_headless: bool`, default `False`
- `browser_verify: bool`, default `True`

`run_crawl` builds one API client object with a shared interface:

```python
query(params: dict[str, Any]) -> dict[str, Any]
get_userinfo() -> dict[str, Any]
get_siteinfo() -> dict[str, Any]
close() -> None
```

Existing tests that pass a fake client continue to work.

### Requests Client

The current `HuijiApiClient` remains unchanged except for an optional no-op `close()` method if needed for lifecycle symmetry. It is still the default transport.

### Browser Client

Create `src/huijiwiki/browser_client.py`.

Responsibilities:

- Import Playwright lazily so normal `requests` mode does not require it.
- Launch a persistent Chromium context with a visible window by default.
- Use a stable local profile directory so manual verification can survive reruns.
- Open the homepage and userinfo API verification tabs.
- Wait for explicit user confirmation through an injectable callback.
- Execute read-only API requests from the page context with `fetch`.
- Detect Cloudflare HTML/challenge responses and raise `SessionExpiredError`.
- Detect MediaWiki API errors and raise `ApiResponseError`.
- Enforce host lock and read-only action guard before every request.
- Close browser resources when the crawl ends.

The browser client returns parsed JSON payloads identical to `HuijiApiClient`.

### CLI and Launcher

`scripts/crawl_huiji_res1999.py` gains:

- `--transport {requests,browser}`
- `--browser-profile PATH`
- `--browser-headless`
- `--no-browser-verify`

`crawl_huiji_res1999.ps1` gains:

- `-Transport Requests|Browser`
- `-BrowserProfile`
- `-BrowserHeadless`
- `-NoBrowserVerify`

The `.bat` wrapper remains unchanged except as needed for line endings.

### Error Handling

Browser mode exits with code `2` for session/challenge states, same as requests mode. User-facing messages should clearly say whether the failure came from:

- missing Playwright package,
- missing Playwright browser runtime,
- browser verification not completed,
- Cloudflare challenge HTML,
- wrong authenticated account,
- API response error.

Missing Playwright package should exit with code `1` and show the install command:

```powershell
conda activate 1999wiki
pip install playwright
python -m playwright install chromium
```

### Progress and Rate Limiting

The existing `ProgressReporter` and `sleep` delay remain authoritative. Browser mode is expected to be slower than requests mode. Default `-Sleep 1.0` is retained; users can increase it if Cloudflare is sensitive.

### Security and Compliance

- Secrets and cookie values are never printed.
- The browser profile directory is local and excluded from git through existing data directory conventions.
- The same host lock blocks non-`https://res1999.huijiwiki.com/api.php` API URLs.
- The same read-only action guard blocks all write actions.
- The implementation does not attempt to defeat Cloudflare; it waits for user-driven browser verification.

## Testing Strategy

Automated tests focus on logic, not a live browser:

- CLI parses `--transport browser` and browser profile arguments.
- `CrawlConfig` stores browser transport settings.
- Browser client enforces read-only actions and host lock before calling browser APIs.
- Browser client converts JSON payloads into the same shape as `HuijiApiClient`.
- Browser client raises `SessionExpiredError` on HTML/challenge responses.
- Browser client raises an actionable dependency error when Playwright is unavailable.
- Launcher includes the new PowerShell parameters and forwards them to Python.

Manual verification:

- Run dry-run with browser transport.
- Complete browser verification manually.
- Confirm userinfo validates `POTATO BOT`.
- Confirm dry-run writes `siteinfo.json`.

## Acceptance Criteria

- `.\crawl_huiji_res1999.bat -Mode DryRun -Transport Browser` opens a visible browser and waits for manual verification.
- After the user verifies and presses Enter, the crawler validates `POTATO BOT` through the browser session.
- Full mode can reuse existing resume state and output layout.
- Requests transport remains the default and previous tests continue to pass.
- No write actions are possible through browser transport.
