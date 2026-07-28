"""SSE 流式问答端点测试。"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from src.rag.conversation import ConversationMemoryStore
from src.rag.execution import AskExecutionInput, PreparedExecution
from src.rag.serializers import response_packet_to_public_dict
from tests.conftest import CONVERSATION_ID, ExecutionAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """解析 SSE 文本流为 (event, data) 列表。"""
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        ev = block.split("event: ", 1)[1].split("\n", 1)[0] if "event: " in block else "message"
        data_line = [line for line in block.split("\n") if line.startswith("data: ")]
        data = json.loads(data_line[0][6:]) if data_line else {}
        events.append((ev, data))
    return events


def _stream_events(client, question: str, conversation_id: str):
    with client.stream(
        "POST",
        "/ask/stream",
        json={"question": question, "conversation_id": conversation_id},
    ) as response:
        assert response.status_code == 200
        return _parse_sse(response.read().decode("utf-8"))


class _ExecuteProtocol:
    def execute(self, *args, **kwargs):
        return ExecutionAdapter(self).execute(*args, **kwargs)


class _TrueStreamingChain:
    def __init__(self, chunks=("first", " second"), final_answer="first second"):
        class _PacketFixture:
            def ask(self, question, **_kwargs):
                return {
                    "answer": "unused",
                    "sources": [{
                        "name": "Fixture",
                        "category": "fixture",
                        "source": "fixture.md",
                        "score": 1.0,
                        "content": "Evidence",
                    }],
                    "context": "Evidence",
                }

        self.packet = ExecutionAdapter(_PacketFixture()).execute("Question")
        self.chunks = tuple(chunks)
        self.final_answer = final_answer
        self.finished = False

    def prepare_execution(
        self,
        question,
        category=None,
        route_options=None,
        action_payload=None,
        conversation=None,
        memory_status="disabled",
        memory_turns_used=0,
        trace=None,
    ):
        del trace
        return PreparedExecution(
            request=AskExecutionInput(
                question=question,
                category=category,
                route_options=route_options or {},
                action_payload=action_payload,
                memory_status=memory_status,
                memory_turns_used=memory_turns_used,
            ),
            conversation=conversation,
            retrieval_packet=self.packet.retrieval_packet,
            answer_context="Evidence",
            generation_messages=(),
            generation_mode="grounded",
            immediate_answer=None,
            missing_intents=(),
        )

    async def astream_prepared(self, prepared):
        del prepared
        for chunk in self.chunks:
            yield chunk
            await asyncio.sleep(0)
        self.finished = True

    def finalize_execution(self, prepared, draft, trace=None):
        del prepared
        if trace is not None:
            trace.mark_validated_ready()
        return replace(self.packet, answer=self.final_answer or draft)


def test_stream_emits_real_model_chunk_before_generation_finishes():
    from backend.sse import rag_stream_generator

    async def scenario():
        chain = _TrueStreamingChain()
        generator = rag_stream_generator(chain, "Question", None)
        first_blocks = [await anext(generator) for _ in range(5)]
        first_events = _parse_sse("".join(first_blocks))

        assert [name for name, _data in first_events] == [
            "status",
            "status",
            "sources",
            "status",
            "token",
        ]
        assert first_events[-1][1]["token"] == "first"
        assert chain.finished is False
        await generator.aclose()

    asyncio.run(scenario())


def _collect_true_stream(chain):
    from backend.sse import rag_stream_generator

    async def scenario():
        return _parse_sse("".join([
            block
            async for block in rag_stream_generator(chain, "Question", None)
        ]))

    return asyncio.run(scenario())


def test_stream_replaces_draft_once_when_validation_changes_answer():
    events = _collect_true_stream(
        _TrueStreamingChain(chunks=("Draft",), final_answer="Final [S01]")
    )

    assert [name for name, _data in events] == [
        "status",
        "status",
        "sources",
        "status",
        "token",
        "status",
        "answer_replace",
        "status",
        "done",
    ]
    assert next(data for name, data in events if name == "answer_replace") == {
        "answer": "Final [S01]",
        "reason": "citation_validation",
    }
    assert events[-1][1]["corrected"] is True


def test_stream_does_not_replace_when_final_answer_matches_chunks():
    events = _collect_true_stream(
        _TrueStreamingChain(chunks=("Final", " [S01]"), final_answer="Final [S01]")
    )

    assert not any(name == "answer_replace" for name, _data in events)
    assert not any(
        name == "status" and data.get("phase") == "corrected"
        for name, data in events
    )
    assert events[-1][1]["corrected"] is False


def test_no_model_branch_emits_no_fake_tokens():
    class NoModelChain(_TrueStreamingChain):
        def prepare_execution(self, *args, **kwargs):
            prepared = super().prepare_execution(*args, **kwargs)
            return replace(
                prepared,
                generation_mode="none",
                immediate_answer="No model answer",
            )

        def finalize_execution(self, prepared, draft, trace=None):
            assert draft is None
            if trace is not None:
                trace.mark_validated_ready()
            return replace(
                self.packet,
                answer=prepared.immediate_answer,
                grounding_mode="none",
                turn_outcome="not_committable",
            )

    events = _collect_true_stream(NoModelChain())

    assert not any(name == "token" for name, _data in events)
    assert not any(
        name == "status" and data.get("phase") in {"generating", "validating"}
        for name, data in events
    )
    assert events[-1][1]["answer"] == "No model answer"


def test_sources_and_done_share_one_frozen_retrieval_snapshot():
    events = _collect_true_stream(_TrueStreamingChain())
    sources = next(data for name, data in events if name == "sources")
    done = next(data for name, data in events if name == "done")

    assert sources["sources"] == done["sources"]
    assert sources["memory"] == done["memory"]


def test_sync_and_stream_done_are_publicly_equivalent_for_same_draft():
    chain = _TrueStreamingChain(
        chunks=("Final", " [S01]"),
        final_answer="Final [S01]",
    )
    events = _collect_true_stream(chain)
    done = next(data for name, data in events if name == "done")
    expected = response_packet_to_public_dict(
        replace(chain.packet, answer="Final [S01]")
    )

    assert {key: done[key] for key in expected} == expected


def test_long_prepare_emits_heartbeat_comment_without_repeating_status():
    class SlowPrepareChain(_TrueStreamingChain):
        def prepare_execution(self, *args, **kwargs):
            time.sleep(0.03)
            return super().prepare_execution(*args, **kwargs)

    from backend.sse import rag_stream_generator

    async def scenario():
        return [
            block
            async for block in rag_stream_generator(
                SlowPrepareChain(),
                "Question",
                None,
                heartbeat_seconds=0.005,
            )
        ]

    blocks = asyncio.run(scenario())
    events = _parse_sse("".join(blocks))

    assert ": heartbeat\n\n" in blocks
    assert [
        data["phase"] for name, data in events if name == "status"
    ] == [
        "understanding",
        "retrieving",
        "generating",
        "validating",
    ]


def test_generation_failure_before_first_token_has_partial_false():
    class FailingChain(_TrueStreamingChain):
        async def astream_prepared(self, prepared):
            del prepared
            raise RuntimeError("secret upstream detail")
            yield ""

    events = _collect_true_stream(FailingChain())
    error = next(data for name, data in events if name == "error")

    assert error == {
        "message": "回答生成失败，请稍后重试。",
        "phase": "generating",
        "partial": False,
    }
    assert events[-2] == ("status", {"phase": "failed"})
    assert not any(name == "done" for name, _data in events)


def test_generation_failure_after_first_token_preserves_partial_draft():
    class PartiallyFailingChain(_TrueStreamingChain):
        async def astream_prepared(self, prepared):
            del prepared
            yield "Partial"
            raise RuntimeError("secret upstream detail")

    events = _collect_true_stream(PartiallyFailingChain())
    error = next(data for name, data in events if name == "error")

    assert next(data for name, data in events if name == "token")["token"] == "Partial"
    assert error == {
        "message": "回答生成失败，请稍后重试。",
        "phase": "generating",
        "partial": True,
    }
    assert not any(name == "done" for name, _data in events)


def test_validation_failure_replaces_draft_with_safe_fallback_and_errors():
    class ValidationFailureChain(_TrueStreamingChain):
        def finalize_execution(self, prepared, draft, trace=None):
            del prepared, draft, trace
            raise ValueError("secret validation detail")

    events = _collect_true_stream(ValidationFailureChain(chunks=("Draft",)))
    replacement = next(
        data for name, data in events if name == "answer_replace"
    )
    error = next(data for name, data in events if name == "error")

    assert replacement == {
        "answer": "回答校验失败，未展示未经验证的草稿。",
        "reason": "safe_fallback",
    }
    assert error == {
        "message": "回答校验失败，请稍后重试。",
        "phase": "validating",
        "partial": False,
    }
    assert not any(name == "done" for name, _data in events)


def test_disconnect_closes_upstream_and_never_commits_memory():
    class ClosableChain(_TrueStreamingChain):
        def __init__(self):
            super().__init__(chunks=("Partial", " ignored"))
            self.closed = False

        async def astream_prepared(self, prepared):
            del prepared
            try:
                yield "Partial"
                await asyncio.sleep(0)
                yield " ignored"
            finally:
                self.closed = True

    from backend.sse import rag_stream_generator

    async def scenario():
        chain = ClosableChain()
        store = ConversationMemoryStore()
        disconnected = False

        async def is_disconnected():
            return disconnected

        generator = rag_stream_generator(
            chain,
            "Question",
            None,
            memory_store=store,
            conversation_id=UUID(CONVERSATION_ID),
            is_disconnected=is_disconnected,
        )
        async for block in generator:
            if block.startswith("event: token"):
                disconnected = True
        lease = await store.acquire(UUID(CONVERSATION_ID))
        try:
            turns = lease.projection.turns
        finally:
            await store.release(lease)
        return chain.closed, turns

    closed, turns = asyncio.run(scenario())

    assert closed is True
    assert turns == ()


def test_success_commits_only_the_final_corrected_answer():
    from backend.sse import rag_stream_generator

    async def scenario():
        store = ConversationMemoryStore()
        async for _block in rag_stream_generator(
            _TrueStreamingChain(chunks=("Draft",), final_answer="Final corrected [S01]"),
            "Question",
            None,
            memory_store=store,
            conversation_id=UUID(CONVERSATION_ID),
        ):
            pass
        lease = await store.acquire(UUID(CONVERSATION_ID))
        try:
            return lease.projection.turns
        finally:
            await store.release(lease)

    turns = asyncio.run(scenario())

    assert turns[-1].answer == "Final corrected [S01]"


def test_sse_sources_and_done_have_identical_memory_metadata(client_with_memory_chain):
    client_with_memory_chain.post("/ask", json={
        "question": "介绍角色甲",
        "conversation_id": CONVERSATION_ID,
    })

    events = _stream_events(client_with_memory_chain, "她的技能呢", CONVERSATION_ID)
    sources = next(data for event, data in events if event == "sources")
    done = next(data for event, data in events if event == "done")

    assert sources["memory"] == done["memory"]
    assert sources["memory"] == {
        "status": "hit",
        "turns_used": 1,
        "rewrite_mode": "planner",
    }


def test_sync_and_sse_expose_reconciled_lifecycle_timing(client_with_memory_chain):
    sync = client_with_memory_chain.post("/ask", json={"question": "Timing question"}).json()
    events = _stream_events(
        client_with_memory_chain,
        "Timing question",
        "00000000-0000-4000-8000-000000000099",
    )
    done = next(data for event, data in events if event == "done")

    for payload in (sync, done):
        timing = payload["timing"]
        assert timing["model_first_token_ms"] <= timing["validated_ready_ms"]
        assert timing["validated_ready_ms"] <= timing["visible_first_token_ms"]
        assert timing["visible_first_token_ms"] <= timing["completed_ms"]
        assert "memory.acquire" in timing["stage_ms"]
        assert "response.serialize" in timing["stage_ms"]


class _CancelableMemoryChain(_ExecuteProtocol):
    def retrieve(
        self,
        question,
        category=None,
        route_options=None,
        action_payload=None,
        conversation=None,
    ):
        plan = SimpleNamespace(
            original_query=question,
            normalized_query="角色甲 技能",
            entity="角色甲",
            entity_type="character",
            intent="skill",
            secondary_intents=(),
            context_rewrite_mode="none",
        )
        return {
            "plan": plan,
            "sources": [{
                "name": "角色甲",
                "category": "人物",
                "source": "fixture.md",
                "score": 1.0,
                "content": "fixture",
            }],
            "context": "fixture",
            "assets": [],
            "media": [],
            "route": None,
            "free_supplement": False,
        }

    def llm_ready(self):
        return True

    def _stream_llm(
        self,
        question,
        context,
        free_supplement=False,
        conversation=None,
    ):
        yield AIMessageChunk(content="partial")
        yield AIMessageChunk(content="complete")


def test_cancel_before_done_does_not_commit():
    from backend.sse import rag_stream_generator

    async def scenario():
        store = ConversationMemoryStore()
        conversation_id = UUID(CONVERSATION_ID)
        generator = rag_stream_generator(
            _CancelableMemoryChain(),
            "问题",
            None,
            memory_store=store,
            conversation_id=conversation_id,
        )
        async for block in generator:
            if block.startswith("event: token"):
                await generator.aclose()
                break
        lease = await store.acquire(conversation_id)
        try:
            assert lease.projection.turns == ()
        finally:
            await store.release(lease)

    asyncio.run(scenario())


def test_disconnect_probe_before_done_does_not_commit():
    from backend.sse import rag_stream_generator

    async def scenario():
        store = ConversationMemoryStore()
        conversation_id = UUID(CONVERSATION_ID)
        disconnected = False

        async def is_disconnected():
            return disconnected

        generator = rag_stream_generator(
            _CancelableMemoryChain(),
            "问题",
            None,
            memory_store=store,
            conversation_id=conversation_id,
            is_disconnected=is_disconnected,
        )
        events = []
        async for block in generator:
            events.append(block)
            if block.startswith("event: token"):
                disconnected = True

        assert any(block.startswith("event: token") for block in events)
        assert not any(block.startswith("event: done") for block in events)
        lease = await store.acquire(conversation_id)
        try:
            assert lease.projection.turns == ()
        finally:
            await store.release(lease)

    asyncio.run(scenario())


def test_clear_during_stream_invalidates_the_old_generation_commit():
    from backend.sse import rag_stream_generator

    async def scenario():
        store = ConversationMemoryStore()
        conversation_id = UUID(CONVERSATION_ID)
        generator = rag_stream_generator(
            _CancelableMemoryChain(),
            "问题",
            None,
            memory_store=store,
            conversation_id=conversation_id,
        )

        assert (await anext(generator)).startswith("event: sources")
        assert (await anext(generator)).startswith("event: token")
        await store.clear(conversation_id)
        async for _block in generator:
            pass

        lease = await store.acquire(conversation_id)
        try:
            assert lease.status == "new"
            assert lease.projection.turns == ()
        finally:
            await store.release(lease)

    asyncio.run(scenario())


def test_sync_and_stream_memory_and_source_semantics_match_on_fresh_ids(
    client_with_memory_chain,
):
    sync_id = "00000000-0000-4000-8000-000000000011"
    stream_id = "00000000-0000-4000-8000-000000000012"

    sync = client_with_memory_chain.post("/ask", json={
        "question": "介绍角色甲",
        "conversation_id": sync_id,
    }).json()
    stream_events = _stream_events(
        client_with_memory_chain,
        "介绍角色甲",
        stream_id,
    )
    stream_sources = next(data for event, data in stream_events if event == "sources")
    stream_done = next(data for event, data in stream_events if event == "done")

    assert sync["memory"] == stream_sources["memory"] == stream_done["memory"]
    assert sync["route"]["entity"] == stream_sources["route"]["entity"]
    assert sync["route"]["requested_intents"] == stream_sources["route"]["requested_intents"]
    assert sync["sources"][0]["parent_id"] == stream_sources["sources"][0]["parent_id"]

    assert client_with_memory_chain.post("/ask", json={
        "question": "她的技能呢",
        "conversation_id": sync_id,
    }).json()["memory"]["status"] == "hit"
    assert client_with_memory_chain.post("/ask", json={
        "question": "她的技能呢",
        "conversation_id": stream_id,
    }).json()["memory"]["status"] == "hit"


@pytest.fixture
def client_with_mock_chain(monkeypatch):
    """api_key 就绪 + mock chain 流式固定 token。"""
    from backend import main as main_mod
    from tests.conftest import MockChain, MockVectorstore

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 2}),
        "retriever": None,
        "chain": MockChain(stream_tokens=["6", "是", "一位"], llm_ready=True),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    return TestClient(main_mod.app)


@pytest.fixture
def client_no_apikey(monkeypatch):
    """api_key 空,测降级。"""
    from backend import main as main_mod
    from tests.conftest import MockChain, MockVectorstore

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 2}),
        "retriever": None,
        "chain": MockChain(stream_tokens=[], llm_ready=False),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    return TestClient(main_mod.app)


def test_ask_stream_emits_sources_then_tokens_then_done(client_with_mock_chain):
    """事件顺序:sources → N×token → done,token 拼接为完整文本。"""
    with client_with_mock_chain.stream("POST", "/ask/stream",
                                       json={"question": "6是谁", "category": "人物"}) as resp:
        assert resp.status_code == 200
        text = resp.read().decode("utf-8")
    events = _parse_sse(text)
    event_types = [e[0] for e in events]
    assert event_types[0] == "sources"
    assert event_types[-1] == "done"
    assert event_types[1:-1]
    assert all(event_type == "token" for event_type in event_types[1:-1])
    # token 拼接
    tokens = [e[1]["token"] for e in events if e[0] == "token"]
    assert "".join(tokens) == "6是一位"
    # done 携带完整 answer
    assert events[-1][1]["answer"] == "6是一位"
    # sources 非空
    assert len(events[0][1]["sources"]) > 0


def test_ask_stream_api_key_empty_emits_fallback(client_no_apikey):
    """api_key 空:逐字发降级提示,done 仍带 sources。"""
    with client_no_apikey.stream("POST", "/ask/stream",
                                 json={"question": "test"}) as resp:
        text = resp.read().decode("utf-8")
    events = _parse_sse(text)
    tokens = [e[1]["token"] for e in events if e[0] == "token"]
    full = "".join(tokens)
    assert "DEEPSEEK_API_KEY" in full
    assert events[-1][0] == "done"
    assert events[-1][1]["answer"] == full


def test_ask_stream_category_filter_passed(client_with_mock_chain):
    """category 参数传到 retriever(sources 事件携带 category)。"""
    with client_with_mock_chain.stream("POST", "/ask/stream",
                                       json={"question": "x", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")
    events = _parse_sse(text)
    sources_event = next(e for e in events if e[0] == "sources")
    sources = sources_event[1]["sources"]
    assert len(sources) > 0
    for s in sources:
        assert s["category"] == "人物"


def test_ask_stream_emits_error_when_retrieval_fails(monkeypatch):
    """检索阶段抛异常(如 Ollama 未运行)时,应发送 error 事件而非中断连接。"""
    from backend import main as main_mod
    from tests.conftest import MockChain, MockVectorstore

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 2}),
        "retriever": None,
        "chain": MockChain(
            stream_tokens=["x"],
            llm_ready=True,
            retriever_raises=ConnectionError("Failed to connect to Ollama"),
        ),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)
    with client.stream("POST", "/ask/stream",
                       json={"question": "test", "category": "人物"}) as resp:
        assert resp.status_code == 200
        text = resp.read().decode("utf-8")
    events = _parse_sse(text)
    # 应有 error 事件,而非连接中断(无事件)
    assert len(events) > 0
    assert events[-1][0] == "error"
    assert "Ollama" in events[-1][1]["message"] or "retriev" in events[-1][1]["message"].lower() or "connect" in events[-1][1]["message"].lower()


def test_ask_stream_uses_chain_retrieve_when_available(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class ChainWithRetrieve(_ExecuteProtocol):
        def __init__(self):
            self.retrieve_calls = []

        def retrieve(self, question, category=None):
            self.retrieve_calls.append((question, category))
            return {
                "plan": None,
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": category or "人物",
                    "source": "玛蒂尔达.md",
                    "score": 1.0,
                    "content": "神秘术内容",
                    "heading_path": "玛蒂尔达 > 神秘术",
                    "chunk_index": 2,
                    "retrieval_stage": "entity_name",
                    "debug": {"router_intent": "skill"},
                }],
                "context": "[玛蒂尔达] 神秘术内容",
            }

        def llm_ready(self):
            return True

        def _stream_llm(self, question, context):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content="ok")

    chain = ChainWithRetrieve()
    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": chain,
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream("POST", "/ask/stream", json={"question": "玛蒂尔达的技能是什么", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)
    assert chain.retrieve_calls == [("玛蒂尔达的技能是什么", "人物")]
    assert events[0][0] == "sources"
    assert events[0][1]["sources"][0]["heading_path"] == "玛蒂尔达 > 神秘术"


def test_ask_stream_emits_assets_with_sources_and_done(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def retrieve(self, question, category=None):
            return {
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "100/玛蒂尔达.md",
                    "score": 1.0,
                    "heading_path": "玛蒂尔达 > 神秘术",
                    "chunk_index": 1,
                    "retrieval_stage": "entity_packet",
                }],
                "context": "ctx",
                "assets": [{"asset_id": "a2", "role": "skill", "url": "http://minio/a2.png", "alt": "神秘术"}],
            }

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream("POST", "/ask/stream", json={"question": "q", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)

    assert events[0][0] == "sources"
    assert events[0][1]["assets"][0]["asset_id"] == "a2"
    assert events[0][1]["media"][0]["asset_id"] == "a2"
    assert events[-1][0] == "done"
    assert events[-1][1]["assets"][0]["url"] == "http://minio/a2.png"
    assert events[-1][1]["media"][0]["url"] == "http://minio/a2.png"


def test_ask_response_includes_typed_media(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def ask(self, question, category=None):
            return {
                "answer": "ok",
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "100/玛蒂尔达.md",
                    "score": 1.0,
                }],
                "assets": [{"asset_id": "a2", "role": "skill", "url": "http://minio/a2.png", "alt": "神秘术"}],
                "media": [{
                    "media_id": "m2",
                    "asset_id": "a2",
                    "asset_type": "skill",
                    "mime": "image/png",
                    "url": "http://minio/a2.png",
                    "title": "神秘术",
                    "alt": "神秘术",
                    "role": "skill",
                    "attach_policy": "auto",
                }],
            }

        def llm_ready(self):
            return True

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    resp = client.post("/ask", json={"question": "q", "category": "人物"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["assets"][0]["asset_id"] == "a2"
    assert payload["media"][0]["media_id"] == "m2"
    assert payload["media"][0]["asset_type"] == "skill"


def test_ask_stream_sources_event_includes_route_actions_and_panels(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def retrieve(self, question, category=None):
            return {
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "100/玛蒂尔达.md",
                    "score": 1.0,
                    "content": "神秘术内容",
                }],
                "context": "ctx",
                "assets": [],
                "media": [],
                "media_panels": [],
                "route": {"name": "rag_grounded", "confidence": 0.8, "intent": "skill", "entity": "玛蒂尔达"},
                "omitted_actions": [{
                    "label": "全部技能",
                    "query": "介绍玛蒂尔达的全部技能",
                    "entity": "玛蒂尔达",
                    "entity_type": "character",
                    "intent": "skill",
                    "packet_policy": "section_detail",
                    "target_parent_id": "char:3041/skills",
                }],
                "failure_actions": [],
            }

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream("POST", "/ask/stream", json={"question": "q", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)
    sources_event = events[0][1]
    assert sources_event["route"]["name"] == "rag_grounded"
    assert sources_event["omitted_actions"][0]["target_parent_id"] == "char:3041/skills"
    assert sources_event["failure_actions"] == []
    assert sources_event["media_panels"] == []


def test_ask_stream_sources_event_includes_planning_diagnostics_and_source_ids(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def retrieve(self, question, category=None):
            return {
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "Data:Char/3041.json",
                    "score": 1.0,
                    "content": "神秘术内容",
                    "child_id": "char:3041/skills:1",
                    "parent_id": "char:3041/skills",
                    "section_kind": "skill",
                }],
                "context": "ctx",
                "assets": [],
                "media": [],
                "route": {"name": "rag_grounded", "confidence": 0.7, "intent": "skill", "entity": "玛蒂尔达"},
                "planning_status": "fallback_timeout",
                "planning_warning": "LLM 规划超时，已使用规则降级。",
                "planning_error": "timeout",
                "omitted_actions": [],
                "failure_actions": [],
                "media_panels": [],
            }

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream("POST", "/ask/stream", json={"question": "q", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)
    sources_payload = events[0][1]
    done_payload = events[-1][1]

    assert sources_payload["planning_status"] == "fallback_timeout"
    assert sources_payload["planning_warning"]
    assert sources_payload["planning_error"] == "timeout"
    assert done_payload["planning_status"] == "fallback_timeout"
    assert sources_payload["sources"][0]["child_id"] == "char:3041/skills:1"
    assert sources_payload["sources"][0]["parent_id"] == "char:3041/skills"
    assert sources_payload["sources"][0]["section_kind"] == "skill"


def test_ask_stream_no_sources_exposes_recovery_actions(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def retrieve(self, question, category=None):
            return {
                "sources": [],
                "context": "",
                "assets": [],
                "media": [],
                "route": {"name": "rag_grounded", "confidence": 0.0, "intent": "intro", "entity": "玛蒂尔达"},
                "planning_status": "llm",
                "planning_warning": "",
                "planning_error": "",
                "omitted_actions": [],
                "failure_actions": [{
                    "label": "扩大范围重新搜索",
                    "query": question,
                    "entity": "玛蒂尔达",
                    "entity_type": "character",
                    "intent": "expanded_rag",
                    "packet_policy": "expanded",
                    "target_parent_id": None,
                }, {
                    "label": "使用自由补充重答",
                    "query": question,
                    "entity": "玛蒂尔达",
                    "entity_type": "character",
                    "intent": "llm_general",
                    "packet_policy": "free_supplement",
                    "target_parent_id": None,
                }],
                "media_panels": [],
            }

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream("POST", "/ask/stream", json={"question": "q", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)
    labels = [item["label"] for item in events[0][1]["failure_actions"]]

    assert labels == ["扩大范围重新搜索", "使用自由补充重答"]


def test_ask_stream_empty_free_supplement_routes_to_llm(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def __init__(self):
            self.free_supplement_flags = []

        def retrieve(self, question, category=None, route_options=None, action_payload=None):
            return {
                "sources": [],
                "context": "",
                "assets": [],
                "media": [],
                "free_supplement": True,
                "route": {"name": "llm_general", "confidence": 0.0, "intent": "llm_general", "entity": None},
                "planning_status": "llm",
                "planning_warning": "",
                "planning_error": "",
                "omitted_actions": [],
                "failure_actions": [],
                "media_panels": [],
            }

        def llm_ready(self):
            return True

        def _stream_llm(self, question, context, free_supplement=False):
            from langchain_core.messages import AIMessageChunk

            self.free_supplement_flags.append(free_supplement)
            yield AIMessageChunk(content="自由")
            yield AIMessageChunk(content="回答")

    chain = Chain()
    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": chain,
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream(
        "POST",
        "/ask/stream",
        json={
            "question": "1999是什么游戏",
            "route_options": {"free_supplement": True},
        },
    ) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)

    assert chain.free_supplement_flags == [True]
    assert events[0][1]["failure_actions"] == []
    assert events[-1][1]["answer"] == "自由回答"


def test_ask_response_includes_planning_diagnostics_and_debug_fields(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def ask(self, question, category=None):
            return {
                "answer": "ok",
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "Data:Char/3041.json",
                    "score": 1.0,
                    "child_id": "char:3041/profile:0000",
                    "parent_id": "char:3041/profile",
                    "section_kind": "profile",
                }],
                "assets": [],
                "media": [],
                "route": {"name": "rag_grounded", "confidence": 0.9, "intent": "intro", "entity": "玛蒂尔达"},
                "planning_status": "fallback_parse_error",
                "planning_warning": "LLM 返回不是合法 JSON，已使用规则降级。",
                "planning_error": "invalid json",
                "omitted_actions": [],
                "failure_actions": [],
                "media_panels": [],
            }

        def llm_ready(self):
            return True

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    resp = client.post("/ask", json={"question": "q", "category": "人物"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["planning_status"] == "fallback_parse_error"
    assert payload["planning_warning"]
    assert payload["planning_error"] == "invalid json"
    assert payload["sources"][0]["child_id"] == "char:3041/profile:0000"
    assert payload["sources"][0]["parent_id"] == "char:3041/profile"
    assert payload["sources"][0]["section_kind"] == "profile"


def _first_voice_page():
    return {
        "type": "voice",
        "grouping": "voice_line",
        "entity_id": "char:test",
        "lines": [{
            "voice_line_id": "char:test/voice:001",
            "title": "Line one",
            "variants": [{
                "media_id": "voice-zh",
                "asset_id": "voice-zh",
                "asset_type": "voice",
                "role": "voice",
                "url": "https://media.example/voice-zh.mp3",
                "language": "zh",
            }],
        }],
        "page_size": 1,
        "total_lines": 3,
        "has_more": True,
        "next_cursor": "opaque-cursor",
    }


def _transport_result():
    voice = _first_voice_page()["lines"][0]["variants"][0]
    return {
        "answer": "ok",
        "sources": [{
            "name": "Test Character",
            "category": "characters",
            "source": "Data:Char/test.json",
            "score": 1.0,
            "content": "context",
        }],
        "context": "context",
        "assets": [voice],
        "media": [voice],
        "route": {
            "name": "rag_grounded",
            "confidence": 0.8,
            "intent": "skill",
            "entity": "Test Character",
            "requested_intents": ["skill", "voice"],
            "retrieval_debug": {
                "candidate_k": 28,
                "intent_targets": {"skill": 5, "voice": 2},
            },
        },
        "planning_status": "llm",
        "planning_warning": "",
        "planning_error": "",
        "omitted_actions": [],
        "failure_actions": [],
        "media_panels": [_first_voice_page()],
        "plan": {"prompt": "must-not-leak"},
    }


def test_ask_and_sse_share_first_page_route_metadata(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain(_ExecuteProtocol):
        def ask(self, question, category=None, route_options=None, action_payload=None):
            return _transport_result()

        def retrieve(self, question, category=None, route_options=None, action_payload=None):
            return _transport_result()

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"characters": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    ask_payload = client.post("/ask", json={"question": "q"}).json()
    with client.stream("POST", "/ask/stream", json={"question": "q"}) as response:
        events = _parse_sse(response.read().decode("utf-8"))
    sources_payload = events[0][1]
    done_payload = events[-1][1]

    for payload in (sources_payload, done_payload):
        assert payload["route"] == ask_payload["route"]
        assert payload["media_panels"] == ask_payload["media_panels"]
        assert payload["assets"] == ask_payload["assets"]
        assert payload["media"] == ask_payload["media"]
        assert "plan" not in payload
    assert ask_payload["route"]["requested_intents"] == ["skill", "voice"]
    assert ask_payload["route"]["retrieval_debug"]["candidate_k"] == 28


def test_voice_page_endpoint_is_typed_and_registry_only(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Bomb:
        def __getattr__(self, name):
            raise AssertionError(f"page request touched {name}")

    class PageChain:
        _query_planner = Bomb()
        _retriever = Bomb()
        _llm = Bomb()
        _embedding = Bomb()

        def __init__(self):
            self.calls = []

        def get_voice_page(self, cursor):
            self.calls.append(cursor)
            page = _first_voice_page()
            page["has_more"] = False
            page["next_cursor"] = None
            return page

    chain = PageChain()
    vectorstore = MockVectorstore(doc_counts={"characters": 1})
    main_mod._state = {
        "vs": vectorstore,
        "retriever": None,
        "chain": chain,
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    response = client.get("/api/media/voice/page", params={"cursor": "opaque-cursor"})

    assert response.status_code == 200
    assert response.json()["lines"][0]["voice_line_id"] == "char:test/voice:001"
    assert chain.calls == ["opaque-cursor"]
    operation = client.get("/openapi.json").json()["paths"]["/api/media/voice/page"]["get"]
    assert [item["name"] for item in operation["parameters"]] == ["cursor"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/VoicePanelPage"
    }


@pytest.mark.parametrize(
    ("error_type", "status_code", "message"),
    [
        ("invalid", 400, "invalid voice cursor"),
        ("mismatch", 409, "reload first page"),
    ],
)
def test_voice_page_endpoint_maps_cursor_errors(monkeypatch, error_type, status_code, message):
    from backend import main as main_mod
    from src.assets.voice_pagination import InvalidVoiceCursor, VoiceCursorBuildMismatch

    class Chain(_ExecuteProtocol):
        def get_voice_page(self, cursor):
            if error_type == "invalid":
                raise InvalidVoiceCursor("unknown")
            raise VoiceCursorBuildMismatch("old build")

    main_mod._state = {"vs": object(), "retriever": None, "chain": Chain(), "loaded": True}
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    response = TestClient(main_mod.app).get(
        "/api/media/voice/page",
        params={"cursor": "opaque-cursor"},
    )

    assert response.status_code == status_code
    assert message in response.json()["detail"].lower()


def test_voice_page_endpoint_returns_503_when_chain_is_unavailable(monkeypatch):
    from backend import main as main_mod

    main_mod._state = {"vs": None, "retriever": None, "chain": None, "loaded": False}
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)

    response = TestClient(main_mod.app).get(
        "/api/media/voice/page",
        params={"cursor": "opaque-cursor"},
    )

    assert response.status_code == 503


def test_voice_page_endpoint_never_initializes_unloaded_rag_dependencies(monkeypatch):
    from backend import main as main_mod
    from src.rag import vectorstore as vectorstore_mod

    calls = []

    def fail_on_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("voice page request initialized a RAG dependency")

    main_mod._state = {"vs": None, "retriever": None, "chain": None, "loaded": False}
    monkeypatch.setattr(main_mod, "load_vectorstore", fail_on_call)
    monkeypatch.setattr(main_mod, "Retriever", fail_on_call)
    monkeypatch.setattr(vectorstore_mod, "get_embeddings", fail_on_call)

    response = TestClient(main_mod.app).get(
        "/api/media/voice/page",
        params={"cursor": "opaque-cursor"},
    )

    assert response.status_code == 503
    assert calls == []


def test_voice_page_endpoint_returns_503_for_loaded_legacy_chain(monkeypatch):
    from backend import main as main_mod

    class LegacyChain:
        pass

    main_mod._state = {
        "vs": object(),
        "retriever": object(),
        "chain": LegacyChain(),
        "loaded": True,
    }
    monkeypatch.setattr(
        main_mod,
        "_ensure_loaded",
        lambda: (_ for _ in ()).throw(AssertionError("page request called loader")),
    )

    response = TestClient(main_mod.app).get(
        "/api/media/voice/page",
        params={"cursor": "opaque-cursor"},
    )

    assert response.status_code == 503
    assert "voice pagination unavailable" in response.json()["detail"].lower()


def test_voice_page_endpoint_rejects_stale_chain_without_loading(monkeypatch):
    from backend import main as main_mod
    from src.rag import vectorstore as vectorstore_mod

    calls = []

    def fail_on_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("stale page request touched a RAG dependency")

    class StaleChain:
        def get_voice_page(self, cursor):
            calls.append(cursor)
            return _first_voice_page()

    main_mod._state = {
        "vs": object(),
        "retriever": object(),
        "chain": StaleChain(),
        "loaded": False,
    }
    monkeypatch.setattr(main_mod, "load_vectorstore", fail_on_call)
    monkeypatch.setattr(main_mod, "Retriever", fail_on_call)
    monkeypatch.setattr(vectorstore_mod, "get_embeddings", fail_on_call)

    response = TestClient(main_mod.app).get(
        "/api/media/voice/page",
        params={"cursor": "opaque-cursor"},
    )

    assert response.status_code == 503
    assert calls == []


def test_ask_and_sse_serialization_remove_local_paths_and_secrets(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    result = _transport_result()
    unsafe_media = {
        "media_id": "unsafe",
        "asset_id": "unsafe",
        "asset_type": "voice",
        "role": "voice",
        "url": "file:///D:/private/voice.mp3",
        "local_relpath": "D:\\private\\voice.mp3",
        "api_key": "super-secret",
    }
    result["assets"] = [unsafe_media]
    result["media"] = [unsafe_media]
    result["media_panels"][0]["lines"][0]["variants"] = [unsafe_media]
    result["route"]["retrieval_debug"].update({
        "prompt": "private prompt",
        "secret_key": "super-secret",
        "local_relpath": "C:\\private\\index.jsonl",
    })

    class Chain(_ExecuteProtocol):
        def ask(self, question, category=None, route_options=None, action_payload=None):
            return result

        def retrieve(self, question, category=None, route_options=None, action_payload=None):
            return result

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"characters": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    ask_text = client.post("/ask", json={"question": "q"}).text
    with client.stream("POST", "/ask/stream", json={"question": "q"}) as response:
        sse_text = response.read().decode("utf-8")

    for serialized in (ask_text, sse_text):
        lowered = serialized.lower()
        assert "file://" not in lowered
        assert "d:\\" not in lowered
        assert "c:\\" not in lowered
        assert "local_relpath" not in lowered
        assert "super-secret" not in lowered
        assert "private prompt" not in lowered


def test_sse_sanitizer_is_recursive_deterministic_and_json_safe(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class UnknownValue:
        def __repr__(self):
            return "unknown-object-secret"

    result = _transport_result()
    result["route"]["requested_intents"] = ["skill", "voice"]
    result["route"]["retrieval_debug"] = {
        "candidate_k": 28,
        "required_source_count": "7",
        "intent_targets": {"skill": 5, "voice": 2},
        "coverage_shortfall": {"skill": 0, "voice": UnknownValue()},
        "system_prompt": "nested-system-prompt-secret",
        "raw_content": "nested-raw-content-secret",
        "api_key": "nested-api-key-secret",
        "token": "nested-token-secret",
        "path": Path("D:/private/debug.json"),
        "local_relpath": "C:\\private\\debug.json",
    }
    result["failure_actions"] = [{
        "label": "Retry",
        "query": "q",
        "metadata": {
            "system_prompt": "action-system-prompt-secret",
            "raw_content": "action-raw-content-secret",
            "api_key": "action-api-key-secret",
            "token": "action-token-secret",
            "path": Path("D:/private/action.json"),
            "local_relpath": "C:\\private\\action.json",
            "innocent_local_value": "E:\\private\\value.txt",
            "safe_set": {"beta", "alpha"},
            "safe_tuple": ("zeta", "alpha"),
            "safe_list": ["one", "two"],
            "execution_plan": "action-execution-plan-secret",
            "query_planner": "action-query-planner-secret",
            "queryPlan": "camel-query-plan-secret",
            "ExecutionPlan": "pascal-execution-plan-secret",
            "plannerState": "camel-planner-state-secret",
            "rawContent": "camel-raw-content-secret",
            "apiKey": "camel-api-key-secret",
            "localRelpath": "camel-local-relpath-secret",
            "queryPLAN": "acronym-query-plan-secret",
            "XMLPlannerState": "acronym-planner-state-secret",
            "RawCONTENT": "acronym-raw-content-secret",
            "APIKey": "acronym-api-key-secret",
            "localRELPATH": "acronym-local-relpath-secret",
            "pageSize": 8,
            "totalLines": 12,
            "nextCursor": "opaque-next-cursor",
            "nested": {
                "planner_state": "nested-planner-secret",
                "safe_value": "kept",
            },
            "raw_bytes": b"bytes-secret",
            "unknown": UnknownValue(),
        },
    }]

    class Chain(_ExecuteProtocol):
        def retrieve(self, question, category=None, route_options=None, action_payload=None):
            return result

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"characters": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)

    with TestClient(main_mod.app).stream(
        "POST",
        "/ask/stream",
        json={"question": "q"},
    ) as response:
        events = _parse_sse(response.read().decode("utf-8"))

    assert response.status_code == 200
    assert not [event for event, _payload in events if event == "error"]
    sources = events[0][1]
    assert sources["route"]["retrieval_debug"] == {
        "candidate_k": 28,
        "intent_targets": {"skill": 5, "voice": 2},
        "coverage_shortfall": {"skill": 0},
    }
    assert "metadata" not in sources["failure_actions"][0]
    serialized = json.dumps(events, ensure_ascii=False)
    for marker in (
        "prompt-secret",
        "content-secret",
        "api-key-secret",
        "token-secret",
        "execution-plan-secret",
        "query-planner-secret",
        "planner-secret",
        "camel-",
        "pascal-",
        "acronym-",
        "bytes-secret",
        "unknown-object-secret",
        "D:/private",
        "C:\\private",
        "E:\\private",
        "local_relpath",
    ):
        assert marker not in serialized


def test_route_normalizer_filters_unsafe_intent_values_and_count_keys():
    from backend.schemas import normalize_route, sanitize_transport_value

    route = {
        "name": "rag_grounded",
        "intent": "skill",
        "requested_intents": [
            "skill",
            "D:\\private\\intent",
            "voice",
            "file://private/intent",
            "system_prompt",
            "execution_plan",
            "query_planner",
            "skill/path",
            "unknown_intent",
            7,
        ],
        "retrieval_debug": {
            "candidate_k": 28,
            "intent_targets": {
                "skill": 5,
                "voice": 2,
                "D:\\private\\intent": 9,
                "file://private/intent": 8,
                "system_prompt": 7,
                "execution_plan": 6,
                "query_planner": 5,
                "skill/path": 4,
                "unknown_intent": 3,
                "item": "3",
            },
            "coverage_shortfall": {
                "skill": 0,
                "voice": 1,
                "C:\\private\\voice": 2,
            },
        },
    }

    normalized = normalize_route(route)

    assert normalized["requested_intents"] == ["skill", "voice"]
    assert normalized["retrieval_debug"] == {
        "candidate_k": 28,
        "intent_targets": {"skill": 5, "voice": 2},
        "coverage_shortfall": {"skill": 0, "voice": 1},
    }
    serialized = json.dumps(normalized, ensure_ascii=False)
    assert "file://" not in serialized
    assert ":\\" not in serialized
    assert "/path" not in serialized
    assert "prompt" not in serialized
    assert "plan" not in serialized

    nested = sanitize_transport_value({
        "safe": {
            "execution_plan": "plan-secret",
            "query_planner": "planner-secret",
            "release_planner_state": "planner-state-secret",
            "queryPlan": "camel-plan-secret",
            "ExecutionPlan": "pascal-plan-secret",
            "plannerState": "camel-planner-secret",
            "rawContent": "camel-content-secret",
            "apiKey": "camel-api-secret",
            "localRelpath": "camel-relpath-secret",
            "APIKey": "acronym-api-secret",
            "XMLPlannerState": "acronym-planner-secret",
            "pageSize": 8,
            "totalLines": 12,
            "nextCursor": "opaque-next-cursor",
            "value": "kept",
        },
    })
    assert nested == {"safe": {
        "pageSize": 8,
        "totalLines": 12,
        "nextCursor": "opaque-next-cursor",
        "value": "kept",
    }}


def test_transport_sanitizer_preserves_allowlisted_planner_stage_timings():
    from backend.schemas import sanitize_transport_value

    sanitized = sanitize_transport_value({
        "timing": {
            "stage_ms": {
                "planner.llm": 10.0,
                "planner.normalize": 2.0,
                "answer.llm": 20.0,
                "planner.secret": 99.0,
            }
        }
    })

    assert sanitized["timing"]["stage_ms"] == {
        "planner.llm": 10.0,
        "planner.normalize": 2.0,
        "answer.llm": 20.0,
    }


def test_media_normalizer_preserves_v3_binding_identity_and_semantics():
    from backend.schemas import normalize_media_items

    normalized = normalize_media_items([{
        "binding_id": "binding:sha256:" + "1" * 64,
        "resource_id": "resource:sha256:" + "a" * 64,
        "media_id": "media:sha1:" + "b" * 40,
        "asset_id": "legacy-asset-id",
        "asset_type": "image",
        "media_role": "collection_item",
        "url": "https://media.example/shared.webp",
        "section": "collection",
        "source_binding_token": "character-data:1001:type2:0",
        "owner_entity_id": "character:1001",
        "owner_page_id": "char:1001",
        "variant": "base",
        "skin_id": "skin:1",
    }])

    assert normalized[0]["asset_id"] == normalized[0]["binding_id"]
    assert normalized[0]["resource_id"] == "resource:sha256:" + "a" * 64
    assert normalized[0]["media_id"] == "media:sha1:" + "b" * 40
    assert normalized[0]["media_role"] == "collection_item"
    assert normalized[0]["source_binding_token"] == "character-data:1001:type2:0"


def test_media_panel_models_use_literal_discriminators_and_list_factories():
    from backend.schemas import AskResponse, LegacyVideoPanel, VoicePanelPage

    voice_schema = VoicePanelPage.model_json_schema()
    video_schema = LegacyVideoPanel.model_json_schema()

    assert voice_schema["properties"]["type"]["const"] == "voice"
    assert voice_schema["properties"]["grouping"]["const"] == "voice_line"
    assert video_schema["properties"]["type"]["const"] == "video"
    for field in (
        "assets",
        "media",
        "omitted_actions",
        "failure_actions",
        "media_panels",
    ):
        assert AskResponse.model_fields[field].default_factory is list


def test_normalize_media_panels_keeps_only_typed_voice_and_legacy_video():
    from backend.schemas import LegacyVideoPanel, VoiceLineGroup, normalize_media_panels
    from pydantic import ValidationError

    voice_page = _first_voice_page()
    video_item = {
        "media_id": "video-one",
        "asset_id": "video-one",
        "asset_type": "video",
        "role": "video",
        "url": "https://media.example/video.mp4",
    }
    valid_video = {"type": "video", "items": [video_item]}
    empty_voice_variants = json.loads(json.dumps(voice_page))
    empty_voice_variants["lines"][0]["variants"] = []
    malformed = [
        {"type": "voice", "items": voice_page["lines"][0]["variants"]},
        {**voice_page, "grouping": "variant"},
        {**voice_page, "type": "video"},
        {"type": "video", "items": voice_page["lines"][0]["variants"]},
        {"type": "video", "items": [video_item], "grouping": "voice_line"},
        {"type": "audio", "items": []},
        empty_voice_variants,
        {"type": "video", "items": []},
        {"type": "voice", "grouping": "voice_line", "lines": [], "items": []},
        {"unexpected": "panel"},
    ]

    normalized = normalize_media_panels([voice_page, valid_video, *malformed])

    assert [panel["type"] for panel in normalized] == ["voice", "video"]
    assert normalized[0]["grouping"] == "voice_line"
    assert normalized[0]["lines"][0]["variants"][0]["asset_type"] == "voice"
    assert normalized[1]["items"][0]["asset_type"] == "video"
    with pytest.raises(ValidationError):
        VoiceLineGroup(voice_line_id="voice:empty", title="Empty", variants=[])
    with pytest.raises(ValidationError):
        LegacyVideoPanel(type="video", items=[])
