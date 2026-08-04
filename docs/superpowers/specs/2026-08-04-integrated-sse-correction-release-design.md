# Integrated SSE Correction Release Design

**Date:** 2026-08-04
**Status:** Approved

## 1. Goal

Replace the currently active A/B-only production release with a corrected
release that contains:

- Thread A request routing and composite orchestration;
- Thread B Chinese BM25 analyzer compatibility;
- true incremental answer streaming over SSE;
- the main-page scroll, navigation, and chat-boundary repairs completed after
  the SSE merge; and
- the two packaging and CI portability corrections discovered during the
  A/B-only release.

The correction must exclude unfinished Thread C and all later experimental or
unmerged work. Production must continue to pull immutable, digest-qualified
images from TCR without requiring GitHub, GHCR, or a VPN.

## 2. Root cause being corrected

The active source commit `05ccd6ba0af157787b335ed299f8c26f5f2b3bfb`
was built from the exact A/B merge point
`daf3fe85390c534e0177c2eb06768b7f9ffc3a44`, plus packaging and CI-only
commits. That release deliberately excluded every later main-line change.

True SSE was merged immediately after the A/B point by
`2cbaef3a5c1235c95eba1cb18cd5e9f36ebd9dc6`, whose second parent is the
verified SSE implementation and test tip
`44cc589a358eacc4a99d947340b87adc3761a9f7`. Neither commit is an ancestor of
the active release. The previous smoke test only proved that the SSE endpoint
could return a valid terminal event; it did not prove incremental answer
chunks reached the browser.

## 3. Exact source boundary

### 3.1 Included base

The new release base is exactly:

`0993dbbad34cbdb06f9d6a5ffc5eae82cc8925f4`

This is the last first-parent main-line commit before Thread C documentation
and implementation begin. Its ancestry includes:

- A/B merge `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`;
- true SSE merge `2cbaef3a5c1235c95eba1cb18cd5e9f36ebd9dc6`;
- Backend preparation/finalization split and incremental model chunk delivery;
- cancellation, failure, correction, and pending-media streaming handling;
- Frontend phase parsing and progressive answer display;
- true-delivery SSE regression tests;
- main-section navigation and data-section scroll repairs;
- chat and viewport boundary stabilization; and
- the associated responsive/WebKit regression tests through `0993dbb`.

### 3.2 Required release-only corrections

Apply these two existing commits on top of `0993dbb`, preserving their changes
without introducing unrelated source:

1. `b24d33a3cabee974389356df6ed543b816d3f943` — keep provenance imports inside
   the Backend image runtime boundary and add the Docker packaging regression.
2. `05ccd6ba0af157787b335ed299f8c26f5f2b3bfb` — guard Windows-only subprocess
   detach flags so the supervisor tests remain portable on Linux CI.

The resulting commit identity is determined only after both changes apply and
the release worktree is clean.

### 3.3 Explicit exclusions

Exclude all commits after `0993dbb` from the main first-parent chain, including:

- Thread C story/topic/media projection design, implementation, evidence, and
  integration merge `33e5837`;
- story-segment follow-on work and the `codex/rag-e-story-segment` branch;
- D0 or other RAG evaluation work not present at `0993dbb`;
- the unmerged supervisor-terminal-readability branch;
- every dirty or untracked file in the main workspace; and
- documentation commits created solely to operate or report the previous
  A/B-only production release.

No corpus, embedding, BM25, Milvus, MinIO, media, or database migration is part
of this release.

## 4. Approaches considered

### 4.1 Safe historical boundary plus two corrections — selected

Create a new isolated release worktree at `0993dbb`, then apply the two proven
release-only corrections. This gives a simple ancestry proof for every
included feature and a simple exclusion proof for Thread C.

### 4.2 Publish current `main`

Rejected because current `main` already contains a partial Thread C merge and
later story-segment preparation. Reverting C from current `main` would create
a large negative patch with substantially weaker exclusion evidence.

### 4.3 Cherry-pick individual SSE and UI commits onto the A/B release

Rejected because the SSE and scroll work are multi-commit dependency chains.
Selecting them commit by commit risks omitting an intermediate contract,
regression test, or refactor that later commits assume.

## 5. Release architecture

1. Create an isolated branch and worktree from exact commit `0993dbb`.
2. Apply the packaging correction and Linux CI portability correction.
3. Prove the branch contains the required A/B and SSE ancestors and excludes
   the first Thread C commit `4c312c52ee7b1e018e4608aeda741fdc4bba9a79`.
