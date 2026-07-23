# Task 9 Report: Host Caddy and Blue/Green Operations

## Status

Implemented the host Caddy route and blue/green control-plane scripts without
performing a server deployment, DNS change, application image pull, Compose
`up`, or host Caddy reload.

## RED evidence

The first Task 9 test run was:

```text
conda run -n 1999wiki python -m pytest -q tests/test_deploy_scripts.py
22 failed, 1 warning
```

Every failure was the expected missing-file/control failure. Incremental RED
cycles also proved:

- `smoke-test.sh` was missing before the candidate/public-base behavior test;
- preflight did not initially reject quoted-empty secrets or require the active
  RAG pointer;
- preflight did not initially export the protected Caddy environment before
  validating the Caddyfile.

## GREEN implementation

Created:

- `deploy/Caddyfile`
- `deploy/caddy/active-upstream.caddy.example`
- `deploy/env/caddy.env.example`
- `deploy/bin/preflight.sh`
- `deploy/bin/deploy.sh`
- `deploy/bin/switch.sh`
- `deploy/bin/rollback.sh`
- `deploy/bin/smoke-test.sh`
- `deploy/bin/cleanup.sh`
- `tests/test_deploy_scripts.py`

The controls use explicit production defaults under `/srv/1999wiki` and
`/etc/caddy`, while environment overrides make deterministic isolated tests
possible.

Security and failure-order properties include:

- protected `APP_ENV_FILE` resolution outside Git, `.example` rejection, Linux
  mode `0600`, and root/current-user ownership;
- nonempty MinIO, MySQL, and API-key checks without value disclosure, including
  rejection of quoted-empty and unresolved-placeholder values;
- exact paired GHCR repositories, identical immutable `sha-[0-9a-f]{7}` tags,
  and release-argument agreement;
- existing RAG active pointer, disk, memory, Docker/Compose/Caddy/curl/python,
  external network, healthy infra, valid app config, and unused target project;
- no validation-time data-directory or service creation;
- candidate pull/start/readiness/smoke before switch, with candidate stop on
  failure;
- full temporary Caddy config validation before atomic fragment replacement;
- automatic old-fragment reload restoration on switch failure;
- active/previous release state recording before the old app is stopped;
- rollback starts only the recorded previous app, verifies it, restores the
  recorded fragment, and never references infra Compose;
- cleanup requires an exact confirmation and only removes one inactive app
  project plus the exact paired release images, without volumes or global
  pruning.

## Behavioral test evidence

Docker-isolated command stubs and temporary Linux files prove:

- successful preflight is read-only and secret-free;
- checked examples, mode `0644`, wrong repositories, quoted-empty secrets, and
  missing RAG pointers fail closed without leaking sentinel values;
- a failed candidate smoke test occurs after exact pulls/start and triggers
  candidate stop without any Caddy reload;
- a failed switch reload restores the prior fragment, reloads it, and does not
  write active state;
- candidate app checks use the loopback candidate origin while projected media
  retrieval uses the public host origin;
- cleanup with the wrong confirmation issues no Docker command, and successful
  cleanup contains only the named app project and exact images.

Fresh final regression:

```text
conda run -n 1999wiki python -m pytest -q \
  tests/test_deploy_scripts.py \
  tests/test_production_compose.py \
  tests/test_docker_packaging.py

84 passed, 1 warning in 12.72s
```

The warning is the pre-existing Starlette/httpx deprecation warning.

## ShellCheck evidence

```text
docker run --rm -v "${PWD}/deploy:/deploy:ro" \
  koalaman/shellcheck:v0.10.0 \
  /deploy/bin/preflight.sh \
  /deploy/bin/deploy.sh \
  /deploy/bin/switch.sh \
  /deploy/bin/rollback.sh \
  /deploy/bin/smoke-test.sh \
  /deploy/bin/cleanup.sh
```

Result: exit 0 with no findings.

## Caddy evidence

Validated only mounted repository files, not the host:

```text
docker run --rm \
  -e SITE_ADDRESS=:80 \
  -e MINIO_PROXY_UPSTREAM=127.0.0.1:19000 \
  -v "${PWD}/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v "${PWD}/deploy/caddy/active-upstream.caddy.example:/etc/caddy/active-upstream.caddy:ro" \
  caddy:2.11.4-alpine \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Result: `Valid configuration`. Caddy emitted the expected warning that `:80`
is HTTP-only; using a domain in `SITE_ADDRESS` enables normal automatic HTTPS.

## Self-review

- All six scripts use `set -Eeuo pipefail`, bounded network operations, quoted
  variables, safe temporary cleanup, and name-only diagnostics.
- No script contains Docker container inspect, environment dumps, global prune,
  volume prune, or `down -v`.
- Switch/rollback temp configs replace exactly one configured active import and
  validate the complete Caddy config before changing the live fragment.
- Failure traps were behaviorally exercised rather than only asserted as text.
- `git diff --check` passed.

## Concerns

- The existing container frontend Caddy configuration handles `/api/*` without
  stripping `/api`, while the Backend routes are `/ask`, `/ask/stream`, and
  `/api/wiki/*`. The Task 9 smoke test deliberately calls the browser-facing
  `/api/ask` and `/api/ask/stream` paths, so a candidate with that mismatch will
  fail closed before switching. Fixing the prior-task container routing was
  outside the requested Task 9 file scope.
- The only test warning is an existing Starlette/httpx deprecation warning.

## Fix wave: reviewer findings

The rejected first pass was reworked around one shared, fail-closed operations
control plane rather than independent script-local state:

- `ops_helper.py` is now the only non-evaluating parser and validator for
  release, app, infra, Caddy, snapshot, active-state, transaction-journal,
  Compose-status, fragment, and health inputs. It rejects duplicate/unexpected
  keys, quotes, whitespace, and unresolved `${...}` values without `source` or
  `eval`.
- `ops-common.sh` owns the global nonblocking `flock`, immutable mode-`0600`
  snapshots, exact Compose identity checks, Caddy service readability and
  metadata preservation, atomic fsync-backed replacements, and the durable
  `prepared` / `traffic_installed` / `state_committed` journal.
- Deploy establishes its partial-candidate cleanup responsibility immediately
  before Compose `up`; any partial `up` failure stops the named candidate
  services.
- Switch takes only `SLOT RELEASE_SNAPSHOT`, derives all ports/images/app
  configuration from the validated snapshot, and repeats readiness plus smoke
  under the inherited operations lock.
- Rollback regenerates traffic from strictly reconciled previous metadata,
  verifies the previous project/images before switching, atomically swaps
  active/previous state, and restores the old fragment/state if reload fails.
- Cleanup requires a complete v2 active state and exact active-fragment
  agreement, and protects the active deployment, the recorded rollback target,
  and all images used by either even when their containers are stopped.
- The smoke test follows redirects, requires a hashed asset with a final 2xx
  non-HTML response, derives media projection only from the snapshotted
  `MEDIA_PUBLIC_BASE_URL`, and parses SSE blocks so one `done` event is last and
  no `error` event occurs.
- The container Caddyfile now preserves `/health`, `/api/wiki/*`, and
  `/api/media/*`, strips `/api` for Backend `/ask` and category routes, and
  places the SPA fallback last.

### Fix-wave RED/GREEN evidence

The new reviewer-safety static tests started at `5 failed`. After the shared
control-plane implementation and script rewiring, the focused deployment and
packaging suite finished:

```text
pytest -q tests/test_deploy_scripts.py tests/test_docker_packaging.py
87 passed in 50.86s
```

The Linux-container behavioral tests now cover:

- global lock contention;
- strict placeholder rejection without ambient expansion;
- immutable snapshot/TOCTOU behavior and wrong-slot rejection;
- candidate cleanup when Compose `up` partially fails;
- fragment ownership/group/mode preservation (`0:1234:0640`) for a
  group-readable Caddy service identity;
- missing, malformed, divergent, stopped-active, and wrong-confirmation
  cleanup states;
- real `SIGKILL` injection before state commit and after state commit, followed
  by deterministic journal reconciliation;
- successful rollback state swapping and reload-failure restoration;
- HTML asset fallback, nonterminal SSE, and unrelated media-base rejection;
- actual Caddy 2.11.4 request routing for health, Wiki, media, Ask, and category
  paths.

Fresh full repository regression:

```text
PYTHONPATH=. pytest -q
1646 passed, 2 skipped, 2 warnings in 124.55s
```

Both warnings are the existing FastAPI `on_event` deprecations.

### Fix-wave static and container validation

All seven shell files passed `bash -n`. ShellCheck v0.10.0 passed with no
findings using external source resolution for `ops-common.sh`.

The mounted host Caddy configuration passed Caddy 2.11.4 validation with
`Valid configuration`; no host Caddy command was run.

The frontend was rebuilt without `--pull`, using cached Node/Caddy layers:

```text
docker build --progress=plain -f docker/Dockerfile.frontend \
  -t 1999wiki-frontend:task9-review .
```

Resulting manifest-list digest:
`sha256:cb95f1d3db91c34410dfaee8573b87014f58ea38da103f61e345b66ec264b704`.
The Caddyfile copied into that image also passed Caddy 2.11.4 validation.

`git diff --check` passed. No live Compose project, host Caddy service, DNS, or
production deployment state was read or changed.

### Remaining concerns

- Crash recovery is durable at file/journal boundaries and tested with real
  process kills; like any userspace design, guarantees still depend on the
  underlying filesystem honoring fsync and atomic rename semantics.
- The full Windows pytest run printed transient native Torch DLL access-
  violation diagnostics during collection, but collection continued and the
  run completed with exit code 0 and the result above.
