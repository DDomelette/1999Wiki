from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest


SKOPEO_IMAGE = "quay.io/skopeo/stable:v1.19.0"


@dataclass(frozen=True)
class CopyEvidence:
    source_digest: str
    first_registry_digest: str
    second_registry_digest: str
    conflict_was_rejected: bool
    remaining_resources: tuple[str, ...]


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
        f"registry-a:5000/{repository}:sha-fixture",
        f"registry-b:5000/{repository}:sha-fixture",
    )
    context = tmp_path / "fixture-context"
    archive = tmp_path / "fixture.oci"
    skopeo_container_names: list[str] = []
    failure: BaseException | None = None
    source_digest = ""
    first_registry_digest = ""
    second_registry_digest = ""
    conflict_was_rejected = False
    remaining_resources: tuple[str, ...] = ()

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

    def inspect_target(target: str, *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return skopeo(
            "inspect",
            "--raw",
            "--tls-verify=false",
            f"docker://{target}",
            check=check,
        )

    def refuse_conflict_or_accept_exact(target: str, expected_digest: str) -> bool:
        inspected = inspect_target(target)
        actual_digest = _digest(inspected.stdout)
        if actual_digest == expected_digest:
            return False
        raise RuntimeError(
            f"refusing conflicting tag: expected {expected_digest}, observed {actual_digest}"
        )

    try:
        context.mkdir()
        (context / "Dockerfile").write_text(
            "FROM scratch\nCOPY payload.txt /payload.txt\n",
            encoding="utf-8",
            newline="\n",
        )
        (context / "payload.txt").write_text(
            "dual-registry-fixture\n",
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

        assert refuse_conflict_or_accept_exact(targets[0], source_digest) is False
        try:
            refuse_conflict_or_accept_exact(targets[0], "sha256:" + ("0" * 64))
        except RuntimeError as exc:
            conflict_was_rejected = "refusing conflicting tag" in str(exc)
        else:
            raise AssertionError("a conflicting immutable tag was not rejected")
    except BaseException as exc:
        failure = exc
    finally:
        for name in docker_ps_names(prefix):
            _run(["docker", "container", "rm", "--force", name], check=False)
        for name in docker_network_names(prefix):
            _run(["docker", "network", "rm", name], check=False)
        for reference in docker_image_refs(repository_prefix):
            _run(["docker", "image", "rm", reference], check=False)
        archive.unlink(missing_ok=True)
        shutil.rmtree(context, ignore_errors=True)

        remaining = [
            *docker_ps_names(prefix),
            *docker_network_names(prefix),
            *docker_image_refs(repository_prefix),
        ]
        if archive.exists():
            remaining.append(str(archive))
        if context.exists():
            remaining.append(str(context))
        remaining_resources = tuple(remaining)

    if remaining_resources:
        cleanup_error = AssertionError(
            f"dual-registry fixture leaked resources: {remaining_resources!r}"
        )
        if failure is not None:
            raise cleanup_error from failure
        raise cleanup_error
    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)

    return CopyEvidence(
        source_digest=source_digest,
        first_registry_digest=first_registry_digest,
        second_registry_digest=second_registry_digest,
        conflict_was_rejected=conflict_was_rejected,
        remaining_resources=remaining_resources,
    )


@pytest.mark.registry_integration
def test_one_oci_archive_copies_to_two_registries_with_one_digest(
    tmp_path: Path,
) -> None:
    evidence = _run_dual_registry_fixture(tmp_path)
    assert evidence.source_digest == evidence.first_registry_digest
    assert evidence.source_digest == evidence.second_registry_digest
    assert evidence.conflict_was_rejected is True
    assert evidence.remaining_resources == ()
