import json
import math
from collections import Counter
from copy import deepcopy

import pytest

import src.rag.sparse as sparse_module
from src.rag.chinese_analyzer import ChineseBM25Analyzer
from src.rag.sparse import (
    LegacyRegexAnalyzer,
    LocalBM25SparseIndex,
    canonical_child_corpus_sha256,
    legacy_tokenize,
    tokenize,
)


SEMANTIC_CHILD = {
    "child_id": "char:1/profile:1",
    "parent_id": "char:1/profile",
    "text": "Profile text.",
    "search_text": "Regulus Profile text.",
    "entity_id": "1",
    "entity_name": "Regulus",
    "entity_type": "character",
    "category": "character",
    "section_kind": "profile",
    "title": "Profile",
    "depth_level": 3,
    "media_policy": "auto",
    "ancestor_ids": ["char:1", "char:1/profile"],
    "quality_flags": ["verified"],
    "route_tags": ["profile"],
    "chunk_index": 0,
}


def test_bm25_prefers_exact_name_and_filename_terms():
    records = [
        {"id": "char:3041/skill:30410111", "search_text": "Matilda Genius Exercise Skill-30410111"},
        {"id": "char:3074/skill:30740111", "search_text": "Ezra Shell Care Skill-30740111"},
        {"id": "common:box", "search_text": "000-box-construction common background material"},
    ]
    index = LocalBM25SparseIndex()
    index.build(records)

    results = index.search("Matilda Skill-30410111", top_k=3)

    assert results[0]["id"] == "char:3041/skill:30410111"
    assert results[-1]["id"] == "common:box"


def test_legacy_tokenize_preserves_exact_compatibility_behavior():
    assert legacy_tokenize("Matilda Skill-30410111 000_box 中文词") == [
        "matilda",
        "skill-30410111",
        "000_box",
        "中文词",
    ]
    assert tokenize is legacy_tokenize


def test_default_index_uses_frozen_legacy_analyzer():
    index = LocalBM25SparseIndex()

    assert isinstance(index.analyzer, LegacyRegexAnalyzer)
    assert index.analyzer.identity == "legacy-regex/v1"


class _FalseyAnalyzer:
    identity = "test-falsey/v1"

    def __bool__(self):
        return False

    def analyze(self, text):
        return ["custom"]


def test_only_none_selects_default_legacy_analyzer():
    analyzer = _FalseyAnalyzer()

    assert LocalBM25SparseIndex(analyzer=analyzer).analyzer is analyzer


@pytest.mark.parametrize("k1", (0, -1, math.nan, math.inf, -math.inf, True, "1.5"))
def test_bm25_rejects_invalid_k1(k1):
    with pytest.raises((TypeError, ValueError)):
        LocalBM25SparseIndex(k1=k1)


@pytest.mark.parametrize("b", (-0.1, 1.1, math.nan, math.inf, -math.inf, True, "0.75"))
def test_bm25_rejects_invalid_b(b):
    with pytest.raises((TypeError, ValueError)):
        LocalBM25SparseIndex(b=b)


class _FailingAnalyzer:
    identity = "test-failing/v1"

    def __init__(self):
        self.fail = False

    def analyze(self, text):
        if self.fail:
            raise RuntimeError("intentional analyzer failure")
        return legacy_tokenize(text)


def test_failed_build_preserves_previous_index_state():
    analyzer = _FailingAnalyzer()
    index = LocalBM25SparseIndex(analyzer=analyzer)
    index.build([{"id": "old", "search_text": "Matilda"}])
    before_records = list(index.records)
    before_doc_terms = [Counter(terms) for terms in index.doc_terms]
    before_df = Counter(index.df)
    before_avgdl = index.avgdl
    analyzer.fail = True

    with pytest.raises(RuntimeError, match="intentional analyzer failure"):
        index.build([{"id": "new", "search_text": "Sonetto"}])

    assert index.records == before_records
    assert index.doc_terms == before_doc_terms
    assert index.df == before_df
    assert index.avgdl == before_avgdl


def test_empty_and_tokenless_queries_return_no_results():
    index = LocalBM25SparseIndex()
    index.build([{"id": "rain", "search_text": "雨"}])

    assert index.search("") == []
    assert index.search("？！…") == []
    assert LocalBM25SparseIndex().search("Matilda") == []


def test_single_han_character_remains_searchable_with_legacy_analyzer():
    index = LocalBM25SparseIndex()
    index.build([{"id": "rain", "search_text": "雨"}])

    assert index.search("雨", top_k=1)[0]["id"] == "rain"


