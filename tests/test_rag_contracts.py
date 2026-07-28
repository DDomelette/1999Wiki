from __future__ import annotations

import dataclasses

import pytest

from src.rag.chain import RAGChain
from src.rag.contracts import (
    CitationValidation,
    EntityRef,
    FrozenRetrievalPacket,
    ResponsePacket,
    RouteAuthorization,
    RouteDecision,
    SourceRef,
    freeze_value,
)
from src.rag.query_plan import QueryPlanner
from src.rag.request_plan import RequestPlanner


def _response_packet_fixture() -> ResponsePacket:
    authorization = RouteAuthorization(
        semantic_intents=("meta_question",),
        proposed_route="llm_general",
        allow_free_supplement_after_empty=False,
        force_free_supplement=False,
        authorization_reason="default_closed",
    )
    decision = RouteDecision(
        authorization=authorization,
        retrieval_outcome="empty",
        effective_route="rag_grounded",
        route_reason="free_supplement_not_authorized",
    )
    retrieval = FrozenRetrievalPacket(
        plan={"intent": "meta_question"},
        entity_ref=None,
        route_decision=decision,
        requested_intents=("meta_question",),
        sources=({"child_id": "child-1", "metadata": {"rank": 1}},),
        source_map=(
            SourceRef(
                citation_id="S01",
                entity_type="system",
                entity_id="help",
                child_id="child-1",
                parent_id="parent-1",
                display_name="Help",
                heading_path="Usage",
            ),
        ),
        media=(),
        media_panels=(),
        context="context",
        diagnostics={"candidate_k": 20, "nested": {"counts": [1, 2]}},
        omitted_actions=(),
        failure_actions=(),
        planning_status="llm",
        planning_warning="",
        planning_error="",
    )
    return ResponsePacket(
        retrieval_packet=retrieval,
        answer="No grounded answer was found.",
        grounding_mode="none",
        citation_validation=CitationValidation(valid=True),
        memory_info={"history_used": False, "turns": []},
        turn_outcome="not_committable",
    )


def test_entity_ref_uses_type_and_id_as_ownership_key():
    ref = EntityRef("fixture_type", "fixture-1", "Example", ("Alias",), "current_exact")

    assert ref.ownership_key == ("fixture_type", "fixture-1")


def test_response_packet_deep_freezes_nested_public_values():
    packet = _response_packet_fixture()

    with pytest.raises(TypeError):
        packet.retrieval_packet.diagnostics["candidate_k"] = 99
    with pytest.raises(TypeError):
        packet.retrieval_packet.diagnostics["nested"]["counts"][0] = 99
    with pytest.raises(TypeError):
        packet.retrieval_packet.sources[0]["metadata"]["rank"] = 99
    with pytest.raises(dataclasses.FrozenInstanceError):
        packet.answer = "changed"


def test_route_and_intent_are_separate_contracts():
    authorization = RouteAuthorization(
        semantic_intents=("meta_question",),
        proposed_route="llm_general",
        allow_free_supplement_after_empty=False,
        force_free_supplement=False,
        authorization_reason="default_closed",
    )

    assert authorization.semantic_intents == ("meta_question",)
    assert authorization.proposed_route == "llm_general"


def test_freeze_value_sorts_sets_and_rejects_later_mutation():
    frozen = freeze_value({"tags": {"beta", "alpha"}, "items": [{"value": 1}]})

    assert frozen["tags"] == ("alpha", "beta")
    with pytest.raises(TypeError):
        frozen["items"][0]["value"] = 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retrieval_outcome", "unknown"),
        ("effective_route", "hybrid_answer"),
    ],
)
def test_route_decision_rejects_values_outside_the_public_contract(field: str, value: str):
    authorization = RouteAuthorization(
        semantic_intents=("general",),
        proposed_route="rag_grounded",
        allow_free_supplement_after_empty=False,
        force_free_supplement=False,
        authorization_reason="default_closed",
    )
    kwargs = {
        "authorization": authorization,
        "retrieval_outcome": "sufficient",
        "effective_route": "rag_grounded",
        "route_reason": "grounded_sources_available",
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        RouteDecision(**kwargs)


def test_local_route_uses_not_applicable_instead_of_empty():
    authorization = RouteAuthorization(
        semantic_intents=("assistant_meta",),
        proposed_route="local_response",
        allow_free_supplement_after_empty=False,
        force_free_supplement=False,
        authorization_reason="local_assistant_meta",
    )

    decision = RouteDecision(
        authorization=authorization,
        retrieval_outcome="not_applicable",
        effective_route="local_response",
        route_reason="local_assistant_meta",
    )

    assert decision.retrieval_outcome == "not_applicable"
    assert decision.effective_route == "local_response"


def test_public_planning_meta_does_not_propagate_raw_planner_exception():
    sensitive = (
        "sk-public-secret C:\\Users\\reviewer\\private\\planner.py "
        "Traceback (most recent call last): upstream body"
    )

    class RaisingLLM:
        def invoke(self, messages):
            raise RuntimeError(sensitive)

    plan = RequestPlanner(
        RaisingLLM(),
        query_planner=QueryPlanner(None),
    ).plan("中国的首都是什么")
    chain = RAGChain.__new__(RAGChain)

    public_meta = chain._planning_meta(plan)

    assert public_meta["planning_error"] == "request_planner_api_error"
    assert sensitive not in repr(public_meta)
    assert "sk-public-secret" not in repr(public_meta)
    assert "C:\\Users\\reviewer" not in repr(public_meta)
    assert "Traceback" not in repr(public_meta)
