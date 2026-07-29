"""Fixed-order, read-only orchestration for the single Huiji corpus builder."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import media_v3 as media_stage
from . import wikitext_projection as wikitext_stage
from .artifact_writer import (
    CandidateArtifactInput,
    verify_candidate_manifest,
    write_candidate_artifacts,
)
from .contracts import (
    BuildState,
    CAPACITY_MARGIN_RATIO,
    CLOUD_CAPACITY_MARGIN_MINIMUM_BYTES,
    CorpusBuildRequest,
    CorpusBuildResult,
    DIAGNOSTIC_ONLY_NEXT_GATE,
    LOCAL_CAPACITY_MARGIN_MINIMUM_BYTES,
    MIN_FREE_AFTER_COMMIT_BYTES,
    P0_MEDIA_NEW_BYTES_MAX,
    P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX,
    VoiceBindingInput,
    canonical_json_bytes,
    fixture_contract_fingerprint,
)
from .fidelity import build_fidelity_ledger
from .media_download_plan import (
    MEDIA_SELECTION_POLICY_SHA256,
    MediaCapacityEvidence,
    MediaDownloadPlanRequest,
    build_media_download_plan,
    media_selection_priority,
)
from .page_sources import (
    CrawlerSemanticInputs,
    build_page_revision_join,
    validate_recovery_gate,
)
from .projection import (
    compose_corpus_projection,
    project_crawler_semantics,
    project_page_semantics,
)
from .source_inventory import (
    capture_code_fingerprint,
    capture_corpus_source_inventory,
    verify_corpus_source_inventory,
)
from .voice_stage import VoiceBindingStage


_BUILD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_FILES = (
    "pages.jsonl",
    "wikitext.jsonl",
    "data_pages.jsonl",
    "resources_manifest.jsonl",
)
_PARTICIPATING_CODE_PATHS = (
    Path("src/huiji_rag/build/contracts.py"),
    Path("src/huiji_rag/build/source_inventory.py"),
    Path("src/huiji_rag/build/page_sources.py"),
    Path("src/huiji_rag/build/projection.py"),
    Path("src/huiji_rag/build/wikitext_projection.py"),
    Path("src/huiji_rag/build/story_projection.py"),
    Path("src/huiji_rag/build/topic_projection.py"),
    Path("src/huiji_rag/build/media_download_plan.py"),
    Path("src/huiji_rag/build/voice_stage.py"),
    Path("src/huiji_rag/build/media_v3.py"),
    Path("src/huiji_rag/build/fidelity.py"),
    Path("src/huiji_rag/build/artifact_writer.py"),
    Path("src/huiji_rag/build/orchestrator.py"),
    Path("src/huiji_rag/media.py"),
    Path("src/huiji_rag/models.py"),
    Path("src/huiji_rag/resources/topic_catalog.v1.json"),
    Path("src/rag/sparse.py"),
)
_ACTIVE_FILE_NAMES = {
    "parents": "parent_blocks.jsonl",
    "children": "child_blocks.jsonl",
    "excluded": "excluded_entities.jsonl",
    "media": "media_assets.jsonl",
    "child_bm25": "child_text_bm25.json",
    "media_bm25": "media_asset_bm25.json",
}


class _ExpectedGateFailure(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class HuijiCorpusBuilder:
    """The only public builder that can emit the complete corpus artifact set."""

    def validate_request(self, request: CorpusBuildRequest) -> Path:
        version = request.build_version
        if not isinstance(version, str) or not _BUILD_ID_RE.fullmatch(version):
            raise ValueError("build_version must match ^[a-z0-9][a-z0-9_-]{0,63}$")
        if version == "dev":
            raise ValueError("build_version dev is reserved for the installed legacy build")
        if request.configured_build_version and version == request.configured_build_version:
            raise ValueError("candidate build_version must differ from the configured build")

        processed_root = Path(request.processed_root).resolve()
        build_root = (processed_root / version).resolve()
        try:
            build_root.relative_to(processed_root)
        except ValueError as error:  # pragma: no cover - grammar excludes separators
            raise ValueError("candidate build root escapes processed root") from error
        if build_root.exists():
            raise FileExistsError(f"candidate build root already exists: {build_root}")

        pointer = request.active_pointer_path or processed_root / "active_build.v1.json"
        if pointer.exists():
            payload = _load_json_object(pointer, "active pointer")
            active_version = str(payload.get("build_version") or payload.get("buildVersion") or "")
            if active_version == version:
                raise ValueError("candidate build_version must differ from the active build")
        if tuple(request.requested_source_filenames) != _SOURCE_FILES:
            raise ValueError("candidate request must name exactly the four crawler source files")
        return build_root

    def inspect_source(self, request: CorpusBuildRequest):
        self.validate_request(request)
        return capture_corpus_source_inventory(
            request.raw_root,
            filenames=request.requested_source_filenames,
        )

    def build_candidate(self, request: CorpusBuildRequest) -> CorpusBuildResult:
        """Run the frozen stages and retain blocked candidates as immutable evidence."""
        build_root = self.validate_request(request)
        run_dir = Path(request.run_dir).resolve()
        if run_dir.exists():
            raise FileExistsError(f"candidate run directory already exists: {run_dir}")
        run_dir.mkdir(parents=True, exist_ok=False)

        try:
            return self._build_candidate(request, build_root, run_dir)
        except _ExpectedGateFailure as error:
            return _write_prebuild_blocked_result(
                request,
                build_root,
                run_dir,
                blocker=error.code,
                detail=error.detail,
            )

    def _build_candidate(
        self,
        request: CorpusBuildRequest,
        build_root: Path,
        run_dir: Path,
    ) -> CorpusBuildResult:
        project_root = _project_root(request)
        if (
            request.recovery_manifest_path is None
            or request.recovery_audit_receipt_path is None
            or request.recovery_apply_receipt_path is None
        ):
            raise _ExpectedGateFailure(
                "source_recovery_invalid",
                "recovery manifest, audit receipt, and apply receipt are required",
            )
        try:
            recovery = validate_recovery_gate(
                request.raw_root,
                manifest_path=request.recovery_manifest_path,
                audit_receipt_path=request.recovery_audit_receipt_path,
                apply_receipt_path=request.recovery_apply_receipt_path,
            )
        except (FileNotFoundError, OSError, ValueError):
            raise _ExpectedGateFailure(
                "source_recovery_invalid",
                "recovery evidence is unavailable or invalid",
            ) from None
        _write_create_new(
            run_dir / "source_recovery_gate.v1.json",
            {
                "schema_version": "huiji.source-recovery-gate/v1",
                "snapshot_id": recovery.snapshot_id,
                "invalid_payload_rows": recovery.invalid_payload_rows,
                "sqlite_quick_check": recovery.sqlite_quick_check,
                "data_pages_sha256": recovery.data_pages_sha256,
                "crawl_state_sha256": recovery.crawl_state_sha256,
            },
        )
        baseline, baseline_path, baseline_sha256 = _load_fidelity_baseline(
            request, project_root
        )
        active = _load_active_baseline_rows(baseline, project_root)

        try:
            source_inventory = capture_corpus_source_inventory(
                request.raw_root,
                filenames=request.requested_source_filenames,
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise _ExpectedGateFailure("source_inventory_invalid", str(error)) from error
        _write_create_new(
            run_dir / "source_inventory.v1.json", source_inventory.to_json()
        )

        try:
            semantic_inputs = CrawlerSemanticInputs.from_root(request.raw_root)
            page_stream = semantic_inputs.pages()
            revision_stream = semantic_inputs.revisions()
            source_join = build_page_revision_join(page_stream, revision_stream)
            data_stream = semantic_inputs.data_pages()
            resource_stream = semantic_inputs.resources()
            data_projection = project_crawler_semantics(
                item.projection_row() for item in data_stream
            )
            page_projection = project_page_semantics(
                source_join, semantic_inputs.revisions()
            )
            projection = compose_corpus_projection(
                data_projection, page_projection
            )
            resource_rows = tuple(
                item.projection_row() for item in resource_stream
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise _ExpectedGateFailure("semantic_projection_invalid", str(error)) from error
        _write_create_new(
            run_dir / "semantic_source_diagnostics.v1.json",
            {
                "schema_version": "huiji.semantic-source-diagnostics/v1",
                "source_filenames": list(semantic_inputs.source_filenames),
                "metrics": {
                    stream.source_name: {
                        "read_rows": stream.metrics.read_rows,
                        "accepted_rows": stream.metrics.accepted_rows,
                        "excluded_rows": stream.metrics.excluded_rows,
                        "peak_rss_bytes": stream.metrics.peak_rss_bytes,
                        "elapsed_seconds": stream.metrics.elapsed_seconds,
                        "reason_counts": dict(stream.metrics.reason_counts),
                    }
                    for stream in (
                        page_stream,
                        revision_stream,
                        data_stream,
                        resource_stream,
                    )
                },
                "page_revision_join": {
                    "joined_count": len(source_join.joined),
                    "diagnostics": [
                        item.to_json() for item in source_join.diagnostics
                    ],
                    "blockers": list(source_join.blockers),
                },
            },
        )

        media_config = media_stage.MediaV3Config(
            raw_root=request.raw_root,
            public_base_url=request.public_base_url,
            bucket_name=request.bucket_name,
            object_prefix=request.object_prefix,
        )
        try:
            voice_resources = media_stage.prepare_voice_resource_rows(
                media_config, resource_rows
            )
            voice_result = VoiceBindingStage().run(
                VoiceBindingInput(
                    source_rows=projection.voice_sources,
                    resource_rows=voice_resources.resource_rows,
                )
            )
            media = media_stage.assemble_media_v3(
                media_config, projection, resource_rows, voice_result
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise _ExpectedGateFailure("media_assembly_invalid", str(error)) from error

        blockers: list[str] = [
            *source_join.blockers,
            *voice_resources.blockers,
            *media.blockers,
        ]
        diagnostic_reason_set = {
            str(item.get("reason_code") or "")
            for item in media.unresolved_intents
            if str(item.get("reason_code") or "")
            in {
                "referenced_resource_missing",
                "referenced_resource_not_downloaded",
            }
        }
        if any(
            str(item.get("planning_shortfall_reason") or "")
            for item in media.unresolved_intents
        ):
            diagnostic_reason_set.add("capacity_planning_incomplete")
        protected_references: dict[str, Any] = {
            "fidelity_baseline": _reference(
                baseline_path, baseline_sha256, project_root
            )
        }
        wiki_blocker, wiki_reference = _validate_wiki_receipt(
            request, project_root, build_root, run_dir
        )
        if wiki_blocker:
            blockers.append(wiki_blocker)
        if wiki_reference:
            protected_references["wiki_compatibility_receipt"] = wiki_reference

        reconciled_rows = media.runtime_rows
        inventory = _load_media_inventory(request, build_root, run_dir)
        reconciliation = None
        if inventory is None:
            blockers.append("minio_inventory_missing")
        else:
            try:
                reconciliation = media_stage.reconcile_media_v3_minio(
                    media,
                    inventory[0],
                    expected_bucket=request.bucket_name,
                    expected_prefix=request.object_prefix,
                )
            except ValueError as error:
                raise _ExpectedGateFailure("minio_inventory_invalid", str(error)) from error
            blockers.extend(reconciliation.blockers)
            reconciled_rows = reconciliation.runtime_rows
            protected_references["minio_inventory"] = _reference(
                inventory[1], inventory[2], project_root
            ) | {"inventory_sha256": reconciliation.inventory_sha256}

        capacity_summary: dict[str, Any] = {"status": "not_requested"}
        capacity_evidence = request.capacity_planning
        if capacity_evidence is None:
            diagnostic_reason_set.add("capacity_not_requested")
        elif inventory is None or reconciliation is None:
            capacity_summary = {"status": "capacity_inventory_missing"}
        elif inventory is not None and reconciliation is not None:
            if (
                capacity_evidence.selection_policy_sha256
                != MEDIA_SELECTION_POLICY_SHA256
                or capacity_evidence.media_budget_baseline_inventory_sha256
                != reconciliation.inventory_sha256
            ):
                blockers.append("capacity_evidence_mismatch")
                capacity_summary = {"status": "capacity_evidence_mismatch"}
            else:
                try:
                    capacity_result = build_media_download_plan(
                        MediaDownloadPlanRequest(
                            media_rows=_capacity_planning_rows(media),
                            minio_inventory_rows=_capacity_inventory_rows(inventory[0]),
                            source_inventory_fingerprint=(
                                source_inventory.source_inventory_sha256
                            ),
                            projection_fingerprint=_projection_fingerprint(projection),
                            phase=capacity_evidence.phase,
                            selection_policy_sha256=(
                                capacity_evidence.selection_policy_sha256
                            ),
                            media_budget_baseline_inventory_sha256=(
                                capacity_evidence.media_budget_baseline_inventory_sha256
                            ),
                            workers=capacity_evidence.workers,
                            capacity=MediaCapacityEvidence(
                                free_local_bytes=capacity_evidence.free_local_bytes,
                                known_cloud_free_or_quota_bytes=(
                                    capacity_evidence.known_cloud_free_or_quota_bytes
                                ),
                                other_storage_growth_bytes=(
                                    capacity_evidence.other_storage_growth_bytes
                                ),
                                candidate_artifact_estimate_bytes=(
                                    capacity_evidence.candidate_artifact_estimate_bytes
                                ),
                                actual_free_after_commit_bytes=(
                                    capacity_evidence.actual_free_after_commit_bytes
                                ),
                                overflow_storage_overhead_bytes=(
                                    capacity_evidence.overflow_storage_overhead_bytes
                                ),
                                overflow_candidate_index_growth_bytes=(
                                    capacity_evidence.overflow_candidate_index_growth_bytes
                                ),
                            ),
                        )
                    )
                except ValueError as error:
                    raise _ExpectedGateFailure(
                        "capacity_planning_invalid", str(error)
                    ) from error
                capacity_paths: dict[str, Path] = {}
                for filename, data in capacity_result.artifact_bytes().items():
                    path = run_dir / filename
                    _write_bytes_create_new(path, data)
                    capacity_paths[filename] = path
                protected_references["referenced_media_capacity"] = {
                    filename: _reference(
                        path, _file_sha256(path), project_root
                    )
                    for filename, path in sorted(capacity_paths.items())
                }
                capacity_summary = {
                    "status": capacity_result.state,
                    "allowlist_sha256": capacity_result.allowlist_sha256,
                    "resource_count": len(capacity_result.allowlist_rows),
                }
                if capacity_result.state == "capacity_blocked":
                    blockers.append("capacity_blocked")
                elif capacity_result.state == "unknown_capacity":
                    diagnostic_reason_set.add("unknown_capacity")

        diagnostic_reasons = tuple(sorted(diagnostic_reason_set))
        _write_create_new(
            run_dir / "projection_diagnostics.v1.json",
            {
                "schema_version": "huiji.projection-diagnostics/v1",
                "projection_exclusions": [
                    _sanitized_exclusion(item.to_json())
                    for item in projection.exclusions
                ],
                "identity_fallbacks": [
                    item.to_json() for item in projection.identity_fallbacks
                ],
                "media_diagnostics": [
                    _sanitized_media_diagnostic(item)
                    for item in media.unresolved_intents
                ],
                "capacity": capacity_summary,
            },
        )

        try:
            legacy_media = media_stage.reconcile_active_media_occurrences(
                active["media"],
                media,
                projection,
                voice_result,
                raw_root=request.raw_root,
            )
            fidelity = build_fidelity_ledger(
                active_parent_rows=active["parents"],
                active_child_rows=active["children"],
                active_excluded_rows=active["excluded"],
                projection=projection,
                legacy_media=legacy_media,
                active_child_bm25_records=active["child_bm25"],
                active_media_bm25_records=active["media_bm25"],
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise _ExpectedGateFailure("fidelity_reconciliation_invalid", str(error)) from error

        try:
            verify_corpus_source_inventory(Path(request.raw_root), source_inventory)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise _ExpectedGateFailure("source_inventory_drift", str(error)) from error

        code_fingerprint = capture_code_fingerprint(
            project_root, _PARTICIPATING_CODE_PATHS
        )
        config_fingerprint = _config_fingerprint(request)
        embedding_fingerprint = _embedding_fingerprint(request)
        try:
            written = write_candidate_artifacts(
                request.processed_root,
                CandidateArtifactInput(
                    build_version=request.build_version,
                    projection=projection,
                    media_rows=tuple(reconciled_rows),
                    binding_inventory=media.binding_inventory,
                    voice_result=voice_result,
                    fidelity=fidelity,
                    source_inventory=source_inventory,
                    code_fingerprint_sha256=str(
                        code_fingerprint["code_fingerprint_sha256"]
                    ),
                    config_fingerprint_sha256=config_fingerprint,
                    fidelity_baseline_path=_display_path(baseline_path, project_root),
                    fidelity_baseline_sha256=baseline_sha256,
                    blockers=tuple(blockers),
                    diagnostic_reasons=diagnostic_reasons,
                    protected_state_references=protected_references,
                    embedding_config_fingerprint_sha256=embedding_fingerprint,
                    forbidden_collection_names=request.forbidden_collection_names,
                ),
            )
        except (FileExistsError, OSError, ValueError) as error:
            raise _ExpectedGateFailure("artifact_assembly_invalid", str(error)) from error

        payload = {
            "schema_version": "huiji.corpus-candidate-result/v1",
            "build_version": request.build_version,
            "build_root": _display_path(written.paths.build_root, project_root),
            "state": written.state.value,
            "row_counts": dict(written.row_counts),
            "semantic_artifact_sha256": dict(written.semantic_artifact_sha256),
            "build_manifest": _display_path(written.paths.build_manifest, project_root),
            "build_manifest_sha256": written.build_manifest_sha256,
            "blockers": list(written.blockers),
            "diagnostics": list(diagnostic_reasons),
            "next_gate": (
                "user_run_embedding"
                if written.state is BuildState.READY_FOR_EMBEDDING
                else (
                    DIAGNOSTIC_ONLY_NEXT_GATE
                    if written.state is BuildState.DIAGNOSTIC_ONLY
                    else "resolve_blockers_and_rebuild_under_new_version"
                )
            ),
        }
        _write_create_new(run_dir / "candidate_result.v1.json", payload)
        return CorpusBuildResult(
            build_version=request.build_version,
            build_root=written.paths.build_root,
            state=written.state,
            build_manifest=written.paths.build_manifest,
            build_report=written.paths.build_report,
            blockers=written.blockers,
            row_counts=written.row_counts,
        )

    def verify_candidate(
        self, build_root: Path, expected_manifest_sha256: str
    ) -> dict[str, Any]:
        """Verify a pinned candidate without changing or repairing it."""
        manifest = verify_candidate_manifest(
            Path(build_root), expected_manifest_sha256=expected_manifest_sha256
        )
        return {
            "schema_version": "huiji.corpus-candidate-verification/v1",
            "build_root": str(Path(build_root).resolve()),
            "state": str(manifest["state"]),
            "row_counts": dict(manifest["row_counts"]),
            "semantic_corpus": dict(manifest["semantic_corpus"]),
            "blockers": list(manifest.get("blockers") or []),
            "diagnostic_reasons": list(manifest.get("diagnostic_reasons") or []),
            "build_manifest_sha256": expected_manifest_sha256,
            "next_gate": (
                "user_run_embedding"
                if manifest["state"] == BuildState.READY_FOR_EMBEDDING.value
                else (
                    DIAGNOSTIC_ONLY_NEXT_GATE
                    if manifest["state"] == BuildState.DIAGNOSTIC_ONLY.value
                    else "resolve_blockers_and_rebuild_under_new_version"
                )
            ),
        }


def _project_root(request: CorpusBuildRequest) -> Path:
    root = Path(request.project_root or Path.cwd()).resolve()
    if not root.is_dir():
        raise _ExpectedGateFailure("project_root_invalid", f"project root is missing: {root}")
    return root


def _load_fidelity_baseline(
    request: CorpusBuildRequest, project_root: Path
) -> tuple[dict[str, Any], Path, str]:
    path, digest = _verified_file(
        request.fidelity_baseline_path,
        request.expected_fidelity_baseline_sha256,
        "fidelity baseline",
    )
    payload = _load_json_object(path, "fidelity baseline")
    if payload.get("schema_version") != "huiji.corpus-preservation-baseline/v2":
        raise _ExpectedGateFailure(
            "fidelity_baseline_schema_mismatch", "unsupported fidelity baseline schema"
        )
    if payload.get("status") != "pass":
        raise _ExpectedGateFailure(
            "fidelity_baseline_not_passing", "fidelity baseline status is not pass"
        )
    _require_outside(path, request.processed_root, request.build_version, "fidelity baseline")
    return payload, path, digest


def _load_active_baseline_rows(
    baseline: Mapping[str, Any], project_root: Path
) -> dict[str, tuple[dict[str, Any], ...]]:
    active = baseline.get("active_artifacts")
    files = active.get("files") if isinstance(active, Mapping) else None
    if not isinstance(files, Mapping):
        raise _ExpectedGateFailure(
            "fidelity_baseline_incomplete", "baseline lacks active artifact file evidence"
        )
    result: dict[str, tuple[dict[str, Any], ...]] = {}
    for key, filename in _ACTIVE_FILE_NAMES.items():
        entry = files.get(filename)
        if not isinstance(entry, Mapping):
            raise _ExpectedGateFailure(
                "fidelity_baseline_incomplete", f"baseline lacks {filename}"
            )
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise _ExpectedGateFailure(
                "fidelity_baseline_incomplete", f"baseline has invalid {filename} evidence"
            )
        path = _contained_project_file(project_root, relative, filename)
        _verified_file(path, expected, filename)
        if path.suffix.casefold() == ".jsonl":
            result[key] = tuple(_read_jsonl(path))
        else:
            payload = _load_json_object(path, filename)
            records = payload.get("records")
            if not isinstance(records, list) or any(
                not isinstance(row, dict) for row in records
            ):
                raise _ExpectedGateFailure(
                    "fidelity_baseline_incomplete", f"{filename} lacks object records"
                )
            result[key] = tuple(dict(row) for row in records)
    return result


def _validate_wiki_receipt(
    request: CorpusBuildRequest,
    project_root: Path,
    build_root: Path,
    run_dir: Path,
) -> tuple[str, dict[str, str] | None]:
    if request.wiki_compatibility_receipt_path is None:
        return "wiki_compatibility_receipt_missing", None
    path, digest = _verified_file(
        request.wiki_compatibility_receipt_path,
        request.expected_wiki_compatibility_receipt_sha256,
        "Wiki compatibility receipt",
    )
    if _is_within(path, build_root) or _is_within(path, run_dir):
        raise _ExpectedGateFailure(
            "wiki_compatibility_receipt_location_invalid",
            "Wiki compatibility receipt must be outside candidate and run roots",
        )
    payload = _load_json_object(path, "Wiki compatibility receipt")
    if payload.get("schema_version") != "huiji.wiki-media-v3-compatibility-receipt/v1":
        raise _ExpectedGateFailure(
            "wiki_compatibility_receipt_schema_mismatch",
            "unsupported Wiki compatibility receipt schema",
        )
    if payload.get("status") != "passed":
        raise _ExpectedGateFailure(
            "wiki_compatibility_receipt_not_passing",
            "Wiki compatibility receipt status is not passed",
        )
    fixture_root = project_root / "tests/fixtures/contracts/huiji_media_v3"
    expected = fixture_contract_fingerprint(fixture_root)
    receipt_rows = payload.get("fixtures")
    if not isinstance(receipt_rows, list):
        raise _ExpectedGateFailure(
            "wiki_compatibility_fixture_mismatch", "receipt fixture list is missing"
        )
    actual = sorted(
        (
            Path(str(row.get("path") or "")).name,
            str(row.get("sha256") or ""),
        )
        for row in receipt_rows
        if isinstance(row, Mapping)
    )
    pinned = sorted((str(row["path"]), str(row["sha256"])) for row in expected["files"])
    if actual != pinned:
        raise _ExpectedGateFailure(
            "wiki_compatibility_fixture_mismatch",
            "Wiki receipt fixture hashes differ from the frozen RAG fixture",
        )
    return "", _reference(path, digest, project_root)


def _load_media_inventory(
    request: CorpusBuildRequest, build_root: Path, run_dir: Path
) -> tuple[dict[str, Any], Path, str] | None:
    if request.minio_inventory_path is None:
        return None
    path, digest = _verified_file(
        request.minio_inventory_path,
        request.expected_minio_inventory_sha256,
        "MinIO inventory",
    )
    if _is_within(path, build_root) or _is_within(path, run_dir):
        raise _ExpectedGateFailure(
            "minio_inventory_location_invalid",
            "MinIO inventory must be captured outside candidate and run roots",
        )
    payload = _load_json_object(path, "MinIO inventory")
    if payload.get("schema_version") != "evb.minio-inventory/v1":
        raise _ExpectedGateFailure(
            "minio_inventory_schema_mismatch", "unsupported MinIO inventory schema"
        )
    return payload, path, digest


def _config_fingerprint(request: CorpusBuildRequest) -> str:
    payload = {
        "schema_version": "huiji.corpus-build-config/v1",
        "source_filenames": list(request.requested_source_filenames),
        "public_base_url": request.public_base_url,
        "bucket_name": request.bucket_name,
        "object_prefix": request.object_prefix,
        "wikitext_parser_config_sha256": wikitext_stage._PARSER_CONFIG_SHA256,
        "decorative_minimum_dimension_px": (
            wikitext_stage._DECORATIVE_MINIMUM_DIMENSION_PX
        ),
        "media_selection_policy": {
            "sha256": MEDIA_SELECTION_POLICY_SHA256,
        },
        "media_capacity_constants": {
            "p0_new_bytes_max": P0_MEDIA_NEW_BYTES_MAX,
            "p1_cumulative_new_bytes_max": P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX,
            "minimum_free_after_commit_bytes": MIN_FREE_AFTER_COMMIT_BYTES,
            "local_margin_minimum_bytes": LOCAL_CAPACITY_MARGIN_MINIMUM_BYTES,
            "cloud_margin_minimum_bytes": CLOUD_CAPACITY_MARGIN_MINIMUM_BYTES,
            "margin_ratio": CAPACITY_MARGIN_RATIO,
        },
        "capacity_planning": (
            None
            if request.capacity_planning is None
            else {
                "phase": request.capacity_planning.phase,
                "workers": request.capacity_planning.workers,
                "free_local_bytes": request.capacity_planning.free_local_bytes,
                "known_cloud_free_or_quota_bytes": (
                    request.capacity_planning.known_cloud_free_or_quota_bytes
                ),
                "other_storage_growth_bytes": (
                    request.capacity_planning.other_storage_growth_bytes
                ),
                "candidate_artifact_estimate_bytes": (
                    request.capacity_planning.candidate_artifact_estimate_bytes
                ),
                "selection_policy_sha256": (
                    request.capacity_planning.selection_policy_sha256
                ),
                "media_budget_baseline_inventory_sha256": (
                    request.capacity_planning.media_budget_baseline_inventory_sha256
                ),
                "actual_free_after_commit_bytes": (
                    request.capacity_planning.actual_free_after_commit_bytes
                ),
                "overflow_storage_overhead_bytes": (
                    request.capacity_planning.overflow_storage_overhead_bytes
                ),
                "overflow_candidate_index_growth_bytes": (
                    request.capacity_planning.overflow_candidate_index_growth_bytes
                ),
            }
        ),
    }
    return hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()


def _sanitized_exclusion(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reason_code": str(row.get("reason_code") or ""),
        "source_title": str(row.get("source_title") or ""),
        "source_identity": str(row.get("source_identity") or ""),
        "source_content_sha256": str(row.get("source_content_sha256") or ""),
        "entity_id": str(row.get("entity_id") or ""),
        "json_path": str(row.get("json_path") or "$"),
        "details": _sanitized_mapping(row.get("details")),
    }


def _sanitized_media_diagnostic(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reason_code": str(row.get("reason_code") or ""),
        "source_binding_token": str(row.get("source_binding_token") or ""),
        "filename": Path(str(row.get("filename") or "")).name,
    }


def _capacity_planning_rows(media: media_stage.MediaV3Assembly) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    inventory_by_binding = {
        str(item.get("binding_id") or ""): item for item in media.binding_inventory
    }
    for item in media.runtime_rows:
        binding_id = str(item.get("binding_id") or "")
        inventory = inventory_by_binding.get(binding_id, {})
        rows.append(
            {
                "resource_id": str(item.get("resource_id") or ""),
                "binding_id": binding_id,
                "owner_id": str(item.get("owner_page_id") or ""),
                "owner_type": _capacity_owner_type(item.get("owner_page_id")),
                "category": str(item.get("entity_type") or ""),
                "parent_id": str(item.get("parent_id") or ""),
                "child_id": str(item.get("child_id") or ""),
                "section": str(item.get("section") or ""),
                "media_role": str(item.get("media_role") or ""),
                "selection_priority": media_selection_priority(
                    str(item.get("media_role") or "")
                ),
                "eligible": True,
                "filename": str(item.get("filename") or ""),
                "url": str(item.get("source_url") or ""),
                "mime": str(item.get("mime") or ""),
                "sha1": str(item.get("sha1") or ""),
                "content_sha256": str(item.get("content_sha256") or ""),
                "size": item.get("size"),
                "local_relpath": str(inventory.get("local_relpath") or ""),
                "object_key": str(item.get("object_key") or ""),
                "download_status": "downloaded",
                "local_present": True,
                "source_refs": [dict(ref) for ref in item.get("source_refs") or ()],
            }
        )
    for item in media.unresolved_intents:
        planning = item.get("planning_evidence")
        if isinstance(planning, Mapping):
            rows.append(dict(planning))
        elif str(item.get("planning_shortfall_reason") or ""):
            source_binding_token = str(item.get("source_binding_token") or "")
            rows.append(
                {
                    "resource_id": "",
                    "binding_id": "planning-incomplete:sha256:"
                    + hashlib.sha256(source_binding_token.encode("utf-8")).hexdigest(),
                    "owner_id": str(item.get("owner_page_id") or ""),
                    "owner_type": _capacity_owner_type(item.get("owner_page_id")),
                    "media_role": str(item.get("media_role") or ""),
                    "capacity_planning_incomplete": True,
                    "planning_shortfall_reason": str(
                        item.get("planning_shortfall_reason") or ""
                    ),
                }
            )
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                str(item.get("resource_id") or ""),
                str(item.get("binding_id") or ""),
            ),
        )
    )


def _capacity_inventory_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise ValueError("MinIO inventory objects are missing")
    return tuple(
        {
            "object_key": str(item.get("object_key") or ""),
            "sha1": str(item.get("sha1") or ""),
            "content_sha256": str(item.get("sha256") or ""),
            "size": item.get("size"),
        }
        for item in objects
        if isinstance(item, Mapping)
    )


def _projection_fingerprint(projection: Any) -> str:
    payload = {
        "parents": [item.to_json() for item in projection.parents],
        "children": [item.to_json() for item in projection.children],
        "media_intents": [item.to_json() for item in projection.media_intents],
        "exclusions": [item.to_json() for item in projection.exclusions],
        "record_links": [item.to_json() for item in projection.record_links],
    }
    return hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()


def _capacity_owner_type(value: object) -> str:
    return str(value or "").split(":", 1)[0].casefold() or "unknown"


def _sanitized_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed = {
        "declared_width",
        "declared_height",
        "minimum_dimension_px",
        "occurrence",
        "heading_depth",
        "selector_count",
        "pageid",
        "revid",
        "source_line_number",
    }
    return {key: value[key] for key in sorted(value) if key in allowed}


def _embedding_fingerprint(request: CorpusBuildRequest) -> str:
    if not request.embedding_provider or not request.embedding_model:
        return ""
    payload = {
        "schema_version": "huiji.embedding-config/v1",
        "provider": request.embedding_provider,
        "model": request.embedding_model,
    }
    return hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()


def _write_prebuild_blocked_result(
    request: CorpusBuildRequest,
    build_root: Path,
    run_dir: Path,
    *,
    blocker: str,
    detail: str,
) -> CorpusBuildResult:
    build_manifest = build_root / "build_manifest.json"
    build_report = build_root / "build_report.json"
    payload = {
        "schema_version": "huiji.corpus-candidate-result/v1",
        "build_version": request.build_version,
        "build_root": str(build_root),
        "state": BuildState.BLOCKED.value,
        "row_counts": {},
        "semantic_artifact_sha256": {},
        "build_manifest": str(build_manifest) if build_manifest.is_file() else None,
        "build_manifest_sha256": (
            _file_sha256(build_manifest) if build_manifest.is_file() else None
        ),
        "blockers": [blocker],
        "failure_detail": _public_failure_detail(blocker),
        "next_gate": "resolve_blockers_and_rebuild_under_new_version",
    }
    _write_create_new(run_dir / "candidate_result.v1.json", payload)
    return CorpusBuildResult(
        build_version=request.build_version,
        build_root=build_root,
        state=BuildState.BLOCKED,
        build_manifest=build_manifest if build_manifest.is_file() else None,
        build_report=build_report if build_report.is_file() else None,
        blockers=(blocker,),
        row_counts={},
    )


def _public_failure_detail(blocker: str) -> str:
    if blocker == "source_recovery_invalid":
        return "recovery evidence is unavailable or invalid"
    return f"candidate gate did not pass: {_code(blocker)}"


def _verified_file(path: Path, expected_sha256: str, label: str) -> tuple[Path, str]:
    if not _SHA256_RE.fullmatch(str(expected_sha256)):
        raise _ExpectedGateFailure(
            f"{_code(label)}_expected_sha256_invalid",
            f"{label} expected SHA-256 must be lowercase hexadecimal",
        )
    resolved = Path(path).resolve()
    if not resolved.is_file() or resolved.suffix.casefold() == ".pyc":
        raise _ExpectedGateFailure(
            f"{_code(label)}_missing", f"{label} does not exist: {resolved}"
        )
    digest = _file_sha256(resolved)
    if digest != expected_sha256:
        raise _ExpectedGateFailure(
            f"{_code(label)}_sha256_mismatch", f"{label} SHA-256 mismatch"
        )
    return resolved, digest


def _contained_project_file(project_root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        raise _ExpectedGateFailure(
            "fidelity_baseline_path_escape", f"{label} path escapes project root"
        )
    path = (project_root / candidate).resolve()
    if not _is_within(path, project_root):
        raise _ExpectedGateFailure(
            "fidelity_baseline_path_escape", f"{label} path escapes project root"
        )
    return path


def _require_outside(path: Path, processed_root: Path, build_version: str, label: str) -> None:
    candidate = (Path(processed_root).resolve() / build_version).resolve()
    if _is_within(path, candidate):
        raise _ExpectedGateFailure(
            f"{_code(label)}_location_invalid", f"{label} must be outside candidate root"
        )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row {line_number} in {path.name} is not an object")
            rows.append(value)
    return rows


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _ExpectedGateFailure(f"{_code(label)}_invalid", str(error)) from error
    if not isinstance(value, dict):
        raise _ExpectedGateFailure(
            f"{_code(label)}_invalid", f"{label} must contain a JSON object"
        )
    return value


def _write_create_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(payload))


def _write_bytes_create_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def _reference(path: Path, digest: str, project_root: Path) -> dict[str, str]:
    return {"path": _display_path(path, project_root), "sha256": digest}


def _display_path(path: Path, project_root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return f"external-read-only/{resolved.name}"


def _is_within(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
