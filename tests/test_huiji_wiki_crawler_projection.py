from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.huiji_wiki.crawler_projection import (
    CrawlerProjectionConfig,
    build_crawler_character_projection,
    validate_crawler_only_payload,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _resource(raw_root: Path, name: str, payload: bytes) -> dict[str, object]:
    sha1 = hashlib.sha1(payload).hexdigest()
    relpath = f"assets/files/{sha1}/{name}"
    path = raw_root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "name": name,
        "title": f"文件:{name}",
        "sha1": sha1,
        "mime": "image/webp",
        "local_relpath": relpath,
        "width": 640,
        "height": 960,
    }


def _config() -> CrawlerProjectionConfig:
    return CrawlerProjectionConfig(
        public_base_url="http://127.0.0.1:9002",
        bucket_name="reverse1999-assets",
        object_prefix="reverse1999",
    )


def test_projection_uses_crawler_character_structure_and_explicit_media_fields(tmp_path: Path):
    raw_root = tmp_path / "res1999"
    resources = [
        _resource(raw_root, "Headicon_large-300301.webp", b"avatar"),
        _resource(raw_root, "L2d_static-300301_hujisheng.webp", b"live2d"),
        _resource(raw_root, "L2d_static-300301_hujisheng_p.webp", b"portrait"),
        _resource(raw_root, "Skin_bg-300301_hujisheng.webp", b"background"),
        _resource(raw_root, "Belonging-300301.webp", b"collection"),
        _resource(raw_root, "Item-333003.webp", b"udimo"),
    ]
    _write_jsonl(raw_root / "resources_manifest.jsonl", resources)
    _write_jsonl(
        raw_root / "data_pages.jsonl",
        [
            {
                "title": "Data:Char/3003.json",
                "content": {
                    "id": 3003,
                    "name": "槲寄生",
                    "nameEng": "Druvis III",
                    "rare": 5,
                    "dmgType": 2,
                    "roleBirthday": "10/23",
                    "desc2": "漫游于林间的术杖制造师。",
                    "passive_skill": [
                        {"name": "木秀于林", "skillLevel": 1, "desc_art": "往泥壤中侵蚀。"},
                        {"name": "木秀于林Ⅱ", "skillLevel": 2, "desc_art": "往泥壤中剥离。"},
                    ],
                    "skill_ex_level": [
                        {"skillLevel": 1, "desc": "咒语造成的精神创伤提升。"},
                    ],
                    "character_data": [
                        {
                            "id": 2,
                            "type": 2,
                            "number": 1,
                            "title": "1900橡木铃",
                            "titleEn": "Lugus Samildánach",
                            "text": "百年纪念款。",
                            "icon": "300301",
                            "estimate": "1#20",
                        },
                        {
                            "id": 5,
                            "type": 3,
                            "number": 1,
                            "title": "咆哮的1920年代",
                            "titleEn": "Roaring Twenties",
                            "text": "现代化改变了一切。",
                            "icon": "300304",
                        },
                    ],
                    "skin": [
                        {
                            "id": 300301,
                            "name": "槲寄生",
                            "nameEng": "Druvis III",
                            "des": "初始皮肤",
                            "skinDescription": "酒会从来都是不适合她的。",
                            "largeIcon": "300301",
                            "live2d": "300301_hujisheng",
                            "verticalDrawing": "300301_hujisheng_p",
                            "drawing": "300301",
                            "live2dbg": "300301_hujisheng",
                        }
                    ],
                },
            },
            {
                "title": "Data:Item/1/333003.json",
                "content": {
                    "id": 333003,
                    "name": "尤提姆贴纸·槲寄生",
                    "icon": "333003",
                    "desc": "槲寄生的尤提姆形象",
                },
            },
        ],
    )

    projection = build_crawler_character_projection(raw_root, config=_config())
    character = projection.characters["char:3003"]

    assert character.source_title == "Data:Char/3003.json"
    assert character.profile["Name"] == "槲寄生"
    assert character.profile["exonym"] == "Druvis III"
    assert character.profile["伤害类型"] == "精神创伤"
    assert {block["section"] for block in character.blocks} >= {
        "inheritance",
        "portray",
        "collection",
        "culture_dossier",
    }

    roles = [item["media_role"] for item in character.media_links]
    assert roles == [
        "roster_avatar",
        "stage_live2d",
        "stage_portrait",
        "skin_background",
        "collection_item",
        "udimo",
    ]
    assert character.media_links[0]["title"] == "文件:Headicon_large-300301.webp"
    assert character.media_links[1]["title"] == "文件:L2d_static-300301_hujisheng.webp"
    assert character.media_links[2]["title"] == "文件:L2d_static-300301_hujisheng_p.webp"
    assert character.media_links[4]["title"] == "文件:Belonging-300301.webp"
    assert character.media_links[5]["title"] == "文件:Item-333003.webp"
    assert all(item["object_key"].startswith("reverse1999/") for item in character.media_links)
    assert all("wiki-supplement" not in item["object_key"] for item in character.media_links)
    assert all(item["url"].startswith("http://127.0.0.1:9002/reverse1999-assets/") for item in character.media_links)


