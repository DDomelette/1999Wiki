from src.rag.entity_packet import RetrievalCandidate
from src.rag.query_plan import QueryPlan
from src.rag.reranker import INTENT_QUERY_KEYWORDS, OptionalBgeReranker, RobustIntentRouter
import pytest


def _plan(intent: str = "skill"):
    return QueryPlan(
        original_query="玛蒂尔达的技能是什么",
        normalized_query="玛蒂尔达的技能、神秘术、传承和塑造是什么？",
        entity="玛蒂尔达",
        aliases=("玛蒂尔达", "Matilda Bouanich"),
        intent=intent,
        section_hints=("神秘术", "传承", "塑造") if intent == "skill" else (),
        scatter_terms=("玛蒂尔达", "Matilda Bouanich"),
        confidence=0.9,
    )


def _candidate(heading: str, chunk_index: int, content: str, score: float, stage: str = "entity_name"):
    return RetrievalCandidate(
        id=f"{heading}-{chunk_index}",
        name="玛蒂尔达",
        category="人物",
        source="玛蒂尔达.md",
        heading_path=heading,
        chunk_index=chunk_index,
        content=content,
        vector_score=score,
        retrieval_stage=stage,
    )


def test_skill_intent_promotes_skill_sections_over_voice_vector_score():
    candidates = [
        _candidate("玛蒂尔达 > 语音", 11, "我会以第一名的成绩。", 0.99),
        _candidate("玛蒂尔达 > 神秘术", 2, "天才习作造成精神创伤。", 0.52),
        _candidate("玛蒂尔达 > 神秘术", 3, "众望瞩目造成精神创伤。", 0.51),
        _candidate("玛蒂尔达 > 塑造", 6, "塑造提升技能效果。", 0.30),
    ]

    ranked = RobustIntentRouter().rerank(_plan(), candidates, limit=4)

    assert ranked[0]["heading_path"] == "玛蒂尔达 > 神秘术"
    assert ranked[1]["heading_path"] == "玛蒂尔达 > 神秘术"
    assert ranked[-1]["heading_path"] == "玛蒂尔达 > 语音"


def test_robust_router_uses_actual_heading_paths_when_stage0_is_general():
    candidates = [
        _candidate("玛蒂尔达 > 神秘术", 2, "技能文本", 0.40),
        _candidate("玛蒂尔达 > 语音", 11, "语音文本", 0.90),
    ]

    ranked = RobustIntentRouter().rerank(_plan(intent="general"), candidates, limit=2)

    assert ranked[0]["heading_path"] == "玛蒂尔达 > 神秘术"
    assert ranked[0]["debug"]["router_intent"] == "skill"


def test_robust_router_confirms_item_when_stage0_is_general():
    plan = QueryPlan(
        original_query="玛蒂尔达的单品是什么",
        normalized_query="玛蒂尔达 单品",
        entity="玛蒂尔达",
        aliases=(),
        intent="general",
        section_hints=(),
        scatter_terms=("玛蒂尔达",),
        confidence=0.0,
    )
    candidates = [
        _candidate("玛蒂尔达 > 文化", 1, "文化文本", 0.80),
        _candidate("玛蒂尔达 > 单品", 2, "单品文本", 0.40),
    ]

    ranked = RobustIntentRouter().rerank(plan, candidates, limit=2)

    assert ranked[0]["heading_path"] == "玛蒂尔达 > 单品"
    assert ranked[0]["debug"]["router_intent"] == "item"


@pytest.mark.parametrize(
    ("query", "target_heading", "expected_intent"),
    [
        ("播放玛蒂尔达语音", "玛蒂尔达 > 语音", "voice"),
        ("看一下玛蒂尔达的立绘", "玛蒂尔达 > 立绘", "media"),
        ("看一下玛蒂尔达PV", "玛蒂尔达 > 视频", "video"),
        ("讲讲玛蒂尔达的故事", "玛蒂尔达 > 故事", "story"),
        ("玛蒂尔达心相推荐", "玛蒂尔达 > 心相", "psychube"),
        ("玛蒂尔达文化背景是什么", "玛蒂尔达 > 文化", "culture"),
    ],
)
def test_robust_router_confirms_main_intents_when_stage0_is_general(query, target_heading, expected_intent):
    plan = QueryPlan(
        original_query=query,
        normalized_query=query,
        entity="玛蒂尔达",
        aliases=(),
        intent="general",
        section_hints=(),
        scatter_terms=("玛蒂尔达",),
        confidence=0.0,
    )
    candidates = [
        _candidate("玛蒂尔达 > 基础资料", 1, "基础资料文本", 0.90),
        _candidate(target_heading, 2, f"{expected_intent} 文本", 0.30),
    ]

    ranked = RobustIntentRouter().rerank(plan, candidates, limit=2)

    assert ranked[0]["heading_path"] == target_heading
    assert ranked[0]["debug"]["router_intent"] == expected_intent


def test_keyword_score_supports_media_intent_keywords():
    plan = QueryPlan(
        original_query="看看玛蒂尔达的立绘",
        normalized_query="玛蒂尔达 立绘 图片",
        entity="玛蒂尔达",
        aliases=(),
        intent="media",
        section_hints=("media", "立绘", "图片"),
        scatter_terms=("玛蒂尔达",),
        confidence=0.9,
    )
    router = RobustIntentRouter()

    score = router._keyword_score(plan, "media", "玛蒂尔达 > 立绘\n立绘 图片")

    assert score > 0


def test_item_intent_does_not_penalize_item_heading_as_noise():
    router = RobustIntentRouter()

    assert router._noise_penalty("item", "玛蒂尔达 > 单品") == 0.0


def test_intent_query_keywords_cover_main_router_intents():
    expected = {
        "intro",
        "profile_fact",
        "skill",
        "item",
        "culture",
        "voice",
        "media",
        "video",
        "psychube",
        "story",
        "general_game",
        "meta_question",
    }

    assert expected <= set(INTENT_QUERY_KEYWORDS)
    assert "profile" in INTENT_QUERY_KEYWORDS
    assert "lore" in INTENT_QUERY_KEYWORDS


def test_optional_reranker_disabled_returns_input_order():
    reranker = OptionalBgeReranker(enabled=False, base_url="", api_key="", model="BAAI/bge-reranker-v2-m3")
    rows = [{"child_id": "a", "text": "A"}, {"child_id": "b", "text": "B"}]
    assert reranker.rerank("query", rows) == rows


class _FakeRerankClient:
    def score(self, query, documents):
        assert query == "十四行诗技能"
        assert documents == ["A", "B"]
        return [0.2, 0.9]


def test_optional_reranker_enabled_uses_scores():
    reranker = OptionalBgeReranker(
        enabled=True,
        base_url="https://api.siliconflow.cn/v1",
        api_key="key",
        model="BAAI/bge-reranker-v2-m3",
        client=_FakeRerankClient(),
    )
    rows = [{"child_id": "a", "text": "A"}, {"child_id": "b", "text": "B"}]

    ranked = reranker.rerank("十四行诗技能", rows)

    assert [row["child_id"] for row in ranked] == ["b", "a"]
    assert ranked[0]["debug"]["reranker_score"] == 0.9
