"""Resolve one immutable, read-only artifact snapshot for Wiki imports."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Mapping, Any

from src.huiji_rag.active_pointer import (
    load_active_pointer,
    resolve_generation_zero_evidence,
)


@dataclass(frozen=True)
class WikiArtifactSnapshot:
    source_mode: Literal["active", "legacy"]
    build_version: str
    artifact_schema_version: str
    parent_blocks: Path
    child_blocks: Path
    media_assets: Path
    manifest_sha256: str
    input_sha256: Mapping[str, str]
    activation_id: str | None
    activation_epoch: int | None
    snapshot_sha256: str
    generation: int | None = None
    pointer_sha256: str | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contained(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"artifact containment violation: {candidate}")
    return candidate


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"required manifest is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def resolve_wiki_snapshot(cfg: Any, project_root: Path, evidence_root: Path) -> WikiArtifactSnapshot:
    project_root = Path(project_root).resolve()
    processed_root = _contained(project_root, Path(cfg.huiji.processed_root))
    pointer_path = processed_root / "active_build.v1.json"
    source_mode: Literal["active", "legacy"] = "active" if pointer_path.is_file() else "legacy"
    pointer: dict[str, Any] = load_active_pointer(pointer_path) if source_mode == "active" else {}
    build_version = str(pointer.get("build_version") or cfg.huiji.build_version)
    if not build_version or any(part in {"..", ""} for part in Path(build_version).parts):
        raise ValueError("artifact containment violation: invalid build version")

    configured_dir = processed_root / build_version
    artifact_dir = _contained(processed_root, configured_dir)
    manifest_path = artifact_dir / "build_manifest.json"
    manifest = _load_json(manifest_path)
    if str(manifest.get("build_version") or build_version) != build_version:
        raise ValueError("build manifest version does not match pinned snapshot")

    manifest_sha256 = _sha256(manifest_path)
    if source_mode == "active" and str(pointer["build_manifest_sha256"]).lower() != manifest_sha256:
        raise ValueError("active pointer build manifest hash mismatch")
    artifact_schema_version = str(pointer.get("artifact_schema_version") or manifest.get("artifact_schema_version") or manifest.get("schema_version") or "evb.media-asset/v1_legacy")
    if source_mode == "legacy":
        artifact_schema_version = "evb.media-asset/v1_legacy"
    media_path = artifact_dir / "media_assets.jsonl"
    if artifact_schema_version == "evb.media-asset/v2":
        media_path = artifact_dir / "runtime" / "media_assets.v2.jsonl"
        media_manifest = _load_json(artifact_dir / "runtime" / "media_assets.v2.manifest.json")
        if media_manifest.get("schema_version") not in {
            "evb.media-assets-manifest/v2",
            "evb.media-artifact-manifest/v2",
        }:
            raise ValueError("invalid v2 media manifest schema")
    elif artifact_schema_version == "evb.media-asset/v3":
        media_path = artifact_dir / "runtime" / "media_assets.v3.jsonl"
        media_schema = _load_json(artifact_dir / "runtime" / "media_assets.v3.schema.json")
        if media_schema.get("schema_version") != "evb.media-assets/v3":
            raise ValueError("invalid v3 media schema document")
        media_manifest = _load_json(artifact_dir / "runtime" / "media_assets.v3.manifest.json")
        if media_manifest.get("schema_version") != "evb.media-artifact-manifest/v3":
            raise ValueError("invalid v3 media manifest schema")
    paths = {
        "parent_blocks": _contained(artifact_dir, artifact_dir / "parent_blocks.jsonl"),
        "child_blocks": _contained(artifact_dir, artifact_dir / "child_blocks.jsonl"),
        "media_assets": _contained(artifact_dir, media_path),
    }
    for name, path in paths.items():
        if not path.is_file():
            raise ValueError(f"required artifact is missing: {name}")
    input_sha256 = {name: _sha256(path) for name, path in paths.items()}
    if source_mode == "active" and pointer.get("generation") == 0:
        collection_path, inventory_path = resolve_generation_zero_evidence(
            processed_root, pointer
        )
        if _sha256(collection_path) != pointer["collection_manifest_sha256"]:
            raise ValueError("generation-zero collection manifest hash mismatch")
        if _sha256(inventory_path) != pointer["deployment_inventory_sha256"]:
            raise ValueError("generation-zero deployment inventory hash mismatch")
        collection_manifest = _load_json(collection_path)
        entries = collection_manifest.get("artifacts")
        if not isinstance(entries, Mapping):
            raise ValueError("generation-zero artifact map is invalid")
        for name, digest in input_sha256.items():
            evidence = entries.get(name)
            if not isinstance(evidence, Mapping) or evidence.get("sha256") != digest:
                raise ValueError(f"generation-zero artifact hash mismatch: {name}")
    declared = manifest.get("input_sha256") or manifest.get("output_sha256") or {}
    if isinstance(declared, dict):
        for name, digest in input_sha256.items():
            expected = declared.get(name) or declared.get(f"{name}.jsonl")
            if expected and str(expected).lower() != digest:
                raise ValueError(f"artifact hash mismatch: {name}")

    identity = {
        "source_mode": source_mode,
        "build_version": build_version,
        "artifact_schema_version": artifact_schema_version,
        "manifest_sha256": manifest_sha256,
        "input_sha256": input_sha256,
        "activation_id": pointer.get("activation_id"),
        "activation_epoch": pointer.get("activation_epoch"),
        "generation": int(pointer["generation"]) if source_mode == "active" else None,
        "pointer_sha256": _sha256(pointer_path) if source_mode == "active" else None,
    }
    snapshot_sha256 = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    snapshot = WikiArtifactSnapshot(
        **identity,
        parent_blocks=paths["parent_blocks"],
        child_blocks=paths["child_blocks"],
        media_assets=paths["media_assets"],
        snapshot_sha256=snapshot_sha256,
    )

    receipt_dir = _contained(project_root, Path(evidence_root)) / snapshot_sha256
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / "wiki_import_snapshot.v1.json"
    public_receipt = {
        **identity,
        "schema_version": "wiki.import-snapshot/v1",
        "snapshot_sha256": snapshot_sha256,
        "artifacts": {name: str(path.relative_to(project_root)).replace("\\", "/") for name, path in paths.items()},
    }
    encoded = json.dumps(public_receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if receipt_path.exists():
        if receipt_path.read_text(encoding="utf-8") != encoded:
            raise ValueError("existing snapshot receipt differs from current verification")
    else:
        with receipt_path.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
    return snapshot


def snapshot_is_stale(snapshot: WikiArtifactSnapshot, processed_root: Path, configured_build: str) -> bool:
    pointer = Path(processed_root) / "active_build.v1.json"
    if snapshot.source_mode == "legacy":
        return pointer.exists() or configured_build != snapshot.build_version
    if not pointer.is_file() or snapshot.pointer_sha256 is None:
        return True
    try:
        return _sha256(pointer) != snapshot.pointer_sha256
    except OSError:
        return True
