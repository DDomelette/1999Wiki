from src.rag.entity_packet import EntityPacketRetriever
from src.rag.packet_policy import get_packet_policy
from src.rag.query_plan import QueryPlan


class _FakeVectorstore:
    collection_name = "chunks_bge_m3_v1"

    def __init__(self):
        self.queries = []
        self.searches = []

    def query_rows(self, expr: str, limit: int = 10000):
        self.queries.append(expr)
        if 'name == "玛蒂尔达"' in expr:
            return [
                {
                    "id": "m#0002",
                    "text": "## 神秘术\n天才习作",
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "玛蒂尔达.md",
                    "heading_path": "玛蒂尔达 > 神秘术",
                    "chunk_index": 2,
                },
                {
                    "id": "m#0011",
                    "text": "## 语音\n初遇",
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "玛蒂尔达.md",
                    "heading_path": "玛蒂尔达 > 语音",
                    "chunk_index": 11,
                },
            ]
        if 'text like "%Matilda Bouanich%"' in expr:
            return [
                {
                    "id": "hop#0000",
                    "text": "Matilda Bouanich 相关心相说明",
                    "name": "跳房子游戏",
                    "category": "心相",
                    "source": "跳房子游戏.md",
                    "heading_path": "",
                    "chunk_index": 0,
                },
            ]
        return []

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, expr: str | None = None):
        self.searches.append({"query": query, "k": k, "expr": expr})
        return []


def _plan():
    return QueryPlan(
        original_query="玛蒂尔达的技能是什么",
        normalized_query="玛蒂尔达的技能、神秘术、传承和塑造是什么？",
        entity="玛蒂尔达",
        aliases=("玛蒂尔达", "Matilda Bouanich"),
        intent="skill",
        section_hints=("神秘术", "传承", "塑造"),
        scatter_terms=("玛蒂尔达", "Matilda Bouanich"),
        confidence=0.9,
    )


def test_entity_packet_collects_main_chunks_and_scattered_alias_hits():
    vectorstore = _FakeVectorstore()
    packet = EntityPacketRetriever(vectorstore).collect(_plan(), category=None, vector_k=8)

    assert [item.source for item in packet] == ["玛蒂尔达.md", "玛蒂尔达.md", "跳房子游戏.md"]
    assert packet[0].retrieval_stage == "entity_name"
    assert packet[2].retrieval_stage == "scatter_text"
    assert any('name == "玛蒂尔达"' in expr for expr in vectorstore.queries)
    assert any('text like "%Matilda Bouanich%"' in expr for expr in vectorstore.queries)


def test_entity_packet_deduplicates_by_id():
    vectorstore = _FakeVectorstore()
    vectorstore.query_rows = lambda expr, limit=10000: [
        {
            "id": "same",
            "text": "A",
            "name": "玛蒂尔达",
            "category": "人物",
            "source": "玛蒂尔达.md",
            "heading_path": "神秘术",
            "chunk_index": 1,
        },
        {
            "id": "same",
            "text": "A",
            "name": "玛蒂尔达",
            "category": "人物",
            "source": "玛蒂尔达.md",
            "heading_path": "神秘术",
            "chunk_index": 1,
        },
    ]

    packet = EntityPacketRetriever(vectorstore).collect(_plan(), category=None, vector_k=8)

    assert len(packet) == 1


def test_character_intro_policy_sections():
    policy = get_packet_policy("character", "intro")
    assert policy.name == "intro_full"
    assert policy.sections == (
        "dossier",
        "profile",
        "collection",
        "culture_dossier",
        "skills",
        "media",
        "udimo",
    )
    assert policy.auto_media_types == ("portrait", "image")
    assert policy.omitted_parent_actions is True


def test_character_voice_policy_uses_voice_panel():
    policy = get_packet_policy("character", "voice")
    assert policy.sections == ("voice",)
    assert policy.panel == "voice"
    assert policy.auto_media_types == ()
    assert policy.intent_media_types == ("voice",)
