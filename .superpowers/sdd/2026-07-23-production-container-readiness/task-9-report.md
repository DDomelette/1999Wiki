# Task 9 Report — Production Blue/Green Operations

## Scope and operating boundary

Task 9 adds and hardens the host-Caddy blue/green control plane for the
production container deployment. The implementation operates on the two app
projects (`1999wiki-blue` and `1999wiki-green`) and their exact release images.
Shared infrastructure is never retired by these controls.

All work and verification in this task used test harnesses, read-only
configuration validation, frontend builds, or locally tagged build images.
No live Compose project, host Caddy process, DNS record, production server, or
production state directory was changed.

## Fix round 2 result

The eight open review findings against `c59c472` are addressed as follows.

### 1. Repeatable, crash-recoverable lifecycle

- Active state schema version 3 uses `PREVIOUS_AVAILABLE` as explicit rollback
  authority. When it is `0`, every previous field must be canonically empty.
- Cleanup accepts only the exact recorded previous slot/release/project,
  verifies its frozen snapshots and images, refuses active or shared images,
  and requires the exact confirmation string
  `remove-<slot>-<sha-release>`.
- `retirement.env` is an exact-schema, mode-0600 journal with phases
  `prepared`, `resources_removed`, and `state_committed`.
- Retirement removes only the recorded app project and exact images, verifies
  their absence, atomically commits state with no previous authority, and then
  durably removes the journal and obsolete fragment backup.
- Startup reconciliation is idempotent on either side of every retirement
  crash point. A completed retry can safely acknowledge the original cleanup
  request.
- Preflight refuses a slot while it is still the rollback target and permits it
  after retirement. The end-to-end regression performs:
  blue active → switch green → retire blue → preflight blue.

### 2. Inherited lock proof and no-follow lock acquisition

- Mutating entry points re-exec through `ops_helper.py lock-exec`, which opens
  the state root and canonical `operations.lock` with no-follow semantics,
  acquires a nonblocking `flock`, and passes the real open file description as
  inherited fd 9.
- An inherited process validates descriptor type, owner/mode, canonical
  device/inode identity, and actual lock ownership. `OPS_LOCK_HELD` alone is
  not trusted.
- Tests cover real inheritance, concurrent contention, a separately opened
  forged fd, a wrong inode, and a lock-file symlink without modifying its
  target.

### 3. Snapshot and state path symlink containment

- State roots must be real mode-0700 directories owned by root/current user.
- Protected files, snapshots, transaction artifacts, retirement artifacts,
  atomic destinations, and durable unlinks reject symlinks in every existing
  path component.
- Snapshot creation validates components before writing and uses mode-0700
  snapshot directories. The escape regression proves that a symlinked
  `snapshots` component causes failure and no outside file is created.

### 4. Strict environment parsing

- The parser rejects both bare `$NAME` and braced `${NAME}` placeholders.
- Release and Caddy files require exact approved key sets.
- App and infra files reject every unexpected key while retaining their
  explicitly supported optional keys.
- Required values remain nonempty and protected files retain the existing
  outside-repository, owner, mode, and `.example` rejection checks.
- `MEDIA_PUBLIC_BASE_URL` remains exactly `/media` or an absolute HTTPS base;
  absolute HTTP bases are rejected.

### 5. Media retrieval bound to the public origin

- Smoke validation resolves `/media/...` through `PUBLIC_BASE_URL`.
- An absolute configured media base and the returned media URL must both share
  the exact scheme/host/port origin of `PUBLIC_BASE_URL` and remain under the
  configured media path.
- The retrieval request is therefore made through the tested public host, not
  an unrelated CDN or service endpoint.

### 6. Post-commit candidate safety

- State commit and housekeeping are separate. After `active.env` and the Caddy
  fragment commit, journal unlink, obsolete-backup removal, previous-project
  stop, and status printing are warning-only housekeeping.
