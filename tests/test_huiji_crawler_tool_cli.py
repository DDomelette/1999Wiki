from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.huiji_crawler_tool.cli as cli
from src.huiji_crawler_tool.errors import (
    CrawlerConfigError,
    CrawlerEnvironmentError,
    PackageIntegrityError,
    RuntimeLockConflict,
)
from src.huijiwiki.credential_schema import CanonicalCredential
from src.huijiwiki.errors import (
    AccountMismatchError,
    ApiResponseError,
    CredentialLoadError,
    SessionExpiredError,
)


def _write_tool(root: Path) -> None:
    config = root / "config" / "crawler.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        """schema_version: huiji_crawler_config.v1
site:
  expected_user: POTATO BOT
crawl:
  namespaces: [0, 3500]
  include_file_manifest: false
  sleep_seconds: 1.0
  progress: true
  log_every: 100
  transport: requests
browser:
  headless: false
  verify_account: true
edge:
  port: 9222
""",
        encoding="utf-8",
    )


def _write_credential(root: Path, secret: str = "session-secret") -> Path:
    target = root / ".local" / "accounts" / "default" / "credential.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
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
                        "http_only": True,
                    }
                ],
            }
        ).to_bytes()
    )
    return target


def test_cli_exposes_exact_p1_command_surface_without_p2_commands() -> None:
    parser = cli.build_parser()
    help_text = parser.format_help()

    for command in ("crawl", "credential", "doctor", "verify-package"):
        assert command in help_text
    for deferred in ("schedule", "account add", "dpapi", "gui"):
        assert deferred not in help_text.casefold()

    assert parser.parse_args(["credential", "status"]).credential_command == "status"
    assert parser.parse_args(["credential", "import", "--legacy-source", "legacy.dat"]).credential_command == "import"
    assert parser.parse_args(["credential", "refresh"]).credential_command == "refresh"


def test_crawl_cli_uses_cli_then_env_then_yaml_and_builds_core_config(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root)
    captured = []
    monkeypatch.setattr(cli, "run_crawl", lambda config: captured.append(config) or {"ok": True})

    exit_code = cli.main(
        ["crawl", "--transport", "browser", "--namespaces", "10,14", "--dry-run"],
        tool_root=root,
        environ={"HUIJI_CRAWLER_TRANSPORT": "edge", "HUIJI_CRAWLER_LOG_EVERY": "25"},
    )

    assert exit_code == 0
    assert captured[0].transport == "browser"
    assert captured[0].namespaces == [10, 14]
    assert captured[0].log_every == 25
    assert captured[0].dry_run is True
    assert captured[0].out == root / "workspace" / "default" / "res1999"
    assert json.loads(capsys.readouterr().out) == {"ok": True}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CredentialLoadError("credential"), 2),
        (SessionExpiredError("session"), 2),
        (CrawlerConfigError("config"), 3),
        (PackageIntegrityError("package"), 4),
        (ApiResponseError("api"), 5),
        (AccountMismatchError("account"), 6),
        (RuntimeLockConflict("lock"), 7),
        (CrawlerEnvironmentError("environment"), 8),
    ],
)
def test_cli_maps_domain_failures_to_stable_exit_codes(
    tmp_path: Path,
    monkeypatch,
    capsys,
    error: Exception,
    expected: int,
) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "dispatch", fail)

    assert cli.main(["doctor"], tool_root=root, environ={}) == expected
    captured = capsys.readouterr()
    assert type(error).__name__ in captured.err
    assert "Traceback" not in captured.err


def test_unexpected_cli_error_reports_type_without_secret_message(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root)

    def fail(*args, **kwargs):
        raise RuntimeError("session-secret-must-not-appear")

    monkeypatch.setattr(cli, "dispatch", fail)

    assert cli.main(["doctor"], tool_root=root, environ={}) == 1
    assert "session-secret-must-not-appear" not in capsys.readouterr().err


def test_missing_credential_fails_before_workspace_or_network(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root)
    network_called = False

    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            nonlocal network_called
            network_called = True
            raise AssertionError("network client must not be created")

    monkeypatch.setattr("src.huijiwiki.crawler.HuijiApiClient", ForbiddenClient)

    exit_code = cli.main(["crawl", "--dry-run"], tool_root=root, environ={})

    assert exit_code == 2
    assert network_called is False
    assert not (root / "workspace").exists()
    assert "credential refresh" in capsys.readouterr().err


def test_account_mismatch_writes_no_crawl_workspace(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root)
    _write_credential(root)

    class WrongAccountClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_userinfo(self):
            return {"query": {"userinfo": {"name": "Personal User"}}}

        def get_siteinfo(self):
            raise AssertionError("siteinfo must not run for wrong account")

        def close(self):
            pass

    monkeypatch.setattr("src.huijiwiki.crawler.HuijiApiClient", WrongAccountClient)

    assert cli.main(["crawl", "--dry-run"], tool_root=root, environ={}) == 6
    assert not (root / "workspace").exists()


def test_credential_status_is_redacted(tmp_path: Path, capsys) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root)
    _write_credential(root, secret="private-cookie-value")

    assert cli.main(["credential", "status"], tool_root=root, environ={}) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == "valid"
    assert report["credential"]["cookie_names"] == ["huiji_session"]
    assert "private-cookie-value" not in output


def test_old_python_scripts_are_thin_unified_cli_wrappers() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in (
        "crawl_huiji_res1999.py",
        "import_huiji_credentials.py",
        "refresh_huiji_credentials.py",
    ):
        text = (root / "scripts" / name).read_text(encoding="utf-8")
        assert "ArgumentParser" not in text
        assert "get_config" not in text
        assert "src.huiji_crawler_tool.cli" in text


def test_legacy_import_wrapper_translates_source_option(tmp_path: Path, monkeypatch) -> None:
    import scripts.import_huiji_credentials as wrapper

    captured = []
    monkeypatch.setattr(wrapper, "crawler_tool_main", lambda argv, **kwargs: captured.append(argv) or 0)

    assert wrapper.main(["--source", str(tmp_path / "legacy.dat"), "--replace"]) == 0
    assert captured == [
        ["credential", "import", "--legacy-source", str(tmp_path / "legacy.dat"), "--replace"]
    ]
