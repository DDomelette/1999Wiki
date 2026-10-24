# Integrated SSE Correction Production Release Report

## Outcome

The integrated correction release is online in the green slot as `sha-68e531f` from full commit `68e531f6f3ca4c12a0f3d02ff3169bcc5b44190a`. It contains A+B, true incremental SSE, and the completed main-page scroll/navigation repairs, while excluding unfinished Thread C. Both production containers are `healthy` with restart count `0`, the public readiness endpoint passes, and blue `sha-05ccd6b` remains the protected rollback target.

The server used TCR only. It did not need GitHub, GHCR, or a VPN.

## Root cause corrected

The preceding production release `sha-05ccd6b` contained the A/B release line but did not include the later true-SSE and main scroll/navigation work. This correction rebuilt from the exact direct pre-C boundary and carried the already-reviewed packaging and CI corrections forward.

The release gate was also strengthened so a candidate cannot switch traffic on a terminal-only SSE response. The checked-in smoke parser now requires at least two non-empty `token` events before exactly one `done`, rejects malformed/error/late events, and proves that the visible streamed answer equals the terminal answer.

## Exact source boundary

- Release base: `0993dbbad34cbdb06f9d6a5ffc5eae82cc8925f4`.
- A/B ancestor: `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`.
- True-SSE merge ancestor: `2cbaef3a5c1235c95eba1cb18cd5e9f36ebd9dc6`.
- Included streaming implementation: `18372f0`, `56a2f5d`, `1c767e4`, `e09d509`, `5d4b87d`, `dada4a0`, and `44cc589`.
- Included main scroll/navigation repairs: `6019b6c`, `60edce2`, `07dc24c`, `5558ffe`, `273520e`, and `0993dbb`.
- Applied release corrections: `c48c2e4` (packaging) and `80bbc17` (platform-specific CI detach behavior).
- Added release gate commit: `68e531f`.
- Excluded first Thread C commit: `4c312c52ee7b1e018e4608aeda741fdc4bba9a79`.
- Excluded Thread C merge: `33e5837`.
- Pushed source record: `origin/codex/release-integrated-sse` equals the full release commit.

The correction worktree was clean after verification. The only new source edit beyond the reviewed historical corrections was the two-file true-SSE smoke-gate change in `deploy/bin/smoke-test.sh` and `tests/test_deploy_scripts.py`.

## Local verification

- TDD: the zero-token and one-token regressions failed first; after the minimal parser change the two new cases passed. The complete smoke-related deploy set then passed with `11 passed, 105 deselected`.
- Focused Python gates: `287 passed, 1 skipped, 3 warnings`.
- Full Python suite: `2242 passed, 5 skipped, 3 warnings`.
- Frontend unit suite: 55 files, `323 passed`.
- Production Vite build: passed. The existing chunk-size warning remained.
- Browser E2E: the first invocation failed only because `playwright.config.ts` has no managed `webServer` and nothing was listening on `127.0.0.1:5173`; after starting the reviewed Vite server, the exact suite passed with `19 passed, 45 skipped`.
- Linux supervisor portability: `8 passed, 1 skipped, 1 warning` in the production runtime dependency set plus locked test-only `pytest 9.1.1` and `psutil 7.2.2`. Earlier reduced containers were rejected because they lacked application or test-only dependencies; no product assertion failed in those environment probes.
- Backend production image: built for `linux/amd64`, passed its in-build import, and passed a corrected `import backend.main` runtime check.
- Frontend production image: built for `linux/amd64`.

`npm ci` reported six pre-existing audit findings in the locked dependency baseline: three moderate, two high, and one critical. No unrelated lockfile mutation or automated audit fix was applied during this release.

## TCR publication and manifest

- Backend: `ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-68e531f@sha256:4e9313f9cb27636de7f9dff34ddb5595f542ec2adb255610d0b794584de89960`.
- Frontend: `ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:sha-68e531f@sha256:6db64a57f47a4f99bf038c31d2000942cd7659159e04a193de0be5f56ef859f2`.
- Manifest SHA-256: `f43656e3f68192749b52f43ef26a7382df2ded6f16afcd36dc57b448a8b1735b`.
- Manifest schema: `1999wiki.release/v2`.
- Manifest state: `ready_with_deferred_ghcr`.
- Primary registry: `tcr`.

Both tags were proven absent before publication. Buildx metadata and independent remote TCR inspection returned the same digests. GHCR remained deferred after five network failures and was not a production dependency, matching the TCR-first requirement for the China-hosted server.

## Runtime bundle and green retirement

The reviewed deploy archive SHA-256 was `390b9f051d26b05013cc7c93d491ef67ea3d4c5cb8916e49eca4467d63853e3a`. The staged and live runtime trees contained 20 tracked deploy files; before installation their only byte difference was `deploy/bin/smoke-test.sh`, and after the same-directory atomic replacement all 20 files matched.

