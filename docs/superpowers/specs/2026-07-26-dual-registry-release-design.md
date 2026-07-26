# 1999Wiki Dual-Registry Release Design

**Status:** Proposed design, awaiting operator review. The architecture and
failure policy were approved in conversation. The document has been reconciled
with the final permission-preparation and digest-retirement interfaces and
self-reviewed. Implementation planning must not begin until the operator
reviews and approves this written version.

## 1. Purpose

1999Wiki application images must be easy to pull from the production server in
Guangzhou without making GitHub Container Registry (GHCR) the only release
path. Each reviewed commit therefore produces one Backend image and one
Frontend image, then publishes the exact same OCI content to:

- primary: Tencent Container Registry (TCR);
- mirror: GitHub Container Registry (GHCR).

TCR availability is a release requirement. GHCR remains the independent backup
registry, but a network-only GHCR outage may defer that mirror without blocking
a TCR-backed deployment.

This design replaces the not-yet-published single-registry
`1999wiki.release/v1` contract. The project is not live and no v1 release has
been published, so the implementation does not carry v1 production
compatibility.

## 2. Fixed names and release identity

For a full Git commit whose first seven hexadecimal characters are `a3b1541`,
the immutable tag is `sha-a3b1541`.

Primary TCR repositories:

```text
ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend
ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend
```

GHCR mirror repositories:

```text
ghcr.io/ddomelette/1999wiki-backend
ghcr.io/ddomelette/1999wiki-frontend
```

The public release identity is always the full 40-character Git commit plus the
two component manifest digests. A `sha-*` tag is a human-readable locator, not
sufficient deployment identity. Server release metadata always uses
digest-qualified references:

```text
<registry>/<repository>:sha-<short-sha>@sha256:<manifest-digest>
```

Backend and Frontend must come from the same full commit. A mixed release is
invalid even if both images exist.

## 3. Scope and non-goals

This change covers:

- building Backend and Frontend once per reviewed commit;
- copying the resulting OCI manifests to TCR and GHCR;
- registry-specific tag immutability checks;
- bounded GHCR network retries and failure classification;
- a machine-readable dual-registry release manifest;
- a separate GHCR backfill attestation;
- generation and validation of server `release.env` files;
- deployment helpers accepting both approved repository families;
- TCR login and pull instructions for the server;
- automated tests for publication and deployment identity.

This change does not:

- deploy automatically from GitHub Actions;
- build images on the production server;
- install Codex CLI, Node.js, Conda, crawler, packaging, or vectorization tools
  on the server;
- move MySQL, MinIO, Milvus, etcd, media, or RAG data into application images;
- make the server read COS during normal operation;
- introduce an automatic cross-registry runtime failover;
- change the existing blue/green application and persistent-data architecture.

## 4. Architecture

### 4.1 One build, two destinations

The release workflow checks out one full commit with Git LFS, runs the existing
Python and Frontend gates, and builds exactly two single-platform
`linux/amd64` OCI archives:

```text
backend.oci
frontend.oci
```

Each component is built once. The workflow must not run a separate Docker build
for TCR and GHCR. A manifest-preserving tool such as `skopeo copy --all
--preserve-digests` copies each archive to each registry. Any registry rewrite
that changes the protected manifest digest fails closed.

The OCI archives are temporary files inside the publication job. Their
manifest digests are verified before and after each registry copy, then the
runner discards the archives normally. They are not uploaded as a second
long-term image store. Later GHCR backfill uses the verified TCR digest, not a
rebuild and not a mutable local cache.

### 4.2 Publication order

Publication runs in this order:

1. derive the full commit and its `sha-<7>` tag;
2. verify tests, Git LFS inputs, and both local OCI archives;
3. authenticate to TCR without printing credentials;
4. inspect both TCR target tags;
5. preflight GHCR authentication, permission, and target tags under the
   failure policy in section 5;
6. fail unless both TCR tags are absent and GHCR has no non-transient blocker;
7. copy Backend and Frontend OCI content to TCR;
8. read both TCR registry digests and prove they match the built manifests;
9. unless GHCR was already deferred by its preflight, copy and verify the
   corresponding GHCR tags;
10. classify the GHCR result;
11. write and upload `release-manifest.json` and the workflow summary.

TCR is the hard gate. A TCR lookup, authentication, authorization, push,
manifest, tag, or digest error prevents a deployable release manifest.

The workflow concurrency key includes the full commit and publication workflow.
Two runs may not publish the same release concurrently.

### 4.3 Registry tag rules

Before first publication, both target tags in a registry must be absent.
Existing content at either TCR tag blocks normal publication, even if only one
component exists. This prevents a partial or foreign release from being
silently adopted.

The dedicated GHCR backfill flow is idempotent:

- an absent GHCR tag receives the exact TCR digest;
- an existing GHCR tag is accepted only when it already resolves to the exact
  expected digest;
- an existing different digest is a tag conflict and fails closed.

TCR partial publication never produces a deployable manifest. Recovery requires
an operator to inspect the exact registry state and either remove the incomplete
tags or complete a separately reviewed recovery procedure. The normal workflow
does not overwrite or reinterpret them.

If both TCR images are complete but a later non-transient GHCR error blocks the
release, the workflow likewise emits no deployable manifest. It may upload a
sanitized `publication-failure.json` containing the commit, TCR refs/digests,
failed phase, and workflow run identity for diagnosis. That artifact is not
accepted by server tooling. After the blocker is corrected, the default
recovery is operator-verified removal of the unpublished release tags followed
by a clean rerun; inventing a release manifest from the failure artifact is
forbidden.

## 5. GHCR failure classification and retry policy

Only transient network-class failures are retryable:

- DNS resolution and connection establishment failures;
- connection reset or transport timeout;
- registry HTTP `500`, `502`, `503`, or `504`.

One workflow run has a shared budget of at most five transient GHCR failures,
with bounded exponential backoff and jitter. Tag inspection, copy, and
post-copy verification consume the same budget; splitting the work into
multiple commands cannot create another five retries. The failure counter and
sanitized operation name are recorded in the job summary.

The following fail immediately and may not be converted into a deferred mirror:

- invalid or missing authentication;
- authorization or repository permission failure;
- registry throttling or other HTTP `4xx` responses;
- existing tag resolving to a different digest;
- malformed or unexpected manifest;
- source/target digest mismatch;
- unsupported media type or lost manifest/platform content;
- client/configuration errors other than the explicitly retryable statuses.

After the fifth transient failure in the shared budget, the workflow records
GHCR as
`deferred_after_5_network_failures`. If both TCR images are verified, the
release is deployable from TCR in the degraded mirror state.

A timeout after a copy can leave an indeterminate GHCR result. Before consuming
another retry, the workflow re-reads the target tag. An exact digest is treated
as a successful idempotent copy; a different digest fails closed; continued
network uncertainty consumes the next transient attempt.

## 6. Release manifest v2

`release-manifest.json` is immutable evidence from the original publication
workflow. Its canonical schema is:

```json
{
  "schema_version": "1999wiki.release/v2",
  "commit": "a3b1541000000000000000000000000000000000",
  "release_tag": "sha-a3b1541",
  "primary_registry": "tcr",
  "release_state": "ready",
  "images": {
    "backend": {
      "digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "registries": {
        "tcr": {
          "status": "published",
          "tag": "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-a3b1541",
          "ref": "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-a3b1541@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        "ghcr": {
          "status": "published",
          "tag": "ghcr.io/ddomelette/1999wiki-backend:sha-a3b1541",
          "ref": "ghcr.io/ddomelette/1999wiki-backend:sha-a3b1541@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        }
      }
    },
    "frontend": {
      "digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "registries": {
        "tcr": {
          "status": "published",
          "tag": "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:sha-a3b1541",
          "ref": "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:sha-a3b1541@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        },
        "ghcr": {
          "status": "published",
          "tag": "ghcr.io/ddomelette/1999wiki-frontend:sha-a3b1541",
          "ref": "ghcr.io/ddomelette/1999wiki-frontend:sha-a3b1541@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        }
      }
    }
  }
}
```

The example uses synthetic but structurally valid digest values. Real manifests
contain the observed lowercase SHA-256 digests and no placeholders.

Allowed component registry status values are:

- `published`;
- `deferred_after_5_network_failures`.

Every registry record has the exact fields `status`, `tag`, and `ref`. A
published record has its digest-qualified string in `ref`. A deferred GHCR
record retains the expected immutable tag but has JSON `null` in `ref`; it must
not imply that unverified content is pullable.

Allowed release states are:

- `ready`: both TCR images and both GHCR images are published and identical;
- `ready_with_deferred_ghcr`: both TCR images are published and at least one
  GHCR image is deferred solely after five transient attempts.

There is no manifest for a failed TCR release. A deployable manifest requires:

- an exact canonical field set with no unrecognized fields;
- a valid full commit and matching `sha-<7>` tags;
- the approved component repository for every registry record;
- mandatory `published` TCR records for both components;
- one protected digest per component shared by TCR and any published GHCR
  record;
- a release state derived exactly from the component statuses.

The original v2 manifest is never edited after publication.

## 7. Server release selection

The production server defaults to TCR. The manifest helper emits:

```env
RELEASE_COMMIT=a3b1541000000000000000000000000000000000
BACKEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-a3b1541@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
FRONTEND_IMAGE=ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:sha-a3b1541@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
```

