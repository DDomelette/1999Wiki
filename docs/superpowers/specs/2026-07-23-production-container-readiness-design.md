# 1999Wiki Production Container Readiness Design

**Status:** Final implementation design. The historical migration document is
an initial draft; production operators must use this design together with the
[implementation plan](../plans/2026-07-23-production-container-readiness.md)
and the [production deployment runbook](../../codex/production-deployment-runbook.md).

## 1. Purpose

This design turns the migrated 1999Wiki repository into a reproducible,
environment-configured, two-image release that can be pulled from GHCR and
switched between blue and green application slots on the existing server.

The server runs the application and its local infrastructure only. It does not
build images, crawl source data, generate embeddings, or read normal runtime
media from COS. COS remains a backup destination managed by the existing backup
thread.

## 2. Fixed constraints

- Backend image: `ghcr.io/ddomelette/1999wiki-backend:sha-<7-char-git-sha>`.
- Frontend image: `ghcr.io/ddomelette/1999wiki-frontend:sha-<7-char-git-sha>`.
- Images are immutable. Publication is serialized per full commit and refuses
  to push when either target `sha-*` tag already exists.
- Every published release emits `release-manifest.json`, binding the reviewed
  full commit, both exact tag refs, and both registry digests. Production uses
  the resulting `tag@sha256:...` identities; tag-only refs are invalid.
- GitHub Actions builds both images from the same clean Git commit and pushes
  them only when manually triggered.
- The server pulls images from GHCR and never builds them.
- MySQL, Milvus, etcd, MinIO, and RAG runtime artifacts live outside application
  images in persistent server directories.
- Blue and green application slots share the same infrastructure and data.
- Both Backend slots use one Uvicorn worker.
- `/wiki-preview/*`, the React `wiki-preview` component tree, `kimi_web/`,
  Streamlit, Gradio, and the legacy static HTML frontend are retired rather than
  redirected or shipped.
- The formal UI is the React application under `frontend/react-app`.
- The 17 referenced `frontend/react-app/public` shell assets stay in the
  Frontend image. The required MP4 remains a Git LFS object.
- Production media is served from the server's MinIO through the public
  same-origin `/media/` route. Runtime operation does not depend on COS.

## 3. Release architecture

### 3.1 Long-lived infrastructure

`deploy/compose.infra.yml` owns:

- MySQL 8
- MinIO
- etcd
- Milvus Standalone

All four services use explicit image versions, `restart: unless-stopped`,
healthchecks, and host bind mounts under `/srv/1999wiki/`. Milvus depends on
healthy etcd and MinIO. Infrastructure is attached to the external Docker
network `1999wiki-infra`.

MinIO API is bound to a host loopback port for the host Caddy media proxy.
MinIO Console and Attu are disabled by default. Any temporary diagnostic UI is
loopback-only and enabled through an explicit Compose profile.

Production secrets have no fallback passwords. Compose uses required-variable
interpolation so missing MySQL, MinIO, or GHCR credentials fail before container
startup.

### 3.2 Blue and green application slots

`deploy/compose.app.yml` contains one Backend service and one Frontend service.
The same file is instantiated twice with different Compose project names and
release environment files:

```text
docker compose -p 1999wiki-blue  --env-file releases/<sha>/blue.env  up -d
docker compose -p 1999wiki-green --env-file releases/<sha>/green.env up -d
```

Each slot receives distinct loopback diagnostic/frontend ports but joins the
shared `1999wiki-infra` network. The Frontend container proxies `/api/*` and
`/health` to the Backend container in the same Compose project. The host Caddy
proxies public application traffic to the active Frontend loopback port.

The old slot remains available during candidate validation. After a successful
switch it is stopped but not immediately removed. Rollback restarts the old slot
if necessary and atomically restores the previous Caddy upstream.

### 3.3 Host Caddy

The host Caddy configuration reads:

```env
SITE_ADDRESS=:80
MINIO_PROXY_UPSTREAM=127.0.0.1:19000
```

Before DNS binding, `SITE_ADDRESS=:80` supports IP-based HTTP validation. After
the domain's A/AAAA records point to the server and ports 80/443 are reachable,
the operator changes only `SITE_ADDRESS` to the domain. Caddy then manages HTTPS.

