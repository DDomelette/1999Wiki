from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huiji_crawler_packaging.dependency_lock import DependencyLockError
from src.huiji_crawler_packaging.standard_package import PackageBuildError, build_standard_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the standard Windows Huiji crawler ZIP")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_standard_package(
            project_root=args.project_root,
            policy_path=args.policy,
            lock_path=args.lock,
            wheelhouse=args.wheelhouse,
            output_dir=args.output,
            evidence_dir=args.evidence,
        )
    except (DependencyLockError, PackageBuildError, OSError) as exc:
        print(f"Crawler package build failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
