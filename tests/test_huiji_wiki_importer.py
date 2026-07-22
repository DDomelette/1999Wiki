from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from src.huiji_wiki.importer import WikiImportPayload, build_wiki_import_payload, import_payload_to_mysql


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_build_wiki_import_payload_adds_non_character_categories(tmp_path: Path):
    _write_jsonl(
        tmp_path / "parent_blocks.jsonl",
        [
            {
                "parent_id": "char:3003",
                "entity_id": "3003",
                "entity_name": "槲寄生",
                "entity_type": "character",
                "category": "character",
                "title": "槲寄生",
                "source_refs": [{"title": "Data:Char/3003.json"}],
                "child_ids": ["char:3003/profile:0000"],
            },
            {
                "parent_id": "story:abc/profile",
                "entity_id": "abc",
                "entity_name": "此即明日",
                "entity_type": "story",
                "category": "story",
                "title": "此即明日",
                "source_refs": [{"title": "Data:Episode/1.json"}],
                "child_ids": ["story:abc:0000"],
            },
            {
                "parent_id": "item:1/110104/profile",
                "entity_id": "1/110104",
                "entity_name": "床下怪物",
                "entity_type": "item",
                "category": "item",
                "title": "床下怪物",
                "source_refs": [{"title": "Data:Item/1/110104.json"}],
                "child_ids": ["item:1/110104:0000"],
            },
        ],
    )
    _write_jsonl(
        tmp_path / "child_blocks.jsonl",
        [
            {
                "child_id": "story:abc:0000",
                "parent_id": "story:abc/profile",
                "category": "story",
                "text": "此即明日\n主线剧情摘要",
            },
            {
                "child_id": "item:1/110104:0000",
                "parent_id": "item:1/110104/profile",
                "category": "item",
                "text": "床下怪物\n孩子们说的都是真的。",
            },
        ],
    )
    _write_jsonl(tmp_path / "media_assets.jsonl", [])

    payload = build_wiki_import_payload(tmp_path)

    page_ids = {page["page_id"] for page in payload.pages}
    assert "char:3003" not in page_ids
    assert "story:abc/profile" in page_ids
    assert "item:1/110104/profile" in page_ids
    assert payload.categories["story"]["label"] == "剧情"
    assert payload.categories["item"]["label"] == "物品"
    story_page = next(page for page in payload.pages if page["page_id"] == "story:abc/profile")
    assert story_page["page_type"] == "story"
    assert story_page["category"] == "剧情"
    assert story_page["route"] == "/wiki/story/abc"
    assert story_page["source_title"] == "Data:Episode/1.json"
    assert story_page["content_json"]["summary"] == "此即明日\n主线剧情摘要"
    assert payload.full_replace is False
    assert story_page["content_json"]["contentVersion"] == 1
    assert story_page["content_json"]["blocks"]


