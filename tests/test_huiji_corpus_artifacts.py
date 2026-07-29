from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.huiji_rag.build.artifact_writer import (
    CandidateArtifactInput,
    verify_candidate_manifest,
    write_candidate_artifacts,
)
from src.huiji_rag.build.contracts import (
    CORPUS_BUILD_SCHEMA_VERSION,
    CorpusSourceInventory,
    SourceFileEvidence,
    VoiceBindingInput,
    canonical_json_bytes,
)
from src.huiji_rag.build.fidelity import FidelityResult
from src.huiji_rag.build.projection import CorpusProjection, SemanticChild
from src.huiji_rag.build.voice_stage import VoiceBindingStage
from src.huiji_rag.models import ChildBlock, ParentBlock, VoiceSourceRow
from src.rag.chinese_analyzer import ChineseBM25Analyzer


FIXTURE = Path("tests/fixtures/contracts/huiji_media_v3/media_assets.v3.jsonl")


def _artifact_input(build_version: str, *, blockers=()) -> CandidateArtifactInput:
    analyzer = ChineseBM25Analyzer()
    media_rows = [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()[:2]
        if line
    ]
    children = []
    parents = []
    for row in media_rows:
        source_ref = {
            "kind": "data_page",
            "title": f"Data:Char/{row['entity_id']}.json",
            "content_sha256": "a" * 64,
            "json_path": "$",
        }
        block = ChildBlock(
            child_id=row["child_id"],
            parent_id=row["parent_id"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            category="character",
            section_kind=row["section"],
            title=row["title"],
            text=row["search_text"],
            search_text=row["search_text"],
            chunk_index=0,
            media_ids=(),
            media_policy="auto",
            source_refs=(source_ref,),
            content_hash=hashlib.sha256(row["search_text"].encode()).hexdigest(),
        )
        children.append(
            SemanticChild(
                block=block,
                stable_source_token="default",
                source_token_kind="crawler_stable_id",
                owner_entity_id=row["owner_entity_id"],
                owner_page_id=row["owner_page_id"],
            )
        )
        parents.append(
            ParentBlock(
                parent_id=row["parent_id"],
                entity_id=row["entity_id"],
                entity_name=row["entity_name"],
                entity_aliases=(),
                category="character",
                section_kind=row["section"],
                title=row["title"],
                summary_text=row["search_text"],
                source_refs=(source_ref,),
                child_ids=(row["child_id"],),
                content_hash=hashlib.sha256(row["search_text"].encode()).hexdigest(),
            )
        )
    projection = CorpusProjection(
        parents=tuple(parents),
        children=tuple(children),
        voice_sources=(),
        media_intents=(),
        exclusions=(),
        identity_fallbacks=(),
        record_links=(),
    )
    source_files = tuple(
        SourceFileEvidence(
            relative_path=name,
            sha256=str(index) * 64,
            size=index,
            row_count=index,
            identity_sha256=str(index + 4) * 64,
        )
        for index, name in enumerate(
            ("pages.jsonl", "wikitext.jsonl", "data_pages.jsonl", "resources_manifest.jsonl"),
            start=1,
        )
    )
    inventory = CorpusSourceInventory(
        files=source_files,
        source_inventory_sha256="9" * 64,
    )
    fidelity = FidelityResult(
        ledger_rows=(),
        build_diff={
            "schema_version": "huiji.build-diff/v1",
            "unexplained_parent_child_loss": 0,
            "unexplained_binding_loss": 0,
        },
        blockers=(),
    )
    voice = VoiceBindingStage().run(
        VoiceBindingInput(source_rows=(), resource_rows=())
    )
    binding_inventory = tuple(
        {
            "schema_version": "huiji.media-binding-inventory/v3",
            "binding_id": row["binding_id"],
            "resource_id": row["resource_id"],
            "local_relpath": f"assets/{row['filename']}",
        }
        for row in media_rows
    )
    return CandidateArtifactInput(
        build_version=build_version,
        projection=projection,
        media_rows=tuple(media_rows),
        binding_inventory=binding_inventory,
        voice_result=voice,
        fidelity=fidelity,
        source_inventory=inventory,
        code_fingerprint_sha256="b" * 64,
        config_fingerprint_sha256="c" * 64,
        fidelity_baseline_path="eval/baseline.json",
        fidelity_baseline_sha256="d" * 64,
        bm25_analyzer_identity=analyzer.identity,
        bm25_k1=1.5,
        bm25_b=0.75,
        blockers=tuple(blockers),
        protected_state_references={"pre": "e" * 64},
        embedding_config_fingerprint_sha256="f" * 64,
        forbidden_collection_names=("active", "historical"),
        generated_at_utc="2026-07-21T00:00:00Z",
    )


def test_candidate_writer_uses_exact_layout_manifest_closure_and_direct_bm25(tmp_path: Path) -> None:
    first = write_candidate_artifacts(tmp_path / "processed", _artifact_input("build-a"))

    assert first.state.value == "ready_for_embedding"
    assert first.paths.embedding_handoff_v1.is_file()
    assert not (first.paths.build_root / "media_assets.jsonl").exists()
    assert first.paths.media_assets_v3 == first.paths.build_root / "runtime/media_assets.v3.jsonl"
    assert first.paths.media_bm25_v3 == first.paths.build_root / "indexes/media_binding_bm25.v3.json"
    manifest = verify_candidate_manifest(
        first.paths.build_root,
        expected_manifest_sha256=first.build_manifest_sha256,
    )
    assert manifest["schema_version"] == CORPUS_BUILD_SCHEMA_VERSION
    assert manifest["artifact_schema_version"] == "evb.media-asset/v3"
    child_rows = [
        json.loads(line)
        for line in first.paths.child_blocks.read_text(encoding="utf-8").splitlines()
        if line
    ]
    child_bm25 = json.loads(first.paths.child_bm25.read_text(encoding="utf-8"))
    media_bm25 = json.loads(first.paths.media_bm25_v3.read_text(encoding="utf-8"))
    assert child_bm25["records"] == child_rows
    assert child_bm25["schema_version"] == "huiji.bm25-index/v3"
    assert media_bm25["schema_version"] == "huiji.media-binding-bm25/v4"
    assert child_bm25["analyzer"] == media_bm25["analyzer"]
    assert child_bm25["bm25"] == media_bm25["bm25"] == {"k1": 1.5, "b": 0.75}
    assert manifest["semantic_corpus"]["child"]["analyzer_fingerprint_sha256"] == (
        child_bm25["analyzer"]["fingerprint_sha256"]
    )
    assert manifest["semantic_corpus"]["child"]["analyzer_probe_sha256"]
    assert manifest["semantic_corpus"]["child"]["bm25"] == child_bm25["bm25"]
    assert manifest["semantic_corpus"]["child"] == {
        **manifest["semantic_corpus"]["media_binding"],
        "id_field": "child_id",
        "row_count": len(child_rows),
        "ordered_ids_sha256": child_bm25["ordered_ids_sha256"],
        "semantic_corpus_sha256": child_bm25["semantic_corpus_sha256"],
    }
    handoff = json.loads(first.paths.embedding_handoff_v1.read_text(encoding="utf-8"))
    assert handoff["child_analyzer_fingerprint_sha256"] == (
        child_bm25["analyzer"]["fingerprint_sha256"]
    )
    artifact_schemas = {
        entry["relative_path"]: entry["schema_version"]
        for entry in manifest["artifacts"]
    }
    assert artifact_schemas["indexes/child_text_bm25.json"] == "huiji.bm25-index/v3"
    assert artifact_schemas["indexes/media_binding_bm25.v3.json"] == (
        "huiji.media-binding-bm25/v4"
    )

    second = write_candidate_artifacts(tmp_path / "processed", _artifact_input("build-b"))
    assert first.semantic_artifact_sha256 == second.semantic_artifact_sha256
    assert first.build_manifest_sha256 != second.build_manifest_sha256
    assert first.paths.child_bm25.read_bytes() == second.paths.child_bm25.read_bytes()
    assert first.paths.media_bm25_v3.read_bytes() == second.paths.media_bm25_v3.read_bytes()


def test_bm25_analyzer_change_preserves_semantic_hash_but_changes_payload(tmp_path: Path) -> None:
    base_request = _artifact_input("base")
    changed_analyzer = ChineseBM25Analyzer(extra_terms=("确定性额外术语",))
    changed_request = replace(
        _artifact_input("changed"),
        bm25_analyzer_identity=changed_analyzer.identity,
    )

    base = write_candidate_artifacts(tmp_path / "base", base_request)
    changed = write_candidate_artifacts(tmp_path / "changed", changed_request)
    base_manifest = verify_candidate_manifest(base.paths.build_root)
    changed_manifest = verify_candidate_manifest(changed.paths.build_root)

    assert (
        base_manifest["semantic_corpus"]["child"]["semantic_corpus_sha256"]
        == changed_manifest["semantic_corpus"]["child"]["semantic_corpus_sha256"]
    )
    assert base.paths.child_bm25.read_bytes() != changed.paths.child_bm25.read_bytes()
    assert (
        base_manifest["semantic_corpus"]["child"]["analyzer_fingerprint_sha256"]
        != changed_manifest["semantic_corpus"]["child"]["analyzer_fingerprint_sha256"]
    )


def _rewrite_candidate_json(root: Path, relative_path: str, payload: dict) -> None:
    target = root / relative_path
    data = canonical_json_bytes(payload)
    target.write_bytes(data)
    manifest_path = root / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(
        item for item in manifest["artifacts"]
        if item["relative_path"] == relative_path
    )
    entry["sha256"] = hashlib.sha256(data).hexdigest()
    entry["size"] = len(data)
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def _set_nested(payload: dict, path: tuple[str, ...], value) -> None:
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("schema_version",), "huiji.bm25-index/v99"),
        (("record_kind",), "media_binding"),
        (("analyzer", "schema_version"), "rag.bm25-analyzer/v99"),
        (("analyzer", "name"), "other-analyzer"),
        (("analyzer", "version"), "99"),
        (("analyzer", "segmenter", "name"), "other-segmenter"),
        (("analyzer", "segmenter", "version"), "99"),
        (("analyzer", "segmenter", "hmm"), True),
        (("analyzer", "config_sha256"), "0" * 64),
        (("analyzer", "dictionary_sha256"), "0" * 64),
        (("analyzer", "fingerprint_sha256"), "0" * 64),
        (("analyzer_fingerprint_sha256",), "0" * 64),
        (("bm25", "k1"), 1.2),
        (("bm25", "b"), 0.4),
        (("analyzer_probe_sha256",), "0" * 64),
        (("row_count",), 99),
        (("ordered_ids_sha256",), "0" * 64),
        (("semantic_corpus_sha256",), "0" * 64),
    ),
)
def test_candidate_bm25_parity_rejects_metadata_drift(
    tmp_path: Path,
    path: tuple[str, ...],
    value,
) -> None:
    result = write_candidate_artifacts(
        tmp_path / "processed",
        _artifact_input("parity-drift"),
    )
    relative = "indexes/child_text_bm25.json"
    payload = json.loads(result.paths.child_bm25.read_text(encoding="utf-8"))
    _set_nested(payload, path, value)
    _rewrite_candidate_json(result.paths.build_root, relative, payload)

    with pytest.raises(ValueError):
        verify_candidate_manifest(result.paths.build_root)


