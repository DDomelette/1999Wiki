"""Independent LLM judge and deterministic answer checks for M3."""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.rag_eval.contracts import (
    EvalCase,
    EvaluationEvent,
    JudgeIdentity,
    Severity,
    worst_severity,
)


JUDGE_PROMPT_VERSION = "rag-answer-judge/v1"
PAIR_PROMPT_VERSION = "rag-answer-pair-judge/v1"
_CITATION_RE = re.compile(r"\[(S\d{2,})\]")
_REFUSAL_MARKERS = (
    "资料不足",
    "未找到",
    "没有找到",
    "无法",
    "不能确认",
    "需要更多",
    "请明确",
    "请提供",
    "自由补充",
)


class JudgeConfigError(ValueError):
    """Raised when an independent judge cannot be configured safely."""


@dataclass(frozen=True)
class JudgeConfig:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    temperature: float = 0.0
    prompt_version: str = JUDGE_PROMPT_VERSION

    @property
    def identity(self) -> JudgeIdentity:
        return JudgeIdentity(
            base_url=self.base_url,
            model=self.model,
            prompt_version=self.prompt_version,
        )


@dataclass(frozen=True)
class JudgeResult:
    groundedness: int
    relevance: int
    completeness: int
    refusal_correctness: int
    unsupported_claims: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    reason: str
    passed: bool
    prompt_version: str
    error: str = ""

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
        *,
        prompt_version: str,
    ) -> "JudgeResult":
        if payload.get("schema_version") != "rag_judge.v1":
            raise ValueError("judge schema_version must be rag_judge.v1")
        scores: dict[str, int] = {}
        for key in ("groundedness", "relevance", "completeness", "refusal_correctness"):
            value = payload.get(key)
            if type(value) is not int or not 1 <= value <= 5:
                raise ValueError(f"judge score {key} must be an integer in 1..5")
            scores[key] = value
        return cls(
            groundedness=scores["groundedness"],
            relevance=scores["relevance"],
            completeness=scores["completeness"],
            refusal_correctness=scores["refusal_correctness"],
            unsupported_claims=_strings(payload.get("unsupported_claims")),
            missing_requirements=_strings(payload.get("missing_requirements")),
            reason=str(payload.get("reason") or ""),
            passed=bool(payload.get("passed")),
            prompt_version=prompt_version,
        )

    @classmethod
    def failure(cls, error: str) -> "JudgeResult":
        return cls(
            groundedness=1,
            relevance=1,
            completeness=1,
            refusal_correctness=1,
            unsupported_claims=(),
            missing_requirements=(),
            reason="judge execution failed",
            passed=False,
            prompt_version=JUDGE_PROMPT_VERSION,
            error=error,
        )

    @property
    def score(self) -> float:
        return (
            self.groundedness
            + self.relevance
            + self.completeness
            + self.refusal_correctness
        ) / 20.0 * 100.0


@dataclass(frozen=True)
class AnswerEvaluation:
    judge: JudgeResult
    citation_names: tuple[str, ...]
    citation_validity: float
    refusal_marker_present: bool
    events: tuple[EvaluationEvent, ...]

    @property
    def severity(self) -> Severity:
        return worst_severity([event.severity for event in self.events])

    @property
    def score(self) -> float:
        citation_component = self.citation_validity * 10.0
        return min(100.0, self.judge.score * 0.9 + citation_component)


@dataclass(frozen=True)
class PairJudgeResult:
    equivalent: bool
    contradictions: tuple[str, ...]
    reason: str
    prompt_version: str
    events: tuple[EvaluationEvent, ...] = ()


