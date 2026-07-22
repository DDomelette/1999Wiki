from __future__ import annotations

import json
import sys
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import quote

import pytest

import scripts.verify_multi_intent_voice as evaluator


def _child(entity_id: str, child_id: str, section_kind: str) -> dict[str, str]:
    return {
        "entity_id": entity_id,
        "entity_name": f"name-{entity_id}",
        "child_id": child_id,
        "parent_id": f"{entity_id}/{section_kind}",
        "section_kind": section_kind,
    }


def _voice_media(
    entity_id: str,
    child_id: str,
    media_id: str,
    filename: str,
    *,
    available: bool = True,
    url: str = "https://assets.example.test/audio.mp3",
) -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "child_id": child_id,
        "media_id": media_id,
        "asset_type": "voice",
        "is_available": available,
        "url": url,
        "filename": filename,
    }


def _skill_media(entity_id: str, child_id: str, media_id: str) -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "child_id": child_id,
        "media_id": media_id,
        "asset_type": "skill",
        "mime": "image/webp",
        "is_available": True,
        "url": "https://assets.example.test/skill.webp",
        "filename": f"{media_id}.webp",
    }


def _evaluation_fixture() -> tuple[evaluator.CharacterInventory, list[dict[str, object]], list[dict[str, object]]]:
    entity_id = "entity-eval"
    child_rows = [
        {**_child(entity_id, "skill-eval-a", "skill"), "text": "a" * 11},
        {**_child(entity_id, "skill-eval-b", "skill"), "text": "b" * 13},
        {**_child(entity_id, "voice-eval-a", "voice"), "text": "c" * 7},
        {**_child(entity_id, "voice-eval-b", "voice"), "text": "d" * 9},
        {**_child(entity_id, "voice-eval-text-only", "voice"), "text": "e" * 5},
    ]
    media_rows = [
        _skill_media(entity_id, "skill-eval-a", "skill-media-a"),
        _voice_media(entity_id, "voice-eval-a", "voice-media-a-zh", "Zh_line_a.mp3"),
        _voice_media(entity_id, "voice-eval-a", "voice-media-a-en", "En_line_a.mp3"),
        _voice_media(entity_id, "voice-eval-b", "voice-media-b-jp", "Jp_line_b.mp3"),
    ]
    inventory = evaluator.build_character_inventory(child_rows, media_rows)[0]
    return inventory, child_rows, media_rows


def _route_debug(
    inventory: evaluator.CharacterInventory,
    source_ids: list[str],
    *,
    page_size: int,
    max_sources: int,
    chars_used: int,
) -> dict[str, object]:
    skill_retained = len(set(source_ids) & set(inventory.skill_child_ids))
    voice_retained = len(set(source_ids) & set(inventory.voice_text_child_ids))
    skill_target = len(inventory.skill_child_ids) or 1
    voice_target = min(page_size, len(inventory.voice_text_child_ids)) or 1
    return {
        "requested_intents": ["skill", "voice"],
        "retrieval_debug": {
            "intent_targets": {"skill": skill_target, "voice": voice_target},
            "intent_retained": {"skill": skill_retained, "voice": voice_retained},
            "coverage_shortfall": {
                "skill": max(0, skill_target - skill_retained),
                "voice": max(0, voice_target - voice_retained),
            },
            "chars_used": chars_used,
            "max_sources": max_sources,
        },
    }


def _panel(
    inventory: evaluator.CharacterInventory,
    *,
    page_size: int,
    start: int = 0,
) -> dict[str, object]:
    media_by_line = dict(inventory.playable_media_by_line)
    language_by_media = dict(inventory.media_languages)
    line_ids = inventory.playable_voice_line_ids[start : start + page_size]
    end = start + len(line_ids)
    has_more = end < len(inventory.playable_voice_line_ids)
    return {
        "type": "voice",
        "grouping": "voice_line",
        "entity_id": inventory.entity_id,
        "lines": [
            {
                "voice_line_id": line_id,
                "title": line_id,
                "variants": [
                    {
                        "media_id": media_id,
                        "child_id": line_id,
                        "entity_id": inventory.entity_id,
                        "asset_type": "voice",
                        "role": "voice",
                        "language": language_by_media[media_id],
                        "url": f"https://assets.example.test/{media_id}.mp3",
                    }
                    for media_id in media_by_line[line_id]
                ],
            }
            for line_id in line_ids
        ],
        "page_size": page_size,
        "total_lines": len(inventory.playable_voice_line_ids),
        "has_more": has_more,
        "next_cursor": f"cursor-{end}" if has_more else None,
    }


def _transcript_for_inventory(
    inventory: evaluator.CharacterInventory,
    *,
    page_size: int,
) -> dict[str, object]:
    source_ids = [
        *inventory.skill_child_ids,
        *inventory.voice_text_child_ids[:page_size],
    ]
    chars = dict(inventory.child_char_lengths)
    route = _route_debug(
        inventory,
        source_ids,
        page_size=page_size,
        max_sources=len(source_ids),
        chars_used=sum(chars.get(source_id, 0) for source_id in source_ids),
    )
    panel = _panel(inventory, page_size=page_size)
    variants = [
        variant
        for line in panel["lines"]
        for variant in line["variants"]
    ]
    media = [
        *[
            {
                "media_id": media_id,
                "asset_type": "skill",
                "url": f"https://assets.example.test/{media_id}.webp",
            }
            for media_id in inventory.skill_media_ids[:1]
        ],
        *variants,
    ]
    return {
        "sources": [{"child_id": child_id} for child_id in source_ids],
        "route": route,
        "media": media,
        "media_panels": [panel],
    }


def test_build_character_inventory_uses_only_available_http_voice_variants():
    child_rows = [
        _child("entity-a", "skill-a", "skill"),
        _child("entity-a", "voice-a-1", "voice"),
        _child("entity-a", "voice-a-2", "voice"),
    ]
    media_rows = [
        _voice_media("entity-a", "voice-a-1", "media-zh", "Zh_line.mp3"),
        _voice_media("entity-a", "voice-a-1", "media-en", "En_line.mp3"),
        _voice_media("entity-a", "voice-a-2", "media-unavailable", "Jp_line.mp3", available=False),
        _voice_media("entity-a", "voice-a-2", "media-local", "Kr_line.mp3", url="D:\\audio.mp3"),
        {
            **_voice_media("entity-a", "voice-a-2", "media-image", "Zh_image.webp"),
            "asset_type": "image",
        },
    ]

    inventory = evaluator.build_character_inventory(child_rows, media_rows)

    assert inventory == [
        evaluator.CharacterInventory(
            entity_id="entity-a",
            entity_name="name-entity-a",
            entity_scope="entity-a",
            skill_child_ids=("skill-a",),
            voice_text_child_ids=("voice-a-1", "voice-a-2"),
            playable_voice_line_ids=("voice-a-1",),
            playable_media_ids=("media-en", "media-zh"),
            languages=("en", "zh"),
            child_char_lengths=(("skill-a", 0), ("voice-a-1", 0), ("voice-a-2", 0)),
            playable_media_by_line=(("voice-a-1", ("media-en", "media-zh")),),
            media_languages=(("media-en", "en"), ("media-zh", "zh")),
        )
    ]


