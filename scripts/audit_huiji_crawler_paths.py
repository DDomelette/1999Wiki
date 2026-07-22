from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huiji_crawler_tool.errors import ToolPathViolation
from src.huiji_crawler_tool.path_audit import PathAuditError, audit_crawler_paths
from src.huiji_crawler_tool.runtime_paths import resolve_owned_path
from src.huijiwiki.credential_store import atomic_write_canonical_json, canonical_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the structured Huiji crawler path audit")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--include", type=Path, action="append", default=[])
    parser.add_argument("--mode", choices=("source", "stage"), default="source")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = args.root.expanduser().resolve(strict=True)
        policy = args.policy if args.policy.is_absolute() else root / args.policy
        output = None if args.output is None else resolve_owned_path(args.output, root=root, label="output")
        report = audit_crawler_paths(
            root,
            policy,
            includes=args.include,
            mode=args.mode,
        )
        if output is None:
            sys.stdout.write(canonical_json(report))
        else:
            atomic_write_canonical_json(output, report)
        return 0 if report["status"] == "passed" else 2
    except (OSError, PathAuditError, ToolPathViolation) as exc:
        print(f"Huiji crawler path audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
