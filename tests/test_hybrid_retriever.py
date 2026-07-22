from src.rag.hybrid import rerank_children_with_parent_context, weighted_rrf
from src.rag.layered_expansion import expand_ranked_children
from src.rag.packet_policy import compose_packet_policies, get_packet_policy
from src.rag.retrieval_budget import allocate_sources


def test_weighted_rrf_combines_bm25_and_dense_ranks():
    rows = weighted_rrf(
        bm25=[{"child_id": "a"}, {"child_id": "b"}],
        dense=[{"child_id": "b"}, {"child_id": "c"}],
        entity="玛蒂尔达",
        intent="skill",
    )

    assert rows[0]["child_id"] == "b"
    assert rows[0]["debug"]["bm25_rank"] == 2
    assert rows[0]["debug"]["dense_rank"] == 1


def test_weighted_rrf_filters_hard_excluded_and_penalizes_quality_flags():
    rows = [
        {
            "child_id": "bad",
            "entity_name": "???",
            "category": "character",
            "section_kind": "profile",
            "quality_flags": ["weak_entity_name"],
        },
        {
            "child_id": "good",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "profile",
            "quality_flags": [],
        },
    ]

    ranked = weighted_rrf(rows, [], entity="Sonetto", intent="intro")

    assert [row["child_id"] for row in ranked] == ["good"]


def test_parent_context_keeps_hit_and_neighbor_order():
    children = [
        {"child_id": "a", "parent_id": "p", "chunk_index": 0, "text": "前文"},
        {"child_id": "b", "parent_id": "p", "chunk_index": 1, "text": "命中"},
        {"child_id": "c", "parent_id": "p", "chunk_index": 2, "text": "后文"},
    ]
    ranked = [{"child_id": "b", "parent_id": "p", "score": 1.0}]

    out = rerank_children_with_parent_context(ranked, children, neighbor_window=1, limit=3)

    assert [row["child_id"] for row in out] == ["b", "a", "c"]


def test_intro_expands_parent_sections_and_returns_omitted_actions():
    children = [
        {
            "child_id": "char:3023/profile:0000",
            "parent_id": "char:3023/profile",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "profile",
            "chunk_index": 0,
            "text": "Profile",
            "score": 0.9,
        },
        {
            "child_id": "char:3023/skill:302301",
            "parent_id": "char:3023/skills",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "skill",
            "chunk_index": 0,
            "text": "Skill",
            "score": 0.8,
        },
        {
            "child_id": "char:3023/item:1",
            "parent_id": "char:3023/items",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "item",
            "chunk_index": 0,
            "text": "Item with longer body",
            "score": 0.4,
        },
    ]
    ranked = [children[1]]

    result = expand_ranked_children(
        ranked=ranked,
        all_children=children,
        policy=get_packet_policy("character", "intro", "legacy"),
        budget_chars=12,
        sibling_window=1,
    )

    retained_ids = [row["child_id"] for row in result.sources]
    assert "char:3023/profile:0000" in retained_ids
    assert "char:3023/skill:302301" in retained_ids
    assert result.omitted_actions
    assert result.omitted_actions[0]["intent"] in {
        "item", "skill", "media", "culture", "voice", "udimo"
    }


def test_omitted_actions_are_stable_across_input_order():
    from src.rag.layered_expansion import make_omitted_actions

    rows = [
        {
            "child_id": "char:1/item:1",
            "parent_id": "char:1/items",
            "section_kind": "item",
            "entity_name": "Fixture",
        },
        {
            "child_id": "char:1/profile:1",
            "parent_id": "char:1/profile",
            "section_kind": "profile",
            "entity_name": "Fixture",
        },
    ]

    forward = make_omitted_actions(rows, "Fixture")
    reverse = make_omitted_actions(list(reversed(rows)), "Fixture")

    assert forward == reverse
    assert [item["target_parent_id"] for item in forward] == [
        "char:1/profile",
        "char:1/items",
    ]


