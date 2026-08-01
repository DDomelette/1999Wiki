from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from src.huiji_rag.build.fidelity import build_fidelity_ledger
from src.huiji_rag.build.media_v3 import LegacyMediaReconciliation
from src.huiji_rag.build.projection import (
    CorpusProjection,
    ProjectionExclusion,
    SemanticChild,
    SemanticRecordLink,
    project_crawler_semantics,
)
from src.huiji_rag.models import ChildBlock, ParentBlock


SHA = "a" * 64
STORY_SHA = "7" * 64


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


def _story_fixture(*, tokens: tuple[str, ...] = ("step-z", "step-a")):
    source_title = "Data:Story/9001.json"
    candidate_parent_id = "story:9001/story"
    legacy_parent_id = "story:legacy-9001/profile"
    legacy_child_id = "story:legacy-9001:0000"
    parent_ref = {
        "kind": "data_page",
        "title": source_title,
        "revid": 9,
        "content_sha256": STORY_SHA,
        "json_path": "$",
    }
    legacy_ref = {
        "source_kind": "crawler_data_page",
        "source_title": source_title,
        "source_row_id": "$",
        "source_content_sha256": STORY_SHA,
    }
    candidate_ids = tuple(f"{candidate_parent_id}/{token}" for token in tokens)
    parent = ParentBlock(
        parent_id=candidate_parent_id,
        entity_id="9001",
        entity_name="Migration fixture",
        entity_aliases=(),
        category="story",
        section_kind="story",
        title="Migration fixture",
        summary_text="Story line",
        source_refs=(parent_ref,),
        child_ids=candidate_ids,
        content_hash="8" * 64,
        entity_type="story",
    )
    children = tuple(
        SemanticChild(
            block=ChildBlock(
                child_id=candidate_id,
                parent_id=candidate_parent_id,
                entity_id="9001",
                entity_name="Migration fixture",
                category="story",
                section_kind="story",
                title="Migration fixture",
                text=f"Line {index}",
                search_text=f"Migration fixture line {index}",
                chunk_index=index,
                media_ids=(),
                media_policy="text_only",
                source_refs=(
                    {
                        **parent_ref,
                        "json_path": f"$.steps.{index}",
                    },
                ),
                content_hash=str(index + 1) * 64,
                entity_type="story",
                ancestor_ids=("story:9001", candidate_parent_id),
            ),
            stable_source_token=token,
            source_token_kind="stable_step_id",
            owner_entity_id="story:9001",
            owner_page_id="story:9001",
            source_fields={"json_path": f"$.steps.{index}"},
        )
        for index, (token, candidate_id) in enumerate(zip(tokens, candidate_ids))
    )
    links = (
        SemanticRecordLink(
            record_kind="parent",
            legacy_id=legacy_parent_id,
            candidate_id=candidate_parent_id,
            change_kind="corrected_semantics",
            source_title=source_title,
            source_content_sha256=STORY_SHA,
            json_path="$",
            legacy_section="profile",
            candidate_section="story",
        ),
        *(
            SemanticRecordLink(
                record_kind="child",
                legacy_id=legacy_child_id,
                candidate_id=child.block.child_id,
                change_kind="corrected_semantics",
                source_title=source_title,
                source_content_sha256=STORY_SHA,
                json_path=str(child.source_fields["json_path"]),
                legacy_section="profile",
                candidate_section="story",
            )
            for child in reversed(children)
        ),
    )
    projection = CorpusProjection(
        parents=(parent,),
        children=children,
        voice_sources=(),
        media_intents=(),
        exclusions=(),
        identity_fallbacks=(),
        record_links=links,
    )
    active_parent = {
        **parent.to_json(),
        "parent_id": legacy_parent_id,
        "entity_id": "legacy-9001",
        "section_kind": "profile",
        "source_refs": [legacy_ref],
        "child_ids": [legacy_child_id],
    }
    active_child = {
        **children[0].block.to_json(),
        "child_id": legacy_child_id,
        "parent_id": legacy_parent_id,
        "entity_id": "legacy-9001",
        "section_kind": "profile",
        "source_refs": [legacy_ref],
    }
    return {
        "projection": projection,
        "active_parents": (active_parent,),
        "active_children": (active_child,),
        "active_excluded": (),
        "legacy": LegacyMediaReconciliation(
            occurrence_rows=(),
            category_counts={},
            active_occurrence_count=0,
            unexplained_binding_loss=0,
        ),
        "child_bm25": (),
        "media_bm25": (),
    }


