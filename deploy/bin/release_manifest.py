#!/usr/bin/env python3
"""Create the machine-readable identity manifest for one image release."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


COMMIT_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORIES = {
    "backend": "ghcr.io/ddomelette/1999wiki-backend",
    "frontend": "ghcr.io/ddomelette/1999wiki-frontend",
}


class ManifestError(ValueError):
    pass


def _image_record(
    component: str,
    *,
    commit: str,
    tag: str,
    digest: str,
) -> dict[str, str]:
    expected_tag = f"{REPOSITORIES[component]}:sha-{commit[:7]}"
    if tag != expected_tag:
        raise ManifestError(f"{component} tag does not match the full commit")
    if DIGEST_RE.fullmatch(digest) is None:
        raise ManifestError(f"{component} digest is not a sha256 registry digest")
    return {"tag": tag, "digest": digest, "ref": f"{tag}@{digest}"}


def create_manifest(
    *,
    commit: str,
    backend_tag: str,
    backend_digest: str,
    frontend_tag: str,
    frontend_digest: str,
) -> dict[str, object]:
    if COMMIT_RE.fullmatch(commit) is None:
        raise ManifestError("commit must be a full lowercase Git SHA")
    return {
        "schema_version": "1999wiki.release/v1",
        "commit": commit,
        "images": {
            "backend": _image_record(
                "backend",
                commit=commit,
                tag=backend_tag,
                digest=backend_digest,
            ),
            "frontend": _image_record(
                "frontend",
                commit=commit,
                tag=frontend_tag,
                digest=frontend_digest,
            ),
        },
    }


def verify_manifest(path: Path, expected_commit: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        images = payload["images"]
        backend = images["backend"]
        frontend = images["frontend"]
        canonical = create_manifest(
            commit=payload["commit"],
            backend_tag=backend["tag"],
            backend_digest=backend["digest"],
            frontend_tag=frontend["tag"],
            frontend_digest=frontend["digest"],
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ManifestError("manifest schema is invalid") from exc
    if payload != canonical:
        raise ManifestError("manifest contains unexpected or divergent identity fields")
    if payload["commit"] != expected_commit:
        raise ManifestError("manifest commit does not match the reviewed full SHA")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--commit", required=True)
    create.add_argument("--backend-tag", required=True)
    create.add_argument("--backend-digest", required=True)
    create.add_argument("--frontend-tag", required=True)
    create.add_argument("--frontend-digest", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            payload = create_manifest(
                commit=args.commit,
                backend_tag=args.backend_tag,
                backend_digest=args.backend_digest,
                frontend_tag=args.frontend_tag,
                frontend_digest=args.frontend_digest,
            )
            args.output.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            payload = verify_manifest(args.manifest, args.commit)
            print(f"RELEASE_COMMIT={payload['commit']}")
            images = payload["images"]
            print(f"BACKEND_IMAGE={images['backend']['ref']}")
            print(f"FRONTEND_IMAGE={images['frontend']['ref']}")
    except (OSError, ManifestError) as exc:
        print(f"release-manifest: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
