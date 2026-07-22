"""Isolated endpoint probes used by the trust evaluation evidence bundle."""
from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Mapping
from uuid import uuid4

from fastapi.testclient import TestClient

from src.rag.chain import RAGChain
from src.rag.conversation import ConversationMemoryStore
from src.rag.retriever import RetrievalExecutionError


class _FailingRetriever:
    last_omitted_actions: list[dict[str, Any]] = []
    last_route_debug: dict[str, Any] = {}

    def __init__(self) -> None:
        self.search_calls = 0

    def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_calls += 1
        raise RetrievalExecutionError("retrieval.dense", "IsolatedProbeError")


class _ProbePlanner:
    def plan(self, question: str, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            original_query=question,
            normalized_query=question,
            intent="general_game",
            entity=None,
            entity_type="",
            route="rag_grounded",
            route_options={},
            packet_policy="default",
            confidence=1.0,
            planning_status="deterministic_probe",
            planning_warning="",
            planning_error="",
            secondary_intents=(),
        )


class _ProbeLLM:
    def __init__(self) -> None:
        self.invoked = False

    def invoke(self, messages: object) -> object:
        self.invoked = True
        raise AssertionError("retrieval failure must not invoke the answer model")


def _parse_sse(text: str) -> dict[str, Mapping[str, Any]]:
    events: dict[str, Mapping[str, Any]] = {}
    for block in text.split("\n\n"):
        event = ""
        data: Mapping[str, Any] = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event:
            events[event] = data
    return events


def _observation(
    payload: Mapping[str, Any],
    *,
    status_code: int,
    llm_invoked: bool,
) -> dict[str, Any]:
    route = payload.get("route") or {}
    sources = payload.get("sources") or []
    return {
        "status_code": status_code,
        "retrieval_outcome": route.get("retrieval_outcome"),
        "effective_route": route.get("effective_route"),
        "route_reason": route.get("route_reason"),
        "source_count": len(sources),
        "grounding_mode": payload.get("grounding_mode"),
        "llm_invoked": llm_invoked,
    }


def run_isolated_route_failure_probe() -> dict[str, Any]:
    """Exercise both real HTTP handlers with an isolated failing Retriever."""
    from backend import main as main_module

    retriever = _FailingRetriever()
    llm = _ProbeLLM()
    cfg = replace(main_module.cfg, llm=replace(main_module.cfg.llm, api_key=""))
    chain = RAGChain(cfg, retriever)
    chain._query_planner = _ProbePlanner()
    chain._llm = llm

    previous_state = main_module._state
    previous_loader = main_module._ensure_loaded
    main_module._state = {
        "vs": None,
        "retriever": retriever,
        "chain": chain,
        "memory": ConversationMemoryStore(),
        "loaded": True,
    }
    main_module._ensure_loaded = lambda: None
    question = "isolated retrieval failure route probe"
    options = {"free_supplement": True}
    try:
        with TestClient(main_module.app) as client:
            sync_response = client.post(
                "/ask",
                json={
                    "question": question,
                    "conversation_id": str(uuid4()),
                    "route_options": options,
                },
            )
            sync_payload = sync_response.json()
            sync_observation = _observation(
                sync_payload,
                status_code=sync_response.status_code,
                llm_invoked=llm.invoked,
            )

            llm.invoked = False
            with client.stream(
                "POST",
                "/ask/stream",
                json={
                    "question": question,
                    "conversation_id": str(uuid4()),
                    "route_options": options,
                },
            ) as stream_response:
                events = _parse_sse(stream_response.read().decode("utf-8"))
                done = events.get("done", {})
                source_event = events.get("sources", {})
                stream_payload = dict(done)
                stream_payload.setdefault("sources", source_event.get("sources", []))
                stream_observation = _observation(
                    stream_payload,
                    status_code=stream_response.status_code,
                    llm_invoked=llm.invoked,
                )
    finally:
        main_module._state = previous_state
        main_module._ensure_loaded = previous_loader

    expected = {
        "status_code": 200,
        "retrieval_outcome": "failed",
        "effective_route": "rag_grounded",
        "route_reason": "retrieval_failed",
        "source_count": 0,
        "grounding_mode": "none",
        "llm_invoked": False,
    }
    return {
        "schema_version": "rag_eval.isolated_route_failure/v1",
        "probe": "deterministic_failing_retriever",
        "production_fault_injection": False,
        "expected": expected,
        "sync": sync_observation,
        "sse": stream_observation,
        "retriever_calls": retriever.search_calls,
        "passed": sync_observation == expected and stream_observation == expected,
    }
