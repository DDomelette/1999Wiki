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


def _content_key(item: RetrievalCandidate) -> tuple[str, str, int, str]:
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
        seen_content: set[tuple[str, str, int, str]] = set()
        output: list[RetrievalCandidate] = []
        for item in items:
            key = _candidate_key(item)
            content_key = _content_key(item)
            if key in seen or content_key in seen_content:
                continue
            seen.add(key)
            seen_content.add(content_key)
            output.append(item)
        return output