def test_inventory_keeps_typed_scope_internal_and_validates_raw_owner_id(monkeypatch):
    raw_entity_id = "3003"
    entity_scope = "char:3003"
    child_rows = [
        {
            **_child(raw_entity_id, "char:3003/skill:0001", "skill"),
            "parent_id": "char:3003/skill",
            "text": "skill",
        },
        {
            **_child(raw_entity_id, "char:3003/voice:0001", "voice"),
            "parent_id": "char:3003/voice",
            "text": "voice",
        },
    ]
    media_rows = [
        {
            **_skill_media(raw_entity_id, "char:3003/skill:0001", "skill-media"),
            "parent_id": "char:3003/skill",
        },
        {
            **_voice_media(raw_entity_id, "char:3003/voice:0001", "voice-media", "Zh_line.mp3"),
            "parent_id": "char:3003/voice",
        },
    ]
    inventory = evaluator.build_character_inventory(child_rows, media_rows)[0]

    assert inventory.entity_id == raw_entity_id
    assert inventory.entity_scope == entity_scope

    panel = _panel(inventory, page_size=1)
    panel["entity_id"] = raw_entity_id
    for line in panel["lines"]:
        for variant in line["variants"]:
            variant["entity_id"] = raw_entity_id
    assert evaluator.evaluate_first_voice_page(inventory, panel) == []
    assert evaluator.evaluate_all_voice_pages(inventory, [panel]) == []

    transcript = _transcript_for_inventory(inventory, page_size=1)
    transcript["media_panels"] = [panel]
    for media in transcript["media"]:
        if media.get("asset_type") == "voice":
            media["entity_id"] = raw_entity_id
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "done", "data": {**transcript, "answer": "ok"}},
        ],
    )
    monkeypatch.setattr(evaluator, "follow_voice_pages", lambda *_args, **_kwargs: [panel])

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=1,
        budgets={"max_sources": 2, "context_budget_chars": 100},
        timeout=1.0,
    )

    assert result["entity_id"] == raw_entity_id
    assert result["entity_scope"] == entity_scope
    assert result["dynamic_expectations"]["entity_scope"] == entity_scope
    assert result["failures"] == []


def test_conflicting_entity_scope_is_retained_as_invalid_inventory_and_evaluation_failure():
    child_rows = [
        {
            **_child("entity-alpha", "char:entity-beta/voice:0001", "voice"),
            "parent_id": "char:entity-beta/voice",
            "text": "voice",
        }
    ]
    media_rows = [
        {
            **_voice_media("entity-alpha", "char:entity-beta/voice:0001", "voice-media", "Zh_line.mp3"),
            "parent_id": "char:entity-beta/voice",
        }
    ]
    inventory = evaluator.build_character_inventory(child_rows, media_rows)[0]
    panel = {
        "type": "voice",
        "grouping": "voice_line",
        "entity_id": "char:entity-beta",
        "lines": [
            {
                "voice_line_id": "char:entity-beta/voice:0001",
                "variants": [
                    {
                        "media_id": "voice-media",
                        "child_id": "char:entity-beta/voice:0001",
                        "entity_id": "char:entity-beta",
                        "language": "zh",
                        "url": "https://assets.example.test/voice.mp3",
                    }
                ],
            }
        ],
        "page_size": 1,
        "total_lines": 1,
        "has_more": False,
        "next_cursor": None,
    }

    assert inventory.entity_scope == ""
    assert inventory.entity_scope_valid is False
    assert "invalid_entity_scope" in evaluator.evaluate_first_voice_page(inventory, panel)
    assert "invalid_entity_scope:0" in evaluator.evaluate_all_voice_pages(inventory, [panel])


def test_evaluate_entity_rejects_invalid_scope_without_playable_media_or_voice_panel(monkeypatch):
    raw_entity_id = "entity-alpha"
    child_rows = [
        {
            **_child(raw_entity_id, "char:entity-beta/skill:0001", "skill"),
            "parent_id": "char:entity-beta/skill",
            "text": "skill",
        },
        {
            **_child(raw_entity_id, "char:entity-beta/voice:0001", "voice"),
            "parent_id": "char:entity-beta/voice",
            "text": "voice",
        },
    ]
    inventory = evaluator.build_character_inventory(child_rows, [])[0]
    source_ids = [*inventory.skill_child_ids, *inventory.voice_text_child_ids]
    chars = dict(inventory.child_char_lengths)
    transcript = {
        "sources": [{"child_id": child_id} for child_id in source_ids],
        "route": _route_debug(
            inventory,
            source_ids,
            page_size=1,
            max_sources=len(source_ids),
            chars_used=sum(chars[child_id] for child_id in source_ids),
        ),
        "media": [],
        "media_panels": [],
    }
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "done", "data": {**transcript, "answer": "ok"}},
        ],
    )

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=1,
        budgets={"max_sources": len(source_ids), "context_budget_chars": sum(chars.values())},
        timeout=1.0,
    )

    assert inventory.entity_scope_valid is False
    assert result["failures"] == ["invalid_entity_scope"]
    assert result["pass"] is False


def test_build_inventory_matches_runtime_voice_audio_classification():
    entity_id = "entity-classification"
    voice_ids = [f"voice-{index}" for index in range(6)]
    child_rows = [_child(entity_id, child_id, "voice") for child_id in voice_ids]
    media_rows = [
        {**_voice_media(entity_id, voice_ids[0], "media-image-audio", "line.mp3"), "asset_type": "image", "mime": "audio/mpeg"},
        {**_voice_media(entity_id, voice_ids[1], "media-voice-image", "line.mp3"), "mime": "image/webp"},
        {**_voice_media(entity_id, voice_ids[2], "media-extension-audio", "line.ogg"), "mime": ""},
        {**_voice_media(entity_id, voice_ids[3], "media-extension-text", "line.txt"), "mime": ""},
        {**_voice_media(entity_id, voice_ids[4], "media-mime-audio", "line.bin"), "mime": "audio/ogg"},
        {**_voice_media(entity_id, voice_ids[5], "media-uppercase-voice", "line.mp3"), "asset_type": "VOICE", "mime": "audio/mpeg"},
    ]
    expected_rows = [media_rows[2], media_rows[4]]

    inventory = evaluator.build_character_inventory(child_rows, media_rows)[0]

    assert set(inventory.playable_voice_line_ids) == {row["child_id"] for row in expected_rows}
    assert set(inventory.playable_media_ids) == {row["media_id"] for row in expected_rows}


