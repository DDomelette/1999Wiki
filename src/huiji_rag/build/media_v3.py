"""Crawler-only assembly and read-only availability checks for media v3."""
from __future__ import annotations

import hashlib
import mimetypes
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from src.huiji_rag.media import (
    build_media_object_key,
    build_public_media_url,
    classify_asset_type,
    preferred_format_score,
)
from src.huiji_rag.models import BindingRecord, ResourceRow
from src.huiji_rag.normalizer import normalize_language

from .contracts import (
    VoiceBindingResult,
    canonical_json_bytes,
    compute_resource_id,
    ordered_media_v3_row,
)
from .projection import CorpusProjection, MediaBindingIntent, SemanticChild


_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_VOICE_PREFIX_TO_LANGUAGE = {
    "zh": "zh",
    "en": "en",
    "jp": "jp",
    "kr": "kr",
    "tw": "zh-hant",
}
_ROLE_ASSET_TYPES = {
    "voice": "voice",
    "skill": "skill",
    "roster_avatar": "portrait",
    "stage_live2d": "portrait",
    "stage_portrait": "portrait",
    "collection_item": "image",
    "udimo": "image",
    "character_chibi": "image",
    "character_chibi_variant": "image",
    "skin_background": "image",
}
_OWNER_PAGE_ROLES = {
    "roster_avatar",
    "stage_live2d",
    "stage_portrait",
    "character_chibi",
    "character_chibi_variant",
    "skin_background",
}
_LANGUAGE_ORDER = {"zh": 0, "zh-hant": 1, "en": 2, "jp": 3, "kr": 4}
_RESOURCE_PAYLOAD_FIELDS = (
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
    "sha1",
    "source_sha1",
    "content_sha256",
    "size",
    "duration_ms",
    "width",
    "height",
)


@dataclass(frozen=True)
class MediaV3Config:
    raw_root: Path
    public_base_url: str
    bucket_name: str
    object_prefix: str = "reverse1999"

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_root", Path(self.raw_root).resolve())


@dataclass(frozen=True)
class VoiceResourcePreparation:
    resource_rows: tuple[ResourceRow, ...]
    diagnostics: tuple[Mapping[str, Any], ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_rows", tuple(self.resource_rows))
        object.__setattr__(self, "diagnostics", _frozen_rows(self.diagnostics))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))


@dataclass(frozen=True)
class MediaV3Assembly:
    runtime_rows: tuple[Mapping[str, Any], ...]
    binding_inventory: tuple[Mapping[str, Any], ...]
    unresolved_intents: tuple[Mapping[str, Any], ...]
    blockers: tuple[str, ...]
    resource_count: int
    binding_count: int
    shared_resource_groups: int
    counts_by_role: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_rows", _frozen_rows(self.runtime_rows))
        object.__setattr__(self, "binding_inventory", _frozen_rows(self.binding_inventory))
        object.__setattr__(self, "unresolved_intents", _frozen_rows(self.unresolved_intents))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(
            self, "counts_by_role", MappingProxyType(dict(sorted(self.counts_by_role.items())))
        )

    @property
    def local_validation_passed(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class MinioMediaReconciliation:
    runtime_rows: tuple[Mapping[str, Any], ...]
    same_hash: tuple[str, ...]
    missing_remote: tuple[str, ...]
    hash_mismatch: tuple[Mapping[str, Any], ...]
    orphan_remote: tuple[str, ...]
    blockers: tuple[str, ...]
    inventory_sha256: str
    ready_for_embedding: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_rows", _frozen_rows(self.runtime_rows))
        object.__setattr__(self, "same_hash", tuple(sorted(set(self.same_hash))))
        object.__setattr__(self, "missing_remote", tuple(sorted(set(self.missing_remote))))
        object.__setattr__(self, "hash_mismatch", _frozen_rows(self.hash_mismatch))
        object.__setattr__(self, "orphan_remote", tuple(sorted(set(self.orphan_remote))))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))


@dataclass(frozen=True)
class LegacyMediaReconciliation:
    occurrence_rows: tuple[Mapping[str, Any], ...]
    category_counts: Mapping[str, int]
    active_occurrence_count: int
    unexplained_binding_loss: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurrence_rows", _frozen_rows(self.occurrence_rows))
        object.__setattr__(
            self,
            "category_counts",
            MappingProxyType(dict(sorted(self.category_counts.items()))),
        )


@dataclass(frozen=True)
class _ResolvedResource:
    filename: str
    title: str
    source_url: str
    local_relpath: str
    mime: str
    sha1: str
    sha256: str
    size: int
    width: int
    height: int
    duration_ms: int
    quality_flags: tuple[str, ...]
    source_refs: tuple[dict[str, Any], ...]


class _ResourceResolutionError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


