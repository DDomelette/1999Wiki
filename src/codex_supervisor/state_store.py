from __future__ import annotations

import json
import os
from pathlib import Path

from src.codex_supervisor.contracts import WorkerName, WorkerState


class AtomicStateStore:
    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root.resolve()

    def state_path(self, worker: WorkerName) -> Path:
        return self.runtime_root / "workers" / worker / "state.json"

    def event_log_path(self, worker: WorkerName) -> Path:
        return self.runtime_root / "logs" / f"{worker}.events.jsonl"

    def stderr_log_path(self, worker: WorkerName) -> Path:
        return self.runtime_root / "logs" / f"{worker}.stderr.log"

    def session_path(self, worker: WorkerName) -> Path:
        return self.runtime_root / "sessions" / f"{worker}.json"

    def lock_path(self, worker: WorkerName) -> Path:
        return self.runtime_root / "locks" / f"{worker}.lock"

    def read(self, worker: WorkerName) -> WorkerState:
        path = self.state_path(worker)
        if not path.is_file():
            raise FileNotFoundError(f"worker {worker} state does not exist")
        return WorkerState.from_json(
            json.loads(path.read_text(encoding="utf-8"))
        )

    def write(self, state: WorkerState) -> None:
        path = self.state_path(state.worker)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    state.to_json(),
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def append_event(self, worker: WorkerName, raw_line: str) -> None:
        path = self.event_log_path(worker)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(raw_line.rstrip("\r\n"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
