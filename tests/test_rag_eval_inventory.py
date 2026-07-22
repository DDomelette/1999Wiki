from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.rag_eval.contracts import JudgeIdentity, Severity
from src.rag_eval.inventory import (
    InventoryError,
    MilvusSnapshot,
    ProtectedDataSnapshot,
    build_inventory,
    capture_artifact_digests,
    capture_mysql_table_digests,
    capture_protected_snapshot,
    capture_milvus_snapshot_from_client,
    compare_protected_snapshots,
    compare_snapshots,
    reconstruct_context,
    run_preflight,
)


def _fixture_rows():
    parents = [
        {
            "parent_id": "fixture:entity-1/profile",
            "entity_id": "entity-1",
            "entity_name": "测试实体甲",
            "entity_aliases": ["实体甲"],
            "entity_type": "character",
            "category": "character",
            "section_kind": "profile",
            "child_ids": ["fixture:entity-1/profile:0001"],
        },
        {
            "parent_id": "fixture:entity-1/skills",
            "entity_id": "entity-1",
            "entity_name": "测试实体甲",
            "entity_type": "character",
            "category": "character",
            "section_kind": "skills",
            "child_ids": ["fixture:entity-1/skill:0001"],
        },
    ]
    children = [
        {
            "child_id": "fixture:entity-1/profile:0001",
            "parent_id": "fixture:entity-1/profile",
            "entity_id": "entity-1",
            "entity_name": "测试实体甲",
            "entity_type": "character",
            "category": "character",
            "section_kind": "profile",
            "title": "测试实体甲 / 基础资料",
            "route_tags": ["intro", "profile_fact", "media"],
            "text": "稀有度: 5",
            "media_ids": [],
        },
        {
            "child_id": "fixture:entity-1/skill:0001",
            "parent_id": "fixture:entity-1/skills",
            "entity_id": "entity-1",
            "entity_name": "测试实体甲",
            "entity_type": "character",
            "category": "character",
            "section_kind": "skill",
            "title": "测试实体甲 / 技能",
            "route_tags": ["skill"],
            "text": "技能文本",
            "media_ids": ["media:sha1:" + "a" * 40],
        },
    ]
    media = [
        {
            "media_id": "media:sha1:" + "a" * 40,
            "entity_id": "entity-1",
            "entity_name": "测试实体甲",
            "parent_id": "fixture:entity-1/skills",
            "child_id": "fixture:entity-1/skill:0001",
            "asset_type": "voice",
            "mime": "audio/mpeg",
            "url": "http://127.0.0.1:9002/bucket/voice.mp3",
            "is_available": True,
            "is_common": False,
            "language": "zh",
            "local_relpath": "private/path/voice.mp3",
        }
    ]
    return parents, children, media


def test_inventory_derives_entities_intents_and_media_from_rows():
    parents, children, media = _fixture_rows()
    inventory = build_inventory(parents, children, media, build_version="fixture")

    entity = inventory.entities["entity-1"]
    assert entity.aliases == ("实体甲",)
    assert entity.child_ids_by_intent["skill"] == ("fixture:entity-1/skill:0001",)
    assert entity.media_ids_by_type["voice"] == ("media:sha1:" + "a" * 40,)
    assert inventory.children["fixture:entity-1/profile:0001"].text == "稀有度: 5"
    assert not hasattr(inventory.media["media:sha1:" + "a" * 40][0], "local_relpath")
    assert len(inventory.sha256) == 64


def test_inventory_rejects_media_with_unknown_child():
    parents, children, media = _fixture_rows()
    media[0]["child_id"] = "fixture:missing"

    with pytest.raises(InventoryError, match="unknown child"):
        build_inventory(parents, children, media, build_version="fixture")


def test_reconstruct_context_uses_observed_order_and_labels():
    parents, children, media = _fixture_rows()
    inventory = build_inventory(parents, children, media, build_version="fixture")
    observed = [
        {
            "child_id": "fixture:entity-1/skill:0001",
            "name": "测试实体甲",
            "heading_path": "技能",
        },
        {
            "child_id": "fixture:entity-1/profile:0001",
            "name": "测试实体甲",
            "heading_path": "",
        },
    ]

    context = reconstruct_context(inventory, observed)

    assert context == "[测试实体甲 / 技能] 技能文本\n\n[测试实体甲] 稀有度: 5"


def test_reconstruct_context_prefers_current_short_citation_ids():
    parents, children, media = _fixture_rows()
    inventory = build_inventory(parents, children, media, build_version="fixture")

    context = reconstruct_context(
        inventory,
        [
            {
                "citation_id": "S01",
                "child_id": "fixture:entity-1/skill:0001",
                "name": "测试实体甲",
                "heading_path": "技能",
            }
        ],
    )

    assert context == "[S01] 测试实体甲 / 技能\n技能文本"


