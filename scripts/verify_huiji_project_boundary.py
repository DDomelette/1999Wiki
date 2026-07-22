from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class ForbiddenFileAccess(RuntimeError):
    """Raised when the guarded process opens a file below a forbidden root."""


class ForbiddenOpenGuard:
    def __init__(self, forbidden_roots: list[Path]) -> None:
        self.forbidden_roots = [Path(root).expanduser().resolve(strict=False) for root in forbidden_roots]
        self.blocked_paths: list[str] = []

    @property
    def blocked_access_count(self) -> int:
        return len(self.blocked_paths)

    def __call__(self, event: str, args: tuple[object, ...]) -> None:
        if event != "open" or not args:
            return
        raw_path = args[0]
        if isinstance(raw_path, int):
            return
        if isinstance(raw_path, bytes):
            raw_path = os.fsdecode(raw_path)
        if not isinstance(raw_path, str):
            return
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve(strict=False)
        for root in self.forbidden_roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            rendered = str(resolved)
            self.blocked_paths.append(rendered)
            raise ForbiddenFileAccess(f"Blocked file access under forbidden root: {rendered}")


class ReadOnlyRequestAudit:
    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []
        self.non_read_only_action_count = 0

    def observe(self, *, method: object, url: object, params: object) -> None:
        normalized_method = str(method).upper()
        normalized_params = params if isinstance(params, dict) else {}
        action = str(normalized_params.get("action", "query")).lower()
        parsed = urlsplit(str(url))
        self.requests.append(
            {
                "method": normalized_method,
                "scheme": parsed.scheme,
                "host": parsed.hostname or "",
                "path": parsed.path,
                "action": action,
            }
        )
        if normalized_method != "GET" or action != "query":
            self.non_read_only_action_count += 1
            raise RuntimeError(f"Blocked non-read-only HTTP request: {normalized_method} action={action}")


def _last_json_object(text: str) -> dict[str, object] | None:
    for line in reversed(text.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _resolve_inside_root(value: Path, *, root: Path, label: str) -> Path:
    root = root.resolve(strict=True)
    candidate = value.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must resolve inside {root}") from exc
    return resolved


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Huiji crawler with forbidden file roots")
    parser.add_argument("--tool-root", type=Path, default=ROOT)
    parser.add_argument("--forbid-root", type=Path, action="append", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("crawler_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    evidence = _resolve_inside_root(args.evidence, root=ROOT, label="evidence")
    tool_root = args.tool_root.expanduser().resolve(strict=True)
    if not tool_root.is_dir():
        raise ValueError("tool-root must be a directory")
    crawler_args = list(args.crawler_args)
    if crawler_args and crawler_args[0] == "--":
        crawler_args = crawler_args[1:]
    guard = ForbiddenOpenGuard(args.forbid_root)
    report: dict[str, object] = {
        "schema_version": "huiji_project_boundary.v1",
        "tool_root": str(tool_root),
        "forbidden_roots": [str(path) for path in guard.forbidden_roots],
        "blocked_access_count": 0,
        "blocked_paths": [],
        "crawler_exit_code": None,
        "crawler_report": None,
        "request_count": 0,
        "non_read_only_action_count": 0,
        "requests": [],
        "status": "running",
    }
    exit_code = 6
    stdout_buffer = io.StringIO()
    request_audit = ReadOnlyRequestAudit()
    session_class: object | None = None
    original_request: object | None = None
    sys.addaudithook(guard)
    try:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(tool_root))
        from src.huiji_crawler_tool.cli import main as crawler_tool_main
        from requests.sessions import Session

        module_path = Path(sys.modules[crawler_tool_main.__module__].__file__).resolve(strict=True)
        module_path.relative_to(tool_root)
        session_class = Session
        original_request = Session.request

        def guarded_request(session: object, method: object, url: object, **kwargs: object) -> object:
            request_audit.observe(method=method, url=url, params=kwargs.get("params"))
            return original_request(session, method, url, **kwargs)  # type: ignore[misc,operator]

        Session.request = guarded_request  # type: ignore[method-assign]
        with contextlib.redirect_stdout(stdout_buffer):
            exit_code = int(crawler_tool_main(crawler_args, tool_root=tool_root))
        report["crawler_exit_code"] = exit_code
        report["crawler_report"] = _last_json_object(stdout_buffer.getvalue())
        report["status"] = "passed" if exit_code == 0 else "crawler_failed"
    except ForbiddenFileAccess:
        exit_code = 5
        report["status"] = "forbidden_access_blocked"
    except Exception as exc:
        exit_code = 6
        report["status"] = "wrapper_error"
        report["error_type"] = type(exc).__name__
    finally:
        if session_class is not None and original_request is not None:
            session_class.request = original_request  # type: ignore[attr-defined,method-assign]
        captured_stdout = stdout_buffer.getvalue()
        if captured_stdout:
            sys.stdout.write(captured_stdout)
        report["blocked_access_count"] = guard.blocked_access_count
        report["blocked_paths"] = list(guard.blocked_paths)
        report["request_count"] = len(request_audit.requests)
        report["non_read_only_action_count"] = request_audit.non_read_only_action_count
        report["requests"] = request_audit.requests
        _atomic_write_json(evidence, report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
