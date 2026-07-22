from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.runtime_path_audit import PathAuditPolicyError, audit_external_paths


def _write_policy(root: Path, entries: list[dict[str, str]]) -> Path:
    path = root / "config" / "external-path-allowlist.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"schema_version": "external_path_allowlist.v1", "entries": entries},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_audit_detects_drive_unc_and_file_urls_but_not_http_urls(tmp_path: Path):
    root = tmp_path / "project"
    source = root / "src" / "paths.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        'drive = r"D:\\external\\data"\n'
        'unc = r"\\\\server\\share\\data"\n'
        'local_url = "file:///C:/private/data.json"\n'
        'http_url = "https://example.com/C:/not-a-local-path"\n',
        encoding="utf-8",
    )
    policy = _write_policy(root, [])

    report = audit_external_paths(root, policy)
    values = [match["value"] for match in report["matches"]]

    assert any(value.startswith("D:\\external") for value in values)
    assert any(value.startswith("\\\\server\\share") for value in values)
    assert "file:///C:/private/data.json" in values
    assert all(not value.startswith("https://") for value in values)
    assert report["unclassified_external_path_count"] == 3


def test_audit_ignores_path_detection_regexes_and_bare_markers(tmp_path: Path):
    root = tmp_path / "project"
    source = root / "src" / "diagnostics.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        'drive_regex = r"[A-Z]:[\\\\/]"\n'
        'unc_regex = r"\\\\\\\\[^\\s]+"\n'
        'markers = (r"D:\\\\", r"C:\\\\", "file://")\n',
        encoding="utf-8",
    )
    policy = _write_policy(root, [])

    report = audit_external_paths(root, policy)

    assert report["matches"] == []


def test_audit_scans_active_ini_configuration(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "pytest.ini").write_text(
        "[tool]\nexternal = D:\\external\\runtime\n",
        encoding="utf-8",
    )
    policy = _write_policy(root, [])

    report = audit_external_paths(root, policy)

    assert report["unclassified_external_path_count"] == 1
    assert report["matches"][0]["file"] == "pytest.ini"


def test_audit_applies_only_exact_narrow_allowlist_entries(tmp_path: Path):
    root = tmp_path / "project"
    source = root / "src" / "browser.py"
    source.parent.mkdir(parents=True)
    external = r"C:\Program Files\Browser\browser.exe"
    source.write_text(f'executable = r"{external}"\n', encoding="utf-8")
    policy = _write_policy(
        root,
        [
            {
                "id": "system-browser",
                "file": "src/browser.py",
                "value": external,
                "category": "system_executable",
                "reason": "Approved system browser discovery candidate.",
            }
        ],
    )

    report = audit_external_paths(root, policy)

    assert report["unclassified_external_path_count"] == 0
    assert report["stale_allowlist_count"] == 0
    assert report["matches"][0]["category"] == "system_executable"
    assert report["matches"][0]["allowlist_id"] == "system-browser"


@pytest.mark.parametrize(
    "entry",
    [
        {
            "id": "wild-file",
            "file": "src/*.py",
            "value": r"C:\external\tool.exe",
            "category": "system_executable",
            "reason": "Too broad.",
        },
        {
            "id": "wild-value",
            "file": "src/tool.py",
            "value": r"C:\external\*",
            "category": "system_executable",
            "reason": "Too broad.",
        },
        {
            "id": "bad-category",
            "file": "src/tool.py",
            "value": r"C:\external\tool.exe",
            "category": "project_data",
            "reason": "Project data cannot be allowed.",
        },
    ],
)
def test_audit_rejects_broad_or_unapproved_allowlist_entries(tmp_path: Path, entry):
    root = tmp_path / "project"
    root.mkdir()
    policy = _write_policy(root, [entry])

    with pytest.raises(PathAuditPolicyError):
        audit_external_paths(root, policy)


def test_audit_reports_stale_allowlist_entry(tmp_path: Path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "tool.py").write_text("value = 1\n", encoding="utf-8")
    policy = _write_policy(
        root,
        [
            {
                "id": "stale",
                "file": "src/tool.py",
                "value": r"C:\missing\tool.exe",
                "category": "system_executable",
                "reason": "Must become stale.",
            }
        ],
    )

    report = audit_external_paths(root, policy)

    assert report["stale_allowlist_count"] == 1
    assert report["stale_allowlist_ids"] == ["stale"]


def test_audit_never_reads_private_generated_or_historical_scopes(tmp_path: Path):
    root = tmp_path / "project"
    private_paths = [
        root / ".env",
        root / ".local" / "credential.dat",
        root / "data" / "raw.txt",
        root / "eval" / "evidence.json",
        root / "tests" / "test_fixture.py",
        root / "frontend" / "react-app" / "dist" / "bundle.js",
        root / "docs" / "superpowers" / "specs" / "old.md",
        root / "docs" / "huiji-crawler" / "specs" / "old.md",
        root / "docs" / "huiji-crawler" / "plans" / "old.md",
        root / "backups" / "snapshot.txt",
    ]
    for path in private_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(r"D:\must-not-be-read", encoding="utf-8")
    policy = _write_policy(root, [])

    report = audit_external_paths(root, policy)
    encoded = json.dumps(report, sort_keys=True)

    assert report["matches"] == []
    assert "must-not-be-read" not in encoded
    excluded = {item["path"]: item["reason"] for item in report["excluded_scopes"]}
    assert ".env" in excluded
    assert ".local" in excluded
    assert "data" in excluded
    assert "tests" in excluded
    assert "docs/superpowers/specs" in excluded
    assert "docs/huiji-crawler/specs" in excluded
    assert "docs/huiji-crawler/plans" in excluded
    assert "config/external-path-allowlist.yaml" in excluded


def test_audit_report_never_echoes_unrelated_secret_text(tmp_path: Path):
    root = tmp_path / "project"
    source = root / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text('api_key = "secret-value"\npath = r"D:\\external\\data"\n', encoding="utf-8")
    policy = _write_policy(root, [])

    report = audit_external_paths(root, policy)

    assert "secret-value" not in json.dumps(report, sort_keys=True)
