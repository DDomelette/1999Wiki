"""Read-only provenance fingerprints and evidence contracts for Huiji RAG."""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence


BASELINE_SCHEMA = "huiji.provenance_baseline/v1"
AUDIT_SCHEMA = "huiji.provenance_audit/v1"
RUNTIME_SCHEMA = "huiji.runtime_verification/v1"
SOURCE_MODE = "huiji_crawler"
MILVUS_CONNECT_TIMEOUT_SECONDS = 10.0

_HEX_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_PUBLIC_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-/]{1,256}\Z")
_SENSITIVE_TOKEN_RE = re.compile(
    r"(?i)(password|secret|access[_-]?key|api[_-]?key|token|credential)"
)


class ProvenanceValidationError(ValueError):
    """A stable, safely classifiable provenance validation failure."""

    def __init__(self, code: str, component: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.component = component


@dataclass(frozen=True)
class ArtifactFingerprint:
    relative_path: str
    sha256: str
    size_bytes: int
    row_count: int
    id_field: str
    id_count: int
    unique_id_count: int
    ids_sha256: str
    semantic_sha256: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Bm25Fingerprint:
    relative_path: str
    sha256: str
    size_bytes: int
    row_count: int
    ids_sha256: str
    semantic_sha256: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MilvusFingerprint:
    database: str
    collection: str
    schema_sha256: str
    row_count: int
    primary_field: str
    primary_id_count: int
    primary_ids_sha256: str
    business_fields_sha256: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AuditResult:
    status: Literal["pass", "blocked", "error"]
    issues: tuple[VerificationIssue, ...]
    source_mode: str
    build_version: str
    raw_snapshot: Mapping[str, Mapping[str, object]]
    artifacts: Mapping[str, ArtifactFingerprint]
    bm25: Mapping[str, Bm25Fingerprint]
    milvus: MilvusFingerprint | None
    counters: Mapping[str, int]
    audit_evidence_relpath: str = ""
    audit_evidence_sha256: str = ""

    def to_evidence_dict(self) -> dict[str, object]:
        return {
            "schema_version": AUDIT_SCHEMA,
            "status": self.status,
            "source_mode": self.source_mode,
            "build_version": self.build_version,
            "issues": [issue.to_public_dict() for issue in sorted(self.issues)],
            "raw_snapshot": {key: dict(value) for key, value in sorted(self.raw_snapshot.items())},
            "artifacts": {
                key: value.to_json() for key, value in sorted(self.artifacts.items())
            },
            "bm25": {key: value.to_json() for key, value in sorted(self.bm25.items())},
            "milvus": self.milvus.to_json() if self.milvus is not None else None,
            "counters": dict(sorted(self.counters.items())),
        }


@dataclass(frozen=True, order=True)
class VerificationIssue:
    code: str
    component: str
    expected: str = ""
    actual: str = ""

    def to_public_dict(self) -> dict[str, str]:
        return {
            "code": _safe_public_value(self.code),
            "component": _safe_public_value(self.component),
            "expected": _safe_public_value(self.expected),
            "actual": _safe_public_value(self.actual),
        }


@dataclass(frozen=True)
class VerificationResult:
    status: Literal["pass", "blocked", "error"]
    issues: tuple[VerificationIssue, ...]
    baseline_sha256: str
    evidence_relpath: str = ""
    duration_ms: int = 0

    @property
    def allowed(self) -> bool:
        return self.status == "pass" and not self.issues

    def to_public_dict(self) -> dict[str, object]:
        evidence = _safe_relative_public_path(self.evidence_relpath)
        return {
            "status": self.status if self.status in {"pass", "blocked", "error"} else "error",
            "issues": [issue.to_public_dict() for issue in sorted(self.issues)],
            "baseline_sha256": (
                self.baseline_sha256.lower()
                if _HEX_SHA256_RE.fullmatch(self.baseline_sha256.lower())
                else ""
            ),
            "evidence_relpath": evidence,
            "duration_ms": max(0, int(self.duration_ms)),
        }


def canonical_json_bytes(value: object) -> bytes:
    """Return deterministic UTF-8 JSON with exactly one trailing LF."""
    _reject_non_finite(value)
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(path: str | Path, project_root: str | Path) -> str:
    target = Path(path).resolve()
    root = Path(project_root).resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise ProvenanceValidationError(
            "path_outside_project",
            "filesystem",
            "path is outside project root",
        ) from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ProvenanceValidationError(
            "path_outside_project",
            "filesystem",
            "path is outside project root",
        )
    return relative.as_posix()


def write_hash_pinned_json(path: str | Path, payload: Mapping[str, object]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = canonical_json_bytes(dict(payload))
    digest = hashlib.sha256(body).hexdigest()
    with target.open("xb") as handle:
        handle.write(body)
    sidecar = target.with_name(f"{target.name}.sha256")
    with sidecar.open("xb") as handle:
        handle.write(f"{digest}  {target.name}\n".encode("ascii"))
    return digest


def fingerprint_jsonl(
    path: str | Path,
    *,
    project_root: str | Path,
    id_field: str,
    require_unique_ids: bool,
) -> ArtifactFingerprint:
    target = Path(path)
    rows = list(_iter_jsonl_rows(target))
    ids = [_required_id(row, id_field, target.name) for row in rows]
    if require_unique_ids and len(ids) != len(set(ids)):
        raise ProvenanceValidationError(
            "artifact_id_mismatch",
            target.name,
            f"duplicate {id_field}",
        )
    return ArtifactFingerprint(
        relative_path=safe_relative_path(target, project_root),
        sha256=sha256_file(target),
        size_bytes=target.stat().st_size,
        row_count=len(rows),
        id_field=id_field,
        id_count=len(ids),
        unique_id_count=len(set(ids)),
        ids_sha256=_sha256_lines(ids),
        semantic_sha256=_semantic_rows_sha256(rows),
    )


def fingerprint_bm25(
    path: str | Path,
    *,
    project_root: str | Path,
    source_rows: Sequence[Mapping[str, object]] | Iterable[Mapping[str, object]],
    source_id_field: str,
) -> Bm25Fingerprint:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceValidationError(
            "baseline_invalid",
            target.name,
            "BM25 payload is invalid",
        ) from error
    records = payload.get("records") if isinstance(payload, Mapping) else None
    if not isinstance(records, list) or not all(isinstance(row, Mapping) for row in records):
        raise ProvenanceValidationError(
            "baseline_invalid",
            target.name,
            "BM25 records must be a list of objects",
        )

    normalized_records: list[dict[str, object]] = []
    ids: list[str] = []
    for row in records:
        source_id = _required_id(row, source_id_field, target.name)
        derived_id = str(row.get("id") or "")
        if derived_id != source_id:
            raise ProvenanceValidationError(
                "bm25_id_mismatch",
                target.name,
                "BM25 derived id differs from source id",
            )
        item = dict(row)
        item.pop("id", None)
        normalized_records.append(item)
        ids.append(derived_id)

    frozen_source = [dict(row) for row in source_rows]
    source_digest = _semantic_rows_sha256(frozen_source)
    record_digest = _semantic_rows_sha256(normalized_records)
    if source_digest != record_digest:
        raise ProvenanceValidationError(
            "bm25_semantic_mismatch",
            target.name,
            "BM25 semantic corpus differs from source artifact",
        )
    return Bm25Fingerprint(
        relative_path=safe_relative_path(target, project_root),
        sha256=sha256_file(target),
        size_bytes=target.stat().st_size,
        row_count=len(records),
        ids_sha256=_sha256_lines(ids),
        semantic_sha256=record_digest,
    )


def normalize_milvus_schema(schema: Mapping[str, object]) -> dict[str, object]:
    raw_fields = schema.get("fields")
    if not isinstance(raw_fields, list):
        raise ProvenanceValidationError(
            "milvus_schema_mismatch",
            "milvus",
            "collection schema has no field list",
        )
    fields: list[dict[str, object]] = []
    for raw in raw_fields:
        if not isinstance(raw, Mapping) or not str(raw.get("name") or ""):
            raise ProvenanceValidationError(
                "milvus_schema_mismatch",
                "milvus",
                "collection schema contains an invalid field",
            )
        params = raw.get("params")
        if not isinstance(params, Mapping):
            params = raw.get("type_params")
        fields.append(
            {
                "name": str(raw.get("name")),
                "type": raw.get("type", raw.get("data_type", "")),
                "is_primary": bool(raw.get("is_primary", False)),
                "auto_id": bool(raw.get("auto_id", False)),
                "nullable": bool(raw.get("nullable", False)),
                "params": dict(params) if isinstance(params, Mapping) else {},
            }
        )
    return {
        "enable_dynamic_field": bool(schema.get("enable_dynamic_field", False)),
        "fields": sorted(fields, key=lambda field: str(field["name"])),
    }


def capture_milvus_fingerprint(
    client: object,
    collection_name: str,
    *,
    database: str,
) -> MilvusFingerprint:
    from src.rag.vectorstore import HUIJI_BUSINESS_FIELDS

    if not bool(client.has_collection(collection_name)):
        raise ProvenanceValidationError(
            "milvus_collection_missing",
            collection_name,
            "Milvus collection is missing",
        )
    schema = client.describe_collection(collection_name)
    if not isinstance(schema, Mapping):
        raise ProvenanceValidationError(
            "milvus_schema_mismatch",
            collection_name,
            "Milvus schema is invalid",
        )
    normalized_schema = normalize_milvus_schema(schema)
    primary_fields = [
        str(field["name"])
        for field in normalized_schema["fields"]
        if isinstance(field, Mapping) and field.get("is_primary")
    ]
    if primary_fields != ["id"]:
        raise ProvenanceValidationError(
            "milvus_schema_mismatch",
            collection_name,
            "Milvus primary field differs from id",
        )

    iterator = client.query_iterator(
        collection_name=collection_name,
        batch_size=1000,
        limit=-1,
        filter="",
        output_fields=list(HUIJI_BUSINESS_FIELDS),
    )
    rows: list[dict[str, object]] = []
    try:
        while True:
            batch = iterator.next()
            if not batch:
                break
            for raw in batch:
                if not isinstance(raw, Mapping):
                    raise ProvenanceValidationError(
                        "milvus_content_mismatch",
                        collection_name,
                        "Milvus query returned a non-object row",
                    )
                missing = [field for field in HUIJI_BUSINESS_FIELDS if field not in raw]
                if missing:
                    raise ProvenanceValidationError(
                        "milvus_content_mismatch",
                        collection_name,
                        "Milvus query omitted a business field",
                    )
                rows.append({field: raw[field] for field in HUIJI_BUSINESS_FIELDS})
    finally:
        iterator.close()

    ids = [str(row["id"]) for row in rows]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ProvenanceValidationError(
            "milvus_id_mismatch",
            collection_name,
            "Milvus primary IDs are blank or duplicated",
        )
    stats = client.get_collection_stats(collection_name)
    try:
        row_count = int(stats.get("row_count", 0))
    except (AttributeError, TypeError, ValueError) as error:
        raise ProvenanceValidationError(
            "milvus_row_count_mismatch",
            collection_name,
            "Milvus row count is invalid",
        ) from error
    if row_count != len(rows):
        raise ProvenanceValidationError(
            "milvus_row_count_mismatch",
            collection_name,
            "Milvus row count differs from queried rows",
        )
    return MilvusFingerprint(
        database=database,
        collection=collection_name,
        schema_sha256=hashlib.sha256(canonical_json_bytes(normalized_schema)).hexdigest(),
        row_count=row_count,
        primary_field="id",
        primary_id_count=len(ids),
        primary_ids_sha256=_sha256_lines(ids),
        business_fields_sha256=_semantic_rows_sha256(rows),
    )


def audit_huiji_provenance(cfg: object, client: object) -> AuditResult:
    """Perform the full raw-to-artifact-to-Milvus Huiji audit without writes."""
    from src.huiji_rag.io import build_paths
    from src.rag.vectorstore import huiji_child_to_business_row

    paths_cfg = getattr(cfg, "paths", None)
    project_root = Path(getattr(paths_cfg, "project_root", Path.cwd())).resolve()
    huiji = getattr(cfg, "huiji", None)
    vectorstore = getattr(cfg, "vectorstore", None)
    source_mode = str(getattr(huiji, "source_mode", ""))
    build_version = str(getattr(huiji, "build_version", ""))
    collection_name = str(getattr(vectorstore, "collection_name", ""))
    database = str(getattr(vectorstore, "db_name", ""))
    issues: list[VerificationIssue] = []
    raw_snapshot: dict[str, Mapping[str, object]] = {}
    artifacts: dict[str, ArtifactFingerprint] = {}
    bm25: dict[str, Bm25Fingerprint] = {}
    milvus: MilvusFingerprint | None = None
    counters = {
        "source_ref_occurrences": 0,
        "media_occurrences": 0,
        "data_page_rows": 0,
        "resource_rows": 0,
    }

    if not bool(getattr(huiji, "enabled", False)) or source_mode != SOURCE_MODE:
        issues.append(VerificationIssue("source_mode_mismatch", "huiji_config", SOURCE_MODE, source_mode))
    if not build_version:
        issues.append(VerificationIssue("build_version_mismatch", "huiji_config", "nonempty", "blank"))
    text_collection = str(getattr(huiji, "text_collection_name", ""))
    if not collection_name or text_collection != collection_name:
        issues.append(
            VerificationIssue(
                "collection_config_mismatch",
                "huiji_config",
                text_collection,
                collection_name,
            )
        )

    try:
        paths = build_paths(cfg)
        for candidate in (
            paths.raw_root,
            paths.build_root,
            paths.parent_blocks,
            paths.child_blocks,
            paths.media_assets,
            paths.child_bm25,
            paths.media_bm25,
        ):
            safe_relative_path(candidate, project_root)
    except ProvenanceValidationError as error:
        issues.append(_issue_from_error(error))
        return _audit_result("blocked", issues, source_mode, build_version, raw_snapshot, artifacts, bm25, None, counters)
    except Exception:
        issues.append(VerificationIssue("verification_internal_error", "build_paths"))
        return _audit_result("error", issues, source_mode, build_version, raw_snapshot, artifacts, bm25, None, counters)

    try:
        page_rows = list(_iter_jsonl_rows(paths.raw_root / "data_pages.jsonl"))
        resource_rows = list(_iter_jsonl_rows(paths.raw_root / "resources_manifest.jsonl"))
        parent_rows = list(_iter_jsonl_rows(paths.parent_blocks))
        child_rows = list(_iter_jsonl_rows(paths.child_blocks))
        media_rows = list(_iter_jsonl_rows(paths.media_assets))
        counters["data_page_rows"] = len(page_rows)
        counters["resource_rows"] = len(resource_rows)
        raw_snapshot = {
            "data_pages": _raw_file_fingerprint(
                paths.raw_root / "data_pages.jsonl", project_root, len(page_rows)
            ),
            "resources_manifest": _raw_file_fingerprint(
                paths.raw_root / "resources_manifest.jsonl", project_root, len(resource_rows)
            ),
        }
    except ProvenanceValidationError as error:
        issues.append(_issue_from_error(error))
        return _audit_result("blocked", issues, source_mode, build_version, raw_snapshot, artifacts, bm25, None, counters)

    for name, path, id_field, unique in (
        ("parent_blocks", paths.parent_blocks, "parent_id", True),
        ("child_blocks", paths.child_blocks, "child_id", True),
        ("media_assets", paths.media_assets, "media_id", False),
    ):
        try:
            artifacts[name] = fingerprint_jsonl(
                path,
                project_root=project_root,
                id_field=id_field,
                require_unique_ids=unique,
            )
        except ProvenanceValidationError as error:
            issues.append(_issue_from_error(error, name))

    source_issues, source_count = _audit_source_refs(page_rows, parent_rows, child_rows)
    issues.extend(source_issues)
    counters["source_ref_occurrences"] = source_count
    media_issues, media_count = _audit_media_refs(resource_rows, media_rows)
    issues.extend(media_issues)
    counters["media_occurrences"] = media_count

    for name, path, rows, id_field in (
        ("child_bm25", paths.child_bm25, child_rows, "child_id"),
        ("media_bm25", paths.media_bm25, media_rows, "media_id"),
    ):
        try:
            bm25[name] = fingerprint_bm25(
                path,
                project_root=project_root,
                source_rows=rows,
                source_id_field=id_field,
            )
        except ProvenanceValidationError as error:
            issues.append(_issue_from_error(error, name))

    try:
        milvus = capture_milvus_fingerprint(
            client,
            collection_name,
            database=database,
        )
        expected_rows = [huiji_child_to_business_row(dict(row)) for row in child_rows]
        expected_ids = [str(row["id"]) for row in expected_rows]
        if milvus.row_count != len(expected_rows):
            issues.append(
                VerificationIssue(
                    "milvus_row_count_mismatch",
                    collection_name,
                    str(len(expected_rows)),
                    str(milvus.row_count),
                )
            )
        if milvus.primary_ids_sha256 != _sha256_lines(expected_ids):
            issues.append(VerificationIssue("milvus_id_mismatch", collection_name))
        if milvus.business_fields_sha256 != _semantic_rows_sha256(expected_rows):
            issues.append(VerificationIssue("milvus_content_mismatch", collection_name))
    except ProvenanceValidationError as error:
        issues.append(_issue_from_error(error, collection_name))
    except Exception:
        issues.append(VerificationIssue("verification_internal_error", "milvus"))

    status: Literal["pass", "blocked", "error"] = "pass"
    if any(issue.code == "verification_internal_error" for issue in issues):
        status = "error"
    elif issues:
        status = "blocked"
    return _audit_result(
        status,
        issues,
        source_mode,
        build_version,
        raw_snapshot,
        artifacts,
        bm25,
        milvus,
        counters,
    )


def build_baseline_candidate(result: AuditResult) -> dict[str, object]:
    if result.status != "pass" or result.issues:
        raise ProvenanceValidationError(
            "audit_not_passed",
            "audit",
            "a baseline candidate requires a passed full audit",
        )
    if not _HEX_SHA256_RE.fullmatch(result.audit_evidence_sha256.lower()):
        raise ProvenanceValidationError(
            "audit_evidence_mismatch",
            "audit",
            "audit evidence SHA-256 is missing",
        )
    evidence_path = _safe_relative_public_path(result.audit_evidence_relpath)
    if not evidence_path:
        raise ProvenanceValidationError(
            "audit_evidence_mismatch",
            "audit",
            "audit evidence path is invalid",
        )
    if result.milvus is None:
        raise ProvenanceValidationError(
            "milvus_collection_missing",
            "milvus",
            "passed audit lacks Milvus evidence",
        )
    return {
        "schema_version": BASELINE_SCHEMA,
        "source_mode": result.source_mode,
        "build_version": result.build_version,
        "raw_snapshot": {
            key: dict(value) for key, value in sorted(result.raw_snapshot.items())
        },
        "artifacts": {
            key: value.to_json() for key, value in sorted(result.artifacts.items())
        },
        "bm25": {key: value.to_json() for key, value in sorted(result.bm25.items())},
        "milvus": result.milvus.to_json(),
        "audit_evidence": {
            "relative_path": evidence_path,
            "sha256": result.audit_evidence_sha256.lower(),
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator_version": "1",
    }


def install_baseline_create_new(
    candidate_path: str | Path,
    output_path: str | Path,
    *,
    project_root: str | Path,
) -> str:
    candidate = Path(candidate_path)
    root = Path(project_root).resolve()
    safe_relative_path(candidate, root)
    actual_candidate_sha = sha256_file(candidate)
    if _read_sidecar_sha256(candidate) != actual_candidate_sha:
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline_candidate",
            "candidate sidecar does not match candidate",
        )
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline_candidate",
            "candidate JSON is invalid",
        ) from error
    if not isinstance(payload, Mapping) or payload.get("schema_version") != BASELINE_SCHEMA:
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline_candidate",
            "candidate schema is invalid",
        )
    if candidate.read_bytes() != canonical_json_bytes(payload):
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline_candidate",
            "candidate is not canonical JSON",
        )
    audit = payload.get("audit_evidence")
    if not isinstance(audit, Mapping):
        raise ProvenanceValidationError(
            "audit_evidence_mismatch",
            "audit",
            "candidate has no audit evidence",
        )
    relative = _safe_relative_public_path(audit.get("relative_path"))
    expected_sha = str(audit.get("sha256") or "").lower()
    if not relative or not _HEX_SHA256_RE.fullmatch(expected_sha):
        raise ProvenanceValidationError(
            "audit_evidence_mismatch",
            "audit",
            "candidate audit reference is invalid",
        )
    audit_path = (root / relative).resolve()
    safe_relative_path(audit_path, root)
    if not audit_path.is_file() or sha256_file(audit_path) != expected_sha:
        raise ProvenanceValidationError(
            "audit_evidence_mismatch",
            "audit",
            "audit evidence content differs from candidate",
        )
    if _read_sidecar_sha256(audit_path) != expected_sha:
        raise ProvenanceValidationError(
            "audit_evidence_mismatch",
            "audit",
            "audit evidence sidecar differs from candidate",
        )
    return write_hash_pinned_json(output_path, dict(payload))


