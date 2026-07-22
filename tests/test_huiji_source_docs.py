from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.verify_huiji_provenance_acceptance import (
    compare_protected_payloads,
    identify_shadow_minio_additions,
    main as acceptance_main,
    merge_listing_inventory_with_baseline,
    parse_allowed_artifact_additions,
    sample_active_sources,
)


ROOT = Path(__file__).resolve().parents[1]


class _Snapshot:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def to_json(self):
        return self.payload


def _protected_payload(*, artifact_sha: str = "a" * 64, captured: str = "one"):
    return {
        "schema_version": "rag_eval.protected_snapshot/v2",
        "captured_at_utc": captured,
        "milvus": {
            "collection_name": "active_v3",
            "schema_sha256": "b" * 64,
            "row_count": 2,
            "primary_field": "id",
            "primary_id_count": 2,
            "primary_ids_sha256": "c" * 64,
            "load_state": {"state": "Loaded"},
            "captured_at_utc": captured,
        },
        "minio_inventories": {
            "reverse1999-assets/reverse1999": {
                "object_count": 2,
                "objects_sha256": "d" * 64,
                "captured_at_utc": captured,
                "inventory_sha256": "e" * 64,
            }
        },
        "mysql_tables": {"wiki_pages": {"row_count": 1, "sha256": "f" * 64}},
        "artifacts": {"data/processed/huiji/dev/child_blocks.jsonl": {"sha256": artifact_sha}},
    }


def test_protected_payload_comparison_ignores_capture_metadata_only():
    before = _protected_payload(captured="before")
    same = _protected_payload(captured="after")
    same["minio_inventories"]["reverse1999-assets/reverse1999"]["inventory_sha256"] = "0" * 64

    assert compare_protected_payloads(before, same) == []

    changed = _protected_payload(artifact_sha="9" * 64, captured="after")
    assert compare_protected_payloads(before, changed) == ["artifacts changed"]


def test_protected_payload_comparison_allows_only_exact_new_artifacts():
    before = _protected_payload(captured="before")
    after = json.loads(json.dumps(before))
    after["captured_at_utc"] = "after"
    path = "data/processed/huiji/operations/op-1/plan.json"
    evidence = {"sha256": "1" * 64, "size": 42}
    after["artifacts"][path] = evidence

    assert compare_protected_payloads(before, after) == ["artifacts changed"]
    assert compare_protected_payloads(
        before,
        after,
        allowed_artifact_additions={path: evidence},
    ) == []

    wrong = json.loads(json.dumps(after))
    wrong["artifacts"][path]["size"] = 43
    with pytest.raises(ValueError, match="does not match evidence"):
        compare_protected_payloads(
            before,
            wrong,
            allowed_artifact_additions={path: evidence},
        )

    extra = json.loads(json.dumps(after))
    extra["artifacts"]["data/processed/huiji/operations/op-2/extra.json"] = evidence
    assert compare_protected_payloads(
        before,
        extra,
        allowed_artifact_additions={path: evidence},
    ) == ["artifacts changed"]


def test_exact_artifact_addition_parser_rejects_approximate_authority():
    value = "data/processed/huiji/operations/op-1/plan.json|" + "a" * 64 + "|42"
    assert parse_allowed_artifact_additions([value]) == {
        "data/processed/huiji/operations/op-1/plan.json": {
            "sha256": "a" * 64,
            "size": 42,
        }
    }

    for invalid in (
        "../plan.json|" + "a" * 64 + "|42",
        "data\\plan.json|" + "a" * 64 + "|42",
        "data/plan.json|bad|42",
        "data/plan.json|" + "a" * 64 + "|042",
    ):
        with pytest.raises(ValueError):
            parse_allowed_artifact_additions([invalid])


def test_protected_payload_comparison_allows_only_attributed_shadow_objects():
    before = _protected_payload(captured="before")
    before["minio_inventories"]["a-bucket"] = {
        "bucket": "a-bucket",
        "prefix": "",
        "objects": [
            {
                "object_key": "files/insert_log/100/101/102/0/1",
                "sha256": "1" * 64,
                "size": 10,
            }
        ],
        "captured_at_utc": "before",
        "inventory_sha256": "2" * 64,
    }
    after = json.loads(json.dumps(before))
    after["captured_at_utc"] = "after"
    after["minio_inventories"]["a-bucket"]["captured_at_utc"] = "after"
    after["minio_inventories"]["a-bucket"]["inventory_sha256"] = "3" * 64
    shadow_key = "files/insert_log/200/201/202/0/2"
    after["minio_inventories"]["a-bucket"]["objects"].append(
        {"object_key": shadow_key, "sha256": "4" * 64, "size": 20}
    )

    assert compare_protected_payloads(before, after) == ["minio_inventories changed"]
    assert compare_protected_payloads(
        before,
        after,
        allowed_minio_additions={"a-bucket": (shadow_key,)},
    ) == []

    after["minio_inventories"]["a-bucket"]["objects"].append(
        {
            "object_key": "files/insert_log/999/998/997/0/3",
            "sha256": "5" * 64,
            "size": 30,
        }
    )
    assert compare_protected_payloads(
        before,
        after,
        allowed_minio_additions={"a-bucket": (shadow_key,)},
    ) == ["minio_inventories changed"]

    after["minio_inventories"]["a-bucket"]["objects"][0]["sha256"] = "6" * 64
    assert compare_protected_payloads(
        before,
        after,
        allowed_minio_additions={"a-bucket": (shadow_key,)},
    ) == ["minio_inventories changed"]


