from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import sys
import tarfile
from collections import defaultdict, deque
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
DEPLOY_BIN = ROOT / "deploy" / "bin"
for directory in (SCRIPTS, DEPLOY_BIN):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import publish_registries  # noqa: E402
from publish_registries import PublicationError, main, publish_release  # noqa: E402
from registry_transport import (  # noqa: E402
    Credential,
    ProbeState,
    RegistryFailure,
    _TransientRegistryFailure,
)


COMMIT = "abcdef0123456789abcdef0123456789abcdef01"
WORKFLOW_RUN_ID = "123456789"
OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
DOCKER_MANIFEST_MEDIA_TYPE = (
    "application/vnd.docker.distribution.manifest.v2+json"
)
OCI_CONFIG_MEDIA_TYPE = "application/vnd.oci.image.config.v1+json"
OCI_LAYER_MEDIA_TYPE = "application/vnd.oci.image.layer.v1.tar"
DOCKER_CONFIG_MEDIA_TYPE = "application/vnd.docker.container.image.v1+json"
DOCKER_LAYER_MEDIA_TYPE = (
    "application/vnd.docker.image.rootfs.diff.tar"
)


def _minimal_layer_blob() -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as layer:
        content = b"minimal OCI layer\n"
        member = tarfile.TarInfo("fixture.txt")
        member.size = len(content)
        layer.addfile(member, io.BytesIO(content))
    return output.getvalue()


