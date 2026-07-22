from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from src.huiji_rag.models import SourceInventory
from src.huiji_rag.io import capture_baseline_from_rows
from src.huiji_rag.source import capture_source_inventory


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_baseline_serializes_six_dynamic_classes():
    inventory = SourceInventory(
        source_inventory_sha256="source-hash",
        entity_rows=[{"pageid": 1}, {"pageid": 2}],
        resource_rows=[{"name": "voice"}],
    )
    media_rows = [
        {
            "media_id": "media:sha1:" + "a" * 40,
            "sha1": "a" * 40,
            "asset_type": "voice",
        },
        {
            "media_id": "media:sha1:" + "b" * 40,
            "sha1": "b" * 40,
            "asset_type": "image",
        },
    ]

    evidence = capture_baseline_from_rows(
        inventory,
        media_rows=media_rows,
        milvus_observation={"row_count": 7},
    )

    assert evidence.schema_version == "evb.baseline/v1"
    assert evidence.source_inventory_sha256 == "source-hash"
    assert evidence.observations == {
        "entity_row_count": 2,
        "resource_row_count": 1,
        "media_row_count": 2,
        "media_id_count": 2,
        "media_sha1_count": 2,
        "voice_media_row_count": 1,
    }
    assert evidence.milvus_observation == {"row_count": 7}
    assert "historical_expected_count" not in evidence.observations


def test_media_id_inventory_uses_full_sha1_pattern():
    inventory = SourceInventory("source-hash", [], [])
    evidence = capture_baseline_from_rows(
        inventory,
        media_rows=[
            {"media_id": "media:sha1:" + "a" * 40, "sha1": "a" * 40},
            {"media_id": "media:" + "b" * 16, "sha1": "b" * 40},
            {"media_id": "media:sha1:not-a-hash", "sha1": "c" * 40},
        ],
        milvus_observation={},
    )

    assert evidence.observations["media_id_count"] == 1
    assert evidence.observations["media_sha1_count"] == 3


def test_capture_cli_requires_build_output_and_returns_documented_codes(tmp_path, monkeypatch):
    script_path = Path(__file__).parents[1] / "scripts" / "capture_evb_baseline.py"
    spec = importlib.util.spec_from_file_location("capture_evb_baseline", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    _write_jsonl(raw_root / "pages.jsonl", [{"pageid": 1}])
    _write_jsonl(raw_root / "resources_manifest.jsonl", [])
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(raw_root=raw_root, processed_root=tmp_path / "processed")
    )
    monkeypatch.setattr(module, "get_config", lambda: cfg)
    monkeypatch.setattr("src.huiji_rag.io._capture_milvus_observation", lambda _cfg: {})

    missing_output = tmp_path / "missing.json"
    assert module.main(["--build", "missing", "--output", str(missing_output)]) == 2
    assert not missing_output.exists()

    build_root = tmp_path / "processed" / "dev"
    build_root.mkdir(parents=True)
    _write_jsonl(build_root / "parent_blocks.jsonl", [{"parent_id": "char:1"}])
    _write_jsonl(build_root / "child_blocks.jsonl", [{"child_id": "char:1/voice:1"}])
    _write_jsonl(
        build_root / "media_assets.jsonl",
        [{"media_id": "media:sha1:" + "a" * 40, "sha1": "a" * 40}],
    )

    output = tmp_path / "baseline.json"
    assert module.main(["--build", "dev", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == "evb.baseline/v1"
    assert module.main(["--build", "dev", "--output", str(output)]) == 3
