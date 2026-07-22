from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.refresh_huiji_credentials as refresh_script
import src.huiji_crawler_tool.cli as crawler_cli
import src.huijiwiki.credential_store as credential_store
from src.huijiwiki.credential_refresh import (
    refresh_credentials,
    select_huiji_cookies,
    serialize_huiji_cookies,
)
from src.huijiwiki.credential_schema import CanonicalCredential
from src.huijiwiki.credential_store import CredentialValidationError
from src.huijiwiki.errors import AccountMismatchError, SessionExpiredError


def _browser_cookies(secret: str = "session-secret") -> list[dict[str, object]]:
    return [
        {
            "name": "huiji_session",
            "value": secret,
            "domain": ".huijiwiki.com",
            "path": "/",
            "expires": 1_900_000_000,
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        },
        {
            "name": "__cf_bm",
            "value": "cloudflare-secret",
            "domain": "res1999.huijiwiki.com",
            "path": "/",
            "expires": 1_900_000_100,
            "secure": True,
            "httpOnly": True,
        },
        {
            "name": "unrelated",
            "value": "other-domain-secret",
            "domain": "example.com",
            "path": "/",
        },
    ]


def _valid_existing_credential(secret: str = "old-secret") -> bytes:
    return CanonicalCredential.from_payload(
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


class FakeBrowserClient:
    def __init__(self, *, account: str = "POTATO BOT", cookies=None, error: Exception | None = None):
        self.account = account
        self.cookies = list(_browser_cookies() if cookies is None else cookies)
        self.error = error
        self.cookie_urls: list[str] = []
        self.closed = False

    def get_userinfo(self):
        if self.error is not None:
            raise self.error
        return {"query": {"userinfo": {"name": self.account}}}

    def get_cookies(self, url: str):
        self.cookie_urls.append(url)
        return list(self.cookies)

    def close(self):
        self.closed = True


def test_select_huiji_cookies_excludes_unrelated_domain_and_fields():
    selected = select_huiji_cookies(_browser_cookies())

    assert [item["name"] for item in selected] == ["__cf_bm", "huiji_session"]
    assert {item["domain"] for item in selected} == {".huijiwiki.com", "res1999.huijiwiki.com"}
    assert all("sameSite" not in item for item in selected)
    assert all("http_only" in item for item in selected)
    assert all("httpOnly" not in item for item in selected)
    assert "other-domain-secret" not in json.dumps(selected)


def test_serialize_huiji_cookies_is_deterministic_and_loader_compatible(tmp_path):
    first = serialize_huiji_cookies(
        list(reversed(_browser_cookies())),
        expected_user="POTATO BOT",
    )
    second = serialize_huiji_cookies(_browser_cookies(), expected_user="POTATO BOT")
    payload = json.loads(first.decode("utf-8"))

    assert first == second
    assert payload["schema_version"] == "huiji_credential.v2"
    assert payload["expected_user"] == "POTATO BOT"
    assert [item["name"] for item in payload["cookies"]] == ["__cf_bm", "huiji_session"]
    assert not first.startswith(b"\xef\xbb\xbf")


def test_refresh_credentials_verifies_account_then_atomically_writes_redacted_report(tmp_path):
    target = tmp_path / "config.dat"
    client = FakeBrowserClient()

    report = refresh_credentials(client, expected_user="POTATO BOT", target=target)

    encoded = json.dumps(report, sort_keys=True)
    assert report["status"] == "refreshed"
    assert report["account"] == "POTATO BOT"
    assert report["target"]["cookie_names"] == ["__cf_bm", "huiji_session"]
    assert "session-secret" not in encoded
    assert "cloudflare-secret" not in encoded
    assert client.cookie_urls == ["https://res1999.huijiwiki.com/wiki/%E9%A6%96%E9%A1%B5"]
    assert target.exists()


def test_refresh_wrong_account_does_not_modify_existing_target(tmp_path):
    target = tmp_path / "config.dat"
    original = _valid_existing_credential()
    target.write_bytes(original)

    with pytest.raises(AccountMismatchError):
        refresh_credentials(
            FakeBrowserClient(account="Personal User"),
            expected_user="POTATO BOT",
            target=target,
        )

    assert target.read_bytes() == original


def test_refresh_cloudflare_error_does_not_modify_existing_target(tmp_path):
    target = tmp_path / "config.dat"
    original = _valid_existing_credential()
    target.write_bytes(original)

    with pytest.raises(SessionExpiredError):
        refresh_credentials(
            FakeBrowserClient(error=SessionExpiredError("blocked")),
            expected_user="POTATO BOT",
            target=target,
        )

    assert target.read_bytes() == original


def test_refresh_empty_huiji_cookie_set_does_not_modify_existing_target(tmp_path):
    target = tmp_path / "config.dat"
    original = _valid_existing_credential()
    target.write_bytes(original)

    with pytest.raises(CredentialValidationError, match="no Huiji cookies"):
        refresh_credentials(
            FakeBrowserClient(cookies=[{"name": "x", "value": "y", "domain": "example.com"}]),
            expected_user="POTATO BOT",
            target=target,
        )

    assert target.read_bytes() == original


def test_refresh_atomic_replace_failure_preserves_existing_target(tmp_path, monkeypatch):
    target = tmp_path / "config.dat"
    original = _valid_existing_credential()
    target.write_bytes(original)
    monkeypatch.setattr(
        credential_store.os,
        "replace",
        lambda *args: (_ for _ in ()).throw(OSError("simulated replace failure")),
    )

    with pytest.raises(OSError, match="simulated replace failure"):
        refresh_credentials(FakeBrowserClient(), expected_user="POTATO BOT", target=target)

    assert target.read_bytes() == original
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def _write_tool_config(root: Path) -> None:
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "crawler.yaml").write_text(
        "\n".join(
            (
                "schema_version: huiji_crawler_config.v1",
                "site:",
                "  expected_user: POTATO BOT",
                "crawl:",
                "  namespaces: [0]",
                "  include_file_manifest: false",
                "  sleep_seconds: 0",
                "  progress: false",
                "  log_every: 1",
                "  transport: requests",
                "browser:",
                "  headless: false",
                "  verify_account: true",
                "edge:",
                "  port: 9222",
                "",
            )
        ),
        encoding="utf-8",
    )


