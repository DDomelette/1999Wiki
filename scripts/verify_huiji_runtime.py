"""Fast fail-closed runtime verifier for the installed Huiji baseline."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.provenance import (
    RUNTIME_SCHEMA,
    safe_relative_path,
    verify_runtime,
    write_hash_pinned_json,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify Huiji runtime provenance")
    parser.add_argument("--run-dir", type=Path)
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
        if args.run_dir is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            run_dir = project_root / "eval" / "huiji_provenance" / f"{stamp}-runtime-{uuid4().hex[:8]}"
        else:
            run_dir = Path(args.run_dir)
        safe_relative_path(run_dir, project_root)
        if run_dir.exists():
            raise FileExistsError("runtime evidence directory already exists")
        evidence_path = run_dir / "runtime.v1.json"
        relative = safe_relative_path(evidence_path, project_root)
        result = replace(
            verify_runtime(cfg, client_factory=client_factory),
            evidence_relpath=relative,
        )
        write_hash_pinned_json(
            evidence_path,
            {"schema_version": RUNTIME_SCHEMA, **result.to_public_dict()},
        )
        codes = ",".join(issue.code for issue in result.issues) or "none"
        print(f"status={result.status} errors={codes} evidence={relative}")
        if result.status == "pass":
            return 0
        if result.status == "blocked":
            return 2
        return 3
    except Exception as error:
        print(f"status=error error_type={type(error).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