This output remains validation-only release metadata and contains no registry
password.

An operator may explicitly request GHCR output when either:

- both GHCR component records in the original manifest are `published`; or
- the original manifest is supplied together with a valid mirror attestation
  that binds the SHA-256 of those exact manifest bytes and proves both expected
  GHCR refs now resolve to the component digests.

A partially mirrored release without a complete attestation cannot emit a GHCR
`release.env`.

Deployment validation accepts only the four approved repository names and
requires the tag, digest, and full commit to agree with the v2 manifest. Pulls,
local `RepoDigests` checks, active/previous state, rollback, and retirement
remain digest-qualified. Registry selection does not weaken the existing image
identity contract.

There is no silent server-side fallback. Changing from TCR to GHCR is an
operator-controlled release metadata change followed by normal preflight and
blue/green deployment checks.

## 8. GHCR backfill

A separate manually triggered workflow repairs only releases whose original
manifest has `release_state=ready_with_deferred_ghcr`.

It:

1. downloads and validates the original immutable v2 manifest;
2. authenticates to both registries;
3. reads each exact TCR `repository@digest`;
4. proves the TCR digest matches the original manifest;
5. copies that digest to the matching GHCR `sha-*` tag without rebuilding;
6. accepts an already-existing GHCR tag only when its digest matches exactly;
7. verifies both final GHCR digests;
8. emits `mirror-attestation.json`.

The canonical attestation contains its schema version, SHA-256 of the exact
original manifest bytes, commit, component TCR source refs, component GHCR
destination refs, exact digests, `completed` status, workflow run identity, and
an RFC 3339 UTC completion timestamp. It does not replace or mutate
`release-manifest.json`.

Attestation verification requires the referenced manifest bytes, revalidates
the original v2 schema and commit, recomputes the manifest SHA-256, and requires
both attested GHCR digests to equal their component digests. Server tooling may
then emit GHCR refs from the manifest-plus-attestation pair. An attestation
alone is never deployment metadata.

Backfill uses the same immediate-failure classifications. One backfill run has
the same shared ceiling of five transient GHCR failures.

## 9. Credentials and configuration

GitHub Actions stores registry credentials only in GitHub Secrets:

```text
TCR_USERNAME
TCR_PASSWORD
```

Non-secret repository configuration uses variables or checked-in constants:

```text
TCR_REGISTRY=ccr.ccs.tencentyun.com
TCR_NAMESPACE=1999wiki_code
```

GHCR continues to use the workflow's scoped `GITHUB_TOKEN` with
`packages: write`. Workflow steps pass passwords through supported secret
inputs or standard input, never command-line arguments, generated manifests,
artifacts, summaries, or logs.

The server authenticates to the private TCR repositories using the existing
personal-instance username and initialized password. Login uses
`docker login --password-stdin`. The responsible account's Docker credential
file is mode `0600`; its containing `.docker` directory is mode `0700`.
Release files and deployment logs never copy or print that credential file.

TCR personal edition is acceptable for this low-traffic initial deployment, but
it remains an external availability dependency without an enterprise SLA.
GHCR and the locally retained rollback image provide recovery options; neither
changes the rule that a new release must first be complete in TCR.

## 10. Error handling and operational states

- Test, build, OCI archive, or checksum failure: no publication.
- TCR tag lookup failure: no publication.
- TCR authentication, permission, copy, or digest failure: release failed.
- Partial TCR publication: no deployable manifest; operator inspection needed.
- GHCR authentication, permission, tag conflict, manifest, or digest failure:
  release failed immediately; any already-published TCR content remains
  non-deployable until the documented operator recovery is completed.
- GHCR transient failure before five attempts: retry only the uncertain
  operation after checking current target state.
- GHCR transient failure on the fifth attempt: publish a
  `ready_with_deferred_ghcr` manifest when TCR is complete.
- Manifest construction or canonical verification failure: release failed even
  when registry uploads exist.
- Server TCR pull failure: deployment stops before candidate startup; it does
  not silently consume COS or rebuild locally.
- Server registry credential failure: report the registry and non-secret
  reason, never the username/password payload.

Workflow summaries distinguish `published`, `deferred`, and `failed`; they do
not label a TCR-only release as fully mirrored.

## 11. Testing

### 11.1 Unit and contract tests

Tests cover:

- exact TCR and GHCR repository allowlists;
- full commit to `sha-<7>` tag matching;
- canonical v2 manifest creation and rejection of extra/missing fields;
- release-state derivation from all component status combinations;
- mandatory TCR publication for both components;
- shared per-component digest across registries;
- TCR-default and explicit-GHCR environment emission;
- refusal to emit GHCR refs for partial/deferred mirrors without a complete
  matching attestation;