def _story_exclusion_fixture(
    payload: dict[str, object],
    *,
    story_id: str = "8200",
):
    source_title = f"Data:Story/{story_id}.json"
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    source_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    revid = 91
    source_row = {
        "title": source_title,
        "revid": revid,
        "content": content,
        "content_sha256": source_sha256,
    }
    projection = project_crawler_semantics([source_row])
    legacy_owner = hashlib.sha1(source_title.encode("utf-8")).hexdigest()[:12]
    legacy_parent_id = f"story:{legacy_owner}/profile"
    legacy_child_id = f"story:{legacy_owner}:0000"
    source_ref = {
        "source_kind": "crawler_data_page",
        "source_title": source_title,
        "source_row_id": f"{source_title}:{revid}:$",
        "source_content_sha256": source_sha256,
        "revid": revid,
        "json_path": "$",
    }
    active_parent = {
        "parent_id": legacy_parent_id,
        "entity_id": legacy_owner,
        "entity_name": source_title,
        "entity_type": "story",
        "category": "story",
        "section_kind": "profile",
        "source_refs": [source_ref],
        "child_ids": [legacy_child_id],
    }
    active_child = {
        "child_id": legacy_child_id,
        "parent_id": legacy_parent_id,
        "entity_id": legacy_owner,
        "entity_name": source_title,
        "entity_type": "story",
        "category": "story",
        "section_kind": "profile",
        "source_refs": [source_ref],
    }
    return {
        "projection": projection,
        "active_parents": (active_parent,),
        "active_children": (active_child,),
        "active_excluded": (),
        "legacy": LegacyMediaReconciliation(
            occurrence_rows=(),
            category_counts={},
            active_occurrence_count=0,
            unexplained_binding_loss=0,
        ),
        "child_bm25": (),
        "media_bm25": (),
    }


def _active_story_rows(result):
    return tuple(
        row
        for row in result.ledger_rows
        if row["record_kind"] in {"parent", "child"} and row["active_identity"]
    )


def _assert_story_exclusion_migration_rejected(values) -> None:
    try:
        result = _build(values)
    except ValueError:
        return
    assert result.passed is False
    assert all(
        row["classification"] != "corrected_semantics"
        for row in _active_story_rows(result)
    )


def _build_story_or_fail(values):
    try:
        return _build(values)
    except ValueError as exc:
        pytest.fail(f"Story expansion must be reconciled as one source group: {exc}")


def _assert_story_group_rejected(values) -> None:
    try:
        result = _build(values)
    except ValueError:
        return
    assert result.passed is False
    assert result.blockers


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


def test_non_story_child_ledger_preserves_public_payload_hash_and_bm25_shape() -> None:
    values = _fixture()

    result = _build(values)
    child_row = next(
        row
        for row in result.ledger_rows
        if row["record_kind"] == "child"
        and row["active_identity"] == "char:1/culture:0010"
    )
    child_bm25_row = next(
        row
        for row in result.ledger_rows
        if row["record_kind"] == "child_bm25"
    )

    assert (
        child_row["candidate_sha256"]
        == "ddb2c3c2613779cc4c0ef347303f36d452adb4d30ff077624f60e639abeccbcb"
    )
    assert child_row["details"] == {
        "payload_changed": True,
        "legacy_section": "culture",
        "candidate_section": "collection",
    }
    assert child_bm25_row["candidate_sha256"] == ""


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