def test_positive_ties_keep_record_order_and_zero_fill_is_stable():
    index = LocalBM25SparseIndex()
    index.build(
        [
            {"id": "first", "search_text": "shared"},
            {"id": "second", "search_text": "shared"},
            {"id": "fallback", "search_text": "other"},
        ]
    )

    results = index.search("shared", top_k=3)

    assert [result["id"] for result in results] == ["first", "second", "fallback"]
    assert results[0]["bm25_score"] == results[1]["bm25_score"]
    assert results[2]["bm25_score"] == 0.0


@pytest.fixture
def chinese_bm25_fixture():
    analyzer = ChineseBM25Analyzer()
    records = [
        {
            "id": "char:3041/skill:30410111",
            "search_text": "十四行诗 技能 神秘学家 Skill-30410111",
            "text": "十四行诗的技能介绍",
        },
        {
            "id": "char:3074/profile",
            "search_text": "槲寄生 基础资料 神秘学家",
            "text": "槲寄生的基础资料",
        },
        {
            "id": "event:star-voyage",
            "search_text": "星海远航 限时活动",
            "text": "星海远航",
        },
        {
            "id": "weather:rain",
            "search_text": "雨",
            "text": "雨",
        },
        {
            "id": "media:banner",
            "search_text": "Banner_今夜星光灿烂.png Data:Story/304502 000-box-construction",
            "text": "technical identifiers",
        },
    ]
    index = LocalBM25SparseIndex(analyzer=analyzer)
    index.build(records)
    return analyzer, index, records


def test_chinese_natural_and_spaced_queries_rank_same_skill_first(chinese_bm25_fixture):
    _, index, _ = chinese_bm25_fixture

    natural = index.search("十四行诗的技能是什么", top_k=3)
    spaced = index.search("十四行诗 技能", top_k=3)

    assert natural[0]["id"] == "char:3041/skill:30410111"
    assert spaced[0]["id"] == natural[0]["id"]


def test_chinese_unknown_word_uses_bigram_fallback(chinese_bm25_fixture):
    _, index, _ = chinese_bm25_fixture

    assert index.search("星海远航", top_k=1)[0]["id"] == "event:star-voyage"


def test_chinese_single_han_and_technical_atoms_remain_searchable(chinese_bm25_fixture):
    _, index, _ = chinese_bm25_fixture

    assert index.search("雨", top_k=1)[0]["id"] == "weather:rain"
    for query in (
        "Skill-30410111",
        "Data:Story/304502",
        "Banner_今夜星光灿烂.png",
        "000-box-construction",
    ):
        assert index.search(query, top_k=1)[0]["id"] in {
            "char:3041/skill:30410111",
            "media:banner",
        }


def test_build_and_search_share_exact_analyzer_and_preserve_records(chinese_bm25_fixture):
    analyzer, index, records = chinese_bm25_fixture
    expected_records = [dict(record) for record in records]

    index.search("十四行诗", top_k=1)

    assert index.analyzer is analyzer
    assert index.analyzer.identity is analyzer.identity
    assert index.records == expected_records


def test_chinese_fixture_exercises_multisegment_api_without_crossing_boundaries(
    chinese_bm25_fixture,
):
    analyzer, index, _ = chinese_bm25_fixture
    segments = ("槲寄生", "", "基础资料", "Skill-30410111")

    assert index.analyzer is analyzer
    assert analyzer.analyze_segments(segments) == [
        token
        for segment in segments
        for token in analyzer.analyze(segment)
    ]
    assert "生基" not in analyzer.analyze_segments(segments)


