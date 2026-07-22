"""Audit and optionally prune frontend images not present in the Huiji crawler manifest."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLY_CONFIRMATION_TOKEN = "DELETE_NON_CRAWLER_FRONTEND_MEDIA"


@dataclass(frozen=True)
class FrontendImageAuditRow:
    relative_path: str
    sha1: str
    size: int
    crawler: bool


def _sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_crawler_sha1s(manifest_path: Path) -> set[str]:
    result: set[str] = set()
    with manifest_path.open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            sha1 = str(json.loads(line).get("sha1") or "").strip().lower()
            if len(sha1) == 40:
                result.add(sha1)
    return result


def audit_frontend_images(
    images_root: Path,
    crawler_sha1s: set[str],
) -> tuple[FrontendImageAuditRow, ...]:
    root = images_root.resolve()
    rows: list[FrontendImageAuditRow] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        sha1 = _sha1_file(path)
        rows.append(
            FrontendImageAuditRow(
                relative_path=path.relative_to(root).as_posix(),
                sha1=sha1,
                size=path.stat().st_size,
                crawler=sha1 in crawler_sha1s,
            )
        )
    return tuple(rows)


def prune_non_crawler_images(
    images_root: Path,
    rows: tuple[FrontendImageAuditRow, ...],
    *,
    confirmation: str,
) -> tuple[str, ...]:
    if confirmation != APPLY_CONFIRMATION_TOKEN:
        raise ValueError("pruning requires the exact confirmation token")
    root = images_root.resolve()
    deleted: list[str] = []
    for row in rows:
        if row.crawler:
            continue
        target = (root / row.relative_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"frontend image escapes images root: {row.relative_path}")
        if target.is_file():
            target.unlink()
            deleted.append(row.relative_path)
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if not any(directory.iterdir()):
            directory.rmdir()
    return tuple(deleted)


def _report(rows: tuple[FrontendImageAuditRow, ...]) -> dict:
    crawler = [row for row in rows if row.crawler]
    foreign = [row for row in rows if not row.crawler]
    return {
        "total": len(rows),
        "crawler": len(crawler),
        "non_crawler": len(foreign),
        "crawler_bytes": sum(row.size for row in crawler),
        "non_crawler_bytes": sum(row.size for row in foreign),
        "files": [asdict(row) for row in rows],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "data/huiji/res1999/resources_manifest.jsonl",
    )
    parser.add_argument(
        "--images-root",
        type=Path,
        default=PROJECT_ROOT / "frontend/react-app/public/images",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "eval/wiki-crawler-only-migration/frontend-images.json",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args(argv)

    crawler_sha1s = load_crawler_sha1s(args.manifest.resolve())
    rows = audit_frontend_images(args.images_root.resolve(), crawler_sha1s)
    report = _report(rows)
    report["mode"] = "apply" if args.apply else "dry-run"
    _write_json(args.report.resolve(), report)
    if args.apply:
        deleted = prune_non_crawler_images(
            args.images_root,
            rows,
            confirmation=args.confirmation,
        )
        post_rows = audit_frontend_images(args.images_root.resolve(), crawler_sha1s)
        post_report = _report(post_rows)
        post_report.update({"mode": "post-apply", "deleted": len(deleted)})
        if post_report["non_crawler"]:
            raise RuntimeError("non-crawler frontend images remain after pruning")
        _write_json(args.report.resolve(), post_report)
        report = post_report
    print(
        "Frontend crawler media audit: "
        f"total={report['total']} crawler={report['crawler']} "
        f"non_crawler={report['non_crawler']} report={args.report.resolve()}"
    )
    return 0 if report["non_crawler"] == 0 or not args.apply else 1


if __name__ == "__main__":
    raise SystemExit(main())