def test_select_stratified_characters_is_deterministic_and_keeps_an_anomaly():
    eligible = [
        evaluator.CharacterInventory(
            entity_id=entity_id,
            entity_name=f"name-{entity_id}",
            skill_child_ids=tuple(f"skill-{entity_id}-{index}" for index in range(skill_count)),
            voice_text_child_ids=tuple(f"voice-{entity_id}-{index}" for index in range(playable_count)),
            playable_voice_line_ids=tuple(f"voice-{entity_id}-{index}" for index in range(playable_count)),
            playable_media_ids=tuple(f"media-{entity_id}-{index}" for index in range(playable_count)),
            languages=languages,
        )
        for entity_id, playable_count, skill_count, languages in (
            ("entity-low", 1, 1, ("zh",)),
            ("entity-middle", 3, 2, ("en", "zh")),
            ("entity-high", 5, 3, ("en", "jp", "zh")),
        )
    ]
    anomaly = evaluator.CharacterInventory(
        entity_id="entity-voice-without-media",
        entity_name="name-entity-voice-without-media",
        skill_child_ids=("skill-anomaly",),
        voice_text_child_ids=("voice-anomaly",),
        playable_voice_line_ids=(),
        playable_media_ids=(),
        languages=(),
    )

    first = evaluator.select_stratified_characters([*eligible, anomaly], limit=3)
    second = evaluator.select_stratified_characters([*eligible, anomaly], limit=3)

    assert first == second
    assert [item.entity_id for item in first[:3]] == ["entity-low", "entity-middle", "entity-high"]
    assert first[-1] == anomaly
    assert {len(item.skill_child_ids) for item in first[:3]} == {1, 2, 3}
    assert {len(item.languages) for item in first[:3]} == {1, 2, 3}


def test_anomaly_pool_covers_missing_sections_no_media_and_partial_playable_voice():
    missing_section = evaluator.CharacterInventory(
        entity_id="anomaly-missing-section",
        entity_name="missing-section",
        skill_child_ids=(),
        voice_text_child_ids=("voice-missing",),
        playable_voice_line_ids=("voice-missing",),
        playable_media_ids=("media-missing",),
        languages=("zh",),
    )
    no_media = evaluator.CharacterInventory(
        entity_id="anomaly-no-media",
        entity_name="no-media",
        skill_child_ids=("skill-no-media",),
        voice_text_child_ids=("voice-no-media",),
        playable_voice_line_ids=(),
        playable_media_ids=(),
        languages=(),
    )
    partial = evaluator.CharacterInventory(
        entity_id="entity-02",
        entity_name="partial",
        skill_child_ids=("skill-partial",),
        voice_text_child_ids=("voice-playable", "voice-text-only"),
        playable_voice_line_ids=("voice-playable",),
        playable_media_ids=("media-playable",),
        languages=("zh",),
    )

    assert evaluator._is_anomaly(missing_section)
    assert evaluator._is_anomaly(no_media)
    assert evaluator._is_anomaly(partial)
    assert evaluator._anomaly_sort_key(partial) < evaluator._anomaly_sort_key(no_media)
    assert evaluator._anomaly_sort_key(no_media) < evaluator._anomaly_sort_key(missing_section)

    ordinary = [
        evaluator.CharacterInventory(
            entity_id=f"entity-{index:02d}",
            entity_name=f"ordinary-{index}",
            skill_child_ids=(f"skill-{index}",),
            voice_text_child_ids=(f"voice-{index}",),
            playable_voice_line_ids=(f"voice-{index}",),
            playable_media_ids=(f"media-{index}",),
            languages=("zh",),
        )
        for index in range(10)
        if index != 2
    ]

    selected = evaluator.select_stratified_characters([*ordinary, partial], limit=8)

    assert len([item for item in selected if evaluator._is_eligible(item)]) == 9
    assert selected[-1] == partial
    assert len({item.entity_id for item in selected}) == len(selected)


def test_capture_collection_snapshot_only_uses_metadata_schema_and_count_reads(monkeypatch):
    calls: list[tuple[str, str]] = []

    class ReadOnlyMilvusClient:
        def __init__(self, *, uri: str, db_name: str):
            calls.append(("connect", f"{uri}/{db_name}"))

        def has_collection(self, collection_name: str) -> bool:
            calls.append(("has_collection", collection_name))
            return True

        def describe_collection(self, collection_name: str) -> dict[str, object]:
            calls.append(("describe_collection", collection_name))
            return {"fields": [{"name": "id", "type": "VARCHAR"}]}

        def get_collection_stats(self, collection_name: str) -> dict[str, str]:
            calls.append(("get_collection_stats", collection_name))
            return {"row_count": "17"}

    monkeypatch.setattr(evaluator, "MilvusClient", ReadOnlyMilvusClient)
    cfg = SimpleNamespace(
        vectorstore=SimpleNamespace(
            uri="http://milvus.example.test:19530",
            db_name="evaluation",
            collection_name="text-evaluation",
        )
    )

    snapshot = evaluator.capture_collection_snapshot(cfg)

    assert snapshot == {
        "collection_name": "text-evaluation",
        "exists": True,
        "schema": {"fields": [{"name": "id", "type": "VARCHAR"}]},
        "row_count": 17,
    }
    assert [name for name, _ in calls] == [
        "connect",
        "has_collection",
        "describe_collection",
        "get_collection_stats",
    ]


def test_compare_collection_snapshots_reports_guard_violations():
    before = {
        "collection_name": "text-before",
        "exists": True,
        "schema": {"fields": [{"name": "id"}]},
        "row_count": 17,
    }
    after = {
        "collection_name": "text-after",
        "exists": True,
        "schema": {"fields": [{"name": "text"}]},
        "row_count": 18,
    }

    assert evaluator.compare_collection_snapshots(before, after) == [
        "collection_name changed",
        "schema changed",
        "row_count changed",
    ]


def test_compare_snapshots_cli_returns_nonzero_and_reports_mismatch(monkeypatch, tmp_path, capsys):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps({"collection_name": "same", "schema": {}, "row_count": 7}), encoding="utf-8")
    after.write_text(json.dumps({"collection_name": "same", "schema": {}, "row_count": 8}), encoding="utf-8")
    monkeypatch.setattr(evaluator, "get_config", lambda: (_ for _ in ()).throw(AssertionError("config loaded")))
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_multi_intent_voice.py", "compare-snapshots", "--before", str(before), "--after", str(after)],
    )

    exit_code = evaluator.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload == {"failures": ["row_count changed"], "overall_pass": False}


