from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from src.huiji_crawler_tool.path_audit import PathAuditPolicyError, audit_crawler_paths


def _policy(root: Path, entries: list[dict[str, str]] | None = None) -> Path:
    path = root / "config" / "external-path-allowlist.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"schema_version": "external_path_allowlist.v1", "entries": entries or []},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_python_ast_finds_runtime_path_but_ignores_regex_comments_and_docstrings(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    source = root / "src" / "tool.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        'r"""Historical example D:\\docs\\old-project."""\n'
        "import re\nfrom pathlib import Path\n"
        'drive_regex = r"[A-Z]:[\\\\/]"\n'
        'compiled = re.compile(r"(?i)([A-Z]:[\\\\/]+[^\\s]+)")\n'
        '# D:\\comment\\not-runtime\n'
        'runtime_path = Path(r"D:\\external\\runtime")\n',
        encoding="utf-8",
    )

    report = audit_crawler_paths(root, _policy(root), includes=[source])

    assert report["parse_error_count"] == 0
    assert report["unclassified_external_path_count"] == 1
    assert report["matches"][0]["parser"] == "python_ast"
    assert report["matches"][0]["value"] == r"D:\external\runtime"
    assert report["matches"][0]["line"] == 7


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None and shutil.which("powershell") is None,
    reason="PowerShell AST parsing is available only where PowerShell is installed",
)
def test_powershell_parser_finds_string_paths_with_line_and_column(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    source = root / "launch.ps1"
    root.mkdir()
    source.write_text('$edge = "C:\\External Tools\\edge.exe"\n', encoding="utf-8")

    report = audit_crawler_paths(root, _policy(root), includes=[source])

    assert report["parse_error_count"] == 0
    assert report["matches"][0]["parser"] == "powershell_ast"
    assert report["matches"][0]["line"] == 1
    assert report["matches"][0]["column"] > 0


def test_yaml_and_json_only_classify_path_semantics(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    config = root / "config" / "crawler.yaml"
    payload = root / "config" / "runtime.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        "runtime_path: 'D:\\runtime\\crawler'\napi_key: 'C:\\not-a-runtime-path\\secret'\n",
        encoding="utf-8",
    )
    payload.write_text(
        json.dumps(
            {
                "edge_executable": r"C:\Program Files\Edge\msedge.exe",
                "token": r"D:\not-a-runtime-path\secret",
            }
        ),
        encoding="utf-8",
    )

    report = audit_crawler_paths(root, _policy(root), includes=[config, payload])
    matches = {(item["parser"], item["value"]) for item in report["matches"]}

    assert matches == {
        ("json", r"C:\Program Files\Edge\msedge.exe"),
        ("yaml", r"D:\runtime\crawler"),
    }


def test_cmd_fallback_is_explicit_and_parse_failure_is_not_silent(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    launcher = root / "run.cmd"
    broken_json = root / "config" / "broken.json"
    broken_json.parent.mkdir(parents=True)
    launcher.write_text('@"C:\\Tools\\python.exe" -V\n', encoding="utf-8")
    broken_json.write_text('{"runtime_path": ', encoding="utf-8")

    report = audit_crawler_paths(root, _policy(root), includes=[launcher, broken_json])

    assert report["matches"][0]["parser"] == "text_fallback"
    assert report["parse_error_count"] == 1
    assert report["parse_errors"][0]["file"] == "config/broken.json"


def test_audit_distinguishes_http_loopback_drive_unc_and_file_url(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    source = root / "src" / "paths.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        'drive = r"D:\\external\\data"\n'
        'unc = r"\\\\server\\share\\data"\n'
        'local_url = "file:///C:/private/data.json"\n'
        'http_url = "https://example.com/C:/not-local"\n'
        'loopback = "http://127.0.0.1:9222"\n',
        encoding="utf-8",
    )

    report = audit_crawler_paths(root, _policy(root), includes=[source])
    values = {item["value"] for item in report["matches"]}

    assert values == {r"D:\external\data", r"\\server\share\data", "file:///C:/private/data.json"}


def test_exact_edge_allowlist_passes_and_stale_duplicate_entries_are_reported(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    source = root / "src" / "discovery.py"
    source.parent.mkdir(parents=True)
    edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    source.write_text(f'edge_executable = r"{edge}"\n', encoding="utf-8")
    policy = _policy(
        root,
        [
            {
                "id": "edge",
                "file": "src/discovery.py",
                "value": edge,
                "category": "system_executable",
                "reason": "Exact system Edge candidate.",
            },
            {
                "id": "edge-duplicate",
                "file": "src/discovery.py",
                "value": edge,
                "category": "system_executable",
                "reason": "Duplicate must be reported.",
            },
            {
                "id": "stale",
                "file": "src/discovery.py",
                "value": r"C:\missing\tool.exe",
                "category": "system_executable",
                "reason": "Stale must be reported.",
            },
        ],
    )

    report = audit_crawler_paths(root, policy, includes=[source])

    assert report["unclassified_external_path_count"] == 0
    assert report["duplicate_allowlist_count"] == 1
    assert report["stale_allowlist_count"] == 2
    assert report["matches"][0]["allowlist_id"] == "edge"


def test_wildcard_allowlist_entry_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    policy = _policy(
        root,
        [
            {
                "id": "wildcard",
                "file": "src/*.py",
                "value": r"C:\Tools\*",
                "category": "system_executable",
                "reason": "Too broad.",
            }
        ],
    )

    with pytest.raises(PathAuditPolicyError, match="Wildcards"):
        audit_crawler_paths(root, policy, includes=[])


def test_symlink_or_junction_escape_is_reported_from_real_path(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "tool.py").write_text('path = r"D:\\external\\data"\n', encoding="utf-8")
    link = root / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        environment = dict(os.environ)
        environment["HUIJI_TEST_LINK"] = str(link)
        environment["HUIJI_TEST_TARGET"] = str(outside)
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "New-Item -ItemType Junction -Path $env:HUIJI_TEST_LINK -Target $env:HUIJI_TEST_TARGET | Out-Null",
            ],
            capture_output=True,
            env=environment,
            text=True,
        )
        if completed.returncode != 0:
            pytest.skip("symlink and junction creation are unavailable")

    report = audit_crawler_paths(root, _policy(root), includes=[link])

    assert report["path_escape_count"] == 1
    assert report["scanned_files"] == []


def test_huiji_crawler_docs_are_non_executable_history_not_runtime_dependencies(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    docs = root / "docs" / "huiji-crawler" / "plans"
    docs.mkdir(parents=True)
    (docs / "old.md").write_text(r"Historical D:\old-project\crawler", encoding="utf-8")

    report = audit_crawler_paths(root, _policy(root), includes=[docs])

    assert report["matches"] == []
    assert report["scanned_files"] == []


def test_report_never_echoes_unrelated_secret_values(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    source = root / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        'api_key = "unrelated-secret-value"\nruntime_path = r"D:\\external\\data"\n',
        encoding="utf-8",
    )

    report = audit_crawler_paths(root, _policy(root), includes=[source])

    assert "unrelated-secret-value" not in json.dumps(report, sort_keys=True)
