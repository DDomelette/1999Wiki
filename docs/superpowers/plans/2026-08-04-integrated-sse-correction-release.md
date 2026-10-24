# Integrated SSE Correction Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish and deploy an immutable correction release containing A+B, true incremental SSE, and the completed scroll/navigation repairs, while excluding Thread C and preserving the existing BM25 v2 and Milvus identities.

**Architecture:** Build a new isolated release branch from the proven pre-C boundary `0993dbb`, apply the two existing release corrections, and strengthen the checked-in smoke gate so a candidate cannot switch traffic without at least two real SSE token events. Push exact `linux/amd64` images directly to TCR, atomically install the reviewed runtime bundle on the server, deploy into green, verify the inactive candidate against production dependencies, switch Caddy, and retain the current blue release as rollback.

**Tech Stack:** Git worktrees, PowerShell, Conda Python 3.11.15, pytest, Node.js/npm/Vitest/Vite, Playwright, Docker Buildx, TCR, SSH, Bash, Docker Compose, Caddy, and the in-app browser.

## Global Constraints

- Release base is exactly `0993dbbad34cbdb06f9d6a5ffc5eae82cc8925f4`; branch is `codex/release-integrated-sse`; worktree is `D:\1999Wiki\.worktrees\release-integrated-sse`.
- Required historical corrections are `b24d33a3cabee974389356df6ed543b816d3f943` and `05ccd6ba0af157787b335ed299f8c26f5f2b3bfb`; apply them in that order and stop on any conflict.
- Required included ancestors are A/B `daf3fe85390c534e0177c2eb06768b7f9ffc3a44` and true SSE `2cbaef3a5c1235c95eba1cb18cd5e9f36ebd9dc6`.
- Thread C starts at `4c312c52ee7b1e018e4608aeda741fdc4bba9a79`; that commit and merge `33e5837` must not be ancestors of the release.
- The only new source change is a test-driven strengthening of `deploy/bin/smoke-test.sh` and its deploy-script regressions. Do not add application features.
- Keep BM25 schema `huiji.bm25-index/v2`, active build SHA-256 `87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e`, BM25 SHA-256 `70519e409f7b962cd52bd532bfa0a65fdc22b27ea545157e42ad13f3bf96f20a`, and Milvus collection `text_child_bge_m3_shadow_crawler_v3_20260721t051246z` unchanged.
- Perform no corpus build, index build, embedding, Milvus, MinIO, media, or database write.
- Production consumes only digest-qualified TCR images. Do not require GitHub, GHCR, or a VPN on the server.
- Never print, persist in plaintext, or place registry credentials in command arguments. Use the existing authenticated Docker clients and protected server credential.
- Do not modify, stage, stash, clean, reset, or commit the four unrelated user document changes in `D:\1999Wiki`.
- Before green cleanup, require active blue `sha-05ccd6b` and previous green `sha-1ec7752`. The only authorized retirement command is `cleanup.sh sha-1ec7752 green remove-green-sha-1ec7752`.
- A failed pre-switch gate leaves blue serving. A failed post-switch gate invokes `rollback.sh` immediately. Do not repair a failed candidate in place.
- After success, blue `sha-05ccd6b` is the protected rollback target and must not be cleaned up.

## File and State Map

**Created or modified on the correction release branch:**

- Modify: `deploy/bin/smoke-test.sh` — require true token delivery, not terminal-only SSE.
- Modify: `tests/test_deploy_scripts.py` — valid multi-token fixture and failure-closed regressions.
- Apply existing corrections to `src/huiji_rag/build/artifact_writer.py`, `src/huiji_rag/provenance.py`, `src/rag/sparse.py`, `tests/test_docker_packaging.py`, and `tests/test_codex_supervisor_processes.py`.

**Created locally and ignored:**

- `.local/release-integrated-sse/<release>/backend-build-metadata.json`
- `.local/release-integrated-sse/<release>/frontend-build-metadata.json`
- `.local/release-integrated-sse/<release>/release-manifest.json`
- `.local/release-integrated-sse/<release>/runtime-bundle.tar`
- `.local/release-integrated-sse/<release>/publication-receipt.json`

**Created or updated on production:**

- `/srv/1999wiki/runtime-bundle` — full tracked tree verified; its only changed deploy file is atomically replaced from the reviewed archive.
- `/srv/1999wiki/runtime-bundle.pre-<release>` — retained prior runtime bundle.
- `/srv/1999wiki/releases/<release>/{release-manifest.json,release.identity,green.env}`
- `/srv/1999wiki/deploy-state/active.env`, Caddy active fragment, and `/srv/1999wiki/deploy-state/snapshots/<release>/green/` — changed only by checked-in transactions.

## PowerShell Identity Preamble

Every implementation task after Task 1 recreates these values rather than relying on variables from a prior shell:

```powershell
$Root = 'D:\1999Wiki'
$Worktree = 'D:\1999Wiki\.worktrees\release-integrated-sse'
$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$Head = git -C $Worktree rev-parse HEAD
if ($Head -notmatch '^[0-9a-f]{40}$') { throw 'invalid release HEAD' }
$Release = "sha-$($Head.Substring(0, 7))"
$Evidence = "$Root\.local\release-integrated-sse\$Release"
$BackendTag = "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:$Release"
$FrontendTag = "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:$Release"
```

After Task 4, each production task also reloads `$Evidence\publication-receipt.json` and verifies its `commit` and `release` fields equal `$Head` and `$Release` before using its manifest or image identities.

---

### Task 1: Create the isolated source identity

**Files:**

- Read: `docs/superpowers/specs/2026-08-04-integrated-sse-correction-release-design.md`
- Create worktree: `D:\1999Wiki\.worktrees\release-integrated-sse`
- Create branch: `refs/heads/codex/release-integrated-sse`

