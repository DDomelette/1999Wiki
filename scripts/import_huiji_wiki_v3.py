"""Inspect or execute the hash-pinned Candidate F Wiki v3 import."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_wiki.formal_import import (
    ACTIVATION_ID,
    APPLY_CONFIRMATION,
    EXPECTED_HANDOFF_SHA256,
    apply_formal_import,
    inspection_payload,
    prepare_formal_import,
    write_create_new,
)


DEFAULT_HANDOFF = Path(
    "data/processed/huiji/activation/transactions/"
    f"{ACTIVATION_ID}/wiki_import_handoff.v1.json"
)
DEFAULT_EVIDENCE = Path("eval/huiji_wiki_v3_import") / ACTIVATION_ID


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--expected-handoff-sha256", default=EXPECTED_HANDOFF_SHA256)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE)
    return parser


def inspection_evidence_name(*, already_installed: bool) -> str:
    return "inspection.post-import.v1.json" if already_installed else "inspection.pre-import.v1.json"


def main() -> int:
    args = build_parser().parse_args()
    if args.apply and args.confirmation != APPLY_CONFIRMATION:
        raise SystemExit(f"--apply requires --confirmation \"{APPLY_CONFIRMATION}\"")
    cfg = get_config()
    handoff = args.handoff if args.handoff.is_absolute() else PROJECT_ROOT / args.handoff
    context = prepare_formal_import(
        cfg,
        project_root=PROJECT_ROOT,
        handoff_path=handoff,
        expected_handoff_sha256=args.expected_handoff_sha256,
    )
    evidence_root = args.evidence_root if args.evidence_root.is_absolute() else PROJECT_ROOT / args.evidence_root
    if not args.apply:
        payload = inspection_payload(context)
        path = evidence_root / inspection_evidence_name(already_installed=context.already_installed)
        if not path.exists():
            digest = write_create_new(path, payload)
        else:
            digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        print(json.dumps({**payload, "evidence_path": path.relative_to(PROJECT_ROOT).as_posix(), "evidence_sha256": digest}, ensure_ascii=False, indent=2, default=str))
        return 0

    result = apply_formal_import(cfg, context)
    receipt = {
        "schema_version": "huiji.wiki-v3-formal-import-commit/v1",
        **result,
    }
    path = evidence_root / "import_commit.v1.json"
    if result["status"] == "committed":
        digest = write_create_new(path, receipt)
    elif path.exists():
        digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    else:
        digest = write_create_new(path, receipt)
    print(json.dumps({**receipt, "evidence_path": path.relative_to(PROJECT_ROOT).as_posix(), "evidence_sha256": digest}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
