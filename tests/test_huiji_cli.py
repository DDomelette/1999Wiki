import json
import time
from pathlib import Path

import pytest
import scripts.crawl_huiji_res1999 as crawl_script
import src.huiji_crawler_tool.cli as crawler_cli
from scripts.crawl_huiji_res1999 import build_parser, parse_namespaces_values
from src.huijiwiki.errors import AccountMismatchError, CredentialLoadError, SessionExpiredError
from src.huijiwiki.crawler import CrawlConfig, run_crawl
from src.huijiwiki.project_paths import ProjectPathViolation


def _write_tool_config(root: Path) -> None:
    path = root / "config" / "crawler.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """schema_version: huiji_crawler_config.v1
site:
  expected_user: POTATO BOT
crawl:
  namespaces: [0, 3500, 10, 828, 14]
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


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_userinfo(self):
        return {"query": {"userinfo": {"name": "POTATO BOT"}}}

    def get_siteinfo(self):
        return {"query": {"general": {"sitename": "重返未来1999WIKI"}, "statistics": {"pages": 140334}}}

    def query(self, params):
        self.calls.append(dict(params))
        if params.get("list") == "allpages":
            return {
                "query": {
                    "allpages": [
                        {
                            "pageid": 1,
                            "ns": 0,
                            "title": "槲寄生",
                            "lastrevid": 10,
                            "length": 100,
                            "touched": "2026-07-02T00:00:00Z",
                        }
                    ]
                }
            }
        if params.get("prop") == "revisions":
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "ns": 0,
                            "title": "槲寄生",
                            "revisions": [
                                {
                                    "revid": 10,
                                    "timestamp": "2026-07-02T00:00:00Z",
                                    "slots": {
                                        "main": {
                                            "contentmodel": "wikitext",
                                            "contentformat": "text/x-wiki",
                                            "content": "角色资料",
                                        }
                                    },
                                }
                            ],
                        }
                    ]
                }
            }
        if params.get("list") == "allimages":
            return {
                "query": {
                    "allimages": [
                        {
                            "name": "A.png",
                            "title": "File:A.png",
                            "url": "https://img.example/A.png",
                            "descriptionurl": "https://res1999.huijiwiki.com/wiki/File:A.png",
                            "mime": "image/png",
                            "size": 100,
                            "width": 64,
                            "height": 64,
                            "sha1": "sha-a",
                            "timestamp": "2026-07-02T00:00:00Z",
                        }
                    ]
                }
            }
        raise AssertionError(params)


def test_cli_accepts_comma_or_space_separated_namespaces():
    assert parse_namespaces_values(["0,3500"]) == [0, 3500]
    assert parse_namespaces_values(["0", "3500"]) == [0, 3500]

    parser = build_parser()
    assert parser.parse_args(["--namespaces", "0,3500"]).namespaces == ["0,3500"]
    assert parser.parse_args(["--namespaces", "0", "3500"]).namespaces == ["0", "3500"]
    assert parser.parse_args(["--quiet"]).progress is False
    assert parser.parse_args(["--log-every", "25"]).log_every == 25
    assert "--robot-root" not in parser.format_help()
    assert "robot_root" not in CrawlConfig.__dataclass_fields__


def test_cli_accepts_browser_transport_options(tmp_path):
    parser = build_parser()
    args = parser.parse_args(
        [
            "--transport",
            "browser",
            "--browser-profile",
            str(tmp_path / "profile"),
            "--browser-headless",
            "--no-browser-verify",
        ]
    )

    assert args.transport == "browser"
    assert args.browser_profile == tmp_path / "profile"
    assert args.browser_headless is True
    assert args.browser_verify is False


def test_cli_accepts_edge_transport_options(tmp_path):
    parser = build_parser()
    edge_exe = tmp_path / "msedge.exe"
    args = parser.parse_args(
        [
            "--transport",
            "edge",
            "--edge-profile",
            str(tmp_path / "edge-profile"),
            "--edge-port",
            "9333",
            "--edge-executable",
            str(edge_exe),
            "--no-browser-verify",
        ]
    )

    assert args.transport == "edge"
    assert args.edge_profile == tmp_path / "edge-profile"
    assert args.edge_port == 9333
    assert args.edge_executable == edge_exe
    assert args.browser_verify is False


def test_crawl_config_defaults_to_requests_transport(tmp_path):
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "res1999",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
    )

    assert config.transport == "requests"
    assert config.browser_profile is None
    assert config.browser_headless is False
    assert config.browser_verify is True
    assert config.edge_profile is None
    assert config.edge_port == 9222
    assert config.edge_executable is None


