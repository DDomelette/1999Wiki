from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.schemas import AskResponse
from src.rag.chain import RAGChain
from src.rag.contracts import CitationValidation, ResponsePacket
from src.rag.execution import AskExecutionInput, build_completed_turn
from src.rag.tracing import RequestTrace
from src.rag.serializers import (
    response_packet_to_public_dict,
    response_packet_to_sse_events,
    response_packet_to_sse_strings,
)


class _PlannerSpy:
    def __init__(self):
        self.calls = 0
        self.normalized_query = None
        self.secondary_intents = ()
        self.intent = "general"

    def plan(self, question, category=None, conversation=None, trace=None):
        del category, conversation
        self.calls += 1
        active = trace
        if active is not None:
            with active.span("planner.llm"):
                pass
            with active.span("planner.normalize"):
                pass
            with active.span("entity.resolve"):
                pass
        return SimpleNamespace(
            original_query=question,
            normalized_query=self.normalized_query or question,
            intent=self.intent,
            secondary_intents=self.secondary_intents,
            entity="Fixture",
            entity_type="fixture",
            entity_id="fixture-1",
            resolution_mode="current_exact",
            confidence=1.0,
            route="rag_grounded",
            planning_status="llm",
            planning_warning="",
            planning_error="",
            context_rewrite_mode="none",
        )


class _RetrieverSpy:
    last_route_debug = {}
    last_omitted_actions = []

    def __init__(self):
        self.calls = 0

    def search(self, query, category=None, query_plan=None, trace=None):
        del query, category, query_plan
        self.calls += 1
        if trace is not None:
            for stage in (
                "retrieval.structured",
                "retrieval.bm25",
                "retrieval.dense",
                "retrieval.fusion",
                "retrieval.rerank",
                "retrieval.expand",
                "retrieval.allocate",
            ):
                with trace.span(stage):
                    pass
        return [{
            "name": "Fixture",
            "category": "fixture",
            "source": "fixture.json",
            "score": 1.0,
            "content": "Evidence",
            "heading_path": "Fixture > Evidence",
            "child_id": "child-1",
            "parent_id": "parent-1",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
        }]


class _DuplicateRetrieverSpy(_RetrieverSpy):
    def search(self, query, category=None, query_plan=None, trace=None):
        row = super().search(query, category, query_plan, trace)
        return [row[0], dict(row[0])]


class _RegistrySpy:
    def __init__(self):
        self.calls = 0

    def find_for_retrieval(self, plan, sources):
        del plan, sources
        self.calls += 1
        return []


class _LLMSpy:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = 0
        self.messages = []

    def invoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        return SimpleNamespace(content=next(self.answers))


class _TransientAnswerLLM(_LLMSpy):
    def invoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            raise ConnectionError("temporary answer connection failure")
        return SimpleNamespace(content=next(self.answers))


def _chain(tmp_path, answers):
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
    retriever = _RetrieverSpy()
    chain = RAGChain(cfg, retriever)
    planner = _PlannerSpy()
    registry = _RegistrySpy()
    llm = _LLMSpy(answers)
    chain._query_planner = planner
    chain._asset_registry = registry
    chain._llm = llm
    return chain, planner, retriever, registry, llm


def test_execute_calls_each_business_stage_once(tmp_path):
    chain, planner, retriever, registry, llm = _chain(tmp_path, ["Answer [S01]"])

    packet = chain.execute("Question")

    assert isinstance(packet, ResponsePacket)
    assert planner.calls == 1
    assert retriever.calls == 1
    assert registry.calls == 1
    assert llm.calls == 1
    assert packet.citation_validation.valid is True


