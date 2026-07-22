from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.rag.tracing import (
    NullTrace,
    RequestTrace,
    safe_trace_attributes,
    trace_snapshot_to_public,
)


def _sequence_clock(*values: int):
    remaining: Iterator[int] = iter(values)
    return lambda: next(remaining)


def test_request_trace_closes_failed_span_and_uses_monotonic_duration():
    trace = RequestTrace(clock_ns=_sequence_clock(100, 200, 350))

    with pytest.raises(RuntimeError, match="boom"):
        with trace.span("planner.llm"):
            raise RuntimeError("boom")

    span = trace.snapshot().spans[0]
    assert span.status == "error"
    assert span.start_offset_ms == pytest.approx(0.0001)
    assert span.duration_ms == pytest.approx(0.00015)
    assert span.error_class == "RuntimeError"


def test_request_trace_records_parent_and_safe_count_attributes():
    trace = RequestTrace(clock_ns=_sequence_clock(100, 200, 250, 300, 400))

    with trace.span("retrieve", candidate_k=20):
        with trace.span("retrieve.dense", result_count=8):
            pass

    snapshot = trace.snapshot()
    assert snapshot.spans[0].name == "retrieve.dense"
    assert snapshot.spans[0].parent_name == "retrieve"
    assert snapshot.spans[0].attributes["result_count"] == 8
    assert snapshot.spans[1].parent_name is None


def test_trace_rejects_sensitive_or_free_text_attributes():
    with pytest.raises(ValueError, match="attribute"):
        safe_trace_attributes({"question": "real user question"})
    with pytest.raises(ValueError, match="attribute"):
        safe_trace_attributes({"local_path": r"D:\secret"})
    with pytest.raises(ValueError, match="scalar"):
        safe_trace_attributes({"candidate_k": {"unsafe": 1}})
    with pytest.raises(ValueError, match="token"):
        safe_trace_attributes({"route_reason": "contains copied user text"})
    with pytest.raises(ValueError, match="non-negative integer"):
        safe_trace_attributes({"source_count": -1})


def test_trace_marks_lifecycle_only_once():
    trace = RequestTrace(clock_ns=_sequence_clock(100, 200, 250, 300, 350, 400))

    trace.mark_model_first_token()
    trace.mark_model_first_token()
    trace.mark_validated_ready()
    trace.mark_visible_first_token()
    trace.mark_completed()

    snapshot = trace.snapshot()
    assert snapshot.model_first_token_ms == pytest.approx(0.0001)
    assert snapshot.validated_ready_ms == pytest.approx(0.00015)
    assert snapshot.visible_first_token_ms == pytest.approx(0.0002)
    assert snapshot.completed_ms == pytest.approx(0.00025)


def test_null_trace_is_a_noop_with_the_same_interface():
    trace = NullTrace(warning="instrumentation_unavailable")

    with trace.span("retrieve", candidate_k=20):
        trace.mark_model_first_token()
        trace.mark_completed()

    snapshot = trace.snapshot()
    assert snapshot.spans == ()
    assert snapshot.warning == "instrumentation_unavailable"


def test_public_trace_projection_contains_only_stage_timing_and_status():
    trace = RequestTrace()
    with trace.span("answer.llm", source_count=1):
        pass
    trace.mark_model_first_token()
    trace.mark_validated_ready()
    trace.mark_visible_first_token()
    trace.mark_completed()

    public = trace_snapshot_to_public(trace.snapshot())
    serialized = repr(public).lower()

    assert public["stage_ms"]["answer.llm"] >= 0
    assert "question" not in serialized
    assert "answer" not in serialized.replace("answer.llm", "")
    assert "context" not in serialized
