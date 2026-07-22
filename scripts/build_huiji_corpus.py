"""Build, verify or prepare review evidence for one immutable Huiji candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config  # noqa: E402
from src.huiji_rag.build import (  # noqa: E402
    BuildState,
    CorpusBuildRequest,
    HuijiCorpusBuilder,
)
from src.huiji_rag.build.contracts import canonical_json_bytes  # noqa: E402
from src.huiji_rag.build.activation_evidence import (  # noqa: E402
    PinnedEvidence,
    build_activation_review,
    summarize_protected_compare,
)
from src.huiji_rag.provenance import (  # noqa: E402
    safe_relative_path,
    write_hash_pinned_json,
)
from src.huiji_rag.generation_zero import (  # noqa: E402
    load_hash_pinned_json,
    validate_bootstrap_receipt,
    validate_wiki_rollback_receipt,
)


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and verify immutable crawler-only Huiji corpus candidates."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    candidate = subparsers.add_parser(
        "candidate", help="build one create-new candidate without embedding or activation"
    )
    candidate.add_argument("--build-version", required=True)
    candidate.add_argument("--fidelity-baseline", type=Path, required=True)
    candidate.add_argument("--expected-fidelity-baseline-sha256", required=True)
    candidate.add_argument("--run-dir", type=Path, required=True)
    candidate.add_argument("--raw-root", type=Path)
    candidate.add_argument("--processed-root", type=Path)
    candidate.add_argument(
        "--wiki-compatibility-receipt",
        type=Path,
        default=_optional_env_path("HUIJI_WIKI_V3_COMPAT_RECEIPT"),
    )
    candidate.add_argument(
        "--expected-wiki-compatibility-receipt-sha256",
        default=os.environ.get("HUIJI_WIKI_V3_COMPAT_RECEIPT_SHA256", ""),
    )
    candidate.add_argument("--minio-inventory", type=Path)
    candidate.add_argument("--expected-minio-inventory-sha256", default="")

    verify = subparsers.add_parser(
        "verify", help="verify one hash-pinned candidate without repairing it"
    )
    verify.add_argument("--build-root", type=Path, required=True)
    verify.add_argument("--expected-build-manifest-sha256", required=True)

    proposal = subparsers.add_parser(
        "proposal",
        help="create review-only activation evidence; never change active state",
    )
    proposal.add_argument("--proposal-id", required=True)
    proposal.add_argument("--candidate-build-root", type=Path, required=True)
    proposal.add_argument("--expected-build-manifest-sha256", required=True)
    proposal.add_argument("--output-root", type=Path)
    for name in (
        "shadow-evidence",
        "full-chain-evidence",
        "protected-baseline",
        "protected-compare-evidence",
        "wiki-compatibility-receipt",
        "wiki-rollback-receipt",
        "bootstrap-receipt",
    ):
        proposal.add_argument(f"--{name}", type=Path)
        proposal.add_argument(f"--expected-{name}-sha256", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "candidate":
            return _run_candidate(args)
        if args.command == "verify":
            return _run_verify(args)
        return _run_proposal(args)
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "schema_version": "huiji.corpus-cli-error/v1",
                    "command": args.command,
                    "status": "error",
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def _run_candidate(args: argparse.Namespace) -> int:
    cfg = get_config()
    receipt = args.wiki_compatibility_receipt
    receipt_sha = str(args.expected_wiki_compatibility_receipt_sha256 or "")
    _require_path_hash_pair(receipt, receipt_sha, "Wiki compatibility receipt")
    inventory = args.minio_inventory
    inventory_sha = str(args.expected_minio_inventory_sha256 or "")
    _require_path_hash_pair(inventory, inventory_sha, "MinIO inventory")

    request = CorpusBuildRequest(
        build_version=args.build_version,
        raw_root=args.raw_root or cfg.huiji.raw_root,
        processed_root=args.processed_root or cfg.huiji.processed_root,
        run_dir=args.run_dir,
        fidelity_baseline_path=args.fidelity_baseline,
        expected_fidelity_baseline_sha256=args.expected_fidelity_baseline_sha256,
        wiki_compatibility_receipt_path=receipt,
        expected_wiki_compatibility_receipt_sha256=receipt_sha,
        configured_build_version=cfg.huiji.build_version,
        active_pointer_path=cfg.huiji.processed_root / "active_build.v1.json",
        project_root=PROJECT_ROOT,
        minio_inventory_path=inventory,
        expected_minio_inventory_sha256=inventory_sha,
        public_base_url=cfg.assets.public_base_url,
        bucket_name=cfg.assets.bucket_name,
        object_prefix=cfg.assets.object_prefix,
        embedding_provider=cfg.embedding.provider,
        embedding_model=cfg.embedding.model,
        forbidden_collection_names=(
            cfg.vectorstore.collection_name,
            cfg.huiji.text_collection_name,
            cfg.huiji.asset_caption_collection_name,
        ),
    )
    result = HuijiCorpusBuilder().build_candidate(request)
    manifest_sha = (
        _file_sha256(result.build_manifest)
        if result.build_manifest is not None and result.build_manifest.is_file()
        else None
    )
    payload = {
        "build_root": str(result.build_root),
        "state": result.state.value,
        "row_counts": dict(result.row_counts),
        "build_manifest": None
        if result.build_manifest is None
        else str(result.build_manifest),
        "build_manifest_sha256": manifest_sha,
        "blockers": list(result.blockers),
        "conflict_or_exclusion_counts": {
            key: value
            for key, value in result.row_counts.items()
            if key in {"conflicts", "quarantine", "excluded"}
        },
        "next_gate": (
            "user_run_embedding"
            if result.state is BuildState.READY_FOR_EMBEDDING
            else "resolve_blockers_and_rebuild_under_new_version"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if result.state is BuildState.READY_FOR_EMBEDDING else 3


def _run_verify(args: argparse.Namespace) -> int:
    _require_sha256(args.expected_build_manifest_sha256, "build manifest")
    payload = HuijiCorpusBuilder().verify_candidate(
        args.build_root, args.expected_build_manifest_sha256
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _run_proposal(args: argparse.Namespace) -> int:
    """Create hash-pinned activation-review evidence without activating."""
    if not _ID_RE.fullmatch(args.proposal_id):
        raise ValueError("proposal_id must use the corpus candidate ID grammar")
    _require_sha256(args.expected_build_manifest_sha256, "build manifest")
    cfg = get_config()
    configured_paths = getattr(cfg, "paths", None)
    project_root = Path(
        getattr(configured_paths, "project_root", "")
        or (Path(args.output_root).resolve().parent if args.output_root else PROJECT_ROOT)
    ).resolve()
    verified = HuijiCorpusBuilder().verify_candidate(
        args.candidate_build_root, args.expected_build_manifest_sha256
    )
    output_root = args.output_root or (
        cfg.huiji.processed_root / "activation" / "proposals"
    )
    proposal_root = (Path(output_root).resolve() / args.proposal_id).resolve()
    if proposal_root.exists():
        raise FileExistsError(f"proposal directory already exists: {proposal_root}")
    pointer = cfg.huiji.processed_root / "active_build.v1.json"
    evidence_args = {
        "shadow": (args.shadow_evidence, args.expected_shadow_evidence_sha256),
        "full_chain": (args.full_chain_evidence, args.expected_full_chain_evidence_sha256),
        "protected_baseline": (args.protected_baseline, args.expected_protected_baseline_sha256),
        "protected_compare": (
            args.protected_compare_evidence,
            args.expected_protected_compare_evidence_sha256,
        ),
        "wiki_compatibility": (
            args.wiki_compatibility_receipt,
            args.expected_wiki_compatibility_receipt_sha256,
        ),
        "wiki_rollback": (
            args.wiki_rollback_receipt,
            args.expected_wiki_rollback_receipt_sha256,
        ),
        "bootstrap": (
            args.bootstrap_receipt,
            args.expected_bootstrap_receipt_sha256,
        ),
    }
    evidence: dict[str, PinnedEvidence | None] = {}
    for name, (path, digest) in evidence_args.items():
        _require_path_hash_pair(path, digest, name.replace("_", " "))
        evidence[name] = (
            None
            if path is None
            else _load_pinned_evidence(path, digest, project_root)
        )

    previous_state = _load_previous_state(
        project_root,
        evidence,
        active_pointer_path=pointer,
    )

    baseline = evidence.get("protected_baseline")
    comparison = evidence.get("protected_compare")
    if baseline is None or comparison is None:
        protected_payload = {
            "schema_version": "huiji.activation-protected-state/v1",
            "status": "blocked",
            "blockers": ["protected_state_evidence_missing"],
        }
    else:
        protected_payload = summarize_protected_compare(baseline, comparison)
        protected_payload["status"] = (
            "pass"
            if comparison.payload.get("status") == "pass"
            and not comparison.payload.get("changes")
            else "blocked"
        )
    proposal_root.mkdir(parents=True, exist_ok=False)
    protected_path = proposal_root / "protected_state_inventory.v1.json"
    protected_sha = write_hash_pinned_json(protected_path, protected_payload)
    protected_ref = {
        "path": safe_relative_path(protected_path, project_root),
        "sha256": protected_sha,
    }
    proposal_payload, rollback_payload = build_activation_review(
        proposal_id=args.proposal_id,
        candidate_root=safe_relative_path(args.candidate_build_root, project_root),
        candidate_manifest_sha256=args.expected_build_manifest_sha256,
        candidate_state=str(verified["state"]),
        active_pointer_path=pointer,
        evidence=evidence,
        protected_inventory_ref=protected_ref,
        previous_state=previous_state,
    )
    output = proposal_root / "activation_proposal.v1.json"
    proposal_sha = write_hash_pinned_json(output, proposal_payload)
    if rollback_payload is not None:
        write_hash_pinned_json(proposal_root / "rollback_tuple.v1.json", rollback_payload)
    public = {
        **proposal_payload,
        "path": safe_relative_path(output, project_root),
        "sha256": proposal_sha,
    }
    print(json.dumps(public, ensure_ascii=False, sort_keys=True))
    return 0 if proposal_payload["allowed_for_activation_review"] else 3


def _load_previous_state(
    project_root: Path,
    evidence: Mapping[str, PinnedEvidence | None],
    *,
    active_pointer_path: Path,
) -> dict[str, object] | None:
    bootstrap = evidence.get("bootstrap")
    wiki = evidence.get("wiki_rollback")
    protected = evidence.get("protected_compare")
    if bootstrap is None or wiki is None or protected is None:
        return None
    bootstrap_path = (project_root / bootstrap.path).resolve()
    bootstrap_payload = validate_bootstrap_receipt(
        bootstrap_path, project_root=project_root
    )
    wiki_path = (project_root / wiki.path).resolve()
    if (
        wiki.sha256
        != "e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6"
        or "legacy-dev-pre-candidate-f-20260721b" not in wiki.path
    ):
        raise ValueError("only the approved 20260721b Wiki rollback Receipt is accepted")
    wiki_payload = validate_wiki_rollback_receipt(
        wiki_path, wiki.sha256, project_root
    )
    if bootstrap_payload.get("wiki_rollback_receipt", {}).get("sha256") != wiki.sha256:
        raise ValueError("bootstrap and proposal Wiki rollback Receipts differ")
    pointer_ref = bootstrap_payload.get("pointer")
    collection_ref = bootstrap_payload.get("collection_manifest")
    inventory_ref = bootstrap_payload.get("deployment_inventory")
    after_ref = bootstrap_payload.get("protected_state_after")
    if not all(
        isinstance(value, Mapping)
        for value in (pointer_ref, collection_ref, inventory_ref, after_ref)
    ):
        raise ValueError("bootstrap Receipt previous-state references are incomplete")
    if pointer_ref.get("relative_path") != safe_relative_path(active_pointer_path, project_root):
        raise ValueError("bootstrap Receipt pointer path mismatch")
    if after_ref.get("sha256") != protected.sha256:
        raise ValueError("bootstrap Receipt protected compare mismatch")
    collection_path = (project_root / str(collection_ref["relative_path"])).resolve()
    inventory_path = (project_root / str(inventory_ref["relative_path"])).resolve()
    collection, _ = load_hash_pinned_json(
        collection_path,
        expected_sha256=str(collection_ref["sha256"]),
        expected_schema="evb.collection-manifest/v1",
    )
    inventory, _ = load_hash_pinned_json(
        inventory_path,
        expected_sha256=str(inventory_ref["sha256"]),
        expected_schema="huiji.generation-zero-deployment-inventory/v1",
    )
    trusted_ref = inventory.get("trusted_protected_compare")
    if not isinstance(trusted_ref, Mapping):
        raise ValueError("generation-zero deployment inventory lacks trusted compare")
    trusted_path = (project_root / str(trusted_ref.get("relative_path") or "")).resolve()
    trusted, _ = load_hash_pinned_json(
        trusted_path,
        expected_sha256=str(trusted_ref.get("sha256") or ""),
        expected_schema="huiji.protected_compare/v1",
    )
    authorized_shadow = trusted.get("allowed_shadow_addition")
    if (
        trusted.get("status") != "pass"
        or trusted.get("changes") != []
        or not isinstance(authorized_shadow, Mapping)
        or not str(authorized_shadow.get("collection") or "")
    ):
        raise ValueError("generation-zero trusted shadow authorization is invalid")
    after = protected.payload.get("after")
    minio = after.get("minio_inventories") if isinstance(after, Mapping) else None
    expected_minio_scopes = {
        "a-bucket": ("a-bucket", ""),
        "reverse1999-assets/reverse1999": ("reverse1999-assets", "reverse1999"),
    }
    if not isinstance(minio, Mapping) or set(minio) != set(expected_minio_scopes):
        raise ValueError("bootstrap protected compare MinIO scopes are incomplete")
    minio_scopes: dict[str, object] = {}
    for scope, value in sorted(minio.items()):
        if not isinstance(value, Mapping) or not isinstance(value.get("objects"), list):
            raise ValueError(f"bootstrap MinIO scope is invalid: {scope}")
        expected_bucket, expected_prefix = expected_minio_scopes[str(scope)]
        if value.get("bucket") != expected_bucket or value.get("prefix") != expected_prefix:
            raise ValueError(f"bootstrap MinIO scope identity mismatch: {scope}")
        minio_scopes[str(scope)] = {
            "protected_compare": protected.reference(),
            "bucket": value.get("bucket"),
            "prefix": value.get("prefix"),
            "object_count": len(value["objects"]),
        }
    return {
        "pointer_path": str(pointer_ref["relative_path"]),
        "build_manifest": collection["build_manifest"],
        "collection_manifest": dict(collection_ref),
        "installed_provenance": collection["installed_provenance"],
        "settings": inventory["settings"],
        "deployment_inventory": dict(inventory_ref),
        "trusted_protected_compare": dict(trusted_ref),
        "authorized_shadow_addition": dict(authorized_shadow),
        "active_milvus": inventory["active_milvus"],
        "wiki_restore_entrypoint": wiki_payload["restore_entrypoint"],
        "minio_scopes": minio_scopes,
    }


def _load_pinned_evidence(
    path: Path,
    expected_sha256: str,
    project_root: Path,
) -> PinnedEvidence:
    target = Path(path).resolve()
    relative = safe_relative_path(target, project_root)
    if not target.is_file() or _file_sha256(target) != expected_sha256:
        raise ValueError(f"evidence SHA-256 mismatch: {relative}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence is not a JSON object: {relative}")
    return PinnedEvidence(relative, expected_sha256, payload)


def _require_path_hash_pair(path: Path | None, digest: str, label: str) -> None:
    if (path is None) != (not digest):
        raise ValueError(f"{label} path and expected SHA-256 must be supplied together")
    if digest:
        _require_sha256(digest, label)


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256_RE.fullmatch(str(value)):
        raise ValueError(f"{label} expected SHA-256 must be lowercase hexadecimal")


def _optional_env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