def test_composite_execute_retrieves_only_kb_and_serializes_safe_ordered_subtasks(tmp_path):
    chain, planner, retriever, registry, llm = _chain(tmp_path, ["Knowledge [S01]"])

    packet = chain.execute("你好，你是谁，请介绍一下十四行诗")
    public = response_packet_to_public_dict(packet)
    wire = AskResponse.model_validate(public)

    assert planner.calls == 1
    assert retriever.calls == 1
    assert registry.calls == 1
    assert llm.calls == 1
    assert [item["subtask_id"] for item in public["subtasks"]] == ["T01", "T02", "T03"]
    assert [item["task_type"] for item in public["subtasks"]] == [
        "social_smalltalk",
        "assistant_meta",
        "knowledge_base",
    ]
    assert public["route"]["name"] == "composite"
    assert public["sources"][0]["citation_id"] == "S01"
    assert packet.answer.index("T01") < packet.answer.index("T02") < packet.answer.index("T03")
    assert packet.grounding_mode == "mixed"
    assert packet.turn_outcome == "mixed"
    assert [item.subtask_id for item in wire.subtasks] == ["T01", "T02", "T03"]


def test_composite_duplicate_identical_sources_keep_one_aligned_citation(tmp_path):
    chain, _planner, _retriever, _registry, llm = _chain(
        tmp_path,
        ["Knowledge [S01]"],
    )
    duplicate_retriever = _DuplicateRetrieverSpy()
    chain._retriever = duplicate_retriever

    packet = chain.execute("你好，你是谁，请介绍一下十四行诗")

    kb_branch = packet.branch_results[2]
    assert duplicate_retriever.calls == 1
    assert llm.calls == 1
    assert kb_branch.status == "succeeded"
    assert kb_branch.source_ids == ("S01",)
    assert packet.citation_validation.valid is True
    assert [row["citation_id"] for row in packet.retrieval_packet.sources] == ["S01"]


def test_composite_recovery_action_requires_exact_subtask_binding(tmp_path):
    chain, _planner, retriever, _registry, _llm = _chain(tmp_path, ["unused"])

    with pytest.raises(ValueError, match="valid subtask_id"):
        chain.execute(
            "你好，你是谁，请介绍一下十四行诗",
            action_payload={
                "label": "扩大搜索",
                "query": "请介绍一下十四行诗",
                "action_type": "expand_search",
            },
        )

    assert retriever.calls == 0


def test_execute_retries_one_transient_answer_failure(tmp_path):
    chain, _planner, _retriever, _registry, _llm = _chain(tmp_path, ["unused"])
    transient = _TransientAnswerLLM(["Answer [S01]"])
    chain._llm = transient

    packet = chain.execute("Question")

    assert transient.calls == 2
    assert packet.answer == "Answer [S01]"
    assert packet.citation_validation.valid is True


def test_grounded_answer_preserves_original_semantics_and_adds_normalized_topic(tmp_path):
    chain, planner, _retriever, _registry, llm = _chain(tmp_path, ["Answer [S01]"])
    planner.normalized_query = "Normalized skill question"

    chain.execute("Prove a skill absent from the evidence")

    question = llm.messages[0][-1].content
    assert "Prove a skill absent from the evidence" in question
    assert "Normalized skill question" in question


def test_attached_media_is_exposed_to_answer_generation_as_system_metadata(tmp_path):
    chain, _planner, _retriever, registry, llm = _chain(tmp_path, ["Attached image [S01]"])
    registry.find_for_retrieval = lambda plan, sources: [{
        "media_id": "media:fixture-image",
        "asset_type": "portrait",
        "title": "Fixture portrait",
    }]

    chain.execute("Show the image")

    system_message = llm.messages[0][0].content
    assert "Fixture portrait" in system_message
    assert "media:fixture-image" in system_message
    assert "system metadata" in system_message.lower()


def test_media_only_answer_uses_deterministic_operational_summary(tmp_path):
    chain, planner, _retriever, registry, _llm = _chain(
        tmp_path,
        ["检索到的资料不足以完整回答 [S01]。"],
    )
    planner.intent = "media"
    registry.find_for_retrieval = lambda plan, sources: [
        {
            "media_id": "media:fixture-portrait",
            "asset_type": "portrait",
            "title": "Fixture portrait.webp",
        },
        {
            "media_id": "media:fixture-image",
            "asset_type": "image",
            "title": "Fixture image.webp",
        },
    ]

    packet = chain.execute("Fixture 的图片呢")

    assert packet.answer == (
        "当前检索来源对应 Fixture [S01]。\n\n"
        "系统已挂载 2 个图片附件；附件数量、类型和文件名来自系统媒体元数据，"
        "请在下方媒体区查看。"
    )
    assert "资料不足" not in packet.answer
    assert "Fixture portrait.webp" not in packet.answer


