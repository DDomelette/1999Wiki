from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huijiwiki.resource_downloader import DownloadConfig, DownloadResult, DownloadSummary, ResourceDownloader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download res1999 HuijiWiki file resources from crawl_state.sqlite")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "huiji" / "res1999")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--mime-prefix", action="append", default=[])
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = args.out
    db_path = args.db or out / "crawl_state.sqlite"
    if not db_path.exists():
        print(f"Resource state database not found: {db_path}", file=sys.stderr)
        return 1

    config = DownloadConfig(
        out=out,
        db_path=db_path,
        workers=args.workers,
        limit=args.limit,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
        include_failed=args.include_failed,
        mime_prefixes=tuple(args.mime_prefix),
        log_every=args.log_every,
    )
    started_at = time.time()
    summary = ResourceDownloader(config).run(progress_fn=progress_printer(started_at, args.log_every))
    print(json.dumps(summary.to_json(), ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
