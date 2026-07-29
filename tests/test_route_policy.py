from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.rag.query_plan import QueryPlan
from src.rag.request_plan import PlannedSubtask
from src.rag.retriever import RetrievalExecutionError, Retriever
from src.rag.route_policy import (
    authorize_subtask,
    authorize_route,
    classify_retrieval_outcome,
    finalize_subtask_route,
    finalize_route,
)


def _plan(intent: str = "meta_question", route: str = "llm_general") -> QueryPlan:
    return QueryPlan(
        original_query="fixture question",
        normalized_query="fixture question",
        entity=None,
        aliases=(),
        intent=intent,
        section_hints=(),
        scatter_terms=(),
        confidence=0.8,
        route=route,
    )


def _authorization(*, toggle=False, force=False, proposed="llm_general"):
    action = {"action_type": "force_free_supplement"} if force else None
    return authorize_route(
        _plan(route=proposed),
        {"free_supplement": toggle},
        action,
    )


@pytest.mark.parametrize(
    ("toggle", "force", "outcome", "expected_route"),
    [
        (False, False, "sufficient", "rag_grounded"),
        (False, False, "partial", "rag_grounded"),
        (False, False, "empty", "rag_grounded"),
        (False, False, "failed", "rag_grounded"),
        (True, False, "sufficient", "rag_grounded"),
        (True, False, "partial", "rag_grounded"),
        (True, False, "empty", "llm_general"),
        (True, False, "failed", "rag_grounded"),
        (False, True, "empty", "llm_general"),
    ],
)
def test_route_matrix(toggle, force, outcome, expected_route):
    auth = _authorization(toggle=toggle, force=force)

    assert finalize_route(auth, outcome).effective_route == expected_route


def test_meta_question_intent_survives_planner_llm_general_proposal():
    auth = authorize_route(_plan(intent="meta_question", route="llm_general"), {}, None)
    decision = finalize_route(auth, "empty")

    assert auth.semantic_intents == ("meta_question",)
    assert decision.effective_route == "rag_grounded"
    assert decision.route_reason == "grounded_empty"


def test_expanded_route_remains_grounded_and_does_not_become_general():
    auth = authorize_route(
        _plan(intent="skill", route="rag_grounded"),
        {"expanded": True, "free_supplement": False},
        None,
    )
    decision = finalize_route(auth, "sufficient")

    assert decision.effective_route == "expanded_rag"
    assert auth.semantic_intents == ("skill",)


def test_legacy_hybrid_answer_is_normalized_to_grounded_route():
    auth = authorize_route(_plan(intent="skill", route="hybrid_answer"), {}, None)

    assert auth.proposed_route == "rag_grounded"


def test_legacy_action_route_values_are_normalized_without_becoming_intents():
    auth = authorize_route(
        _plan(intent="skill", route="rag_grounded"),
        {},
        {"intent": "llm_general", "packet_policy": "free_supplement"},
    )

    assert auth.force_free_supplement is True
    assert auth.semantic_intents == ("skill",)


def test_failed_dependency_never_becomes_empty_fallback():
    decision = finalize_route(_authorization(toggle=True), "failed")

    assert decision.effective_route == "rag_grounded"
    assert decision.route_reason == "retrieval_failed"


@pytest.mark.parametrize(
    ("sources", "shortfall", "failed", "expected"),
    [
        ([], {}, False, "empty"),
        ([object()], {"skill": 0}, False, "sufficient"),
        ([object()], {"skill": 1}, False, "partial"),
        ([], {}, True, "failed"),
    ],
)
def test_retrieval_outcome_classification(sources, shortfall, failed, expected):
    assert classify_retrieval_outcome(sources, shortfall, failed=failed) == expected


class _FailedVectorstore:
    def similarity_search_with_relevance_scores(self, *args, **kwargs):
        raise TimeoutError("primary failed")

    def similarity_search(self, *args, **kwargs):
        raise ConnectionError("fallback failed")


