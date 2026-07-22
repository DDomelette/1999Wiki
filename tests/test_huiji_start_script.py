from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_huiji_crawl_powershell_launcher_uses_unified_cli_and_portable_python_discovery():
    text = (ROOT / "crawl_huiji_res1999.ps1").read_text(encoding="utf-8")

    assert "1999wiki" not in text
    assert "conda" not in text.lower()
    assert "scripts\\crawl_huiji_res1999.py" not in text
    assert "scripts\\refresh_huiji_credentials.py" not in text
    assert "D:\\1999WIKI_ROBOT" not in text
    assert "RobotRoot" not in text
    assert "--robot-root" not in text
    assert "HUIJI_CRAWLER_PYTHON" in text
    assert "py.exe" in text
    assert "-3.12-64" in text
    assert "python.exe" in text
    assert '"-m", "src.huiji_crawler_tool", "crawl"' in text
    assert "--expected-user" in text
    assert "--log-every" in text
    assert "--quiet" in text
    assert '[ValidateSet("", "Requests", "Browser", "Edge")]' in text
    assert "$Transport" in text
    assert "--transport" in text
    assert "BrowserProfile" in text
    assert "--browser-profile" in text
    assert "EdgeProfile" in text
    assert "--edge-profile" in text
    assert "EdgePort" in text
    assert "--edge-port" in text
    assert "EdgeExecutable" in text
    assert "--edge-executable" in text
    assert "--browser-headless" in text
    assert "--no-browser-verify" in text
    assert "Read-Host" not in text
    assert "NoRetryOnSessionExpired" not in text
    assert "GUI tool" not in text
    assert "old GUI" not in text
    assert "password" not in text.lower()
    assert "huiji_session" not in text
    assert "__cf_bm" not in text


def test_huiji_crawl_batch_launcher_wraps_powershell_script():
    text = (ROOT / "crawl_huiji_res1999.bat").read_text(encoding="utf-8")

    assert "chcp 65001" in text
    assert "powershell" in text.lower()
    assert "crawl_huiji_res1999.ps1" in text
    assert "%*" in text


def test_huiji_crawl_batch_launcher_uses_crlf_line_endings():
    data = (ROOT / "crawl_huiji_res1999.bat").read_bytes()

    assert b"\r\n" in data
    assert data.count(b"\n") == data.count(b"\r\n")


def test_huiji_verify_powershell_launcher_runs_integrity_script():
    text = (ROOT / "verify_huiji_res1999.ps1").read_text(encoding="utf-8")

    assert "1999wiki" in text
    assert "scripts\\verify_huiji_res1999.py" in text
    assert "SkipResourceFiles" in text
    assert "--skip-resource-files" in text
    assert "SkipResourceHash" in text
    assert "--skip-resource-hash" in text
    assert "--issue-limit" in text
    assert "password" not in text.lower()
    assert "cookie" not in text.lower()


def test_huiji_verify_batch_launcher_wraps_powershell_script():
    text = (ROOT / "verify_huiji_res1999.bat").read_text(encoding="utf-8")

    assert "chcp 65001" in text
    assert "powershell" in text.lower()
    assert "verify_huiji_res1999.ps1" in text
    assert "%*" in text
