from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from backend import main as main_mod
from src.huiji_rag.provenance import VerificationIssue, VerificationResult
from src.rag.conversation import ConversationMemoryStore


def _result(status: str, code: str = "") -> VerificationResult:
    issues = (VerificationIssue(code, "runtime"),) if code else ()
    return VerificationResult(
        status=status,
        issues=issues,
        baseline_sha256="a" * 64,
        evidence_relpath="eval/huiji_provenance/run/runtime.v1.json",
    )


def _reset_state() -> None:
    main_mod._state = {
        "vs": None,
        "retriever": None,
        "chain": None,
        "memory": ConversationMemoryStore(),
        "loaded": False,
        "provenance_checked": False,
        "provenance": None,
    }


@contextmanager
def _isolated_state():
    previous = main_mod._state
    try:
        _reset_state()
        yield
    finally:
        main_mod._state = previous


def test_blocked_provenance_never_constructs_rag(monkeypatch):
    with _isolated_state():
        monkeypatch.setattr(
            main_mod,
            "verify_runtime",
            lambda _cfg: _result("blocked", "artifact_hash_mismatch"),
            raising=False,
        )
        monkeypatch.setattr(
            main_mod,
            "load_vectorstore",
            lambda _cfg: pytest.fail("vectorstore loaded"),
        )

        main_mod._ensure_loaded()

        assert main_mod._state["loaded"] is False
        assert main_mod._state["vs"] is None
        assert main_mod._state["retriever"] is None
        assert main_mod._state["chain"] is None


def test_verifier_exception_fails_closed_before_rag(monkeypatch):
    with _isolated_state():
        monkeypatch.setattr(
            main_mod,
            "verify_runtime",
            lambda _cfg: (_ for _ in ()).throw(RuntimeError(r"D:\private\secret")),
            raising=False,
        )
        monkeypatch.setattr(
            main_mod,
            "load_vectorstore",
            lambda _cfg: pytest.fail("vectorstore loaded"),
        )

        main_mod._ensure_loaded()

        result = main_mod._state["provenance"]
        assert result.status == "error"
        assert [issue.code for issue in result.issues] == ["verification_internal_error"]
        assert main_mod._state["loaded"] is False


def test_allowed_provenance_and_rag_constructors_run_once(monkeypatch):
    calls = {"verify": 0, "vectorstore": 0, "retriever": 0, "chain": 0}
    vectorstore = object()
    retriever = object()
    chain = object()

    def verify(_cfg):
        calls["verify"] += 1
        return _result("pass")

    def load(_cfg):
        calls["vectorstore"] += 1
        return vectorstore

    def make_retriever(_cfg, value):
        calls["retriever"] += 1
        assert value is vectorstore
        return retriever

    def make_chain(_cfg, value):
        calls["chain"] += 1
        assert value is retriever
        return chain

    with _isolated_state():
        monkeypatch.setattr(main_mod, "verify_runtime", verify, raising=False)
        monkeypatch.setattr(main_mod, "load_vectorstore", load)
        monkeypatch.setattr(main_mod, "Retriever", make_retriever)
        monkeypatch.setattr(main_mod, "RAGChain", make_chain)

        main_mod._ensure_loaded()
        main_mod._ensure_loaded()

        assert calls == {"verify": 1, "vectorstore": 1, "retriever": 1, "chain": 1}
        assert main_mod._state["loaded"] is True


def test_blocked_health_is_safe_and_rag_endpoints_return_503(monkeypatch):
    with _isolated_state():
        monkeypatch.setattr(
            main_mod,
            "verify_runtime",
            lambda _cfg: _result("blocked", "artifact_hash_mismatch"),
            raising=False,
        )
        monkeypatch.setattr(
            main_mod,
            "load_vectorstore",
            lambda _cfg: pytest.fail("vectorstore loaded"),
        )
        with TestClient(main_mod.app) as client:
            health = client.get("/health")
            ask = client.post("/ask", json={"question": "generic"})
            stream = client.post("/ask/stream", json={"question": "generic"})
            voice = client.get("/api/media/voice/page", params={"cursor": "invalid"})

        assert health.status_code == 200
        payload = health.json()
        assert payload["status"] == "error"
        assert payload["vectorstore_loaded"] is False
        assert payload["provenance_status"] == "blocked"
        assert payload["provenance_errors"] == ["artifact_hash_mismatch"]
        assert payload["provenance_evidence"] == "eval/huiji_provenance/run/runtime.v1.json"
        serialized = health.text
        assert "D:\\" not in serialized
        assert "secret" not in serialized.lower()
        assert ask.status_code == 503
        assert stream.status_code == 503
        assert voice.status_code == 503
