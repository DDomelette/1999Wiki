#!/usr/bin/env python3
"""Backfill deferred GHCR tags from verified immutable TCR digests."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIRECTORY.parents[1]
DEPLOY_BIN = REPOSITORY_ROOT / "deploy" / "bin"
for _directory in (SCRIPT_DIRECTORY, DEPLOY_BIN):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from registry_transport import (  # noqa: E402
    CommandResult,
    Credential,
    FailureKind,
    MirrorDeferred,
    ProbeState,
    RegistryFailure,
    RetryBudget,
    SkopeoTransport,
    _TransientRegistryFailure,
    _fatal_code,
    _is_explicit_absence,
    _retry_transient,
    _sleep_after_transient,
    _validate_target,
    classify_failure,
    secure_authfile,
)
from release_identity import (  # noqa: E402
    COMPONENTS,
    REPOSITORIES,
    ManifestError,
    canonical_json,
    create_mirror_attestation,
    verify_release_manifest_bytes,
)


TCR_REGISTRY = "ccr.ccs.tencentyun.com"
TCR_NAMESPACE = "1999wiki_code"
GHCR_REGISTRY = "ghcr.io"
FAILURE_SCHEMA_VERSION = "1999wiki.mirror-backfill-failure/v1"
_DEFERRED_STATE = "ready_with_deferred_ghcr"
_ENVIRONMENT_KEYS = (
    "TCR_USERNAME",
    "TCR_PASSWORD",
    "GHCR_USERNAME",
    "GHCR_PASSWORD",
    "TCR_REGISTRY",
    "TCR_NAMESPACE",
)


class BackfillError(RuntimeError):
    """Sanitized backfill state safe for callers and failure artifacts."""

    def __init__(
        self,
        *,
        commit: str,
        workflow_run_id: str,
        phase: str,
        code: str,
        mutated: bool,
        verified_tcr: Mapping[str, str],
        verified_ghcr: Mapping[str, str],
    ) -> None:
        self.commit = commit
        self.workflow_run_id = workflow_run_id
        self.phase = phase
        self.code = code
        self.mutated = mutated
        self.verified_tcr = dict(verified_tcr)
        self.verified_ghcr = dict(verified_ghcr)
        super().__init__(f"mirror backfill failed: phase={phase} code={code}")

    def report(self) -> dict[str, object]:
        return {
            "schema_version": FAILURE_SCHEMA_VERSION,
            "commit": self.commit,
            "release_tag": f"sha-{self.commit[:7]}",
            "phase": self.phase,
            "code": self.code,
            "workflow_run_id": self.workflow_run_id,
            "mutated": self.mutated,
            "verified_tcr": dict(self.verified_tcr),
            "verified_ghcr": dict(self.verified_ghcr),
        }


def _local_failure_code(error: Exception) -> str:
    if isinstance(error, OSError):
        return "local_io_failure"
    if isinstance(error, (ValueError, ManifestError)):
        return "local_validation_failure"
    return "unexpected_local_failure"


def _validate_workflow_inputs(
    credentials: Mapping[str, Credential],
    workflow_run_id: str,
    completed_at: str,
) -> None:
    if set(credentials) != {"tcr", "ghcr"} or not all(
        isinstance(credentials.get(registry), Credential)
        for registry in ("tcr", "ghcr")
    ):
        raise ValueError("credentials must contain valid tcr and ghcr credentials")
    if (
        not isinstance(workflow_run_id, str)
        or not workflow_run_id.isascii()
        or not workflow_run_id.isdecimal()
    ):
        raise ValueError("workflow_run_id must contain ASCII decimal digits only")
    if not isinstance(completed_at, str) or not completed_at.endswith("Z"):
        raise ValueError("completed_at must be an RFC 3339 UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(completed_at[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(
            "completed_at must be an RFC 3339 UTC Z timestamp"
        ) from exc
    if parsed.isoformat().removesuffix("+00:00") != completed_at[:-1]:
        raise ValueError("completed_at must be an RFC 3339 UTC Z timestamp")


def _manifest_facts(
    manifest_raw: bytes,
    expected_commit: str,
    workflow_run_id: str,
) -> tuple[dict[str, object], dict[str, str]]:
    try:
        manifest = verify_release_manifest_bytes(manifest_raw, expected_commit)
    except (ManifestError, ValueError):
        raise BackfillError(
            commit=expected_commit,
            workflow_run_id=workflow_run_id,
            phase="manifest_verify",
            code="invalid_manifest",
            mutated=False,
            verified_tcr={},
            verified_ghcr={},
        ) from None
    if manifest["release_state"] != _DEFERRED_STATE:
        raise BackfillError(
            commit=expected_commit,
            workflow_run_id=workflow_run_id,
            phase="manifest_verify",
            code="no_backfill_required",
            mutated=False,
            verified_tcr={},
            verified_ghcr={},
        )
    images = manifest["images"]
    assert isinstance(images, Mapping)
    digests: dict[str, str] = {}
    for component in COMPONENTS:
        image = images[component]
        assert isinstance(image, Mapping)
        digest = image["digest"]
        assert isinstance(digest, str)
        digests[component] = digest
    return manifest, digests


def _source(component: str, digest: str) -> str:
    return f"docker://{REPOSITORIES['tcr'][component]}@{digest}"


def _target(component: str, commit: str) -> str:
    return (
        f"{REPOSITORIES['ghcr'][component]}:"
        f"sha-{commit[:7]}"
    )


def _immutable_ref(reference: str) -> str:
    return reference.removeprefix("docker://")


def backfill_release(
    manifest_raw: bytes,
    expected_commit: str,
    transport: SkopeoTransport,
    credentials: Mapping[str, Credential],
    workflow_run_id: str,
    completed_at: str,
) -> dict[str, object]:
    """Copy verified TCR digests to GHCR and attest only final verified refs."""
    _manifest, digests = _manifest_facts(
        manifest_raw,
        expected_commit,
        workflow_run_id,
    )
    try:
        _validate_workflow_inputs(credentials, workflow_run_id, completed_at)
    except (TypeError, ValueError):
        raise BackfillError(
            commit=expected_commit,
            workflow_run_id=workflow_run_id,
            phase="input_validate",
            code="local_validation_failure",
            mutated=False,
            verified_tcr={},
            verified_ghcr={},
        ) from None

    tcr_budget = RetryBudget(max_failures=1)
    ghcr_budget = RetryBudget(max_failures=5)
    mutated = False
    verified_tcr: dict[str, str] = {}
    verified_ghcr: dict[str, str] = {}

    def fatal(phase: str, code: str) -> BackfillError:
        return BackfillError(
            commit=expected_commit,
            workflow_run_id=workflow_run_id,
            phase=phase,
            code=code,
            mutated=mutated,
            verified_tcr=verified_tcr,
            verified_ghcr=verified_ghcr,
        )

    def call(
        operation: Callable[[], ProbeState | None],
        phase: str,
        budget: RetryBudget,
    ) -> ProbeState | None:
        try:
            return _retry_transient(
                operation,
                budget,
                time.sleep,
                transport.jitter,
            )
        except MirrorDeferred:
            raise fatal(phase, "network_failure") from None
        except RegistryFailure as exc:
            raise fatal(phase, exc.code) from None
        except BackfillError:
            raise
        except Exception as exc:
            raise fatal(phase, _local_failure_code(exc)) from None

    transport.credential = credentials["tcr"]
    call(
        lambda: transport.login(TCR_REGISTRY, tcr_budget),
        "tcr_login",
        tcr_budget,
    )
    transport.credential = credentials["ghcr"]
    call(
        lambda: transport.login(GHCR_REGISTRY, ghcr_budget),
        "ghcr_login",
        ghcr_budget,
    )

    for component in COMPONENTS:
        source = _source(component, digests[component])
        state = call(
            lambda source=source, component=component: transport.inspect_source(  # type: ignore[attr-defined]
                source,
                digests[component],
                tcr_budget,
            ),
            f"tcr_{component}_verify",
            tcr_budget,
        )
        if state is ProbeState.ABSENT:
            raise fatal(f"tcr_{component}_verify", "source_missing")
        if state is not ProbeState.PRESENT_EXPECTED:
            raise fatal(f"tcr_{component}_verify", "digest_mismatch")
        verified_tcr[component] = _immutable_ref(source)

    def probe_target(component: str, phase: str) -> ProbeState:
        state = call(
            lambda: transport.probe(
                _target(component, expected_commit),
                digests[component],
                ghcr_budget,
            ),
            phase,
            ghcr_budget,
        )
        assert isinstance(state, ProbeState)
        return state

    def ensure_target(component: str) -> None:
        nonlocal mutated
        probe_phase = f"ghcr_{component}_probe"
        copy_phase = f"ghcr_{component}_copy"
        verify_phase = f"ghcr_{component}_verify"
        state = probe_target(component, probe_phase)
        if state is ProbeState.PRESENT_EXPECTED:
            verified_ghcr[component] = (
                f"{_target(component, expected_commit)}@{digests[component]}"
            )
            return
        if state is ProbeState.PRESENT_CONFLICT:
            raise fatal(probe_phase, "digest_mismatch")

        while True:
            mutated = True
            try:
                transport.copy(
                    _source(component, digests[component]),
                    _target(component, expected_commit),
                    ghcr_budget,
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
                reconciled = probe_target(component, verify_phase)
                if reconciled is ProbeState.PRESENT_EXPECTED:
                    verified_ghcr[component] = (
                        f"{_target(component, expected_commit)}@"
                        f"{digests[component]}"
                    )
                    return
                if reconciled is ProbeState.PRESENT_CONFLICT:
                    raise fatal(verify_phase, "digest_mismatch")
                continue
            except MirrorDeferred:
                raise fatal(copy_phase, "network_failure") from None
            except RegistryFailure as exc:
                raise fatal(copy_phase, exc.code) from None
            except Exception as exc:
                raise fatal(copy_phase, _local_failure_code(exc)) from None

            verified = probe_target(component, verify_phase)
            if verified is ProbeState.PRESENT_EXPECTED:
                verified_ghcr[component] = (
                    f"{_target(component, expected_commit)}@{digests[component]}"
                )
                return
            if verified is ProbeState.PRESENT_CONFLICT:
                raise fatal(verify_phase, "digest_mismatch")
            raise fatal(verify_phase, "manifest_missing_after_copy")

    for component in COMPONENTS:
        ensure_target(component)

    final_refs: dict[str, str] = {}
    for component in COMPONENTS:
        state = probe_target(component, f"ghcr_{component}_final_verify")
        if state is ProbeState.ABSENT:
            raise fatal(
                f"ghcr_{component}_final_verify",
                "manifest_missing_after_copy",
            )
        if state is not ProbeState.PRESENT_EXPECTED:
            raise fatal(f"ghcr_{component}_final_verify", "digest_mismatch")
        final_refs[component] = (
            f"{_target(component, expected_commit)}@{digests[component]}"
        )
        verified_ghcr[component] = final_refs[component]

    try:
        return create_mirror_attestation(
            manifest_raw,
            final_refs,
            workflow_run_id,
            completed_at,
        )
    except Exception as exc:
        raise fatal("attestation_build", _local_failure_code(exc)) from None


class BackfillSkopeoTransport(SkopeoTransport):
    """Skopeo transport whose copy source is an immutable registry digest."""

    mutated: bool = False

    @staticmethod
    def _validate_source(source: str, expected_digest: str | None = None) -> None:
        permitted = {
            f"docker://{REPOSITORIES['tcr'][component]}@{digest}"
            for component, digest in (
                ("backend", expected_digest),
                ("frontend", expected_digest),
            )
            if isinstance(digest, str)
        }
        if expected_digest is not None:
            if source not in permitted:
                raise ValueError("source must be an approved TCR repository@digest")
            return
        prefixes = tuple(
            f"docker://{REPOSITORIES['tcr'][component]}@sha256:"
            for component in COMPONENTS
        )
        if not source.startswith(prefixes):
            raise ValueError("source must be an approved TCR repository@digest")
        encoded = source.rpartition("@sha256:")[2]
        if len(encoded) != 64 or any(
            character not in "0123456789abcdef" for character in encoded
        ):
            raise ValueError("source must be an approved TCR repository@digest")

    def inspect_source(
        self,
        source: str,
        expected_digest: str,
        budget: RetryBudget,
    ) -> ProbeState:
        self._validate_source(source, expected_digest)
        budget.ensure_available()
        result = self.runner(
            [
                "skopeo",
                "inspect",
                "--raw",
                "--authfile",
                str(self.authfile),
                source,
            ],
            None,
        )
        if result.returncode != 0:
            if _is_explicit_absence(result.stderr):
                return ProbeState.ABSENT
            if classify_failure(result.stderr) is FailureKind.TRANSIENT:
                budget.consume()
                raise _TransientRegistryFailure("inspect", budget.failures)
            raise RegistryFailure(
                "inspect",
                TCR_REGISTRY,
                _fatal_code(result.stderr),
            )
        actual_digest = "sha256:" + hashlib.sha256(result.stdout).hexdigest()
        if actual_digest == expected_digest:
            return ProbeState.PRESENT_EXPECTED
        return ProbeState.PRESENT_CONFLICT

    def copy(self, source: str, target: str, budget: RetryBudget) -> None:
        self._validate_source(source)
        _validate_target(target)
        self.mutated = True
        self._run(
            "copy",
            GHCR_REGISTRY,
            [
                "skopeo",
                "copy",
                "--all",
                "--preserve-digests",
                "--authfile",
                str(self.authfile),
                source,
                f"docker://{target}",
            ],
            None,
            budget,
        )


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


def _make_transport(
    authfile: Path,
    credential: Credential,
) -> BackfillSkopeoTransport:
    return BackfillSkopeoTransport(
        authfile=authfile,
        credential=credential,
        runner=_run_skopeo,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--authfile", required=True, type=Path)
    parser.add_argument("--attestation-output", required=True, type=Path)
    parser.add_argument("--failure-output", required=True, type=Path)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--completed-at", required=True)
    return parser


def _validate_distinct_paths(paths: tuple[Path, ...]) -> None:
    resolved: list[Path] = []
    for path in paths:
        resolved.append(path.resolve(strict=False))
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left == right:
                raise ValueError("backfill paths must be pairwise distinct")
            try:
                equivalent = os.path.samefile(left, right)
            except OSError:
                equivalent = False
            if equivalent:
                raise ValueError("backfill paths must be pairwise distinct")


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


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _emit_failure(
    error: BackfillError,
    attestation_output: Path,
    failure_output: Path,
) -> None:
    _remove(attestation_output)
    try:
        _write_canonical(failure_output, error.report())
    except Exception:
        _remove(failure_output)


def _error_from_attestation(
    *,
    commit: str,
    workflow_run_id: str,
    phase: str,
    code: str,
    mutated: bool,
    attestation: Mapping[str, object] | None,
) -> BackfillError:
    verified_tcr: dict[str, str] = {}
    verified_ghcr: dict[str, str] = {}
    if attestation is not None:
        images = attestation.get("images")
        if isinstance(images, Mapping):
            for component in COMPONENTS:
                image = images.get(component)
                if isinstance(image, Mapping):
                    source = image.get("source")
                    destination = image.get("destination")
                    if isinstance(source, str):
                        verified_tcr[component] = source
                    if isinstance(destination, str):
                        verified_ghcr[component] = destination
    return BackfillError(
        commit=commit,
        workflow_run_id=workflow_run_id,
        phase=phase,
        code=code,
        mutated=mutated,
        verified_tcr=verified_tcr,
        verified_ghcr=verified_ghcr,
    )


def _main_after_path_validation(args: argparse.Namespace) -> int:
    try:
        manifest_raw = args.manifest.read_bytes()
        _manifest_facts(manifest_raw, args.commit, args.workflow_run_id)
        _validate_workflow_inputs(
            {
                "tcr": Credential("validation", "validation"),
                "ghcr": Credential("validation", "validation"),
            },
            args.workflow_run_id,
            args.completed_at,
        )
    except (BackfillError, OSError, ValueError):
        return 2

    environment = {key: os.environ.get(key) for key in _ENVIRONMENT_KEYS}
    if (
        environment["TCR_REGISTRY"] != TCR_REGISTRY
        or environment["TCR_NAMESPACE"] != TCR_NAMESPACE
        or any(not environment[key] for key in _ENVIRONMENT_KEYS[:4])
    ):
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

    try:
        args.attestation_output.unlink(missing_ok=True)
        args.failure_output.unlink(missing_ok=True)
    except OSError:
        return 2

    attestation: dict[str, object] | None = None
    primary_error: BackfillError | None = None
    transport: SkopeoTransport | None = None
    try:
        try:
            with secure_authfile(args.authfile):
                transport = _make_transport(args.authfile, credentials["tcr"])
                try:
                    attestation = backfill_release(
                        manifest_raw,
                        args.commit,
                        transport,
                        credentials,
                        args.workflow_run_id,
                        args.completed_at,
                    )
                except BackfillError as exc:
                    primary_error = exc
        except Exception as exc:
            if primary_error is None:
                primary_error = _error_from_attestation(
                    commit=args.commit,
                    workflow_run_id=args.workflow_run_id,
                    phase="authfile_cleanup",
                    code=_local_failure_code(exc),
                    mutated=bool(getattr(transport, "mutated", False)),
                    attestation=attestation,
                )
    finally:
        _remove(args.authfile)

    if primary_error is not None:
        _emit_failure(
            primary_error,
            args.attestation_output,
            args.failure_output,
        )
        return 1

    assert attestation is not None
    try:
        _write_canonical(args.attestation_output, attestation)
    except Exception as exc:
        write_error = _error_from_attestation(
            commit=args.commit,
            workflow_run_id=args.workflow_run_id,
            phase="attestation_write",
            code=_local_failure_code(exc),
            mutated=bool(getattr(transport, "mutated", False)),
            attestation=attestation,
        )
        _emit_failure(
            write_error,
            args.attestation_output,
            args.failure_output,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = (
        args.manifest,
        args.authfile,
        args.attestation_output,
        args.failure_output,
    )
    try:
        _validate_distinct_paths(paths)
    except (OSError, ValueError):
        return 2
    try:
        return _main_after_path_validation(args)
    finally:
        _remove(args.authfile)


if __name__ == "__main__":
    raise SystemExit(main())
