"""Offline, create-new C8d corpus-fidelity evidence diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

from src.huiji_rag.build.fidelity import build_fidelity_ledger
from src.huiji_rag.build.media_v3 import LegacyMediaReconciliation
from src.huiji_rag.build.page_sources import (
    CrawlerSemanticInputs,
    build_page_revision_join,
)
from src.huiji_rag.build.projection import (
    compose_corpus_projection,
    project_crawler_semantics,
    project_page_semantics,
    project_topic_semantics,
)


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_RUN_ID_RE = re.compile(r"task8-c-[A-Za-z0-9_-]+\Z")
_BLOCKER_PREFIX_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
_CANONICAL_NONNEGATIVE_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_AGGREGATE_BLOCKER_PREFIXES = frozenset(
    {
        "legacy_media_missing_local_bytes",
        "legacy_media_missing_resource_metadata",
        "legacy_media_ambiguous_binding",
        "legacy_media_conflicting_binding",
        "unexplained_binding_loss",
        "unexplained_parent_child_loss",
    }
)
_OUTPUT_NAMES = (
    "manifest.c8d-fidelity.v1.json",
    "receipt.c8d-fidelity.v1.json",
    "summary.c8d-fidelity.v1.json",
)
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "run_id",
    "repository_root",
    "protected_state_root",
    "output_root",
    "expected_git_head",
    "expected_git_tree",
    "diagnostic",
    "accepted_checkpoints",
    "expected_output_files",
    "sample_limit_per_blocker_prefix",
    "expected_protected_identity_count",
    "expected_protected_drift_count",
    "expected_legacy_media_category_counts",
    "inputs",
    "c8c_evidence_chain",
}
_INPUT_FIELDS = {"path", "sha256", "size_bytes"}
_INPUT_FIELDS_WITH_ROWS = _INPUT_FIELDS | {"row_count"}
_REQUIRED_INPUTS = {
    "active_parents",
    "active_children",
    "active_excluded",
    "active_child_bm25",
    "active_media_bm25",
    "candidate_parents",
    "candidate_children",
    "c8b_story_ledger",
    "active_media",
    "candidate_media_v3",
    "resource_metadata",
    "c8b_taxonomy",
    "c8c_taxonomy",
    "protected_identity_manifest",
    "crawler_pages",
    "crawler_wikitext",
    "crawler_data_pages",
    "crawler_resources_manifest",
    "c8c_product_manifest",
    "c8c_product_summary",
    "c8c_product_receipt",
}
_MEDIA_CATEGORIES = (
    "ambiguous_binding",
    "conflicting_binding",
    "missing_local_bytes",
    "missing_resource_metadata",
    "preserved_binding",
    "rekeyed_binding",
    "source_removed_with_evidence",
)
_ACTIVITY_COUNTERS = {
    "activation": 0,
    "active_pointer_changes": 0,
    "allowed_read_only_git_calls": 1,
    "downloads": 0,
    "forbidden_subprocess_calls": 0,
    "local_media_byte_reads": 0,
    "milvus_writes": 0,
    "minio_writes": 0,
    "mysql_writes": 0,
    "network": 0,
    "production_writes": 0,
    "total_subprocess_calls": 1,
    "vector_or_embedding_builds": 0,
    "writes_outside_exact_outputs": 0,
}
_SAMPLE_FIELDS = (
    "record_kind",
    "classification",
    "reason_code",
    "active_identity_sha256",
    "candidate_identity_count",
    "candidate_identities_sha256",
    "source_evidence_count",
)
_PROTECTED_RECORD_FIELDS = {"label", "path", "sha256", "size", "mtime_ns"}
_RESOURCE_METADATA_FIELDS = {
    "descriptionurl",
    "download_status",
    "height",
    "local_relpath",
    "mime",
    "name",
    "seen_at",
    "sha1",
    "site",
    "size",
    "source",
    "timestamp",
    "title",
    "url",
    "width",
}
_C8C_MANIFEST_FIELDS = {
    "diagnostic_script_sha256",
    "forbidden_action_counters",
    "head",
    "inputs",
    "interpreter",
    "outputs",
    "protected_drift_count",
    "protected_identity_count",
    "run_id",
    "schema_version",
    "status",
    "tree",
}
_C8C_MANIFEST_LABELS = (
    "d_acceptance_receipt",
    "d_green_review_receipt",
    "legacy_active_media",
    "accepted_taxonomy",
    "candidate_media_v3",
    "accepted_baseline",
    "protected_identity_manifest",
    "pages",
    "wikitext",
    "data_pages",
    "resources_manifest",
    "reviewed_file",
    "reviewed_file",
    "reviewed_file",
    "reviewed_file",
    "reviewed_file",
    "reviewed_file",
)
_C8C_REVIEWED_FILES = (
    "src/huiji_rag/build/media_v3.py",
    "src/huiji_rag/build/fidelity.py",
    "src/huiji_rag/build/orchestrator.py",
    "tests/test_huiji_media_v3_builder.py",
    "tests/test_huiji_corpus_fidelity.py",
    "docs/superpowers/specs/2026-07-29-rag-thread-c-legacy-media-decision.md",
)


def _canonical_json_bytes(
    value: object, *, trailing_newline: bool = True
) -> bytes:
    rendered = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if trailing_newline:
        rendered += "\n"
    return rendered.encode("utf-8")


def _canonical_bytes(value: object) -> bytes:
    return _canonical_json_bytes(value, trailing_newline=True)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash_text(value: str) -> str:
    return _sha256(value.encode("utf-8"))


def _source_binding_token_id(value: object) -> str:
    return "source-binding:sha256:" + _sha256(
        _canonical_json_bytes(value, trailing_newline=False)
    )


def _reject_duplicate_keys(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label} JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _json_array(raw: bytes, label: str) -> tuple[dict[str, Any], ...]:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label} JSON") from error
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of JSON objects")
    return tuple(value)


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields do not match the frozen schema")


def _contained_file(root: Path, value: object, label: str) -> Path:
    candidate = Path(str(value))
    if candidate.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    path = candidate.resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(root):
        raise ValueError(f"{label} escapes the frozen repository")
    return path


def _read_verified_identity(
    identity: Mapping[str, object], root: Path, label: str
) -> tuple[Path, bytes]:
    expected_fields = (
        _INPUT_FIELDS_WITH_ROWS if "row_count" in identity else _INPUT_FIELDS
    )
    _exact_fields(identity, expected_fields, label)
    digest = str(identity.get("sha256") or "")
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError(f"{label} SHA-256 is invalid")
    path = _contained_file(root, identity.get("path"), label)
    raw = path.read_bytes()
    if len(raw) != identity.get("size_bytes") or _sha256(raw) != digest:
        raise ValueError(f"{label} identity does not match")
    if "row_count" in identity:
        count = identity["row_count"]
        if not isinstance(count, int) or count < 0 or raw.count(b"\n") != count:
            raise ValueError(f"{label} row count does not match")
    return path, raw


def _read_jsonl(raw: bytes, label: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank line in {label}")
        rows.append(_json_object(line, f"{label} row {index}"))
    return tuple(rows)


def _bm25_records(raw: bytes, label: str) -> tuple[dict[str, Any], ...]:
    payload = _json_object(raw, label)
    _exact_fields(payload, {"records"}, label)
    records = payload["records"]
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError(f"{label} BM25 records must be an array of objects")
    return tuple(records)


def _validate_protected_state(
    raw: bytes, protected_state_root: Path, *, expected_count: int
) -> tuple[dict[str, Any], ...]:
    protected_root_value = Path(protected_state_root)
    if protected_root_value.is_symlink():
        raise ValueError("protected state root must not be a symlink")
    protected_root = protected_root_value.resolve(strict=True)
    if not protected_root.is_dir():
        raise ValueError("protected state root is not a directory")
    protected = _json_object(raw, "protected state")
    _exact_fields(protected, {"schema_version", "records"}, "protected state")
    records = protected["records"]
    if (
        protected["schema_version"] != "huiji.task8-protected-state/v1"
        or not isinstance(records, list)
        or len(records) != expected_count
    ):
        raise ValueError("protected identity contract does not match")
    labels: set[str] = set()
    paths: set[Path] = set()
    validated: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("protected identity contract does not match")
        _exact_fields(record, _PROTECTED_RECORD_FIELDS, f"protected record {index}")
        label = str(record["label"])
        digest = str(record["sha256"])
        size = record["size"]
        mtime_ns = record["mtime_ns"]
        if (
            not label
            or label in labels
            or not _SHA256_RE.fullmatch(digest)
            or type(size) is not int
            or size < 0
            or type(mtime_ns) is not int
            or mtime_ns < 0
        ):
            raise ValueError("protected identity contract does not match")
        path = _contained_file(
            protected_root, record["path"], f"protected record {index}"
        )
        if path in paths:
            raise ValueError("protected identity contract does not match")
        content = path.read_bytes()
        if (
            len(content) != size
            or _sha256(content) != digest
            or path.stat().st_mtime_ns != mtime_ns
        ):
            raise ValueError("protected state drift detected")
        labels.add(label)
        paths.add(path)
        validated.append(dict(record))
    return tuple(validated)


def load_run_config(
    path: Path,
    *,
    expected_run_config_sha256: str,
    output_root: Path,
) -> dict[str, Any]:
    """Load a hash-pinned, exact-schema run config without creating output."""
    config_path = Path(path).resolve(strict=True)
    expected_digest = str(expected_run_config_sha256).lower()
    if not _SHA256_RE.fullmatch(expected_digest):
        raise ValueError("expected run-config SHA-256 is invalid")
    raw = config_path.read_bytes()
    if _sha256(raw) != expected_digest:
        raise ValueError("run-config SHA-256 does not match")
    config = _json_object(raw, "run config")
    _exact_fields(config, _TOP_LEVEL_FIELDS, "run config")
    if config["schema_version"] != "huiji.c8d-fidelity-run-config/v1":
        raise ValueError("run-config schema is not approved")
    run_id = str(config["run_id"])
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id is invalid")
    configured_output = Path(str(config["output_root"])).resolve()
    if configured_output != Path(output_root).resolve() or configured_output.name != run_id:
        raise ValueError("output root does not match the pinned run identity")
    if tuple(config["expected_output_files"]) != _OUTPUT_NAMES:
        raise ValueError("expected output set is not canonical")
    for field in ("expected_git_head", "expected_git_tree"):
        if not _COMMIT_RE.fullmatch(str(config[field])):
            raise ValueError(f"{field} is invalid")
    limit = config["sample_limit_per_blocker_prefix"]
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("sample limit is invalid")
    repository_value = Path(str(config["repository_root"]))
    if repository_value.is_symlink():
        raise ValueError("repository root must not be a symlink")
    repository_root = repository_value.resolve(strict=True)
    if not repository_root.is_dir():
        raise ValueError("repository root is not a directory")
    protected_root_value = Path(str(config["protected_state_root"]))
    if protected_root_value.is_symlink():
        raise ValueError("protected state root must not be a symlink")
    protected_state_root = protected_root_value.resolve(strict=True)
    if not protected_state_root.is_dir():
        raise ValueError("protected state root is not a directory")

    diagnostic = config["diagnostic"]
    if not isinstance(diagnostic, dict):
        raise ValueError("diagnostic identity is invalid")
    _exact_fields(diagnostic, {"path", "sha256"}, "diagnostic")
    diagnostic_rel = Path(str(diagnostic["path"]))
    if diagnostic_rel.is_absolute() or ".." in diagnostic_rel.parts:
        raise ValueError("diagnostic path is not repository-relative")
    diagnostic_path = _contained_file(
        repository_root, repository_root / diagnostic_rel, "diagnostic"
    )
    if _sha256(diagnostic_path.read_bytes()) != diagnostic["sha256"]:
        raise ValueError("diagnostic identity does not match")

    checkpoints = config["accepted_checkpoints"]
    if not isinstance(checkpoints, dict):
        raise ValueError("accepted checkpoints are invalid")
    _exact_fields(
        checkpoints,
        {
            "task7_c8a_commit",
            "c8b_commit",
            "c8b_d_acceptance",
            "c8c_commit",
            "c8c_d_acceptance",
        },
        "accepted checkpoints",
    )
    for field in ("task7_c8a_commit", "c8b_commit", "c8c_commit"):
        if not _COMMIT_RE.fullmatch(str(checkpoints[field])):
            raise ValueError(f"{field} is invalid")
    parsed_receipts: dict[str, dict[str, Any]] = {}
    for field in ("c8b_d_acceptance", "c8c_d_acceptance"):
        identity = checkpoints[field]
        if not isinstance(identity, dict):
            raise ValueError(f"{field} identity is invalid")
        _, receipt_raw = _read_verified_identity(identity, repository_root, field)
        receipt = _json_object(receipt_raw, field)
        parsed_receipts[field] = receipt
    c8b_receipt = parsed_receipts["c8b_d_acceptance"]
    c8c_receipt = parsed_receipts["c8c_d_acceptance"]
    if not (
        c8b_receipt.get("schema_version") == "codex.thread-c-d-acceptance/v1"
        and c8b_receipt.get("phase") == "C8b"
        and c8b_receipt.get("status") == "accepted_for_commit"
        and c8b_receipt.get("expected_parent_head") == checkpoints["task7_c8a_commit"]
    ):
        raise ValueError("C8b acceptance receipt does not match the checkpoint chain")
    if not (
        c8c_receipt.get("schema_version") == "d.c8c-final-acceptance/v1"
        and c8c_receipt.get("phase") == "C8c"
        and c8c_receipt.get("decision") == "accepted_for_checkpoint_commit"
        and c8c_receipt.get("base_commit") == checkpoints["c8b_commit"]
    ):
        raise ValueError("C8c acceptance receipt does not match the checkpoint chain")

    inputs = config["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != _REQUIRED_INPUTS:
        raise ValueError("input set does not match the frozen C8d contract")
    verified: dict[str, tuple[Path, bytes]] = {}
    for label, identity in inputs.items():
        if not isinstance(identity, dict):
            raise ValueError(f"{label} identity is invalid")
        verified[label] = _read_verified_identity(identity, repository_root, label)

    for label in ("active_child_bm25", "active_media_bm25"):
        _bm25_records(verified[label][1], label.replace("_", " ") + " BM25")
    expected_protected_count = config["expected_protected_identity_count"]
    if (
        type(expected_protected_count) is not int
        or expected_protected_count < 0
        or config["expected_protected_drift_count"] != 0
    ):
        raise ValueError("protected identity contract does not match")
    _validate_protected_state(
        verified["protected_identity_manifest"][1],
        protected_state_root,
        expected_count=expected_protected_count,
    )

    _validate_c8c_chain(config, verified)
    return config


def _validate_c8c_chain(
    config: Mapping[str, Any], verified: Mapping[str, tuple[Path, bytes]]
) -> None:
    chain = config["c8c_evidence_chain"]
    if not isinstance(chain, dict):
        raise ValueError("C8c evidence chain is invalid")
    _exact_fields(
        chain,
        {"manifest_sha256", "summary_sha256", "receipt_sha256", "occurrence_ledger_sha256"},
        "C8c evidence chain",
    )
    for label, chain_field in (
        ("c8c_product_manifest", "manifest_sha256"),
        ("c8c_product_summary", "summary_sha256"),
        ("c8c_product_receipt", "receipt_sha256"),
    ):
        if verified[label][1] is None or _sha256(verified[label][1]) != chain[chain_field]:
            raise ValueError("C8c evidence-chain hash mismatch")
    manifest = _json_object(verified["c8c_product_manifest"][1], "C8c product manifest")
    summary = _json_object(verified["c8c_product_summary"][1], "C8c product summary")
    receipt = _json_object(verified["c8c_product_receipt"][1], "C8c product receipt")
    taxonomy = _json_object(verified["c8c_taxonomy"][1], "C8c taxonomy")
    _exact_fields(manifest, _C8C_MANIFEST_FIELDS, "C8c product manifest")
    if manifest.get("schema_version") != "huiji.c8c-product-parity-manifest/v1":
        raise ValueError("C8c product manifest schema is invalid")
    if summary.get("schema_version") != "huiji.c8c-product-parity-summary/v1":
        raise ValueError("C8c product summary schema is invalid")
    if receipt.get("schema_version") != "huiji.c8c-product-parity-receipt/v1":
        raise ValueError("C8c product receipt schema is invalid")
    manifest_path = verified["c8c_product_manifest"][0]
    diagnostic_path = manifest_path.with_name("diagnostic.product-parity.py")
    if diagnostic_path.is_symlink() or not diagnostic_path.resolve(strict=True).is_relative_to(
        Path(str(config["repository_root"])).resolve(strict=True)
    ):
        raise ValueError("C8c product diagnostic path is invalid")
    if manifest.get("diagnostic_script_sha256") != _sha256(diagnostic_path.read_bytes()):
        raise ValueError("C8c product diagnostic hash mismatch")
    if not (
        manifest.get("run_id") == summary.get("run_id") == receipt.get("run_id")
        and manifest.get("head") == summary.get("head") == receipt.get("head")
        and manifest.get("tree") == summary.get("tree") == receipt.get("tree")
    ):
        raise ValueError("C8c product identity mismatch")
    if (
        manifest.get("outputs", {}).get("summary.product-parity.v1.json")
        != _sha256(verified["c8c_product_summary"][1])
        or receipt.get("output_sha256", {}).get("summary.product-parity.v1.json")
        != _sha256(verified["c8c_product_summary"][1])
        or receipt.get("output_sha256", {}).get("manifest.product-parity.v1.json")
        != _sha256(verified["c8c_product_manifest"][1])
        or receipt.get("output_sha256", {}).get("diagnostic.product-parity.py")
        != manifest.get("diagnostic_script_sha256")
    ):
        raise ValueError("C8c product output cross-hash mismatch")
    rows = taxonomy.get("rows")
    counts = taxonomy.get("category_counts")
    if not isinstance(rows, list) or not isinstance(counts, dict):
        raise ValueError("C8c taxonomy rows are invalid")
    observed = Counter(str(row.get("category") or "") for row in rows if isinstance(row, dict))
    normalized_counts = {category: int(counts.get(category, 0)) for category in _MEDIA_CATEGORIES}
    if (
        set(counts) != set(_MEDIA_CATEGORIES)
        or taxonomy.get("active_occurrence_count") != len(rows)
        or normalized_counts != {category: observed.get(category, 0) for category in _MEDIA_CATEGORIES}
        or normalized_counts != config["expected_legacy_media_category_counts"]
    ):
        raise ValueError("C8c taxonomy count contract mismatch")
    if (
        chain["occurrence_ledger_sha256"]
        != summary.get("product_occurrence_ledger_sha256")
    ):
        raise ValueError("C8c occurrence ledger identity mismatch")
    accepted = summary.get("accepted_taxonomy", {})
    unexplained = sum(normalized_counts[name] for name in _MEDIA_CATEGORIES[:4])
    if accepted != {
        "active_occurrence_count": len(rows),
        "category_counts": counts,
        "unexplained_binding_loss": unexplained,
    }:
        raise ValueError("C8c accepted taxonomy parity mismatch")
    if not (
        summary.get("active_occurrence_count") == len(rows)
        and summary.get("category_counts") == counts
        and summary.get("unexplained_binding_loss") == unexplained
        and receipt.get("active_occurrence_count") == len(rows)
        and receipt.get("category_counts") == counts
        and receipt.get("unexplained_binding_loss") == unexplained
    ):
        raise ValueError("C8c product count parity mismatch")
    coverage = taxonomy.get("coverage_checks", {})
    duplicate_checks = taxonomy.get("duplicate_consumption_checks", {})
    population = taxonomy.get("population_cross_check", {})
    coverage_fields = {
        "all_categories_known",
        "category_sum_equals_active_occurrence_count",
        "each_active_occurrence_exactly_once",
        "incomplete_evidence_explicit_count",
        "potential_candidate_collision_count",
        "proven_candidate_consumption_collision_count",
    }
    duplicate_fields = {
        "bounded_collision_samples",
        "duplicate_active_occurrence_id_count",
        "potential_candidate_collision_count",
        "proven_candidate_consumption_collision_count",
    }
    population_fields = {
        "accepted_baseline",
        "accepted_fidelity_active_occurrences",
        "accepted_fidelity_unexplained_binding_loss",
        "legacy_jsonl",
        "pinned_expected_result",
    }
    occurrence_ids = [
        str(row.get("occurrence_id") or "")
        for row in rows
        if isinstance(row, dict)
    ]
    if not (
        isinstance(coverage, dict)
        and set(coverage) == coverage_fields
        and coverage["all_categories_known"] is True
        and coverage["category_sum_equals_active_occurrence_count"] is True
        and coverage["each_active_occurrence_exactly_once"] is True
        and coverage["incomplete_evidence_explicit_count"] == unexplained
        and isinstance(duplicate_checks, dict)
        and set(duplicate_checks) == duplicate_fields
        and isinstance(duplicate_checks["bounded_collision_samples"], list)
        and duplicate_checks["duplicate_active_occurrence_id_count"] == 0
        and coverage["potential_candidate_collision_count"]
        == duplicate_checks["potential_candidate_collision_count"]
        and coverage["proven_candidate_consumption_collision_count"]
        == duplicate_checks["proven_candidate_consumption_collision_count"]
        == 0
        and isinstance(population, dict)
        and set(population) == population_fields
        and set(population.values()) == {len(rows)}
        and len(occurrence_ids) == len(rows)
        and "" not in occurrence_ids
        and len(set(occurrence_ids)) == len(occurrence_ids)
    ):
        raise ValueError("C8c occurrence population cross-check mismatch")
    manifest_inputs = manifest.get("inputs")
    if (
        not isinstance(manifest_inputs, list)
        or len(manifest_inputs) != len(_C8C_MANIFEST_LABELS)
        or any(not isinstance(identity, dict) for identity in manifest_inputs)
        or any(
            set(identity) != {"identity", "label", "row_count", "sha256", "size"}
            for identity in manifest_inputs
        )
        or tuple(str(identity["label"]) for identity in manifest_inputs)
        != _C8C_MANIFEST_LABELS
    ):
        raise ValueError("C8c product input manifest is invalid")
    semantic_row_counts = {
        "accepted_taxonomy": len(rows),
        "protected_identity_manifest": config["expected_protected_identity_count"],
    }
    repository_root = Path(str(config["repository_root"])).resolve(strict=True)
    witnessed_paths: list[str] = []
    for index, identity in enumerate(manifest_inputs):
        relative = Path(str(identity["identity"]))
        digest = str(identity["sha256"])
        size = identity["size"]
        row_count = identity["row_count"]
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not _SHA256_RE.fullmatch(digest)
            or type(size) is not int
            or size < 0
            or (row_count is not None and (type(row_count) is not int or row_count < 0))
        ):
            raise ValueError("C8c product input identity is invalid")
        semantic_row_count = semantic_row_counts.get(identity["label"])
        witness_path = _contained_file(
            repository_root,
            repository_root / relative,
            f"C8c product input {index}",
        )
        witness_raw = witness_path.read_bytes()
        if (
            len(witness_raw) != size
            or _sha256(witness_raw) != digest
            or (
                row_count is not None
                and (
                    row_count != semantic_row_count
                    if semantic_row_count is not None
                    else witness_raw.count(b"\n") != row_count
                )
            )
        ):
            raise ValueError("C8c product input identity cross-check mismatch")
        witnessed_paths.append(relative.as_posix())
    if len(witnessed_paths) != len(set(witnessed_paths)):
        raise ValueError("C8c product input identity is duplicated")

    c8d_mapping = {
        2: "active_media",
        3: "c8c_taxonomy",
        4: "candidate_media_v3",
        6: "protected_identity_manifest",
        7: "crawler_pages",
        8: "crawler_wikitext",
        9: "crawler_data_pages",
        10: "crawler_resources_manifest",
    }
    for index, c8d_label in c8d_mapping.items():
        path, _raw = verified[c8d_label]
        product_label = _C8C_MANIFEST_LABELS[index]
        expected = {
            "identity": path.relative_to(repository_root).as_posix(),
            "label": product_label,
            "row_count": (
                semantic_row_counts[product_label]
                if product_label in semantic_row_counts
                else config["inputs"][c8d_label].get("row_count")
            ),
            "sha256": config["inputs"][c8d_label]["sha256"],
            "size": config["inputs"][c8d_label]["size_bytes"],
        }
        if manifest_inputs[index] != expected:
            raise ValueError("C8c product input identity cross-check mismatch")
    baseline = _json_object(
        (repository_root / witnessed_paths[5]).read_bytes(), "accepted C8c baseline"
    )
    if not (
        witnessed_paths[5]
        == "eval/huiji_corpus_fidelity/20260720T073917Z/"
        "corpus-preservation-baseline.v2.json"
        and baseline.get("schema_version") == "huiji.corpus-preservation-baseline/v2"
        and baseline.get("status") == "pass"
        and tuple(witnessed_paths[11:]) == _C8C_REVIEWED_FILES
    ):
        raise ValueError("C8c product witness identity mapping is invalid")


def read_git_identity(repository_root: Path) -> tuple[str, str]:
    """Perform the diagnostic's sole subprocess call."""
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD", "HEAD^{tree}"),
        cwd=Path(repository_root),
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    values = completed.stdout.splitlines()
    if len(values) != 2 or not all(_COMMIT_RE.fullmatch(value) for value in values):
        raise RuntimeError("git returned an invalid HEAD/tree identity")
    return values[0], values[1]