def test_shadow_minio_additions_require_exact_collection_or_segment_path_tokens():
    before = _protected_payload()
    before["minio_inventories"]["a-bucket"] = {
        "bucket": "a-bucket",
        "prefix": "",
        "objects": [],
    }
    after = json.loads(json.dumps(before))
    attributed = [
        "files/insert_log/200/201/300/0/1",
        "files/stats_log/200/201/301/100/2",
        "files/index_files/900/201/300/HNSW_0",
    ]
    unrelated = "files/insert_log/999/998/997/0/3"
    after["minio_inventories"]["a-bucket"]["objects"] = [
        {"object_key": key, "sha256": "a" * 64, "size": 1}
        for key in [*attributed, unrelated]
    ]

    class Client:
        def describe_collection(self, collection_name):
            assert collection_name == "shadow_v1"
            return {"collection_id": 200}

        def list_persistent_segments(self, collection_name):
            assert collection_name == "shadow_v1"
            return [
                SimpleNamespace(segment_id=300, collection_id=200),
                SimpleNamespace(segment_id=301, collection_id=200),
            ]

    additions, summary = identify_shadow_minio_additions(
        before,
        after,
        client=Client(),
        collection_name="shadow_v1",
    )

    assert additions == {"a-bucket": tuple(sorted(attributed))}
    assert summary["collection"] == "shadow_v1"
    assert summary["object_count"] == 3
    assert unrelated not in additions["a-bucket"]


def test_listing_inventory_reuses_hashes_only_for_unchanged_object_identity():
    baseline = {
        "bucket": "reverse1999-assets",
        "prefix": "reverse1999",
        "bucket_policy_summary": "absent",
        "objects": [
            {
                "object_key": "reverse1999/voice/a.mp3",
                "size": 10,
                "etag": "etag-a",
                "version_id": None,
                "sha1": "1" * 40,
                "sha256": "2" * 64,
                "audit_event_id": None,
                "application_operation_id": "op-1",
            },
            {
                "object_key": "reverse1999/voice/b.mp3",
                "size": 20,
                "etag": "etag-b",
                "version_id": None,
                "sha1": "3" * 40,
                "sha256": "4" * 64,
                "audit_event_id": None,
                "application_operation_id": None,
            },
        ],
    }

    merged = merge_listing_inventory_with_baseline(
        baseline,
        current_policy_summary="absent",
        current_objects=[
            {
                "object_key": "reverse1999/voice/a.mp3",
                "size": 10,
                "etag": '"etag-a"',
                "version_id": None,
            },
            {
                "object_key": "reverse1999/voice/b.mp3",
                "size": 21,
                "etag": "etag-b-new",
                "version_id": None,
            },
            {
                "object_key": "reverse1999/voice/c.mp3",
                "size": 30,
                "etag": "etag-c",
                "version_id": None,
            },
        ],
    )

    rows = {row["object_key"]: row for row in merged["objects"]}
    assert rows["reverse1999/voice/a.mp3"]["sha256"] == "2" * 64
    assert rows["reverse1999/voice/a.mp3"]["application_operation_id"] == "op-1"
    assert rows["reverse1999/voice/b.mp3"]["sha256"] == ""
    assert rows["reverse1999/voice/c.mp3"]["sha256"] == ""


def test_acceptance_snapshot_and_compare_write_hash_pinned_evidence(tmp_path: Path):
    cfg = SimpleNamespace(paths=SimpleNamespace(project_root=tmp_path))
    before_path = tmp_path / "eval" / "protected.pre.v2.json"

    assert acceptance_main(
        ["snapshot", "--output", str(before_path)],
        cfg_loader=lambda: cfg,
        snapshot_loader=lambda _cfg: _Snapshot(_protected_payload(captured="before")),
    ) == 0
    assert before_path.with_name(before_path.name + ".sha256").is_file()

    compare_path = tmp_path / "eval" / "protected.compare.v2.json"
    assert acceptance_main(
        ["compare", "--before", str(before_path), "--output", str(compare_path)],
        cfg_loader=lambda: cfg,
        snapshot_loader=lambda _cfg: _Snapshot(_protected_payload(captured="after")),
    ) == 0
    assert json.loads(compare_path.read_text(encoding="utf-8"))["status"] == "pass"


