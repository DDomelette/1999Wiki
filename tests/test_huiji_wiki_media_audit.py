from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from src.huiji_wiki.media_audit import audit_media, audit_media_manifest, write_repair_request
from src.huiji_wiki.snapshot import WikiArtifactSnapshot


class Response(io.BytesIO):
    status = 200
    headers = {"Content-Type": "image/webp", "Content-Length": "5"}
    def __enter__(self): return self
    def __exit__(self, *_): return False


def _snapshot(tmp_path: Path) -> WikiArtifactSnapshot:
    artifact = tmp_path / "dev" / "empty"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("", encoding="utf-8")
    return WikiArtifactSnapshot("legacy", "dev", "v1", artifact, artifact, artifact, "a" * 64, {}, None, None, "b" * 64)


def test_audit_uses_http_bytes_and_reports_unverified_nonvoice_hash(tmp_path: Path):
    body = b"image"
    rows = [{"media_id": "m1", "asset_type": "image", "url": "https://media.test/a.webp", "mime": "image/webp", "sha1": hashlib.sha1(body).hexdigest(), "size": len(body)}]
    report = audit_media(_snapshot(tmp_path), rows, tmp_path / "audit.json", opener=lambda *_args, **_kwargs: Response(body))
    assert report["results"][0]["status"] == "unverified-content-sha256"
    assert json.loads((tmp_path / "audit.json").read_text())["snapshotSha256"] == "b" * 64


def test_missing_media_creates_sanitized_create_new_repair_request(tmp_path: Path):
    snapshot = _snapshot(tmp_path)
    rows = [{"media_id": "m2", "url": "D:\\secret\\a.webp", "object_key": "reverse1999/image/a.webp", "local_relpath": "D:\\raw\\a.webp", "source_url": "https://private.test"}]
    path = write_repair_request(snapshot, rows, tmp_path / "repair.json")
    payload = path.read_text(encoding="utf-8")
    assert "reverse1999/image/a.webp" in payload
    assert "local_relpath" not in payload and "source_url" not in payload and "D:\\" not in payload
    try:
        write_repair_request(snapshot, rows, path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("repair request must use create-new semantics")


def test_blocks_audit_and_repair_for_unfinished_evb_transaction(tmp_path: Path):
    snapshot = _snapshot(tmp_path)
    journal = tmp_path / "activation/transactions/tx-1/journal.v1.json"
    journal.parent.mkdir(parents=True)
    journal.write_text('{"state":"committing"}', encoding="utf-8")
    rows = [{"media_id": "m3", "url": "https://media.test/a.webp", "mime": "image/webp"}]
    report = audit_media(snapshot, rows, tmp_path / "blocked.json", opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("HTTP must not run")))
    assert report["results"][0]["status"] == "blocked-by-evb"
    try:
        write_repair_request(snapshot, rows, tmp_path / "blocked-repair.json")
    except RuntimeError as exc:
        assert "blocked-by-evb" in str(exc)
    else:
        raise AssertionError("repair must be blocked")


def test_manifest_audit_checks_every_mapping_without_http(tmp_path: Path):
    report = audit_media_manifest(_snapshot(tmp_path), [
        {"media_id": "m1", "object_key": "reverse1999/image/a.webp", "url": "https://media.test/a.webp"},
        {"media_id": "m1", "object_key": "reverse1999/image/b.webp", "url": "https://media.test/b.webp"},
        {"media_id": "m3", "object_key": "", "url": "D:\\local.webp"},
    ], tmp_path / "manifest.json")

    assert report["rowCount"] == 3
    assert report["completeCount"] == 1
    assert [item["status"] for item in report["results"]] == ["mapping-complete", "conflicting-media-id", "missing-index-fields"]
