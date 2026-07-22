from __future__ import annotations

import json
from pathlib import Path

import src.huiji_crawler_tool.cli as cli
import src.huiji_crawler_tool.doctor as doctor_module
from bootstrap.python_runtime import inspect_runtime
from src.huiji_crawler_tool.config import load_crawler_settings
from src.huiji_crawler_tool.discovery import (
    DependencyStatus,
    EdgeCandidate,
    PythonCandidate,
)
from src.huiji_crawler_tool.doctor import RuntimeLockStatus, build_doctor_report
from src.huijiwiki.credential_schema import CanonicalCredential


def _write_tool(root: Path, *, secret: str | None = None, expires: int | None = 1_900_000_000) -> None:
    config = root / "config" / "crawler.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        """schema_version: huiji_crawler_config.v1
site:
  expected_user: POTATO BOT
crawl:
  namespaces: [0]
  include_file_manifest: false
  sleep_seconds: 0
  progress: false
  log_every: 1
  transport: requests
browser:
  headless: false
  verify_account: true
edge:
  port: 9222
""",
        encoding="utf-8",
    )
    if secret is not None:
        credential = root / ".local" / "accounts" / "default" / "credential.json"
        credential.parent.mkdir(parents=True)
        credential.write_bytes(
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
                            "expires": expires,
                            "secure": True,
                            "http_only": True,
                        }
                    ],
                }
            ).to_bytes()
        )


def _runtime(root: Path, *, supported: bool = True):
    return inspect_runtime(
        system="Windows" if supported else "Linux",
        implementation="cpython",
        version=(3, 12, 4),
        machine="AMD64",
        pointer_bits=64,
        executable=root / "python.exe",
    )


def _dependencies() -> tuple[DependencyStatus, ...]:
    return tuple(
        DependencyStatus(name=name, import_name=import_name, version="1.0", status="available")
        for name, import_name in (
            ("playwright", "playwright"),
            ("PyYAML", "yaml"),
            ("requests", "requests"),
        )
    )


def _edge(root: Path) -> tuple[EdgeCandidate, ...]:
    path = root / "external" / "msedge.exe"
    return (EdgeCandidate(source="default_x86", path=path, status="available"),)


def test_doctor_is_offline_redacted_deterministic_and_does_not_create_runtime_paths(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root, secret="private-cookie-value")
    settings = load_crawler_settings(tool_root=root, environ={})
    runtime = _runtime(root)
    python_candidates = (
        PythonCandidate(
            source="path",
            command=(str(root / "python.exe"),),
            status="supported",
            runtime=runtime,
        ),
    )

    first = build_doctor_report(
        settings,
        environ={"UNRELATED_SECRET": "must-not-appear"},
        current_runtime=runtime,
        python_candidates=python_candidates,
        dependency_statuses=_dependencies(),
        edge_candidates=_edge(root),
        lock_status=RuntimeLockStatus(available=True, status="not_created"),
        now=1_800_000_000,
    )
    second = build_doctor_report(
        settings,
        environ={"UNRELATED_SECRET": "must-not-appear"},
        current_runtime=runtime,
        python_candidates=python_candidates,
        dependency_statuses=_dependencies(),
        edge_candidates=_edge(root),
        lock_status=RuntimeLockStatus(available=True, status="not_created"),
        now=1_800_000_000,
    )

    encoded = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert first == second
    assert first["schema_version"] == "huiji_crawler_doctor.v1"
    assert first["status"] == "ok"
    assert first["network_accessed"] is False
    assert first["credential"]["cookie_names"] == ["huiji_session"]
    assert first["credential"]["expiry_status"] == "valid"
    assert first["runtime_lock"]["available"] is True
    assert first["package"]["status"] == "source_checkout"
    assert "private-cookie-value" not in encoded
    assert "must-not-appear" not in encoded
    assert not settings.paths.workspace.exists()
    assert not settings.paths.browser_profile.exists()
    assert not settings.paths.edge_profile.exists()


def test_doctor_reports_python_dependencies_edge_owned_paths_credential_and_lock(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root, secret="secret")
    settings = load_crawler_settings(tool_root=root, environ={})
    report = build_doctor_report(
        settings,
        environ={},
        current_runtime=_runtime(root),
        python_candidates=(),
        dependency_statuses=_dependencies(),
        edge_candidates=_edge(root),
        lock_status=RuntimeLockStatus(available=False, status="held"),
        now=1_800_000_000,
    )

    assert report["status"] == "warning"
    assert report["current_python"]["supported"] is True
    assert [item["name"] for item in report["dependencies"]] == ["playwright", "PyYAML", "requests"]
    assert report["edge"]["selected_source"] == "default_x86"
    assert all(item["status"] == "inside_tool_root" for item in report["owned_paths"])
    assert report["runtime_lock"] == {"available": False, "status": "held"}


def test_credential_status_reports_hash_names_and_expiry_without_values(tmp_path: Path, capsys) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root, secret="credential-secret", expires=1_900_000_000)

    assert cli.main(["credential", "status"], tool_root=root, environ={}) == 0
    output = capsys.readouterr().out
    report = json.loads(output)

    assert len(report["credential"]["sha256"]) == 64
    assert report["credential"]["cookie_names"] == ["huiji_session"]
    assert report["credential"]["cookie_expiries"][0]["expires"] == 1_900_000_000
    assert "credential-secret" not in output


def test_doctor_invalid_environment_returns_exit_8_without_network_or_runtime_creation(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_tool(root)
    unsupported = _runtime(root, supported=False)
    monkeypatch.setattr(doctor_module, "current_runtime_info", lambda: unsupported)
    monkeypatch.setattr(doctor_module, "discover_python_candidates", lambda **kwargs: ())
    monkeypatch.setattr(doctor_module, "inspect_dependencies", _dependencies)
    monkeypatch.setattr(doctor_module, "discover_edge_candidates", lambda **kwargs: _edge(root))
    monkeypatch.setattr(
        doctor_module,
        "probe_runtime_lock",
        lambda path: RuntimeLockStatus(available=True, status="not_created"),
    )
    monkeypatch.setattr(
        "requests.sessions.Session.request",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network must not run")),
    )

    assert cli.main(["doctor"], tool_root=root, environ={}) == 8
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["network_accessed"] is False
    assert not (root / "workspace").exists()
    assert not (root / ".local").exists()
