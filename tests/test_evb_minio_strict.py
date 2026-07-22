from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from scripts import build_huiji_evb
from config.config import AssetStorageCfg, HuijiCfg
from src.huiji_rag import minio_strict
from src.huiji_rag.builder import strict_object_requests_from_build_manifest
from src.huiji_rag.minio_strict import (
    CapabilityEvidence,
    CapabilityUnavailable,
    ContentHashMismatch,
    EvidenceAlreadyUsed,
    EvidenceMismatch,
    InventoryObject,
    MinioOperationPlan,
    ObjectEvidence,
    ObjectInventory,
    PostCreateReadbackFailure,
    StrictMinioUploader,
    StrictObjectRequest,
    attach_operation_evidence,
    canonical_hash_without,
    capture_object_inventory,
    load_and_claim_operation_plan,
    load_capability_evidence_from_bundle,
    load_operation_plan,
    prepare_upload_inputs,
    validate_capability_authority,
    write_upload_report,
)


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_EMPTY_POLICY_SUMMARY = f"sha256:{_sha256(b'{}')}"


def _inventory_evidence_objects(
    objects: tuple[InventoryObject, ...],
) -> tuple[InventoryObject, ...]:
    return tuple(
        replace(
            item,
            application_operation_id=item.application_operation_id or "fixture-operation",
        )
        for item in objects
    )


def _write_json(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return _sha256(path.read_bytes())


def _capabilities() -> CapabilityEvidence:
    return CapabilityEvidence(
        conditional_create_supported=True,
        application_audit_supported=True,
        durable_replace_supported=False,
        details=(
            "endpoint=127.0.0.1:9002",
            "bucket=reverse1999-assets",
            "prefix=reverse1999",
            "server_identity=minio-test",
            "probe_operation_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "audit_correlation_id=audit-test-1",
            "checked_at_utc=2026-07-12T00:00:00Z",
            "server_atomic_if_none_match=proven",
            "application_audit_correlation=proven",
        ),
        checked_at_utc="2026-07-12T00:00:00Z",
    )


def _write_preflight_bundle(path: Path, capability: CapabilityEvidence | None = None) -> str:
    sidecar_path = path.with_name("minio_capability.v1.json")
    evidence = capability or _capabilities()
    sidecar_sha = _write_json(
        sidecar_path,
        {
            "schema_version": "evb.minio-capability/v1",
            "conditional_create_supported": evidence.conditional_create_supported,
            "application_audit_supported": evidence.application_audit_supported,
            "durable_replace_supported": evidence.durable_replace_supported,
            "details": list(evidence.details),
            "checked_at_utc": evidence.checked_at_utc,
        },
    )
    return _write_json(
        path,
        {
            "schema_version": "evb.preflight-bundle/v1",
            "sidecars": [{"path": sidecar_path.name, "sha256": sidecar_sha}],
        },
    )


def _inventory(path: Path, objects: tuple[InventoryObject, ...] = ()) -> ObjectInventory:
    inventory = ObjectInventory.create(
        bucket="reverse1999-assets",
        prefix="reverse1999",
        objects=_inventory_evidence_objects(objects),
        captured_at_utc="2026-07-12T00:00:00Z",
        bucket_policy_summary=_EMPTY_POLICY_SUMMARY,
    )
    _write_json(path, inventory.to_json())
    return inventory


def _request(root: Path, name: str = "voice.mp3", data: bytes = b"voice") -> StrictObjectRequest:
    local = root / "resources" / name
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    sha1 = _sha1(data)
    return StrictObjectRequest(
        bucket="reverse1999-assets",
        object_key=f"reverse1999/voice/{sha1[:2]}/{sha1}.mp3",
        local_path=local,
        sha1=sha1,
        sha256=_sha256(data),
        size=len(data),
        content_type="audio/mpeg",
        asset_type="voice",
        suffix=".mp3",
    )


def _cli_config(raw_root: Path, processed_root: Path):
    return SimpleNamespace(
        assets=AssetStorageCfg(
            provider="minio",
            endpoint="127.0.0.1:9002",
            public_base_url="http://127.0.0.1:9002",
            bucket_name="reverse1999-assets",
            secure=False,
            object_prefix="reverse1999",
            access_key="minioadmin",
            secret_key="minioadmin",
        ),
        huiji=HuijiCfg(
            enabled=True,
            raw_root=raw_root,
            processed_root=processed_root,
            credential_file=processed_root / "credentials" / "config.dat",
            build_version="build-1",
            text_collection_name="text",
            asset_caption_collection_name="asset",
        ),
    )


def _plan(
    uploader: StrictMinioUploader,
    tmp_path: Path,
    request: StrictObjectRequest | tuple[StrictObjectRequest, ...],
    inventory_objects: tuple[InventoryObject, ...] = (),
    sidecar_capability: CapabilityEvidence | None = None,
) -> MinioOperationPlan:
    baseline = tmp_path / "baseline.json"
    build = tmp_path / "build.json"
    bundle = tmp_path / "bundle.json"
    inventory_path = tmp_path / "inventory.json"
    baseline_hash = _write_json(baseline, {"schema_version": "baseline/v1"})
    build_hash = _write_json(build, {"schema_version": "build/v1"})
    bundle_hash = _write_preflight_bundle(bundle, sidecar_capability)
    _inventory(inventory_path, inventory_objects)
    return uploader.create_operation_plan(
        baseline,
        baseline_hash,
        build,
        build_hash,
        bundle,
        bundle_hash,
        inventory_path,
        _sha256(inventory_path.read_bytes()),
        request if isinstance(request, tuple) else (request,),
        tmp_path / "minio_operation_plan.v1.json",
    )


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class _FakeMinio:
    def __init__(self, readback: bytes = b"voice", execute_error: Exception | None = None) -> None:
        self.readback = readback
        self.execute_error = execute_error
        self.execute_calls: list[SimpleNamespace] = []

    def _execute(self, **kwargs):
        self.execute_calls.append(SimpleNamespace(kwargs=kwargs))
        if self.execute_error is not None:
            raise self.execute_error
        return SimpleNamespace(
            headers={
                "ETag": '"etag-created"',
                "x-amz-version-id": "version-1",
                "x-amz-request-id": "request-1",
            }
        )

    def get_object(self, bucket: str, object_key: str):
        return _Body(self.readback)

    def stat_object(self, bucket: str, object_key: str):
        return SimpleNamespace(etag="etag-readback", version_id="version-1", size=len(self.readback))

    def list_objects(self, bucket: str, prefix: str, recursive: bool):
        return ()

    def get_bucket_policy(self, bucket: str):
        return "{}"


class _ReadbackByKeyMinio(_FakeMinio):
    def __init__(self, readbacks: dict[str, bytes]) -> None:
        super().__init__()
        self.readbacks = readbacks
        self.events: list[tuple[str, str]] = []

    def _execute(self, **kwargs):
        self.events.append(("execute", str(kwargs["object_name"])))
        return super()._execute(**kwargs)

    def get_object(self, bucket: str, object_key: str):
        self.events.append(("readback", object_key))
        return _Body(self.readbacks[object_key])

    def stat_object(self, bucket: str, object_key: str):
        body = self.readbacks[object_key]
        return SimpleNamespace(etag="etag-readback", version_id="version-1", size=len(body))


def test_execute_put_uses_bytes_and_required_headers(tmp_path):
    fake = _FakeMinio()
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    request = _request(tmp_path)
    plan = _plan(uploader, tmp_path, request)
    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        _inventory(tmp_path / "current-inventory.json"),
    )
    operation_id = UUID(str(claimed.used_by_operation_id))

    evidence = uploader.conditional_create(claimed, request, operation_id)

    call = fake.execute_calls[0]
    assert call.kwargs["method"] == "PUT"
    assert isinstance(call.kwargs["body"], bytes)
    assert call.kwargs["headers"]["If-None-Match"] == "*"
    assert call.kwargs["headers"]["Content-Type"] == "audio/mpeg"
    assert call.kwargs["headers"]["x-amz-meta-evb-operation-id"] == str(operation_id)
    assert evidence.operation_audit_id == str(operation_id)
    assert evidence.version_id == "version-1"
    assert evidence.server_request_id == "request-1"


def test_unclaimed_or_mismatched_operation_id_never_executes(tmp_path):
    fake = _FakeMinio()
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    request = _request(tmp_path)
    plan = _plan(uploader, tmp_path, request)

    with pytest.raises(EvidenceMismatch):
        uploader.conditional_create(
            plan, request, UUID("11111111-1111-1111-1111-111111111111")
        )
    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        _inventory(tmp_path / "current-inventory.json"),
    )
    with pytest.raises(EvidenceMismatch):
        uploader.conditional_create(
            claimed, request, UUID("22222222-2222-2222-2222-222222222222")
        )

    assert fake.execute_calls == []


