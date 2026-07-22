from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bootstrap.package_verify import MANIFEST_HASH_NAME, MANIFEST_NAME, verify_package
from bootstrap.python_runtime import PythonRuntimeInfo, UnsupportedPythonRuntime, current_runtime_info, validate_runtime


INSTALL_MARKER = ".huiji-crawler-install.v1.json"
INSTALL_SCHEMA = "huiji_crawler_install.v1"


class InstallError(RuntimeError):
    """Raised when package installation or marker validation fails."""


def _owned_path(path: Path, *, root: Path, label: str, must_exist: bool) -> Path:
    try:
        resolved = path.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise InstallError(f"{label} must resolve inside the tool root") from exc
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    encoded = _canonical_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _expected_marker(root: Path, runtime: PythonRuntimeInfo) -> dict[str, object]:
    lock = _owned_path(root / "requirements-crawler.lock.txt", root=root, label="dependency lock", must_exist=True)
    manifest = _owned_path(root / MANIFEST_NAME, root=root, label="manifest", must_exist=True)
    sidecar = _owned_path(root / MANIFEST_HASH_NAME, root=root, label="manifest sidecar", must_exist=True)
    if not lock.is_file() or not manifest.is_file() or not sidecar.is_file():
        raise InstallError("Package dependency lock or manifest is missing")
    manifest_hash = _sha256(manifest)
    expected_sidecar = sidecar.read_text(encoding="ascii").strip().split()[0].casefold()
    if manifest_hash != expected_sidecar:
        raise InstallError("Manifest detached SHA-256 mismatch")
    return {
        "schema_version": INSTALL_SCHEMA,
        "python": {
            "implementation": runtime.implementation,
            "version": list(runtime.version),
            "machine": runtime.machine,
            "pointer_bits": runtime.pointer_bits,
        },
        "requirements_lock_sha256": _sha256(lock),
        "manifest_sha256": manifest_hash,
    }


def check_install_marker(
    root: Path,
    *,
    runtime: PythonRuntimeInfo | None = None,
) -> dict[str, object]:
    resolved_root = Path(root).expanduser().resolve(strict=True)
    inspected = current_runtime_info() if runtime is None else runtime
    try:
        validate_runtime(inspected)
    except UnsupportedPythonRuntime as exc:
        raise InstallError(str(exc)) from exc
    marker = _owned_path(
        resolved_root / ".venv" / INSTALL_MARKER,
        root=resolved_root,
        label="install marker",
        must_exist=True,
    )
    try:
        actual = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError("Install marker is missing or invalid; run install.cmd") from exc
    expected = _expected_marker(resolved_root, inspected)
    if actual != expected:
        raise InstallError("Install marker does not match Python, lock or manifest; run install.cmd")
    return {"schema_version": "huiji_crawler_install_check.v1", "status": "valid"}


def install_package(
    root: Path,
    *,
    runtime: PythonRuntimeInfo | None = None,
    verify_fn: Callable[..., dict[str, object]] = verify_package,
    run_fn: Callable[..., Any] = subprocess.run,
) -> dict[str, object]:
    resolved_root = Path(root).expanduser().resolve(strict=True)
    inspected = current_runtime_info() if runtime is None else runtime
    try:
        validate_runtime(inspected)
    except UnsupportedPythonRuntime as exc:
        raise InstallError(
            "Huiji crawler installation requires Windows x64 CPython >=3.12.0,<3.13"
        ) from exc
    venv_root = resolved_root / ".venv"
    if venv_root.exists():
        _owned_path(venv_root, root=resolved_root, label="virtual environment", must_exist=True)
    marker = venv_root / INSTALL_MARKER
    marker.unlink(missing_ok=True)
    try:
        verify_fn(resolved_root, critical_only=True)
        run_fn(
            [str(inspected.executable), "-m", "venv", str(venv_root)],
            check=True,
            cwd=resolved_root,
        )
        venv_python = venv_root / "Scripts" / "python.exe"
        if not venv_python.is_file():
            raise InstallError("Virtual environment did not create Scripts\\python.exe")
        venv_python = _owned_path(
            venv_python,
            root=resolved_root,
            label="virtual environment Python",
            must_exist=True,
        )
        lock = resolved_root / "requirements-crawler.lock.txt"
        run_fn(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "--only-binary=:all:",
                "-r",
                str(lock),
            ],
            check=True,
            cwd=resolved_root,
        )
        run_fn(
            [str(venv_python), "-c", "import playwright,requests,yaml"],
            check=True,
            cwd=resolved_root,
        )
        run_fn(
            [str(venv_python), "-m", "src.huiji_crawler_tool", "--help"],
            check=True,
            cwd=resolved_root,
        )
        marker_payload = _expected_marker(resolved_root, inspected)
        _atomic_write(marker, marker_payload)
    except Exception as exc:
        marker.unlink(missing_ok=True)
        if isinstance(exc, InstallError):
            raise
        raise InstallError(f"Crawler installation failed ({type(exc).__name__})") from exc
    return {
        "schema_version": "huiji_crawler_install_result.v1",
        "status": "installed",
        "marker": INSTALL_MARKER,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Huiji crawler dependencies")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check-marker", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = check_install_marker(args.root) if args.check_marker else install_package(args.root)
    except (InstallError, OSError) as exc:
        print(f"Crawler install failed: {exc}", file=sys.stderr)
        return 8
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
