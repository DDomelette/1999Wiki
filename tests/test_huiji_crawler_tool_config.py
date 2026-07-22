from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.huiji_crawler_tool.config import load_crawler_settings
from src.huiji_crawler_tool.errors import CrawlerConfigError, ToolPathViolation


def _write_config(root: Path, payload: dict[str, object] | None = None) -> Path:
    config = root / "config" / "crawler.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    data = payload or {
        "schema_version": "huiji_crawler_config.v1",
        "site": {"expected_user": "YAML USER"},
        "crawl": {
            "namespaces": [0, 10],
            "include_file_manifest": False,
            "sleep_seconds": 2.0,
            "progress": True,
            "log_every": 50,
            "transport": "requests",
        },
        "browser": {"headless": False, "verify_account": True},
        "edge": {"port": 9222},
    }
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config


def test_config_priority_is_cli_then_env_then_yaml_then_defaults(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_config(root)

    settings = load_crawler_settings(
        tool_root=root,
        environ={
            "HUIJI_CRAWLER_EXPECTED_USER": "ENV USER",
            "HUIJI_CRAWLER_LOG_EVERY": "25",
            "HUIJI_CRAWLER_TRANSPORT": "edge",
        },
        cli_overrides={"expected_user": "CLI USER", "transport": "browser"},
    )

    assert settings.expected_user == "CLI USER"
    assert settings.transport == "browser"
    assert settings.log_every == 25
    assert settings.namespaces == (0, 10)
    assert settings.include_file_manifest is False


def test_config_uses_built_in_defaults_for_omitted_groups(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_config(root, {"schema_version": "huiji_crawler_config.v1"})

    settings = load_crawler_settings(tool_root=root, environ={})

    assert settings.namespaces == (0, 3500, 10, 828, 14)
    assert settings.sleep == 1.0
    assert settings.expected_user == "POTATO BOT"
    assert settings.transport == "requests"
    assert settings.paths.workspace == root / "workspace" / "default" / "res1999"


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "wrong"},
        {"schema_version": "huiji_crawler_config.v1", "unknown": {}},
        {"schema_version": "huiji_crawler_config.v1", "site": {"cookie": "private"}},
        {"schema_version": "huiji_crawler_config.v1", "crawl": {"progress": "yes"}},
        {"schema_version": "huiji_crawler_config.v1", "edge": {"port": 70000}},
    ],
)
def test_config_rejects_unknown_secret_and_invalid_values(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_config(root, payload)

    with pytest.raises(CrawlerConfigError):
        load_crawler_settings(tool_root=root, environ={})


def test_owned_path_environment_override_cannot_escape(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    _write_config(root)

    with pytest.raises(ToolPathViolation):
        load_crawler_settings(
            tool_root=root,
            environ={"HUIJI_CRAWLER_OUT": str(outside)},
        )

    assert not (root / ".local").exists()
    assert not (root / "workspace").exists()


def test_external_edge_executable_is_allowed_but_must_exist(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    external = tmp_path / "msedge.exe"
    root.mkdir()
    external.write_bytes(b"edge")
    _write_config(root)

    settings = load_crawler_settings(
        tool_root=root,
        environ={"HUIJI_CRAWLER_EDGE_EXECUTABLE": str(external)},
    )

    assert settings.edge_executable == external.resolve()

    with pytest.raises(CrawlerConfigError, match="Edge executable"):
        load_crawler_settings(
            tool_root=root,
            environ={"HUIJI_CRAWLER_EDGE_EXECUTABLE": str(tmp_path / "missing.exe")},
        )


def test_config_error_does_not_create_runtime_directories(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_config(root, {"schema_version": "huiji_crawler_config.v1", "crawl": {"sleep_seconds": -1}})

    with pytest.raises(CrawlerConfigError):
        load_crawler_settings(tool_root=root, environ={})

    assert not (root / ".local").exists()
    assert not (root / "workspace").exists()