**Interfaces:**

- Consumes: exact Git objects `0993dbb`, `b24d33a`, and `05ccd6b`.
- Produces: clean source with the safe historical tree and exactly five correction paths changed before the smoke-gate task.

- [ ] **Step 1: Invoke the worktree safety procedure**

Use `superpowers:using-git-worktrees`. Confirm `D:\1999Wiki` is the normal checkout, `.worktrees` is ignored, and no native worktree-creation tool is available before using Git fallback.

- [ ] **Step 2: Prove boundary objects and ancestry**

```powershell
$Base = '0993dbbad34cbdb06f9d6a5ffc5eae82cc8925f4'
$AB = 'daf3fe85390c534e0177c2eb06768b7f9ffc3a44'
$SSE = '2cbaef3a5c1235c95eba1cb18cd5e9f36ebd9dc6'
$FirstC = '4c312c52ee7b1e018e4608aeda741fdc4bba9a79'
foreach ($commit in @($Base, $AB, $SSE, $FirstC,
    'b24d33a3cabee974389356df6ed543b816d3f943',
    '05ccd6ba0af157787b335ed299f8c26f5f2b3bfb')) {
    if ((git rev-parse "$commit^{commit}") -ne $commit) { throw "unresolved commit: $commit" }
}
git merge-base --is-ancestor $AB $Base
if ($LASTEXITCODE -ne 0) { throw 'A/B absent from safe base' }
git merge-base --is-ancestor $SSE $Base
if ($LASTEXITCODE -ne 0) { throw 'true SSE absent from safe base' }
git merge-base --is-ancestor $FirstC $Base
if ($LASTEXITCODE -eq 0) { throw 'Thread C present in safe base' }
if ((git rev-list --parents -n 1 $FirstC) -ne "$FirstC $Base") {
    throw 'safe base is not the direct pre-C boundary'
}
```

Expected: A/B and SSE included; `0993dbb` is the direct parent of the first C commit.

- [ ] **Step 3: Refuse ambiguous state and create the worktree**

```powershell
$Worktree = 'D:\1999Wiki\.worktrees\release-integrated-sse'
git -C 'D:\1999Wiki' check-ignore --quiet .worktrees
if ($LASTEXITCODE -ne 0) { throw '.worktrees is not ignored' }
if (Test-Path -LiteralPath $Worktree) { throw 'target worktree exists' }
git show-ref --verify --quiet refs/heads/codex/release-integrated-sse
if ($LASTEXITCODE -eq 0) { throw 'target branch exists' }
git worktree add -b codex/release-integrated-sse $Worktree $Base
if ($LASTEXITCODE -ne 0) { throw 'worktree creation failed' }
```

Expected: linked worktree created at the exact base.

- [ ] **Step 4: Apply the two proven corrections without conflict**

```powershell
git -C $Worktree cherry-pick b24d33a3cabee974389356df6ed543b816d3f943
if ($LASTEXITCODE -ne 0) { throw 'packaging correction conflicted; stop' }
git -C $Worktree cherry-pick 05ccd6ba0af157787b335ed299f8c26f5f2b3bfb
if ($LASTEXITCODE -ne 0) { throw 'CI correction conflicted; stop' }
```

Expected: two clean cherry-picks with no manual conflict resolution.

- [ ] **Step 5: Verify exact correction scope**

```powershell
$expected = @(
  'src/huiji_rag/build/artifact_writer.py', 'src/huiji_rag/provenance.py',
  'src/rag/sparse.py', 'tests/test_codex_supervisor_processes.py',
  'tests/test_docker_packaging.py'
) | Sort-Object
$actual = @(git -C $Worktree diff --name-only $Base..HEAD | Sort-Object)
if (Compare-Object $expected $actual) { throw "unexpected scope: $($actual -join ', ')" }
if (@(git -C $Worktree status --porcelain=v1).Count -ne 0) { throw 'dirty worktree' }
```

Expected: exactly five paths differ and the worktree is clean.

---

### Task 2: Strengthen the candidate true-SSE gate with TDD

**Files:**

- Modify: `tests/test_deploy_scripts.py`
- Modify: `deploy/bin/smoke-test.sh`

**Interfaces:**

- Consumes: existing smoke harness and saved SSE response.
- Produces: a smoke gate rejecting terminal-only and one-token responses before `switch.sh` can install traffic.

- [ ] **Step 1: Invoke the TDD procedure**

Read and use `superpowers:test-driven-development` before editing.

- [ ] **Step 2: Write failing regressions**

Change `_smoke_harness()` so the valid stream is `sources`, `status: generating`, `token: o`, `token: k`, `status: validating`, then `done: ok`. Extend `test_smoke_fails_closed_on_asset_sse_and_media_projection_errors` with two mutations: one removes both token blocks, one removes only the second. Both must expect `fewer than two non-empty token events`. Extend the static contract test to require `json.loads`, `token`, and the same diagnostic in `smoke-test.sh`.

- [ ] **Step 3: Run the tests and observe RED**

```powershell
Push-Location $Worktree
try {
  & 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest -q tests/test_deploy_scripts.py -k smoke
  if ($LASTEXITCODE -eq 0) { throw 'new true-SSE regressions did not fail' }
} finally { Pop-Location }
```

Expected: new zero/one-token cases fail because production only checks `done`.

- [ ] **Step 4: Implement the minimal parser**

Replace the terminal-only Python block in `smoke-test.sh`. Parse each non-comment SSE block into exactly one event name and one JSON payload. Reject malformed JSON, any `error`, absent or repeated terminal `done`, fewer than two non-empty token events, a token or `answer_replace` at or after `done`, and final answer mismatch. Compute draft text by concatenating token payloads; if `answer_replace` appears, use its final answer as visible text; require visible text to equal `done.answer`.