def test_acceptance_compare_blocks_protected_artifact_drift(tmp_path: Path):
    cfg = SimpleNamespace(paths=SimpleNamespace(project_root=tmp_path))
    before_path = tmp_path / "eval" / "protected.pre.v2.json"
    assert acceptance_main(
        ["snapshot", "--output", str(before_path)],
        cfg_loader=lambda: cfg,
        snapshot_loader=lambda _cfg: _Snapshot(_protected_payload()),
    ) == 0
    output = tmp_path / "eval" / "protected.changed.v2.json"

    exit_code = acceptance_main(
        ["compare", "--before", str(before_path), "--output", str(output)],
        cfg_loader=lambda: cfg,
        snapshot_loader=lambda _cfg: _Snapshot(_protected_payload(artifact_sha="9" * 64)),
    )

    assert exit_code == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["changes"] == ["artifacts changed"]


def test_acceptance_compare_records_exact_artifact_additions(tmp_path: Path):
    cfg = SimpleNamespace(paths=SimpleNamespace(project_root=tmp_path))
    before = _protected_payload(captured="before")
    before_path = tmp_path / "eval" / "protected.pre.v2.json"
    assert acceptance_main(
        ["snapshot", "--output", str(before_path)],
        cfg_loader=lambda: cfg,
        snapshot_loader=lambda _cfg: _Snapshot(before),
    ) == 0

    relative_path = "data/processed/huiji/operations/op-1/plan.json"
    addition = {"sha256": "1" * 64, "size": 42}
    after = json.loads(json.dumps(before))
    after["captured_at_utc"] = "after"
    after["artifacts"][relative_path] = addition
    output = tmp_path / "eval" / "protected.allowed.v2.json"
    token = f"{relative_path}|{addition['sha256']}|{addition['size']}"

    assert acceptance_main(
        [
            "compare",
            "--before",
            str(before_path),
            "--output",
            str(output),
            "--allow-artifact-addition",
            token,
        ],
        cfg_loader=lambda: cfg,
        snapshot_loader=lambda _cfg: _Snapshot(after),
    ) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["allowed_artifact_additions"] == {relative_path: addition}


def test_dynamic_source_sampling_uses_entity_types_without_exposing_names():
    child = SimpleNamespace(
        child_id="char:1/profile:0000",
        entity_id="char:1",
        section_kind="profile",
        route_tags=("intro",),
    )
    entity = SimpleNamespace(
        entity_id="char:1",
        entity_name="Private Character Name",
        entity_type="character",
        aliases=(),
        child_ids_by_intent={"intro": (child.child_id,)},
    )
    inventory = SimpleNamespace(
        entities={entity.entity_id: entity},
        children={child.child_id: child},
    )

    class Retriever:
        def search(self, query, k, query_plan):
            assert query == entity.entity_name
            assert query_plan.entity_id == entity.entity_id
            return [
                {
                    "entity_id": entity.entity_id,
                    "child_id": child.child_id,
                    "retrieval_stage": "huiji_hybrid",
                }
            ]

    payload = sample_active_sources(
        SimpleNamespace(rag=SimpleNamespace(top_k=5)),
        inventory_loader=lambda _cfg: inventory,
        vectorstore_loader=lambda _cfg: object(),
        retriever_factory=lambda _cfg, _vs: Retriever(),
    )

    serialized = json.dumps(payload)
    assert payload["status"] == "pass"
    assert payload["samples"][0]["entity_type"] == "character"
    assert payload["samples"][0]["stages"] == ["huiji_hybrid"]
    assert "Private Character Name" not in serialized
    assert "char:1" not in serialized


def test_current_docs_name_huiji_as_the_only_rag_source_and_disable_legacy_commands():
    readme_head = "\n".join((ROOT / "README.md").read_text(encoding="utf-8").splitlines()[:35])
    architecture_head = "\n".join(
        (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8").splitlines()[:90]
    )
    runbook = (ROOT / "docs" / "huiji-rag-runbook.md").read_text(encoding="utf-8")

    assert "huiji_crawler" in readme_head
    assert "text_child_bge_m3_v3" in readme_head
    assert "provenance" in readme_head.lower()
    assert "旧命令已禁用" in readme_head

    assert "Huiji crawler" in architecture_head
    assert "provenance" in architecture_head.lower()
    assert "历史架构" in architecture_head

    assert "audit_huiji_provenance.py audit" in runbook
    assert "audit_huiji_provenance.py install-baseline" in runbook
    assert "verify_huiji_runtime.py" in runbook
    assert "build_huiji_index.py" in runbook
    assert "--collection-name" in runbook
    assert "不激活" in runbook
    assert "不删除" in runbook
    assert "scripts/extract_data.py" not in runbook
    assert "scripts/build_index.py" not in runbook
    assert "scripts/build_assets.py" not in runbook
    assert "切回旧 Obsidian" not in runbook
