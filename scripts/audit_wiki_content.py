"""Create a new, read-only Wiki content quality report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_wiki.content_quality import build_content_quality_report
from src.huiji_wiki.importer import build_wiki_import_payload
from src.huiji_wiki.snapshot import resolve_wiki_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = get_config()
    snapshot = resolve_wiki_snapshot(cfg, PROJECT_ROOT, PROJECT_ROOT / "data/processed/huiji/evidence/wiki-content-audit")
    payload = build_wiki_import_payload(
        snapshot,
        include_character=True,
        raw_root=cfg.huiji.raw_root,
        asset_public_base_url=cfg.assets.public_base_url,
        asset_bucket_name=cfg.assets.bucket_name,
        asset_object_prefix=cfg.assets.object_prefix,
    )
    report = build_content_quality_report(payload.pages)
    report["snapshotSha256"] = snapshot.snapshot_sha256
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"pages={report['pageCount']} issues={report['issuePageCount']} output={args.output}")


if __name__ == "__main__":
    main()
