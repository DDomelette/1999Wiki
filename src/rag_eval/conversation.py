"""Dynamic, inventory-derived evaluation for short-term conversation memory."""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from typing import Mapping, Sequence
from uuid import uuid4

from src.rag_eval.client import ObservedExchange, RagEvalClient
from src.rag_eval.contracts import (
    Difficulty,
    EvalCase,
    EvaluationEvent,
    Severity,
    worst_severity,
)
from src.rag_eval.inventory import EntityRecord, EvaluationInventory, reconstruct_context
from src.rag_eval.sampling import INTENT_LABELS
from src.rag.packet_policy import compose_packet_policies


class ConversationEvaluationError(ValueError):
    """Raised when inventory or observed exchanges cannot support a valid gate."""


@dataclass(frozen=True)
class ConversationTrack:
    track_id: str
    initial_entity_id: str
    initial_entity_name: str
    initial_query: str
    follow_intent: str
    follow_up_query: str
    multi_intents: tuple[str, ...]
    multi_intent_query: str
    switch_entity_id: str
    switch_entity_name: str
    switch_query: str
    derivation: Mapping[str, object]


@dataclass(frozen=True)
class ConversationTrackResult:
    track_id: str
    severity: Severity
    checks: Mapping[str, bool]
    observations: Mapping[str, object]


@dataclass(frozen=True)
class MemoryModeResult:
    mode: str
    case_id: str
    metrics: Mapping[str, object]
    observed: Mapping[str, object]


@dataclass(frozen=True)
class MemoryTripletResult:
    track_id: str
    modes: Mapping[str, MemoryModeResult]
    comparisons: Mapping[str, float]
    events: tuple[EvaluationEvent, ...]

    @property
    def severity(self) -> Severity:
        return worst_severity([event.severity for event in self.events])


_INTENT_ORDER = tuple(INTENT_LABELS)


def _supported_intents(entity: EntityRecord) -> tuple[str, ...]:
    return tuple(
        intent
        for intent in _INTENT_ORDER
        if entity.child_ids_by_intent.get(intent)
    )


def _entity_volume(entity: EntityRecord) -> int:
    children = {
        child_id
        for values in entity.child_ids_by_intent.values()
        for child_id in values
    }
    media = {
        media_id
        for values in entity.media_ids_by_type.values()
        for media_id in values
    }
    return len(children) + len(media)


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _media_ids_for_intents(
    entity: EntityRecord,
    intents: tuple[str, ...],
) -> tuple[str, ...]:
    bundle = compose_packet_policies(entity.entity_type, intents)
    return tuple(dict.fromkeys(
        media_id
        for media_type in bundle.media_types
        for media_id in entity.media_ids_by_type.get(media_type, ())
    ))