def test_bm25_save_load_roundtrip(tmp_path):
    path = tmp_path / "child_bm25.json"
    index = LocalBM25SparseIndex()
    index.build([{"id": "portrait:3041", "search_text": "Matilda portrait"}])

    index.save(path)
    loaded = LocalBM25SparseIndex.load(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "rag.local-bm25/v2"
    assert payload["analyzer"] == {"schema_version": "legacy-regex/v1"}
    assert loaded.analyzer.identity == "legacy-regex/v1"
    assert loaded.search("Matilda", top_k=1)[0]["id"] == "portrait:3041"


@pytest.mark.parametrize(
    "payload",
    (
        {"records": [{"id": "legacy", "search_text": "槲寄生"}]},
        {
            "schema_version": "huiji.bm25-index/v2",
            "record_kind": "child",
            "records": [{"id": "legacy", "search_text": "槲寄生"}],
        },
        {
            "schema_version": "huiji.media-binding-bm25/v3",
            "record_kind": "media_binding",
            "records": [{"id": "legacy", "search_text": "槲寄生"}],
        },
    ),
)
def test_legacy_payload_schemas_bind_exact_legacy_analyzer(tmp_path, payload):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = LocalBM25SparseIndex.load(path)

    assert loaded.analyzer.identity == "legacy-regex/v1"
    assert loaded.doc_terms == [Counter({"槲寄生": 1})]
    assert loaded.search("寄生") == []


def test_local_v2_roundtrip_preserves_analyzer_terms_parameters_scores_and_order(tmp_path):
    path = tmp_path / "local.json"
    analyzer = ChineseBM25Analyzer(extra_terms=("星海远航",))
    index = LocalBM25SparseIndex(analyzer=analyzer, k1=1.2, b=0.4)
    index.build(
        [
            {"id": "first", "search_text": "星海远航 十四行诗"},
            {"id": "second", "search_text": "十四行诗"},
            {"id": "fallback", "search_text": "槲寄生"},
        ]
    )
    before = index.search("星海远航 十四行诗", top_k=3)

    index.save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    loaded = LocalBM25SparseIndex.load(path)

    assert payload["schema_version"] == "rag.local-bm25/v2"
    assert payload["record_kind"] == "local"
    assert payload["analyzer"] == analyzer.identity.to_dict()
    assert payload["bm25"] == {"k1": 1.2, "b": 0.4}
    assert loaded.analyzer.identity.to_dict() == analyzer.identity.to_dict()
    assert loaded.k1 == 1.2
    assert loaded.b == 0.4
    assert loaded.doc_terms == index.doc_terms
    assert loaded.search("星海远航 十四行诗", top_k=3) == before


@pytest.mark.parametrize(
    ("schema_version", "record_kind"),
    (
        ("huiji.bm25-index/v3", "child"),
        ("huiji.media-binding-bm25/v4", "media_binding"),
    ),
)
def test_new_artifact_schemas_rebuild_embedded_chinese_analyzer(
    tmp_path,
    schema_version,
    record_kind,
):
    analyzer = ChineseBM25Analyzer(extra_terms=("离树庭院",))
    payload = {
        "schema_version": schema_version,
        "record_kind": record_kind,
        "analyzer": analyzer.identity.to_dict(),
        "bm25": {"k1": 1.1, "b": 0.6},
        "records": [{"id": "target", "search_text": "离树庭院 神秘学家"}],
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = LocalBM25SparseIndex.load(path)

    assert loaded.analyzer.identity.to_dict() == analyzer.identity.to_dict()
    assert loaded.search("离树庭院", top_k=1)[0]["id"] == "target"
    assert (loaded.k1, loaded.b) == (1.1, 0.6)


def _valid_local_payload():
    analyzer = ChineseBM25Analyzer(extra_terms=("严格加载词",))
    return {
        "schema_version": "rag.local-bm25/v2",
        "record_kind": "local",
        "analyzer": analyzer.identity.to_dict(),
        "bm25": {"k1": 1.5, "b": 0.75},
        "records": [{"id": "secret-record", "search_text": "private-query-text"}],
    }


def _without(payload, key):
    changed = deepcopy(payload)
    changed.pop(key)
    return changed


def _with_nested(payload, keys, value):
    changed = deepcopy(payload)
    target = changed
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    return changed


@pytest.mark.parametrize(
    "payload_factory",
    (
        lambda payload: _without(payload, "analyzer"),
        lambda payload: _without(payload, "bm25"),
        lambda payload: _with_nested(payload, ("schema_version",), "rag.local-bm25/v99"),
        lambda payload: _with_nested(
            payload, ("analyzer", "segmenter", "name"), "unsupported-segmenter"
        ),
        lambda payload: _with_nested(
            payload, ("analyzer", "config", "merge_rule_version"), "99"
        ),
        lambda payload: _with_nested(payload, ("analyzer", "config_sha256"), "0" * 64),
        lambda payload: _with_nested(payload, ("analyzer", "dictionary_sha256"), "0" * 64),
        lambda payload: _with_nested(payload, ("analyzer", "fingerprint_sha256"), "0" * 64),
        lambda payload: _with_nested(payload, ("bm25", "k1"), math.nan),
        lambda payload: _with_nested(payload, ("bm25", "b"), 2),
    ),
)
def test_new_schema_malformed_metadata_fails_closed_without_record_leakage(
    tmp_path,
    payload_factory,
):
    path = tmp_path / "malformed.json"
    path.write_text(
        json.dumps(payload_factory(_valid_local_payload()), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as error:
        LocalBM25SparseIndex.load(path)

    assert "secret-record" not in str(error.value)
    assert "private-query-text" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    (
        {
            "schema_version": "unknown/v1",
            "records": [{"id": "secret-record", "search_text": "private-query-text"}],
        },
        {
            "records": [{"id": "secret-record", "search_text": "private-query-text"}],
            "analyzer": {"schema_version": "legacy-regex/v1"},
        },
        {
            "schema_version": "rag.local-bm25/v2",
            "records": [{"id": "secret-record", "search_text": "private-query-text"}],
        },
    ),
)
def test_unknown_or_ambiguous_payload_never_falls_back_to_records_only(tmp_path, payload):
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        LocalBM25SparseIndex.load(path)


def test_loader_rejects_analyzer_override_argument(tmp_path):
    path = tmp_path / "local.json"
    index = LocalBM25SparseIndex(analyzer=ChineseBM25Analyzer())
    index.build([{"id": "target", "search_text": "十四行诗"}])
    index.save(path)

    with pytest.raises(TypeError):
        LocalBM25SparseIndex.load(path, analyzer=LegacyRegexAnalyzer())


def test_atomic_save_uses_same_directory_and_preserves_existing_target_on_failure(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "local.json"
    path.write_text("existing-target", encoding="utf-8")
    index = LocalBM25SparseIndex(analyzer=ChineseBM25Analyzer())
    index.build([{"id": "target", "search_text": "十四行诗"}])
    before_files = {item.name for item in tmp_path.iterdir()}

    def fail_replace(source, target):
        assert source.parent == path.parent
        assert target == path
        raise OSError("replace failed")

    monkeypatch.setattr(sparse_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        index.save(path)

    assert path.read_text(encoding="utf-8") == "existing-target"
    assert {item.name for item in tmp_path.iterdir()} == before_files


def test_regenerated_bm25_semantic_corpus_hash_matches(tmp_path):
    before = [
        {
            "child_id": "char:2/voice:1",
            "parent_id": "char:2/voice",
            "entity_id": "2",
            "category": "character",
            "section_kind": "voice",
            "route_tags": ["voice", "character"],
            "text": "Wake up.",
            "search_text": "Matilda Wake up.",
            "media_ids": ["media:sha1:" + "a" * 40],
        },
        {
            "child_id": "char:1/profile:1",
            "parent_id": "char:1/profile",
            "entity_id": "1",
            "category": "character",
            "section_kind": "profile",
            "route_tags": ["profile"],
            "text": "Profile.",
            "search_text": "Regulus Profile.",
            "media_ids": [],
        },
    ]
    regenerated = [
        {**before[1], "media_ids": ["media:sha1:" + "b" * 40], "timestamp": "later"},
        {**before[0], "route_tags": ["character", "voice"], "index_offset": 9},
    ]
    path = tmp_path / "child_bm25.json"
    index = LocalBM25SparseIndex()
    index.build(regenerated)
    index.save(path)

    assert canonical_child_corpus_sha256(before) == canonical_child_corpus_sha256(regenerated)
    assert canonical_child_corpus_sha256(before) == canonical_child_corpus_sha256(
        LocalBM25SparseIndex.load(path).records
    )


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("child_id", "char:1/profile:2"),
        ("parent_id", "char:1/other"),
        ("text", "Changed text."),
        ("search_text", "Changed search text."),
        ("entity_id", "2"),
        ("entity_name", "Changed Name"),
        ("entity_type", "item"),
        ("category", "item"),
        ("section_kind", "dossier"),
        ("title", "Changed title"),
        ("depth_level", 4),
        ("media_policy", "manual"),
        ("ancestor_ids", ["char:other"]),
        ("quality_flags", ["changed"]),
        ("route_tags", ["changed"]),
        ("chunk_index", 1),
    ),
)
def test_child_corpus_hash_changes_for_each_semantic_field(field, changed):
    assert canonical_child_corpus_sha256((SEMANTIC_CHILD,)) != canonical_child_corpus_sha256(
        ({**SEMANTIC_CHILD, field: changed},)
    )


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("media_ids", ["media:sha1:" + "a" * 40]),
        ("timestamp", "later"),
        ("index_offset", 99),
        ("content_hash", "a" * 64),
        ("source_refs", [{"title": "serialization noise"}]),
    ),
)
def test_child_corpus_hash_ignores_media_and_layout_only_fields(field, changed):
    assert canonical_child_corpus_sha256((SEMANTIC_CHILD,)) == canonical_child_corpus_sha256(
        ({**SEMANTIC_CHILD, field: changed},)
    )
