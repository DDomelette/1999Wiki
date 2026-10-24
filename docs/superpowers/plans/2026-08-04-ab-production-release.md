# A/B Production Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the exact A/B merge commit as immutable Backend and Frontend images, deploy it through the protected blue/green production workflow, and prove A is active while the BM25 v2 and Milvus identities remain unchanged.

**Architecture:** Create an isolated release worktree fixed to `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`, pass local and GitHub release gates, then deploy digest-qualified TCR images with the checked-in production scripts. The deployment script tests the inactive blue slot against real production dependencies before its atomic switch; public-route regression and a bounded observation window follow immediately, with `rollback.sh` as the only post-switch recovery action.

**Tech Stack:** Git and Git worktrees, PowerShell 5, Conda Python 3.11.15, pytest, Node.js/npm/Vitest/Vite, Docker BuildKit, GitHub Actions and `gh`, TCR/GHCR, SSH, Bash, Docker Compose, Caddy.

## Global Constraints

- Release source is exactly `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`; release name is `sha-daf3fe8`; branch is `codex/release-ab`.
- Do not release the current `main`, Thread C, D0, E, or any working-tree content after the A/B merge.
- Keep production BM25 at `huiji.bm25-index/v2`; do not build, upload, or activate v3.
- Keep active Milvus collection `text_child_bge_m3_shadow_crawler_v3_20260721t051246z`; perform no corpus, embedding, Milvus, media, or database write.
- Do not modify, stage, stash, clean, reset, or commit the four unrelated user document changes in `D:\1999Wiki`.
- The only authorized retirement is stopped blue `sha-0761382` with confirmation `remove-blue-sha-0761382`; never retire active green `sha-1ec7752` in this change window.
- Never print, persist, or place TCR credentials or GitHub tokens in process arguments. The TCR password may exist only in protected remote storage, process memory, and the encrypted GitHub Secret.
- Accept only digest-qualified image identities from a verified canonical `1999wiki.release/v2` manifest.
- A failed gate stops the release. A failed post-switch gate invokes `rollback.sh`; do not repair production in place.
- Do not retire the new rollback target after the switch.

## File and state map

**Created during planning:**

- `docs/superpowers/plans/2026-08-04-ab-production-release.md` — this executable plan.

**Created only after verified deployment:**

- `docs/superpowers/reports/2026-08-04-ab-production-release.md` — committed human-readable release evidence.
- `.local/release-ab/run-$RunId/release-manifest.json` — ignored GitHub artifact downloaded from the exact publication run, where `$RunId` is the validated numeric Actions run ID.
- `.local/release-ab/dispatch-boundary.json` — ignored create-new dispatch timestamp and immutable input identity.
- `.local/release-ab/selected-run.json` — ignored uniquely selected Actions run metadata.
- `.local/release-ab/publication-receipt.json` — ignored manifest/run handoff consumed by production tasks.

**Remote production files created or updated:**

- `/srv/1999wiki/releases/sha-daf3fe8/release-manifest.json` — byte-identical canonical manifest.
- `/srv/1999wiki/releases/sha-daf3fe8/release.identity` — verified TCR commit and digest-qualified image identities.
- `/srv/1999wiki/releases/sha-daf3fe8/blue.env` — release identity plus `BACKEND_PORT=18100` and `FRONTEND_PORT=18180`.
- `/srv/1999wiki/deploy-state/active.env` — updated only by checked-in cleanup/switch/rollback transactions.
- `/srv/1999wiki/deploy-state/snapshots/sha-daf3fe8/blue/` — protected snapshot created by `deploy.sh`.

**Read-only release interfaces:**

- `.github/workflows/publish-images.yml`
- `.github/scripts/publish_registries.py`
- `deploy/bin/release_manifest.py`
- `deploy/bin/cleanup.sh`
- `deploy/bin/deploy.sh`
- `deploy/bin/preflight.sh`
- `deploy/bin/smoke-test.sh`
- `deploy/bin/switch.sh`
- `deploy/bin/rollback.sh`

---

### Task 1: Create the isolated release identity

**Files:**

- Read: `docs/superpowers/specs/2026-08-04-ab-production-release-design.md`
- Read: `.github/workflows/publish-images.yml`
- Create worktree: `D:\1999Wiki.worktrees\release-ab`
- Create branch ref: `refs/heads/codex/release-ab`

**Interfaces:**

- Consumes: full Git object `daf3fe85390c534e0177c2eb06768b7f9ffc3a44` from `D:\1999Wiki`.
- Produces: a clean worktree whose `HEAD`, branch ref, and tree are the immutable input for all later tasks.

- [ ] **Step 1: Invoke the worktree safety procedure**

Use `superpowers:using-git-worktrees` before creating the worktree. Confirm the current checkout is not already a linked worktree and that the chosen worktree directory is outside `D:\1999Wiki`.

- [ ] **Step 2: Prove the release source identities before branch creation**

Run from `D:\1999Wiki`:

```powershell
$ReleaseCommit = 'daf3fe85390c534e0177c2eb06768b7f9ffc3a44'
$ACommit = '7535df532c26dfdef0c9a951a2c9f2c7d149824a'

if ((git rev-parse "$ReleaseCommit^{commit}") -ne $ReleaseCommit) {
    throw 'release commit does not resolve exactly'
}
git merge-base --is-ancestor $ACommit $ReleaseCommit
if ($LASTEXITCODE -ne 0) { throw 'Thread A merge is not an ancestor of Thread B merge' }

$parents = @(git rev-list --parents -n 1 $ReleaseCommit)
if ($parents -ne "$ReleaseCommit $ACommit af17aeb9114008d79ff38d0cae5d9e46ae845354") {
    throw 'A/B merge parent identity changed'
}

if ((git rev-parse "$ReleaseCommit`:deploy") -ne '88a584e2e4411f1bf5b61fdaab3b87e06da264ef') {
    throw 'deploy tree identity changed'
}
```

Expected: all commands exit zero and emit no exception.

- [ ] **Step 3: Refuse an ambiguous pre-existing branch or directory**

```powershell
$ReleaseWorktree = 'D:\1999Wiki.worktrees\release-ab'
if (Test-Path -LiteralPath $ReleaseWorktree) {
    throw 'release worktree path already exists; inspect it instead of overwriting it'
}
git show-ref --verify --quiet refs/heads/codex/release-ab
if ($LASTEXITCODE -eq 0) {
    throw 'release branch already exists; verify its identity instead of recreating it'
}
```

Expected: neither target exists. If either exists, stop and inspect; do not delete it.

- [ ] **Step 4: Create the release worktree and branch**

```powershell
git worktree add -b codex/release-ab `
    'D:\1999Wiki.worktrees\release-ab' `
    'daf3fe85390c534e0177c2eb06768b7f9ffc3a44'