def _strict_c8c_adapter(
    taxonomy: Mapping[str, Any],
    active_media: Sequence[Mapping[str, Any]],
    candidate_media: Sequence[Mapping[str, Any]],
    resource_metadata: Sequence[Mapping[str, Any]],
) -> LegacyMediaReconciliation:
    """Adapt frozen C8c decisions verbatim after exhaustive identity checks."""
    rows = taxonomy["rows"]
    active_by_hash = {
        _sha256(_canonical_json_bytes(row, trailing_newline=False)): dict(row)
        for row in active_media
    }
    if len(active_by_hash) != len(active_media):
        raise ValueError("duplicate active media row identity")
    candidate_by_id = {str(row.get("binding_id") or ""): dict(row) for row in candidate_media}
    if "" in candidate_by_id or len(candidate_by_id) != len(candidate_media):
        raise ValueError("duplicate candidate media binding identity")
    resource_match_cardinality: dict[tuple[Any, Any, Any], int] = {}
    for resource in resource_metadata:
        if set(resource) != _RESOURCE_METADATA_FIELDS:
            raise ValueError("resource metadata schema is invalid")
        sha1 = str(resource.get("sha1") or "")
        if not sha1:
            raise ValueError("resource metadata identity is missing")
        resource_key = (resource.get("sha1"), resource.get("name"), resource.get("size"))
        resource_match_cardinality[resource_key] = (
            resource_match_cardinality.get(resource_key, 0) + 1
        )
    for candidate in candidate_media:
        resource_key = (
            candidate.get("source_sha1"),
            candidate.get("filename"),
            candidate.get("size"),
        )
        if resource_match_cardinality.get(resource_key, 0) != 1:
            raise ValueError("candidate media resource metadata does not match")
    occurrence_ids: set[str] = set()
    coverage = taxonomy.get("coverage_checks")
    duplicate_checks = taxonomy.get("duplicate_consumption_checks")
    if not (
        isinstance(coverage, dict)
        and isinstance(duplicate_checks, dict)
        and coverage.get("proven_candidate_consumption_collision_count")
        == duplicate_checks.get("proven_candidate_consumption_collision_count")
        == 0
    ):
        raise ValueError("C8c proven candidate consumption collision")
    adapted: list[dict[str, Any]] = []
    for decision in rows:
        if not isinstance(decision, dict):
            raise ValueError("C8c occurrence decision is invalid")
        occurrence_id = str(decision.get("occurrence_id") or "")
        if not occurrence_id or occurrence_id in occurrence_ids:
            raise ValueError("C8c occurrence identity is missing or duplicated")
        occurrence_ids.add(occurrence_id)
        active = active_by_hash.get(str(decision.get("legacy_row_sha256") or ""))
        if active is None:
            raise ValueError("C8c occurrence has no exact active row")
        for decision_field, active_field in (
            ("legacy_media_id", "media_id"),
            ("legacy_sha1", "sha1"),
            ("legacy_parent_id", "parent_id"),
            ("legacy_child_id", "child_id"),
        ):
            if decision.get(decision_field) != active.get(active_field):
                raise ValueError("C8c active occurrence identity mismatch")
        candidate_ids = decision.get("candidate_binding_ids")
        potential_ids = decision.get("potential_candidate_ids")
        if (
            not isinstance(candidate_ids, list)
            or len(candidate_ids) != len(set(candidate_ids))
            or candidate_ids != potential_ids
            or decision.get("exact_candidate_count") != len(candidate_ids)
        ):
            raise ValueError("C8c candidate cardinality mismatch")
        candidates = []
        for candidate_id in candidate_ids:
            candidate = candidate_by_id.get(str(candidate_id))
            if candidate is None:
                raise ValueError("C8c candidate binding identity is absent")
            candidates.append(candidate)
        source_token_ids = sorted(
            {_source_binding_token_id(row.get("source_binding_token")) for row in candidates}
        )
        if source_token_ids != sorted(
            decision.get("candidate_source_binding_token_ids") or []
        ):
            raise ValueError("C8c candidate source identity mismatch")
        candidate_refs = [
            {
                "source_binding_token_sha256": _hash_text(str(row["source_binding_token"])),
                "parent_id_sha256": _hash_text(str(row.get("parent_id") or "")),
                "child_id_sha256": _hash_text(str(row.get("child_id") or "")),
            }
            for row in candidates
        ]
        classification = str(decision.get("category") or "")
        reason_code = str(decision.get("reason_code") or "")
        if classification not in _MEDIA_CATEGORIES or not reason_code:
            raise ValueError("C8c decision is not an approved explicit classification")
        adapted.append(
            {
                "occurrence_id": occurrence_id,
                "active_row_sha256": decision["legacy_row_sha256"],
                "active_media_id": active["media_id"],
                "active_sha1": active["sha1"],
                "active_parent_id": active["parent_id"],
                "active_child_id": active["child_id"],
                "candidate_child_id": (
                    str(candidates[0].get("child_id") or "") if len(candidates) == 1 else ""
                ),
                "resource_id": (
                    str(candidates[0].get("resource_id") or "") if len(candidates) == 1 else ""
                ),
                "candidate_binding_ids": list(candidate_ids),
                "classification": classification,
                "reason_code": reason_code,
                "candidate_source_refs": candidate_refs,
                "local_evidence": {},
            }
        )
    counts = Counter(row["classification"] for row in adapted)
    expected_counts = {
        category: int(taxonomy.get("category_counts", {}).get(category, 0))
        for category in _MEDIA_CATEGORIES
    }
    observed_counts = {category: counts.get(category, 0) for category in _MEDIA_CATEGORIES}
    if expected_counts != observed_counts:
        raise ValueError("C8c adapted category counts do not match accepted taxonomy")
    return LegacyMediaReconciliation(
        occurrence_rows=tuple(adapted),
        category_counts=dict(counts),
        active_occurrence_count=len(adapted),
        unexplained_binding_loss=sum(counts[name] for name in _MEDIA_CATEGORIES[:4]),
    )


