from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huijiwiki.credential_store import atomic_write_canonical_json, canonical_json
from src.huijiwiki.project_paths import ProjectPathViolation, resolve_project_local_path
from src.runtime_path_audit import PathAuditPolicyError, audit_external_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit project runtime files for external filesystem paths")
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "config" / "external-path-allowlist.yaml",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = None
        if args.output is not None:
            output = resolve_project_local_path(
                args.output,
                project_root=ROOT,
                label="output",
            )
        report = audit_external_paths(ROOT, args.policy)
        if output is None:
            sys.stdout.write(canonical_json(report))
        else:
            atomic_write_canonical_json(output, report)
        if report["stale_allowlist_count"]:
            return 3
        if report["unclassified_external_path_count"]:
            return 2
        return 0
    except (ProjectPathViolation, PathAuditPolicyError, OSError) as exc:
        print(f"External path audit failed: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