def test_dense_dependency_failure_is_not_reported_as_empty():
    retriever = Retriever.__new__(Retriever)
    retriever.vectorstore = _FailedVectorstore()

    with pytest.raises(RetrievalExecutionError, match="retrieval.dense") as error:
        retriever._dense_rows_for_plan("q", _plan(intent="skill"), 20)

    assert error.value.stage == "retrieval.dense"
    assert error.value.error_class == "ConnectionError"
    assert "fallback failed" not in str(error.value)


@pytest.mark.parametrize(
    ("expanded", "free", "outcome", "route", "reason"),
    [
        (False, False, "sufficient", "rag_grounded", "grounded_sufficient"),
        (False, False, "partial", "rag_grounded", "grounded_partial"),
        (False, False, "empty", "rag_grounded", "grounded_empty"),
        (False, False, "failed", "rag_grounded", "retrieval_failed"),
        (True, False, "sufficient", "expanded_rag", "grounded_sufficient"),
        (True, False, "partial", "expanded_rag", "grounded_partial"),
        (True, False, "empty", "expanded_rag", "grounded_empty"),
        (True, False, "failed", "rag_grounded", "retrieval_failed"),
        (False, True, "sufficient", "rag_grounded", "grounded_sufficient"),
        (False, True, "partial", "rag_grounded", "grounded_partial"),
        (False, True, "empty", "llm_general", "authorized_empty_fallback"),
        (False, True, "failed", "rag_grounded", "retrieval_failed"),
        (True, True, "sufficient", "expanded_rag", "grounded_sufficient"),
        (True, True, "partial", "expanded_rag", "grounded_partial"),
        (True, True, "empty", "llm_general", "authorized_empty_fallback"),
        (True, True, "failed", "rag_grounded", "retrieval_failed"),
    ],
)
def test_dual_toggle_matrix(expanded, free, outcome, route, reason):
    knowledge_task = PlannedSubtask(
        subtask_id="T01",
        order=1,
        task_type="knowledge_base",
        query="fixture question",
        query_plan=_plan(intent="skill", route="rag_grounded"),
    )

    authorization = authorize_subtask(
        knowledge_task,
        {"expanded": expanded, "free_supplement": free},
        None,
    )
    decision = finalize_subtask_route(authorization, outcome)

    assert decision.effective_route == route
    assert decision.route_reason == reason


@pytest.mark.parametrize(
    ("task_type", "reason"),
    [
        ("assistant_meta", "local_assistant_meta"),
        ("social_smalltalk", "local_social_smalltalk"),
        ("out_of_scope", "local_out_of_scope"),
    ],
)
def test_local_subtasks_are_authorized_without_retrieval(task_type, reason):
    task = PlannedSubtask("T01", 1, task_type, "fixture", None)

    decision = finalize_subtask_route(authorize_subtask(task, {}, None), "not_applicable")

    assert decision.effective_route == "local_response"
    assert decision.retrieval_outcome == "not_applicable"
    assert decision.route_reason == reason


def test_general_open_is_denied_by_default_even_if_planner_proposes_it():
    task = PlannedSubtask("T01", 1, "general_open", "中国首都是什么", None)

    decision = finalize_subtask_route(authorize_subtask(task, {}, None), "not_applicable")

    assert decision.effective_route == "local_response"
    assert decision.route_reason == "general_open_denied"


@pytest.mark.parametrize(
    ("options", "action", "reason"),
    [
        ({"free_supplement": True}, None, "toggle_allows_empty_fallback"),
        ({}, {"action_type": "force_free_supplement", "subtask_id": "T01"}, "explicit_recovery_action"),
    ],
)
def test_general_open_requires_explicit_authorization(options, action, reason):
    task = PlannedSubtask("T01", 1, "general_open", "中国首都是什么", None)

    decision = finalize_subtask_route(
        authorize_subtask(task, options, action),
        "not_applicable",
    )

    assert decision.effective_route == "llm_general"
    assert decision.route_reason == reason


def test_recovery_action_authorization_does_not_cross_subtask_id():
    task = PlannedSubtask("T02", 2, "general_open", "中国首都是什么", None)

    decision = finalize_subtask_route(
        authorize_subtask(
            task,
            {},
            {"action_type": "force_free_supplement", "subtask_id": "T01"},
        ),
        "not_applicable",
    )

    assert decision.effective_route == "local_response"
    assert decision.route_reason == "general_open_denied"
