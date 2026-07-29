import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.documents import Document

from src.huiji_rag.io import write_jsonl
from src.rag.packet_policy import get_packet_policy
from src.rag.query_plan import QueryPlan
from src.rag.retriever import (
    Retriever,
    _doc_to_huiji_row,
    _sparse_query_for_plan,
    build_sparse_query_segments,
)
from src.rag.tracing import RequestTrace


class _PacketFakeVectorstore:
    def query_rows(self, expr: str, limit: int = 10000):
        if 'name == "玛蒂尔达"' in expr:
            return [
                {
                    "id": "voice",
                    "text": "语音内容",
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "玛蒂尔达.md",
                    "heading_path": "玛蒂尔达 > 语音",
                    "chunk_index": 11,
                },
                {
                    "id": "skill-a",
                    "text": "神秘术一：天才习作",
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "玛蒂尔达.md",
                    "heading_path": "玛蒂尔达 > 神秘术",
                    "chunk_index": 2,
                },
                {
                    "id": "skill-b",
                    "text": "神秘术二：众望瞩目",
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "玛蒂尔达.md",
                    "heading_path": "玛蒂尔达 > 神秘术",
                    "chunk_index": 3,
                },
            ]
        return []

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, expr: str | None = None):
        return []


def test_retriever_uses_huiji_children_when_enabled(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": "char:3041/skill:30410111",
                    "parent_id": "char:3041/skills",
                    "entity_name": "玛蒂尔达",
                    "entity_type": "character",
                    "entity_id": "3041",
                    "category": "character",
                "section_kind": "skill",
                "text": "天才习作",
                "search_text": "玛蒂尔达 技能 天才习作 Skill-30410111",
                "chunk_index": 0,
                "media_policy": "auto",
            }
        ],
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=4),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    retriever = Retriever(cfg, _PacketFakeVectorstore())
    plan = QueryPlan(
        original_query="玛蒂尔达技能",
        normalized_query="玛蒂尔达 技能",
        entity="玛蒂尔达",
        aliases=("Matilda",),
        intent="skill",
        section_hints=("skills",),
        scatter_terms=("玛蒂尔达",),
        confidence=0.9,
        entity_type="character",
        entity_id="3041",
        resolution_mode="current_exact",
    )

    results = retriever.search("玛蒂尔达 技能", query_plan=plan)

    assert results[0]["child_id"] == "char:3041/skill:30410111"
    assert results[0]["retrieval_stage"] == "huiji_hybrid"


def test_sparse_query_for_profile_plan_uses_entity_terms_not_compact_rewrite():
    sonetto = "\u5341\u56db\u884c\u8bd7"
    plan = QueryPlan(
        original_query="\u4ecb\u7ecd\u4e00\u4e0b\u5341\u56db\u884c\u8bd7",
        normalized_query=f"{sonetto}\u89d2\u8272\u4ecb\u7ecd",
        entity=sonetto,
        aliases=("Sonetto",),
        intent="profile",
        section_hints=("\u89d2\u8272\u7b80\u4ecb",),
        scatter_terms=(sonetto, "Sonetto", "\u89d2\u8272", "\u4ecb\u7ecd"),
        confidence=0.95,
    )

    sparse_query = _sparse_query_for_plan(plan.normalized_query, plan)

    assert f"{sonetto}\u89d2\u8272\u4ecb\u7ecd" not in sparse_query
    assert sonetto in sparse_query.split(" ")
    assert "\u89d2\u8272\u8d44\u6599" in sparse_query.split(" ")
    assert "\u57fa\u7840\u8d44\u6599" in sparse_query.split(" ")


def test_sparse_query_for_plan_prefers_explicit_sparse_query():
    plan = QueryPlan(
        original_query="介绍一下十四行诗",
        normalized_query="十四行诗角色介绍",
        entity="十四行诗",
        aliases=("Sonetto",),
        intent="intro",
        section_hints=("profile",),
        scatter_terms=("十四行诗", "Sonetto"),
        confidence=0.9,
        dense_query="十四行诗背景技能单品文化",
        sparse_query="十四行诗 Sonetto char:3023 profile skills items",
    )

    assert build_sparse_query_segments(plan) == (
        "介绍一下十四行诗",
        "十四行诗 Sonetto char:3023 profile skills items",
        "十四行诗",
        "Sonetto",
        "角色资料",
        "基础资料",
        "profile",
    )
    assert _sparse_query_for_plan(plan.normalized_query, plan) == " ".join(
        build_sparse_query_segments(plan)
    )


