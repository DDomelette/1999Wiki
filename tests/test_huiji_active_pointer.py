from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.huiji_rag.active_pointer import (
    ACTIVE_POINTER_FIELDS,
    ACTIVE_POINTER_SCHEMA_VERSION,
    canonical_pointer_path,
    load_active_pointer,
    resolve_generation_zero_evidence,
    validate_active_pointer,
)


def _pointer(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": ACTIVE_POINTER_SCHEMA_VERSION,
        "generation": 0,
        "build_version": "dev",
        "previous_build_version": None,
        "build_manifest_sha256": "ad886077e2aff90350480c9925686693121af9c643796131c361fde6efeed231",
        "milvus_collection_name": "text_child_bge_m3_v3",
        "collection_schema_fingerprint": "db9e13b98d7a1cf4116ba6647a16eb0e7daff0a77c558f66c9db2597038a6bc4",
        "collection_manifest_sha256": "c" * 64,
        "embedding_model_id": "BAAI/bge-m3",
        "embedding_config_fingerprint": "17787be97e63ea53e3298748adf546ebc17d5456669481349eb8bb088b336099",
        "artifact_schema_version": "evb.media-asset/v1_legacy",
        "deployment_inventory_sha256": "e" * 64,
        "activation_epoch": 0,
        "activation_id": "legacy-dev-generation-0-20260722a",
        "activated_at_utc": "2026-07-22T01:02:03Z",
    }
    value.update(overrides)
    return value


def test_generation_zero_pointer_contract_is_exact() -> None:
    pointer = validate_active_pointer(_pointer())
    assert frozenset(pointer) == ACTIVE_POINTER_FIELDS
    assert pointer["generation"] == 0

    for field, bad in (
        ("generation", True),
        ("activation_epoch", 1),
        ("build_version", "candidate-f"),
        ("previous_build_version", "dev"),
        ("milvus_collection_name", "other"),
        ("embedding_model_id", "other"),
        ("artifact_schema_version", "evb.media-asset/v3"),
        ("activated_at_utc", "2026-07-22T01:02:03+00:00"),
        ("build_manifest_sha256", "A" * 64),
    ):
        with pytest.raises(ValueError):
            validate_active_pointer(_pointer(**{field: bad}))


def test_pointer_rejects_missing_extra_and_legacy_alias() -> None:
    missing = _pointer()
    missing.pop("collection_manifest_sha256")
    with pytest.raises(ValueError, match="field set"):
        validate_active_pointer(missing)
    with pytest.raises(ValueError, match="field set"):
        validate_active_pointer({**_pointer(), "unknown": "value"})
    aliased = _pointer()
    aliased["collection_name"] = aliased.pop("milvus_collection_name")
    with pytest.raises(ValueError, match="field set"):
        validate_active_pointer(aliased)


def test_pointer_loader_rejects_duplicate_keys_and_noncanonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "active_build.v1.json"
    path.write_text('{"schema_version":"evb.active-build/v1","schema_version":"x"}\n')
    with pytest.raises(ValueError, match="duplicate"):
        load_active_pointer(path)

    path.write_text(json.dumps(_pointer(), indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical"):
        load_active_pointer(path)


def test_canonical_path_and_generation_zero_evidence_are_derived(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    assert canonical_pointer_path(processed) == processed / "active_build.v1.json"
    manifest, inventory = resolve_generation_zero_evidence(processed, _pointer())
    expected = processed / "activation/bootstrap/legacy-dev-generation-0-20260722a"
    assert manifest == expected / "collection_manifest.v1.json"
    assert inventory == expected / "deployment_inventory.v1.json"

    escaped = processed / "link"
    try:
        escaped.symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege is unavailable")
    with pytest.raises(ValueError, match="containment"):
        canonical_pointer_path(escaped)
