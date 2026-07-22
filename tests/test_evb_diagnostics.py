from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
import scripts.diagnose_huiji_artifacts as diagnostic_script

from src.huiji_rag.diagnostics import (
    classify_binding_conflicts,
    expand_conflict_closure,
    should_stop_mutations,
    transcript_sha256,
)
from src.huiji_rag.models import (
    BindingRecord,
    BindingStatus,
    ConflictResult,
    ResourceRow,
    VoiceSourceRow,
)
from src.huiji_rag.voice_binding import bind_voice_row, index_voice_resources
from scripts.diagnose_huiji_artifacts import (
    resource_rows_for_sources,
    voice_source_rows_from_data_pages,
    write_r03_evidence,
)
from src.huiji_rag.diagnostics import build_quarantine_listing


def _record(
    source_id: str,
    *,
    entity_id: str = "entity:1",
    child_id: str = "child:1",
    language: str = "en",
    event_name: str = "WakeUp",
    transcript: str = "Wake up.",
    expected_filename: str = "En_WakeUp.mp3",
    sha256: str = "a" * 64,
    object_key: str = "voice/en/wake-up.mp3",
    status: BindingStatus = BindingStatus.EXACT,
) -> BindingRecord:
    source = VoiceSourceRow(
        source_id=source_id,
        entity_id=entity_id,
        child_id=child_id,
        language=language,
        event_name=event_name,
        transcript=transcript,
    )
    matches = ()
    if status is not BindingStatus.SHORTFALL:
        matches = (
            ResourceRow(
                filename=expected_filename,
                language=language,
                sha1="b" * 40,
                sha256=sha256,
                resource_id=f"resource:{source_id}",
                object_key=object_key,
            ),
        )
    return BindingRecord.from_match(source, expected_filename, matches, status)


def test_zero_exact_is_shortfall_and_multiple_sha_is_fatal():
    source = VoiceSourceRow(source_id="shortfall", language="en", event_name="WakeUp")
    shortfall = bind_voice_row(source, index_voice_resources(()))
    fatal = bind_voice_row(
        VoiceSourceRow(source_id="fatal", language="en", event_name="WakeUp"),
        index_voice_resources(
            (
                ResourceRow("En_WakeUp.mp3", "en", "a" * 40, "b" * 64),
                ResourceRow("en_wakeup.mp3", "en", "c" * 40, "d" * 64),
            )
        ),
    )

    result = classify_binding_conflicts((shortfall, fatal))

    assert transcript_sha256(None) == hashlib.sha256(b"").hexdigest()
    assert result.shortfall_ids == ("shortfall",)
    assert result.fatal_ids == ("fatal",)
    assert result.root_causes["fatal"] == ("duplicate_eventname_sha",)


def test_same_sha_different_event_and_text_is_quarantined():
    first = _record("first", event_name="WakeUp", transcript="Wake up.")
    second = _record("second", event_name="Attack", transcript="Attack now.")

    result = classify_binding_conflicts((first, second))

    assert result.quarantined_ids == ("first", "second")
    assert result.status_by_id["first"] is BindingStatus.QUARANTINED
    assert result.status_by_id["second"] is BindingStatus.QUARANTINED
    assert result.root_causes["first"] == ("same_sha_different_event_or_text",)


def test_cross_child_is_trigger_then_classified():
    first = _record("first", child_id="child:1")
    second = _record("second", child_id="child:2")

    result = classify_binding_conflicts((first, second))

    assert result.quarantined_ids == ("first", "second")
    assert result.root_causes["first"] == ("cross_child_sha",)
    assert result.root_causes["second"] == ("cross_child_sha",)


def test_shared_sha_across_languages_for_same_event_is_valid_resource_reuse():
    first = _record(
        "first",
        child_id="char:1/voice:1",
        language="en",
        event_name="WakeUp",
        transcript="Chinese transcript",
        expected_filename="En_WakeUp.mp3",
    )
    second = _record(
        "second",
        child_id="char:1/voice:1",
        language="zh",
        event_name="WakeUp",
        transcript="Wake up.",
        expected_filename="Zh_WakeUp.mp3",
    )

    result = classify_binding_conflicts((first, second))

    assert result.quarantined_ids == ()
    assert result.exact_ids == ("first", "second")
    assert result.root_causes["first"] == ()
    assert result.root_causes["second"] == ()