def test_compare_snapshots_cli_returns_zero_for_equal_snapshots(monkeypatch, tmp_path, capsys):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    snapshot = {"collection_name": "same", "schema": {"fields": []}, "row_count": 7}
    before.write_text(json.dumps(snapshot), encoding="utf-8")
    after.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(evaluator, "get_config", lambda: (_ for _ in ()).throw(AssertionError("config loaded")))
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_multi_intent_voice.py", "compare-snapshots", "--before", str(before), "--after", str(after)],
    )

    exit_code = evaluator.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"failures": [], "overall_pass": True}


def test_evaluate_sources_uses_dynamic_exact_quotas_and_accepts_text_only_voice():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = len(inventory.playable_voice_line_ids)
    source_ids = [
        *inventory.skill_child_ids,
        inventory.voice_text_child_ids[0],
        inventory.voice_text_child_ids[-1],
    ]
    chars = dict(inventory.child_char_lengths)
    chars_used = sum(chars[source_id] for source_id in source_ids)
    route = _route_debug(
        inventory,
        source_ids,
        page_size=page_size,
        max_sources=len(source_ids),
        chars_used=chars_used,
    )

    failures = evaluator.evaluate_sources(
        inventory,
        source_ids,
        route,
        page_size,
        {
            "max_sources": len(source_ids),
            "context_budget_chars": chars_used,
        },
    )

    assert failures == []


def test_evaluate_sources_rejects_duplicates_foreign_ids_and_false_shortfall():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = len(inventory.playable_voice_line_ids)
    source_ids = [inventory.skill_child_ids[0], inventory.voice_text_child_ids[0]]
    chars = dict(inventory.child_char_lengths)
    route = _route_debug(
        inventory,
        source_ids,
        page_size=page_size,
        max_sources=len(source_ids),
        chars_used=sum(chars[source_id] for source_id in source_ids),
    )
    route["retrieval_debug"]["coverage_shortfall"]["voice"] = 0
    observed = [*source_ids, source_ids[0], "foreign-child"]

    failures = evaluator.evaluate_sources(
        inventory,
        observed,
        route,
        page_size,
        {"max_sources": len(source_ids), "context_budget_chars": sum(chars.values())},
    )

    assert "duplicate_source_id:skill-eval-a" in failures
    assert "foreign_source_id:foreign-child" in failures
    assert "coverage_shortfall_mismatch:voice" in failures


def test_evaluate_sources_accepts_same_entity_spare_fill_rows():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    spare_child_id = "entity-eval/profile:0000"
    inventory = replace(
        inventory,
        child_char_lengths=(*inventory.child_char_lengths, (spare_child_id, 17)),
    )
    source_ids = [
        *inventory.skill_child_ids,
        *inventory.voice_text_child_ids,
        spare_child_id,
    ]
    chars = dict(inventory.child_char_lengths)
    chars_used = sum(chars[source_id] for source_id in source_ids)
    route = _route_debug(
        inventory,
        source_ids,
        page_size=len(inventory.voice_text_child_ids),
        max_sources=len(source_ids),
        chars_used=chars_used,
    )

    failures = evaluator.evaluate_sources(
        inventory,
        source_ids,
        route,
        len(inventory.voice_text_child_ids),
        {"max_sources": len(source_ids), "context_budget_chars": chars_used},
    )

    assert failures == []


def test_evaluate_sources_accepts_truthful_over_budget_two_intent_coverage():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = len(inventory.playable_voice_line_ids)
    source_ids = [inventory.skill_child_ids[0], inventory.voice_text_child_ids[0]]
    chars = dict(inventory.child_char_lengths)
    chars_used = sum(chars[source_id] for source_id in source_ids)
    route = _route_debug(
        inventory,
        source_ids,
        page_size=page_size,
        max_sources=len(source_ids),
        chars_used=chars_used,
    )

    failures = evaluator.evaluate_sources(
        inventory,
        source_ids,
        route,
        page_size,
        {"max_sources": len(source_ids), "context_budget_chars": chars_used},
    )

    assert failures == []


def test_evaluate_sources_requires_truthful_missing_section_shortfall():
    entity_id = "entity-missing-skill"
    rows = [{**_child(entity_id, "voice-only-text", "voice"), "text": "voice"}]
    inventory = evaluator.build_character_inventory(rows, [])[0]
    source_ids = list(inventory.voice_text_child_ids)
    route = _route_debug(
        inventory,
        source_ids,
        page_size=1,
        max_sources=1,
        chars_used=len(rows[0]["text"]),
    )

    assert evaluator.evaluate_sources(
        inventory,
        source_ids,
        route,
        1,
        {"max_sources": 1, "context_budget_chars": len(rows[0]["text"])},
    ) == []
    assert evaluator.evaluate_first_voice_page(inventory, None) == []


def test_evaluate_sources_recomputes_observed_chars_and_rejects_unknown_ids():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    source_ids = [inventory.skill_child_ids[0], inventory.voice_text_child_ids[0], "unknown-child"]
    chars = dict(inventory.child_char_lengths)
    known_chars = chars[source_ids[0]] + chars[source_ids[1]]
    route = _route_debug(
        inventory,
        source_ids[:2],
        page_size=1,
        max_sources=len(source_ids),
        chars_used=known_chars - 1,
    )

    failures = evaluator.evaluate_sources(
        inventory,
        source_ids,
        route,
        1,
        {"max_sources": len(source_ids), "context_budget_chars": known_chars - 1},
    )

    assert "foreign_source_id:unknown-child" in failures
    assert "unknown_source_char_length:unknown-child" in failures
    assert "observed_chars_over_budget" in failures
    assert "chars_used_underreported" in failures


def test_evaluate_first_voice_page_checks_exact_lines_variants_and_languages():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = len(inventory.playable_voice_line_ids)
    panel = _panel(inventory, page_size=page_size)

    assert evaluator.evaluate_first_voice_page(inventory, panel) == []

    panel["lines"][0]["variants"][0]["language"] = "foreign-language"
    panel["lines"][0]["variants"].append(dict(panel["lines"][0]["variants"][0]))
    panel["lines"][0]["variants"].append({
        "media_id": "foreign-media",
        "child_id": panel["lines"][0]["voice_line_id"],
        "entity_id": "foreign-entity",
        "asset_type": "voice",
        "role": "voice",
        "language": "zh",
        "url": "https://assets.example.test/foreign.mp3",
    })

    failures = evaluator.evaluate_first_voice_page(inventory, panel)

    assert any(item.startswith("duplicate_voice_media_id:") for item in failures)
    assert "foreign_voice_media_id:foreign-media" in failures
    assert any(item.startswith("voice_language_mismatch:") for item in failures)