def test_build_default_client_uses_browser_transport(monkeypatch, tmp_path):
    import src.huijiwiki.crawler as crawler

    created = []

    class BrowserClient:
        pass

    def fake_create(config):
        created.append(config)
        return BrowserClient()

    monkeypatch.setattr(crawler, "create_verified_browser_client", fake_create)
    monkeypatch.setattr(
        crawler,
        "load_default_cookies",
        lambda config: (_ for _ in ()).throw(AssertionError("browser must not load Requests cookies")),
    )
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
        transport="browser",
        browser_profile=tmp_path / "profile",
    )

    client = crawler.build_default_client(config)

    assert isinstance(client, BrowserClient)
    assert created == [config]


def test_build_default_client_uses_edge_transport(monkeypatch, tmp_path):
    import src.huijiwiki.crawler as crawler

    created = []

    class EdgeClient:
        pass

    def fake_create(config):
        created.append(config)
        return EdgeClient()

    monkeypatch.setattr(crawler, "create_edge_cdp_browser_client", fake_create)
    monkeypatch.setattr(
        crawler,
        "load_default_cookies",
        lambda config: (_ for _ in ()).throw(AssertionError("edge must not load Requests cookies")),
    )
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
        transport="edge",
        edge_profile=tmp_path / "edge-profile",
    )

    client = crawler.build_default_client(config)

    assert isinstance(client, EdgeClient)
    assert created == [config]


def test_run_crawl_closes_default_client(monkeypatch, tmp_path):
    import src.huijiwiki.crawler as crawler

    class CloseAwareClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.closed = False

        def close(self):
            self.closed = True

    client = CloseAwareClient()
    monkeypatch.setattr(crawler, "build_default_client", lambda config: client)
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
        transport="browser",
    )

    run_crawl(config)

    assert client.closed is True


def test_cli_returns_clear_message_for_session_expiry(monkeypatch, tmp_path, capsys):
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool_config(root)

    def fake_run_crawl(config):
        raise SessionExpiredError("Cloudflare or login session blocked the API response")

    monkeypatch.setattr(crawler_cli, "run_crawl", fake_run_crawl)

    exit_code = crawler_cli.main(
        ["crawl", "--dry-run"],
        tool_root=root,
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Cloudflare" in captured.err
    assert "credential refresh" in captured.err
    assert "GUI tool" not in captured.err
    assert "Traceback" not in captured.err


def test_cli_returns_browser_refresh_message_for_browser_session_expiry(monkeypatch, tmp_path, capsys):
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool_config(root)

    def fake_run_crawl(config):
        raise SessionExpiredError("Cloudflare or login session blocked the browser API response")

    monkeypatch.setattr(crawler_cli, "run_crawl", fake_run_crawl)

    exit_code = crawler_cli.main(
        ["crawl", "--dry-run", "--transport", "browser"],
        tool_root=root,
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "credential refresh" in captured.err
    assert "GUI" not in captured.err


def test_cli_missing_requests_credential_fails_with_local_refresh_guidance(tmp_path, capsys):
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool_config(root)

    exit_code = crawler_cli.main(
        ["crawl", "--dry-run"],
        tool_root=root,
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "credential.json" in captured.err
    assert "credential refresh" in captured.err
    assert "D:\\1999WIKI_ROBOT" not in captured.err
    assert "Traceback" not in captured.err


def test_load_default_cookies_rejects_empty_file_without_exposing_contents(tmp_path):
    config_path = tmp_path / "config.dat"
    config_path.write_text("", encoding="utf-8")
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=config_path,
        out=tmp_path / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
    )

    with pytest.raises(CredentialLoadError, match="Could not load") as excinfo:
        crawl_script.run_crawl(config)

    assert "cookie-value" not in str(excinfo.value)


def test_run_crawl_refuses_non_bot_account_before_siteinfo(tmp_path):
    class PersonalAccountClient(FakeClient):
        def get_userinfo(self):
            return {"query": {"userinfo": {"name": "Personal User"}}}

        def get_siteinfo(self):
            raise AssertionError("siteinfo must not be fetched for the wrong account")

    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "res1999",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
    )

    try:
        run_crawl(config, client=PersonalAccountClient())
    except AccountMismatchError as exc:
        assert "POTATO BOT" in str(exc)
        assert "Personal User" in str(exc)
    else:
        raise AssertionError("Expected AccountMismatchError")


def test_run_crawl_refuses_expired_cloudflare_cookie_before_api_call(tmp_path):
    class ApiMustNotBeCalled:
        def get_userinfo(self):
            raise AssertionError("userinfo must not be fetched with an expired Cloudflare cookie")

    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "res1999",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
        cf_cookie_expires_at=time.time() - 60,
    )

    try:
        run_crawl(config, client=ApiMustNotBeCalled())
    except SessionExpiredError as exc:
        assert "expired" in str(exc)
        assert "refresh_huiji_credentials.py" in str(exc)
        assert "GUI" not in str(exc)
    else:
        raise AssertionError("Expected SessionExpiredError")


