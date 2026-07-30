from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.huiji_rag.build.story_projection import project_stories
from src.huiji_rag.build.projection import project_crawler_semantics


REAL_DATA_PAGES_ENV = "HUIJI_DATA_PAGES_SNAPSHOT"


def _wrapper(
    title: str,
    payload: dict[str, object],
    *,
    revid: int = 11,
    source_content_sha256: str | None = None,
) -> dict[str, object]:
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "site": "res1999",
        "pageid": revid,
        "revid": revid,
        "title": title,
        "content": content,
        "content_sha256": source_content_sha256
        or hashlib.sha256(content.encode()).hexdigest(),
    }


def _story(
    story_id: str,
    payload: dict[str, object],
    *,
    revid: int = 11,
    source_content_sha256: str | None = None,
) -> dict[str, object]:
    return _wrapper(
        f"Data:Story/{story_id}.json",
        payload,
        revid=revid,
        source_content_sha256=source_content_sha256,
    )


def _legacy_story(story_id: str, text: str) -> dict[str, object]:
    return _story(story_id, {"steps": [{"id": "line", "text": text}]})


def _multilingual(chinese: str, english: str = "") -> list[str]:
    return [chinese, "", english, "", "", "", "", ""]


def _real_story_100003_minimized() -> dict[str, object]:
    return _story(
        "100003",
        {
            "info": {"start": "22", "title": "序章0-2.2"},
            "25": {
                "step": ["24"],
                "type": 0,
                "name": _multilingual(""),
                "head_icon": "",
                "audio": "",
                "bool_1": False,
                "text": _multilingual(""),
                "bg": "",
                "choice": [],
            },
            "26": {
                "step": ["25"],
                "type": 1,
                "name": _multilingual("十四行诗", "Sonetto"),
                "head_icon": "3007",
                "audio": "story/100003/26.mp3",
                "bool_1": True,
                "text": _multilingual(
                    "辉光既出，一瞬之内，偷袭者形迹散去。",
                    "As the light shines.",
                ),
                "bg": "story/bg/100003.png",
                "choice": [
                    [
                        "",
                        "",
                        "",
                        _multilingual(""),
                        _multilingual("拾起唱片。", "Pick up the record."),
                        "",
                        "",
                        0,
                        "",
                        "",
                        9,
                    ]
                ],
            },
            "24": {
                "step": [],
                "type": 1,
                "name": _multilingual("维尔汀", "Vertin"),
                "text": _multilingual("继续前进。", "Move on."),
                "choice": [],
            },
        },
        revid=126758,
        source_content_sha256=(
            "1b146e181ebbdfe2bae1d69a6209e4e3fad66cef284b6173610a939b1a24215e"
        ),
    )


def _nested_episode(
    name: str,
    *,
    before: object = 0,
    main: object = "",
    after: object = 0,
    title: str = "Data:Episode/10102.json",
    revid: int = 362384,
) -> dict[str, object]:
    return _wrapper(
        title,
        {
            "episode": {
                "name": name,
                "beforeStory": before,
                "story": main,
                "afterStory": after,
                "pic": "episode/ignored.png",
            }
        },
        revid=revid,
        source_content_sha256=(
            "7f266dc48a3a81312cc5d795be4bac2ccaf7727179a50b07d586380316552466"
        ),
    )


def test_story_uses_payload_name_before_all_relation_names() -> None:
    result = project_stories(
        [
            _real_story_100003_minimized(),
            _nested_episode("Episode Alias", before=100003),
        ]
    )

    assert result.parents[0].entity_name == "序章0-2.2"
    assert result.parents[0].entity_aliases == ("Episode Alias (before)",)
    assert [
        (ref["source_title"], ref["json_path"])
        for ref in result.parents[0].source_refs
    ] == [
        ("Data:Story/100003.json", "$"),
        ("Data:Story/100003.json", "$.info.title"),
        ("Data:Episode/10102.json", "$.episode.beforeStory"),
        ("Data:Episode/10102.json", "$.episode.name"),
    ]


def test_story_uses_exact_chapter_element_name_when_payload_has_no_name() -> None:
    result = project_stories(
        [
            _legacy_story("101", "Line"),
            _wrapper(
                "Data:ChapterElement/1.json",
                {
                    "chapter_map_element": [
                        {"id": 101, "param": "101", "title": "Not a Story relation"}
                    ]
                },
            ),
        ]
    )

    assert result.parents[0].entity_name == "Data:Story/101"
    assert result.parents[0].entity_aliases == ()
    assert [item.reason_code for item in result.diagnostics] == [
        "unsupported_story_relation"
    ]
    assert result.diagnostics[0].source_title == "Data:ChapterElement/1.json"


