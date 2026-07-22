from __future__ import annotations

import copy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.huiji_rag.activation as activation_module
from src.huiji_rag.activation import (
    ACTIVATION_ID,
    ACTIVATION_JOURNAL_SCHEMA,
    ActivationConflict,
    PREVIOUS_POINTER_SHA256,
    PREVIOUS_SETTINGS_SHA256,
    _candidate_settings,
    _conditional_replace,
    _p0_matrix,
    append_journal,
    compare_activation_protected,
    read_journal,
    recover_activation,
)
from src.huiji_rag.backend_process import BackendProcessIdentity


def test_candidate_settings_change_only_approved_scalars() -> None:
    before = b"""vectorstore:\n  collection_name: old\nhuiji:\n  build_version: dev\n  text_collection_name: old\nother:\n  value: keep\n"""
    after = _candidate_settings(before).decode("utf-8")
    assert "text_child_bge_m3_shadow_crawler_v3_20260721t051246z" in after
    assert "crawler-v3-20260721t051246z" in after
    assert "value: keep" in after


def test_activation_journal_is_hash_chained_and_strict(tmp_path: Path) -> None:
    path = tmp_path / "activation_journal.v1.jsonl"
    append_journal(
        path,
        state="prepared",
        intent_sha256="a" * 64,
        pointer_sha256="b" * 64,
    )
    append_journal(
        path,
        state="backend_stopped",
        intent_sha256="a" * 64,
        pointer_sha256="b" * 64,
    )
    events = read_journal(path)
    assert [event["state"] for event in events] == ["prepared", "backend_stopped"]
    assert all(event["schema_version"] == ACTIVATION_JOURNAL_SCHEMA for event in events)
    with pytest.raises(ValueError, match="transition"):
        append_journal(
            path,
            state="committed",
            intent_sha256="a" * 64,
            pointer_sha256="b" * 64,
        )


def test_activation_protected_compare_allows_only_operation_evidence() -> None:
    before = {
        "milvus": {"collection": "old"},
        "minio_inventories": {"scope": {"objects": []}},
        "mysql_tables": {"wiki_pages": {"row_count": 1, "sha256": "a"}},
        "artifacts": {
            "data/processed/huiji/active_build.v1.json": {"sha256": "old", "size": 1},
            "data/processed/huiji/dev/build_manifest.json": {"sha256": "same", "size": 1},
        },
    }
    after = copy.deepcopy(before)
    after["milvus"] = {"collection": "candidate"}
    after["artifacts"]["data/processed/huiji/active_build.v1.json"] = {"sha256": "new", "size": 1}
    after["artifacts"]["data/processed/huiji/activation/transactions/op/evidence.json"] = {"sha256": "x", "size": 2}
    assert compare_activation_protected(
        before,
        after,
        transaction_prefix="data/processed/huiji/activation/transactions/op",
    ) == []
    after["mysql_tables"]["wiki_pages"]["row_count"] = 2
    assert compare_activation_protected(
        before,
        after,
        transaction_prefix="data/processed/huiji/activation/transactions/op",
    ) == ["mysql_tables changed"]


def test_activation_protected_compare_allows_only_exact_pinned_artifact_changes() -> None:
    before = {
        "minio_inventories": {},
        "mysql_tables": {},
        "artifacts": {
            "authority/journal.jsonl": {"sha256": "old", "size": 1},
            "stable.json": {"sha256": "stable", "size": 2},
        },
    }
    after = copy.deepcopy(before)
    after["artifacts"]["authority/journal.jsonl"] = {"sha256": "sealed", "size": 3}
    after["artifacts"]["authority/receipt.json"] = {"sha256": "receipt", "size": 4}
    allowed = {
        "authority/journal.jsonl": {"sha256": "sealed", "size": 3},
        "authority/receipt.json": {"sha256": "receipt", "size": 4},
    }
    assert compare_activation_protected(
        before, after, allowed_artifact_changes=allowed
    ) == []

    after["artifacts"]["authority/receipt.json"]["size"] = 5
    with pytest.raises(ValueError, match="does not match"):
        compare_activation_protected(
            before, after, allowed_artifact_changes=allowed
        )


def test_activation_protected_compare_rejects_extra_file_beside_allowed_evidence() -> None:
    before = {"minio_inventories": {}, "mysql_tables": {}, "artifacts": {}}
    after = copy.deepcopy(before)
    after["artifacts"]["authority/receipt.json"] = {"sha256": "receipt", "size": 4}
    after["artifacts"]["authority/unapproved.json"] = {"sha256": "extra", "size": 5}
    assert compare_activation_protected(
        before,
        after,
        allowed_artifact_changes={
            "authority/receipt.json": {"sha256": "receipt", "size": 4}
        },
    ) == ["artifacts changed"]


