import os
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from subprocess import CompletedProcess, run
import sys

from scripts.check_runtime_dependencies import main, unsatisfied_requirements


def _version_getter(versions: dict[str, str]):
    def get_version(name: str) -> str:
        try:
            return versions[name]
        except KeyError as error:
            raise PackageNotFoundError(name) from error

    return get_version


def test_unsatisfied_requirements_reports_missing_and_version_mismatch(tmp_path: Path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "installed>=1\nmissing\npinned==2.2.0\nignored; python_version < '2'\n",
        encoding="utf-8",
    )

    issues = unsatisfied_requirements(
        requirements,
        version_getter=_version_getter({"installed": "1.5", "pinned": "4.2.0"}),
    )

    assert [(issue.requirement, issue.actual) for issue in issues] == [
        ("missing", "missing"),
        ("pinned==2.2.0", "4.2.0"),
    ]


def test_dependency_cli_combines_requirement_and_pip_check_failures(tmp_path: Path, capsys):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("missing-package\n", encoding="utf-8")

    def failed_pip_check() -> CompletedProcess[str]:
        return CompletedProcess(
            args=["python", "-m", "pip", "check"],
            returncode=1,
            stdout="broken-package requires dependency",
            stderr="",
        )

    result = main(
        ["--requirements", str(requirements)],
        version_getter=_version_getter({}),
        pip_check_runner=failed_pip_check,
    )

    output = capsys.readouterr()
    assert result == 1
    assert "missing-package" in output.err
    assert "broken-package requires dependency" in output.err


def test_dependency_cli_passes_when_requirements_and_environment_are_consistent(
    tmp_path: Path, capsys
):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("installed>=1\n", encoding="utf-8")

    result = main(
        ["--requirements", str(requirements)],
        version_getter=_version_getter({"installed": "1.5"}),
        pip_check_runner=lambda: CompletedProcess([], 0, "No broken requirements found.\n", ""),
    )

    output = capsys.readouterr()
    assert result == 0
    assert "status=pass" in output.out


def test_dependency_cli_handles_keyboard_interrupt_without_traceback(tmp_path: Path, capsys):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("installed>=1\n", encoding="utf-8")

    def interrupted_pip_check() -> CompletedProcess[str]:
        raise KeyboardInterrupt

    result = main(
        ["--requirements", str(requirements)],
        version_getter=_version_getter({"installed": "1.5"}),
        pip_check_runner=interrupted_pip_check,
    )

    output = capsys.readouterr()
    assert result == 130
    assert "status=cancelled" in output.err
    assert "Traceback" not in output.err


def test_dependency_checker_reports_missing_packaging_without_traceback(tmp_path: Path):
    shadow_root = tmp_path / "shadow"
    shadow_package = shadow_root / "packaging"
    shadow_package.mkdir(parents=True)
    (shadow_package / "__init__.py").write_text(
        "raise ModuleNotFoundError('packaging unavailable', name='packaging')\n",
        encoding="utf-8",
    )
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("packaging\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(shadow_root)

    completed = run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "check_runtime_dependencies.py"),
            "--requirements",
            str(requirements),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )

    assert completed.returncode == 1
    assert "requirement=packaging actual=missing" in completed.stderr
    assert "Traceback" not in completed.stderr
