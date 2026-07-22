import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import src.assets.huiji_registry as huiji_registry
from src.assets.huiji_registry import HuijiMediaRegistry
from src.huiji_rag.build.contracts import (
    MEDIA_V3_ROW_SCHEMA_VERSION,
    canonical_jsonl_bytes,
    ordered_media_v3_row,
)
from src.huiji_rag.io import write_jsonl
from src.huiji_rag.runtime_artifacts import RuntimeArtifactSnapshot


def _cfg(tmp_path):
    return SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        )
    )


def _plan(
    intent="intro",
    media_intent="none",
    entity="玛蒂尔达",
    secondary_intents=(),
    entity_id=None,
):
    return SimpleNamespace(
        intent=intent,
        secondary_intents=secondary_intents,
        media_intent=media_intent,
        entity=entity,
        entity_type="character",
        entity_id=entity_id,
        resolution_mode="current_exact" if entity_id else "unresolved",
    )


def _v3_snapshot(tmp_path, media_path):
    child_path = tmp_path / "child_blocks.jsonl"
    write_jsonl(child_path, [])
    return RuntimeArtifactSnapshot(
        source_mode="active_pointer",
        capability="v3",
        artifact_schema_version=MEDIA_V3_ROW_SCHEMA_VERSION,
        build_version="candidate-v3",
        build_root=tmp_path,
        manifest_path=tmp_path / "build_manifest.json",
        manifest_sha256="a" * 64,
        parent_blocks=tmp_path / "parent_blocks.jsonl",
        child_blocks=child_path,
        media_assets=media_path,
        child_bm25=tmp_path / "child_bm25.json",
        media_bm25=tmp_path / "media_bm25.json",
        collection_name="candidate-collection",
        artifact_sha256={},
        tuple_sha256="b" * 64,
    )


def test_media_registry_inherits_owner_type_only_from_verified_source_binding(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "media_assets.jsonl",
        [
            {
                "media_id": "owned",
                "entity_id": "owner-a",
                "entity_name": "Shared Name",
                "child_id": "scope:owner-a/profile:0000",
                "parent_id": "scope:owner-a/profile",
                "asset_type": "image",
                "filename": "owned.webp",
                "title": "owned",
                "mime": "image/webp",
                "url": "https://media.example/owned.webp",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
            },
            {
                "media_id": "foreign",
                "entity_id": "owner-b",
                "entity_name": "Shared Name",
                "child_id": "scope:owner-b/profile:0000",
                "parent_id": "scope:owner-b/profile",
                "asset_type": "image",
                "filename": "foreign.webp",
                "title": "foreign",
                "mime": "image/webp",
                "url": "https://media.example/foreign.webp",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
            },
        ],
    )
    registry = HuijiMediaRegistry(_cfg(tmp_path))
    sources = [
        {
            "entity_type": "character",
            "entity_id": "owner-a",
            "entity_name": "Shared Name",
            "child_id": "scope:owner-a/profile:0000",
            "parent_id": "scope:owner-a/profile",
        },
        {
            "entity_type": "character",
            "entity_id": "owner-b",
            "entity_name": "Shared Name",
            "child_id": "scope:owner-b/profile:0000",
            "parent_id": "scope:owner-b/profile",
        },
    ]

    bundle = registry.find_bundle_for_retrieval(
        _plan(entity="Shared Name", media_intent="image", entity_id="owner-a"),
        sources,
    )

    assert [item["media_id"] for item in bundle.items] == ["owned"]
    assert bundle.items[0]["entity_type"] == "character"
    assert bundle.items[0]["entity_id"] == "owner-a"


