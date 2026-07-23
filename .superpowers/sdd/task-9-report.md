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
