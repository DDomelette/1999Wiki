"""One-time evidence CLI for the MinIO blue-green migration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence
from urllib.request import urlopen
from uuid import uuid4

from minio import Minio
from minio.error import S3Error


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.huiji_rag.minio_strict import (  # noqa: E402
    MediaOperationAuthority,
    ObjectInventory,
)


class EvidenceDrift(RuntimeError):
    pass


class ProbeRequestFailed(RuntimeError):
    def __init__(self, code: str, request_id: str | None) -> None:
        super().__init__(code)
        self.code = code
        self.request_id = request_id


class ProbePreconditionFailed(ProbeRequestFailed):
    pass


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _write_create_new(path: Path, payload: Mapping[str, object]) -> str:
    resolved = Path(path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(payload) + b"\n"
    with resolved.open("xb") as handle:
        handle.write(data)
    digest = _sha256(data)
    print(digest)
    return digest


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return value


def _copy_create_new(source: Path, destination: Path) -> str:
    resolved_source = Path(source).resolve(strict=True)
    resolved_destination = Path(destination).resolve()
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with resolved_source.open("rb") as source_handle, resolved_destination.open("xb") as target:
        for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
            target.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def capture_filesystem_inventory(root: Path, output: Path) -> dict[str, object]:
    resolved = Path(root).resolve(strict=True)
    files = []
    for path in sorted((item for item in resolved.rglob("*") if item.is_file())):
        files.append({
            "relative_path": path.relative_to(resolved).as_posix(),
            "size": path.stat().st_size,
            "sha256": _file_sha256(path),
        })
    payload: dict[str, object] = {
        "schema_version": "evb.filesystem-inventory/v1",
        "root": resolved.as_posix(),
        "file_count": len(files),
        "files": files,
    }
    _write_create_new(output, payload)
    return payload


def compare_file_payloads(
    expected: Mapping[str, object], actual: Mapping[str, object]
) -> dict[str, object]:
    expected_files = expected.get("files")
    actual_files = actual.get("files")
    if not isinstance(expected_files, list) or not isinstance(actual_files, list):
        raise EvidenceDrift("filesystem evidence lacks files")
    normalized_expected = [
        {key: item.get(key) for key in ("relative_path", "size", "sha256")}
        for item in expected_files if isinstance(item, dict)
    ]
    normalized_actual = [
        {key: item.get(key) for key in ("relative_path", "size", "sha256")}
        for item in actual_files if isinstance(item, dict)
    ]
    if normalized_expected != normalized_actual:
        raise EvidenceDrift("filesystem inventory drift")
    return {"status": "equal", "file_count": len(normalized_expected)}


def _object_state(item: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(item.get(key) for key in (
        "object_key", "size", "sha1", "sha256", "etag", "version_id"
    ))


def compare_object_payloads(
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    *,
    allowed_added_keys: set[str],
) -> dict[str, object]:
    for field in ("bucket", "prefix", "bucket_policy_summary"):
        if expected.get(field) != actual.get(field):
            raise EvidenceDrift(f"object inventory {field} drift")
    expected_items = expected.get("objects")
    actual_items = actual.get("objects")
    if not isinstance(expected_items, list) or not isinstance(actual_items, list):
        raise EvidenceDrift("object inventory lacks objects")
    expected_by_key = {str(item["object_key"]): item for item in expected_items}
    actual_by_key = {str(item["object_key"]): item for item in actual_items}
    if len(expected_by_key) != len(expected_items) or len(actual_by_key) != len(actual_items):
        raise EvidenceDrift("object inventory contains duplicate keys")
    missing = sorted(set(expected_by_key) - set(actual_by_key))
    added = sorted(set(actual_by_key) - set(expected_by_key))
    changed = sorted(
        key for key in set(expected_by_key) & set(actual_by_key)
        if _object_state(expected_by_key[key]) != _object_state(actual_by_key[key])
    )
    if missing or changed or set(added) != allowed_added_keys:
        raise EvidenceDrift(
            f"object inventory drift: missing={len(missing)} changed={len(changed)} "
            f"added={len(added)}"
        )
    return {
        "status": "equal_with_approved_additions" if added else "equal",
        "object_count": len(actual_by_key),
        "added_keys": added,
    }


def capture_milvus_inventory(
    client: object, endpoint: str, database: str
) -> dict[str, object]:
    collections = []
    for name in sorted(client.list_collections()):
        description = client.describe_collection(name)
        fields = description.get("fields") if isinstance(description, dict) else None
        primary = next(
            (
                str(field["name"])
                for field in (fields or [])
                if isinstance(field, dict) and field.get("is_primary")
            ),
            None,
        )
        if primary is None and isinstance(fields, list):
            primary = next(
                (str(field["name"]) for field in fields if isinstance(field, dict)),
                None,
            )
        if not primary:
            raise EvidenceDrift(f"Milvus collection {name} lacks a primary field")
        rows = client.query(
            collection_name=name, filter="", output_fields=[primary], limit=1
        )
        first_value = rows[0].get(primary) if rows else None
        collections.append({
            "name": name,
            "description": description,
            "indexes": client.list_indexes(name),
            "stats": client.get_collection_stats(name),
            "load_state": client.get_load_state(name),
            "first_id_fingerprint": {
                "field": primary,
                "sha256": _sha256(canonical_bytes(first_value)),
            },
        })
    return {
        "schema_version": "evb.milvus-inventory/v1",
        "endpoint": endpoint,
        "database": database,
        "collection_count": len(collections),
        "collections": collections,
    }


def compare_milvus_payloads(
    expected: Mapping[str, object], actual: Mapping[str, object]
) -> dict[str, object]:
    for field in ("database", "collection_count", "collections"):
        if expected.get(field) != actual.get(field):
            raise EvidenceDrift(f"Milvus inventory {field} drift")
    return {"status": "equal", "collection_count": expected.get("collection_count")}


def verify_media_samples(
    inventory: Mapping[str, object], base_url: str, asset_types: Sequence[str],
    fetch: object | None = None,
) -> dict[str, object]:
    objects = inventory.get("objects")
    if not isinstance(objects, list):
        raise EvidenceDrift("inventory lacks objects")
    fetch_body = fetch or (lambda url: urlopen(url, timeout=30).read())
    samples = []
    for asset_type in sorted(set(asset_types)):
        marker = f"/{asset_type}/"
        candidates = sorted(
            (item for item in objects if marker in str(item.get("object_key", ""))),
            key=lambda item: str(item["object_key"]),
        )
        if not candidates:
            raise EvidenceDrift(f"no media sample for asset type {asset_type}")
        item = candidates[0]
        body = fetch_body(f"{base_url.rstrip('/')}/{item['object_key']}")
        if (
            len(body) != item.get("size")
            or _sha1(body) != item.get("sha1")
            or _sha256(body) != item.get("sha256")
        ):
            raise EvidenceDrift(f"media sample hash mismatch: {item['object_key']}")
        samples.append({
            "asset_type": asset_type,
            "object_key": item["object_key"],
            "size": len(body),
            "sha1": _sha1(body),
            "sha256": _sha256(body),
        })
    return {
        "schema_version": "evb.media-sample-verification/v1",
        "base_url": base_url.rstrip("/"),
        "samples": samples,
    }


def prepare_c19_evidence(
    *, artifact_root: Path, baseline: Path, current_inventory: Path,
    capability: Path, reconciliation: Path, output_root: Path,
) -> dict[str, Path]:
    artifact = Path(artifact_root).resolve(strict=True)
    media_manifest = artifact / "runtime" / "media_assets.v2.manifest.json"
    manifest = _read_json(media_manifest)
    media_path = artifact / str(manifest["file_paths"]["media_assets_v2"])
    expected_media_hash = str(manifest["file_sha256"]["media_assets_v2"])
    if _file_sha256(media_path) != expected_media_hash:
        raise EvidenceDrift("media artifact manifest hash mismatch")
    output = Path(output_root).resolve()
    copied_media_manifest = output / "runtime" / "media_assets.v2.manifest.json"
    copied_media = output / "runtime" / "media_assets.v2.jsonl"
    _copy_create_new(media_manifest, copied_media_manifest)
    if _copy_create_new(media_path, copied_media) != expected_media_hash:
        raise EvidenceDrift("copied runtime media hash mismatch")
    build_manifest = output / "build_manifest.json"
    preflight_root = output / "preflight"
    preflight_bundle = preflight_root / "preflight_bundle_manifest.v1.json"
    _write_create_new(build_manifest, {
        "schema_version": "evb.build-manifest/v1",
        "build_version": manifest.get("build_version"),
        "artifact_root": artifact.as_posix(),
        "media_artifact_manifest": media_manifest.relative_to(artifact).as_posix(),
        "media_artifact_manifest_sha256": _file_sha256(copied_media_manifest),
        "media_assets_sha256": expected_media_hash,
    })
    sidecars = []
    for name, filename, path in (
        ("baseline", "baseline.v1.json", baseline),
        ("current_inventory", "current_inventory.v1.json", current_inventory),
        ("minio_capability", "minio_capability.v1.json", capability),
        ("reconciliation", "reconciliation.v1.json", reconciliation),
    ):
        resolved = Path(path).resolve(strict=True)
        destination = preflight_root / filename
        sidecars.append({
            "name": name,
            "path": filename,
            "sha256": _copy_create_new(resolved, destination),
        })
    _write_create_new(preflight_bundle, {
        "schema_version": "evb.preflight-bundle/v1",
        "baseline_sha256": _file_sha256(Path(baseline)),
        "build_manifest": "../build_manifest.json",
        "build_manifest_sha256": _file_sha256(build_manifest),
        "sidecars": sidecars,
    })
    return {"build_manifest": build_manifest, "preflight_bundle": preflight_bundle}


def _verify_expected_file(path: Path, expected_sha256: str, label: str) -> Path:
    resolved = Path(path).resolve(strict=True)
    if (
        len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise EvidenceDrift(f"{label} expected SHA-256 is not canonical")
    if _file_sha256(resolved) != expected_sha256:
        raise EvidenceDrift(f"{label} SHA-256 mismatch")
    return resolved


def prepare_v3_operation_evidence(
    *,
    build_manifest: Path,
    expected_build_manifest_sha256: str,
    baseline: Path,
    expected_baseline_sha256: str,
    current_inventory: Path,
    capability: Path,
    expected_capability_sha256: str,
    reconciliation: Path,
    expected_reconciliation_sha256: str,
    allowed_media_authorities: Sequence[str],
    output_root: Path,
) -> dict[str, Path]:
    build_path = _verify_expected_file(
        build_manifest, expected_build_manifest_sha256, "candidate build manifest"
    )
    baseline_path = _verify_expected_file(
        baseline, expected_baseline_sha256, "fidelity baseline"
    )
    capability_path = _verify_expected_file(
        capability, expected_capability_sha256, "MinIO capability evidence"
    )
    reconciliation_path = _verify_expected_file(
        reconciliation, expected_reconciliation_sha256, "approved reconciliation"
    )
    inventory_path = Path(current_inventory).resolve(strict=True)
    inventory_file_sha256 = _file_sha256(inventory_path)

    build_payload = _read_json(build_path)
    if (
        build_payload.get("schema_version") != "huiji.corpus-build/v2"
        or build_payload.get("artifact_schema_version") != "evb.media-asset/v3"
    ):
        raise EvidenceDrift("candidate build manifest is not corpus media v3")
    inventory = ObjectInventory.from_json(_read_json(inventory_path))
    capability_payload = _read_json(capability_path)
    if capability_payload.get("schema_version") != "evb.minio-capability/v1":
        raise EvidenceDrift("MinIO capability evidence schema is unsupported")
    if not capability_payload.get("conditional_create_supported") or not capability_payload.get(
        "application_audit_supported"
    ):
        raise EvidenceDrift("MinIO capability evidence is not passing")
    reconciliation_payload = _read_json(reconciliation_path)
    if (
        reconciliation_payload.get("schema_version")
        != "huiji.candidate-minio-reconciliation/v1"
    ):
        raise EvidenceDrift("approved reconciliation schema is unsupported")
    if reconciliation_payload.get("candidate_build_manifest_sha256") != expected_build_manifest_sha256:
        raise EvidenceDrift("approved reconciliation pins a different candidate")
    reconciliation_inventory = reconciliation_payload.get("current_inventory")
    if not isinstance(reconciliation_inventory, Mapping) or (
        reconciliation_inventory.get("object_state_sha256")
        != inventory.object_state_sha256
    ):
        raise EvidenceDrift("fresh inventory object state differs from approved reconciliation")
    classification = reconciliation_payload.get("classification")
    if not isinstance(classification, Mapping):
        raise EvidenceDrift("approved reconciliation lacks classification")
    if int(classification.get("hash_mismatch_count", -1)) != 0:
        raise EvidenceDrift("approved reconciliation contains a hash mismatch")
    approved_missing_hash = str(
        classification.get("ordered_missing_object_keys_sha256") or ""
    )
    if len(approved_missing_hash) != 64 or any(
        character not in "0123456789abcdef" for character in approved_missing_hash
    ):
        raise EvidenceDrift("approved missing object-key SHA-256 is invalid")

    authorities = tuple(
        sorted(MediaOperationAuthority.from_token(value) for value in allowed_media_authorities)
    )
    if not authorities or len(set(authorities)) != len(authorities):
        raise EvidenceDrift("operation media authorities must be non-empty and unique")
    output = Path(output_root).resolve()
    if output.exists():
        raise FileExistsError(f"v3 operation preflight root already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)
    copied_capability = output / "minio_capability.v1.json"
    copied_reconciliation = output / "reconciliation.v1.json"
    capability_copy_sha = _copy_create_new(capability_path, copied_capability)
    reconciliation_copy_sha = _copy_create_new(
        reconciliation_path, copied_reconciliation
    )
    bundle_path = output / "preflight_bundle.v1.json"

    def source_reference(path: Path) -> str:
        return os.path.relpath(path, output).replace("\\", "/")

    _write_create_new(
        bundle_path,
        {
            "schema_version": "evb.minio-operation-preflight/v1",
            "build_manifest_path": source_reference(build_path),
            "build_manifest_sha256": expected_build_manifest_sha256,
            "baseline_path": source_reference(baseline_path),
            "baseline_sha256": expected_baseline_sha256,
            "before_inventory_path": source_reference(inventory_path),
            "before_inventory_sha256": inventory_file_sha256,
            "before_inventory_object_sha256": inventory.object_state_sha256,
            "approved_missing_object_keys_sha256": approved_missing_hash,
            "allowed_media_authorities": [item.to_json() for item in authorities],
            "sidecars": [
                {
                    "name": "minio_capability",
                    "path": copied_capability.name,
                    "sha256": capability_copy_sha,
                    "source_path": source_reference(capability_path),
                },
                {
                    "name": "reconciliation",
                    "path": copied_reconciliation.name,
                    "sha256": reconciliation_copy_sha,
                    "source_path": source_reference(reconciliation_path),
                },
            ],
            "created_at_utc": _utc_now(),
        },
    )
    return {
        "preflight_bundle": bundle_path,
        "capability": copied_capability,
        "reconciliation": copied_reconciliation,
    }


def client_from_env(endpoint: str, access_key_env: str, secret_key_env: str) -> Minio:
    access_key = os.environ.get(access_key_env)
    secret_key = os.environ.get(secret_key_env)
    if not access_key or not secret_key:
        raise ValueError("MinIO credential environment variables are required")
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)


def _metadata(value: object) -> dict[str, str]:
    raw = getattr(value, "metadata", {}) or {}
    return {str(key).lower(): str(item) for key, item in raw.items()}


def capture_object_inventory(
    client: object, bucket: str, prefix: str
) -> dict[str, object]:
    normalized_prefix = prefix.rstrip("/")
    try:
        policy_raw = client.get_bucket_policy(bucket)
    except S3Error as error:
        if error.code == "NoSuchBucketPolicy":
            policy_summary = "absent"
        else:
            raise
    else:
        try:
            policy = json.loads(policy_raw)
            policy_bytes = canonical_bytes(policy)
        except json.JSONDecodeError:
            policy_bytes = str(policy_raw).encode("utf-8")
        policy_summary = f"sha256:{_sha256(policy_bytes)}"
    list_prefix = normalized_prefix + "/" if normalized_prefix else ""
    objects = []
    for listed in client.list_objects(bucket, prefix=list_prefix, recursive=True):
        key = str(listed.object_name)
        stat = client.stat_object(bucket, key)
        response = client.get_object(bucket, key)
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        size = 0
        try:
            stream = getattr(response, "stream", None)
            chunks: Iterable[bytes]
            if callable(stream):
                chunks = stream(1024 * 1024)
            else:
                chunks = (response.read(),)
            for chunk in chunks:
                if chunk:
                    sha1.update(chunk)
                    sha256.update(chunk)
                    size += len(chunk)
        finally:
            response.close()
            response.release_conn()
        metadata = _metadata(stat)
        etag = str(getattr(stat, "etag", "") or "").strip('"')
        if not etag:
            raise EvidenceDrift(f"empty ETag for {key}")
        objects.append({
            "object_key": key,
            "size": size,
            "sha1": sha1.hexdigest(),
            "sha256": sha256.hexdigest(),
            "etag": etag,
            "version_id": getattr(stat, "version_id", None),
            "application_operation_id": (
                metadata.get("x-amz-meta-evb-operation-id")
                or metadata.get("evb-operation-id")
            ),
            "audit_event_id": (
                metadata.get("x-amz-meta-evb-audit-event-id")
                or metadata.get("evb-audit-event-id")
            ),
        })
    objects.sort(key=lambda item: str(item["object_key"]))
    inventory: dict[str, object] = {
        "schema_version": "evb.minio-inventory/v1",
        "bucket": bucket,
        "prefix": normalized_prefix,
        "bucket_policy_summary": policy_summary,
        "captured_at_utc": _utc_now(),
        "inventory_sha256": "",
        "object_count": len(objects),
        "objects": objects,
    }
    inventory["inventory_sha256"] = _sha256(canonical_bytes({
        key: value for key, value in inventory.items()
        if key not in {"inventory_sha256", "object_count"}
    }))
    return inventory


def _execute_probe(
    client: object,
    *,
    bucket: str,
    key: str,
    payload: bytes,
    operation_id: str,
    probe_id: str,
) -> object:
    try:
        return client._execute(
            method="PUT",
            bucket_name=bucket,
            object_name=key,
            body=payload,
            headers={
                "If-None-Match": "*",
                "Content-Type": "application/octet-stream",
                "x-amz-meta-evb-operation-id": operation_id,
                "x-amz-meta-evb-audit-event-id": probe_id,
            },
        )
    except ProbeRequestFailed:
        raise
    except S3Error as error:
        if error.code in {"PreconditionFailed", "ConditionalRequestConflict"}:
            raise ProbePreconditionFailed(error.code, error.request_id) from error
        raise ProbeRequestFailed(error.code, error.request_id) from error


def run_capability_probe(
    *,
    client: object,
    endpoint: str,
    bucket: str,
    prefix: str,
    output: Path,
    payload: bytes | None = None,
    operation_id: str | None = None,
    probe_id: str | None = None,
) -> dict[str, object]:
    operation_id = operation_id or str(uuid4())
    probe_id = probe_id or str(uuid4())
    payload = payload or (
        f"EVB conditional probe\nprobe_id={probe_id}\noperation_id={operation_id}\n"
    ).encode("utf-8")
    key = f"{prefix.rstrip('/')}/{probe_id}.bin"
    first = _execute_probe(
        client, bucket=bucket, key=key, payload=payload,
        operation_id=operation_id, probe_id=probe_id,
    )
    try:
        _execute_probe(
            client, bucket=bucket, key=key, payload=payload,
            operation_id=operation_id, probe_id=probe_id,
        )
    except ProbePreconditionFailed as conflict:
        second_code = conflict.code
        second_request_id = conflict.request_id
    else:
        raise EvidenceDrift("second conditional create unexpectedly succeeded")
    response = client.get_object(bucket, key)
    try:
        body = response.read()
    finally:
        response.close()
        response.release_conn()
    stat = client.stat_object(bucket, key)
    metadata = _metadata(stat)
    etag = str(getattr(stat, "etag", "") or "").strip('"')
    if (
        _sha1(body) != _sha1(payload)
        or _sha256(body) != _sha256(payload)
        or len(body) != len(payload)
        or not etag
        or (
            metadata.get("x-amz-meta-evb-operation-id")
            or metadata.get("evb-operation-id")
        ) != operation_id
    ):
        raise EvidenceDrift("capability probe readback or audit mismatch")
    first_headers = {
        str(key).lower(): str(value)
        for key, value in (getattr(first, "headers", {}) or {}).items()
    }
    checked_at = _utc_now()
    details = [
        f"endpoint={endpoint}",
        f"bucket={bucket}",
        f"prefix={prefix.rstrip('/')}",
        f"server_identity={first_headers.get('server', 'MinIO')}",
        f"probe_operation_id={operation_id}",
        f"audit_correlation_id={operation_id}",
        f"checked_at_utc={checked_at}",
        "server_atomic_if_none_match=proven",
        "application_audit_correlation=proven",
        f"probe_object_key={key}",
        f"probe_object_sha1={_sha1(payload)}",
        f"probe_object_sha256={_sha256(payload)}",
        f"probe_object_size={len(payload)}",
        f"probe_object_etag={etag}",
        f"probe_second_result={second_code}",
    ]
    payload_out: dict[str, object] = {
        "schema_version": "evb.minio-capability/v1",
        "conditional_create_supported": True,
        "application_audit_supported": True,
        "durable_replace_supported": False,
        "checked_at_utc": checked_at,
        "details": details,
        "probe_registration": {
            "object_key": key,
            "operation_id": operation_id,
            "audit_event_id": probe_id,
            "second_request_id": second_request_id,
            "retention": "temporary_registered_no_delete",
            "delete_called": False,
        },
    }
    _write_create_new(output, payload_out)
    return payload_out


def normalize_capability_authority(
    source: Path, authority_prefix: str, output: Path
) -> dict[str, object]:
    payload = _read_json(source)
    if payload.get("schema_version") != "evb.minio-capability/v1":
        raise EvidenceDrift("unsupported capability evidence")
    details = payload.get("details")
    if not isinstance(details, list):
        raise EvidenceDrift("capability evidence lacks details")
    prefix_values = [
        str(item).split("=", 1)[1]
        for item in details if str(item).startswith("prefix=")
    ]
    if len(prefix_values) != 1:
        raise EvidenceDrift("capability evidence has ambiguous prefix")
    probe_prefix = prefix_values[0].rstrip("/")
    authority = authority_prefix.rstrip("/")
    if not authority or not probe_prefix.startswith(authority + "/"):
        raise EvidenceDrift("probe prefix is outside capability authority")
    registration = payload.get("probe_registration")
    if not isinstance(registration, dict) or not str(
        registration.get("object_key") or ""
    ).startswith(probe_prefix + "/"):
        raise EvidenceDrift("probe registration is outside probe prefix")
    normalized_details = [
        f"prefix={authority}" if str(item).startswith("prefix=") else str(item)
        for item in details
    ]
    normalized_details.append(f"probe_prefix={probe_prefix}")
    normalized = dict(payload)
    normalized["details"] = normalized_details
    _write_create_new(output, normalized)
    return normalized


def write_receipt(
    *, schema: str, status: str, inputs: Mapping[str, Path],
    fields: Mapping[str, str], output: Path,
) -> dict[str, object]:
    items = []
    for label, path in sorted(inputs.items()):
        resolved = Path(path).resolve(strict=True)
        items.append({"label": label, "path": resolved.as_posix(), "sha256": _file_sha256(resolved)})
    payload: dict[str, object] = {
        "schema_version": schema,
        "status": status,
        "inputs": items,
        "fields": dict(sorted(fields.items())),
    }
    _write_create_new(output, payload)
    return payload


def reconcile_build(
    runtime_media: Path, raw_root: Path, inventory: Mapping[str, object],
    predecessor_sha256: str | None = None,
) -> dict[str, object]:
    if predecessor_sha256 is not None and (
        len(predecessor_sha256) != 64
        or any(character not in "0123456789abcdef" for character in predecessor_sha256)
    ):
        raise EvidenceDrift("invalid predecessor reconciliation SHA-256")
    resolved_raw = Path(raw_root).resolve(strict=True)
    local: dict[str, dict[str, object]] = {}
    missing_declared = 0
    for line in Path(runtime_media).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = str(row.get("object_key") or "")
        if not key:
            continue
        relative = Path(str(row.get("local_relpath") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise EvidenceDrift("local media path escapes raw root")
        source = (resolved_raw / relative).resolve(strict=True)
        source.relative_to(resolved_raw)
        body = source.read_bytes()
        if not row.get("content_sha256"):
            missing_declared += 1
        item = {
            "object_key": key,
            "size": len(body),
            "sha1": _sha1(body),
            "sha256": _sha256(body),
            "asset_type": str(row.get("asset_type") or ""),
            "binding_status": str(row.get("binding_status") or ""),
            "local_relpath": relative.as_posix(),
        }
        previous = local.get(key)
        if previous and _object_state(previous) != _object_state(item):
            raise EvidenceDrift("duplicate local key has divergent content")
        local[key] = item
    remote_items = inventory.get("objects")
    if not isinstance(remote_items, list):
        raise EvidenceDrift("inventory lacks objects")
    remote = {str(item["object_key"]): item for item in remote_items}
    classes: dict[str, list[dict[str, object]]] = {
        "same_hash": [], "missing_remote": [], "hash_mismatch": [], "orphan_remote": []
    }
    for key, item in sorted(local.items()):
        other = remote.get(key)
        if other is None:
            classes["missing_remote"].append(item)
        elif (item["size"], item["sha1"], item["sha256"]) == (
            other.get("size"), other.get("sha1"), other.get("sha256")
        ):
            classes["same_hash"].append(item)
        else:
            classes["hash_mismatch"].append({"local": item, "remote": other})
    for key, item in sorted(remote.items()):
        if key not in local:
            classes["orphan_remote"].append(item)
    result: dict[str, object] = {
        "schema_version": "evb.minio-build-reconciliation/v1",
        "classification_counts": {key: len(value) for key, value in classes.items()},
        "missing_declared_content_sha256_count": missing_declared,
        "classes": classes,
    }
    if predecessor_sha256 is not None:
        result["predecessor_reconciliation_sha256"] = predecessor_sha256
    return result


def _parse_pairs(values: Sequence[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected NAME=VALUE: {value}")
        key, item = value.split("=", 1)
        if not key or key in parsed:
            raise ValueError(f"duplicate or empty name: {key}")
        parsed[key] = item
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    filesystem = sub.add_parser("filesystem-inventory")
    filesystem.add_argument("--root", type=Path, required=True)
    filesystem.add_argument("--output", type=Path, required=True)
    compare_files = sub.add_parser("compare-files")
    compare_files.add_argument("--expected", type=Path, required=True)
    compare_files.add_argument("--actual", type=Path, required=True)
    compare_files.add_argument("--output", type=Path, required=True)
    objects = sub.add_parser("object-inventory")
    capability = sub.add_parser("capability-probe")
    for command in (objects, capability):
        command.add_argument("--endpoint", required=True)
        command.add_argument("--bucket", required=True)
        command.add_argument("--access-key-env", required=True)
        command.add_argument("--secret-key-env", required=True)
        command.add_argument("--output", type=Path, required=True)
    objects.add_argument("--prefix", nargs="?", const="", default="")
    capability.add_argument("--prefix", required=True)
    normalize_capability = sub.add_parser("normalize-capability-authority")
    normalize_capability.add_argument("--input", type=Path, required=True)
    normalize_capability.add_argument("--authority-prefix", required=True)
    normalize_capability.add_argument("--output", type=Path, required=True)
    compare_objects = sub.add_parser("compare-objects")
    compare_objects.add_argument("--expected", type=Path, required=True)
    compare_objects.add_argument("--actual", type=Path, required=True)
    compare_objects.add_argument("--allow-added-key", action="append", default=[])
    compare_objects.add_argument("--output", type=Path, required=True)
    receipt = sub.add_parser("receipt")
    receipt.add_argument("--schema", required=True)
    receipt.add_argument("--status", required=True)
    receipt.add_argument("--input", action="append", default=[])
    receipt.add_argument("--field", action="append", default=[])
    receipt.add_argument("--output", type=Path, required=True)
    reconcile = sub.add_parser("reconcile-build")
    reconcile.add_argument("--runtime-media", type=Path, required=True)
    reconcile.add_argument("--raw-root", type=Path, required=True)
    reconcile.add_argument("--inventory", type=Path, required=True)
    reconcile.add_argument("--predecessor-sha256")
    reconcile.add_argument("--output", type=Path, required=True)
    milvus = sub.add_parser("milvus-inventory")
    milvus.add_argument("--endpoint", required=True)
    milvus.add_argument("--database", default="default")
    milvus.add_argument("--output", type=Path, required=True)
    compare_milvus = sub.add_parser("compare-milvus")
    compare_milvus.add_argument("--expected", type=Path, required=True)
    compare_milvus.add_argument("--actual", type=Path, required=True)
    compare_milvus.add_argument("--output", type=Path, required=True)
    media = sub.add_parser("media-samples")
    media.add_argument("--inventory", type=Path, required=True)
    media.add_argument("--base-url", required=True)
    media.add_argument("--asset-type", action="append", required=True)
    media.add_argument("--output", type=Path, required=True)
    c19 = sub.add_parser("prepare-c19-evidence")
    c19.add_argument("--artifact-root", type=Path, required=True)
    c19.add_argument("--baseline", type=Path, required=True)
    c19.add_argument("--current-inventory", type=Path, required=True)
    c19.add_argument("--capability", type=Path, required=True)
    c19.add_argument("--reconciliation", type=Path, required=True)
    c19.add_argument("--output-root", type=Path, required=True)
    v3_operation = sub.add_parser("prepare-v3-operation-evidence")
    v3_operation.add_argument("--build-manifest", type=Path, required=True)
    v3_operation.add_argument("--expected-build-manifest-sha256", required=True)
    v3_operation.add_argument("--baseline", type=Path, required=True)
    v3_operation.add_argument("--expected-baseline-sha256", required=True)
    v3_operation.add_argument("--current-inventory", type=Path, required=True)
    v3_operation.add_argument("--capability", type=Path, required=True)
    v3_operation.add_argument("--expected-capability-sha256", required=True)
    v3_operation.add_argument("--reconciliation", type=Path, required=True)
    v3_operation.add_argument("--expected-reconciliation-sha256", required=True)
    v3_operation.add_argument("--allow-media-authority", action="append", required=True)
    v3_operation.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "filesystem-inventory":
            capture_filesystem_inventory(args.root, args.output)
        elif args.command == "compare-files":
            result = compare_file_payloads(_read_json(args.expected), _read_json(args.actual))
            _write_create_new(args.output, result)
        elif args.command == "object-inventory":
            client = client_from_env(args.endpoint, args.access_key_env, args.secret_key_env)
            _write_create_new(
                args.output, capture_object_inventory(client, args.bucket, args.prefix)
            )
        elif args.command == "compare-objects":
            result = compare_object_payloads(
                _read_json(args.expected), _read_json(args.actual),
                allowed_added_keys=set(args.allow_added_key),
            )
            _write_create_new(args.output, result)
        elif args.command == "capability-probe":
            client = client_from_env(args.endpoint, args.access_key_env, args.secret_key_env)
            run_capability_probe(
                client=client, endpoint=args.endpoint, bucket=args.bucket,
                prefix=args.prefix, output=args.output,
            )
        elif args.command == "normalize-capability-authority":
            normalize_capability_authority(
                args.input, args.authority_prefix, args.output
            )
        elif args.command == "receipt":
            write_receipt(
                schema=args.schema, status=args.status,
                inputs={key: Path(value) for key, value in _parse_pairs(args.input).items()},
                fields=_parse_pairs(args.field), output=args.output,
            )
        elif args.command == "reconcile-build":
            result = reconcile_build(
                args.runtime_media, args.raw_root, _read_json(args.inventory),
                predecessor_sha256=args.predecessor_sha256,
            )
            if result["classification_counts"]["hash_mismatch"]:
                raise EvidenceDrift("build reconciliation contains hash mismatch")
            _write_create_new(args.output, result)
        elif args.command == "prepare-v3-operation-evidence":
            prepare_v3_operation_evidence(
                build_manifest=args.build_manifest,
                expected_build_manifest_sha256=args.expected_build_manifest_sha256,
                baseline=args.baseline,
                expected_baseline_sha256=args.expected_baseline_sha256,
                current_inventory=args.current_inventory,
                capability=args.capability,
                expected_capability_sha256=args.expected_capability_sha256,
                reconciliation=args.reconciliation,
                expected_reconciliation_sha256=args.expected_reconciliation_sha256,
                allowed_media_authorities=tuple(args.allow_media_authority),
                output_root=args.output_root,
            )
        elif args.command == "milvus-inventory":
            from pymilvus import MilvusClient

            client = MilvusClient(uri=args.endpoint, db_name=args.database)
            _write_create_new(
                args.output,
                capture_milvus_inventory(client, args.endpoint, args.database),
            )
        elif args.command == "compare-milvus":
            _write_create_new(
                args.output,
                compare_milvus_payloads(_read_json(args.expected), _read_json(args.actual)),
            )
        elif args.command == "media-samples":
            _write_create_new(
                args.output,
                verify_media_samples(
                    _read_json(args.inventory), args.base_url, args.asset_type
                ),
            )
        elif args.command == "prepare-c19-evidence":
            prepare_c19_evidence(
                artifact_root=args.artifact_root, baseline=args.baseline,
                current_inventory=args.current_inventory, capability=args.capability,
                reconciliation=args.reconciliation, output_root=args.output_root,
            )
    except (EvidenceDrift, ProbeRequestFailed, FileExistsError, FileNotFoundError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