def test_closure_recurses_to_fixed_point_with_hash():
    rows = (
        _record(
            "a",
            entity_id="entity:1",
            child_id="child:a",
            language="en",
            event_name="Alpha",
            expected_filename="En_Alpha_1.mp3",
            sha256="a" * 64,
            object_key="voice/a",
        ),
        _record(
            "b",
            entity_id="entity:1",
            child_id="child:b",
            language="ja",
            event_name="Beta",
            expected_filename="Jp_Beta_1.mp3",
            sha256="b" * 64,
            object_key="voice/b",
        ),
        _record(
            "c",
            entity_id="entity:2",
            child_id="child:c",
            language="zh",
            event_name="Beta",
            expected_filename="Zh_Gamma_1.mp3",
            sha256="c" * 64,
            object_key="voice/c",
        ),
        _record(
            "d",
            entity_id="entity:3",
            child_id="child:d",
            language="tw",
            event_name="Delta",
            expected_filename="Tw_Delta_1.mp3",
            sha256="c" * 64,
            object_key="voice/d",
        ),
        _record(
            "child_only",
            entity_id="entity:child-only",
            child_id="child:a",
            language="ko",
            event_name="ChildOnly",
            expected_filename="Ko_ChildOnly_1.mp3",
            sha256="e" * 64,
            object_key="voice/child-only",
        ),
    )

    closure = expand_conflict_closure({"a"}, rows)

    assert closure.visited_ids == ("a", "b", "c", "d")
    assert closure.round_counts == (1, 1, 1)
    assert closure.visited_counts["rows"] == 4
    assert closure.visited_counts["entities"] == 3
    assert "children" not in closure.visited_counts
    assert closure.whole_corpus_visited is False
    assert closure.closure_sha256 == "f729ae0cbcc8241ebb6918af712a88d5ca2c13f7fbe08f809aa297bfdf99fbe4"


def test_closure_does_not_expand_through_child_id():
    first = _record("first", child_id="child:shared")
    child_only = _record(
        "child_only",
        entity_id="entity:other",
        child_id="child:shared",
        language="ja",
        event_name="Other",
        expected_filename="Ja_Other_1.mp3",
        sha256="b" * 64,
        object_key="voice/other",
    )

    closure = expand_conflict_closure({"first"}, (first, child_only))

    assert closure.visited_ids == ("first",)
    assert closure.round_counts == ()


def test_should_stop_mutations_uses_fatal_ids_not_stop_flag():
    exact = _record("exact")
    result = classify_binding_conflicts((exact,))
    inconsistent = replace(result, stop_mutations=True, fatal_ids=())

    assert should_stop_mutations(inconsistent) is False


def test_fatal_stops_mutations_but_finishes_read_only_closure():
    fatal = _record("fatal", entity_id="entity:1", status=BindingStatus.FATAL)
    linked = _record("linked", entity_id="entity:1")

    result = classify_binding_conflicts((fatal, linked))
    closure = expand_conflict_closure(set(result.fatal_ids), (fatal, linked))

    assert should_stop_mutations(result) is True
    assert closure.visited_ids == ("fatal", "linked")
    assert closure.round_counts == (1,)


def test_runtime_projection_excludes_quarantine():
    exact = _record("exact", sha256="d" * 64)
    first = _record("first", sha256="e" * 64, child_id="child:1")
    second = _record("second", sha256="e" * 64, child_id="child:2")

    result = classify_binding_conflicts((exact, first, second))

    assert result.runtime_ids == ("exact",)
    assert result.quality_flags_by_id["first"] == ("quarantined", "cross_child_sha")
    assert result.quality_flags_by_id["second"] == ("quarantined", "cross_child_sha")


def test_conflict_result_mappings_cannot_be_mutated():
    result = classify_binding_conflicts((_record("exact"),))

    with pytest.raises(TypeError):
        result.status_by_id["exact"] = BindingStatus.FATAL
    with pytest.raises(TypeError):
        result.root_causes["exact"] = ("unexpected",)
    with pytest.raises(TypeError):
        result.quality_flags_by_id["exact"] = ("unexpected",)


def test_conflict_closure_counts_cannot_be_mutated():
    closure = expand_conflict_closure({"exact"}, (_record("exact"),))

    with pytest.raises(TypeError):
        closure.visited_counts["rows"] = 0
    with pytest.raises(TypeError):
        closure.dimension_counts["rows"] = 0


