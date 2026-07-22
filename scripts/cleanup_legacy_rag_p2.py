"""One-time, evidence-bound cleanup for the retired local RAG corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minio import Minio
from minio.error import S3Error
from pymilvus import MilvusClient

from config.config import get_config
from src.huiji_rag.minio_strict import capture_object_inventory
from src.rag_eval.inventory import PROTECTED_MYSQL_TABLES


ROOT = Path(__file__).resolve().parents[1]
LOCAL_CANDIDATES = (
    "data/raw",
    "data/processed/documents.jsonl",
    "data/processed/assets.jsonl",
)
PROBE_MARKERS = ("_evb_capability_probe", "minio-capability", "capability-probe")
HEX40 = re.compile(r"[0-9a-f]{40}\Z", re.IGNORECASE)
HEX64 = re.compile(r"[0-9a-f]{64}\Z", re.IGNORECASE)
REQUIRED_OBJECT_FIELDS = (
    "object_key",
    "size",
    "sha1",
    "sha256",
    "etag",
    "version_id",
    "application_operation_id",
    "audit_event_id",
)
P2_REQUIREMENTS = (
    *(f"CLEAN-INVENTORY-P0-0{i}" for i in range(1, 7)),
    *(f"CLEAN-BACKUP-P0-0{i}" for i in range(1, 8)),
    "CLEAN-PLAN-P0-01",
    "CLEAN-PLAN-P0-02",
    *(f"CLEAN-APPLY-P0-0{i}" for i in range(1, 6)),
    *(f"CLEAN-VERIFY-P0-0{i}" for i in range(1, 7)),
)


class CleanupBlocked(RuntimeError):
    def __init__(self, message: str, diagnostics: Mapping[str, object] | None = None):
        self.diagnostics = dict(diagnostics or {})
        super().__init__(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            _json_safe(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _set_fingerprint(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(set(str(item) for item in values)):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_pinned_json(path: Path, payload: Mapping[str, object]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = canonical_json_bytes(payload)
    digest = hashlib.sha256(body).hexdigest()
    with target.open("xb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    sidecar = target.with_name(target.name + ".sha256")
    with sidecar.open("xb") as handle:
        handle.write(f"{digest}  {target.name}\n".encode("ascii"))
        handle.flush()
        os.fsync(handle.fileno())
    return digest


def _load_json(path: Path, *, require_sidecar: bool = True) -> dict[str, Any]:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise CleanupBlocked(f"evidence is not a JSON object: {target.name}")
    if require_sidecar:
        sidecar = target.with_name(target.name + ".sha256")
        if not sidecar.is_file():
            raise CleanupBlocked(f"evidence sidecar is missing: {target.name}")
        expected = sidecar.read_text(encoding="ascii").split()[0].lower()
        if sha256_file(target) != expected:
            raise CleanupBlocked(f"evidence hash mismatch: {target.name}")
    return payload


def assert_plan_hash(path: Path, expected_sha256: str) -> str:
    expected = str(expected_sha256).strip().lower()
    if not HEX64.fullmatch(expected):
        raise CleanupBlocked("expected plan hash is invalid")
    actual = sha256_file(Path(path))
    if actual != expected:
        raise CleanupBlocked("operation plan hash mismatch")
    return actual


def resolve_within(root: Path, relative: str | Path) -> Path:
    base = Path(root).resolve()
    candidate = (base / Path(relative)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise CleanupBlocked("path escapes approved root") from error
    return candidate


def validate_complete_object(value: Mapping[str, object]) -> None:
    missing = [field for field in REQUIRED_OBJECT_FIELDS if field not in value]
    if missing:
        raise CleanupBlocked(f"inventory object lacks {', '.join(missing)}")
    key = str(value.get("object_key") or "")
    if not key or key.startswith("/") or ".." in Path(key).parts:
        raise CleanupBlocked("inventory object key is unsafe")
    if int(value.get("size", -1)) < 0:
        raise CleanupBlocked("inventory object size is invalid")
    if not HEX40.fullmatch(str(value.get("sha1") or "")):
        raise CleanupBlocked("inventory object sha1 is invalid")
    if not HEX64.fullmatch(str(value.get("sha256") or "")):
        raise CleanupBlocked("inventory object sha256 is invalid")
    if not str(value.get("etag") or ""):
        raise CleanupBlocked("inventory object etag is empty")


def _is_probe(key: str) -> bool:
    lowered = key.casefold()
    return any(marker in lowered for marker in PROBE_MARKERS)


def classify_keys(
    *,
    remote_keys: Iterable[str],
    legacy_keys: Iterable[str],
    rag_keys: Iterable[str],
    wiki_keys: Iterable[str],
) -> dict[str, tuple[str, ...]]:
    remote = set(remote_keys)
    legacy = set(legacy_keys)
    rag = set(rag_keys)
    wiki = set(wiki_keys)
    active = rag | wiki
    missing_active = sorted(active - remote)
    if missing_active:
        raise CleanupBlocked(
            "active consumer object is missing remotely",
            {
                "missing_active_count": len(missing_active),
                "missing_active": missing_active,
                "expanded_prefixes": sorted({_parent_prefix(key) for key in missing_active}),
            },
        )
    candidates = remote & legacy - active
    probes = {key for key in remote if _is_probe(key)}
    candidates -= probes
    residual = remote - active - candidates - probes
    return {
        "delete_candidates": tuple(sorted(candidates)),
        "active_consumers": tuple(sorted(remote & active)),
        "capability_probes": tuple(sorted(probes)),
        "residual_orphans": tuple(sorted(residual)),
        "legacy_missing_remote": tuple(sorted(legacy - remote)),
    }


def _parent_prefix(key: str) -> str:
    parts = key.strip("/").split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else parts[0]


def validate_expected_hashes(
    remote_by_key: Mapping[str, Mapping[str, object]],
    expected_by_key: Mapping[str, Sequence[Mapping[str, object]]],
) -> None:
    mismatches: list[dict[str, object]] = []
    for key in sorted(set(remote_by_key) & set(expected_by_key)):
        remote = remote_by_key[key]
        for expected in expected_by_key[key]:
            reasons: list[str] = []
            sha1 = str(expected.get("sha1") or "").lower()
            sha256 = str(expected.get("sha256") or "").lower()
            size = expected.get("size")
            if sha1 and sha1 != str(remote.get("sha1") or "").lower():
                reasons.append("sha1")
            if sha256 and sha256 != str(remote.get("sha256") or "").lower():
                reasons.append("sha256")
            if size is not None and int(size) != int(remote.get("size", -1)):
                reasons.append("size")
            if reasons:
                mismatches.append(
                    {
                        "object_key": key,
                        "source": str(expected.get("source") or "unknown"),
                        "reasons": reasons,
                    }
                )
    if mismatches:
        prefixes = sorted({_parent_prefix(str(item["object_key"])) for item in mismatches})
        related = sorted(
            key
            for key in remote_by_key
            if any(key == prefix or key.startswith(prefix + "/") for prefix in prefixes)
        )
        raise CleanupBlocked(
            "content hash mismatch blocks cleanup planning",
            {
                "hash_mismatch_count": len(mismatches),
                "hash_mismatches": mismatches,
                "expanded_prefixes": prefixes,
                "related_keys": related,
            },
        )


def append_receipt(path: Path, payload: Mapping[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = canonical_json_bytes(payload)
    with target.open("ab") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def delete_exact_objects(
    client: object,
    bucket: str,
    objects: Sequence[Mapping[str, object]],
    receipt: Path,
) -> None:
    remover = getattr(client, "remove_object", None)
    if not callable(remover):
        raise CleanupBlocked("MinIO client lacks exact-key removal")
    for item in objects:
        validate_complete_object(item)
        key = str(item["object_key"])
        version_id = item.get("version_id")
        remover(bucket, key, version_id=None if version_id is None else str(version_id))
        append_receipt(
            receipt,
            {
                "event": "remote_deleted",
                "bucket": bucket,
                "object_key": key,
                "version_id": version_id,
                "completed_at_utc": _utc_now(),
            },
        )


def _hash_body(body: bytes) -> tuple[str, str, int]:
    return hashlib.sha1(body).hexdigest(), hashlib.sha256(body).hexdigest(), len(body)


def conditional_restore_object(
    client: object,
    bucket: str,
    planned: Mapping[str, object],
    backup_path: Path,
    operation_id: str,
) -> dict[str, object]:
    validate_complete_object(planned)
    body = Path(backup_path).read_bytes()
    actual = _hash_body(body)
    expected = (
        str(planned["sha1"]),
        str(planned["sha256"]),
        int(planned["size"]),
    )
    if actual != expected:
        raise CleanupBlocked("restore backup content hash mismatch")
    execute = getattr(client, "_execute", None)
    if not callable(execute):
        raise CleanupBlocked("conditional-create transport is unavailable")
    try:
        response = execute(
            method="PUT",
            bucket_name=bucket,
            object_name=str(planned["object_key"]),
            body=body,
            headers={
                "If-None-Match": "*",
                "x-amz-meta-evb-operation-id": str(operation_id),
            },
        )
    except S3Error as error:
        if error.code != "PreconditionFailed":
            raise
        raise CleanupBlocked("restore target already exists; no overwrite was attempted") from error
    headers = getattr(response, "headers", {}) or {}
    return {
        "status": "created",
        "object_key": str(planned["object_key"]),
        "etag": str(headers.get("ETag") or headers.get("etag") or "").strip('"'),
    }


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise CleanupBlocked(f"JSONL row is not an object at line {line_number}")
            yield value


def _key_from_row(row: Mapping[str, object], bucket: str) -> str:
    direct = str(
        row.get("object_key")
        or row.get("storage_key")
        or row.get("minio_object_key")
        or ""
    ).strip().lstrip("/")
    if direct:
        return direct
    url = str(row.get("url") or row.get("media_url") or "")
    if not url:
        return ""
    parts = [unquote(part) for part in urlsplit(url).path.split("/") if part]
    if bucket in parts:
        return "/".join(parts[parts.index(bucket) + 1 :])
    return ""


def _expected_from_rows(
    rows: Iterable[Mapping[str, object]], source: str, bucket: str
) -> tuple[set[str], dict[str, list[dict[str, object]]]]:
    keys: set[str] = set()
    expected: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        key = _key_from_row(row, bucket)
        if not key:
            continue
        sha1 = str(row.get("sha1") or "").lower()
        asset_id = str(row.get("asset_id") or "").lower()
        if not HEX40.fullmatch(sha1) and HEX40.fullmatch(asset_id):
            sha1 = asset_id
        if not HEX40.fullmatch(sha1):
            sha1 = ""
        # ``content_hash`` is the RAG binding/content-record fingerprint for
        # generic media rows. Only explicitly byte-oriented fields may be
        # compared with the remote object's SHA-256.
        sha256 = str(row.get("content_sha256") or row.get("sha256") or "").lower()
        if not HEX64.fullmatch(sha256):
            sha256 = ""
        raw_size = row.get("size") or row.get("size_bytes")
        size = None if raw_size in (None, "") else int(raw_size)
        keys.add(key)
        expected.setdefault(key, []).append(
            {"source": source, "sha1": sha1, "sha256": sha256, "size": size}
        )
    return keys, expected


def _merge_expected(*values: Mapping[str, Sequence[Mapping[str, object]]]):
    output: dict[str, list[dict[str, object]]] = {}
    for value in values:
        for key, rows in value.items():
            output.setdefault(key, []).extend(dict(row) for row in rows)
    return output


def _minio_client(cfg: object) -> Minio:
    assets = getattr(cfg, "assets")
    return Minio(
        str(getattr(assets, "endpoint")),
        access_key=str(getattr(assets, "access_key")),
        secret_key=str(getattr(assets, "secret_key")),
        secure=bool(getattr(assets, "secure")),
    )


def _inventory_payload(client: object, bucket: str, prefix: str = "") -> dict[str, Any]:
    inventory = capture_object_inventory(client, bucket, prefix)
    payload = inventory.to_json()
    payload["object_state_sha256"] = inventory.object_state_sha256
    for item in payload["objects"]:
        validate_complete_object(item)
    return payload


def _mysql_connection(cfg: object):
    import pymysql

    mysql = getattr(cfg, "mysql")
    return pymysql.connect(
        host=str(getattr(mysql, "host")),
        port=int(getattr(mysql, "port")),
        user=str(getattr(mysql, "user")),
        password=str(getattr(mysql, "password")),
        database=str(getattr(mysql, "database")),
        charset=str(getattr(mysql, "charset", "utf8mb4")),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _capture_wiki(cfg: object, bucket: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    connection = _mysql_connection(cfg)
    rows: list[dict[str, object]] = []
    tables: set[str] = set()
    counts: dict[str, object] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            cursor.execute("SHOW TABLES")
            tables = {str(next(iter(row.values()))) for row in cursor.fetchall()}
            if "wiki_media_links" not in tables:
                raise CleanupBlocked("current Wiki media table is missing")
            cursor.execute("SELECT * FROM wiki_media_links")
            raw_rows = [dict(row) for row in cursor.fetchall()]
            for row in raw_rows:
                key = _key_from_row(row, bucket)
                if key:
                    rows.append(
                        {
                            "object_key": key,
                            "sha1": str(row.get("sha1") or row.get("content_sha1") or ""),
                            "sha256": str(row.get("sha256") or row.get("content_sha256") or ""),
                            "size": row.get("size") or row.get("size_bytes"),
                            "media_role": str(row.get("media_role") or ""),
                            "page_id": str(row.get("page_id") or ""),
                        }
                    )
            for table in PROTECTED_MYSQL_TABLES:
                if table not in tables:
                    counts[table] = {"status": "absent"}
                    continue
                cursor.execute("SELECT COUNT(*) AS row_count FROM " + chr(96) + table + chr(96))
                counts[table] = {
                    "status": "present",
                    "row_count": int(cursor.fetchone()["row_count"]),
                }
            connection.rollback()
    finally:
        connection.close()
    rows.sort(key=lambda item: (str(item["object_key"]), str(item["page_id"]), str(item["media_role"])))
    return rows, counts


def _capture_milvus(cfg: object) -> dict[str, object]:
    vector = getattr(cfg, "vectorstore")
    client = MilvusClient(uri=str(getattr(vector, "uri")), db_name=str(getattr(vector, "db_name")))
    output: dict[str, object] = {}
    for collection in sorted(client.list_collections()):
        description = _json_safe(client.describe_collection(collection))
        stats = client.get_collection_stats(collection)
        row_count = int(stats.get("row_count", 0))
        rows = client.query(
            collection_name=collection,
            filter="",
            output_fields=["id"],
            limit=max(1, row_count),
        )
        ids = sorted(str(row.get("id") or "") for row in rows)
        output[collection] = {
            "row_count": row_count,
            "primary_id_count": len(ids),
            "primary_ids_sha256": _set_fingerprint(ids),
            "schema_sha256": hashlib.sha256(canonical_json_bytes(description)).hexdigest(),
        }
    return {"database": str(getattr(vector, "db_name")), "collections": output}


def _file_ref(path: Path) -> dict[str, object]:
    target = Path(path)
    return {"relative_path": target.resolve().relative_to(ROOT).as_posix(), "sha256": sha256_file(target)}


def command_inventory(args: argparse.Namespace) -> int:
    cfg = get_config()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    legacy_path = Path(args.legacy_manifest).resolve()
    rag_path = Path(args.rag_media).resolve()
    baseline_path = Path(args.provenance_baseline).resolve()
    for path in (legacy_path, rag_path, baseline_path):
        try:
            path.relative_to(ROOT)
        except ValueError as error:
            raise CleanupBlocked("inventory input escapes project root") from error
        if not path.is_file():
            raise CleanupBlocked(f"inventory input is missing: {path.name}")

    legacy_rows = list(_iter_jsonl(legacy_path))
    rag_rows = list(_iter_jsonl(rag_path))
    wiki_rows, mysql_counts = _capture_wiki(cfg, args.bucket)
    legacy_keys, legacy_expected = _expected_from_rows(legacy_rows, "legacy_manifest", args.bucket)
    rag_keys, rag_expected = _expected_from_rows(rag_rows, "active_rag", args.bucket)
    wiki_keys, wiki_expected = _expected_from_rows(wiki_rows, "current_wiki", args.bucket)

    client = _minio_client(cfg)
    target = _inventory_payload(client, args.bucket)
    protected_a_bucket = _inventory_payload(client, "a-bucket")
    remote_by_key = {str(item["object_key"]): item for item in target["objects"]}
    diagnostics: dict[str, object] = {
        "status": "pass",
        "missing_active_count": 0,
        "hash_mismatch_count": 0,
        "expanded_prefixes": [],
        "related_keys": [],
    }
    try:
        classes = classify_keys(
            remote_keys=remote_by_key,
            legacy_keys=legacy_keys,
            rag_keys=rag_keys,
            wiki_keys=wiki_keys,
        )
        validate_expected_hashes(
            remote_by_key,
            _merge_expected(legacy_expected, rag_expected, wiki_expected),
        )
    except CleanupBlocked as error:
        diagnostics.update(error.diagnostics)
        diagnostics["status"] = "blocked"
        diagnostics["reason"] = str(error)
        write_pinned_json(output_dir / "diagnostics.v1.json", diagnostics)
        raise

    candidate_objects = [remote_by_key[key] for key in classes["delete_candidates"]]
    retained = {
        name: {
            "count": len(values),
            "keys_sha256": _set_fingerprint(values),
        }
        for name, values in classes.items()
        if name != "delete_candidates"
    }
    sources = {
        "legacy_manifest": _file_ref(legacy_path),
        "active_rag_media": _file_ref(rag_path),
        "provenance_baseline": _file_ref(baseline_path),
    }
    wiki_payload = {
        "schema_version": "huiji.cleanup.wiki-media/v1",
        "captured_at_utc": _utc_now(),
        "rows": wiki_rows,
        "key_count": len(wiki_keys),
        "keys_sha256": _set_fingerprint(wiki_keys),
        "mysql_counts": mysql_counts,
    }
    wiki_sha = write_pinned_json(output_dir / "wiki-media-current.v1.json", wiki_payload)
    candidate_payload = {
        "schema_version": "huiji.cleanup.candidate-set/v1",
        "bucket": args.bucket,
        "objects": candidate_objects,
        "object_count": len(candidate_objects),
        "keys_sha256": _set_fingerprint(item["object_key"] for item in candidate_objects),
    }
    candidate_sha = write_pinned_json(
        output_dir / "legacy-delete-candidates.v1.json", candidate_payload
    )
    consumer_payload = {
        "schema_version": "huiji.cleanup.consumer-union/v1",
        "keys": list(classes["active_consumers"]),
        "key_count": len(classes["active_consumers"]),
        "keys_sha256": _set_fingerprint(classes["active_consumers"]),
    }
    consumer_sha = write_pinned_json(output_dir / "consumer-union.v1.json", consumer_payload)
    write_pinned_json(output_dir / "retained-classes.v1.json", {
        "schema_version": "huiji.cleanup.retained-classes/v1",
        "classes": retained,
    })
    diagnostics_sha = write_pinned_json(output_dir / "diagnostics.v1.json", diagnostics)
    inventory_payload = {
        "schema_version": "huiji.cleanup.inventory/v1",
        "captured_at_utc": _utc_now(),
        "status": "pass",
        "bucket": args.bucket,
        "target_inventory": target,
        "a_bucket_inventory": protected_a_bucket,
        "sources": sources,
        "wiki_export_sha256": wiki_sha,
        "candidate_set_sha256": candidate_sha,
        "consumer_union_sha256": consumer_sha,
        "diagnostics_sha256": diagnostics_sha,
        "sets": {
            "remote": {"count": len(remote_by_key), "keys_sha256": _set_fingerprint(remote_by_key)},
            "legacy": {"count": len(legacy_keys), "keys_sha256": _set_fingerprint(legacy_keys)},
            "active_rag": {"count": len(rag_keys), "keys_sha256": _set_fingerprint(rag_keys)},
            "current_wiki": {"count": len(wiki_keys), "keys_sha256": _set_fingerprint(wiki_keys)},
            "delete_candidates": {"count": len(candidate_objects), "keys_sha256": candidate_payload["keys_sha256"]},
        },
        "retained": retained,
        "mysql_counts": mysql_counts,
        "milvus": _capture_milvus(cfg),
        "local_candidates": list(LOCAL_CANDIDATES),
    }
    digest = write_pinned_json(output_dir / "inventory.v1.json", inventory_payload)
    print(json.dumps({"status": "pass", "inventory_sha256": digest, "counts": inventory_payload["sets"]}, sort_keys=True))
    return 0


def _collect_files(root: Path, *, project_candidates: bool) -> list[dict[str, object]]:
    base = Path(root).resolve()
    files: list[Path] = []
    if project_candidates:
        for relative in LOCAL_CANDIDATES:
            target = resolve_within(base, relative)
            if target.is_dir():
                files.extend(path for path in target.rglob("*") if path.is_file())
            elif target.is_file():
                files.append(target)
            else:
                raise CleanupBlocked(f"local backup candidate is missing: {relative}")
    else:
        files = [path for path in base.rglob("*") if path.is_file()]
    output = []
    for path in sorted(set(files), key=lambda item: item.as_posix()):
        output.append(
            {
                "relative_path": path.relative_to(base).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return output


def _restic_restore_base(live_root: Path, restore_root: Path) -> Path:
    live = Path(live_root).resolve()
    restore = Path(restore_root).resolve()
    drive = live.drive.rstrip(":\\/")
    tail = live.parts[1:] if live.drive else live.parts
    candidate = restore.joinpath(drive, *tail) if drive else restore.joinpath(*tail)
    return candidate if candidate.exists() else restore


def command_verify_local_backup(args: argparse.Namespace) -> int:
    live = Path(args.live_root).resolve()
    restored = _restic_restore_base(live, Path(args.restore_root))
    project_candidates = any(resolve_within(live, item).exists() for item in LOCAL_CANDIDATES)
    left = _collect_files(live, project_candidates=project_candidates)
    right = _collect_files(restored, project_candidates=project_candidates)
    if left != right:
        raise CleanupBlocked("restored local backup differs from live candidate set")
    payload = {
        "schema_version": "huiji.cleanup.local-backup-receipt/v1",
        "status": "pass",
        "scope": "project_candidates" if project_candidates else "complete_root",
        "files": left,
        "file_count": len(left),
        "files_sha256": hashlib.sha256(canonical_json_bytes(left)).hexdigest(),
        "verified_at_utc": _utc_now(),
    }
    digest = write_pinned_json(Path(args.output), payload)
    print(json.dumps({"status": "pass", "file_count": len(left), "sha256": digest}, sort_keys=True))
    return 0


def command_backup_minio(args: argparse.Namespace) -> int:
    inventory = _load_json(Path(args.inventory))
    candidates = _load_json(Path(args.candidate_set))
    if inventory.get("status") != "pass":
        raise CleanupBlocked("inventory is not authorized")
    if sha256_file(Path(args.candidate_set)) != str(inventory.get("candidate_set_sha256")):
        raise CleanupBlocked("candidate set differs from inventory")
    bucket = str(candidates.get("bucket") or "")
    objects = candidates.get("objects")
    if not isinstance(objects, list):
        raise CleanupBlocked("candidate set objects are malformed")
    backup_root = Path(args.backup_root).resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    client = _minio_client(get_config())
    receipts: list[dict[str, object]] = []
    for item in objects:
        if not isinstance(item, Mapping):
            raise CleanupBlocked("candidate object is malformed")
        validate_complete_object(item)
        key = str(item["object_key"])
        target = resolve_within(backup_root, Path(bucket) / Path(key))
        target.parent.mkdir(parents=True, exist_ok=True)
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        size = 0
        response = client.get_object(bucket, key, version_id=item.get("version_id"))
        try:
            with target.open("xb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    sha1.update(chunk)
                    sha256.update(chunk)
                    size += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            response.close()
            response.release_conn()
        if (sha1.hexdigest(), sha256.hexdigest(), size) != (
            str(item["sha1"]),
            str(item["sha256"]),
            int(item["size"]),
        ):
            raise CleanupBlocked(f"downloaded backup hash mismatch: {key}")
        receipts.append(
            {
                **dict(item),
                "bucket": bucket,
                "backup_relative_path": target.relative_to(backup_root).as_posix(),
            }
        )
    payload = {
        "schema_version": "huiji.cleanup.minio-backup-receipt/v1",
        "status": "pass",
        "bucket": bucket,
        "backup_root": backup_root.as_posix(),
        "inventory_sha256": sha256_file(Path(args.inventory)),
        "candidate_set_sha256": sha256_file(Path(args.candidate_set)),
        "objects": receipts,
        "object_count": len(receipts),
        "objects_sha256": hashlib.sha256(canonical_json_bytes(receipts)).hexdigest(),
        "completed_at_utc": _utc_now(),
    }
    digest = write_pinned_json(Path(args.output), payload)
    print(json.dumps({"status": "pass", "object_count": len(receipts), "sha256": digest}, sort_keys=True))
    return 0


def _extract_restic_snapshot(path: Path) -> str:
    snapshot_id = ""
    body = Path(path).read_bytes()
    encoding = "utf-16" if body.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    for line in body.decode(encoding).splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, Mapping) and value.get("snapshot_id"):
            snapshot_id = str(value["snapshot_id"])
    if not snapshot_id:
        raise CleanupBlocked("restic receipt lacks snapshot_id")
    return snapshot_id


def _relative_evidence(path: Path, base: Path) -> str:
    return os.path.relpath(Path(path).resolve(), Path(base).resolve()).replace("\\", "/")


def _operation_id_from_output(path: Path) -> str:
    output = Path(path).resolve()
    operation_root = output.parent.parent if output.parent.name == "p2" else output.parent
    if not operation_root.name:
        raise CleanupBlocked("operation plan output has no operation ID")
    return operation_root.name


def command_plan(args: argparse.Namespace) -> int:
    inventory_path = Path(args.inventory).resolve()
    local_path = Path(args.local_backup_receipt).resolve()
    minio_path = Path(args.minio_backup_receipt).resolve()
    restic_path = Path(args.restic_receipt).resolve()
    inventory = _load_json(inventory_path)
    local = _load_json(local_path)
    minio = _load_json(minio_path)
    restore_receipt_path = minio_path.parent / "minio-restic-restore-receipt.v1.json"
    restore_receipt = _load_json(restore_receipt_path)
    if any(value.get("status") != "pass" for value in (inventory, local, minio, restore_receipt)):
        raise CleanupBlocked("backup or inventory gate did not pass")
    if minio.get("inventory_sha256") != sha256_file(inventory_path):
        raise CleanupBlocked("MinIO backup is not bound to this inventory")
    if minio.get("object_count") != inventory["sets"]["delete_candidates"]["count"]:
        raise CleanupBlocked("MinIO backup candidate count differs from inventory")
    output = Path(args.output).resolve()
    operation_id = _operation_id_from_output(output)
    plan = {
        "schema_version": "huiji.cleanup.operation-plan/v1",
        "operation_id": operation_id,
        "created_at_utc": _utc_now(),
        "bucket": str(minio["bucket"]),
        "local_delete_paths": list(LOCAL_CANDIDATES),
        "remote_delete_objects": minio["objects"],
        "remote_delete_count": int(minio["object_count"]),
        "preconditions": {
            "target_object_state_sha256": inventory["target_inventory"]["object_state_sha256"],
            "a_bucket_object_state_sha256": inventory["a_bucket_inventory"]["object_state_sha256"],
            "mysql_counts": inventory["mysql_counts"],
            "milvus": inventory["milvus"],
            "active_consumer_keys_sha256": inventory["sets"]["active_rag"]["keys_sha256"],
            "wiki_consumer_keys_sha256": inventory["sets"]["current_wiki"]["keys_sha256"],
        },
        "retained": inventory["retained"],
        "evidence": {
            "inventory": {"path": _relative_evidence(inventory_path, output.parent), "sha256": sha256_file(inventory_path)},
            "local_backup": {"path": _relative_evidence(local_path, output.parent), "sha256": sha256_file(local_path)},
            "minio_backup": {"path": _relative_evidence(minio_path, output.parent), "sha256": sha256_file(minio_path)},
            "minio_restore_test": {"path": _relative_evidence(restore_receipt_path, output.parent), "sha256": sha256_file(restore_receipt_path)},
            "restic_receipt": {"path": _relative_evidence(restic_path, output.parent), "sha256": sha256_file(restic_path), "snapshot_id": _extract_restic_snapshot(restic_path)},
        },
        "postconditions": {
            "local_candidates_absent": True,
            "remote_candidates_absent": True,
            "mysql_mutation_count": 0,
            "a_bucket_unchanged": True,
            "milvus_unchanged": True,
        },
    }
    digest = write_pinned_json(output, plan)
    print(json.dumps({"status": "pass", "operation_id": operation_id, "object_count": plan["remote_delete_count"], "sha256": digest}, sort_keys=True))
    return 0


def _resolve_plan_evidence(plan_path: Path, plan: Mapping[str, object], name: str) -> Path:
    evidence = plan.get("evidence")
    ref = evidence.get(name) if isinstance(evidence, Mapping) else None
    if not isinstance(ref, Mapping):
        raise CleanupBlocked(f"operation plan lacks evidence: {name}")
    path = resolve_within(plan_path.parent, str(ref.get("path") or ""))
    if sha256_file(path) != str(ref.get("sha256") or ""):
        raise CleanupBlocked(f"operation plan evidence drifted: {name}")
    return path


def _verify_local_fingerprint(project_root: Path, receipt: Mapping[str, object]) -> None:
    current = _collect_files(project_root, project_candidates=True)
    if current != receipt.get("files"):
        raise CleanupBlocked("local candidate set drifted after backup")


def _capture_current_protected(cfg: object, bucket: str) -> dict[str, object]:
    client = _minio_client(cfg)
    _wiki_rows, mysql_counts = _capture_wiki(cfg, bucket)
    return {
        "target": _inventory_payload(client, bucket),
        "a_bucket": _inventory_payload(client, "a-bucket"),
        "mysql_counts": mysql_counts,
        "milvus": _capture_milvus(cfg),
    }


def _require_no_drift(plan: Mapping[str, object], current: Mapping[str, object]) -> None:
    pre = plan.get("preconditions")
    if not isinstance(pre, Mapping):
        raise CleanupBlocked("operation plan preconditions are missing")
    checks = {
        "target MinIO": (pre.get("target_object_state_sha256"), current["target"]["object_state_sha256"]),
        "a-bucket": (pre.get("a_bucket_object_state_sha256"), current["a_bucket"]["object_state_sha256"]),
        "MySQL": (pre.get("mysql_counts"), current["mysql_counts"]),
        "Milvus": (pre.get("milvus"), current["milvus"]),
    }
    changed = [name for name, (before, after) in checks.items() if before != after]
    if changed:
        raise CleanupBlocked("operation plan is stale: " + ", ".join(changed))


def _delete_local_candidates(project_root: Path, receipt: Path) -> None:
    for relative in LOCAL_CANDIDATES:
        target = resolve_within(project_root, relative)
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
        else:
            raise CleanupBlocked(f"planned local candidate disappeared before delete: {relative}")
        append_receipt(receipt, {"event": "local_deleted", "relative_path": relative, "completed_at_utc": _utc_now()})


def command_apply(args: argparse.Namespace) -> int:
    plan_path = Path(args.operation_plan).resolve()
    plan_sha = assert_plan_hash(plan_path, args.expected_plan_sha256)
    plan = _load_json(plan_path)
    receipt = Path(args.receipt).resolve()
    if receipt.exists():
        raise CleanupBlocked("apply receipt already exists; plan cannot be reused")
    inventory = _load_json(_resolve_plan_evidence(plan_path, plan, "inventory"))
    local_receipt = _load_json(_resolve_plan_evidence(plan_path, plan, "local_backup"))
    _load_json(_resolve_plan_evidence(plan_path, plan, "minio_backup"))
    _load_json(_resolve_plan_evidence(plan_path, plan, "minio_restore_test"))
    _resolve_plan_evidence(plan_path, plan, "restic_receipt")
    _verify_local_fingerprint(ROOT, local_receipt)
    cfg = get_config()
    current = _capture_current_protected(cfg, str(plan["bucket"]))
    _require_no_drift(plan, current)
    append_receipt(receipt, {"event": "apply_started", "operation_id": plan["operation_id"], "plan_sha256": plan_sha, "completed_at_utc": _utc_now()})
    client = _minio_client(cfg)
    objects = plan.get("remote_delete_objects")
    if not isinstance(objects, list):
        raise CleanupBlocked("operation plan remote objects are malformed")
    delete_exact_objects(client, str(plan["bucket"]), objects, receipt)
    _delete_local_candidates(ROOT, receipt)
    append_receipt(receipt, {"event": "mysql_noop", "mutation_count": 0, "completed_at_utc": _utc_now()})
    append_receipt(receipt, {"event": "apply_completed", "operation_id": plan["operation_id"], "completed_at_utc": _utc_now()})
    print(json.dumps({"status": "pass", "remote_deleted": len(objects), "local_deleted": len(LOCAL_CANDIDATES)}, sort_keys=True))
    return 0


def _receipt_rows(path: Path) -> list[dict[str, object]]:
    rows = list(_iter_jsonl(path))
    if not rows:
        raise CleanupBlocked("apply receipt is empty")
    return rows


def _expected_remaining_inventory(
    before: Mapping[str, object], delete_keys: set[str]
) -> dict[str, Mapping[str, object]]:
    objects = before.get("objects")
    if not isinstance(objects, list):
        raise CleanupBlocked("before inventory objects are malformed")
    return {
        str(item["object_key"]): item
        for item in objects
        if isinstance(item, Mapping) and str(item.get("object_key") or "") not in delete_keys
    }


def command_verify(args: argparse.Namespace) -> int:
    plan_path = Path(args.operation_plan).resolve()
    plan_sha = assert_plan_hash(plan_path, args.expected_plan_sha256)
    plan = _load_json(plan_path)
    receipt_rows = _receipt_rows(Path(args.apply_receipt))
    if receipt_rows[-1].get("event") != "apply_completed":
        raise CleanupBlocked("apply receipt does not show completion")
    objects = plan.get("remote_delete_objects")
    if not isinstance(objects, list):
        raise CleanupBlocked("operation plan remote objects are malformed")
    delete_keys = {str(item["object_key"]) for item in objects if isinstance(item, Mapping)}
    remote_receipts = {str(row.get("object_key")) for row in receipt_rows if row.get("event") == "remote_deleted"}
    local_receipts = {str(row.get("relative_path")) for row in receipt_rows if row.get("event") == "local_deleted"}
    if remote_receipts != delete_keys or local_receipts != set(LOCAL_CANDIDATES):
        raise CleanupBlocked("apply receipt does not cover the exact plan")
    for relative in LOCAL_CANDIDATES:
        if resolve_within(ROOT, relative).exists():
            raise CleanupBlocked(f"planned local path still exists: {relative}")
    cfg = get_config()
    current = _capture_current_protected(cfg, str(plan["bucket"]))
    inventory = _load_json(_resolve_plan_evidence(plan_path, plan, "inventory"))
    before_target = inventory["target_inventory"]
    expected_remaining = _expected_remaining_inventory(before_target, delete_keys)
    current_objects = {
        str(item["object_key"]): item for item in current["target"]["objects"]
    }
    if current_objects != expected_remaining:
        raise CleanupBlocked("post-delete target inventory differs outside the exact plan")
    pre = plan["preconditions"]
    if current["a_bucket"]["object_state_sha256"] != pre["a_bucket_object_state_sha256"]:
        raise CleanupBlocked("a-bucket changed during cleanup")
    if current["mysql_counts"] != pre["mysql_counts"]:
        raise CleanupBlocked("MySQL changed during cleanup")
    if current["milvus"] != pre["milvus"]:
        raise CleanupBlocked("Milvus changed during cleanup")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    post_payload = {
        "schema_version": "huiji.cleanup.post-inventory/v1",
        "captured_at_utc": _utc_now(),
        "target_inventory": current["target"],
        "a_bucket_inventory": current["a_bucket"],
        "mysql_counts": current["mysql_counts"],
        "milvus": current["milvus"],
    }
    post_sha = write_pinned_json(output_dir / "post-inventory.v1.json", post_payload)
    matrix = {
        "schema_version": "huiji.cleanup.acceptance/v1",
        "status": "pass",
        "operation_id": plan["operation_id"],
        "plan_sha256": plan_sha,
        "apply_receipt_sha256": sha256_file(Path(args.apply_receipt)),
        "post_inventory_sha256": post_sha,
        "requirements": [{"requirement_id": item, "status": "pass"} for item in P2_REQUIREMENTS],
    }
    matrix_sha = write_pinned_json(output_dir / "p2-acceptance.v1.json", matrix)
    print(json.dumps({"status": "pass", "requirements": len(P2_REQUIREMENTS), "sha256": matrix_sha}, sort_keys=True))
    return 0


def command_restore_partial(args: argparse.Namespace) -> int:
    restore_plan_path = Path(args.restore_plan).resolve()
    assert_plan_hash(restore_plan_path, args.expected_restore_plan_sha256)
    restore_plan = _load_json(restore_plan_path)
    capability = _load_json(Path(args.capability_evidence))
    if capability.get("status") != "pass" or not capability.get("conditional_create_supported"):
        raise CleanupBlocked("conditional-create capability is not proven")
    objects = restore_plan.get("objects")
    if not isinstance(objects, list):
        raise CleanupBlocked("restore plan objects are malformed")
    backup_root = Path(str(restore_plan.get("backup_root") or "")).resolve()
    client = _minio_client(get_config())
    receipt = Path(args.receipt)
    if receipt.exists():
        raise CleanupBlocked("restore receipt already exists")
    for item in objects:
        if not isinstance(item, Mapping):
            raise CleanupBlocked("restore object is malformed")
        backup = resolve_within(backup_root, str(item.get("backup_relative_path") or ""))
        result = conditional_restore_object(
            client,
            str(item.get("bucket") or restore_plan.get("bucket") or ""),
            item,
            backup,
            str(restore_plan.get("operation_id") or ""),
        )
        append_receipt(receipt, {"event": "restored", **result, "completed_at_utc": _utc_now()})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    inventory = sub.add_parser("inventory", help="capture read-only current inventories")
    inventory.add_argument("--bucket", required=True)
    inventory.add_argument("--legacy-manifest", type=Path, required=True)
    inventory.add_argument("--rag-media", type=Path, required=True)
    inventory.add_argument("--provenance-baseline", type=Path, required=True)
    inventory.add_argument("--mysql-current", action="store_true", required=True)
    inventory.add_argument("--output-dir", type=Path, required=True)

    local = sub.add_parser("verify-local-backup", help="compare live and restored file trees")
    local.add_argument("--live-root", type=Path, required=True)
    local.add_argument("--restore-root", type=Path, required=True)
    local.add_argument("--output", type=Path, required=True)

    backup = sub.add_parser("backup-minio", help="download exact candidate objects")
    backup.add_argument("--inventory", type=Path, required=True)
    backup.add_argument("--candidate-set", type=Path, required=True)
    backup.add_argument("--backup-root", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)

    plan = sub.add_parser("plan", help="create a hash-pinned exact deletion plan")
    plan.add_argument("--inventory", type=Path, required=True)
    plan.add_argument("--local-backup-receipt", type=Path, required=True)
    plan.add_argument("--minio-backup-receipt", type=Path, required=True)
    plan.add_argument("--restic-receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)

    apply = sub.add_parser("apply", help="apply an exact hash-pinned plan")
    apply.add_argument("--operation-plan", type=Path, required=True)
    apply.add_argument("--expected-plan-sha256", required=True)
    apply.add_argument("--receipt", type=Path, required=True)

    verify = sub.add_parser("verify", help="reconcile all protected state")
    verify.add_argument("--operation-plan", type=Path, required=True)
    verify.add_argument("--expected-plan-sha256", required=True)
    verify.add_argument("--apply-receipt", type=Path, required=True)
    verify.add_argument("--output-dir", type=Path, required=True)

    restore = sub.add_parser("restore-partial", help="conditionally restore an approved subset")
    restore.add_argument("--restore-plan", type=Path, required=True)
    restore.add_argument("--expected-restore-plan-sha256", required=True)
    restore.add_argument("--capability-evidence", type=Path, required=True)
    restore.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handlers = {
        "inventory": command_inventory,
        "verify-local-backup": command_verify_local_backup,
        "backup-minio": command_backup_minio,
        "plan": command_plan,
        "apply": command_apply,
        "verify": command_verify,
        "restore-partial": command_restore_partial,
    }
    try:
        return handlers[args.command](args)
    except CleanupBlocked as error:
        print(
            json.dumps(
                {"status": "blocked", "reason": str(error), "diagnostics": error.diagnostics},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "error_type": type(error).__name__, "reason": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