The public routes are:

```text
/media/*  -> local MinIO API, with /media stripped
/*        -> active Frontend slot
```

The active Frontend upstream is stored in a small imported Caddy fragment.
Switch and rollback scripts validate the candidate configuration, replace the
fragment atomically, and reload Caddy.

## 4. Runtime configuration contract

Images contain safe local-development defaults only. Production values enter at
container startup through an environment file outside Git.

Backend consumes:

```env
MILVUS_URI=http://standalone:19530
MILVUS_DB_NAME=reverse1999_rag
MILVUS_COLLECTION_NAME=text_child_bge_m3_shadow_crawler_v3_20260721t051246z
MINIO_ENDPOINT=minio:9000
MINIO_SECURE=false
MINIO_ACCESS_KEY=<secret>
MINIO_SECRET_KEY=<secret>
MINIO_BUCKET=reverse1999-assets
MEDIA_PUBLIC_BASE_URL=/media
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=reverse1999_wiki
MYSQL_USER=<runtime-user>
MYSQL_PASSWORD=<secret>
HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
```

`MEDIA_PUBLIC_BASE_URL` accepts either:

- a same-origin absolute path beginning with `/`, with `/media` as the
  production default; or
- an absolute `http://` or `https://` base URL for a future dedicated media
  domain.

It rejects query strings, fragments, credentials, traversal segments,
backslashes, and non-HTTP schemes.

The Backend fails readiness when required production endpoints, credentials, or
the active RAG artifact closure are missing. It does not silently fall back from
container service names to loopback addresses.

## 5. Media URL projection

Database and RAG artifact rows retain stable `object_key` values. Stored `url`
values are treated as build-time evidence, not as browser-facing authority.

One shared URL projector builds the response URL from:

```text
MEDIA_PUBLIC_BASE_URL + MINIO_BUCKET + object_key
```

Examples:

```text
/media/reverse1999-assets/reverse1999/portrait/ab/example.webp
https://media.example.com/reverse1999-assets/reverse1999/portrait/ab/example.webp
```

The projector percent-encodes the bucket and key without changing `/`
separators. Wiki list thumbnails, Wiki detail media, RAG media panels, voice
pagination, and any public media DTO use the same projector. A record without a
safe `object_key` is omitted instead of leaking a stored `127.0.0.1` URL.

No migration rewrites hash-pinned active artifacts in place. No deployment
requires rebuilding the active RAG artifacts merely to change a domain.

## 6. Milvus category counting

`_count_by_category` stops using `query(limit=100000)`. The Milvus path consumes
`query_iterator` with bounded batches and `limit=-1`, counts returned IDs, and
always closes the iterator. This avoids the 16,384 query-window limit while
remaining compatible with the Milvus client already used elsewhere in the
repository.

Query errors remain visible in logs and health diagnostics. The categories
endpoint no longer converts an operational counting failure into an unexplained
zero without evidence.

## 7. Frontend retirement and build boundary

The following tracked runtime sources are deleted:

- `kimi_web/`
- `frontend/streamlit_app.py`
- `frontend/gradio_app.py`
- `frontend/html/`
- `frontend/react-app/src/components/wiki-preview/`
- preview-only unit and E2E tests
- `/wiki-preview` route and `kimi-preview` variants/imports in formal Wiki
  components
- preview-only health UI and CSS

Formal `/wiki/*`, the suggested-question feature, mobile layouts, the 17 public
assets, and real Wiki API behavior remain.

The Frontend Docker build copies the complete `frontend/react-app` build input,
runs `npm ci` and `npm run build`, then copies only `dist/` and the Frontend
Caddy configuration into the runtime image. `node_modules`, source tests,
Playwright browsers, logs, and local build output never enter the runtime image.

## 8. Python dependency boundary

Python 3.11 is the only Backend build/runtime version.

Requirements are split into:

```text
requirements/runtime.in
requirements/runtime.lock.txt
requirements/dev.in
requirements/dev.lock.txt
```

The runtime input contains only packages imported by Backend request handling,
configuration, RAG retrieval, Wiki access, MinIO projection, and healthchecks.
It excludes Streamlit, Gradio, Playwright, pytest, crawler packaging tools, and
vector-generation-only dependencies.

