from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.huiji_rag.io import write_jsonl
from src.rag.query_plan import QueryPlan, QueryPlanner
from src.rag.request_plan import RequestPlanner
from src.rag.retriever import RetrievalExecutionError, Retriever


_FIXTURE = Path(__file__).parent / "fixtures" / "rag_thread_a" / "topic_story_children.json"


class EmptyVectorstore:
    def similarity_search_with_relevance_scores(self, query, k=4, expr=None):
        return []

    def similarity_search(self, query, k=4, expr=None):
        return []


@pytest.fixture
def topic_rows():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def topic_retriever(tmp_path, topic_rows):
    processed = tmp_path / "processed" / "build"
    write_jsonl(processed / "child_blocks.jsonl", topic_rows)
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=4),
        retrieval=SimpleNamespace(
            bm25_k=8,
            dense_k=8,
            rerank_k=12,
            context_budget_chars=4000,
            sibling_window=0,
            candidate_oversample=4,
            candidate_k_max=40,
            max_sources=4,
        ),
        reranker=SimpleNamespace(enabled=False),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    return Retriever(cfg, EmptyVectorstore())


def test_owner_free_game_topic_uses_corpus_topic_and_crosses_valid_topic_sources(
    topic_retriever,
):
    request_planner = RequestPlanner(None, query_planner=QueryPlanner(None))

    plan = request_planner.plan("暴雨是什么").subtasks[0].query_plan
    results = topic_retriever.search(plan.normalized_query, query_plan=plan)

    assert plan.retrieval_scope == "corpus_topic"
    assert {row["entity_type"] for row in results} <= {"topic", "story", "page"}
    assert len({row["parent_id"] for row in results}) >= 2
    assert all(row["source_refs"] for row in results)


def test_resolved_topic_uses_topic_strict(topic_retriever):
    plan = QueryPlan(
        original_query="暴雨是什么",
        normalized_query="暴雨",
        entity="暴雨",
        aliases=("暴雨事件",),
        intent="general_game",
        section_hints=(),
        scatter_terms=("暴雨", "暴雨事件"),
        confidence=1.0,
        entity_type="topic",
        entity_id="topic:storm",
        retrieval_scope="topic_strict",
    )

    results = topic_retriever.search(plan.normalized_query, query_plan=plan)

    assert {row["entity_id"] for row in results} == {"topic:storm"}
    assert len({row["parent_id"] for row in results}) >= 2


def test_character_skill_keeps_entity_strict_owner_gate(topic_retriever):
    plan = QueryPlan(
        original_query="十四行诗的技能是什么",
        normalized_query="十四行诗 技能",
        entity="十四行诗",
        aliases=("Sonetto",),
        intent="skill",
        section_hints=("skills",),
        scatter_terms=("十四行诗", "Sonetto"),
        confidence=1.0,
        entity_type="character",
        entity_id="character:sonetto",
        retrieval_scope="entity_strict",
    )

    results = topic_retriever.search(plan.normalized_query, query_plan=plan)

    assert {row["entity_id"] for row in results} == {"character:sonetto"}
    assert topic_retriever.last_route_debug["owner_mismatch"] > 0


def test_invalid_source_refs_and_unverified_aliases_never_become_results(topic_retriever):
    plan = QueryPlan(
        original_query="暴雨是什么",
        normalized_query="暴雨",
        entity=None,
        aliases=(),
        intent="general_game",
        section_hints=(),
        scatter_terms=("暴雨",),
        confidence=1.0,
        retrieval_scope="corpus_topic",
        route="expanded_rag",
    )

    results = topic_retriever.search(plan.normalized_query, k=10, query_plan=plan)

    child_ids = {row["child_id"] for row in results}
    assert "topic:missing-ref/definition:01" not in child_ids
    assert "topic:invalid-source/definition:01" not in child_ids
    assert "topic:unverified-alias/definition:01" not in child_ids
    assert "character:mention/profile:01" not in child_ids
    assert topic_retriever.last_route_debug["invalid_source_refs"] > 0


def test_unresolved_story_keeps_internal_id_without_guessing_title(topic_retriever):
    plan = QueryPlan(
        original_query="Data:Story/304502",
        normalized_query="Data Story 304502",
        entity=None,
        aliases=(),
        intent="story",
        section_hints=("story", "plot"),
        scatter_terms=("Data:Story/304502",),
        confidence=0.5,
        retrieval_scope="corpus_topic",
    )

    results = topic_retriever.search(plan.normalized_query, query_plan=plan)

    unresolved = next(row for row in results if row["entity_id"] == "Data:Story/304502")
    assert unresolved["name"] == ""
    assert unresolved["heading_path"] == ""
    assert topic_retriever.last_route_debug["unresolved_titles"] > 0


def test_none_scope_is_rejected_before_any_retrieval(topic_retriever):
    plan = QueryPlan(
        original_query="你是谁",
        normalized_query="你是谁",
        entity=None,
        aliases=(),
        intent="meta_question",
        section_hints=(),
        scatter_terms=(),
        confidence=1.0,
        retrieval_scope="none",
    )

    with pytest.raises(RetrievalExecutionError, match="InvalidRetrievalScope"):
        topic_retriever.search(plan.normalized_query, query_plan=plan)


def test_fixture_uses_only_frozen_fields_and_no_owner_type(topic_rows):
    frozen_fields = {
        "category",
        "entity_type",
        "entity_id",
        "entity_name",
        "entity_aliases",
        "owner_entity_id",
        "owner_page_id",
        "route_tags",
        "parent_id",
        "child_id",
        "heading_path",
        "section_kind",
        "content",
        "search_text",
        "source_refs",
    }

    assert {row["entity_type"] for row in topic_rows} >= {
        "character",
        "story",
        "topic",
    }
    assert all(set(row) <= frozen_fields for row in topic_rows)
    assert all("owner_type" not in row for row in topic_rows)
