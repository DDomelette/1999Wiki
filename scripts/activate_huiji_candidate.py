"""Inspect, apply, or recover the approved Candidate F activation."""
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
from src.huiji_rag.activation import (  # noqa: E402
    ACTIVATION_ID,
    ActivationConflict,
    ActivationRolledBack,
    apply_activation,
    inspect_activation,
    recover_activation,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Activate the approved Huiji Candidate F tuple")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--activation-id", required=True)
    inspect.add_argument("--proposal", type=Path, required=True)
    inspect.add_argument("--expected-proposal-sha256", required=True)
    inspect.add_argument("--rollback-tuple", type=Path, required=True)
    inspect.add_argument("--expected-rollback-tuple-sha256", required=True)
    inspect.add_argument("--expected-pointer-sha256", required=True)
    inspect.add_argument("--expected-settings-sha256", required=True)

    apply = commands.add_parser("apply")
    apply.add_argument("--intent", type=Path, required=True)
    apply.add_argument("--expected-intent-sha256", required=True)
    apply.add_argument("--expected-proposal-sha256", required=True)
    apply.add_argument("--expected-rollback-tuple-sha256", required=True)
    apply.add_argument("--expected-pointer-sha256", required=True)
    apply.add_argument("--expected-settings-sha256", required=True)
    apply.add_argument("--confirmation", required=True)

    recover = commands.add_parser("recover")
    recover.add_argument("--activation-id", required=True)
    recover.add_argument("--expected-intent-sha256", required=True)
    return parser


def _wiki_health() -> Mapping[str, object]:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/wiki/health", timeout=15) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("Wiki health response is invalid")
    return value


def _protected_capture(before: Mapping[str, object]) -> Mapping[str, object]:
    from scripts.verify_huiji_provenance_acceptance import capture_listing_reuse_snapshot

    return capture_listing_reuse_snapshot(get_config(), before)


def _retrieval_smoke(cfg: object) -> Mapping[str, object]:
    from scripts.verify_huiji_provenance_acceptance import sample_active_sources

    return sample_active_sources(cfg)


def _voice_smoke(cfg: object) -> Mapping[str, object]:
    from scripts.verify_multi_intent_voice import (
        build_character_inventory,
        run_evaluation,
    )
    from src.huiji_rag.io import iter_jsonl
    from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot

    snapshot = resolve_runtime_artifact_snapshot(cfg)
    inventory = build_character_inventory(
        iter_jsonl(snapshot.child_blocks), iter_jsonl(snapshot.media_assets)
    )
    return run_evaluation(
        cfg,
        base_url="http://127.0.0.1:8000",
        inventory=inventory,
        before_snapshot_reference=(
            "data/processed/huiji/activation/transactions/"
            f"{ACTIVATION_ID}/protected_state.before.v1.json"
        ),
        limit=8,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = get_config()
        if args.command == "inspect":
            if args.expected_proposal_sha256 != "fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8":
                raise ValueError("proposal SHA authorization mismatch")
            if args.expected_rollback_tuple_sha256 != "07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b":
                raise ValueError("rollback SHA authorization mismatch")
            result = inspect_activation(
                cfg,
                activation_id=args.activation_id,
                proposal_path=args.proposal,
                rollback_path=args.rollback_tuple,
                expected_pointer_sha256=args.expected_pointer_sha256,
                expected_settings_sha256=args.expected_settings_sha256,
                protected_capture=_protected_capture,
                wiki_health=_wiki_health,
            )
        elif args.command == "apply":
            result = apply_activation(
                cfg,
                intent_path=args.intent,
                expected_intent_sha256=args.expected_intent_sha256,
                expected_proposal_sha256=args.expected_proposal_sha256,
                expected_rollback_sha256=args.expected_rollback_tuple_sha256,
                expected_pointer_sha256=args.expected_pointer_sha256,
                expected_settings_sha256=args.expected_settings_sha256,
                confirmation=args.confirmation,
                protected_capture=_protected_capture,
                retrieval_smoke=_retrieval_smoke,
                voice_smoke=_voice_smoke,
                wiki_health=_wiki_health,
            )
        else:
            result = recover_activation(
                cfg,
                activation_id=args.activation_id,
                expected_intent_sha256=args.expected_intent_sha256,
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ActivationRolledBack:
        print(json.dumps({"status": "rolled_back"}, sort_keys=True), file=sys.stderr)
        return 2
    except ActivationConflict:
        print(json.dumps({"status": "conflict"}, sort_keys=True), file=sys.stderr)
        return 3
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "error_type": type(error).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
