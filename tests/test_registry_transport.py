from __future__ import annotations

import hashlib
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
DEPLOY_BIN = ROOT / "deploy" / "bin"
for directory in (SCRIPTS, DEPLOY_BIN):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from registry_transport import (  # noqa: E402
    CommandResult,
    Credential,
    FailureKind,
    MirrorDeferred,
    ProbeState,
    RegistryFailure,
    RetryBudget,
    SkopeoTransport,
    classify_failure,
    ensure_mirror_copy,
    secure_authfile,
)


SOURCE = "release.oci.tar"
TARGET = "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0"
EXPECTED_RAW = b'{"schemaVersion":2,"config":{"digest":"sha256:config"}}'
EXPECTED_DIGEST = "sha256:" + hashlib.sha256(EXPECTED_RAW).hexdigest()
OTHER_RAW = b'{"schemaVersion":2,"config":{"digest":"sha256:other"}}'


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("dial tcp: lookup ghcr.io: no such host", FailureKind.TRANSIENT),
        ("read: connection reset by peer", FailureKind.TRANSIENT),
        ("i/o timeout", FailureKind.TRANSIENT),
        ("status code: 500", FailureKind.TRANSIENT),
        ("status code: 502", FailureKind.TRANSIENT),
        ("status code: 503", FailureKind.TRANSIENT),
        ("status code: 504", FailureKind.TRANSIENT),
        ("unauthorized: authentication required", FailureKind.FATAL),
        ("denied: requested access", FailureKind.FATAL),
        ("status code: 429", FailureKind.FATAL),
        ("manifest invalid", FailureKind.FATAL),
        ("unsupported media type", FailureKind.FATAL),
        ("digest mismatch", FailureKind.FATAL),
    ],
)
def test_failure_classification(stderr: str, expected: FailureKind) -> None:
    assert classify_failure(stderr) is expected


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("StatusCode: 500", FailureKind.TRANSIENT),
        ("status-code: 502", FailureKind.TRANSIENT),
        ("HTTP 504 gateway timeout", FailureKind.TRANSIENT),
        ("reading manifest digest sha256:abc: i/o timeout", FailureKind.TRANSIENT),
        ("reading media type application/vnd.oci.image: connection reset by peer", FailureKind.TRANSIENT),
        ("blob already exists; connection reset by peer", FailureKind.TRANSIENT),
        ("lookup ghcr.io: temporary failure in name resolution", FailureKind.TRANSIENT),
        ("StatusCode: 5000", FailureKind.FATAL),
        ("status code: 401; i/o timeout", FailureKind.FATAL),
        ("forbidden: access denied; timeout", FailureKind.FATAL),
        ("status code: 409 tag conflict; timeout", FailureKind.FATAL),
        ("unauthorized: authentication required; manifest unknown", FailureKind.FATAL),
    ],
)
def test_failure_classification_gives_exact_fatal_evidence_priority(
    stderr: str, expected: FailureKind
) -> None:
    assert classify_failure(stderr) is expected


class ScriptedRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = iter(results)
        self.calls: list[tuple[list[str], bytes | None]] = []

    def __call__(self, argv: list[str], stdin: bytes | None) -> CommandResult:
        self.calls.append((argv, stdin))
        return next(self.results)


def _ok(stdout: bytes = b"") -> CommandResult:
    return CommandResult(0, stdout, "")


def _failed(stderr: str) -> CommandResult:
    return CommandResult(1, b"", stderr)


def _transport(runner: Callable[[list[str], bytes | None], CommandResult], authfile: Path) -> SkopeoTransport:
    return SkopeoTransport(
        authfile=authfile,
        credential=Credential("mirror-bot", "not-in-argv"),
        runner=runner,
        jitter=lambda: 0.0,
    )


