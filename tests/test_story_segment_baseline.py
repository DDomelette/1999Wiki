from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.capture_story_segment_baseline import (
    _capture_or_replay_dense_rows,
    baseline_business_sha256,
    build_equivalence_rows,
    case_result_sha256,
    request_plan_from_receipt,
    sanitize_active_result,
)
from src.rag_eval.story_segment_baseline import (
    AtomEvidenceTarget,
    canonical_evidence_text,
    load_story_segment_eval,
    load_story_segment_thresholds,
    match_active_evidence_to_atoms,
    verify_eval_gold_against_atom_artifact,
)


def _sha(text: str) -> str:
    return hashlib.sha256(canonical_evidence_text(text).encode("utf-8")).hexdigest()


def _gold(
    atom_id: str = "story:100/story/step-1",
    *,
    query_id: str = "q-1",
    group: str = "g-1",
    title: str = "Data:Story/100.json",
    path: str = "$.1",
    source_hash: str = "a" * 64,
    text: str = "维尔汀: 我记得。",
) -> AtomEvidenceTarget:
    return AtomEvidenceTarget(
        query_id=query_id,
        atom_id=atom_id,
        required_atom_group=group,
        source_title=title,
        source_json_path=path,
        source_content_sha256=source_hash,
        normalized_evidence_sha256=_sha(text),
    )


def _result(
    *,
    text: str = "维尔汀: 我记得。",
    atom_id: str | None = None,
    path: str = "$.1",
    source_hash: str = "a" * 64,
    revid: int | None = 42,
    target_evidence_text: str | None = "维尔汀: 我记得。",
) -> dict[str, object]:
    source_ref: dict[str, object] = {
        "source_title": "Data:Story/100.json",
        "json_path": path,
        "source_content_sha256": source_hash,
    }
    if revid is not None:
        source_ref["revid"] = revid
    result: dict[str, object] = {"text": text, "source_refs": [source_ref]}
    if target_evidence_text is not None:
        result["gold_evidence_text_by_sha256"] = {_sha(target_evidence_text): target_evidence_text}
    if atom_id is not None:
        result["atom_id"] = atom_id
        result["normalized_evidence_sha256"] = _sha(text)
    return result


def test_canonical_evidence_text_only_applies_nfc_and_newline_normalization():
    assert canonical_evidence_text("e\u0301  x\r\ny\rz") == "é  x\ny\nz"
    assert canonical_evidence_text(" a\t b ") == " a\t b "


def test_matches_exact_atom_identity_before_other_rules():
    matches = match_active_evidence_to_atoms(
        [_result(atom_id="story:100/story/step-1", path="$.other")],
        [_gold()],
        stage="retrieval_at_k",
    )
    assert len(matches) == 1
    assert matches[0].match_rule == "exact_atom_id"
    assert matches[0].matched is True
    assert matches[0].result_rank == 1


def test_exact_atom_identity_requires_matching_normalized_content_hash():
    result = _result(atom_id="story:100/story/step-1")
    result["normalized_evidence_sha256"] = "f" * 64
    match = match_active_evidence_to_atoms(
        [result], [_gold()], stage="retrieval_at_k"
    )[0]
    assert match.matched is False
    assert match.reason_code == "atom_identity_content_hash_mismatch"


def test_matches_exact_source_path_revision_hash():
    match = match_active_evidence_to_atoms(
        [_result()], [_gold()], stage="final_context"
    )[0]
    assert match.match_rule == "exact_source_path_revision_hash"
    assert match.matched is True


def test_matches_unique_exact_text_span_with_unicode_code_point_offsets():
    text = "开头🙂维尔汀: 我记得。结尾"
    match = match_active_evidence_to_atoms(
        [_result(text=text, path="$.other")],
        [_gold()],
        stage="final_context",
    )[0]
    assert match.match_rule == "unique_exact_text_span"
    assert match.matched_span == (3, 12)
    assert text[slice(*match.matched_span)] == "维尔汀: 我记得。"


def test_duplicate_text_is_ambiguous():
    match = match_active_evidence_to_atoms(
        [_result(text="维尔汀: 我记得。/维尔汀: 我记得。", path="$.other")],
        [_gold()],
        stage="retrieval_at_k",
    )[0]
    assert match.match_rule == "ambiguous"
    assert match.matched is False
    assert match.reason_code == "evidence_text_occurs_multiple_times"


def test_source_version_mismatch_never_falls_back_to_text():
    match = match_active_evidence_to_atoms(
        [_result(path="$.other", source_hash="b" * 64)],
        [_gold()],
        stage="retrieval_at_k",
    )[0]
    assert match.match_rule == "unmatched"
    assert match.reason_code == "source_version_mismatch"