def load_validated_evidence(config: dict[str, object]) -> SimpleNamespace:
    """Load only pinned local evidence and project through checked-out public stages."""
    identities = config["inputs"]

    def rows(label: str) -> tuple[dict[str, Any], ...]:
        return _read_jsonl(Path(identities[label]["path"]).read_bytes(), label)

    repository_root = Path(str(config["repository_root"])).resolve(strict=True)
    crawler_root = Path(identities["crawler_pages"]["path"]).resolve().parent
    expected_crawler = {
        "pages.jsonl": Path(identities["crawler_pages"]["path"]).resolve(),
        "wikitext.jsonl": Path(identities["crawler_wikitext"]["path"]).resolve(),
        "data_pages.jsonl": Path(identities["crawler_data_pages"]["path"]).resolve(),
        "resources_manifest.jsonl": Path(identities["crawler_resources_manifest"]["path"]).resolve(),
    }
    if any(path.parent != crawler_root or path.name != name for name, path in expected_crawler.items()):
        raise ValueError("crawler source identities do not form one frozen source root")
    semantic_inputs = CrawlerSemanticInputs.from_root(crawler_root)
    page_stream = semantic_inputs.pages()
    revision_stream = semantic_inputs.revisions()
    page_join = build_page_revision_join(page_stream, revision_stream)
    data_projection = project_crawler_semantics(semantic_inputs.iter_data_page_mappings())
    page_projection = project_page_semantics(page_join, semantic_inputs.revisions())
    topic_projection = project_topic_semantics(data_projection, page_projection)
    projection = compose_corpus_projection(
        data_projection,
        page_projection,
        topic_projection,
    )

    active_media = rows("active_media")
    candidate_media = rows("candidate_media_v3")
    resource_metadata = rows("resource_metadata")
    taxonomy = _json_object(Path(identities["c8c_taxonomy"]["path"]).read_bytes(), "C8c taxonomy")
    legacy_media = _strict_c8c_adapter(
        taxonomy,
        active_media,
        candidate_media,
        resource_metadata,
    )
    protected = _json_object(
        Path(identities["protected_identity_manifest"]["path"]).read_bytes(),
        "protected state",
    )
    if not crawler_root.is_relative_to(repository_root):
        raise ValueError("crawler root escapes the frozen repository")
    candidate_parents = rows("candidate_parents")
    candidate_children = rows("candidate_children")
    projected_parent_rows = tuple(
        sorted(
            (
                _json_object(
                    _canonical_json_bytes(
                        parent.to_json(), trailing_newline=False
                    ),
                    "projected parent",
                )
                for parent in projection.parents
            ),
            key=lambda row: str(row["parent_id"]),
        )
    )
    projected_child_rows = tuple(
        sorted(
            (
                _json_object(
                    _canonical_json_bytes(
                        child.to_json(), trailing_newline=False
                    ),
                    "projected child",
                )
                for child in projection.children
            ),
            key=lambda row: str(row["child_id"]),
        )
    )
    if projected_parent_rows != candidate_parents or projected_child_rows != candidate_children:
        raise ValueError("checked-out corpus projection does not match pinned candidate rows")
    story_ledger_rows = rows("c8b_story_ledger")
    c8b_taxonomy = _json_object(
        Path(identities["c8b_taxonomy"]["path"]).read_bytes(), "C8b taxonomy"
    )
    if (
        c8b_taxonomy.get("schema_version")
        != "huiji.task8-c8b-story-legacy-taxonomy/v1"
        or c8b_taxonomy.get("status") != "completed_pending_review"
        or not isinstance(c8b_taxonomy.get("story_record_link_evidence"), dict)
    ):
        raise ValueError("C8b taxonomy identity mismatch")
    ledger_ids = [str(row.get("ledger_id") or "") for row in story_ledger_rows]
    if any(not value for value in ledger_ids) or len(set(ledger_ids)) != len(ledger_ids):
        raise ValueError("C8b ledger identities are missing or duplicated")
    return SimpleNamespace(
        data_projection=data_projection,
        page_projection=page_projection,
        topic_projection=topic_projection,
        projection=projection,
        active_parent_rows=rows("active_parents"),
        active_child_rows=rows("active_children"),
        active_excluded_rows=rows("active_excluded"),
        active_child_bm25_records=_bm25_records(
            Path(identities["active_child_bm25"]["path"]).read_bytes(),
            "active child BM25",
        ),
        active_media_bm25_records=_bm25_records(
            Path(identities["active_media_bm25"]["path"]).read_bytes(),
            "active media BM25",
        ),
        candidate_parent_rows=candidate_parents,
        candidate_child_rows=candidate_children,
        story_ledger_rows=story_ledger_rows,
        legacy_media=legacy_media,
        protected_identity_count=int(config["expected_protected_identity_count"]),
    )


