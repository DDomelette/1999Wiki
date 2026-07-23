from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.huiji_wiki.models import WikiMediaLink
from src.huiji_wiki.repository import (
    InvalidWikiCursor,
    MySQLWikiRepository,
    WikiListCursor,
    WikiRepositoryUnavailable,
    decode_wiki_list_cursor,
    encode_wiki_list_cursor,
    is_public_media_url,
    sanitize_media_item,
    wiki_list_filter_fingerprint,
)


def test_public_media_url_guard_accepts_only_http_urls():
    assert is_public_media_url("http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/a.webp")
    assert is_public_media_url("https://cdn.example/reverse1999/image/a.webp")
    assert is_public_media_url("/media/reverse1999-assets/reverse1999/image/a.webp")
    assert not is_public_media_url("")
    assert not is_public_media_url("D:\\assets\\a.webp")
    assert not is_public_media_url("C:\\assets\\a.webp")
    assert not is_public_media_url("file:///tmp/a.webp")


def test_sanitize_media_item_keeps_only_api_safe_fields():
    item = {
        "mediaId": "m1",
        "assetId": "m1",
        "assetType": "portrait",
        "mime": "image/webp",
        "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/m1.webp",
        "title": "立绘",
        "alt": "立绘",
        "role": "portrait",
        "sectionKey": "profile",
        "displayOrder": 2,
        "objectKey": "reverse1999/portrait/aa/m1.webp",
        "local_relpath": "assets/files/m1.webp",
        "sha1": "abc",
        "width": 512,
        "height": 1024,
        "variant": "initial",
    }

    assert sanitize_media_item(item) == {
        "mediaId": "m1",
        "assetId": "m1",
        "assetType": "portrait",
        "mime": "image/webp",
        "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/m1.webp",
        "title": "立绘",
        "alt": "立绘",
        "role": "portrait",
        "sectionKey": "profile",
        "displayOrder": 2,
        "sha1": "abc",
        "width": 512,
        "height": 1024,
        "variant": "initial",
    }
    assert sanitize_media_item({**item, "url": "D:\\assets\\m1.webp"}) is None


def test_sanitize_media_v3_item_preserves_binding_identity_but_hides_storage_fields():
    item = {
        "binding_id": "binding:sha256:" + "a" * 64,
        "resource_id": "resource:sha256:" + "b" * 64,
        "media_id": "media:sha1:" + "c" * 40,
        "url": "https://cdn.example/portrait.webp",
        "asset_type": "portrait",
        "media_role": "stage_portrait",
        "owner_entity_id": "character:3003",
        "owner_page_id": "char:3003",
        "skin_id": "300301",
        "event_name": "",
        "language": "",
        "source_binding_token": "relation:1",
        "binding_status": "exact",
        "object_key": "reverse1999/portrait/a.webp",
        "source_refs": [{"source_title": "Data:Char/3003.json"}],
    }

    payload = sanitize_media_item(item)

    assert payload == {
        "bindingId": item["binding_id"],
        "resourceId": item["resource_id"],
        "mediaId": item["media_id"],
        "assetId": item["media_id"],
        "assetType": "portrait",
        "url": item["url"],
        "role": "stage_portrait",
        "ownerEntityId": "character:3003",
        "ownerPageId": "char:3003",
        "skinId": "300301",
        "sourceBindingToken": "relation:1",
        "bindingStatus": "exact",
    }
    assert "objectKey" not in payload
    assert "sourceRefs" not in payload


def test_wiki_media_link_to_api_uses_shared_media_whitelist():
    media = WikiMediaLink(
        page_id="char:3074",
        section_key="portrait",
        media_id="m1",
        media_role="portrait",
        display_order=1,
        object_key="reverse1999/portrait/aa/m1.webp",
        url="http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/m1.webp",
        asset_type="portrait",
        mime="image/webp",
        title="立绘",
        sha1="abc",
        width=512,
        height=1024,
        variant="initial",
    )

    payload = media.to_api()

    assert payload == {
        "mediaId": "m1",
        "assetId": "m1",
        "assetType": "portrait",
        "mime": "image/webp",
        "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/m1.webp",
        "title": "立绘",
        "alt": "立绘",
        "role": "portrait",
        "sectionKey": "portrait",
        "displayOrder": 1,
        "sha1": "abc",
        "width": 512,
        "height": 1024,
        "variant": "initial",
    }


