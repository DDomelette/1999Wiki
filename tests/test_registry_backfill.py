from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict, deque
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
DEPLOY_BIN = ROOT / "deploy" / "bin"
for directory in (SCRIPTS, DEPLOY_BIN):
    sys.path.insert(0, str(directory))

import backfill_ghcr  # noqa: E402
from backfill_ghcr import BackfillError, backfill_release, main  # noqa: E402
from registry_transport import (  # noqa: E402
    CommandResult,
    Credential,
    ProbeState,
    RegistryFailure,
    RetryBudget,
    _TransientRegistryFailure,
)
from release_identity import (  # noqa: E402
    canonical_json,
    create_release_manifest,
    verify_mirror_attestation,
)


COMMIT = "abcdef0123456789abcdef0123456789abcdef01"
BACKEND_DIGEST = "sha256:" + "a" * 64
FRONTEND_DIGEST = "sha256:" + "b" * 64
WORKFLOW_RUN_ID = "123456790"
COMPLETED_AT = "2026-07-26T12:30:00Z"
TCR_REGISTRY = "ccr.ccs.tencentyun.com"
GHCR_REGISTRY = "ghcr.io"
TCR_SOURCES = {
    "backend": (
        "docker://ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-backend@" + BACKEND_DIGEST
    ),
    "frontend": (
        "docker://ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-frontend@" + FRONTEND_DIGEST
    ),
}
GHCR_TARGETS = {
    "backend": "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0",
    "frontend": "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0",
}
GHCR_REFS = {
    component: f"{GHCR_TARGETS[component]}@{digest}"
    for component, digest in {
        "backend": BACKEND_DIGEST,
        "frontend": FRONTEND_DIGEST,
    }.items()
}
CREDENTIALS = {
    "tcr": Credential("tcr-user", "tcr-secret"),
    "ghcr": Credential("ghcr-user", "ghcr-secret"),
}


def deferred_manifest_raw() -> bytes:
    return canonical_json(
        create_release_manifest(
            COMMIT,
            {"backend": BACKEND_DIGEST, "frontend": FRONTEND_DIGEST},
            {
                "backend": "deferred_after_5_network_failures",
                "frontend": "deferred_after_5_network_failures",
            },
        )
    )


class FakeBackfillTransport:
    """Registry-free state machine at the Skopeo transport boundary."""

    jitter = staticmethod(lambda: 0.0)

    def __init__(
        self,
        scripted: Mapping[str, list[object]] | None = None,
        *,
        ghcr_states: Mapping[str, ProbeState] | None = None,
    ) -> None:
        self.credential = CREDENTIALS["tcr"]
        self.calls: list[str] = []
        self.copy_sources: list[str] = []
        self.budget_ids: dict[str, list[int]] = defaultdict(list)
        self.scripted: dict[str, deque[object]] = defaultdict(deque)
        for phase, outcomes in (scripted or {}).items():
            self.scripted[phase].extend(outcomes)
        self.ghcr_states = {
            "backend": ProbeState.ABSENT,
            "frontend": ProbeState.PRESENT_EXPECTED,
            **(ghcr_states or {}),
        }

    @staticmethod
    def _component(reference: str) -> str:
        return "backend" if "1999wiki-backend" in reference else "frontend"

    def _result(
        self,
        phase: str,
        budget: RetryBudget,
        default: object,
    ) -> object:
        outcome = self.scripted[phase].popleft() if self.scripted[phase] else default
        if outcome == "transient":
            budget.consume()
            raise _TransientRegistryFailure(phase, budget.failures)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def login(self, registry: str, budget: RetryBudget) -> None:
        alias = "tcr" if registry == TCR_REGISTRY else "ghcr"
        phase = f"login:{alias}"
        self.calls.append(phase)
        self.budget_ids[alias].append(id(budget))
        self._result(phase, budget, None)

    def inspect_source(
        self,
        source: str,
        expected_digest: str,
        budget: RetryBudget,
    ) -> ProbeState:
        component = self._component(source)
        phase = f"inspect:tcr:{component}"
        self.calls.append(phase)
        self.budget_ids["tcr"].append(id(budget))
        assert source == TCR_SOURCES[component]
        expected = BACKEND_DIGEST if component == "backend" else FRONTEND_DIGEST
        assert expected_digest == expected
        return self._result(  # type: ignore[return-value]
            phase,
            budget,
            ProbeState.PRESENT_EXPECTED,
        )

    def probe(
        self,
        target: str,
        expected_digest: str,
        budget: RetryBudget,
    ) -> ProbeState:
        component = self._component(target)
        phase = f"probe:ghcr:{component}"
        self.calls.append(phase)
        self.budget_ids["ghcr"].append(id(budget))
        assert target == GHCR_TARGETS[component]
        expected = BACKEND_DIGEST if component == "backend" else FRONTEND_DIGEST
        assert expected_digest == expected
        return self._result(phase, budget, self.ghcr_states[component])  # type: ignore[return-value]

    def copy(self, source: str, target: str, budget: RetryBudget) -> None:
        component = self._component(target)
        phase = f"copy:ghcr:{component}"
        self.calls.append(phase)
        self.budget_ids["ghcr"].append(id(budget))
        self.copy_sources.append(source)
        assert source == TCR_SOURCES[component]
        assert target == GHCR_TARGETS[component]
        try:
            self._result(phase, budget, None)
        except _TransientRegistryFailure:
            # The registry accepted the copy but the client lost the response.
            self.ghcr_states[component] = ProbeState.PRESENT_EXPECTED
            raise
        self.ghcr_states[component] = ProbeState.PRESENT_EXPECTED