class _ResourceCatalog:
    def __init__(
        self,
        config: MediaV3Config,
        rows: Iterable[Mapping[str, Any]],
    ) -> None:
        self.config = config
        self.rows = tuple(dict(row) for row in rows)
        self.by_stem: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_filename_sha1: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self._file_cache: dict[Path, tuple[str, str, int]] = {}
        for row in self.rows:
            filename = _resource_filename(row)
            if not filename:
                continue
            self.by_stem[_normalized_stem(filename)].append(row)
            sha1 = str(row.get("sha1") or "").lower()
            self.by_filename_sha1[(_normalized_filename(filename), sha1)].append(row)
        for values in (*self.by_stem.values(), *self.by_filename_sha1.values()):
            values.sort(key=_resource_row_sort_key)

    def match_intent(self, intent: MediaBindingIntent) -> tuple[dict[str, Any], ...]:
        stems = [_normalized_stem(intent.resource_stem)] if intent.resource_stem else []
        if intent.media_role == "skill" and intent.resource_stem.casefold().startswith("skill-"):
            stems.append(_normalized_stem(intent.resource_stem[6:]))
        matches: list[dict[str, Any]] = []
        seen: set[bytes] = set()
        for stem in stems:
            for row in self.by_stem.get(stem, ()):
                identity = canonical_json_bytes(row, trailing_newline=False)
                if identity not in seen:
                    seen.add(identity)
                    matches.append(row)
        return tuple(sorted(matches, key=_resource_row_sort_key))

    def rows_for_voice_match(self, match: ResourceRow) -> tuple[dict[str, Any], ...]:
        key = (_normalized_filename(match.filename), str(match.sha1 or "").lower())
        return tuple(self.by_filename_sha1.get(key, ()))

    def resolve(
        self, row: Mapping[str, Any], *, expected_object_kind: str
    ) -> _ResolvedResource:
        filename = _resource_filename(row)
        if not filename:
            raise _ResourceResolutionError("resource_filename_missing", "filename is empty")
        manifest_sha1 = str(row.get("sha1") or "").lower()
        if not _SHA1_RE.fullmatch(manifest_sha1):
            raise _ResourceResolutionError(
                "resource_sha1_invalid", f"invalid SHA-1 for {filename}"
            )
        local_relpath = str(row.get("local_relpath") or "")
        path = _resolve_local_media_path(self.config.raw_root, local_relpath)
        actual_sha1, actual_sha256, actual_size = self._hash_file(path)
        if actual_sha1 != manifest_sha1:
            raise _ResourceResolutionError(
                "local_sha1_mismatch",
                f"local SHA-1 differs from manifest for {filename}",
            )
        manifest_size = _nonnegative_int(row.get("size"), default=-1)
        if manifest_size < 0 or manifest_size != actual_size:
            raise _ResourceResolutionError(
                "local_size_mismatch", f"local size differs from manifest for {filename}"
            )
        declared_sha256 = str(row.get("sha256") or row.get("content_sha256") or "").lower()
        if declared_sha256 and (
            not _SHA256_RE.fullmatch(declared_sha256) or declared_sha256 != actual_sha256
        ):
            raise _ResourceResolutionError(
                "local_sha256_mismatch",
                f"local SHA-256 differs from manifest for {filename}",
            )
        object_key = str(row.get("object_key") or "")
        expected_key = build_media_object_key(
            self.config.object_prefix, expected_object_kind, actual_sha1, filename
        )
        if object_key and object_key != expected_key:
            raise _ResourceResolutionError(
                "object_key_mismatch", f"declared object key differs for {filename}"
            )
        return _ResolvedResource(
            filename=filename,
            title=str(row.get("title") or filename),
            source_url=str(row.get("descriptionurl") or row.get("source_url") or row.get("url") or ""),
            local_relpath=path.relative_to(self.config.raw_root).as_posix(),
            mime=str(row.get("mime") or mimetypes.guess_type(filename)[0] or "application/octet-stream"),
            sha1=actual_sha1,
            sha256=actual_sha256,
            size=actual_size,
            width=max(0, _nonnegative_int(row.get("width"), default=0)),
            height=max(0, _nonnegative_int(row.get("height"), default=0)),
            duration_ms=max(0, _nonnegative_int(row.get("duration_ms"), default=0)),
            quality_flags=tuple(sorted(set(_string_values(row.get("quality_flags"))))),
            source_refs=(_resource_source_ref(row, actual_sha1, filename),),
        )

    def _hash_file(self, path: Path) -> tuple[str, str, int]:
        cached = self._file_cache.get(path)
        if cached is not None:
            return cached
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(chunk)
                sha1.update(chunk)
                sha256.update(chunk)
        result = (sha1.hexdigest(), sha256.hexdigest(), size)
        self._file_cache[path] = result
        return result


def prepare_voice_resource_rows(
    config: MediaV3Config,
    resource_rows: Iterable[Mapping[str, Any]],
) -> VoiceResourcePreparation:
    """Materialize crawler voice resources for the exact VoiceBindingStage."""
    catalog = _ResourceCatalog(config, resource_rows)
    prepared: list[ResourceRow] = []
    diagnostics: list[dict[str, Any]] = []
    blockers: list[str] = []
    for row in sorted(catalog.rows, key=_resource_row_sort_key):
        filename = _resource_filename(row)
        language = _voice_language(filename)
        if language is None:
            continue
        try:
            resource = catalog.resolve(row, expected_object_kind="voice")
        except _ResourceResolutionError as error:
            diagnostics.append(
                {
                    "reason_code": error.reason_code,
                    "filename": filename,
                    "local_relpath": str(row.get("local_relpath") or ""),
                    "detail": error.detail,
                }
            )
            blockers.append(f"voice_resource_invalid:{error.reason_code}:{filename}")
            continue
        object_key = build_media_object_key(
            config.object_prefix, "voice", resource.sha1, resource.filename
        )
        prepared.append(
            ResourceRow(
                filename=resource.filename,
                language=language,
                sha1=resource.sha1,
                sha256=resource.sha256,
                resource_id=f"resource:sha256:{resource.sha256}",
                source_id=f"crawler-resource:{resource.sha1}:{resource.filename}",
                source_url=resource.source_url,
                title=resource.title,
                mime=resource.mime,
                local_relpath=resource.local_relpath,
                object_key=object_key,
                quality_flags=resource.quality_flags,
            )
        )
    prepared.sort(key=lambda item: (item.language, _normalized_filename(item.filename), item.sha1))
    return VoiceResourcePreparation(tuple(prepared), tuple(diagnostics), tuple(blockers))


