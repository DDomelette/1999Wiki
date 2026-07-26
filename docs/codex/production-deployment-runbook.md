# 1999Wiki Production Deployment Runbook

## Scope and safety boundary

This runbook deploys reviewed, immutable Backend and Frontend images to the
single 4-core, 4-GiB RAM, 40-GiB system-disk server. The host is runtime-only:
it does not build images, crawl data, generate embeddings, run repository
tests, or install Node.js, Conda, Playwright, Codex CLI, COSCLI, or COS
credentials.

Use the Backend and Frontend identities from the workflow's
`release-manifest.json`. Each identity retains the exact
`sha-<7 lowercase hex>` tag and qualifies it with the protected registry
digest as `tag@sha256:<64 lowercase hex>`. The manifest's full commit must equal
the reviewed commit. Do not overwrite a `sha-*` tag. Do not use
`docker compose down -v`, unscoped `docker system prune -a`, or delete
infrastructure data as part of an application rollback.

The checked-in deployment files are a runtime bundle, not a source checkout.
Transfer the reviewed `deploy/` directory from the same branch as the image
commit to `/srv/1999wiki/runtime-bundle/deploy/`. Do not clone the development
repository onto the server.

## 1. One-time host preparation

The commands below assume a supported Debian/Ubuntu host and a root shell.
Install Docker Engine and the Compose v2 plugin from Docker's official
repository, and install Caddy from Caddy's official repository. Confirm the
actual installed tools:

```bash
docker version
docker compose version
caddy version
python3 --version
```

Create the runtime layout:

```bash
install -d -m 0750 /srv/1999wiki
install -d -m 0750 \
  /srv/1999wiki/runtime-bundle \
  /srv/1999wiki/mysql \
  /srv/1999wiki/minio \
  /srv/1999wiki/etcd \
  /srv/1999wiki/milvus \
  /srv/1999wiki/import-staging \
  /srv/1999wiki/releases
install -d -m 0755 /srv/1999wiki/rag-artifacts
install -d -m 0700 \
  /srv/1999wiki/protected \
  /srv/1999wiki/deploy-state
docker network inspect 1999wiki-infra >/dev/null 2>&1 ||
  docker network create 1999wiki-infra
```

After transferring the reviewed runtime bundle, make the operations scripts
executable:

```bash
chmod 0755 /srv/1999wiki/runtime-bundle/deploy/bin/*.sh
chmod 0755 /srv/1999wiki/runtime-bundle/deploy/bin/*.py
```

Install the host Caddy files:

```bash
install -o root -g root -m 0644 \
  /srv/1999wiki/runtime-bundle/deploy/Caddyfile \
  /etc/caddy/Caddyfile
install -o caddy -g caddy -m 0640 \
  /srv/1999wiki/runtime-bundle/deploy/caddy/active-upstream.caddy.example \
  /etc/caddy/active-upstream.caddy
install -d -m 0755 /etc/systemd/system/caddy.service.d
printf '%s\n' \
  '[Service]' \
  'EnvironmentFile=/srv/1999wiki/protected/caddy.env' \
  > /etc/systemd/system/caddy.service.d/1999wiki.conf
chmod 0644 /etc/systemd/system/caddy.service.d/1999wiki.conf
```

The initial upstream fragment may point to an inactive port. This is expected
until the first successful deployment atomically switches it.

## 2. Protected environment files

Create protected files from the checked-in examples, then replace every blank
credential and placeholder. Keep application credentials consistent with the
infrastructure credentials while using a non-root MySQL application user.

```bash
install -m 0600 \
  /srv/1999wiki/runtime-bundle/deploy/env/app.env.example \
  /srv/1999wiki/protected/app.env
install -m 0600 \
  /srv/1999wiki/runtime-bundle/deploy/env/infra.env.example \
  /srv/1999wiki/protected/infra.env
install -m 0600 \
  /srv/1999wiki/runtime-bundle/deploy/env/caddy.env.example \
  /srv/1999wiki/protected/caddy.env
```

The production application contract includes:

```text
MILVUS_URI=http://standalone:19530
MILVUS_DB_NAME=reverse1999_rag
MILVUS_COLLECTION_NAME=text_child_bge_m3_shadow_crawler_v3_20260721t051246z
MINIO_ENDPOINT=minio:9000
MINIO_BUCKET=reverse1999-assets
MEDIA_PUBLIC_BASE_URL=/media
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=reverse1999_wiki
HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
```

Never print the completed environment files. Validate their owner/mode and
review only variable names when troubleshooting.

For IP-only commissioning, keep:

```text
SITE_ADDRESS=:80
MINIO_PROXY_UPSTREAM=127.0.0.1:19000
```

Load the new systemd configuration only after `caddy.env` exists:

```bash
systemctl daemon-reload
systemctl enable caddy
systemctl restart caddy
systemctl --no-pager --full status caddy
```

## 3. Stage and verify persistent data

Stage the reviewed MySQL, MinIO, Milvus, and active RAG migration inputs using
the separately reviewed migration/backup procedure. Database and object
restores that require running services occur immediately after Step 4; do not
start an application slot meanwhile. COS is backup-only: production runtime
must not fetch ordinary media, databases, or RAG artifacts from COS.

Place the contents of the active Huiji closure directly under:

```text
/srv/1999wiki/rag-artifacts/
```

The selected closure is manifest-authoritative, not a hand-picked directory.
It must contain exactly 11 files totaling 222,789,868 bytes. The closure is
non-secret and mounted read-only. Its production permission contract is
root-owned or otherwise administratively owned directories at mode `0755` and
regular files at mode `0644`, so the image's unrelated non-root application
identity can traverse and read the mount without write access. Verify the
content, enforce the permission contract, and recheck it before starting an
application slot:

```bash
cd /srv/1999wiki/runtime-bundle
python3 deploy/bin/verify-rag-closure.py \
  --root /srv/1999wiki/rag-artifacts
python3 deploy/bin/prepare-rag-permissions.py \
  --root /srv/1999wiki/rag-artifacts
python3 deploy/bin/prepare-rag-permissions.py \
  --root /srv/1999wiki/rag-artifacts \
  --check
```

The permission preparer rejects symlinks and non-regular closure entries.
Preflight repeats both the byte/hash verification and the mode check. Never
apply this public-read-only contract to protected environment files or database
directories.

## 4. Start and inspect infrastructure

```bash
cd /srv/1999wiki/runtime-bundle
docker compose \
  -p 1999wiki-infra \
  --env-file /srv/1999wiki/protected/infra.env \
  -f deploy/compose.infra.yml \
  config --quiet
docker compose \
  -p 1999wiki-infra \
  --env-file /srv/1999wiki/protected/infra.env \
  -f deploy/compose.infra.yml \
  up -d
docker compose \
  -p 1999wiki-infra \
  --env-file /srv/1999wiki/protected/infra.env \
  -f deploy/compose.infra.yml \
  ps
```

Proceed only when MySQL, MinIO, etcd, and Milvus Standalone are all healthy.
Restore the staged MySQL, MinIO, and Milvus data with the reviewed migration
procedure while application slots remain stopped.

The public same-origin media route requires anonymous `s3:GetObject` for the
restored media bucket; write and listing permissions remain private. Set that
exact bucket policy from inside the container without printing credentials:

```bash
docker compose \
  -p 1999wiki-infra \
  --env-file /srv/1999wiki/protected/infra.env \
  -f /srv/1999wiki/runtime-bundle/deploy/compose.infra.yml \
  exec -T minio sh -ceu '
    umask 077
    policy="$(mktemp)"
    trap "rm -f -- \"$policy\"" EXIT
    cat >"$policy" <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":["*"]},"Action":["s3:GetObject"],"Resource":["arn:aws:s3:::reverse1999-assets/*"]}]}
JSON
    mc alias set local http://127.0.0.1:9000 \
      "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
    mc anonymous set-json "$policy" local/reverse1999-assets >/dev/null
  '
```