```

Expected: Git creates a linked worktree on `codex/release-ab`.

- [ ] **Step 5: Verify the new worktree is byte-clean and isolated**

```powershell
$ReleaseWorktree = 'D:\1999Wiki.worktrees\release-ab'
$Expected = 'daf3fe85390c534e0177c2eb06768b7f9ffc3a44'

if ((git -C $ReleaseWorktree rev-parse HEAD) -ne $Expected) { throw 'wrong HEAD' }
if ((git -C $ReleaseWorktree branch --show-current) -ne 'codex/release-ab') {
    throw 'wrong release branch'
}
if (@(git -C $ReleaseWorktree status --porcelain=v1).Count -ne 0) {
    throw 'release worktree is not clean'
}
if ((git -C 'D:\1999Wiki' status --short | Measure-Object).Count -ne 4) {
    throw 'main workspace user-change count drifted; inspect before continuing'
}
```

Expected: release worktree clean; main workspace still shows exactly the four unrelated user changes.

**Review gate:** The worktree contains no new commit and must still point exactly to `daf3fe85390c534e0177c2eb06768b7f9ffc3a44`.

---

### Task 2: Run the local package and regression gates

**Files:**

- Read: `requirements/dev.lock.txt`
- Read: `frontend/react-app/package-lock.json`
- Read: `docker/Dockerfile.backend`
- Read: `docker/Dockerfile.frontend`
- Generated and ignored: `frontend/react-app/node_modules/`, `frontend/react-app/dist/`
- Generated local Docker tags: `1999wiki-backend:release-ab-local`, `1999wiki-frontend:release-ab-local`

**Interfaces:**

- Consumes: clean release worktree from Task 1.
- Produces: local evidence that the full Python suite, frontend suite/build, and both production image builds pass from the exact commit.

- [ ] **Step 1: Verify pinned toolchain identities**

```powershell
$ReleaseWorktree = 'D:\1999Wiki.worktrees\release-ab'
$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'

& $Python -c "import sys; assert sys.version_info[:3] == (3, 11, 15); print(sys.executable); print(sys.version)"
node --version
npm.cmd --version
docker version --format '{{.Client.Version}}'
docker buildx version
```

Expected: Python is exactly 3.11.15 from the `1999wiki` environment; every command exits zero.

- [ ] **Step 2: Run the complete Python test suite**

```powershell
Push-Location 'D:\1999Wiki.worktrees\release-ab'
try {
    & 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'full Python suite failed' }
} finally {
    Pop-Location
}
```

Expected: pytest exits zero with no failed or errored test.

- [ ] **Step 3: Run a clean frontend install and test suite**

```powershell
Push-Location 'D:\1999Wiki.worktrees\release-ab\frontend\react-app'
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'frontend tests failed' }
} finally {
    Pop-Location
}
```

Expected: lockfile install and Vitest both exit zero.

- [ ] **Step 4: Build the production frontend**

```powershell
Push-Location 'D:\1999Wiki.worktrees\release-ab\frontend\react-app'
try {
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'frontend production build failed' }
} finally {
    Pop-Location
}
```

Expected: TypeScript and Vite exit zero and create `dist/`.

- [ ] **Step 5: Build both release Docker images locally without pushing**

```powershell
Push-Location 'D:\1999Wiki.worktrees\release-ab'
try {
    docker build --file docker/Dockerfile.backend `
        --tag 1999wiki-backend:release-ab-local .
    if ($LASTEXITCODE -ne 0) { throw 'backend image build failed' }

    docker build --file docker/Dockerfile.frontend `
        --tag 1999wiki-frontend:release-ab-local .
    if ($LASTEXITCODE -ne 0) { throw 'frontend image build failed' }
} finally {
    Pop-Location
}
```

Expected: both builds exit zero; no registry push occurs.

- [ ] **Step 6: Re-prove source cleanliness after generated outputs**

```powershell
$ReleaseWorktree = 'D:\1999Wiki.worktrees\release-ab'
if (@(git -C $ReleaseWorktree status --porcelain=v1).Count -ne 0) {
    git -C $ReleaseWorktree status --short
    throw 'release verification changed tracked or untracked release inputs'
}
if ((git -C $ReleaseWorktree rev-parse HEAD) -ne 'daf3fe85390c534e0177c2eb06768b7f9ffc3a44') {
    throw 'release HEAD changed during verification'
}
```

Expected: clean worktree and unchanged HEAD.

**Review gate:** Do not push the branch unless every local gate passed from the exact release worktree.

---

### Task 3: Repair the protected TCR boundary and publish the branch ref

**Files:**

- Read remotely: `/root/.docker/config.json` through `sudo`.
- External updates: GitHub repository Secrets `TCR_USERNAME` and `TCR_PASSWORD`.
- External create/update: `refs/heads/codex/release-ab` on `origin`.

**Interfaces:**

- Consumes: locally verified worktree from Task 2 and the production server's currently valid TCR credential.
- Produces: a remote release branch fixed to the expected commit and updated encrypted GitHub Secrets.

- [ ] **Step 1: Prove the protected server credential still reads TCR**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki `
  "sudo -n docker manifest inspect ccr.ccs.tencentyun.com/1999wiki_code/1999wiki-backend:sha-1ec7752 >/dev/null"
if ($LASTEXITCODE -ne 0) { throw 'protected TCR credential probe failed' }
```

Expected: exit zero with no credential output.

- [ ] **Step 2: Validate credential shape without printing the password**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "sudo -n python3 - <<'PY'
import base64, json
from pathlib import Path

data = json.loads(Path('/root/.docker/config.json').read_text())
encoded = data.get('auths', {}).get('ccr.ccs.tencentyun.com', {}).get('auth', '')
raw = base64.b64decode(encoded).decode('utf-8')
username, separator, password = raw.partition(':')
assert separator and username == '100017272217' and password
print('protected TCR credential shape is valid')
PY"
if ($LASTEXITCODE -ne 0) { throw 'protected credential shape validation failed' }
```