def assemble_media_v3(
    config: MediaV3Config,
    projection: CorpusProjection,
    resource_rows: Iterable[Mapping[str, Any]],
    voice_result: VoiceBindingResult,
) -> MediaV3Assembly:
    """Build one canonical runtime row per source-backed media binding."""
    catalog = _ResourceCatalog(config, resource_rows)
    children = {child.block.child_id: child for child in projection.children}
    runtime_rows: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    blockers: list[str] = []

    for intent in sorted(projection.media_intents, key=_intent_sort_key):
        child = children.get(intent.child_id)
        if child is None:
            unresolved.append(_unresolved_intent(intent, "unknown_child"))
            blockers.append(f"media_intent_unknown_child:{intent.source_binding_token}")
            continue
        if not intent.resource_stem:
            unresolved.append(_unresolved_intent(intent, "source_has_no_resource_reference"))
            continue
        matches = catalog.match_intent(intent)
        if not matches:
            unresolved.append(_unresolved_intent(intent, "referenced_resource_missing"))
            if intent.missing_policy != "text_only":
                blockers.append(f"media_resource_missing:{intent.source_binding_token}")
            continue
        preferred_score = max(
            preferred_format_score(_resource_filename(source_row))
            for source_row in matches
        )
        preferred_matches = tuple(
            source_row
            for source_row in matches
            if preferred_format_score(_resource_filename(source_row)) == preferred_score
        )
        resolved_groups: dict[
            tuple[str, str, str],
            list[tuple[_ResolvedResource, Mapping[str, Any]]],
        ] = defaultdict(list)
        for source_row in preferred_matches:
            asset_type = _asset_type_for_role(intent.media_role, _resource_filename(source_row))
            object_kind = _object_kind_for_resource(
                _resource_filename(source_row), intent.media_role
            )
            try:
                resource = catalog.resolve(
                    source_row, expected_object_kind=object_kind
                )
            except _ResourceResolutionError as error:
                unresolved.append(
                    {
                        **_unresolved_intent(intent, error.reason_code),
                        "filename": _resource_filename(source_row),
                        "local_relpath": str(source_row.get("local_relpath") or ""),
                        "detail": error.detail,
                    }
                )
                blockers.append(
                    f"media_resource_invalid:{intent.source_binding_token}:{error.reason_code}"
                )
                continue
            resolved_groups[(resource.sha256, asset_type, object_kind)].append(
                (resource, source_row)
            )
        if len(resolved_groups) > 1:
            unresolved.append(
                {
                    **_unresolved_intent(intent, "ambiguous_preferred_resource"),
                    "preferred_format_score": preferred_score,
                    "candidate_filenames": sorted(
                        {
                            item[0].filename
                            for group in resolved_groups.values()
                            for item in group
                        }
                    ),
                    "candidate_sha256": sorted(
                        {key[0] for key in resolved_groups}
                    ),
                }
            )
            blockers.append(
                f"ambiguous_preferred_media_resource:{intent.source_binding_token}"
            )
            continue
        if not resolved_groups:
            continue
        (_sha256, asset_type, object_kind), group = next(
            iter(sorted(resolved_groups.items(), key=lambda item: item[0]))
        )
        resource = group[0][0]
        source_refs = _merge_source_refs(
            intent.source_refs,
            *(item[0].source_refs for item in group),
        )
        row = _build_runtime_row(
            config,
            child,
            resource,
            asset_type=asset_type,
            object_kind=object_kind,
            media_role=intent.media_role,
            source_binding_token=intent.source_binding_token,
            source_refs=source_refs,
            title=intent.title,
            section=intent.section,
            variant=intent.variant,
            skin_id=intent.skin_id,
            event_name=intent.event_name,
            language=intent.language,
            sort_order=intent.sort_order * 1000,
            binding_status="not_applicable",
            quality_flags=resource.quality_flags,
            search_parts=(
                child.block.entity_name,
                intent.title,
                intent.media_role,
                resource.filename,
            ),
        )
        runtime_rows.append(row)
        inventory.append(
            _binding_inventory_row(
                row,
                resource.local_relpath,
                source_kind="projected_relation",
            )
        )

    _append_exact_voice_rows(
        config,
        catalog,
        children,
        voice_result,
        runtime_rows,
        inventory,
        unresolved,
        blockers,
    )
    if voice_result.ready_gate_blocked:
        blockers.append("voice_binding_gate_blocked")

    runtime_rows, duplicate_blockers = _validated_unique_bindings(runtime_rows)
    blockers.extend(duplicate_blockers)
    runtime_rows, inventory, resource_blockers = _canonicalize_resource_payloads(
        runtime_rows, inventory
    )
    blockers.extend(resource_blockers)
    runtime_rows.sort(key=_runtime_sort_key)
    inventory.sort(key=lambda row: str(row["binding_id"]))
    unresolved.sort(key=lambda row: canonical_json_bytes(row, trailing_newline=False))
    resource_counts = Counter(str(row["resource_id"]) for row in runtime_rows)
    role_counts = Counter(str(row["media_role"]) for row in runtime_rows)
    return MediaV3Assembly(
        runtime_rows=tuple(runtime_rows),
        binding_inventory=tuple(inventory),
        unresolved_intents=tuple(unresolved),
        blockers=tuple(blockers),
        resource_count=len(resource_counts),
        binding_count=len(runtime_rows),
        shared_resource_groups=sum(count > 1 for count in resource_counts.values()),
        counts_by_role=dict(role_counts),
    )


