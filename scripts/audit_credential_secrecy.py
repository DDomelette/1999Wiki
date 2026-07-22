from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huijiwiki.credential_store import atomic_write_canonical_json, canonical_json
from src.huiji_crawler_tool.errors import ToolPathViolation
from src.huiji_crawler_tool.runtime_paths import ToolPaths, resolve_owned_path
from src.runtime_secret_audit import audit_credential_secrecy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check project text for project-local Huiji Cookie values")
    parser.add_argument("--credential", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = ToolPaths.from_root(ROOT)
        root = paths.root
        credential = resolve_owned_path(
            args.credential or paths.credential_file,
            root=root,
            label="credential",
            must_exist=True,
        )
        output = None
        if args.output is not None:
            output = resolve_owned_path(
                args.output,
                root=root,
                label="output",
            )
        report = audit_credential_secrecy(root, credential)
        if output is None:
            sys.stdout.write(canonical_json(report))
        else:
            atomic_write_canonical_json(output, report)
        return 2 if report["violation_count"] else 0
    except (ToolPathViolation, OSError, ValueError) as exc:
        print(f"Credential secrecy audit failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
