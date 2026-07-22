"""Read-only artifact inventory and Milvus snapshot support."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import unquote, urlsplit

import requests
from pymilvus import MilvusClient

from config.config import Config
from src.huiji_rag.io import iter_jsonl
from src.huiji_rag.minio_strict import capture_object_inventory
from src.rag.packet_policy import CHARACTER_POLICIES
from src.rag.source_labels import format_source_label
from src.rag_eval.contracts import EvaluationEvent, JudgeIdentity, Severity, worst_severity


class InventoryError(ValueError):
    """Raised when frozen artifacts cannot define trustworthy expectations."""


@dataclass(frozen=True)
class ChildRecord:
    child_id: str
    parent_id: str
    entity_id: str
    entity_name: str
    entity_type: str
    category: str
    section_kind: str
    title: str
    route_tags: tuple[str, ...]
    text: str
    media_ids: tuple[str, ...]


@dataclass(frozen=True)
class MediaRecord:
    media_id: str
    entity_id: str
    entity_name: str
    parent_id: str
    child_id: str
    asset_type: str
    mime: str
    url: str
    is_available: bool
    is_common: bool
    language: str
    event_name: str
    sort_order: int


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    entity_name: str
    entity_type: str
    category: str
    aliases: tuple[str, ...]
    child_ids_by_intent: Mapping[str, tuple[str, ...]]
    media_ids_by_type: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class EvaluationInventory:
    build_version: str
    entities: Mapping[str, EntityRecord]
    children: Mapping[str, ChildRecord]
    media: Mapping[str, tuple[MediaRecord, ...]]
    parent_ids: tuple[str, ...]
    sha256: str
    build_manifest_sha256: str = ""


@dataclass(frozen=True)
class MilvusSnapshot:
    collection_name: str
    schema_sha256: str
    row_count: int
    primary_field: str
    primary_id_count: int
    primary_ids_sha256: str
    load_state: Mapping[str, object]
    captured_at_utc: str
    schema_version: str = "rag_eval.milvus_snapshot/v1"

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProtectedDataSnapshot:
    milvus: MilvusSnapshot | object
    minio_inventories: Mapping[str, Mapping[str, object]]
    mysql_tables: Mapping[str, Mapping[str, object]]
    artifacts: Mapping[str, Mapping[str, object]]
    captured_at_utc: str = field(default_factory=lambda: _utc_now())
    schema_version: str = "rag_eval.protected_snapshot/v2"

    def to_json(self) -> dict[str, object]:
        milvus_json = getattr(self.milvus, "to_json", None)
        return {
            "schema_version": self.schema_version,
            "milvus": milvus_json() if callable(milvus_json) else asdict(self.milvus),
            "minio_inventories": dict(self.minio_inventories),
            "mysql_tables": dict(self.mysql_tables),
            "artifacts": dict(self.artifacts),
            "captured_at_utc": self.captured_at_utc,
        }


@dataclass(frozen=True)
class PreflightResult:
    allowed_to_run: bool
    severity: Severity
    events: tuple[EvaluationEvent, ...]
    backend_health: Mapping[str, object] = field(default_factory=dict)
    minio_ready: bool = False
    inventory: EvaluationInventory | object | None = None
    snapshot: MilvusSnapshot | object | None = None


_SECTION_INTENTS: dict[str, tuple[str, ...]] = {}
for _intent, _policy in CHARACTER_POLICIES.items():
    for _section in _policy.sections:
        _SECTION_INTENTS.setdefault(_section, ())
        if _intent not in _SECTION_INTENTS[_section]:
            _SECTION_INTENTS[_section] = (*_SECTION_INTENTS[_section], _intent)
_SECTION_INTENTS.update(
    {
        "skill": ("skill",),
        "ultimate": ("skill",),
        "item": ("item",),
        "psychube": ("psychube",),
        "story": ("story",),
    }
)


def build_inventory(
    parent_rows: Iterable[Mapping[str, object]],
    child_rows: Iterable[Mapping[str, object]],
    media_rows: Iterable[Mapping[str, object]],
    *,
    build_version: str,
    build_manifest_sha256: str = "",
) -> EvaluationInventory:
    parents: dict[str, Mapping[str, object]] = {}
    entity_meta: dict[str, dict[str, object]] = {}
    for row in parent_rows:
        parent_id = str(row.get("parent_id") or "")
        if not parent_id:
            raise InventoryError("parent row has blank parent_id")
        if parent_id in parents:
            raise InventoryError(f"duplicate parent_id: {parent_id}")
        parents[parent_id] = row
        entity_id = str(row.get("entity_id") or "")
        if entity_id:
            meta = entity_meta.setdefault(
                entity_id,
                {
                    "name": str(row.get("entity_name") or ""),
                    "type": str(row.get("entity_type") or ""),
                    "category": str(row.get("category") or ""),
                    "aliases": set(),
                },
            )
            meta["aliases"].update(_string_values(row.get("entity_aliases")))  # type: ignore[union-attr]

    children: dict[str, ChildRecord] = {}
    entity_intents: dict[str, dict[str, list[str]]] = {}
    for row in child_rows:
        child_id = str(row.get("child_id") or "")
        parent_id = str(row.get("parent_id") or "")
        entity_id = str(row.get("entity_id") or "")
        if not child_id or not parent_id or not entity_id:
            raise InventoryError("child row has blank child_id, parent_id, or entity_id")
        if child_id in children:
            raise InventoryError(f"duplicate child_id: {child_id}")
        if parent_id not in parents:
            raise InventoryError(f"child {child_id} references unknown parent {parent_id}")
        section = str(row.get("section_kind") or "")
        route_tags = _string_values(row.get("route_tags"))
        record = ChildRecord(
            child_id=child_id,
            parent_id=parent_id,
            entity_id=entity_id,
            entity_name=str(row.get("entity_name") or ""),
            entity_type=str(row.get("entity_type") or ""),
            category=str(row.get("category") or ""),
            section_kind=section,
            title=str(row.get("title") or ""),
            route_tags=route_tags,
            text=str(row.get("text") or row.get("content") or ""),
            media_ids=_string_values(row.get("media_ids")),
        )
        children[child_id] = record
        meta = entity_meta.setdefault(
            entity_id,
            {
                "name": record.entity_name,
                "type": record.entity_type,
                "category": record.category,
                "aliases": set(),
            },
        )
        if not str(meta.get("name") or ""):
            meta["name"] = record.entity_name
        intents = tuple(dict.fromkeys((*route_tags, *_SECTION_INTENTS.get(section, ()))))
        buckets = entity_intents.setdefault(entity_id, {})
        for intent in intents:
            buckets.setdefault(intent, []).append(child_id)

    occurrences: dict[str, list[MediaRecord]] = {}
    entity_media: dict[str, dict[str, list[str]]] = {}
    for row in media_rows:
        media_id = str(row.get("media_id") or "")
        child_id = str(row.get("child_id") or "")
        entity_id = str(row.get("entity_id") or "")
        if not media_id or not child_id or not entity_id:
            raise InventoryError("media row has blank media_id, child_id, or entity_id")
        if child_id not in children:
            raise InventoryError(f"media {media_id} references unknown child {child_id}")
        url = str(row.get("url") or "")
        if bool(row.get("is_available")) and not _safe_http_url(url):
            raise InventoryError(f"available media {media_id} has unsafe URL")
        asset_type = _media_type(row)
        record = MediaRecord(
            media_id=media_id,
            entity_id=entity_id,
            entity_name=str(row.get("entity_name") or ""),
            parent_id=str(row.get("parent_id") or ""),
            child_id=child_id,
            asset_type=asset_type,
            mime=str(row.get("mime") or ""),
            url=url,
            is_available=bool(row.get("is_available")),
            is_common=bool(row.get("is_common")),
            language=str(row.get("language") or ""),
            event_name=str(row.get("event_name") or ""),
            sort_order=int(row.get("sort_order") or 0),
        )
        occurrences.setdefault(media_id, []).append(record)
        if record.is_available and not record.is_common:
            bucket = entity_media.setdefault(entity_id, {}).setdefault(asset_type, [])
            if media_id not in bucket:
                bucket.append(media_id)

    known_media_ids = set(occurrences)
    for child in children.values():
        missing = sorted(set(child.media_ids) - known_media_ids)
        if missing:
            raise InventoryError(
                f"child {child.child_id} references unknown media: {', '.join(missing[:3])}"
            )

    entities: dict[str, EntityRecord] = {}
    for entity_id in sorted(set(entity_meta) | set(entity_intents) | set(entity_media)):
        meta = entity_meta.get(entity_id, {})
        name = str(meta.get("name") or "")
        if not name:
            raise InventoryError(f"entity {entity_id} has blank entity_name")
        intents = {
            key: tuple(dict.fromkeys(values))
            for key, values in sorted(entity_intents.get(entity_id, {}).items())
        }
        media_types = {
            key: tuple(values)
            for key, values in sorted(entity_media.get(entity_id, {}).items())
        }
        entities[entity_id] = EntityRecord(
            entity_id=entity_id,
            entity_name=name,
            entity_type=str(meta.get("type") or ""),
            category=str(meta.get("category") or ""),
            aliases=tuple(sorted(meta.get("aliases") or ())),
            child_ids_by_intent=intents,
            media_ids_by_type=media_types,
        )

    frozen_media = {
        key: tuple(sorted(values, key=lambda item: (item.child_id, item.language, item.sort_order)))
        for key, values in sorted(occurrences.items())
    }
    projection = {
        "build_version": build_version,
        "parents": sorted(parents),
        "children": [asdict(children[key]) for key in sorted(children)],
        "media": [asdict(item) for key in sorted(frozen_media) for item in frozen_media[key]],
    }
    return EvaluationInventory(
        build_version=build_version,
        entities=entities,
        children=children,
        media=frozen_media,
        parent_ids=tuple(sorted(parents)),
        sha256=_sha256(_canonical_bytes(projection)),
        build_manifest_sha256=build_manifest_sha256,
    )


def capture_inventory(cfg: Config) -> EvaluationInventory:
    from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot

    snapshot = resolve_runtime_artifact_snapshot(cfg)
    required = (snapshot.parent_blocks, snapshot.child_blocks, snapshot.media_assets)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise InventoryError(f"required artifacts missing: {', '.join(missing)}")
    return build_inventory(
        iter_jsonl(snapshot.parent_blocks),
        iter_jsonl(snapshot.child_blocks),
        iter_jsonl(snapshot.media_assets),
        build_version=snapshot.build_version,
        build_manifest_sha256=snapshot.manifest_sha256,
    )


def reconstruct_context(
    inventory: EvaluationInventory,
    observed_sources: Iterable[Mapping[str, object]],
) -> str:
    parts: list[str] = []
    for source in observed_sources:
        child_id = str(source.get("child_id") or "")
        child = inventory.children.get(child_id)
        if child is None:
            raise InventoryError(f"unresolved source child_id: {child_id}")
        label = format_source_label(
            str(source.get("name") or child.entity_name),
            str(source.get("heading_path") or ""),
        )
        citation_id = str(source.get("citation_id") or "")
        if citation_id:
            parts.append(f"[{citation_id}] {label}\n{child.text}")
        else:
            parts.append(f"[{label}] {child.text}")
    return "\n\n".join(parts)


def capture_milvus_snapshot_from_client(
    client: object,
    collection_name: str,
) -> MilvusSnapshot:
    if not bool(client.has_collection(collection_name)):
        raise InventoryError(f"Milvus collection does not exist: {collection_name}")
    schema = client.describe_collection(collection_name)
    fields = schema.get("fields") if isinstance(schema, dict) else None
    primary = next(
        (
            str(field.get("name"))
            for field in fields or ()
            if isinstance(field, dict) and field.get("is_primary")
        ),
        "",
    )
    if not primary:
        raise InventoryError(f"Milvus collection {collection_name} lacks a primary field")
    iterator = client.query_iterator(
        collection_name=collection_name,
        batch_size=1000,
        limit=-1,
        filter="",
        output_fields=[primary],
    )
    values: list[str] = []
    try:
        while True:
            batch = iterator.next()
            if not batch:
                break
            for row in batch:
                if primary not in row:
                    raise InventoryError("Milvus primary-key query returned a row without primary key")
                values.append(str(row[primary]))
    finally:
        iterator.close()
    if len(values) != len(set(values)):
        raise InventoryError("Milvus primary-key query returned duplicate IDs")
    stats = client.get_collection_stats(collection_name)
    row_count = int(stats.get("row_count", 0))
    if row_count != len(values):
        raise InventoryError(
            f"Milvus row count differs from primary-key count: {row_count} != {len(values)}"
        )
    return MilvusSnapshot(
        collection_name=collection_name,
        schema_sha256=_sha256(_canonical_bytes(schema)),
        row_count=row_count,
        primary_field=primary,
        primary_id_count=len(values),
        primary_ids_sha256=_sha256_lines(values),
        load_state=client.get_load_state(collection_name),
        captured_at_utc=_utc_now(),
    )


def capture_milvus_snapshot(cfg: Config) -> MilvusSnapshot:
    vectorstore = cfg.vectorstore
    client = MilvusClient(uri=str(vectorstore.uri), db_name=str(vectorstore.db_name))
    return capture_milvus_snapshot_from_client(client, str(vectorstore.collection_name))


def compare_snapshots(before: MilvusSnapshot, after: MilvusSnapshot) -> list[str]:
    changes: list[str] = []
    for field_name in (
        "collection_name",
        "schema_sha256",
        "row_count",
        "primary_field",
        "primary_id_count",
        "primary_ids_sha256",
        "load_state",
    ):
        if getattr(before, field_name) != getattr(after, field_name):
            changes.append(f"{field_name} changed")
    return changes


PROTECTED_MYSQL_TABLES = (
    "wiki_categories",
    "wiki_pages",
    "wiki_media_links",
    "wiki_import_snapshots",
    "wiki_aliases",
    "wiki_relations",
    "wiki_link_spans",
    "wiki_page_supplements",
    "wiki_supplement_snapshots",
)
_SAFE_SQL_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_ARTIFACT_INPUTS = (
    Path("eval/rag_full_chain_thresholds.v1.json"),
    Path("eval/rag_full_chain_boundary_seeds.v1.jsonl"),
)
_OPERATIONAL_ARTIFACT_EXCLUSIONS = frozenset(
    {
        Path(".generation-zero-bootstrap.lock"),
        Path(".candidate-activation.lock"),
    }
)


def _is_operational_artifact(relative: Path) -> bool:
    if relative in _OPERATIONAL_ARTIFACT_EXCLUSIONS:
        return True
    parts = relative.parts
    return bool(
        relative.suffix.casefold() == ".log"
        and len(parts) >= 5
        and parts[0:2] == ("activation", "transactions")
        and parts[-2] in {"runtime", "rollback-runtime"}
    )


def capture_protected_snapshot(
    cfg: Config | object,
    *,
    milvus_loader: Callable[[object], object] | None = None,
    minio_loader: Callable[[object], Mapping[str, Mapping[str, object]]] | None = None,
    mysql_loader: Callable[[object], Mapping[str, Mapping[str, object]]] | None = None,
    artifact_loader: Callable[[object], Mapping[str, Mapping[str, object]]] | None = None,
) -> ProtectedDataSnapshot:
    return ProtectedDataSnapshot(
        milvus=(milvus_loader or capture_milvus_snapshot)(cfg),
        minio_inventories=(minio_loader or capture_configured_minio_inventories)(cfg),
        mysql_tables=(mysql_loader or capture_mysql_table_digests)(cfg),
        artifacts=(artifact_loader or capture_artifact_digests)(cfg),
    )


def compare_protected_snapshots(
    before: ProtectedDataSnapshot,
    after: ProtectedDataSnapshot,
) -> list[str]:
    changes = compare_snapshots(before.milvus, after.milvus)
    sections = (
        ("minio_inventories", _stable_minio_projection),
        ("mysql_tables", lambda value: value),
        ("artifacts", lambda value: value),
    )
    for name, normalize in sections:
        if normalize(getattr(before, name)) != normalize(getattr(after, name)):
            changes.append(f"{name} changed")
    return changes


def capture_configured_minio_inventories(
    cfg: Config | object,
    *,
    client_factory: Callable[[object], object] | None = None,
    inventory_loader: Callable[[object, str, str], object] = capture_object_inventory,
) -> Mapping[str, Mapping[str, object]]:
    assets = getattr(cfg, "assets", None)
    if assets is None:
        raise InventoryError("asset storage configuration is missing")
    if client_factory is None:
        from minio import Minio

        client = Minio(
            str(getattr(assets, "endpoint", "")),
            access_key=str(getattr(assets, "access_key", "")),
            secret_key=str(getattr(assets, "secret_key", "")),
            secure=bool(getattr(assets, "secure", False)),
        )
    else:
        client = client_factory(cfg)
    configured_scopes = getattr(cfg, "rag_eval_minio_scopes", None)
    scopes = configured_scopes or (
        (
            str(getattr(assets, "bucket_name", "")),
            str(getattr(assets, "object_prefix", "")),
        ),
        ("a-bucket", ""),
    )
    output: dict[str, Mapping[str, object]] = {}
    for bucket, prefix in scopes:
        bucket_name = str(bucket)
        object_prefix = str(prefix).strip("/")
        if not bucket_name:
            raise InventoryError("protected MinIO bucket is blank")
        inventory = inventory_loader(client, bucket_name, object_prefix)
        serializer = getattr(inventory, "to_json", None)
        payload = serializer() if callable(serializer) else inventory
        if not isinstance(payload, Mapping):
            raise InventoryError("MinIO inventory is not serializable")
        output[f"{bucket_name}/{object_prefix}".rstrip("/")] = dict(payload)
    return output


def capture_mysql_table_digests(
    cfg: Config | object,
    *,
    tables: tuple[str, ...] = PROTECTED_MYSQL_TABLES,
    connection_factory: Callable[[object], object] | None = None,
) -> Mapping[str, Mapping[str, object]]:
    for table in tables:
        if not _SAFE_SQL_NAME_RE.fullmatch(table):
            raise InventoryError(f"unsafe protected table name: {table}")
    if connection_factory is None:
        import pymysql

        mysql = getattr(cfg, "mysql", None)
        if mysql is None:
            raise InventoryError("MySQL configuration is missing")
        connection = pymysql.connect(
            host=str(getattr(mysql, "host", "")),
            port=int(getattr(mysql, "port", 3306)),
            user=str(getattr(mysql, "user", "")),
            password=str(getattr(mysql, "password", "")),
            database=str(getattr(mysql, "database", "")),
            charset=str(getattr(mysql, "charset", "utf8mb4")),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    else:
        connection = connection_factory(cfg)

    output: dict[str, Mapping[str, object]] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            for table in tables:
                try:
                    cursor.execute(
                        f"SHOW KEYS FROM `{table}` WHERE Key_name = 'PRIMARY'"
                    )
                except Exception as error:
                    if getattr(error, "args", ())[:1] == (1146,):
                        output[table] = {"status": "absent"}
                        continue
                    raise
                key_rows = cursor.fetchall()
                primary_keys = tuple(
                    str(row.get("Column_name") or "")
                    for row in key_rows
                    if isinstance(row, Mapping) and row.get("Column_name")
                )
                if not primary_keys:
                    raise InventoryError(f"protected table lacks a primary key: {table}")
                order_by = ", ".join(f"`{key}`" for key in primary_keys)
                cursor.execute(f"SELECT * FROM `{table}` ORDER BY {order_by}")
                rows = cursor.fetchall()
                digest = hashlib.sha256()
                count = 0
                for row in rows:
                    digest.update(_canonical_bytes(_json_safe_row(row)))
                    digest.update(b"\n")
                    count += 1
                output[table] = {
                    "row_count": count,
                    "sha256": digest.hexdigest(),
                }
    except Exception:
        connection.rollback()
        raise
    else:
        connection.rollback()
    finally:
        connection.close()
    return output


def capture_artifact_digests(
    cfg: Config | object,
) -> Mapping[str, Mapping[str, object]]:
    paths = getattr(cfg, "paths", None)
    project_root = Path(getattr(paths, "project_root", Path.cwd())).resolve()
    huiji = getattr(cfg, "huiji", None)
    processed_root = Path(
        getattr(huiji, "processed_root", project_root / "data" / "processed" / "huiji")
    ).resolve()
    candidates: set[Path] = set()
    for relative in _ARTIFACT_INPUTS:
        candidate = (project_root / relative).resolve()
        if candidate.is_file():
            candidates.add(candidate)
    if processed_root.is_dir():
        for candidate in processed_root.rglob("*"):
            if candidate.is_file():
                resolved = candidate.resolve()
                try:
                    processed_relative = resolved.relative_to(processed_root)
                except ValueError as error:
                    raise InventoryError("processed artifact escapes configured root") from error
                if _is_operational_artifact(processed_relative):
                    continue
                candidates.add(resolved)

    output: dict[str, Mapping[str, object]] = {}
    for path in sorted(candidates, key=lambda item: item.as_posix()):
        try:
            relative = path.relative_to(project_root).as_posix()
        except ValueError as error:
            raise InventoryError("protected artifact escapes project root") from error
        output[relative] = {
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    return output


def _stable_minio_projection(
    values: Mapping[str, Mapping[str, object]],
) -> Mapping[str, Mapping[str, object]]:
    return {
        key: {
            item_key: item_value
            for item_key, item_value in value.items()
            if item_key not in {"captured_at_utc", "inventory_sha256"}
        }
        for key, value in values.items()
    }


def _json_safe_row(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_row(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_row(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_preflight(
    cfg: object,
    base_url: str,
    judge_identity: JudgeIdentity | None,
    *,
    backend_health: Callable[[str], Mapping[str, object]] | None = None,
    minio_health: Callable[[str], bool] | None = None,
    inventory_loader: Callable[[object], object] | None = None,
    snapshot_loader: Callable[[object], object] | None = None,
) -> PreflightResult:
    events: list[EvaluationEvent] = []
    backend_fetch = backend_health or _fetch_json
    minio_fetch = minio_health or _fetch_ready
    inventory_fn = inventory_loader or capture_inventory
    snapshot_fn = snapshot_loader or capture_protected_snapshot
    health: Mapping[str, object] = {}
    minio_ready = False
    inventory: object | None = None
    snapshot: object | None = None

    try:
        health = backend_fetch(f"{base_url.rstrip('/')}/health")
        if not (
            health.get("status") == "ok"
            and health.get("vectorstore_loaded") is True
            and health.get("llm_ready") is True
        ):
            raise InventoryError("backend health is not ready")
    except Exception as error:
        events.append(_ready_event("READY.BACKEND_UNAVAILABLE", str(error)))

    minio_base = str(getattr(getattr(cfg, "assets", None), "public_base_url", ""))
    try:
        minio_ready = minio_fetch(f"{minio_base.rstrip('/')}/minio/health/ready")
        if not minio_ready:
            raise InventoryError("MinIO health is not ready")
    except Exception as error:
        events.append(_ready_event("READY.MINIO_UNAVAILABLE", str(error)))

    llm = getattr(cfg, "llm", None)
    if not str(getattr(llm, "api_key", "")):
        events.append(_ready_event("READY.ANSWER_MODEL_UNAVAILABLE", "answer model API key missing"))
    if judge_identity is None:
        events.append(_ready_event("READY.JUDGE_UNAVAILABLE", "judge identity missing"))
    elif (
        judge_identity.base_url.rstrip("/"),
        judge_identity.model,
    ) == (
        str(getattr(llm, "base_url", "")).rstrip("/"),
        str(getattr(llm, "model", "")),
    ):
        events.append(_ready_event("READY.JUDGE_NOT_INDEPENDENT", "judge matches production model"))

    if not events:
        try:
            inventory = inventory_fn(cfg)
            snapshot = snapshot_fn(cfg)
        except Exception as error:
            events.append(_ready_event("READY.DATA_UNAVAILABLE", str(error)))

    severity = worst_severity([event.severity for event in events])
    return PreflightResult(
        allowed_to_run=not events,
        severity=severity,
        events=tuple(events),
        backend_health=health,
        minio_ready=minio_ready,
        inventory=inventory,
        snapshot=snapshot,
    )


def _ready_event(code: str, message: str) -> EvaluationEvent:
    return EvaluationEvent.create(
        code,
        "M1",
        Severity.SEV0,
        observed={"message": message},
        recommended_action="restore evaluation prerequisites before sending sampled requests",
    )


def _fetch_json(url: str) -> Mapping[str, object]:
    session = requests.Session()
    session.trust_env = False
    response = session.get(url, timeout=(3.0, 10.0))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise InventoryError("health response is not a JSON object")
    return payload


def _fetch_ready(url: str) -> bool:
    session = requests.Session()
    session.trust_env = False
    response = session.get(url, timeout=(3.0, 10.0))
    return response.ok


def _string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(dict.fromkeys(str(item) for item in value if str(item)))
    return ()


def _media_type(row: Mapping[str, object]) -> str:
    asset_type = str(row.get("asset_type") or row.get("role") or "").lower()
    mime = str(row.get("mime") or "").lower()
    if asset_type in {"voice", "audio"} or mime.startswith("audio/"):
        return "voice"
    if asset_type == "video" or mime.startswith("video/"):
        return "video"
    if mime.startswith("image/") or asset_type in {"portrait", "skill", "skin", "image", "media"}:
        return "image" if asset_type == "media" else asset_type
    return asset_type


def _safe_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return False
    decoded = unquote(parsed.netloc + parsed.path).replace("\\", "/")
    lowered = decoded.lower()
    return "file:" not in lowered and "/../" not in lowered and not lowered.endswith("/..")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_lines(values: Iterable[str]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    return _sha256(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
