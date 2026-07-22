from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.verify_huiji_project_boundary import (
    ForbiddenFileAccess,
    ForbiddenOpenGuard,
    ReadOnlyRequestAudit,
    _last_json_object,
)


def test_forbidden_open_guard_allows_project_file_and_blocks_forbidden_root(tmp_path: Path):
    project = tmp_path / "project"
    forbidden = tmp_path / "legacy"
    project.mkdir()
    forbidden.mkdir()
    guard = ForbiddenOpenGuard([forbidden])

    guard("open", (str(project / "config.dat"), "r", 0))

    with pytest.raises(ForbiddenFileAccess, match="legacy"):
        guard("open", (str(forbidden / "config.dat"), "r", 0))

    assert guard.blocked_access_count == 1
    assert guard.blocked_paths == [str((forbidden / "config.dat").resolve())]


def test_forbidden_open_guard_ignores_non_path_open_events(tmp_path: Path):
    guard = ForbiddenOpenGuard([tmp_path / "legacy"])

    guard("open", (3, "r", 0))
    guard("other.event", (str(tmp_path / "legacy" / "config.dat"),))

    assert guard.blocked_access_count == 0


def test_boundary_wrapper_source_contains_no_hardcoded_legacy_root():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "verify_huiji_project_boundary.py").read_text(encoding="utf-8")

    assert "1999WIKI_ROBOT" not in text
    assert "--tool-root" in text
    assert "--forbid-root" in text
    assert "sys.addaudithook" in text
    assert text.index("sys.dont_write_bytecode = True") < text.index(
        "from src.huiji_crawler_tool.cli import main as crawler_tool_main"
    )
    assert "src.huiji_crawler_tool.cli" in text
    assert "scripts.crawl_huiji_res1999" not in text


def test_boundary_wrapper_has_only_stdlib_imports_before_argument_parsing():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "verify_huiji_project_boundary.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    allowed_roots = {
        "__future__",
        "argparse",
        "contextlib",
        "io",
        "json",
        "os",
        "sys",
        "tempfile",
        "pathlib",
        "urllib",
    }

    for node in tree.body:
        if isinstance(node, ast.Import):
            assert {alias.name.split(".")[0] for alias in node.names} <= allowed_roots
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in allowed_roots


def test_read_only_request_audit_records_only_sanitized_request_metadata():
    audit = ReadOnlyRequestAudit()

    audit.observe(
        method="get",
        url="https://res1999.huijiwiki.com/api.php?token=private",
        params={"action": "query", "token": "private"},
    )

    assert audit.non_read_only_action_count == 0
    assert audit.requests == [
        {
            "method": "GET",
            "scheme": "https",
            "host": "res1999.huijiwiki.com",
            "path": "/api.php",
            "action": "query",
        }
    ]


def test_read_only_request_audit_blocks_write_before_dispatch():
    audit = ReadOnlyRequestAudit()

    with pytest.raises(RuntimeError, match="POST action=edit"):
        audit.observe(
            method="POST",
            url="https://res1999.huijiwiki.com/api.php",
            params={"action": "edit"},
        )

    assert audit.non_read_only_action_count == 1


def test_last_json_object_ignores_non_json_output():
    assert _last_json_object('notice\n{"account":"POTATO BOT"}\n') == {"account": "POTATO BOT"}
