#!/usr/bin/env python3
"""Enforce the public-read-only permission contract for the RAG closure."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path


DIRECTORY_MODE = 0o755
FILE_MODE = 0o644


class PermissionContractError(ValueError):
    pass


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _checked_entry(path: Path, *, expect_directory: bool | None = None) -> os.stat_result:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise PermissionContractError(f"cannot inspect closure path: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise PermissionContractError(f"closure path is a forbidden symlink: {path}")
    if expect_directory is True and not stat.S_ISDIR(info.st_mode):
        raise PermissionContractError(f"closure root is not a directory: {path}")
    if expect_directory is False and not stat.S_ISREG(info.st_mode):
        raise PermissionContractError(f"closure entry is not a regular file: {path}")
    return info


def _closure_entries(root: Path) -> tuple[list[Path], list[Path]]:
    root = _absolute(root)
    _checked_entry(root, expect_directory=True)
    directories = [root]
    files: list[Path] = []
    for current, names, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in names:
            child = current_path / name
            _checked_entry(child, expect_directory=True)
            directories.append(child)
        for name in filenames:
            child = current_path / name
            _checked_entry(child, expect_directory=False)
            files.append(child)
    return directories, files


def enforce(root: Path, *, check_only: bool) -> tuple[int, int]:
    directories, files = _closure_entries(root)
    expected = (
        *((path, DIRECTORY_MODE) for path in directories),
        *((path, FILE_MODE) for path in files),
    )
    for path, mode in expected:
        actual = stat.S_IMODE(os.lstat(path).st_mode)
        if check_only:
            if actual != mode:
                raise PermissionContractError(
                    f"closure permission mismatch at {path}: "
                    f"expected {mode:04o}, got {actual:04o}"
                )
        else:
            os.chmod(path, mode, follow_symlinks=False)
    if not check_only:
        directories, files = _closure_entries(root)
        for path in directories:
            if stat.S_IMODE(os.lstat(path).st_mode) != DIRECTORY_MODE:
                raise PermissionContractError(f"failed to set directory mode: {path}")
        for path in files:
            if stat.S_IMODE(os.lstat(path).st_mode) != FILE_MODE:
                raise PermissionContractError(f"failed to set file mode: {path}")
    return len(directories), len(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        directory_count, file_count = enforce(args.root, check_only=args.check)
    except (OSError, PermissionContractError) as exc:
        print(f"prepare-rag-permissions: {exc}", file=sys.stderr)
        return 1
    action = "verified" if args.check else "prepared"
    print(
        f"{action} RAG permissions: "
        f"{directory_count} directories mode 0755, {file_count} files mode 0644"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
