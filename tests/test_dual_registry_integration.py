from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest


SKOPEO_IMAGE = "quay.io/skopeo/stable:v1.19.0"
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
DEPLOY_BIN = ROOT / "deploy" / "bin"
for directory in (SCRIPTS, DEPLOY_BIN):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import registry_transport as registry_transport_module  # noqa: E402
from registry_transport import (  # noqa: E402
    ProbeState,
    RegistryFailure,
    RetryBudget,
    ensure_mirror_copy,
)


@dataclass(frozen=True)
class CopyEvidence:
    source_digest: str
    first_registry_digest: str
    second_registry_digest: str
    exact_policy_result: str
    exact_policy_copy_calls: int
    exact_digest_before: str
    exact_digest_after: str
    conflict_digest_before: str
    conflict_was_rejected: bool
    conflict_policy_copy_calls: int
    conflict_digest_after: str
    remaining_resources: tuple[str, ...]


@dataclass(frozen=True)
class CleanupOutcome:
    errors: tuple[str, ...]
    residues: tuple[str, ...]


def _run_best_effort_cleanup(
    *,
    cleanup_steps: tuple[tuple[str, Callable[[], object]], ...],
    residue_checks: tuple[tuple[str, Callable[[], list[str]]], ...],
) -> CleanupOutcome:
    errors: list[str] = []
    residues: list[str] = []
    for label, cleanup in cleanup_steps:
        try:
            cleanup()
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    for label, check in residue_checks:
        try:
            residues.extend(f"{label}:{item}" for item in check())
        except Exception as exc:
            errors.append(f"{label} residue check: {type(exc).__name__}: {exc}")
    return CleanupOutcome(tuple(errors), tuple(residues))


def _raise_aggregated_fixture_failure(
    primary: BaseException | None,
    cleanup: CleanupOutcome,
) -> None:
    details: list[str] = []
    if primary is not None:
        details.append(f"primary error: {type(primary).__name__}: {primary}")
    if cleanup.errors:
        details.append(f"cleanup errors: {cleanup.errors!r}")
    if cleanup.residues:
        details.append(f"residues: {cleanup.residues!r}")
    aggregate = AssertionError(
        "dual-registry fixture failed; " + "; ".join(details)
    )
    if primary is not None:
        raise aggregate from primary
    raise aggregate


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        stdout = result.stdout.decode("utf-8", errors="replace")
        raise AssertionError(
            f"command failed ({result.returncode}): {argv!r}\n"
            f"stdout:\n{stdout[-4000:]}\nstderr:\n{stderr[-4000:]}"
        )
    return result


def docker_ps_names(prefix: str) -> list[str]:
    result = _run(["docker", "ps", "-a", "--format", "{{.Names}}"])
    return sorted(
        name
        for name in result.stdout.decode("utf-8").splitlines()
        if name.startswith(prefix)
    )


def docker_network_names(prefix: str) -> list[str]:
    result = _run(["docker", "network", "ls", "--format", "{{.Name}}"])
    return sorted(
        name
        for name in result.stdout.decode("utf-8").splitlines()
        if name.startswith(prefix)
    )


def docker_image_refs(repository_prefix: str) -> list[str]:
    result = _run(
        ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"]
    )
    return sorted(
        reference
        for reference in result.stdout.decode("utf-8").splitlines()
        if reference.split(":", 1)[0].startswith(repository_prefix)
    )


def _digest(raw_manifest: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw_manifest).hexdigest()


@dataclass
class LocalRegistryTransport:
    inspect_target: Callable[[str], subprocess.CompletedProcess[bytes]]
    skopeo: Callable[..., subprocess.CompletedProcess[bytes]]
    copy_calls: int = 0
    jitter: Callable[[], float] = lambda: 0.0

    def login(self, registry: str, budget: RetryBudget) -> None:
        del registry
        budget.ensure_available()

    def probe(
        self, target: str, expected_digest: str, budget: RetryBudget
    ) -> ProbeState:
        budget.ensure_available()
        inspected = self.inspect_target(target)
        if inspected.returncode != 0:
            raise AssertionError(
                "local registry probe failed: "
                + inspected.stderr.decode("utf-8", errors="replace")[-2000:]
            )
        return (
            ProbeState.PRESENT_EXPECTED
            if _digest(inspected.stdout) == expected_digest
            else ProbeState.PRESENT_CONFLICT
        )

    def copy(self, source: str, target: str, budget: RetryBudget) -> None:
        budget.ensure_available()
        self.copy_calls += 1
        self.skopeo(
            "copy",
            "--all",
            "--preserve-digests",
            "--dest-tls-verify=false",
            source,
            f"docker://{target}",
        )