def test_story_uses_episode_before_main_after_name_with_controlled_phase_label() -> None:
    result = project_stories(
        [
            _legacy_story("201", "Before"),
            _legacy_story("202", "Main"),
            _legacy_story("203", "After"),
            _nested_episode(
                "Episode Nine",
                before=201,
                main="202",
                after=203,
            ),
        ]
    )

    assert [parent.entity_name for parent in result.parents] == [
        "Episode Nine (before)",
        "Episode Nine",
        "Episode Nine (after)",
    ]
    assert [child.block.route_tags for child in result.children] == [
        ("story", "episode"),
        ("story", "episode"),
        ("story", "episode"),
    ]


def test_story_accepts_exact_page_or_data_relation_but_never_fuzzy_similarity() -> None:
    result = project_stories(
        [
            _legacy_story("300", "Fallback"),
            _legacy_story("301", "Exact"),
            _nested_episode("Story 300 Similar Text", before=30),
            _nested_episode("Synthetic Nested ID", main={"storyId": "300"}),
            _nested_episode(
                "Exact Episode Relation",
                main="301",
                title="Data:Episode/10103.json",
                revid=362385,
            ),
        ]
    )

    assert [parent.entity_name for parent in result.parents] == [
        "Data:Story/300",
        "Exact Episode Relation",
    ]


def test_same_priority_story_name_conflict_blocks_only_affected_story() -> None:
    result = project_stories(
        [
            _legacy_story("400", "Blocked"),
            _story(
                "401",
                {"info": {"title": "Healthy"}, "1": {"text": _multilingual("Kept")}},
            ),
            _nested_episode("First Name", main="400"),
            _nested_episode(
                "Second Name",
                main="400",
                title="Data:Episode/10103.json",
                revid=362385,
            ),
        ]
    )

    assert result.blocked_story_ids == ("400",)
    assert [parent.entity_id for parent in result.parents] == ["401"]
    assert "story_name_conflict" in {
        item.reason_code for item in result.diagnostics
    }


def test_lower_priority_names_become_sorted_aliases() -> None:
    result = project_stories(
        [
            _story(
                "500",
                {
                    "info": {"title": "Primary"},
                    "1": {"text": _multilingual("Line")},
                },
            ),
            _nested_episode("Lower Alias", main="500"),
        ]
    )

    assert result.parents[0].entity_aliases == ("Lower Alias",)
    assert result.children[0].block.entity_aliases == ("Lower Alias",)


def test_raw_story_id_fallback_sets_weak_entity_name_and_remains_searchable() -> None:
    result = project_stories([_legacy_story("600", "Line")])
    parent = result.parents[0]
    child = result.children[0]

    assert parent.entity_name == "Data:Story/600"
    assert parent.quality_flags == ("weak_entity_name",)
    assert child.block.quality_flags == ("weak_entity_name",)
    assert "Data:Story/600.json" in child.block.search_text
    assert "600" in child.block.search_text


def test_story_steps_keep_scene_speaker_dialogue_choice_order_and_json_paths() -> None:
    result = project_stories([_real_story_100003_minimized()])

    assert [child.block.content for child in result.children] == [
        "十四行诗: 辉光既出，一瞬之内，偷袭者形迹散去。\nChoice: 拾起唱片。",
        "维尔汀: 继续前进。",
    ]
    assert [child.block.source_refs[0]["json_path"] for child in result.children] == [
        "$.26",
        "$.24",
    ]
    assert [child.block.child_id for child in result.children] == [
        "story:100003/story/step-26",
        "story:100003/story/step-24",
    ]


def test_story_control_fields_resource_paths_and_booleans_do_not_enter_content() -> None:
    result = project_stories([_real_story_100003_minimized()])
    content = "\n".join(child.block.content for child in result.children)

    assert all(
        value not in content
        for value in (
            "story/100003/26.mp3",
            "story/bg/100003.png",
            "3007",
            "True",
            "False",
            "['25']",
        )
    )