def load_judge_config(
    production_cfg: object,
    environ: Mapping[str, str] | None = None,
) -> JudgeConfig:
    values = environ if environ is not None else os.environ
    base_url = str(values.get("RAG_EVAL_JUDGE_BASE_URL") or "").strip()
    model = str(values.get("RAG_EVAL_JUDGE_MODEL") or "").strip()
    api_key = str(values.get("RAG_EVAL_JUDGE_API_KEY") or "").strip()
    missing = [
        name
        for name, value in (
            ("RAG_EVAL_JUDGE_BASE_URL", base_url),
            ("RAG_EVAL_JUDGE_MODEL", model),
            ("RAG_EVAL_JUDGE_API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        raise JudgeConfigError(f"judge configuration missing: {', '.join(missing)}")
    llm = getattr(production_cfg, "llm", None)
    production_identity = (
        str(getattr(llm, "base_url", "")).rstrip("/"),
        str(getattr(llm, "model", "")),
    )
    judge_identity = (base_url.rstrip("/"), model)
    if judge_identity == production_identity:
        raise JudgeConfigError("judge must use a distinct (base_url, model) identity")
    return JudgeConfig(base_url=base_url, model=model, api_key=api_key)


class AnswerJudge:
    def __init__(self, config: JudgeConfig, *, client: object | None = None) -> None:
        if config.temperature != 0.0:
            raise JudgeConfigError("judge temperature must be 0")
        self.config = config
        self.client = client or ChatOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            temperature=0,
        )

    def evaluate_answer(
        self,
        case: EvalCase,
        *,
        answer: str,
        context: str,
        sources: Iterable[Mapping[str, object]],
        media: Iterable[Mapping[str, object]] = (),
        failure_actions: Iterable[Mapping[str, object]] = (),
    ) -> AnswerEvaluation:
        sources = tuple(sources)
        media = tuple(media)
        failure_actions = tuple(failure_actions)
        source_ids: set[str] = set()
        for item in sources:
            citation_id = str(item.get("citation_id") or "")
            if citation_id:
                source_ids.add(citation_id)
        citations = _extract_citations(answer)
        invalid = tuple(citation_id for citation_id in citations if citation_id not in source_ids)
        citation_validity = (
            (len(citations) - len(invalid)) / len(citations)
            if citations
            else (0.0 if source_ids and answer.strip() else 1.0)
        )
        events: list[EvaluationEvent] = []
        if invalid:
            events.append(
                _answer_event(
                    "ANSWER.INVALID_CITATION",
                    Severity.SEV1,
                    case,
                    observed={"invalid_citations": list(invalid)},
                    expected={"source_ids": sorted(source_ids)},
                    action="validate short citation IDs against the current source map before release",
                )
            )
        elif source_ids and answer.strip() and not citations:
            events.append(
                _answer_event(
                    "ANSWER.CITATION_MISSING",
                    Severity.SEV3,
                    case,
                    expected={"source_ids": sorted(source_ids)},
                    action="make grounded answers cite returned short source IDs",
                )
            )

        refusal_marker = any(marker in answer for marker in _REFUSAL_MARKERS) or bool(failure_actions)
        payload = {
            "query": case.query,
            "difficulty": case.difficulty.value,
            "scenario": case.scenario,
            "expected_intents": list(case.expected_intents),
            "expected_behavior": case.expected_behavior,
            "expected_entity_name": case.expected_entity_name,
            "expected_entity_ids": list(case.expected_entity_ids),
            "conversation_mode": case.conversation_mode,
            "context": context,
            "answer": answer,
            "operational_metadata": {
                "grounding_sources": [
                    _project_fields(
                        item,
                        (
                            "citation_id",
                            "entity_type",
                            "entity_id",
                            "child_id",
                            "parent_id",
                            "name",
                            "heading_path",
                        ),
                    )
                    for item in sources[:40]
                ],
                "attached_media_count": len(media),
                "attached_media_truncated": len(media) > 40,
                "attached_media": [
                    _project_fields(
                        item,
                        ("media_id", "asset_type", "role", "mime", "title", "child_id"),
                    )
                    for item in media[:40]
                ],
                "failure_actions": [
                    _project_fields(item, ("action_type", "label", "reason"))
                    for item in failure_actions
                ],
            },
        }
        try:
            judge = self._invoke_answer_with_retry(payload)
        except Exception as error:
            judge = JudgeResult.failure(str(error))
            events.append(
                _answer_event(
                    "ANSWER.JUDGE_FAILED",
                    Severity.SEV2,
                    case,
                    observed={"error": str(error)},
                    action="restore or recalibrate the independent judge and rerun all M3 cases",
                )
            )
        else:
            if judge.groundedness == 1 or judge.unsupported_claims:
                severity = Severity.SEV1 if judge.groundedness == 1 else Severity.SEV2
                events.append(
                    _answer_event(
                        "ANSWER.UNGROUNDED_CLAIM",
                        severity,
                        case,
                        observed={"unsupported_claims": list(judge.unsupported_claims)},
                        action="verify M2 first, then tighten prompt/context use and claim generation",
                    )
                )
            if min(judge.groundedness, judge.relevance, judge.completeness) < 3:
                events.append(
                    _answer_event(
                        "ANSWER.QUALITY_BELOW_PASS",
                        Severity.SEV2,
                        case,
                        observed={
                            "groundedness": judge.groundedness,
                            "relevance": judge.relevance,
                            "completeness": judge.completeness,
                        },
                        expected={"minimum": 3},
                        action="optimize only the failed answer-quality dimension after M2 passes",
                    )
                )
            if case.difficulty.value == "D4" and (
                judge.refusal_correctness < 3 or not refusal_marker
            ):
                events.append(
                    _answer_event(
                        "ANSWER.REFUSAL_INCORRECT",
                        Severity.SEV2,
                        case,
                        observed={
                            "refusal_correctness": judge.refusal_correctness,
                            "refusal_marker_present": refusal_marker,
                        },
                        expected={"minimum": 3, "refusal_marker_present": True},
                        action="repair no-evidence, clarification, and free-supplement branches",
                    )
                )
        return AnswerEvaluation(
            judge=judge,
            citation_names=citations,
            citation_validity=citation_validity,
            refusal_marker_present=refusal_marker,
            events=tuple(_deduplicate_events(events)),
        )

    def _invoke_answer_with_retry(self, payload: Mapping[str, object]) -> JudgeResult:
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                return self._invoke_answer(payload)
            except Exception as error:
                last_error = error
        assert last_error is not None
        raise last_error

    def evaluate_answer_pair(
        self,
        case: EvalCase,
        *,
        stream_answer: str,
        sync_answer: str,
        context: str,
    ) -> PairJudgeResult:
        payload = {
            "query": case.query,
            "expected_intents": list(case.expected_intents),
            "context": context,
            "stream_answer": stream_answer,
            "sync_answer": sync_answer,
        }
        messages = [
            SystemMessage(
                content=(
                    "Compare two answers to the same query and context. Ignore wording, style, and length. "
                    "Set equivalent=false only for contradictions in entity, numeric facts, or requested-intent "
                    "conclusions. Return JSON with schema_version=rag_pair_judge.v1, equivalent, "
                    "contradictions, and reason."
                )
            ),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        ]
        raw = _response_text(self.client.invoke(messages))
        parsed = _parse_json_object(raw)
        if parsed.get("schema_version") != "rag_pair_judge.v1":
            raise ValueError("pair judge schema_version must be rag_pair_judge.v1")
        equivalent = parsed.get("equivalent")
        if type(equivalent) is not bool:
            raise ValueError("pair judge equivalent must be boolean")
        contradictions = _strings(parsed.get("contradictions"))
        events: tuple[EvaluationEvent, ...] = ()
        if not equivalent:
            events = (
                _answer_event(
                    "ANSWER.SYNC_STREAM_DIVERGENCE",
                    Severity.SEV2,
                    case,
                    observed={"contradictions": list(contradictions)},
                    action="inspect nondeterministic planning/context and answer conclusions",
                ),
            )
        return PairJudgeResult(
            equivalent=equivalent,
            contradictions=contradictions,
            reason=str(parsed.get("reason") or ""),
            prompt_version=PAIR_PROMPT_VERSION,
            events=events,
        )

    def _invoke_answer(self, payload: Mapping[str, object]) -> JudgeResult:
        messages = [
            SystemMessage(content=_ANSWER_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        ]
        raw = _response_text(self.client.invoke(messages))
        try:
            parsed = _parse_json_object(raw)
            return JudgeResult.from_payload(parsed, prompt_version=self.config.prompt_version)
        except ValueError as error:
            repair_messages = [
                *messages,
                HumanMessage(
                    content=(
                        "Your previous response failed JSON/schema validation: "
                        f"{error}. Return only one JSON object that matches schema_version "
                        "rag_judge.v1. All four scores must be integers from 1 through 5."
                    )
                ),
            ]
            raw = _response_text(self.client.invoke(repair_messages))
            parsed = _parse_json_object(raw)
            try:
                return JudgeResult.from_payload(parsed, prompt_version=self.config.prompt_version)
            except ValueError:
                return JudgeResult.from_payload(
                    _normalize_integral_scores(parsed),
                    prompt_version=self.config.prompt_version,
                )


_ANSWER_SYSTEM_PROMPT = """Evaluate only the supplied query, expected task, retrieved context, operational metadata, and answer.
Do not use outside game knowledge. A fact that may be true but is absent from the context is ungrounded.
Operational metadata is authoritative for attached media IDs, types, and titles and for offered recovery actions; it is not entity lore evidence.
The source identity metadata is authoritative for classifying and attributing each retrieved source, including its entity type and owner; it is not additional lore evidence.
For conversation cases, expected entity metadata resolves pronouns and identifies the expected answer subject; it is task metadata, not additional lore evidence.
Equivalent human-readable labels translated directly from an attached media type or filename prefix are supported when they add no new property or lore claim.
When an answer mentions attached media, a nearby S citation may support the entity identity while operational media metadata supports the attached file fields; this does not mean the cited text source contains those media fields unless the answer explicitly claims it does.
Paginated voice media need not be enumerated in the prose answer. Do not penalize completeness when the answer truthfully says the complete voice set is available through pagination and only summarizes cited text rows.
Judge completeness only against the user's requested scope and expected intents, not against every unrelated field present in the retrieved context. Do not invent extra requirements from context breadth.
Interpret expected_behavior as a grading contract. For insufficient_evidence, reject_false_premise, or no_fabrication, a concise non-fabricating refusal or clarification is relevant and complete when the context lacks the requested evidence. Do not penalize it for omitting an unsupported substantive answer.
For partial_answer, give full completeness credit when the answer covers supported intents and explicitly identifies each unsupported intent; do not require invented content for the missing part.
For clarify_or_failure_action, a concise request for the missing entity or scope, or a truthful response accompanied by recovery actions, is complete and has correct refusal behavior.
Score groundedness, relevance, completeness, and refusal_correctness from 1 to 5.
Return JSON only with schema_version=rag_judge.v1, the four integer scores, unsupported_claims,
missing_requirements, reason, and passed. List exact unsupported claims and missing requirements.
Do not reward style or length."""


def _project_fields(
    item: Mapping[str, object],
    fields: Iterable[str],
) -> dict[str, object]:
    return {field: item[field] for field in fields if field in item and item[field] is not None}


def _normalize_integral_scores(payload: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    for field in ("groundedness", "relevance", "completeness", "refusal_correctness"):
        value = normalized.get(field)
        if type(value) is float and math.isfinite(value) and value.is_integer():
            normalized[field] = int(value)
    return normalized


def _parse_json_object(value: str) -> dict[str, object]:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("judge response must be a JSON object")
    return payload


def _response_text(response: object) -> str:
    value = getattr(response, "content", response)
    if not isinstance(value, str):
        raise ValueError("judge response content must be a string")
    if len(value.encode("utf-8")) > 256 * 1024:
        raise ValueError("judge response exceeded byte limit")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item))


def _extract_citations(answer: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_CITATION_RE.findall(answer)))


def _answer_event(
    code: str,
    severity: Severity,
    case: EvalCase,
    *,
    observed: Mapping[str, object] | None = None,
    expected: Mapping[str, object] | None = None,
    action: str,
) -> EvaluationEvent:
    return EvaluationEvent.create(
        code,
        "M3",
        severity,
        case_ids=(case.case_id,),
        observed=observed,
        expected=expected,
        recommended_action=action,
    )


def _deduplicate_events(events: Iterable[EvaluationEvent]) -> list[EvaluationEvent]:
    output: list[EvaluationEvent] = []
    seen: set[str] = set()
    for event in events:
        if event.event_code not in seen:
            output.append(event)
            seen.add(event.event_code)
    return output
