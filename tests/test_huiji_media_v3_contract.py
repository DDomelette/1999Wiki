from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.huiji_rag.build.contracts import (
    FIXTURE_FILENAMES,
    MEDIA_V3_FIELD_ORDER,
    MEDIA_V3_MANIFEST_SCHEMA_VERSION,
    MEDIA_V3_ROW_SCHEMA_VERSION,
    MEDIA_V3_SCHEMA_VERSION,
    binding_identity,
    canonical_json_bytes,
    compute_binding_id,
    compute_media_id,
    compute_resource_id,
    fixture_contract_fingerprint,
    media_v3_schema_document,
    normalize_media_v3_rows,
    validate_media_v3_row,
)


FIXTURE_ROOT = Path("tests/fixtures/contracts/huiji_media_v3")


def _rows() -> list[dict[str, object]]:
    return [json.loads(line) for line in (FIXTURE_ROOT / "media_assets.v3.jsonl").read_text(
        encoding="utf-8"
    ).splitlines() if line]


def test_frozen_schema_document_and_row_order_match_fixture() -> None:
    schema = json.loads((FIXTURE_ROOT / "media_assets.v3.schema.json").read_text(encoding="utf-8"))

    assert schema == media_v3_schema_document()
    assert schema["schema_version"] == MEDIA_V3_SCHEMA_VERSION
    assert schema["row_schema_version"] == MEDIA_V3_ROW_SCHEMA_VERSION
    assert schema["manifest_schema_version"] == MEDIA_V3_MANIFEST_SCHEMA_VERSION
    assert tuple(schema["x-field-order"]) == MEDIA_V3_FIELD_ORDER
    assert schema["required"] == list(MEDIA_V3_FIELD_ORDER)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["binding_status"]["enum"] == ["exact", "not_applicable"]
    assert schema["properties"]["binding_id"]["pattern"].startswith("^binding:sha256:")

    for row in _rows():
        assert tuple(row) == MEDIA_V3_FIELD_ORDER
        assert validate_media_v3_row(row) is row
        assert "local_relpath" not in row


def test_frozen_ids_ignore_display_and_order_fields_but_track_relationship_and_content() -> None:
    row = _rows()[0]
    original = compute_binding_id(row)
    changed_display = {
        **row,
        "sort_order": 99,
        "entity_name": "Renamed display value",
        "filename": "renamed.webp",
        "title": "Renamed title",
        "source_url": "https://example.test/source",
        "url": "https://example.test/object",
    }
    assert compute_binding_id(changed_display) == original
    assert binding_identity(changed_display) == binding_identity(row)

    changed_relation = {**row, "source_binding_token": "resource-row:portrait:changed"}
    assert compute_binding_id(changed_relation) != original

    changed_resource = {
        **row,
        "resource_id": compute_resource_id("9" * 64),
    }
    assert compute_binding_id(changed_resource) != original
    assert compute_media_id("a" * 40) == "media:sha1:" + "a" * 40
    with pytest.raises(ValueError, match="lowercase content_sha256"):
        compute_resource_id("A" * 64)


def test_fixture_normalization_preserves_all_bindings_and_expected_identity_sets() -> None:
    rows = _rows()
    resources, bindings = normalize_media_v3_rows(rows)
    expected_resources = json.loads(
        (FIXTURE_ROOT / "expected_resources.json").read_text(encoding="utf-8")
    )
    expected_bindings = json.loads(
        (FIXTURE_ROOT / "expected_bindings.json").read_text(encoding="utf-8")
    )

    assert len(bindings) == len(rows) == expected_bindings["count"]
    assert len(resources) == expected_resources["count"]
    assert {row["resource_id"] for row in resources} == {
        row["resource_id"] for row in expected_resources["resources"]
    }
    assert {row["binding_id"] for row in bindings} == {
        row["binding_id"] for row in expected_bindings["bindings"]
    }

    shared = {}
    for binding in bindings:
        shared.setdefault(binding["resource_id"], []).append(binding)
    shared_groups = [group for group in shared.values() if len(group) > 1]
    assert len(shared_groups) == 1
    assert {row["owner_entity_id"] for row in shared_groups[0]} == {
        "character:1001",
        "character:1002",
    }
    assert len({row["binding_id"] for row in shared_groups[0]}) == 2


def test_fixture_covers_voice_variants_collection_udimo_and_empty_optional_identity() -> None:
    rows = _rows()
    voice = [row for row in rows if row["media_role"] == "voice"]
    assert len(voice) == 2
    assert len({row["child_id"] for row in voice}) == 1
    assert len({row["event_name"] for row in voice}) == 1
    assert {row["language"] for row in voice} == {"en-us", "zh-cn"}
    assert {row["media_role"] for row in rows} >= {"collection_item", "udimo", "voice"}
    assert any(row["variant"] == "" and row["skin_id"] == "" for row in rows)
    assert len({row["media_id"] for row in rows}) < len(rows)


def test_contract_fingerprint_pins_exactly_four_files_and_is_deterministic() -> None:
    first = fixture_contract_fingerprint(FIXTURE_ROOT)
    second = fixture_contract_fingerprint(FIXTURE_ROOT)

    assert first == second
    assert [item["path"] for item in first["files"]] == list(FIXTURE_FILENAMES)
    assert all(len(item["sha256"]) == 64 for item in first["files"])
    assert len(first["contract_sha256"]) == 64
    assert canonical_json_bytes(first).startswith(b'{"contract_sha256":')


def test_validation_rejects_reordered_or_local_path_rows() -> None:
    row = _rows()[0]
    reordered = {"media_id": row["media_id"], **{key: value for key, value in row.items() if key != "media_id"}}
    with pytest.raises(ValueError, match="field order"):
        validate_media_v3_row(reordered)

    with pytest.raises(ValueError, match="local_relpath"):
        validate_media_v3_row({**copy.deepcopy(row), "local_relpath": "assets/shared.webp"})