def test_evaluate_all_voice_pages_requires_exact_union_without_duplicates():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    pages = [
        _panel(inventory, page_size=1, start=index)
        for index in range(len(inventory.playable_voice_line_ids))
    ]

    assert evaluator.evaluate_all_voice_pages(inventory, pages) == []

    duplicate_pages = [*pages, pages[-1]]
    failures = evaluator.evaluate_all_voice_pages(inventory, duplicate_pages)

    assert any(item.startswith("duplicate_voice_line_id:") for item in failures)
    assert any(item.startswith("duplicate_voice_media_id:") for item in failures)


def test_evaluate_media_union_requires_skill_and_voice_without_local_paths():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    route = {"requested_intents": ["skill", "voice"]}
    media = [
        {"media_id": inventory.skill_media_ids[0], "asset_type": "skill", "url": "https://assets.test/s.webp"},
        {"media_id": inventory.playable_media_ids[0], "asset_type": "voice", "url": "https://assets.test/v.mp3"},
    ]

    assert evaluator.evaluate_media_union(route, media) == []

    media[0]["url"] = "file://local/skill.webp"
    failures = evaluator.evaluate_media_union(route, media)

    assert "local_path_leak" in failures

    assert "media_strategy_missing:skill" in evaluator.evaluate_media_union(route, media[1:])

    media[0]["url"] = "https://assets.test/%5C%5Cserver%5Cshare%5Cskill.webp"
    assert "local_path_leak" in evaluator.evaluate_media_union(route, media)


def test_transport_safety_does_not_treat_profile_identifier_as_file_scheme():
    assert evaluator._contains_local_path("char:entity/profile:0000") is False


def test_inventory_preserves_reused_media_id_membership_and_exposes_conflict():
    entity_id = "entity-reused-media"
    first_child = f"{entity_id}/voice:0001"
    second_child = f"{entity_id}/voice:0002"
    child_rows = [
        _child(entity_id, first_child, "voice"),
        _child(entity_id, second_child, "voice"),
    ]
    media_rows = [
        _voice_media(entity_id, first_child, "shared-media", "Zh_first.mp3"),
        _voice_media(entity_id, second_child, "shared-media", "Zh_second.mp3"),
    ]

    inventory = evaluator.build_character_inventory(child_rows, media_rows)[0]

    assert inventory.playable_voice_line_ids == (first_child, second_child)
    assert inventory.playable_media_ids == ("shared-media", "shared-media")
    assert inventory.playable_media_by_line == (
        (first_child, ("shared-media",)),
        (second_child, ("shared-media",)),
    )
    assert inventory.media_id_line_conflicts == (
        ("shared-media", (first_child, second_child)),
    )

    pages = [
        _panel(inventory, page_size=1, start=index)
        for index in range(len(inventory.playable_voice_line_ids))
    ]
    failures = evaluator.evaluate_all_voice_pages(inventory, pages)

    assert "artifact_media_id_reused_across_voice_lines:shared-media" in failures
    assert "duplicate_voice_media_id:shared-media" in failures
    assert "all_voice_line_set_mismatch" not in failures
    assert "all_voice_media_set_mismatch" not in failures


@pytest.mark.parametrize(
    "unsafe_value",
    [
        {"url": "https://assets.test/safe.webp", "metadata": {"local_relpath": "safe-looking"}},
        {"url": "assets/relative.webp"},
        {"url": "data:image/webp;base64,AAAA"},
        {
            "url": "https://assets.test/" + (
                lambda value: quote(quote(quote(value, safe=""), safe=""), safe="")
            )("file:///C:/private/audio.mp3")
        },
    ],
)
def test_transport_safety_rejects_forbidden_keys_and_unsafe_urls(unsafe_value):
    assert evaluator._contains_local_path({"wrapper": [unsafe_value]}) is True


def test_parse_sse_events_handles_chunk_boundaries_crlf_and_multiline_data():
    raw = (
        ": heartbeat\r\n"
        "event: sources\r\n"
        "data: {\"sources\": [],\r\n"
        "data: \"label\": \"技能和语音\"}\r\n\r\n"
        "event: done\n"
        "data: {\"answer\": \"ok\"}"
    ).encode("utf-8")
    split_points = [1, 9, 25, 47, len(raw) - 2]
    chunks = [raw[start:end] for start, end in zip([0, *split_points], [*split_points, len(raw)])]

    assert evaluator.parse_sse_events(chunks) == [
        {"event": "sources", "data": {"sources": [], "label": "技能和语音"}},
        {"event": "done", "data": {"answer": "ok"}},
    ]


