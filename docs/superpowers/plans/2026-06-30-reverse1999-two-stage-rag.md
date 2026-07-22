# Reverse1999 Two Stage RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust Stage 0 + Stage 1 + Stage 2 retrieval pipeline so entity questions such as "玛蒂尔达的技能是什么" retrieve the full relevant character sections instead of unrelated high-similarity chunks.

**Architecture:** Stage 0 uses the same chat LLM as answer generation to normalize the user question and produce a structured query plan. Stage 1 builds an entity packet from Milvus metadata filters, text-like alias matches, optional backlink/link data, and vector candidates. Stage 2 uses the robust Intent Router: it combines Stage 0 intent with Stage 1's actual `heading_path` distribution, scores section groups, restores adjacent chunks, packs context, and returns sources with debug metadata.

**Tech Stack:** Python 3.11/3.12, FastAPI, LangChain `ChatOpenAI`, `pymilvus.MilvusClient`, `langchain_core.documents.Document`, pytest.

---

## File Structure

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/query_plan.py`
  - Owns Stage 0 data model, LLM prompt, JSON parsing, and deterministic fallback when the LLM is unavailable.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/entity_packet.py`
  - Owns Stage 1 entity packet retrieval, Milvus metadata query wrappers, alias matching, deduplication, and candidate normalization.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/reranker.py`
  - Owns robust Intent Router, section grouping, section scoring, adjacency restoration, noise penalties, and context packing.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/retriever.py`
  - Keeps the public `Retriever.search(...)` API, adds optional `query_plan`, delegates entity packet and rerank logic, keeps legacy dense search fallback.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/vectorstore.py`
  - Adds read-only Milvus query helpers used by entity packet retrieval.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/chain.py`
  - Builds the query planner from the same LLM as answer generation, centralizes retrieval in `retrieve(...)`, and uses normalized query for retrieval while keeping original user wording for answer generation.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`
  - Uses `chain.retrieve(...)` so streaming and non-streaming routes share Stage 0/1/2 retrieval.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/schemas.py`
  - Adds optional source debug fields without breaking current frontend consumers.
- Test:
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_query_plan.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_entity_packet.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_reranker.py`
  - Modify existing `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_retriever.py`
  - Modify existing `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_sse.py`

## Contracts

Stage 0 returns this shape:

```python
QueryPlan(
    original_query="玛蒂儿达技能是啥",
    normalized_query="玛蒂尔达的技能、神秘术、传承和塑造是什么？",
    entity="玛蒂尔达",
    aliases=("玛蒂尔达", "Matilda Bouanich"),
    intent="skill",
    section_hints=("神秘术", "传承", "塑造"),
    scatter_terms=("玛蒂尔达", "Matilda Bouanich"),
    confidence=0.92,
)
```

Stage 1 returns candidate chunks, not final context:

```python
RetrievalCandidate(
    name="玛蒂尔达",
    category="人物",
    source="100-UTTU人物合辑/神秘学家｜Arcanists/玛蒂尔达｜Matilda Bouanich.md",
    heading_path="玛蒂尔达 > 神秘术",
    chunk_index=2,
    content="...",
    vector_score=0.61,
    retrieval_stage="entity_name",
)
```

Stage 2 returns final source dictionaries compatible with the current frontend:

```python
{
    "name": "玛蒂尔达",
    "category": "人物",
    "source": "100-UTTU人物合辑/神秘学家｜Arcanists/玛蒂尔达｜Matilda Bouanich.md",
    "score": 78.4,
    "content": "...",
    "heading_path": "玛蒂尔达 > 神秘术",
    "chunk_index": 2,
    "retrieval_stage": "entity_name",
    "debug": {
        "intent": "skill",
        "section_score": 40.0,
        "vector_score": 0.61,
    },
}
```

---

### Task 1: Stage 0 Query Plan

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/query_plan.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_query_plan.py`

- [ ] **Step 1: Write the failing query-plan tests**

Create `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_query_plan.py`:

```python
import json

from langchain_core.messages import AIMessage

from src.rag.query_plan import QueryPlan, QueryPlanner


class _FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=json.dumps(self.payload, ensure_ascii=False))


def test_query_planner_parses_llm_json_for_skill_question():
    planner = QueryPlanner(_FakeLLM({
        "normalized_query": "玛蒂尔达的技能、神秘术、传承和塑造是什么？",
        "entity": "玛蒂尔达",
        "aliases": ["玛蒂尔达", "Matilda Bouanich"],
        "intent": "skill",
        "section_hints": ["神秘术", "传承", "塑造"],
        "scatter_terms": ["玛蒂尔达", "Matilda Bouanich"],
        "confidence": 0.92,
    }))

    plan = planner.plan("玛蒂儿达技能是啥", category="人物")

    assert plan.original_query == "玛蒂儿达技能是啥"
    assert plan.normalized_query == "玛蒂尔达的技能、神秘术、传承和塑造是什么？"
    assert plan.entity == "玛蒂尔达"
    assert plan.aliases == ("玛蒂尔达", "Matilda Bouanich")
    assert plan.intent == "skill"
    assert plan.section_hints == ("神秘术", "传承", "塑造")
    assert plan.scatter_terms == ("玛蒂尔达", "Matilda Bouanich")
    assert plan.confidence == 0.92


def test_query_planner_fallback_when_llm_is_missing():
    planner = QueryPlanner(None)

    plan = planner.plan("玛蒂尔达的技能是什么")

    assert isinstance(plan, QueryPlan)
    assert plan.normalized_query == "玛蒂尔达的技能是什么"
    assert plan.intent == "skill"
    assert plan.section_hints == ("神秘术", "传承", "塑造")
    assert plan.scatter_terms == ("玛蒂尔达",)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_query_plan.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.rag.query_plan'`.

- [ ] **Step 3: Implement `query_plan.py`**

Create `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/query_plan.py`:

```python
"""Stage 0 query planning for retrieval."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from langchain_core.messages import HumanMessage, SystemMessage


VALID_INTENTS = {"skill", "profile", "voice", "lore", "psychube", "general"}

INTENT_SECTION_HINTS: dict[str, tuple[str, ...]] = {
    "skill": ("神秘术", "传承", "塑造"),
    "profile": ("概览", "基本信息", "尤提姆", "洞悉材料"),
    "voice": ("语音",),
    "lore": ("文化", "剧情", "故事", "箱中日历"),
    "psychube": ("心相", "相从心生"),
    "general": (),
}


@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    normalized_query: str
    entity: str | None
    aliases: tuple[str, ...]
    intent: str
    section_hints: tuple[str, ...]
    scatter_terms: tuple[str, ...]
    confidence: float


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, Iterable):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
        return tuple(out)
    return ()


def _guess_intent(query: str) -> str:
    patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("skill", ("技能", "神秘术", "大招", "至终", "仪式", "传承", "洞悉", "塑造")),
        ("voice", ("语音", "台词", "互动", "对白")),
        ("psychube", ("心相", "搭配", "推荐")),
        ("lore", ("剧情", "故事", "关系", "经历", "事件", "日历")),
        ("profile", ("介绍", "是谁", "基础", "生日", "属性", "星级", "定位")),
    )
    for intent, keywords in patterns:
        if any(keyword in query for keyword in keywords):
            return intent
    return "general"


def _guess_scatter_terms(query: str) -> tuple[str, ...]:
    candidates = re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z·｜ -]{1,32}", query)
    cleaned: list[str] = []
    stop_words = {"介绍一下", "是什么", "技能", "是谁", "的", "一下"}
    for candidate in candidates:
        term = candidate.strip(" ？?，,。")
        if term and term not in stop_words and term not in cleaned:
            cleaned.append(term)
    return tuple(cleaned[:3])


class QueryPlanner:
    """Use the answer LLM to normalize a question into a retrieval plan."""

    def __init__(self, llm: Any | None) -> None:
        self._llm = llm

    def plan(self, query: str, category: str | None = None) -> QueryPlan:
        if self._llm is None:
            return self._fallback(query)
        try:
            messages = [
                SystemMessage(content=self._system_prompt()),
                HumanMessage(content=json.dumps({
                    "question": query,
                    "category": category,
                }, ensure_ascii=False)),
            ]
            response = self._llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            payload = self._extract_json(content)
            return self._from_payload(query, payload)
        except Exception:
            return self._fallback(query)

    def _system_prompt(self) -> str:
        return (
            "你是 Reverse:1999 知识库的检索规划器。"
            "只输出 JSON，不回答用户问题。"
            "字段必须包含 normalized_query, entity, aliases, intent, section_hints, scatter_terms, confidence。"
            "intent 只能是 skill/profile/voice/lore/psychube/general。"
            "如果用户有错别字，请修正角色名；如果不确定实体，entity 使用 null。"
        )

    def _extract_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        return json.loads(text)

    def _from_payload(self, original_query: str, payload: dict[str, Any]) -> QueryPlan:
        intent = str(payload.get("intent") or "general").strip()
        if intent not in VALID_INTENTS:
            intent = _guess_intent(original_query)
        aliases = _as_tuple(payload.get("aliases"))
        entity = payload.get("entity")
        entity_text = str(entity).strip() if entity else None
        section_hints = _as_tuple(payload.get("section_hints")) or INTENT_SECTION_HINTS[intent]
        scatter_terms = _as_tuple(payload.get("scatter_terms")) or aliases or ((entity_text,) if entity_text else ())
        normalized_query = str(payload.get("normalized_query") or original_query).strip()
        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return QueryPlan(
            original_query=original_query,
            normalized_query=normalized_query or original_query,
            entity=entity_text,
            aliases=aliases,
            intent=intent,
            section_hints=section_hints,
            scatter_terms=scatter_terms,
            confidence=max(0.0, min(1.0, confidence)),
        )

    def _fallback(self, query: str) -> QueryPlan:
        intent = _guess_intent(query)
        terms = _guess_scatter_terms(query)
        return QueryPlan(
            original_query=query,
            normalized_query=query,
            entity=terms[0] if len(terms) == 1 else None,
            aliases=terms,
            intent=intent,
            section_hints=INTENT_SECTION_HINTS[intent],
            scatter_terms=terms,
            confidence=0.0,
        )
```

