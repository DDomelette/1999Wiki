from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class SnapshotFile:
    size: int
    sha256: str
    rows: int | None = None
    invalid_payload_rows: int | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> SnapshotFile:
        sha256 = str(value["sha256"]).lower()
        if len(sha256) != 64 or any(
            character not in "0123456789abcdef" for character in sha256
        ):
            raise ValueError("manifest contains an invalid SHA-256")
        return cls(
            size=int(value["size"]),
            sha256=sha256,
            rows=_optional_int(value.get("rows")),
            invalid_payload_rows=_optional_int(
                value.get("invalid_payload_rows")
            ),
        )


@dataclass(frozen=True)
class SnapshotManifest:
    schema_version: str
    snapshot_id: str
    files: Mapping[str, SnapshotFile]
    recover: tuple[str, ...]

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> SnapshotManifest:
        if value.get("schema_version") != "huiji-source-recovery/v1":
            raise ValueError("unsupported snapshot recovery manifest")
        files = {
            str(name): SnapshotFile.from_json(spec)
            for name, spec in value["files"].items()
        }
        recover = tuple(str(name) for name in value["recover"])
        if not recover or any(name not in files for name in recover):
            raise ValueError("manifest recover list is invalid")
        return cls(
            schema_version=str(value["schema_version"]),
            snapshot_id=str(value["snapshot_id"]),
            files=files,
            recover=recover,
        )

    @classmethod
    def load(cls, path: Path) -> SnapshotManifest:
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class AuditFile:
    status: str
    size: int | None
    sha256: str | None


@dataclass(frozen=True)
class RecoveryAudit:
    status: str
    snapshot_id: str
    source_root: Path
    target_root: Path
    manifest: SnapshotManifest
    files: Mapping[str, AuditFile]
    source_verified: bool
    invalid_payload_rows: int
    blockers: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "huiji-source-recovery-audit/v1",
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "source_root": str(self.source_root),
            "target_root": str(self.target_root),
            "source_verified": self.source_verified,
            "invalid_payload_rows": self.invalid_payload_rows,
            "files": {
                name: asdict(value) for name, value in self.files.items()
            },
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class RecoveryFileReceipt:
    status: str
    size: int
    sha256: str


@dataclass(frozen=True)
class RecoveryReceipt:
    status: str
    snapshot_id: str
    files: Mapping[str, RecoveryFileReceipt]
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "huiji-source-recovery-receipt/v1",
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "files": {
                name: asdict(value) for name, value in self.files.items()
            },
            "error": self.error,
        }


def audit_snapshot(
    source_root: Path,
    target_root: Path,
    manifest: SnapshotManifest,
) -> RecoveryAudit:
    source = source_root.resolve()
    target = target_root.resolve()
    if source == target:
        raise ValueError("source and target must be distinct")

    blockers: list[str] = []
    source_verified = True
    invalid_payload_rows = 0
    for name, expected in manifest.files.items():
        source_path = source / name
        problem = _verify_file(source_path, expected)
        if problem:
            source_verified = False
            blockers.append(f"source {name}: {problem}")
    data_spec = manifest.files.get("data_pages.jsonl")
    data_path = source / "data_pages.jsonl"
    if data_spec and data_path.is_file():
        rows, invalid_payload_rows = _inspect_data_pages(data_path)
        if data_spec.rows is not None and rows != data_spec.rows:
            source_verified = False
            blockers.append(
                f"source data_pages.jsonl rows {rows} != {data_spec.rows}"
            )
        if (
            data_spec.invalid_payload_rows is not None
            and invalid_payload_rows != data_spec.invalid_payload_rows
        ):
            source_verified = False
            blockers.append(
                "source data_pages.jsonl invalid payload rows "
                f"{invalid_payload_rows} != "
                f"{data_spec.invalid_payload_rows}"
            )
    sqlite_path = source / "crawl_state.sqlite"
    if sqlite_path.is_file():
        sqlite_result = _sqlite_quick_check(sqlite_path)
        if sqlite_result != "ok":
            source_verified = False
            blockers.append(
                f"source crawl_state.sqlite quick_check: {sqlite_result}"
            )

    files: dict[str, AuditFile] = {}
    for name, expected in manifest.files.items():
        target_path = target / name
        if not target_path.exists():
            status = "missing"
            if name not in manifest.recover:
                blockers.append(f"target sibling missing: {name}")
            files[name] = AuditFile(status, None, None)
            continue
        actual_size = target_path.stat().st_size
        actual_hash = _sha256(target_path)
        status = (
            "already_present"
            if actual_size == expected.size
            and actual_hash == expected.sha256
            else "mismatch"
        )
        if status == "mismatch":
            blockers.append(f"target mismatch: {name}")
        files[name] = AuditFile(status, actual_size, actual_hash)

    return RecoveryAudit(
        status="ready" if source_verified and not blockers else "blocked",
        snapshot_id=manifest.snapshot_id,
        source_root=source,
        target_root=target,
        manifest=manifest,
        files=files,
        source_verified=source_verified,
        invalid_payload_rows=invalid_payload_rows,
        blockers=tuple(blockers),
    )