def test_run_evaluation_builds_deterministic_report_from_sse_and_cursor_pages():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = 1
    source_ids = [*inventory.skill_child_ids, inventory.voice_text_child_ids[0]]
    chars = dict(inventory.child_char_lengths)
    route = _route_debug(
        inventory,
        source_ids,
        page_size=page_size,
        max_sources=len(source_ids),
        chars_used=sum(chars[source_id] for source_id in source_ids),
    )
    first_page = _panel(inventory, page_size=page_size)
    second_page = _panel(inventory, page_size=page_size, start=page_size)
    media_by_line = dict(inventory.playable_media_by_line)
    language_by_media = dict(inventory.media_languages)
    first_media = [
        {
            "media_id": inventory.skill_media_ids[0],
            "asset_type": "skill",
            "url": "https://assets.example.test/skill.webp",
        },
        *[
            {
                "media_id": media_id,
                "asset_type": "voice",
                "child_id": first_page["lines"][0]["voice_line_id"],
                "language": language_by_media[media_id],
                "url": f"https://assets.example.test/{media_id}.mp3",
            }
            for media_id in media_by_line[first_page["lines"][0]["voice_line_id"]]
        ],
    ]
    transcript = {
        "sources": [{"child_id": child_id} for child_id in source_ids],
        "route": route,
        "media": first_media,
        "media_panels": [first_page],
    }
    requests: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            requests.append(("POST", body["question"]))
            sources = json.dumps(transcript, ensure_ascii=False, separators=(",", ":"))
            done = json.dumps({**transcript, "answer": "ok"}, ensure_ascii=False, separators=(",", ":"))
            payload = f"event: sources\ndata: {sources}\n\nevent: done\ndata: {done}\n\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            for index in range(0, len(payload), 7):
                self.wfile.write(payload[index : index + 7])
                self.wfile.flush()

        def do_GET(self):
            requests.append(("GET", self.path))
            payload = json.dumps(second_page, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cfg = SimpleNamespace(
        rag=SimpleNamespace(top_k=len(source_ids)),
        retrieval=SimpleNamespace(
            context_budget_chars=sum(chars.values()),
            voice_page_size=page_size,
            voice_page_size_max=20,
        ),
    )
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        first_report = evaluator.run_evaluation(
            cfg,
            base_url=base_url,
            inventory=[inventory],
            before_snapshot_reference="eval/before.json",
            limit=8,
            timeout=2.0,
        )
        second_report = evaluator.run_evaluation(
            cfg,
            base_url=base_url,
            inventory=[inventory],
            before_snapshot_reference="eval/before.json",
            limit=8,
            timeout=2.0,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first_report == second_report
    assert first_report["overall_pass"] is True
    assert first_report["before_snapshot_reference"] == "eval/before.json"
    assert first_report["selected_entities"] == [inventory.entity_id]
    evaluation = first_report["evaluations"][0]
    assert evaluation["query"] == f"{inventory.entity_name}的技能和语音"
    assert evaluation["dynamic_expectations"]["S"] == list(inventory.skill_child_ids)
    assert evaluation["dynamic_expectations"]["T"] == list(inventory.voice_text_child_ids)
    assert evaluation["dynamic_expectations"]["V"] == list(inventory.playable_voice_line_ids)
    assert evaluation["dynamic_expectations"]["M"] == list(inventory.playable_media_ids)
    assert evaluation["dynamic_expectations"]["voice_media_by_line"] == {
        line_id: list(media_ids) for line_id, media_ids in inventory.playable_media_by_line
    }
    assert evaluation["dynamic_expectations"]["child_char_lengths"] == dict(inventory.child_char_lengths)
    assert evaluation["dynamic_expectations"]["text_only_voice_ids"] == sorted(
        set(inventory.voice_text_child_ids) - set(inventory.playable_voice_line_ids)
    )
    assert evaluation["observed"]["retrieval_debug"] == route["retrieval_debug"]
    assert evaluation["observed"]["source_chars"] == sum(chars[source_id] for source_id in source_ids)
    assert evaluation["observed"]["first_page_size"] == page_size
    assert evaluation["observed"]["first_total_lines"] == len(inventory.playable_voice_line_ids)
    assert evaluation["observed"]["page_count"] == len(inventory.playable_voice_line_ids)
    assert evaluation["failures"] == []
    assert any(method == "GET" and "cursor=cursor-1" in value for method, value in requests)


def test_run_evaluation_records_bounded_http_errors_instead_of_raising():
    inventory, _child_rows, _media_rows = _evaluation_fixture()

    class FailingHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), FailingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cfg = SimpleNamespace(
        rag=SimpleNamespace(top_k=20),
        retrieval=SimpleNamespace(context_budget_chars=9000, voice_page_size=8, voice_page_size_max=20),
    )
    try:
        report = evaluator.run_evaluation(
            cfg,
            base_url=f"http://127.0.0.1:{server.server_port}",
            inventory=[inventory],
            before_snapshot_reference="eval/before.json",
            limit=8,
            timeout=1.0,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert report["overall_pass"] is False
    assert report["evaluations"][0]["failures"] == ["transport_error:http_status_503"]


def test_evaluate_cli_loads_artifacts_and_writes_requested_report(monkeypatch, tmp_path):
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    output = tmp_path / "report.json"
    cfg = SimpleNamespace()
    captured: dict[str, object] = {}
    expected_report = {"overall_pass": True, "selected_entities": [inventory.entity_id]}

    monkeypatch.setattr(evaluator, "get_config", lambda: cfg)
    monkeypatch.setattr(
        evaluator,
        "resolve_runtime_artifact_snapshot",
        lambda _cfg: SimpleNamespace(child_blocks="children.jsonl", media_assets="media.jsonl"),
    )
    monkeypatch.setattr(evaluator, "iter_jsonl", lambda _path: [])
    monkeypatch.setattr(evaluator, "build_character_inventory", lambda _children, _media: [inventory])

    def fake_run_evaluation(config, **kwargs):
        captured["config"] = config
        captured.update(kwargs)
        return expected_report

    monkeypatch.setattr(evaluator, "run_evaluation", fake_run_evaluation)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_multi_intent_voice.py",
            "evaluate",
            "--base-url",
            "http://127.0.0.1:8765",
            "--output",
            str(output),
        ],
    )

    exit_code = evaluator.main()

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8")) == expected_report
    assert captured["config"] is cfg
    assert captured["base_url"] == "http://127.0.0.1:8765"
    assert captured["inventory"] == [inventory]
    assert captured["before_snapshot_reference"] == "eval/multi_intent_voice_collection_before.json"


def test_evaluate_cli_returns_nonzero_when_report_fails(monkeypatch, tmp_path):
    output = tmp_path / "report.json"
    cfg = SimpleNamespace()
    expected_report = {"overall_pass": False, "report_failures": ["artifact conflict"]}
    monkeypatch.setattr(evaluator, "get_config", lambda: cfg)
    monkeypatch.setattr(
        evaluator,
        "resolve_runtime_artifact_snapshot",
        lambda _cfg: SimpleNamespace(child_blocks="children.jsonl", media_assets="media.jsonl"),
    )
    monkeypatch.setattr(evaluator, "iter_jsonl", lambda _path: [])
    monkeypatch.setattr(evaluator, "build_character_inventory", lambda _children, _media: [])
    monkeypatch.setattr(evaluator, "run_evaluation", lambda _cfg, **_kwargs: expected_report)
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_multi_intent_voice.py", "evaluate", "--output", str(output)],
    )

    exit_code = evaluator.main()

    assert exit_code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == expected_report