def test_refresh_cli_defaults_to_edge_and_forces_verified_tool_local_paths(tmp_path, monkeypatch, capsys):
    root = tmp_path / "tool"
    target = root / ".local" / "accounts" / "default" / "credential.json"
    output = root / "eval" / "refresh.v1.json"
    runtime = root / ".local" / "accounts" / "default" / "refresh-runtime-custom"
    root.mkdir()
    _write_tool_config(root)
    client = FakeBrowserClient()
    captured_config = []
    monkeypatch.setattr(
        crawler_cli,
        "create_edge_cdp_browser_client",
        lambda config: captured_config.append(config) or client,
    )

    exit_code = refresh_script.main(
        ["--out", str(runtime), "--output", str(output)],
        tool_root=root,
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert client.closed is True
    assert captured_config[0].transport == "edge"
    assert captured_config[0].browser_verify is True
    assert captured_config[0].out == runtime.resolve()
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == "huiji_credential.v2"
    assert json.loads(output.read_text(encoding="utf-8"))["account"] == "POTATO BOT"
    assert "session-secret" not in output.read_text(encoding="utf-8")


def test_refresh_cli_rejects_external_runtime_path_before_launch(tmp_path, monkeypatch, capsys):
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool_config(root)
    launched = False

    def fail_launch(config):
        nonlocal launched
        launched = True
        raise AssertionError("browser must not launch")

    monkeypatch.setattr(crawler_cli, "create_edge_cdp_browser_client", fail_launch)

    exit_code = refresh_script.main(
        ["--out", str(tmp_path / "outside")],
        tool_root=root,
    )

    captured = capsys.readouterr()
    assert exit_code == 3
    assert launched is False
    assert "inside the tool root" in captured.err


def test_refresh_cli_closes_client_when_account_verification_fails(tmp_path, monkeypatch, capsys):
    root = tmp_path / "tool"
    target = root / ".local" / "accounts" / "default" / "credential.json"
    root.mkdir()
    _write_tool_config(root)
    client = FakeBrowserClient(account="Personal User")
    monkeypatch.setattr(crawler_cli, "create_edge_cdp_browser_client", lambda config: client)

    exit_code = refresh_script.main([], tool_root=root)

    captured = capsys.readouterr()
    assert exit_code == 6
    assert client.closed is True
    assert not target.exists()
    assert "Personal User" in captured.err
    assert "session-secret" not in captured.err
