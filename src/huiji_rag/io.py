"""Filesystem helpers for Huiji RAG build artifacts."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from src.huiji_rag.models import BaselineEvidence, EvbBuildPaths, SourceInventory
from src.huiji_rag.normalizer import validate_safe_id
from src.huiji_rag.source import canonical_json_bytes, capture_source_inventory


@dataclass(frozen=True)
class HuijiBuildPaths:
    raw_root: Path
    build_root: Path
    parent_blocks: Path
    child_blocks: Path
    media_assets: Path
    build_manifest: Path
    excluded_entities: Path
    build_report: Path
    child_bm25: Path
    media_bm25: Path


@dataclass(frozen=True)
class CorpusCandidatePaths:
    build_root: Path
    build_manifest: Path
    build_report: Path
    parent_blocks: Path
    child_blocks: Path
    excluded_entities: Path
    runtime_root: Path
    media_assets_v3: Path
    media_schema_v3: Path
    media_manifest_v3: Path
    indexes_root: Path
    child_bm25: Path
    media_bm25_v3: Path
    diagnostic_root: Path
    binding_inventory_v3: Path
    voice_binding_inventory_v1: Path
    quarantine_v1: Path
    conflicts_v1: Path
    fidelity_ledger_v1: Path
    build_diff_v1: Path
    handoff_root: Path
    embedding_handoff_v1: Path


_CORPUS_BUILD_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def corpus_candidate_paths(
    processed_root: str | Path, build_version: str
) -> CorpusCandidatePaths:
    """Return the frozen v3 candidate layout under a containment-checked root."""
    if not isinstance(build_version, str) or not _CORPUS_BUILD_ID_RE.fullmatch(
        build_version
    ):
        raise ValueError("build_version must use the corpus candidate ID grammar")
    if build_version == "dev":
        raise ValueError("build_version dev is reserved for the installed legacy build")
    root = Path(processed_root).resolve()
    build_root = (root / build_version).resolve()
    try:
        build_root.relative_to(root)
    except ValueError as error:  # pragma: no cover - ID grammar excludes separators
        raise ValueError("candidate build root escapes processed root") from error
    runtime = build_root / "runtime"
    indexes = build_root / "indexes"
    diagnostic = build_root / "diagnostic"
    handoff = build_root / "handoff"
    return CorpusCandidatePaths(
        build_root=build_root,
        build_manifest=build_root / "build_manifest.json",
        build_report=build_root / "build_report.json",
        parent_blocks=build_root / "parent_blocks.jsonl",
        child_blocks=build_root / "child_blocks.jsonl",
        excluded_entities=build_root / "excluded_entities.jsonl",
        runtime_root=runtime,
        media_assets_v3=runtime / "media_assets.v3.jsonl",
        media_schema_v3=runtime / "media_assets.v3.schema.json",
        media_manifest_v3=runtime / "media_assets.v3.manifest.json",
        indexes_root=indexes,
        child_bm25=indexes / "child_text_bm25.json",
        media_bm25_v3=indexes / "media_binding_bm25.v3.json",
        diagnostic_root=diagnostic,
        binding_inventory_v3=diagnostic / "binding_inventory.v3.jsonl",
        voice_binding_inventory_v1=diagnostic / "voice_binding_inventory.v1.jsonl",
        quarantine_v1=diagnostic / "quarantine.v1.jsonl",
        conflicts_v1=diagnostic / "conflicts.v1.jsonl",
        fidelity_ledger_v1=diagnostic / "fidelity_ledger.v1.jsonl",
        build_diff_v1=diagnostic / "build_diff.v1.json",
        handoff_root=handoff,
        embedding_handoff_v1=handoff / "embedding_handoff.v1.json",
    )


def build_paths(cfg: Any) -> HuijiBuildPaths:
    huiji = getattr(cfg, "huiji", None)
    raw_root = Path(getattr(huiji, "raw_root", "data/huiji/res1999"))
    processed_root = Path(getattr(huiji, "processed_root", "data/processed/huiji"))
    build_version = str(getattr(huiji, "build_version", "dev"))
    build_root = processed_root / build_version
    indexes_root = build_root / "indexes"
    return HuijiBuildPaths(
        raw_root=raw_root,
        build_root=build_root,
        parent_blocks=build_root / "parent_blocks.jsonl",
        child_blocks=build_root / "child_blocks.jsonl",
        media_assets=build_root / "media_assets.jsonl",
        build_manifest=build_root / "build_manifest.json",
        excluded_entities=build_root / "excluded_entities.jsonl",
        build_report=build_root / "build_report.json",
        child_bm25=indexes_root / "child_text_bm25.json",
        media_bm25=indexes_root / "media_asset_bm25.json",
    )


def evb_build_paths(processed_root: Path, build_version: str) -> EvbBuildPaths:
    """Return containment-checked paths for a single isolated EVB build."""
    safe_version = validate_safe_id(build_version, "build_version")
    if safe_version == "dev":
        raise ValueError("build_version dev is not permitted for EVB builds")
    output_root = Path(processed_root).resolve()
    live_dev_root = (
        Path(__file__).resolve().parents[2] / "data" / "processed" / "huiji" / "dev"
    ).resolve()
    try:
        output_root.relative_to(live_dev_root)
    except ValueError:
        pass
    else:
        raise ValueError("EVB output_root must not target the live dev root or its descendants")
    build_root = (output_root / safe_version).resolve()
    try:
        build_root.relative_to(output_root)
    except ValueError as error:
        raise ValueError("EVB build root escapes processed root") from error
    indexes_root = build_root / "indexes"
    runtime_root = build_root / "runtime"
    diagnostic_root = build_root / "diagnostic"
    return EvbBuildPaths(
        output_root=output_root,
        build_root=build_root,
        indexes_root=indexes_root,
        runtime_root=runtime_root,
        diagnostic_root=diagnostic_root,
        binding_inventory=diagnostic_root / "binding_inventory.v1.jsonl",
        media_assets_v2=runtime_root / "media_assets.v2.jsonl",
        media_schema_v2=runtime_root / "media_assets.v2.schema.json",
        media_manifest_v2=runtime_root / "media_assets.v2.manifest.json",
        parent_blocks=build_root / "parent_blocks.jsonl",
        child_blocks=build_root / "child_blocks.jsonl",
        media_assets=build_root / "media_assets.jsonl",
        build_manifest=build_root / "build_manifest.json",
        build_report=build_root / "build_report.json",
        child_bm25=indexes_root / "child_text_bm25.json",
        media_bm25=indexes_root / "media_asset_bm25.json",
    )


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


_FULL_MEDIA_ID_RE = re.compile(r"media:sha1:[0-9a-f]{40}", re.IGNORECASE)
_FULL_SHA1_RE = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)


def capture_baseline_from_rows(
    inventory: SourceInventory,
    media_rows: Sequence[Mapping[str, object]],
    milvus_observation: Mapping[str, object],
) -> BaselineEvidence:
    valid_media_ids = {
        str(row.get("media_id") or "")
        for row in media_rows
        if _FULL_MEDIA_ID_RE.fullmatch(str(row.get("media_id") or ""))
    }
    valid_sha1s = {
        str(row.get("sha1") or "")
        for row in media_rows
        if _FULL_SHA1_RE.fullmatch(str(row.get("sha1") or ""))
    }
    observations = {
        "entity_row_count": len(inventory.entity_rows),
        "resource_row_count": len(inventory.resource_rows),
        "media_row_count": len(media_rows),
        "media_id_count": len(valid_media_ids),
        "media_sha1_count": len(valid_sha1s),
        "voice_media_row_count": sum(
            1 for row in media_rows if str(row.get("asset_type") or "") == "voice"
        ),
    }
    return BaselineEvidence(
        schema_version="evb.baseline/v1",
        source_inventory_sha256=inventory.source_inventory_sha256,
        observations=observations,
        milvus_observation=dict(milvus_observation),
    )


def _capture_milvus_observation(cfg: Any) -> dict[str, object]:
    from pymilvus import MilvusClient

    vectorstore = getattr(cfg, "vectorstore")
    collection_name = str(getattr(vectorstore, "collection_name"))
    client = MilvusClient(
        uri=str(getattr(vectorstore, "uri")),
        db_name=str(getattr(vectorstore, "db_name")),
    )
    if not client.has_collection(collection_name):
        return {
            "collection_name": collection_name,
            "exists": False,
            "schema": None,
            "row_count": None,
        }
    stats = client.get_collection_stats(collection_name)
    return {
        "collection_name": collection_name,
        "exists": True,
        "schema": client.describe_collection(collection_name),
        "row_count": int(stats.get("row_count", 0)),
    }


def _write_baseline_create_new(path: Path, evidence: BaselineEvidence) -> None:
    payload = {
        "schema_version": evidence.schema_version,
        "source_inventory_sha256": evidence.source_inventory_sha256,
        "observations": evidence.observations,
        "milvus_observation": evidence.milvus_observation,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(payload))


def capture_baseline(cfg: Any, build_version: str) -> BaselineEvidence:
    huiji = getattr(cfg, "huiji")
    build_root = Path(getattr(huiji, "processed_root")) / build_version
    parent_blocks = build_root / "parent_blocks.jsonl"
    child_blocks = build_root / "child_blocks.jsonl"
    media_assets = build_root / "media_assets.jsonl"
    missing = [path.name for path in (parent_blocks, child_blocks, media_assets) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required build output is missing: {', '.join(missing)}")

    # Parse parent and child output before capture; media is intentionally excluded from their projections.
    list(iter_jsonl(parent_blocks))
    list(iter_jsonl(child_blocks))
    inventory = capture_source_inventory(Path(getattr(huiji, "raw_root")))
    evidence = capture_baseline_from_rows(
        inventory,
        media_rows=list(iter_jsonl(media_assets)),
        milvus_observation=_capture_milvus_observation(cfg),
    )
    output = os.environ.get("EVB_BASELINE_PATH", "").strip()
    if not output:
        raise ValueError("EVB_BASELINE_PATH is required for baseline capture")
    _write_baseline_create_new(Path(output), evidence)
    return evidence