def test_anomaly_assertion_proves_text_only_source_without_empty_player_row(monkeypatch):
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    unretained_text_only_id = "voice-eval-aaa-text-only"
    retained_text_only_id = "voice-eval-text-only"
    inventory = replace(
        inventory,
        voice_text_child_ids=tuple(sorted((
            *inventory.voice_text_child_ids,
            unretained_text_only_id,
        ))),
        child_char_lengths=tuple(sorted((
            *inventory.child_char_lengths,
            (unretained_text_only_id, 6),
        ))),
    )
    page_size = len(inventory.voice_text_child_ids)
    transcript = _transcript_for_inventory(inventory, page_size=page_size)
    transcript["sources"] = [
        source
        for source in transcript["sources"]
        if source["child_id"] != unretained_text_only_id
    ]
    source_ids = [source["child_id"] for source in transcript["sources"]]
    transcript["route"] = _route_debug(
        inventory,
        source_ids,
        page_size=page_size,
        max_sources=len(source_ids),
        chars_used=sum(dict(inventory.child_char_lengths)[source_id] for source_id in source_ids),
    )
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "done", "data": {**transcript, "answer": "ok"}},
        ],
    )
    monkeypatch.setattr(
        evaluator,
        "follow_voice_pages",
        lambda *_args, **_kwargs: transcript["media_panels"],
    )

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=page_size,
        budgets={"max_sources": 20, "context_budget_chars": 9000},
        timeout=1.0,
        sample_type="anomaly",
    )

    assert result["observed"]["retained_text_only_voice_ids"] == [retained_text_only_id]
    assert result["observed"]["sampled_text_only_voice_child_id"] == retained_text_only_id
    assert result["observed"]["sampled_text_only_voice_source_retained"] is True
    assert result["observed"]["sampled_text_only_voice_player_row_emitted"] is False
    assert not any("anomaly_text_only_voice" in failure for failure in result["failures"])

    transcript["media_panels"][0]["lines"].append(
        {
            "voice_line_id": retained_text_only_id,
            "title": retained_text_only_id,
            "variants": [],
        }
    )
    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=page_size,
        budgets={"max_sources": 20, "context_budget_chars": 9000},
        timeout=1.0,
        sample_type="anomaly",
    )

    assert (
        f"anomaly_text_only_voice_player_row_emitted:{retained_text_only_id}"
        in result["failures"]
    )

    transcript["media_panels"][0]["lines"].pop()
    transcript["sources"] = [
        source
        for source in transcript["sources"]
        if source["child_id"] != retained_text_only_id
    ]
    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=page_size,
        budgets={"max_sources": 20, "context_budget_chars": 9000},
        timeout=1.0,
        sample_type="anomaly",
    )

    assert result["observed"]["retained_text_only_voice_ids"] == []
    assert "anomaly_text_only_voice_source_missing" in result["failures"]


def test_anomaly_does_not_require_text_only_source_when_playable_rows_fill_quota(
    monkeypatch,
):
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = 1
    transcript = _transcript_for_inventory(inventory, page_size=page_size)
    text_only = set(inventory.voice_text_child_ids) - set(inventory.playable_voice_line_ids)
    transcript["sources"] = [
        source
        for source in transcript["sources"]
        if source["child_id"] not in text_only
    ]
    source_ids = [source["child_id"] for source in transcript["sources"]]
    transcript["route"] = _route_debug(
        inventory,
        source_ids,
        page_size=page_size,
        max_sources=20,
        chars_used=sum(
            dict(inventory.child_char_lengths)[source_id] for source_id in source_ids
        ),
    )
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "done", "data": {**transcript, "answer": "ok"}},
        ],
    )
    monkeypatch.setattr(
        evaluator,
        "follow_voice_pages",
        lambda *_args, **_kwargs: transcript["media_panels"],
    )

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=page_size,
        budgets={"max_sources": 20, "context_budget_chars": 9000},
        timeout=1.0,
        sample_type="anomaly",
    )

    assert result["observed"]["text_only_source_required_by_quota"] is False
    assert "anomaly_text_only_voice_source_missing" not in result["failures"]


def test_report_rejects_voice_page_size_that_differs_from_runtime_config(monkeypatch):
    entity_id = "entity-one-line"
    child_rows = [
        {**_child(entity_id, "skill-one", "skill"), "text": "skill"},
        {**_child(entity_id, "voice-one", "voice"), "text": "voice"},
    ]
    media_rows = [
        _skill_media(entity_id, "skill-one", "skill-media-one"),
        _voice_media(entity_id, "voice-one", "voice-media-one", "Zh_line.mp3"),
    ]
    inventory = evaluator.build_character_inventory(child_rows, media_rows)[0]
    source_ids = [*inventory.skill_child_ids, *inventory.voice_text_child_ids]
    route = _route_debug(
        inventory,
        source_ids,
        page_size=1,
        max_sources=len(source_ids),
        chars_used=sum(dict(inventory.child_char_lengths).values()),
    )
    panel = _panel(inventory, page_size=1)
    panel["page_size"] = 2
    media = [
        {"media_id": inventory.skill_media_ids[0], "asset_type": "skill", "url": "https://assets.test/s.webp"},
        *panel["lines"][0]["variants"],
    ]
    transcript = {
        "sources": [{"child_id": child_id} for child_id in source_ids],
        "route": route,
        "media": media,
        "media_panels": [panel],
    }
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "done", "data": {**transcript, "answer": "ok"}},
        ],
    )
    monkeypatch.setattr(evaluator, "follow_voice_pages", lambda *_args, **_kwargs: [panel])

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=1,
        budgets={"max_sources": len(source_ids), "context_budget_chars": 100},
        timeout=1.0,
    )

    assert "voice_page_size_config_mismatch" in result["failures"]


def test_evaluate_entity_rejects_duplicate_and_malformed_voice_panels(monkeypatch):
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = len(inventory.playable_voice_line_ids)
    transcript = _transcript_for_inventory(inventory, page_size=page_size)
    valid_panel = transcript["media_panels"][0]
    transcript["media_panels"] = [valid_panel, dict(valid_panel), {"type": "voice"}, "invalid", {"type": "video"}]
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "done", "data": {**transcript, "answer": "ok"}},
        ],
    )
    monkeypatch.setattr(evaluator, "follow_voice_pages", lambda *_args, **_kwargs: [valid_panel])

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=page_size,
        budgets={"max_sources": 20, "context_budget_chars": 9000},
        timeout=1.0,
    )

    assert "sources_voice_panel_count:2" in result["failures"]
    assert "done_voice_panel_count:2" in result["failures"]
    assert "malformed_voice_panel:2" in result["failures"]
    assert "malformed_media_panel:3" in result["failures"]
    assert "malformed_media_panel:4" in result["failures"]


@pytest.mark.parametrize("bad_answer", ["   ", 1, None])
def test_evaluate_entity_requires_complete_done_event_and_nonempty_answer(monkeypatch, bad_answer):
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    page_size = len(inventory.playable_voice_line_ids)
    transcript = _transcript_for_inventory(inventory, page_size=page_size)
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "done", "data": {"answer": bad_answer}},
        ],
    )
    monkeypatch.setattr(evaluator, "follow_voice_pages", lambda *_args, **_kwargs: transcript["media_panels"])

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=page_size,
        budgets={"max_sources": 20, "context_budget_chars": 9000},
        timeout=1.0,
    )

    assert "done_answer_missing" in result["failures"]
    assert "done_sources_invalid" in result["failures"]
    assert "done_route_invalid" in result["failures"]
    assert "done_media_invalid" in result["failures"]
    assert "done_voice_panel_count:0" in result["failures"]


