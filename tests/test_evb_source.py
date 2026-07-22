from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.huiji_rag.models import ChildBlock, ParentBlock
from src.huiji_rag.source import (
    canonical_json_bytes,
    capture_source_inventory,
    sha256_json,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_canonical_json_hash_is_order_stable():
    first = {"name": "Sonetto", "nested": {"voice": ["en", "zh"]}}
    second = {"nested": {"voice": ["en", "zh"]}, "name": "Sonetto"}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert sha256_json(first) == sha256_json(second)
    assert canonical_json_bytes(first).endswith(b"\n")


def test_capture_source_inventory_rejects_root_escape_and_pyc(tmp_path):
    _write_jsonl(tmp_path / "pages.jsonl", [{"pageid": 1, "title": "A"}])
    _write_jsonl(
        tmp_path / "resources_manifest.jsonl",
        [{"name": "bad", "local_relpath": "../outside.bin"}],
    )

    with pytest.raises(ValueError, match="escapes raw root"):
        capture_source_inventory(tmp_path)

    _write_jsonl(
        tmp_path / "resources_manifest.jsonl",
        [{"name": "bytecode", "local_relpath": "assets/cache.pyc"}],
    )
    with pytest.raises(ValueError, match=r"\.pyc"):
        capture_source_inventory(tmp_path)


def test_parent_child_projection_ignores_media():
    parent = ParentBlock.from_json(
        {
            "parent_id": "char:1",
            "entity_id": "1",
            "asset_type": "voice",
            "media_id": "media:sha1:" + "a" * 40,
        }
    )
    child = ChildBlock.from_json(
        {
            "child_id": "char:1/voice:1",
            "parent_id": "char:1",
            "media_ids": ["media:sha1:" + "b" * 40],
            "filename": "voice.mp3",
            "asset_type": "voice",
        }
    )

    assert "media_id" not in parent.to_json()
    assert "asset_type" not in parent.to_json()
    assert child.media_ids == ("media:sha1:" + "b" * 40,)
    assert "filename" not in child.to_json()
