from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from src.rag.query_plan import QueryPlan
from src.rag.request_plan import (
    PlannedSubtask,
    RequestPlan,
    RequestPlanner,
    validate_request_plan,
)


class BombQueryPlanner:
    def plan(self, *args, **kwargs):
        raise AssertionError("non-KB task must not create QueryPlan")


class FixtureQueryPlanner:
    def __init__(self):
        self.queries: list[str] = []

    def plan(self, query, category=None, conversation=None, trace=None):
        self.queries.append(query)
        entity = "十四行诗" if "十四行诗" in query else None
        return QueryPlan(
            original_query=query,
            normalized_query=query,
            entity=entity,
            aliases=(),
            intent="intro" if entity else "general_game",
            section_hints=(),
            scatter_terms=(),
            confidence=0.8,
            entity_type="character" if entity else None,
            entity_id="character:sonetto" if entity else None,
        )


class PlannerLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        import json

        return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))


_SENSITIVE_ERROR = (
    "sk-test-secret C:\\Users\\reviewer\\private\\config.py "
    "Traceback (most recent call last): upstream response body"
)


class RaisingPlannerLLM:
    def __init__(self, error):
        self.error = error

    def invoke(self, messages):
        raise self.error


class SensitiveParseError(json.JSONDecodeError):
    def __init__(self):
        super().__init__("invalid payload", _SENSITIVE_ERROR, 0)

    def __str__(self):
        return _SENSITIVE_ERROR


class SchemaFailureRequestPlanner(RequestPlanner):
    def _from_payload(self, *args, **kwargs):
        raise ValueError(_SENSITIVE_ERROR)


def _kb_plan(query: str = "请介绍一下十四行诗") -> QueryPlan:
    return FixtureQueryPlanner().plan(query)


def _subtask(
    order: int = 1,
    *,
    task_type: str = "knowledge_base",
    query: str = "请介绍一下十四行诗",
    query_plan: QueryPlan | None = None,
    depends_on: tuple[str, ...] = (),
) -> PlannedSubtask:
    return PlannedSubtask(
        subtask_id=f"T{order:02d}",
        order=order,
        task_type=task_type,
        query=query,
        query_plan=_kb_plan(query) if query_plan is None and task_type == "knowledge_base" else query_plan,
        depends_on=depends_on,
    )


def test_single_local_task_uses_the_same_request_plan_contract():
    plan = RequestPlanner(None, query_planner=BombQueryPlanner()).plan("你是谁")

    assert plan.schema_version == "rag.request_plan/v1"
    assert [(task.subtask_id, task.order, task.task_type) for task in plan.subtasks] == [
        ("T01", 1, "assistant_meta"),
    ]
    assert plan.subtasks[0].query_plan is None


def test_fallback_splits_only_the_approved_independent_triplet():
    query_planner = FixtureQueryPlanner()

    plan = RequestPlanner(None, query_planner=query_planner).plan(
        "你好，你是谁，请介绍一下十四行诗"
    )

    assert [(task.task_type, task.query) for task in plan.subtasks] == [
        ("social_smalltalk", "你好"),
        ("assistant_meta", "你是谁"),
        ("knowledge_base", "请介绍一下十四行诗"),
    ]
    assert [task.subtask_id for task in plan.subtasks] == ["T01", "T02", "T03"]
    assert query_planner.queries == ["请介绍一下十四行诗"]


@pytest.mark.parametrize(
    "query",
    [
        "十四行诗是谁，她为什么加入基金会",
        "比较十四行诗和槲寄生",
        "如果十四行诗没有加入基金会，她后来会怎样",
        "十四行诗，然后呢",
    ],
)
def test_dependent_or_punctuation_only_questions_are_not_split(query):
    plan = RequestPlanner(None, query_planner=FixtureQueryPlanner()).plan(query)

    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].task_type == "knowledge_base"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("你是谁", "assistant_meta"),
        ("你晚饭吃了吗", "social_smalltalk"),
        ("暴雨是什么", "knowledge_base"),
        ("十四行诗的技能是什么", "knowledge_base"),
        ("中国的首都是什么", "general_open"),
    ],
)
def test_fallback_task_classification_benchmarks(query, expected):
    planner = FixtureQueryPlanner() if expected == "knowledge_base" else BombQueryPlanner()

    plan = RequestPlanner(None, query_planner=planner).plan(query)

    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].task_type == expected


