from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_start_scripts_use_ipv4_health_check():
    """Windows scripts should avoid localhost IPv6 resolution for backend health."""
    for script_name in ("start.ps1", "start.bat"):
        text = (ROOT / script_name).read_text(encoding="utf-8")
        assert "http://127.0.0.1:8000/health" in text
        assert "http://localhost:8000/health" not in text


def test_start_scripts_launch_react_vite():
    """Both one-click launchers should pin Vite to 5173 instead of drifting to 5174."""
    for script_name in ("start.ps1", "start.bat"):
        text = (ROOT / script_name).read_text(encoding="utf-8")
        assert "React Vite" in text
        assert "5173" in text
        assert "npm.cmd" in text
        assert "--port" in text
        assert "5173" in text
        assert "--strictPort" in text


def test_start_scripts_do_not_use_stale_chroma_or_ollama_checks():
    """Milvus/SiliconFlow setup should not be guarded by stale Chroma/Ollama checks."""
    for script_name in ("start.ps1", "start.bat"):
        text = (ROOT / script_name).read_text(encoding="utf-8")
        assert "vectorstore\\chroma.sqlite3" not in text
        assert "Ollama" not in text


def test_start_scripts_bind_backend_to_ipv4_loopback_only():
    """Avoid duplicate 0.0.0.0 and 127.0.0.1 listeners on Windows."""
    for script_name in ("start.ps1", "start.bat"):
        text = (ROOT / script_name).read_text(encoding="utf-8")
        assert "--host" in text
        assert "127.0.0.1" in text
        assert "0.0.0.0" not in text


def test_start_scripts_require_ok_health_status():
    """HTTP 200 with status=error must not be treated as a ready backend."""
    ps1 = (ROOT / "start.ps1").read_text(encoding="utf-8")
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")

    assert ".status" in ps1
    assert "-eq \"ok\"" in ps1
    assert "json.load" in bat
    assert "status')=='ok'" in bat


def test_start_scripts_gate_huiji_provenance_before_backend_and_never_auto_build_legacy_data():
    for script_name in ("start.ps1", "start.bat"):
        text = (ROOT / script_name).read_text(encoding="utf-8")
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


def test_vite_config_refuses_port_drift():
    """Manual npm run dev should also fail instead of opening 5174."""
    vite_config = (ROOT / "frontend" / "react-app" / "vite.config.ts").read_text(encoding="utf-8")

    assert "port: 5173" in vite_config
    assert "strictPort: true" in vite_config
    assert "host: '127.0.0.1'" in vite_config or 'host: "127.0.0.1"' in vite_config
