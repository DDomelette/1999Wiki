# A/B Production Release Report

## Outcome

`online`

Production is serving blue release `sha-05ccd6b` from commit
`05ccd6ba0af157787b335ed299f8c26f5f2b3bfb`. Both application containers are
healthy with zero restarts. Green release `sha-1ec7752` is stopped and retained
as the verified rollback target.

The production server pulls only digest-qualified TCR images. It does not need
GitHub or GHCR access.

## Source and local verification

- A/B merge baseline: `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`.
- Packaging-only child commit: `b24d33a3cabee974389356df6ed543b816d3f943`.
- CI-test-only child commit and released source:
  `05ccd6ba0af157787b335ed299f8c26f5f2b3bfb`.
- Remote branch `codex/release-ab` resolves to the full released source commit.
- Full Python gate after the final source change: 2223 passed, 5 skipped, 3
  warnings.
- The affected packaging/BM25/provenance group passed 89 tests. The new Docker
  runtime-allow-list test was observed failing before the packaging fix and
  passing after it.
- Windows supervisor tests passed 8 tests with 1 non-Windows branch skipped;
  the same file passed 8 tests with 1 Windows branch skipped in Linux.
- Frontend gate: 51 files and 265 tests passed; the production Vite build
  passed.
- Both production Dockerfiles built successfully for `linux/amd64`. The
  Backend image passed its in-image `import backend.main` gate.
- Analyzer probe hashes were unchanged across the packaging refactor:
  `efdf55da8db36b421c82a53bb0ca8f3642bbc470ea5260073dceea660acc36dc`
  for the Chinese analyzer and
  `dac1e4838ca994ed683e152de065b958976d3ba998eae715643fbc0ffab3544f`
  for the legacy analyzer.
- All 20 Git-tracked files in the server runtime deployment bundle matched the
  released deploy tree byte-for-byte. The only remote extra was a generated
  `deploy/bin/__pycache__/release_identity.cpython-312.pyc` cache file.
- The four pre-existing user document changes in the main workspace were not
  staged, modified, stashed, cleaned, reset, or committed.

## GitHub publication

- TCR repository variables were verified and the protected `TCR_USERNAME` and
  `TCR_PASSWORD` Secrets were refreshed through an in-memory bridge. No
  plaintext credential was printed or placed in a command argument.
