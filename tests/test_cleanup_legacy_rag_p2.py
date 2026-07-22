from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.cleanup_legacy_rag_p2 import (
    CleanupBlocked,
    _expected_from_rows,
    _extract_restic_snapshot,
    _operation_id_from_output,
    append_receipt,
    assert_plan_hash,
    build_parser,
    canonical_json_bytes,
    classify_keys,
    conditional_restore_object,
    delete_exact_objects,
    resolve_within,
    validate_complete_object,
    validate_expected_hashes,
)


def _remote(key: str, *, sha1: str = "a" * 40, sha256: str = "b" * 64):
    return {
        "object_key": key,
        "size": 3,
        "sha1": sha1,
        "sha256": sha256,
        "etag": "etag",
        "version_id": None,
        "application_operation_id": None,
        "audit_event_id": None,
    }


def test_canonical_serialization_is_sorted_and_stable():
    assert canonical_json_bytes({"z": 1, "a": [2, 1]}) == b'{"a":[2,1],"z":1}\n'


def test_resolve_within_rejects_escape(tmp_path: Path):
    assert resolve_within(tmp_path, "a/b.bin") == (tmp_path / "a" / "b.bin").resolve()
    with pytest.raises(CleanupBlocked, match="escapes"):
        resolve_within(tmp_path, "../outside.bin")


def test_inventory_objects_require_all_identity_fields():
    validate_complete_object(_remote("reverse1999/legacy/a.bin"))
    broken = _remote("reverse1999/legacy/a.bin")
    broken.pop("sha256")
    with pytest.raises(CleanupBlocked, match="sha256"):
        validate_complete_object(broken)


def test_classification_uses_dynamic_legacy_minus_consumer_formula():
    remote = {
        "reverse1999/legacy/a.bin",
        "reverse1999/shared/b.bin",
        "reverse1999/wiki/c.bin",
        "reverse1999/other/d.bin",
        "_evb_capability_probe/probe.bin",
    }
    result = classify_keys(
        remote_keys=remote,
        legacy_keys={"reverse1999/legacy/a.bin", "reverse1999/shared/b.bin"},
        rag_keys={"reverse1999/shared/b.bin"},
        wiki_keys={"reverse1999/wiki/c.bin"},
    )

    assert result["delete_candidates"] == ("reverse1999/legacy/a.bin",)
    assert result["active_consumers"] == (
        "reverse1999/shared/b.bin",
        "reverse1999/wiki/c.bin",
    )
    assert result["capability_probes"] == ("_evb_capability_probe/probe.bin",)
    assert result["residual_orphans"] == ("reverse1999/other/d.bin",)


def test_missing_active_consumer_blocks_classification():
    with pytest.raises(CleanupBlocked, match="active consumer"):
        classify_keys(
            remote_keys={"reverse1999/legacy/a.bin"},
            legacy_keys={"reverse1999/legacy/a.bin"},
            rag_keys={"reverse1999/missing.bin"},
            wiki_keys=set(),
        )


def test_hash_mismatch_blocks_and_expands_related_scope():
    remote = {"reverse1999/voice/aa/file.mp3": _remote("reverse1999/voice/aa/file.mp3")}
    expected = {
        "reverse1999/voice/aa/file.mp3": [
            {"source": "rag", "sha1": "f" * 40, "sha256": "", "size": None}
        ]
    }

    with pytest.raises(CleanupBlocked) as error:
        validate_expected_hashes(remote, expected)

    diagnostics = error.value.diagnostics
    assert diagnostics["hash_mismatch_count"] == 1
    assert diagnostics["expanded_prefixes"] == ["reverse1999/voice/aa"]
    assert diagnostics["related_keys"] == ["reverse1999/voice/aa/file.mp3"]


def test_rag_content_hash_is_not_treated_as_file_sha256():
    key = "reverse1999/image/aa/file.webp"
    keys, expected = _expected_from_rows(
        [
            {
                "object_key": key,
                "sha1": "a" * 40,
                "content_hash": "c" * 64,
            }
        ],
        "active_rag",
        "reverse1999-assets",
    )

    assert keys == {key}
    assert expected[key][0]["sha256"] == ""


