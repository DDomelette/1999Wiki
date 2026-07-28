from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from src.codex_supervisor.contracts import WorkerState
from src.codex_supervisor.processes import (
    ProcessIdentity,
    ProcessSnapshot,
    validate_process_identity,
    windows_detach_flags,
)
from src.codex_supervisor.runner import RunnerRequest, run_worker
from src.codex_supervisor.state_store import AtomicStateStore


FAKE_CODEX = (
    Path(__file__).parent / "fixtures" / "codex_supervisor" / "fake_codex.py"
)


def test_process_identity_rejects_pid_reuse() -> None:
    identity = ProcessIdentity(
        pid=42,
        create_time=100.0,
        executable="python.exe",
        cwd="D:/worktree",
        argv=("python.exe", "runner.py", "--worker", "A"),
        worker="A",
        role="runner",
    )
    observed = ProcessSnapshot(
        pid=42,
        create_time=101.0,
        executable="python.exe",
        cwd="D:/worktree",
        argv=("python.exe", "runner.py", "--worker", "A"),
    )
    with pytest.raises(RuntimeError, match="PID was reused"):
        validate_process_identity(identity, observed)


def test_stop_refuses_command_or_worktree_drift() -> None:
    identity = ProcessIdentity(
        pid=42,
        create_time=100.0,
        executable="codex.exe",
        cwd="D:/1999Wiki.worktrees/rag-a-routing",
        argv=("codex.exe", "exec", "-m", "gpt-5.6-sol"),
        worker="A",
        role="codex",
    )
    observed = ProcessSnapshot(
        pid=42,
        create_time=100.0,
        executable="codex.exe",
        cwd="D:/1999Wiki.worktrees/rag-b-bm25",
        argv=("codex.exe", "exec", "-m", "gpt-5.6-sol"),
    )
    with pytest.raises(RuntimeError, match="working directory drifted"):
        validate_process_identity(identity, observed)


def test_process_identity_rejects_command_drift() -> None:
    identity = ProcessIdentity(
        pid=42,
        create_time=100.0,
        executable="codex.exe",
        cwd="D:/worktree",
        argv=("codex.exe", "exec", "--json"),
        worker="A",
        role="codex",
    )
    observed = ProcessSnapshot(
        pid=42,
        create_time=100.0,
        executable="codex.exe",
        cwd="D:/worktree",
        argv=("codex.exe", "exec", "--quiet"),
    )
    with pytest.raises(RuntimeError, match="command line drifted"):
        validate_process_identity(identity, observed)


def test_detached_runner_uses_no_stdin_and_windows_detach_flags() -> None:
    flags = windows_detach_flags()
    assert flags & subprocess.CREATE_NEW_PROCESS_GROUP
    assert flags & subprocess.DETACHED_PROCESS
    assert flags & subprocess.CREATE_NO_WINDOW


def test_runner_streams_events_and_persists_stderr(tmp_path: Path) -> None:
    store = AtomicStateStore(tmp_path / "runtime")
    request = _request(
        tmp_path,
        store,
        "--fake-delay-seconds",
        "0.4",
        "--fake-stderr",
        "synthetic stderr",
    )
    result: list[int] = []
    thread = threading.Thread(
        target=lambda: result.append(run_worker(request)),
        daemon=True,
    )
    thread.start()

    event_path = store.event_log_path("A")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if event_path.exists() and "thread.started" in event_path.read_text(
            encoding="utf-8"
        ):
            break
        time.sleep(0.02)
    assert thread.is_alive(), "runner buffered events until child exit"

    thread.join(timeout=5)
    assert result == [0]
    assert store.read("A").status == "completed_pending_review"
    assert "synthetic stderr" in store.stderr_log_path("A").read_text(
        encoding="utf-8"
    )
    session = json.loads(
        store.session_path("A").read_text(encoding="utf-8")
    )
    assert session["runner"]["pid"]
    assert session["codex"]["pid"]


def test_runner_marks_abnormal_child_exit_failed(tmp_path: Path) -> None:
    store = AtomicStateStore(tmp_path / "runtime")
    request = _request(
        tmp_path,
        store,
        "--fake-exit-code",
        "17",
    )
    assert run_worker(request) == 17
    state = store.read("A")
    assert state.status == "failed"
    assert "17" in (state.blocker or "")


def test_runner_reclaims_stale_lock(tmp_path: Path) -> None:
    store = AtomicStateStore(tmp_path / "runtime")
    lock = store.lock_path("A")
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"pid": 999999, "create_time": 1.0}),
        encoding="utf-8",
    )
    assert run_worker(_request(tmp_path, store)) == 0


def _request(
    tmp_path: Path,
    store: AtomicStateStore,
    *fake_args: str,
) -> RunnerRequest:
    return RunnerRequest(
        worker="A",
        project_root=Path.cwd(),
        runtime_root=store.runtime_root,
        worktree=tmp_path,
        argv=(sys.executable, str(FAKE_CODEX), *fake_args),
    )
