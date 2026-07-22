"""Build Wiki display rows from Huiji processed artifacts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.huiji_wiki.content_blocks import build_content_blocks
from src.huiji_wiki.crawler_projection import (
    CrawlerCharacterProjection,
    CrawlerProjectionConfig,
    build_crawler_character_projection,
    validate_crawler_only_payload,
)
from src.huiji_wiki.snapshot import WikiArtifactSnapshot
from src.huiji_wiki.media_v3 import normalize_media_v3_rows


CATEGORY_META: dict[str, dict[str, str]] = {
    "character": {
        "label": "角色",
        "template_group": "character",
        "animation_profile": "entity-list",
        "theme_token": "character",
    },
    "psychube": {
        "label": "心相",
        "template_group": "psychube",
        "animation_profile": "artifact-list",
        "theme_token": "psychube",
    },
    "story": {
        "label": "剧情",
        "template_group": "story",
        "animation_profile": "story-list",
        "theme_token": "story",
    },
    "item": {
        "label": "物品",
        "template_group": "generic",
        "animation_profile": "generic-list",
        "theme_token": "item",
    },
}


@dataclass
class WikiImportPayload:
    pages: list[dict[str, Any]]
    categories: dict[str, dict[str, Any]]
    media_links: list[dict[str, Any]]
    media_resources: list[dict[str, Any]] = field(default_factory=list)
    media_bindings: list[dict[str, Any]] = field(default_factory=list)
    snapshot: WikiArtifactSnapshot | None = None
    full_replace: bool = False


def build_wiki_import_payload(
    source: Path | WikiArtifactSnapshot,
    *,
    include_character: bool = False,
    raw_root: Path | None = None,
    asset_public_base_url: str = "",
    asset_bucket_name: str = "",
    asset_object_prefix: str = "reverse1999",
) -> WikiImportPayload:
    snapshot = source if isinstance(source, WikiArtifactSnapshot) else None
    processed_dir = Path(source) if snapshot is None else snapshot.parent_blocks.parent
    parent_path = processed_dir / "parent_blocks.jsonl" if snapshot is None else snapshot.parent_blocks
    child_path = processed_dir / "child_blocks.jsonl" if snapshot is None else snapshot.child_blocks
    media_path = processed_dir / "media_assets.jsonl" if snapshot is None else snapshot.media_assets
    children = _load_children(child_path)
    media_by_parent = _load_media_by_parent(media_path)
    pages: list[dict[str, Any]] = []
    media_links: list[dict[str, Any]] = []
    media_resources: list[dict[str, Any]] = []
    media_bindings: list[dict[str, Any]] = []
    v3_rows: list[tuple[str, dict[str, Any]]] = []
    is_media_v3 = snapshot is not None and snapshot.artifact_schema_version == "evb.media-asset/v3"
    category_counts: dict[str, int] = {}
    now = datetime.now().isoformat(timespec="seconds")
    crawler_projection = _crawler_projection(
        include_character=include_character,
        raw_root=raw_root,
        asset_public_base_url=asset_public_base_url,
        asset_bucket_name=asset_bucket_name,
        asset_object_prefix=asset_object_prefix,
    )

    parent_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for parent in _read_jsonl(parent_path):
        category = str(parent.get("category") or parent.get("entity_type") or "")
        if not include_character and category == "character":
            continue
        if category not in CATEGORY_META:
            continue
        entity_id = _clean_text(parent.get("entity_id") or _route_tail(str(parent.get("parent_id") or "")))
        if entity_id:
            parent_groups.setdefault((category, entity_id), []).append(parent)

    for (category, entity_id), group in parent_groups.items():
        parent = next((row for row in group if str(row.get("section_kind") or "") == "entity"), group[0])

        page_id = str(parent.get("parent_id") or "")
        if not page_id:
            continue
        child_ids = [child_id for row in group for child_id in row.get("child_ids", [])]
        child_rows = [children[child_id] for child_id in child_ids if child_id in children]
        title = _clean_text(parent.get("title") or parent.get("entity_name") or page_id)
        source_title = _first_source_title(parent, child_rows)
        summary = _summary_from_children(child_rows) or title
        category_meta = CATEGORY_META[category]
        content = {
            "contentVersion": 1,
            "blocks": build_content_blocks(page_id, child_rows),
            "summary": summary,
            "sectionKind": str(parent.get("section_kind") or ""),
            "sourceRefs": parent.get("source_refs") or [],
            "childCount": len(child_rows),
        }
        character_projection = crawler_projection.characters.get(page_id)
        if category == "character" and character_projection is not None:
            content.update(
                {
                    "crawlerProjectionVersion": 1,
                    "crawlerSourceTitle": character_projection.source_title,
                    "profile": character_projection.profile,
                    "skins": list(character_projection.skins),
                    "blocks": _merge_blocks(
                        list(content["blocks"]),
                        list(character_projection.blocks),
                    ),
                }
            )
        page = {
            "page_id": page_id,
            "page_type": category,
            "title": _truncate(title, 255),
            "subtitle": _truncate(source_title or entity_id, 255),
            "category": category_meta["label"],
            "route": f"/wiki/{category}/{quote(entity_id, safe='')}",
            "source_pageid": None,
            "source_title": _truncate(source_title, 255),
            "content_json": content,
            "updated_at": now,
        }
        pages.append(page)
        category_counts[category] = category_counts.get(category, 0) + 1

        grouped_media = [media for row in group for media in media_by_parent.get(str(row.get("parent_id") or ""), [])]
        semantic_media = (
            list(character_projection.media_links)
            if character_projection is not None and not is_media_v3
            else []
        )
        media_links.extend(semantic_media)
        media_offset = len(semantic_media)
        for order, media in enumerate(grouped_media, start=media_offset + 1):
            if is_media_v3:
                v3_rows.append((page_id, media))
            else:
                media_links.append(_media_link_from_asset(page_id, media, order))

    if is_media_v3:
        media_resources, media_bindings, v3_links = normalize_media_v3_rows(v3_rows)
        media_links.extend(v3_links)

    categories = {
        key: {
            "category_key": key,
            "label": meta["label"],
            "page_count": count,
            "template_group": meta["template_group"],
            "animation_profile": meta["animation_profile"],
            "theme_token": meta["theme_token"],
        }
        for key, count in category_counts.items()
        for meta in [CATEGORY_META[key]]
    }
    payload = WikiImportPayload(
        pages=pages,
        categories=categories,
        media_links=media_links,
        media_resources=media_resources,
        media_bindings=media_bindings,
        snapshot=snapshot,
        full_replace=include_character,
    )
    validate_crawler_only_payload(
        {
            "pages": payload.pages,
            "categories": payload.categories,
            "media_links": payload.media_links,
        }
    )
    return payload


def _crawler_projection(
    *,
    include_character: bool,
    raw_root: Path | None,
    asset_public_base_url: str,
    asset_bucket_name: str,
    asset_object_prefix: str,
) -> CrawlerCharacterProjection:
    if not include_character:
        return CrawlerCharacterProjection(characters={})
    if raw_root is None:
        raise ValueError("crawler raw_root is required when include_character is enabled")
    if not asset_public_base_url or not asset_bucket_name:
        raise ValueError("shared MinIO public base URL and bucket are required for character import")
    return build_crawler_character_projection(
        raw_root,
        config=CrawlerProjectionConfig(
            public_base_url=asset_public_base_url,
            bucket_name=asset_bucket_name,
            object_prefix=asset_object_prefix,
        ),
    )


def _merge_blocks(
    canonical: list[dict[str, Any]],
    projected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected_sections = {str(block.get("section") or "") for block in projected}
    replace_sections = {"inheritance", "portray", "collection", "culture_dossier"}
    retained = [
        block
        for block in canonical
        if str(block.get("section") or "") not in (projected_sections & replace_sections)
    ]
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for block in [*retained, *projected]:
        block_id = str(block.get("id") or "")
        if block_id and block_id in seen:
            continue
        if block_id:
            seen.add(block_id)
        result.append(block)
    return result


def import_payload_to_mysql(payload: WikiImportPayload, cfg: Any) -> dict[str, int]:
    is_media_v3 = (
        payload.snapshot is not None
        and payload.snapshot.artifact_schema_version == "evb.media-asset/v3"
    )
    if is_media_v3 and not payload.full_replace:
        raise ValueError("media v3 imports must be authoritative full replacements")
    import pymysql

    conn = pymysql.connect(
        host=cfg.mysql.host,
        port=cfg.mysql.port,
        user=cfg.mysql.user,
        password=cfg.mysql.password,
        database=cfg.mysql.database,
        charset=cfg.mysql.charset,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        conn.begin()
        with conn.cursor() as cur:
            if payload.snapshot is not None:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wiki_import_snapshots (
                      id TINYINT NOT NULL PRIMARY KEY,
                      source_mode VARCHAR(16) NOT NULL,
                      build_version VARCHAR(64) NOT NULL,
                      artifact_schema_version VARCHAR(64) NOT NULL,
                      activation_epoch BIGINT NULL,
                      manifest_sha256 CHAR(64) NOT NULL,
                      input_sha256_json JSON NOT NULL,
                      snapshot_sha256 CHAR(64) NOT NULL,
                      imported_at_utc VARCHAR(40) NOT NULL,
                      CHECK (id = 1)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            _reconcile_authoritative_rows(cur, payload)
            for category in payload.categories.values():
                cur.execute(
                    """
                    INSERT INTO wiki_categories
                        (category_key, label, page_count, template_group, animation_profile, theme_token)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        label = VALUES(label),
                        page_count = VALUES(page_count),
                        template_group = VALUES(template_group),
                        animation_profile = VALUES(animation_profile),
                        theme_token = VALUES(theme_token)
                    """,
                    (
                        category["category_key"],
                        category["label"],
                        category["page_count"],
                        category["template_group"],
                        category["animation_profile"],
                        category["theme_token"],
                    ),
                )
            for page in payload.pages:
                cur.execute(
                    """
                    INSERT INTO wiki_pages
                        (page_id, page_type, title, subtitle, category, route, source_pageid,
                         source_title, content_json, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s)
                    ON DUPLICATE KEY UPDATE
                        page_type = VALUES(page_type),
                        title = VALUES(title),
                        subtitle = VALUES(subtitle),
                        category = VALUES(category),
                        route = VALUES(route),
                        source_title = VALUES(source_title),
                        content_json = VALUES(content_json),
                        updated_at = VALUES(updated_at)
                    """,
                    (
                        page["page_id"],
                        page["page_type"],
                        page["title"],
                        page["subtitle"],
                        page["category"],
                        page["route"],
                        page["source_pageid"],
                        page["source_title"],
                        json.dumps(page["content_json"], ensure_ascii=False),
                        page["updated_at"],
                    ),
                )
            if is_media_v3:
                _insert_media_v3_rows(cur, payload)
            elif payload.media_links:
                if not payload.full_replace:
                    page_ids = sorted({item["page_id"] for item in payload.media_links})
                    placeholders = ",".join(["%s"] * len(page_ids))
                    cur.execute(f"DELETE FROM wiki_media_links WHERE page_id IN ({placeholders})", tuple(page_ids))
                for media in payload.media_links:
                    cur.execute(
                        """
                        INSERT INTO wiki_media_links
                            (page_id, section_key, media_id, media_role, display_order, fallback_media_id,
                             object_key, url, asset_type, mime, title, sha1, width, height)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            media["page_id"],
                            media["section_key"],
                            media["media_id"],
                            media["media_role"],
                            media["display_order"],
                            media["fallback_media_id"],
                            media["object_key"],
                            media["url"],
                            media["asset_type"],
                            media["mime"],
                            media["title"],
                            media["sha1"],
                            media["width"],
                            media["height"],
                        ),
                    )
            if payload.snapshot is not None:
                snapshot = payload.snapshot
                cur.execute(
                    """
                    INSERT INTO wiki_import_snapshots
                      (id, source_mode, build_version, artifact_schema_version, activation_epoch,
                       manifest_sha256, input_sha256_json, snapshot_sha256, imported_at_utc)
                    VALUES (1, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
                    ON DUPLICATE KEY UPDATE
                      source_mode=VALUES(source_mode), build_version=VALUES(build_version),
                      artifact_schema_version=VALUES(artifact_schema_version), activation_epoch=VALUES(activation_epoch),
                      manifest_sha256=VALUES(manifest_sha256), input_sha256_json=VALUES(input_sha256_json),
                      snapshot_sha256=VALUES(snapshot_sha256), imported_at_utc=VALUES(imported_at_utc)
                    """,
                    (
                        snapshot.source_mode, snapshot.build_version, snapshot.artifact_schema_version,
                        snapshot.activation_epoch, snapshot.manifest_sha256,
                        json.dumps(dict(snapshot.input_sha256), sort_keys=True), snapshot.snapshot_sha256,
                        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    ),
                )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "pages": len(payload.pages),
        "categories": len(payload.categories),
        "media_links": len(payload.media_links),
        "media_resources": len(payload.media_resources),
        "media_bindings": len(payload.media_bindings),
    }


