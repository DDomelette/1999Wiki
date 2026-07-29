"""Top-level request classification without route authorization."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from .conversation import EMPTY_PROJECTION, ConversationProjection
from .query_plan import QueryPlan, QueryPlanner
from .tracing import NullTrace, RequestTrace


TaskType = Literal[
    "assistant_meta",
    "social_smalltalk",
    "knowledge_base",
    "general_open",
    "out_of_scope",
]
RetrievalScope = Literal["none", "entity_strict", "topic_strict", "corpus_topic"]
AggregationMode = Literal["ordered_sections"]

PLANNING_ERROR_TIMEOUT = "request_planner_timeout"
PLANNING_ERROR_PARSE = "request_planner_parse_error"
PLANNING_ERROR_SCHEMA = "request_planner_schema_error"
PLANNING_ERROR_API = "request_planner_api_error"

_TASK_TYPES = frozenset({
    "assistant_meta",
    "social_smalltalk",
    "knowledge_base",
    "general_open",
    "out_of_scope",
})
_ASSISTANT_META_MARKERS = (
    "你是谁",
    "你能做什么",
    "能做什么",
    "怎么使用",
    "如何使用",
    "助手能查",
    "能查什么",
)
_SMALLTALK_MARKERS = (
    "你好",
    "您好",
    "谢谢",
    "晚安",
    "早上好",
    "晚饭吃了吗",
    "吃饭了吗",
    "睡了吗",
)
_KB_MARKERS = (
    "重返未来",
    "reverse: 1999",
    "十四行诗",
    "槲寄生",
    "暴雨",
    "基金会",
    "角色",
    "技能",
    "神秘术",
    "剧情",
    "世界观",
    "心相",
    "语音",
    "立绘",
)
_OUT_OF_SCOPE_MARKERS = (
    "删除数据库",
    "修改生产",
    "执行命令",
    "下载全部",
)
_GENERAL_OPEN_MARKERS = (
    "中国的首都",
    "法国的首都",
    "今天的天气",
    "写一段代码",
)
_DEPENDENCY_MARKERS = ("她", "他", "它", "为什么", "比较", "如果", "后来", "然后呢")
_SEMANTIC_TEXT_RE = re.compile(r"[\W_]+", re.UNICODE)


@dataclass(frozen=True)
class PlannedSubtask:
    subtask_id: str
    order: int
    task_type: TaskType
    query: str
    query_plan: QueryPlan | None
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "depends_on", tuple(self.depends_on))


@dataclass(frozen=True)
class RequestPlan:
    original_query: str
    subtasks: tuple[PlannedSubtask, ...]
    aggregation_mode: AggregationMode = "ordered_sections"
    planning_status: str = "llm"
    planning_warning: str = ""
    planning_error: str = ""
    schema_version: str = "rag.request_plan/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "subtasks", tuple(self.subtasks))


class RequestPlanner:
    """Classify top-level tasks while leaving all authorization to route policy."""

    def __init__(self, llm: Any | None, *, query_planner: QueryPlanner) -> None:
        self._llm = llm
        self._query_planner = query_planner

    def plan(
        self,
        query: str,
        *,
        category: str | None = None,
        conversation: ConversationProjection = EMPTY_PROJECTION,
        trace: RequestTrace | NullTrace | None = None,
    ) -> RequestPlan:
        direct = self._safe_local_or_fixed_plan(
            query,
            category=category,
            conversation=conversation,
            trace=trace,
        )
        if direct is not None:
            return direct
        if self._llm is None:
            return self._fallback(
                query,
                category=category,
                conversation=conversation,
                trace=trace,
                status="fallback_no_llm",
                warning="顶层任务规划服务未配置，已使用本地安全分类。",
                error="llm is None",
            )
        try:
            messages = [
                SystemMessage(content=self._system_prompt()),
                HumanMessage(content=json.dumps({"question": query}, ensure_ascii=False)),
            ]
            response = self._llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            payload = json.loads(content)
            plan = self._from_payload(
                query,
                payload,
                category=category,
                conversation=conversation,
                trace=trace,
            )
            return validate_request_plan(plan)
        except TimeoutError:
            status = "fallback_timeout"
            warning = "顶层任务规划服务超时，已使用本地安全分类。"
            error = PLANNING_ERROR_TIMEOUT
        except json.JSONDecodeError:
            status = "fallback_parse_error"
            warning = "顶层任务规划结果解析失败，已使用本地安全分类。"
            error = PLANNING_ERROR_PARSE
        except ValueError:
            status = "fallback_schema_error"
            warning = "顶层任务规划字段不合法，已使用本地安全分类。"
            error = PLANNING_ERROR_SCHEMA
        except Exception:
            status = "fallback_api_error"
            warning = "顶层任务规划服务调用失败，已使用本地安全分类。"
            error = PLANNING_ERROR_API
        return self._fallback(
            query,
            category=category,
            conversation=conversation,
            trace=trace,
            status=status,
            warning=warning,
            error=error,
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "只把用户请求分类为安全的顶层任务，不回答问题。只输出 JSON 对象，唯一顶层字段"
            "为 subtasks。每个 subtask 只允许 task_type、query、order、depends_on；"
            "task_type 只能是 assistant_meta/social_smalltalk/knowledge_base/general_open/"
            "out_of_scope。不得输出 route、授权、实体、检索参数或回答。最多四个任务；"
            "只拆分语义独立且没有共享指代的请求。"
        )

    def _safe_local_or_fixed_plan(
        self,
        query: str,
        *,
        category: str | None,
        conversation: ConversationProjection,
        trace: RequestTrace | NullTrace | None,
    ) -> RequestPlan | None:
        parts = tuple(
            part.strip()
            for part in re.split(r"[,，]", query)
            if part.strip()
        )
        if (
            len(parts) == 3
            and self._classify(parts[0], category) == "social_smalltalk"
            and self._classify(parts[1], category) == "assistant_meta"
            and self._classify(parts[2], category) == "knowledge_base"
        ):
            return self._build_plan(
                query,
                (
                    ("social_smalltalk", parts[0], ()),
                    ("assistant_meta", parts[1], ()),
                    ("knowledge_base", parts[2], ()),
                ),
                category=category,
                conversation=conversation,
                trace=trace,
                status="fallback_rule",
            )
        task_type = self._classify(query, category)
        if task_type in {"assistant_meta", "social_smalltalk", "out_of_scope"}:
            return self._build_plan(
                query,
                ((task_type, query.strip(), ()),),
                category=category,
                conversation=conversation,
                trace=trace,
                status="fallback_rule",
            )
        return None

    def _from_payload(
        self,
        query: str,
        payload: object,
        *,
        category: str | None,
        conversation: ConversationProjection,
        trace: RequestTrace | NullTrace | None,
    ) -> RequestPlan:
        if not isinstance(payload, dict) or set(payload) != {"subtasks"}:
            raise ValueError("request planner payload must contain only subtasks")
        raw_subtasks = payload["subtasks"]
        if not isinstance(raw_subtasks, list):
            raise ValueError("subtasks must be a list")
        parsed: list[tuple[str, str, tuple[str, ...]]] = []
        for expected_order, raw in enumerate(raw_subtasks, start=1):
            if not isinstance(raw, dict):
                raise ValueError("subtask must be an object")
            allowed = {"task_type", "query", "order", "depends_on"}
            if set(raw) - allowed:
                raise ValueError("subtask contains authorization or retrieval fields")
            if raw.get("order") != expected_order:
                raise ValueError("subtask order must be contiguous")
            task_type = str(raw.get("task_type") or "")
            subquery = str(raw.get("query") or "").strip()
            depends_raw = raw.get("depends_on", [])
            if not isinstance(depends_raw, list):
                raise ValueError("depends_on must be a list")
            parsed.append((task_type, subquery, tuple(str(item) for item in depends_raw)))
        return self._build_plan(
            query,
            tuple(parsed),
            category=category,
            conversation=conversation,
            trace=trace,
            status="llm",
        )

    def _fallback(
        self,
        query: str,
        *,
        category: str | None,
        conversation: ConversationProjection,
        trace: RequestTrace | NullTrace | None,
        status: str,
        warning: str,
        error: str,
    ) -> RequestPlan:
        task_type = self._classify(query, category)
        return self._build_plan(
            query,
            ((task_type, query.strip(), ()),),
            category=category,
            conversation=conversation,
            trace=trace,
            status=status,
            warning=warning,
            error=error,
        )

    def _build_plan(
        self,
        original_query: str,
        tasks: tuple[tuple[str, str, tuple[str, ...]], ...],
        *,
        category: str | None,
        conversation: ConversationProjection,
        trace: RequestTrace | NullTrace | None,
        status: str,
        warning: str = "",
        error: str = "",
    ) -> RequestPlan:
        subtasks: list[PlannedSubtask] = []
        for order, (task_type, subquery, depends_on) in enumerate(tasks, start=1):
            query_plan = None
            if task_type == "knowledge_base":
                query_plan = self._plan_kb(
                    subquery,
                    category=category,
                    conversation=conversation,
                    trace=trace,
                )
                scope = _retrieval_scope(query_plan, subquery)
                try:
                    query_plan = replace(query_plan, retrieval_scope=scope)
                except TypeError:
                    setattr(query_plan, "retrieval_scope", scope)
            subtasks.append(PlannedSubtask(
                subtask_id=f"T{order:02d}",
                order=order,
                task_type=task_type,
                query=subquery,
                query_plan=query_plan,
                depends_on=depends_on,
            ))
        return validate_request_plan(RequestPlan(
            original_query=original_query,
            subtasks=tuple(subtasks),
            planning_status=status,
            planning_warning=warning,
            planning_error=error,
        ))

    def _plan_kb(
        self,
        query: str,
        *,
        category: str | None,
        conversation: ConversationProjection,
        trace: RequestTrace | NullTrace | None,
    ) -> QueryPlan:
        if trace is None or isinstance(trace, NullTrace):
            return self._query_planner.plan(
                query,
                category=category,
                conversation=conversation,
            )
        return self._query_planner.plan(
            query,
            category=category,
            conversation=conversation,
            trace=trace,
        )

    @staticmethod
    def _classify(query: str, category: str | None) -> TaskType:
        lowered = query.lower()
        if any(marker in lowered for marker in _ASSISTANT_META_MARKERS):
            return "assistant_meta"
        if any(marker in lowered for marker in _SMALLTALK_MARKERS):
            return "social_smalltalk"
        if any(marker in lowered for marker in _OUT_OF_SCOPE_MARKERS):
            return "out_of_scope"
        if category or any(marker in lowered for marker in _KB_MARKERS):
            return "knowledge_base"
        if any(marker in lowered for marker in _GENERAL_OPEN_MARKERS):
            return "general_open"
        return "knowledge_base"


def validate_request_plan(plan: RequestPlan) -> RequestPlan:
    if plan.schema_version != "rag.request_plan/v1":
        raise ValueError("unsupported request plan schema version")
    if plan.aggregation_mode != "ordered_sections":
        raise ValueError("unsupported aggregation mode")
    if not 1 <= len(plan.subtasks) <= 4:
        raise ValueError("request plan must contain one to four subtasks")

    original_semantics = _semantic_text(plan.original_query)
    seen_ids: set[str] = set()
    for expected_order, subtask in enumerate(plan.subtasks, start=1):
        expected_id = f"T{expected_order:02d}"
        if subtask.order != expected_order or subtask.subtask_id != expected_id:
            raise ValueError("subtask IDs and order must be contiguous")
        if subtask.subtask_id in seen_ids:
            raise ValueError("duplicate subtask ID")
        if subtask.task_type not in _TASK_TYPES:
            raise ValueError("unsupported task type")
        if not subtask.query.strip():
            raise ValueError("subtask query must not be empty")
        query_semantics = _semantic_text(subtask.query)
        if not query_semantics or query_semantics not in original_semantics:
            raise ValueError("subtask query must be a semantic subset of the request")
        if subtask.task_type == "knowledge_base":
            if subtask.query_plan is None:
                raise ValueError("knowledge task requires QueryPlan")
        elif subtask.query_plan is not None:
            raise ValueError("non-KB task must not contain QueryPlan")
        for dependency in subtask.depends_on:
            if dependency not in seen_ids:
                raise ValueError("depends_on must reference an earlier subtask")
        seen_ids.add(subtask.subtask_id)
    return plan


def _semantic_text(value: str) -> str:
    return _SEMANTIC_TEXT_RE.sub("", value).lower()


def _retrieval_scope(plan: QueryPlan, query: str) -> RetrievalScope:
    entity_type = str(getattr(plan, "entity_type", None) or "").lower()
    entity_id = getattr(plan, "entity_id", None)
    entity = getattr(plan, "entity", None)
    intent = str(getattr(plan, "intent", "") or "")
    if entity_id and entity_type in {"topic", "story", "page"}:
        return "topic_strict"
    if entity_id or entity:
        return "entity_strict"
    if "暴雨" in query or intent in {"general_game", "story", "lore"}:
        return "corpus_topic"
    return "corpus_topic"


__all__ = [
    "AggregationMode",
    "PLANNING_ERROR_API",
    "PLANNING_ERROR_PARSE",
    "PLANNING_ERROR_SCHEMA",
    "PLANNING_ERROR_TIMEOUT",
    "PlannedSubtask",
    "RequestPlan",
    "RequestPlanner",
    "RetrievalScope",
    "TaskType",
    "validate_request_plan",
]