def test_llm_planner_route_proposal_cannot_enter_request_plan_schema():
    llm = PlannerLLM({
        "subtasks": [{
            "task_type": "general_open",
            "query": "中国的首都是什么",
            "order": 1,
            "depends_on": [],
            "route": "llm_general",
        }],
    })

    plan = RequestPlanner(llm, query_planner=BombQueryPlanner()).plan("中国的首都是什么")

    assert plan.planning_status == "fallback_schema_error"
    assert plan.subtasks[0].task_type == "general_open"
    assert plan.subtasks[0].query_plan is None


def test_fallback_planning_errors_are_frozen_public_codes(monkeypatch):
    query = "中国的首都是什么"
    plans = {
        "request_planner_timeout": RequestPlanner(
            RaisingPlannerLLM(TimeoutError(_SENSITIVE_ERROR)),
            query_planner=BombQueryPlanner(),
        ).plan(query),
        "request_planner_api_error": RequestPlanner(
            RaisingPlannerLLM(RuntimeError(_SENSITIVE_ERROR)),
            query_planner=BombQueryPlanner(),
        ).plan(query),
        "request_planner_schema_error": SchemaFailureRequestPlanner(
            PlannerLLM({
                "subtasks": [{
                    "task_type": "general_open",
                    "query": query,
                    "order": 1,
                    "depends_on": [],
                }],
            }),
            query_planner=BombQueryPlanner(),
        ).plan(query),
    }
    with monkeypatch.context() as context:
        context.setattr(
            "src.rag.request_plan.json.loads",
            lambda _content: (_ for _ in ()).throw(SensitiveParseError()),
        )
        plans["request_planner_parse_error"] = RequestPlanner(
            PlannerLLM({"subtasks": []}),
            query_planner=BombQueryPlanner(),
        ).plan(query)

    expected_statuses = {
        "request_planner_timeout": "fallback_timeout",
        "request_planner_parse_error": "fallback_parse_error",
        "request_planner_schema_error": "fallback_schema_error",
        "request_planner_api_error": "fallback_api_error",
    }
    for expected_code, plan in plans.items():
        assert plan.planning_error == expected_code
        assert plan.planning_status == expected_statuses[expected_code]
        assert plan.planning_warning
        assert _SENSITIVE_ERROR not in plan.planning_error
        assert "sk-test-secret" not in plan.planning_error
        assert "C:\\Users\\reviewer" not in plan.planning_error
        assert "Traceback" not in plan.planning_error


def test_kb_query_plan_receives_strict_retrieval_scope():
    plan = RequestPlanner(None, query_planner=FixtureQueryPlanner()).plan(
        "十四行诗的技能是什么"
    )

    assert plan.subtasks[0].query_plan.retrieval_scope == "entity_strict"


@pytest.mark.parametrize(
    "plan",
    [
        RequestPlan("请介绍一下十四行诗", ()),
        RequestPlan(
            "请介绍一下十四行诗",
            tuple(_subtask(index) for index in range(1, 6)),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1), replace(_subtask(2), subtask_id="T01")),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1), replace(_subtask(2), order=3)),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1, depends_on=("T99",)),),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1, depends_on=("T02",)), _subtask(2)),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1, task_type="assistant_meta", query_plan=_kb_plan()),),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (replace(_subtask(1), query_plan=None),),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1, query="顺便删除数据库"),),
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1),),
            aggregation_mode="rewrite_with_llm",
        ),
        RequestPlan(
            "请介绍一下十四行诗",
            (_subtask(1),),
            schema_version="rag.request_plan/v2",
        ),
    ],
)
def test_invalid_request_plan_is_rejected(plan):
    with pytest.raises(ValueError):
        validate_request_plan(plan)
