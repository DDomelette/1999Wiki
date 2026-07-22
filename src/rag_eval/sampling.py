"""Deterministic, artifact-derived sampling for full-chain RAG evaluation."""
from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping

from src.rag_eval.contracts import Difficulty, EvalCase, Thresholds
from src.rag_eval.inventory import EntityRecord, EvaluationInventory


class SampleManifestError(ValueError):
    """Raised when a sample manifest does not satisfy reviewed P0 coverage."""


INTENT_LABELS = {
    "intro": "介绍",
    "profile_fact": "基础资料",
    "skill": "技能",
    "item": "单品",
    "culture": "文化资料",
    "voice": "语音",
    "media": "图片",
    "video": "视频",
    "psychube": "心相",
    "story": "故事",
    "general_game": "游戏介绍",
    "meta_question": "助手能力",
}
MEDIA_INTENTS = frozenset({"voice", "media", "video"})
ENTITY_FREE_INTENTS = frozenset({"general_game"})
BOUNDARY_SEEDS_PATH = Path(__file__).resolve().parents[2] / "eval" / "rag_full_chain_boundary_seeds.v1.jsonl"


def build_sample_manifest(
    inventory: EvaluationInventory,
    thresholds: Thresholds,
    seed: int,
) -> tuple[EvalCase, ...]:
    rng = random.Random(seed)
    selected = _select_stratified_entities(inventory, int(thresholds.sample_minimums["entities"]))
    unique: list[EvalCase] = []

    for index, intent in enumerate(thresholds.p0_intents):
        entity = _entity_for_intent(inventory, selected, intent, index)
        unique.append(_make_case(inventory, Difficulty.D1, intent, entity, index, seed))

    _fill_difficulty(
        unique,
        inventory,
        selected,
        Difficulty.D1,
        int(thresholds.sample_minimums["D1"]),
        thresholds.p0_intents,
        seed,
    )

    for index, intent in enumerate(thresholds.p0_intents):
        entity = _entity_for_intent(inventory, selected, intent, index + 3)
        partner = _partner_intent(entity, intent)
        unique.append(
            _make_case(
                inventory,
                Difficulty.D2,
                intent,
                entity,
                index,
                seed,
                partner_intent=partner,
            )
        )

    _fill_difficulty(
        unique,
        inventory,
        selected,
        Difficulty.D2,
        int(thresholds.sample_minimums["D2"]),
        thresholds.p0_intents,
        seed,
    )

    for index, intent in enumerate(thresholds.p0_intents):
        entity = _entity_for_intent(inventory, selected, intent, index + 6)
        unique.append(_make_case(inventory, Difficulty.D3, intent, entity, index, seed))

    _fill_difficulty(
        unique,
        inventory,
        selected,
        Difficulty.D3,
        int(thresholds.sample_minimums["D3"]),
        thresholds.p0_intents,
        seed,
    )

    boundary = _load_boundary_seeds()
    boundary_required = int(thresholds.sample_minimums["D4"])
    if len(boundary) < boundary_required:
        raise SampleManifestError("boundary seed file does not satisfy D4 minimum")
    for index, row in enumerate(boundary[:boundary_required]):
        entity = selected[index % len(selected)] if selected and "{entity}" in row["query_template"] else None
        query = row["query_template"].format(entity=entity.entity_name if entity else "")
        expected_ids = (entity.entity_id,) if entity else ()
        unique.append(
            EvalCase(
                case_id=f"d4-{index + 1:03d}-{row['seed_id']}",
                query=query,
                difficulty=Difficulty.D4,
                scenario="boundary",
                expected_entity_id=entity.entity_id if entity else "",
                expected_entity_ids=expected_ids,
                expected_entity_name=entity.entity_name if entity else "",
                expected_ownership_key=(entity.entity_type, entity.entity_id) if entity else None,
                expected_intents=(),
                expected_behavior=row["expected_behavior"],
                allow_no_sources=True,
                derivation={
                    "inventory_sha256": inventory.sha256,
                    "seed": seed,
                    "boundary_seed_id": row["seed_id"],
                },
            )
        )

    _add_entity_type_coverage(unique, inventory, thresholds, seed)
    unique.extend(_route_contract_cases(inventory, seed))

    minimum_unique = int(thresholds.sample_minimums["unique"])
    fill_index = 0
    while len(unique) < minimum_unique:
        intent = thresholds.p0_intents[fill_index % len(thresholds.p0_intents)]
        entity = _entity_for_intent(inventory, selected, intent, fill_index + len(unique))
        difficulty = (Difficulty.D1, Difficulty.D2, Difficulty.D3)[fill_index % 3]
        unique.append(_make_case(inventory, difficulty, intent, entity, len(unique), seed))
        fill_index += 1

    unique = _deduplicate_case_ids(unique)
    repeat_count = math.ceil(len(unique) * float(thresholds.sample_minimums["repeat_rate"]))
    repeat_candidates = sorted(unique, key=lambda case: case.case_id)
    rng.shuffle(repeat_candidates)
    repeats = [
        replace(
            original,
            case_id=f"repeat-{index + 1:03d}-{original.case_id}",
            repeat_of=original.case_id,
            derivation={**original.derivation, "repeat_of": original.case_id},
        )
        for index, original in enumerate(repeat_candidates[:repeat_count])
    ]
    cases = tuple((*unique, *repeats))
    validate_sample_manifest(cases, inventory, thresholds)
    return cases