LAYER_BLOB = _minimal_layer_blob()
LAYER_DIGEST = "sha256:" + hashlib.sha256(LAYER_BLOB).hexdigest()
CONFIG_BLOB = json.dumps(
    {
        "architecture": "amd64",
        "config": {},
        "os": "linux",
        "rootfs": {
            "type": "layers",
            "diff_ids": [LAYER_DIGEST],
        },
    },
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8")
CONFIG_DIGEST = "sha256:" + hashlib.sha256(CONFIG_BLOB).hexdigest()


def _manifest_bytes(
    component: str,
    *,
    schema_version: int = 2,
    media_type: str = OCI_MANIFEST_MEDIA_TYPE,
    config: object | None = None,
    layers: object | None = None,
    padding: int = 0,
) -> bytes:
    docker = media_type == DOCKER_MANIFEST_MEDIA_TYPE
    payload = {
        "schemaVersion": schema_version,
        "mediaType": media_type,
        "config": config
        if config is not None
        else {
            "mediaType": (
                DOCKER_CONFIG_MEDIA_TYPE if docker else OCI_CONFIG_MEDIA_TYPE
            ),
            "digest": CONFIG_DIGEST,
            "size": len(CONFIG_BLOB),
        },
        "layers": layers
        if layers is not None
        else [
            {
                "mediaType": (
                    DOCKER_LAYER_MEDIA_TYPE if docker else OCI_LAYER_MEDIA_TYPE
                ),
                "digest": LAYER_DIGEST,
                "size": len(LAYER_BLOB),
            }
        ],
        "annotations": {
            "org.opencontainers.image.title": component,
            "test.padding": "x" * padding,
        },
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


BACKEND_MANIFEST = _manifest_bytes("backend")
FRONTEND_MANIFEST = _manifest_bytes("frontend")
BACKEND_DIGEST = "sha256:" + hashlib.sha256(BACKEND_MANIFEST).hexdigest()
FRONTEND_DIGEST = "sha256:" + hashlib.sha256(FRONTEND_MANIFEST).hexdigest()
DIGESTS = {"backend": BACKEND_DIGEST, "frontend": FRONTEND_DIGEST}
TCR_REGISTRY = "ccr.ccs.tencentyun.com"
TCR_NAMESPACE = "1999wiki_code"
TCR_TAGS = {
    "backend": (
        "ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-backend:sha-abcdef0"
    ),
    "frontend": (
        "ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-frontend:sha-abcdef0"
    ),
}
GHCR_TAGS = {
    "backend": "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0",
    "frontend": "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0",
}
TCR_REFS = {
    component: f"{TCR_TAGS[component]}@{DIGESTS[component]}"
    for component in ("backend", "frontend")
}
CREDENTIALS = {
    "tcr": Credential("tcr-user", "tcr-secret"),
    "ghcr": Credential("ghcr-user", "ghcr-secret"),
}


def _add_tar_member(
    archive: tarfile.TarFile,
    name: str,
    content: bytes,
    *,
    member_type: bytes = tarfile.REGTYPE,
    linkname: str = "",
) -> None:
    info = tarfile.TarInfo(name)
    info.type = member_type
    info.linkname = linkname
    if info.isreg():
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    else:
        archive.addfile(info)


def _oci_archive(
    path: Path,
    digest: str,
    manifest: bytes,
    *,
    descriptor_media_type: str = OCI_MANIFEST_MEDIA_TYPE,
    descriptor_size: int | None = None,
    index_schema_version: int = 2,
    index_padding: int = 0,
    manifest_member_type: bytes = tarfile.REGTYPE,
    config_blob: bytes = CONFIG_BLOB,
    layer_blob: bytes = LAYER_BLOB,
) -> Path:
    index = json.dumps(
        {
            "schemaVersion": index_schema_version,
            "manifests": [
                {
                    "mediaType": descriptor_media_type,
                    "digest": digest,
                    "size": (
                        len(manifest)
                        if descriptor_size is None
                        else descriptor_size
                    ),
                }
            ],
            "padding": "x" * index_padding,
        }
    ).encode("utf-8")
    with tarfile.open(path, "w") as archive:
        _add_tar_member(
            archive,
            "oci-layout",
            b'{"imageLayoutVersion":"1.0.0"}',
        )
        _add_tar_member(archive, "index.json", index)
        blob_name = f"blobs/sha256/{digest.removeprefix('sha256:')}"
        if manifest_member_type in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
            _add_tar_member(archive, "manifest-target", manifest)
            _add_tar_member(
                archive,
                blob_name,
                b"",
                member_type=manifest_member_type,
                linkname="manifest-target",
            )
        else:
            _add_tar_member(
                archive,
                blob_name,
                manifest,
                member_type=manifest_member_type,
            )
        _add_tar_member(
            archive,
            f"blobs/sha256/{CONFIG_DIGEST.removeprefix('sha256:')}",
            config_blob,
        )
        _add_tar_member(
            archive,
            f"blobs/sha256/{LAYER_DIGEST.removeprefix('sha256:')}",
            layer_blob,
        )
    return path


@pytest.fixture
def archives(tmp_path: Path) -> dict[str, Path]:
    return {
        "backend": _oci_archive(
            tmp_path / "backend.oci", BACKEND_DIGEST, BACKEND_MANIFEST
        ),
        "frontend": _oci_archive(
            tmp_path / "frontend.oci", FRONTEND_DIGEST, FRONTEND_MANIFEST
        ),
    }


class StatefulTransport:
    """Registry-free transport whose state models preflight, copy, and verify."""

    def __init__(
        self,
        scripted: Mapping[str, list[object]] | None = None,
    ) -> None:
        self.credential = CREDENTIALS["tcr"]
        self.jitter = lambda: 0.0
        self.calls: list[str] = []
        self.login_credentials: list[tuple[str, str]] = []
        self.budget_ids: dict[str, list[int]] = defaultdict(list)
        self.copy_attempted: set[tuple[str, str]] = set()
        self.scripted = defaultdict(deque)
        for phase, outcomes in (scripted or {}).items():
            self.scripted[phase].extend(outcomes)

    @staticmethod
    def _registry(value: str) -> str:
        return "tcr" if value == TCR_REGISTRY or value.startswith(TCR_REGISTRY + "/") else "ghcr"

    @staticmethod
    def _component(target: str) -> str:
        return "frontend" if "frontend" in target else "backend"

    def _result(self, phase: str, budget, default: object) -> object:
        outcome = self.scripted[phase].popleft() if self.scripted[phase] else default
        if outcome == "transient":
            budget.consume()
            raise _TransientRegistryFailure(phase, budget.failures)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def login(self, registry: str, budget) -> None:
        budget.ensure_available()
        alias = self._registry(registry)
        self.budget_ids[alias].append(id(budget))
        phase = f"login:{alias}"
        self.calls.append(phase)
        self.login_credentials.append((alias, self.credential.username))
        self._result(phase, budget, None)

    def probe(self, target: str, expected_digest: str, budget) -> ProbeState:
        budget.ensure_available()
        alias = self._registry(target)
        self.budget_ids[alias].append(id(budget))
        component = self._component(target)
        copied = (alias, component) in self.copy_attempted
        operation = "verify" if copied else "probe"
        phase = f"{operation}:{alias}:{component}"
        self.calls.append(phase)
        default = ProbeState.PRESENT_EXPECTED if copied else ProbeState.ABSENT
        return self._result(phase, budget, default)  # type: ignore[return-value]

    def copy(self, source: str, target: str, budget) -> None:
        budget.ensure_available()
        alias = self._registry(target)
        self.budget_ids[alias].append(id(budget))
        component = self._component(target)
        phase = f"copy:{alias}:{component}"
        self.calls.append(phase)
        self.copy_attempted.add((alias, component))
        self._result(phase, budget, None)


def _publish(
    archives: Mapping[str, Path],
    transport: StatefulTransport | None = None,
) -> tuple[dict[str, object], StatefulTransport]:
    fake = transport or StatefulTransport()
    manifest = publish_release(
        COMMIT,
        archives,
        fake,  # type: ignore[arg-type]
        CREDENTIALS,
        WORKFLOW_RUN_ID,
    )
    return manifest, fake


def test_success_uses_exact_preflight_then_tcr_then_ghcr_order(
    archives: Mapping[str, Path],
) -> None:
    manifest, transport = _publish(archives)

    assert transport.calls == [
        "login:tcr",
        "probe:tcr:backend",
        "probe:tcr:frontend",
        "login:ghcr",
        "probe:ghcr:backend",
        "probe:ghcr:frontend",
        "copy:tcr:backend",
        "verify:tcr:backend",
        "copy:tcr:frontend",
        "verify:tcr:frontend",
        "copy:ghcr:backend",
        "verify:ghcr:backend",
        "copy:ghcr:frontend",
        "verify:ghcr:frontend",
    ]
    assert transport.login_credentials == [
        ("tcr", "tcr-user"),
        ("ghcr", "ghcr-user"),
    ]
    assert len(set(transport.budget_ids["tcr"])) == 1
    assert len(set(transport.budget_ids["ghcr"])) == 1
    assert transport.budget_ids["tcr"][0] != transport.budget_ids["ghcr"][0]
    assert manifest["release_state"] == "ready"


@pytest.mark.parametrize(
    ("component", "digest"),
    [
        ("backend", BACKEND_DIGEST),
        ("frontend", FRONTEND_DIGEST),
    ],
)
def test_each_archive_descriptor_must_match_its_referenced_blob_before_login(
    tmp_path: Path,
    archives: Mapping[str, Path],
    component: str,
    digest: str,
) -> None:
    candidates = dict(archives)
    candidates[component] = _oci_archive(
        tmp_path / f"corrupt-{component}.oci",
        digest,
        b"tampered-manifest",
    )
    transport = StatefulTransport()

    with pytest.raises(ValueError, match="digest"):
        _publish(candidates, transport)

    assert transport.calls == []


@pytest.mark.parametrize(
    "case",
    [
        "index_schema",
        "descriptor_media_type",
        "descriptor_size",
        "manifest_non_json",
        "manifest_schema",
        "manifest_media_type",
        "config_structure",
        "layers_structure",
        "unsafe_config_digest",
        "referenced_blob_size",
        "symlink_manifest",
        "hardlink_manifest",
        "non_regular_manifest",
        "oversized_index",
        "oversized_manifest",
    ],
)
def test_oci_preflight_rejects_invalid_or_unbounded_archives_before_login(
    tmp_path: Path,
    archives: Mapping[str, Path],
    case: str,
) -> None:
    manifest = BACKEND_MANIFEST
    options: dict[str, object] = {}
    if case == "index_schema":
        options["index_schema_version"] = 1
    elif case == "descriptor_media_type":
        options["descriptor_media_type"] = (
            "application/vnd.oci.image.index.v1+json"
        )
    elif case == "descriptor_size":
        options["descriptor_size"] = len(manifest) + 1
    elif case == "manifest_non_json":
        manifest = b"not-json"
    elif case == "manifest_schema":
        manifest = _manifest_bytes("backend", schema_version=1)
    elif case == "manifest_media_type":
        manifest = _manifest_bytes(
            "backend",
            media_type=DOCKER_MANIFEST_MEDIA_TYPE,
        )
    elif case == "config_structure":
        manifest = _manifest_bytes("backend", config=[])
    elif case == "layers_structure":
        manifest = _manifest_bytes("backend", layers={})
    elif case == "unsafe_config_digest":
        manifest = _manifest_bytes(
            "backend",
            config={
                "mediaType": OCI_CONFIG_MEDIA_TYPE,
                "digest": "sha256:../../outside",
                "size": len(CONFIG_BLOB),
            },
        )
    elif case == "referenced_blob_size":
        manifest = _manifest_bytes(
            "backend",
            config={
                "mediaType": OCI_CONFIG_MEDIA_TYPE,
                "digest": CONFIG_DIGEST,
                "size": len(CONFIG_BLOB) + 1,
            },
        )
    elif case == "symlink_manifest":
        options["manifest_member_type"] = tarfile.SYMTYPE
    elif case == "hardlink_manifest":
        options["manifest_member_type"] = tarfile.LNKTYPE
    elif case == "non_regular_manifest":
        options["manifest_member_type"] = tarfile.FIFOTYPE
    elif case == "oversized_index":
        options["index_padding"] = 300_000
    elif case == "oversized_manifest":
        manifest = _manifest_bytes("backend", padding=4 * 1024 * 1024)
    digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
    invalid = _oci_archive(
        tmp_path / f"{case}.oci",
        digest,
        manifest,
        **options,  # type: ignore[arg-type]
    )
    candidates = dict(archives)
    candidates["backend"] = invalid
    transport = StatefulTransport()

    with pytest.raises(ValueError):
        _publish(candidates, transport)

    assert transport.calls == []


def test_oci_preflight_accepts_the_allowed_docker_image_manifest_type(
    tmp_path: Path,
    archives: Mapping[str, Path],
) -> None:
    manifest = _manifest_bytes(
        "backend",
        media_type=DOCKER_MANIFEST_MEDIA_TYPE,
    )
    digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
    docker_archive = _oci_archive(
        tmp_path / "docker-manifest.oci",
        digest,
        manifest,
        descriptor_media_type=DOCKER_MANIFEST_MEDIA_TYPE,
    )
    candidates = dict(archives)
    candidates["backend"] = docker_archive

    published, transport = _publish(candidates)

    assert published["release_state"] == "ready"
    assert transport.calls[0] == "login:tcr"


@pytest.mark.parametrize(
    ("blob_name", "replacement"),
    [
        ("config_blob", b"X" + CONFIG_BLOB[1:]),
        ("layer_blob", b"X" + LAYER_BLOB[1:]),
    ],
    ids=["config", "layer"],
)
def test_oci_preflight_hashes_each_referenced_blob_before_login(
    tmp_path: Path,
    archives: Mapping[str, Path],
    blob_name: str,
    replacement: bytes,
) -> None:
    tampered = _oci_archive(
        tmp_path / f"tampered-{blob_name}.oci",
        BACKEND_DIGEST,
        BACKEND_MANIFEST,
        **{blob_name: replacement},
    )
    candidates = dict(archives)
    candidates["backend"] = tampered
    transport = StatefulTransport()

    with pytest.raises(ValueError, match="digest"):
        _publish(candidates, transport)

    assert transport.calls == []


@pytest.mark.parametrize(
    "present",
    [ProbeState.PRESENT_EXPECTED, ProbeState.PRESENT_CONFLICT],
)
def test_any_existing_tcr_tag_is_a_fatal_hard_gate(
    archives: Mapping[str, Path],
    present: ProbeState,
) -> None:
    transport = StatefulTransport({"probe:tcr:backend": [present]})

    with pytest.raises(PublicationError) as caught:
        _publish(archives, transport)

    assert caught.value.phase == "tcr_backend_probe"
    assert caught.value.code == "tag_conflict"
    assert caught.value.mutated is False
    assert transport.copy_attempted == set()


def test_tcr_auth_failure_is_fatal_before_any_mutation(
    archives: Mapping[str, Path],
) -> None:
    transport = StatefulTransport(
        {
            "login:tcr": [
                RegistryFailure("login", TCR_REGISTRY, "authentication_failed")
            ]
        }
    )

    with pytest.raises(PublicationError) as caught:
        _publish(archives, transport)

    assert caught.value.phase == "tcr_login"
    assert caught.value.code == "authentication_failed"
    assert caught.value.mutated is False
    assert transport.copy_attempted == set()


def test_first_tcr_transient_is_fail_fast_fatal_instead_of_deployable(
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publish_registries.time, "sleep", lambda _: None)
    transport = StatefulTransport({"login:tcr": ["transient"]})

    with pytest.raises(PublicationError) as caught:
        _publish(archives, transport)

    assert caught.value.phase == "tcr_login"
    assert caught.value.code == "network_failure"
    assert caught.value.mutated is False
    assert transport.copy_attempted == set()


@pytest.mark.parametrize(
    ("scripted", "phase", "code", "verified_tcr"),
    [
        (
            {"verify:tcr:backend": [ProbeState.ABSENT]},
            "tcr_backend_verify",
            "manifest_missing_after_copy",
            {},
        ),
        (
            {"verify:tcr:backend": [ProbeState.PRESENT_CONFLICT]},
            "tcr_backend_verify",
            "digest_mismatch",
            {},
        ),
        (
            {
                "copy:tcr:frontend": [
                    RegistryFailure("copy", TCR_REGISTRY, "fatal_registry_failure")
                ]
            },
            "tcr_frontend_copy",
            "fatal_registry_failure",
            {"backend": TCR_REFS["backend"]},
        ),
    ],
)
def test_tcr_partial_copy_or_mismatch_is_fatal_and_never_claims_unverified_refs(
    archives: Mapping[str, Path],
    scripted: Mapping[str, list[object]],
    phase: str,
    code: str,
    verified_tcr: Mapping[str, str],
) -> None:
    transport = StatefulTransport(scripted)

    with pytest.raises(PublicationError) as caught:
        _publish(archives, transport)

    assert caught.value.phase == phase
    assert caught.value.code == code
    assert caught.value.mutated is True
    assert caught.value.verified_tcr == verified_tcr


def test_fifth_ghcr_preflight_transient_defers_both_components_then_publishes_tcr(
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publish_registries.time, "sleep", lambda _: None)
    transport = StatefulTransport({"login:ghcr": ["transient"] * 5})

    manifest, transport = _publish(archives, transport)

    images = manifest["images"]
    assert manifest["release_state"] == "ready_with_deferred_ghcr"
    assert images["backend"]["registries"]["ghcr"]["status"] == (
        "deferred_after_5_network_failures"
    )
    assert images["frontend"]["registries"]["ghcr"]["status"] == (
        "deferred_after_5_network_failures"
    )
    assert len(set(transport.budget_ids["ghcr"])) == 1
    assert len(set(transport.budget_ids["tcr"])) == 1
    assert transport.budget_ids["ghcr"][0] != transport.budget_ids["tcr"][0]
    assert transport.calls[-4:] == [
        "copy:tcr:backend",
        "verify:tcr:backend",
        "copy:tcr:frontend",
        "verify:tcr:frontend",
    ]
    assert not any(call.startswith("copy:ghcr") for call in transport.calls)


def test_shared_fifth_transient_can_defer_only_frontend_after_backend_publishes(
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publish_registries.time, "sleep", lambda _: None)
    transport = StatefulTransport(
        {
            "probe:ghcr:backend": ["transient"] * 4 + [ProbeState.ABSENT],
            "copy:ghcr:frontend": ["transient"],
        }
    )

    manifest, _ = _publish(archives, transport)

    images = manifest["images"]
    assert images["backend"]["registries"]["ghcr"]["status"] == "published"
    assert images["frontend"]["registries"]["ghcr"]["status"] == (
        "deferred_after_5_network_failures"
    )
    assert manifest["release_state"] == "ready_with_deferred_ghcr"
    assert len(set(transport.budget_ids["ghcr"])) == 1
    assert len(set(transport.budget_ids["tcr"])) == 1
    assert transport.budget_ids["ghcr"][0] != transport.budget_ids["tcr"][0]


def test_transient_ghcr_copy_reconciles_before_considering_another_copy(
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publish_registries.time, "sleep", lambda _: None)
    transport = StatefulTransport(
        {
            "copy:ghcr:backend": ["transient"],
            "verify:ghcr:backend": [ProbeState.PRESENT_EXPECTED],
        }
    )

    manifest, _ = _publish(archives, transport)

    assert manifest["images"]["backend"]["registries"]["ghcr"]["status"] == (
        "published"
    )
    assert transport.calls.count("copy:ghcr:backend") == 1
    backend_copy = transport.calls.index("copy:ghcr:backend")
    assert transport.calls[backend_copy + 1] == "verify:ghcr:backend"


@pytest.mark.parametrize(
    ("phase", "outcome", "expected_phase", "expected_code"),
    [
        (
            "login:ghcr",
            RegistryFailure("login", "ghcr.io", "authentication_failed"),
            "ghcr_login",
            "authentication_failed",
        ),
        (
            "probe:ghcr:backend",
            RegistryFailure("probe", "ghcr.io", "authentication_failed"),
            "ghcr_backend_probe",
            "authentication_failed",
        ),
        (
            "probe:ghcr:backend",
            RegistryFailure("probe", "ghcr.io", "fatal_registry_failure"),
            "ghcr_backend_probe",
            "fatal_registry_failure",
        ),
        (
            "probe:ghcr:backend",
            ProbeState.PRESENT_CONFLICT,
            "ghcr_backend_probe",
            "tag_conflict",
        ),
    ],
)
def test_ghcr_auth_permission_429_or_tag_conflict_is_fatal_before_tcr_mutation(
    archives: Mapping[str, Path],
    phase: str,
    outcome: object,
    expected_phase: str,
    expected_code: str,
) -> None:
    transport = StatefulTransport({phase: [outcome]})

    with pytest.raises(PublicationError) as caught:
        _publish(archives, transport)

    assert caught.value.phase == expected_phase
    assert caught.value.code == expected_code
    assert caught.value.mutated is False
    assert transport.copy_attempted == set()


def test_even_digest_identical_existing_ghcr_tag_is_a_conflict(
    archives: Mapping[str, Path],
) -> None:
    transport = StatefulTransport(
        {"probe:ghcr:backend": [ProbeState.PRESENT_EXPECTED]}
    )

    with pytest.raises(PublicationError) as caught:
        _publish(archives, transport)

    assert caught.value.phase == "ghcr_backend_probe"
    assert caught.value.code == "tag_conflict"
    assert transport.copy_attempted == set()


def _cli_args(tmp_path: Path, archives: Mapping[str, Path]) -> list[str]:
    return [
        "--commit",
        COMMIT,
        "--backend-archive",
        str(archives["backend"]),
        "--frontend-archive",
        str(archives["frontend"]),
        "--authfile",
        str(tmp_path / "auth.json"),
        "--manifest-output",
        str(tmp_path / "release-manifest.json"),
        "--failure-output",
        str(tmp_path / "publication-failure.json"),
        "--workflow-run-id",
        WORKFLOW_RUN_ID,
    ]


def _override_arg(args: list[str], option: str, value: Path) -> list[str]:
    overridden = list(args)
    overridden[overridden.index(option) + 1] = str(value)
    return overridden


def _set_cli_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "TCR_USERNAME",
        "TCR_PASSWORD",
        "GHCR_USERNAME",
        "GHCR_PASSWORD",
        "TCR_REGISTRY",
        "TCR_NAMESPACE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TCR_USERNAME", "tcr-user")
    monkeypatch.setenv("TCR_PASSWORD", "tcr-secret")
    monkeypatch.setenv("GHCR_USERNAME", "ghcr-user")
    monkeypatch.setenv("GHCR_PASSWORD", "ghcr-secret")
    monkeypatch.setenv("TCR_REGISTRY", TCR_REGISTRY)
    monkeypatch.setenv("TCR_NAMESPACE", TCR_NAMESPACE)


@pytest.mark.parametrize(
    "collision",
    [
        "manifest_is_backend_alias",
        "authfile_is_backend",
        "backend_is_frontend",
        "success_is_failure",
    ],
)
def test_cli_rejects_colliding_paths_before_io_and_preserves_every_file(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    collision: str,
) -> None:
    _set_cli_environment(monkeypatch)
    args = _cli_args(tmp_path, archives)
    shared_output = tmp_path / "shared-output.json"
    shared_output.write_bytes(b"preexisting-output")
    if collision == "manifest_is_backend_alias":
        (tmp_path / "nested").mkdir()
        args = _override_arg(
            args,
            "--manifest-output",
            tmp_path / "nested" / ".." / archives["backend"].name,
        )
    elif collision == "authfile_is_backend":
        args = _override_arg(args, "--authfile", archives["backend"])
    elif collision == "backend_is_frontend":
        args = _override_arg(args, "--frontend-archive", archives["backend"])
    else:
        args = _override_arg(args, "--manifest-output", shared_output)
        args = _override_arg(args, "--failure-output", shared_output)
    watched = {
        path: path.read_bytes()
        for path in {
            archives["backend"],
            archives["frontend"],
            shared_output,
        }
    }
    transport = StatefulTransport()
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )

    assert main(args) == 2

    assert transport.calls == []
    for path, contents in watched.items():
        assert path.is_file()
        assert path.read_bytes() == contents