@pytest.fixture(autouse=True)
def no_real_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backfill_ghcr.time, "sleep", lambda _delay: None)


def run_backfill(transport: FakeBackfillTransport) -> dict[str, object]:
    return backfill_release(
        deferred_manifest_raw(),
        COMMIT,
        transport,  # type: ignore[arg-type]
        CREDENTIALS,
        WORKFLOW_RUN_ID,
        COMPLETED_AT,
    )


def test_backfill_uses_verified_digest_sources_and_attests_only_after_final_verifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeBackfillTransport()
    real_create = backfill_ghcr.create_mirror_attestation
    creator_calls: list[tuple[bytes, dict[str, str], list[str]]] = []

    def record_create(
        manifest_raw: bytes,
        ghcr_refs: Mapping[str, str],
        workflow_run_id: str,
        completed_at: str,
    ) -> dict[str, object]:
        creator_calls.append((manifest_raw, dict(ghcr_refs), list(transport.calls)))
        return real_create(
            manifest_raw,
            ghcr_refs,
            workflow_run_id,
            completed_at,
        )

    monkeypatch.setattr(backfill_ghcr, "create_mirror_attestation", record_create)

    attestation = run_backfill(transport)

    assert transport.calls == [
        "login:tcr",
        "login:ghcr",
        "inspect:tcr:backend",
        "inspect:tcr:frontend",
        "probe:ghcr:backend",
        "copy:ghcr:backend",
        "probe:ghcr:backend",
        "probe:ghcr:frontend",
        "probe:ghcr:backend",
        "probe:ghcr:frontend",
    ]
    assert transport.copy_sources == [TCR_SOURCES["backend"]]
    assert len(set(transport.budget_ids["ghcr"])) == 1
    assert creator_calls == [
        (deferred_manifest_raw(), GHCR_REFS, transport.calls)
    ]
    assert attestation["manifest_sha256"] == (
        "sha256:" + hashlib.sha256(deferred_manifest_raw()).hexdigest()
    )
    assert (
        verify_mirror_attestation(
            deferred_manifest_raw(),
            attestation,
            COMMIT,
        )
        == attestation
    )


