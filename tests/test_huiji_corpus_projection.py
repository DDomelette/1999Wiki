from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from src.huiji_rag.build.projection import (
    CorpusProjection,
    compose_corpus_projection,
    project_crawler_semantics,
    validate_corpus_projection,
)
from src.huiji_rag.build.wikitext_projection import (
    PageChildProjection,
    PageDiagnostic,
    PageParentProjection,
    PageProjection,
    PageSectionProjection,
)


def _row(title: str, content: dict[str, object], *, revid: int = 1) -> dict[str, object]:
    encoded = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    return {
        "title": title,
        "revid": revid,
        "content": encoded,
        "content_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _character() -> dict[str, object]:
    return {
        "id": 7,
        "name": "样本角色",
        "nameEng": "Sample",
        "rare": 5,
        "career": 2,
        "dmgType": 1,
        "skinId": 701,
        "character_data": [
            {"id": 1, "type": 1, "title": "", "text": "样本档案。"},
            {
                "id": 2,
                "type": 2,
                "number": 1,
                "title": "怀表",
                "titleEn": "Pocket Watch",
                "estimate": "1#20",
                "text": "一枚旧怀表。",
                "icon": "7001",
            },
            {
                "id": 5,
                "type": 3,
                "number": 1,
                "title": "远行",
                "titleEn": "The Journey",
                "text": "关于一次远行的记录。",
            },
            {
                "type": 2,
                "number": 2,
                "title": "无编号藏品",
                "text": "没有图片也必须保留。",
            },
        ],
        "skill": {
            "7011": {
                "id": 7011,
                "icon": 7011,
                "name": "第一技能",
                "skillRank": 1,
                "desc_art": "第一阶。",
            },
            "7012": {
                "id": 7012,
                "icon": 7011,
                "name": "第一技能",
                "skillRank": 2,
                "desc_art": "第二阶。",
            },
            "7031": {
                "id": 7031,
                "icon": 7031,
                "name": "终仪",
                "skillRank": 0,
                "desc_art": "最终效果。",
            },
        },
        "character_voice": [
            {
                "heroId": 7,
                "audio": 1701,
                "name": "初遇",
                "eventName": "play_sample_hello",
                "content": "你好。#0|很高兴见到你。#1.2",
                "encontent": "Hello.#0",
            }
        ],
        "skin": [
            {
                "id": 701,
                "name": "初始衣着",
                "largeIcon": "701",
                "live2d": "701_live",
                "verticalDrawing": "701_portrait",
                "live2dbg": "701_bg",
            }
        ],
    }


def _empty_projection() -> CorpusProjection:
    return CorpusProjection(
        parents=(),
        children=(),
        voice_sources=(),
        media_intents=(),
        exclusions=(),
        identity_fallbacks=(),
        record_links=(),
    )


def _chunked_page_projection() -> PageProjection:
    source_row_id = "wikitext:7:11:100:5100"
    source_ref = {
        "source_kind": "crawler_wikitext",
        "source_title": "Chunk Fixture",
        "source_content_sha256": "a" * 64,
        "source_row_id": source_row_id,
        "pageid": 7,
        "revid": 11,
        "char_start": 100,
        "char_end": 5100,
    }
    child_ids = (
        "page:7/section:lead/chunk:0000",
        "page:7/section:lead/chunk:0001",
    )
    children = tuple(
        PageChildProjection(
            category="page",
            entity_type="page",
            entity_id="page:7",
            entity_name="Chunk Fixture",
            entity_aliases=(),
            owner_entity_id="page:7",
            owner_page_id="page:7",
            route_tags=("page",),
            parent_id="page:7/section:lead",
            child_id=child_id,
            heading_path=("lead",),
            section_kind="lead",
            content=f"Chunk {index}",
            text=f"Chunk {index}",
            search_text=f"Chunk Fixture Chunk {index}",
            source_refs=(dict(source_ref),),
            quality_flags=(),
            content_hash=hashlib.sha256(f"Chunk {index}".encode()).hexdigest(),
        )
        for index, child_id in enumerate(child_ids)
    )
    return PageProjection(
        pages=(
            PageParentProjection(
                parent_id="page:7",
                entity_id="page:7",
                entity_name="Chunk Fixture",
                entity_aliases=(),
                child_ids=(),
                source_refs=(dict(source_ref),),
                content_hash="b" * 64,
            ),
        ),
        sections=(
            PageSectionProjection(
                parent_id="page:7/section:lead",
                root_parent_id="page:7",
                heading_path=("lead",),
                child_ids=child_ids,
                source_refs=(dict(source_ref),),
            ),
        ),
        children=children,
        image_references=(),
        media_intents=(),
        redirects=(),
        diagnostics=(),
        exclusions=(),
    )


def test_page_chunks_qualify_shared_source_span_with_stable_chunk_identity() -> None:
    page_projection = _chunked_page_projection()

    first = compose_corpus_projection(_empty_projection(), page_projection)
    second = compose_corpus_projection(_empty_projection(), page_projection)

    assert [child.stable_source_token for child in first.children] == [
        "wikitext:7:11:100:5100:chunk:0000",
        "wikitext:7:11:100:5100:chunk:0001",
    ]
    assert [child.source_token_kind for child in first.children] == [
        "crawler_wikitext_span",
        "crawler_wikitext_span",
    ]
    assert {
        child.block.source_refs[0]["source_row_id"] for child in first.children
    } == {"wikitext:7:11:100:5100"}
    assert [child.stable_source_token for child in second.children] == [
        child.stable_source_token for child in first.children
    ]


def test_true_duplicate_page_chunk_remains_fail_closed() -> None:
    page_projection = _chunked_page_projection()
    duplicate = page_projection.children[0]
    invalid = replace(
        page_projection,
        children=(duplicate, duplicate),
        sections=(
            replace(
                page_projection.sections[0],
                child_ids=(duplicate.child_id, duplicate.child_id),
            ),
        ),
    )

    with pytest.raises(ValueError, match="duplicate child IDs"):
        compose_corpus_projection(_empty_projection(), invalid)


def test_repeated_heading_exclusions_use_deterministic_occurrence_source_identity() -> None:
    page_projection = _chunked_page_projection()
    source_hash = page_projection.children[0].source_refs[0]["source_content_sha256"]
    diagnostics = (
        PageDiagnostic(
            reason_code="duplicate_heading_path_occurrence",
            pageid=7,
            source_title="Chunk Fixture",
            revid=11,
            source_content_sha256=source_hash,
            char_start=120,
            char_end=130,
            heading_path=("lead",),
        ),
        PageDiagnostic(
            reason_code="duplicate_heading_path_occurrence",
            pageid=7,
            source_title="Chunk Fixture",
            revid=11,
            source_content_sha256=source_hash,
            char_start=220,
            char_end=230,
            heading_path=("lead",),
        ),
    )
    diagnostic_projection = replace(page_projection, diagnostics=diagnostics)

    first = compose_corpus_projection(_empty_projection(), diagnostic_projection)
    second = compose_corpus_projection(_empty_projection(), diagnostic_projection)
    exclusions = [
        item
        for item in first.exclusions
        if item.reason_code == "duplicate_heading_path_occurrence"
    ]

    assert len(exclusions) == 2
    assert len({item.source_identity for item in exclusions}) == 2
    assert [item.source_identity for item in exclusions] == [
        item.source_identity
        for item in second.exclusions
        if item.reason_code == "duplicate_heading_path_occurrence"
    ]
    assert {
        (
            item.source_title,
            item.source_content_sha256,
            item.details["pageid"],
            item.details["revid"],
            item.details["char_start"],
            item.details["char_end"],
            tuple(item.details["heading_path"]),
        )
        for item in exclusions
    } == {
        ("Chunk Fixture", source_hash, 7, 11, 120, 130, ("lead",)),
        ("Chunk Fixture", source_hash, 7, 11, 220, 230, ("lead",)),
    }
    assert all("Chunk 0" not in str(item.to_json()) for item in exclusions)
    assert all("Chunk 1" not in str(item.to_json()) for item in exclusions)


def test_projection_builds_canonical_sections_ids_and_business_fields() -> None:
    rows = [
        _row("Data:Char/map.json", {"name": {"样本角色": 7}}),
        _row("Data:Char/7.json", _character()),
    ]

    projection = project_crawler_semantics(rows)
    parent_ids = {item.parent_id for item in projection.parents}
    children = {item.block.child_id: item for item in projection.children}

    assert parent_ids >= {
        "char:7",
        "char:7/profile",
        "char:7/dossier",
        "char:7/collection",
        "char:7/culture_dossier",
        "char:7/skills",
        "char:7/voice",
    }
    collection = children["char:7/collection/2"]
    assert collection.owner_entity_id == "character:7"
    assert collection.block.section_kind == "collection"
    assert collection.name_en == "Pocket Watch"
    assert collection.valuation == "1#20"
    assert collection.description == "一枚旧怀表。"
    assert collection.ordinal == 1
    assert collection.block.text == "怀表\n一枚旧怀表。"
    assert collection.media_binding_tokens == ("collection:2:7001",)

    culture = children["char:7/culture_dossier/5"]
    assert culture.block.section_kind == "culture_dossier"
    assert culture.name_en == "The Journey"
    assert culture.ordinal == 1

    voice = children["char:7/voice/play_sample_hello"]
    assert voice.block.text == "初遇\n中文: 你好。\n很高兴见到你。\nEN: Hello."
    assert projection.voice_sources[0].child_id == voice.block.child_id
    assert {item.language for item in projection.voice_sources} == {"zh", "en"}
    assert voice.source_fields["audio_ids"] == ["1701"]
    assert voice.media_binding_tokens == (
        "voice:play_sample_hello:zh",
        "voice:play_sample_hello:en",
    )

    skin_intents = {
        (item.media_role, item.resource_stem)
        for item in projection.media_intents
        if item.section == "profile"
    }
    assert skin_intents >= {
        ("roster_avatar", "Headicon_large-701"),
        ("stage_live2d", "L2d_static-701_live"),
        ("stage_portrait", "L2d_static-701_portrait"),
        ("skin_background", "Skin_bg-701_bg"),
    }

    skills = [item for item in projection.children if item.block.section_kind == "skill"]
    assert [item.block.child_id for item in skills] == [
        "char:7/skills/skill-7011",
        "char:7/skills/ultimate-7031",
    ]
    assert "星级 1 / Rank 1: 第一阶。" in skills[0].block.text
    assert "至终的仪式: 最终效果。" in skills[1].block.text


def test_skill_and_ultimate_ids_are_separate_namespaces() -> None:
    character = _character()
    character["skill"] = {
        "normal-1": {
            "id": 7101,
            "icon": 7131,
            "name": "普通技能",
            "skillRank": 1,
            "desc_art": "普通效果。",
        },
        "ultimate": {
            "id": 7131,
            "icon": 7141,
            "name": "至终仪式",
            "skillRank": 0,
            "desc_art": "终结效果。",
        },
    }

    projection = project_crawler_semantics([_row("Data:Char/7.json", character)])
    skills = {
        item.block.child_id: item
        for item in projection.children
        if item.block.section_kind == "skill"
    }

    assert set(skills) == {
        "char:7/skills/skill-7131",
        "char:7/skills/ultimate-7131",
    }
    assert skills["char:7/skills/ultimate-7131"].source_fields["icon_id"] == "7141"
    links = {item.legacy_id for item in projection.record_links}
    assert "char:7/skill:7131" in links
    assert "char:7/ultimate:7131" in links


def _shared_skill_character(entity_id: int) -> dict[str, object]:
    return {
        "id": entity_id,
        "name": f"Character {entity_id}",
        "skill": {
            "normal": {
                "id": 30030111,
                "icon": 30030111,
                "name": "Shared Skill",
                "skillRank": 1,
                "desc_art": "Shared skill description.",
            },
            "ultimate": {
                "id": 30030131,
                "icon": 30030131,
                "name": "Shared Ultimate",
                "skillRank": 0,
                "desc_art": "Shared ultimate description.",
            },
        },
    }


def test_shared_skill_assets_use_owner_qualified_relation_tokens() -> None:
    rows = [
        _row("Data:Char/3003.json", _shared_skill_character(3003), revid=30030),
        _row("Data:Char/9999.json", _shared_skill_character(9999), revid=99990),
    ]

    first = project_crawler_semantics(rows)
    second = project_crawler_semantics(rows)
    validate_corpus_projection(first)

    expected = {
        "skill:char:3003:30030111:30030111",
        "ultimate:char:3003:30030131:30030131",
        "skill:char:9999:30030111:30030111",
        "ultimate:char:9999:30030131:30030131",
    }
    skill_intents = [
        intent for intent in first.media_intents if intent.media_role == "skill"
    ]
    assert {intent.source_binding_token for intent in skill_intents} == expected
    assert {intent.resource_stem for intent in skill_intents} == {
        "Skill-30030111",
        "Skill-30030131",
    }
    children = {
        child.block.child_id: child
        for child in first.children
        if child.block.section_kind == "skill"
    }
    assert all(
        children[intent.child_id].media_binding_tokens
        == (intent.source_binding_token,)
        for intent in skill_intents
    )
    assert [
        intent.source_binding_token
        for intent in second.media_intents
        if intent.media_role == "skill"
    ] == [intent.source_binding_token for intent in skill_intents]


def test_true_duplicate_skill_media_relation_remains_fail_closed() -> None:
    projection = project_crawler_semantics(
        [_row("Data:Char/3003.json", _shared_skill_character(3003))]
    )
    intent = next(
        item for item in projection.media_intents if item.media_role == "skill"
    )

    with pytest.raises(ValueError, match="duplicate media source identities"):
        validate_corpus_projection(
            replace(projection, media_intents=(*projection.media_intents, intent))
        )


def test_voice_projection_groups_duplicate_event_occurrences_and_keeps_evidence() -> None:
    character = _character()
    first = dict(character["character_voice"][0])
    second = {**first, "audio": 1702, "skins": "night", "encontent": "Hello!#0"}
    third = {**first, "audio": 1703, "skins": "day", "encontent": "Hello.#1"}
    character["character_voice"] = [first, second, third]

    projection = project_crawler_semantics([_row("Data:Char/7.json", character)])
    voice_children = [
        item for item in projection.children if item.block.section_kind == "voice"
    ]

    assert len(voice_children) == 1
    voice = voice_children[0]
    assert voice.block.child_id == "char:7/voice/play_sample_hello"
    assert "EN: Hello." in voice.block.text
    assert voice.source_fields["audio_ids"] == ["1701", "1702", "1703"]
    assert voice.source_fields["skin_scopes"] == ["night", "day"]
    assert len(voice.source_fields["transcript_evidence"]["en"]["variants"]) == 3
    assert "source_transcript_variant_resolved" in voice.block.quality_flags
    legacy_links = {
        item.legacy_id: item.candidate_id
        for item in projection.record_links
        if item.legacy_id.startswith("char:7/voice:")
    }
    assert legacy_links == {
        "char:7/voice:1701": voice.block.child_id,
        "char:7/voice:1702": voice.block.child_id,
        "char:7/voice:1703": voice.block.child_id,
    }
    assert {item.source_id for item in projection.voice_sources} == {
        "char:7/voice/play_sample_hello:zh",
        "char:7/voice/play_sample_hello:en",
    }


def test_nested_skill_sources_keep_json_index_paths() -> None:
    character = _character()
    character["skill"] = [
        [
            {
                "id": 7011,
                "icon": 7011,
                "name": "第一技能",
                "skillRank": 1,
                "desc_art": "第一阶。",
            }
        ]
    ]

    projection = project_crawler_semantics([_row("Data:Char/7.json", character)])
    skill = next(
        item for item in projection.children if item.block.section_kind == "skill"
    )

    assert skill.block.source_refs[0]["json_path"] == "$.skill.0.0"


def test_projection_keeps_text_without_media_and_records_identity_fallback() -> None:
    projection = project_crawler_semantics([_row("Data:Char/7.json", _character())])
    no_image = next(
        item for item in projection.children if item.block.title == "无编号藏品"
    )

    assert no_image.block.text == "无编号藏品\n没有图片也必须保留。"
    assert no_image.media_binding_tokens
    intent = next(
        item
        for item in projection.media_intents
        if item.source_binding_token == no_image.media_binding_tokens[0]
    )
    assert intent.resource_stem == ""
    assert intent.missing_policy == "text_only"
    assert len(projection.identity_fallbacks) == 1
    assert no_image.stable_source_token == projection.identity_fallbacks[0].stable_source_token


def test_udimo_owner_requires_structured_item_name_not_page_title() -> None:
    rows = [
        _row("Data:Char/7.json", _character()),
        _row(
            "Data:Item/udimo-title-only.json",
            {"id": 99, "name": "普通物品", "desc": "标题不能建立角色关系。"},
        ),
    ]
    projection = project_crawler_semantics(rows)
    assert not any(item.block.section_kind == "udimo" for item in projection.children)

    rows.append(
        _row(
            "Data:Item/1/107.json",
            {
                "id": 107,
                "name": "尤提姆贴纸·样本角色",
                "desc": "角色的尤提姆形象。",
                "icon": "107",
            },
        )
    )
    projection = project_crawler_semantics(rows)
    udimo = next(item for item in projection.children if item.block.section_kind == "udimo")
    assert udimo.block.child_id == "char:7/udimo/107"
    assert udimo.owner_page_id == "char:7"
    intent = next(item for item in projection.media_intents if item.media_role == "udimo")
    assert intent.owner_entity_id == "character:7"
    assert intent.resource_stem == "Item-107"


def test_projection_dynamically_excludes_invalid_characters() -> None:
    rows = [
        _row("Data:Char/no-id.json", {"name": "无编号"}),
        _row("Data:Char/no-name.json", {"id": 2, "name": ""}),
        _row("Data:Char/placeholder.json", {"id": 3, "name": "???"}),
        _row("Data:Char/valid.json", {"id": 4, "name": "正常角色"}),
    ]
    projection = project_crawler_semantics(rows)

    assert {item.reason_code for item in projection.exclusions} == {
        "missing_entity_id",
        "empty_entity_name",
        "placeholder_name",
    }
    assert {item.entity_id for item in projection.parents if item.category == "character"} == {"4"}
    assert all(len(item.source_identity) == 64 for item in projection.exclusions)


def test_json_valid_false_wrapper_emits_excluded_evidence_without_parsing_content(
    monkeypatch,
) -> None:
    valid = _row(
        "Data:Item/41.json",
        {"id": 41, "name": "有效邻居", "description": "仍然投影。"},
    )
    invalid_content = '{"id":"must-not-project",'
    invalid = {
        "site": "res1999",
        "pageid": 9001,
        "revid": 9002,
        "title": "Data:Story/invalid.json",
        "content": invalid_content,
        "content_sha256": hashlib.sha256(invalid_content.encode()).hexdigest(),
        "json_valid": False,
        "json_error": "fixture invalid payload",
        "__source_file": "data_pages.jsonl",
        "__source_line_number": 2,
    }
    real_loads = json.loads

    def guarded_loads(value, *args, **kwargs):
        if value == invalid_content:
            raise AssertionError("invalid wrapper content must never be parsed")
        return real_loads(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", guarded_loads)

    projection = project_crawler_semantics([valid, invalid])

    assert [item.reason_code for item in projection.exclusions] == [
        "invalid_data_wrapper"
    ]
    exclusion = projection.exclusions[0]
    assert exclusion.source_title == "Data:Story/invalid.json"
    assert exclusion.details == {
        "json_error": "fixture invalid payload",
        "pageid": 9001,
        "revid": 9002,
        "source_file": "data_pages.jsonl",
        "source_line_number": 2,
    }
    assert all(item.entity_id != "must-not-project" for item in projection.parents)
    assert all(
        item.block.entity_id != "must-not-project" for item in projection.children
    )
    assert not projection.media_intents
    assert any(item.entity_id == "41" for item in projection.parents)


def test_story_stage_replaces_generic_story_profile_projection() -> None:
    rows = [
        _row(
            "Data:Story/304502.json",
            {
                "info": {"title": "Natural Story Name"},
                "steps": [
                    {
                        "id": "opening",
                        "speaker": "Vertin",
                        "text": "The story text survives.",
                        "background": "missing/background.png",
                    }
                ]
            },
        ),
    ]

    projection = project_crawler_semantics(rows)
    story_parent = next(
        parent for parent in projection.parents if parent.entity_type == "story"
    )
    story_children = [
        child for child in projection.children if child.block.entity_type == "story"
    ]

    assert story_parent.parent_id == "story:304502/story"
    assert story_parent.entity_name == "Natural Story Name"
    assert [child.block.child_id for child in story_children] == [
        "story:304502/story/step-opening"
    ]
    assert story_children[0].block.content == "Vertin: The story text survives."
    assert story_children[0].owner_entity_id == "story:304502"
    assert story_children[0].block.source_refs[0]["json_path"] == "$.steps.0"
    assert all(
        parent.parent_id != "story:304502/profile" for parent in projection.parents
    )
