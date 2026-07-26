#!/usr/bin/env python3
"""Enforce the public-read-only permission contract for the RAG closure."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import json
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterator


DIRECTORY_MODE = 0o755
EXPECTED_FILE_COUNT = 11
EXPECTED_TOTAL_BYTES = 222_789_868
FILE_MODE = 0o644


class PermissionContractError(ValueError):
    pass


FingerprintEntry = tuple[str, str, int, int, int, int, int, int]


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _relative_parts(value: str) -> tuple[str, ...]:
    if not value or "\\" in value or "\x00" in value:
        raise PermissionContractError(
            "closure verifier returned a noncanonical path"
        )
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise PermissionContractError(
            "closure verifier returned a noncanonical path"
        )
    return relative.parts


def _expected_components(relative_files: list[str]) -> dict[str, str]:
    components = {".": "directory"}
    for value in relative_files:
        parts = _relative_parts(value)
        for index in range(len(parts)):
            path = PurePosixPath(*parts[: index + 1]).as_posix()
            kind = "file" if index == len(parts) - 1 else "directory"
            existing = components.get(path)
            if existing is not None and existing != kind:
                raise PermissionContractError(
                    "closure verifier returned conflicting path metadata"
                )
            components[path] = kind
    return components


def _verified_entries(
    root: Path,
) -> tuple[Path, list[str], dict[str, FingerprintEntry]]:
    root = _absolute(root)
    verifier = Path(__file__).with_name("verify-rag-closure.py")
    result = subprocess.run(
        [
            sys.executable,
            os.fspath(verifier),
            "--root",
            os.fspath(root),
            "--metadata-json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PermissionContractError(
            f"closure verification failed with status {result.returncode}"
        )
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PermissionContractError(
            "closure verifier returned invalid metadata"
        ) from exc
    if (
        not isinstance(metadata, dict)
        or metadata.get("count") != EXPECTED_FILE_COUNT
        or metadata.get("total_bytes") != EXPECTED_TOTAL_BYTES
    ):
        raise PermissionContractError(
            "verified closure is not the approved "
            f"{EXPECTED_FILE_COUNT}-file/{EXPECTED_TOTAL_BYTES}-byte set"
        )
    relative_files = metadata.get("files")
    if (
        not isinstance(relative_files, list)
        or len(relative_files) != EXPECTED_FILE_COUNT
        or not all(isinstance(value, str) for value in relative_files)
        or len(set(relative_files)) != EXPECTED_FILE_COUNT
    ):
        raise PermissionContractError(
            "closure verifier returned invalid file metadata"
        )

    expected_components = _expected_components(relative_files)
    raw_fingerprint = metadata.get("fingerprint")
    if (
        not isinstance(raw_fingerprint, list)
        or len(raw_fingerprint) != len(expected_components)
    ):
        raise PermissionContractError(
            "closure verifier returned invalid fingerprint metadata"
        )
    fingerprint: dict[str, FingerprintEntry] = {}
    for raw_entry in raw_fingerprint:
        if (
            not isinstance(raw_entry, list)
            or len(raw_entry) != 8
            or not isinstance(raw_entry[0], str)
            or not isinstance(raw_entry[1], str)
            or any(type(value) is not int for value in raw_entry[2:])
        ):
            raise PermissionContractError(
                "closure verifier returned invalid fingerprint metadata"
            )
        path = raw_entry[0]
        kind = raw_entry[1]
        if path != ".":
            _relative_parts(path)
        if path in fingerprint or expected_components.get(path) != kind:
            raise PermissionContractError(
                "closure verifier returned invalid fingerprint metadata"
            )
        fingerprint[path] = tuple(raw_entry)  # type: ignore[assignment]
    if set(fingerprint) != set(expected_components):
        raise PermissionContractError(
            "closure verifier returned incomplete fingerprint metadata"
        )
    return root, sorted(relative_files), fingerprint


def _require_linux_fd_primitives() -> tuple[int, int]:
    supports_dir_fd = getattr(os, "supports_dir_fd", ())
    if (
        sys.platform != "linux"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "fchmod")
        or os.open not in supports_dir_fd
    ):
        raise PermissionContractError(
            "required Linux no-follow descriptor primitives are unavailable"
        )
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | close_on_exec
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | close_on_exec
    return directory_flags, file_flags


def _compare_fingerprint(
    fd: int,
    entry: FingerprintEntry,
) -> None:
    path, kind, *expected_signature = entry
    try:
        info = os.fstat(fd)
    except OSError as exc:
        raise PermissionContractError(
            f"cannot inspect opened closure component: {path}"
        ) from exc
    if (
        kind == "directory"
        and not stat.S_ISDIR(info.st_mode)
    ) or (
        kind == "file"
        and not stat.S_ISREG(info.st_mode)
    ):
        raise PermissionContractError(
            f"opened closure component has the wrong type: {path}"
        )
    actual_signature = (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )
    if actual_signature != tuple(expected_signature):
        raise PermissionContractError(
            f"opened closure component changed after verification: {path}"
        )


@contextmanager
def _opened_verified_entries(
    root: Path,
    fingerprint: dict[str, FingerprintEntry],
) -> Iterator[dict[str, int]]:
    directory_flags, file_flags = _require_linux_fd_primitives()
    with ExitStack() as stack:
        try:
            root_fd = os.open(root, directory_flags)
        except OSError as exc:
            raise PermissionContractError(
                "cannot open verified closure root without following links"
            ) from exc
        stack.callback(os.close, root_fd)
        opened = {".": root_fd}
        _compare_fingerprint(root_fd, fingerprint["."])
        ordered_paths = sorted(
            (path for path in fingerprint if path != "."),
            key=lambda path: (len(PurePosixPath(path).parts), path),
        )
        for path in ordered_paths:
            relative = PurePosixPath(path)
            parent = relative.parent.as_posix()
            if parent == ".":
                parent = "."
            flags = (
                directory_flags
                if fingerprint[path][1] == "directory"
                else file_flags
            )
            try:
                fd = os.open(relative.name, flags, dir_fd=opened[parent])
            except OSError as exc:
                raise PermissionContractError(
                    f"cannot open verified closure component without "
                    f"following links: {path}"
                ) from exc
            stack.callback(os.close, fd)
            opened[path] = fd
            _compare_fingerprint(fd, fingerprint[path])
        yield opened


def _expected_mode(kind: str) -> int:
    return DIRECTORY_MODE if kind == "directory" else FILE_MODE


def _check_open_modes(
    opened: dict[str, int],
    fingerprint: dict[str, FingerprintEntry],
) -> None:
    for path, entry in fingerprint.items():
        expected_mode = _expected_mode(entry[1])
        actual_mode = stat.S_IMODE(os.fstat(opened[path]).st_mode)
        if actual_mode != expected_mode:
            raise PermissionContractError(
                f"closure permission mismatch at {path}: "
                f"expected {expected_mode:04o}, got {actual_mode:04o}"
            )


def _check_post_verification_modes(
    fingerprint: dict[str, FingerprintEntry],
) -> None:
    for path, entry in fingerprint.items():
        expected_mode = _expected_mode(entry[1])
        actual_mode = stat.S_IMODE(entry[4])
        if actual_mode != expected_mode:
            raise PermissionContractError(
                f"failed to set {entry[1]} mode: {path}"
            )


def _verify_opened_namespace(
    root: Path,
    files: list[str],
    fingerprint: dict[str, FingerprintEntry],
    opened: dict[str, int],
) -> None:
    _, post_files, post_fingerprint = _verified_entries(root)
    if (
        post_files != files
        or set(post_fingerprint) != set(fingerprint)
    ):
        raise PermissionContractError(
            "verified closure changed after permission preparation"
        )
    for path in sorted(post_fingerprint):
        _compare_fingerprint(opened[path], post_fingerprint[path])
    _check_post_verification_modes(post_fingerprint)


def enforce(root: Path, *, check_only: bool) -> tuple[int, int]:
    root, files, fingerprint = _verified_entries(root)
    with _opened_verified_entries(root, fingerprint) as opened:
        if check_only:
            _check_open_modes(opened, fingerprint)
        else:
            ordered = sorted(
                fingerprint,
                key=lambda path: (
                    fingerprint[path][1] == "file",
                    path,
                ),
            )
            for path in ordered:
                os.fchmod(
                    opened[path],
                    _expected_mode(fingerprint[path][1]),
                )
            _check_open_modes(opened, fingerprint)
        _verify_opened_namespace(root, files, fingerprint, opened)
    directory_count = sum(
        entry[1] == "directory" for entry in fingerprint.values()
    )
    return directory_count, len(files)


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