def test_evaluate_entity_appends_traversal_error_to_prior_sse_failures(monkeypatch):
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    transcript = _transcript_for_inventory(inventory, page_size=1)
    monkeypatch.setattr(
        evaluator,
        "fetch_sse_events",
        lambda *_args, **_kwargs: [
            {"event": "sources", "data": transcript},
            {"event": "error", "data": {"message": "partial"}},
            {"event": "done", "data": {**transcript, "answer": "ok"}},
        ],
    )
    monkeypatch.setattr(
        evaluator,
        "follow_voice_pages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(evaluator.EvaluationTransportError("page_network_error")),
    )

    result = evaluator._evaluate_entity(
        inventory,
        base_url="http://127.0.0.1:1",
        page_size=1,
        budgets={"max_sources": 20, "context_budget_chars": 9000},
        timeout=1.0,
    )

    assert "sse_error_event" in result["failures"]
    assert "transport_error:page_network_error" in result["failures"]


def test_evaluate_all_voice_pages_rejects_contract_and_geometry_violations():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    pages = [
        _panel(inventory, page_size=1, start=index)
        for index in range(len(inventory.playable_voice_line_ids))
    ]
    pages[0]["type"] = "video"
    pages[0]["grouping"] = "flat"
    pages[0]["lines"] = []
    pages[0]["next_cursor"] = ""
    pages[1]["entity_id"] = "foreign-entity"
    pages[1]["page_size"] = 2
    pages[1]["next_cursor"] = "unexpected-terminal-cursor"

    failures = evaluator.evaluate_all_voice_pages(inventory, pages)

    assert "voice_page_type_mismatch:0" in failures
    assert "voice_page_grouping_mismatch:0" in failures
    assert "voice_nonterminal_geometry_mismatch:0" in failures
    assert "voice_next_cursor_mismatch:0" in failures
    assert "voice_page_entity_mismatch:1" in failures
    assert "voice_page_size_mismatch:1" in failures
    assert "voice_terminal_cursor_present:1" in failures


def test_follow_voice_pages_bounds_declared_geometry_and_absolute_ceiling(monkeypatch):
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    first = _panel(inventory, page_size=1)
    second = _panel(inventory, page_size=1, start=1)
    second["has_more"] = True
    second["next_cursor"] = "extra-cursor"
    monkeypatch.setattr(evaluator, "fetch_voice_page", lambda *_args, **_kwargs: second)

    with pytest.raises(evaluator.EvaluationTransportError, match="voice_page_limit_exceeded"):
        evaluator.follow_voice_pages("http://127.0.0.1:1", first, timeout=1.0, max_pages=10_000)


def test_evaluate_all_voice_pages_reports_invalid_page_size_on_each_page():
    inventory, _child_rows, _media_rows = _evaluation_fixture()
    pages = [
        _panel(inventory, page_size=1, start=index)
        for index in range(len(inventory.playable_voice_line_ids))
    ]
    for page in pages:
        page["page_size"] = 0

    failures = evaluator.evaluate_all_voice_pages(inventory, pages)

    assert {
        f"voice_page_size_invalid:{index}"
        for index in range(len(pages))
    }.issubset(failures)

    first = _panel(inventory, page_size=1)
    first["total_lines"] = evaluator.MAX_VOICE_PAGES + 1
    with pytest.raises(evaluator.EvaluationTransportError, match="voice_page_absolute_limit_exceeded"):
        evaluator.follow_voice_pages("http://127.0.0.1:1", first, timeout=1.0, max_pages=10_000)


def test_report_uses_retriever_max_source_budget_default():
    cfg = SimpleNamespace(
        rag=SimpleNamespace(top_k=37),
        retrieval=SimpleNamespace(context_budget_chars=9000, voice_page_size=8, voice_page_size_max=20),
    )

    report = evaluator.run_evaluation(
        cfg,
        base_url="http://127.0.0.1:1",
        inventory=[],
        before_snapshot_reference="eval/before.json",
    )

    assert report["config"]["max_sources"] == 20


def test_run_evaluation_ignores_lower_limit_for_required_eligible_gate(monkeypatch):
    eligible = [
        evaluator.CharacterInventory(
            entity_id=f"entity-{index:02d}",
            entity_name=f"name-{index:02d}",
            skill_child_ids=(f"skill-{index}",),
            voice_text_child_ids=(f"voice-{index}",),
            playable_voice_line_ids=(f"voice-{index}",),
            playable_media_ids=(f"media-{index}",),
            languages=("zh",),
        )
        for index in range(10)
    ]
    monkeypatch.setattr(
        evaluator,
        "_evaluate_entity",
        lambda item, **_kwargs: {
            "entity_id": item.entity_id,
            "failures": [],
            "pass": True,
        },
    )
    cfg = SimpleNamespace(
        rag=SimpleNamespace(top_k=20),
        retrieval=SimpleNamespace(context_budget_chars=9000, voice_page_size=8, voice_page_size_max=20),
    )

    report = evaluator.run_evaluation(
        cfg,
        base_url="http://127.0.0.1:1",
        inventory=eligible,
        before_snapshot_reference="eval/before.json",
        limit=1,
    )

    assert len(report["selected_entities"]) == min(8, len(eligible))
    assert report["config"]["sample_limit"] == 8


def test_run_evaluation_labels_additional_sample_as_anomaly(monkeypatch):
    eligible = [
        evaluator.CharacterInventory(
            entity_id=f"entity-{index:02d}",
            entity_name=f"name-{index:02d}",
            skill_child_ids=(f"skill-{index}",),
            voice_text_child_ids=(f"voice-{index}",),
            playable_voice_line_ids=(f"voice-{index}",),
            playable_media_ids=(f"media-{index}",),
            languages=("zh",),
        )
        for index in range(10)
        if index != 2
    ]
    partial = evaluator.CharacterInventory(
        entity_id="entity-02",
        entity_name="partial",
        skill_child_ids=("skill-partial",),
        voice_text_child_ids=("voice-playable", "voice-text-only"),
        playable_voice_line_ids=("voice-playable",),
        playable_media_ids=("media-playable",),
        languages=("zh",),
    )
    observed_types: list[str] = []

    def fake_evaluate(item, **kwargs):
        observed_types.append(kwargs["sample_type"])
        return {"entity_id": item.entity_id, "sample_type": kwargs["sample_type"], "failures": [], "pass": True}

    monkeypatch.setattr(evaluator, "_evaluate_entity", fake_evaluate)
    cfg = SimpleNamespace(
        rag=SimpleNamespace(top_k=20),
        retrieval=SimpleNamespace(context_budget_chars=9000, voice_page_size=8, voice_page_size_max=20),
    )

    report = evaluator.run_evaluation(
        cfg,
        base_url="http://127.0.0.1:1",
        inventory=[*eligible, partial],
        before_snapshot_reference="eval/before.json",
        limit=1,
    )

    assert observed_types == ["eligible"] * min(8, len(eligible) + 1) + ["anomaly"]
    assert report["eligible_sample_count"] == 8
    assert report["anomaly_sample_count"] == 1
