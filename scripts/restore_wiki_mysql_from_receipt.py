"""Validate or explicitly apply a verified Wiki MySQL rollback receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.huiji_wiki.mysql_rollback import (
    SOURCE_CONTAINER,
    SOURCE_DATABASE,
    build_restore_confirmation,
    execute_production_restore,
    validate_passing_receipt,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run validation is the default; mutation requires every explicit guard."
    )
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-receipt-sha256")
    parser.add_argument("--target-container")
    parser.add_argument("--target-database")
    parser.add_argument("--confirmation")
    return parser


def validate_apply_request(
    args: argparse.Namespace,
    payload: dict[str, Any],
    receipt_path: Path,
) -> None:
    if not args.apply:
        raise ValueError("restore mutation requires --apply")
    actual_sha256 = hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest()
    if args.expected_receipt_sha256 != actual_sha256:
        raise ValueError("receipt file SHA-256 confirmation mismatch")
    if args.target_container != SOURCE_CONTAINER:
        raise ValueError("target container confirmation mismatch")
    if args.target_database != SOURCE_DATABASE:
        raise ValueError("target database confirmation mismatch")
    expected_confirmation = build_restore_confirmation(str(payload["receipt_id"]))
    if args.confirmation != expected_confirmation:
        raise ValueError("restore phrase confirmation mismatch")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt_path = args.receipt.resolve()
    payload = validate_passing_receipt(receipt_path, project_root=PROJECT_ROOT)
    if not args.apply:
        result = {
            "status": "validated",
            "mode": "dry-run",
            "receipt_id": payload["receipt_id"],
            "target_container": SOURCE_CONTAINER,
            "target_database": SOURCE_DATABASE,
            "confirmation": build_restore_confirmation(str(payload["receipt_id"])),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    validate_apply_request(args, payload, receipt_path)
    result = execute_production_restore(
        project_root=PROJECT_ROOT,
        receipt_path=receipt_path,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
