from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Literal, cast

from .citations import validate_or_repair_answer
from .contracts import (
    CitationValidation,
    EntityRef,
    FrozenRetrievalPacket,
    ResponsePacket,
    freeze_value,
)
from .conversation import (
    EMPTY_PROJECTION,
    ConversationProjection,
    ConversationTurn,
    build_conversation_turn,
    history_messages,
)
from .query_plan import requested_intents
from .tracing import NullTrace, RequestTrace

MemoryStatus = Literal["disabled", "new", "hit", "expired"]
GenerationMode = Literal["grounded", "free_supplement", "none"]
_MEMORY_STATUSES = frozenset({"disabled", "new", "hit", "expired"})


@dataclass(frozen=True)
class AskExecutionInput:
    question: str
    category: str | None
    route_options: Mapping[str, bool]
    action_payload: Mapping[str, object] | None
    memory_status: MemoryStatus = "disabled"
    memory_turns_used: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_options", freeze_value(self.route_options))
        if self.action_payload is not None:
            object.__setattr__(self, "action_payload", freeze_value(self.action_payload))
        if self.memory_status not in _MEMORY_STATUSES:
            raise ValueError("unsupported memory status")
        if self.memory_turns_used < 0:
            raise ValueError("memory_turns_used must not be negative")


@dataclass(frozen=True)
class PreparedExecution:
    request: AskExecutionInput
    conversation: ConversationProjection
    retrieval_packet: FrozenRetrievalPacket
    answer_context: str
    generation_messages: tuple[Any, ...]
    generation_mode: GenerationMode
    immediate_answer: str | None
    missing_intents: tuple[str, ...]


def normalize_memory_status(value: object) -> MemoryStatus:
    return cast(MemoryStatus, value if value in _MEMORY_STATUSES else "disabled")


