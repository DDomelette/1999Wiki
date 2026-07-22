from __future__ import annotations

import json
from pathlib import Path

import scripts.import_huiji_credentials as import_script
from src.huijiwiki.credential_schema import CanonicalCredential


def _write_tool_config(root: Path) -> None:
    path = root / "config" / "crawler.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """schema_version: huiji_crawler_config.v1
site:
  expected_user: POTATO BOT
""",
        encoding="utf-8",
    )


def _write_legacy_source(path: Path, secret: str = "session-secret") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "huiji_session",
                        "value": secret,
                        "domain": ".huijiwiki.com",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_canonical_target(path: Path, secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        CanonicalCredential.from_payload(
            {
                "schema_version": "huiji_credential.v2",
                "expected_user": "POTATO BOT",
                "cookies": [
                    {
                        "name": "huiji_session",
                        "value": secret,
                        "domain": ".huijiwiki.com",
                        "path": "/",
                        "expires": None,
                        "secure": True,
                        "http_only": False,
                    }
                ],
            }
        ).to_bytes()
    )


def test_import_cli_uses_fixed_target_and_emits_redacted_json(tmp_path, capsys):
    root = tmp_path / "tool"
    source = tmp_path / "external" / "config.dat"
    target = root / ".local" / "accounts" / "default" / "credential.json"
    root.mkdir()
    _write_tool_config(root)
    _write_legacy_source(source)

    exit_code = import_script.main(["--source", str(source)], tool_root=root)

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert exit_code == 0
    assert report["status"] == "imported"
    assert target.read_bytes() != source.read_bytes()
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == "huiji_credential.v2"
    assert report["source"]["sha256"] != report["target"]["sha256"]
    assert "session-secret" not in captured.out
    assert "session-secret" not in captured.err


def test_import_cli_writes_canonical_report_to_tool_local_output(tmp_path, capsys):
    root = tmp_path / "tool"
    source = tmp_path / "external" / "config.dat"
    output = root / "eval" / "credential-import.v2.json"
    root.mkdir()
    _write_tool_config(root)
    _write_legacy_source(source)

    exit_code = import_script.main(
        ["--source", str(source), "--output", str(output)],
        tool_root=root,
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == "huiji_credential_import.v2"
    assert report["status"] == "imported"
    assert "session-secret" not in output.read_text(encoding="utf-8")


def test_import_cli_rejects_external_report_before_writing_target(tmp_path, capsys):
    root = tmp_path / "tool"
    source = tmp_path / "external" / "config.dat"
    target = root / ".local" / "accounts" / "default" / "credential.json"
    output = tmp_path / "outside" / "report.json"
    root.mkdir()
    _write_tool_config(root)
    _write_legacy_source(source)

    exit_code = import_script.main(
        ["--source", str(source), "--output", str(output)],
        tool_root=root,
    )

    captured = capsys.readouterr()
    assert exit_code == 3
    assert not target.exists()
    assert not output.exists()
    assert "inside the tool root" in captured.err


def test_import_cli_conflict_requires_replace(tmp_path, capsys):
    root = tmp_path / "tool"
    source = tmp_path / "external" / "config.dat"
    target = root / ".local" / "accounts" / "default" / "credential.json"
    root.mkdir()
    _write_tool_config(root)
    _write_legacy_source(source, "new-secret")
    _write_canonical_target(target, "existing-secret")
    original = target.read_bytes()

    exit_code = import_script.main(["--source", str(source)], tool_root=root)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert target.read_bytes() == original
    assert "new-secret" not in captured.err
    assert "existing-secret" not in captured.err


def test_import_cli_missing_source_returns_credential_exit(tmp_path, capsys):
    root = tmp_path / "tool"
    target = root / ".local" / "accounts" / "default" / "credential.json"
    root.mkdir()
    _write_tool_config(root)

    exit_code = import_script.main(
        ["--source", str(tmp_path / "missing.dat")],
        tool_root=root,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "cannot be read" in captured.err.lower()
    assert not target.exists()
