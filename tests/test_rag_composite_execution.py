from __future__ import annotations

import threading
import time

from src.rag.contracts import (
    BranchResult,
    CitationValidation,
    RouteAuthorization,
    RouteDecision,
)
from src.rag.execution import (
    AskExecutionInput,
    RAGExecutionService,
    execute_request_plan,
)
from src.rag.query_plan import QueryPlan
from src.rag.request_plan import PlannedSubtask, RequestPlan


def _task(subtask_id: str, order: int, task_type: str, depends_on=()):
    return PlannedSubtask(
        subtask_id=subtask_id,
        order=order,
        task_type=task_type,
        query=f"query-{subtask_id}",
        query_plan=object() if task_type == "knowledge_base" else None,
        depends_on=tuple(depends_on),
    )


def _branch(subtask, *, status="succeeded", answer=None, source_ids=()):
    grounded = subtask.task_type == "knowledge_base" and status == "succeeded"
    return BranchResult(
        subtask_id=subtask.subtask_id,
        order=subtask.order,
        task_type=subtask.task_type,
        query=subtask.query,
        effective_route="rag_grounded" if grounded else "local_response",
        retrieval_outcome="sufficient" if grounded else "not_applicable",
        grounding_mode="grounded" if grounded else "none",
        status=status,
        answer=answer or f"answer-{subtask.subtask_id}",
        source_ids=tuple(source_ids),
        entity_ref=None,
        citation_validation=CitationValidation(valid=True),
        public_error="" if status == "succeeded" else "branch_execution_failed",
    )


def _source(subtask_id):
    return {
        "entity_type": "topic",
        "entity_id": f"topic:{subtask_id}",
        "child_id": f"child:{subtask_id}",
        "parent_id": f"parent:{subtask_id}",
        "name": subtask_id,
        "content": subtask_id,
        "source_refs": [{
            "site": "huiji",
            "title": subtask_id,
            "revid": "1",
            "content_sha256": subtask_id[-1] * 64,
        }],
    }


def test_retrieval_finishes_before_any_answer_and_only_kb_retrieves():
    plan = RequestPlan(
        original_query="composite",
        subtasks=(
            _task("T01", 1, "social_smalltalk"),
            _task("T02", 2, "assistant_meta"),
            _task("T03", 3, "knowledge_base"),
        ),
    )
    events = []

    def retrieve(subtask):
        events.append(("retrieve", subtask.subtask_id))
        return {"sources": [_source(subtask.subtask_id)]}

    def answer(subtask, retrieved, source_ids, source_map):
        events.append(("answer", subtask.subtask_id))
        if subtask.task_type == "knowledge_base":
            assert source_ids == ("S01",)
            assert tuple(ref.citation_id for ref in source_map) == ("S01",)
            return _branch(subtask, answer="KB [S01]", source_ids=source_ids)
        assert retrieved == {}
        assert source_ids == ()
        assert source_map == ()
        return _branch(
            subtask,
            answer="local [S99]" if subtask.subtask_id == "T01" else None,
        )

    result = execute_request_plan(plan, retrieve, answer)

    assert events[0] == ("retrieve", "T03")
    assert [branch.subtask_id for branch in result.branches] == ["T01", "T02", "T03"]
    assert "[S99]" not in result.branches[0].answer
    assert result.branches[0].source_ids == ()
    first_answer = next(index for index, event in enumerate(events) if event[0] == "answer")
    assert all(event[0] == "retrieve" for event in events[:first_answer])


def test_executor_never_exceeds_four_active_branches_and_preserves_order():
    plan = RequestPlan(
        original_query="four",
        subtasks=tuple(_task(f"T0{index}", index, "knowledge_base") for index in range(1, 5)),
    )
    lock = threading.Lock()
    active = 0
    maximum = 0

    def retrieve(subtask):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return {"sources": [_source(subtask.subtask_id)]}

    def answer(subtask, retrieved, source_ids, source_map):
        del retrieved, source_map
        return _branch(subtask, answer=f"{subtask.subtask_id} [{source_ids[0]}]", source_ids=source_ids)

    result = execute_request_plan(plan, retrieve, answer, max_workers=4)

    assert maximum <= 4
    assert [branch.subtask_id for branch in result.branches] == ["T01", "T02", "T03", "T04"]


def test_branch_failure_isolated_and_dependencies_use_topological_batches():
    plan = RequestPlan(
        original_query="dependencies",
        subtasks=(
            _task("T01", 1, "assistant_meta"),
            _task("T02", 2, "knowledge_base", ("T01",)),
            _task("T03", 3, "knowledge_base", ("T02",)),
        ),
    )
    answered = []

    def retrieve(subtask):
        return {"sources": [_source(subtask.subtask_id)]}

    def answer(subtask, retrieved, source_ids, source_map):
        del retrieved, source_map
        answered.append(subtask.subtask_id)
        if subtask.subtask_id == "T01":
            raise RuntimeError("Traceback C:\\secret\\prompt api_key=secret")
        return _branch(
            subtask,
            answer=f"{subtask.subtask_id} [{source_ids[0]}]",
            source_ids=source_ids,
        )

    result = execute_request_plan(plan, retrieve, answer)

    assert answered == ["T01", "T02", "T03"]
    assert result.branches[0].status == "failed"
    assert result.branches[0].public_error == "branch_execution_failed"
    assert "Traceback" not in result.branches[0].answer
    assert result.branches[2].status == "succeeded"


