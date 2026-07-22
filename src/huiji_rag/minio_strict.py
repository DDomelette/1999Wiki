"""Strictly additive, evidence-bound MinIO object creation for EVB builds."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Literal, Mapping, Sequence
from uuid import UUID, uuid4

import minio
from minio.error import S3Error


_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_OPERATION_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_MEDIA_AUTHORITY_NAME_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
_MEDIA_AUTHORITY_MIME_RE = re.compile(r"[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*\Z")
_MEDIA_AUTHORITY_SUFFIX_RE = re.compile(r"\.[a-z0-9]+\Z")
_MISSING_CODES = {"NoSuchKey", "NoSuchObject", "NotFound", "XMinioInvalidObjectName"}


class StrictMinioError(RuntimeError):
    """Base class for failures that must stop the strict upload sequence."""


class CapabilityUnavailable(StrictMinioError):
    pass


class ContentHashMismatch(StrictMinioError):
    pass


class PostCreateReadbackFailure(ContentHashMismatch):
    def __init__(self, message: str, evidence: "ObjectEvidence") -> None:
        super().__init__(message)
        self.evidence = evidence


class EvidenceAlreadyUsed(StrictMinioError):
    pass


class EvidenceMismatch(StrictMinioError):
    pass


class ApplicationAuditMissing(EvidenceMismatch):
    pass


class ConcurrencyConflict(StrictMinioError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_hash_without(value: Any, field: str) -> str:
    payload = _jsonable(value)
    if not isinstance(payload, dict):
        raise TypeError("canonical hash input must be an object")
    payload.pop(field, None)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def ordered_object_keys_sha256(keys: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(keys):
        digest.update(str(key).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _file_hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_hash(value: str, pattern: re.Pattern[str], field: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise EvidenceMismatch(f"{field} is not a lowercase canonical hash")
    return value


def _verify_file(path: Path, expected_sha256: str, field: str) -> Path:
    expected = _validate_hash(expected_sha256, _SHA256_RE, field)
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise EvidenceMismatch(f"{field} does not exist")
    if _file_hash(resolved, "sha256") != expected:
        raise EvidenceMismatch(f"{field} SHA-256 mismatch")
    return resolved


def _write_create_new(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _serialized_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class StrictObjectRequest:
    bucket: str
    object_key: str
    local_path: Path
    sha1: str
    sha256: str
    size: int
    content_type: str
    asset_type: str
    suffix: str


@dataclass(frozen=True, order=True)
class MediaOperationAuthority:
    asset_type: str
    media_role: str
    binding_status: str
    mime: str
    suffix: str

    def __post_init__(self) -> None:
        for field, value in (
            ("asset_type", self.asset_type),
            ("media_role", self.media_role),
            ("binding_status", self.binding_status),
        ):
            if _MEDIA_AUTHORITY_NAME_RE.fullmatch(value) is None:
                raise EvidenceMismatch(f"media authority {field} is invalid")
        if _MEDIA_AUTHORITY_MIME_RE.fullmatch(self.mime) is None:
            raise EvidenceMismatch("media authority MIME is invalid")
        if _MEDIA_AUTHORITY_SUFFIX_RE.fullmatch(self.suffix) is None:
            raise EvidenceMismatch("media authority suffix is invalid")

    @classmethod
    def from_token(cls, value: str) -> "MediaOperationAuthority":
        parts = str(value).split("|")
        if len(parts) != 5 or any(not part for part in parts):
            raise EvidenceMismatch("media authority token must have five pipe-delimited fields")
        return cls(*parts)

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> "MediaOperationAuthority":
        return cls(
            asset_type=str(value.get("asset_type") or ""),
            media_role=str(value.get("media_role") or ""),
            binding_status=str(value.get("binding_status") or ""),
            mime=str(value.get("mime") or ""),
            suffix=str(value.get("suffix") or ""),
        )

    def to_json(self) -> dict[str, str]:
        return {
            "asset_type": self.asset_type,
            "media_role": self.media_role,
            "binding_status": self.binding_status,
            "mime": self.mime,
            "suffix": self.suffix,
        }


@dataclass(frozen=True)
class CapabilityEvidence:
    conditional_create_supported: bool
    application_audit_supported: bool
    durable_replace_supported: bool
    details: tuple[str, ...]
    checked_at_utc: str

    def require_conditional_create_and_app_audit(self) -> None:
        if not self.conditional_create_supported or not self.application_audit_supported:
            raise CapabilityUnavailable("conditional create and application audit are required")


@dataclass(frozen=True)
class MinioOperationPreflight:
    schema_version: str
    build_manifest_sha256: str
    baseline_sha256: str
    before_inventory_sha256: str
    before_inventory_object_sha256: str
    approved_missing_object_keys_sha256: str
    approved_missing_remote_count: int
    approved_missing_role_counts: tuple[tuple[str, int], ...]
    allowed_media_authorities: tuple[MediaOperationAuthority, ...]
    reconciliation_sha256: str


@dataclass(frozen=True, order=True)
class InventoryObject:
    object_key: str
    version_id: str | None
    etag: str
    sha1: str
    sha256: str
    size: int
    audit_event_id: str | None = None
    application_operation_id: str | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> "InventoryObject":
        return cls(
            object_key=str(value["object_key"]),
            version_id=None if value.get("version_id") is None else str(value["version_id"]),
            etag=str(value.get("etag") or ""),
            sha1=str(value.get("sha1") or ""),
            sha256=str(value.get("sha256") or ""),
            size=int(value.get("size", -1)),
            audit_event_id=(
                None
                if value.get("audit_event_id") is None
                else str(value["audit_event_id"])
            ),
            application_operation_id=(
                None
                if value.get("application_operation_id") is None
                else str(value["application_operation_id"])
            ),
        )


@dataclass(frozen=True)
class ObjectInventory:
    schema_version: str
    bucket: str
    prefix: str
    objects: tuple[InventoryObject, ...]
    captured_at_utc: str
    inventory_sha256: str
    bucket_policy_summary: str = ""

    @classmethod
    def create(
        cls,
        bucket: str,
        prefix: str,
        objects: Sequence[InventoryObject],
        captured_at_utc: str | None = None,
        bucket_policy_summary: str = "",
    ) -> "ObjectInventory":
        inventory = cls(
            schema_version="evb.minio-inventory/v1",
            bucket=bucket,
            prefix=prefix.rstrip("/"),
            objects=tuple(sorted(objects, key=lambda item: item.object_key)),
            captured_at_utc=captured_at_utc or _utc_now(),
            inventory_sha256="",
            bucket_policy_summary=bucket_policy_summary,
        )
        return replace(
            inventory,
            inventory_sha256=canonical_hash_without(inventory, "inventory_sha256"),
        )

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> "ObjectInventory":
        raw_objects = value.get("objects")
        if not isinstance(raw_objects, list):
            raise EvidenceMismatch("inventory objects must be a list")
        parsed_objects = tuple(InventoryObject.from_json(item) for item in raw_objects)
        keys = tuple(item.object_key for item in parsed_objects)
        if len(set(keys)) != len(keys):
            raise EvidenceMismatch("MinIO inventory contains duplicate object targets")
        if keys != tuple(sorted(keys)):
            raise EvidenceMismatch("MinIO inventory is not sorted")
        inventory = cls(
            schema_version=str(value.get("schema_version") or ""),
            bucket=str(value.get("bucket") or ""),
            prefix=str(value.get("prefix") or "").rstrip("/"),
            objects=parsed_objects,
            captured_at_utc=str(value.get("captured_at_utc") or ""),
            inventory_sha256=str(value.get("inventory_sha256") or ""),
            bucket_policy_summary=str(value.get("bucket_policy_summary") or ""),
        )
        if inventory.schema_version != "evb.minio-inventory/v1":
            raise EvidenceMismatch("unsupported MinIO inventory schema")
        if not (
            inventory.bucket_policy_summary == "absent"
            or (
                inventory.bucket_policy_summary.startswith("sha256:")
                and _SHA256_RE.fullmatch(
                    inventory.bucket_policy_summary.removeprefix("sha256:")
                )
            )
        ):
            raise EvidenceMismatch("MinIO inventory lacks a proven bucket policy summary")
        if any(not item.etag for item in inventory.objects):
            raise EvidenceMismatch("MinIO inventory contains an object with an empty ETag")
        expected = canonical_hash_without(inventory, "inventory_sha256")
        if inventory.inventory_sha256 != expected:
            raise EvidenceMismatch("MinIO inventory internal hash mismatch")
        return inventory

    def to_json(self) -> dict[str, object]:
        return _jsonable(self)

    @property
    def object_state_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_bytes(
                {
                    "bucket": self.bucket,
                    "prefix": self.prefix,
                    "bucket_policy_summary": self.bucket_policy_summary,
                    "objects": self.objects,
                }
            )
        ).hexdigest()


@dataclass(frozen=True)
class PlannedObject:
    bucket: str
    object_key: str
    sha1: str
    sha256: str
    size: int
    source_path: str
    content_type: str
    asset_type: str
    suffix: str
    disposition: Literal["conditional_create", "same_hash_skip"]
    before_version_id: str | None
    before_etag: str
    before_sha1: str | None
    before_sha256: str | None
    before_size: int | None

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> "PlannedObject":
        return cls(
            bucket=str(value["bucket"]), object_key=str(value["object_key"]),
            sha1=str(value["sha1"]), sha256=str(value["sha256"]), size=int(value["size"]),
            source_path=str(value["source_path"]), content_type=str(value["content_type"]),
            asset_type=str(value["asset_type"]), suffix=str(value["suffix"]),
            disposition=str(value.get("disposition") or "conditional_create"),
            before_version_id=(None if value.get("before_version_id") is None else str(value["before_version_id"])),
            before_etag=str(value.get("before_etag") or ""),
            before_sha1=None if value.get("before_sha1") is None else str(value["before_sha1"]),
            before_sha256=None if value.get("before_sha256") is None else str(value["before_sha256"]),
            before_size=None if value.get("before_size") is None else int(value["before_size"]),
        )


@dataclass(frozen=True)
class MinioOperationPlan:
    schema_version: str
    plan_id: str
    baseline_path: str
    baseline_sha256: str
    build_manifest_path: str
    build_manifest_sha256: str
    preflight_bundle_path: str
    preflight_bundle_sha256: str
    before_inventory_path: str
    before_inventory_sha256: str
    before_inventory_object_sha256: str
    bucket: str
    prefix: str
    source_root: str
    capability_evidence: CapabilityEvidence
    objects: tuple[PlannedObject, ...]
    object_set_sha256: str
    created_at_utc: str
    used_by_operation_id: str | None
    operation_plan_sha256: str

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> "MinioOperationPlan":
        objects = value.get("objects")
        if not isinstance(objects, list):
            raise EvidenceMismatch("operation plan objects must be a list")
        parsed_objects = tuple(PlannedObject.from_json(item) for item in objects)
        targets = tuple((item.bucket, item.object_key) for item in parsed_objects)
        if len(set(targets)) != len(targets):
            raise EvidenceMismatch("operation plan contains duplicate object targets")
        if targets != tuple(sorted(targets)):
            raise EvidenceMismatch("operation plan objects are not canonically sorted")
        plan = cls(
            schema_version=str(value.get("schema_version") or ""), plan_id=str(value.get("plan_id") or ""),
            baseline_path=str(value.get("baseline_path") or ""), baseline_sha256=str(value.get("baseline_sha256") or ""),
            build_manifest_path=str(value.get("build_manifest_path") or ""), build_manifest_sha256=str(value.get("build_manifest_sha256") or ""),
            preflight_bundle_path=str(value.get("preflight_bundle_path") or ""), preflight_bundle_sha256=str(value.get("preflight_bundle_sha256") or ""),
            before_inventory_path=str(value.get("before_inventory_path") or ""), before_inventory_sha256=str(value.get("before_inventory_sha256") or ""),
            before_inventory_object_sha256=str(value.get("before_inventory_object_sha256") or ""),
            bucket=str(value.get("bucket") or ""), prefix=str(value.get("prefix") or "").rstrip("/"),
            source_root=str(value.get("source_root") or ""),
            capability_evidence=CapabilityEvidence(
                conditional_create_supported=bool(dict(value.get("capability_evidence") or {}).get("conditional_create_supported")),
                application_audit_supported=bool(dict(value.get("capability_evidence") or {}).get("application_audit_supported")),
                durable_replace_supported=bool(dict(value.get("capability_evidence") or {}).get("durable_replace_supported")),
                details=tuple(str(item) for item in dict(value.get("capability_evidence") or {}).get("details", [])),
                checked_at_utc=str(dict(value.get("capability_evidence") or {}).get("checked_at_utc") or ""),
            ),
            objects=parsed_objects,
            object_set_sha256=str(value.get("object_set_sha256") or ""), created_at_utc=str(value.get("created_at_utc") or ""),
            used_by_operation_id=None if value.get("used_by_operation_id") is None else str(value["used_by_operation_id"]),
            operation_plan_sha256=str(value.get("operation_plan_sha256") or ""),
        )
        if plan.schema_version != "evb.minio-operation-plan/v1":
            raise EvidenceMismatch("unsupported MinIO operation plan schema")
        if plan.operation_plan_sha256 != canonical_hash_without(plan, "operation_plan_sha256"):
            raise EvidenceMismatch("MinIO operation plan internal hash mismatch")
        if plan.object_set_sha256 != hashlib.sha256(_canonical_bytes(plan.objects)).hexdigest():
            raise EvidenceMismatch("MinIO operation plan object-set hash mismatch")
        return plan

    def to_json(self) -> dict[str, object]:
        return _jsonable(self)


@dataclass(frozen=True)
class MinioPlanUseMarker:
    schema_version: str
    plan_path: str
    plan_sha256: str
    operation_id: str
    object_set_sha256: str
    claimed_at_utc: str
    marker_sha256: str


@dataclass(frozen=True)
class ObjectEvidence:
    status: str
    bucket: str
    object_key: str
    version_id: str | None
    etag: str
    server_request_id: str | None
    sha1_before: str | None
    sha256_before: str | None
    size_before: int | None
    sha1_after: str | None
    sha256_after: str | None
    size_after: int | None
    http_readback: bool
    operation_audit_id: str


@dataclass(frozen=True)
class UploadReport:
    schema_version: str
    operation_id: str
    status: str
    operation_plan_sha256: str
    before_inventory_sha256: str
    before_inventory_object_sha256: str
    current_inventory_sha256: str
    current_inventory_object_sha256: str
    after_inventory_sha256: str | None
    after_inventory_object_sha256: str | None
    after_inventory_capture_error_code: str | None
    after_inventory_capture_request_id: str | None
    objects: tuple[ObjectEvidence, ...]
    report_sha256: str

    def to_json(self) -> dict[str, object]:
        return _jsonable(self)


def attach_operation_evidence(
    evidence: ObjectEvidence, operation_id: str, version_id: str | None
) -> ObjectEvidence:
    if not operation_id:
        raise EvidenceMismatch("application operation/audit ID is mandatory")
    return replace(evidence, operation_audit_id=operation_id, version_id=version_id)


def _load_inventory(path: Path) -> ObjectInventory:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceMismatch("unable to read MinIO inventory") from error
    if not isinstance(payload, dict):
        raise EvidenceMismatch("MinIO inventory must be an object")
    return ObjectInventory.from_json(payload)


def load_object_inventory(path: Path) -> ObjectInventory:
    return _load_inventory(Path(path))


def local_capability_evidence(minio_client: object) -> CapabilityEvidence:
    version = str(getattr(minio, "__version__", ""))
    execute = getattr(minio_client, "_execute", None)
    supported = version == "7.2.20" and callable(execute)
    return CapabilityEvidence(
        conditional_create_supported=supported,
        application_audit_supported=supported,
        durable_replace_supported=False,
        details=(
            f"minio-sdk:{version or 'unknown'}",
            "private-execute:available" if callable(execute) else "private-execute:missing",
            "if-none-match-and-application-operation-id:required",
            "server-semantics-and-audit-correlation:requires-r05",
        ),
        checked_at_utc=_utc_now(),
    )


def load_operation_preflight_bundle(
    bundle_path: Path,
) -> tuple[MinioOperationPreflight, CapabilityEvidence]:
    resolved_bundle = Path(bundle_path).resolve()
    try:
        payload = json.loads(resolved_bundle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceMismatch("operation preflight bundle is not readable JSON") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != "evb.minio-operation-preflight/v1":
        raise EvidenceMismatch("unsupported operation preflight bundle")
    for field in (
        "build_manifest_sha256",
        "baseline_sha256",
        "before_inventory_sha256",
        "before_inventory_object_sha256",
        "approved_missing_object_keys_sha256",
    ):
        _validate_hash(str(payload.get(field) or ""), _SHA256_RE, f"preflight {field}")

    raw_authorities = payload.get("allowed_media_authorities")
    if not isinstance(raw_authorities, list) or any(
        not isinstance(item, dict) for item in raw_authorities
    ):
        raise EvidenceMismatch("operation preflight media authorities are malformed")
    authorities = tuple(MediaOperationAuthority.from_json(item) for item in raw_authorities)
    if not authorities or len(set(authorities)) != len(authorities):
        raise EvidenceMismatch("operation preflight media authorities are empty or duplicated")
    if authorities != tuple(sorted(authorities)):
        raise EvidenceMismatch("operation preflight media authorities are not canonical")

    raw_sidecars = payload.get("sidecars")
    if not isinstance(raw_sidecars, list) or any(
        not isinstance(item, dict) for item in raw_sidecars
    ):
        raise EvidenceMismatch("operation preflight sidecars are malformed")
    root = resolved_bundle.parent
    sidecars: dict[str, tuple[Path, str]] = {}
    seen_paths: set[Path] = set()
    seen_hashes: set[str] = set()
    for item in raw_sidecars:
        name = str(item.get("name") or "")
        relative = Path(str(item.get("path") or ""))
        expected = str(item.get("sha256") or "")
        if not name or relative.is_absolute() or ".." in relative.parts:
            raise EvidenceMismatch("operation preflight sidecar path escapes its bundle")
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise EvidenceMismatch("operation preflight sidecar path escapes its bundle") from error
        if name in sidecars or resolved in seen_paths:
            raise EvidenceMismatch("operation preflight reuses a sidecar name or path")
        _validate_hash(expected, _SHA256_RE, "operation preflight sidecar")
        if expected in seen_hashes:
            raise EvidenceMismatch("operation preflight reuses a sidecar hash")
        _verify_file(resolved, expected, f"operation preflight sidecar {name}")
        sidecars[name] = (resolved, expected)
        seen_paths.add(resolved)
        seen_hashes.add(expected)
    if set(sidecars) != {"minio_capability", "reconciliation"}:
        raise EvidenceMismatch("operation preflight sidecar set is incomplete or unexpected")

    reconciliation_path, reconciliation_sha256 = sidecars["reconciliation"]
    try:
        reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceMismatch("approved reconciliation is not readable JSON") from error
    if (
        not isinstance(reconciliation, dict)
        or reconciliation.get("schema_version")
        != "huiji.candidate-minio-reconciliation/v1"
    ):
        raise EvidenceMismatch("approved reconciliation schema is unsupported")
    if reconciliation.get("candidate_build_manifest_sha256") != payload.get(
        "build_manifest_sha256"
    ):
        raise EvidenceMismatch("approved reconciliation candidate differs from preflight")
    reconciliation_inventory = reconciliation.get("current_inventory")
    if not isinstance(reconciliation_inventory, dict) or reconciliation_inventory.get(
        "object_state_sha256"
    ) != payload.get("before_inventory_object_sha256"):
        raise EvidenceMismatch("approved reconciliation inventory differs from preflight")
    classification = reconciliation.get("classification")
    if not isinstance(classification, dict):
        raise EvidenceMismatch("approved reconciliation lacks classification")
    mismatch_count = classification.get("hash_mismatch_count")
    missing_count = classification.get("missing_remote_unique_object_count")
    raw_role_counts = classification.get("missing_role_counts")
    if mismatch_count != 0:
        raise EvidenceMismatch("approved reconciliation contains a hash mismatch")
    if isinstance(missing_count, bool) or not isinstance(missing_count, int) or missing_count < 0:
        raise EvidenceMismatch("approved reconciliation missing count is invalid")
    if not isinstance(raw_role_counts, dict):
        raise EvidenceMismatch("approved reconciliation role counts are invalid")
    role_counts: list[tuple[str, int]] = []
    for role, count in raw_role_counts.items():
        if (
            not isinstance(role, str)
            or not role
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise EvidenceMismatch("approved reconciliation role count is invalid")
        role_counts.append((role, count))
    if sum(count for _, count in role_counts) != missing_count:
        raise EvidenceMismatch("approved reconciliation role counts do not close")
    approved_missing_hash = str(
        classification.get("ordered_missing_object_keys_sha256") or ""
    )
    if approved_missing_hash != payload.get("approved_missing_object_keys_sha256"):
        raise EvidenceMismatch("approved reconciliation missing-key hash differs from preflight")

    capability = load_capability_evidence_from_bundle(resolved_bundle)
    preflight = MinioOperationPreflight(
        schema_version="evb.minio-operation-preflight/v1",
        build_manifest_sha256=str(payload["build_manifest_sha256"]),
        baseline_sha256=str(payload["baseline_sha256"]),
        before_inventory_sha256=str(payload["before_inventory_sha256"]),
        before_inventory_object_sha256=str(payload["before_inventory_object_sha256"]),
        approved_missing_object_keys_sha256=approved_missing_hash,
        approved_missing_remote_count=missing_count,
        approved_missing_role_counts=tuple(sorted(role_counts)),
        allowed_media_authorities=authorities,
        reconciliation_sha256=reconciliation_sha256,
    )
    return preflight, capability


def load_capability_evidence_from_bundle(bundle_path: Path) -> CapabilityEvidence:
    bundle_path = Path(bundle_path).resolve()
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    sidecars = payload.get("sidecars") if isinstance(payload, dict) else None
    if not isinstance(sidecars, list):
        raise CapabilityUnavailable("preflight bundle has no capability sidecars")
    for item in sidecars:
        if not isinstance(item, dict) or Path(str(item.get("path") or "")).name != "minio_capability.v1.json":
            continue
        relative = Path(str(item.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise CapabilityUnavailable("MinIO capability sidecar escapes its bundle")
        sidecar = (bundle_path.parent / relative).resolve()
        try:
            sidecar.relative_to(bundle_path.parent)
        except ValueError as error:
            raise CapabilityUnavailable("MinIO capability sidecar escapes its bundle") from error
        expected = str(item.get("sha256") or "")
        try:
            _verify_file(sidecar, expected, "MinIO capability sidecar")
            evidence_payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (EvidenceMismatch, OSError, json.JSONDecodeError) as error:
            raise CapabilityUnavailable("MinIO capability sidecar is not hash-pinned and readable") from error
        if not isinstance(evidence_payload, dict) or evidence_payload.get("schema_version") != "evb.minio-capability/v1":
            raise CapabilityUnavailable("unsupported MinIO capability evidence")
        details = tuple(str(value) for value in evidence_payload.get("details", []))
        evidence = CapabilityEvidence(
            conditional_create_supported=bool(evidence_payload.get("conditional_create_supported")),
            application_audit_supported=bool(evidence_payload.get("application_audit_supported")),
            durable_replace_supported=bool(evidence_payload.get("durable_replace_supported", False)),
            details=details,
            checked_at_utc=str(evidence_payload.get("checked_at_utc") or ""),
        )
        evidence.require_conditional_create_and_app_audit()
        try:
            proof = _capability_details(evidence)
        except EvidenceMismatch as error:
            raise CapabilityUnavailable("MinIO capability evidence details are malformed") from error
        if (
            proof.get("server_atomic_if_none_match") != "proven"
            or proof.get("application_audit_correlation") != "proven"
        ):
            raise CapabilityUnavailable("MinIO capability evidence lacks server and audit proof")
        return evidence
    raise CapabilityUnavailable("preflight bundle lacks minio_capability.v1.json")


def combine_capability_evidence(
    sdk: CapabilityEvidence, server: CapabilityEvidence
) -> CapabilityEvidence:
    return CapabilityEvidence(
        conditional_create_supported=(
            sdk.conditional_create_supported and server.conditional_create_supported
        ),
        application_audit_supported=(
            sdk.application_audit_supported and server.application_audit_supported
        ),
        durable_replace_supported=False,
        details=tuple((*sdk.details, *server.details)),
        checked_at_utc=max(sdk.checked_at_utc, server.checked_at_utc),
    )


def _capability_details(evidence: CapabilityEvidence) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in evidence.details:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if not key or not value or key in parsed:
            raise EvidenceMismatch("capability details are malformed or duplicated")
        parsed[key] = value
    return parsed


def validate_operation_plan_authority_path(plan_path: Path, processed_root: Path) -> Path:
    resolved_plan = Path(plan_path).resolve()
    resolved_processed = Path(processed_root).resolve()
    try:
        relative = resolved_plan.relative_to(resolved_processed)
    except ValueError as error:
        raise EvidenceMismatch("operation plan authority path escapes processed root") from error
    legacy_layout = len(relative.parts) == 3 and relative.parts[1] == "operations"
    global_layout = (
        len(relative.parts) == 3
        and relative.parts[0] == "operations"
        and _SAFE_OPERATION_ID_RE.fullmatch(relative.parts[1]) is not None
    )
    if resolved_plan.name != "minio_operation_plan.v1.json" or not (
        legacy_layout or global_layout
    ):
        raise EvidenceMismatch("operation plan authority path is not fixed")
    return resolved_plan


def validate_capability_authority(
    evidence: CapabilityEvidence, *, endpoint: str, bucket: str, prefix: str
) -> None:
    evidence.require_conditional_create_and_app_audit()
    details = _capability_details(evidence)
    required = {
        "endpoint",
        "bucket",
        "prefix",
        "server_identity",
        "probe_operation_id",
        "audit_correlation_id",
        "checked_at_utc",
        "server_atomic_if_none_match",
        "application_audit_correlation",
    }
    missing = sorted(required - details.keys())
    if missing:
        raise EvidenceMismatch(f"capability details are missing: {', '.join(missing)}")
    expected = {
        "endpoint": endpoint,
        "bucket": bucket,
        "prefix": prefix.rstrip("/"),
        "server_atomic_if_none_match": "proven",
        "application_audit_correlation": "proven",
    }
    for key, value in expected.items():
        if details[key] != value:
            raise EvidenceMismatch(f"capability {key} differs from configured authority")
    try:
        UUID(details["probe_operation_id"])
        datetime.fromisoformat(details["checked_at_utc"].replace("Z", "+00:00"))
        datetime.fromisoformat(evidence.checked_at_utc.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceMismatch("capability identifiers or checked time are invalid") from error


def validate_capability_provenance(
    planned: CapabilityEvidence, pinned_sidecar: CapabilityEvidence
) -> None:
    planned_details = _capability_details(planned)
    sidecar_details = _capability_details(pinned_sidecar)
    local_aggregate_fields = {
        "aggregate_checked_at_utc",
        "minio_sdk_version",
        "private_execute_available",
    }
    planned_server = {
        key: value for key, value in planned_details.items() if key not in local_aggregate_fields
    }
    sidecar_server = {
        key: value for key, value in sidecar_details.items() if key not in local_aggregate_fields
    }
    if planned_server != sidecar_server:
        raise EvidenceMismatch("capability provenance differs from the immutable operation plan")


def validate_after_inventory_delta(
    current: ObjectInventory,
    after: ObjectInventory,
    object_evidence: Sequence[ObjectEvidence],
) -> None:
    if current.bucket != after.bucket or current.prefix != after.prefix:
        raise EvidenceMismatch("after inventory drift: bucket or prefix changed")
    if current.bucket_policy_summary != after.bucket_policy_summary:
        raise EvidenceMismatch("after inventory drift: bucket policy summary changed")
    current_by_key = {item.object_key: item for item in current.objects}
    after_by_key = {item.object_key: item for item in after.objects}
    if any(after_by_key.get(key) != item for key, item in current_by_key.items()):
        raise EvidenceMismatch("after inventory drift: existing object changed or disappeared")
    uploaded = {item.object_key: item for item in object_evidence if item.status == "uploaded"}
    added_keys = set(after_by_key) - set(current_by_key)
    if added_keys != set(uploaded):
        raise EvidenceMismatch("after inventory drift: unapproved object delta")
    for key, evidence in uploaded.items():
        item = after_by_key[key]
        if (item.sha1, item.sha256, item.size) != (
            evidence.sha1_after,
            evidence.sha256_after,
            evidence.size_after,
        ):
            raise EvidenceMismatch("after inventory drift: uploaded object content differs")
        if not evidence.etag or not item.etag or item.etag != evidence.etag:
            raise EvidenceMismatch("after inventory drift: uploaded ETag is missing or differs")
        if evidence.version_id is not None and item.version_id != evidence.version_id:
            raise EvidenceMismatch("after inventory drift: uploaded version ID differs")
        if item.application_operation_id is None:
            raise ApplicationAuditMissing(
                "after inventory drift: uploaded application audit is missing"
            )
        if item.application_operation_id != evidence.operation_audit_id:
            raise EvidenceMismatch("after inventory drift: uploaded application audit differs")


def _marker_path(plan_path: Path) -> Path:
    return plan_path.with_name("minio_operation_plan.use.v1.json")


def load_and_claim_operation_plan(
    path: Path, expected_sha256: str, current_inventory: ObjectInventory
) -> MinioOperationPlan:
    plan_path = Path(path).resolve()
    plan = load_operation_plan(plan_path, expected_sha256)
    if current_inventory.bucket != plan.bucket or current_inventory.prefix != plan.prefix:
        raise EvidenceMismatch("MinIO bucket or prefix drifted")
    if current_inventory.object_state_sha256 != plan.before_inventory_object_sha256:
        raise EvidenceMismatch("MinIO before inventory drifted")
    operation_id = str(uuid4())
    marker = MinioPlanUseMarker(
        schema_version="evb.minio-plan-use/v1", plan_path=os.path.relpath(plan_path, plan_path.parent),
        plan_sha256=plan.operation_plan_sha256, operation_id=operation_id,
        object_set_sha256=plan.object_set_sha256, claimed_at_utc=_utc_now(), marker_sha256="",
    )
    marker = replace(marker, marker_sha256=canonical_hash_without(marker, "marker_sha256"))
    try:
        _write_create_new(_marker_path(plan_path), _jsonable(marker))
    except FileExistsError as error:
        raise EvidenceAlreadyUsed("MinIO operation plan already has a use marker") from error
    return replace(plan, used_by_operation_id=operation_id)


def validate_planned_request(
    plan: MinioOperationPlan, request: StrictObjectRequest, operation_id: UUID
) -> None:
    if not isinstance(operation_id, UUID):
        raise EvidenceMismatch("operation_id must be a UUID")
    if plan.used_by_operation_id is None:
        raise EvidenceMismatch("operation plan has not been claimed")
    if plan.used_by_operation_id != str(operation_id):
        raise EvidenceMismatch("operation ID does not own the claimed operation plan")
    expected = (
        request.bucket, request.object_key, request.sha1, request.sha256, request.size,
        request.content_type, request.asset_type, request.suffix,
    )
    matches = [item for item in plan.objects if (
        item.bucket, item.object_key, item.sha1, item.sha256, item.size,
        item.content_type, item.asset_type, item.suffix,
    ) == expected]
    if len(matches) != 1:
        raise EvidenceMismatch("request is not an exact member of the immutable operation plan")


def map_s3_error(error: S3Error) -> Literal["concurrency_conflict", "blocked", "failed"]:
    if error.code in {"PreconditionFailed", "ConditionalRequestConflict"}:
        return "concurrency_conflict"
    if error.code in {"AccessDenied", "NotImplemented", "MethodNotAllowed"}:
        return "blocked"
    return "failed"


class StrictMinioUploader:
    def __init__(
        self,
        minio_client: object,
        capabilities: CapabilityEvidence,
        *,
        source_root: Path,
    ) -> None:
        self._minio = minio_client
        self._capabilities = capabilities
        self._source_root = Path(source_root).resolve()

    def capability_preflight(self, before_inventory: Path) -> CapabilityEvidence:
        _load_inventory(Path(before_inventory))
        self._capabilities.require_conditional_create_and_app_audit()
        if not callable(getattr(self._minio, "_execute", None)):
            raise CapabilityUnavailable("MinIO private conditional transport is unavailable")
        return self._capabilities

    def _validate_local_request(self, request: StrictObjectRequest) -> bytes:
        _validate_hash(request.sha1, _SHA1_RE, "request SHA-1")
        _validate_hash(request.sha256, _SHA256_RE, "request SHA-256")
        resolved = Path(request.local_path).resolve(strict=True)
        try:
            resolved.relative_to(self._source_root)
        except ValueError as error:
            raise EvidenceMismatch("local source escapes approved source root") from error
        body = resolved.read_bytes()
        if len(body) != request.size:
            raise ContentHashMismatch("local source size mismatch")
        if hashlib.sha1(body).hexdigest() != request.sha1:
            raise ContentHashMismatch("local source SHA-1 mismatch")
        if hashlib.sha256(body).hexdigest() != request.sha256:
            raise ContentHashMismatch("local source SHA-256 mismatch")
        expected_key = f"reverse1999/{request.asset_type}/{request.sha1[:2]}/{request.sha1}{request.suffix}"
        if request.object_key != expected_key:
            raise EvidenceMismatch("object key is not derived from the approved SHA-1")
        if request.asset_type == "voice" and request.suffix != ".mp3":
            raise EvidenceMismatch("voice object suffix must be .mp3")
        return body

    def create_operation_plan(
        self,
        baseline_path: Path,
        expected_baseline_sha256: str,
        build_manifest_path: Path,
        expected_build_manifest_sha256: str,
        preflight_bundle_path: Path,
        expected_preflight_bundle_sha256: str,
        before_inventory_path: Path,
        expected_before_inventory_sha256: str,
        requests: Sequence[StrictObjectRequest],
        output: Path,
    ) -> MinioOperationPlan:
        baseline = _verify_file(baseline_path, expected_baseline_sha256, "baseline")
        build = _verify_file(build_manifest_path, expected_build_manifest_sha256, "build manifest")
        bundle = _verify_file(preflight_bundle_path, expected_preflight_bundle_sha256, "preflight bundle")
        inventory_path = _verify_file(before_inventory_path, expected_before_inventory_sha256, "before inventory")
        inventory = _load_inventory(inventory_path)
        self.capability_preflight(inventory_path)
        output = Path(output).resolve()

        existing = {item.object_key: item for item in inventory.objects}
        planned: list[PlannedObject] = []
        for request in requests:
            self._validate_local_request(request)
            if request.bucket != inventory.bucket or not request.object_key.startswith(inventory.prefix + "/"):
                raise EvidenceMismatch("request bucket or prefix differs from before inventory")
            remote = existing.get(request.object_key)
            if remote is not None:
                if (remote.sha1, remote.sha256, remote.size) != (
                    request.sha1, request.sha256, request.size
                ):
                    raise ContentHashMismatch("existing MinIO object differs from approved content")
            planned.append(PlannedObject(
                bucket=request.bucket, object_key=request.object_key, sha1=request.sha1,
                sha256=request.sha256, size=request.size,
                source_path=os.path.relpath(Path(request.local_path).resolve(), output.parent),
                content_type=request.content_type, asset_type=request.asset_type, suffix=request.suffix,
                disposition="same_hash_skip" if remote is not None else "conditional_create",
                before_version_id=None if remote is None else remote.version_id,
                before_etag="" if remote is None else remote.etag,
                before_sha1=None if remote is None else remote.sha1,
                before_sha256=None if remote is None else remote.sha256,
                before_size=None if remote is None else remote.size,
            ))
        planned.sort(key=lambda item: (item.bucket, item.object_key))
        if len({(item.bucket, item.object_key) for item in planned}) != len(planned):
            raise EvidenceMismatch("operation plan contains duplicate object targets")
        object_set_sha256 = hashlib.sha256(_canonical_bytes(planned)).hexdigest()

        def rel(path: Path) -> str:
            return os.path.relpath(path, output.parent)

        plan = MinioOperationPlan(
            schema_version="evb.minio-operation-plan/v1", plan_id=str(uuid4()),
            baseline_path=rel(baseline), baseline_sha256=expected_baseline_sha256,
            build_manifest_path=rel(build), build_manifest_sha256=expected_build_manifest_sha256,
            preflight_bundle_path=rel(bundle), preflight_bundle_sha256=expected_preflight_bundle_sha256,
            before_inventory_path=rel(inventory_path), before_inventory_sha256=expected_before_inventory_sha256,
            before_inventory_object_sha256=inventory.object_state_sha256,
            bucket=inventory.bucket, prefix=inventory.prefix,
            source_root=self._source_root.as_posix(),
            capability_evidence=self._capabilities,
            objects=tuple(planned),
            object_set_sha256=object_set_sha256, created_at_utc=_utc_now(),
            used_by_operation_id=None, operation_plan_sha256="",
        )
        plan = replace(plan, operation_plan_sha256=canonical_hash_without(plan, "operation_plan_sha256"))
        _write_create_new(output, plan.to_json())
        return plan

    def verify_readback(self, request: StrictObjectRequest) -> ObjectEvidence:
        response = self._minio.get_object(request.bucket, request.object_key)
        try:
            body = response.read()
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            release = getattr(response, "release_conn", None)
            if callable(release):
                release()
        sha1 = hashlib.sha1(body).hexdigest()
        sha256 = hashlib.sha256(body).hexdigest()
        if (sha1, sha256, len(body)) != (request.sha1, request.sha256, request.size):
            raise ContentHashMismatch("HTTP readback does not match approved local content")
        stat = self._minio.stat_object(request.bucket, request.object_key)
        etag = str(getattr(stat, "etag", "") or "").strip('"')
        if not etag:
            raise ContentHashMismatch("HTTP readback ETag is missing")
        return ObjectEvidence(
            status="uploaded", bucket=request.bucket, object_key=request.object_key,
            version_id=getattr(stat, "version_id", None), etag=etag,
            server_request_id=None, sha1_before=None, sha256_before=None, size_before=None,
            sha1_after=sha1, sha256_after=sha256, size_after=len(body), http_readback=True,
            operation_audit_id="unattached",
        )

    def conditional_create(
        self, plan: MinioOperationPlan, request: StrictObjectRequest, operation_id: UUID
    ) -> ObjectEvidence:
        self._capabilities.require_conditional_create_and_app_audit()
        validate_planned_request(plan, request, operation_id)
        body = self._validate_local_request(request)
        return self._conditional_create_with_body(plan, request, operation_id, body)

    def _conditional_create_with_body(
        self,
        plan: MinioOperationPlan,
        request: StrictObjectRequest,
        operation_id: UUID,
        body: bytes,
    ) -> ObjectEvidence:
        self._capabilities.require_conditional_create_and_app_audit()
        validate_planned_request(plan, request, operation_id)
        response = self._minio._execute(
            method="PUT", bucket_name=request.bucket, object_name=request.object_key, body=body,
            headers={
                "If-None-Match": "*", "Content-Type": request.content_type,
                "x-amz-meta-evb-operation-id": str(operation_id),
            },
        )
        headers = getattr(response, "headers", {}) or {}
        response_evidence = attach_operation_evidence(
            _empty_evidence(
                "hash_mismatch", request, str(operation_id), headers.get("x-amz-request-id")
            ),
            operation_id=str(operation_id),
            version_id=headers.get("x-amz-version-id"),
        )
        response_evidence = replace(
            response_evidence,
            etag=str(headers.get("ETag") or headers.get("etag") or "").strip('"'),
        )
        if not response_evidence.etag:
            raise PostCreateReadbackFailure("PUT response ETag is missing", response_evidence)
        try:
            evidence = self.verify_readback(request)
        except (ContentHashMismatch, OSError) as error:
            raise PostCreateReadbackFailure(str(error), response_evidence) from error
        return attach_operation_evidence(
            replace(
                evidence,
                etag=response_evidence.etag or evidence.etag,
                server_request_id=response_evidence.server_request_id,
            ),
            operation_id=str(operation_id),
            version_id=response_evidence.version_id,
        )

    def upload_sequence(
        self,
        plan: MinioOperationPlan,
        requests: Sequence[StrictObjectRequest],
        operation_id: UUID,
        *,
        current_inventory: ObjectInventory | None = None,
        after_inventory: ObjectInventory | None = None,
    ) -> UploadReport:
        self._capabilities.require_conditional_create_and_app_audit()
        request_by_signature = {
            (
                item.bucket, item.object_key, item.sha1, item.sha256, item.size,
                item.content_type, item.asset_type, item.suffix,
            ): item
            for item in requests
        }
        if len(request_by_signature) != len(requests):
            raise EvidenceMismatch("upload request set contains duplicates")
        plan_signatures = tuple(
            (
                item.bucket, item.object_key, item.sha1, item.sha256, item.size,
                item.content_type, item.asset_type, item.suffix,
            )
            for item in plan.objects
        )
        if set(request_by_signature) != set(plan_signatures):
            raise EvidenceMismatch("upload request set differs from the immutable object set")
        ordered_requests = tuple(request_by_signature[signature] for signature in plan_signatures)
        planned_by_signature = dict(zip(plan_signatures, plan.objects, strict=True))

        evidence_by_signature: dict[tuple[object, ...], ObjectEvidence] = {}
        status = "uploaded"
        stopped = False

        def signature_for(request: StrictObjectRequest) -> tuple[object, ...]:
            return (
                request.bucket,
                request.object_key,
                request.sha1,
                request.sha256,
                request.size,
                request.content_type,
                request.asset_type,
                request.suffix,
            )

        def record_failure(
            request: StrictObjectRequest, error: BaseException, signature: tuple[object, ...]
        ) -> None:
            nonlocal status, stopped
            status = "failed"
            failure_status = "missing_local" if isinstance(error, FileNotFoundError) else "hash_mismatch"
            evidence_by_signature[signature] = _empty_evidence(
                failure_status, request, str(operation_id)
            )
            stopped = True

        frozen_bodies: dict[tuple[object, ...], bytes] = {}
        for request in ordered_requests:
            signature = signature_for(request)
            try:
                body = self._validate_local_request(request)
                if planned_by_signature[signature].disposition == "conditional_create":
                    frozen_bodies[signature] = body
            except (StrictMinioError, OSError) as error:
                record_failure(request, error, signature)
                break

        if not stopped:
            for request in ordered_requests:
                signature = signature_for(request)
                planned = planned_by_signature[signature]
                if planned.disposition != "same_hash_skip":
                    continue
                try:
                    readback = self.verify_readback(request)
                    evidence_by_signature[signature] = attach_operation_evidence(
                        replace(
                            readback,
                            status="same_hash_skip",
                            version_id=planned.before_version_id,
                            etag=planned.before_etag or readback.etag,
                            sha1_before=planned.before_sha1,
                            sha256_before=planned.before_sha256,
                            size_before=planned.before_size,
                        ),
                        operation_id=str(operation_id),
                        version_id=planned.before_version_id,
                    )
                except S3Error as error:
                    status = map_s3_error(error)
                    evidence_by_signature[signature] = _empty_evidence(
                        status, request, str(operation_id), error.request_id
                    )
                    stopped = True
                    break
                except (StrictMinioError, OSError) as error:
                    record_failure(request, error, signature)
                    break

        if not stopped:
            for request in ordered_requests:
                signature = signature_for(request)
                planned = planned_by_signature[signature]
                if planned.disposition == "same_hash_skip":
                    continue
                try:
                    evidence_by_signature[signature] = self._conditional_create_with_body(
                        plan,
                        request,
                        operation_id,
                        frozen_bodies[signature],
                    )
                except S3Error as error:
                    status = map_s3_error(error)
                    evidence_by_signature[signature] = _empty_evidence(
                        status, request, str(operation_id), error.request_id
                    )
                    stopped = True
                    break
                except PostCreateReadbackFailure as error:
                    status = "failed"
                    evidence_by_signature[signature] = error.evidence
                    stopped = True
                    break
                except (StrictMinioError, OSError) as error:
                    record_failure(request, error, signature)
                    break

        evidence = tuple(
            evidence_by_signature.get(
                signature_for(request),
                _empty_evidence("not_attempted_after_stop", request, str(operation_id)),
            )
            for request in ordered_requests
        )
        current_inventory_sha256 = (
            current_inventory.inventory_sha256
            if current_inventory is not None
            else plan.before_inventory_sha256
        )
        current_inventory_object_sha256 = (
            current_inventory.object_state_sha256
            if current_inventory is not None
            else plan.before_inventory_object_sha256
        )
        after_inventory_sha256 = (
            after_inventory.inventory_sha256
            if after_inventory is not None
            else current_inventory_sha256
        )
        after_inventory_object_sha256 = (
            after_inventory.object_state_sha256
            if after_inventory is not None
            else current_inventory_object_sha256
        )
        return UploadReport(
            "evb.minio-report/v1",
            str(operation_id),
            status,
            plan.operation_plan_sha256,
            plan.before_inventory_sha256,
            plan.before_inventory_object_sha256,
            current_inventory_sha256,
            current_inventory_object_sha256,
            after_inventory_sha256,
            after_inventory_object_sha256,
            None,
            None,
            evidence,
            "",
        )


def requests_from_operation_plan(
    plan: MinioOperationPlan, plan_path: Path
) -> tuple[StrictObjectRequest, ...]:
    root = Path(plan_path).resolve().parent
    return tuple(
        StrictObjectRequest(
            bucket=item.bucket,
            object_key=item.object_key,
            local_path=(root / item.source_path).resolve(),
            sha1=item.sha1,
            sha256=item.sha256,
            size=item.size,
            content_type=item.content_type,
            asset_type=item.asset_type,
            suffix=item.suffix,
        )
        for item in plan.objects
    )


def prepare_upload_inputs(
    plan_path: Path,
    expected_sha256: str,
    *,
    processed_root: Path,
    source_root: Path,
    endpoint: str,
    bucket: str,
    prefix: str,
    report_path: Path,
) -> tuple[MinioOperationPlan, tuple[StrictObjectRequest, ...]]:
    """Validate every immutable/local input before a mutation client is constructed."""
    resolved_plan = validate_operation_plan_authority_path(plan_path, processed_root)
    resolved_report = Path(report_path).resolve()
    if resolved_report != resolved_plan.with_name("minio_write_report.v1.json"):
        raise EvidenceMismatch("MinIO report destination is not the fixed sibling path")
    if resolved_report.exists():
        raise EvidenceMismatch("MinIO report destination already exists")

    plan = load_operation_plan(resolved_plan, expected_sha256)
    configured_source = Path(source_root).resolve()
    if Path(plan.source_root).resolve() != configured_source:
        raise EvidenceMismatch("operation plan source root differs from configured authority")
    if plan.bucket != bucket:
        raise EvidenceMismatch("operation plan bucket differs from configured authority")
    if plan.prefix != prefix.rstrip("/"):
        raise EvidenceMismatch("operation plan prefix differs from configured authority")
    validate_capability_authority(
        plan.capability_evidence,
        endpoint=endpoint,
        bucket=bucket,
        prefix=prefix,
    )

    evidence_paths = (
        (plan.baseline_path, plan.baseline_sha256, "baseline"),
        (plan.build_manifest_path, plan.build_manifest_sha256, "build manifest"),
        (plan.preflight_bundle_path, plan.preflight_bundle_sha256, "preflight bundle"),
        (plan.before_inventory_path, plan.before_inventory_sha256, "before inventory"),
    )
    resolved_evidence: dict[str, Path] = {}
    for relative_path, expected, label in evidence_paths:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (resolved_plan.parent / candidate).resolve()
        resolved_evidence[label] = _verify_file(resolved, expected, label)
    preflight_payload = json.loads(
        resolved_evidence["preflight bundle"].read_text(encoding="utf-8")
    )
    if (
        isinstance(preflight_payload, dict)
        and preflight_payload.get("schema_version")
        == "evb.minio-operation-preflight/v1"
    ):
        operation_preflight, sidecar_capability = load_operation_preflight_bundle(
            resolved_evidence["preflight bundle"]
        )
        expected_core = (
            (plan.build_manifest_sha256, operation_preflight.build_manifest_sha256, "build manifest"),
            (plan.baseline_sha256, operation_preflight.baseline_sha256, "baseline"),
            (plan.before_inventory_sha256, operation_preflight.before_inventory_sha256, "before inventory"),
            (
                plan.before_inventory_object_sha256,
                operation_preflight.before_inventory_object_sha256,
                "before inventory object state",
            ),
        )
        for planned_value, preflight_value, label in expected_core:
            if planned_value != preflight_value:
                raise EvidenceMismatch(f"operation preflight {label} differs from plan")
        if any(item.disposition != "conditional_create" for item in plan.objects):
            raise EvidenceMismatch("v3 operation plan contains a non-create disposition")
        if (
            ordered_object_keys_sha256([item.object_key for item in plan.objects])
            != operation_preflight.approved_missing_object_keys_sha256
        ):
            raise EvidenceMismatch("v3 operation plan missing object-key set differs from approval")
        if len(plan.objects) != operation_preflight.approved_missing_remote_count:
            raise EvidenceMismatch("v3 operation plan missing object count differs from approval")
        plan_role_counts: dict[str, int] = {}
        authority_projection = {
            (item.asset_type, item.mime, item.suffix)
            for item in operation_preflight.allowed_media_authorities
        }
        for item in plan.objects:
            if (item.asset_type, item.content_type, item.suffix) not in authority_projection:
                raise EvidenceMismatch("v3 operation plan object is outside media authority")
            plan_role_counts[item.asset_type] = plan_role_counts.get(item.asset_type, 0) + 1
        if tuple(sorted(plan_role_counts.items())) != operation_preflight.approved_missing_role_counts:
            raise EvidenceMismatch("v3 operation plan media counts differ from approval")
    else:
        sidecar_capability = load_capability_evidence_from_bundle(
            resolved_evidence["preflight bundle"]
        )
    validate_capability_authority(
        sidecar_capability,
        endpoint=endpoint,
        bucket=bucket,
        prefix=prefix,
    )
    validate_capability_provenance(plan.capability_evidence, sidecar_capability)

    requests = requests_from_operation_plan(plan, resolved_plan)
    validator = StrictMinioUploader(object(), plan.capability_evidence, source_root=configured_source)
    for request in requests:
        if request.bucket != bucket or not request.object_key.startswith(prefix.rstrip("/") + "/"):
            raise EvidenceMismatch("planned request differs from configured bucket or prefix")
        validator._validate_local_request(request)
    return plan, requests


def capture_object_inventory(
    minio_client: object, bucket: str, prefix: str
) -> ObjectInventory:
    normalized_prefix = prefix.rstrip("/")
    try:
        raw_policy = minio_client.get_bucket_policy(bucket)
    except S3Error as error:
        if error.code in {"NoSuchBucketPolicy", "NoSuchPolicy"}:
            bucket_policy_summary = "absent"
        else:
            raise
    except (AttributeError, OSError) as error:
        raise CapabilityUnavailable("MinIO inventory evidence cannot read bucket policy") from error
    else:
        if not isinstance(raw_policy, str):
            raise CapabilityUnavailable("MinIO inventory evidence has invalid bucket policy")
        try:
            policy_payload = json.loads(raw_policy)
        except json.JSONDecodeError as error:
            raise CapabilityUnavailable("MinIO inventory evidence has invalid bucket policy") from error
        bucket_policy_summary = f"sha256:{hashlib.sha256(_canonical_bytes(policy_payload)).hexdigest()}"

    records: list[InventoryObject] = []
    try:
        list_prefix = f"{normalized_prefix}/" if normalized_prefix else ""
        listed_objects = minio_client.list_objects(
            bucket, prefix=list_prefix, recursive=True
        )
        for listed in listed_objects:
            object_key = str(listed.object_name)
            stat = minio_client.stat_object(bucket, object_key)
            metadata = getattr(stat, "metadata", {}) or {}
            normalized_metadata = {str(key).lower(): value for key, value in metadata.items()}
            sha1 = str(
                normalized_metadata.get("x-amz-meta-sha1")
                or normalized_metadata.get("sha1")
                or ""
            )
            sha256 = str(
                normalized_metadata.get("x-amz-meta-content-sha256")
                or normalized_metadata.get("content-sha256")
                or normalized_metadata.get("sha256")
                or ""
            )
            operation_value = normalized_metadata.get("x-amz-meta-evb-operation-id")
            application_operation_id = (
                None if operation_value is None else str(operation_value) or None
            )
            audit_event_value = normalized_metadata.get("x-amz-meta-evb-audit-event-id")
            audit_event_id = None if audit_event_value is None else str(audit_event_value)
            size = int(getattr(stat, "size", -1))
            etag = str(getattr(stat, "etag", "") or "").strip('"')
            if not etag:
                raise CapabilityUnavailable(
                    f"MinIO inventory evidence has an empty ETag for {object_key}"
                )
            if not _SHA1_RE.fullmatch(sha1) or not _SHA256_RE.fullmatch(sha256):
                response = minio_client.get_object(bucket, object_key)
                try:
                    body = response.read()
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
                    release = getattr(response, "release_conn", None)
                    if callable(release):
                        release()
                sha1 = hashlib.sha1(body).hexdigest()
                sha256 = hashlib.sha256(body).hexdigest()
                size = len(body)
            records.append(
                InventoryObject(
                    object_key=object_key,
                    version_id=getattr(stat, "version_id", None),
                    etag=etag,
                    sha1=sha1,
                    sha256=sha256,
                    size=size,
                    audit_event_id=audit_event_id,
                    application_operation_id=application_operation_id,
                )
            )
    except S3Error:
        raise
    except OSError as error:
        raise CapabilityUnavailable("MinIO inventory evidence transport failed") from error
    return ObjectInventory.create(
        bucket,
        normalized_prefix,
        records,
        bucket_policy_summary=bucket_policy_summary,
    )


def write_upload_report(path: Path, report: UploadReport) -> UploadReport:
    finalized = replace(
        report,
        report_sha256=canonical_hash_without(report, "report_sha256"),
    )
    _write_create_new(Path(path).resolve(), finalized.to_json())
    return finalized


def _empty_evidence(
    status: str,
    request: StrictObjectRequest,
    operation_id: str,
    server_request_id: str | None = None,
) -> ObjectEvidence:
    return ObjectEvidence(
        status=status, bucket=request.bucket, object_key=request.object_key, version_id=None,
        etag="", server_request_id=server_request_id, sha1_before=None, sha256_before=None,
        size_before=None, sha1_after=None, sha256_after=None, size_after=None,
        http_readback=False, operation_audit_id=operation_id,
    )


def load_operation_plan(path: Path, expected_sha256: str) -> MinioOperationPlan:
    _validate_hash(expected_sha256, _SHA256_RE, "operation plan")
    verified = Path(path).resolve()
    if not verified.is_file():
        raise EvidenceMismatch("operation plan does not exist")
    payload = json.loads(verified.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceMismatch("operation plan must be an object")
    if verified.read_bytes() != _serialized_json_bytes(payload):
        raise EvidenceMismatch("operation plan is not in canonical serialization")
    plan = MinioOperationPlan.from_json(payload)
    if plan.operation_plan_sha256 != expected_sha256:
        raise EvidenceMismatch("operation plan canonical hash differs from file hash")
    return plan