def test_migration_group_without_atom_evidence_does_not_match():
    result = _result(path="$.other")
    result["corrected_semantics"] = {"expansion_group": "g-1"}
    result["text"] = "无关正文"
    match = match_active_evidence_to_atoms(
        [result], [_gold()], stage="retrieval_at_k"
    )[0]
    assert match.matched is False


def test_empty_source_refs_fail_closed():
    match = match_active_evidence_to_atoms(
        [{"text": "维尔汀: 我记得。", "source_refs": []}],
        [_gold()],
        stage="retrieval_at_k",
    )[0]
    assert match.matched is False
    assert match.reason_code == "missing_source_ref"


def test_same_span_cannot_be_consumed_by_multiple_atoms():
    gold = [
        _gold(atom_id="story:100/story/step-1", path="$.1"),
        _gold(atom_id="story:100/story/step-2", path="$.2"),
    ]
    matches = match_active_evidence_to_atoms(
        [_result(path="$.other")], gold, stage="retrieval_at_k"
    )
    assert [item.match_rule for item in matches] == ["ambiguous", "ambiguous"]
    assert all(item.reason_code == "shared_evidence_text_ambiguous" for item in matches)


def test_stages_are_independent_and_invalid_stage_is_rejected():
    retrieval = match_active_evidence_to_atoms(
        [_result()], [_gold()], stage="retrieval_at_k"
    )[0]
    final = match_active_evidence_to_atoms(
        [], [_gold()], stage="final_context"
    )[0]
    assert retrieval.matched is True
    assert final.matched is False
    with pytest.raises(ValueError, match="stage"):
        match_active_evidence_to_atoms([], [_gold()], stage="answer")  # type: ignore[arg-type]


def test_answer_rewrite_and_summary_are_never_evidence():
    result = {
        "text": "无关正文",
        "source_refs": _result()["source_refs"],
        "answer": "维尔汀: 我记得。",
        "planner_rewrite": "维尔汀: 我记得。",
        "summary": "维尔汀: 我记得。",
    }
    match = match_active_evidence_to_atoms(
        [result], [_gold()], stage="final_context"
    )[0]
    assert match.matched is False


def test_load_frozen_eval_and_threshold_contracts():
    cases = load_story_segment_eval(Path("eval/story_segment_eval.v1.jsonl"))
    thresholds = load_story_segment_thresholds(
        Path("eval/story_segment_thresholds.v1.json")
    )
    assert len(cases) >= 80
    assert len({case.query_id for case in cases}) == len(cases)
    assert sum(case.stratum == "exact_atom" for case in cases) >= 12
    assert sum(case.stratum == "single_story_fact" for case in cases) >= 10
    assert sum(case.stratum == "single_story_multi_detail" for case in cases) >= 10
    assert sum(case.stratum == "branch_boundary" for case in cases) >= 8
    assert sum(case.stratum == "multi_story" for case in cases) >= 8
    assert sum(case.stratum == "topic_story" for case in cases) >= 8
    assert sum(case.stratum == "character_story_shortfall" for case in cases) >= 4
    assert sum(case.stratum == "authorization" for case in cases) >= 12
    assert sum(case.stratum == "answer_scope" for case in cases) >= 8
    assert thresholds.schema_version == "rag.story-segment-thresholds/v1"
    assert thresholds.hard_gates["atom_bm25_recall_at_80"]["minimum"] == 0.95
    assert thresholds.hard_gates["reranker_api_calls"]["maximum"] == 0
    assert {case.query for case in cases} >= {
        "6是谁？",
        "37有什么技能？",
        "暴雨在哪些剧情中造成了影响？",
        "伊索尔德是怎么疯掉的？请结合剧情《第六章6-5.1》作有限综合。",
    }
    query_types = {case.query_type for case in cases}
    assert {"internal_story_id", "long_substring_negative", "character_skill_story_composite", "mixed_composite"} <= query_types


def test_frozen_scope_authorization_and_source_span_invariants():
    cases = load_story_segment_eval(Path("eval/story_segment_eval.v1.jsonl"))
    for case in cases:
        for span in case.request_plan_source_spans:
            assert case.query[span["start"] : span["end"]] == span["text"]
        scope = case.expected_answer_scope
        if case.expected_retrieval_outcome in {"failed", "not_applicable"}:
            assert scope == {"applicable": False, "value": None}
        if scope["applicable"]:
            assert scope["value"]["narrative_coverage"] in {"local", "bounded", "non_exhaustive"}
        if case.expected_authorization_origin == "verified_continuation":
            assert not case.request_plan_source_spans
        if case.expected_authorization_origin == "validated_conversation_anchor":
            assert not case.request_plan_source_spans


