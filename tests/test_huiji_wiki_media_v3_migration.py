from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.migrate_wiki_media_v3 import migration_plan, validate_backup_evidence


def test_migration_plan_creates_resources_before_bindings_and_drops_in_reverse():
    apply_plan = migration_plan(rollback=False)
    rollback_plan = migration_plan(rollback=True)

    assert "CREATE TABLE IF NOT EXISTS wiki_media_resources" in apply_plan[0]
    assert "CREATE TABLE IF NOT EXISTS wiki_media_bindings" in apply_plan[1]
    assert rollback_plan == [
        "DROP TABLE IF EXISTS wiki_media_bindings",
        "DROP TABLE IF EXISTS wiki_media_resources",
    ]


def test_backup_evidence_rejects_credentials(tmp_path: Path):
    evidence = tmp_path / "backup.json"
    evidence.write_text(json.dumps({
        "schema_version": "huiji.wiki-media-v3-backup-evidence/v1",
        "verified": True,
        "password": "secret",
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="credentials"):
        validate_backup_evidence(evidence)
