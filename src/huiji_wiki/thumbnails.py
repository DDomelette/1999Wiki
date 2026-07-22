"""Explicit Wiki thumbnail planning helpers."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping


IMAGE_TYPES = {"image", "portrait", "skill", "item", "poster", "psychube"}
THUMBNAIL_PREFIX = "reverse1999/wiki-thumbnail/"


def build_thumbnail_plan(rows: Iterable[Mapping[str, object]], public_base_url: str, bucket: str, *, max_width: int = 480, limit: int = 0) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        media_id = str(row.get("media_id") or row.get("asset_id") or "")
        asset_type = str(row.get("asset_type") or "").lower()
        source_url = str(row.get("url") or "")
        if not media_id or media_id in seen or asset_type not in IMAGE_TYPES or not source_url.startswith(("http://", "https://")):
            continue
        seen.add(media_id)
        digest = hashlib.sha1(f"{media_id}|{max_width}".encode("utf-8")).hexdigest()
        object_key = f"{THUMBNAIL_PREFIX}{digest[:2]}/{digest}-w{max_width}.webp"
        entries.append({
            "sourceMediaId": media_id,
            "sourceUrl": source_url,
            "thumbnailObjectKey": object_key,
            "thumbnailUrl": f"{public_base_url.rstrip('/')}/{bucket}/{object_key}",
            "maxWidth": max_width,
            "status": "planned",
        })
        if limit and len(entries) >= limit:
            break
    return {"schemaVersion": "wiki.thumbnail-map/v1", "mode": "dry-run", "entries": entries}


def validate_apply_confirmation(apply: bool, confirmation: str) -> None:
    if apply and confirmation != THUMBNAIL_PREFIX:
        raise ValueError(f"apply requires exact prefix confirmation: {THUMBNAIL_PREFIX}")


def refuse_thumbnail_collision(client: object, bucket: str, object_key: str) -> None:
    try:
        client.stat_object(bucket, object_key)  # type: ignore[attr-defined]
    except Exception as exc:
        if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return
        raise
    raise RuntimeError(f"thumbnail collision refused: {object_key}")
