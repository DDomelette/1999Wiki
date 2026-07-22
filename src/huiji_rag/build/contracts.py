"""Frozen contracts shared by the crawler corpus builder and Wiki consumers."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from src.huiji_rag.active_pointer import ACTIVE_POINTER_SCHEMA_VERSION


MEDIA_V3_ROW_SCHEMA_VERSION = "evb.media-asset/v3"
MEDIA_V3_SCHEMA_VERSION = "evb.media-assets/v3"
MEDIA_V3_MANIFEST_SCHEMA_VERSION = "evb.media-artifact-manifest/v3"
CORPUS_BUILD_SCHEMA_VERSION = "huiji.corpus-build/v2"
PARENT_BLOCK_SCHEMA_VERSION = "huiji.parent-blocks/v2"
CHILD_BLOCK_SCHEMA_VERSION = "huiji.child-blocks/v2"

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

FIXTURE_FILENAMES = (
    "media_assets.v3.schema.json",
    "media_assets.v3.jsonl",
    "expected_resources.json",
    "expected_bindings.json",
)

CRAWLER_SOURCE_FILENAMES = (
    "pages.jsonl",
    "wikitext.jsonl",
    "data_pages.jsonl",
    "resources_manifest.jsonl",
)


class BuildState(str, Enum):
    BLOCKED = "blocked"
    DIAGNOSTIC_ONLY = "diagnostic_only"
    READY_FOR_EMBEDDING = "ready_for_embedding"


@dataclass(frozen=True)
class SourceFileEvidence:
    relative_path: str
    sha256: str
    size: int
    row_count: int
    identity_sha256: str

    def to_json(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size": self.size,
            "row_count": self.row_count,
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True)
class CorpusSourceInventory:
    files: tuple[SourceFileEvidence, ...]
    source_inventory_sha256: str
    schema_version: str = "huiji.crawler-source-inventory/v1"

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "files": [item.to_json() for item in self.files],
            "source_inventory_sha256": self.source_inventory_sha256,
        }


@dataclass(frozen=True)
class CorpusBuildRequest:
    build_version: str
    raw_root: Path
    processed_root: Path
    run_dir: Path
    fidelity_baseline_path: Path
    expected_fidelity_baseline_sha256: str
    wiki_compatibility_receipt_path: Path | None = None
    expected_wiki_compatibility_receipt_sha256: str = ""
    configured_build_version: str = ""
    active_pointer_path: Path | None = None
    requested_source_filenames: tuple[str, ...] = CRAWLER_SOURCE_FILENAMES
    project_root: Path | None = None
    minio_inventory_path: Path | None = None
    expected_minio_inventory_sha256: str = ""
    public_base_url: str = ""
    bucket_name: str = ""
    object_prefix: str = "reverse1999"
    embedding_provider: str = ""
    embedding_model: str = ""
    forbidden_collection_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "requested_source_filenames", tuple(self.requested_source_filenames)
        )
        object.__setattr__(
            self,
            "forbidden_collection_names",
            tuple(sorted(set(self.forbidden_collection_names))),
        )


@dataclass(frozen=True)
class CorpusBuildResult:
    build_version: str
    build_root: Path
    state: BuildState
    build_manifest: Path | None = None
    build_report: Path | None = None
    blockers: tuple[str, ...] = ()
    row_counts: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, BuildState):
            raise ValueError("corpus build state must use the frozen BuildState enum")
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(self, "row_counts", MappingProxyType(dict(self.row_counts or {})))


@dataclass(frozen=True)
class VoiceBindingInput:
    source_rows: tuple[Any, ...]
    resource_rows: tuple[Any, ...]


@dataclass(frozen=True)
class VoiceBindingResult:
    binding_rows: tuple[Any, ...]
    exact_bindings: tuple[Any, ...]
    quarantined_bindings: tuple[Any, ...]
    shortfall_bindings: tuple[Any, ...]
    fatal_bindings: tuple[Any, ...]
    conflict_result: Any
    conflict_closure: Any
    status_by_source: Mapping[str, str]
    quality_flags_by_source: Mapping[str, tuple[str, ...]]
    root_causes_by_source: Mapping[str, tuple[str, ...]]
    source_input_fingerprint_sha256: str
    resource_input_fingerprint_sha256: str
    input_fingerprint_sha256: str
    output_fingerprint_sha256: str
    binding_fingerprint_sha256: str
    status_counts: Mapping[str, int]
    counts_by_language: Mapping[str, int]
    counts_by_event: Mapping[str, int]
    counts_by_owner: Mapping[str, int]
    event_count: int
    language_count: int
    owner_count: int
    skin_count: int
    ready_gate_blocked: bool

    def __post_init__(self) -> None:
        for field_name in (
            "binding_rows",
            "exact_bindings",
            "quarantined_bindings",
            "shortfall_bindings",
            "fatal_bindings",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for field_name in (
            "status_by_source",
            "quality_flags_by_source",
            "root_causes_by_source",
            "status_counts",
            "counts_by_language",
            "counts_by_event",
            "counts_by_owner",
        ):
            values = dict(getattr(self, field_name))
            if field_name in {"quality_flags_by_source", "root_causes_by_source"}:
                values = {key: tuple(value) for key, value in values.items()}
            object.__setattr__(self, field_name, MappingProxyType(values))

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_ID_RE = re.compile(r"^resource:sha256:[0-9a-f]{64}$")
_MEDIA_ID_RE = re.compile(r"^media:sha1:[0-9a-f]{40}$")
_BINDING_ID_RE = re.compile(r"^binding:sha256:[0-9a-f]{64}$")
_SOURCE_REF_REQUIRED_FIELDS = (
    "source_kind",
    "source_title",
    "source_row_id",
    "source_content_sha256",
)

_RESOURCE_PROJECTION_FIELDS = (
    "resource_id",
    "media_id",
    "asset_type",
    "mime",
    "filename",
    "source_url",
    "url",
    "object_key",
    "is_available",
    "is_common",
    "content_hash",
    "quality_flags",
    "sha1",
    "source_sha1",
    "content_sha256",
    "size",
    "duration_ms",
    "width",
    "height",
)

_BINDING_PROJECTION_FIELDS = (
    "binding_id",
    "resource_id",
    "page_id",
    "entity_id",
    "entity_name",
    "owner_entity_id",
    "owner_page_id",
    "parent_id",
    "child_id",
    "section_key",
    "media_role",
    "variant",
    "skin_id",
    "event_name",
    "language",
    "source_binding_token",
    "source_refs",
    "title",
    "attach_policy",
    "search_text",
    "panel_group",
    "sort_order",
    "binding_status",
)


def canonical_json_bytes(value: object, *, trailing_newline: bool = True) -> bytes:
    """Encode deterministic UTF-8 JSON without accepting non-finite numbers."""
    _reject_non_finite(value)
    suffix = "\n" if trailing_newline else ""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + suffix
    ).encode("utf-8")


def canonical_jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    """Encode media rows in frozen field order, one canonical object per line."""
    encoded: list[bytes] = []
    for row in rows:
        validated = validate_media_v3_row(dict(row))
        encoded.append(
            (
                json.dumps(validated, ensure_ascii=False, separators=(",", ":")) + "\n"
            ).encode("utf-8")
        )
    return b"".join(encoded)


def compute_resource_id(content_sha256: str) -> str:
    value = _require_hash(content_sha256, _SHA256_RE, "content_sha256")
    return f"resource:sha256:{value}"


def compute_media_id(sha1: str) -> str:
    value = _require_hash(sha1, _SHA1_RE, "sha1")
    return f"media:sha1:{value}"


def binding_identity(row: Mapping[str, Any]) -> list[str]:
    required = (
        "owner_entity_id",
        "owner_page_id",
        "parent_id",
        "child_id",
        "section",
        "media_role",
        "source_binding_token",
        "resource_id",
    )
    missing = [name for name in required if not str(row.get(name) or "")]
    if missing:
        raise ValueError(f"media binding identity fields are empty: {missing}")
    identity = [
        "evb.media-binding/v1",
        str(row["owner_entity_id"]),
        str(row["owner_page_id"]),
        str(row["parent_id"]),
        str(row["child_id"]),
        str(row["section"]),
        str(row["media_role"]),
        str(row.get("variant") or ""),
        str(row.get("skin_id") or ""),
        str(row.get("event_name") or ""),
        str(row.get("language") or ""),
        str(row["source_binding_token"]),
        str(row["resource_id"]),
    ]
    return identity


def compute_binding_id(row: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(binding_identity(row), trailing_newline=False)
    return "binding:sha256:" + hashlib.sha256(payload).hexdigest()


def ordered_media_v3_row(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return one row in the frozen order after deriving compatibility IDs."""
    row = dict(values)
    content_sha256 = str(row.get("content_sha256") or "").lower()
    sha1 = str(row.get("sha1") or "").lower()
    row["artifact_schema_version"] = MEDIA_V3_ROW_SCHEMA_VERSION
    row["content_sha256"] = content_sha256
    row["content_hash"] = content_sha256
    row["sha1"] = sha1
    row["source_sha1"] = str(row.get("source_sha1") or sha1).lower()
    row["resource_id"] = compute_resource_id(content_sha256)
    row["media_id"] = compute_media_id(sha1)
    row["binding_id"] = compute_binding_id(row)
    try:
        ordered = {name: row[name] for name in MEDIA_V3_FIELD_ORDER}
    except KeyError as error:
        raise ValueError(f"media v3 field missing: {error.args[0]}") from error
    return validate_media_v3_row(ordered)


