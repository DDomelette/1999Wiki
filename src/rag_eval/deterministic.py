"""Deterministic M1, M2, M4, and M5 evaluation rules."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

from src.rag_eval.client import ObservedExchange
from src.rag_eval.contracts import (
    EvalCase,
    EvaluationEvent,
    Severity,
    Thresholds,
    worst_severity,
)
from src.rag_eval.inventory import EvaluationInventory, MediaRecord


_MEDIA_INTENTS = frozenset({"voice", "media", "video"})


@dataclass(frozen=True)
class DeterministicResult:
    module_scores: Mapping[str, float]
    metrics: Mapping[str, object]
    events: tuple[EvaluationEvent, ...]

    @property
    def severity(self) -> Severity:
        return worst_severity([event.severity for event in self.events])


@dataclass(frozen=True)
class ReliabilityResult:
    score: float
    metrics: Mapping[str, float]
    events: tuple[EvaluationEvent, ...]

    @property
    def severity(self) -> Severity:
        return worst_severity([event.severity for event in self.events])


def recall_at_k(
    ranked_ids: Sequence[str],
    relevant: Mapping[str, float] | Iterable[str],
    k: int,
) -> float:
    relevant_ids = set(relevant)
    if not relevant_ids:
        return 1.0
    return len(set(ranked_ids[: max(0, k)]) & relevant_ids) / len(relevant_ids)


def mrr(
    ranked_ids: Sequence[str],
    relevant: Mapping[str, float] | Iterable[str],
) -> float:
    relevant_ids = set(relevant)
    if not relevant_ids:
        return 1.0
    for rank, item in enumerate(ranked_ids, start=1):
        if item in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    ranked_ids: Sequence[str],
    relevant: Mapping[str, float] | Iterable[str],
    k: int,
) -> float:
    relevance = (
        {str(key): float(value) for key, value in relevant.items()}
        if isinstance(relevant, Mapping)
        else {str(key): 1.0 for key in relevant}
    )
    if not relevance:
        return 1.0

    def dcg(gains: Sequence[float]) -> float:
        return sum((2.0**gain - 1.0) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))

    actual = [relevance.get(item, 0.0) for item in ranked_ids[: max(0, k)]]
    ideal = sorted(relevance.values(), reverse=True)[: max(0, k)]
    ideal_score = dcg(ideal)
    return dcg(actual) / ideal_score if ideal_score else 1.0


def evaluate_deterministic(
    case: EvalCase,
    exchange: ObservedExchange,
    inventory: EvaluationInventory,
    thresholds: Thresholds,
    *,
    parity_exchange: ObservedExchange | None = None,
) -> DeterministicResult:
    retrieval_score, retrieval_metrics, retrieval_events = _evaluate_retrieval(
        case, exchange, inventory
    )
    media_score, media_metrics, media_events = _evaluate_media(
        case, exchange, inventory, parity_exchange
    )
    reliability_score, reliability_metrics, reliability_events = _evaluate_exchange_reliability(
        exchange, thresholds
    )
    route_events = _evaluate_route_contract(case, exchange)
    citation_events = _evaluate_citation_contract(case, exchange)
    trace_events = _evaluate_stage_trace(case, exchange)
    parity_events = _evaluate_packet_parity(case, exchange, parity_exchange)
    scores: dict[str, float] = {
        "M2": retrieval_score,
        "M5": reliability_score,
    }
    if (
        case.scenario in {"media", "hybrid"}
        or bool(set(case.expected_intents) & _MEDIA_INTENTS)
        or media_events
        or exchange.media
        or exchange.media_panels
    ):
        scores["M4"] = media_score
    return DeterministicResult(
        module_scores=scores,
        metrics={
            "M2": retrieval_metrics,
            "M4": media_metrics,
            "M5": reliability_metrics,
        },
        events=tuple((
            *retrieval_events,
            *media_events,
            *route_events,
            *citation_events,
            *reliability_events,
            *trace_events,
            *parity_events,
        )),
    )


def evaluate_reliability(
    exchanges: Sequence[ObservedExchange],
    thresholds: Thresholds,
    *,
    repeat_pairs: Sequence[tuple[ObservedExchange, ObservedExchange]] = (),
) -> ReliabilityResult:
    total = len(exchanges)
    successes = sum(exchange.success for exchange in exchanges)
    success_rate = successes / total if total else 0.0
    retrieval_values = [
        exchange.timing.retrieval_ms
        for exchange in exchanges
        if exchange.timing.retrieval_ms is not None
    ]
    ttft_values = [
        exchange.timing.ttft_ms
        for exchange in exchanges
        if exchange.timing.ttft_ms is not None
    ]
    total_values = [exchange.timing.total_ms for exchange in exchanges]
    metrics = {
        "success_rate": success_rate,
        "retrieval_p95_ms": _percentile(retrieval_values, 0.95),
        "ttft_p95_ms": _percentile(ttft_values, 0.95),
        "total_p95_ms": _percentile(total_values, 0.95),
        "repeat_consistency_rate": 1.0,
    }
    events: list[EvaluationEvent] = []
    minimum = float(thresholds.reliability["success_rate_min"])
    if total == 0 or successes == 0:
        events.append(
            _event(
                "RELY.MAIN_PATH_UNAVAILABLE",
                "M5",
                Severity.SEV0,
                observed={"success_rate": success_rate},
                expected={"minimum": minimum},
                action="restore the answer path before quality evaluation",
            )
        )
    elif success_rate < minimum:
        events.append(
            _event(
                "RELY.SUCCESS_RATE_BELOW_MINIMUM",
                "M5",
                Severity.SEV2,
                observed={"success_rate": success_rate},
                expected={"minimum": minimum},
                action="group request failures by stage and repair the dominant cause",
            )
        )
    exceeded = {
        key: value
        for key, value in metrics.items()
        if key.endswith("_p95_ms")
        and value > float(thresholds.reliability[key])
    }
    if exceeded:
        events.append(
            _event(
                "RELY.P95_LATENCY_EXCEEDED",
                "M5",
                Severity.SEV2,
                observed=exceeded,
                expected={key: thresholds.reliability[key] for key in exceeded},
                action="optimize only the stage whose P95 exceeded its fixed threshold",
            )
        )
    repeat_failures = []
    for original, repeated in repeat_pairs:
        difference = _repeat_diff(original, repeated)
        if difference:
            repeat_failures.append(
                {
                    "original_case_id": original.case_id,
                    "repeat_case_id": repeated.case_id,
                    "difference": difference,
                }
            )
    repeat_rate = (
        1.0 - len(repeat_failures) / len(repeat_pairs)
        if repeat_pairs
        else 1.0
    )
    metrics["repeat_consistency_rate"] = repeat_rate
    if repeat_failures:
        events.append(
            _event(
                "RELY.REPEAT_DIVERGENCE",
                "M5",
                Severity.SEV2,
                case_ids=tuple(
                    item["repeat_case_id"] for item in repeat_failures
                ),
                observed={"pairs": repeat_failures},
                expected={"repeat_consistency_rate": 1.0},
                action="inspect planner nondeterminism, ranking tie-breaks, and external state drift",
            )
        )
    score = max(
        0.0,
        success_rate * 100.0
        - (20.0 if exceeded else 0.0)
        - (20.0 if repeat_failures else 0.0),
    )
    return ReliabilityResult(score=score, metrics=metrics, events=tuple(events))


def _evaluate_retrieval(
    case: EvalCase,
    exchange: ObservedExchange,
    inventory: EvaluationInventory,
) -> tuple[float, dict[str, object], list[EvaluationEvent]]:
    events: list[EvaluationEvent] = []
    route_entity = str(exchange.route.get("entity") or "")
    expected_entity_names = {
        inventory.entities[entity_id].entity_name
        for entity_id in case.expected_entity_ids
        if entity_id in inventory.entities
    }
    entity_ok = not expected_entity_names or route_entity in expected_entity_names
    if not entity_ok:
        events.append(
            _event(
                "RETR.WRONG_ENTITY",
                "M2",
                Severity.SEV2,
                case=case,
                observed={"entity": route_entity},
                expected={"entities": sorted(expected_entity_names)},
                action="inspect entity lexicon, aliases, and Stage 0 fallback",
            )
        )

    requested = _route_intents(exchange.route)
    expected_intents = set(case.expected_intents)
    intent_intersection = expected_intents & set(requested)
    if expected_intents:
        intent_recall = len(intent_intersection) / len(expected_intents)
        intent_precision = (
            len(intent_intersection) / len(set(requested)) if requested else 0.0
        )
        intent_f1 = (
            2.0 * intent_precision * intent_recall / (intent_precision + intent_recall)
            if intent_precision + intent_recall
            else 0.0
        )
    else:
        intent_f1 = 1.0
    if not expected_intents.issubset(set(requested)):
        events.append(
            _event(
                "RETR.INTENT_LOSS",
                "M2",
                Severity.SEV2,
                case=case,
                observed={"requested_intents": requested},
                expected={"expected_intents": list(case.expected_intents)},
                action="inspect planner schema and downstream policy composition",
            )
        )

    ranked_ids = [str(source.get("child_id") or "") for source in exchange.sources]
    cross_entity: list[str] = []
    cross_ownership_keys: list[tuple[str, str]] = []
    allowed_entities = set(case.expected_entity_ids)
    expected_owner = case.expected_ownership_key
    if allowed_entities or expected_owner:
        for source, child_id in zip(exchange.sources, ranked_ids, strict=True):
            child = inventory.children.get(child_id)
            owner = _row_ownership_key(source)
            if owner is None and child is not None:
                owner = (child.entity_type, child.entity_id)
            if expected_owner is not None and owner is not None and owner != expected_owner:
                cross_entity.append(child_id)
                cross_ownership_keys.append(owner)
            elif child is not None and allowed_entities and child.entity_id not in allowed_entities:
                cross_entity.append(child_id)
                cross_ownership_keys.append((child.entity_type, child.entity_id))
    if cross_entity:
        events.append(
            _event(
                "RETR.CROSS_ENTITY_SOURCE",
                "M2",
                Severity.SEV1,
                case=case,
                observed={
                    "child_ids": cross_entity,
                    "ownership_keys": [list(value) for value in dict.fromkeys(cross_ownership_keys)],
                },
                expected={
                    "entity_ids": sorted(allowed_entities),
                    "ownership_key": list(expected_owner) if expected_owner else None,
                },
                action="stop score tuning and inspect entity filtering and parent ownership",
            )
        )

    debug = exchange.route.get("retrieval_debug")
    debug = debug if isinstance(debug, Mapping) else {}
    expected_shortfall = (
        case.expected_retrieval_outcome in {"empty", "partial"}
        or (
            case.expected_behavior == "insufficient_evidence"
            and case.allow_no_sources
        )
    )
    qrels = case.source_relevance or {source_id: 1.0 for source_id in case.expected_source_ids}
    required_source_count = debug.get("required_source_count")
    recall_capacity = (
        int(required_source_count)
        if type(required_source_count) is int and required_source_count > 0
        else len(qrels)
    )
    relevant_seen = len(set(ranked_ids) & set(qrels))
    recall_denominator = min(len(qrels), recall_capacity) if qrels else 0
    recall = (
        min(1.0, relevant_seen / recall_denominator)
        if recall_denominator
        else 1.0
    )
    reciprocal_rank = mrr(ranked_ids, qrels)
    ndcg = ndcg_at_k(ranked_ids, qrels, len(ranked_ids))
    if qrels and recall < 1.0:
        events.append(
            _event(
                "RETR.QREL_MISS",
                "M2",
                Severity.SEV3,
                case=case,
                observed={"recall": recall, "ranked_ids": ranked_ids},
                expected={"source_ids": sorted(qrels)},
                action="inspect sparse/dense queries, filters, candidate K, and reranking",
            )
        )

    shortfall = debug.get("coverage_shortfall") if isinstance(debug, Mapping) else {}
    positive_shortfall = {
        str(key): int(value)
        for key, value in (shortfall.items() if isinstance(shortfall, Mapping) else ())
        if isinstance(value, int) and value > 0 and key in expected_intents
    }
    if positive_shortfall and not expected_shortfall:
        events.append(
            _event(
                "RETR.BUDGET_SHORTFALL",
                "M2",
                Severity.SEV2,
                case=case,
                observed={"coverage_shortfall": positive_shortfall},
                expected={"coverage_shortfall": {key: 0 for key in positive_shortfall}},
                action="inspect intent quotas and source/character budget allocation",
            )
        )

    if not exchange.sources and not case.allow_no_sources and not exchange.failure_actions:
        events.append(
            _event(
                "RETR.NO_SOURCES_WITHOUT_ACTION",
                "M2",
                Severity.SEV2,
                case=case,
                action="return truthful failure actions when retrieval is empty",
            )
        )

    coverage = (
        1.0
        if expected_shortfall
        else _source_intent_coverage(case, ranked_ids, inventory)
    )
    score = (
        (20.0 if entity_ok else 0.0)
        + 25.0 * intent_f1
        + 30.0 * recall
        + 15.0 * ndcg
        + 10.0 * coverage
    )
    return score, {
        "entity_accuracy": float(entity_ok),
        "intent_f1": intent_f1,
        "recall_at_k": recall,
        "mrr": reciprocal_rank,
        "ndcg_at_k": ndcg,
        "intent_coverage": coverage,
        "coverage_shortfall": positive_shortfall,
    }, events


def _evaluate_media(
    case: EvalCase,
    exchange: ObservedExchange,
    inventory: EvaluationInventory,
    parity: ObservedExchange | None,
) -> tuple[float, dict[str, object], list[EvaluationEvent]]:
    events: list[EvaluationEvent] = []
    transport_payload = {
        "route": exchange.route,
        "sources": exchange.sources,
        "media": exchange.media,
        "media_panels": exchange.media_panels,
        "voice_pages": exchange.voice_pages,
    }
    if _contains_local_path(transport_payload):
        events.append(
            _event(
                "MEDIA.LOCAL_PATH_LEAK",
                "M4",
                Severity.SEV1,
                case=case,
                action="inspect response schemas, sanitization, and public URL construction",
            )
        )

    top_media = list(exchange.media)
    panel_media = _panel_media(exchange.voice_pages or exchange.media_panels)
    observed_media = [*top_media, *panel_media]
    observed_ids = [str(item.get("media_id") or item.get("asset_id") or "") for item in observed_media]
    expected_ids = set(case.expected_media_ids)
    observed_set = {item for item in observed_ids if item}
    binding_failures: list[dict[str, str]] = []
    allowed_entities = set(case.expected_entity_ids)
    expected_owner = case.expected_ownership_key
    cross_media: list[dict[str, object]] = []
    for item in observed_media:
        media_id = str(item.get("media_id") or item.get("asset_id") or "")
        owner = _row_ownership_key(item)
        if owner is None:
            child = inventory.children.get(str(item.get("child_id") or ""))
            if child is not None:
                owner = (child.entity_type, child.entity_id)
        if expected_owner is not None and owner is not None and owner != expected_owner:
            cross_media.append({"media_id": media_id, "ownership_key": list(owner)})
        if not media_id or media_id not in inventory.media:
            continue
        child_id = str(item.get("child_id") or "")
        occurrences = inventory.media[media_id]
        matching = [occurrence for occurrence in occurrences if occurrence.child_id == child_id]
        if child_id and not matching:
            binding_failures.append({"media_id": media_id, "child_id": child_id})
            continue
        candidates = matching or list(occurrences)
        if allowed_entities and not any(item.entity_id in allowed_entities for item in candidates):
            binding_failures.append({"media_id": media_id, "child_id": child_id})
    if cross_media:
        events.append(
            _event(
                "MEDIA.CROSS_ENTITY_MEDIA",
                "M4",
                Severity.SEV1,
                case=case,
                observed={"media": cross_media},
                expected={"ownership_key": list(expected_owner) if expected_owner else None},
                action="inspect media ownership filtering before packet serialization",
            )
        )
    if binding_failures:
        events.append(
            _event(
                "MEDIA.WRONG_CHILD_BINDING",
                "M4",
                Severity.SEV1,
                case=case,
                observed={"bindings": binding_failures},
                expected={"entity_ids": sorted(allowed_entities)},
                action="inspect build-time media-to-child binding; do not mask it in pagination",
            )
        )

    media_types = {_media_type(item) for item in observed_media}
    forbidden = set(case.forbidden_media_types) & media_types
    if forbidden:
        events.append(
            _event(
                "MEDIA.FORBIDDEN_TYPE",
                "M4",
                Severity.SEV1 if "voice" in forbidden else Severity.SEV2,
                case=case,
                observed={"media_types": sorted(media_types)},
                expected={"forbidden": sorted(case.forbidden_media_types)},
                action="inspect media-intent policy and registry filtering",
            )
        )

    allowed_types = _allowed_media_types(case.expected_intents)
    unexpected_types = media_types - allowed_types if case.expected_intents else set()
    if unexpected_types:
        events.append(
            _event(
                "MEDIA.UNEXPECTED_TYPE",
                "M4",
                Severity.SEV2,
                case=case,
                observed={"media_types": sorted(media_types)},
                expected={"allowed_media_types": sorted(allowed_types)},
                action="inspect requested intent normalization and media policy composition",
            )
        )

    voice_contract = "voice" in case.expected_intents
    if voice_contract:
        media_recall = len(expected_ids & observed_set) / len(expected_ids) if expected_ids else 1.0
        media_precision = (
            len(expected_ids & observed_set) / len(observed_set)
            if observed_set
            else (1.0 if not expected_ids else 0.0)
        )
    else:
        expected_available = bool(expected_ids)
        observed_available = bool(observed_set)
        media_recall = 1.0 if not expected_available or observed_available else 0.0
        contract_failures = bool(
            forbidden or unexpected_types or cross_media or binding_failures
        )
        media_precision = 0.0 if contract_failures else 1.0
        if expected_available and not observed_available:
            events.append(
                _event(
                    "MEDIA.EXPECTED_MEDIA_MISSING",
                    "M4",
                    Severity.SEV2,
                    case=case,
                    expected={"available_media_count": len(expected_ids)},
                    action="inspect source-to-media binding and the non-voice first-page budget",
                )
            )
        if (
            case.expected_behavior == "insufficient_evidence"
            and not expected_available
            and not case.expected_source_ids
            and not exchange.sources
            and observed_available
        ):
            events.append(
                _event(
                    "MEDIA.UNEXPECTED_ATTACHMENT",
                    "M4",
                    Severity.SEV2,
                    case=case,
                    observed={"media_ids": sorted(observed_set)},
                    expected={"media_ids": []},
                    action="inspect media intent filtering for no-evidence requests",
                )
            )
            media_precision = 0.0
    page_ok = True
    if "voice" in case.expected_intents:
        page_events = _evaluate_voice_pages(case, exchange, inventory)
        events.extend(page_events)
        page_ok = not page_events

    parity_ok = True
    if parity is not None:
        parity_diff = _parity_diff(exchange, parity)
        if parity_diff:
            parity_ok = False
    score = 40.0 * media_recall + 20.0 * media_precision + (25.0 if page_ok else 0.0) + (15.0 if parity_ok else 0.0)
    return score, {
        "media_recall": media_recall,
        "media_precision": media_precision,
        "page_set_equal": page_ok,
        "sync_stream_contract_equal": parity_ok,
    }, events


def _evaluate_voice_pages(
    case: EvalCase,
    exchange: ObservedExchange,
    inventory: EvaluationInventory,
) -> list[EvaluationEvent]:
    pages = list(exchange.voice_pages or [panel for panel in exchange.media_panels if panel.get("type") == "voice"])
    if not pages:
        return [
            _event(
                "MEDIA.VOICE_PAGES_MISSING",
                "M4",
                Severity.SEV2,
                case=case,
                action="inspect voice bundle generation and pagination endpoint",
            )
        ]
    line_ids: list[str] = []
    media_ids: list[str] = []
    for page in pages:
        for line in page.get("lines") or ():
            if not isinstance(line, Mapping):
                continue
            line_ids.append(str(line.get("voice_line_id") or ""))
            for variant in line.get("variants") or ():
                if isinstance(variant, Mapping):
                    media_ids.append(str(variant.get("media_id") or ""))
    allowed_entities = set(case.expected_entity_ids)
    expected_media: set[str] = set()
    expected_lines: set[str] = set()
    for media_id in case.expected_media_ids:
        voice_occurrences = [
            occurrence
            for occurrence in inventory.media.get(media_id, ())
            if (not allowed_entities or occurrence.entity_id in allowed_entities)
            and (occurrence.asset_type == "voice" or occurrence.mime.lower().startswith("audio/"))
        ]
        if voice_occurrences:
            expected_media.add(media_id)
            expected_lines.update(occurrence.child_id for occurrence in voice_occurrences)
    failures: dict[str, object] = {}
    if set(media_ids) != expected_media:
        failures["media_set"] = {"observed": sorted(set(media_ids)), "expected": sorted(expected_media)}
    if set(line_ids) != expected_lines:
        failures["line_set"] = {"observed": sorted(set(line_ids)), "expected": sorted(expected_lines)}
    if len(media_ids) != len(set(media_ids)):
        failures["duplicate_media_ids"] = sorted(_duplicates(media_ids))
    if len(line_ids) != len(set(line_ids)):
        failures["duplicate_line_ids"] = sorted(_duplicates(line_ids))
    total_lines = int(pages[0].get("total_lines") or 0)
    if total_lines != len(expected_lines):
        failures["total_lines"] = {"observed": total_lines, "expected": len(expected_lines)}
    if not failures:
        return []
    return [
        _event(
            "MEDIA.VOICE_PAGE_SET_MISMATCH",
            "M4",
            Severity.SEV2,
            case=case,
            observed=failures,
            action="inspect stable line ordering, cursor state, and page union construction",
        )
    ]


def _evaluate_exchange_reliability(
    exchange: ObservedExchange,
    thresholds: Thresholds,
) -> tuple[float, dict[str, object], list[EvaluationEvent]]:
    events: list[EvaluationEvent] = []
    if not exchange.success:
        events.append(
            _event(
                "RELY.REQUEST_FAILED",
                "M5",
                Severity.SEV2,
                case_ids=(exchange.case_id,),
                observed={"error": exchange.error, "status_code": exchange.status_code},
                action="classify the failure by planning, retrieval, model, or protocol stage",
            )
        )
        return 0.0, {"success": False}, events
    exceeded = {
        "retrieval_ms": exchange.timing.retrieval_ms is not None
        and exchange.timing.retrieval_ms > thresholds.reliability["retrieval_p95_ms"],
        "ttft_ms": exchange.timing.ttft_ms is not None
        and exchange.timing.ttft_ms > thresholds.reliability["ttft_p95_ms"],
        "total_ms": exchange.timing.total_ms > thresholds.reliability["total_p95_ms"],
    }
    score = 100.0 - 10.0 * sum(bool(value) for value in exceeded.values())
    return score, {"success": True, "single_request_threshold_exceeded": exceeded}, events


def _evaluate_route_contract(
    case: EvalCase,
    exchange: ObservedExchange,
) -> list[EvaluationEvent]:
    route = exchange.route
    events: list[EvaluationEvent] = []
    effective = str(route.get("effective_route") or route.get("name") or "")
    outcome = str(route.get("retrieval_outcome") or "")
    force = str(case.action_payload.get("action_type") or "") == "force_free_supplement"
    toggle = case.route_options.get("free_supplement") is True
    general_allowed = force or (toggle and outcome == "empty")
    if effective == "llm_general" and not general_allowed:
        events.append(
            _event(
                "ROUTE.UNAUTHORIZED_GENERAL",
                "M2",
                Severity.SEV1,
                case=case,
                observed={"effective_route": effective, "retrieval_outcome": outcome},
                expected={"free_supplement": toggle, "force_free_supplement": force},
                action="inspect route authorization; Planner proposals must not bypass the user gate",
            )
        )
    observed_intents = exchange.semantic_intents or _route_intents(route)
    if case.expected_intents and not set(case.expected_intents).issubset(observed_intents):
        events.append(
            _event(
                "ROUTE.INTENT_OVERWRITTEN",
                "M2",
                Severity.SEV2,
                case=case,
                observed={"semantic_intents": list(observed_intents)},
                expected={"semantic_intents": list(case.expected_intents)},
                action="preserve semantic intents independently from execution route selection",
            )
        )
    route_mismatch = bool(
        case.expected_effective_route and effective != case.expected_effective_route
    )
    outcome_mismatch = bool(
        case.expected_retrieval_outcome and outcome != case.expected_retrieval_outcome
    )
    if route_mismatch or outcome_mismatch:
        if not any(event.event_code == "ROUTE.UNAUTHORIZED_GENERAL" for event in events):
            events.append(
                _event(
                    "ROUTE.DECISION_MISMATCH",
                    "M2",
                    Severity.SEV2,
                    case=case,
                    observed={"effective_route": effective, "retrieval_outcome": outcome},
                    expected={
                        "effective_route": case.expected_effective_route,
                        "retrieval_outcome": case.expected_retrieval_outcome,
                    },
                    action="inspect retrieval outcome classification and route finalization",
                )
            )
    return events


_SHORT_CITATION_RE = re.compile(r"\[(S\d{2,})\]")


def _evaluate_citation_contract(
    case: EvalCase,
    exchange: ObservedExchange,
) -> list[EvaluationEvent]:
    known_ids = set(exchange.source_map) or {
        str(source.get("citation_id") or "")
        for source in exchange.sources
        if source.get("citation_id")
    }
    used_ids = tuple(dict.fromkeys(_SHORT_CITATION_RE.findall(exchange.answer)))
    invalid_ids = tuple(value for value in used_ids if value not in known_ids)
    warning = str(exchange.raw.get("citation_warning") or "")
    events: list[EvaluationEvent] = []
    if invalid_ids:
        events.append(
            _event(
                "CITE.UNKNOWN_OR_STALE_ID",
                "M3",
                Severity.SEV1,
                case=case,
                observed={"invalid_ids": list(invalid_ids)},
                expected={"source_ids": sorted(known_ids)},
                action="block transport and validate every short citation against this response source map",
            )
        )
    if invalid_ids and "invalid_citation" in warning:
        events.append(
            _event(
                "CITE.INVALID_DRAFT_TRANSPORTED",
                "M3",
                Severity.SEV1,
                case=case,
                observed={"citation_warning": warning, "invalid_ids": list(invalid_ids)},
                action="return only repaired output or a safe fallback, never the invalid draft",
            )
        )
    if (
        "citation_validation_failed" in warning
        or "citation_safe_fallback" in warning
    ):
        events.append(
            _event(
                "CITE.SAFE_FALLBACK_USED",
                "M3",
                Severity.SEV2,
                case=case,
                observed={"citation_warning": warning},
                action="inspect citation repair inputs while retaining the safe fallback",
            )
        )
    return events


_BASE_REQUIRED_STAGE_NAMES = frozenset(
    {
        "planner.normalize",
        "route.resolve",
        "source_map.build",
        "media.attach",
        "response.serialize",
        "memory.acquire",
    }
)


def _evaluate_stage_trace(
    case: EvalCase,
    exchange: ObservedExchange,
) -> list[EvaluationEvent]:
    if not exchange.success:
        return []
    stage_value = exchange.stage_trace.get("stage_ms")
    stage_ms = stage_value if isinstance(stage_value, Mapping) else exchange.timing.stage_ms
    available = set(stage_ms)
    decision = exchange.route_decision
    outcome = str(decision.get("retrieval_outcome") or "")
    effective = str(decision.get("effective_route") or "")
    route_reason = str(decision.get("route_reason") or "")
    required = set(_BASE_REQUIRED_STAGE_NAMES)
    if effective == "llm_general" or outcome in {"sufficient", "partial"}:
        required.update({"answer.llm", "citation.validate"})
    missing = sorted(required - available)
    if (
        route_reason != "explicit_recovery_action"
        and not any(name.startswith("retrieval.") for name in available)
    ):
        missing.append("retrieval.*")
    if not missing:
        return []
    return [
        _event(
            "RELY.STAGE_SPAN_INCOMPLETE",
            "M5",
            Severity.SEV2,
            case=case,
            observed={"missing_stages": missing, "available_stages": sorted(available)},
            action="restore stage instrumentation before using latency evidence for acceptance",
        )
    ]


def _evaluate_packet_parity(
    case: EvalCase,
    primary: ObservedExchange,
    parity: ObservedExchange | None,
) -> list[EvaluationEvent]:
    if parity is None:
        return []
    difference = _parity_diff(primary, parity)
    if not difference:
        return []
    return [
        _event(
            "RELY.SYNC_STREAM_PACKET_DIVERGENCE",
            "M5",
            Severity.SEV2,
            case=case,
            observed=difference,
            action="serialize both transports from the same frozen response packet",
        )
    ]


def _source_intent_coverage(
    case: EvalCase,
    ranked_ids: Sequence[str],
    inventory: EvaluationInventory,
) -> float:
    if not case.expected_intents:
        return 1.0
    covered = 0
    for intent in case.expected_intents:
        if any(
            child_id in inventory.children
            and (
                intent in inventory.children[child_id].route_tags
                or child_id in case.expected_source_ids
            )
            for child_id in ranked_ids
        ):
            covered += 1
    return covered / len(case.expected_intents)


def _route_intents(route: Mapping[str, object]) -> tuple[str, ...]:
    requested = route.get("semantic_intents") or route.get("requested_intents")
    if isinstance(requested, list):
        return tuple(dict.fromkeys(str(item) for item in requested if str(item)))
    intent = str(route.get("intent") or "")
    return (intent,) if intent else ()


def _panel_media(panels: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    values: list[Mapping[str, object]] = []
    for panel in panels:
        for line in panel.get("lines") or ():
            if isinstance(line, Mapping):
                values.extend(item for item in line.get("variants") or () if isinstance(item, Mapping))
        values.extend(item for item in panel.get("items") or () if isinstance(item, Mapping))
    return values


def _parity_diff(primary: ObservedExchange, parity: ObservedExchange) -> dict[str, object]:
    comparisons = {
        "entity_ref": (dict(primary.entity_ref), dict(parity.entity_ref)),
        "intents": (sorted(_route_intents(primary.route)), sorted(_route_intents(parity.route))),
        "route": (dict(primary.route_decision), dict(parity.route_decision)),
        "source_ids": (
            [str(item.get("child_id") or "") for item in primary.sources],
            [str(item.get("child_id") or "") for item in parity.sources],
        ),
        "citation_map": (dict(primary.source_map), dict(parity.source_map)),
        "media_ids": (
            [str(item.get("media_id") or item.get("asset_id") or "") for item in primary.media],
            [str(item.get("media_id") or item.get("asset_id") or "") for item in parity.media],
        ),
        "omitted_actions": (
            [dict(item) for item in primary.omitted_actions],
            [dict(item) for item in parity.omitted_actions],
        ),
        "failure_actions": (
            [dict(item) for item in primary.failure_actions],
            [dict(item) for item in parity.failure_actions],
        ),
        "memory": (dict(primary.memory), dict(parity.memory)),
    }
    return {
        key: {"stream": values[0], "sync": values[1]}
        for key, values in comparisons.items()
        if values[0] != values[1]
    }


def _row_ownership_key(value: Mapping[str, object]) -> tuple[str, str] | None:
    entity_type = str(value.get("entity_type") or "")
    entity_id = str(value.get("entity_id") or "")
    return (entity_type, entity_id) if entity_type and entity_id else None


def _repeat_diff(
    original: ObservedExchange,
    repeated: ObservedExchange,
) -> dict[str, object]:
    comparisons = {
        "entity": (original.route.get("entity"), repeated.route.get("entity")),
        "intents": (sorted(_route_intents(original.route)), sorted(_route_intents(repeated.route))),
        "source_ids": (
            sorted(str(item.get("child_id") or "") for item in original.sources),
            sorted(str(item.get("child_id") or "") for item in repeated.sources),
        ),
        "media_ids": (
            sorted(str(item.get("media_id") or item.get("asset_id") or "") for item in original.media),
            sorted(str(item.get("media_id") or item.get("asset_id") or "") for item in repeated.media),
        ),
        "success": (original.success, repeated.success),
    }
    return {
        key: {"original": values[0], "repeat": values[1]}
        for key, values in comparisons.items()
        if values[0] != values[1]
    }


_FORBIDDEN_PATH_KEYS = {
    "absolute_path",
    "file_path",
    "filesystem_path",
    "local_path",
    "local_relpath",
}


def _contains_local_path(value: object) -> bool:
    if isinstance(value, str):
        decoded = value
        for _ in range(8):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        lowered = decoded.lower()
        normalized = lowered.replace("\\", "/")
        return bool(
            lowered.lstrip().startswith("file:")
            or re.search(r"(?:^|[^a-z0-9])[a-z]:/", normalized)
            or "\\" in decoded
            or "/../" in normalized
            or normalized.endswith("/..")
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _FORBIDDEN_PATH_KEYS:
                return True
            if (normalized_key == "url" or normalized_key.endswith("_url")) and isinstance(item, str):
                if not _safe_http_url(item):
                    return True
            if _contains_local_path(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_local_path(item) for item in value)
    return False


def _safe_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _media_type(item: Mapping[str, object]) -> str:
    asset_type = str(item.get("asset_type") or item.get("role") or "").lower()
    mime = str(item.get("mime") or "").lower()
    if asset_type in {"voice", "audio"} or mime.startswith("audio/"):
        return "voice"
    if asset_type == "video" or mime.startswith("video/"):
        return "video"
    if mime.startswith("image/") or asset_type in {"image", "portrait", "skill", "skin", "media"}:
        return "image"
    return asset_type


def _allowed_media_types(intents: Iterable[str]) -> set[str]:
    allowed: set[str] = set()
    for intent in intents:
        if intent == "voice":
            allowed.add("voice")
        elif intent == "video":
            allowed.add("video")
        elif intent in {
            "intro",
            "profile",
            "profile_fact",
            "skill",
            "item",
            "culture",
            "media",
            "psychube",
        }:
            allowed.add("image")
    return allowed


def _duplicates(values: Iterable[str]) -> list[str]:
    return [value for value, count in Counter(values).items() if value and count > 1]


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _event(
    code: str,
    module: str,
    severity: Severity,
    *,
    case: EvalCase | None = None,
    case_ids: tuple[str, ...] = (),
    observed: Mapping[str, object] | None = None,
    expected: Mapping[str, object] | None = None,
    action: str,
) -> EvaluationEvent:
    resolved_ids = case_ids or ((case.case_id,) if case else ())
    return EvaluationEvent.create(
        code,
        module,
        severity,
        case_ids=resolved_ids,
        observed=observed,
        expected=expected,
        recommended_action=action,
    )