def test_operation_plan_hash_and_claim_are_immutable(tmp_path):
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=tmp_path)
    request = _request(tmp_path)
    plan = _plan(uploader, tmp_path, request)
    plan_path = tmp_path / "minio_operation_plan.v1.json"
    inventory_path = tmp_path / "inventory.json"
    captured_inventory = ObjectInventory.from_json(json.loads(inventory_path.read_text(encoding="utf-8")))
    unchanged_inventory = ObjectInventory.create(
        captured_inventory.bucket,
        captured_inventory.prefix,
        captured_inventory.objects,
        captured_at_utc="2026-07-12T00:05:00Z",
        bucket_policy_summary=captured_inventory.bucket_policy_summary,
    )

    assert plan.operation_plan_sha256 == canonical_hash_without(plan, "operation_plan_sha256")
    assert plan.used_by_operation_id is None
    original = plan_path.read_bytes()

    claimed = load_and_claim_operation_plan(plan_path, plan.operation_plan_sha256, unchanged_inventory)

    assert claimed.used_by_operation_id is not None
    assert plan_path.read_bytes() == original
    with pytest.raises(EvidenceAlreadyUsed):
        load_and_claim_operation_plan(plan_path, plan.operation_plan_sha256, unchanged_inventory)


def test_operation_plan_rejects_noncanonical_bytes(tmp_path):
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=tmp_path)
    plan = _plan(uploader, tmp_path, _request(tmp_path))
    plan_path = tmp_path / "minio_operation_plan.v1.json"

    assert load_operation_plan(plan_path, plan.operation_plan_sha256) == plan
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_path.write_text(json.dumps(payload, indent=4, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(EvidenceMismatch, match="canonical serialization"):
        load_operation_plan(plan_path, plan.operation_plan_sha256)


def test_inventory_and_plan_reject_duplicate_or_noncanonical_order(tmp_path):
    one = InventoryObject(
        "b", None, "", "1" * 40, "2" * 64, 1, application_operation_id="op-1"
    )
    two = InventoryObject(
        "a", None, "", "3" * 40, "4" * 64, 1, application_operation_id="op-2"
    )
    inventory = ObjectInventory.create(
        "bucket", "prefix", (one, two), bucket_policy_summary="absent"
    )
    payload = inventory.to_json()
    payload["objects"] = [payload["objects"][1], payload["objects"][0]]
    payload["inventory_sha256"] = canonical_hash_without(payload, "inventory_sha256")
    path = tmp_path / "inventory.json"
    _write_json(path, payload)

    with pytest.raises(EvidenceMismatch, match="not sorted"):
        ObjectInventory.from_json(json.loads(path.read_text(encoding="utf-8")))

    payload["objects"] = [payload["objects"][0], payload["objects"][0]]
    payload["inventory_sha256"] = canonical_hash_without(payload, "inventory_sha256")
    with pytest.raises(EvidenceMismatch, match="duplicate"):
        ObjectInventory.from_json(payload)


def test_inventory_load_requires_policy_but_allows_missing_historical_operation_id():
    object_without_application_id = InventoryObject(
        "reverse1999/voice/aa/object.mp3", None, "etag", "a" * 40, "b" * 64, 1
    )
    missing_policy = ObjectInventory.create(
        "bucket", "reverse1999", (object_without_application_id,)
    )
    with pytest.raises(EvidenceMismatch, match="bucket policy summary"):
        ObjectInventory.from_json(missing_policy.to_json())

    historical_inventory = ObjectInventory.create(
        "bucket",
        "reverse1999",
        (object_without_application_id,),
        bucket_policy_summary="absent",
    )
    loaded = ObjectInventory.from_json(historical_inventory.to_json())
    assert loaded.objects[0].application_operation_id is None


def test_new_object_evidence_requires_application_operation_id():
    evidence = ObjectEvidence(
        status="created", bucket="bucket",
        object_key="reverse1999/voice/aa/object.mp3", version_id=None,
        etag="etag", server_request_id="request", sha1_before=None,
        sha256_before=None, size_before=None, sha1_after="a" * 40,
        sha256_after="b" * 64, size_after=1, http_readback=True,
        operation_audit_id="unattached",
    )

    with pytest.raises(EvidenceMismatch, match="operation/audit ID"):
        attach_operation_evidence(evidence, "", None)


def test_inventory_load_rejects_empty_object_etag_but_allows_empty_inventory():
    empty = ObjectInventory.create(
        "bucket", "reverse1999", (), bucket_policy_summary="absent"
    )
    assert ObjectInventory.from_json(empty.to_json()).objects == ()

    object_without_etag = InventoryObject(
        "reverse1999/voice/aa/object.mp3",
        None,
        "",
        "a" * 40,
        "b" * 64,
        1,
        application_operation_id="operation-1",
    )
    inventory = ObjectInventory.create(
        "bucket",
        "reverse1999",
        (object_without_etag,),
        bucket_policy_summary="absent",
    )

    with pytest.raises(EvidenceMismatch, match="ETag"):
        ObjectInventory.from_json(inventory.to_json())


def test_capability_details_and_upload_authority_are_exact(tmp_path):
    capability = _capabilities()
    validate_capability_authority(
        capability,
        endpoint="127.0.0.1:9002",
        bucket="reverse1999-assets",
        prefix="reverse1999",
    )
    with pytest.raises(EvidenceMismatch, match="bucket"):
        validate_capability_authority(
            capability,
            endpoint="127.0.0.1:9002",
            bucket="wrong-bucket",
            prefix="reverse1999",
        )

    processed = tmp_path / "processed"
    source_root = tmp_path / "raw"
    operations = processed / "build-1" / "operations"
    request = _request(source_root)
    uploader = StrictMinioUploader(_FakeMinio(), capability, source_root=source_root)
    plan = _plan(uploader, operations, request)
    plan_path = operations / "minio_operation_plan.v1.json"
    report_path = operations / "minio_write_report.v1.json"

    prepared, requests = prepare_upload_inputs(
        plan_path,
        plan.operation_plan_sha256,
        processed_root=processed,
        source_root=source_root,
        endpoint="127.0.0.1:9002",
        bucket="reverse1999-assets",
        prefix="reverse1999",
        report_path=report_path,
    )
    assert prepared == plan
    assert requests[0].local_path == request.local_path.resolve()

    with pytest.raises(EvidenceMismatch, match="authority path"):
        prepare_upload_inputs(
            plan_path,
            plan.operation_plan_sha256,
            processed_root=tmp_path / "other-processed",
            source_root=source_root,
            endpoint="127.0.0.1:9002",
            bucket="reverse1999-assets",
            prefix="reverse1999",
            report_path=report_path,
        )


def test_operation_plan_authority_accepts_exact_legacy_and_global_layouts(tmp_path):
    processed = tmp_path / "processed"
    legacy = processed / "build-1" / "operations" / "minio_operation_plan.v1.json"
    global_plan = (
        processed
        / "operations"
        / "crawler-v3-fill-20260721t000000z"
        / "minio_operation_plan.v1.json"
    )

    assert minio_strict.validate_operation_plan_authority_path(legacy, processed) == legacy.resolve()
    assert (
        minio_strict.validate_operation_plan_authority_path(global_plan, processed)
        == global_plan.resolve()
    )

    rejected = (
        processed / "operations" / "../unsafe" / "minio_operation_plan.v1.json",
        processed / "operations" / "unsafe.id" / "minio_operation_plan.v1.json",
        processed / "operations" / "safe-id" / "plan.json",
        processed / "extra" / "operations" / "safe-id" / "minio_operation_plan.v1.json",
    )
    for path in rejected:
        with pytest.raises(EvidenceMismatch, match="authority path"):
            minio_strict.validate_operation_plan_authority_path(path, processed)


def test_capability_authority_accepts_combined_checked_time_with_server_detail():
    combined = replace(_capabilities(), checked_at_utc="2026-07-12T00:10:00Z")

    validate_capability_authority(
        combined,
        endpoint="127.0.0.1:9002",
        bucket="reverse1999-assets",
        prefix="reverse1999",
    )

    invalid_server_time = replace(
        combined,
        details=tuple(
            "checked_at_utc=not-a-time" if item.startswith("checked_at_utc=") else item
            for item in combined.details
        ),
    )
    with pytest.raises(EvidenceMismatch, match="checked time"):
        validate_capability_authority(
            invalid_server_time,
            endpoint="127.0.0.1:9002",
            bucket="reverse1999-assets",
            prefix="reverse1999",
        )


def test_capability_sidecar_accepts_structured_authority_details(tmp_path):
    sidecar_path = tmp_path / "minio_capability.v1.json"
    sidecar_sha = _write_json(
        sidecar_path,
        {
            "schema_version": "evb.minio-capability/v1",
            "conditional_create_supported": True,
            "application_audit_supported": True,
            "durable_replace_supported": False,
            "details": list(_capabilities().details),
            "checked_at_utc": _capabilities().checked_at_utc,
        },
    )
    bundle_path = tmp_path / "preflight_bundle.v1.json"
    _write_json(
        bundle_path,
        {
            "schema_version": "evb.preflight-bundle/v1",
            "sidecars": [{"path": "minio_capability.v1.json", "sha256": sidecar_sha}],
        },
    )

    evidence = load_capability_evidence_from_bundle(bundle_path)

    validate_capability_authority(
        evidence,
        endpoint="127.0.0.1:9002",
        bucket="reverse1999-assets",
        prefix="reverse1999",
    )


def test_uploader_stops_after_conflict_and_requires_hash_readback(tmp_path):
    from minio.error import S3Error

    conflict = S3Error(
        SimpleNamespace(headers={}),
        "PreconditionFailed",
        "already exists",
        "resource",
        "request-id",
        "host-id",
    )
    fake = _FakeMinio(execute_error=conflict)
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    first = _request(tmp_path, "first.mp3", b"first")
    second = _request(tmp_path, "second.mp3", b"second")
    plan = _plan(uploader, tmp_path, (first, second))
    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        _inventory(tmp_path / "current-inventory.json"),
    )
    report = uploader.upload_sequence(
        claimed,
        (second, first),
        UUID(str(claimed.used_by_operation_id)),
    )

    assert len(fake.execute_calls) == 1
    assert report.status == "concurrency_conflict"
    assert report.objects[1].status == "not_attempted_after_stop"

    mismatch = StrictMinioUploader(_FakeMinio(readback=b"wrong"), _capabilities(), source_root=tmp_path)
    with pytest.raises(ContentHashMismatch):
        mismatch.verify_readback(first)


def test_uploader_rejects_object_set_drift_before_first_write(tmp_path):
    fake = _FakeMinio()
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    planned = _request(tmp_path, "planned.mp3", b"planned")
    extra = _request(tmp_path, "extra.mp3", b"extra")
    plan = _plan(uploader, tmp_path, planned)

    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        _inventory(tmp_path / "current-inventory.json"),
    )
    with pytest.raises(EvidenceMismatch):
        uploader.upload_sequence(
            claimed,
            (planned, extra),
            UUID(str(claimed.used_by_operation_id)),
        )

    assert fake.execute_calls == []


