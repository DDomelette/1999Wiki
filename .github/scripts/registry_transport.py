#!/usr/bin/env python3
"""Digest-preserving OCI archive transport for the release mirror workflow."""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import os
import random
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIRECTORY.parents[1]
DEPLOY_BIN = REPOSITORY_ROOT / "deploy" / "bin"
for _directory in (SCRIPT_DIRECTORY, DEPLOY_BIN):
    import sys

    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from release_identity import (  # noqa: E402
    COMPONENTS,
    REPOSITORIES,
    ManifestError,
    _release_tag,
    _validate_commit,
    _validate_digest as _validate_release_digest,
)


class FailureKind(enum.Enum):
    TRANSIENT = "transient"
    FATAL = "fatal"


class ProbeState(enum.Enum):
    ABSENT = "absent"
    PRESENT_EXPECTED = "present_expected"
    PRESENT_CONFLICT = "present_conflict"


class RegistryFailure(RuntimeError):
    """A non-retryable registry result with no registry output attached."""

    def __init__(self, operation: str, registry: str, code: str) -> None:
        self.operation = operation
        self.registry = registry
        self.code = code
        super().__init__(
            f"registry failure: operation={operation} registry={registry} code={code}"
        )


class MirrorDeferred(RuntimeError):
    """The workflow-wide allowance for transient registry failures was spent."""


class _TransientRegistryFailure(RuntimeError):
    def __init__(self, operation: str, failure_number: int) -> None:
        self.operation = operation
        self.failure_number = failure_number
        super().__init__(operation)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: str


@dataclass(frozen=True)
class Credential:
    username: str
    password: str = dataclasses.field(repr=False)


@dataclass
class RetryBudget:
    max_failures: int = 5
    failures: int = 0

    def ensure_available(self) -> None:
        if self.failures >= self.max_failures:
            raise MirrorDeferred("deferred_after_5_network_failures")

    def consume(self) -> None:
        self.ensure_available()
        self.failures += 1
        if self.failures >= self.max_failures:
            raise MirrorDeferred("deferred_after_5_network_failures")


_FATAL_MARKERS = (
    "unauthorized",
    "forbidden",
    "authentication",
    "permission",
    "access denied",
    "denied",
    "tag conflict",
    "tag already exists",
    "already exists",
    "manifest invalid",
    "invalid manifest",
    "manifest rejected",
    "unsupported media type",
    "media type",
    "digest mismatch",
    "digest",
)
_TRANSIENT_MARKERS = (
    "no such host",
    "connection reset by peer",
    "connection refused",
    "network is unreachable",
    "dial tcp",
    "i/o timeout",
    "timeout",
)
_ABSENT_MARKERS = ("manifest unknown", "name unknown", "no such manifest")
_STATUS_CODE_RE = re.compile(
    r"\b(?:status[-_\s]*code|http(?:/\d(?:\.\d)?)?)\s*:?\s*(\d+)\b",
    re.IGNORECASE,
)


def _status_codes(stderr: str) -> set[int]:
    return {int(match.group(1)) for match in _STATUS_CODE_RE.finditer(stderr)}


def _has_fatal_evidence(stderr: str) -> bool:
    evidence = stderr.casefold()
    return any(marker in evidence for marker in _FATAL_MARKERS) or any(
        400 <= status <= 499 for status in _status_codes(stderr)
    )


def classify_failure(stderr: str) -> FailureKind:
    """Classify only known network failures as transient, after fatal evidence."""
    if _has_fatal_evidence(stderr):
        return FailureKind.FATAL
    evidence = stderr.casefold()
    if any(marker in evidence for marker in _TRANSIENT_MARKERS):
        return FailureKind.TRANSIENT
    if any(status in {500, 502, 503, 504} for status in _status_codes(stderr)):
        return FailureKind.TRANSIENT
    return FailureKind.FATAL


def _is_explicit_absence(stderr: str) -> bool:
    evidence = stderr.casefold()
    return any(marker in evidence for marker in _ABSENT_MARKERS)


def _registry(reference: str) -> str:
    return reference.split("/", 1)[0]


def _validate_target(reference: str) -> None:
    repository, separator, tag = reference.rpartition(":")
    canonical_prefix = _release_tag("0" * 40)[:-7]
    candidate_commit = tag.removeprefix(canonical_prefix) + "0" * 33
    try:
        _validate_commit(candidate_commit)
    except ManifestError as exc:
        raise ValueError("target must use the canonical release tag grammar") from exc
    if not separator or _release_tag(candidate_commit) != tag:
        raise ValueError("target must use the canonical release tag grammar")
    permitted = {
        registered
        for registry in REPOSITORIES.values()
        for component in COMPONENTS
        for registered in (registry[component],)
    }
    if repository not in permitted:
        raise ValueError("target repository is not a release registry repository")


def _validate_digest(digest: str) -> None:
    try:
        _validate_release_digest(digest, "expected")
    except ManifestError as exc:
        raise ValueError("expected digest must use the canonical sha256 grammar") from exc


def _fatal_code(stderr: str) -> str:
    evidence = stderr.casefold()
    if any(marker in evidence for marker in ("unauthorized", "forbidden", "authentication", "permission", "denied")) or any(
        status in {401, 403} for status in _status_codes(stderr)
    ):
        return "authentication_failed"
    return "fatal_registry_failure"


