from __future__ import annotations

import base64
import builtins
import copy
import hashlib
import importlib
import importlib.util
import io
import json
import os
import platform
import socket
import subprocess
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest


SCRIPT_RELATIVE_PATH = "scripts/diagnose_huiji_corpus_fidelity.py"
SCRIPT = Path(__file__).resolve().parents[1] / SCRIPT_RELATIVE_PATH
HEAD = "9c226de2e850ecabf8e672afaacc8a517e802e7d"
TREE = "f4dcc15ef5cc7f811132580c3423c63a05a06d44"
C8A_COMMIT = "012c7ca6b3abaa0445ccd00a8974ea4fefcbd333"
C8B_COMMIT = "7366787401603e9a86d7277c99b3cc3f49e97508"
C8C_COMMIT = HEAD
C8B_RECEIPT_SHA256 = (
    "7dfc5cce2fda7b1b7ce97f76e59413a16c8df249abe1d1aa891b32892646fc20"
)
C8C_RECEIPT_SHA256 = (
    "55d9f63504b1522c250e049bd2fbaff66db70cab382030baf4b35bfe87cb8df2"
)
C8B_TAXONOMY_SHA256 = (
    "44a511ba41a7067e4536c51226c8c40603c55806653a22bde468be066ac32ecd"
)
C8B_EVIDENCE_MANIFEST_SHA256 = (
    "977cde250ec88e970150ce98d97339f17555639dbcf905154ffd4c9a283e5fc0"
)
C8C_PRODUCT_MANIFEST_SHA256 = (
    "dc7dc31936c8e85d6c6f3af5a10c1eeb9a70300ac9990476d8f27bb1b164e764"
)
PROTECTED_STATE_SHA256 = (
    "ef85f54d229e05d975092badfd734899e85c6a74d30f0cac310b8b0d0a4b355f"
)
RUN_ID = "task8-c-c8d-fixture-20260731T000000Z"
SCRIPT_BYTES = SCRIPT.read_bytes()
SCRIPT_SHA256 = hashlib.sha256(SCRIPT_BYTES).hexdigest()
OUTPUT_NAMES = (
    "manifest.c8d-fidelity.v1.json",
    "receipt.c8d-fidelity.v1.json",
    "summary.c8d-fidelity.v1.json",
)
OUTPUT_SCHEMAS = {
    "manifest.c8d-fidelity.v1.json": "huiji.c8d-fidelity-manifest/v1",
    "receipt.c8d-fidelity.v1.json": "huiji.c8d-fidelity-receipt/v1",
    "summary.c8d-fidelity.v1.json": "huiji.c8d-fidelity-summary/v1",
}
CRAWLER_SOURCES = (
    "pages.jsonl",
    "wikitext.jsonl",
    "data_pages.jsonl",
    "resources_manifest.jsonl",
)
MEDIA_COUNTS = {
    "ambiguous_binding": 2,
    "conflicting_binding": 1,
    "missing_local_bytes": 3,
    "missing_resource_metadata": 0,
    "preserved_binding": 0,
    "rekeyed_binding": 0,
    "source_removed_with_evidence": 0,
}
ACTIVITY_COUNTERS = {
    "activation": 0,
    "active_pointer_changes": 0,
    "allowed_read_only_git_calls": 1,
    "downloads": 0,
    "forbidden_subprocess_calls": 0,
    "local_media_byte_reads": 0,
    "milvus_writes": 0,
    "minio_writes": 0,
    "mysql_writes": 0,
    "network": 0,
    "production_writes": 0,
    "total_subprocess_calls": 1,
    "vector_or_embedding_builds": 0,
    "writes_outside_exact_outputs": 0,
}
SAMPLE_FIELDS = {
    "record_kind",
    "classification",
    "reason_code",
    "active_identity_sha256",
    "candidate_identity_count",
    "candidate_identities_sha256",
    "source_evidence_count",
}
C8B_RECEIPT_DEFLATE_BASE64 = (
    "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"
)
C8C_RECEIPT_DEFLATE_BASE64 = (
    "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"
)


def _load_diagnostic():
    assert SCRIPT.is_file(), (
        "missing tracked diagnostic: scripts/diagnose_huiji_corpus_fidelity.py"
    )
    spec = importlib.util.spec_from_file_location(
        "diagnose_huiji_corpus_fidelity_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_json_bytes(
    value: object, *, trailing_newline: bool = True
) -> bytes:
    rendered = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if trailing_newline:
        rendered += "\n"
    return rendered.encode("utf-8")


def _canonical_bytes(value: object) -> bytes:
    return _canonical_json_bytes(value, trailing_newline=True)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(path: Path, raw: bytes, row_count: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "path": path.as_posix(),
        "sha256": _sha256(raw),
        "size_bytes": len(raw),
    }
    if row_count is not None:
        result["row_count"] = row_count
    return result


def _write_json(path: Path, value: object) -> dict[str, object]:
    raw = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return _identity(path, raw)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> dict[str, object]:
    raw = b"".join(_canonical_bytes(row) for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return _identity(path, raw, len(rows))


def _write_bytes(path: Path, raw: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return _identity(path, raw)


def _raw_identity(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return _identity(path, raw)


def _hashed(value: str) -> str:
    return _sha256(value.encode("utf-8"))


def _source_binding_token_id(value: object) -> str:
    return "source-binding:sha256:" + _sha256(
        _canonical_json_bytes(value, trailing_newline=False)
    )


def _approved_receipt_bytes(encoded: str) -> bytes:
    return zlib.decompress(base64.b64decode(encoded), -zlib.MAX_WBITS)


def _active_parent() -> dict[str, object]:
    return {
        "record_id": "story:9/profile",
        "entity_type": "story",
        "category": "story",
        "section_kind": "profile",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "kind": "legacy-data-page",
            }
        ],
    }


def _active_child() -> dict[str, object]:
    return {
        "record_id": "story:9/profile:0000",
        "parent_id": "story:9/profile",
        "entity_type": "story",
        "category": "story",
        "section_kind": "profile",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "kind": "legacy-data-page",
            }
        ],
    }


def _active_non_story_child() -> dict[str, object]:
    return {
        # Deliberately misleading prefix: the typed row, not this identifier,
        # is the authoritative Story/non-Story partition evidence.
        "record_id": "story:mismatched-prefix/profile:0000",
        "parent_id": "character:9/profile",
        "entity_type": "character",
        "category": "character",
        "section_kind": "profile",
        "source_refs": [
            {
                "source_title": "Data:Character/9.json",
                "content_sha256": "b" * 64,
                "kind": "legacy-data-page",
            }
        ],
    }


def _candidate_parent() -> dict[str, object]:
    return {
        "record_id": "story:9/story",
        "entity_id": "9",
        "entity_type": "story",
        "category": "story",
        "section_kind": "story",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "kind": "data-page",
            }
        ],
    }


def _candidate_child(index: int) -> dict[str, object]:
    return {
        "record_id": f"story:9/story:step-{index:04d}",
        "parent_id": "story:9/story",
        "entity_id": "9",
        "entity_type": "story",
        "category": "story",
        "section_kind": "story",
        "source_token": f"$.steps[{index}]",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "json_path": f"$.steps[{index}]",
                "kind": "data-page",
            }
        ],
    }


def _candidate_non_story_child() -> dict[str, object]:
    return {
        "record_id": "character:9/profile-v2:0000",
        "parent_id": "character:9/profile-v2",
        "entity_id": "9",
        "entity_type": "character",
        "category": "character",
        "section_kind": "profile-v2",
        "source_token": "$.profile",
        "source_refs": [
            {
                "source_title": "Data:Character/9.json",
                "content_sha256": "b" * 64,
                "json_path": "$.profile",
                "kind": "data-page",
            }
        ],
    }


def _story_ledger_row() -> dict[str, object]:
    return {
        "schema_version": "huiji.fidelity-ledger/v1",
        "ledger_id": "fidelity:sha256:" + "c" * 64,
        "record_kind": "child",
        "active_identity": "story:9/profile:0000",
        "candidate_identities": [
            "story:9/story:step-0000",
            "story:9/story:step-0001",
        ],
        "classification": "blocked_ambiguous",
        "reason_code": "candidate_identity_ambiguous",
        "active_sha256": _hashed("story-active-child"),
        "candidate_sha256": _hashed("story-candidate-children"),
        "source_evidence": [
            {
                "source_title": "Data:Story/9.json",
                "source_content_sha256": "a" * 64,
                "json_path": "$.steps",
            }
        ],
        "details": {"legacy_section": "profile", "candidate_section": "story"},
    }


def _non_story_ledger_row() -> dict[str, object]:
    return {
        "schema_version": "huiji.fidelity-ledger/v1",
        "ledger_id": "fidelity:sha256:" + "d" * 64,
        "record_kind": "child",
        # Deliberately misleading prefix: Story classification must come from
        # the accepted source-backed C8b audit, never this string prefix.
        "active_identity": "story:mismatched-prefix/profile:0000",
        "candidate_identities": ["character:9/profile-v2:0000"],
        "classification": "blocked_ambiguous",
        "reason_code": "candidate_identity_ambiguous",
        "active_sha256": _hashed("character-active-child"),
        "candidate_sha256": _hashed("character-candidate-child"),
        "source_evidence": [
            {
                "source_title": "Data:Character/9.json",
                "source_content_sha256": "b" * 64,
                "json_path": "$.profile",
            }
        ],
        "details": {"legacy_section": "profile", "candidate_section": "profile-v2"},
    }


