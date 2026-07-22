from __future__ import annotations

from pathlib import Path
import json

import src.huiji_wiki.compatibility_receipt as receipt_module
from src.huiji_wiki.compatibility_receipt import evaluate_shared_fixture, write_passing_receipt


def test_missing_shared_fixture_is_deterministically_blocked_without_output(tmp_path: Path):
    output = tmp_path / "receipt.json"

    payload = write_passing_receipt(tmp_path, output)

    assert payload["status"] == "blocked_shared_fixture_missing"
    assert payload["missing"] == [
        "expected_bindings.json",
        "expected_resources.json",
        "media_assets.v3.jsonl",
        "media_assets.v3.schema.json",
    ]
    assert output.exists() is False
    assert evaluate_shared_fixture(tmp_path) == payload


def test_passing_fixture_writes_create_new_hash_pinned_receipt(tmp_path: Path, monkeypatch):
    fixture_root = tmp_path / "tests/fixtures/contracts/huiji_media_v3"
    fixture_root.mkdir(parents=True)
    (fixture_root / "media_assets.v3.schema.json").write_text(
        json.dumps({"schema_version": "evb.media-assets/v3"}), encoding="utf-8"
    )
    (fixture_root / "media_assets.v3.jsonl").write_text(
        '{"owner_page_id":"char:1"}\n{"owner_page_id":"char:2"}\n', encoding="utf-8"
    )
    (fixture_root / "expected_resources.json").write_text(
        json.dumps([{"resource_id": "resource:1"}]), encoding="utf-8"
    )
    (fixture_root / "expected_bindings.json").write_text(
        json.dumps([{"binding_id": "binding:1"}, {"binding_id": "binding:2"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(receipt_module, "normalize_media_v3_rows", lambda _rows: (
        [{"resource_id": "resource:1"}],
        [
            {"binding_id": "binding:1", "resource_id": "resource:1"},
            {"binding_id": "binding:2", "resource_id": "resource:1"},
        ],
        [],
    ))
    output = tmp_path / "receipt.json"

    payload = write_passing_receipt(tmp_path, output)

    assert payload["status"] == "passed"
    assert payload["input_binding_count"] == 2
    assert payload["unique_binding_count"] == 2
    assert payload["resource_count"] == 1
    assert payload["resource_to_many_binding_count"] == 1
    assert len(payload["fixtures"]) == 4
    assert all(len(item["sha256"]) == 64 for item in payload["fixtures"])
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"
