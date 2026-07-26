#!/usr/bin/env python3
"""Verify the manifest-declared active RAG artifact closure without writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


EXPECTED_FILE_COUNT = 11
PROJECT_RELATIVE_PREFIX = ("data", "processed", "huiji")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class VerificationError(ValueError):
    """A safe, operator-facing closure verification failure."""


class TransientVerificationError(VerificationError):
    """A verification failure caused by a changing filesystem snapshot."""


FileSignature = tuple[int, int, int, int, int, int]
FingerprintEntry = tuple[str, str, int, int, int, int, int, int]


def _file_signature(path: Path, label: str) -> FileSignature:
    try:
        info = path.lstat()
    except OSError as error:
        raise TransientVerificationError(f"{label} disappeared") from error
    if not stat.S_ISREG(info.st_mode):
        raise VerificationError(f"{label} is not a regular file")
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _record_observation(
    path: Path,
    label: str,
    before: FileSignature,
    after: FileSignature,
    observed: dict[Path, FileSignature],
) -> None:
    if before != after:
        raise TransientVerificationError(
            f"{label} changed during verification"
        )
    previous = observed.get(path)
    if previous is not None and previous != after:
        raise TransientVerificationError(
            f"{label} changed during verification"
        )
    observed[path] = after


def _json_object(
    path: Path,
    label: str,
    observed: dict[Path, FileSignature],
) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError(f"{label} has a duplicate key")
            result[key] = value
        return result

    try:
        before = _file_signature(path, label)
        raw = path.read_bytes()
        after = _file_signature(path, label)
        _record_observation(path, label, before, after, observed)
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except VerificationError:
        raise
    except OSError as error:
        raise TransientVerificationError(
            f"{label} disappeared while being read"
        ) from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{label} is invalid JSON") from error
    if not isinstance(payload, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return payload


def _sha256_value(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise VerificationError(f"{label} SHA-256 is invalid")
    return value


def _size_value(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise VerificationError(f"{label} size is invalid")
    return value


def _safe_id(value: object, label: str) -> str:
    text = str(value or "")
    if SAFE_ID_RE.fullmatch(text) is None or text in {".", ".."}:
        raise VerificationError(f"{label} is invalid")
    return text


def _reject_symlink_components(root: Path, target: Path, label: str) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise VerificationError(f"{label} path escape") from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise VerificationError(f"{label} contains a symlink")


def _regular_file(root: Path, target: Path, label: str) -> Path:
    _reject_symlink_components(root, target, label)
    try:
        mode = target.stat().st_mode
    except OSError as error:
        raise VerificationError(f"{label} is missing") from error
    if not stat.S_ISREG(mode):
        raise VerificationError(f"{label} is not a regular file")
    try:
        resolved = target.resolve(strict=True)
    except OSError as error:
        raise TransientVerificationError(f"{label} disappeared") from error
    if resolved != root and root not in resolved.parents:
        raise VerificationError(f"{label} path escape")
    return target


def _fixed_path(root: Path, parts: tuple[str, ...], label: str) -> Path:
    target = root.joinpath(*parts)
    return _regular_file(root, target, label)


def _declared_parts(
    value: object,
    label: str,
    *,
    strip_project_prefix: bool,
) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise VerificationError(f"{label} relative path is missing")
    if "\\" in value or "\x00" in value:
        raise VerificationError(f"{label} path is not canonical")
    raw_parts = value.split("/")
    if value.startswith("/") or any(part == ".." for part in raw_parts):
        raise VerificationError(f"{label} path escape")
    if any(part in {"", "."} for part in raw_parts):
        raise VerificationError(f"{label} path is not canonical")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value:
        raise VerificationError(f"{label} path is not canonical")
    parts = pure.parts
    if strip_project_prefix and (
        parts[: len(PROJECT_RELATIVE_PREFIX)] == PROJECT_RELATIVE_PREFIX
    ):
        parts = parts[len(PROJECT_RELATIVE_PREFIX) :]
    if not parts:
        raise VerificationError(f"{label} relative path is invalid")
    return parts


def _declared_path(
    root: Path,
    value: object,
    label: str,
    *,
    strip_project_prefix: bool = True,
) -> Path:
    parts = _declared_parts(
        value,
        label,
        strip_project_prefix=strip_project_prefix,
    )
    if any(part in {"", ".", ".."} for part in parts):
        raise VerificationError(f"{label} path escape")
    return _regular_file(root, root.joinpath(*parts), label)


def _sha256_file(
    path: Path,
    label: str,
    observed: dict[Path, FileSignature],
) -> str:
    digest = hashlib.sha256()
    try:
        before = _file_signature(path, label)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = _file_signature(path, label)
    except OSError as error:
        raise TransientVerificationError(
            f"{path.name} disappeared while being hashed"
        ) from error
    _record_observation(path, label, before, after, observed)
    return digest.hexdigest()


def _verify_digest(
    path: Path,
    expected: object,
    label: str,
    observed: dict[Path, FileSignature],
) -> None:
    if _sha256_file(path, label, observed) != _sha256_value(expected, label):
        raise VerificationError(f"{label} hash mismatch")


def _verify_reference(
    root: Path,
    reference: object,
    label: str,
    observed: dict[Path, FileSignature],
) -> Path:
    if not isinstance(reference, Mapping):
        raise VerificationError(f"{label} reference is invalid")
    target = _declared_path(root, reference.get("relative_path"), label)
    expected_size = _size_value(reference.get("size"), label)
    try:
        actual_size = target.stat().st_size
    except OSError as error:
        raise TransientVerificationError(f"{label} disappeared") from error
    if actual_size != expected_size:
        raise VerificationError(f"{label} size mismatch")
    _verify_digest(target, reference.get("sha256"), label, observed)
    return target


def _closure_fingerprint(
    root: Path,
    verified_paths: set[Path],
    observed: Mapping[Path, FileSignature],
) -> tuple[FingerprintEntry, ...]:
    components: dict[str, FingerprintEntry] = {}
    try:
        root_info = root.lstat()
    except OSError as error:
        raise TransientVerificationError(
            "root directory disappeared"
        ) from error
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise VerificationError("root contains a symlink")
    components["."] = (
        ".",
        "directory",
        root_info.st_dev,
        root_info.st_ino,
        root_info.st_mode,
        root_info.st_size,
        root_info.st_mtime_ns,
        root_info.st_ctime_ns,
    )
    for path in sorted(verified_paths):
        relative = path.relative_to(root)
        current = root
        for index, part in enumerate(relative.parts):
            current = current / part
            key = current.relative_to(root).as_posix()
            try:
                info = current.lstat()
            except OSError as error:
                raise TransientVerificationError(
                    f"{path.name} disappeared"
                ) from error
            is_leaf = index == len(relative.parts) - 1
            expected_kind = "file" if is_leaf else "directory"
            if stat.S_ISLNK(info.st_mode):
                raise VerificationError(f"{path.name} contains a symlink")
            if (
                is_leaf and not stat.S_ISREG(info.st_mode)
            ) or (
                not is_leaf and not stat.S_ISDIR(info.st_mode)
            ):
                raise VerificationError(f"{path.name} has an invalid path component")
            entry: FingerprintEntry = (
                key,
                expected_kind,
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )
            existing = components.get(key)
            if existing is not None and existing != entry:
                raise TransientVerificationError(
                    "closure changed during verification"
                )
            components[key] = entry
            if is_leaf:
                signature = entry[2:]
                if observed.get(path) != signature:
                    raise TransientVerificationError(
                        f"{path.name} changed during verification"
                    )
    return tuple(components[key] for key in sorted(components))


def _verified_closure(
    root_value: str | Path,
) -> tuple[Path, set[Path], int, tuple[FingerprintEntry, ...]]:
    observed: dict[Path, FileSignature] = {}
    raw_root = Path(root_value)
    if raw_root.is_symlink():
        raise VerificationError("root contains a symlink")
    try:
        root = raw_root.resolve(strict=True)
    except OSError as error:
        raise VerificationError("root directory is missing") from error
    if not root.is_dir():
        raise VerificationError("root is not a directory")

    pointer_path = _fixed_path(root, ("active_build.v1.json",), "active pointer")
    pointer = _json_object(pointer_path, "active pointer", observed)
    if pointer.get("schema_version") != "evb.active-build/v1":
        raise VerificationError("active pointer schema is unsupported")
    build_version = _safe_id(pointer.get("build_version"), "build version")
    activation_id = _safe_id(pointer.get("activation_id"), "activation ID")

    build_manifest_path = _fixed_path(
        root,
        (build_version, "build_manifest.json"),
        "build manifest",
    )
    transaction_parts = ("activation", "transactions", activation_id)
    collection_manifest_path = _fixed_path(
        root,
        (*transaction_parts, "collection_manifest.v1.json"),
        "collection manifest",
    )
    deployment_inventory_path = _fixed_path(
        root,
        (*transaction_parts, "deployment_inventory.v1.json"),
        "deployment inventory",
    )
    _verify_digest(
        build_manifest_path,
        pointer.get("build_manifest_sha256"),
        "build manifest",
        observed,
    )
    _verify_digest(
        collection_manifest_path,
        pointer.get("collection_manifest_sha256"),
        "collection manifest",
        observed,
    )
    _verify_digest(
        deployment_inventory_path,
        pointer.get("deployment_inventory_sha256"),
        "deployment inventory",
        observed,
    )

    build_manifest = _json_object(build_manifest_path, "build manifest", observed)
    collection_manifest = _json_object(
        collection_manifest_path,
        "collection manifest",
        observed,
    )
    deployment_inventory = _json_object(
        deployment_inventory_path,
        "deployment inventory",
        observed,
    )
    if build_manifest.get("build_version") != build_version:
        raise VerificationError("build manifest version mismatch")
    if collection_manifest.get("schema_version") != "evb.collection-manifest/v1":
        raise VerificationError("collection manifest schema is unsupported")
    if collection_manifest.get("build_version") != build_version:
        raise VerificationError("collection manifest version mismatch")
    if (
        collection_manifest.get("artifact_schema_version")
        != pointer.get("artifact_schema_version")
    ):
        raise VerificationError("collection manifest artifact schema mismatch")
    if (
        deployment_inventory.get("schema_version")
        != "huiji.activation-deployment-inventory/v1"
    ):
        raise VerificationError("deployment inventory schema is unsupported")

    build_reference = collection_manifest.get("build_manifest")
    referenced_build_path = _verify_reference(
        root,
        build_reference,
        "build manifest reference",
        observed,
    )
    if referenced_build_path != build_manifest_path:
        raise VerificationError("build manifest reference path mismatch")
    if (
        isinstance(build_reference, Mapping)
        and build_reference.get("sha256") != pointer.get("build_manifest_sha256")
    ):
        raise VerificationError("build manifest reference hash mismatch")

    raw_build_entries = build_manifest.get("artifacts")
    if not isinstance(raw_build_entries, list):
        raise VerificationError("build manifest artifact list is invalid")
    build_entries: dict[str, Mapping[str, Any]] = {}
    build_root = root / build_version
    for index, entry in enumerate(raw_build_entries):
        if not isinstance(entry, Mapping):
            raise VerificationError("build manifest artifact entry is invalid")
        label = f"build manifest artifact {index}"
        parts = _declared_parts(
            entry.get("relative_path"),
            label,
            strip_project_prefix=False,
        )
        canonical = PurePosixPath(*parts).as_posix()
        if canonical in build_entries:
            raise VerificationError(
                "build manifest has a duplicate canonical artifact path"
            )
        _size_value(entry.get("size"), label)
        _sha256_value(entry.get("sha256"), label)
        build_entries[canonical] = entry

    artifact_references = collection_manifest.get("artifacts")
    if not isinstance(artifact_references, Mapping):
        raise VerificationError("collection manifest artifact map is invalid")
    verified_paths = {
        pointer_path,
        build_manifest_path,
        collection_manifest_path,
        deployment_inventory_path,
    }
    collection_entries: dict[Path, Mapping[str, Any]] = {}
    for name, reference in artifact_references.items():
        label = f"artifact {name}"
        target = _verify_reference(root, reference, label, observed)
        try:
            build_relative = target.relative_to(build_root).as_posix()
        except ValueError as error:
            raise VerificationError(f"{label} path escape") from error
        if target in collection_entries or target in verified_paths:
            raise VerificationError(f"{label} duplicates a closure path")
        if not isinstance(reference, Mapping):
            raise VerificationError(f"{label} reference is invalid")
        build_entry = build_entries.get(build_relative)
        if not isinstance(build_entry, Mapping):
            raise VerificationError(f"{label} is absent from build manifest")
        if any(
            build_entry.get(field) != reference.get(field)
            for field in ("sha256", "size")
        ):
            raise VerificationError(f"{label} manifests disagree")
        collection_entries[target] = reference

    verified_paths.update(collection_entries)

    if len(verified_paths) != EXPECTED_FILE_COUNT:
        raise VerificationError(
            f"closure count mismatch: expected {EXPECTED_FILE_COUNT}, "
            f"found {len(verified_paths)}"
        )
    try:
        total_bytes = sum(path.stat().st_size for path in verified_paths)
    except OSError as error:
        raise TransientVerificationError(
            "closure changed during size observation"
        ) from error
    fingerprint = _closure_fingerprint(root, verified_paths, observed)
    return root, verified_paths, total_bytes, fingerprint


def verify_closure(root_value: str | Path) -> tuple[int, int]:
    _, verified_paths, total_bytes, _ = _verified_closure(root_value)
    return len(verified_paths), total_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the active manifest-declared RAG artifact closure."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--metadata-json",
        action="store_true",
        help="emit verified relative paths as machine-readable JSON",
    )
    args = parser.parse_args(argv)
    try:
        root, verified_paths, total_bytes, fingerprint = _verified_closure(
            args.root
        )
    except TransientVerificationError as error:
        print(f"RAG closure verification failed: {error}", file=sys.stderr)
        return 75
    except VerificationError as error:
        print(f"RAG closure verification failed: {error}", file=sys.stderr)
        return 1
    if args.metadata_json:
        print(
            json.dumps(
                {
                    "count": len(verified_paths),
                    "total_bytes": total_bytes,
                    "files": sorted(
                        path.relative_to(root).as_posix()
                        for path in verified_paths
                    ),
                    "fingerprint": fingerprint,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        print(
            f"verified {len(verified_paths)} files totaling {total_bytes} bytes"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