class RAGExecutionService:
    """Own one complete business execution and freeze its validated result."""

    def __init__(self, chain: Any) -> None:
        self._chain = chain

    def execute(
        self,
        request: AskExecutionInput,
        conversation: ConversationProjection = EMPTY_PROJECTION,
        trace: RequestTrace | NullTrace | None = None,
    ) -> ResponsePacket:
        active_trace = trace or NullTrace()
        prepared = self.prepare(request, conversation, active_trace)
        if prepared.generation_mode == "none":
            return self.finalize(prepared, None, active_trace)
        try:
            with active_trace.span("answer.llm"):
                response = _invoke_with_retry(
                    self._chain._llm,
                    list(prepared.generation_messages),
                )
                draft = response.content if hasattr(response, "content") else str(response)
            active_trace.mark_model_first_token()
        except Exception as exc:
            return self.finalize(
                prepared,
                None,
                active_trace,
                generation_error=exc,
            )
        return self.finalize(prepared, str(draft), active_trace)

    def prepare(
        self,
        request: AskExecutionInput,
        conversation: ConversationProjection,
        trace: RequestTrace | NullTrace,
    ) -> PreparedExecution:
        from .chain import (
            _API_KEY_EMPTY_MSG,
            _EMPTY_RETRIEVAL_MSG,
            _RETRIEVAL_FAILED_MSG,
        )

        retrieved = self._chain.retrieve(
            request.question,
            category=request.category,
            route_options=dict(request.route_options),
            action_payload=(
                dict(request.action_payload) if request.action_payload is not None else None
            ),
            conversation=conversation,
            trace=trace,
        )
        plan = retrieved["plan"]
        source_map = tuple(retrieved.get("source_map", ()))
        sources = tuple(retrieved.get("sources", ()))
        context = str(retrieved.get("context", ""))
        answer_context = _answer_context(context, retrieved)
        route_decision = retrieved["route_decision"]
        retrieval_packet = FrozenRetrievalPacket(
            plan=plan,
            entity_ref=_entity_ref(plan),
            route_decision=route_decision,
            requested_intents=tuple(requested_intents(plan)),
            sources=sources,
            source_map=source_map,
            media=tuple(retrieved.get("media", ())),
            media_panels=tuple(retrieved.get("media_panels", ())),
            context=context,
            diagnostics={"route": retrieved.get("route") or {}},
            omitted_actions=tuple(retrieved.get("omitted_actions", ())),
            failure_actions=tuple(retrieved.get("failure_actions", ())),
            planning_status=str(retrieved.get("planning_status", "")),
            planning_warning=str(retrieved.get("planning_warning", "")),
            planning_error=str(retrieved.get("planning_error", "")),
            assets=tuple(retrieved.get("assets", ())),
        )
        generation_mode: GenerationMode
        immediate_answer: str | None = None
        generation_messages: tuple[Any, ...] = ()
        if retrieved.get("retrieval_failed", False):
            generation_mode = "none"
            immediate_answer = _RETRIEVAL_FAILED_MSG
        elif not self._chain.llm_ready():
            generation_mode = "none"
            immediate_answer = _API_KEY_EMPTY_MSG
        elif not sources and retrieved.get("free_supplement", False):
            generation_mode = "free_supplement"
            generation_messages = tuple(
                self._chain._free_supplement_messages(request.question, conversation)
            )
        elif not sources:
            generation_mode = "none"
            immediate_answer = _empty_retrieval_answer(plan, _EMPTY_RETRIEVAL_MSG)
        else:
            generation_mode = "grounded"
            normalized_question = _answer_question(plan, request.question)
            generation_messages = tuple(self._chain._prompt.format_messages(
                context=answer_context,
                history=history_messages(conversation),
                question=normalized_question,
            ))
        return PreparedExecution(
            request=request,
            conversation=conversation,
            retrieval_packet=retrieval_packet,
            answer_context=answer_context,
            generation_messages=generation_messages,
            generation_mode=generation_mode,
            immediate_answer=immediate_answer,
            missing_intents=_missing_intents(retrieved),
        )

    def finalize(
        self,
        prepared: PreparedExecution,
        draft: str | None,
        trace: RequestTrace | NullTrace | None = None,
        *,
        generation_error: Exception | None = None,
    ) -> ResponsePacket:
        active_trace = trace or NullTrace()
        retrieval_packet = prepared.retrieval_packet
        plan = retrieval_packet.plan
        answer: str
        grounding_mode: Literal["grounded", "ungrounded", "none"] = "none"
        turn_outcome: Literal["grounded", "ungrounded", "not_committable"] = "not_committable"
        validation = CitationValidation(valid=True)

        if generation_error is not None:
            answer = f"LLM invocation failed: {type(generation_error).__name__}"
            validation = CitationValidation(
                valid=False,
                warnings=("answer_generation_failed",),
            )
        elif prepared.generation_mode == "none":
            answer = prepared.immediate_answer or ""
        elif prepared.generation_mode == "free_supplement":
            from .chain import _FREE_SUPPLEMENT_PREFIX

            supplemented = f"{_FREE_SUPPLEMENT_PREFIX}{draft or ''}"
            answer, validation = validate_or_repair_answer(
                draft=supplemented,
                context="",
                source_map=(),
                grounding_mode="ungrounded",
                trace=active_trace,
            )
            grounding_mode = "ungrounded"
            if validation.valid:
                turn_outcome = "ungrounded"
        else:
            intents = tuple(retrieval_packet.requested_intents)
            draft_text = _normalize_structured_values(
                str(draft or ""),
                prepared.answer_context,
            )
            draft_text = _remove_unsupported_system_membership(
                draft_text,
                prepared.answer_context,
            )
            draft_text = _normalize_voice_scope(
                draft_text,
                intents,
                tuple(retrieval_packet.assets),
            )
            draft_text = _normalize_media_scope(
                draft_text,
                intents,
                tuple(retrieval_packet.assets),
                plan,
                tuple(retrieval_packet.source_map),
            )
            draft_text = _preserve_evidence_qualifiers(
                draft_text,
                prepared.answer_context,
            )
            draft_text = _neutralize_unsupported_attributions(
                draft_text,
                prepared.answer_context,
            )
            draft_text = _normalize_answer_scope(
                draft_text,
                plan,
                prepared.answer_context,
                prepared.missing_intents,
            )
            disclosure = _shortfall_disclosure(prepared.missing_intents)
            if disclosure:
                draft_text = f"{disclosure}\n\n{draft_text}"
            answer, validation = validate_or_repair_answer(
                draft=draft_text,
                context=prepared.answer_context,
                source_map=tuple(retrieval_packet.source_map),
                grounding_mode="grounded",
                repair=self._chain._repair_citations,
                trace=active_trace,
            )
            if disclosure and disclosure not in answer:
                answer = f"{disclosure}\n\n{answer}"
            grounding_mode = "grounded"
            if validation.valid and "citation_safe_fallback" not in validation.warnings:
                turn_outcome = "grounded"

        memory_info = {
            "status": prepared.request.memory_status,
            "turns_used": prepared.request.memory_turns_used,
            "rewrite_mode": str(getattr(plan, "context_rewrite_mode", "none") or "none"),
        }
        response_packet = ResponsePacket(
            retrieval_packet=retrieval_packet,
            answer=answer,
            grounding_mode=grounding_mode,
            citation_validation=validation,
            memory_info=memory_info,
            turn_outcome=turn_outcome,
        )
        active_trace.mark_validated_ready()
        return response_packet


