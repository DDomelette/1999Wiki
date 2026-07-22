from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.rag_eval.client import ObservedExchange, TimingObservation
from src.rag_eval.contracts import Difficulty, EvalCase, Severity, load_thresholds
from src.rag_eval.deterministic import (
    evaluate_deterministic,
    evaluate_reliability,
    mrr,
    ndcg_at_k,
    recall_at_k,
)
from src.rag_eval.inventory import ChildRecord, EntityRecord, EvaluationInventory, MediaRecord


def _inventory() -> EvaluationInventory:
    child_a = ChildRecord(
        child_id="fixture:entity-a/skill:1",
        parent_id="fixture:entity-a/skills",
        entity_id="entity-a",
        entity_name="测试实体甲",
        entity_type="character",
        category="character",
        section_kind="skill",
        title="测试实体甲 / 技能",
        route_tags=("skill",),
        text="技能证据",
        media_ids=("media:sha1:" + "a" * 40,),
    )
    child_b = ChildRecord(
        child_id="fixture:entity-b/profile:1",
        parent_id="fixture:entity-b/profile",
        entity_id="entity-b",
        entity_name="测试实体乙",
        entity_type="character",
        category="character",
        section_kind="profile",
        title="测试实体乙 / 资料",
        route_tags=("intro",),
        text="资料证据",
        media_ids=(),
    )
    media_id = "media:sha1:" + "a" * 40
    media = MediaRecord(
        media_id=media_id,
        entity_id="entity-a",
        entity_name="测试实体甲",
        parent_id=child_a.parent_id,
        child_id=child_a.child_id,
        asset_type="voice",
        mime="audio/mpeg",
        url="http://example.test/voice.mp3",
        is_available=True,
        is_common=False,
        language="zh",
        event_name="测试台词",
        sort_order=0,
    )
    return EvaluationInventory(
        build_version="fixture",
        entities={
            "entity-a": EntityRecord(
                entity_id="entity-a",
                entity_name="测试实体甲",
                entity_type="character",
                category="character",
                aliases=(),
                child_ids_by_intent={"skill": (child_a.child_id,), "voice": (child_a.child_id,)},
                media_ids_by_type={"voice": (media_id,)},
            ),
            "entity-b": EntityRecord(
                entity_id="entity-b",
                entity_name="测试实体乙",
                entity_type="character",
                category="character",
                aliases=(),
                child_ids_by_intent={"intro": (child_b.child_id,)},
                media_ids_by_type={},
            ),
        },
        children={child_a.child_id: child_a, child_b.child_id: child_b},
        media={media_id: (media,)},
        parent_ids=(child_a.parent_id, child_b.parent_id),
        sha256="f" * 64,
    )


def _case(*, voice=False) -> EvalCase:
    child_id = "fixture:entity-a/skill:1"
    media_id = "media:sha1:" + "a" * 40
    return EvalCase(
        case_id="fixture-case",
        query="测试实体甲的语音" if voice else "测试实体甲的技能",
        difficulty=Difficulty.D1,
        scenario="media" if voice else "text",
        expected_entity_id="entity-a",
        expected_entity_ids=("entity-a",),
        expected_entity_name="测试实体甲",
        expected_ownership_key=("character", "entity-a"),
        expected_intents=("voice" if voice else "skill",),
        expected_source_ids=(child_id,),
        source_relevance={child_id: 2.0},
        expected_media_ids=(media_id,) if voice else (),
        forbidden_media_types=() if voice else ("voice",),
    )


def _exchange(*, sources=None, media=None, panels=None, route=None, success=True, error=""):
    return ObservedExchange(
        case_id="fixture-case",
        endpoint="/ask/stream",
        success=success,
        status_code=200 if success else 500,
        route=route
        or {
            "entity": "测试实体甲",
            "intent": "skill",
            "requested_intents": ["skill"],
            "retrieval_debug": {"coverage_shortfall": {"skill": 0}},
        },
        sources=tuple(
            sources
            or [
                {
                    "name": "测试实体甲",
                    "child_id": "fixture:entity-a/skill:1",
                    "parent_id": "fixture:entity-a/skills",
                    "section_kind": "skill",
                }
            ]
        ),
        media=tuple(media or []),
        media_panels=tuple(panels or []),
        failure_actions=(),
        answer="回答" if success else "",
        timing=TimingObservation("now", 100.0, 200.0, 300.0),
        error=error,
    )


