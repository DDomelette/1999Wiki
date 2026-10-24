from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.huijiwiki import snapshot_recovery as recovery
from src.huijiwiki.snapshot_recovery import (
    SnapshotManifest,
    audit_snapshot,
    recover_missing_files,
)


@dataclass(frozen=True)
class RecoveryFixture:
    source: Path
    target: Path
    receipt: Path
    manifest: SnapshotManifest


def make_recovery_fixture(tmp_path: Path) -> RecoveryFixture:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    rows = (
        '{"json_valid":true,"content":"{\\"id\\":1}"}\n'
        '{"json_valid":false,"content":"not-json","json_error":"bad"}\n'
    )
    (source / "data_pages.jsonl").write_text(rows, encoding="utf-8")
    with sqlite3.connect(source / "crawl_state.sqlite") as connection:
        connection.execute("CREATE TABLE crawl_runs (id INTEGER PRIMARY KEY)")
    (source / "pages.jsonl").write_text('{"pageid":1}\n', encoding="utf-8")
    shutil.copyfile(source / "pages.jsonl", target / "pages.jsonl")
    payload = {
        "schema_version": "huiji-source-recovery/v1",
        "snapshot_id": "fixture",
        "files": {
            filename: _file_spec(source / filename)
            for filename in (
                "data_pages.jsonl",
                "crawl_state.sqlite",
                "pages.jsonl",
            )
        },
        "recover": ["data_pages.jsonl", "crawl_state.sqlite"],
    }
    payload["files"]["data_pages.jsonl"]["rows"] = 2
    payload["files"]["data_pages.jsonl"]["invalid_payload_rows"] = 1
    return RecoveryFixture(
        source=source,
        target=target,
        receipt=tmp_path / "receipt.json",
        manifest=SnapshotManifest.from_json(payload),
    )


def test_audit_only_does_not_create_target(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    audit = audit_snapshot(
        fixture.source,
        fixture.target,
        fixture.manifest,
    )
    assert audit.status == "ready"
    assert audit.invalid_payload_rows == 1
    assert not (fixture.target / "data_pages.jsonl").exists()


def test_apply_recovers_only_manifest_recover_files(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    existing_sibling = fixture.target / "pages.jsonl"
    original_mtime_ns = existing_sibling.stat().st_mtime_ns
    source_bytes = (fixture.source / "data_pages.jsonl").read_bytes()
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    receipt = recover_missing_files(audit, fixture.receipt)
    assert (fixture.target / "data_pages.jsonl").read_bytes() == source_bytes
    assert (fixture.target / "crawl_state.sqlite").exists()
    assert existing_sibling.stat().st_mtime_ns == original_mtime_ns
    assert receipt.status == "completed"
    with sqlite3.connect(
        fixture.target / "crawl_state.sqlite"
    ) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_mismatched_existing_target_is_never_overwritten(
    tmp_path: Path,
) -> None:
    fixture = make_recovery_fixture(tmp_path)
    target_file = fixture.target / "data_pages.jsonl"
    target_file.write_bytes(b"user data")
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    with pytest.raises(RuntimeError, match="target mismatch"):
        recover_missing_files(audit, fixture.receipt)
    assert target_file.read_bytes() == b"user data"


def test_staging_hash_mismatch_never_publishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = make_recovery_fixture(tmp_path)

    def corrupt_copy(source: Path, staging: Path) -> None:
        staging.write_bytes(b"corrupt")

    monkeypatch.setattr(recovery, "_copy_to_staging", corrupt_copy)
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    with pytest.raises(RuntimeError, match="staging hash mismatch"):
        recover_missing_files(audit, fixture.receipt)
    assert not (fixture.target / "data_pages.jsonl").exists()


def test_partial_previous_success_is_idempotent(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    shutil.copyfile(
        fixture.source / "data_pages.jsonl",
        fixture.target / "data_pages.jsonl",
    )
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    receipt = recover_missing_files(audit, fixture.receipt)
    assert receipt.files["data_pages.jsonl"].status == "already_present"
    assert receipt.files["crawl_state.sqlite"].status == "recovered"


def test_source_and_target_must_be_distinct(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    with pytest.raises(ValueError, match="must be distinct"):
        audit_snapshot(
            fixture.source,
            fixture.source,
            fixture.manifest,
        )


def test_production_manifest_uses_valid_sha256_values() -> None:
    manifest = SnapshotManifest.load(
        Path("config/recovery/huiji-res1999-20260707.json")
    )
    for name, spec in manifest.files.items():
        assert len(spec.sha256) == 64, name
        assert all(character in "0123456789abcdef" for character in spec.sha256)


def _file_spec(path: Path) -> dict[str, object]:
    return {
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