def test_voice_cursor_keeps_the_verified_owner_across_pages(tmp_path):
    processed = tmp_path / "processed" / "build"

    def voice(media_id, entity_id, line):
        return {
            "media_id": media_id,
            "entity_id": entity_id,
            "entity_name": "Shared Voice Name",
            "child_id": f"scope:{entity_id}/voice:{line:04d}",
            "parent_id": f"scope:{entity_id}/voice",
            "asset_type": "voice",
            "filename": f"zh_{line}.mp3",
            "title": f"line {line}",
            "mime": "audio/mpeg",
            "url": f"https://media.example/{media_id}.mp3",
            "is_available": True,
            "is_common": False,
            "attach_policy": "on_intent",
            "sort_order": line,
            "language": "zh",
        }

    write_jsonl(
        processed / "media_assets.jsonl",
        [
            voice("owned-1", "owner-a", 1),
            voice("owned-2", "owner-a", 2),
            voice("foreign-1", "owner-b", 1),
        ],
    )
    registry = HuijiMediaRegistry(_cfg(tmp_path))
    sources = [
        {
            "entity_type": "character",
            "entity_id": "owner-a",
            "entity_name": "Shared Voice Name",
            "child_id": "scope:owner-a/voice:0001",
            "parent_id": "scope:owner-a/voice",
        },
        {
            "entity_type": "character",
            "entity_id": "owner-b",
            "entity_name": "Shared Voice Name",
            "child_id": "scope:owner-b/voice:0001",
            "parent_id": "scope:owner-b/voice",
        },
    ]

    bundle = registry.find_bundle_for_retrieval(
        _plan(
            intent="voice",
            media_intent="audio",
            entity="Shared Voice Name",
            entity_id="owner-a",
        ),
        sources,
        voice_page_size=1,
    )

    panel = bundle.panels[0]
    assert panel["entity_type"] == "character"
    assert panel["entity_id"] == "owner-a"
    assert panel["total_lines"] == 2
    assert [item["media_id"] for item in bundle.items] == ["owned-1"]
    assert bundle.items[0]["entity_type"] == "character"
    assert bundle.items[0]["entity_id"] == "owner-a"

    next_page = registry.get_voice_page(panel["next_cursor"])

    assert next_page["entity_type"] == "character"
    assert next_page["entity_id"] == "owner-a"
    assert [
        variant["media_id"]
        for line in next_page["lines"]
        for variant in line["variants"]
    ] == ["owned-2"]


def test_media_registry_only_returns_assets_bound_to_final_sources_and_http_urls(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "media_assets.jsonl",
        [
            {
                "media_id": "correct",
                "entity_name": "玛蒂尔达",
                "child_id": "char:3041/profile:0000",
                "parent_id": "char:3041/profile",
                "asset_type": "portrait",
                "filename": "matilda.webp",
                "title": "玛蒂尔达立绘",
                "mime": "image/webp",
                "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/matilda.webp",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
            },
            {
                "media_id": "wrong-source",
                "entity_name": "玛蒂尔达",
                "child_id": "char:3041/voice:0001",
                "parent_id": "char:3041/voice",
                "asset_type": "portrait",
                "filename": "matilda-other.webp",
                "title": "错误来源图片",
                "mime": "image/webp",
                "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/bb/matilda-other.webp",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
            },
            {
                "media_id": "wrong-entity",
                "entity_name": "十四行诗",
                "child_id": "char:3023/profile:0000",
                "parent_id": "char:3023/profile",
                "asset_type": "portrait",
                "filename": "matilda.webp",
                "title": "跨实体噪声",
                "mime": "image/webp",
                "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/cc/noise.webp",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
            },
            {
                "media_id": "local-path",
                "entity_name": "玛蒂尔达",
                "child_id": "char:3041/profile:0000",
                "parent_id": "char:3041/profile",
                "asset_type": "image",
                "filename": "local-path.png",
                "title": "本地路径泄露",
                "mime": "image/png",
                "url": "D:\\assets\\local-path.png",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
            },
            {
                "media_id": "embedded-local-path",
                "entity_name": "玛蒂尔达",
                "child_id": "char:3041/profile:0000",
                "parent_id": "char:3041/profile",
                "asset_type": "image",
                "filename": "embedded-local-path.png",
                "title": "嵌入本地路径",
                "mime": "image/png",
                "url": "https://media.example/image.png?source=d:\\assets\\private.png",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
            },
        ],
    )
    registry = HuijiMediaRegistry(_cfg(tmp_path))

    media = registry.find_for_retrieval(
        _plan(),
        [{"child_id": "char:3041/profile:0000", "parent_id": "char:3041/profile"}],
        limit=8,
    )

    assert [item["media_id"] for item in media] == ["correct"]
    assert media[0]["child_id"] == "char:3041/profile:0000"
    assert media[0]["parent_id"] == "char:3041/profile"
    assert all(item["url"].startswith(("http://", "https://")) for item in media)
    assert all("D:\\" not in str(item) and "C:\\" not in str(item) and "file://" not in str(item) for item in media)


