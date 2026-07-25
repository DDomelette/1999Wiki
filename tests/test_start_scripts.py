from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_start_scripts_use_ipv4_health_check():
    """Windows scripts should avoid localhost IPv6 resolution for backend health."""
    text = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8000/health" in text
    assert "http://localhost:8000/health" not in text


def test_start_scripts_launch_react_vite():
    """Both one-click launchers should pin Vite to 5173 instead of drifting to 5174."""
    text = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "React Vite" in text
    assert "5173" in text
    assert "npm.cmd" in text
    assert "--port" in text
    assert "5173" in text
    assert "--strictPort" in text


def test_start_scripts_do_not_use_stale_chroma_or_ollama_checks():
    """Milvus/SiliconFlow setup should not be guarded by stale Chroma/Ollama checks."""
    text = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "vectorstore\\chroma.sqlite3" not in text
    assert "Ollama" not in text


def test_start_scripts_bind_backend_to_ipv4_loopback_only():
    """Avoid duplicate 0.0.0.0 and 127.0.0.1 listeners on Windows."""
    text = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "--host" in text
    assert "127.0.0.1" in text
    assert "0.0.0.0" not in text


def test_start_scripts_require_ok_health_status():
    """HTTP 200 with status=error must not be treated as a ready backend."""
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert ".status" in ps1
    assert "-eq \"ok\"" in ps1


def test_start_scripts_gate_huiji_provenance_before_backend_and_never_auto_build_legacy_data():
    text = (ROOT / "start.ps1").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "documents.jsonl" not in lowered
    assert "extract_data.py" not in lowered
    assert "scripts\\build_index.py" not in lowered
    assert "verify_huiji_runtime.py" in lowered
    assert lowered.index("verify_huiji_runtime.py") < lowered.index("uvicorn")
    assert "provenance_status" in lowered
    assert "provenance_skip" not in lowered
    assert "skip_provenance" not in lowered
    assert "huiji_provenance_disable" not in lowered


def test_start_scripts_use_1999wiki_and_prepare_compose_before_provenance():
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8")
    lowered = ps1.lower()

    assert r"d:\anaconda32024\envs\1999wiki\python.exe" in lowered
    assert "conda run" not in lowered
    assert "check_runtime_dependencies.py" in lowered
    assert "infra\\milvus\\docker-compose.yml" in lowered
    assert "docker" in lowered and "compose" in lowered
    assert "--no-recreate" in lowered
    assert "--wait-timeout" in lowered and "180" in lowered
    assert lowered.index("docker") < lowered.index("verify_huiji_runtime.py")


def test_powershell_cleanup_covers_the_full_startup_and_only_managed_apps():
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8")
    lowered = ps1.lower()

    assert lowered.index("try {") < lowered.index("verify_huiji_runtime.py")
    assert "finally" in lowered
    assert "taskkill.exe" in lowered
    assert "$process.refresh()" in lowered
    assert "$process.hasexited" in lowered
    assert "get-process -id $process.id" not in lowered
    assert "docker compose down" not in lowered
    assert "docker compose stop" not in lowered
    assert "read-host" not in lowered


def test_powershell_uses_fast_dotnet_port_detection():
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "IPGlobalProperties" in ps1
    assert "Get-NetTCPConnection" not in ps1


def test_powershell_recognizes_cancellation_across_startup_phases():
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "Test-NativeCancellationCode" in ps1
    assert "PipelineStoppedException" in ps1


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None and shutil.which("powershell") is None,
    reason="process cleanup integration test requires PowerShell",
)
def test_cleanup_skips_an_exited_process_even_if_its_pid_now_points_to_a_live_process():
    script_path = str(ROOT / "start.ps1").replace("'", "''")
    command = rf"""
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$tokens, [ref]$errors)
$functionAst = $ast.Find({{ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Stop-StartedProcesses' }}, $true)
Invoke-Expression $functionAst.Extent.Text
$child = Start-Process -PassThru -WindowStyle Hidden -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-Command', 'Start-Sleep -Seconds 30')
try {{
    $exitedOriginal = [pscustomobject]@{{ Id = $child.Id; HasExited = $true }}
    $exitedOriginal | Add-Member -MemberType ScriptMethod -Name Refresh -Value {{}}
    Stop-StartedProcesses -Processes @($exitedOriginal)
    if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) {{ exit 0 }}
    exit 1
}} finally {{
    Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue
}}
"""

    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr


def test_batch_launcher_delegates_to_powershell_for_identical_behavior():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8").lower()

    assert "powershell" in bat
    assert "start.ps1" in bat
    assert "exit /b" in bat


def test_milvus_compose_waits_for_healthy_dependencies_and_restarts():
    compose = yaml.safe_load(
        (ROOT / "infra" / "milvus" / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    standalone = services["standalone"]

    assert standalone["depends_on"]["etcd"]["condition"] == "service_healthy"
    assert standalone["depends_on"]["minio"]["condition"] == "service_healthy"
    for service_name in ("etcd", "minio", "standalone", "mysql", "attu"):
        assert services[service_name]["restart"] == "unless-stopped"


def test_vite_config_refuses_port_drift():
    """Manual npm run dev should also fail instead of opening 5174."""
    vite_config = (ROOT / "frontend" / "react-app" / "vite.config.ts").read_text(encoding="utf-8")

    assert "port: 5173" in vite_config
    assert "strictPort: true" in vite_config
    assert "host: '127.0.0.1'" in vite_config or 'host: "127.0.0.1"' in vite_config
