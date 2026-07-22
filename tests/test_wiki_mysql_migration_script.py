from __future__ import annotations

from pathlib import Path


def test_wiki_mysql_migration_script_uses_dump_restore_not_volume_copy():
    script = Path("scripts/migrate_wiki_mysql.ps1").read_text(encoding="utf-8")

    assert "mysqldump" in script
    assert "reverse1999_wiki" in script
    assert "docker cp" not in script
    assert "Remove-Item" not in script
    assert "DROP DATABASE" not in script
    assert "edurag-mysql" in script
    assert "reverse1999-main-mysql" in script


def test_wiki_mysql_migration_script_does_not_default_source_password():
    script = Path("scripts/migrate_wiki_mysql.ps1").read_text(encoding="utf-8")

    assert 'SourceRootPassword = "123456"' not in script
    assert "Resolve-RootPassword" in script
    assert "SOURCE_MYSQL_ROOT_PASSWORD" in script


def test_wiki_mysql_migration_script_preserves_utf8_bytes():
    script = Path("scripts/migrate_wiki_mysql.ps1").read_text(encoding="utf-8")

    assert "Set-Content" not in script
    assert "Get-Content -Raw" not in script
    assert "RedirectStandardOutput" in script
    assert "RedirectStandardInput" in script
    assert "HEX(title)" in script


def test_wiki_mysql_migration_script_avoids_powershell_args_auto_variable():
    script = Path("scripts/migrate_wiki_mysql.ps1").read_text(encoding="utf-8")

    assert "[string[]]$Args" not in script