def recover_missing_files(
    audit: RecoveryAudit,
    receipt_path: Path,
) -> RecoveryReceipt:
    mismatches = [
        name
        for name in audit.manifest.recover
        if audit.files[name].status == "mismatch"
    ]
    if mismatches:
        raise RuntimeError("target mismatch: " + ", ".join(mismatches))
    if audit.status != "ready" or not audit.source_verified:
        raise RuntimeError(
            "recovery audit is blocked: " + "; ".join(audit.blockers)
        )

    staging_root = (
        audit.target_root / f".recovery-staging-{uuid.uuid4().hex}"
    )
    staging_root.mkdir(parents=True, exist_ok=False)
    results: dict[str, RecoveryFileReceipt] = {}
    try:
        for name in audit.manifest.recover:
            expected = audit.manifest.files[name]
            source = audit.source_root / name
            target = audit.target_root / name
            if target.exists():
                problem = _verify_file(target, expected)
                if problem:
                    raise RuntimeError(f"target mismatch: {name}: {problem}")
                results[name] = RecoveryFileReceipt(
                    "already_present", expected.size, expected.sha256
                )
                continue

            staging = staging_root / name
            _copy_to_staging(source, staging)
            problem = _verify_file(staging, expected)
            if problem:
                raise RuntimeError(
                    f"staging hash mismatch: {name}: {problem}"
                )
            if name == "data_pages.jsonl":
                rows, invalid = _inspect_data_pages(staging)
                if expected.rows is not None and rows != expected.rows:
                    raise RuntimeError(
                        f"staging row mismatch: {rows} != {expected.rows}"
                    )
                if (
                    expected.invalid_payload_rows is not None
                    and invalid != expected.invalid_payload_rows
                ):
                    raise RuntimeError(
                        "staging invalid payload row mismatch"
                    )
            if name == "crawl_state.sqlite":
                result = _sqlite_quick_check(staging)
                if result != "ok":
                    raise RuntimeError(
                        f"staging SQLite quick_check failed: {result}"
                    )

            if target.exists():
                problem = _verify_file(target, expected)
                if problem:
                    raise RuntimeError(
                        f"target mismatch during publish: {name}: {problem}"
                    )
                staging.unlink(missing_ok=True)
                status = "already_present"
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging, target)
                problem = _verify_file(target, expected)
                if problem:
                    raise RuntimeError(
                        f"published file verification failed: {name}: {problem}"
                    )
                status = "recovered"
            results[name] = RecoveryFileReceipt(
                status, expected.size, expected.sha256
            )
        receipt = RecoveryReceipt(
            status="completed",
            snapshot_id=audit.snapshot_id,
            files=results,
        )
        _atomic_json_write(receipt_path, receipt.to_json())
        return receipt
    except BaseException as error:
        receipt = RecoveryReceipt(
            status="failed",
            snapshot_id=audit.snapshot_id,
            files=results,
            error=f"{type(error).__name__}: {error}",
        )
        _atomic_json_write(receipt_path, receipt.to_json())
        raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def write_audit_receipt(
    audit: RecoveryAudit,
    receipt_path: Path,
) -> None:
    _atomic_json_write(receipt_path, audit.to_json())


def _verify_file(path: Path, expected: SnapshotFile) -> str | None:
    if not path.is_file():
        return "missing"
    size = path.stat().st_size
    if size != expected.size:
        return f"size {size} != {expected.size}"
    digest = _sha256(path)
    if digest != expected.sha256:
        return f"sha256 {digest} != {expected.sha256}"
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_data_pages(path: Path) -> tuple[int, int]:
    rows = 0
    invalid_payload_rows = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            rows += 1
            wrapper = json.loads(line)
            if not isinstance(wrapper, dict):
                raise ValueError(
                    f"data_pages row {rows} is not a JSON object"
                )
            if wrapper.get("json_valid") is False:
                invalid_payload_rows += 1
    return rows, invalid_payload_rows


def _sqlite_quick_check(path: Path) -> str:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        row = connection.execute("PRAGMA quick_check").fetchone()
    finally:
        connection.close()
    return str(row[0]) if row else "no result"


def _copy_to_staging(source: Path, staging: Path) -> None:
    staging.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, staging.open("xb") as target:
        shutil.copyfileobj(
            source_handle,
            target,
            length=4 * 1024 * 1024,
        )
        target.flush()
        os.fsync(target.fileno())


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