def test_one_shared_budget_defers_on_fifth_network_failure_without_a_sixth_command(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner([_failed("i/o timeout")] * 5)
    budget = RetryBudget(max_failures=5)
    transport = _transport(runner, tmp_path / "auth.json")

    with pytest.raises(MirrorDeferred, match="deferred_after_5_network_failures"):
        ensure_mirror_copy(transport, SOURCE, TARGET, EXPECTED_DIGEST, budget, lambda _: None)

    assert len(runner.calls) == 5
    assert budget.failures == 5


def test_probe_distinguishes_explicit_absence_expected_digest_and_conflict(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner(
        [
            _failed("manifest unknown"),
            _ok(EXPECTED_RAW),
            _ok(OTHER_RAW),
        ]
    )
    transport = _transport(runner, tmp_path / "auth.json")
    budget = RetryBudget()

    assert transport.probe(TARGET, EXPECTED_DIGEST, budget) is ProbeState.ABSENT
    assert transport.probe(TARGET, EXPECTED_DIGEST, budget) is ProbeState.PRESENT_EXPECTED
    assert transport.probe(TARGET, EXPECTED_DIGEST, budget) is ProbeState.PRESENT_CONFLICT


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("manifest unknown", ProbeState.ABSENT),
        ("name unknown", ProbeState.ABSENT),
        ("no such manifest", ProbeState.ABSENT),
        ("manifest unavailable", None),
        ("unauthorized: authentication required; manifest unknown", None),
    ],
)
def test_probe_only_accepts_strict_absence_after_fatal_evidence(
    tmp_path: Path, stderr: str, expected: ProbeState | None
) -> None:
    transport = _transport(ScriptedRunner([_failed(stderr)]), tmp_path / "auth.json")

    if expected is None:
        with pytest.raises(RegistryFailure):
            transport.probe(TARGET, EXPECTED_DIGEST, RetryBudget())
    else:
        assert transport.probe(TARGET, EXPECTED_DIGEST, RetryBudget()) is expected


@pytest.mark.parametrize(
    "stderr",
    ["unauthorized: authentication required", "unexpected response from proxy"],
)
def test_probe_authentication_and_ambiguous_errors_are_stable_fatal_failures(
    tmp_path: Path, stderr: str
) -> None:
    transport = _transport(ScriptedRunner([_failed(stderr)]), tmp_path / "auth.json")

    with pytest.raises(RegistryFailure) as caught:
        transport.probe(TARGET, EXPECTED_DIGEST, RetryBudget())

    error = caught.value
    assert error.operation == "probe"
    assert error.registry == "ghcr.io"
    assert error.code in {"authentication_failed", "fatal_registry_failure"}
    assert stderr not in str(error)
    assert "not-in-argv" not in str(error)


