from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.rag.contracts import EntityRef
from src.rag.ownership import (
    OwnershipViolation,
    assert_packet_ownership,
    filter_owned_rows,
    ownership_key,
    validate_owned_media,
    validate_target_parent,
)


def _owner(entity_type: str = "type-a", entity_id: str = "id-a") -> EntityRef:
    return EntityRef(entity_type, entity_id, "Fixture Entity", (), "current_exact")


def _rows_for_two_owners() -> list[dict[str, object]]:
    return [
        {
            "child_id": "a-1",
            "parent_id": "a-parent",
            "entity_type": "type-a",
            "entity_id": "id-a",
            "score": 0.5,
        },
        {
            "child_id": "b-1",
            "parent_id": "b-parent",
            "entity_type": "type-b",
            "entity_id": "id-b",
            "score": 0.99,
        },
    ]


def test_ownership_key_requires_both_type_and_id():
    assert ownership_key({"entity_type": "type-a", "entity_id": "id-a"}) == (
        "type-a",
        "id-a",
    )
    assert ownership_key({"entity_type": "type-a"}) is None
    assert ownership_key({"entity_id": "id-a"}) is None


@pytest.mark.parametrize(
    "stage",
    ["structured", "bm25", "dense", "rerank", "expand", "allocate"],
)
def test_owner_gate_removes_other_owner_without_backfill(stage: str):
    kept, diagnostics = filter_owned_rows(_rows_for_two_owners(), _owner(), stage)

    assert [row["child_id"] for row in kept] == ["a-1"]
    assert diagnostics.owner_mismatch == 1
    assert diagnostics.missing_owner_metadata == 0
    assert diagnostics.before_count == 2
    assert diagnostics.after_count == 1


def test_missing_owner_metadata_is_not_owned():
    kept, diagnostics = filter_owned_rows(
        [{"child_id": "unknown"}],
        _owner("fixture", "1"),
        "dense",
    )

    assert kept == []
    assert diagnostics.missing_owner_metadata == 1
    assert diagnostics.owner_mismatch == 0


def test_owner_gate_is_noop_when_entity_is_unresolved():
    rows: list[Mapping[str, object]] = _rows_for_two_owners()

    kept, diagnostics = filter_owned_rows(rows, None, "dense")

    assert [row["child_id"] for row in kept] == ["a-1", "b-1"]
    assert diagnostics.before_count == diagnostics.after_count == 2


def test_target_parent_must_exist_and_have_the_same_owner():
    rows = _rows_for_two_owners()

    assert validate_target_parent("a-parent", _owner(), rows) == "a-parent"
    with pytest.raises(OwnershipViolation, match="target parent"):
        validate_target_parent("b-parent", _owner(), rows)
    with pytest.raises(OwnershipViolation, match="target parent"):
        validate_target_parent("missing", _owner(), rows)


def test_owned_media_and_final_packet_reject_foreign_or_incomplete_owner():
    owned = {
        "media_id": "owned",
        "entity_type": "type-a",
        "entity_id": "id-a",
    }
    foreign = {
        "media_id": "foreign",
        "entity_type": "type-b",
        "entity_id": "id-b",
    }
    incomplete = {"media_id": "incomplete", "entity_id": "id-a"}

    kept, diagnostics = validate_owned_media([owned, foreign, incomplete], _owner())

    assert [item["media_id"] for item in kept] == ["owned"]
    assert diagnostics.owner_mismatch == 1
    assert diagnostics.missing_owner_metadata == 1
    with pytest.raises(OwnershipViolation, match="owner mismatch"):
        assert_packet_ownership(_owner(), [owned], [foreign])


def test_final_packet_allows_unresolved_owner_without_claiming_ownership():
    assert_packet_ownership(None, _rows_for_two_owners(), [])
