"""RAG chain: retrieve -> prompt -> LLM, returning answer, sources, media, and route metadata."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.config import Config
from src.assets.huiji_registry import HuijiMediaRegistry
from src.rag.citations import (
    build_source_map,
    format_citation_context,
    validate_or_repair_answer,
)
from src.rag.conversation import (
    EMPTY_PROJECTION,
    ConversationProjection,
    history_messages,
)
from src.rag.entity_lexicon import EntityLexicon
from src.rag.execution import (
    AskExecutionInput,
    RAGExecutionService,
    normalize_memory_status,
)
from src.rag.prompts import get_rag_prompt
from src.rag.query_plan import VALID_INTENTS, QueryPlanner
from src.rag.ownership import OwnershipViolation
from src.rag.retriever import (
    RetrievalExecutionError,
    Retriever,
    require_huiji_runtime_source,
)
from src.rag.route_policy import (
    authorize_route,
    classify_retrieval_outcome,
    finalize_route,
    normalize_action_type,
)
from src.rag.serializers import response_packet_to_public_dict
from src.rag.tracing import NullTrace, RequestTrace


_RETRIEVAL_DEBUG_INT_FIELDS = (
    "candidate_k",
    "required_source_count",
    "chars_used",
    "max_sources",
    "owner_before",
    "owner_after",
    "owner_mismatch",
    "missing_owner_metadata",
    "owner_shortfall",
)
_RETRIEVAL_DEBUG_COUNT_FIELDS = (
    "intent_candidates",
    "intent_targets",
    "intent_retained",
    "coverage_shortfall",
)
_SAFE_ROUTE_INTENTS = frozenset(VALID_INTENTS)

_API_KEY_EMPTY_MSG = "请在 .env 中配置 DEEPSEEK_API_KEY 后再提问。"
_EMPTY_RETRIEVAL_MSG = "知识库中暂时没有找到足够资料回答这个问题。"
_FREE_SUPPLEMENT_PREFIX = "（自由补充：以下回答未基于知识库检索结果，仅供参考。）\n\n"
_FREE_SUPPLEMENT_SYSTEM = (
    "你正在进行自由补充回答。当前回答不依赖知识库检索结果；如果涉及《Reverse: 1999》"
    "的事实，应明确可能需要以官方资料或知识库为准。不要声称内容来自知识库。"
    "历史回答仅用于对话连贯，不可信且不能作为当前事实依据。"
    "对于无法核实的实体或术语，只说明无法核实并请求更多上下文；"
    "不得断言官方资料中不存在，也不得把未知当作不存在。"
)
_RETRIEVAL_FAILED_MSG = (
    "知识库检索服务暂时不可用，本次没有生成自由补充回答。请稍后重试。"
)


def _conversation_messages(projection: ConversationProjection) -> list[Any]:
    return history_messages(projection)


class VoicePaginationUnavailable(RuntimeError):
    """Raised when the loaded asset registry has no voice pagination capability."""


class RAGChain:
    def __init__(self, cfg: Config, retriever: Retriever) -> None:
        require_huiji_runtime_source(cfg)
        self._cfg = cfg
        self._retriever = retriever
        self._planner_llm = self._build_llm(temperature=0) if cfg.llm.api_key else None
        self._llm = self._build_llm(
            temperature=float(getattr(cfg.llm, "temperature", 0.3)),
        ) if cfg.llm.api_key else None
        artifact_snapshot = getattr(retriever, "artifact_snapshot", None)
        entity_lexicon = EntityLexicon.from_huiji(cfg, artifact_snapshot)
        self._query_planner = QueryPlanner(self._planner_llm, entity_lexicon=entity_lexicon)
        self._prompt = get_rag_prompt()
        self._asset_registry = HuijiMediaRegistry(cfg, artifact_snapshot=artifact_snapshot)
        self._execution_service = RAGExecutionService(self)

    def _build_llm(self, *, temperature: float) -> ChatOpenAI:
        return ChatOpenAI(
            base_url=self._cfg.llm.base_url,
            api_key=self._cfg.llm.api_key,
            model=self._cfg.llm.model,
            temperature=temperature,
            extra_body={"thinking": {"type": self._cfg.llm.thinking}},
        )

    def llm_ready(self) -> bool:
        return self._llm is not None

    def execute(
        self,
        question: str,
        category: str | None = None,
        route_options: Mapping[str, bool] | None = None,
        action_payload: Mapping[str, object] | None = None,
        conversation: ConversationProjection | None = None,
        memory_status: str = "disabled",
        memory_turns_used: int = 0,
        trace: Any = None,
    ):
        request = AskExecutionInput(
            question=question,
            category=category,
            route_options=route_options or {},
            action_payload=action_payload,
            memory_status=normalize_memory_status(memory_status),
            memory_turns_used=max(0, int(memory_turns_used)),
        )
        return self._execution_service.execute(
            request,
            conversation or EMPTY_PROJECTION,
            trace,
        )

    def retrieve(
        self,
        question: str,
        category: str | None = None,
        route_options: dict[str, bool] | None = None,
        action_payload: dict[str, Any] | None = None,
        conversation: ConversationProjection | None = None,
        trace: RequestTrace | NullTrace | None = None,
    ) -> dict[str, Any]:
        active_trace = trace or NullTrace()
        projection = conversation or EMPTY_PROJECTION
        if trace is None or isinstance(active_trace, NullTrace):
            plan = self._query_planner.plan(
                question,
                category=category,
                conversation=projection,
            )
        else:
            plan = self._query_planner.plan(
                question,
                category=category,
                conversation=projection,
                trace=active_trace,
            )
        options = dict(route_options or {})
        authorization = authorize_route(plan, options, action_payload)
        plan = self._with_authorized_options(
            plan,
            options,
            authorization.proposed_route,
        )
        if action_payload:
            plan = self._with_action_payload(plan, action_payload)

        retrieval_failed = False
        if authorization.force_free_supplement:
            sources = []
            debug: dict[str, Any] = {}
        else:
            try:
                if trace is None or isinstance(active_trace, NullTrace):
                    sources = self._retriever.search(
                        plan.normalized_query,
                        category=category,
                        query_plan=plan,
                    )
                else:
                    sources = self._retriever.search(
                        plan.normalized_query,
                        category=category,
                        query_plan=plan,
                        trace=active_trace,
                    )
            except RetrievalExecutionError:
                sources = []
                retrieval_failed = True
            debug = (
                {}
                if retrieval_failed
                else (getattr(self._retriever, "last_route_debug", {}) or {})
            )
        shortfall = debug.get("coverage_shortfall", {}) if isinstance(debug, dict) else {}
        if not isinstance(shortfall, dict):
            shortfall = {}
        outcome = classify_retrieval_outcome(
            sources,
            shortfall,
            failed=retrieval_failed,
        )
        with active_trace.span("route.resolve"):
            decision = finalize_route(authorization, outcome)
        free_supplement = decision.effective_route == "llm_general"
        with active_trace.span("source_map.build", source_count=len(sources)):
            frozen_sources, source_map = build_source_map(sources)
        sources = [dict(source) for source in frozen_sources]
        context = self._format_context(sources, source_map)
        with active_trace.span("media.attach", source_count=len(sources)):
            if free_supplement or retrieval_failed:
                assets = []
                media_panels = []
            elif hasattr(self._asset_registry, "find_bundle_for_retrieval"):
                bundle = self._asset_registry.find_bundle_for_retrieval(plan, sources)
                assets = list(bundle.items)
                media_panels = [dict(panel) for panel in bundle.panels]
                media_panels.extend(self._build_media_panels(assets, include_voice=False))
            else:
                assets = self._asset_registry.find_for_retrieval(plan, sources)
                media_panels = self._build_media_panels(assets)
        route = self._route_info(plan, decision, debug)
        omitted_actions = (
            []
            if free_supplement or retrieval_failed
            else list(getattr(self._retriever, "last_omitted_actions", []) or [])
        )
        if retrieval_failed:
            failure_actions = self._failure_actions(question, plan, include_free=False)
        elif outcome in {"empty", "partial"} and not free_supplement:
            failure_actions = self._failure_actions(question, plan)
        else:
            failure_actions = []
        planning_meta = self._planning_meta(plan)
        return {
            "plan": plan,
            "sources": sources,
            "source_map": source_map,
            "context": context,
            "assets": assets,
            "media": assets,
            "route": route,
            "omitted_actions": omitted_actions,
            "failure_actions": failure_actions,
            "media_panels": media_panels,
            "free_supplement": free_supplement,
            "retrieval_failed": retrieval_failed,
            "route_decision": decision,
            **planning_meta,
        }

    def _with_authorized_options(
        self,
        plan: Any,
        route_options: dict[str, bool],
        proposed_route: str,
    ) -> Any:
        try:
            return replace(
                plan,
                route_options=dict(route_options),
                route=proposed_route,
            )
        except Exception:
            setattr(plan, "route_options", dict(route_options))
            setattr(plan, "route", proposed_route)
            return plan

    def _with_action_payload(self, plan: Any, action_payload: dict[str, Any]) -> Any:
        action_type = normalize_action_type(action_payload)
        target_parent_id = str(action_payload.get("target_parent_id") or "").strip()
        if action_type != "expand_parent" and not target_parent_id:
            return plan
        plan_owner = (
            str(getattr(plan, "entity_type", None) or "").strip(),
            str(getattr(plan, "entity_id", None) or "").strip(),
        )
        action_owner = (
            str(action_payload.get("entity_type") or "").strip(),
            str(action_payload.get("entity_id") or "").strip(),
        )
        if not all(plan_owner) or (any(action_owner) and action_owner != plan_owner):
            raise OwnershipViolation("expand action owner does not match the current plan")
        updates = {"target_parent_id": target_parent_id or None}
        try:
            return replace(plan, **updates)
        except (TypeError, AttributeError):
            for key, value in updates.items():
                setattr(plan, key, value)
            return plan

    def _route_info(
        self,
        plan: Any,
        decision: Any,
        debug: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        debug = debug or {}
        if not isinstance(debug, dict):
            debug = {}
        plan_intents = [
            intent
            for intent in (
                getattr(plan, "intent", ""),
                *tuple(getattr(plan, "secondary_intents", ()) or ()),
            )
            if type(intent) is str and intent
        ]
        debug_intents = self._strict_ordered_strings(debug.get("requested_intents"))
        requested = debug_intents or list(dict.fromkeys(plan_intents))
        retrieval_debug: dict[str, object] = {}
        for field in _RETRIEVAL_DEBUG_INT_FIELDS:
            value = debug.get(field)
            if type(value) is int:
                retrieval_debug[field] = value
        for field in _RETRIEVAL_DEBUG_COUNT_FIELDS:
            value = debug.get(field)
            if isinstance(value, dict):
                counts = {
                    key: count
                    for key, count in value.items()
                    if self._is_safe_intent_identifier(key) and type(count) is int
                }
                retrieval_debug[field] = counts
        plan_intent = self._strict_string(getattr(plan, "intent", ""))
        debug_entity = self._strict_entity(debug.get("entity"))
        plan_entity = self._strict_entity(getattr(plan, "entity", None))
        return {
            "name": decision.effective_route,
            "confidence": self._strict_confidence(getattr(plan, "confidence", 0.0)),
            "intent": plan_intent if self._is_safe_intent_identifier(plan_intent) else "general",
            "entity": debug_entity or plan_entity,
            "requested_intents": list(decision.authorization.semantic_intents) or requested,
            "semantic_intents": list(decision.authorization.semantic_intents) or requested,
            "proposed_route": decision.authorization.proposed_route,
            "effective_route": decision.effective_route,
            "retrieval_outcome": decision.retrieval_outcome,
            "route_reason": decision.route_reason,
            "retrieval_debug": retrieval_debug,
        }

    @staticmethod
    def _strict_ordered_strings(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return list(dict.fromkeys(
            item for item in value if RAGChain._is_safe_intent_identifier(item)
        ))

    @staticmethod
    def _is_safe_intent_identifier(value: Any) -> bool:
        return type(value) is str and value in _SAFE_ROUTE_INTENTS

    @staticmethod
    def _strict_string(value: Any) -> str:
        return value if type(value) is str else ""

    @staticmethod
    def _strict_entity(value: Any) -> str | None:
        return value if type(value) is str and value else None

    @staticmethod
    def _strict_confidence(value: Any) -> float:
        if type(value) not in (int, float):
            return 0.0
        return float(value)

    def _planning_meta(self, plan: Any) -> dict[str, str]:
        return {
            "planning_status": str(getattr(plan, "planning_status", "") or ""),
            "planning_warning": str(getattr(plan, "planning_warning", "") or ""),
            "planning_error": str(getattr(plan, "planning_error", "") or ""),
        }

    def _failure_actions(
        self,
        question: str,
        plan: Any,
        *,
        include_free: bool = True,
    ) -> list[dict[str, Any]]:
        entity = getattr(plan, "entity", "") or ""
        entity_type = getattr(plan, "entity_type", "") or ""
        entity_id = getattr(plan, "entity_id", "") or ""
        semantic_intents = [
            item
            for item in (
                getattr(plan, "intent", ""),
                *tuple(getattr(plan, "secondary_intents", ()) or ()),
            )
            if item in VALID_INTENTS
        ]
        actions = [{
            "label": "扩大范围重新搜索",
            "query": question,
            "action_type": "expand_search",
            "entity": entity,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "semantic_intents": semantic_intents,
            "intent": "",
            "packet_policy": "",
            "target_parent_id": None,
        }]
        if include_free:
            actions.append({
                "label": "使用自由补充重答",
                "query": question,
                "action_type": "force_free_supplement",
                "entity": entity,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "semantic_intents": semantic_intents,
                "intent": "",
                "packet_policy": "",
                "target_parent_id": None,
            })
        return actions

    def _build_media_panels(
        self,
        media: list[dict[str, Any]],
        *,
        include_voice: bool = True,
    ) -> list[dict[str, Any]]:
        panels: list[dict[str, Any]] = []
        voice_items = [
            item for item in media
            if item.get("asset_type") == "voice" or item.get("role") == "voice"
        ]
        video_items = [
            item for item in media
            if item.get("asset_type") == "video" or item.get("role") == "video"
        ]
        if include_voice and voice_items:
            panels.append({"type": "voice", "items": voice_items})
        if video_items:
            panels.append({"type": "video", "items": video_items})
        return panels

    def get_voice_page(self, cursor: str) -> dict[str, object]:
        get_voice_page = getattr(self._asset_registry, "get_voice_page", None)
        if not callable(get_voice_page):
            raise VoicePaginationUnavailable("voice pagination unavailable")
        return get_voice_page(cursor)

    def _format_context(self, sources: list[dict[str, Any]], source_map: Any) -> str:
        return format_citation_context(sources, source_map)

    def _ask_v1(
        self,
        question: str,
        category: str | None = None,
        route_options: dict[str, bool] | None = None,
        action_payload: dict[str, Any] | None = None,
        conversation: ConversationProjection | None = None,
    ) -> dict[str, Any]:
        projection = conversation or EMPTY_PROJECTION
        retrieved = self.retrieve(
            question,
            category=category,
            route_options=route_options,
            action_payload=action_payload,
            conversation=projection,
        )
        sources = retrieved["sources"]
        assets = retrieved["assets"]
        media = retrieved.get("media", assets)
        meta = {
            "route": retrieved.get("route"),
            "planning_status": retrieved.get("planning_status", ""),
            "planning_warning": retrieved.get("planning_warning", ""),
            "planning_error": retrieved.get("planning_error", ""),
            "omitted_actions": retrieved.get("omitted_actions", []),
            "failure_actions": retrieved.get("failure_actions", []),
            "media_panels": retrieved.get("media_panels", []),
            "citation_warning": "",
        }
        private_meta = {
            "_conversation_plan": retrieved["plan"],
            "_turn_outcome": "not_committable",
        }
        if retrieved.get("retrieval_failed", False):
            return {
                "answer": _RETRIEVAL_FAILED_MSG,
                "sources": [],
                "assets": [],
                "media": [],
                **meta,
                **private_meta,
            }
        if not self.llm_ready():
            return {"answer": _API_KEY_EMPTY_MSG, "sources": sources, "assets": assets, "media": media, **meta, **private_meta}

        if not sources:
            if retrieved.get("free_supplement", False):
                try:
                    draft = self._invoke_free_supplement(question, projection)
                    answer, validation = validate_or_repair_answer(
                        draft=draft,
                        context="",
                        source_map=(),
                        grounding_mode="ungrounded",
                    )
                    private_meta["_citation_validation"] = validation
                    meta["citation_warning"] = ",".join(validation.warnings)
                    if validation.valid:
                        private_meta["_turn_outcome"] = "ungrounded"
                except Exception as e:
                    answer = f"调用 LLM 失败: {e}"
                return {"answer": answer, "sources": [], "assets": [], "media": [], **meta, **private_meta}
            return {"answer": _EMPTY_RETRIEVAL_MSG, "sources": [], "assets": [], "media": [], **meta, **private_meta}

        context = retrieved["context"]
        messages = self._prompt.format_messages(
            context=context,
            history=_conversation_messages(projection),
            question=question,
        )
        try:
            resp = self._llm.invoke(messages)
            draft = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            return {"answer": f"调用 LLM 失败: {e}", "sources": sources, "assets": assets, "media": media, **meta, **private_meta}
        answer, validation = validate_or_repair_answer(
            draft=str(draft),
            context=context,
            source_map=retrieved.get("source_map", ()),
            grounding_mode="grounded",
            repair=self._repair_citations,
        )
        private_meta["_citation_validation"] = validation
        meta["citation_warning"] = ",".join(validation.warnings)
        if validation.valid:
            private_meta["_turn_outcome"] = "grounded"
        return {"answer": answer, "sources": sources, "assets": assets, "media": media, **meta, **private_meta}

    def ask(
        self,
        question: str,
        category: str | None = None,
        route_options: dict[str, bool] | None = None,
        action_payload: dict[str, Any] | None = None,
        conversation: ConversationProjection | None = None,
    ) -> dict[str, Any]:
        packet = self.execute(
            question,
            category=category,
            route_options=route_options,
            action_payload=action_payload,
            conversation=conversation,
        )
        result = response_packet_to_public_dict(packet)
        result["_conversation_plan"] = packet.retrieval_packet.plan
        result["_turn_outcome"] = packet.turn_outcome
        result["_citation_validation"] = packet.citation_validation
        return result

    def _repair_citations(self, draft: str, context: str, source_map: Any) -> str:
        valid_ids = ", ".join(item.citation_id for item in source_map)
        messages = [
            SystemMessage(content=(
                "Repair citation markers without adding facts. Use only the current "
                f"source IDs: {valid_ids}. Every factual claim needs at least one ID. "
                "Use separate markers such as [S01][S03], never titles or combined labels. "
                "If the draft only reports insufficient evidence, it must still end with one "
                "valid current ID. If no draft claim is supportable, return exactly: "
                f"检索到的资料不足以完整回答 [{source_map[0].citation_id}]。"
            )),
            HumanMessage(content=f"Current evidence:\n{context}\n\nDraft:\n{draft}"),
        ]
        response = self._llm.invoke(messages)
        return str(response.content if hasattr(response, "content") else response)

    def _free_supplement_messages(
        self,
        question: str,
        conversation: ConversationProjection = EMPTY_PROJECTION,
    ) -> list[Any]:
        return [
            SystemMessage(content=_FREE_SUPPLEMENT_SYSTEM),
            *_conversation_messages(conversation),
            HumanMessage(content=question),
        ]

    def _invoke_free_supplement(
        self,
        question: str,
        conversation: ConversationProjection = EMPTY_PROJECTION,
    ) -> str:
        resp = self._llm.invoke(self._free_supplement_messages(question, conversation))
        answer = resp.content if hasattr(resp, "content") else str(resp)
        return f"{_FREE_SUPPLEMENT_PREFIX}{answer}"

    def _stream_llm(
        self,
        question: str,
        context: str,
        free_supplement: bool = False,
        conversation: ConversationProjection | None = None,
    ):
        projection = conversation or EMPTY_PROJECTION
        if free_supplement:
            yield _FREE_SUPPLEMENT_PREFIX
            messages = self._free_supplement_messages(question, projection)
        else:
            messages = self._prompt.format_messages(
                context=context,
                history=_conversation_messages(projection),
                question=question,
            )
        for chunk in self._llm.stream(messages):
            yield chunk