def test_login_uses_password_stdin_and_copy_preserves_all_manifest_variants(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner([_ok(), _failed("manifest unknown"), _ok(), _ok(EXPECTED_RAW)])
    transport = _transport(runner, tmp_path / "auth.json")

    assert ensure_mirror_copy(
        transport, SOURCE, TARGET, EXPECTED_DIGEST, RetryBudget(), lambda _: None
    ) == "published"

    login_argv, login_stdin = runner.calls[0]
    assert login_argv == [
        "skopeo", "login", "--authfile", str(tmp_path / "auth.json"),
        "--username", "mirror-bot", "--password-stdin", "ghcr.io",
    ]
    assert login_stdin == b"not-in-argv"
    assert all("not-in-argv" not in argument for argv, _ in runner.calls for argument in argv)
    copy_argv, copy_stdin = runner.calls[2]
    assert copy_argv == [
        "skopeo", "copy", "--all", "--preserve-digests", "--authfile",
        str(tmp_path / "auth.json"), "oci-archive:release.oci.tar", f"docker://{TARGET}",
    ]
    assert copy_stdin is None


def test_uncertain_copy_is_reconciled_by_an_exact_destination_manifest(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner(
        [_ok(), _failed("manifest unknown"), _failed("i/o timeout"), _ok(EXPECTED_RAW)]
    )
    transport = _transport(runner, tmp_path / "auth.json")

    assert ensure_mirror_copy(
        transport, SOURCE, TARGET, EXPECTED_DIGEST, RetryBudget(), lambda _: None
    ) == "published"
    assert [call[0][1] for call in runner.calls].count("copy") == 1


def test_uncertain_copy_retries_only_after_reconciliation_proves_absence(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner(
        [
            _ok(),
            _failed("manifest unknown"),
            _failed("i/o timeout"),
            _failed("name unknown"),
            _ok(),
            _ok(EXPECTED_RAW),
        ]
    )
    transport = _transport(runner, tmp_path / "auth.json")

    assert ensure_mirror_copy(
        transport, SOURCE, TARGET, EXPECTED_DIGEST, RetryBudget(), lambda _: None
    ) == "published"
    assert [call[0][1] for call in runner.calls].count("copy") == 2


def test_interleaved_copy_and_probe_failures_back_off_once_in_global_order(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner(
        [
            _ok(),
            _failed("manifest unknown"),
            _failed("i/o timeout"),
            _failed("i/o timeout"),
            _failed("name unknown"),
            _ok(),
            _ok(EXPECTED_RAW),
        ]
    )
    transport = _transport(runner, tmp_path / "auth.json")
    delays: list[float] = []

    assert ensure_mirror_copy(
        transport, SOURCE, TARGET, EXPECTED_DIGEST, RetryBudget(), delays.append
    ) == "published"

    assert delays == [1.0, 2.0]


def test_shared_budget_spans_login_probe_copy_and_verify_and_blocks_reuse(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner(
        [
            _failed("i/o timeout"),
            _ok(),
            _failed("i/o timeout"),
            _failed("manifest unknown"),
            _failed("i/o timeout"),
            _failed("name unknown"),
            _ok(),
            _failed("i/o timeout"),
            _ok(EXPECTED_RAW),
            _failed("i/o timeout"),
        ]
    )
    transport = _transport(runner, tmp_path / "auth.json")
    budget = RetryBudget()
    delays: list[float] = []

    assert ensure_mirror_copy(
        transport, SOURCE, TARGET, EXPECTED_DIGEST, budget, delays.append
    ) == "published"
    assert budget.failures == 4
    assert delays == [1.0, 2.0, 4.0, 8.0]

    with pytest.raises(MirrorDeferred, match="deferred_after_5_network_failures"):
        ensure_mirror_copy(transport, SOURCE, TARGET, EXPECTED_DIGEST, budget, delays.append)
    calls_after_deferred = len(runner.calls)

    with pytest.raises(MirrorDeferred, match="deferred_after_5_network_failures"):
        transport.probe(TARGET, EXPECTED_DIGEST, budget)
    assert len(runner.calls) == calls_after_deferred
    assert delays == [1.0, 2.0, 4.0, 8.0]


def test_exact_digest_conflict_fails_without_copying(tmp_path: Path) -> None:
    runner = ScriptedRunner([_ok(), _ok(OTHER_RAW)])
    transport = _transport(runner, tmp_path / "auth.json")

    with pytest.raises(RegistryFailure) as caught:
        ensure_mirror_copy(
            transport, SOURCE, TARGET, EXPECTED_DIGEST, RetryBudget(), lambda _: None
        )

    assert caught.value.code == "digest_conflict"
    assert [call[0][1] for call in runner.calls].count("copy") == 0


def test_secure_authfile_uses_private_mode_and_always_removes_the_file(tmp_path: Path) -> None:
    authfile = tmp_path / "nested" / "auth.json"

    with secure_authfile(authfile) as created:
        assert created == authfile
        assert created.is_file()
        if os.name != "nt":
            assert stat.S_IMODE(created.stat().st_mode) == 0o600

    assert not authfile.exists()