def test_sparse_query_segments_for_corpus_topic_are_ordered_and_deduplicated():
    plan = QueryPlan(
        original_query="暴雨是什么",
        normalized_query="暴雨",
        entity=None,
        aliases=("暴雨", "暴雨事件"),
        intent="general_game",
        section_hints=("剧情", "故事"),
        scatter_terms=("暴雨", "暴雨事件", ""),
        confidence=0.8,
        sparse_query="暴雨",
        retrieval_scope="corpus_topic",
    )

    assert build_sparse_query_segments(plan) == (
        "暴雨是什么",
        "暴雨",
        "暴雨事件",
        "story",
        "剧情",
        "故事",
    )


def test_milvus_serialized_topic_metadata_survives_corpus_topic_gates():
    source_ref = {
        "source_kind": "crawler_page",
        "source_title": "暴雨",
        "source_row_id": "storm-definition",
        "source_content_sha256": "a" * 64,
    }
    row = _doc_to_huiji_row(
        Document(
            page_content="暴雨是游戏世界观中的核心事件。",
            metadata={
                "child_id": "topic:storm/definition:milvus",
                "parent_id": "page:storm/definition",
                "entity_id": "topic:storm",
                "entity_name": "暴雨",
                "entity_type": "topic",
                "category": "topic",
                "section_kind": "topic",
                "route_tags": json.dumps(
                    ["general_game", "definition"],
                    ensure_ascii=False,
                ),
                "source_ref": json.dumps([source_ref], ensure_ascii=False),
            },
        ),
        score=0.9,
        rank=1,
    )

    assert row["route_tags"] == ("general_game", "definition")
    assert row["source_refs"] == (source_ref,)
    assert Retriever._is_corpus_topic_candidate(row) is True
    assert Retriever._has_valid_source_refs(row) is True


def test_malformed_milvus_topic_metadata_fails_closed_without_character_tuples():
    malformed_rows = [
        _doc_to_huiji_row(
            Document(
                page_content="malformed route tags",
                metadata={
                    "entity_type": "character",
                    "route_tags": '{"general_game": true}',
                    "source_ref": "[]",
                },
            ),
            score=0.9,
            rank=1,
        ),
        _doc_to_huiji_row(
            Document(
                page_content="malformed source refs",
                metadata={
                    "entity_type": "character",
                    "route_tags": '["general_game"]',
                    "source_ref": '{"source_kind": "crawler_page"}',
                },
            ),
            score=0.8,
            rank=2,
        ),
        _doc_to_huiji_row(
            Document(
                page_content="invalid json",
                metadata={
                    "entity_type": "character",
                    "route_tags": "[not-json",
                    "source_ref": "[not-json",
                },
            ),
            score=0.7,
            rank=3,
        ),
    ]

    assert malformed_rows[0]["route_tags"] == ()
    assert malformed_rows[1]["source_refs"] == ()
    assert malformed_rows[2]["route_tags"] == ()
    assert malformed_rows[2]["source_refs"] == ()
    assert all(
        not (
            Retriever._is_corpus_topic_candidate(row)
            and Retriever._has_valid_source_refs(row)
        )
        for row in malformed_rows
    )


class _CrossOwnerDenseVectorstore:
    def similarity_search_with_relevance_scores(self, query, k=4, expr=None):
        del query, k, expr
        return [
            (
                Document(
                    page_content="foreign high score",
                    metadata={
                        "child_id": "owner-b/profile:0000",
                        "parent_id": "owner-b/profile",
                        "entity_name": "Shared Name",
                        "entity_type": "character",
                        "entity_id": "owner-b",
                        "category": "character",
                        "section_kind": "profile",
                    },
                ),
                0.99,
            )
        ]

    def similarity_search(self, query, k=4, expr=None):
        return [doc for doc, _ in self.similarity_search_with_relevance_scores(query, k, expr)]