def test_existing_metadata_match_requires_http_readback_and_reports_skip(tmp_path):
    request = _request(tmp_path)
    remote = InventoryObject(
        request.object_key,
        "old-version",
        "old-etag",
        request.sha1,
        request.sha256,
        request.size,
    )
    fake = _FakeMinio(readback=b"voice")
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    plan = _plan(uploader, tmp_path, request, (remote,))
    current = _inventory(tmp_path / "current-inventory.json", (remote,))
    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json", plan.operation_plan_sha256, current
    )

    report = uploader.upload_sequence(
        claimed, (request,), UUID(str(claimed.used_by_operation_id))
    )

    assert fake.execute_calls == []
    assert report.objects[0].status == "same_hash_skip"
    assert report.objects[0].http_readback is True
    assert report.objects[0].sha1_before == request.sha1
    assert report.objects[0].sha1_after == request.sha1

    mismatch_fake = _FakeMinio(readback=b"wrong")
    mismatch = StrictMinioUploader(mismatch_fake, _capabilities(), source_root=tmp_path)
    mismatch_request = _request(tmp_path / "mismatch")
    mismatch_plan = _plan(
        mismatch,
        tmp_path / "mismatch",
        mismatch_request,
        (
            InventoryObject(
                    mismatch_request.object_key,
                    None,
                    "old-etag",
                mismatch_request.sha1,
                mismatch_request.sha256,
                mismatch_request.size,
            ),
        ),
    )
    mismatch_current = ObjectInventory.from_json(
        json.loads((tmp_path / "mismatch" / "inventory.json").read_text(encoding="utf-8"))
    )
    mismatch_claimed = load_and_claim_operation_plan(
        tmp_path / "mismatch" / "minio_operation_plan.v1.json",
        mismatch_plan.operation_plan_sha256,
        mismatch_current,
    )
    mismatch_report = mismatch.upload_sequence(
        mismatch_claimed,
        (mismatch_request,),
        UUID(str(mismatch_claimed.used_by_operation_id)),
    )
    assert mismatch_fake.execute_calls == []
    assert mismatch_report.status == "failed"
    assert mismatch_report.objects[0].status == "hash_mismatch"


def test_all_same_hash_skips_are_read_back_before_first_mixed_order_write(tmp_path):
    root = tmp_path / "source"
    requests = tuple(_request(root, f"voice-{index}.mp3", data) for index, data in enumerate((b"a", b"b", b"c")))
    ordered = sorted(requests, key=lambda item: item.object_key)
    missing = ordered[0]
    skips = ordered[1:]
    inventory_objects = tuple(
        InventoryObject(item.object_key, "v1", "etag", item.sha1, item.sha256, item.size)
        for item in skips
    )
    fake = _ReadbackByKeyMinio(
        {
            missing.object_key: missing.local_path.read_bytes(),
            skips[0].object_key: skips[0].local_path.read_bytes(),
            skips[1].object_key: b"mismatch",
        }
    )
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=root)
    plan = _plan(uploader, tmp_path / "operations", requests, inventory_objects)
    claimed = load_and_claim_operation_plan(
        tmp_path / "operations" / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        ObjectInventory.create(
            plan.bucket,
            plan.prefix,
            _inventory_evidence_objects(inventory_objects),
            bucket_policy_summary=_EMPTY_POLICY_SUMMARY,
        ),
    )

    report = uploader.upload_sequence(
        claimed,
        requests,
        UUID(str(claimed.used_by_operation_id)),
    )

    assert [event for event, _ in fake.events] == ["readback", "readback"]
    assert fake.execute_calls == []
    assert report.status == "failed"
    assert [item.status for item in report.objects] == [
        "not_attempted_after_stop",
        "same_hash_skip",
        "hash_mismatch",
    ]

    success_root = tmp_path / "success-source"
    success_requests = tuple(
        _request(success_root, f"voice-{index}.mp3", data)
        for index, data in enumerate((b"a", b"b", b"c"))
    )
    success_ordered = sorted(success_requests, key=lambda item: item.object_key)
    success_inventory = tuple(
        InventoryObject(item.object_key, "v1", "etag", item.sha1, item.sha256, item.size)
        for item in success_ordered[1:]
    )
    success_fake = _ReadbackByKeyMinio(
        {item.object_key: item.local_path.read_bytes() for item in success_requests}
    )
    success_uploader = StrictMinioUploader(
        success_fake, _capabilities(), source_root=success_root
    )
    success_operations = tmp_path / "success-operations"
    success_plan = _plan(
        success_uploader, success_operations, success_requests, success_inventory
    )
    success_claimed = load_and_claim_operation_plan(
        success_operations / "minio_operation_plan.v1.json",
        success_plan.operation_plan_sha256,
        ObjectInventory.create(
            success_plan.bucket,
            success_plan.prefix,
            _inventory_evidence_objects(success_inventory),
            bucket_policy_summary=_EMPTY_POLICY_SUMMARY,
        ),
    )

    success_report = success_uploader.upload_sequence(
        success_claimed,
        success_requests,
        UUID(str(success_claimed.used_by_operation_id)),
    )

    assert [event for event, _ in success_fake.events[:3]] == [
        "readback",
        "readback",
        "execute",
    ]
    assert success_report.status == "uploaded"


