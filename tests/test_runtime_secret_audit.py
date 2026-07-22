from __future__ import annotations

import json
from pathlib import Path

from src.runtime_secret_audit import audit_credential_secrecy


def _write_credential(path: Path, secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
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
                        "http_only": True,
                    },
                    {
                        "name": "huijiUserName",
                        "value": "POTATO BOT",
                        "domain": ".huijiwiki.com",
                        "path": "/",
                        "expires": None,
                        "secure": True,
                        "http_only": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_secret_audit_reports_cookie_name_and_file_without_echoing_value(tmp_path: Path):
    root = tmp_path / "project"
    credential = root / ".local" / "huiji" / "credentials" / "config.dat"
    leaked_secret = "real-session-secret-value"
    _write_credential(credential, leaked_secret)
    source = root / "src" / "leak.py"
    source.parent.mkdir(parents=True)
    source.write_text(f'copied = "{leaked_secret}"\n', encoding="utf-8")
    (root / ".env").write_text(f"IGNORED={leaked_secret}\n", encoding="utf-8")

    report = audit_credential_secrecy(root, credential)
    encoded = json.dumps(report, sort_keys=True)

    assert report["violation_count"] == 1
    assert report["violations"] == [
        {"file": "src/leak.py", "line": 1, "cookie_name": "huiji_session"}
    ]
    assert leaked_secret not in encoded
    assert "POTATO BOT" not in encoded
    assert ".env" not in report["scanned_files"]
    assert ".local/huiji/credentials/config.dat" not in report["scanned_files"]


def test_secret_audit_clean_tree_has_zero_violations(tmp_path: Path):
    root = tmp_path / "project"
    credential = root / ".local" / "huiji" / "credentials" / "config.dat"
    _write_credential(credential, "real-session-secret-value")
    source = root / "src" / "clean.py"
    source.parent.mkdir(parents=True)
    source.write_text('message = "safe"\n', encoding="utf-8")

    report = audit_credential_secrecy(root, credential)

    assert report["violation_count"] == 0
    assert report["violations"] == []
