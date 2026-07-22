from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import src.huijiwiki.credential_store as credential_store
from src.huijiwiki.credential_schema import CanonicalCredential
from src.huijiwiki.credential_store import (
    CredentialConflictError,
    CredentialValidationError,
    import_legacy_credential,
    inspect_credential,
)


def _legacy_bytes(secret: str = "session-secret") -> bytes:
    return json.dumps(
        {
            "cookies": [
                {
                    "name": "huiji_session",
                    "value": secret,
                    "domain": ".huijiwiki.com",
                    "path": "/",
                },
                {
                    "name": "__cf_bm",
                    "value": "cloudflare-secret",
                    "domain": ".huijiwiki.com",
                    "path": "/",
                    "expires": 1_900_000_000,
                },
            ]
        },
        sort_keys=True,
    ).encode("utf-8")


def _canonical_bytes(secret: str = "session-secret") -> bytes:
    return CanonicalCredential.from_payload(
        {
            "schema_version": "huiji_credential.v2",
            "expected_user": "POTATO BOT",
            "cookies": [
                {
                    "name": "huiji_session",
                    "value": secret,
                    "domain": ".huijiwiki.com",
                    "path": "/",
                    "expires": None,
                    "secure": True,
                    "http_only": False,
                },
                {
                    "name": "__cf_bm",
                    "value": "cloudflare-secret",
                    "domain": ".huijiwiki.com",
                    "path": "/",
                    "expires": 1_900_000_000,
                    "secure": True,
                    "http_only": False,
                },
            ],
        }
    ).to_bytes()


def test_inspect_credential_reports_schema_hash_size_names_and_user_without_values(tmp_path: Path) -> None:
    path = tmp_path / "credential.json"
    payload = _canonical_bytes()
    path.write_bytes(payload)

    inspection = inspect_credential(path)
    encoded = json.dumps(inspection.to_json(), sort_keys=True)

    assert inspection.size == len(payload)
    assert inspection.sha256 == hashlib.sha256(payload).hexdigest()
    assert inspection.cookie_names == ("__cf_bm", "huiji_session")
    assert inspection.expected_user == "POTATO BOT"
    assert inspection.schema_version == "huiji_credential.v2"
    assert "session-secret" not in encoded
    assert "cloudflare-secret" not in encoded


def test_import_converts_legacy_source_to_v2_and_reports_redacted_evidence(tmp_path: Path) -> None:
    source = tmp_path / "external" / "config.dat"
    target = tmp_path / "tool" / ".local" / "accounts" / "default" / "credential.json"
    source.parent.mkdir()
    source.write_bytes(_legacy_bytes())

    report = import_legacy_credential(source, target, expected_user="POTATO BOT")

    target_payload = json.loads(target.read_text(encoding="utf-8"))
    assert report["status"] == "imported"
    assert target_payload["schema_version"] == "huiji_credential.v2"
    assert target_payload["expected_user"] == "POTATO BOT"
    assert target.read_bytes() != source.read_bytes()
    assert report["source"]["sha256"] != report["target"]["sha256"]
    assert "session-secret" not in json.dumps(report, sort_keys=True)


def test_import_same_canonical_payload_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.dat"
    target = tmp_path / "credential.json"
    source.write_bytes(_legacy_bytes())
    import_legacy_credential(source, target, expected_user="POTATO BOT")
    original = target.read_bytes()
    monkeypatch.setattr(
        credential_store.os,
        "replace",
        lambda *args: (_ for _ in ()).throw(AssertionError("same canonical hash must not rewrite target")),
    )

    report = import_legacy_credential(source, target, expected_user="POTATO BOT")

    assert report["status"] == "already_same_canonical"
    assert target.read_bytes() == original


def test_import_conflict_stops_without_replace(tmp_path: Path) -> None:
    source = tmp_path / "source.dat"
    target = tmp_path / "credential.json"
    source.write_bytes(_legacy_bytes("new-secret"))
    original = _canonical_bytes("existing-secret")
    target.write_bytes(original)

    with pytest.raises(CredentialConflictError):
        import_legacy_credential(source, target, expected_user="POTATO BOT")

    assert target.read_bytes() == original


def test_import_replace_is_explicit_and_atomic(tmp_path: Path) -> None:
    source = tmp_path / "source.dat"
    target = tmp_path / "credential.json"
    source.write_bytes(_legacy_bytes("new-secret"))
    target.write_bytes(_canonical_bytes("existing-secret"))

    report = import_legacy_credential(
        source,
        target,
        expected_user="POTATO BOT",
        replace=True,
    )

    assert report["status"] == "replaced"
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == "huiji_credential.v2"
    assert b"new-secret" in target.read_bytes()


def test_import_can_replace_malformed_target_only_when_explicit(tmp_path: Path) -> None:
    source = tmp_path / "source.dat"
    target = tmp_path / "credential.json"
    source.write_bytes(_legacy_bytes("new-secret"))
    target.write_bytes(b"broken-target")

    with pytest.raises(CredentialConflictError):
        import_legacy_credential(source, target, expected_user="POTATO BOT")

    report = import_legacy_credential(
        source,
        target,
        expected_user="POTATO BOT",
        replace=True,
    )

    assert report["status"] == "replaced"
    assert inspect_credential(target).schema_version == "huiji_credential.v2"


@pytest.mark.parametrize("payload", [b"", b"not a credential", b"\x80not-a-valid-pickle"])
def test_import_rejects_empty_or_malformed_source(tmp_path: Path, payload: bytes) -> None:
    source = tmp_path / "source.dat"
    target = tmp_path / "credential.json"
    source.write_bytes(payload)

    with pytest.raises(CredentialValidationError):
        import_legacy_credential(source, target, expected_user="POTATO BOT")

    assert not target.exists()


def test_import_source_hash_size_and_mtime_are_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source.dat"
    target = tmp_path / "credential.json"
    source.write_bytes(_legacy_bytes())
    before = source.stat()
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    report = import_legacy_credential(source, target, expected_user="POTATO BOT")

    after = source.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
    assert report["source"]["mtime_ns"] == before.st_mtime_ns


def test_atomic_replace_failure_preserves_existing_target_and_removes_temp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.dat"
    target = tmp_path / "credential.json"
    source.write_bytes(_legacy_bytes("new-secret"))
    original = _canonical_bytes("existing-secret")
    target.write_bytes(original)

    def fail_replace(source_path, target_path):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(credential_store.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        import_legacy_credential(
            source,
            target,
            expected_user="POTATO BOT",
            replace=True,
        )

    assert target.read_bytes() == original
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []
