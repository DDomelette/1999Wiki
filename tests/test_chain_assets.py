from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.assets.huiji_registry import HuijiMediaRegistry, MediaRetrievalBundle
from src.rag.chain import RAGChain
from src.rag.conversation import build_conversation_turn, project_turns
from src.rag.ownership import OwnershipViolation


class FakePlanner:
    def plan(self, question, category=None, conversation=None):
        return SimpleNamespace(normalized_query=question, intent="skill", entity="玛蒂尔达")


class FakeRetriever:
    def search(self, query, category=None, query_plan=None):
        return [{
            "name": "玛蒂尔达",
            "category": "人物",
            "source": "100/玛蒂尔达.md",
            "score": 1.0,
            "content": "神秘术内容",
            "heading_path": "玛蒂尔达 > 神秘术",
            "chunk_index": 1,
            "retrieval_stage": "entity_packet",
        }]


class FakeRegistry:
    def find_for_retrieval(self, plan, sources):
        return [{"asset_id": "a2", "role": "skill", "url": "http://minio/a2.png", "alt": "神秘术"}]


def _chain_cfg(tmp_path: Path):
    return SimpleNamespace(
        llm=SimpleNamespace(api_key=""),
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        paths=SimpleNamespace(project_root=tmp_path),
    )


def test_chain_retrieve_returns_assets(tmp_path):
    cfg = _chain_cfg(tmp_path)
    chain = RAGChain(cfg, FakeRetriever())
    chain._query_planner = FakePlanner()
    chain._asset_registry = FakeRegistry()

    result = chain.retrieve("玛蒂尔达的技能是什么", category="人物")

    assert result["assets"] == [{"asset_id": "a2", "role": "skill", "url": "http://minio/a2.png", "alt": "神秘术"}]
    assert result["media"] == result["assets"]


def test_chain_retrieve_returns_actions_and_route(tmp_path):
    cfg = _chain_cfg(tmp_path)
    retriever = FakeRetriever()
    retriever.last_omitted_actions = [{
        "label": "全部技能",
        "query": "介绍玛蒂尔达的全部技能",
        "entity": "玛蒂尔达",
        "entity_type": "character",
        "intent": "skill",
        "packet_policy": "section_detail",
        "target_parent_id": "char:3041/skills",
    }]
    retriever.last_route_debug = {"route": "rag_grounded", "intent": "skill", "entity": "玛蒂尔达"}
    retriever.last_expansion_debug = {"retained_count": 1}
    chain = RAGChain(cfg, retriever)
    chain._query_planner = FakePlanner()
    chain._asset_registry = FakeRegistry()

    result = chain.retrieve("介绍一下玛蒂尔达", category="人物")

    assert result["route"] == {
        "name": "rag_grounded",
        "confidence": 0.0,
        "intent": "skill",
        "entity": "玛蒂尔达",
        "requested_intents": ["skill"],
        "semantic_intents": ["skill"],
        "proposed_route": "rag_grounded",
        "effective_route": "rag_grounded",
        "retrieval_outcome": "sufficient",
        "route_reason": "grounded_sufficient",
        "retrieval_debug": {},
    }
    assert result["omitted_actions"][0]["target_parent_id"] == "char:3041/skills"
    assert result["failure_actions"] == []
    assert result["media_panels"] == []


class BundleRegistry:
    def __init__(self):
        self.find_calls = []
        self.page_calls = []

    def find_bundle_for_retrieval(self, plan, sources):
        self.find_calls.append((plan, sources))
        voice_variants = (
            {
                "media_id": "voice-zh",
                "asset_id": "voice-zh",
                "asset_type": "voice",
                "role": "voice",
                "url": "https://media.example/voice-zh.mp3",
                "language": "zh",
            },
            {
                "media_id": "voice-en",
                "asset_id": "voice-en",
                "asset_type": "voice",
                "role": "voice",
                "url": "https://media.example/voice-en.mp3",
                "language": "en",
            },
        )
        voice_page = {
            "type": "voice",
            "grouping": "voice_line",
            "entity_id": "char:test",
            "lines": [{
                "voice_line_id": "char:test/voice:001",
                "title": "Line one",
                "variants": list(voice_variants),
            }],
            "page_size": 1,
            "total_lines": 3,
            "has_more": True,
            "next_cursor": "opaque-cursor",
        }
        skill = {
            "media_id": "skill-image",
            "asset_id": "skill-image",
            "asset_type": "skill",
            "role": "skill",
            "url": "https://media.example/skill.png",
            "alt": "Skill",
        }
        video = {
            "media_id": "video-one",
            "asset_id": "video-one",
            "asset_type": "video",
            "role": "video",
            "url": "https://media.example/video.mp4",
            "alt": "Video",
        }
        return MediaRetrievalBundle(
            items=(skill, *voice_variants, video),
            panels=(voice_page,),
        )

    def get_voice_page(self, cursor):
        self.page_calls.append(cursor)
        return {"next_cursor": None, "lines": []}


class MultiIntentPlanner:
    def __init__(self):
        self.calls = 0

    def plan(self, question, category=None, conversation=None):
        self.calls += 1
        return SimpleNamespace(
            normalized_query=question,
            intent="skill",
            secondary_intents=("voice",),
            entity="Test Character",
            confidence=0.75,
            route="rag_grounded",
        )


class DebugRetriever(FakeRetriever):
    def __init__(self):
        self.search_calls = 0
        self.last_route_debug = {
            "requested_intents": ["skill", "voice"],
            "candidate_k": 28,
            "required_source_count": 7,
            "intent_targets": {"skill": 5, "voice": 2},
            "intent_retained": {"skill": 5, "voice": 2},
            "coverage_shortfall": {"skill": 0, "voice": 0},
            "chars_used": 1200,
            "max_sources": 7,
            "prompt": "must-not-leak",
            "api_key": "must-not-leak",
            "local_relpath": "D:\\private\\artifact.jsonl",
        }

    def search(self, query, category=None, query_plan=None):
        self.search_calls += 1
        return super().search(query, category=category, query_plan=query_plan)


def test_huiji_bundle_is_used_once_and_keeps_mixed_first_page_media(tmp_path):
    cfg = _chain_cfg(tmp_path)
    retriever = DebugRetriever()
    planner = MultiIntentPlanner()
    registry = BundleRegistry()
    chain = RAGChain(cfg, retriever)
    chain._query_planner = planner
    chain._asset_registry = registry

    result = chain.retrieve("show skills and voices", category="characters")

    assert len(registry.find_calls) == 1
    assert [item["media_id"] for item in result["assets"]] == [
        "skill-image",
        "voice-zh",
        "voice-en",
        "video-one",
    ]
    assert result["media"] == result["assets"]
    assert result["media_panels"][0]["type"] == "voice"
    assert result["media_panels"][0]["lines"][0]["voice_line_id"] == "char:test/voice:001"
    assert result["media_panels"][1] == {
        "type": "video",
        "items": [result["assets"][-1]],
    }
    assert result["route"]["requested_intents"] == ["skill", "voice"]
    assert result["route"]["retrieval_debug"] == {
        "candidate_k": 28,
        "required_source_count": 7,
        "intent_targets": {"skill": 5, "voice": 2},
        "intent_retained": {"skill": 5, "voice": 2},
        "coverage_shortfall": {"skill": 0, "voice": 0},
        "chars_used": 1200,
        "max_sources": 7,
    }


def test_get_voice_page_forwards_only_to_loaded_registry(tmp_path):
    cfg = _chain_cfg(tmp_path)
    retriever = DebugRetriever()
    planner = MultiIntentPlanner()
    registry = BundleRegistry()
    chain = RAGChain(cfg, retriever)
    chain._query_planner = planner
    chain._asset_registry = registry

    result = chain.get_voice_page("opaque-cursor")

    assert result == {"next_cursor": None, "lines": []}
    assert registry.page_calls == ["opaque-cursor"]
    assert planner.calls == 0
    assert retriever.search_calls == 0


def test_chain_constructs_only_huiji_media_registry(tmp_path):
    cfg = _chain_cfg(tmp_path)
    chain = RAGChain(cfg, FakeRetriever())

    assert isinstance(chain._asset_registry, HuijiMediaRegistry)


def test_route_debug_accepts_only_strict_known_shapes(tmp_path):
    class UnknownText:
        def __str__(self):
            return "unknown-route-secret"

    cfg = _chain_cfg(tmp_path)
    retriever = DebugRetriever()
    retriever.last_route_debug = {
        "requested_intents": [
            "skill",
            "D:\\private\\intent",
            "voice",
            "file://private/intent",
            "execution_plan",
            7,
        ],
        "candidate_k": 28,
        "required_source_count": "7",
        "intent_candidates": {
            "skill": 5,
            "voice": 2,
            "D:\\private\\intent": 9,
            "file://private/intent": 8,
            "query_planner": 7,
        },
        "intent_targets": {"skill": 5, "voice": "2"},
        "intent_retained": {"skill": 5, "voice": 2},
        "coverage_shortfall": {"skill": 0, "voice": 0},
        "chars_used": True,
        "max_sources": 7,
        "route": UnknownText(),
        "intent": Path("D:/private/intent.txt"),
        "entity": b"private-entity",
        "system_prompt": "do not expose",
        "path": Path("D:/private/index.jsonl"),
    }
    chain = RAGChain(cfg, retriever)
    chain._query_planner = MultiIntentPlanner()
    chain._asset_registry = BundleRegistry()

    route = chain.retrieve("show skills and voices")["route"]

    assert route["requested_intents"] == ["skill", "voice"]
    assert route["name"] == "rag_grounded"
    assert route["intent"] == "skill"
    assert route["entity"] == "Test Character"
    assert route["retrieval_debug"] == {
        "candidate_k": 28,
        "intent_candidates": {"skill": 5, "voice": 2},
        "intent_targets": {"skill": 5},
        "intent_retained": {"skill": 5, "voice": 2},
        "coverage_shortfall": {"skill": 0, "voice": 0},
        "max_sources": 7,
    }


def _completed_turn(*, entity="角色甲", grounding_mode="grounded"):
    return build_conversation_turn(
        original_question=f"介绍一下{entity}",
        standalone_question=f"{entity}的介绍",
        answer=f"{entity}的历史回答",
        entity=entity,
        entity_type="character",
        requested_intents=("intro",),
        category="人物",
        grounding_mode=grounding_mode,
        completed_at=datetime.now(timezone.utc),
    )


class ConversationPlanner:
    def __init__(self):
        self.conversations = []

    def plan(self, question, category=None, conversation=None):
        self.conversations.append(conversation)
        return SimpleNamespace(
            original_query=question,
            normalized_query="角色甲 技能",
            intent="skill",
            secondary_intents=(),
            entity="角色甲",
            entity_type="character",
            entity_id="role-a",
            resolution_mode="history_exact",
            confidence=0.9,
            route="rag_grounded",
            route_options={},
            packet_policy="section_detail",
            target_parent_id=None,
            planning_status="llm",
            planning_warning="",
            planning_error="",
        )


class AnswerLLM:
    def __init__(self):
        self.invoke_count = 0
        self.messages = []

    def invoke(self, messages):
        self.invoke_count += 1
        self.messages = list(messages)
        return SimpleNamespace(content="本轮回答 [S01]")


def test_chain_passes_one_projection_to_planner_and_answer_model(tmp_path):
    cfg = _chain_cfg(tmp_path)
    planner = ConversationPlanner()
    llm = AnswerLLM()
    chain = RAGChain(cfg, FakeRetriever())
    chain._query_planner = planner
    chain._asset_registry = FakeRegistry()
    chain._llm = llm
    projection = project_turns([_completed_turn()])

    result = chain.ask(
        "她的技能呢",
        category="人物",
        conversation=projection,
    )

    assert planner.conversations == [projection]
    assert llm.invoke_count == 1
    assert isinstance(llm.messages[1], HumanMessage)
    assert llm.messages[1].content == "介绍一下角色甲"
    assert isinstance(llm.messages[2], AIMessage)
    assert llm.messages[2].content == (
        "[Historical conversation; not current evidence]\n角色甲的历史回答"
    )
    assert result["_turn_outcome"] == "grounded"
    assert result["_conversation_plan"].entity == "角色甲"


class ActionRecordingRetriever(FakeRetriever):
    def __init__(self):
        self.plan = None
        self.last_omitted_actions = []
        self.last_route_debug = {}

    def search(self, query, category=None, query_plan=None):
        self.plan = query_plan
        return super().search(query, category=category, query_plan=query_plan)


def test_action_payload_cannot_override_history_owner(tmp_path):
    cfg = _chain_cfg(tmp_path)
    retriever = ActionRecordingRetriever()
    chain = RAGChain(cfg, retriever)
    chain._query_planner = ConversationPlanner()
    chain._asset_registry = FakeRegistry()
    projection = project_turns([_completed_turn()])

    with pytest.raises(OwnershipViolation, match="owner"):
        chain.retrieve(
            "继续",
            category="人物",
            conversation=projection,
            action_payload={
                "action_type": "expand_parent",
                "entity": "角色乙",
                "entity_type": "character",
                "entity_id": "role-b",
                "intent": "voice",
                "target_parent_id": "char:role-b/voice",
            },
        )


def test_same_owner_action_sets_parent_without_overriding_semantic_intent(tmp_path):
    cfg = _chain_cfg(tmp_path)
    retriever = ActionRecordingRetriever()
    chain = RAGChain(cfg, retriever)
    chain._query_planner = ConversationPlanner()
    chain._asset_registry = FakeRegistry()

    result = chain.retrieve(
        "继续",
        category="人物",
        action_payload={
            "action_type": "expand_parent",
            "entity": "角色甲",
            "entity_type": "character",
            "entity_id": "role-a",
            "intent": "voice",
            "target_parent_id": "char:role-a/skills",
        },
    )

    assert retriever.plan is result["plan"]
    assert retriever.plan.entity == "角色甲"
    assert retriever.plan.entity_type == "character"
    assert retriever.plan.entity_id == "role-a"
    assert retriever.plan.intent == "skill"
    assert retriever.plan.target_parent_id == "char:role-a/skills"