def test_reconstruct_context_rejects_unresolved_source():
    parents, children, media = _fixture_rows()
    inventory = build_inventory(parents, children, media, build_version="fixture")

    with pytest.raises(InventoryError, match="unresolved source"):
        reconstruct_context(inventory, [{"child_id": "fixture:unknown", "name": "x"}])


class _Iterator:
    def __init__(self, batches):
        self._batches = iter(batches)
        self.closed = False

    def next(self):
        return next(self._batches, [])

    def close(self):
        self.closed = True


class _MilvusClient:
    def __init__(self, ids):
        self.ids = ids
        self.output_fields = None

    def has_collection(self, name):
        return True

    def describe_collection(self, name):
        return {
            "collection_name": name,
            "fields": [
                {"name": "id", "is_primary": True, "type": 21},
                {"name": "embedding", "type": 101},
            ],
        }

    def get_collection_stats(self, name):
        return {"row_count": str(len(self.ids))}

    def get_load_state(self, name):
        return {"state": "Loaded"}

    def query_iterator(self, collection_name, batch_size, limit, filter, output_fields):
        self.output_fields = output_fields
        return _Iterator([[{"id": item} for item in self.ids[:2]], [{"id": item} for item in self.ids[2:]]])


def _sha256_lines(values):
    return hashlib.sha256("".join(f"{item}\n" for item in sorted(values)).encode()).hexdigest()


def test_snapshot_hashes_all_primary_ids_without_requesting_vectors():
    client = _MilvusClient(["c", "a", "b"])

    snapshot = capture_milvus_snapshot_from_client(client, "collection")

    assert snapshot.primary_field == "id"
    assert snapshot.primary_id_count == 3
    assert snapshot.primary_ids_sha256 == _sha256_lines(["a", "b", "c"])
    assert client.output_fields == ["id"]


def test_snapshot_comparison_detects_same_count_different_ids():
    before = MilvusSnapshot(
        collection_name="c",
        schema_sha256="s",
        row_count=2,
        primary_field="id",
        primary_id_count=2,
        primary_ids_sha256="a",
        load_state={"state": "Loaded"},
        captured_at_utc="before",
    )
    after = MilvusSnapshot(**{**before.__dict__, "primary_ids_sha256": "b", "captured_at_utc": "after"})

    assert compare_snapshots(before, after) == ["primary_ids_sha256 changed"]


def test_protected_snapshot_ignores_capture_time_but_detects_object_drift():
    milvus = MilvusSnapshot(
        collection_name="c",
        schema_sha256="s",
        row_count=2,
        primary_field="id",
        primary_id_count=2,
        primary_ids_sha256="a",
        load_state={"state": "Loaded"},
        captured_at_utc="before",
    )
    before = ProtectedDataSnapshot(
        milvus=milvus,
        minio_inventories={
            "bucket/prefix": {
                "captured_at_utc": "before",
                "inventory_sha256": "capture-specific-a",
                "objects": [{"object_key": "prefix/a", "sha256": "1" * 64}],
            }
        },
        mysql_tables={"wiki_pages": {"row_count": 1, "sha256": "2" * 64}},
        artifacts={"data/a.json": {"size": 1, "sha256": "3" * 64}},
        captured_at_utc="before",
    )
    recaptured = ProtectedDataSnapshot(
        **{
            **before.__dict__,
            "minio_inventories": {
                "bucket/prefix": {
                    **before.minio_inventories["bucket/prefix"],
                    "captured_at_utc": "after",
                    "inventory_sha256": "capture-specific-b",
                }
            },
            "captured_at_utc": "after",
        }
    )

    assert compare_protected_snapshots(before, recaptured) == []

    drifted = ProtectedDataSnapshot(
        **{
            **recaptured.__dict__,
            "minio_inventories": {
                "bucket/prefix": {
                    **recaptured.minio_inventories["bucket/prefix"],
                    "objects": [{"object_key": "prefix/a", "sha256": "4" * 64}],
                }
            },
        }
    )
    assert compare_protected_snapshots(before, drifted) == ["minio_inventories changed"]


class _ReadOnlyCursor:
    def __init__(self):
        self.commands = []
        self.description = (("page_id",), ("title",))
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql):
        self.commands.append(" ".join(sql.split()))
        if sql.startswith("SHOW KEYS"):
            self._rows = [{"Column_name": "page_id"}]
        elif sql.startswith("SELECT"):
            self._rows = [
                {"page_id": "p2", "title": "乙"},
                {"page_id": "p1", "title": "甲"},
            ]
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)


