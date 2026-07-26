from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.huiji_rag.build.contracts import (
    ACTIVE_POINTER_SCHEMA_VERSION,
    CORPUS_BUILD_SCHEMA_VERSION,
    MEDIA_V3_MANIFEST_SCHEMA_VERSION,
    MEDIA_V3_ROW_SCHEMA_VERSION,
    MEDIA_V3_SCHEMA_VERSION,
)
from src.huiji_rag.runtime_artifacts import (
    resolve_isolated_candidate_snapshot,
    resolve_runtime_artifact_snapshot,
)
from src.rag.retriever import Retriever


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
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


def _cfg(processed_root: Path, *, collection: str = "fixture-collection"):
    return SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=processed_root.parent / "raw",
            processed_root=processed_root,
            build_version="legacy-build",
            text_collection_name=collection,
        ),
        vectorstore=SimpleNamespace(collection_name=collection),
    )


def _pointer(
    processed_root: Path,
    build: str,
    schema: str,
    collection: str,
    *,
    artifact_prefix: str = "data/processed/huiji",
) -> None:
    manifest = processed_root / build / "build_manifest.json"
    collection_sha = "b" * 64
    inventory_sha = "d" * 64
    if schema == MEDIA_V3_ROW_SCHEMA_VERSION:
        transaction = processed_root / "activation/transactions/fixture-activation"
        inventory = transaction / "deployment_inventory.v1.json"
        _write(
            inventory,
            {"schema_version": "huiji.activation-deployment-inventory/v1"},
        )
        inventory_sha = _sha(inventory)
        names = {
            "parent_blocks": "parent_blocks.jsonl",
            "child_blocks": "child_blocks.jsonl",
            "media_assets": "runtime/media_assets.v3.jsonl",
            "child_bm25": "indexes/child_text_bm25.json",
            "media_bm25": "indexes/media_binding_bm25.v3.json",
            "media_schema": "runtime/media_assets.v3.schema.json",
            "media_manifest": "runtime/media_assets.v3.manifest.json",
        }
        artifacts = {
            name: {
                "relative_path": (
                    f"{artifact_prefix.rstrip('/')}/"
                    f"{(processed_root / build / relative).relative_to(processed_root).as_posix()}"
                ),
                "sha256": _sha(processed_root / build / relative),
                "size": (processed_root / build / relative).stat().st_size,
            }
            for name, relative in names.items()
        }
        collection_manifest = transaction / "collection_manifest.v1.json"
        _write(
            collection_manifest,
            {
                "schema_version": "evb.collection-manifest/v1",
                "artifact_schema_version": MEDIA_V3_ROW_SCHEMA_VERSION,
                "build_version": build,
                "build_manifest": {"sha256": _sha(manifest)},
                "artifacts": artifacts,
                "milvus": {"collection": collection, "schema_sha256": "a" * 64},
                "embedding": {
                    "model_id": "fixture-model",
                    "config_fingerprint": "c" * 64,
                },
            },
        )
        collection_sha = _sha(collection_manifest)
    _write(
        processed_root / "active_build.v1.json",
        {
            "schema_version": ACTIVE_POINTER_SCHEMA_VERSION,
            "generation": 1,
            "build_version": build,
            "previous_build_version": "legacy-build",
            "build_manifest_sha256": _sha(manifest),
            "artifact_schema_version": schema,
            "milvus_collection_name": collection,
            "collection_schema_fingerprint": "a" * 64,
            "collection_manifest_sha256": collection_sha,
            "embedding_model_id": "fixture-model",
            "embedding_config_fingerprint": "c" * 64,
            "deployment_inventory_sha256": inventory_sha,
            "activation_epoch": 1,
            "activation_id": "fixture-activation",
            "activated_at_utc": "2026-07-22T01:02:03Z",
        },
    )


def _v2_build(processed_root: Path, build: str = "v2-build") -> None:
    root = processed_root / build
    files = {
        "parent_blocks": root / "parent_blocks.jsonl",
        "child_blocks": root / "child_blocks.jsonl",
        "media_assets_v2": root / "runtime" / "media_assets.v2.jsonl",
        "child_bm25": root / "indexes" / "child_text_bm25.json",
    }
    _write(files["parent_blocks"], "{}\n")
    _write(files["child_blocks"], "{}\n")
    # A v3-looking field in a v2 file must not change the manifest capability.
    _write(files["media_assets_v2"], '{"binding_id":"looks-like-v3"}\n')
    _write(files["child_bm25"], {})
    manifest_path = root / "runtime" / "media_assets.v2.manifest.json"
    _write(
        manifest_path,
        {
            "schema_version": "evb.media-artifact-manifest/v2",
            "file_paths": {
                key: path.relative_to(root).as_posix()
                for key, path in files.items()
            },
            "file_sha256": {key: _sha(path) for key, path in files.items()},
        },
    )
    _write(
        root / "build_manifest.json",
        {
            "schema_version": "evb.build-manifest/v1",
            "build_version": build,
            "media_artifact_manifest": manifest_path.relative_to(root).as_posix(),
            "media_artifact_manifest_sha256": _sha(manifest_path),
        },
    )


