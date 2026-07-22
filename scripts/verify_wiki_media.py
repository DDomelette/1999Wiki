"""Verify pinned Wiki media by public HTTP URL without changing object storage."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_wiki.media_audit import audit_media, audit_media_manifest
from src.huiji_wiki.snapshot import resolve_wiki_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    cfg = get_config()
    snapshot = resolve_wiki_snapshot(cfg, PROJECT_ROOT, PROJECT_ROOT / "data/processed/huiji/evidence/wiki-import")
    with snapshot.media_assets.open(encoding="utf-8") as handle:
        rows = (json.loads(line) for line in handle if line.strip())
        report = audit_media_manifest(snapshot, rows, args.output) if args.manifest_only else audit_media(snapshot, rows, args.output)
    print(json.dumps({"results": len(report["results"]), "snapshot": snapshot.snapshot_sha256[:12]}))


if __name__ == "__main__":
    main()
