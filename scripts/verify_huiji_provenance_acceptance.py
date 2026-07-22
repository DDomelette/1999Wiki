"""Acceptance evidence for Huiji provenance and protected-state invariants."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.provenance import (
    load_provenance_baseline,
    safe_relative_path,
    verify_runtime,
    write_hash_pinned_json,
)
from src.rag.query_plan import QueryPlan, VALID_INTENTS
from src.rag.retriever import Retriever
from src.rag.vectorstore import load_vectorstore
from src.rag_eval.inventory import (
    capture_artifact_digests,
    capture_inventory,
    capture_milvus_snapshot,
    capture_mysql_table_digests,
    capture_protected_snapshot,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify Huiji provenance acceptance gates")
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--allow-shadow-collection")
    compare.add_argument(
        "--reuse-before-minio-content-hashes",
        action="store_true",
        help=(
            "compare current MinIO key/size/ETag/version against the full before "
            "inventory without downloading unchanged object bodies"
        ),
    )
    compare.add_argument(
        "--allow-artifact-addition",
        action="append",
        default=[],
        metavar="PATH|SHA256|SIZE",
        help="allow one exact create-new artifact while retaining all other drift gates",
    )
    sample = subparsers.add_parser("sample-active")
    sample.add_argument("--output", type=Path, required=True)
    drift = subparsers.add_parser("prove-artifact-drift")
    drift.add_argument("--output", type=Path, required=True)
    return parser


def _snapshot_payload(value: object) -> dict[str, object]:
    serializer = getattr(value, "to_json", None)
    payload = serializer() if callable(serializer) else value
    if not isinstance(payload, Mapping):
        raise TypeError("protected snapshot is not serializable")
    return dict(payload)


def _stable_protected_payload(payload: Mapping[str, object]) -> dict[str, object]:
    frozen = copy.deepcopy(dict(payload))
    frozen.pop("captured_at_utc", None)
    milvus = frozen.get("milvus")
    if isinstance(milvus, dict):
        milvus.pop("captured_at_utc", None)
    inventories = frozen.get("minio_inventories")
    if isinstance(inventories, dict):
        for value in inventories.values():
            if isinstance(value, dict):
                value.pop("captured_at_utc", None)
                value.pop("inventory_sha256", None)
    return frozen


def _listing_identity(value: Mapping[str, object]) -> dict[str, object]:
    return {
        "object_key": str(value.get("object_key") or ""),
        "size": int(value.get("size") or 0),
        "etag": str(value.get("etag") or "").strip('"'),
        "version_id": (
            None if value.get("version_id") is None else str(value.get("version_id"))
        ),
    }


def merge_listing_inventory_with_baseline(
    baseline: Mapping[str, object],
    *,
    current_policy_summary: str,
    current_objects: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Reuse full hashes only when immutable listing identity still matches."""
    baseline_objects = baseline.get("objects")
    if not isinstance(baseline_objects, list):
        raise ValueError("before MinIO inventory lacks objects")
    by_key: dict[str, Mapping[str, object]] = {}
    for item in baseline_objects:
        if not isinstance(item, Mapping):
            raise ValueError("before MinIO inventory contains an invalid object")
        key = str(item.get("object_key") or "")
        if not key or key in by_key:
            raise ValueError("before MinIO inventory has blank or duplicate keys")
        by_key[key] = item

    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in current_objects:
        identity = _listing_identity(item)
        key = str(identity["object_key"])
        if not key or not identity["etag"] or key in seen:
            raise ValueError("current MinIO listing has blank or duplicate identity")
        seen.add(key)
        previous = by_key.get(key)
        if previous is not None and _listing_identity(previous) == identity:
            merged.append(dict(previous))
        else:
            merged.append(
                {
                    **identity,
                    "sha1": "",
                    "sha256": "",
                    "audit_event_id": None,
                    "application_operation_id": None,
                }
            )
    payload = dict(baseline)
    payload["bucket_policy_summary"] = current_policy_summary
    payload["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
    payload["inventory_sha256"] = "listing-reuse-before-content-hashes"
    payload["objects"] = sorted(merged, key=lambda item: str(item["object_key"]))
    return payload


def _bucket_policy_summary(client: object, bucket: str) -> str:
    try:
        raw_policy = client.get_bucket_policy(bucket)
    except Exception as error:
        if str(getattr(error, "code", "")) in {"NoSuchBucketPolicy", "NoSuchPolicy"}:
            return "absent"
        raise
    if not isinstance(raw_policy, str):
        raise ValueError("MinIO bucket policy is invalid")
    payload = json.loads(raw_policy)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def capture_listing_reuse_snapshot(
    cfg: object,
    before: Mapping[str, object],
) -> dict[str, object]:
    """Capture protected state while reusing content hashes for unchanged MinIO objects."""
    from minio import Minio

    assets = getattr(cfg, "assets", None)
    if assets is None:
        raise ValueError("asset storage configuration is missing")
    client = Minio(
        str(getattr(assets, "endpoint", "")),
        access_key=str(getattr(assets, "access_key", "")),
        secret_key=str(getattr(assets, "secret_key", "")),
        secure=bool(getattr(assets, "secure", False)),
    )
    before_inventories = before.get("minio_inventories")
    if not isinstance(before_inventories, Mapping):
        raise ValueError("before snapshot lacks MinIO inventories")
    inventories: dict[str, dict[str, object]] = {}
    for scope in sorted(str(value) for value in before_inventories):
        baseline = before_inventories.get(scope)
        if not isinstance(baseline, Mapping):
            raise ValueError(f"before MinIO inventory is invalid: {scope}")
        bucket = str(baseline.get("bucket") or "")
        prefix = str(baseline.get("prefix") or "").rstrip("/")
        if not bucket:
            raise ValueError(f"before MinIO inventory has a blank bucket: {scope}")
        list_prefix = f"{prefix}/" if prefix else ""
        current: list[dict[str, object]] = []
        for item in client.list_objects(bucket, prefix=list_prefix, recursive=True):
            current.append(
                {
                    "object_key": str(getattr(item, "object_name", "") or ""),
                    "size": int(getattr(item, "size", -1)),
                    "etag": str(getattr(item, "etag", "") or "").strip('"'),
                    "version_id": getattr(item, "version_id", None),
                }
            )
        inventories[scope] = merge_listing_inventory_with_baseline(
            baseline,
            current_policy_summary=_bucket_policy_summary(client, bucket),
            current_objects=current,
        )

    milvus = capture_milvus_snapshot(cfg)
    serializer = getattr(milvus, "to_json", None)
    return {
        "schema_version": "rag_eval.protected_snapshot/v2",
        "milvus": serializer() if callable(serializer) else milvus,
        "minio_inventories": inventories,
        "mysql_tables": capture_mysql_table_digests(cfg),
        "artifacts": capture_artifact_digests(cfg),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "minio_capture_mode": "listing-reuse-before-content-hashes/v1",
    }


def compare_protected_payloads(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    allowed_minio_additions: Mapping[str, Sequence[str]] | None = None,
    allowed_artifact_additions: Mapping[str, Mapping[str, object]] | None = None,
) -> list[str]:
    left = _stable_protected_payload(before)
    right = _stable_protected_payload(after)
    left_inventories = left.get("minio_inventories")
    right_inventories = right.get("minio_inventories")
    if (
        allowed_minio_additions
        and isinstance(left_inventories, Mapping)
        and isinstance(right_inventories, Mapping)
    ):
        for scope, allowed_keys in allowed_minio_additions.items():
            left_inventory = left_inventories.get(scope)
            right_inventory = right_inventories.get(scope)
            if not isinstance(left_inventory, Mapping) or not isinstance(right_inventory, dict):
                continue
            left_objects = left_inventory.get("objects")
            right_objects = right_inventory.get("objects")
            if not isinstance(left_objects, list) or not isinstance(right_objects, list):
                continue
            existing_keys = {
                str(item.get("object_key") or "")
                for item in left_objects
                if isinstance(item, Mapping)
            }
            allowed = {str(value) for value in allowed_keys}
            right_inventory["objects"] = [
                item
                for item in right_objects
                if not (
                    isinstance(item, Mapping)
                    and str(item.get("object_key") or "") in allowed
                    and str(item.get("object_key") or "") not in existing_keys
                )
            ]
    if allowed_artifact_additions:
        left_artifacts = left.get("artifacts")
        right_artifacts = right.get("artifacts")
        if not isinstance(left_artifacts, Mapping) or not isinstance(right_artifacts, dict):
            raise ValueError("protected snapshot lacks artifact inventory")
        for path, expected in allowed_artifact_additions.items():
            if path in left_artifacts:
                raise ValueError(f"allowed artifact addition already existed: {path}")
            actual = right_artifacts.get(path)
            if actual is None:
                raise ValueError(f"allowed artifact addition is missing: {path}")
            if actual != dict(expected):
                raise ValueError(f"allowed artifact addition does not match evidence: {path}")
            del right_artifacts[path]
    changes: list[str] = []
    for key in ("milvus", "minio_inventories", "mysql_tables", "artifacts"):
        if left.get(key) != right.get(key):
            changes.append(f"{key} changed")
    return changes


_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def parse_allowed_artifact_additions(
    values: Sequence[str],
) -> dict[str, dict[str, object]]:
    additions: dict[str, dict[str, object]] = {}
    for value in values:
        parts = value.split("|")
        if len(parts) != 3:
            raise ValueError("artifact addition must use PATH|SHA256|SIZE")
        raw_path, sha256, raw_size = parts
        path = PurePosixPath(raw_path)
        if (
            not raw_path
            or "\\" in raw_path
            or path.is_absolute()
            or str(path) != raw_path
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError(f"artifact addition path is not canonical: {raw_path}")
        normalized_sha256 = sha256.lower()
        if not _SHA256_RE.fullmatch(normalized_sha256):
            raise ValueError(f"artifact addition SHA-256 is invalid: {raw_path}")
        try:
            size = int(raw_size)
        except ValueError as error:
            raise ValueError(f"artifact addition size is invalid: {raw_path}") from error
        if size < 0 or str(size) != raw_size:
            raise ValueError(f"artifact addition size is not canonical: {raw_path}")
        if raw_path in additions:
            raise ValueError(f"duplicate artifact addition: {raw_path}")
        additions[raw_path] = {"sha256": normalized_sha256, "size": size}
    return additions


def identify_shadow_minio_additions(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    client: object,
    collection_name: str,
    storage_scope: str = "a-bucket",
) -> tuple[dict[str, tuple[str, ...]], dict[str, object]]:
    describe = getattr(client, "describe_collection", None)
    list_segments = getattr(client, "list_persistent_segments", None)
    if not callable(describe) or not callable(list_segments):
        raise TypeError("Milvus client cannot attribute shadow storage")
    collection = describe(collection_name)
    if not isinstance(collection, Mapping) or not collection.get("collection_id"):
        raise ValueError("shadow collection lacks a collection ID")
    collection_id = str(collection["collection_id"])
    tokens = {collection_id}
    for segment in list_segments(collection_name):
        segment_collection_id = str(getattr(segment, "collection_id", ""))
        if segment_collection_id != collection_id:
            raise ValueError("shadow segment belongs to a different collection")
        segment_id = str(getattr(segment, "segment_id", ""))
        if not segment_id:
            raise ValueError("shadow segment lacks an ID")
        tokens.add(segment_id)

    def object_keys(payload: Mapping[str, object]) -> set[str]:
        inventories = payload.get("minio_inventories")
        inventory = inventories.get(storage_scope) if isinstance(inventories, Mapping) else None
        objects = inventory.get("objects") if isinstance(inventory, Mapping) else None
        if not isinstance(objects, list):
            raise ValueError(f"protected snapshot lacks MinIO scope: {storage_scope}")
        return {
            str(item.get("object_key") or "")
            for item in objects
            if isinstance(item, Mapping) and item.get("object_key")
        }

    added = object_keys(after) - object_keys(before)
    attributed = tuple(
        sorted(key for key in added if tokens.intersection(part for part in key.split("/") if part))
    )
    digest = hashlib.sha256()
    for key in attributed:
        digest.update(key.encode("utf-8"))
        digest.update(b"\n")
    return (
        {storage_scope: attributed},
        {
            "collection": collection_name,
            "storage_scope": storage_scope,
            "object_count": len(attributed),
            "object_keys_sha256": digest.hexdigest(),
            "attribution_token_count": len(tokens),
        },
    )


def _sha256_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _intent_for_entity(entity: object, child: object) -> str:
    intents = getattr(entity, "child_ids_by_intent", {})
    if isinstance(intents, Mapping):
        for intent in sorted(str(key) for key in intents):
            if intent in VALID_INTENTS:
                return intent
    for intent in getattr(child, "route_tags", ()) or ():
        if str(intent) in VALID_INTENTS:
            return str(intent)
    section = str(getattr(child, "section_kind", ""))
    return {
        "skills": "skill",
        "skill": "skill",
        "voice": "voice",
        "profile": "intro",
        "dossier": "profile_fact",
        "items": "item",
        "culture": "culture",
        "story": "story",
        "psychube": "psychube",
    }.get(section, "general")


def sample_active_sources(
    cfg: object,
    *,
    inventory_loader: Callable[[object], object] = capture_inventory,
    vectorstore_loader: Callable[[object], object] = load_vectorstore,
    retriever_factory: Callable[[object, object], object] = Retriever,
) -> dict[str, object]:
    inventory = inventory_loader(cfg)
    entities = getattr(inventory, "entities", {})
    children = getattr(inventory, "children", {})
    if not isinstance(entities, Mapping) or not isinstance(children, Mapping):
        raise ValueError("evaluation inventory is invalid")
    selected: dict[str, object] = {}
    for entity_id in sorted(entities):
        entity = entities[entity_id]
        entity_type = str(getattr(entity, "entity_type", "") or "unknown")
        if entity_type in selected:
            continue
        child_ids: list[str] = []
        intents = getattr(entity, "child_ids_by_intent", {})
        if isinstance(intents, Mapping):
            for values in intents.values():
                child_ids.extend(str(value) for value in values)
        if not child_ids:
            child_ids = [
                str(child_id)
                for child_id, child in children.items()
                if str(getattr(child, "entity_id", "")) == str(entity_id)
            ]
        child = next((children[value] for value in sorted(set(child_ids)) if value in children), None)
        if child is not None:
            selected[entity_type] = (entity, child)
    if not selected:
        raise ValueError("no dynamic entity samples are available")

    retriever = retriever_factory(cfg, vectorstore_loader(cfg))
    top_k = max(1, int(getattr(getattr(cfg, "rag", None), "top_k", 5) or 5))
    samples: list[dict[str, object]] = []
    for entity_type in sorted(selected):
        entity, child = selected[entity_type]
        entity_id = str(getattr(entity, "entity_id", ""))
        entity_name = str(getattr(entity, "entity_name", ""))
        child_id = str(getattr(child, "child_id", ""))
        intent = _intent_for_entity(entity, child)
        plan = QueryPlan(
            original_query=entity_name,
            normalized_query=entity_name,
            entity=entity_name,
            aliases=tuple(getattr(entity, "aliases", ()) or ()),
            intent=intent,
            section_hints=(str(getattr(child, "section_kind", "")),),
            scatter_terms=(),
            confidence=1.0,
            entity_type=entity_type,
            entity_id=entity_id,
            resolution_mode="exact_id",
            dense_query=entity_name,
            sparse_query=entity_name,
            planning_status="fallback_no_llm",
        )
        sources = retriever.search(entity_name, k=top_k, query_plan=plan)
        if not sources:
            raise ValueError("dynamic sample returned no sources")
        if any(str(source.get("entity_id") or "") != entity_id for source in sources):
            raise ValueError("dynamic sample returned a different owner")
        stages = sorted({str(source.get("retrieval_stage") or "") for source in sources})
        if stages != ["huiji_hybrid"]:
            raise ValueError("dynamic sample did not use huiji_hybrid")
        samples.append(
            {
                "entity_type": entity_type,
                "entity_id_sha256": _sha256_token(entity_id),
                "child_id_sha256": _sha256_token(child_id),
                "source_count": len(sources),
                "stages": stages,
            }
        )
    return {
        "schema_version": "huiji.active_source_sample/v1",
        "status": "pass",
        "samples": samples,
    }


def _default_client(cfg: object) -> object:
    from pymilvus import MilvusClient

    vectorstore = getattr(cfg, "vectorstore")
    return MilvusClient(
        uri=str(getattr(vectorstore, "uri")),
        db_name=str(getattr(vectorstore, "db_name")),
    )


def _prove_artifact_drift(
    cfg: object,
    *,
    client_factory: Callable[[object], object],
) -> dict[str, object]:
    project_root = Path(getattr(getattr(cfg, "paths"), "project_root")).resolve()
    baseline_path = Path(getattr(getattr(cfg, "huiji"), "provenance_baseline"))
    baseline, _digest = load_provenance_baseline(baseline_path, project_root=project_root)
    with tempfile.TemporaryDirectory(prefix="huiji-provenance-drift-") as temp_name:
        temp_root = Path(temp_name).resolve()
        artifacts = baseline.get("artifacts")
        bm25 = baseline.get("bm25")
        entries: list[Mapping[str, object]] = []
        if isinstance(artifacts, Mapping):
            entries.extend(value for value in artifacts.values() if isinstance(value, Mapping))
        if isinstance(bm25, Mapping):
            entries.extend(value for value in bm25.values() if isinstance(value, Mapping))
        for entry in entries:
            relative = str(entry.get("relative_path") or "")
            source = (project_root / relative).resolve()
            safe_relative_path(source, project_root)
            destination = temp_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        baseline_relative = safe_relative_path(baseline_path, project_root)
        copied_baseline = temp_root / baseline_relative
        copied_baseline.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(baseline_path, copied_baseline)
        shutil.copy2(
            baseline_path.with_name(f"{baseline_path.name}.sha256"),
            copied_baseline.with_name(f"{copied_baseline.name}.sha256"),
        )

        temp_cfg = copy.deepcopy(cfg)
        temp_cfg.paths.project_root = temp_root
        processed_relative = safe_relative_path(getattr(cfg.huiji, "processed_root"), project_root)
        temp_cfg.huiji.processed_root = temp_root / processed_relative
        temp_cfg.huiji.provenance_baseline = copied_baseline
        child_entry = artifacts.get("child_blocks") if isinstance(artifacts, Mapping) else None
        if not isinstance(child_entry, Mapping):
            raise ValueError("baseline lacks child_blocks")
        child_copy = temp_root / str(child_entry.get("relative_path") or "")
        child_copy.write_bytes(child_copy.read_bytes() + b"\n")
        result = verify_runtime(temp_cfg, client_factory=client_factory)
        codes = sorted({issue.code for issue in result.issues})
        if result.status != "blocked" or "artifact_hash_mismatch" not in codes:
            raise ValueError("temporary artifact drift was not blocked")
        return {
            "schema_version": "huiji.artifact_drift_proof/v1",
            "status": "pass",
            "observed_runtime_status": result.status,
            "observed_codes": codes,
        }


def main(
    argv: Sequence[str] | None = None,
    *,
    cfg_loader: Callable[[], Any] = get_config,
    snapshot_loader: Callable[[object], object] = capture_protected_snapshot,
    listing_snapshot_loader: Callable[
        [object, Mapping[str, object]], object
    ] = capture_listing_reuse_snapshot,
    inventory_loader: Callable[[object], object] = capture_inventory,
    vectorstore_loader: Callable[[object], object] = load_vectorstore,
    retriever_factory: Callable[[object, object], object] = Retriever,
    client_factory: Callable[[object], object] = _default_client,
) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = cfg_loader()
        project_root = Path(getattr(getattr(cfg, "paths"), "project_root")).resolve()
        output = Path(args.output)
        safe_relative_path(output, project_root)
        if args.command == "snapshot":
            payload = _snapshot_payload(snapshot_loader(cfg))
            write_hash_pinned_json(output, payload)
            print(f"status=pass evidence={safe_relative_path(output, project_root)}")
            return 0
        if args.command == "compare":
            before_path = Path(args.before)
            safe_relative_path(before_path, project_root)
            before = json.loads(before_path.read_text(encoding="utf-8"))
            if not isinstance(before, Mapping):
                raise ValueError("before snapshot is invalid")
            after = _snapshot_payload(
                listing_snapshot_loader(cfg, before)
                if args.reuse_before_minio_content_hashes
                else snapshot_loader(cfg)
            )
            allowed_minio_additions: Mapping[str, Sequence[str]] | None = None
            allowed_artifact_additions = parse_allowed_artifact_additions(
                args.allow_artifact_addition
            )
            shadow_summary: Mapping[str, object] | None = None
            shadow_collection = str(args.allow_shadow_collection or "").strip()
            if shadow_collection:
                active_collection = str(
                    getattr(getattr(cfg, "vectorstore", None), "collection_name", "")
                )
                if shadow_collection == active_collection:
                    raise ValueError("active collection cannot be an allowed shadow")
                allowed_minio_additions, shadow_summary = identify_shadow_minio_additions(
                    before,
                    after,
                    client=client_factory(cfg),
                    collection_name=shadow_collection,
                )
            changes = compare_protected_payloads(
                before,
                after,
                allowed_minio_additions=allowed_minio_additions,
                allowed_artifact_additions=allowed_artifact_additions,
            )
            payload = {
                "schema_version": "huiji.protected_compare/v1",
                "status": "blocked" if changes else "pass",
                "changes": changes,
                "after": after,
            }
            if shadow_summary is not None:
                payload["allowed_shadow_addition"] = dict(shadow_summary)
            if args.reuse_before_minio_content_hashes:
                payload["minio_capture_mode"] = (
                    "listing-reuse-before-content-hashes/v1"
                )
            if allowed_artifact_additions:
                payload["allowed_artifact_additions"] = {
                    path: allowed_artifact_additions[path]
                    for path in sorted(allowed_artifact_additions)
                }
            write_hash_pinned_json(output, payload)
            print(
                f"status={payload['status']} changes={','.join(changes) or 'none'} "
                f"evidence={safe_relative_path(output, project_root)}"
            )
            return 2 if changes else 0
        if args.command == "sample-active":
            payload = sample_active_sources(
                cfg,
                inventory_loader=inventory_loader,
                vectorstore_loader=vectorstore_loader,
                retriever_factory=retriever_factory,
            )
        else:
            payload = _prove_artifact_drift(cfg, client_factory=client_factory)
        write_hash_pinned_json(output, payload)
        print(f"status=pass evidence={safe_relative_path(output, project_root)}")
        return 0
    except Exception as error:
        print(f"status=error error_type={type(error).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
