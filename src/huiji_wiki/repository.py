"""Repository layer for the Huiji wiki browser API."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from config.config import Config
from src.assets.public_url import project_media_row
from src.huiji_wiki.models import (
    WikiCategory,
    WikiLinkSpan,
    WikiMediaLink,
    WikiPage,
    WikiRelation,
    is_public_media_url,
    sanitize_media_item,
)


@dataclass(frozen=True)
class WikiListCursor:
    version: int
    offset: int
    filter_fingerprint: str


class InvalidWikiCursor(ValueError):
    pass


class WikiRepositoryUnavailable(RuntimeError):
    pass


def wiki_list_filter_fingerprint(*, category: str, q: str, page_type: str) -> str:
    value = f"{category}\0{q}\0{page_type}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def encode_wiki_list_cursor(cursor: WikiListCursor) -> str:
    payload = json.dumps(
        {"v": cursor.version, "o": cursor.offset, "f": cursor.filter_fingerprint},
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_wiki_list_cursor(value: str, *, expected_fingerprint: str) -> WikiListCursor:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode((value + padding).encode("ascii"), altchars=b"-_", validate=True)
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError, ValueError) as exc:
        raise InvalidWikiCursor("invalid cursor encoding") from exc
    if not isinstance(payload, dict) or set(payload) != {"v", "o", "f"}:
        raise InvalidWikiCursor("invalid cursor payload")
    version = payload.get("v")
    offset = payload.get("o")
    fingerprint = payload.get("f")
    if version != 1 or isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise InvalidWikiCursor("unsupported cursor")
    if not isinstance(fingerprint, str) or fingerprint != expected_fingerprint:
        raise InvalidWikiCursor("cursor filter mismatch")
    return WikiListCursor(version=version, offset=offset, filter_fingerprint=fingerprint)


class WikiRepository(Protocol):
    def list_categories(self) -> list[WikiCategory]: ...

    def list_pages(
        self,
        category: str = "",
        q: str = "",
        page_type: str = "",
        limit: int = 30,
        cursor: str = "",
    ) -> tuple[list[WikiPage], str | None]: ...

    def get_page_detail(self, page_id: str) -> dict[str, Any]: ...

    def get_page_detail_by_route(self, route: str) -> dict[str, Any]: ...

    def resolve_route(self, entity_id: str = "", source_id: str = "", title: str = "") -> str | None: ...

    def first_media_url_by_page(self, page_ids: list[str]) -> dict[str, str]: ...

    def get_health(self) -> dict[str, Any]: ...


class MySQLWikiRepository:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _connect(self):
        import pymysql

        return pymysql.connect(
            host=self.cfg.mysql.host,
            port=self.cfg.mysql.port,
            user=self.cfg.mysql.user,
            password=self.cfg.mysql.password,
            database=self.cfg.mysql.database,
            charset=self.cfg.mysql.charset,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def ensure_schema(self) -> None:
        return None

    def list_categories(self) -> list[WikiCategory]:
        self.ensure_schema()
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        c.category_key AS `key`,
                        c.label AS label,
                        COALESCE(NULLIF(COUNT(p.page_id), 0), c.page_count) AS count,
                        c.template_group,
                        c.animation_profile,
                        c.theme_token
                    FROM wiki_categories c
                    LEFT JOIN wiki_pages p ON p.category = c.label OR p.category = c.category_key
                    GROUP BY
                        c.category_key,
                        c.label,
                        c.page_count,
                        c.template_group,
                        c.animation_profile,
                        c.theme_token
                    ORDER BY
                        CASE c.category_key
                            WHEN 'character' THEN 10
                            WHEN 'psychube' THEN 20
                            WHEN 'story' THEN 30
                            WHEN 'world' THEN 40
                            WHEN 'faction' THEN 50
                            WHEN 'calendar' THEN 60
                            ELSE 999
                        END,
                        count DESC,
                        c.label ASC
                    """
                )
                return [
                    WikiCategory(
                        key=str(row.get("key", "")),
                        label=str(row.get("label", "")),
                        count=int(row.get("count", 0) or 0),
                        template_group=str(row.get("template_group", "")),
                        animation_profile=str(row.get("animation_profile", "")),
                        theme_token=str(row.get("theme_token", "")),
                    )
                    for row in cur.fetchall()
                ]
        except Exception:
            return []

    def list_pages(
        self,
        category: str = "",
        q: str = "",
        page_type: str = "",
        limit: int = 30,
        cursor: str = "",
    ) -> tuple[list[WikiPage], str | None]:
        self.ensure_schema()
        page_limit = max(1, min(int(limit or 30), 100))
        fingerprint = wiki_list_filter_fingerprint(category=category, q=q, page_type=page_type)
        offset = (
            decode_wiki_list_cursor(cursor, expected_fingerprint=fingerprint).offset
            if cursor
            else 0
        )
        clauses: list[str] = []
        filter_params: list[Any] = []
        if category:
            clauses.append(
                """
                (
                    p.category = %s
                    OR p.page_type = %s
                    OR p.category = (
                        SELECT c.label FROM wiki_categories c
                        WHERE c.category_key = %s
                        LIMIT 1
                    )
                )
                """
            )
            filter_params.extend([category, category, category])
        if page_type:
            clauses.append("p.page_type = %s")
            filter_params.append(page_type)
        if q:
            needle = f"%{q}%"
            clauses.append(
                """
                (
                    p.title LIKE %s
                    OR p.subtitle LIKE %s
                    OR p.source_title LIKE %s
                    OR COALESCE(alias_rank.alias_match, 0) = 1
                )
                """
            )
            filter_params.extend([needle, needle, needle])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        fetch_limit = page_limit + 1
        alias_sql = ""
        candidate_fields = "0 AS match_rank, 0 AS alias_priority"
        query_params: list[Any] = []
        if q:
            needle = f"%{q}%"
            candidate_fields = """
                CASE
                    WHEN p.title = %s THEN 0
                    WHEN p.title LIKE %s THEN 1
                    WHEN COALESCE(alias_rank.exact_alias_match, 0) = 1 THEN 2
                    WHEN COALESCE(alias_rank.alias_match, 0) = 1 THEN 3
                    WHEN p.subtitle LIKE %s THEN 4
                    WHEN p.source_title LIKE %s THEN 5
                    ELSE 6
                END AS match_rank,
                COALESCE(alias_rank.alias_priority, 0) AS alias_priority
            """
            alias_sql = """
                LEFT JOIN (
                    SELECT page_id,
                           MAX(CASE WHEN alias = %s THEN 1 ELSE 0 END) AS exact_alias_match,
                           MAX(CASE WHEN alias LIKE %s THEN 1 ELSE 0 END) AS alias_match,
                           MAX(CASE WHEN alias = %s OR alias LIKE %s THEN priority ELSE 0 END) AS alias_priority
                    FROM wiki_aliases
                    GROUP BY page_id
                ) alias_rank ON alias_rank.page_id = p.page_id
            """
            query_params.extend([q, needle, needle, needle])
            query_params.extend([q, needle, q, needle])
        candidate_sql = (
            "SELECT p.page_id, p.title, p.subtitle, p.source_title, "
            f"{candidate_fields} FROM wiki_pages p {alias_sql}{where} "
            "ORDER BY match_rank ASC, alias_priority DESC, p.page_id ASC LIMIT %s OFFSET %s"
        )
        sql = (
            "SELECT p.page_id, p.page_type, p.title, p.subtitle, p.category, p.route, "
            "p.source_pageid, p.source_title, p.content_json, p.updated_at "
            f"FROM ({candidate_sql}) ranked "
            "JOIN wiki_pages p ON p.page_id = ranked.page_id "
            "ORDER BY ranked.match_rank ASC, ranked.alias_priority DESC, ranked.page_id ASC"
        )
        query_params.extend(filter_params)
        query_params.extend([fetch_limit, offset])
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(sql, tuple(query_params))
                rows = list(cur.fetchall())
        except Exception as exc:
            raise WikiRepositoryUnavailable("wiki page list query failed") from exc
        has_more = len(rows) > page_limit
        next_cursor = (
            encode_wiki_list_cursor(
                WikiListCursor(version=1, offset=offset + page_limit, filter_fingerprint=fingerprint)
            )
            if has_more
            else None
        )
        rows = rows[:page_limit]
        return [self._page_from_row(row) for row in rows], next_cursor

    def get_page_detail(self, page_id: str) -> dict[str, Any]:
        self.ensure_schema()
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT page_id, page_type, title, subtitle, category, route, source_pageid, source_title,
                           content_json, updated_at
                    FROM wiki_pages WHERE page_id = %s
                    """,
                    (page_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise KeyError(page_id)
                page = self._page_from_row(row)
                artifact_schema = self._installed_artifact_schema(cur)
                if artifact_schema == "evb.media-asset/v3":
                    cur.execute(
                        """
                        SELECT b.page_id, b.binding_id, b.resource_id, b.section_key,
                               r.media_id, b.media_role, b.sort_order AS display_order,
                               '' AS fallback_media_id, r.object_key, r.url, r.asset_type, r.mime,
                               b.title, r.sha1, r.width, r.height, b.variant, b.attach_policy,
                               b.child_id, b.parent_id, b.panel_group, b.sort_order, r.duration_ms,
                               b.owner_entity_id, b.owner_page_id, b.skin_id, b.event_name,
                               b.language, b.source_binding_token, b.binding_status
                        FROM wiki_media_bindings b
                        JOIN wiki_media_resources r ON r.resource_id = b.resource_id
                        WHERE b.page_id = %s
                        ORDER BY b.sort_order ASC, b.binding_id ASC
                        """,
                        (page_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT page_id, section_key, media_id, media_role, display_order, fallback_media_id,
                               object_key, url, asset_type, mime, title, sha1, width, height
                        FROM wiki_media_links WHERE page_id = %s
                        ORDER BY display_order ASC
                        """,
                        (page_id,),
                    )
                projected_rows = (
                    project_media_row(
                        item,
                        base_url=self.cfg.assets.public_base_url,
                        bucket_name=self.cfg.assets.bucket_name,
                    )
                    for item in cur.fetchall()
                )
                media_links = [
                    payload
                    for payload in (
                        WikiMediaLink.from_json(item).to_api()
                        for item in projected_rows
                        if item is not None
                    )
                    if payload
                ]
                cur.execute(
                    """
                    SELECT from_page_id, to_page_id, relation_type, label, confidence
                    FROM wiki_relations WHERE from_page_id = %s OR to_page_id = %s
                    """,
                    (page_id, page_id),
                )
                relations = [
                    WikiRelation(
                        from_page_id=str(item.get("from_page_id", "")),
                        to_page_id=str(item.get("to_page_id", "")),
                        relation_type=str(item.get("relation_type", "")),
                        label=str(item.get("label", "")),
                        confidence=float(item.get("confidence", 0.0) or 0.0),
                    ).to_json()
                    for item in cur.fetchall()
                ]
                cur.execute(
                    """
                    SELECT page_id, section_key, text, target_route, confidence
                    FROM wiki_link_spans WHERE page_id = %s
                    """,
                    (page_id,),
                )
                link_spans = [
                    WikiLinkSpan(
                        page_id=str(item.get("page_id", "")),
                        section_key=str(item.get("section_key", "")),
                        text=str(item.get("text", "")),
                        target_route=str(item.get("target_route", "")),
                        confidence=float(item.get("confidence", 0.0) or 0.0),
                    ).to_json()
                    for item in cur.fetchall()
                ]
        except KeyError:
            raise
        except Exception as exc:
            raise KeyError(page_id) from exc
        payload = page.to_api()
        payload["content"] = dict(page.content_json or {})
        return {**payload, "mediaLinks": media_links, "relations": relations, "linkSpans": link_spans}

    def get_page_detail_by_route(self, route: str) -> dict[str, Any]:
        self.ensure_schema()
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT page_id FROM wiki_pages WHERE route = %s LIMIT 1", (route,))
                row = cur.fetchone()
                if not row:
                    raise KeyError(route)
                page_id = str(row["page_id"])
        except KeyError:
            raise
        except Exception as exc:
            raise KeyError(route) from exc
        return self.get_page_detail(page_id)

    def resolve_route(self, entity_id: str = "", source_id: str = "", title: str = "") -> str | None:
        self.ensure_schema()
        try:
            with self._connect() as conn, conn.cursor() as cur:
                if entity_id:
                    cur.execute("SELECT route FROM wiki_pages WHERE page_id LIKE %s LIMIT 1", (f"%:{entity_id}",))
                    row = cur.fetchone()
                    if row:
                        return str(row["route"])
                if source_id:
                    cur.execute(
                        "SELECT route FROM wiki_pages WHERE source_title = %s OR source_pageid = %s LIMIT 1",
                        (source_id, source_id),
                    )
                    row = cur.fetchone()
                    if row:
                        return str(row["route"])
                if title:
                    cur.execute(
                        """
                        SELECT route
                        FROM wiki_pages
                        WHERE title = %s OR subtitle = %s
                        ORDER BY CASE WHEN title = %s THEN 0 ELSE 1 END, page_id ASC
                        LIMIT 1
                        """,
                        (title, title, title),
                    )
                    row = cur.fetchone()
                    if row:
                        return str(row["route"])
                    cur.execute(
                        """
                        SELECT p.route
                        FROM wiki_aliases a
                        JOIN wiki_pages p ON p.page_id = a.page_id
                        WHERE a.alias = %s
                        ORDER BY a.priority DESC
                        LIMIT 1
                        """,
                        (title,),
                    )
                    row = cur.fetchone()
                    if row:
                        return str(row["route"])
        except Exception:
            return None
        return None

    def first_media_url_by_page(self, page_ids: list[str]) -> dict[str, str]:
        if not page_ids:
            return {}
        placeholders = ",".join(["%s"] * len(page_ids))
        result: dict[str, str] = {}
        try:
            with self._connect() as conn, conn.cursor() as cur:
                artifact_schema = self._installed_artifact_schema(cur)
                if artifact_schema == "evb.media-asset/v3":
                    sql = (
                        "SELECT b.page_id, r.object_key, r.url, b.media_role "
                        "FROM wiki_media_bindings b "
                        "JOIN wiki_media_resources r ON r.resource_id = b.resource_id "
                        "WHERE b.page_id IN (" + placeholders + ") AND r.object_key <> '' "
                        "AND (LOWER(r.asset_type) IN "
                        "('image','portrait','skill','skin','psychube','poster','item') "
                        "OR LOWER(r.mime) LIKE 'image/%%') "
                        "ORDER BY b.page_id ASC, "
                        "CASE WHEN b.media_role = 'roster_avatar' THEN 0 "
                        "WHEN b.media_role IN ('stage_live2d','stage_portrait') THEN 1 ELSE 2 END ASC, "
                        "b.sort_order ASC, b.binding_id ASC"
                    )
                else:
                    sql = (
                        "SELECT page_id, object_key, url, media_role "
                        "FROM wiki_media_links WHERE page_id IN ("
                        + placeholders
                        + ") AND object_key <> '' "
                        + "AND (LOWER(asset_type) IN ('image','portrait','skill','skin','psychube','poster','item') "
                        + "OR LOWER(mime) LIKE 'image/%%') "
                        + "ORDER BY page_id ASC, "
                        + "CASE WHEN media_role = 'roster_avatar' THEN 0 "
                        + "WHEN media_role IN ('stage_live2d','stage_portrait') THEN 1 ELSE 2 END ASC, "
                        + "display_order ASC"
                    )
                cur.execute(sql, tuple(page_ids))
                rows = list(cur.fetchall())
        except Exception:
            return result
        for row in rows:
            page_id = str(row.get("page_id", ""))
            projected = project_media_row(
                row,
                base_url=self.cfg.assets.public_base_url,
                bucket_name=self.cfg.assets.bucket_name,
            )
            url = str(projected.get("url", "")) if projected is not None else ""
            if page_id not in result and is_public_media_url(url):
                result[page_id] = url
        return result

    def get_health(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ready": False,
            "pageCount": 0,
            "categoryCount": 0,
            "mediaLinkCount": 0,
            "mediaResourceCount": 0,
            "mediaBindingCount": 0,
            "linkSpanCount": 0,
            "aliasCount": 0,
            "sourceMode": "",
            "buildVersion": "",
            "artifactSchemaVersion": "",
            "activationEpoch": None,
            "manifestSha256Prefix": "",
            "stale": False,
            "error": "",
        }
        tables = [
            ("pageCount", "wiki_pages"),
            ("categoryCount", "wiki_categories"),
            ("mediaLinkCount", "wiki_media_links"),
            ("linkSpanCount", "wiki_link_spans"),
            ("aliasCount", "wiki_aliases"),
        ]
        try:
            self.ensure_schema()
            with self._connect() as conn, conn.cursor() as cur:
                for key, table in tables:
                    cur.execute(f"SELECT COUNT(*) AS count FROM {table}")
                    row = cur.fetchone() or {}
                    payload[key] = int(row.get("count", 0) or 0)
                try:
                    cur.execute(
                        """SELECT source_mode, build_version, artifact_schema_version, activation_epoch,
                                  manifest_sha256, snapshot_sha256
                           FROM wiki_import_snapshots WHERE id = 1"""
                    )
                    snapshot = cur.fetchone() or {}
                except Exception:
                    snapshot = {}
                payload.update({
                    "sourceMode": str(snapshot.get("source_mode") or ""),
                    "buildVersion": str(snapshot.get("build_version") or ""),
                    "artifactSchemaVersion": str(snapshot.get("artifact_schema_version") or ""),
                    "activationEpoch": snapshot.get("activation_epoch"),
                    "manifestSha256Prefix": str(snapshot.get("manifest_sha256") or "")[:12].lower(),
                })
                if payload["artifactSchemaVersion"] == "evb.media-asset/v3":
                    for key, table in (
                        ("mediaResourceCount", "wiki_media_resources"),
                        ("mediaBindingCount", "wiki_media_bindings"),
                    ):
                        cur.execute(f"SELECT COUNT(*) AS count FROM {table}")
                        row = cur.fetchone() or {}
                        payload[key] = int(row.get("count", 0) or 0)
                huiji = getattr(self.cfg, "huiji", None)
                current_build = str(getattr(huiji, "build_version", ""))
                pointer = Path(getattr(huiji, "processed_root", ".")) / "active_build.v1.json"
                if huiji is not None and pointer.is_file():
                    try:
                        pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
                        current_build = str(pointer_data.get("build_version") or pointer_data.get("buildVersion") or current_build)
                        payload["stale"] = (
                            payload["sourceMode"] != "active"
                            or payload["buildVersion"] != current_build
                            or payload["activationEpoch"] != pointer_data.get("activation_epoch")
                            or str(snapshot.get("manifest_sha256") or "") != str(pointer_data.get("build_manifest_sha256") or "")
                        )
                    except (OSError, json.JSONDecodeError):
                        payload["stale"] = True
                elif payload["sourceMode"] == "active":
                    payload["stale"] = True
                payload["stale"] = payload["stale"] or bool(payload["buildVersion"] and payload["buildVersion"] != current_build)
            payload["ready"] = payload["pageCount"] > 0 and (
                payload["artifactSchemaVersion"] != "evb.media-asset/v3"
                or payload["mediaBindingCount"] > 0
            )
        except Exception as exc:
            payload["error"] = exc.__class__.__name__
        return payload

    @staticmethod
    def _json_value(value: Any, default: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return default

    def _page_from_row(self, row: dict[str, Any]) -> WikiPage:
        content = row.get("content_json")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {}
        return WikiPage(
            page_id=str(row.get("page_id", "")),
            page_type=str(row.get("page_type", "generic")),
            title=str(row.get("title", "")),
            subtitle=str(row.get("subtitle", "")),
            category=str(row.get("category", "")),
            route=str(row.get("route", "")),
            source_pageid=row.get("source_pageid"),
            source_title=str(row.get("source_title", "")),
            content_json=dict(content or {}),
            updated_at=str(row.get("updated_at", "")),
        )

    @staticmethod
    def _installed_artifact_schema(cur: Any) -> str:
        try:
            cur.execute(
                "SELECT artifact_schema_version FROM wiki_import_snapshots WHERE id = 1"
            )
            row = cur.fetchone() or {}
            return str(row.get("artifact_schema_version") or "")
        except Exception:
            return ""