def test_registry_rejects_generic_decoded_local_markers_but_keeps_valid_object_keys(tmp_path):
    processed = tmp_path / "processed" / "build"

    def encode_rounds(value, rounds):
        encoded = value
        for _index in range(rounds):
            encoded = quote(encoded, safe="")
        return encoded

    unsafe_urls = [
        "https://media.example/image.webp?source=R:\\private\\image.webp",
        "https://media.example/image.webp?source=s:/private/image.webp",
        "https://media.example/image.webp?source=FiLe://server/private.webp",
        "https://media.example/images/../private/image.webp",
        "https://media.example/images\\..\\private\\image.webp",
        "https://media.example/image.webp?source=T%3A%5Cprivate%5Cimage.webp",
        "https://media.example/image.webp?source=u%3A%2Fprivate%2Fimage.webp",
        "https://media.example/image.webp?source=FILE%3A%2F%2Fprivate%2Fimage.webp",
        "https://media.example/images/%2E%2E%2Fprivate%2Fimage.webp",
        "file:/etc/passwd",
        "file:\\server\\share\\image.webp",
        "https://media.example/image.webp?source=file:/etc/passwd",
        "https://media.example/image.webp?source=file:\\server\\share\\image.webp",
        "https://media.example/image.webp?source=FILE%3A%5C%5Cserver%5Cshare%5Cimage.webp",
        "https://media.example/image.webp?source=\\\\server\\share\\image.webp",
        "https://media.example/images/\\\\server\\share\\image.webp",
        "https://media.example/images/"
        + encode_rounds("%2E%2E%2Fprivate%2Fimage.webp", 3),
        "https://media.example/image.webp?value="
        + encode_rounds("%2Fstill-changing", 32),
    ]
    rows = [
        {
            "media_id": f"unsafe-{index}",
            "entity_name": "玛蒂尔达",
            "child_id": "char:3041/profile:0000",
            "parent_id": "char:3041/profile",
            "asset_type": "image",
            "filename": f"unsafe-{index}.webp",
            "title": "unsafe",
            "mime": "image/webp",
            "url": url,
            "is_available": True,
            "is_common": False,
            "attach_policy": "auto",
        }
        for index, url in enumerate(unsafe_urls)
    ]
    safe_url = (
        "https://media.example/reverse1999/image/folder..name/image.webp"
        "?redirect=https%3A%2F%2Fcdn.example%2Fimage.webp"
    )
    rows.append(
        {
            "media_id": "safe",
            "entity_name": "玛蒂尔达",
            "child_id": "char:3041/profile:0000",
            "parent_id": "char:3041/profile",
            "asset_type": "image",
            "filename": "safe.webp",
            "title": "safe",
            "mime": "image/webp",
            "url": safe_url,
            "is_available": True,
            "is_common": False,
            "attach_policy": "auto",
        }
    )
    write_jsonl(processed / "media_assets.jsonl", rows)
    registry = HuijiMediaRegistry(_cfg(tmp_path))

    media = registry.find_for_retrieval(
        _plan(),
        [{"child_id": "char:3041/profile:0000", "parent_id": "char:3041/profile"}],
    )

    assert [item["media_id"] for item in media] == ["safe"]
    assert media[0]["url"] == safe_url


def test_media_registry_gates_voice_until_voice_intent(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "media_assets.jsonl",
        [
            {
                "media_id": "voice-1",
                "entity_name": "玛蒂尔达",
                "child_id": "char:3041/voice:0001",
                "parent_id": "char:3041/voice",
                "asset_type": "voice",
                "filename": "voice.mp3",
                "title": "语音",
                "mime": "audio/mpeg",
                "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/voice/aa/voice.mp3",
                "is_available": True,
                "is_common": False,
                "attach_policy": "on_intent",
                "panel_group": "voice:default",
            },
        ],
    )
    registry = HuijiMediaRegistry(_cfg(tmp_path))
    sources = [{"child_id": "char:3041/voice:0001", "parent_id": "char:3041/voice"}]

    assert registry.find_for_retrieval(_plan(intent="intro"), sources) == []
    media = registry.find_for_retrieval(_plan(intent="voice", media_intent="audio"), sources)

    assert [item["media_id"] for item in media] == ["voice-1"]
    assert media[0]["asset_type"] == "voice"
    assert media[0]["panel_group"] == "voice:default"