def validate_sample_manifest(
    cases: Iterable[EvalCase],
    inventory: EvaluationInventory,
    thresholds: Thresholds,
) -> None:
    values = list(cases)
    ids = [case.case_id for case in values]
    if len(ids) != len(set(ids)):
        raise SampleManifestError("duplicate case_id in sample manifest")
    unique = [case for case in values if case.repeat_of is None]
    repeats = [case for case in values if case.repeat_of is not None]
    if len(unique) < int(thresholds.sample_minimums["unique"]):
        raise SampleManifestError("unique sample minimum is not met")
    counts = Counter(case.difficulty.value for case in unique)
    for difficulty in Difficulty:
        if counts[difficulty.value] < int(thresholds.sample_minimums[difficulty.value]):
            raise SampleManifestError(f"{difficulty.value} sample minimum is not met")
    represented_entities = {
        entity_id for case in unique for entity_id in case.expected_entity_ids if entity_id
    }
    if len(represented_entities) < int(thresholds.sample_minimums["entities"]):
        raise SampleManifestError("entity sample minimum is not met")
    if len(repeats) < math.ceil(len(unique) * float(thresholds.sample_minimums["repeat_rate"])):
        raise SampleManifestError("repeat sample minimum is not met")

    by_id = {case.case_id: case for case in unique}
    for case in values:
        if case.derivation.get("inventory_sha256") != inventory.sha256:
            raise SampleManifestError(f"case {case.case_id} has stale inventory derivation")
        unsupported = set(case.expected_intents) - set(thresholds.p0_intents)
        if unsupported:
            raise SampleManifestError(f"case {case.case_id} has unsupported intents: {sorted(unsupported)}")
        missing_sources = set(case.expected_source_ids) - set(inventory.children)
        if missing_sources:
            raise SampleManifestError(f"case {case.case_id} has unavailable source IDs")
        missing_media = set(case.expected_media_ids) - set(inventory.media)
        if missing_media:
            raise SampleManifestError(f"case {case.case_id} has unavailable media IDs")
        if case.repeat_of:
            original = by_id.get(case.repeat_of)
            if original is None or case.query != original.query:
                raise SampleManifestError(f"case {case.case_id} has invalid repeat_of")

    for intent in thresholds.p0_intents:
        if not any(intent in case.expected_intents and case.difficulty is Difficulty.D1 for case in unique):
            raise SampleManifestError(f"P0 intent lacks D1 coverage: {intent}")
        if not any(
            intent in case.expected_intents and case.difficulty in {Difficulty.D2, Difficulty.D3}
            for case in unique
        ):
            raise SampleManifestError(f"P0 intent lacks D2/D3 coverage: {intent}")


