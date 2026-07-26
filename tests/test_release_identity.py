from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "bin"))

from release_identity import (  # noqa: E402
    ManifestError,
    canonical_json,
    create_mirror_attestation,
    create_release_manifest,
    emit_release_env,
    verify_mirror_attestation,
    verify_release_manifest_bytes,
)


COMMIT = "abcdef0123456789abcdef0123456789abcdef01"
BACKEND_DIGEST = "sha256:" + "a" * 64
FRONTEND_DIGEST = "sha256:" + "b" * 64


def canonical_deferred_manifest() -> dict[str, object]:
    return create_release_manifest(
        COMMIT,
        {"backend": BACKEND_DIGEST, "frontend": FRONTEND_DIGEST},
        {
            "backend": "published",
            "frontend": "deferred_after_5_network_failures",
        },
    )


def canonical_deferred_manifest_bytes() -> bytes:
    return canonical_json(canonical_deferred_manifest())


def test_release_v2_records_mandatory_tcr_and_deferred_ghcr() -> None:
    payload = canonical_deferred_manifest()

    assert payload["schema_version"] == "1999wiki.release/v2"
    assert payload["primary_registry"] == "tcr"
    assert payload["release_state"] == "ready_with_deferred_ghcr"
    assert (
        payload["images"]["backend"]["registries"]["tcr"]["ref"]
        == "ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-backend:sha-abcdef0@" + BACKEND_DIGEST
    )
    assert payload["images"]["frontend"]["registries"]["ghcr"] == {
        "status": "deferred_after_5_network_failures",
        "tag": "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0",
        "ref": None,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "1999wiki.release/v1"),
        ("commit", "ABCDEF0123456789abcdef0123456789abcdef01"),
        ("release_tag", "sha-deadbee"),
        ("primary_registry", "ghcr"),
        ("release_state", "ready"),
    ],
)
def test_manifest_verification_rejects_wrong_top_level_values(
    field: str, value: str
) -> None:
    payload = canonical_deferred_manifest()
    payload[field] = value
    with pytest.raises(ManifestError):
        verify_release_manifest_bytes(canonical_json(payload), COMMIT)


def test_manifest_verification_rejects_extra_and_missing_fields() -> None:
    extra = canonical_deferred_manifest()
    extra["unexpected"] = "field"
    with pytest.raises(ManifestError):
        verify_release_manifest_bytes(canonical_json(extra), COMMIT)

    missing = canonical_deferred_manifest()
    del missing["images"]
    with pytest.raises(ManifestError):
        verify_release_manifest_bytes(canonical_json(missing), COMMIT)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["images"]["backend"]["registries"]["tcr"].update(
            status="deferred_after_5_network_failures"
        ),
        lambda payload: payload["images"]["backend"]["registries"]["tcr"].update(
            tag="ccr.ccs.tencentyun.com/wrong/1999wiki-backend:sha-abcdef0"
        ),
        lambda payload: payload["images"]["backend"].update(
            digest=FRONTEND_DIGEST
        ),
        lambda payload: payload["images"]["backend"]["registries"]["ghcr"].update(
            ref=None
        ),
        lambda payload: payload["images"]["frontend"]["registries"]["ghcr"].update(
            ref=(
                "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@"
                + FRONTEND_DIGEST
            )
        ),
        lambda payload: payload.update(release_state="fully_mirrored"),
    ],
)
def test_manifest_verification_rejects_divergent_identity_records(mutate) -> None:
    payload = copy.deepcopy(canonical_deferred_manifest())
    mutate(payload)
    with pytest.raises(ManifestError):
        verify_release_manifest_bytes(canonical_json(payload), COMMIT)


def test_manifest_verification_requires_exact_canonical_bytes() -> None:
    raw = canonical_deferred_manifest_bytes()
    assert raw.endswith(b"\n")
    with pytest.raises(ManifestError):
        verify_release_manifest_bytes(raw.rstrip(b"\n"), COMMIT)
    assert verify_release_manifest_bytes(raw, COMMIT) == canonical_deferred_manifest()