def test_exact_owner_returns_short_result_without_cross_owner_backfill(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": "owner-a/profile:0000",
                "parent_id": "owner-a/profile",
                "entity_name": "Shared Name",
                "entity_type": "character",
                "entity_id": "owner-a",
                "category": "character",
                "section_kind": "profile",
                "text": "owned profile",
                "search_text": "Shared Name profile",
                "chunk_index": 0,
            },
            {
                "child_id": "owner-b/profile:0000",
                "parent_id": "owner-b/profile",
                "entity_name": "Shared Name",
                "entity_type": "character",
                "entity_id": "owner-b",
                "category": "character",
                "section_kind": "profile",
                "text": "foreign profile",
                "search_text": "Shared Name profile",
                "chunk_index": 0,
            },
        ],
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=20),
        retrieval=SimpleNamespace(context_budget_chars=1000, sibling_window=0),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    retriever = Retriever(cfg, _CrossOwnerDenseVectorstore())
    plan = QueryPlan(
        original_query="Shared Name profile",
        normalized_query="Shared Name profile",
        entity="Shared Name",
        aliases=(),
        intent="profile_fact",
        section_hints=("profile",),
        scatter_terms=("Shared Name",),
        confidence=1.0,
        entity_type="character",
        entity_id="owner-a",
        resolution_mode="current_exact",
    )

    results = retriever.search(plan.normalized_query, k=20, query_plan=plan)

    assert [item["child_id"] for item in results] == ["owner-a/profile:0000"]
    assert results[0]["entity_id"] == "owner-a"
    assert retriever.last_route_debug["owner_mismatch"] > 0
    assert retriever.last_route_debug["owner_shortfall"] > 0
    assert retriever.last_route_debug["ownership_key"] == ["character", "owner-a"]


def test_unresolved_owner_bound_intent_returns_empty_without_cross_entity_fill(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "child_blocks.jsonl",
        [{
            "child_id": "owner-b/profile:0000",
            "parent_id": "owner-b/profile",
            "entity_name": "Other Entity",
            "entity_type": "character",
            "entity_id": "owner-b",
            "category": "character",
            "section_kind": "profile",
            "text": "foreign profile",
            "search_text": "Other Entity profile",
            "chunk_index": 0,
        }],
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=20),
        retrieval=SimpleNamespace(context_budget_chars=1000, sibling_window=0),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    vectorstore = _CrossOwnerDenseVectorstore()
    retriever = Retriever(cfg, vectorstore)
    plan = QueryPlan(
        original_query="不存在角色的介绍",
        normalized_query="不存在角色的介绍",
        entity=None,
        aliases=(),
        intent="intro",
        secondary_intents=("general",),
        section_hints=("profile",),
        scatter_terms=(),
        confidence=0.2,
        resolution_mode="unresolved",
    )
    trace = RequestTrace()

    results = retriever.search(plan.normalized_query, k=20, query_plan=plan, trace=trace)

    assert results == []
    assert retriever.last_route_debug["unresolved_owner"] is True
    assert retriever.last_route_debug["coverage_shortfall"]["intro"] > 0
    assert {
        "retrieval.structured",
        "retrieval.bm25",
        "retrieval.dense",
        "retrieval.fusion",
        "retrieval.rerank",
        "retrieval.expand",
        "retrieval.allocate",
    } <= {span.name for span in trace.snapshot().spans}

    meta_plan = QueryPlan(
        original_query="现在有多少在线玩家",
        normalized_query="现在有多少在线玩家",
        entity=None,
        aliases=(),
        intent="meta_question",
        section_hints=(),
        scatter_terms=(),
        confidence=0.9,
        resolution_mode="unresolved",
    )
    assert retriever.search(meta_plan.normalized_query, query_plan=meta_plan) == []

    game_plan = QueryPlan(
        original_query="介绍一下这个游戏",
        normalized_query="介绍一下这个游戏",
        entity=None,
        aliases=(),
        intent="general_game",
        section_hints=(),
        scatter_terms=(),
        confidence=0.9,
        resolution_mode="unresolved",
    )
    assert retriever.search(game_plan.normalized_query, query_plan=game_plan) == []
    assert retriever.last_route_debug["unresolved_owner"] is True


