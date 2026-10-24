from pathlib import Path

import pytest

from src.codex_supervisor.contracts import (
    SUPPORTED_WORKERS,
    UsageTotals,
    WorkerState,
    build_codex_base_args,
    load_supervisor_config,
    supported_workers_json,
    validate_worker_name,
)


def test_worker_config_enforces_two_layers_and_standard_speed() -> None:
    config = load_supervisor_config(Path.cwd())
    worker = config.workers["A"]
    args = build_codex_base_args(
        worker,
        Path("scripts/codex-supervisor/schemas/worker-final.schema.json"),
    )

    assert args[:2] == ("codex", "exec")
    assert ("-m", "gpt-5.6-sol") == args[2:4]
    assert "--disable" in args
    assert "fast_mode" in args
    assert "multi_agent" in args
    assert ("--sandbox", "workspace-write") in tuple(zip(args, args[1:]))
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    assert worker.allow_subagents is False
    assert config.python_environment == "1999wiki"


def test_worker_registry_is_the_only_exact_abce_source() -> None:
    assert SUPPORTED_WORKERS == ("A", "B", "C", "E")
    assert supported_workers_json() == {
        "schema_version": "codex-supervisor-workers/v1",
        "workers": ["A", "B", "C", "E"],
    }
    assert validate_worker_name("E") == "E"
    with pytest.raises(ValueError, match="unsupported worker name"):
        validate_worker_name("D")


def test_worker_state_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unsupported worker status"):
        WorkerState.initial("A").with_status("invented")


def test_usage_totals_accumulate_cached_and_reasoning_tokens() -> None:
    usage = UsageTotals().add(
        input_tokens=100,
        cached_input_tokens=60,
        output_tokens=20,
        reasoning_output_tokens=8,
    )
    assert usage.to_json() == {
        "input_tokens": 100,
        "cached_input_tokens": 60,
        "output_tokens": 20,
        "reasoning_output_tokens": 8,
    }


def test_all_workers_use_distinct_branches_and_worktrees() -> None:
    config = load_supervisor_config(Path.cwd())
    assert set(config.workers) == {"A", "B", "C", "E"}
    assert len({worker.branch for worker in config.workers.values()}) == 4
    assert len({worker.worktree for worker in config.workers.values()}) == 4
    assert config.workers["E"].branch == "codex/rag-e-story-segment"
    assert config.workers["E"].worktree.name == "rag-e-story-segment"
    assert config.workers["E"].reasoning_effort == "high"


def test_worker_state_json_round_trip() -> None:
    state = WorkerState.initial("B").with_status("planning")
    assert WorkerState.from_json(state.to_json()) == state


def test_v1_config_is_rejected_without_rewriting_existing_state(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    config_dir = project / "config"
    config_dir.mkdir(parents=True)
    state = project / ".codex-supervisor" / "workers" / "A" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_bytes(b'{"legacy":"preserve-exactly"}\n')
    payload = {
        "schema_version": "codex-supervisor/v1",
        "runtime_root": ".codex-supervisor",
        "python_environment": "1999wiki",
        "model": "gpt-5.6-sol",
        "sandbox": "workspace-write",
        "fast_mode": False,
        "multi_agent": False,
        "workers": {},
    }
    (config_dir / "codex-supervisor.workers.json").write_text(
        __import__("json").dumps(payload), encoding="utf-8"
    )
    before = state.read_bytes()
    with pytest.raises(ValueError, match="unsupported supervisor config schema"):
        load_supervisor_config(project)
    assert state.read_bytes() == before


def test_v2_config_load_preserves_existing_abc_state_bytes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    config_dir = project / "config"
    config_dir.mkdir(parents=True)
    source = Path("config/codex-supervisor.workers.json").read_text(
        encoding="utf-8"
    )
    (config_dir / "codex-supervisor.workers.json").write_text(
        source.replace("../1999Wiki.worktrees", "worktrees"),
        encoding="utf-8",
    )
    states: dict[str, tuple[Path, bytes]] = {}
    for worker in ("A", "B", "C"):
        path = (
            project
            / ".codex-supervisor"
            / "workers"
            / worker
            / "state.json"
        )
        path.parent.mkdir(parents=True)
        raw = (f'{{"worker":"{worker}","legacy":true}}\n').encode()
        path.write_bytes(raw)
        states[worker] = (path, raw)
    load_supervisor_config(project)
    assert all(path.read_bytes() == raw for path, raw in states.values())
