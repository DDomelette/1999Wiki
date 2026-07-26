# 1999Wiki Dual-Registry Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build each reviewed Backend and Frontend image once, publish the
identical OCI manifests to TCR and GHCR under immutable seven-character
short-SHA tags such as `sha-a3b1541`, default production deployment to TCR
digest-qualified refs, and support safe deferred GHCR backfill without
rebuilding.

**Architecture:** Pure release-identity code owns canonical v2 manifests,
mirror attestations, and environment emission. A separate Skopeo transport
layer owns registry login, probing, manifest-preserving copy, digest
verification, sanitized failure classification, and the shared five-failure
GHCR budget. Thin publication/backfill coordinators apply TCR-first policy,
while GitHub Actions builds two temporary `linux/amd64` OCI archives exactly
once and calls those coordinators.

**Tech Stack:** Python 3.11, pytest, GitHub Actions, Docker Buildx,
OCI image archives, Skopeo, TCR Personal Edition, GHCR, Bash, ShellCheck,
actionlint, Docker Compose.

## Global Constraints

- Primary Backend:
  `ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend`.
- Primary Frontend:
  `ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend`.
- Mirror Backend: `ghcr.io/ddomelette/1999wiki-backend`.
- Mirror Frontend: `ghcr.io/ddomelette/1999wiki-frontend`.
- One reviewed full Git commit produces exactly one Backend OCI archive and one
  Frontend OCI archive for `linux/amd64`; registry-specific rebuilds are
  forbidden.
- The immutable tag is `sha-` plus the first seven lowercase hexadecimal
  characters of the full 40-character commit.
- All registry copies use `skopeo copy --all --preserve-digests`; a destination
  manifest digest different from the source digest fails closed.
- TCR is mandatory. TCR lookup, login, permission, tag, copy, manifest, or
  digest failure blocks the release.
- GHCR has one shared budget of five transient failures per workflow run.
  Retryable classes are DNS/connectivity failures, reset/timeout, and HTTP
  `500`, `502`, `503`, or `504`.
- GHCR authentication, authorization, any HTTP `4xx` including `429`, tag
  conflict, malformed manifest, media-type, or digest failure is fatal without
  retry.
- A fifth transient GHCR failure permits
  `ready_with_deferred_ghcr` only after both TCR images are verified.
- Publication and backfill must never log passwords, raw auth files, or
  secret-bearing command lines.
- GitHub Secrets are `TCR_USERNAME` and `TCR_PASSWORD`. GitHub variables are
  `TCR_REGISTRY=ccr.ccs.tencentyun.com` and
  `TCR_NAMESPACE=1999wiki_code`.
- GHCR uses the workflow-scoped `GITHUB_TOKEN` and `${{ github.actor }}`.
- `release-manifest.json` uses `1999wiki.release/v2` and is immutable after
  publication.
- A deferred mirror is made deployable from GHCR only by a separate
  `1999wiki.mirror-attestation/v1` bound to the SHA-256 of the exact original
  manifest bytes.
- Server release files default to TCR. GHCR selection is explicit and requires
  either two originally published GHCR records or a valid complete attestation.
- Backend and Frontend refs in one server release must use the same registry
  family and the same seven-character short-SHA tag.
- Existing RAG permission, blue/green, digest verification, rollback, and
  retirement fail-closed behavior must not be weakened.
- The server never builds images and never reads COS for normal runtime media
  or application data.
- Do not push registries, merge to `main`, change GitHub secrets, SSH to the
  server, or deploy during Tasks 1-7. Those are a separate post-plan operator
  phase after all review gates pass.

## File Structure

- `deploy/bin/release_identity.py` — pure canonical schemas and validation for
  v2 release manifests, v1 mirror attestations, and registry-specific
  environment emission.
- `deploy/bin/release_manifest.py` — CLI wrapper over `release_identity.py`;
  contains no independent schema rules.
- `.github/scripts/registry_transport.py` — Skopeo command boundary, sanitized
  failure classification, exact digest probing/copying, and shared retry
  budget.
- `.github/scripts/publish_registries.py` — TCR-first normal publication
  coordinator; writes either the v2 manifest or a non-deployable failure
  report.
- `.github/scripts/backfill_ghcr.py` — exact TCR-digest-to-GHCR backfill
  coordinator; writes a mirror attestation only after both GHCR refs verify.
- `.github/workflows/publish-images.yml` — tests, two one-time OCI builds, and
  normal dual-registry publication.
- `.github/workflows/backfill-ghcr.yml` — manual download/validation/backfill of
  a degraded release.
- `deploy/bin/ops_helper.py` — centralized approved repository parser for TCR
  and GHCR release, local-digest, and retirement validation.
- `deploy/bin/ops-common.sh` — consumes parsed tag/canonical-digest identities;
  contains no registry-specific regular expression.
- `deploy/env/release.env.example` — TCR-first digest-qualified example.
- `tests/test_release_identity.py` — canonical schema, attestation, and
  environment-selection tests.
- `tests/test_registry_transport.py` — classifier, global retry budget, probe,
  copy, and digest tests.
- `tests/test_registry_publication.py` — TCR-first publication state-machine
  tests.
- `tests/test_registry_backfill.py` — exact-source backfill and attestation
  tests.
- `tests/test_ghcr_workflow.py` — static contracts for both Actions workflows.
- `tests/test_deploy_scripts.py` — server allowlist, mixed-registry rejection,
  local RepoDigest, rollback, and retirement tests.
- `tests/test_production_compose.py` — TCR-first release example assertion.
- `tests/test_dual_registry_integration.py` — disposable two-registry,
  one-archive, same-digest integration proof.
- `pytest.ini` — registers the explicit `registry_integration` marker.
- `docs/codex/production-deployment-runbook.md` — TCR login, manifest
  selection, degraded GHCR, and backfill operating instructions.
