from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Mapping, TypeAlias


WorkerName: TypeAlias = Literal["A", "B", "C"]


class WorkerPhase(StrEnum):
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"


class WorkerStatus(StrEnum):
    PLANNING = "planning"
    AWAITING_PLAN_REVIEW = "awaiting_plan_review"
    APPROVED = "approved"
    RUNNING = "running"
    TESTING = "testing"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED_PENDING_REVIEW = "completed_pending_review"
    ACCEPTED = "accepted"


ALLOWED_STATUSES = tuple(status.value for status in WorkerStatus)


@dataclass(frozen=True)
class UsageTotals:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0

    def add(
        self,
        *,
        input_tokens: int = 0,
        cached_input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_output_tokens: int = 0,
    ) -> UsageTotals:
        return UsageTotals(
            input_tokens=self.input_tokens + int(input_tokens),
            cached_input_tokens=self.cached_input_tokens
            + int(cached_input_tokens),
            output_tokens=self.output_tokens + int(output_tokens),
            reasoning_output_tokens=self.reasoning_output_tokens
            + int(reasoning_output_tokens),
        )

    def to_json(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> UsageTotals:
        return cls(
            input_tokens=int(value.get("input_tokens", 0)),
            cached_input_tokens=int(value.get("cached_input_tokens", 0)),
            output_tokens=int(value.get("output_tokens", 0)),
            reasoning_output_tokens=int(value.get("reasoning_output_tokens", 0)),
        )


@dataclass(frozen=True)
class WorkerConfig:
    name: WorkerName
    branch: str
    worktree: Path
    model: str
    sandbox: str
    fast_mode: bool
    multi_agent: bool
    allow_subagents: bool = False


@dataclass(frozen=True)
class SupervisorConfig:
    schema_version: str
    project_root: Path
    runtime_root: Path
    python_environment: str
    workers: Mapping[WorkerName, WorkerConfig]


@dataclass(frozen=True)
class WorkerState:
    worker: WorkerName
    status: str = WorkerStatus.PLANNING.value
    phase: str = WorkerPhase.PLANNING.value
    session_id: str | None = None
    pid: int | None = None
    process_create_time: float | None = None
    command_fingerprint: str | None = None
    current_action: str | None = None
    tests_summary: str | None = None
    summary: str | None = None
    blocker: str | None = None
    last_error: str | None = None
    last_event_key: str | None = None
    last_event_ordinal: int = 0
    last_exit_code: int | None = None
    usage: UsageTotals = field(default_factory=UsageTotals)

    @classmethod
    def initial(cls, worker: WorkerName) -> WorkerState:
        if worker not in ("A", "B", "C"):
            raise ValueError(f"unsupported worker name: {worker}")
        return cls(worker=worker)

    def with_status(self, status: str | WorkerStatus) -> WorkerState:
        value = status.value if isinstance(status, WorkerStatus) else str(status)
        if value not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported worker status: {value}")
        return replace(self, status=value)

    def to_json(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "status": self.status,
            "phase": self.phase,
            "session_id": self.session_id,
            "pid": self.pid,
            "process_create_time": self.process_create_time,
            "command_fingerprint": self.command_fingerprint,
            "current_action": self.current_action,
            "tests_summary": self.tests_summary,
            "summary": self.summary,
            "blocker": self.blocker,
            "last_error": self.last_error,
            "last_event_key": self.last_event_key,
            "last_event_ordinal": self.last_event_ordinal,
            "last_exit_code": self.last_exit_code,
            "usage": self.usage.to_json(),
        }

    def to_public_json(self) -> dict[str, Any]:
        return self.to_json()

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> WorkerState:
        worker = str(value["worker"])
        state = cls.initial(worker)  # type: ignore[arg-type]
        status = str(value.get("status", WorkerStatus.PLANNING.value))
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported worker status: {status}")
        return cls(
            worker=state.worker,
            status=status,
            phase=str(value.get("phase", WorkerPhase.PLANNING.value)),
            session_id=_optional_str(value.get("session_id")),
            pid=_optional_int(value.get("pid")),
            process_create_time=_optional_float(
                value.get("process_create_time")
            ),
            command_fingerprint=_optional_str(
                value.get("command_fingerprint")
            ),
            current_action=_optional_str(value.get("current_action")),
            tests_summary=_optional_str(value.get("tests_summary")),
            summary=_optional_str(value.get("summary")),
            blocker=_optional_str(value.get("blocker")),
            last_error=_optional_str(value.get("last_error")),
            last_event_key=_optional_str(value.get("last_event_key")),
            last_event_ordinal=int(value.get("last_event_ordinal", 0)),
            last_exit_code=_optional_int(value.get("last_exit_code")),
            usage=UsageTotals.from_json(value.get("usage", {})),
        )


def load_supervisor_config(project_root: Path) -> SupervisorConfig:
    root = project_root.resolve()
    path = root / "config" / "codex-supervisor.workers.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "codex-supervisor/v1":
        raise ValueError("unsupported supervisor config schema")

    model = str(payload["model"])
    sandbox = str(payload["sandbox"])
    fast_mode = bool(payload["fast_mode"])
    multi_agent = bool(payload["multi_agent"])
    workers: dict[WorkerName, WorkerConfig] = {}
    for raw_name, raw_worker in payload["workers"].items():
        if raw_name not in ("A", "B", "C"):
            raise ValueError(f"unsupported worker name: {raw_name}")
        name: WorkerName = raw_name
        worktree = (root / str(raw_worker["worktree"])).resolve()
        workers[name] = WorkerConfig(
            name=name,
            branch=str(raw_worker["branch"]),
            worktree=worktree,
            model=model,
            sandbox=sandbox,
            fast_mode=fast_mode,
            multi_agent=multi_agent,
            allow_subagents=False,
        )

    if set(workers) != {"A", "B", "C"}:
        raise ValueError("supervisor config must define workers A, B, and C")
    if fast_mode or multi_agent:
        raise ValueError("supervised workers require standard speed and two layers")
    return SupervisorConfig(
        schema_version=str(payload["schema_version"]),
        project_root=root,
        runtime_root=(root / str(payload["runtime_root"])).resolve(),
        python_environment=str(payload["python_environment"]),
        workers=workers,
    )


def build_codex_base_args(
    config: WorkerConfig, final_schema: Path
) -> tuple[str, ...]:
    args = (
        "codex",
        "exec",
        "-m",
        config.model,
        "--disable",
        "fast_mode",
        "--disable",
        "multi_agent",
        "--sandbox",
        config.sandbox,
        "--json",
        "--output-schema",
        str(final_schema.resolve()),
        "--cd",
        str(config.worktree),
    )
    if config.allow_subagents:
        raise ValueError("supervised workers may not create subagents")
    return args


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