def test_rank_metrics_use_dynamic_qrels():
    ranked = ["x", "b", "a"]
    relevant = {"a": 2.0, "b": 1.0}

    assert recall_at_k(ranked, relevant, 3) == 1.0
    assert mrr(ranked, relevant) == 0.5
    assert 0.0 < ndcg_at_k(ranked, relevant, 3) <= 1.0


def test_cross_entity_source_is_sev1_and_cannot_be_averaged():
    exchange = _exchange(
        sources=[
            {
                "name": "测试实体乙",
                "child_id": "fixture:entity-b/profile:1",
                "parent_id": "fixture:entity-b/profile",
                "section_kind": "profile",
            }
        ]
    )

    result = evaluate_deterministic(
        _case(),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert any(
        event.event_code == "RETR.CROSS_ENTITY_SOURCE" and event.severity is Severity.SEV1
        for event in result.events
    )


def test_owner_fields_detect_cross_entity_even_when_child_is_unknown():
    exchange = _exchange(
        sources=[
            {
                "citation_id": "S01",
                "name": "测试实体乙",
                "child_id": "fixture:unknown",
                "entity_type": "character",
                "entity_id": "entity-b",
            }
        ]
    )

    result = evaluate_deterministic(
        _case(),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    event = next(event for event in result.events if event.event_code == "RETR.CROSS_ENTITY_SOURCE")
    assert event.severity is Severity.SEV1
    assert event.observed["ownership_keys"] == [["character", "entity-b"]]


def test_cross_entity_media_has_dedicated_sev1_event():
    exchange = _exchange(
        media=[
            {
                "media_id": "foreign-media",
                "asset_type": "image",
                "url": "http://example.test/foreign.png",
                "entity_type": "character",
                "entity_id": "entity-b",
            }
        ]
    )

    result = evaluate_deterministic(
        _case(),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert any(
        event.event_code == "MEDIA.CROSS_ENTITY_MEDIA"
        and event.severity is Severity.SEV1
        for event in result.events
    )


def test_unauthorized_general_and_semantic_intent_overwrite_are_stable_events():
    case = replace(
        _case(),
        route_options={"free_supplement": False},
        expected_retrieval_outcome="sufficient",
        expected_effective_route="rag_grounded",
    )
    exchange = _exchange(
        route={
            "entity": "测试实体甲",
            "semantic_intents": ["voice"],
            "requested_intents": ["voice"],
            "proposed_route": "llm_general",
            "effective_route": "llm_general",
            "retrieval_outcome": "sufficient",
        }
    )

    result = evaluate_deterministic(
        case,
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    codes = {event.event_code: event.severity for event in result.events}
    assert codes["ROUTE.UNAUTHORIZED_GENERAL"] is Severity.SEV1
    assert codes["ROUTE.INTENT_OVERWRITTEN"] is Severity.SEV2


def test_expected_semantic_intents_allow_planner_superset_without_overwrite_event():
    case = replace(_case(), expected_intents=("skill",))
    exchange = _exchange(
        route={
            "semantic_intents": ["skill", "profile_fact"],
            "requested_intents": ["skill", "profile_fact"],
            "proposed_route": "rag_grounded",
            "effective_route": "rag_grounded",
            "retrieval_outcome": "sufficient",
        }
    )

    result = evaluate_deterministic(
        case,
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert all(event.event_code != "ROUTE.INTENT_OVERWRITTEN" for event in result.events)


def test_route_contract_detects_retrieval_outcome_mismatch_even_when_route_matches():
    case = replace(
        _case(),
        expected_retrieval_outcome="partial",
        expected_effective_route="rag_grounded",
    )
    exchange = _exchange(
        route={
            "semantic_intents": ["skill"],
            "proposed_route": "rag_grounded",
            "effective_route": "rag_grounded",
            "retrieval_outcome": "sufficient",
        }
    )

    result = evaluate_deterministic(
        case,
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert any(event.event_code == "ROUTE.DECISION_MISMATCH" for event in result.events)


def test_unknown_citation_and_transported_invalid_draft_are_sev1():
    exchange = replace(
        _exchange(
            sources=[
                {
                    "citation_id": "S01",
                    "name": "测试实体甲",
                    "child_id": "fixture:entity-a/skill:1",
                    "entity_type": "character",
                    "entity_id": "entity-a",
                }
            ]
        ),
        answer="错误引用。[S99]",
        grounding_mode="grounded",
        source_map={"S01": {"child_id": "fixture:entity-a/skill:1"}},
        raw={"citation_warning": "invalid_citation_label"},
    )

    result = evaluate_deterministic(
        _case(),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    codes = {event.event_code: event.severity for event in result.events}
    assert codes["CITE.UNKNOWN_OR_STALE_ID"] is Severity.SEV1
    assert codes["CITE.INVALID_DRAFT_TRANSPORTED"] is Severity.SEV1


def test_safe_citation_fallback_and_incomplete_stage_trace_are_sev2():
    exchange = replace(
        _exchange(),
        answer="检索到的资料不足以可靠生成完整回答 [S01]。",
        grounding_mode="grounded",
        raw={"citation_warning": "citation_safe_fallback"},
        stage_trace={"stage_ms": {"route.resolve": 1.0}, "error_stages": []},
    )

    result = evaluate_deterministic(
        _case(),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    codes = {event.event_code: event.severity for event in result.events}
    assert codes["CITE.SAFE_FALLBACK_USED"] is Severity.SEV2
    assert codes["RELY.STAGE_SPAN_INCOMPLETE"] is Severity.SEV2


def test_empty_grounded_path_does_not_require_answer_or_citation_spans():
    stages = {
        "planner.normalize": 1.0,
        "route.resolve": 1.0,
        "source_map.build": 1.0,
        "media.attach": 1.0,
        "response.serialize": 1.0,
        "memory.acquire": 1.0,
        "retrieval.dense": 1.0,
    }
    exchange = replace(
        _exchange(sources=[]),
        route_decision={
            "effective_route": "rag_grounded",
            "retrieval_outcome": "empty",
            "route_reason": "grounded_empty",
        },
        stage_trace={"stage_ms": stages, "error_stages": []},
    )

    result = evaluate_deterministic(
        replace(_case(), allow_no_sources=True, expected_source_ids=(), source_relevance={}),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert "RELY.STAGE_SPAN_INCOMPLETE" not in {event.event_code for event in result.events}


def test_explicit_free_path_does_not_require_retrieval_spans():
    stages = {
        "planner.normalize": 1.0,
        "route.resolve": 1.0,
        "source_map.build": 1.0,
        "media.attach": 1.0,
        "answer.llm": 1.0,
        "citation.validate": 1.0,
        "response.serialize": 1.0,
        "memory.acquire": 1.0,
    }
    exchange = replace(
        _exchange(sources=[]),
        route_decision={
            "effective_route": "llm_general",
            "retrieval_outcome": "empty",
            "route_reason": "explicit_recovery_action",
        },
        stage_trace={"stage_ms": stages, "error_stages": []},
    )

    result = evaluate_deterministic(
        replace(_case(), allow_no_sources=True, expected_source_ids=(), source_relevance={}),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert "RELY.STAGE_SPAN_INCOMPLETE" not in {event.event_code for event in result.events}


def test_expected_partial_shortfall_is_diagnostic_not_sev2():
    case = replace(
        _case(),
        allow_no_sources=True,
        expected_behavior="insufficient_evidence",
        expected_retrieval_outcome="partial",
    )
    exchange = _exchange(route={
        "entity": "测试实体甲",
        "intent": "skill",
        "requested_intents": ["skill"],
        "retrieval_debug": {"coverage_shortfall": {"skill": 1}},
    })

    result = evaluate_deterministic(
        case,
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert "RETR.BUDGET_SHORTFALL" not in {event.event_code for event in result.events}


def test_retrieval_recall_is_capped_by_the_packet_required_source_count():
    child_id = "fixture:entity-a/skill:1"
    case = replace(
        _case(),
        expected_source_ids=(child_id, "fixture:entity-a/skill:2", "fixture:entity-a/skill:3"),
        source_relevance={
            child_id: 2.0,
            "fixture:entity-a/skill:2": 2.0,
            "fixture:entity-a/skill:3": 2.0,
        },
    )
    exchange = _exchange(route={
        "entity": "测试实体甲",
        "intent": "skill",
        "requested_intents": ["skill"],
        "retrieval_debug": {
            "required_source_count": 1,
            "coverage_shortfall": {"skill": 0},
        },
    })

    result = evaluate_deterministic(
        case,
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert result.metrics["M2"]["recall_at_k"] == 1.0
    assert "RETR.QREL_MISS" not in {event.event_code for event in result.events}


def test_empty_expected_intent_set_is_not_scored_as_intent_failure():
    case = replace(_case(), expected_intents=())

    result = evaluate_deterministic(
        case,
        _exchange(),
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert result.metrics["M2"]["intent_f1"] == 1.0
    assert result.module_scores["M2"] == 100.0


def test_expected_insufficient_evidence_does_not_lose_intent_coverage_score():
    case = replace(
        _case(),
        expected_intents=("video",),
        expected_source_ids=(),
        source_relevance={},
        allow_no_sources=True,
        expected_behavior="insufficient_evidence",
    )
    exchange = replace(
        _exchange(),
        sources=(),
        route={
            "entity": "测试实体甲",
            "intent": "video",
            "requested_intents": ["video"],
            "retrieval_debug": {"coverage_shortfall": {"video": 1}},
        },
    )

    result = evaluate_deterministic(
        case,
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert result.metrics["M2"]["intent_coverage"] == 1.0
    assert result.module_scores["M2"] == 100.0


def test_sync_stream_packet_parity_preserves_source_order_actions_and_memory():
    primary = replace(
        _exchange(
            sources=[
                {"citation_id": "S01", "child_id": "fixture:entity-a/skill:1"},
                {"citation_id": "S02", "child_id": "fixture:entity-b/profile:1"},
            ]
        ),
        source_map={"S01": {"child_id": "fixture:entity-a/skill:1"}, "S02": {"child_id": "fixture:entity-b/profile:1"}},
        omitted_actions=({"action_type": "expand_search"},),
        memory={"status": "hit", "turns_used": 1, "rewrite_mode": "planner"},
    )
    parity = replace(
        primary,
        endpoint="/ask",
        sources=tuple(reversed(primary.sources)),
    )

    result = evaluate_deterministic(
        _case(),
        primary,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
        parity_exchange=parity,
    )

    event = next(
        event
        for event in result.events
        if event.event_code == "RELY.SYNC_STREAM_PACKET_DIVERGENCE"
    )
    assert event.severity is Severity.SEV2
    assert "source_ids" in event.observed


def test_local_path_and_wrong_child_binding_are_sev1():
    media_id = "media:sha1:" + "a" * 40
    exchange = _exchange(
        route={"entity": "测试实体甲", "intent": "voice", "requested_intents": ["voice"]},
        media=[
            {
                "media_id": media_id,
                "asset_type": "voice",
                "child_id": "fixture:entity-b/profile:1",
                "url": "file://private/voice.mp3",
            }
        ],
    )

    result = evaluate_deterministic(
        _case(voice=True),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    codes = {event.event_code: event.severity for event in result.events}
    assert codes["MEDIA.LOCAL_PATH_LEAK"] is Severity.SEV1
    assert codes["MEDIA.WRONG_CHILD_BINDING"] is Severity.SEV1


def test_profile_child_id_is_not_mistaken_for_file_uri():
    from src.rag_eval.deterministic import _contains_local_path

    assert _contains_local_path("char:9999/profile:0000") is False
    assert _contains_local_path("file:///D:/secret/media.png") is True


def test_voice_page_exact_set_passes_media_gate():
    media_id = "media:sha1:" + "a" * 40
    panel = {
        "type": "voice",
        "entity_id": "entity-a",
        "lines": [
            {
                "voice_line_id": "fixture:entity-a/skill:1",
                "title": "测试台词",
                "variants": [
                    {
                        "media_id": media_id,
                        "asset_type": "voice",
                        "child_id": "fixture:entity-a/skill:1",
                        "url": "http://example.test/voice.mp3",
                    }
                ],
            }
        ],
        "page_size": 1,
        "total_lines": 1,
        "has_more": False,
        "next_cursor": None,
    }
    exchange = _exchange(
        route={"entity": "测试实体甲", "intent": "voice", "requested_intents": ["voice"]},
        media=[panel["lines"][0]["variants"][0]],
        panels=[panel],
    )
    exchange = ObservedExchange(**{**exchange.__dict__, "voice_pages": (panel,)})

    result = evaluate_deterministic(
        _case(voice=True),
        exchange,
        _inventory(),
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert not [event for event in result.events if event.module == "M4"]
    assert result.module_scores["M4"] == 100.0


def test_voice_page_gate_ignores_non_voice_media_in_hybrid_expectations():
    inventory = _inventory()
    voice_media_id = "media:sha1:" + "a" * 40
    skill_media_id = "media:sha1:" + "b" * 40
    skill_media = MediaRecord(
        media_id=skill_media_id,
        entity_id="entity-a",
        entity_name="fixture entity a",
        parent_id="fixture:entity-a/skills",
        child_id="fixture:entity-a/skill:1",
        asset_type="skill",
        mime="image/png",
        url="http://example.test/skill.png",
        is_available=True,
        is_common=False,
        language="",
        event_name="skill image",
        sort_order=0,
    )
    inventory = replace(
        inventory,
        media={**inventory.media, skill_media_id: (skill_media,)},
    )
    case = replace(
        _case(voice=True),
        expected_intents=("skill", "voice"),
        expected_media_ids=(skill_media_id, voice_media_id),
    )
    voice_variant = {
        "media_id": voice_media_id,
        "asset_type": "voice",
        "child_id": "fixture:entity-a/skill:1",
        "url": "http://example.test/voice.mp3",
    }
    panel = {
        "type": "voice",
        "entity_id": "entity-a",
        "lines": [
            {
                "voice_line_id": "fixture:entity-a/skill:1",
                "title": "voice line",
                "variants": [voice_variant],
            }
        ],
        "page_size": 1,
        "total_lines": 1,
        "has_more": False,
        "next_cursor": None,
    }
    exchange = _exchange(
        route={
            "entity": "fixture entity a",
            "intent": "skill",
            "requested_intents": ["skill", "voice"],
        },
        media=[
            voice_variant,
            {
                "media_id": skill_media_id,
                "asset_type": "skill",
                "child_id": "fixture:entity-a/skill:1",
                "url": "http://example.test/skill.png",
            },
        ],
        panels=[panel],
    )
    exchange = ObservedExchange(**{**exchange.__dict__, "voice_pages": (panel,)})

    result = evaluate_deterministic(
        case,
        exchange,
        inventory,
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert not [event for event in result.events if event.event_code == "MEDIA.VOICE_PAGE_SET_MISMATCH"]


def test_nonvoice_media_scores_available_allowed_subset_instead_of_full_inventory_recall():
    inventory = _inventory()
    media_id = "media:sha1:" + "b" * 40
    missing_media_id = "media:sha1:" + "c" * 40
    media = MediaRecord(
        media_id=media_id,
        entity_id="entity-a",
        entity_name="测试实体甲",
        parent_id="fixture:entity-a/skills",
        child_id="fixture:entity-a/skill:1",
        asset_type="skill",
        mime="image/png",
        url="http://example.test/skill.png",
        is_available=True,
        is_common=False,
        language="",
        event_name="skill image",
        sort_order=0,
    )
    inventory = replace(inventory, media={**inventory.media, media_id: (media,)})
    case = replace(
        _case(),
        scenario="media",
        expected_intents=("media",),
        expected_media_ids=(media_id, missing_media_id),
        forbidden_media_types=("voice",),
    )
    exchange = _exchange(
        media=[{
            "media_id": media_id,
            "asset_type": "skill",
            "child_id": "fixture:entity-a/skill:1",
            "entity_type": "character",
            "entity_id": "entity-a",
        }],
        route={"entity": "测试实体甲", "requested_intents": ["media"]},
    )

    result = evaluate_deterministic(
        case,
        exchange,
        inventory,
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert result.metrics["M4"]["media_recall"] == 1.0
    assert result.metrics["M4"]["media_precision"] == 1.0
    assert result.module_scores["M4"] == 100.0


def test_nonvoice_media_rejects_types_not_allowed_by_requested_intents():
    inventory = _inventory()
    media_id = "media:sha1:" + "b" * 40
    media = MediaRecord(
        media_id=media_id,
        entity_id="entity-a",
        entity_name="测试实体甲",
        parent_id="fixture:entity-a/skills",
        child_id="fixture:entity-a/skill:1",
        asset_type="skill",
        mime="image/png",
        url="http://example.test/skill.png",
        is_available=True,
        is_common=False,
        language="",
        event_name="skill image",
        sort_order=0,
    )
    inventory = replace(inventory, media={**inventory.media, media_id: (media,)})
    case = replace(
        _case(),
        scenario="media",
        expected_intents=("video",),
        expected_media_ids=(),
    )
    exchange = _exchange(
        media=[{
            "media_id": media_id,
            "asset_type": "skill",
            "child_id": "fixture:entity-a/skill:1",
            "entity_type": "character",
            "entity_id": "entity-a",
        }],
        route={"entity": "测试实体甲", "requested_intents": ["video"]},
    )

    result = evaluate_deterministic(
        case,
        exchange,
        inventory,
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert "MEDIA.UNEXPECTED_TYPE" in {event.event_code for event in result.events}


def test_partial_text_answer_allows_owned_image_attachment_from_supported_intent():
    inventory = _inventory()
    media_id = "media:sha1:" + "b" * 40
    media = MediaRecord(
        media_id=media_id,
        entity_id="entity-a",
        entity_name="测试实体甲",
        parent_id="fixture:entity-a/skills",
        child_id="fixture:entity-a/skill:1",
        asset_type="image",
        mime="image/png",
        url="http://example.test/portrait.png",
        is_available=True,
        is_common=False,
        language="",
        event_name="portrait",
        sort_order=0,
    )
    inventory = replace(inventory, media={**inventory.media, media_id: (media,)})
    case = replace(
        _case(),
        scenario="boundary",
        expected_intents=("intro", "video"),
        expected_media_ids=(),
        expected_behavior="partial_answer",
        expected_retrieval_outcome="partial",
    )
    exchange = _exchange(
        media=[{
            "media_id": media_id,
            "asset_type": "image",
            "child_id": "fixture:entity-a/skill:1",
            "entity_type": "character",
            "entity_id": "entity-a",
        }],
        route={"entity": "测试实体甲", "requested_intents": ["intro", "video"]},
    )

    result = evaluate_deterministic(
        case,
        exchange,
        inventory,
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert "MEDIA.UNEXPECTED_ATTACHMENT" not in {
        event.event_code for event in result.events
    }
    assert result.module_scores["M4"] == 100.0


def test_supported_refusal_evidence_does_not_make_owned_attachment_unexpected():
    inventory = _inventory()
    media_id = "media:sha1:" + "b" * 40
    media = MediaRecord(
        media_id=media_id,
        entity_id="entity-a",
        entity_name="测试实体甲",
        parent_id="fixture:entity-a/skills",
        child_id="fixture:entity-a/skill:1",
        asset_type="image",
        mime="image/png",
        url="http://example.test/image.png",
        is_available=True,
        is_common=False,
        language="",
        event_name="image",
        sort_order=0,
    )
    inventory = replace(inventory, media={**inventory.media, media_id: (media,)})
    case = replace(
        _case(),
        scenario="boundary",
        expected_intents=(),
        expected_source_ids=(),
        source_relevance={},
        expected_behavior="insufficient_evidence",
        allow_no_sources=True,
    )
    exchange = _exchange(media=[{
        "media_id": media_id,
        "asset_type": "image",
        "child_id": "fixture:entity-a/skill:1",
        "entity_type": "character",
        "entity_id": "entity-a",
    }])

    result = evaluate_deterministic(
        case,
        exchange,
        inventory,
        load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json")),
    )

    assert "MEDIA.UNEXPECTED_ATTACHMENT" not in {
        event.event_code for event in result.events
    }


def test_reliability_reports_success_rate_and_p95_failure():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    exchanges = [_exchange() for _ in range(49)]
    exchanges.append(_exchange(success=False, error="failed"))
    for index in range(3):
        exchanges[index] = ObservedExchange(
            **{
                **exchanges[index].__dict__,
                "timing": TimingObservation("now", 6000.0, 16000.0, 46000.0),
            }
        )

    result = evaluate_reliability(exchanges, thresholds)

    assert result.metrics["success_rate"] == 0.98
    assert any(event.event_code == "RELY.P95_LATENCY_EXCEEDED" for event in result.events)


def test_reliability_reports_repeat_route_or_evidence_divergence():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    original = _exchange()
    repeated = _exchange(
        sources=[
            {
                "name": "测试实体乙",
                "child_id": "fixture:entity-b/profile:1",
                "parent_id": "fixture:entity-b/profile",
            }
        ]
    )

    result = evaluate_reliability(
        [original, repeated],
        thresholds,
        repeat_pairs=[(original, repeated)],
    )

    assert any(event.event_code == "RELY.REPEAT_DIVERGENCE" for event in result.events)