def test_thresholds_encode_every_spec_hard_gate_separately():
    thresholds = load_story_segment_thresholds(Path("eval/story_segment_thresholds.v1.json"))
    required = {
        "atom_bm25_recall_at_80",
        "segment_dense_recall_at_30",
        "fused_segment_recall_at_8",
        "final_evidence_recall",
        "middle_late_final_evidence_recall_delta",
        "fused_mrr_at_8",
        "fused_ndcg_at_8",
        "story_explicit_one_to_three_owner_coverage",
        "required_story_authorization_precision",
        "policy_story_mention_recall",
        "policy_story_mention_precision",
        "request_plan_occurrence_unique_assignment_rate",
        "provisional_final_transaction_closure",
        "fallback_unaffected_subtask_retention_rate",
        "non_story_false_rejection_count",
        "planner_mutation_wrong_authorization_count",
        "ambiguous_story_detection_retriever_calls",
        "validated_continuation_correctness",
        "continuation_frontend_field_loss_rate",
        "continuation_authorized_page_rate",
        "continuation_planner_calls",
        "continuation_composite_comparison_count",
        "validated_anchor_authorization_precision",
        "validated_anchor_invalid_set_count",
        "validated_anchor_conflict_revival_count",
        "multi_detail_coverage_rate",
        "topic_page_required_source_retention",
        "story_duplicate_body_rate",
        "atom_citation_closure_rate",
        "story_cross_branch_expansion_rate",
        "owner_gate_unauthorized_rate",
        "published_character_relation_precision",
        "reviewable_character_relation_recall",
        "protected_query_non_regression_rate",
        "baseline_equivalence_false_coverage_count",
        "oversized_atom_mapping_body_citation_closure_rate",
        "full_chain_success_rate",
        "dense_embedding_calls_per_knowledge_subtask",
        "request_detector_calls",
        "story_local_pipeline_p95_ms",
        "shortfall_false_refusal_count",
        "story_answer_scope_applicability_rate",
        "story_answer_scope_deterministic_bytes_rate",
        "not_applicable_empty_fallback_isolation_rate",
        "request_retrieval_outcome_projection_rate",
        "nonexhaustive_overclaim_count",
        "answer_scope_added_api_calls",
        "reranker_api_calls",
        "retrieval_p95_ms",
        "ttft_p95_ms",
        "response_total_p95_ms",
        "typed_dense_story_segment_row_limit",
        "story_query_time_full_scan_count",
        "candidate_remaining_capacity_bytes",
        "active_or_provenance_drift_count",
    }
    assert required <= set(thresholds.hard_gates)


def test_every_gold_atom_is_bound_to_the_c_release_artifact():
    cases = load_story_segment_eval(Path("eval/story_segment_eval.v1.jsonl"))
    assert all(case.gold_artifact_sha256 == "40d17b412a60c44bcdab953d9d382d3fb32f0812026b0eb51b972961c40999a1" for case in cases)
    targets = [target for case in cases for group in case.required_atom_groups for target in group.atoms]
    assert targets
    assert all(target.source_title.startswith("Data:Story/") for target in targets)
    assert all(len(target.normalized_evidence_sha256) == 64 for target in targets)
    assert verify_eval_gold_against_atom_artifact(
        cases,
        Path("eval/story_segment/dependencies/c-release-20260802T110503Z/published-story-v1/story_atoms.v1.jsonl"),
        expected_artifact_sha256="40d17b412a60c44bcdab953d9d382d3fb32f0812026b0eb51b972961c40999a1",
    ) == len({target.atom_id for target in targets})