def bounded_structured_samples(
    rows: Iterable[Mapping[str, object]], *, limit_per_prefix: int
) -> dict[str, list[dict[str, object]]]:
    """Return deterministic bounded samples containing hashes and counts only."""
    if type(limit_per_prefix) is not int or not 1 <= limit_per_prefix <= 5:
        raise ValueError("sample limit must be an integer from 1 through 5")
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        prefix = str(row.get("blocker_prefix") or "")
        if not prefix:
            continue
        candidates = tuple(str(value) for value in (row.get("candidate_identities") or ()))
        candidate_digest = _hash_text("\0".join(sorted(candidates)))
        sample = {
            "record_kind": str(row.get("record_kind") or ""),
            "classification": str(row.get("classification") or ""),
            "reason_code": str(row.get("reason_code") or ""),
            "active_identity_sha256": _hash_text(str(row.get("active_identity") or "")),
            "candidate_identity_count": len(candidates),
            "candidate_identities_sha256": candidate_digest,
            "source_evidence_count": len(tuple(row.get("source_evidence") or ())),
        }
        grouped.setdefault(prefix, []).append(sample)
    result: dict[str, list[dict[str, object]]] = {}
    for prefix in sorted(grouped):
        ordered = sorted(
            grouped[prefix],
            key=lambda row: tuple(str(row[field]) for field in sorted(_SAMPLE_FIELDS)),
        )
        result[prefix] = ordered[:limit_per_prefix]
    return result


