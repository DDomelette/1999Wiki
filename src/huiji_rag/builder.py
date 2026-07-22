"""Compatibility facade for the corpus builder and diagnostic EVB workflow."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.huiji_rag.artifacts import (
    INTERNAL_MEDIA_ASSET_V2_FIELDS,
    MEDIA_ASSET_V2_FIELDS,
    build_entity_name_directory,
    build_entity_name_exclusions,
    build_runtime_media_projection,
    write_media_artifacts,
)
from src.huiji_rag.diagnostics import classify_binding_conflicts
from src.huiji_rag.io import evb_build_paths
from src.huiji_rag.models import (
    BindingRecord,
    BuildRequest,
    BuildResult,
    ChildBlock,
    EvbBuildPaths,
    MediaAsset,
    MediaArtifacts,
    ParentBlock,
    ResourceRow,
    VoiceSourceRow,
)
from src.huiji_rag.normalizer import validate_safe_id
from src.huiji_rag.minio_strict import (
    MediaOperationAuthority,
    ObjectInventory,
    StrictObjectRequest,
)
from src.huiji_rag.build.contracts import VoiceBindingInput
from src.huiji_rag.build.orchestrator import HuijiCorpusBuilder
from src.huiji_rag.build.voice_stage import VoiceBindingStage


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_BINDING_ID_RE = re.compile(r"binding:sha256:[0-9a-f]{64}\Z")
_RESOURCE_ID_RE = re.compile(r"resource:sha256:[0-9a-f]{64}\Z")
_MEDIA_ID_RE = re.compile(r"media:sha1:[0-9a-f]{40}\Z")
_MEDIA_NAME_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


@dataclass(frozen=True)
class _ArtifactFixture:
    public_base_url: str
    bucket_name: str
    parent_rows: tuple[ParentBlock, ...]
    child_rows: tuple[ChildBlock, ...]
    nonvoice_rows: tuple[MediaAsset, ...]
    voice_source_rows: tuple[VoiceSourceRow, ...]
    resource_rows: tuple[ResourceRow, ...]

    @classmethod
    def from_json(cls, payload: Mapping[str, object]) -> "_ArtifactFixture":
        if payload.get("schema_version") != "evb.artifact-fixture/v1":
            raise ValueError("artifact fixture has an unsupported schema version")
        return cls(
            public_base_url=str(payload.get("public_base_url") or ""),
            bucket_name=str(payload.get("bucket_name") or ""),
            parent_rows=tuple(
                ParentBlock.from_json(row) for row in _fixture_rows(payload, "parent_rows")
            ),
            child_rows=tuple(
                ChildBlock.from_json(row) for row in _fixture_rows(payload, "child_rows")
            ),
            nonvoice_rows=tuple(
                MediaAsset.from_json(row) for row in _fixture_rows(payload, "nonvoice_rows")
            ),
            voice_source_rows=tuple(
                VoiceSourceRow.from_json(row)
                for row in _fixture_rows(payload, "voice_source_rows")
            ),
            resource_rows=tuple(
                ResourceRow.from_json(row) for row in _fixture_rows(payload, "resource_rows")
            ),
        )


@dataclass(frozen=True)
class StrictObjectRequestResolution:
    all_requests: tuple[StrictObjectRequest, ...]
    missing_requests: tuple[StrictObjectRequest, ...]
    candidate_unique_object_count: int
    missing_binding_count: int
    same_hash_count: int
    missing_remote_count: int
    hash_mismatch_count: int
    orphan_remote_count: int
    missing_authority_counts: tuple[tuple[str, int], ...]
    ordered_missing_object_keys_sha256: str

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "huiji.v3-minio-request-resolution/v1",
            "candidate_unique_object_count": self.candidate_unique_object_count,
            "missing_binding_count": self.missing_binding_count,
            "same_hash_count": self.same_hash_count,
            "missing_remote_count": self.missing_remote_count,
            "hash_mismatch_count": self.hash_mismatch_count,
            "orphan_remote_count": self.orphan_remote_count,
            "missing_authority_counts": dict(self.missing_authority_counts),
            "ordered_missing_object_keys_sha256": self.ordered_missing_object_keys_sha256,
            "all_request_count": len(self.all_requests),
            "missing_request_count": len(self.missing_requests),
        }


def _fixture_rows(payload: Mapping[str, object], field: str) -> tuple[dict[str, Any], ...]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"artifact fixture {field} must be a list of objects")
    return tuple(dict(row) for row in value)


def assemble_media_artifacts(
    parent_rows: Sequence[Mapping[str, object]],
    child_rows: Sequence[Mapping[str, object]],
    nonvoice_rows: Sequence[Mapping[str, object]],
    binding_rows: Sequence[BindingRecord],
    schema: Mapping[str, object],
    manifest_inputs: Mapping[str, object],
    public_base_url: str,
    bucket_name: str,
) -> MediaArtifacts:
    """Apply Task 3 statuses and canonical entity identity before artifact writing."""
    result = classify_binding_conflicts(binding_rows)
    effective_rows = tuple(
        replace(
            row,
            status=result.status_by_id[row.source_id],
            binding_status=result.status_by_id[row.source_id],
            quality_flags=result.quality_flags_by_id[row.source_id],
        )
        for row in binding_rows
    )
    entity_names = build_entity_name_directory(parent_rows)
    exclusions = build_entity_name_exclusions(effective_rows, entity_names)
    runtime_rows = tuple(
        build_runtime_media_projection(
            nonvoice_rows,
            effective_rows,
            entity_names,
            public_base_url,
            bucket_name,
        )
    )
    return MediaArtifacts(
        binding_rows=effective_rows,
        runtime_rows=runtime_rows,
        schema=schema,
        manifest_inputs={
            **manifest_inputs,
            "public_base_url": public_base_url,
            "bucket_name": bucket_name,
        },
        nonvoice_rows=nonvoice_rows,
        entity_name_exclusions=exclusions,
        parent_rows=parent_rows,
        child_rows=child_rows,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_expected_sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _verified_evidence_file(path: Path, expected_sha256: str, field: str) -> tuple[Path, str]:
    expected = _validate_expected_sha256(expected_sha256, field)
    resolved = Path(path).resolve()
    if resolved.suffix.lower() == ".pyc":
        raise ValueError(f"{field} must not reference bytecode")
    if not resolved.is_file():
        raise FileNotFoundError(f"{field} does not exist: {resolved}")
    actual = _file_sha256(resolved)
    if actual != expected:
        raise ValueError(f"{field} SHA-256 does not match expected value")
    return resolved, actual


def _load_json_object(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{field} must contain JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return value


def _legacy_strict_object_requests_from_build_manifest(
    build_path: Path,
    build: Mapping[str, object],
    inventory: ObjectInventory,
    source_root: Path,
) -> tuple[StrictObjectRequest, ...]:
    relative_manifest = build.get("media_artifact_manifest")
    if not isinstance(relative_manifest, str) or not relative_manifest:
        raise ValueError("build manifest does not declare a media artifact manifest")
    artifact_manifest_path = (build_path.parent / relative_manifest).resolve()
    try:
        artifact_manifest_path.relative_to(build_path.parent)
    except ValueError as error:
        raise ValueError("media artifact manifest escapes the build root") from error
    artifact_manifest = _load_json_object(artifact_manifest_path, "media artifact manifest")
    file_paths = artifact_manifest.get("file_paths")
    file_hashes = artifact_manifest.get("file_sha256")
    if not isinstance(file_paths, dict) or not isinstance(file_hashes, dict):
        raise ValueError("media artifact manifest lacks pinned file paths")
    runtime_rel = file_paths.get("media_assets_v2")
    runtime_hash = file_hashes.get("media_assets_v2")
    if not isinstance(runtime_rel, str) or not isinstance(runtime_hash, str):
        raise ValueError("media artifact manifest lacks pinned runtime media")
    runtime_path = (artifact_manifest_path.parent.parent / runtime_rel).resolve()
    _verified_evidence_file(runtime_path, runtime_hash, "runtime media artifact")

    resolved_source_root = Path(source_root).resolve()
    existing = {item.object_key: item for item in inventory.objects}
    requests: list[StrictObjectRequest] = []
    for line_number, line in enumerate(runtime_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"runtime media row {line_number} is not an object")
        if row.get("asset_type") != "voice" or row.get("binding_status") != "exact":
            continue
        sha1 = str(row.get("sha1") or row.get("source_sha1") or "")
        sha256 = str(row.get("content_sha256") or "")
        object_key = str(row.get("object_key") or "")
        local_relpath = str(row.get("local_relpath") or "")
        relative_source = Path(local_relpath)
        if relative_source.is_absolute() or ".." in relative_source.parts:
            raise ValueError("local media source escapes configured raw root")
        local_path = (resolved_source_root / relative_source).resolve()
        try:
            local_path.relative_to(resolved_source_root)
        except ValueError as error:
            raise ValueError("local media source escapes configured raw root") from error
        request = StrictObjectRequest(
            bucket=inventory.bucket,
            object_key=object_key,
            local_path=local_path,
            sha1=sha1,
            sha256=sha256,
            size=local_path.stat().st_size,
            content_type=str(row.get("mime") or "audio/mpeg"),
            asset_type="voice",
            suffix=Path(str(row.get("filename") or ".mp3")).suffix.lower() or ".mp3",
        )
        remote = existing.get(object_key)
        if remote is not None:
            if (remote.sha1, remote.sha256, remote.size) != (request.sha1, request.sha256, request.size):
                raise ValueError(f"existing MinIO object hash mismatch: {object_key}")
        requests.append(request)
    return tuple(sorted(requests, key=lambda item: (item.bucket, item.object_key)))


def _required_text(row: Mapping[str, object], field: str, label: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} {field} is required")
    return value


def _load_v3_artifact_rows(
    build_path: Path,
    build: Mapping[str, object],
    *,
    relative_path: str,
    schema_version: str,
) -> tuple[dict[str, Any], ...]:
    raw_artifacts = build.get("artifacts")
    if not isinstance(raw_artifacts, list) or any(
        not isinstance(item, dict) for item in raw_artifacts
    ):
        raise ValueError("v3 build manifest artifacts must be a list of objects")
    artifact_paths = [str(item.get("relative_path") or "") for item in raw_artifacts]
    if any(not path for path in artifact_paths) or len(set(artifact_paths)) != len(
        artifact_paths
    ):
        raise ValueError("v3 build manifest contains missing or duplicate artifact paths")
    matches = [
        item for item in raw_artifacts if item.get("relative_path") == relative_path
    ]
    if len(matches) != 1:
        raise ValueError(f"v3 build manifest must pin exactly one {relative_path}")
    entry = matches[0]
    if entry.get("schema_version") != schema_version:
        raise ValueError(f"v3 artifact schema mismatch: {relative_path}")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("v3 artifact path escapes the candidate root")
    artifact_path = (build_path.parent / relative).resolve()
    try:
        artifact_path.relative_to(build_path.parent)
    except ValueError as error:
        raise ValueError("v3 artifact path escapes the candidate root") from error
    _, actual_sha256 = _verified_evidence_file(
        artifact_path,
        str(entry.get("sha256") or ""),
        f"v3 artifact {relative_path}",
    )
    if actual_sha256 != entry.get("sha256"):
        raise ValueError(f"v3 artifact SHA-256 mismatch: {relative_path}")
    declared_size = entry.get("size")
    if isinstance(declared_size, bool) or not isinstance(declared_size, int):
        raise ValueError(f"v3 artifact size is invalid: {relative_path}")
    if artifact_path.stat().st_size != declared_size:
        raise ValueError(f"v3 artifact size mismatch: {relative_path}")
    declared_rows = entry.get("row_count")
    if isinstance(declared_rows, bool) or not isinstance(declared_rows, int):
        raise ValueError(f"v3 artifact row count is invalid: {relative_path}")

    rows: list[dict[str, Any]] = []
    with artifact_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(
                    f"v3 artifact contains a blank row: {relative_path}:{line_number}"
                )
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"v3 artifact row is not JSON: {relative_path}:{line_number}"
                ) from error
            if not isinstance(value, dict):
                raise ValueError(
                    f"v3 artifact row is not an object: {relative_path}:{line_number}"
                )
            rows.append(value)
    if len(rows) != declared_rows:
        raise ValueError(f"v3 artifact row count mismatch: {relative_path}")
    return tuple(rows)


def _expected_v3_binding_id(row: Mapping[str, object]) -> str:
    identity = [
        "evb.media-binding/v1",
        _required_text(row, "owner_entity_id", "runtime media row"),
        _required_text(row, "owner_page_id", "runtime media row"),
        _required_text(row, "parent_id", "runtime media row"),
        _required_text(row, "child_id", "runtime media row"),
        _required_text(row, "section", "runtime media row"),
        _required_text(row, "media_role", "runtime media row"),
        str(row.get("variant") or ""),
        str(row.get("skin_id") or ""),
        str(row.get("event_name") or ""),
        str(row.get("language") or ""),
        _required_text(row, "source_binding_token", "runtime media row"),
        _required_text(row, "resource_id", "runtime media row"),
    ]
    encoded = json.dumps(
        identity, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return "binding:sha256:" + hashlib.sha256(encoded).hexdigest()


def _validated_v3_runtime_row(row: Mapping[str, object]) -> dict[str, object]:
    if row.get("artifact_schema_version") != "evb.media-asset/v3":
        raise ValueError("runtime media row has an unsupported v3 schema")
    binding_id = _required_text(row, "binding_id", "runtime media row")
    resource_id = _required_text(row, "resource_id", "runtime media row")
    media_id = _required_text(row, "media_id", "runtime media row")
    sha1 = _required_text(row, "sha1", "runtime media row")
    sha256 = _required_text(row, "content_sha256", "runtime media row")
    if _BINDING_ID_RE.fullmatch(binding_id) is None:
        raise ValueError("runtime media binding_id is not canonical")
    if _RESOURCE_ID_RE.fullmatch(resource_id) is None or resource_id != f"resource:sha256:{sha256}":
        raise ValueError("runtime media resource_id does not match content SHA-256")
    if _MEDIA_ID_RE.fullmatch(media_id) is None or media_id != f"media:sha1:{sha1}":
        raise ValueError("runtime media media_id does not match SHA-1")
    if _SHA1_RE.fullmatch(sha1) is None or _SHA256_RE.fullmatch(sha256) is None:
        raise ValueError("runtime media content hashes are not canonical")
    if binding_id != _expected_v3_binding_id(row):
        raise ValueError("runtime media binding_id does not match binding identity")
    source_sha1 = row.get("source_sha1")
    if source_sha1 not in (None, "", sha1):
        raise ValueError("runtime media source_sha1 differs from SHA-1")

    asset_type = _required_text(row, "asset_type", "runtime media row")
    media_role = _required_text(row, "media_role", "runtime media row")
    binding_status = _required_text(row, "binding_status", "runtime media row")
    mime = _required_text(row, "mime", "runtime media row")
    filename = _required_text(row, "filename", "runtime media row")
    object_key = _required_text(row, "object_key", "runtime media row")
    if _MEDIA_NAME_RE.fullmatch(asset_type) is None or _MEDIA_NAME_RE.fullmatch(media_role) is None:
        raise ValueError("runtime media type or role is invalid")
    if binding_status not in {"exact", "not_applicable"}:
        raise ValueError(f"runtime media binding status is not upload-safe: {binding_status}")
    suffix = Path(filename).suffix.lower()
    if not suffix or Path(object_key).suffix.lower() != suffix:
        raise ValueError("runtime media filename and object-key suffix differ")
    expected_key = f"reverse1999/{asset_type}/{sha1[:2]}/{sha1}{suffix}"
    if object_key != expected_key:
        raise ValueError("runtime media object key is not derived from SHA-1")
    size = row.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError("runtime media size is invalid")
    if not isinstance(row.get("is_available"), bool):
        raise ValueError("runtime media is_available must be boolean")
    return {
        **dict(row),
        "binding_id": binding_id,
        "resource_id": resource_id,
        "sha1": sha1,
        "content_sha256": sha256,
        "asset_type": asset_type,
        "media_role": media_role,
        "binding_status": binding_status,
        "mime": mime,
        "suffix": suffix,
        "object_key": object_key,
        "size": size,
    }


def _validated_v3_binding_row(
    row: Mapping[str, object], source_root: Path
) -> dict[str, object]:
    if row.get("schema_version") != "huiji.media-binding-inventory/v3":
        raise ValueError("binding inventory row has an unsupported v3 schema")
    for field, pattern in (
        ("binding_id", _BINDING_ID_RE),
        ("resource_id", _RESOURCE_ID_RE),
        ("sha1", _SHA1_RE),
        ("content_sha256", _SHA256_RE),
    ):
        if pattern.fullmatch(_required_text(row, field, "binding inventory row")) is None:
            raise ValueError(f"binding inventory {field} is not canonical")
    for field in (
        "owner_entity_id",
        "owner_page_id",
        "parent_id",
        "child_id",
        "media_role",
        "source_binding_token",
        "object_key",
    ):
        _required_text(row, field, "binding inventory row")
    size = row.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError("binding inventory size is invalid")
    local_relpath = _required_text(row, "local_relpath", "binding inventory row")
    relative_source = Path(local_relpath)
    if relative_source.is_absolute() or ".." in relative_source.parts:
        raise ValueError("local media source escapes configured raw root")
    local_path = (source_root / relative_source).resolve()
    try:
        local_path.relative_to(source_root)
    except ValueError as error:
        raise ValueError("local media source escapes configured raw root") from error
    return {**dict(row), "size": size, "local_path": local_path}


def _validate_v3_blocker_closure(
    build: Mapping[str, object], missing_keys: set[str], missing_binding_count: int
) -> None:
    blockers = build.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise ValueError("v3 build manifest blockers must be a list of strings")
    if not missing_keys:
        if blockers:
            raise ValueError("v3 build blockers remain without missing MinIO objects")
        return
    unavailable_counts: list[int] = []
    blocker_keys: list[str] = []
    unexpected: list[str] = []
    for blocker in blockers:
        if blocker.startswith("media_unavailable:"):
            raw_count = blocker.removeprefix("media_unavailable:")
            if not raw_count.isdigit():
                unexpected.append(blocker)
            else:
                unavailable_counts.append(int(raw_count))
        elif blocker.startswith("minio_object_missing:"):
            blocker_keys.append(blocker.removeprefix("minio_object_missing:"))
        else:
            unexpected.append(blocker)
    if unexpected:
        raise ValueError(f"v3 build has a non-MinIO blocker: {unexpected[0]}")
    if unavailable_counts != [missing_binding_count]:
        raise ValueError("v3 media_unavailable blocker count does not close")
    if len(blocker_keys) != len(set(blocker_keys)) or set(blocker_keys) != missing_keys:
        raise ValueError("v3 minio_object_missing blocker set does not close")


def _ordered_key_hash(keys: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(keys):
        digest.update(key.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validate_v3_local_bytes(
    path: Path, *, expected_sha1: str, expected_sha256: str, expected_size: int
) -> None:
    resolved = Path(path)
    if not resolved.is_file():
        raise ValueError(f"missing local media source: {resolved}")
    if resolved.stat().st_size != expected_size:
        raise ValueError(f"local media source size mismatch: {resolved}")
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha1.update(chunk)
            sha256.update(chunk)
    if sha1.hexdigest() != expected_sha1 or sha256.hexdigest() != expected_sha256:
        raise ValueError(f"local media source hash mismatch: {resolved}")


def resolve_strict_object_requests_from_build_manifest(
    build_manifest_path: Path,
    inventory: ObjectInventory,
    source_root: Path,
    *,
    allowed_media_authorities: Sequence[MediaOperationAuthority],
) -> StrictObjectRequestResolution:
    build_path = Path(build_manifest_path).resolve()
    build = _load_json_object(build_path, "build manifest")
    if (
        build.get("schema_version") != "huiji.corpus-build/v2"
        or build.get("artifact_schema_version") != "evb.media-asset/v3"
    ):
        raise ValueError("strict v3 resolution requires a corpus media v3 build manifest")
    authorities = tuple(sorted(set(allowed_media_authorities)))
    if not authorities:
        raise ValueError("v3 strict resolution requires an explicit media authority")

    runtime_rows = _load_v3_artifact_rows(
        build_path,
        build,
        relative_path="runtime/media_assets.v3.jsonl",
        schema_version="evb.media-asset/v3",
    )
    binding_rows = _load_v3_artifact_rows(
        build_path,
        build,
        relative_path="diagnostic/binding_inventory.v3.jsonl",
        schema_version="huiji.media-binding-inventory/v3",
    )
    runtime = tuple(_validated_v3_runtime_row(row) for row in runtime_rows)
    resolved_source_root = Path(source_root).resolve()
    bindings = tuple(
        _validated_v3_binding_row(row, resolved_source_root) for row in binding_rows
    )
    runtime_by_id = {str(row["binding_id"]): row for row in runtime}
    binding_by_id = {str(row["binding_id"]): row for row in bindings}
    if len(runtime_by_id) != len(runtime):
        raise ValueError("runtime media contains duplicate binding_id")
    if len(binding_by_id) != len(bindings):
        raise ValueError("binding inventory contains duplicate binding_id")
    if set(runtime_by_id) != set(binding_by_id):
        raise ValueError("runtime media and binding inventory binding_id sets differ")

    overlap_fields = (
        "binding_id",
        "resource_id",
        "owner_entity_id",
        "owner_page_id",
        "parent_id",
        "child_id",
        "media_role",
        "source_binding_token",
        "object_key",
        "sha1",
        "content_sha256",
        "size",
    )
    groups: dict[str, dict[str, object]] = {}
    for binding_id in sorted(runtime_by_id):
        runtime_row = runtime_by_id[binding_id]
        binding_row = binding_by_id[binding_id]
        if any(runtime_row.get(field) != binding_row.get(field) for field in overlap_fields):
            raise ValueError(f"binding physical identity differs across artifacts: {binding_id}")
        object_key = str(runtime_row["object_key"])
        physical_identity = (
            runtime_row["resource_id"],
            runtime_row["sha1"],
            runtime_row["content_sha256"],
            runtime_row["size"],
            runtime_row["asset_type"],
            runtime_row["mime"],
            runtime_row["suffix"],
        )
        group = groups.get(object_key)
        if group is None:
            group = {
                "physical_identity": physical_identity,
                "rows": [],
                "local_paths": set(),
            }
            groups[object_key] = group
        elif group["physical_identity"] != physical_identity:
            raise ValueError(f"object physical identity conflicts across bindings: {object_key}")
        group_rows = group["rows"]
        group_paths = group["local_paths"]
        assert isinstance(group_rows, list) and isinstance(group_paths, set)
        group_rows.append(runtime_row)
        group_paths.add(binding_row["local_path"])

    remote_by_key = {item.object_key: item for item in inventory.objects}
    if len(remote_by_key) != len(inventory.objects):
        raise ValueError("MinIO inventory contains duplicate object keys")
    all_requests: list[StrictObjectRequest] = []
    missing_requests: list[StrictObjectRequest] = []
    missing_keys: set[str] = set()
    missing_binding_count = 0
    same_hash_count = 0
    authority_counts: dict[str, int] = {}
    authority_set = set(authorities)

    for object_key, group in sorted(groups.items()):
        rows = group["rows"]
        local_paths = group["local_paths"]
        physical = group["physical_identity"]
        assert isinstance(rows, list) and isinstance(local_paths, set)
        resource_id, sha1, sha256, size, asset_type, mime, suffix = physical
        remote = remote_by_key.get(object_key)
        is_missing = remote is None
        if remote is not None:
            if (remote.sha1, remote.sha256, remote.size) != (sha1, sha256, size):
                raise ValueError(f"existing MinIO object hash mismatch: {object_key}")
            same_hash_count += 1
        if any(bool(row["is_available"]) == is_missing for row in rows):
            raise ValueError(f"candidate media availability drifted: {object_key}")

        selected_path = min(local_paths, key=lambda path: Path(path).as_posix())
        request = StrictObjectRequest(
            bucket=inventory.bucket,
            object_key=object_key,
            local_path=Path(selected_path),
            sha1=str(sha1),
            sha256=str(sha256),
            size=int(size),
            content_type=str(mime),
            asset_type=str(asset_type),
            suffix=str(suffix),
        )
        all_requests.append(request)
        if not is_missing:
            continue

        row_authorities = {
            MediaOperationAuthority(
                asset_type=str(row["asset_type"]),
                media_role=str(row["media_role"]),
                binding_status=str(row["binding_status"]),
                mime=str(row["mime"]),
                suffix=str(row["suffix"]),
            )
            for row in rows
        }
        if not row_authorities.issubset(authority_set):
            raise ValueError(f"missing object is outside approved media authority: {object_key}")
        if len(row_authorities) != 1:
            raise ValueError(f"missing object has ambiguous media authority: {object_key}")
        for local_path in sorted(local_paths, key=lambda path: Path(path).as_posix()):
            _validate_v3_local_bytes(
                Path(local_path),
                expected_sha1=str(sha1),
                expected_sha256=str(sha256),
                expected_size=int(size),
            )
        authority = next(iter(row_authorities))
        label = f"{authority.asset_type}/{authority.media_role}"
        authority_counts[label] = authority_counts.get(label, 0) + 1
        missing_binding_count += len(rows)
        missing_keys.add(object_key)
        missing_requests.append(request)

    _validate_v3_blocker_closure(build, missing_keys, missing_binding_count)
    candidate_keys = set(groups)
    orphan_count = len(set(remote_by_key) - candidate_keys)
    return StrictObjectRequestResolution(
        all_requests=tuple(all_requests),
        missing_requests=tuple(missing_requests),
        candidate_unique_object_count=len(candidate_keys),
        missing_binding_count=missing_binding_count,
        same_hash_count=same_hash_count,
        missing_remote_count=len(missing_keys),
        hash_mismatch_count=0,
        orphan_remote_count=orphan_count,
        missing_authority_counts=tuple(sorted(authority_counts.items())),
        ordered_missing_object_keys_sha256=_ordered_key_hash(tuple(missing_keys)),
    )


def strict_object_requests_from_build_manifest(
    build_manifest_path: Path,
    inventory: ObjectInventory,
    source_root: Path,
    *,
    allowed_media_authorities: Sequence[MediaOperationAuthority] = (),
) -> tuple[StrictObjectRequest, ...]:
    """Derive strict physical-object requests from an explicitly versioned build."""
    build_path = Path(build_manifest_path).resolve()
    build = _load_json_object(build_path, "build manifest")
    if (
        build.get("schema_version") == "huiji.corpus-build/v2"
        and build.get("artifact_schema_version") == "evb.media-asset/v3"
    ):
        return resolve_strict_object_requests_from_build_manifest(
            build_path,
            inventory,
            source_root,
            allowed_media_authorities=allowed_media_authorities,
        ).all_requests
    return _legacy_strict_object_requests_from_build_manifest(
        build_path, build, inventory, source_root
    )


def _verify_bundle_sidecars(
    bundle_path: Path, bundle: dict[str, Any], baseline_sha256: str
) -> tuple[dict[str, str], str, Mapping[str, Path]]:
    if bundle.get("schema_version") != "evb.preflight-bundle/v1":
        raise ValueError("preflight bundle has an unsupported schema version")
    if bundle.get("baseline_sha256") != baseline_sha256:
        raise ValueError("preflight bundle baseline SHA-256 is stale or reused")
    raw_sidecars = bundle.get("sidecars")
    if not isinstance(raw_sidecars, list) or not raw_sidecars:
        raise ValueError("preflight bundle must declare sidecars")

    root = bundle_path.parent.resolve()
    sidecars: dict[str, str] = {}
    sidecar_paths: dict[str, Path] = {}
    paths: set[Path] = set()
    hashes: set[str] = set()
    dev_projection_sha256: str | None = None
    for item in raw_sidecars:
        if not isinstance(item, dict):
            raise ValueError("preflight bundle sidecar must be an object")
        relative_path = item.get("path")
        expected_sha256 = item.get("sha256")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("preflight bundle sidecar path is required")
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("preflight bundle sidecar path escapes bundle root")
        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError("preflight bundle sidecar path escapes bundle root") from error
        if resolved in paths:
            raise ValueError("preflight bundle reuses a sidecar path")
        verified_path, actual = _verified_evidence_file(
            resolved, str(expected_sha256 or ""), "preflight bundle sidecar"
        )
        if actual in hashes or actual == baseline_sha256:
            raise ValueError("preflight bundle reuses evidence")
        paths.add(verified_path)
        hashes.add(actual)
        sidecars[verified_path.name] = actual
        sidecar_paths[verified_path.name] = verified_path
        if verified_path.name == "dev_inventory.v1.json":
            inventory = _load_json_object(verified_path, "dev inventory sidecar")
            projection = inventory.get("canonical_non_media_projection_sha256")
            dev_projection_sha256 = _validate_expected_sha256(
                projection, "dev inventory canonical projection"
            )
    if dev_projection_sha256 is None:
        raise ValueError("preflight bundle must declare dev_inventory.v1.json with a canonical projection")
    return sidecars, dev_projection_sha256, sidecar_paths


def _assert_report_root(report_root: Path | None, paths: EvbBuildPaths) -> Path:
    target = (report_root or paths.build_root).resolve()
    try:
        target.relative_to(paths.build_root)
    except ValueError as error:
        raise ValueError("report_root must be contained by build_root") from error
    return target


class EvbBuilder:
    """Build diagnostic EVB evidence; full corpus builds use HuijiCorpusBuilder."""

    def build_offline(self, request: BuildRequest) -> BuildResult:
        safe_version = validate_safe_id(request.build_version, "build_version")
        if safe_version == "dev":
            raise ValueError("build_version dev is not permitted for EVB builds")
        output_root = Path(request.output_root).resolve()
        paths = evb_build_paths(output_root, safe_version)
        report_root = _assert_report_root(request.report_root, paths)

        baseline_path, baseline_sha256 = _verified_evidence_file(
            request.baseline_path, request.expected_baseline_sha256, "baseline"
        )
        bundle_path, bundle_sha256 = _verified_evidence_file(
            request.preflight_bundle_path,
            request.expected_preflight_bundle_sha256,
            "preflight bundle",
        )
        if baseline_path == bundle_path:
            raise ValueError("baseline and preflight bundle evidence must be distinct")
        bundle = _load_json_object(bundle_path, "preflight bundle")
        sidecars, dev_projection_sha256, sidecar_paths = _verify_bundle_sidecars(
            bundle_path, bundle, baseline_sha256
        )

        if paths.build_root.exists():
            raise FileExistsError(f"isolated build root already exists: {paths.build_root}")

        manifest = {
            "schema_version": "evb.build-manifest/v1",
            "build_version": safe_version,
            "baseline_path": str(baseline_path),
            "baseline_sha256": baseline_sha256,
            "preflight_bundle_path": str(bundle_path),
            "preflight_bundle_sha256": bundle_sha256,
            "preflight_sidecars": sidecars,
            "canonical_non_media_projection_sha256": dev_projection_sha256,
            "dry_run": bool(request.dry_run),
        }
        report = {
            "schema_version": "evb.build-report/v1",
            "build_version": safe_version,
            "status": "dry_run" if request.dry_run else "offline_prepared",
            "baseline_sha256": baseline_sha256,
            "preflight_bundle_sha256": bundle_sha256,
        }

        artifact_fixture_path = sidecar_paths.get("artifact_fixture.v1.json")
        if artifact_fixture_path is not None and request.dry_run:
            fixture = _ArtifactFixture.from_json(
                _load_json_object(artifact_fixture_path, "artifact fixture sidecar")
            )
            voice_result = VoiceBindingStage().run(
                VoiceBindingInput(
                    source_rows=fixture.voice_source_rows,
                    resource_rows=fixture.resource_rows,
                )
            )
            binding_rows = voice_result.binding_rows
            media_artifacts = assemble_media_artifacts(
                parent_rows=tuple(row.to_json() for row in fixture.parent_rows),
                child_rows=tuple(row.to_json() for row in fixture.child_rows),
                nonvoice_rows=tuple(row.to_json() for row in fixture.nonvoice_rows),
                binding_rows=binding_rows,
                schema={
                    "schema_version": "evb.media-assets/v2",
                    "fields": list(MEDIA_ASSET_V2_FIELDS),
                    "internal_fields": list(INTERNAL_MEDIA_ASSET_V2_FIELDS),
                },
                manifest_inputs={
                    "build_version": safe_version,
                    "baseline_sha256": baseline_sha256,
                    "preflight_bundle_sha256": bundle_sha256,
                    "artifact_fixture_sha256": sidecars["artifact_fixture.v1.json"],
                    "canonical_non_media_projection_sha256": dev_projection_sha256,
                    "previous_build_version": "dev",
                },
                public_base_url=fixture.public_base_url,
                bucket_name=fixture.bucket_name,
            )
            artifact_manifest = write_media_artifacts(paths, media_artifacts)
            manifest["media_artifact_manifest"] = paths.media_manifest_v2.relative_to(
                paths.build_root
            ).as_posix()
            manifest["media_artifact_file_sha256"] = dict(artifact_manifest.file_sha256)
            report["media_artifact_runtime_status_counts"] = dict(
                artifact_manifest.runtime_status_counts
            )
        else:
            paths.build_root.mkdir(parents=True, exist_ok=False)
        report_root.mkdir(parents=True, exist_ok=True)
        paths.build_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report_path = report_root / "build_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return BuildResult(
            build_version=safe_version,
            build_root=paths.build_root,
            build_manifest=paths.build_manifest,
            build_report=report_path,
            baseline_sha256=baseline_sha256,
            preflight_bundle_sha256=bundle_sha256,
            dry_run=bool(request.dry_run),
        )