class _DenseNoiseVectorstore:
    def __init__(self) -> None:
        self.calls = []

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, expr: str | None = None):
        self.calls.append({"query": query, "k": k, "expr": expr})
        return [(
            Document(
                page_content="\u91d1\u871c\u513f profile noise",
                metadata={
                    "id": "char:3060/profile:0000",
                    "child_id": "char:3060/profile:0000",
                    "parent_id": "char:3060/profile",
                    "entity_name": "\u91d1\u871c\u513f",
                    "name": "\u91d1\u871c\u513f",
                    "entity_type": "character",
                    "entity_id": "3060",
                    "category": "character",
                    "section_kind": "profile",
                    "chunk_index": 0,
                },
            ),
            0.99,
        )]

    def similarity_search(self, query: str, k: int = 4, expr: str | None = None):
        return [doc for doc, _ in self.similarity_search_with_relevance_scores(query, k=k, expr=expr)]


def test_profile_huiji_search_prefers_exact_character_profile_over_dense_and_youtium_noise(tmp_path):
    sonetto = "\u5341\u56db\u884c\u8bd7"
    youtium = "\u5c24\u63d0\u59c6"
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": "char:3023/profile:0000",
                "parent_id": "char:3023/profile",
                "entity_name": sonetto,
                "entity_type": "character",
                "entity_id": "3023",
                "category": "character",
                "section_kind": "profile",
                "text": f"{sonetto} \u89d2\u8272\u8d44\u6599 \u57fa\u7840\u8d44\u6599",
                "search_text": f"{sonetto} Sonetto \u89d2\u8272\u8d44\u6599 \u57fa\u7840\u8d44\u6599",
                "chunk_index": 0,
                "media_policy": "auto",
            },
            {
                "child_id": "item:1/333023:0000",
                "parent_id": "item:1/333023/profile",
                "entity_name": f"{youtium}\u8d34\u7eb8\u00b7{sonetto}",
                "entity_type": "item",
                "entity_id": "333023",
                "category": "item",
                "section_kind": "profile",
                "text": f"{youtium}\u8d34\u7eb8\u00b7{sonetto} | {sonetto}\u7684{youtium}\u5f62\u8c61",
                "search_text": f"{youtium}\u8d34\u7eb8 {sonetto}",
                "chunk_index": 0,
                "media_policy": "auto",
            },
            {
                "child_id": "char:3060/profile:0000",
                "parent_id": "char:3060/profile",
                "entity_name": "\u91d1\u871c\u513f",
                "entity_type": "character",
                "entity_id": "3060",
                "category": "character",
                "section_kind": "profile",
                "text": "\u91d1\u871c\u513f profile noise",
                "search_text": "\u91d1\u871c\u513f profile noise",
                "chunk_index": 0,
                "media_policy": "auto",
            },
        ],
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=5),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    vectorstore = _DenseNoiseVectorstore()
    retriever = Retriever(cfg, vectorstore)
    plan = QueryPlan(
        original_query=f"\u4ecb\u7ecd\u4e00\u4e0b{sonetto}",
        normalized_query=f"{sonetto}\u89d2\u8272\u4ecb\u7ecd",
        entity=sonetto,
        aliases=("Sonetto",),
        intent="profile",
        section_hints=("\u89d2\u8272\u7b80\u4ecb",),
        scatter_terms=(sonetto, "Sonetto", "\u89d2\u8272", "\u4ecb\u7ecd"),
        confidence=0.95,
        entity_type="character",
        entity_id="3023",
        resolution_mode="current_exact",
    )

    results = retriever.search(plan.normalized_query, k=5, query_plan=plan)

    assert vectorstore.calls[0]["query"] == plan.normalized_query
    assert results[0]["child_id"] == "char:3023/profile:0000"
    assert all(youtium not in item["name"] for item in results)
    assert all(item["name"] != "\u91d1\u871c\u513f" for item in results)


