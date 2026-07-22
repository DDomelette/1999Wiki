import pytest

from src.rag.sparse import LocalBM25SparseIndex, canonical_child_corpus_sha256


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


def test_bm25_save_load_roundtrip(tmp_path):
    path = tmp_path / "child_bm25.json"
    index = LocalBM25SparseIndex()
    index.build([{"id": "portrait:3041", "search_text": "Matilda portrait"}])

    index.save(path)
    loaded = LocalBM25SparseIndex.load(path)

    assert loaded.search("Matilda", top_k=1)[0]["id"] == "portrait:3041"


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
