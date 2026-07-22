from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import pytest

from src.rag_eval.contracts import Difficulty, load_thresholds
from src.rag_eval.inventory import (
    ChildRecord,
    EntityRecord,
    EvaluationInventory,
    MediaRecord,
)
from src.rag_eval.sampling import (
    SampleManifestError,
    build_sample_manifest,
    validate_sample_manifest,
)
from src.rag_eval.reporting import select_human_audit


def _inventory() -> EvaluationInventory:
    entities = {}
    children = {}
    media = {}
    for index in range(10):
        entity_id = f"entity-{index:02d}"
        name = f"测试实体{index:02d}"
        child_ids_by_intent = {}
        for intent in ("intro", "profile_fact", "skill", "item", "culture", "voice", "media"):
            child_id = f"fixture:{entity_id}/{intent}:0001"
            child_ids_by_intent[intent] = (child_id,)
            children[child_id] = ChildRecord(
                child_id=child_id,
                parent_id=f"fixture:{entity_id}/{intent}",
                entity_id=entity_id,
                entity_name=name,
                entity_type="character",
                category="character",
                section_kind=intent,
                title=f"{name} / {intent}",
                route_tags=(intent,),
                text=f"{name} {intent} evidence",
                media_ids=(),
            )
        voice_id = "media:sha1:" + f"{index + 1:040x}"
        media[voice_id] = (
            MediaRecord(
                media_id=voice_id,
                entity_id=entity_id,
                entity_name=name,
                parent_id=f"fixture:{entity_id}/voice",
                child_id=child_ids_by_intent["voice"][0],
                asset_type="voice",
                mime="audio/mpeg",
                url=f"http://example.test/{voice_id}.mp3",
                is_available=True,
                is_common=False,
                language="zh",
                event_name="测试台词",
                sort_order=0,
            ),
        )
        entities[entity_id] = EntityRecord(
            entity_id=entity_id,
            entity_name=name,
            entity_type="character",
            category="character",
            aliases=(f"实体{index:02d}",),
            child_ids_by_intent=child_ids_by_intent,
            media_ids_by_type={"voice": (voice_id,)},
        )

    for intent in ("story", "psychube"):
        entity_id = f"{intent}-entity"
        child_id = f"fixture:{entity_id}:0001"
        children[child_id] = ChildRecord(
            child_id=child_id,
            parent_id=f"fixture:{entity_id}",
            entity_id=entity_id,
            entity_name=f"测试{intent}",
            entity_type=intent,
            category=intent,
            section_kind="profile",
            title=f"测试{intent}",
            route_tags=("profile",),
            text=f"{intent} evidence",
            media_ids=(),
        )
        entities[entity_id] = EntityRecord(
            entity_id=entity_id,
            entity_name=f"测试{intent}",
            entity_type=intent,
            category=intent,
            aliases=(),
            child_ids_by_intent={intent: (child_id,)},
            media_ids_by_type={},
        )

    return EvaluationInventory(
        build_version="fixture",
        entities=entities,
        children=children,
        media=media,
        parent_ids=tuple(sorted({child.parent_id for child in children.values()})),
        sha256="f" * 64,
    )


def test_manifest_meets_difficulty_entity_intent_and_repeat_minima():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    cases = build_sample_manifest(_inventory(), thresholds, seed=1999)
    unique = [case for case in cases if case.repeat_of is None]
    counts = Counter(case.difficulty for case in unique)

    assert len(unique) >= 48
    assert counts[Difficulty.D1] >= 16
    assert counts[Difficulty.D2] >= 12
    assert counts[Difficulty.D3] >= 12
    assert counts[Difficulty.D4] >= 8
    assert len({entity_id for case in unique for entity_id in case.expected_entity_ids}) >= 8
    assert len([case for case in cases if case.repeat_of]) >= math.ceil(len(unique) * 0.1)


def test_every_p0_intent_has_standard_and_complex_or_noisy_coverage():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    cases = build_sample_manifest(_inventory(), thresholds, seed=1999)
    unique = [case for case in cases if case.repeat_of is None]

    for intent in thresholds.p0_intents:
        assert any(intent in case.expected_intents and case.difficulty is Difficulty.D1 for case in unique)
        assert any(
            intent in case.expected_intents and case.difficulty in {Difficulty.D2, Difficulty.D3}
            for case in unique
        )