def test_cli_rejects_hardlink_equivalent_paths_without_touching_the_archive(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    authfile_hardlink = tmp_path / "auth-hardlink.json"
    os.link(archives["backend"], authfile_hardlink)
    before = archives["backend"].read_bytes()
    transport = StatefulTransport()
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )
    args = _override_arg(
        _cli_args(tmp_path, archives),
        "--authfile",
        authfile_hardlink,
    )

    assert main(args) == 2

    assert transport.calls == []
    assert archives["backend"].read_bytes() == before
    assert authfile_hardlink.is_file()
    assert authfile_hardlink.read_bytes() == before


def test_cli_writes_only_canonical_manifest_on_success_and_removes_authfile(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport()
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )
    args = _cli_args(tmp_path, archives)

    assert main(args) == 0

    manifest_path = tmp_path / "release-manifest.json"
    assert json.loads(manifest_path.read_bytes())["release_state"] == "ready"
    assert manifest_path.read_bytes().endswith(b"\n")
    assert not (tmp_path / "publication-failure.json").exists()
    assert not (tmp_path / "auth.json").exists()


def test_cli_fatal_mutation_writes_exact_sanitized_failure_and_no_manifest(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport(
        {
            "copy:ghcr:frontend": [
                RegistryFailure("copy", "ghcr.io", "digest_mismatch")
            ]
        }
    )
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )
    args = _cli_args(tmp_path, archives)

    assert main(args) == 1

    failure_path = tmp_path / "publication-failure.json"
    assert json.loads(failure_path.read_bytes()) == {
        "schema_version": "1999wiki.publication-failure/v1",
        "commit": COMMIT,
        "release_tag": "sha-abcdef0",
        "phase": "ghcr_frontend_copy",
        "code": "digest_mismatch",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "verified_tcr": {
            "backend": TCR_REFS["backend"],
            "frontend": TCR_REFS["frontend"],
        },
    }
    raw = failure_path.read_text(encoding="utf-8")
    for forbidden in (
        "stderr",
        "tcr-user",
        "tcr-secret",
        "ghcr-user",
        "ghcr-secret",
        str(tmp_path / "auth.json"),
        "TCR_PASSWORD",
        "GHCR_PASSWORD",
        "environment",
    ):
        assert forbidden not in raw
    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "auth.json").exists()


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (OSError("disk full at D:/secret/auth.json tcr-secret"), "local_io_failure"),
        (ValueError("invalid D:/secret/auth.json tcr-secret"), "local_validation_failure"),
        (RuntimeError("unknown D:/secret/auth.json tcr-secret"), "unexpected_local_failure"),
    ],
)
def test_cli_sanitizes_local_or_unknown_fatal_after_backend_was_verified(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_code: str,
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport({"copy:tcr:frontend": [error]})
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )

    try:
        result = main(_cli_args(tmp_path, archives))
    except Exception as exc:
        pytest.fail(f"local fatal escaped the CLI: {type(exc).__name__}")

    assert result == 1
    failure_path = tmp_path / "publication-failure.json"
    assert json.loads(failure_path.read_bytes()) == {
        "schema_version": "1999wiki.publication-failure/v1",
        "commit": COMMIT,
        "release_tag": "sha-abcdef0",
        "phase": "tcr_frontend_copy",
        "code": expected_code,
        "workflow_run_id": WORKFLOW_RUN_ID,
        "verified_tcr": {"backend": TCR_REFS["backend"]},
    }
    raw = failure_path.read_text(encoding="utf-8")
    for forbidden in ("disk full", "invalid D:/", "unknown D:/", "tcr-secret"):
        assert forbidden not in raw
    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "auth.json").exists()


