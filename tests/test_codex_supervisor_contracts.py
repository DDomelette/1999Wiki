from pathlib import Path

import pytest

from src.codex_supervisor.contracts import (
    UsageTotals,
    WorkerState,
    build_codex_base_args,
    load_supervisor_config,
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
    assert set(config.workers) == {"A", "B", "C"}
    assert len({worker.branch for worker in config.workers.values()}) == 3
    assert len({worker.worktree for worker in config.workers.values()}) == 3


def test_worker_state_json_round_trip() -> None:
    state = WorkerState.initial("B").with_status("planning")
    assert WorkerState.from_json(state.to_json()) == state
