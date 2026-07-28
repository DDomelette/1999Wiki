from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import psutil

from src.codex_supervisor.contracts import WorkerName, WorkerState
from src.codex_supervisor.events import apply_event
from src.codex_supervisor.processes import (
    ProcessIdentity,
    codex_creation_flags,
    inspect_owned_process,
    windows_detach_flags,
)
from src.codex_supervisor.state_store import AtomicStateStore


@dataclass(frozen=True)
class RunnerRequest:
    worker: WorkerName
    project_root: Path
    runtime_root: Path
    worktree: Path
    argv: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "project_root": str(self.project_root.resolve()),
            "runtime_root": str(self.runtime_root.resolve()),
            "worktree": str(self.worktree.resolve()),
            "argv": list(self.argv),
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> RunnerRequest:
        worker = str(value["worker"])
        if worker not in ("A", "B", "C"):
            raise ValueError(f"unsupported worker name: {worker}")
        return cls(
            worker=worker,  # type: ignore[arg-type]
            project_root=Path(str(value["project_root"])).resolve(),
            runtime_root=Path(str(value["runtime_root"])).resolve(),
            worktree=Path(str(value["worktree"])).resolve(),
            argv=tuple(str(item) for item in value["argv"]),
        )


def start_detached_runner(request: RunnerRequest) -> ProcessIdentity:
    store = AtomicStateStore(request.runtime_root)
    _reject_active_session(store, request.worker)
    request_path = (
        request.runtime_root / "requests" / f"{request.worker}.json"
    )
    _atomic_json_write(request_path, request.to_json())
    argv = (
        sys.executable,
        "-m",
        "src.codex_supervisor.runner",
        "--request",
        str(request_path),
    )
    process = subprocess.Popen(
        argv,
        cwd=request.project_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        creationflags=windows_detach_flags(),
        start_new_session=os.name != "nt",
    )
    return _capture_with_retry(
        process.pid,
        worker=request.worker,
        role="runner",
    )


def run_worker(request: RunnerRequest) -> int:
    store = AtomicStateStore(request.runtime_root)
    lock_owner = _acquire_lock(store, request.worker)
    child: subprocess.Popen[str] | None = None
    try:
        try:
            state = store.read(request.worker)
        except FileNotFoundError:
            state = WorkerState.initial(request.worker)
        state = replace(
            state.with_status("running"),
            blocker=None,
            last_error=None,
        )
        store.write(state)

        runner_identity = ProcessIdentity.capture(
            psutil.Process(os.getpid()),
            worker=request.worker,
            role="runner",
        )
        stderr_path = store.stderr_log_path(request.worker)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        with stderr_path.open(
            "a", encoding="utf-8", newline="\n"
        ) as stderr_file:
            child = subprocess.Popen(
                request.argv,
                cwd=request.worktree,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                creationflags=codex_creation_flags(),
                start_new_session=False,
            )
            child_identity = _capture_with_retry(
                child.pid,
                worker=request.worker,
                role="codex",
            )
            _write_session(
                store,
                request.worker,
                runner_identity,
                child_identity,
                state.session_id,
            )
            assert child.stdout is not None
            for raw_line in child.stdout:
                line = raw_line.rstrip("\r\n")
                store.append_event(request.worker, line)
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError("event is not a JSON object")
                    event["_supervisor_event_ordinal"] = (
                        state.last_event_ordinal + 1
                    )
                    state = apply_event(state, event)
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    state = replace(
                        state,
                        last_error=f"ignored malformed event: {error}",
                    )
                store.write(state)
            return_code = child.wait()

        if return_code != 0:
            state = replace(
                state.with_status("failed"),
                blocker=f"Codex child exited with code {return_code}",
                last_error=f"Codex child exited with code {return_code}",
                last_exit_code=return_code,
            )
        elif state.status == "running":
            state = state.with_status("completed_pending_review")
        store.write(state)
        _write_session(
            store,
            request.worker,
            runner_identity,
            child_identity,
            state.session_id,
        )
        return return_code
    except BaseException as error:
        try:
            state = store.read(request.worker)
        except FileNotFoundError:
            state = WorkerState.initial(request.worker)
        public_error = f"runner failed: {type(error).__name__}: {error}"
        store.write(
            replace(
                state.with_status("failed"),
                blocker=public_error,
                last_error=public_error,
            )
        )
        raise
    finally:
        _release_lock(store, request.worker, lock_owner)


def _reject_active_session(
    store: AtomicStateStore,
    worker: WorkerName,
) -> None:
    path = store.session_path(worker)
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    for role in ("codex", "runner"):
        raw_identity = payload.get(role)
        if not isinstance(raw_identity, Mapping):
            continue
        identity = ProcessIdentity.from_json(raw_identity)
        try:
            inspect_owned_process(identity)
        except psutil.NoSuchProcess:
            continue
        raise RuntimeError(f"worker {worker} already has an active {role}")


def _capture_with_retry(
    pid: int,
    *,
    worker: WorkerName,
    role: str,
) -> ProcessIdentity:
    deadline = time.monotonic() + 5
    while True:
        try:
            return ProcessIdentity.capture(
                psutil.Process(pid),
                worker=worker,
                role=role,  # type: ignore[arg-type]
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def _acquire_lock(
    store: AtomicStateStore,
    worker: WorkerName,
) -> dict[str, Any]:
    path = store.lock_path(worker)
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = {
        "pid": os.getpid(),
        "create_time": psutil.Process(os.getpid()).create_time(),
    }
    for _ in range(2):
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            )
        except FileExistsError:
            if _lock_is_active(path):
                raise RuntimeError(f"worker {worker} runner lock is active")
            path.unlink(missing_ok=True)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(owner, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        return owner
    raise RuntimeError(f"could not acquire worker {worker} runner lock")


def _lock_is_active(path: Path) -> bool:
    try:
        owner = json.loads(path.read_text(encoding="utf-8"))
        process = psutil.Process(int(owner["pid"]))
        return abs(
            process.create_time() - float(owner["create_time"])
        ) <= 0.01
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        psutil.NoSuchProcess,
    ):
        return False


def _release_lock(
    store: AtomicStateStore,
    worker: WorkerName,
    owner: Mapping[str, Any],
) -> None:
    path = store.lock_path(worker)
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if current == owner:
        path.unlink(missing_ok=True)


def _write_session(
    store: AtomicStateStore,
    worker: WorkerName,
    runner: ProcessIdentity,
    codex: ProcessIdentity,
    session_id: str | None,
) -> None:
    _atomic_json_write(
        store.session_path(worker),
        {
            "schema_version": "codex-supervisor-session/v1",
            "worker": worker,
            "session_id": session_id,
            "runner": runner.to_json(),
            "codex": codex.to_json(),
        },
    )


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    request = RunnerRequest.from_json(
        json.loads(args.request.read_text(encoding="utf-8"))
    )
    return run_worker(request)


if __name__ == "__main__":
    raise SystemExit(main())
