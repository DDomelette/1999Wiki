"""Fail-closed coordinator for the production Wiki media v3 import."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.huiji_rag.activation import validate_wiki_handoff
from src.huiji_wiki.importer import (
    WikiImportPayload,
    build_wiki_import_payload,
    import_payload_to_mysql,
)
from src.huiji_wiki.media_schema import media_v3_schema_statements
from src.huiji_wiki.mysql_inventory import collect_mysql_inventory
from src.huiji_wiki.mysql_rollback import (
    DockerMysqlClient,
    SOURCE_CONTAINER,
    SOURCE_DATABASE,
    inspect_container,
    validate_passing_receipt,
)
from src.huiji_wiki.snapshot import WikiArtifactSnapshot, resolve_wiki_snapshot


ACTIVATION_ID = "candidate-f-generation-1-20260722d"
BUILD_VERSION = "crawler-v3-20260721t051246z"
COLLECTION_NAME = "text_child_bge_m3_shadow_crawler_v3_20260721t051246z"
HANDOFF_SCHEMA = "huiji.wiki-import-handoff/v1"
ARTIFACT_SCHEMA = "evb.media-asset/v3"
EXPECTED_HANDOFF_SHA256 = "884e6ae0ef10911564a84ec3c3ec5b3f57939fc47475ab68599d04ca14d4e90a"
EXPECTED_POINTER_SHA256 = "87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e"
EXPECTED_ROLLBACK_SHA256 = "e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6"
EXPECTED_COUNTS = {
    "wiki_pages": 7456,
    "wiki_categories": 4,
    "wiki_media_links": 17527,
    "wiki_media_resources": 19132,
    "wiki_media_bindings": 19400,
}
APPLY_CONFIRMATION = "IMPORT WIKI CANDIDATE F GENERATION 1"


@dataclass(frozen=True)
class FormalImportContext:
    authority: Mapping[str, Any]
    rollback_receipt: Mapping[str, Any]
    snapshot: WikiArtifactSnapshot
    payload: WikiImportPayload
    database_before: Mapping[str, Any]
    inventory_before: Mapping[str, Any]
    already_installed: bool


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    root = Path(project_root).resolve()
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes project root: {value}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verify_ref(project_root: Path, ref: Mapping[str, Any]) -> Path:
    relative = ref.get("relative_path") or ref.get("path")
    expected = str(ref.get("sha256") or "").lower()
    if not isinstance(relative, str) or len(expected) != 64:
        raise ValueError("invalid hash-pinned reference")
    path = resolve_project_path(project_root, relative)
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"hash-pinned reference mismatch: {relative}")
    return path


def validate_import_authority(
    project_root: Path,
    handoff_path: Path,
    *,
    expected_handoff_sha256: str = EXPECTED_HANDOFF_SHA256,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(project_root).resolve()
    handoff_path = Path(handoff_path).resolve()
    if handoff_path != root and root not in handoff_path.parents:
        raise ValueError("handoff path escapes project root")
    if sha256_file(handoff_path) != expected_handoff_sha256.lower():
        raise ValueError("Wiki handoff file hash mismatch")

    handoff = validate_wiki_handoff(handoff_path, root)
    if (
        handoff.get("schema_version") != HANDOFF_SCHEMA
        or handoff.get("status") != "passed"
        or handoff.get("wiki_import_allowed") is not True
        or handoff.get("wiki_import_status") != "not_started"
        or handoff.get("wiki_must_run_transactional_import_and_rollback_gate") is not True
        or handoff.get("activation_id") != ACTIVATION_ID
        or handoff.get("active_generation") != 1
        or handoff.get("active_build_version") != BUILD_VERSION
        or handoff.get("active_collection") != COLLECTION_NAME
    ):
        raise ValueError("Wiki handoff authority does not match Candidate F generation 1")

    for key in (
        "activation_receipt",
        "active_pointer",
        "candidate_build_manifest",
        "media_v3_manifest",
        "wiki_compatibility_receipt",
        "wiki_pre_import_rollback_receipt",
    ):
        ref = handoff.get(key)
        if not isinstance(ref, Mapping):
            raise ValueError(f"Wiki handoff lacks {key}")
        _verify_ref(root, ref)

    pointer_ref = handoff["active_pointer"]
    if str(pointer_ref.get("sha256")) != EXPECTED_POINTER_SHA256:
        raise ValueError("active pointer pin differs from the approved generation 1 pointer")
    pointer = _load_json(_verify_ref(root, pointer_ref))
    if (
        pointer.get("schema_version") != "evb.active-build/v1"
        or pointer.get("generation") != 1
        or pointer.get("activation_id") != ACTIVATION_ID
        or pointer.get("build_version") != BUILD_VERSION
        or pointer.get("artifact_schema_version") != ARTIFACT_SCHEMA
        or pointer.get("milvus_collection_name") != COLLECTION_NAME
    ):
        raise ValueError("active pointer tuple differs from Wiki handoff")

    media_manifest = _load_json(_verify_ref(root, handoff["media_v3_manifest"]))
    if (
        media_manifest.get("schema_version") != "evb.media-artifact-manifest/v3"
        or media_manifest.get("binding_count") != EXPECTED_COUNTS["wiki_media_bindings"]
        or media_manifest.get("resource_count") != EXPECTED_COUNTS["wiki_media_resources"]
    ):
        raise ValueError("media v3 manifest counts or schema differ from the approved import")

    rollback_ref = handoff["wiki_pre_import_rollback_receipt"]
    if str(rollback_ref.get("sha256")) != EXPECTED_ROLLBACK_SHA256:
        raise ValueError("Wiki rollback receipt pin differs from the approved receipt")
    rollback_path = _verify_ref(root, rollback_ref)
    rollback = validate_passing_receipt(rollback_path, project_root=root)
    current = inspect_container(SOURCE_CONTAINER)
    expected_authority = rollback.get("source_authority") or {}
    if (
        current.get("container_id") != expected_authority.get("container_id")
        or current.get("image_id") != expected_authority.get("image_id")
        or current.get("status") != "running"
        or current.get("health") not in {"", "healthy"}
        or expected_authority.get("database") != SOURCE_DATABASE
    ):
        raise ValueError("production MySQL authority differs from the rollback receipt")
    return handoff, rollback


def query_database_state(cfg: Any) -> dict[str, Any]:
    import pymysql

    conn = pymysql.connect(
        host=cfg.mysql.host,
        port=cfg.mysql.port,
        user=cfg.mysql.user,
        password=cfg.mysql.password,
        database=cfg.mysql.database,
        charset=cfg.mysql.charset,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = {str(next(iter(row.values()))) for row in cur.fetchall()}
            counts: dict[str, int | None] = {}
            for table in EXPECTED_COUNTS:
                if table not in tables:
                    counts[table] = None
                    continue
                cur.execute(f"SELECT COUNT(*) AS row_count FROM `{table}`")
                counts[table] = int((cur.fetchone() or {}).get("row_count", 0))
            snapshot = None
            if "wiki_import_snapshots" in tables:
                cur.execute("SELECT * FROM wiki_import_snapshots WHERE id=1")
                snapshot = cur.fetchone()
    finally:
        conn.close()
    return {"tables": sorted(tables), "counts": counts, "snapshot": snapshot}


def validate_payload(payload: WikiImportPayload) -> dict[str, int]:
    counts = {
        "wiki_pages": len(payload.pages),
        "wiki_categories": len(payload.categories),
        "wiki_media_resources": len(payload.media_resources),
        "wiki_media_bindings": len(payload.media_bindings),
    }
    for key, expected in EXPECTED_COUNTS.items():
        if key == "wiki_media_links":
            continue
        if counts.get(key) != expected:
            raise ValueError(f"formal Wiki payload count mismatch: {key}")
    if not payload.full_replace or payload.snapshot is None:
        raise ValueError("formal Wiki import requires an authoritative snapshot payload")

    page_ids = [str(row["page_id"]) for row in payload.pages]
    routes = [str(row["route"]) for row in payload.pages]
    resource_ids = [str(row["resource_id"]) for row in payload.media_resources]
    binding_ids = [str(row["binding_id"]) for row in payload.media_bindings]
    for label, values in (
        ("page_id", page_ids),
        ("route", routes),
        ("resource_id", resource_ids),
        ("binding_id", binding_ids),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label} in formal Wiki payload")
    page_set = set(page_ids)
    resource_set = set(resource_ids)
    if any(str(row["page_id"]) not in page_set for row in payload.media_bindings):
        raise ValueError("Wiki media binding references a missing page")
    if any(str(row["resource_id"]) not in resource_set for row in payload.media_bindings):
        raise ValueError("Wiki media binding references a missing resource")
    return counts


def _snapshot_is_target(snapshot: Mapping[str, Any] | None, expected_sha256: str) -> bool:
    return bool(
        snapshot
        and snapshot.get("source_mode") == "active"
        and snapshot.get("build_version") == BUILD_VERSION
        and snapshot.get("artifact_schema_version") == ARTIFACT_SCHEMA
        and int(snapshot.get("activation_epoch") or -1) == 1
        and snapshot.get("snapshot_sha256") == expected_sha256
    )


def _validate_database_prestate(
    state: Mapping[str, Any],
    rollback: Mapping[str, Any],
    snapshot: WikiArtifactSnapshot,
) -> bool:
    counts = state["counts"]
    already_installed = _snapshot_is_target(state.get("snapshot"), snapshot.snapshot_sha256)
    if already_installed:
        for key, expected in EXPECTED_COUNTS.items():
            if counts.get(key) != expected:
                raise ValueError(f"installed Wiki v3 count drift: {key}")
        return True

    installed = rollback.get("installed_snapshot") or {}
    current = state.get("snapshot") or {}
    for key in ("source_mode", "build_version", "artifact_schema_version", "snapshot_sha256"):
        if current.get(key) != installed.get(key):
            raise ValueError("production Wiki snapshot differs from the pre-import rollback baseline")
    for key in ("wiki_pages", "wiki_categories", "wiki_media_links"):
        if counts.get(key) != EXPECTED_COUNTS[key]:
            raise ValueError(f"production Wiki pre-import count drift: {key}")
    for key in ("wiki_media_resources", "wiki_media_bindings"):
        if counts.get(key) not in {None, 0}:
            raise ValueError(f"partial Wiki v3 state exists before import: {key}")
    return False


def prepare_formal_import(
    cfg: Any,
    *,
    project_root: Path,
    handoff_path: Path,
    expected_handoff_sha256: str = EXPECTED_HANDOFF_SHA256,
) -> FormalImportContext:
    root = Path(project_root).resolve()
    authority, rollback = validate_import_authority(
        root,
        handoff_path,
        expected_handoff_sha256=expected_handoff_sha256,
    )
    snapshot = resolve_wiki_snapshot(
        cfg,
        root,
        root / "data/processed/huiji/evidence/wiki-import",
    )
    if (
        snapshot.source_mode != "active"
        or snapshot.generation != 1
        or snapshot.activation_id != ACTIVATION_ID
        or snapshot.build_version != BUILD_VERSION
        or snapshot.artifact_schema_version != ARTIFACT_SCHEMA
        or snapshot.pointer_sha256 != EXPECTED_POINTER_SHA256
    ):
        raise ValueError("resolved Wiki snapshot differs from the approved active generation")
    payload = build_wiki_import_payload(
        snapshot,
        include_character=True,
        raw_root=cfg.huiji.raw_root,
        asset_public_base_url=cfg.assets.public_base_url,
        asset_bucket_name=cfg.assets.bucket_name,
        asset_object_prefix=cfg.assets.object_prefix,
    )
    validate_payload(payload)
    database_before = query_database_state(cfg)
    already_installed = _validate_database_prestate(database_before, rollback, snapshot)
    inventory_before = collect_mysql_inventory(
        DockerMysqlClient(SOURCE_CONTAINER),
        SOURCE_DATABASE,
    )
    if not already_installed and inventory_before.get("inventory_sha256") != rollback.get("source_inventory_sha256"):
        raise ValueError("production Wiki inventory differs from the verified rollback baseline")
    return FormalImportContext(
        authority=authority,
        rollback_receipt=rollback,
        snapshot=snapshot,
        payload=payload,
        database_before=database_before,
        inventory_before=inventory_before,
        already_installed=already_installed,
    )


def install_media_v3_schema(cfg: Any) -> None:
    import pymysql

    conn = pymysql.connect(
        host=cfg.mysql.host,
        port=cfg.mysql.port,
        user=cfg.mysql.user,
        password=cfg.mysql.password,
        database=cfg.mysql.database,
        charset=cfg.mysql.charset,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            for statement in media_v3_schema_statements():
                cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def apply_formal_import(cfg: Any, context: FormalImportContext) -> dict[str, Any]:
    if context.already_installed:
        return {
            "status": "already_installed",
            "snapshot_sha256": context.snapshot.snapshot_sha256,
            "counts": dict(context.database_before["counts"]),
        }
    install_media_v3_schema(cfg)
    after_schema = query_database_state(cfg)
    for table in ("wiki_media_resources", "wiki_media_bindings"):
        if after_schema["counts"].get(table) != 0:
            raise ValueError(f"new Wiki v3 table is not empty: {table}")

    result = import_payload_to_mysql(context.payload, cfg)
    after = query_database_state(cfg)
    for key, expected in EXPECTED_COUNTS.items():
        if after["counts"].get(key) != expected:
            raise ValueError(f"formal Wiki import post-count mismatch: {key}")
    if not _snapshot_is_target(after.get("snapshot"), context.snapshot.snapshot_sha256):
        raise ValueError("formal Wiki import installed snapshot mismatch")
    inventory_after = collect_mysql_inventory(
        DockerMysqlClient(SOURCE_CONTAINER),
        SOURCE_DATABASE,
    )
    return {
        "status": "committed",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "activation_id": ACTIVATION_ID,
        "build_version": BUILD_VERSION,
        "snapshot_sha256": context.snapshot.snapshot_sha256,
        "import_result": result,
        "counts": dict(after["counts"]),
        "inventory_before_sha256": context.inventory_before["inventory_sha256"],
        "inventory_after_sha256": inventory_after["inventory_sha256"],
        "database_after": after,
    }


def inspection_payload(context: FormalImportContext) -> dict[str, Any]:
    return {
        "schema_version": "huiji.wiki-v3-formal-import-inspection/v1",
        "status": "already_installed" if context.already_installed else "ready",
        "activation_id": ACTIVATION_ID,
        "build_version": BUILD_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA,
        "snapshot_sha256": context.snapshot.snapshot_sha256,
        "payload_counts": validate_payload(context.payload),
        "database_before": context.database_before,
        "inventory_before_sha256": context.inventory_before["inventory_sha256"],
        "rollback_inventory_sha256": context.rollback_receipt["source_inventory_sha256"],
    }


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_create_new(path: Path, payload: Mapping[str, Any]) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json_bytes(payload)
    with path.open("xb") as handle:
        handle.write(encoded)
    return hashlib.sha256(encoded).hexdigest()

