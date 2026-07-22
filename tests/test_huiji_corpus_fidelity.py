from __future__ import annotations

from dataclasses import replace

from src.huiji_rag.build.fidelity import build_fidelity_ledger
from src.huiji_rag.build.media_v3 import LegacyMediaReconciliation
from src.huiji_rag.build.projection import (
    CorpusProjection,
    ProjectionExclusion,
    SemanticChild,
    SemanticRecordLink,
)
from src.huiji_rag.models import ChildBlock, ParentBlock


SHA = "a" * 64


def _fixture(*, duplicate_media: bool = False):
    source_ref = {
        "kind": "data_page",
        "title": "Data:Char/1.json",
        "revid": 1,
        "content_sha256": SHA,
        "json_path": "$.character_data.0",
    }
    candidate_parent = ParentBlock(
        parent_id="char:1/collection",
        entity_id="1",
        entity_name="Alpha",
        entity_aliases=(),
        category="character",
        section_kind="collection",
        title="Alpha / Collection",
        summary_text="Collection text",
        source_refs=(source_ref,),
        child_ids=("char:1/collection/10",),
        content_hash="b" * 64,
    )
    block = ChildBlock(
        child_id="char:1/collection/10",
        parent_id="char:1/collection",
        entity_id="1",
        entity_name="Alpha",
        category="character",
        section_kind="collection",
        title="Collection",
        text="Collection text",
        search_text="Alpha Collection",
        chunk_index=0,
        media_ids=(),
        media_policy="auto",
        source_refs=(source_ref,),
        content_hash="c" * 64,
    )
    child = SemanticChild(
        block=block,
        stable_source_token="10",
        source_token_kind="crawler_stable_id",
        owner_entity_id="character:1",
        owner_page_id="char:1",
    )
    links = (
        SemanticRecordLink(
            record_kind="parent",
            legacy_id="char:1/culture",
            candidate_id="char:1/collection",
            change_kind="corrected_semantics",
            source_title="Data:Char/1.json",
            source_content_sha256=SHA,
            json_path="$.character_data",
            legacy_section="culture",
            candidate_section="collection",
        ),
        SemanticRecordLink(
            record_kind="child",
            legacy_id="char:1/culture:0010",
            candidate_id="char:1/collection/10",
            change_kind="corrected_semantics",
            source_title="Data:Char/1.json",
            source_content_sha256=SHA,
            json_path="$.character_data.0",
            legacy_section="culture",
            candidate_section="collection",
        ),
    )
    exclusion = ProjectionExclusion(
        reason_code="placeholder_name",
        source_title="Data:Char/0.json",
        source_identity="Data:Char/0.json",
        source_content_sha256="d" * 64,
    )
    projection = CorpusProjection(
        parents=(candidate_parent,),
        children=(child,),
        voice_sources=(),
        media_intents=(),
        exclusions=(exclusion,),
        identity_fallbacks=(),
        record_links=links,
    )
    active_parent = {
        **candidate_parent.to_json(),
        "parent_id": "char:1/culture",
        "section_kind": "culture",
        "child_ids": ["char:1/culture:0010"],
    }
    active_child = {
        **block.to_json(),
        "child_id": "char:1/culture:0010",
        "parent_id": "char:1/culture",
        "section_kind": "culture",
    }
    occurrences = [
        {
            "occurrence_id": "active-occurrence:sha256:" + "1" * 64,
            "active_row_sha256": "2" * 64,
            "active_media_id": "media:sha1:" + "3" * 40,
            "active_sha1": "3" * 40,
            "active_parent_id": "char:1/culture",
            "active_child_id": "char:1/culture:0010",
            "candidate_child_id": "char:1/collection/10",
            "resource_id": "resource:sha256:" + "4" * 64,
            "candidate_binding_ids": ["binding:sha256:" + "5" * 64],
            "classification": "preserved_binding",
            "reason_code": "active_occurrence_maps_to_one_v3_binding",
            "candidate_source_refs": [source_ref],
            "local_evidence": {},
        }
    ]
    if duplicate_media:
        occurrences.append(
            {
                **occurrences[0],
                "occurrence_id": "active-occurrence:sha256:" + "6" * 64,
                "active_row_sha256": "7" * 64,
                "candidate_binding_ids": ["binding:sha256:" + "8" * 64],
            }
        )
    legacy = LegacyMediaReconciliation(
        occurrence_rows=tuple(occurrences),
        category_counts={"preserved_binding": len(occurrences)},
        active_occurrence_count=len(occurrences),
        unexplained_binding_loss=0,
    )
    active_media_bm25 = [
        {"media_id": occurrence["active_media_id"], "search_text": "media"}
        for occurrence in occurrences
    ]
    return {
        "projection": projection,
        "active_parents": (active_parent,),
        "active_children": (active_child,),
        "active_excluded": (
            {"source": "Data:Char/0.json", "reason": "placeholder_name"},
        ),
        "legacy": legacy,
        "child_bm25": (active_child,),
        "media_bm25": tuple(active_media_bm25),
    }


