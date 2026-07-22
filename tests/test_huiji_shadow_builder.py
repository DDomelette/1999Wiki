from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import build_huiji_index as shadow_script
from src.huiji_rag.provenance import VerificationIssue, VerificationResult
from src.huiji_rag.build.contracts import canonical_json_bytes
from src.rag.vectorstore import (
    HUIJI_BUSINESS_FIELDS,
    build_huiji_shadow_collection,
    huiji_child_to_business_row,
)


def _children() -> list[dict[str, object]]:
    return [
        {"child_id": "c1", "parent_id": "p1", "text": "A", "source_refs": []},
        {"child_id": "c2", "parent_id": "p2", "text": "B", "source_refs": []},
        {"child_id": "c3", "parent_id": "p3", "text": "C", "source_refs": []},
    ]


class _Embeddings:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return [[float(index), 0.0] for index, _text in enumerate(texts, start=1)]


class _Iterator:
    def __init__(self, rows):
        self.rows = list(rows)
        self.done = False

    def next(self):
        if self.done:
            return []
        self.done = True
        return self.rows

    def close(self):
        return None


class _ShadowClient:
    def __init__(self, existing: tuple[str, ...] = ()):
        self.collections = {name: [] for name in existing}
        self.mutations: list[str] = []
        self.flushes: list[str] = []

    def has_collection(self, collection_name):
        return collection_name in self.collections

    def create_for_test(self, collection_name):
        if collection_name in self.collections:
            raise RuntimeError("already exists")
        self.collections[collection_name] = []
        self.mutations.append("create")

    def insert(self, collection_name, data):
        self.collections[collection_name].extend(dict(row) for row in data)
        self.mutations.append("insert")

    def flush(self, collection_name):
        self.flushes.append(collection_name)

    def delete(self, **_kwargs):
        self.mutations.append("delete")

    def drop_collection(self, **_kwargs):
        self.mutations.append("drop")

    def describe_collection(self, collection_name):
        fields = [
            {
                "name": name,
                "type": 21,
                "is_primary": name == "id",
                "auto_id": False,
                "params": {},
            }
            for name in HUIJI_BUSINESS_FIELDS
        ]
        fields.append({"name": "embedding", "type": 101, "params": {"dim": 1024}})
        return {"collection_name": collection_name, "enable_dynamic_field": True, "fields": fields}

    def query_iterator(self, collection_name, **_kwargs):
        rows = [
            {field: row[field] for field in HUIJI_BUSINESS_FIELDS}
            for row in self.collections[collection_name]
        ]
        return _Iterator(rows)

    def get_collection_stats(self, collection_name):
        return {"row_count": len(self.collections[collection_name])}


def _cfg(tmp_path: Path | None = None):
    root = tmp_path or Path.cwd()
    if tmp_path is not None:
        settings = root / "config" / "settings.yaml"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("huiji: true\n", encoding="utf-8")
    return SimpleNamespace(
        paths=SimpleNamespace(project_root=root),
        embedding=SimpleNamespace(
            provider="test", model="test-model", api_key="test-key"
        ),
        huiji=SimpleNamespace(
            provenance_baseline=root / "config" / "provenance" / "huiji-dev.v1.json",
            processed_root=root / "data" / "processed" / "huiji",
            build_version="dev",
            text_collection_name="active_v3",
        ),
        vectorstore=SimpleNamespace(
            uri="http://127.0.0.1:19600",
            db_name="reverse1999_rag",
            collection_name="active_v3",
        ),
    )


def _write_handoff(tmp_path: Path, cfg, children=None) -> tuple[Path, str]:
    rows = list(children or _children())
    build_root = tmp_path / "data" / "processed" / "huiji" / "crawler-v3-test"
    build_root.mkdir(parents=True)
    child_path = build_root / "child_blocks.jsonl"
    child_bytes = b"".join(canonical_json_bytes(row) for row in rows)
    child_path.write_bytes(child_bytes)
    child_ids = [str(row["child_id"]) for row in rows]
    ordered_ids = hashlib.sha256(
        "".join(f"{value}\n" for value in child_ids).encode("utf-8")
    ).hexdigest()
    embedding_fingerprint = hashlib.sha256(
        canonical_json_bytes(
            {
                "schema_version": "huiji.embedding-config/v1",
                "provider": cfg.embedding.provider,
                "model": cfg.embedding.model,
            },
            trailing_newline=False,
        )
    ).hexdigest()
    handoff = build_root / "handoff" / "embedding_handoff.v1.json"
    handoff.parent.mkdir()
    handoff.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "huiji.embedding-handoff/v1",
                "build_version": "crawler-v3-test",
                "child_artifact": {
                    "relative_path": "child_blocks.jsonl",
                    "row_count": len(rows),
                    "schema_version": "huiji.child-blocks/v2",
                    "sha256": hashlib.sha256(child_bytes).hexdigest(),
                    "size": len(child_bytes),
                },
                "child_bm25": {},
                "child_ordered_ids_sha256": ordered_ids,
                "child_semantic_corpus_sha256": shadow_script.canonical_child_corpus_sha256(rows),
                "embedding_config_fingerprint_sha256": embedding_fingerprint,
                "target_requirements": {
                    "must_be_new": True,
                    "must_not_be_active": True,
                    "must_not_exist": True,
                    "forbidden_collection_names": ["active_v3"],
                },
            }
        )
    )
    return handoff, hashlib.sha256(handoff.read_bytes()).hexdigest()


