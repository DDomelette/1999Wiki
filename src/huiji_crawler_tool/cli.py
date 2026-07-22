from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.error import URLError

import requests

from src.huijiwiki.browser_client import (
    BrowserLaunchError,
    MissingPlaywrightError,
    create_edge_cdp_browser_client,
    create_verified_browser_client,
)
from src.huijiwiki.credential_refresh import refresh_credentials
from src.huijiwiki.credential_store import (
    CredentialConflictError,
    CredentialValidationError,
    atomic_write_canonical_json,
    canonical_json,
    import_legacy_credential,
    inspect_credential,
)
from src.huijiwiki.crawler import CrawlConfig, run_crawl
from src.huijiwiki.errors import (
    AccountMismatchError,
    ApiResponseError,
    CredentialLoadError,
    HostViolation,
    ReadOnlyViolation,
    SessionExpiredError,
)
from src.huijiwiki.project_paths import ProjectPathViolation

from .config import CrawlerSettings, load_crawler_settings
from .doctor import build_doctor_report, credential_status_report
from .errors import (
    CliUsageError,
    CrawlerConfigError,
    CrawlerEnvironmentError,
    PackageIntegrityError,
    RuntimeLockConflict,
    ToolPathViolation,
)
from .runtime_lock import RuntimeLock
from .runtime_paths import resolve_owned_path


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def parse_namespaces_values(values: Sequence[str]) -> list[int]:
    namespaces: list[int] = []
    for value in values:
        for item in value.split(","):
            cleaned = item.strip()
            if not cleaned:
                continue
            try:
                namespaces.append(int(cleaned))
            except ValueError as exc:
                raise CliUsageError("namespaces must contain integers") from exc
    if not namespaces:
        raise CliUsageError("namespaces must not be empty")
    return namespaces


def _add_crawl_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--namespaces", nargs="+", default=None)
    parser.add_argument("--include-file-manifest", action="store_true", default=None)
    parser.add_argument("--sleep", type=float, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--expected-user", default=None)
    parser.add_argument("--quiet", action="store_false", dest="progress", default=None)
    parser.add_argument("--log-every", type=int, default=None)
    parser.add_argument("--transport", choices=("requests", "browser", "edge"), default=None)
    parser.add_argument("--browser-profile", type=Path, default=None)
    parser.add_argument("--browser-headless", action="store_true", default=None)
    parser.add_argument("--no-browser-verify", action="store_false", dest="browser_verify", default=None)
    parser.add_argument("--edge-profile", type=Path, default=None)
    parser.add_argument("--edge-port", type=int, default=None)
    parser.add_argument("--edge-executable", type=Path, default=None)


def build_crawl_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog=prog,
        description="Read-only crawler for res1999.huijiwiki.com",
    )
    _add_crawl_arguments(parser)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="huiji-crawler", description="Windows Huiji crawler tool")
    commands = parser.add_subparsers(dest="command", required=True)

    crawl = commands.add_parser("crawl", help="Run the read-only crawler")
    _add_crawl_arguments(crawl)

    credential = commands.add_parser("credential", help="Manage the default crawler credential")
    credential_commands = credential.add_subparsers(dest="credential_command", required=True)

    import_command = credential_commands.add_parser("import", help="Import an explicit legacy source")
    import_command.add_argument("--legacy-source", type=Path, required=True)
    import_command.add_argument("--replace", action="store_true")
    import_command.add_argument("--output", type=Path, default=None)

    refresh = credential_commands.add_parser("refresh", help="Refresh with a verified browser account")
    refresh.add_argument("--transport", choices=("browser", "edge"), default="edge")
    refresh.add_argument("--expected-user", default=None)
    refresh.add_argument("--out", type=Path, default=None)
    refresh.add_argument("--output", type=Path, default=None)
    refresh.add_argument("--browser-profile", type=Path, default=None)
    refresh.add_argument("--browser-headless", action="store_true", default=None)
    refresh.add_argument("--edge-profile", type=Path, default=None)
    refresh.add_argument("--edge-port", type=int, default=None)
    refresh.add_argument("--edge-executable", type=Path, default=None)

    status = credential_commands.add_parser("status", help="Inspect the canonical credential")
    status.add_argument("--output", type=Path, default=None)

    doctor = commands.add_parser("doctor", help="Run offline environment diagnostics")
    doctor.add_argument("--output", type=Path, default=None)

    verify = commands.add_parser("verify-package", help="Verify immutable package files")
    verify.add_argument("--critical-only", action="store_true")
    verify.add_argument("--output", type=Path, default=None)
    return parser


