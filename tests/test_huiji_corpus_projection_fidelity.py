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
