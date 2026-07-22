from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.huiji_rag.io import write_jsonl
from src.huiji_rag.provenance import (
    ArtifactFingerprint,
    AuditResult,
    MilvusFingerprint,
    ProvenanceValidationError,
    VerificationIssue,
    VerificationResult,
    canonical_json_bytes,
    fingerprint_bm25,
    fingerprint_jsonl,
    capture_milvus_fingerprint,
    audit_huiji_provenance,
    build_baseline_candidate,
    install_baseline_create_new,
    verify_runtime,
    safe_relative_path,
    write_hash_pinned_json,
)
from src.rag.vectorstore import HUIJI_BUSINESS_FIELDS, huiji_child_to_business_row
from scripts.audit_huiji_provenance import main as audit_cli_main
from scripts.verify_huiji_runtime import main as runtime_cli_main
import scripts.verify_huiji_runtime as runtime_cli


def test_canonical_json_and_hash_pinned_evidence_are_stable_and_create_new(tmp_path: Path):
    target = tmp_path / "nested" / "evidence.v1.json"
    payload = {"z": 1, "a": ["文本", 2]}

    digest = write_hash_pinned_json(target, payload)

    assert target.read_bytes() == '{"a":["文本",2],"z":1}\n'.encode("utf-8")
    assert target.with_name("evidence.v1.json.sha256").read_text(encoding="ascii") == (
        f"{digest}  evidence.v1.json\n"
    )
    with pytest.raises(FileExistsError):
        write_hash_pinned_json(target, payload)


def test_canonical_json_rejects_non_finite_numbers():
    with pytest.raises(ValueError, match="finite"):
        canonical_json_bytes({"value": float("nan")})