- `docs/superpowers/specs/2026-07-23-production-container-readiness-design.md`
  — short supersession note linking the approved dual-registry design.
- Delete `.github/scripts/refuse-existing-image-tags.sh` after its behavior is
  covered by `registry_transport.py`.

---

### Task 1: Canonical Release Manifest v2 and Mirror Attestation

**Files:**
- Create: `deploy/bin/release_identity.py`
- Create: `tests/test_release_identity.py`

**Interfaces:**
- Produces:
  `create_release_manifest(commit: str, digests: Mapping[str, str],
  ghcr_statuses: Mapping[str, str]) -> dict[str, object]`.
- Produces:
  `verify_release_manifest_bytes(raw: bytes, expected_commit: str)
  -> dict[str, object]`.
- Produces:
  `create_mirror_attestation(manifest_raw: bytes,
  ghcr_refs: Mapping[str, str], workflow_run_id: str,
  completed_at: str) -> dict[str, object]`.
- Produces:
  `verify_mirror_attestation(manifest_raw: bytes,
  attestation: Mapping[str, object], expected_commit: str)
  -> dict[str, object]`.
- Produces:
  `emit_release_env(manifest: Mapping[str, object], registry: str,
  attestation: Mapping[str, object] | None = None) -> tuple[str, str, str]`.
- Depends only on the Python standard library.

- [ ] **Step 1: Add pure v2 manifest behavior tests**

Create `tests/test_release_identity.py` with a v2 TCR-first/deferred fixture.
Leave the existing v1 CLI and its historical workflow test unchanged until
Task 6, so the still-active single-registry workflow remains executable:

```python
COMMIT = "abcdef0123456789abcdef0123456789abcdef01"
BACKEND_DIGEST = "sha256:" + "a" * 64
FRONTEND_DIGEST = "sha256:" + "b" * 64


def test_release_v2_records_mandatory_tcr_and_deferred_ghcr() -> None:
    payload = create_release_manifest(
        COMMIT,
        {"backend": BACKEND_DIGEST, "frontend": FRONTEND_DIGEST},
        {
            "backend": "published",
            "frontend": "deferred_after_5_network_failures",
        },
    )
    assert payload["schema_version"] == "1999wiki.release/v2"
    assert payload["primary_registry"] == "tcr"
    assert payload["release_state"] == "ready_with_deferred_ghcr"
    assert (
        payload["images"]["backend"]["registries"]["tcr"]["ref"]
        == "ccr.ccs.tencentyun.com/1999wiki_code/"
        "1999wiki-backend:sha-abcdef0@" + BACKEND_DIGEST
    )
    assert (
        payload["images"]["frontend"]["registries"]["ghcr"]
        == {
            "status": "deferred_after_5_network_failures",
            "tag": "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0",
            "ref": None,
        }
    )
```

- [ ] **Step 2: Add strict negative schema tests**

Add parameterized tests that mutate one canonical payload at a time and require
`ManifestError` for:

```python
[
    ("schema_version", "1999wiki.release/v1"),
    ("commit", "ABCDEF0123456789abcdef0123456789abcdef01"),
    ("release_tag", "sha-deadbee"),
    ("primary_registry", "ghcr"),
    ("release_state", "ready"),
]
```

Also cover an extra field, a missing field, a TCR status other than
`published`, wrong repository, mismatched digest, GHCR `published` with
`ref=None`, GHCR deferred with a non-null ref, and mixed derived release state.

- [ ] **Step 3: Add attestation and environment-selection tests**

Use canonical JSON bytes ending in one newline. Test:

```python
def test_deferred_ghcr_requires_matching_complete_attestation() -> None:
    manifest_raw = canonical_deferred_manifest_bytes()
    with pytest.raises(ManifestError, match="attestation"):
        emit_release_env(
            verify_release_manifest_bytes(manifest_raw, COMMIT),
            "ghcr",
        )

    attestation = create_mirror_attestation(
        manifest_raw,
        {
            "backend": (
                "ghcr.io/ddomelette/1999wiki-backend:"
                "sha-abcdef0@" + BACKEND_DIGEST
            ),
            "frontend": (
                "ghcr.io/ddomelette/1999wiki-frontend:"
                "sha-abcdef0@" + FRONTEND_DIGEST
            ),
        },
        workflow_run_id="123456789",
        completed_at="2026-07-26T12:00:00Z",
    )
    verified = verify_mirror_attestation(
        manifest_raw,
        attestation,
        COMMIT,
    )
    lines = emit_release_env(
        verify_release_manifest_bytes(manifest_raw, COMMIT),
        "ghcr",
        verified,
    )
    assert lines[1].startswith("BACKEND_IMAGE=ghcr.io/")
    assert lines[2].startswith("FRONTEND_IMAGE=ghcr.io/")
```

Reject a wrong manifest SHA-256, commit, component name, repository, digest,
status, run ID, non-UTC timestamp, extra field, missing field, or attestation
without both components. Confirm TCR emission never needs an attestation and a
fully mirrored original manifest emits GHCR directly.

- [ ] **Step 4: Run the new tests to verify RED**