def _make_case(
    inventory: EvaluationInventory,
    difficulty: Difficulty,
    intent: str,
    entity: EntityRecord | None,
    index: int,
    seed: int,
    *,
    partner_intent: str | None = None,
) -> EvalCase:
    intents = tuple(dict.fromkeys(item for item in (intent, partner_intent) if item))
    source_ids = _source_ids(entity, intents, inventory)
    media_ids = _media_ids(entity, intents)
    supported_intents = {
        current
        for current in intents
        if _source_ids(entity, (current,), inventory) or _media_ids(entity, (current,))
    }
    missing_intents = set(intents) - supported_intents
    no_evidence = not source_ids and not media_ids
    partial_evidence = bool(supported_intents) and bool(missing_intents)
    scenario = _scenario(intents, difficulty)
    query = _query_for(difficulty, intents, entity, index)
    entity_ids = (entity.entity_id,) if entity else ()
    return EvalCase(
        case_id=f"{difficulty.value.lower()}-{index + 1:03d}-{intent}",
        query=query,
        difficulty=difficulty,
        scenario=scenario,
        expected_entity_id=entity.entity_id if entity else "",
        expected_entity_ids=entity_ids,
        expected_entity_name=entity.entity_name if entity else "",
        expected_ownership_key=(entity.entity_type, entity.entity_id) if entity else None,
        expected_intents=intents,
        expected_source_ids=source_ids,
        source_relevance={source_id: 2.0 for source_id in source_ids},
        expected_media_ids=media_ids,
        forbidden_media_types=("voice",) if "voice" not in intents else (),
        allow_no_sources=no_evidence or intent in ENTITY_FREE_INTENTS,
        expected_behavior=(
            "insufficient_evidence"
            if no_evidence
            else ("partial_answer" if partial_evidence else "grounded_answer")
        ),
        expected_retrieval_outcome="partial" if partial_evidence else "",
        derivation={
            "inventory_sha256": inventory.sha256,
            "seed": seed,
            "intent": intent,
            "partner_intent": partner_intent or "",
            "source_rule": "artifact_child_ids",
            "media_rule": "available_non_common_intent_media",
        },
    )


def _fill_difficulty(
    cases: list[EvalCase],
    inventory: EvaluationInventory,
    selected: list[EntityRecord],
    difficulty: Difficulty,
    required: int,
    intents: tuple[str, ...],
    seed: int,
) -> None:
    current = sum(case.difficulty is difficulty for case in cases)
    while current < required:
        intent = intents[current % len(intents)]
        entity = _entity_for_intent(inventory, selected, intent, current)
        cases.append(_make_case(inventory, difficulty, intent, entity, current + len(cases), seed))
        current += 1


def _add_entity_type_coverage(
    cases: list[EvalCase],
    inventory: EvaluationInventory,
    thresholds: Thresholds,
    seed: int,
) -> None:
    sampled_types = {
        case.expected_ownership_key[0]
        for case in cases
        if case.expected_ownership_key
    }
    available = sorted(
        (
            entity
            for entity in inventory.entities.values()
            if entity.child_ids_by_intent and entity.entity_type not in sampled_types
        ),
        key=lambda entity: (entity.entity_type, _entity_volume(entity), entity.entity_id),
    )
    seen_types = set(sampled_types)
    for entity in available:
        if entity.entity_type in seen_types:
            continue
        intent = next(
            (
                candidate
                for candidate in thresholds.p0_intents
                if _supports_intent(entity, candidate)
            ),
            "intro",
        )
        cases.append(
            _make_case(
                inventory,
                Difficulty.D1,
                intent,
                entity,
                len(cases),
                seed,
            )
        )
        seen_types.add(entity.entity_type)


