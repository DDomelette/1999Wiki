from __future__ import annotations

import hashlib
import msvcrt
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path

from bootstrap.python_runtime import PythonRuntimeInfo, current_runtime_info

from src.huijiwiki.credential_store import CredentialValidationError, inspect_credential

from .config import CrawlerSettings
from .discovery import (
    DependencyStatus,
    EdgeCandidate,
    PythonCandidate,
    discover_edge_candidates,
    discover_python_candidates,
    inspect_dependencies,
)


@dataclass(frozen=True)
class RuntimeLockStatus:
    available: bool
    status: str

    def to_json(self) -> dict[str, object]:
        return {"available": self.available, "status": self.status}


def probe_runtime_lock(path: Path) -> RuntimeLockStatus:
    candidate = Path(path)
    if not candidate.exists():
        return RuntimeLockStatus(available=True, status="not_created")
    try:
        with candidate.open("r+b") as handle:
            handle.seek(0, 2)
            if handle.tell() < 1:
                return RuntimeLockStatus(available=False, status="invalid_empty_lock")
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return RuntimeLockStatus(available=False, status="held")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        return RuntimeLockStatus(available=False, status="unreadable")
    return RuntimeLockStatus(available=True, status="available")


def _package_status(root: Path) -> dict[str, object]:
    manifest = root / "package-manifest.v1.json"
    sidecar = root / "package-manifest.v1.sha256"
    if not manifest.exists():
        return {"status": "source_checkout", "manifest_present": False}
    if not manifest.is_file() or not sidecar.is_file():
        return {"status": "invalid", "manifest_present": True, "reason": "missing_sidecar"}
    try:
        actual = hashlib.sha256(manifest.read_bytes()).hexdigest()
        expected = sidecar.read_text(encoding="ascii").strip().split()[0].casefold()
    except (OSError, UnicodeError, IndexError):
        return {"status": "invalid", "manifest_present": True, "reason": "unreadable"}
    if len(expected) != 64 or actual != expected:
        return {"status": "invalid", "manifest_present": True, "reason": "hash_mismatch"}
    return {
        "status": "manifest_hash_valid",
        "manifest_present": True,
        "manifest_sha256": actual,
    }


def _owned_path_status(settings: CrawlerSettings) -> list[dict[str, object]]:
    root = settings.paths.root.resolve(strict=True)
    results: list[dict[str, object]] = []
    for field in fields(settings.paths):
        if field.name == "root":
            continue
        path = Path(getattr(settings.paths, field.name)).resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError:
            status = "outside_tool_root"
        else:
            status = "inside_tool_root"
        results.append({"name": field.name, "path": str(path), "status": status})
    return sorted(results, key=lambda item: str(item["name"]))


def _expiry_status(cookie_expiries: Sequence[dict[str, object]], *, now: int) -> str:
    sessions = [item for item in cookie_expiries if item["name"] == "huiji_session"]
    if not sessions:
        return "missing_session_cookie"
    sessions.sort(
        key=lambda item: (len(str(item["domain"]).lstrip(".")), len(str(item["path"]))),
        reverse=True,
    )
    expires = sessions[0]["expires"]
    if expires is None:
        return "session"
    return "expired" if int(expires) <= now else "valid"


def credential_status_report(
    path: Path,
    *,
    expected_user: str,
    now: int | None = None,
) -> dict[str, object]:
    inspection = inspect_credential(path)
    report = inspection.to_json()
    report["present"] = True
    report["status"] = "valid"
    report["expected_user_matches"] = inspection.expected_user == expected_user
    report["expiry_status"] = _expiry_status(
        list(report["cookie_expiries"]),
        now=int(time.time() if now is None else now),
    )
    return report


def build_doctor_report(
    settings: CrawlerSettings,
    *,
    environ: Mapping[str, str] | None = None,
    current_runtime: PythonRuntimeInfo | None = None,
    python_candidates: Sequence[PythonCandidate] | None = None,
    dependency_statuses: Sequence[DependencyStatus] | None = None,
    edge_candidates: Sequence[EdgeCandidate] | None = None,
    lock_status: RuntimeLockStatus | None = None,
    now: int | None = None,
) -> dict[str, object]:
    environment = {} if environ is None else dict(environ)
    runtime = current_runtime_info() if current_runtime is None else current_runtime
    discovered_python = (
        discover_python_candidates(environ=environment)
        if python_candidates is None
        else tuple(python_candidates)
    )
    dependencies = inspect_dependencies() if dependency_statuses is None else tuple(dependency_statuses)
    discovered_edge = (
        discover_edge_candidates(environ=environment)
        if edge_candidates is None
        else tuple(edge_candidates)
    )
    probed_lock = probe_runtime_lock(settings.paths.lock_file) if lock_status is None else lock_status
    package = _package_status(settings.paths.root)
    owned_paths = _owned_path_status(settings)

    try:
        credential = credential_status_report(
            settings.paths.credential_file,
            expected_user=settings.expected_user,
            now=now,
        )
    except CredentialValidationError as exc:
        credential = {
            "path": str(settings.paths.credential_file),
            "present": settings.paths.credential_file.is_file(),
            "status": "missing_or_invalid",
            "error_type": type(exc).__name__,
        }

    selected_edge = next(
        (candidate for candidate in discovered_edge if candidate.status == "available"),
        None,
    )
    errors: list[str] = []
    warnings: list[str] = []
    if not runtime.supported:
        errors.append("unsupported_current_python")
    if any(item.status != "available" for item in dependencies):
        errors.append("missing_dependency")
    if any(item["status"] != "inside_tool_root" for item in owned_paths):
        errors.append("owned_path_escape")
    if package["status"] == "invalid":
        errors.append("invalid_package_manifest")
    if selected_edge is None:
        warnings.append("edge_not_found")
    if credential["status"] != "valid":
        warnings.append("credential_missing_or_invalid")
    else:
        if not credential["expected_user_matches"]:
            warnings.append("credential_account_mismatch")
        if credential["expiry_status"] in {"expired", "missing_session_cookie"}:
            warnings.append("credential_expiry")
    if not probed_lock.available:
        warnings.append("runtime_lock_unavailable")

    status = "error" if errors else "warning" if warnings else "ok"
    environment_report = [
        {
            "name": "HUIJI_CRAWLER_EDGE_EXECUTABLE",
            "set": "HUIJI_CRAWLER_EDGE_EXECUTABLE" in environment,
            "selected": selected_edge is not None and selected_edge.source == "environment",
        },
        {
            "name": "HUIJI_CRAWLER_PYTHON",
            "set": "HUIJI_CRAWLER_PYTHON" in environment,
            "selected": any(
                candidate.source == "environment" and candidate.status == "supported"
                for candidate in discovered_python
            ),
        },
    ]
    return {
        "schema_version": "huiji_crawler_doctor.v1",
        "status": status,
        "tool_root": str(settings.paths.root),
        "platform": {"system": runtime.system, "machine": runtime.machine},
        "current_python": runtime.to_json(),
        "python_candidates": [candidate.to_json() for candidate in discovered_python],
        "dependencies": [item.to_json() for item in dependencies],
        "edge": {
            "candidates": [candidate.to_json() for candidate in discovered_edge],
            "selected_path": None if selected_edge is None else str(selected_edge.path),
            "selected_source": None if selected_edge is None else selected_edge.source,
        },
        "environment": environment_report,
        "owned_paths": owned_paths,
        "package": package,
        "credential": credential,
        "runtime_lock": probed_lock.to_json(),
        "errors": sorted(errors),
        "warnings": sorted(warnings),
        "network_accessed": False,
    }