Expected: only the non-secret validation sentence is printed.

- [ ] **Step 3: Stream both values from protected storage into GitHub Secrets**

Run this exact in-memory bridge; it captures the remote JSON only inside the Python process and sends each value to `gh secret set` over stdin:

```powershell
@'
import base64
import json
import shlex
import subprocess

remote_program = r'''
import base64, json
from pathlib import Path
data = json.loads(Path("/root/.docker/config.json").read_text())
encoded = data["auths"]["ccr.ccs.tencentyun.com"]["auth"]
raw = base64.b64decode(encoded).decode("utf-8")
username, separator, password = raw.partition(":")
assert separator and username == "100017272217" and password
print(json.dumps({"username": username, "password": password}), end="")
'''
remote_command = "sudo -n python3 -c " + shlex.quote(remote_program)
completed = subprocess.run(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "1999wiki", remote_command],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=True,
)
credential = json.loads(completed.stdout.decode("utf-8"))
for secret_name, key in (("TCR_USERNAME", "username"), ("TCR_PASSWORD", "password")):
    subprocess.run(
        ["gh", "secret", "set", secret_name, "--repo", "DDomelette/1999Wiki"],
        input=credential[key].encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
print("updated GitHub Secrets: TCR_USERNAME, TCR_PASSWORD")
'@ | & 'D:\Anaconda32024\envs\1999wiki\python.exe' -
if ($LASTEXITCODE -ne 0) { throw 'secret bridge failed' }
```

Expected: only the two Secret names are reported; neither value appears in output, command arguments, or files.

- [ ] **Step 4: Verify repository variable names and Secret update metadata**

```powershell
gh api repos/DDomelette/1999Wiki/actions/variables `
  --jq '.variables[] | [.name,.value] | @tsv'
gh api repos/DDomelette/1999Wiki/actions/secrets `
  --jq '.secrets[] | [.name,.updated_at] | @tsv'
```

Expected: `TCR_REGISTRY=ccr.ccs.tencentyun.com`, `TCR_NAMESPACE=1999wiki_code`, and both required Secret names have current update timestamps. Values remain unreadable.

- [ ] **Step 5: Push only the release branch and verify its exact remote object**

```powershell
$ReleaseWorktree = 'D:\1999Wiki.worktrees\release-ab'
$Expected = 'daf3fe85390c534e0177c2eb06768b7f9ffc3a44'
git -C $ReleaseWorktree push --set-upstream origin codex/release-ab
if ($LASTEXITCODE -ne 0) { throw 'release branch push failed' }

$remote = git -C $ReleaseWorktree ls-remote origin refs/heads/codex/release-ab
$remoteSha = ($remote -split '\s+')[0]
if ($remoteSha -ne $Expected) { throw 'remote release branch is not the reviewed commit' }
```

Expected: only `codex/release-ab` is pushed and resolves to the full release commit.

**Review gate:** Re-read `git status`, local HEAD, and remote SHA before dispatching any workflow.

---

### Task 4: Publish immutable images and verify the exact run artifact

**Files:**

- External create: one GitHub Actions workflow run for `publish-images.yml`.
- Create ignored: `.local/release-ab/run-$RunId/release-manifest.json`.
- Create ignored: `.local/release-ab/dispatch-boundary.json`.
- Create ignored: `.local/release-ab/selected-run.json`.
- Create ignored: `.local/release-ab/publication-receipt.json`.
- Read: `deploy/bin/release_manifest.py`.

**Interfaces:**

- Consumes: remote branch and GitHub Secrets from Task 3.
- Produces: numeric run ID, successful run metadata, and a verified canonical manifest bound to the release commit.

- [ ] **Step 1: Revalidate dispatch inputs and record the dispatch boundary**

```powershell
$Repo = 'DDomelette/1999Wiki'
$ReleaseBranch = 'codex/release-ab'
$ReleaseCommit = 'daf3fe85390c534e0177c2eb06768b7f9ffc3a44'
$remote = git -C 'D:\1999Wiki.worktrees\release-ab' ls-remote origin "refs/heads/$ReleaseBranch"
if (($remote -split '\s+')[0] -ne $ReleaseCommit) { throw 'remote ref drifted' }
$DispatchNotBefore = (Get-Date).ToUniversalTime()
$EvidenceRoot = 'D:\1999Wiki\.local\release-ab'
if (Test-Path -LiteralPath $EvidenceRoot) {
    throw 'release evidence root already exists; do not overwrite a prior attempt'
}
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$boundary = [ordered]@{
    schema_version = '1999wiki.ab-dispatch-boundary/v1'
    repository = $Repo
    branch = $ReleaseBranch
    commit = $ReleaseCommit
    dispatch_not_before_utc = $DispatchNotBefore.ToString('o')
}
$boundary | ConvertTo-Json | Set-Content -LiteralPath "$EvidenceRoot\dispatch-boundary.json" -Encoding UTF8
```

Expected: remote ref matches and `$DispatchNotBefore` is set immediately before dispatch.

- [ ] **Step 2: Dispatch exactly one workflow run**

```powershell
gh workflow run publish-images.yml `
  --repo DDomelette/1999Wiki `
  --ref codex/release-ab
if ($LASTEXITCODE -ne 0) { throw 'workflow dispatch failed' }
```

Expected: GitHub accepts the dispatch. Do not dispatch a second run if discovery is slow.

- [ ] **Step 3: Discover one uniquely matching numeric run ID by condition**

