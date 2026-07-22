"""Immutable Huiji build records and EventName Voice Binding evidence types."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence, TypeVar


_Value = TypeVar("_Value")


class BindingStatus(str, Enum):
    EXACT = "exact"
    SHORTFALL = "shortfall"
    QUARANTINED = "quarantined"
    FATAL = "fatal"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ResourceRow:
    """The resource evidence used by exact EventName voice binding."""

    filename: str
    language: str
    sha1: str
    sha256: str
    resource_id: str = ""
    source_id: str = ""
    source_url: str = ""
    title: str = ""
    mime: str = ""
    local_relpath: str = ""
    object_key: str = ""
    quality_flags: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "ResourceRow":
        return cls(
            filename=str(row.get("filename") or row.get("name") or ""),
            language=str(row.get("language") or row.get("lang") or ""),
            sha1=str(row.get("sha1") or ""),
            sha256=str(row.get("sha256") or ""),
            resource_id=str(row.get("resource_id") or row.get("id") or ""),
            source_id=str(row.get("source_id") or row.get("source") or ""),
            source_url=str(row.get("source_url") or row.get("url") or ""),
            title=str(row.get("title") or ""),
            mime=str(row.get("mime") or ""),
            local_relpath=str(row.get("local_relpath") or ""),
            object_key=str(row.get("object_key") or ""),
            quality_flags=_tuple_of_str(row.get("quality_flags", ())),
        )


@dataclass(frozen=True)
class VoiceSourceRow:
    """The authoritative EventName and language for one source voice row."""

    event_name: str
    language: str
    source_id: str = ""
    entity_id: str = ""
    parent_id: str = ""
    child_id: str = ""
    skin_id: str = ""
    audio_id: str = ""
    title: str = ""
    source_url: str = ""
    transcript: str = ""
    quality_flags: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "VoiceSourceRow":
        return cls(
            event_name=str(row.get("event_name") or row.get("eventName") or ""),
            language=str(row.get("language") or row.get("lang") or ""),
            source_id=str(row.get("source_id") or row.get("id") or ""),
            entity_id=str(row.get("entity_id") or ""),
            parent_id=str(row.get("parent_id") or ""),
            child_id=str(row.get("child_id") or ""),
            skin_id=str(row.get("skin_id") or row.get("skinId") or ""),
            audio_id=str(row.get("audio_id") or row.get("audioId") or ""),
            title=str(row.get("title") or ""),
            source_url=str(row.get("source_url") or row.get("url") or ""),
            transcript=str(row.get("transcript") or row.get("text") or ""),
            quality_flags=_tuple_of_str(row.get("quality_flags", ())),
        )


@dataclass(frozen=True)
class BindingRecord:
    """Exact-match decision with source and resource evidence retained."""

    source: VoiceSourceRow
    expected_filename: str
    matches: tuple[ResourceRow, ...]
    status: BindingStatus
    binding_status: BindingStatus
    source_id: str
    entity_id: str
    parent_id: str
    child_id: str
    skin_id: str
    audio_id: str
    event_name: str
    language: str
    transcript: str
    resource_ids: tuple[str, ...]
    resource_source_ids: tuple[str, ...]
    resource_filenames: tuple[str, ...]
    source_sha1: tuple[str, ...]
    content_sha256: tuple[str, ...]
    object_key: tuple[str, ...]
    local_relpath: tuple[str, ...]
    text_sha256: str
    quality_flags: tuple[str, ...]
    evidence_ids: tuple[str, ...]

    @classmethod
    def from_match(
        cls,
        source: VoiceSourceRow,
        expected_filename: str,
        matches: Sequence[ResourceRow],
        status: BindingStatus,
    ) -> "BindingRecord":
        resources = tuple(matches)
        quality_flags = tuple(
            dict.fromkeys(
                (*source.quality_flags, *(flag for resource in resources for flag in resource.quality_flags))
            )
        )
        resource_ids = tuple(resource.resource_id for resource in resources)
        evidence_ids = tuple(
            value for value in (source.source_id, *resource_ids) if value
        )
        return cls(
            source=source,
            expected_filename=expected_filename,
            matches=resources,
            status=BindingStatus(status),
            binding_status=BindingStatus(status),
            source_id=source.source_id,
            entity_id=source.entity_id,
            parent_id=source.parent_id,
            child_id=source.child_id,
            skin_id=source.skin_id,
            audio_id=source.audio_id,
            event_name=source.event_name,
            language=source.language,
            transcript=source.transcript,
            resource_ids=resource_ids,
            resource_source_ids=tuple(resource.source_id for resource in resources),
            resource_filenames=tuple(resource.filename for resource in resources),
            source_sha1=tuple(resource.sha1 for resource in resources),
            content_sha256=tuple(resource.sha256 for resource in resources),
            object_key=tuple(resource.object_key for resource in resources),
            local_relpath=tuple(resource.local_relpath for resource in resources),
            text_sha256=_text_sha256(source.transcript),
            quality_flags=quality_flags,
            evidence_ids=evidence_ids,
        )

    def to_json(self) -> dict[str, Any]:
        payload = {
            "source": self.source.to_json(),
            "expected_filename": self.expected_filename,
            "matches": [resource.to_json() for resource in self.matches],
            "status": self.status.value,
        }
        payload.update(
            {
                "binding_status": self.binding_status.value,
                "source_id": self.source_id,
                "entity_id": self.entity_id,
                "parent_id": self.parent_id,
                "child_id": self.child_id,
                "skin_id": self.skin_id,
                "audio_id": self.audio_id,
                "event_name": self.event_name,
                "language": self.language,
                "transcript": self.transcript,
                "resource_ids": list(self.resource_ids),
                "resource_source_ids": list(self.resource_source_ids),
                "resource_filenames": list(self.resource_filenames),
                "source_sha1": list(self.source_sha1),
                "content_sha256": list(self.content_sha256),
                "object_key": list(self.object_key),
                "local_relpath": list(self.local_relpath),
                "text_sha256": self.text_sha256,
                "quality_flags": list(self.quality_flags),
                "evidence_ids": list(self.evidence_ids),
            }
        )
        return payload


@dataclass(frozen=True)
class ConflictResult:
    """Immutable conflict classification used to gate mutation and runtime projection."""

    fatal_ids: tuple[str, ...]
    quarantined_ids: tuple[str, ...]
    shortfall_ids: tuple[str, ...]
    exact_ids: tuple[str, ...]
    runtime_ids: tuple[str, ...]
    stop_mutations: bool
    root_causes: Mapping[str, tuple[str, ...]]
    status_by_id: Mapping[str, BindingStatus]
    quality_flags_by_id: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "root_causes",
            _immutable_mapping({key: tuple(value) for key, value in self.root_causes.items()}),
        )
        object.__setattr__(self, "status_by_id", _immutable_mapping(self.status_by_id))
        object.__setattr__(
            self,
            "quality_flags_by_id",
            _immutable_mapping(
                {key: tuple(value) for key, value in self.quality_flags_by_id.items()}
            ),
        )


@dataclass(frozen=True)
class ConflictClosure:
    """The fixed-point read-only conflict neighborhood for one or more bindings."""

    visited_ids: tuple[str, ...]
    round_counts: tuple[int, ...]
    visited_counts: Mapping[str, int]
    closure_sha256: str
    whole_corpus_visited: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "visited_counts", _immutable_mapping(self.visited_counts))

    @property
    def dimension_counts(self) -> Mapping[str, int]:
        """Compatibility name for the visited closure dimension counts."""
        return self.visited_counts


def _text_sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _immutable_mapping(values: Mapping[str, _Value]) -> Mapping[str, _Value]:
    return MappingProxyType(dict(values))


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _tuple_of_dict(value: Any) -> tuple[dict[str, Any], ...]:
    return tuple(dict(item) for item in (value or ()) if isinstance(item, dict))


@dataclass(frozen=True)
class ParentBlock:
    parent_id: str
    entity_id: str
    entity_name: str
    entity_aliases: tuple[str, ...]
    category: str
    section_kind: str
    title: str
    summary_text: str
    source_refs: tuple[dict[str, Any], ...]
    child_ids: tuple[str, ...]
    content_hash: str
    entity_type: str = "character"
    depth_level: int = 1
    ancestor_ids: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    omitted_action_label: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "ParentBlock":
        return cls(
            parent_id=str(row["parent_id"]),
            entity_id=str(row.get("entity_id", "")),
            entity_name=str(row.get("entity_name", "")),
            entity_aliases=_tuple_of_str(row.get("entity_aliases", ())),
            category=str(row.get("category", "")),
            section_kind=str(row.get("section_kind", "")),
            title=str(row.get("title", "")),
            summary_text=str(row.get("summary_text", "")),
            source_refs=_tuple_of_dict(row.get("source_refs", ())),
            child_ids=_tuple_of_str(row.get("child_ids", ())),
            content_hash=str(row.get("content_hash", "")),
            entity_type=str(row.get("entity_type", "character")),
            depth_level=int(row.get("depth_level", 1) or 1),
            ancestor_ids=_tuple_of_str(row.get("ancestor_ids", ())),
            quality_flags=_tuple_of_str(row.get("quality_flags", ())),
            omitted_action_label=str(row.get("omitted_action_label", "")),
        )


@dataclass(frozen=True)
class ChildBlock:
    child_id: str
    parent_id: str
    entity_id: str
    entity_name: str
    category: str
    section_kind: str
    title: str
    text: str
    search_text: str
    chunk_index: int
    media_ids: tuple[str, ...]
    media_policy: str
    source_refs: tuple[dict[str, Any], ...]
    content_hash: str
    entity_type: str = "character"
    depth_level: int = 3
    ancestor_ids: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    route_tags: tuple[str, ...] = ()
    omitted_action_label: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "ChildBlock":
        return cls(
            child_id=str(row["child_id"]),
            parent_id=str(row["parent_id"]),
            entity_id=str(row.get("entity_id", "")),
            entity_name=str(row.get("entity_name", "")),
            category=str(row.get("category", "")),
            section_kind=str(row.get("section_kind", "")),
            title=str(row.get("title", "")),
            text=str(row.get("text", "")),
            search_text=str(row.get("search_text", "")),
            chunk_index=int(row.get("chunk_index", 0) or 0),
            media_ids=_tuple_of_str(row.get("media_ids", ())),
            media_policy=str(row.get("media_policy", "auto")),
            source_refs=_tuple_of_dict(row.get("source_refs", ())),
            content_hash=str(row.get("content_hash", "")),
            entity_type=str(row.get("entity_type", "character")),
            depth_level=int(row.get("depth_level", 3) or 3),
            ancestor_ids=_tuple_of_str(row.get("ancestor_ids", ())),
            quality_flags=_tuple_of_str(row.get("quality_flags", ())),
            route_tags=_tuple_of_str(row.get("route_tags", ())),
            omitted_action_label=str(row.get("omitted_action_label", "")),
        )


@dataclass(frozen=True)
class MediaAsset:
    media_id: str
    sha1: str
    entity_id: str
    entity_name: str
    parent_id: str
    child_id: str
    asset_type: str
    mime: str
    filename: str
    title: str
    source_url: str
    local_relpath: str
    object_key: str
    url: str
    is_available: bool
    is_common: bool
    attach_policy: str
    search_text: str
    content_hash: str
    panel_group: str = ""
    sort_order: int = 0
    duration_ms: int = 0
    quality_flags: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "MediaAsset":
        return cls(
            media_id=str(row["media_id"]),
            sha1=str(row.get("sha1", "")),
            entity_id=str(row.get("entity_id", "")),
            entity_name=str(row.get("entity_name", "")),
            parent_id=str(row.get("parent_id", "")),
            child_id=str(row.get("child_id", "")),
            asset_type=str(row.get("asset_type", "")),
            mime=str(row.get("mime", "")),
            filename=str(row.get("filename", "")),
            title=str(row.get("title", "")),
            source_url=str(row.get("source_url", "")),
            local_relpath=str(row.get("local_relpath", "")),
            object_key=str(row.get("object_key", "")),
            url=str(row.get("url", "")),
            is_available=bool(row.get("is_available", False)),
            is_common=bool(row.get("is_common", False)),
            attach_policy=str(row.get("attach_policy", "manual")),
            search_text=str(row.get("search_text", "")),
            content_hash=str(row.get("content_hash", "")),
            panel_group=str(row.get("panel_group", "")),
            sort_order=int(row.get("sort_order", 0) or 0),
            duration_ms=int(row.get("duration_ms", 0) or 0),
            quality_flags=_tuple_of_str(row.get("quality_flags", ())),
        )


@dataclass(frozen=True)
class SourceInventory:
    source_inventory_sha256: str
    entity_rows: Sequence[dict[str, object]]
    resource_rows: Sequence[dict[str, object]]


@dataclass(frozen=True)
class BaselineEvidence:
    schema_version: str
    source_inventory_sha256: str
    observations: dict[str, int]
    milvus_observation: dict[str, object]


@dataclass(frozen=True)
class BaselineReceipt:
    schema_version: str
    baseline_relative_path: str
    baseline_sha256: str
    baseline_schema_version: str
    source_inventory_sha256: str
    receipt_sha256: str


@dataclass(frozen=True)
class EntityNameDirectory:
    entries: Mapping[str, tuple[str, str]]
    conflicts: Mapping[str, tuple[tuple[str, str], ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", _immutable_mapping(dict(sorted(self.entries.items()))))
        object.__setattr__(
            self,
            "conflicts",
            _immutable_mapping(
                {
                    key: tuple(sorted(tuple(value) for value in values))
                    for key, values in sorted(self.conflicts.items())
                }
            ),
        )


@dataclass(frozen=True)
class EntityNameExclusion:
    source_id: str
    entity_key: str
    cause: str

    def to_json(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MediaArtifacts:
    binding_rows: Sequence[BindingRecord]
    runtime_rows: Sequence[Mapping[str, object]]
    schema: Mapping[str, object]
    manifest_inputs: Mapping[str, object]
    nonvoice_rows: Sequence[Mapping[str, object]]
    entity_name_exclusions: Sequence[EntityNameExclusion] = ()
    parent_rows: Sequence[Mapping[str, object]] = ()
    child_rows: Sequence[Mapping[str, object]] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_rows", tuple(self.binding_rows))
        object.__setattr__(self, "runtime_rows", tuple(dict(row) for row in self.runtime_rows))
        object.__setattr__(self, "schema", _immutable_mapping(self.schema))
        object.__setattr__(self, "manifest_inputs", _immutable_mapping(self.manifest_inputs))
        object.__setattr__(self, "nonvoice_rows", tuple(dict(row) for row in self.nonvoice_rows))
        object.__setattr__(self, "entity_name_exclusions", tuple(self.entity_name_exclusions))
        object.__setattr__(self, "parent_rows", tuple(dict(row) for row in self.parent_rows))
        object.__setattr__(self, "child_rows", tuple(dict(row) for row in self.child_rows))


@dataclass(frozen=True)
class ArtifactManifest:
    schema_version: str
    build_version: str
    file_paths: Mapping[str, str]
    file_sha256: Mapping[str, str]
    row_counts: Mapping[str, int]
    baseline_input_hashes: Mapping[str, str]
    previous_build_evidence: Mapping[str, object]
    runtime_status_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_paths", _immutable_mapping(self.file_paths))
        object.__setattr__(self, "file_sha256", _immutable_mapping(self.file_sha256))
        object.__setattr__(self, "row_counts", _immutable_mapping(self.row_counts))
        object.__setattr__(
            self, "baseline_input_hashes", _immutable_mapping(self.baseline_input_hashes)
        )
        object.__setattr__(
            self, "previous_build_evidence", _immutable_mapping(self.previous_build_evidence)
        )
        object.__setattr__(
            self, "runtime_status_counts", _immutable_mapping(self.runtime_status_counts)
        )

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "build_version": self.build_version,
            "file_paths": dict(self.file_paths),
            "file_sha256": dict(self.file_sha256),
            "row_counts": dict(self.row_counts),
            "baseline_input_hashes": dict(self.baseline_input_hashes),
            "previous_build_evidence": dict(self.previous_build_evidence),
            "runtime_status_counts": dict(self.runtime_status_counts),
        }


@dataclass(frozen=True)
class EvbBuildPaths:
    """All Task 1 build paths, rooted in one isolated build directory."""

    output_root: Path
    build_root: Path
    indexes_root: Path
    runtime_root: Path
    diagnostic_root: Path
    binding_inventory: Path
    media_assets_v2: Path
    media_schema_v2: Path
    media_manifest_v2: Path
    parent_blocks: Path
    child_blocks: Path
    media_assets: Path
    build_manifest: Path
    build_report: Path
    child_bm25: Path
    media_bm25: Path

    def all_paths(self) -> tuple[Path, ...]:
        return (
            self.indexes_root,
            self.runtime_root,
            self.diagnostic_root,
            self.binding_inventory,
            self.media_assets_v2,
            self.media_schema_v2,
            self.media_manifest_v2,
            self.parent_blocks,
            self.child_blocks,
            self.media_assets,
            self.build_manifest,
            self.build_report,
            self.child_bm25,
            self.media_bm25,
        )


@dataclass(frozen=True)
class BuildRequest:
    build_version: str
    baseline_path: Path
    expected_baseline_sha256: str
    preflight_bundle_path: Path
    expected_preflight_bundle_sha256: str
    output_root: Path
    dry_run: bool = False
    report_root: Path | None = None


@dataclass(frozen=True)
class BuildResult:
    build_version: str
    build_root: Path
    build_manifest: Path
    build_report: Path
    baseline_sha256: str
    preflight_bundle_sha256: str
    dry_run: bool
