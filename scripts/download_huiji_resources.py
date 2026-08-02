from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huijiwiki.resource_downloader import (
    ApprovalRequiredError,
    DownloadConfig,
    DownloadResult,
    DownloadSummary,
    ResourceDownloader,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download an explicitly approved HuijiWiki media allowlist"
    )
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--allowlist-sha256", required=True)
    parser.add_argument("--source-inventory-sha256", required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--staging-receipt", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--log-every", type=int, default=100)
    return parser


def progress_printer(started_at: float, log_every: int):
    def print_progress(done: int, summary: DownloadSummary, result: DownloadResult) -> None:
        should_log = done == 1 or done == summary.total or (log_every > 0 and done % log_every == 0)
        if not should_log:
            return
        elapsed = max(0.001, time.time() - started_at)
        rate = done / elapsed
        remaining = summary.total - done
        eta_seconds = int(remaining / rate) if rate > 0 else 0
        print(
            "[progress] resource download "
            f"{done}/{summary.total} | downloaded={summary.downloaded} skipped={summary.skipped} "
            f"failed={summary.failed} | rate={rate:.2f}/s | ETA={format_duration(eta_seconds)} "
            f"| current: {result.job.name}",
            file=sys.stderr,
            flush=True,
        )

    return print_progress


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{sec:02d}s"


def build_download_config(args: argparse.Namespace) -> DownloadConfig:
    return DownloadConfig(
        staging_root=args.staging_root,
        allowlist_path=args.allowlist,
        expected_allowlist_sha256=args.allowlist_sha256,
        expected_source_inventory_sha256=args.source_inventory_sha256,
        approval_path=args.approval,
        staging_receipt_path=args.staging_receipt,
        workers=args.workers,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
        log_every=args.log_every,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = build_download_config(args)
        started_at = time.time()
        summary = ResourceDownloader(config).run(
            progress_fn=progress_printer(started_at, args.log_every)
        )
    except (ApprovalRequiredError, OSError, ValueError) as error:
        print(f"Download refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary.to_json(), ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
