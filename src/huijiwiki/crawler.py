from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .client import HuijiApiClient
from .browser_client import create_edge_cdp_browser_client, create_verified_browser_client
from .cookies import CookieLoader
from .enumerator import PageEnumerator
from .errors import AccountMismatchError, CredentialLoadError, SessionExpiredError
from .jsonl import JsonlWriter, write_json_file
from .models import content_sha256
from .project_paths import resolve_project_local_path
from .progress import ProgressReporter, format_duration
from .resources import ResourceManifestBuilder
from .revisions import RevisionFetcher
from .state import CrawlStateStore


@dataclass(frozen=True)
class CrawlConfig:
    project_root: Path
    config_path: Path
    out: Path
    namespaces: list[int]
    include_file_manifest: bool
    sleep: float
    resume: bool
    dry_run: bool
    limit: int | None
    force: bool
    expected_user: str = "POTATO BOT"
    progress: bool = True
    log_every: int = 100
    transport: str = "requests"
    browser_profile: Path | None = None
    browser_headless: bool = False
    browser_verify: bool = True
    edge_profile: Path | None = None
    edge_port: int = 9222
    edge_executable: Path | None = None
    cf_cookie_expires_at: float | None = None

    def __post_init__(self) -> None:
        root = Path(self.project_root).expanduser().resolve(strict=True)
        object.__setattr__(self, "project_root", root)
        for field_name in ("config_path", "out", "browser_profile", "edge_profile"):
            value = getattr(self, field_name)
            if value is None:
                continue
            object.__setattr__(
                self,
                field_name,
                resolve_project_local_path(
                    value,
                    project_root=root,
                    label=field_name,
                ),
            )
        if self.edge_executable is not None:
            object.__setattr__(self, "edge_executable", Path(self.edge_executable).expanduser())

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["project_root"] = "."
        payload["out"] = self._project_relative(self.out)
        payload["browser_profile"] = self._project_relative(self.browser_profile)
        payload["edge_profile"] = self._project_relative(self.edge_profile)
        payload["edge_executable"] = str(self.edge_executable) if self.edge_executable else None
        payload["config_path"] = self._project_relative(self.config_path)
        return payload

    def _project_relative(self, path: Path | None) -> str | None:
        if path is None:
            return None
        return path.relative_to(self.project_root).as_posix()


def build_default_client(config: CrawlConfig) -> HuijiApiClient:
    if config.transport == "browser":
        return create_verified_browser_client(config)
    if config.transport == "edge":
        return create_edge_cdp_browser_client(config)
    cookies, _ = load_default_cookies(config)
    return HuijiApiClient(cookies=cookies, request_delay=config.sleep)


def load_default_cookies(config: CrawlConfig) -> tuple[Any, int | None]:
    loader = CookieLoader(config.config_path)
    try:
        cookies = loader.load_cookies()
    except Exception as exc:
        relative_path = config.config_path.relative_to(config.project_root).as_posix()
        raise CredentialLoadError(
            f"Could not load project-local Huiji credential {relative_path} "
            f"({type(exc).__name__})."
        ) from exc
    if not cookies:
        relative_path = config.config_path.relative_to(config.project_root).as_posix()
        raise CredentialLoadError(
            f"Project-local Huiji credential {relative_path} contains no cookies."
        )
    if config.expected_user and loader.expected_user != config.expected_user:
        raise CredentialLoadError(
            f"Project-local Huiji credential {relative_path} is for a different expected account."
        )
    return cookies, loader.get_cookie_expires_at(
        "__cf_bm",
        host="res1999.huijiwiki.com",
    )


def validate_expected_account(api: Any, expected_user: str) -> str:
    payload = api.get_userinfo()
    actual_user = str(payload.get("query", {}).get("userinfo", {}).get("name", ""))
    if expected_user and actual_user != expected_user:
        raise AccountMismatchError(
            f"Authenticated HuijiWiki account is {actual_user!r}; expected {expected_user!r}. "
            "Stop and refresh the project-local crawler credential before crawling."
        )
    return actual_user


def ensure_cloudflare_cookie_fresh(expires_at: float | None, now: float | None = None) -> None:
    if expires_at is None:
        return
    remaining = expires_at - (time.time() if now is None else now)
    if remaining < 0:
        raise SessionExpiredError(
            "Cloudflare cookie in the project-local config.dat expired "
            f"{format_duration(-remaining)} ago. Run "
            "python scripts/refresh_huiji_credentials.py --transport edge, then retry."
        )


