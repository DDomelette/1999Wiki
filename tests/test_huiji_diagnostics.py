import json
from types import SimpleNamespace

from scripts.diagnose_huiji_artifacts import default_processed_dir, diagnose_artifacts
from src.huiji_rag.io import write_jsonl


def test_diagnose_artifacts_reports_media_contract_problems(tmp_path):
    processed = tmp_path / "processed"
    write_jsonl(
        processed / "media_assets.jsonl",
        [
            {
                "media_id": "media-ok",
                "entity_name": "十四行诗",
                "parent_id": "char:3023/profile",
                "child_id": "char:3023/profile:0000",
                "asset_type": "portrait",
                "attach_policy": "auto",
                "object_key": "reverse1999/image/aa/a.webp",
                "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/a.webp",
                "local_relpath": "assets/files/aa/a.webp",
            },
            {
                "media_id": "media-local",
                "entity_name": "十四行诗",
                "parent_id": "char:3023/profile",
                "child_id": "char:3023/profile:0000",
                "asset_type": "portrait",
                "attach_policy": "auto",
                "object_key": "reverse1999/image/bb/b.webp",
                "url": "D:\\assets\\b.webp",
                "local_relpath": "assets/files/bb/b.webp",
            },
            {
                "media_id": "media-missing-fields",
                "entity_name": "",
                "child_id": "char:3023/profile:0001",
                "asset_type": "image",
                "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/cc/c.webp",
            },
        ],
    )
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": "char:3023/profile:0000",
                "media_ids": ["media-ok", "media-missing-from-assets"],
            }
        ],
    )
    (processed / "build_manifest.json").write_text(
        json.dumps({"build_version": "test", "media_count": 3}),
        encoding="utf-8",
    )

    report = diagnose_artifacts(processed)

    assert report["build_version"] == "test"
    assert report["media_records"] == 3
    assert report["unique_object_keys"] == 2
    assert report["non_http_url_count"] == 1
    assert report["local_path_url_count"] == 1
    assert report["missing_required_field_count"] == 4
    assert report["child_media_missing_asset_count"] == 1
    assert report["media_without_child_reference_count"] == 2
    assert report["asset_type_counts"]["portrait"] == 2


def test_default_processed_dir_uses_existing_build_paths_contract(tmp_path):
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="dev",
        )
    )

    assert default_processed_dir(cfg) == tmp_path / "processed" / "dev"