def test_story_missing_media_never_removes_text_child() -> None:
    result = project_stories(
        [
            _story(
                "900",
                {
                    "info": {"title": "Text First"},
                    "1": {
                        "name": _multilingual(""),
                        "text": _multilingual("Text survives."),
                        "head_icon": "",
                        "audio": "",
                        "bg": "",
                    },
                },
            )
        ]
    )

    assert [child.block.content for child in result.children] == ["Text survives."]


def test_story_ids_use_business_id_scene_or_stable_step_and_hash_fallback_evidence() -> None:
    numeric = project_stories([_real_story_100003_minimized()])
    legacy = _story(
        "1000",
        {
            "name": "Legacy IDs",
            "steps": [
                {"scene": "Station", "text": "Scene line."},
                {"id": "step-2", "text": "Stable line."},
                {"text": "Fallback line."},
            ],
        },
    )
    first = project_stories([legacy])
    second = project_stories([legacy])

    assert numeric.children[0].stable_source_token == "step-26"
    assert [child.block.child_id for child in first.children] == [
        "story:1000/story/scene-station",
        "story:1000/story/step-step-2",
        first.children[2].block.child_id,
    ]
    assert first.children[2].block.child_id.startswith("story:1000/story/hash-")
    assert first.children[2].block.child_id == second.children[2].block.child_id
    assert len(first.identity_fallbacks) == 1
    assert first.identity_fallbacks[0].json_path == "$.steps.2"


def test_normalized_legacy_steps_container_remains_compatible() -> None:
    result = project_stories(
        [
            _story(
                "1100",
                {
                    "name": "Legacy",
                    "steps": [
                        {
                            "id": "opening",
                            "scene": "Platform",
                            "speaker": "Vertin",
                            "text": "Legacy line.",
                            "choices": ["Choice A"],
                        }
                    ],
                },
            )
        ]
    )

    assert result.children[0].block.content == (
        "Scene: Platform\nVertin: Legacy line.\nChoice: Choice A"
    )
    assert result.children[0].block.source_refs[0]["json_path"] == "$.steps.0"


def test_single_restored_story_row_streams_to_nonempty_children() -> None:
    snapshot_value = os.environ.get(REAL_DATA_PAGES_ENV)
    if not snapshot_value:
        pytest.skip(f"set {REAL_DATA_PAGES_ENV} for opt-in restored-row validation")
    snapshot_path = Path(snapshot_value)
    if not snapshot_path.is_file():
        pytest.skip(f"{REAL_DATA_PAGES_ENV} does not name a readable file")

    selected = None
    with snapshot_path.open("rb") as handle:
        for raw_line in handle:
            wrapper = json.loads(raw_line)
            if wrapper.get("title") == "Data:Story/100003.json":
                selected = wrapper
                break

    assert selected is not None
    result = project_stories([selected])
    assert result.parents[0].entity_name == "序章0-2.2"
    assert result.children
    assert result.children[0].block.source_refs[0]["json_path"].startswith("$.")


def test_story_projection_emits_complete_source_backed_migration_links() -> None:
    source_sha256 = "7" * 64
    projection = project_crawler_semantics(
        [
            _story(
                "9001",
                {
                    "name": "Migration fixture",
                    "steps": [
                        {"id": "second", "text": "Second line."},
                        {"id": "first", "text": "First line."},
                    ],
                },
                source_content_sha256=source_sha256,
            )
        ]
    )

    assert [link.to_json() for link in projection.record_links] == [
        {
            "record_kind": "parent",
            "legacy_id": "story:e327f1d8456f/profile",
            "candidate_id": "story:9001/story",
            "change_kind": "corrected_semantics",
            "source_title": "Data:Story/9001.json",
            "source_content_sha256": source_sha256,
            "json_path": "$",
            "legacy_section": "profile",
            "candidate_section": "story",
        },
        {
            "record_kind": "child",
            "legacy_id": "story:e327f1d8456f:0000",
            "candidate_id": "story:9001/story/step-second",
            "change_kind": "corrected_semantics",
            "source_title": "Data:Story/9001.json",
            "source_content_sha256": source_sha256,
            "json_path": "$.steps.0",
            "legacy_section": "profile",
            "candidate_section": "story",
        },
        {
            "record_kind": "child",
            "legacy_id": "story:e327f1d8456f:0000",
            "candidate_id": "story:9001/story/step-first",
            "change_kind": "corrected_semantics",
            "source_title": "Data:Story/9001.json",
            "source_content_sha256": source_sha256,
            "json_path": "$.steps.1",
            "legacy_section": "profile",
            "candidate_section": "story",
        },
    ]
