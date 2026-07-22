"""Create and verify the formal Wiki MySQL pre-import rollback receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.huiji_wiki.mysql_rollback import build_pre_import_receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a verified rollback receipt for the fixed Wiki MySQL authority."
    )
    parser.add_argument(
        "--receipt-id",
        required=True,
        help="Unique lowercase receipt identifier; existing output is never overwritten.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_pre_import_receipt(PROJECT_ROOT, args.receipt_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
