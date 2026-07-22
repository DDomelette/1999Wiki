from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True


MANIFEST_NAME = "package-manifest.v1.json"
MANIFEST_HASH_NAME = "package-manifest.v1.sha256"
MANIFEST_SCHEMA = "huiji_crawler_package_manifest.v1"
MUTABLE_PREFIXES = (".local/", ".venv/", "workspace/")
CRITICAL_PATHS = frozenset(
    {
        "huiji-crawler.cmd",
        "bootstrap/package_verify.py",
        "src/huiji_crawler_tool/cli.py",
        "config/crawler.yaml",
        "requirements-crawler.lock.txt",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PackageVerificationError(RuntimeError):
    """Raised when immutable package content does not match its manifest."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackageVerificationError(f"Manifest contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside_root(path: Path, root: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise PackageVerificationError(f"Package path escape detected for {label}") from exc
    return resolved


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PackageVerificationError("Manifest file path must be a non-empty POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise PackageVerificationError(f"Manifest contains unsafe path: {value}")
    if re.match(r"^[A-Za-z]:", value):
        raise PackageVerificationError(f"Manifest contains absolute path: {value}")
    return value


def _load_manifest(root: Path) -> tuple[dict[str, Any], str]:
    manifest_path = _inside_root(root / MANIFEST_NAME, root, label=MANIFEST_NAME)
    sidecar_path = _inside_root(root / MANIFEST_HASH_NAME, root, label=MANIFEST_HASH_NAME)
    actual_hash = _sha256(manifest_path)
    try:
        expected_hash = sidecar_path.read_text(encoding="ascii").strip().split()[0].casefold()
    except (OSError, UnicodeError, IndexError) as exc:
        raise PackageVerificationError("Manifest hash sidecar is unreadable") from exc
    if not _SHA256_RE.fullmatch(expected_hash) or expected_hash != actual_hash:
        raise PackageVerificationError("Manifest detached SHA-256 mismatch")
    try:
        payload = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except PackageVerificationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageVerificationError("Manifest is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise PackageVerificationError("Manifest must be an object")
    return payload, actual_hash


def _validate_manifest(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if set(payload) != {"schema_version", "target", "mutable_prefixes", "files"}:
        raise PackageVerificationError("Manifest top-level fields are invalid")
    if payload["schema_version"] != MANIFEST_SCHEMA:
        raise PackageVerificationError(f"Manifest schema_version must be {MANIFEST_SCHEMA}")
    target = payload["target"]
    if target != {"os": "windows", "arch": "x64", "python": ">=3.12.0,<3.13"}:
        raise PackageVerificationError("Manifest target is invalid")
    if payload["mutable_prefixes"] != list(MUTABLE_PREFIXES):
        raise PackageVerificationError("Manifest mutable prefixes are invalid")
    records = payload["files"]
    if not isinstance(records, list):
        raise PackageVerificationError("Manifest files must be a list")

    by_path: dict[str, dict[str, Any]] = {}
    casefold_paths: set[str] = set()
    for raw in records:
        if not isinstance(raw, dict) or set(raw) != {"path", "role", "critical", "size", "sha256"}:
            raise PackageVerificationError("Manifest file record fields are invalid")
        relative = _safe_relative(raw["path"])
        folded = relative.casefold()
        if relative in by_path:
            raise PackageVerificationError(f"Manifest contains duplicate path: {relative}")
        if folded in casefold_paths:
            raise PackageVerificationError(f"Manifest contains case-colliding path: {relative}")
        if any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in MUTABLE_PREFIXES):
            raise PackageVerificationError(f"Mutable path cannot appear in manifest: {relative}")
        if not isinstance(raw["role"], str) or not raw["role"]:
            raise PackageVerificationError(f"Manifest role is invalid: {relative}")
        if not isinstance(raw["critical"], bool):
            raise PackageVerificationError(f"Manifest critical flag is invalid: {relative}")
        if isinstance(raw["size"], bool) or not isinstance(raw["size"], int) or raw["size"] < 0:
            raise PackageVerificationError(f"Manifest size is invalid: {relative}")
        if not isinstance(raw["sha256"], str) or not _SHA256_RE.fullmatch(raw["sha256"]):
            raise PackageVerificationError(f"Manifest SHA-256 is invalid: {relative}")
        by_path[relative] = raw
        casefold_paths.add(folded)

    missing_critical = sorted(CRITICAL_PATHS - set(by_path))
    if missing_critical:
        raise PackageVerificationError(f"Manifest is missing critical path: {missing_critical[0]}")
    for relative in CRITICAL_PATHS:
        if by_path[relative]["critical"] is not True:
            raise PackageVerificationError(f"Required path is not marked critical: {relative}")
    return by_path


def _verify_record(root: Path, relative: str, record: dict[str, Any]) -> None:
    path = _inside_root(root / Path(relative), root, label=relative)
    if not path.is_file():
        raise PackageVerificationError(f"Manifest path is not a file: {relative}")
    stat = path.stat()
    if stat.st_size != record["size"]:
        raise PackageVerificationError(f"Package size mismatch: {relative}")
    if _sha256(path) != record["sha256"]:
        raise PackageVerificationError(f"Package SHA-256 mismatch: {relative}")


def _immutable_inventory(root: Path) -> set[str]:
    inventory: set[str] = set()
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        kept: list[str] = []
        for dirname in sorted(dirnames):
            child = directory_path / dirname
            relative = child.relative_to(root).as_posix()
            _inside_root(child, root, label=relative)
            kept.append(dirname)
        dirnames[:] = kept
        for filename in sorted(filenames):
            child = directory_path / filename
            relative = child.relative_to(root).as_posix()
            _inside_root(child, root, label=relative)
            if any(relative.startswith(prefix) for prefix in MUTABLE_PREFIXES):
                continue
            inventory.add(relative)
    return inventory


def verify_package(root: Path, *, critical_only: bool = False) -> dict[str, object]:
    resolved_root = Path(root).expanduser().resolve(strict=True)
    if not resolved_root.is_dir():
        raise PackageVerificationError("Package root must be a directory")
    payload, manifest_hash = _load_manifest(resolved_root)
    records = _validate_manifest(payload)
    selected = CRITICAL_PATHS if critical_only else frozenset(records)
    for relative in sorted(selected):
        _verify_record(resolved_root, relative, records[relative])
    if not critical_only:
        actual = _immutable_inventory(resolved_root)
        expected = set(records) | {MANIFEST_NAME, MANIFEST_HASH_NAME}
        extras = sorted(actual - expected, key=str.casefold)
        missing = sorted(expected - actual, key=str.casefold)
        if extras:
            raise PackageVerificationError(f"Package contains extra immutable file: {extras[0]}")
        if missing:
            raise PackageVerificationError(f"Package is missing immutable file: {missing[0]}")
    return {
        "schema_version": "huiji_crawler_package_verification.v1",
        "status": "passed",
        "mode": "critical" if critical_only else "full",
        "manifest_sha256": manifest_hash,
        "verified_file_count": len(selected),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify Huiji crawler package integrity")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--critical-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = verify_package(args.root, critical_only=args.critical_only)
    except (OSError, PackageVerificationError) as exc:
        print(f"Package verification failed: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