def load_provenance_baseline(
    path: str | Path,
    *,
    project_root: str | Path,
) -> tuple[dict[str, object], str]:
    target = Path(path)
    safe_relative_path(target, project_root)
    if not target.is_file():
        raise ProvenanceValidationError(
            "baseline_missing",
            "baseline",
            "configured provenance baseline is missing",
        )
    try:
        digest = sha256_file(target)
        if _read_sidecar_sha256(target) != digest:
            raise ProvenanceValidationError(
                "baseline_invalid",
                "baseline",
                "baseline sidecar does not match",
            )
        payload = json.loads(target.read_text(encoding="utf-8"))
    except ProvenanceValidationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline",
            "baseline JSON is invalid",
        ) from error
    if not isinstance(payload, Mapping) or payload.get("schema_version") != BASELINE_SCHEMA:
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline",
            "baseline schema is invalid",
        )
    if target.read_bytes() != canonical_json_bytes(payload):
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline",
            "baseline is not canonical JSON",
        )
    required = {"source_mode", "build_version", "artifacts", "bm25", "milvus", "audit_evidence"}
    if not required.issubset(payload):
        raise ProvenanceValidationError(
            "baseline_invalid",
            "baseline",
            "baseline required fields are missing",
        )
    return dict(payload), digest


def verify_runtime(
    cfg: object,
    *,
    client_factory: Any = None,
) -> VerificationResult:
    """Verify the installed baseline against runtime inputs without reading raw data."""
    from src.huiji_rag.io import build_paths
    from src.huiji_rag.active_pointer import load_active_pointer

    started = time.perf_counter()
    paths_cfg = getattr(cfg, "paths", None)
    project_root = Path(getattr(paths_cfg, "project_root", Path.cwd())).resolve()
    huiji = getattr(cfg, "huiji", None)
    vectorstore = getattr(cfg, "vectorstore", None)
    pointer_path = Path(getattr(huiji, "processed_root", "")) / "active_build.v1.json"
    if pointer_path.is_file():
        try:
            pointer = load_active_pointer(pointer_path)
        except Exception:
            return _verification_result(
                "blocked",
                (VerificationIssue("active_pointer_invalid", "active_pointer"),),
                "",
                started,
            )
        if int(pointer["generation"]) > 0:
            return _verify_activated_runtime(
                cfg,
                pointer=pointer,
                started=started,
                client_factory=client_factory,
            )
    baseline_path = Path(getattr(huiji, "provenance_baseline", ""))
    try:
        baseline, baseline_sha = load_provenance_baseline(
            baseline_path,
            project_root=project_root,
        )
    except ProvenanceValidationError as error:
        return _verification_result(
            "blocked",
            (VerificationIssue(error.code, error.component),),
            "",
            started,
        )
    except Exception:
        return _verification_result(
            "error",
            (VerificationIssue("verification_internal_error", "baseline"),),
            "",
            started,
        )

    issues: list[VerificationIssue] = []
    source_mode = str(getattr(huiji, "source_mode", ""))
    build_version = str(getattr(huiji, "build_version", ""))
    baseline_source = str(baseline.get("source_mode") or "")
    baseline_build = str(baseline.get("build_version") or "")
    if not bool(getattr(huiji, "enabled", False)) or source_mode != SOURCE_MODE or source_mode != baseline_source:
        issues.append(VerificationIssue("source_mode_mismatch", "huiji_config", baseline_source, source_mode))
    if build_version != baseline_build:
        issues.append(VerificationIssue("build_version_mismatch", "huiji_config", baseline_build, build_version))
    configured_collection = str(getattr(vectorstore, "collection_name", ""))
    huiji_collection = str(getattr(huiji, "text_collection_name", ""))
    baseline_milvus = baseline.get("milvus")
    baseline_collection = (
        str(baseline_milvus.get("collection") or "")
        if isinstance(baseline_milvus, Mapping)
        else ""
    )
    if (
        not configured_collection
        or huiji_collection != configured_collection
        or baseline_collection != configured_collection
    ):
        issues.append(
            VerificationIssue(
                "collection_config_mismatch",
                "huiji_config",
                baseline_collection,
                configured_collection,
            )
        )

    try:
        paths = build_paths(cfg)
        expected_paths = {
            "parent_blocks": paths.parent_blocks,
            "child_blocks": paths.child_blocks,
            "media_assets": paths.media_assets,
            "child_bm25": paths.child_bm25,
            "media_bm25": paths.media_bm25,
        }
        for path in expected_paths.values():
            safe_relative_path(path, project_root)
        artifact_baseline = baseline.get("artifacts")
        bm25_baseline = baseline.get("bm25")
        if not isinstance(artifact_baseline, Mapping) or not isinstance(bm25_baseline, Mapping):
            raise ProvenanceValidationError("baseline_invalid", "baseline")

        current_artifacts: dict[str, ArtifactFingerprint] = {}
        for name, id_field, unique in (
            ("parent_blocks", "parent_id", True),
            ("child_blocks", "child_id", True),
            ("media_assets", "media_id", False),
        ):
            path = expected_paths[name]
            expected = artifact_baseline.get(name)
            if not path.is_file():
                issues.append(VerificationIssue("artifact_missing", name))
                continue
            if not isinstance(expected, Mapping) or expected.get("relative_path") != safe_relative_path(path, project_root):
                issues.append(VerificationIssue("artifact_missing", name))
                continue
            current = fingerprint_jsonl(
                path,
                project_root=project_root,
                id_field=id_field,
                require_unique_ids=unique,
            )
            current_artifacts[name] = current
            issues.extend(_compare_artifact_fingerprint(name, expected, current))

        child_rows = list(_iter_jsonl_rows(paths.child_blocks)) if paths.child_blocks.is_file() else []
        media_rows = list(_iter_jsonl_rows(paths.media_assets)) if paths.media_assets.is_file() else []
        for name, rows, id_field in (
            ("child_bm25", child_rows, "child_id"),
            ("media_bm25", media_rows, "media_id"),
        ):
            path = expected_paths[name]
            expected = bm25_baseline.get(name)
            if not path.is_file():
                issues.append(VerificationIssue("artifact_missing", name))
                continue
            if not isinstance(expected, Mapping) or expected.get("relative_path") != safe_relative_path(path, project_root):
                issues.append(VerificationIssue("artifact_missing", name))
                continue
            try:
                current = fingerprint_bm25(
                    path,
                    project_root=project_root,
                    source_rows=rows,
                    source_id_field=id_field,
                )
            except ProvenanceValidationError as error:
                issues.append(_issue_from_error(error, name))
                continue
            issues.extend(_compare_bm25_fingerprint(name, expected, current))
    except ProvenanceValidationError as error:
        issues.append(_issue_from_error(error))
    except Exception:
        return _verification_result(
            "error",
            (VerificationIssue("verification_internal_error", "artifacts"),),
            baseline_sha,
            started,
        )

    try:
        if client_factory is None:
            client = _runtime_milvus_client(cfg)
        else:
            client = client_factory(cfg)
        current_milvus = capture_milvus_fingerprint(
            client,
            configured_collection,
            database=str(getattr(vectorstore, "db_name", "")),
        )
        if not isinstance(baseline_milvus, Mapping):
            issues.append(VerificationIssue("baseline_invalid", "milvus"))
        else:
            issues.extend(_compare_milvus_fingerprint(baseline_milvus, current_milvus))
    except ProvenanceValidationError as error:
        issues.append(_issue_from_error(error, configured_collection or "milvus"))
    except Exception:
        return _verification_result(
            "error",
            (VerificationIssue("verification_internal_error", "milvus"),),
            baseline_sha,
            started,
        )

    return _verification_result(
        "blocked" if issues else "pass",
        tuple(issues),
        baseline_sha,
        started,
    )


