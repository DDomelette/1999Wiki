from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from time import perf_counter

from src.huiji_rag.build.artifact_writer import _analyzer_probe_sha256
from src.huiji_rag.provenance import canonical_json_bytes, fingerprint_bm25
from src.rag.chinese_analyzer import ChineseBM25Analyzer
from src.rag.sparse import (
    LocalBM25SparseIndex,
    canonical_child_corpus_sha256,
    legacy_tokenize,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "bm25_shadow"
RECORDS_PATH = FIXTURE_ROOT / "records.v1.json"
QUERIES_PATH = FIXTURE_ROOT / "queries.v1.json"
REPORT_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "reports"
    / "2026-07-29-rag-thread-b-bm25-shadow-comparison.md"
)
REQUIRED_CLASSIFICATIONS = {
    "improvement",
    "oov_bigram_recovery",
    "no_improvement",
    "ranking_change",
    "technical_non_regression",
    "multi_segment",
    "zero_result",
    "punctuation",
}
TECHNICAL_KINDS = {
    "english",
    "numeric",
    "internal_id",
    "filename",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_fixture(path: Path, schema_version: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == schema_version
    return payload


def _ordered_ids_sha256(records: list[dict]) -> str:
    values = sorted(str(record["child_id"]) for record in records)
    return _sha256("".join(f"{value}\n" for value in values).encode("utf-8"))


def _result_rows(results: list[dict]) -> list[dict]:
    return [
        {
            "id": str(result["child_id"]),
            "rank": int(result["bm25_rank"]),
            "score": float(result["bm25_score"]),
        }
        for result in results
    ]


def _classification_passes(
    query: dict,
    legacy_rows: list[dict],
    chinese_rows: list[dict],
) -> bool:
    expected = query["classification"]
    target = query.get("target_id")
    legacy_ids = [row["id"] for row in legacy_rows]
    chinese_ids = [row["id"] for row in chinese_rows]
    if expected in {"improvement", "oov_bigram_recovery"}:
        return bool(chinese_ids) and chinese_ids[0] == target and (
            not legacy_ids or legacy_ids[0] != target
        )
    if expected == "no_improvement":
        return legacy_ids == chinese_ids and bool(chinese_ids) and chinese_ids[0] == target
    if expected == "ranking_change":
        return legacy_ids != chinese_ids and bool(chinese_ids) and chinese_ids[0] == target
    if expected == "technical_non_regression":
        return (
            bool(legacy_ids)
            and bool(chinese_ids)
            and legacy_ids[0] == target
            and chinese_ids[0] == target
        )
    if expected == "multi_segment":
        return bool(chinese_ids) and chinese_ids[0] == target
    if expected in {"zero_result", "punctuation"}:
        return legacy_rows == chinese_rows == []
    return False


def _build_shadow_evidence(tmp_path: Path) -> dict:
    records_fixture = _load_fixture(RECORDS_PATH, "rag.bm25-shadow-records/v1")
    queries_fixture = _load_fixture(QUERIES_PATH, "rag.bm25-shadow-queries/v1")
    records = [dict(record) for record in records_fixture["records"]]
    queries = [dict(query) for query in queries_fixture["queries"]]
    analyzer = ChineseBM25Analyzer()

    legacy_path = tmp_path / "legacy.records-only.json"
    legacy_payload = {
        "records": [
            {"id": str(record["child_id"]), **record}
            for record in records
        ]
    }
    legacy_path.write_bytes(canonical_json_bytes(legacy_payload))
    legacy_build_started = perf_counter()
    legacy_index = LocalBM25SparseIndex.load(legacy_path)
    legacy_build_seconds = perf_counter() - legacy_build_started

    local_path = tmp_path / "chinese.local.v2.json"
    chinese_build_started = perf_counter()
    chinese_memory = LocalBM25SparseIndex(analyzer=analyzer)
    chinese_memory.build(records)
    chinese_memory.save(local_path)
    chinese_index = LocalBM25SparseIndex.load(local_path)
    chinese_build_seconds = perf_counter() - chinese_build_started
    local_payload = json.loads(local_path.read_text(encoding="utf-8"))

    semantic_sha256 = canonical_child_corpus_sha256(records)
    child_payload = {
        "schema_version": "huiji.bm25-index/v3",
        "record_kind": "child",
        "analyzer": local_payload["analyzer"],
        "bm25": local_payload["bm25"],
        "id_field": "child_id",
        "row_count": len(records),
        "ordered_ids_sha256": _ordered_ids_sha256(records),
        "semantic_corpus_sha256": semantic_sha256,
        "analyzer_fingerprint_sha256": analyzer.identity.fingerprint_sha256,
        "analyzer_probe_sha256": _analyzer_probe_sha256(analyzer),
        "records": records,
    }
    child_path = tmp_path / "chinese.child.v3.json"
    child_path.write_bytes(canonical_json_bytes(child_payload))
    child_index = LocalBM25SparseIndex.load(child_path)
    assert child_index.doc_terms == chinese_index.doc_terms
    assert child_index.analyzer.identity == chinese_index.analyzer.identity

    query_evidence = []
    query_timings: dict[str, dict[str, float]] = {}
    hard_gates: dict[str, bool] = {}
    for query in queries:
        segments = query.get("segments")
        query_text = (
            " ".join(str(segment) for segment in segments)
            if segments is not None
            else str(query["text"])
        )
        legacy_tokens = [
            token
            for segment in (segments or (query_text,))
            for token in legacy_tokenize(str(segment))
        ]
        chinese_tokens = (
            analyzer.analyze_segments(segments)
            if segments is not None
            else analyzer.analyze(query_text)
        )
        legacy_started = perf_counter()
        legacy_rows = _result_rows(
            legacy_index.search(query_text, top_k=int(query["top_k"]))
        )
        legacy_seconds = perf_counter() - legacy_started
        chinese_started = perf_counter()
        chinese_rows = _result_rows(
            chinese_index.search(query_text, top_k=int(query["top_k"]))
        )
        chinese_seconds = perf_counter() - chinese_started
        classification_passed = _classification_passes(
            query,
            legacy_rows,
            chinese_rows,
        )
        if query.get("hard_gate"):
            hard_gates[str(query["query_id"])] = classification_passed
        query_evidence.append(
            {
                "query_id": query["query_id"],
                "kind": query["kind"],
                "text": query.get("text", ""),
                "segments": segments or [],
                "classification": query["classification"],
                "classification_passed": classification_passed,
                "target_id": query.get("target_id", ""),
                "forbidden_cross_token": query.get("forbidden_cross_token", ""),
                "legacy_tokens": legacy_tokens,
                "chinese_tokens": chinese_tokens,
                "legacy_top_k": legacy_rows,
                "chinese_top_k": chinese_rows,
            }
        )
        query_timings[str(query["query_id"])] = {
            "legacy_seconds": legacy_seconds,
            "chinese_seconds": chinese_seconds,
        }

    document_tokens = [
        {
            "id": record["child_id"],
            "legacy_tokens": legacy_tokenize(record["search_text"]),
            "chinese_tokens": analyzer.analyze(record["search_text"]),
        }
        for record in records
    ]
    legacy_counts = [len(row["legacy_tokens"]) for row in document_tokens]
    chinese_counts = [len(row["chinese_tokens"]) for row in document_tokens]
    legacy_total = sum(legacy_counts)
    chinese_total = sum(chinese_counts)

    legacy_provenance = fingerprint_bm25(
        legacy_path,
        project_root=tmp_path,
        source_rows=records,
        source_id_field="child_id",
    )
    chinese_provenance = fingerprint_bm25(
        child_path,
        project_root=tmp_path,
        source_rows=records,
        source_id_field="child_id",
    )

    deterministic = {
        "schema_version": "rag.bm25-shadow-evidence/v1",
        "shadow_only": True,
        "activated": False,
        "fixture_identity": {
            "records_sha256": _sha256(RECORDS_PATH.read_bytes()),
            "queries_sha256": _sha256(QUERIES_PATH.read_bytes()),
            "record_count": len(records),
            "query_count": len(queries),
        },
        "analyzer_identity": analyzer.identity.to_dict(),
        "payloads": {
            "semantic_corpus_sha256": semantic_sha256,
            "legacy_records_only_sha256": _sha256(legacy_path.read_bytes()),
            "legacy_records_only_bytes": legacy_path.stat().st_size,
            "chinese_local_v2_sha256": _sha256(local_path.read_bytes()),
            "chinese_local_v2_bytes": local_path.stat().st_size,
            "chinese_child_v3_sha256": _sha256(child_path.read_bytes()),
            "chinese_child_v3_bytes": child_path.stat().st_size,
        },
        "provenance": {
            "legacy_payload_schema": legacy_provenance.payload_schema,
            "legacy_analyzer_schema": legacy_provenance.analyzer_schema,
            "legacy_semantic_sha256": legacy_provenance.semantic_sha256,
            "legacy_payload_sha256": legacy_provenance.sha256,
            "chinese_payload_schema": chinese_provenance.payload_schema,
            "chinese_analyzer_schema": chinese_provenance.analyzer_schema,
            "chinese_analyzer_fingerprint_sha256": (
                chinese_provenance.analyzer_fingerprint_sha256
            ),
            "chinese_semantic_sha256": chinese_provenance.semantic_sha256,
            "chinese_payload_sha256": chinese_provenance.sha256,
        },
        "document_tokens": document_tokens,
        "token_distribution": {
            "legacy_counts": legacy_counts,
            "chinese_counts": chinese_counts,
            "legacy_total": legacy_total,
            "chinese_total": chinese_total,
            "expansion_ratio": chinese_total / legacy_total,
        },
        "queries": query_evidence,
        "hard_gates": hard_gates,
        "commands": [
            (
                "D:\\Anaconda32024\\envs\\1999wiki\\python.exe -m pytest -q "
                "tests/test_chinese_bm25_shadow.py"
            ),
            (
                "D:\\Anaconda32024\\envs\\1999wiki\\python.exe -m pytest -q "
                "tests/test_chinese_bm25_analyzer.py tests/test_sparse_bm25.py "
                "tests/test_chinese_bm25_shadow.py tests/test_huiji_corpus_artifacts.py "
                "tests/test_huiji_provenance.py tests/test_runtime_requirements.py "
                "tests/test_backend_provenance_gate.py tests/test_retriever.py "
                "tests/test_hybrid_retriever.py "
                "--basetemp=.tmp/rag-b-site/.pytest-b5-full"
            ),
        ],
        "results": {
            "shadow_test": "passed",
            "production_activation": "not_run",
        },
        "uncovered_risks": [
            "Shadow fixture is intentionally small and not a production traffic distribution.",
            "Timing samples are descriptive and are not production SLA evidence.",
            "Jieba dictionary behavior outside approved fixture vocabulary remains unbenchmarked.",
        ],
    }
    return {
        "deterministic": deterministic,
        "timings": {
            "descriptive_only": True,
            "legacy_build_seconds": legacy_build_seconds,
            "chinese_build_seconds": chinese_build_seconds,
            "query_samples": query_timings,
        },
    }


def _report_payload() -> dict:
    text = REPORT_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- shadow-result-json\n(.*?)\nshadow-result-json -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_shadow_fixture_contract_covers_all_required_outcomes() -> None:
    records = _load_fixture(RECORDS_PATH, "rag.bm25-shadow-records/v1")
    queries = _load_fixture(QUERIES_PATH, "rag.bm25-shadow-queries/v1")

    assert len(records["records"]) == len(
        {record["child_id"] for record in records["records"]}
    )
    assert REQUIRED_CLASSIFICATIONS == {
        query["classification"] for query in queries["queries"]
    }
    assert TECHNICAL_KINDS.issubset(
        {query["kind"] for query in queries["queries"]}
    )
    assert sum(query["classification"] == "improvement" for query in queries["queries"]) == 2
    assert sum(query["classification"] == "oov_bigram_recovery" for query in queries["queries"]) == 1


def test_shadow_comparison_reloads_payloads_and_passes_hard_gates(tmp_path: Path) -> None:
    result = _build_shadow_evidence(tmp_path)
    deterministic = result["deterministic"]
    query_rows = deterministic["queries"]

    assert all(row["classification_passed"] for row in query_rows)
    assert deterministic["hard_gates"]
    assert all(deterministic["hard_gates"].values())
    assert deterministic["shadow_only"] is True
    assert deterministic["activated"] is False
    assert (
        deterministic["provenance"]["legacy_semantic_sha256"]
        == deterministic["provenance"]["chinese_semantic_sha256"]
    )
    assert (
        deterministic["provenance"]["legacy_payload_sha256"]
        != deterministic["provenance"]["chinese_payload_sha256"]
    )
    assert (
        deterministic["provenance"]["legacy_analyzer_schema"]
        == "legacy-regex/v1"
    )
    assert (
        deterministic["provenance"]["chinese_analyzer_schema"]
        == "rag.bm25-analyzer/v1"
    )
    assert deterministic["token_distribution"]["expansion_ratio"] > 1
    segment_row = next(row for row in query_rows if row["kind"] == "multi_segment")
    assert segment_row["forbidden_cross_token"] not in segment_row["chinese_tokens"]


def test_report_matches_deterministic_shadow_evidence(tmp_path: Path) -> None:
    computed = _build_shadow_evidence(tmp_path)
    report = _report_payload()
    deterministic = computed["deterministic"]

    assert report["deterministic_sha256"] == _sha256(
        canonical_json_bytes(deterministic)
    )
    assert report["queries_sha256"] == _sha256(
        canonical_json_bytes(deterministic["queries"])
    )
    assert report["document_tokens_sha256"] == _sha256(
        canonical_json_bytes(deterministic["document_tokens"])
    )
    for key in (
        "fixture_identity",
        "analyzer_identity",
        "payloads",
        "provenance",
        "token_distribution",
        "hard_gates",
        "commands",
        "results",
        "uncovered_risks",
    ):
        assert report[key] == deterministic[key]
    assert report["shadow_only"] is True
    assert report["activated"] is False
    assert report["timings"]["descriptive_only"] is True
    assert report["timings"]["legacy_build_seconds"] >= 0
    assert report["timings"]["chinese_build_seconds"] >= 0
    query_samples = report["timings"]["query_samples"]
    assert set(query_samples) == {
        query["query_id"] for query in deterministic["queries"]
    }
    for sample in query_samples.values():
        assert set(sample) == {"legacy_seconds", "chinese_seconds"}
        for elapsed_seconds in sample.values():
            assert isinstance(elapsed_seconds, (int, float))
            assert not isinstance(elapsed_seconds, bool)
            assert math.isfinite(elapsed_seconds)
            assert elapsed_seconds >= 0
