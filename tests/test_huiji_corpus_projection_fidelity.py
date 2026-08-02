from __future__ import annotations

import hashlib
import json

from src.huiji_rag.build.projection import project_crawler_semantics


def _row(title: str, content: dict[str, object]) -> dict[str, object]:
    encoded = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    return {
        "title": title,
        "revid": 11,
        "content": encoded,
        "content_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
    }


def test_projection_emits_reversible_legacy_links_for_semantic_corrections() -> None:
    projection = project_crawler_semantics(
        [
            _row(
                "Data:Char/8.json",
                {
                    "id": 8,
                    "name": "角色八",
                    "character_data": [
                        {"id": 20, "type": 2, "title": "藏品", "text": "藏品说明。"},
                        {"id": 30, "type": 3, "title": "文化", "text": "文化说明。"},
                    ],
                },
            )
        ]
    )
    by_legacy = {item.legacy_id: item for item in projection.record_links if item.legacy_id}

    collection = by_legacy["char:8/culture:0000"]
    assert collection.candidate_id == "char:8/collection/20"
    assert collection.change_kind == "corrected_semantics"
    assert (collection.legacy_section, collection.candidate_section) == ("culture", "collection")

    culture = by_legacy["char:8/item:0001"]
    assert culture.candidate_id == "char:8/culture_dossier/30"
    assert culture.change_kind == "corrected_semantics"
    assert (culture.legacy_section, culture.candidate_section) == (
        "item",
        "culture_dossier",
    )

    profile = by_legacy["char:8/profile:0000"]
    assert profile.candidate_id == "char:8/profile/root"
    assert profile.change_kind == "preserved_rekeyed"


def test_generic_entities_keep_text_and_parent_identity_while_rekeying_child() -> None:
    row = _row(
        "Data:Item/1/100.json",
        {"id": "1/100", "name": "测试物品", "desc": "物品描述。"},
    )
    projection = project_crawler_semantics([row])
    parent = projection.parents[0]
    child = projection.children[0]

    assert parent.parent_id == "item:1/100/profile"
    assert child.block.child_id == "item:1/100/profile/root"
    assert child.block.text == "测试物品\n物品描述。"
    assert parent.content_hash == child.block.content_hash
    links = {item.record_kind: item for item in projection.record_links}
    assert links["parent"].change_kind == "preserved_exact"
    assert links["child"].legacy_id == "item:1/100:0000"
    assert links["child"].change_kind == "preserved_rekeyed"


def test_generic_empty_name_falls_back_to_full_crawler_title() -> None:
    row = _row(
        "Data:Item/2/-1.json",
        {"id": "2/-1", "name": "", "desc": ""},
    )
    projection = project_crawler_semantics([row])

    assert projection.children[0].block.entity_name == "Data:Item/2/-1"
    assert projection.children[0].block.text.startswith("Data:Item/2/-1\n")


def test_generic_parent_uses_legacy_sentence_boundary_summary() -> None:
    long_value = "x" * 300 + "。" + "y" * 900
    row = _row("Data:Episode/7.json", {"content": long_value})
    projection = project_crawler_semantics([row])

    summary = projection.parents[0].summary_text
    assert summary.endswith("。")
    assert len(summary) < 1000


def test_every_child_has_nonempty_heading_path_and_explicit_entity_aliases() -> None:
    projection = project_crawler_semantics(
        [
            _row("Data:Char/map.json", {"name": {"Alias Name": 8}}),
            _row("Data:Char/8.json", {"id": 8, "name": "Canonical Name"}),
            _row(
                "Data:Item/1.json",
                {"id": 1, "name": "Item Name", "desc": "Item description."},
            ),
        ]
    )

    assert projection.children
    assert all(child.block.heading_path for child in projection.children)
    assert all(
        isinstance(child.block.entity_aliases, tuple)
        for child in projection.children
    )
    character = next(
        child for child in projection.children if child.block.entity_type == "character"
    )
    assert character.block.entity_aliases == ("Alias Name",)


def test_legacy_character_enrichment_does_not_change_text_owner_section_or_route() -> None:
    projection = project_crawler_semantics(
        [_row("Data:Char/8.json", {"id": 8, "name": "Canonical Name"})]
    )
    child = projection.children[0]

    assert child.block.text == (
        "Canonical Name 角色资料\n稀有度: \n职业: \n伤害类型: "
    )
    assert child.block.content == child.block.text
    assert child.owner_entity_id == "character:8"
    assert child.owner_page_id == "char:8"
    assert child.block.section_kind == "profile"
    assert child.block.route_tags == ("intro", "profile_fact", "media")


def test_schema_enrichment_is_separate_from_semantic_fidelity_change() -> None:
    projection = project_crawler_semantics(
        [_row("Data:Item/1.json", {"id": 1, "name": "Item", "desc": "Description."})]
    )
    child = projection.children[0]
    enriched = child.to_json()

    assert enriched["content"] == child.block.text
    assert enriched["heading_path"] == ("profile",)
    assert enriched["entity_aliases"] == ()
    assert child.block.content_hash == hashlib.sha256(child.block.text.encode()).hexdigest()
