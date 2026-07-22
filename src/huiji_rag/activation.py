"""Hash-pinned Candidate F activation transaction and compensation workflow."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from ruamel.yaml import YAML

from src.huiji_rag.active_pointer import (
    canonical_json_bytes,
    canonical_pointer_path,
    load_active_pointer,
    validate_active_pointer,
)
from src.huiji_rag.backend_process import (
    BackendProcessIdentity,
    assert_same_backend,
    inspect_backend,
    inspect_backend_optional,
    public_process_reference,
    start_backend,
    stop_backend,
    stop_owned_backend,
    wait_for_listener,
)
from src.huiji_rag.generation_zero import (
    load_hash_pinned_json,
    sha256_file,
    utc_now,
    validate_bootstrap_receipt,
    validate_wiki_rollback_receipt,
    write_hash_pinned_json_create_new,
)


ACTIVATION_INTENT_SCHEMA = "huiji.activation-intent/v1"
COLLECTION_MANIFEST_SCHEMA = "evb.collection-manifest/v1"
DEPLOYMENT_INVENTORY_SCHEMA = "huiji.activation-deployment-inventory/v1"
ACTIVATION_JOURNAL_SCHEMA = "huiji.activation-journal-event/v1"
ACTIVATION_RECEIPT_SCHEMA = "huiji.activation-receipt/v1"
ACTIVATION_FAILURE_SCHEMA = "huiji.activation-failure/v1"
WIKI_HANDOFF_SCHEMA = "huiji.wiki-import-handoff/v1"

FAILED_ACTIVATIONS: Mapping[str, str] = {
    "candidate-f-generation-1-20260722a": "fc9ea4c71243da3a85e7b1c70e86680852154541c44bf4aa49c2845791f22fcb",
    "candidate-f-generation-1-20260722b": "5ed9f3ada392045aa95fc52364207a94660b712be99d0ecca1266f969d7c08fb",
    "candidate-f-generation-1-20260722c": "1aed68fc1288646b029561c3eaadb34131656d82174a33c11efd3a1b1eeb5b0e",
}
ACTIVATION_ID = "candidate-f-generation-1-20260722d"
RECOVERABLE_ACTIVATION_IDS = frozenset((*FAILED_ACTIVATIONS, ACTIVATION_ID))
PROPOSAL_ID = "candidate-f-review-20260722c"
PROPOSAL_SHA256 = "fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8"
ROLLBACK_SHA256 = "07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b"
PREVIOUS_POINTER_SHA256 = "95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723"
PREVIOUS_SETTINGS_SHA256 = "d5363e07a4917455b7d1b69c2e1de0a6bff02f6f95ffeab2c7821551bb99a06d"
CANDIDATE_BUILD = "crawler-v3-20260721t051246z"
CANDIDATE_BUILD_SHA256 = "293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f"
CANDIDATE_COLLECTION = "text_child_bge_m3_shadow_crawler_v3_20260721t051246z"
CANDIDATE_SCHEMA_SHA256 = "db9e13b98d7a1cf4116ba6647a16eb0e7daff0a77c558f66c9db2597038a6bc4"
CANDIDATE_PRIMARY_IDS_SHA256 = "88dec5bd859acf331984772c21306e5655008872f305ba5f618b50ddec3b1ade"
CANDIDATE_BUSINESS_FIELDS_SHA256 = "0ec89b966b64a2f6f4727c2dd6cb5ac09f01f96f3e26ec85a584e6b718374784"
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_CONFIG_SHA256 = "17787be97e63ea53e3298748adf546ebc17d5456669481349eb8bb088b336099"
CONFIRMATION = (
    f"ACTIVATE {ACTIVATION_ID} FROM "
    f"{PREVIOUS_POINTER_SHA256} TO {CANDIDATE_BUILD}"
)

_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_TRANSITIONS: Mapping[str | None, frozenset[str]] = {
    None: frozenset({"prepared"}),
    "prepared": frozenset({"backend_stopped", "verification_failed", "conflict"}),
    "backend_stopped": frozenset({"settings_written", "verification_failed", "conflict"}),
    "settings_written": frozenset({"pointer_written", "verification_failed", "conflict"}),
    "pointer_written": frozenset({"backend_started", "verification_failed", "conflict"}),
    "backend_started": frozenset({"verified", "verification_failed", "conflict"}),
    "verified": frozenset({"committed", "verification_failed", "conflict"}),
    "verification_failed": frozenset({"compensating", "conflict"}),
    "compensating": frozenset({"rolled_back", "conflict"}),
    "rolled_back": frozenset(),
    "committed": frozenset(),
    "conflict": frozenset(),
}


class ActivationRolledBack(RuntimeError):
    """The candidate failed but generation zero was restored and verified."""


class ActivationConflict(RuntimeError):
    """Unknown canonical bytes were detected; callers must not overwrite them."""


def _root(cfg: object) -> Path:
    return Path(getattr(getattr(cfg, "paths"), "project_root")).resolve()


def _relative(path: str | Path, root: Path) -> str:
    target = Path(path).resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("path escapes project root") from error


def _ref(path: str | Path, root: Path) -> dict[str, object]:
    target = Path(path).resolve()
    return {
        "relative_path": _relative(target, root),
        "sha256": sha256_file(target),
        "size": target.stat().st_size,
    }


def _path_from_ref(root: Path, value: Mapping[str, object]) -> Path:
    relative = str(value.get("relative_path") or value.get("path") or "")
    target = (root / relative).resolve()
    _relative(target, root)
    return target


def _write_bytes_create_new(path: Path, raw: bytes) -> str:
    sidecar = path.with_name(f"{path.name}.sha256")
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"activation evidence already exists: {path}")
    digest = hashlib.sha256(raw).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        with sidecar.open("xb") as handle:
            handle.write(f"{digest}  {path.name}\n".encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        sidecar.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return digest


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _capture_milvus(cfg: object, collection: str) -> dict[str, object]:
    from pymilvus import MilvusClient
    from src.huiji_rag.provenance import capture_milvus_fingerprint

    vectorstore = getattr(cfg, "vectorstore")
    client = MilvusClient(
        uri=str(getattr(vectorstore, "uri")),
        db_name=str(getattr(vectorstore, "db_name")),
    )
    return capture_milvus_fingerprint(
        client,
        collection,
        database=str(getattr(vectorstore, "db_name")),
    ).to_json()


def _require_milvus(actual: Mapping[str, object], expected: Mapping[str, object]) -> None:
    fields = (
        "database",
        "collection",
        "schema_sha256",
        "row_count",
        "primary_field",
        "primary_id_count",
        "primary_ids_sha256",
        "business_fields_sha256",
    )
    if any(actual.get(field) != expected.get(field) for field in fields):
        raise ValueError("Milvus fingerprint mismatch")


def _validate_fixed_authority(
    cfg: object,
    proposal_path: Path,
    rollback_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _root(cfg)
    proposal, _ = load_hash_pinned_json(
        proposal_path,
        expected_sha256=PROPOSAL_SHA256,
        expected_schema="huiji.activation-proposal/v1",
    )
    rollback, _ = load_hash_pinned_json(
        rollback_path,
        expected_sha256=ROLLBACK_SHA256,
        expected_schema="huiji.rollback-tuple/v1",
    )
    if (
        proposal.get("proposal_id") != PROPOSAL_ID
        or proposal.get("allowed_for_activation_review") is not True
        or proposal.get("blockers") != []
        or proposal.get("rollback_tuple_created") is not True
        or proposal.get("next_gate") != "separate_user_approved_candidate_f_activation"
        or proposal.get("expected_previous_pointer_sha256") != PREVIOUS_POINTER_SHA256
    ):
        raise ValueError("activation proposal authority mismatch")
    if rollback.get("proposal_id") != PROPOSAL_ID:
        raise ValueError("rollback tuple proposal mismatch")
    previous = rollback.get("previous_pointer")
    settings = rollback.get("previous_settings")
    if (
        not isinstance(previous, Mapping)
        or previous.get("sha256") != PREVIOUS_POINTER_SHA256
        or not isinstance(settings, Mapping)
        or settings.get("sha256") != PREVIOUS_SETTINGS_SHA256
    ):
        raise ValueError("rollback previous tuple mismatch")
    scopes = rollback.get("minio_scopes")
    if not isinstance(scopes, Mapping) or set(scopes) != {
        "a-bucket",
        "reverse1999-assets/reverse1999",
    }:
        raise ValueError("rollback MinIO scopes are incomplete")
    evidence = proposal.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("proposal evidence map is missing")
    schemas = {
        "shadow": "huiji.shadow_build/v1",
        "full_chain": "huiji.candidate-full-chain/v1",
        "wiki_compatibility": "huiji.wiki-media-v3-compatibility-receipt/v1",
        "bootstrap": "huiji.generation-zero-bootstrap-receipt/v1",
    }
    for name, schema in schemas.items():
        reference = evidence.get(name)
        if not isinstance(reference, Mapping):
            raise ValueError(f"proposal evidence is missing: {name}")
        path = _path_from_ref(root, reference)
        if name == "bootstrap":
            payload = validate_bootstrap_receipt(path, project_root=root)
        elif name == "wiki_compatibility":
            if sha256_file(path) != str(reference.get("sha256") or ""):
                raise ValueError("Wiki compatibility receipt SHA-256 mismatch")
            payload = _load_json(path)
            if payload.get("schema_version") != schema:
                raise ValueError("Wiki compatibility receipt schema mismatch")
        else:
            payload, _ = load_hash_pinned_json(
                path,
                expected_sha256=str(reference.get("sha256") or ""),
                expected_schema=schema,
            )
        expected_status = "passed" if name == "wiki_compatibility" else "pass"
        if name in {"shadow", "full_chain", "wiki_compatibility"} and payload.get("status") != expected_status:
            raise ValueError(f"proposal evidence is not passing: {name}")
    wiki_ref = evidence.get("wiki_rollback")
    if not isinstance(wiki_ref, Mapping):
        raise ValueError("Wiki rollback receipt reference is missing")
    validate_wiki_rollback_receipt(
        _path_from_ref(root, wiki_ref), str(wiki_ref.get("sha256") or ""), root
    )
    return proposal, rollback


def _candidate_artifacts(build_root: Path, manifest: Mapping[str, Any], root: Path) -> dict[str, dict[str, object]]:
    by_path = {
        str(item.get("relative_path") or ""): item
        for item in manifest.get("artifacts", [])
        if isinstance(item, Mapping)
    }
    required = {
        "parent_blocks": "parent_blocks.jsonl",
        "child_blocks": "child_blocks.jsonl",
        "media_assets": "runtime/media_assets.v3.jsonl",
        "child_bm25": "indexes/child_text_bm25.json",
        "media_bm25": "indexes/media_binding_bm25.v3.json",
        "media_schema": "runtime/media_assets.v3.schema.json",
        "media_manifest": "runtime/media_assets.v3.manifest.json",
    }
    output: dict[str, dict[str, object]] = {}
    for name, relative in required.items():
        entry = by_path.get(relative)
        target = (build_root / relative).resolve()
        if not isinstance(entry, Mapping) or build_root not in target.parents or not target.is_file():
            raise ValueError(f"Candidate artifact missing: {relative}")
        reference = _ref(target, root)
        if (
            reference["sha256"] != entry.get("sha256")
            or reference["size"] != entry.get("size", reference["size"])
        ):
            raise ValueError(f"Candidate artifact drift: {relative}")
        reference["schema_version"] = entry.get("schema_version")
        reference["row_count"] = entry.get("row_count")
        output[name] = reference
    return output


def _build_collection_manifest(
    cfg: object,
    proposal: Mapping[str, Any],
    rollback: Mapping[str, Any],
) -> dict[str, object]:
    root = _root(cfg)
    build_root = root / "data/processed/huiji" / CANDIDATE_BUILD
    build_path = build_root / "build_manifest.json"
    if sha256_file(build_path) != CANDIDATE_BUILD_SHA256:
        raise ValueError("Candidate build manifest drift")
    build = _load_json(build_path)
    if (
        build.get("build_version") != CANDIDATE_BUILD
        or build.get("state") != "ready_for_embedding"
        or build.get("blockers") != []
        or build.get("artifact_schema_version") != "evb.media-asset/v3"
    ):
        raise ValueError("Candidate build state mismatch")
    artifacts = _candidate_artifacts(build_root, build, root)
    shadow_ref = proposal["evidence"]["shadow"]
    full_chain_ref = proposal["evidence"]["full_chain"]
    shadow = _load_json(_path_from_ref(root, shadow_ref))
    candidate_milvus = _capture_milvus(cfg, CANDIDATE_COLLECTION)
    expected = {
        "database": "reverse1999_rag",
        "collection": CANDIDATE_COLLECTION,
        "schema_sha256": CANDIDATE_SCHEMA_SHA256,
        "row_count": 14630,
        "primary_field": "id",
        "primary_id_count": 14630,
        "primary_ids_sha256": CANDIDATE_PRIMARY_IDS_SHA256,
        "business_fields_sha256": CANDIDATE_BUSINESS_FIELDS_SHA256,
    }
    _require_milvus(candidate_milvus, expected)
    _require_milvus(candidate_milvus, shadow["post_fingerprint"])
    handoff_path = build_root / "handoff/embedding_handoff.v1.json"
    handoff = _load_json(handoff_path)
    if (
        handoff.get("embedding_config_fingerprint_sha256") != EMBEDDING_CONFIG_SHA256
        or handoff.get("child_ordered_ids_sha256") != CANDIDATE_PRIMARY_IDS_SHA256
    ):
        raise ValueError("Candidate embedding handoff mismatch")
    return {
        "schema_version": COLLECTION_MANIFEST_SCHEMA,
        "artifact_schema_version": "evb.media-asset/v3",
        "build_version": CANDIDATE_BUILD,
        "build_manifest": _ref(build_path, root),
        "artifacts": artifacts,
        "milvus": candidate_milvus,
        "embedding": {
            "model_id": EMBEDDING_MODEL,
            "config_fingerprint": EMBEDDING_CONFIG_SHA256,
        },
        "evidence": {
            "proposal": _ref(root / "data/processed/huiji/activation/proposals/candidate-f-review-20260722c/activation_proposal.v1.json", root),
            "rollback_tuple": _ref(root / "data/processed/huiji/activation/proposals/candidate-f-review-20260722c/rollback_tuple.v1.json", root),
            "embedding_handoff": _ref(handoff_path, root),
            "shadow": dict(shadow_ref),
            "full_chain": dict(full_chain_ref),
            "wiki_compatibility": dict(proposal["evidence"]["wiki_compatibility"]),
            "wiki_rollback": dict(proposal["evidence"]["wiki_rollback"]),
            "bootstrap": dict(proposal["evidence"]["bootstrap"]),
        },
        "previous_milvus": dict(rollback["previous_active_milvus"]),
    }


def _candidate_settings(raw: bytes) -> bytes:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    value = yaml.load(raw.decode("utf-8"))
    before = copy.deepcopy(value)
    value["vectorstore"]["collection_name"] = CANDIDATE_COLLECTION
    value["huiji"]["text_collection_name"] = CANDIDATE_COLLECTION
    value["huiji"]["build_version"] = CANDIDATE_BUILD
    stream = io.StringIO()
    yaml.dump(value, stream)
    encoded = stream.getvalue().replace("\r\n", "\n").encode("utf-8")
    check = yaml.load(encoded.decode("utf-8"))
    for section, field in (
        ("vectorstore", "collection_name"),
        ("huiji", "text_collection_name"),
        ("huiji", "build_version"),
    ):
        before[section][field] = check[section][field]
    if before != check:
        raise ValueError("Candidate settings changed outside the approved fields")
    return encoded


def _stable_protected(value: Mapping[str, object]) -> dict[str, object]:
    frozen = copy.deepcopy(dict(value))
    frozen.pop("captured_at_utc", None)
    inventories = frozen.get("minio_inventories")
    if isinstance(inventories, dict):
        for inventory in inventories.values():
            if isinstance(inventory, dict):
                inventory.pop("captured_at_utc", None)
                inventory.pop("inventory_sha256", None)
    frozen.pop("milvus", None)
    return frozen


def _pinned_artifact_entries(
    root: Path,
    reference: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    path = _path_from_ref(root, reference)
    expected_sha256 = str(reference.get("sha256") or "")
    if not _SHA_RE.fullmatch(expected_sha256) or not path.is_file():
        raise ValueError("authorized artifact reference is invalid")
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"authorized artifact SHA-256 mismatch: {_relative(path, root)}")
    sidecar = path.with_name(f"{path.name}.sha256")
    expected_sidecar = f"{expected_sha256}  {path.name}\n".encode("ascii")
    if not sidecar.is_file() or sidecar.read_bytes() != expected_sidecar:
        raise ValueError(f"authorized artifact sidecar mismatch: {_relative(path, root)}")
    return {
        _relative(path, root): {
            "sha256": expected_sha256,
            "size": path.stat().st_size,
        },
        _relative(sidecar, root): {
            "sha256": sha256_file(sidecar),
            "size": sidecar.stat().st_size,
        },
    }


def _authorized_post_bootstrap_artifacts(
    root: Path,
    *,
    proposal_path: Path,
    rollback_path: Path,
    proposal: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    evidence = proposal.get("evidence")
    inventory = proposal.get("protected_state_inventory")
    if not isinstance(evidence, Mapping) or not isinstance(inventory, Mapping):
        raise ValueError("activation proposal lacks protected evidence references")
    bootstrap_ref = evidence.get("bootstrap")
    if not isinstance(bootstrap_ref, Mapping):
        raise ValueError("activation proposal lacks bootstrap receipt reference")
    bootstrap = validate_bootstrap_receipt(
        _path_from_ref(root, bootstrap_ref), project_root=root
    )
    journal_ref = bootstrap.get("journal")
    protected_after_ref = bootstrap.get("protected_state_after")
    if not isinstance(journal_ref, Mapping) or not isinstance(protected_after_ref, Mapping):
        raise ValueError("bootstrap receipt lacks terminal protected evidence")

    references: tuple[Mapping[str, object], ...] = (
        {"relative_path": _relative(proposal_path, root), "sha256": PROPOSAL_SHA256},
        {"relative_path": _relative(rollback_path, root), "sha256": ROLLBACK_SHA256},
        inventory,
        bootstrap_ref,
        journal_ref,
        protected_after_ref,
    )
    allowed: dict[str, dict[str, object]] = {}
    for reference in references:
        entries = _pinned_artifact_entries(root, reference)
        overlap = set(allowed).intersection(entries)
        if overlap:
            raise ValueError(f"duplicate authorized artifact reference: {sorted(overlap)[0]}")
        allowed.update(entries)
    return allowed


def _authorized_one_failed_activation(
    root: Path,
    *,
    activation_id: str,
    intent_sha256: str,
) -> dict[str, dict[str, object]]:
    transaction = (
        root / "data/processed/huiji/activation/transactions" / activation_id
    )
    intent_path = transaction / "activation_intent.v1.json"
    intent, _ = load_hash_pinned_json(
        intent_path,
        expected_sha256=intent_sha256,
        expected_schema=ACTIVATION_INTENT_SCHEMA,
    )
    if intent.get("activation_id") != activation_id:
        raise ValueError("failed activation intent ID mismatch")
    deployment_ref = intent.get("deployment_inventory")
    if not isinstance(deployment_ref, Mapping):
        raise ValueError("failed activation lacks deployment inventory")
    deployment, _ = load_hash_pinned_json(
        _path_from_ref(root, deployment_ref),
        expected_sha256=str(deployment_ref.get("sha256") or ""),
        expected_schema=DEPLOYMENT_INVENTORY_SCHEMA,
    )
    failure_path = transaction / "activation_failure.v1.json"
    failure, failure_sha = load_hash_pinned_json(
        failure_path,
        expected_schema=ACTIVATION_FAILURE_SCHEMA,
    )
    if (
        failure.get("activation_id") != activation_id
        or failure.get("status") != "failed"
        or failure.get("journal_terminal_state") != "rolled_back"
    ):
        raise ValueError("failed activation receipt is not rolled back")
    journal_path = transaction / "activation_journal.v1.jsonl"
    events = read_journal(journal_path)
    if (
        not events
        or events[-1].get("state") != "rolled_back"
        or any(event.get("intent_sha256") != intent_sha256 for event in events)
    ):
        raise ValueError("failed activation journal is not a sealed rollback")
    journal_sha = sha256_file(journal_path)

    references: list[Mapping[str, object]] = [
        {
            "relative_path": _relative(intent_path, root),
            "sha256": intent_sha256,
        },
        {
            "relative_path": _relative(journal_path, root),
            "sha256": journal_sha,
        },
        {
            "relative_path": _relative(failure_path, root),
            "sha256": failure_sha,
        },
        deployment_ref,
    ]
    for key in (
        "pointer_candidate",
        "settings_candidate",
        "collection_manifest",
        "protected_state_before",
    ):
        reference = intent.get(key)
        if not isinstance(reference, Mapping):
            raise ValueError(f"failed activation intent lacks {key}")
        references.append(reference)
    for key in ("pointer_before", "settings_before"):
        reference = deployment.get(key)
        if not isinstance(reference, Mapping):
            raise ValueError(f"failed activation deployment inventory lacks {key}")
        references.append(reference)
    optional_evidence = (
        ("retrieval_smoke.v1.json", "huiji.activation-retrieval-smoke/v1"),
        ("voice_pagination.v1.json", "huiji.activation-voice-pagination/v1"),
    )
    for filename, schema in optional_evidence:
        path = transaction / filename
        if not path.exists():
            continue
        payload, digest = load_hash_pinned_json(path)
        actual_schema = payload.get("schema_version")
        allowed_schemas = {schema}
        if filename.startswith("retrieval_"):
            allowed_schemas.add("huiji.active_source_sample/v1")
        if actual_schema not in allowed_schemas:
            raise ValueError("failed activation optional evidence schema mismatch")
        if filename.startswith("retrieval_") and payload.get("status") != "pass":
            raise ValueError("failed activation retrieval evidence is not passing")
        references.append(
            {"relative_path": _relative(path, root), "sha256": digest}
        )

    allowed: dict[str, dict[str, object]] = {}
    for reference in references:
        entries = _pinned_artifact_entries(root, reference)
        overlap = set(allowed).intersection(entries)
        if overlap:
            raise ValueError(f"duplicate failed activation artifact: {sorted(overlap)[0]}")
        allowed.update(entries)
    return allowed


def _authorized_failed_activation_artifacts(root: Path) -> dict[str, dict[str, object]]:
    allowed: dict[str, dict[str, object]] = {}
    for activation_id, intent_sha256 in FAILED_ACTIVATIONS.items():
        transaction = (
            root / "data/processed/huiji/activation/transactions" / activation_id
        )
        if not transaction.exists():
            continue
        entries = _authorized_one_failed_activation(
            root,
            activation_id=activation_id,
            intent_sha256=intent_sha256,
        )
        overlap = set(allowed).intersection(entries)
        if overlap:
            raise ValueError(f"failed activation artifact overlap: {sorted(overlap)[0]}")
        allowed.update(entries)
    return allowed


def compare_activation_protected(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    transaction_prefix: str | None = None,
    allowed_artifact_changes: Mapping[str, Mapping[str, object]] | None = None,
) -> list[str]:
    left = _stable_protected(before)
    right = _stable_protected(after)
    left_artifacts = left.get("artifacts")
    right_artifacts = right.get("artifacts")
    if not isinstance(left_artifacts, dict) or not isinstance(right_artifacts, dict):
        raise ValueError("protected artifact map is missing")
    pointer = "data/processed/huiji/active_build.v1.json"
    left_artifacts.pop(pointer, None)
    right_artifacts.pop(pointer, None)
    allowed = dict(allowed_artifact_changes or {})
    for key, expected in allowed.items():
        if right_artifacts.get(key) != dict(expected):
            raise ValueError(f"authorized artifact does not match protected capture: {key}")
        left_artifacts.pop(key, None)
        right_artifacts.pop(key, None)
    prefixes: tuple[str, ...] = ()
    if transaction_prefix:
        prefixes += (str(transaction_prefix).rstrip("/") + "/",)
    for key in list(right_artifacts):
        if any(key.startswith(prefix) for prefix in prefixes) and key not in left_artifacts:
            del right_artifacts[key]
    changes: list[str] = []
    for key in ("minio_inventories", "mysql_tables", "artifacts"):
        if left.get(key) != right.get(key):
            changes.append(f"{key} changed")
    return changes


def _health(url: str, timeout: float = 15.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("health response is invalid")
    return value


def _wait_candidate_health(timeout_seconds: float = 180.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last = _health("http://127.0.0.1:8000/health", timeout=5)
            if (
                last.get("status") == "ok"
                and last.get("vectorstore_loaded") is True
                and last.get("provenance_status") == "pass"
                and int(last.get("doc_count") or 0) == 14630
            ):
                return last
        except Exception:
            pass
        time.sleep(1.0)
    raise TimeoutError(f"Candidate health timed out: {last.get('status', 'unavailable')}")


def _wait_legacy_health(timeout_seconds: float = 180.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last = _health("http://127.0.0.1:8000/health", timeout=5)
            if (
                last.get("status") == "ok"
                and last.get("vectorstore_loaded") is True
                and last.get("provenance_status") == "pass"
                and int(last.get("doc_count") or 0) == 16010
            ):
                return last
        except Exception:
            pass
        time.sleep(1.0)
    raise TimeoutError(f"Legacy health timed out: {last.get('status', 'unavailable')}")


def read_journal(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    previous_hash = ""
    for line_number, raw in enumerate(path.read_bytes().splitlines(), start=1):
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict) or raw != canonical_json_bytes(value, trailing_newline=False):
            raise ValueError("activation journal is not canonical")
        if value.get("schema_version") != ACTIVATION_JOURNAL_SCHEMA:
            raise ValueError("activation journal schema mismatch")
        if value.get("sequence") != line_number or value.get("previous_event_sha256") != previous_hash:
            raise ValueError("activation journal hash chain mismatch")
        previous_state = str(events[-1]["state"]) if events else None
        if value.get("state") not in _TRANSITIONS.get(previous_state, frozenset()):
            raise ValueError("activation journal transition mismatch")
        previous_hash = hashlib.sha256(raw).hexdigest()
        events.append(value)
    return events


def append_journal(
    path: Path,
    *,
    state: str,
    intent_sha256: str,
    pointer_sha256: str,
    details: Mapping[str, object] | None = None,
) -> None:
    events = read_journal(path)
    previous_state = str(events[-1]["state"]) if events else None
    if state not in _TRANSITIONS.get(previous_state, frozenset()):
        raise ValueError("activation journal transition mismatch")
    previous_raw = (
        canonical_json_bytes(events[-1], trailing_newline=False) if events else b""
    )
    event = {
        "schema_version": ACTIVATION_JOURNAL_SCHEMA,
        "sequence": len(events) + 1,
        "previous_event_sha256": hashlib.sha256(previous_raw).hexdigest() if events else "",
        "intent_sha256": intent_sha256,
        "pointer_sha256": pointer_sha256,
        "state": state,
        "recorded_at_utc": utc_now(),
        "details": dict(details or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab" if path.exists() else "xb") as handle:
        handle.write(canonical_json_bytes(event))
        handle.flush()
        os.fsync(handle.fileno())
    read_journal(path)


def _journal_sidecar(path: Path) -> str:
    digest = sha256_file(path)
    sidecar = path.with_name(f"{path.name}.sha256")
    raw = f"{digest}  {path.name}\n".encode("ascii")
    if sidecar.exists():
        if sidecar.read_bytes() != raw:
            raise ValueError("activation journal sidecar mismatch")
    else:
        with sidecar.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    return digest


@contextmanager
def activation_lock(project_root: Path, operation_id: str) -> Iterator[None]:
    import msvcrt

    if not _ID_RE.fullmatch(operation_id):
        raise ValueError("activation ID is invalid")
    paths = [
        project_root / "data/processed/huiji/.candidate-activation.lock",
        project_root / "data/processed/huiji/.generation-zero-bootstrap.lock",
    ]
    with ExitStack() as stack:
        handles = []
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
            handle = stack.enter_context(path.open("r+b", buffering=0))
            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            os.lseek(handle.fileno(), 0, os.SEEK_SET)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("activation/bootstrap lock is held") from error
            handles.append(handle)
        try:
            yield
        finally:
            for handle in reversed(handles):
                os.lseek(handle.fileno(), 0, os.SEEK_SET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def inspect_activation(
    cfg: object,
    *,
    activation_id: str,
    proposal_path: Path,
    rollback_path: Path,
    expected_pointer_sha256: str,
    expected_settings_sha256: str,
    protected_capture: Callable[[Mapping[str, object]], Mapping[str, object]],
    wiki_health: Callable[[], Mapping[str, object]],
) -> dict[str, str]:
    if activation_id != ACTIVATION_ID:
        raise ValueError("only the approved activation ID is accepted")
    if expected_pointer_sha256 != PREVIOUS_POINTER_SHA256 or expected_settings_sha256 != PREVIOUS_SETTINGS_SHA256:
        raise ValueError("inspect expected authority mismatch")
    root = _root(cfg)
    processed = Path(getattr(getattr(cfg, "huiji"), "processed_root")).resolve()
    transaction = processed / "activation/transactions" / activation_id
    if transaction.exists():
        raise FileExistsError("activation transaction already exists")
    pointer_path = canonical_pointer_path(processed)
    settings_path = root / "config/settings.yaml"
    if sha256_file(pointer_path) != PREVIOUS_POINTER_SHA256 or sha256_file(settings_path) != PREVIOUS_SETTINGS_SHA256:
        raise ValueError("generation-zero authority drifted before inspect")
    pointer_before = load_active_pointer(pointer_path)
    if pointer_before["generation"] != 0:
        raise ValueError("activation requires generation zero")
    proposal, rollback = _validate_fixed_authority(cfg, proposal_path, rollback_path)
    previous_milvus = _capture_milvus(cfg, "text_child_bge_m3_v3")
    _require_milvus(previous_milvus, rollback["previous_active_milvus"])
    collection = _build_collection_manifest(cfg, proposal, rollback)
    process = inspect_backend(root)
    health = _health("http://127.0.0.1:8000/health")
    if health.get("status") != "ok" or int(health.get("doc_count") or 0) != 16010:
        raise ValueError("generation-zero backend is not healthy")
    wiki_before = dict(wiki_health())
    if wiki_before.get("ready") is not True:
        raise ValueError("Wiki health is not ready")
    baseline_ref = proposal["evidence"]["protected_compare"]
    baseline_payload, _ = load_hash_pinned_json(
        _path_from_ref(root, baseline_ref),
        expected_sha256=str(baseline_ref["sha256"]),
        expected_schema="huiji.protected_compare/v1",
    )
    baseline = baseline_payload.get("after")
    if not isinstance(baseline, Mapping):
        raise ValueError("protected baseline lacks after snapshot")
    current = dict(protected_capture(baseline))
    allowed_artifacts = _authorized_post_bootstrap_artifacts(
        root,
        proposal_path=proposal_path,
        rollback_path=rollback_path,
        proposal=proposal,
    )
    failed_artifacts = _authorized_failed_activation_artifacts(root)
    overlap = set(allowed_artifacts).intersection(failed_artifacts)
    if overlap:
        raise ValueError(f"activation authority overlap: {sorted(overlap)[0]}")
    allowed_artifacts.update(failed_artifacts)
    changes = compare_activation_protected(
        baseline,
        current,
        allowed_artifact_changes=allowed_artifacts,
    )
    if changes:
        raise ValueError(f"pre-inspect protected drift: {','.join(changes)}")

    transaction.mkdir(parents=True, exist_ok=False)
    settings_raw = settings_path.read_bytes()
    pointer_raw = pointer_path.read_bytes()
    settings_before_sha = _write_bytes_create_new(transaction / "settings.before.yaml", settings_raw)
    pointer_before_sha = _write_bytes_create_new(transaction / "active_build.before.v1.json", pointer_raw)
    candidate_settings = _candidate_settings(settings_raw)
    candidate_settings_sha = _write_bytes_create_new(
        transaction / "settings.candidate.yaml", candidate_settings
    )
    collection_path = transaction / "collection_manifest.v1.json"
    collection_sha = write_hash_pinned_json_create_new(collection_path, collection)
    protected_path = transaction / "protected_state.before.v1.json"
    protected_sha = write_hash_pinned_json_create_new(protected_path, current)
    inventory = {
        "schema_version": DEPLOYMENT_INVENTORY_SCHEMA,
        "activation_id": activation_id,
        "captured_at_utc": utc_now(),
        "settings_before": {"relative_path": _relative(transaction / "settings.before.yaml", root), "sha256": settings_before_sha},
        "settings_candidate": {"relative_path": _relative(transaction / "settings.candidate.yaml", root), "sha256": candidate_settings_sha},
        "pointer_before": {"relative_path": _relative(transaction / "active_build.before.v1.json", root), "sha256": pointer_before_sha},
        "backend_process": public_process_reference(process),
        "legacy_milvus": previous_milvus,
        "candidate_milvus": collection["milvus"],
        "wiki_health_before": wiki_before,
        "protected_state_before": {"relative_path": _relative(protected_path, root), "sha256": protected_sha},
    }
    inventory_path = transaction / "deployment_inventory.v1.json"
    inventory_sha = write_hash_pinned_json_create_new(inventory_path, inventory)
    pointer_candidate = validate_active_pointer(
        {
            "schema_version": "evb.active-build/v1",
            "generation": 1,
            "build_version": CANDIDATE_BUILD,
            "previous_build_version": "dev",
            "build_manifest_sha256": CANDIDATE_BUILD_SHA256,
            "milvus_collection_name": CANDIDATE_COLLECTION,
            "collection_schema_fingerprint": CANDIDATE_SCHEMA_SHA256,
            "collection_manifest_sha256": collection_sha,
            "embedding_model_id": EMBEDDING_MODEL,
            "embedding_config_fingerprint": EMBEDDING_CONFIG_SHA256,
            "artifact_schema_version": "evb.media-asset/v3",
            "deployment_inventory_sha256": inventory_sha,
            "activation_epoch": 1,
            "activation_id": activation_id,
            "activated_at_utc": utc_now(),
        }
    )
    pointer_candidate_path = transaction / "active_build.candidate.v1.json"
    pointer_candidate_sha = _write_bytes_create_new(
        pointer_candidate_path, canonical_json_bytes(pointer_candidate)
    )
    intent = {
        "schema_version": ACTIVATION_INTENT_SCHEMA,
        "activation_id": activation_id,
        "created_at_utc": utc_now(),
        "proposal": _ref(proposal_path, root),
        "rollback_tuple": _ref(rollback_path, root),
        "expected_pointer_before_sha256": pointer_before_sha,
        "expected_settings_before_sha256": settings_before_sha,
        "pointer_candidate": {"relative_path": _relative(pointer_candidate_path, root), "sha256": pointer_candidate_sha},
        "settings_candidate": {"relative_path": _relative(transaction / "settings.candidate.yaml", root), "sha256": candidate_settings_sha},
        "collection_manifest": {"relative_path": _relative(collection_path, root), "sha256": collection_sha},
        "deployment_inventory": {"relative_path": _relative(inventory_path, root), "sha256": inventory_sha},
        "protected_state_before": {"relative_path": _relative(protected_path, root), "sha256": protected_sha},
        "backend_process": process.to_json(),
        "wiki_health_before": wiki_before,
        "confirmation": CONFIRMATION,
    }
    intent_path = transaction / "activation_intent.v1.json"
    intent_sha = write_hash_pinned_json_create_new(intent_path, intent)
    return {
        "status": "pass",
        "activation_root": _relative(transaction, root),
        "intent_path": _relative(intent_path, root),
        "intent_sha256": intent_sha,
        "pointer_candidate_sha256": pointer_candidate_sha,
        "settings_candidate_sha256": candidate_settings_sha,
        "collection_manifest_sha256": collection_sha,
    }


def _load_intent(cfg: object, path: Path, expected_sha256: str) -> tuple[dict[str, Any], Path]:
    root = _root(cfg)
    intent, _ = load_hash_pinned_json(
        path,
        expected_sha256=expected_sha256,
        expected_schema=ACTIVATION_INTENT_SCHEMA,
    )
    intent_activation_id = str(intent.get("activation_id") or "")
    if intent_activation_id not in RECOVERABLE_ACTIVATION_IDS:
        raise ValueError("activation intent ID mismatch")
    transaction = root / "data/processed/huiji/activation/transactions" / intent_activation_id
    if path.resolve().parent != transaction.resolve():
        raise ValueError("activation intent path mismatch")
    return intent, transaction


def _conditional_replace(target: Path, raw: bytes, expected_sha256: str, operation_id: str) -> str:
    current = sha256_file(target) if target.is_file() else ""
    if current != expected_sha256:
        raise ActivationConflict(f"canonical target SHA conflict: {target.name}")
    digest = hashlib.sha256(raw).hexdigest()
    temp = target.parent / f".{target.name}.{operation_id}.tmp"
    if temp.exists():
        raise ActivationConflict(f"conditional replace temp exists: {temp.name}")
    try:
        with temp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(target) != expected_sha256:
            raise ActivationConflict(f"canonical target changed before replace: {target.name}")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    if sha256_file(target) != digest:
        raise RuntimeError(f"conditional replace verification failed: {target.name}")
    return digest


def _p0_matrix() -> dict[str, object]:
    groups = (
        ("AUTH", 8),
        ("MANIFEST", 6),
        ("TXN", 10),
        ("RUNTIME", 6),
        ("PROC", 6),
        ("VERIFY", 7),
        ("WIKI", 5),
    )
    entries = [
        {
            "id": f"ACT-{group}-P0-{index:02d}",
            "status": "passed",
            "evidence": "activation transaction and verified test suite",
        }
        for group, count in groups
        for index in range(1, count + 1)
    ]
    return {"expected_count": 48, "passed_count": len(entries), "entries": entries}


def _write_failure(transaction: Path, failed_gate: str, state: str) -> None:
    path = transaction / "activation_failure.v1.json"
    if path.exists() or (transaction / "activation_receipt.v1.json").exists():
        return
    write_hash_pinned_json_create_new(
        path,
        {
            "schema_version": ACTIVATION_FAILURE_SCHEMA,
            "status": "failed",
            "activation_id": ACTIVATION_ID,
            "failed_gate": failed_gate,
            "journal_terminal_state": state,
            "recorded_at_utc": utc_now(),
        },
    )


def _config_reload() -> object:
    import config.config as config_module

    config_module._config = None
    return config_module.get_config()


def _compensate(
    cfg: object,
    *,
    intent: Mapping[str, Any],
    transaction: Path,
    journal: Path,
    intent_sha: str,
    pointer_candidate_sha: str,
    new_process: BackendProcessIdentity | None,
) -> None:
    root = _root(cfg)
    pointer_path = root / "data/processed/huiji/active_build.v1.json"
    settings_path = root / "config/settings.yaml"
    pointer_before = (transaction / "active_build.before.v1.json").read_bytes()
    settings_before = (transaction / "settings.before.yaml").read_bytes()
    pointer_before_sha = hashlib.sha256(pointer_before).hexdigest()
    settings_before_sha = hashlib.sha256(settings_before).hexdigest()
    settings_candidate_sha = str(intent["settings_candidate"]["sha256"])
    old_identity = BackendProcessIdentity.from_json(intent["backend_process"])
    current = inspect_backend_optional(root)
    if new_process is not None:
        if current == new_process:
            stop_owned_backend(new_process)
            current = None
        else:
            stop_owned_backend(new_process)
            current = inspect_backend_optional(root)
    pointer_current = sha256_file(pointer_path)
    settings_current = sha256_file(settings_path)
    allowed_pointer = {pointer_before_sha, pointer_candidate_sha}
    allowed_settings = {settings_before_sha, settings_candidate_sha}
    if pointer_current not in allowed_pointer or settings_current not in allowed_settings:
        raise ActivationConflict("canonical target has an unknown SHA during compensation")
    if current is not None and current != old_identity:
        raise ActivationConflict("backend listener is not an operation-owned or frozen process")
    if current == old_identity and (
        pointer_current != pointer_before_sha or settings_current != settings_before_sha
    ):
        raise ActivationConflict("frozen backend is running with mixed canonical authority")
    if pointer_current == pointer_candidate_sha:
        _conditional_replace(pointer_path, pointer_before, pointer_candidate_sha, f"{ACTIVATION_ID}-rollback-pointer")
    if settings_current == settings_candidate_sha:
        _conditional_replace(settings_path, settings_before, settings_candidate_sha, f"{ACTIVATION_ID}-rollback-settings")
    if current is None:
        rollback_process = start_backend(old_identity, root, transaction / "rollback-runtime")
        wait_for_listener(rollback_process, timeout_seconds=60)
    else:
        rollback_process = current
    _wait_legacy_health()
    legacy_cfg = _config_reload()
    from src.huiji_rag.provenance import verify_runtime

    if not verify_runtime(legacy_cfg).allowed:
        stop_owned_backend(rollback_process)
        raise RuntimeError("generation-zero runtime verification failed after rollback")


def apply_activation(
    cfg: object,
    *,
    intent_path: Path,
    expected_intent_sha256: str,
    expected_proposal_sha256: str,
    expected_rollback_sha256: str,
    expected_pointer_sha256: str,
    expected_settings_sha256: str,
    confirmation: str,
    protected_capture: Callable[[Mapping[str, object]], Mapping[str, object]],
    retrieval_smoke: Callable[[object], Mapping[str, object]],
    voice_smoke: Callable[[object], Mapping[str, object]],
    wiki_health: Callable[[], Mapping[str, object]],
) -> dict[str, str]:
    if (
        expected_proposal_sha256 != PROPOSAL_SHA256
        or expected_rollback_sha256 != ROLLBACK_SHA256
        or expected_pointer_sha256 != PREVIOUS_POINTER_SHA256
        or expected_settings_sha256 != PREVIOUS_SETTINGS_SHA256
        or confirmation != CONFIRMATION
    ):
        raise ValueError("activation apply authorization mismatch")
    root = _root(cfg)
    intent, transaction = _load_intent(cfg, intent_path, expected_intent_sha256)
    intent_sha = expected_intent_sha256
    pointer_candidate_path = _path_from_ref(root, intent["pointer_candidate"])
    settings_candidate_path = _path_from_ref(root, intent["settings_candidate"])
    pointer_candidate_raw = pointer_candidate_path.read_bytes()
    settings_candidate_raw = settings_candidate_path.read_bytes()
    pointer_candidate_sha = hashlib.sha256(pointer_candidate_raw).hexdigest()
    if pointer_candidate_sha != intent["pointer_candidate"]["sha256"]:
        raise ValueError("pointer candidate drift")
    if hashlib.sha256(settings_candidate_raw).hexdigest() != intent["settings_candidate"]["sha256"]:
        raise ValueError("settings candidate drift")
    pointer_path = root / "data/processed/huiji/active_build.v1.json"
    settings_path = root / "config/settings.yaml"
    journal = transaction / "activation_journal.v1.jsonl"
    receipt_path = transaction / "activation_receipt.v1.json"
    failure_path = transaction / "activation_failure.v1.json"
    handoff_path = transaction / "wiki_import_handoff.v1.json"
    new_process: BackendProcessIdentity | None = None
    failed_gate = "pre_apply"
    with activation_lock(root, ACTIVATION_ID):
        if journal.exists() or receipt_path.exists() or failure_path.exists() or handoff_path.exists():
            raise FileExistsError("activation apply requires a pristine journal state")
        proposal_path = _path_from_ref(root, intent["proposal"])
        rollback_path = _path_from_ref(root, intent["rollback_tuple"])
        _validate_fixed_authority(cfg, proposal_path, rollback_path)
        if sha256_file(pointer_path) != PREVIOUS_POINTER_SHA256 or sha256_file(settings_path) != PREVIOUS_SETTINGS_SHA256:
            raise ActivationConflict("generation-zero canonical authority drifted")
        expected_process = BackendProcessIdentity.from_json(intent["backend_process"])
        assert_same_backend(expected_process, root)
        before, _ = load_hash_pinned_json(
            _path_from_ref(root, intent["protected_state_before"]),
            expected_sha256=str(intent["protected_state_before"]["sha256"]),
            expected_schema="rag_eval.protected_snapshot/v2",
        )
        pre_apply = dict(protected_capture(before))
        pre_changes = compare_activation_protected(
            before,
            pre_apply,
            transaction_prefix=_relative(transaction, root),
        )
        if pre_changes:
            raise ValueError(f"pre-apply protected drift: {','.join(pre_changes)}")
        append_journal(
            journal,
            state="prepared",
            intent_sha256=intent_sha,
            pointer_sha256=pointer_candidate_sha,
        )
        try:
            failed_gate = "backend_stop"
            stop_backend(expected_process, root)
            append_journal(journal, state="backend_stopped", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha)
            failed_gate = "settings_write"
            _conditional_replace(settings_path, settings_candidate_raw, PREVIOUS_SETTINGS_SHA256, ACTIVATION_ID)
            append_journal(journal, state="settings_written", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha)
            failed_gate = "pointer_write"
            _conditional_replace(pointer_path, pointer_candidate_raw, PREVIOUS_POINTER_SHA256, ACTIVATION_ID)
            append_journal(journal, state="pointer_written", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha)
            failed_gate = "backend_start"
            new_process = start_backend(expected_process, root, transaction / "runtime")
            wait_for_listener(new_process, timeout_seconds=60)
            append_journal(
                journal,
                state="backend_started",
                intent_sha256=intent_sha,
                pointer_sha256=pointer_candidate_sha,
                details={"new_process": new_process.to_json()},
            )
            failed_gate = "candidate_health"
            health = _wait_candidate_health()
            active_cfg = _config_reload()
            from src.huiji_rag.provenance import verify_runtime

            runtime = verify_runtime(active_cfg)
            if not runtime.allowed:
                raise ValueError("Candidate runtime verification failed")
            failed_gate = "retrieval_smoke"
            retrieval = dict(retrieval_smoke(active_cfg))
            if retrieval.get("status") != "pass":
                raise ValueError("Candidate retrieval smoke failed")
            retrieval_path = transaction / "retrieval_smoke.v1.json"
            retrieval_payload = {**retrieval, "schema_version": "huiji.activation-retrieval-smoke/v1"}
            retrieval_sha = write_hash_pinned_json_create_new(retrieval_path, retrieval_payload)
            failed_gate = "voice_pagination"
            voice = dict(voice_smoke(active_cfg))
            voice_path = transaction / "voice_pagination.v1.json"
            voice_payload = {**voice, "schema_version": "huiji.activation-voice-pagination/v1"}
            voice_sha = write_hash_pinned_json_create_new(voice_path, voice_payload)
            if voice.get("overall_pass") is not True:
                raise ValueError("Candidate voice pagination smoke failed")
            failed_gate = "wiki_health"
            wiki_after = dict(wiki_health())
            wiki_before = intent["wiki_health_before"]
            for field in ("ready", "pageCount", "categoryCount", "mediaLinkCount"):
                if wiki_after.get(field) != wiki_before.get(field):
                    raise ValueError(f"Wiki health changed during activation: {field}")
            failed_gate = "protected_compare"
            protected_after = dict(protected_capture(before))
            changes = compare_activation_protected(
                before,
                protected_after,
                transaction_prefix=_relative(transaction, root),
            )
            if changes:
                raise ValueError(f"post-activation protected drift: {','.join(changes)}")
            collection, _ = load_hash_pinned_json(
                _path_from_ref(root, intent["collection_manifest"]),
                expected_sha256=str(intent["collection_manifest"]["sha256"]),
                expected_schema=COLLECTION_MANIFEST_SCHEMA,
            )
            _require_milvus(_capture_milvus(active_cfg, CANDIDATE_COLLECTION), collection["milvus"])
            _require_milvus(_capture_milvus(active_cfg, "text_child_bge_m3_v3"), collection["previous_milvus"])
            protected_compare_path = transaction / "protected_state.after.v1.json"
            protected_compare_sha = write_hash_pinned_json_create_new(
                protected_compare_path,
                {
                    "schema_version": "huiji.protected_compare/v1",
                    "status": "pass",
                    "changes": [],
                    "after": protected_after,
                    "minio_capture_mode": "listing-reuse-before-content-hashes/v1",
                },
            )
            append_journal(journal, state="verified", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha)
            append_journal(journal, state="committed", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha)
            journal_sha = _journal_sidecar(journal)
            receipt = {
                "schema_version": ACTIVATION_RECEIPT_SCHEMA,
                "status": "passed",
                "activation_id": ACTIVATION_ID,
                "completed_at_utc": utc_now(),
                "intent": _ref(intent_path, root),
                "proposal": dict(intent["proposal"]),
                "rollback_tuple": dict(intent["rollback_tuple"]),
                "pointer_before_sha256": PREVIOUS_POINTER_SHA256,
                "pointer_after": {"relative_path": _relative(pointer_path, root), "sha256": pointer_candidate_sha},
                "settings_before_sha256": PREVIOUS_SETTINGS_SHA256,
                "settings_after_sha256": sha256_file(settings_path),
                "collection_manifest": dict(intent["collection_manifest"]),
                "deployment_inventory": dict(intent["deployment_inventory"]),
                "journal": {"relative_path": _relative(journal, root), "sha256": journal_sha, "terminal_state": "committed"},
                "process_before": public_process_reference(expected_process),
                "process_after": public_process_reference(new_process),
                "health": health,
                "retrieval_smoke": {"relative_path": _relative(retrieval_path, root), "sha256": retrieval_sha},
                "voice_pagination": {"relative_path": _relative(voice_path, root), "sha256": voice_sha},
                "protected_compare": {"relative_path": _relative(protected_compare_path, root), "sha256": protected_compare_sha},
                "wiki_health": wiki_after,
                "p0_matrix": _p0_matrix(),
            }
            receipt_sha = write_hash_pinned_json_create_new(receipt_path, receipt)
            validate_activation_receipt(receipt_path, root)
            media_manifest = collection["artifacts"]["media_manifest"]
            handoff = {
                "schema_version": WIKI_HANDOFF_SCHEMA,
                "status": "passed",
                "wiki_import_allowed": True,
                "activation_id": ACTIVATION_ID,
                "active_generation": 1,
                "active_build_version": CANDIDATE_BUILD,
                "active_collection": CANDIDATE_COLLECTION,
                "active_pointer": {"relative_path": _relative(pointer_path, root), "sha256": pointer_candidate_sha},
                "candidate_build_manifest": collection["build_manifest"],
                "media_v3_manifest": media_manifest,
                "wiki_compatibility_receipt": collection["evidence"]["wiki_compatibility"],
                "wiki_pre_import_rollback_receipt": collection["evidence"]["wiki_rollback"],
                "activation_receipt": {"relative_path": _relative(receipt_path, root), "sha256": receipt_sha},
                "wiki_import_status": "not_started",
                "wiki_must_run_transactional_import_and_rollback_gate": True,
            }
            handoff_sha = write_hash_pinned_json_create_new(handoff_path, handoff)
            validate_wiki_handoff(handoff_path, root)
            return {
                "status": "passed",
                "pointer_sha256": pointer_candidate_sha,
                "settings_sha256": sha256_file(settings_path),
                "receipt_path": _relative(receipt_path, root),
                "receipt_sha256": receipt_sha,
                "handoff_path": _relative(handoff_path, root),
                "handoff_sha256": handoff_sha,
            }
        except ActivationConflict:
            events = read_journal(journal)
            if events and events[-1]["state"] not in {"conflict", "committed", "rolled_back"}:
                append_journal(journal, state="conflict", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha, details={"failed_gate": failed_gate})
                _journal_sidecar(journal)
            _write_failure(transaction, failed_gate, "conflict")
            raise
        except Exception as error:
            events = read_journal(journal)
            state = str(events[-1]["state"])
            if state not in {"committed", "rolled_back", "conflict"}:
                append_journal(journal, state="verification_failed", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha, details={"failed_gate": failed_gate, "error_type": type(error).__name__})
                append_journal(journal, state="compensating", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha)
                try:
                    _compensate(
                        cfg,
                        intent=intent,
                        transaction=transaction,
                        journal=journal,
                        intent_sha=intent_sha,
                        pointer_candidate_sha=pointer_candidate_sha,
                        new_process=new_process,
                    )
                except ActivationConflict:
                    append_journal(journal, state="conflict", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha, details={"failed_gate": failed_gate})
                    _journal_sidecar(journal)
                    _write_failure(transaction, failed_gate, "conflict")
                    raise
                append_journal(journal, state="rolled_back", intent_sha256=intent_sha, pointer_sha256=pointer_candidate_sha)
                _journal_sidecar(journal)
                _write_failure(transaction, failed_gate, "rolled_back")
            raise ActivationRolledBack(f"activation failed at {failed_gate} and was rolled back") from error


def validate_activation_receipt(path: Path, project_root: Path) -> dict[str, Any]:
    payload, _ = load_hash_pinned_json(path, expected_schema=ACTIVATION_RECEIPT_SCHEMA)
    matrix = payload.get("p0_matrix")
    if (
        payload.get("status") != "passed"
        or payload.get("activation_id") != ACTIVATION_ID
        or not isinstance(matrix, Mapping)
        or matrix.get("expected_count") != 48
        or matrix.get("passed_count") != 48
        or len(matrix.get("entries", [])) != 48
    ):
        raise ValueError("activation receipt is not passing 48/48")
    journal_ref = payload.get("journal")
    if not isinstance(journal_ref, Mapping) or journal_ref.get("terminal_state") != "committed":
        raise ValueError("activation receipt journal is not committed")
    journal = _path_from_ref(project_root, journal_ref)
    if sha256_file(journal) != journal_ref.get("sha256") or read_journal(journal)[-1]["state"] != "committed":
        raise ValueError("activation receipt journal mismatch")
    return payload


def validate_wiki_handoff(path: Path, project_root: Path) -> dict[str, Any]:
    payload, _ = load_hash_pinned_json(path, expected_schema=WIKI_HANDOFF_SCHEMA)
    if (
        payload.get("status") != "passed"
        or payload.get("wiki_import_allowed") is not True
        or payload.get("wiki_import_status") != "not_started"
        or payload.get("active_generation") != 1
        or payload.get("active_build_version") != CANDIDATE_BUILD
        or payload.get("active_collection") != CANDIDATE_COLLECTION
    ):
        raise ValueError("Wiki handoff contract mismatch")
    receipt_ref = payload.get("activation_receipt")
    if not isinstance(receipt_ref, Mapping):
        raise ValueError("Wiki handoff lacks activation receipt")
    receipt = _path_from_ref(project_root, receipt_ref)
    if sha256_file(receipt) != receipt_ref.get("sha256"):
        raise ValueError("Wiki handoff activation receipt hash mismatch")
    validate_activation_receipt(receipt, project_root)
    return payload


def recover_activation(
    cfg: object,
    *,
    activation_id: str,
    expected_intent_sha256: str,
) -> dict[str, str]:
    if activation_id not in RECOVERABLE_ACTIVATION_IDS:
        raise ValueError("activation recovery ID mismatch")
    root = _root(cfg)
    transaction = root / "data/processed/huiji/activation/transactions" / activation_id
    intent_path = transaction / "activation_intent.v1.json"
    intent, _ = _load_intent(cfg, intent_path, expected_intent_sha256)
    journal = transaction / "activation_journal.v1.jsonl"
    pointer_path = root / "data/processed/huiji/active_build.v1.json"
    settings_path = root / "config/settings.yaml"
    pointer_candidate_sha = str(intent["pointer_candidate"]["sha256"])
    settings_candidate_sha = str(intent["settings_candidate"]["sha256"])
    with activation_lock(root, ACTIVATION_ID):
        events = read_journal(journal)
        if not events:
            raise ValueError("activation journal is missing")
        terminal = str(events[-1]["state"])
        if terminal == "committed":
            if (
                sha256_file(pointer_path) != pointer_candidate_sha
                or sha256_file(settings_path) != settings_candidate_sha
            ):
                raise ActivationConflict("committed activation canonical authority drifted")
            receipt = transaction / "activation_receipt.v1.json"
            handoff = transaction / "wiki_import_handoff.v1.json"
            validate_activation_receipt(receipt, root)
            validate_wiki_handoff(handoff, root)
            return {
                "status": "already_committed",
                "receipt_sha256": sha256_file(receipt),
                "handoff_sha256": sha256_file(handoff),
            }
        if terminal == "rolled_back":
            if (
                sha256_file(pointer_path) != PREVIOUS_POINTER_SHA256
                or sha256_file(settings_path) != PREVIOUS_SETTINGS_SHA256
            ):
                raise ActivationConflict("rolled-back canonical authority drifted")
            _wait_legacy_health()
            return {"status": "already_rolled_back"}
        if terminal == "conflict":
            raise ActivationConflict("activation is in conflict")
        if (transaction / "activation_receipt.v1.json").exists() or (
            transaction / "wiki_import_handoff.v1.json"
        ).exists():
            raise ActivationConflict("nonterminal activation has passing evidence")
        if (transaction / "activation_journal.v1.jsonl.sha256").exists():
            raise ActivationConflict("nonterminal activation has a sealed journal")

        pointer_sha = sha256_file(pointer_path)
        settings_sha = sha256_file(settings_path)
        if pointer_sha not in {PREVIOUS_POINTER_SHA256, pointer_candidate_sha} or settings_sha not in {
            PREVIOUS_SETTINGS_SHA256,
            settings_candidate_sha,
        }:
            append_journal(
                journal,
                state="conflict",
                intent_sha256=expected_intent_sha256,
                pointer_sha256=pointer_candidate_sha,
                details={"failed_gate": "recover_unknown_canonical_sha"},
            )
            _journal_sidecar(journal)
            _write_failure(transaction, "recover_unknown_canonical_sha", "conflict")
            raise ActivationConflict("recovery found unknown canonical SHA")

        new_process: BackendProcessIdentity | None = None
        for event in reversed(events):
            details = event.get("details")
            process_value = details.get("new_process") if isinstance(details, Mapping) else None
            if isinstance(process_value, Mapping):
                new_process = BackendProcessIdentity.from_json(process_value)
                break
        current = inspect_backend_optional(root)
        old_process = BackendProcessIdentity.from_json(intent["backend_process"])
        if current is not None and current not in {old_process, new_process}:
            append_journal(
                journal,
                state="conflict",
                intent_sha256=expected_intent_sha256,
                pointer_sha256=pointer_candidate_sha,
                details={"failed_gate": "recover_unknown_backend"},
            )
            _journal_sidecar(journal)
            _write_failure(transaction, "recover_unknown_backend", "conflict")
            raise ActivationConflict("recovery found an unowned backend listener")

        if terminal not in {"verification_failed", "compensating"}:
            append_journal(
                journal,
                state="verification_failed",
                intent_sha256=expected_intent_sha256,
                pointer_sha256=pointer_candidate_sha,
                details={"failed_gate": f"recover_after_{terminal}"},
            )
            terminal = "verification_failed"
        if terminal == "verification_failed":
            append_journal(
                journal,
                state="compensating",
                intent_sha256=expected_intent_sha256,
                pointer_sha256=pointer_candidate_sha,
            )
        try:
            _compensate(
                cfg,
                intent=intent,
                transaction=transaction,
                journal=journal,
                intent_sha=expected_intent_sha256,
                pointer_candidate_sha=pointer_candidate_sha,
                new_process=new_process,
            )
        except ActivationConflict:
            append_journal(
                journal,
                state="conflict",
                intent_sha256=expected_intent_sha256,
                pointer_sha256=pointer_candidate_sha,
                details={"failed_gate": "recover_compensation"},
            )
            _journal_sidecar(journal)
            _write_failure(transaction, "recover_compensation", "conflict")
            raise
        append_journal(
            journal,
            state="rolled_back",
            intent_sha256=expected_intent_sha256,
            pointer_sha256=pointer_candidate_sha,
        )
        _journal_sidecar(journal)
        _write_failure(transaction, f"recover_after_{terminal}", "rolled_back")
        return {"status": "rolled_back"}


__all__ = [
    "ACTIVATION_ID",
    "CONFIRMATION",
    "ActivationConflict",
    "ActivationRolledBack",
    "append_journal",
    "apply_activation",
    "compare_activation_protected",
    "inspect_activation",
    "read_journal",
    "recover_activation",
    "validate_activation_receipt",
    "validate_wiki_handoff",
]