def reconcile_media_v3_minio(
    assembly: MediaV3Assembly,
    inventory: object,
    *,
    expected_bucket: str,
    expected_prefix: str,
) -> MinioMediaReconciliation:
    """Classify declared keys against a verified inventory without mutating MinIO."""
    bucket, prefix, inventory_sha256, remote_rows = _inventory_parts(inventory)
    normalized_prefix = expected_prefix.strip("/")
    if bucket != expected_bucket:
        raise ValueError("MinIO inventory bucket does not match media configuration")
    if prefix.strip("/") != normalized_prefix:
        raise ValueError("MinIO inventory prefix does not match media configuration")
    remote_by_key: dict[str, object] = {}
    for remote in remote_rows:
        key = str(_object_value(remote, "object_key") or "")
        if not key or key in remote_by_key:
            raise ValueError("MinIO inventory contains an empty or duplicate object key")
        remote_by_key[key] = remote

    rows_by_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in assembly.runtime_rows:
        rows_by_key[str(row["object_key"])].append(row)
    same_hash: list[str] = []
    missing_remote: list[str] = []
    mismatch: list[dict[str, Any]] = []
    blockers = list(assembly.blockers)
    available_by_key: dict[str, bool] = {}

    for object_key, rows in sorted(rows_by_key.items()):
        expected_identities = {
            (str(row["sha1"]), str(row["content_sha256"]), int(row["size"]))
            for row in rows
        }
        if len(expected_identities) != 1:
            diagnostic = _expanded_mismatch(
                object_key,
                rows,
                actual=None,
                reason_code="candidate_object_key_collision",
            )
            mismatch.append(diagnostic)
            blockers.append(f"minio_hash_mismatch:{object_key}")
            available_by_key[object_key] = False
            continue
        remote = remote_by_key.get(object_key)
        if remote is None:
            missing_remote.append(object_key)
            blockers.append(f"minio_object_missing:{object_key}")
            available_by_key[object_key] = False
            continue
        expected_sha1, expected_sha256, expected_size = next(iter(expected_identities))
        actual_identity = (
            str(_object_value(remote, "sha1") or "").lower(),
            str(_object_value(remote, "sha256") or "").lower(),
            int(_object_value(remote, "size") or 0),
        )
        if actual_identity != (expected_sha1, expected_sha256, expected_size):
            mismatch.append(
                _expanded_mismatch(
                    object_key,
                    rows,
                    actual={
                        "sha1": actual_identity[0],
                        "sha256": actual_identity[1],
                        "size": actual_identity[2],
                        "etag": str(_object_value(remote, "etag") or ""),
                        "version_id": _object_value(remote, "version_id"),
                    },
                    reason_code="remote_content_identity_mismatch",
                )
            )
            blockers.append(f"minio_hash_mismatch:{object_key}")
            available_by_key[object_key] = False
            continue
        same_hash.append(object_key)
        available_by_key[object_key] = True

    reconciled_rows = [
        ordered_media_v3_row({**dict(row), "is_available": available_by_key[str(row["object_key"])]})
        for row in assembly.runtime_rows
    ]
    reconciled_rows.sort(key=_runtime_sort_key)
    orphan_remote = sorted(set(remote_by_key) - set(rows_by_key))
    unique_blockers = tuple(sorted(set(blockers)))
    return MinioMediaReconciliation(
        runtime_rows=tuple(reconciled_rows),
        same_hash=tuple(same_hash),
        missing_remote=tuple(missing_remote),
        hash_mismatch=tuple(mismatch),
        orphan_remote=tuple(orphan_remote),
        blockers=unique_blockers,
        inventory_sha256=inventory_sha256,
        ready_for_embedding=not unique_blockers,
    )