- acceptance of a complete attestation only with the byte-identical original
  manifest;
- retry classification for DNS, timeout, reset, and allowed `5xx`;
- immediate failure for authentication, authorization, conflict, malformed
  manifest, media-type, and digest errors;
- five-attempt boundary and indeterminate-copy reconciliation;
- backfill acceptance of an already matching target and rejection of a
  different target digest;
- rejection of a mirror attestation with a wrong manifest hash, commit,
  component, repository, digest, or incomplete status.

### 11.2 Workflow structure tests

Static workflow tests prove:

- Backend and Frontend each have one build step;
- both registry copies consume the same OCI archive;
- TCR publication and verification precede GHCR publication;
- no deployment or SSH step exists;
- credentials are referenced only through approved secret inputs;
- the release manifest and any failure/attestation artifacts have explicit
  retention;
- normal publication and backfill are distinct workflows;
- TCR failure cannot reach manifest upload;
- the fifth eligible GHCR network failure can reach only the degraded release
  state.

### 11.3 Local integration tests

A disposable local OCI registry test uses unique repository names and
explicitly controlled loopback ports to prove:

- one local OCI archive can be copied to two destinations with the same
  manifest digest;
- tags resolve to that digest;
- exact-match retry reconciliation is idempotent;
- conflicting tags fail closed;
- digest-qualified pull and local `RepoDigests` validation work for both
  approved registry shapes;
- retirement reconciles the intended tag and canonical `repository@digest`
  through separate tri-state checks, removes only verified identities, and
  confirms both are absent without affecting unrelated images.

The test cleans only its uniquely named containers, tags, and temporary files.
On Windows Docker Desktop, its readiness probe and Docker registry reference
must use a tested address/port pairing; a probe against IPv4 followed by a
Docker push resolved through IPv6 is not valid evidence of registry failure.

### 11.4 Server acceptance

Before the first live switch:

- TCR login succeeds without exposing the password;
- both TCR digest-qualified refs pull on the Guangzhou server;
- manifest verification emits a TCR-backed `release.env`;
- preflight accepts TCR and rejects an unapproved registry/repository;
- candidate startup, health, Wiki, RAG, SSE, media, and Frontend checks pass;
- blue/green switch and rollback preserve exact image identities;
- the old slot remains available through the observation window;
- no runtime request to COS occurs.

## 12. Implementation boundaries

Implementation should keep these units separate:

- OCI build/export: produces immutable local archives and checksums;
- registry probe/copy: has no release-manifest policy;
- failure classifier/retry wrapper: classifies sanitized command outcomes;
- manifest helper: owns canonical schema and environment emission;
- publication workflow: coordinates TCR then GHCR;
- backfill workflow: mirrors exact TCR digests and writes attestation;
- deployment validation: accepts approved digest-qualified identities and does
  not know registry credentials.

The existing permission-preparation and Docker image-retirement fixes remain a
prerequisite. They are closed through `ea4111e` with a clean scoped re-review.
Dual-registry work reuses these final interfaces:

- permission preparation consumes the closure verifier's exact fingerprint,
  opens the approved root, ancestors, and files with Linux no-follow descriptor
  operations, compares `fstat` identity, changes modes through retained
  descriptors, and runs post-mutation closure verification;
- retirement derives an exact tag plus canonical `repository@digest`, evaluates
  each through a distinct present/absent/error result, removes only an exact
  verified identity, and confirms both forms absent before state commit.

Repository allowlists in release validation and retirement are expanded for
the two approved TCR repositories without weakening those descriptor or
digest-state contracts. If active and retired slot metadata point to the same
component digest under different registry aliases, automatic retirement fails
closed for operator inspection rather than risking removal of active content.

## 13. Acceptance criteria

The design is implemented only when:

1. one reviewed full commit produces one Backend OCI archive and one Frontend
   OCI archive;
2. TCR receives both exact immutable tags and their digests match the archives;
3. GHCR receives identical digests or is deferred only after five classified
   transient attempts;
4. all non-network GHCR failures stop the release immediately;
5. a canonical v2 manifest records mandatory TCR and actual GHCR state;
6. the server can generate and validate TCR-backed release metadata using only
   environment/configuration changes, not code edits;
7. a deferred mirror can be backfilled from exact TCR digests without rebuild
   or original-manifest mutation;
8. automated tests cover manifest, retry, conflict, backfill, and deployment
   identity contracts;
9. full Python, Frontend, Compose, Docker, workflow, RAG-closure, and local smoke
   gates pass before publication;
10. the operator reviews and approves this written design and its subsequent
    implementation plan before the workflows are changed.
