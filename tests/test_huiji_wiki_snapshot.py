from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.huiji_wiki.snapshot import resolve_wiki_snapshot, snapshot_is_stale


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )


def _pointer(build: str, manifest_sha: str, schema: str, generation: int) -> dict[str, object]:
    return {
        "schema_version": "evb.active-build/v1",
        "generation": generation,
        "build_version": build,
        "previous_build_version": "dev",
        "build_manifest_sha256": manifest_sha,
        "milvus_collection_name": "fixture-collection",
        "collection_schema_fingerprint": "a" * 64,
        "collection_manifest_sha256": "b" * 64,
        "embedding_model_id": "fixture-model",
        "embedding_config_fingerprint": "c" * 64,
        "artifact_schema_version": schema,
        "deployment_inventory_sha256": "d" * 64,
        "activation_epoch": generation,
        "activation_id": f"activation-{generation}",
        "activated_at_utc": "2026-07-22T01:02:03Z",
    }


def test_resolves_hash_pinned_legacy_snapshot_and_reuses_receipt(tmp_path: Path):
    root = tmp_path / "project"
    build = root / "data" / "processed" / "huiji" / "dev"
    build.mkdir(parents=True)
    for name in ("parent_blocks.jsonl", "child_blocks.jsonl", "media_assets.jsonl"):
        (build / name).write_text('{"id":1}\n', encoding="utf-8")
    _json(build / "build_manifest.json", {"build_version": "dev", "artifact_schema_version": "v1"})
    cfg = SimpleNamespace(huiji=SimpleNamespace(processed_root=root / "data/processed/huiji", build_version="dev"))

    first = resolve_wiki_snapshot(cfg, root, root / "evidence")
    second = resolve_wiki_snapshot(cfg, root, root / "evidence")

    assert first == second
    assert first.source_mode == "legacy"
    assert first.input_sha256["parent_blocks"] == hashlib.sha256((build / "parent_blocks.jsonl").read_bytes()).hexdigest()
    receipts = list((root / "evidence").rglob("wiki_import_snapshot.v1.json"))
    assert len(receipts) == 1


def test_rejects_missing_manifest_and_traversal_build(tmp_path: Path):
    root = tmp_path / "project"
    processed = root / "data/processed/huiji"
    processed.mkdir(parents=True)
    cfg = SimpleNamespace(huiji=SimpleNamespace(processed_root=processed, build_version="../outside"))
    with pytest.raises(ValueError, match="containment"):
        resolve_wiki_snapshot(cfg, root, root / "evidence")


def test_active_pointer_pins_v2_runtime_and_detects_pointer_change(tmp_path: Path):
    root = tmp_path / "project"
    processed = root / "data/processed/huiji"
    build = processed / "release-1"
    runtime = build / "runtime"
    runtime.mkdir(parents=True)
    for name in ("parent_blocks.jsonl", "child_blocks.jsonl"):
        (build / name).write_text('{"id":1}\n', encoding="utf-8")
    (runtime / "media_assets.v2.jsonl").write_text('{"media_id":"m1"}\n', encoding="utf-8")
    _json(runtime / "media_assets.v2.manifest.json", {"schema_version": "evb.media-assets-manifest/v2"})
    _json(build / "build_manifest.json", {"build_version": "release-1"})
    manifest_sha = hashlib.sha256((build / "build_manifest.json").read_bytes()).hexdigest()
    pointer = _pointer("release-1", manifest_sha, "evb.media-asset/v2", 2)
    _json(processed / "active_build.v1.json", pointer)
    cfg = SimpleNamespace(huiji=SimpleNamespace(processed_root=processed, build_version="dev"))

    snapshot = resolve_wiki_snapshot(cfg, root, root / "evidence")

    assert snapshot.media_assets == runtime / "media_assets.v2.jsonl"
    assert snapshot.generation == 2
    assert snapshot_is_stale(snapshot, processed, "dev") is False
    pointer["activation_epoch"] = 3
    _json(processed / "active_build.v1.json", pointer)
    assert snapshot_is_stale(snapshot, processed, "dev") is True


def test_active_pointer_pins_v3_runtime_with_unique_manifest_schema(tmp_path: Path):
    root = tmp_path / "project"
    processed = root / "data/processed/huiji"
    build = processed / "release-v3"
    runtime = build / "runtime"
    runtime.mkdir(parents=True)
    for name in ("parent_blocks.jsonl", "child_blocks.jsonl"):
        (build / name).write_text('{"id":1}\n', encoding="utf-8")
    (runtime / "media_assets.v3.jsonl").write_text(
        '{"artifact_schema_version":"evb.media-asset/v3"}\n', encoding="utf-8"
    )
    _json(runtime / "media_assets.v3.schema.json", {"schema_version": "evb.media-assets/v3"})
    _json(runtime / "media_assets.v3.manifest.json", {"schema_version": "evb.media-artifact-manifest/v3"})
    _json(build / "build_manifest.json", {"build_version": "release-v3"})
    manifest_sha = hashlib.sha256((build / "build_manifest.json").read_bytes()).hexdigest()
    _json(
        processed / "active_build.v1.json",
        _pointer("release-v3", manifest_sha, "evb.media-asset/v3", 3),
    )
    cfg = SimpleNamespace(huiji=SimpleNamespace(processed_root=processed, build_version="dev"))

    snapshot = resolve_wiki_snapshot(cfg, root, root / "evidence")

    assert snapshot.artifact_schema_version == "evb.media-asset/v3"
    assert snapshot.media_assets == runtime / "media_assets.v3.jsonl"
