from __future__ import annotations

import hashlib
import json
import sys

import pytest

from src.huiji_wiki.media_v3 import (
    MEDIA_V3_FIELD_ORDER,
    normalize_media_v3_rows,
    validate_media_v3_row,
)
from src.huiji_wiki.importer import WikiImportPayload, import_payload_to_mysql
from src.huiji_wiki.snapshot import WikiArtifactSnapshot
from pathlib import Path
from types import SimpleNamespace


def _row(*, binding_token: str = "relation:1", child_id: str = "child:1") -> dict:
    sha1 = "a" * 40
    content_sha256 = "b" * 64
    values = {
        "artifact_schema_version": "evb.media-asset/v3",
        "binding_id": "",
        "resource_id": f"resource:sha256:{content_sha256}",
        "media_id": f"media:sha1:{sha1}",
        "entity_id": "3003",
        "entity_name": "槲寄生",
        "owner_entity_id": "character:3003",
        "owner_page_id": "char:3003",
        "parent_id": "char:3003",
        "child_id": child_id,
        "section": "profile",
        "asset_type": "portrait",
        "media_role": "stage_portrait",
        "variant": "initial",
        "skin_id": "300301",
        "event_name": "",
        "language": "",
        "source_binding_token": binding_token,
        "source_refs": [{
            "source_kind": "crawler",
            "source_title": "Data:Char/3003.json",
            "source_row_id": binding_token,
            "source_content_sha256": "c" * 64,
        }],
        "mime": "image/webp",
        "filename": "L2d_static-300301.webp",
        "title": "槲寄生初始立绘",
        "source_url": "https://example.test/source.webp",
        "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/a.webp",
        "object_key": "reverse1999/portrait/a.webp",
        "is_available": True,
        "is_common": False,
        "attach_policy": "owner_page",
        "search_text": "槲寄生 初始立绘",
        "content_hash": content_sha256,
        "panel_group": "portrait",
        "sort_order": 1,
        "duration_ms": 0,
        "width": 1024,
        "height": 2048,
        "quality_flags": [],
        "sha1": sha1,
        "source_sha1": "d" * 40,
        "content_sha256": content_sha256,
        "size": 1234,
        "binding_status": "exact",
    }
    identity = [
        "evb.media-binding/v1",
        values["owner_entity_id"],
        values["owner_page_id"],
        values["parent_id"],
        values["child_id"],
        values["section"],
        values["media_role"],
        values["variant"],
        values["skin_id"],
        values["event_name"],
        values["language"],
        values["source_binding_token"],
        values["resource_id"],
    ]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    values["binding_id"] = "binding:sha256:" + hashlib.sha256(encoded).hexdigest()
    return {key: values[key] for key in MEDIA_V3_FIELD_ORDER}


def test_v3_row_requires_frozen_order_and_rejects_local_paths():
    row = _row()
    assert validate_media_v3_row(row) == row

    reordered = {"media_id": row["media_id"], **{key: value for key, value in row.items() if key != "media_id"}}
    with pytest.raises(ValueError, match="field order"):
        validate_media_v3_row(reordered)

    with pytest.raises(ValueError, match="local_relpath"):
        validate_media_v3_row({**row, "local_relpath": "assets/files/a.webp"})


def test_v3_row_rejects_binding_identity_mismatch():
    row = _row()
    row["binding_id"] = "binding:sha256:" + "0" * 64
    with pytest.raises(ValueError, match="binding_id"):
        validate_media_v3_row(row)


def test_normalization_preserves_two_bindings_for_one_resource():
    first = _row(binding_token="relation:1", child_id="child:1")
    second = _row(binding_token="relation:2", child_id="child:2")

    resources, bindings, links = normalize_media_v3_rows(
        [("char:3003", first), ("char:3003", second)]
    )

    assert len(resources) == 1
    assert len(bindings) == 2
    assert len(links) == 2
    assert bindings[0]["resource_id"] == bindings[1]["resource_id"]
    assert bindings[0]["binding_id"] != bindings[1]["binding_id"]
    assert links[0]["media_id"] == links[1]["media_id"]
    assert links[0]["binding_id"] != links[1]["binding_id"]


