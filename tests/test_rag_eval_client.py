from __future__ import annotations

import json

import pytest

from src.rag_eval.client import ClientProtocolError, RagEvalClient, parse_sse_lines
from src.rag_eval.contracts import Difficulty, EvalCase


def _case(query: str = "测试问题") -> EvalCase:
    return EvalCase(
        case_id="fixture-case",
        query=query,
        difficulty=Difficulty.D1,
        scenario="text",
    )


def _event(event: str, data: dict) -> list[str]:
    return [f"event: {event}", f"data: {json.dumps(data, ensure_ascii=False)}", ""]


def test_parse_sse_requires_sources_before_tokens_and_done():
    lines = [
        *_event("sources", {"sources": [{"child_id": "c1"}], "media": [], "route": {"intent": "intro"}}),
        *_event("token", {"token": "答"}),
        *_event("token", {"token": "案"}),
        *_event("done", {"answer": "答案", "sources": [{"child_id": "c1"}], "media": []}),
    ]

    transcript = parse_sse_lines(lines)

    assert transcript.answer == "答案"
    assert transcript.tokens == ("答", "案")
    assert transcript.sources_payload["sources"][0]["child_id"] == "c1"
    assert transcript.done_payload["answer"] == "答案"


def test_parse_sse_rejects_token_before_sources():
    with pytest.raises(ClientProtocolError, match="before sources"):
        parse_sse_lines([*_event("token", {"token": "x"}), *_event("done", {"answer": "x"})])


def test_parse_sse_error_without_done_is_structured_failure():
    transcript = parse_sse_lines(
        [
            *_event("sources", {"sources": [], "media": []}),
            *_event("error", {"message": "LLM failed"}),
        ]
    )

    assert transcript.success is False
    assert transcript.error == "LLM failed"
    assert transcript.done_payload == {}


class _Response:
    def __init__(self, *, payload=None, lines=None, status_code=200):
        self._payload = payload
        self._lines = lines or []
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.content = json.dumps(payload or {}).encode("utf-8")
        self.closed = False
        self.iter_chunk_size = None

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=True, chunk_size=None):
        self.iter_chunk_size = chunk_size
        yield from self._lines

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.trust_env = True
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return next(self.responses)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return next(self.responses)

    def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return next(self.responses)


class _Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.1
        return self.value


def test_stream_client_disables_proxy_and_records_timings():
    lines = [
        *_event("sources", {"sources": [{"child_id": "c1"}], "media": [], "route": {"intent": "intro"}, "memory": {"status": "hit"}}),
        *_event("token", {"token": "答"}),
        *_event("done", {"answer": "答", "sources": [{"child_id": "c1"}], "media": [], "memory": {"status": "hit"}}),
    ]
    session = _Session([_Response(lines=lines)])
    client = RagEvalClient("http://127.0.0.1:8000", session=session, clock=_Clock())

    exchange = client.ask_stream(_case())

    assert session.trust_env is False
    assert exchange.success is True
    assert exchange.answer == "答"
    assert exchange.timing.retrieval_ms is None
    assert exchange.timing.packet_ready_ms is not None
    assert exchange.timing.ttft_ms is not None
    assert exchange.timing.total_ms >= exchange.timing.ttft_ms
    assert session.calls[0][2]["stream"] is True
    assert exchange.raw["memory"] == {"status": "hit"}
    assert exchange.raw["sources_event"]["memory"] == exchange.raw["done_event"]["memory"]


def test_sync_client_rejects_non_object_json():
    session = _Session([_Response(payload=["bad"])])
    client = RagEvalClient("http://127.0.0.1:8000", session=session)

    exchange = client.ask(_case())

    assert exchange.success is False
    assert "JSON object" in exchange.error


def test_voice_pagination_follows_cursors_and_rejects_loop():
    first_panel = {
        "type": "voice",
        "grouping": "voice_line",
        "entity_id": "entity-1",
        "lines": [{"voice_line_id": "line-1", "title": "1", "variants": [{"media_id": "m1"}]}],
        "page_size": 1,
        "total_lines": 3,
        "has_more": True,
        "next_cursor": "cursor-1",
    }
    page_two = {
        **first_panel,
        "lines": [{"voice_line_id": "line-2", "title": "2", "variants": [{"media_id": "m2"}]}],
        "next_cursor": "cursor-2",
    }
    page_three_loop = {
        **first_panel,
        "lines": [{"voice_line_id": "line-3", "title": "3", "variants": [{"media_id": "m3"}]}],
        "next_cursor": "cursor-2",
    }
    session = _Session([_Response(payload=page_two), _Response(payload=page_three_loop)])
    client = RagEvalClient("http://127.0.0.1:8000", session=session)

    with pytest.raises(ClientProtocolError, match="repeated voice cursor"):
        client.collect_voice_pages([first_panel])


