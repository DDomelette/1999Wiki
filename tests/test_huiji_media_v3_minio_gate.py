from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.huiji_rag.build.media_v3 import MediaV3Assembly, reconcile_media_v3_minio
from src.huiji_rag.minio_strict import InventoryObject, ObjectInventory


FIXTURE = Path("tests/fixtures/contracts/huiji_media_v3/media_assets.v3.jsonl")


def _assembly() -> MediaV3Assembly:
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line]
    resources = {row["resource_id"] for row in rows}
    return MediaV3Assembly(
        runtime_rows=tuple(rows),
        binding_inventory=(),
        unresolved_intents=(),
        blockers=(),
        resource_count=len(resources),
        binding_count=len(rows),
        shared_resource_groups=1,
        counts_by_role={},
    )


def _inventory(
    assembly: MediaV3Assembly,
    *,
    omit: str = "",
    mismatch: str = "",
    include_orphan: bool = True,
) -> ObjectInventory:
    by_key = {}
    for row in assembly.runtime_rows:
        key = str(row["object_key"])
        if key == omit or key in by_key:
            continue
        sha256 = "9" * 64 if key == mismatch else str(row["content_sha256"])
        by_key[key] = InventoryObject(
            object_key=key,
            version_id=None,
            etag="etag",
            sha1=str(row["sha1"]),
            sha256=sha256,
            size=int(row["size"]),
        )
    if include_orphan:
        by_key["reverse1999/orphan/unused.bin"] = InventoryObject(
            object_key="reverse1999/orphan/unused.bin",
            version_id="orphan-v1",
            etag="orphan-etag",
            sha1="0" * 40,
            sha256="0" * 64,
            size=10,
        )
    return ObjectInventory.create(
        bucket="reverse1999-assets",
        prefix="reverse1999",
        objects=tuple(by_key.values()),
        captured_at_utc="2026-07-21T00:00:00Z",
        bucket_policy_summary="sha256:" + "1" * 64,
    )


def test_minio_gate_marks_all_declared_rows_available_and_keeps_orphans_diagnostic() -> None:
    assembly = _assembly()

    result = reconcile_media_v3_minio(
        assembly,
        _inventory(assembly),
        expected_bucket="reverse1999-assets",
        expected_prefix="reverse1999",
    )

    assert result.ready_for_embedding is True
    assert result.blockers == ()
    assert len(result.same_hash) == assembly.resource_count
    assert result.missing_remote == ()
    assert result.hash_mismatch == ()
    assert result.orphan_remote == ("reverse1999/orphan/unused.bin",)
    assert all(row["is_available"] is True for row in result.runtime_rows)
    assert len(result.runtime_rows) == assembly.binding_count


def test_minio_gate_missing_shared_key_blocks_every_binding_for_that_resource() -> None:
    assembly = _assembly()
    shared_key = str(assembly.runtime_rows[0]["object_key"])

    result = reconcile_media_v3_minio(
        assembly,
        _inventory(assembly, omit=shared_key),
        expected_bucket="reverse1999-assets",
        expected_prefix="reverse1999",
    )

    assert result.ready_for_embedding is False
    assert result.missing_remote == (shared_key,)
    shared_rows = [row for row in result.runtime_rows if row["object_key"] == shared_key]
    assert len(shared_rows) == 2
    assert all(row["is_available"] is False for row in shared_rows)
    assert len({row["binding_id"] for row in shared_rows}) == 2


def test_minio_hash_mismatch_expands_binding_owner_and_consumer_diagnostics() -> None:
    assembly = _assembly()
    shared_key = str(assembly.runtime_rows[0]["object_key"])

    result = reconcile_media_v3_minio(
        assembly,
        _inventory(assembly, mismatch=shared_key),
        expected_bucket="reverse1999-assets",
        expected_prefix="reverse1999",
    )

    assert result.ready_for_embedding is False
    assert result.missing_remote == ()
    assert len(result.hash_mismatch) == 1
    mismatch = result.hash_mismatch[0]
    assert mismatch["reason_code"] == "remote_content_identity_mismatch"
    assert set(mismatch["owner_entity_ids"]) == {"character:1001", "character:1002"}
    assert len(mismatch["binding_ids"]) == 2
    assert mismatch["consumers"] == ["huiji_rag", "huiji_wiki"]
    assert any(blocker.startswith("minio_hash_mismatch:") for blocker in result.blockers)


def test_minio_gate_rejects_wrong_bucket_or_unverified_mapping() -> None:
    assembly = _assembly()
    inventory = _inventory(assembly)
    with pytest.raises(ValueError, match="bucket"):
        reconcile_media_v3_minio(
            assembly,
            inventory,
            expected_bucket="other-bucket",
            expected_prefix="reverse1999",
        )

    payload = {
        "schema_version": inventory.schema_version,
        "bucket": inventory.bucket,
        "prefix": inventory.prefix,
        "objects": [],
        "captured_at_utc": inventory.captured_at_utc,
        "inventory_sha256": "0" * 64,
    }
    with pytest.raises(ValueError, match="invalid"):
        reconcile_media_v3_minio(
            assembly,
            payload,
            expected_bucket="reverse1999-assets",
            expected_prefix="reverse1999",
        )