def test_import_script_can_load_project_modules():
    result = subprocess.run(
        [sys.executable, "scripts/import_huiji_wiki_pages.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--processed-dir" in result.stdout
    assert "--raw-root" in result.stdout


def test_character_import_merges_crawler_projection_into_canonical_rows(tmp_path: Path):
    processed = tmp_path / "processed"
    raw_root = tmp_path / "raw"
    processed.mkdir()
    _write_jsonl(
        processed / "parent_blocks.jsonl",
        [{
            "parent_id": "char:3003",
            "entity_id": "3003",
            "entity_name": "槲寄生",
            "entity_type": "character",
            "category": "character",
            "section_kind": "entity",
            "title": "槲寄生",
            "source_refs": [{"title": "Data:Char/3003.json"}],
            "child_ids": ["char:3003/profile:0000"],
        }],
    )
    _write_jsonl(
        processed / "child_blocks.jsonl",
        [{
            "child_id": "char:3003/profile:0000",
            "parent_id": "char:3003",
            "section_kind": "profile",
            "text": "槲寄生\n稀有度: 5",
        }],
    )
    _write_jsonl(processed / "media_assets.jsonl", [])

    avatar = b"crawler-avatar"
    sha1 = hashlib.sha1(avatar).hexdigest()
    relpath = f"assets/files/{sha1}/Headicon_large-300301.webp"
    (raw_root / relpath).parent.mkdir(parents=True)
    (raw_root / relpath).write_bytes(avatar)
    _write_jsonl(
        raw_root / "resources_manifest.jsonl",
        [{
            "name": "Headicon_large-300301.webp",
            "title": "文件:Headicon_large-300301.webp",
            "sha1": sha1,
            "mime": "image/webp",
            "local_relpath": relpath,
            "width": 228,
            "height": 524,
        }],
    )
    _write_jsonl(
        raw_root / "data_pages.jsonl",
        [{
            "title": "Data:Char/3003.json",
            "content": {
                "id": 3003,
                "name": "槲寄生",
                "nameEng": "Druvis III",
                "passive_skill": [{"name": "木秀于林", "skillLevel": 1, "desc_art": "往泥壤中侵蚀。"}],
                "skill_ex_level": [{"skillLevel": 1, "desc": "精神创伤提升。"}],
                "skin": [{"id": 300301, "largeIcon": "300301"}],
            },
        }],
    )

    payload = build_wiki_import_payload(
        processed,
        include_character=True,
        raw_root=raw_root,
        asset_public_base_url="http://127.0.0.1:9002",
        asset_bucket_name="reverse1999-assets",
        asset_object_prefix="reverse1999",
    )

    assert payload.full_replace is True
    page = payload.pages[0]
    assert page["content_json"]["crawlerProjectionVersion"] == 1
    assert page["content_json"]["profile"]["Name"] == "槲寄生"
    assert {block["section"] for block in page["content_json"]["blocks"]} >= {"profile", "inheritance", "portray"}
    assert payload.media_links[0]["media_role"] == "roster_avatar"
    assert payload.media_links[0]["object_key"].startswith("reverse1999/portrait/")
    assert "supplement" not in json.dumps(page, ensure_ascii=False).casefold()


def test_full_replace_reconciles_stale_wiki_rows_with_temporary_authority_tables(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []
            self.many_calls: list[tuple[str, list[tuple]]] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.calls.append((" ".join(str(sql).split()), tuple(params)))

        def executemany(self, sql, rows):
            self.many_calls.append((" ".join(str(sql).split()), list(rows)))

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()
            self.committed = False
            self.rolled_back = False
            self.began = False
            self.closed = False

        def cursor(self):
            return self.cursor_instance

        def begin(self):
            self.began = True

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    connection = Connection()
    fake_pymysql = SimpleNamespace(
        connect=lambda **_kwargs: connection,
        cursors=SimpleNamespace(DictCursor=object),
    )
    monkeypatch.setitem(sys.modules, "pymysql", fake_pymysql)
    payload = WikiImportPayload(
        pages=[{
            "page_id": "char:3003",
            "page_type": "character",
            "title": "槲寄生",
            "subtitle": "Druvis III",
            "category": "角色",
            "route": "/wiki/character/3003",
            "source_pageid": 3003,
            "source_title": "Data:Char/3003.json",
            "content_json": {"crawlerProjectionVersion": 1},
            "updated_at": "2026-07-18T00:00:00",
        }],
        categories={"character": {
            "category_key": "character",
            "label": "角色",
            "page_count": 1,
            "template_group": "character",
            "animation_profile": "entity-list",
            "theme_token": "character",
        }},
        media_links=[],
        full_replace=True,
    )
    cfg = SimpleNamespace(mysql=SimpleNamespace(
        host="127.0.0.1", port=3307, user="root", password="secret",
        database="reverse1999_wiki", charset="utf8mb4",
    ))

    import_payload_to_mysql(payload, cfg)

    sql = "\n".join(statement for statement, _ in connection.cursor_instance.calls)
    assert "CREATE TEMPORARY TABLE wiki_import_page_ids" in sql
    assert "CREATE TEMPORARY TABLE wiki_import_routes" in sql
    assert "CREATE TEMPORARY TABLE wiki_import_category_keys" in sql
    assert "DELETE a FROM wiki_aliases AS a LEFT JOIN wiki_import_page_ids" in sql
    assert "DELETE s FROM wiki_link_spans AS s LEFT JOIN wiki_import_page_ids" in sql
    assert "DELETE p FROM wiki_pages AS p LEFT JOIN wiki_import_page_ids" in sql
    assert "DELETE c FROM wiki_categories AS c LEFT JOIN wiki_import_category_keys" in sql
    assert "DELETE FROM wiki_media_links" in sql
    assert connection.cursor_instance.many_calls == [
        ("INSERT INTO wiki_import_page_ids (page_id) VALUES (%s)", [("char:3003",)]),
        ("INSERT INTO wiki_import_routes (route) VALUES (%s)", [("/wiki/character/3003",)]),
        ("INSERT INTO wiki_import_category_keys (category_key) VALUES (%s)", [("character",)]),
    ]
    assert connection.committed is True
    assert connection.began is True
    assert connection.rolled_back is False
    assert connection.closed is True
