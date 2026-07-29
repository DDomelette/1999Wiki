from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from src.rag.tracing import RequestTrace


def test_parallel_spans_keep_thread_local_parents_and_coherent_snapshots():
    trace = RequestTrace()
    outer_ready = threading.Barrier(2)
    inner_ready = threading.Barrier(2)
    workers_done = threading.Event()
    snapshot_errors: list[BaseException] = []
    snapshots = []

    def worker(label: str) -> None:
        with trace.span(f"{label}.outer"):
            outer_ready.wait(timeout=1)
            with trace.span(f"{label}.inner"):
                trace.mark_model_first_token()
                inner_ready.wait(timeout=1)
                snapshots.append(trace.snapshot())
            trace.mark_validated_ready()

    def reader() -> None:
        try:
            while not workers_done.is_set():
                snapshot = trace.snapshot()
                assert all(span.duration_ms >= 0 for span in snapshot.spans)
                snapshots.append(snapshot)
        except BaseException as error:
            snapshot_errors.append(error)

    reader_thread = threading.Thread(target=reader)
    reader_thread.start()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(worker, label)
                for label in ("alpha", "beta")
            ]
            for future in futures:
                future.result(timeout=2)
    finally:
        workers_done.set()
        reader_thread.join(timeout=1)

    final = trace.snapshot()
    by_name = {span.name: span for span in final.spans}

    assert snapshot_errors == []
    assert set(by_name) == {
        "alpha.outer",
        "alpha.inner",
        "beta.outer",
        "beta.inner",
    }
    assert by_name["alpha.outer"].parent_name is None
    assert by_name["beta.outer"].parent_name is None
    assert by_name["alpha.inner"].parent_name == "alpha.outer"
    assert by_name["beta.inner"].parent_name == "beta.outer"
    assert final.model_first_token_ms is not None
    assert final.validated_ready_ms is not None
    assert snapshots


def test_parallel_mark_once_reads_the_clock_exactly_once():
    class SlowClock:
        def __init__(self) -> None:
            self.calls = 0
            self.lock = threading.Lock()

        def __call__(self) -> int:
            with self.lock:
                self.calls += 1
                value = self.calls
            if value > 1:
                time.sleep(0.02)
            return value * 1_000_000

    clock = SlowClock()
    trace = RequestTrace(clock_ns=clock)
    ready = threading.Barrier(4)

    def mark() -> None:
        ready.wait(timeout=1)
        trace.mark_completed()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(mark) for _index in range(4)]
        for future in futures:
            future.result(timeout=2)

    first = trace.snapshot()
    second = trace.snapshot()

    assert clock.calls == 2
    assert first.completed_ms == second.completed_ms == 1.0