```powershell
$Boundary = Get-Content -Raw -LiteralPath 'D:\1999Wiki\.local\release-ab\dispatch-boundary.json' | ConvertFrom-Json
$Repo = [string]$Boundary.repository
$ReleaseBranch = [string]$Boundary.branch
$ReleaseCommit = [string]$Boundary.commit
$DispatchNotBefore = ([DateTime]$Boundary.dispatch_not_before_utc).ToUniversalTime()
$deadline = (Get-Date).AddMinutes(3)
$Run = $null
do {
    $runs = @(
        gh run list `
          --repo $Repo `
          --workflow publish-images.yml `
          --branch $ReleaseBranch `
          --event workflow_dispatch `
          --limit 20 `
          --json databaseId,headSha,headBranch,createdAt,status,conclusion,url |
        ConvertFrom-Json |
        Where-Object {
            $_.headSha -eq $ReleaseCommit -and
            $_.headBranch -eq $ReleaseBranch -and
            ([DateTime]$_.createdAt).ToUniversalTime() -ge $DispatchNotBefore.AddSeconds(-5)
        }
    )
    if ($runs.Count -gt 1) { throw 'multiple matching runs; stop for explicit selection' }
    if ($runs.Count -eq 1) { $Run = $runs[0]; break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if ($null -eq $Run) { throw 'matching workflow run did not appear' }
if ([string]$Run.databaseId -notmatch '^[1-9][0-9]*$') { throw 'run ID is not numeric' }
$RunId = [string]$Run.databaseId
$selection = [ordered]@{
    schema_version = '1999wiki.ab-selected-run/v1'
    repository = $Repo
    branch = $ReleaseBranch
    commit = $ReleaseCommit
    run_id = $RunId
    created_at = [string]$Run.createdAt
    url = [string]$Run.url
}
$selection | ConvertTo-Json | Set-Content -LiteralPath 'D:\1999Wiki\.local\release-ab\selected-run.json' -Encoding UTF8
$Run | ConvertTo-Json -Depth 4
```

Expected: exactly one matching run and one numeric `$RunId`.

- [ ] **Step 4: Wait for that exact run with periodic user-visible progress**

```powershell
$Selection = Get-Content -Raw -LiteralPath 'D:\1999Wiki\.local\release-ab\selected-run.json' | ConvertFrom-Json
$Repo = [string]$Selection.repository
$RunId = [string]$Selection.run_id
gh run watch $RunId --repo $Repo --exit-status
if ($LASTEXITCODE -ne 0) {
    gh run view $RunId --repo $Repo --log-failed
    throw 'publication workflow failed; do not redeploy or blindly retry'
}
```

Expected: run completes successfully. While waiting, report progress at least once per minute; do not launch another run.

- [ ] **Step 5: Re-bind completed run metadata**

```powershell
$Selection = Get-Content -Raw -LiteralPath 'D:\1999Wiki\.local\release-ab\selected-run.json' | ConvertFrom-Json
$Repo = [string]$Selection.repository
$RunId = [string]$Selection.run_id
$ReleaseCommit = [string]$Selection.commit
$ReleaseBranch = [string]$Selection.branch
$Completed = gh run view $RunId --repo $Repo `
  --json databaseId,workflowName,headSha,headBranch,status,conclusion,url |
  ConvertFrom-Json
if ([string]$Completed.databaseId -ne $RunId) { throw 'run ID changed' }
if ($Completed.workflowName -ne 'Publish immutable application images') { throw 'wrong workflow' }
if ($Completed.headSha -ne $ReleaseCommit) { throw 'wrong workflow commit' }
if ($Completed.headBranch -ne $ReleaseBranch) { throw 'wrong workflow branch' }
if ($Completed.status -ne 'completed' -or $Completed.conclusion -ne 'success') {
    throw 'workflow did not complete successfully'
}
$Completed | ConvertTo-Json -Depth 4
```

Expected: every identity matches the dispatch.

- [ ] **Step 6: Download only the exact release artifact**

```powershell
$Selection = Get-Content -Raw -LiteralPath 'D:\1999Wiki\.local\release-ab\selected-run.json' | ConvertFrom-Json
$Repo = [string]$Selection.repository
$RunId = [string]$Selection.run_id
$ReleaseInput = "D:\1999Wiki\.local\release-ab\run-$RunId"
if (Test-Path -LiteralPath $ReleaseInput) {
    throw 'release input directory already exists; do not overwrite evidence'
}
New-Item -ItemType Directory -Path $ReleaseInput | Out-Null
gh run download $RunId `
  --repo $Repo `
  --name release-sha-daf3fe8 `
  --dir $ReleaseInput
if ($LASTEXITCODE -ne 0) { throw 'release artifact download failed' }
$Manifest = Join-Path $ReleaseInput 'release-manifest.json'
if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) { throw 'manifest is missing' }
if (@(Get-ChildItem -LiteralPath $ReleaseInput -Recurse -File).Count -ne 1) {
    throw 'release artifact contains files other than the canonical manifest'
}
```

Expected: exactly one `release-manifest.json` exists under the create-new run directory.

- [ ] **Step 7: Verify manifest schema, commit, registry state, and hash**

```powershell
$Selection = Get-Content -Raw -LiteralPath 'D:\1999Wiki\.local\release-ab\selected-run.json' | ConvertFrom-Json
$RunId = [string]$Selection.run_id
$ReleaseCommit = [string]$Selection.commit
$Manifest = "D:\1999Wiki\.local\release-ab\run-$RunId\release-manifest.json"
$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$Verifier = 'D:\1999Wiki.worktrees\release-ab\deploy\bin\release_manifest.py'
& $Python $Verifier verify `
  --manifest $Manifest `
  --commit $ReleaseCommit `
  --registry tcr
if ($LASTEXITCODE -ne 0) { throw 'canonical TCR manifest verification failed' }

