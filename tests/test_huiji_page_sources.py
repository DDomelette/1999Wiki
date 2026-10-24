from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.huiji_rag.build.page_sources import (
    CrawlerSemanticInputs,
    JsonlStream,
    build_page_revision_join,
    validate_recovery_gate,
)


FIXTURE_ROOT = Path("tests/fixtures/huiji_topic_story_media_projection")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _recovery_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    data = raw / "data_pages.jsonl"
    data.write_text(
        '{"site":"res1999","pageid":1,"revid":2,"title":"Data:A.json",'
        '"content":"{}","content_sha256":"' + "a" * 64 + '","json_valid":true}\n'
        '{"site":"res1999","pageid":2,"revid":3,"title":"Data:B.json",'
        '"content":"not-json","content_sha256":"' + "b" * 64 + '","json_valid":false}\n',
        encoding="utf-8",
    )
    state = raw / "crawl_state.sqlite"
    with sqlite3.connect(state) as connection:
        connection.execute("CREATE TABLE crawl_runs (id INTEGER PRIMARY KEY)")
    manifest = tmp_path / "manifest.json"
    audit = tmp_path / "audit.json"
    apply = tmp_path / "apply.json"
    snapshot_id = "fixture"
    _write_json(
        manifest,
        {
            "schema_version": "huiji-source-recovery/v1",
            "snapshot_id": snapshot_id,
            "files": {
                "data_pages.jsonl": {
                    "size": data.stat().st_size,
                    "sha256": _sha256(data),
                    "rows": 2,
                    "invalid_payload_rows": 1,
                },
                "crawl_state.sqlite": {
                    "size": state.stat().st_size,
                    "sha256": _sha256(state),
                },
            },
            "recover": ["data_pages.jsonl", "crawl_state.sqlite"],
        },
    )
    _write_json(
        audit,
        {
            "status": "ready",
            "snapshot_id": snapshot_id,
            "invalid_payload_rows": 1,
        },
    )
    _write_json(
        apply,
        {
            "status": "completed",
            "snapshot_id": snapshot_id,
            "files": {
                "data_pages.jsonl": {
                    "status": "recovered",
                    "size": data.stat().st_size,
                    "sha256": _sha256(data),
                },
                "crawl_state.sqlite": {
                    "status": "recovered",
                    "size": state.stat().st_size,
                    "sha256": _sha256(state),
                },
            },
        },
    )
    return raw, manifest, audit, apply


def test_semantic_inputs_stream_exactly_four_crawler_files() -> None:
    inputs = CrawlerSemanticInputs.from_root(FIXTURE_ROOT)

    assert inputs.source_filenames == (
        "pages.jsonl",
        "wikitext.jsonl",
        "data_pages.jsonl",
        "resources_manifest.jsonl",
    )
    assert [row.row["pageid"] for row in inputs.pages()] == [1, 1, 2, 3]
    assert [row.row["pageid"] for row in inputs.revisions()] == [1, 3, 99]
    assert [row.row["pageid"] for row in inputs.data_pages()] == [41, 9001]
    assert [row.row["name"] for row in inputs.resources()] == [
        "Banner_测试页面.png"
    ]


def test_stream_reader_never_calls_path_read_text_or_splitlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_read_text(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("streaming JSONL must not call Path.read_text")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    stream = JsonlStream(FIXTURE_ROOT / "pages.jsonl", source_name="pages.jsonl")

    assert sum(1 for _row in stream) == 4
    assert stream.metrics.read_rows == 4
    assert stream.metrics.accepted_rows == 4


def test_stream_reader_reports_utf8_json_schema_and_oversize_line_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_bytes(
        b'{"site":"res1999","pageid":1,"title":"A"}\n'
        b"\xff\n"
        b"{bad json}\n"
        b"[]\n"
        b'{"site":"res1999","pageid":2,"padding":"0123456789"}\n'
    )
    stream = JsonlStream(path, source_name="pages.jsonl", max_line_bytes=48)

    rows = list(stream)

    assert [row.row["pageid"] for row in rows] == [1]
    assert [item.reason_code for item in stream.diagnostics] == [
        "utf8_error",
        "json_parse_error",
        "schema_error",
        "line_too_large",
    ]
    assert [item.line_number for item in stream.diagnostics] == [2, 3, 4, 5]
    assert stream.metrics.excluded_rows == 4
    assert stream.metrics.peak_rss_bytes == "unavailable" or int(
        stream.metrics.peak_rss_bytes
    ) > 0
    assert stream.metrics.elapsed_seconds >= 0


def test_page_revision_join_dedupes_identical_rows_and_keeps_bounded_metadata() -> None:
    inputs = CrawlerSemanticInputs.from_root(FIXTURE_ROOT)

    result = build_page_revision_join(inputs.pages(), inputs.revisions())

    assert [item.page.pageid for item in result.joined] == [1]
    assert result.joined[0].revision.revid == 11
    assert not hasattr(result.joined[0].revision, "content")
    assert {item.reason_code for item in result.diagnostics} == {
        "missing_latest_revision",
        "non_main_namespace",
        "orphan_revision",
    }
    assert result.blockers == ()


def test_conflicting_page_or_revision_identity_blocks_only_affected_page(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "pages.jsonl"
    revisions = tmp_path / "wikitext.jsonl"
    pages.write_text(
        '{"site":"res1999","pageid":1,"ns":0,"title":"A","lastrevid":2,'
        '"status":"active","seen_at":"t"}\n'
        '{"site":"res1999","pageid":1,"ns":0,"title":"B","lastrevid":2,'
        '"status":"active","seen_at":"t"}\n',
        encoding="utf-8",
    )
    revisions.write_text(
        '{"site":"res1999","pageid":1,"revid":2,"title":"A",'
        '"content_sha256":"' + "a" * 64 + '","content":"one"}\n'
        '{"site":"res1999","pageid":1,"revid":2,"title":"A",'
        '"content_sha256":"' + "b" * 64 + '","content":"two"}\n',
        encoding="utf-8",
    )

    result = build_page_revision_join(
        JsonlStream(pages, source_name="pages.jsonl"),
        JsonlStream(revisions, source_name="wikitext.jsonl"),
    )

    assert result.joined == ()
    assert result.blockers == (
        "page_identity_conflict:1",
        "revision_identity_conflict:1:2",
    )


def test_recovery_gate_requires_pinned_receipts_and_uses_read_only_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, manifest, audit, apply = _recovery_fixture(tmp_path)
    connections: list[str] = []
    real_connect = sqlite3.connect

    def recording_connect(database: object, *args: object, **kwargs: object):
        connections.append(str(database))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    evidence = validate_recovery_gate(
        raw,
        manifest_path=manifest,
        audit_receipt_path=audit,
        apply_receipt_path=apply,
    )

    assert evidence.snapshot_id == "fixture"
    assert evidence.invalid_payload_rows == 1
    assert evidence.sqlite_quick_check == "ok"
    assert connections and connections[-1].endswith("?mode=ro")

    payload = json.loads(apply.read_text(encoding="utf-8"))
    payload["status"] = "failed"
    _write_json(apply, payload)
    with pytest.raises(ValueError, match="apply receipt"):
        validate_recovery_gate(
            raw,
            manifest_path=manifest,
            audit_receipt_path=audit,
            apply_receipt_path=apply,
        )