def test_section_detail_policy_prioritizes_requested_section_rows():
    children = [
        {
            "child_id": "char:3023/profile:0000",
            "parent_id": "char:3023/profile",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "profile",
            "chunk_index": 0,
            "text": "Profile",
            "score": 0.95,
        },
        {
            "child_id": "char:3023/culture:0000",
            "parent_id": "char:3023/culture",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "culture",
            "chunk_index": 0,
            "text": "Culture",
            "score": 0.9,
        },
        {
            "child_id": "char:3023/skill:30230111",
            "parent_id": "char:3023/skills",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "skill",
            "chunk_index": 0,
            "text": "Skill one",
            "score": 0.8,
        },
        {
            "child_id": "char:3023/skill:30230121",
            "parent_id": "char:3023/skills",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "skill",
            "chunk_index": 1,
            "text": "Skill two",
            "score": 0.7,
        },
    ]

    result = expand_ranked_children(
        ranked=[children[2]],
        all_children=children,
        policy=get_packet_policy("character", "skill"),
        budget_chars=1000,
        sibling_window=1,
    )

    assert [row["child_id"] for row in result.sources[:2]] == [
        "char:3023/skill:30230111",
        "char:3023/skill:30230121",
    ]


def test_expansion_preserves_ranked_child_debug_for_eval():
    children = [
        {
            "child_id": "char:3023/skill:30230111",
            "parent_id": "char:3023/skills",
            "entity_name": "Sonetto",
            "category": "character",
            "section_kind": "skill",
            "chunk_index": 0,
            "text": "Skill one",
        }
    ]
    ranked = [
        {
            **children[0],
            "score": 0.9,
            "debug": {
                "bm25_rank": 1,
                "dense_rank": 3,
                "reranker_score": 0.88,
            },
        }
    ]

    result = expand_ranked_children(
        ranked=ranked,
        all_children=children,
        policy=get_packet_policy("character", "skill"),
        budget_chars=1000,
        sibling_window=1,
    )

    assert result.sources[0]["debug"]["bm25_rank"] == 1
    assert result.sources[0]["debug"]["dense_rank"] == 3
    assert result.sources[0]["debug"]["reranker_score"] == 0.88
    assert result.sources[0]["debug"]["layered_hit"] is True


def test_expansion_preserves_ranked_matched_intents_metadata():
    child = {
        "child_id": "char:3023/skill:30230111",
        "parent_id": "char:3023/skills",
        "entity_name": "Sonetto",
        "category": "character",
        "section_kind": "skill",
        "chunk_index": 0,
        "text": "Skill one",
    }
    ranked = [{**child, "score": 0.9, "matched_intents": ("skill", "intro")}]

    result = expand_ranked_children(
        ranked=ranked,
        all_children=[child],
        policy=get_packet_policy("character", "skill"),
        budget_chars=1000,
        sibling_window=1,
    )

    assert result.sources[0]["matched_intents"] == ("skill", "intro")


def test_expansion_and_allocator_preserve_reranked_core_before_new_siblings():
    children = [
        {
            "child_id": child_id,
            "parent_id": "char:1/culture",
            "entity_name": "Test Character",
            "category": "character",
            "section_kind": "culture",
            "chunk_index": index,
            "text": child_id,
            "score": score,
            "matched_intents": ("culture",),
        }
        for index, (child_id, score) in enumerate(
            (("a", 0.9), ("b", 0.1), ("sibling", 2.0))
        )
    ]
    ranked = [dict(children[1]), dict(children[0])]

    expanded = expand_ranked_children(
        ranked=ranked,
        all_children=children,
        policy=get_packet_policy("character", "culture"),
        budget_chars=1000,
        sibling_window=1,
    )

    assert [row["child_id"] for row in expanded.sources] == ["b", "a", "sibling"]
    assert [row["debug"].get("ranked_position") for row in expanded.sources[:2]] == [1, 2]

    allocated = allocate_sources(
        expanded.sources,
        {"culture": expanded.sources},
        compose_packet_policies("character", ("culture",)),
        max_sources=3,
        context_budget_chars=100,
        voice_page_size=1,
    )

    assert [row["child_id"] for row in allocated.sources] == ["b", "a", "sibling"]
