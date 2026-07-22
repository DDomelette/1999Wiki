"""Build one explicit, new, non-active Huiji Milvus shadow collection."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.build.contracts import canonical_json_bytes
from src.huiji_rag.io import iter_jsonl
from src.huiji_rag.provenance import (
    ProvenanceValidationError,
    capture_milvus_fingerprint,
    load_provenance_baseline,
    safe_relative_path,
    sha256_file,
    verify_runtime,
    write_hash_pinned_json,
)
from src.rag.sparse import canonical_child_corpus_sha256
from src.rag.vectorstore import build_huiji_shadow_collection, huiji_child_to_business_row


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class CandidateHandoff:
    path: Path
    sha256: str
    build_version: str
    children: tuple[dict[str, Any], ...]
    child_artifact: Mapping[str, object]
    child_ordered_ids_sha256: str
    child_semantic_corpus_sha256: str
    embedding_config_fingerprint_sha256: str
    forbidden_collection_names: tuple[str, ...]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a new Huiji shadow collection")
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--handoff-manifest", type=Path, required=True)
    parser.add_argument("--expected-handoff-sha256", required=True)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--batch-delay-seconds", type=float, default=0.6)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-seconds", type=float, default=60.0)
    return parser


def _default_client(cfg: object) -> object:
    from pymilvus import MilvusClient

    vectorstore = getattr(cfg, "vectorstore")
    return MilvusClient(
        uri=str(getattr(vectorstore, "uri")),
        db_name=str(getattr(vectorstore, "db_name")),
    )


def _default_embeddings(cfg: object) -> object:
    from src.rag.embeddings import get_embeddings

    return get_embeddings(cfg)


def _sha256_rows(rows: Sequence[Mapping[str, object]]) -> str:
    from src.huiji_rag.provenance import canonical_json_bytes

    digest = hashlib.sha256()
    for row in sorted(canonical_json_bytes(dict(value)) for value in rows):
        digest.update(row)
    return digest.hexdigest()


def _sha256_ids(values: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _sha256_ordered_ids(values: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _embedding_config_fingerprint(cfg: object) -> str:
    embedding = getattr(cfg, "embedding", None)
    payload = {
        "schema_version": "huiji.embedding-config/v1",
        "provider": str(getattr(embedding, "provider", "")),
        "model": str(getattr(embedding, "model", "")),
    }
    if not payload["provider"] or not payload["model"]:
        raise ProvenanceValidationError(
            "embedding_config_invalid", "embedding_config"
        )
    return hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()


def _require_embedding_credentials(cfg: object) -> None:
    embedding = getattr(cfg, "embedding", None)
    if not str(getattr(embedding, "api_key", "")).strip():
        raise ProvenanceValidationError(
            "embedding_credentials_missing", "embedding_config"
        )


def _load_candidate_handoff(
    cfg: object,
    handoff_path: Path,
    expected_sha256: str,
) -> CandidateHandoff:
    project_root = Path(getattr(getattr(cfg, "paths"), "project_root")).resolve()
    path = Path(handoff_path).resolve()
    safe_relative_path(path, project_root)
    expected = str(expected_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(expected):
        raise ProvenanceValidationError(
            "embedding_handoff_hash_invalid", "embedding_handoff"
        )
    if not path.is_file():
        raise ProvenanceValidationError(
            "embedding_handoff_missing", "embedding_handoff"
        )
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected:
        raise ProvenanceValidationError(
            "embedding_handoff_hash_mismatch", "embedding_handoff"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProvenanceValidationError(
            "embedding_handoff_invalid", "embedding_handoff"
        ) from error
    if not isinstance(payload, Mapping) or payload.get("schema_version") != "huiji.embedding-handoff/v1":
        raise ProvenanceValidationError(
            "embedding_handoff_invalid", "embedding_handoff"
        )

    build_version = str(payload.get("build_version") or "").strip()
    child = payload.get("child_artifact")
    requirements = payload.get("target_requirements")
    if not build_version or not isinstance(child, Mapping) or not isinstance(requirements, Mapping):
        raise ProvenanceValidationError(
            "embedding_handoff_invalid", "embedding_handoff"
        )
    if any(
        requirements.get(name) is not True
        for name in ("must_be_new", "must_not_be_active", "must_not_exist")
    ):
        raise ProvenanceValidationError(
            "embedding_target_requirements_invalid", "embedding_handoff"
        )

    relative_text = str(child.get("relative_path") or "")
    relative = PurePosixPath(relative_text)
    if (
        not relative_text
        or "\\" in relative_text
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ProvenanceValidationError(
            "embedding_child_path_invalid", "child_artifact"
        )
    build_root = path.parent.parent.resolve()
    child_path = (build_root / Path(*relative.parts)).resolve()
    try:
        child_path.relative_to(build_root)
    except ValueError as error:
        raise ProvenanceValidationError(
            "embedding_child_path_invalid", "child_artifact"
        ) from error
    safe_relative_path(child_path, project_root)
    if not child_path.is_file():
        raise ProvenanceValidationError(
            "embedding_child_artifact_missing", "child_artifact"
        )

    expected_child_sha = str(child.get("sha256") or "").lower()
    if not _SHA256_RE.fullmatch(expected_child_sha) or sha256_file(child_path) != expected_child_sha:
        raise ProvenanceValidationError("artifact_hash_mismatch", "child_blocks")
    try:
        expected_size = int(child.get("size"))
        expected_rows = int(child.get("row_count"))
    except (TypeError, ValueError) as error:
        raise ProvenanceValidationError(
            "embedding_handoff_invalid", "child_artifact"
        ) from error
    if child.get("schema_version") != "huiji.child-blocks/v2":
        raise ProvenanceValidationError(
            "embedding_child_schema_mismatch", "child_artifact"
        )
    if child_path.stat().st_size != expected_size:
        raise ProvenanceValidationError("artifact_size_mismatch", "child_blocks")

    try:
        children = tuple(dict(row) for row in iter_jsonl(child_path))
    except (OSError, UnicodeError, ValueError) as error:
        raise ProvenanceValidationError(
            "embedding_child_artifact_invalid", "child_artifact"
        ) from error
    child_ids = [str(row.get("child_id") or "") for row in children]
    if (
        len(children) != expected_rows
        or any(not value for value in child_ids)
        or len(set(child_ids)) != len(child_ids)
    ):
        raise ProvenanceValidationError(
            "embedding_child_row_mismatch", "child_artifact"
        )
    ordered_ids_sha256 = _sha256_ordered_ids(child_ids)
    expected_ordered_ids = str(payload.get("child_ordered_ids_sha256") or "")
    if ordered_ids_sha256 != expected_ordered_ids:
        raise ProvenanceValidationError(
            "embedding_child_id_mismatch", "child_artifact"
        )
    semantic_sha256 = canonical_child_corpus_sha256(children)
    expected_semantic = str(payload.get("child_semantic_corpus_sha256") or "")
    if semantic_sha256 != expected_semantic:
        raise ProvenanceValidationError(
            "embedding_child_content_mismatch", "child_artifact"
        )
    config_fingerprint = _embedding_config_fingerprint(cfg)
    expected_config_fingerprint = str(
        payload.get("embedding_config_fingerprint_sha256") or ""
    )
    if config_fingerprint != expected_config_fingerprint:
        raise ProvenanceValidationError(
            "embedding_config_mismatch", "embedding_config"
        )

    forbidden_raw = requirements.get("forbidden_collection_names")
    if not isinstance(forbidden_raw, list) or any(
        not isinstance(value, str) or not value.strip() for value in forbidden_raw
    ):
        raise ProvenanceValidationError(
            "embedding_target_requirements_invalid", "embedding_handoff"
        )
    return CandidateHandoff(
        path=path,
        sha256=actual_sha256,
        build_version=build_version,
        children=children,
        child_artifact=dict(child),
        child_ordered_ids_sha256=ordered_ids_sha256,
        child_semantic_corpus_sha256=semantic_sha256,
        embedding_config_fingerprint_sha256=config_fingerprint,
        forbidden_collection_names=tuple(sorted(set(forbidden_raw))),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    cfg_loader: Callable[[], Any] = get_config,
    client_factory: Callable[[object], object] = _default_client,
    embeddings_factory: Callable[[object], object] = _default_embeddings,
) -> int:
    args = _parser().parse_args(argv)
    cfg = cfg_loader()
    project_root = Path(getattr(getattr(cfg, "paths"), "project_root")).resolve()
    if args.run_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = project_root / "eval" / "huiji_provenance" / f"{stamp}-shadow-{uuid4().hex[:8]}"
    else:
        run_dir = Path(args.run_dir)
    evidence_path = run_dir / "shadow-build.v1.json"
    target = str(args.collection_name).strip()
    inserted = 0
    baseline_sha = ""
    handoff_sha = ""
    handoff_relative = ""
    candidate_build_version = ""
    child_artifact_evidence: dict[str, object] | None = None
    embedding_config_fingerprint = ""
    settings_path = project_root / "config" / "settings.yaml"
    settings_before = sha256_file(settings_path) if settings_path.is_file() else ""
    phase = "precondition"
    status = "error"
    failure_code = "shadow_build_error"
    post_fingerprint: dict[str, object] | None = None
    try:
        safe_relative_path(evidence_path, project_root)
        if run_dir.exists():
            raise FileExistsError("shadow evidence directory already exists")
        configured_active = str(getattr(getattr(cfg, "vectorstore"), "collection_name", ""))
        huiji_active = str(getattr(getattr(cfg, "huiji"), "text_collection_name", ""))
        if target in {configured_active, huiji_active}:
            raise ProvenanceValidationError(
                "active_collection_forbidden",
                "shadow_target",
            )

        phase = "handoff_validation"
        handoff = _load_candidate_handoff(
            cfg,
            args.handoff_manifest,
            args.expected_handoff_sha256,
        )
        handoff_sha = handoff.sha256
        handoff_relative = safe_relative_path(handoff.path, project_root)
        candidate_build_version = handoff.build_version
        embedding_config_fingerprint = handoff.embedding_config_fingerprint_sha256
        child_artifact_evidence = {
            **dict(handoff.child_artifact),
            "ordered_ids_sha256": handoff.child_ordered_ids_sha256,
            "semantic_corpus_sha256": handoff.child_semantic_corpus_sha256,
        }
        if target in set(handoff.forbidden_collection_names):
            raise ProvenanceValidationError(
                "active_collection_forbidden", "shadow_target"
            )

        phase = "embedding_credentials"
        _require_embedding_credentials(cfg)

        phase = "runtime_provenance"
        runtime = verify_runtime(cfg, client_factory=client_factory)
        baseline_sha = runtime.baseline_sha256
        if not runtime.allowed:
            failure_code = runtime.issues[0].code if runtime.issues else "verification_internal_error"
            status = "blocked" if runtime.status == "blocked" else "error"
            raise ProvenanceValidationError(failure_code, "runtime")

        baseline, loaded_sha = load_provenance_baseline(
            getattr(getattr(cfg, "huiji"), "provenance_baseline"),
            project_root=project_root,
        )
        baseline_sha = loaded_sha
        baseline_milvus = baseline.get("milvus")
        if not isinstance(baseline_milvus, Mapping):
            raise ProvenanceValidationError("baseline_invalid", "milvus")
        baseline_active = str(baseline_milvus.get("collection") or "")
        active_names = tuple(
            {
                configured_active,
                huiji_active,
                baseline_active,
                *handoff.forbidden_collection_names,
            }
        )
        if target in active_names:
            raise ProvenanceValidationError(
                "active_collection_forbidden",
                "shadow_target",
            )

        phase = "build"
        progress_events: list[dict[str, object]] = []
        inserted = build_huiji_shadow_collection(
            cfg,
            list(handoff.children),
            collection_name=target,
            active_collection_names=active_names,
            batch_size=args.batch_size,
            batch_delay_seconds=args.batch_delay_seconds,
            max_retries=args.max_retries,
            retry_seconds=args.retry_seconds,
            progress=lambda event: progress_events.append(dict(event)),
            client_factory=client_factory,
            embeddings_factory=embeddings_factory,
        )

        phase = "post_verify"
        post = capture_milvus_fingerprint(
            client_factory(cfg),
            target,
            database=str(getattr(getattr(cfg, "vectorstore"), "db_name", "")),
        )
        expected_rows = [
            huiji_child_to_business_row(child) for child in handoff.children
        ]
        expected_ids = [str(row["id"]) for row in expected_rows]
        if post.schema_sha256 != str(baseline_milvus.get("schema_sha256") or ""):
            raise ProvenanceValidationError("milvus_schema_mismatch", target)
        if post.row_count != len(expected_rows):
            raise ProvenanceValidationError("milvus_row_count_mismatch", target)
        if post.primary_ids_sha256 != _sha256_ids(expected_ids):
            raise ProvenanceValidationError("milvus_id_mismatch", target)
        if post.business_fields_sha256 != _sha256_rows(expected_rows):
            raise ProvenanceValidationError("milvus_content_mismatch", target)
        if sha256_file(settings_path) != settings_before:
            raise ProvenanceValidationError("collection_config_mismatch", "settings")
        post_fingerprint = post.to_json()
        status = "pass"
        failure_code = ""
    except ProvenanceValidationError as error:
        failure_code = error.code
        if status == "error" and error.code != "verification_internal_error":
            status = "blocked"
    except FileExistsError:
        failure_code = "target_collection_exists"
        status = "blocked"
    except Exception:
        failure_code = "shadow_build_error"
        status = "error"

    payload = {
        "schema_version": "huiji.shadow_build/v1",
        "status": status,
        "failure_code": failure_code,
        "phase": phase,
        "baseline_sha256": baseline_sha,
        "handoff_manifest": handoff_relative,
        "handoff_sha256": handoff_sha,
        "candidate_build_version": candidate_build_version,
        "child_artifact": child_artifact_evidence,
        "embedding_config_fingerprint_sha256": embedding_config_fingerprint,
        "database": str(getattr(getattr(cfg, "vectorstore"), "db_name", "")),
        "collection": target,
        "inserted_count": inserted,
        "post_fingerprint": post_fingerprint,
        "settings_sha256_before": settings_before,
        "settings_sha256_after": sha256_file(settings_path) if settings_path.is_file() else "",
    }
    try:
        write_hash_pinned_json(evidence_path, payload)
        relative = safe_relative_path(evidence_path, project_root)
        print(f"status={status} failure={failure_code or 'none'} evidence={relative}")
    except Exception as error:
        print(f"status=error error_type={type(error).__name__}", file=sys.stderr)
        return 3
    if status == "pass":
        return 0
    if status == "blocked":
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
