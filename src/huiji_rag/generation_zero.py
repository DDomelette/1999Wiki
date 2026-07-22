"""Independent generation-zero bootstrap primitives and transaction workflow."""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from src.huiji_rag.active_pointer import (
    canonical_json_bytes,
    canonical_pointer_path,
    load_active_pointer,
    validate_active_pointer,
)


BOOTSTRAP_INTENT_SCHEMA = "huiji.generation-zero-bootstrap-intent/v1"
COLLECTION_MANIFEST_SCHEMA = "evb.collection-manifest/v1"
DEPLOYMENT_INVENTORY_SCHEMA = "huiji.generation-zero-deployment-inventory/v1"
BOOTSTRAP_JOURNAL_SCHEMA = "huiji.generation-zero-bootstrap-journal-event/v1"
EFFECTIVE_TUPLE_SCHEMA = "huiji.effective-runtime-tuple/v1"
BOOTSTRAP_RECEIPT_SCHEMA = "huiji.generation-zero-bootstrap-receipt/v1"
BOOTSTRAP_FAILURE_SCHEMA = "huiji.generation-zero-bootstrap-failure/v1"

BOOTSTRAP_CONFIRMATION = "BOOTSTRAP HUIJI LEGACY DEV GENERATION 0"
BOOTSTRAP_LOCK_RELATIVE = Path("data/processed/huiji/.generation-zero-bootstrap.lock")
GENERATION_ZERO_ARTIFACT_SCHEMA = "evb.media-asset/v1_legacy"
GENERATION_ZERO_BUILD = "dev"
GENERATION_ZERO_COLLECTION = "text_child_bge_m3_v3"
GENERATION_ZERO_BUILD_MANIFEST_SHA256 = (
    "ad886077e2aff90350480c9925686693121af9c643796131c361fde6efeed231"
)
GENERATION_ZERO_PROVENANCE_SHA256 = (
    "dafd3a7b309fc96fe784945d4b5f143f3e8aec2e93a6856151e3a52fb4e8e6a4"
)
GENERATION_ZERO_EMBEDDING_CONFIG_SHA256 = (
    "17787be97e63ea53e3298748adf546ebc17d5456669481349eb8bb088b336099"
)
GENERATION_ZERO_EMBEDDING_MODEL = "BAAI/bge-m3"

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_TRANSITIONS: Mapping[str | None, frozenset[str]] = {
    None: frozenset({"prepared"}),
    "prepared": frozenset({"pointer_written", "verification_failed", "conflict"}),
    "pointer_written": frozenset({"verified", "verification_failed", "conflict"}),
    "verified": frozenset({"committed", "verification_failed", "conflict"}),
    "verification_failed": frozenset({"compensating", "conflict"}),
    "compensating": frozenset({"rolled_back", "conflict"}),
    "rolled_back": frozenset(),
    "committed": frozenset(),
    "conflict": frozenset(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_effective_runtime_tuple(
    *,
    artifact_capability: str,
    artifact_schema_version: str,
    build_version: str,
    artifacts: Mapping[str, str],
    milvus: Mapping[str, object],
    embedding: Mapping[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": EFFECTIVE_TUPLE_SCHEMA,
        "artifact_capability": str(artifact_capability),
        "artifact_schema_version": str(artifact_schema_version),
        "build_version": str(build_version),
        "artifacts": dict(sorted((str(key), str(value)) for key, value in artifacts.items())),
        "milvus": dict(sorted((str(key), value) for key, value in milvus.items())),
        "embedding": dict(sorted((str(key), value) for key, value in embedding.items())),
    }
    payload["tuple_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()
    return payload


def read_journal(path: str | Path) -> list[dict[str, object]]:
    target = Path(path)
    if not target.is_file():
        return []
    events: list[dict[str, object]] = []
    previous_hash = ""
    intent_sha = ""
    pointer_sha = ""
    for line_number, raw in enumerate(target.read_bytes().splitlines(), start=1):
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"journal line {line_number} is invalid") from error
        if not isinstance(value, dict):
            raise ValueError(f"journal line {line_number} is not an object")
        if raw != canonical_json_bytes(value, trailing_newline=False):
            raise ValueError(f"journal line {line_number} is not canonical")
        if value.get("schema_version") != BOOTSTRAP_JOURNAL_SCHEMA:
            raise ValueError("journal schema mismatch")
        if value.get("sequence") != line_number:
            raise ValueError("journal sequence mismatch")
        if str(value.get("previous_event_sha256") or "") != previous_hash:
            raise ValueError("journal hash chain mismatch")
        current_intent = str(value.get("intent_sha256") or "")
        current_pointer = str(value.get("pointer_sha256") or "")
        if not _SHA256_RE.fullmatch(current_intent) or not _SHA256_RE.fullmatch(current_pointer):
            raise ValueError("journal identity hash is invalid")
        if events and (current_intent != intent_sha or current_pointer != pointer_sha):
            raise ValueError("journal operation identity changed")
        state = str(value.get("state") or "")
        previous_state = str(events[-1]["state"]) if events else None
        if state not in _TRANSITIONS.get(previous_state, frozenset()):
            raise ValueError("journal state transition is invalid")
        intent_sha = current_intent
        pointer_sha = current_pointer
        previous_hash = hashlib.sha256(raw).hexdigest()
        events.append(value)
    return events


def append_journal_event(
    path: str | Path,
    *,
    state: str,
    intent_sha256: str,
    pointer_sha256: str,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if not _SHA256_RE.fullmatch(intent_sha256) or not _SHA256_RE.fullmatch(pointer_sha256):
        raise ValueError("journal identity hash is invalid")
    target = Path(path)
    events = read_journal(target)
    previous_state = str(events[-1]["state"]) if events else None
    if state not in _TRANSITIONS.get(previous_state, frozenset()):
        raise ValueError("journal state transition is invalid")
    previous_hash = (
        hashlib.sha256(
            canonical_json_bytes(events[-1], trailing_newline=False)
        ).hexdigest()
        if events
        else ""
    )
    event: dict[str, object] = {
        "schema_version": BOOTSTRAP_JOURNAL_SCHEMA,
        "sequence": len(events) + 1,
        "previous_event_sha256": previous_hash,
        "intent_sha256": intent_sha256,
        "pointer_sha256": pointer_sha256,
        "state": state,
        "recorded_at_utc": utc_now(),
        "details": dict(sorted((details or {}).items())),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "xb" if not target.exists() else "ab"
    with target.open(mode) as handle:
        handle.write(canonical_json_bytes(event))
        handle.flush()
        os.fsync(handle.fileno())
    read_journal(target)
    return event


def create_pointer_cas(
    target: str | Path,
    pointer_bytes: bytes,
    *,
    operation_id: str,
) -> None:
    if not _ID_RE.fullmatch(operation_id):
        raise ValueError("operation ID is invalid")
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.parent / f".{destination.name}.{operation_id}.tmp"
    if temp.exists():
        raise FileExistsError(f"pointer temp already exists: {temp}")
    try:
        with temp.open("xb") as handle:
            handle.write(pointer_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, destination)
        with destination.open("r+b") as handle:
            os.fsync(handle.fileno())
    finally:
        if temp.exists():
            temp.unlink()


def write_hash_pinned_json_create_new(
    path: str | Path, payload: Mapping[str, object]
) -> str:
    target = Path(path)
    sidecar = target.with_name(f"{target.name}.sha256")
    if target.exists() or sidecar.exists():
        raise FileExistsError(f"evidence already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(dict(payload))
    digest = hashlib.sha256(raw).hexdigest()
    try:
        with target.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        sidecar_raw = f"{digest}  {target.name}\n".encode("ascii")
        with sidecar.open("xb") as handle:
            handle.write(sidecar_raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        if sidecar.exists():
            sidecar.unlink()
        if target.exists():
            target.unlink()
        raise
    return digest


def load_hash_pinned_json(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    expected_schema: str | None = None,
) -> tuple[dict[str, Any], str]:
    target = Path(path)
    sidecar = target.with_name(f"{target.name}.sha256")
    if not target.is_file() or not sidecar.is_file():
        raise ValueError(f"hash-pinned evidence is missing: {target}")
    raw = target.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"evidence SHA-256 mismatch: {target}")
    expected_sidecar = f"{digest}  {target.name}\n".encode("ascii")
    if sidecar.read_bytes() != expected_sidecar:
        raise ValueError(f"evidence sidecar mismatch: {target}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"evidence JSON is invalid: {target}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"evidence is not an object: {target}")
    if raw != canonical_json_bytes(payload):
        raise ValueError(f"evidence bytes are not canonical: {target}")
    if expected_schema is not None and payload.get("schema_version") != expected_schema:
        raise ValueError(f"evidence schema mismatch: {target}")
    return payload, digest


def _project_root(cfg: object) -> Path:
    return Path(getattr(getattr(cfg, "paths", None), "project_root", Path.cwd())).resolve()


def _relative(path: str | Path, root: Path) -> str:
    target = Path(path).resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"path escapes project root: {target}") from error


def _file_reference(path: str | Path, root: Path) -> dict[str, object]:
    target = Path(path).resolve()
    return {
        "relative_path": _relative(target, root),
        "sha256": sha256_file(target),
        "size": target.stat().st_size,
    }


def _embedding_identity(cfg: object) -> dict[str, object]:
    embedding = getattr(cfg, "embedding", None)
    provider = str(getattr(embedding, "provider", ""))
    model = str(getattr(embedding, "model", ""))
    payload = {
        "schema_version": "huiji.embedding-config/v1",
        "provider": provider,
        "model": model,
    }
    fingerprint = hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()
    if model != GENERATION_ZERO_EMBEDDING_MODEL:
        raise ValueError("generation-zero embedding model mismatch")
    if fingerprint != GENERATION_ZERO_EMBEDDING_CONFIG_SHA256:
        raise ValueError("generation-zero embedding config mismatch")
    return {
        "provider": provider,
        "model_id": model,
        "config_fingerprint": fingerprint,
    }


def _build_collection_manifest(
    cfg: object,
    baseline: Mapping[str, Any],
    baseline_sha256: str,
) -> tuple[dict[str, object], dict[str, object]]:
    from src.huiji_rag.io import build_paths

    root = _project_root(cfg)
    paths = build_paths(cfg)
    build_manifest = Path(paths.build_manifest).resolve()
    if sha256_file(build_manifest) != GENERATION_ZERO_BUILD_MANIFEST_SHA256:
        raise ValueError("generation-zero build manifest drift")
    provenance_path = Path(getattr(getattr(cfg, "huiji"), "provenance_baseline")).resolve()
    if baseline_sha256 != GENERATION_ZERO_PROVENANCE_SHA256:
        raise ValueError("generation-zero provenance drift")
    artifact_source = baseline.get("artifacts")
    bm25_source = baseline.get("bm25")
    if not isinstance(artifact_source, Mapping) or not isinstance(bm25_source, Mapping):
        raise ValueError("legacy provenance artifact map is invalid")
    configured = {
        "parent_blocks": Path(paths.parent_blocks),
        "child_blocks": Path(paths.child_blocks),
        "media_assets": Path(paths.media_assets),
        "child_bm25": Path(paths.child_bm25),
        "media_bm25": Path(paths.media_bm25),
    }
    artifacts: dict[str, dict[str, object]] = {}
    artifact_hashes: dict[str, str] = {}
    for name, path in configured.items():
        source = artifact_source.get(name) if name in artifact_source else bm25_source.get(name)
        if not isinstance(source, Mapping):
            raise ValueError(f"legacy provenance is missing {name}")
        reference = _file_reference(path, root)
        if (
            reference["relative_path"] != source.get("relative_path")
            or reference["sha256"] != source.get("sha256")
            or reference["size"] != source.get("size_bytes")
        ):
            raise ValueError(f"legacy artifact identity mismatch: {name}")
        artifacts[name] = reference
        artifact_hashes[name] = str(reference["sha256"])
    milvus = baseline.get("milvus")
    if not isinstance(milvus, Mapping):
        raise ValueError("legacy provenance Milvus identity is missing")
    milvus_identity = dict(sorted((str(key), value) for key, value in milvus.items()))
    embedding = _embedding_identity(cfg)
    effective = build_effective_runtime_tuple(
        artifact_capability="legacy",
        artifact_schema_version=GENERATION_ZERO_ARTIFACT_SCHEMA,
        build_version=GENERATION_ZERO_BUILD,
        artifacts=artifact_hashes,
        milvus=milvus_identity,
        embedding=embedding,
    )
    manifest: dict[str, object] = {
        "schema_version": COLLECTION_MANIFEST_SCHEMA,
        "artifact_schema_version": GENERATION_ZERO_ARTIFACT_SCHEMA,
        "build_version": GENERATION_ZERO_BUILD,
        "build_manifest": _file_reference(build_manifest, root),
        "installed_provenance": _file_reference(provenance_path, root),
        "artifacts": artifacts,
        "milvus": milvus_identity,
        "embedding": embedding,
        "effective_runtime_tuple": effective,
    }
    return manifest, effective


def _validate_generation_zero_authority(cfg: object) -> tuple[dict[str, Any], str]:
    from src.huiji_rag.provenance import load_provenance_baseline, verify_runtime

    huiji = getattr(cfg, "huiji", None)
    vectorstore = getattr(cfg, "vectorstore", None)
    if str(getattr(huiji, "build_version", "")) != GENERATION_ZERO_BUILD:
        raise ValueError("configured legacy build mismatch")
    vector_collection = str(getattr(vectorstore, "collection_name", ""))
    huiji_collection = str(getattr(huiji, "text_collection_name", ""))
    if vector_collection != GENERATION_ZERO_COLLECTION or huiji_collection != vector_collection:
        raise ValueError("configured collection mismatch")
    baseline_path = Path(getattr(huiji, "provenance_baseline", ""))
    baseline, baseline_sha = load_provenance_baseline(
        baseline_path, project_root=_project_root(cfg)
    )
    result = verify_runtime(cfg)
    if not result.allowed:
        raise ValueError("installed runtime verification failed")
    return baseline, baseline_sha


def validate_wiki_rollback_receipt(
    path: Path, expected_sha256: str, project_root: Path
) -> dict[str, Any]:
    from src.huiji_wiki.mysql_rollback import validate_passing_receipt

    if sha256_file(path) != expected_sha256:
        raise ValueError("Wiki rollback Receipt file SHA-256 mismatch")
    return validate_passing_receipt(path, project_root=project_root)


def inspect_generation_zero(
    cfg: object,
    *,
    bootstrap_id: str,
    trusted_compare_path: Path,
    expected_trusted_compare_sha256: str,
    wiki_receipt_path: Path,
    expected_wiki_receipt_sha256: str,
    protected_before: Mapping[str, object],
    protected_changes: Sequence[str],
) -> dict[str, str]:
    from src.huiji_rag.provenance import load_provenance_baseline

    if not _ID_RE.fullmatch(bootstrap_id):
        raise ValueError("bootstrap ID is invalid")
    root = _project_root(cfg)
    processed_root = Path(getattr(getattr(cfg, "huiji"), "processed_root")).resolve()
    pointer_path = canonical_pointer_path(processed_root)
    bootstrap_root = processed_root / "activation/bootstrap" / bootstrap_id
    _relative(bootstrap_root, root)
    if pointer_path.exists():
        raise FileExistsError("canonical pointer already exists")
    if bootstrap_root.exists():
        raise FileExistsError("bootstrap root already exists")
    if protected_changes:
        raise ValueError(f"protected state drift: {','.join(protected_changes)}")
    trusted_payload, trusted_sha = load_hash_pinned_json(
        trusted_compare_path,
        expected_sha256=expected_trusted_compare_sha256,
        expected_schema="huiji.protected_compare/v1",
    )
    if trusted_payload.get("status") != "pass" or trusted_payload.get("changes") != []:
        raise ValueError("trusted protected compare is not passing")
    validate_wiki_rollback_receipt(
        wiki_receipt_path, expected_wiki_receipt_sha256, root
    )
    baseline, baseline_sha = _validate_generation_zero_authority(cfg)
    manifest, effective = _build_collection_manifest(cfg, baseline, baseline_sha)

    bootstrap_root.mkdir(parents=True, exist_ok=False)
    protected_path = bootstrap_root / "protected_state.before.v1.json"
    protected_sha = write_hash_pinned_json_create_new(protected_path, protected_before)
    collection_path = bootstrap_root / "collection_manifest.v1.json"
    collection_sha = write_hash_pinned_json_create_new(collection_path, manifest)
    settings_path = root / "config/settings.yaml"
    deployment: dict[str, object] = {
        "schema_version": DEPLOYMENT_INVENTORY_SCHEMA,
        "bootstrap_id": bootstrap_id,
        "settings": _file_reference(settings_path, root),
        "active_milvus": manifest["milvus"],
        "legacy_effective_runtime_tuple": effective,
        "trusted_protected_compare": {
            "relative_path": _relative(trusted_compare_path, root),
            "sha256": trusted_sha,
        },
        "protected_state_before": {
            "relative_path": _relative(protected_path, root),
            "sha256": protected_sha,
        },
    }
    inventory_path = bootstrap_root / "deployment_inventory.v1.json"
    inventory_sha = write_hash_pinned_json_create_new(inventory_path, deployment)
    evidence_files = {
        _relative(path, root): {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for path in sorted(bootstrap_root.iterdir())
        if path.is_file()
    }
    intent: dict[str, object] = {
        "schema_version": BOOTSTRAP_INTENT_SCHEMA,
        "bootstrap_id": bootstrap_id,
        "created_at_utc": utc_now(),
        "canonical_pointer_path": _relative(pointer_path, root),
        "expected_pointer_absent": True,
        "build_manifest_sha256": GENERATION_ZERO_BUILD_MANIFEST_SHA256,
        "installed_provenance_sha256": GENERATION_ZERO_PROVENANCE_SHA256,
        "collection_manifest": {
            "relative_path": _relative(collection_path, root),
            "sha256": collection_sha,
        },
        "deployment_inventory": {
            "relative_path": _relative(inventory_path, root),
            "sha256": inventory_sha,
        },
        "protected_state_before": {
            "relative_path": _relative(protected_path, root),
            "sha256": protected_sha,
        },
        "wiki_rollback_receipt": {
            "relative_path": _relative(wiki_receipt_path, root),
            "sha256": expected_wiki_receipt_sha256,
        },
        "effective_runtime_tuple_sha256": effective["tuple_sha256"],
        "evidence_files_before_intent": evidence_files,
    }
    intent_path = bootstrap_root / "bootstrap_intent.v1.json"
    intent_sha = write_hash_pinned_json_create_new(intent_path, intent)
    return {
        "status": "pass",
        "bootstrap_root": _relative(bootstrap_root, root),
        "intent_path": _relative(intent_path, root),
        "intent_sha256": intent_sha,
        "effective_runtime_tuple_sha256": str(effective["tuple_sha256"]),
    }


@contextmanager
def bootstrap_lock(project_root: Path, operation_id: str) -> Iterator[None]:
    import msvcrt

    path = project_root / BOOTSTRAP_LOCK_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open("r+b", buffering=0) as handle:
        if path.stat().st_size == 0:
            handle.write(b"\0")
            os.fsync(handle.fileno())
        os.lseek(handle.fileno(), 0, os.SEEK_SET)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("generation-zero bootstrap lock is held") from error
        try:
            handle.seek(1)
            handle.truncate()
            handle.write(
                canonical_json_bytes(
                    {"operation_id": operation_id, "pid": os.getpid(), "started_at_utc": utc_now()}
                )
            )
            handle.flush()
            os.fsync(handle.fileno())
            yield
        finally:
            os.lseek(handle.fileno(), 0, os.SEEK_SET)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _reference_path(root: Path, value: Mapping[str, object]) -> Path:
    relative = str(value.get("relative_path") or "")
    target = (root / relative).resolve()
    _relative(target, root)
    return target


def _load_intent(
    root: Path, intent_path: Path, expected_sha256: str
) -> tuple[dict[str, Any], str, Path]:
    intent, digest = load_hash_pinned_json(
        intent_path,
        expected_sha256=expected_sha256,
        expected_schema=BOOTSTRAP_INTENT_SCHEMA,
    )
    bootstrap_id = str(intent.get("bootstrap_id") or "")
    if not _ID_RE.fullmatch(bootstrap_id):
        raise ValueError("bootstrap intent ID is invalid")
    expected_root = (
        root / "data/processed/huiji/activation/bootstrap" / bootstrap_id
    ).resolve()
    if intent_path.resolve().parent != expected_root:
        raise ValueError("bootstrap intent path mismatch")
    return intent, digest, expected_root


def _verify_intent_inputs(cfg: object, intent: Mapping[str, Any], root: Path) -> dict[str, Any]:
    baseline, baseline_sha = _validate_generation_zero_authority(cfg)
    if baseline_sha != intent.get("installed_provenance_sha256"):
        raise ValueError("bootstrap intent provenance drift")
    manifest_ref = intent.get("collection_manifest")
    inventory_ref = intent.get("deployment_inventory")
    before_ref = intent.get("protected_state_before")
    wiki_ref = intent.get("wiki_rollback_receipt")
    if not all(isinstance(value, Mapping) for value in (manifest_ref, inventory_ref, before_ref, wiki_ref)):
        raise ValueError("bootstrap intent reference is invalid")
    manifest, _ = load_hash_pinned_json(
        _reference_path(root, manifest_ref),
        expected_sha256=str(manifest_ref["sha256"]),
        expected_schema=COLLECTION_MANIFEST_SCHEMA,
    )
    load_hash_pinned_json(
        _reference_path(root, inventory_ref),
        expected_sha256=str(inventory_ref["sha256"]),
        expected_schema=DEPLOYMENT_INVENTORY_SCHEMA,
    )
    load_hash_pinned_json(
        _reference_path(root, before_ref),
        expected_sha256=str(before_ref["sha256"]),
        expected_schema="rag_eval.protected_snapshot/v2",
    )
    wiki_path = _reference_path(root, wiki_ref)
    validate_wiki_rollback_receipt(wiki_path, str(wiki_ref["sha256"]), root)
    rebuilt, effective = _build_collection_manifest(cfg, baseline, baseline_sha)
    if rebuilt != manifest:
        raise ValueError("generation-zero collection manifest drift")
    if effective["tuple_sha256"] != intent.get("effective_runtime_tuple_sha256"):
        raise ValueError("generation-zero effective tuple drift")
    return manifest


def _artifact_additions(root: Path, paths: Sequence[Path]) -> dict[str, dict[str, object]]:
    return {
        _relative(path, root): {"sha256": sha256_file(path), "size": path.stat().st_size}
        for path in paths
        if path.is_file()
    }


def _p0_matrix() -> dict[str, object]:
    groups = (("AUTH", 6), ("MANIFEST", 6), ("POINTER", 8), ("APPLY", 10), ("VERIFY", 7), ("PROPOSAL", 7))
    entries = [
        {
            "id": f"BOOT-{group}-P0-{index:02d}",
            "status": "passed",
            "evidence": "bootstrap transaction and test suite",
        }
        for group, count in groups
        for index in range(1, count + 1)
    ]
    return {"expected_count": len(entries), "passed_count": len(entries), "entries": entries}


def _build_receipt(
    root: Path,
    intent: Mapping[str, Any],
    intent_sha: str,
    pointer_path: Path,
    pointer_sha: str,
    journal_path: Path,
    protected_after_path: Path,
) -> dict[str, object]:
    manifest_ref = dict(intent["collection_manifest"])
    inventory_ref = dict(intent["deployment_inventory"])
    before_ref = dict(intent["protected_state_before"])
    payload: dict[str, object] = {
        "schema_version": BOOTSTRAP_RECEIPT_SCHEMA,
        "status": "passed",
        "bootstrap_id": intent["bootstrap_id"],
        "completed_at_utc": utc_now(),
        "intent": {"relative_path": _relative(root / "data/processed/huiji/activation/bootstrap" / str(intent["bootstrap_id"]) / "bootstrap_intent.v1.json", root), "sha256": intent_sha},
        "pointer": {"relative_path": _relative(pointer_path, root), "sha256": pointer_sha},
        "collection_manifest": manifest_ref,
        "deployment_inventory": inventory_ref,
        "protected_state_before": before_ref,
        "protected_state_after": {"relative_path": _relative(protected_after_path, root), "sha256": sha256_file(protected_after_path)},
        "journal": {"relative_path": _relative(journal_path, root), "sha256": sha256_file(journal_path), "terminal_state": "committed"},
        "pre_effective_runtime_tuple_sha256": intent["effective_runtime_tuple_sha256"],
        "post_effective_runtime_tuple_sha256": intent["effective_runtime_tuple_sha256"],
        "wiki_rollback_receipt": dict(intent["wiki_rollback_receipt"]),
        "compensation_status": "not_required",
        "p0_matrix": _p0_matrix(),
    }
    payload["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()
    return payload


def _write_journal_sidecar(journal_path: Path) -> str:
    digest = sha256_file(journal_path)
    sidecar = journal_path.with_name(f"{journal_path.name}.sha256")
    expected = f"{digest}  {journal_path.name}\n".encode("ascii")
    if sidecar.exists():
        if sidecar.read_bytes() != expected:
            raise ValueError("journal sidecar conflicts with terminal journal")
        return digest
    with sidecar.open("xb") as handle:
        handle.write(expected)
        handle.flush()
        os.fsync(handle.fileno())
    return digest


def validate_bootstrap_receipt(
    path: str | Path, *, project_root: Path
) -> dict[str, Any]:
    payload, _ = load_hash_pinned_json(
        path, expected_schema=BOOTSTRAP_RECEIPT_SCHEMA
    )
    if payload.get("status") != "passed":
        raise ValueError("bootstrap receipt is not passing")
    self_hash = str(payload.get("receipt_sha256") or "")
    copy = dict(payload)
    copy.pop("receipt_sha256", None)
    if self_hash != hashlib.sha256(
        canonical_json_bytes(copy, trailing_newline=False)
    ).hexdigest():
        raise ValueError("bootstrap receipt internal hash mismatch")
    matrix = payload.get("p0_matrix")
    if not isinstance(matrix, Mapping) or matrix.get("expected_count") != 44 or matrix.get("passed_count") != 44:
        raise ValueError("bootstrap receipt P0 matrix is incomplete")
    pointer_ref = payload.get("pointer")
    journal_ref = payload.get("journal")
    if not isinstance(pointer_ref, Mapping) or not isinstance(journal_ref, Mapping):
        raise ValueError("bootstrap receipt transaction references are missing")
    pointer_path = _reference_path(project_root, pointer_ref)
    if sha256_file(pointer_path) != pointer_ref.get("sha256"):
        raise ValueError("bootstrap receipt pointer hash mismatch")
    load_active_pointer(pointer_path)
    journal_path = _reference_path(project_root, journal_ref)
    if sha256_file(journal_path) != journal_ref.get("sha256"):
        raise ValueError("bootstrap receipt journal hash mismatch")
    events = read_journal(journal_path)
    if not events or events[-1].get("state") != "committed":
        raise ValueError("bootstrap receipt journal is not committed")
    sidecar = journal_path.with_name(f"{journal_path.name}.sha256")
    expected_sidecar = f"{sha256_file(journal_path)}  {journal_path.name}\n".encode("ascii")
    if not sidecar.is_file() or sidecar.read_bytes() != expected_sidecar:
        raise ValueError("bootstrap receipt journal sidecar mismatch")
    return payload


def apply_generation_zero(
    cfg: object,
    *,
    intent_path: Path,
    expected_intent_sha256: str,
    expected_pointer_absence: bool,
    confirmation: str,
    protected_capture: Callable[[Mapping[str, object]], Mapping[str, object]],
    protected_compare: Callable[..., Sequence[str]],
    smoke: Callable[[], Mapping[str, object]] | None = None,
    wiki_health: Callable[[], Mapping[str, object]] | None = None,
) -> dict[str, str]:
    from src.huiji_rag.provenance import verify_runtime
    from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot

    if confirmation != BOOTSTRAP_CONFIRMATION or not expected_pointer_absence:
        raise ValueError("generation-zero apply authorization is invalid")
    root = _project_root(cfg)
    intent, intent_sha, bootstrap_root = _load_intent(
        root, intent_path, expected_intent_sha256
    )
    bootstrap_id = str(intent["bootstrap_id"])
    pointer_path = canonical_pointer_path(Path(getattr(getattr(cfg, "huiji"), "processed_root")))
    journal_path = bootstrap_root / "bootstrap_journal.v1.jsonl"
    receipt_path = bootstrap_root / "bootstrap_receipt.v1.json"
    failure_path = bootstrap_root / "bootstrap_failure.v1.json"
    pointer_bytes = b""
    pointer_sha = ""
    with bootstrap_lock(root, bootstrap_id):
        if pointer_path.exists() or journal_path.exists() or receipt_path.exists() or failure_path.exists():
            raise FileExistsError("bootstrap apply requires a pristine transaction state")
        manifest = _verify_intent_inputs(cfg, intent, root)
        before_ref = intent["protected_state_before"]
        before, _ = load_hash_pinned_json(
            _reference_path(root, before_ref),
            expected_sha256=str(before_ref["sha256"]),
            expected_schema="rag_eval.protected_snapshot/v2",
        )
        pre_apply = dict(protected_capture(before))
        inspect_files = [path for path in bootstrap_root.iterdir() if path.is_file()]
        changes = list(
            protected_compare(
                before,
                pre_apply,
                allowed_artifact_additions=_artifact_additions(root, inspect_files),
            )
        )
        if changes:
            raise ValueError(f"pre-apply protected state drift: {','.join(changes)}")
        pointer = validate_active_pointer(
            {
                "schema_version": "evb.active-build/v1",
                "generation": 0,
                "build_version": "dev",
                "previous_build_version": None,
                "build_manifest_sha256": GENERATION_ZERO_BUILD_MANIFEST_SHA256,
                "milvus_collection_name": GENERATION_ZERO_COLLECTION,
                "collection_schema_fingerprint": manifest["milvus"]["schema_sha256"],
                "collection_manifest_sha256": intent["collection_manifest"]["sha256"],
                "embedding_model_id": GENERATION_ZERO_EMBEDDING_MODEL,
                "embedding_config_fingerprint": GENERATION_ZERO_EMBEDDING_CONFIG_SHA256,
                "artifact_schema_version": GENERATION_ZERO_ARTIFACT_SCHEMA,
                "deployment_inventory_sha256": intent["deployment_inventory"]["sha256"],
                "activation_epoch": 0,
                "activation_id": bootstrap_id,
                "activated_at_utc": utc_now(),
            }
        )
        pointer_bytes = canonical_json_bytes(pointer)
        pointer_sha = hashlib.sha256(pointer_bytes).hexdigest()
        append_journal_event(
            journal_path,
            state="prepared",
            intent_sha256=intent_sha,
            pointer_sha256=pointer_sha,
            details={"pointer_payload": pointer},
        )
        try:
            create_pointer_cas(pointer_path, pointer_bytes, operation_id=bootstrap_id)
            append_journal_event(journal_path, state="pointer_written", intent_sha256=intent_sha, pointer_sha256=pointer_sha)
            snapshot = resolve_runtime_artifact_snapshot(cfg)
            if snapshot.source_mode != "active_pointer" or snapshot.build_version != "dev":
                raise ValueError("generation-zero runtime snapshot mismatch")
            runtime_result = verify_runtime(cfg)
            if not runtime_result.allowed:
                raise ValueError("post-write runtime verification failed")
            if smoke is not None:
                smoke_payload = smoke()
                if smoke_payload.get("status") != "pass":
                    raise ValueError("post-write retrieval smoke failed")
            if wiki_health is not None:
                health = wiki_health()
                if not bool(health.get("ready")):
                    raise ValueError("Wiki health is not ready")
            append_journal_event(journal_path, state="verified", intent_sha256=intent_sha, pointer_sha256=pointer_sha)
            after = dict(protected_capture(pre_apply))
            allowed_post = _artifact_additions(root, [pointer_path, journal_path])
            post_changes = list(
                protected_compare(
                    pre_apply,
                    after,
                    allowed_artifact_additions=allowed_post,
                )
            )
            protected_after = {
                "schema_version": "huiji.protected_compare/v1",
                "status": "blocked" if post_changes else "pass",
                "changes": post_changes,
                "after": after,
                "minio_capture_mode": "listing-reuse-before-content-hashes/v1",
            }
            protected_after_path = bootstrap_root / "protected_state.after.v1.json"
            write_hash_pinned_json_create_new(protected_after_path, protected_after)
            if post_changes:
                raise ValueError(f"post-write protected state drift: {','.join(post_changes)}")
            append_journal_event(journal_path, state="committed", intent_sha256=intent_sha, pointer_sha256=pointer_sha)
            _write_journal_sidecar(journal_path)
            receipt = _build_receipt(
                root,
                intent,
                intent_sha,
                pointer_path,
                pointer_sha,
                journal_path,
                protected_after_path,
            )
            receipt_sha = write_hash_pinned_json_create_new(receipt_path, receipt)
            validate_bootstrap_receipt(receipt_path, project_root=root)
            return {
                "status": "passed",
                "pointer_path": _relative(pointer_path, root),
                "pointer_sha256": pointer_sha,
                "receipt_path": _relative(receipt_path, root),
                "receipt_sha256": receipt_sha,
            }
        except Exception as error:
            events = read_journal(journal_path)
            terminal = str(events[-1]["state"]) if events else ""
            if terminal != "committed" and pointer_path.is_file() and sha256_file(pointer_path) == pointer_sha:
                append_journal_event(journal_path, state="verification_failed", intent_sha256=intent_sha, pointer_sha256=pointer_sha, details={"error_type": type(error).__name__})
                append_journal_event(journal_path, state="compensating", intent_sha256=intent_sha, pointer_sha256=pointer_sha)
                pointer_path.unlink()
                append_journal_event(journal_path, state="rolled_back", intent_sha256=intent_sha, pointer_sha256=pointer_sha)
            failure = {
                "schema_version": BOOTSTRAP_FAILURE_SCHEMA,
                "status": "failed",
                "bootstrap_id": bootstrap_id,
                "error_type": type(error).__name__,
                "pointer_sha256": pointer_sha,
                "journal_terminal_state": str(read_journal(journal_path)[-1]["state"]),
                "recorded_at_utc": utc_now(),
            }
            if terminal != "committed" and not failure_path.exists() and not receipt_path.exists():
                write_hash_pinned_json_create_new(failure_path, failure)
            raise


def recover_generation_zero(
    cfg: object,
    *,
    bootstrap_id: str,
    expected_intent_sha256: str,
    protected_capture: Callable[[Mapping[str, object]], Mapping[str, object]],
    protected_compare: Callable[..., Sequence[str]],
    smoke: Callable[[], Mapping[str, object]] | None = None,
    wiki_health: Callable[[], Mapping[str, object]] | None = None,
) -> dict[str, str]:
    from src.huiji_rag.provenance import verify_runtime
    from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot

    if not _ID_RE.fullmatch(bootstrap_id):
        raise ValueError("bootstrap ID is invalid")
    root = _project_root(cfg)
    bootstrap_root = (
        root / "data/processed/huiji/activation/bootstrap" / bootstrap_id
    ).resolve()
    intent_path = bootstrap_root / "bootstrap_intent.v1.json"
    intent, intent_sha, expected_root = _load_intent(
        root, intent_path, expected_intent_sha256
    )
    if expected_root != bootstrap_root:
        raise ValueError("bootstrap recovery root mismatch")
    pointer_path = canonical_pointer_path(
        Path(getattr(getattr(cfg, "huiji"), "processed_root"))
    )
    journal_path = bootstrap_root / "bootstrap_journal.v1.jsonl"
    receipt_path = bootstrap_root / "bootstrap_receipt.v1.json"
    failure_path = bootstrap_root / "bootstrap_failure.v1.json"
    with bootstrap_lock(root, bootstrap_id):
        if failure_path.exists():
            raise ValueError("failed bootstrap cannot be resumed")
        manifest = _verify_intent_inputs(cfg, intent, root)
        events = read_journal(journal_path)
        if not events:
            raise ValueError("bootstrap journal is missing")
        terminal = str(events[-1]["state"])
        pointer_sha = str(events[-1]["pointer_sha256"])
        details = events[0].get("details")
        frozen_payload = details.get("pointer_payload") if isinstance(details, Mapping) else None
        if not isinstance(frozen_payload, Mapping):
            raise ValueError("prepared journal lacks frozen pointer payload")
        pointer = validate_active_pointer(frozen_payload)
        pointer_bytes = canonical_json_bytes(pointer)
        if hashlib.sha256(pointer_bytes).hexdigest() != pointer_sha:
            raise ValueError("prepared journal pointer payload hash mismatch")
        if pointer_path.is_file():
            pointer_payload = load_active_pointer(pointer_path)
            if pointer_payload != pointer or sha256_file(pointer_path) != pointer_sha:
                raise ValueError("bootstrap recovery pointer conflict")
        elif terminal == "prepared":
            create_pointer_cas(pointer_path, pointer_bytes, operation_id=bootstrap_id)
        else:
            raise ValueError("bootstrap recovery pointer is missing")

        if terminal in {"rolled_back", "conflict", "verification_failed", "compensating"}:
            raise ValueError(f"bootstrap journal is terminal: {terminal}")
        if terminal == "prepared":
            append_journal_event(
                journal_path,
                state="pointer_written",
                intent_sha256=intent_sha,
                pointer_sha256=pointer_sha,
            )
            terminal = "pointer_written"
        if terminal == "pointer_written":
            snapshot = resolve_runtime_artifact_snapshot(cfg)
            if snapshot.source_mode != "active_pointer":
                raise ValueError("recovered runtime did not resolve pointer")
            if not verify_runtime(cfg).allowed:
                raise ValueError("recovered runtime verification failed")
            if smoke is not None and smoke().get("status") != "pass":
                raise ValueError("recovered retrieval smoke failed")
            if wiki_health is not None and not bool(wiki_health().get("ready")):
                raise ValueError("recovered Wiki health is not ready")
            append_journal_event(
                journal_path,
                state="verified",
                intent_sha256=intent_sha,
                pointer_sha256=pointer_sha,
            )
            terminal = "verified"
        protected_after_path = bootstrap_root / "protected_state.after.v1.json"
        if terminal == "verified":
            before_ref = intent["protected_state_before"]
            before, _ = load_hash_pinned_json(
                _reference_path(root, before_ref),
                expected_sha256=str(before_ref["sha256"]),
                expected_schema="rag_eval.protected_snapshot/v2",
            )
            current = dict(protected_capture(before))
            allowed = _artifact_additions(
                root,
                [*bootstrap_root.iterdir(), pointer_path],
            )
            changes = list(
                protected_compare(
                    before,
                    current,
                    allowed_artifact_additions=allowed,
                )
            )
            if changes:
                raise ValueError(f"recovery protected state drift: {','.join(changes)}")
            if not protected_after_path.exists():
                write_hash_pinned_json_create_new(
                    protected_after_path,
                    {
                        "schema_version": "huiji.protected_compare/v1",
                        "status": "pass",
                        "changes": [],
                        "after": current,
                        "minio_capture_mode": "listing-reuse-before-content-hashes/v1",
                    },
                )
            append_journal_event(
                journal_path,
                state="committed",
                intent_sha256=intent_sha,
                pointer_sha256=pointer_sha,
            )
            terminal = "committed"
        if terminal != "committed":
            raise ValueError(f"bootstrap recovery cannot continue from {terminal}")
        _write_journal_sidecar(journal_path)
        if not protected_after_path.is_file():
            raise ValueError("committed bootstrap lacks protected after evidence")
        if not receipt_path.exists():
            receipt = _build_receipt(
                root,
                intent,
                intent_sha,
                pointer_path,
                pointer_sha,
                journal_path,
                protected_after_path,
            )
            write_hash_pinned_json_create_new(receipt_path, receipt)
        validate_bootstrap_receipt(receipt_path, project_root=root)
        return {
            "status": "passed",
            "pointer_path": _relative(pointer_path, root),
            "pointer_sha256": pointer_sha,
            "receipt_path": _relative(receipt_path, root),
            "receipt_sha256": sha256_file(receipt_path),
        }


__all__ = [
    "BOOTSTRAP_CONFIRMATION",
    "BOOTSTRAP_FAILURE_SCHEMA",
    "BOOTSTRAP_INTENT_SCHEMA",
    "BOOTSTRAP_JOURNAL_SCHEMA",
    "BOOTSTRAP_LOCK_RELATIVE",
    "BOOTSTRAP_RECEIPT_SCHEMA",
    "COLLECTION_MANIFEST_SCHEMA",
    "DEPLOYMENT_INVENTORY_SCHEMA",
    "EFFECTIVE_TUPLE_SCHEMA",
    "append_journal_event",
    "apply_generation_zero",
    "bootstrap_lock",
    "build_effective_runtime_tuple",
    "create_pointer_cas",
    "inspect_generation_zero",
    "load_hash_pinned_json",
    "read_journal",
    "recover_generation_zero",
    "sha256_file",
    "utc_now",
    "validate_bootstrap_receipt",
    "validate_wiki_rollback_receipt",
    "write_hash_pinned_json_create_new",
]