def _write_revision(
    revision,
    wikitext_writer: JsonlWriter,
    data_writer: JsonlWriter,
    state: CrawlStateStore,
    summary: dict[str, Any],
) -> None:
    payload = revision.to_json()
    wikitext_writer.write(payload)
    if revision.ns == 3500 or revision.title.startswith("Data:"):
        data_payload = dict(payload)
        try:
            json.loads(revision.content)
            data_payload["json_valid"] = True
            data_payload["json_error"] = None
        except json.JSONDecodeError as exc:
            data_payload["json_valid"] = False
            data_payload["json_error"] = str(exc)
        data_writer.write(data_payload)
    state.mark_revision_fetched(
        pageid=revision.pageid,
        revid=revision.revid,
        content_sha256=content_sha256(revision.content),
        stored_in="wikitext.jsonl",
    )
    summary["fetched_revisions"] += 1


def run_crawl(config: CrawlConfig, client: Any | None = None) -> dict[str, Any]:
    out = Path(config.out)
    cf_cookie_expires_at = config.cf_cookie_expires_at
    created_client = client is None
    api: Any | None = None
    state: CrawlStateStore | None = None
    run_id: int | None = None
    errors_writer: JsonlWriter | None = None
    summary: dict[str, Any] = {
        "dry_run": config.dry_run,
        "account": None,
        "namespaces": config.namespaces,
        "indexed_pages": 0,
        "fetch_candidates": 0,
        "fetched_revisions": 0,
        "resources_indexed": 0,
    }
    try:
        if client is None and config.transport == "requests":
            cookies, loaded_cf_cookie_expires_at = load_default_cookies(config)
            if cf_cookie_expires_at is None:
                cf_cookie_expires_at = loaded_cf_cookie_expires_at
            api = HuijiApiClient(cookies=cookies, request_delay=config.sleep)
        else:
            api = build_default_client(config) if client is None else client
        progress = ProgressReporter(
            enabled=config.progress,
            log_every=config.log_every,
            cf_cookie_expires_at=cf_cookie_expires_at,
        )
        progress.stage("preflight: cookies loaded")
        ensure_cloudflare_cookie_fresh(cf_cookie_expires_at)
        actual_user = validate_expected_account(api, config.expected_user)
        progress.stage(f"account verified: {actual_user}")
        siteinfo = api.get_siteinfo()

        out.mkdir(parents=True, exist_ok=True)
        state = CrawlStateStore(out / "crawl_state.sqlite")
        state.initialize()
        run_id = state.start_run(config.to_json())
        errors_writer = JsonlWriter(out / "errors.jsonl")
        write_json_file(out / "siteinfo.json", siteinfo)
        summary["account"] = actual_user
        if config.dry_run:
            progress.stage("dry-run complete")
            state.finish_run(run_id, "completed", summary)
            return summary

        pages_writer = JsonlWriter(out / "pages.jsonl")
        wikitext_writer = JsonlWriter(out / "wikitext.jsonl")
        data_writer = JsonlWriter(out / "data_pages.jsonl")

        enumerator = PageEnumerator(api)
        fetcher = RevisionFetcher(api)
        pageids_to_fetch: list[int] = []

        for ns in config.namespaces:
            seen: set[int] = set()
            state.mark_namespace_scan_started(run_id, ns)
            for page in enumerator.iter_namespace(ns):
                pages_writer.write(page.to_json())
                state.upsert_page_index(page)
                seen.add(page.pageid)
                summary["indexed_pages"] += 1
                progress.item("page index", summary["indexed_pages"], title=page.title)
                decision = state.should_fetch(page.pageid, page.lastrevid, force=config.force)
                if decision.should_fetch:
                    pageids_to_fetch.append(page.pageid)
                    summary["fetch_candidates"] += 1
                    if config.limit is not None and len(pageids_to_fetch) >= config.limit:
                        break
            state.mark_namespace_scan_completed(run_id, ns, seen)
            if config.limit is not None and len(pageids_to_fetch) >= config.limit:
                break

        for revision in fetcher.fetch_pageids(pageids_to_fetch):
            progress.item(
                "revision fetch",
                summary["fetched_revisions"] + 1,
                total=len(pageids_to_fetch),
                title=revision.title,
            )
            _write_revision(revision, wikitext_writer, data_writer, state, summary)

        if config.include_file_manifest:
            resource_writer = JsonlWriter(out / "resources_manifest.jsonl")
            for resource in ResourceManifestBuilder(api).iter_resources():
                resource_writer.write(resource.to_json())
                state.upsert_resource(resource)
                summary["resources_indexed"] += 1
                progress.item("resource manifest", summary["resources_indexed"], title=resource.title)

        state.finish_run(run_id, "completed", summary)
        return summary
    except Exception as exc:
        if errors_writer is not None and state is not None and run_id is not None:
            errors_writer.write(
                {
                    "stage": "run_crawl",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            state.finish_run(run_id, "failed", summary)
        raise
    finally:
        if created_client and api is not None:
            close = getattr(api, "close", None)
            if callable(close):
                close()
