from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from src.codex_supervisor.task_receipts import (
    compute_allowed_tree_identity,
    verify_red_acceptance,
    verify_task_receipt,
)


def _git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Supervisor Tests"],
        cwd=repo,
        check=True,
    )
    (repo / "tracked.txt").write_bytes(b"base\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    return repo, base


def test_allowed_tree_identity_includes_tracked_untracked_and_absent(
    tmp_path: Path,
) -> None:
    repo, base = _git_repo(tmp_path)
    (repo / "tracked.txt").write_bytes(b"changed\n")
    (repo / "new.py").write_bytes(b"print('red')\n")
    first = compute_allowed_tree_identity(
        repository_root=repo,
        base_commit=base,
        allowed_relative_paths=("new.py", "missing.py", "tracked.txt"),
    )
    second = compute_allowed_tree_identity(
        repository_root=repo,
        base_commit=base,
        allowed_relative_paths=("tracked.txt", "missing.py", "new.py"),
    )
    assert first == second
    assert first.identity_sha256 == hashlib.sha256(
        first.canonical_bytes
    ).hexdigest()
    entries = {entry.path: entry for entry in first.entries}
    assert entries["new.py"].state == "file"
    assert entries["new.py"].sha256 == hashlib.sha256(
        b"print('red')\n"
    ).hexdigest()
    assert entries["missing.py"].state == "absent"
    assert entries["tracked.txt"].size_bytes == len(b"changed\n")


def test_allowed_tree_identity_rejects_outside_allowlist_change(
    tmp_path: Path,
) -> None:
    repo, base = _git_repo(tmp_path)
    (repo / "outside.txt").write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="outside allowlist"):
        compute_allowed_tree_identity(
            repository_root=repo,
            base_commit=base,
            allowed_relative_paths=("tracked.txt",),
        )


@pytest.mark.parametrize("path", ("../escape", ".", "a/../b", "tracked.txt"))
def test_allowed_tree_identity_rejects_unsafe_or_duplicate_paths(
    tmp_path: Path, path: str,
) -> None:
    repo, base = _git_repo(tmp_path)
    paths = (path, path) if path == "tracked.txt" else (path,)
    with pytest.raises(ValueError):
        compute_allowed_tree_identity(
            repository_root=repo,
            base_commit=base,
            allowed_relative_paths=paths,
        )


def test_verify_task_receipt_closes_red_green_and_scope() -> None:
    sha = "a" * 64
    receipt = {
        "schema_version": "rag.story-segment-task-receipt/v1",
        "task_id": "E0.1",
        "base_commit": "b" * 40,
        "red_tree_identity": {
            "manifest_path": "red.json",
            "manifest_sha256": sha,
            "identity_sha256": "c" * 64,
        },
        "red_log_sha256": "d" * 64,
        "d_red_acceptance": {"path": "accept.json", "sha256": "e" * 64},
        "red": {
            "argv": ["python", "-m", "pytest"],
            "expected_failure": "missing contract",
            "observed_failure": "ImportError: missing contract",
            "passed_gate": True,
        },
        "green_tree_identity": {
            "manifest_path": "green.json",
            "manifest_sha256": "f" * 64,
            "identity_sha256": "1" * 64,
        },
        "green_log_sha256": "2" * 64,
        "green": {
            "argv": ["python", "-m", "pytest"],
            "exit_code": 0,
            "passed": 3,
            "failed": 0,
            "skipped": 0,
        },
        "real_evidence": {
            "status": "not_applicable",
            "reason": "E0.1 table: not_applicable",
            "input_identity": {},
            "output_sha256": "",
        },
        "protected_drift_count": 0,
        "forbidden_operation_counts": {"embedding": 0, "milvus": 0},
        "allowed_files": ["src/a.py", "tests/test_a.py"],
        "observed_changed_files": ["src/a.py", "tests/test_a.py"],
    }
    verify_task_receipt(receipt)
    drifted = json.loads(json.dumps(receipt))
    drifted["observed_changed_files"].append("zzz/outside.py")
    with pytest.raises(ValueError, match="outside allowed_files"):
        verify_task_receipt(drifted)
    receipt["forbidden_operation_counts"]["milvus"] = 1
    with pytest.raises(ValueError, match="forbidden operation"):
        verify_task_receipt(receipt)


def test_verify_red_acceptance_requires_two_real_business_failures() -> None:
    acceptance = {
        "schema_version": "rag.story-segment-red-acceptance/v1",
        "task_id": "E0.1",
        "base_commit": "b" * 40,
        "allowed_tree_identity_sha256": "a" * 64,
        "allowed_tree_manifest_sha256": "c" * 64,
        "expected_business_failure": "missing story structure contract",
        "e_red": {
            "argv": ["python", "-m", "pytest"],
            "exit_code": 1,
            "log_sha256": "d" * 64,
            "observed_failure": "ImportError: story structure",
        },
        "d_red": {
            "argv": ["python", "-m", "pytest"],
            "exit_code": 1,
            "log_sha256": "e" * 64,
            "observed_failure": "ImportError: story structure",
        },
        "observed_changed_files": ["tests/test_story_structure.py"],
        "outside_allowlist_change_count": 0,
        "accepted_at_utc": "2026-08-02T12:00:00Z",
        "d_supervision_commit": "f" * 40,
    }
    verify_red_acceptance(acceptance)
    acceptance["d_red"]["exit_code"] = 0
    with pytest.raises(ValueError, match="must fail"):
        verify_red_acceptance(acceptance)