def _verify_activated_runtime(
    cfg: object,
    *,
    pointer: Mapping[str, object],
    started: float,
    client_factory: Any,
) -> VerificationResult:
    """Verify a nonzero active tuple from its transaction-owned manifest."""
    from src.huiji_rag.active_pointer import resolve_activation_evidence
    from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot

    huiji = getattr(cfg, "huiji", None)
    vectorstore = getattr(cfg, "vectorstore", None)
    processed_root = Path(getattr(huiji, "processed_root", "")).resolve()
    issues: list[VerificationIssue] = []
    configured_collection = str(getattr(vectorstore, "collection_name", ""))
    huiji_collection = str(getattr(huiji, "text_collection_name", ""))
    configured_build = str(getattr(huiji, "build_version", ""))
    pointer_collection = str(pointer.get("milvus_collection_name") or "")
    pointer_build = str(pointer.get("build_version") or "")
    if (
        configured_collection != pointer_collection
        or huiji_collection != pointer_collection
    ):
        issues.append(
            VerificationIssue(
                "collection_config_mismatch",
                "huiji_config",
                pointer_collection,
                configured_collection,
            )
        )
    if configured_build != pointer_build:
        issues.append(
            VerificationIssue(
                "build_version_mismatch",
                "huiji_config",
                pointer_build,
                configured_build,
            )
        )
    try:
        snapshot = resolve_runtime_artifact_snapshot(cfg)
        if (
            snapshot.build_version != pointer_build
            or snapshot.collection_name != pointer_collection
            or snapshot.artifact_schema_version
            != pointer.get("artifact_schema_version")
        ):
            issues.append(VerificationIssue("runtime_tuple_mismatch", "artifacts"))
        manifest_path, _ = resolve_activation_evidence(processed_root, pointer)
        manifest_sha = sha256_file(manifest_path)
        if manifest_sha != pointer.get("collection_manifest_sha256"):
            issues.append(
                VerificationIssue("collection_manifest_hash_mismatch", "manifest")
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_milvus = manifest.get("milvus")
        if not isinstance(expected_milvus, Mapping):
            issues.append(VerificationIssue("manifest_invalid", "milvus"))
        else:
            if client_factory is None:
                client = _runtime_milvus_client(cfg)
            else:
                client = client_factory(cfg)
            current = capture_milvus_fingerprint(
                client,
                pointer_collection,
                database=str(getattr(vectorstore, "db_name", "")),
            )
            issues.extend(_compare_milvus_fingerprint(expected_milvus, current))
    except ProvenanceValidationError as error:
        issues.append(_issue_from_error(error))
        manifest_sha = str(pointer.get("collection_manifest_sha256") or "")
    except Exception:
        return _verification_result(
            "error",
            (VerificationIssue("verification_internal_error", "activation"),),
            str(pointer.get("collection_manifest_sha256") or ""),
            started,
        )
    return _verification_result(
        "blocked" if issues else "pass",
        tuple(issues),
        manifest_sha,
        started,
    )


def _runtime_milvus_client(cfg: object) -> object:
    from pymilvus import MilvusClient

    vectorstore = getattr(cfg, "vectorstore")
    return MilvusClient(
        uri=str(getattr(vectorstore, "uri")),
        db_name=str(getattr(vectorstore, "db_name")),
        timeout=MILVUS_CONNECT_TIMEOUT_SECONDS,
    )


def _verification_result(
    status: Literal["pass", "blocked", "error"],
    issues: Sequence[VerificationIssue],
    baseline_sha256: str,
    started: float,
) -> VerificationResult:
    return VerificationResult(
        status=status,
        issues=tuple(sorted(set(issues))),
        baseline_sha256=baseline_sha256,
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def _compare_artifact_fingerprint(
    component: str,
    expected: Mapping[str, object],
    actual: ArtifactFingerprint,
) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    if expected.get("sha256") != actual.sha256 or expected.get("size_bytes") != actual.size_bytes:
        issues.append(VerificationIssue("artifact_hash_mismatch", component))
    if expected.get("row_count") != actual.row_count:
        issues.append(VerificationIssue("artifact_count_mismatch", component))
    if (
        expected.get("id_count") != actual.id_count
        or expected.get("unique_id_count") != actual.unique_id_count
        or expected.get("ids_sha256") != actual.ids_sha256
    ):
        issues.append(VerificationIssue("artifact_id_mismatch", component))
    if expected.get("semantic_sha256") != actual.semantic_sha256:
        issues.append(VerificationIssue("artifact_hash_mismatch", component))
    return issues


def _compare_bm25_fingerprint(
    component: str,
    expected: Mapping[str, object],
    actual: Bm25Fingerprint,
) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    if expected.get("sha256") != actual.sha256 or expected.get("size_bytes") != actual.size_bytes:
        issues.append(VerificationIssue("artifact_hash_mismatch", component))
    if expected.get("row_count") != actual.row_count:
        issues.append(VerificationIssue("artifact_count_mismatch", component))
    if expected.get("ids_sha256") != actual.ids_sha256:
        issues.append(VerificationIssue("artifact_id_mismatch", component))
    if expected.get("semantic_sha256") != actual.semantic_sha256:
        issues.append(VerificationIssue("artifact_hash_mismatch", component))
    return issues


def _compare_milvus_fingerprint(
    expected: Mapping[str, object],
    actual: MilvusFingerprint,
) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    component = actual.collection
    if expected.get("database") != actual.database or expected.get("collection") != actual.collection:
        issues.append(VerificationIssue("collection_config_mismatch", component))
    if expected.get("schema_sha256") != actual.schema_sha256:
        issues.append(VerificationIssue("milvus_schema_mismatch", component))
    if expected.get("row_count") != actual.row_count:
        issues.append(VerificationIssue("milvus_row_count_mismatch", component))
    if (
        expected.get("primary_field") != actual.primary_field
        or expected.get("primary_id_count") != actual.primary_id_count
        or expected.get("primary_ids_sha256") != actual.primary_ids_sha256
    ):
        issues.append(VerificationIssue("milvus_id_mismatch", component))
    if expected.get("business_fields_sha256") != actual.business_fields_sha256:
        issues.append(VerificationIssue("milvus_content_mismatch", component))
    return issues


def _audit_source_refs(
    page_rows: Sequence[Mapping[str, object]],
    parent_rows: Sequence[Mapping[str, object]],
    child_rows: Sequence[Mapping[str, object]],
) -> tuple[list[VerificationIssue], int]:
    by_title: dict[str, list[Mapping[str, object]]] = {}
    for row in page_rows:
        by_title.setdefault(str(row.get("title") or ""), []).append(row)
    issues: list[VerificationIssue] = []
    count = 0
    for component, rows in (("parent_blocks", parent_rows), ("child_blocks", child_rows)):
        for row in rows:
            refs = row.get("source_refs")
            if not isinstance(refs, list) or not refs:
                issues.append(VerificationIssue("source_ref_missing", component))
                continue
            for ref in refs:
                count += 1
                if not isinstance(ref, Mapping):
                    issues.append(VerificationIssue("source_ref_missing", component))
                    continue
                if str(ref.get("kind") or "") != "data_page":
                    issues.append(VerificationIssue("source_kind_mismatch", component))
                    continue
                title = str(ref.get("title") or "")
                candidates = by_title.get(title, [])
                if not candidates:
                    issues.append(VerificationIssue("source_ref_missing", component))
                    continue
                try:
                    revid = int(ref.get("revid"))
                except (TypeError, ValueError):
                    issues.append(VerificationIssue("source_revision_mismatch", component))
                    continue
                revisions = [row for row in candidates if int(row.get("revid") or -1) == revid]
                if not revisions:
                    issues.append(VerificationIssue("source_revision_mismatch", component))
                    continue
                digest = str(ref.get("content_sha256") or "").lower()
                if not any(str(row.get("content_sha256") or "").lower() == digest for row in revisions):
                    issues.append(VerificationIssue("source_hash_mismatch", component))
    return issues, count


def _audit_media_refs(
    resource_rows: Sequence[Mapping[str, object]],
    media_rows: Sequence[Mapping[str, object]],
) -> tuple[list[VerificationIssue], int]:
    normalized = [
        (
            str(row.get("sha1") or "").lower(),
            str(row.get("local_relpath") or "").replace("\\", "/"),
            str(row.get("url") or ""),
        )
        for row in resource_rows
    ]
    known_sha = {item[0] for item in normalized}
    known_sha_path = {(item[0], item[1]) for item in normalized}
    known_exact = set(normalized)
    issues: list[VerificationIssue] = []
    for row in media_rows:
        sha1 = str(row.get("sha1") or "").lower()
        local_path = str(row.get("local_relpath") or "").replace("\\", "/")
        source_url = str(row.get("source_url") or "")
        if (sha1, local_path, source_url) in known_exact:
            continue
        if sha1 not in known_sha:
            issues.append(VerificationIssue("media_sha1_mismatch", "media_assets"))
        elif (sha1, local_path) not in known_sha_path:
            issues.append(VerificationIssue("media_path_mismatch", "media_assets"))
        else:
            issues.append(VerificationIssue("media_url_mismatch", "media_assets"))
    return issues, len(media_rows)


def _raw_file_fingerprint(path: Path, project_root: Path, row_count: int) -> dict[str, object]:
    return {
        "relative_path": safe_relative_path(path, project_root),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "row_count": row_count,
    }


def _audit_result(
    status: Literal["pass", "blocked", "error"],
    issues: Sequence[VerificationIssue],
    source_mode: str,
    build_version: str,
    raw_snapshot: Mapping[str, Mapping[str, object]],
    artifacts: Mapping[str, ArtifactFingerprint],
    bm25: Mapping[str, Bm25Fingerprint],
    milvus: MilvusFingerprint | None,
    counters: Mapping[str, int],
) -> AuditResult:
    return AuditResult(
        status=status,
        issues=tuple(sorted(set(issues))),
        source_mode=source_mode,
        build_version=build_version,
        raw_snapshot=dict(raw_snapshot),
        artifacts=dict(artifacts),
        bm25=dict(bm25),
        milvus=milvus,
        counters=dict(counters),
    )


def _issue_from_error(error: ProvenanceValidationError, component: str = "") -> VerificationIssue:
    return VerificationIssue(error.code, component or error.component)


def _read_sidecar_sha256(path: Path) -> str:
    sidecar = path.with_name(f"{path.name}.sha256")
    try:
        parts = sidecar.read_text(encoding="ascii").strip().split()
    except (OSError, UnicodeDecodeError) as error:
        raise ProvenanceValidationError(
            "baseline_invalid",
            path.name,
            "SHA-256 sidecar is missing or invalid",
        ) from error
    if len(parts) != 2 or parts[1] != path.name or not _HEX_SHA256_RE.fullmatch(parts[0].lower()):
        raise ProvenanceValidationError(
            "baseline_invalid",
            path.name,
            "SHA-256 sidecar is malformed",
        )
    return parts[0].lower()


def _iter_jsonl_rows(path: Path) -> Iterable[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, Mapping):
                    raise ValueError(f"row {line_number} is not an object")
                yield dict(value)
    except ProvenanceValidationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ProvenanceValidationError(
            "baseline_invalid",
            path.name,
            "artifact JSONL is invalid",
        ) from error


def _required_id(row: Mapping[str, object], field: str, component: str) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise ProvenanceValidationError(
            "artifact_id_mismatch",
            component,
            f"blank {field}",
        )
    return value


def _semantic_rows_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    encoded = sorted(canonical_json_bytes(dict(row)) for row in rows)
    for row in encoded:
        digest.update(row)
    return digest.hexdigest()


def _sha256_lines(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(str(item) for item in values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _reject_non_finite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical JSON numbers must be finite")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_non_finite(key)
            _reject_non_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_non_finite(item)


def _safe_public_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _SENSITIVE_TOKEN_RE.search(text):
        return ""
    if _HEX_SHA256_RE.fullmatch(text.lower()):
        return text.lower()
    if _SAFE_PUBLIC_TOKEN_RE.fullmatch(text) and ".." not in text:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"redacted-{digest}"


def _safe_relative_public_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return ""
    if any(part in {"", ".", ".."} for part in text.split("/")):
        return ""
    if not _SAFE_PUBLIC_TOKEN_RE.fullmatch(text) or _SENSITIVE_TOKEN_RE.search(text):
        return ""
    return text