def test_projection_prefers_webp_over_png_for_the_same_explicit_resource(tmp_path: Path):
    raw_root = tmp_path / "res1999"
    png = _resource(raw_root, "Headicon_large-300301.png", b"png")
    png["mime"] = "image/png"
    webp = _resource(raw_root, "Headicon_large-300301.webp", b"webp")
    _write_jsonl(raw_root / "resources_manifest.jsonl", [png, webp])
    _write_jsonl(
        raw_root / "data_pages.jsonl",
        [{
            "title": "Data:Char/3003.json",
            "content": {
                "id": 3003,
                "name": "槲寄生",
                "skin": [{"id": 300301, "largeIcon": "300301"}],
            },
        }],
    )

    projection = build_crawler_character_projection(raw_root, config=_config())

    avatar = projection.characters["char:3003"].media_links[0]
    assert avatar["title"].endswith(".webp")
    assert avatar["mime"] == "image/webp"


def test_projection_uses_unique_collection_media_ids_across_skin_groups(tmp_path: Path):
    raw_root = tmp_path / "res1999"
    resources = [
        _resource(raw_root, "Belonging-300301.webp", b"collection-initial"),
        _resource(raw_root, "Belonging-300304.webp", b"collection-skin"),
    ]
    _write_jsonl(raw_root / "resources_manifest.jsonl", resources)
    _write_jsonl(
        raw_root / "data_pages.jsonl",
        [{
            "title": "Data:Char/3003.json",
            "content": {
                "id": 3003,
                "name": "sample-character",
                "character_data": [
                    {
                        "id": 2,
                        "type": 2,
                        "number": 1,
                        "skinId": 0,
                        "icon": "300301",
                        "title": "initial collection",
                    },
                    {
                        "id": 8,
                        "type": 2,
                        "number": 1,
                        "skinId": 300303,
                        "icon": "300304",
                        "title": "skin collection",
                    },
                ],
            },
        }],
    )

    character = build_crawler_character_projection(raw_root, config=_config()).characters["char:3003"]
    media = [item for item in character.media_links if item["media_role"] == "collection_item"]
    blocks = [item for item in character.blocks if item["section"] == "collection"]

    assert len({item["media_id"] for item in media}) == 2
    assert [item["mediaIds"] for item in blocks] == [[media[0]["media_id"]], [media[1]["media_id"]]]


def test_projection_ignores_character_index_and_partial_rows_without_scalar_id(tmp_path: Path):
    raw_root = tmp_path / "res1999"
    _write_jsonl(raw_root / "resources_manifest.jsonl", [])
    _write_jsonl(
        raw_root / "data_pages.jsonl",
        [
            {
                "title": "Data:Char.json",
                "content": {"id": {"3003": "槲寄生"}, "name": {"槲寄生": 3003}},
            },
            {
                "title": "Data:Char/3002.json",
                "content": {"skin": [{"id": 300201}]},
            },
        ],
    )

    projection = build_crawler_character_projection(raw_root, config=_config())

    assert projection.characters == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"source_kind": "obsidian_character"},
        {"source_key": "D:/Obsidian_depot/Reverse1999/角色.md"},
        {"object_key": "reverse1999/wiki-supplement/character/a.webp"},
    ],
)
def test_crawler_only_validator_rejects_legacy_sources(payload: dict[str, str]):
    with pytest.raises(ValueError, match="crawler-only"):
        validate_crawler_only_payload(payload)


def test_crawler_only_validator_allows_domain_text_that_mentions_obsidian():
    validate_crawler_only_payload(
        {
            "content_json": {
                "blocks": [{"section": "voice", "text": "My heart is made of obsidian gravels."}],
            },
            "source_title": "Data:Char/3070.json",
        }
    )