def _settings_overrides(args: argparse.Namespace, *, include_transport: bool = True) -> dict[str, object]:
    names = (
        "out",
        "namespaces",
        "include_file_manifest",
        "sleep",
        "expected_user",
        "progress",
        "log_every",
        "browser_profile",
        "browser_headless",
        "browser_verify",
        "edge_profile",
        "edge_port",
        "edge_executable",
    )
    overrides = {name: getattr(args, name, None) for name in names}
    if include_transport:
        overrides["transport"] = getattr(args, "transport", None)
    namespaces = overrides.get("namespaces")
    if namespaces is not None:
        overrides["namespaces"] = parse_namespaces_values(namespaces)
    return overrides


def _write_report(
    report: dict[str, object],
    *,
    output: Path | None,
    root: Path,
) -> None:
    if output is None:
        sys.stdout.write(canonical_json(report))
        return
    resolved = resolve_owned_path(output, root=root, label="output")
    atomic_write_canonical_json(resolved, report)


def _validated_output(output: Path | None, *, root: Path) -> Path | None:
    if output is None:
        return None
    return resolve_owned_path(output, root=root, label="output")


def _crawl(args: argparse.Namespace, *, root: Path, environ: Mapping[str, str]) -> int:
    settings = load_crawler_settings(
        tool_root=root,
        cli_overrides=_settings_overrides(args),
        environ=environ,
    )
    if args.config is not None:
        compatibility_path = resolve_owned_path(args.config, root=root, label="config")
        if compatibility_path != settings.paths.credential_file:
            raise CrawlerConfigError(
                "The deprecated --config option may only name the fixed canonical credential"
            )
    config = CrawlConfig(
        project_root=settings.paths.root,
        config_path=settings.paths.credential_file,
        out=settings.paths.workspace,
        namespaces=list(settings.namespaces),
        include_file_manifest=settings.include_file_manifest,
        sleep=settings.sleep,
        resume=bool(args.resume),
        dry_run=bool(args.dry_run),
        limit=args.limit,
        force=bool(args.force),
        expected_user=settings.expected_user,
        progress=settings.progress,
        log_every=settings.log_every,
        transport=settings.transport,
        browser_profile=settings.paths.browser_profile,
        browser_headless=settings.browser_headless,
        browser_verify=settings.browser_verify,
        edge_profile=settings.paths.edge_profile,
        edge_port=settings.edge_port,
        edge_executable=settings.edge_executable,
    )
    with RuntimeLock(settings.paths.lock_file):
        report = run_crawl(config)
    _write_report(report, output=None, root=root)
    return 0


def _credential_import(
    args: argparse.Namespace,
    *,
    root: Path,
    environ: Mapping[str, str],
) -> int:
    settings = load_crawler_settings(tool_root=root, environ=environ)
    output = _validated_output(args.output, root=root)
    with RuntimeLock(settings.paths.lock_file):
        report = import_legacy_credential(
            args.legacy_source,
            settings.paths.credential_file,
            expected_user=settings.expected_user,
            replace=bool(args.replace),
        )
    _write_report(report, output=output, root=root)
    return 0


def _refresh_overrides(args: argparse.Namespace) -> dict[str, object]:
    return {
        "expected_user": args.expected_user,
        "browser_profile": args.browser_profile,
        "browser_headless": args.browser_headless,
        "edge_profile": args.edge_profile,
        "edge_port": args.edge_port,
        "edge_executable": args.edge_executable,
    }


def _credential_refresh(
    args: argparse.Namespace,
    *,
    root: Path,
    environ: Mapping[str, str],
) -> int:
    settings = load_crawler_settings(
        tool_root=root,
        cli_overrides=_refresh_overrides(args),
        environ=environ,
    )
    runtime_out = settings.paths.refresh_runtime
    if args.out is not None:
        runtime_out = resolve_owned_path(args.out, root=root, label="out")
    output = _validated_output(args.output, root=root)
    runtime_config = CrawlConfig(
        project_root=settings.paths.root,
        config_path=settings.paths.credential_file,
        out=runtime_out,
        namespaces=[],
        include_file_manifest=False,
        sleep=0.0,
        resume=False,
        dry_run=True,
        limit=None,
        force=False,
        expected_user=settings.expected_user,
        progress=False,
        transport=args.transport,
        browser_profile=settings.paths.browser_profile,
        browser_headless=settings.browser_headless,
        browser_verify=True,
        edge_profile=settings.paths.edge_profile,
        edge_port=settings.edge_port,
        edge_executable=settings.edge_executable,
    )
    factory = create_verified_browser_client if args.transport == "browser" else create_edge_cdp_browser_client
    client = None
    with RuntimeLock(settings.paths.lock_file):
        try:
            client = factory(runtime_config)
            report = refresh_credentials(
                client,
                expected_user=settings.expected_user,
                target=settings.paths.credential_file,
            )
        finally:
            if client is not None:
                client.close()
    _write_report(report, output=output, root=root)
    return 0


