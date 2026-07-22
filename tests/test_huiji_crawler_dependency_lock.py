from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from src.huiji_crawler_packaging.dependency_lock import (
    DependencyLockError,
    generate_dependency_lock,
    inspect_wheelhouse,
    validate_lock,
)


def write_wheel(
    wheelhouse: Path,
    name: str,
    version: str,
    *,
    requires: tuple[str, ...] = (),
    tag: str = "py3-none-any",
) -> Path:
    normalized = name.replace("-", "_")
    filename = f"{normalized}-{version}-{tag}.whl"
    path = wheelhouse / filename
    dist_info = f"{normalized}-{version}.dist-info"
    metadata = [
        "Metadata-Version: 2.3",
        f"Name: {name}",
        f"Version: {version}",
        "License-Expression: MIT",
        *(f"Requires-Dist: {item}" for item in requires),
        "",
    ]
    wheelhouse.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{dist_info}/METADATA", "\n".join(metadata))
        archive.writestr(f"{dist_info}/WHEEL", f"Wheel-Version: 1.0\nTag: {tag}\n")
        archive.writestr(f"{dist_info}/licenses/LICENSE", "MIT license text\n")
    return path


def test_lock_contains_complete_win_amd64_cp312_binary_graph_with_hashes(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheels"
    direct = write_wheel(wheelhouse, "Alpha", "1.0", requires=("Beta>=2",))
    dependency = write_wheel(wheelhouse, "Beta", "2.1")
    requirements = tmp_path / "requirements.in"
    requirements.write_text("Alpha==1.0\n", encoding="utf-8")

    lock = inspect_wheelhouse(requirements, wheelhouse, python_version="3.12", platform="win_amd64")

    assert [record.name for record in lock.records] == ["alpha", "beta"]
    assert f"sha256:{hashlib.sha256(direct.read_bytes()).hexdigest()}" in lock.text
    assert f"sha256:{hashlib.sha256(dependency.read_bytes()).hexdigest()}" in lock.text
    assert lock.text.splitlines() == sorted(lock.text.splitlines(), key=str.casefold)


def test_lock_generation_is_sorted_reproducible_and_validatable(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheels"
    write_wheel(wheelhouse, "Zulu", "1.0")
    write_wheel(wheelhouse, "Alpha", "2.0")
    requirements = tmp_path / "requirements.in"
    requirements.write_text("Zulu==1.0\nAlpha==2.0\n", encoding="utf-8")
    first = tmp_path / "first.lock"
    second = tmp_path / "second.lock"

    generate_dependency_lock(requirements, first, wheelhouse)
    generate_dependency_lock(requirements, second, wheelhouse)

    assert first.read_bytes() == second.read_bytes()
    assert validate_lock(first, requirements, wheelhouse).text == first.read_text(encoding="utf-8")


def test_lock_rejects_missing_transitive_or_wrong_target_wheel(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheels"
    write_wheel(wheelhouse, "Alpha", "1.0", requires=("Missing>=1",))
    requirements = tmp_path / "requirements.in"
    requirements.write_text("Alpha==1.0\n", encoding="utf-8")

    with pytest.raises(DependencyLockError, match="missing"):
        inspect_wheelhouse(requirements, wheelhouse)

    (wheelhouse / "Alpha-1.0-py3-none-any.whl").unlink()
    write_wheel(wheelhouse, "Alpha", "1.0", tag="cp311-cp311-win_amd64")
    with pytest.raises(DependencyLockError, match="target"):
        inspect_wheelhouse(requirements, wheelhouse)


def test_repository_direct_dependency_input_is_exact_and_unpolluted() -> None:
    root = Path(__file__).resolve().parents[1]
    lines = (root / "packaging" / "huiji-crawler" / "requirements-crawler.in").read_text(
        encoding="utf-8"
    ).splitlines()

    assert lines == ["playwright==1.61.0", "PyYAML==6.0.3", "requests==2.34.2"]