def reconcile_active_media_occurrences(
    active_rows: Iterable[Mapping[str, Any]],
    assembly: MediaV3Assembly,
    projection: CorpusProjection,
    voice_result: VoiceBindingResult,
    *,
    raw_root: Path,
) -> LegacyMediaReconciliation:
    """Classify every legacy media occurrence without using it as candidate input."""
    candidate_rows = tuple(assembly.runtime_rows)
    candidate_by_media_child: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    candidate_by_media: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    candidate_children = {child.block.child_id: child for child in projection.children}
    child_rekeys = {
        link.legacy_id: link.candidate_id
        for link in projection.record_links
        if link.record_kind == "child" and link.legacy_id and link.candidate_id
    }
    for row in candidate_rows:
        media_id = str(row["media_id"])
        candidate_by_media_child[(media_id, str(row["child_id"]))].append(row)
        candidate_by_media[media_id].append(row)

    voice_status: dict[tuple[str, str], set[str]] = defaultdict(set)
    for binding in voice_result.binding_rows:
        effective_status = str(
            voice_result.status_by_source.get(binding.source_id, binding.status.value)
        )
        for match in binding.matches:
            voice_status[(binding.child_id, match.sha1)].add(effective_status)

    root = Path(raw_root).resolve()
    local_hash_cache: dict[Path, tuple[str, str, int]] = {}
    occurrence_rows: list[dict[str, Any]] = []
    categories: Counter[str] = Counter()
    for index, source_row in enumerate(active_rows):
        active = dict(source_row)
        media_id = str(active.get("media_id") or "")
        sha1 = str(active.get("sha1") or "").lower()
        old_child_id = str(active.get("child_id") or "")
        candidate_child_id = child_rekeys.get(old_child_id, old_child_id)
        direct = candidate_by_media_child.get((media_id, candidate_child_id), ())
        same_resource = candidate_by_media.get(media_id, ())
        candidate_binding_ids = sorted({str(row["binding_id"]) for row in direct})
        resource_id = (
            str(same_resource[0]["resource_id"])
            if same_resource
            else ""
        )
        classification = "preserved_binding"
        reason_code = "active_occurrence_maps_to_one_v3_binding"
        if len(direct) > 1:
            classification = "schema_split_binding"
            reason_code = "active_occurrence_maps_to_multiple_explicit_v3_bindings"
        elif not direct:
            statuses = sorted(voice_status.get((candidate_child_id, sha1), ()))
            if str(active.get("asset_type") or "") == "voice" and statuses:
                classification = "evb_status_excluded"
                reason_code = "evb_" + "+".join(statuses)
            else:
                owner_id = f"character:{str(active.get('entity_id') or '')}"
                owner_bindings = [
                    row
                    for row in same_resource
                    if str(row["owner_entity_id"]) == owner_id
                ]
                candidate_binding_ids = sorted(
                    {str(row["binding_id"]) for row in owner_bindings}
                )
                if owner_bindings:
                    classification = "owner_relation_migrated"
                    reason_code = "resource_preserved_under_explicit_owner_relation"
                else:
                    classification = "legacy_non_explicit_relation"
                    reason_code = "legacy_filename_guess_has_no_explicit_crawler_relation"

        local_evidence: dict[str, Any] = {}
        if not resource_id:
            try:
                local_path = _resolve_local_media_path(
                    root, str(active.get("local_relpath") or "")
                )
                actual_sha1, sha256, size = _hash_active_file(
                    local_path, local_hash_cache
                )
                if not _SHA1_RE.fullmatch(sha1) or actual_sha1 != sha1:
                    raise _ResourceResolutionError(
                        "active_sha1_mismatch", str(active.get("local_relpath") or "")
                    )
                resource_id = compute_resource_id(sha256)
                local_evidence = {
                    "content_sha256": sha256,
                    "size": size,
                    "local_relpath": local_path.relative_to(root).as_posix(),
                }
            except _ResourceResolutionError as error:
                classification = "unexplained_missing_resource"
                reason_code = error.reason_code

        active_row_sha256 = hashlib.sha256(
            canonical_json_bytes(active, trailing_newline=False)
        ).hexdigest()
        occurrence_id = "active-occurrence:sha256:" + hashlib.sha256(
            canonical_json_bytes(
                ["huiji.active-media-occurrence/v1", index, active_row_sha256],
                trailing_newline=False,
            )
        ).hexdigest()
        source_child = candidate_children.get(candidate_child_id)
        occurrence = {
            "schema_version": "huiji.active-media-occurrence-map/v1",
            "occurrence_id": occurrence_id,
            "active_row_index": index,
            "active_row_sha256": active_row_sha256,
            "active_media_id": media_id,
            "active_sha1": sha1,
            "active_parent_id": str(active.get("parent_id") or ""),
            "active_child_id": old_child_id,
            "candidate_child_id": candidate_child_id,
            "resource_id": resource_id,
            "candidate_binding_ids": candidate_binding_ids,
            "classification": classification,
            "reason_code": reason_code,
            "candidate_source_refs": (
                []
                if source_child is None
                else [dict(ref) for ref in source_child.block.source_refs]
            ),
            "local_evidence": local_evidence,
        }
        occurrence_rows.append(occurrence)
        categories[classification] += 1

    return LegacyMediaReconciliation(
        occurrence_rows=tuple(occurrence_rows),
        category_counts=dict(categories),
        active_occurrence_count=len(occurrence_rows),
        unexplained_binding_loss=categories["unexplained_missing_resource"],
    )


