"""Import Huiji crawler and processed artifacts into canonical Wiki tables."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_wiki.importer import build_wiki_import_payload, import_payload_to_mysql
from src.huiji_wiki.snapshot import resolve_wiki_snapshot, snapshot_is_stale


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=None,
        help="Deprecated compatibility option; must resolve to the configured legacy build directory.",
    )
    parser.add_argument("--legacy-build", default="", help="Pin a configured legacy build and create a verified receipt.")
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
        help="Huiji crawler root. Defaults to the configured huiji.raw_root.",
    )
    parser.add_argument(
        "--include-character",
        action="store_true",
        help="Also import character parent pages. Leave disabled to preserve current rich character pages.",
    )
    args = parser.parse_args()

    cfg = get_config()
    if args.legacy_build:
        cfg.huiji.build_version = args.legacy_build
    if args.processed_dir:
        requested = args.processed_dir.resolve()
        expected = (cfg.huiji.processed_root / cfg.huiji.build_version).resolve()
        if requested != expected:
            parser.error("--processed-dir must equal the configured verified legacy build")
    snapshot = resolve_wiki_snapshot(
        cfg,
        PROJECT_ROOT,
        PROJECT_ROOT / "data/processed/huiji/evidence/wiki-import",
    )
    payload = build_wiki_import_payload(
        snapshot,
        include_character=args.include_character,
        raw_root=(args.raw_root or cfg.huiji.raw_root) if args.include_character else None,
        asset_public_base_url=cfg.assets.public_base_url,
        asset_bucket_name=cfg.assets.bucket_name,
        asset_object_prefix=cfg.assets.object_prefix,
    )
    result = import_payload_to_mysql(payload, cfg)
    stale = snapshot_is_stale(snapshot, cfg.huiji.processed_root, cfg.huiji.build_version)
    print(
        "Imported wiki rows: "
        f"pages={result['pages']} categories={result['categories']} media_links={result['media_links']} "
        f"snapshot={snapshot.snapshot_sha256[:12]} stale={str(stale).lower()}"
    )


if __name__ == "__main__":
    main()
