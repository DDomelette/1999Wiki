"""Media normalization helpers for Huiji RAG assets."""
from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urlsplit, urlunsplit


COMMON_PATTERNS = ("common", "logo", "icon")
FORMAT_PRIORITY = {
    ".webp": 60,
    ".png": 50,
    ".jpg": 40,
    ".jpeg": 40,
    ".gif": 30,
    ".mp4": 50,
    ".webm": 40,
    ".mp3": 50,
    ".ogg": 40,
    ".wav": 30,
}


@dataclass(frozen=True)
class MediaAsset:
    media_id: str
    entity_id: str
    entity_name: str
    parent_id: str
    child_id: str
    asset_type: str
    mime: str
    filename: str
    title: str
    source_url: str
    url: str
    object_key: str
    is_available: bool
    is_common: bool
    attach_policy: str
    search_text: str
    content_hash: str
    panel_group: str
    sort_order: int
    duration_ms: int
    quality_flags: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row["quality_flags"] = list(self.quality_flags)
        return row


def classify_asset_type(filename: str) -> str:
    lower = filename.lower()
    if any(pattern in lower for pattern in COMMON_PATTERNS):
        return "common"
    if lower.endswith((".mp3", ".ogg", ".wav")):
        return "voice"
    if lower.endswith((".mp4", ".webm", ".mov")):
        return "video"
    if lower.startswith("skill-"):
        return "skill"
    if lower.startswith(("portrait-", "portriat-", "l2d_static-")) or "stand" in lower:
        return "portrait"
    if "psychube" in lower or "equip" in lower:
        return "psychube"
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    return "unknown"


def attach_policy_for(asset_type: str) -> str:
    if asset_type in {"skill", "portrait", "psychube", "image"}:
        return "auto"
    if asset_type in {"voice", "video"}:
        return "on_intent"
    return "manual"


def panel_group_for(asset_type: str, filename: str, child_id: str) -> str:
    if asset_type == "voice":
        lower = filename.lower()
        if "skin:" in child_id:
            return "voice:skin:" + child_id.split("skin:", 1)[1].split(":", 1)[0]
        if "skin_" in lower:
            return "voice:skin:" + lower.split("skin_", 1)[1].split("_", 1)[0]
        return "voice:default"
    if asset_type == "video":
        return "video"
    return ""


def canonical_asset_key(child_id: str, asset_type: str, filename: str) -> tuple[str, str, str]:
    stem = Path(filename).stem.lower()
    stem = re.sub(r"[\s_-]+", " ", stem).strip()
    return child_id, asset_type, stem


def preferred_format_score(filename: str) -> int:
    return FORMAT_PRIORITY.get(Path(filename).suffix.lower(), 0)


def media_id_for_sha1(sha1: str) -> str:
    if not isinstance(sha1, str) or not re.fullmatch(r"[0-9A-Fa-f]{40}", sha1):
        raise ValueError("sha1 must be a 40-character hexadecimal SHA-1")
    return f"media:sha1:{sha1.lower()}"


def build_media_object_key(
    prefix: str, asset_type: str, sha1: str, filename: str
) -> str:
    """Build the canonical content-addressed MinIO key for one media file."""
    if not isinstance(sha1, str) or not re.fullmatch(r"[0-9a-f]{40}", sha1):
        raise ValueError("sha1 must be a lowercase 40-character SHA-1")
    suffix = Path(filename).suffix.lower() or ".bin"
    safe_prefix = _safe_object_component(prefix, "object prefix", allow_slash=True)
    safe_type = _safe_object_component(asset_type, "asset type")
    if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
        raise ValueError("filename has an unsafe media suffix")
    return f"{safe_prefix}/{safe_type}/{sha1[:2]}/{sha1}{suffix}"


def build_public_media_url(base_url: str, bucket_name: str, object_key: str) -> str:
    """Build a browser-safe HTTP(S) URL without exposing a local path."""
    normalized_base = _validated_public_base_url(base_url)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}", bucket_name):
        raise ValueError("bucket_name is unsafe")
    safe_key = _safe_object_component(object_key, "object key", allow_slash=True)
    return (
        f"{normalized_base}/{quote(bucket_name, safe='')}/"
        f"{quote(safe_key, safe='/')}"
    )