def test_uncertain_copy_is_reconciled_before_any_second_copy() -> None:
    transport = FakeBackfillTransport(
        {"copy:ghcr:backend": ["transient"]},
    )
    # The first reconciliation observes the server-side copy despite the
    # transient client result.
    transport.scripted["probe:ghcr:backend"].extend(
        [ProbeState.ABSENT, ProbeState.PRESENT_EXPECTED]
    )

    run_backfill(transport)

    assert transport.calls.count("copy:ghcr:backend") == 1
    copy_index = transport.calls.index("copy:ghcr:backend")
    assert transport.calls[copy_index + 1] == "probe:ghcr:backend"


def test_already_exact_targets_are_idempotently_accepted_without_copy() -> None:
    transport = FakeBackfillTransport(
        ghcr_states={
            "backend": ProbeState.PRESENT_EXPECTED,
            "frontend": ProbeState.PRESENT_EXPECTED,
        }
    )

    attestation = run_backfill(transport)

    assert not any(call.startswith("copy:") for call in transport.calls)
    assert attestation["status"] == "completed"


@pytest.mark.parametrize(
    ("manifest_raw", "expected_commit", "expected_code"),
    [
        (
            canonical_json(
                create_release_manifest(
                    COMMIT,
                    {
                        "backend": BACKEND_DIGEST,
                        "frontend": FRONTEND_DIGEST,
                    },
                    {"backend": "published", "frontend": "published"},
                )
            ),
            COMMIT,
            "no_backfill_required",
        ),
        (deferred_manifest_raw().rstrip(b"\n"), COMMIT, "invalid_manifest"),
        (b"{not-json}\n", COMMIT, "invalid_manifest"),
        (deferred_manifest_raw(), "0" * 40, "invalid_manifest"),
    ],
)
def test_invalid_ready_noncanonical_or_wrong_commit_is_rejected_before_login(
    manifest_raw: bytes,
    expected_commit: str,
    expected_code: str,
) -> None:
    transport = FakeBackfillTransport()

    with pytest.raises(BackfillError) as caught:
        backfill_release(
            manifest_raw,
            expected_commit,
            transport,  # type: ignore[arg-type]
            CREDENTIALS,
            WORKFLOW_RUN_ID,
            COMPLETED_AT,
        )

    assert caught.value.phase == "manifest_verify"
    assert caught.value.code == expected_code
    assert caught.value.mutated is False
    assert transport.calls == []


@pytest.mark.parametrize(
    ("component", "state"),
    [
        ("backend", ProbeState.ABSENT),
        ("frontend", ProbeState.PRESENT_CONFLICT),
    ],
)
def test_missing_or_mismatched_tcr_source_stops_before_any_ghcr_target(
    component: str,
    state: ProbeState,
) -> None:
    transport = FakeBackfillTransport(
        {f"inspect:tcr:{component}": [state]},
    )

    with pytest.raises(BackfillError) as caught:
        run_backfill(transport)

    assert caught.value.phase == f"tcr_{component}_verify"
    assert caught.value.code == (
        "source_missing" if state is ProbeState.ABSENT else "digest_mismatch"
    )
    assert not any(
        call.startswith(("probe:ghcr", "copy:ghcr"))
        for call in transport.calls
    )
    assert caught.value.mutated is False


def test_existing_different_ghcr_digest_is_fatal_without_copy_or_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeBackfillTransport(
        ghcr_states={"backend": ProbeState.PRESENT_CONFLICT}
    )
    created = False

    def unexpected_create(*_args, **_kwargs):
        nonlocal created
        created = True
        raise AssertionError("attestation must not be created")

    monkeypatch.setattr(
        backfill_ghcr,
        "create_mirror_attestation",
        unexpected_create,
    )

    with pytest.raises(BackfillError) as caught:
        run_backfill(transport)

    assert caught.value.phase == "ghcr_backend_probe"
    assert caught.value.code == "digest_mismatch"
    assert transport.copy_sources == []
    assert created is False