def test_fidelity_exclusion_ledger_uses_source_stable_occurrence_identity() -> None:
    values = _fixture()
    exclusions = (
        ProjectionExclusion(
            reason_code="unsupported_template_media",
            source_title="Page",
            source_identity="occurrence-" + "1" * 64,
            source_content_sha256="e" * 64,
            details={"pageid": 7, "revid": 11, "char_start": 10, "char_end": 20},
        ),
        ProjectionExclusion(
            reason_code="unsupported_template_media",
            source_title="Page",
            source_identity="occurrence-" + "2" * 64,
            source_content_sha256="e" * 64,
            details={"pageid": 7, "revid": 11, "char_start": 30, "char_end": 40},
        ),
    )
    values["projection"] = replace(values["projection"], exclusions=exclusions)
    values["active_excluded"] = ()

    first = _build(values)
    second = _build(values)
    first_rows = [
        row for row in first.ledger_rows if row["record_kind"] == "excluded"
    ]
    second_rows = [
        row for row in second.ledger_rows if row["record_kind"] == "excluded"
    ]

    assert len(first_rows) == 2
    assert len({row["ledger_id"] for row in first_rows}) == 2
    assert [row["ledger_id"] for row in first_rows] == [
        row["ledger_id"] for row in second_rows
    ]
    assert {
        row["candidate_identities"][0].rsplit(":", 1)[-1] for row in first_rows
    } == {item.source_identity for item in exclusions}


def test_fidelity_exclusion_ledger_deduplicates_exact_duplicate_occurrence() -> None:
    values = _fixture()
    exclusion = ProjectionExclusion(
        reason_code="unsupported_template_media",
        source_title="Page",
        source_identity="occurrence-" + "1" * 64,
        source_content_sha256="e" * 64,
        details={"pageid": 7, "revid": 11, "char_start": 10, "char_end": 20},
    )
    values["projection"] = replace(
        values["projection"], exclusions=(exclusion, exclusion)
    )
    values["active_excluded"] = ()

    first = _build(values)
    second = _build(values)
    first_rows = [
        row for row in first.ledger_rows if row["record_kind"] == "excluded"
    ]
    second_rows = [
        row for row in second.ledger_rows if row["record_kind"] == "excluded"
    ]

    assert len(first_rows) == 1
    assert [row["ledger_id"] for row in first_rows] == [
        row["ledger_id"] for row in second_rows
    ]


def test_fidelity_exclusion_ledger_rejects_conflicting_duplicate_identity() -> None:
    values = _fixture()
    first = ProjectionExclusion(
        reason_code="unsupported_template_media",
        source_title="Page",
        source_identity="occurrence-" + "1" * 64,
        source_content_sha256="e" * 64,
        details={"pageid": 7, "revid": 11, "char_start": 10, "char_end": 20},
    )
    conflicting = replace(first, details={**first.details, "char_end": 21})
    values["projection"] = replace(
        values["projection"], exclusions=(first, conflicting)
    )
    values["active_excluded"] = ()

    with pytest.raises(ValueError, match="conflicting candidate exclusion identity"):
        _build(values)


def test_fidelity_ledger_blocks_missing_candidate_and_bm25_sequence_drift() -> None:
    values = _fixture()
    values["projection"] = replace(values["projection"], children=())
    values["child_bm25"] = ({**values["child_bm25"][0], "child_id": "wrong"},)

    result = _build(values)

    assert result.unexplained_parent_child_loss == 1
    assert any(blocker.startswith("unexplained_child_missing:") for blocker in result.blockers)
    assert "active_child_bm25_sequence_mismatch:0" in result.blockers


def test_story_child_expansion_consumes_all_candidates_in_one_ledger_row() -> None:
    values = _story_fixture(tokens=("step-z", "step-a"))

    first = _build_story_or_fail(values)
    second = _build_story_or_fail(values)
    child_rows = [
        row
        for row in first.ledger_rows
        if row["record_kind"] == "child" and row["active_identity"]
    ]

    assert first.passed is True
    assert len(child_rows) == 1
    assert child_rows[0]["classification"] == "corrected_semantics"
    assert child_rows[0]["candidate_identities"] == [
        "story:9001/story/step-a",
        "story:9001/story/step-z",
    ]
    assert child_rows[0] == next(
        row
        for row in second.ledger_rows
        if row["record_kind"] == "child" and row["active_identity"]
    )
    assert not any(
        row["record_kind"] == "child"
        and row["classification"] in {"new_source_record", "unexplained_addition"}
        for row in first.ledger_rows
    )