def _route_contract_cases(
    inventory: EvaluationInventory,
    seed: int,
) -> tuple[EvalCase, ...]:
    partial_selection = next(
        (
            (entity, supported, missing)
            for entity in sorted(inventory.entities.values(), key=lambda item: item.entity_id)
            if entity.entity_type == "character"
            for supported in ("intro", "profile_fact", "skill", "item", "culture", "voice", "media")
            if _supports_intent(entity, supported)
            for missing in ("voice", "video", "skill", "item", "culture", "media")
            if missing != supported and not _supports_intent(entity, missing)
        ),
        None,
    )
    if partial_selection is None:
        raise SampleManifestError("cannot derive a partial route case from current inventory")
    entity, supported_intent, missing_intent = partial_selection
    owner = (entity.entity_type, entity.entity_id)
    entity_ids = (entity.entity_id,)
    name = entity.entity_name
    partial_intents = (supported_intent, missing_intent)
    source_ids = _source_ids(entity, (supported_intent,), inventory)[:1]
    unknown_query = "不存在实体RAG-EVAL-OWNER的技能是什么？"
    base = {
        "difficulty": Difficulty.D4,
        "scenario": "boundary",
        "allow_no_sources": True,
        "expected_behavior": "insufficient_evidence",
        "derivation": {
            "inventory_sha256": inventory.sha256,
            "seed": seed,
            "source_rule": "route_contract_fixture",
        },
    }
    return (
        EvalCase(
            case_id="route-default-closed-empty",
            query=unknown_query,
            expected_intents=("skill",),
            route_options={"free_supplement": False},
            expected_retrieval_outcome="empty",
            expected_effective_route="rag_grounded",
            **base,
        ),
        EvalCase(
            case_id="route-toggle-open-empty",
            query=unknown_query,
            expected_intents=("skill",),
            route_options={"free_supplement": True},
            expected_retrieval_outcome="empty",
            expected_effective_route="llm_general",
            **base,
        ),
        EvalCase(
            case_id="route-toggle-open-partial",
            query=(
                f"请一起介绍{name}的{INTENT_LABELS[supported_intent]}"
                f"和{INTENT_LABELS[missing_intent]}"
            ),
            expected_entity_id=entity.entity_id,
            expected_entity_ids=entity_ids,
            expected_entity_name=name,
            expected_ownership_key=owner,
            expected_intents=partial_intents,
            expected_source_ids=source_ids,
            route_options={"free_supplement": True},
            expected_retrieval_outcome="partial",
            expected_effective_route="rag_grounded",
            **{**base, "expected_behavior": "partial_answer"},
        ),
        EvalCase(
            case_id="route-explicit-free-recovery",
            query=unknown_query,
            route_options={"free_supplement": True},
            action_payload={
                "action_type": "force_free_supplement",
                "label": "自由补充重答",
                "query": unknown_query,
            },
            expected_retrieval_outcome="empty",
            expected_effective_route="llm_general",
            **base,
        ),
    )


def _select_stratified_entities(
    inventory: EvaluationInventory,
    minimum: int,
) -> list[EntityRecord]:
    characters = sorted(
        (entity for entity in inventory.entities.values() if entity.entity_type == "character"),
        key=lambda entity: (_entity_volume(entity), entity.entity_id),
    )
    target = min(max(minimum, 1), len(characters))
    selected: list[EntityRecord] = []
    for index in range(target):
        position = round(index * (len(characters) - 1) / max(target - 1, 1))
        _append_unique(selected, characters[position])
    for intent in ("story", "psychube"):
        candidate = next(
            (entity for entity in sorted(inventory.entities.values(), key=lambda item: item.entity_id)
             if entity.entity_type == intent or entity.child_ids_by_intent.get(intent)),
            None,
        )
        if candidate:
            _append_unique(selected, candidate)
    if len(selected) < minimum:
        for entity in sorted(inventory.entities.values(), key=lambda item: item.entity_id):
            _append_unique(selected, entity)
            if len(selected) >= minimum:
                break
    if len(selected) < minimum:
        raise SampleManifestError("not enough entities for reviewed sample minimum")
    return selected


def _entity_for_intent(
    inventory: EvaluationInventory,
    selected: list[EntityRecord],
    intent: str,
    index: int,
) -> EntityRecord | None:
    if intent in ENTITY_FREE_INTENTS:
        return None
    candidates = [entity for entity in selected if _supports_intent(entity, intent)]
    if not candidates:
        candidates = [
            entity
            for entity in sorted(inventory.entities.values(), key=lambda item: item.entity_id)
            if _supports_intent(entity, intent)
        ]
    if not candidates and intent == "video":
        candidates = [entity for entity in selected if entity.entity_type == "character"]
    return candidates[index % len(candidates)] if candidates else None


def _supports_intent(entity: EntityRecord, intent: str) -> bool:
    if entity.child_ids_by_intent.get(intent):
        return True
    if entity.entity_type == intent:
        return True
    if intent == "voice":
        return bool(entity.media_ids_by_type.get("voice"))
    if intent == "media":
        return any(entity.media_ids_by_type.get(key) for key in ("image", "portrait", "skill", "skin"))
    if intent == "video":
        return bool(entity.media_ids_by_type.get("video"))
    return False