def _reconcile_authoritative_rows(cur: Any, payload: WikiImportPayload) -> None:
    if not payload.full_replace:
        return
    if not payload.pages or not payload.categories:
        raise ValueError("authoritative Wiki import requires non-empty pages and categories")

    page_ids = sorted({str(page["page_id"]) for page in payload.pages})
    routes = sorted({str(page["route"]) for page in payload.pages})
    category_keys = sorted(payload.categories)
    temporary_tables = (
        "wiki_import_page_ids",
        "wiki_import_routes",
        "wiki_import_category_keys",
    )
    for table in temporary_tables:
        cur.execute(f"DROP TEMPORARY TABLE IF EXISTS {table}")
    cur.execute(
        "CREATE TEMPORARY TABLE wiki_import_page_ids "
        "(page_id VARCHAR(128) NOT NULL PRIMARY KEY) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.execute(
        "CREATE TEMPORARY TABLE wiki_import_routes "
        "(route VARCHAR(255) NOT NULL PRIMARY KEY) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.execute(
        "CREATE TEMPORARY TABLE wiki_import_category_keys "
        "(category_key VARCHAR(64) NOT NULL PRIMARY KEY) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.executemany(
        "INSERT INTO wiki_import_page_ids (page_id) VALUES (%s)",
        [(page_id,) for page_id in page_ids],
    )
    cur.executemany(
        "INSERT INTO wiki_import_routes (route) VALUES (%s)",
        [(route,) for route in routes],
    )
    cur.executemany(
        "INSERT INTO wiki_import_category_keys (category_key) VALUES (%s)",
        [(key,) for key in category_keys],
    )
    cur.execute(
        "DELETE a FROM wiki_aliases AS a "
        "LEFT JOIN wiki_import_page_ids AS p ON p.page_id = a.page_id "
        "WHERE p.page_id IS NULL"
    )
    cur.execute(
        "DELETE s FROM wiki_link_spans AS s "
        "LEFT JOIN wiki_import_page_ids AS p ON p.page_id = s.page_id "
        "LEFT JOIN wiki_import_routes AS r ON r.route = s.target_route "
        "WHERE p.page_id IS NULL OR r.route IS NULL"
    )
    cur.execute(
        "DELETE p FROM wiki_pages AS p "
        "LEFT JOIN wiki_import_page_ids AS authority ON authority.page_id = p.page_id "
        "WHERE authority.page_id IS NULL"
    )
    cur.execute(
        "DELETE c FROM wiki_categories AS c "
        "LEFT JOIN wiki_import_category_keys AS authority ON authority.category_key = c.category_key "
        "WHERE authority.category_key IS NULL"
    )
    is_media_v3 = (
        payload.snapshot is not None
        and payload.snapshot.artifact_schema_version == "evb.media-asset/v3"
    )
    if not is_media_v3:
        cur.execute("DELETE FROM wiki_media_links")
    if is_media_v3:
        cur.execute("DELETE FROM wiki_media_bindings")
        cur.execute("DELETE FROM wiki_media_resources")


