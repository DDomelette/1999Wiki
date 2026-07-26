#!/usr/bin/env python3
"""Publish one OCI build to TCR first and GHCR second."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Callable


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIRECTORY.parents[1]
DEPLOY_BIN = REPOSITORY_ROOT / "deploy" / "bin"
for _directory in (SCRIPT_DIRECTORY, DEPLOY_BIN):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from registry_transport import (  # noqa: E402
    CommandResult,
    Credential,
    MirrorDeferred,
    ProbeState,
    RegistryFailure,
    RetryBudget,
    SkopeoTransport,
    _TransientRegistryFailure,
    _retry_transient,
    _sleep_after_transient,
    secure_authfile,
)
from release_identity import (  # noqa: E402
    COMPONENTS,
    REPOSITORIES,
    canonical_json,
    create_release_manifest,
)


TCR_REGISTRY = "ccr.ccs.tencentyun.com"
TCR_NAMESPACE = "1999wiki_code"
GHCR_REGISTRY = "ghcr.io"
FAILURE_SCHEMA_VERSION = "1999wiki.publication-failure/v1"
DEFERRED = "deferred_after_5_network_failures"
_ENVIRONMENT_KEYS = (
    "TCR_USERNAME",
    "TCR_PASSWORD",
    "GHCR_USERNAME",
    "GHCR_PASSWORD",
    "TCR_REGISTRY",
    "TCR_NAMESPACE",
)
_MAX_OCI_MEMBERS = 4096
_MAX_OCI_INDEX_BYTES = 256 * 1024
_MAX_OCI_MANIFEST_BYTES = 4 * 1024 * 1024
_HASH_CHUNK_BYTES = 64 * 1024
_OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
_DOCKER_MANIFEST_MEDIA_TYPE = (
    "application/vnd.docker.distribution.manifest.v2+json"
)
_MANIFEST_MEDIA_TYPES = {
    _OCI_MANIFEST_MEDIA_TYPE,
    _DOCKER_MANIFEST_MEDIA_TYPE,
}
_CONFIG_MEDIA_TYPES = {
    _OCI_MANIFEST_MEDIA_TYPE: {
        "application/vnd.oci.image.config.v1+json",
    },
    _DOCKER_MANIFEST_MEDIA_TYPE: {
        "application/vnd.docker.container.image.v1+json",
    },
}
_LAYER_MEDIA_TYPES = {
    _OCI_MANIFEST_MEDIA_TYPE: {
        "application/vnd.oci.image.layer.v1.tar",
        "application/vnd.oci.image.layer.v1.tar+gzip",
        "application/vnd.oci.image.layer.v1.tar+zstd",
        "application/vnd.oci.image.layer.nondistributable.v1.tar",
        "application/vnd.oci.image.layer.nondistributable.v1.tar+gzip",
        "application/vnd.oci.image.layer.nondistributable.v1.tar+zstd",
    },
    _DOCKER_MANIFEST_MEDIA_TYPE: {
        "application/vnd.docker.image.rootfs.diff.tar",
        "application/vnd.docker.image.rootfs.diff.tar.gzip",
        "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip",
    },
}


class PublicationError(RuntimeError):
    """Sanitized fatal publication state, safe to serialize."""

    def __init__(
        self,
        *,
        commit: str,
        workflow_run_id: str,
        phase: str,
        code: str,
        mutated: bool,
        verified_tcr: Mapping[str, str],
    ) -> None:
        self.commit = commit
        self.workflow_run_id = workflow_run_id
        self.phase = phase
        self.code = code
        self.mutated = mutated
        self.verified_tcr = dict(verified_tcr)
        super().__init__(f"publication failed: phase={phase} code={code}")

    def report(self) -> dict[str, object]:
        return {
            "schema_version": FAILURE_SCHEMA_VERSION,
            "commit": self.commit,
            "release_tag": f"sha-{self.commit[:7]}",
            "phase": self.phase,
            "code": self.code,
            "workflow_run_id": self.workflow_run_id,
            "verified_tcr": dict(self.verified_tcr),
        }


def _local_failure_code(error: Exception) -> str:
    if isinstance(error, OSError):
        return "local_io_failure"
    if isinstance(error, ValueError):
        return "local_validation_failure"
    return "unexpected_local_failure"


def _digest_hex(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} digest is invalid")
    algorithm, separator, encoded = value.partition(":")
    if (
        algorithm != "sha256"
        or separator != ":"
        or len(encoded) != 64
        or any(character not in "0123456789abcdef" for character in encoded)
    ):
        raise ValueError(f"{label} digest is invalid")
    return encoded


def _checked_member_name(member: tarfile.TarInfo) -> str:
    name = member.name.rstrip("/") if member.isdir() else member.name
    candidate = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or candidate.is_absolute()
        or ".." in candidate.parts
        or "." in candidate.parts
        or str(candidate) != name
    ):
        raise ValueError("OCI archive contains an unsafe member path")
    if not (member.isfile() or member.isdir()):
        raise ValueError("OCI archive contains a link or non-regular member")
    return name


def _read_member(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    maximum: int,
    label: str,
) -> bytes:
    if not member.isfile():
        raise ValueError(f"{label} must be a regular file")
    if member.size < 0 or member.size > maximum:
        raise ValueError(f"{label} exceeds the permitted size")
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ValueError(f"{label} must be a regular file")
    raw = extracted.read(member.size + 1)
    if len(raw) != member.size:
        raise ValueError(f"{label} size does not match its tar header")
    return raw


def _referenced_descriptor(
    archive: tarfile.TarFile,
    descriptor: object,
    *,
    media_types: set[str],
    members: Mapping[str, tarfile.TarInfo],
    label: str,
) -> None:
    if not isinstance(descriptor, dict):
        raise ValueError(f"{label} descriptor must be an object")
    media_type = descriptor.get("mediaType")
    if not isinstance(media_type, str) or media_type not in media_types:
        raise ValueError(f"{label} descriptor mediaType is invalid")
    encoded = _digest_hex(descriptor.get("digest"), label)
    size = descriptor.get("size")
    if type(size) is not int or size < 0:
        raise ValueError(f"{label} descriptor size is invalid")
    member = members.get(f"blobs/sha256/{encoded}")
    if member is None or not member.isfile() or member.size != size:
        raise ValueError(f"{label} descriptor does not match its local blob")
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ValueError(f"{label} blob must be a regular file")
    remaining = member.size
    actual = hashlib.sha256()
    while remaining:
        chunk = extracted.read(min(_HASH_CHUNK_BYTES, remaining))
        if not chunk:
            raise ValueError(f"{label} blob size is incomplete")
        actual.update(chunk)
        remaining -= len(chunk)
    if actual.hexdigest() != encoded:
        raise ValueError(f"{label} blob digest does not match its descriptor")


def _archive_digest(path: Path) -> str:
    try:
        with tarfile.open(path, "r:*") as archive:
            members: dict[str, tarfile.TarInfo] = {}
            for count, member in enumerate(archive, start=1):
                if count > _MAX_OCI_MEMBERS:
                    raise ValueError("OCI archive contains too many members")
                name = _checked_member_name(member)
                if name in members:
                    raise ValueError("OCI archive contains duplicate member paths")
                members[name] = member

            index_member = members.get("index.json")
            if index_member is None:
                raise ValueError("OCI archive has no index.json")
            index_raw = _read_member(
                archive,
                index_member,
                _MAX_OCI_INDEX_BYTES,
                "OCI archive index",
            )
            try:
                index = json.loads(index_raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("OCI archive index is not valid JSON") from exc
            if not isinstance(index, dict) or type(index.get("schemaVersion")) is not int:
                raise ValueError("OCI archive index schemaVersion is invalid")
            if index["schemaVersion"] != 2:
                raise ValueError("OCI archive index schemaVersion is invalid")
            manifests = index.get("manifests")
            if not isinstance(manifests, list) or len(manifests) != 1:
                raise ValueError(
                    "OCI archive must contain exactly one manifest descriptor"
                )
            descriptor = manifests[0]
            if not isinstance(descriptor, dict):
                raise ValueError("OCI archive manifest descriptor must be an object")
            media_type = descriptor.get("mediaType")
            if media_type not in _MANIFEST_MEDIA_TYPES:
                raise ValueError("OCI archive manifest mediaType is invalid")
            digest = descriptor.get("digest")
            encoded = _digest_hex(digest, "OCI archive manifest")
            declared_size = descriptor.get("size")
            if (
                type(declared_size) is not int
                or declared_size < 1
                or declared_size > _MAX_OCI_MANIFEST_BYTES
            ):
                raise ValueError("OCI archive manifest size is invalid")
            manifest_member = members.get(f"blobs/sha256/{encoded}")
            if (
                manifest_member is None
                or not manifest_member.isfile()
                or manifest_member.size != declared_size
            ):
                raise ValueError(
                    "OCI archive manifest descriptor does not match its blob"
                )
            manifest_raw = _read_member(
                archive,
                manifest_member,
                _MAX_OCI_MANIFEST_BYTES,
                "OCI archive manifest",
            )
            if hashlib.sha256(manifest_raw).hexdigest() != encoded:
                raise ValueError(
                    "OCI archive descriptor digest does not match manifest blob"
                )
            try:
                manifest = json.loads(manifest_raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("OCI archive manifest is not valid JSON") from exc
            if (
                not isinstance(manifest, dict)
                or type(manifest.get("schemaVersion")) is not int
                or manifest["schemaVersion"] != 2
                or manifest.get("mediaType") != media_type
            ):
                raise ValueError("OCI archive manifest schema is invalid")
            _referenced_descriptor(
                archive,
                manifest.get("config"),
                media_types=_CONFIG_MEDIA_TYPES[media_type],
                members=members,
                label="OCI image config",
            )
            layers = manifest.get("layers")
            if not isinstance(layers, list):
                raise ValueError("OCI image layers must be a list")
            for layer in layers:
                _referenced_descriptor(
                    archive,
                    layer,
                    media_types=_LAYER_MEDIA_TYPES[media_type],
                    members=members,
                    label="OCI image layer",
                )
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("OCI archive is not a readable tar file") from exc
    assert isinstance(digest, str)
    return digest


def _validate_workflow_run_id(workflow_run_id: str) -> None:
    if (
        not isinstance(workflow_run_id, str)
        or not workflow_run_id.isascii()
        or not workflow_run_id.isdecimal()
    ):
        raise ValueError("workflow_run_id must contain ASCII decimal digits only")


def _targets(commit: str) -> dict[str, dict[str, str]]:
    tag = f"sha-{commit[:7]}"
    return {
        registry: {
            component: f"{REPOSITORIES[registry][component]}:{tag}"
            for component in COMPONENTS
        }
        for registry in ("tcr", "ghcr")
    }


def publish_release(
    commit: str,
    archives: Mapping[str, Path],
    transport: SkopeoTransport,
    credentials: Mapping[str, Credential],
    workflow_run_id: str,
) -> dict[str, object]:
    """Publish using a TCR hard gate and one shared GHCR retry budget."""
    if set(archives) != set(COMPONENTS):
        raise ValueError("archives must contain exactly backend and frontend")
    if set(credentials) != {"tcr", "ghcr"}:
        raise ValueError("credentials must contain exactly tcr and ghcr")
    if not all(isinstance(credentials[name], Credential) for name in ("tcr", "ghcr")):
        raise ValueError("registry credentials are invalid")
    _validate_workflow_run_id(workflow_run_id)

    archive_paths = {component: Path(archives[component]) for component in COMPONENTS}
    digests = {
        component: _archive_digest(archive_paths[component])
        for component in COMPONENTS
    }
    # Validate the complete release identity before any registry command.
    create_release_manifest(
        commit,
        digests,
        {"backend": "published", "frontend": "published"},
    )
    targets = _targets(commit)
    tcr_budget = RetryBudget(max_failures=1)
    ghcr_budget = RetryBudget()
    mutated = False
    verified_tcr: dict[str, str] = {}

    def fatal(phase: str, code: str) -> PublicationError:
        return PublicationError(
            commit=commit,
            workflow_run_id=workflow_run_id,
            phase=phase,
            code=code,
            mutated=mutated,
            verified_tcr=verified_tcr,
        )

    def call(
        operation: Callable[[], ProbeState | None],
        phase: str,
        budget: RetryBudget,
        *,
        allow_deferred: bool,
    ) -> ProbeState | None:
        try:
            return _retry_transient(
                operation,
                budget,
                time.sleep,
                transport.jitter,
            )
        except MirrorDeferred:
            if allow_deferred:
                raise
            raise fatal(phase, "network_failure") from None
        except RegistryFailure as exc:
            raise fatal(phase, exc.code) from None
        except Exception as exc:
            raise fatal(phase, _local_failure_code(exc)) from None

    def login(registry: str, *, allow_deferred: bool) -> None:
        budget = tcr_budget if registry == "tcr" else ghcr_budget
        transport.credential = credentials[registry]
        hostname = TCR_REGISTRY if registry == "tcr" else GHCR_REGISTRY
        call(
            lambda: transport.login(hostname, budget),
            f"{registry}_login",
            budget,
            allow_deferred=allow_deferred,
        )

    def preflight_component(registry: str, component: str) -> None:
        budget = tcr_budget if registry == "tcr" else ghcr_budget
        state = call(
            lambda: transport.probe(
                targets[registry][component],
                digests[component],
                budget,
            ),
            f"{registry}_{component}_probe",
            budget,
            allow_deferred=registry == "ghcr",
        )
        if state is not ProbeState.ABSENT:
            raise fatal(f"{registry}_{component}_probe", "tag_conflict")

    login("tcr", allow_deferred=False)
    for component in COMPONENTS:
        preflight_component("tcr", component)

    ghcr_preflight_deferred = False
    try:
        login("ghcr", allow_deferred=True)
        for component in COMPONENTS:
            preflight_component("ghcr", component)
    except MirrorDeferred:
        ghcr_preflight_deferred = True

    def copy_and_verify(
        registry: str,
        component: str,
        *,
        allow_deferred: bool,
    ) -> None:
        nonlocal mutated
        budget = tcr_budget if registry == "tcr" else ghcr_budget
        mutated = True
        copy_phase = f"{registry}_{component}_copy"
        verify_phase = f"{registry}_{component}_verify"
        reconciled = False
        while True:
            try:
                transport.copy(
                    str(archive_paths[component]),
                    targets[registry][component],
                    budget,
                )
            except _TransientRegistryFailure as transient:
                try:
                    _sleep_after_transient(
                        transient.failure_number,
                        time.sleep,
                        transport.jitter,
                    )
                except Exception as exc:
                    raise fatal(copy_phase, _local_failure_code(exc)) from None
                state = call(
                    lambda: transport.probe(
                        targets[registry][component],
                        digests[component],
                        budget,
                    ),
                    verify_phase,
                    budget,
                    allow_deferred=allow_deferred,
                )
                if state is ProbeState.PRESENT_EXPECTED:
                    reconciled = True
                    break
                if state is ProbeState.ABSENT:
                    continue
                raise fatal(verify_phase, "digest_mismatch")
            except MirrorDeferred:
                if allow_deferred:
                    raise
                raise fatal(copy_phase, "network_failure") from None
            except RegistryFailure as exc:
                raise fatal(copy_phase, exc.code) from None
            except Exception as exc:
                raise fatal(copy_phase, _local_failure_code(exc)) from None
            break
        if reconciled:
            state = ProbeState.PRESENT_EXPECTED
        else:
            state = call(
                lambda: transport.probe(
                    targets[registry][component],
                    digests[component],
                    budget,
                ),
                verify_phase,
                budget,
                allow_deferred=allow_deferred,
            )
        if state is ProbeState.ABSENT:
            raise fatal(
                verify_phase,
                "manifest_missing_after_copy",
            )
        if state is not ProbeState.PRESENT_EXPECTED:
            raise fatal(verify_phase, "digest_mismatch")
        if registry == "tcr":
            verified_tcr[component] = (
                f"{targets['tcr'][component]}@{digests[component]}"
            )

    for component in COMPONENTS:
        copy_and_verify("tcr", component, allow_deferred=False)

    ghcr_statuses: dict[str, str] = {}
    if ghcr_preflight_deferred:
        ghcr_statuses = {component: DEFERRED for component in COMPONENTS}
    else:
        for index, component in enumerate(COMPONENTS):
            try:
                copy_and_verify("ghcr", component, allow_deferred=True)
            except MirrorDeferred:
                for remaining in COMPONENTS[index:]:
                    ghcr_statuses[remaining] = DEFERRED
                break
            ghcr_statuses[component] = "published"

    try:
        return create_release_manifest(commit, digests, ghcr_statuses)
    except Exception as exc:
        raise fatal("manifest_build", _local_failure_code(exc)) from None


def _run_skopeo(argv: list[str], stdin: bytes | None) -> CommandResult:
    completed = subprocess.run(
        argv,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return CommandResult(
        completed.returncode,
        completed.stdout,
        completed.stderr.decode("utf-8", errors="replace"),
    )


def _make_transport(authfile: Path, credential: Credential) -> SkopeoTransport:
    return SkopeoTransport(
        authfile=authfile,
        credential=credential,
        runner=_run_skopeo,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--backend-archive", required=True, type=Path)
    parser.add_argument("--frontend-archive", required=True, type=Path)
    parser.add_argument("--authfile", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--failure-output", required=True, type=Path)
    parser.add_argument("--workflow-run-id", required=True)
    return parser


def _write_canonical(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_distinct_paths(paths: tuple[Path, ...]) -> None:
    resolved = tuple(path.resolve(strict=False) for path in paths)
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left == right:
                raise ValueError("publication paths must be pairwise distinct")
            try:
                equivalent = os.path.samefile(left, right)
            except OSError:
                equivalent = False
            if equivalent:
                raise ValueError("publication paths must be pairwise distinct")


def _remove_output(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _emit_failure(
    error: PublicationError,
    manifest_output: Path,
    failure_output: Path,
) -> None:
    _remove_output(manifest_output)
    try:
        _write_canonical(failure_output, error.report())
    except Exception:
        _remove_output(failure_output)


def _verified_tcr_from_manifest(
    manifest: Mapping[str, object],
) -> dict[str, str]:
    images = manifest["images"]
    assert isinstance(images, Mapping)
    verified: dict[str, str] = {}
    for component in COMPONENTS:
        image = images[component]
        assert isinstance(image, Mapping)
        registries = image["registries"]
        assert isinstance(registries, Mapping)
        tcr = registries["tcr"]
        assert isinstance(tcr, Mapping)
        reference = tcr["ref"]
        assert isinstance(reference, str)
        verified[component] = reference
    return verified


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _validate_distinct_paths(
            (
                args.backend_archive,
                args.frontend_archive,
                args.authfile,
                args.manifest_output,
                args.failure_output,
            )
        )
    except (OSError, ValueError):
        return 2
    try:
        args.manifest_output.unlink(missing_ok=True)
        args.failure_output.unlink(missing_ok=True)
    except OSError:
        return 2

    environment = {key: os.environ.get(key) for key in _ENVIRONMENT_KEYS}
    if (
        environment["TCR_REGISTRY"] != TCR_REGISTRY
        or environment["TCR_NAMESPACE"] != TCR_NAMESPACE
    ):
        return 2
    if any(not environment[key] for key in _ENVIRONMENT_KEYS[:4]):
        return 2

    credentials = {
        "tcr": Credential(
            environment["TCR_USERNAME"],  # type: ignore[arg-type]
            environment["TCR_PASSWORD"],  # type: ignore[arg-type]
        ),
        "ghcr": Credential(
            environment["GHCR_USERNAME"],  # type: ignore[arg-type]
            environment["GHCR_PASSWORD"],  # type: ignore[arg-type]
        ),
    }
    archives = {
        "backend": args.backend_archive,
        "frontend": args.frontend_archive,
    }

    manifest: dict[str, object] | None = None
    publication_error: PublicationError | None = None
    try:
        with secure_authfile(args.authfile):
            transport = _make_transport(args.authfile, credentials["tcr"])
            try:
                manifest = publish_release(
                    args.commit,
                    archives,
                    transport,
                    credentials,
                    args.workflow_run_id,
                )
            except PublicationError as exc:
                publication_error = exc
    except Exception as exc:
        if publication_error is None and manifest is not None:
            cleanup_error = PublicationError(
                commit=args.commit,
                workflow_run_id=args.workflow_run_id,
                phase="authfile_cleanup",
                code=_local_failure_code(exc),
                mutated=True,
                verified_tcr=_verified_tcr_from_manifest(manifest),
            )
            _emit_failure(
                cleanup_error,
                args.manifest_output,
                args.failure_output,
            )
            return 1
        if publication_error is None:
            return 2

    if publication_error is not None:
        if publication_error.mutated:
            _emit_failure(
                publication_error,
                args.manifest_output,
                args.failure_output,
            )
        return 1

    assert manifest is not None
    try:
        _write_canonical(args.manifest_output, manifest)
    except Exception as exc:
        write_error = PublicationError(
            commit=args.commit,
            workflow_run_id=args.workflow_run_id,
            phase="manifest_write",
            code=_local_failure_code(exc),
            mutated=True,
            verified_tcr=_verified_tcr_from_manifest(manifest),
        )
        _emit_failure(
            write_error,
            args.manifest_output,
            args.failure_output,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