def test_activation_p0_matrix_is_exact_48() -> None:
    matrix = _p0_matrix()
    ids = [entry["id"] for entry in matrix["entries"]]
    assert matrix["expected_count"] == 48
    assert matrix["passed_count"] == 48
    assert len(ids) == len(set(ids)) == 48


def test_conditional_replace_never_overwrites_unknown_bytes(tmp_path: Path) -> None:
    target = tmp_path / "settings.yaml"
    target.write_bytes(b"before\n")
    expected = __import__("hashlib").sha256(b"before\n").hexdigest()
    digest = _conditional_replace(target, b"candidate\n", expected, "operation-a")
    assert target.read_bytes() == b"candidate\n"
    assert digest == __import__("hashlib").sha256(b"candidate\n").hexdigest()
    with pytest.raises(ActivationConflict, match="SHA conflict"):
        _conditional_replace(target, b"overwrite\n", expected, "operation-b")
    assert target.read_bytes() == b"candidate\n"


def test_failure_journal_reaches_only_rolled_back_terminal(tmp_path: Path) -> None:
    path = tmp_path / "activation_journal.v1.jsonl"
    identity = {"intent_sha256": "a" * 64, "pointer_sha256": "b" * 64}
    for state in (
        "prepared",
        "backend_stopped",
        "settings_written",
        "verification_failed",
        "compensating",
        "rolled_back",
    ):
        append_journal(path, state=state, **identity)
    assert read_journal(path)[-1]["state"] == "rolled_back"
    with pytest.raises(ValueError, match="transition"):
        append_journal(path, state="committed", **identity)


def _recovery_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path.resolve()
    transaction = root / "data/processed/huiji/activation/transactions" / ACTIVATION_ID
    transaction.mkdir(parents=True)
    pointer_candidate_sha = "c" * 64
    process = BackendProcessIdentity(
        pid=123,
        create_time=1.0,
        executable="python.exe",
        cwd=str(root),
        argv=("python.exe", "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"),
    )
    intent = {
        "pointer_candidate": {"sha256": pointer_candidate_sha},
        "settings_candidate": {"sha256": "d" * 64},
        "backend_process": process.to_json(),
    }
    monkeypatch.setattr(
        activation_module,
        "_load_intent",
        lambda cfg, path, expected: (intent, transaction),
    )
    monkeypatch.setattr(
        activation_module,
        "activation_lock",
        lambda root, operation_id: nullcontext(),
    )
    cfg = SimpleNamespace(paths=SimpleNamespace(project_root=root))
    journal = transaction / "activation_journal.v1.jsonl"
    append_journal(
        journal,
        state="prepared",
        intent_sha256="a" * 64,
        pointer_sha256=pointer_candidate_sha,
    )
    return cfg, transaction, journal, process


def test_recover_nonterminal_state_compensates_to_rolled_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg, transaction, journal, process = _recovery_fixture(tmp_path, monkeypatch)
    canonical = {
        "active_build.v1.json": PREVIOUS_POINTER_SHA256,
        "settings.yaml": PREVIOUS_SETTINGS_SHA256,
    }
    def fake_sha256(path: Path) -> str:
        target = Path(path)
        if target.name in canonical:
            return canonical[target.name]
        return __import__("hashlib").sha256(target.read_bytes()).hexdigest()

    monkeypatch.setattr(
        activation_module,
        "sha256_file",
        fake_sha256,
    )
    monkeypatch.setattr(activation_module, "inspect_backend_optional", lambda root: process)
    compensated: list[bool] = []
    monkeypatch.setattr(
        activation_module,
        "_compensate",
        lambda *args, **kwargs: compensated.append(True),
    )

    result = recover_activation(
        cfg,
        activation_id=ACTIVATION_ID,
        expected_intent_sha256="a" * 64,
    )

    assert result == {"status": "rolled_back"}
    assert compensated == [True]
    assert [event["state"] for event in read_journal(journal)] == [
        "prepared",
        "verification_failed",
        "compensating",
        "rolled_back",
    ]
    assert (transaction / "activation_failure.v1.json").is_file()


def test_recover_unknown_canonical_sha_seals_conflict_without_compensation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg, transaction, journal, _process = _recovery_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(activation_module, "sha256_file", lambda path: "f" * 64)
    compensated: list[bool] = []
    monkeypatch.setattr(
        activation_module,
        "_compensate",
        lambda *args, **kwargs: compensated.append(True),
    )

    with pytest.raises(ActivationConflict, match="unknown canonical SHA"):
        recover_activation(
            cfg,
            activation_id=ACTIVATION_ID,
            expected_intent_sha256="a" * 64,
        )

    assert compensated == []
    assert read_journal(journal)[-1]["state"] == "conflict"
    assert (transaction / "activation_failure.v1.json").is_file()
