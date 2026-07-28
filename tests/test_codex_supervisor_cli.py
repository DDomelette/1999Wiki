from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from src.codex_supervisor.cli import build_resume_args, main
from src.codex_supervisor.contracts import (
    WorkerState,
    load_supervisor_config,
)
from src.codex_supervisor.state_store import AtomicStateStore


def invoke_cli(
    argv: list[str],
    *,
    project_root: Path | None = None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(argv, project_root=project_root or Path.cwd())
    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_start_rejects_unapproved_prompt_path(tmp_path: Path) -> None:
    exit_code, _, stderr = invoke_cli(
        [
            "start",
            "--worker",
            "A",
            "--task-file",
            str(tmp_path / "free.txt"),
        ]
    )
    assert exit_code == 2
    assert "approved-task.md" in stderr


def test_resume_uses_recorded_session_and_standard_flags() -> None:
    config = load_supervisor_config(Path.cwd())
    argv = build_resume_args(
        config=config.workers["A"],
        session_id="thread-a",
        prompt="继续已批准的计划修订",
        final_schema=Path(
            "scripts/codex-supervisor/schemas/worker-final.schema.json"
        ),
    )
    assert argv[:3] == ("codex", "exec", "resume")
    assert "thread-a" in argv
    assert ("-m", "gpt-5.6-sol") in tuple(zip(argv, argv[1:]))
    assert "--disable" in argv
    assert "multi_agent" in argv
    assert 'sandbox_mode="workspace-write"' in argv


def test_resume_requires_recorded_session(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    task = _approved_task(project, "A", "approved-resume.md")
    store = AtomicStateStore(project / ".codex-supervisor")
    store.write(WorkerState.initial("A").with_status("failed"))

    exit_code, _, stderr = invoke_cli(
        [
            "resume",
            "--worker",
            "A",
            "--task-file",
            str(task),
        ],
        project_root=project,
    )
    assert exit_code == 2
    assert "session ID" in stderr


def test_accept_only_allows_completed_pending_review(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    store = AtomicStateStore(project / ".codex-supervisor")
    store.write(WorkerState.initial("B").with_status("running"))
    exit_code, _, stderr = invoke_cli(
        ["accept", "--worker", "B"],
        project_root=project,
    )
    assert exit_code == 2
    assert "completed_pending_review" in stderr

    store.write(
        WorkerState.initial("B").with_status("completed_pending_review")
    )
    exit_code, stdout, _ = invoke_cli(
        ["accept", "--worker", "B"],
        project_root=project,
    )
    assert exit_code == 0
    assert json.loads(stdout)["status"] == "accepted"


def test_task_file_requires_scope_and_no_subagents(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    task = (
        project
        / ".codex-supervisor"
        / "workers"
        / "C"
        / "approved-task.md"
    )
    task.parent.mkdir(parents=True)
    task.write_text("Spec: x\nPlan: y\n", encoding="utf-8")
    exit_code, _, stderr = invoke_cli(
        [
            "start",
            "--worker",
            "C",
            "--task-file",
            str(task),
        ],
        project_root=project,
    )
    assert exit_code == 2
    assert "Allowed files" in stderr


def test_dashboard_uses_fixed_worker_order_and_missing_marker(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    store = AtomicStateStore(project / ".codex-supervisor")
    store.write(WorkerState.initial("B").with_status("blocked"))
    exit_code, stdout, _ = invoke_cli(
        ["dashboard"],
        project_root=project,
    )
    assert exit_code == 0
    rows = json.loads(stdout)["workers"]
    assert [row["worker"] for row in rows] == ["A", "B", "C"]
    assert [row["status"] for row in rows] == [
        "not_started",
        "blocked",
        "not_started",
    ]


def test_watch_once_prints_state_and_event_history(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    store = AtomicStateStore(project / ".codex-supervisor")
    store.write(WorkerState.initial("A").with_status("running"))
    store.append_event("A", '{"type":"thread.started","thread_id":"x"}')
    exit_code, stdout, _ = invoke_cli(
        ["watch", "--worker", "A", "--tail", "5", "--once"],
        project_root=project,
    )
    assert exit_code == 0
    assert '"status": "running"' in stdout
    assert "thread.started" in stdout


def _project_fixture(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    source = (
        Path.cwd() / "config" / "codex-supervisor.workers.json"
    ).read_text(encoding="utf-8")
    (project / "config" / "codex-supervisor.workers.json").write_text(
        source.replace("../1999Wiki.worktrees", "worktrees"),
        encoding="utf-8",
    )
    schema = (
        project
        / "scripts"
        / "codex-supervisor"
        / "schemas"
        / "worker-final.schema.json"
    )
    schema.parent.mkdir(parents=True)
    schema.write_text("{}", encoding="utf-8")
    return project


def _approved_task(
    project: Path,
    worker: str,
    filename: str = "approved-task.md",
) -> Path:
    task = (
        project
        / ".codex-supervisor"
        / "workers"
        / worker
        / filename
    )
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(
        "\n".join(
            (
                "Spec: docs/spec.md",
                "Plan: docs/plan.md",
                "Allowed files:",
                "- docs/plan.md",
                "Subagents: forbidden",
            )
        ),
        encoding="utf-8",
    )
    return task
