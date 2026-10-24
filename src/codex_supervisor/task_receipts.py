from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping, Sequence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_TASK_ID_RE = re.compile(r"^E[0-5]\.[1-9][0-9]*$")


@dataclass(frozen=True)
class AllowedTreeEntry:
    path: str
    state: Literal["absent", "file"]
    size_bytes: int | None = None
    sha256: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": self.path,
            "state": self.state,
        }
        if self.state == "file":
            payload["size_bytes"] = self.size_bytes
            payload["sha256"] = self.sha256
        return payload


@dataclass(frozen=True)
class AllowedTreeIdentity:
    base_commit: str
    entries: tuple[AllowedTreeEntry, ...]

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json())

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "codex.allowed-tree-identity/v1",
            "base_commit": self.base_commit,
            "entries": [entry.to_json() for entry in self.entries],
        }


def compute_allowed_tree_identity(
    *,
    repository_root: Path,
    base_commit: str,
    allowed_relative_paths: Sequence[str],
) -> AllowedTreeIdentity:
    root = repository_root.resolve()
    if not (root / ".git").exists():
        raise ValueError("repository_root is not a Git worktree")
    if not _COMMIT_RE.fullmatch(base_commit):
        raise ValueError("base_commit must be a lowercase 40-hex commit")
    observed_head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if observed_head != base_commit:
        raise ValueError("worktree HEAD does not equal base_commit")
    _git(root, "rev-parse", "--verify", f"{base_commit}^{{commit}}")

    normalized = tuple(_normalize_relative_path(item) for item in allowed_relative_paths)
    if not normalized:
        raise ValueError("allowed_relative_paths must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("allowed_relative_paths contains duplicates")
    allowed = frozenset(normalized)
    changed = _changed_paths(root, base_commit)
    outside = sorted(changed - allowed)
    if outside:
        raise ValueError(
            "worktree contains changes outside allowlist: "
            + ", ".join(outside)
        )

    entries: list[AllowedTreeEntry] = []
    for relative in sorted(allowed):
        path = root.joinpath(*PurePosixPath(relative).parts)
        _reject_symlink_chain(root, path)
        if not path.exists():
            entries.append(AllowedTreeEntry(relative, "absent"))
            continue
        if not path.is_file():
            raise ValueError(f"allowlisted path is not a regular file: {relative}")
        raw = path.read_bytes()
        entries.append(
            AllowedTreeEntry(
                path=relative,
                state="file",
                size_bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return AllowedTreeIdentity(base_commit=base_commit, entries=tuple(entries))


def verify_task_receipt(receipt: Mapping[str, object]) -> None:
    required = {
        "schema_version",
        "task_id",
        "base_commit",
        "red_tree_identity",
        "red_log_sha256",
        "d_red_acceptance",
        "red",
        "green_tree_identity",
        "green_log_sha256",
        "green",
        "real_evidence",
        "protected_drift_count",
        "forbidden_operation_counts",
        "allowed_files",
        "observed_changed_files",
    }
    if set(receipt) != required:
        raise ValueError("task receipt field set is not exact")
    if receipt["schema_version"] != "rag.story-segment-task-receipt/v1":
        raise ValueError("unsupported task receipt schema")
    if not _TASK_ID_RE.fullmatch(str(receipt["task_id"])):
        raise ValueError("invalid story segment task_id")
    _require_commit(receipt["base_commit"], "base_commit")
    _verify_tree_reference(receipt["red_tree_identity"], "red_tree_identity")
    _verify_tree_reference(receipt["green_tree_identity"], "green_tree_identity")
    _require_sha(receipt["red_log_sha256"], "red_log_sha256")
    _require_sha(receipt["green_log_sha256"], "green_log_sha256")

    acceptance = _mapping(receipt["d_red_acceptance"], "d_red_acceptance")
    if set(acceptance) != {"path", "sha256"} or not str(acceptance["path"]):
        raise ValueError("invalid d_red_acceptance")
    _require_sha(acceptance["sha256"], "d_red_acceptance.sha256")

    red = _mapping(receipt["red"], "red")
    if set(red) != {"argv", "expected_failure", "observed_failure", "passed_gate"}:
        raise ValueError("red field set is not exact")
    _require_argv(red["argv"], "red.argv")
    if not str(red["expected_failure"]) or not str(red["observed_failure"]):
        raise ValueError("RED evidence must name expected and observed failure")
    if red["passed_gate"] is not True:
        raise ValueError("RED gate was not passed")

    green = _mapping(receipt["green"], "green")
    if set(green) != {"argv", "exit_code", "passed", "failed", "skipped"}:
        raise ValueError("green field set is not exact")
    _require_argv(green["argv"], "green.argv")
    if int(green["exit_code"]) != 0 or int(green["failed"]) != 0:
        raise ValueError("GREEN gate did not pass")
    if any(int(green[key]) < 0 for key in ("passed", "failed", "skipped")):
        raise ValueError("GREEN counts must be non-negative")

    evidence = _mapping(receipt["real_evidence"], "real_evidence")
    if set(evidence) != {"status", "reason", "input_identity", "output_sha256"}:
        raise ValueError("real_evidence field set is not exact")
    status = str(evidence["status"])
    if status not in {"required", "not_applicable"}:
        raise ValueError("real_evidence status is invalid")
    if not isinstance(evidence["input_identity"], Mapping):
        raise ValueError("real_evidence input_identity must be an object")
    if status == "required":
        _require_sha(evidence["output_sha256"], "real_evidence.output_sha256")
    elif not str(evidence["reason"]):
        raise ValueError("not_applicable real evidence requires an exact reason")

    if int(receipt["protected_drift_count"]) != 0:
        raise ValueError("protected state drift is nonzero")
    operations = _mapping(
        receipt["forbidden_operation_counts"], "forbidden_operation_counts"
    )
    if not operations or any(int(value) != 0 for value in operations.values()):
        raise ValueError("forbidden operation count is nonzero or absent")

    allowed = _normalized_path_list(receipt["allowed_files"], "allowed_files")
    observed = _normalized_path_list(
        receipt["observed_changed_files"], "observed_changed_files"
    )
    outside = sorted(set(observed) - set(allowed))
    if outside:
        raise ValueError(
            "observed_changed_files contains paths outside allowed_files: "
            + ", ".join(outside)
        )


def verify_red_acceptance(acceptance: Mapping[str, object]) -> None:
    required = {
        "schema_version",
        "task_id",
        "base_commit",
        "allowed_tree_identity_sha256",
        "allowed_tree_manifest_sha256",
        "expected_business_failure",
        "e_red",
        "d_red",
        "observed_changed_files",
        "outside_allowlist_change_count",
        "accepted_at_utc",
        "d_supervision_commit",
    }
    if set(acceptance) != required:
        raise ValueError("RED acceptance field set is not exact")
    if acceptance["schema_version"] != "rag.story-segment-red-acceptance/v1":
        raise ValueError("unsupported RED acceptance schema")
    if not _TASK_ID_RE.fullmatch(str(acceptance["task_id"])):
        raise ValueError("invalid RED acceptance task_id")
    _require_commit(acceptance["base_commit"], "base_commit")
    _require_commit(
        acceptance["d_supervision_commit"], "d_supervision_commit"
    )
    _require_sha(
        acceptance["allowed_tree_identity_sha256"],
        "allowed_tree_identity_sha256",
    )
    _require_sha(
        acceptance["allowed_tree_manifest_sha256"],
        "allowed_tree_manifest_sha256",
    )
    if not str(acceptance["expected_business_failure"]):
        raise ValueError("expected_business_failure is empty")
    for label in ("e_red", "d_red"):
        evidence = _mapping(acceptance[label], label)
        if set(evidence) != {
            "argv",
            "exit_code",
            "log_sha256",
            "observed_failure",
        }:
            raise ValueError(f"{label} field set is not exact")
        _require_argv(evidence["argv"], f"{label}.argv")
        if int(evidence["exit_code"]) == 0:
            raise ValueError(f"{label} must fail with a business RED")
        _require_sha(evidence["log_sha256"], f"{label}.log_sha256")
        if not str(evidence["observed_failure"]):
            raise ValueError(f"{label}.observed_failure is empty")
    _normalized_path_list(
        acceptance["observed_changed_files"], "observed_changed_files"
    )
    if int(acceptance["outside_allowlist_change_count"]) != 0:
        raise ValueError("RED acceptance has outside-allowlist changes")
    timestamp = str(acceptance["accepted_at_utc"])
    if not timestamp.endswith("Z"):
        raise ValueError("accepted_at_utc must be RFC3339 UTC")
    try:
        datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("accepted_at_utc must be RFC3339 UTC") from error


def _verify_tree_reference(value: object, label: str) -> None:
    reference = _mapping(value, label)
    if set(reference) != {"manifest_path", "manifest_sha256", "identity_sha256"}:
        raise ValueError(f"{label} field set is not exact")
    if not str(reference["manifest_path"]):
        raise ValueError(f"{label}.manifest_path is empty")
    _require_sha(reference["manifest_sha256"], f"{label}.manifest_sha256")
    _require_sha(reference["identity_sha256"], f"{label}.identity_sha256")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _require_sha(value: object, label: str) -> None:
    if not _SHA256_RE.fullmatch(str(value)):
        raise ValueError(f"{label} must be lowercase SHA-256")


def _require_commit(value: object, label: str) -> None:
    if not _COMMIT_RE.fullmatch(str(value)):
        raise ValueError(f"{label} must be lowercase 40-hex")


def _require_argv(value: object, label: str) -> None:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{label} must be a non-empty string array")


def _normalized_path_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty array")
    paths = tuple(_normalize_relative_path(str(item)) for item in value)
    if len(set(paths)) != len(paths):
        raise ValueError(f"{label} contains duplicates")
    if paths != tuple(sorted(paths)):
        raise ValueError(f"{label} must be in normalized sorted order")
    return paths


def _normalize_relative_path(value: str) -> str:
    text = value.replace("\\", "/")
    path = PurePosixPath(text)
    if (
        not text
        or not path.parts
        or path.is_absolute()
        or text.endswith("/")
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise ValueError(f"unsafe relative path: {value}")
    normalized = path.as_posix()
    if normalized == ".":
        raise ValueError(f"unsafe relative path: {value}")
    return normalized


def _reject_symlink_chain(root: Path, path: Path) -> None:
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"allowlisted path crosses a symlink: {current}")


def _changed_paths(root: Path, base_commit: str) -> frozenset[str]:
    tracked = _nul_paths(_git(root, "diff", "--name-only", "-z", base_commit, "--"))
    untracked = _nul_paths(
        _git(root, "ls-files", "--others", "--exclude-standard", "-z", "--")
    )
    return frozenset(
        _normalize_relative_path(path) for path in (*tracked, *untracked)
    )


def _nul_paths(raw: bytes) -> tuple[str, ...]:
    return tuple(
        part.decode("utf-8", errors="strict")
        for part in raw.split(b"\0")
        if part
    )


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            "Git identity command failed: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result.stdout


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="codex-task-receipts")
    commands = parser.add_subparsers(dest="command", required=True)
    identity = commands.add_parser("identity")
    identity.add_argument("--repository-root", required=True, type=Path)
    identity.add_argument("--base-commit", required=True)
    identity.add_argument("--allowed-file", action="append", required=True)
    identity.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "identity":
        identity = compute_allowed_tree_identity(
            repository_root=args.repository_root,
            base_commit=args.base_commit,
            allowed_relative_paths=args.allowed_file,
        )
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(identity.canonical_bytes)
        print(
            json.dumps(
                {
                    "manifest_path": str(output),
                    "manifest_sha256": hashlib.sha256(
                        identity.canonical_bytes
                    ).hexdigest(),
                    "identity_sha256": identity.identity_sha256,
                },
                sort_keys=True,
            )
        )
        return 0
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    verify_task_receipt(receipt)
    print(json.dumps({"valid": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