def test_candidate_bm25_parity_rejects_record_and_cross_payload_identity_drift(
    tmp_path: Path,
) -> None:
    records_result = write_candidate_artifacts(
        tmp_path / "records",
        _artifact_input("record-drift"),
    )
    records_payload = json.loads(
        records_result.paths.child_bm25.read_text(encoding="utf-8")
    )
    records_payload["records"][0]["search_text"] = "changed private record"
    _rewrite_candidate_json(
        records_result.paths.build_root,
        "indexes/child_text_bm25.json",
        records_payload,
    )
    with pytest.raises(ValueError):
        verify_candidate_manifest(records_result.paths.build_root)

    identity_result = write_candidate_artifacts(
        tmp_path / "identity",
        _artifact_input("identity-drift"),
    )
    identity_payload = json.loads(
        identity_result.paths.child_bm25.read_text(encoding="utf-8")
    )
    changed = ChineseBM25Analyzer(extra_terms=("仅 child 漂移",)).identity.to_dict()
    identity_payload["analyzer"] = changed
    identity_payload["analyzer_fingerprint_sha256"] = changed[
        "fingerprint_sha256"
    ]
    _rewrite_candidate_json(
        identity_result.paths.build_root,
        "indexes/child_text_bm25.json",
        identity_payload,
    )
    with pytest.raises(ValueError, match="identity differs"):
        verify_candidate_manifest(identity_result.paths.build_root)


