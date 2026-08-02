from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import psutil
import pytest

from src.codex_supervisor.processes import ProcessSnapshot
from src.codex_supervisor.runner import RunnerRequest, run_worker
from src.codex_supervisor.state_store import AtomicStateStore


FAKE_CODEX = (
    Path(__file__).parent / "fixtures" / "codex_supervisor" / "fake_codex.py"
)


@pytest.mark.parametrize("worker", ("A", "E"))
def test_observer_data_can_be_reopened_without_stopping_worker(
    tmp_path: Path, worker: str,
) -> None:
    runtime = tmp_path / "runtime"
    wait_file = tmp_path / "release"
    request = RunnerRequest(
        worker=worker,  # type: ignore[arg-type]
        project_root=Path.cwd(),
        runtime_root=runtime,
        worktree=tmp_path,
        argv=(
            sys.executable,
            str(FAKE_CODEX),
            "--fake-wait-file",
            str(wait_file),
        ),
    )
    thread = threading.Thread(target=run_worker, args=(request,), daemon=True)
    thread.start()
    store = AtomicStateStore(runtime)
    session_path = store.session_path(worker)  # type: ignore[arg-type]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not session_path.exists():
        time.sleep(0.02)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    codex = session["codex"]
    before = ProcessSnapshot.from_process(psutil.Process(codex["pid"]))

    event_path = store.event_log_path(worker)  # type: ignore[arg-type]
    while time.monotonic() < deadline:
        if event_path.exists() and "thread.started" in event_path.read_text(
            encoding="utf-8"
        ):
            break
        time.sleep(0.02)
    first_history = event_path.read_text(encoding="utf-8")
    second_history = store.event_log_path(worker).read_text(encoding="utf-8")  # type: ignore[arg-type]
    after = ProcessSnapshot.from_process(psutil.Process(codex["pid"]))

    assert "thread.started" in first_history
    assert second_history.startswith(first_history)
    assert after.pid == before.pid
    assert after.create_time == before.create_time

    wait_file.touch()
    thread.join(timeout=5)
    assert not thread.is_alive()
