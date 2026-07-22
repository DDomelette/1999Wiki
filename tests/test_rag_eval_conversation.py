from __future__ import annotations

from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

from src.rag_eval.conversation import (
    ConversationEvaluationError,
    _same_intent_coverage,
    build_conversation_tracks,
    evaluate_memory_triplets,
    evaluate_conversation_global_checks,
)
from src.rag_eval.client import ObservedExchange, TimingObservation
from src.rag_eval.contracts import Severity
from src.rag_eval.inventory import ChildRecord, EntityRecord, EvaluationInventory


def _entity(entity_id: str, display_name: str, intents: tuple[str, ...], volume: int):
    children = {}
    child_ids_by_intent = {}
    for intent in intents:
        ids = tuple(f"fixture:{entity_id}/{intent}:{index:04d}" for index in range(volume))
        child_ids_by_intent[intent] = ids
        for child_id in ids:
            children[child_id] = ChildRecord(
                child_id=child_id,
                parent_id=f"fixture:{entity_id}/{intent}",
                entity_id=entity_id,
                entity_name=display_name,
                entity_type="character",
                category="character",
                section_kind=intent,
                title=f"{display_name} {intent}",
                route_tags=(intent,),
                text=f"{display_name} {intent} evidence",
                media_ids=(),
            )
    return EntityRecord(
        entity_id=entity_id,
        entity_name=display_name,
        entity_type="character",
        category="character",
        aliases=(),
        child_ids_by_intent=child_ids_by_intent,
        media_ids_by_type={},
    ), children


def _synthetic_inventory(entity_specs):
    entities = {}
    children = {}
    for spec in entity_specs:
        entity, entity_children = _entity(*spec)
        entities[entity.entity_id] = entity
        children.update(entity_children)
    return EvaluationInventory(
        build_version="fixture",
        entities=entities,
        children=children,
        media={},
        parent_ids=tuple(sorted({child.parent_id for child in children.values()})),
        sha256="a" * 64,
    )


def test_tracks_are_dynamic_stratified_and_require_two_entities():
    inventory = _synthetic_inventory([
        ("entity-a", "测试角色甲", ("skill", "voice"), 3),
        ("entity-b", "测试角色乙", ("item", "culture"), 30),
    ])

    tracks = build_conversation_tracks(inventory, seed=20260713, limit=8)

    assert {track.initial_entity_id for track in tracks} == {"entity-a", "entity-b"}
    assert all(track.switch_entity_id != track.initial_entity_id for track in tracks)
    assert all(len(track.multi_intents) >= 2 for track in tracks)
    assert [asdict(track) for track in tracks] == [
        asdict(track)
        for track in build_conversation_tracks(inventory, seed=20260713, limit=8)
    ]

    one_entity = _synthetic_inventory([
        ("entity-a", "测试角色甲", ("skill", "voice"), 3),
    ])
    with pytest.raises(ConversationEvaluationError, match="at least two"):
        build_conversation_tracks(one_entity, seed=20260713)


def test_track_expectations_are_derived_only_from_inventory_ids():
    inventory = _synthetic_inventory([
        ("entity-a", "测试角色甲", ("skill", "voice", "culture"), 2),
        ("entity-b", "测试角色乙", ("item", "culture"), 2),
    ])

    track = build_conversation_tracks(inventory, seed=7, limit=2)[0]

    assert track.initial_entity_name in track.initial_query
    assert track.switch_entity_name in track.switch_query
    entity_child_ids = {
        child_id
        for child_id, child in inventory.children.items()
        if child.entity_id == track.initial_entity_id
    }
    assert set(track.derivation["allowed_follow_child_ids"]) == entity_child_ids
    assert set(track.derivation["required_follow_child_ids"]) <= entity_child_ids
    assert set(track.derivation["allowed_follow_child_ids"]) <= set(inventory.children)
    assert set(track.derivation["allowed_follow_parent_ids"]) <= set(inventory.parent_ids)
    assert set(track.derivation["allowed_child_ids"]) <= set(inventory.children)
    assert set(track.derivation["allowed_parent_ids"]) <= set(inventory.parent_ids)
    assert track.derivation["inventory_sha256"] == inventory.sha256