def _invoke_with_retry(llm: Any, messages: list[Any]) -> Any:
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            return llm.invoke(messages)
        except Exception as error:
            last_error = error
    assert last_error is not None
    raise last_error


def _entity_ref(plan: Any) -> EntityRef | None:
    entity_type = str(getattr(plan, "entity_type", None) or "").strip()
    entity_id = str(getattr(plan, "entity_id", None) or "").strip()
    entity_name = str(getattr(plan, "entity", None) or "").strip()
    if not entity_type or not entity_id or not entity_name:
        return None
    aliases = tuple(str(item) for item in (getattr(plan, "aliases", ()) or ()))
    return EntityRef(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        aliases=aliases,
        resolution_mode=str(getattr(plan, "resolution_mode", "unresolved") or "unresolved"),
    )


def _answer_context(context: str, retrieved: Mapping[str, Any]) -> str:
    notices: list[str] = []
    plan = retrieved.get("plan")
    intents = requested_intents(plan) if plan is not None else ()
    media = retrieved.get("media")
    if isinstance(media, (list, tuple)) and media:
        media_items: list[str] = []
        for item in media[:20]:
            if not isinstance(item, Mapping):
                continue
            media_id = str(item.get("media_id") or item.get("asset_id") or "").strip()
            media_type = str(item.get("asset_type") or item.get("role") or "").strip()
            title = str(item.get("title") or item.get("alt") or "").strip()
            label = " | ".join(value for value in (media_id, media_type, title) if value)
            if label:
                media_items.append(label)
        if media_items:
            notices.append(
                "已挂载媒体（system metadata，不是知识来源，无需引用）：\n"
                + "\n".join(f"- {item}" for item in media_items)
                + "\n回答媒体请求时应说明资源已附加，不得声称本轮没有找到这些媒体。"
            )
    if len(intents) > 1:
        notices.append(
            "多个意图回答要求（系统元数据，不是知识来源，无需引用）："
            f"本轮请求意图为 {', '.join(intents)}；回答必须逐项覆盖，"
            "不得只回答首个意图。"
        )
    route = retrieved.get("route")
    if not isinstance(route, Mapping):
        return _join_answer_context(notices, context)
    debug = route.get("retrieval_debug")
    if not isinstance(debug, Mapping):
        return _join_answer_context(notices, context)
    shortfall = debug.get("coverage_shortfall")
    if not isinstance(shortfall, Mapping):
        return _join_answer_context(notices, context)
    missing = _missing_intents(retrieved)
    if not missing:
        return _join_answer_context(notices, context)
    notices.append(
        "检索覆盖说明（系统元数据，不是知识来源，无需引用）："
        f"以下请求意图没有检索到对应资料：{', '.join(missing)}。"
        "回答必须明确说明资料不足，不得声称已找到这些内容。"
    )
    return _join_answer_context(notices, context)


def _join_answer_context(notices: list[str], context: str) -> str:
    parts = [*notices, context]
    return "\n\n".join(part for part in parts if part)


