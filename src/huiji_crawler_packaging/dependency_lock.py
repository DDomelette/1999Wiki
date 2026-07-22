from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.requirements import Requirement
from packaging.tags import Tag
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


class DependencyLockError(RuntimeError):
    """Raised when the target wheel graph or hash lock is incomplete."""


@dataclass(frozen=True)
class WheelRecord:
    name: str
    version: str
    filename: str
    path: Path
    sha256: str
    requires: tuple[str, ...]
    license_expression: str | None
    license_files: tuple[str, ...]

    @property
    def lock_line(self) -> str:
        return f"{self.name}=={self.version} --hash=sha256:{self.sha256}"


@dataclass(frozen=True)
class DependencyLock:
    records: tuple[WheelRecord, ...]
    text: str


_LOCK_LINE = re.compile(
    r"^(?P<name>[a-z0-9][a-z0-9._-]*)==(?P<version>[^\s]+) --hash=sha256:(?P<hash>[0-9a-f]{64})$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _direct_requirements(path: Path) -> tuple[Requirement, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise DependencyLockError("Cannot read direct dependency input") from exc
    requirements: list[Requirement] = []
    seen: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            requirement = Requirement(line)
        except Exception as exc:
            raise DependencyLockError(f"Invalid direct dependency: {line}") from exc
        specifiers = list(requirement.specifier)
        if (
            requirement.url is not None
            or requirement.extras
            or requirement.marker is not None
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            raise DependencyLockError(f"Direct dependency must use one exact pin: {line}")
        name = canonicalize_name(requirement.name)
        if name in seen:
            raise DependencyLockError(f"Duplicate direct dependency: {name}")
        seen.add(name)
        requirements.append(requirement)
    if not requirements:
        raise DependencyLockError("Direct dependency input is empty")
    return tuple(requirements)


def _target_environment(python_version: str, platform: str) -> dict[str, str]:
    major, minor = python_version.split(".", 1)
    return {
        "implementation_name": "cpython",
        "implementation_version": f"{major}.{minor}.0",
        "os_name": "nt",
        "platform_machine": "AMD64",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": "Windows",
        "platform_version": "",
        "python_full_version": f"{major}.{minor}.0",
        "python_version": f"{major}.{minor}",
        "sys_platform": "win32",
        "extra": "",
        "target_platform": platform,
    }


def _tag_matches(tag: Tag, *, python_version: str, platform: str) -> bool:
    target_cp = "cp" + python_version.replace(".", "")
    platform_ok = tag.platform in {"any", platform}
    if not platform_ok:
        return False
    if tag.interpreter in {"py3", "py2.py3", target_cp}:
        return tag.abi in {"none", target_cp, "abi3"}
    if tag.abi == "abi3" and tag.interpreter.startswith("cp3"):
        try:
            return int(tag.interpreter[2:]) <= int(target_cp[2:])
        except ValueError:
            return False
    return False


def _read_wheel(path: Path, *, python_version: str, platform: str) -> WheelRecord:
    try:
        parsed_name, parsed_version, _build, tags = parse_wheel_filename(path.name)
    except Exception as exc:
        raise DependencyLockError(f"Invalid wheel filename: {path.name}") from exc
    if not any(_tag_matches(tag, python_version=python_version, platform=platform) for tag in tags):
        raise DependencyLockError(f"Wheel does not match target {python_version}/{platform}: {path.name}")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise DependencyLockError(f"Wheel must contain one METADATA file: {path.name}")
            metadata = BytesParser(policy=email_policy).parsebytes(archive.read(metadata_names[0]))
            license_files = tuple(
                sorted(
                    name
                    for name in names
                    if ".dist-info/licenses/" in name.casefold()
                    and not name.endswith("/")
                    and ".." not in PurePosixPath(name).parts
                )
            )
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise DependencyLockError(f"Cannot inspect wheel: {path.name}") from exc
    metadata_name = canonicalize_name(str(metadata.get("Name", "")))
    metadata_version = str(metadata.get("Version", ""))
    if metadata_name != canonicalize_name(str(parsed_name)) or Version(metadata_version) != parsed_version:
        raise DependencyLockError(f"Wheel filename and METADATA disagree: {path.name}")
    expression = metadata.get("License-Expression") or metadata.get("License")
    return WheelRecord(
        name=metadata_name,
        version=str(parsed_version),
        filename=path.name,
        path=path.resolve(strict=True),
        sha256=_sha256(path),
        requires=tuple(sorted(metadata.get_all("Requires-Dist", []), key=str.casefold)),
        license_expression=None if not expression else str(expression).strip(),
        license_files=license_files,
    )


def inspect_wheelhouse(
    requirements_input: Path,
    wheelhouse: Path,
    *,
    python_version: str = "3.12",
    platform: str = "win_amd64",
) -> DependencyLock:
    direct = _direct_requirements(Path(requirements_input))
    root = Path(wheelhouse).expanduser().resolve(strict=True)
    wheel_paths = sorted(root.glob("*.whl"), key=lambda item: item.name.casefold())
    if not wheel_paths:
        raise DependencyLockError("Wheelhouse contains no wheels")
    unexpected = sorted(path.name for path in root.iterdir() if path.is_file() and path.suffix.casefold() != ".whl")
    if unexpected:
        raise DependencyLockError(f"Wheelhouse contains non-wheel artifact: {unexpected[0]}")
    records = tuple(
        sorted(
            (_read_wheel(path, python_version=python_version, platform=platform) for path in wheel_paths),
            key=lambda item: item.name,
        )
    )
    by_name: dict[str, WheelRecord] = {}
    for record in records:
        if record.name in by_name:
            raise DependencyLockError(f"Wheelhouse contains duplicate distribution: {record.name}")
        by_name[record.name] = record

    environment = _target_environment(python_version, platform)
    queue: deque[str] = deque()
    reachable: set[str] = set()
    for requirement in direct:
        name = canonicalize_name(requirement.name)
        record = by_name.get(name)
        if record is None or Version(record.version) not in requirement.specifier:
            raise DependencyLockError(f"Wheelhouse is missing direct dependency: {name}")
        queue.append(name)
    while queue:
        name = queue.popleft()
        if name in reachable:
            continue
        reachable.add(name)
        for raw_requirement in by_name[name].requires:
            try:
                requirement = Requirement(raw_requirement)
            except Exception as exc:
                raise DependencyLockError(f"Invalid wheel dependency metadata in {name}") from exc
            if requirement.marker is not None and not requirement.marker.evaluate(environment):
                continue
            dependency_name = canonicalize_name(requirement.name)
            dependency = by_name.get(dependency_name)
            if dependency is None:
                raise DependencyLockError(f"Wheel graph is missing dependency: {dependency_name}")
            if requirement.specifier and Version(dependency.version) not in requirement.specifier:
                raise DependencyLockError(f"Wheel dependency version mismatch: {dependency_name}")
            queue.append(dependency_name)
    extras = sorted(set(by_name) - reachable)
    if extras:
        raise DependencyLockError(f"Wheelhouse contains unreachable dependency: {extras[0]}")
    selected = tuple(by_name[name] for name in sorted(reachable))
    text = "\n".join(record.lock_line for record in selected) + "\n"
    return DependencyLock(records=selected, text=text)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def generate_dependency_lock(
    requirements_input: Path,
    output: Path,
    wheelhouse: Path,
    *,
    python_version: str = "3.12",
    platform: str = "win_amd64",
    run_fn: Callable[..., Any] = subprocess.run,
) -> DependencyLock:
    wheelhouse_path = Path(wheelhouse).expanduser().resolve(strict=False)
    wheelhouse_path.mkdir(parents=True, exist_ok=True)
    if not any(wheelhouse_path.glob("*.whl")):
        abi = "cp" + python_version.replace(".", "")
        try:
            run_fn(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "--implementation",
                    "cp",
                    "--python-version",
                    python_version,
                    "--abi",
                    abi,
                    "--platform",
                    platform,
                    "--dest",
                    str(wheelhouse_path),
                    "--requirement",
                    str(Path(requirements_input).resolve(strict=True)),
                ],
                check=True,
            )
        except Exception as exc:
            raise DependencyLockError(f"Target wheel download failed ({type(exc).__name__})") from exc
    lock = inspect_wheelhouse(
        requirements_input,
        wheelhouse_path,
        python_version=python_version,
        platform=platform,
    )
    _atomic_write_text(Path(output).expanduser().resolve(strict=False), lock.text)
    return lock


def validate_lock(
    lock_path: Path,
    requirements_input: Path,
    wheelhouse: Path,
    *,
    python_version: str = "3.12",
    platform: str = "win_amd64",
) -> DependencyLock:
    expected = inspect_wheelhouse(
        requirements_input,
        wheelhouse,
        python_version=python_version,
        platform=platform,
    )
    try:
        actual = Path(lock_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DependencyLockError("Cannot read dependency lock") from exc
    lines = actual.splitlines()
    if any(_LOCK_LINE.fullmatch(line) is None for line in lines) or actual != expected.text:
        raise DependencyLockError("Dependency lock does not match the verified target wheel graph")
    return expected