def _append_exact_voice_rows(
    config: MediaV3Config,
    catalog: _ResourceCatalog,
    children: Mapping[str, SemanticChild],
    voice_result: VoiceBindingResult,
    runtime_rows: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    blockers: list[str],
) -> None:
    for binding in sorted(
        voice_result.exact_bindings,
        key=lambda item: (item.child_id, item.language, item.source_id),
    ):
        child = children.get(binding.child_id)
        if child is None:
            unresolved.append(
                {
                    "reason_code": "voice_child_excluded",
                    "source_binding_token": binding.source_id,
                    "child_id": binding.child_id,
                    "event_name": binding.event_name,
                    "language": binding.language,
                }
            )
            continue
        groups: dict[str, list[tuple[_ResolvedResource, ResourceRow]]] = defaultdict(list)
        for match in binding.matches:
            source_rows = catalog.rows_for_voice_match(match)
            if not source_rows:
                unresolved.append(
                    {
                        "reason_code": "voice_manifest_evidence_missing",
                        "source_binding_token": binding.source_id,
                        "child_id": binding.child_id,
                        "filename": match.filename,
                    }
                )
                blockers.append(f"voice_manifest_evidence_missing:{binding.source_id}")
                continue
            for source_row in source_rows:
                try:
                    resource = catalog.resolve(source_row, expected_object_kind="voice")
                except _ResourceResolutionError as error:
                    unresolved.append(
                        {
                            "reason_code": error.reason_code,
                            "source_binding_token": binding.source_id,
                            "child_id": binding.child_id,
                            "filename": match.filename,
                            "detail": error.detail,
                        }
                    )
                    blockers.append(f"voice_resource_invalid:{binding.source_id}:{error.reason_code}")
                    continue
                if resource.sha256 != match.sha256 or resource.sha1 != match.sha1:
                    unresolved.append(
                        {
                            "reason_code": "voice_stage_resource_drift",
                            "source_binding_token": binding.source_id,
                            "child_id": binding.child_id,
                            "filename": match.filename,
                        }
                    )
                    blockers.append(f"voice_stage_resource_drift:{binding.source_id}")
                    continue
                groups[resource.sha256].append((resource, match))
        for resource_index, (_sha256, group) in enumerate(sorted(groups.items())):
            resource = group[0][0]
            language, _prefix = normalize_language(binding.language)
            source_refs = _merge_source_refs(
                child.block.source_refs,
                resource.source_refs,
            )
            quality_flags = tuple(
                sorted(set((*binding.quality_flags, *resource.quality_flags)))
            )
            row = _build_runtime_row(
                config,
                child,
                resource,
                asset_type="voice",
                object_kind="voice",
                media_role="voice",
                source_binding_token=f"voice:{child.stable_source_token}:{language}",
                source_refs=source_refs,
                title=child.block.title,
                section="voice",
                variant="",
                skin_id=binding.skin_id,
                event_name=binding.event_name,
                language=language,
                sort_order=(
                    child.block.chunk_index * 1000
                    + _LANGUAGE_ORDER.get(language, 100)
                    + resource_index
                ),
                binding_status="exact",
                quality_flags=quality_flags,
                search_parts=(
                    child.block.entity_name,
                    child.block.title,
                    binding.transcript,
                    binding.event_name,
                    language,
                ),
            )
            runtime_rows.append(row)
            inventory.append(
                _binding_inventory_row(row, resource.local_relpath, source_kind="voice_exact")
            )


def _build_runtime_row(
    config: MediaV3Config,
    child: SemanticChild,
    resource: _ResolvedResource,
    *,
    asset_type: str,
    object_kind: str,
    media_role: str,
    source_binding_token: str,
    source_refs: Sequence[Mapping[str, Any]],
    title: str,
    section: str,
    variant: str,
    skin_id: str,
    event_name: str,
    language: str,
    sort_order: int,
    binding_status: str,
    quality_flags: Sequence[str],
    search_parts: Sequence[str],
) -> dict[str, Any]:
    object_key = build_media_object_key(
        config.object_prefix, object_kind, resource.sha1, resource.filename
    )
    url = build_public_media_url(config.public_base_url, config.bucket_name, object_key)
    values = {
        "entity_id": child.block.entity_id,
        "entity_name": child.block.entity_name,
        "owner_entity_id": child.owner_entity_id,
        "owner_page_id": child.owner_page_id,
        "parent_id": child.block.parent_id,
        "child_id": child.block.child_id,
        "section": section,
        "asset_type": asset_type,
        "media_role": media_role,
        "variant": str(variant or ""),
        "skin_id": str(skin_id or ""),
        "event_name": str(event_name or ""),
        "language": str(language or ""),
        "source_binding_token": source_binding_token,
        "source_refs": [dict(item) for item in source_refs],
        "mime": resource.mime,
        "filename": resource.filename,
        "title": str(title or resource.title),
        "source_url": resource.source_url,
        "url": url,
        "object_key": object_key,
        "is_available": False,
        "is_common": asset_type == "common",
        "attach_policy": _attach_policy(media_role),
        "search_text": _search_text(search_parts),
        "panel_group": _panel_group(media_role, skin_id),
        "sort_order": max(0, int(sort_order)),
        "duration_ms": resource.duration_ms,
        "width": resource.width,
        "height": resource.height,
        "quality_flags": sorted(set(str(item) for item in quality_flags if str(item))),
        "sha1": resource.sha1,
        "source_sha1": resource.sha1,
        "content_sha256": resource.sha256,
        "size": resource.size,
        "binding_status": binding_status,
    }
    return ordered_media_v3_row(values)


def _binding_inventory_row(
    row: Mapping[str, Any], local_relpath: str, *, source_kind: str
) -> dict[str, Any]:
    return {
        "schema_version": "huiji.media-binding-inventory/v3",
        "binding_id": row["binding_id"],
        "resource_id": row["resource_id"],
        "owner_entity_id": row["owner_entity_id"],
        "owner_page_id": row["owner_page_id"],
        "parent_id": row["parent_id"],
        "child_id": row["child_id"],
        "media_role": row["media_role"],
        "source_binding_token": row["source_binding_token"],
        "object_key": row["object_key"],
        "local_relpath": local_relpath,
        "sha1": row["sha1"],
        "content_sha256": row["content_sha256"],
        "size": row["size"],
        "source_kind": source_kind,
    }


