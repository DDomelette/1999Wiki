from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Sequence

import psutil

from src.codex_supervisor.contracts import (
    SUPPORTED_WORKERS,
    SupervisorConfig,
    WorkerConfig,
    WorkerName,
    argparse_worker_name,
    build_codex_base_args,
    load_supervisor_config,
    supported_workers_json,
)
from src.codex_supervisor.processes import (
    ProcessIdentity,
    inspect_owned_process,
    stop_owned_worker,
)
from src.codex_supervisor.runner import (
    RunnerRequest,
    start_detached_runner,
)
from src.codex_supervisor.state_store import AtomicStateStore


def is_resumable_status(status: str) -> bool:
    return status in {
        "failed",
        "blocked",
        "needs_approval",
        "completed_pending_review",
        "accepted",
    }


def build_resume_args(
    config: WorkerConfig,
    session_id: str,
    prompt: str,
    final_schema: Path,
) -> tuple[str, ...]:
    if not session_id.strip():
        raise ValueError("resume requires a recorded session ID")
    if config.allow_subagents or config.fast_mode or config.multi_agent:
        raise ValueError("resume configuration violates worker constraints")
    return (
        "codex",
        "exec",
        "resume",
        "-m",
        config.model,
        "-c",
        f'model_reasoning_effort="{config.reasoning_effort}"',
        "--disable",
        "fast_mode",
        "--disable",
        "multi_agent",
        "-c",
        f'sandbox_mode="{config.sandbox}"',
        "--json",
        "--output-schema",
        str(final_schema.resolve()),
        session_id,
        prompt,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
) -> int:
    root = (project_root or Path.cwd()).resolve()
    try:
        args = _parser().parse_args(argv)
        return _dispatch(args, root)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _dispatch(args: argparse.Namespace, root: Path) -> int:
    config = load_supervisor_config(root)
    store = AtomicStateStore(config.runtime_root)
    worker: WorkerName | None = getattr(args, "worker", None)
    if args.command == "worker-list":
        payload = supported_workers_json()
        payload["config_schema_version"] = config.schema_version
        _print_json(payload)
        return 0
    if args.command == "worker-validate":
        assert worker is not None
        worker_config = config.workers[worker]
        _print_json(
            {
                "worker": worker,
                "branch": worker_config.branch,
                "worktree": str(worker_config.worktree),
                "model": worker_config.model,
                "reasoning_effort": worker_config.reasoning_effort,
                "sandbox": worker_config.sandbox,
                "fast_mode": worker_config.fast_mode,
                "multi_agent": worker_config.multi_agent,
                "allow_subagents": worker_config.allow_subagents,
            }
        )
        return 0
    if args.command == "start":
        assert worker is not None
        prompt = _read_approved_task(
            Path(args.task_file),
            store,
            worker,
            "approved-task.md",
        )
        worker_config = config.workers[worker]
        _validate_worktree(worker_config)
        schema = _final_schema(root)
        command = resolve_codex_argv(
            build_codex_base_args(worker_config, schema) + (prompt,)
        )
        identity = start_detached_runner(
            RunnerRequest(
                worker=worker,
                project_root=root,
                runtime_root=config.runtime_root,
                worktree=worker_config.worktree,
                argv=command,
                required_python_environment=config.python_environment,
            )
        )
        _print_json(
            {
                "worker": worker,
                "runner_pid": identity.pid,
                "state": str(store.state_path(worker)),
                "watch": _watch_command(root, worker),
            }
        )
        return 0
    if args.command == "resume":
        assert worker is not None
        state = store.read(worker)
        if not is_resumable_status(state.status):
            raise ValueError(
                "resume requires failed, blocked, needs_approval, or "
                "completed_pending_review/accepted state"
            )
        if not state.session_id:
            raise ValueError("resume requires a recorded session ID")
        prompt = _read_approved_task(
            Path(args.task_file),
            store,
            worker,
            "approved-resume.md",
        )
        worker_config = config.workers[worker]
        _validate_worktree(worker_config)
        command = resolve_codex_argv(
            build_resume_args(
                worker_config,
                state.session_id,
                prompt,
                _final_schema(root),
            )
        )
        identity = start_detached_runner(
            RunnerRequest(
                worker=worker,
                project_root=root,
                runtime_root=config.runtime_root,
                worktree=worker_config.worktree,
                argv=command,
                required_python_environment=config.python_environment,
            )
        )
        _print_json(
            {
                "worker": worker,
                "session_id": state.session_id,
                "runner_pid": identity.pid,
                "watch": _watch_command(root, worker),
            }
        )
        return 0
    if args.command == "stop":
        assert worker is not None
        _stop_worker(store, worker)
        _print_json({"worker": worker, "status": "blocked"})
        return 0
    if args.command == "status":
        assert worker is not None
        _print_json(_public_state(store, worker))
        return 0
    if args.command == "inspect":
        assert worker is not None
        state = _public_state(store, worker)
        session_path = store.session_path(worker)
        session = (
            json.loads(session_path.read_text(encoding="utf-8"))
            if session_path.is_file()
            else None
        )
        _print_json({"state": state, "session": session})
        return 0
    if args.command == "accept":
        assert worker is not None
        state = store.read(worker)
        if state.status != "completed_pending_review":
            raise ValueError(
                "accept requires completed_pending_review state"
            )
        accepted = state.with_status("accepted")
        store.write(accepted)
        _print_json(accepted.to_public_json())
        return 0
    if args.command == "watch":
        assert worker is not None
        _watch_worker(
            store,
            worker,
            tail=args.tail,
            once=args.once,
        )
        return 0
    if args.command == "dashboard":
        _dashboard(store, config, watch=args.watch)
        return 0
    raise ValueError(f"unsupported command: {args.command}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-supervisor")
    commands = parser.add_subparsers(dest="command", required=True)
    worker_list = commands.add_parser("worker-list")
    worker_list.add_argument("--json", action="store_true")
    worker_validate = commands.add_parser("worker-validate")
    worker_validate.add_argument(
        "--worker", required=True, type=argparse_worker_name
    )
    worker_validate.add_argument("--json", action="store_true")
    for command in ("start", "resume"):
        child = commands.add_parser(command)
        child.add_argument(
            "--worker", required=True, type=argparse_worker_name
        )
        child.add_argument("--task-file", required=True)
    for command in ("stop", "status", "inspect", "accept"):
        child = commands.add_parser(command)
        child.add_argument(
            "--worker", required=True, type=argparse_worker_name
        )
    watch = commands.add_parser("watch")
    watch.add_argument(
        "--worker", required=True, type=argparse_worker_name
    )
    watch.add_argument("--tail", type=int, default=50)
    watch.add_argument("--once", action="store_true")
    dashboard = commands.add_parser("dashboard")
    dashboard.add_argument("--watch", action="store_true")
    return parser