def test_registry_matches_media_against_composite_source_entity_bindings(tmp_path):
    processed = tmp_path / "processed" / "build"

    def skill_row(media_id, child_id, parent_id, *, entity_name="目标角色", entity_id=None):
        row = {
            "media_id": media_id,
            "entity_name": entity_name,
            "child_id": child_id,
            "parent_id": parent_id,
            "asset_type": "skill",
            "filename": f"{media_id}.webp",
            "title": media_id,
            "mime": "image/webp",
            "url": f"https://media.example/{media_id}.webp",
            "is_available": True,
            "is_common": False,
            "attach_policy": "auto",
        }
        if entity_id is not None:
            row["entity_id"] = entity_id
        return row

    write_jsonl(
        processed / "media_assets.jsonl",
        [
            skill_row("valid-direct", "char:100/skill:0001", "char:100/skills-a"),
            skill_row("valid-parent-expansion", "char:100/skill:0003", "char:100/skills-a"),
            skill_row("cross-entity-pair", "char:100/skill:0001", "char:200/skills"),
            skill_row("cross-prefix-parent", "char:200/skill:0003", "char:100/skills-a"),
            skill_row("same-entity-cross-parent", "char:100/skill:0001", "char:100/skills-b"),
            skill_row(
                "explicit-entity-conflict",
                "char:100/skill:0004",
                "char:100/skills-a",
                entity_id="char:200",
            ),
            skill_row(
                "wrong-plan-name",
                "char:100/skill:0005",
                "char:100/skills-a",
                entity_name="其他角色",
            ),
        ],
    )
    registry = HuijiMediaRegistry(_cfg(tmp_path))
    sources = [
        {
            "entity_id": "char:100",
            "entity_name": "目标角色",
            "child_id": "char:100/skill:0001",
            "parent_id": "char:100/skills-a",
        },
        {
            "entity_id": "char:100",
            "entity_name": "目标角色",
            "child_id": "char:100/skill:0002",
            "parent_id": "char:100/skills-b",
        },
        {
            "entity_id": "char:200",
            "entity_name": "其他角色",
            "child_id": "char:200/skill:0001",
            "parent_id": "char:200/skills",
        },
    ]

    media = registry.find_for_retrieval(
        _plan(intent="skill", entity="目标角色"),
        sources,
    )

    assert [item["media_id"] for item in media] == [
        "valid-direct",
        "valid-parent-expansion",
    ]


def test_registry_builds_voice_page_from_actual_bare_entity_id_schema(tmp_path):
    processed = tmp_path / "processed" / "build"
    rows = [
        {
            "media_id": f"voice-{line}-{language}",
            "entity_id": "3003",
            "entity_name": "槲寄生",
            "child_id": f"char:3003/voice:130030{line}",
            "parent_id": "char:3003/voice",
            "asset_type": "voice",
            "filename": f"{language}_play_mianvoc_hero3003_0{line}.mp3",
            "title": f"voice {line} {language}",
            "mime": "audio/mpeg",
            "url": f"https://media.example/voice-{line}-{language}.mp3",
            "is_available": True,
            "is_common": False,
            "attach_policy": "on_intent",
            "sort_order": order,
        }
        for line in (1, 2)
        for language, order in (("En", 1), ("Jp", 2))
    ]
    rows.append(
        {
            **rows[0],
            "media_id": "conflicting-entity",
            "entity_id": "3004",
            "filename": "Zh_conflicting.mp3",
            "url": "https://media.example/conflicting.mp3",
        }
    )
    write_jsonl(processed / "media_assets.jsonl", rows)
    registry = HuijiMediaRegistry(_cfg(tmp_path))
    source = {
        "entity_id": "3003",
        "entity_name": "槲寄生",
        "child_id": "char:3003/voice:1300301",
        "parent_id": "char:3003/voice",
    }

    bundle = registry.find_bundle_for_retrieval(
        _plan(intent="voice", media_intent="audio", entity="槲寄生"),
        [source],
        voice_page_size=8,
    )

    assert len(bundle.panels) == 1
    panel = bundle.panels[0]
    assert panel["entity_id"] == "char:3003"
    assert panel["total_lines"] == 2
    assert [line["voice_line_id"] for line in panel["lines"]] == [
        "char:3003/voice:1300301",
        "char:3003/voice:1300302",
    ]
    assert {item["media_id"] for item in bundle.items} == {
        "voice-1-En",
        "voice-1-Jp",
        "voice-2-En",
        "voice-2-Jp",
    }