@pytest.mark.parametrize(
    ("source_change", "expected_status"),
    [("missing", "missing_local"), ("changed", "hash_mismatch")],
)
def test_all_conditional_create_sources_validate_before_first_write(
    tmp_path, source_change, expected_status
):
    root = tmp_path / "source"
    requests = tuple(
        sorted(
            (
                _request(root, "first.mp3", b"first"),
                _request(root, "second.mp3", b"second"),
            ),
            key=lambda item: item.object_key,
        )
    )
    fake = _ReadbackByKeyMinio(
        {item.object_key: item.local_path.read_bytes() for item in requests}
    )
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=root)
    operations = tmp_path / "operations"
    plan = _plan(uploader, operations, requests)
    claimed = load_and_claim_operation_plan(
        operations / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        ObjectInventory.create(
            plan.bucket,
            plan.prefix,
            (),
            bucket_policy_summary=_EMPTY_POLICY_SUMMARY,
        ),
    )
    failing = requests[1]
    if source_change == "missing":
        failing.local_path.unlink()
    else:
        failing.local_path.write_bytes(b"changed")

    report = uploader.upload_sequence(
        claimed,
        requests,
        UUID(str(claimed.used_by_operation_id)),
    )

    assert fake.execute_calls == []
    assert report.status == "failed"
    assert [item.status for item in report.objects] == [
        "not_attempted_after_stop",
        expected_status,
    ]


def test_upload_sequence_freezes_all_conditional_create_bytes_before_first_write(tmp_path):
    root = tmp_path / "source"
    requests = tuple(
        sorted(
            (
                _request(root, "first.mp3", b"first-approved"),
                _request(root, "second.mp3", b"second-approved"),
            ),
            key=lambda item: item.object_key,
        )
    )
    approved = {item.object_key: item.local_path.read_bytes() for item in requests}

    class MutatingAfterFirstPutMinio(_ReadbackByKeyMinio):
        def _execute(self, **kwargs):
            response = super()._execute(**kwargs)
            if len(self.execute_calls) == 1:
                requests[1].local_path.write_bytes(b"changed-after-first-put")
            return response

    fake = MutatingAfterFirstPutMinio(approved)
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=root)
    operations = tmp_path / "operations"
    plan = _plan(uploader, operations, requests)
    claimed = load_and_claim_operation_plan(
        operations / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        ObjectInventory.create(
            plan.bucket,
            plan.prefix,
            (),
            bucket_policy_summary=_EMPTY_POLICY_SUMMARY,
        ),
    )

    report = uploader.upload_sequence(
        claimed,
        requests,
        UUID(str(claimed.used_by_operation_id)),
    )

    assert report.status == "uploaded"
    assert len(fake.execute_calls) == 2
    assert {
        call.kwargs["object_name"]: call.kwargs["body"] for call in fake.execute_calls
    } == approved


def test_after_inventory_delta_allows_only_reported_uploads():
    existing = InventoryObject("reverse1999/voice/aa/existing.mp3", "v1", "etag-1", "a" * 40, "b" * 64, 1)
    uploaded = InventoryObject(
        "reverse1999/voice/bb/uploaded.mp3", "v2", "etag-2", "c" * 40,
        "d" * 64, 2, application_operation_id="operation-1",
    )
    current = ObjectInventory.create("reverse1999-assets", "reverse1999", (existing,))
    after = ObjectInventory.create("reverse1999-assets", "reverse1999", (existing, uploaded))
    evidence = ObjectEvidence(
        status="uploaded",
        bucket="reverse1999-assets",
        object_key=uploaded.object_key,
        version_id=uploaded.version_id,
        etag=uploaded.etag,
        server_request_id="request-1",
        sha1_before=None,
        sha256_before=None,
        size_before=None,
        sha1_after=uploaded.sha1,
        sha256_after=uploaded.sha256,
        size_after=uploaded.size,
        http_readback=True,
        operation_audit_id="operation-1",
    )

    minio_strict.validate_after_inventory_delta(current, after, (evidence,))

    modified = replace(existing, etag="changed")
    with pytest.raises(EvidenceMismatch, match="after inventory drift"):
        minio_strict.validate_after_inventory_delta(
            current,
            ObjectInventory.create("reverse1999-assets", "reverse1999", (modified, uploaded)),
            (evidence,),
        )
    with pytest.raises(EvidenceMismatch, match="after inventory drift"):
        minio_strict.validate_after_inventory_delta(current, after, ())
    with pytest.raises(EvidenceMismatch, match="after inventory drift"):
        minio_strict.validate_after_inventory_delta(
            current,
            ObjectInventory.create("reverse1999-assets", "reverse1999", (uploaded,)),
            (evidence,),
        )


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    [("etag", "different-etag"), ("version_id", "different-version")],
)
def test_after_inventory_delta_binds_available_uploaded_response_ids(field, drifted_value):
    uploaded = InventoryObject(
        "reverse1999/voice/bb/uploaded.mp3",
        "version-1",
        "etag-1",
        "c" * 40,
        "d" * 64,
        2,
    )
    evidence = ObjectEvidence(
        status="uploaded",
        bucket="reverse1999-assets",
        object_key=uploaded.object_key,
        version_id=uploaded.version_id,
        etag=uploaded.etag,
        server_request_id="request-1",
        sha1_before=None,
        sha256_before=None,
        size_before=None,
        sha1_after=uploaded.sha1,
        sha256_after=uploaded.sha256,
        size_after=uploaded.size,
        http_readback=True,
        operation_audit_id="operation-1",
    )
    current = ObjectInventory.create("reverse1999-assets", "reverse1999", ())

    with pytest.raises(EvidenceMismatch, match="after inventory drift"):
        minio_strict.validate_after_inventory_delta(
            current,
            ObjectInventory.create(
                "reverse1999-assets",
                "reverse1999",
                (replace(uploaded, **{field: drifted_value}),),
            ),
            (evidence,),
        )


def test_after_inventory_delta_requires_unchanged_policy_and_nonempty_etags():
    uploaded = InventoryObject(
        "reverse1999/voice/bb/uploaded.mp3",
        None,
        "etag-1",
        "c" * 40,
        "d" * 64,
        2,
    )
    evidence = ObjectEvidence(
        status="uploaded",
        bucket="reverse1999-assets",
        object_key=uploaded.object_key,
        version_id=None,
        etag="etag-1",
        server_request_id="request-1",
        sha1_before=None,
        sha256_before=None,
        size_before=None,
        sha1_after=uploaded.sha1,
        sha256_after=uploaded.sha256,
        size_after=uploaded.size,
        http_readback=True,
        operation_audit_id="operation-1",
    )
    current = ObjectInventory.create(
        "reverse1999-assets", "reverse1999", (), bucket_policy_summary="policy-before"
    )

    with pytest.raises(EvidenceMismatch, match="bucket policy"):
        minio_strict.validate_after_inventory_delta(
            current,
            ObjectInventory.create(
                "reverse1999-assets",
                "reverse1999",
                (uploaded,),
                bucket_policy_summary="policy-after",
            ),
            (evidence,),
        )
    with pytest.raises(EvidenceMismatch, match="ETag"):
        minio_strict.validate_after_inventory_delta(
            replace(current, bucket_policy_summary="policy-before"),
            ObjectInventory.create(
                "reverse1999-assets",
                "reverse1999",
                (uploaded,),
                bucket_policy_summary="policy-before",
            ),
            (replace(evidence, etag=""),),
        )
    with pytest.raises(EvidenceMismatch, match="ETag"):
        minio_strict.validate_after_inventory_delta(
            current,
            ObjectInventory.create(
                "reverse1999-assets",
                "reverse1999",
                (replace(uploaded, etag=""),),
                bucket_policy_summary="policy-before",
            ),
            (evidence,),
        )


@pytest.mark.parametrize("missing_etag", ["put", "readback"])
def test_conditional_create_fails_closed_when_etag_is_missing(tmp_path, missing_etag):
    request = _request(tmp_path)

    class MissingEtagMinio(_FakeMinio):
        def _execute(self, **kwargs):
            response = super()._execute(**kwargs)
            if missing_etag == "put":
                response.headers.pop("ETag")
            return response

        def stat_object(self, bucket: str, object_key: str):
            stat = super().stat_object(bucket, object_key)
            if missing_etag == "readback":
                stat.etag = ""
            return stat

    fake = MissingEtagMinio()
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    plan = _plan(uploader, tmp_path, request)
    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        _inventory(tmp_path / "current-inventory.json"),
    )

    with pytest.raises(PostCreateReadbackFailure, match="ETag"):
        uploader.conditional_create(
            claimed, request, UUID(str(claimed.used_by_operation_id))
        )


def test_capture_inventory_records_read_only_policy_and_application_audit_evidence():
    object_key = "reverse1999/voice/aa/object.mp3"

    class EvidenceMinio:
        def get_bucket_policy(self, bucket: str):
            return '{"Statement":[],"Version":"2012-10-17"}'

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            return (SimpleNamespace(object_name=object_key),)

        def stat_object(self, bucket: str, requested_key: str):
            return SimpleNamespace(
                etag="etag-1",
                version_id=None,
                size=1,
                metadata={
                    "X-Amz-Meta-Sha1": "a" * 40,
                    "X-Amz-Meta-Content-Sha256": "b" * 64,
                    "X-Amz-Meta-Evb-Operation-Id": "operation-1",
                },
            )

    inventory = capture_object_inventory(EvidenceMinio(), "bucket", "reverse1999")

    assert inventory.bucket_policy_summary.startswith("sha256:")
    assert inventory.objects[0].application_operation_id == "operation-1"
    assert inventory.objects[0].audit_event_id is None