def _remove_container(name: str) -> None:
    result = _run(["docker", "container", "rm", "--force", name], check=False)
    if result.returncode != 0 and b"No such container" not in result.stderr:
        raise AssertionError(
            result.stderr.decode("utf-8", errors="replace")[-2000:]
        )


def _remove_network(name: str) -> None:
    result = _run(["docker", "network", "rm", name], check=False)
    if result.returncode != 0 and b"not found" not in result.stderr.lower():
        raise AssertionError(
            result.stderr.decode("utf-8", errors="replace")[-2000:]
        )


def _remove_scoped_images(repository_prefix: str) -> None:
    image_steps = tuple(
        (
            f"remove image {reference}",
            lambda reference=reference: _run(
                ["docker", "image", "rm", reference],
                check=True,
            ),
        )
        for reference in docker_image_refs(repository_prefix)
    )
    outcome = _run_best_effort_cleanup(
        cleanup_steps=image_steps,
        residue_checks=(),
    )
    if outcome.errors:
        raise AssertionError("; ".join(outcome.errors))


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _build_oci_archive(
    *,
    context: Path,
    archive: Path,
    payload: str,
    cwd: Path,
) -> None:
    context.mkdir()
    (context / "Dockerfile").write_text(
        "FROM scratch\nCOPY payload.txt /payload.txt\n",
        encoding="utf-8",
        newline="\n",
    )
    (context / "payload.txt").write_text(
        payload,
        encoding="utf-8",
        newline="\n",
    )
    _run(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "--output",
            f"type=oci,dest={archive}",
            str(context),
        ],
        cwd=cwd,
    )