def _credential_status(
    args: argparse.Namespace,
    *,
    root: Path,
    environ: Mapping[str, str],
) -> int:
    settings = load_crawler_settings(tool_root=root, environ=environ)
    report: dict[str, object] = {
        "schema_version": "huiji_credential_status.v1",
        "status": "valid",
        "credential": credential_status_report(
            settings.paths.credential_file,
            expected_user=settings.expected_user,
        ),
    }
    _write_report(report, output=args.output, root=root)
    return 0


def _doctor(args: argparse.Namespace, *, root: Path, environ: Mapping[str, str]) -> int:
    settings = load_crawler_settings(tool_root=root, environ=environ)
    output = _validated_output(args.output, root=root)
    report = build_doctor_report(settings, environ=environ)
    _write_report(report, output=output, root=root)
    return 8 if report["status"] == "error" else 0


def _verify_package(args: argparse.Namespace, *, root: Path) -> int:
    manifest = root / "package-manifest.v1.json"
    if not manifest.exists():
        report: dict[str, object] = {
            "schema_version": "huiji_crawler_package_verification.v1",
            "status": "source_checkout",
            "critical_only": bool(args.critical_only),
        }
    else:
        try:
            from bootstrap.package_verify import PackageVerificationError, verify_package
        except ImportError as exc:
            raise PackageIntegrityError("Package verifier is unavailable") from exc
        try:
            report = verify_package(root, critical_only=bool(args.critical_only))
        except PackageVerificationError as exc:
            raise PackageIntegrityError(str(exc)) from exc
    _write_report(report, output=args.output, root=root)
    return 0


def dispatch(
    args: argparse.Namespace,
    *,
    tool_root: Path,
    environ: Mapping[str, str],
) -> int:
    if args.command == "crawl":
        return _crawl(args, root=tool_root, environ=environ)
    if args.command == "credential":
        if args.credential_command == "import":
            return _credential_import(args, root=tool_root, environ=environ)
        if args.credential_command == "refresh":
            return _credential_refresh(args, root=tool_root, environ=environ)
        if args.credential_command == "status":
            return _credential_status(args, root=tool_root, environ=environ)
    if args.command == "doctor":
        return _doctor(args, root=tool_root, environ=environ)
    if args.command == "verify-package":
        return _verify_package(args, root=tool_root)
    raise CliUsageError("Unsupported command")


def _domain_error_code(exc: Exception) -> int | None:
    if isinstance(exc, AccountMismatchError):
        return 6
    if isinstance(
        exc,
        (CredentialLoadError, CredentialValidationError, CredentialConflictError, SessionExpiredError),
    ):
        return 2
    if isinstance(
        exc,
        (CrawlerConfigError, ToolPathViolation, ProjectPathViolation, ReadOnlyViolation, HostViolation),
    ):
        return 3
    if isinstance(exc, PackageIntegrityError):
        return 4
    if isinstance(exc, (ApiResponseError, requests.RequestException, URLError)):
        return 5
    if isinstance(exc, RuntimeLockConflict):
        return 7
    if isinstance(exc, (CrawlerEnvironmentError, BrowserLaunchError, MissingPlaywrightError)):
        return 8
    return None


def main(
    argv: Sequence[str] | None = None,
    *,
    tool_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    root = Path(tool_root or Path(__file__).resolve().parents[2]).expanduser().resolve(strict=True)
    environment = dict(os.environ if environ is None else environ)
    try:
        args = build_parser().parse_args(argv)
        return dispatch(args, tool_root=root, environ=environment)
    except Exception as exc:
        code = _domain_error_code(exc)
        if code is None:
            print(f"InternalError: {type(exc).__name__}", file=sys.stderr)
            return 1
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        if code == 2:
            print(
                "Run huiji-crawler.cmd credential refresh --transport edge, then retry.",
                file=sys.stderr,
            )
        return code