The development input includes the runtime input plus test and repository
tooling. Both lock files pin transitive versions. The Backend Dockerfile installs
only the runtime lock.

The root `requirements.txt` remains a documented compatibility entry point for
local development and delegates to the development lock.

## 9. Image contents

### 9.1 Backend image

The Backend image contains only:

- `backend/`
- runtime portions of `src/`
- `config/` files required at runtime
- the pinned runtime Python environment
- a non-root application user
- a container healthcheck

It excludes raw crawler data, crawler/browser source packages, embedding/build
scripts, evaluation tools/results, tests, local logs, backups, credentials,
MySQL/Milvus/MinIO data, and RAG artifact payloads.

The RAG closure is mounted read-only at `/runtime/rag/huiji`. It is non-secret:
the root and necessary ancestors of the manifest-selected closure use mode
`0755`, and exactly its 11 regular files use mode `0644`, allowing the unrelated
non-root Backend identity to traverse and read them without write access.
Undeclared files and directories retain their modes. Preparation consumes a
successful verifier result, requires exactly 11 files totaling 222,789,868
bytes, and rejects symlinks; preflight checks this permission contract. The
current closure contains exactly the active pointer, two activation evidence
files, the build manifest, parent/child blocks, media rows, two BM25 indexes,
and the media schema/manifest: 11 files totaling about 212.47 MiB.

### 9.2 Frontend image

The Frontend runtime image contains only:

- the React production build
- the Frontend Caddyfile
- health/proxy configuration

The current 17 shell assets total about 168.21 MiB and are expected to dominate
the image. Bulk MinIO media is not duplicated into this image.

## 10. Build context and clean-checkout rules

The root `.dockerignore` excludes all non-image inputs, including:

- `.git`, `.worktrees`, IDE metadata, caches, and local environments
- `node_modules`, existing `dist`, test output, logs, backups, and `.env`
- `data/`, `vectorstore/`, local infrastructure volumes, and runtime databases
- crawler sources and packaging assets from the Backend image through explicit
  Dockerfile copy boundaries

Git attributes enforce CRLF checkout for tracked `.bat` and `.cmd` launchers.
This is required because the clean worktree baseline proved their existing
line-ending contract was not preserved by Git.

Tests that claim to be isolated must create or inject their own fixture
configuration and artifacts. They may not pass only because ignored data exists
in the developer's main checkout.

## 11. GHCR workflow

`.github/workflows/publish-images.yml` uses `workflow_dispatch` and:

1. checks out the selected commit with Git LFS enabled;
2. verifies the LFS object is present;
3. installs Python 3.11 development dependencies;
4. runs the Python suite;
5. runs `npm ci`, the frontend suite, and the production build;
6. builds Backend and Frontend images from the same full SHA;
7. serializes publication by the full SHA and fails closed unless both exact
   `sha-<7-char-sha>` tags are absent;
8. pushes only those two exact tags to GHCR;
9. creates and uploads a machine-readable release manifest containing the full
   commit, exact tags, digests, and digest-qualified refs;
10. records the same attestable identities in the workflow summary.

The workflow receives `contents: read` and `packages: write`. It does not SSH to
the production server and does not deploy automatically.

## 12. Deployment scripts

Scripts under `deploy/` provide:

- preflight validation of Docker, Compose, disk, memory, environment files, and
  the target release;
- candidate-slot startup and health waiting;
- same-slot Frontend-to-Backend smoke checks;
- MySQL, Milvus, MinIO, Wiki, RAG, SSE, shell-asset, and media URL checks;
- atomic Caddy switch;
- rollback to the recorded previous slot;
- targeted cleanup after the observation period.

Release metadata contains the reviewed full commit and digest-qualified Backend
and Frontend refs. Its seven-character tags must both match the full commit.
After pull, operations validate each protected digest against local
`RepoDigests`; snapshots and active/previous state retain the digest-qualified
identity. Retirement queries the exact tag, refuses a mismatched local digest or
an indeterminate Docker result, removes only the verified identity, and confirms
absence before committing retirement state.