def _ensure(client: _ShadowClient, name: str):
    client.create_for_test(name)


def test_shadow_builder_rejects_active_name_before_client_or_embedding():
    client_calls = 0
    embeddings = _Embeddings()

    def client_factory(_cfg):
        nonlocal client_calls
        client_calls += 1
        return _ShadowClient()

    with pytest.raises(ValueError, match="active collection"):
        build_huiji_shadow_collection(
            _cfg(),
            _children(),
            collection_name="active_v3",
            active_collection_names=("active_v3",),
            client_factory=client_factory,
            embeddings_factory=lambda _cfg: embeddings,
            collection_ensurer=_ensure,
        )

    assert client_calls == 0
    assert embeddings.calls == 0


def test_shadow_builder_rejects_existing_target_before_embedding():
    client = _ShadowClient(existing=("shadow_v1",))
    embeddings = _Embeddings()

    with pytest.raises(FileExistsError, match="already exists"):
        build_huiji_shadow_collection(
            _cfg(),
            _children(),
            collection_name="shadow_v1",
            active_collection_names=("active_v3",),
            client_factory=lambda _cfg: client,
            embeddings_factory=lambda _cfg: embeddings,
            collection_ensurer=_ensure,
        )

    assert embeddings.calls == 0
    assert client.mutations == []


def test_shadow_builder_creates_new_collection_without_mutating_active_config():
    cfg = _cfg()
    client = _ShadowClient(existing=("active_v3",))
    embeddings = _Embeddings()
    original_collection = cfg.vectorstore.collection_name

    inserted = build_huiji_shadow_collection(
        cfg,
        _children(),
        collection_name="shadow_v1",
        active_collection_names=("active_v3",),
        batch_size=2,
        batch_delay_seconds=0,
        client_factory=lambda _cfg: client,
        embeddings_factory=lambda _cfg: embeddings,
        collection_ensurer=_ensure,
    )

    assert inserted == 3
    assert cfg.vectorstore.collection_name == original_collection
    assert len(client.collections["shadow_v1"]) == 3
    assert client.mutations == ["create", "insert", "insert"]
    assert "delete" not in client.mutations
    assert "drop" not in client.mutations
    assert client.flushes == ["shadow_v1"]
    assert [
        {field: row[field] for field in HUIJI_BUSINESS_FIELDS}
        for row in client.collections["shadow_v1"]
    ] == [huiji_child_to_business_row(child) for child in _children()]


def test_shadow_builder_retains_created_collection_on_embedding_failure():
    client = _ShadowClient()
    embeddings = _Embeddings(fail=True)

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        build_huiji_shadow_collection(
            _cfg(),
            _children(),
            collection_name="shadow_failed",
            active_collection_names=("active_v3",),
            batch_delay_seconds=0,
            max_retries=0,
            client_factory=lambda _cfg: client,
            embeddings_factory=lambda _cfg: embeddings,
            collection_ensurer=_ensure,
        )

    assert "shadow_failed" in client.collections
    assert client.mutations == ["create"]


def test_shadow_cli_requires_collection_name_before_loading_config():
    with pytest.raises(SystemExit) as error:
        shadow_script.main([], cfg_loader=lambda: pytest.fail("config loaded"))

    assert error.value.code == 2


def test_shadow_cli_blocks_failed_provenance_before_embedding_or_mutation(
    tmp_path: Path,
    monkeypatch,
):
    cfg = _cfg(tmp_path)
    handoff, handoff_sha = _write_handoff(tmp_path, cfg)
    client = _ShadowClient()
    embeddings = _Embeddings()
    monkeypatch.setattr(
        shadow_script,
        "verify_runtime",
        lambda _cfg, client_factory: VerificationResult(
            status="blocked",
            issues=(VerificationIssue("artifact_hash_mismatch", "child_blocks"),),
            baseline_sha256="a" * 64,
        ),
    )

    exit_code = shadow_script.main(
        [
            "--collection-name",
            "shadow_v1",
            "--handoff-manifest",
            str(handoff),
            "--expected-handoff-sha256",
            handoff_sha,
            "--run-dir",
            str(tmp_path / "eval" / "shadow-blocked"),
        ],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
        embeddings_factory=lambda _cfg: embeddings,
    )

    assert exit_code == 2
    assert embeddings.calls == 0
    assert client.mutations == []
    evidence = tmp_path / "eval" / "shadow-blocked" / "shadow-build.v1.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["failure_code"] == "artifact_hash_mismatch"


