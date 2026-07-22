"""Strict, streaming inventory for the four authoritative crawler files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contracts import (
    CRAWLER_SOURCE_FILENAMES,
    CorpusSourceInventory,
    SourceFileEvidence,
    canonical_json_bytes,
)

try:
    import orjson as _orjson
except ImportError:  # pragma: no cover - production environment includes orjson
    _orjson = None


_FORBIDDEN_SOURCE_LABELS = {
    "assets",
    "documents",
    "minio",
    "mysql",
    "obsidian",
    "wiki_page_supplements",
}
_SOURCE_LABEL_FIELDS = {
    "source_kind",
    "source_mode",
    "source_system",
    "source_type",
    "storage_source",
}


def capture_corpus_source_inventory(
    raw_root: Path,
    *,
    filenames: Sequence[str] = CRAWLER_SOURCE_FILENAMES,
) -> CorpusSourceInventory:
    """Hash and validate exactly the authoritative crawler JSONL inputs."""
    if tuple(filenames) != CRAWLER_SOURCE_FILENAMES:
        raise ValueError("corpus source inventory accepts exactly the four crawler files")
    root_input = Path(raw_root)
    if root_input.is_symlink():
        raise ValueError("crawler raw root must not be a symlink")
    root = root_input.resolve(strict=True)
    if not root.is_dir():
        raise FileNotFoundError(f"crawler raw root is not a directory: {root}")

    evidence: list[SourceFileEvidence] = []
    for filename in CRAWLER_SOURCE_FILENAMES:
        path = _resolve_source_file(root, filename)
        evidence.append(_capture_file(path, root, filename))
    payload = {
        "schema_version": "huiji.crawler-source-inventory/v1",
        "files": [item.to_json() for item in evidence],
    }
    return CorpusSourceInventory(
        files=tuple(evidence),
        source_inventory_sha256=hashlib.sha256(
            canonical_json_bytes(payload, trailing_newline=False)
        ).hexdigest(),
    )


def capture_code_fingerprint(
    project_root: Path,
    participating_paths: Sequence[Path],
) -> dict[str, object]:
    """Fingerprint participating source bytes without Git metadata."""
    root = Path(project_root).resolve(strict=True)
    records: list[dict[str, str]] = []
    for candidate in sorted((Path(item) for item in participating_paths), key=lambda item: item.as_posix()):
        raw = candidate if candidate.is_absolute() else root / candidate
        if raw.is_symlink():
            raise ValueError(f"participating source must not be a symlink: {candidate}")
        path = raw.resolve(strict=True)
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(f"participating source escapes project root: {candidate}") from error
        if not path.is_file() or path.suffix.casefold() == ".pyc":
            raise ValueError(f"invalid participating source: {candidate}")
        records.append({"path": relative, "sha256": _hash_file(path)})
    if not records:
        raise ValueError("at least one participating source file is required")
    return {
        "schema_version": "huiji.builder-code-fingerprint/v1",
        "files": records,
        "code_fingerprint_sha256": hashlib.sha256(
            canonical_json_bytes(records, trailing_newline=False)
        ).hexdigest(),
    }


def verify_corpus_source_inventory(raw_root: Path, expected: CorpusSourceInventory) -> None:
    current = capture_corpus_source_inventory(raw_root)
    if current != expected:
        raise ValueError("crawler source inventory drifted after capture")


def _resolve_source_file(root: Path, filename: str) -> Path:
    if Path(filename).name != filename or Path(filename).suffix.casefold() != ".jsonl":
        raise ValueError(f"invalid crawler source filename: {filename}")
    raw = root / filename
    if raw.is_symlink():
        raise ValueError(f"crawler source must not be a symlink: {filename}")
    path = raw.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"crawler source escapes raw root: {filename}") from error
    if not path.is_file() or path.suffix.casefold() == ".pyc":
        raise FileNotFoundError(f"crawler source file is missing: {filename}")
    return path


def _capture_file(path: Path, root: Path, filename: str) -> SourceFileEvidence:
    before = _file_signature(path)
    digest = hashlib.sha256()
    identity_digest = hashlib.sha256()
    identities: set[tuple[object, ...]] = set()
    row_count = 0
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            digest.update(raw_line)
            if not raw_line.strip():
                continue
            row = _loads_object(raw_line, path, line_number)
            _validate_crawler_labels(row, filename, line_number)
            if filename == "resources_manifest.jsonl":
                _validate_local_relpath(root, row, line_number)
            identity = _source_identity(filename, row, line_number)
            if identity in identities:
                raise ValueError(
                    f"duplicate source identity in {filename} at row {line_number}: {identity!r}"
                )
            identities.add(identity)
            identity_digest.update(canonical_json_bytes(identity, trailing_newline=False))
            identity_digest.update(b"\n")
            row_count += 1
    after = _file_signature(path)
    if before != after:
        raise ValueError(f"crawler source changed while being read: {filename}")
    return SourceFileEvidence(
        relative_path=filename,
        sha256=digest.hexdigest(),
        size=after[0],
        row_count=row_count,
        identity_sha256=identity_digest.hexdigest(),
    )


def _source_identity(
    filename: str,
    row: Mapping[str, Any],
    line_number: int,
) -> tuple[object, ...]:
    if filename == "pages.jsonl":
        fields = ("site", "pageid", "seen_at")
    elif filename in {"wikitext.jsonl", "data_pages.jsonl"}:
        fields = ("site", "pageid", "revid")
    elif filename == "resources_manifest.jsonl":
        fields = ("site", "title", "sha1", "url")
    else:  # pragma: no cover - allowlist makes this unreachable
        raise ValueError(f"unsupported crawler source file: {filename}")
    values = tuple(row.get(field) for field in fields)
    if any(value is None or value == "" for value in values):
        raise ValueError(
            f"crawler source identity is incomplete in {filename} at row {line_number}: {fields}"
        )
    return values


def _validate_crawler_labels(
    row: Mapping[str, Any],
    filename: str,
    line_number: int,
) -> None:
    if row.get("site") != "res1999":
        raise ValueError(f"non-res1999 crawler row in {filename} at row {line_number}")
    if filename == "resources_manifest.jsonl" and row.get("source") != "huiji_file_namespace":
        raise ValueError(f"non-crawler resource source in {filename} at row {line_number}")
    for field in _SOURCE_LABEL_FIELDS:
        value = str(row.get(field) or "").strip().casefold()
        if value in _FORBIDDEN_SOURCE_LABELS:
            raise ValueError(
                f"forbidden source label {value!r} in {filename} at row {line_number}"
            )


def _validate_local_relpath(root: Path, row: Mapping[str, Any], line_number: int) -> None:
    value = str(row.get("local_relpath") or "")
    if not value:
        return
    relative = Path(value)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError(f"resource local_relpath escapes raw root at row {line_number}: {value}")
    if relative.suffix.casefold() == ".pyc":
        raise ValueError(f"invalid resource local_relpath at row {line_number}: {value}")


def _loads_object(raw: bytes, path: Path, line_number: int) -> dict[str, Any]:
    try:
        value = _orjson.loads(raw) if _orjson is not None else json.loads(raw)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid JSON in {path.name} at row {line_number}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSONL row must be an object in {path.name} at row {line_number}")
    return value


def _file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
