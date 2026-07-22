from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import minio_blue_green_evidence as migration
from src.huiji_rag.minio_strict import (
    EvidenceMismatch,
    ObjectInventory,
    load_operation_preflight_bundle,
)


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json_fixture(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return _sha256(path.read_bytes())


def test_filesystem_inventory_is_sorted_canonical_and_create_new(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "b.bin").write_bytes(b"b")
    (root / "a.bin").write_bytes(b"a")
    output = tmp_path / "inventory.json"

    payload = migration.capture_filesystem_inventory(root, output)

    assert [item["relative_path"] for item in payload["files"]] == ["a.bin", "b.bin"]
    assert output.read_bytes() == migration.canonical_bytes(payload) + b"\n"
    with pytest.raises(FileExistsError):
        migration.capture_filesystem_inventory(root, output)


def test_compare_files_rejects_any_delta(tmp_path):
    expected = {"schema_version": "evb.filesystem-inventory/v1", "files": []}
    actual = {
        "schema_version": "evb.filesystem-inventory/v1",
        "files": [{"relative_path": "new", "size": 1, "sha256": "a" * 64}],
    }
    with pytest.raises(migration.EvidenceDrift):
        migration.compare_file_payloads(expected, actual)


def test_compare_objects_allows_only_registered_probe_additions():
    base = {
        "bucket": "bucket",
        "prefix": "prefix",
        "bucket_policy_summary": "absent",
        "objects": [{"object_key": "prefix/a", "size": 1, "sha1": "a" * 40,
                     "sha256": "b" * 64, "etag": "etag", "version_id": None}],
    }
    added = {"object_key": "prefix/_evb_capability_probe/p.bin", "size": 1,
             "sha1": "c" * 40, "sha256": "d" * 64, "etag": "probe", "version_id": None}
    actual = {**base, "objects": [*base["objects"], added]}

    result = migration.compare_object_payloads(
        base, actual, allowed_added_keys={added["object_key"]}
    )

    assert result["added_keys"] == [added["object_key"]]
    with pytest.raises(migration.EvidenceDrift):
        migration.compare_object_payloads(base, actual, allowed_added_keys=set())


class _Response:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None):
        self._body = body
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class _ProbeClient:
    def __init__(self, body: bytes, operation_id: str):
        self.body = body
        self.operation_id = operation_id
        self.calls = 0

    def _execute(self, **kwargs):
        self.calls += 1
        if self.calls == 2:
            raise migration.ProbePreconditionFailed("PreconditionFailed", "request-2")
        return SimpleNamespace(headers={"ETag": "probe-etag", "x-amz-request-id": "request-1"})

    def get_object(self, bucket: str, key: str):
        return _Response(self.body)

    def stat_object(self, bucket: str, key: str):
        return SimpleNamespace(
            etag="probe-etag",
            version_id=None,
            size=len(self.body),
            metadata={"x-amz-meta-evb-operation-id": self.operation_id},
        )


def test_capability_probe_requires_200_then_precondition_and_metadata_readback(tmp_path):
    body = b"approved probe"
    operation_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    client = _ProbeClient(body, operation_id)

    payload = migration.run_capability_probe(
        client=client,
        endpoint="127.0.0.1:9002",
        bucket="bucket",
        prefix="prefix/_evb_capability_probe",
        output=tmp_path / "capability.json",
        payload=body,
        operation_id=operation_id,
        probe_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )

    assert payload["conditional_create_supported"] is True
    assert payload["application_audit_supported"] is True
    assert payload["checked_at_utc"].endswith("Z")
    assert any(item.startswith("checked_at_utc=") for item in payload["details"])
    assert client.calls == 2


def test_capability_probe_failure_writes_no_capability_sidecar(tmp_path):
    class Failing:
        def _execute(self, **kwargs):
            raise migration.ProbeRequestFailed("NoSuchKey", "request-1")

    output = tmp_path / "capability.json"
    with pytest.raises(migration.ProbeRequestFailed):
        migration.run_capability_probe(
            client=Failing(), endpoint="e", bucket="b", prefix="p", output=output,
            payload=b"x", operation_id="a", probe_id="b",
        )
    assert not output.exists()