def _stratified_entities(
    eligible: Sequence[EntityRecord],
    *,
    seed: int,
    limit: int,
) -> tuple[EntityRecord, ...]:
    ordered = sorted(eligible, key=lambda item: (_entity_volume(item), item.entity_id))
    target = min(max(2, int(limit)), len(ordered))
    if target == len(ordered):
        return tuple(ordered)

    positions = (0, (len(ordered) - 1) // 2, len(ordered) - 1)
    selected: list[EntityRecord] = []
    for position in positions:
        candidate = ordered[position]
        if all(item.entity_id != candidate.entity_id for item in selected):
            selected.append(candidate)
        if len(selected) == target:
            return tuple(selected)

    remaining = [
        item
        for item in ordered
        if all(existing.entity_id != item.entity_id for existing in selected)
    ]
    random.Random(seed).shuffle(remaining)
    selected.extend(remaining[: target - len(selected)])
    return tuple(selected)


def build_conversation_tracks(
    inventory: EvaluationInventory,
    *,
    seed: int,
    limit: int = 8,
) -> tuple[ConversationTrack, ...]:
    eligible = [
        entity
        for entity in inventory.entities.values()
        if entity.entity_type == "character" and len(_supported_intents(entity)) >= 2
    ]
    if len(eligible) < 2:
        raise ConversationEvaluationError(
            "conversation evaluation requires at least two eligible character entities"
        )
    selected = _stratified_entities(eligible, seed=seed, limit=limit)
    tracks: list[ConversationTrack] = []
    for index, entity in enumerate(selected):
        intents = _supported_intents(entity)
        offset = (seed + index) % len(intents)
        rotated = (*intents[offset:], *intents[:offset])
        follow_intent = rotated[0]
        multi_intents = tuple(rotated[:2])
        switch = selected[(index + 1) % len(selected)]
        required_follow_child_ids = tuple(
            entity.child_ids_by_intent.get(follow_intent, ())
        )
        follow_child_ids = tuple(sorted(
            child_id
            for child_id, child in inventory.children.items()
            if child.entity_id == entity.entity_id
        ))
        follow_parent_ids = tuple(sorted({
            inventory.children[child_id].parent_id
            for child_id in follow_child_ids
            if child_id in inventory.children
        }))
        follow_media_ids = _media_ids_for_intents(entity, (follow_intent,))
        child_ids = tuple(dict.fromkeys(
            child_id
            for intent in multi_intents
            for child_id in entity.child_ids_by_intent.get(intent, ())
        ))
        parent_ids = tuple(sorted({
            inventory.children[child_id].parent_id
            for child_id in child_ids
            if child_id in inventory.children
        }))
        media_ids = _media_ids_for_intents(entity, multi_intents)
        identity = {
            "seed": seed,
            "inventory_sha256": inventory.sha256,
            "initial_entity_id": entity.entity_id,
            "switch_entity_id": switch.entity_id,
            "follow_intent": follow_intent,
            "multi_intents": multi_intents,
        }
        track_id = f"conversation-{_sha256_json(identity)[:16]}"
        tracks.append(ConversationTrack(
            track_id=track_id,
            initial_entity_id=entity.entity_id,
            initial_entity_name=entity.entity_name,
            initial_query=f"介绍一下{entity.entity_name}",
            follow_intent=follow_intent,
            follow_up_query=f"它的{INTENT_LABELS[follow_intent]}呢",
            multi_intents=multi_intents,
            multi_intent_query=(
                f"再说说它的{INTENT_LABELS[multi_intents[0]]}和"
                f"{INTENT_LABELS[multi_intents[1]]}"
            ),
            switch_entity_id=switch.entity_id,
            switch_entity_name=switch.entity_name,
            switch_query=f"那么{switch.entity_name}的{INTENT_LABELS[follow_intent]}呢",
            derivation={
                "inventory_sha256": inventory.sha256,
                "allowed_follow_child_ids": follow_child_ids,
                "allowed_follow_parent_ids": follow_parent_ids,
                "allowed_follow_media_ids": follow_media_ids,
                "required_follow_child_ids": required_follow_child_ids,
                "allowed_child_ids": child_ids,
                "allowed_parent_ids": parent_ids,
                "allowed_media_ids": media_ids,
                "follow_child_ids_sha256": _sha256_json(follow_child_ids),
                "follow_parent_ids_sha256": _sha256_json(follow_parent_ids),
                "follow_media_ids_sha256": _sha256_json(follow_media_ids),
                "required_follow_child_ids_sha256": _sha256_json(
                    required_follow_child_ids
                ),
                "child_ids_sha256": _sha256_json(child_ids),
                "parent_ids_sha256": _sha256_json(parent_ids),
                "media_ids_sha256": _sha256_json(media_ids),
            },
        ))
    return tuple(tracks)


def _case(track_id: str, suffix: str, query: str) -> EvalCase:
    return EvalCase(
        case_id=f"{track_id}-{suffix}",
        query=query,
        difficulty=Difficulty.D2,
        scenario="conversation",
    )


def _memory(exchange: ObservedExchange) -> Mapping[str, object]:
    if exchange.memory:
        return dict(exchange.memory)
    value = exchange.raw.get("memory") if isinstance(exchange.raw, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else {}


def _entity(exchange: ObservedExchange) -> str | None:
    value = exchange.route.get("entity")
    return value if isinstance(value, str) and value else None


def _source_names(exchange: ObservedExchange) -> set[str]:
    return {
        str(source.get("name") or "")
        for source in exchange.sources
        if source.get("name")
    }


def _same_intent_coverage(
    actual: Sequence[str],
    expected: Sequence[str],
) -> bool:
    return len(actual) == len(expected) and set(actual) == set(expected)


def _requested(exchange: ObservedExchange) -> tuple[str, ...]:
    value = exchange.route.get("requested_intents")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value if str(item))


def _entity_sources_only(exchange: ObservedExchange, entity: str) -> bool:
    names = _source_names(exchange)
    return bool(names) and names <= {entity}


def evaluate_conversation_tracks(
    client: RagEvalClient,
    tracks: Sequence[ConversationTrack],
) -> tuple[ConversationTrackResult, ...]:
    results: list[ConversationTrackResult] = []
    for track in tracks:
        conversation_id = str(uuid4())
        first = client.ask(
            _case(track.track_id, "initial", track.initial_query),
            conversation_id=conversation_id,
        )
        follow = client.ask(
            _case(track.track_id, "follow", track.follow_up_query),
            conversation_id=conversation_id,
        )
        multi = client.ask(
            _case(track.track_id, "multi", track.multi_intent_query),
            conversation_id=conversation_id,
        )
        switch = client.ask(
            _case(track.track_id, "switch", track.switch_query),
            conversation_id=conversation_id,
        )
        requested = multi.route.get("requested_intents")
        checks = {
            "initial_new": _memory(first).get("status") == "new",
            "initial_entity": _entity(first) == track.initial_entity_name,
            "follow_hit": _memory(follow).get("status") == "hit",
            "follow_entity": _entity(follow) == track.initial_entity_name,
            "follow_no_cross_entity": _source_names(follow) <= {track.initial_entity_name},
            "multi_intents": _same_intent_coverage(
                tuple(requested or ()),
                track.multi_intents,
            ),
            "switch_entity": _entity(switch) == track.switch_entity_name,
            "switch_no_old_entity": track.initial_entity_name not in _source_names(switch),
        }
        cross_leak = not checks["follow_no_cross_entity"] or not checks["switch_no_old_entity"]
        severity = (
            Severity.SEV1
            if cross_leak
            else Severity.PASS if all(checks.values()) else Severity.SEV2
        )
        results.append(ConversationTrackResult(
            track_id=track.track_id,
            severity=severity,
            checks=checks,
            observations={
                "initial_memory": dict(_memory(first)),
                "follow_memory": dict(_memory(follow)),
                "multi_requested_intents": list(requested or ()),
                "initial_entity": _entity(first),
                "follow_entity": _entity(follow),
                "switch_entity": _entity(switch),
            },
        ))
    return tuple(results)


_SHORT_CITATION_RE = re.compile(r"\[(S\d{2,})\]")


def evaluate_memory_triplets(
    client: RagEvalClient,
    judge: object,
    inventory: EvaluationInventory,
    tracks: Sequence[ConversationTrack],
) -> tuple[MemoryTripletResult, ...]:
    results: list[MemoryTripletResult] = []
    for track in tracks:
        conversation_id = str(uuid4())
        off_case = _memory_case(track, "memory_off", track.follow_up_query)
        initial_case = _memory_case(track, "memory_on_initial", track.initial_query)
        on_case = _memory_case(track, "memory_on", track.follow_up_query)
        oracle_case = _memory_case(
            track,
            "oracle_standalone",
            f"{track.initial_entity_name}的{INTENT_LABELS[track.follow_intent]}呢",
        )

        off_exchange = client.ask(off_case)
        initial_exchange = client.ask(initial_case, conversation_id=conversation_id)
        on_exchange = client.ask(on_case, conversation_id=conversation_id)
        oracle_exchange = client.ask(oracle_case)

        mode_results: dict[str, MemoryModeResult] = {}
        evaluations: dict[str, object] = {}
        events: list[EvaluationEvent] = []
        for mode, case, exchange in (
            ("memory_off", off_case, off_exchange),
            ("memory_on", on_case, on_exchange),
            ("oracle_standalone", oracle_case, oracle_exchange),
        ):
            context = reconstruct_context(inventory, exchange.sources)
            evaluation = judge.evaluate_answer(
                case,
                answer=exchange.answer,
                context=context,
                sources=exchange.sources,
                media=exchange.media,
                failure_actions=exchange.failure_actions,
            )
            evaluations[mode] = evaluation
            events.extend(tuple(getattr(evaluation, "events", ())))
            metrics = _memory_mode_metrics(track, exchange, evaluation, inventory)
            mode_results[mode] = MemoryModeResult(
                mode=mode,
                case_id=case.case_id,
                metrics=metrics,
                observed={
                    "entity_ref": dict(exchange.entity_ref),
                    "semantic_intents": list(exchange.semantic_intents),
                    "source_ids": [
                        str(source.get("child_id") or "") for source in exchange.sources
                    ],
                    "citation_ids": sorted(exchange.source_map),
                    "grounding_mode": exchange.grounding_mode,
                    "memory": dict(_memory(exchange)),
                },
            )

        on_metrics = mode_results["memory_on"].metrics
        if not bool(on_metrics["absolute_gate_passed"]):
            ownership_failure = not bool(on_metrics["source_ownership"])
            events.append(
                EvaluationEvent.create(
                    "MEMORY.ABSOLUTE_GATE_FAILED",
                    "M3",
                    Severity.SEV1 if ownership_failure else Severity.SEV2,
                    case_ids=(on_case.case_id,),
                    observed={
                        key: on_metrics[key]
                        for key in (
                            "entity_accuracy",
                            "intent_exact",
                            "source_ownership",
                            "citation_validity",
                            "groundedness",
                            "completeness",
                        )
                    },
                    recommended_action="inspect memory anchoring, current retrieval, and M3 evidence",
                )
            )

        stale_initial = _invalid_citation_ids(initial_exchange)
        repeated = sorted(stale_initial & set(_SHORT_CITATION_RE.findall(on_exchange.answer)))
        if repeated:
            events.append(
                EvaluationEvent.create(
                    "MEMORY.HISTORICAL_ERROR_PROPAGATED",
                    "M3",
                    Severity.SEV1,
                    case_ids=(on_case.case_id,),
                    observed={"repeated_historical_citation_ids": repeated},
                    expected={"repeated_historical_citation_ids": []},
                    recommended_action="treat assistant history as non-evidence and prefer current source map",
                )
            )

        off_score = float(mode_results["memory_off"].metrics["answer_score"])
        on_score = float(mode_results["memory_on"].metrics["answer_score"])
        oracle_score = float(mode_results["oracle_standalone"].metrics["answer_score"])
        results.append(
            MemoryTripletResult(
                track_id=track.track_id,
                modes=mode_results,
                comparisons={
                    "memory_on_minus_off": on_score - off_score,
                    "oracle_minus_memory_on": oracle_score - on_score,
                },
                events=tuple(_deduplicate_memory_events(events)),
            )
        )
    return tuple(results)


def _memory_case(track: ConversationTrack, mode: str, query: str) -> EvalCase:
    source_ids = tuple(track.derivation.get("required_follow_child_ids") or ())
    return EvalCase(
        case_id=f"{track.track_id}-{mode}",
        query=query,
        difficulty=Difficulty.D2,
        scenario="text",
        expected_entity_id=track.initial_entity_id,
        expected_entity_ids=(track.initial_entity_id,),
        expected_entity_name=track.initial_entity_name,
        expected_ownership_key=("character", track.initial_entity_id),
        expected_intents=(track.follow_intent,) if mode != "memory_on_initial" else ("intro",),
        expected_source_ids=source_ids,
        source_relevance={source_id: 2.0 for source_id in source_ids},
        expected_behavior=(
            "insufficient_evidence" if mode == "memory_off" else "grounded_answer"
        ),
        allow_no_sources=mode == "memory_off",
        conversation_mode=mode,
        derivation={
            "inventory_sha256": track.derivation.get("inventory_sha256", ""),
            "track_id": track.track_id,
        },
    )


def _memory_mode_metrics(
    track: ConversationTrack,
    exchange: ObservedExchange,
    evaluation: object,
    inventory: EvaluationInventory,
) -> Mapping[str, object]:
    expected_owner = ("character", track.initial_entity_id)
    entity_accuracy = (
        exchange.ownership_key == expected_owner
        or _entity(exchange) == track.initial_entity_name
    )
    actual_intents = exchange.semantic_intents or _requested(exchange)
    expected_intents = (track.follow_intent,)
    intersection = len(set(actual_intents) & set(expected_intents))
    precision = intersection / len(set(actual_intents)) if actual_intents else 0.0
    recall = intersection / len(expected_intents)
    intent_f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    ownership_values = [
        _observed_source_owner(source, inventory) for source in exchange.sources
    ]
    source_ownership = bool(ownership_values) and all(
        value == expected_owner for value in ownership_values
    )
    judged = getattr(evaluation, "judge")
    citation_validity = float(getattr(evaluation, "citation_validity", 0.0))
    absolute = all(
        (
            exchange.success,
            entity_accuracy,
            set(actual_intents) == set(expected_intents),
            source_ownership,
            int(getattr(judged, "groundedness", 1)) >= 3,
            int(getattr(judged, "relevance", 1)) >= 3,
            int(getattr(judged, "completeness", 1)) >= 3,
            citation_validity >= 1.0,
        )
    )
    planner_ms = sum(
        value
        for key, value in exchange.timing.stage_ms.items()
        if key.startswith("planner.")
    )
    return {
        "entity_accuracy": float(entity_accuracy),
        "intent_exact": set(actual_intents) == set(expected_intents),
        "intent_f1": intent_f1,
        "source_ownership": source_ownership,
        "groundedness": int(getattr(judged, "groundedness", 1)),
        "relevance": int(getattr(judged, "relevance", 1)),
        "completeness": int(getattr(judged, "completeness", 1)),
        "citation_validity": citation_validity,
        "refusal_correctness": int(getattr(judged, "refusal_correctness", 1)),
        "answer_score": float(getattr(evaluation, "score", 0.0)),
        "planner_ms": planner_ms,
        "retrieval_ms": exchange.timing.retrieval_ms,
        "validated_ready_ms": exchange.timing.validated_ready_ms,
        "total_ms": exchange.timing.total_ms,
        "absolute_gate_passed": absolute,
    }


def _observed_source_owner(
    source: Mapping[str, object],
    inventory: EvaluationInventory,
) -> tuple[str, str] | None:
    entity_type = str(source.get("entity_type") or "")
    entity_id = str(source.get("entity_id") or "")
    if entity_type and entity_id:
        return entity_type, entity_id
    child = inventory.children.get(str(source.get("child_id") or ""))
    return (child.entity_type, child.entity_id) if child else None


def _invalid_citation_ids(exchange: ObservedExchange) -> set[str]:
    used = set(_SHORT_CITATION_RE.findall(exchange.answer))
    known = set(exchange.source_map)
    return used - known


def _deduplicate_memory_events(
    events: Sequence[EvaluationEvent],
) -> list[EvaluationEvent]:
    output: list[EvaluationEvent] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for event in events:
        key = event.event_code, event.case_ids
        if key not in seen:
            output.append(event)
            seen.add(key)
    return output


def evaluate_conversation_global_checks(
    client: RagEvalClient,
    tracks: Sequence[ConversationTrack],
) -> ConversationTrackResult:
    if len(tracks) < 2:
        raise ConversationEvaluationError(
            "global conversation checks require at least two tracks"
        )
    first, second = tracks[:2]
    same_follow_query = "再介绍一下它"

    interleaved_a = str(uuid4())
    interleaved_b = str(uuid4())
    first_a = client.ask(
        _case(first.track_id, "interleaved-initial-a", first.initial_query),
        conversation_id=interleaved_a,
    )
    first_b = client.ask(
        _case(second.track_id, "interleaved-initial-b", second.initial_query),
        conversation_id=interleaved_b,
    )
    follow_a = client.ask(
        _case(first.track_id, "interleaved-follow-a", same_follow_query),
        conversation_id=interleaved_a,
    )
    follow_b = client.ask(
        _case(second.track_id, "interleaved-follow-b", same_follow_query),
        conversation_id=interleaved_b,
    )
    try:
        interleaved_clear_status = client.clear_conversation(interleaved_a)
    except Exception:
        interleaved_clear_status = 0
    after_clear = client.ask(
        _case(first.track_id, "interleaved-after-clear", same_follow_query),
        conversation_id=interleaved_a,
    )

    sync_id = str(uuid4())
    stream_id = str(uuid4())
    sync_initial = client.ask(
        _case(first.track_id, "parity-sync-initial", first.initial_query),
        conversation_id=sync_id,
    )
    sync_follow = client.ask(
        _case(first.track_id, "parity-sync-follow", first.multi_intent_query),
        conversation_id=sync_id,
    )
    stream_initial = client.ask_stream(
        _case(first.track_id, "parity-stream-initial", first.initial_query),
        conversation_id=stream_id,
    )
    stream_follow = client.ask_stream(
        _case(first.track_id, "parity-stream-follow", first.multi_intent_query),
        conversation_id=stream_id,
    )

    cancel_id = str(uuid4())
    cancel_initial = client.ask(
        _case(first.track_id, "cancel-initial", first.initial_query),
        conversation_id=cancel_id,
    )
    try:
        cancel_events = client.cancel_stream_after_first_token(
            _case(first.track_id, "cancel-switch", first.switch_query),
            conversation_id=cancel_id,
        )
    except Exception:
        cancel_events = ()
    after_cancel = client.ask(
        _case(first.track_id, "cancel-follow", same_follow_query),
        conversation_id=cancel_id,
    )
    try:
        cancel_clear_status = client.clear_conversation(cancel_id)
    except Exception:
        cancel_clear_status = 0
    after_cancel_clear = client.ask(
        _case(first.track_id, "cancel-after-clear", same_follow_query),
        conversation_id=cancel_id,
    )

    checks = {
        "interleaved_initial_new": (
            _memory(first_a).get("status") == "new"
            and _memory(first_b).get("status") == "new"
        ),
        "interleaved_follow_hit": (
            _memory(follow_a).get("status") == "hit"
            and _memory(follow_b).get("status") == "hit"
        ),
        "interleaved_entities": (
            _entity(follow_a) == first.initial_entity_name
            and _entity(follow_b) == second.initial_entity_name
        ),
        "interleaved_sources": (
            _entity_sources_only(follow_a, first.initial_entity_name)
            and _entity_sources_only(follow_b, second.initial_entity_name)
        ),
        "clear_isolation": (
            interleaved_clear_status == 204
            and _memory(after_clear).get("status") == "new"
            and _entity(after_clear) != first.initial_entity_name
        ),
        "parity_initial_new": (
            _memory(sync_initial).get("status") == "new"
            and _memory(stream_initial).get("status") == "new"
        ),
        "parity_follow_hit": (
            _memory(sync_follow).get("status") == "hit"
            and _memory(stream_follow).get("status") == "hit"
        ),
        "parity_entity": (
            _entity(sync_follow) == first.initial_entity_name
            and _entity(stream_follow) == first.initial_entity_name
        ),
        "parity_intents": (
            _same_intent_coverage(_requested(sync_follow), first.multi_intents)
            and _same_intent_coverage(_requested(stream_follow), first.multi_intents)
        ),
        "parity_sources": (
            _entity_sources_only(sync_follow, first.initial_entity_name)
            and _entity_sources_only(stream_follow, first.initial_entity_name)
        ),
        "parity_answers": bool(sync_follow.answer.strip() and stream_follow.answer.strip()),
        "cancel_stopped_before_done": (
            "sources" in cancel_events
            and "token" in cancel_events
            and "done" not in cancel_events
        ),
        "cancel_preserved_last_complete_turn": (
            _memory(cancel_initial).get("status") == "new"
            and _memory(after_cancel).get("status") == "hit"
            and _entity(after_cancel) == first.initial_entity_name
            and _entity_sources_only(after_cancel, first.initial_entity_name)
        ),
        "cancel_clear_isolation": (
            cancel_clear_status == 204
            and _memory(after_cancel_clear).get("status") == "new"
            and _entity(after_cancel_clear) != first.initial_entity_name
            and _entity(after_cancel_clear) != first.switch_entity_name
        ),
    }
    cross_entity_checks = (
        checks["interleaved_entities"],
        checks["interleaved_sources"],
        checks["parity_entity"],
        checks["parity_sources"],
        checks["cancel_preserved_last_complete_turn"],
    )
    severity = (
        Severity.SEV1
        if not all(cross_entity_checks)
        else Severity.PASS if all(checks.values()) else Severity.SEV2
    )
    identity = {
        "kind": "global",
        "track_ids": [first.track_id, second.track_id],
    }
    return ConversationTrackResult(
        track_id=f"conversation-global-{_sha256_json(identity)[:16]}",
        severity=severity,
        checks=checks,
        observations={
            "interleaved_entities": [_entity(follow_a), _entity(follow_b)],
            "after_clear_memory": dict(_memory(after_clear)),
            "parity_entities": [_entity(sync_follow), _entity(stream_follow)],
            "parity_intents": [list(_requested(sync_follow)), list(_requested(stream_follow))],
            "cancel_events": list(cancel_events),
            "after_cancel_entity": _entity(after_cancel),
            "after_cancel_clear_memory": dict(_memory(after_cancel_clear)),
        },
    )