def _missing_intents(retrieved: Mapping[str, Any]) -> tuple[str, ...]:
    route = retrieved.get("route")
    if not isinstance(route, Mapping):
        return ()
    debug = route.get("retrieval_debug")
    if not isinstance(debug, Mapping):
        return ()
    shortfall = debug.get("coverage_shortfall")
    if not isinstance(shortfall, Mapping):
        return ()
    return tuple(sorted(
        str(intent)
        for intent, count in shortfall.items()
        if _is_positive_count(count)
    ))


_INTENT_DISPLAY_NAMES = {
    "profile_fact": "基础资料",
    "skill": "技能",
    "item": "单品",
    "culture": "文化资料",
    "voice": "语音",
    "media": "图片",
    "video": "视频",
    "intro": "介绍",
    "story": "故事",
    "psychube": "心相",
}


def _shortfall_disclosure(missing: tuple[str, ...]) -> str:
    if not missing:
        return ""
    labels = "、".join(_INTENT_DISPLAY_NAMES.get(intent, intent) for intent in missing)
    return f"检索到的资料不足以完整覆盖：{labels}。"


_RAW_PROFILE_FIELD_RE = re.compile(
    r"(?m)^\s*(稀有度|职业|伤害类型)\s*[:：]\s*(\d+(?:\.\d+)?)\s*$"
)
_ENTITY_REQUIRED_INTENTS = frozenset({
    "intro",
    "profile",
    "profile_fact",
    "skill",
    "item",
    "culture",
    "voice",
    "media",
    "video",
    "story",
})
_SYSTEM_MEMBERSHIP_RE = re.compile(
    r"(?:根据(?:现有|已知|检索到的)信息[，,]\s*)?"
    r"[^。！？\n]{1,50}?是《(?:Reverse\s*:\s*1999|重返未来\s*[：:]\s*1999)》"
    r"中的(?:一名|一个)?(?:角色|人物)[。！？]?\s*",
    re.IGNORECASE,
)


def _normalize_structured_values(answer: str, context: str) -> str:
    """Keep raw structured profile values free of model-added units or decoding."""
    normalized = answer
    fields = tuple(dict.fromkeys(_RAW_PROFILE_FIELD_RE.findall(context)))
    for field, value in fields:
        value_pattern = re.escape(value)
        if field == "稀有度":
            added_unit = re.compile(
                rf"(?<![\d.])({value_pattern})(\*{{0,2}})\s*星"
            )
            normalized = added_unit.sub(
                lambda match: f"{match.group(1)}{match.group(2)}",
                normalized,
            )
        added_explanation = re.compile(
            rf"({re.escape(field)}[^\n]{{0,32}}?{value_pattern})(?![\d.])"
            rf"(\*{{0,2}})\s*[（(][^）)\n]{{1,48}}[）)]"
        )
        normalized = added_explanation.sub(
            lambda match: f"{match.group(1)}{match.group(2)}",
            normalized,
        )
    return normalized


def _remove_unsupported_system_membership(answer: str, context: str) -> str:
    if re.search(r"Reverse\s*:\s*1999|重返未来\s*[：:]\s*1999", context, re.IGNORECASE):
        return answer
    return _SYSTEM_MEMBERSHIP_RE.sub("", answer).strip()


def _normalize_voice_scope(
    answer: str,
    intents: tuple[str, ...],
    assets: tuple[Mapping[str, Any], ...],
) -> str:
    if "voice" not in intents or not assets:
        return answer
    scoped = re.sub(
        r"\n*\s*此外，已挂载的媒体资源[\s\S]*$",
        "",
        answer,
    ).rstrip()
    disclosure = "完整语音请通过按台词分页的附件查看；正文仅列出本轮引用的部分台词。"
    return f"{scoped}\n\n{disclosure}" if scoped else disclosure