def test_intro_huiji_search_reports_omitted_actions_for_top_k_trim(tmp_path):
    sonetto = "\u5341\u56db\u884c\u8bd7"
    processed = tmp_path / "processed" / "build"
    rows = [
        ("char:3023/profile:0000", "char:3023/profile", "profile", "Profile"),
        ("char:3023/dossier:0000", "char:3023/dossier", "dossier", "Dossier"),
        ("char:3023/culture:0000", "char:3023/culture", "culture", "Culture"),
        ("char:3023/skill:302301", "char:3023/skills", "skill", "Skill"),
        ("char:3023/item:1", "char:3023/items", "item", "Item"),
        ("char:3023/media:portrait", "char:3023/media", "media", "Media"),
    ]
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": child_id,
                    "parent_id": parent_id,
                    "entity_name": sonetto,
                    "entity_type": "character",
                    "entity_id": "3023",
                    "category": "character",
                "section_kind": section,
                "title": section,
                "text": text,
                "search_text": f"{sonetto} {section} {text}",
                "chunk_index": index,
                "media_policy": "auto",
            }
            for index, (child_id, parent_id, section, text) in enumerate(rows)
        ],
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=2),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    retriever = Retriever(cfg, _PacketFakeVectorstore())
    plan = QueryPlan(
        original_query=f"\u4ecb\u7ecd\u4e00\u4e0b{sonetto}",
        normalized_query=f"{sonetto}\u89d2\u8272\u4ecb\u7ecd",
        entity=sonetto,
        aliases=("Sonetto",),
        intent="intro",
        section_hints=("profile", "dossier", "culture", "skills", "items", "media"),
        scatter_terms=(sonetto, "Sonetto"),
        confidence=0.95,
        entity_type="character",
        entity_id="3023",
        resolution_mode="current_exact",
    )

    results = retriever.search(plan.normalized_query, k=2, query_plan=plan)

    assert len(results) == 2
    omitted_parent_ids = {action["target_parent_id"] for action in retriever.last_omitted_actions}
    assert {"char:3023/culture", "char:3023/skills", "char:3023/items", "char:3023/media"} <= omitted_parent_ids


class _RecordingSparse:
    def __init__(self):
        self.limits = []

    def search(self, query, top_k):
        self.limits.append(top_k)
        return []


class _RecordingReranker:
    def __init__(self):
        self.limits = []

    def rerank(self, query, rows, limit=None):
        self.limits.append(limit)
        return rows[:limit]


def test_huiji_multi_intent_allocates_exact_skill_and_clamped_voice_coverage(tmp_path):
    entity = "Test Character"
    processed = tmp_path / "processed" / "build"
    rows = [
        {
            "child_id": f"char:1/skill:{index}",
            "parent_id": "char:1/skills",
            "entity_name": entity,
            "entity_type": "character",
            "entity_id": "1",
            "category": "character",
            "section_kind": "skill",
            "text": f"Skill {index}",
            "search_text": f"{entity} skill {index}",
            "chunk_index": index,
        }
        for index in range(5)
    ] + [
        {
            "child_id": f"char:1/voice:{index}",
            "parent_id": "char:1/voice",
            "entity_name": entity,
            "entity_type": "character",
            "entity_id": "1",
            "category": "character",
            "section_kind": "voice",
            "text": f"Voice {index}",
            "search_text": f"{entity} voice {index}",
            "chunk_index": index,
        }
        for index in range(4)
    ]
    write_jsonl(processed / "child_blocks.jsonl", rows)
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=7),
        retrieval=SimpleNamespace(
            bm25_k=2,
            dense_k=3,
            rerank_k=4,
            context_budget_chars=1000,
            sibling_window=0,
            candidate_oversample=4,
            candidate_k_max=100,
            voice_page_size=10,
            voice_page_size_max=2,
        ),
        reranker=SimpleNamespace(enabled=False),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    vectorstore = _DenseNoiseVectorstore()
    retriever = Retriever(cfg, vectorstore)
    sparse = _RecordingSparse()
    reranker = _RecordingReranker()
    retriever._huiji_sparse = sparse
    retriever._reranker = reranker
    plan = QueryPlan(
        original_query=f"{entity} skills and voices",
        normalized_query=f"{entity} skills and voices",
        entity=entity,
        aliases=(),
        intent="skill",
        secondary_intents=("voice",),
        section_hints=("skills", "voice"),
        scatter_terms=(entity,),
        confidence=0.99,
        entity_type="character",
        entity_id="1",
        resolution_mode="current_exact",
    )

    results = retriever.search(plan.normalized_query, k=7, query_plan=plan)

    assert sparse.limits == [28]
    assert vectorstore.calls[0]["k"] == 28
    assert reranker.limits == [28]
    assert len(results) == 7
    assert sum(item["section_kind"] == "skill" for item in results) == 5
    assert sum(item["section_kind"] == "voice" for item in results) == 2
    assert all(item["debug"]["matched_intents"] for item in results)
    assert retriever.last_omitted_actions == []
    assert {key: retriever.last_route_debug[key] for key in (
        "requested_intents",
        "candidate_k",
        "required_source_count",
        "intent_candidates",
        "intent_targets",
        "intent_retained",
        "coverage_shortfall",
        "chars_used",
        "max_sources",
    )} == {
        "requested_intents": ["skill", "voice"],
        "candidate_k": 28,
        "required_source_count": 7,
        "intent_candidates": {"skill": 5, "voice": 4},
        "intent_targets": {"skill": 5, "voice": 2},
        "intent_retained": {"skill": 5, "voice": 2},
        "coverage_shortfall": {"skill": 0, "voice": 0},
        "chars_used": sum(len(item["content"]) for item in results),
        "max_sources": 7,
    }


