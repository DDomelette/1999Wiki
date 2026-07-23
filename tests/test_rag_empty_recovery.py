from __future__ import annotations

from types import SimpleNamespace

from src.rag.chain import RAGChain
from src.rag.retriever import RetrievalExecutionError


class EmptyRetriever:
    last_omitted_actions: list[dict] = []
    last_route_debug: dict = {"route": "rag_grounded", "intent": "general", "entity": None}

    def __init__(self):
        self.search_calls = 0

    def search(self, query, category=None, query_plan=None):
        self.search_calls += 1
        return []


class NonEmptyRetriever:
    last_omitted_actions: list[dict] = []
    last_route_debug: dict = {"route": "rag_grounded", "intent": "intro", "entity": "十四行诗"}

    def __init__(self):
        self.search_calls = 0

    def search(self, query, category=None, query_plan=None):
        self.search_calls += 1
        return [{
            "name": "十四行诗",
            "category": "人物",
            "source": "Data:Char/3023.json",
            "score": 1.0,
            "content": "知识库命中的内容",
        }]


class EmptyRegistry:
    def find_for_retrieval(self, plan, sources):
        return []


class Planner:
    def plan(self, question, category=None, conversation=None):
        return SimpleNamespace(
            original_query=question,
            normalized_query=question,
            intent="general",
            entity=None,
            entity_type="",
            route="rag_grounded",
            route_options={},
            packet_policy="default",
            confidence=0.0,
            planning_status="llm",
            planning_warning="",
            planning_error="",
            secondary_intents=(),
        )


class UnresolvedSkillPlanner(Planner):
    def plan(self, question, category=None, conversation=None):
        plan = super().plan(question, category, conversation)
        plan.intent = "skill"
        return plan


class NoInvokeLLM:
    def __init__(self):
        self.invoked = False

    def invoke(self, messages):
        self.invoked = True
        raise AssertionError("empty grounded retrieval should not invoke LLM")


class RecordingLLM:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content="这是自由补充回答。")