- [ ] **Step 4: Run query-plan tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_query_plan.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/rag/query_plan.py tests/test_query_plan.py
git commit -m "feat: add stage 0 query planner"
```

---

### Task 2: Stage 1 Entity Packet Retrieval

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/entity_packet.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/vectorstore.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_entity_packet.py`

- [ ] **Step 1: Write the failing entity-packet tests**

Create `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_entity_packet.py`:

```python
from src.rag.entity_packet import EntityPacketRetriever
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
                {"id": "m#0002", "text": "## 神秘术\n天才习作", "name": "玛蒂尔达", "category": "人物", "source": "玛蒂尔达.md", "heading_path": "玛蒂尔达 > 神秘术", "chunk_index": 2},
                {"id": "m#0011", "text": "## 语音\n初遇", "name": "玛蒂尔达", "category": "人物", "source": "玛蒂尔达.md", "heading_path": "玛蒂尔达 > 语音", "chunk_index": 11},
            ]
        if 'text like "%Matilda Bouanich%"' in expr:
            return [
                {"id": "hop#0000", "text": "Matilda Bouanich 相关心相说明", "name": "跳房子游戏", "category": "心相", "source": "跳房子游戏.md", "heading_path": "", "chunk_index": 0},
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
        {"id": "same", "text": "A", "name": "玛蒂尔达", "category": "人物", "source": "玛蒂尔达.md", "heading_path": "神秘术", "chunk_index": 1},
        {"id": "same", "text": "A", "name": "玛蒂尔达", "category": "人物", "source": "玛蒂尔达.md", "heading_path": "神秘术", "chunk_index": 1},
    ]

    packet = EntityPacketRetriever(vectorstore).collect(_plan(), category=None, vector_k=8)

    assert len(packet) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_entity_packet.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.rag.entity_packet'`.

- [ ] **Step 3: Add read-only query helpers to `vectorstore.py`**

Modify `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/vectorstore.py` inside `MilvusVectorstore`:

```python
    def query_rows(self, expr: str, limit: int = 10000) -> list[dict[str, Any]]:
        return self.client.query(
            collection_name=self.collection_name,
            filter=expr,
            output_fields=[
                PRIMARY_FIELD,
                TEXT_FIELD,
                "source",
                "name",
                "category",
                "heading_path",
                "chunk_index",
            ],
            limit=limit,
        )
```

- [ ] **Step 4: Implement `entity_packet.py`**

Create `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/entity_packet.py`:

```python
"""Stage 1 entity packet retrieval."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document

from src.rag.query_plan import QueryPlan


def escape_milvus_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


@dataclass(frozen=True)
class RetrievalCandidate:
    name: str
    category: str
    source: str
    heading_path: str
    chunk_index: int
    content: str
    vector_score: float
    retrieval_stage: str
    id: str = ""


def _candidate_key(item: RetrievalCandidate) -> tuple[str, str, int, str]:
    if item.id:
        return (item.id, "", -1, "")
    return (item.source, item.heading_path, item.chunk_index, item.content[:120])


def _from_row(row: dict[str, Any], retrieval_stage: str, vector_score: float = 0.0) -> RetrievalCandidate:
    return RetrievalCandidate(
        id=str(row.get("id", "")),
        name=str(row.get("name", "")),
        category=str(row.get("category", "")),
        source=str(row.get("source", "")),
        heading_path=str(row.get("heading_path", "")),
        chunk_index=int(row.get("chunk_index") or 0),
        content=str(row.get("text", "")),
        vector_score=float(vector_score),
        retrieval_stage=retrieval_stage,
    )


def _from_doc(doc: Document, score: float, retrieval_stage: str) -> RetrievalCandidate:
    metadata = doc.metadata
    return RetrievalCandidate(
        id=str(metadata.get("id", "")),
        name=str(metadata.get("name", "")),
        category=str(metadata.get("category", "")),
        source=str(metadata.get("source", "")),
        heading_path=str(metadata.get("heading_path", "")),
        chunk_index=int(metadata.get("chunk_index") or 0),
        content=doc.page_content,
        vector_score=float(score),
        retrieval_stage=retrieval_stage,
    )


class EntityPacketRetriever:
    """Collect all likely relevant chunks before Stage 2 reranking."""

    def __init__(self, vectorstore: Any) -> None:
        self._vs = vectorstore

    def collect(self, plan: QueryPlan, category: str | None, vector_k: int) -> list[RetrievalCandidate]:
        candidates: list[RetrievalCandidate] = []
        if plan.entity:
            candidates.extend(self._query_by_entity(plan.entity, category))
        for term in plan.scatter_terms:
            candidates.extend(self._query_by_text_like(term, category))
        candidates.extend(self._vector_candidates(plan, category, vector_k))
        return self._dedupe(candidates)

    def _query_by_entity(self, entity: str, category: str | None) -> list[RetrievalCandidate]:
        filters = [f'name == "{escape_milvus_string(entity)}"']
        if category:
            filters.append(f'category == "{escape_milvus_string(category)}"')
        return [
            _from_row(row, "entity_name")
            for row in self._query_rows(" and ".join(filters))
        ]

    def _query_by_text_like(self, term: str, category: str | None) -> list[RetrievalCandidate]:
        if not term:
            return []
        filters = [f'text like "%{escape_milvus_string(term)}%"']
        if category:
            filters.append(f'category == "{escape_milvus_string(category)}"')
        return [
            _from_row(row, "scatter_text")
            for row in self._query_rows(" and ".join(filters))
        ]

    def _query_rows(self, expr: str) -> list[dict[str, Any]]:
        if not hasattr(self._vs, "query_rows"):
            return []
        try:
            return list(self._vs.query_rows(expr, limit=10000))
        except Exception:
            return []

    def _vector_candidates(self, plan: QueryPlan, category: str | None, vector_k: int) -> list[RetrievalCandidate]:
        expr = f'category == "{escape_milvus_string(category)}"' if category else None
        try:
            results = self._vs.similarity_search_with_relevance_scores(
                plan.normalized_query,
                k=vector_k,
                expr=expr,
            )
        except Exception:
            return []
        return [_from_doc(doc, score, "vector") for doc, score in results]

    def _dedupe(self, items: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        seen: set[tuple[str, str, int, str]] = set()
        output: list[RetrievalCandidate] = []
        for item in items:
            key = _candidate_key(item)
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output
```

- [ ] **Step 5: Run entity-packet tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_entity_packet.py tests/test_vectorstore.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/rag/entity_packet.py src/rag/vectorstore.py tests/test_entity_packet.py tests/test_vectorstore.py
git commit -m "feat: collect entity retrieval packets"
```

---

### Task 3: Robust Intent Router and Context Packer

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/reranker.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_reranker.py`

- [ ] **Step 1: Write the failing reranker tests**

Create `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_reranker.py`:

```python
from src.rag.entity_packet import RetrievalCandidate
from src.rag.query_plan import QueryPlan
from src.rag.reranker import RobustIntentRouter


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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_reranker.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.rag.reranker'`.

- [ ] **Step 3: Implement `reranker.py`**

Create `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/reranker.py`:

```python
"""Stage 2 robust intent routing, section reranking, and context packing."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.rag.entity_packet import RetrievalCandidate
from src.rag.query_plan import INTENT_SECTION_HINTS, QueryPlan


NOISE_HEADINGS = ("语音", "单品", "箱中日历")
QUERY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "skill": ("技能", "神秘术", "大招", "至终", "仪式", "传承", "洞悉", "塑造"),
    "profile": ("介绍", "是谁", "基础", "生日", "属性", "星级", "定位"),
    "voice": ("语音", "台词", "互动", "对白"),
    "lore": ("剧情", "故事", "关系", "经历", "事件", "日历"),
    "psychube": ("心相", "搭配", "推荐"),
}


@dataclass(frozen=True)
class SectionGroup:
    source: str
    heading_path: str
    items: tuple[RetrievalCandidate, ...]
    score: float
    debug: dict[str, float | str]


class RobustIntentRouter:
    """Combine Stage 0 intent with actual Stage 1 headings before packing context."""

    def rerank(self, plan: QueryPlan, candidates: list[RetrievalCandidate], limit: int) -> list[dict]:
        if not candidates:
            return []
        router_intent = self._confirm_intent(plan, candidates)
        groups = self._group(candidates)
        scored = [self._score_group(plan, router_intent, group) for group in groups]
        scored.sort(key=lambda group: (-group.score, group.source, min(item.chunk_index for item in group.items)))
        return self._pack(plan, router_intent, scored, limit)

    def _confirm_intent(self, plan: QueryPlan, candidates: list[RetrievalCandidate]) -> str:
        if plan.intent != "general":
            return plan.intent
        headings = " ".join(item.heading_path for item in candidates)
        query = plan.normalized_query + " " + plan.original_query
        for intent, hints in INTENT_SECTION_HINTS.items():
            if any(hint and hint in headings for hint in hints):
                if any(keyword in query for keyword in QUERY_KEYWORDS.get(intent, ())):
                    return intent
        if any(keyword in query for keyword in QUERY_KEYWORDS["skill"]):
            return "skill"
        return "general"

    def _group(self, candidates: list[RetrievalCandidate]) -> list[SectionGroup]:
        buckets: dict[tuple[str, str], list[RetrievalCandidate]] = defaultdict(list)
        for item in candidates:
            buckets[(item.source, item.heading_path)].append(item)
        groups: list[SectionGroup] = []
        for (source, heading_path), items in buckets.items():
            ordered = tuple(sorted(items, key=lambda item: item.chunk_index))
            groups.append(SectionGroup(source=source, heading_path=heading_path, items=ordered, score=0.0, debug={}))
        return groups

    def _score_group(self, plan: QueryPlan, router_intent: str, group: SectionGroup) -> SectionGroup:
        hints = plan.section_hints or INTENT_SECTION_HINTS.get(router_intent, ())
        heading = group.heading_path
        content = "\n".join(item.content for item in group.items)
        section_score = 40.0 if any(hint and hint in heading for hint in hints) else 0.0
        keyword_score = self._keyword_score(plan, router_intent, heading + "\n" + content)
        vector_score = max((item.vector_score for item in group.items), default=0.0) * 20.0
        entity_score = 10.0 if plan.entity and any(item.name == plan.entity for item in group.items) else 0.0
        adjacency_bonus = 5.0 if len(group.items) > 1 else 0.0
        noise_penalty = self._noise_penalty(router_intent, heading)
        score = section_score + keyword_score + vector_score + entity_score + adjacency_bonus - noise_penalty
        return SectionGroup(
            source=group.source,
            heading_path=group.heading_path,
            items=group.items,
            score=score,
            debug={
                "router_intent": router_intent,
                "section_score": section_score,
                "keyword_score": keyword_score,
                "vector_score": vector_score,
                "entity_score": entity_score,
                "adjacency_bonus": adjacency_bonus,
                "noise_penalty": noise_penalty,
            },
        )

    def _keyword_score(self, plan: QueryPlan, router_intent: str, text: str) -> float:
        keywords = QUERY_KEYWORDS.get(router_intent, ())
        query_text = plan.normalized_query + " " + plan.original_query
        score = 0.0
        for keyword in keywords:
            if keyword in query_text and keyword in text:
                score += 6.0
        return min(score, 24.0)

    def _noise_penalty(self, router_intent: str, heading_path: str) -> float:
        if router_intent == "voice":
            return 0.0
        if "语音" in heading_path:
            return 28.0
        if router_intent in {"lore", "general"}:
            return 0.0
        return 8.0 if any(noise in heading_path for noise in NOISE_HEADINGS) else 0.0

    def _pack(self, plan: QueryPlan, router_intent: str, groups: list[SectionGroup], limit: int) -> list[dict]:
        packed: list[dict] = []
        for group in groups:
            for item in group.items:
                packed.append({
                    "name": item.name,
                    "category": item.category,
                    "source": item.source,
                    "score": float(group.score),
                    "content": item.content,
                    "heading_path": item.heading_path,
                    "chunk_index": item.chunk_index,
                    "retrieval_stage": item.retrieval_stage,
                    "debug": {
                        **group.debug,
                        "intent": plan.intent,
                        "router_intent": router_intent,
                    },
                })
                if len(packed) >= limit:
                    return packed
        return packed
```