@contextmanager
def secure_authfile(path: Path) -> Iterator[Path]:
    """Create a private, empty authfile and remove it regardless of outcome."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(descriptor)
    path.chmod(0o600)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


Runner = Callable[[list[str], bytes | None], CommandResult]


@dataclass
class SkopeoTransport:
    authfile: Path
    credential: Credential
    runner: Runner
    jitter: Callable[[], float] = lambda: random.uniform(0.0, 0.5)

    def _run(
        self,
        operation: str,
        registry: str,
        argv: list[str],
        stdin: bytes | None,
        budget: RetryBudget,
    ) -> CommandResult:
        budget.ensure_available()
        result = self.runner(argv, stdin)
        if result.returncode == 0:
            return result
        if classify_failure(result.stderr) is FailureKind.TRANSIENT:
            budget.consume()
            raise _TransientRegistryFailure(operation, budget.failures)
        raise RegistryFailure(operation, registry, _fatal_code(result.stderr))

    def login(self, registry: str, budget: RetryBudget) -> None:
        self._run(
            "login",
            registry,
            [
                "skopeo",
                "login",
                "--authfile",
                str(self.authfile),
                "--username",
                self.credential.username,
                "--password-stdin",
                registry,
            ],
            self.credential.password.encode("utf-8"),
            budget,
        )

    def probe(
        self, target: str, expected_digest: str, budget: RetryBudget
    ) -> ProbeState:
        _validate_target(target)
        _validate_digest(expected_digest)
        registry = _registry(target)
        budget.ensure_available()
        result = self.runner(
            [
                "skopeo",
                "inspect",
                "--raw",
                "--authfile",
                str(self.authfile),
                f"docker://{target}",
            ],
            None,
        )
        if result.returncode != 0:
            if _has_fatal_evidence(result.stderr):
                raise RegistryFailure("probe", registry, _fatal_code(result.stderr))
            if _is_explicit_absence(result.stderr):
                return ProbeState.ABSENT
            if classify_failure(result.stderr) is FailureKind.TRANSIENT:
                budget.consume()
                raise _TransientRegistryFailure("probe", budget.failures)
            raise RegistryFailure("probe", registry, _fatal_code(result.stderr))
        actual_digest = "sha256:" + hashlib.sha256(result.stdout).hexdigest()
        if actual_digest == expected_digest:
            return ProbeState.PRESENT_EXPECTED
        return ProbeState.PRESENT_CONFLICT

    def copy(self, source: str, target: str, budget: RetryBudget) -> None:
        _validate_target(target)
        source_ref = source if source.startswith("oci-archive:") else f"oci-archive:{source}"
        self._run(
            "copy",
            _registry(target),
            [
                "skopeo",
                "copy",
                "--all",
                "--preserve-digests",
                "--authfile",
                str(self.authfile),
                source_ref,
                f"docker://{target}",
            ],
            None,
            budget,
        )


def _sleep_after_transient(
    failure_number: int, sleep: Callable[[float], None], jitter: Callable[[], float]
) -> None:
    delay = min(2 ** (failure_number - 1), 8)
    extra = jitter()
    if not 0.0 <= extra <= 0.5:
        raise ValueError("jitter must be in [0.0, 0.5]")
    sleep(float(delay) + extra)


def _retry_transient(
    operation: Callable[[], ProbeState | None],
    budget: RetryBudget,
    sleep: Callable[[float], None],
    jitter: Callable[[], float],
) -> ProbeState | None:
    while True:
        try:
            return operation()
        except _TransientRegistryFailure as transient:
            _sleep_after_transient(transient.failure_number, sleep, jitter)


def _raise_conflict(target: str) -> None:
    raise RegistryFailure("probe", _registry(target), "digest_conflict")


def ensure_mirror_copy(
    transport: SkopeoTransport,
    source: str,
    target: str,
    expected_digest: str,
    budget: RetryBudget,
    sleep: Callable[[float], None],
) -> str:
    """Mirror an OCI archive, reconciling an uncertain copy before repeating it."""
    _validate_target(target)
    _validate_digest(expected_digest)
    registry = _registry(target)
    _retry_transient(
        lambda: transport.login(registry, budget), budget, sleep, transport.jitter
    )

    initial = _retry_transient(
        lambda: transport.probe(target, expected_digest, budget),
        budget,
        sleep,
        transport.jitter,
    )
    assert isinstance(initial, ProbeState)
    if initial is ProbeState.PRESENT_EXPECTED:
        return "published"
    if initial is ProbeState.PRESENT_CONFLICT:
        _raise_conflict(target)

    while True:
        try:
            transport.copy(source, target, budget)
        except _TransientRegistryFailure as transient:
            _sleep_after_transient(transient.failure_number, sleep, transport.jitter)
            reconciled = _retry_transient(
                lambda: transport.probe(target, expected_digest, budget),
                budget,
                sleep,
                transport.jitter,
            )
            assert isinstance(reconciled, ProbeState)
            if reconciled is ProbeState.PRESENT_EXPECTED:
                return "published"
            if reconciled is ProbeState.PRESENT_CONFLICT:
                _raise_conflict(target)
            continue

        verified = _retry_transient(
            lambda: transport.probe(target, expected_digest, budget),
            budget,
            sleep,
            transport.jitter,
        )
        assert isinstance(verified, ProbeState)
        if verified is ProbeState.PRESENT_EXPECTED:
            return "published"
        if verified is ProbeState.PRESENT_CONFLICT:
            _raise_conflict(target)
        raise RegistryFailure("verify", registry, "manifest_missing_after_copy")