class RecordingCursor:
    def __init__(self, *, all_rows=None, one_rows=None, fail_on=""):
        self.calls: list[tuple[str, tuple]] = []
        self._all_rows = list(all_rows or [])
        self._one_rows = list(one_rows or [])
        self._fail_on = fail_on

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        self.calls.append((normalized, tuple(params)))
        if self._fail_on and self._fail_on in normalized:
            raise RuntimeError("synthetic missing table")

    def fetchall(self):
        return self._all_rows.pop(0)

    def fetchone(self):
        return self._one_rows.pop(0) if self._one_rows else None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _repo_with_cursor(cursor: RecordingCursor) -> MySQLWikiRepository:
    cfg = SimpleNamespace(
        mysql=SimpleNamespace(),
        assets=SimpleNamespace(
            public_base_url="/media",
            bucket_name="reverse1999-assets",
        ),
    )
    repo = MySQLWikiRepository(cfg)
    repo._connect = lambda: RecordingConnection(cursor)  # type: ignore[method-assign]
    return repo


def test_list_categories_uses_wiki_category_metadata_and_stable_order():
    cursor = RecordingCursor(
        all_rows=[
            [
                {
                    "key": "character",
                    "label": "角色",
                    "count": 132,
                    "template_group": "character",
                    "animation_profile": "entity-list",
                    "theme_token": "character",
                }
            ]
        ]
    )
    repo = _repo_with_cursor(cursor)

    categories = repo.list_categories()

    assert "wiki_categories" in cursor.calls[0][0]
    assert categories[0].key == "character"
    assert categories[0].label == "角色"
    assert categories[0].template_group == "character"
    assert categories[0].animation_profile == "entity-list"
    assert categories[0].theme_token == "character"


def _page_row(page_id: str, title: str = "X") -> dict:
    return {
        "page_id": page_id,
        "page_type": "character",
        "title": title,
        "subtitle": title,
        "category": "角色",
        "route": f"/wiki/char/{page_id.split(':')[-1]}",
        "source_pageid": int(page_id.split(":")[-1]),
        "source_title": f"Data:Char/{page_id.split(':')[-1]}.json",
        "content_json": "{}",
        "updated_at": "",
    }


def test_wiki_list_cursor_round_trip_and_filter_validation():
    fingerprint = wiki_list_filter_fingerprint(category="角色", q="苏芙比", page_type="character")
    token = encode_wiki_list_cursor(WikiListCursor(version=1, offset=30, filter_fingerprint=fingerprint))

    decoded = decode_wiki_list_cursor(token, expected_fingerprint=fingerprint)

    assert decoded == WikiListCursor(version=1, offset=30, filter_fingerprint=fingerprint)
    assert ":" not in token
    with pytest.raises(InvalidWikiCursor):
        decode_wiki_list_cursor("not-a-valid-cursor", expected_fingerprint=fingerprint)
    with pytest.raises(InvalidWikiCursor):
        decode_wiki_list_cursor(
            token,
            expected_fingerprint=wiki_list_filter_fingerprint(category="角色", q="露西", page_type="character"),
        )