Run:

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_release_identity.py
```

Expected: collection/import failure because `release_identity.py` and the v2
interfaces do not exist.

- [ ] **Step 5: Implement the pure identity library**

Create `deploy/bin/release_identity.py` with these constants and record rules:

```python
SCHEMA_VERSION = "1999wiki.release/v2"
ATTESTATION_SCHEMA_VERSION = "1999wiki.mirror-attestation/v1"
COMPONENTS = ("backend", "frontend")
REPOSITORIES = {
    "tcr": {
        "backend": (
            "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend"
        ),
        "frontend": (
            "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend"
        ),
    },
    "ghcr": {
        "backend": "ghcr.io/ddomelette/1999wiki-backend",
        "frontend": "ghcr.io/ddomelette/1999wiki-frontend",
    },
}
GHCR_STATUSES = {
    "published",
    "deferred_after_5_network_failures",
}
```

Canonical JSON uses:

```python
def canonical_json(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
```

For each component, store one top-level `digest`; derive all tags from the
commit. TCR records are always `published`. GHCR deferred records use
`ref=None`. Derive `release_state` from the two GHCR statuses rather than
accepting it as input. Strict verification reconstructs the canonical payload
and requires exact equality.

Attestations store:

```python
{
    "schema_version": "1999wiki.mirror-attestation/v1",
    "manifest_sha256": "sha256:" + hashlib.sha256(manifest_raw).hexdigest(),
    "commit": COMMIT,
    "status": "completed",
    "workflow_run_id": "123456789",
    "completed_at": "2026-07-26T12:00:00Z",
    "images": {
        "backend": {
            "source": TCR_BACKEND_REF,
            "destination": GHCR_BACKEND_REF,
            "digest": BACKEND_DIGEST,
        },
        "frontend": {
            "source": TCR_FRONTEND_REF,
            "destination": GHCR_FRONTEND_REF,
            "digest": FRONTEND_DIGEST,
        },
    },
}
```

Require `completed_at` to parse as an RFC 3339 `Z` timestamp and
`workflow_run_id` to contain ASCII decimal digits only.

- [ ] **Step 6: Run focused and compatibility tests**

Run:

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_release_identity.py `
  tests/test_ghcr_workflow.py
```

Expected: all tests pass. The existing v1 CLI assertion remains intentionally
until Task 6; all new identity-library assertions are v2.

- [ ] **Step 7: Commit Task 1**

```powershell
git add -- `
  deploy/bin/release_identity.py `
  tests/test_release_identity.py
git commit -m "feat: define dual-registry release identity"
```

### Task 2: Skopeo Transport, Failure Classification, and Shared Retry Budget

**Files:**
- Create: `.github/scripts/registry_transport.py`
- Create: `tests/test_registry_transport.py`

**Interfaces:**
- Consumes `REPOSITORIES`, component names, tag grammar, and digest grammar
  from `deploy/bin/release_identity.py`.
- Produces `FailureKind`, `ProbeState`, `RegistryFailure`,
  `MirrorDeferred`, `CommandResult`, `Credential`, `RetryBudget`,
  `SkopeoTransport`, `secure_authfile`, and
  `ensure_mirror_copy(transport: SkopeoTransport, source: str, target: str,
  expected_digest: str, budget: RetryBudget,
  sleep: Callable[[float], None]) -> str`.
- No manifest creation and no normal/backfill release-state policy lives here.

- [ ] **Step 1: Write classifier and retry-budget tests**

Use a literal table:

```python
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
```

Test a single `RetryBudget(max_failures=5)` shared across login, probe, copy,
and verification. Five transient failures must raise `MirrorDeferred`; a sixth
registry command must never run. A successful operation does not create a new
budget.

- [ ] **Step 2: Write probe and manifest-preserving copy tests**

Inject a `runner(argv, stdin) -> CommandResult` fake with exact scripted
results. Assert:

- `manifest unknown` is `ProbeState.ABSENT`;
- exact raw-manifest SHA-256 is `ProbeState.PRESENT_EXPECTED`;
- a different digest is `ProbeState.PRESENT_CONFLICT`;
- authentication and ambiguous errors raise fatal `RegistryFailure`;
- command arguments contain `--all --preserve-digests`;
- credentials travel in `stdin`, not `argv`;
- errors expose only `operation`, `registry`, and stable `code`.

- [ ] **Step 3: Write uncertain-copy reconciliation tests**

For a copy that times out after the registry accepted it, script:

```text
copy -> transient timeout
probe destination -> exact expected digest
```

Require `ensure_mirror_copy` to return `published` without a second copy.
Cover:

```text
copy -> transient
probe -> absent
copy -> success
verify -> exact
```

Also cover five shared transient failures returning
`deferred_after_5_network_failures`, and an exact-digest conflict failing
immediately.

- [ ] **Step 4: Run tests to verify RED**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_registry_transport.py
```

Expected: import failure because `registry_transport.py` does not exist.

- [ ] **Step 5: Implement the transport**

Define:

```python
class FailureKind(enum.Enum):
    TRANSIENT = "transient"
    FATAL = "fatal"


class ProbeState(enum.Enum):
    ABSENT = "absent"
    PRESENT_EXPECTED = "present_expected"
    PRESENT_CONFLICT = "present_conflict"


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

    def consume(self) -> None:
        self.failures += 1
        if self.failures >= self.max_failures:
            raise MirrorDeferred(
                "deferred_after_5_network_failures"
            )
```

Match fatal evidence before transient evidence. Treat only explicit
`manifest unknown`, `name unknown`, or `no such manifest` as absence.
Everything unrecognized is fatal.

`SkopeoTransport` commands are:

```text
skopeo login --authfile AUTH --username USER --password-stdin REGISTRY
skopeo inspect --raw --authfile AUTH docker://REPOSITORY:TAG
skopeo copy --all --preserve-digests --authfile AUTH
  oci-archive:ARCHIVE docker://REPOSITORY:TAG
```

Compute the protected manifest digest as
`sha256:` plus `hashlib.sha256(raw_manifest).hexdigest()`. Require the target
raw manifest to hash to the same value after every successful copy.

Backoff delays are `1`, `2`, `4`, and `8` seconds plus injected jitter in
`[0.0, 0.5]`; tests inject a no-op sleeper and zero jitter.

`secure_authfile(path: Path)` creates an empty file with mode `0600`, yields its
path, and unlinks it in `finally`. Publication and backfill both use this
context manager instead of duplicating credential-file cleanup.

Because `.github` is not a Python package name, scripts add their own directory
and the resolved repository root's `deploy/bin` directory to `sys.path` before
importing `registry_transport` and `release_identity`. Tests use the same
resolved directories; they do not depend on the caller's working directory.

- [ ] **Step 6: Run focused tests**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_registry_transport.py `
  tests/test_ghcr_workflow.py
```

Expected: all tests pass. Keep
`.github/scripts/refuse-existing-image-tags.sh` during this task because the
still-active single-registry workflow references it. Task 5 removes both the
workflow reference and the script atomically.

- [ ] **Step 7: Commit Task 2**

```powershell
git add -- `
  .github/scripts/registry_transport.py `
  tests/test_registry_transport.py
git commit -m "feat: add digest-preserving registry transport"
```

### Task 3: TCR-First Publication Coordinator

**Files:**
- Create: `.github/scripts/publish_registries.py`
- Create: `tests/test_registry_publication.py`

**Interfaces:**
- Consumes `release_identity.create_release_manifest`,
  `release_identity.canonical_json`, `SkopeoTransport`, and `RetryBudget`.
- Produces
  `publish_release(commit: str, archives: Mapping[str, Path],
  transport: SkopeoTransport, credentials: Mapping[str, Credential],
  workflow_run_id: str) -> dict[str, object]`.
- CLI writes `release-manifest.json` on success and
  `publication-failure.json` on fatal failure after any registry mutation.

- [ ] **Step 1: Write TCR hard-gate tests**

Use a stateful fake transport and assert exact ordering:

```python
assert calls == [
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
```

Test that an existing TCR tag, TCR auth failure, TCR partial copy, or TCR
digest mismatch raises a fatal publication error and emits no deployable
manifest.

- [ ] **Step 2: Write GHCR degraded/fatal tests**

Cover:

- GHCR preflight reaches five transient failures: both GHCR statuses deferred,
  then TCR publishes and the manifest is
  `ready_with_deferred_ghcr`.
- Backend GHCR publishes, Frontend reaches the shared fifth transient failure:
  Backend is `published`, Frontend is deferred.
- GHCR auth/permission/`429`/tag conflict/digest mismatch: immediate failure,
  no deployable manifest.
- A GHCR tag present during normal publication is a conflict even when its
  digest equals the intended digest.
- `publication-failure.json` contains only:

```python
{
    "schema_version": "1999wiki.publication-failure/v1",
    "commit": COMMIT,
    "release_tag": "sha-abcdef0",
    "phase": "ghcr_frontend_copy",
    "code": "digest_mismatch",
    "workflow_run_id": "123456789",
    "verified_tcr": {
        "backend": TCR_BACKEND_REF,
        "frontend": TCR_FRONTEND_REF,
    },
}
```

It must contain no stderr, username, password, auth-file path, or environment
dump.

`verified_tcr` is an exact component-to-ref object containing zero, one, or two
entries according to which TCR destinations were actually verified before the
failure. It must never claim an unverified component.

- [ ] **Step 3: Run tests to verify RED**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_registry_publication.py
```

Expected: import failure because `publish_registries.py` does not exist.

- [ ] **Step 4: Implement publication policy**

The CLI is:

```text
publish_registries.py
  --commit abcdef0123456789abcdef0123456789abcdef01
  --backend-archive D:/runner-temp/backend.oci
  --frontend-archive D:/runner-temp/frontend.oci
  --authfile D:/runner-temp/1999wiki-auth.json
  --manifest-output release-manifest.json
  --failure-output publication-failure.json
  --workflow-run-id 123456789
```

Read credentials only from:

```text
TCR_USERNAME
TCR_PASSWORD
GHCR_USERNAME
GHCR_PASSWORD
TCR_REGISTRY
TCR_NAMESPACE
```

Validate the two non-secret TCR values against the fixed approved values before
login. Create the auth file with mode `0600`; delete it in `finally`.

Preflight GHCR before TCR mutation so fatal GHCR auth/tag problems do not
strand TCR tags. If GHCR preflight consumes the fifth transient failure, mark
both components deferred and continue with TCR. Publish and verify both TCR
images before any GHCR copy. Build the final manifest through
`create_release_manifest`; never hand-build its JSON fields.

- [ ] **Step 5: Run focused publication tests**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_registry_transport.py `
  tests/test_registry_publication.py `
  tests/test_release_identity.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- `
  .github/scripts/publish_registries.py `
  tests/test_registry_publication.py
git commit -m "feat: publish TCR-first dual-registry releases"
```

### Task 4: Exact-Digest GHCR Backfill

**Files:**
- Create: `.github/scripts/backfill_ghcr.py`
- Create: `tests/test_registry_backfill.py`

**Interfaces:**
- Consumes canonical release manifest bytes, release-identity verification,
  Skopeo transport, and the shared retry budget.
- Produces
  `backfill_release(manifest_raw: bytes, expected_commit: str,
  transport: SkopeoTransport, credentials: Mapping[str, Credential],
  workflow_run_id: str, completed_at: str) -> dict[str, object]`.
- Writes a mirror attestation only after both GHCR refs verify.

- [ ] **Step 1: Write backfill source and target tests**

Test:

```text
verify degraded original manifest
login TCR
login GHCR
inspect exact TCR backend repo@digest
inspect exact TCR frontend repo@digest
probe GHCR Backend
copy missing Backend from exact TCR repo@digest
verify Backend
probe GHCR Frontend
accept already-exact Frontend
verify both
create attestation
```

The Backend copy source must have the concrete shape
`docker://ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`;
Frontend uses its approved repository and observed digest. Neither source is a
tag or an OCI rebuild.

- [ ] **Step 2: Write refusal tests**

Reject:

- an original `ready` manifest because no backfill is needed;
- an invalid or noncanonical original manifest;
- wrong expected commit;
- missing or mismatched TCR source digest;
- GHCR existing different digest;
- fatal GHCR auth/permission/manifest error;
- five transient failures without writing an attestation;
- any attempt to overwrite the original manifest path.

An already-exact GHCR target is idempotently accepted.

- [ ] **Step 3: Run tests to verify RED**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_registry_backfill.py
```

Expected: import failure because `backfill_ghcr.py` does not exist.

- [ ] **Step 4: Implement backfill**

The CLI is:

```text
backfill_ghcr.py
  --manifest release-manifest.json
  --commit abcdef0123456789abcdef0123456789abcdef01
  --authfile D:/runner-temp/1999wiki-backfill-auth.json
  --attestation-output mirror-attestation.json
  --failure-output mirror-failure.json
  --workflow-run-id 123456790
  --completed-at 2026-07-26T12:30:00Z
```

The original manifest is opened read-only and its bytes retained for hashing.
The script verifies both TCR sources before probing or copying GHCR. Use one
shared five-failure budget for GHCR login, probe, copy, and verification. Only
`release_identity.create_mirror_attestation` may construct the attestation.
Delete the temporary auth file in `finally`.

- [ ] **Step 5: Run focused backfill tests**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_registry_backfill.py `
  tests/test_registry_transport.py `
  tests/test_release_identity.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 4**

```powershell
git add -- `
  .github/scripts/backfill_ghcr.py `
  tests/test_registry_backfill.py
git commit -m "feat: backfill GHCR from verified TCR digests"
```

### Task 5: Build-Once Publish and Backfill Workflows

**Files:**
- Modify: `.github/workflows/publish-images.yml`
- Create: `.github/workflows/backfill-ghcr.yml`
- Modify: `tests/test_ghcr_workflow.py`
- Delete: `.github/scripts/refuse-existing-image-tags.sh`

**Interfaces:**
- Consumes the Task 3 and Task 4 CLIs.
- Produces Actions artifacts:
  `release-sha-abcdef0/release-manifest.json` and
  `mirror-sha-abcdef0-123456790/mirror-attestation.json`, with values derived
  from the validated release and workflow run.
- Does not deploy or SSH.

- [ ] **Step 1: Replace workflow tests with dual-registry structural tests**

Require:

- `workflow_dispatch` only;
- separate Python and Frontend test jobs;
- publish depends on both;
- exactly two `docker/build-push-action@v6` steps;
- each build has `platforms: linux/amd64`, no registry tag, and one OCI output;
- neither build has `push: true`;
- the two archives are not uploaded as artifacts;
- Skopeo is installed and its version recorded;
- publisher receives secrets only through environment variables;
- TCR variables use `${{ vars.TCR_REGISTRY }}` and
  `${{ vars.TCR_NAMESPACE }}`;
- manifest upload occurs only after publisher success;
- a failure artifact upload is guarded by `failure()` and file existence;
- no SSH, SCP, Compose, server IP, COS, or deploy command exists.

Add a test for the backfill workflow's exact inputs:

```yaml
release_run_id:
  required: true
release_tag:
  required: true
expected_commit:
  required: true
```

Require `actions/download-artifact@v4` to use the supplied run ID and exact
release artifact name, then call `backfill_ghcr.py` and upload only the
attestation/failure result.

- [ ] **Step 2: Run workflow tests to verify RED**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_ghcr_workflow.py
```

Expected: failures showing the old workflow pushes GHCR directly, builds per
destination semantics, and has no backfill workflow.

- [ ] **Step 3: Implement build-once publication workflow**

Keep the existing test jobs. In `publish`, add:

```yaml
- name: Install Skopeo
  shell: bash
  run: |
    sudo apt-get update
    sudo apt-get install --yes skopeo
    skopeo --version

- id: backend
  uses: docker/build-push-action@v6
  with:
    context: .
    file: docker/Dockerfile.backend
    platforms: linux/amd64
    push: false
    outputs: type=oci,dest=${{ runner.temp }}/backend.oci
    cache-from: type=gha
    cache-to: type=gha,mode=max

- id: frontend
  uses: docker/build-push-action@v6
  with:
    context: .
    file: docker/Dockerfile.frontend
    platforms: linux/amd64
    push: false
    outputs: type=oci,dest=${{ runner.temp }}/frontend.oci
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

Call the publisher with:

```yaml
env:
  TCR_USERNAME: ${{ secrets.TCR_USERNAME }}
  TCR_PASSWORD: ${{ secrets.TCR_PASSWORD }}
  TCR_REGISTRY: ${{ vars.TCR_REGISTRY }}
  TCR_NAMESPACE: ${{ vars.TCR_NAMESPACE }}
  GHCR_USERNAME: ${{ github.actor }}
  GHCR_PASSWORD: ${{ secrets.GITHUB_TOKEN }}
run: |
  python3 .github/scripts/publish_registries.py \
    --commit "$GITHUB_SHA" \
    --backend-archive "${RUNNER_TEMP}/backend.oci" \
    --frontend-archive "${RUNNER_TEMP}/frontend.oci" \
    --authfile "${RUNNER_TEMP}/1999wiki-auth.json" \
    --manifest-output release-manifest.json \
    --failure-output publication-failure.json \
    --workflow-run-id "$GITHUB_RUN_ID"
```

The summary reads only canonical manifest fields and labels the release
`ready` or `ready_with_deferred_ghcr`.

After the workflow no longer references the Bash tag guard, remove it:

```powershell
git rm -- .github/scripts/refuse-existing-image-tags.sh
```

- [ ] **Step 4: Implement manual backfill workflow**

Use `permissions: {contents: read, actions: read, packages: write}` and the
same full-commit concurrency group plus `-ghcr-backfill`. Download the exact
original artifact from `release_run_id`, validate `release_tag` with
`^sha-[0-9a-f]{7}$`, validate `expected_commit` through the Python CLI, install
Skopeo, and invoke `backfill_ghcr.py`.

Use PowerShell/YAML tests to ensure workflow expressions never interpolate
passwords into `run:` strings.

- [ ] **Step 5: Run workflow, actionlint, and focused Python tests**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_ghcr_workflow.py `
  tests/test_registry_publication.py `
  tests/test_registry_backfill.py
docker run --rm `
  --volume "${PWD}:/repo:ro" `
  --workdir /repo `
  rhysd/actionlint:1.7.7
```

Expected: all pytest tests pass and actionlint exits 0.

- [ ] **Step 6: Commit Task 5**

```powershell
git add -- `
  .github/workflows/publish-images.yml `
  .github/workflows/backfill-ghcr.yml `
  tests/test_ghcr_workflow.py
git add -u -- .github/scripts/refuse-existing-image-tags.sh
git commit -m "ci: publish immutable images to TCR and GHCR"
```

### Task 6: Accept TCR and Attested GHCR on the Server

**Files:**
- Modify: `deploy/bin/release_manifest.py`
- Modify: `deploy/bin/ops_helper.py`
- Modify: `deploy/bin/ops-common.sh`
- Modify: `deploy/env/release.env.example`
- Modify: `tests/test_ghcr_workflow.py`
- Modify: `tests/test_release_identity.py`
- Modify: `tests/test_deploy_scripts.py`
- Modify: `tests/test_production_compose.py`

**Interfaces:**
- Consumes registry-specific environment output from
  `release_manifest.py verify`.
- Produces
  `parse_image_identity(value: str,
  expected_component: str | None = None) -> ImageIdentity`.
- Produces CLI:
  `ops_helper.py emit-image-identity
  ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-abcdef0@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`,
  printing exact tag and canonical `repository@digest` on two lines.

- [ ] **Step 1: Write the final v2 CLI tests**

Move the historical subprocess CLI test out of
`tests/test_ghcr_workflow.py` and rewrite it in
`tests/test_release_identity.py` for:

```text
create --commit --backend-digest --frontend-digest
       --backend-ghcr-status --frontend-ghcr-status --output
verify --manifest --commit --registry {tcr,ghcr}
       [--attestation mirror-attestation.json]
attest --manifest --commit --backend-ghcr-ref --frontend-ghcr-ref
       --workflow-run-id --completed-at --output
```

`verify --registry tcr` must print exactly:

```text
RELEASE_COMMIT=abcdef0123456789abcdef0123456789abcdef01
BACKEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-abcdef0@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
FRONTEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:sha-abcdef0@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
```

Test GHCR verification both with an originally complete manifest and with a
valid attestation. Remove every final v1 schema assertion.

- [ ] **Step 2: Write release validation tests**

Add literal TCR Backend/Frontend refs and assert:

- a paired TCR release passes;
- a paired GHCR release still passes;
- TCR Backend plus GHCR Frontend fails;
- a namespace typo, component swap, tag-only ref, uppercase digest, wrong
  short tag, or unapproved registry fails;
- `validate-image-digests` accepts the exact corresponding TCR
  `repository@digest` and rejects a GHCR digest list for a TCR ref.

- [ ] **Step 3: Write retirement parsing tests**

Exercise the real CLI:

```text
python3 deploy/bin/ops_helper.py emit-image-identity
  ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-abcdef0@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

Expected two output lines:

```text
ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-abcdef0
ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

Extend cleanup harness coverage to TCR tag+digest, digest-only, mismatch,
inspect error, and absence. Add one cross-registry same-digest active/previous
case that fails closed without state commit.

- [ ] **Step 4: Update release example test**

Change the expected example to exact TCR-first prefixes:

```python
assert (
    "BACKEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/"
    "1999wiki-backend:sha-replace@sha256:"
) in release_example
```

Do the same for Frontend.

- [ ] **Step 5: Run tests to verify RED**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_deploy_scripts.py `
  tests/test_production_compose.py `
  tests/test_release_identity.py `
  tests/test_ghcr_workflow.py
```

Expected: new v2 CLI, TCR acceptance, and image-identity tests fail against the
old v1 CLI and GHCR-only parser.

- [ ] **Step 6: Convert `release_manifest.py` to the final thin v2 CLI**

Implement the three command shapes from Step 1. Import all schema and
attestation functions from `release_identity.py`. Use
`Path.write_bytes(canonical_json(payload))`; do not retain independent v1
repository or schema rules.

- [ ] **Step 7: Centralize image parsing in `ops_helper.py`**

Define:

```python
@dataclass(frozen=True)
class ImageIdentity:
    registry: str
    component: str
    tag: str
    digest: str
    tagged_ref: str
    canonical_ref: str
```

Build the approved repository-to-identity mapping from
`release_identity.REPOSITORIES`. `validate_release` parses both images, requires
their registry keys and tags to match, and binds the tag to `RELEASE_COMMIT`.
`validate_image_digests` parses the expected image and requires its exact
canonical ref in the JSON list.

Add the `emit-image-identity` subcommand. It accepts only a valid approved,
digest-qualified Backend or Frontend ref.

- [ ] **Step 8: Remove registry regex duplication from `ops-common.sh`**

Replace the hard-coded GHCR regex in `ops_set_retirement_image_refs` with:

```bash
local output
output="$(ops_helper emit-image-identity "$image")" || return 1
mapfile -t OPS_RETIREMENT_PARSED_REFS <<<"$output"
[[ "${#OPS_RETIREMENT_PARSED_REFS[@]}" -eq 2 ]] || return 1
OPS_RETIREMENT_IMAGE_TAG="${OPS_RETIREMENT_PARSED_REFS[0]}"
OPS_RETIREMENT_IMAGE_DIGEST="${OPS_RETIREMENT_PARSED_REFS[1]}"
```

Keep the independent tag/digest tri-state checks, exact removal identities,
post-removal absence verification, and state-commit order unchanged.

Before removing a previous component, parse the corresponding active and
retirement refs and compare their protected digest strings. If the digests
match while repository aliases differ, abort before image removal and preserve
the retirement journal for operator inspection.

- [ ] **Step 9: Make the checked-in release example TCR-first**

Use:

```env
RELEASE_COMMIT=replace-with-full-40-character-commit
BACKEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-replace@sha256:replace-with-backend-registry-digest
FRONTEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:sha-replace@sha256:replace-with-frontend-registry-digest
BACKEND_PORT=18100
FRONTEND_PORT=18180
```

- [ ] **Step 10: Run focused server tests and static gates**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_deploy_scripts.py `
  tests/test_production_compose.py `
  tests/test_release_identity.py `
  tests/test_ghcr_workflow.py
python -m py_compile `
  deploy/bin/release_identity.py `
  deploy/bin/release_manifest.py `
  deploy/bin/ops_helper.py
```

Run Bash syntax and ShellCheck with the known Git Bash/Docker tools:

```powershell
$bash = 'D:\Git\bin\bash.exe'
$shFiles = @(rg --files deploy .github/scripts -g '*.sh' |
  ForEach-Object { $_.Replace('\','/') })
foreach ($file in $shFiles) { & $bash -n $file }
docker run --rm `
  --volume "${PWD}:/repo:ro" `
  --workdir /repo `
  koalaman/shellcheck:v0.10.0 @shFiles
```

Expected: tests pass and all commands exit 0.

- [ ] **Step 11: Commit Task 6**

```powershell
git add -- `
  deploy/bin/release_manifest.py `
  deploy/bin/ops_helper.py `
  deploy/bin/ops-common.sh `
  deploy/env/release.env.example `
  tests/test_ghcr_workflow.py `
  tests/test_release_identity.py `
  tests/test_deploy_scripts.py `
  tests/test_production_compose.py
git commit -m "feat: deploy from approved TCR or GHCR refs"
```

### Task 7: Real Dual-Registry Proof, Runbook, and Full Release Gate

**Files:**
- Create: `tests/test_dual_registry_integration.py`
- Modify: `pytest.ini`
- Modify: `docs/codex/production-deployment-runbook.md`
- Modify:
  `docs/superpowers/specs/2026-07-23-production-container-readiness-design.md`
- Test: all files from Tasks 1-6

**Interfaces:**
- Consumes the finished publication, backfill, manifest, and server helpers.
- Produces one clean, reviewed implementation branch ready for integration.
- Does not contact TCR, GHCR, COS, or the production server.

- [ ] **Step 1: Write the disposable two-registry integration test**

The test:

1. creates a unique Docker network;
2. starts two uniquely named `registry:2` containers on that network;
3. creates a tiny Buildx context under `tmp_path` with:

   ```dockerfile
   FROM scratch
   COPY payload.txt /payload.txt
   ```

   and the exact UTF-8 payload `dual-registry-fixture\n`;
4. builds one `linux/amd64` OCI archive;
5. runs `quay.io/skopeo/stable:v1.19.0` on the network;
6. copies the same archive to `registry-a:5000` and `registry-b:5000` with
   `--all --preserve-digests --dest-tls-verify=false`;
7. hashes `skopeo inspect --raw` output for source and both targets;
8. requires all three digests to be identical;
9. proves an already-exact target is idempotent and a conflicting tag fails;
10. removes only the unique containers, network, images, and temporary files
    in `finally`.

The archive build command is:

```text
docker buildx build --platform linux/amd64
  --output type=oci,dest=fixture.oci fixture-context
```

Register and mark it:

```ini
[pytest]
markers =
    registry_integration: uses disposable local OCI registry containers
```

```python
@pytest.mark.registry_integration
def test_one_oci_archive_copies_to_two_registries_with_one_digest(
    tmp_path: Path,
) -> None:
    evidence = _run_dual_registry_fixture(tmp_path)
    assert evidence.source_digest == evidence.first_registry_digest
    assert evidence.source_digest == evidence.second_registry_digest
    assert evidence.conflict_was_rejected is True
    assert evidence.remaining_resources == ()
```

Define the test-only `CopyEvidence` dataclass and
`_run_dual_registry_fixture(tmp_path: Path) -> CopyEvidence` in the same file;
the helper performs the ten concrete lifecycle steps listed above and returns
observed digests plus exact post-cleanup resource names.

- [ ] **Step 2: Run the integration gate**

```powershell
conda run -n 1999wiki python -m pytest -q -m registry_integration `
  tests/test_dual_registry_integration.py
```

Expected: one pass proving real copy/digest behavior. If it fails, use the
actual Registry/Skopeo output to distinguish a fixture problem from a
production transport defect. Before changing production code, add a focused
unit regression to `tests/test_registry_transport.py`, verify that focused test
fails for the observed reason, then implement the minimal correction and rerun
both tests.

- [ ] **Step 3: Verify exact fixture cleanup**

Use fixed container DNS names inside the unique Docker network, so no host port
or IPv4/IPv6 proxy behavior is involved. Assert cleanup with:

```python
assert docker_ps_names(prefix) == []
assert docker_network_names(prefix) == []
assert docker_image_refs(repository_prefix) == []
```

Rerun the command from Step 2. Expected: one pass and zero leftovers.

- [ ] **Step 4: Rewrite the runbook's release section for TCR-first operation**

Document exact operator commands:

```bash
read -rsp 'TCR password: ' TCR_PASSWORD
printf '%s' "$TCR_PASSWORD" |
  docker login ccr.ccs.tencentyun.com \
    --username 100017272217 \
    --password-stdin
unset TCR_PASSWORD
chmod 0700 "$HOME/.docker"
chmod 0600 "$HOME/.docker/config.json"
```

Explain:

- GitHub Secrets/variables required before workflow dispatch;
- TCR is the default source;
- `release-manifest.json` is downloaded, verified with
  `--registry tcr`, and copied unchanged to the release directory;
- GHCR may be selected only with two original `published` records or
  `--attestation mirror-attestation.json`;
- degraded releases are labeled accurately;
- backfill uses the exact original workflow run/artifact and never rebuilds;
- server pulls the emitted digest-qualified TCR refs;
- no runtime COS access or server-side build is introduced.

Replace all normal GHCR-first pull/removal examples with TCR refs. Retain a
separate explicit GHCR recovery example.

- [ ] **Step 5: Add a supersession note to the older production design**

At the start of its GHCR section, add:

```markdown
> Registry publication and production pull selection are superseded by
> [2026-07-26-dual-registry-release-design.md](2026-07-26-dual-registry-release-design.md).
> TCR is primary; GHCR is the digest-identical mirror. All other container,
> data, and blue/green boundaries in this document remain in force.
```

- [ ] **Step 6: Run the complete Python gate**

```powershell
conda run -n 1999wiki python -m pytest -q
```

Expected: zero failures. Record the actual pass/skip counts; do not reuse the
previous `1,737 passed / 4 skipped` evidence.

- [ ] **Step 7: Run the Frontend gate**

```powershell
Set-Location frontend/react-app
npm ci
npm test
npm run build
Set-Location ../..
```

Expected: all React tests pass and the production build exits 0.

- [ ] **Step 8: Run workflow, shell, Compose, and whitespace gates**

```powershell
docker run --rm `
  --volume "${PWD}:/repo:ro" `
  --workdir /repo `
  rhysd/actionlint:1.7.7

$bash = 'D:\Git\bin\bash.exe'
$shFiles = @(rg --files deploy .github/scripts -g '*.sh' |
  ForEach-Object { $_.Replace('\','/') })
foreach ($file in $shFiles) { & $bash -n $file }

docker run --rm `
  --volume "${PWD}:/repo:ro" `
  --workdir /repo `
  koalaman/shellcheck:v0.10.0 @shFiles

docker compose `
  --env-file deploy/env/infra.env.example `
  -f deploy/compose.infra.yml `
  config --quiet

git diff --check
```

Use test-generated non-secret environment files when the checked-in examples
intentionally contain required placeholders. Expected: every command exits 0.

- [ ] **Step 9: Rebuild both production images from the final commit**

Use the final reviewed full commit's first seven characters:

```powershell
$sha = (git rev-parse HEAD).Substring(0,7)
docker build `
  --file docker/Dockerfile.backend `
  --tag "1999wiki-backend:verify-$sha" `
  .
docker build `
  --file docker/Dockerfile.frontend `
  --tag "1999wiki-frontend:verify-$sha" `
  .
docker image inspect `
  "1999wiki-backend:verify-$sha" `
  "1999wiki-frontend:verify-$sha"
```

Run the existing runtime-content inspection tests. Remove only these two
`verify-$sha` tags afterward; do not prune.

- [ ] **Step 10: Verify the final worktree and commit documentation/integration**

Require:

```powershell
git status --short
git diff --check
docker ps -a --filter name=1999wiki-dual-registry-
docker network ls --filter name=1999wiki-dual-registry-
docker image ls --format '{{.Repository}}:{{.Tag}}' |
  Select-String '1999wiki-dual-registry-' -SimpleMatch
```

Only the pre-existing untracked
`docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md` may remain.

Commit:

```powershell
git add -- `
  tests/test_dual_registry_integration.py `
  pytest.ini `
  docs/codex/production-deployment-runbook.md `
  docs/superpowers/specs/2026-07-23-production-container-readiness-design.md
git commit -m "docs: operate TCR-first mirrored releases"
```

- [ ] **Step 11: Request final whole-branch review**

Review from the original production-readiness branch base
`c45430df007349995855f5cf869709da5f5c93e6` through the final implementation
HEAD. Require explicit verdicts for:

- build-once OCI identity;
- TCR hard gate;
- exact five-failure GHCR policy;
- fatal error classification;
- canonical v2 manifest;
- immutable attested backfill;
- server TCR default and approved GHCR selection;
- tag/canonical-digest retirement;
- secrets/log redaction;
- no COS/server-build regression;
- tests and cleanup.

Do not merge, push, publish, or deploy until Critical and Important findings
are zero.

## Post-Plan Operator Phase

After Task 7 review is clean, handle these as a separately verified operational
sequence:

1. fast-forward the reviewed branch into `main`;
2. push `main` to `git@github.com:DDomelette/1999Wiki.git`;
3. configure the two GitHub Secrets and two repository variables without
   printing their values;
4. dispatch the publish workflow for the reviewed full commit;
5. require TCR success and record whether GHCR is `published` or
   `deferred_after_5_network_failures`;
6. download and verify the exact release manifest;
7. authenticate the Guangzhou server to TCR interactively or through an
   approved protected channel;
8. stage persistent data using the existing migration procedure;
9. deploy the TCR digest-qualified release through the existing blue/green
   runbook;
10. verify switch and rollback before retiring the old slot.

Stop for missing credentials, a TCR failure, a non-network GHCR failure,
manifest/digest disagreement, inadequate server disk, or any new
data-boundary decision.
