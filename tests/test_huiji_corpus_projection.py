from __future__ import annotations

import hashlib
import json

from src.huiji_rag.build.projection import project_crawler_semantics


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