Scripts never run `docker compose down -v` and never run unrestricted
`docker system prune -a`. They do not print secret-bearing environment files or
full `docker inspect` output.

## 13. Error handling and observability

- Invalid environment values fail startup with the variable name and a
  non-secret reason.
- Missing credentials are reported as missing, never echoed.
- Backend `/health` distinguishes configuration, RAG closure, Milvus, MinIO, and
  MySQL readiness.
- Frontend container health verifies static serving and Backend proxy reachability.
- Compose services use bounded JSON-file log rotation.
- Candidate deployment aborts before Caddy switching if any required smoke check
  fails.
- Rollback owns a previous-slot restart until authoritative state commit.
  Identity, readiness, smoke, Caddy, or public-verification failure before that
  commit stops only the restarted candidate; post-commit failures never stop
  the active slot.
- Rollback does not modify persistent infrastructure or restore data.

## 14. Verification gates

Before any image is publishable:

- a clean worktree has no dependency on ignored source data;
- all `.bat` and `.cmd` line-ending tests pass;
- Python tests pass under Python 3.11;
- React unit tests and production build pass;
- `/wiki-preview`, `kimi-preview`, `KimiWiki`, `kimi_web`, Streamlit, Gradio,
  and legacy HTML runtime paths are absent from production inputs;
- `127.0.0.1:9002`, `127.0.0.1:19600`, and `limit=100000` are absent from
  production runtime decisions;
- media projection tests cover relative and absolute bases, encoding, unsafe
  keys, Wiki DTOs, and RAG DTOs;
- both Docker images build from a clean checkout with Git LFS;
- image inspection confirms forbidden directories and credentials are absent;
- production Compose renders with `docker compose config`;
- local smoke deployment validates same-origin `/media`, `/api`, `/health`, Wiki,
  RAG, and SSE routes.

## 15. Implementation sequence

1. Repair clean-checkout test isolation and Git line endings.
2. Retire preview and legacy frontend paths.
3. Add environment overrides and the shared media URL projector.
4. Apply the projector to Wiki and RAG response paths.
5. Replace the Milvus category count query.
6. Split and lock Python dependencies.
7. Add Dockerfiles, `.dockerignore`, and Frontend proxy configuration.
8. Add hardened infrastructure and application Compose files.
9. Add host Caddy and blue/green deployment scripts.
10. Add the manual GHCR workflow.
11. Run clean-checkout, image-build, Compose-render, and smoke verification.

## 16. Release verification closure

Task 12 closed the local release gate on 2026-07-26 without publishing images,
connecting to the production server, changing DNS, or mutating production data.
The verification used the real active RAG closure read-only and isolated,
named temporary Docker projects for all smoke-test writes.

The verified release-producing commit is `f71176d`. Both images were built
locally from that commit with the required immutable tag:

```text
ghcr.io/ddomelette/1999wiki-backend:sha-f71176d
sha256:7807a2a5cf4b86c5792bd940a7c30e4b400300b52fa90c99146e920d1dbc891b

ghcr.io/ddomelette/1999wiki-frontend:sha-f71176d
sha256:3dea7dd909ed9691d57755d8b6b8ca258fa5344b3c6ac35aa85839e5967275f4
```

These are local image IDs, not evidence of GHCR publication. The manual
publication workflow remains the authority for registry digests.

The final local gate passed:

- 1,737 Python tests, with four known platform skips;
- 238 React tests across 50 files;
- the React production build;
- both production Docker builds and runtime-content inspection;
- the real RAG closure at exactly 11 files and 222,789,868 bytes;
- isolated MySQL, MinIO, etcd, and Milvus health;
- the formal React shell and hashed asset, Backend readiness, Wiki
  health/list/detail, synchronous RAG, RAG SSE with one terminal `done`, and a
  same-origin non-HTML `/media/` object through Caddy.

The smoke gate exposed and closed one release blocker: activation artifact
validation assumed the development checkout prefix and rejected the approved
production relocation at `/runtime/rag/huiji`. The runtime now validates the
canonical manifest identity independently of that mount relocation.

The complete operator procedure is
[docs/codex/production-deployment-runbook.md](../../codex/production-deployment-runbook.md).
Live publication and deployment must wait for review of the whole release
branch and require separate operator authorization.
