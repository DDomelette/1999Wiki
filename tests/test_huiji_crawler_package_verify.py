from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from bootstrap.package_verify import PackageVerificationError, verify_package


CRITICAL_PATHS = (
    "huiji-crawler.cmd",
    "bootstrap/package_verify.py",
    "src/huiji_crawler_tool/cli.py",
    "config/crawler.yaml",
    "requirements-crawler.lock.txt",
)


def _write_package(root: Path, *, extra_paths: tuple[str, ...] = ("README.md",)) -> dict[str, object]:
    records = []
    for relative in (*CRITICAL_PATHS, *extra_paths):
        path = root / Path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"payload:{relative}\n".encode()
        path.write_bytes(payload)
        records.append(
            {
                "path": relative,
                "role": "runtime_source",
                "critical": relative in CRITICAL_PATHS,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "huiji_crawler_package_manifest.v1",
        "target": {"os": "windows", "arch": "x64", "python": ">=3.12.0,<3.13"},
        "mutable_prefixes": [".local/", ".venv/", "workspace/"],
        "files": records,
    }
    encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "package-manifest.v1.json").write_bytes(encoded)
    (root / "package-manifest.v1.sha256").write_text(
        hashlib.sha256(encoded).hexdigest() + "  package-manifest.v1.json\n",
        encoding="ascii",
    )
    return manifest


def test_package_verifier_accepts_valid_manifest_and_detached_hash(tmp_path: Path) -> None:
    root = tmp_path / "package"
    root.mkdir()
    _write_package(root)

    report = verify_package(root)
    critical = verify_package(root, critical_only=True)

    assert report["status"] == "passed"
    assert report["verified_file_count"] == len(CRITICAL_PATHS) + 1
    assert critical["mode"] == "critical"
    assert critical["verified_file_count"] == len(CRITICAL_PATHS)


@pytest.mark.parametrize("mutation", ["tamper", "extra", "detached_hash"])
def test_package_verifier_rejects_tamper_extra_and_detached_hash(
    tmp_path: Path,
    mutation: str,
) -> None:
    root = tmp_path / "package"
    root.mkdir()
    _write_package(root)
    if mutation == "tamper":
        (root / "README.md").write_text("tampered", encoding="utf-8")
    elif mutation == "extra":
        (root / "unexpected.txt").write_text("extra", encoding="utf-8")
    else:
        (root / "package-manifest.v1.sha256").write_text("0" * 64 + "\n", encoding="ascii")

    with pytest.raises(PackageVerificationError):
        verify_package(root)


@pytest.mark.parametrize(
    "bad_paths",
    [
        ["README.md", "README.md"],
        ["Readme.md", "README.md"],
        ["../outside.txt"],
        ["C:/outside.txt"],
    ],
)
def test_package_verifier_rejects_duplicate_case_collision_and_unsafe_paths(
    tmp_path: Path,
    bad_paths: list[str],
) -> None:
    root = tmp_path / "package"
    root.mkdir()
    manifest = _write_package(root)
    template = dict(manifest["files"][-1])
    manifest["files"] = list(manifest["files"][:-1]) + [dict(template, path=path) for path in bad_paths]
    encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "package-manifest.v1.json").write_bytes(encoded)
    (root / "package-manifest.v1.sha256").write_text(hashlib.sha256(encoded).hexdigest(), encoding="ascii")

    with pytest.raises(PackageVerificationError):
        verify_package(root)


def test_package_verifier_ignores_only_exact_mutable_prefixes(tmp_path: Path) -> None:
    root = tmp_path / "package"
    root.mkdir()
    _write_package(root)
    for relative in (
        ".venv/Lib/private.py",
        ".local/accounts/default/credential.json",
        "workspace/default/res1999/siteinfo.json",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("mutable", encoding="utf-8")

    assert verify_package(root)["status"] == "passed"
    (root / ".venv-copy.txt").write_text("not mutable", encoding="utf-8")
    with pytest.raises(PackageVerificationError, match="extra"):
        verify_package(root)


def test_package_verifier_rejects_symlink_or_junction_escape(tmp_path: Path) -> None:
    root = tmp_path / "package"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    _write_package(root)
    (outside / "payload.txt").write_text("outside", encoding="utf-8")
    link = root / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        environment = dict(os.environ)
        environment["HUIJI_TEST_LINK"] = str(link)
        environment["HUIJI_TEST_TARGET"] = str(outside)
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "New-Item -ItemType Junction -Path $env:HUIJI_TEST_LINK -Target $env:HUIJI_TEST_TARGET | Out-Null",
            ],
            capture_output=True,
            env=environment,
            text=True,
        )
        if completed.returncode != 0:
            pytest.skip("symlink and junction creation are unavailable")

    with pytest.raises(PackageVerificationError, match="escape"):
        verify_package(root)