def test_story_child_expansion_rejects_partial_or_mixed_groups() -> None:
    one_child = _story_fixture(tokens=("step-only",))
    one_child_result = _build_story_or_fail(one_child)
    one_child_row = next(
        row
        for row in one_child_result.ledger_rows
        if row["record_kind"] == "child" and row["active_identity"]
    )
    assert one_child_result.passed is True
    assert one_child_row["candidate_identities"] == [
        "story:9001/story/step-only"
    ]

    partial = _story_fixture()
    partial["projection"] = replace(
        partial["projection"],
        record_links=partial["projection"].record_links[:-1],
    )
    _assert_story_group_rejected(partial)

    mixed_hash = _story_fixture()
    mixed_links = list(mixed_hash["projection"].record_links)
    mixed_links[-1] = replace(mixed_links[-1], source_content_sha256="9" * 64)
    mixed_hash["projection"] = replace(
        mixed_hash["projection"], record_links=tuple(mixed_links)
    )
    _assert_story_group_rejected(mixed_hash)

    wrong_owner = _story_fixture()
    wrong_children = list(wrong_owner["projection"].children)
    wrong_children[-1] = replace(
        wrong_children[-1], owner_entity_id="story:wrong"
    )
    wrong_owner["projection"] = replace(
        wrong_owner["projection"], children=tuple(wrong_children)
    )
    _assert_story_group_rejected(wrong_owner)

    duplicate_target = _story_fixture()
    duplicate_target["projection"] = replace(
        duplicate_target["projection"],
        record_links=(
            *duplicate_target["projection"].record_links,
            duplicate_target["projection"].record_links[-1],
        ),
    )
    _assert_story_group_rejected(duplicate_target)

    incomplete_evidence = _story_fixture()
    incomplete_links = list(incomplete_evidence["projection"].record_links)
    incomplete_links[-1] = replace(
        incomplete_links[-1], source_content_sha256="", json_path=""
    )
    incomplete_evidence["projection"] = replace(
        incomplete_evidence["projection"], record_links=tuple(incomplete_links)
    )
    _assert_story_group_rejected(incomplete_evidence)

    unmatched = _story_fixture(tokens=("step-only",))
    unmatched_candidate = unmatched["projection"].children[0]
    unrelated_ref = {
        **unmatched_candidate.block.source_refs[0],
        "title": "Data:Story/other.json",
        "content_sha256": "6" * 64,
    }
    unrelated_block = replace(
        unmatched_candidate.block,
        child_id="story:other/story/step-only",
        parent_id="story:other/story",
        entity_id="other",
        source_refs=(unrelated_ref,),
        ancestor_ids=("story:other", "story:other/story"),
    )
    unrelated_child = replace(
        unmatched_candidate,
        block=unrelated_block,
        owner_entity_id="story:other",
        owner_page_id="story:other",
    )
    unrelated_parent = replace(
        unmatched["projection"].parents[0],
        parent_id="story:other/story",
        entity_id="other",
        source_refs=(unrelated_ref,),
        child_ids=(unrelated_block.child_id,),
    )
    unmatched["projection"] = replace(
        unmatched["projection"],
        parents=(unrelated_parent,),
        children=(unrelated_child,),
        record_links=(),
    )
    unmatched_result = _build(unmatched)
    assert unmatched_result.passed is False
    assert "unexplained_parent_missing:story:legacy-9001/profile" in unmatched_result.blockers
    assert "unexplained_child_missing:story:legacy-9001:0000" in unmatched_result.blockers
    assert "unexplained_parent_addition:story:other/story" in unmatched_result.blockers
    assert "unexplained_child_addition:story:other/story/step-only" in unmatched_result.blockers


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {
            "1": {
                "step": [],
                "type": 0,
                "name": ["Hidden narrator"],
                "show_name": False,
                "text": [""],
                "choice": [],
            }
        },
    ),
    ids=("empty-object", "numeric-control-only"),
)
def test_control_only_story_exclusion_atomically_closes_complete_profile_pair(
    payload: dict[str, object],
) -> None:
    values = _story_exclusion_fixture(payload)

    first = _build(values)
    second = _build(values)

    assert first.passed is True, (
        "one complete control-only Story profile Parent/Child pair must close "
        f"atomically through its source exclusion; blockers={first.blockers!r}"
    )
    assert first.unexplained_parent_child_loss == 0
    assert values["projection"].parents == ()
    assert values["projection"].children == ()
    assert values["projection"].record_links == ()
    assert len(values["projection"].exclusions) == 1
    exclusion_fact = values["projection"].exclusions[0].to_json()
    active_rows = _active_story_rows(first)
    assert len(active_rows) == 2
    assert {row["record_kind"] for row in active_rows} == {"parent", "child"}
    assert all(row["classification"] == "corrected_semantics" for row in active_rows)
    assert all(row["candidate_identities"] == [] for row in active_rows)
    assert all(row["source_evidence"] == [exclusion_fact] for row in active_rows)
    assert len(
        {row["details"]["atomic_migration_group_id"] for row in active_rows}
    ) == 1
    assert active_rows == _active_story_rows(second)


