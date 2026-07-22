"""Deterministic, isolated EventName voice-binding artifacts."""
from __future__ import annotations

from collections import Counter
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from typing import Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote, urlsplit, urlunsplit

from src.huiji_rag.media import media_id_for_sha1
from src.huiji_rag.models import (
    ArtifactManifest,
    BindingRecord,
    BindingStatus,
    EntityNameDirectory,
    EntityNameExclusion,
    EvbBuildPaths,
    MediaArtifacts,
)
from src.rag.sparse import canonical_child_corpus_sha256


MEDIA_ASSET_V2_FIELDS: Sequence[str] = (
    "media_id",
    "entity_id",
    "entity_name",
    "parent_id",
    "child_id",
    "asset_type",
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
    "quality_flags",
    "local_relpath",
    "sha1",
    "event_name",
    "language",
    "source_sha1",
    "content_sha256",
    "binding_status",
    "artifact_schema_version",
    "binding_key",
)
LEGACY_MEDIA_ASSET_FIELDS: Sequence[str] = MEDIA_ASSET_V2_FIELDS[:23]
INTERNAL_MEDIA_ASSET_V2_FIELDS: Sequence[str] = (
    "local_relpath",
    "sha1",
    "source_sha1",
    "content_sha256",
    "binding_key",
    "quality_flags",
    "object_key",
    "source_url",
)
_SHA1_RE = re.compile(r"[0-9a-fA-F]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_RUNTIME_STATUSES = frozenset((BindingStatus.EXACT.value, BindingStatus.NOT_APPLICABLE.value))
_DIAGNOSTIC_CAUSES = frozenset(
    (
        "cross_child_sha",
        "duplicate_eventname_sha",
        "missing_exact_resource",
        "same_sha_different_event_or_text",
        "shared_sha_distinct_binding_key",
    )
)
_STATUS_ORDER = {
    BindingStatus.EXACT.value: 0,
    BindingStatus.SHORTFALL.value: 1,
    BindingStatus.QUARANTINED.value: 2,
    BindingStatus.FATAL.value: 3,
}


def adapt_legacy_media_row(row: Mapping[str, object]) -> dict[str, object]:
    missing = [field for field in LEGACY_MEDIA_ASSET_FIELDS if field not in row]
    if missing:
        raise ValueError(f"legacy media row missing fields: {', '.join(missing)}")
    sha1 = _valid_sha1(row.get("sha1"), "legacy sha1")
    media_id = str(row.get("media_id") or "")
    if media_id != media_id_for_sha1(sha1):
        raise ValueError("legacy media_id must use its full lowercase SHA-1")
    adapted = {field: row[field] for field in LEGACY_MEDIA_ASSET_FIELDS}
    adapted.update(
        {
            "event_name": None,
            "language": None,
            "source_sha1": sha1,
            "content_sha256": None,
            "binding_status": BindingStatus.NOT_APPLICABLE.value,
            "artifact_schema_version": "evb.media-asset/v1_legacy",
            "binding_key": None,
        }
    )
    return adapted


def build_binding_inventory(rows: Iterable[BindingRecord]) -> Iterator[dict[str, object]]:
    records = sorted(
        rows,
        key=lambda row: (_STATUS_ORDER[row.binding_status.value], row.source_id),
    )
    for record in records:
        payload = record.to_json()
        payload.update(
            {
                "schema_version": "evb.binding-inventory/v1",
                "diagnostic_classification": {
                    "binding_status": record.binding_status.value,
                    "runtime_eligible": record.binding_status is BindingStatus.EXACT,
                    "root_causes": sorted(
                        flag for flag in record.quality_flags if flag in _DIAGNOSTIC_CAUSES
                    ),
                    "exclusion_causes": [],
                },
            }
        )
        yield payload


def build_entity_name_directory(
    parent_rows: Iterable[Mapping[str, object]],
) -> EntityNameDirectory:
    values_by_key: dict[str, set[tuple[str, str]]] = {}
    for row in parent_rows:
        if str(row.get("section_kind") or "") != "entity":
            continue
        entity_key = str(row.get("parent_id") or "").strip()
        output_entity_id = str(row.get("entity_id") or "").strip()
        entity_name = str(row.get("entity_name") or "").strip()
        if not entity_key or not output_entity_id or not entity_name:
            continue
        value = (output_entity_id, entity_name)
        values_by_key.setdefault(entity_key, set()).add(value)
    entries = {
        key: next(iter(values))
        for key, values in values_by_key.items()
        if len(values) == 1
    }
    conflicts = {
        key: tuple(sorted(values))
        for key, values in values_by_key.items()
        if len(values) > 1
    }
    return EntityNameDirectory(entries=entries, conflicts=conflicts)


def build_entity_name_exclusions(
    binding_rows: Iterable[BindingRecord],
    entity_names: EntityNameDirectory,
) -> tuple[EntityNameExclusion, ...]:
    exclusions = []
    for row in binding_rows:
        if row.binding_status is not BindingStatus.EXACT:
            continue
        value = entity_names.entries.get(row.entity_id)
        if row.entity_id in entity_names.conflicts:
            cause = "entity_name_exclusion:conflicting_canonical_names"
        elif value is None or not value[0].strip() or not value[1].strip():
            cause = "entity_name_exclusion:missing_or_blank"
        else:
            continue
        if cause:
            exclusions.append(
                EntityNameExclusion(
                    source_id=row.source_id,
                    entity_key=row.entity_id,
                    cause=cause,
                )
            )
    return tuple(sorted(exclusions, key=lambda item: item.source_id))


def build_runtime_media_projection(
    nonvoice_rows: Iterable[Mapping[str, object]],
    binding_rows: Iterable[BindingRecord],
    entity_names: EntityNameDirectory,
    public_base_url: str,
    bucket_name: str,
) -> Iterator[dict[str, object]]:
    normalized_base = _validated_public_base_url(public_base_url)
    normalized_bucket = _validated_bucket_name(bucket_name)
    runtime: list[dict[str, object]] = []
    for row in nonvoice_rows:
        if str(row.get("asset_type") or "") == "voice":
            raise ValueError("build_runtime_media_projection nonvoice_rows contains voice")
        runtime.append(adapt_legacy_media_row(row))
    for binding in binding_rows:
        if binding.binding_status is not BindingStatus.EXACT:
            continue
        identity = entity_names.entries.get(binding.entity_id)
        if identity is None or not identity[0].strip() or not identity[1].strip():
            continue
        _validate_exact_binding(binding)
        output_entity_id, entity_name = identity
        binding_key = f"{binding.child_id}|{binding.language}|{binding.expected_filename}"
        for resource in binding.matches:
            sha1 = _valid_sha1(resource.sha1, "exact voice source_sha1")
            sha256 = _valid_sha256(resource.sha256, "exact voice content_sha256")
            quality_flags = list(
                dict.fromkeys((*binding.quality_flags, *resource.quality_flags))
            )
            runtime.append(
                {
                    "media_id": media_id_for_sha1(sha1),
                    "entity_id": output_entity_id,
                    "entity_name": entity_name,
                    "parent_id": binding.parent_id,
                    "child_id": binding.child_id,
                    "asset_type": "voice",
                    "mime": resource.mime,
                    "filename": resource.filename,
                    "title": resource.title or binding.source.title,
                    "source_url": resource.source_url,
                    "url": _public_media_url(
                        normalized_base, normalized_bucket, resource.object_key
                    ),
                    "object_key": resource.object_key,
                    "is_available": bool(resource.local_relpath),
                    "is_common": False,
                    "attach_policy": "on_intent",
                    "search_text": " ".join(
                        value
                        for value in (
                            entity_name,
                            binding.event_name,
                            binding.transcript,
                            resource.filename,
                        )
                        if value
                    ),
                    "content_hash": sha256,
                    "panel_group": (
                        f"voice:skin:{binding.skin_id}" if binding.skin_id else "voice:default"
                    ),
                    "sort_order": 0,
                    "duration_ms": 0,
                    "quality_flags": quality_flags,
                    "local_relpath": resource.local_relpath,
                    "sha1": sha1,
                    "event_name": binding.event_name,
                    "language": binding.language,
                    "source_sha1": sha1,
                    "content_sha256": sha256,
                    "binding_status": BindingStatus.EXACT.value,
                    "artifact_schema_version": "evb.media-asset/v2",
                    "binding_key": binding_key,
                }
            )
    runtime.sort(key=_runtime_sort_key)
    yield from runtime


def canonical_nonvoice_projection_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    projection = [
        {field: row.get(field) for field in LEGACY_MEDIA_ASSET_FIELDS}
        for row in rows
        if str(row.get("asset_type") or "") != "voice"
    ]
    projection.sort(key=lambda row: _canonical_json_bytes(row))
    return hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def write_media_artifacts(paths: EvbBuildPaths, artifacts: MediaArtifacts) -> ArtifactManifest:
    runtime_rows = [dict(row) for row in artifacts.runtime_rows]
    inventory_rows = list(build_binding_inventory(artifacts.binding_rows))
    schema = dict(artifacts.schema)
    _validate_schema(schema)
    public_base_url: str | None = None
    bucket_name: str | None = None
    if any(
        row.get("binding_status") == BindingStatus.EXACT.value
        and row.get("asset_type") == "voice"
        for row in runtime_rows
    ):
        if "public_base_url" not in artifacts.manifest_inputs:
            raise ValueError("exact voice artifacts require manifest_inputs public_base_url")
        if "bucket_name" not in artifacts.manifest_inputs:
            raise ValueError("exact voice artifacts require manifest_inputs bucket_name")
        public_base_url = _validated_public_base_url(
            str(artifacts.manifest_inputs["public_base_url"])
        )
        bucket_name = _validated_bucket_name(str(artifacts.manifest_inputs["bucket_name"]))
    _validate_runtime_rows(runtime_rows, public_base_url, bucket_name)
    _validate_nonvoice_projection(artifacts.nonvoice_rows, runtime_rows)
    _validate_isolated_paths(paths)
    exclusions = {item.source_id: item for item in artifacts.entity_name_exclusions}
    for row in inventory_rows:
        exclusion = exclusions.get(str(row.get("source_id") or ""))
        if exclusion is not None:
            classification = dict(row["diagnostic_classification"])
            classification["runtime_eligible"] = False
            classification["exclusion_causes"] = [exclusion.cause]
            row["diagnostic_classification"] = classification

    parent_rows = sorted(
        (dict(row) for row in artifacts.parent_rows), key=lambda row: str(row.get("parent_id") or "")
    )
    child_rows = sorted(
        (dict(row) for row in artifacts.child_rows), key=lambda row: str(row.get("child_id") or "")
    )
    child_corpus_sha256 = canonical_child_corpus_sha256(child_rows) if child_rows else None
    status_counts = dict(sorted(Counter(str(row["binding_status"]) for row in runtime_rows).items()))
    build_version = str(artifacts.manifest_inputs.get("build_version") or paths.build_root.name)
    baseline_hashes = {
        str(key): str(value)
        for key, value in artifacts.manifest_inputs.items()
        if "sha256" in str(key).lower() and isinstance(value, str)
    }
    previous_evidence = {
        str(key): value
        for key, value in artifacts.manifest_inputs.items()
        if str(key).startswith(("previous_", "canonical_non_media_", "child_corpus_"))
    }
    prepared: dict[str, tuple[Path, bytes]] = {
        "binding_inventory": (paths.binding_inventory, _jsonl_bytes(inventory_rows)),
        "media_assets_v2": (
            paths.media_assets_v2,
            _jsonl_bytes(sorted(runtime_rows, key=_runtime_sort_key)),
        ),
        "media_schema_v2": (paths.media_schema_v2, _canonical_json_bytes(schema)),
    }
    if artifacts.parent_rows:
        prepared["parent_blocks"] = (paths.parent_blocks, _jsonl_bytes(parent_rows))
    if artifacts.child_rows:
        prepared["child_blocks"] = (paths.child_blocks, _jsonl_bytes(child_rows))
        prepared["child_bm25"] = (
            paths.child_bm25,
            _canonical_json_bytes({"records": child_rows}),
        )
        previous_evidence["child_corpus_sha256"] = child_corpus_sha256
    file_hashes = {
        name: hashlib.sha256(payload).hexdigest()
        for name, (_path, payload) in prepared.items()
    }
    manifest = ArtifactManifest(
        schema_version="evb.media-artifact-manifest/v2",
        build_version=build_version,
        file_paths={
            name: path.relative_to(paths.build_root).as_posix()
            for name, (path, _payload) in prepared.items()
        },
        file_sha256=file_hashes,
        row_counts={
            "binding_inventory": len(inventory_rows),
            "runtime_media": len(runtime_rows),
            "nonvoice": len(artifacts.nonvoice_rows),
            "parent": len(parent_rows),
            "child": len(child_rows),
            "entity_name_exclusions": len(exclusions),
        },
        baseline_input_hashes=baseline_hashes,
        previous_build_evidence=previous_evidence,
        runtime_status_counts=status_counts,
    )
    manifest_payload = _canonical_json_bytes(manifest.to_json())
    paths.build_root.mkdir(parents=True, exist_ok=False)
    for path, payload in prepared.values():
        _write_prepared_bytes(path, payload)
    _write_prepared_bytes(paths.media_manifest_v2, manifest_payload)
    return manifest


def _validate_exact_binding(binding: BindingRecord) -> None:
    if not binding.source_id or not binding.entity_id or not binding.parent_id or not binding.child_id:
        raise ValueError("exact voice binding is missing source identity evidence")
    if not binding.event_name or not binding.language or not binding.expected_filename:
        raise ValueError("exact voice binding is missing EventName evidence")
    if not binding.matches:
        raise ValueError("exact voice binding is missing resource evidence")
    if len(binding.matches) != len(binding.source_sha1) or len(binding.matches) != len(binding.content_sha256):
        raise ValueError("exact voice binding evidence cardinality mismatch")
    if binding.source_sha1 != tuple(resource.sha1 for resource in binding.matches):
        raise ValueError("exact voice SHA-1 evidence does not match retained resources")
    if binding.content_sha256 != tuple(resource.sha256 for resource in binding.matches):
        raise ValueError("exact voice SHA-256 evidence does not match retained resources")
    for resource in binding.matches:
        _valid_sha1(resource.sha1, "exact voice source_sha1")
        _valid_sha256(resource.sha256, "exact voice content_sha256")
        if not resource.filename or not resource.object_key or not resource.local_relpath:
            raise ValueError("exact voice resource is not consumable")


def _validate_schema(schema: Mapping[str, object]) -> None:
    if schema.get("schema_version") != "evb.media-assets/v2":
        raise ValueError("media v2 schema version drift")
    fields = schema.get("fields")
    if not isinstance(fields, list):
        raise ValueError("media v2 schema fields must be a list")
    if len(fields) != len(set(str(field) for field in fields)):
        raise ValueError("media v2 schema contains duplicate fields")
    if tuple(fields) != tuple(MEDIA_ASSET_V2_FIELDS):
        raise ValueError("media v2 schema fields drift from the exact contract")
    internal_fields = schema.get("internal_fields")
    if not isinstance(internal_fields, list) or tuple(internal_fields) != tuple(
        INTERNAL_MEDIA_ASSET_V2_FIELDS
    ):
        raise ValueError("media v2 internal fields drift from the exact contract")


def _validate_runtime_rows(
    rows: Sequence[Mapping[str, object]],
    public_base_url: str | None = None,
    bucket_name: str | None = None,
) -> None:
    voice_media_ids: set[str] = set()
    association_keys: set[tuple[str, str, str, str]] = set()
    for row in rows:
        status = str(row.get("binding_status") or "")
        asset_type = str(row.get("asset_type") or "")
        if status not in _RUNTIME_STATUSES:
            raise ValueError("non-consumable binding status in runtime projection")
        if (asset_type == "voice") != (status == BindingStatus.EXACT.value):
            raise ValueError("non-consumable runtime voice row")
        if tuple(row.keys()) != tuple(MEDIA_ASSET_V2_FIELDS) and set(row) != set(MEDIA_ASSET_V2_FIELDS):
            raise ValueError("runtime media row fields drift from the exact v2 contract")
        sha1 = _valid_sha1(row.get("sha1"), "runtime sha1")
        media_id = str(row.get("media_id") or "")
        if media_id != media_id_for_sha1(sha1):
            raise ValueError("runtime media_id is not a full SHA-1 ID")
        association_key = (
            media_id,
            str(row.get("parent_id") or ""),
            str(row.get("child_id") or ""),
            status,
        )
        if association_key in association_keys:
            raise ValueError(f"duplicate runtime association: {association_key}")
        association_keys.add(association_key)
        if asset_type == "voice":
            if media_id in voice_media_ids:
                raise ValueError(f"duplicate exact voice media_id: {media_id}")
            voice_media_ids.add(media_id)
            _valid_sha256(row.get("content_sha256"), "runtime content_sha256")
            if not str(row.get("entity_id") or "").strip() or not str(row.get("entity_name") or "").strip():
                raise ValueError("runtime voice row lacks canonical entity identity")
            if row.get("artifact_schema_version") != "evb.media-asset/v2":
                raise ValueError("runtime voice artifact schema version drift")
            expected_binding_key = "|".join(
                (
                    str(row.get("child_id") or ""),
                    str(row.get("language") or ""),
                    str(row.get("filename") or ""),
                )
            )
            if row.get("binding_key") != expected_binding_key:
                raise ValueError("runtime voice binding_key drift")
            _validate_relative_artifact_path(row.get("object_key"), "object_key")
            _validate_relative_artifact_path(row.get("local_relpath"), "local_relpath")
            source_sha1 = _valid_sha1(row.get("source_sha1"), "runtime source_sha1")
            if source_sha1 != sha1:
                raise ValueError("runtime source_sha1 differs from sha1")
            content_sha256 = _valid_sha256(
                row.get("content_sha256"), "runtime content_sha256"
            )
            if row.get("content_hash") != content_sha256:
                raise ValueError("runtime content_hash differs from content_sha256")
            source_url = str(row.get("source_url") or "")
            public_url = str(row.get("url") or "")
            if not source_url or source_url == public_url:
                raise ValueError("runtime source/public URL separation failed")
            if public_base_url is None or bucket_name is None:
                raise ValueError("runtime exact voice lacks pinned public URL authority")
            expected_public_url = _public_media_url(
                public_base_url,
                bucket_name,
                str(row.get("object_key") or ""),
            )
            if public_url != expected_public_url:
                raise ValueError("runtime public URL authority differs from manifest inputs")


def _validate_nonvoice_projection(
    nonvoice_rows: Sequence[Mapping[str, object]],
    runtime_rows: Sequence[Mapping[str, object]],
) -> None:
    if any(str(row.get("asset_type") or "") == "voice" for row in nonvoice_rows):
        raise ValueError("MediaArtifacts.nonvoice_rows contains voice")
    expected = Counter(
        _canonical_json_bytes(adapt_legacy_media_row(row)) for row in nonvoice_rows
    )
    actual = Counter(
        _canonical_json_bytes(dict(row))
        for row in runtime_rows
        if row.get("binding_status") == BindingStatus.NOT_APPLICABLE.value
    )
    if expected != actual:
        raise ValueError("runtime nonvoice projection multiset drift")


def _validate_relative_artifact_path(value: object, field: str) -> str:
    text = str(value or "")
    candidate = Path(text)
    if (
        not text
        or candidate.is_absolute()
        or "\\" in text
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(f"runtime voice {field} is unsafe")
    return text


def _validate_isolated_paths(paths: EvbBuildPaths) -> None:
    if paths.build_root.name == "dev":
        raise ValueError("dev artifact writes are forbidden")
    if paths.build_root.exists():
        raise FileExistsError(f"isolated build root already exists: {paths.build_root}")
    for path in paths.all_paths():
        try:
            path.resolve().relative_to(paths.build_root.resolve())
        except ValueError as error:
            raise ValueError("artifact path escapes isolated build root") from error


def _valid_sha1(value: object, field: str) -> str:
    text = str(value or "")
    if not _SHA1_RE.fullmatch(text):
        raise ValueError(f"{field} must be a full SHA-1")
    return text.lower()


def _valid_sha256(value: object, field: str) -> str:
    text = str(value or "")
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{field} must be a full SHA-256")
    return text.lower()


def _validated_public_base_url(value: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
        _port = parsed.port
        hostname = parsed.hostname
    except ValueError as error:
        raise ValueError("public_base_url must be a safe HTTP(S) base URL") from error
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
        raise ValueError("public_base_url must be a safe HTTP(S) base URL")
    _validate_public_hostname(hostname)
    path = quote(parsed.path, safe="/%")
    return urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def _validate_public_hostname(hostname: str) -> None:
    if hostname == "localhost":
        return
    try:
        ipaddress.ip_address(hostname)
        return
    except ValueError:
        pass
    labels = hostname.split(".")
    if any(
        not label
        or len(label) > 63
        or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    ):
        raise ValueError("public_base_url has an invalid hostname")


def _validated_bucket_name(value: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}", text):
        raise ValueError("bucket_name is unsafe")
    return text


def _public_media_url(public_base_url: str, bucket_name: str, object_key: str) -> str:
    key = str(object_key or "")
    if not key or "\\" in key or any(part in {"", ".", ".."} for part in key.split("/")):
        raise ValueError("exact object_key is unsafe for public URL construction")
    return f"{public_base_url}/{quote(bucket_name, safe='')}/{quote(key, safe='/')}"


def _runtime_sort_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("media_id") or ""),
        str(row.get("binding_key") or ""),
        str(row.get("child_id") or ""),
        str(row.get("asset_type") or ""),
    )


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Mapping[str, object]]) -> bytes:
    return b"".join(_canonical_json_bytes(dict(row)) for row in rows)


def _write_prepared_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