def test_explicit_content_sha256_is_treated_as_file_sha256():
    key = "reverse1999/voice/aa/file.mp3"
    keys, expected = _expected_from_rows(
        [
            {
                "object_key": key,
                "sha1": "a" * 40,
                "content_hash": "c" * 64,
                "content_sha256": "d" * 64,
            }
        ],
        "active_rag",
        "reverse1999-assets",
    )

    assert keys == {key}
    assert expected[key][0]["sha256"] == "d" * 64


def test_operation_id_preserves_p2_suffix(tmp_path: Path):
    output = tmp_path / "20260719T215123Z-huiji-p2" / "p2" / "operation-plan.v1.json"

    assert _operation_id_from_output(output) == "20260719T215123Z-huiji-p2"


def test_restic_snapshot_receipt_accepts_powershell_utf16(tmp_path: Path):
    receipt = tmp_path / "restic.jsonl"
    receipt.write_text(
        '{"message_type":"summary","snapshot_id":"abc123"}\n',
        encoding="utf-16",
    )

    assert _extract_restic_snapshot(receipt) == "abc123"


def test_plan_hash_must_match_exact_file(tmp_path: Path):
    plan = tmp_path / "plan.json"
    plan.write_bytes(b"{}\n")
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    assert assert_plan_hash(plan, digest) == digest
    with pytest.raises(CleanupBlocked, match="hash"):
        assert_plan_hash(plan, "0" * 64)


def test_append_receipt_is_create_new_then_append_only(tmp_path: Path):
    receipt = tmp_path / "receipt.jsonl"
    append_receipt(receipt, {"event": "one"})
    append_receipt(receipt, {"event": "two"})
    rows = [json.loads(line) for line in receipt.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"event": "one"}, {"event": "two"}]


class _DeleteClient:
    def __init__(self):
        self.calls = []

    def remove_object(self, bucket, object_key, version_id=None):
        self.calls.append((bucket, object_key, version_id))


def test_delete_uses_only_exact_keys_and_versions(tmp_path: Path):
    client = _DeleteClient()
    objects = [
        {**_remote("reverse1999/legacy/a.bin"), "version_id": "v1"},
        _remote("reverse1999/legacy/b.bin"),
    ]
    delete_exact_objects(client, "reverse1999-assets", objects, tmp_path / "receipt.jsonl")
    assert client.calls == [
        ("reverse1999-assets", "reverse1999/legacy/a.bin", "v1"),
        ("reverse1999-assets", "reverse1999/legacy/b.bin", None),
    ]


class _ConditionalClient:
    def __init__(self):
        self.calls = []

    def _execute(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"headers": {"ETag": '"etag"'}})()


def test_restore_uses_if_none_match_and_hash_checked_body(tmp_path: Path):
    body = b"abc"
    backup = tmp_path / "object.bin"
    backup.write_bytes(body)
    planned = _remote(
        "reverse1999/legacy/object.bin",
        sha1=hashlib.sha1(body).hexdigest(),
        sha256=hashlib.sha256(body).hexdigest(),
    )
    client = _ConditionalClient()

    conditional_restore_object(client, "reverse1999-assets", planned, backup, "restore-op")

    assert client.calls[0]["method"] == "PUT"
    assert client.calls[0]["object_name"] == planned["object_key"]
    assert client.calls[0]["headers"]["If-None-Match"] == "*"
    assert client.calls[0]["body"] == body


def test_cli_exposes_all_gated_subcommands():
    parser = build_parser()
    help_text = parser.format_help()
    for command in (
        "inventory",
        "verify-local-backup",
        "backup-minio",
        "plan",
        "apply",
        "verify",
        "restore-partial",
    ):
        assert command in help_text


def test_controller_cannot_batch_delete_buckets_or_milvus_collections():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "cleanup_legacy_rag_p2.py").read_text(
        encoding="utf-8"
    )
    assert "remove_objects" not in source
    assert "remove_bucket" not in source
    assert "drop_collection" not in source
    assert "delete_collection" not in source
    assert 'delete_exact_objects(client, str(plan["bucket"])' in source
    assert 'delete_exact_objects(client, "a-bucket"' not in source
