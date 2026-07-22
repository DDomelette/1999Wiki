from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.rag_eval.contracts import (
    Difficulty,
    EvalCase,
    EvaluationEvent,
    JudgeIdentity,
    RunManifest,
    Severity,
    load_thresholds,
    worst_severity,
)


def test_severity_order_is_incident_order_and_otel_mapping_is_stable():
    assert Severity.PASS.rank == 5
    assert Severity.SEV4.otel_number == 9
    assert Severity.SEV3.otel_number == 13
    assert Severity.SEV2.otel_number == 17
    assert Severity.SEV1.otel_number == 20
    assert Severity.SEV0.otel_number == 21
    assert worst_severity([Severity.SEV3, Severity.SEV1]) is Severity.SEV1
    assert worst_severity([]) is Severity.PASS


def test_event_rejects_mismatched_severity_number():
    with pytest.raises(ValueError, match="severity_number"):
        EvaluationEvent(
            event_code="RETR.CROSS_ENTITY_SOURCE",
            module="M2",
            severity=Severity.SEV1,
            severity_number=17,
        )


def test_event_rejects_unknown_module_and_malformed_code():
    with pytest.raises(ValueError, match="module"):
        EvaluationEvent(
            event_code="RETR.CROSS_ENTITY_SOURCE",
            module="retrieval",
            severity=Severity.SEV1,
            severity_number=20,
        )
    with pytest.raises(ValueError, match="event_code"):
        EvaluationEvent(
            event_code="cross entity source",
            module="M2",
            severity=Severity.SEV1,
            severity_number=20,
        )


def test_judge_identity_contains_no_secret_field():
    identity = JudgeIdentity(
        base_url="https://judge.example/v1",
        model="judge-model",
        prompt_version="rag-answer-judge/v1",
    )
    assert set(identity.to_json()) == {"base_url", "model", "prompt_version"}


def test_load_reviewed_thresholds():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    assert thresholds.schema_version == "rag_eval.thresholds/v1"
    assert thresholds.sample_minimums["unique"] == 48
    assert thresholds.difficulty[Difficulty.D3].floor == 70
    assert thresholds.reliability["success_rate_min"] == 0.98
    assert "voice" in thresholds.p0_intents
    assert thresholds.reliability["retrieval_p95_ms"] == 5000
    assert thresholds.reliability["ttft_p95_ms"] == 15000
    assert thresholds.reliability["total_p95_ms"] == 45000


def test_run_manifest_defaults_to_v2_schema():
    manifest = RunManifest(
        run_id="run-v2",
        started_at_utc="2026-07-15T00:00:00Z",
        seed=1999,
        build_version="fixture",
        collection_name="fixture",
        production_model="fixture",
        judge_identity=JudgeIdentity("https://judge", "judge", "v2"),
        thresholds_sha256="a" * 64,
    )

    assert manifest.schema_version == "rag_eval.run_manifest/v2"


def test_v2_eval_case_carries_owner_route_and_conversation_contracts():
    case = EvalCase(
        case_id="route-fixture",
        query="测试查询",
        difficulty=Difficulty.D4,
        scenario="boundary",
        expected_ownership_key=("character", "entity-a"),
        route_options={"free_supplement": True},
        action_payload={"type": "force_free_supplement"},
        expected_retrieval_outcome="empty",
        expected_effective_route="llm_general",
        conversation_mode="oracle_standalone",
    )

    payload = case.to_json()

    assert payload["expected_ownership_key"] == ["character", "entity-a"]
    assert payload["route_options"] == {"free_supplement": True}
    assert payload["action_payload"] == {"type": "force_free_supplement"}
    assert payload["expected_retrieval_outcome"] == "empty"
    assert payload["expected_effective_route"] == "llm_general"
    assert payload["conversation_mode"] == "oracle_standalone"


def test_threshold_loader_rejects_weakened_sample_minima(tmp_path: Path):
    source = json.loads(
        Path("eval/rag_full_chain_thresholds.v1.json").read_text(encoding="utf-8")
    )
    source["sample_minimums"]["unique"] = 47
    path = tmp_path / "weak.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="unique"):
        load_thresholds(path)


def test_threshold_loader_rejects_bad_weights_and_intent_list(tmp_path: Path):
    source = json.loads(
        Path("eval/rag_full_chain_thresholds.v1.json").read_text(encoding="utf-8")
    )
    source["weights"]["text"]["M5"] = 0.2
    source["p0_intents"] = ["intro"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="p0_intents"):
        load_thresholds(path)
