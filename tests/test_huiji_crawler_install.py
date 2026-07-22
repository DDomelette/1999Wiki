from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bootstrap.install import INSTALL_MARKER, InstallError, check_install_marker, install_package
from bootstrap.python_runtime import inspect_runtime


def _runtime(root: Path, *, system: str = "Windows", version=(3, 12, 4), bits: int = 64, implementation="cpython"):
    return inspect_runtime(
        system=system,
        implementation=implementation,
        version=version,
        machine="AMD64",
        pointer_bits=bits,
        executable=root / "system-python.exe",
    )


def _package_inputs(root: Path) -> None:
    lock = root / "requirements-crawler.lock.txt"
    manifest = root / "package-manifest.v1.json"
    lock.write_text("requests==2.34.2 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    manifest.write_text('{"schema_version":"huiji_crawler_package_manifest.v1"}\n', encoding="utf-8")
    (root / "package-manifest.v1.sha256").write_text(
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        encoding="ascii",
    )


@pytest.mark.parametrize(
    "runtime",
    [
        ("Linux", (3, 12, 4), 64, "cpython"),
        ("Windows", (3, 11, 9), 64, "cpython"),
        ("Windows", (3, 13, 0), 64, "cpython"),
        ("Windows", (3, 12, 4), 32, "cpython"),
        ("Windows", (3, 12, 4), 64, "pypy"),
    ],
)
def test_install_rejects_non_windows_non_cpython_non_312_or_32_bit(
    tmp_path: Path,
    runtime: tuple[str, tuple[int, int, int], int, str],
) -> None:
    root = tmp_path / "package"
    root.mkdir()
    _package_inputs(root)
    system, version, bits, implementation = runtime

    with pytest.raises(InstallError, match="Windows x64 CPython"):
        install_package(
            root,
            runtime=_runtime(root, system=system, version=version, bits=bits, implementation=implementation),
            verify_fn=lambda *args, **kwargs: {"status": "passed"},
            run_fn=lambda *args, **kwargs: None,
        )


def test_install_uses_require_hashes_only_binary_and_tool_local_venv(tmp_path: Path) -> None:
    root = tmp_path / "package with spaces"
    root.mkdir()
    _package_inputs(root)
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append([str(item) for item in command])
        if command[1:3] == ["-m", "venv"]:
            python = root / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"")
        return subprocess.CompletedProcess(command, 0, "", "")

    report = install_package(
        root,
        runtime=_runtime(root),
        verify_fn=lambda *args, **kwargs: {"status": "passed"},
        run_fn=run,
    )

    pip = next(command for command in commands if "pip" in command)
    assert "--require-hashes" in pip
    assert "--only-binary=:all:" in pip
    assert str(root / "requirements-crawler.lock.txt") in pip
    assert commands[0][-1] == str(root / ".venv")
    marker = root / ".venv" / INSTALL_MARKER
    encoded = marker.read_text(encoding="utf-8")
    assert report["status"] == "installed"
    assert str(root) not in encoded
    assert check_install_marker(root, runtime=_runtime(root))["status"] == "valid"


def test_install_failure_leaves_no_success_marker(tmp_path: Path) -> None:
    root = tmp_path / "package"
    root.mkdir()
    _package_inputs(root)

    def run(command, **kwargs):
        if command[1:3] == ["-m", "venv"]:
            python = root / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"")
            return subprocess.CompletedProcess(command, 0, "", "")
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(InstallError):
        install_package(
            root,
            runtime=_runtime(root),
            verify_fn=lambda *args, **kwargs: {"status": "passed"},
            run_fn=run,
        )

    assert not (root / ".venv" / INSTALL_MARKER).exists()
