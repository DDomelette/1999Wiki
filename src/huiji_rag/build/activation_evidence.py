"""Pure builders for read-only activation-review evidence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.huiji_rag.build.contracts import canonical_json_bytes


@dataclass(frozen=True)
class PinnedEvidence:
    path: str
    sha256: str
    payload: Mapping[str, Any]

    def reference(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


def summarize_protected_compare(
    baseline: PinnedEvidence,
    comparison: PinnedEvidence,
) -> dict[str, object]:
    after = comparison.payload.get("after")
    if not isinstance(after, Mapping):
        raise ValueError("protected compare lacks after snapshot")
    minio = after.get("minio_inventories")
    mysql = after.get("mysql_tables")
    artifacts = after.get("artifacts")
    if not isinstance(minio, Mapping) or not isinstance(mysql, Mapping) or not isinstance(artifacts, Mapping):
        raise ValueError("protected compare after snapshot is incomplete")
    minio_summary: dict[str, dict[str, object]] = {}
    for scope, inventory in sorted(minio.items()):
        if not isinstance(inventory, Mapping) or not isinstance(inventory.get("objects"), list):
            raise ValueError(f"protected MinIO scope is invalid: {scope}")
        identities = [
            {
                "object_key": str(item.get("object_key") or ""),
                "size": int(item.get("size") or 0),
                "etag": str(item.get("etag") or ""),
                "version_id": item.get("version_id"),
            }
            for item in inventory["objects"]
            if isinstance(item, Mapping)
        ]
        minio_summary[str(scope)] = {
            "object_count": len(identities),
            "listing_identity_sha256": hashlib.sha256(
                canonical_json_bytes(identities, trailing_newline=False)
            ).hexdigest(),
            "bucket_policy_summary": str(inventory.get("bucket_policy_summary") or ""),
        }
    return {
        "schema_version": "huiji.activation-protected-state/v1",
        "baseline": baseline.reference(),
        "comparison": comparison.reference(),
        "comparison_status": str(comparison.payload.get("status") or ""),
        "comparison_changes": list(comparison.payload.get("changes") or []),
        "minio_capture_mode": str(comparison.payload.get("minio_capture_mode") or "full-content"),
        "milvus": dict(after.get("milvus") or {}),
        "minio": minio_summary,
        "mysql": {str(key): dict(value) for key, value in sorted(mysql.items()) if isinstance(value, Mapping)},
        "artifact_count": len(artifacts),
        "artifacts_sha256": hashlib.sha256(
            canonical_json_bytes(dict(sorted(artifacts.items())), trailing_newline=False)
        ).hexdigest(),
    }


def build_activation_review(
    *,
    proposal_id: str,
    candidate_root: str,
    candidate_manifest_sha256: str,
    candidate_state: str,
    active_pointer_path: Path,
    evidence: Mapping[str, PinnedEvidence | None],
    protected_inventory_ref: Mapping[str, str],
    previous_state: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    blockers: list[str] = []
    required = {
        "shadow": ("huiji.shadow_build/v1", "shadow_not_verified"),
        "full_chain": ("huiji.candidate-full-chain/v1", "full_chain_not_verified"),
        "protected_compare": ("huiji.protected_compare/v1", "protected_state_not_verified"),
        "wiki_compatibility": (
            "huiji.wiki-media-v3-compatibility-receipt/v1",
            "wiki_compatibility_not_verified",
        ),
        "bootstrap": (
            "huiji.generation-zero-bootstrap-receipt/v1",
            "generation_zero_bootstrap_not_verified",
        ),
    }
    for name, (schema, blocker) in required.items():
        item = evidence.get(name)
        if item is None or item.payload.get("schema_version") != schema or item.payload.get("status") not in {"pass", "passed"}:
            blockers.append(blocker)
    shadow = evidence.get("shadow")
    full_chain = evidence.get("full_chain")
    protected = evidence.get("protected_compare")
    if shadow is not None and full_chain is not None:
        candidate = full_chain.payload.get("candidate")
        if (
            not isinstance(candidate, Mapping)
            or candidate.get("build_manifest_sha256") != candidate_manifest_sha256
            or candidate.get("collection") != shadow.payload.get("collection")
            or candidate.get("build_version") != shadow.payload.get("candidate_build_version")
        ):
            blockers.append("candidate_shadow_full_chain_tuple_mismatch")
    if shadow is not None and protected is not None:
        allowed_shadow = protected.payload.get("allowed_shadow_addition")
        if not isinstance(allowed_shadow, Mapping) and previous_state is not None:
            allowed_shadow = previous_state.get("authorized_shadow_addition")
        if not isinstance(allowed_shadow, Mapping) or allowed_shadow.get("collection") != shadow.payload.get("collection"):
            blockers.append("shadow_protected_state_tuple_mismatch")
    if candidate_state != "ready_for_embedding":
        blockers.append("candidate_not_ready_for_embedding")

    pointer_payload: dict[str, Any] | None = None
    pointer_sha256 = ""
    if active_pointer_path.is_file():
        pointer_bytes = active_pointer_path.read_bytes()
        pointer_sha256 = hashlib.sha256(pointer_bytes).hexdigest()
        try:
            loaded = json.loads(pointer_bytes)
        except (UnicodeError, json.JSONDecodeError):
            blockers.append("active_pointer_invalid")
        else:
            if isinstance(loaded, dict):
                pointer_payload = loaded
            else:
                blockers.append("active_pointer_invalid")
    else:
        blockers.append("active_pointer_not_bootstrapped")

    wiki_rollback = evidence.get("wiki_rollback")
    if wiki_rollback is None:
        blockers.append("wiki_rollback_receipt_missing")
    bootstrap = evidence.get("bootstrap")
    if bootstrap is not None:
        pointer_ref = bootstrap.payload.get("pointer")
        protected_ref = bootstrap.payload.get("protected_state_after")
        if (
            bootstrap.payload.get("status") != "passed"
            or not isinstance(pointer_ref, Mapping)
            or pointer_ref.get("sha256") != pointer_sha256
            or not isinstance(protected_ref, Mapping)
            or protected is None
            or protected_ref.get("sha256") != protected.sha256
        ):
            blockers.append("generation_zero_bootstrap_tuple_mismatch")
    required_previous = {
        "pointer_path",
        "build_manifest",
        "collection_manifest",
        "installed_provenance",
        "settings",
        "deployment_inventory",
        "trusted_protected_compare",
        "authorized_shadow_addition",
        "active_milvus",
        "wiki_restore_entrypoint",
        "minio_scopes",
    }
    if previous_state is None or not required_previous.issubset(previous_state):
        blockers.append("previous_state_tuple_incomplete")
    blockers = sorted(set(blockers))
    rollback: dict[str, object] | None = None
    if (
        not blockers
        and pointer_payload is not None
        and wiki_rollback is not None
        and previous_state is not None
    ):
        rollback = {
            "schema_version": "huiji.rollback-tuple/v1",
            "proposal_id": proposal_id,
            "previous_pointer": {
                "path": previous_state["pointer_path"],
                "sha256": pointer_sha256,
                "payload": pointer_payload,
            },
            "previous_build_manifest": previous_state["build_manifest"],
            "previous_collection_manifest": previous_state["collection_manifest"],
            "previous_installed_provenance": previous_state["installed_provenance"],
            "previous_settings": previous_state["settings"],
            "previous_deployment_inventory": previous_state["deployment_inventory"],
            "previous_trusted_protected_compare": previous_state[
                "trusted_protected_compare"
            ],
            "authorized_shadow_addition": previous_state[
                "authorized_shadow_addition"
            ],
            "previous_active_milvus": previous_state["active_milvus"],
            "wiki_rollback_receipt": wiki_rollback.reference(),
            "wiki_restore_entrypoint": previous_state["wiki_restore_entrypoint"],
            "minio_scopes": previous_state["minio_scopes"],
            "protected_state_inventory": dict(protected_inventory_ref),
        }

    proposal = {
        "schema_version": "huiji.activation-proposal/v1",
        "proposal_id": proposal_id,
        "candidate": {
            "build_root": candidate_root,
            "build_manifest_sha256": candidate_manifest_sha256,
            "state": candidate_state,
        },
        "evidence": {
            name: item.reference()
            for name, item in sorted(evidence.items())
            if item is not None
        },
        "protected_state_inventory": dict(protected_inventory_ref),
        "expected_previous_pointer_sha256": pointer_sha256,
        "allowed_for_activation_review": not blockers,
        "blockers": blockers,
        "rollback_tuple_created": rollback is not None,
        "active_state_changed": False,
        "next_gate": (
            "separate_user_approved_candidate_f_activation"
            if not blockers
            else "resolve_activation_review_blockers"
        ),
    }
    return proposal, rollback


__all__ = [
    "PinnedEvidence",
    "build_activation_review",
    "summarize_protected_compare",
]