def _source_ids(
    entity: EntityRecord | None,
    intents: tuple[str, ...],
    inventory: EvaluationInventory,
) -> tuple[str, ...]:
    if entity is None:
        return ()
    values: list[str] = []
    for intent in intents:
        candidates = entity.child_ids_by_intent.get(intent, ())
        if not candidates and entity.entity_type == intent:
            candidates = tuple(
                child_id
                for child_id, child in inventory.children.items()
                if child.entity_id == entity.entity_id
            )
        for child_id in candidates:
            if child_id not in values:
                values.append(child_id)
    return tuple(values)


def _media_ids(entity: EntityRecord | None, intents: tuple[str, ...]) -> tuple[str, ...]:
    if entity is None:
        return ()
    types: list[str] = []
    if "voice" in intents:
        types.append("voice")
    if "video" in intents:
        types.append("video")
    if "media" in intents or "intro" in intents:
        types.extend(("image", "portrait", "skin"))
    if "skill" in intents:
        types.append("skill")
    values: list[str] = []
    for media_type in types:
        for media_id in entity.media_ids_by_type.get(media_type, ()):
            if media_id not in values:
                values.append(media_id)
    return tuple(values)


def _partner_intent(entity: EntityRecord | None, intent: str) -> str | None:
    if entity is None:
        return None
    preferred = ("skill", "voice", "profile_fact", "culture", "media", "intro")
    for candidate in preferred:
        if candidate != intent and _supports_intent(entity, candidate):
            return candidate
    return None


def _query_for(
    difficulty: Difficulty,
    intents: tuple[str, ...],
    entity: EntityRecord | None,
    index: int,
) -> str:
    primary = intents[0]
    label = INTENT_LABELS[primary]
    name = entity.entity_name if entity else ""
    if primary == "general_game":
        return {
            Difficulty.D1: "《重返未来：1999》是什么游戏？",
            Difficulty.D2: "从类型和世界观角度介绍一下《重返未来：1999》",
            Difficulty.D3: "1999这游系大概讲啥呀",
        }[difficulty]
    if primary == "meta_question":
        return {
            Difficulty.D1: "你是谁？",
            Difficulty.D2: "你能用知识库帮我查询哪些内容？",
            Difficulty.D3: "你这助首都能查点啥",
        }[difficulty]
    if difficulty is Difficulty.D1:
        return f"介绍一下{name}" if primary == "intro" else f"{name}的{label}是什么？"
    if difficulty is Difficulty.D2:
        if len(intents) > 1:
            return f"请一起介绍{name}的{INTENT_LABELS[intents[0]]}和{INTENT_LABELS[intents[1]]}"
        return f"请结合现有资料完整说明{name}的{label}，资料不足也要指出"
    alias = entity.aliases[index % len(entity.aliases)] if entity and entity.aliases else name
    noisy_label = {
        "skill": "技技",
        "voice": "语因",
        "profile_fact": "基楚资枓",
        "culture": "文话资枓",
        "media": "图骗",
        "video": "视屏",
    }.get(primary, label)
    return f"想问下 {alias} {noisy_label} 都有啥呀"


def _scenario(intents: tuple[str, ...], difficulty: Difficulty) -> str:
    if difficulty is Difficulty.D4:
        return "boundary"
    has_media = bool(set(intents) & MEDIA_INTENTS)
    if has_media and len(intents) > 1:
        return "hybrid"
    if has_media:
        return "media"
    return "text"


def _entity_volume(entity: EntityRecord) -> int:
    return len({child_id for values in entity.child_ids_by_intent.values() for child_id in values})


def _append_unique(values: list[EntityRecord], item: EntityRecord) -> None:
    if all(existing.entity_id != item.entity_id for existing in values):
        values.append(item)


def _deduplicate_case_ids(cases: list[EvalCase]) -> list[EvalCase]:
    counts: Counter[str] = Counter()
    result: list[EvalCase] = []
    for case in cases:
        counts[case.case_id] += 1
        if counts[case.case_id] == 1:
            result.append(case)
        else:
            result.append(replace(case, case_id=f"{case.case_id}-{counts[case.case_id]}"))
    return result


def _load_boundary_seeds(path: Path = BOUNDARY_SEEDS_PATH) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if not all(payload.get(key) for key in ("seed_id", "query_template", "expected_behavior")):
                raise SampleManifestError("boundary seed row is incomplete")
            rows.append({key: str(payload[key]) for key in ("seed_id", "query_template", "expected_behavior")})
    return rows