def _build(values):
    return build_fidelity_ledger(
        active_parent_rows=values["active_parents"],
        active_child_rows=values["active_children"],
        active_excluded_rows=values["active_excluded"],
        projection=values["projection"],
        legacy_media=values["legacy"],
        active_child_bm25_records=values["child_bm25"],
        active_media_bm25_records=values["media_bm25"],
    )


def test_fidelity_ledger_accepts_only_explicit_rekeys_and_preserves_occurrences() -> None:
    values = _fixture(duplicate_media=True)

    result = _build(values)

    assert result.passed is True
    assert result.unexplained_parent_child_loss == 0
    assert result.unexplained_binding_loss == 0
    media = [row for row in result.ledger_rows if row["record_kind"] == "media_binding"]
    assert len(media) == 2
    assert len({row["active_identity"] for row in media}) == 2
    assert result.build_diff["active_counts"]["media_bindings"] == 2
    corrected = [
        row
        for row in result.ledger_rows
        if row["classification"] == "corrected_semantics"
    ]
    assert {row["record_kind"] for row in corrected} >= {"parent", "child"}


def test_fidelity_ledger_rejects_unapproved_section_correction() -> None:
    values = _fixture()
    bad_link = replace(
        values["projection"].record_links[1], candidate_section="unapproved"
    )
    values["projection"] = replace(
        values["projection"],
        record_links=(values["projection"].record_links[0], bad_link),
    )

    result = _build(values)

    assert result.passed is False
    assert "unapproved_section_correction:char:1/culture:0010" in result.blockers


def test_fidelity_ledger_accepts_legacy_items_parent_for_culture_dossier() -> None:
    values = _fixture()
    parent_link = replace(
        values["projection"].record_links[0],
        legacy_id="char:1/items",
        legacy_section="items",
        candidate_section="culture_dossier",
    )
    child_link = replace(
        values["projection"].record_links[1],
        legacy_id="char:1/item:0010",
        legacy_section="item",
        candidate_section="culture_dossier",
    )
    values["projection"] = replace(
        values["projection"], record_links=(parent_link, child_link)
    )
    values["active_parents"] = (
        {
            **values["active_parents"][0],
            "parent_id": "char:1/items",
            "section_kind": "items",
            "child_ids": ["char:1/item:0010"],
        },
    )
    active_child = {
        **values["active_children"][0],
        "child_id": "char:1/item:0010",
        "parent_id": "char:1/items",
        "section_kind": "item",
    }
    values["active_children"] = (active_child,)
    values["child_bm25"] = (active_child,)

    result = _build(values)

    assert result.passed is True
    assert ["items", "culture_dossier"] in result.build_diff[
        "allowed_section_corrections"
    ]


def test_fidelity_ledger_blocks_missing_candidate_and_bm25_sequence_drift() -> None:
    values = _fixture()
    values["projection"] = replace(values["projection"], children=())
    values["child_bm25"] = ({**values["child_bm25"][0], "child_id": "wrong"},)

    result = _build(values)

    assert result.unexplained_parent_child_loss == 1
    assert any(blocker.startswith("unexplained_child_missing:") for blocker in result.blockers)
    assert "active_child_bm25_sequence_mismatch:0" in result.blockers