@pytest.mark.parametrize(
    "fault",
    ("source-title", "source-hash", "revision", "root-path", "story-owner"),
)
def test_control_only_story_exclusion_source_and_owner_mismatch_fail_closed(
    fault: str,
) -> None:
    values = _story_exclusion_fixture({})
    parents = [dict(row) for row in values["active_parents"]]
    children = [dict(row) for row in values["active_children"]]
    if fault == "story-owner":
        parents[0]["entity_id"] = "wrong-owner"
        children[0]["entity_id"] = "wrong-owner"
    else:
        replacement = {
            "source-title": {"source_title": "Data:Story/wrong.json"},
            "source-hash": {"source_content_sha256": "f" * 64},
            "revision": {"revid": 92},
            "root-path": {"json_path": "$.1"},
        }[fault]
        parents[0]["source_refs"] = [{**parents[0]["source_refs"][0], **replacement}]
        children[0]["source_refs"] = [{**children[0]["source_refs"][0], **replacement}]
    values["active_parents"] = tuple(parents)
    values["active_children"] = tuple(children)

    _assert_story_exclusion_migration_rejected(values)


@pytest.mark.parametrize("missing_kind", ("parent", "child"))
def test_control_only_story_exclusion_requires_complete_profile_pair(
    missing_kind: str,
) -> None:
    values = _story_exclusion_fixture({})
    active_key = {
        "parent": "active_parents",
        "child": "active_children",
    }[missing_kind]
    values[active_key] = ()

    _assert_story_exclusion_migration_rejected(values)


def test_invalid_or_unsupported_story_exclusion_cannot_close_profile_pair() -> None:
    invalid = _story_exclusion_fixture({})
    invalid_content = '{"1":'
    invalid_row = {
        "title": "Data:Story/8200.json",
        "revid": 91,
        "content": invalid_content,
        "content_sha256": hashlib.sha256(invalid_content.encode("utf-8")).hexdigest(),
        "json_valid": False,
        "json_error": "fixture invalid payload",
    }
    invalid["projection"] = project_crawler_semantics([invalid_row])
    for record_kind in ("active_parents", "active_children"):
        row = dict(invalid[record_kind][0])
        row["source_refs"] = [
            {
                **row["source_refs"][0],
                "source_content_sha256": invalid_row["content_sha256"],
            }
        ]
        invalid[record_kind] = (row,)
    _assert_story_exclusion_migration_rejected(invalid)

    unsupported = _story_exclusion_fixture(
        {"1": {"subtitle": ["Potentially visible caption"]}}
    )
    _assert_story_exclusion_migration_rejected(unsupported)


