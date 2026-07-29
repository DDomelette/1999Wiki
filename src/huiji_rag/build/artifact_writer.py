"""Create-new canonical artifacts and closure verification for corpus v3."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from src.huiji_rag.io import CorpusCandidatePaths, corpus_candidate_paths
from src.rag.chinese_analyzer import AnalyzerIdentity, ChineseBM25Analyzer
from src.rag.sparse import LocalBM25SparseIndex, canonical_child_corpus_sha256

from .contracts import (
    CHILD_BLOCK_SCHEMA_VERSION,
    CORPUS_BUILD_SCHEMA_VERSION,
    MEDIA_V3_MANIFEST_SCHEMA_VERSION,
    MEDIA_V3_ROW_SCHEMA_VERSION,
    MEDIA_V3_SCHEMA_VERSION,
    PARENT_BLOCK_SCHEMA_VERSION,
    BuildState,
    CorpusSourceInventory,
    VoiceBindingResult,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    media_v3_schema_document,
    normalize_media_v3_rows,
    validate_media_v3_row,
)
from .fidelity import FidelityResult
from .projection import CorpusProjection


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SELF_MANIFEST_PATH = "build_manifest.json"
_BM25_PROBES = (
    "槲寄生的基础资料",
    "十四行诗的技能是什么",
    "Data:Story/304502",
    "Skill-30410111",
    "Banner_今夜星光灿烂.png",
)


def _default_bm25_analyzer_identity() -> AnalyzerIdentity:
    return ChineseBM25Analyzer().identity


@dataclass(frozen=True)
class CandidateArtifactInput:
    build_version: str
    projection: CorpusProjection
    media_rows: tuple[Mapping[str, Any], ...]
    binding_inventory: tuple[Mapping[str, Any], ...]
    voice_result: VoiceBindingResult
    fidelity: FidelityResult
    source_inventory: CorpusSourceInventory
    code_fingerprint_sha256: str
    config_fingerprint_sha256: str
    fidelity_baseline_path: str
    fidelity_baseline_sha256: str
    bm25_analyzer_identity: AnalyzerIdentity = field(
        default_factory=_default_bm25_analyzer_identity
    )
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    blockers: tuple[str, ...] = ()
    protected_state_references: Mapping[str, Any] = field(default_factory=dict)
    embedding_config_fingerprint_sha256: str = ""
    forbidden_collection_names: tuple[str, ...] = ()
    generated_at_utc: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_rows", tuple(self.media_rows))
        object.__setattr__(self, "binding_inventory", tuple(self.binding_inventory))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(
            self,
            "protected_state_references",
            MappingProxyType(dict(self.protected_state_references)),
        )
        object.__setattr__(
            self,
            "forbidden_collection_names",
            tuple(sorted(set(self.forbidden_collection_names))),
        )


@dataclass(frozen=True)
class CandidateWriteResult:
    paths: CorpusCandidatePaths
    state: BuildState
    build_manifest_sha256: str
    semantic_artifact_sha256: Mapping[str, str]
    blockers: tuple[str, ...]
    row_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "semantic_artifact_sha256",
            MappingProxyType(dict(sorted(self.semantic_artifact_sha256.items()))),
        )
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(
            self, "row_counts", MappingProxyType(dict(sorted(self.row_counts.items())))
        )


@dataclass(frozen=True)
class _Bm25Snapshot:
    analyzer: ChineseBM25Analyzer
    analyzer_payload: Mapping[str, object]
    bm25_payload: Mapping[str, float]
    analyzer_probe_sha256: str


def write_candidate_artifacts(
    processed_root: str | Path,
    request: CandidateArtifactInput,
) -> CandidateWriteResult:
    """Write one immutable candidate. A failed partial root is never reused."""
    paths = corpus_candidate_paths(processed_root, request.build_version)
    if paths.build_root.exists():
        raise FileExistsError(f"candidate build root already exists: {paths.build_root}")
    _validate_sha(request.code_fingerprint_sha256, "code fingerprint")
    _validate_sha(request.config_fingerprint_sha256, "config fingerprint")
    _validate_sha(request.fidelity_baseline_sha256, "fidelity baseline")
    if request.embedding_config_fingerprint_sha256:
        _validate_sha(
            request.embedding_config_fingerprint_sha256,
            "embedding config fingerprint",
        )
    bm25_snapshot = _validated_bm25_snapshot(
        request.bm25_analyzer_identity,
        request.bm25_k1,
        request.bm25_b,
    )

    parent_rows = sorted(
        (parent.to_json() for parent in request.projection.parents),
        key=lambda row: str(row["parent_id"]),
    )
    child_rows = sorted(
        (child.to_json() for child in request.projection.children),
        key=lambda row: str(row["child_id"]),
    )
    media_rows = sorted(
        (validate_media_v3_row(dict(row)) for row in request.media_rows),
        key=_media_sort_key,
    )
    _require_unique(parent_rows, "parent_id", "parent")
    _require_unique(child_rows, "child_id", "child")
    _require_unique(media_rows, "binding_id", "media binding")
    resources, bindings = normalize_media_v3_rows(media_rows)

    child_ids = {str(row["child_id"]) for row in child_rows}
    unknown_media_children = sorted(
        {str(row["child_id"]) for row in media_rows} - child_ids
    )
    derived_blockers: list[str] = []
    if unknown_media_children:
        derived_blockers.append(
            f"media_unknown_child:{len(unknown_media_children)}"
        )
    unavailable_count = sum(not bool(row["is_available"]) for row in media_rows)
    if unavailable_count:
        derived_blockers.append(f"media_unavailable:{unavailable_count}")
    inventory_ids = [
        str(row.get("binding_id") or "") for row in request.binding_inventory
    ]
    binding_ids = [str(row["binding_id"]) for row in media_rows]
    if sorted(inventory_ids) != sorted(binding_ids):
        derived_blockers.append("binding_inventory_runtime_multiset_mismatch")
    if not request.embedding_config_fingerprint_sha256:
        derived_blockers.append("embedding_config_fingerprint_missing")

    blockers = sorted(
        set(
            (
                *request.blockers,
                *request.fidelity.blockers,
                *derived_blockers,
                *(("voice_binding_gate_blocked",)
                  if request.voice_result.ready_gate_blocked
                  else ()),
            )
        )
    )
    state = BuildState.BLOCKED if blockers else BuildState.READY_FOR_EMBEDDING
    paths.build_root.mkdir(parents=True, exist_ok=False)

    files: dict[str, dict[str, Any]] = {}
    semantic_hashes: dict[str, str] = {}

    _write_jsonl_artifact(
        paths,
        paths.parent_blocks,
        parent_rows,
        PARENT_BLOCK_SCHEMA_VERSION,
        files,
        semantic_hashes,
    )
    _write_jsonl_artifact(
        paths,
        paths.child_blocks,
        child_rows,
        CHILD_BLOCK_SCHEMA_VERSION,
        files,
        semantic_hashes,
    )
    excluded_rows = sorted(
        (item.to_json() for item in request.projection.exclusions),
        key=lambda row: canonical_json_bytes(row, trailing_newline=False),
    )
    _write_jsonl_artifact(
        paths,
        paths.excluded_entities,
        excluded_rows,
        "huiji.projection-exclusions/v1",
        files,
        semantic_hashes,
    )

    media_bytes = canonical_jsonl_bytes(media_rows)
    _write_bytes_create_new(paths.media_assets_v3, media_bytes)
    _add_file_entry(
        paths,
        paths.media_assets_v3,
        MEDIA_V3_ROW_SCHEMA_VERSION,
        len(media_rows),
        files,
    )
    semantic_hashes[_relative(paths, paths.media_assets_v3)] = _sha256(media_bytes)

    schema_bytes = canonical_json_bytes(media_v3_schema_document())
    _write_bytes_create_new(paths.media_schema_v3, schema_bytes)
    _add_file_entry(
        paths, paths.media_schema_v3, MEDIA_V3_SCHEMA_VERSION, None, files
    )
    semantic_hashes[_relative(paths, paths.media_schema_v3)] = _sha256(schema_bytes)

    child_bm25, child_metrics = _bm25_payload(
        child_rows,
        id_field="child_id",
        record_kind="child",
        semantic_sha256=canonical_child_corpus_sha256(child_rows),
        snapshot=bm25_snapshot,
    )
    media_semantic_sha256 = _canonical_rows_sha256(media_rows)
    media_bm25, media_metrics = _bm25_payload(
        media_rows,
        id_field="binding_id",
        record_kind="media_binding",
        semantic_sha256=media_semantic_sha256,
        snapshot=bm25_snapshot,
    )
    _write_json_artifact(
        paths,
        paths.child_bm25,
        child_bm25,
        "huiji.bm25-index/v3",
        len(child_rows),
        files,
        semantic_hashes,
    )
    _write_json_artifact(
        paths,
        paths.media_bm25_v3,
        media_bm25,
        "huiji.media-binding-bm25/v4",
        len(media_rows),
        files,
        semantic_hashes,
    )

    binding_inventory = sorted(
        (dict(row) for row in request.binding_inventory),
        key=lambda row: str(row.get("binding_id") or ""),
    )
    voice_inventory, quarantine, conflicts = _voice_diagnostics(request.voice_result)
    fidelity_rows = [dict(row) for row in request.fidelity.ledger_rows]
    _write_jsonl_artifact(
        paths,
        paths.binding_inventory_v3,
        binding_inventory,
        "huiji.media-binding-inventory/v3",
        files,
        semantic_hashes,
    )
    _write_jsonl_artifact(
        paths,
        paths.voice_binding_inventory_v1,
        voice_inventory,
        "huiji.voice-binding-inventory/v1",
        files,
        semantic_hashes,
    )
    _write_jsonl_artifact(
        paths,
        paths.quarantine_v1,
        quarantine,
        "huiji.voice-quarantine/v1",
        files,
        semantic_hashes,
    )
    _write_jsonl_artifact(
        paths,
        paths.conflicts_v1,
        conflicts,
        "huiji.voice-conflicts/v1",
        files,
        semantic_hashes,
    )
    _write_jsonl_artifact(
        paths,
        paths.fidelity_ledger_v1,
        fidelity_rows,
        "huiji.fidelity-ledger/v1",
        files,
        semantic_hashes,
    )
    _write_json_artifact(
        paths,
        paths.build_diff_v1,
        dict(request.fidelity.build_diff),
        "huiji.build-diff/v1",
        None,
        files,
        semantic_hashes,
    )

    media_manifest = {
        "schema_version": MEDIA_V3_MANIFEST_SCHEMA_VERSION,
        "row_schema_version": MEDIA_V3_ROW_SCHEMA_VERSION,
        "schema_document_version": MEDIA_V3_SCHEMA_VERSION,
        "files": {
            "media_assets": _manifest_file_projection(
                files[_relative(paths, paths.media_assets_v3)]
            ),
            "media_schema": _manifest_file_projection(
                files[_relative(paths, paths.media_schema_v3)]
            ),
        },
        "binding_count": len(media_rows),
        "resource_count": len(resources),
        "shared_resource_group_count": _shared_resource_count(media_rows),
        "ordered_binding_ids_sha256": media_metrics["ordered_ids_sha256"],
        "semantic_corpus_sha256": media_semantic_sha256,
    }
    _write_json_artifact(
        paths,
        paths.media_manifest_v3,
        media_manifest,
        MEDIA_V3_MANIFEST_SCHEMA_VERSION,
        None,
        files,
        semantic_hashes,
    )

    row_counts = {
        "parents": len(parent_rows),
        "children": len(child_rows),
        "excluded": len(excluded_rows),
        "media_bindings": len(media_rows),
        "media_resources": len(resources),
        "binding_inventory": len(binding_inventory),
        "voice_binding_inventory": len(voice_inventory),
        "quarantine": len(quarantine),
        "conflicts": len(conflicts),
        "fidelity_ledger": len(fidelity_rows),
    }
    handoff_created = False
    if state is BuildState.READY_FOR_EMBEDDING:
        handoff = {
            "schema_version": "huiji.embedding-handoff/v1",
            "build_version": request.build_version,
            "child_artifact": _manifest_file_projection(
                files[_relative(paths, paths.child_blocks)]
            ),
            "child_bm25": _manifest_file_projection(
                files[_relative(paths, paths.child_bm25)]
            ),
            "child_ordered_ids_sha256": child_metrics["ordered_ids_sha256"],
            "child_semantic_corpus_sha256": child_metrics[
                "semantic_corpus_sha256"
            ],
            "child_analyzer_fingerprint_sha256": child_metrics[
                "analyzer_fingerprint_sha256"
            ],
            "embedding_config_fingerprint_sha256": request.embedding_config_fingerprint_sha256,
            "target_requirements": {
                "must_be_new": True,
                "must_not_be_active": True,
                "must_not_exist": True,
                "forbidden_collection_names": list(request.forbidden_collection_names),
            },
        }
        _write_json_artifact(
            paths,
            paths.embedding_handoff_v1,
            handoff,
            "huiji.embedding-handoff/v1",
            None,
            files,
            semantic_hashes=None,
        )
        handoff_created = True

    report = {
        "schema_version": "huiji.corpus-build-report/v2",
        "build_version": request.build_version,
        "state": state.value,
        "generated_at_utc": request.generated_at_utc or _utc_now(),
        "row_counts": row_counts,
        "voice_status_counts": dict(request.voice_result.status_counts),
        "blockers": blockers,
        "handoff_created": handoff_created,
        "next_gate": (
            "user_run_embedding"
            if handoff_created
            else "resolve_blockers_and_rebuild_under_new_version"
        ),
    }
    _write_json_artifact(
        paths,
        paths.build_report,
        report,
        "huiji.corpus-build-report/v2",
        None,
        files,
        semantic_hashes=None,
    )

    manifest = {
        "schema_version": CORPUS_BUILD_SCHEMA_VERSION,
        "artifact_schema_version": MEDIA_V3_ROW_SCHEMA_VERSION,
        "build_version": request.build_version,
        "state": state.value,
        "source_inventory": request.source_inventory.to_json(),
        "code_fingerprint_sha256": request.code_fingerprint_sha256,
        "config_fingerprint_sha256": request.config_fingerprint_sha256,
        "fidelity_baseline": {
            "path": request.fidelity_baseline_path,
            "sha256": request.fidelity_baseline_sha256,
        },
        "protected_state_references": dict(request.protected_state_references),
        "schema_versions": {
            "parent": PARENT_BLOCK_SCHEMA_VERSION,
            "child": CHILD_BLOCK_SCHEMA_VERSION,
            "media_row": MEDIA_V3_ROW_SCHEMA_VERSION,
            "media_schema": MEDIA_V3_SCHEMA_VERSION,
            "media_manifest": MEDIA_V3_MANIFEST_SCHEMA_VERSION,
        },
        "artifacts": [files[path] for path in sorted(files)],
        "row_counts": row_counts,
        "voice_status_counts": dict(request.voice_result.status_counts),
        "semantic_corpus": {
            "child": child_metrics,
            "media_binding": media_metrics,
        },
        "fidelity": {
            "unexplained_parent_child_loss": request.fidelity.unexplained_parent_child_loss,
            "unexplained_binding_loss": request.fidelity.unexplained_binding_loss,
        },
        "blockers": blockers,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    _write_bytes_create_new(paths.build_manifest, manifest_bytes)
    manifest_sha256 = _sha256(manifest_bytes)
    verify_candidate_manifest(
        paths.build_root, expected_manifest_sha256=manifest_sha256
    )
    return CandidateWriteResult(
        paths=paths,
        state=state,
        build_manifest_sha256=manifest_sha256,
        semantic_artifact_sha256=semantic_hashes,
        blockers=tuple(blockers),
        row_counts=row_counts,
    )


def verify_candidate_manifest(
    build_root: str | Path,
    *,
    expected_manifest_sha256: str = "",
) -> dict[str, Any]:
    """Verify exact manifest closure and derived BM25/media contracts."""
    root = Path(build_root).resolve()
    manifest_path = root / _SELF_MANIFEST_PATH
    if not manifest_path.is_file():
        raise FileNotFoundError("candidate build_manifest.json is missing")
    manifest_bytes = manifest_path.read_bytes()
    if expected_manifest_sha256:
        _validate_sha(expected_manifest_sha256, "expected build manifest")
        if _sha256(manifest_bytes) != expected_manifest_sha256:
            raise ValueError("candidate build manifest SHA-256 mismatch")
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as error:
        raise ValueError("candidate build manifest is invalid JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != CORPUS_BUILD_SCHEMA_VERSION:
        raise ValueError("candidate build manifest schema is unsupported")
    if canonical_json_bytes(manifest) != manifest_bytes:
        raise ValueError("candidate build manifest is not canonical JSON")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise ValueError("candidate build manifest artifacts must be an array")
    by_path: dict[str, dict[str, Any]] = {}
    for entry in entries:
        relative = str(entry.get("relative_path") or "")
        if relative in by_path:
            raise ValueError(f"duplicate manifest artifact path: {relative}")
        target = _safe_manifest_target(root, relative)
        if not target.is_file():
            raise FileNotFoundError(f"manifest artifact is missing: {relative}")
        data = target.read_bytes()
        if _sha256(data) != str(entry.get("sha256") or ""):
            raise ValueError(f"manifest artifact hash mismatch: {relative}")
        expected_size = entry.get("size")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int):
            raise ValueError(f"manifest artifact size is invalid: {relative}")
        if len(data) != expected_size:
            raise ValueError(f"manifest artifact size mismatch: {relative}")
        row_count = entry.get("row_count")
        if row_count is not None:
            actual_count = (
                _jsonl_row_count(data)
                if relative.endswith(".jsonl")
                else _json_record_count(data)
            )
            if actual_count != int(row_count):
                raise ValueError(f"manifest artifact row count mismatch: {relative}")
        _verify_canonical_artifact_bytes(relative, data)
        by_path[relative] = entry

    disk_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    declared_files = set(by_path)
    if disk_files != declared_files:
        raise ValueError(
            "candidate manifest closure differs: "
            f"missing={sorted(declared_files - disk_files)}, "
            f"extra={sorted(disk_files - declared_files)}"
        )
    if "media_assets.jsonl" in disk_files:
        raise ValueError("v3 candidate must not emit root-level media_assets.jsonl")
    _verify_media_contract(root, by_path)
    bm25_metrics = _verify_bm25_parity(root, by_path)
    if manifest.get("semantic_corpus") != bm25_metrics:
        raise ValueError("candidate manifest semantic corpus metrics mismatch")

    state = str(manifest.get("state") or "")
    handoff_path = "handoff/embedding_handoff.v1.json"
    if state == BuildState.BLOCKED.value and handoff_path in by_path:
        raise ValueError("blocked candidate must not contain an embedding handoff")
    if state == BuildState.READY_FOR_EMBEDDING.value and handoff_path not in by_path:
        raise ValueError("ready candidate is missing its embedding handoff")
    if state == BuildState.READY_FOR_EMBEDDING.value:
        handoff = json.loads((root / handoff_path).read_text(encoding="utf-8"))
        if (
            not isinstance(handoff, dict)
            or handoff.get("child_analyzer_fingerprint_sha256")
            != bm25_metrics["child"]["analyzer_fingerprint_sha256"]
        ):
            raise ValueError("candidate embedding handoff BM25 identity mismatch")
    return manifest


def _verify_media_contract(
    root: Path, entries: Mapping[str, Mapping[str, Any]]
) -> None:
    media_path = "runtime/media_assets.v3.jsonl"
    schema_path = "runtime/media_assets.v3.schema.json"
    manifest_path = "runtime/media_assets.v3.manifest.json"
    if media_path not in entries:
        v2_paths = [path for path in entries if path.endswith("media_assets.v2.jsonl")]
        if v2_paths and not any(path.endswith("media_assets.v2.schema.json") for path in entries):
            raise ValueError("historical v2 media artifact is missing its schema")
        raise ValueError("candidate manifest is missing media_assets.v3.jsonl")
    if schema_path not in entries or manifest_path not in entries:
        raise ValueError("candidate media v3 schema or manifest is missing")
    schema = json.loads((root / schema_path).read_text(encoding="utf-8"))
    if schema != media_v3_schema_document():
        raise ValueError("candidate media v3 schema document differs from frozen contract")
    rows = _read_jsonl(root / media_path)
    for row in rows:
        validate_media_v3_row(row)
    resources, _bindings = normalize_media_v3_rows(rows)
    media_manifest = json.loads((root / manifest_path).read_text(encoding="utf-8"))
    if media_manifest.get("schema_version") != MEDIA_V3_MANIFEST_SCHEMA_VERSION:
        raise ValueError("candidate media manifest schema is unsupported")
    if media_manifest.get("binding_count") != len(rows):
        raise ValueError("candidate media manifest binding count mismatch")
    if media_manifest.get("resource_count") != len(resources):
        raise ValueError("candidate media manifest resource count mismatch")
    if media_manifest.get("shared_resource_group_count") != _shared_resource_count(rows):
        raise ValueError("candidate media manifest shared-resource count mismatch")
    binding_ids = [str(row["binding_id"]) for row in rows]
    if media_manifest.get("ordered_binding_ids_sha256") != _sha256_lines(binding_ids):
        raise ValueError("candidate media manifest binding ID hash mismatch")
    if media_manifest.get("semantic_corpus_sha256") != _canonical_rows_sha256(rows):
        raise ValueError("candidate media manifest semantic corpus hash mismatch")
    expected_files = media_manifest.get("files")
    if not isinstance(expected_files, dict):
        raise ValueError("candidate media manifest files are invalid")
    for key, relative in (("media_assets", media_path), ("media_schema", schema_path)):
        expected = expected_files.get(key)
        if not isinstance(expected, dict):
            raise ValueError(f"candidate media manifest is missing {key}")
        actual = entries[relative]
        if (
            expected.get("relative_path") != relative
            or expected.get("sha256") != actual.get("sha256")
            or expected.get("size") != actual.get("size")
            or expected.get("row_count") != actual.get("row_count")
        ):
            raise ValueError(f"candidate media manifest {key} fingerprint mismatch")


def _verify_bm25_parity(
    root: Path, entries: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    pairs = (
        (
            "child_blocks.jsonl",
            "indexes/child_text_bm25.json",
            "child_id",
            "child",
            "huiji.bm25-index/v3",
        ),
        (
            "runtime/media_assets.v3.jsonl",
            "indexes/media_binding_bm25.v3.json",
            "binding_id",
            "media_binding",
            "huiji.media-binding-bm25/v4",
        ),
    )
    metrics: dict[str, dict[str, Any]] = {}
    shared_identity: tuple[dict[str, object], dict[str, float], str] | None = None
    for artifact_path, index_path, id_field, record_kind, schema_version in pairs:
        if artifact_path not in entries or index_path not in entries:
            raise ValueError(f"candidate BM25 pair is missing: {artifact_path}")
        artifact_rows = _read_jsonl(root / artifact_path)
        payload = json.loads((root / index_path).read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != schema_version
            or payload.get("record_kind") != record_kind
        ):
            raise ValueError(f"candidate BM25 schema differs from {artifact_path}")
        loaded = LocalBM25SparseIndex.load(root / index_path)
        if not isinstance(loaded.analyzer, ChineseBM25Analyzer):
            raise ValueError(f"candidate BM25 analyzer differs from {artifact_path}")
        analyzer_payload = loaded.analyzer.identity.to_dict()
        bm25_payload = {"k1": loaded.k1, "b": loaded.b}
        analyzer_probe_sha256 = _analyzer_probe_sha256(loaded.analyzer)
        identity = (analyzer_payload, bm25_payload, analyzer_probe_sha256)
        if shared_identity is None:
            shared_identity = identity
        elif identity != shared_identity:
            raise ValueError("candidate child/media BM25 identity differs")
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or records != artifact_rows:
            raise ValueError(f"candidate BM25 records differ from {artifact_path}")
        ids = [str(row.get(id_field) or "") for row in artifact_rows]
        if payload.get("ordered_ids_sha256") != _sha256_lines(ids):
            raise ValueError(f"candidate BM25 ordered IDs differ from {artifact_path}")
        if payload.get("row_count") != len(artifact_rows):
            raise ValueError(f"candidate BM25 row count differs from {artifact_path}")
        semantic_sha256 = (
            canonical_child_corpus_sha256(artifact_rows)
            if id_field == "child_id"
            else _canonical_rows_sha256(artifact_rows)
        )
        if payload.get("semantic_corpus_sha256") != semantic_sha256:
            raise ValueError(f"candidate BM25 semantic corpus differs from {artifact_path}")
        metric = {
            "id_field": id_field,
            "row_count": len(artifact_rows),
            "ordered_ids_sha256": _sha256_lines(ids),
            "semantic_corpus_sha256": semantic_sha256,
            "analyzer_fingerprint_sha256": analyzer_payload[
                "fingerprint_sha256"
            ],
            "analyzer_probe_sha256": analyzer_probe_sha256,
            "bm25": bm25_payload,
        }
        for key, expected in metric.items():
            if payload.get(key) != expected:
                raise ValueError(f"candidate BM25 metrics differ from {artifact_path}")
        metrics[record_kind] = metric
    return metrics


def _bm25_payload(
    rows: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    record_kind: str,
    semantic_sha256: str,
    snapshot: _Bm25Snapshot,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ids = [str(row.get(id_field) or "") for row in rows]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"{record_kind} BM25 requires unique non-empty {id_field}")
    metrics = {
        "id_field": id_field,
        "row_count": len(rows),
        "ordered_ids_sha256": _sha256_lines(ids),
        "semantic_corpus_sha256": semantic_sha256,
        "analyzer_fingerprint_sha256": snapshot.analyzer_payload[
            "fingerprint_sha256"
        ],
        "analyzer_probe_sha256": snapshot.analyzer_probe_sha256,
        "bm25": dict(snapshot.bm25_payload),
    }
    return (
        {
            "schema_version": (
                "huiji.media-binding-bm25/v4"
                if record_kind == "media_binding"
                else "huiji.bm25-index/v3"
            ),
            "record_kind": record_kind,
            "analyzer": dict(snapshot.analyzer_payload),
            **metrics,
            "records": [dict(row) for row in rows],
        },
        metrics,
    )


def _validated_bm25_snapshot(
    identity: AnalyzerIdentity,
    k1: float,
    b: float,
) -> _Bm25Snapshot:
    if not isinstance(identity, AnalyzerIdentity):
        raise ValueError("BM25 analyzer identity is invalid")
    analyzer = ChineseBM25Analyzer(
        dictionary_path=os.devnull,
        extra_terms=identity.dictionary_terms,
        config=identity.config,
    )
    if analyzer.identity != identity:
        raise ValueError("BM25 analyzer identity mismatch")
    index = LocalBM25SparseIndex(analyzer=analyzer, k1=k1, b=b)
    return _Bm25Snapshot(
        analyzer=analyzer,
        analyzer_payload=MappingProxyType(identity.to_dict()),
        bm25_payload=MappingProxyType({"k1": index.k1, "b": index.b}),
        analyzer_probe_sha256=_analyzer_probe_sha256(analyzer),
    )


def _analyzer_probe_sha256(analyzer: ChineseBM25Analyzer) -> str:
    token_arrays = [analyzer.analyze(probe) for probe in _BM25_PROBES]
    return _sha256(canonical_json_bytes(token_arrays))


def _voice_diagnostics(
    voice_result: VoiceBindingResult,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for binding in sorted(voice_result.binding_rows, key=lambda row: row.source_id):
        status = str(voice_result.status_by_source[binding.source_id])
        causes = list(voice_result.root_causes_by_source[binding.source_id])
        flags = list(voice_result.quality_flags_by_source[binding.source_id])
        inventory.append(
            {
                "schema_version": "huiji.voice-binding-inventory/v1",
                "source_id": binding.source_id,
                "status": status,
                "root_causes": causes,
                "quality_flags": flags,
                "binding": binding.to_json(),
            }
        )
        if status == "quarantined":
            quarantine.append(
                {
                    "schema_version": "huiji.voice-quarantine/v1",
                    "source_id": binding.source_id,
                    "status": status,
                    "root_causes": causes,
                    "quality_flags": flags,
                    "binding": binding.to_json(),
                }
            )
        if status in {"quarantined", "fatal"}:
            conflicts.append(
                {
                    "schema_version": "huiji.voice-conflicts/v1",
                    "source_id": binding.source_id,
                    "status": status,
                    "root_causes": causes,
                    "evidence_ids": list(binding.evidence_ids),
                }
            )
    return inventory, quarantine, conflicts


def _write_jsonl_artifact(
    paths: CorpusCandidatePaths,
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    schema_version: str,
    files: dict[str, dict[str, Any]],
    semantic_hashes: dict[str, str],
) -> None:
    data = b"".join(
        canonical_json_bytes(dict(row))
        for row in rows
    )
    _write_bytes_create_new(path, data)
    _add_file_entry(paths, path, schema_version, len(rows), files)
    semantic_hashes[_relative(paths, path)] = _sha256(data)


def _write_json_artifact(
    paths: CorpusCandidatePaths,
    path: Path,
    payload: Mapping[str, Any],
    schema_version: str,
    row_count: int | None,
    files: dict[str, dict[str, Any]],
    semantic_hashes: dict[str, str] | None,
) -> None:
    data = canonical_json_bytes(dict(payload))
    _write_bytes_create_new(path, data)
    _add_file_entry(paths, path, schema_version, row_count, files)
    if semantic_hashes is not None:
        semantic_hashes[_relative(paths, path)] = _sha256(data)


def _write_bytes_create_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def _add_file_entry(
    paths: CorpusCandidatePaths,
    path: Path,
    schema_version: str,
    row_count: int | None,
    files: dict[str, dict[str, Any]],
) -> None:
    relative = _relative(paths, path)
    if relative in files:
        raise ValueError(f"duplicate candidate artifact path: {relative}")
    data = path.read_bytes()
    files[relative] = {
        "relative_path": relative,
        "sha256": _sha256(data),
        "size": len(data),
        "row_count": row_count,
        "schema_version": schema_version,
    }


def _manifest_file_projection(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "relative_path": entry["relative_path"],
        "sha256": entry["sha256"],
        "size": entry["size"],
        "row_count": entry["row_count"],
        "schema_version": entry["schema_version"],
    }


def _safe_manifest_target(root: Path, relative: str) -> Path:
    if (
        not relative
        or "\\" in relative
        or Path(relative).is_absolute()
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or relative == _SELF_MANIFEST_PATH
    ):
        raise ValueError(f"unsafe manifest artifact path: {relative}")
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError(f"manifest artifact escapes build root: {relative}") from error
    return target


def _relative(paths: CorpusCandidatePaths, path: Path) -> str:
    return path.relative_to(paths.build_root).as_posix()


def _require_unique(
    rows: Sequence[Mapping[str, Any]], field_name: str, label: str
) -> None:
    values = [str(row.get(field_name) or "") for row in rows]
    if any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError(f"candidate {label} rows require unique {field_name}")


def _media_sort_key(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(row["owner_page_id"]),
        str(row["child_id"]),
        int(row["sort_order"]),
        str(row["binding_id"]),
    )


def _canonical_rows_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(
        canonical_json_bytes([dict(row) for row in rows])
    ).hexdigest()


def _sha256_lines(values: Iterable[str]) -> str:
    data = "".join(f"{value}\n" for value in values).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _jsonl_row_count(data: bytes) -> int:
    return sum(1 for line in data.splitlines() if line.strip())


def _json_record_count(data: bytes) -> int:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as error:
        raise ValueError("manifest JSON artifact is invalid") from error
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("manifest JSON artifact with row_count has no records array")
    return len(records)


def _verify_canonical_artifact_bytes(relative: str, data: bytes) -> None:
    try:
        if relative.endswith(".jsonl"):
            rows = [
                json.loads(line)
                for line in data.decode("utf-8").splitlines()
                if line.strip()
            ]
            expected = (
                canonical_jsonl_bytes(rows)
                if relative == "runtime/media_assets.v3.jsonl"
                else b"".join(canonical_json_bytes(row) for row in rows)
            )
        elif relative.endswith(".json"):
            expected = canonical_json_bytes(json.loads(data.decode("utf-8")))
        else:
            raise ValueError(f"candidate artifact has an unsupported extension: {relative}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"candidate artifact is not valid UTF-8 JSON: {relative}") from error
    if expected != data:
        raise ValueError(f"candidate artifact is not canonical JSON: {relative}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"JSONL artifact row is not an object: {path}")
                rows.append(value)
    return rows


def _shared_resource_count(rows: Sequence[Mapping[str, Any]]) -> int:
    counts: dict[str, int] = {}
    for row in rows:
        resource_id = str(row["resource_id"])
        counts[resource_id] = counts.get(resource_id, 0) + 1
    return sum(count > 1 for count in counts.values())


def _validate_sha(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "CandidateArtifactInput",
    "CandidateWriteResult",
    "verify_candidate_manifest",
    "write_candidate_artifacts",
]
