from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.huiji_rag.generation_zero import (
    BOOTSTRAP_JOURNAL_SCHEMA,
    bootstrap_lock,
    build_effective_runtime_tuple,
    create_pointer_cas,
    read_journal,
    append_journal_event,
)


def test_effective_tuple_excludes_authority_transport_fields() -> None:
    common = {
        "artifact_capability": "legacy",
        "artifact_schema_version": "evb.media-asset/v1_legacy",
        "build_version": "dev",
        "artifacts": {"parent_blocks": "a" * 64},
        "milvus": {"collection": "text_child_bge_m3_v3", "row_count": 16010},
        "embedding": {"model_id": "BAAI/bge-m3", "config_fingerprint": "b" * 64},
    }
    left = build_effective_runtime_tuple(**common)
    right = build_effective_runtime_tuple(**common)
    assert left == right
    changed = build_effective_runtime_tuple(
        **{**common, "milvus": {"collection": "other", "row_count": 16010}}
    )
    assert changed["tuple_sha256"] != left["tuple_sha256"]
    assert "source_mode" not in left


def test_journal_is_hash_chained_and_rejects_invalid_transition(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap_journal.v1.jsonl"
    first = append_journal_event(
        path,
        state="prepared",
        intent_sha256="a" * 64,
        pointer_sha256="b" * 64,
    )
    second = append_journal_event(
        path,
        state="pointer_written",
        intent_sha256="a" * 64,
        pointer_sha256="b" * 64,
    )
    events = read_journal(path)
    assert [item["state"] for item in events] == ["prepared", "pointer_written"]
    assert events[0]["schema_version"] == BOOTSTRAP_JOURNAL_SCHEMA
    assert events[1]["previous_event_sha256"] == hashlib.sha256(
        json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert second["sequence"] == 2
    with pytest.raises(ValueError, match="transition"):
        append_journal_event(
            path,
            state="committed",
            intent_sha256="a" * 64,
            pointer_sha256="b" * 64,
        )


def test_pointer_cas_never_overwrites_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "active_build.v1.json"
    first = b'{"generation":0}\n'
    create_pointer_cas(target, first, operation_id="operation-a")
    assert target.read_bytes() == first
    with pytest.raises(FileExistsError):
        create_pointer_cas(target, b'{"generation":1}\n', operation_id="operation-b")
    assert target.read_bytes() == first


def test_bootstrap_lock_releases_for_the_next_operation(tmp_path: Path) -> None:
    with bootstrap_lock(tmp_path, "first-operation"):
        pass
    with bootstrap_lock(tmp_path, "second-operation"):
        pass
