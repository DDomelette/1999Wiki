"""Migrate Wiki data to the authoritative Huiji crawler projection."""
from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_wiki.crawler_media_migration import (
    audit_crawler_media_objects,
    build_crawler_media_operations,
    delete_private_media_prefix,
    upload_missing_crawler_media,
)
from src.huiji_wiki.importer import build_wiki_import_payload, import_payload_to_mysql
from src.huiji_wiki.snapshot import resolve_wiki_snapshot


APPLY_CONFIRMATION_TOKEN = "APPLY_CRAWLER_ONLY_WIKI"
BACKUP_TABLES = (
    "wiki_categories",
    "wiki_pages",
    "wiki_media_links",
    "wiki_aliases",
    "wiki_link_spans",
    "wiki_import_snapshots",
    "wiki_page_supplements",
    "wiki_supplement_snapshots",
)
OBSIDIAN_REFERENCE_QUERY = (
    "SELECT ("
    "(SELECT COUNT(*) FROM wiki_media_links WHERE LOWER(object_key) LIKE '%obsidian%' "
    "OR LOWER(url) LIKE '%obsidian%') + "
    "(SELECT COUNT(*) FROM wiki_pages WHERE LOWER(COALESCE(source_title,'')) LIKE '%obsidian%' "
    "OR LOWER(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(content_json, '$.crawlerSourceTitle')),'')) "
    "LIKE '%obsidian%')"
    ") AS total"
)


def evaluate_mysql_verification(
    actual: dict[str, int],
    expected: dict[str, int],
) -> dict[str, Any]:
    errors: list[str] = []
    for field in ("pages", "categories", "media_links", "character_pages"):
        if actual.get(field) != expected.get(field):
            errors.append(f"{field}: expected {expected.get(field)}, got {actual.get(field)}")
    character_pages = expected.get("character_pages", 0)
    for field in (
        "crawler_character_pages",
        "characters_with_roster",
        "characters_with_stage",
    ):
        if actual.get(field) != character_pages:
            errors.append(f"{field}: expected {character_pages}, got {actual.get(field)}")
    for field in ("private_media_refs", "obsidian_refs"):
        if actual.get(field) != 0:
            errors.append(f"{field}: expected 0, got {actual.get(field)}")
    return {"ok": not errors, "errors": errors}


def validate_apply_request(
    *,
    apply: bool,
    backup_dir: Path | None,
    confirmation: str,
) -> None:
    if not apply:
        return
    if backup_dir is None:
        raise ValueError("--apply requires a backup directory")
    if confirmation != APPLY_CONFIRMATION_TOKEN:
        raise ValueError("--apply requires the exact confirmation token")