def test_list_pages_opaque_cursor_returns_extra_row_on_next_page_without_duplicates():
    rows = [_page_row(f"char:{page_id}") for page_id in range(3009, 3013)]
    cursor = RecordingCursor(all_rows=[rows[:3], rows[2:]])
    repo = _repo_with_cursor(cursor)

    first_pages, next_cursor = repo.list_pages(page_type="character", limit=2)
    second_pages, final_cursor = repo.list_pages(page_type="character", limit=2, cursor=next_cursor or "")

    all_ids = [page.page_id for page in first_pages + second_pages]
    assert all_ids == ["char:3009", "char:3010", "char:3011", "char:3012"]
    assert len(all_ids) == len(set(all_ids))
    assert next_cursor and next_cursor != "char:3011"
    assert final_cursor is None
    assert cursor.calls[0][1][-2:] == (3, 0)
    assert cursor.calls[1][1][-2:] == (3, 2)


def test_list_pages_search_aggregates_aliases_once_and_sorts_narrow_candidates():
    rows = [
        _page_row("char:3009", "苏芙比"),
        _page_row("char:3010"),
        _page_row("char:3011", "玛丽莲"),
    ]
    cursor = RecordingCursor(all_rows=[rows])
    repo = _repo_with_cursor(cursor)

    pages, next_cursor = repo.list_pages(q="苏芙比", limit=2)

    sql, params = cursor.calls[0]
    candidate_sql = sql.split("FROM (", 1)[1].rsplit(") ranked", 1)[0]
    assert candidate_sql.count("FROM wiki_aliases") == 1
    assert "content_json" not in candidate_sql
    assert sql.count("content_json") == 1
    assert "JOIN wiki_pages p ON p.page_id = ranked.page_id" in sql
    assert "match_rank" in candidate_sql
    assert "alias_priority" in candidate_sql
    assert "%苏芙比%" in params
    assert [page.page_id for page in pages] == ["char:3009", "char:3010"]
    assert next_cursor is not None


def test_list_pages_wraps_database_failures_in_repository_error():
    cursor = RecordingCursor(all_rows=[[]], fail_on="FROM wiki_pages")
    repo = _repo_with_cursor(cursor)

    with pytest.raises(WikiRepositoryUnavailable):
        repo.list_pages(page_type="character", limit=2)


def test_list_pages_accepts_category_key_as_page_type_or_category_label():
    cursor = RecordingCursor(all_rows=[[]])
    repo = _repo_with_cursor(cursor)

    repo.list_pages(category="character", limit=2)

    sql, params = cursor.calls[0]
    assert "p.page_type = %s" in sql
    assert "wiki_categories" in sql
    assert params[:3] == ("character", "character", "character")


def test_resolve_route_title_checks_page_title_before_alias_fallback():
    cursor = RecordingCursor(one_rows=[{"route": "/wiki/char/3009"}])
    repo = _repo_with_cursor(cursor)

    route = repo.resolve_route(title="苏芙比")

    sql, params = cursor.calls[0]
    assert route == "/wiki/char/3009"
    assert "FROM wiki_pages" in sql
    assert "title = %s" in sql
    assert params[0] == "苏芙比"


def test_get_page_detail_by_route_resolves_route_to_page_id_before_detail_lookup():
    cursor = RecordingCursor(one_rows=[{"page_id": "char:3074"}])
    repo = _repo_with_cursor(cursor)
    called: list[str] = []
    repo.get_page_detail = lambda page_id: called.append(page_id) or {"pageId": page_id}  # type: ignore[method-assign]

    detail = repo.get_page_detail_by_route("/wiki/char/3074")

    sql, params = cursor.calls[0]
    assert detail == {"pageId": "char:3074"}
    assert "FROM wiki_pages" in sql
    assert "route = %s" in sql
    assert params == ("/wiki/char/3074",)
    assert called == ["char:3074"]


def test_get_page_detail_by_route_raises_key_error_for_missing_route():
    cursor = RecordingCursor(one_rows=[None])
    repo = _repo_with_cursor(cursor)

    try:
        repo.get_page_detail_by_route("/wiki/missing")
    except KeyError as exc:
        assert exc.args == ("/wiki/missing",)
    else:
        raise AssertionError("expected KeyError")