def test_voice_source_rows_include_only_nonempty_transcript_variants():
    rows = voice_source_rows_from_data_pages(
        (
            {
                "title": "Data:Char/7.json",
                "content": json.dumps(
                    {
                        "character_voice": [
                            {
                                "heroId": 7,
                                "audio": 101,
                                "eventName": "WakeUp",
                                "content": "Chinese",
                                "encontent": "English",
                                "twcontent": "   ",
                                "jpcontent": None,
                                "kocontent": "Korean",
                            },
                            {"heroId": 7, "audio": 102, "eventName": "", "content": "ignored"},
                        ]
                    }
                ),
            },
        )
    )

    assert [(row.source_id, row.language, row.transcript) for row in rows] == [
        ("Data:Char/7.json:101:en", "en", "English"),
        ("Data:Char/7.json:101:kr", "kr", "Korean"),
        ("Data:Char/7.json:101:zh", "zh", "Chinese"),
    ]
    assert {row.parent_id for row in rows} == {"char:7/voice"}
    assert {row.child_id for row in rows} == {"char:7/voice:101"}


def test_voice_source_rows_require_character_json_title_and_nonblank_event_name():
    def page(title: str, audio: int, event_name: str) -> dict[str, str]:
        return {
            "title": title,
            "content": json.dumps(
                {
                    "character_voice": [
                        {
                            "heroId": 7,
                            "audio": audio,
                            "eventName": event_name,
                            "content": "Transcript",
                        }
                    ]
                }
            ),
        }

    rows = voice_source_rows_from_data_pages(
        (
            page("Data:Char/7.json", 101, "  WakeUp  "),
            page("Data:Char/7", 102, "NoSuffix"),
            page("Data:Char/7.json.bak", 103, "BackupSuffix"),
            page("Data:Char/nested/7.json", 104, "Nested"),
            page("Other:Char/7.json", 105, "WrongNamespace"),
            page("Data:Char/8.json", 106, "   "),
        )
    )

    assert [(row.source_id, row.event_name) for row in rows] == [
        ("Data:Char/7.json:101:zh", "  WakeUp  ")
    ]


def test_resource_rows_hash_only_exact_language_filename_matches(tmp_path: Path):
    raw_root = tmp_path / "raw"
    matched = raw_root / "assets" / "matched.mp3"
    unmatched = raw_root / "assets" / "unmatched.mp3"
    matched.parent.mkdir(parents=True)
    matched.write_bytes(b"matched")
    unmatched.write_bytes(b"unmatched")
    source = VoiceSourceRow(event_name="WakeUp", language="en", source_id="source")
    hashed: list[Path] = []

    rows, counters = resource_rows_for_sources(
        (
            {"name": "En_WakeUp.mp3", "sha1": "a" * 40, "local_relpath": "assets/matched.mp3"},
            {"name": "En_Unrelated.mp3", "sha1": "b" * 40, "local_relpath": "assets/unmatched.mp3"},
            {"name": "en_WakeUp.mp3", "sha1": "c" * 40, "local_relpath": "assets/unmatched.mp3"},
            {"name": "En_Unrelated.ogg", "sha1": "e" * 40, "local_relpath": "assets/unmatched.mp3"},
        ),
        (source,),
        raw_root,
        sha256_for_path=lambda path: hashed.append(path) or "d" * 64,
    )

    assert [(row.filename, row.language, row.sha256) for row in rows] == [
        ("En_WakeUp.mp3", "en", "d" * 64)
    ]
    assert rows[0].object_key == "reverse1999/voice/aa/" + "a" * 40 + ".mp3"
    assert hashed == [matched]
    assert counters["voice_resource_rows"] == 2
    assert counters["unmatched_voice_resource_rows_not_hashed"] == 1