- Transaction reconciliation now durably removes the journal before deleting
  artifacts it references. A failed journal unlink therefore leaves a valid,
  retryable journal.
- The parent deploy error trap reconciles first, then validates authoritative
  active state and fragment identity. It does not stop a candidate that a child
  committed even if the child later exits nonzero and housekeeping
  reconciliation also returns nonzero.
- Regressions inject transaction unlink failure, old-project stop failure, and
  child nonzero after commit.

### 7. Recovery validation before traffic mutation

- Transaction journals record the old fragment uid, gid, and mode.
- Journal validation checks exact keys, owner/mode, contained canonical
  backups, fragment metadata, and fragment semantics against the validated old
  state active frontend port.
- With no old state, the fragment must be exactly one loopback
  `reverse_proxy` directive.
- Reconciliation cannot install the old fragment or reload Caddy until these
  checks pass. The corrupt-backup regression observes unchanged candidate
  traffic, no recovery reload, and a retained journal.

### 8. Exact orphan cleanup and superseded history

- Obsolete `tx-gen-*-old-{fragment,state}` artifacts are removed only when
  neither active state nor a surviving journal references them.
- Cleanup Docker behavior is verified from real script execution: one exact
  inactive app project, two exact images, no infra project, no volumes, and no
  global prune.
- Historical success statements associated with the initial `652d501` and
  fix-round-1 `c59c472` controls are superseded for the areas listed above.
  Those revisions did not yet provide the final retirement protocol, real
  inherited-lock proof, full no-follow containment, strict placeholder/key
  rules, same-origin media proof, or post-commit parent safety. The evidence in
  this report applies to the final fix-round-2 tree.

## Files changed in fix round 2

- `deploy/bin/ops_helper.py`
- `deploy/bin/ops-common.sh`
- `deploy/bin/preflight.sh`
- `deploy/bin/deploy.sh`
- `deploy/bin/switch.sh`
- `deploy/bin/rollback.sh`
- `deploy/bin/smoke-test.sh`
- `deploy/bin/cleanup.sh`
- `tests/test_deploy_scripts.py`
- this report

The local exploratory plan
`docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md` is not part of
Task 9 delivery and is intentionally excluded from staging.

## Verification evidence

| Gate | Result |
| --- | --- |
| Focused operations suite | `69 passed, 1 existing dependency warning` |
| Full Python suite | `1661 passed, 2 skipped, 3 existing deprecation warnings` |
| Frontend Vitest | `50 files passed; 238 tests passed` |
| Frontend production build | `tsc && vite build` passed; existing >500 kB chunk advisory only |
| Python helper compile | `python -m py_compile deploy/bin/ops_helper.py` passed |
| Bash syntax | `bash -n` passed for all six entry scripts and `ops-common.sh` |
| ShellCheck | `koalaman/shellcheck:v0.10.0` passed for all six entry scripts and `ops-common.sh` |
| Host Caddy | Caddy 2.11.4 validation passed with the example active fragment; expected HTTP-only advisory for `SITE_ADDRESS=:80` |
| Frontend Caddy | Caddy 2.11.4 validation passed |
| Backend image | Cached production build passed; forbidden data/test paths absent; user `app`; no declared volumes |
| Frontend image | Cached production build passed; `/srv/index.html` present; source/node_modules absent; user `caddy`; no declared volumes |
| Diff hygiene | Final `git diff --check` is run immediately before staging |

## Remaining operational concerns

- This work deliberately does not substitute for a maintenance-window rehearsal
  on the target host. Before first production use, operators should back up the
  state directory and exercise switch, rollback, retirement, and a simulated
  interrupted retirement with the installed Docker and Caddy versions.
- The frontend production bundle still emits the existing advisory that its
  main JavaScript chunk is slightly above 500 kB after minification. This does
  not block Task 9 control-plane safety.
- The full Python suite emits existing FastAPI/Starlette deprecation warnings;
  they are outside the Task 9 deployment-script scope.