- Run
  [30903255739](https://github.com/DDomelette/1999Wiki/actions/runs/30903255739)
  stopped before image publication because a Windows-only test referenced
  Windows `subprocess` constants on Ubuntu. The publish job was skipped and no
  `sha-b24d33a` TCR tag was created.
- Run
  [30904868962](https://github.com/DDomelette/1999Wiki/actions/runs/30904868962)
  passed Python tests, frontend tests/build, and both image builds. Its registry
  publisher exited before creating either `sha-05ccd6b` TCR tag; no canonical
  release artifact was produced by that run.
- Because the production path is TCR-first and the GitHub-to-domestic-registry
  boundary was unreliable, the exact `linux/amd64` images were published
  directly from the authenticated local Docker client to TCR. Both target tags
  were proven absent first, then verified by digest after push. GHCR was not
  used and is recorded as deferred.

## Release manifest

- Schema: `1999wiki.release/v2`.
- Release tag: `sha-05ccd6b`.
- Release state: `ready_with_deferred_ghcr`.
- Manifest SHA-256:
  `81dfb3c7c021dbf1327fe37d4f10a848c37efad165759383e1b3227c6b2bd872`.
- Backend TCR image:
  `ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-05ccd6b@sha256:13149c5b1ae13dc5e834f8ae4afcdae3456c21b8413549da9f66ff3bc2617717`.
- Frontend TCR image:
  `ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:sha-05ccd6b@sha256:31c557ed5e8b710f8c077f9bfcad5f61deaf8733579d031d77a125ce4cf6ccd8`.
- The local and installed server manifests have the same SHA-256. The server
  generated and validated canonical `release.identity` and `blue.env` files
  from that manifest.

## Old blue retirement

- The exact authorized stopped blue release `sha-0761382` was retired with
  confirmation `remove-blue-sha-0761382`.
- Its two stopped application containers and blue network were removed, and
  its safe frontend image tag was released.
- Its release manifest and protected deployment snapshot were retained.
- Active green `sha-1ec7752` remained healthy with zero restarts throughout
  retirement.

## Inactive-slot deployment tests

- Standalone preflight passed for `sha-05ccd6b` in blue.
- RAG closure verified 11 files totaling 222,789,868 bytes, including required
  ownership and permission checks.
- The server pulled both images only from TCR using their digest-qualified
  references.
- Blue Backend and Frontend became healthy on loopback ports before switching.
- The deployment transaction passed its direct-candidate and public-route smoke
  suites. These covered the React shell and asset, readiness, Wiki list/detail,
  synchronous RAG, SSE terminal behavior, and media routing against real
  production dependencies.

## Traffic switch and public regression

- The first switch to blue completed successfully. A post-switch check then
  used an incorrect release-plan expectation: it required the dependent
  comparison question `比较十四行诗和槲寄生` to become `composite`.
- Production returned `rag_grounded`, which is the correct behavior. The
  repository's explicit regression contract says dependent comparison
  questions must remain one knowledge-base task. The conservative failure
  branch nevertheless rolled back successfully to green `sha-1ec7752`.
- The same verified blue deployment was reactivated through the protected
  previous-slot transaction; its canonical smoke suite passed before traffic
  switched.
- The correct deterministic composite benchmark
  `你好，你是谁，请介绍一下十四行诗` passed through the public API with route
  `composite`, retrieval outcome `sufficient`, exactly 3 ordered subtasks
  (`social_smalltalk`, `assistant_meta`, `knowledge_base`), 20 sources, and 20
  knowledge-branch citation IDs.
- Final public readiness passed with blue active.

## BM25 and Milvus identity preservation

- Active build SHA-256 before and after release:
  `87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e`.
- BM25 artifact SHA-256 before and after release:
  `70519e409f7b962cd52bd532bfa0a65fdc22b27ea545157e42ad13f3bf96f20a`.
- BM25 schema remains `huiji.bm25-index/v2`; no v3 artifact was built,
  uploaded, or activated.
- Milvus collection remains
  `text_child_bge_m3_shadow_crawler_v3_20260721t051246z`.
- No corpus, embedding, Milvus, media, or database write was performed.

## Stability observation

- Twenty readiness/health/resource samples ran at 30-second intervals for a
  complete 10-minute observation window.
- Backend and Frontend were healthy with restart count 0 throughout.
- Final available disk was 16,450,428,928 bytes, above the 8 GiB floor; final
  available memory was 1,717 MiB.
- The compact final log review found 0 Caddy error lines, 0 Backend critical
  lines, and 0 Frontend critical lines in the reviewed window.

## Rollback readiness

- Authoritative active state: blue `sha-05ccd6b`, generation
  `gen-55153b3fbb6909d5d43af7e4`.
- Authoritative previous state: green `sha-1ec7752` with
  `PREVIOUS_AVAILABLE=1`.
- The green release snapshot exists and both green images remain bound to their
  original digest-qualified TCR references:
  - Backend `sha256:768f9956542c5df8b15dc0567ef78faf1442eb45a1d95aa2fde93c0439e6bf0c`.
  - Frontend `sha256:90f446541f8f38459c134cdffe5b3b1d545de8686d11400afa7e1f8224f1ca95`.
- Green is stopped, not cleaned up. The rollback path was exercised once and
  successfully restored green before the corrected gate reactivated blue.

## Unrelated workspace preservation

The following pre-existing user changes remain present and unstaged:

- `docs/huiji-crawler/plans/README.md`
- `docs/huiji-crawler/specs/2026-07-20-windows-crawler-p2-credential-lifecycle-design.md`
- `docs/huiji-crawler/plans/2026-07-29-windows-crawler-p2-credential-lifecycle.md`
- `docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md`