def _c8c_taxonomy(
    active_media_rows: list[dict[str, object]],
) -> dict[str, object]:
    categories = (
        "ambiguous_binding",
        "ambiguous_binding",
        "conflicting_binding",
        "missing_local_bytes",
        "missing_local_bytes",
        "missing_local_bytes",
    )
    rows = []
    for index, (active_media_row, category) in enumerate(
        zip(active_media_rows, categories, strict=True)
    ):
        candidate_binding_ids = [
            (
                active_media_rows[0]["binding_id"]
                if category == "ambiguous_binding"
                else active_media_row["binding_id"]
            )
        ]
        raw_source_binding_token = (
            active_media_rows[0]["source_binding_token"]
            if category == "ambiguous_binding"
            else active_media_row["source_binding_token"]
        )
        rows.append(
            {
                "occurrence_id": "legacy-occurrence:sha256:"
                + f"{index + 1:x}" * 64,
                "legacy_row_sha256": _sha256(
                    _canonical_json_bytes(
                        active_media_row, trailing_newline=False
                    )
                ),
                "legacy_media_id": active_media_row["media_id"],
                "legacy_sha1": active_media_row["sha1"],
                "legacy_parent_id": active_media_row["parent_id"],
                "legacy_child_id": active_media_row["child_id"],
                "legacy_resource_identity_id": (
                    "legacy-resource:sha256:" + f"{index + 7:x}" * 64
                ),
                "category": category,
                "reason_code": f"verified_binding_{category}",
                "candidate_shape": "unique",
                "exact_candidate_count": 1,
                "candidate_binding_ids": candidate_binding_ids,
                "potential_candidate_ids": candidate_binding_ids,
                "candidate_source_binding_token_ids": [
                    _source_binding_token_id(raw_source_binding_token)
                ],
                "source_relation_shape": "unique",
                "successor_parent_count": 1,
                "successor_parent_ids": [
                    (
                        "character:conflict/profile"
                        if category == "conflicting_binding"
                        else "story:9/story"
                    )
                ],
                "successor_child_count": 1,
                "successor_child_ids": [
                    (
                        "character:conflict/profile:0000"
                        if category == "conflicting_binding"
                        else "story:9/story:step-0000"
                    )
                ],
                "owner_transition": True,
                "parent_transition": True,
                "child_transition": True,
                "current_closure_status": (
                    "conflicting"
                    if category == "conflicting_binding"
                    else "closed"
                ),
                "resource_metadata_present": True,
                "resource_metadata_conflicting": (
                    category == "conflicting_binding"
                ),
                "potential_candidate_collision": (
                    category == "ambiguous_binding"
                ),
                "local_byte_state": "absent",
                "local_size_verified": False,
                "local_sha1_verified": False,
                "local_sha256_verified": False,
                "protected_candidate_resource_evidence": False,
                "explicit_source_removal_evidence": False,
            }
        )
    return {
        "schema_version": "huiji.c8c-legacy-media-taxonomy/v1",
        "run_id": "task8-c-20260730T145113Z",
        "active_occurrence_count": len(active_media_rows),
        "category_counts": MEDIA_COUNTS,
        "bounded_samples": {},
        "coverage_checks": {
            "all_categories_known": True,
            "category_sum_equals_active_occurrence_count": True,
            "each_active_occurrence_exactly_once": True,
            "incomplete_evidence_explicit_count": len(active_media_rows),
            "potential_candidate_collision_count": 1,
            "proven_candidate_consumption_collision_count": 0,
        },
        "duplicate_consumption_checks": {
            "bounded_collision_samples": [
                {
                    "candidate_binding_id": active_media_rows[0]["binding_id"],
                    "occurrence_ids": [
                        "legacy-occurrence:sha256:" + "1" * 64,
                        "legacy-occurrence:sha256:" + "2" * 64,
                    ],
                }
            ],
            "duplicate_active_occurrence_id_count": 0,
            "potential_candidate_collision_count": 1,
            "proven_candidate_consumption_collision_count": 0,
        },
        "population_cross_check": {
            "accepted_baseline": len(active_media_rows),
            "accepted_fidelity_active_occurrences": len(active_media_rows),
            "accepted_fidelity_unexplained_binding_loss": len(active_media_rows),
            "legacy_jsonl": len(active_media_rows),
            "pinned_expected_result": len(active_media_rows),
        },
        "rows": rows,
    }


