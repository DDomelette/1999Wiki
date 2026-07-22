from __future__ import annotations

from src.rag_eval.isolated import run_isolated_route_failure_probe


def test_isolated_failure_probe_uses_real_sync_and_sse_endpoints():
    evidence = run_isolated_route_failure_probe()

    assert evidence["schema_version"] == "rag_eval.isolated_route_failure/v1"
    assert evidence["probe"] == "deterministic_failing_retriever"
    assert evidence["production_fault_injection"] is False
    assert evidence["passed"] is True
    for transport in ("sync", "sse"):
        observed = evidence[transport]
        assert observed["status_code"] == 200
        assert observed["retrieval_outcome"] == "failed"
        assert observed["effective_route"] == "rag_grounded"
        assert observed["route_reason"] == "retrieval_failed"
        assert observed["source_count"] == 0
        assert observed["grounding_mode"] == "none"
        assert observed["llm_invoked"] is False
