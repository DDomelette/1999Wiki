from __future__ import annotations

import json
import hashlib
import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from src.rag.chinese_analyzer import AnalyzerIdentity, ChineseBM25Analyzer


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
_LEGACY_SCHEMAS = frozenset(
    ("huiji.bm25-index/v2", "huiji.media-binding-bm25/v3")
)
_NEW_SCHEMA_RECORD_KINDS = {
    "rag.local-bm25/v2": "local",
    "huiji.bm25-index/v3": "child",
    "huiji.media-binding-bm25/v4": "media_binding",
}
_LEGACY_ANALYZER_PAYLOAD = {"schema_version": "legacy-regex/v1"}
_ANALYZER_PROBES = (
    "槲寄生的基础资料",
    "十四行诗的技能是什么",
    "Data:Story/304502",
    "Skill-30410111",
    "Banner_今夜星光灿烂.png",
)


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


def legacy_tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]+", text.lower())


tokenize = legacy_tokenize


class TextAnalyzer(Protocol):
    identity: object

    def analyze(self, text: str) -> list[str]: ...


def analyzer_probe_sha256(analyzer: TextAnalyzer) -> str:
    token_arrays = [analyzer.analyze(probe) for probe in _ANALYZER_PROBES]
    payload = (
        json.dumps(
            token_arrays,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class LegacyRegexAnalyzer:
    identity: str = "legacy-regex/v1"

    def analyze(self, text: str) -> list[str]:
        return legacy_tokenize(text)


def _validate_bm25_parameters(k1: float, b: float) -> tuple[float, float]:
    if isinstance(k1, bool) or not isinstance(k1, (int, float)):
        raise TypeError("k1 must be a finite number greater than zero")
    if isinstance(b, bool) or not isinstance(b, (int, float)):
        raise TypeError("b must be a finite number between zero and one")
    normalized_k1 = float(k1)
    normalized_b = float(b)
    if not math.isfinite(normalized_k1) or normalized_k1 <= 0:
        raise ValueError("k1 must be a finite number greater than zero")
    if not math.isfinite(normalized_b) or not 0 <= normalized_b <= 1:
        raise ValueError("b must be a finite number between zero and one")
    return normalized_k1, normalized_b


def _validated_records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(record, Mapping) for record in value):
        raise ValueError("BM25 payload records are invalid")
    return [dict(record) for record in value]


def _serialize_analyzer(analyzer: TextAnalyzer) -> dict[str, object]:
    identity = analyzer.identity
    if identity == "legacy-regex/v1":
        return dict(_LEGACY_ANALYZER_PAYLOAD)
    if isinstance(identity, AnalyzerIdentity):
        return identity.to_dict()
    raise ValueError("BM25 analyzer identity is unsupported")


def _load_new_analyzer(
    value: object,
    *,
    allow_legacy: bool,
) -> TextAnalyzer:
    if not isinstance(value, Mapping):
        raise ValueError("BM25 analyzer metadata is invalid")
    analyzer_payload = dict(value)
    if analyzer_payload == _LEGACY_ANALYZER_PAYLOAD:
        if allow_legacy:
            return LegacyRegexAnalyzer()
        raise ValueError("BM25 analyzer metadata is unsupported")
    try:
        identity = AnalyzerIdentity.from_dict(analyzer_payload)
        analyzer = ChineseBM25Analyzer(
            dictionary_path=os.devnull,
            extra_terms=identity.dictionary_terms,
            config=identity.config,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"BM25 analyzer metadata is invalid: {error}") from error
    if analyzer.identity != identity:
        raise ValueError("BM25 analyzer identity mismatch")
    return analyzer


def _load_payload(payload: object) -> tuple[TextAnalyzer, float, float, list[dict[str, Any]]]:
    if not isinstance(payload, Mapping):
        raise ValueError("BM25 payload must be an object")
    payload_mapping = dict(payload)
    schema_version = payload_mapping.get("schema_version")
    if schema_version is None:
        if set(payload_mapping) != {"records"}:
            raise ValueError("BM25 records-only payload shape is invalid")
        return (
            LegacyRegexAnalyzer(),
            1.5,
            0.75,
            _validated_records(payload_mapping["records"]),
        )
    if schema_version in _LEGACY_SCHEMAS:
        return (
            LegacyRegexAnalyzer(),
            1.5,
            0.75,
            _validated_records(payload_mapping.get("records")),
        )
    expected_record_kind = _NEW_SCHEMA_RECORD_KINDS.get(schema_version)
    if expected_record_kind is None:
        raise ValueError("BM25 payload schema is unsupported")
    if payload_mapping.get("record_kind") != expected_record_kind:
        raise ValueError("BM25 payload record kind is invalid")
    if "analyzer" not in payload_mapping or "bm25" not in payload_mapping:
        raise ValueError("BM25 payload metadata is missing")
    bm25 = payload_mapping["bm25"]
    if not isinstance(bm25, Mapping) or "k1" not in bm25 or "b" not in bm25:
        raise ValueError("BM25 parameter metadata is invalid")
    k1, b = _validate_bm25_parameters(bm25["k1"], bm25["b"])
    analyzer = _load_new_analyzer(
        payload_mapping["analyzer"],
        allow_legacy=schema_version == "rag.local-bm25/v2",
    )
    records = _validated_records(payload_mapping.get("records"))
    return analyzer, k1, b, records


class LocalBM25SparseIndex:
    def __init__(
        self,
        analyzer: TextAnalyzer | None = None,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1, self.b = _validate_bm25_parameters(k1, b)
        self.analyzer = LegacyRegexAnalyzer() if analyzer is None else analyzer
        self.records: list[dict[str, Any]] = []
        self.doc_terms: list[Counter[str]] = []
        self.df: Counter[str] = Counter()
        self.avgdl = 0.0

    def build(self, records: list[dict[str, Any]]) -> None:
        next_records = list(records)
        next_doc_terms: list[Counter[str]] = []
        next_df: Counter[str] = Counter()
        total_len = 0
        for record in next_records:
            terms = Counter(
                self.analyzer.analyze(str(record.get("search_text") or record.get("text") or ""))
            )
            next_doc_terms.append(terms)
            total_len += sum(terms.values())
            for term in terms:
                next_df[term] += 1
        next_avgdl = total_len / len(next_records) if next_records else 0.0
        self.records = next_records
        self.doc_terms = next_doc_terms
        self.df = next_df
        self.avgdl = next_avgdl

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        q_terms = self.analyzer.analyze(query)
        if not q_terms:
            return []
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
        payload = {
            "schema_version": "rag.local-bm25/v2",
            "record_kind": "local",
            "analyzer": _serialize_analyzer(self.analyzer),
            "bm25": {"k1": self.k1, "b": self.b},
            "records": self.records,
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(
                    payload,
                    temporary,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: str | Path) -> "LocalBM25SparseIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        analyzer, k1, b, records = _load_payload(payload)
        index = cls(analyzer=analyzer, k1=k1, b=b)
        index.build(records)
        return index
