from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.huiji_rag.closure import (
    CLOSURE_SCHEMA,
    ClosureConflict,
    ClosureInspection,
    EXPECTED_P0_IDS,
    _validate_database_state,
    _validate_health,
    _validate_receipt_shape,
    _write_receipt_and_sidecar_create_new,
    build_closure_receipt,
    canonical_json_bytes,
    close_candidate,
    resolve_project_path,
    validate_hash_sidecar,
    validate_pinned_json,
)
import src.huiji_rag.closure as closure_module
from scripts import close_huiji_candidate as closure_cli


def _write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(payload)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_closure_contract_has_exactly_23_unique_p0_ids():
    assert CLOSURE_SCHEMA == "huiji.candidate-f-cross-system-closure/v1"
    assert len(EXPECTED_P0_IDS) == 23
    assert len(set(EXPECTED_P0_IDS)) == 23


def test_resolve_project_path_rejects_escape(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(ValueError, match="escapes project root"):
        resolve_project_path(root, tmp_path / "outside.json")


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_validate_hash_sidecar_accepts_lf_and_crlf(tmp_path: Path, newline: bytes):
    target = tmp_path / "receipt.json"
    target.write_bytes(b"{}\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    sidecar = target.with_name(f"{target.name}.sha256")
    sidecar.write_bytes(f"{digest}  {target.name}".encode("ascii") + newline)

    assert validate_hash_sidecar(target) == digest


def test_validate_hash_sidecar_rejects_wrong_digest(tmp_path: Path):
    target = tmp_path / "receipt.json"
    target.write_bytes(b"{}\n")
    sidecar = target.with_name(f"{target.name}.sha256")
    sidecar.write_text(f"{'0' * 64}  {target.name}\n", encoding="ascii", newline="")

    with pytest.raises(ValueError, match="sidecar mismatch"):
        validate_hash_sidecar(target)


def test_validate_pinned_json_checks_canonical_bytes_and_schema(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    target = root / "evidence.json"
    digest = _write_json(target, {"schema_version": "example/v1", "status": "pass"})

    payload = validate_pinned_json(
        root,
        target,
        expected_sha256=digest,
        expected_schema="example/v1",
    )

    assert payload["status"] == "pass"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical JSON"):
        validate_pinned_json(
            root,
            target,
            expected_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            expected_schema="example/v1",
        )


def test_validate_pinned_json_can_accept_windows_canonical_newline(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    target = root / "evidence.json"
    payload = {"schema_version": "example/v1", "status": "pass"}
    target.write_bytes(canonical_json_bytes(payload).replace(b"\n", b"\r\n"))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()

    loaded = validate_pinned_json(
        root,
        target,
        expected_sha256=digest,
        expected_schema="example/v1",
        allow_crlf=True,
    )

    assert loaded == payload


def _rag_health() -> dict:
    return {
        "status": "ok",
        "vectorstore_loaded": True,
        "provenance_status": "pass",
        "doc_count": 14630,
    }


def _wiki_health() -> dict:
    return {
        "ready": True,
        "pageCount": 7456,
        "categoryCount": 4,
        "mediaLinkCount": 17527,
        "mediaResourceCount": 19132,
        "mediaBindingCount": 19400,
        "sourceMode": "active",
        "buildVersion": "crawler-v3-20260721t051246z",
        "artifactSchemaVersion": "evb.media-asset/v3",
        "activationEpoch": 1,
        "stale": False,
    }


def _database_state() -> dict:
    return {
        "counts": {
            "wiki_pages": 7456,
            "wiki_categories": 4,
            "wiki_media_links": 17527,
            "wiki_media_resources": 19132,
            "wiki_media_bindings": 19400,
        },
        "snapshot": {
            "id": 1,
            "source_mode": "active",
            "build_version": "crawler-v3-20260721t051246z",
            "artifact_schema_version": "evb.media-asset/v3",
            "activation_epoch": 1,
            "manifest_sha256": "293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f",
            "snapshot_sha256": "7529288166e2304d2e31cad7777a5fb8173e830ece13d340fae0650d08f019a1",
            "imported_at_utc": "2026-07-22T10:11:27Z",
        },
    }


def _formal_receipt(database: dict | None = None) -> dict:
    return {
        "database": database or _database_state(),
        "completed_at_utc": "2026-07-22T11:59:49Z",
        "evidence": {
            "protected_compare": {
                "path": "eval/protected.json",
                "sha256": "1" * 64,
            }
        },
    }


def _inspection(root: Path, formal_path: Path) -> ClosureInspection:
    return ClosureInspection(
        activation_receipt={},
        handoff={"wiki_import_status": "not_started"},
        formal_receipt=_formal_receipt(),
        formal_evidence={},
        active_pointer={},
        runtime_identity={
            "source_mode": "active_pointer",
            "generation": 1,
            "build_version": "crawler-v3-20260721t051246z",
            "collection": "text_child_bge_m3_shadow_crawler_v3_20260721t051246z",
            "artifact_schema_version": "evb.media-asset/v3",
            "manifest_sha256": "2" * 64,
            "tuple_sha256": "3" * 64,
            "artifact_sha256": {},
        },
        rag_health=_rag_health(),
        wiki_health=_wiki_health(),
        database_state=_database_state(),
        rollback={
            "rag_generation_zero": {"status": "traceable_not_executed"},
            "wiki_pre_import": {"status": "traceable_not_executed"},
        },
    )


def _receipt_files(root: Path) -> tuple[Path, Path, Path, Path]:
    activation = root / closure_module.ACTIVATION_RECEIPT_RELATIVE
    handoff = root / closure_module.WIKI_HANDOFF_RELATIVE
    pointer = root / closure_module.ACTIVE_POINTER_RELATIVE
    formal = root / closure_module.DEFAULT_FORMAL_RECEIPT_RELATIVE
    for path in (activation, handoff, pointer, formal):
        _write_json(path, {"schema_version": "fixture/v1"})
    return activation, handoff, pointer, formal


def test_validate_health_rejects_stale_wiki():
    wiki = _wiki_health()
    wiki["stale"] = True

    with pytest.raises(ValueError, match="Wiki health"):
        _validate_health(_rag_health(), wiki)


def test_validate_health_rejects_wrong_rag_doc_count():
    rag = _rag_health()
    rag["doc_count"] = 16010

    with pytest.raises(ValueError, match="RAG health"):
        _validate_health(rag, _wiki_health())


def test_validate_database_state_rejects_second_import_timestamp():
    current = _database_state()
    current["snapshot"] = dict(current["snapshot"])
    current["snapshot"]["imported_at_utc"] = "2026-07-22T12:30:00Z"

    with pytest.raises(ValueError, match="snapshot differs"):
        _validate_database_state(_formal_receipt(), current)


def test_build_receipt_records_single_completed_transition(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    activation, handoff, pointer, formal = _receipt_files(root)
    payload = build_closure_receipt(
        _inspection(root, formal),
        project_root=root,
        formal_receipt_path=formal,
        closed_at_utc="2026-07-22T12:00:00Z",
    )

    assert payload["wiki_import"]["status_transition"] == {
        "from": "not_started",
        "to": "completed",
    }
    assert payload["mutation_assertions"]["milvus_writes"] is False
    assert payload["requirement_matrix"]["passed_count"] == 23
    assert payload["activation"]["wiki_handoff"]["path"].endswith("wiki_import_handoff.v1.json")
    assert activation.exists() and handoff.exists() and pointer.exists()


def test_validate_receipt_shape_rejects_missing_p0_entry(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    _, _, _, formal = _receipt_files(root)
    payload = build_closure_receipt(
        _inspection(root, formal),
        project_root=root,
        formal_receipt_path=formal,
        closed_at_utc="2026-07-22T12:00:00Z",
    )
    payload["requirement_matrix"]["entries"].pop()

    with pytest.raises(ValueError, match="P0 matrix"):
        _validate_receipt_shape(payload)


def test_write_receipt_is_canonical_and_sidecar_is_exact_lf(tmp_path: Path):
    target = tmp_path / "closure.json"
    payload = {"schema_version": CLOSURE_SCHEMA, "status": "closed"}

    digest = _write_receipt_and_sidecar_create_new(target, payload)

    assert target.read_bytes() == canonical_json_bytes(payload)
    assert target.with_name(f"{target.name}.sha256").read_bytes() == (
        f"{digest}  {target.name}\n".encode("ascii")
    )
    assert validate_hash_sidecar(target, require_lf=True) == digest


@pytest.mark.parametrize("existing", ["receipt", "sidecar"])
def test_close_rejects_partial_preexisting_output(
    tmp_path: Path,
    existing: str,
):
    root = tmp_path / "project"
    root.mkdir()
    output = root / "eval/closure.json"
    output.parent.mkdir(parents=True)
    if existing == "receipt":
        output.write_text("{}\n", encoding="utf-8")
    else:
        output.with_name(f"{output.name}.sha256").write_text("x", encoding="ascii")

    with pytest.raises(ClosureConflict, match="partial"):
        close_candidate(
            SimpleNamespace(),
            project_root=root,
            formal_receipt_path=root / "formal.json",
            expected_formal_receipt_sha256="0" * 64,
            output_path=output,
        )


def test_close_existing_pair_validates_and_returns_already_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "project"
    root.mkdir()
    output = root / "eval/closure.json"
    digest = _write_receipt_and_sidecar_create_new(output, {"schema_version": CLOSURE_SCHEMA})
    calls: list[str] = []
    monkeypatch.setattr(
        closure_module,
        "validate_closure_receipt",
        lambda *args, **kwargs: calls.append(kwargs["expected_receipt_sha256"]) or {},
    )

    result = close_candidate(
        SimpleNamespace(),
        project_root=root,
        formal_receipt_path=root / "formal.json",
        expected_formal_receipt_sha256="0" * 64,
        output_path=output,
    )

    assert result["status"] == "already_closed"
    assert calls == [digest]


def test_closure_module_does_not_import_write_or_embedding_modules():
    source = inspect.getsource(closure_module)
    forbidden = (
        "import_payload_to_mysql",
        "build_wiki_import_payload",
        "src.huiji_rag.builder",
        "src.rag.vectorstore",
        "minio_store",
        "restore_wiki_mysql_from_receipt",
    )

    assert all(name not in source for name in forbidden)


def test_database_reader_uses_read_only_transaction_without_dml():
    source = inspect.getsource(closure_module._query_database_state).upper()

    assert "START TRANSACTION READ ONLY" in source
    assert all(
        statement not in source
        for statement in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP ", "ALTER ")
    )


def test_cli_inspect_prints_only_safe_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    root = tmp_path / "project"
    root.mkdir()
    _, _, _, formal = _receipt_files(root)
    monkeypatch.setattr(closure_cli, "get_config", lambda: SimpleNamespace())
    monkeypatch.setattr(
        closure_cli,
        "inspect_candidate_closure",
        lambda *args, **kwargs: _inspection(root, formal),
    )

    exit_code = closure_cli.main(
        [
            "inspect",
            "--formal-import-receipt",
            str(formal),
            "--expected-formal-import-receipt-sha256",
            "0" * 64,
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert json.loads(output)["status"] == "ready_to_close"
    assert "password" not in output.lower()
    assert "api_key" not in output.lower()


def test_cli_conflict_has_stable_exit_without_error_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(closure_cli, "get_config", lambda: SimpleNamespace())

    def fail(*args, **kwargs):
        raise ClosureConflict("private-path-must-not-appear")

    monkeypatch.setattr(closure_cli, "close_candidate", fail)

    exit_code = closure_cli.main(
        [
            "close",
            "--formal-import-receipt",
            "formal.json",
            "--expected-formal-import-receipt-sha256",
            "0" * 64,
        ]
    )

    error = capsys.readouterr().err
    assert exit_code == 3
    assert json.loads(error)["status"] == "conflict"
    assert "private-path-must-not-appear" not in error


def test_cli_validate_reports_matrix_without_rewriting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(closure_cli, "get_config", lambda: SimpleNamespace())
    monkeypatch.setattr(
        closure_cli,
        "validate_closure_receipt",
        lambda *args, **kwargs: {
            "activation_id": closure_module.ACTIVATION_ID,
            "requirement_matrix": {"passed_count": 23, "expected_count": 23},
        },
    )

    exit_code = closure_cli.main(
        [
            "validate",
            "--receipt",
            "closure.json",
            "--expected-receipt-sha256",
            "a" * 64,
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "valid"
    assert output["p0_passed"] == output["p0_total"] == 23