def _secure_authfile_with_failing_cleanup(path: Path):
    @contextmanager
    def managed():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        try:
            yield path
        finally:
            path.unlink(missing_ok=True)
            raise OSError("cleanup-secret D:/secret/auth.json")

    return managed()


def test_authfile_cleanup_failure_does_not_mask_the_primary_publication_error(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport(
        {
            "copy:tcr:frontend": [
                RegistryFailure(
                    "copy",
                    TCR_REGISTRY,
                    "fatal_registry_failure",
                )
            ]
        }
    )
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )
    monkeypatch.setattr(
        publish_registries,
        "secure_authfile",
        _secure_authfile_with_failing_cleanup,
    )

    assert main(_cli_args(tmp_path, archives)) == 1

    failure_path = tmp_path / "publication-failure.json"
    assert json.loads(failure_path.read_bytes()) == {
        "schema_version": "1999wiki.publication-failure/v1",
        "commit": COMMIT,
        "release_tag": "sha-abcdef0",
        "phase": "tcr_frontend_copy",
        "code": "fatal_registry_failure",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "verified_tcr": {"backend": TCR_REFS["backend"]},
    }
    assert "cleanup-secret" not in failure_path.read_text(encoding="utf-8")
    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "auth.json").exists()


def test_authfile_cleanup_only_failure_after_mutation_has_stable_local_artifact(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport()
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )
    monkeypatch.setattr(
        publish_registries,
        "secure_authfile",
        _secure_authfile_with_failing_cleanup,
    )

    assert main(_cli_args(tmp_path, archives)) == 1

    failure_path = tmp_path / "publication-failure.json"
    failure = json.loads(failure_path.read_bytes())
    assert failure["phase"] == "authfile_cleanup"
    assert failure["code"] == "local_io_failure"
    assert failure["verified_tcr"] == TCR_REFS
    assert "cleanup-secret" not in failure_path.read_text(encoding="utf-8")
    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "auth.json").exists()


