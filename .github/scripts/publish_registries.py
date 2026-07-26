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
import time
from collections.abc import Mapping
from pathlib import Path
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


def _archive_digest(path: Path) -> str:
    try:
        with tarfile.open(path, "r:*") as archive:
            member = archive.getmember("index.json")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError("OCI archive index is not a regular file")
            payload = json.loads(extracted.read().decode("utf-8"))
    except (OSError, tarfile.TarError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("OCI archive has no valid index.json") from exc
    if not isinstance(payload, dict):
        raise ValueError("OCI archive index must be an object")
    manifests = payload.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise ValueError("OCI archive must contain exactly one manifest descriptor")
    descriptor = manifests[0]
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("digest"), str):
        raise ValueError("OCI archive manifest descriptor has no digest")
    digest = descriptor["digest"]
    algorithm, separator, encoded = digest.partition(":")
    if (
        algorithm != "sha256"
        or separator != ":"
        or len(encoded) != 64
        or any(character not in "0123456789abcdef" for character in encoded)
    ):
        raise ValueError("OCI archive manifest descriptor digest is invalid")
    try:
        with tarfile.open(path, "r:*") as archive:
            manifest = archive.extractfile(archive.getmember(f"blobs/sha256/{encoded}"))
            if manifest is None:
                raise ValueError("OCI archive manifest blob is not a regular file")
            actual = hashlib.sha256(manifest.read()).hexdigest()
    except (OSError, tarfile.TarError, KeyError) as exc:
        raise ValueError("OCI archive has no referenced manifest blob") from exc
    if actual != encoded:
        raise ValueError("OCI archive descriptor digest does not match manifest blob")
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
                _sleep_after_transient(
                    transient.failure_number,
                    time.sleep,
                    transport.jitter,
                )
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

    return create_release_manifest(commit, digests, ghcr_statuses)


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
    path.write_bytes(canonical_json(payload))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.manifest_output.unlink(missing_ok=True)
    args.failure_output.unlink(missing_ok=True)

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

    try:
        with secure_authfile(args.authfile):
            transport = _make_transport(args.authfile, credentials["tcr"])
            manifest = publish_release(
                args.commit,
                archives,
                transport,
                credentials,
                args.workflow_run_id,
            )
    except PublicationError as exc:
        if exc.mutated:
            _write_canonical(args.failure_output, exc.report())
        return 1
    except (OSError, ValueError):
        return 2

    _write_canonical(args.manifest_output, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