def _run_dual_registry_fixture(tmp_path: Path) -> CopyEvidence:
    token = uuid.uuid4().hex[:12]
    prefix = f"1999wiki-dual-registry-{token}"
    network = f"{prefix}-network"
    registry_containers = (
        f"{prefix}-registry-a",
        f"{prefix}-registry-b",
    )
    repository_prefix = prefix
    repository = f"{repository_prefix}/fixture"
    source = "oci-archive:/fixture/fixture.oci"
    targets = (
        f"registry-a:5000/{repository}:sha-abcdef0",
        f"registry-b:5000/{repository}:sha-abcdef0",
    )
    conflict_repository = f"{repository_prefix}/conflict"
    conflict_target = f"registry-b:5000/{conflict_repository}:sha-abcdef0"
    conflict_source = "oci-archive:/fixture/conflict.oci"
    context = tmp_path / "fixture-context"
    archive = tmp_path / "fixture.oci"
    conflict_context = tmp_path / "conflict-context"
    conflict_archive = tmp_path / "conflict.oci"
    skopeo_container_names: list[str] = []
    failure: BaseException | None = None
    source_digest = ""
    first_registry_digest = ""
    second_registry_digest = ""
    exact_policy_result = ""
    exact_policy_copy_calls = -1
    exact_digest_before = ""
    exact_digest_after = ""
    conflict_digest_before = ""
    conflict_was_rejected = False
    conflict_policy_copy_calls = -1
    conflict_digest_after = ""
    remaining_resources: tuple[str, ...] = ()
    cleanup_outcome = CleanupOutcome((), ())

    def skopeo(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        name = f"{prefix}-skopeo-{len(skopeo_container_names) + 1}"
        skopeo_container_names.append(name)
        return _run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                network,
                "--volume",
                f"{tmp_path.resolve()}:/fixture:ro",
                SKOPEO_IMAGE,
                *arguments,
            ],
            check=check,
        )

    def inspect_target(
        target: str, *, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        return skopeo(
            "inspect",
            "--raw",
            "--tls-verify=false",
            f"docker://{target}",
            check=check,
        )

    try:
        _build_oci_archive(
            context=context,
            archive=archive,
            payload="dual-registry-fixture\n",
            cwd=tmp_path,
        )
        _build_oci_archive(
            context=conflict_context,
            archive=conflict_archive,
            payload="dual-registry-conflict\n",
            cwd=tmp_path,
        )

        _run(["docker", "network", "create", network])
        for container, alias in zip(
            registry_containers, ("registry-a", "registry-b"), strict=True
        ):
            _run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    container,
                    "--network",
                    network,
                    "--network-alias",
                    alias,
                    "registry:2",
                ]
            )

        deadline = time.monotonic() + 15
        for container in registry_containers:
            while True:
                ready = _run(
                    [
                        "docker",
                        "exec",
                        container,
                        "wget",
                        "-q",
                        "-O",
                        "-",
                        "http://127.0.0.1:5000/v2/",
                    ],
                    check=False,
                )
                if ready.returncode == 0 and ready.stdout.strip() == b"{}":
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        f"registry did not become ready: {container}: "
                        f"{ready.stderr.decode('utf-8', errors='replace')[-2000:]}"
                    )
                time.sleep(0.1)

        source_digest = _digest(skopeo("inspect", "--raw", source).stdout)
        for target in targets:
            skopeo(
                "copy",
                "--all",
                "--preserve-digests",
                "--dest-tls-verify=false",
                source,
                f"docker://{target}",
            )

        first_registry_digest = _digest(inspect_target(targets[0]).stdout)
        second_registry_digest = _digest(inspect_target(targets[1]).stdout)

        skopeo(
            "copy",
            "--all",
            "--preserve-digests",
            "--dest-tls-verify=false",
            conflict_source,
            f"docker://{conflict_target}",
        )
        conflict_digest_before = _digest(inspect_target(conflict_target).stdout)

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setitem(
                registry_transport_module.REPOSITORIES,
                "local_fixture",
                {
                    "backend": targets[0].rsplit(":", 1)[0],
                    "frontend": conflict_target.rsplit(":", 1)[0],
                },
            )

            exact_transport = LocalRegistryTransport(
                inspect_target=inspect_target,
                skopeo=skopeo,
            )
            exact_digest_before = _digest(inspect_target(targets[0]).stdout)
            exact_policy_result = ensure_mirror_copy(
                exact_transport,  # type: ignore[arg-type]
                source,
                targets[0],
                source_digest,
                RetryBudget(),
                lambda _: None,
            )
            exact_policy_copy_calls = exact_transport.copy_calls
            exact_digest_after = _digest(inspect_target(targets[0]).stdout)

            conflict_transport = LocalRegistryTransport(
                inspect_target=inspect_target,
                skopeo=skopeo,
            )
            try:
                ensure_mirror_copy(
                    conflict_transport,  # type: ignore[arg-type]
                    source,
                    conflict_target,
                    source_digest,
                    RetryBudget(),
                    lambda _: None,
                )
            except RegistryFailure as exc:
                conflict_was_rejected = exc.code == "digest_conflict"
            else:
                raise AssertionError(
                    "production mirror policy accepted a conflicting local tag"
                )
            conflict_policy_copy_calls = conflict_transport.copy_calls
            conflict_digest_after = _digest(inspect_target(conflict_target).stdout)
    except BaseException as exc:
        failure = exc
    finally:
        cleanup_steps: list[tuple[str, Callable[[], object]]] = []
        for name in (*registry_containers, *skopeo_container_names):
            cleanup_steps.append(
                (
                    f"remove container {name}",
                    lambda name=name: _remove_container(name),
                )
            )
        cleanup_steps.extend(
            (
                ("remove network", lambda: _remove_network(network)),
                (
                    "remove scoped images",
                    lambda: _remove_scoped_images(repository_prefix),
                ),
                ("unlink primary archive", lambda: archive.unlink(missing_ok=True)),
                (
                    "unlink conflict archive",
                    lambda: conflict_archive.unlink(missing_ok=True),
                ),
                ("remove primary context", lambda: _remove_tree(context)),
                (
                    "remove conflict context",
                    lambda: _remove_tree(conflict_context),
                ),
            )
        )
        outcome = _run_best_effort_cleanup(
            cleanup_steps=tuple(cleanup_steps),
            residue_checks=(
                ("containers", lambda: docker_ps_names(prefix)),
                ("networks", lambda: docker_network_names(prefix)),
                ("images", lambda: docker_image_refs(repository_prefix)),
                (
                    "paths",
                    lambda: [
                        str(path)
                        for path in (
                            archive,
                            conflict_archive,
                            context,
                            conflict_context,
                        )
                        if path.exists()
                    ],
                ),
            ),
        )
        cleanup_outcome = outcome
        remaining_resources = outcome.residues

    if failure is not None or cleanup_outcome.errors or remaining_resources:
        _raise_aggregated_fixture_failure(failure, cleanup_outcome)

    return CopyEvidence(
        source_digest=source_digest,
        first_registry_digest=first_registry_digest,
        second_registry_digest=second_registry_digest,
        exact_policy_result=exact_policy_result,
        exact_policy_copy_calls=exact_policy_copy_calls,
        exact_digest_before=exact_digest_before,
        exact_digest_after=exact_digest_after,
        conflict_digest_before=conflict_digest_before,
        conflict_was_rejected=conflict_was_rejected,
        conflict_policy_copy_calls=conflict_policy_copy_calls,
        conflict_digest_after=conflict_digest_after,
        remaining_resources=remaining_resources,
    )


