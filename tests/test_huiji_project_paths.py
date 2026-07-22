from __future__ import annotations

from pathlib import Path

import pytest

from src.huijiwiki.project_paths import ProjectPathViolation, resolve_project_local_path


def test_private_browser_profile_names_are_git_ignored():
    project_root = Path(__file__).resolve().parents[1]
    patterns = {
        line.strip()
        for line in (project_root / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ".local/" in patterns
    assert "**/browser_profile/" in patterns
    assert "**/edge_profile/" in patterns


def test_resolve_project_local_path_accepts_project_relative_path(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()

    resolved = resolve_project_local_path(
        ".local/huiji/credentials/config.dat",
        project_root=root,
        label="credential_file",
    )

    assert resolved == (root / ".local/huiji/credentials/config.dat").resolve()


def test_resolve_project_local_path_accepts_absolute_path_inside_project(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    candidate = root / "data" / "huiji"

    resolved = resolve_project_local_path(
        candidate,
        project_root=root,
        label="raw_root",
    )

    assert resolved == candidate.resolve()


def test_resolve_project_local_path_rejects_external_absolute_path(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(ProjectPathViolation, match="credential_file"):
        resolve_project_local_path(
            tmp_path / "outside" / "config.dat",
            project_root=root,
            label="credential_file",
        )


def test_resolve_project_local_path_rejects_parent_traversal(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(ProjectPathViolation, match="processed_root"):
        resolve_project_local_path(
            "../outside",
            project_root=root,
            label="processed_root",
        )


def test_resolve_project_local_path_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(ProjectPathViolation, match="browser_profile"):
        resolve_project_local_path(
            link / "profile",
            project_root=root,
            label="browser_profile",
        )


def test_resolve_project_local_path_honors_must_exist(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(FileNotFoundError):
        resolve_project_local_path(
            "missing.dat",
            project_root=root,
            label="credential_file",
            must_exist=True,
        )
