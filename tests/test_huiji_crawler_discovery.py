from __future__ import annotations

from pathlib import Path

import pytest

from bootstrap.python_runtime import inspect_runtime
from src.huiji_crawler_tool.config import load_crawler_settings
from src.huiji_crawler_tool.discovery import (
    discover_edge_candidates,
    discover_python_candidates,
    select_edge_executable,
    select_python_candidate,
)
from src.huiji_crawler_tool.errors import CrawlerConfigError, CrawlerEnvironmentError


def _write_config(root: Path) -> None:
    path = root / "config" / "crawler.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """schema_version: huiji_crawler_config.v1
site:
  expected_user: POTATO BOT
crawl:
  namespaces: [0]
  include_file_manifest: false
  sleep_seconds: 0
  progress: false
  log_every: 1
  transport: requests
browser:
  headless: false
  verify_account: true
edge:
  port: 9222
""",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("system", "implementation", "version", "pointer_bits", "supported"),
    [
        ("Windows", "cpython", (3, 12, 0), 64, True),
        ("Windows", "cpython", (3, 12, 99), 64, True),
        ("Linux", "cpython", (3, 12, 0), 64, False),
        ("Windows", "pypy", (3, 12, 0), 64, False),
        ("Windows", "cpython", (3, 11, 9), 64, False),
        ("Windows", "cpython", (3, 13, 0), 64, False),
        ("Windows", "cpython", (3, 12, 0), 32, False),
    ],
)
def test_python_runtime_accepts_only_windows_cpython_312_x64(
    system: str,
    implementation: str,
    version: tuple[int, int, int],
    pointer_bits: int,
    supported: bool,
) -> None:
    info = inspect_runtime(
        system=system,
        implementation=implementation,
        version=version,
        machine="AMD64",
        pointer_bits=pointer_bits,
        executable=Path("python.exe"),
    )

    assert info.supported is supported
    assert bool(info.reasons) is (not supported)


def test_python_discovery_order_is_explicit_then_launcher_then_path(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit-python.exe"
    launcher = tmp_path / "py.exe"
    path_python = tmp_path / "path-python.exe"
    for path in (explicit, launcher, path_python):
        path.write_bytes(b"")

    def which(name: str) -> str | None:
        return {"py.exe": str(launcher), "py": str(launcher), "python.exe": str(path_python)}.get(name)

    def probe(command: tuple[str, ...]):
        executable = explicit if len(command) == 1 and command[0] == str(explicit) else path_python
        if "-3.12-64" in command:
            executable = tmp_path / "launcher-selected-python.exe"
        return inspect_runtime(
            system="Windows",
            implementation="cpython",
            version=(3, 12, 4),
            machine="AMD64",
            pointer_bits=64,
            executable=executable,
        )

    candidates = discover_python_candidates(
        environ={"HUIJI_CRAWLER_PYTHON": str(explicit)},
        which_fn=which,
        probe_fn=probe,
    )

    assert [candidate.source for candidate in candidates] == ["environment", "py_launcher", "path"]
    assert candidates[0].command == (str(explicit),)
    assert candidates[1].command[-1] == "-3.12-64"
    assert select_python_candidate(candidates) == candidates[0]


def test_python_selection_rejects_when_no_supported_candidate() -> None:
    candidates = discover_python_candidates(environ={}, which_fn=lambda name: None)

    with pytest.raises(CrawlerEnvironmentError, match="CPython 3.12 x64"):
        select_python_candidate(candidates)


def test_edge_discovery_order_and_exact_allowlist_are_stable(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit" / "msedge.exe"
    environment = tmp_path / "environment" / "msedge.exe"
    default_x86 = tmp_path / "Program Files (x86)" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    default_x64 = tmp_path / "Program Files" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    for path in (explicit, environment, default_x86, default_x64):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")

    candidates = discover_edge_candidates(
        explicit=explicit,
        environ={"HUIJI_CRAWLER_EDGE_EXECUTABLE": str(environment)},
        defaults=(default_x86, default_x64),
    )

    assert [candidate.source for candidate in candidates] == [
        "cli",
        "environment",
        "default_x86",
        "default_x64",
    ]
    assert select_edge_executable(candidates) == explicit.resolve()
    assert all(candidate.path.name == "msedge.exe" for candidate in candidates)


def test_external_edge_does_not_relax_profile_or_output_containment(tmp_path: Path) -> None:
    root = tmp_path / "tool"
    root.mkdir()
    _write_config(root)
    edge = tmp_path / "system" / "msedge.exe"
    edge.parent.mkdir()
    edge.write_bytes(b"")

    settings = load_crawler_settings(
        tool_root=root,
        environ={"HUIJI_CRAWLER_EDGE_EXECUTABLE": str(edge)},
    )

    assert settings.edge_executable == edge.resolve()
    with pytest.raises(CrawlerConfigError, match="tool root"):
        load_crawler_settings(
            tool_root=root,
            environ={
                "HUIJI_CRAWLER_EDGE_EXECUTABLE": str(edge),
                "HUIJI_CRAWLER_OUT": str(tmp_path / "outside"),
            },
        )
