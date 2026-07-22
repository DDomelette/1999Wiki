"""Strict shared contract for the canonical Huiji active-build pointer."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


ACTIVE_POINTER_SCHEMA_VERSION = "evb.active-build/v1"
ACTIVE_POINTER_FIELDS = frozenset(
    {
        "schema_version",
        "generation",
        "build_version",
        "previous_build_version",
        "build_manifest_sha256",
        "milvus_collection_name",
        "collection_schema_fingerprint",
        "collection_manifest_sha256",
        "embedding_model_id",
        "embedding_config_fingerprint",
        "artifact_schema_version",
        "deployment_inventory_sha256",
        "activation_epoch",
        "activation_id",
        "activated_at_utc",
    }
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_BUILD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_COLLECTION_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}\Z")
_RFC3339_UTC_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)
_CAPABILITIES = {
    "evb.media-asset/v1_legacy",
    "evb.media-asset/v2",
    "evb.media-asset/v3",
}
_GENERATION_ZERO = {
    "build_version": "dev",
    "previous_build_version": None,
    "build_manifest_sha256": "ad886077e2aff90350480c9925686693121af9c643796131c361fde6efeed231",
    "milvus_collection_name": "text_child_bge_m3_v3",
    "collection_schema_fingerprint": "db9e13b98d7a1cf4116ba6647a16eb0e7daff0a77c558f66c9db2597038a6bc4",
    "embedding_model_id": "BAAI/bge-m3",
    "embedding_config_fingerprint": "17787be97e63ea53e3298748adf546ebc17d5456669481349eb8bb088b336099",
    "artifact_schema_version": "evb.media-asset/v1_legacy",
}


def canonical_json_bytes(value: object, *, trailing_newline: bool = True) -> bytes:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return encoded + (b"\n" if trailing_newline else b"")


def validate_active_pointer(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("active pointer must be an object")
    value = dict(payload)
    if frozenset(value) != ACTIVE_POINTER_FIELDS:
        raise ValueError("active pointer field set is invalid")
    if value["schema_version"] != ACTIVE_POINTER_SCHEMA_VERSION:
        raise ValueError("active pointer schema is unsupported")
    for field in ("generation", "activation_epoch"):
        if type(value[field]) is not int or value[field] < 0:
            raise ValueError(f"active pointer {field} is invalid")
    if value["generation"] != value["activation_epoch"]:
        raise ValueError("active pointer generation and epoch differ")
    if not _BUILD_RE.fullmatch(str(value["build_version"])):
        raise ValueError("active pointer build version is invalid")
    previous = value["previous_build_version"]
    if previous is not None and not _BUILD_RE.fullmatch(str(previous)):
        raise ValueError("active pointer previous build version is invalid")
    if not _COLLECTION_RE.fullmatch(str(value["milvus_collection_name"])):
        raise ValueError("active pointer collection is invalid")
    if not str(value["embedding_model_id"]).strip():
        raise ValueError("active pointer embedding model is invalid")
    if value["artifact_schema_version"] not in _CAPABILITIES:
        raise ValueError("active pointer artifact schema is unsupported")
    if not _ID_RE.fullmatch(str(value["activation_id"])):
        raise ValueError("active pointer activation ID is invalid")
    for field in (
        "build_manifest_sha256",
        "collection_schema_fingerprint",
        "collection_manifest_sha256",
        "embedding_config_fingerprint",
        "deployment_inventory_sha256",
    ):
        if not _SHA256_RE.fullmatch(str(value[field])):
            raise ValueError(f"active pointer {field} is invalid")
    timestamp = str(value["activated_at_utc"])
    if not _RFC3339_UTC_RE.fullmatch(timestamp):
        raise ValueError("active pointer activation time is invalid")
    try:
        datetime.fromisoformat(timestamp.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError("active pointer activation time is invalid") from error

    if value["generation"] == 0:
        for field, expected in _GENERATION_ZERO.items():
            if value[field] != expected:
                raise ValueError(f"generation-zero pointer {field} mismatch")
    elif previous is None:
        raise ValueError("nonzero pointer lacks previous build version")
    return value


def load_active_pointer(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise ValueError("active pointer is missing")
    raw = target.read_bytes()

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in values:
            if key in result:
                raise ValueError(f"active pointer has duplicate key: {key}")
            result[key] = item
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("active pointer is invalid JSON") from error
    validated = validate_active_pointer(payload)
    if raw != canonical_json_bytes(validated):
        raise ValueError("active pointer bytes are not canonical")
    return validated


def canonical_pointer_path(processed_root: str | Path) -> Path:
    raw_root = Path(processed_root)
    if raw_root.is_symlink():
        raise ValueError("active pointer containment violation")
    root = raw_root.resolve()
    target = root / "active_build.v1.json"
    if target.parent != root:
        raise ValueError("active pointer containment violation")
    return target


def resolve_generation_zero_evidence(
    processed_root: str | Path,
    pointer: Mapping[str, Any],
) -> tuple[Path, Path]:
    value = validate_active_pointer(pointer)
    if value["generation"] != 0:
        raise ValueError("pointer is not generation zero")
    root = Path(processed_root).resolve()
    evidence_root = (
        root / "activation" / "bootstrap" / str(value["activation_id"])
    ).resolve()
    if root not in evidence_root.parents:
        raise ValueError("generation-zero evidence containment violation")
    return (
        evidence_root / "collection_manifest.v1.json",
        evidence_root / "deployment_inventory.v1.json",
    )


def resolve_activation_evidence(
    processed_root: str | Path,
    pointer: Mapping[str, Any],
) -> tuple[Path, Path]:
    """Resolve nonzero activation evidence from the pointer-owned transaction."""
    value = validate_active_pointer(pointer)
    if value["generation"] <= 0:
        raise ValueError("pointer is not an activated generation")
    root = Path(processed_root).resolve()
    evidence_root = (
        root / "activation" / "transactions" / str(value["activation_id"])
    ).resolve()
    if root not in evidence_root.parents:
        raise ValueError("activation evidence containment violation")
    return (
        evidence_root / "collection_manifest.v1.json",
        evidence_root / "deployment_inventory.v1.json",
    )


__all__ = [
    "ACTIVE_POINTER_FIELDS",
    "ACTIVE_POINTER_SCHEMA_VERSION",
    "canonical_json_bytes",
    "canonical_pointer_path",
    "load_active_pointer",
    "resolve_activation_evidence",
    "resolve_generation_zero_evidence",
    "validate_active_pointer",
]
