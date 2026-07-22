from __future__ import annotations

from pathlib import Path

import pytest

from scripts.migrate_wiki_to_crawler_source import (
    APPLY_CONFIRMATION_TOKEN,
    OBSIDIAN_REFERENCE_QUERY,
    evaluate_mysql_verification,
    execute_apply_pipeline,
    validate_apply_request,
)


def test_obsidian_reference_query_checks_provenance_fields_not_article_text():
    assert "crawlerSourceTitle" in OBSIDIAN_REFERENCE_QUERY
    assert "CAST(content_json AS CHAR)" not in OBSIDIAN_REFERENCE_QUERY


def test_validate_apply_request_requires_backup_and_exact_confirmation(tmp_path: Path):
    with pytest.raises(ValueError, match="backup directory"):
        validate_apply_request(apply=True, backup_dir=None, confirmation=APPLY_CONFIRMATION_TOKEN)
    with pytest.raises(ValueError, match="confirmation token"):
        validate_apply_request(apply=True, backup_dir=tmp_path, confirmation="wrong")

    validate_apply_request(
        apply=True,
        backup_dir=tmp_path,
        confirmation=APPLY_CONFIRMATION_TOKEN,
    )


def test_execute_apply_pipeline_cleans_only_after_verified_import():
    calls: list[str] = []

    result = execute_apply_pipeline(
        backup=lambda: calls.append("backup") or {"path": "backup.sql"},
        upload=lambda: calls.append("upload") or {"uploaded": 2},
        import_payload=lambda: calls.append("import") or {"pages": 3},
        verify=lambda: calls.append("verify") or {"ok": True},
        cleanup=lambda: calls.append("cleanup") or {"deleted": 4},
    )

    assert calls == ["backup", "upload", "import", "verify", "cleanup"]
    assert result["verification"]["ok"] is True
    assert result["cleanup"]["deleted"] == 4


def test_execute_apply_pipeline_never_cleans_after_failed_verification():
    calls: list[str] = []

    with pytest.raises(RuntimeError, match="verification failed"):
        execute_apply_pipeline(
            backup=lambda: calls.append("backup") or {},
            upload=lambda: calls.append("upload") or {},
            import_payload=lambda: calls.append("import") or {},
            verify=lambda: calls.append("verify") or {"ok": False, "errors": ["bad reference"]},
            cleanup=lambda: calls.append("cleanup") or {},
        )

    assert calls == ["backup", "upload", "import", "verify"]


def test_evaluate_mysql_verification_requires_exact_authoritative_counts_and_provenance():
    expected = {"pages": 10, "categories": 4, "media_links": 30, "character_pages": 3}
    actual = {
        **expected,
        "crawler_character_pages": 3,
        "characters_with_roster": 3,
        "characters_with_stage": 3,
        "private_media_refs": 0,
        "obsidian_refs": 0,
    }

    assert evaluate_mysql_verification(actual, expected) == {"ok": True, "errors": []}

    invalid = dict(actual)
    invalid["media_links"] = 29
    invalid["characters_with_stage"] = 2
    invalid["private_media_refs"] = 1
    result = evaluate_mysql_verification(invalid, expected)

    assert result["ok"] is False
    assert any("media_links" in error for error in result["errors"])
    assert any("characters_with_stage" in error for error in result["errors"])
    assert any("private_media_refs" in error for error in result["errors"])
