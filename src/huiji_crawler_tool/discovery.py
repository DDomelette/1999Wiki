from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from bootstrap.python_runtime import PythonRuntimeInfo, probe_python_command

from .errors import CrawlerEnvironmentError


DEFAULT_EDGE_EXECUTABLES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


@dataclass(frozen=True)
class PythonCandidate:
    source: str
    command: tuple[str, ...]
    status: str
    runtime: PythonRuntimeInfo | None

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "command": list(self.command),
            "status": self.status,
            "runtime": None if self.runtime is None else self.runtime.to_json(),
        }


@dataclass(frozen=True)
class EdgeCandidate:
    source: str
    path: Path
    status: str

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "path": str(self.path),
            "status": self.status,
        }


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    import_name: str
    version: str | None
    status: str

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "import_name": self.import_name,
            "version": self.version,
            "status": self.status,
        }


def _which_first(which_fn: Callable[[str], str | None], *names: str) -> str | None:
    for name in names:
        found = which_fn(name)
        if found:
            return found
    return None


def discover_python_candidates(
    *,
    environ: Mapping[str, str] | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
    probe_fn: Callable[[tuple[str, ...]], PythonRuntimeInfo] = probe_python_command,
) -> tuple[PythonCandidate, ...]:
    environment = dict(os.environ if environ is None else environ)
    commands: list[tuple[str, tuple[str, ...]]] = []
    explicit = environment.get("HUIJI_CRAWLER_PYTHON", "").strip()
    if explicit:
        commands.append(("environment", (explicit,)))
    launcher = _which_first(which_fn, "py.exe", "py")
    if launcher:
        commands.append(("py_launcher", (launcher, "-3.12-64")))
    path_python = _which_first(which_fn, "python.exe", "python")
    if path_python:
        commands.append(("path", (path_python,)))

    candidates: list[PythonCandidate] = []
    for source, command in commands:
        try:
            runtime = probe_fn(command)
        except Exception:
            candidates.append(
                PythonCandidate(source=source, command=command, status="unavailable", runtime=None)
            )
            continue
        candidates.append(
            PythonCandidate(
                source=source,
                command=command,
                status="supported" if runtime.supported else "unsupported",
                runtime=runtime,
            )
        )
    return tuple(candidates)


def select_python_candidate(candidates: Sequence[PythonCandidate]) -> PythonCandidate:
    for candidate in candidates:
        if candidate.status == "supported" and candidate.runtime is not None:
            return candidate
    raise CrawlerEnvironmentError(
        "No supported Python candidate found; Windows CPython 3.12 x64 is required"
    )


def discover_edge_candidates(
    *,
    explicit: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    defaults: Sequence[Path] = DEFAULT_EDGE_EXECUTABLES,
) -> tuple[EdgeCandidate, ...]:
    environment = dict(os.environ if environ is None else environ)
    values: list[tuple[str, str | Path]] = []
    if explicit not in (None, ""):
        values.append(("cli", explicit))
    environment_value = environment.get("HUIJI_CRAWLER_EDGE_EXECUTABLE", "").strip()
    if environment_value:
        values.append(("environment", environment_value))
    default_sources = ("default_x86", "default_x64")
    values.extend(
        (default_sources[index] if index < len(default_sources) else f"default_{index}", path)
        for index, path in enumerate(defaults)
    )
    candidates: list[EdgeCandidate] = []
    for source, value in values:
        path = Path(value).expanduser().resolve(strict=False)
        candidates.append(
            EdgeCandidate(
                source=source,
                path=path,
                status="available" if path.is_file() else "missing",
            )
        )
    return tuple(candidates)


def select_edge_executable(candidates: Sequence[EdgeCandidate]) -> Path:
    for candidate in candidates:
        if candidate.status == "available":
            return candidate.path
    raise CrawlerEnvironmentError("Microsoft Edge executable was not found")


def find_edge_executable(
    explicit: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    return select_edge_executable(
        discover_edge_candidates(explicit=explicit, environ=environ)
    )


def inspect_dependencies() -> tuple[DependencyStatus, ...]:
    dependencies = (
        ("playwright", "playwright"),
        ("PyYAML", "yaml"),
        ("requests", "requests"),
    )
    results: list[DependencyStatus] = []
    for distribution, import_name in dependencies:
        available = importlib.util.find_spec(import_name) is not None
        version: str | None = None
        if available:
            try:
                version = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                available = False
        results.append(
            DependencyStatus(
                name=distribution,
                import_name=import_name,
                version=version,
                status="available" if available else "missing",
            )
        )
    return tuple(results)