This policy publishes object reads only through the loopback-bound MinIO API
and host Caddy `/media/` route; the MinIO console stays unpublished.

Confirm restored MySQL table counts, the active Milvus collection name and
14,630-row count, representative object keys, and the RAG closure identity
against the migration manifest.

## 5. Create an immutable release

Authenticate to GHCR with a token limited to `read:packages`:

```bash
read -rsp 'GHCR token: ' GHCR_TOKEN
printf '%s' "$GHCR_TOKEN" |
  docker login ghcr.io -u DDomelette --password-stdin
unset GHCR_TOKEN
```

After the manual workflow succeeds, download its artifact named
`release-sha-abcdef0`. It contains `release-manifest.json`; do not reconstruct
digest values from the job summary or from an unprotected tag. On an operator
workstation this can be downloaded from the workflow run's **Artifacts**
section. Transfer that exact file with the reviewed runtime bundle to:

```text
/srv/1999wiki/releases/sha-abcdef0/release-manifest.json
```

Verify the artifact against the reviewed full commit. This command validates
the exact schema, full commit, both exact tags, both registry digests, and both
digest-qualified refs, then prints only non-secret release identity:

```bash
cd /srv/1999wiki/runtime-bundle
python3 deploy/bin/release_manifest.py verify \
  --manifest /srv/1999wiki/releases/sha-abcdef0/release-manifest.json \
  --commit abcdef0123456789abcdef0123456789abcdef01
```

For release `sha-abcdef0`, create both slot files. Use distinct ports:

```bash
install -d -m 0700 /srv/1999wiki/releases/sha-abcdef0
install -m 0600 \
  deploy/env/release.env.example \
  /srv/1999wiki/releases/sha-abcdef0/blue.env
cp /srv/1999wiki/releases/sha-abcdef0/blue.env \
  /srv/1999wiki/releases/sha-abcdef0/green.env
chmod 0600 /srv/1999wiki/releases/sha-abcdef0/green.env
```

Edit both files by copying the three verified identity lines and adding the
slot's distinct ports:

```text
blue:
  RELEASE_COMMIT=abcdef0123456789abcdef0123456789abcdef01
  BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@sha256:<backend-registry-digest>
  FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@sha256:<frontend-registry-digest>
  BACKEND_PORT=18100
  FRONTEND_PORT=18180

green:
  RELEASE_COMMIT=abcdef0123456789abcdef0123456789abcdef01
  BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@sha256:<backend-registry-digest>
  FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@sha256:<frontend-registry-digest>
  BACKEND_PORT=18200
  FRONTEND_PORT=18280
```

Pull both digest-qualified identities before the change window. Inspect
`RepoDigests` and confirm each contains the manifest's matching
`repository@sha256:...` value:

```bash
docker pull \
  ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@sha256:<backend-registry-digest>
docker pull \
  ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@sha256:<frontend-registry-digest>
docker image inspect \
  ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@sha256:<backend-registry-digest> \
  ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@sha256:<frontend-registry-digest> \
  --format '{{json .RepoDigests}}'
```

Deployment snapshots preserve the full commit and both digest-qualified refs.
Preflight refuses tag-only metadata, mismatched seven-character tags, or refs
from different commits. Candidate identity checks also compare the protected
digests with the locally pulled images' `RepoDigests`.

## 6. Deploy a candidate and switch

Choose the inactive slot. The deployment script performs preflight, starts the
candidate without building, waits for health, checks React/Wiki/RAG/SSE/media,
validates Caddy, atomically switches traffic, records state, and stops the old
slot. It does not remove the rollback target.

For initial IP-only deployment:

```bash
cd /srv/1999wiki/runtime-bundle
SMOKE_RAG_QUESTION='请介绍槲寄生' \
PUBLIC_BASE_URL='http://127.0.0.1' \
bash deploy/bin/deploy.sh sha-abcdef0 blue
```

For the next release, target the other slot:

