from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.codex_supervisor.contracts import WorkerState
from src.codex_supervisor.events import apply_event
from src.codex_supervisor.state_store import AtomicStateStore


FIXTURES = Path(__file__).parent / "fixtures" / "codex_supervisor"


def reduce_fixture(worker: str, filename: str) -> WorkerState:
    state = WorkerState.initial(worker)  # type: ignore[arg-type]
    for ordinal, line in enumerate(
        (FIXTURES / filename).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        event = json.loads(line)
        event["_supervisor_event_ordinal"] = ordinal
        state = apply_event(state, event)
    return state


def test_success_events_capture_session_action_test_and_usage() -> None:
    state = reduce_fixture("A", "events-success.jsonl")
    assert state.session_id == "thread-a"
    assert state.current_action == "python -m pytest tests/test_x.py -q"
    assert state.tests_summary == "2 passed"
    assert state.usage.cached_input_tokens == 700
    assert state.status == "completed_pending_review"


def test_failure_event_preserves_public_error_without_traceback() -> None:
    state = reduce_fixture("C", "events-failure.jsonl")
    assert state.status == "failed"
    assert state.blocker == "source snapshot missing"
    assert "Traceback" not in json.dumps(state.to_public_json())


def test_replayed_usage_event_is_not_counted_twice() -> None:
    state = WorkerState.initial("A")
    event = {
        "type": "turn.completed",
        "usage": {"input_tokens": 10, "output_tokens": 3},
        "_supervisor_event_ordinal": 4,
    }
    once = apply_event(state, event)
    twice = apply_event(once, event)
    assert twice.usage == once.usage


def test_unknown_event_does_not_fail_reducer() -> None:
    state = WorkerState.initial("B")
    event = {"type": "future.event", "_supervisor_event_ordinal": 1}
    assert apply_event(state, event).last_event_ordinal == 1


def test_atomic_state_store_round_trips_and_separates_workers(
    tmp_path: Path,
) -> None:
    store = AtomicStateStore(tmp_path)
    store.write(WorkerState.initial("A").with_status("running"))
    store.write(WorkerState.initial("B").with_status("blocked"))

    assert store.read("A").status == "running"
    assert store.read("B").status == "blocked"
    assert store.state_path("A") != store.state_path("B")


def test_atomic_state_store_missing_state_is_explicit(tmp_path: Path) -> None:
    store = AtomicStateStore(tmp_path)
    with pytest.raises(FileNotFoundError, match="worker A state"):
        store.read("A")


def test_failed_serialization_preserves_existing_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = AtomicStateStore(tmp_path)
    original = WorkerState.initial("C").with_status("running")
    store.write(original)

    def fail_dump(*args: object, **kwargs: object) -> None:
        raise TypeError("synthetic serialization failure")

    monkeypatch.setattr("src.codex_supervisor.state_store.json.dump", fail_dump)
    with pytest.raises(TypeError, match="synthetic"):
        store.write(original.with_status("failed"))
    assert store.read("C") == original


def test_raw_events_and_public_state_use_separate_paths(
    tmp_path: Path,
) -> None:
    store = AtomicStateStore(tmp_path)
    store.write(WorkerState.initial("A"))
    store.append_event("A", '{"type":"turn.started"}')

    assert store.state_path("A").read_text(encoding="utf-8")
    assert store.event_log_path("A").read_text(encoding="utf-8") == (
        '{"type":"turn.started"}\n'
    )