def test_v3_mysql_import_requires_authoritative_full_replace():
    row = _row()
    resources, bindings, links = normalize_media_v3_rows([("char:3003", row)])
    snapshot = WikiArtifactSnapshot(
        source_mode="active",
        build_version="candidate",
        artifact_schema_version="evb.media-asset/v3",
        parent_blocks=Path("parent_blocks.jsonl"),
        child_blocks=Path("child_blocks.jsonl"),
        media_assets=Path("runtime/media_assets.v3.jsonl"),
        manifest_sha256="a" * 64,
        input_sha256={},
        activation_id="a3",
        activation_epoch=3,
        snapshot_sha256="b" * 64,
    )
    payload = WikiImportPayload(
        pages=[],
        categories={},
        media_links=links,
        media_resources=resources,
        media_bindings=bindings,
        snapshot=snapshot,
        full_replace=False,
    )
    cfg = SimpleNamespace(mysql=SimpleNamespace(
        host="127.0.0.1", port=3307, user="wiki", password="secret",
        database="reverse1999_wiki", charset="utf8mb4",
    ))

    with pytest.raises(ValueError, match="authoritative full replacements"):
        import_payload_to_mysql(payload, cfg)


def test_v3_full_replace_inserts_resources_and_all_bindings_in_one_commit(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.calls.append((" ".join(str(sql).split()), tuple(params)))

        def executemany(self, sql, rows):
            self.calls.append((" ".join(str(sql).split()), tuple(tuple(row) for row in rows)))

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

    first = _row(binding_token="relation:1", child_id="child:1")
    second = _row(binding_token="relation:2", child_id="child:2")
    resources, bindings, links = normalize_media_v3_rows(
        [("char:3003", first), ("char:3003", second)]
    )
    snapshot = WikiArtifactSnapshot(
        source_mode="active", build_version="candidate",
        artifact_schema_version="evb.media-asset/v3",
        parent_blocks=Path("parent_blocks.jsonl"), child_blocks=Path("child_blocks.jsonl"),
        media_assets=Path("runtime/media_assets.v3.jsonl"), manifest_sha256="a" * 64,
        input_sha256={}, activation_id="a3", activation_epoch=3, snapshot_sha256="b" * 64,
    )
    payload = WikiImportPayload(
        pages=[{
            "page_id": "char:3003", "page_type": "character", "title": "槲寄生",
            "subtitle": "Druvis III", "category": "角色", "route": "/wiki/character/3003",
            "source_pageid": 3003, "source_title": "Data:Char/3003.json",
            "content_json": {"blocks": []}, "updated_at": "2026-07-20T00:00:00",
        }],
        categories={"character": {
            "category_key": "character", "label": "角色", "page_count": 1,
            "template_group": "character", "animation_profile": "entity-list",
            "theme_token": "character",
        }},
        media_links=links, media_resources=resources, media_bindings=bindings,
        snapshot=snapshot, full_replace=True,
    )
    connection = Connection()
    monkeypatch.setitem(sys.modules, "pymysql", SimpleNamespace(
        connect=lambda **_kwargs: connection,
        cursors=SimpleNamespace(DictCursor=object),
    ))
    cfg = SimpleNamespace(mysql=SimpleNamespace(
        host="127.0.0.1", port=3307, user="wiki", password="secret",
        database="reverse1999_wiki", charset="utf8mb4",
    ))

    result = import_payload_to_mysql(payload, cfg)

    sql = [statement for statement, _params in connection.cursor_instance.calls]
    assert sql.index("DELETE FROM wiki_media_bindings") < sql.index("DELETE FROM wiki_media_resources")
    assert sum("INSERT INTO wiki_media_resources" in statement for statement in sql) == 1
    assert sum("INSERT INTO wiki_media_bindings" in statement for statement in sql) == 2
    assert "DELETE FROM wiki_media_links" not in sql
    assert result["media_resources"] == 1
    assert result["media_bindings"] == 2
    assert connection.committed is True
    assert connection.began is True
    assert connection.rolled_back is False
    assert connection.closed is True