def test_structured_rows_require_exact_target_parent_when_action_sets_one():
    retriever = Retriever.__new__(Retriever)
    retriever._huiji_children = [
        {
            "child_id": "char:a/skills:1",
            "parent_id": "char:a/skills",
            "entity_name": "角色甲",
            "category": "character",
            "section_kind": "skill",
        },
        {
            "child_id": "char:b/skills:1",
            "parent_id": "char:b/skills",
            "entity_name": "角色乙",
            "category": "character",
            "section_kind": "skill",
        },
        {
            "child_id": "char:b/skills-alt:1",
            "parent_id": "char:b/skills-alt",
            "entity_name": "角色乙",
            "category": "character",
            "section_kind": "skill",
        },
    ]
    plan = QueryPlan(
        original_query="角色乙的技能",
        normalized_query="角色乙 技能",
        entity="角色乙",
        aliases=(),
        intent="skill",
        section_hints=("skills",),
        scatter_terms=("角色乙",),
        confidence=1.0,
        entity_type="character",
        target_parent_id="char:b/skills",
    )

    rows = retriever._structured_rows_for_plan(
        plan,
        get_packet_policy("character", "skill"),
    )

    assert [row["child_id"] for row in rows] == ["char:b/skills:1"]


def test_huiji_voice_page_size_zero_clamps_to_one_at_consumption(tmp_path):
    entity = "Zero Voice Character"
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": f"char:2/voice:{index}",
                "parent_id": "char:2/voice",
                "entity_name": entity,
                "entity_type": "character",
                "entity_id": "2",
                "category": "character",
                "section_kind": "voice",
                "text": f"Voice {index}",
                "search_text": f"{entity} voice {index}",
                "chunk_index": index,
            }
            for index in range(2)
        ],
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=2),
        retrieval=SimpleNamespace(
            bm25_k=2,
            dense_k=2,
            rerank_k=4,
            context_budget_chars=1000,
            sibling_window=0,
            candidate_oversample=4,
            candidate_k_max=100,
            voice_page_size=0,
            voice_page_size_max=20,
        ),
        reranker=SimpleNamespace(enabled=False),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    retriever = Retriever(cfg, _DenseNoiseVectorstore())
    plan = QueryPlan(
        original_query=f"{entity} voices",
        normalized_query=f"{entity} voices",
        entity=entity,
        aliases=(),
        intent="voice",
        section_hints=("voice",),
        scatter_terms=(entity,),
        confidence=0.99,
        entity_type="character",
        entity_id="2",
        resolution_mode="current_exact",
    )

    results = retriever.search(plan.normalized_query, k=2, query_plan=plan)

    assert len(results) == 1
    assert retriever.last_route_debug["required_source_count"] == 1
    assert retriever.last_route_debug["intent_targets"] == {"voice": 1}
    assert retriever.last_route_debug["intent_retained"] == {"voice": 1}