def test_candidate_manifest_rejects_bm25_manifest_and_handoff_identity_drift(
    tmp_path: Path,
) -> None:
    manifest_result = write_candidate_artifacts(
        tmp_path / "manifest",
        _artifact_input("manifest-drift"),
    )
    manifest_path = manifest_result.paths.build_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["semantic_corpus"]["child"]["analyzer_probe_sha256"] = "0" * 64
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="semantic corpus metrics mismatch"):
        verify_candidate_manifest(manifest_result.paths.build_root)

    handoff_result = write_candidate_artifacts(
        tmp_path / "handoff",
        _artifact_input("handoff-drift"),
    )
    handoff = json.loads(
        handoff_result.paths.embedding_handoff_v1.read_text(encoding="utf-8")
    )
    handoff["child_analyzer_fingerprint_sha256"] = "0" * 64
    _rewrite_candidate_json(
        handoff_result.paths.build_root,
        "handoff/embedding_handoff.v1.json",
        handoff,
    )
    with pytest.raises(ValueError, match="handoff"):
        verify_candidate_manifest(handoff_result.paths.build_root)


def test_blocked_candidate_never_emits_embedding_handoff(tmp_path: Path) -> None:
    result = write_candidate_artifacts(
        tmp_path / "processed", _artifact_input("blocked-a", blockers=("test_gate",))
    )

    assert result.state.value == "blocked"
    assert not result.paths.embedding_handoff_v1.exists()
    report = json.loads(result.paths.build_report.read_text(encoding="utf-8"))
    assert report["handoff_created"] is False
    assert report["blockers"] == ["test_gate"]
    verify_candidate_manifest(result.paths.build_root)