def test_capture_inventory_uses_empty_list_prefix_for_bucket_root():
    observed = {}

    class RootInventoryMinio:
        def get_bucket_policy(self, bucket: str):
            return "{}"

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            observed["prefix"] = prefix
            return (SimpleNamespace(object_name="root-object"),)

        def stat_object(self, bucket: str, object_key: str):
            return SimpleNamespace(
                etag="etag-1",
                version_id=None,
                size=1,
                metadata={
                    "X-Amz-Meta-Sha1": "a" * 40,
                    "X-Amz-Meta-Content-Sha256": "b" * 64,
                },
            )

    inventory = capture_object_inventory(RootInventoryMinio(), "a-bucket", "")

    assert observed["prefix"] == ""
    assert inventory.prefix == ""
    assert [item.object_key for item in inventory.objects] == ["root-object"]


def test_capture_inventory_rejects_empty_stat_etag():
    class EmptyEtagMinio:
        def get_bucket_policy(self, bucket: str):
            return "{}"

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            return (SimpleNamespace(object_name="reverse1999/voice/aa/object.mp3"),)

        def stat_object(self, bucket: str, object_key: str):
            return SimpleNamespace(
                etag="",
                version_id=None,
                size=1,
                metadata={
                    "X-Amz-Meta-Sha1": "a" * 40,
                    "X-Amz-Meta-Content-Sha256": "b" * 64,
                    "X-Amz-Meta-Evb-Operation-Id": "operation-1",
                },
            )

    with pytest.raises(CapabilityUnavailable, match="ETag"):
        capture_object_inventory(EmptyEtagMinio(), "bucket", "reverse1999")


@pytest.mark.parametrize("missing_evidence", ["policy"])
def test_capture_inventory_blocks_when_mandatory_gate_evidence_is_unavailable(
    missing_evidence,
):
    class IncompleteMinio:
        def get_bucket_policy(self, bucket: str):
            if missing_evidence == "policy":
                raise PermissionError("policy denied")
            return "{}"

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            return (SimpleNamespace(object_name="reverse1999/voice/aa/object.mp3"),)

        def stat_object(self, bucket: str, object_key: str):
            return SimpleNamespace(
                etag="etag-1",
                version_id=None,
                size=1,
                metadata={
                    "X-Amz-Meta-Sha1": "a" * 40,
                    "X-Amz-Meta-Content-Sha256": "b" * 64,
                },
            )

    with pytest.raises(CapabilityUnavailable, match="inventory evidence"):
        capture_object_inventory(IncompleteMinio(), "bucket", "reverse1999")


def test_capture_inventory_allows_missing_historical_operation_id():
    class HistoricalMinio:
        def get_bucket_policy(self, bucket: str):
            return "{}"

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            return (SimpleNamespace(object_name="reverse1999/voice/aa/object.mp3"),)

        def stat_object(self, bucket: str, object_key: str):
            return SimpleNamespace(
                etag="etag-1", version_id=None, size=1,
                metadata={
                    "X-Amz-Meta-Sha1": "a" * 40,
                    "X-Amz-Meta-Content-Sha256": "b" * 64,
                },
            )

    inventory = capture_object_inventory(HistoricalMinio(), "bucket", "reverse1999")

    assert inventory.objects[0].application_operation_id is None


@pytest.mark.parametrize("failure_stage", ["list", "stat", "get", "read"])
def test_capture_inventory_maps_transport_oserrors_to_capability_unavailable(failure_stage):
    object_key = "reverse1999/voice/aa/object.mp3"

    class FailingBody(_Body):
        def read(self) -> bytes:
            raise OSError("read failed")

    class TransportFailureMinio:
        def get_bucket_policy(self, bucket: str):
            return "{}"

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            if failure_stage == "list":
                raise OSError("list failed")
            return (SimpleNamespace(object_name=object_key),)

        def stat_object(self, bucket: str, requested_key: str):
            if failure_stage == "stat":
                raise OSError("stat failed")
            return SimpleNamespace(
                etag="etag-1",
                version_id=None,
                size=1,
                metadata={"X-Amz-Meta-Evb-Operation-Id": "operation-1"},
            )

        def get_object(self, bucket: str, requested_key: str):
            if failure_stage == "get":
                raise OSError("get failed")
            return FailingBody(b"x") if failure_stage == "read" else _Body(b"x")

    with pytest.raises(CapabilityUnavailable, match="inventory evidence"):
        capture_object_inventory(TransportFailureMinio(), "bucket", "reverse1999")


def test_prepare_upload_inputs_rejects_capability_provenance_drift(tmp_path):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    drifted = replace(
        _capabilities(),
        details=tuple(
            "server_identity=minio-other" if item.startswith("server_identity=") else item
            for item in _capabilities().details
        ),
    )
    uploader = StrictMinioUploader(_FakeMinio(), drifted, source_root=raw_root)
    plan = _plan(uploader, operations, request)

    with pytest.raises(EvidenceMismatch, match="capability provenance"):
        prepare_upload_inputs(
            operations / "minio_operation_plan.v1.json",
            plan.operation_plan_sha256,
            processed_root=processed,
            source_root=raw_root,
            endpoint="127.0.0.1:9002",
            bucket="reverse1999-assets",
            prefix="reverse1999",
            report_path=operations / "minio_write_report.v1.json",
        )


def test_prepare_upload_inputs_rejects_additional_server_proof_digest_drift(tmp_path):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    planned_capability = replace(
        _capabilities(), details=(*_capabilities().details, "server_proof_digest=planned")
    )
    sidecar_capability = replace(
        _capabilities(), details=(*_capabilities().details, "server_proof_digest=sidecar")
    )
    uploader = StrictMinioUploader(
        _FakeMinio(), planned_capability, source_root=raw_root
    )
    plan = _plan(
        uploader,
        operations,
        request,
        sidecar_capability=sidecar_capability,
    )

    with pytest.raises(EvidenceMismatch, match="capability provenance"):
        prepare_upload_inputs(
            operations / "minio_operation_plan.v1.json",
            plan.operation_plan_sha256,
            processed_root=processed,
            source_root=raw_root,
            endpoint="127.0.0.1:9002",
            bucket="reverse1999-assets",
            prefix="reverse1999",
            report_path=operations / "minio_write_report.v1.json",
        )


