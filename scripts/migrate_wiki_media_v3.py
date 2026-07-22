"""Create or safely remove the Wiki media v3 resource/binding tables."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_wiki.media_schema import (
    DROP_MEDIA_BINDINGS_SQL,
    DROP_MEDIA_RESOURCES_SQL,
    media_v3_schema_statements,
)


APPLY_CONFIRMATION = "APPLY_WIKI_MEDIA_V3_SCHEMA"
ROLLBACK_CONFIRMATION = "ROLLBACK_WIKI_MEDIA_V3_SCHEMA"


def validate_backup_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "huiji.wiki-media-v3-backup-evidence/v1":
        raise ValueError("invalid Wiki media v3 backup evidence schema")
    if payload.get("verified") is not True:
        raise ValueError("Wiki media v3 backup evidence is not verified")
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    if any(secret in serialized for secret in ("password", "passwd", "mysql_password")):
        raise ValueError("backup evidence must not contain database credentials")
    return payload


def migration_plan(*, rollback: bool) -> list[str]:
    if rollback:
        return [DROP_MEDIA_BINDINGS_SQL, DROP_MEDIA_RESOURCES_SQL]
    return list(media_v3_schema_statements())


def execute_migration(
    cfg: Any,
    *,
    rollback: bool,
    backup_evidence: Path | None = None,
) -> dict[str, Any]:
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
    with conn:
        with conn.cursor() as cur:
            if rollback:
                counts: dict[str, int] = {}
                for table in ("wiki_media_bindings", "wiki_media_resources"):
                    try:
                        cur.execute(f"SELECT COUNT(*) AS count FROM {table}")
                        counts[table] = int((cur.fetchone() or {}).get("count", 0) or 0)
                    except Exception:
                        counts[table] = 0
                if any(counts.values()):
                    if backup_evidence is None:
                        raise ValueError("non-empty Wiki media v3 tables require verified backup evidence")
                    validate_backup_evidence(backup_evidence)
            for statement in migration_plan(rollback=rollback):
                cur.execute(statement)
            conn.commit()
    return {"action": "rollback" if rollback else "apply", "statementCount": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="execute the schema migration")
    parser.add_argument("--rollback", action="store_true", help="drop only the v3 compatibility tables")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--backup-evidence", type=Path)
    args = parser.parse_args()
    if args.rollback and not args.apply:
        parser.error("--rollback requires --apply")
    expected = ROLLBACK_CONFIRMATION if args.rollback else APPLY_CONFIRMATION
    plan = migration_plan(rollback=args.rollback)
    if not args.apply:
        print(json.dumps({
            "mode": "dry-run",
            "action": "apply",
            "tables": ["wiki_media_resources", "wiki_media_bindings"],
            "statementCount": len(plan),
        }, ensure_ascii=False, indent=2))
        return 0
    if args.confirmation != expected:
        parser.error(f"--apply requires --confirmation {expected}")
    result = execute_migration(
        get_config(),
        rollback=args.rollback,
        backup_evidence=args.backup_evidence,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