def test_grounded_answer_removes_unit_not_present_on_structured_rarity_value(tmp_path):
    chain, _planner, retriever, _registry, _llm = _chain(
        tmp_path,
        [
            "该角色是一位 **5**星角色，稀有度为 5星 [S01]。"
            "职业为 6（职业编号），伤害类型为 2（具体类型未说明）[S01]。"
        ],
    )
    retriever.search = lambda *args, **kwargs: [{
        "name": "Fixture",
        "category": "character",
        "source": "fixture.json",
        "score": 1.0,
        "content": "Fixture 角色资料\n稀有度: 5\n职业: 6\n伤害类型: 2",
        "heading_path": "Fixture > 基础资料",
        "child_id": "child-1",
        "parent_id": "parent-1",
        "entity_type": "fixture",
        "entity_id": "fixture-1",
    }]

    packet = chain.execute("介绍 Fixture")

    assert "5星" not in packet.answer
    assert "**5**星" not in packet.answer
    assert "**5**角色" in packet.answer
    assert "稀有度为 5 [S01]" in packet.answer
    assert "职业为 6，伤害类型为 2[S01]" in packet.answer
    assert "职业编号" not in packet.answer
    assert "具体类型未说明" not in packet.answer


def test_grounded_answer_removes_unsupported_system_membership_claim(tmp_path):
    chain, _planner, _retriever, _registry, _llm = _chain(
        tmp_path,
        ["Fixture 是《Reverse: 1999》中的一名角色。基础资料如下 [S01]。"],
    )

    packet = chain.execute("介绍 Fixture")

    assert "Reverse: 1999" not in packet.answer
    assert packet.answer == "基础资料如下 [S01]。"


def test_voice_answer_discloses_paginated_scope_without_claiming_all_text_is_listed(tmp_path):
    chain, planner, _retriever, registry, _llm = _chain(
        tmp_path,
        [
            "语音示例 [S01]。\n\n此外，已挂载的媒体资源中包含多种语言，"
            "具体内容已在上方列出。"
        ],
    )
    planner.intent = "voice"
    registry.find_for_retrieval = lambda plan, sources: [{
        "media_id": "media:voice",
        "asset_type": "voice",
        "title": "(中文) 完整语音",
    }]

    packet = chain.execute("Fixture 的语音")

    assert "具体内容已在上方列出" not in packet.answer
    assert "按台词分页" in packet.answer
    assert "正文仅列出本轮引用的部分台词" in packet.answer


def test_grounded_answer_removes_unprovable_totality_claim(tmp_path):
    chain, planner, _retriever, _registry, _llm = _chain(
        tmp_path,
        ["文化资料如下 [S01]。\n\n以上是检索到的全部文化资料。"],
    )
    planner.intent = "culture"

    packet = chain.execute("Fixture 的文化资料呢")

    assert packet.answer == "文化资料如下 [S01]。"


def test_grounded_answer_preserves_uncertainty_from_cited_source(tmp_path):
    chain, planner, retriever, _registry, _llm = _chain(
        tmp_path,
        ["- **悬垂的翎羽**：出品自某地宝石工坊 [S01]。"],
    )
    planner.intent = "culture"
    retriever.search = lambda *args, **kwargs: [{
        "name": "Fixture",
        "category": "character",
        "source": "fixture.json",
        "score": 1.0,
        "content": "悬垂的翎羽\n这枚宝石耳坠据传出品自某地宝石工坊。",
        "heading_path": "Fixture / 悬垂的翎羽",
        "child_id": "child-1",
        "parent_id": "parent-1",
        "entity_type": "fixture",
        "entity_id": "fixture-1",
    }]

    packet = chain.execute("Fixture 的文化资料呢")

    assert packet.answer == "- **悬垂的翎羽**：据传，出品自某地宝石工坊 [S01]。"