def test_source_collision_fails_only_the_offending_branch():
    plan = RequestPlan(
        original_query="collision",
        subtasks=(
            _task("T01", 1, "knowledge_base"),
            _task("T02", 2, "knowledge_base"),
            _task("T03", 3, "assistant_meta"),
        ),
    )

    def retrieve(subtask):
        source = _source("T01")
        if subtask.subtask_id == "T02":
            source["content"] = "conflicting content"
            source["source_refs"][0]["content_sha256"] = "b" * 64
        return {"sources": [source]}

    def answer(subtask, retrieved, source_ids, source_map):
        del retrieved, source_map
        if subtask.task_type == "knowledge_base":
            return _branch(
                subtask,
                answer=f"{subtask.subtask_id} [{source_ids[0]}]",
                source_ids=source_ids,
            )
        return _branch(subtask)

    result = execute_request_plan(plan, retrieve, answer)

    assert result.branches[0].status == "succeeded"
    assert result.branches[1].status == "failed"
    assert result.branches[1].public_error == "branch_retrieval_failed"
    assert result.branches[2].status == "succeeded"


class CompletionOrderedCompositeChain:
    def __init__(self, request_plan):
        self.request_plan = request_plan
        self.completion_order = []

    def retrieve(self, question, _subtask=None, **kwargs):
        del question, kwargs
        if _subtask is None:
            return {"request_plan": self.request_plan, "composite_pending": True}
        if _subtask.subtask_id == "T01":
            time.sleep(0.03)
        self.completion_order.append(_subtask.subtask_id)
        intent = _subtask.query_plan.intent
        authorization = RouteAuthorization(
            semantic_intents=(intent,),
            proposed_route="rag_grounded",
            allow_free_supplement_after_empty=False,
            force_free_supplement=False,
            authorization_reason="default_closed",
        )
        decision = RouteDecision(
            authorization=authorization,
            retrieval_outcome="empty",
            effective_route="rag_grounded",
            route_reason="grounded_empty",
        )
        return {
            "plan": _subtask.query_plan,
            "request_plan": self.request_plan,
            "subtask": _subtask,
            "sources": [],
            "source_map": (),
            "context": "",
            "assets": [{"asset_id": f"asset-{_subtask.subtask_id}"}],
            "media": [{"media_id": f"media-{_subtask.subtask_id}"}],
            "media_panels": [],
            "omitted_actions": [{
                "label": f"action-{_subtask.subtask_id}",
                "query": _subtask.query,
                "action_type": "expand_search",
            }],
            "failure_actions": [],
            "route": {"name": "rag_grounded"},
            "free_supplement": False,
            "local_response": False,
            "retrieval_failed": False,
            "route_decision": decision,
            "planning_status": "llm",
            "planning_warning": "",
            "planning_error": "",
        }

    def llm_ready(self):
        return False


def _ordered_kb_task(subtask_id, order, intent):
    plan = QueryPlan(
        original_query=f"query-{subtask_id}",
        normalized_query=f"query-{subtask_id}",
        entity=f"entity-{subtask_id}",
        aliases=(),
        intent=intent,
        section_hints=(),
        scatter_terms=(),
        confidence=1.0,
        entity_type="topic",
        entity_id=f"topic:{subtask_id}",
    )
    return PlannedSubtask(
        subtask_id=subtask_id,
        order=order,
        task_type="knowledge_base",
        query=plan.original_query,
        query_plan=plan,
    )


def test_composite_aggregate_fields_ignore_worker_completion_order():
    request_plan = RequestPlan(
        original_query="ordered",
        subtasks=(
            _ordered_kb_task("T01", 1, "story"),
            _ordered_kb_task("T02", 2, "general_game"),
        ),
    )
    observations = []
    for _ in range(3):
        chain = CompletionOrderedCompositeChain(request_plan)
        packet = RAGExecutionService(chain).execute(
            AskExecutionInput(
                question="ordered",
                category=None,
                route_options={},
                action_payload=None,
            )
        )
        observations.append((
            chain.completion_order,
            packet.retrieval_packet.requested_intents,
            tuple(item["asset_id"] for item in packet.retrieval_packet.assets),
            tuple(item["label"] for item in packet.retrieval_packet.omitted_actions),
            packet.retrieval_packet.route_decision.authorization.semantic_intents,
        ))

    assert all(order == ["T02", "T01"] for order, *_ in observations)
    assert all(item[1:] == (
        ("story", "general_game"),
        ("asset-T01", "asset-T02"),
        ("action-T01", "action-T02"),
        ("story",),
    ) for item in observations)