def validate_media_v3_row(row: dict[str, Any]) -> dict[str, Any]:
    if "local_relpath" in row:
        raise ValueError("media v3 runtime row must not contain local_relpath")
    expected = set(MEDIA_V3_FIELD_ORDER)
    actual = set(row)
    if actual != expected:
        raise ValueError(
            f"media v3 fields differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    if tuple(row) != MEDIA_V3_FIELD_ORDER:
        raise ValueError("media v3 field order does not match the frozen contract")
    if row["artifact_schema_version"] != MEDIA_V3_ROW_SCHEMA_VERSION:
        raise ValueError("invalid media v3 row schema")

    non_string = {
        "source_refs",
        "is_available",
        "is_common",
        "sort_order",
        "duration_ms",
        "width",
        "height",
        "quality_flags",
        "size",
    }
    for field in (name for name in MEDIA_V3_FIELD_ORDER if name not in non_string):
        if not isinstance(row[field], str):
            raise ValueError(f"media v3 {field} must be a string")
    for field in (
        "owner_entity_id",
        "owner_page_id",
        "parent_id",
        "child_id",
        "section",
        "media_role",
        "source_binding_token",
    ):
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
    _require_hash(row["sha1"], _SHA1_RE, "sha1")
    _require_hash(row["source_sha1"], _SHA1_RE, "source_sha1")
    _require_hash(row["content_sha256"], _SHA256_RE, "content_sha256")
    if row["content_hash"] != row["content_sha256"]:
        raise ValueError("media v3 content_hash must equal content_sha256")
    if not _RESOURCE_ID_RE.fullmatch(row["resource_id"]):
        raise ValueError("invalid media v3 resource_id")
    if not _MEDIA_ID_RE.fullmatch(row["media_id"]):
        raise ValueError("invalid media v3 media_id")
    if not _BINDING_ID_RE.fullmatch(row["binding_id"]):
        raise ValueError("invalid media v3 binding_id")
    if row["resource_id"] != compute_resource_id(row["content_sha256"]):
        raise ValueError("media v3 resource_id does not match content_sha256")
    if row["media_id"] != compute_media_id(row["sha1"]):
        raise ValueError("media v3 media_id does not match sha1")
    if row["binding_id"] != compute_binding_id(row):
        raise ValueError("media v3 binding_id does not match the frozen identity")
    if row["binding_status"] not in {"exact", "not_applicable"}:
        raise ValueError("invalid media v3 binding_status")

    flags = row["quality_flags"]
    if (
        not isinstance(flags, list)
        or any(not isinstance(item, str) for item in flags)
        or flags != sorted(set(flags))
    ):
        raise ValueError("media v3 quality_flags must be sorted and unique")
    refs = row["source_refs"]
    if not isinstance(refs, list) or not refs:
        raise ValueError("media v3 source_refs must be a non-empty array")
    for ref in refs:
        if not isinstance(ref, dict) or not set(_SOURCE_REF_REQUIRED_FIELDS).issubset(ref):
            raise ValueError("media v3 source_refs entry is incomplete")
        _require_hash(
            str(ref.get("source_content_sha256") or ""),
            _SHA256_RE,
            "source_content_sha256",
        )
    return row


def normalize_media_v3_rows(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project the binding stream without collapsing relationship identities."""
    resources: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, Any]] = {}
    for candidate in rows:
        row = validate_media_v3_row(dict(candidate))
        resource = {field: row[field] for field in _RESOURCE_PROJECTION_FIELDS}
        previous = resources.get(row["resource_id"])
        if previous is not None and previous != resource:
            raise ValueError(f"conflicting resource payload: {row['resource_id']}")
        resources[row["resource_id"]] = resource

        binding_values = {
            "binding_id": row["binding_id"],
            "resource_id": row["resource_id"],
            "page_id": row["owner_page_id"],
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
            "source_refs": row["source_refs"],
            "title": row["title"],
            "attach_policy": row["attach_policy"],
            "search_text": row["search_text"],
            "panel_group": row["panel_group"],
            "sort_order": row["sort_order"],
            "binding_status": row["binding_status"],
        }
        binding = {field: binding_values[field] for field in _BINDING_PROJECTION_FIELDS}
        if row["binding_id"] in bindings:
            raise ValueError(f"duplicate media binding: {row['binding_id']}")
        bindings[row["binding_id"]] = binding
    return (
        [resources[key] for key in sorted(resources)],
        [bindings[key] for key in sorted(bindings)],
    )


def media_v3_schema_document() -> dict[str, Any]:
    string = {"type": "string"}
    properties: dict[str, Any] = {name: dict(string) for name in MEDIA_V3_FIELD_ORDER}
    properties.update(
        {
            "artifact_schema_version": {
                "type": "string",
                "const": MEDIA_V3_ROW_SCHEMA_VERSION,
            },
            "binding_id": {"type": "string", "pattern": _BINDING_ID_RE.pattern},
            "resource_id": {"type": "string", "pattern": _RESOURCE_ID_RE.pattern},
            "media_id": {
                "type": "string",
                "pattern": _MEDIA_ID_RE.pattern,
                "deprecated": True,
            },
            "source_refs": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": list(_SOURCE_REF_REQUIRED_FIELDS),
                    "properties": {
                        **{name: {"type": "string"} for name in _SOURCE_REF_REQUIRED_FIELDS},
                        "revision_id": {"type": ["string", "integer"]},
                    },
                    "additionalProperties": True,
                },
            },
            "is_available": {"type": "boolean"},
            "is_common": {"type": "boolean"},
            "sort_order": {"type": "integer", "minimum": 0},
            "duration_ms": {"type": "integer", "minimum": 0},
            "width": {"type": "integer", "minimum": 0},
            "height": {"type": "integer", "minimum": 0},
            "quality_flags": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "sha1": {"type": "string", "pattern": _SHA1_RE.pattern},
            "source_sha1": {"type": "string", "pattern": _SHA1_RE.pattern},
            "content_sha256": {"type": "string", "pattern": _SHA256_RE.pattern},
            "content_hash": {"type": "string", "pattern": _SHA256_RE.pattern},
            "size": {"type": "integer", "minimum": 0},
            "binding_status": {"type": "string", "enum": ["exact", "not_applicable"]},
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": MEDIA_V3_SCHEMA_VERSION,
        "row_schema_version": MEDIA_V3_ROW_SCHEMA_VERSION,
        "manifest_schema_version": MEDIA_V3_MANIFEST_SCHEMA_VERSION,
        "type": "object",
        "required": list(MEDIA_V3_FIELD_ORDER),
        "properties": properties,
        "additionalProperties": False,
        "x-field-order": list(MEDIA_V3_FIELD_ORDER),
    }


def fixture_contract_fingerprint(fixture_root: Path) -> dict[str, Any]:
    root = Path(fixture_root).resolve()
    files: list[dict[str, str]] = []
    for filename in FIXTURE_FILENAMES:
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(f"shared media v3 fixture is missing: {path}")
        files.append({"path": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {
        "schema_version": "huiji.media-v3-contract-fingerprint/v1",
        "files": files,
        "contract_sha256": hashlib.sha256(
            canonical_json_bytes(files, trailing_newline=False)
        ).hexdigest(),
    }


def _require_hash(value: str, pattern: re.Pattern[str], field: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"invalid lowercase {field}")
    return value


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _reject_non_finite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical JSON does not permit non-finite numbers")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_non_finite(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_non_finite(item)