def completed_attestation(manifest_raw: bytes) -> dict[str, object]:
    return create_mirror_attestation(
        manifest_raw,
        {
            "backend": (
                "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@" + BACKEND_DIGEST
            ),
            "frontend": (
                "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@"
                + FRONTEND_DIGEST
            ),
        },
        workflow_run_id="123456789",
        completed_at="2026-07-26T12:00:00Z",
    )


def test_deferred_ghcr_requires_matching_complete_attestation() -> None:
    manifest_raw = canonical_deferred_manifest_bytes()
    with pytest.raises(ManifestError, match="attestation"):
        emit_release_env(
            verify_release_manifest_bytes(manifest_raw, COMMIT), "ghcr"
        )

    verified = verify_mirror_attestation(
        manifest_raw, completed_attestation(manifest_raw), COMMIT
    )
    lines = emit_release_env(
        verify_release_manifest_bytes(manifest_raw, COMMIT), "ghcr", verified
    )
    assert lines[1].startswith("BACKEND_IMAGE=ghcr.io/")
    assert lines[2].startswith("FRONTEND_IMAGE=ghcr.io/")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda attestation: attestation.update(manifest_sha256="sha256:" + "0" * 64),
        lambda attestation: attestation.update(commit="0" * 40),
        lambda attestation: attestation["images"].pop("frontend"),
        lambda attestation: attestation["images"].update(unexpected={}),
        lambda attestation: attestation["images"]["backend"].update(
            destination="ghcr.io/wrong/1999wiki-backend:sha-abcdef0@" + BACKEND_DIGEST
        ),
        lambda attestation: attestation["images"]["backend"].update(
            digest=FRONTEND_DIGEST
        ),
        lambda attestation: attestation.update(status="pending"),
        lambda attestation: attestation.update(workflow_run_id="12a"),
        lambda attestation: attestation.update(completed_at="2026-07-26T12:00:00+00:00"),
        lambda attestation: attestation.update(unexpected="field"),
    ],
)
def test_attestation_verification_rejects_invalid_identity(mutate) -> None:
    raw = canonical_deferred_manifest_bytes()
    attestation = copy.deepcopy(completed_attestation(raw))
    mutate(attestation)
    with pytest.raises(ManifestError):
        verify_mirror_attestation(raw, attestation, COMMIT)


def test_tcr_emission_never_needs_attestation() -> None:
    manifest = verify_release_manifest_bytes(canonical_deferred_manifest_bytes(), COMMIT)
    lines = emit_release_env(manifest, "tcr")
    assert lines == (
        f"RELEASE_COMMIT={COMMIT}",
        "BACKEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-backend:sha-abcdef0@" + BACKEND_DIGEST,
        "FRONTEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-frontend:sha-abcdef0@" + FRONTEND_DIGEST,
    )


def test_fully_mirrored_manifest_emits_ghcr_without_attestation() -> None:
    manifest = create_release_manifest(
        COMMIT,
        {"backend": BACKEND_DIGEST, "frontend": FRONTEND_DIGEST},
        {"backend": "published", "frontend": "published"},
    )
    assert manifest["release_state"] == "ready"
    assert (
        verify_release_manifest_bytes(canonical_json(manifest), COMMIT)
        == manifest
    )
    noncanonical = copy.deepcopy(manifest)
    noncanonical["release_state"] = "fully_mirrored"
    with pytest.raises(ManifestError):
        verify_release_manifest_bytes(canonical_json(noncanonical), COMMIT)

    lines = emit_release_env(manifest, "ghcr")
    assert lines[1] == (
        "BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@"
        + BACKEND_DIGEST
    )
    assert lines[2] == (
        "FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@"
        + FRONTEND_DIGEST
    )


def test_attestation_hash_binds_the_exact_manifest_bytes() -> None:
    raw = canonical_deferred_manifest_bytes()
    attestation = completed_attestation(raw)
    assert attestation["manifest_sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda attestation: attestation.pop("status"),
        lambda attestation: attestation["images"]["backend"].pop("source"),
    ],
)
def test_attestation_verification_rejects_independent_missing_required_fields(
    mutate,
) -> None:
    raw = canonical_deferred_manifest_bytes()
    attestation = copy.deepcopy(completed_attestation(raw))
    mutate(attestation)
    with pytest.raises(ManifestError):
        verify_mirror_attestation(raw, attestation, COMMIT)
