from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from src.huiji_crawler_tool.errors import ToolPathViolation
from src.huiji_crawler_tool.runtime_paths import ToolPaths, resolve_owned_path


def _make_directory_link(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            pytest.skip("Windows symlink and junction creation are unavailable")


def test_tool_paths_are_root_relative_and_fixed(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()

    paths = ToolPaths.from_root(root)

    assert paths.root == root.resolve()
    assert paths.settings_file == root / "config" / "crawler.yaml"
    assert paths.credential_file == root / ".local" / "accounts" / "default" / "credential.json"
    assert paths.workspace == root / "workspace" / "default" / "res1999"
    assert paths.browser_profile == root / ".local" / "accounts" / "default" / "browser-profile"
    assert paths.edge_profile == root / ".local" / "accounts" / "default" / "edge-profile"
    assert paths.refresh_runtime == root / ".local" / "accounts" / "default" / "refresh-runtime"
    assert paths.lock_file == root / ".local" / "locks" / "default.lock"


@pytest.mark.parametrize(
    "value",
    [
        Path("..") / "outside",
        Path("nested") / ".." / ".." / "outside",
    ],
)
def test_owned_path_rejects_parent_escape(tmp_path: Path, value: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()

    with pytest.raises(ToolPathViolation, match="inside the tool root"):
        resolve_owned_path(value, root=root, label="output")


def test_owned_path_rejects_external_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    with pytest.raises(ToolPathViolation, match="inside the tool root"):
        resolve_owned_path(outside, root=root, label="output")


def test_owned_path_rejects_symlink_or_junction_escape(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "linked"
    _make_directory_link(link, outside)

    with pytest.raises(ToolPathViolation, match="inside the tool root"):
        resolve_owned_path(link / "result", root=root, label="output")


def test_owned_path_allows_existing_file_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    target = root / "config" / "crawler.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("schema_version: huiji_crawler_config.v1\n", encoding="utf-8")

    resolved = resolve_owned_path(target, root=root, label="settings", must_exist=True)

    assert resolved == target.resolve()