def test_grounded_answer_neutralizes_unsupported_speaker_attribution(tmp_path):
    chain, planner, retriever, _registry, _llm = _chain(
        tmp_path,
        ["- **袖剑**：受访者认为其兼具致命性与美观性 [S01]。"],
    )
    planner.intent = "culture"
    retriever.search = lambda *args, **kwargs: [{
        "name": "Fixture",
        "category": "character",
        "source": "fixture.json",
        "score": 1.0,
        "content": (
            "袖剑\n我们对此物感到十分好奇，期望借来原型图，"
            "试图了解武器致命的同时亦兼具美观性的原因。"
        ),
        "heading_path": "Fixture / 袖剑",
        "child_id": "child-1",
        "parent_id": "parent-1",
        "entity_type": "fixture",
        "entity_id": "fixture-1",
    }]

    packet = chain.execute("Fixture 的文化资料呢")

    assert packet.answer == "- **袖剑**：资料提及，其兼具致命性与美观性 [S01]。"


def test_grounded_answer_removes_all_content_totality_variant(tmp_path):
    chain, planner, _retriever, _registry, _llm = _chain(
        tmp_path,
        ["文化资料如下 [S01]。\n\n以上是已知信息中所有与该实体文化资料相关的内容。"],
    )
    planner.intent = "culture"

    packet = chain.execute("Fixture 的文化资料呢")

    assert packet.answer == "文化资料如下 [S01]。"


def test_broad_profile_answer_drops_unsolicited_shortfall_when_profile_is_retrieved(tmp_path):
    chain, planner, retriever, _registry, _llm = _chain(
        tmp_path,
        [
            "基础资料：稀有度 5、职业 1、伤害类型 1 [S01]。\n\n"
            "关于生日、星级、职业名称和属性，检索到的资料不足以完整回答。"
        ],
    )
    planner.intent = "profile_fact"
    planner.normalized_query = "Fixture 的基础资料"
    retriever.search = lambda *args, **kwargs: [{
        "name": "Fixture",
        "category": "character",
        "source": "fixture.json",
        "score": 1.0,
        "content": "Fixture 角色资料\n稀有度: 5\n职业: 1\n伤害类型: 1",
        "heading_path": "Fixture / 基础资料",
        "child_id": "child-1",
        "parent_id": "parent-1",
        "entity_type": "fixture",
        "entity_id": "fixture-1",
    }]

    packet = chain.execute("它的基础资料呢")

    assert "资料不足" not in packet.answer
    assert packet.answer == "基础资料：稀有度 5、职业 1、伤害类型 1 [S01]。"


def test_broad_profile_answer_drops_false_negative_for_field_present_in_dossier(tmp_path):
    chain, planner, retriever, _registry, _llm = _chain(
        tmp_path,
        [
            "基础资料：稀有度 5、职业 1、伤害类型 1 [S01]。\n"
            "知识库中未提供关于生日的解释或具体数值。"
        ],
    )
    planner.intent = "profile_fact"
    planner.normalized_query = "Fixture 的基础资料"
    retriever.search = lambda *args, **kwargs: [{
        "name": "Fixture",
        "category": "character",
        "source": "fixture.json",
        "score": 1.0,
        "content": "Fixture 条目\n诞生于4月11日春",
        "heading_path": "Fixture / 条目",
        "child_id": "child-1",
        "parent_id": "parent-1",
        "entity_type": "fixture",
        "entity_id": "fixture-1",
    }]

    packet = chain.execute("它的基础资料呢")

    assert "未提供" not in packet.answer
    assert packet.answer == "基础资料：稀有度 5、职业 1、伤害类型 1 [S01]。"


def test_section_detail_prompt_requires_coverage_without_totality_claims(tmp_path):
    chain, planner, _retriever, _registry, llm = _chain(tmp_path, ["Answer [S01]"])
    planner.intent = "culture"

    chain.execute("Fixture 的文化资料呢")

    system_message = llm.messages[0][0].content
    assert "逐项覆盖" in system_message
    assert "不得声称已列出全部资料" in system_message