class _ReadOnlyConnection:
    def __init__(self):
        self.cursor_value = _ReadOnlyCursor()
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_mysql_snapshot_establishes_read_only_transaction_and_emits_only_digests():
    connection = _ReadOnlyConnection()

    result = capture_mysql_table_digests(
        SimpleNamespace(mysql=SimpleNamespace()),
        tables=("wiki_pages",),
        connection_factory=lambda _cfg: connection,
    )

    assert connection.cursor_value.commands[:2] == [
        "SET TRANSACTION READ ONLY",
        "START TRANSACTION WITH CONSISTENT SNAPSHOT",
    ]
    assert connection.cursor_value.commands[-1].endswith("ORDER BY `page_id`")
    assert result["wiki_pages"]["row_count"] == 2
    assert set(result["wiki_pages"]) == {"row_count", "sha256"}
    assert "甲" not in repr(result)
    assert connection.rolled_back is True
    assert connection.closed is True


def test_artifact_snapshot_records_relative_path_size_and_sha256(tmp_path: Path):
    project = tmp_path / "project"
    processed = project / "data" / "processed" / "huiji" / "build-a"
    processed.mkdir(parents=True)
    (processed / "child_blocks.jsonl").write_text("fixture\n", encoding="utf-8")
    eval_dir = project / "eval"
    eval_dir.mkdir()
    (eval_dir / "rag_full_chain_thresholds.v1.json").write_text("{}\n", encoding="utf-8")
    cfg = SimpleNamespace(
        paths=SimpleNamespace(project_root=project),
        huiji=SimpleNamespace(processed_root=project / "data" / "processed" / "huiji"),
    )

    result = capture_artifact_digests(cfg)

    assert set(result) == {
        "data/processed/huiji/build-a/child_blocks.jsonl",
        "eval/rag_full_chain_thresholds.v1.json",
    }
    assert all(set(item) == {"size", "sha256"} for item in result.values())


def test_artifact_snapshot_excludes_operational_locks_and_runtime_logs(
    tmp_path: Path,
):
    project = tmp_path / "project"
    processed_root = project / "data" / "processed" / "huiji"
    processed_root.mkdir(parents=True)
    (processed_root / ".generation-zero-bootstrap.lock").write_bytes(b"locked")
    (processed_root / ".candidate-activation.lock").write_bytes(b"locked")
    (processed_root / ".other-hidden-artifact").write_bytes(b"protected")
    runtime = processed_root / "activation" / "transactions" / "op" / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "backend.stdout.log").write_bytes(b"mutable")
    (runtime / "process.json").write_bytes(b"protected")
    cfg = SimpleNamespace(
        paths=SimpleNamespace(project_root=project),
        huiji=SimpleNamespace(processed_root=processed_root),
    )

    result = capture_artifact_digests(cfg)

    assert "data/processed/huiji/.generation-zero-bootstrap.lock" not in result
    assert "data/processed/huiji/.candidate-activation.lock" not in result
    assert "data/processed/huiji/.other-hidden-artifact" in result
    assert "data/processed/huiji/activation/transactions/op/runtime/backend.stdout.log" not in result
    assert "data/processed/huiji/activation/transactions/op/runtime/process.json" in result


def test_capture_protected_snapshot_collects_all_sections():
    milvus = SimpleNamespace(to_json=lambda: {"ids": "stable"})

    snapshot = capture_protected_snapshot(
        SimpleNamespace(),
        milvus_loader=lambda _cfg: milvus,
        minio_loader=lambda _cfg: {"bucket/prefix": {"objects": []}},
        mysql_loader=lambda _cfg: {"wiki_pages": {"row_count": 1, "sha256": "a" * 64}},
        artifact_loader=lambda _cfg: {"data/a": {"size": 1, "sha256": "b" * 64}},
    )

    assert snapshot.milvus is milvus
    assert set(snapshot.to_json()) == {
        "schema_version",
        "milvus",
        "minio_inventories",
        "mysql_tables",
        "artifacts",
        "captured_at_utc",
    }


def test_preflight_rejects_identical_judge_and_production_model():
    cfg = SimpleNamespace(
        llm=SimpleNamespace(base_url="https://llm.example/v1", model="same", api_key="key"),
        assets=SimpleNamespace(public_base_url="http://127.0.0.1:9002"),
    )
    identity = JudgeIdentity(
        base_url="https://llm.example/v1",
        model="same",
        prompt_version="rag-answer-judge/v1",
    )

    result = run_preflight(
        cfg,
        "http://127.0.0.1:8000",
        identity,
        backend_health=lambda _url: {"status": "ok", "vectorstore_loaded": True, "llm_ready": True},
        minio_health=lambda _url: True,
        inventory_loader=lambda _cfg: object(),
        snapshot_loader=lambda _cfg: object(),
    )

    assert result.allowed_to_run is False
    assert result.severity is Severity.SEV0
    assert result.events[0].event_code == "READY.JUDGE_NOT_INDEPENDENT"