def _normalize_media_scope(
    answer: str,
    intents: tuple[str, ...],
    assets: tuple[Mapping[str, Any], ...],
    plan: Any,
    source_map: tuple[Any, ...],
) -> str:
    if intents != ("media",) or not assets or not source_map:
        return answer
    entity_name = str(getattr(plan, "entity", None) or "当前实体").strip()
    first_source = source_map[0]
    if isinstance(first_source, Mapping):
        citation_id = str(first_source.get("citation_id") or "").strip()
    else:
        citation_id = str(getattr(first_source, "citation_id", "") or "").strip()
    if not citation_id:
        return answer
    return (
        f"当前检索来源对应 {entity_name} [{citation_id}]。\n\n"
        f"系统已挂载 {len(assets)} 个图片附件；附件数量、类型和文件名来自系统媒体元数据，"
        "请在下方媒体区查看。"
    )


_SOURCE_CONTEXT_BLOCK_RE = re.compile(
    r"(?ms)^\[(S\d{2,})\]\s.*?(?=^\[S\d{2,}\]\s|\Z)"
)
_EPISTEMIC_QUALIFIERS = (
    "据传",
    "据说",
    "传闻",
    "相传",
    "可能",
    "或许",
    "推测",
    "疑似",
    "尚未证实",
    "未获证实",
)
_ANSWER_CITATION_RE = re.compile(r"\[(S\d{2,})\]")
_ANSWER_QUALIFIER_PREFIX_RE = re.compile(
    r"^(\s*(?:[-*]\s+)?(?:\*\*[^*\n]+\*\*[:：]\s*)?)"
)


def _preserve_evidence_qualifiers(answer: str, context: str) -> str:
    uncertain_sources = {
        match.group(1)
        for match in _SOURCE_CONTEXT_BLOCK_RE.finditer(context)
        if any(marker in match.group(0) for marker in _EPISTEMIC_QUALIFIERS)
    }
    if not uncertain_sources:
        return answer

    normalized: list[str] = []
    for line in answer.splitlines():
        cited = set(_ANSWER_CITATION_RE.findall(line))
        if (
            cited & uncertain_sources
            and not any(marker in line for marker in _EPISTEMIC_QUALIFIERS)
        ):
            prefix = _ANSWER_QUALIFIER_PREFIX_RE.match(line)
            offset = prefix.end() if prefix is not None else 0
            line = f"{line[:offset]}据传，{line[offset:]}"
        normalized.append(line)
    return "\n".join(normalized)


_SPEAKER_ATTRIBUTION_RE = re.compile(
    r"(?:受访者|调查者|采访者|作者|记录者)"
    r"(?:认为|表示|声称|称|提到|透露|推测|希望|期望)"
)


def _neutralize_unsupported_attributions(answer: str, context: str) -> str:
    source_blocks = {
        match.group(1): match.group(0)
        for match in _SOURCE_CONTEXT_BLOCK_RE.finditer(context)
    }
    if not source_blocks:
        return answer

    normalized: list[str] = []
    for line in answer.splitlines():
        cited = _ANSWER_CITATION_RE.findall(line)
        evidence = "\n".join(source_blocks.get(citation_id, "") for citation_id in cited)
        if evidence:
            line = _SPEAKER_ATTRIBUTION_RE.sub(
                lambda match: match.group(0) if match.group(0) in evidence else "资料提及，",
                line,
            )
        normalized.append(line)
    return "\n".join(normalized)


_TOTALITY_CLAIM_RE = re.compile(
    r"(?:^|\n+)\s*(?:以上|上述|这些)(?:内容)?(?:就是|是)?"
    r"(?:本次|本轮)?(?:检索到的|资料中的)?[^。！!\n]{0,24}?(?:全部|所有)[^。！!\n]{0,32}"
    r"(?:资料|内容|信息)[。！!]?\s*",
    re.MULTILINE,
)
_UNSOLICITED_SHORTFALL_RE = re.compile(
    r"(?:\n\s*)+(?:关于|至于)[^。！!\n]{0,120}?"
    r"(?:资料不足|不足以完整回答)[^。！!\n]*[。！!]?\s*"
)
_PROFILE_FALSE_NEGATIVE_RE = re.compile(
    r"[^。！？!?\n]*(?:未提供|未找到|没有提供|资料不足|不足以完整回答|"
    r"无法(?:确认|回答|得知))[^。！？!?\n]*(?:[。！？!?]|$)"
)
_PROFILE_FIELD_EVIDENCE = {
    "生日": ("生日", "诞生于", "出生于"),
    "星级": ("星级", "稀有度"),
    "稀有度": ("稀有度", "星级"),
    "职业": ("职业",),
    "属性": ("属性",),
    "伤害类型": ("伤害类型",),
    "定位": ("定位",),
    "别名": ("别名", "昵称", "称号"),
}