def test_manifest_is_deterministic_and_qrels_come_from_inventory():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    inventory = _inventory()

    first = build_sample_manifest(inventory, thresholds, seed=1999)
    second = build_sample_manifest(inventory, thresholds, seed=1999)

    assert first == second
    grounded = [case for case in first if case.expected_source_ids]
    assert grounded
    assert all(case.derivation["inventory_sha256"] == inventory.sha256 for case in first)
    assert all(source_id in inventory.children for case in grounded for source_id in case.expected_source_ids)


def test_no_real_entity_or_count_is_required_by_sampling_source():
    source = Path("src/rag_eval/sampling.py").read_text(encoding="utf-8")
    assert "char:" not in source
    assert not re.search(
        r"expected_(skill|voice|language)_count\s*=\s*\d+",
        source,
    )


def test_validate_manifest_rejects_duplicate_case_ids():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    cases = list(build_sample_manifest(_inventory(), thresholds, seed=1999))
    cases.append(cases[0])

    with pytest.raises(SampleManifestError, match="duplicate case_id"):
        validate_sample_manifest(cases, _inventory(), thresholds)


def test_v2_sample_manifest_covers_every_available_entity_type_and_route_mode():
    thresholds = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    inventory = _inventory()

    cases = build_sample_manifest(inventory, thresholds, seed=1999)

    available_types = {
        entity.entity_type
        for entity in inventory.entities.values()
        if entity.child_ids_by_intent
    }
    sampled_types = {
        case.expected_ownership_key[0]
        for case in cases
        if case.expected_ownership_key
    }
    assert available_types <= sampled_types
    assert {
        (False, "empty"),
        (True, "empty"),
        (True, "partial"),
    } <= {
        (
            bool(case.route_options.get("free_supplement")),
            case.expected_retrieval_outcome,
        )
        for case in cases
        if case.expected_retrieval_outcome
    }
    assert all(case.expected_retrieval_outcome != "failed" for case in cases)
    explicit = next(case for case in cases if case.case_id == "route-explicit-free-recovery")
    assert explicit.action_payload == {
        "action_type": "force_free_supplement",
        "label": "自由补充重答",
        "query": explicit.query,
    }
    assert explicit.query == next(
        case.query for case in cases if case.case_id == "route-toggle-open-empty"
    )
    meta_cases = [case for case in cases if "meta_question" in case.expected_intents]
    assert meta_cases
    assert all(case.expected_behavior == "insufficient_evidence" for case in meta_cases)
    general_game_cases = [case for case in cases if "general_game" in case.expected_intents]
    assert general_game_cases
    assert all(case.expected_behavior == "insufficient_evidence" for case in general_game_cases)
    empty_cases = [
        case
        for case in cases
        if case.case_id in {"route-default-closed-empty", "route-toggle-open-empty"}
    ]
    assert all(case.expected_intents for case in empty_cases)
    assert all(case.expected_ownership_key is None for case in empty_cases)
    partial = next(case for case in cases if case.case_id == "route-toggle-open-partial")
    assert partial.expected_ownership_key is not None
    assert len(partial.expected_intents) == 2
    assert partial.expected_source_ids
    assert partial.expected_behavior == "partial_answer"
    video_hybrids = [
        case for case in cases
        if "video" in case.expected_intents and len(case.expected_intents) > 1
    ]
    assert video_hybrids
    assert all(case.expected_behavior == "partial_answer" for case in video_hybrids)
    assert all(case.expected_retrieval_outcome == "partial" for case in video_hybrids)


def test_human_audit_size_is_stratified_and_reproducible():
    case_ids = [f"case-{index:03d}" for index in range(53)]

    first = select_human_audit(case_ids, seed=1999)
    second = select_human_audit(case_ids, seed=1999)

    assert first == second
    assert len(first) == max(12, math.ceil(0.20 * len(set(case_ids))))
    assert len(first) == len(set(first))