def _insert_media_v3_rows(cur: Any, payload: WikiImportPayload) -> None:
    for resource in payload.media_resources:
        cur.execute(
            """
            INSERT INTO wiki_media_resources
              (resource_id, media_id, asset_type, mime, filename, source_url, url, object_key,
               is_available, is_common, content_hash, quality_flags_json, sha1, source_sha1,
               content_sha256, size, duration_ms, width, height)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON),
                    %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resource["resource_id"], resource["media_id"], resource["asset_type"],
                resource["mime"], resource["filename"], resource["source_url"], resource["url"],
                resource["object_key"], resource["is_available"], resource["is_common"],
                resource["content_hash"], json.dumps(resource["quality_flags"], ensure_ascii=False),
                resource["sha1"], resource["source_sha1"], resource["content_sha256"],
                resource["size"], resource["duration_ms"], resource["width"], resource["height"],
            ),
        )
    for binding in payload.media_bindings:
        cur.execute(
            """
            INSERT INTO wiki_media_bindings
              (binding_id, resource_id, page_id, entity_id, entity_name, owner_entity_id,
               owner_page_id, parent_id, child_id, section_key, media_role, variant, skin_id,
               event_name, language, source_binding_token, source_refs_json, title, attach_policy,
               search_text, panel_group, sort_order, binding_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CAST(%s AS JSON), %s, %s, %s, %s, %s, %s)
            """,
            (
                binding["binding_id"], binding["resource_id"], binding["page_id"],
                binding["entity_id"], binding["entity_name"], binding["owner_entity_id"],
                binding["owner_page_id"], binding["parent_id"], binding["child_id"],
                binding["section_key"], binding["media_role"], binding["variant"], binding["skin_id"],
                binding["event_name"], binding["language"], binding["source_binding_token"],
                json.dumps(binding["source_refs"], ensure_ascii=False), binding["title"],
                binding["attach_policy"], binding["search_text"], binding["panel_group"],
                binding["sort_order"], binding["binding_status"],
            ),
        )


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _load_children(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("child_id")): row for row in _read_jsonl(path)}


def _load_media_by_parent(path: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in _read_jsonl(path):
        parent_id = str(row.get("parent_id") or "")
        if parent_id:
            result.setdefault(parent_id, []).append(row)
    return result


def _summary_from_children(children: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for child in children[:4]:
        text = _clean_text(child.get("text") or child.get("search_text") or "")
        if text:
            parts.append(text)
    return _truncate("\n\n".join(parts), 900)


def _first_source_title(parent: dict[str, Any], children: list[dict[str, Any]]) -> str:
    for source_refs in [parent.get("source_refs") or [], *[child.get("source_refs") or [] for child in children]]:
        for ref in source_refs:
            title = _clean_text(ref.get("title") if isinstance(ref, dict) else "")
            if title:
                return title
    return ""


def _media_link_from_asset(page_id: str, media: dict[str, Any], order: int) -> dict[str, Any]:
    return {
        "page_id": page_id,
        "section_key": str(media.get("panel_group") or media.get("asset_type") or "media"),
        "media_id": str(media.get("media_id") or media.get("asset_id") or ""),
        "media_role": str(media.get("asset_type") or ""),
        "display_order": int(media.get("sort_order") or order),
        "fallback_media_id": "",
        "object_key": str(media.get("object_key") or ""),
        "url": str(media.get("url") or ""),
        "asset_type": str(media.get("asset_type") or ""),
        "mime": str(media.get("mime") or ""),
        "title": _truncate(_clean_text(media.get("title") or ""), 255),
        "sha1": str(media.get("sha1") or ""),
        "width": int(media.get("width") or 0),
        "height": int(media.get("height") or 0),
    }


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def _truncate(value: str, limit: int) -> str:
    return value[:limit]


def _route_tail(page_id: str) -> str:
    parts = [part for part in page_id.split("/") if part and part != "profile"]
    return parts[-1] if parts else page_id