def test_crawler_only_health_counts_core_tables_without_supplement_queries():
    cursor = RecordingCursor(
        one_rows=[
            {"count": 7456},
            {"count": 4},
            {"count": 17527},
            {"count": 998},
            {"count": 263},
            {
                "source_mode": "legacy",
                "build_version": "dev",
                "artifact_schema_version": "v1",
                "activation_epoch": None,
                "manifest_sha256": "a" * 64,
                "snapshot_sha256": "canonical-snapshot",
            },
        ]
    )
    repo = _repo_with_cursor(cursor)

    health = repo.get_health()

    assert health["ready"] is True
    assert health["pageCount"] == 7456
    assert health["mediaLinkCount"] == 17527
    assert "supplementReady" not in health
    assert all("wiki_page_supplements" not in sql for sql, _ in cursor.calls)
    assert all("wiki_supplement_snapshots" not in sql for sql, _ in cursor.calls)


def test_v3_health_reports_resource_and_binding_counts_separately():
    cursor = RecordingCursor(one_rows=[
        {"count": 7456},
        {"count": 4},
        {"count": 0},
        {"count": 998},
        {"count": 263},
        {
            "source_mode": "active",
            "build_version": "release-v3",
            "artifact_schema_version": "evb.media-asset/v3",
            "activation_epoch": 3,
            "manifest_sha256": "a" * 64,
            "snapshot_sha256": "canonical-v3-snapshot",
        },
        {"count": 15383},
        {"count": 15758},
    ])
    repo = _repo_with_cursor(cursor)

    health = repo.get_health()

    assert health["ready"] is True
    assert health["mediaLinkCount"] == 0
    assert health["mediaResourceCount"] == 15383
    assert health["mediaBindingCount"] == 15758


def test_crawler_only_thumbnail_prefers_canonical_roster_avatar_in_one_query():
    cursor = RecordingCursor(
        all_rows=[[{
            "page_id": "char:3003",
            "object_key": "reverse1999/portrait/aa/avatar.webp",
            "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/avatar.webp",
            "media_role": "roster_avatar",
        }, {
            "page_id": "char:3003",
            "object_key": "reverse1999/portrait/bb/stage.webp",
            "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/bb/stage.webp",
            "media_role": "stage_live2d",
        }]],
    )
    repo = _repo_with_cursor(cursor)

    result = repo.first_media_url_by_page(["char:3003"])

    sql, params = cursor.calls[-1]
    assert len(cursor.calls) == 2
    assert "wiki_page_supplements" not in sql
    assert "roster_avatar" in sql
    assert "LOWER(asset_type) IN" in sql
    assert "object_key" in sql
    assert params == ("char:3003",)
    assert result["char:3003"] == (
        "/media/reverse1999-assets/reverse1999/portrait/aa/avatar.webp"
    )


def test_crawler_only_thumbnail_query_escapes_percent_for_pymysql_parameter_formatting():
    class PyMySQLFormattingCursor(RecordingCursor):
        def execute(self, sql, params=()):
            sql % tuple(repr(value) for value in params)
            super().execute(sql, params)

    cursor = PyMySQLFormattingCursor(all_rows=[[]])
    repo = _repo_with_cursor(cursor)

    repo.first_media_url_by_page(["char:3003"])

    assert len(cursor.calls) == 2