def test_run_crawl_writes_expected_outputs_and_resume_skips_unchanged(tmp_path):
    out = tmp_path / "res1999"
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=out,
        namespaces=[0],
        include_file_manifest=True,
        sleep=0.0,
        resume=True,
        dry_run=False,
        limit=None,
        force=False,
    )

    first = run_crawl(config, client=FakeClient())
    second = run_crawl(config, client=FakeClient())

    assert first["fetched_revisions"] == 1
    assert second["fetched_revisions"] == 0
    assert json.loads((out / "siteinfo.json").read_text(encoding="utf-8"))["query"]["statistics"]["pages"] == 140334
    assert (out / "pages.jsonl").exists()
    assert (out / "wikitext.jsonl").exists()
    assert (out / "data_pages.jsonl").exists()
    assert (out / "resources_manifest.jsonl").exists()
    assert (out / "errors.jsonl").exists()
    assert (out / "crawl_state.sqlite").exists()
    assert "角色资料" in (out / "wikitext.jsonl").read_text(encoding="utf-8")
    assert "not_downloaded" in (out / "resources_manifest.jsonl").read_text(encoding="utf-8")


def test_run_crawl_prints_progress_and_cloudflare_cookie_remaining(tmp_path, capsys):
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "res1999",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=False,
        limit=None,
        force=False,
        progress=True,
        log_every=1,
        cf_cookie_expires_at=time.time() + 3600,
    )

    run_crawl(config, client=FakeClient())

    captured = capsys.readouterr()
    assert "preflight: cookies loaded" in captured.err
    assert "Cloudflare cookie" in captured.err
    assert "current:" in captured.err
    assert "槲寄生" in captured.err


def test_run_crawl_quiet_suppresses_progress(tmp_path, capsys):
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=tmp_path / "res1999",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=False,
        limit=None,
        force=False,
        progress=False,
        log_every=1,
        cf_cookie_expires_at=time.time() + 3600,
    )

    run_crawl(config, client=FakeClient())

    captured = capsys.readouterr()
    assert "current:" not in captured.err


def test_dry_run_writes_siteinfo_but_no_revision_content(tmp_path):
    out = tmp_path / "res1999"
    config = CrawlConfig(
        project_root=tmp_path,
        config_path=tmp_path / "config.dat",
        out=out,
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
    )

    summary = run_crawl(config, client=FakeClient())

    assert summary["dry_run"] is True
    assert (out / "siteinfo.json").exists()
    assert not (out / "wikitext.jsonl").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("config_path", Path("outside-config.dat")),
        ("out", Path("outside-out")),
        ("browser_profile", Path("outside-browser")),
        ("edge_profile", Path("outside-edge")),
    ],
)
def test_crawl_config_rejects_project_owned_paths_outside_root(tmp_path, field, value):
    root = tmp_path / "project"
    root.mkdir()
    kwargs = {
        "project_root": root,
        "config_path": root / "config.dat",
        "out": root / "out",
        "namespaces": [0],
        "include_file_manifest": False,
        "sleep": 0.0,
        "resume": True,
        "dry_run": True,
        "limit": None,
        "force": False,
        "browser_profile": None,
        "edge_profile": None,
    }
    kwargs[field] = tmp_path / value

    with pytest.raises(ProjectPathViolation, match=field):
        CrawlConfig(**kwargs)


def test_crawl_config_allows_external_edge_executable_as_system_dependency(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    edge_executable = tmp_path / "system" / "msedge.exe"

    config = CrawlConfig(
        project_root=root,
        config_path=root / "config.dat",
        out=root / "out",
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
        edge_executable=edge_executable,
    )

    assert config.edge_executable == edge_executable


def test_cli_rejects_external_out_before_running_crawler(monkeypatch, tmp_path, capsys):
    root = tmp_path / "project"
    root.mkdir()
    _write_tool_config(root)
    called = False

    def fake_run(config):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(crawler_cli, "run_crawl", fake_run)

    exit_code = crawler_cli.main(
        ["crawl", "--out", str(tmp_path / "outside"), "--dry-run"],
        tool_root=root,
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert called is False
    assert "out" in captured.err
    assert "Traceback" not in captured.err
