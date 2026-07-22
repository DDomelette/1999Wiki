from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huijiwiki.integrity import IntegrityConfig, IntegrityReport, verify_integrity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify local res1999 HuijiWiki crawl completeness")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "huiji" / "res1999")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--skip-resource-files", action="store_true")
    parser.add_argument("--skip-resource-hash", action="store_true")
    parser.add_argument("--issue-limit", type=int, default=200)
    parser.add_argument("--json", action="store_true", dest="json_only")
    return parser


def print_human_report(report: IntegrityReport) -> None:
    status = "ok" if report.ok else "error"
    print(f"[{status}] HuijiWiki local crawl integrity {'passed' if report.ok else 'failed'}")
    print(
        "[summary] "
        f"errors={report.error_count} warnings={report.warning_count} "
        f"active_pages={report.counts.get('active_pages', 0)} "
        f"complete_page_revisions={report.counts.get('complete_page_revisions', 0)} "
        f"resources={report.counts.get('resources', 0)} "
        f"verified_resource_files={report.counts.get('verified_resource_files', 0)}"
    )
    for issue in report.issues:
        ref = f" {issue.ref}" if issue.ref else ""
        print(f"[{issue.severity}] {issue.code}{ref}: {issue.message}")
    if report.error_count + report.warning_count > len(report.issues):
        omitted = report.error_count + report.warning_count - len(report.issues)
        print(f"[note] {omitted} additional issues omitted by --issue-limit")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_integrity(
        IntegrityConfig(
            out=args.out,
            db_path=args.db,
            verify_resource_files=not args.skip_resource_files,
            verify_resource_hash=not args.skip_resource_hash,
            issue_limit=args.issue_limit,
        )
    )
    if args.json_only:
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_report(report)
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