def test_loader_rejects_free_text_gold_or_unknown_threshold_direction(tmp_path: Path):
    bad_eval = tmp_path / "bad.jsonl"
    bad_eval.write_text(
        json.dumps({"schema_version": "rag.story-segment-eval-case/v1", "query_id": "bad", "query": "x", "stratum": "exact_atom", "gold_artifact_sha256": "a" * 64, "required_atom_groups": [{"group_id": "g", "expected": "差不多命中"}]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_story_segment_eval(bad_eval)

    bad_thresholds = tmp_path / "bad-thresholds.json"
    bad_thresholds.write_text(
        json.dumps({"schema_version": "rag.story-segment-thresholds/v1", "denominator_definitions": {"all": "all reviewed cases"}, "hard_gates": {"x": {"direction": "average", "minimum": 1, "denominator": "all"}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="direction"):
        load_story_segment_thresholds(bad_thresholds)


def test_baseline_business_sha_excludes_only_declared_run_metadata():
    first = {
        "schema_version": "rag.story-segment-active-baseline/v1",
        "captured_at_utc": "2026-08-02T00:00:00Z",
        "run_id": "run-a",
        "cases": [{"query_id": "q-1", "retrieval": [{"child_id": "c-1"}]}],
    }
    second = {
        **first,
        "captured_at_utc": "2026-08-02T00:01:00Z",
        "run_id": "run-b",
    }
    assert baseline_business_sha256(first) == baseline_business_sha256(second)
    second["cases"] = [{"query_id": "q-1", "retrieval": [{"child_id": "c-2"}]}]
    assert baseline_business_sha256(first) != baseline_business_sha256(second)


def test_case_result_sha_covers_plan_and_retrieval_but_not_itself():
    case = {"query_id": "q-1", "request_plan": {"status": "llm"}, "retrieval_at_k": []}
    digest = case_result_sha256(case)
    assert case_result_sha256({**case, "result_sha256": digest}) == digest
    assert case_result_sha256({**case, "retrieval_at_k": [{"child_id": "c-1"}]}) != digest


def test_sanitize_active_result_retains_only_source_backed_evidence_fields():
    result = sanitize_active_result(
        {
            "child_id": "child-1",
            "parent_id": "parent-1",
            "content": "来源正文",
            "source_refs": [
                {
                    "source_title": "Data:Story/100.json",
                    "json_path": "$.1",
                    "source_content_sha256": "a" * 64,
                    "revid": 42,
                    "private": "drop-me",
                }
            ],
            "score": 0.75,
            "answer": "不得作为证据",
            "planner_rewrite": "不得作为证据",
            "api_key": "secret",
        }
    )
    assert result == {
        "atom_id": None,
        "category": "",
        "child_id": "child-1",
        "content": "来源正文",
        "entity_id": "",
        "entity_name": "",
        "entity_type": "",
        "heading_path": "",
        "normalized_evidence_sha256": _sha("来源正文"),
        "owner_entity_id": "",
        "owner_page_id": "",
        "parent_id": "parent-1",
        "score": 0.75,
        "section_kind": "",
        "source_refs": [
            {
                "json_path": "$.1",
                "revid": 42,
                "source_content_sha256": "a" * 64,
                "source_title": "Data:Story/100.json",
            }
        ],
    }


def test_equivalence_rows_are_canonical_and_stage_isolated():
    gold = _gold(text="目标证据")
    active = _result(text="目标证据", target_evidence_text="目标证据")
    observations = {
        "q-1": {
            "retrieval_at_k": [{**active, "score": 0.9}],
            "final_context": [],
        }
    }
    rows = build_equivalence_rows(
        {"q-1": (gold,)},
        observations,
        evidence_text_by_sha256={_sha("目标证据"): "目标证据"},
    )
    assert [(row["stage"], row["matched"]) for row in rows] == [
        ("retrieval_at_k", True),
        ("final_context", False),
    ]
    assert rows[0]["active_source_refs"] == active["source_refs"]
    assert rows[0]["target_source_ref"] == {
        "json_path": "$.1",
        "source_content_sha256": "a" * 64,
        "source_title": "Data:Story/100.json",
    }


def test_request_plan_receipt_replay_round_trips_without_planner_call():
    from src.rag.query_plan import QueryPlan
    from src.rag.request_plan import PlannedSubtask, RequestPlan

    query_plan = QueryPlan(
        original_query="剧情《测试》讲了什么？",
        normalized_query="剧情《测试》讲了什么？",
        entity="测试",
        aliases=("测试别名",),
        intent="story",
        section_hints=("story",),
        scatter_terms=("测试", "剧情"),
        confidence=0.9,
        entity_type="story",
        entity_id="100",
        dense_query="测试 剧情",
        sparse_query="测试 剧情",
        target_levels=("story", "line"),
        secondary_intents=("lore",),
        retrieval_scope="topic_strict",
    )
    original = RequestPlan(
        original_query="剧情《测试》讲了什么？",
        subtasks=(
            PlannedSubtask(
                subtask_id="T01",
                order=1,
                task_type="knowledge_base",
                query="剧情《测试》讲了什么？",
                query_plan=query_plan,
                depends_on=(),
            ),
        ),
        planning_status="llm",
    )
    replayed = request_plan_from_receipt(json.loads(json.dumps(original, default=lambda value: value.__dict__)))
    assert replayed == original


def test_dense_candidate_cassette_replay_never_calls_embedding_search():
    class FakeRetriever:
        def __init__(self):
            self.calls = 0

        def _dense_rows_for_plan(self, query, plan, candidate_k):
            self.calls += 1
            return [{"child_id": "dense-1", "text": query, "vector_score": 0.5}]

    retriever = FakeRetriever()
    with _capture_or_replay_dense_rows(retriever, None) as captured:
        assert retriever._dense_rows_for_plan("query", object(), 80)[0]["child_id"] == "dense-1"
    assert retriever.calls == 1
    assert captured == [{"child_id": "dense-1", "text": "query", "vector_score": 0.5}]

    with _capture_or_replay_dense_rows(retriever, captured) as replayed:
        assert retriever._dense_rows_for_plan("changed", object(), 80) == captured
    assert retriever.calls == 1
    assert replayed == captured
