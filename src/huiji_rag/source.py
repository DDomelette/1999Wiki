"""Read-only access to Huiji source manifests and source inventory evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from src.huiji_rag.models import SourceInventory


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL row must be an object: {target}")
                yield row


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _resolve_under_root(raw_root: Path, value: str | Path) -> Path:
    candidate = (raw_root / Path(value)).resolve()
    try:
        candidate.relative_to(raw_root)
    except ValueError as error:
        raise ValueError(f"path escapes raw root: {value}") from error
    if candidate.suffix.casefold() == ".pyc":
        raise ValueError(f".pyc inputs are not permitted: {value}")
    return candidate


def _sorted_rows(rows: Iterator[dict[str, Any]]) -> tuple[dict[str, object], ...]:
    return tuple(
        sorted(
            (dict(row) for row in rows),
            key=canonical_json_bytes,
        )
    )


def capture_source_inventory(raw_root: Path) -> SourceInventory:
    root = Path(raw_root).resolve()
    if root.suffix.casefold() == ".pyc":
        raise ValueError(f".pyc inputs are not permitted: {raw_root}")
    if not root.is_dir():
        raise FileNotFoundError(f"raw root does not exist: {root}")

    pages_path = _resolve_under_root(root, "pages.jsonl")
    resources_path = _resolve_under_root(root, "resources_manifest.jsonl")
    if not pages_path.is_file() or not resources_path.is_file():
        raise FileNotFoundError("raw source manifests pages.jsonl and resources_manifest.jsonl are required")

    entity_rows = _sorted_rows(iter_jsonl(pages_path))
    resource_rows = _sorted_rows(iter_jsonl(resources_path))
    for row in resource_rows:
        local_relpath = row.get("local_relpath")
        if local_relpath:
            _resolve_under_root(root, str(local_relpath))

    inventory_payload = {
        "entity_rows": entity_rows,
        "resource_rows": resource_rows,
    }
    return SourceInventory(
        source_inventory_sha256=sha256_json(inventory_payload),
        entity_rows=entity_rows,
        resource_rows=resource_rows,
    )


class HuijiCrawlerDataSource:
    def __init__(self, raw_root: str | Path) -> None:
        self.raw_root = Path(raw_root)

    def _path(self, name: str) -> Path:
        return self.raw_root / name

    def iter_pages(self) -> Iterator[dict[str, Any]]:
        yield from iter_jsonl(self._path("pages.jsonl"))

    def iter_wikitext(self) -> Iterator[dict[str, Any]]:
        yield from iter_jsonl(self._path("wikitext.jsonl"))

    def iter_data_pages(self, prefix: str | None = None) -> Iterator[dict[str, Any]]:
        for row in iter_jsonl(self._path("data_pages.jsonl")):
            if prefix is not None and not str(row.get("title", "")).startswith(prefix):
                continue
            yield row

    def iter_resources(self) -> Iterator[dict[str, Any]]:
        yield from iter_jsonl(self._path("resources_manifest.jsonl"))

    def local_file_exists(self, local_relpath: str) -> bool:
        return (self.raw_root / local_relpath).exists()
