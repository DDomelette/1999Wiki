from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.huiji_wiki.mysql_rollback import (
    PASSING_RECEIPT_SCHEMA,
    TEST_ONLY_RECEIPT_SCHEMA,
    build_restore_confirmation,
    canonical_json_bytes,
    mysqldump_args,
    owned_apply_container_args,
    resolve_under,
    temporary_container_args,
    validate_passing_receipt,
    validate_receipt_id,
)


def test_receipt_id_and_output_containment_are_strict(tmp_path: Path):
    assert validate_receipt_id("legacy-dev_20260721") == "legacy-dev_20260721"
    for value in ("", "../escape", "A", "bad.dot", "x" * 65):
        with pytest.raises(ValueError):
            validate_receipt_id(value)

    root = tmp_path / "root"
    root.mkdir()
    assert resolve_under(root, "a/b.json") == (root / "a/b.json").resolve()
    with pytest.raises(ValueError, match="escape"):
        resolve_under(root, "../outside.json")


def test_dump_arguments_pin_single_transaction_and_disable_locks():
    args = mysqldump_args("reverse1999_wiki")

    required = {
        "--single-transaction",
        "--skip-lock-tables",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        "--set-gtid-purged=OFF",
        "--no-tablespaces",
        "--default-character-set=utf8mb4",
        "--skip-comments",
    }
    assert required.issubset(args)
    assert "--lock-tables" not in args
    assert args[-1] == "reverse1999_wiki"


def test_temp_container_has_same_image_no_network_ports_or_named_volume():
    args = temporary_container_args(
        container_name="wiki-rollback-verify-op1",
        image_id="sha256:" + "a" * 64,
        operation_id="op1",
    )

    joined = " ".join(args)
    assert "--network none" in joined
    assert "--tmpfs /var/lib/mysql" in joined
    assert "-p " not in joined and "-P" not in args
    assert "MYSQL_ALLOW_EMPTY_PASSWORD=yes" in joined
    assert args[-1] == "sha256:" + "a" * 64


def test_owned_apply_container_is_isolated_and_explicitly_test_only():
    args = owned_apply_container_args(
        container_name="wiki-rollback-apply-op1",
        image_id="sha256:" + "b" * 64,
        operation_id="op1",
    )

    joined = " ".join(args)
    assert "--network none" in joined
    assert "--tmpfs /var/lib/mysql" in joined
    assert "rollback.test-only=true" in joined
    assert "rollback.role=apply-target" in joined
    assert "-p " not in joined and "-P" not in args


def test_canonical_json_and_passing_loader_reject_test_only(tmp_path: Path):
    sidecar = tmp_path / "sidecar.json"
    sidecar.write_bytes(b"{}\n")
    sidecar_pin = {
        "path": "sidecar.json",
        "size": sidecar.stat().st_size,
        "sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
    }
    entrypoint = tmp_path / "restore.py"
    entrypoint.write_bytes(b"# pinned restore entrypoint\n")
    entrypoint_pin = {
        "path": "restore.py",
        "size": entrypoint.stat().st_size,
        "sha256": hashlib.sha256(entrypoint.read_bytes()).hexdigest(),
    }
    payload = {
        "schema_version": PASSING_RECEIPT_SCHEMA,
        "status": "passed",
        "receipt_id": "receipt-1",
        "sidecars": [sidecar_pin],
        "restore_entrypoint": entrypoint_pin,
    }
    payload["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(canonical_json_bytes(payload, include_self_hash=True))

    loaded = validate_passing_receipt(receipt, project_root=tmp_path)
    assert loaded["receipt_id"] == "receipt-1"

    test_only = dict(payload, schema_version=TEST_ONLY_RECEIPT_SCHEMA, test_only=True)
    test_only["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(test_only)).hexdigest()
    receipt.write_bytes(canonical_json_bytes(test_only, include_self_hash=True))
    with pytest.raises(ValueError, match="schema"):
        validate_passing_receipt(receipt, project_root=tmp_path)


def test_confirmation_is_exact():
    assert build_restore_confirmation("receipt-1") == "RESTORE reverse1999_wiki FROM receipt-1"