def test_voice_bundle_returns_current_parent_page_and_stable_followup(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": "char:3041/voice:0001",
                "parent_id": "char:3041/voice",
                "entity_name": "玛蒂尔达",
                "text": "初遇\n中文: 喂，你为什么会在这里？！\nEN: Hey, why are you here?\n日: な、なんであなたがここに！？\n韩: 어이, 네가 여긴 어쩐 일이야?!",
            },
            {
                "child_id": "char:3041/voice:0002",
                "parent_id": "char:3041/voice",
                "entity_name": "玛蒂尔达",
                "text": "问候\n中文: 进门之前，请先敲门！\nEN: Knock first!\n日: 入る前には必ずノックをしなさい！\n韩: 들어오기 전에 노크부터 해줘!",
            },
            {
                "child_id": "char:3041/voice:0003",
                "parent_id": "char:3041/voice",
                "entity_name": "玛蒂尔达",
                "text": "受敌\n中文: 可恶！\nEN: How dare you!\n日: 許せない！\n韩: 용서 못 해!",
            },
            {
                "child_id": "char:3041/voice:0004",
                "parent_id": "char:3041/voice",
                "entity_name": "玛蒂尔达",
                "text": "纯文本\n中文: 这一条没有可播放音频。",
            },
        ],
    )
    rows = []
    for child_index in range(1, 4):
        for language, order in (("Zh", 0), ("En", 1), ("Jp", 2), ("Kr", 3)):
            rows.append(
                {
                    "media_id": f"voice-{child_index}-{language}",
                    "entity_name": "玛蒂尔达",
                    "child_id": f"char:3041/voice:000{child_index}",
                    "parent_id": "char:3041/voice",
                    "asset_type": "voice",
                    "filename": f"{language}_play_mianvoc_hero3041_{child_index:02d}.mp3",
                    "title": f"文件:{language} play mianvoc hero3041 {child_index:02d}.mp3",
                    "mime": "audio/mpeg",
                    "url": f"http://127.0.0.1:9002/reverse1999-assets/reverse1999/voice/{child_index}/{language}.mp3",
                    "is_available": True,
                    "is_common": False,
                    "attach_policy": "on_intent",
                    "panel_group": "voice:default",
                    "sort_order": order,
                }
            )
    write_jsonl(processed / "media_assets.jsonl", rows)
    registry = HuijiMediaRegistry(_cfg(tmp_path))

    bundle = registry.find_bundle_for_retrieval(
        _plan(intent="voice", media_intent="audio", entity="玛蒂尔达"),
        [{"child_id": "char:3041/voice:0001", "parent_id": "char:3041/voice"}],
        limit=8,
        voice_page_size=2,
    )

    assert isinstance(bundle, huiji_registry.MediaRetrievalBundle)
    assert len(bundle.items) == 8
    assert len(bundle.panels) == 1
    panel = bundle.panels[0]
    assert panel["type"] == "voice"
    assert panel["grouping"] == "voice_line"
    assert panel["entity_id"] == "char:3041"
    assert [line["voice_line_id"] for line in panel["lines"]] == [
        "char:3041/voice:0001",
        "char:3041/voice:0002",
    ]
    assert [line["title"] for line in panel["lines"]] == [
        "喂，你为什么会在这里？！",
        "进门之前，请先敲门！",
    ]
    assert panel["page_size"] == 2
    assert panel["total_lines"] == 3
    assert panel["has_more"] is True
    assert panel["next_cursor"]
    assert {item["media_id"] for item in bundle.items} == {
        f"voice-{child_index}-{language}"
        for child_index in (1, 2)
        for language in ("Zh", "En", "Jp", "Kr")
    }
    assert any(item["title"] == "(中文) 喂，你为什么会在这里？！" for item in bundle.items)
    assert any(item["title"] == "(EN) Knock first!" for item in bundle.items)
    assert {item["language"] for item in bundle.items} == {"zh", "en", "jp", "kr"}

    next_page = registry.get_voice_page(panel["next_cursor"])
    repeated_page = registry.get_voice_page(panel["next_cursor"])

    assert next_page == repeated_page
    assert [line["voice_line_id"] for line in next_page["lines"]] == [
        "char:3041/voice:0003"
    ]
    assert next_page["has_more"] is False
    assert next_page["next_cursor"] is None
    all_line_ids = {
        line["voice_line_id"]
        for page in (panel, next_page)
        for line in page["lines"]
    }
    all_media_ids = {
        variant["media_id"]
        for page in (panel, next_page)
        for line in page["lines"]
        for variant in line["variants"]
    }
    assert all_line_ids == {f"char:3041/voice:000{index}" for index in range(1, 4)}
    assert all_media_ids == {row["media_id"] for row in rows}
    assert registry.find_for_retrieval(
        _plan(intent="voice", media_intent="audio", entity="玛蒂尔达"),
        [{"child_id": "char:3041/voice:0001", "parent_id": "char:3041/voice"}],
        limit=8,
    ) == list(
        registry.find_bundle_for_retrieval(
            _plan(intent="voice", media_intent="audio", entity="玛蒂尔达"),
            [{"child_id": "char:3041/voice:0001", "parent_id": "char:3041/voice"}],
            limit=8,
        ).items
    )