def test_voice_diagnostics_separate_shortfall_from_quarantine_and_conflicts(
    tmp_path: Path,
) -> None:
    request = _artifact_input("voice-diagnostics")
    request = replace(
        request,
        voice_result=VoiceBindingStage().run(
            VoiceBindingInput(
                source_rows=(
                    VoiceSourceRow(
                        event_name="Missing",
                        language="en",
                        source_id="voice:shortfall",
                        entity_id="1001",
                        parent_id="char:1001/voice",
                        child_id="char:1001/voice/event-missing",
                        transcript="Missing",
                    ),
                ),
                resource_rows=(),
            )
        ),
    )

    result = write_candidate_artifacts(tmp_path / "processed", request)
    inventory_rows = [
        json.loads(line)
        for line in result.paths.voice_binding_inventory_v1.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]

    assert [row["status"] for row in inventory_rows] == ["shortfall"]
    assert result.paths.quarantine_v1.read_bytes() == b""
    assert result.paths.conflicts_v1.read_bytes() == b""
    report = json.loads(result.paths.build_report.read_text(encoding="utf-8"))
    assert report["row_counts"]["voice_binding_inventory"] == 1
    assert report["row_counts"]["quarantine"] == 0
    assert report["row_counts"]["conflicts"] == 0
    assert report["voice_status_counts"] == {"shortfall": 1}


def test_manifest_verifier_rejects_hash_drift_and_extra_files(tmp_path: Path) -> None:
    first = write_candidate_artifacts(tmp_path / "one", _artifact_input("drift-a"))
    first.paths.child_blocks.write_bytes(first.paths.child_blocks.read_bytes() + b"{}\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_candidate_manifest(first.paths.build_root)

    second = write_candidate_artifacts(tmp_path / "two", _artifact_input("extra-a"))
    (second.paths.build_root / "unexpected.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="closure differs"):
        verify_candidate_manifest(second.paths.build_root)


def test_manifest_verifier_reports_historical_v2_missing_schema_shape(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    runtime = root / "runtime"
    runtime.mkdir(parents=True)
    media = runtime / "media_assets.v2.jsonl"
    media.write_bytes(b"{}\n")
    relative = "runtime/media_assets.v2.jsonl"
    manifest = {
        "schema_version": CORPUS_BUILD_SCHEMA_VERSION,
        "state": "blocked",
        "artifacts": [
            {
                "relative_path": relative,
                "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                "size": len(media.read_bytes()),
                "row_count": 1,
                "schema_version": "evb.media-asset/v2",
            }
        ],
    }
    (root / "build_manifest.json").write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(ValueError, match="historical v2 media artifact is missing its schema"):
        verify_candidate_manifest(root)