def test_safe_relative_path_rejects_escape_and_absolute_output(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()

    assert safe_relative_path(root / "data" / "x.jsonl", root) == "data/x.jsonl"
    with pytest.raises(ProvenanceValidationError, match="outside project root") as error:
        safe_relative_path(tmp_path / "outside.jsonl", root)
    assert error.value.code == "path_outside_project"


def test_jsonl_fingerprint_tracks_file_rows_ids_and_semantics(tmp_path: Path):
    path = tmp_path / "child_blocks.jsonl"
    write_jsonl(
        path,
        [
            {"child_id": "c2", "text": "B"},
            {"child_id": "c1", "text": "A"},
        ],
    )

    fingerprint = fingerprint_jsonl(
        path,
        project_root=tmp_path,
        id_field="child_id",
        require_unique_ids=True,
    )

    assert isinstance(fingerprint, ArtifactFingerprint)
    assert fingerprint.relative_path == "child_blocks.jsonl"
    assert fingerprint.row_count == 2
    assert fingerprint.id_count == 2
    assert fingerprint.unique_id_count == 2
    assert fingerprint.size_bytes == path.stat().st_size
    assert all(
        len(value) == 64
        for value in (
            fingerprint.sha256,
            fingerprint.ids_sha256,
            fingerprint.semantic_sha256,
        )
    )


def test_jsonl_fingerprint_rejects_duplicate_required_ids(tmp_path: Path):
    path = tmp_path / "child_blocks.jsonl"
    write_jsonl(path, [{"child_id": "same"}, {"child_id": "same"}])

    with pytest.raises(ProvenanceValidationError) as error:
        fingerprint_jsonl(
            path,
            project_root=tmp_path,
            id_field="child_id",
            require_unique_ids=True,
        )

    assert error.value.code == "artifact_id_mismatch"


def test_jsonl_fingerprint_preserves_duplicate_media_occurrences(tmp_path: Path):
    path = tmp_path / "media_assets.jsonl"
    write_jsonl(
        path,
        [
            {"media_id": "m1", "child_id": "c1"},
            {"media_id": "m1", "child_id": "c2"},
        ],
    )

    fingerprint = fingerprint_jsonl(
        path,
        project_root=tmp_path,
        id_field="media_id",
        require_unique_ids=False,
    )

    assert fingerprint.id_count == 2
    assert fingerprint.unique_id_count == 1


def test_bm25_fingerprint_requires_semantic_equality_with_source_rows(tmp_path: Path):
    source_rows = [
        {"child_id": "c1", "text": "A"},
        {"child_id": "c2", "text": "B"},
    ]
    path = tmp_path / "child_bm25.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {"id": "c2", "child_id": "c2", "text": "B"},
                    {"id": "c1", "child_id": "c1", "text": "A"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    fingerprint = fingerprint_bm25(
        path,
        project_root=tmp_path,
        source_rows=source_rows,
        source_id_field="child_id",
    )

    assert fingerprint.row_count == 2
    assert len(fingerprint.semantic_sha256) == 64

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"][0]["text"] = "changed"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ProvenanceValidationError) as error:
        fingerprint_bm25(
            path,
            project_root=tmp_path,
            source_rows=source_rows,
            source_id_field="child_id",
        )
    assert error.value.code == "bm25_semantic_mismatch"


def test_bm25_fingerprint_rejects_derived_id_mismatch(tmp_path: Path):
    path = tmp_path / "child_bm25.json"
    path.write_text(
        json.dumps({"records": [{"id": "wrong", "child_id": "c1", "text": "A"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ProvenanceValidationError) as error:
        fingerprint_bm25(
            path,
            project_root=tmp_path,
            source_rows=[{"child_id": "c1", "text": "A"}],
            source_id_field="child_id",
        )
    assert error.value.code == "bm25_id_mismatch"


def test_public_verification_payload_sanitizes_paths_secrets_and_source_text():
    result = VerificationResult(
        status="blocked",
        issues=(
            VerificationIssue(
                code="artifact_hash_mismatch",
                component="child_blocks",
                expected=r"D:\private\child.jsonl",
                actual="MINIO_SECRET_KEY=do-not-leak",
            ),
            VerificationIssue(
                code="verification_internal_error",
                component="milvus",
                actual="真实来源正文不应进入诊断",
            ),
        ),
        baseline_sha256="a" * 64,
        evidence_relpath="eval/huiji_provenance/run/runtime.v1.json",
    )

    serialized = json.dumps(result.to_public_dict(), ensure_ascii=False)

    assert "artifact_hash_mismatch" in serialized
    assert "D:\\private" not in serialized
    assert "MINIO_SECRET_KEY" not in serialized
    assert "do-not-leak" not in serialized
    assert "真实来源正文" not in serialized
    assert "eval/huiji_provenance/run/runtime.v1.json" in serialized


class _FakeQueryIterator:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows
        self._yielded = False
        self.closed = False

    def next(self):
        if self._yielded:
            return []
        self._yielded = True
        return self._rows

    def close(self):
        self.closed = True


class _ReadOnlyMilvusClient:
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        row_count: int | None = None,
        exists: bool = True,
    ):
        self.rows = rows
        self.row_count = len(rows) if row_count is None else row_count
        self.exists = exists
        self.output_fields: list[str] = []
        self.iterator: _FakeQueryIterator | None = None
        self.mutation_calls: list[str] = []

    def has_collection(self, collection_name: str):
        return self.exists

    def describe_collection(self, collection_name: str):
        fields = []
        for name in HUIJI_BUSINESS_FIELDS:
            fields.append(
                {
                    "name": name,
                    "type": 21 if name != "chunk_index" and name != "depth_level" else 5,
                    "is_primary": name == "id",
                    "auto_id": False,
                    "params": {"max_length": 256} if name != "chunk_index" else {},
                }
            )
        fields.append({"name": "embedding", "type": 101, "params": {"dim": 1024}})
        return {
            "collection_name": collection_name,
            "enable_dynamic_field": True,
            "fields": fields,
        }

    def query_iterator(self, **kwargs):
        self.output_fields = list(kwargs["output_fields"])
        self.iterator = _FakeQueryIterator(self.rows)
        return self.iterator

    def get_collection_stats(self, collection_name: str):
        return {"row_count": self.row_count}

    def insert(self, **kwargs):
        self.mutation_calls.append("insert")

    def delete(self, **kwargs):
        self.mutation_calls.append("delete")

    def upsert(self, **kwargs):
        self.mutation_calls.append("upsert")

    def create_collection(self, **kwargs):
        self.mutation_calls.append("create_collection")

    def drop_collection(self, **kwargs):
        self.mutation_calls.append("drop_collection")


def _business_rows() -> list[dict[str, object]]:
    return [
        huiji_child_to_business_row({"child_id": "c2", "parent_id": "p2", "text": "B"}),
        huiji_child_to_business_row({"child_id": "c1", "parent_id": "p1", "text": "A"}),
    ]


def test_milvus_fingerprint_reads_only_non_vector_business_fields():
    client = _ReadOnlyMilvusClient(_business_rows())

    fingerprint = capture_milvus_fingerprint(
        client,
        "active_v3",
        database="reverse1999_rag",
    )

    assert isinstance(fingerprint, MilvusFingerprint)
    assert fingerprint.collection == "active_v3"
    assert fingerprint.database == "reverse1999_rag"
    assert fingerprint.row_count == 2
    assert fingerprint.primary_id_count == 2
    assert "embedding" not in client.output_fields
    assert client.output_fields == list(HUIJI_BUSINESS_FIELDS)
    assert client.iterator is not None and client.iterator.closed is True
    assert client.mutation_calls == []
    assert len(fingerprint.schema_sha256) == 64
    assert len(fingerprint.primary_ids_sha256) == 64
    assert len(fingerprint.business_fields_sha256) == 64


def test_milvus_fingerprint_is_independent_of_query_row_order():
    first = capture_milvus_fingerprint(
        _ReadOnlyMilvusClient(_business_rows()),
        "active_v3",
        database="reverse1999_rag",
    )
    second = capture_milvus_fingerprint(
        _ReadOnlyMilvusClient(list(reversed(_business_rows()))),
        "active_v3",
        database="reverse1999_rag",
    )

    assert first.primary_ids_sha256 == second.primary_ids_sha256
    assert first.business_fields_sha256 == second.business_fields_sha256


@pytest.mark.parametrize(
    ("client", "code"),
    [
        (_ReadOnlyMilvusClient(_business_rows(), exists=False), "milvus_collection_missing"),
        (_ReadOnlyMilvusClient(_business_rows(), row_count=3), "milvus_row_count_mismatch"),
        (
            _ReadOnlyMilvusClient([_business_rows()[0], _business_rows()[0]]),
            "milvus_id_mismatch",
        ),
        (
            _ReadOnlyMilvusClient([{k: v for k, v in _business_rows()[0].items() if k != "text"}]),
            "milvus_content_mismatch",
        ),
    ],
)
def test_milvus_fingerprint_rejects_invalid_collection_state(client, code):
    with pytest.raises(ProvenanceValidationError) as error:
        capture_milvus_fingerprint(client, "active_v3", database="reverse1999_rag")

    assert error.value.code == code


def _audit_fixture(tmp_path: Path):
    raw_root = tmp_path / "data" / "huiji" / "res1999"
    build_root = tmp_path / "data" / "processed" / "huiji" / "dev"
    raw_root.mkdir(parents=True)
    (build_root / "indexes").mkdir(parents=True)
    content_sha = "a" * 64
    write_jsonl(
        raw_root / "data_pages.jsonl",
        [
            {
                "title": "Data:Char/1.json",
                "revid": 7,
                "content_sha256": content_sha,
                "content": {"name": "generic"},
            }
        ],
    )
    write_jsonl(
        raw_root / "resources_manifest.jsonl",
        [
            {
                "sha1": "b" * 40,
                "local_relpath": "assets/files/bb/voice.mp3",
                "url": "https://example.invalid/voice.mp3",
                "size": 10,
            }
        ],
    )
    source_ref = {
        "kind": "data_page",
        "title": "Data:Char/1.json",
        "revid": 7,
        "content_sha256": content_sha,
        "json_path": "$",
    }
    parent_rows = [
        {
            "parent_id": "char:1/profile",
            "entity_id": "char:1",
            "source_refs": [source_ref],
            "summary_text": "summary",
        }
    ]
    child_rows = [
        {
            "child_id": "char:1/profile:0000",
            "parent_id": "char:1/profile",
            "entity_id": "char:1",
            "text": "profile",
            "source_refs": [source_ref],
        }
    ]
    media_rows = [
        {
            "media_id": "media:sha1:" + "b" * 40,
            "child_id": "char:1/profile:0000",
            "parent_id": "char:1/profile",
            "entity_id": "char:1",
            "sha1": "b" * 40,
            "local_relpath": "assets/files/bb/voice.mp3",
            "source_url": "https://example.invalid/voice.mp3",
        }
    ]
    write_jsonl(build_root / "parent_blocks.jsonl", parent_rows)
    write_jsonl(build_root / "child_blocks.jsonl", child_rows)
    write_jsonl(build_root / "media_assets.jsonl", media_rows)
    (build_root / "indexes" / "child_text_bm25.json").write_text(
        json.dumps({"records": [{"id": row["child_id"], **row} for row in child_rows]}),
        encoding="utf-8",
    )
    (build_root / "indexes" / "media_asset_bm25.json").write_text(
        json.dumps({"records": [{"id": row["media_id"], **row} for row in media_rows]}),
        encoding="utf-8",
    )
    cfg = SimpleNamespace(
        paths=SimpleNamespace(project_root=tmp_path),
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=raw_root,
            processed_root=tmp_path / "data" / "processed" / "huiji",
            build_version="dev",
            text_collection_name="active_v3",
            provenance_baseline=tmp_path / "config" / "provenance" / "huiji-dev.v1.json",
        ),
        vectorstore=SimpleNamespace(
            db_name="reverse1999_rag",
            collection_name="active_v3",
        ),
    )
    client = _ReadOnlyMilvusClient([huiji_child_to_business_row(child_rows[0])])
    return cfg, client, raw_root, build_root


def _rewrite_bm25_for_artifact(build_root: Path, artifact: str, index: str, id_field: str):
    rows = [json.loads(line) for line in (build_root / artifact).read_text(encoding="utf-8").splitlines() if line]
    (build_root / "indexes" / index).write_text(
        json.dumps({"records": [{"id": row[id_field], **row} for row in rows]}),
        encoding="utf-8",
    )


def test_full_audit_passes_exact_huiji_reverse_references(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)

    result = audit_huiji_provenance(cfg, client)

    assert isinstance(result, AuditResult)
    assert result.status == "pass"
    assert result.issues == ()
    assert result.counters["source_ref_occurrences"] == 2
    assert result.counters["media_occurrences"] == 1
    assert result.milvus is not None
    assert result.milvus.business_fields_sha256


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("blank_refs", "source_ref_missing"),
        ("bad_kind", "source_kind_mismatch"),
        ("bad_revision", "source_revision_mismatch"),
        ("bad_hash", "source_hash_mismatch"),
        ("missing_title", "source_ref_missing"),
    ],
)
def test_full_audit_blocks_source_reference_problems(tmp_path: Path, mutation: str, expected_code: str):
    cfg, client, _, build_root = _audit_fixture(tmp_path)
    path = build_root / "parent_blocks.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    if mutation == "blank_refs":
        row["source_refs"] = []
    elif mutation == "bad_kind":
        row["source_refs"][0]["kind"] = "obsidian"
    elif mutation == "bad_revision":
        row["source_refs"][0]["revid"] = 8
    elif mutation == "bad_hash":
        row["source_refs"][0]["content_sha256"] = "c" * 64
    else:
        row["source_refs"][0]["title"] = "Data:Missing.json"
    write_jsonl(path, [row])

    result = audit_huiji_provenance(cfg, client)

    assert result.status == "blocked"
    assert expected_code in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("sha1", "c" * 40, "media_sha1_mismatch"),
        ("local_relpath", "assets/files/cc/other.mp3", "media_path_mismatch"),
        ("source_url", "https://example.invalid/other.mp3", "media_url_mismatch"),
    ],
)
def test_full_audit_blocks_media_manifest_problems(
    tmp_path: Path,
    field: str,
    value: str,
    expected_code: str,
):
    cfg, client, _, build_root = _audit_fixture(tmp_path)
    media_path = build_root / "media_assets.jsonl"
    row = json.loads(media_path.read_text(encoding="utf-8").splitlines()[0])
    row[field] = value
    write_jsonl(media_path, [row])
    _rewrite_bm25_for_artifact(
        build_root,
        "media_assets.jsonl",
        "media_asset_bm25.json",
        "media_id",
    )

    result = audit_huiji_provenance(cfg, client)

    assert result.status == "blocked"
    assert expected_code in {issue.code for issue in result.issues}