$ManifestHash = (Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash.ToLowerInvariant()
$payload = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json
if ($payload.schema_version -ne '1999wiki.release/v2') { throw 'wrong manifest schema' }
if ($payload.release_tag -ne 'sha-daf3fe8') { throw 'wrong release tag' }
if ($payload.release_state -notin @('ready','ready_with_deferred_ghcr')) {
    throw 'release state is not deployable'
}
"manifest_sha256=$ManifestHash"
"release_state=$($payload.release_state)"

$publication = [ordered]@{
    schema_version = '1999wiki.ab-publication-receipt/v1'
    repository = [string]$Selection.repository
    branch = [string]$Selection.branch
    commit = $ReleaseCommit
    run_id = $RunId
    run_url = [string]$Selection.url
    manifest_path = $Manifest
    manifest_sha256 = $ManifestHash
    release_state = [string]$payload.release_state
    backend_tcr_ref = [string]$payload.images.backend.registries.tcr.ref
    frontend_tcr_ref = [string]$payload.images.frontend.registries.tcr.ref
    backend_ghcr_status = [string]$payload.images.backend.registries.ghcr.status
    frontend_ghcr_status = [string]$payload.images.frontend.registries.ghcr.status
}
$publication | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath 'D:\1999Wiki\.local\release-ab\publication-receipt.json' -Encoding UTF8
```

Expected: verifier emits the full commit and two digest-qualified TCR refs; state is one of the two allowed values.

**Review gate:** If publication failed after any registry mutation, retain the exact failure artifact and stop. Do not reuse or overwrite `sha-daf3fe8`.

---

### Task 5: Prepare production metadata and safely free the blue slot

**Files:**

- Read: `/srv/1999wiki/runtime-bundle/deploy/**`
- Read: `/srv/1999wiki/deploy-state/active.env`
- Read: `/srv/1999wiki/rag-artifacts/active_build.v1.json`
- Read: `/srv/1999wiki/rag-artifacts/crawler-v3-20260721t051246z/indexes/child_text_bm25.json`
- Create: `/srv/1999wiki/releases/sha-daf3fe8/release-manifest.json`
- Create: `/srv/1999wiki/releases/sha-daf3fe8/release.identity`
- Create: `/srv/1999wiki/releases/sha-daf3fe8/blue.env`
- Update transactionally: `/srv/1999wiki/deploy-state/active.env`

**Interfaces:**

- Consumes: verified local manifest and hash from Task 4.
- Produces: a verified release directory, reusable empty blue slot, and pre-deployment BM25/Milvus/active-state evidence.

- [ ] **Step 1: Prove the server runtime bundle exactly matches the release deploy tree**

```powershell
$LocalRoot = (Resolve-Path 'D:\1999Wiki.worktrees\release-ab').Path.TrimEnd('\')
$local = @{}
Get-ChildItem -LiteralPath "$LocalRoot\deploy" -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($LocalRoot.Length + 1).Replace('\','/')
    $local[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}

$remoteLines = @(ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki `
  "sudo -n bash -c 'cd /srv/1999wiki/runtime-bundle && find deploy -type f -print0 | sort -z | xargs -0 sha256sum'")
if ($LASTEXITCODE -ne 0) { throw 'remote runtime-bundle hashing failed' }
$remote = @{}
foreach ($line in $remoteLines) {
    if ($line -notmatch '^([0-9a-f]{64})  (deploy/.+)$') { throw "invalid remote hash row: $line" }
    $remote[$Matches[2]] = $Matches[1]
}
if ($local.Count -ne $remote.Count) { throw 'runtime-bundle file count differs' }
foreach ($path in $local.Keys) {
    if (-not $remote.ContainsKey($path) -or $remote[$path] -ne $local[$path]) {
        throw "runtime-bundle mismatch: $path"
    }
}
"runtime_bundle_file_count=$($local.Count)"
```

Expected: all 22 tracked deploy files match. If not, stop; do not overwrite the server bundle under this plan.

- [ ] **Step 2: Capture and validate immutable pre-deployment identities**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "sudo -n python3 - <<'PY'
import hashlib, json
from pathlib import Path

active = Path('/srv/1999wiki/rag-artifacts/active_build.v1.json')
bm25 = Path('/srv/1999wiki/rag-artifacts/crawler-v3-20260721t051246z/indexes/child_text_bm25.json')
active_raw = active.read_bytes()
bm25_raw = bm25.read_bytes()
active_data = json.loads(active_raw)
bm25_data = json.loads(bm25_raw)
assert active_data['milvus_collection_name'] == 'text_child_bge_m3_shadow_crawler_v3_20260721t051246z'
assert bm25_data['schema_version'] == 'huiji.bm25-index/v2'
assert hashlib.sha256(bm25_raw).hexdigest() == '70519e409f7b962cd52bd532bfa0a65fdc22b27ea545157e42ad13f3bf96f20a'
print('active_build_sha256=' + hashlib.sha256(active_raw).hexdigest())
print('bm25_sha256=' + hashlib.sha256(bm25_raw).hexdigest())
print('bm25_schema=' + bm25_data['schema_version'])
print('milvus_collection=' + active_data['milvus_collection_name'])
PY"
if ($LASTEXITCODE -ne 0) { throw 'pre-deployment artifact identity failed' }
```

Expected: active build SHA `87c083...`, BM25 SHA `70519e...`, v2 schema, and exact Milvus collection are emitted.

- [ ] **Step 3: Validate the exact old blue retirement target**

```powershell
$RemoteScript = @'
set -eu
sudo -n grep -Fx 'ACTIVE_SLOT=green' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'ACTIVE_RELEASE=sha-1ec7752' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'PREVIOUS_AVAILABLE=1' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'PREVIOUS_SLOT=blue' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'PREVIOUS_RELEASE=sha-0761382' /srv/1999wiki/deploy-state/active.env
test -z "$(docker ps --filter name=1999wiki-blue --format '{{.ID}}')"
test "$(docker ps -a --filter name=1999wiki-blue --format '{{.ID}}' | wc -l)" -eq 2
curl --fail --show-error --silent http://127.0.0.1/health/ready >/dev/null
'@
($RemoteScript -replace "`r`n", "`n") | ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "bash -s"
if ($LASTEXITCODE -ne 0) { throw 'old blue retirement preconditions changed' }
```

Expected: green is active/ready, blue `sha-0761382` is the exact stopped previous target, and exactly two stopped blue application containers exist.

- [ ] **Step 4: Execute only the authorized old-blue retirement**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki `
  "cd /srv/1999wiki/runtime-bundle && sudo -n bash deploy/bin/cleanup.sh sha-0761382 blue remove-blue-sha-0761382"
if ($LASTEXITCODE -ne 0) { throw 'old blue retirement failed; stop for reconciliation' }
```

Expected: `retired previous blue deployment at sha-0761382`.

- [ ] **Step 5: Verify cleanup changed only the permitted rollback occupancy**

```powershell
$RemoteScript = @'
set -eu
sudo -n grep -Fx 'ACTIVE_SLOT=green' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'ACTIVE_RELEASE=sha-1ec7752' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'PREVIOUS_AVAILABLE=0' /srv/1999wiki/deploy-state/active.env
test -z "$(docker ps -a --filter name=1999wiki-blue --format '{{.ID}}')"
docker inspect 1999wiki-green-backend-1 --format '{{.State.Health.Status}} {{.RestartCount}}'
docker inspect 1999wiki-green-frontend-1 --format '{{.State.Health.Status}} {{.RestartCount}}'
curl --fail --show-error --silent http://127.0.0.1/health/ready >/dev/null
sudo -n test -f /srv/1999wiki/releases/sha-0761382/release-manifest.json
sudo -n test -f /srv/1999wiki/deploy-state/snapshots/sha-0761382/blue/release.env
'@
($RemoteScript -replace "`r`n", "`n") | ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "bash -s"
if ($LASTEXITCODE -ne 0) { throw 'post-retirement state is not safe' }
```

Expected: green remains healthy with restart count zero; old release metadata and snapshot remain; blue containers are absent.

- [ ] **Step 6: Refuse a pre-existing target release directory, then transfer the manifest**

```powershell
$Publication = Get-Content -Raw -LiteralPath 'D:\1999Wiki\.local\release-ab\publication-receipt.json' | ConvertFrom-Json
$Manifest = [string]$Publication.manifest_path
$ManifestHash = [string]$Publication.manifest_sha256
if ((Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ManifestHash) {
    throw 'local manifest drifted after publication verification'
}
$RemoteStage = '/home/ubuntu/release-manifest-sha-daf3fe8.json'
ssh 1999wiki "sudo -n test ! -e /srv/1999wiki/releases/sha-daf3fe8 && test ! -e $RemoteStage"
if ($LASTEXITCODE -ne 0) { throw 'target release path already exists; do not overwrite it' }

scp $Manifest "1999wiki`:$RemoteStage"
if ($LASTEXITCODE -ne 0) { throw 'manifest transfer failed' }

ssh 1999wiki "set -eu
sudo -n install -d -m 0700 /srv/1999wiki/releases/sha-daf3fe8
sudo -n install -m 0600 $RemoteStage /srv/1999wiki/releases/sha-daf3fe8/release-manifest.json
rm -f $RemoteStage
sudo -n sha256sum /srv/1999wiki/releases/sha-daf3fe8/release-manifest.json
"
if ($LASTEXITCODE -ne 0) { throw 'server manifest install failed' }
```

Expected: server SHA-256 equals `$ManifestHash` from Task 4.

- [ ] **Step 7: Generate canonical server identity and blue release environment**

```powershell
$RemoteScript = @'
set -eu
cd /srv/1999wiki/runtime-bundle
sudo -n python3 deploy/bin/release_manifest.py verify \
  --manifest /srv/1999wiki/releases/sha-daf3fe8/release-manifest.json \
  --commit daf3fe85390c534e0177c2eb06768b7f9ffc3a44 \
  --registry tcr | sudo -n tee /srv/1999wiki/releases/sha-daf3fe8/release.identity >/dev/null
sudo -n chmod 0600 /srv/1999wiki/releases/sha-daf3fe8/release.identity
sudo -n bash -c 'cat /srv/1999wiki/releases/sha-daf3fe8/release.identity > /srv/1999wiki/releases/sha-daf3fe8/blue.env; printf "BACKEND_PORT=18100\nFRONTEND_PORT=18180\n" >> /srv/1999wiki/releases/sha-daf3fe8/blue.env'
sudo -n chmod 0600 /srv/1999wiki/releases/sha-daf3fe8/blue.env
sudo -n python3 deploy/bin/ops_helper.py validate-env release \
  /srv/1999wiki/releases/sha-daf3fe8/blue.env \
  --release sha-daf3fe8
'@
($RemoteScript -replace "`r`n", "`n") | ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "bash -s"
if ($LASTEXITCODE -ne 0) { throw 'server release metadata validation failed' }
```

Expected: canonical verification and release-env validation both exit zero.

**Review gate:** Stop before deployment unless green is still active, blue is empty, previous is cleared, and all three new release files validate.

---

### Task 6: Deploy, test the real inactive slot, and atomically switch

**Files:**

- Execute: `/srv/1999wiki/runtime-bundle/deploy/bin/deploy.sh`
- Execute internally: `preflight.sh`, `smoke-test.sh`, `switch.sh`
- Create transactionally: `/srv/1999wiki/deploy-state/snapshots/sha-daf3fe8/blue/{release.env,app.env}`
- Update transactionally: `/srv/1999wiki/deploy-state/active.env` and Caddy active fragment.

**Interfaces:**

- Consumes: empty blue slot and verified blue release environment from Task 5.
- Produces: blue containers tested on loopback against real production dependencies, then an atomic public switch with green recorded as rollback.

- [ ] **Step 1: Run the standalone preflight before any application container starts**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "set -eu
cd /srv/1999wiki/runtime-bundle
sudo -n env PUBLIC_BASE_URL=http://127.0.0.1 \
  bash deploy/bin/preflight.sh sha-daf3fe8 blue
"
if ($LASTEXITCODE -ne 0) { throw 'production preflight failed' }
```

Expected: `preflight passed for sha-daf3fe8 in blue`. This checks RAG closure, protected files, at least 8 GiB free, healthy shared infrastructure, image/env shape, Caddy syntax, empty blue, and non-active/non-previous slot state.

- [ ] **Step 2: Execute the checked-in deployment transaction**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "set -eu
cd /srv/1999wiki/runtime-bundle
sudo -n env \
  SMOKE_RAG_QUESTION='比较十四行诗和槲寄生' \
  PUBLIC_BASE_URL='http://127.0.0.1' \
  bash deploy/bin/deploy.sh sha-daf3fe8 blue
"
if ($LASTEXITCODE -ne 0) {
    $activeRelease = ssh 1999wiki "sudo -n grep '^ACTIVE_RELEASE=' /srv/1999wiki/deploy-state/active.env"
    if ($activeRelease -eq 'ACTIVE_RELEASE=sha-daf3fe8') {
        ssh 1999wiki "cd /srv/1999wiki/runtime-bundle && sudo -n env SMOKE_RAG_QUESTION='请介绍槲寄生' PUBLIC_BASE_URL='http://127.0.0.1' bash deploy/bin/rollback.sh"
        if ($LASTEXITCODE -ne 0) { throw 'deploy failed after switch and rollback also failed' }
    }
    throw 'deploy transaction failed; release is not accepted online'
}
```

Expected transaction order:

1. snapshot protected release/app configuration;
2. repeat preflight under the operations lock;
3. pull both digest-qualified images;
4. start blue only on loopback ports;
5. verify exact Compose image identities and readiness;
6. test React shell/asset, readiness, Wiki list/detail, synchronous RAG, SSE terminal event, and media through blue with real dependencies;
7. repeat candidate identity/smoke under the switch lock;
8. atomically reload Caddy, commit active state, verify public health, and stop green.

- [ ] **Step 3: Verify the authoritative state immediately after the script returns**

```powershell
$RemoteScript = @'
set -eu
sudo -n grep -Fx 'ACTIVE_SLOT=blue' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'ACTIVE_RELEASE=sha-daf3fe8' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'PREVIOUS_AVAILABLE=1' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'PREVIOUS_SLOT=green' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'PREVIOUS_RELEASE=sha-1ec7752' /srv/1999wiki/deploy-state/active.env
docker inspect 1999wiki-blue-backend-1 --format '{{.State.Health.Status}} {{.RestartCount}} {{.Config.Image}}'
docker inspect 1999wiki-blue-frontend-1 --format '{{.State.Health.Status}} {{.RestartCount}} {{.Config.Image}}'
test -z "$(docker ps --filter name=1999wiki-green --format '{{.ID}}')"
'@
($RemoteScript -replace "`r`n", "`n") | ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "bash -s"
if ($LASTEXITCODE -ne 0) { throw 'post-switch state identity failed; invoke rollback task' }
```

Expected: blue active and healthy with restart count zero; green stopped and recorded as previous rollback.

If this identity check fails while `ACTIVE_RELEASE=sha-daf3fe8`, immediately run the exact rollback command in Task 7 Step 5 before returning control.

**Review gate:** Do not call cleanup. Green `sha-1ec7752` must remain the recorded rollback target.

---

### Task 7: Run public A/B regression, observe, and roll back on failure

**Files:**

- Read: public `/health/ready`, `/api/wiki/health`, `/api/ask`, `/api/ask/stream`, and returned `/media/` route.
- Read: Docker container health/restart counts and recent Caddy/application logs.
- Execute on failure only: `/srv/1999wiki/runtime-bundle/deploy/bin/rollback.sh`.

**Interfaces:**

- Consumes: switched blue deployment from Task 6.
- Produces: post-activation proof for Thread A, compatibility proof for Thread B on BM25 v2, a 10-minute stability record, or a verified rollback to green.

- [ ] **Step 1: Repeat the canonical public smoke suite**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "set -eu
cd /srv/1999wiki/runtime-bundle
sudo -n env \
  SMOKE_RAG_QUESTION='请介绍槲寄生' \
  bash deploy/bin/smoke-test.sh \
    http://127.0.0.1:18180 \
    http://127.0.0.1 \
    /srv/1999wiki/protected/app.env
"
if ($LASTEXITCODE -ne 0) { throw 'canonical post-switch smoke failed' }
```

Expected: `smoke tests passed` through the active public route and direct blue port.

- [ ] **Step 2: Verify Thread A composite routing and citations through the public API**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "python3 - <<'PY'
import json
import urllib.request

question = '比较十四行诗和槲寄生'
request = urllib.request.Request(
    'http://127.0.0.1/api/ask',
    data=json.dumps({'question': question}, ensure_ascii=False).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(request, timeout=90) as response:
    assert response.status == 200
    payload = json.load(response)
route = payload.get('route') or {}
subtasks = payload.get('subtasks') or []
sources = payload.get('sources') or []
assert route.get('effective_route') == 'composite', route
assert route.get('retrieval_outcome') in {'sufficient', 'partial'}, route
assert len(subtasks) >= 2, subtasks
assert all(item.get('status') in {'succeeded', 'empty'} for item in subtasks), subtasks
assert isinstance(payload.get('answer'), str) and payload['answer'].strip()
assert sources, 'composite answer has no sources'
assert any(item.get('citation_ids') for item in subtasks), subtasks
print(json.dumps({
    'effective_route': route.get('effective_route'),
    'retrieval_outcome': route.get('retrieval_outcome'),
    'subtask_count': len(subtasks),
    'source_count': len(sources),
}, ensure_ascii=False, sort_keys=True))
PY"
if ($LASTEXITCODE -ne 0) { throw 'Thread A composite production check failed' }
```

Expected: route `composite`, at least two subtasks, non-empty answer/sources, and subtask citation IDs.

- [ ] **Step 3: Re-prove Thread B is running against unchanged BM25 v2 and unchanged Milvus**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "sudo -n python3 - <<'PY'
import hashlib, json
from pathlib import Path

active = Path('/srv/1999wiki/rag-artifacts/active_build.v1.json')
bm25 = Path('/srv/1999wiki/rag-artifacts/crawler-v3-20260721t051246z/indexes/child_text_bm25.json')
active_raw = active.read_bytes()
bm25_raw = bm25.read_bytes()
active_data = json.loads(active_raw)
bm25_data = json.loads(bm25_raw)
assert hashlib.sha256(active_raw).hexdigest() == '87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e'
assert hashlib.sha256(bm25_raw).hexdigest() == '70519e409f7b962cd52bd532bfa0a65fdc22b27ea545157e42ad13f3bf96f20a'
assert bm25_data['schema_version'] == 'huiji.bm25-index/v2'
assert active_data['milvus_collection_name'] == 'text_child_bge_m3_shadow_crawler_v3_20260721t051246z'
print('BM25 v2 and Milvus identities unchanged')
PY"
if ($LASTEXITCODE -ne 0) { throw 'BM25/Milvus identity changed' }
```

Expected: exact pre/post hashes and collection identity match.

- [ ] **Step 4: Observe health, restarts, errors, and capacity for 10 minutes**

Run the following as a yielded long-running command so progress can be reported at least once per minute:

```powershell
$RemoteScript = @'
set -eu
for iteration in $(seq 1 20); do
  printf 'observation=%s timestamp=%s\n' "$iteration" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  curl --fail --show-error --silent http://127.0.0.1/health/ready >/dev/null
  docker inspect 1999wiki-blue-backend-1 1999wiki-blue-frontend-1 \
    --format '{{.Name}} {{.State.Health.Status}} {{.RestartCount}}'
  df -B1 --output=avail /srv/1999wiki | tail -1
  free -m | awk 'NR==2 {print "memory_used_mb=" $3 " memory_available_mb=" $7}'
  sleep 30
done
sudo -n journalctl -u caddy --since '-12 minutes' --no-pager
docker logs --since 12m 1999wiki-blue-backend-1 2>&1 | tail -200
docker logs --since 12m 1999wiki-blue-frontend-1 2>&1 | tail -200
'@
($RemoteScript -replace "`r`n", "`n") | ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "bash -s"
if ($LASTEXITCODE -ne 0) { throw 'stability observation failed' }
```

Expected: twenty successful readiness samples, both containers healthy with restart count zero, no disk drop below the 8 GiB preflight floor, and no critical traceback or repeated 5xx evidence in the reviewed logs.

- [ ] **Step 5: Apply the failure branch exactly when any Task 6/7 gate fails**

Do not run this on success. On the first critical failure after the active-state switch:

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "set -eu
cd /srv/1999wiki/runtime-bundle
sudo -n env \
  SMOKE_RAG_QUESTION='请介绍槲寄生' \
  PUBLIC_BASE_URL='http://127.0.0.1' \
  bash deploy/bin/rollback.sh
sudo -n grep -Fx 'ACTIVE_SLOT=green' /srv/1999wiki/deploy-state/active.env
sudo -n grep -Fx 'ACTIVE_RELEASE=sha-1ec7752' /srv/1999wiki/deploy-state/active.env
curl --fail --show-error --silent http://127.0.0.1/health/ready >/dev/null
"
if ($LASTEXITCODE -ne 0) { throw 'rollback did not restore verified green service' }
```

Expected on failure path: green `sha-1ec7752` is active and ready again. Report A/B as not online.

**Review gate:** Success requires all public checks and the full observation window. No cleanup follows.

---

### Task 8: Record evidence and close the release

**Files:**

- Create: `D:\1999Wiki\docs\superpowers\reports\2026-08-04-ab-production-release.md`
- Read: verified local manifest and all Task 1–7 command results.
- Do not stage: the four unrelated user document changes.

**Interfaces:**

- Consumes: exact release identities and verification output from every prior task.
- Produces: a committed report and a final user-facing status that distinguishes publication, inactive-slot testing, switch, live verification, and rollback readiness.

- [ ] **Step 1: Capture final authoritative state without changing it**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 1999wiki "set -eu
sudo -n cat /srv/1999wiki/deploy-state/active.env
sudo -n sha256sum \
  /srv/1999wiki/releases/sha-daf3fe8/release-manifest.json \
  /srv/1999wiki/rag-artifacts/active_build.v1.json \
  /srv/1999wiki/rag-artifacts/crawler-v3-20260721t051246z/indexes/child_text_bm25.json
docker inspect 1999wiki-blue-backend-1 1999wiki-blue-frontend-1 \
  --format '{{.Name}} {{.State.Health.Status}} {{.RestartCount}} {{.Config.Image}}'
sudo -n test -f /srv/1999wiki/deploy-state/snapshots/sha-1ec7752/green/release.env
"
if ($LASTEXITCODE -ne 0) { throw 'final authoritative state capture failed' }
```

Expected on success path: active blue `sha-daf3fe8`, previous green `sha-1ec7752`, exact unchanged RAG hashes, healthy zero-restart blue containers.

- [ ] **Step 2: Create the report with actual values, never placeholders**

Use `apply_patch` to create `docs/superpowers/reports/2026-08-04-ab-production-release.md`. Include the actual values collected above under these exact headings:

```markdown
# A/B Production Release Report

## Outcome
## Source and local verification
## GitHub publication
## Release manifest
## Old blue retirement
## Inactive-slot deployment tests
## Traffic switch and public regression
## BM25 and Milvus identity preservation
## Stability observation
## Rollback readiness
## Unrelated workspace preservation
```

The Outcome must say either `online` or `rolled back/not online`; it must not claim success if any gate was skipped. Include the full commit, run ID/URL, manifest SHA-256/state/image refs, pre/post artifact hashes, active/previous slots, test outcomes, restart counts, and whether rollback was invoked.

- [ ] **Step 3: Self-review the report and workspace scope**

```powershell
$Report = 'docs/superpowers/reports/2026-08-04-ab-production-release.md'
if (-not (Test-Path -LiteralPath $Report -PathType Leaf)) { throw 'release report missing' }
$patterns = @('T' + 'BD', 'T' + 'ODO', 'PLACE' + 'HOLDER', 'FIX' + 'ME', 'numeric-run-id', 'digest-goes-here')
$redFlags = rg -n ($patterns -join '|') $Report
if ($LASTEXITCODE -eq 0) { $redFlags; throw 'release report contains placeholders' }
git diff --check -- $Report
if ($LASTEXITCODE -ne 0) { throw 'release report whitespace check failed' }
git status --short
```

Expected: report has no placeholders; the only new release change is the report, alongside the same four unrelated user files.

- [ ] **Step 4: Commit only the release report**

```powershell
git add -- 'docs/superpowers/reports/2026-08-04-ab-production-release.md'
git diff --cached --name-status
git diff --cached --check
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 1 -or $staged[0] -ne 'docs/superpowers/reports/2026-08-04-ab-production-release.md') {
    throw 'staged scope contains files other than the release report'
}
git commit -m 'docs: record A/B production release'
```

Expected: exactly one report file is committed; user document changes remain unstaged.

- [ ] **Step 5: Deliver the final status with immutable evidence**

On success, report:

- production active release `sha-daf3fe8` at the full A/B commit;
- GitHub run ID and URL;
- manifest SHA-256 and both digest-qualified image refs;
- local, inactive-slot, and public test results;
- unchanged BM25 v2 SHA/schema and Milvus collection;
- 10-minute health/restart result;
- green `sha-1ec7752` retained as rollback target.

On failure, lead with the failed gate and whether green was never switched or was restored by rollback. Never say A/B is online unless Task 7 completed successfully.

---

## Completion checklist

- [ ] Release worktree remains at `daf3fe85390c534e0177c2eb06768b7f9ffc3a44` with no source commit.
- [ ] Local Python/frontend/Docker gates pass.
- [ ] TCR Secrets are repaired without plaintext exposure.
- [ ] Remote branch is exactly the reviewed full commit.
- [ ] One exact GitHub run succeeds and yields a verified canonical manifest.
- [ ] Old stopped blue `sha-0761382` is retired exactly as authorized.
- [ ] Server runtime bundle matches the release deploy tree.
- [ ] Inactive blue passes real-dependency smoke before switching.
- [ ] Active blue passes public A routing/composite/citation checks.
- [ ] BM25 v2 and Milvus identities are byte-for-byte unchanged.
- [ ] Ten-minute observation passes with zero restarts.
- [ ] Green `sha-1ec7752` remains the rollback target.
- [ ] Final report is the only release evidence committed on `main`.