- [ ] **Step 4: Run reranker tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_reranker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/rag/reranker.py tests/test_reranker.py
git commit -m "feat: add robust intent section reranker"
```

---

### Task 4: Wire Stage 1 and Stage 2 into Retriever

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/retriever.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_retriever.py`

- [ ] **Step 1: Add retriever integration tests**

Append to `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_retriever.py`:

```python
from src.rag.query_plan import QueryPlan


class _PacketFakeVectorstore:
    def query_rows(self, expr: str, limit: int = 10000):
        if 'name == "玛蒂尔达"' in expr:
            return [
                {"id": "voice", "text": "语音内容", "name": "玛蒂尔达", "category": "人物", "source": "玛蒂尔达.md", "heading_path": "玛蒂尔达 > 语音", "chunk_index": 11},
                {"id": "skill-a", "text": "神秘术一：天才习作", "name": "玛蒂尔达", "category": "人物", "source": "玛蒂尔达.md", "heading_path": "玛蒂尔达 > 神秘术", "chunk_index": 2},
                {"id": "skill-b", "text": "神秘术二：众望瞩目", "name": "玛蒂尔达", "category": "人物", "source": "玛蒂尔达.md", "heading_path": "玛蒂尔达 > 神秘术", "chunk_index": 3},
            ]
        return []

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, expr: str | None = None):
        return []


def test_search_with_query_plan_returns_skill_section_before_voice(tmp_path):
    retriever = Retriever(_cfg(tmp_path), _PacketFakeVectorstore())
    plan = QueryPlan(
        original_query="玛蒂尔达的技能是什么",
        normalized_query="玛蒂尔达的技能、神秘术、传承和塑造是什么？",
        entity="玛蒂尔达",
        aliases=("玛蒂尔达", "Matilda Bouanich"),
        intent="skill",
        section_hints=("神秘术", "传承", "塑造"),
        scatter_terms=("玛蒂尔达", "Matilda Bouanich"),
        confidence=0.9,
    )

    results = retriever.search(plan.normalized_query, k=3, category="人物", query_plan=plan)

    assert [item["heading_path"] for item in results[:2]] == ["玛蒂尔达 > 神秘术", "玛蒂尔达 > 神秘术"]
    assert results[0]["debug"]["router_intent"] == "skill"
```

- [ ] **Step 2: Run retriever tests to verify failure**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_retriever.py -q
```

Expected: FAIL with `TypeError: search() got an unexpected keyword argument 'query_plan'`.

- [ ] **Step 3: Modify `Retriever.search(...)`**

Modify `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/retriever.py`:

```python
from src.rag.entity_packet import EntityPacketRetriever
from src.rag.query_plan import QueryPlan
from src.rag.reranker import RobustIntentRouter
```

Add these fields in `Retriever.__init__`:

```python
        self._packet_retriever = EntityPacketRetriever(vectorstore)
        self._router = RobustIntentRouter()
```

Change the method signature and first branch of `search`:

```python
    def search(
        self,
        query: str,
        k: int | None = None,
        category: str | None = None,
        query_plan: QueryPlan | None = None,
    ) -> list[dict[str, Any]]:
        top_k = k or self._cfg.rag.top_k
        if query_plan is not None and (query_plan.entity or query_plan.scatter_terms):
            packet = self._packet_retriever.collect(
                query_plan,
                category=category,
                vector_k=max(top_k * 3, 12),
            )
            ranked = self._router.rerank(query_plan, packet, limit=top_k)
            if ranked:
                return ranked

        entity_name = self._detect_entity_name(query, category)
        kwargs = self._search_kwargs(top_k, category, name=entity_name)
        results = self._similarity_search(query, kwargs)
        if entity_name and not results:
            fallback_kwargs = self._search_kwargs(top_k, category)
            results = self._similarity_search(query, fallback_kwargs)

        out: list[dict[str, Any]] = []
        for doc, score in results:
            out.append({
                "name": doc.metadata.get("name", ""),
                "category": doc.metadata.get("category", ""),
                "source": doc.metadata.get("source", ""),
                "score": float(score),
                "content": doc.page_content,
                "heading_path": doc.metadata.get("heading_path", ""),
                "chunk_index": int(doc.metadata.get("chunk_index", 0) or 0),
                "retrieval_stage": "legacy_vector",
                "debug": {},
            })
        return out