def test_shadow_cli_rejects_bad_handoff_hash_before_embedding_or_mutation(
    tmp_path: Path,
):
    cfg = _cfg(tmp_path)
    handoff, _handoff_sha = _write_handoff(tmp_path, cfg)
    client = _ShadowClient()
    embeddings = _Embeddings()

    exit_code = shadow_script.main(
        [
            "--collection-name",
            "shadow_v1",
            "--handoff-manifest",
            str(handoff),
            "--expected-handoff-sha256",
            "f" * 64,
            "--run-dir",
            str(tmp_path / "eval" / "shadow-bad-handoff"),
        ],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
        embeddings_factory=lambda _cfg: embeddings,
    )

    assert exit_code == 2
    assert embeddings.calls == 0
    assert client.mutations == []
    evidence = tmp_path / "eval" / "shadow-bad-handoff" / "shadow-build.v1.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["failure_code"] == "embedding_handoff_hash_mismatch"


def test_shadow_cli_blocks_missing_embedding_credentials_before_milvus(
    tmp_path: Path,
):
    cfg = _cfg(tmp_path)
    handoff, handoff_sha = _write_handoff(tmp_path, cfg)
    cfg.embedding.api_key = ""
    client_calls = 0

    def client_factory(_cfg):
        nonlocal client_calls
        client_calls += 1
        return _ShadowClient()

    exit_code = shadow_script.main(
        [
            "--collection-name",
            "shadow_v1",
            "--handoff-manifest",
            str(handoff),
            "--expected-handoff-sha256",
            handoff_sha,
            "--run-dir",
            str(tmp_path / "eval" / "shadow-no-credentials"),
        ],
        cfg_loader=lambda: cfg,
        client_factory=client_factory,
        embeddings_factory=lambda _cfg: pytest.fail("embedding model loaded"),
    )

    assert exit_code == 2
    assert client_calls == 0
    evidence = tmp_path / "eval" / "shadow-no-credentials" / "shadow-build.v1.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["failure_code"] == "embedding_credentials_missing"


def test_shadow_cli_builds_from_hash_pinned_candidate_handoff(
    tmp_path: Path,
    monkeypatch,
):
    cfg = _cfg(tmp_path)
    handoff, handoff_sha = _write_handoff(tmp_path, cfg)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        shadow_script,
        "verify_runtime",
        lambda _cfg, client_factory: VerificationResult(
            status="pass", issues=(), baseline_sha256="b" * 64
        ),
    )
    monkeypatch.setattr(
        shadow_script,
        "load_provenance_baseline",
        lambda *_args, **_kwargs: (
            {"milvus": {"collection": "active_v3", "schema_sha256": "schema"}},
            "b" * 64,
        ),
    )

    def fake_build(_cfg, children, **kwargs):
        captured["children"] = children
        captured["collection"] = kwargs["collection_name"]
        return len(children)

    monkeypatch.setattr(shadow_script, "build_huiji_shadow_collection", fake_build)

    class Fingerprint:
        schema_sha256 = "schema"
        row_count = 3
        primary_ids_sha256 = shadow_script._sha256_ids(["c1", "c2", "c3"])
        business_fields_sha256 = shadow_script._sha256_rows(
            [huiji_child_to_business_row(child) for child in _children()]
        )

        def to_json(self):
            return {
                "schema_sha256": self.schema_sha256,
                "row_count": self.row_count,
                "primary_ids_sha256": self.primary_ids_sha256,
                "business_fields_sha256": self.business_fields_sha256,
            }

    monkeypatch.setattr(
        shadow_script,
        "capture_milvus_fingerprint",
        lambda *_args, **_kwargs: Fingerprint(),
    )

    exit_code = shadow_script.main(
        [
            "--collection-name",
            "shadow_candidate_v1",
            "--handoff-manifest",
            str(handoff),
            "--expected-handoff-sha256",
            handoff_sha,
            "--run-dir",
            str(tmp_path / "eval" / "shadow-pass"),
        ],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: _ShadowClient(existing=("active_v3",)),
        embeddings_factory=lambda _cfg: _Embeddings(),
    )

    assert exit_code == 0
    assert captured["children"] == _children()
    assert captured["collection"] == "shadow_candidate_v1"
    evidence = tmp_path / "eval" / "shadow-pass" / "shadow-build.v1.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["handoff_sha256"] == handoff_sha
    assert payload["candidate_build_version"] == "crawler-v3-test"