def test_exact_duplicate_story_exclusion_yields_one_atomic_migration_fact() -> None:
    single = _story_exclusion_fixture({})
    duplicate = _story_exclusion_fixture({})
    exclusion = duplicate["projection"].exclusions[0]
    duplicate["projection"] = replace(
        duplicate["projection"], exclusions=(exclusion, exclusion)
    )

    single_result = _build(single)
    first = _build(duplicate)
    second = _build(duplicate)

    assert first.passed is True, (
        "an exact duplicate Story exclusion must deduplicate before the complete "
        "profile pair closes atomically; "
        f"blockers={first.blockers!r}"
    )
    active_rows = _active_story_rows(first)
    assert len(active_rows) == 2
    assert all(row["classification"] == "corrected_semantics" for row in active_rows)
    assert all(row["candidate_identities"] == [] for row in active_rows)
    assert len(
        {row["details"]["atomic_migration_group_id"] for row in active_rows}
    ) == 1
    assert first.ledger_rows == single_result.ledger_rows
    assert first.ledger_rows == second.ledger_rows


def test_conflicting_duplicate_story_exclusion_identity_fails_closed() -> None:
    values = _story_exclusion_fixture({})
    exclusion = values["projection"].exclusions[0]
    conflicting = replace(
        exclusion,
        details={**exclusion.details, "story_structure_kind": "conflicting"},
    )
    values["projection"] = replace(
        values["projection"], exclusions=(exclusion, conflicting)
    )

    with pytest.raises(ValueError, match="conflicting candidate exclusion identity"):
        _build(values)


def test_competing_story_exclusion_consumption_fails_closed() -> None:
    competing = _story_exclusion_fixture({})
    second_parent = {
        **competing["active_parents"][0],
        "parent_id": "story:competing/profile",
        "child_ids": ["story:competing:0000"],
    }
    second_child = {
        **competing["active_children"][0],
        "child_id": "story:competing:0000",
        "parent_id": "story:competing/profile",
    }
    competing["active_parents"] = (*competing["active_parents"], second_parent)
    competing["active_children"] = (*competing["active_children"], second_child)
    _assert_story_exclusion_migration_rejected(competing)


def test_story_exclusion_cannot_consume_competing_profile_record_link() -> None:
    values = _story_exclusion_fixture({})
    active_parent_id = values["active_parents"][0]["parent_id"]
    exclusion = values["projection"].exclusions[0]
    competing_link = SemanticRecordLink(
        record_kind="parent",
        legacy_id=active_parent_id,
        candidate_id="story:competing/story",
        change_kind="corrected_semantics",
        source_title=exclusion.source_title,
        source_content_sha256=exclusion.source_content_sha256,
        json_path="$",
        legacy_section="profile",
        candidate_section="story",
    )
    values["projection"] = replace(
        values["projection"], record_links=(competing_link,)
    )

    _assert_story_exclusion_migration_rejected(values)


def test_non_story_record_cannot_consume_story_control_only_exclusion() -> None:
    values = _story_exclusion_fixture({})
    values["active_parents"] = (
        {
            **values["active_parents"][0],
            "entity_type": "item",
            "category": "item",
        },
    )
    values["active_children"] = (
        {
            **values["active_children"][0],
            "entity_type": "item",
            "category": "item",
        },
    )

    _assert_story_exclusion_migration_rejected(values)


def test_non_story_duplicate_legacy_links_remain_fail_closed() -> None:
    story = _story_fixture(tokens=("step-z", "step-a"))
    non_story = _fixture()
    duplicate_non_story = non_story["projection"].record_links[-1]
    projection = CorpusProjection(
        parents=(
            *story["projection"].parents,
            *non_story["projection"].parents,
        ),
        children=(
            *story["projection"].children,
            *non_story["projection"].children,
        ),
        voice_sources=(),
        media_intents=(),
        exclusions=non_story["projection"].exclusions,
        identity_fallbacks=(),
        record_links=(
            *story["projection"].record_links,
            *non_story["projection"].record_links,
            duplicate_non_story,
        ),
    )
    values = {
        **non_story,
        "projection": projection,
        "active_parents": (
            *story["active_parents"],
            *non_story["active_parents"],
        ),
        "active_children": (
            *story["active_children"],
            *non_story["active_children"],
        ),
        "child_bm25": (),
        "media_bm25": (),
    }

    with pytest.raises(
        ValueError,
        match=r"duplicate child fidelity link: char:1/culture:0010",
    ):
        _build(values)