def _v3_build(processed_root: Path, build: str = "v3-build") -> None:
    root = processed_root / build
    files = {
        "parent_blocks.jsonl": "{}\n",
        "child_blocks.jsonl": "{}\n",
        "runtime/media_assets.v3.jsonl": "",
        "indexes/child_text_bm25.json": "{}",
        "indexes/media_binding_bm25.v3.json": "{}",
    }
    for relative, content in files.items():
        _write(root / relative, content)
    _write(
        root / "runtime" / "media_assets.v3.schema.json",
        {"schema_version": MEDIA_V3_SCHEMA_VERSION},
    )
    _write(
        root / "runtime" / "media_assets.v3.manifest.json",
        {"schema_version": MEDIA_V3_MANIFEST_SCHEMA_VERSION},
    )
    artifact_paths = [
        *files,
        "runtime/media_assets.v3.schema.json",
        "runtime/media_assets.v3.manifest.json",
    ]
    _write(
        root / "build_manifest.json",
        {
            "schema_version": CORPUS_BUILD_SCHEMA_VERSION,
            "artifact_schema_version": MEDIA_V3_ROW_SCHEMA_VERSION,
            "build_version": build,
            "state": "ready_for_embedding",
            "blockers": [],
            "artifacts": [
                {"relative_path": relative, "sha256": _sha(root / relative)}
                for relative in artifact_paths
            ],
        },
    )


def test_runtime_loader_uses_explicit_legacy_v2_and_v3_capabilities(tmp_path):
    legacy_root = tmp_path / "legacy"
    legacy_build = legacy_root / "legacy-build"
    _write(legacy_build / "media_assets.jsonl", '{"binding_id":"looks-like-v3"}\n')
    legacy = resolve_runtime_artifact_snapshot(_cfg(legacy_root))
    assert legacy.source_mode == "installed_legacy"
    assert legacy.capability == "legacy"

    v2_root = tmp_path / "v2"
    _v2_build(v2_root)
    _pointer(v2_root, "v2-build", "evb.media-asset/v2", "fixture-collection")
    v2 = resolve_runtime_artifact_snapshot(_cfg(v2_root))
    assert v2.source_mode == "active_pointer"
    assert v2.capability == "v2"
    assert v2.media_assets.name == "media_assets.v2.jsonl"

    v3_root = tmp_path / "v3"
    _v3_build(v3_root)
    _pointer(v3_root, "v3-build", MEDIA_V3_ROW_SCHEMA_VERSION, "fixture-collection")
    v3 = resolve_runtime_artifact_snapshot(_cfg(v3_root))
    assert v3.source_mode == "active_pointer"
    assert v3.capability == "v3"
    assert v3.media_assets.name == "media_assets.v3.jsonl"
    assert v3.collection_name == "fixture-collection"
    assert set(v3.artifact_sha256) >= {
        "parent_blocks", "child_blocks", "media_assets", "child_bm25", "media_bm25"
    }


def test_v3_snapshot_accepts_production_relocated_runtime_root(tmp_path):
    processed_root = tmp_path / "runtime" / "rag" / "huiji"
    _v3_build(processed_root)
    _pointer(
        processed_root,
        "v3-build",
        MEDIA_V3_ROW_SCHEMA_VERSION,
        "fixture-collection",
        artifact_prefix="data/processed/huiji",
    )

    snapshot = resolve_runtime_artifact_snapshot(_cfg(processed_root))

    assert snapshot.build_root == (processed_root / "v3-build").resolve()


def test_v3_snapshot_rejects_bm25_drift_and_collection_mismatch(tmp_path, monkeypatch):
    processed_root = tmp_path / "processed"
    _v3_build(processed_root)
    _pointer(
        processed_root,
        "v3-build",
        MEDIA_V3_ROW_SCHEMA_VERSION,
        "fixture-collection",
    )
    cfg = _cfg(processed_root)
    snapshot = resolve_runtime_artifact_snapshot(cfg)

    with pytest.raises(RuntimeError, match="tuple mismatch"):
        Retriever(
            cfg,
            SimpleNamespace(collection_name="wrong-collection"),
            artifact_snapshot=snapshot,
        )

    monkeypatch.setattr(Retriever, "_load_huiji_children", lambda self: None)
    retriever = Retriever(
        cfg,
        SimpleNamespace(collection_name="fixture-collection"),
        artifact_snapshot=snapshot,
    )
    assert retriever.artifact_snapshot is snapshot

    (processed_root / "v3-build" / "indexes" / "child_text_bm25.json").write_text(
        '{"drift":true}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="artifact SHA-256 mismatch"):
        resolve_runtime_artifact_snapshot(cfg)


def test_isolated_candidate_snapshot_rejects_active_or_mixed_tuple(tmp_path):
    processed_root = tmp_path / "processed"
    _v3_build(processed_root, "active-build")
    _pointer(
        processed_root,
        "active-build",
        MEDIA_V3_ROW_SCHEMA_VERSION,
        "active-collection",
    )
    _v3_build(processed_root, "candidate-build")
    cfg = _cfg(processed_root, collection="active-collection")
    candidate_manifest = processed_root / "candidate-build" / "build_manifest.json"

    snapshot = resolve_isolated_candidate_snapshot(
        cfg,
        processed_root / "candidate-build",
        expected_manifest_sha256=_sha(candidate_manifest),
        collection_name="shadow-collection",
    )

    assert snapshot.source_mode == "isolated_candidate"
    assert snapshot.capability == "v3"
    assert snapshot.build_version == "candidate-build"
    assert snapshot.collection_name == "shadow-collection"

    with pytest.raises(ValueError, match="collection is active"):
        resolve_isolated_candidate_snapshot(
            cfg,
            processed_root / "candidate-build",
            expected_manifest_sha256=_sha(candidate_manifest),
            collection_name="active-collection",
        )
    with pytest.raises(ValueError, match="build root is active"):
        resolve_isolated_candidate_snapshot(
            cfg,
            processed_root / "active-build",
            expected_manifest_sha256=_sha(
                processed_root / "active-build" / "build_manifest.json"
            ),
            collection_name="shadow-collection",
        )
    with pytest.raises(ValueError, match="manifest SHA-256 mismatch"):
        resolve_isolated_candidate_snapshot(
            cfg,
            processed_root / "candidate-build",
            expected_manifest_sha256="f" * 64,
            collection_name="shadow-collection",
        )
