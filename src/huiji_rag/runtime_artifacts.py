"""Read-only resolution of one coherent installed RAG artifact snapshot."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from src.huiji_rag.active_pointer import (
    load_active_pointer,
    resolve_activation_evidence,
    resolve_generation_zero_evidence,
)
from src.huiji_rag.build.contracts import (
    CORPUS_BUILD_SCHEMA_VERSION,
    MEDIA_V3_MANIFEST_SCHEMA_VERSION,
    MEDIA_V3_ROW_SCHEMA_VERSION,
    MEDIA_V3_SCHEMA_VERSION,
    canonical_json_bytes,
)
from src.huiji_rag.io import build_paths
from src.huiji_rag.provenance import load_provenance_baseline


ArtifactCapability = Literal["legacy", "v2", "v3"]
SnapshotSource = Literal["installed_legacy", "active_pointer", "isolated_candidate"]

_SCHEMA_TO_CAPABILITY: Mapping[str, ArtifactCapability] = {
    "evb.media-asset/v1_legacy": "legacy",
    "evb.media-asset/v2": "v2",
    "evb.media-asset/v3": "v3",
}
_V2_MANIFEST_SCHEMAS = {
    "evb.media-assets-manifest/v2",
    "evb.media-artifact-manifest/v2",
}
_SHA256_CHARS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class RuntimeArtifactSnapshot:
    """A hash-pinned file tuple shared by text and media retrieval."""

    source_mode: SnapshotSource
    capability: ArtifactCapability
    artifact_schema_version: str
    build_version: str
    build_root: Path
    manifest_path: Path
    manifest_sha256: str
    parent_blocks: Path
    child_blocks: Path
    media_assets: Path
    child_bm25: Path
    media_bm25: Path
    collection_name: str
    artifact_sha256: Mapping[str, str]
    tuple_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_sha256",
            MappingProxyType(dict(sorted(self.artifact_sha256.items()))),
        )


def resolve_runtime_artifact_snapshot(cfg: Any) -> RuntimeArtifactSnapshot:
    """Resolve installed legacy or active-pointer v2/v3 without field inference."""
    huiji = getattr(cfg, "huiji", None)
    if huiji is None:
        raise ValueError("Huiji runtime configuration is missing")
    processed_root = Path(getattr(huiji, "processed_root", "")).resolve()
    pointer_path = processed_root / "active_build.v1.json"
    collection_name = str(
        getattr(getattr(cfg, "vectorstore", None), "collection_name", "")
        or getattr(huiji, "text_collection_name", "")
    )
    if pointer_path.is_file():
        return _resolve_active_pointer(
            processed_root,
            pointer_path,
            collection_name=collection_name,
        )
    return _resolve_installed_legacy(cfg, collection_name=collection_name)


def resolve_isolated_candidate_snapshot(
    cfg: Any,
    build_root: str | Path,
    *,
    expected_manifest_sha256: str,
    collection_name: str,
    active_snapshot: RuntimeArtifactSnapshot | None = None,
) -> RuntimeArtifactSnapshot:
    """Resolve a hash-pinned v3 candidate while refusing the active tuple."""
    huiji = getattr(cfg, "huiji", None)
    if huiji is None:
        raise ValueError("Huiji runtime configuration is missing")
    processed_root = Path(getattr(huiji, "processed_root", "")).resolve()
    candidate_root = _contained(processed_root, Path(build_root).resolve())
    if candidate_root.parent != processed_root:
        raise ValueError("isolated candidate must be a direct processed-root child")
    target_collection = str(collection_name or "").strip()
    if not target_collection:
        raise ValueError("isolated candidate collection is blank")

    active = active_snapshot or resolve_runtime_artifact_snapshot(cfg)
    active_collections = {
        str(active.collection_name or "").strip(),
        str(getattr(getattr(cfg, "vectorstore", None), "collection_name", "")).strip(),
        str(getattr(huiji, "text_collection_name", "")).strip(),
    }
    if target_collection in active_collections:
        raise ValueError("isolated candidate collection is active")
    if candidate_root == active.build_root:
        raise ValueError("isolated candidate build root is active")

    manifest_path = _contained(candidate_root, candidate_root / "build_manifest.json")
    manifest_sha = _sha256_file(manifest_path)
    expected_sha = _sha256_value(
        expected_manifest_sha256, "isolated candidate manifest"
    )
    if manifest_sha != expected_sha:
        raise ValueError("isolated candidate build manifest SHA-256 mismatch")
    manifest = _load_json_object(manifest_path, "isolated candidate manifest")
    build_version = _safe_build_version(manifest.get("build_version"))
    if candidate_root.name != build_version:
        raise ValueError("isolated candidate build version differs from its path")
    if manifest.get("state") != "ready_for_embedding":
        raise ValueError("isolated candidate is not ready_for_embedding")
    blockers = manifest.get("blockers")
    if not isinstance(blockers, list) or blockers:
        raise ValueError("isolated candidate has blockers")

    paths, hashes = _resolve_v3_files(candidate_root, manifest)
    active_paths = {
        active.parent_blocks,
        active.child_blocks,
        active.media_assets,
        active.child_bm25,
        active.media_bm25,
    }
    if any(path in active_paths for path in paths.values()):
        raise ValueError("isolated candidate artifact overlaps the active tuple")
    return _make_snapshot(
        source_mode="isolated_candidate",
        capability="v3",
        artifact_schema_version=MEDIA_V3_ROW_SCHEMA_VERSION,
        build_version=build_version,
        build_root=candidate_root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        paths=paths,
        artifact_sha256=hashes,
        collection_name=target_collection,
    )


def _resolve_active_pointer(
    processed_root: Path,
    pointer_path: Path,
    *,
    collection_name: str,
) -> RuntimeArtifactSnapshot:
    pointer = load_active_pointer(pointer_path)

    artifact_schema = str(pointer.get("artifact_schema_version") or "")
    capability = _SCHEMA_TO_CAPABILITY.get(artifact_schema)
    if capability is None:
        raise ValueError("active pointer artifact schema is unsupported")
    build_version = _safe_build_version(pointer.get("build_version"))
    build_root = _contained(processed_root, processed_root / build_version)
    manifest_path = _contained(build_root, build_root / "build_manifest.json")
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != _sha256_value(pointer.get("build_manifest_sha256"), "active manifest"):
        raise ValueError("active pointer build manifest SHA-256 mismatch")
    manifest = _load_json_object(manifest_path, "build manifest")
    declared_build = str(manifest.get("build_version") or build_version)
    if declared_build != build_version:
        raise ValueError("build manifest version does not match active pointer")

    if int(pointer["generation"]) == 0:
        paths, hashes = _resolve_generation_zero_files(
            processed_root,
            pointer,
            build_root=build_root,
        )
    elif capability == "v3":
        paths, hashes = _resolve_v3_files(build_root, manifest)
        _validate_activation_collection_manifest(
            processed_root,
            pointer,
            build_version=build_version,
            manifest_sha256=manifest_sha,
            paths=paths,
            hashes=hashes,
        )
    elif capability == "v2":
        paths, hashes = _resolve_v2_files(build_root, manifest)
    else:
        paths, hashes = _resolve_legacy_files(build_root)
    pointer_collection = str(pointer["milvus_collection_name"])
    if pointer_collection != collection_name:
        raise ValueError("active pointer collection differs from runtime configuration")
    return _make_snapshot(
        source_mode="active_pointer",
        capability=capability,
        artifact_schema_version=artifact_schema,
        build_version=build_version,
        build_root=build_root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        paths=paths,
        artifact_sha256=hashes,
        collection_name=pointer_collection,
    )


def _validate_activation_collection_manifest(
    processed_root: Path,
    pointer: Mapping[str, Any],
    *,
    build_version: str,
    manifest_sha256: str,
    paths: Mapping[str, Path],
    hashes: Mapping[str, str],
) -> None:
    collection_path, inventory_path = resolve_activation_evidence(
        processed_root, pointer
    )
    if _sha256_file(collection_path) != str(pointer["collection_manifest_sha256"]):
        raise ValueError("activation collection manifest SHA-256 mismatch")
    if _sha256_file(inventory_path) != str(pointer["deployment_inventory_sha256"]):
        raise ValueError("activation deployment inventory SHA-256 mismatch")
    collection = _load_canonical_json_object(
        collection_path, "activation collection manifest"
    )
    inventory = _load_canonical_json_object(
        inventory_path, "activation deployment inventory"
    )
    if collection.get("schema_version") != "evb.collection-manifest/v1":
        raise ValueError("activation collection manifest schema mismatch")
    if inventory.get("schema_version") != "huiji.activation-deployment-inventory/v1":
        raise ValueError("activation deployment inventory schema mismatch")
    if (
        collection.get("build_version") != build_version
        or collection.get("artifact_schema_version") != "evb.media-asset/v3"
    ):
        raise ValueError("activation collection manifest tuple mismatch")
    build_ref = collection.get("build_manifest")
    if not isinstance(build_ref, Mapping) or build_ref.get("sha256") != manifest_sha256:
        raise ValueError("activation build manifest reference mismatch")
    milvus = collection.get("milvus")
    if (
        not isinstance(milvus, Mapping)
        or milvus.get("collection") != pointer["milvus_collection_name"]
        or milvus.get("schema_sha256") != pointer["collection_schema_fingerprint"]
    ):
        raise ValueError("activation Milvus identity mismatch")
    embedding = collection.get("embedding")
    if (
        not isinstance(embedding, Mapping)
        or embedding.get("model_id") != pointer["embedding_model_id"]
        or embedding.get("config_fingerprint")
        != pointer["embedding_config_fingerprint"]
    ):
        raise ValueError("activation embedding identity mismatch")
    entries = collection.get("artifacts")
    if not isinstance(entries, Mapping):
        raise ValueError("activation artifact map is invalid")
    artifact_prefix = "data/processed/huiji"
    for name, digest in hashes.items():
        evidence = entries.get(name)
        path = paths.get(name)
        if not isinstance(evidence, Mapping) or path is None:
            raise ValueError(f"activation artifact is missing: {name}")
        relative = path.resolve().relative_to(processed_root.resolve()).as_posix()
        if (
            evidence.get("relative_path")
            != f"{artifact_prefix}/{relative}"
            or evidence.get("sha256") != digest
            or evidence.get("size") != path.stat().st_size
        ):
            raise ValueError(f"activation artifact identity mismatch: {name}")


def _resolve_generation_zero_files(
    processed_root: Path,
    pointer: Mapping[str, Any],
    *,
    build_root: Path,
) -> tuple[dict[str, Path], dict[str, str]]:
    collection_path, inventory_path = resolve_generation_zero_evidence(
        processed_root, pointer
    )
    if _sha256_file(collection_path) != str(pointer["collection_manifest_sha256"]):
        raise ValueError("generation-zero collection manifest SHA-256 mismatch")
    if _sha256_file(inventory_path) != str(pointer["deployment_inventory_sha256"]):
        raise ValueError("generation-zero deployment inventory SHA-256 mismatch")
    collection = _load_canonical_json_object(
        collection_path, "generation-zero collection manifest"
    )
    inventory = _load_canonical_json_object(
        inventory_path, "generation-zero deployment inventory"
    )
    if collection.get("schema_version") != "evb.collection-manifest/v1":
        raise ValueError("generation-zero collection manifest schema mismatch")
    if inventory.get("schema_version") != "huiji.generation-zero-deployment-inventory/v1":
        raise ValueError("generation-zero deployment inventory schema mismatch")
    if collection.get("build_version") != "dev":
        raise ValueError("generation-zero collection manifest build mismatch")
    if collection.get("artifact_schema_version") != "evb.media-asset/v1_legacy":
        raise ValueError("generation-zero collection manifest capability mismatch")
    if collection.get("milvus") != inventory.get("active_milvus"):
        raise ValueError("generation-zero Milvus evidence mismatch")
    if (
        not isinstance(collection.get("milvus"), Mapping)
        or collection["milvus"].get("collection") != pointer["milvus_collection_name"]
        or collection["milvus"].get("schema_sha256")
        != pointer["collection_schema_fingerprint"]
    ):
        raise ValueError("generation-zero Milvus identity mismatch")
    embedding = collection.get("embedding")
    if (
        not isinstance(embedding, Mapping)
        or embedding.get("model_id") != pointer["embedding_model_id"]
        or embedding.get("config_fingerprint")
        != pointer["embedding_config_fingerprint"]
    ):
        raise ValueError("generation-zero embedding identity mismatch")

    project_root = processed_root.parents[2]
    provenance = collection.get("installed_provenance")
    expected_provenance = project_root / "config/provenance/huiji-dev.v1.json"
    if not isinstance(provenance, Mapping):
        raise ValueError("generation-zero provenance reference is missing")
    if provenance.get("relative_path") != "config/provenance/huiji-dev.v1.json":
        raise ValueError("generation-zero provenance path mismatch")
    if _sha256_file(expected_provenance) != provenance.get("sha256"):
        raise ValueError("generation-zero provenance SHA-256 mismatch")

    entries = collection.get("artifacts")
    if not isinstance(entries, Mapping):
        raise ValueError("generation-zero artifact map is invalid")
    expected_paths = _resolve_legacy_files(build_root)[0]
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for name, target in expected_paths.items():
        evidence = entries.get(name)
        if not isinstance(evidence, Mapping):
            raise ValueError(f"generation-zero artifact is missing: {name}")
        relative = target.resolve().relative_to(project_root).as_posix()
        if evidence.get("relative_path") != relative:
            raise ValueError(f"generation-zero artifact path mismatch: {name}")
        digest = _sha256_file(target)
        if digest != evidence.get("sha256") or target.stat().st_size != evidence.get("size"):
            raise ValueError(f"generation-zero artifact identity mismatch: {name}")
        paths[name] = target.resolve()
        hashes[name] = digest
    return paths, hashes


def _resolve_installed_legacy(
    cfg: Any,
    *,
    collection_name: str,
) -> RuntimeArtifactSnapshot:
    paths = build_paths(cfg)
    huiji = cfg.huiji
    build_version = _safe_build_version(getattr(huiji, "build_version", ""))
    build_root = Path(paths.build_root).resolve()
    provenance_value = getattr(huiji, "provenance_baseline", None)
    provenance_path = Path(provenance_value).resolve() if provenance_value else None

    # Production's schema-less dev build is recognized only by its installed,
    # hash-pinned provenance baseline. Minimal test configurations omit it.
    if provenance_path is not None:
        project_root = Path(
            getattr(getattr(cfg, "paths", None), "project_root", Path.cwd())
        ).resolve()
        baseline, baseline_sha = load_provenance_baseline(
            provenance_path,
            project_root=project_root,
        )
        if str(baseline.get("build_version") or "") != build_version:
            raise ValueError("legacy provenance build version mismatch")
        artifact_rows = baseline.get("artifacts")
        bm25_rows = baseline.get("bm25")
        if not isinstance(artifact_rows, Mapping) or not isinstance(bm25_rows, Mapping):
            raise ValueError("legacy provenance artifact mapping is invalid")
        expected = {
            "parent_blocks": (paths.parent_blocks, artifact_rows.get("parent_blocks")),
            "child_blocks": (paths.child_blocks, artifact_rows.get("child_blocks")),
            "media_assets": (paths.media_assets, artifact_rows.get("media_assets")),
            "child_bm25": (paths.child_bm25, bm25_rows.get("child_bm25")),
            "media_bm25": (paths.media_bm25, bm25_rows.get("media_bm25")),
        }
        hashes: dict[str, str] = {}
        for name, (path, evidence) in expected.items():
            if not isinstance(evidence, Mapping):
                raise ValueError(f"legacy provenance is missing {name}")
            target = Path(path).resolve()
            relative = target.relative_to(project_root).as_posix()
            if str(evidence.get("relative_path") or "") != relative:
                raise ValueError(f"legacy provenance path mismatch: {name}")
            digest = _sha256_file(target)
            if digest != _sha256_value(evidence.get("sha256"), name):
                raise ValueError(f"legacy provenance SHA-256 mismatch: {name}")
            hashes[name] = digest
        resolved_paths = {name: Path(value[0]).resolve() for name, value in expected.items()}
        return _make_snapshot(
            source_mode="installed_legacy",
            capability="legacy",
            artifact_schema_version="evb.media-asset/v1_legacy",
            build_version=build_version,
            build_root=build_root,
            manifest_path=provenance_path,
            manifest_sha256=baseline_sha,
            paths=resolved_paths,
            artifact_sha256=hashes,
            collection_name=collection_name,
        )

    fixture_paths = {
        "parent_blocks": Path(paths.parent_blocks).resolve(),
        "child_blocks": Path(paths.child_blocks).resolve(),
        "media_assets": Path(paths.media_assets).resolve(),
        "child_bm25": Path(paths.child_bm25).resolve(),
        "media_bm25": Path(paths.media_bm25).resolve(),
    }
    hashes = {
        name: _sha256_file(path)
        for name, path in fixture_paths.items()
        if path.is_file()
    }
    manifest_path = Path(paths.build_manifest).resolve()
    manifest_sha = _sha256_file(manifest_path) if manifest_path.is_file() else ""
    return _make_snapshot(
        source_mode="installed_legacy",
        capability="legacy",
        artifact_schema_version="evb.media-asset/v1_legacy",
        build_version=build_version,
        build_root=build_root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        paths=fixture_paths,
        artifact_sha256=hashes,
        collection_name=collection_name,
    )


def _resolve_v3_files(
    build_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Path], dict[str, str]]:
    if manifest.get("schema_version") != CORPUS_BUILD_SCHEMA_VERSION:
        raise ValueError("v3 build manifest schema is unsupported")
    if manifest.get("artifact_schema_version") != MEDIA_V3_ROW_SCHEMA_VERSION:
        raise ValueError("v3 build manifest media capability mismatch")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or any(not isinstance(item, Mapping) for item in entries):
        raise ValueError("v3 build manifest artifact list is invalid")
    by_path = {str(item.get("relative_path") or ""): item for item in entries}
    required = {
        "parent_blocks": "parent_blocks.jsonl",
        "child_blocks": "child_blocks.jsonl",
        "media_assets": "runtime/media_assets.v3.jsonl",
        "child_bm25": "indexes/child_text_bm25.json",
        "media_bm25": "indexes/media_binding_bm25.v3.json",
        "media_schema": "runtime/media_assets.v3.schema.json",
        "media_manifest": "runtime/media_assets.v3.manifest.json",
    }
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for name, relative in required.items():
        entry = by_path.get(relative)
        if not isinstance(entry, Mapping):
            raise ValueError(f"v3 build manifest is missing {relative}")
        target = _contained(build_root, build_root / relative)
        digest = _sha256_file(target)
        if digest != _sha256_value(entry.get("sha256"), relative):
            raise ValueError(f"v3 artifact SHA-256 mismatch: {relative}")
        paths[name] = target
        hashes[name] = digest
    schema = _load_json_object(paths["media_schema"], "v3 media schema")
    if schema.get("schema_version") != MEDIA_V3_SCHEMA_VERSION:
        raise ValueError("v3 media schema document is unsupported")
    media_manifest = _load_json_object(paths["media_manifest"], "v3 media manifest")
    if media_manifest.get("schema_version") != MEDIA_V3_MANIFEST_SCHEMA_VERSION:
        raise ValueError("v3 media manifest schema is unsupported")
    return paths, hashes


def _resolve_v2_files(
    build_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Path], dict[str, str]]:
    if manifest.get("schema_version") != "evb.build-manifest/v1":
        raise ValueError("v2 build manifest schema is unsupported")
    relative_manifest = str(
        manifest.get("media_artifact_manifest")
        or "runtime/media_assets.v2.manifest.json"
    )
    media_manifest_path = _contained(build_root, build_root / relative_manifest)
    media_manifest_sha = _sha256_file(media_manifest_path)
    declared_manifest_sha = manifest.get("media_artifact_manifest_sha256")
    if declared_manifest_sha and media_manifest_sha != _sha256_value(
        declared_manifest_sha, "v2 media manifest"
    ):
        raise ValueError("v2 media manifest SHA-256 mismatch")
    media_manifest = _load_json_object(media_manifest_path, "v2 media manifest")
    if media_manifest.get("schema_version") not in _V2_MANIFEST_SCHEMAS:
        raise ValueError("v2 media manifest schema is unsupported")
    file_paths = media_manifest.get("file_paths")
    file_hashes = media_manifest.get("file_sha256")
    if not isinstance(file_paths, Mapping) or not isinstance(file_hashes, Mapping):
        raise ValueError("v2 media manifest files are invalid")
    required = {
        "parent_blocks": "parent_blocks",
        "child_blocks": "child_blocks",
        "media_assets": "media_assets_v2",
        "child_bm25": "child_bm25",
    }
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {"media_manifest": media_manifest_sha}
    for name, key in required.items():
        relative = str(file_paths.get(key) or "")
        if not relative:
            raise ValueError(f"v2 media manifest is missing {key}")
        target = _contained(build_root, build_root / relative)
        digest = _sha256_file(target)
        if digest != _sha256_value(file_hashes.get(key), key):
            raise ValueError(f"v2 artifact SHA-256 mismatch: {key}")
        paths[name] = target
        hashes[name] = digest
    paths["media_bm25"] = build_root / "indexes" / "media_asset_bm25.json"
    if paths["media_bm25"].is_file():
        hashes["media_bm25"] = _sha256_file(paths["media_bm25"])
    return paths, hashes


def _resolve_legacy_files(
    build_root: Path,
) -> tuple[dict[str, Path], dict[str, str]]:
    paths = {
        "parent_blocks": build_root / "parent_blocks.jsonl",
        "child_blocks": build_root / "child_blocks.jsonl",
        "media_assets": build_root / "media_assets.jsonl",
        "child_bm25": build_root / "indexes" / "child_text_bm25.json",
        "media_bm25": build_root / "indexes" / "media_asset_bm25.json",
    }
    hashes = {
        name: _sha256_file(path)
        for name, path in paths.items()
        if path.is_file()
    }
    return paths, hashes


def _make_snapshot(
    *,
    source_mode: SnapshotSource,
    capability: ArtifactCapability,
    artifact_schema_version: str,
    build_version: str,
    build_root: Path,
    manifest_path: Path,
    manifest_sha256: str,
    paths: Mapping[str, Path],
    artifact_sha256: Mapping[str, str],
    collection_name: str,
) -> RuntimeArtifactSnapshot:
    identity = {
        "source_mode": source_mode,
        "capability": capability,
        "artifact_schema_version": artifact_schema_version,
        "build_version": build_version,
        "manifest_sha256": manifest_sha256,
        "artifact_sha256": dict(sorted(artifact_sha256.items())),
        "collection_name": collection_name,
    }
    tuple_sha = hashlib.sha256(
        canonical_json_bytes(identity, trailing_newline=False)
    ).hexdigest()
    return RuntimeArtifactSnapshot(
        source_mode=source_mode,
        capability=capability,
        artifact_schema_version=artifact_schema_version,
        build_version=build_version,
        build_root=Path(build_root).resolve(),
        manifest_path=Path(manifest_path).resolve(),
        manifest_sha256=manifest_sha256,
        parent_blocks=Path(paths["parent_blocks"]).resolve(),
        child_blocks=Path(paths["child_blocks"]).resolve(),
        media_assets=Path(paths["media_assets"]).resolve(),
        child_bm25=Path(paths["child_bm25"]).resolve(),
        media_bm25=Path(paths["media_bm25"]).resolve(),
        collection_name=collection_name,
        artifact_sha256=artifact_sha256,
        tuple_sha256=tuple_sha,
    )


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_canonical_json_object(path: Path, label: str) -> dict[str, Any]:
    payload = _load_json_object(path, label)
    if path.read_bytes() != canonical_json_bytes(payload):
        raise ValueError(f"{label} bytes are not canonical")
    return payload


def _contained(root: Path, target: Path) -> Path:
    resolved_root = Path(root).resolve()
    resolved = Path(target).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"artifact containment violation: {resolved}")
    return resolved


def _safe_build_version(value: Any) -> str:
    version = str(value or "").strip()
    if not version or Path(version).name != version or version in {".", ".."}:
        raise ValueError("artifact build version is invalid")
    return version


def _sha256_file(path: Path) -> str:
    if not Path(path).is_file():
        raise ValueError(f"required artifact is missing: {path}")
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_value(value: Any, label: str) -> str:
    digest = str(value or "")
    if len(digest) != 64 or any(char not in _SHA256_CHARS for char in digest):
        raise ValueError(f"{label} SHA-256 is invalid")
    return digest


__all__ = [
    "ArtifactCapability",
    "RuntimeArtifactSnapshot",
    "resolve_isolated_candidate_snapshot",
    "resolve_runtime_artifact_snapshot",
]
