from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.rag_eval.contracts import (
    CaseResult,
    Difficulty,
    EvalCase,
    JudgeIdentity,
    RunManifest,
    Severity,
    load_thresholds,
)
from src.rag_eval.reporting import REQUIRED_ARTIFACTS, write_run_evidence
from src.rag_eval.scoring import classify_run


THRESHOLDS = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))


def _payloads():
    manifest = RunManifest(
        run_id="run-001",
        started_at_utc="2026-07-13T00:00:00Z",
        seed=1999,
        build_version="test",
        collection_name="test_collection",
        production_model="production-model",
        judge_identity=JudgeIdentity(
            base_url="https://judge.invalid/v1",
            model="judge-model",
            prompt_version="rag_eval.answer_judge/v1",
        ),
        thresholds_sha256="a" * 64,
    )
    samples = [
        EvalCase(
            case_id=f"case-{index:02d}",
            query="介绍测试实体",
            difficulty=(Difficulty.D1, Difficulty.D2, Difficulty.D3, Difficulty.D4)[index % 4],
            scenario="text",
            expected_entity_id=f"entity-{index:02d}",
            expected_ownership_key=("fixture", f"entity-{index:02d}"),
        )
        for index in range(12)
    ]
    cases = [
        CaseResult(
            case_id=sample.case_id,
            difficulty=sample.difficulty,
            scenario="text",
            module_scores={"M2": 100, "M3": 100, "M5": 100},
            observed={"answer": "受支持的答案", "debug_path": r"D:\\secret\\file"},
            judge={"score": 5, "api_key": "super-secret"},
            score=100,
        )
        for sample in samples
    ]
    summary = classify_run(cases, THRESHOLDS)
    snapshot = {
        "schema_version": "rag_eval.protected_snapshot/v2",
        "milvus": {"primary_ids_sha256": "b" * 64},
        "minio_inventories": {},
        "mysql_tables": {},
        "artifacts": {},
        "captured_at_utc": "2026-07-15T00:00:00Z",
    }
    return manifest, samples, cases, summary, snapshot


def test_write_run_evidence_creates_complete_hash_chained_bundle(tmp_path):
    manifest, samples, cases, summary, snapshot = _payloads()
    run_dir = write_run_evidence(
        output_root=tmp_path,
        manifest=manifest,
        samples=samples,
        cases=cases,
        summary=summary,
        pre_snapshot=snapshot,
        post_snapshot=snapshot,
        adjudication_queue=[],
        memory_pair_results=[],
        stage_latency={"dominant_stage": "retrieval.dense"},
        isolated_route_failure={
            "schema_version": "rag_eval.isolated_route_failure/v1",
            "passed": True,
        },
    )
    assert {path.name for path in run_dir.iterdir()} == set(REQUIRED_ARTIFACTS)

    previous_sha = None
    for name in REQUIRED_ARTIFACTS:
        path = run_dir / name
        if name.endswith(".md"):
            text = path.read_text(encoding="utf-8")
            assert "super-secret" not in text
            assert r"D:\\secret\\file" not in text
            previous_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            continue
        if name.endswith(".jsonl"):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            assert rows or name in {
                "adjudication_queue.v2.jsonl",
                "memory_pair_results.v1.jsonl",
            }
            for row in rows:
                assert row["schema_version"].startswith("rag_eval.")
                assert row["predecessor_sha256"] == previous_sha
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert payload["schema_version"].startswith("rag_eval.")
            assert payload["predecessor_sha256"] == previous_sha
        previous_sha = hashlib.sha256(path.read_bytes()).hexdigest()


def test_write_run_evidence_refuses_existing_run_id(tmp_path):
    args = _payloads()
    write_run_evidence(
        output_root=tmp_path,
        manifest=args[0],
        samples=args[1],
        cases=args[2],
        summary=args[3],
        pre_snapshot=args[4],
        post_snapshot=args[4],
        adjudication_queue=[],
        memory_pair_results=[],
        stage_latency={},
    )
    with pytest.raises(FileExistsError, match="run-001"):
        write_run_evidence(
            output_root=tmp_path,
            manifest=args[0],
            samples=args[1],
            cases=args[2],
            summary=args[3],
            pre_snapshot=args[4],
            post_snapshot=args[4],
            adjudication_queue=[],
            memory_pair_results=[],
            stage_latency={},
        )


def test_report_is_concise_and_has_exactly_five_module_rows(tmp_path):
    manifest, samples, cases, summary, snapshot = _payloads()
    run_dir = write_run_evidence(
        output_root=tmp_path,
        manifest=manifest,
        samples=samples,
        cases=cases,
        summary=summary,
        pre_snapshot=snapshot,
        post_snapshot=snapshot,
        adjudication_queue=[],
        memory_pair_results=[],
        stage_latency={},
    )
    report = (run_dir / "evaluation_report.v2.md").read_text(encoding="utf-8")
    assert report.count("| M1 ") == 1
    assert report.count("| M2 ") == 1
    assert report.count("| M3 ") == 1
    assert report.count("| M4 ") == 1
    assert report.count("| M5 ") == 1
    assert "## D1-D4" in report
    assert "## Failure Clusters" in report
    assert "## Remediation" in report
    assert "Run ID: **run-001**" in report
    assert "Snapshot equal: **true**" in report
    assert "READY-P0-01" in report
    assert "RELY-P0-04" in report
    assert len(report.splitlines()) < 100


def test_v2_human_audit_manifest_is_reproducible_and_hash_pinned(tmp_path):
    manifest, samples, cases, summary, snapshot = _payloads()

    run_dir = write_run_evidence(
        output_root=tmp_path,
        manifest=manifest,
        samples=samples,
        cases=cases,
        summary=summary,
        pre_snapshot=snapshot,
        post_snapshot=snapshot,
        adjudication_queue=[],
        memory_pair_results=[],
        stage_latency={},
    )

    audit_rows = [
        json.loads(line)
        for line in (run_dir / "human_audit_manifest.v1.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    case_rows = [
        json.loads(line)
        for line in (run_dir / "case_results.v2.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    case_hashes = {
        row["case_id"]: hashlib.sha256(
            (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        for row in case_rows
    }

    assert len(audit_rows) == 12
    assert len({row["case_id"] for row in audit_rows}) == 12
    assert all(row["seed"] == 1999 for row in audit_rows)
    assert all(row["evidence_sha256"] == case_hashes[row["case_id"]] for row in audit_rows)
    assert all(row["evidence_ref"].startswith("case_results.v2.jsonl#") for row in audit_rows)