def test_partial_retrieval_shortfall_is_injected_as_system_metadata(tmp_path):
    chain, planner, retriever, _registry, llm = _chain(tmp_path, ["资料不足 [S01]"])
    planner.normalized_query = "Fixture video"
    retriever.last_route_debug = {
        "coverage_shortfall": {"video": 1, "intro": 0},
    }

    chain.execute("Video question")

    system_message = llm.messages[0][0].content
    assert "检索覆盖说明" in system_message
    assert "video" in system_message
    assert "不得声称已找到" in system_message


def test_multi_intent_prompt_requires_every_requested_intent(tmp_path):
    chain, planner, _retriever, _registry, llm = _chain(tmp_path, ["Answer [S01]"])
    planner.secondary_intents = ("skill",)

    chain.execute("Profile and skill question")

    system_message = llm.messages[0][0].content
    assert "多个意图" in system_message
    assert "general, skill" in system_message
    assert "逐项覆盖" in system_message
    assert "必须逐项回答：general、技能" in llm.messages[0][-1].content


def test_partial_answer_gets_deterministic_missing_intent_disclosure(tmp_path):
    chain, _planner, retriever, _registry, _llm = _chain(
        tmp_path,
        ["Available profile [S01]"],
    )
    retriever.last_route_debug = {"coverage_shortfall": {"video": 1}}

    packet = chain.execute("Profile and video question")

    assert packet.answer.startswith("检索到的资料不足以完整覆盖：视频。")
    assert "Available profile [S01]" in packet.answer


def test_serializers_are_pure_and_share_one_frozen_answer(tmp_path):
    chain, planner, retriever, registry, llm = _chain(tmp_path, ["Answer [S01]"])
    packet = chain.execute("Question")
    counts = (planner.calls, retriever.calls, registry.calls, llm.calls)

    public = response_packet_to_public_dict(packet)
    events = list(response_packet_to_sse_events(packet, token_chunk_size=3))

    assert (planner.calls, retriever.calls, registry.calls, llm.calls) == counts
    assert "content" not in public["sources"][0]
    assert public["sources"][0]["citation_id"] == "S01"
    assert "".join(event.data["token"] for event in events if event.event == "token") == packet.answer
    assert next(event for event in events if event.event == "done").data["answer"] == packet.answer


def test_invalid_draft_is_never_serialized_to_sse(tmp_path):
    invalid_draft = "Invalid draft [S99]"
    chain, _planner, _retriever, _registry, llm = _chain(
        tmp_path,
        [invalid_draft, "Repaired [S01]"],
    )

    packet = chain.execute("Question")
    wire = "".join(response_packet_to_sse_strings(packet, token_chunk_size=2))

    assert llm.calls == 2
    assert packet.answer == "Repaired [S01]"
    assert invalid_draft not in wire


def test_completed_turn_requires_a_valid_committable_packet(tmp_path):
    chain, _planner, _retriever, _registry, _llm = _chain(tmp_path, ["Answer [S01]"])
    packet = chain.execute("Question")
    request = AskExecutionInput("Question", None, {}, None)

    completed = build_completed_turn(request, packet, datetime.now(timezone.utc))
    invalid = replace(
        packet,
        citation_validation=CitationValidation(valid=False, missing_required=True),
    )

    assert completed is not None
    assert completed.entity_id == "fixture-1"
    assert build_completed_turn(request, invalid, datetime.now(timezone.utc)) is None


def test_execute_propagates_trace_and_records_all_applicable_stages(tmp_path):
    chain, _planner, _retriever, _registry, _llm = _chain(tmp_path, ["Answer [S01]"])
    trace = RequestTrace()

    chain.execute("Question", trace=trace)
    snapshot = trace.snapshot()
    names = {span.name for span in snapshot.spans}

    assert {
        "planner.llm",
        "planner.normalize",
        "entity.resolve",
        "route.resolve",
        "retrieval.structured",
        "retrieval.bm25",
        "retrieval.dense",
        "retrieval.fusion",
        "retrieval.rerank",
        "retrieval.expand",
        "retrieval.allocate",
        "media.attach",
        "source_map.build",
        "answer.llm",
        "citation.validate",
    } <= names
    assert snapshot.model_first_token_ms is not None
    assert snapshot.validated_ready_ms is not None
    assert snapshot.model_first_token_ms <= snapshot.validated_ready_ms