def _safe_object_component(value: str, field: str, *, allow_slash: bool = False) -> str:
    text = str(value or "").strip("/")
    if (
        not text
        or "\\" in text
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        raise ValueError(f"{field} is unsafe")
    parts = text.split("/")
    if not allow_slash and len(parts) != 1:
        raise ValueError(f"{field} must be one path component")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{field} contains an unsafe path segment")
    return text


def _validated_public_base_url(value: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
        _port = parsed.port
        hostname = parsed.hostname
    except ValueError as error:
        raise ValueError("public_base_url must be a safe HTTP(S) URL") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not hostname
        or "\\" in text
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError("public_base_url must be a safe HTTP(S) URL")
    if hostname != "localhost":
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            labels = hostname.split(".")
            if any(
                not label
                or len(label) > 63
                or not re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label
                )
                for label in labels
            ):
                raise ValueError("public_base_url has an invalid hostname")
    return urlunsplit(
        (parsed.scheme, parsed.netloc, quote(parsed.path, safe="/%").rstrip("/"), "", "")
    )


# Compatibility aliases for the legacy resolver below. New build code uses the
# public names so object identity is not duplicated across modules.
_object_key = build_media_object_key
_public_url = build_public_media_url


def _content_hash(parts: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _matches_terms(filename: str, terms: Iterable[str]) -> bool:
    lower = filename.lower()
    return any(term and term.lower() in lower for term in terms)


def resolve_media_assets(
    cfg: Any,
    raw_root: str | Path,
    resources: Iterable[dict[str, Any]],
    entity_id: str,
    entity_name: str,
    aliases: Iterable[str],
    parent_id: str,
    child_id: str,
    filename_terms: Iterable[str],
) -> list[dict[str, Any]]:
    raw_path = Path(raw_root)
    assets: dict[tuple[str, str, str], MediaAsset] = {}
    terms = set(str(term) for term in filename_terms)
    terms.update(str(alias) for alias in aliases)
    terms.add(str(entity_name))
    for resource in resources:
        filename = str(resource.get("filename") or resource.get("name") or "")
        if not filename or not _matches_terms(filename, terms):
            continue
        sha1 = str(resource.get("sha1") or hashlib.sha1(filename.encode("utf-8")).hexdigest())
        local_relpath = str(resource.get("local_relpath") or filename)
        asset_type = classify_asset_type(filename)
        object_key = _object_key(getattr(cfg.assets, "object_prefix", "reverse1999"), asset_type, sha1, filename)
        media = MediaAsset(
            media_id=str(resource.get("media_id") or media_id_for_sha1(sha1)),
            entity_id=entity_id,
            entity_name=entity_name,
            parent_id=parent_id,
            child_id=child_id,
            asset_type=asset_type,
            mime=str(resource.get("mime") or mimetypes.guess_type(filename)[0] or ""),
            filename=filename,
            title=str(resource.get("title") or Path(filename).stem),
            source_url=str(resource.get("source_url") or resource.get("url") or ""),
            url=_public_url(getattr(cfg.assets, "public_base_url", ""), getattr(cfg.assets, "bucket_name", ""), object_key),
            object_key=object_key,
            is_available=bool((raw_path / local_relpath).exists() or resource.get("is_available", False)),
            is_common=asset_type == "common",
            attach_policy=attach_policy_for(asset_type),
            search_text=re.sub(r"\s+", " ", " ".join([entity_name, filename, str(resource.get("title") or "")])).strip(),
            content_hash=_content_hash([entity_id, parent_id, child_id, filename, sha1]),
            panel_group=panel_group_for(asset_type, filename, child_id),
            sort_order=int(resource.get("sort_order") or len(assets)),
            duration_ms=int(resource.get("duration_ms") or 0),
            quality_flags=tuple(resource.get("quality_flags") or ()),
        )
        key = canonical_asset_key(media.child_id, media.asset_type, media.filename)
        existing = assets.get(key)
        if existing is None or preferred_format_score(media.filename) > preferred_format_score(existing.filename):
            assets[key] = media
    return [asset.to_json() for asset in sorted(assets.values(), key=lambda item: item.sort_order)]