4. Run full Python, Frontend unit, Frontend production-build, targeted SSE,
   responsive UI, packaging, and Linux-container gates.
5. Build Backend and Frontend images for `linux/amd64` and verify the Backend
   can import its production entry point inside the built image.
6. Push both exact images directly from the authenticated local Docker client
   to TCR, inspect their registry digests, and create a canonical
   `1999wiki.release/v2` manifest. GHCR remains deferred.
7. Install only the manifest and generated release identity on the server;
   production pulls the images from TCR by digest.
8. Deploy into the inactive green slot, run candidate smoke and incremental
   SSE tests against real production dependencies, then atomically switch
   Caddy from blue to green.
9. Observe the public route and both containers, retaining the prior blue
   release as the protected rollback target.

## 6. Production slot lifecycle and destructive boundary

Current authoritative state is:

- active blue: `sha-05ccd6b`;
- previous green: `sha-1ec7752`.

The green slot is both inactive and recorded as the current previous release,
so it cannot be reused until its exact stopped deployment is retired. After a
fresh state check, retirement is authorized only for green
`sha-1ec7752` using the exact confirmation:

`remove-green-sha-1ec7752`

Retirement may remove its stopped application containers, green network, and
safe image tags. Its immutable release manifest and protected deployment
snapshot must remain. It must not affect the active blue containers, shared
Milvus/MySQL/MinIO/etcd services, RAG artifacts, or Caddy routing.

Failure behavior is intentionally asymmetric:

- before the switch, any failure leaves active blue `sha-05ccd6b` serving;
- after the switch, any public regression failure invokes the checked-in
  rollback transaction and restores blue `sha-05ccd6b`;
- after a successful switch, blue `sha-05ccd6b` becomes the new protected
  previous release and must not be cleaned up during this task.

## 7. Verification contract

### 7.1 Source and packaging

- exact base and ancestry checks pass;
- the release worktree contains no uncommitted files;
- the four pre-existing main-workspace document changes remain untouched;
- the complete Python suite passes;
- targeted provenance, BM25, request-routing, RAG execution, and SSE suites
  pass;
- Frontend unit tests and production build pass;
- the targeted Playwright responsive/navigation suite passes with its pinned
  browser runtime; inability to run that suite blocks release rather than
  silently weakening the gate;
- both Docker production builds pass for `linux/amd64`; and
- `import backend.main` succeeds inside the Backend image.

### 7.2 True-streaming acceptance

The release is not accepted merely because `/api/ask/stream` ends with a
`done` event. A deterministic test must prove all of the following:

- at least two non-empty `token` events are received before `done`;
- concatenating the `token` payloads produces the scripted draft answer;
- sources and final answer/citation state remain consistent with the terminal
  payload;
- the Frontend parser applies `status`, `token`, `answer_replace`, and `done`
  events in order; and
- cancellation and failure paths do not commit incomplete conversation state.

The inactive green candidate must pass the server smoke suite plus a direct
SSE event-order probe before any traffic switch. The public route must repeat
the event-order probe after switching.

### 7.3 A/B and data identity preservation

- the known composite benchmark produces the expected social, assistant-meta,
  and knowledge-base subtasks;
- public readiness and Wiki endpoints pass;
- the active BM25 artifact SHA, schema `huiji.bm25-index/v2`, active build SHA,
  and Milvus collection exactly match the pre-deployment capture; and
- no index build, corpus build, embedding, upload, or activation command runs.

### 7.4 Stability and rollback

- Backend and Frontend remain healthy with restart count 0 throughout a
  10-minute observation window sampled every 30 seconds;
- public readiness stays green and recent critical logs remain empty;
- the final active state identifies the new green release; and
- previous blue `sha-05ccd6b` retains valid snapshots and digest-qualified TCR
  image references for rollback.

## 8. Delivery records

The task produces:

- a clean, pushed correction release branch;
- immutable Backend and Frontend TCR image references with registry digests;
- a canonical manifest installed under the new server release directory;
- an updated authoritative blue/green state only after successful smoke and
  switch transactions; and
- a production correction report containing actual commit, digest, test,
  observation, and rollback evidence.

Success means users can visibly observe incremental answer output in
production while A/B behavior remains present and Thread C remains absent.
