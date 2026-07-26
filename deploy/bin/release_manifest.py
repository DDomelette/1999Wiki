#!/usr/bin/env python3
"""Thin CLI for canonical v2 release manifests and mirror attestations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from release_identity import (
    GHCR_STATUSES,
    REPOSITORIES,
    ManifestError,
    canonical_json,
    create_mirror_attestation,
    create_release_manifest,
    emit_release_env,
    verify_release_manifest_bytes,
)


def _load_json(path: Path) -> object:
    return json.loads(path.read_bytes())


def _create(args: argparse.Namespace) -> None:
    payload = create_release_manifest(
        args.commit,
        {
            "backend": args.backend_digest,
            "frontend": args.frontend_digest,
        },
        {
            "backend": args.backend_ghcr_status,
            "frontend": args.frontend_ghcr_status,
        },
    )
    args.output.write_bytes(canonical_json(payload))


def _verify(args: argparse.Namespace) -> None:
    manifest_raw = args.manifest.read_bytes()
    manifest = verify_release_manifest_bytes(manifest_raw, args.commit)
    attestation = _load_json(args.attestation) if args.attestation else None
    for line in emit_release_env(manifest, args.registry, attestation):
        print(line)


def _attest(args: argparse.Namespace) -> None:
    manifest_raw = args.manifest.read_bytes()
    verify_release_manifest_bytes(manifest_raw, args.commit)
    payload = create_mirror_attestation(
        manifest_raw,
        {
            "backend": args.backend_ghcr_ref,
            "frontend": args.frontend_ghcr_ref,
        },
        args.workflow_run_id,
        args.completed_at,
    )
    args.output.write_bytes(canonical_json(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("--commit", required=True)
    create.add_argument("--backend-digest", required=True)
    create.add_argument("--frontend-digest", required=True)
    create.add_argument(
        "--backend-ghcr-status",
        choices=sorted(GHCR_STATUSES),
        required=True,
    )
    create.add_argument(
        "--frontend-ghcr-status",
        choices=sorted(GHCR_STATUSES),
        required=True,
    )
    create.add_argument("--output", type=Path, required=True)
    create.set_defaults(handler=_create)

    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--commit", required=True)
    verify.add_argument("--registry", choices=tuple(REPOSITORIES), required=True)
    verify.add_argument("--attestation", type=Path)
    verify.set_defaults(handler=_verify)

    attest = commands.add_parser("attest")
    attest.add_argument("--manifest", type=Path, required=True)
    attest.add_argument("--commit", required=True)
    attest.add_argument("--backend-ghcr-ref", required=True)
    attest.add_argument("--frontend-ghcr-ref", required=True)
    attest.add_argument("--workflow-run-id", required=True)
    attest.add_argument("--completed-at", required=True)
    attest.add_argument("--output", type=Path, required=True)
    attest.set_defaults(handler=_attest)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
    except (OSError, UnicodeError, json.JSONDecodeError, ManifestError) as exc:
        print(f"release-manifest: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