@pytest.mark.parametrize(
    ("phase", "failure", "expected_phase"),
    [
        (
            "login:ghcr",
            RegistryFailure("login", GHCR_REGISTRY, "authentication_failed"),
            "ghcr_login",
        ),
        (
            "probe:ghcr:backend",
            RegistryFailure("probe", GHCR_REGISTRY, "fatal_registry_failure"),
            "ghcr_backend_probe",
        ),
        (
            "copy:ghcr:backend",
            RegistryFailure("copy", GHCR_REGISTRY, "fatal_registry_failure"),
            "ghcr_backend_copy",
        ),
    ],
)
def test_fatal_ghcr_failures_are_sanitized_and_never_attested(
    phase: str,
    failure: RegistryFailure,
    expected_phase: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeBackfillTransport({phase: [failure]})
    monkeypatch.setattr(
        backfill_ghcr,
        "create_mirror_attestation",
        lambda *_args, **_kwargs: pytest.fail("attestation must not be created"),
    )

    with pytest.raises(BackfillError) as caught:
        run_backfill(transport)

    assert caught.value.phase == expected_phase
    assert caught.value.code == failure.code
    assert "stderr" not in str(caught.value)
    assert "secret" not in str(caught.value)


def test_fifth_shared_ghcr_transient_has_no_sixth_attempt_or_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeBackfillTransport({"login:ghcr": ["transient"] * 6})
    monkeypatch.setattr(
        backfill_ghcr,
        "create_mirror_attestation",
        lambda *_args, **_kwargs: pytest.fail("attestation must not be created"),
    )

    with pytest.raises(BackfillError) as caught:
        run_backfill(transport)

    assert caught.value.phase == "ghcr_login"
    assert caught.value.code == "network_failure"
    assert transport.calls.count("login:ghcr") == 5
    assert caught.value.mutated is False


@pytest.mark.parametrize(
    ("final_outcomes", "expected_code"),
    [
        ([ProbeState.ABSENT], "manifest_missing_after_copy"),
        ([ProbeState.PRESENT_CONFLICT], "digest_mismatch"),
        (
            [
                RegistryFailure(
                    "probe",
                    GHCR_REGISTRY,
                    "fatal_registry_failure",
                )
            ],
            "fatal_registry_failure",
        ),
        (["transient"] * 5, "network_failure"),
    ],
    ids=["absent", "conflict", "fatal", "transient-exhausted"],
)
def test_failed_backend_final_verify_removes_its_stale_verified_ref(
    final_outcomes: list[object],
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeBackfillTransport(
        ghcr_states={
            "backend": ProbeState.PRESENT_EXPECTED,
            "frontend": ProbeState.PRESENT_EXPECTED,
        }
    )
    transport.scripted["probe:ghcr:backend"].extend(
        [ProbeState.PRESENT_EXPECTED, *final_outcomes]
    )
    monkeypatch.setattr(
        backfill_ghcr,
        "create_mirror_attestation",
        lambda *_args, **_kwargs: pytest.fail("attestation must not be created"),
    )

    with pytest.raises(BackfillError) as caught:
        run_backfill(transport)

    assert caught.value.phase == "ghcr_backend_final_verify"
    assert caught.value.code == expected_code
    assert caught.value.report()["verified_ghcr"] == {
        "frontend": GHCR_REFS["frontend"],
    }


def _cli_args(tmp_path: Path, manifest_path: Path) -> list[str]:
    return [
        "--manifest",
        str(manifest_path),
        "--commit",
        COMMIT,
        "--authfile",
        str(tmp_path / "auth.json"),
        "--attestation-output",
        str(tmp_path / "mirror-attestation.json"),
        "--failure-output",
        str(tmp_path / "mirror-failure.json"),
        "--workflow-run-id",
        WORKFLOW_RUN_ID,
        "--completed-at",
        COMPLETED_AT,
    ]


def _override_arg(args: list[str], option: str, path: Path) -> list[str]:
    result = list(args)
    result[result.index(option) + 1] = str(path)
    return result


def _set_cli_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "TCR_USERNAME": "tcr-user",
        "TCR_PASSWORD": "tcr-secret",
        "GHCR_USERNAME": "ghcr-user",
        "GHCR_PASSWORD": "ghcr-secret",
        "TCR_REGISTRY": TCR_REGISTRY,
        "TCR_NAMESPACE": "1999wiki_code",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_cli_preserves_manifest_bytes_writes_attestation_and_removes_authfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "release-manifest.json"
    raw = deferred_manifest_raw()
    manifest_path.write_bytes(raw)
    transport = FakeBackfillTransport()
    _set_cli_environment(monkeypatch)
    monkeypatch.setattr(
        backfill_ghcr,
        "_make_transport",
        lambda authfile, credential: transport,
    )

    assert main(_cli_args(tmp_path, manifest_path)) == 0

    assert manifest_path.read_bytes() == raw
    attestation_raw = (tmp_path / "mirror-attestation.json").read_bytes()
    attestation = json.loads(attestation_raw)
    assert attestation_raw == canonical_json(attestation)
    assert attestation["manifest_sha256"] == (
        "sha256:" + hashlib.sha256(raw).hexdigest()
    )
    assert not (tmp_path / "mirror-failure.json").exists()
    assert not (tmp_path / "auth.json").exists()


@pytest.mark.parametrize(
    "collision",
    ["resolved_alias", "hardlink", "same_outputs", "auth_is_manifest"],
)
def test_cli_rejects_manifest_equivalent_or_colliding_paths_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision: str,
) -> None:
    manifest_path = tmp_path / "release-manifest.json"
    raw = deferred_manifest_raw()
    manifest_path.write_bytes(raw)
    watched_output = tmp_path / "watched-output.json"
    watched_output.write_bytes(b"preexisting")
    args = _cli_args(tmp_path, manifest_path)
    if collision == "resolved_alias":
        nested = tmp_path / "nested"
        nested.mkdir()
        args = _override_arg(
            args,
            "--attestation-output",
            nested / ".." / manifest_path.name,
        )
    elif collision == "hardlink":
        hardlink = tmp_path / "manifest-hardlink.json"
        os.link(manifest_path, hardlink)
        args = _override_arg(args, "--failure-output", hardlink)
    elif collision == "same_outputs":
        args = _override_arg(args, "--attestation-output", watched_output)
        args = _override_arg(args, "--failure-output", watched_output)
    else:
        args = _override_arg(args, "--authfile", manifest_path)
    _set_cli_environment(monkeypatch)
    transport = FakeBackfillTransport()
    monkeypatch.setattr(
        backfill_ghcr,
        "_make_transport",
        lambda authfile, credential: transport,
    )

    assert main(args) == 2

    assert transport.calls == []
    assert manifest_path.read_bytes() == raw
    assert watched_output.read_bytes() == b"preexisting"
    assert not (tmp_path / "auth.json").exists()


def test_cli_removes_existing_authfile_when_manifest_preflight_fails(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release-manifest.json"
    invalid_raw = deferred_manifest_raw().rstrip(b"\n")
    manifest_path.write_bytes(invalid_raw)
    authfile = tmp_path / "auth.json"
    authfile.write_bytes(b"stale-temporary-credential")

    assert main(_cli_args(tmp_path, manifest_path)) == 2

    assert manifest_path.read_bytes() == invalid_raw
    assert not authfile.exists()
    assert not (tmp_path / "mirror-attestation.json").exists()
    assert not (tmp_path / "mirror-failure.json").exists()


@pytest.mark.parametrize(
    "preflight_failure",
    ["noncanonical_manifest", "missing_environment"],
)
def test_cli_removes_stale_outputs_before_safe_preflight_early_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preflight_failure: str,
) -> None:
    manifest_path = tmp_path / "release-manifest.json"
    manifest_raw = deferred_manifest_raw()
    if preflight_failure == "noncanonical_manifest":
        manifest_raw = manifest_raw.rstrip(b"\n")
        _set_cli_environment(monkeypatch)
    else:
        for key in (
            "TCR_USERNAME",
            "TCR_PASSWORD",
            "GHCR_USERNAME",
            "GHCR_PASSWORD",
            "TCR_REGISTRY",
            "TCR_NAMESPACE",
        ):
            monkeypatch.delenv(key, raising=False)
    manifest_path.write_bytes(manifest_raw)
    authfile = tmp_path / "auth.json"
    authfile.write_bytes(b"stale-temporary-credential")
    attestation_output = tmp_path / "mirror-attestation.json"
    failure_output = tmp_path / "mirror-failure.json"
    attestation_output.write_bytes(b"stale-attestation")
    failure_output.write_bytes(b"stale-failure")

    assert main(_cli_args(tmp_path, manifest_path)) == 2

    assert manifest_path.read_bytes() == manifest_raw
    assert not authfile.exists()
    assert not attestation_output.exists()
    assert not failure_output.exists()


def _secure_authfile_with_failing_cleanup(path: Path):
    @contextmanager
    def managed():
        path.write_bytes(b"")
        try:
            yield path
        finally:
            path.unlink(missing_ok=True)
            raise OSError("cleanup-secret D:/runner-temp/private-auth.json")

    return managed()


def test_cli_cleanup_does_not_mask_primary_failure_and_artifact_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_bytes(deferred_manifest_raw())
    transport = FakeBackfillTransport(
        {
            "copy:ghcr:backend": [
                RegistryFailure("copy", GHCR_REGISTRY, "fatal_registry_failure")
            ]
        }
    )
    _set_cli_environment(monkeypatch)
    monkeypatch.setattr(
        backfill_ghcr,
        "_make_transport",
        lambda authfile, credential: transport,
    )
    monkeypatch.setattr(
        backfill_ghcr,
        "secure_authfile",
        _secure_authfile_with_failing_cleanup,
    )

    assert main(_cli_args(tmp_path, manifest_path)) == 1

    failure_raw = (tmp_path / "mirror-failure.json").read_bytes()
    assert json.loads(failure_raw) == {
        "schema_version": "1999wiki.mirror-backfill-failure/v1",
        "commit": COMMIT,
        "release_tag": "sha-abcdef0",
        "phase": "ghcr_backend_copy",
        "code": "fatal_registry_failure",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "mutated": True,
        "verified_tcr": {
            "backend": TCR_SOURCES["backend"].removeprefix("docker://"),
            "frontend": TCR_SOURCES["frontend"].removeprefix("docker://"),
        },
        "verified_ghcr": {},
    }
    text = failure_raw.decode("utf-8")
    for forbidden in (
        "stderr",
        "tcr-secret",
        "ghcr-secret",
        "cleanup-secret",
        str(tmp_path),
        "TCR_PASSWORD",
        "GHCR_PASSWORD",
    ):
        assert forbidden not in text
    assert not (tmp_path / "mirror-attestation.json").exists()
    assert not (tmp_path / "auth.json").exists()


def test_skopeo_backfill_transport_uses_exact_registry_digest_source() -> None:
    calls: list[tuple[list[str], bytes | None]] = []

    def runner(argv: list[str], stdin: bytes | None) -> CommandResult:
        calls.append((argv, stdin))
        return CommandResult(0, b"", "")

    transport = backfill_ghcr.BackfillSkopeoTransport(
        authfile=Path("D:/runner-temp/auth.json"),
        credential=CREDENTIALS["ghcr"],
        runner=runner,
    )

    transport.copy(
        TCR_SOURCES["backend"],
        GHCR_TARGETS["backend"],
        RetryBudget(),
    )

    assert calls == [
        (
            [
                "skopeo",
                "copy",
                "--all",
                "--preserve-digests",
                "--authfile",
                str(Path("D:/runner-temp/auth.json")),
                TCR_SOURCES["backend"],
                "docker://" + GHCR_TARGETS["backend"],
            ],
            None,
        )
    ]