def test_normalize_capability_authority_preserves_probe_registration(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "schema_version": "evb.minio-capability/v1",
        "details": [
            "endpoint=127.0.0.1:9002", "bucket=reverse1999-assets",
            "prefix=reverse1999/_evb_capability_probe",
            "probe_object_key=reverse1999/_evb_capability_probe/id.bin",
        ],
        "probe_registration": {"object_key": "reverse1999/_evb_capability_probe/id.bin"},
    }) + "\n", encoding="utf-8")
    output = tmp_path / "normalized.json"

    result = migration.normalize_capability_authority(
        source, "reverse1999", output
    )

    assert "prefix=reverse1999" in result["details"]
    assert "probe_prefix=reverse1999/_evb_capability_probe" in result["details"]
    assert result["probe_registration"]["object_key"].endswith("id.bin")


def test_receipt_hash_pins_every_named_input(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(b"evidence\n")
    output = tmp_path / "receipt.json"
    payload = migration.write_receipt(
        schema="receipt/v1", status="ready", inputs={"evidence": evidence},
        fields={"target": "fixed"}, output=output,
    )
    assert payload["inputs"][0]["sha256"] == _sha256(evidence.read_bytes())


def test_reconcile_build_hashes_actual_local_bytes_and_separates_missing_declared_sha256(
    tmp_path,
):
    raw = tmp_path / "raw"
    raw.mkdir()
    body = b"image"
    media = raw / "image.webp"
    media.write_bytes(body)
    runtime = tmp_path / "runtime.jsonl"
    runtime.write_text(json.dumps({
        "object_key": f"reverse1999/image/{_sha1(body)[:2]}/{_sha1(body)}.webp",
        "asset_type": "image", "binding_status": "not_applicable",
        "local_relpath": "image.webp", "sha1": _sha1(body), "content_sha256": "",
    }) + "\n", encoding="utf-8")
    inventory = {"objects": [{
        "object_key": f"reverse1999/image/{_sha1(body)[:2]}/{_sha1(body)}.webp",
        "size": len(body), "sha1": _sha1(body), "sha256": _sha256(body),
        "etag": "etag", "version_id": None,
    }]}

    result = migration.reconcile_build(
        runtime, raw, inventory, predecessor_sha256="f" * 64
    )

    assert result["classification_counts"]["same_hash"] == 1
    assert result["missing_declared_content_sha256_count"] == 1
    assert result["classification_counts"]["hash_mismatch"] == 0
    assert result["predecessor_reconciliation_sha256"] == "f" * 64


def test_cli_rejects_missing_credential_env_before_client(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_ACCESS", raising=False)
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    with pytest.raises(ValueError, match="credential"):
        migration.client_from_env(
            "127.0.0.1:9002", "MISSING_ACCESS", "MISSING_SECRET"
        )


def test_source_contains_no_delete_or_bucket_mutation_calls():
    source = Path(migration.__file__).read_text(encoding="utf-8")
    for forbidden in (
        ".remove_object(", ".delete_object(", ".make_bucket(",
        ".set_bucket_policy(", ".put_object(", ".fput_object(",
    ):
        assert forbidden not in source


def test_object_inventory_hashes_streamed_content_and_policy():
    body = b"remote bytes"

    class Client:
        queried_fields = []

        def get_bucket_policy(self, bucket):
            return '{"Version":"1"}'

        def list_objects(self, bucket, prefix, recursive):
            return [SimpleNamespace(object_name="prefix/a.bin")]

        def stat_object(self, bucket, key):
            return SimpleNamespace(
                etag="etag", version_id=None,
                metadata={"x-amz-meta-evb-operation-id": "operation"},
            )

        def get_object(self, bucket, key):
            response = _Response(body)
            response.stream = lambda size: (body[:4], body[4:])
            return response

    result = migration.capture_object_inventory(Client(), "bucket", "prefix")

    assert result["bucket_policy_summary"].startswith("sha256:")
    assert result["objects"][0]["sha1"] == _sha1(body)
    assert result["objects"][0]["sha256"] == _sha256(body)
    assert result["objects"][0]["application_operation_id"] == "operation"
    assert ObjectInventory.from_json(result).object_state_sha256


def test_milvus_inventory_and_comparison_are_read_only_and_deterministic(tmp_path):
    class Client:
        queried_fields = []

        def list_collections(self):
            return ["z", "a"]

        def describe_collection(self, name):
            return {"collection_name": name, "fields": [{"name": "id"}]}

        def list_indexes(self, name):
            return ["idx"]

        def get_collection_stats(self, name):
            return {"row_count": "2"}

        def get_load_state(self, name):
            return {"state": "Loaded"}

        def query(self, collection_name, filter, output_fields, limit):
            self.queried_fields.append(output_fields)
            return [{"id": f"{collection_name}-first"}]

    first = migration.capture_milvus_inventory(Client(), "http://127.0.0.1:19530", "default")
    second = migration.capture_milvus_inventory(Client(), "http://127.0.0.1:19530", "default")

    assert [item["name"] for item in first["collections"]] == ["a", "z"]
    assert Client.queried_fields == [["id"], ["id"], ["id"], ["id"]]
    assert set(first["collections"][0]["first_id_fingerprint"]) == {"field", "sha256"}
    assert "first_row" not in first["collections"][0]
    assert migration.compare_milvus_payloads(first, second)["status"] == "equal"


def test_media_samples_are_deterministic_and_hash_verified():
    voice = b"voice"
    image = b"image"
    inventory = {"objects": [
        {"object_key": "reverse1999/voice/b.mp3", "size": len(voice),
         "sha1": _sha1(voice), "sha256": _sha256(voice)},
        {"object_key": "reverse1999/image/a.webp", "size": len(image),
         "sha1": _sha1(image), "sha256": _sha256(image)},
    ]}
    bodies = {
        "http://example/bucket/reverse1999/voice/b.mp3": voice,
        "http://example/bucket/reverse1999/image/a.webp": image,
    }

    result = migration.verify_media_samples(
        inventory, "http://example/bucket", ["voice", "image"], bodies.__getitem__
    )

    assert [item["asset_type"] for item in result["samples"]] == ["image", "voice"]


def test_prepare_c19_evidence_is_create_new_relative_and_hash_pinned(tmp_path):
    artifact = tmp_path / "artifact"
    (artifact / "runtime").mkdir(parents=True)
    runtime = artifact / "runtime" / "media_assets.v2.jsonl"
    runtime.write_text("{}\n", encoding="utf-8")
    media_manifest = artifact / "runtime" / "media_assets.v2.manifest.json"
    media_manifest.write_text(json.dumps({
        "schema_version": "evb.media-artifact-manifest/v2",
        "build_version": "build",
        "file_paths": {"media_assets_v2": "runtime/media_assets.v2.jsonl"},
        "file_sha256": {"media_assets_v2": _sha256(runtime.read_bytes())},
    }) + "\n", encoding="utf-8")
    inputs = {}
    for name in ("baseline", "inventory", "capability", "reconciliation"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
        inputs[name] = path
    output = tmp_path / "processed" / "build"

    result = migration.prepare_c19_evidence(
        artifact_root=artifact, baseline=inputs["baseline"],
        current_inventory=inputs["inventory"], capability=inputs["capability"],
        reconciliation=inputs["reconciliation"], output_root=output,
    )

    build = json.loads(result["build_manifest"].read_text(encoding="utf-8"))
    bundle = json.loads(result["preflight_bundle"].read_text(encoding="utf-8"))
    assert result["build_manifest"] == output / "build_manifest.json"
    assert result["preflight_bundle"] == output / "preflight" / "preflight_bundle_manifest.v1.json"
    assert build["media_artifact_manifest"] == "runtime/media_assets.v2.manifest.json"
    assert (output / "runtime" / "media_assets.v2.manifest.json").is_file()
    assert (output / "runtime" / "media_assets.v2.jsonl").read_bytes() == runtime.read_bytes()
    assert bundle["baseline_sha256"] == _sha256(inputs["baseline"].read_bytes())
    assert {item["name"] for item in bundle["sidecars"]} >= {
        "minio_capability", "current_inventory", "reconciliation"
    }
    assert all(not Path(item["path"]).is_absolute() for item in bundle["sidecars"])
    assert (result["preflight_bundle"].parent / "minio_capability.v1.json").is_file()
    with pytest.raises(FileExistsError):
        migration.prepare_c19_evidence(
            artifact_root=artifact, baseline=inputs["baseline"],
            current_inventory=inputs["inventory"], capability=inputs["capability"],
            reconciliation=inputs["reconciliation"], output_root=output,
        )


def test_prepare_v3_operation_evidence_pins_authorities_and_exact_sidecar_bytes(tmp_path):
    build_manifest = tmp_path / "candidate" / "build_manifest.json"
    build_sha = _write_json_fixture(
        build_manifest,
        {
            "schema_version": "huiji.corpus-build/v2",
            "artifact_schema_version": "evb.media-asset/v3",
            "artifacts": [],
        },
    )
    baseline = tmp_path / "baseline.json"
    baseline_sha = _write_json_fixture(baseline, {"schema_version": "baseline/v1"})
    inventory_path = tmp_path / "inventory.json"
    inventory = ObjectInventory.create(
        "reverse1999-assets", "reverse1999", (), bucket_policy_summary="absent"
    )
    inventory_sha = _write_json_fixture(inventory_path, inventory.to_json())
    capability = tmp_path / "capability.json"
    capability_sha = _write_json_fixture(
        capability,
        {
            "schema_version": "evb.minio-capability/v1",
            "conditional_create_supported": True,
            "application_audit_supported": True,
            "durable_replace_supported": False,
            "checked_at_utc": "2026-07-21T00:00:00Z",
            "details": [
                "endpoint=127.0.0.1:9002",
                "bucket=reverse1999-assets",
                "prefix=reverse1999",
                "server_identity=minio-test",
                "probe_operation_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "audit_correlation_id=audit-test",
                "checked_at_utc=2026-07-21T00:00:00Z",
                "server_atomic_if_none_match=proven",
                "application_audit_correlation=proven",
            ],
        },
    )
    reconciliation = tmp_path / "reconciliation.json"
    reconciliation_sha = _write_json_fixture(
        reconciliation,
        {
            "schema_version": "huiji.candidate-minio-reconciliation/v1",
            "candidate_build_manifest_sha256": build_sha,
            "current_inventory": {
                "file_sha256": inventory_sha,
                "object_state_sha256": inventory.object_state_sha256,
            },
            "classification": {
                "hash_mismatch_count": 0,
                "missing_remote_unique_object_count": 1,
                "missing_role_counts": {"voice": 1},
                "ordered_missing_object_keys_sha256": "a" * 64,
            },
        },
    )
    output = tmp_path / "processed" / "operations" / "operation" / "preflight"

    result = migration.prepare_v3_operation_evidence(
        build_manifest=build_manifest,
        expected_build_manifest_sha256=build_sha,
        baseline=baseline,
        expected_baseline_sha256=baseline_sha,
        current_inventory=inventory_path,
        capability=capability,
        expected_capability_sha256=capability_sha,
        reconciliation=reconciliation,
        expected_reconciliation_sha256=reconciliation_sha,
        allowed_media_authorities=(
            "voice|voice|exact|audio/mpeg|.mp3",
            "skill|skill|not_applicable|image/png|.png",
        ),
        output_root=output,
    )

    bundle = json.loads(result["preflight_bundle"].read_text(encoding="utf-8"))
    assert bundle["schema_version"] == "evb.minio-operation-preflight/v1"
    assert bundle["build_manifest_sha256"] == build_sha
    assert bundle["baseline_sha256"] == baseline_sha
    assert bundle["before_inventory_sha256"] == inventory_sha
    assert bundle["before_inventory_object_sha256"] == inventory.object_state_sha256
    assert bundle["approved_missing_object_keys_sha256"] == "a" * 64
    assert [item["asset_type"] for item in bundle["allowed_media_authorities"]] == [
        "skill",
        "voice",
    ]
    sidecars = {item["name"]: item for item in bundle["sidecars"]}
    copied_capability = result["preflight_bundle"].parent / sidecars["minio_capability"]["path"]
    copied_reconciliation = (
        result["preflight_bundle"].parent / sidecars["reconciliation"]["path"]
    )
    assert copied_capability.read_bytes() == capability.read_bytes()
    assert copied_reconciliation.read_bytes() == reconciliation.read_bytes()
    preflight, loaded_capability = load_operation_preflight_bundle(
        result["preflight_bundle"]
    )
    assert preflight.build_manifest_sha256 == build_sha
    assert preflight.allowed_media_authorities[0].asset_type == "skill"
    assert loaded_capability.conditional_create_supported is True
    with pytest.raises(FileExistsError):
        migration.prepare_v3_operation_evidence(
            build_manifest=build_manifest,
            expected_build_manifest_sha256=build_sha,
            baseline=baseline,
            expected_baseline_sha256=baseline_sha,
            current_inventory=inventory_path,
            capability=capability,
            expected_capability_sha256=capability_sha,
            reconciliation=reconciliation,
            expected_reconciliation_sha256=reconciliation_sha,
            allowed_media_authorities=("voice|voice|exact|audio/mpeg|.mp3",),
            output_root=output,
        )
    copied_reconciliation.write_bytes(copied_reconciliation.read_bytes() + b" ")
    with pytest.raises(EvidenceMismatch, match="sidecar reconciliation"):
        load_operation_preflight_bundle(result["preflight_bundle"])


def test_object_inventory_cli_accepts_an_explicit_empty_prefix():
    args = migration.build_parser().parse_args([
        "object-inventory", "--endpoint", "127.0.0.1:9002",
        "--bucket", "a-bucket", "--prefix",
        "--access-key-env", "ACCESS", "--secret-key-env", "SECRET",
        "--output", "inventory.json",
    ])

    assert args.prefix == ""
