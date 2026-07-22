from __future__ import annotations

import json
import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


_CHILD_SEMANTIC_FIELDS = (
    "child_id",
    "parent_id",
    "text",
    "search_text",
    "entity_id",
    "entity_name",
    "entity_type",
    "category",
    "section_kind",
    "title",
    "depth_level",
    "media_policy",
    "ancestor_ids",
    "quality_flags",
    "route_tags",
    "chunk_index",
)
_SET_LIKE_CHILD_FIELDS = frozenset(("ancestor_ids", "quality_flags", "route_tags"))


def canonical_child_corpus_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    canonical_rows: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for source in rows:
        child_id = str(source.get("child_id") or source.get("id") or "")
        if not child_id:
            raise ValueError("child semantic corpus row requires child_id")
        if child_id in seen_ids:
            raise ValueError(f"duplicate child_id in semantic corpus: {child_id}")
        seen_ids.add(child_id)
        row: dict[str, object] = {}
        for field in _CHILD_SEMANTIC_FIELDS:
            value = child_id if field == "child_id" else source.get(field)
            if field in _SET_LIKE_CHILD_FIELDS:
                value = sorted({str(item) for item in (value or ())})
            row[field] = value
        canonical_rows.append(row)
    canonical_rows.sort(key=lambda row: str(row["child_id"]))
    payload = (
        json.dumps(canonical_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]+", text.lower())


class LocalBM25SparseIndex:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.records: list[dict[str, Any]] = []
        self.doc_terms: list[Counter[str]] = []
        self.df: Counter[str] = Counter()
        self.avgdl = 0.0

    def build(self, records: list[dict[str, Any]]) -> None:
        self.records = list(records)
        self.doc_terms = []
        self.df = Counter()
        total_len = 0
        for record in self.records:
            terms = Counter(tokenize(str(record.get("search_text") or record.get("text") or "")))
            self.doc_terms.append(terms)
            total_len += sum(terms.values())
            for term in terms:
                self.df[term] += 1
        self.avgdl = total_len / len(self.records) if self.records else 0.0

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        q_terms = tokenize(query)
        total_docs = len(self.records)
        scored: list[tuple[float, int]] = []
        for index, terms in enumerate(self.doc_terms):
            doc_len = sum(terms.values()) or 1
            score = 0.0
            for term in q_terms:
                tf = terms.get(term, 0)
                if tf == 0:
                    continue
                idf = math.log(1 + (total_docs - self.df[term] + 0.5) / (self.df[term] + 0.5))
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1))
                score += idf * (tf * (self.k1 + 1)) / denom
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and len(scored) < top_k:
            scored_indexes = {index for _, index in scored}
            for index in range(total_docs):
                if index not in scored_indexes:
                    scored.append((0.0, index))
                if len(scored) >= top_k:
                    break
        return [
            {**self.records[index], "bm25_score": score, "bm25_rank": rank + 1}
            for rank, (score, index) in enumerate(scored[:top_k])
        ]

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"records": self.records}, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "LocalBM25SparseIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls()
        index.build(list(payload.get("records", [])))
        return index