def _validated_unique_bindings(
    rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    by_binding: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for row in rows:
        binding_id = str(row["binding_id"])
        previous = by_binding.get(binding_id)
        if previous is None:
            by_binding[binding_id] = row
            continue
        blockers.append(f"duplicate_binding_identity:{binding_id}")
        if previous != row:
            blockers.append(f"conflicting_binding_payload:{binding_id}")
    return list(by_binding.values()), blockers


def _canonicalize_resource_payloads(
    rows: Sequence[dict[str, Any]],
    inventory: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    by_resource: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_resource[str(row["resource_id"])].append(row)

    blockers: list[str] = []
    canonical_rows: list[dict[str, Any]] = []
    canonical_by_binding: dict[str, dict[str, Any]] = {}
    for resource_id, group in sorted(by_resource.items()):
        content_identities = {
            (
                str(row["sha1"]),
                str(row["content_sha256"]),
                int(row["size"]),
            )
            for row in group
        }
        if len(content_identities) != 1:
            blockers.append(f"resource_content_identity_conflict:{resource_id}")
        canonical = min(group, key=_canonical_resource_row_sort_key)
        quality_flags = sorted(
            {
                str(flag)
                for row in group
                for flag in row["quality_flags"]
                if str(flag)
            }
        )
        for original in group:
            normalized = dict(original)
            for field_name in _RESOURCE_PAYLOAD_FIELDS:
                normalized[field_name] = canonical[field_name]
            normalized["quality_flags"] = quality_flags
            canonical_rows.append(normalized)
            canonical_by_binding[str(normalized["binding_id"])] = normalized

    canonical_inventory: list[dict[str, Any]] = []
    for original in inventory:
        row = dict(original)
        runtime = canonical_by_binding.get(str(row.get("binding_id") or ""))
        if runtime is not None:
            for field_name in (
                "resource_id",
                "object_key",
                "sha1",
                "content_sha256",
                "size",
            ):
                row[field_name] = runtime[field_name]
        canonical_inventory.append(row)
    return canonical_rows, canonical_inventory, blockers


def _canonical_resource_row_sort_key(
    row: Mapping[str, Any],
) -> tuple[int, str, str, str, str]:
    filename = str(row["filename"])
    return (
        -preferred_format_score(filename),
        _normalized_filename(filename),
        str(row["object_key"]),
        str(row["source_url"]),
        str(row["binding_id"]),
    )


def _inventory_parts(inventory: object) -> tuple[str, str, str, Sequence[object]]:
    if isinstance(inventory, Mapping):
        try:
            from src.huiji_rag.minio_strict import ObjectInventory

            parsed = ObjectInventory.from_json(inventory)
        except Exception as error:
            raise ValueError(
                "MinIO inventory evidence is invalid: "
                f"{type(error).__name__}: {error}"
            ) from error
        inventory = parsed
    bucket = str(_object_value(inventory, "bucket") or "")
    prefix = str(_object_value(inventory, "prefix") or "")
    inventory_sha256 = str(_object_value(inventory, "inventory_sha256") or "")
    objects = _object_value(inventory, "objects")
    if not _SHA256_RE.fullmatch(inventory_sha256) or not isinstance(objects, (tuple, list)):
        raise ValueError("MinIO inventory evidence is incomplete")
    return bucket, prefix, inventory_sha256, objects


def _expanded_mismatch(
    object_key: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    actual: Mapping[str, Any] | None,
    reason_code: str,
) -> dict[str, Any]:
    expected = sorted(
        {
            (str(row["sha1"]), str(row["content_sha256"]), int(row["size"]))
            for row in rows
        }
    )
    return {
        "reason_code": reason_code,
        "object_key": object_key,
        "prefix": object_key.split("/", 1)[0],
        "expected": [
            {"sha1": sha1, "sha256": sha256, "size": size}
            for sha1, sha256, size in expected
        ],
        "actual": None if actual is None else dict(actual),
        "binding_ids": sorted({str(row["binding_id"]) for row in rows}),
        "owner_entity_ids": sorted({str(row["owner_entity_id"]) for row in rows}),
        "owner_page_ids": sorted({str(row["owner_page_id"]) for row in rows}),
        "child_ids": sorted({str(row["child_id"]) for row in rows}),
        "sections": sorted({str(row["section"]) for row in rows}),
        "media_roles": sorted({str(row["media_role"]) for row in rows}),
        "consumers": ["huiji_rag", "huiji_wiki"],
    }


def _resolve_local_media_path(raw_root: Path, local_relpath: str) -> Path:
    if not local_relpath:
        raise _ResourceResolutionError("local_path_missing", "local_relpath is empty")
    unresolved = raw_root / Path(local_relpath)
    path = unresolved.resolve()
    try:
        path.relative_to(raw_root)
    except ValueError as error:
        raise _ResourceResolutionError("local_path_escape", local_relpath) from error
    current = raw_root
    for part in Path(local_relpath).parts:
        current = current / part
        if current.is_symlink():
            raise _ResourceResolutionError("local_path_symlink", local_relpath)
    if path.suffix.casefold() == ".pyc" or not path.is_file():
        raise _ResourceResolutionError("local_file_missing", local_relpath)
    return path


def _hash_active_file(
    path: Path, cache: dict[Path, tuple[str, str, int]]
) -> tuple[str, str, int]:
    cached = cache.get(path)
    if cached is not None:
        return cached
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    result = (sha1.hexdigest(), sha256.hexdigest(), size)
    cache[path] = result
    return result


def _resource_source_ref(
    row: Mapping[str, Any], sha1: str, filename: str
) -> dict[str, Any]:
    return {
        "source_kind": "crawler_resource",
        "source_title": str(row.get("title") or filename),
        "source_row_id": f"crawler-resource:{sha1}:{filename}",
        "source_content_sha256": hashlib.sha256(
            canonical_json_bytes(dict(row), trailing_newline=False)
        ).hexdigest(),
    }


def _merge_source_refs(*groups: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    merged: dict[bytes, dict[str, Any]] = {}
    for group in groups:
        for raw_ref in group:
            ref = _normalize_source_ref(raw_ref)
            key = canonical_json_bytes(ref, trailing_newline=False)
            merged[key] = ref
    return tuple(merged[key] for key in sorted(merged))


def _normalize_source_ref(raw_ref: Mapping[str, Any]) -> dict[str, Any]:
    if "source_kind" in raw_ref:
        ref = dict(raw_ref)
    else:
        title = str(raw_ref.get("title") or "")
        json_path = str(raw_ref.get("json_path") or "$")
        revision = raw_ref.get("revid")
        ref = {
            "source_kind": "crawler_data_page",
            "source_title": title,
            "source_row_id": f"{title}#{json_path}",
            "source_content_sha256": str(raw_ref.get("content_sha256") or "").lower(),
            "json_path": json_path,
        }
        if revision is not None:
            ref["revision"] = str(revision)
    content_sha256 = str(ref.get("source_content_sha256") or "").lower()
    if not _SHA256_RE.fullmatch(content_sha256):
        raise ValueError("media source reference has an invalid source_content_sha256")
    for field_name in ("source_kind", "source_title", "source_row_id"):
        if not str(ref.get(field_name) or ""):
            raise ValueError(f"media source reference has an empty {field_name}")
    ref["source_content_sha256"] = content_sha256
    return ref


def _unresolved_intent(intent: MediaBindingIntent, reason_code: str) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "source_binding_token": intent.source_binding_token,
        "owner_entity_id": intent.owner_entity_id,
        "owner_page_id": intent.owner_page_id,
        "parent_id": intent.parent_id,
        "child_id": intent.child_id,
        "section": intent.section,
        "media_role": intent.media_role,
        "resource_stem": intent.resource_stem,
        "missing_policy": intent.missing_policy,
    }


def _asset_type_for_role(media_role: str, filename: str) -> str:
    explicit = _ROLE_ASSET_TYPES.get(media_role)
    if explicit:
        return explicit
    classified = classify_asset_type(filename)
    return "image" if classified == "unknown" else classified


def _object_kind_for_resource(filename: str, media_role: str) -> str:
    lower = filename.casefold()
    if media_role in {"collection_item", "udimo"}:
        return "image"
    if media_role == "skill" and not lower.startswith("skill-"):
        return "image"
    return _asset_type_for_role(media_role, filename)


def _attach_policy(media_role: str) -> str:
    if media_role == "voice":
        return "voice_line"
    if media_role in _OWNER_PAGE_ROLES:
        return "owner_page"
    return "source_relation"


def _panel_group(media_role: str, skin_id: str) -> str:
    if media_role == "voice":
        return f"voice:skin:{skin_id}" if skin_id else "voice"
    return media_role


def _voice_language(filename: str) -> str | None:
    if Path(filename).suffix.casefold() != ".mp3":
        return None
    prefix, separator, _rest = Path(filename).stem.partition("_")
    if not separator:
        return None
    return _VOICE_PREFIX_TO_LANGUAGE.get(prefix.casefold())


def _resource_filename(row: Mapping[str, Any]) -> str:
    value = str(row.get("filename") or row.get("name") or "").replace("\\", "/")
    return value.rsplit("/", 1)[-1]


def _normalized_filename(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _normalized_stem(value: str) -> str:
    return _normalized_filename(Path(value).stem)


def _resource_row_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _normalized_filename(_resource_filename(row)),
        str(row.get("sha1") or "").lower(),
        str(row.get("local_relpath") or ""),
    )


def _intent_sort_key(intent: MediaBindingIntent) -> tuple[str, int, str, str]:
    return (
        intent.owner_page_id,
        intent.sort_order,
        intent.source_binding_token,
        intent.resource_stem.casefold(),
    )


def _runtime_sort_key(row: Mapping[str, Any]) -> tuple[str, int, str]:
    return (
        str(row["owner_page_id"]),
        int(row["sort_order"]),
        str(row["binding_id"]),
    )


def _search_text(parts: Sequence[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(str(part) for part in parts if str(part))).strip()


def _nonnegative_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result >= 0 else default


def _string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (tuple, list)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _object_value(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _frozen_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(MappingProxyType(dict(row)) for row in rows)


__all__ = [
    "MediaV3Assembly",
    "MediaV3Config",
    "LegacyMediaReconciliation",
    "MinioMediaReconciliation",
    "VoiceResourcePreparation",
    "assemble_media_v3",
    "prepare_voice_resource_rows",
    "reconcile_active_media_occurrences",
    "reconcile_media_v3_minio",
]
