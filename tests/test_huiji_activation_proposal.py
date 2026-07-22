from __future__ import annotations

import json
from pathlib import Path

from src.huiji_rag.build.activation_evidence import (
    PinnedEvidence,
    build_activation_review,
)


def _evidence(*, include_rollback: bool, pointer_sha256: str = ""):
    collection = "shadow-v1"
    manifest_sha = "a" * 64
    values = {
        "shadow": PinnedEvidence(
            "eval/shadow.json",
            "1" * 64,
            {
                "schema_version": "huiji.shadow_build/v1",
                "status": "pass",
                "collection": collection,
                "candidate_build_version": "candidate-v1",
            },
        ),
        "full_chain": PinnedEvidence(
            "eval/full-chain.json",
            "2" * 64,
            {
                "schema_version": "huiji.candidate-full-chain/v1",
                "status": "pass",
                "candidate": {
                    "build_version": "candidate-v1",
                    "build_manifest_sha256": manifest_sha,
                    "collection": collection,
                },
            },
        ),
        "protected_compare": PinnedEvidence(
            "eval/protected.json",
            "3" * 64,
            {
                "schema_version": "huiji.protected_compare/v1",
                "status": "pass",
                "allowed_shadow_addition": {"collection": collection},
            },
        ),
        "wiki_compatibility": PinnedEvidence(
            "eval/wiki.json",
            "4" * 64,
            {
                "schema_version": "huiji.wiki-media-v3-compatibility-receipt/v1",
                "status": "passed",
            },
        ),
        "wiki_rollback": None,
        "bootstrap": None,
    }
    if include_rollback:
        values["wiki_rollback"] = PinnedEvidence(
            "eval/wiki-rollback.json",
            "5" * 64,
            {"schema_version": "huiji.wiki-rollback-receipt/v1", "status": "pass"},
        )
        values["bootstrap"] = PinnedEvidence(
            "eval/bootstrap.json",
            "7" * 64,
            {
                "schema_version": "huiji.generation-zero-bootstrap-receipt/v1",
                "status": "passed",
                "pointer": {"sha256": pointer_sha256},
                "protected_state_after": {"sha256": "3" * 64},
            },
        )
    return values, manifest_sha


def _previous_state() -> dict[str, object]:
    return {
        "pointer_path": "data/processed/huiji/active_build.v1.json",
        "build_manifest": {"sha256": "a" * 64},
        "collection_manifest": {"sha256": "b" * 64},
        "installed_provenance": {"sha256": "c" * 64},
        "settings": {"sha256": "d" * 64},
        "deployment_inventory": {"sha256": "e" * 64},
        "trusted_protected_compare": {"sha256": "f" * 64},
        "authorized_shadow_addition": {"collection": "shadow-v1"},
        "active_milvus": {"collection": "active"},
        "wiki_restore_entrypoint": {"path": "scripts/restore.py"},
        "minio_scopes": {
            "a-bucket": {},
            "reverse1999-assets/reverse1999": {},
        },
    }


def test_activation_review_blocks_without_pointer_and_wiki_rollback(tmp_path: Path):
    evidence, manifest_sha = _evidence(include_rollback=False)

    proposal, rollback = build_activation_review(
        proposal_id="proposal-v1",
        candidate_root="data/processed/huiji/candidate-v1",
        candidate_manifest_sha256=manifest_sha,
        candidate_state="ready_for_embedding",
        active_pointer_path=tmp_path / "active_build.v1.json",
        evidence=evidence,
        protected_inventory_ref={"path": "eval/protected-state.json", "sha256": "6" * 64},
    )

    assert proposal["allowed_for_activation_review"] is False
    assert proposal["blockers"] == [
        "active_pointer_not_bootstrapped",
        "generation_zero_bootstrap_not_verified",
        "previous_state_tuple_incomplete",
        "wiki_rollback_receipt_missing",
    ]
    assert proposal["rollback_tuple_created"] is False
    assert rollback is None


def test_activation_review_builds_rollback_only_for_complete_previous_tuple(tmp_path: Path):
    pointer = tmp_path / "active_build.v1.json"
    pointer.write_text(
        json.dumps({"schema_version": "evb.active-build/v1", "generation": 1}),
        encoding="utf-8",
    )
    import hashlib

    evidence, manifest_sha = _evidence(
        include_rollback=True,
        pointer_sha256=hashlib.sha256(pointer.read_bytes()).hexdigest(),
    )
    evidence["protected_compare"].payload.pop("allowed_shadow_addition")

    proposal, rollback = build_activation_review(
        proposal_id="proposal-v1",
        candidate_root="data/processed/huiji/candidate-v1",
        candidate_manifest_sha256=manifest_sha,
        candidate_state="ready_for_embedding",
        active_pointer_path=pointer,
        evidence=evidence,
        protected_inventory_ref={"path": "eval/protected-state.json", "sha256": "6" * 64},
        previous_state=_previous_state(),
    )

    assert proposal["allowed_for_activation_review"] is True
    assert proposal["blockers"] == []
    assert proposal["active_state_changed"] is False
    assert proposal["next_gate"] == "separate_user_approved_candidate_f_activation"
    assert proposal["rollback_tuple_created"] is True
    assert rollback is not None
    assert rollback["previous_pointer"]["payload"]["generation"] == 1