def test_quarantine_listing_derives_cause_sets_overlap_and_counts():
    first = _record("first", child_id="child:1", event_name="WakeUp", transcript="Wake up.")
    second = _record("second", child_id="child:2", event_name="Attack", transcript="Attack now.")
    listing = build_quarantine_listing((first, second), classify_binding_conflicts((first, second)))

    summary = listing["summary"]
    assert [item["source_id"] for item in listing["quarantined_occurrences"]] == ["first", "second"]
    assert summary["cause_occurrence_sets"]["cross_child_sha"] == ["first", "second"]
    assert summary["cause_occurrence_sets"]["same_sha_different_event_or_text"] == ["first", "second"]
    assert summary["cause_occurrence_sets"]["shared_sha_distinct_binding_key"] == []
    assert summary["cause_occurrence_counts"]["cross_child_sha"] == len(
        summary["cause_occurrence_sets"]["cross_child_sha"]
    )
    assert summary["cause_occurrence_counts"]["same_sha_different_event_or_text"] == len(
        summary["cause_occurrence_sets"]["same_sha_different_event_or_text"]
    )
    assert summary["cause_occurrence_counts"]["shared_sha_distinct_binding_key"] == 0
    assert summary["named_cause_intersection"] == ["first", "second"]
    assert summary["named_cause_intersection_count"] == len(summary["named_cause_intersection"])
    assert summary["named_cause_union"] == ["first", "second"]
    assert summary["named_cause_union_count"] == len(summary["named_cause_union"])
    assert summary["quarantined_total"] == 2


def test_r03_evidence_writes_one_canonical_sidecar_from_final_listing_bytes(tmp_path: Path):
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()
    stale_sidecar = output_dir / "task-3-r03-cross-child-listing.v1.sha256"
    stale_sidecar.write_text("stale\n", encoding="utf-8")
    listing = build_quarantine_listing(
        (_record("first", child_id="child:1"), _record("second", child_id="child:2")),
        classify_binding_conflicts((_record("first", child_id="child:1"), _record("second", child_id="child:2"))),
    )

    result = write_r03_evidence(output_dir, listing)

    listing_path = output_dir / "task-3-r03-cross-child-listing.v1.json"
    sidecar = output_dir / "task-3-r03-cross-child-listing.v1.json.sha256"
    assert sidecar.read_text(encoding="utf-8") == f"{result['listing_sha256']}  {listing_path.name}\n"
    assert hashlib.sha256(listing_path.read_bytes()).hexdigest() == result["listing_sha256"]
    current = json.loads((output_dir / "task-3-r03-current.json").read_text(encoding="utf-8"))
    assert current["cross_child_listing_sha256"] == result["listing_sha256"]
    assert "named_cause_intersection" not in current
    assert "named_cause_union" not in current
    assert not stale_sidecar.exists()


def test_current_summary_cannot_be_supplied_separately_from_listing(tmp_path: Path):
    listing = build_quarantine_listing(
        (_record("first", child_id="child:1"), _record("second", child_id="child:2")),
        classify_binding_conflicts((_record("first", child_id="child:1"), _record("second", child_id="child:2"))),
        provenance={
            "source_input_sha256": {"data_pages.jsonl": "a" * 64},
            "resource_inventory": {"voice_resource_rows": 2},
            "classification": {"classified_rows": 2},
            "closure": {"visited_rows": 2},
            "mutation_client_instantiated": False,
        },
    )

    with pytest.raises(TypeError):
        write_r03_evidence(tmp_path, listing, {"quarantined": 999})

    current = write_r03_evidence(tmp_path, listing)["current"]

    assert current["quarantined"] == listing["summary"]["quarantined_total"]
    assert current["source_input_sha256"] == listing["provenance"]["source_input_sha256"]


def test_r03_generation_builds_the_resource_index_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw_root = tmp_path / "raw"
    assets = raw_root / "assets"
    assets.mkdir(parents=True)
    (assets / "en.mp3").write_bytes(b"en")
    (assets / "zh.mp3").write_bytes(b"zh")
    (raw_root / "data_pages.jsonl").write_text(
        json.dumps(
            {
                "title": "Data:Char/7.json",
                "content": json.dumps(
                    {
                        "character_voice": [
                            {
                                "heroId": 7,
                                "audio": 101,
                                "eventName": "WakeUp",
                                "content": "Chinese",
                                "encontent": "English",
                            }
                        ]
                    }
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (raw_root / "resources_manifest.jsonl").write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"name": "En_WakeUp.mp3", "sha1": "a" * 40, "local_relpath": "assets/en.mp3"},
                {"name": "Zh_WakeUp.mp3", "sha1": "b" * 40, "local_relpath": "assets/zh.mp3"},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    original = diagnostic_script.index_voice_resources
    calls = 0

    def counted_index(rows):
        nonlocal calls
        calls += 1
        return original(rows)

    monkeypatch.setattr(diagnostic_script, "index_voice_resources", counted_index)

    diagnostic_script.generate_r03_evidence(raw_root, tmp_path / "evidence")

    assert calls == 1