The complete prior runtime bundle is retained at `/srv/1999wiki/runtime-bundle.pre-sha-68e531f`, and the reviewed stage is retained at `/srv/1999wiki/runtime-bundle.stage-sha-68e531f`.

Old green `sha-1ec7752` was rechecked as exactly two stopped application containers and retired only with the exact confirmation `remove-green-sha-1ec7752`. Its release manifest and deployment snapshot remain retained. Blue stayed healthy and public throughout this retirement.

## Inactive candidate and traffic switch

The first inactive-candidate attempt was safely blocked before switch. The local PowerShell text pipeline changed the UTF-8 smoke question: the expected phrase hash was `3a70640eb37816b2886bf9b2a6504eb54889504ab969b98738baf7c5c3f41a3a`, while the streamed bytes produced `3126b70f80dce5bafa2c5ae4736137cb6883a8be7f9ed9cf17c5787d329e7465`. The malformed Unicode reached the request-planning safety validator and caused the candidate `/ask` smoke to return 500. The deploy transaction stopped both candidate containers before switch; blue remained active and public readiness stayed 200.

The failed, uncommitted candidate was then removed under the operations lock while its immutable release snapshot and manifest were retained. `scp` preserved the exact expected UTF-8 hash. A fresh empty-slot preflight passed, both strengthened smoke runs passed, Caddy switched atomically, and blue stopped only after the second smoke succeeded. No product container or server file was hot-patched.

Authoritative post-switch state:

- Active: green `sha-68e531f`.
- Previous: blue `sha-05ccd6b`, available for rollback.
- Green Backend/Frontend: `healthy 0`.
- Running blue containers: zero.
- Public readiness: passing.

## True streaming acceptance

The canonical post-switch smoke passed against direct green and the public Caddy path.

The incremental public SSE probe observed `status`, `sources`, 802 non-empty `token` events, a final validation status, and exactly one terminal `done`. The first token arrived at 8.429 seconds and completion arrived at 14.145 seconds. No `error` or late token occurred, no answer correction was needed, and the concatenated visible token text exactly equaled `done.answer`.

The actual production browser UI was also exercised with the same detailed Sonetto question. During one live request, the same assistant bubble visibly grew through lengths `14 -> 24 -> 42` while the request was still in progress; the sampler recorded 90 distinct length changes and later observed a final length of 2013. The final UI retained the answer, media gallery, the `来源:` section, and 20 source labels from `[S01]` through `[S20]`. Browser-control telemetry to `ab.chatgpt.com` timed out repeatedly on the local control side, slowing automation calls, but did not affect the production page or its network request.

## A/B and data identity preservation

The public composite request `你好，你是谁，请介绍一下十四行诗` returned:

- `effective_route`: `composite`.
- `retrieval_outcome`: `sufficient`.
- Ordered tasks: `social_smalltalk`, `assistant_meta`, `knowledge_base`.
- Sources: 20.
- Knowledge citations: 20, all resolving to returned source IDs.

Production data identities remained unchanged before and after switch:

- Active-build SHA-256: `87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e`.
- BM25 SHA-256: `70519e409f7b962cd52bd532bfa0a65fdc22b27ea545157e42ad13f3bf96f20a`.
- BM25 schema: `huiji.bm25-index/v2`.
- Milvus collection: `text_child_bge_m3_shadow_crawler_v3_20260721t051246z`.

No corpus, index, embedding, Milvus, MinIO, media, or database write was performed.

## Stability observation

Twenty samples were taken at 30-second intervals from `2026-08-04T17:05:00Z` through `2026-08-04T17:14:32Z`, followed by log review. Every sample passed public readiness and reported both green containers as `healthy/0`.

- Available disk range: 16,925,675,520 to 16,927,432,704 bytes, always above 8 GiB.
- Available memory range: 1,704 to 1,720 MiB.
- Traceback/panic/unhealthy-transition count: 0.
- Backend error count: 0.
- Caddy error count: 0.
- HTTP 5xx count: 0.

## Rollback readiness

Rollback was not invoked because all post-switch gates passed. Blue `sha-05ccd6b` remains stopped, recorded as `PREVIOUS_RELEASE`, and protected from cleanup. Its release snapshot is present. The prior runtime-bundle backup and the new release snapshot are also retained.

## Unrelated workspace preservation

The correction worktree remained clean. The following pre-existing user changes in the main checkout were neither modified, staged, stashed, cleaned, nor committed:

- `docs/huiji-crawler/plans/README.md`
- `docs/huiji-crawler/specs/2026-07-20-windows-crawler-p2-credential-lifecycle-design.md`
- `docs/huiji-crawler/plans/2026-07-29-windows-crawler-p2-credential-lifecycle.md`
- `docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md`
