from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.rag.chain import RAGChain
from src.rag.execution import RAGExecutionService
from src.rag.local_responses import render_local_response
from src.rag.query_plan import QueryPlanner


def test_assistant_meta_is_deterministic_and_project_scoped():
    answer = render_local_response("assistant_meta", "你是谁", reason="local_assistant_meta")

    assert "AI 助手" in answer
    assert "重返未来：1999" in answer
    assert "知识库" in answer


def test_smalltalk_never_claims_human_experience():
    answer = render_local_response(
        "social_smalltalk",
        "你晚饭吃了吗",
        reason="local_social_smalltalk",
    )

    assert "不吃饭" in answer
    assert not any(marker in answer for marker in ("我吃了", "我睡", "我看见", "我的身体"))


def test_denied_general_uses_a_capability_boundary_not_an_entity_error():
    answer = render_local_response(
        "general_open",
        "中国首都是什么",
        reason="general_open_denied",
    )

    assert "自由补充" in answer
    assert "实体识别失败" not in answer
    assert "数据库为空" not in answer


class Bomb:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        raise AssertionError("local response must not invoke LLM")

    def search(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("local response must not retrieve")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("你是谁", "AI 助手"),
        ("你晚饭吃了吗", "不吃饭"),
    ],
)
def test_local_chain_succeeds_without_retriever_or_llm(query, expected):
    bomb_retriever = Bomb()
    bomb_llm = Bomb()
    chain = RAGChain.__new__(RAGChain)
    chain._planner_llm = bomb_llm
    chain._query_planner = QueryPlanner(None)
    chain._retriever = bomb_retriever
    chain._llm = None
    chain._asset_registry = SimpleNamespace()
    chain._execution_service = RAGExecutionService(chain)

    result = chain.ask(query)

    assert expected in result["answer"]
    assert result["sources"] == []
    assert result["assets"] == []
    assert result["media"] == []
    assert result["route"]["effective_route"] == "local_response"
    assert result["route"]["retrieval_outcome"] == "not_applicable"
    assert bomb_retriever.calls == 0
    assert bomb_llm.calls == 0
