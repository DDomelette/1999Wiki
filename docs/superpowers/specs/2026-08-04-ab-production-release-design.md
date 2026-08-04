# A/B Production Release Design

**Date:** 2026-08-04
**Status:** Approved for implementation planning
**Release commit:** `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`
**Release tag:** `sha-daf3fe8`

## 1. Goal

Package and deploy the merged Thread A routing/composite-answer work and
Thread B Chinese BM25 analyzer compatibility work from the exact A/B merge
commit. The deployment must not include later Thread C, D0, or Story Segment
changes from the current `main` branch.

Thread B is a code-only compatibility release in this change window. The
production BM25 artifact remains `huiji.bm25-index/v2`; this release does not
build, upload, activate, or switch to a v3 Chinese-tokenized index.

The release is complete only when the immutable images are published, the
inactive production slot passes real-environment tests, traffic is switched,
post-switch tests pass, and the recorded BM25 and Milvus identities remain
unchanged.

## 2. Current state and constraints

- Thread A merge: `7535df532c26dfdef0c9a951a2c9f2c7d149824a`.
- Thread B merge and release source: `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`.
- The local `main` branch is substantially ahead of `origin/main`, contains
  later C and D0 work, and has four unrelated user document changes. It is not
  a valid release source.
- Production currently serves release `sha-1ec7752` from the green slot. The
  blue slot is the deployment target and green remains the rollback target.
- Production currently uses Milvus collection
  `text_child_bge_m3_shadow_crawler_v3_20260721t051246z`.
- The repository already contains the immutable dual-registry publication
  workflow, release manifest verifier, and blue/green deployment scripts at
  the A/B release commit.
- Historical GitHub publication attempts passed Python tests, frontend tests,
  frontend builds, and image builds, then failed before registry mutation at
  the TCR login boundary. The production server's protected Docker credential
  can currently read the existing TCR release image and is the approved source
  for repairing the repository's TCR Secrets without exposing plaintext.

## 3. Considered approaches

### 3.1 Clean A/B release branch — selected

Create `codex/release-ab` at the exact A/B merge commit in an isolated
worktree. Run local release gates, push that branch, publish immutable images
through GitHub Actions, and deploy them with the existing blue/green tooling.

This approach isolates the release from the dirty `main` worktree, preserves
the CI and manifest audit chain, and supports an immediate production rollback.

### 3.2 Git tag at the A/B commit

Dispatch the workflow from a tag at the same commit. This provides a fixed Git
reference but makes any separately reviewed release-infrastructure correction
less ergonomic. It offers no benefit over the content-addressed image tag and
full commit checks already enforced by the selected approach.

### 3.3 Manual local/server publication

Build OCI archives locally and push them from an operator-controlled host.
This can bypass an unavailable GitHub publication boundary, but weakens the
single-run test/build/publish evidence chain. It is an emergency fallback only
and requires a new explicit decision before use.

## 4. Release architecture

The release identity flows through fixed boundaries:

1. Git commit `daf3fe8...` in an isolated release worktree.
2. Local Python, frontend, and production-build verification.
3. GitHub Actions bound to `codex/release-ab` and the exact full commit.
4. Backend and frontend OCI images published to TCR and GHCR under
   `sha-daf3fe8`, each protected by its registry digest.
5. Canonical `1999wiki.release/v2` manifest binding the commit, tag, registry
   statuses, and component digests.
6. A private production release directory containing the byte-identical
   manifest and verified release identity.
7. The inactive blue slot using the digest-qualified images and the existing
   production application, RAG artifact, database, MinIO, and Milvus settings.
8. An atomic Caddy traffic switch only after blue passes its real-environment
   gates.

The runtime `deploy/` bundle must come from the same release commit. No source
checkout is placed on the production server.

## 5. Progressive deployment and testing

Testing is interleaved with deployment because local tests cannot cover all
production configuration, registry, network, storage, and dependency behavior.
Each phase is a hard gate; success in an earlier phase never waives a later
phase.

### Phase 1: Local release-candidate verification

- Verify the worktree is fixed to the full release commit and contains no
  tracked, staged, unmerged, or untracked release changes.
- Run the complete Python suite in the project's pinned Python environment.
- Run frontend tests and the production frontend build from a clean dependency
  install.
- Run repository release-contract tests and validate both Docker build inputs.
- Record exact commands, exit codes, and relevant version identities.

Any failure stops before the branch is pushed or credentials are changed.

### Phase 2: Registry-bound CI verification

