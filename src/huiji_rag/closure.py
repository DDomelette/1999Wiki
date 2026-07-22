"""Read-only Candidate F cross-system closure and immutable receipt handling."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen


CLOSURE_SCHEMA = "huiji.candidate-f-cross-system-closure/v1"
ACTIVATION_ID = "candidate-f-generation-1-20260722d"
BUILD_VERSION = "crawler-v3-20260721t051246z"
COLLECTION_NAME = "text_child_bge_m3_shadow_crawler_v3_20260721t051246z"
ARTIFACT_SCHEMA = "evb.media-asset/v3"
GENERATION = 1

ACTIVATION_RECEIPT_SHA256 = "78310c7f0009c6df88413f5a888940d4aa404073b81ef001ebc9d1a6eb3d7f58"
WIKI_HANDOFF_SHA256 = "884e6ae0ef10911564a84ec3c3ec5b3f57939fc47475ab68599d04ca14d4e90a"
ACTIVE_POINTER_SHA256 = "87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e"
SETTINGS_SHA256 = "d2b25e7dfbb41a0b1c13e7d3964dbcf286380c0bdf2cc5ee920c1e0d1be5d473"
FORMAL_IMPORT_RECEIPT_SHA256 = "76909a9cbb85ce81e4e4a746a780b8836423ee9b6e921c503249cade1a87a23f"
INSTALLED_SNAPSHOT_SHA256 = "7529288166e2304d2e31cad7777a5fb8173e830ece13d340fae0650d08f019a1"
RAG_ROLLBACK_SHA256 = "07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b"
WIKI_ROLLBACK_SHA256 = "e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6"
RAG_PROPOSAL_SHA256 = "fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8"

EXPECTED_COUNTS = {
    "wiki_pages": 7456,
    "wiki_categories": 4,
    "wiki_media_links": 17527,
    "wiki_media_resources": 19132,
    "wiki_media_bindings": 19400,
}

EXPECTED_P0_IDS = (
    "CLOSE-AUTH-P0-01",
    "CLOSE-AUTH-P0-02",
    "CLOSE-AUTH-P0-03",
    "CLOSE-AUTH-P0-04",
    "CLOSE-RUNTIME-P0-01",
    "CLOSE-RUNTIME-P0-02",
    "CLOSE-RUNTIME-P0-03",
    "CLOSE-RUNTIME-P0-04",
    "CLOSE-RUNTIME-P0-05",
    "CLOSE-WIKI-P0-01",
    "CLOSE-WIKI-P0-02",
    "CLOSE-WIKI-P0-03",
    "CLOSE-WIKI-P0-04",
    "CLOSE-ROLLBACK-P0-01",
    "CLOSE-ROLLBACK-P0-02",
    "CLOSE-MUTATION-P0-01",
    "CLOSE-MUTATION-P0-02",
    "CLOSE-MUTATION-P0-03",
    "CLOSE-EVIDENCE-P0-01",
    "CLOSE-EVIDENCE-P0-02",
    "CLOSE-EVIDENCE-P0-03",
    "CLOSE-EVIDENCE-P0-04",
    "CLOSE-EVIDENCE-P0-05",
)

ACTIVATION_RECEIPT_RELATIVE = (
    "data/processed/huiji/activation/transactions/"
    f"{ACTIVATION_ID}/activation_receipt.v1.json"
)
WIKI_HANDOFF_RELATIVE = (
    "data/processed/huiji/activation/transactions/"
    f"{ACTIVATION_ID}/wiki_import_handoff.v1.json"
)
ACTIVE_POINTER_RELATIVE = "data/processed/huiji/active_build.v1.json"
SETTINGS_RELATIVE = "config/settings.yaml"
RAG_ROLLBACK_RELATIVE = (
    "data/processed/huiji/activation/proposals/"
    "candidate-f-review-20260722c/rollback_tuple.v1.json"
)
RAG_PROPOSAL_RELATIVE = (
    "data/processed/huiji/activation/proposals/"
    "candidate-f-review-20260722c/activation_proposal.v1.json"
)
WIKI_ROLLBACK_RELATIVE = (
    "eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/"
    "wiki_pre_import_rollback_receipt.v1.json"
)
DEFAULT_FORMAL_RECEIPT_RELATIVE = (
    "eval/huiji_wiki_v3_import/"
    f"{ACTIVATION_ID}/formal_import_receipt.v1.json"
)
DEFAULT_OUTPUT_RELATIVE = (
    "eval/huiji_candidate_closure/"
    f"{ACTIVATION_ID}/candidate_f_closure_receipt.v1.json"
)

_SHA256_CHARS = frozenset("0123456789abcdef")


class ClosureConflict(RuntimeError):
    """Raised when output ownership or current state is ambiguous."""


@dataclass(frozen=True)
class ClosureInspection:
    activation_receipt: Mapping[str, Any]
    handoff: Mapping[str, Any]
    formal_receipt: Mapping[str, Any]
    formal_evidence: Mapping[str, Mapping[str, Any]]
    active_pointer: Mapping[str, Any]
    runtime_identity: Mapping[str, Any]
    rag_health: Mapping[str, Any]
    wiki_health: Mapping[str, Any]
    database_state: Mapping[str, Any]
    rollback: Mapping[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    root = Path(project_root).resolve(strict=True)
    raw = Path(value)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path escapes project root: {value}")
    return resolved


def _relative(path: Path, root: Path) -> str:
    return str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")


def _valid_sha256(value: object) -> str:
    normalized = str(value or "").lower()
    if len(normalized) != 64 or any(char not in _SHA256_CHARS for char in normalized):
        raise ValueError("invalid SHA-256 value")
    return normalized


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON evidence: {Path(path).name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {Path(path).name}")
    return value


def validate_hash_sidecar(target: Path, *, require_lf: bool = False) -> str:
    target = Path(target)
    sidecar = target.with_name(f"{target.name}.sha256")
    if not target.is_file() or not sidecar.is_file():
        raise ValueError(f"receipt or sidecar missing: {target.name}")
    digest = sha256_file(target)
    expected_lf = f"{digest}  {target.name}\n".encode("ascii")
    raw = sidecar.read_bytes()
    if require_lf:
        matched = raw == expected_lf
    else:
        matched = raw in {expected_lf, expected_lf.replace(b"\n", b"\r\n")}
    if not matched:
        raise ValueError(f"sidecar mismatch: {target.name}")
    return digest


def validate_pinned_json(
    project_root: Path,
    path: str | Path,
    *,
    expected_sha256: str,
    expected_schema: str | None = None,
    canonical: bool = True,
    allow_crlf: bool = False,
) -> dict[str, Any]:
    target = resolve_project_path(project_root, path)
    expected = _valid_sha256(expected_sha256)
    if not target.is_file() or sha256_file(target) != expected:
        raise ValueError(f"hash-pinned evidence mismatch: {_relative(target, project_root)}")
    payload = _load_json(target)
    if canonical:
        expected_bytes = canonical_json_bytes(payload)
        accepted = {expected_bytes}
        if allow_crlf:
            accepted.add(expected_bytes.replace(b"\n", b"\r\n"))
        if target.read_bytes() not in accepted:
            raise ValueError(f"evidence is not canonical JSON: {_relative(target, project_root)}")
    if expected_schema is not None and payload.get("schema_version") != expected_schema:
        raise ValueError(f"evidence schema mismatch: {_relative(target, project_root)}")
    return payload


def _path_from_ref(project_root: Path, reference: Mapping[str, Any]) -> Path:
    relative = reference.get("relative_path") or reference.get("path")
    if not isinstance(relative, str) or not relative:
        raise ValueError("hash-pinned reference path is missing")
    return resolve_project_path(project_root, relative)


def _verify_reference(project_root: Path, reference: Mapping[str, Any]) -> Path:
    path = _path_from_ref(project_root, reference)
    expected = _valid_sha256(reference.get("sha256"))
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"hash-pinned reference mismatch: {_relative(path, project_root)}")
    expected_size = reference.get("size")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        raise ValueError(f"hash-pinned reference size mismatch: {_relative(path, project_root)}")
    return path


def _file_ref(path: Path, project_root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, project_root),
        "sha256": sha256_file(path),
        "size": Path(path).stat().st_size,
    }


def validate_formal_import_receipt(
    project_root: Path,
    formal_receipt_path: Path,
    *,
    expected_sha256: str,
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    path = resolve_project_path(project_root, formal_receipt_path)
    payload = validate_pinned_json(
        project_root,
        path,
        expected_sha256=expected_sha256,
        expected_schema="huiji.wiki-v3-formal-import-receipt/v1",
        allow_crlf=True,
    )
    validate_hash_sidecar(path)
    if (
        payload.get("status") != "passed"
        or payload.get("activation_id") != ACTIVATION_ID
        or payload.get("build_version") != BUILD_VERSION
        or payload.get("active_collection") != COLLECTION_NAME
        or payload.get("installed_snapshot_sha256") != INSTALLED_SNAPSHOT_SHA256
    ):
        raise ValueError("formal import receipt authority mismatch")

    evidence = payload.get("evidence")
    required = {
        "api_smoke",
        "import_commit",
        "p0_matrix",
        "playwright",
        "protected_compare",
        "rag_smoke",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != required:
        raise ValueError("formal import receipt evidence set mismatch")
    loaded: dict[str, Mapping[str, Any]] = {}
    for name in sorted(required):
        reference = evidence[name]
        if not isinstance(reference, Mapping):
            raise ValueError(f"formal import evidence reference is invalid: {name}")
        evidence_path = _verify_reference(project_root, reference)
        if name != "playwright":
            loaded[name] = _load_json(evidence_path)
        else:
            loaded[name] = {"reference_only": True}

    commit = loaded["import_commit"]
    matrix = loaded["p0_matrix"]
    protected = loaded["protected_compare"]
    if (
        commit.get("schema_version") != "huiji.wiki-v3-formal-import-commit/v1"
        or commit.get("status") != "committed"
        or commit.get("snapshot_sha256") != INSTALLED_SNAPSHOT_SHA256
    ):
        raise ValueError("formal import commit evidence mismatch")
    if (
        matrix.get("schema_version") != "huiji.wiki-v3-p0-matrix/v1"
        or matrix.get("status") != "pass"
        or matrix.get("passed") != 8
        or matrix.get("total") != 8
    ):
        raise ValueError("formal import P0 matrix mismatch")
    if (
        protected.get("schema_version") != "huiji.wiki-v3-protected-compare/v1"
        or protected.get("status") != "pass"
    ):
        raise ValueError("formal protected compare mismatch")
    operation_scope = protected.get("operation_scope")
    if not isinstance(operation_scope, Mapping) or any(
        int(operation_scope.get(name, -1)) != 0
        for name in (
            "candidate_artifact_writes",
            "milvus_writes",
            "minio_writes",
            "rag_pointer_writes",
        )
    ):
        raise ValueError("formal protected compare contains storage writes")
    for reference in protected.get("protected_artifacts", []):
        if not isinstance(reference, Mapping):
            raise ValueError("formal protected artifact reference is invalid")
        _verify_reference(project_root, reference)
    return payload, loaded


def _http_json(url: str) -> dict[str, Any]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=15) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"health response is invalid: {url}")
    return value


def _query_database_state(cfg: Any) -> dict[str, Any]:
    import pymysql

    conn = pymysql.connect(
        host=cfg.mysql.host,
        port=cfg.mysql.port,
        user=cfg.mysql.user,
        password=cfg.mysql.password,
        database=cfg.mysql.database,
        charset=cfg.mysql.charset,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("SHOW TABLES")
            tables = {str(next(iter(row.values()))) for row in cursor.fetchall()}
            counts: dict[str, int | None] = {}
            for table in EXPECTED_COUNTS:
                if table not in tables:
                    counts[table] = None
                else:
                    cursor.execute(f"SELECT COUNT(*) AS row_count FROM `{table}`")
                    counts[table] = int((cursor.fetchone() or {}).get("row_count", 0))
            snapshot = None
            if "wiki_import_snapshots" in tables:
                cursor.execute("SELECT * FROM wiki_import_snapshots WHERE id=1")
                snapshot = cursor.fetchone()
        conn.rollback()
        return {"tables": sorted(tables), "counts": counts, "snapshot": snapshot}
    finally:
        conn.close()


def _validate_health(
    rag_health: Mapping[str, Any],
    wiki_health: Mapping[str, Any],
) -> None:
    if (
        rag_health.get("status") != "ok"
        or rag_health.get("vectorstore_loaded") is not True
        or rag_health.get("provenance_status") != "pass"
        or int(rag_health.get("doc_count") or -1) != 14630
    ):
        raise ValueError("RAG health does not match Candidate F")
    expected_wiki = {
        "ready": True,
        "pageCount": EXPECTED_COUNTS["wiki_pages"],
        "categoryCount": EXPECTED_COUNTS["wiki_categories"],
        "mediaLinkCount": EXPECTED_COUNTS["wiki_media_links"],
        "mediaResourceCount": EXPECTED_COUNTS["wiki_media_resources"],
        "mediaBindingCount": EXPECTED_COUNTS["wiki_media_bindings"],
        "sourceMode": "active",
        "buildVersion": BUILD_VERSION,
        "artifactSchemaVersion": ARTIFACT_SCHEMA,
        "activationEpoch": GENERATION,
        "stale": False,
    }
    if any(wiki_health.get(key) != value for key, value in expected_wiki.items()):
        raise ValueError("Wiki health does not match Candidate F")


def _validate_database_state(
    formal_receipt: Mapping[str, Any],
    database_state: Mapping[str, Any],
) -> None:
    formal_database = formal_receipt.get("database")
    if not isinstance(formal_database, Mapping):
        raise ValueError("formal receipt database state is missing")
    if database_state.get("counts") != formal_database.get("counts"):
        raise ValueError("current Wiki counts differ from formal receipt")
    if database_state.get("snapshot") != formal_database.get("snapshot"):
        raise ValueError("current Wiki snapshot differs from formal receipt")
    snapshot = database_state.get("snapshot")
    if (
        not isinstance(snapshot, Mapping)
        or snapshot.get("snapshot_sha256") != INSTALLED_SNAPSHOT_SHA256
        or snapshot.get("manifest_sha256") != "293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f"
        or snapshot.get("source_mode") != "active"
        or snapshot.get("build_version") != BUILD_VERSION
        or snapshot.get("artifact_schema_version") != ARTIFACT_SCHEMA
        or int(snapshot.get("activation_epoch") or -1) != GENERATION
        or not snapshot.get("imported_at_utc")
    ):
        raise ValueError("current Wiki installed snapshot identity mismatch")


def _validate_historical_bootstrap(
    project_root: Path,
    reference: Mapping[str, Any],
    *,
    pointer_before: Path,
    expected_pointer_payload: Mapping[str, Any],
) -> dict[str, Any]:
    from src.huiji_rag.generation_zero import read_journal

    root = Path(project_root).resolve()
    path = _verify_reference(root, reference)
    payload = validate_pinned_json(
        root,
        path,
        expected_sha256=str(reference.get("sha256") or ""),
        expected_schema="huiji.generation-zero-bootstrap-receipt/v1",
    )
    validate_hash_sidecar(path)
    if payload.get("status") != "passed":
        raise ValueError("historical bootstrap receipt is not passing")
    internal_hash = str(payload.get("receipt_sha256") or "")
    without_hash = dict(payload)
    without_hash.pop("receipt_sha256", None)
    expected_internal = hashlib.sha256(
        json.dumps(
            without_hash,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    matrix = payload.get("p0_matrix")
    if (
        internal_hash != expected_internal
        or not isinstance(matrix, Mapping)
        or matrix.get("expected_count") != 44
        or matrix.get("passed_count") != 44
        or len(matrix.get("entries", [])) != 44
    ):
        raise ValueError("historical bootstrap receipt contract mismatch")

    for name in (
        "collection_manifest",
        "deployment_inventory",
        "intent",
        "journal",
        "protected_state_after",
        "protected_state_before",
        "wiki_rollback_receipt",
    ):
        item = payload.get(name)
        if not isinstance(item, Mapping):
            raise ValueError(f"historical bootstrap reference missing: {name}")
        item_path = _verify_reference(root, item)
        if name == "journal":
            events = read_journal(item_path)
            if not events or events[-1].get("state") != "committed":
                raise ValueError("historical bootstrap journal is not committed")
            validate_hash_sidecar(item_path)

    pointer_ref = payload.get("pointer")
    if (
        not isinstance(pointer_ref, Mapping)
        or pointer_ref.get("sha256") != sha256_file(pointer_before)
        or _load_json(pointer_before) != dict(expected_pointer_payload)
        or int(expected_pointer_payload.get("generation", -1)) != 0
    ):
        raise ValueError("historical bootstrap pointer authority mismatch")
    return payload


def _validate_rag_rollback(
    cfg: Any,
    project_root: Path,
    activation_receipt: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    from src.huiji_rag.activation import (
        _capture_milvus,
        _require_milvus,
    )
    from src.huiji_wiki.mysql_rollback import validate_passing_receipt

    root = Path(project_root).resolve()
    proposal_path = resolve_project_path(root, RAG_PROPOSAL_RELATIVE)
    rollback_path = resolve_project_path(root, RAG_ROLLBACK_RELATIVE)
    proposal = validate_pinned_json(
        root,
        proposal_path,
        expected_sha256=RAG_PROPOSAL_SHA256,
        expected_schema="huiji.activation-proposal/v1",
    )
    rollback = validate_pinned_json(
        root,
        rollback_path,
        expected_sha256=RAG_ROLLBACK_SHA256,
        expected_schema="huiji.rollback-tuple/v1",
    )
    if (
        proposal.get("proposal_id") != "candidate-f-review-20260722c"
        or proposal.get("allowed_for_activation_review") is not True
        or proposal.get("blockers") != []
        or proposal.get("rollback_tuple_created") is not True
        or proposal.get("expected_previous_pointer_sha256")
        != "95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723"
        or rollback.get("proposal_id") != proposal.get("proposal_id")
    ):
        raise ValueError("RAG proposal or rollback authority mismatch")
    receipt_rollback = activation_receipt.get("rollback_tuple")
    if not isinstance(receipt_rollback, Mapping) or receipt_rollback.get("sha256") != RAG_ROLLBACK_SHA256:
        raise ValueError("activation receipt rollback reference mismatch")

    references = (
        "previous_build_manifest",
        "previous_collection_manifest",
        "previous_deployment_inventory",
        "previous_installed_provenance",
        "previous_trusted_protected_compare",
        "protected_state_inventory",
        "wiki_restore_entrypoint",
        "wiki_rollback_receipt",
    )
    for name in references:
        reference = rollback.get(name)
        if not isinstance(reference, Mapping):
            raise ValueError(f"RAG rollback reference missing: {name}")
        _verify_reference(root, reference)

    transaction = root / "data/processed/huiji/activation/transactions" / ACTIVATION_ID
    pointer_before = transaction / "active_build.before.v1.json"
    settings_before = transaction / "settings.before.yaml"
    previous_pointer = rollback.get("previous_pointer")
    previous_settings = rollback.get("previous_settings")
    if (
        not isinstance(previous_pointer, Mapping)
        or sha256_file(pointer_before) != previous_pointer.get("sha256")
        or _load_json(pointer_before) != previous_pointer.get("payload")
        or int((previous_pointer.get("payload") or {}).get("generation", -1)) != 0
    ):
        raise ValueError("generation-zero pointer rollback authority mismatch")
    if (
        not isinstance(previous_settings, Mapping)
        or sha256_file(settings_before) != previous_settings.get("sha256")
    ):
        raise ValueError("generation-zero settings rollback authority mismatch")

    proposal_evidence = proposal.get("evidence")
    if not isinstance(proposal_evidence, Mapping):
        raise ValueError("RAG proposal evidence map is missing")
    bootstrap_ref = proposal_evidence.get("bootstrap")
    if not isinstance(bootstrap_ref, Mapping):
        raise ValueError("RAG proposal bootstrap reference is missing")
    bootstrap = _validate_historical_bootstrap(
        root,
        bootstrap_ref,
        pointer_before=pointer_before,
        expected_pointer_payload=previous_pointer["payload"],
    )
    for name in (
        "full_chain",
        "protected_baseline",
        "protected_compare",
        "shadow",
        "wiki_compatibility",
        "wiki_rollback",
    ):
        reference = proposal_evidence.get(name)
        if not isinstance(reference, Mapping):
            raise ValueError(f"RAG proposal evidence reference missing: {name}")
        evidence_path = _verify_reference(root, reference)
        if name in {"full_chain", "shadow", "wiki_compatibility"}:
            evidence_payload = _load_json(evidence_path)
            expected_status = "passed" if name == "wiki_compatibility" else "pass"
            if evidence_payload.get("status") != expected_status:
                raise ValueError(f"RAG proposal evidence is not passing: {name}")
    protected_inventory = proposal.get("protected_state_inventory")
    if not isinstance(protected_inventory, Mapping):
        raise ValueError("RAG proposal protected inventory is missing")
    _verify_reference(root, protected_inventory)

    live_legacy = _capture_milvus(cfg, "text_child_bge_m3_v3")
    _require_milvus(live_legacy, rollback["previous_active_milvus"])

    wiki_reference = handoff.get("wiki_pre_import_rollback_receipt")
    if not isinstance(wiki_reference, Mapping) or wiki_reference.get("sha256") != WIKI_ROLLBACK_SHA256:
        raise ValueError("Wiki rollback handoff reference mismatch")
    wiki_path = _verify_reference(root, wiki_reference)
    wiki_payload = validate_passing_receipt(wiki_path, project_root=root)
    restore = wiki_payload.get("restore_entrypoint")
    if not isinstance(restore, Mapping):
        raise ValueError("Wiki rollback restore entrypoint is missing")
    _verify_reference(root, restore)
    return {
        "rag_generation_zero": {
            "rollback_tuple": _file_ref(rollback_path, root),
            "previous_pointer_sha256": str(previous_pointer["sha256"]),
            "previous_settings_sha256": str(previous_settings["sha256"]),
            "legacy_collection": str(live_legacy["collection"]),
            "legacy_row_count": int(live_legacy["row_count"]),
            "bootstrap_receipt_sha256": str(bootstrap_ref["sha256"]),
            "bootstrap_journal_state": str(bootstrap["journal"]["terminal_state"]),
            "status": "traceable_not_executed",
        },
        "wiki_pre_import": {
            "receipt": _file_ref(wiki_path, root),
            "receipt_id": str(wiki_payload["receipt_id"]),
            "restore_entrypoint": dict(restore),
            "status": "traceable_not_executed",
        },
        "proposal": {
            "proposal_id": str(proposal["proposal_id"]),
            "path": _relative(proposal_path, root),
            "sha256": sha256_file(proposal_path),
        },
    }


def inspect_candidate_closure(
    cfg: Any,
    *,
    project_root: Path,
    formal_receipt_path: Path,
    expected_formal_receipt_sha256: str,
    rag_health_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    wiki_health_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    database_state_fetcher: Callable[[], Mapping[str, Any]] | None = None,
) -> ClosureInspection:
    from src.huiji_rag.activation import validate_activation_receipt, validate_wiki_handoff
    from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot

    root = Path(project_root).resolve(strict=True)
    activation_path = resolve_project_path(root, ACTIVATION_RECEIPT_RELATIVE)
    handoff_path = resolve_project_path(root, WIKI_HANDOFF_RELATIVE)
    pointer_path = resolve_project_path(root, ACTIVE_POINTER_RELATIVE)
    settings_path = resolve_project_path(root, SETTINGS_RELATIVE)
    if sha256_file(activation_path) != ACTIVATION_RECEIPT_SHA256:
        raise ValueError("activation receipt SHA-256 mismatch")
    if sha256_file(handoff_path) != WIKI_HANDOFF_SHA256:
        raise ValueError("Wiki handoff SHA-256 mismatch")
    if sha256_file(pointer_path) != ACTIVE_POINTER_SHA256:
        raise ValueError("active pointer SHA-256 mismatch")
    if sha256_file(settings_path) != SETTINGS_SHA256:
        raise ValueError("settings SHA-256 mismatch")
    activation = validate_activation_receipt(activation_path, root)
    handoff = validate_wiki_handoff(handoff_path, root)
    formal, evidence = validate_formal_import_receipt(
        root,
        formal_receipt_path,
        expected_sha256=expected_formal_receipt_sha256,
    )
    pointer = validate_pinned_json(
        root,
        pointer_path,
        expected_sha256=ACTIVE_POINTER_SHA256,
        expected_schema="evb.active-build/v1",
    )
    if (
        pointer.get("generation") != GENERATION
        or pointer.get("activation_id") != ACTIVATION_ID
        or pointer.get("build_version") != BUILD_VERSION
        or pointer.get("artifact_schema_version") != ARTIFACT_SCHEMA
        or pointer.get("milvus_collection_name") != COLLECTION_NAME
    ):
        raise ValueError("active pointer identity mismatch")
    if (
        handoff.get("wiki_import_status") != "not_started"
        or handoff.get("active_generation") != GENERATION
        or handoff.get("active_build_version") != BUILD_VERSION
        or handoff.get("active_collection") != COLLECTION_NAME
    ):
        raise ValueError("Wiki handoff identity mismatch")

    snapshot = resolve_runtime_artifact_snapshot(cfg)
    if snapshot.build_version != BUILD_VERSION or snapshot.collection_name != COLLECTION_NAME:
        raise ValueError("strict RAG runtime snapshot identity mismatch")
    runtime_identity = {
        "source_mode": snapshot.source_mode,
        "generation": int(pointer["generation"]),
        "build_version": snapshot.build_version,
        "collection": snapshot.collection_name,
        "artifact_schema_version": snapshot.artifact_schema_version,
        "manifest_sha256": snapshot.manifest_sha256,
        "tuple_sha256": snapshot.tuple_sha256,
        "artifact_sha256": dict(snapshot.artifact_sha256),
    }

    rag_health = dict((rag_health_fetcher or (lambda: _http_json("http://127.0.0.1:8000/health")))())
    wiki_health = dict((wiki_health_fetcher or (lambda: _http_json("http://127.0.0.1:8000/api/wiki/health")))())
    _validate_health(rag_health, wiki_health)
    database_state = dict((database_state_fetcher or (lambda: _query_database_state(cfg)))())
    _validate_database_state(formal, database_state)
    rollback = _validate_rag_rollback(cfg, root, activation, handoff)
    return ClosureInspection(
        activation_receipt=activation,
        handoff=handoff,
        formal_receipt=formal,
        formal_evidence=evidence,
        active_pointer=pointer,
        runtime_identity=runtime_identity,
        rag_health=rag_health,
        wiki_health=wiki_health,
        database_state=database_state,
        rollback=rollback,
    )


def _requirement_matrix() -> dict[str, Any]:
    return {
        "expected_count": len(EXPECTED_P0_IDS),
        "passed_count": len(EXPECTED_P0_IDS),
        "entries": [
            {"id": requirement, "status": "passed", "evidence": "closure validator and current read-only state"}
            for requirement in EXPECTED_P0_IDS
        ],
    }


def build_closure_receipt(
    inspection: ClosureInspection,
    *,
    project_root: Path,
    formal_receipt_path: Path,
    closed_at_utc: str,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    formal_path = resolve_project_path(root, formal_receipt_path)
    activation_path = resolve_project_path(root, ACTIVATION_RECEIPT_RELATIVE)
    handoff_path = resolve_project_path(root, WIKI_HANDOFF_RELATIVE)
    pointer_path = resolve_project_path(root, ACTIVE_POINTER_RELATIVE)
    protected_ref = inspection.formal_receipt["evidence"]["protected_compare"]
    snapshot = inspection.database_state["snapshot"]
    return {
        "schema_version": CLOSURE_SCHEMA,
        "status": "closed",
        "activation_id": ACTIVATION_ID,
        "closed_at_utc": closed_at_utc,
        "activation": {
            "activation_receipt": _file_ref(activation_path, root),
            "wiki_handoff": _file_ref(handoff_path, root),
            "active_pointer": _file_ref(pointer_path, root),
        },
        "wiki_import": {
            "formal_import_receipt": _file_ref(formal_path, root),
            "status_transition": {"from": "not_started", "to": "completed"},
            "formal_completed_at_utc": inspection.formal_receipt["completed_at_utc"],
            "installed_snapshot": dict(snapshot),
        },
        "runtime_identity": {
            "rag": dict(inspection.runtime_identity),
            "wiki": {
                "generation": inspection.wiki_health["activationEpoch"],
                "build_version": inspection.wiki_health["buildVersion"],
                "artifact_schema_version": inspection.wiki_health["artifactSchemaVersion"],
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "manifest_sha256": snapshot["manifest_sha256"],
            },
        },
        "joint_health": {
            "rag": dict(inspection.rag_health),
            "wiki": dict(inspection.wiki_health),
            "inventory_counts": dict(inspection.database_state["counts"]),
        },
        "rollback": dict(inspection.rollback),
        "mutation_assertions": {
            "milvus_writes": False,
            "minio_writes": False,
            "embedding_runs": False,
            "mysql_imports": False,
            "scope": "candidate_f_closure_operation",
            "formal_protected_compare": dict(protected_ref),
        },
        "requirement_matrix": _requirement_matrix(),
    }


def _validate_receipt_shape(payload: Mapping[str, Any]) -> None:
    matrix = payload.get("requirement_matrix")
    if (
        payload.get("schema_version") != CLOSURE_SCHEMA
        or payload.get("status") != "closed"
        or payload.get("activation_id") != ACTIVATION_ID
        or not payload.get("closed_at_utc")
        or not isinstance(matrix, Mapping)
        or matrix.get("expected_count") != 23
        or matrix.get("passed_count") != 23
    ):
        raise ValueError("closure receipt contract mismatch")
    entries = matrix.get("entries")
    if (
        not isinstance(entries, list)
        or len(entries) != 23
        or tuple(entry.get("id") for entry in entries) != EXPECTED_P0_IDS
        or any(entry.get("status") != "passed" for entry in entries)
    ):
        raise ValueError("closure receipt P0 matrix mismatch")
    transition = ((payload.get("wiki_import") or {}).get("status_transition") or {})
    if transition != {"from": "not_started", "to": "completed"}:
        raise ValueError("closure receipt Wiki status transition mismatch")
    mutation = payload.get("mutation_assertions")
    if not isinstance(mutation, Mapping) or any(
        mutation.get(name) is not False
        for name in ("milvus_writes", "minio_writes", "embedding_runs", "mysql_imports")
    ):
        raise ValueError("closure receipt mutation assertions mismatch")


def validate_closure_receipt(
    cfg: Any,
    *,
    project_root: Path,
    receipt_path: Path,
    expected_receipt_sha256: str,
    rag_health_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    wiki_health_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    database_state_fetcher: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=True)
    path = resolve_project_path(root, receipt_path)
    payload = validate_pinned_json(
        root,
        path,
        expected_sha256=expected_receipt_sha256,
        expected_schema=CLOSURE_SCHEMA,
    )
    validate_hash_sidecar(path, require_lf=True)
    _validate_receipt_shape(payload)
    formal_ref = payload["wiki_import"]["formal_import_receipt"]
    if not isinstance(formal_ref, Mapping):
        raise ValueError("closure receipt formal import reference missing")
    inspection = inspect_candidate_closure(
        cfg,
        project_root=root,
        formal_receipt_path=_path_from_ref(root, formal_ref),
        expected_formal_receipt_sha256=str(formal_ref.get("sha256") or ""),
        rag_health_fetcher=rag_health_fetcher,
        wiki_health_fetcher=wiki_health_fetcher,
        database_state_fetcher=database_state_fetcher,
    )
    expected = build_closure_receipt(
        inspection,
        project_root=root,
        formal_receipt_path=_path_from_ref(root, formal_ref),
        closed_at_utc=str(payload["closed_at_utc"]),
    )
    if payload != expected:
        raise ValueError("closure receipt differs from current validated state")
    return payload


def _write_receipt_and_sidecar_create_new(path: Path, payload: Mapping[str, Any]) -> str:
    path = Path(path)
    sidecar = path.with_name(f"{path.name}.sha256")
    if path.exists() or sidecar.exists():
        raise ClosureConflict("closure receipt output is not create-new")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    created_receipt = False
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        created_receipt = True
        with sidecar.open("xb") as handle:
            handle.write(f"{digest}  {path.name}\n".encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        if created_receipt and not sidecar.exists() and path.is_file() and sha256_file(path) == digest:
            path.unlink()
        raise
    return digest


def close_candidate(
    cfg: Any,
    *,
    project_root: Path,
    formal_receipt_path: Path,
    expected_formal_receipt_sha256: str,
    output_path: Path | None = None,
    rag_health_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    wiki_health_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    database_state_fetcher: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=True)
    output = resolve_project_path(root, output_path or DEFAULT_OUTPUT_RELATIVE)
    sidecar = output.with_name(f"{output.name}.sha256")
    if output.exists() != sidecar.exists():
        raise ClosureConflict("closure receipt has a partial pre-existing output")
    if output.exists():
        digest = validate_hash_sidecar(output, require_lf=True)
        validate_closure_receipt(
            cfg,
            project_root=root,
            receipt_path=output,
            expected_receipt_sha256=digest,
            rag_health_fetcher=rag_health_fetcher,
            wiki_health_fetcher=wiki_health_fetcher,
            database_state_fetcher=database_state_fetcher,
        )
        return {
            "status": "already_closed",
            "receipt_path": _relative(output, root),
            "receipt_sha256": digest,
            "p0_passed": 23,
            "p0_total": 23,
        }

    inspection = inspect_candidate_closure(
        cfg,
        project_root=root,
        formal_receipt_path=formal_receipt_path,
        expected_formal_receipt_sha256=expected_formal_receipt_sha256,
        rag_health_fetcher=rag_health_fetcher,
        wiki_health_fetcher=wiki_health_fetcher,
        database_state_fetcher=database_state_fetcher,
    )
    payload = build_closure_receipt(
        inspection,
        project_root=root,
        formal_receipt_path=formal_receipt_path,
        closed_at_utc=utc_now(),
    )
    digest = _write_receipt_and_sidecar_create_new(output, payload)
    validate_closure_receipt(
        cfg,
        project_root=root,
        receipt_path=output,
        expected_receipt_sha256=digest,
        rag_health_fetcher=rag_health_fetcher,
        wiki_health_fetcher=wiki_health_fetcher,
        database_state_fetcher=database_state_fetcher,
    )
    return {
        "status": "closed",
        "receipt_path": _relative(output, root),
        "receipt_sha256": digest,
        "p0_passed": 23,
        "p0_total": 23,
    }


__all__ = [
    "ACTIVATION_ID",
    "CLOSURE_SCHEMA",
    "ClosureConflict",
    "ClosureInspection",
    "DEFAULT_FORMAL_RECEIPT_RELATIVE",
    "DEFAULT_OUTPUT_RELATIVE",
    "EXPECTED_P0_IDS",
    "FORMAL_IMPORT_RECEIPT_SHA256",
    "build_closure_receipt",
    "canonical_json_bytes",
    "close_candidate",
    "inspect_candidate_closure",
    "resolve_project_path",
    "sha256_file",
    "validate_closure_receipt",
    "validate_formal_import_receipt",
    "validate_hash_sidecar",
    "validate_pinned_json",
]
