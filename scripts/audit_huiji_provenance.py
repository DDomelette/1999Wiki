"""Run the full Huiji provenance audit and install a reviewed baseline."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.provenance import (
    ProvenanceValidationError,
    audit_huiji_provenance,
    build_baseline_candidate,
    install_baseline_create_new,
    safe_relative_path,
    write_hash_pinned_json,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Huiji RAG provenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--run-dir", type=Path, required=True)
    audit.add_argument("--candidate-baseline", type=Path, required=True)
    install = subparsers.add_parser("install-baseline")
    install.add_argument("--candidate", type=Path, required=True)
    install.add_argument("--output", type=Path, required=True)
    return parser


def _default_client(cfg: object) -> object:
    from pymilvus import MilvusClient

    vectorstore = getattr(cfg, "vectorstore")
    return MilvusClient(
        uri=str(getattr(vectorstore, "uri")),
        db_name=str(getattr(vectorstore, "db_name")),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    cfg_loader: Callable[[], Any] = get_config,
    client_factory: Callable[[object], object] = _default_client,
) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = cfg_loader()
        project_root = Path(getattr(getattr(cfg, "paths"), "project_root")).resolve()
        if args.command == "install-baseline":
            digest = install_baseline_create_new(
                args.candidate,
                args.output,
                project_root=project_root,
            )
            relative = safe_relative_path(args.output, project_root)
            print(f"status=pass baseline={relative} sha256={digest}")
            return 0

        run_dir = Path(args.run_dir)
        candidate_path = Path(args.candidate_baseline)
        safe_relative_path(run_dir, project_root)
        safe_relative_path(candidate_path, project_root)
        if run_dir.exists():
            raise FileExistsError("audit run directory already exists")
        if candidate_path.exists() or candidate_path.with_name(
            f"{candidate_path.name}.sha256"
        ).exists():
            raise FileExistsError("baseline candidate already exists")

        result = audit_huiji_provenance(cfg, client_factory(cfg))
        audit_path = run_dir / "audit.v1.json"
        audit_sha = write_hash_pinned_json(audit_path, result.to_evidence_dict())
        evidence_relpath = safe_relative_path(audit_path, project_root)
        if result.status == "pass":
            linked = replace(
                result,
                audit_evidence_relpath=evidence_relpath,
                audit_evidence_sha256=audit_sha,
            )
            write_hash_pinned_json(candidate_path, build_baseline_candidate(linked))
        codes = ",".join(sorted({issue.code for issue in result.issues}))
        print(
            f"status={result.status} errors={codes or 'none'} "
            f"evidence={evidence_relpath}"
        )
        if result.status == "pass":
            return 0
        if result.status == "blocked":
            return 2
        return 3
    except ProvenanceValidationError as error:
        print(f"status=blocked errors={error.code}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"status=error error_type={type(error).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