```bash
SMOKE_RAG_QUESTION='请介绍槲寄生' \
PUBLIC_BASE_URL='http://127.0.0.1' \
bash deploy/bin/deploy.sh sha-1234567 green
```

Immediately verify:

```bash
curl --fail --show-error http://127.0.0.1/health/ready
curl --fail --show-error http://127.0.0.1/api/wiki/health
docker compose -p 1999wiki-infra \
  --env-file /srv/1999wiki/protected/infra.env \
  -f deploy/compose.infra.yml ps
journalctl -u caddy --since '-10 minutes' --no-pager
```

Also verify the public React shell, one hashed asset, Wiki list/detail, a
synchronous RAG answer, the RAG SSE terminal event, and at least one returned
`/media/` object from a browser or the smoke script. Observe container restart
counts, RSS, swap, disk free space, latency, and error logs during the agreed
observation period. On this host, blue and green Backend containers should
overlap only during validation and switching.

## 7. Roll back

Rollback is application-only. It restarts and re-smokes the recorded previous
slot, restores the Caddy upstream atomically, records the reversed state, and
stops the replaced slot. If identity, readiness, smoke, Caddy validation, or
public verification fails before the authoritative state commit, rollback
stops only the previous-slot candidate it restarted. After state commit, later
housekeeping failures never stop the new active slot. Rollback does not alter
MySQL, MinIO, etcd, Milvus, the RAG closure, or COS.

```bash
cd /srv/1999wiki/runtime-bundle
SMOKE_RAG_QUESTION='请介绍槲寄生' \
PUBLIC_BASE_URL='http://127.0.0.1' \
bash deploy/bin/rollback.sh
```

If a schema or data change is not backward-compatible, stop and use its
separately approved restoration plan. Container rollback is not data rollback.

## 8. Retire the previous slot

Only after the observation period and backup checkpoint, read
`/srv/1999wiki/deploy-state/active.env` to identify the exact recorded previous
slot and release. Then use the required confirmation token:

```bash
bash deploy/bin/cleanup.sh \
  sha-abcdef0 \
  blue \
  remove-blue-sha-abcdef0
```

The example values are placeholders; they must exactly match the recorded
previous deployment. Never target the active slot. Cleanup is deliberately
scoped and does not remove volumes or infrastructure.

Remove old application images only by exact, reviewed tag after confirming they
are not referenced by the active or rollback deployment:

```bash
docker image rm \
  ghcr.io/ddomelette/1999wiki-backend:sha-deadbee@sha256:<backend-registry-digest> \
  ghcr.io/ddomelette/1999wiki-frontend:sha-deadbee@sha256:<frontend-registry-digest>
```

Do not perform a global prune.

## 9. Bind DNS and enable HTTPS

Keep IP-only HTTP until the application is stable. Then create the domain's A
record, and an AAAA record only when IPv6 is actually routed and firewalled.
Open inbound TCP 80 and 443. Change only the protected Caddy setting:

```text
SITE_ADDRESS=wiki.example.com
```

Reload and verify:

```bash
SITE_ADDRESS=wiki.example.com \
MINIO_PROXY_UPSTREAM=127.0.0.1:19000 \
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl restart caddy
curl --fail --show-error https://wiki.example.com/health/ready
```

Update operational commands to use
`PUBLIC_BASE_URL=https://wiki.example.com`. Keep
`MEDIA_PUBLIC_BASE_URL=/media`; media remains same-origin and local to the
server.

## 10. Backup and incident boundaries

- Back up MySQL, MinIO, Milvus, etcd-compatible Milvus state, the active RAG
  closure, release metadata, and deployment state through the separate backup
  workflow.
- COS is an off-host backup destination only. No server runtime credential,
  mount, startup fetch, or ordinary media request may depend on COS.
- Confirm a usable restore point before destructive migrations or retirement.
- Preserve the previous slot and immutable image tags throughout the
  observation period.
- If readiness or smoke fails before switching, inspect the candidate and
  dependency logs; do not bypass the gate.
- If public health fails after switching, run the bounded rollback. Do not
  repair the incident with a rebuild on the server.