def _run_config(tmp_path: Path) -> tuple[Path, str, Path, dict[str, object]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository = tmp_path / "repository"
    evidence = repository / "frozen"
    output_root = tmp_path / RUN_ID
    repository.mkdir()

    active_parent = _active_parent()
    active_child = _active_child()
    candidate_parent = _candidate_parent()
    candidate_children = [
        _candidate_child(0),
        _candidate_child(1),
        _candidate_non_story_child(),
    ]
    active_media_rows = [
        {
            "binding_id": "binding:sha256:" + f"{index + 1:x}" * 64,
            "media_id": "media:sha1:" + f"{index + 1:x}" * 40,
            "sha1": f"{index + 1:x}" * 40,
            "parent_id": "story:9/profile",
            "child_id": "story:9/profile:0000",
            "source_binding_token": f"wiki:legacy-media:{index}",
        }
        for index in range(6)
    ]
    # Repeated SHA1 values are valid legacy/resource facts when the concrete
    # filename/size identity distinguishes the resource rows.
    active_media_rows[1]["sha1"] = active_media_rows[0]["sha1"]
    active_media_rows[1]["media_id"] = active_media_rows[0]["media_id"]
    candidate_media_rows = []
    for index, active_media_row in enumerate(active_media_rows):
        filename = f"safe-{index}.png"
        title = f"Natural context for safe media {index}"
        content_sha256 = f"{index + 1:x}" * 64
        candidate_media_rows.append(
            {
                "binding_id": active_media_row["binding_id"],
                "resource_id": "resource:sha256:" + f"{index + 1:x}" * 64,
                "source_sha1": active_media_row["sha1"],
                "content_sha256": content_sha256,
                "content_hash": f"sha256:{content_sha256}",
                "size": 123 + index,
                "filename": filename,
                "title": title,
                "source_binding_token": active_media_row["source_binding_token"],
                "parent_id": (
                    "character:conflict/profile"
                    if index == 2
                    else "story:9/story"
                ),
                "child_id": (
                    "character:conflict/profile:0000"
                    if index == 2
                    else "story:9/story:step-0000"
                ),
            }
        )
    resource_rows = [
        {
            "descriptionurl": f"https://example.invalid/wiki/File:Safe-{index}.png",
            "download_status": "not_downloaded",
            "height": 1,
            "local_relpath": f"media/safe-{index}.png",
            "mime": "image/png",
            "name": f"safe-{index}.png",
            "sha1": active_media_row["sha1"],
            "seen_at": "2026-07-30T00:00:00Z",
            "site": "huijiwiki.com",
            "size": 123 + index,
            "source": "api:imageinfo",
            "timestamp": "2026-07-30T00:00:00Z",
            "title": f"File:Safe-{index}.png",
            "url": f"https://example.invalid/media/safe-{index}.png",
            "width": 1,
        }
        for index, active_media_row in enumerate(active_media_rows)
    ]
    resource_rows.append(
        {
            "descriptionurl": "https://example.invalid/wiki/File:Unrelated.bin",
            "download_status": "not_downloaded",
            "height": 0,
            "local_relpath": "media/unrelated.bin",
            "mime": "application/octet-stream",
            "name": "unrelated.bin",
            "sha1": "f" * 40,
            "seen_at": "2026-07-30T00:00:00Z",
            "site": "huijiwiki.com",
            "size": 987,
            "source": "api:imageinfo",
            "timestamp": "2026-07-30T00:00:00Z",
            "title": "File:Unrelated.bin",
            "url": "https://example.invalid/media/unrelated.bin",
            "width": 0,
        }
    )
    local_media_raw = b"local media bytes must never be read\n"
    resource_rows[0] = {
        **resource_rows[0],
        "name": "arbitrary-resource.dat",
        "title": "File:Arbitrary resource.dat",
        "local_relpath": "media/arbitrary-resource.dat",
    }
    for candidate_media_row in candidate_media_rows:
        if candidate_media_row["source_sha1"] == resource_rows[0]["sha1"]:
            if candidate_media_row["size"] == resource_rows[0]["size"]:
                candidate_media_row["filename"] = resource_rows[0]["name"]
    local_media_path = evidence / "crawler" / str(resource_rows[0]["local_relpath"])
    local_media_path.parent.mkdir(parents=True)
    local_media_path.write_bytes(local_media_raw)

    inputs: dict[str, dict[str, object]] = {
        "active_parents": _write_jsonl(evidence / "active-parents.jsonl", [active_parent]),
        "active_children": _write_jsonl(
            evidence / "active-children.jsonl",
            [active_child, _active_non_story_child()],
        ),
        "active_excluded": _write_jsonl(evidence / "active-excluded.jsonl", []),
        "active_child_bm25": _write_json(
            evidence / "active-child-bm25.json", {"records": []}
        ),
        "active_media_bm25": _write_json(
            evidence / "active-media-bm25.json", {"records": []}
        ),
        "candidate_parents": _write_jsonl(
            evidence / "candidate-parents.jsonl", [candidate_parent]
        ),
        "candidate_children": _write_jsonl(
            evidence / "candidate-children.jsonl", candidate_children
        ),
        "active_media": _write_jsonl(
            evidence / "active-media.jsonl", active_media_rows
        ),
        "candidate_media_v3": _write_jsonl(
            evidence / "candidate-media.v3.jsonl", candidate_media_rows
        ),
        "resource_metadata": _write_jsonl(
            evidence / "crawler" / "resources_manifest.jsonl",
            resource_rows,
        ),
    }
    inputs["c8b_story_ledger"] = _write_jsonl(
        evidence / "fidelity-ledger.c8b.jsonl",
        [_story_ledger_row(), _non_story_ledger_row()],
    )
    taxonomy = _c8c_taxonomy(active_media_rows)
    inputs["c8b_taxonomy"] = _write_json(
        evidence / "taxonomy.c8b3.v1.json",
        {
            "schema_version": "huiji.task8-c8b-story-legacy-taxonomy/v1",
            "decision_matrix": {},
            "dynamic_counts": {},
            "inputs": {},
            "mode": "read_only",
            "one_to_one_migration_pair_audit": {},
            "policy_selection": {},
            "run": {"run_id": "task8-c-20260729T161119Z"},
            "stage_metrics": {},
            "status": "accepted",
            "story_record_link_evidence": {
                "parent": {
                    "candidate_count": 1,
                    "missing_record_link_count": 1,
                    "new_source_record_link_count": 1,
                    "source_ref_complete_count": 1,
                },
                "child": {
                    "candidate_count": 2,
                    "missing_record_link_count": 2,
                    "new_source_record_link_count": 2,
                    "source_ref_complete_count": 2,
                    "stable_source_token_kind_counts": {"json_path": 2},
                },
                "missing_record_link_causes": [
                    {
                        "observed_behavior": "record_link_not_emitted",
                        "record_kind": "parent",
                        "source_function": "project_story_parent",
                        "source_stage": "data_projection",
                    },
                    {
                        "observed_behavior": "record_link_not_emitted",
                        "record_kind": "child",
                        "source_function": "project_story_steps",
                        "source_stage": "data_projection",
                    },
                    {
                        "observed_behavior": "record_link_not_emitted",
                        "record_kind": "child",
                        "source_function": "compose_corpus_projection",
                        "source_stage": "composed_projection",
                    },
                ],
            },
            "safety": {"protected_identity_count": 32, "protected_drift_count": 0},
            "samples": {},
            "taxonomy": {},
        },
    )
    c8b_taxonomy_identity = inputs["c8b_taxonomy"]
    c8b_manifest_witnesses = (
        (
            "taxonomy.py",
            _write_bytes(
                evidence / "taxonomy.py",
                b"# pinned C8b taxonomy diagnostic fixture\n",
            ),
        ),
        (
            "protected_pre.c8b3.v1.json",
            _write_json(
                evidence / "protected_pre.c8b3.v1.json",
                {"fixture": "pinned C8b protected state"},
            ),
        ),
        ("taxonomy.c8b3.v1.json", c8b_taxonomy_identity),
        (
            "protected_post.c8b3.v1.json",
            _write_json(
                evidence / "protected_post.c8b3.v1.json",
                {"fixture": "pinned C8b protected state"},
            ),
        ),
        (
            "protected_compare.c8b3.v1.json",
            _write_json(
                evidence / "protected_compare.c8b3.v1.json",
                {"protected_drift_count": 0, "protected_identity_count": 32},
            ),
        ),
    )
    c8b_manifest_files = [
        {
            "basename": basename,
            "label": basename,
            "mtime_ns": Path(identity["path"]).stat().st_mtime_ns,
            "sha256": identity["sha256"],
            "size": identity["size_bytes"],
        }
        for basename, identity in c8b_manifest_witnesses
    ]
    _write_json(
        evidence / "manifest.c8b3.v1.json",
        {
            "checkpoint_commit": C8A_COMMIT,
            "files": c8b_manifest_files,
            "protected_drift_count": 0,
            "protected_identity_count": 32,
            "run_id": "task8-c-20260729T161119Z",
            "schema_version": "huiji.task8-c8b-evidence-manifest/v1",
            "status": "completed_pending_review",
        },
    )
    inputs["c8c_taxonomy"] = _write_json(
        evidence / "taxonomy.c8c-legacy-media.v1.json", taxonomy
    )
    protected_rows = []
    for index in range(32):
        protected_path = evidence / "protected-targets" / f"target-{index:02d}.txt"
        protected_raw = f"protected target {index:02d}\n".encode()
        protected_path.parent.mkdir(parents=True, exist_ok=True)
        protected_path.write_bytes(protected_raw)
        stat = protected_path.stat()
        protected_rows.append(
            {
                "label": f"protected_target_{index:02d}",
                "path": protected_path.as_posix(),
                "sha256": _sha256(protected_raw),
                "size": len(protected_raw),
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    inputs["protected_identity_manifest"] = _write_json(
        evidence / "protected_pre.v1.json",
        {
            "schema_version": "huiji.task8-protected-state/v1",
            "records": protected_rows,
        },
    )

    for filename in CRAWLER_SOURCES[:3]:
        label = f"crawler_{Path(filename).stem}"
        inputs[label] = _write_jsonl(
            evidence / "crawler" / filename,
            [{"title": filename, "content_sha256": _hashed(filename)}],
        )
    # These two C8d labels are one pinned C8c/raw-crawler fact, not two
    # independently editable resource manifests.
    inputs["crawler_resources_manifest"] = inputs["resource_metadata"]

    c8b_receipt = evidence / "d-acceptance-c8b.json"
    c8b_receipt.write_bytes(_approved_receipt_bytes(C8B_RECEIPT_DEFLATE_BASE64))
    c8c_receipt = evidence / "d-accept-c8c-final.json"
    c8c_receipt.write_bytes(_approved_receipt_bytes(C8C_RECEIPT_DEFLATE_BASE64))
    assert _sha256(c8b_receipt.read_bytes()) == C8B_RECEIPT_SHA256
    assert _sha256(c8c_receipt.read_bytes()) == C8C_RECEIPT_SHA256
    accepted_checkpoints = {
        "task7_c8a_commit": C8A_COMMIT,
        "c8b_commit": C8B_COMMIT,
        "c8b_d_acceptance": {
            "path": c8b_receipt.as_posix(),
            "sha256": C8B_RECEIPT_SHA256,
            "size_bytes": c8b_receipt.stat().st_size,
        },
        "c8c_commit": C8C_COMMIT,
        "c8c_d_acceptance": {
            "path": c8c_receipt.as_posix(),
            "sha256": C8C_RECEIPT_SHA256,
            "size_bytes": c8c_receipt.stat().st_size,
        },
    }
    parity_status = "c8c_real_snapshot_product_parity_pending_d_review"
    parity_forbidden_counters = {
        "activation_calls": 0,
        "active_pointer_changes": 0,
        "media_download_calls": 0,
        "milvus_calls": 0,
        "minio_calls": 0,
        "mysql_calls": 0,
        "network_calls": 0,
        "production_writes": 0,
        "subprocess_calls": 0,
        "vector_rebuild_calls": 0,
        "writes_outside_run_directory": 0,
    }
    accepted_taxonomy_rows_sha256 = _sha256(
        _canonical_bytes(taxonomy["rows"])
    )
    product_ledger_sha256 = _sha256(
        _canonical_json_bytes(
            {
                "evidence_class": "product-occurrence-ledger",
                "accepted_taxonomy_rows_sha256": (
                    accepted_taxonomy_rows_sha256
                ),
                "run_id": "task8-c-product-parity-20260730T190741Z",
            },
            trailing_newline=False,
        )
    )
    assert product_ledger_sha256 != accepted_taxonomy_rows_sha256
    product_summary = {
        "schema_version": "huiji.c8c-product-parity-summary/v1",
        "run_id": "task8-c-product-parity-20260730T190741Z",
        "head": C8B_COMMIT,
        "tree": "d612af9038026eb7b01ebccb5b5f3e22b04ddffd",
        "status": parity_status,
        "accepted_taxonomy": {
            "active_occurrence_count": 6,
            "category_counts": taxonomy["category_counts"],
            "unexplained_binding_loss": 6,
        },
        "active_occurrence_count": 6,
        "category_counts": taxonomy["category_counts"],
        "elapsed_seconds": 0.0,
        "fidelity": {
            "blocker_prefix_counts": {
                "legacy_media_ambiguous_binding": 1,
                "legacy_media_conflicting_binding": 1,
                "legacy_media_missing_local_bytes": 1,
                "unexplained_binding_loss": 1,
            },
            "legacy_media_blocker_counts": {
                "legacy_media_ambiguous_binding:2": 1,
                "legacy_media_conflicting_binding:1": 1,
                "legacy_media_missing_local_bytes:3": 1,
                "legacy_media_missing_resource_metadata:0": 0,
                "unexplained_binding_loss:6": 1,
            },
            "non_media_blocker_prefix_counts": {},
            "returned": True,
            "unexplained_binding_loss": 6,
        },
        "forbidden_action_counters": parity_forbidden_counters,
        "observed_audit_events": {
            "loopback_capability_probe_binds": 0,
            "socket_capability_probe_constructors": 0,
        },
        "parity": {
            "active_occurrence_count_equal": True,
            "all_seven_category_counts_equal": True,
            "unexplained_binding_loss_equal": True,
        },
        "peak_rss_bytes": 0,
        "product_interface": (
            "src.huiji_rag.build.media_v3.reconcile_active_media_occurrences"
        ),
        "product_occurrence_ledger_sha256": product_ledger_sha256,
        "protected_state": {
            "identity_count": 32,
            "drift_count": 0,
            "state_sha256_pre": _hashed("protected-state"),
            "state_sha256_post": _hashed("protected-state"),
        },
        "stage_elapsed_seconds": {
            "compose_projection": 0.0,
            "data_projection": 0.0,
            "load_accepted_taxonomy": 0.0,
            "load_active_baseline": 0.0,
            "load_active_media": 0.0,
            "load_candidate_media": 0.0,
            "load_fidelity_active_rows": 0.0,
            "page_projection": 0.0,
            "page_revision_join": 0.0,
            "preflight_input_hashing": 0.0,
            "resource_manifest_projection": 0.0,
            "tracked_fidelity_ledger": 0.0,
            "tracked_media_reconciliation": 0.0,
        },
        "unexplained_binding_loss": 6,
    }
    product_summary_ref = _write_json(
        evidence / "summary.product-parity.v1.json", product_summary
    )
    product_diagnostic_path = evidence / "diagnostic.product-parity.py"
    product_diagnostic_path.write_bytes(b"# frozen product parity diagnostic\n")
    product_diagnostic_sha256 = _sha256(product_diagnostic_path.read_bytes())
    accepted_baseline_witness = _write_json(
        repository
        / "eval/huiji_corpus_fidelity/20260720T073917Z/corpus-preservation-baseline.v2.json",
        {
            "schema_version": "huiji.corpus-preservation-baseline/v2",
            "status": "pass",
            "active_artifacts": {
                "files": {
                    filename: {
                        "path": Path(inputs[label]["path"])
                        .relative_to(repository)
                        .as_posix(),
                        "sha256": inputs[label]["sha256"],
                        "size": inputs[label]["size_bytes"],
                    }
                    for filename, label in (
                        ("parent_blocks.jsonl", "active_parents"),
                        ("child_blocks.jsonl", "active_children"),
                        ("excluded_entities.jsonl", "active_excluded"),
                        ("media_assets.jsonl", "active_media"),
                        ("child_text_bm25.json", "active_child_bm25"),
                        ("media_asset_bm25.json", "active_media_bm25"),
                    )
                }
            },
        },
    )
    c8c_review_witnesses = (
        _write_json(
            repository
            / ".codex-supervisor/workers/C/d-review-c8c-real-interface-accepted.json",
            {
                "schema_version": "fixture.c8c-real-interface-review/v1",
                "status": "accepted",
            },
        ),
        _write_json(
            repository
            / ".codex-supervisor/workers/C/d-review-c8c-final-43-green.json",
            {
                "schema_version": "fixture.c8c-green-review/v1",
                "status": "accepted",
            },
        ),
    )
    reviewed_file_paths = (
        "src/huiji_rag/build/media_v3.py",
        "src/huiji_rag/build/fidelity.py",
        "src/huiji_rag/build/orchestrator.py",
        "tests/test_huiji_media_v3_builder.py",
        "tests/test_huiji_corpus_fidelity.py",
        "docs/superpowers/specs/2026-07-29-rag-thread-c-legacy-media-decision.md",
    )
    reviewed_file_witnesses = tuple(
        _write_bytes(
            repository / relative_path,
            f"pinned C8c reviewed fixture: {relative_path}\n".encode("utf-8"),
        )
        for relative_path in reviewed_file_paths
    )
    # Preserve the accepted C8c product-manifest sequence as a list and bind
    # every witness explicitly to the corresponding C8d fixture identity.
    manifest_witnesses = (
        ("d_acceptance_receipt", c8c_review_witnesses[0]),
        ("d_green_review_receipt", c8c_review_witnesses[1]),
        ("legacy_active_media", inputs["active_media"]),
        ("accepted_taxonomy", inputs["c8c_taxonomy"]),
        ("candidate_media_v3", inputs["candidate_media_v3"]),
        ("accepted_baseline", accepted_baseline_witness),
        ("protected_identity_manifest", inputs["protected_identity_manifest"]),
        ("pages", inputs["crawler_pages"]),
        ("wikitext", inputs["crawler_wikitext"]),
        ("data_pages", inputs["crawler_data_pages"]),
        ("resources_manifest", inputs["crawler_resources_manifest"]),
        *(("reviewed_file", identity) for identity in reviewed_file_witnesses),
    )
    product_manifest_inputs = [
        {
            "identity": Path(identity["path"]).relative_to(repository).as_posix(),
            "label": label,
            "row_count": identity.get("row_count"),
            "sha256": identity["sha256"],
            "size": identity["size_bytes"],
        }
        for label, identity in manifest_witnesses
    ]
    product_manifest = {
        "schema_version": "huiji.c8c-product-parity-manifest/v1",
        "run_id": product_summary["run_id"],
        "head": product_summary["head"],
        "tree": product_summary["tree"],
        "status": parity_status,
        "diagnostic_script_sha256": product_diagnostic_sha256,
        "forbidden_action_counters": parity_forbidden_counters,
        "inputs": product_manifest_inputs,
        "interpreter": {
            "identity": "conda:1999wiki/python.exe",
            "version": "3.11.15",
        },
        "outputs": {
            "summary.product-parity.v1.json": product_summary_ref["sha256"]
        },
        "protected_identity_count": 32,
        "protected_drift_count": 0,
    }
    product_manifest_ref = _write_json(
        evidence / "manifest.product-parity.v1.json", product_manifest
    )
    product_receipt = {
        "schema_version": "huiji.c8c-product-parity-receipt/v1",
        "run_id": product_summary["run_id"],
        "head": product_summary["head"],
        "tree": product_summary["tree"],
        "status": parity_status,
        "active_occurrence_count": 6,
        "category_counts": taxonomy["category_counts"],
        "commit_created": False,
        "forbidden_action_counters": parity_forbidden_counters,
        "output_sha256": {
            "diagnostic.product-parity.py": product_manifest[
                "diagnostic_script_sha256"
            ],
            "manifest.product-parity.v1.json": product_manifest_ref["sha256"],
            "summary.product-parity.v1.json": product_summary_ref["sha256"],
        },
        "protected_identity_count": 32,
        "protected_drift_count": 0,
        "staged_path_count": 0,
        "tracked_files_modified": False,
        "unexplained_binding_loss": 6,
    }
    product_receipt_ref = _write_json(
        evidence / "receipt.product-parity.v1.json", product_receipt
    )
    inputs.update(
        {
            "c8c_product_manifest": product_manifest_ref,
            "c8c_product_summary": product_summary_ref,
            "c8c_product_receipt": product_receipt_ref,
        }
    )

    diagnostic_path = repository / SCRIPT_RELATIVE_PATH
    diagnostic_path.parent.mkdir(parents=True)
    diagnostic_path.write_bytes(SCRIPT_BYTES)
    config: dict[str, object] = {
        "schema_version": "huiji.c8d-fidelity-run-config/v1",
        "run_id": RUN_ID,
        "repository_root": repository.as_posix(),
        "output_root": output_root.as_posix(),
        "expected_git_head": HEAD,
        "expected_git_tree": TREE,
        "diagnostic": {
            "path": SCRIPT_RELATIVE_PATH,
            "sha256": SCRIPT_SHA256,
        },
        "accepted_checkpoints": accepted_checkpoints,
        "expected_output_files": list(OUTPUT_NAMES),
        "sample_limit_per_blocker_prefix": 5,
        "expected_protected_identity_count": 32,
        "expected_protected_drift_count": 0,
        "expected_legacy_media_category_counts": MEDIA_COUNTS,
        "inputs": inputs,
        "c8c_evidence_chain": {
            "manifest_sha256": product_manifest_ref["sha256"],
            "summary_sha256": product_summary_ref["sha256"],
            "receipt_sha256": product_receipt_ref["sha256"],
            "occurrence_ledger_sha256": product_summary[
                "product_occurrence_ledger_sha256"
            ],
        },
    }
    config_path = tmp_path / "run-config.c8d.json"
    config_raw = _canonical_bytes(config)
    config_path.write_bytes(config_raw)
    return config_path, _sha256(config_raw), output_root, config


def _test_evidence_fixture() -> SimpleNamespace:
    return SimpleNamespace(
        data_projection=SimpleNamespace(
            parents=(),
            children=(),
            exclusions=(),
            record_links=(),
            voice_sources=(),
            media_intents=(),
            identity_fallbacks=(),
        ),
        page_projection=SimpleNamespace(
            parents=(),
            children=(),
            pages=(),
            sections=(),
            diagnostics=(),
            exclusions=(),
            media_intents=(),
        ),
        topic_projection=SimpleNamespace(
            parents=(),
            children=(),
            diagnostics=(),
            catalog_fingerprint_sha256="0" * 64,
        ),
        active_parent_rows=(_active_parent(),),
        active_child_rows=(_active_child(), _active_non_story_child()),
        active_excluded_rows=(),
        active_child_bm25_records=(),
        active_media_bm25_records=(),
        candidate_parent_rows=(_candidate_parent(),),
        candidate_child_rows=(
            _candidate_child(0),
            _candidate_child(1),
            _candidate_non_story_child(),
        ),
        story_ledger_rows=(_story_ledger_row(), _non_story_ledger_row()),
        legacy_media=SimpleNamespace(
            occurrence_rows=tuple(
                SimpleNamespace(
                    occurrence_id="legacy-occurrence:sha256:"
                    + f"{index + 1:x}" * 64,
                    category=category,
                )
                for index, category in enumerate(
                    (
                        "ambiguous_binding",
                        "ambiguous_binding",
                        "conflicting_binding",
                        "missing_local_bytes",
                        "missing_local_bytes",
                        "missing_local_bytes",
                    )
                )
            ),
            category_counts=MEDIA_COUNTS,
            unexplained_binding_loss=6,
            active_occurrence_count=6,
        ),
    )


def _fidelity_result() -> SimpleNamespace:
    return SimpleNamespace(
        passed=False,
        blockers=(
            "blocked_ambiguous_child:1",
            "blocked_ambiguous_child:1",
            "blocked_ambiguous_parent:1",
            "legacy_media_ambiguous_binding:2",
            "legacy_media_conflicting_binding:1",
            "legacy_media_missing_local_bytes:3",
            "unexplained_binding_loss:6",
            "unexplained_child_missing:1",
            "unexplained_parent_child_loss:1",
            "unexplained_parent_missing:1",
        ),
        category_counts={"blocked_ambiguous": 2},
        unexplained_parent_child_loss=1,
        unexplained_binding_loss=6,
        ledger_rows=(_story_ledger_row(), _non_story_ledger_row()),
        build_diff={},
    )


def _invoke(module: Any, config_path: Path, digest: str, output_root: Path) -> Any:
    return module.run_diagnostic(
        config_path,
        expected_run_config_sha256=digest,
        output_root=output_root,
    )


def _assert_no_output(output_root: Path) -> None:
    assert not output_root.exists() or not tuple(output_root.iterdir())


def test_cli_requires_hash_pinned_run_config_and_exact_identity_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    config_path, digest, output_root, config = _run_config(tmp_path)
    calls: list[tuple[Path, str, Path]] = []

    def capture(path: Path, *, expected_run_config_sha256: str, output_root: Path):
        calls.append((Path(path), expected_run_config_sha256, Path(output_root)))

    monkeypatch.setattr(module, "run_diagnostic", capture)
    argv = [
        "--run-config",
        str(config_path),
        "--expected-run-config-sha256",
        digest,
        "--output-root",
        str(output_root),
    ]
    assert module.main(argv) == 0
    assert calls == [(config_path, digest, output_root)]

    invalid_argv = (
        [],
        ["--run-config", str(config_path)],
        [
            "--run-config",
            str(config_path),
            "--expected-run-config-sha256",
            digest,
        ],
        [
            "--run-config",
            str(config_path),
            "--output-root",
            str(output_root),
        ],
        [
            "--run-config",
            str(config_path),
            "--expected-run-config-sha256",
            "not-a-sha256",
            "--output-root",
            str(output_root),
        ],
        [
            "--run-config",
            str(config_path),
            "--expected-run-config-sha256",
            "0" * 64,
            "--output-root",
            str(output_root),
        ],
    )
    for invalid in invalid_argv:
        with pytest.raises((SystemExit, RuntimeError, ValueError)):
            module.main(list(invalid))
        _assert_no_output(output_root)
    assert calls == [(config_path, digest, output_root)]

    verified = {
        label: (Path(identity["path"]), Path(identity["path"]).read_bytes())
        for label, identity in config["inputs"].items()
    }
    taxonomy = json.loads(verified["c8c_taxonomy"][1])
    active_media_rows = [
        json.loads(line)
        for line in verified["active_media"][1].decode("utf-8").splitlines()
    ]
    assert {
        row["legacy_row_sha256"] for row in taxonomy["rows"]
    } == {
        _sha256(
            _canonical_json_bytes(row, trailing_newline=False)
        )
        for row in active_media_rows
    }
    assert all(
        row["legacy_row_sha256"]
        != _sha256(_canonical_bytes(active))
        for row, active in zip(
            taxonomy["rows"], active_media_rows, strict=True
        )
    )
    assert set(taxonomy["coverage_checks"]) == {
        "all_categories_known",
        "category_sum_equals_active_occurrence_count",
        "each_active_occurrence_exactly_once",
        "incomplete_evidence_explicit_count",
        "potential_candidate_collision_count",
        "proven_candidate_consumption_collision_count",
    }
    assert set(taxonomy["duplicate_consumption_checks"]) == {
        "bounded_collision_samples",
        "duplicate_active_occurrence_id_count",
        "potential_candidate_collision_count",
        "proven_candidate_consumption_collision_count",
    }
    assert set(taxonomy["population_cross_check"]) == {
        "accepted_baseline",
        "accepted_fidelity_active_occurrences",
        "accepted_fidelity_unexplained_binding_loss",
        "legacy_jsonl",
        "pinned_expected_result",
    }
    assert set(taxonomy["population_cross_check"].values()) == {
        len(active_media_rows)
    }
    assert (
        taxonomy["coverage_checks"][
            "proven_candidate_consumption_collision_count"
        ]
        == taxonomy["duplicate_consumption_checks"][
            "proven_candidate_consumption_collision_count"
        ]
        == 0
    )
    ambiguous_rows = [
        row
        for row in taxonomy["rows"]
        if row["category"] == "ambiguous_binding"
    ]
    assert len(ambiguous_rows) == 2
    assert (
        ambiguous_rows[0]["potential_candidate_ids"]
        == ambiguous_rows[1]["potential_candidate_ids"]
    )
    candidate_media_by_id = {
        row["binding_id"]: row
        for row in (
            json.loads(line)
            for line in verified["candidate_media_v3"][1]
            .decode("utf-8")
            .splitlines()
        )
    }
    for row in taxonomy["rows"]:
        expected_source_ids = {
            _source_binding_token_id(
                candidate_media_by_id[candidate_id][
                    "source_binding_token"
                ]
            )
            for candidate_id in row["candidate_binding_ids"]
        }
        assert set(row["candidate_source_binding_token_ids"]) == (
            expected_source_ids
        )
        assert all(
            stable_id
            != candidate_media_by_id[candidate_id][
                "source_binding_token"
            ]
            for stable_id in row["candidate_source_binding_token_ids"]
            for candidate_id in row["candidate_binding_ids"]
        )

    module._validate_c8c_chain(config, verified)

    field_drift_taxonomy = copy.deepcopy(taxonomy)
    field_drift_taxonomy["coverage_checks"][
        "category_sum_matches_population"
    ] = field_drift_taxonomy["coverage_checks"].pop(
        "category_sum_equals_active_occurrence_count"
    )
    field_drift_verified = dict(verified)
    field_drift_verified["c8c_taxonomy"] = (
        verified["c8c_taxonomy"][0],
        _canonical_bytes(field_drift_taxonomy),
    )
    with pytest.raises(ValueError):
        module._validate_c8c_chain(config, field_drift_verified)

    product_chain_mismatch = copy.deepcopy(config)
    product_chain_mismatch["c8c_evidence_chain"][
        "occurrence_ledger_sha256"
    ] = "0" * 64
    with pytest.raises(ValueError, match="occurrence ledger"):
        module._validate_c8c_chain(product_chain_mismatch, verified)

    loaded = module.load_run_config(
        config_path, expected_run_config_sha256=digest, output_root=output_root
    )
    assert loaded == config
    assert C8B_EVIDENCE_MANIFEST_SHA256 == "977cde250ec88e970150ce98d97339f17555639dbcf905154ffd4c9a283e5fc0"
    assert C8B_TAXONOMY_SHA256 == "44a511ba41a7067e4536c51226c8c40603c55806653a22bde468be066ac32ecd"
    assert C8C_PRODUCT_MANIFEST_SHA256 == "dc7dc31936c8e85d6c6f3af5a10c1eeb9a70300ac9990476d8f27bb1b164e764"
    assert PROTECTED_STATE_SHA256 == "ef85f54d229e05d975092badfd734899e85c6a74d30f0cac310b8b0d0a4b355f"
    assert loaded["accepted_checkpoints"] == config["accepted_checkpoints"]
    assert set(loaded["inputs"]) >= {
        "protected_identity_manifest",
        "crawler_pages",
        "crawler_wikitext",
        "crawler_data_pages",
        "crawler_resources_manifest",
        "c8b_taxonomy",
        "c8c_taxonomy",
        "c8c_product_manifest",
        "c8c_product_summary",
        "c8c_product_receipt",
    }
    assert "c8b_story_ledger" in loaded["inputs"]
    for identity in loaded["inputs"].values():
        path = Path(identity["path"])
        raw = path.read_bytes()
        assert path.is_file()
        assert len(raw) == identity["size_bytes"]
        assert _sha256(raw) == identity["sha256"]
        if "row_count" in identity:
            assert raw.count(b"\n") == identity["row_count"]
    for name in ("c8b_d_acceptance", "c8c_d_acceptance"):
        identity = loaded["accepted_checkpoints"][name]
        raw = Path(identity["path"]).read_bytes()
        assert len(raw) == identity["size_bytes"]
        assert _sha256(raw) == identity["sha256"]
    diagnostic_path = (
        Path(loaded["repository_root"]) / loaded["diagnostic"]["path"]
    )
    assert _sha256(diagnostic_path.read_bytes()) == loaded["diagnostic"]["sha256"]
    for label in ("active_child_bm25", "active_media_bm25"):
        payload = json.loads(Path(loaded["inputs"][label]["path"]).read_bytes())
        assert set(payload) == {"records"}
        assert isinstance(payload["records"], list)
    protected = json.loads(
        Path(loaded["inputs"]["protected_identity_manifest"]["path"]).read_bytes()
    )
    assert protected["schema_version"] == "huiji.task8-protected-state/v1"
    assert len(protected["records"]) == 32
    assert all(
        set(record) == {"label", "path", "sha256", "size", "mtime_ns"}
        for record in protected["records"]
    )
    c8b_taxonomy = json.loads(
        Path(loaded["inputs"]["c8b_taxonomy"]["path"]).read_bytes()
    )
    assert set(c8b_taxonomy) == {
        "decision_matrix",
        "dynamic_counts",
        "inputs",
        "mode",
        "one_to_one_migration_pair_audit",
        "policy_selection",
        "run",
        "safety",
        "samples",
        "schema_version",
        "stage_metrics",
        "status",
        "story_record_link_evidence",
        "taxonomy",
    }
    assert c8b_taxonomy["schema_version"] == (
        "huiji.task8-c8b-story-legacy-taxonomy/v1"
    )
    assert set(c8b_taxonomy["story_record_link_evidence"]) == {
        "parent",
        "child",
        "missing_record_link_causes",
    }
    assert set(c8b_taxonomy["story_record_link_evidence"]["parent"]) == {
        "candidate_count",
        "missing_record_link_count",
        "new_source_record_link_count",
        "source_ref_complete_count",
    }
    assert set(c8b_taxonomy["story_record_link_evidence"]["child"]) == {
        "candidate_count",
        "missing_record_link_count",
        "new_source_record_link_count",
        "source_ref_complete_count",
        "stable_source_token_kind_counts",
    }
    missing_causes = c8b_taxonomy["story_record_link_evidence"][
        "missing_record_link_causes"
    ]
    assert isinstance(missing_causes, list) and len(missing_causes) == 3
    assert all(
        set(row)
        == {"observed_behavior", "record_kind", "source_function", "source_stage"}
        for row in missing_causes
    )
    assert "ledger_id" not in json.dumps(c8b_taxonomy)
    c8b_manifest_path = Path(loaded["inputs"]["c8b_taxonomy"]["path"]).with_name(
        "manifest.c8b3.v1.json"
    )
    c8b_manifest = json.loads(c8b_manifest_path.read_bytes())
    assert set(c8b_manifest) == {
        "checkpoint_commit",
        "files",
        "protected_drift_count",
        "protected_identity_count",
        "run_id",
        "schema_version",
        "status",
    }
    assert c8b_manifest["schema_version"] == "huiji.task8-c8b-evidence-manifest/v1"
    assert c8b_manifest["checkpoint_commit"] == C8A_COMMIT
    assert c8b_manifest["run_id"] == "task8-c-20260729T161119Z"
    assert c8b_manifest["status"] == "completed_pending_review"
    assert c8b_manifest["protected_identity_count"] == 32
    assert c8b_manifest["protected_drift_count"] == 0
    assert isinstance(c8b_manifest["files"], list)
    assert [entry["basename"] for entry in c8b_manifest["files"]] == [
        "taxonomy.py",
        "protected_pre.c8b3.v1.json",
        "taxonomy.c8b3.v1.json",
        "protected_post.c8b3.v1.json",
        "protected_compare.c8b3.v1.json",
    ]
    assert all(
        set(entry) == {"basename", "label", "mtime_ns", "sha256", "size"}
        for entry in c8b_manifest["files"]
    )
    for entry in c8b_manifest["files"]:
        witness_path = c8b_manifest_path.with_name(entry["basename"])
        witness_raw = witness_path.read_bytes()
        assert witness_path.stat().st_mtime_ns == entry["mtime_ns"]
        assert _sha256(witness_raw) == entry["sha256"]
        assert len(witness_raw) == entry["size"]
    taxonomy_entries = [
        entry
        for entry in c8b_manifest["files"]
        if entry["basename"] == entry["label"] == "taxonomy.c8b3.v1.json"
    ]
    assert taxonomy_entries == [{
        "basename": "taxonomy.c8b3.v1.json",
        "label": "taxonomy.c8b3.v1.json",
        "mtime_ns": Path(loaded["inputs"]["c8b_taxonomy"]["path"]).stat().st_mtime_ns,
        "sha256": loaded["inputs"]["c8b_taxonomy"]["sha256"],
        "size": loaded["inputs"]["c8b_taxonomy"]["size_bytes"],
    }]
    story_ledger_rows = [
        json.loads(line)
        for line in Path(loaded["inputs"]["c8b_story_ledger"]["path"])
        .read_text()
        .splitlines()
    ]
    assert story_ledger_rows[0]["source_evidence"] == _story_ledger_row()[
        "source_evidence"
    ]
    assert story_ledger_rows[1]["active_identity"] == _active_non_story_child()[
        "record_id"
    ]
    assert story_ledger_rows[1]["candidate_identities"] == [
        _candidate_non_story_child()["record_id"]
    ]

    resource_identity = loaded["inputs"]["resource_metadata"]
    assert resource_identity == loaded["inputs"]["crawler_resources_manifest"]
    resource_rows = [
        json.loads(line)
        for line in Path(resource_identity["path"]).read_text().splitlines()
    ]
    assert all(
        set(row)
        == {
            "descriptionurl",
            "download_status",
            "height",
            "local_relpath",
            "mime",
            "name",
            "seen_at",
            "sha1",
            "site",
            "size",
            "source",
            "timestamp",
            "title",
            "url",
            "width",
        }
        for row in resource_rows
    )
    candidate_media_rows = [
        json.loads(line)
        for line in Path(loaded["inputs"]["candidate_media_v3"]["path"])
        .read_text()
        .splitlines()
    ]
    required_media_fields = {
        "binding_id",
        "resource_id",
        "source_sha1",
        "content_sha256",
        "content_hash",
        "size",
        "filename",
        "title",
    }
    assert all(required_media_fields <= set(row) for row in candidate_media_rows)
    forbidden_resource_fields = {
        "resource_sha1",
        "resource_sha256",
        "resource_size",
        "size_bytes",
    }
    assert all(not forbidden_resource_fields.intersection(row) for row in candidate_media_rows)
    assert all("resource_id" not in row for row in resource_rows)
    candidate_resource_matches = {
        candidate["binding_id"]: [
            resource
            for resource in resource_rows
            if (
                candidate["source_sha1"],
                candidate["filename"],
                candidate["size"],
            )
            == (
                resource["sha1"],
                resource["name"],
                resource["size"],
            )
        ]
        for candidate in candidate_media_rows
    }
    assert all(
        len(matches) == 1
        for matches in candidate_resource_matches.values()
    )
    assert all(
        candidate["title"]
        != candidate_resource_matches[candidate["binding_id"]][0][
            "title"
        ]
        for candidate in candidate_media_rows
    )
    assert {
        row["sha1"] for row in resource_rows
    } > {
        row["source_sha1"] for row in candidate_media_rows
    }
    repeated_sha1_resources = [
        row
        for row in resource_rows
        if row["sha1"] == candidate_media_rows[0]["source_sha1"]
    ]
    assert len(repeated_sha1_resources) == 2
    assert len(
        {
            (row["name"], row["size"])
            for row in repeated_sha1_resources
        }
    ) == 2

    product_manifest = json.loads(
        Path(loaded["inputs"]["c8c_product_manifest"]["path"]).read_bytes()
    )
    product_summary_path = Path(
        loaded["inputs"]["c8c_product_summary"]["path"]
    )
    product_summary = json.loads(product_summary_path.read_bytes())
    product_receipt = json.loads(
        Path(loaded["inputs"]["c8c_product_receipt"]["path"]).read_bytes()
    )
    c8c_taxonomy = json.loads(
        Path(loaded["inputs"]["c8c_taxonomy"]["path"]).read_bytes()
    )
    assert c8c_taxonomy["active_occurrence_count"] == len(c8c_taxonomy["rows"]) == 6
    assert sum(c8c_taxonomy["category_counts"].values()) == 6
    assert c8c_taxonomy["category_counts"] == MEDIA_COUNTS
    assert product_summary["accepted_taxonomy"] == {
        "active_occurrence_count": 6,
        "category_counts": MEDIA_COUNTS,
        "unexplained_binding_loss": 6,
    }
    assert set(product_manifest) == {
        "diagnostic_script_sha256",
        "forbidden_action_counters",
        "head",
        "inputs",
        "interpreter",
        "outputs",
        "protected_drift_count",
        "protected_identity_count",
        "run_id",
        "schema_version",
        "status",
        "tree",
    }
    assert all(
        set(identity) == {"identity", "label", "row_count", "sha256", "size"}
        for identity in product_manifest["inputs"]
    )
    assert [entry["label"] for entry in product_manifest["inputs"]] == [
        "d_acceptance_receipt",
        "d_green_review_receipt",
        "legacy_active_media",
        "accepted_taxonomy",
        "candidate_media_v3",
        "accepted_baseline",
        "protected_identity_manifest",
        "pages",
        "wikitext",
        "data_pages",
        "resources_manifest",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
    ]
    accepted_baseline_entry = next(
        entry
        for entry in product_manifest["inputs"]
        if entry["label"] == "accepted_baseline"
    )
    assert accepted_baseline_entry["identity"] == (
        "eval/huiji_corpus_fidelity/20260720T073917Z/"
        "corpus-preservation-baseline.v2.json"
    )
    accepted_baseline_path = (
        Path(loaded["repository_root"]) / accepted_baseline_entry["identity"]
    )
    bm25_identities = tuple(
        loaded["inputs"][label]
        for label in ("active_child_bm25", "active_media_bm25")
    )
    assert all(
        accepted_baseline_entry["identity"]
        != Path(identity["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix()
        for identity in bm25_identities
    )
    assert all(
        accepted_baseline_path != Path(identity["path"])
        for identity in bm25_identities
    )
    assert all(
        accepted_baseline_entry["sha256"] != identity["sha256"]
        for identity in bm25_identities
    )
    accepted_baseline_payload = json.loads(accepted_baseline_path.read_bytes())
    assert accepted_baseline_payload["schema_version"] == (
        "huiji.corpus-preservation-baseline/v2"
    )
    assert accepted_baseline_payload["status"] == "pass"
    assert [entry["identity"] for entry in product_manifest["inputs"]] == [
        ".codex-supervisor/workers/C/d-review-c8c-real-interface-accepted.json",
        ".codex-supervisor/workers/C/d-review-c8c-final-43-green.json",
        Path(loaded["inputs"]["active_media"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["c8c_taxonomy"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["candidate_media_v3"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        "eval/huiji_corpus_fidelity/20260720T073917Z/"
        "corpus-preservation-baseline.v2.json",
        Path(loaded["inputs"]["protected_identity_manifest"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_pages"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_wikitext"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_data_pages"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_resources_manifest"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        "src/huiji_rag/build/media_v3.py",
        "src/huiji_rag/build/fidelity.py",
        "src/huiji_rag/build/orchestrator.py",
        "tests/test_huiji_media_v3_builder.py",
        "tests/test_huiji_corpus_fidelity.py",
        "docs/superpowers/specs/2026-07-29-rag-thread-c-legacy-media-decision.md",
    ]
    for entry in product_manifest["inputs"]:
        witness_raw = (Path(loaded["repository_root"]) / entry["identity"]).read_bytes()
        assert _sha256(witness_raw) == entry["sha256"]
        assert len(witness_raw) == entry["size"]
    assert len(product_manifest["inputs"]) == len(
        {entry["identity"] for entry in product_manifest["inputs"]}
    )
    assert set(product_summary) == {
        "accepted_taxonomy",
        "active_occurrence_count",
        "category_counts",
        "elapsed_seconds",
        "fidelity",
        "forbidden_action_counters",
        "head",
        "observed_audit_events",
        "parity",
        "peak_rss_bytes",
        "product_interface",
        "product_occurrence_ledger_sha256",
        "protected_state",
        "run_id",
        "schema_version",
        "stage_elapsed_seconds",
        "status",
        "tree",
        "unexplained_binding_loss",
    }
    assert set(product_receipt) == {
        "active_occurrence_count",
        "category_counts",
        "commit_created",
        "forbidden_action_counters",
        "head",
        "output_sha256",
        "protected_drift_count",
        "protected_identity_count",
        "run_id",
        "schema_version",
        "staged_path_count",
        "status",
        "tracked_files_modified",
        "tree",
        "unexplained_binding_loss",
    }
    assert (
        product_manifest["outputs"]["summary.product-parity.v1.json"]
        == _sha256(product_summary_path.read_bytes())
        == product_receipt["output_sha256"]["summary.product-parity.v1.json"]
    )
    product_manifest_path = Path(
        loaded["inputs"]["c8c_product_manifest"]["path"]
    )
    assert (
        product_receipt["output_sha256"]["manifest.product-parity.v1.json"]
        == _sha256(product_manifest_path.read_bytes())
    )
    product_diagnostic_path = product_manifest_path.with_name(
        "diagnostic.product-parity.py"
    )
    assert (
        product_manifest["diagnostic_script_sha256"]
        == _sha256(product_diagnostic_path.read_bytes())
        == product_receipt["output_sha256"]["diagnostic.product-parity.py"]
    )
    assert product_manifest["run_id"] == product_summary["run_id"]
    assert product_manifest["run_id"] == product_receipt["run_id"]
    assert product_manifest["head"] == product_summary["head"] == product_receipt["head"]
    assert product_manifest["tree"] == product_summary["tree"] == product_receipt["tree"]
    assert (
        product_summary["product_occurrence_ledger_sha256"]
        == loaded["c8c_evidence_chain"]["occurrence_ledger_sha256"]
    )
    assert product_summary[
        "product_occurrence_ledger_sha256"
    ] != _sha256(_canonical_bytes(c8c_taxonomy["rows"]))


def test_diagnostic_calls_full_fidelity_and_separates_blocker_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    config_path, digest, output_root, config = _run_config(tmp_path)
    evidence = _test_evidence_fixture()
    projection = SimpleNamespace(
        parents=(_candidate_parent(),),
        children=(
            _candidate_child(0),
            _candidate_child(1),
            _candidate_non_story_child(),
        ),
    )
    assert projection.parents == evidence.candidate_parent_rows
    assert projection.children == evidence.candidate_child_rows
    compose_calls: list[tuple[object, object, object]] = []
    fidelity_calls: list[dict[str, object]] = []

    def compose(data: object, page: object, topic: object):
        compose_calls.append((data, page, topic))
        return projection

    def build(**kwargs: object):
        fidelity_calls.append(kwargs)
        return _fidelity_result()

    semantic_inputs = SimpleNamespace(
        pages=lambda: (),
        revisions=lambda: (),
        iter_data_page_mappings=lambda: (),
    )
    monkeypatch.setattr(
        module.CrawlerSemanticInputs,
        "from_root",
        lambda _root: semantic_inputs,
    )
    monkeypatch.setattr(module, "build_page_revision_join", lambda *_args: object())
    monkeypatch.setattr(
        module, "project_crawler_semantics", lambda *_args: evidence.data_projection
    )
    monkeypatch.setattr(
        module, "project_page_semantics", lambda *_args: evidence.page_projection
    )
    monkeypatch.setattr(
        module, "project_topic_semantics", lambda *_args: evidence.topic_projection
    )
    monkeypatch.setattr(module, "compose_corpus_projection", compose)
    loaded_evidence = module.load_validated_evidence(config)
    assert loaded_evidence.projection is projection
    assert loaded_evidence.candidate_parent_rows == projection.parents
    assert loaded_evidence.candidate_child_rows == projection.children
    assert compose_calls == [
        (evidence.data_projection, evidence.page_projection, evidence.topic_projection)
    ]

    monkeypatch.setattr(
        module, "load_validated_evidence", lambda _config: loaded_evidence
    )
    monkeypatch.setattr(module, "build_fidelity_ledger", build)
    monkeypatch.setattr(module, "read_git_identity", lambda _root: (HEAD, TREE))

    _invoke(module, config_path, digest, output_root)

    assert len(compose_calls) == 1
    assert len(fidelity_calls) == 1
    call = fidelity_calls[0]
    assert call["projection"] is projection
    assert call["active_parent_rows"] == loaded_evidence.active_parent_rows
    assert call["active_child_rows"] == loaded_evidence.active_child_rows
    assert call["legacy_media"] is loaded_evidence.legacy_media
    summary = json.loads((output_root / OUTPUT_NAMES[2]).read_bytes())
    assert summary["fidelity_returned_normally"] is True
    assert summary["story_blocker_prefix_counts"] == {
        "blocked_ambiguous_child": 1,
        "blocked_ambiguous_parent": 1,
        "unexplained_child_missing": 1,
        "unexplained_parent_missing": 1,
    }
    assert summary["non_story_media_blocker_counts"] == {
        "ambiguous_binding": 2,
        "conflicting_binding": 1,
        "missing_local_bytes": 3,
        "missing_resource_metadata": 0,
    }
    assert summary["other_blocker_prefix_counts"] == {
        "blocked_ambiguous_child": 1,
        "unexplained_binding_loss": 6,
        "unexplained_parent_child_loss": 1,
    }
    story_evidence = summary["story_partition_evidence"]
    assert story_evidence["source_identity_sha256"] == _hashed(
        "Data:Story/9.json\0" + "a" * 64
    )
    assert story_evidence["legacy_child_identity_sha256"] == _hashed(
        "story:9/profile:0000"
    )
    assert story_evidence["candidate_child_identity_sha256"] == [
        _hashed("story:9/story:step-0000"),
        _hashed("story:9/story:step-0001"),
    ]
    non_story_evidence = summary["non_story_partition_evidence"]
    assert non_story_evidence == [
        {
            "record_kind": "child",
            "classification": "blocked_ambiguous",
            "reason_code": "candidate_identity_ambiguous",
            "active_identity_sha256": _hashed(
                "story:mismatched-prefix/profile:0000"
            ),
            "candidate_identities_sha256": _hashed(
                "character:9/profile-v2:0000"
            ),
            "source_evidence_sha256": _hashed(
                "Data:Character/9.json\0" + "b" * 64
            ),
        }
    ]
    assert "story" not in json.dumps(summary["non_story_media_blocker_counts"])


def test_diagnostic_writes_only_three_canonical_create_new_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    empty_config_path, empty_digest, empty_output, empty_config = _run_config(
        tmp_path / "preexisting-empty"
    )
    empty_output.mkdir(parents=True)
    reached = {"git": 0, "projection": 0, "fidelity": 0}

    def reached_git(_root: Path) -> tuple[str, str]:
        reached["git"] += 1
        return HEAD, TREE

    def reached_projection(_config: object) -> SimpleNamespace:
        reached["projection"] += 1
        return _test_evidence_fixture()

    def reached_fidelity(**_kwargs: object) -> SimpleNamespace:
        reached["fidelity"] += 1
        return _fidelity_result()

    monkeypatch.setattr(module, "read_git_identity", reached_git)
    monkeypatch.setattr(module, "load_validated_evidence", reached_projection)
    monkeypatch.setattr(module, "build_fidelity_ledger", reached_fidelity)
    original_load_run_config = module.load_run_config
    monkeypatch.setattr(
        module,
        "load_run_config",
        lambda *_args, **_kwargs: empty_config,
    )
    with pytest.raises(FileExistsError, match="create-new"):
        _invoke(module, empty_config_path, empty_digest, empty_output)
    assert reached == {"git": 0, "projection": 0, "fidelity": 0}
    assert tuple(empty_output.iterdir()) == ()
    monkeypatch.setattr(module, "load_run_config", original_load_run_config)

    config_path, digest, output_root, config = _run_config(tmp_path)
    monkeypatch.setattr(module, "read_git_identity", lambda _root: (HEAD, TREE))
    monkeypatch.setattr(module, "load_validated_evidence", lambda _config: _test_evidence_fixture())
    monkeypatch.setattr(module, "build_fidelity_ledger", lambda **_kwargs: _fidelity_result())

    _invoke(module, config_path, digest, output_root)

    assert tuple(sorted(path.name for path in output_root.iterdir())) == OUTPUT_NAMES
    documents: dict[str, dict[str, object]] = {}
    hashes: dict[str, str] = {}
    for name in OUTPUT_NAMES:
        raw = (output_root / name).read_bytes()
        assert raw == _canonical_bytes(json.loads(raw))
        documents[name] = json.loads(raw)
        hashes[name] = _sha256(raw)
        assert documents[name]["schema_version"] == OUTPUT_SCHEMAS[name]

    manifest = documents[OUTPUT_NAMES[0]]
    receipt = documents[OUTPUT_NAMES[1]]
    summary = documents[OUTPUT_NAMES[2]]
    assert manifest["run_id"] == receipt["run_id"] == summary["run_id"] == RUN_ID
    assert manifest["output_sha256"] == {OUTPUT_NAMES[2]: hashes[OUTPUT_NAMES[2]]}
    assert receipt["output_sha256"] == {
        OUTPUT_NAMES[0]: hashes[OUTPUT_NAMES[0]],
        OUTPUT_NAMES[2]: hashes[OUTPUT_NAMES[2]],
    }
    assert manifest["run_config"] == {
        "path": config_path.name,
        "sha256": digest,
        "size_bytes": config_path.stat().st_size,
    }
    assert manifest["diagnostic"] == {
        "path": SCRIPT_RELATIVE_PATH,
        "sha256": SCRIPT_SHA256,
    }
    assert manifest["git_identity"] == {"head": HEAD, "tree": TREE}
    repository_root = Path(config["repository_root"])
    expected_checkpoints = {
        "task7_c8a_commit": C8A_COMMIT,
        "c8b_commit": C8B_COMMIT,
        "c8b_d_acceptance": {
            "identity": "frozen/d-acceptance-c8b.json",
            "sha256": C8B_RECEIPT_SHA256,
            "size": 3622,
        },
        "c8c_commit": C8C_COMMIT,
        "c8c_d_acceptance": {
            "identity": "frozen/d-accept-c8c-final.json",
            "sha256": C8C_RECEIPT_SHA256,
            "size": 3705,
        },
    }
    expected_inputs = {
        label: {
            "identity": Path(identity["path"]).relative_to(
                repository_root
            ).as_posix(),
            "sha256": identity["sha256"],
            "size": identity["size_bytes"],
            **(
                {"row_count": identity["row_count"]}
                if "row_count" in identity
                else {}
            ),
        }
        for label, identity in config["inputs"].items()
    }
    assert manifest["accepted_checkpoints"] == expected_checkpoints
    assert manifest["inputs"] == expected_inputs
    assert manifest["c8c_evidence_chain"] == config["c8c_evidence_chain"]
    assert receipt["output_confinement"] == {
        "create_new": True,
        "output_root": RUN_ID,
        "unexpected_output_count": 0,
        "writes_outside_exact_outputs": 0,
    }
    assert receipt["protected_state"] == {
        "identity_count_pre": 32,
        "identity_count_post": 32,
        "drift_count": 0,
    }
    assert receipt["activity_counters"] == ACTIVITY_COUNTERS
    encoded_identity_chain = json.dumps(manifest, ensure_ascii=False).lower()
    assert str(tmp_path).lower().replace("\\", "/") not in encoded_identity_chain
    for secret in ("password", "credential", "token=", "api_key"):
        assert secret not in encoded_identity_chain

    before = {path.name: path.read_bytes() for path in output_root.iterdir()}
    with pytest.raises(FileExistsError):
        _invoke(module, config_path, digest, output_root)
    assert {path.name: path.read_bytes() for path in output_root.iterdir()} == before

    for drift_kind in ("content", "size", "membership", "timestamp"):
        drift_config_path, drift_digest, drift_output, drift_config = _run_config(
            tmp_path / f"protected-{drift_kind}"
        )
        protected_path = Path(
            drift_config["inputs"]["protected_identity_manifest"]["path"]
        )
        protected = json.loads(protected_path.read_bytes())
        target = Path(protected["records"][0]["path"])

        def drift_then_build(
            **_kwargs: object,
        ) -> SimpleNamespace:
            if drift_kind == "content":
                target.write_bytes(b"X" * target.stat().st_size)
            elif drift_kind == "size":
                target.write_bytes(target.read_bytes() + b"X")
            elif drift_kind == "membership":
                target.unlink()
            else:
                stat = target.stat()
                os.utime(
                    target,
                    ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
                )
            return _fidelity_result()

        monkeypatch.setattr(module, "read_git_identity", lambda _root: (HEAD, TREE))
        monkeypatch.setattr(
            module,
            "load_validated_evidence",
            lambda _config: _test_evidence_fixture(),
        )
        monkeypatch.setattr(module, "build_fidelity_ledger", drift_then_build)
        with pytest.raises(ValueError, match="protected.*drift"):
            _invoke(module, drift_config_path, drift_digest, drift_output)
        _assert_no_output(drift_output)


def test_diagnostic_blocks_network_external_writers_and_media_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    platform.system()
    config_path, digest, output_root, config = _run_config(tmp_path)
    forbidden: list[str] = []
    subprocess_counts = {"total": 0, "allowed": 0, "forbidden": 0}
    real_builtin_open = builtins.open
    real_io_open = io.open

    def reject(name: str) -> Callable[..., Any]:
        def blocked(*_args: object, **_kwargs: object) -> Any:
            forbidden.append(name)
            raise AssertionError(f"forbidden operation: {name}")

        return blocked

    monkeypatch.setattr(socket, "create_connection", reject("network"))
    monkeypatch.setattr(socket.socket, "connect", reject("network"))
    monkeypatch.setattr(socket.socket, "connect_ex", reject("network"))

    def guarded_run(argv: object, **kwargs: object):
        subprocess_counts["total"] += 1
        expected_kwargs = {
            "cwd": Path(config["repository_root"]),
            "check": True,
            "capture_output": True,
            "text": True,
            "shell": False,
        }
        if tuple(argv) != ("git", "rev-parse", "HEAD", "HEAD^{tree}") or kwargs != expected_kwargs:
            subprocess_counts["forbidden"] += 1
            raise AssertionError("arbitrary subprocess rejected")
        subprocess_counts["allowed"] += 1
        return subprocess.CompletedProcess(argv, 0, f"{HEAD}\n{TREE}\n", "")

    monkeypatch.setattr(subprocess, "run", guarded_run)

    exact_outputs = {path.resolve() for path in (output_root / name for name in OUTPUT_NAMES)}
    repository_root = Path(config["repository_root"]).resolve()
    allowed_reads = {
        config_path.resolve(),
        (repository_root / SCRIPT_RELATIVE_PATH).resolve(),
        *(
            Path(identity["path"]).resolve()
            for identity in config["inputs"].values()
        ),
        *(
            Path(config["accepted_checkpoints"][name]["path"]).resolve()
            for name in ("c8b_d_acceptance", "c8c_d_acceptance")
        ),
        *exact_outputs,
    }
    product_manifest_path = Path(
        config["inputs"]["c8c_product_manifest"]["path"]
    ).resolve()
    allowed_reads.add(product_manifest_path.with_name("diagnostic.product-parity.py"))
    allowed_reads.add(
        Path(config["inputs"]["c8b_taxonomy"]["path"])
        .with_name("manifest.c8b3.v1.json")
        .resolve()
    )
    protected_state = json.loads(
        Path(config["inputs"]["protected_identity_manifest"]["path"]).read_bytes()
    )
    allowed_reads.update(
        Path(record["path"]).resolve() for record in protected_state["records"]
    )
    code_roots = tuple(
        path.resolve()
        for path in (
            Path(__file__).resolve().parents[1] / "src",
            Path(__file__).resolve().parents[1] / "scripts",
        )
    )
    local_media_path = (
        Path(config["inputs"]["resource_metadata"]["path"]).parent
        / "media"
        / "arbitrary-resource.dat"
    ).resolve()
    assert local_media_path.is_file()
    assert local_media_path not in allowed_reads

    def guard_open(delegate: Callable[..., Any]) -> Callable[..., Any]:
        def guarded(file: object, mode: str = "r", *args: object, **kwargs: object):
            path = Path(file).resolve() if isinstance(file, (str, Path)) else None
            if path is not None and any(flag in mode for flag in "wax+"):
                if path not in exact_outputs:
                    return reject("write_outside_exact_outputs")(file, mode)
            if path is not None and "r" in mode:
                code_read = path.suffix in {".py", ".pyc"} and any(
                    path.is_relative_to(root) for root in code_roots
                )
                if path not in allowed_reads and not code_read:
                    return reject("local_media_byte_read")(file, mode)
            return delegate(file, mode, *args, **kwargs)

        return guarded

    monkeypatch.setattr(builtins, "open", guard_open(real_builtin_open))
    monkeypatch.setattr(io, "open", guard_open(real_io_open))

    adapter_boundaries = (
        ("src.assets.minio_store", "MinioAssetStorage", "upload_file", "minio"),
        (
            "src.huiji_rag.minio_strict",
            "StrictMinioUploader",
            "upload_sequence",
            "minio",
        ),
        ("src.huiji_rag.activation", None, "apply_activation", "activation"),
        ("src.huiji_rag.build.media_v3", None, "reconcile_media_v3_minio", "minio"),
        ("src.huijiwiki.resource_downloader", "ResourceDownloader", "run", "download"),
        ("src.huiji_rag.closure", None, "_query_database_state", "mysql"),
        ("src.huiji_rag.io", None, "_capture_milvus_observation", "milvus"),
        ("src.huiji_rag.provenance", None, "_runtime_milvus_client", "milvus"),
        (
            "src.huiji_rag.build.orchestrator",
            "HuijiCorpusBuilder",
            "build_candidate",
            "vector",
        ),
    )
    for module_name, class_name, attribute, label in adapter_boundaries:
        target_module = importlib.import_module(module_name)
        target = getattr(target_module, class_name) if class_name else target_module
        assert hasattr(target, attribute), f"missing guard boundary: {module_name}.{attribute}"
        monkeypatch.setattr(target, attribute, reject(label))

    # The exact accepted C8c manifest-schema RED is owned by the first node;
    # keep this node focused on offline/read/write confinement.
    monkeypatch.setattr(module, "_validate_c8c_chain", lambda *_args: None)
    monkeypatch.setattr(module, "load_validated_evidence", lambda _config: _test_evidence_fixture())
    monkeypatch.setattr(module, "build_fidelity_ledger", lambda **_kwargs: _fidelity_result())
    _invoke(module, config_path, digest, output_root)

    assert forbidden == []
    assert subprocess_counts == {"total": 1, "allowed": 1, "forbidden": 0}
    receipt = json.loads((output_root / OUTPUT_NAMES[1]).read_bytes())
    assert receipt["activity_counters"] == ACTIVITY_COUNTERS


def test_diagnostic_bounds_sanitizes_and_deterministically_orders_samples(
    tmp_path: Path
) -> None:
    module = _load_diagnostic()
    for invalid_limit in (0, 6, True, 1.0):
        with pytest.raises(ValueError, match="sample limit"):
            module.bounded_structured_samples([], limit_per_prefix=invalid_limit)
    for valid_limit in range(1, 6):
        assert module.bounded_structured_samples(
            [], limit_per_prefix=valid_limit
        ) == {}
    rows = []
    for index in range(7):
        rows.append(
            {
                "blocker_prefix": "blocked_ambiguous_child",
                "record_kind": "child",
                "classification": "blocked_ambiguous",
                "reason_code": "unmatched_source_group",
                "active_identity": f"story:private:{index}/profile:0000",
                "candidate_identities": [
                    f"story:private:{index}/story:step-0000"
                ],
                "source_evidence": [
                    {
                        "source_title": f"Data:Story/private-{index}.json",
                        "source_content_sha256": "a" * 64,
                        "json_path": "$.steps",
                    }
                ],
                "raw_text": "{{secret wikitext}} password=hunter2",
                "absolute_path": f"{tmp_path}/private-{index}.json",
            }
        )
    rows.append(
        {
            "blocker_prefix": "legacy_media_conflicting_binding",
            "record_kind": "media",
            "classification": "conflicting_binding",
            "reason_code": "current_closure_conflict",
            "active_identity": "media:sha1:" + "f" * 40,
            "candidate_identities": ["binding:sha256:" + "e" * 64],
            "source_evidence": [
                {
                    "source_title": "crawler-resource:"
                    + "d" * 40
                    + ":private.png",
                    "source_content_sha256": "c" * 64,
                    "json_path": "$.resources[0]",
                }
            ],
            "raw_text": "token=secret",
            "absolute_path": "C:\\private\\raw.png",
        }
    )

    first = module.bounded_structured_samples(rows, limit_per_prefix=5)
    second = module.bounded_structured_samples(
        tuple(reversed(rows)), limit_per_prefix=5
    )

    assert first == second
    assert list(first) == sorted(first)
    assert len(first["blocked_ambiguous_child"]) == 5
    assert len(first["legacy_media_conflicting_binding"]) == 1
    for prefix, samples in first.items():
        assert samples == sorted(
            samples,
            key=lambda row: tuple(str(row[field]) for field in sorted(SAMPLE_FIELDS)),
        )
        for sample in samples:
            assert set(sample) == SAMPLE_FIELDS
            for field in (
                "active_identity_sha256",
                "candidate_identities_sha256",
            ):
                assert len(sample[field]) == 64
                int(sample[field], 16)
            assert sample["candidate_identity_count"] >= 0
            assert sample["source_evidence_count"] >= 0

    encoded = json.dumps(first, ensure_ascii=False).lower()
    for forbidden_text in (
        "story:private",
        "media:sha1",
        "binding:sha256",
        "data:story",
        "crawler-resource",
        "private.png",
        "c:\\private",
        str(tmp_path).lower(),
        "hunter2",
        "secret wikitext",
        "password",
        "token=",
        "raw_text",
        "absolute_path",
        '"active_identity":',
        '"candidate_identities":',
        '"source_evidence":',
        '"blocker_prefix":',
    ):
        assert forbidden_text not in encoded


def test_diagnostic_fails_closed_on_hash_head_tree_path_or_output_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    adapter_config_path, adapter_digest, adapter_output, adapter_config = _run_config(
        tmp_path / "strict-adapter"
    )

    def jsonl_rows(label: str) -> list[dict[str, object]]:
        path = Path(adapter_config["inputs"][label]["path"])
        return [json.loads(line) for line in path.read_text().splitlines()]

    taxonomy = json.loads(
        Path(adapter_config["inputs"]["c8c_taxonomy"]["path"]).read_bytes()
    )
    active_media = jsonl_rows("active_media")
    candidate_media = jsonl_rows("candidate_media_v3")
    resource_metadata = jsonl_rows("resource_metadata")
    assert len(resource_metadata) > len(
        {row["source_sha1"] for row in candidate_media}
    )
    assert all(
        candidate["title"]
        != next(
            resource["title"]
            for resource in resource_metadata
            if (
                resource["sha1"],
                resource["name"],
                resource["size"],
            )
            == (
                candidate["source_sha1"],
                candidate["filename"],
                candidate["size"],
            )
        )
        for candidate in candidate_media
    )
    reconciled = module._strict_c8c_adapter(
        taxonomy, active_media, candidate_media, resource_metadata
    )
    assert reconciled.active_occurrence_count == len(active_media)
    title_variant_candidates = copy.deepcopy(candidate_media)
    title_variant_candidates[0]["title"] = (
        "A different natural-language description remains valid"
    )
    assert module._strict_c8c_adapter(
        taxonomy,
        active_media,
        title_variant_candidates,
        resource_metadata,
    ).active_occurrence_count == len(active_media)

    trailing_newline_taxonomy = copy.deepcopy(taxonomy)
    trailing_newline_taxonomy["rows"][0][
        "legacy_row_sha256"
    ] = _sha256(_canonical_bytes(active_media[0]))
    with pytest.raises(ValueError, match="active row"):
        module._strict_c8c_adapter(
            trailing_newline_taxonomy,
            active_media,
            candidate_media,
            resource_metadata,
        )

    proven_collision_taxonomy = copy.deepcopy(taxonomy)
    proven_collision_taxonomy["coverage_checks"][
        "proven_candidate_consumption_collision_count"
    ] = 1
    proven_collision_taxonomy["duplicate_consumption_checks"][
        "proven_candidate_consumption_collision_count"
    ] = 1
    with pytest.raises(ValueError):
        module._strict_c8c_adapter(
            proven_collision_taxonomy,
            active_media,
            candidate_media,
            resource_metadata,
        )

    # Removing the sole exact triple match leaves only a valid same-SHA1
    # alternative, which must not be accepted as the candidate's resource.
    with pytest.raises(ValueError, match="resource metadata"):
        module._strict_c8c_adapter(
            taxonomy, active_media, candidate_media, resource_metadata[1:]
        )
    # Repeated SHA1 is valid, but two rows with the same concrete triple are
    # non-unique and must fail closed.
    with pytest.raises(ValueError, match="resource metadata"):
        module._strict_c8c_adapter(
            taxonomy,
            active_media,
            candidate_media,
            [*resource_metadata, copy.deepcopy(resource_metadata[0])],
        )
    for field, conflicting_value in (
        ("sha1", "0" * 40),
        ("name", "conflicting-name.png"),
        ("size", 999),
    ):
        conflicting_metadata = copy.deepcopy(resource_metadata)
        conflicting_metadata[0][field] = conflicting_value
        with pytest.raises(ValueError, match="resource metadata"):
            module._strict_c8c_adapter(
                taxonomy, active_media, candidate_media, conflicting_metadata
            )
    for field, conflicting_value in (
        ("source_sha1", "0" * 40),
        ("filename", "conflicting-name.png"),
        ("size", 999),
    ):
        conflicting_candidate_media = copy.deepcopy(candidate_media)
        conflicting_candidate_media[0][field] = conflicting_value
        with pytest.raises(ValueError, match="resource metadata"):
            module._strict_c8c_adapter(
                taxonomy,
                active_media,
                conflicting_candidate_media,
                resource_metadata,
            )

    for index, malformed_bm25 in enumerate(
        ([], {}, {"records": {}}, {"records": [], "unexpected": True})
    ):
        case_root = tmp_path / f"bm25-malformed-{index}"
        case_config_path, _, case_output, case_config = _run_config(case_root)
        bm25_path = Path(case_config["inputs"]["active_child_bm25"]["path"])
        bm25_raw = _canonical_bytes(malformed_bm25)
        bm25_path.write_bytes(bm25_raw)
        case_config["inputs"]["active_child_bm25"] = _identity(
            bm25_path, bm25_raw
        )
        case_raw = _canonical_bytes(case_config)
        case_config_path.write_bytes(case_raw)
        with pytest.raises(ValueError, match="BM25"):
            module.load_run_config(
                case_config_path,
                expected_run_config_sha256=_sha256(case_raw),
                output_root=case_output,
            )

    base_config_path, base_digest, _, base_config = _run_config(tmp_path / "base")

    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def git_run(argv: object, **kwargs: object):
        calls.append((tuple(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, f"{HEAD}\n{TREE}\n", "")

    monkeypatch.setattr(module.subprocess, "run", git_run)
    assert module.read_git_identity(Path(base_config["repository_root"])) == (HEAD, TREE)
    assert calls == [
        (
            ("git", "rev-parse", "HEAD", "HEAD^{tree}"),
            {
                "cwd": Path(base_config["repository_root"]),
                "check": True,
                "capture_output": True,
                "text": True,
                "shell": False,
            },
        )
    ]

    def run_case(
        name: str,
        mutate: Callable[[dict[str, Any], Path], None],
        *,
        raw_override: Callable[[bytes], bytes] | None = None,
        expected_digest_override: str | None = None,
        prepare: Callable[[dict[str, Any], Path], None] | None = None,
    ) -> None:
        case_root = tmp_path / name
        config_path, digest, output_root, config = _run_config(case_root)
        case = copy.deepcopy(config)
        mutate(case, case_root)
        if prepare is not None:
            prepare(case, case_root)
        raw = _canonical_bytes(case)
        if raw_override is not None:
            raw = raw_override(raw)
        config_path.write_bytes(raw)
        actual_digest = _sha256(raw)
        expected_digest = expected_digest_override or actual_digest
        before = (
            {path.name: path.read_bytes() for path in Path(case["output_root"]).iterdir()}
            if Path(case["output_root"]).is_dir()
            else {}
        )
        with pytest.raises(
            (FileExistsError, OSError, RuntimeError, subprocess.SubprocessError, ValueError)
        ):
            module.run_diagnostic(
                config_path,
                expected_run_config_sha256=expected_digest,
                output_root=Path(case["output_root"]),
            )
        after = (
            {path.name: path.read_bytes() for path in Path(case["output_root"]).iterdir()}
            if Path(case["output_root"]).is_dir()
            else {}
        )
        assert after == before
        assert not any(case_root.rglob("*.partial"))
        assert not any(case_root.rglob("*.tmp"))

    cases: list[tuple[str, Callable[[dict[str, Any], Path], None]]] = [
        ("wrong-head", lambda c, _r: c.__setitem__("expected_git_head", "0" * 40)),
        ("wrong-tree", lambda c, _r: c.__setitem__("expected_git_tree", "0" * 40)),
        (
            "wrong-input-hash",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("sha256", "0" * 64),
        ),
        (
            "wrong-input-size",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("size_bytes", 999),
        ),
        (
            "wrong-row-count",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("row_count", 999),
        ),
        (
            "path-escape",
            lambda c, r: c["inputs"]["active_parents"].__setitem__(
                "path", (r.parent / "outside.jsonl").as_posix()
            ),
        ),
        (
            "script-drift",
            lambda c, _r: c["diagnostic"].__setitem__("sha256", "0" * 64),
        ),
        (
            "receipt-drift",
            lambda c, _r: c["accepted_checkpoints"]["c8c_d_acceptance"].__setitem__(
                "sha256", "0" * 64
            ),
        ),
        (
            "checkpoint-drift",
            lambda c, _r: c["accepted_checkpoints"].__setitem__("c8b_commit", "0" * 40),
        ),
        (
            "evidence-chain-drift",
            lambda c, _r: c["c8c_evidence_chain"].__setitem__(
                "summary_sha256", "0" * 64
            ),
        ),
        (
            "run-id-output-mismatch",
            lambda c, r: c.__setitem__("output_root", (r / "wrong-run-id").as_posix()),
        ),
        ("unknown-top-field", lambda c, _r: c.__setitem__("surprise", True)),
        ("missing-top-field", lambda c, _r: c.pop("accepted_checkpoints")),
        (
            "unknown-input-field",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("surprise", True),
        ),
        (
            "missing-input-field",
            lambda c, _r: c["inputs"]["active_parents"].pop("sha256"),
        ),
        (
            "product-schema-drift",
            lambda c, _r: c["inputs"]["c8c_product_manifest"].__setitem__(
                "sha256", "0" * 64
            ),
        ),
    ]
    for name, mutation in cases:
        run_case(name, mutation)

    run_case(
        "wrong-run-config-digest",
        lambda _c, _r: None,
        expected_digest_override="0" * 64,
    )
    run_case(
        "duplicate-json-key",
        lambda _c, _r: None,
        raw_override=lambda raw: raw.replace(
            b'{"accepted_checkpoints":',
            b'{"schema_version":"duplicate","accepted_checkpoints":',
            1,
        ),
    )

    def make_symlink(case: dict[str, Any], root: Path) -> None:
        target = Path(case["inputs"]["active_parents"]["path"])
        replacement = root / "symlink-parents.jsonl"
        replacement.symlink_to(target)
        case["inputs"]["active_parents"] = {
            **case["inputs"]["active_parents"],
            "path": replacement.as_posix(),
        }

    try:
        run_case(
            "symlink-input",
            lambda _c, _r: None,
            prepare=make_symlink,
        )
    except OSError as error:
        if getattr(error, "winerror", None) != 1314:
            raise

    def colliding_output(case: dict[str, Any], _root: Path) -> None:
        output = Path(case["output_root"])
        output.mkdir(parents=True)
        (output / OUTPUT_NAMES[2]).write_bytes(b"preexisting\n")

    run_case(
        "output-collision",
        lambda _c, _r: None,
        prepare=colliding_output,
    )

    second_subprocess_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def second_subprocess(argv: object, **kwargs: object):
        second_subprocess_calls.append((tuple(argv), kwargs))
        if len(second_subprocess_calls) == 1:
            assert tuple(argv) == ("git", "rev-parse", "HEAD", "HEAD^{tree}")
            return subprocess.CompletedProcess(argv, 0, f"{HEAD}\n{TREE}\n", "")
        raise subprocess.SubprocessError("subsequent subprocess rejected")

    original_load_validated_evidence = module.load_validated_evidence

    def inject_subsequent_subprocess(config: dict[str, object]):
        module.subprocess.run(
            ("python", "unexpected.py"),
            cwd=Path(config["repository_root"]),
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
        return original_load_validated_evidence(config)

    monkeypatch.setattr(module.subprocess, "run", second_subprocess)
    monkeypatch.setattr(
        module, "load_validated_evidence", inject_subsequent_subprocess
    )
    run_case("second-subprocess", lambda _c, _r: None)
    assert [call[0] for call in second_subprocess_calls] == [
        ("git", "rev-parse", "HEAD", "HEAD^{tree}"),
        ("python", "unexpected.py"),
    ]
    assert _sha256(base_config_path.read_bytes()) == base_digest
