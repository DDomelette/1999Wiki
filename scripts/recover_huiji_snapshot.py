from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.huijiwiki.snapshot_recovery import (
    SnapshotManifest,
    audit_snapshot,
    recover_missing_files,
    write_audit_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    manifest = SnapshotManifest.load(args.manifest)
    audit = audit_snapshot(args.source_root, args.target_root, manifest)
    if not args.apply:
        write_audit_receipt(audit, args.receipt)
        print(json.dumps(audit.to_json(), ensure_ascii=False, indent=2))
        return 0 if audit.status == "ready" else 2
    receipt = recover_missing_files(audit, args.receipt)
    print(json.dumps(receipt.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