- Revalidate the protected production TCR credential without printing it.
- Stream the username and password separately into GitHub Secrets; do not
  store them in a workspace file, command argument, transcript, or design
  artifact.
- Dispatch `publish-images.yml` for the exact release branch and record the
  numeric run ID immediately.
- Verify the run's workflow name, `headSha`, branch, status, conclusion, and
  URL before trusting it.
- Accept only `ready` or `ready_with_deferred_ghcr`. The latter is allowed only
  when both TCR components are published and GHCR was deferred after exactly
  five classified network failures. Authentication, permission, tag conflict,
  manifest, digest, and non-network failures are fatal.
- Download the exact run artifact, verify the canonical manifest against the
  full commit, and record its SHA-256.

No production slot is changed if this phase fails.

### Phase 3: Inactive blue-slot real-environment verification

- Capture the active green release, active BM25 schema/artifact identity,
  active Milvus collection, protected image digests, and rollback snapshot.
- Transfer the release manifest and same-commit runtime bundle, then verify
  their bytes on the server.
- Pull both digest-qualified TCR images and verify their `RepoDigests`.
- Run the provided deployment preflight for the blue slot.
- Start blue on its distinct loopback ports while green continues serving
  production traffic.
- Exercise blue directly through the server's local ports against the real
  production dependencies. Tests cover health, ordinary knowledge queries,
  Thread A routing and composite questions, citations, SSE completion, Wiki
  media delivery, and Thread B compatibility with the existing BM25 v2
  artifact.
- Confirm that the tests caused no corpus rebuild, embedding call, Milvus
  write, BM25 pointer change, media migration, or database migration.

Any failure leaves green active. Blue may remain stopped or isolated for
diagnosis; it must not receive public traffic.

### Phase 4: Traffic switch and immediate regression

- Atomically switch Caddy from green to blue with the checked-in switch tool.
- Confirm the active state is `sha-daf3fe8` and public routing reaches the new
  blue containers.
- Repeat the critical smoke suite through the public production route.
- Compare BM25 and Milvus identities with the pre-deployment capture.
- Observe container health, restart counts, server error responses, and
  relevant application logs during a bounded stabilization window.

If a critical smoke check, identity comparison, or health check fails, invoke
the checked-in rollback operation immediately and verify that green
`sha-1ec7752` is serving again.

## 6. Test coverage and success criteria

The deployment is successful only when all of the following are true:

- The GitHub run is successful and bound to the full release commit.
- The release manifest is canonical, verified, and hash-recorded.
- Both TCR components are published; GHCR is published or meets the narrowly
  defined deferred-network state.
- The blue backend and frontend use the manifest's digest-qualified images and
  remain healthy.
- Local-port and public-route smoke suites pass.
- Thread A routing and composite-answer behavior works with complete citations
  and terminal SSE behavior.
- Thread B loads and runs compatibly with the unchanged BM25 v2 artifact.
- The BM25 schema/artifact identity and Milvus collection name match their
  pre-deployment values exactly.
- The production active release is `sha-daf3fe8`.
- The previous green release and snapshots remain available for rollback.

If any item is missing, the outcome is not reported as successfully deployed.

## 7. Safety and non-goals

- Do not release the current `main` tree or any later C, D0, or E changes.
- Do not modify, stage, stash, clean, reset, or commit the user's four unrelated
  document changes.
- Do not rebuild, upload, or activate a BM25 v3 artifact.
- Do not run corpus projection, embedding, Milvus writes, media migration,
  database migration, or production data cleanup.
- Do not print, persist, or commit TCR passwords, GitHub tokens, application
  secrets, or Docker auth payloads.
- Do not accept mutable image tags without their verified digest.
- Do not remove the previous production release during this change window.
- Do not widen the release to fix unrelated application behavior discovered
  during deployment. Stop or roll back, diagnose, and obtain a separately
  reviewed fix.

## 8. Evidence and handoff

The release record must include:

- release branch and full commit;
- local verification commands and exit codes;
- GitHub workflow run ID, URL, workflow name, branch, `headSha`, status, and
  conclusion;
- release manifest path, SHA-256, state, and digest-qualified component refs;
- server release directory and runtime-bundle identity;
- preflight, inactive-slot smoke, switch, public smoke, and stabilization
  results;
- pre/post active slot, release, BM25 identity, and Milvus collection;
- rollback availability and, if invoked, rollback verification.

The final user report must distinguish image publication, inactive-slot
deployment, traffic activation, and post-activation verification. It may claim
"A/B is online" only after all four stages are complete.