def execute_apply_pipeline(
    *,
    backup: Callable[[], dict[str, Any]],
    upload: Callable[[], dict[str, Any]],
    import_payload: Callable[[], dict[str, Any]],
    verify: Callable[[], dict[str, Any]],
    cleanup: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    result = {
        "backup": backup(),
        "upload": upload(),
        "import": import_payload(),
    }
    verification = verify()
    result["verification"] = verification
    if not verification.get("ok"):
        raise RuntimeError(f"crawler-only migration verification failed: {verification}")
    result["cleanup"] = cleanup()
    return result


def _connect_mysql(cfg: Any):
    import pymysql

    return pymysql.connect(
        host=cfg.mysql.host,
        port=cfg.mysql.port,
        user=cfg.mysql.user,
        password=cfg.mysql.password,
        database=cfg.mysql.database,
        charset=cfg.mysql.charset,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _create_minio_client(cfg: Any):
    from minio import Minio

    if not cfg.assets.access_key or not cfg.assets.secret_key:
        raise ValueError("MinIO credentials must be supplied through configuration or environment")
    endpoint = cfg.assets.endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")
    return Minio(
        endpoint,
        access_key=cfg.assets.access_key,
        secret_key=cfg.assets.secret_key,
        secure=cfg.assets.secure,
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(value: Any, charset: str) -> str:
    from pymysql.converters import encoders, escape_item

    escaped = escape_item(value, charset, mapping=encoders)
    return escaped.decode(charset) if isinstance(escaped, bytes) else str(escaped)


def backup_mysql_tables(cfg: Any, backup_dir: Path) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir.resolve() / f"wiki-crawler-migration-{timestamp}.sql"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS=0;",
        "START TRANSACTION;",
    ]
    counts: dict[str, int] = {}
    conn = _connect_mysql(cfg)
    with conn:
        with conn.cursor() as cursor:
            for table in BACKUP_TABLES:
                cursor.execute("SHOW TABLES LIKE %s", (table,))
                if cursor.fetchone() is None:
                    continue
                cursor.execute(f"SHOW CREATE TABLE `{table}`")
                create_row = cursor.fetchone() or {}
                create_sql = next(
                    (str(value) for value in create_row.values() if str(value).startswith("CREATE TABLE")),
                    "",
                )
                if not create_sql:
                    raise RuntimeError(f"failed to capture schema for {table}")
                lines.extend([f"DROP TABLE IF EXISTS `{table}`;", create_sql + ";"])
                cursor.execute(f"SELECT * FROM `{table}`")
                rows = cursor.fetchall()
                counts[table] = len(rows)
                for row in rows:
                    columns = ", ".join(f"`{column}`" for column in row)
                    values = ", ".join(
                        _sql_literal(value, cfg.mysql.charset) for value in row.values()
                    )
                    lines.append(f"INSERT INTO `{table}` ({columns}) VALUES ({values});")
    lines.extend(["COMMIT;", "SET FOREIGN_KEY_CHECKS=1;", ""])
    backup_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "path": str(backup_path),
        "sha256": _sha256_file(backup_path),
        "table_counts": counts,
    }


def _payload_counts(payload: Any) -> dict[str, int]:
    return {
        "pages": len(payload.pages),
        "categories": len(payload.categories),
        "media_links": len(payload.media_links),
        "character_pages": sum(page["page_type"] == "character" for page in payload.pages),
    }


def query_mysql_wiki_counts(cfg: Any) -> dict[str, int]:
    queries = {
        "pages": "SELECT COUNT(*) AS total FROM wiki_pages",
        "categories": "SELECT COUNT(*) AS total FROM wiki_categories",
        "media_links": "SELECT COUNT(*) AS total FROM wiki_media_links",
        "character_pages": "SELECT COUNT(*) AS total FROM wiki_pages WHERE page_type='character'",
        "crawler_character_pages": (
            "SELECT COUNT(*) AS total FROM wiki_pages WHERE page_type='character' "
            "AND JSON_UNQUOTE(JSON_EXTRACT(content_json, '$.crawlerProjectionVersion'))='1'"
        ),
        "characters_with_roster": (
            "SELECT COUNT(DISTINCT p.page_id) AS total FROM wiki_pages p "
            "JOIN wiki_media_links m ON m.page_id=p.page_id "
            "WHERE p.page_type='character' AND m.media_role='roster_avatar'"
        ),
        "characters_with_stage": (
            "SELECT COUNT(DISTINCT p.page_id) AS total FROM wiki_pages p "
            "JOIN wiki_media_links m ON m.page_id=p.page_id "
            "WHERE p.page_type='character' AND m.media_role IN ('stage_portrait','stage_live2d')"
        ),
        "private_media_refs": (
            "SELECT COUNT(*) AS total FROM wiki_media_links "
            "WHERE object_key LIKE '%/wiki-supplement/%' OR url LIKE '%/wiki-supplement/%'"
        ),
        "obsidian_refs": OBSIDIAN_REFERENCE_QUERY,
    }
    result: dict[str, int] = {}
    conn = _connect_mysql(cfg)
    with conn:
        with conn.cursor() as cursor:
            for field, query in queries.items():
                cursor.execute(query)
                result[field] = int((cursor.fetchone() or {}).get("total") or 0)
    return result


def _supplement_tables_present(cfg: Any) -> list[str]:
    present: list[str] = []
    conn = _connect_mysql(cfg)
    with conn:
        with conn.cursor() as cursor:
            for table in ("wiki_page_supplements", "wiki_supplement_snapshots"):
                cursor.execute("SHOW TABLES LIKE %s", (table,))
                if cursor.fetchone() is not None:
                    present.append(table)
    return present


def _drop_supplement_tables(cfg: Any) -> tuple[str, ...]:
    tables = tuple(_supplement_tables_present(cfg))
    conn = _connect_mysql(cfg)
    with conn:
        with conn.cursor() as cursor:
            for table in tables:
                cursor.execute(f"DROP TABLE `{table}`")
        conn.commit()
    return tables


def _private_object_keys(client: Any, bucket: str, prefix: str) -> tuple[str, ...]:
    return tuple(
        str(item.object_name)
        for item in client.list_objects(bucket, prefix=prefix, recursive=True)
    )


def _audit_summary(audit: Any) -> dict[str, Any]:
    return {
        "existing": len(audit.existing),
        "missing": len(audit.missing),
        "conflicts": len(audit.conflicts),
        "missing_keys": [item.object_key for item in audit.missing],
        "conflict_keys": [item.object_key for item in audit.conflicts],
    }


def _print_summary(label: str, payload: dict[str, Any]) -> None:
    print(label + ": " + json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the verified migration.")
    parser.add_argument("--confirmation", default="", help="Exact write confirmation token.")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=PROJECT_ROOT / "eval/wiki-crawler-only-migration",
    )
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument("--legacy-build", default="")
    parser.add_argument("--expected-character-pages", type=int, default=132)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    validate_apply_request(
        apply=args.apply,
        backup_dir=args.backup_dir,
        confirmation=args.confirmation,
    )
    cfg = get_config()
    if args.legacy_build:
        cfg.huiji.build_version = args.legacy_build
    evidence_dir = args.evidence_dir.resolve()
    snapshot = resolve_wiki_snapshot(
        cfg,
        PROJECT_ROOT,
        evidence_dir / "snapshot",
    )
    raw_root = (args.raw_root or cfg.huiji.raw_root).resolve()
    payload = build_wiki_import_payload(
        snapshot,
        include_character=True,
        raw_root=raw_root,
        asset_public_base_url=cfg.assets.public_base_url,
        asset_bucket_name=cfg.assets.bucket_name,
        asset_object_prefix=cfg.assets.object_prefix,
    )
    expected = _payload_counts(payload)
    if expected["character_pages"] != args.expected_character_pages:
        raise RuntimeError(
            "crawler character count differs from the approved authority: "
            f"expected={args.expected_character_pages}, payload={expected['character_pages']}"
        )

    operations = build_crawler_media_operations(
        payload.media_links,
        raw_root,
        object_prefix=cfg.assets.object_prefix,
    )
    minio_client = _create_minio_client(cfg)
    audit = audit_crawler_media_objects(minio_client, cfg.assets.bucket_name, operations)
    private_prefix = f"{cfg.assets.object_prefix.strip('/')}/wiki-supplement/"
    private_keys = _private_object_keys(
        minio_client,
        cfg.assets.bucket_name,
        private_prefix,
    )
    preflight = {
        "mode": "apply" if args.apply else "dry-run",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "raw_root": str(raw_root),
            "build_version": cfg.huiji.build_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        "expected_mysql": expected,
        "crawler_media_operations": len(operations),
        "minio_audit": _audit_summary(audit),
        "legacy_private_objects": {
            "prefix": private_prefix,
            "count": len(private_keys),
            "keys": list(private_keys),
        },
        "supplement_tables": _supplement_tables_present(cfg),
    }
    _write_json(evidence_dir / "preflight.json", preflight)
    if not args.apply:
        _print_summary(
            "Crawler-only Wiki dry-run",
            {
                "expected_mysql": expected,
                "crawler_media_operations": len(operations),
                "minio_existing": len(audit.existing),
                "minio_missing": len(audit.missing),
                "minio_conflicts": len(audit.conflicts),
                "legacy_private_objects": len(private_keys),
                "supplement_tables": preflight["supplement_tables"],
                "evidence": str(evidence_dir / "preflight.json"),
            },
        )
        return 0
    if audit.conflicts:
        raise RuntimeError("MinIO contains conflicting shared objects; see preflight.json")

    def upload() -> dict[str, Any]:
        uploaded = upload_missing_crawler_media(
            minio_client,
            cfg.assets.bucket_name,
            audit,
        )
        post_upload = audit_crawler_media_objects(
            minio_client,
            cfg.assets.bucket_name,
            operations,
        )
        if post_upload.missing or post_upload.conflicts:
            raise RuntimeError(f"MinIO post-upload verification failed: {_audit_summary(post_upload)}")
        return {"uploaded": len(uploaded), "keys": [item.object_key for item in uploaded]}

    def verify() -> dict[str, Any]:
        actual = query_mysql_wiki_counts(cfg)
        result = evaluate_mysql_verification(actual, expected)
        return {**result, "actual": actual, "expected": expected}

    def cleanup() -> dict[str, Any]:
        deleted_keys = delete_private_media_prefix(
            minio_client,
            cfg.assets.bucket_name,
            private_prefix,
        )
        dropped_tables = _drop_supplement_tables(cfg)
        remaining_keys = _private_object_keys(
            minio_client,
            cfg.assets.bucket_name,
            private_prefix,
        )
        remaining_tables = _supplement_tables_present(cfg)
        if remaining_keys or remaining_tables:
            raise RuntimeError(
                f"legacy cleanup incomplete: objects={len(remaining_keys)}, tables={remaining_tables}"
            )
        return {
            "deleted_private_objects": len(deleted_keys),
            "deleted_keys": list(deleted_keys),
            "dropped_tables": list(dropped_tables),
        }

    try:
        result = execute_apply_pipeline(
            backup=lambda: backup_mysql_tables(cfg, args.backup_dir),
            upload=upload,
            import_payload=lambda: import_payload_to_mysql(payload, cfg),
            verify=verify,
            cleanup=cleanup,
        )
    except Exception as error:
        _write_json(
            evidence_dir / "failure.json",
            {
                "failed_at": datetime.now().isoformat(timespec="seconds"),
                "error_type": type(error).__name__,
                "error": str(error),
                "preflight": preflight,
            },
        )
        raise

    receipt = {
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "preflight": preflight,
        "result": result,
        "final_mysql": query_mysql_wiki_counts(cfg),
    }
    _write_json(evidence_dir / "receipt.json", receipt)
    _print_summary(
        "Crawler-only Wiki migration complete",
        {
            "backup": result["backup"]["path"],
            "uploaded": result["upload"]["uploaded"],
            "import": result["import"],
            "deleted_private_objects": result["cleanup"]["deleted_private_objects"],
            "dropped_tables": result["cleanup"]["dropped_tables"],
            "evidence": str(evidence_dir / "receipt.json"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
