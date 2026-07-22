"""Validate the installed Python environment against the project requirements."""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable, Sequence

try:
    from packaging.requirements import InvalidRequirement, Requirement
except ModuleNotFoundError as error:
    if not error.name or not error.name.startswith("packaging"):
        raise
    InvalidRequirement = ValueError
    Requirement = None  # type: ignore[assignment,misc]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = PROJECT_ROOT / "requirements.txt"


@dataclass(frozen=True)
class DependencyIssue:
    requirement: str
    actual: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the 1999Wiki Python runtime")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    return parser


def unsatisfied_requirements(
    requirements_path: Path,
    *,
    version_getter: Callable[[str], str] = version,
) -> tuple[DependencyIssue, ...]:
    """Return missing, invalid, or version-mismatched direct requirements."""
    if Requirement is None:
        return (DependencyIssue("packaging", "missing"),)
    issues: list[DependencyIssue] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        requirement_text = line.strip()
        if not requirement_text or requirement_text.startswith("#"):
            continue
        try:
            requirement = Requirement(requirement_text)
        except InvalidRequirement:
            issues.append(DependencyIssue(requirement_text, "invalid"))
            continue
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        try:
            installed_version = version_getter(requirement.name)
        except PackageNotFoundError:
            issues.append(DependencyIssue(requirement_text, "missing"))
            continue
        if requirement.specifier and not requirement.specifier.contains(
            installed_version,
            prereleases=True,
        ):
            issues.append(DependencyIssue(requirement_text, installed_version))
    return tuple(issues)


def _run_pip_check() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    version_getter: Callable[[str], str] = version,
    pip_check_runner: Callable[[], subprocess.CompletedProcess[str]] = _run_pip_check,
) -> int:
    args = _parser().parse_args(argv)
    try:
        issues = unsatisfied_requirements(
            args.requirements,
            version_getter=version_getter,
        )
        for issue in issues:
            print(
                f"dependency_error requirement={issue.requirement} actual={issue.actual}",
                file=sys.stderr,
            )

        if Requirement is None:
            print("status=error component=dependencies", file=sys.stderr)
            return 1

        completed = pip_check_runner()
        if completed.returncode != 0:
            details = (completed.stdout or completed.stderr or "pip check failed").strip()
            print(f"dependency_error pip_check={details}", file=sys.stderr)
    except KeyboardInterrupt:
        print("status=cancelled component=dependencies", file=sys.stderr)
        return 130
    except (OSError, UnicodeError) as error:
        print(
            f"status=error component=requirements error_type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    if issues or completed.returncode != 0:
        print("status=error component=dependencies", file=sys.stderr)
        return 1
    print("status=pass component=dependencies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
