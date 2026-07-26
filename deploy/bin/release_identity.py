#!/usr/bin/env python3
"""Canonical identities for TCR-first releases and their GHCR mirrors."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
import re


SCHEMA_VERSION = "1999wiki.release/v2"
ATTESTATION_SCHEMA_VERSION = "1999wiki.mirror-attestation/v1"
COMPONENTS = ("backend", "frontend")
REPOSITORIES = {
    "tcr": {
        "backend": "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend",
        "frontend": "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend",
    },
    "ghcr": {
        "backend": "ghcr.io/ddomelette/1999wiki-backend",
        "frontend": "ghcr.io/ddomelette/1999wiki-frontend",
    },
}
GHCR_STATUSES = {"published", "deferred_after_5_network_failures"}

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\Z"
)


class ManifestError(ValueError):
    """Raised when release identity data is not its exact canonical schema."""


def canonical_json(payload: Mapping[str, object]) -> bytes:
    """Serialize an identity record in the single permitted byte representation."""
    return (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ManifestError(f"{label} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ManifestError(f"{label} has missing or unexpected fields")


def _validate_commit(commit: object) -> str:
    if not isinstance(commit, str) or _COMMIT_RE.fullmatch(commit) is None:
        raise ManifestError("commit must be a full lowercase Git SHA")
    return commit


def _validate_digest(digest: object, component: str) -> str:
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        raise ManifestError(f"{component} digest must be a sha256 registry digest")
    return digest


def _release_tag(commit: str) -> str:
    return f"sha-{commit[:7]}"


def _ref(registry: str, component: str, commit: str, digest: str) -> str:
    return (
        f"{REPOSITORIES[registry][component]}:{_release_tag(commit)}@{digest}"
    )


def _release_state(ghcr_statuses: Mapping[str, str]) -> str:
    return (
        "fully_mirrored"
        if all(ghcr_statuses[component] == "published" for component in COMPONENTS)
        else "ready_with_deferred_ghcr"
    )


def create_release_manifest(
    commit: str,
    digests: Mapping[str, str],
    ghcr_statuses: Mapping[str, str],
) -> dict[str, object]:
    """Build the sole canonical v2 release manifest from its source facts."""
    commit = _validate_commit(commit)
    digests = _require_mapping(digests, "digests")
    ghcr_statuses = _require_mapping(ghcr_statuses, "ghcr_statuses")
    _require_exact_keys(digests, set(COMPONENTS), "digests")
    _require_exact_keys(ghcr_statuses, set(COMPONENTS), "ghcr_statuses")

    checked_digests: dict[str, str] = {}
    checked_statuses: dict[str, str] = {}
    for component in COMPONENTS:
        checked_digests[component] = _validate_digest(digests[component], component)
        status = ghcr_statuses[component]
        if not isinstance(status, str) or status not in GHCR_STATUSES:
            raise ManifestError(f"{component} GHCR status is invalid")
        checked_statuses[component] = status

    images: dict[str, object] = {}
    for component in COMPONENTS:
        digest = checked_digests[component]
        tcr_tag = f"{REPOSITORIES['tcr'][component]}:{_release_tag(commit)}"
        ghcr_tag = f"{REPOSITORIES['ghcr'][component]}:{_release_tag(commit)}"
        ghcr_status = checked_statuses[component]
        images[component] = {
            "digest": digest,
            "registries": {
                "tcr": {
                    "status": "published",
                    "tag": tcr_tag,
                    "ref": f"{tcr_tag}@{digest}",
                },
                "ghcr": {
                    "status": ghcr_status,
                    "tag": ghcr_tag,
                    "ref": f"{ghcr_tag}@{digest}"
                    if ghcr_status == "published"
                    else None,
                },
            },
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "commit": commit,
        "release_tag": _release_tag(commit),
        "primary_registry": "tcr",
        "release_state": _release_state(checked_statuses),
        "images": images,
    }


def _decode_manifest(raw: bytes) -> Mapping[str, object]:
    if not isinstance(raw, bytes):
        raise ManifestError("manifest must be UTF-8 JSON bytes")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError("manifest is not valid UTF-8 JSON") from exc
    return _require_mapping(payload, "manifest")


def verify_release_manifest_bytes(raw: bytes, expected_commit: str) -> dict[str, object]:
    """Validate schema, derived fields, and exact canonical bytes of a manifest."""
    expected_commit = _validate_commit(expected_commit)
    payload = _decode_manifest(raw)
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "commit",
            "release_tag",
            "primary_registry",
            "release_state",
            "images",
        },
        "manifest",
    )
    images = _require_mapping(payload["images"], "manifest images")
    _require_exact_keys(images, set(COMPONENTS), "manifest images")
    commit = _validate_commit(payload["commit"])

    digests: dict[str, str] = {}
    statuses: dict[str, str] = {}
    for component in COMPONENTS:
        image = _require_mapping(images[component], f"{component} image")
        _require_exact_keys(image, {"digest", "registries"}, f"{component} image")
        digests[component] = _validate_digest(image["digest"], component)
        registries = _require_mapping(image["registries"], f"{component} registries")
        _require_exact_keys(registries, {"tcr", "ghcr"}, f"{component} registries")
        ghcr = _require_mapping(registries["ghcr"], f"{component} GHCR record")
        statuses[component] = ghcr.get("status")  # type: ignore[assignment]

    canonical = create_release_manifest(commit, digests, statuses)
    if payload != canonical or raw != canonical_json(canonical):
        raise ManifestError("manifest contains unexpected or divergent identity fields")
    if commit != expected_commit:
        raise ManifestError("manifest commit does not match the reviewed full SHA")
    return canonical


def _validate_workflow_run_id(value: object) -> str:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ManifestError("workflow_run_id must contain ASCII decimal digits only")
    return value


def _validate_completed_at(value: object) -> str:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        raise ManifestError("completed_at must be an RFC 3339 UTC Z timestamp")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ManifestError("completed_at must be an RFC 3339 UTC Z timestamp") from exc
    return value


def _manifest_from_bytes(manifest_raw: bytes) -> dict[str, object]:
    payload = _decode_manifest(manifest_raw)
    commit = _validate_commit(payload.get("commit"))
    return verify_release_manifest_bytes(manifest_raw, commit)


def _validate_ghcr_refs(
    manifest: Mapping[str, object], ghcr_refs: Mapping[str, str]
) -> dict[str, str]:
    ghcr_refs = _require_mapping(ghcr_refs, "ghcr_refs")
    _require_exact_keys(ghcr_refs, set(COMPONENTS), "ghcr_refs")
    images = _require_mapping(manifest["images"], "manifest images")
    commit = _validate_commit(manifest["commit"])
    result: dict[str, str] = {}
    for component in COMPONENTS:
        image = _require_mapping(images[component], f"{component} image")
        digest = _validate_digest(image["digest"], component)
        ref = ghcr_refs[component]
        expected_ref = _ref("ghcr", component, commit, digest)
        if not isinstance(ref, str) or ref != expected_ref:
            raise ManifestError(f"{component} GHCR reference does not match manifest")
        result[component] = ref
    return result


def create_mirror_attestation(
    manifest_raw: bytes,
    ghcr_refs: Mapping[str, str],
    workflow_run_id: str,
    completed_at: str,
) -> dict[str, object]:
    """Create a completed mirror attestation bound to canonical manifest bytes."""
    manifest = _manifest_from_bytes(manifest_raw)
    refs = _validate_ghcr_refs(manifest, ghcr_refs)
    workflow_run_id = _validate_workflow_run_id(workflow_run_id)
    completed_at = _validate_completed_at(completed_at)
    commit = _validate_commit(manifest["commit"])
    images = _require_mapping(manifest["images"], "manifest images")
    attestation_images: dict[str, object] = {}
    for component in COMPONENTS:
        image = _require_mapping(images[component], f"{component} image")
        digest = _validate_digest(image["digest"], component)
        attestation_images[component] = {
            "source": _ref("tcr", component, commit, digest),
            "destination": refs[component],
            "digest": digest,
        }
    return {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "manifest_sha256": "sha256:" + hashlib.sha256(manifest_raw).hexdigest(),
        "commit": commit,
        "status": "completed",
        "workflow_run_id": workflow_run_id,
        "completed_at": completed_at,
        "images": attestation_images,
    }


def verify_mirror_attestation(
    manifest_raw: bytes,
    attestation: Mapping[str, object],
    expected_commit: str,
) -> dict[str, object]:
    """Verify a completed attestation against the exact release manifest bytes."""
    manifest = _manifest_from_bytes(manifest_raw)
    expected_commit = _validate_commit(expected_commit)
    attestation = _require_mapping(attestation, "attestation")
    _require_exact_keys(
        attestation,
        {
            "schema_version",
            "manifest_sha256",
            "commit",
            "status",
            "workflow_run_id",
            "completed_at",
            "images",
        },
        "attestation",
    )
    if attestation["schema_version"] != ATTESTATION_SCHEMA_VERSION:
        raise ManifestError("attestation schema version is invalid")
    commit = _validate_commit(attestation["commit"])
    if commit != expected_commit or commit != manifest["commit"]:
        raise ManifestError("attestation commit does not match manifest")
    digest = "sha256:" + hashlib.sha256(manifest_raw).hexdigest()
    if attestation["manifest_sha256"] != digest:
        raise ManifestError("attestation manifest SHA-256 does not match")
    if attestation["status"] != "completed":
        raise ManifestError("attestation status must be completed")
    workflow_run_id = _validate_workflow_run_id(attestation["workflow_run_id"])
    completed_at = _validate_completed_at(attestation["completed_at"])
    image_records = _require_mapping(attestation["images"], "attestation images")
    _require_exact_keys(image_records, set(COMPONENTS), "attestation images")
    refs: dict[str, str] = {}
    for component in COMPONENTS:
        image = _require_mapping(image_records[component], f"{component} attestation")
        _require_exact_keys(image, {"source", "destination", "digest"}, f"{component} attestation")
        manifest_image = _require_mapping(
            _require_mapping(manifest["images"], "manifest images")[component],
            f"{component} image",
        )
        component_digest = _validate_digest(manifest_image["digest"], component)
        if image["source"] != _ref("tcr", component, commit, component_digest):
            raise ManifestError(f"{component} attestation source does not match manifest")
        if image["digest"] != component_digest:
            raise ManifestError(f"{component} attestation digest does not match manifest")
        destination = image["destination"]
        if not isinstance(destination, str):
            raise ManifestError(f"{component} attestation destination is invalid")
        refs[component] = destination
    refs = _validate_ghcr_refs(manifest, refs)
    canonical = create_mirror_attestation(
        manifest_raw, refs, workflow_run_id, completed_at
    )
    if dict(attestation) != canonical:
        raise ManifestError("attestation contains unexpected or divergent identity fields")
    return canonical


def emit_release_env(
    manifest: Mapping[str, object],
    registry: str,
    attestation: Mapping[str, object] | None = None,
) -> tuple[str, str, str]:
    """Return the release commit and selected immutable image references as env lines."""
    manifest = _require_mapping(manifest, "manifest")
    commit = _validate_commit(manifest.get("commit"))
    manifest_raw = canonical_json(manifest)
    verified_manifest = verify_release_manifest_bytes(manifest_raw, commit)
    if registry not in REPOSITORIES:
        raise ManifestError("registry must be tcr or ghcr")
    images = _require_mapping(verified_manifest["images"], "manifest images")

    if registry == "ghcr":
        ghcr_records = {
            component: _require_mapping(
                _require_mapping(images[component], f"{component} image")["registries"],
                f"{component} registries",
            )["ghcr"]
            for component in COMPONENTS
        }
        if not all(
            _require_mapping(ghcr_records[component], f"{component} GHCR record")["status"]
            == "published"
            for component in COMPONENTS
        ):
            if attestation is None:
                raise ManifestError("GHCR emission requires a matching attestation")
            try:
                verified_attestation = verify_mirror_attestation(
                    manifest_raw, attestation, commit
                )
            except ManifestError as exc:
                raise ManifestError(
                    "GHCR emission requires a matching attestation"
                ) from exc
            source_images = _require_mapping(
                verified_attestation["images"], "attestation images"
            )
            refs = {
                component: _require_mapping(
                    source_images[component], f"{component} attestation"
                )["destination"]
                for component in COMPONENTS
            }
        else:
            refs = {
                component: _require_mapping(
                    ghcr_records[component], f"{component} GHCR record"
                )["ref"]
                for component in COMPONENTS
            }
    else:
        refs = {
            component: _require_mapping(
                _require_mapping(images[component], f"{component} image")["registries"],
                f"{component} registries",
            )["tcr"]
            for component in COMPONENTS
        }
        refs = {
            component: _require_mapping(refs[component], f"{component} TCR record")[
                "ref"
            ]
            for component in COMPONENTS
        }

    if not all(isinstance(refs[component], str) for component in COMPONENTS):
        raise ManifestError("selected image reference is invalid")
    return (
        f"RELEASE_COMMIT={commit}",
        f"BACKEND_IMAGE={refs['backend']}",
        f"FRONTEND_IMAGE={refs['frontend']}",
    )