def _read_approved_task(
    task_file: Path,
    store: AtomicStateStore,
    worker: WorkerName,
    filename: str,
) -> str:
    expected = (
        store.runtime_root / "workers" / worker / filename
    ).resolve()
    actual = task_file.resolve()
    if actual != expected:
        raise ValueError(f"task file must be exact {filename} path")
    if not actual.is_file():
        raise FileNotFoundError(f"approved task file is missing: {actual}")
    content = actual.read_text(encoding="utf-8")
    required = ("Spec:", "Plan:", "Allowed files:", "Subagents: forbidden")
    missing = [marker for marker in required if marker not in content]
    if missing:
        raise ValueError(
            "approved task file is missing: " + ", ".join(missing)
        )
    return content


def _validate_worktree(config: WorkerConfig) -> None:
    if not config.worktree.is_dir():
        raise FileNotFoundError(
            f"worker {config.name} worktree is missing: {config.worktree}"
        )
    result = subprocess.run(
        [
            "git",
            "-C",
            str(config.worktree),
            "branch",
            "--show-current",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"worker {config.name} worktree is not a Git checkout"
        )
    if result.stdout.strip() != config.branch:
        raise RuntimeError(
            f"worker {config.name} branch does not match {config.branch}"
        )


def resolve_codex_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    launcher_value = shutil.which("codex")
    if launcher_value:
        launcher = Path(launcher_value)
        if launcher.suffix.casefold() in {".cmd", ".bat"}:
            javascript = (
                launcher.parent
                / "node_modules"
                / "@openai"
                / "codex"
                / "bin"
                / "codex.js"
            )
            node = shutil.which("node.exe") or shutil.which("node")
            if javascript.is_file() and node:
                return (node, str(javascript), *argv[1:])
        elif launcher.is_file():
            return (str(launcher), *argv[1:])
    executable = shutil.which("codex.exe")
    if executable:
        return (executable, *argv[1:])
    if not launcher_value:
        raise FileNotFoundError("codex executable was not found")
    raise RuntimeError(
        "codex launcher requires an accessible executable or npm Node entry"
    )


def _stop_worker(store: AtomicStateStore, worker: WorkerName) -> None:
    path = store.session_path(worker)
    if not path.is_file():
        raise FileNotFoundError(f"worker {worker} session does not exist")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for role in ("codex", "runner"):
        identity_value = payload.get(role)
        if not isinstance(identity_value, dict):
            continue
        stop_owned_worker(ProcessIdentity.from_json(identity_value))
    state = store.read(worker)
    store.write(
        replace(
            state.with_status("blocked"),
            blocker="stopped explicitly by supervisor",
        )
    )


def _final_schema(root: Path) -> Path:
    return (
        root
        / "scripts"
        / "codex-supervisor"
        / "schemas"
        / "worker-final.schema.json"
    )


def _watch_command(root: Path, worker: WorkerName) -> str:
    return (
        "powershell.exe -NoExit -ExecutionPolicy Bypass -File "
        f'"{root / "scripts" / "codex-supervisor" / "Watch-Worker.ps1"}" '
        f"-Worker {worker}"
    )


def _watch_worker(
    store: AtomicStateStore,
    worker: WorkerName,
    *,
    tail: int,
    once: bool,
) -> None:
    if tail < 0:
        raise ValueError("watch tail must be non-negative")
    event_path = store.event_log_path(worker)
    offset = 0
    first = True
    while True:
        try:
            state = _public_state(store, worker)
        except FileNotFoundError:
            state = {"worker": worker, "status": "not_started"}
        if first:
            _print_json({"state": state})
            if event_path.is_file():
                lines = event_path.read_text(encoding="utf-8").splitlines()
                selected = lines[-tail:] if tail else []
                for line in selected:
                    print(line)
                offset = event_path.stat().st_size
            first = False
        elif event_path.is_file():
            size = event_path.stat().st_size
            if size < offset:
                offset = 0
            with event_path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                for line in handle:
                    print(line.rstrip("\r\n"), flush=True)
                offset = handle.tell()
        if once:
            return
        time.sleep(0.5)


def _dashboard(
    store: AtomicStateStore,
    config: SupervisorConfig,
    *,
    watch: bool,
) -> None:
    while True:
        print(
            "Worker Branch                 Phase           Status"
            "                    Tests             Tokens  Cached"
        )
        for worker in SUPPORTED_WORKERS:
            try:
                state = _public_state(store, worker)
            except FileNotFoundError:
                state = {
                    "worker": worker,
                    "phase": "-",
                    "status": "not_started",
                    "tests_summary": "-",
                    "usage": {},
                }
            usage = state.get("usage") or {}
            tokens = (
                int(usage.get("input_tokens", 0))
                + int(usage.get("output_tokens", 0))
                + int(usage.get("reasoning_output_tokens", 0))
            )
            cached = int(usage.get("cached_input_tokens", 0))
            branch = config.workers[worker].branch
            print(
                f"{worker:<6} {branch:<22} "
                f"{str(state.get('phase') or '-'):<15} "
                f"{str(state.get('status') or '-'):<25} "
                f"{str(state.get('tests_summary') or '-'):<17} "
                f"{tokens:>7,} {cached:>7,}",
                flush=True,
            )
        if not watch:
            return
        print()
        time.sleep(1.0)


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _public_state(
    store: AtomicStateStore, worker: WorkerName
) -> dict[str, object]:
    state = store.read(worker)
    public = state.to_public_json()
    public["trusted_running"] = False
    if state.status != "running":
        public["process_liveness"] = "not_running"
        return public
    if state.pid is None or state.process_create_time is None:
        public["process_liveness"] = "untrusted_missing_pid"
        return public
    session_path = store.session_path(worker)
    if not session_path.is_file():
        public["process_liveness"] = "untrusted_missing_session"
        return public
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
        identity = ProcessIdentity.from_json(session["codex"])
        if identity.worker != worker or identity.pid != state.pid:
            raise RuntimeError("state/session worker or PID mismatch")
        if abs(identity.create_time - state.process_create_time) > 0.01:
            raise RuntimeError("state/session create time mismatch")
        inspect_owned_process(identity)
    except psutil.NoSuchProcess:
        public["process_liveness"] = "untrusted_process_missing"
        return public
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        public["process_liveness"] = "untrusted_identity_mismatch"
        return public
    public["trusted_running"] = True
    public["process_liveness"] = "alive_identity_verified"
    return public
