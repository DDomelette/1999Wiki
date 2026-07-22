"""Exact Windows process control used only by the local activation CLI."""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import psutil


@dataclass(frozen=True)
class BackendProcessIdentity:
    pid: int
    create_time: float
    executable: str
    cwd: str
    argv: tuple[str, ...]
    host: str = "127.0.0.1"
    port: int = 8000

    def to_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["argv"] = list(self.argv)
        return value

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "BackendProcessIdentity":
        return cls(
            pid=int(value["pid"]),
            create_time=float(value["create_time"]),
            executable=str(value["executable"]),
            cwd=str(value["cwd"]),
            argv=tuple(str(item) for item in value["argv"]),
            host=str(value.get("host") or "127.0.0.1"),
            port=int(value.get("port") or 8000),
        )


def _listener_pids(host: str, port: int) -> set[int]:
    pids: set[int] = set()
    for connection in psutil.net_connections(kind="tcp"):
        if connection.status != psutil.CONN_LISTEN or not connection.laddr:
            continue
        address = str(connection.laddr.ip)
        if int(connection.laddr.port) == port and address == host and connection.pid:
            pids.add(int(connection.pid))
    return pids


def _validate_command(identity: BackendProcessIdentity, project_root: Path) -> None:
    expected_tail = (
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    )
    if identity.argv[1:] != expected_tail:
        raise RuntimeError("port 8000 owner command is not the approved backend")
    executable = Path(identity.executable).resolve()
    if executable.name.lower() not in {"python.exe", "pythonw.exe"}:
        raise RuntimeError("backend executable is not Python")
    if Path(identity.cwd).resolve() != project_root.resolve():
        raise RuntimeError("backend working directory is not the project root")


def inspect_backend_optional(project_root: Path) -> BackendProcessIdentity | None:
    pids = _listener_pids("127.0.0.1", 8000)
    if not pids:
        return None
    if len(pids) != 1:
        raise RuntimeError("expected exactly one approved backend listener")
    pid = next(iter(pids))
    process = psutil.Process(pid)
    identity = BackendProcessIdentity(
        pid=pid,
        create_time=process.create_time(),
        executable=process.exe(),
        cwd=process.cwd(),
        argv=tuple(process.cmdline()),
    )
    _validate_command(identity, project_root)
    return identity


def inspect_backend(project_root: Path) -> BackendProcessIdentity:
    identity = inspect_backend_optional(project_root)
    if identity is None:
        raise RuntimeError("expected exactly one approved backend listener")
    return identity


def assert_same_backend(
    expected: BackendProcessIdentity,
    project_root: Path,
) -> BackendProcessIdentity:
    current = inspect_backend(project_root)
    if current != expected:
        raise RuntimeError("backend process identity drifted after inspect")
    return current


def stop_backend(
    expected: BackendProcessIdentity,
    project_root: Path,
    *,
    timeout_seconds: float = 30.0,
) -> None:
    assert_same_backend(expected, project_root)
    process = psutil.Process(expected.pid)
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except psutil.TimeoutExpired as error:
        raise TimeoutError("backend stop timed out") from error
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _listener_pids(expected.host, expected.port):
            return
        time.sleep(0.1)
    raise TimeoutError("backend port remained listening after stop")


def start_backend(
    expected: BackendProcessIdentity,
    project_root: Path,
    log_root: Path,
) -> BackendProcessIdentity:
    if _listener_pids(expected.host, expected.port):
        raise RuntimeError("backend port is already occupied")
    _validate_command(expected, project_root)
    log_root.mkdir(parents=True, exist_ok=True)
    stdout_path = log_root / "backend.stdout.log"
    stderr_path = log_root / "backend.stderr.log"
    if stdout_path.exists() or stderr_path.exists():
        raise FileExistsError("backend activation logs already exist")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            list(expected.argv),
            cwd=expected.cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            shell=False,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    created = psutil.Process(process.pid)
    return BackendProcessIdentity(
        pid=process.pid,
        create_time=created.create_time(),
        executable=created.exe(),
        cwd=created.cwd(),
        argv=tuple(created.cmdline()),
    )


def stop_owned_backend(
    identity: BackendProcessIdentity,
    *,
    timeout_seconds: float = 30.0,
) -> None:
    try:
        process = psutil.Process(identity.pid)
        if abs(process.create_time() - identity.create_time) > 0.01:
            raise RuntimeError("owned backend PID was reused")
        process.terminate()
        process.wait(timeout=timeout_seconds)
    except psutil.NoSuchProcess:
        return
    except psutil.TimeoutExpired as error:
        raise TimeoutError("owned backend stop timed out") from error


def wait_for_listener(
    identity: BackendProcessIdentity,
    *,
    timeout_seconds: float = 60.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            process = psutil.Process(identity.pid)
            if abs(process.create_time() - identity.create_time) > 0.01:
                raise RuntimeError("new backend PID was reused")
            if _listener_pids(identity.host, identity.port) == {identity.pid}:
                return
        except psutil.NoSuchProcess as error:
            raise RuntimeError("new backend exited before listening") from error
        time.sleep(0.25)
    raise TimeoutError("new backend listener timed out")


def public_process_reference(identity: BackendProcessIdentity) -> dict[str, Any]:
    return {
        "pid": identity.pid,
        "create_time": identity.create_time,
        "executable": identity.executable,
        "cwd": identity.cwd,
        "argv": list(identity.argv),
        "host": identity.host,
        "port": identity.port,
        "environment_value_recorded": False,
    }


__all__ = [
    "BackendProcessIdentity",
    "assert_same_backend",
    "inspect_backend",
    "inspect_backend_optional",
    "public_process_reference",
    "start_backend",
    "stop_backend",
    "stop_owned_backend",
    "wait_for_listener",
]