def _blocker_prefix_counts(blockers: Iterable[object]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for value in blockers:
        prefix, separator, raw_count = str(value).partition(":")
        if _BLOCKER_PREFIX_RE.fullmatch(prefix) is None:
            raise ValueError("fidelity blocker prefix is invalid")
        count = 1
        if prefix in _AGGREGATE_BLOCKER_PREFIXES:
            if (
                not separator
                or _CANONICAL_NONNEGATIVE_DECIMAL_RE.fullmatch(raw_count) is None
            ):
                raise ValueError("fidelity aggregate blocker count is invalid")
            count = int(raw_count)
        counts[prefix] += count
    return counts


def _source_evidence_digest(evidence: Sequence[Mapping[str, object]]) -> str:
    identities = sorted(
        f"{row.get('source_title', '')}\0{row.get('source_content_sha256', '')}"
        for row in evidence
    )
    return _hash_text("\0".join(identities))


def _is_story_ledger_row(row: Mapping[str, object]) -> bool:
    evidence = row.get("source_evidence") or ()
    return any(
        isinstance(source, Mapping)
        and str(source.get("source_title") or "").startswith("Data:Story/")
        for source in evidence
    )


def _partition_summary(fidelity: object) -> tuple[dict[str, object], list[dict[str, object]]]:
    ledger = tuple(dict(row) for row in fidelity.ledger_rows)
    story_rows = [row for row in ledger if _is_story_ledger_row(row)]
    non_story_rows = [
        row
        for row in ledger
        if row.get("record_kind") in {"parent", "child"}
        and not _is_story_ledger_row(row)
    ]
    story_child = next((row for row in story_rows if row.get("record_kind") == "child"), None)
    story_evidence: dict[str, object] = {}
    if story_child is not None:
        evidence = tuple(story_child.get("source_evidence") or ())
        story_evidence = {
            "source_identity_sha256": _source_evidence_digest(evidence),
            "legacy_child_identity_sha256": _hash_text(str(story_child["active_identity"])),
            "candidate_child_identity_sha256": sorted(
                _hash_text(str(value)) for value in story_child.get("candidate_identities", ())
            ),
        }
    non_story = [
        {
            "record_kind": str(row.get("record_kind") or ""),
            "classification": str(row.get("classification") or ""),
            "reason_code": str(row.get("reason_code") or ""),
            "active_identity_sha256": _hash_text(str(row.get("active_identity") or "")),
            "candidate_identities_sha256": _hash_text(
                "\0".join(sorted(str(value) for value in row.get("candidate_identities", ())))
            ),
            "source_evidence_sha256": _source_evidence_digest(tuple(row.get("source_evidence") or ())),
        }
        for row in non_story_rows
    ]
    non_story.sort(key=lambda row: tuple(str(row[key]) for key in sorted(row)))
    return story_evidence, non_story


def _summary(config: Mapping[str, Any], fidelity: object) -> dict[str, object]:
    counts = _blocker_prefix_counts(fidelity.blockers)
    non_story_ledger_prefixes = Counter(
        f"blocked_ambiguous_{row.get('record_kind')}"
        for row in fidelity.ledger_rows
        if row.get("record_kind") in {"parent", "child"}
        and row.get("classification") == "blocked_ambiguous"
        and not _is_story_ledger_row(row)
    )
    story_prefixes = (
        "blocked_ambiguous_child",
        "blocked_ambiguous_parent",
        "unexplained_child_missing",
        "unexplained_parent_missing",
    )
    story_counts = {
        prefix: counts[prefix] - non_story_ledger_prefixes[prefix]
        for prefix in story_prefixes
        if counts[prefix] - non_story_ledger_prefixes[prefix] > 0
    }
    other = Counter(counts)
    for prefix, count in story_counts.items():
        other[prefix] -= count
        if other[prefix] == 0:
            del other[prefix]
    for category in _MEDIA_CATEGORIES[:4]:
        other.pop(f"legacy_media_{category}", None)
    story_evidence, non_story_evidence = _partition_summary(fidelity)
    sample_rows = [
        {
            **row,
            "blocker_prefix": (
                f"blocked_ambiguous_{row.get('record_kind')}"
                if row.get("classification") == "blocked_ambiguous"
                else str(row.get("reason_code") or "")
            ),
        }
        for row in fidelity.ledger_rows
    ]
    return {
        "schema_version": "huiji.c8d-fidelity-summary/v1",
        "run_id": config["run_id"],
        "fidelity_returned_normally": True,
        "fidelity_passed": bool(fidelity.passed),
        "story_blocker_prefix_counts": dict(sorted(story_counts.items())),
        "non_story_media_blocker_counts": {
            category: int(config["expected_legacy_media_category_counts"][category])
            for category in _MEDIA_CATEGORIES[:4]
        },
        "other_blocker_prefix_counts": dict(sorted(other.items())),
        "story_partition_evidence": story_evidence,
        "non_story_partition_evidence": non_story_evidence,
        "structured_samples": bounded_structured_samples(
            sample_rows,
            limit_per_prefix=int(config["sample_limit_per_blocker_prefix"]),
        ),
        "protected_identity_count": int(config["expected_protected_identity_count"]),
        "protected_drift_count": 0,
    }


def _sanitized_identity(
    identity: Mapping[str, object], repository_root: Path
) -> dict[str, object]:
    path = Path(str(identity["path"])).resolve(strict=True)
    return {
        "identity": path.relative_to(repository_root).as_posix(),
        "sha256": identity["sha256"],
        "size": identity["size_bytes"],
        **({"row_count": identity["row_count"]} if "row_count" in identity else {}),
    }


def _write_create_new(path: Path, value: object) -> str:
    raw = _canonical_bytes(value)
    with path.open("xb") as handle:
        handle.write(raw)
    return _sha256(raw)


def run_diagnostic(
    config_path: Path,
    *,
    expected_run_config_sha256: str,
    output_root: Path,
) -> dict[str, object]:
    """Run the fully offline diagnostic and return its sanitized summary."""
    config = load_run_config(
        config_path,
        expected_run_config_sha256=expected_run_config_sha256,
        output_root=output_root,
    )
    output = Path(output_root).resolve()
    if output.exists():
        raise FileExistsError("C8d output root violates create-new absent-only semantics")
    repository_root = Path(str(config["repository_root"])).resolve(strict=True)
    protected_state_root = Path(str(config["protected_state_root"])).resolve(
        strict=True
    )
    head, tree = read_git_identity(repository_root)
    if head != config["expected_git_head"] or tree != config["expected_git_tree"]:
        raise RuntimeError("checked-out HEAD/tree does not match the frozen run config")

    evidence = load_validated_evidence(config)
    projection = getattr(evidence, "projection", None)
    if projection is None:
        projection = compose_corpus_projection(
            evidence.data_projection,
            evidence.page_projection,
            evidence.topic_projection,
        )
    fidelity = build_fidelity_ledger(
        active_parent_rows=evidence.active_parent_rows,
        active_child_rows=evidence.active_child_rows,
        active_excluded_rows=evidence.active_excluded_rows,
        projection=projection,
        legacy_media=evidence.legacy_media,
        active_child_bm25_records=evidence.active_child_bm25_records,
        active_media_bm25_records=evidence.active_media_bm25_records,
    )
    try:
        protected_identity = config["inputs"]["protected_identity_manifest"]
        _, protected_raw = _read_verified_identity(
            protected_identity,
            repository_root,
            "protected identity manifest",
        )
        _validate_protected_state(
            protected_raw,
            protected_state_root,
            expected_count=int(config["expected_protected_identity_count"]),
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("protected state drift detected after fidelity work") from error
    summary = _summary(config, fidelity)
    summary_raw = _canonical_bytes(summary)
    summary_sha256 = _sha256(summary_raw)
    config_raw = Path(config_path).resolve(strict=True).read_bytes()
    checkpoints = dict(config["accepted_checkpoints"])
    sanitized_checkpoints: dict[str, object] = {
        "task7_c8a_commit": checkpoints["task7_c8a_commit"],
        "c8b_commit": checkpoints["c8b_commit"],
        "c8b_d_acceptance": _sanitized_identity(checkpoints["c8b_d_acceptance"], repository_root),
        "c8c_commit": checkpoints["c8c_commit"],
        "c8c_d_acceptance": _sanitized_identity(checkpoints["c8c_d_acceptance"], repository_root),
    }
    manifest = {
        "schema_version": "huiji.c8d-fidelity-manifest/v1",
        "run_id": config["run_id"],
        "run_config": {
            "path": Path(config_path).name,
            "sha256": _sha256(config_raw),
            "size_bytes": len(config_raw),
        },
        "diagnostic": dict(config["diagnostic"]),
        "git_identity": {"head": head, "tree": tree},
        "accepted_checkpoints": sanitized_checkpoints,
        "inputs": {
            label: _sanitized_identity(identity, repository_root)
            for label, identity in sorted(config["inputs"].items())
        },
        "c8c_evidence_chain": dict(config["c8c_evidence_chain"]),
        "output_sha256": {_OUTPUT_NAMES[2]: summary_sha256},
    }
    manifest_raw = _canonical_bytes(manifest)
    manifest_sha256 = _sha256(manifest_raw)
    receipt = {
        "schema_version": "huiji.c8d-fidelity-receipt/v1",
        "run_id": config["run_id"],
        "output_sha256": {
            _OUTPUT_NAMES[0]: manifest_sha256,
            _OUTPUT_NAMES[2]: summary_sha256,
        },
        "output_confinement": {
            "create_new": True,
            "output_root": output.name,
            "unexpected_output_count": 0,
            "writes_outside_exact_outputs": 0,
        },
        "protected_state": {
            "identity_count_pre": int(config["expected_protected_identity_count"]),
            "identity_count_post": int(config["expected_protected_identity_count"]),
            "drift_count": 0,
        },
        "activity_counters": dict(_ACTIVITY_COUNTERS),
    }
    output.mkdir(parents=False, exist_ok=True)
    _write_create_new(output / _OUTPUT_NAMES[2], summary)
    _write_create_new(output / _OUTPUT_NAMES[0], manifest)
    _write_create_new(output / _OUTPUT_NAMES[1], receipt)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-config", type=Path, required=True)
    parser.add_argument("--expected-run-config-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if not _SHA256_RE.fullmatch(args.expected_run_config_sha256):
        parser.error("--expected-run-config-sha256 must be 64 lowercase hex characters")
    config_raw = args.run_config.resolve(strict=True).read_bytes()
    if _sha256(config_raw) != args.expected_run_config_sha256:
        raise ValueError("run-config SHA-256 does not match")
    run_diagnostic(
        args.run_config,
        expected_run_config_sha256=args.expected_run_config_sha256,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
