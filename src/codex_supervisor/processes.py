from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

import psutil

from src.codex_supervisor.contracts import WorkerName


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    create_time: float
    executable: str
    cwd: str
    argv: tuple[str, ...]

    @classmethod
    def from_process(cls, process: psutil.Process) -> ProcessSnapshot:
        return cls(
            pid=process.pid,
            create_time=process.create_time(),
            executable=process.exe(),
            cwd=process.cwd(),
            argv=tuple(process.cmdline()),
        )


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float
    executable: str
    cwd: str
    argv: tuple[str, ...]
    worker: WorkerName
    role: Literal["runner", "codex"]

    def to_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["argv"] = list(self.argv)
        return value

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> ProcessIdentity:
        worker = str(value["worker"])
        role = str(value["role"])
        if worker not in ("A", "B", "C"):
            raise ValueError(f"unsupported worker name: {worker}")
        if role not in ("runner", "codex"):
            raise ValueError(f"unsupported process role: {role}")
        return cls(
            pid=int(value["pid"]),
            create_time=float(value["create_time"]),
            executable=str(value["executable"]),
            cwd=str(value["cwd"]),
            argv=tuple(str(item) for item in value["argv"]),
            worker=worker,  # type: ignore[arg-type]
            role=role,  # type: ignore[arg-type]
        )

    @classmethod
    def capture(
        cls,
        process: psutil.Process,
        *,
        worker: WorkerName,
        role: Literal["runner", "codex"],
    ) -> ProcessIdentity:
        snapshot = ProcessSnapshot.from_process(process)
        return cls(
            **asdict(snapshot),
            worker=worker,
            role=role,
        )


def validate_process_identity(
    identity: ProcessIdentity,
    observed: ProcessSnapshot,
) -> None:
    if identity.pid != observed.pid:
        raise RuntimeError("process PID drifted")
    if abs(identity.create_time - observed.create_time) > 0.01:
        raise RuntimeError("PID was reused")
    if Path(identity.executable).name.casefold() != Path(
        observed.executable
    ).name.casefold():
        raise RuntimeError("process executable drifted")
    if _normal_path(identity.cwd) != _normal_path(observed.cwd):
        raise RuntimeError("process working directory drifted")
    if _normal_argv(identity.argv) != _normal_argv(observed.argv):
        raise RuntimeError("process command line drifted")


def inspect_owned_process(identity: ProcessIdentity) -> psutil.Process:
    try:
        process = psutil.Process(identity.pid)
        observed = ProcessSnapshot.from_process(process)
    except psutil.NoSuchProcess:
        raise
    validate_process_identity(identity, observed)
    return process


def stop_owned_worker(
    identity: ProcessIdentity,
    timeout_seconds: float = 30.0,
) -> None:
    try:
        process = inspect_owned_process(identity)
    except psutil.NoSuchProcess:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except psutil.TimeoutExpired as error:
        raise TimeoutError(
            f"owned {identity.role} process stop timed out"
        ) from error


def windows_detach_flags() -> int:
    if os.name != "nt":
        return 0
    return (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW
    )


def codex_creation_flags() -> int:
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW


def _normal_path(value: str) -> str:
    return os.path.normcase(os.path.abspath(value))


def _normal_argv(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return value
    return (Path(value[0]).name.casefold(), *value[1:])
