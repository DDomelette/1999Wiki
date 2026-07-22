"""Strict media v3 validation and Wiki resource/binding normalization."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable
from urllib.parse import urlparse


MEDIA_V3_FIELD_ORDER = (
    "artifact_schema_version",
    "binding_id",
    "resource_id",
    "media_id",
    "entity_id",
    "entity_name",
    "owner_entity_id",
    "owner_page_id",
    "parent_id",
    "child_id",
    "section",
    "asset_type",
    "media_role",
    "variant",
    "skin_id",
    "event_name",
    "language",
    "source_binding_token",
    "source_refs",
    "mime",
    "filename",
    "title",
    "source_url",
    "url",
    "object_key",
    "is_available",
    "is_common",
    "attach_policy",
    "search_text",
    "content_hash",
    "panel_group",
    "sort_order",
    "duration_ms",
    "width",
    "height",
    "quality_flags",
    "sha1",
    "source_sha1",
    "content_sha256",
    "size",
    "binding_status",
)

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_REF_FIELDS = {
    "source_kind",
    "source_title",
    "source_row_id",
    "source_content_sha256",
}


def compute_binding_id(row: dict[str, Any]) -> str:
    identity = [
        "evb.media-binding/v1",
        row["owner_entity_id"],
        row["owner_page_id"],
        row["parent_id"],
        row["child_id"],
        row["section"],
        row["media_role"],
        row["variant"],
        row["skin_id"],
        row["event_name"],
        row["language"],
        row["source_binding_token"],
        row["resource_id"],
    ]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "binding:sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_media_v3_row(row: dict[str, Any]) -> dict[str, Any]:
    if "local_relpath" in row:
        raise ValueError("media v3 runtime row must not contain local_relpath")
    expected = set(MEDIA_V3_FIELD_ORDER)
    actual = set(row)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"media v3 fields differ: missing={missing}, extra={extra}")
    if tuple(row) != MEDIA_V3_FIELD_ORDER:
        raise ValueError("media v3 field order does not match the frozen contract")
    if row["artifact_schema_version"] != "evb.media-asset/v3":
        raise ValueError("invalid media v3 row schema")

    string_fields = [
        name for name in MEDIA_V3_FIELD_ORDER
        if name not in {
            "source_refs", "is_available", "is_common", "sort_order", "duration_ms",
            "width", "height", "quality_flags", "size",
        }
    ]
    for field in string_fields:
        if not isinstance(row[field], str):
            raise ValueError(f"media v3 {field} must be a string")
    for field in ("owner_entity_id", "owner_page_id", "parent_id", "section", "media_role", "source_binding_token"):
        if not row[field]:
            raise ValueError(f"media v3 {field} must not be empty")

    for field in ("is_available", "is_common"):
        if not isinstance(row[field], bool):
            raise ValueError(f"media v3 {field} must be boolean")
    for field in ("sort_order", "duration_ms", "width", "height", "size"):
        if isinstance(row[field], bool) or not isinstance(row[field], int) or row[field] < 0:
            raise ValueError(f"media v3 {field} must be a non-negative integer")

    if not _is_http_url(row["url"]):
        raise ValueError("media v3 url must be public HTTP(S)")
    if not _HEX_40.fullmatch(row["sha1"]):
        raise ValueError("invalid media v3 sha1")
    if not _HEX_40.fullmatch(row["source_sha1"]):
        raise ValueError("invalid media v3 source_sha1")
    if not _HEX_64.fullmatch(row["content_sha256"]):
        raise ValueError("invalid media v3 content_sha256")
    if row["content_hash"] != row["content_sha256"]:
        raise ValueError("media v3 content_hash must equal content_sha256")
    if row["resource_id"] != f"resource:sha256:{row['content_sha256']}":
        raise ValueError("media v3 resource_id does not match content_sha256")
    if row["media_id"] != f"media:sha1:{row['sha1']}":
        raise ValueError("media v3 media_id does not match sha1")
    if row["binding_id"] != compute_binding_id(row):
        raise ValueError("media v3 binding_id does not match the frozen identity")
    if row["binding_status"] not in {"exact", "not_applicable"}:
        raise ValueError("invalid media v3 binding_status")

    quality_flags = row["quality_flags"]
    if (
        not isinstance(quality_flags, list)
        or any(not isinstance(item, str) for item in quality_flags)
        or quality_flags != sorted(set(quality_flags))
    ):
        raise ValueError("media v3 quality_flags must be sorted and unique")
    refs = row["source_refs"]
    if not isinstance(refs, list) or not refs:
        raise ValueError("media v3 source_refs must be a non-empty array")
    for ref in refs:
        if not isinstance(ref, dict) or not _SOURCE_REF_FIELDS.issubset(ref):
            raise ValueError("media v3 source_refs entry is incomplete")
        if not _HEX_64.fullmatch(str(ref.get("source_content_sha256") or "")):
            raise ValueError("media v3 source ref hash is invalid")
    return row


def normalize_media_v3_rows(
    rows: Iterable[tuple[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    resources_by_id: dict[str, dict[str, Any]] = {}
    bindings_by_id: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    for page_id, candidate in rows:
        row = validate_media_v3_row(candidate)
        resource = _resource_from_row(row)
        existing_resource = resources_by_id.get(resource["resource_id"])
        if existing_resource is not None and existing_resource != resource:
            raise ValueError(f"conflicting resource payload: {resource['resource_id']}")
        resources_by_id[resource["resource_id"]] = resource

        binding = _binding_from_row(page_id, row)
        if binding["binding_id"] in bindings_by_id:
            raise ValueError(f"duplicate media binding: {binding['binding_id']}")
        bindings_by_id[binding["binding_id"]] = binding
        links.append(_link_from_row(page_id, row))
    return list(resources_by_id.values()), list(bindings_by_id.values()), links


def _resource_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_id": row["resource_id"],
        "media_id": row["media_id"],
        "asset_type": row["asset_type"],
        "mime": row["mime"],
        "filename": row["filename"],
        "source_url": row["source_url"],
        "url": row["url"],
        "object_key": row["object_key"],
        "is_available": row["is_available"],
        "is_common": row["is_common"],
        "content_hash": row["content_hash"],
        "quality_flags": list(row["quality_flags"]),
        "sha1": row["sha1"],
        "source_sha1": row["source_sha1"],
        "content_sha256": row["content_sha256"],
        "size": row["size"],
        "duration_ms": row["duration_ms"],
        "width": row["width"],
        "height": row["height"],
    }


def _binding_from_row(page_id: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "binding_id": row["binding_id"],
        "resource_id": row["resource_id"],
        "page_id": page_id,
        "entity_id": row["entity_id"],
        "entity_name": row["entity_name"],
        "owner_entity_id": row["owner_entity_id"],
        "owner_page_id": row["owner_page_id"],
        "parent_id": row["parent_id"],
        "child_id": row["child_id"],
        "section_key": row["section"],
        "media_role": row["media_role"],
        "variant": row["variant"],
        "skin_id": row["skin_id"],
        "event_name": row["event_name"],
        "language": row["language"],
        "source_binding_token": row["source_binding_token"],
        "source_refs": list(row["source_refs"]),
        "title": row["title"],
        "attach_policy": row["attach_policy"],
        "search_text": row["search_text"],
        "panel_group": row["panel_group"],
        "sort_order": row["sort_order"],
        "binding_status": row["binding_status"],
    }


def _link_from_row(page_id: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_id": page_id,
        "binding_id": row["binding_id"],
        "resource_id": row["resource_id"],
        "section_key": row["section"],
        "media_id": row["media_id"],
        "media_role": row["media_role"],
        "display_order": row["sort_order"],
        "fallback_media_id": "",
        "object_key": row["object_key"],
        "url": row["url"],
        "asset_type": row["asset_type"],
        "mime": row["mime"],
        "title": row["title"],
        "sha1": row["sha1"],
        "width": row["width"],
        "height": row["height"],
        "variant": row["variant"],
        "attach_policy": row["attach_policy"],
        "child_id": row["child_id"],
        "parent_id": row["parent_id"],
        "panel_group": row["panel_group"],
        "sort_order": row["sort_order"],
        "duration_ms": row["duration_ms"],
        "owner_entity_id": row["owner_entity_id"],
        "owner_page_id": row["owner_page_id"],
        "skin_id": row["skin_id"],
        "event_name": row["event_name"],
        "language": row["language"],
        "source_binding_token": row["source_binding_token"],
        "binding_status": row["binding_status"],
    }


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
