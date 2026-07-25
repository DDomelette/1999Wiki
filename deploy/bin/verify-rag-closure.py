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


def _json_object(path: Path, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError(f"{label} has a duplicate key")
            result[key] = value
        return result

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except VerificationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{label} is invalid JSON") from error
    if not isinstance(payload, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return payload


def _sha256_value(value: object, label: str) -> str:
    digest = str(value or "")
    if SHA256_RE.fullmatch(digest) is None:
        raise VerificationError(f"{label} SHA-256 is invalid")
    return digest


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
    resolved = target.resolve(strict=True)
    if resolved != root and root not in resolved.parents:
        raise VerificationError(f"{label} path escape")
    return target


def _fixed_path(root: Path, parts: tuple[str, ...], label: str) -> Path:
    target = root.joinpath(*parts)
    return _regular_file(root, target, label)


def _declared_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise VerificationError(f"{label} relative path is missing")
    if "\\" in value or "\x00" in value:
        raise VerificationError(f"{label} path escape")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise VerificationError(f"{label} path escape")
    parts = pure.parts
    if parts[: len(PROJECT_RELATIVE_PREFIX)] == PROJECT_RELATIVE_PREFIX:
        parts = parts[len(PROJECT_RELATIVE_PREFIX) :]
    if not parts:
        raise VerificationError(f"{label} relative path is invalid")
    return _regular_file(root, root.joinpath(*parts), label)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise VerificationError(f"{path.name} could not be read") from error
    return digest.hexdigest()


def _verify_digest(path: Path, expected: object, label: str) -> None:
    if _sha256_file(path) != _sha256_value(expected, label):
        raise VerificationError(f"{label} hash mismatch")


def _verify_reference(
    root: Path,
    reference: object,
    label: str,
) -> Path:
    if not isinstance(reference, Mapping):
        raise VerificationError(f"{label} reference is invalid")
    target = _declared_path(root, reference.get("relative_path"), label)
    expected_size = _size_value(reference.get("size"), label)
    if target.stat().st_size != expected_size:
        raise VerificationError(f"{label} size mismatch")
    _verify_digest(target, reference.get("sha256"), label)
    return target


def verify_closure(root_value: str | Path) -> tuple[int, int]:
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
    pointer = _json_object(pointer_path, "active pointer")
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
    )
    _verify_digest(
        collection_manifest_path,
        pointer.get("collection_manifest_sha256"),
        "collection manifest",
    )
    _verify_digest(
        deployment_inventory_path,
        pointer.get("deployment_inventory_sha256"),
        "deployment inventory",
    )

    build_manifest = _json_object(build_manifest_path, "build manifest")
    collection_manifest = _json_object(
        collection_manifest_path,
        "collection manifest",
    )
    deployment_inventory = _json_object(
        deployment_inventory_path,
        "deployment inventory",
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
    for entry in raw_build_entries:
        if not isinstance(entry, Mapping):
            raise VerificationError("build manifest artifact entry is invalid")
        relative = entry.get("relative_path")
        if not isinstance(relative, str) or relative in build_entries:
            raise VerificationError("build manifest artifact path is invalid")
        build_entries[relative] = entry

    artifact_references = collection_manifest.get("artifacts")
    if not isinstance(artifact_references, Mapping):
        raise VerificationError("collection manifest artifact map is invalid")
    verified_paths = {
        pointer_path,
        build_manifest_path,
        collection_manifest_path,
        deployment_inventory_path,
    }
    build_root = root / build_version
    for name, reference in artifact_references.items():
        label = f"artifact {name}"
        target = _verify_reference(root, reference, label)
        try:
            build_relative = target.relative_to(build_root).as_posix()
        except ValueError as error:
            raise VerificationError(f"{label} path escape") from error
        build_entry = build_entries.get(build_relative)
        if not isinstance(build_entry, Mapping):
            raise VerificationError(f"{label} is absent from build manifest")
        if not isinstance(reference, Mapping) or any(
            build_entry.get(field) != reference.get(field)
            for field in ("sha256", "size")
        ):
            raise VerificationError(f"{label} manifests disagree")
        if target in verified_paths:
            raise VerificationError(f"{label} duplicates a closure path")
        verified_paths.add(target)

    if len(verified_paths) != EXPECTED_FILE_COUNT:
        raise VerificationError(
            f"closure count mismatch: expected {EXPECTED_FILE_COUNT}, "
            f"found {len(verified_paths)}"
        )
    total_bytes = sum(path.stat().st_size for path in verified_paths)
    return len(verified_paths), total_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the active manifest-declared RAG artifact closure."
    )
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        count, total_bytes = verify_closure(args.root)
    except VerificationError as error:
        print(f"RAG closure verification failed: {error}", file=sys.stderr)
        return 1
    print(f"verified {count} files totaling {total_bytes} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
