from __future__ import annotations

import json

from scripts.verify_huiji_wiki_e2e import (
    build_parser,
    build_inspection_summary,
    collect_media_urls,
    find_local_path_leaks,
    load_minio_object_keys,
    load_object_keys_from_media_assets,
    validate_crawler_character_contract,
    validate_search_probe,
    validate_media_asset_minio_coverage,
    walk_opaque_page_list,
)


def test_parser_accepts_machine_readable_output_path():
    args = build_parser().parse_args(["--output", "eval/wiki-report.json"])

    assert args.output == "eval/wiki-report.json"


def test_parser_accepts_crawler_contract_flags():
    args = build_parser().parse_args(
        [
            "--require-crawler-contract",
            "--expected-character-pages",
            "132",
            "--sample-title",
            "槲寄生",
        ]
    )

    assert args.require_crawler_contract is True
    assert args.expected_character_pages == 132
    assert args.sample_title == "槲寄生"


def test_parser_accepts_page_list_and_repeated_search_probes():
    args = build_parser().parse_args(
        [
            "--check-page-list",
            "--page-list-type",
            "character",
            "--search-probe",
            "J",
            "--search-probe",
            "6",
            "--search-probe",
            "露西",
        ]
    )

    assert args.check_page_list is True
    assert args.page_list_type == "character"
    assert args.search_probe == ["J", "6", "露西"]


def test_find_local_path_leaks_recurses_payload():
    payload = {
        "pageId": "char:3074",
        "content": {"source": "Data:Char/3074.json"},
        "mediaLinks": [
            {"url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/a.webp"},
            {"url": "D:\\assets\\local.png"},
            {"local_relpath": "assets/files/local.png"},
        ],
    }

    leaks = find_local_path_leaks(payload)

    assert any("D:\\assets\\local.png" in leak for leak in leaks)
    assert any("local_relpath" in leak for leak in leaks)


def test_find_local_path_leaks_rejects_supplement_audit_fields():
    payload = {
        "content": {
            "sourceKey": "槲寄生｜Druvis III.md",
            "sourceSha256": "abc123",
            "diagnostics": {"conflicts": []},
        }
    }

    leaks = find_local_path_leaks(payload)

    assert any("sourceKey" in leak for leak in leaks)
    assert any("sourceSha256" in leak for leak in leaks)
    assert any("diagnostics" in leak for leak in leaks)


def test_collect_media_urls_returns_only_http_urls():
    payload = {
        "items": [
            {"url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/a.webp"},
            {"url": "https://cdn.example/reverse1999/image/b.webp"},
            {"url": "D:\\assets\\local.png"},
        ]
    }

    assert collect_media_urls(payload) == [
        "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/a.webp",
        "https://cdn.example/reverse1999/image/b.webp",
    ]


def test_validate_media_asset_minio_coverage_reports_missing_keys(tmp_path):
    media_assets = tmp_path / "media_assets.jsonl"
    media_assets.write_text(
        "\n".join(
            [
                json.dumps({"media_id": "m1", "object_key": "reverse1999/image/aa/m1.webp"}),
                json.dumps({"media_id": "m2", "object_key": "reverse1999/portrait/bb/m2.webp"}),
                json.dumps({"media_id": "empty", "object_key": ""}),
            ]
        ),
        encoding="utf-8",
    )
    minio_keys = tmp_path / "minio_keys.txt"
    minio_keys.write_text("reverse1999/image/aa/m1.webp\n", encoding="utf-8")

    object_keys = load_object_keys_from_media_assets(media_assets)
    available = load_minio_object_keys(minio_keys)
    missing = validate_media_asset_minio_coverage(object_keys, available)

    assert object_keys == {"reverse1999/image/aa/m1.webp", "reverse1999/portrait/bb/m2.webp"}
    assert available == {"reverse1999/image/aa/m1.webp"}
    assert missing == ["reverse1999/portrait/bb/m2.webp"]


def test_build_inspection_summary_is_machine_readable():
    summary = build_inspection_summary(
        categories={"categories": [{"key": "character"}]},
        page_items=[{"pageId": "char:3074"}],
        media_urls=["http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/a.webp"],
        leaks=[],
        media_failures=[],
        missing_object_keys=[],
        label="nightly-wiki-media",
    )

    assert summary == {
        "label": "nightly-wiki-media",
        "ok": True,
        "category_count": 1,
        "page_count": 1,
        "http_media_url_count": 1,
        "local_path_leak_count": 0,
        "media_url_failure_count": 0,
        "missing_object_key_count": 0,
    }


def test_build_inspection_summary_marks_failures():
    summary = build_inspection_summary(
        categories={"categories": []},
        page_items=[],
        media_urls=[],
        leaks=["$.mediaLinks[0].local_relpath=<forbidden key>"],
        media_failures=["http://127.0.0.1/bad.webp -> HTTP 404"],
        missing_object_keys=["reverse1999/image/missing.webp"],
        label="wiki-media",
    )

    assert summary["ok"] is False
    assert summary["local_path_leak_count"] == 1
    assert summary["media_url_failure_count"] == 1
    assert summary["missing_object_key_count"] == 1