def test_mixed_policy_union_keeps_limited_skill_and_current_voice_page(tmp_path):
    processed = tmp_path / "processed" / "build"
    rows = [
        {
            "media_id": f"skill-{index}",
            "entity_id": "char:3041",
            "entity_name": "玛蒂尔达",
            "child_id": f"char:3041/skill:{index:04d}",
            "parent_id": "char:3041/skills",
            "asset_type": "skill",
            "filename": f"skill-{index}.webp",
            "title": f"技能 {index}",
            "mime": "image/webp",
            "url": f"https://media.example/skill-{index}.webp",
            "is_available": True,
            "is_common": False,
            "attach_policy": "auto",
            "sort_order": index,
        }
        for index in range(2)
    ]
    rows.extend(
        {
            "media_id": f"voice-{index}",
            "entity_id": "char:3041",
            "entity_name": "玛蒂尔达",
            "child_id": f"char:3041/voice:{index:04d}",
            "parent_id": "char:3041/voice",
            "asset_type": "voice",
            "filename": f"Zh_voice_{index}.mp3",
            "title": f"语音 {index}",
            "mime": "audio/mpeg",
            "url": f"https://media.example/voice-{index}.mp3",
            "is_available": True,
            "is_common": False,
            "attach_policy": "on_intent",
            "sort_order": index,
        }
        for index in range(3)
    )
    write_jsonl(processed / "media_assets.jsonl", rows)
    registry = HuijiMediaRegistry(_cfg(tmp_path))
    sources = [
        {
            "entity_id": "char:3041",
            "child_id": "char:3041/skill:0000",
            "parent_id": "char:3041/skills",
        },
        {
            "entity_id": "char:3041",
            "child_id": "char:3041/voice:0000",
            "parent_id": "char:3041/voice",
        },
    ]

    bundle = registry.find_bundle_for_retrieval(
        _plan(intent="skill", secondary_intents=("voice",), media_intent="audio"),
        sources,
        limit=1,
        voice_page_size=2,
    )

    assert [item["media_id"] for item in bundle.items if item["asset_type"] == "skill"] == [
        "skill-0"
    ]
    assert [item["media_id"] for item in bundle.items if item["asset_type"] == "voice"] == [
        "voice-0",
        "voice-1",
    ]
    assert len(bundle.panels[0]["lines"]) == 2
    assert bundle.panels[0]["total_lines"] == 3


