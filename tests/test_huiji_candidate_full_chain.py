from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.verify_huiji_candidate_full_chain import (
    select_case_owners,
    validate_voice_pages,
)


def _child(owner, section, index):
    return {
        "entity_type": owner[0],
        "entity_id": owner[1],
        "entity_name": owner[2],
        "section_kind": section,
        "child_id": f"{owner[1]}/{section}/{index}",
    }


def _media(owner, role, index):
    return {
        "entity_id": owner[1],
        "entity_name": owner[2],
        "owner_entity_id": f"{owner[0]}:{owner[1]}",
        "media_role": role,
        "is_available": True,
        "binding_id": f"binding-{index}",
    }


def test_dynamic_case_selection_uses_inventory_capabilities_not_fixed_entity():
    full = ("character", "char:full", "Full")
    collection = ("character", "char:collection", "Collection")
    culture = ("character", "char:culture", "Culture")
    udimo = ("character", "char:udimo", "Udimo")
    children = [
        *[_child(full, "voice", index) for index in range(8)],
        _child(full, "skill", 1),
        _child(collection, "collection", 1),
        _child(culture, "culture_dossier", 1),
        _child(udimo, "udimo", 1),
    ]
    media = [
        _media(full, "voice", 1),
        _media(full, "skill", 2),
        _media(collection, "collection_item", 3),
        _media(udimo, "udimo", 4),
    ]

    selected = select_case_owners(children, media)

    assert selected["multi_skill_voice"] == full
    assert selected["skill"] == full
    assert selected["voice"] == full
    assert selected["collection"] == collection
    assert selected["culture_dossier"] == culture
    assert selected["udimo"] == udimo


def test_voice_page_validation_traverses_cursor_and_rejects_duplicate_language():
    second = {
        "lines": [
            {
                "voice_line_id": "line-2",
                "variants": [
                    {"binding_id": "binding-2", "language": "en"},
                ],
            }
        ],
        "page_size": 1,
        "total_lines": 2,
        "has_more": False,
        "next_cursor": None,
    }
    registry = SimpleNamespace(get_voice_page=lambda cursor: second)
    first = {
        "lines": [
            {
                "voice_line_id": "line-1",
                "variants": [
                    {"binding_id": "binding-1", "language": "zh"},
                ],
            }
        ],
        "page_size": 1,
        "total_lines": 2,
        "has_more": True,
        "next_cursor": "cursor-1",
    }

    assert validate_voice_pages(registry, first) == {
        "page_count": 2,
        "line_count": 2,
        "binding_count": 2,
        "language_count": 2,
    }

    broken = dict(first)
    broken["lines"] = [
        {
            "voice_line_id": "line-1",
            "variants": [
                {"binding_id": "binding-1", "language": "zh"},
                {"binding_id": "binding-3", "language": "zh"},
            ],
        }
    ]
    with pytest.raises(ValueError, match="language variants"):
        validate_voice_pages(registry, broken)
