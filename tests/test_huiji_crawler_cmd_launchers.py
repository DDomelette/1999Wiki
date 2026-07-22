from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "packaging" / "huiji-crawler" / "templates"


def test_cmd_launchers_quote_space_and_unicode_roots_and_forward_all_args() -> None:
    runtime = (TEMPLATES / "huiji-crawler.cmd").read_text(encoding="utf-8")
    install = (TEMPLATES / "install.cmd").read_text(encoding="utf-8")
    verify = (TEMPLATES / "verify-package.cmd").read_text(encoding="utf-8")

    assert '%~dp0' in runtime
    assert 'for %%I in ("%ROOT%.") do set "ROOT=%%~fI"' in runtime
    assert '"%ROOT%\\' in runtime
    assert "%*" in runtime
    assert 'set "PYTHONDONTWRITEBYTECODE=1"' in runtime
    assert '"%ROOT%\\bootstrap\\install.py"' in install
    assert '"%ROOT%\\bootstrap\\package_verify.py"' in verify
    assert 'set "PYTHONDONTWRITEBYTECODE=1"' in install
    assert 'set "PYTHONDONTWRITEBYTECODE=1"' in verify


def test_runtime_launcher_verifies_marker_and_critical_files_before_cli_import() -> None:
    text = (TEMPLATES / "huiji-crawler.cmd").read_text(encoding="utf-8")

    marker = text.index("--check-marker")
    verifier = text.index("--critical-only")
    cli = text.index("-m src.huiji_crawler_tool")
    assert marker < verifier < cli
    assert "install.cmd" in text
    assert "exit /b 8" in text
    assert "exit /b 4" in text


def test_python_selector_has_exact_candidate_order() -> None:
    text = (TEMPLATES / "select-python.cmd").read_text(encoding="utf-8")

    explicit = text.index("HUIJI_CRAWLER_PYTHON")
    launcher = text.index("py -3.12-64")
    path = text.index("where python.exe")
    assert explicit < launcher < path


def test_cmd_files_use_crlf_and_contain_no_conda_or_absolute_project_path() -> None:
    for path in sorted(TEMPLATES.glob("*.cmd")):
        data = path.read_bytes()
        text = data.decode("utf-8")
        assert data.count(b"\n") == data.count(b"\r\n")
        assert "conda" not in text.casefold()
        assert "D:\\PycharmProjects" not in text
        assert "D:\\1999WIKI_ROBOT" not in text