def test_fidelity_retains_media_blocker_categories_and_sums_aggregate_loss() -> None:
    values = _fixture()
    blocker_counts = {
        "missing_local_bytes": 2,
        "missing_resource_metadata": 3,
        "ambiguous_binding": 5,
        "conflicting_binding": 7,
    }
    occurrences = []
    index = 0
    for category, count in blocker_counts.items():
        for _ in range(count):
            index += 1
            occurrences.append(
                {
                    "occurrence_id": "active-occurrence:sha256:" + f"{index:064x}",
                    "active_row_sha256": f"{index + 100:064x}",
                    "active_media_id": "media:sha1:" + f"{index:040x}",
                    "active_sha1": f"{index:040x}",
                    "active_parent_id": "char:1/culture",
                    "active_child_id": "char:1/culture:0010",
                    "candidate_child_id": "char:1/collection/10",
                    "resource_id": "",
                    "candidate_binding_ids": [],
                    "classification": category,
                    "reason_code": "c8c_contract_fixture",
                    "candidate_source_refs": [],
                    "local_evidence": {},
                }
            )
    values["legacy"] = LegacyMediaReconciliation(
        occurrence_rows=tuple(reversed(occurrences)),
        category_counts=blocker_counts,
        active_occurrence_count=len(occurrences),
        unexplained_binding_loss=17,
    )
    values["media_bm25"] = tuple(
        {"media_id": row["active_media_id"], "search_text": "media"}
        for row in reversed(occurrences)
    )

    result = _build(values)

    media_rows = [
        row for row in result.ledger_rows if row["record_kind"] == "media_binding"
    ]
    assert {
        category: sum(
            row["classification"] == category for row in media_rows
        )
        for category in blocker_counts
    } == blocker_counts
    assert result.unexplained_binding_loss == sum(blocker_counts.values()) == 17
    assert result.build_diff["unexplained_binding_loss"] == 17
    assert result.blockers == tuple(
        sorted(
            (
                "legacy_media_missing_local_bytes:2",
                "legacy_media_missing_resource_metadata:3",
                "legacy_media_ambiguous_binding:5",
                "legacy_media_conflicting_binding:7",
                "unexplained_binding_loss:17",
            )
        )
    )
    assert [row["active_identity"] for row in media_rows] == sorted(
        row["active_identity"] for row in media_rows
    )


@pytest.mark.parametrize(
    "mismatch",
    ["active_occurrence_count", "category_counts", "aggregate_loss"],
)
def test_legacy_media_reconciliation_rejects_duplicate_fact_mismatch(
    mismatch: str,
) -> None:
    rows = (
        {
            "occurrence_id": "active-occurrence:sha256:" + "1" * 64,
            "classification": "missing_local_bytes",
        },
        {
            "occurrence_id": "active-occurrence:sha256:" + "2" * 64,
            "classification": "conflicting_binding",
        },
    )
    values = {
        "occurrence_rows": rows,
        "category_counts": {
            "missing_local_bytes": 1,
            "conflicting_binding": 1,
        },
        "active_occurrence_count": 2,
        "unexplained_binding_loss": 2,
    }
    if mismatch == "active_occurrence_count":
        values["active_occurrence_count"] = 3
    elif mismatch == "category_counts":
        values["category_counts"] = {"missing_local_bytes": 2}
    else:
        values["unexplained_binding_loss"] = 1

    with pytest.raises(ValueError):
        LegacyMediaReconciliation(**values)