def test_full_audit_blocks_bm25_and_milvus_content_drift(tmp_path: Path):
    cfg, client, _, build_root = _audit_fixture(tmp_path)
    payload = json.loads((build_root / "indexes" / "child_text_bm25.json").read_text(encoding="utf-8"))
    payload["records"][0]["text"] = "changed"
    (build_root / "indexes" / "child_text_bm25.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    client.rows[0]["text"] = "changed"

    result = audit_huiji_provenance(cfg, client)

    assert result.status == "blocked"
    assert {issue.code for issue in result.issues} >= {
        "bm25_semantic_mismatch",
        "milvus_content_mismatch",
    }


def test_baseline_candidate_requires_passed_full_audit(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    blocked = replace(
        audit_huiji_provenance(cfg, client),
        status="blocked",
        issues=(VerificationIssue("source_hash_mismatch", "parent_blocks"),),
    )

    with pytest.raises(ProvenanceValidationError) as error:
        build_baseline_candidate(blocked)

    assert error.value.code == "audit_not_passed"


def test_baseline_candidate_and_install_are_hash_linked_and_create_new(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    result = audit_huiji_provenance(cfg, client)
    audit_path = tmp_path / "eval" / "run" / "audit.v1.json"
    audit_sha = write_hash_pinned_json(audit_path, result.to_evidence_dict())
    result = replace(
        result,
        audit_evidence_relpath="eval/run/audit.v1.json",
        audit_evidence_sha256=audit_sha,
    )
    candidate_path = tmp_path / "eval" / "run" / "baseline.candidate.v1.json"
    candidate = build_baseline_candidate(result)
    write_hash_pinned_json(candidate_path, candidate)
    installed = tmp_path / "config" / "provenance" / "huiji-dev.v1.json"

    digest = install_baseline_create_new(candidate_path, installed, project_root=tmp_path)

    assert digest == installed.with_name("huiji-dev.v1.json.sha256").read_text(encoding="ascii").split()[0]
    assert json.loads(installed.read_text(encoding="utf-8"))["source_mode"] == "huiji_crawler"
    with pytest.raises(FileExistsError):
        install_baseline_create_new(candidate_path, installed, project_root=tmp_path)


def test_baseline_install_rejects_changed_audit_evidence(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    result = audit_huiji_provenance(cfg, client)
    audit_path = tmp_path / "eval" / "run" / "audit.v1.json"
    audit_sha = write_hash_pinned_json(audit_path, result.to_evidence_dict())
    result = replace(
        result,
        audit_evidence_relpath="eval/run/audit.v1.json",
        audit_evidence_sha256=audit_sha,
    )
    candidate_path = tmp_path / "eval" / "run" / "baseline.candidate.v1.json"
    write_hash_pinned_json(candidate_path, build_baseline_candidate(result))
    audit_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ProvenanceValidationError) as error:
        install_baseline_create_new(
            candidate_path,
            tmp_path / "config" / "provenance" / "huiji-dev.v1.json",
            project_root=tmp_path,
        )

    assert error.value.code == "audit_evidence_mismatch"


def test_audit_cli_writes_unique_evidence_and_candidate(tmp_path: Path, capsys):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    run_dir = tmp_path / "eval" / "run"
    candidate = tmp_path / "eval" / "baseline.candidate.v1.json"

    exit_code = audit_cli_main(
        ["audit", "--run-dir", str(run_dir), "--candidate-baseline", str(candidate)],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
    )

    assert exit_code == 0
    assert (run_dir / "audit.v1.json").is_file()
    assert (run_dir / "audit.v1.json.sha256").is_file()
    assert candidate.is_file()
    assert candidate.with_name(candidate.name + ".sha256").is_file()
    assert "status=pass" in capsys.readouterr().out
    before = candidate.read_bytes()

    second_exit = audit_cli_main(
        ["audit", "--run-dir", str(run_dir), "--candidate-baseline", str(candidate)],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
    )

    assert second_exit == 3
    assert candidate.read_bytes() == before
    assert client.mutation_calls == []


def test_audit_cli_does_not_create_candidate_when_blocked(tmp_path: Path):
    cfg, client, _, build_root = _audit_fixture(tmp_path)
    write_jsonl(build_root / "parent_blocks.jsonl", [{"parent_id": "p", "source_refs": []}])
    candidate = tmp_path / "eval" / "baseline.candidate.v1.json"

    exit_code = audit_cli_main(
        [
            "audit",
            "--run-dir",
            str(tmp_path / "eval" / "blocked"),
            "--candidate-baseline",
            str(candidate),
        ],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
    )

    assert exit_code == 2
    assert not candidate.exists()


def test_install_baseline_cli_uses_configured_project_root(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    run_dir = tmp_path / "eval" / "run"
    candidate = tmp_path / "eval" / "baseline.candidate.v1.json"
    assert audit_cli_main(
        ["audit", "--run-dir", str(run_dir), "--candidate-baseline", str(candidate)],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
    ) == 0
    output = tmp_path / "config" / "provenance" / "huiji-dev.v1.json"

    exit_code = audit_cli_main(
        ["install-baseline", "--candidate", str(candidate), "--output", str(output)],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: pytest.fail("Milvus client initialized during install"),
    )

    assert exit_code == 0
    assert output.is_file()


def _install_fixture_baseline(tmp_path: Path, cfg, client) -> Path:
    result = audit_huiji_provenance(cfg, client)
    assert result.status == "pass"
    audit_path = tmp_path / "eval" / "baseline-source" / "audit.v1.json"
    audit_sha = write_hash_pinned_json(audit_path, result.to_evidence_dict())
    linked = replace(
        result,
        audit_evidence_relpath="eval/baseline-source/audit.v1.json",
        audit_evidence_sha256=audit_sha,
    )
    candidate = tmp_path / "eval" / "baseline-source" / "baseline.candidate.v1.json"
    write_hash_pinned_json(candidate, build_baseline_candidate(linked))
    output = cfg.huiji.provenance_baseline
    install_baseline_create_new(candidate, output, project_root=tmp_path)
    return output


def test_runtime_verifier_passes_without_reading_raw_crawler_files(tmp_path: Path):
    cfg, client, raw_root, _ = _audit_fixture(tmp_path)
    _install_fixture_baseline(tmp_path, cfg, client)
    (raw_root / "data_pages.jsonl").unlink()
    (raw_root / "resources_manifest.jsonl").unlink()

    result = verify_runtime(cfg, client_factory=lambda _cfg: client)

    assert result.status == "pass"
    assert result.allowed is True
    assert result.issues == ()
    assert client.mutation_calls == []


def test_runtime_verifier_blocks_artifact_and_config_drift(tmp_path: Path):
    cfg, client, _, build_root = _audit_fixture(tmp_path)
    _install_fixture_baseline(tmp_path, cfg, client)
    child_path = build_root / "child_blocks.jsonl"
    child_path.write_bytes(child_path.read_bytes() + b"\n")
    cfg.huiji.source_mode = "obsidian"

    result = verify_runtime(cfg, client_factory=lambda _cfg: client)

    assert result.status == "blocked"
    assert {issue.code for issue in result.issues} >= {
        "source_mode_mismatch",
        "artifact_hash_mismatch",
    }


def test_runtime_verifier_blocks_collection_and_milvus_content_drift(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    _install_fixture_baseline(tmp_path, cfg, client)
    cfg.huiji.text_collection_name = "other"
    client.rows[0]["text"] = "changed"

    result = verify_runtime(cfg, client_factory=lambda _cfg: client)

    assert result.status == "blocked"
    assert {issue.code for issue in result.issues} >= {
        "collection_config_mismatch",
        "milvus_content_mismatch",
    }


def test_runtime_verifier_fails_closed_on_internal_milvus_error(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    _install_fixture_baseline(tmp_path, cfg, client)

    def broken_client(_cfg):
        raise RuntimeError(r"D:\private\MINIO_SECRET_KEY=hidden")

    result = verify_runtime(cfg, client_factory=broken_client)

    assert result.status == "error"
    assert [issue.code for issue in result.issues] == ["verification_internal_error"]
    assert "private" not in json.dumps(result.to_public_dict())
    assert "milvus_schema_mismatch" not in {issue.code for issue in result.issues}


def test_runtime_verifier_blocks_missing_or_noncanonical_baseline(tmp_path: Path):
    cfg, client, _, _ = _audit_fixture(tmp_path)

    missing = verify_runtime(cfg, client_factory=lambda _cfg: client)
    assert missing.status == "blocked"
    assert [issue.code for issue in missing.issues] == ["baseline_missing"]

    cfg.huiji.provenance_baseline.parent.mkdir(parents=True)
    cfg.huiji.provenance_baseline.write_text("{}", encoding="utf-8")
    invalid = verify_runtime(cfg, client_factory=lambda _cfg: client)
    assert invalid.status == "blocked"
    assert [issue.code for issue in invalid.issues] == ["baseline_invalid"]


def test_runtime_cli_writes_hash_pinned_pass_and_blocked_evidence(tmp_path: Path):
    cfg, client, _, build_root = _audit_fixture(tmp_path)
    _install_fixture_baseline(tmp_path, cfg, client)
    pass_dir = tmp_path / "eval" / "runtime-pass"

    assert runtime_cli_main(
        ["--run-dir", str(pass_dir)],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
    ) == 0
    assert (pass_dir / "runtime.v1.json").is_file()
    assert (pass_dir / "runtime.v1.json.sha256").is_file()

    (build_root / "parent_blocks.jsonl").write_bytes(
        (build_root / "parent_blocks.jsonl").read_bytes() + b"\n"
    )
    blocked_dir = tmp_path / "eval" / "runtime-blocked"
    assert runtime_cli_main(
        ["--run-dir", str(blocked_dir)],
        cfg_loader=lambda: cfg,
        client_factory=lambda _cfg: client,
    ) == 2
    payload = json.loads((blocked_dir / "runtime.v1.json").read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert "artifact_hash_mismatch" in {issue["code"] for issue in payload["issues"]}


def test_runtime_cli_uses_a_bounded_milvus_connection_timeout(monkeypatch):
    captured: dict[str, object] = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("pymilvus.MilvusClient", fake_client)
    cfg = SimpleNamespace(
        vectorstore=SimpleNamespace(
            uri="http://127.0.0.1:19600",
            db_name="reverse1999_rag",
        )
    )

    runtime_cli._default_client(cfg)

    assert captured["timeout"] == runtime_cli.MILVUS_CONNECT_TIMEOUT_SECONDS
    assert 0 < captured["timeout"] <= 10


def test_runtime_cli_handles_keyboard_interrupt_without_traceback(tmp_path: Path, capsys):
    cfg, client, _, _ = _audit_fixture(tmp_path)
    _install_fixture_baseline(tmp_path, cfg, client)

    def interrupted_client(_cfg):
        raise KeyboardInterrupt

    result = runtime_cli_main(
        ["--run-dir", str(tmp_path / "eval" / "runtime-cancelled")],
        cfg_loader=lambda: cfg,
        client_factory=interrupted_client,
    )

    output = capsys.readouterr()
    assert result == 130
    assert "status=cancelled" in output.err
    assert "Traceback" not in output.err