The parser must contain this core contract:

```python
token_rows = [(index, row.get("token")) for index, (name, row) in enumerate(events)
              if name == "token"]
if len(token_rows) < 2 or any(not isinstance(token, str) or not token
                              for _, token in token_rows):
    raise SystemExit("smoke-test: fewer than two non-empty token events")
done_index = names.index("done")
if any(index >= done_index for index, _ in token_rows):
    raise SystemExit("smoke-test: token event arrived after done")
draft = "".join(token for _, token in token_rows)
replacements = [row.get("answer") for name, row in events if name == "answer_replace"]
visible_answer = replacements[-1] if replacements else draft
if events[done_index][1].get("answer") != visible_answer:
    raise SystemExit("smoke-test: streamed answer does not match done answer")
```

- [ ] **Step 5: Run GREEN and commit exact scope**

```powershell
Push-Location $Worktree
try {
  & 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest -q tests/test_deploy_scripts.py -k smoke
  if ($LASTEXITCODE -ne 0) { throw 'true-SSE smoke tests failed' }
} finally { Pop-Location }
git -C $Worktree add -- deploy/bin/smoke-test.sh tests/test_deploy_scripts.py
$staged = @(git -C $Worktree diff --cached --name-only)
if ($staged.Count -ne 2 -or 'deploy/bin/smoke-test.sh' -notin $staged -or
    'tests/test_deploy_scripts.py' -notin $staged) { throw 'unexpected staged scope' }
git -C $Worktree diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'staged check failed' }
git -C $Worktree commit -m 'test(deploy): require true SSE token delivery'
```

Expected: smoke tests pass and one two-file commit is created.

---

### Task 3: Run complete local and container verification

**Files:**

- Read: pinned Python/Node lockfiles and both Dockerfiles.
- Generate ignored Frontend, Playwright, and Docker build outputs.

**Interfaces:**

- Consumes: clean correction branch.
- Produces: full Python, Frontend, browser, Linux portability, and image evidence.

- [ ] **Step 1: Verify tools and run focused Python gates**

```powershell
$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
& $Python -c "import sys; assert sys.version_info[:3] == (3,11,15); print(sys.version)"
node --version; npm.cmd --version; docker version --format '{{.Client.Version}}'; docker buildx version
Push-Location $Worktree
try {
  & $Python -m pytest -q tests/test_sse.py tests/test_rag_execution.py `
    tests/test_request_plan.py tests/test_chinese_bm25_analyzer.py `
    tests/test_docker_packaging.py tests/test_deploy_scripts.py `
    tests/test_codex_supervisor_processes.py
  if ($LASTEXITCODE -ne 0) { throw 'focused gates failed' }
} finally { Pop-Location }
```

Expected: exact Python 3.11.15 and all focused suites pass.

- [ ] **Step 2: Run the complete Python suite**

```powershell
Push-Location $Worktree
try { & $Python -m pytest -q; if ($LASTEXITCODE -ne 0) { throw 'full pytest failed' } }
finally { Pop-Location }
```

Expected: zero failures or errors.

- [ ] **Step 3: Run clean Frontend unit/build/browser gates**

```powershell
Push-Location "$Worktree\frontend\react-app"
try {
  npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
  npm.cmd test; if ($LASTEXITCODE -ne 0) { throw 'Vitest failed' }
  npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Vite build failed' }
  npx.cmd playwright test e2e/main-mobile-responsive.spec.ts
  if ($LASTEXITCODE -ne 0) { throw 'Playwright failed' }
} finally { Pop-Location }
```

Expected: unit, TypeScript/Vite, Chromium, and WebKit gates pass. Missing browser runtime blocks release.

- [ ] **Step 4: Prove Linux supervisor portability**

```powershell
docker run --rm --platform linux/amd64 --volume "${Worktree}:/workspace" `
  --workdir /workspace python:3.11.15-slim-bookworm `
  sh -lc 'python -m pip install --disable-pip-version-check -q pytest && python -m pytest -q tests/test_codex_supervisor_processes.py'
