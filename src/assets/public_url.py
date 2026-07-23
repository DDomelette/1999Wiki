"""Project browser-facing media URLs from stable object storage keys."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit


_MAX_DECODE_ROUNDS = 32


def _decoded_layers(value: str) -> tuple[str, ...]:
    layers = [value]
    current = value
    for _ in range(_MAX_DECODE_ROUNDS):
        decoded = unquote(current)
        if decoded == current:
            return tuple(layers)
        layers.append(decoded)
        current = decoded
    raise ValueError("value has excessive percent-encoding")


def _validate_component(value: str, *, label: str) -> str:
    candidate = str(value).strip()
    if not candidate:
        raise ValueError(f"{label} must not be empty")
    for decoded in _decoded_layers(candidate):
        if "\\" in decoded or any(ord(char) < 32 for char in decoded):
            raise ValueError(f"{label} contains unsafe characters")
        if any(segment in {".", ".."} for segment in decoded.split("/")):
            raise ValueError(f"{label} contains traversal segments")
    return candidate


def normalize_public_media_base(value: str) -> str:
    candidate = _validate_component(value, label="MEDIA_PUBLIC_BASE_URL")
    if candidate.startswith("//"):
        raise ValueError(
            "MEDIA_PUBLIC_BASE_URL must be a same-origin path or HTTP(S) URL"
        )
    try:
        parsed = urlsplit(candidate)
        _port = parsed.port
    except ValueError as error:
        raise ValueError(
            "MEDIA_PUBLIC_BASE_URL must be a safe path or HTTP(S) URL"
        ) from error
    if parsed.query or parsed.fragment:
        raise ValueError("MEDIA_PUBLIC_BASE_URL must not contain query or fragment")
    for decoded_path in _decoded_layers(parsed.path):
        if "\\" in decoded_path or any(ord(char) < 32 for char in decoded_path):
            raise ValueError("MEDIA_PUBLIC_BASE_URL contains unsafe characters")
        if any(segment in {".", ".."} for segment in decoded_path.split("/")):
            raise ValueError("MEDIA_PUBLIC_BASE_URL must not contain traversal segments")
        if decoded_path.startswith("//"):
            raise ValueError(
                "MEDIA_PUBLIC_BASE_URL must be a same-origin path or HTTP(S) URL"
            )
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("MEDIA_PUBLIC_BASE_URL must use HTTP or HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("MEDIA_PUBLIC_BASE_URL must not contain credentials")
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
        )
    if parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise ValueError(
            "MEDIA_PUBLIC_BASE_URL must be a same-origin path or HTTP(S) URL"
        )
    return parsed.path.rstrip("/") or "/"


def build_public_media_url(
    base_url: str,
    bucket_name: str,
    object_key: str,
) -> str:
    base = normalize_public_media_base(base_url)
    bucket = _validate_component(bucket_name, label="MINIO_BUCKET")
    key = _validate_component(object_key, label="object_key")
    for decoded_bucket in _decoded_layers(bucket):
        if "/" in decoded_bucket or "?" in decoded_bucket or "#" in decoded_bucket:
            raise ValueError("MINIO_BUCKET must be a safe single component")
    for decoded_key in _decoded_layers(key):
        if decoded_key.startswith("/") or "?" in decoded_key or "#" in decoded_key:
            raise ValueError("object_key must be a safe relative object key")
    suffix = f"{quote(bucket, safe='-._~')}/{quote(key, safe='/-._~')}"
    return f"{base.rstrip('/')}/{suffix}"


def is_safe_public_media_url(value: str) -> bool:
    try:
        candidate = str(value)
        if not candidate or candidate != candidate.strip():
            return False
        parsed = urlsplit(candidate)
        _port = parsed.port
        if parsed.query or parsed.fragment:
            return False
        if parsed.scheme:
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
            ):
                return False
        elif (
            parsed.netloc
            or not parsed.path.startswith("/")
            or parsed.path.startswith("//")
        ):
            return False
        for decoded_path in _decoded_layers(parsed.path):
            if "\\" in decoded_path or any(ord(char) < 32 for char in decoded_path):
                return False
            if any(segment in {".", ".."} for segment in decoded_path.split("/")):
                return False
            if not parsed.scheme and decoded_path.startswith("//"):
                return False
        return True
    except (TypeError, ValueError):
        return False


def project_media_row(
    row: Mapping[str, Any],
    *,
    base_url: str,
    bucket_name: str,
) -> dict[str, Any] | None:
    object_key = str(row.get("object_key") or "").strip()
    if not object_key:
        return None
    try:
        public_url = build_public_media_url(base_url, bucket_name, object_key)
    except ValueError:
        return None
    projected = dict(row)
    projected["url"] = public_url
    return projected