def test_validate_crawler_character_contract_accepts_projected_character_shape():
    health = {
        "pageCount": 7456,
        "stale": False,
    }
    detail = {
        "title": "槲寄生",
        "sourceTitle": "Data:Char/3003.json",
        "content": {
            "crawlerProjectionVersion": 1,
            "blocks": [
                {"type": "heading", "section": "inheritance", "text": "传承：木秀于林"},
                {
                    "type": "table",
                    "section": "inheritance",
                    "headers": ["洞悉", "效果"],
                    "rows": [["洞悉Ⅰ", "进入战斗时"], ["洞悉Ⅱ", "造成伤害提升"]],
                },
                {"type": "paragraph", "section": "portray", "text": "塑造说明"},
                {
                    "type": "table",
                    "section": "portray",
                    "headers": ["塑造等级", "效果"],
                    "rows": [[f"LV.{level}", f"效果 {level}"] for level in range(1, 6)],
                },
            ],
        },
        "mediaLinks": [
            {"role": "roster_avatar", "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/a.webp"},
            {"role": "stage_live2d", "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/b.webp"},
        ],
    }

    assert validate_crawler_character_contract(
        health,
        {"categories": [{"key": "character", "count": 132}]},
        detail,
        expected_pages=132,
        sample_title="槲寄生",
    ) == []


def test_validate_crawler_character_contract_reports_missing_projection_and_media():
    errors = validate_crawler_character_contract(
        {"pageCount": 131, "stale": True},
        {"categories": [{"key": "character", "count": 131}]},
        {"title": "槲寄生", "sourceTitle": "private.md", "content": {"blocks": []}, "mediaLinks": []},
        expected_pages=132,
        sample_title="槲寄生",
    )

    assert any("character page count" in error for error in errors)
    assert any("stale" in error for error in errors)
    assert any("crawlerProjectionVersion" in error for error in errors)
    assert any("Data:Char" in error for error in errors)
    assert any("inheritance" in error for error in errors)
    assert any("portray" in error for error in errors)
    assert any("LV.1..LV.5" in error for error in errors)
    assert any("roster_avatar" in error for error in errors)
    assert any("stage_live2d/stage_portrait" in error for error in errors)


def test_validate_crawler_character_contract_accepts_numeric_portray_levels():
    detail = {
        "title": "sample-character",
        "sourceTitle": "Data:Char/3003.json",
        "content": {
            "crawlerProjectionVersion": 1,
            "blocks": [
                {
                    "type": "table",
                    "section": "inheritance",
                    "rows": [["level", "effect"], ["1", "sample inheritance"]],
                },
                {
                    "type": "heading",
                    "section": "inheritance",
                    "text": "sample inheritance",
                },
                {
                    "type": "table",
                    "section": "portray",
                    "rows": [["level", "effect"], *[[str(level), f"effect {level}"] for level in range(1, 6)]],
                },
            ],
        },
        "mediaLinks": [
            {"role": "roster_avatar", "url": "http://127.0.0.1:9002/a.webp"},
            {"role": "stage_portrait", "url": "http://127.0.0.1:9002/b.webp"},
        ],
    }

    errors = validate_crawler_character_contract(
        {"pageCount": 7456, "stale": False},
        {"categories": [{"key": "character", "count": 132}]},
        detail,
        expected_pages=132,
        sample_title="sample-character",
    )

    assert not any("portray LV.1..LV.5" in error for error in errors)


def test_walk_opaque_page_list_follows_cursor_without_loss_or_duplicates():
    responses = {
        "": {"items": [{"pageId": "char:1"}, {"pageId": "char:2"}], "nextCursor": "opaque-a"},
        "opaque-a": {"items": [{"pageId": "char:3"}], "nextCursor": None},
    }

    items, errors = walk_opaque_page_list(lambda cursor: responses[cursor], expected_count=3)

    assert [item["pageId"] for item in items] == ["char:1", "char:2", "char:3"]
    assert errors == []


def test_walk_opaque_page_list_detects_duplicate_and_cursor_loop():
    responses = {
        "": {"items": [{"pageId": "char:1"}], "nextCursor": "opaque-a"},
        "opaque-a": {"items": [{"pageId": "char:1"}], "nextCursor": "opaque-a"},
    }

    _, errors = walk_opaque_page_list(lambda cursor: responses[cursor], expected_count=2)

    assert any("duplicate pageId" in error for error in errors)
    assert any("cursor loop" in error for error in errors)


def test_validate_search_probe_requires_exact_title_in_first_item():
    assert validate_search_probe({"items": [{"title": "J"}, {"title": "J女士"}]}, "J") == []

    errors = validate_search_probe({"items": [{"title": "J女士"}, {"title": "J"}]}, "J")

    assert any("first item" in error for error in errors)