def test_cli_manifest_write_failure_after_all_mutations_writes_failure_artifact(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport()
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )
    original_write = publish_registries._write_canonical
    manifest_path = tmp_path / "release-manifest.json"

    def fail_manifest_write(path: Path, payload: Mapping[str, object]) -> None:
        if path == manifest_path:
            raise OSError("disk full D:/secret/auth.json ghcr-secret")
        original_write(path, payload)

    monkeypatch.setattr(
        publish_registries,
        "_write_canonical",
        fail_manifest_write,
    )

    try:
        result = main(_cli_args(tmp_path, archives))
    except Exception as exc:
        pytest.fail(f"manifest write fatal escaped the CLI: {type(exc).__name__}")

    assert result == 1
    assert not manifest_path.exists()
    failure_path = tmp_path / "publication-failure.json"
    assert json.loads(failure_path.read_bytes()) == {
        "schema_version": "1999wiki.publication-failure/v1",
        "commit": COMMIT,
        "release_tag": "sha-abcdef0",
        "phase": "manifest_write",
        "code": "local_io_failure",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "verified_tcr": TCR_REFS,
    }
    assert "disk full" not in failure_path.read_text(encoding="utf-8")
    assert "ghcr-secret" not in failure_path.read_text(encoding="utf-8")


def test_cli_failure_artifact_write_failure_returns_safely_without_false_output(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport(
        {"copy:tcr:frontend": [OSError("source-secret tcr-secret")]}
    )
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )

    def fail_artifact_write(path: Path, payload: Mapping[str, object]) -> None:
        raise OSError("failure-secret D:/secret/auth.json")

    monkeypatch.setattr(
        publish_registries,
        "_write_canonical",
        fail_artifact_write,
    )

    try:
        result = main(_cli_args(tmp_path, archives))
    except Exception as exc:
        pytest.fail(f"failure write fatal escaped the CLI: {type(exc).__name__}")

    assert result == 1
    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "publication-failure.json").exists()
    assert not (tmp_path / "auth.json").exists()
    captured = capsys.readouterr()
    assert "source-secret" not in captured.out + captured.err
    assert "failure-secret" not in captured.out + captured.err
    assert "tcr-secret" not in captured.out + captured.err