def test_build_manifest_preserves_existing_same_hash_objects_for_operation_plan(tmp_path):
    source_root = tmp_path / "source"
    build_root = tmp_path / "build"
    runtime = build_root / "runtime" / "media_assets.v2.jsonl"
    data = b"voice"
    request = _request(source_root, data=data)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(
        json.dumps(
            {
                "asset_type": "voice",
                "binding_status": "exact",
                "sha1": request.sha1,
                "content_sha256": request.sha256,
                "object_key": request.object_key,
                "local_relpath": request.local_path.relative_to(source_root).as_posix(),
                "mime": request.content_type,
                "filename": "voice.mp3",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = build_root / "runtime" / "media_assets.v2.manifest.json"
    _write_json(
        manifest,
        {
            "file_paths": {"media_assets_v2": "runtime/media_assets.v2.jsonl"},
            "file_sha256": {"media_assets_v2": _sha256(runtime.read_bytes())},
        },
    )
    build_manifest = build_root / "build_manifest.json"
    _write_json(
        build_manifest,
        {"schema_version": "evb.build-manifest/v1", "media_artifact_manifest": "runtime/media_assets.v2.manifest.json"},
    )
    inventory = ObjectInventory.create(
        "reverse1999-assets",
        "reverse1999",
        (
            InventoryObject(
                request.object_key,
                "old-version",
                "old-etag",
                request.sha1,
                request.sha256,
                request.size,
            ),
        ),
        captured_at_utc="2026-07-12T00:00:00Z",
    )

    requests = strict_object_requests_from_build_manifest(build_manifest, inventory, source_root)

    assert requests == (request,)


def test_post_put_readback_failure_retains_response_and_stops(tmp_path):
    fake = _FakeMinio(readback=b"wrong")
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    first = _request(tmp_path, "first.mp3", b"first")
    second = _request(tmp_path, "second.mp3", b"second")
    plan = _plan(uploader, tmp_path, (first, second))
    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        _inventory(tmp_path / "current-inventory.json"),
    )

    report = uploader.upload_sequence(
        claimed, (first, second), UUID(str(claimed.used_by_operation_id))
    )

    assert len(fake.execute_calls) == 1
    assert report.objects[0].status == "hash_mismatch"
    assert report.objects[0].etag == "etag-created"
    assert report.objects[0].version_id == "version-1"
    assert report.objects[0].server_request_id == "request-1"
    assert report.objects[1].status == "not_attempted_after_stop"


def test_upload_report_binds_plan_inventories_and_immutable_report_hash(tmp_path):
    fake = _FakeMinio()
    uploader = StrictMinioUploader(fake, _capabilities(), source_root=tmp_path)
    request = _request(tmp_path)
    plan = _plan(uploader, tmp_path, request)
    current = _inventory(tmp_path / "current-inventory.json")
    claimed = load_and_claim_operation_plan(
        tmp_path / "minio_operation_plan.v1.json",
        plan.operation_plan_sha256,
        current,
    )

    report = uploader.upload_sequence(
        claimed,
        (request,),
        UUID(str(claimed.used_by_operation_id)),
        current_inventory=current,
        after_inventory=current,
    )
    report_path = tmp_path / "minio_write_report.v1.json"
    written = write_upload_report(report_path, report)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert written.operation_plan_sha256 == plan.operation_plan_sha256
    assert written.before_inventory_sha256 == plan.before_inventory_sha256
    assert written.current_inventory_sha256 == current.inventory_sha256
    assert written.after_inventory_sha256 == current.inventory_sha256
    assert written.report_sha256
    assert payload["report_sha256"] == written.report_sha256


@pytest.mark.parametrize(
    "missing_option",
    (
        "--expected-baseline-sha256",
        "--expected-build-manifest-sha256",
        "--expected-preflight-bundle-sha256",
        "--expected-before-inventory-sha256",
    ),
)
def test_minio_cli_requires_all_expected_hashes_before_client(
    tmp_path, monkeypatch, capsys, missing_option
):
    calls: list[object] = []
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: calls.append(object()))
    args = [
        "minio-plan",
        "--baseline", str(tmp_path / "baseline.json"),
        "--expected-baseline-sha256", "a" * 64,
        "--build-manifest", str(tmp_path / "build.json"),
        "--expected-build-manifest-sha256", "b" * 64,
        "--preflight-bundle", str(tmp_path / "bundle.json"),
        "--expected-preflight-bundle-sha256", "c" * 64,
        "--before-inventory", str(tmp_path / "inventory.json"),
        "--expected-before-inventory-sha256", "d" * 64,
        "--output", str(tmp_path / "plan.json"),
    ]
    index = args.index(missing_option)
    del args[index:index + 2]

    with pytest.raises(SystemExit) as error:
        build_huiji_evb.main(args)

    assert error.value.code == 2
    assert missing_option in capsys.readouterr().err
    assert calls == []


def test_minio_plan_filters_verified_existing_objects_from_write_plan(tmp_path):
    existing = _request(tmp_path, "existing.mp3", b"existing")
    missing = _request(tmp_path, "missing.mp3", b"missing")
    inventory = ObjectInventory.create(
        "reverse1999-assets", "reverse1999",
        (InventoryObject(
            existing.object_key, None, "etag", existing.sha1,
            existing.sha256, existing.size,
        ),),
    )

    result = build_huiji_evb._missing_plan_requests((existing, missing), inventory)

    assert result == (missing,)


def test_minio_upload_validates_plan_inputs_before_client_construction(tmp_path, monkeypatch, capsys):
    source_root = tmp_path / "source"
    processed = source_root / "data" / "processed" / "huiji"
    operations = processed / "build-1" / "operations"
    request = _request(source_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=source_root)
    plan = _plan(uploader, operations, request)
    plan_path = operations / "minio_operation_plan.v1.json"
    report_path = operations / "minio_write_report.v1.json"
    (operations / "baseline.json").write_text("tampered\n", encoding="utf-8")
    calls: list[object] = []
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: calls.append(object()))
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=source_root, processed_root=processed),
    )
    monkeypatch.setattr(
        build_huiji_evb,
        "_minio_authority",
        lambda: ("127.0.0.1:9002", "reverse1999-assets", "reverse1999"),
        raising=False,
    )

    with pytest.raises(SystemExit) as error:
        build_huiji_evb.main(
            [
                "minio-upload",
                "--operation-plan",
                str(plan_path),
                "--expected-plan-sha256",
                plan.operation_plan_sha256,
                "--report",
                str(report_path),
            ]
        )

    assert error.value.code == 2
    assert "baseline" in capsys.readouterr().err
    assert calls == []


@pytest.mark.parametrize("sidecar_state", ("tampered", "missing"))
def test_minio_upload_revalidates_capability_sidecar_before_client(
    tmp_path, monkeypatch, capsys, sidecar_state
):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    sidecar = operations / "minio_capability.v1.json"
    if sidecar_state == "tampered":
        sidecar.write_text("tampered\n", encoding="utf-8")
    else:
        sidecar.unlink()
    calls: list[object] = []
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: calls.append(object()))
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(operations / "minio_write_report.v1.json"),
        ]
    )

    assert exit_code == 3
    assert "capability sidecar" in capsys.readouterr().err
    assert calls == []


def test_prepare_upload_inputs_requires_capability_sidecar_authority(tmp_path):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    bad_sidecar_capability = replace(
        _capabilities(),
        details=tuple(
            "bucket=wrong-bucket" if item.startswith("bucket=") else item
            for item in _capabilities().details
        ),
    )
    bundle = operations / "bundle.json"
    baseline = operations / "baseline.json"
    build = operations / "build.json"
    inventory_path = operations / "inventory.json"
    baseline_hash = _write_json(baseline, {"schema_version": "baseline/v1"})
    build_hash = _write_json(build, {"schema_version": "build/v1"})
    bundle_hash = _write_preflight_bundle(bundle, bad_sidecar_capability)
    _inventory(inventory_path)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = uploader.create_operation_plan(
        baseline,
        baseline_hash,
        build,
        build_hash,
        bundle,
        bundle_hash,
        inventory_path,
        _sha256(inventory_path.read_bytes()),
        (request,),
        operations / "minio_operation_plan.v1.json",
    )

    with pytest.raises(EvidenceMismatch, match="capability bucket"):
        prepare_upload_inputs(
            operations / "minio_operation_plan.v1.json",
            plan.operation_plan_sha256,
            processed_root=processed,
            source_root=raw_root,
            endpoint="127.0.0.1:9002",
            bucket="reverse1999-assets",
            prefix="reverse1999",
            report_path=operations / "minio_write_report.v1.json",
        )


def test_minio_upload_uses_configured_huiji_roots_before_client(tmp_path, monkeypatch, capsys):
    repo_root = tmp_path / "repo"
    raw_root = repo_root / "data" / "huiji" / "res1999"
    processed = repo_root / "data" / "processed" / "huiji"
    outside_raw = repo_root / "outside-raw"
    operations = processed / "build-1" / "operations"
    request = _request(outside_raw)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=outside_raw)
    plan = _plan(uploader, operations, request)
    calls: list[object] = []
    monkeypatch.setattr(build_huiji_evb, "PROJECT_ROOT", repo_root)
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: calls.append(object()))
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    with pytest.raises(SystemExit) as error:
        build_huiji_evb.main(
            [
                "minio-upload",
                "--operation-plan",
                str(operations / "minio_operation_plan.v1.json"),
                "--expected-plan-sha256",
                plan.operation_plan_sha256,
                "--report",
                str(operations / "minio_write_report.v1.json"),
            ]
        )

    assert error.value.code == 2
    assert "source root" in capsys.readouterr().err
    assert calls == []