def _remove_profile_false_negatives(answer: str, context: str) -> str:
    def replace(match: re.Match[str]) -> str:
        sentence = match.group(0)
        for field, evidence_labels in _PROFILE_FIELD_EVIDENCE.items():
            if field in sentence and any(label in context for label in evidence_labels):
                return ""
        return sentence

    normalized = _PROFILE_FALSE_NEGATIVE_RE.sub(replace, answer)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _normalize_answer_scope(
    answer: str,
    plan: Any,
    context: str,
    missing_intents: tuple[str, ...],
) -> str:
    scoped = _TOTALITY_CLAIM_RE.sub("\n", answer).strip()
    query_scope = " ".join((
        str(getattr(plan, "original_query", "") or ""),
        str(getattr(plan, "normalized_query", "") or ""),
    ))
    broad_profile = any(label in query_scope for label in ("基础资料", "角色资料"))
    profile_retrieved = any(label in context for label in ("基础资料", "角色资料"))
    if (
        requested_intents(plan) == ("profile_fact",)
        and broad_profile
        and not missing_intents
    ):
        if profile_retrieved:
            scoped = _UNSOLICITED_SHORTFALL_RE.sub("\n", scoped).strip()
        scoped = _remove_profile_false_negatives(scoped, context)
    return scoped


def _empty_retrieval_answer(plan: Any, default: str) -> str:
    if getattr(plan, "entity", None):
        return default
    if set(requested_intents(plan)) & _ENTITY_REQUIRED_INTENTS:
        return "请先明确要查询的角色或实体名称。"
    return default


def _answer_question(plan: Any, original_question: str) -> str:
    original = str(getattr(plan, "original_query", "") or original_question).strip()
    normalized = str(getattr(plan, "normalized_query", "") or original).strip()
    if normalized and normalized != original:
        question = (
            f"用户原始问题：{original}\n"
            f"检索规范化主题（仅用于定位证据，不得覆盖原问题的否定、条件或任务要求）：{normalized}"
        )
    else:
        question = original
    intents = requested_intents(plan)
    if len(intents) <= 1:
        return question
    labels = "、".join(_INTENT_DISPLAY_NAMES.get(intent, intent) for intent in intents)
    return f"{question}\n\n必须逐项回答：{labels}。"


def _is_positive_count(value: object) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def build_completed_turn(
    request: AskExecutionInput,
    packet: ResponsePacket,
    completed_at: datetime,
) -> ConversationTurn | None:
    if packet.turn_outcome not in {"grounded", "ungrounded"}:
        return None
    if packet.grounding_mode == "grounded" and not packet.citation_validation.valid:
        return None
    if packet.grounding_mode not in {"grounded", "ungrounded"}:
        return None

    retrieval = packet.retrieval_packet
    entity_ref = retrieval.entity_ref
    plan = retrieval.plan
    standalone = _plan_value(plan, "normalized_query") or request.question
    return build_conversation_turn(
        original_question=request.question,
        standalone_question=str(standalone),
        answer=packet.answer,
        entity=entity_ref.entity_name if entity_ref else None,
        entity_type=entity_ref.entity_type if entity_ref else None,
        entity_id=entity_ref.entity_id if entity_ref else None,
        requested_intents=retrieval.requested_intents,
        category=request.category,
        grounding_mode=packet.grounding_mode,
        completed_at=completed_at,
    )


def _plan_value(plan: Any, field: str) -> Any:
    if isinstance(plan, Mapping):
        return plan.get(field)
    return getattr(plan, field, None)


__all__ = [
    "AskExecutionInput",
    "GenerationMode",
    "PreparedExecution",
    "RAGExecutionService",
    "build_completed_turn",
    "normalize_memory_status",
]