def test_v3_shared_resource_keeps_collection_and_udimo_bindings(tmp_path):
    fixture = Path("tests/fixtures/contracts/huiji_media_v3/media_assets.v3.jsonl")
    fixture_rows = [
        json.loads(line)
        for line in fixture.read_text(encoding="utf-8").splitlines()
        if line
    ]
    portrait = fixture_rows[0]
    collection = next(row for row in fixture_rows if row["media_role"] == "collection_item")
    shared_udimo = ordered_media_v3_row({
        **collection,
        "parent_id": "char:1001/udimo",
        "child_id": "char:1001/udimo/profile",
        "section": "udimo",
        "media_role": "udimo",
        "variant": "companion",
        "source_binding_token": "udimo-owner-relation:1001:shared",
        "title": "Shared resource as Udimo",
        "search_text": "Sample Alpha Udimo",
        "panel_group": "udimo",
    })
    media_path = tmp_path / "media_assets.v3.jsonl"
    media_path.write_bytes(canonical_jsonl_bytes([portrait, collection, shared_udimo]))
    registry = HuijiMediaRegistry(
        _cfg(tmp_path),
        artifact_snapshot=_v3_snapshot(tmp_path, media_path),
    )
    sources = [
        {
            "entity_type": "character",
            "entity_id": "1001",
            "entity_name": "Sample Alpha",
            "child_id": collection["child_id"],
            "parent_id": collection["parent_id"],
        },
        {
            "entity_type": "character",
            "entity_id": "1001",
            "entity_name": "Sample Alpha",
            "child_id": shared_udimo["child_id"],
            "parent_id": shared_udimo["parent_id"],
        },
    ]

    mixed = registry.find_bundle_for_retrieval(
        _plan(
            intent="item",
            secondary_intents=("udimo",),
            media_intent="image",
            entity="Sample Alpha",
            entity_id="1001",
        ),
        sources,
        limit=8,
    )

    assert {item["media_role"] for item in mixed.items} == {
        "collection_item",
        "udimo",
    }
    assert len({item["binding_id"] for item in mixed.items}) == 2
    assert {item["resource_id"] for item in mixed.items} == {
        collection["resource_id"]
    }
    assert all(item["asset_id"] == item["binding_id"] for item in mixed.items)
    assert not any(item["binding_id"] == portrait["binding_id"] for item in mixed.items)

    collection_only = registry.find_bundle_for_retrieval(
        _plan(
            intent="item",
            media_intent="image",
            entity="Sample Alpha",
            entity_id="1001",
        ),
        sources,
    )
    udimo_only = registry.find_bundle_for_retrieval(
        _plan(
            intent="udimo",
            media_intent="image",
            entity="Sample Alpha",
            entity_id="1001",
        ),
        sources,
    )
    assert [item["binding_id"] for item in collection_only.items] == [
        collection["binding_id"]
    ]
    assert [item["binding_id"] for item in udimo_only.items] == [
        shared_udimo["binding_id"]
    ]


def test_legacy_collection_query_does_not_fallback_to_generic_portrait(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "media_assets.jsonl",
        [{
            "media_id": "portrait-only",
            "entity_id": "1001",
            "entity_name": "Sample Alpha",
            "child_id": "char:1001/media/default",
            "parent_id": "char:1001/media",
            "asset_type": "portrait",
            "filename": "portrait.webp",
            "title": "Portrait",
            "mime": "image/webp",
            "url": "https://media.example/portrait.webp",
            "is_available": True,
            "is_common": False,
            "attach_policy": "auto",
        }],
    )
    registry = HuijiMediaRegistry(_cfg(tmp_path))

    bundle = registry.find_bundle_for_retrieval(
        _plan(
            intent="item",
            media_intent="image",
            entity="Sample Alpha",
            entity_id="1001",
        ),
        [{
            "entity_type": "character",
            "entity_id": "1001",
            "entity_name": "Sample Alpha",
            "child_id": "char:1001/media/default",
            "parent_id": "char:1001/media",
        }],
    )

    assert bundle.items == ()