def test_voice_pagination_rejects_local_path_cursor():
    panel = {
        "type": "voice",
        "lines": [],
        "has_more": True,
        "next_cursor": "file://private/cursor",
    }
    client = RagEvalClient("http://127.0.0.1:8000", session=_Session([]))

    with pytest.raises(ClientProtocolError, match="unsafe voice cursor"):
        client.collect_voice_pages([panel])


def test_eval_client_only_adds_conversation_id_when_requested():
    session = _Session([
        _Response(payload={"answer": "a", "sources": []}),
        _Response(payload={"answer": "b", "sources": []}),
    ])
    client = RagEvalClient("http://example", session=session)

    client.ask(_case("q"), conversation_id="uuid-a")
    client.ask(_case("q2"))

    assert session.calls[0][2]["json"]["conversation_id"] == "uuid-a"
    assert "conversation_id" not in session.calls[1][2]["json"]


def test_eval_client_sends_route_contract_and_preserves_trust_packet_fields():
    payload = {
        "answer": "有证据。[S01]",
        "grounding_mode": "grounded",
        "sources": [
            {
                "citation_id": "S01",
                "name": "测试实体甲",
                "child_id": "child-a",
                "parent_id": "parent-a",
                "entity_type": "character",
                "entity_id": "entity-a",
            }
        ],
        "media": [],
        "route": {
            "entity": "测试实体甲",
            "semantic_intents": ["skill"],
            "proposed_route": "llm_general",
            "effective_route": "rag_grounded",
            "retrieval_outcome": "partial",
            "route_reason": "grounded_partial",
        },
        "citation_warning": "citation_repair_attempted",
        "omitted_actions": [{"action_type": "expand_search", "label": "继续", "query": "q"}],
        "failure_actions": [],
        "memory": {"status": "hit", "turns_used": 1, "rewrite_mode": "planner"},
        "timing": {
            "model_first_token_ms": 20.0,
            "validated_ready_ms": 30.0,
            "visible_first_token_ms": 35.0,
            "completed_ms": 40.0,
            "stage_ms": {"retrieval.dense": 7.0, "retrieval.rerank": 5.0},
            "error_stages": [],
            "warning": "",
        },
    }
    session = _Session([_Response(payload=payload)])
    client = RagEvalClient("http://example", session=session, clock=_Clock())
    case = EvalCase(
        **{
            **_case().__dict__,
            "route_options": {"free_supplement": True},
            "action_payload": {"action_type": "force_free_supplement"},
        }
    )

    exchange = client.ask(case)

    sent = session.calls[0][2]["json"]
    assert sent["route_options"] == {"free_supplement": True}
    assert sent["action_payload"] == {"action_type": "force_free_supplement"}
    assert exchange.ownership_key == ("character", "entity-a")
    assert exchange.semantic_intents == ("skill",)
    assert exchange.source_map["S01"]["child_id"] == "child-a"
    assert exchange.grounding_mode == "grounded"
    assert exchange.route_decision["retrieval_outcome"] == "partial"
    assert exchange.omitted_actions[0]["action_type"] == "expand_search"
    assert exchange.memory["status"] == "hit"
    assert exchange.timing.retrieval_ms == 12.0
    assert exchange.timing.validated_ready_ms == 30.0


def test_stream_retrieval_time_comes_from_stage_spans_not_packet_ready_time():
    timing = {
        "model_first_token_ms": 20.0,
        "validated_ready_ms": 30.0,
        "visible_first_token_ms": 35.0,
        "completed_ms": 40.0,
        "stage_ms": {"retrieval.structured": 2.0, "retrieval.dense": 3.0},
        "error_stages": [],
        "warning": "",
    }
    lines = [
        *_event("sources", {"sources": [], "media": [], "timing": timing}),
        *_event("token", {"token": "答"}),
        *_event("done", {"answer": "答", "sources": [], "media": [], "timing": timing}),
    ]
    client = RagEvalClient(
        "http://example",
        session=_Session([_Response(lines=lines)]),
        clock=_Clock(),
    )

    exchange = client.ask_stream(_case())

    assert exchange.timing.retrieval_ms == 5.0
    assert exchange.timing.packet_ready_ms is not None
    assert exchange.timing.packet_ready_ms > exchange.timing.retrieval_ms
    assert exchange.timing.ttft_ms is not None


def test_eval_client_clear_requires_204_and_cancel_closes_after_first_token():
    lines = [
        *_event("sources", {"sources": []}),
        *_event("token", {"token": "partial"}),
        *_event("done", {"answer": "must-not-read", "sources": []}),
    ]
    clear_response = _Response(status_code=204)
    stream_response = _Response(lines=lines)
    session = _Session([clear_response, stream_response])
    client = RagEvalClient("http://example", session=session)

    assert client.clear_conversation("uuid-a") == 204
    events = client.cancel_stream_after_first_token(
        _case(),
        conversation_id="uuid-a",
    )

    assert events == ("sources", "token")
    assert stream_response.closed is True
    assert stream_response.iter_chunk_size == 1