if ($LASTEXITCODE -ne 0) { throw 'Linux supervisor test failed' }
```

Expected: Linux branch passes and Windows-only branch skips.

- [ ] **Step 5: Build and inspect both production images**

```powershell
Push-Location $Worktree
try {
  docker buildx build --platform linux/amd64 --provenance=false --load `
    -f docker/Dockerfile.backend -t 1999wiki-backend:release-integrated-sse-local .
  if ($LASTEXITCODE -ne 0) { throw 'Backend build failed' }
  docker run --rm --platform linux/amd64 1999wiki-backend:release-integrated-sse-local `
    python -c 'import backend.main; print("backend import passed")'
  if ($LASTEXITCODE -ne 0) { throw 'Backend import failed' }
  docker buildx build --platform linux/amd64 --provenance=false --load `
    -f docker/Dockerfile.frontend -t 1999wiki-frontend:release-integrated-sse-local .
  if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
```

Expected: both images build and Backend imports its production entry point.

- [ ] **Step 6: Re-prove scope and cleanliness**

```powershell
$Head = git -C $Worktree rev-parse HEAD
git -C $Worktree merge-base --is-ancestor 2cbaef3a5c1235c95eba1cb18cd5e9f36ebd9dc6 $Head
if ($LASTEXITCODE -ne 0) { throw 'SSE ancestry lost' }
git -C $Worktree merge-base --is-ancestor 4c312c52ee7b1e018e4608aeda741fdc4bba9a79 $Head
if ($LASTEXITCODE -eq 0) { throw 'Thread C entered release' }
if (@(git -C $Worktree status --porcelain=v1).Count -ne 0) { throw 'dirty release worktree' }
```

Expected: true SSE present, C absent, worktree clean.

---

### Task 4: Push source and publish immutable TCR images

**Files:**

- Create ignored publication metadata under `.local/release-integrated-sse/<release>/`.
- Push branch: `origin/codex/release-integrated-sse`.

**Interfaces:**

- Consumes: exact clean commit and authenticated local TCR Docker client.
- Produces: two new digest-qualified TCR images and a verified canonical manifest.

- [ ] **Step 1: Push the reviewed branch as a source record**

```powershell
$Head = git -C $Worktree rev-parse HEAD
git -C $Worktree push --set-upstream origin codex/release-integrated-sse
if ($LASTEXITCODE -ne 0) { throw 'source branch push failed' }
$remote = (git -C $Worktree ls-remote origin refs/heads/codex/release-integrated-sse) -split '\s+'
if ($remote[0] -ne $Head) { throw 'remote source identity mismatch' }
```

Expected: remote branch equals the full local commit. Production never reads this branch.

- [ ] **Step 2: Derive immutable names and refuse overwrite**

```powershell
$Short = $Head.Substring(0, 7)
$Release = "sha-$Short"
$BackendTag = "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:$Release"
$FrontendTag = "ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-frontend:$Release"
$Evidence = "D:\1999Wiki\.local\release-integrated-sse\$Release"
New-Item -ItemType Directory -Path $Evidence -ErrorAction Stop | Out-Null
docker buildx imagetools inspect $BackendTag *> $null
if ($LASTEXITCODE -eq 0) { throw 'Backend tag exists; refuse overwrite' }
docker buildx imagetools inspect $FrontendTag *> $null
if ($LASTEXITCODE -eq 0) { throw 'Frontend tag exists; refuse overwrite' }
```

Expected: evidence directory is new and both TCR tags are absent.

- [ ] **Step 3: Build and push exact images directly to TCR**

```powershell
Push-Location $Worktree
try {
  docker buildx build --platform linux/amd64 --provenance=false --push `
    -f docker/Dockerfile.backend -t $BackendTag `
    --metadata-file "$Evidence\backend-build-metadata.json" .
  if ($LASTEXITCODE -ne 0) { throw 'Backend TCR push failed' }
  docker buildx build --platform linux/amd64 --provenance=false --push `
    -f docker/Dockerfile.frontend -t $FrontendTag `
    --metadata-file "$Evidence\frontend-build-metadata.json" .
  if ($LASTEXITCODE -ne 0) { throw 'Frontend TCR push failed' }
} finally { Pop-Location }
```

Expected: local authenticated Docker pushes both `linux/amd64` images; no GitHub registry path is used.

- [ ] **Step 4: Bind and verify registry digests**

```powershell
$BackendMeta = Get-Content -Raw "$Evidence\backend-build-metadata.json" | ConvertFrom-Json
$FrontendMeta = Get-Content -Raw "$Evidence\frontend-build-metadata.json" | ConvertFrom-Json
$BackendDigest = [string]$BackendMeta.'containerimage.digest'
$FrontendDigest = [string]$FrontendMeta.'containerimage.digest'
if ($BackendDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'invalid Backend digest' }
if ($FrontendDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'invalid Frontend digest' }
docker buildx imagetools inspect "$BackendTag@$BackendDigest" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Backend digest absent from TCR' }
docker buildx imagetools inspect "$FrontendTag@$FrontendDigest" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Frontend digest absent from TCR' }
```

Expected: both exact tag/digest identities resolve in TCR.

- [ ] **Step 5: Create and verify the canonical manifest**

```powershell
$Manifest = "$Evidence\release-manifest.json"
& $Python "$Worktree\deploy\bin\release_manifest.py" create `
  --commit $Head --backend-digest $BackendDigest --frontend-digest $FrontendDigest `
  --backend-ghcr-status deferred_after_5_network_failures `
  --frontend-ghcr-status deferred_after_5_network_failures --output $Manifest
if ($LASTEXITCODE -ne 0) { throw 'manifest creation failed' }
& $Python "$Worktree\deploy\bin\release_manifest.py" verify `
  --manifest $Manifest --commit $Head --registry tcr
if ($LASTEXITCODE -ne 0) { throw 'manifest TCR verification failed' }
$ManifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Manifest).Hash.ToLowerInvariant()
[ordered]@{
  commit=$Head; release=$Release; backend="$BackendTag@$BackendDigest";
  frontend="$FrontendTag@$FrontendDigest"; manifest_path=$Manifest;
  manifest_sha256=$ManifestHash
} | ConvertTo-Json | Set-Content "$Evidence\publication-receipt.json" -Encoding UTF8
```

Expected: state `ready_with_deferred_ghcr`, exact TCR digests, immutable manifest hash, and a non-secret receipt.

---

### Task 5: Install the runtime bundle and prepare green

**Files:**

- Create: `.local/release-integrated-sse/<release>/runtime-bundle.tar`.
- Atomically replace: `/srv/1999wiki/runtime-bundle`.
- Retain: `/srv/1999wiki/runtime-bundle.pre-<release>`.
- Install: `/srv/1999wiki/releases/<release>/{release-manifest.json,release.identity,green.env}`.

**Interfaces:**

- Consumes: verified publication receipt, exact `deploy/` tree, active blue state, and authorized old green retirement.
- Produces: empty green slot, reviewed runtime bundle, and validated green release environment.

- [ ] **Step 1: Capture and validate live identities**

Run an LF-normalized read-only remote script under `sudo` that sources `/srv/1999wiki/deploy-state/active.env` and requires:

```bash
test "$ACTIVE_SLOT" = blue
test "$ACTIVE_RELEASE" = sha-05ccd6b
test "$PREVIOUS_AVAILABLE" = 1
test "$PREVIOUS_SLOT" = green
test "$PREVIOUS_RELEASE" = sha-1ec7752
test "$(docker inspect --format '{{.State.Health.Status}} {{.RestartCount}}' 1999wiki-blue-backend-1)" = 'healthy 0'
test "$(docker inspect --format '{{.State.Health.Status}} {{.RestartCount}}' 1999wiki-blue-frontend-1)" = 'healthy 0'
curl --fail --silent --show-error http://127.0.0.1/health/ready >/dev/null
```

Hash the active-build and BM25 files and require the exact values in Global Constraints. Verify the server's protected Docker client can `docker manifest inspect` both digest-qualified image references from the publication receipt.

Expected: blue healthy, previous green exact, data identities exact, TCR readable.

- [ ] **Step 2: Build and transfer an exact Git runtime archive**

```powershell
$Bundle = "$Evidence\runtime-bundle.tar"
git -C $Worktree archive --format=tar --output=$Bundle $Head deploy
if ($LASTEXITCODE -ne 0) { throw 'runtime archive creation failed' }
$BundleHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Bundle).Hash.ToLowerInvariant()
$RemoteBundle = "/home/ubuntu/runtime-bundle-$Release.tar"
ssh 1999wiki "test ! -e '$RemoteBundle'"
if ($LASTEXITCODE -ne 0) { throw 'remote bundle path exists' }
scp $Bundle "1999wiki`:$RemoteBundle"
if ($LASTEXITCODE -ne 0) { throw 'runtime archive transfer failed' }
```

Expected: exact archive transferred to a new staging path.

- [ ] **Step 3: Verify the full tree and atomically install its only changed deploy file**

Pass `$BundleHash`, `$RemoteBundle`, and `$Release` as non-secret inputs to a root script. The active release, safe base, and both historical corrections share deploy tree `88a584e2e4411f1bf5b61fdaab3b87e06da264ef`; therefore the strengthened `smoke-test.sh` must be the only tracked deploy-file delta. The script must:

```bash
set -euo pipefail
test "$(sha256sum "$REMOTE_BUNDLE" | awk '{print $1}')" = "$EXPECTED_SHA256"
STAGE="/srv/1999wiki/runtime-bundle.stage-$RELEASE"
BACKUP="/srv/1999wiki/runtime-bundle.pre-$RELEASE"
test ! -e "$STAGE" && test ! -e "$BACKUP"
install -d -m 0750 "$STAGE"
tar -xf "$REMOTE_BUNDLE" -C "$STAGE"
chown -R root:root "$STAGE"
find "$STAGE" -type d -exec chmod 0750 {} +
find "$STAGE" -type f -exec chmod 0640 {} +
chmod 0750 "$STAGE"/deploy/bin/*.sh "$STAGE"/deploy/bin/*.py
find "$STAGE/deploy/bin" -name '*.sh' -exec bash -n {} +
python3 -m py_compile "$STAGE"/deploy/bin/*.py

# Compare every staged tracked file with the live bundle. Exactly one path may differ.
python3 - "$STAGE" /srv/1999wiki/runtime-bundle <<'PY'
import hashlib
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])
live = pathlib.Path(sys.argv[2])
different = []
for candidate in sorted((stage / "deploy").rglob("*")):
    if not candidate.is_file() or "__pycache__" in candidate.parts:
        continue
    relative = candidate.relative_to(stage)
    current = live / relative
    if not current.is_file():
        raise SystemExit(f"runtime bundle missing tracked file: {relative}")
    if hashlib.sha256(candidate.read_bytes()).digest() != hashlib.sha256(current.read_bytes()).digest():
        different.append(relative.as_posix())
if different != ["deploy/bin/smoke-test.sh"]:
    raise SystemExit(f"unexpected runtime bundle delta: {different!r}")
PY

cp -a /srv/1999wiki/runtime-bundle "$BACKUP"
TEMP=/srv/1999wiki/runtime-bundle/deploy/bin/.smoke-test.sh.$RELEASE
install -o root -g root -m 0750 "$STAGE/deploy/bin/smoke-test.sh" "$TEMP"
mv -f "$TEMP" /srv/1999wiki/runtime-bundle/deploy/bin/smoke-test.sh

# Final tracked files must now be byte-identical to the reviewed stage.
python3 - "$STAGE" /srv/1999wiki/runtime-bundle <<'PY'
import hashlib
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])
live = pathlib.Path(sys.argv[2])
for candidate in sorted((stage / "deploy").rglob("*")):
    if not candidate.is_file() or "__pycache__" in candidate.parts:
        continue
    relative = candidate.relative_to(stage)
    current = live / relative
    if not current.is_file() or hashlib.sha256(candidate.read_bytes()).digest() != hashlib.sha256(current.read_bytes()).digest():
        raise SystemExit(f"runtime bundle verification failed: {relative}")
PY
rm -f "$REMOTE_BUNDLE"
```

Expected: every tracked deploy file matches the reviewed archive, `smoke-test.sh` changed by a same-directory atomic rename, the complete prior bundle is recoverable, and no live application state changed.

- [ ] **Step 4: Retire only the exact stopped green deployment**

Re-read and require the Step 1 state, require exactly two stopped green application containers, then run:

```powershell
ssh 1999wiki "cd /srv/1999wiki/runtime-bundle && sudo -n bash deploy/bin/cleanup.sh sha-1ec7752 green remove-green-sha-1ec7752"
if ($LASTEXITCODE -ne 0) { throw 'authorized green retirement failed' }
```

Expected: green app containers/network removed, `PREVIOUS_AVAILABLE=0`, blue still `healthy 0`, and old green manifest/snapshot retained.

- [ ] **Step 5: Transfer and install the canonical manifest**

```powershell
$RemoteManifest = "/home/ubuntu/release-manifest-$Release.json"
ssh 1999wiki "sudo -n test ! -e '/srv/1999wiki/releases/$Release' && test ! -e '$RemoteManifest'"
if ($LASTEXITCODE -ne 0) { throw 'target release path exists' }
scp $Manifest "1999wiki`:$RemoteManifest"
if ($LASTEXITCODE -ne 0) { throw 'manifest transfer failed' }
```

The remote root script must hash-check against `$ManifestHash`, install the release directory mode `0700` and manifest mode `0600`, then remove the unprivileged staging copy.

Expected: server manifest hash equals the canonical local hash.

- [ ] **Step 6: Generate and validate green identity**

Run from `/srv/1999wiki/runtime-bundle`:

```bash
python3 deploy/bin/release_manifest.py verify \
  --manifest "/srv/1999wiki/releases/$RELEASE/release-manifest.json" \
  --commit "$FULL_COMMIT" --registry tcr \
  >"/srv/1999wiki/releases/$RELEASE/release.identity"
cat "/srv/1999wiki/releases/$RELEASE/release.identity" \
  >"/srv/1999wiki/releases/$RELEASE/green.env"
printf 'BACKEND_PORT=18200\nFRONTEND_PORT=18280\n' \
  >>"/srv/1999wiki/releases/$RELEASE/green.env"
chmod 0600 "/srv/1999wiki/releases/$RELEASE/release.identity" \
  "/srv/1999wiki/releases/$RELEASE/green.env"
python3 deploy/bin/ops_helper.py validate-env release \
  "/srv/1999wiki/releases/$RELEASE/green.env" --release "$RELEASE"
```

Expected: green env binds only exact TCR digests and ports 18200/18280.

**Review gate:** Stop unless blue is healthy, green empty, previous cleared, runtime backup present, and release files validate.

---

### Task 6: Deploy green and switch traffic

**Files:**

- Execute: `deploy/bin/preflight.sh`, `deploy/bin/deploy.sh`, and on failure only `deploy/bin/rollback.sh`.

**Interfaces:**

- Consumes: empty green slot and validated green env.
- Produces: green tested twice by the strengthened smoke gate before atomic switch; blue becomes previous.

- [ ] **Step 1: Run standalone preflight**

```powershell
ssh 1999wiki "cd /srv/1999wiki/runtime-bundle && sudo -n env PUBLIC_BASE_URL=http://127.0.0.1 bash deploy/bin/preflight.sh $Release green"
if ($LASTEXITCODE -ne 0) { throw 'green preflight failed' }
```

Expected: closure, permissions, capacity, infrastructure, image/env, Caddy, and empty-slot checks pass.

- [ ] **Step 2: Execute the checked-in deployment transaction**

Run this as an LF-normalized remote script:

```bash
cd /srv/1999wiki/runtime-bundle
sudo -n env SMOKE_RAG_QUESTION='请介绍槲寄生' \
  PUBLIC_BASE_URL='http://127.0.0.1' \
  bash deploy/bin/deploy.sh "$RELEASE" green
```

The strong smoke runs once in `deploy.sh` and again in `switch.sh`; both must observe at least two non-empty tokens before exactly one `done` and prove visible/final answer equality. If the transaction fails, inspect `ACTIVE_RELEASE`: roll back immediately if it equals the new release; otherwise require blue `sha-05ccd6b` still active.

Expected: green pulled from TCR, tested twice, switched atomically; blue stopped.

- [ ] **Step 3: Verify authoritative post-switch state**

Require:

```bash
source /srv/1999wiki/deploy-state/active.env
test "$ACTIVE_SLOT" = green
test "$ACTIVE_RELEASE" = "$RELEASE"
test "$PREVIOUS_AVAILABLE" = 1
test "$PREVIOUS_SLOT" = blue
test "$PREVIOUS_RELEASE" = sha-05ccd6b
test "$(docker inspect --format '{{.State.Health.Status}} {{.RestartCount}}' 1999wiki-green-backend-1)" = 'healthy 0'
test "$(docker inspect --format '{{.State.Health.Status}} {{.RestartCount}}' 1999wiki-green-frontend-1)" = 'healthy 0'
test -z "$(docker ps --filter name=1999wiki-blue --format '{{.ID}}')"
curl --fail --silent --show-error http://127.0.0.1/health/ready >/dev/null
```

Expected: green active/healthy; blue stopped and recorded as previous.

---

### Task 7: Verify visible public streaming, A/B behavior, stability, and rollback

**Files:**

- Read: public routes, browser UI, container state, and logs.
- Execute: `deploy/bin/rollback.sh` only on a failed post-switch gate.

**Interfaces:**

- Consumes: switched green deployment.
- Produces: public progressive-streaming proof, A/B/data proof, 10-minute stability evidence, or verified rollback to blue.

- [ ] **Step 1: Repeat canonical smoke through green**

```powershell
ssh 1999wiki "cd /srv/1999wiki/runtime-bundle && sudo -n env SMOKE_RAG_QUESTION='请介绍槲寄生' bash deploy/bin/smoke-test.sh http://127.0.0.1:18280 http://127.0.0.1 /srv/1999wiki/protected/app.env"
if ($LASTEXITCODE -ne 0) { throw 'post-switch smoke failed' }
```

Expected: shell/assets, readiness, Wiki, sync RAG, multi-token SSE, and media pass.

- [ ] **Step 2: Prove public Caddy delivers tokens before completion**

Run a remote Python probe against `http://127.0.0.1/api/ask/stream` using `请详细介绍十四行诗的技能和背景故事`. Parse blank-line-delimited SSE blocks incrementally and record `time.monotonic()` per block. Require `status: generating` before the first token, at least two non-empty tokens before `done`, first-token timestamp strictly earlier than completion, any `answer_replace` before `done`, visible answer equal to `done.answer`, and no `error`. Print event names, token count, first-token/completion latency, and correction presence only; do not print answer text.

```python
import json
import time
import urllib.request

started = time.monotonic()
request = urllib.request.Request(
    "http://127.0.0.1/api/ask/stream",
    data=json.dumps(
        {"question": "请详细介绍十四行诗的技能和背景故事"},
        ensure_ascii=False,
    ).encode("utf-8"),
    headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    method="POST",
)
events = []
with urllib.request.urlopen(request, timeout=120) as response:
    event_name = "message"
    data_lines = []
    for raw_line in response:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if not line:
            if data_lines:
                events.append((event_name, json.loads("\n".join(data_lines)), time.monotonic()))
            event_name, data_lines = "message", []
            continue
        if line.startswith("event:"):
            event_name = line.partition(":")[2].strip()
        elif line.startswith("data:"):
            data_lines.append(line.partition(":")[2].lstrip())

names = [name for name, _, _ in events]
assert "error" not in names, names
done_index = names.index("done")
assert done_index == len(events) - 1 and names.count("done") == 1, names
token_rows = [(i, row["token"], stamp) for i, (name, row, stamp) in enumerate(events)
              if name == "token" and isinstance(row.get("token"), str) and row["token"]]
assert len(token_rows) >= 2, names
generating_index = next(i for i, (name, row, _) in enumerate(events)
                        if name == "status" and row.get("phase") == "generating")
assert generating_index < token_rows[0][0] < done_index
replace_rows = [(i, row["answer"]) for i, (name, row, _) in enumerate(events)
                if name == "answer_replace"]
assert all(i < done_index for i, _ in replace_rows)
draft = "".join(token for _, token, _ in token_rows)
visible = replace_rows[-1][1] if replace_rows else draft
assert visible == events[done_index][1]["answer"]
print(json.dumps({
    "event_names": names,
    "token_count": len(token_rows),
    "first_token_seconds": round(token_rows[0][2] - started, 3),
    "done_seconds": round(events[done_index][2] - started, 3),
    "corrected": bool(replace_rows),
}, ensure_ascii=False))
```

Expected: multiple public token events arrive before completion.

- [ ] **Step 3: Verify the actual browser UI visibly grows**

Read and use `browser:control-in-app-browser`. Open the configured public site, submit `请详细介绍十四行诗的技能和背景故事`, and capture at least two distinct intermediate UI states before completion. Require assistant text to grow between states, then require final answer and sources/citations to remain visible.

Expected: text renders progressively rather than appearing only at `done`.

- [ ] **Step 4: Verify A composite routing through public API**

POST `你好，你是谁，请介绍一下十四行诗` to `/api/ask`. Require `effective_route == "composite"`, `retrieval_outcome == "sufficient"`, ordered task types exactly `social_smalltalk`, `assistant_meta`, and `knowledge_base`, non-empty answer/sources, and knowledge citation IDs resolving to returned sources.

```python
import json
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1/api/ask",
    data=json.dumps(
        {"question": "你好，你是谁，请介绍一下十四行诗"},
        ensure_ascii=False,
    ).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=120) as response:
    payload = json.load(response)
route = payload["route"]
subtasks = payload["subtasks"]
sources = payload["sources"]
assert route["effective_route"] == "composite", route
assert route["retrieval_outcome"] == "sufficient", route
assert [row["task_type"] for row in subtasks] == [
    "social_smalltalk", "assistant_meta", "knowledge_base"
]
source_ids = {row["citation_id"] for row in sources if row.get("citation_id")}
kb_citations = set(subtasks[2]["citation_ids"])
assert payload["answer"].strip() and sources and kb_citations
assert kb_citations <= source_ids
print(json.dumps({
    "task_types": [row["task_type"] for row in subtasks],
    "source_count": len(sources),
    "kb_citation_count": len(kb_citations),
}, ensure_ascii=False))
```

Expected: A remains active alongside true streaming.

- [ ] **Step 5: Re-prove BM25 v2 and Milvus identities**

Hash the active-build and BM25 files again and require the exact Global Constraints values. Parse JSON and require `huiji.bm25-index/v2` plus `text_child_bge_m3_shadow_crawler_v3_20260721t051246z`.

```python
import hashlib
import json
from pathlib import Path

active_path = Path("/srv/1999wiki/rag-artifacts/active_build.v1.json")
bm25_path = Path("/srv/1999wiki/rag-artifacts/crawler-v3-20260721t051246z/indexes/child_text_bm25.json")
active_raw = active_path.read_bytes()
bm25_raw = bm25_path.read_bytes()
assert hashlib.sha256(active_raw).hexdigest() == "87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e"
assert hashlib.sha256(bm25_raw).hexdigest() == "70519e409f7b962cd52bd532bfa0a65fdc22b27ea545157e42ad13f3bf96f20a"
active = json.loads(active_raw)
bm25 = json.loads(bm25_raw)
assert bm25["schema_version"] == "huiji.bm25-index/v2"
assert active["milvus_collection_name"] == "text_child_bge_m3_shadow_crawler_v3_20260721t051246z"
print("BM25 v2 and Milvus identities unchanged")
```

Expected: no retrieval or data identity drift.

- [ ] **Step 6: Observe production for 10 minutes**

Run 20 samples at 30-second intervals. Every sample must require public readiness and green Backend/Frontend `healthy 0`; record disk and memory. Review Caddy and both green logs for the same window and fail on traceback, panic, repeated 5xx, unhealthy transition, or restart. Use yielded waits no longer than 60 seconds and keep the user updated.

```bash
set -euo pipefail
for iteration in $(seq 1 20); do
  printf 'sample=%s timestamp=%s\n' "$iteration" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  curl --fail --silent --show-error http://127.0.0.1/health/ready >/dev/null
  test "$(docker inspect --format '{{.State.Health.Status}} {{.RestartCount}}' 1999wiki-green-backend-1)" = 'healthy 0'
  test "$(docker inspect --format '{{.State.Health.Status}} {{.RestartCount}}' 1999wiki-green-frontend-1)" = 'healthy 0'
  df -B1 --output=avail /srv/1999wiki | awk 'NR==2 {print "disk_available_bytes=" $1}'
  free -m | awk 'NR==2 {print "memory_available_mb=" $7}'
  sleep 30
done
journalctl -u caddy --since '-12 minutes' --no-pager
docker logs --since 12m 1999wiki-green-backend-1 2>&1 | tail -200
docker logs --since 12m 1999wiki-green-frontend-1 2>&1 | tail -200
```

Expected: 20/20 ready, zero restarts, no critical error, disk above 8 GiB.

- [ ] **Step 7: Apply the exact failure branch when needed**

Do not run on success. On the first critical post-switch failure:

```powershell
ssh 1999wiki "cd /srv/1999wiki/runtime-bundle && sudo -n env SMOKE_RAG_QUESTION='请介绍槲寄生' PUBLIC_BASE_URL=http://127.0.0.1 bash deploy/bin/rollback.sh"
if ($LASTEXITCODE -ne 0) { throw 'rollback transaction failed' }
```

Then require active blue `sha-05ccd6b`, public readiness, and blue Backend/Frontend `healthy 0`.

Expected on failure: blue restored and correction reported not online.

**Review gate:** On success, do not clean blue, the prior runtime bundle, or any release snapshot.

---

### Task 8: Record evidence and close the correction release

**Files:**

- Create: `docs/superpowers/reports/2026-08-04-integrated-sse-correction-release.md`
- Do not stage: the four unrelated user documents.

**Interfaces:**

- Consumes: exact Git, TCR, manifest, production, browser, data, and observation evidence.
- Produces: committed release report and immutable final handoff.

- [ ] **Step 1: Capture final state without mutation**

Read `active.env`, manifest/build/BM25 hashes, green image/health/restart identities, previous blue snapshot presence, runtime-bundle backup presence, public readiness, and remote branch identity.

Expected on success: new green active, blue `sha-05ccd6b` previous, green `healthy 0`, exact data hashes.

- [ ] **Step 2: Create the report with actual values**

Use `apply_patch` with these exact headings:

```markdown
# Integrated SSE Correction Production Release Report

## Outcome
## Root cause corrected
## Exact source boundary
## Local verification
## TCR publication and manifest
## Runtime bundle and green retirement
## Inactive candidate and traffic switch
## True streaming acceptance
## A/B and data identity preservation
## Stability observation
## Rollback readiness
## Unrelated workspace preservation
```

Record full commit, release tag, TCR digests, manifest hash/state, test counts, Playwright result, token count/timings without answer text, browser-visible evidence, active/previous states, unchanged data hashes, and whether rollback ran.

- [ ] **Step 3: Self-review and commit only the report**

```powershell
$Report = 'docs/superpowers/reports/2026-08-04-integrated-sse-correction-release.md'
if (-not (Test-Path $Report -PathType Leaf)) { throw 'report missing' }
$patterns = @('T' + 'BD', 'T' + 'ODO', 'PLACE' + 'HOLDER', 'FIX' + 'ME',
  'numeric-' + 'run-id', 'digest-' + 'goes-here')
$redFlags = rg -n ($patterns -join '|') $Report
if ($LASTEXITCODE -eq 0) { $redFlags; throw 'report contains unresolved marker text' }
git diff --check -- $Report
if ($LASTEXITCODE -ne 0) { throw 'report check failed' }
git add -- $Report
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 1 -or $staged[0] -ne $Report) { throw 'unexpected staged scope' }
git commit -m 'docs: record integrated SSE correction release'
if ($LASTEXITCODE -ne 0) { throw 'report commit failed' }
```

Expected: one report commit; user files remain unstaged.

- [ ] **Step 4: Verify before completion and deliver status**

Read and use `superpowers:verification-before-completion`. Freshly re-run public readiness, active/previous identity, container health/restarts, manifest hash, release remote identity, and main status before claiming success.

On success, lead with new green release, visible multi-token result, both TCR image digests, unchanged BM25/Milvus, 10-minute stability, and blue rollback. On failure, lead with the failed gate and verified active release after rollback.

---

## Completion Checklist

- [ ] Safe base includes A/B and true SSE and excludes Thread C.
- [ ] Packaging and CI fixes apply without conflict.
- [ ] Strong smoke gate demonstrates RED then GREEN.
- [ ] Python, Frontend, Playwright, Linux portability, and Docker gates pass.
- [ ] Clean correction branch exactly matches its pushed remote ref.
- [ ] Both immutable images and canonical manifest verify in TCR.
- [ ] Runtime bundle is hash-verified and atomically installed with backup retained.
- [ ] Only previous green `sha-1ec7752` is retired with exact confirmation.
- [ ] Green candidate proves multiple tokens before `done` before switch.
- [ ] Public API and actual UI visibly stream incremental text.
- [ ] A composite behavior remains correct.
- [ ] BM25 v2, active build, and Milvus identities remain unchanged.
- [ ] Ten-minute observation passes with zero restarts and no critical errors.
- [ ] Blue `sha-05ccd6b` remains the protected rollback target.
- [ ] Final report is the only correction evidence committed on `main`.
