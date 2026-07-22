"""测试共享 fixtures 与 mocks。"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from src.rag.conversation import ConversationMemoryStore
from src.rag.citations import build_source_map
from src.rag.contracts import (
    CitationValidation,
    FrozenRetrievalPacket,
    ResponsePacket,
    RouteAuthorization,
    RouteDecision,
)
from src.rag.query_plan import requested_intents


CONVERSATION_ID = "00000000-0000-4000-8000-000000000001"


class ExecutionAdapter:
    """Test-only adapter for legacy static doubles; production requires execute()."""

    def __init__(self, target):
        self.target = target

    def __getattr__(self, name):
        return getattr(self.target, name)

    def execute(
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
        kwargs = {
            "question": question,
            "category": category,
            "route_options": route_options,
            "action_payload": action_payload,
            "conversation": conversation,
        }
        if hasattr(self.target, "ask"):
            result = _call_supported(self.target.ask, kwargs)
        elif hasattr(self.target, "retrieve"):
            result = _call_supported(self.target.retrieve, kwargs)
        else:
            sources = self.target._retriever.search(question, category=category)
            result = {"sources": sources, "context": "\n\n".join(
                str(item.get("content") or "") for item in sources
            )}

        result = dict(result)
        raw_sources = list(result.get("sources", []))
        sources, source_map = build_source_map(raw_sources)
        plan = result.get("plan") or result.get("_conversation_plan") or SimpleNamespace(
            original_query=question,
            normalized_query=question,
            entity=(raw_sources[0].get("name") if raw_sources else None),
            entity_type=(raw_sources[0].get("entity_type") if raw_sources else None),
            entity_id=(raw_sources[0].get("entity_id") if raw_sources else None),
            intent="general",
            secondary_intents=(),
            context_rewrite_mode="planner" if getattr(conversation, "turns", ()) else "none",
        )
        intents = requested_intents(plan)
        route = dict(result.get("route") or {})
        route.setdefault("name", "rag_grounded")
        route.setdefault("intent", intents[0] if intents else "general")
        route.setdefault("entity", getattr(plan, "entity", None))
        route.setdefault("requested_intents", list(intents))
        route.setdefault("semantic_intents", list(intents))
        route.setdefault("proposed_route", route["name"])
        route.setdefault("effective_route", route["name"])
        route.setdefault("retrieval_outcome", "sufficient" if sources else "empty")
        route.setdefault(
            "route_reason",
            "grounded_sufficient" if sources else "grounded_empty",
        )
        authorization = RouteAuthorization(
            semantic_intents=intents,
            proposed_route=route["proposed_route"],
            allow_free_supplement_after_empty=False,
            force_free_supplement=False,
            authorization_reason="test_fixture",
        )
        decision = RouteDecision(
            authorization=authorization,
            retrieval_outcome=route["retrieval_outcome"],
            effective_route=route["effective_route"],
            route_reason=route["route_reason"],
        )

        ready = bool(_call_supported(self.target.llm_ready, {})) if hasattr(self.target, "llm_ready") else True
        free = bool(result.get("free_supplement", False))
        if "answer" in result:
            answer = str(result["answer"])
        elif not ready:
            from src.rag.chain import _API_KEY_EMPTY_MSG
            answer = _API_KEY_EMPTY_MSG
        elif not sources and not free:
            from src.rag.chain import _EMPTY_RETRIEVAL_MSG
            answer = _EMPTY_RETRIEVAL_MSG
        elif hasattr(self.target, "_stream_llm"):
            chunks = _call_supported(self.target._stream_llm, {
                "question": question,
                "context": str(result.get("context", "")),
                "free_supplement": free,
                "conversation": conversation,
            })
            answer = "".join(
                str(chunk.content if hasattr(chunk, "content") else chunk)
                for chunk in chunks
            )
        else:
            answer = "fixture answer"
        if trace is not None:
            trace.mark_model_first_token()

        turn_outcome = result.get("_turn_outcome")
        if turn_outcome not in {"grounded", "ungrounded", "not_committable"}:
            turn_outcome = "ungrounded" if free and ready else (
                "grounded" if sources and ready else "not_committable"
            )
        grounding_mode = turn_outcome if turn_outcome in {"grounded", "ungrounded"} else "none"
        packet = FrozenRetrievalPacket(
            plan=plan,
            entity_ref=None,
            route_decision=decision,
            requested_intents=intents,
            sources=sources,
            source_map=source_map,
            media=tuple(result.get("media", result.get("assets", ()))),
            media_panels=tuple(result.get("media_panels", ())),
            context=str(result.get("context", "")),
            diagnostics={"route": route},
            omitted_actions=tuple(result.get("omitted_actions", ())),
            failure_actions=tuple(result.get("failure_actions", ())),
            planning_status=str(result.get("planning_status", "")),
            planning_warning=str(result.get("planning_warning", "")),
            planning_error=str(result.get("planning_error", "")),
            assets=tuple(result.get("assets", ())),
        )
        response_packet = ResponsePacket(
            retrieval_packet=packet,
            answer=answer,
            grounding_mode=grounding_mode,
            citation_validation=CitationValidation(valid=True),
            memory_info={
                "status": memory_status,
                "turns_used": memory_turns_used,
                "rewrite_mode": str(getattr(plan, "context_rewrite_mode", "none") or "none"),
            },
            turn_outcome=turn_outcome,
        )
        if trace is not None:
            trace.mark_validated_ready()
        return response_packet


def _call_supported(callable_obj, kwargs):
    parameters = inspect.signature(callable_obj).parameters
    return callable_obj(**{key: value for key, value in kwargs.items() if key in parameters})


class MockVectorstore:
    """模拟 Chroma 向量库,提供 count 与 similarity_search。"""

    def __init__(self, doc_counts: dict[str, int] | None = None,
                 docs_by_category: dict[str, list[Document]] | None = None) -> None:
        self._doc_counts = doc_counts or {}
        self._docs_by_category = docs_by_category or {}
        # 默认文档
        if not self._docs_by_category:
            self._docs_by_category = {
                "人物": [
                    Document(page_content="塞梅尔维斯是维拉阵营的神秘学家,擅长使用火焰神秘术。" * 3,
                             metadata={"name": "塞梅尔维斯", "category": "人物",
                                       "source": "100-UTTU人物辑录/塞梅尔维斯.md"}),
                    Document(page_content="曲娘是神秘学家,经营一家酒馆。" * 3,
                             metadata={"name": "曲娘", "category": "人物",
                                       "source": "100-UTTU人物辑录/曲娘.md"}),
                ],
            }

    class _Collection:
        def __init__(self, outer):
            self._outer = outer

        def count(self, where=None):
            # 真实 ChromaDB 的 Collection.count() 不接受 where 参数
            if where is not None:
                raise TypeError(
                    "count() got an unexpected keyword argument 'where'"
                )
            return sum(self._outer._doc_counts.values())

        def get(self, where=None, include=None, limit=None):
            # 模拟真实 ChromaDB get 语义
            include = include or []
            if where and "category" in where:
                cat = where["category"]
                # include=[] 表示只计数,返回 _doc_counts 数量的 ids
                if not include:
                    n = self._outer._doc_counts.get(cat, 0)
                    return {"ids": [f"id-{i}" for i in range(n)]}
                # include 含 documents/metadatas,返回实际文档
                docs = self._outer._docs_by_category.get(cat, [])
            else:
                if not include:
                    n = sum(self._outer._doc_counts.values())
                    return {"ids": [f"id-{i}" for i in range(n)]}
                docs = []
                for cat_docs in self._outer._docs_by_category.values():
                    docs.extend(cat_docs)
            if limit:
                docs = docs[:limit]
            return {
                "ids": [f"id-{i}" for i in range(len(docs))],
                "documents": [d.page_content for d in docs],
                "metadatas": [d.metadata for d in docs],
            }

    @property
    def _collection(self):
        return MockVectorstore._Collection(self)

    def similarity_search(self, query: str, k: int = 4, filter=None):
        cat = (filter or {}).get("category")
        docs = self._docs_by_category.get(cat, [])
        return docs[:k]

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, filter=None):
        docs = self.similarity_search(query, k=k, filter=filter)
        return [(d, 0.5) for d in docs]


class MockChain:
    """模拟 RAGChain,记录调用参数,返回固定流式 token。"""

    def __init__(self, stream_tokens: list[str], llm_ready: bool = True,
                 retriever_raises: Exception | None = None) -> None:
        self._tokens = stream_tokens
        self._ready = llm_ready
        self.last_category: str | None = None
        self._retriever = self._MockRetriever(retriever_raises)

    class _MockRetriever:
        def __init__(self, raises: Exception | None = None):
            self._raises = raises

        def search(self, query: str, k=None, category=None):
            if self._raises is not None:
                raise self._raises
            return [{
                "name": "塞梅尔维斯", "category": category or "人物",
                "source": "mock.md", "score": 0.6,
                "content": "模拟内容",
            }]

    def llm_ready(self) -> bool:
        return self._ready

    def execute(self, *args, **kwargs):
        return ExecutionAdapter(self).execute(*args, **kwargs)

    def _stream_llm(self, question: str, context: str):
        from langchain_core.messages import AIMessageChunk
        for t in self._tokens:
            yield AIMessageChunk(content=t)


class MemoryChain:
    def __init__(self) -> None:
        self.projections = []

    def _plan(self, question, conversation):
        turns = tuple(getattr(conversation, "turns", ()) or ())
        intent = "skill" if "技能" in question else "intro"
        return SimpleNamespace(
            original_query=question,
            normalized_query=f"角色甲 {intent}",
            entity="角色甲",
            entity_type="character",
            intent=intent,
            secondary_intents=(),
            context_rewrite_mode="planner" if turns else "none",
        )

    def execute(self, *args, **kwargs):
        return ExecutionAdapter(self).execute(*args, **kwargs)

    def ask(
        self,
        question,
        category=None,
        route_options=None,
        action_payload=None,
        conversation=None,
    ):
        self.projections.append(conversation)
        plan = self._plan(question, conversation)
        return {
            "answer": f"回答:{plan.normalized_query}",
            "sources": [{
                "name": "角色甲",
                "category": category or "人物",
                "source": "fixture.md",
                "score": 1.0,
                "content": "fixture content",
                "parent_id": "char:a/skills",
            }],
            "assets": [],
            "media": [],
            "route": {
                "name": "rag_grounded",
                "intent": plan.intent,
                "entity": plan.entity,
                "requested_intents": [plan.intent],
            },
            "_conversation_plan": plan,
            "_turn_outcome": "grounded",
        }

    def retrieve(
        self,
        question,
        category=None,
        route_options=None,
        action_payload=None,
        conversation=None,
    ):
        self.projections.append(conversation)
        plan = self._plan(question, conversation)
        return {
            "plan": plan,
            "sources": [{
                "name": "角色甲",
                "category": category or "人物",
                "source": "fixture.md",
                "score": 1.0,
                "content": "fixture content",
                "parent_id": "char:a/skills",
            }],
            "context": "[角色甲] fixture content",
            "assets": [],
            "media": [],
            "route": {
                "name": "rag_grounded",
                "intent": plan.intent,
                "entity": plan.entity,
                "requested_intents": [plan.intent],
            },
            "free_supplement": False,
        }

    def llm_ready(self):
        return True

    def _stream_llm(self, question, context, free_supplement=False, conversation=None):
        from langchain_core.messages import AIMessageChunk

        yield AIMessageChunk(content="回答:")
        yield AIMessageChunk(content="角色甲")


@pytest.fixture
def client_with_memory_chain(monkeypatch):
    from backend import main as main_mod

    previous_state = main_mod._state
    chain = MemoryChain()
    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": chain,
        "memory": ConversationMemoryStore(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    try:
        with TestClient(main_mod.app) as client:
            yield client
    finally:
        main_mod._state = previous_state
