"""Local, redacted tracing for one RAG request execution."""
from __future__ import annotations

import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Iterator, Literal, Mapping


TraceStatus = Literal["ok", "error"]

_TRACE_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")
_ALLOWED_ATTRIBUTES = frozenset(
    {
        "candidate_k",
        "chars_used",
        "coverage_shortfall_count",
        "effective_route",
        "intent_count",
        "invalid_citation_count",
        "max_sources",
        "media_count",
        "missing_owner_metadata",
        "normalized_citation_count",
        "owner_after",
        "owner_before",
        "owner_mismatch",
        "proposed_route",
        "repair_attempts",
        "required_source_count",
        "result_count",
        "retrieval_outcome",
        "route_reason",
        "source_count",
        "stage",
        "status",
        "used_citation_count",
        "warning",
    }
)
_TOKEN_ATTRIBUTES = frozenset(
    {
        "effective_route",
        "proposed_route",
        "retrieval_outcome",
        "route_reason",
        "stage",
        "status",
        "warning",
    }
)


def safe_trace_attributes(attributes: Mapping[str, object]) -> Mapping[str, object]:
    """Validate trace metadata so prompts, paths, and payloads cannot leak."""
    unknown = sorted(set(attributes) - _ALLOWED_ATTRIBUTES)
    if unknown:
        raise ValueError(f"trace attribute is not allow-listed: {unknown[0]}")
    for key, value in attributes.items():
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"trace attribute {key!r} must be a scalar")
        if key in _TOKEN_ATTRIBUTES:
            if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value):
                raise ValueError(f"trace attribute {key!r} must be a safe token")
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"trace attribute {key!r} must be a non-negative integer")
    return MappingProxyType(dict(attributes))


@dataclass(frozen=True)
class StageSpan:
    name: str
    parent_name: str | None
    start_offset_ms: float
    duration_ms: float
    status: TraceStatus
    attributes: Mapping[str, object]
    error_class: str = ""

    @property
    def end_offset_ms(self) -> float:
        return self.start_offset_ms + self.duration_ms


@dataclass(frozen=True)
class TraceSnapshot:
    spans: tuple[StageSpan, ...] = ()
    model_first_token_ms: float | None = None
    validated_ready_ms: float | None = None
    visible_first_token_ms: float | None = None
    completed_ms: float | None = None
    warning: str = ""


class RequestTrace:
    """Collect monotonic stage spans without requiring an external collector."""

    def __init__(self, *, clock_ns: Callable[[], int] = time.perf_counter_ns) -> None:
        self._clock_ns = clock_ns
        self._origin_ns = clock_ns()
        self._spans: list[StageSpan] = []
        self._local = threading.local()
        self._lock = threading.RLock()
        self._marks: dict[str, float] = {}

    @contextmanager
    def span(self, name: str, **attributes: object) -> Iterator[None]:
        if not _TRACE_NAME.fullmatch(name):
            raise ValueError("trace span name is invalid")
        safe = safe_trace_attributes(attributes)
        parents = self._parent_stack()
        parent_name = parents[-1] if parents else None
        started = self._clock_ns()
        status: TraceStatus = "ok"
        error_class = ""
        parents.append(name)
        try:
            yield
        except Exception as error:
            status = "error"
            error_class = type(error).__name__
            raise
        finally:
            parents.pop()
            finished = self._clock_ns()
            with self._lock:
                self._spans.append(
                    StageSpan(
                        name=name,
                        parent_name=parent_name,
                        start_offset_ms=self._milliseconds(started - self._origin_ns),
                        duration_ms=self._milliseconds(max(0, finished - started)),
                        status=status,
                        attributes=safe,
                        error_class=error_class,
                    )
                )

    def mark_model_first_token(self) -> None:
        self._mark_once("model_first_token_ms")

    def mark_validated_ready(self) -> None:
        self._mark_once("validated_ready_ms")

    def mark_visible_first_token(self) -> None:
        self._mark_once("visible_first_token_ms")

    def mark_completed(self) -> None:
        self._mark_once("completed_ms")

    def snapshot(self) -> TraceSnapshot:
        with self._lock:
            return TraceSnapshot(spans=tuple(self._spans), **dict(self._marks))

    def _mark_once(self, name: str) -> None:
        with self._lock:
            if name not in self._marks:
                self._marks[name] = self._milliseconds(
                    self._clock_ns() - self._origin_ns
                )

    def _parent_stack(self) -> list[str]:
        parents = getattr(self._local, "parents", None)
        if parents is None:
            parents = []
            self._local.parents = parents
        return parents

    @staticmethod
    def _milliseconds(nanoseconds: int) -> float:
        return nanoseconds / 1_000_000


class NullTrace:
    """No-op trace used when instrumentation initialization is unavailable."""

    def __init__(self, *, warning: str = "") -> None:
        self._warning = warning

    @contextmanager
    def span(self, name: str, **attributes: object) -> Iterator[None]:
        del name, attributes
        yield

    def mark_model_first_token(self) -> None:
        return None

    def mark_validated_ready(self) -> None:
        return None

    def mark_visible_first_token(self) -> None:
        return None

    def mark_completed(self) -> None:
        return None

    def snapshot(self) -> TraceSnapshot:
        return TraceSnapshot(warning=self._warning)


def make_request_trace() -> RequestTrace | NullTrace:
    try:
        return RequestTrace()
    except Exception:
        return NullTrace(warning="instrumentation_unavailable")


def trace_snapshot_to_public(snapshot: TraceSnapshot) -> dict[str, object]:
    stage_ms: dict[str, float] = {}
    error_stages: list[str] = []
    for span in snapshot.spans:
        stage_ms[span.name] = stage_ms.get(span.name, 0.0) + span.duration_ms
        if span.status == "error" and span.name not in error_stages:
            error_stages.append(span.name)
    return {
        "model_first_token_ms": snapshot.model_first_token_ms,
        "validated_ready_ms": snapshot.validated_ready_ms,
        "visible_first_token_ms": snapshot.visible_first_token_ms,
        "completed_ms": snapshot.completed_ms,
        "stage_ms": stage_ms,
        "error_stages": error_stages,
        "warning": snapshot.warning,
    }


__all__ = [
    "NullTrace",
    "RequestTrace",
    "StageSpan",
    "TraceSnapshot",
    "make_request_trace",
    "safe_trace_attributes",
    "trace_snapshot_to_public",
]
