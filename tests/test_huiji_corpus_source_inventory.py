from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.huiji_rag.build.contracts import CRAWLER_SOURCE_FILENAMES
from src.huiji_rag.build.source_inventory import (
    capture_code_fingerprint,
    capture_corpus_source_inventory,
)
import src.huiji_rag.build.source_inventory as inventory_module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _raw_fixture(root: Path) -> Path:
    raw = root / "raw"
    _write_jsonl(
        raw / "pages.jsonl",
        [{"site": "res1999", "pageid": 1, "seen_at": "t1", "title": "A"}],
    )
    _write_jsonl(
        raw / "wikitext.jsonl",
        [{"site": "res1999", "pageid": 1, "revid": 11, "title": "A", "content": "x"}],
    )
    _write_jsonl(
        raw / "data_pages.jsonl",
        [{"site": "res1999", "pageid": 2, "revid": 22, "title": "Data:A.json", "content": "{}"}],
    )
    _write_jsonl(
        raw / "resources_manifest.jsonl",
        [{
            "site": "res1999",
            "title": "文件:A.webp",
            "sha1": "a" * 40,
            "url": "https://example.test/A.webp",
            "source": "huiji_file_namespace",
            "local_relpath": "assets/files/a/A.webp",
        }],
    )
    return raw


def test_inventory_pins_exactly_four_files_and_is_repeatable_without_mtime_change(
    tmp_path: Path,
) -> None:
    raw = _raw_fixture(tmp_path)
    mtimes = {path.name: path.stat().st_mtime_ns for path in raw.iterdir()}

    first = capture_corpus_source_inventory(raw)
    second = capture_corpus_source_inventory(raw)

    assert first == second
    assert tuple(item.relative_path for item in first.files) == CRAWLER_SOURCE_FILENAMES
    assert all(item.row_count == 1 for item in first.files)
    assert all(len(item.sha256) == 64 and len(item.identity_sha256) == 64 for item in first.files)
    assert len(first.source_inventory_sha256) == 64
    assert mtimes == {path.name: path.stat().st_mtime_ns for path in raw.iterdir()}


def test_inventory_rejects_a_fifth_source_missing_files_and_duplicate_identity(tmp_path: Path) -> None:
    raw = _raw_fixture(tmp_path)
    with pytest.raises(ValueError, match="exactly the four"):
        capture_corpus_source_inventory(raw, filenames=(*CRAWLER_SOURCE_FILENAMES, "documents.jsonl"))

    (raw / "wikitext.jsonl").unlink()
    with pytest.raises(FileNotFoundError, match="wikitext"):
        capture_corpus_source_inventory(raw)

    raw = _raw_fixture(tmp_path / "duplicate")
    duplicate = {"site": "res1999", "pageid": 1, "seen_at": "t1", "title": "B"}
    _write_jsonl(raw / "pages.jsonl", [duplicate, duplicate])
    with pytest.raises(ValueError, match="duplicate source identity"):
        capture_corpus_source_inventory(raw)


def test_inventory_rejects_non_crawler_labels_and_local_path_escape(tmp_path: Path) -> None:
    raw = _raw_fixture(tmp_path)
    _write_jsonl(
        raw / "data_pages.jsonl",
        [{
            "site": "res1999",
            "pageid": 2,
            "revid": 22,
            "source_mode": "obsidian",
        }],
    )
    with pytest.raises(ValueError, match="forbidden source label"):
        capture_corpus_source_inventory(raw)

    raw = _raw_fixture(tmp_path / "escape")
    _write_jsonl(
        raw / "resources_manifest.jsonl",
        [{
            "site": "res1999",
            "title": "文件:A.webp",
            "sha1": "a" * 40,
            "url": "https://example.test/A.webp",
            "source": "huiji_file_namespace",
            "local_relpath": "../outside.webp",
        }],
    )
    with pytest.raises(ValueError, match="escapes raw root"):
        capture_corpus_source_inventory(raw)


def test_inventory_detects_mid_read_file_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _raw_fixture(tmp_path)
    original = inventory_module._file_signature
    calls = 0

    def drifting(path: Path) -> tuple[int, int]:
        nonlocal calls
        calls += 1
        size, mtime = original(path)
        return (size, mtime + 1) if calls == 2 else (size, mtime)

    monkeypatch.setattr(inventory_module, "_file_signature", drifting)
    with pytest.raises(ValueError, match="changed while being read"):
        capture_corpus_source_inventory(raw)


def test_code_fingerprint_uses_participating_file_bytes_not_git(tmp_path: Path) -> None:
    root = tmp_path / "project"
    first = root / "src" / "a.py"
    second = root / "src" / "b.py"
    first.parent.mkdir(parents=True)
    first.write_text("VALUE = 1\n", encoding="utf-8")
    second.write_text("VALUE = 2\n", encoding="utf-8")

    before = capture_code_fingerprint(root, [second, first])
    same = capture_code_fingerprint(root, [first, second])
    assert before == same
    assert [item["path"] for item in before["files"]] == ["src/a.py", "src/b.py"]

    second.write_text("VALUE = 3\n", encoding="utf-8")
    after = capture_code_fingerprint(root, [first, second])
    assert after["code_fingerprint_sha256"] != before["code_fingerprint_sha256"]