def test_minio_plan_rejects_unfixed_output_before_client(tmp_path, monkeypatch, capsys):
    calls: list[object] = []
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: calls.append(object()) or object())
    monkeypatch.setattr(build_huiji_evb, "_validate_path_hash", lambda path, expected, label: Path(path).resolve())
    monkeypatch.setattr(
        build_huiji_evb,
        "load_object_inventory",
        lambda path: ObjectInventory.create("reverse1999-assets", "reverse1999", ()),
    )
    monkeypatch.setattr(
        build_huiji_evb,
        "strict_object_requests_from_build_manifest",
        lambda build, inventory, source_root: (),
    )
    monkeypatch.setattr(build_huiji_evb, "local_capability_evidence", lambda client: _capabilities())
    monkeypatch.setattr(build_huiji_evb, "load_capability_evidence_from_bundle", lambda bundle: _capabilities())
    monkeypatch.setattr(build_huiji_evb, "PROJECT_ROOT", tmp_path / "source")
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(
            raw_root=tmp_path / "source",
            processed_root=tmp_path / "source" / "data" / "processed" / "huiji",
        ),
    )

    with pytest.raises(SystemExit) as error:
        build_huiji_evb.main(
            [
                "minio-plan",
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--expected-baseline-sha256",
                "a" * 64,
                "--build-manifest",
                str(tmp_path / "build.json"),
                "--expected-build-manifest-sha256",
                "b" * 64,
                "--preflight-bundle",
                str(tmp_path / "bundle.json"),
                "--expected-preflight-bundle-sha256",
                "c" * 64,
                "--before-inventory",
                str(tmp_path / "inventory.json"),
                "--expected-before-inventory-sha256",
                "d" * 64,
                "--output",
                str(tmp_path / "wrong" / "plan.json"),
            ]
        )

    assert error.value.code == 2
    assert "operation plan authority path" in capsys.readouterr().err
    assert calls == []


def test_v3_minio_plan_cli_writes_unclaimed_plan_without_transport_mutation(
    tmp_path, monkeypatch
):
    repo_root = tmp_path / "repo"
    raw_root = repo_root / "raw"
    processed_root = repo_root / "processed"
    request = _request(raw_root)
    baseline = repo_root / "baseline.json"
    baseline_sha = _write_json(baseline, {"schema_version": "baseline/v1"})
    build = repo_root / "candidate" / "build_manifest.json"
    build_sha = _write_json(
        build,
        {
            "schema_version": "huiji.corpus-build/v2",
            "artifact_schema_version": "evb.media-asset/v3",
            "artifacts": [],
        },
    )
    inventory_path = repo_root / "inventory.json"
    inventory = _inventory(inventory_path)
    inventory_sha = _sha256(inventory_path.read_bytes())
    preflight_root = repo_root / "preflight"
    capability_path = preflight_root / "minio_capability.v1.json"
    capability = _capabilities()
    capability_sha = _write_json(
        capability_path,
        {
            "schema_version": "evb.minio-capability/v1",
            "conditional_create_supported": True,
            "application_audit_supported": True,
            "durable_replace_supported": False,
            "details": list(capability.details),
            "checked_at_utc": capability.checked_at_utc,
        },
    )
    missing_key_sha = minio_strict.ordered_object_keys_sha256([request.object_key])
    reconciliation_path = preflight_root / "reconciliation.v1.json"
    reconciliation_sha = _write_json(
        reconciliation_path,
        {
            "schema_version": "huiji.candidate-minio-reconciliation/v1",
            "candidate_build_manifest_sha256": build_sha,
            "current_inventory": {
                "object_state_sha256": inventory.object_state_sha256,
            },
            "classification": {
                "hash_mismatch_count": 0,
                "missing_remote_unique_object_count": 1,
                "missing_role_counts": {"voice": 1},
                "ordered_missing_object_keys_sha256": missing_key_sha,
            },
        },
    )
    bundle = preflight_root / "preflight_bundle.v1.json"
    bundle_sha = _write_json(
        bundle,
        {
            "schema_version": "evb.minio-operation-preflight/v1",
            "build_manifest_sha256": build_sha,
            "baseline_sha256": baseline_sha,
            "before_inventory_sha256": inventory_sha,
            "before_inventory_object_sha256": inventory.object_state_sha256,
            "approved_missing_object_keys_sha256": missing_key_sha,
            "allowed_media_authorities": [
                {
                    "asset_type": "voice",
                    "media_role": "voice",
                    "binding_status": "exact",
                    "mime": "audio/mpeg",
                    "suffix": ".mp3",
                }
            ],
            "sidecars": [
                {
                    "name": "minio_capability",
                    "path": capability_path.name,
                    "sha256": capability_sha,
                },
                {
                    "name": "reconciliation",
                    "path": reconciliation_path.name,
                    "sha256": reconciliation_sha,
                },
            ],
        },
    )
    resolution = SimpleNamespace(
        all_requests=(request,),
        missing_requests=(request,),
        candidate_unique_object_count=1,
        missing_binding_count=1,
        same_hash_count=0,
        missing_remote_count=1,
        hash_mismatch_count=0,
        orphan_remote_count=0,
        missing_authority_counts=(("voice/voice", 1),),
        ordered_missing_object_keys_sha256=missing_key_sha,
        to_json=lambda: {
            "schema_version": "huiji.v3-minio-request-resolution/v1",
            "missing_remote_count": 1,
            "ordered_missing_object_keys_sha256": missing_key_sha,
        },
    )
    fake = _FakeMinio()
    sdk_capability = CapabilityEvidence(
        conditional_create_supported=True,
        application_audit_supported=True,
        durable_replace_supported=False,
        details=("minio-sdk:7.2.20", "private-execute:available"),
        checked_at_utc="2026-07-21T00:00:00Z",
    )
    monkeypatch.setattr(build_huiji_evb, "PROJECT_ROOT", repo_root)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed_root),
    )
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(
        build_huiji_evb, "local_capability_evidence", lambda client: sdk_capability
    )
    monkeypatch.setattr(
        build_huiji_evb,
        "resolve_strict_object_requests_from_build_manifest",
        lambda *args, **kwargs: resolution,
    )
    operation_root = processed_root / "operations" / "v3-plan-fixture"
    plan_path = operation_root / "minio_operation_plan.v1.json"
    resolution_path = operation_root / "minio_plan_resolution.v1.json"

    status = build_huiji_evb.main(
        [
            "minio-plan",
            "--baseline",
            str(baseline),
            "--expected-baseline-sha256",
            baseline_sha,
            "--build-manifest",
            str(build),
            "--expected-build-manifest-sha256",
            build_sha,
            "--preflight-bundle",
            str(bundle),
            "--expected-preflight-bundle-sha256",
            bundle_sha,
            "--before-inventory",
            str(inventory_path),
            "--expected-before-inventory-sha256",
            inventory_sha,
            "--resolution-report",
            str(resolution_path),
            "--output",
            str(plan_path),
        ]
    )

    assert status == 0
    assert fake.execute_calls == []
    plan = load_operation_plan(
        plan_path,
        json.loads(plan_path.read_text(encoding="utf-8"))["operation_plan_sha256"],
    )
    assert len(plan.objects) == 1
    assert plan.objects[0].disposition == "conditional_create"
    assert plan.used_by_operation_id is None
    prepared, prepared_requests = prepare_upload_inputs(
        plan_path,
        plan.operation_plan_sha256,
        processed_root=processed_root,
        source_root=raw_root,
        endpoint="127.0.0.1:9002",
        bucket="reverse1999-assets",
        prefix="reverse1999",
        report_path=operation_root / "minio_write_report.v1.json",
    )
    assert prepared == plan
    assert prepared_requests == (request,)
    assert resolution_path.is_file()
    assert not operation_root.joinpath("minio_operation_plan.use.v1.json").exists()
    assert not operation_root.joinpath("minio_write_report.v1.json").exists()


