from pathlib import Path

import pytest


SCRIPT_ROOT = Path("scripts/codex-supervisor")
SCRIPTS = (
    "Start-Worker.ps1",
    "Stop-Worker.ps1",
    "Resume-Worker.ps1",
)


@pytest.mark.parametrize("filename", SCRIPTS)
def test_control_scripts_are_scoped_and_safe(filename: str) -> None:
    content = (SCRIPT_ROOT / filename).read_text(encoding="utf-8")
    lowered = content.lower()
    assert '$ErrorActionPreference = "Stop"' in content
    assert "$PSScriptRoot" in content
    assert '[ValidateSet("A", "B", "C")]' in content
    assert "taskkill" not in lowered
    assert "danger-full-access" not in lowered
    assert "bypass-approvals" not in lowered
    assert "api_key" not in lowered
    assert "cookie" not in lowered


def test_stop_requires_one_explicit_worker() -> None:
    content = (SCRIPT_ROOT / "Stop-Worker.ps1").read_text(
        encoding="utf-8"
    )
    assert "Mandatory = $true" in content
    assert '"all"' not in content


@pytest.mark.parametrize(
    "filename", ("Start-Worker.ps1", "Resume-Worker.ps1")
)
def test_start_and_resume_delegate_to_nonblocking_python_cli(
    filename: str,
) -> None:
    content = (SCRIPT_ROOT / filename).read_text(encoding="utf-8")
    assert "Start-Process" not in content
    assert "Wait-Process" not in content
    assert "approved-" in content