@pytest.mark.registry_integration
def test_one_oci_archive_copies_to_two_registries_with_one_digest(
    tmp_path: Path,
) -> None:
    evidence = _run_dual_registry_fixture(tmp_path)
    assert evidence.source_digest == evidence.first_registry_digest
    assert evidence.source_digest == evidence.second_registry_digest
    assert evidence.exact_policy_result == "published"
    assert evidence.exact_policy_copy_calls == 0
    assert evidence.exact_digest_before == evidence.exact_digest_after
    assert evidence.conflict_digest_before != evidence.source_digest
    assert evidence.conflict_was_rejected is True
    assert evidence.conflict_policy_copy_calls == 0
    assert evidence.conflict_digest_before == evidence.conflict_digest_after
    assert evidence.remaining_resources == ()


def test_cleanup_attempts_every_step_and_aggregates_errors_and_residues() -> None:
    events: list[str] = []

    def fail_cleanup() -> None:
        events.append("cleanup-failed")
        raise RuntimeError("injected cleanup failure")

    def pass_cleanup() -> None:
        events.append("cleanup-continued")

    def fail_residue_check() -> list[str]:
        events.append("residue-check-failed")
        raise OSError("injected residue check failure")

    def find_residue() -> list[str]:
        events.append("residue-check-continued")
        return ["leaked-network"]

    outcome = _run_best_effort_cleanup(
        cleanup_steps=(
            ("first-cleanup", fail_cleanup),
            ("second-cleanup", pass_cleanup),
        ),
        residue_checks=(
            ("containers", fail_residue_check),
            ("networks", find_residue),
        ),
    )

    assert events == [
        "cleanup-failed",
        "cleanup-continued",
        "residue-check-failed",
        "residue-check-continued",
    ]
    assert outcome.errors == (
        "first-cleanup: RuntimeError: injected cleanup failure",
        "containers residue check: OSError: injected residue check failure",
    )
    assert outcome.residues == ("networks:leaked-network",)


def test_fixture_failure_reports_primary_cleanup_errors_and_residues() -> None:
    primary = ValueError("injected primary failure")
    outcome = CleanupOutcome(
        errors=("remove network: RuntimeError: injected cleanup failure",),
        residues=("containers:leaked-container",),
    )

    with pytest.raises(AssertionError) as caught:
        _raise_aggregated_fixture_failure(primary, outcome)

    assert caught.value.__cause__ is primary
    message = str(caught.value)
    assert "primary error: ValueError: injected primary failure" in message
    assert "remove network: RuntimeError: injected cleanup failure" in message
    assert "containers:leaked-container" in message


def test_runbook_pins_and_verifies_the_exact_backfill_run_and_attestation() -> None:
    runbook = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "codex"
        / "production-deployment-runbook.md"
    ).read_text(encoding="utf-8")

    required_commands = (
        "read -r -p 'Confirm exact backfill run ID: ' BACKFILL_RUN_ID",
        'gh run view "$BACKFILL_RUN_ID"',
        "--json databaseId,workflowName,headSha,status,conclusion,url",
        'gh run watch "$BACKFILL_RUN_ID"',
        "--exit-status",
        '--name "mirror-${RELEASE_TAG}-${BACKFILL_RUN_ID}"',
        "--registry ghcr",
        '--attestation "$MIRROR_DIR/mirror-attestation.json"',
        "sha256sum mirror-attestation.json > mirror-attestation.sha256",
        "sha256sum --check mirror-attestation.sha256",
    )
    for command in required_commands:
        assert command in runbook
    assert "gh run list" not in runbook
    assert "latest" not in runbook.casefold()