def make_chain(tmp_path, llm, retriever=None):
    cfg = SimpleNamespace(
        llm=SimpleNamespace(api_key=""),
        assets=SimpleNamespace(
            public_base_url="/media",
            bucket_name="reverse1999-assets",
        ),
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    chain = RAGChain(cfg, retriever or EmptyRetriever())
    chain._query_planner = Planner()
    chain._asset_registry = EmptyRegistry()
    chain._llm = llm
    return chain


def test_empty_retrieval_returns_concise_refusal_and_structured_recovery_actions(tmp_path):
    llm = NoInvokeLLM()
    chain = make_chain(tmp_path, llm)

    result = chain.ask("数据库里没有的问题")

    assert "知识库中暂时没有找到足够资料" in result["answer"]
    assert "扩大范围重新搜索" not in result["answer"]
    assert "自由补充" not in result["answer"]
    assert [action["label"] for action in result["failure_actions"]] == [
        "扩大范围重新搜索",
        "使用自由补充重答",
    ]
    assert result["sources"] == []
    assert result["_turn_outcome"] == "not_committable"
    assert not llm.invoked


def test_unresolved_entity_section_query_asks_for_entity_name(tmp_path):
    llm = NoInvokeLLM()
    chain = make_chain(tmp_path, llm)
    chain._query_planner = UnresolvedSkillPlanner()

    result = chain.ask("那个角色的技能怎么样")

    assert result["answer"] == "请先明确要查询的角色或实体名称。"
    assert result["failure_actions"]
    assert not llm.invoked


def test_free_supplement_action_uses_llm_when_retrieval_is_empty(tmp_path):
    llm = RecordingLLM()
    retriever = EmptyRetriever()
    chain = make_chain(tmp_path, llm, retriever=retriever)

    result = chain.ask(
        "1999是什么游戏",
        action_payload={
            "label": "使用自由补充重答",
            "query": "1999是什么游戏",
            "intent": "llm_general",
            "packet_policy": "free_supplement",
        },
    )

    assert "未基于知识库检索结果" in result["answer"]
    assert "这是自由补充回答。" in result["answer"]
    assert result["failure_actions"] == []
    assert result["sources"] == []
    assert result["_turn_outcome"] == "ungrounded"
    assert retriever.search_calls == 0
    assert llm.messages is not None
    assert "不依赖知识库" in llm.messages[0].content


def test_free_supplement_toggle_does_not_bypass_retrieved_sources(tmp_path):
    llm = RecordingLLM()
    retriever = NonEmptyRetriever()
    chain = make_chain(tmp_path, llm, retriever=retriever)

    result = chain.ask(
        "介绍一下十四行诗",
        route_options={"free_supplement": True},
    )

    assert retriever.search_calls == 1
    assert "未基于知识库检索结果" not in result["answer"]
    assert result["sources"]
    assert result["route"]["effective_route"] == "rag_grounded"
    assert result["route"]["retrieval_outcome"] == "sufficient"
    assert result["assets"] == []
    assert result["media"] == []


def test_free_supplement_toggle_uses_llm_only_after_one_empty_retrieval(tmp_path):
    llm = RecordingLLM()
    retriever = EmptyRetriever()
    chain = make_chain(tmp_path, llm, retriever=retriever)

    result = chain.ask(
        "empty fixture",
        route_options={"free_supplement": True},
    )

    assert retriever.search_calls == 1
    assert result["route"]["effective_route"] == "llm_general"
    assert result["route"]["retrieval_outcome"] == "empty"
    assert result["_turn_outcome"] == "ungrounded"


def test_free_supplement_prompt_forbids_unverified_negative_facts(tmp_path):
    llm = RecordingLLM()
    chain = make_chain(tmp_path, llm)

    chain.ask("unknown fixture", route_options={"free_supplement": True})

    assert "不得断言官方资料中不存在" in llm.messages[0].content


def test_explicit_free_supplement_action_is_the_only_retrieval_bypass(tmp_path):
    llm = RecordingLLM()
    retriever = NonEmptyRetriever()
    chain = make_chain(tmp_path, llm, retriever=retriever)

    result = chain.ask(
        "force fixture",
        action_payload={"action_type": "force_free_supplement"},
    )

    assert retriever.search_calls == 0
    assert result["sources"] == []
    assert result["route"]["route_reason"] == "explicit_recovery_action"


def test_explicit_free_supplement_does_not_reuse_previous_retrieval_debug(tmp_path):
    llm = RecordingLLM()
    retriever = NonEmptyRetriever()
    retriever.last_route_debug = {
        "candidate_k": 999,
        "coverage_shortfall": {"skill": 9},
    }
    chain = make_chain(tmp_path, llm, retriever=retriever)

    result = chain.ask(
        "force fixture",
        action_payload={"action_type": "force_free_supplement"},
    )

    assert result["route"]["retrieval_debug"] == {}


class FailingRetriever:
    last_omitted_actions = []
    last_route_debug = {}

    def search(self, query, category=None, query_plan=None):
        raise RetrievalExecutionError("retrieval.dense", "ConnectionError")


def test_retrieval_dependency_failure_is_not_empty_or_free(tmp_path):
    llm = NoInvokeLLM()
    chain = make_chain(tmp_path, llm, retriever=FailingRetriever())

    result = chain.ask(
        "dependency failure fixture",
        route_options={"free_supplement": True},
    )

    assert result["route"]["retrieval_outcome"] == "failed"
    assert result["route"]["effective_route"] == "rag_grounded"
    assert result["route"]["route_reason"] == "retrieval_failed"
    assert result["_turn_outcome"] == "not_committable"
    assert "ConnectionError" not in result["answer"]
    assert not llm.invoked


class FailingLLM:
    def invoke(self, messages):
        raise RuntimeError("answer failure")


def test_answer_model_error_is_not_committable(tmp_path):
    chain = make_chain(tmp_path, FailingLLM(), retriever=NonEmptyRetriever())

    result = chain.ask("介绍一下十四行诗")

    assert result["_turn_outcome"] == "not_committable"
    assert result["_conversation_plan"] is not None
