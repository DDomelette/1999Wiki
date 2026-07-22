"""Inspect, apply or recover the independent Huiji generation-zero bootstrap."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config  # noqa: E402
from src.huiji_rag.generation_zero import (  # noqa: E402
    apply_generation_zero,
    inspect_generation_zero,
    load_hash_pinned_json,
    recover_generation_zero,
)


_KNOWN_PROPOSAL_ADDITIONS = {
    "data/processed/huiji/activation/proposals/candidate-f-review-20260722b/activation_proposal.v1.json": {
        "sha256": "08ef70fcb75010fd7e9b0b77c3f8e7ae14f307b6aad3bf724ecd647b48b5728c",
        "size": 1927,
    },
    "data/processed/huiji/activation/proposals/candidate-f-review-20260722b/activation_proposal.v1.json.sha256": {
        "sha256": "8c0e784f4355819f631749c8981aa39bfce5710510e544ef296629297d3b7112",
        "size": 94,
    },
    "data/processed/huiji/activation/proposals/candidate-f-review-20260722b/protected_state_inventory.v1.json": {
        "sha256": "dbae26a5a25050e95ab2db025c3cb14c399c21e6d2339c8c851b3a4858b9bf97",
        "size": 2365,
    },
    "data/processed/huiji/activation/proposals/candidate-f-review-20260722b/protected_state_inventory.v1.json.sha256": {
        "sha256": "092da88a3e3ba15dab4d77c5db15f9a06fc74a13f31c7460cb087f89f7109a5b",
        "size": 100,
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap the Huiji legacy runtime as generation zero")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--bootstrap-id", required=True)
    inspect.add_argument("--trusted-protected-compare", type=Path, required=True)
    inspect.add_argument("--expected-trusted-protected-compare-sha256", required=True)
    inspect.add_argument("--wiki-rollback-receipt", type=Path, required=True)
    inspect.add_argument("--expected-wiki-rollback-receipt-sha256", required=True)

    apply = commands.add_parser("apply")
    apply.add_argument("--intent", type=Path, required=True)
    apply.add_argument("--expected-intent-sha256", required=True)
    apply.add_argument("--expected-pointer-absence", action="store_true")
    apply.add_argument("--confirmation", required=True)

    recover = commands.add_parser("recover")
    recover.add_argument("--bootstrap-id", required=True)
    recover.add_argument("--expected-intent-sha256", required=True)
    return parser


def _wiki_health() -> Mapping[str, object]:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/wiki/health", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Wiki health response is invalid")
    return payload


def _run_inspect(args: argparse.Namespace) -> dict[str, str]:
    from scripts.verify_huiji_provenance_acceptance import (
        capture_listing_reuse_snapshot,
        compare_protected_payloads,
    )

    cfg = get_config()
    trusted, _ = load_hash_pinned_json(
        args.trusted_protected_compare,
        expected_sha256=args.expected_trusted_protected_compare_sha256,
        expected_schema="huiji.protected_compare/v1",
    )
    baseline = trusted.get("after")
    if not isinstance(baseline, Mapping):
        raise ValueError("trusted protected compare lacks after snapshot")
    current = capture_listing_reuse_snapshot(cfg, baseline)
    changes = compare_protected_payloads(
        baseline,
        current,
        allowed_artifact_additions=_KNOWN_PROPOSAL_ADDITIONS,
    )
    return inspect_generation_zero(
        cfg,
        bootstrap_id=args.bootstrap_id,
        trusted_compare_path=args.trusted_protected_compare,
        expected_trusted_compare_sha256=args.expected_trusted_protected_compare_sha256,
        wiki_receipt_path=args.wiki_rollback_receipt,
        expected_wiki_receipt_sha256=args.expected_wiki_rollback_receipt_sha256,
        protected_before=current,
        protected_changes=changes,
    )


def _run_apply(args: argparse.Namespace) -> dict[str, str]:
    from scripts.verify_huiji_provenance_acceptance import (
        capture_listing_reuse_snapshot,
        compare_protected_payloads,
        sample_active_sources,
    )

    cfg = get_config()
    return apply_generation_zero(
        cfg,
        intent_path=args.intent,
        expected_intent_sha256=args.expected_intent_sha256,
        expected_pointer_absence=args.expected_pointer_absence,
        confirmation=args.confirmation,
        protected_capture=lambda before: capture_listing_reuse_snapshot(cfg, before),
        protected_compare=compare_protected_payloads,
        smoke=lambda: sample_active_sources(cfg),
        wiki_health=_wiki_health,
    )


def _run_recover(args: argparse.Namespace) -> dict[str, str]:
    from scripts.verify_huiji_provenance_acceptance import (
        capture_listing_reuse_snapshot,
        compare_protected_payloads,
        sample_active_sources,
    )

    cfg = get_config()
    return recover_generation_zero(
        cfg,
        bootstrap_id=args.bootstrap_id,
        expected_intent_sha256=args.expected_intent_sha256,
        protected_capture=lambda before: capture_listing_reuse_snapshot(cfg, before),
        protected_compare=compare_protected_payloads,
        smoke=lambda: sample_active_sources(cfg),
        wiki_health=_wiki_health,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = _run_inspect(args)
        elif args.command == "apply":
            result = _run_apply(args)
        else:
            result = _run_recover(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "error_type": type(error).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