def test_multi_intent_coverage_is_order_independent_but_exact():
    expected = ("intro", "profile_fact")

    assert _same_intent_coverage(("profile_fact", "intro"), expected)
    assert not _same_intent_coverage(("intro",), expected)
    assert not _same_intent_coverage(("intro", "intro", "profile_fact"), expected)


class _StatefulConversationClient:
    def __init__(self, tracks):
        self.tracks = tuple(tracks)
        self.entities = {}

    def _exchange(self, case, conversation_id, endpoint):
        initial = next(
            (track for track in self.tracks if case.query == track.initial_query),
            None,
        )
        if initial is not None:
            self.entities[conversation_id] = initial.initial_entity_name
            entity = initial.initial_entity_name
            status = "new"
            intents = ("intro",)
        else:
            entity = self.entities.get(conversation_id)
            status = "hit" if entity else "new"
            multi = next(
                (track for track in self.tracks if case.query == track.multi_intent_query),
                None,
            )
            intents = multi.multi_intents if multi is not None else ("intro",)
        source = ({"name": entity, "child_id": "fixture"},) if entity else ()
        return ObservedExchange(
            case_id=case.case_id,
            endpoint=endpoint,
            success=True,
            status_code=200,
            route={"entity": entity, "requested_intents": list(intents)},
            sources=source,
            media=(),
            media_panels=(),
            failure_actions=(),
            answer="grounded answer",
            timing=TimingObservation("2026-07-14T00:00:00Z", None, None, 1.0),
            raw={
                "memory": {
                    "status": status,
                    "turns_used": 1 if status == "hit" else 0,
                    "rewrite_mode": "planner" if status == "hit" else "none",
                }
            },
        )

    def ask(self, case, *, conversation_id=None):
        return self._exchange(case, conversation_id, "/ask")

    def ask_stream(self, case, *, conversation_id=None):
        return self._exchange(case, conversation_id, "/ask/stream")

    def clear_conversation(self, conversation_id):
        self.entities.pop(conversation_id, None)
        return 204

    def cancel_stream_after_first_token(self, case, *, conversation_id):
        del case, conversation_id
        return ("sources", "token")


def test_global_checks_cover_interleaving_clear_cancel_and_sync_stream_without_ids():
    inventory = _synthetic_inventory([
        ("entity-a", "测试角色甲", ("skill", "voice"), 2),
        ("entity-b", "测试角色乙", ("item", "culture"), 2),
    ])
    tracks = build_conversation_tracks(inventory, seed=20260713)

    result = evaluate_conversation_global_checks(
        _StatefulConversationClient(tracks),
        tracks,
    )

    assert result.severity is Severity.PASS
    assert all(result.checks.values())
    serialized = json.dumps(asdict(result), ensure_ascii=False)
    assert "conversation_id" not in serialized
    assert "00000000-" not in serialized