@pytest.mark.parametrize(
    ("scripted", "expected_verified"),
    [
        (
            {
                "copy:tcr:backend": [
                    RegistryFailure("copy", TCR_REGISTRY, "fatal_registry_failure")
                ]
            },
            {},
        ),
        (
            {
                "copy:tcr:frontend": [
                    RegistryFailure("copy", TCR_REGISTRY, "fatal_registry_failure")
                ]
            },
            {"backend": TCR_REFS["backend"]},
        ),
    ],
)
def test_cli_failure_lists_exactly_the_tcr_components_verified_before_failure(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    scripted: Mapping[str, list[object]],
    expected_verified: Mapping[str, str],
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport(scripted)
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )

    assert main(_cli_args(tmp_path, archives)) == 1

    failure = json.loads((tmp_path / "publication-failure.json").read_bytes())
    assert failure["verified_tcr"] == expected_verified
    assert not (tmp_path / "release-manifest.json").exists()


def test_cli_preflight_fatal_writes_neither_manifest_nor_failure(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    transport = StatefulTransport(
        {
            "login:ghcr": [
                RegistryFailure("login", "ghcr.io", "authentication_failed")
            ]
        }
    )
    monkeypatch.setattr(
        publish_registries,
        "_make_transport",
        lambda authfile, credential: transport,
    )

    assert main(_cli_args(tmp_path, archives)) == 1

    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "publication-failure.json").exists()
    assert not (tmp_path / "auth.json").exists()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TCR_REGISTRY", "evil.invalid"),
        ("TCR_NAMESPACE", "other"),
    ],
)
def test_cli_rejects_unapproved_tcr_coordinates_before_login_or_authfile_creation(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    _set_cli_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    called = False

    def unexpected_transport(authfile, credential):
        nonlocal called
        called = True
        raise AssertionError("transport must not be created")

    monkeypatch.setattr(publish_registries, "_make_transport", unexpected_transport)

    assert main(_cli_args(tmp_path, archives)) == 2

    assert called is False
    assert not (tmp_path / "auth.json").exists()
    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "publication-failure.json").exists()


def test_cli_authfile_is_private_while_transport_is_active(
    tmp_path: Path,
    archives: Mapping[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cli_environment(monkeypatch)
    authfile = tmp_path / "auth.json"
    observed_modes: list[int] = []
    transport = StatefulTransport()

    def make_transport(created: Path, credential: Credential):
        assert created == authfile
        observed_modes.append(stat.S_IMODE(created.stat().st_mode))
        return transport

    monkeypatch.setattr(publish_registries, "_make_transport", make_transport)

    assert main(_cli_args(tmp_path, archives)) == 0

    if os.name != "nt":
        assert observed_modes == [0o600]
    assert not authfile.exists()