```

- [ ] **Step 4: Run retriever tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_retriever.py tests/test_entity_packet.py tests/test_reranker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/rag/retriever.py tests/test_retriever.py
git commit -m "feat: route retriever through entity packets"
```

---

### Task 5: Wire Query Plan into RAGChain, SSE, and API Sources

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/chain.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/schemas.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_sse.py`

- [ ] **Step 1: Add tests for shared retrieval in streaming**

Append to `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_sse.py`:

```python
def test_ask_stream_uses_chain_retrieve_when_available(monkeypatch):
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class ChainWithRetrieve:
        def __init__(self):
            self.retrieve_calls = []
            self._tokens = ["ok"]

        def retrieve(self, question, category=None):
            self.retrieve_calls.append((question, category))
            return {
                "plan": None,
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": category or "人物",
                    "source": "玛蒂尔达.md",
                    "score": 1.0,
                    "content": "神秘术内容",
                    "heading_path": "玛蒂尔达 > 神秘术",
                    "chunk_index": 2,
                    "retrieval_stage": "entity_name",
                    "debug": {"router_intent": "skill"},
                }],
                "context": "[玛蒂尔达] 神秘术内容",
            }

        def llm_ready(self):
            return True

        def _stream_llm(self, question, context):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content="ok")

    chain = ChainWithRetrieve()
    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": chain,
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream("POST", "/ask/stream", json={"question": "玛蒂尔达的技能是什么", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)
    assert chain.retrieve_calls == [("玛蒂尔达的技能是什么", "人物")]
    assert events[0][0] == "sources"
    assert events[0][1]["sources"][0]["heading_path"] == "玛蒂尔达 > 神秘术"
```

- [ ] **Step 2: Run SSE test to verify failure**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_sse.py::test_ask_stream_uses_chain_retrieve_when_available -q
```

Expected: FAIL because `rag_stream_generator` still calls `chain._retriever.search(...)` directly.

- [ ] **Step 3: Modify `chain.py`**

Modify `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/chain.py`:

```python
from src.rag.query_plan import QueryPlanner
```

Add in `RAGChain.__init__` after `_llm`:

```python
        self._query_planner = QueryPlanner(self._llm)
```

Add methods to `RAGChain`:

```python
    def retrieve(self, question: str, category: str | None = None) -> dict[str, Any]:
        plan = self._query_planner.plan(question, category=category)
        sources = self._retriever.search(
            plan.normalized_query,
            category=category,
            query_plan=plan,
        )
        context = self._format_context(sources)
        return {"plan": plan, "sources": sources, "context": context}

    def _format_context(self, sources: list[dict[str, Any]]) -> str:
        parts = []
        for source in sources:
            heading = source.get("heading_path") or ""
            label = source["name"]
            if heading:
                label = f"{label} / {heading}"
            parts.append(f"[{label}] {source['content']}")
        return "\n\n".join(parts)
```

Change `ask(...)` retrieval block:

```python
        retrieved = self.retrieve(question, category=category)
        sources = retrieved["sources"]
        if not self.llm_ready():
            return {"answer": _API_KEY_EMPTY_MSG, "sources": sources}

        if not sources:
            return {"answer": "知识库中未找到相关内容。", "sources": []}

        context = retrieved["context"]
        messages = self._prompt.format_messages(context=context, question=question)
```

- [ ] **Step 4: Modify `sse.py`**

Change the retrieval block in `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`:

```python
    try:
        if hasattr(chain, "retrieve"):
            retrieved = chain.retrieve(question, category=category)
            sources = retrieved["sources"]
            context = retrieved["context"]
        else:
            sources = chain._retriever.search(question, category=category)
            context = "\n\n".join(f"[{s['name']}] {s['content']}" for s in sources)
    except Exception as e:
        yield sse_event("error", {"message": f"检索失败: {e}"})
        return
```

Then remove the later duplicate context assignment:

```python
    context = "\n\n".join(f"[{s['name']}] {s['content']}" for s in sources)
```

- [ ] **Step 5: Modify `schemas.py`**

Change `SourceItem` in `D:/PycharmProjects/nlp/LangChain/1999Search/backend/schemas.py`:

```python
class SourceItem(BaseModel):
    name: str
    category: str
    source: str
    score: float
    heading_path: Optional[str] = None
    chunk_index: Optional[int] = None
    retrieval_stage: Optional[str] = None
```

Change source construction in `D:/PycharmProjects/nlp/LangChain/1999Search/backend/main.py`:

```python
    sources = [
        SourceItem(
            name=s["name"],
            category=s["category"],
            source=s["source"],
            score=s["score"],
            heading_path=s.get("heading_path"),
            chunk_index=s.get("chunk_index"),
            retrieval_stage=s.get("retrieval_stage"),
        )
        for s in result.get("sources", [])
    ]
```

Change `source_items` construction in `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`:

```python
    source_items = [
        {
            "name": s["name"],
            "category": s["category"],
            "source": s["source"],
            "score": s["score"],
            "heading_path": s.get("heading_path"),
            "chunk_index": s.get("chunk_index"),
            "retrieval_stage": s.get("retrieval_stage"),
        }
        for s in sources
    ]
```

- [ ] **Step 6: Run API and SSE tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_sse.py tests/test_retriever.py tests/test_query_plan.py tests/test_entity_packet.py tests/test_reranker.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```powershell
git add src/rag/chain.py backend/sse.py backend/schemas.py backend/main.py tests/test_sse.py
git commit -m "feat: use query plans in rag chain"
```

---

### Task 6: Verification Against Milvus and Manual RAG Check

**Files:**
- No new implementation files.

- [ ] **Step 1: Run focused Python tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_query_plan.py tests/test_entity_packet.py tests/test_reranker.py tests/test_retriever.py tests/test_sse.py tests/test_vectorstore.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the broader backend/RAG test slice**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_config.py tests/test_categories.py tests/test_extractor.py tests/test_prompts.py tests/test_text_cleaner.py tests/test_start_scripts.py tests/test_milvus_compose.py -q
```

Expected: PASS.

- [ ] **Step 3: Manual Milvus check for Matilda section ordering**

Run with the LangChain environment and valid `.env` keys:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python - <<'PY'
from config.config import get_config
from src.rag.vectorstore import load_vectorstore
from src.rag.retriever import Retriever
from src.rag.query_plan import QueryPlan

cfg = get_config()
vs = load_vectorstore(cfg)
retriever = Retriever(cfg, vs)
plan = QueryPlan(
    original_query="玛蒂尔达的技能是什么",
    normalized_query="玛蒂尔达的技能、神秘术、传承和塑造是什么？",
    entity="玛蒂尔达",
    aliases=("玛蒂尔达", "Matilda Bouanich"),
    intent="skill",
    section_hints=("神秘术", "传承", "塑造"),
    scatter_terms=("玛蒂尔达", "Matilda Bouanich"),
    confidence=0.9,
)
results = retriever.search(plan.normalized_query, k=6, category="人物", query_plan=plan)
for item in results:
    print(item["heading_path"], item["chunk_index"], item["score"], item["content"][:60].replace("\\n", " "))
PY
```

Expected first results:

```text
...神秘术... 2 ...
...神秘术... 3 ...
```

Voice chunks may appear only after the relevant skill sections or not appear within the first six rows.

- [ ] **Step 4: Manual API check**

Start backend and frontend with the existing start script:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
.\start.ps1
```

Ask in the frontend:

```text
玛蒂儿达技能是啥
```

Expected behavior:

- The answer discusses Matilda's skill or 神秘术 content.
- Source list contains `玛蒂尔达` with `heading_path` including `神秘术`.
- It does not answer "知识库中未找到相关内容。"

- [ ] **Step 5: Commit verification notes if a docs update is made**

If `README.md` or `docs/architecture.md` is updated to document the pipeline, commit with:

```powershell
git add README.md docs/architecture.md
git commit -m "docs: document two stage rag retrieval"
```

If no docs file is changed, skip this commit.

---

## Self-Review

- Spec coverage:
  - Stage 0 LLM query optimization is covered by Task 1 and Task 5.
  - Stage 1 full entity packet retrieval is covered by Task 2 and Task 4.
  - Robust Intent Router using Stage 0 intent plus actual Stage 1 `heading_path` is covered by Task 3.
  - Vector similarity participation as a scoring feature is covered by Task 2 vector candidates and Task 3 `vector_score`.
  - SSE and normal `/ask` parity is covered by Task 5.
- Placeholder scan:
  - No implementation step relies on an unnamed function, unspecified file, or undefined command.
  - No step contains open-ended wording that leaves implementation unspecified.
- Type consistency:
  - `QueryPlan`, `RetrievalCandidate`, `RobustIntentRouter.rerank(...)`, and `Retriever.search(..., query_plan=...)` are defined before later tasks use them.
  - Source dictionaries preserve existing `name/category/source/score/content` keys and add optional metadata fields.