class _TripletClient:
    def __init__(self, track, *, repeat_stale=False):
        self.track = track
        self.repeat_stale = repeat_stale
        self.calls = []

    def ask(self, case, *, conversation_id=None):
        self.calls.append((case.conversation_mode, conversation_id, case.query))
        is_initial = case.conversation_mode == "memory_on_initial"
        if is_initial:
            answer = "错误历史。[S99]" if self.repeat_stale else "初始回答。[S01]"
            status = "new"
            intents = ["intro"]
        else:
            answer = (
                "继续错误。[S99]"
                if self.repeat_stale and case.conversation_mode == "memory_on"
                else "追问回答。[S01]"
            )
            status = "hit" if case.conversation_mode == "memory_on" else "disabled"
            intents = [self.track.follow_intent]
        source_id = self.track.derivation["required_follow_child_ids"][0]
        source = {
            "citation_id": "S01",
            "name": self.track.initial_entity_name,
            "child_id": source_id,
            "entity_type": "character",
            "entity_id": self.track.initial_entity_id,
        }
        return ObservedExchange(
            case_id=case.case_id,
            endpoint="/ask",
            success=True,
            status_code=200,
            route={
                "entity": self.track.initial_entity_name,
                "semantic_intents": intents,
                "requested_intents": intents,
            },
            sources=(source,),
            media=(),
            media_panels=(),
            failure_actions=(),
            answer=answer,
            timing=TimingObservation(
                "2026-07-15T00:00:00Z",
                10.0,
                20.0,
                30.0,
                validated_ready_ms=18.0,
                stage_ms={"planner.normalize": 2.0},
            ),
            raw={"memory": {"status": status, "turns_used": int(status == "hit"), "rewrite_mode": "planner" if status == "hit" else "none"}},
            entity_ref={
                "entity_type": "character",
                "entity_id": self.track.initial_entity_id,
                "entity_name": self.track.initial_entity_name,
            },
            ownership_key=("character", self.track.initial_entity_id),
            semantic_intents=tuple(intents),
            source_map={"S01": source},
            grounding_mode="grounded",
            memory={"status": status, "turns_used": int(status == "hit"), "rewrite_mode": "planner" if status == "hit" else "none"},
        )


class _TripletJudge:
    def __init__(self):
        self.calls = []

    def evaluate_answer(self, case, **kwargs):
        self.calls.append((
            case.conversation_mode,
            kwargs["answer"],
            kwargs["context"],
            case.expected_behavior,
            case.allow_no_sources,
        ))
        invalid = "[S99]" in kwargs["answer"]
        return SimpleNamespace(
            judge=SimpleNamespace(
                groundedness=1 if invalid else 5,
                relevance=5,
                completeness=5,
                refusal_correctness=5,
            ),
            citation_validity=0.0 if invalid else 1.0,
            severity=Severity.SEV1 if invalid else Severity.PASS,
            score=80.0 if invalid else 100.0,
            events=(),
        )


def test_memory_triplets_run_off_on_and_oracle_through_m3():
    inventory = _synthetic_inventory([
        ("entity-a", "测试角色甲", ("skill", "voice"), 2),
        ("entity-b", "测试角色乙", ("item", "culture"), 2),
    ])
    track = build_conversation_tracks(inventory, seed=20260713, limit=2)[0]
    client = _TripletClient(track)
    judge = _TripletJudge()

    results = evaluate_memory_triplets(client, judge, inventory, (track,))

    assert len(results) == 1
    result = results[0]
    assert set(result.modes) == {"memory_off", "memory_on", "oracle_standalone"}
    assert [call[0] for call in judge.calls] == [
        "memory_off",
        "memory_on",
        "oracle_standalone",
    ]
    memory_on_call = next(call for call in client.calls if call[0] == "memory_on")
    memory_off_call = next(call for call in client.calls if call[0] == "memory_off")
    oracle_call = next(call for call in client.calls if call[0] == "oracle_standalone")
    assert memory_on_call[1]
    assert memory_off_call[1] is None
    assert oracle_call[1] is None
    memory_off_judge_call = next(call for call in judge.calls if call[0] == "memory_off")
    assert memory_off_judge_call[3:] == ("insufficient_evidence", True)
    assert result.modes["memory_on"].metrics["absolute_gate_passed"] is True
    assert result.comparisons["memory_on_minus_off"] == 0.0
    assert result.severity is Severity.PASS


def test_memory_triplet_marks_historical_error_propagation_sev1():
    inventory = _synthetic_inventory([
        ("entity-a", "测试角色甲", ("skill", "voice"), 2),
        ("entity-b", "测试角色乙", ("item", "culture"), 2),
    ])
    track = build_conversation_tracks(inventory, seed=20260713, limit=2)[0]

    result = evaluate_memory_triplets(
        _TripletClient(track, repeat_stale=True),
        _TripletJudge(),
        inventory,
        (track,),
    )[0]

    assert result.severity is Severity.SEV1
    assert any(
        event.event_code == "MEMORY.HISTORICAL_ERROR_PROPAGATED"
        for event in result.events
    )