def test_crawler_only_page_detail_never_queries_or_merges_supplements():
    cursor = RecordingCursor(
        one_rows=[{
            "page_id": "char:3003",
            "page_type": "character",
            "title": "Druvis III",
            "subtitle": "Druvis III",
            "category": "character",
            "route": "/wiki/character/3003",
            "source_pageid": 3003,
            "source_title": "Data:Char/3003.json",
            "content_json": '{"crawlerProjectionVersion":1,"profile":{"Name":"Druvis III"},"blocks":[]}',
            "updated_at": "",
        }],
        all_rows=[[
            {
                "page_id": "char:3003",
                "section_key": "roster",
                "media_id": "char:3003/crawler:roster_avatar:300301",
                "media_role": "roster_avatar",
                "display_order": 1,
                "fallback_media_id": "",
                "object_key": "reverse1999/portrait/aa/a.webp",
                "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/a.webp",
                "asset_type": "portrait",
                "mime": "image/webp",
                "title": "Headicon large",
                "sha1": "a" * 40,
                "width": 228,
                "height": 524,
            }
        ], [], []],
    )
    repo = _repo_with_cursor(cursor)

    detail = repo.get_page_detail("char:3003")

    assert detail["content"]["crawlerProjectionVersion"] == 1
    assert detail["mediaLinks"][0]["role"] == "roster_avatar"
    assert detail["mediaLinks"][0]["url"] == (
        "/media/reverse1999-assets/reverse1999/portrait/aa/a.webp"
    )
    assert "127.0.0.1:9002" not in str(detail)
    assert all("wiki_page_supplements" not in sql for sql, _ in cursor.calls)
    assert "supplement" not in str(detail).casefold()


def test_v3_page_detail_reads_resource_binding_join_without_collapsing_media_id():
    page_row = {
        "page_id": "char:3003",
        "page_type": "character",
        "title": "槲寄生",
        "subtitle": "Druvis III",
        "category": "character",
        "route": "/wiki/character/3003",
        "source_pageid": 3003,
        "source_title": "Data:Char/3003.json",
        "content_json": '{"blocks":[]}',
        "updated_at": "",
    }
    shared = {
        "page_id": "char:3003",
        "resource_id": "resource:sha256:" + "b" * 64,
        "media_id": "media:sha1:" + "c" * 40,
        "section_key": "profile",
        "media_role": "stage_portrait",
        "display_order": 1,
        "object_key": "reverse1999/portrait/shared.webp",
        "url": "https://cdn.example/shared.webp",
        "asset_type": "portrait",
        "mime": "image/webp",
        "title": "立绘",
        "sha1": "c" * 40,
        "width": 512,
        "height": 1024,
        "variant": "initial",
        "owner_entity_id": "character:3003",
        "owner_page_id": "char:3003",
        "source_binding_token": "relation:1",
        "binding_status": "exact",
    }
    cursor = RecordingCursor(
        one_rows=[page_row, {"artifact_schema_version": "evb.media-asset/v3"}],
        all_rows=[[
            {**shared, "binding_id": "binding:sha256:" + "1" * 64},
            {**shared, "binding_id": "binding:sha256:" + "2" * 64, "source_binding_token": "relation:2"},
        ], [], []],
    )
    repo = _repo_with_cursor(cursor)

    detail = repo.get_page_detail("char:3003")

    assert len(detail["mediaLinks"]) == 2
    assert detail["mediaLinks"][0]["mediaId"] == detail["mediaLinks"][1]["mediaId"]
    assert detail["mediaLinks"][0]["bindingId"] != detail["mediaLinks"][1]["bindingId"]
    assert any("wiki_media_bindings" in sql for sql, _ in cursor.calls)


def test_page_detail_omits_media_with_missing_or_unsafe_object_keys():
    page_row = _page_row("char:3003")
    cursor = RecordingCursor(
        one_rows=[page_row, {"artifact_schema_version": ""}],
        all_rows=[[
            {
                "page_id": "char:3003",
                "section_key": "profile",
                "media_id": "missing-key",
                "media_role": "portrait",
                "display_order": 1,
                "object_key": "",
                "url": "https://stored.example/missing.webp",
                "asset_type": "portrait",
                "mime": "image/webp",
            },
            {
                "page_id": "char:3003",
                "section_key": "profile",
                "media_id": "unsafe-key",
                "media_role": "portrait",
                "display_order": 2,
                "object_key": "../private.webp",
                "url": "https://stored.example/unsafe.webp",
                "asset_type": "portrait",
                "mime": "image/webp",
            },
        ], [], []],
    )
    repo = _repo_with_cursor(cursor)

    detail = repo.get_page_detail("char:3003")

    assert detail["mediaLinks"] == []
