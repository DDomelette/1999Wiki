from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huiji_crawler_packaging.dependency_lock import DependencyLockError, generate_dependency_lock


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the Windows crawler wheel hash lock")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--python-version", default="3.12")
    parser.add_argument("--platform", default="win_amd64")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        lock = generate_dependency_lock(
            args.input,
            args.output,
            args.wheelhouse,
            python_version=args.python_version,
            platform=args.platform,
        )
    except (DependencyLockError, OSError) as exc:
        print(f"Crawler dependency lock failed: {exc}", file=sys.stderr)
        return 2
    print(f"locked {len(lock.records)} wheel distributions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