def test_minio_upload_captures_after_inventory_for_post_put_failure(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    processed = source_root / "data" / "processed" / "huiji"
    operations = processed / "build-1" / "operations"
    request = _request(source_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=source_root)
    plan = _plan(uploader, operations, request)
    plan_path = operations / "minio_operation_plan.v1.json"
    report_path = operations / "minio_write_report.v1.json"
    after_object = InventoryObject(
        request.object_key,
        "created-version",
        "created-etag",
        request.sha1,
        request.sha256,
        request.size,
        application_operation_id="operation-1",
    )
    after_inventory = ObjectInventory.create(
        "reverse1999-assets",
        "reverse1999",
        (after_object,),
        captured_at_utc="2026-07-12T00:01:00Z",
        bucket_policy_summary=_EMPTY_POLICY_SUMMARY,
    )

    class FailingReadbackMinio(_FakeMinio):
        def __init__(self) -> None:
            super().__init__(readback=b"wrong")
            self.list_calls = 0

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            self.list_calls += 1
            if self.list_calls == 1:
                return ()
            return (SimpleNamespace(object_name=request.object_key),)

        def stat_object(self, bucket: str, object_key: str):
            if self.list_calls >= 2:
                return SimpleNamespace(
                    etag=after_object.etag,
                    version_id=after_object.version_id,
                    size=after_object.size,
                    metadata={
                        "X-Amz-Meta-Sha1": after_object.sha1,
                        "X-Amz-Meta-Content-Sha256": after_object.sha256,
                        "X-Amz-Meta-Evb-Operation-Id": "operation-1",
                    },
                )
            return super().stat_object(bucket, object_key)

    fake = FailingReadbackMinio()
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=source_root, processed_root=processed),
    )
    monkeypatch.setattr(
        build_huiji_evb,
        "_minio_authority",
        lambda: ("127.0.0.1:9002", "reverse1999-assets", "reverse1999"),
        raising=False,
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(plan_path),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 5
    assert fake.list_calls == 2
    assert payload["status"] == "failed"
    assert payload["after_inventory_object_sha256"] == after_inventory.object_state_sha256


def test_minio_upload_writes_blocked_report_when_after_inventory_capture_fails(
    tmp_path, monkeypatch
):
    from minio.error import S3Error

    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"
    capture_error = S3Error(
        SimpleNamespace(headers={}),
        "AccessDenied",
        "inventory denied",
        "resource",
        "request-id",
        "host-id",
    )

    class AfterInventoryFailureMinio(_FakeMinio):
        def __init__(self) -> None:
            super().__init__(readback=b"voice")
            self.list_calls = 0

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            self.list_calls += 1
            if self.list_calls == 1:
                return ()
            raise capture_error

    fake = AfterInventoryFailureMinio()
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 5
    assert fake.list_calls == 2
    assert payload["status"] == "blocked"
    assert payload["operation_plan_sha256"] == plan.operation_plan_sha256
    assert payload["current_inventory_sha256"]
    assert payload["after_inventory_sha256"] is None
    assert payload["after_inventory_object_sha256"] is None
    assert payload["after_inventory_capture_error_code"] == "AccessDenied"
    assert payload["after_inventory_capture_request_id"] == "request-id"


def test_minio_upload_after_inventory_drift_writes_failed_report_and_exits_5(
    tmp_path, monkeypatch
):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"
    rogue = InventoryObject(
        "reverse1999/voice/ff/rogue.mp3", "rogue-v1", "rogue-etag", "f" * 40, "e" * 64, 3
    )

    class DriftedAfterInventoryMinio(_FakeMinio):
        def __init__(self) -> None:
            super().__init__()
            self.list_calls = 0

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            self.list_calls += 1
            if self.list_calls == 1:
                return ()
            return (
                SimpleNamespace(object_name=request.object_key),
                SimpleNamespace(object_name=rogue.object_key),
            )

        def stat_object(self, bucket: str, object_key: str):
            if object_key == rogue.object_key:
                item = rogue
            else:
                item = InventoryObject(
                    request.object_key,
                    "version-1",
                    "etag-created",
                    request.sha1,
                    request.sha256,
                    request.size,
                )
            return SimpleNamespace(
                etag=item.etag,
                version_id=item.version_id,
                size=item.size,
                metadata={
                    "X-Amz-Meta-Sha1": item.sha1,
                    "X-Amz-Meta-Content-Sha256": item.sha256,
                    "X-Amz-Meta-Evb-Operation-Id": "operation-1",
                },
            )

    fake = DriftedAfterInventoryMinio()
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 5
    assert payload["status"] == "failed"
    assert payload["after_inventory_sha256"]


def test_minio_upload_current_inventory_s3error_returns_documented_exit_before_claim(
    tmp_path, monkeypatch
):
    from minio.error import S3Error

    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"

    class CurrentInventoryFailureMinio(_FakeMinio):
        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            raise S3Error(
                SimpleNamespace(headers={}),
                "AccessDenied",
                "inventory denied",
                "resource",
                "request-id",
                "host-id",
            )

    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: CurrentInventoryFailureMinio())
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 5
    assert not report_path.exists()
    assert not (operations / "minio_operation_plan.use.v1.json").exists()


def test_minio_upload_unreadable_policy_blocks_before_claim_with_exit_5(
    tmp_path, monkeypatch
):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"

    class PolicyUnavailableMinio(_FakeMinio):
        def get_bucket_policy(self, bucket: str):
            raise PermissionError("policy denied")

    monkeypatch.setattr(
        build_huiji_evb, "_create_minio_client", lambda: PolicyUnavailableMinio()
    )
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 5
    assert not report_path.exists()
    assert not (operations / "minio_operation_plan.use.v1.json").exists()


def test_minio_upload_missing_after_application_audit_writes_blocked_report(
    tmp_path, monkeypatch
):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"

    class MissingAfterAuditMinio(_FakeMinio):
        def __init__(self) -> None:
            super().__init__()
            self.list_calls = 0

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            self.list_calls += 1
            if self.list_calls == 1:
                return ()
            return (SimpleNamespace(object_name=request.object_key),)

        def stat_object(self, bucket: str, object_key: str):
            return SimpleNamespace(
                etag="etag-created",
                version_id="version-1",
                size=request.size,
                metadata={
                    "X-Amz-Meta-Sha1": request.sha1,
                    "X-Amz-Meta-Content-Sha256": request.sha256,
                },
            )

    fake = MissingAfterAuditMinio()
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 5
    assert payload["status"] == "blocked"
    assert (operations / "minio_operation_plan.use.v1.json").is_file()


def test_minio_upload_after_inventory_oserror_writes_blocked_report(tmp_path, monkeypatch):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"

    class AfterInventoryOSErrorMinio(_FakeMinio):
        def __init__(self) -> None:
            super().__init__()
            self.list_calls = 0

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            self.list_calls += 1
            if self.list_calls == 1:
                return ()
            raise OSError("transport failed")

    fake = AfterInventoryOSErrorMinio()
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 5
    assert payload["status"] == "blocked"
    assert payload["after_inventory_capture_error_code"] == "inventory_evidence_unavailable"


@pytest.mark.parametrize("phase", ["before_claim", "after_claim"])
def test_minio_upload_empty_inventory_etag_uses_evidence_unavailable_boundary(
    tmp_path, monkeypatch, phase
):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"

    class EmptyInventoryEtagMinio(_FakeMinio):
        def __init__(self) -> None:
            super().__init__()
            self.list_calls = 0

        def list_objects(self, bucket: str, prefix: str, recursive: bool):
            self.list_calls += 1
            if phase == "after_claim" and self.list_calls == 1:
                return ()
            return (SimpleNamespace(object_name=request.object_key),)

        def stat_object(self, bucket: str, object_key: str):
            return SimpleNamespace(
                etag="",
                version_id=None,
                size=request.size,
                metadata={
                    "X-Amz-Meta-Sha1": request.sha1,
                    "X-Amz-Meta-Content-Sha256": request.sha256,
                    "X-Amz-Meta-Evb-Operation-Id": "operation-1",
                },
            )

    fake = EmptyInventoryEtagMinio()
    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 5
    marker = operations / "minio_operation_plan.use.v1.json"
    if phase == "before_claim":
        assert not marker.exists()
        assert not report_path.exists()
    else:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert marker.is_file()
        assert payload["status"] == "blocked"
        assert payload["after_inventory_capture_error_code"] == "inventory_evidence_unavailable"


@pytest.mark.parametrize(
    ("source_change", "expected_status"),
    [("missing", "missing_local"), ("changed", "hash_mismatch")],
)
def test_minio_upload_reports_post_claim_local_source_failure(
    tmp_path, monkeypatch, source_change, expected_status
):
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    operations = processed / "build-1" / "operations"
    request = _request(raw_root)
    uploader = StrictMinioUploader(_FakeMinio(), _capabilities(), source_root=raw_root)
    plan = _plan(uploader, operations, request)
    report_path = operations / "minio_write_report.v1.json"
    fake = _FakeMinio()

    original_claim = build_huiji_evb.load_and_claim_operation_plan

    def claim_then_change(*args, **kwargs):
        claimed = original_claim(*args, **kwargs)
        if source_change == "missing":
            request.local_path.unlink()
        else:
            request.local_path.write_bytes(b"changed")
        return claimed

    monkeypatch.setattr(build_huiji_evb, "_create_minio_client", lambda: fake)
    monkeypatch.setattr(build_huiji_evb, "load_and_claim_operation_plan", claim_then_change)
    monkeypatch.setattr(
        build_huiji_evb,
        "get_config",
        lambda: _cli_config(raw_root=raw_root, processed_root=processed),
    )

    exit_code = build_huiji_evb.main(
        [
            "minio-upload",
            "--operation-plan",
            str(operations / "minio_operation_plan.v1.json"),
            "--expected-plan-sha256",
            plan.operation_plan_sha256,
            "--report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 5
    assert payload["status"] == "failed"
    assert payload["objects"][0]["status"] == expected_status
    assert fake.execute_calls == []
    assert (operations / "minio_operation_plan.use.v1.json").is_file()
