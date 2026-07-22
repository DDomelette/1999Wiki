# EventName Voice Binding Recovery P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore maintainable Huiji builder sources and promote an isolated eventName-exact voice build, with strictly additive MinIO writes, optional evidence-gated Milvus shadow promotion, and crash-recoverable build/collection activation.

**Architecture:** Rebuild the missing Huiji source pipeline as focused modules that first produce immutable diagnostic evidence, then exact runtime artifacts, then optional shadow-vector experiments. Keep the current `dev` artifacts, active collection, and existing MinIO objects immutable; all mutation goes to new build directories, missing SHA-addressed objects, or never-before-existing shadow collections. Activate one complete build/collection tuple through a global coordinator, durable journal, standby dependency graphs, atomic router epoch, authenticated acknowledgements, and rollback transaction.

**Tech Stack:** Python 3.12.13 (`D:\Anaconda32024\envs\LangChain\python.exe`), dataclasses, JSON/JSONL, FastAPI/Pydantic, `minio==7.2.20`, pymilvus, existing BM25/RRF/reranker stack, pytest, PowerShell, HMAC-SHA256, OS advisory locks.

## Global Constraints

- This plan implements every P0 ID in `docs/superpowers/specs/2026-07-11-eventname-voice-binding-recovery-design.md` and no P1/P2 behavior.
- At execution start, invoke `superpowers:using-git-worktrees` and ask the user to approve the isolation choice. Prefer a native working-tree snapshot facility that preserves the reviewed EVB authority bytes. If it is unavailable, do not copy or commit unrelated dirty/untracked files: either prove that the isolated worktree contains the exact authority snapshot below, or obtain explicit user approval for in-place execution with the external authority snapshot retained.
- Git history, `HEAD`, and a clean checkout are not source authorities. The content-addressed external authority snapshot is the byte authority for pre-existing EVB-owned files; it lives outside the workspace and is never staged.
- Reopen every file immediately before editing. Preserve concurrent user changes; never reset, checkout, revert, or bulk-replace a dirty file.
- EVB does not modify, stage, or commit any `frontend/**` file. `C06F` is a read-only compatibility regression; failure blocks EVB activation and reports a Wiki/EVB contract conflict for the owning line to resolve.
- `.pyc` files are read-only forensic evidence. Production source must be authored and tested as maintainable Python; no generated or decompiled `.pyc` output may become source.
- Current `data/processed/huiji/dev/**`, the active Milvus collection, existing MinIO objects, bucket setup, bucket policy, and old/shadow collections are immutable.
- Dangerous real writes are forbidden until fake/in-memory integration gates pass. Real MinIO conditional create, Milvus shadow create/insert/load, and activation run only in the ordered real-environment gate section.
- Do not call `ensure_huiji_collection()`, `build_huiji_vectorstore()`, `_delete_existing_entities()`, `MinioAssetStorage.__init__()`, or `MinioAssetStorage.upload_file()` from EVB mutation paths.
- No role name, entity ID, media ID, skill count, voice count, language count, historical row count, or expected artifact count may be hardcoded in production or acceptance assertions.
- Backend commands use `D:\Anaconda32024\envs\LangChain\python.exe` from `D:\PycharmProjects\nlp\LangChain\1999Search`.
- Each task follows red-green-refactor discipline: add focused failing tests, run and record the specified failure, implement the smallest complete contract, rerun focused and neighboring tests, execute the listed real-data read-only acceptance, then use the cached-diff audit below to commit only that task's delta.

---

## 1. Execution Workspace, Authority Snapshot, and Commit Audit

All native commands use this fail-fast helper. `$PSNativeCommandUseErrorActionPreference` is additional protection and never replaces explicit exit-code validation.

```powershell
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
function Invoke-NativeChecked {
  param(
    [Parameter(Mandatory=$true)][string]$Label,
    [Parameter(Mandatory=$true)][scriptblock]$Command,
    [int[]]$AllowedExitCodes = @(0)
  )
  $PreviousNativePreference = $PSNativeCommandUseErrorActionPreference
  try {
    $PSNativeCommandUseErrorActionPreference = $false
    $global:LASTEXITCODE = 0
    & $Command
    $Code = $global:LASTEXITCODE
    $script:LastNativeExitCode = $Code
    if ($AllowedExitCodes -notcontains $Code) { throw "$Label failed with exit code $Code" }
  } finally {
    $PSNativeCommandUseErrorActionPreference = $PreviousNativePreference
  }
}
function Invoke-ExpectedNativeFailure {
  param([string]$Label, [scriptblock]$Command, [string]$ExpectedPattern)
  $PreviousNativePreference = $PSNativeCommandUseErrorActionPreference
  try {
    $PSNativeCommandUseErrorActionPreference = $false
    $global:LASTEXITCODE = 0
    $Output = @(& $Command 2>&1)
    $Code = $global:LASTEXITCODE
    $script:LastNativeExitCode = $Code
    if ($Code -eq 0) { throw "$Label unexpectedly passed" }
    if (($Output -join "`n") -notmatch $ExpectedPattern) { throw "$Label failed for an unexpected reason with exit code $Code" }
    $Output
  } finally {
    $PSNativeCommandUseErrorActionPreference = $PreviousNativePreference
  }
}
```

- [ ] Self-test the native helpers before authority/worktree Git probes. This proves allowed branch codes, rejected codes, RED matching, and preference restoration.

```powershell
$PowerShellExe = (Get-Process -Id $PID).Path
$InitialNativePreference = $PSNativeCommandUseErrorActionPreference
$BranchCodes = [ordered]@{ success=0; git_diff_no_index=1; candidate_inconclusive=3; candidate_failed=4; candidate_partial=5; postactivate_rolled_back=6; postactivate_recovery_unproven=7 }
foreach ($Branch in $BranchCodes.GetEnumerator()) {
  $Allowed = [int]$Branch.Value
  Invoke-NativeChecked "helper allows $($Branch.Key)=$Allowed" { & $PowerShellExe -NoProfile -Command "exit $Allowed" } @($Allowed)
  if ($script:LastNativeExitCode -ne $Allowed) { throw "helper did not expose $($Branch.Key) exit $Allowed" }
  if ($PSNativeCommandUseErrorActionPreference -ne $InitialNativePreference) { throw "native preference was not restored" }
}
$DiffLeft = Join-Path $env:TEMP "evb-helper-left-$PID.txt"
$DiffRight = Join-Path $env:TEMP "evb-helper-right-$PID.txt"
Set-Content -LiteralPath $DiffLeft -Value "left" -NoNewline
Set-Content -LiteralPath $DiffRight -Value "right" -NoNewline
try {
  Invoke-NativeChecked "real git diff --no-index code 1" { & git diff --no-index -- $DiffLeft $DiffRight } @(0,1)
  if ($script:LastNativeExitCode -ne 1) { throw "git diff --no-index branch was not exercised" }
} finally {
  Remove-Item -LiteralPath $DiffLeft,$DiffRight -Force
}
$Rejected = $false
try { Invoke-NativeChecked "helper rejects 9" { & $PowerShellExe -NoProfile -Command "exit 9" } } catch { $Rejected = $_.Exception.Message -match 'exit code 9' }
if (-not $Rejected) { throw "helper failed to reject exit 9" }
if ($PSNativeCommandUseErrorActionPreference -ne $InitialNativePreference) { throw "rejected-code branch did not restore native preference" }
Invoke-ExpectedNativeFailure "helper RED" { & $PowerShellExe -NoProfile -Command "[Console]::Error.WriteLine('named-red'); exit 1" } "named-red"
if ($PSNativeCommandUseErrorActionPreference -ne $InitialNativePreference) { throw "RED helper did not restore native preference" }
```

- [ ] **Authority first.** While still in the original workspace, set `$OriginalWorkspace` and create/validate the external content-addressed authority snapshot. Do not invoke `superpowers:using-git-worktrees` before this block succeeds.

```powershell
$OriginalWorkspace = (Resolve-Path ".").Path
$AuthorityBase = Join-Path $env:LOCALAPPDATA "EVB-authority\1999Search"
$SnapshotNonce = [Guid]::NewGuid().ToString("N")
$SnapshotRoot = Join-Path $AuthorityBase ((Get-Date -Format "yyyyMMddTHHmmss") + "-" + $SnapshotNonce)
if (Test-Path -LiteralPath $SnapshotRoot) { throw "authority snapshot collision: $SnapshotRoot" }
New-Item -ItemType Directory -Path $SnapshotRoot | Out-Null
$AuthorityFiles = @(
  "src/huiji_rag/__init__.py", "src/huiji_rag/io.py", "src/huiji_rag/media.py", "src/huiji_rag/text.py",
  "src/assets/huiji_registry.py", "src/assets/voice_pagination.py", "src/assets/minio_store.py",
  "src/rag/vectorstore.py", "src/rag/sparse.py", "backend/main.py", "backend/schemas.py",
  "scripts/diagnose_huiji_artifacts.py", "scripts/verify_multi_intent_voice.py", "scripts/evaluate_huiji_rag.py",
  "config/config.py", "config/settings.yaml", "requirements.txt",
  "tests/test_huiji_models.py", "tests/test_sparse_bm25.py", "tests/test_minio_shared_upload.py",
  "tests/test_huiji_media_registry.py", "tests/test_voice_pagination.py", "tests/test_sse.py",
  "tests/test_vectorstore.py", "tests/test_huiji_eval.py", "tests/test_multi_intent_voice_eval.py"
)
if (($AuthorityFiles | Sort-Object -Unique).Count -ne $AuthorityFiles.Count) { throw "duplicate authority path" }
$Entries = foreach ($Relative in $AuthorityFiles) {
  $Source = (Resolve-Path -LiteralPath (Join-Path $OriginalWorkspace $Relative)).Path
  if (-not $Source.StartsWith($OriginalWorkspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "source root escape: $Relative" }
  $Destination = Join-Path $SnapshotRoot $Relative
  if (Test-Path -LiteralPath $Destination) { throw "snapshot file collision: $Relative" }
  New-Item -ItemType Directory -Path (Split-Path $Destination -Parent) -Force | Out-Null
  Copy-Item -LiteralPath $Source -Destination $Destination
  $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
  $CopyHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($SourceHash -ne $CopyHash) { throw "snapshot hash mismatch: $Relative" }
  [ordered]@{ relative_path = $Relative.Replace("\", "/"); sha256 = $SourceHash; size = (Get-Item -LiteralPath $Source).Length }
}
$ManifestBody = [ordered]@{ schema_version = "evb.workspace-authority/v1"; original_workspace = $OriginalWorkspace; entries = @($Entries | Sort-Object relative_path) }
$ManifestJson = $ManifestBody | ConvertTo-Json -Depth 8 -Compress
$ManifestPath = Join-Path $SnapshotRoot "authority_manifest.v1.json"
[IO.File]::WriteAllText($ManifestPath, $ManifestJson, [Text.UTF8Encoding]::new($false))
$ManifestSha256 = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
$ContentAddressedRoot = Join-Path $AuthorityBase $ManifestSha256
if (-not ([IO.Path]::GetFullPath($ContentAddressedRoot)).StartsWith([IO.Path]::GetFullPath($AuthorityBase) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "authority target root escape" }
if (Test-Path -LiteralPath $ContentAddressedRoot) { throw "content-address collision: $ContentAddressedRoot" }
Move-Item -LiteralPath $SnapshotRoot -Destination $ContentAddressedRoot
$env:EVB_AUTHORITY_ROOT = $ContentAddressedRoot
$env:EVB_AUTHORITY_SHA256 = $ManifestSha256
```

- [ ] **Isolation second.** Invoke `superpowers:using-git-worktrees`, ask the user to approve worktree or in-place mode, and enter the approved directory. If safe inheritance cannot be proved, request approval for in-place execution; do not infer consent and do not create a preservation commit.
- [ ] **Execution root third.** Set `$ExecutionRoot`; verify existing allowlisted bytes or materialize only absent allowlisted files from the snapshot. Existing destination bytes with a different hash are a collision. Destination containment and post-copy hashes are mandatory; no unrelated file is copied.

```powershell
$ExecutionRoot = (Resolve-Path ".").Path
$AuthorityManifestPath = Join-Path $env:EVB_AUTHORITY_ROOT "authority_manifest.v1.json"
if ((Get-FileHash $AuthorityManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $env:EVB_AUTHORITY_SHA256) { throw "authority manifest changed" }
$Authority = Get-Content -Raw $AuthorityManifestPath | ConvertFrom-Json
foreach ($Entry in $Authority.entries) {
  $Relative = [string]$Entry.relative_path
  $Source = (Resolve-Path -LiteralPath (Join-Path $env:EVB_AUTHORITY_ROOT $Relative)).Path
  $Destination = [IO.Path]::GetFullPath((Join-Path $ExecutionRoot $Relative))
  if (-not $Destination.StartsWith($ExecutionRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "execution destination root escape: $Relative" }
  if (Test-Path -LiteralPath $Destination) {
    if ((Get-FileHash $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) { throw "authority destination collision: $Relative" }
  } else {
    New-Item -ItemType Directory -Path (Split-Path $Destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
    if ((Get-FileHash $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) { throw "materialized authority hash mismatch: $Relative" }
  }
}
```

- [ ] Before each task, set the exact `$TaskId` and `$TaskFiles` from that task's commit block and run this task-start snapshot. It classifies each path as `new`, `safe_existing`, or `commit_deferred`; task-start dirty/mixed-owner files are never auto-staged.

```powershell
if ($TaskId -notmatch '^task-(?:[0-9]|1[0-4])$') { throw "invalid task id" }
Invoke-NativeChecked "task index probe" { & git diff --cached --quiet } @(0,1)
$IndexWasClean = ($script:LastNativeExitCode -eq 0)
$TaskSnapshotRoot = Join-Path $env:EVB_AUTHORITY_ROOT ("tasks\" + $TaskId + "-" + [Guid]::NewGuid().ToString("N"))
if (Test-Path -LiteralPath $TaskSnapshotRoot) { throw "task snapshot collision" }
New-Item -ItemType Directory -Path $TaskSnapshotRoot | Out-Null
$TaskStartEntries = foreach ($Relative in $TaskFiles) {
  $Current = Join-Path $ExecutionRoot $Relative
  if (Test-Path -LiteralPath $Current) {
    $StatusLines = @(Invoke-NativeChecked "task status $Relative" { & git status --porcelain=v1 -- $Relative })
    $StageClass = if ($IndexWasClean -and $StatusLines.Count -eq 0) { "safe_existing" } else { "commit_deferred" }
    $Copy = Join-Path $TaskSnapshotRoot $Relative
    New-Item -ItemType Directory -Path (Split-Path $Copy -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $Current -Destination $Copy
    [ordered]@{ relative_path=$Relative; existed=$true; sha256=(Get-FileHash $Current -Algorithm SHA256).Hash.ToLowerInvariant(); stage_class=$StageClass; status=@($StatusLines) }
  } else {
    [ordered]@{ relative_path=$Relative; existed=$false; sha256=$null; stage_class=if($IndexWasClean){"new"}else{"commit_deferred"}; status=@() }
  }
}
$TaskStartJson = [ordered]@{ schema_version="evb.task-start/v1"; task_id=$TaskId; files=@($TaskStartEntries) } | ConvertTo-Json -Depth 6 -Compress
[IO.File]::WriteAllText((Join-Path $TaskSnapshotRoot "task_start.v1.json"), $TaskStartJson, [Text.UTF8Encoding]::new($false))
$AllStatus = @(Invoke-NativeChecked "task status all" { & git status --porcelain=v1 -- $TaskFiles })
$AllStatus | Set-Content -LiteralPath (Join-Path $TaskSnapshotRoot "git_status_before.txt") -Encoding utf8
```

- [ ] After GREEN, calculate the task delta before staging. For each file, compare task-start and current SHA-256, save the non-index binary diff outside the workspace, and hash `task_delta_manifest.v1.json`. Interactive staging is forbidden.

```powershell
$Empty = Join-Path $TaskSnapshotRoot "empty"
[IO.File]::WriteAllBytes($Empty, [byte[]]::new(0))
$DeltaEntries = foreach ($Entry in $TaskStartEntries) {
  $Relative = $Entry.relative_path
  $Before = if ($Entry.existed) { Join-Path $TaskSnapshotRoot $Relative } else { $Empty }
  $After = Join-Path $ExecutionRoot $Relative
  if (-not (Test-Path -LiteralPath $After)) { throw "task deleted an allowlisted file: $Relative" }
  $PatchPath = Join-Path $TaskSnapshotRoot ((($Relative -replace '[\\/]', '__')) + ".patch")
  $Patch = @(Invoke-NativeChecked "task delta $Relative" { & git diff --no-index --binary -- $Before $After } @(0,1))
  [IO.File]::WriteAllLines($PatchPath, [string[]]$Patch, [Text.UTF8Encoding]::new($false))
  [ordered]@{ relative_path=$Relative; before_sha256=$Entry.sha256; after_sha256=(Get-FileHash $After -Algorithm SHA256).Hash.ToLowerInvariant(); patch_sha256=(Get-FileHash $PatchPath -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$DeltaJson = [ordered]@{ schema_version="evb.task-delta/v1"; task_id=$TaskId; entries=@($DeltaEntries) } | ConvertTo-Json -Depth 6 -Compress
$DeltaManifest = Join-Path $TaskSnapshotRoot "task_delta_manifest.v1.json"
[IO.File]::WriteAllText($DeltaManifest, $DeltaJson, [Text.UTF8Encoding]::new($false))
$TaskDeltaSha256 = (Get-FileHash $DeltaManifest -Algorithm SHA256).Hash.ToLowerInvariant()
```
- [ ] Stage non-interactively by task-start classification. New files and `safe_existing` files may use exact-path `git add`; `commit_deferred` files remain only in the external task delta and require user review. Never auto-stage, overwrite, revert, or commit a task-start dirty/mixed-owner file.

```powershell
$NewFiles = @($TaskStartEntries | Where-Object stage_class -eq "new" | ForEach-Object relative_path)
$SafeExistingFiles = @($TaskStartEntries | Where-Object stage_class -eq "safe_existing" | ForEach-Object relative_path)
$DeferredFiles = @($TaskStartEntries | Where-Object stage_class -eq "commit_deferred" | ForEach-Object relative_path)
if ($NewFiles.Count -gt 0) { Invoke-NativeChecked "stage new task files" { & git add -- $NewFiles } }
if ($SafeExistingFiles.Count -gt 0) { Invoke-NativeChecked "stage clean-existing task files" { & git add -- $SafeExistingFiles } }
$Staged = @(Invoke-NativeChecked "list staged task files" { & git diff --cached --name-only })
$Unexpected = @($Staged | Where-Object { $_ -notin $NewFiles -and $_ -notin $SafeExistingFiles })
if ($Unexpected.Count -ne 0) { throw "unrelated staged paths: $($Unexpected -join ',')" }
Invoke-NativeChecked "cached diff check" { & git diff --cached --check }
$CachedDiff = @(Invoke-NativeChecked "cached diff audit" { & git diff --cached --binary -- $NewFiles $SafeExistingFiles })
$CachedPatchPath = Join-Path $TaskSnapshotRoot "cached.patch"
$CachedDiff | Set-Content -LiteralPath $CachedPatchPath -Encoding utf8
$CachedPatchSha256 = (Get-FileHash $CachedPatchPath -Algorithm SHA256).Hash.ToLowerInvariant()
$CommitDisposition = if ($DeferredFiles.Count -gt 0) { "safe_files_staged_mixed_hunks_commit_deferred" } elseif ($Staged.Count -gt 0) { "safe_files_staged" } else { "no_safe_delta" }
```

Each Commit step commits safe staged files only when `$Staged.Count -gt 0`; it reports `$DeferredFiles`, task-delta manifest path/SHA-256, and `commit_deferred` to the user. Mixed-ownership files such as `backend/main.py` are never auto-staged when dirty at task start. Failure manifestation: unsafe inheritance, authority mismatch, index contamination, or mixed hunks blocks that commit without reset, checkout, revert, overwrite, or staging fallback.

## 2. File Responsibility Map

| File | Action | Single responsibility |
|---|---|---|
| `src/huiji_rag/models.py` | Create | Versioned source, binding, artifact, report, and manifest dataclasses/enums |
| `src/huiji_rag/source.py` | Create | Read-only raw source/resource inventory and canonical non-media identity projection |
| `src/huiji_rag/normalizer.py` | Create | NFC, language alias, exact expected filename, ASCII-only comparison, path containment |
| `src/huiji_rag/voice_binding.py` | Create | Exact eventName binding and deterministic binding status classification |
| `src/huiji_rag/diagnostics.py` | Create | Conflict expansion closure, quarantine/fatal reports, baseline classification |
| `src/huiji_rag/artifacts.py` | Create | v1 legacy adapter, v2 media schema, runtime projection, inventory/manifest hashing |
| `src/huiji_rag/builder.py` | Create | Isolated full build orchestration; no direct external mutation |
| `src/huiji_rag/minio_strict.py` | Create | Capability-preflighted `If-None-Match: *` conditional create and readback |
| `src/huiji_rag/vector_registry.py` | Create | Append-only name registry, hash chain, intent/final collection manifests |
| `src/huiji_rag/shadow_vectorstore.py` | Create | Dedicated new-name-only Milvus controller/builder/lifecycle clients |
| `src/huiji_rag/vector_experiment.py` | Create | Immutable experiment/query-label/split manifests and end-to-end A/B metrics |
| `src/huiji_rag/activation_models.py` | Create | Activation tuple, transaction, target, ack, epoch, state schemas |
| `src/huiji_rag/activation_store.py` | Create | Durable pointer/journal/coordinator locks, CAS, immutable snapshots/acks |
| `src/huiji_rag/runtime_activation.py` | Create | Standby dependency graph, request epoch pinning, prepare/commit/rollback |
| `src/huiji_rag/promotion.py` | Create | P0 gate aggregation and artifact/collection promotion decision |
| `scripts/capture_evb_baseline.py` | Create | Historical evidence capture and current dynamic before inventory |
| `scripts/build_huiji_evb.py` | Create | Offline isolated build CLI |
| `scripts/run_evb_vector_experiment.py` | Create | Phase-separated prepare/intent/build-dev/freeze/held-out shadow CLI |
| `scripts/activate_evb_build.py` | Create | Authorization-bound activate/rollback CLI |
| `scripts/verify_evb_real_data.py` | Create | Dynamic real-data hard-gate evaluator and report writer |
| `requirements.txt` | Modify | Pin the only supported strict-upload SDK to `minio==7.2.20` |
| `src/huiji_rag/io.py` | Modify | Versioned paths and durable canonical JSON helpers |
| `src/huiji_rag/media.py` | Modify | Full SHA-1 media ID and non-voice compatibility only |
| `src/assets/huiji_registry.py` | Modify | Active artifact consumer and quarantine/public-field rejection |
| `src/assets/voice_pagination.py` | Modify | `zh-hant`, build epoch cursor, existing pagination contract |
| `backend/main.py` | Modify | Runtime graph provider, health/ack endpoints, request epoch pinning |
| `backend/schemas.py` | Modify | Public safe media and activation health response schemas |
| `src/rag/vectorstore.py` | Modify | Read/load compatibility only; explicit EVB forbidden-helper guard tests |

### Shared Type Contracts

| Type | Exact fields |
|---|---|
| `EvbBuildPaths` | `raw_root`, `processed_root`, `build_root`, `runtime_root`, `diagnostic_root`, `indexes_root`, `parent_blocks`, `child_blocks`, `binding_inventory`, `media_assets_v2`, `media_schema_v2`, `media_manifest_v2`, `build_manifest`, `build_report`, `child_bm25` as `Path` |
| `BuildRequest` | `build_version: str`, `baseline_path: Path`, `expected_baseline_sha256: str`, immutable `preflight_bundle_path: Path`, `expected_preflight_bundle_sha256: str`, `allow_minio_write: bool`, `experiment_id: str | None` |
| `BuildResult` | `paths: EvbBuildPaths`, `manifest_sha256: str`, `fatal: bool`, `quarantined_count: int`, `reports: Mapping[str, Path]` |
| `ResourceRow` | `stable_id`, `language`, `basename`, `local_relpath`, `sha1`, `sha256`, `size`, `mime` |
| `VoiceSourceRow` | `stable_id`, `audio_id`, `entity_id`, `canonical_parent_id`, `canonical_child_id`, `language`, `event_name`, `transcript` |
| `VoiceResourceIndex` | immutable mapping from `(canonical_language, ascii_filename_key)` to ordered `ResourceRow` values |
| `BindingRecord` | source identity fields, expected/resource filename, `source_sha1`, `content_sha256`, `object_key`, `text_sha256`, `binding_status`, `quality_flags`, `evidence_ids` |
| `ConflictResult` | `fatal_ids`, `quarantined_ids`, `shortfall_ids`, `exact_ids`, `stop_mutations`, `root_causes` |
| `ConflictClosure` | `visited_ids`, `round_counts`, dimension counts, `closure_sha256`, `whole_corpus_visited` |
| `MediaArtifacts` | `binding_rows`, `runtime_rows`, `schema`, `manifest`, `nonvoice_rows` |
| `ArtifactManifest` | schema/build versions, file paths/SHA-256/row counts, baseline SHA, input SHA, previous build, runtime projection counts |
| `CapabilityEvidence` | `conditional_create_supported`, `application_audit_supported`, `durable_replace_supported`, `details`, `checked_at_utc` |
| `ObjectInventory` | bucket/prefix, sorted object key/version/ETag/SHA-1/SHA-256/size records, captured time, inventory SHA-256 |
| `ObjectEvidence` | `status`, bucket/key, nullable `version_id`, `etag`, nullable server request ID, SHA-1/SHA-256/size before/after, HTTP readback, mandatory application operation/audit ID |
| `MinioOperationPlan` | `schema_version`, `plan_id`, baseline path/SHA-256, build-manifest path/SHA-256, preflight-bundle path/SHA-256, before-inventory path/SHA-256, ordered exact missing objects with bucket/key/SHA-1/SHA-256/size/contained source path/content type, `created_at_utc`, `used_by_operation_id: str | None`, `operation_plan_sha256` computed without itself; the immutable use marker, not this document, records the claimed operation ID |
| `MinioPlanUseMarker` | plan path/SHA-256, operation ID, exact object-set hash, claimed time, marker SHA-256; immutable create-new sibling proving one-time use while plan bytes retain `used_by_operation_id=null` |
| `LifecycleEvidence` | exact collection name/identity, lifecycle-plan SHA-256, principal, release/unload operation, `status: unloaded_terminal | cleanup_failed_terminal`, result, audit ID, timestamp, and evidence SHA-256 |
| `LifecycleOperationPlan` | `schema_version`, lifecycle ID, exact experiment/candidate/collection name and identity, preflight/intent SHA-256, finalized collection-manifest SHA-256 or partial build-evidence SHA-256, reason enum, created time, nullable use ID, and plan SHA-256 excluding itself |
| `LifecycleReason` | one of `build_partial`, `build_failed`, `dev_unselected`, `held_out_failed`, `held_out_inconclusive`, `orchestration_abort` |
| `LoadedMediaArtifacts` | `build_version`, `activation_epoch`, `artifact_schema_version`, `records`, `manifest_sha256` |
| `ShadowReservation` | `sequence`, `nonce32hex`, `collection_name`, `record_sha256`, `experiment_id`, `candidate_id` |
| `CollectionIntentManifest` | IDs, reservation evidence, owner-token hash, input build/artifact hashes, complete treatment config and fingerprint, experiment/query-label/split hashes |
| `CollectionIdentity` | `collection_name`, server identity, schema fingerprint, owner-token hash |
| `CollectionInventory` | collection name/identity/schema/row/PK/payload/index/load fingerprints and captured inventory SHA-256 |
| `CapacityEvidence` | active/candidate resource limits, measured usage, isolation thresholds, captured time and SHA-256 |
| `AclEvidence` | controller/builder/lifecycle principal grants and explicit denies, proxy policy hash, capability result and SHA-256 |
| `MutationAuthority` | verified preflight/intent/active/capacity/ACL/owner hashes plus exact collection allowlist and operation ID |
| `VectorIntentUseMarker` | candidate/preflight/intent/active-inventory hashes, build operation ID, claimed time and marker SHA-256; immutable `intent_use.v1.json` created before collection create |
| `VectorBuildEvidence` | identity, `collection_created`, `collection_loaded`, `requires_unload`, `server_identity`, row/PK/payload/vector hashes, schema/index/load evidence, inserted-row count, missing/duplicate/non-finite counts, terminal build status |
| `CollectionManifest` | intent SHA, actual identity/schema/payload/vector/index/search/build/evaluation fingerprints, row/PK hashes, input hashes, finalized time |
| `ExperimentRequest` | experiment ID, input build/artifact hashes, candidate configs, deterministic seed, curated evaluator path |
| `VectorPreflightPlan` | `schema_version`, experiment/build/artifact/active-inventory/capacity/ACL/owner hashes, immutable experiment/query-label/split/candidate-registry paths and hashes, ordered candidate IDs/config hashes, `created_at_utc`, `preflight_sha256` |
| `ExperimentManifest` | immutable schema/provenance/query-label/split/template/seed/input hashes |
| `CandidateRegistry` | immutable ordered candidate IDs, complete config paths/hashes, shared experiment/split/seed hashes and registry SHA-256 |
| `QueryLabelEvidence` | query-label JSONL/meta paths and hashes, provenance hashes, eligible entity/template groups and counts |
| `FrozenSplit` | dev entity IDs, held-out entity IDs, template partition hash, seed |
| `CandidateTuple` | collection identity plus query embedding model/config, metric, index params, search params |
| `ArmEvaluation` | split, candidate ID, per-intent metrics, latency/error observations, cost/time, gate results |
| `DevEvaluationBundleManifest` | schema `evb.dev-evaluation-bundle/v1`, experiment/preflight/candidate-registry hashes, complete ordered candidate set, each candidate's exact dev-report path/SHA-256 and build/lifecycle state, created time, and bundle SHA-256 |
| `FrozenCandidate` | immutable path/SHA-256, candidate ID/config/collection, dev evidence SHA and held-out execution count `0` before acceptance |
| `HeldOutExecutionMarker` | experiment/candidate/frozen SHA-256, execution ID, created time, status `claimed`, marker SHA-256; create-new before any held-out request |
| `AcceptanceEvaluation` | primary/secondary metrics, clustered-bootstrap CI/power, hard coverage, wrong-entity, latency/error CIs, pass flag |
| `ActivationTuple` | `build_version`, `build_manifest_sha256`, `milvus_collection_name`, `collection_schema_fingerprint`, `collection_manifest_sha256`, `embedding_model_id`, `embedding_config_fingerprint`, `artifact_schema_version` |
| `ActiveBuildPointer` | `schema_version`, `generation`, the eight flattened `ActivationTuple` fields, `previous_build_version`, `deployment_inventory_sha256`, `activation_epoch`, `activation_id`, `activated_at_utc`; `as_activation_tuple()` reconstructs the exact tuple |
| `ActivationJournal` | transaction ID/version/state, authorization path/SHA-256/use-marker SHA-256, previous/next complete tuples and epochs, snapshot/targets hashes, immutable ack refs, observed pointer/router state |
| `ActivationState` | one of `preparing`, `prepared`, `committing`, `committed`, `rollback_preparing`, `rolling_back`, `rolled_back`, `aborted`, `conflict` |
| `ActivationAck` | target/process/challenge, transaction/phase/epoch, complete tuple, snapshot/targets hashes, health/traffic state, timestamp, HMAC |
| `AckReference` | immutable ack relative path, SHA-256, target, epoch, phase, tuple fingerprint, HMAC result, received time |
| `ActivationRequest` | `transaction_id`, immutable promotion-authorization path/SHA-256, complete `expected_pointer`, complete `next_pointer`, deployment inventory path, report root |
| `DeploymentSnapshot` | immutable transaction-scoped deployment inventory bytes, SHA-256, authenticated unique target IDs, expected process-start nonces |
| `ActivationTargets` | immutable transaction-scoped target/challenge records, snapshot SHA-256, target-set SHA-256 |
| `CoordinatorLease` | coordinator lock path, owner metadata, acquired timestamp, OS lock handle |
| `RuntimeDependencyGraph` | `activation_tuple`, `media_registry`, `vectorstore`, `retriever`, `reranker`, `chain`, `cursor_state` as seven explicit fields |
| `RuntimeFactories` | typed factories for media registry, vectorstore, retriever, reranker, chain, and cursor state, each accepting the complete activation tuple or prior constructed dependency |
| `RequestActivationLease` | pinned activation epoch/tuple and graph reference held until request completion |
| `RouterEpochState` | current activation epoch, complete activation tuple fingerprint, router revision, observed time |
| `ActivationResult` | transaction ID/state, active tuple, router epoch, immutable ack references |
| `PromotionEvidence` | all artifact/MinIO/vector/runtime/activation gate outcomes and report hashes |
| `PromotionDecision` | `allowed`, `artifact_tuple`, optional selected collection tuple, `red_gates`, `reasons` |
| `PromotionAuthorization` | `schema_version`, `authorization_id`, `authorization_type`, selected complete next `ActivationTuple`, expected current complete pointer tuple/generation/epoch, artifact/MinIO/vector/runtime-preflight gate hashes, `report_manifest_sha256`, `created_at_utc`, `used_by_transaction: str | None`, `authorization_sha256` computed from canonical JSON with only `authorization_sha256` removed |
| `AuthorizationUseMarker` | authorization path/SHA-256, transaction ID, expected/next pointer fingerprints, claimed time, marker SHA-256; immutable create-new sibling proving one-time use while authorization bytes retain `used_by_transaction=null` |
| `PromotionOutcome` | authorization/transaction hashes, committed tuple/epoch, commit-ack hashes, post-activation API/inventory gate hashes, `status: success | rolled_back | rollback_failed`, created time and outcome SHA-256 |
| `RollbackEvidence` | committed/auth/current-pointer hashes, rollback journal/ack hashes, restored tuple/router epoch, terminal state and evidence SHA-256 |
| `ReportManifest` | report paths/SHA-256/schema versions plus build, experiment, candidate, transaction identities |
| `RealBeforeInventory` | source/dev/MinIO/active-Milvus/deployment/active-pointer inventories and fingerprints |
| `RealAfterInventory` | corresponding post-run inventories plus active tuple/router epoch/report manifest |
| `PreflightBundleManifest` | schema `evb.preflight-bundle/v1`, bundle ID/baseline SHA, and exact relative path/SHA-256 entries for `source_inventory.v1.json`, `dev_inventory.v1.json`, `minio_before.v1.json`, `milvus_before.v1.json`, `vector_capacity.v1.json`, `vector_acl.v1.json`, `vector_owner.v1.json`, `runtime_preflight.v1.json`, `deployment_inventory.v1.json`, and `active_pointer_before.v1.json` |
| `PostactivationObservationBundle` | schema `evb.postactivation-observation-bundle/v1`, transaction/authorization/before-bundle hashes, red-gate list, and exact relative path/SHA-256 entries for `active_pointer_observed.v1.json`, `after_inventory.v1.json`, `runtime_health.v1.json`, and `api_verification.v1.json`; it contains no outcome or rollback status |
| `PostactivationBundleManifest` | schema `evb.postactivation-bundle/v1`, observation-bundle SHA-256, final `promotion_outcome.v1.json` path/SHA-256, and nullable rollback-bundle path/SHA-256; it is written only after green finalization or completed rollback finalization |
| `RollbackBundleManifest` | schema `evb.rollback-bundle/v1`, source observation-bundle/transaction/authorization hashes, and exact relative path/SHA-256 entries for `active_pointer_rolled_back.v1.json`, `rolled_back_inventory.v1.json`, `runtime_preflight.v1.json`, and `rollback_transaction.v1.json` |
| `GateSummary` | named gate outcomes, red/inconclusive gates, evidence hashes, overall pass flag |
| `IntegrationEvidence` | fake pipeline artifacts, call log, reports, activation/rollback outcomes |
| `FaultEvidence` | injected point, expected state, observed pointer/router state, recovery action, pass flag |
| `ExternalCall` | service, method, target, mutating flag, arguments hash |
| `BootstrapEvidence` | deterministic seed, iterations, effective entities, delta samples hash, confidence interval, empirical power |
| `EvbIntegrationFixture` | synthetic source/resources, fake MinIO/Milvus, deployment targets, initial activation tuple |
| `ActivationFixture` | fake pointer/router/journal state, targets, secrets, injected OS durability adapters |

All dataclasses serialize through canonical JSON adapters; production code must not pass untyped dictionaries across these module boundaries except at JSON/API edges.

Immutable mutation-authority paths are fixed and containment-checked: `data/processed/huiji/{build_version}/operations/minio_operation_plan.v1.json` with sibling `minio_operation_plan.use.v1.json`; experiment files under `data/processed/huiji/vector/experiments/{experiment_id}/` and candidate files under `candidates/{candidate_id}/`, including create-new `intent_use.v1.json` and `lifecycle/{lifecycle_id}/lifecycle_operation_plan.v1.json`; `data/processed/huiji/activation/authorizations/{authorization_id}/promotion_authorization.v1.json` with sibling `uses/{transaction_id}.v1.json` authorization-use markers. Collision is a create-new failure; no command redirects these authorities to `eval/`.

Exact schema constants are `evb.minio-operation-plan/v1`, `evb.vector-preflight-plan/v1`, `evb.dev-evaluation-bundle/v1`, `evb.lifecycle-operation-plan/v1`, `evb.preflight-bundle/v1`, `evb.postactivation-observation-bundle/v1`, `evb.postactivation-bundle/v1`, `evb.rollback-bundle/v1`, `evb.promotion-authorization/v1`, `evb.authorization-use/v1`, and `evb.promotion-outcome/v1`; `authorization_type` is only `promote` or `reactivate`. Hash fields use lowercase SHA-256 over canonical UTF-8 JSON with deterministic key ordering/separators and removal of only the document's own hash field.

## 3. Command and Evidence Catalog

Set `$Python = "D:\Anaconda32024\envs\LangChain\python.exe"` once after entering `$ExecutionRoot`. Every command below is executed through `Invoke-NativeChecked`; allowed nonzero codes are listed only where control flow handles them immediately.

| Code | Exact command or evidence |
|---|---|
| `C01` | `Invoke-NativeChecked "C01" { & $Python -m pytest tests/test_evb_baseline.py tests/test_evb_source.py -q }` |
| `C02` | `Invoke-NativeChecked "C02" { & $Python -m pytest tests/test_evb_normalizer.py tests/test_evb_voice_binding.py -q }` |
| `C03` | `Invoke-NativeChecked "C03" { & $Python -m pytest tests/test_evb_diagnostics.py -q }` |
| `C04` | `Invoke-NativeChecked "C04" { & $Python -m pytest tests/test_evb_artifacts.py tests/test_sparse_bm25.py -q }` |
| `C05` | `Invoke-NativeChecked "C05" { & $Python -m pytest tests/test_evb_minio_strict.py tests/test_minio_shared_upload.py -q }` |
| `C06` | `Invoke-NativeChecked "C06" { & $Python -m pytest tests/test_evb_runtime_registry.py tests/test_huiji_media_registry.py tests/test_voice_pagination.py -q }` |
| `C06F` | From `frontend/react-app`, hash source; `Invoke-NativeChecked "C06F tests" { & npm test -- src/components/chat/MessageBubble.test.tsx src/api/media.test.ts }`; `Invoke-NativeChecked "C06F build" { & npm run build -- --outDir $env:TEMP/evb-frontend-build-$PID --emptyOutDir }`; rehash source and block on any difference or failure |
| `C07` | `Invoke-NativeChecked "C07" { & $Python -m pytest tests/test_evb_vector_registry.py tests/test_evb_shadow_vectorstore.py tests/test_vectorstore.py -q }` |
| `C08` | `Invoke-NativeChecked "C08" { & $Python -m pytest tests/test_evb_vector_experiment.py tests/test_huiji_eval.py -q }` |
| `C09` | `Invoke-NativeChecked "C09" { & $Python -m pytest tests/test_evb_activation_store.py -q }` |
| `C10` | `Invoke-NativeChecked "C10" { & $Python -m pytest tests/test_evb_runtime_activation.py tests/test_sse.py -q }` |
| `C11` | `Invoke-NativeChecked "C11" { & $Python -m pytest tests/test_evb_promotion.py tests/test_multi_intent_voice_eval.py -q }` |
| `C12` | `Invoke-NativeChecked "C12" { & $Python -m pytest tests -q }` |
| `C13` | `Invoke-NativeChecked "C13" { & $Python scripts/capture_evb_baseline.py --build dev --output $env:EVB_BASELINE_PATH }` |
| `C14` | `Invoke-NativeChecked "C14" { & $Python scripts/build_huiji_evb.py offline --build-version evb-gate --baseline tests/fixtures/evb/baseline.v1.json --expected-baseline-sha256 $env:EVB_FAKE_BASELINE_SHA256 --preflight-bundle tests/fixtures/evb/preflight_bundle/preflight_bundle_manifest.v1.json --expected-preflight-bundle-sha256 $env:EVB_FAKE_PREFLIGHT_BUNDLE_SHA256 --dry-run --output-root eval/evb_fake_build }` |
| `C15` | `Invoke-NativeChecked "C15" { & $Python scripts/run_evb_vector_experiment.py fake-pipeline --fixture tests/fixtures/evb/vector_pipeline.v1.json --expected-fixture-sha256 $env:EVB_VECTOR_FIXTURE_SHA256 --report-root eval/evb_vector_fake }` |
| `C16` | `Invoke-NativeChecked "C16" { & $Python scripts/activate_evb_build.py fault-matrix --fixture tests/fixtures/evb/activation_pipeline.v1.json --expected-fixture-sha256 $env:EVB_ACTIVATION_FIXTURE_SHA256 --report eval/evb_activation_fake.json }` |
| `C17` | `Invoke-NativeChecked "C17" { & $Python scripts/verify_evb_real_data.py capture-preflight --build-version $env:EVB_REAL_BUILD --baseline $env:EVB_BASELINE_PATH --expected-baseline-sha256 $env:EVB_BASELINE_SHA256 --output-root eval/evb_real/preflight }` |
| `C18` | `Invoke-NativeChecked "C18" { & $Python scripts/verify_evb_real_data.py postactivate --transaction-record eval/evb_real/activation/committed_transaction.v1.json --expected-transaction-sha256 $env:EVB_COMMITTED_TRANSACTION_SHA256 --promotion-authorization $env:EVB_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_AUTHORIZATION_SHA256 --before-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-before-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --rollback-transaction-id $env:EVB_ROLLBACK_TRANSACTION_ID --output-root eval/evb_real/postactivation } @(0,6,7)` |
| `C19` | `Invoke-NativeChecked "C19" { & $Python scripts/build_huiji_evb.py minio-plan --build-manifest $env:EVB_BUILD_MANIFEST_PATH --expected-build-manifest-sha256 $env:EVB_BUILD_MANIFEST_SHA256 --preflight-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-preflight-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --before-inventory $env:EVB_MINIO_BEFORE_PATH --expected-before-inventory-sha256 $env:EVB_MINIO_BEFORE_SHA256 --baseline $env:EVB_BASELINE_PATH --expected-baseline-sha256 $env:EVB_BASELINE_SHA256 --output $env:EVB_MINIO_PLAN_PATH }` |
| `C20` | `Invoke-NativeChecked "C20" { & $Python scripts/build_huiji_evb.py minio-upload --operation-plan $env:EVB_MINIO_PLAN_PATH --expected-plan-sha256 $env:EVB_MINIO_PLAN_SHA256 --report $env:EVB_MINIO_REPORT_PATH }` |
| `C21` | `Invoke-NativeChecked "C21" { & $Python scripts/run_evb_vector_experiment.py prepare --experiment-id $env:EVB_EXPERIMENT_ID --build-manifest $env:EVB_BUILD_MANIFEST_PATH --expected-build-manifest-sha256 $env:EVB_BUILD_MANIFEST_SHA256 --preflight-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-preflight-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --candidate-configs $env:EVB_CANDIDATE_CONFIGS --expected-candidate-configs-sha256 $env:EVB_CANDIDATE_CONFIGS_SHA256 --output-root data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID }` |
| `C22` | `Invoke-NativeChecked "C22" { & $Python scripts/run_evb_vector_experiment.py intent --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --candidate-id $env:EVB_CANDIDATE_ID --output $env:EVB_VECTOR_INTENT }` |
| `C23` | `Invoke-NativeChecked "C23" { & $Python scripts/run_evb_vector_experiment.py build-dev --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --intent-manifest $env:EVB_VECTOR_INTENT --expected-intent-sha256 $env:EVB_VECTOR_INTENT_SHA256 --report-root $env:EVB_VECTOR_CANDIDATE_ROOT } @(0,3,4,5)` |
| `C24` | `Invoke-NativeChecked "C24" { & $Python scripts/run_evb_vector_experiment.py freeze --dev-bundle $env:EVB_DEV_BUNDLE_PATH --expected-dev-bundle-sha256 $env:EVB_DEV_BUNDLE_SHA256 --output data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/frozen_decision.v1.json }` |
| `C25` | `Invoke-NativeChecked "C25" { & $Python scripts/run_evb_vector_experiment.py held-out --frozen-candidate data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/frozen_decision.v1.json --expected-frozen-sha256 $env:EVB_FROZEN_SHA256 --execution-marker data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/held_out_execution.v1.json --report data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/held_out_report.v1.json --decision-output data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/vector_promotion_decision.v1.json } @(0,3,4,5)` |
| `C26` | `Invoke-NativeChecked "C26" { & $Python scripts/verify_evb_real_data.py aggregate-preactivation --preflight-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-preflight-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --build-manifest $env:EVB_BUILD_MANIFEST_PATH --expected-build-manifest-sha256 $env:EVB_BUILD_MANIFEST_SHA256 --minio-report $env:EVB_MINIO_REPORT_PATH --expected-minio-report-sha256 $env:EVB_MINIO_REPORT_SHA256 --vector-decision $env:EVB_VECTOR_DECISION --expected-vector-decision-sha256 $env:EVB_VECTOR_DECISION_SHA256 --runtime-preflight $env:EVB_RUNTIME_PREFLIGHT_PATH --expected-runtime-preflight-sha256 $env:EVB_RUNTIME_PREFLIGHT_SHA256 --output eval/evb_real/promotion/report_manifest.v1.json }` |
| `C27` | `Invoke-NativeChecked "C27" { & $Python scripts/verify_evb_real_data.py authorize --report-manifest eval/evb_real/promotion/report_manifest.v1.json --expected-report-manifest-sha256 $env:EVB_REPORT_MANIFEST_SHA256 --expected-pointer $env:EVB_ACTIVE_POINTER_BEFORE_PATH --expected-pointer-sha256 $env:EVB_ACTIVE_POINTER_BEFORE_SHA256 --next-tuple eval/evb_real/promotion/next_activation_tuple.v1.json --expected-next-tuple-sha256 $env:EVB_NEXT_TUPLE_SHA256 --authorization-type promote --output $env:EVB_AUTHORIZATION_PATH }` |
| `C28` | `Invoke-NativeChecked "C28" { & $Python scripts/activate_evb_build.py activate --transaction-id $env:EVB_TRANSACTION_ID --promotion-authorization $env:EVB_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_AUTHORIZATION_SHA256 --report-root eval/evb_real/activation }` |
| `C29` | `Invoke-NativeChecked "C29" { & $Python scripts/activate_evb_build.py rollback --transaction-id $env:EVB_ROLLBACK_TRANSACTION_ID --committed-transaction eval/evb_real/activation/committed_transaction.v1.json --expected-transaction-sha256 $env:EVB_COMMITTED_TRANSACTION_SHA256 --promotion-authorization $env:EVB_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_AUTHORIZATION_SHA256 --postactivation-observation-bundle $env:EVB_POSTACTIVATION_OBSERVATION_PATH --expected-postactivation-observation-bundle-sha256 $env:EVB_POSTACTIVATION_OBSERVATION_SHA256 --output-root eval/evb_real/rollback }` |
| `C30` | `Invoke-NativeChecked "C30" { & $Python scripts/verify_evb_real_data.py authorize --report-manifest eval/evb_real/reactivation/report_manifest.v1.json --expected-report-manifest-sha256 $env:EVB_REACTIVATION_REPORT_SHA256 --rollback-bundle $env:EVB_ROLLBACK_BUNDLE_PATH --expected-rollback-bundle-sha256 $env:EVB_ROLLBACK_BUNDLE_SHA256 --expected-pointer $env:EVB_ROLLED_BACK_POINTER_PATH --expected-pointer-sha256 $env:EVB_ROLLED_BACK_POINTER_SHA256 --next-tuple eval/evb_real/promotion/next_activation_tuple.v1.json --expected-next-tuple-sha256 $env:EVB_NEXT_TUPLE_SHA256 --authorization-type reactivate --output $env:EVB_REACTIVATION_AUTHORIZATION_PATH }` |
| `C31` | `Invoke-NativeChecked "C31" { & $Python scripts/activate_evb_build.py activate --transaction-id $env:EVB_REACTIVATE_TRANSACTION_ID --promotion-authorization $env:EVB_REACTIVATION_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_REACTIVATION_AUTHORIZATION_SHA256 --report-root eval/evb_real/reactivation/activation }` |
| `C32` | `Invoke-NativeChecked "C32" { & $Python scripts/run_evb_vector_experiment.py lifecycle-plan --candidate-root $env:EVB_VECTOR_CANDIDATE_ROOT --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --intent-manifest $env:EVB_VECTOR_INTENT --expected-intent-sha256 $env:EVB_VECTOR_INTENT_SHA256 --evidence $env:EVB_LIFECYCLE_EVIDENCE_PATH --expected-evidence-sha256 $env:EVB_LIFECYCLE_EVIDENCE_SHA256 --reason $env:EVB_LIFECYCLE_REASON --output $env:EVB_LIFECYCLE_PLAN_PATH }` |
| `C33` | `Invoke-NativeChecked "C33" { & $Python scripts/run_evb_vector_experiment.py finalize-lifecycle --action unload --lifecycle-plan $env:EVB_LIFECYCLE_PLAN_PATH --expected-lifecycle-plan-sha256 $env:EVB_LIFECYCLE_PLAN_SHA256 --report $env:EVB_LIFECYCLE_REPORT_PATH }` |
| `C34` | `Invoke-NativeChecked "C34" { & $Python scripts/verify_evb_real_data.py postactivate --transaction-record eval/evb_real/reactivation/activation/committed_transaction.v1.json --expected-transaction-sha256 $env:EVB_REACTIVATION_COMMITTED_SHA256 --promotion-authorization $env:EVB_REACTIVATION_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_REACTIVATION_AUTHORIZATION_SHA256 --before-bundle $env:EVB_ROLLBACK_BUNDLE_PATH --expected-before-bundle-sha256 $env:EVB_ROLLBACK_BUNDLE_SHA256 --rollback-transaction-id $env:EVB_REACTIVATION_ROLLBACK_TRANSACTION_ID --output-root eval/evb_real/reactivation/postactivation } @(0,6,7)` |
| `C35` | `Invoke-NativeChecked "C35" { & $Python scripts/run_evb_vector_experiment.py dev-bundle --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --candidate-registry $env:EVB_CANDIDATE_REGISTRY_PATH --expected-candidate-registry-sha256 $env:EVB_CANDIDATE_REGISTRY_SHA256 --output $env:EVB_DEV_BUNDLE_PATH }` |

CLI parser contract is fixed before implementation:

- `capture_evb_baseline.py`: one read-only-capture command requiring `--build` and fixed-path `--output`; it writes create-new baseline evidence and returns `0/2/3`. A separate unit-test-only dry-run path is allowed but is not `C13` and cannot authorize a build.
- `build_huiji_evb.py`: `offline`, `minio-plan`, `minio-upload`; `offline` and `minio-plan` require baseline and preflight-bundle path/hash pairs, and `minio-plan` additionally requires build-manifest and MinIO-before path/hash pairs. Only `minio-upload` mutates object storage.
- `run_evb_vector_experiment.py`: `prepare`, `intent`, `build-dev`, `dev-bundle`, `freeze`, `held-out`, `lifecycle-plan`, `finalize-lifecycle`, `fake-pipeline`. `dev-bundle` writes a create-new complete candidate manifest; `freeze` accepts only its path/hash and never scans a directory. Only `build-dev` and `finalize-lifecycle --action unload` mutate Milvus.
- `activate_evb_build.py`: `activate`, `rollback`, `fault-matrix`. `activate` requires promotion authorization path/hash. `rollback` requires immutable transaction/auth/postactivation-observation-bundle path/hash pairs and writes a `RollbackBundleManifest` under its output root; it never consumes the final postactivation bundle.
- `verify_evb_real_data.py`: `capture-preflight`, `aggregate-preactivation`, `authorize`, `postactivate`. `capture-preflight` writes create-new sidecars and `preflight_bundle_manifest.v1.json`; `postactivate` writes sidecars plus `postactivation_bundle_manifest.v1.json` and automatically invokes authorization-bound rollback on red.
- Parsers return `0` for green/read-only completion, `2` for argument/schema/path/hash errors before mutation, `3` for blocked/red/inconclusive/reused evidence, `4` for concurrency or activation invariant breach, `5` for a stopped external operation with read-only diagnosis, `6` only when postactivation proves automatic rollback, and `7` when recovery is unproven.
- After `C18` or `C34`, switch on `$script:LastNativeExitCode`: `0` continues; `6` records the rollback bundle and terminates the run without drill/reactivation; `7` immediately escalates to manual authoritative recovery and terminates. No other branch continues.
- Every mutating subcommand resolves all evidence paths under fixed roots and verifies expected SHA-256 before opening a mutation client. Forward build/upload/vector/activation requires an unclaimed authority and atomically creates its one-time use marker. Rollback instead requires the original authorization use marker to name the exact committed transaction and rejects any absent/different use. All commands reject mutable, changed, improperly reused, extra-target, stale-active-inventory, or unhashed input.

Real-evidence codes used by the coverage matrix:

| Code | Required real-data acceptance |
|---|---|
| `R01` | Baseline and before inventories are captured from current raw/dev/MinIO/Milvus data with dynamic counts and hashes. |
| `R02` | Every current voice source row is classified by exact language/filename evidence; sampled exact, shortfall, skin, and conflict rows are manually traceable to raw records. |
| `R03` | Closure reports reach fixed point and report visited counts/hash over the current corpus; fatal stops writes while read-only expansion completes. |
| `R04` | Isolated v2 artifacts, non-media projection hash, BM25 semantic corpus hash, media ID inventory, and legacy adapter are verified against current dev. |
| `R05` | Real MinIO preflight proves conditional create and app audit capability; only approved missing SHA-1 keys are added and read back. |
| `R06` | Real Ask/SSE/all-page API responses use exact playable rows, return 409 on build mismatch, and leak no internal fields/paths. |
| `R07` | Real Milvus active inventory is unchanged; one never-before-used shadow name passes identity/schema/row/vector/permission/load checks. |
| `R08` | Frozen real experiment runs dev selection once and held-out once, reports all quality/performance/cost metrics, and either selects one passing candidate or retains active. |
| `R09` | Real deployment prepares every standby graph, commits one epoch, receives authenticated serving acks, completes a rollback drill to the full previous tuple, then uses a fresh hash-pinned authorization to reactivate and postverify the complete new tuple. |
| `R10` | Final report set, before/after inventories, dynamic sampling, all P0 gates, and promotion decision are green with no role/count hardcoding. |

Failure codes used by the coverage matrix:

| Code | Failure manifestation |
|---|---|
| `F01` | Evidence or input hash is absent, non-reproducible, hardcoded, or differs from the captured source. |
| `F02` | A voice row is guessed, cross-language, non-exact, unsafe, or attached to the wrong canonical child. |
| `F03` | Fatal/quarantine closure is incomplete, writes continue after fatal, or runtime receives excluded rows. |
| `F04` | Dev is modified, v2/legacy schema drifts, BM25/non-media parity changes, or runtime artifact contains non-consumable voice rows. |
| `F05` | MinIO capability is unproven, ordinary PUT/helper setup is called, existing object changes, or readback/audit differs. |
| `F06` | Runtime infers filenames, exposes internal fields/paths, duplicates media, violates pagination, or accepts a stale cursor. |
| `F07` | Existing collection changes, forbidden helper runs, name/manifest/permission chain fails, shadow is partial, or unload fails. |
| `F08` | Experiment evidence leaks across splits, held-out is reused/reselected, metrics/CI/resource gates fail, or result is inconclusive. |
| `F09` | Pointer/journal/ack durability, lock ordering, tuple/epoch isolation, authentication, recovery, commit, or rollback is invalid. |
| `F10` | Any automated/real gate is red, required report is missing, or promotion occurs without complete green evidence. |

## Task 0: Preserve Current Sources and Capture Baseline Evidence

**Files:**

- Create: `src/huiji_rag/models.py`
- Create: `src/huiji_rag/source.py`
- Create: `scripts/capture_evb_baseline.py`
- Create: `tests/test_evb_baseline.py`
- Create: `tests/test_evb_source.py`
- Modify: `src/huiji_rag/io.py`
- Read only: `src/huiji_rag/*.pyc`, `data/processed/huiji/dev/**`, current raw resource manifests

**Interfaces:**

- Produces: `canonical_json_bytes(value: object) -> bytes`, `sha256_json(value: object) -> str`, `capture_source_inventory(raw_root: Path) -> SourceInventory`, `capture_baseline_from_rows(inventory: SourceInventory, media_rows: Sequence[Mapping[str, object]], milvus_observation: Mapping[str, object]) -> BaselineEvidence`, `capture_baseline(cfg: Config, build_version: str) -> BaselineEvidence`.
- Produces immutable types:

```python
@dataclass(frozen=True)
class SourceInventory:
    source_inventory_sha256: str
    entity_rows: Sequence[dict[str, object]]
    resource_rows: Sequence[dict[str, object]]

@dataclass(frozen=True)
class BaselineEvidence:
    schema_version: str
    source_inventory_sha256: str
    observations: dict[str, int]
    milvus_observation: dict[str, object]

@dataclass(frozen=True)
class BaselineReceipt:
    schema_version: str
    baseline_relative_path: str
    baseline_sha256: str
    baseline_schema_version: str
    source_inventory_sha256: str
    receipt_sha256: str
```

**Spec IDs:** `EVB-BASELINE-P0-01..04`, `EVB-SCOPE-P0-01..03`, `EVB-BUILD-P0-02..03`, `EVB-IDENT-P0-01..03`, `EVB-SEC-P0-01`.

**Failure manifestation:** `F01` or mutation of current sources/dev blocks the task before builder work.

**Expected:** RED on missing source/evidence modules or any dynamic-inventory mismatch; GREEN when `C01` and `C13` pass. **Real acceptance:** `R01`.

- [ ] **Step 1: Add named RED source/baseline tests.** `test_canonical_json_hash_is_order_stable`, `test_capture_source_inventory_rejects_root_escape_and_pyc`, `test_parent_child_projection_ignores_media`, `test_baseline_serializes_six_dynamic_classes`, `test_media_id_inventory_uses_full_sha1_pattern`, and `test_capture_cli_requires_build_output_and_returns_documented_codes` define the read-only evidence/CLI contract.

```python
def test_baseline_uses_dynamic_observations_and_rejects_pyc(tmp_path):
    inventory = capture_source_inventory(tmp_path)
    evidence = capture_baseline_from_rows(inventory, media_rows=[], milvus_observation={})
    assert evidence.schema_version == "evb.baseline/v1"
    assert "historical_expected_count" not in evidence.observations
```

- [ ] **Step 2: Run `C01`; confirm failure.** Expected: import errors for `src.huiji_rag.models` and `src.huiji_rag.source`.
- [ ] **Step 3: Implement the exact interfaces from this task.** `canonical_json_bytes` uses sorted UTF-8 canonical JSON; `capture_source_inventory` resolves every path under raw root; `capture_baseline_from_rows` computes observations from input rows; `capture_baseline` writes create-new evidence and never imports `.pyc`.
- [ ] **Step 4: Run `C01`; expected PASS, then capture the baseline exactly once and persist an external receipt.** Set `$env:EVB_BASELINE_PATH = "data/processed/huiji/evidence/eventname_voice_binding_baseline.v1.json"`, run `C13`, require create-new exit `0`, and hash the file. Write `BaselineReceipt` plus a companion SHA file with create-new semantics under `$env:EVB_AUTHORITY_ROOT/evidence`; this receipt, not a shell variable, is the cross-session authority. Existing path, receipt collision, non-reproducible evidence, or hash mismatch is RED; `C13` is not dry-run.

```powershell
$env:EVB_BASELINE_PATH = "data/processed/huiji/evidence/eventname_voice_binding_baseline.v1.json"
Invoke-NativeChecked "C13 baseline capture" { & $Python scripts/capture_evb_baseline.py --build dev --output $env:EVB_BASELINE_PATH }
$BaselineResolved = (Resolve-Path -LiteralPath $env:EVB_BASELINE_PATH).Path
$BaselineRelative = [IO.Path]::GetRelativePath($ExecutionRoot, $BaselineResolved).Replace("\", "/")
if ($BaselineRelative.StartsWith("../") -or [IO.Path]::IsPathRooted($BaselineRelative)) { throw "baseline receipt path escapes execution root" }
$BaselineDoc = Get-Content -Raw $BaselineResolved | ConvertFrom-Json
$env:EVB_BASELINE_SHA256 = (Get-FileHash $BaselineResolved -Algorithm SHA256).Hash.ToLowerInvariant()
$ReceiptRoot = Join-Path $env:EVB_AUTHORITY_ROOT "evidence"
New-Item -ItemType Directory -Path $ReceiptRoot -Force | Out-Null
$ReceiptPath = Join-Path $ReceiptRoot "baseline_receipt.v1.json"
$ReceiptShaPath = Join-Path $ReceiptRoot "baseline_receipt.v1.sha256"
if ((Test-Path $ReceiptPath) -or (Test-Path $ReceiptShaPath)) { throw "baseline receipt already exists" }
$ReceiptWithoutHash = [ordered]@{ schema_version="evb.baseline-receipt/v1"; baseline_relative_path=$BaselineRelative; baseline_sha256=$env:EVB_BASELINE_SHA256; baseline_schema_version=$BaselineDoc.schema_version; source_inventory_sha256=$BaselineDoc.source_inventory_sha256 }
$ReceiptCanonical = $ReceiptWithoutHash | ConvertTo-Json -Depth 6 -Compress
$ReceiptHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($ReceiptCanonical))).ToLowerInvariant()
$Receipt = [ordered]@{}; $ReceiptWithoutHash.GetEnumerator() | ForEach-Object { $Receipt[$_.Key]=$_.Value }; $Receipt["receipt_sha256"]=$ReceiptHash
$ReceiptJson = $Receipt | ConvertTo-Json -Depth 6 -Compress
$ReceiptStream = [IO.File]::Open($ReceiptPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $Bytes=[Text.UTF8Encoding]::new($false).GetBytes($ReceiptJson); $ReceiptStream.Write($Bytes,0,$Bytes.Length); $ReceiptStream.Flush($true) } finally { $ReceiptStream.Dispose() }
$ShaStream = [IO.File]::Open($ReceiptShaPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $Bytes=[Text.Encoding]::ASCII.GetBytes($ReceiptHash); $ShaStream.Write($Bytes,0,$Bytes.Length); $ShaStream.Flush($true) } finally { $ShaStream.Dispose() }
$RunLocatorRoot = Join-Path $env:LOCALAPPDATA "EVB-runs/1999Search/2026-07-11-eventname-voice-binding-recovery"
New-Item -ItemType Directory -Path $RunLocatorRoot -Force | Out-Null
$RunLocatorPath = Join-Path $RunLocatorRoot "run_locator.v1.json"
$RunLocatorShaPath = Join-Path $RunLocatorRoot "run_locator.v1.sha256"
if ((Test-Path $RunLocatorPath) -or (Test-Path $RunLocatorShaPath)) { throw "EVB run locator already exists; resume it instead of recapturing" }
$LocatorWithoutHash = [ordered]@{ schema_version="evb.run-locator/v1"; run_id="2026-07-11-eventname-voice-binding-recovery"; authority_root=$env:EVB_AUTHORITY_ROOT; authority_manifest_sha256=$env:EVB_AUTHORITY_SHA256; execution_root=$ExecutionRoot; baseline_receipt_path=$ReceiptPath; baseline_receipt_sha256=$ReceiptHash }
$LocatorCanonical = $LocatorWithoutHash | ConvertTo-Json -Depth 6 -Compress
$LocatorHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($LocatorCanonical))).ToLowerInvariant()
$Locator = [ordered]@{}; $LocatorWithoutHash.GetEnumerator() | ForEach-Object { $Locator[$_.Key]=$_.Value }; $Locator["locator_sha256"]=$LocatorHash
$LocatorJson = $Locator | ConvertTo-Json -Depth 6 -Compress
$LocatorStream = [IO.File]::Open($RunLocatorPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $Bytes=[Text.UTF8Encoding]::new($false).GetBytes($LocatorJson); $LocatorStream.Write($Bytes,0,$Bytes.Length); $LocatorStream.Flush($true) } finally { $LocatorStream.Dispose() }
$LocatorShaStream = [IO.File]::Open($RunLocatorShaPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $Bytes=[Text.Encoding]::ASCII.GetBytes($LocatorHash); $LocatorShaStream.Write($Bytes,0,$Bytes.Length); $LocatorShaStream.Flush($true) } finally { $LocatorShaStream.Dispose() }
```
- [ ] **Step 5: Real acceptance `R01`.** Compare generated hashes to direct raw/dev inventory reads; any mismatch is `F01` and stops all later tasks.
- [ ] **Step 6: Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-0"
$TaskFiles = @("src/huiji_rag/models.py", "src/huiji_rag/source.py", "src/huiji_rag/io.py", "scripts/capture_evb_baseline.py", "tests/test_evb_baseline.py", "tests/test_evb_source.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-0 commit safe files" { & git commit -m "feat: capture immutable EVB baseline evidence" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-0 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 1: Restore Builder, Normalizer, and Versioned Build Paths

**Files:**

- Create: `src/huiji_rag/normalizer.py`
- Create: `src/huiji_rag/builder.py`
- Modify: `src/huiji_rag/models.py`
- Modify: `src/huiji_rag/io.py`
- Create: `scripts/build_huiji_evb.py`
- Create: `tests/test_evb_normalizer.py`
- Create: `tests/test_evb_builder.py`
- Create: `tests/fixtures/evb/baseline.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/preflight_bundle_manifest.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/source_inventory.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/dev_inventory.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/minio_before.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/milvus_before.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/vector_capacity.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/vector_acl.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/vector_owner.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/runtime_preflight.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/deployment_inventory.v1.json`
- Create: `tests/fixtures/evb/preflight_bundle/active_pointer_before.v1.json`

**Interfaces:**

```text
LANGUAGE_ALIASES: dict[str, tuple[str, str]]
normalize_language(value: str) -> tuple[str, str]
expected_voice_filename(raw_event_name: str, language: str) -> str
ascii_filename_key(basename: str) -> str
validate_safe_id(value: str, field: str) -> str
evb_build_paths(processed_root: Path, build_version: str) -> EvbBuildPaths
EvbBuilder.build_offline(self, request: BuildRequest) -> BuildResult
```

Implementation skeleton must use the exact language map `zh/cn/zh-cn -> (zh,Zh)`, `en/en-us -> (en,En)`, `jp/ja/ja-jp -> (jp,Jp)`, `kr/ko/ko-kr -> (kr,Kr)`, and `tw/zh-tw/zh_hant/zh-hant -> (zh-hant,Tw)`. `ascii_filename_key()` lowercases only ASCII `A-Z` after NFC.

```python
def expected_voice_filename(raw_event_name: str, language: str) -> str:
    canonical, prefix = normalize_language(language)
    event_name = validate_event_name(unicodedata.normalize("NFC", raw_event_name))
    return f"{prefix}_{event_name}.mp3"

def ascii_filename_key(basename: str) -> str:
    normalized = unicodedata.normalize("NFC", basename)
    return "".join(chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in normalized)
```

**Spec IDs:** `EVB-SCOPE-P0-01..04`, `EVB-NAME-P0-01..05`, `EVB-BUILD-P0-01..03`, `EVB-SEC-P0-01`, `EVB-SEC-P0-05`.

**Failure manifestation:** `F01`/`F04`; unsafe paths, dev writes, or non-equivalent canonical projection block the build.

**Expected:** RED on missing normalizer/builder and unsafe path cases; GREEN when focused tests and `C14` pass. **Real acceptance:** `R01` and `R04`.

- [ ] **Step 1: Add named RED tests.** `test_validate_safe_id_rejects_separator_colon_dot_and_controls`, `test_expected_voice_filename_uses_exact_prefix_nfc_and_mp3`, `test_ascii_filename_key_does_not_unicode_casefold`, `test_zh_hant_aliases_only_use_tw`, `test_evb_build_paths_are_contained_and_reject_dev`, and `test_builder_never_imports_pyc_or_mutation_clients` define the builder boundary.
- [ ] **Step 2: Run `Invoke-ExpectedNativeFailure "builder focused RED" { & $Python -m pytest tests/test_evb_builder.py -q } "ImportError|ModuleNotFoundError|AttributeError"`; record the expected missing-API RED.**
- [ ] **Step 3: Implement the exact public contracts and `offline` parser.** `EvbBuilder.build_offline(request: BuildRequest) -> BuildResult` may call source/binding/artifact collaborators only; `offline` requires baseline and preflight-bundle path/hash pairs plus safe build version and output/report root. It rejects `dev`, stale/reused evidence, missing expected hash, or bundle-sidecar mismatch before constructing external clients; build manifest stores the exact baseline SHA-256.
- [ ] **Step 4: Rerun focused tests; expected PASS.** Hash `tests/fixtures/evb/baseline.v1.json` into `$env:EVB_FAKE_BASELINE_SHA256` and `tests/fixtures/evb/preflight_bundle/preflight_bundle_manifest.v1.json` into `$env:EVB_FAKE_PREFLIGHT_BUNDLE_SHA256`, then run `C14`; expected dry-run artifacts only under `eval/evb_fake_build`.
- [ ] **Step 5: Real acceptance `R01`.** Resolve every generated/read path and prove containment; compare canonical non-media projection hash with dev.
- [ ] **Step 6: Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-1"
$TaskFiles = @("src/huiji_rag/normalizer.py", "src/huiji_rag/builder.py", "src/huiji_rag/models.py", "src/huiji_rag/io.py", "scripts/build_huiji_evb.py", "tests/test_evb_normalizer.py", "tests/test_evb_builder.py", "tests/fixtures/evb/baseline.v1.json", "tests/fixtures/evb/preflight_bundle/preflight_bundle_manifest.v1.json", "tests/fixtures/evb/preflight_bundle/source_inventory.v1.json", "tests/fixtures/evb/preflight_bundle/dev_inventory.v1.json", "tests/fixtures/evb/preflight_bundle/minio_before.v1.json", "tests/fixtures/evb/preflight_bundle/milvus_before.v1.json", "tests/fixtures/evb/preflight_bundle/vector_capacity.v1.json", "tests/fixtures/evb/preflight_bundle/vector_acl.v1.json", "tests/fixtures/evb/preflight_bundle/vector_owner.v1.json", "tests/fixtures/evb/preflight_bundle/runtime_preflight.v1.json", "tests/fixtures/evb/preflight_bundle/deployment_inventory.v1.json", "tests/fixtures/evb/preflight_bundle/active_pointer_before.v1.json")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-1 commit safe files" { & git commit -m "feat: restore isolated EVB builder foundations" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-1 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 2: Implement Exact eventName Voice Binding

**Files:**

- Create: `src/huiji_rag/voice_binding.py`
- Modify: `src/huiji_rag/models.py`
- Modify: `src/huiji_rag/media.py`
- Create: `tests/test_evb_voice_binding.py`
- Modify: `tests/test_huiji_models.py`

**Interfaces:**

```text
class BindingStatus(str, Enum):
    EXACT = "exact"
    SHORTFALL = "shortfall"
    QUARANTINED = "quarantined"
    FATAL = "fatal"
    NOT_APPLICABLE = "not_applicable"

index_voice_resources(rows: Iterable[ResourceRow]) -> VoiceResourceIndex
bind_voice_row(source: VoiceSourceRow, index: VoiceResourceIndex) -> BindingRecord
BindingRecord.from_match(source: VoiceSourceRow, expected_filename: str, matches: Sequence[ResourceRow], status: BindingStatus) -> BindingRecord
media_id_for_sha1(sha1: str) -> str  # returns "media:sha1:" + sha1
```

```python
def bind_voice_row(source: VoiceSourceRow, index: VoiceResourceIndex) -> BindingRecord:
    language, _prefix = normalize_language(source.language)
    expected = expected_voice_filename(source.event_name, language)
    matches = index.get((language, ascii_filename_key(expected)), ())
    distinct = {item.sha256 for item in matches}
    status = BindingStatus.SHORTFALL if not distinct else BindingStatus.EXACT
    if len(distinct) > 1:
        status = BindingStatus.FATAL
    return BindingRecord.from_match(source, expected, matches, status)
```

**Spec IDs:** `EVB-IDENT-P0-01..03`, `EVB-NAME-P0-01..05`, `EVB-BIND-P0-01..06`, `EVB-ARTIFACT-P0-06`, `EVB-GATE-P0-01..03`.

**Failure manifestation:** `F02`; any guessed, cross-language, non-exact, or truncated-ID association is red.

**Expected:** RED on current guessed/truncated behavior; GREEN when `C02` passes. **Real acceptance:** `R02`.

- [ ] **Step 1: Add named table-driven RED tests.** `test_binding_uses_exact_ascii_insensitive_full_basename`, `test_binding_does_not_unicode_fold_suffix_title_or_substring`, `test_zero_match_is_shortfall_and_distinct_sha_is_fatal`, `test_binding_never_crosses_language_or_borrows_zh_for_tw`, `test_skin_event_name_not_audio_suffix_is_authority`, and `test_media_id_uses_full_sha1_protocol` define exact binding.
- [ ] **Step 2: Run `C02`; expected failure** because binding APIs do not exist and current `media_id_for_sha1()` truncates the SHA.
- [ ] **Step 3: Implement `index_voice_resources`, `bind_voice_row`, `BindingRecord.from_match`, and `media_id_for_sha1`.** Construct `Prefix_rawEventName.mp3`, look up only the canonical language/full ASCII key, retain evidence, and emit no fallback.
- [ ] **Step 4: Run `C02` and `Invoke-NativeChecked "models GREEN" { & $Python -m pytest tests/test_huiji_models.py -q }`; expected PASS.**
- [ ] **Step 5: Real acceptance `R02`.** Run read-only classification across all current voice records; report exact/shortfall/fatal candidates dynamically and inspect deterministic samples from each existing class.
- [ ] **Step 6: Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-2"
$TaskFiles = @("src/huiji_rag/voice_binding.py", "src/huiji_rag/models.py", "src/huiji_rag/media.py", "tests/test_evb_voice_binding.py", "tests/test_huiji_models.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-2 commit safe files" { & git commit -m "feat: bind voice resources by exact eventName" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-2 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 3: Implement Deterministic Conflict Closure and Stop Semantics

**Files:**

- Create: `src/huiji_rag/diagnostics.py`
- Modify: `src/huiji_rag/models.py`
- Create: `tests/test_evb_diagnostics.py`
- Modify: `scripts/diagnose_huiji_artifacts.py`

**Interfaces:**

```text
transcript_sha256(text: str | None) -> str
classify_binding_conflicts(rows: Sequence[BindingRecord]) -> ConflictResult
expand_conflict_closure(seed_ids: set[str], corpus: Sequence[BindingRecord]) -> ConflictClosure
should_stop_mutations(result: ConflictResult) -> bool
```

`expand_conflict_closure()` must repeatedly add rows sharing entity, eventName, expected filename, SHA, object key, language, or naming family until one pass adds zero rows; output sorted IDs, per-round counts, visited dimensions, and closure SHA-256.

```python
visited = set(seed_ids)
while True:
    shared_values = collect_closure_values(visited, corpus_by_id)
    expanded = visited | rows_sharing_any_value(shared_values, corpus)
    if expanded == visited:
        break
    round_counts.append(len(expanded) - len(visited))
    visited = expanded
```

**Spec IDs:** `EVB-DIAG-P0-01..06`, `EVB-BIND-P0-02..03`, `EVB-ARTIFACT-P0-06..07`, `EVB-OBS-P0-02`, `EVB-GATE-P0-04`.

**Failure manifestation:** `F03`; incomplete closure, continued writes after fatal, or runtime quarantine leakage is red.

**Expected:** RED on missing closure APIs; GREEN when `C03` passes. **Real acceptance:** `R03`.

- [ ] **Step 1: Add named RED conflict tests.** `test_zero_exact_is_shortfall_and_multiple_sha_is_fatal`, `test_same_sha_different_event_and_text_is_quarantined`, `test_cross_child_is_trigger_then_classified`, `test_closure_recurses_to_fixed_point_with_hash`, `test_fatal_stops_mutations_but_finishes_read_only_closure`, and `test_runtime_projection_excludes_quarantine` define deterministic stop/diagnosis behavior.
- [ ] **Step 2: Run `C03`; expected import failures.**
- [ ] **Step 3: Implement `transcript_sha256`, `classify_binding_conflicts`, `expand_conflict_closure`, and `should_stop_mutations`.** Mutation decisions remain separate from diagnosis so fatal stops writes immediately while closure traverses immutable indexes to fixed point.
- [ ] **Step 4: Run `C03`; expected PASS.**
- [ ] **Step 5: Real acceptance `R03`.** Derive the current cross-child class solely from the captured before inventory, prove every observed occurrence is listed, and verify no mutation client is instantiated.
- [ ] **Step 6: Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-3"
$TaskFiles = @("src/huiji_rag/diagnostics.py", "src/huiji_rag/models.py", "scripts/diagnose_huiji_artifacts.py", "tests/test_evb_diagnostics.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-3 commit safe files" { & git commit -m "feat: add deterministic EVB conflict closure" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-3 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 4: Build v2 Artifacts, Legacy Adapter, and BM25 Parity

**Files:**

- Create: `src/huiji_rag/artifacts.py`
- Modify: `src/huiji_rag/io.py`
- Modify: `src/huiji_rag/builder.py`
- Modify: `src/rag/sparse.py`
- Create: `tests/test_evb_artifacts.py`
- Modify: `tests/test_sparse_bm25.py`

**Interfaces:**

```text
MEDIA_ASSET_V2_FIELDS: Sequence[str]
adapt_legacy_media_row(row: Mapping[str, object]) -> dict[str, object]
build_binding_inventory(rows: Iterable[BindingRecord]) -> Iterator[dict[str, object]]
build_entity_name_directory(parent_rows: Iterable[Mapping[str, object]]) -> EntityNameDirectory
build_runtime_media_projection(nonvoice_rows, binding_rows, entity_names: EntityNameDirectory, public_base_url: str, bucket_name: str) -> Iterator[dict[str, object]]
write_media_artifacts(paths: EvbBuildPaths, artifacts: MediaArtifacts) -> ArtifactManifest
canonical_child_corpus_sha256(rows: Iterable[Mapping[str, object]]) -> str
```

**Spec IDs:** `EVB-ARTIFACT-P0-01..13`, `EVB-PARITY-P0-01..02`, `EVB-BUILD-P0-01..03`, `EVB-BASELINE-P0-02..04`, `EVB-GATE-P0-12`, `EVB-GATE-P0-16`.

**Failure manifestation:** `F04`; schema/parity drift, dev mutation, or non-consumable runtime rows block promotion.

**Expected:** RED on missing v2 writer/parity checks; GREEN when `C04` and `C14` pass. **Real acceptance:** `R04`.

- [ ] **Step 1: Add named RED schema/parity tests.** `test_v2_schema_has_exact_fields_and_internal_visibility`, `test_binding_inventory_contains_all_statuses`, `test_runtime_projection_contains_exact_voice_and_not_applicable_nonvoice_only`, `test_legacy_adapter_maps_every_named_v1_field`, `test_nonvoice_projection_is_canonically_equivalent`, `test_media_ids_remain_full_sha1`, `test_entity_name_directory_uses_canonical_parents_and_rejects_conflicts`, `test_runtime_projection_excludes_exact_binding_without_authoritative_entity_name`, `test_runtime_projection_uses_canonical_entity_identity`, and `test_regenerated_bm25_semantic_corpus_hash_matches` define artifacts.
- [ ] **Step 2: Run `C04`; expected missing artifact module and schema failures.**
- [ ] **Step 3: Implement the listed artifact/parity interfaces.** Write runtime v2 JSONL/schema/manifest, diagnostic inventory, parent/child artifacts, and regenerated BM25 only under the isolated root; reject shortfall/quarantine/fatal before runtime serialization.
- [ ] **Step 3a: Enforce approved entity-name authority.** Build `EntityNameDirectory(entries, conflicts)` only from canonical parent/entity rows. Conflicting values do not abort read-only diagnosis: they are excluded from `entries`, retained in `conflicts`, and affected exact bindings receive `entity_name_exclusion:conflicting_canonical_names`. Missing/blank entries receive their own exclusion. Output identity comes only from `entries`, never legacy media attachment or filename/title/URL inference.
- [ ] **Step 3b: Exercise the real C14 CLI path.** The hash-pinned fake preflight bundle includes `artifact_fixture.v1.json` (`evb.artifact-fixture/v1`). When that optional sidecar is present on `offline --dry-run`, `EvbBuilder.build_offline()` must parse it through typed source/resource records and write runtime v2, diagnostic inventory, schema, parent/child, regenerated BM25, media manifest, build manifest, and build report under the fresh isolated root. C14 fails if only the two foundation manifests are emitted.
- [ ] **Step 4: Run `C04`; expected PASS.** Run `C14`; expected v2 manifest hashes and zero non-consumable runtime voice rows.
- [ ] **Step 5: Real acceptance `R04`.** Compare current dev and isolated projection/corpus fingerprints, derive the complete media-ID compatibility inventory dynamically from current artifacts, and prove dev timestamps/hashes unchanged.
- [ ] **Step 6: Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-4"
$TaskFiles = @("src/huiji_rag/artifacts.py", "src/huiji_rag/io.py", "src/huiji_rag/builder.py", "src/rag/sparse.py", "tests/test_evb_artifacts.py", "tests/test_sparse_bm25.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-4 commit safe files" { & git commit -m "feat: emit versioned EVB artifacts with parity gates" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-4 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 5: Implement Strict Additive MinIO Conditional Create

**Files:**

- Create: `src/huiji_rag/minio_strict.py`
- Modify: `src/huiji_rag/builder.py`
- Modify: `scripts/build_huiji_evb.py`
- Modify: `requirements.txt`
- Create: `tests/test_evb_minio_strict.py`
- Modify: `tests/test_minio_shared_upload.py`
- Read only: `src/assets/minio_store.py`

**Interfaces:**

```text
@dataclass(frozen=True)
class StrictObjectRequest:
    bucket: str
    object_key: str
    local_path: Path
    sha1: str
    sha256: str
    size: int
    content_type: str
    asset_type: str
    suffix: str

class StrictMinioUploader:
    capability_preflight(self, before_inventory: Path) -> CapabilityEvidence
    create_operation_plan(self, baseline_path: Path, expected_baseline_sha256: str, build_manifest_path: Path, expected_build_manifest_sha256: str, preflight_bundle_path: Path, expected_preflight_bundle_sha256: str, before_inventory_path: Path, expected_before_inventory_sha256: str, requests: Sequence[StrictObjectRequest], output: Path) -> MinioOperationPlan
    conditional_create(self, plan: MinioOperationPlan, request: StrictObjectRequest, operation_id: UUID) -> ObjectEvidence
    verify_readback(self, request: StrictObjectRequest) -> ObjectEvidence
attach_operation_evidence(evidence: ObjectEvidence, operation_id: str, version_id: str | None) -> ObjectEvidence
load_and_claim_operation_plan(path: Path, expected_sha256: str, current_inventory: ObjectInventory) -> MinioOperationPlan
validate_planned_request(plan: MinioOperationPlan, request: StrictObjectRequest, operation_id: UUID) -> None
map_s3_error(error: S3Error) -> Literal["concurrency_conflict", "blocked", "failed"]
```

```python
def conditional_create(self, plan: MinioOperationPlan, request: StrictObjectRequest, operation_id: UUID) -> ObjectEvidence:
    self._capabilities.require_conditional_create_and_app_audit()
    validate_planned_request(plan, request, operation_id)
    body = request.local_path.read_bytes()
    response = self._minio._execute(
        method="PUT",
        bucket_name=request.bucket,
        object_name=request.object_key,
        body=body,
        headers={
            "If-None-Match": "*",
            "Content-Type": request.content_type,
            "x-amz-meta-evb-operation-id": str(operation_id),
        },
    )
    evidence = self.verify_readback(request)
    return attach_operation_evidence(
        evidence,
        operation_id=str(operation_id),
        version_id=response.headers.get("x-amz-version-id"),
    )
```

For EVB, `Minio._execute(method="PUT", bucket_name, object_name, body: bytes, headers)` in `minio==7.2.20` is the only object write transport. The local byte read makes source containment and size/hash verification mandatory before `_execute`. It extracts `ETag`, nullable `x-amz-version-id`, and `x-amz-request-id` from response headers. `PreconditionFailed` and `ConditionalRequestConflict` map to `concurrency_conflict`; `AccessDenied`, `NotImplemented`, and unknown `S3Error` values map to blocked/failed. Every mapped error stops subsequent writes and expands read-only diagnostics. Readback SHA-1/SHA-256/size mismatch is fatal. `MinioAssetStorage` and public `put_object`/`fput_object` are forbidden.

**Spec IDs:** `EVB-STORE-P0-01..09`, `EVB-DIAG-P0-01`, `EVB-SEC-P0-01..03`, `EVB-GATE-P0-05..06`, `EVB-GATE-P0-14`.

**Failure manifestation:** `F05`; unsupported conditional create/audit, ordinary PUT, setup mutation, mismatch, or failed readback stops writes.

**Expected:** RED on missing strict uploader and forbidden calls; GREEN when `C05` passes. **Real acceptance:** `R05` preflight, then Task 14 controlled upload.

- [ ] **Transport RED test.** Add `test_execute_put_uses_bytes_and_required_headers` with key assertions:

```python
assert call.kwargs["method"] == "PUT"
assert isinstance(call.kwargs["body"], bytes)
assert call.kwargs["headers"]["If-None-Match"] == "*"
assert call.kwargs["headers"]["x-amz-meta-evb-operation-id"] == str(operation_id)
```

- [ ] **Transport RED command.** Run `Invoke-ExpectedNativeFailure "MinIO transport RED" { & $Python -m pytest tests/test_evb_minio_strict.py::test_execute_put_uses_bytes_and_required_headers -q } "ImportError|AttributeError|AssertionError"`; expected named test failure.
- [ ] **Transport minimal implementation.** Pin `minio==7.2.20`; implement `conditional_create(self, plan, request, operation_id) -> ObjectEvidence` using only `_execute(method="PUT", bucket_name=request.bucket, object_name=request.object_key, body=request.local_path.read_bytes(), headers=required_headers)` and response header extraction.
- [ ] **Transport GREEN command.** Run `Invoke-NativeChecked "MinIO transport GREEN" { & $Python -m pytest tests/test_evb_minio_strict.py::test_execute_put_uses_bytes_and_required_headers -q }`.

- [ ] **Operation-plan RED test.** Add `test_operation_plan_hash_and_claim_are_immutable` with `assert plan.operation_plan_sha256 == canonical_hash_without(plan, "operation_plan_sha256")`, `assert plan.used_by_operation_id is None`, and, after the first claim, `with pytest.raises(EvidenceAlreadyUsed): load_and_claim_operation_plan(plan_path, plan.operation_plan_sha256, unchanged_inventory)`.
- [ ] **Operation-plan RED command.** Run `Invoke-ExpectedNativeFailure "MinIO plan RED" { & $Python -m pytest tests/test_evb_minio_strict.py::test_operation_plan_hash_and_claim_are_immutable -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Operation-plan minimal implementation.** Implement `StrictMinioUploader.create_operation_plan(self, baseline_path: Path, expected_baseline_sha256: str, build_manifest_path: Path, expected_build_manifest_sha256: str, preflight_bundle_path: Path, expected_preflight_bundle_sha256: str, before_inventory_path: Path, expected_before_inventory_sha256: str, requests: Sequence[StrictObjectRequest], output: Path) -> MinioOperationPlan` with create-new write, exact input hashes and sorted object set; implement `load_and_claim_operation_plan(path: Path, expected_sha256: str, current_inventory: ObjectInventory) -> MinioOperationPlan` with exact inventory revalidation and create-new `minio_operation_plan.use.v1.json`.
- [ ] **Operation-plan GREEN command.** Run `Invoke-NativeChecked "MinIO plan GREEN" { & $Python -m pytest tests/test_evb_minio_strict.py::test_operation_plan_hash_and_claim_are_immutable -q }`.

- [ ] **Uploader stop/readback RED test.** Add `test_uploader_stops_after_conflict_and_requires_hash_readback` with `assert fake.execute_calls == 1`, `assert report.status == "concurrency_conflict"`, and `with pytest.raises(ContentHashMismatch): uploader.verify_readback(request)`.
- [ ] **Uploader stop/readback RED command.** Run `Invoke-ExpectedNativeFailure "MinIO stop RED" { & $Python -m pytest tests/test_evb_minio_strict.py::test_uploader_stops_after_conflict_and_requires_hash_readback -q } "AssertionError|AttributeError"`.
- [ ] **Uploader stop/readback minimal implementation.** Implement `map_s3_error`, stop-token propagation across the planned sequence, HTTP readback SHA-1/SHA-256/size verification, and immutable evidence with ETag/version/request/application IDs; no fallback transport or `MinioAssetStorage` construction.
- [ ] **Uploader stop/readback GREEN command.** Run `Invoke-NativeChecked "MinIO stop GREEN" { & $Python -m pytest tests/test_evb_minio_strict.py::test_uploader_stops_after_conflict_and_requires_hash_readback -q }`.

- [ ] **CLI RED test.** Add `test_minio_cli_requires_all_expected_hashes_before_client` with `assert result.exit_code == 2`, `assert "--expected-build-manifest-sha256" in result.stderr`, and `assert fake_client_factory.calls == []` for each omitted expected hash.
- [ ] **CLI RED command.** Run `Invoke-ExpectedNativeFailure "MinIO CLI RED" { & $Python -m pytest tests/test_evb_minio_strict.py::test_minio_cli_requires_all_expected_hashes_before_client -q } "AssertionError|SystemExit"`.
- [ ] **CLI minimal implementation.** Add `minio-plan` and `minio-upload` parsers exactly as `C19/C20`; validate path/hash pairs before client construction and return only documented exit codes.
- [ ] **CLI GREEN command.** Run `Invoke-NativeChecked "MinIO CLI GREEN" { & $Python -m pytest tests/test_evb_minio_strict.py::test_minio_cli_requires_all_expected_hashes_before_client -q }`, then `C05` and `C14`.
- [ ] **Step 6: Real acceptance `R05` preflight only.** Generate and hash the immutable operation plan from current missing objects without upload; independently verify SDK version, conditional-create semantics, operation-ID audit correlation, bucket/prefix, exact key/hash/size set, source containment, and before inventory. Any change blocks `C20`.
- [ ] **Step 7: Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-5"
$TaskFiles = @("src/huiji_rag/minio_strict.py", "src/huiji_rag/builder.py", "scripts/build_huiji_evb.py", "requirements.txt", "tests/test_evb_minio_strict.py", "tests/test_minio_shared_upload.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-5 commit safe files" { & git commit -m "feat: add strict conditional MinIO uploader" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-5 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 6: Migrate Runtime Registry, Voice Pagination, and Public API Safety

**Files:**

- Modify: `src/assets/huiji_registry.py`
- Modify: `src/assets/voice_pagination.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Create: `tests/test_evb_runtime_registry.py`
- Modify: `tests/test_huiji_media_registry.py`
- Modify: `tests/test_voice_pagination.py`
- Modify: `tests/test_sse.py`

**Interfaces:**

```text
load_active_media_artifacts(cfg: Config, pointer: ActiveBuildPointer) -> LoadedMediaArtifacts
HuijiMediaRegistry.from_artifacts(cfg: Config, artifacts: LoadedMediaArtifacts) -> HuijiMediaRegistry
HuijiMediaRegistry.health_payload() -> dict[str, object]
VoicePaginationIndex(records, transcripts, build_version, activation_epoch)
sanitize_public_media(row: Mapping[str, object]) -> dict[str, object]
```

**Spec IDs:** `EVB-RUNTIME-P0-01..05`, `EVB-PAGE-P0-01..05`, `EVB-ARTIFACT-P0-03..05`, `EVB-ARTIFACT-P0-07..11`, `EVB-GATE-P0-10..11`.

**Failure manifestation:** `F06`; inference, unsafe/public internal fields, duplicate media, pagination drift, or stale cursor acceptance is red.

**Expected:** RED on legacy path loading, absent epoch/zh-hant support, or duplicate compatibility rendering; GREEN when `C06` and `C06F` pass. **Real acceptance:** `R06`.

- [ ] **Step 1: Write named RED runtime tests.** `test_loader_branches_v1_legacy_and_v2_from_pointer`, `test_registry_rejects_quarantine_fatal_and_filename_inference`, `test_public_voice_payload_excludes_internal_fields`, `test_voice_page_contract_size_order_title_replay_and_uniqueness`, `test_first_page_compatibility_assets_are_current_page_only`, and `test_cursor_build_or_epoch_mismatch_is_409` cover the complete runtime contract.
- [ ] **Step 2: Run `C06`; expected failures** because registry reads `build_paths(cfg).media_assets`, has no v2 pointer branch, and pagination lacks `zh-hant`/activation epoch.
- [ ] **Step 3: Implement artifact-only runtime consumption.** Preserve non-voice behavior, keep internal fields in loaded rows, and serialize only the public allowlist. Never read diagnostic inventory or raw resources at runtime.
- [ ] **Step 4: Run `C06`; expected GREEN.** Run read-only `C06F` without editing any frontend file. If `C06F` fails, write `eval/evb_contract_conflicts/frontend_compatibility.v1.json` with command, output SHA-256, backend contract SHA-256, and failing test names; block activation and hand the conflict to the Wiki owner.
- [ ] **Step 5: Real acceptance `R06` read-only.** Start a runtime against a staged pointer, issue dynamic Ask/SSE and all cursors, scan JSON for internal keys/local paths, then test a cursor against a different staged build and require HTTP 409.
- [ ] **Step 6: Commit safe staged files only via Section 1.** Dirty/mixed `backend/main.py` or `backend/schemas.py` is `commit_deferred`; request user review and never stage its Wiki hunks.

```powershell
$TaskId = "task-6"
$TaskFiles = @("src/assets/huiji_registry.py", "src/assets/voice_pagination.py", "backend/schemas.py", "backend/main.py", "tests/test_evb_runtime_registry.py", "tests/test_huiji_media_registry.py", "tests/test_voice_pagination.py", "tests/test_sse.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-6 commit safe files" { & git commit -m "feat: consume safe versioned EVB runtime artifacts" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-6 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 7: Add Append-Only Shadow Name Registry and Dedicated Builder

**Files:**

- Create: `src/huiji_rag/vector_registry.py`
- Create: `src/huiji_rag/shadow_vectorstore.py`
- Create: `tests/test_evb_vector_registry.py`
- Create: `tests/test_evb_shadow_vectorstore.py`
- Modify: `tests/test_vectorstore.py`
- Read only: `src/rag/vectorstore.py`

**Interfaces:**

```text
canonical_record_sha256(record: Mapping[str, object]) -> str
ShadowNameRegistry.reserve(experiment_id: str, candidate_id: str, ownership_hashes: Mapping[str, str]) -> ShadowReservation
ShadowController.create_from_intent(intent: CollectionIntentManifest) -> CollectionIdentity
ShadowBuilder.build_dev(preflight: VectorPreflightPlan, intent: CollectionIntentManifest, rows: Sequence[Mapping[str, object]]) -> VectorBuildEvidence
create_lifecycle_operation_plan(candidate_root: Path, preflight: VectorPreflightPlan, intent: CollectionIntentManifest, evidence_path: Path, expected_evidence_sha256: str, reason: LifecycleReason, output: Path) -> LifecycleOperationPlan
ShadowLifecycle.finalize_lifecycle(plan_path: Path, expected_plan_sha256: str) -> LifecycleEvidence
finalize_collection_manifest(intent, build_evidence, evaluation_evidence) -> CollectionManifest
validate_mutation_authority(preflight: VectorPreflightPlan, intent: CollectionIntentManifest, active_now: CollectionInventory) -> MutationAuthority
claim_vector_intent(authority: MutationAuthority, output: Path) -> VectorIntentUseMarker
```

The reserve record computes `record_sha256` over canonical JSON after removing that field; genesis previous hash is 64 zeros. Name allocation and reserve are one locked append using the unique sequence plus 128-bit CSPRNG nonce: `evb_shadow_{sequence}_{nonce32hex}`.

```python
with registry.lock_exclusive():
    tail = registry.verify_hash_chain_and_recover_tail()
    sequence = tail.sequence + 1
    nonce32hex = secrets.token_hex(16)
    name = f"evb_shadow_{sequence}_{nonce32hex}"
    reservation = registry.append_reserve(sequence, name, experiment_id, candidate_id, ownership_hashes)
```

**Spec IDs:** `EVB-VECTOR-P0-01`, `EVB-VECTOR-P0-03..09`, `EVB-VECTOR-P0-17..19`, `EVB-VECTOR-P0-23..30`, `EVB-VECTOR-P0-32..33`, `EVB-SEC-P0-04..05`, `EVB-GATE-P0-07`, `EVB-GATE-P0-15`, `EVB-GATE-P0-18`.

**Failure manifestation:** `F07`; active/existing mutation, dangerous helper call, registry/manifest break, partial shadow, permission leak, or unload failure is red.

**Expected:** RED on missing dedicated builder and any forbidden-helper call; GREEN when `C07` passes. **Real acceptance:** `R07`.

- [ ] **Registry RED test.** Add `test_concurrent_reserve_has_one_winner` with `assert len(successes) == 1`, `assert failures[0].reason == "name_already_reserved"`, `assert reservation.collection_name == f"evb_shadow_{reservation.sequence}_{reservation.nonce_hex}"`, and `assert len(bytes.fromhex(reservation.nonce_hex)) == 16`. Add neighboring hash-chain, damaged-tail, middle-corruption, and no-reuse tests named in the task review checklist.
- [ ] **Registry RED command.** Run `Invoke-ExpectedNativeFailure "registry RED" { & $Python -m pytest tests/test_evb_vector_registry.py::test_concurrent_reserve_has_one_winner -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Registry minimal implementation.** Implement `canonical_record_sha256(record: Mapping[str, object]) -> str` by removing only `record_sha256`, and implement `ShadowNameRegistry.reserve(experiment_id: str, candidate_id: str, ownership_hashes: Mapping[str, str]) -> ShadowReservation` as one registry-lock append that allocates sequence plus `secrets.token_hex(16)`, writes the chained record durably, and never retries or reuses a name.
- [ ] **Registry GREEN command.** Run `Invoke-NativeChecked "registry GREEN" { & $Python -m pytest tests/test_evb_vector_registry.py::test_concurrent_reserve_has_one_winner -q }`.

- [ ] **Builder/security RED test.** Add `test_build_dev_requires_preflight_and_intent_hashes` with `with pytest.raises(EvidenceMismatch): builder.build_dev(changed_preflight, intent, rows)`, `assert fake_milvus.create_calls == []`, and monkeypatch `ensure_huiji_collection`, `build_huiji_vectorstore`, and `_delete_existing_entities` to raise in `test_shadow_builder_never_calls_existing_vector_helpers`.
- [ ] **Builder/security RED command.** Run `Invoke-ExpectedNativeFailure "shadow builder RED" { & $Python -m pytest tests/test_evb_shadow_vectorstore.py::test_build_dev_requires_preflight_and_intent_hashes tests/test_evb_shadow_vectorstore.py::test_shadow_builder_never_calls_existing_vector_helpers -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Builder/security minimal implementation.** Implement `validate_mutation_authority(preflight: VectorPreflightPlan, intent: CollectionIntentManifest, active_now: CollectionInventory) -> MutationAuthority`, `claim_vector_intent(authority: MutationAuthority, output: Path) -> VectorIntentUseMarker`, `ShadowController.create_from_intent(intent: CollectionIntentManifest) -> CollectionIdentity`, and `ShadowBuilder.build_dev(preflight: VectorPreflightPlan, intent: CollectionIntentManifest, rows: Sequence[Mapping[str, object]]) -> VectorBuildEvidence`. The controller creates the exact reserved name once; `AlreadyExists` and uncertain create results stop without retry, while every documented partial/failure exit writes immutable build evidence before returning.
- [ ] **Builder/security GREEN command.** Run `Invoke-NativeChecked "shadow builder GREEN" { & $Python -m pytest tests/test_evb_shadow_vectorstore.py::test_build_dev_requires_preflight_and_intent_hashes tests/test_evb_shadow_vectorstore.py::test_shadow_builder_never_calls_existing_vector_helpers -q }`.
- [ ] **Lifecycle RED test.** In `test_lifecycle_plan_and_unload_are_exactly_once`, assert `plan.collection_identity == built.identity`, `plan.reason == LifecycleReason.DEV_UNSELECTED`, `evidence.operation == "unload"`, and `with pytest.raises(EvidenceAlreadyUsed): lifecycle.finalize_lifecycle(plan_path, plan_sha)` on a second claim.
- [ ] **Lifecycle RED command.** Run `Invoke-ExpectedNativeFailure "lifecycle RED" { & $Python -m pytest tests/test_evb_shadow_vectorstore.py::test_lifecycle_plan_and_unload_are_exactly_once -q } "AssertionError|AttributeError"`.
- [ ] **Lifecycle minimal implementation.** Implement `create_lifecycle_operation_plan(candidate_root: Path, preflight: VectorPreflightPlan, intent: CollectionIntentManifest, evidence_path: Path, expected_evidence_sha256: str, reason: LifecycleReason, output: Path) -> LifecycleOperationPlan` and `ShadowLifecycle.finalize_lifecycle(plan_path: Path, expected_plan_sha256: str) -> LifecycleEvidence`; revalidate identity/evidence and permit Release/Unload only. The CLI writes exactly one immutable terminal lifecycle evidence document before returning success or failure. Unload failure blocks promotion/new candidate; delete/drop remain impossible.
- [ ] **Lifecycle GREEN command.** Run `Invoke-NativeChecked "lifecycle GREEN" { & $Python -m pytest tests/test_evb_shadow_vectorstore.py::test_lifecycle_plan_and_unload_are_exactly_once -q }`, then `C07`. Task 8 owns fake phase evidence; Task 14 alone invokes real cleanup.
- [ ] **Real acceptance `R07` preflight only.** Prove active inventory, exact-name registry, permission/proxy, owner-token, capacity, and lifecycle evidence without creating a collection.
- [ ] **Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-7"
$TaskFiles = @("src/huiji_rag/vector_registry.py", "src/huiji_rag/shadow_vectorstore.py", "tests/test_evb_vector_registry.py", "tests/test_evb_shadow_vectorstore.py", "tests/test_vectorstore.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-7 commit safe files" { & git commit -m "feat: add append-only EVB shadow builder" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-7 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 8: Freeze Experiments and Run End-to-End Vector A/B

**Files:**

- Create: `src/huiji_rag/vector_experiment.py`
- Create: `scripts/run_evb_vector_experiment.py`
- Create: `tests/test_evb_vector_experiment.py`
- Create: `tests/fixtures/evb/vector_pipeline.v1.json`
- Modify: `scripts/evaluate_huiji_rag.py`
- Modify: `tests/test_huiji_eval.py`

**Interfaces:**

```text
create_experiment_manifest(request: ExperimentRequest) -> ExperimentManifest
create_query_label_manifest(experiment: ExperimentManifest, exact_rows, curated_rows) -> QueryLabelEvidence
split_labels_by_entity(labels, seed: str) -> FrozenSplit
create_vector_preflight_plan(experiment: ExperimentManifest, active: CollectionInventory, capacity: CapacityEvidence, acl: AclEvidence, candidates: CandidateRegistry) -> VectorPreflightPlan
create_candidate_intent(preflight: VectorPreflightPlan, candidate_id: str, reservation: ShadowReservation) -> CollectionIntentManifest
run_dev_candidate(candidate: CandidateTuple, labels: FrozenSplit) -> ArmEvaluation
create_dev_evaluation_bundle(preflight: VectorPreflightPlan, registry: CandidateRegistry, dev_reports: Sequence[Path], output: Path) -> DevEvaluationBundleManifest
freeze_candidate(dev_bundle_path: Path, expected_dev_bundle_sha256: str) -> FrozenCandidate
create_held_out_execution_marker(frozen_path: Path, frozen_sha256: str, output: Path) -> HeldOutExecutionMarker
run_held_out_once(candidate: FrozenCandidate, labels: FrozenSplit) -> AcceptanceEvaluation
record_held_out_execution(candidate: FrozenCandidate, acceptance: AcceptanceEvaluation) -> FrozenCandidate
derive_lifecycle_plan(candidate: CandidateRecord, evidence_path: Path, expected_evidence_sha256: str, reason: LifecycleReason, output: Path) -> LifecycleOperationPlan
paired_entity_bootstrap(active, candidate, seed: str, iterations: int = 2000) -> BootstrapEvidence
```

```python
dev_results = [run_dev_candidate(candidate, frozen_split) for candidate in preregistered]
dev_bundle = create_dev_evaluation_bundle(preflight, registry, dev_report_paths, dev_bundle_path)
frozen = freeze_candidate(dev_bundle_path, sha256_file(dev_bundle_path))
if frozen.held_out_execution_count != 0:
    raise RuntimeError(f"held-out already executed for {frozen.candidate_id}")
marker = create_held_out_execution_marker(frozen.path, frozen.sha256, marker_path)
acceptance = run_held_out_once(frozen, frozen_split)
frozen = record_held_out_execution(frozen, acceptance)
```

**Spec IDs:** `EVB-VECTOR-P0-04..05`, `EVB-VECTOR-P0-13..22`, `EVB-VECTOR-P0-31`, `EVB-GATE-P0-20..22`.

**Failure manifestation:** `F08`; split leakage, reselection, second held-out run, statistical/operational red gate, or inconclusive evidence retains active.

**Expected:** RED on missing immutable experiment/evaluator APIs; GREEN when `C08` and `C15` pass. **Real acceptance:** `R08`.

- [ ] **Prepare RED test.** Add `test_prepare_writes_immutable_experiment_labels_split_registry_and_preflight` with `assert experiment.query_label_sha256 == sha256_file(label_path)`, `assert split.entity_groups.isdisjoint_across_partitions`, `assert split.template_groups.isdisjoint_across_partitions`, and `assert all(candidate.experiment_manifest_sha256 == experiment.sha256 for candidate in registry.candidates)`.
- [ ] **Prepare RED command.** Run `Invoke-ExpectedNativeFailure "vector prepare RED" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_prepare_writes_immutable_experiment_labels_split_registry_and_preflight -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Prepare minimal implementation.** Implement `create_experiment_manifest(request: ExperimentRequest) -> ExperimentManifest`, `create_query_label_manifest(experiment: ExperimentManifest, exact_rows: Sequence[BindingRow], curated_rows: Sequence[CuratedLabel]) -> QueryLabelEvidence`, `split_labels_by_entity(labels: QueryLabelEvidence, seed: str) -> FrozenSplit`, and `create_vector_preflight_plan(experiment: ExperimentManifest, active: CollectionInventory, capacity: CapacityEvidence, acl: AclEvidence, candidates: CandidateRegistry) -> VectorPreflightPlan`; all writes are create-new and hash-bound.
- [ ] **Prepare GREEN command.** Run `Invoke-NativeChecked "vector prepare GREEN" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_prepare_writes_immutable_experiment_labels_split_registry_and_preflight -q }`.

- [ ] **Dev A/B RED test.** Add `test_each_arm_embeds_query_with_its_own_complete_vector_tuple` with `assert active_embedder.calls == frozen_queries`, `assert candidate_embedder.calls == frozen_queries`, `assert active_arm.nonvector_fingerprint == candidate_arm.nonvector_fingerprint`, and `assert active_arm.vector_tuple != candidate_arm.vector_tuple`; add `test_dev_selects_only_passing_best_candidate` for balanced metrics and operational gates.
- [ ] **Dev A/B RED command.** Run `Invoke-ExpectedNativeFailure "vector dev RED" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_each_arm_embeds_query_with_its_own_complete_vector_tuple tests/test_evb_vector_experiment.py::test_dev_selects_only_passing_best_candidate -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Dev A/B minimal implementation.** Implement `run_dev_candidate(candidate: CandidateTuple, labels: FrozenSplit) -> ArmEvaluation` with each arm's own vector tuple/query embedder and shared frozen QueryPlan/BM25/RRF/reranker/allocator/budget/cursor settings; implement deterministic entity-clustered bootstrap and dev-only best passing candidate selection.
- [ ] **Dev A/B GREEN command.** Run `Invoke-NativeChecked "vector dev GREEN" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_each_arm_embeds_query_with_its_own_complete_vector_tuple tests/test_evb_vector_experiment.py::test_dev_selects_only_passing_best_candidate -q }`.
- [ ] **Dev-bundle RED test.** Add key assertions `assert set(bundle.candidate_ids) == set(registry.candidate_ids)`, `assert all(row.dev_report_sha256 for row in bundle.candidates)`, and `with pytest.raises(EvidenceMismatch): freeze_candidate(bundle_path, wrong_sha)`.
- [ ] **Dev-bundle RED command.** Run `Invoke-ExpectedNativeFailure "dev bundle RED" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_dev_bundle_covers_exact_registry_candidate_set -q } "AssertionError|AttributeError"`.
- [ ] **Dev-bundle minimal implementation.** Implement `create_dev_evaluation_bundle(preflight: VectorPreflightPlan, registry: CandidateRegistry, dev_reports: Sequence[Path], output: Path) -> DevEvaluationBundleManifest`, the `dev-bundle` parser, and `freeze_candidate(dev_bundle_path, expected_dev_bundle_sha256)`; enumerate only the immutable registry candidate set and never scan a root.
- [ ] **Dev-bundle GREEN command.** Run `Invoke-NativeChecked "dev bundle GREEN" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_dev_bundle_covers_exact_registry_candidate_set -q }`.

- [ ] **Freeze RED test.** Add `test_freeze_requires_dev_bundle_path_and_hash_and_never_scans_root` with `with pytest.raises(EvidenceMismatch): freeze_candidate(bundle_path, wrong_sha)`, `assert filesystem.scanned_directories == []`, and `assert frozen.candidate_id == expected_dev_winner`.
- [ ] **Freeze RED command.** Run `Invoke-ExpectedNativeFailure "vector freeze RED" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_freeze_requires_dev_bundle_path_and_hash_and_never_scans_root -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Freeze minimal implementation.** Implement `freeze_candidate(dev_bundle_path: Path, expected_dev_bundle_sha256: str) -> FrozenCandidate` as a create-new decision over only the complete dev bundle; it freezes one candidate or explicit no-candidate and never reads held-out labels or scans an experiment root.
- [ ] **Freeze GREEN command.** Run `Invoke-NativeChecked "vector freeze GREEN" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_freeze_requires_dev_bundle_path_and_hash_and_never_scans_root -q }`.

- [ ] **Held-out RED test.** Add `test_held_out_marker_precedes_first_request_and_is_exactly_once` with `assert call_log.index("marker_create_new") < call_log.index("first_query")`, `assert acceptance.candidate_id == frozen.candidate_id`, and `with pytest.raises(EvidenceAlreadyUsed): run_held_out_command(frozen_path, frozen_sha, marker_path)`; add failure/inconclusive assertions that no alternate candidate is selected.
- [ ] **Held-out RED command.** Run `Invoke-ExpectedNativeFailure "vector held-out RED" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_held_out_marker_precedes_first_request_and_is_exactly_once -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Held-out minimal implementation.** Implement `create_held_out_execution_marker(frozen_path: Path, frozen_sha256: str, output: Path) -> HeldOutExecutionMarker`, `run_held_out_once(candidate: FrozenCandidate, labels: FrozenSplit) -> AcceptanceEvaluation`, and `record_held_out_execution(candidate: FrozenCandidate, acceptance: AcceptanceEvaluation) -> FrozenCandidate`; claim before any request and terminate the experiment on red/inconclusive acceptance.
- [ ] **Held-out GREEN command.** Run `Invoke-NativeChecked "vector held-out GREEN" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_held_out_marker_precedes_first_request_and_is_exactly_once -q }`.

- [ ] **Parser RED test.** Add `test_vector_phase_parsers_require_every_path_hash_pair` and assert omitted expected hashes return `2` before filesystem/service access for `prepare`, `intent`, `build-dev`, `dev-bundle`, `freeze`, `held-out`, `lifecycle-plan`, and `finalize-lifecycle`; assert only `build-dev` and `finalize-lifecycle` can obtain mutation principals.
- [ ] **Parser RED command.** Run `Invoke-ExpectedNativeFailure "vector parser RED" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_vector_phase_parsers_require_every_path_hash_pair -q } "AssertionError|SystemExit"`.
- [ ] **Parser minimal implementation.** Add the exact parsers and exit codes from `C21..C25` and `C32..C35`; `prepare/intent/dev-bundle/freeze/held-out/lifecycle-plan` emit evidence only, `build-dev` returns `0/3/4/5` only after immutable build/failure evidence exists, and Task 14 alone invokes `finalize-lifecycle` for real cleanup.
- [ ] **Parser GREEN command.** Run `Invoke-NativeChecked "vector parser GREEN" { & $Python -m pytest tests/test_evb_vector_experiment.py::test_vector_phase_parsers_require_every_path_hash_pair -q }`, then `C08` and `C15`.
- [ ] **Real acceptance `R08` remains prepare-only until Task 14.** Generate immutable experiment/query-label/split/candidate-registry/preflight evidence and hashes; do not reserve a name or create a collection.
- [ ] **Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-8"
$TaskFiles = @("src/huiji_rag/vector_experiment.py", "scripts/run_evb_vector_experiment.py", "scripts/evaluate_huiji_rag.py", "tests/test_evb_vector_experiment.py", "tests/test_huiji_eval.py", "tests/fixtures/evb/vector_pipeline.v1.json")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-8 commit safe files" { & git commit -m "feat: add frozen EVB vector experiments" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-8 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 9: Implement Durable Active Pointer and Generation-0 Bootstrap

**Files:**

- Create: `src/huiji_rag/activation_models.py`
- Create: `src/huiji_rag/activation_store.py`
- Create: `tests/test_evb_activation_store.py`
- Modify: `src/huiji_rag/io.py`

**Interfaces:**

```text
ActivationTuple(build_version, build_manifest_sha256, milvus_collection_name, collection_schema_fingerprint, collection_manifest_sha256, embedding_model_id, embedding_config_fingerprint, artifact_schema_version)
ActiveBuildPointer(schema_version, generation, build_version, previous_build_version, build_manifest_sha256, milvus_collection_name, collection_schema_fingerprint, collection_manifest_sha256, embedding_model_id, embedding_config_fingerprint, artifact_schema_version, deployment_inventory_sha256, activation_epoch, activation_id, activated_at_utc)
ActiveBuildPointer.as_activation_tuple() -> ActivationTuple
PointerStore.bootstrap_dev(expected_inventory: RealBeforeInventory) -> ActiveBuildPointer
PointerStore.compare_and_swap(expected: ActiveBuildPointer, replacement: ActiveBuildPointer) -> ActiveBuildPointer
PointerStore.read_with_retry() -> ActiveBuildPointer
```

**Spec IDs:** `EVB-POINTER-P0-01..07`, `EVB-POINTER-P0-16..17`, `EVB-BUILD-P0-03`, `EVB-ARTIFACT-P0-09..11`, `EVB-GATE-P0-08`, `EVB-GATE-P0-16`.

**Failure manifestation:** `F09`; unsupported durability, incomplete tuple, fallback persistence, unsafe ID/path, or CAS mismatch is red.

**Expected:** RED on missing pointer/store APIs; GREEN when `C09` passes. **Real acceptance:** `R09` capability evidence.

- [ ] **Step 1: Add named RED durability/bootstrap tests.** `test_pointer_v1_has_exact_flat_fields_and_full_tuple_cas`, `test_bootstrap_generation_zero_captures_dev_legacy_and_current_collection`, `test_posix_replace_fsyncs_temp_and_parent`, `test_windows_replace_is_write_through_and_flushed`, `test_reader_observes_old_or_new_complete_pointer`, `test_pointer_paths_reject_unsafe_ids`, and `test_fallback_disables_after_bootstrap_ack` pin storage behavior.
- [ ] **Step 2: Run `C09`; expected missing activation types/store.**
- [ ] **Step 3: Implement `PointerStore.bootstrap_dev`, `compare_and_swap`, `read_with_retry`, and `ActiveBuildPointer.as_activation_tuple`.** Keep settings read-only; use the fixed processed-root pointer/lock, same-directory temp, platform durability adapters, full expected pointer/generation CAS, and injectable OS operations.
- [ ] **Step 4: Run `C09`; expected PASS.**
- [ ] **Step 5: Real acceptance `R01` read-only.** Validate configured dev, pinned inventory, collection manifest/model/config fingerprint, and durable-replacement capability; do not create generation 0 until Task 14.
- [ ] **Step 6: Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-9"
$TaskFiles = @("src/huiji_rag/activation_models.py", "src/huiji_rag/activation_store.py", "src/huiji_rag/io.py", "tests/test_evb_activation_store.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-9 commit safe files" { & git commit -m "feat: add durable EVB active pointer" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-9 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 10: Add Coordinator, Journal, Immutable Targets, and Authenticated Acks

**Files:**

- Modify: `src/huiji_rag/activation_models.py`
- Modify: `src/huiji_rag/activation_store.py`
- Modify: `tests/test_evb_activation_store.py`
- Create: `scripts/activate_evb_build.py`
- Create: `tests/fixtures/evb/activation_pipeline.v1.json`

**Interfaces:**

```text
ActivationCoordinator.acquire(owner_id: str) -> CoordinatorLease
ActivationCoordinator.run(request: ActivationRequest, operation: Callable[[CoordinatorLease], ActivationResult]) -> ActivationResult
AuthorizationStore.validate_and_claim(request: ActivationRequest, lease: CoordinatorLease) -> AuthorizationUseMarker
DeploymentStore.create_snapshot(source: Path) -> DeploymentSnapshot
ActivationTargetStore.create_targets(snapshot: DeploymentSnapshot, transaction_id: str) -> ActivationTargets
TransactionStore.create(request: ActivationRequest, lease: CoordinatorLease, snapshot: DeploymentSnapshot, targets: ActivationTargets) -> ActivationJournal
TransactionStore.advance(transaction_id: str, expected_state: ActivationState, expected_version: int, next_state: ActivationState, ack_refs: Sequence[AckReference]) -> ActivationJournal
AckStore.create_new(ack: ActivationAck, per_instance_secret: bytes) -> AckReference
RuntimeTargetClient.prepare_all(journal: ActivationJournal, targets: ActivationTargets) -> Sequence[AckReference]
RuntimeTargetClient.collect_commit_acks(journal: ActivationJournal, targets: ActivationTargets) -> Sequence[AckReference]
RuntimeTargetClient.prepare_rollback(journal: ActivationJournal, targets: ActivationTargets) -> Sequence[AckReference]
RuntimeTargetClient.collect_rollback_commit(journal: ActivationJournal, targets: ActivationTargets) -> Sequence[AckReference]
EpochRouter.current() -> RouterEpochState
EpochRouter.commit(expected: RouterEpochState, next_epoch: int, next_tuple: ActivationTuple) -> RouterEpochState
recover_unfinished_transaction(coordinator: ActivationCoordinator, transaction_store: TransactionStore, pointer_store: PointerStore, router: EpochRouter) -> ActivationResult
```

```python
with coordinator.acquire(owner_id=request.transaction_id) as lease:
    authorization_use = authorization_store.validate_and_claim(request, lease)
    snapshot = deployment_store.create_snapshot(request.deployment_inventory_path)
    targets = target_store.create_targets(snapshot, request.transaction_id)
    journal = transaction_store.create(request, lease, snapshot, targets)
    prepare_acks = runtime_targets.prepare_all(journal, targets)
    journal = transaction_store.advance(request.transaction_id, "preparing", journal.version, "prepared", prepare_acks)
    journal = transaction_store.advance(request.transaction_id, "prepared", journal.version, "committing", ())
    pointer = pointer_store.compare_and_swap(request.expected_pointer, request.next_pointer)
    old_router = router.current()
    router.commit(old_router, pointer.activation_epoch, pointer.as_activation_tuple())
    commit_acks = runtime_targets.collect_commit_acks(journal, targets)
    journal = transaction_store.advance(request.transaction_id, "committing", journal.version, "committed", commit_acks)
```

**Spec IDs:** `EVB-POINTER-P0-08`, `EVB-POINTER-P0-10..11`, `EVB-POINTER-P0-13..15`, `EVB-POINTER-P0-18..22`, `EVB-SEC-P0-05`, `EVB-GATE-P0-08`, `EVB-GATE-P0-17`, `EVB-GATE-P0-23..24`.

**Failure manifestation:** `F09`; mutable/forged ack, invalid state, lock inversion, mixed transaction, external conflict overwrite, or unrecoverable crash state is red.

**Expected:** RED on missing coordinator/journal/ack contracts; GREEN when `C09` and `C16` pass. **Real acceptance:** `R09` transaction preflight.

- [ ] **Ack/HMAC RED test.** Add `test_ack_path_payload_and_hmac_are_immutable`:

```python
assert ack_path.parts[-4:] == (transaction_id, str(epoch), phase, f"{target_id}.json")
assert verify_hmac(canonical_ack_without_mac(ack), ack.mac, secret)
with pytest.raises(FileExistsError): ack_store.create_new(ack, secret)
```

- [ ] **Ack/HMAC RED command.** Run `Invoke-ExpectedNativeFailure "ack RED" { & $Python -m pytest tests/test_evb_activation_store.py::test_ack_path_payload_and_hmac_are_immutable -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Ack/HMAC minimal implementation.** Implement `AckStore.create_new(ack: ActivationAck, per_instance_secret: bytes) -> AckReference` with canonical payload/HMAC, exact immutable path, target/challenge/process nonce validation, and create-new bytes.
- [ ] **Ack/HMAC GREEN command.** Run `Invoke-NativeChecked "ack GREEN" { & $Python -m pytest tests/test_evb_activation_store.py::test_ack_path_payload_and_hmac_are_immutable -q }`.

- [ ] **Journal CAS/lock RED test.** Add `test_journal_advance_requires_state_version_and_lock_order` with `assert lock_log == ["coordinator", "journal", "pointer"]` and `with pytest.raises(CasMismatch): store.advance(tx, wrong_state, version, next_state, ())`.
- [ ] **Journal CAS/lock RED command.** Run `Invoke-ExpectedNativeFailure "journal RED" { & $Python -m pytest tests/test_evb_activation_store.py::test_journal_advance_requires_state_version_and_lock_order -q } "AssertionError|AttributeError"`.
- [ ] **Journal CAS/lock minimal implementation.** Implement `TransactionStore.create(request: ActivationRequest, lease: CoordinatorLease, snapshot: DeploymentSnapshot, targets: ActivationTargets) -> ActivationJournal` and `TransactionStore.advance(transaction_id: str, expected_state: ActivationState, expected_version: int, next_state: ActivationState, ack_refs: Sequence[AckReference]) -> ActivationJournal` with the legal state table, durable replace adapters, authorization/snapshot/target hashes, and fixed coordinator -> journal -> pointer ordering.
- [ ] **Journal CAS/lock GREEN command.** Run `Invoke-NativeChecked "journal GREEN" { & $Python -m pytest tests/test_evb_activation_store.py::test_journal_advance_requires_state_version_and_lock_order -q }`.

- [ ] **Coordinator recovery RED test.** Add `test_coordinator_excludes_second_writer_and_recovers_unique_transaction` with `assert second.acquire(blocking=False) is False`, `assert recovered.transaction_id == unfinished.transaction_id`, and `with pytest.raises(InvariantBreach)` for two unfinished journals.
- [ ] **Coordinator recovery RED command.** Run `Invoke-ExpectedNativeFailure "coordinator RED" { & $Python -m pytest tests/test_evb_activation_store.py::test_coordinator_excludes_second_writer_and_recovers_unique_transaction -q } "AssertionError|AttributeError"`.
- [ ] **Coordinator recovery minimal implementation.** Implement `ActivationCoordinator.acquire(owner_id: str) -> CoordinatorLease`, `ActivationCoordinator.run(request: ActivationRequest, operation: Callable[[CoordinatorLease], ActivationResult]) -> ActivationResult`, and `recover_unfinished_transaction(coordinator: ActivationCoordinator, transaction_store: TransactionStore, pointer_store: PointerStore, router: EpochRouter) -> ActivationResult`; hold the OS lock for the full lifecycle, reserve generation/epoch under lock, and enter terminal `conflict` on external pointer/router change without restoring another transaction.
- [ ] **Coordinator recovery GREEN command.** Run `Invoke-NativeChecked "coordinator GREEN" { & $Python -m pytest tests/test_evb_activation_store.py::test_coordinator_excludes_second_writer_and_recovers_unique_transaction -q }`.

- [ ] **CLI authorization-claim RED test.** Add `test_activate_claims_exact_authorization_once_before_transaction` with `assert result.exit_code == 2` when hash is omitted, `assert call_log.index("authorization_claim") < call_log.index("transaction_create")`, and `assert second.exit_code == 3`.
- [ ] **CLI authorization-claim RED command.** Run `Invoke-ExpectedNativeFailure "activation CLI RED" { & $Python -m pytest tests/test_evb_activation_store.py::test_activate_claims_exact_authorization_once_before_transaction -q } "AssertionError|AttributeError"`.
- [ ] **CLI authorization-claim minimal implementation.** Implement `AuthorizationStore.validate_and_claim` and `activate/rollback/fault-matrix` parsers. Rehash report/gates/tuples/pointer before client creation; resolve deployment inventory only through the authorization's hash-pinned preflight/rollback bundle; rollback consumes observation-bundle path/hash and writes a rollback bundle.
- [ ] **CLI authorization-claim GREEN command.** Run `Invoke-NativeChecked "activation CLI GREEN" { & $Python -m pytest tests/test_evb_activation_store.py::test_activate_claims_exact_authorization_once_before_transaction -q }`, then `C09` and `C16`.

- [ ] **Real acceptance `R09`.** Prove OS locks, durable writes, secret delivery, snapshot/target identity, router authority, and recovery; do not route production traffic yet.
- [ ] **Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-10"
$TaskFiles = @("src/huiji_rag/activation_models.py", "src/huiji_rag/activation_store.py", "scripts/activate_evb_build.py", "tests/test_evb_activation_store.py", "tests/fixtures/evb/activation_pipeline.v1.json")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-10 commit safe files" { & git commit -m "feat: add crash-safe EVB activation journal" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-10 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 11: Build Standby Runtime Graph and Atomic Router Epoch

**Files:**

- Create: `src/huiji_rag/runtime_activation.py`
- Modify: `backend/main.py`
- Modify: `backend/schemas.py`
- Create: `tests/test_evb_runtime_activation.py`
- Modify: `tests/test_sse.py`

**Interfaces:**

```text
RuntimeDependencyGraph(activation_tuple, media_registry, vectorstore, retriever, reranker, chain, cursor_state)
build_standby_graph(activation_tuple: ActivationTuple, factories: RuntimeFactories) -> RuntimeDependencyGraph
RuntimeGraphManager.prepare(transaction: ActivationJournal) -> ActivationAck
RuntimeGraphManager.commit(epoch: int, activation_tuple: ActivationTuple) -> ActivationAck
RuntimeGraphManager.rollback_prepare(transaction: ActivationJournal) -> ActivationAck
RuntimeGraphManager.rollback_commit(epoch: int, previous: ActivationTuple) -> ActivationAck
RuntimeGraphManager.pin_request() -> RequestActivationLease
EpochRouter.current() -> RouterEpochState
EpochRouter.commit(expected: RouterEpochState, next_epoch: int, next_tuple: ActivationTuple) -> RouterEpochState
```

**Spec IDs:** `EVB-POINTER-P0-08..15`, `EVB-POINTER-P0-18..22`, `EVB-RUNTIME-P0-01..05`, `EVB-PAGE-P0-04`, `EVB-GATE-P0-09`, `EVB-GATE-P0-17`, `EVB-GATE-P0-19`, `EVB-GATE-P0-23..24`.

**Failure manifestation:** `F09`; partial graph, mixed epoch/tuple, unauthenticated serving, or incomplete rollback keeps/restores the authoritative old epoch.

**Expected:** RED on current single cached `_state`; GREEN when `C10` and neighboring runtime tests pass. **Real acceptance:** `R09` staged standby evidence.

- [ ] **Standby-graph RED test.** Add `test_prepare_rebuilds_all_seven_graph_fields` with `assert dataclasses.fields(graph)` matching `activation_tuple/media_registry/vectorstore/retriever/reranker/chain/cursor_state` and `assert graph not in serving_slots` before commit.
- [ ] **Standby-graph RED command.** Run `Invoke-ExpectedNativeFailure "graph RED" { & $Python -m pytest tests/test_evb_runtime_activation.py::test_prepare_rebuilds_all_seven_graph_fields -q } "AssertionError|AttributeError"`.
- [ ] **Standby-graph minimal implementation.** Implement `build_standby_graph(activation_tuple: ActivationTuple, factories: RuntimeFactories) -> RuntimeDependencyGraph` and `RuntimeGraphManager.prepare`; construct every dependency from the complete tuple without mutating global settings.
- [ ] **Standby-graph GREEN command.** Run `Invoke-NativeChecked "graph GREEN" { & $Python -m pytest tests/test_evb_runtime_activation.py::test_prepare_rebuilds_all_seven_graph_fields -q }`.

- [ ] **Router/lease RED test.** Add `test_router_commit_and_request_lease_never_mix_epochs` with `assert lease.activation_tuple == old_tuple` for in-flight requests, `assert manager.pin_request().activation_tuple == new_tuple` after commit, and `with pytest.raises(CasMismatch)` on stale router state.
- [ ] **Router/lease RED command.** Run `Invoke-ExpectedNativeFailure "router RED" { & $Python -m pytest tests/test_evb_runtime_activation.py::test_router_commit_and_request_lease_never_mix_epochs -q } "AssertionError|AttributeError"`.
- [ ] **Router/lease minimal implementation.** Implement `EpochRouter.current/commit`, `RuntimeGraphManager.commit/rollback_prepare/rollback_commit/pin_request`, and target-client adapters; route only after all prepare acks and retain old graphs until leases drain.
- [ ] **Router/lease GREEN command.** Run `Invoke-NativeChecked "router GREEN" { & $Python -m pytest tests/test_evb_runtime_activation.py::test_router_commit_and_request_lease_never_mix_epochs -q }`, then `C10`, `C06`, and `Invoke-NativeChecked "SSE GREEN" { & $Python -m pytest tests/test_sse.py -q }`.
- [ ] **Step 5: Real acceptance `R09` staged process test.** Prepare all target processes with no production routing, validate health payload tuple/schema/model/config, and retain old graph warm.
- [ ] **Step 6: Commit safe staged files only via Section 1.** Dirty/mixed backend files are `commit_deferred`; request user review and never stage Wiki bytes.

```powershell
$TaskId = "task-11"
$TaskFiles = @("src/huiji_rag/runtime_activation.py", "backend/main.py", "backend/schemas.py", "tests/test_evb_runtime_activation.py", "tests/test_sse.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-11 commit safe files" { & git commit -m "feat: add standby EVB runtime activation" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-11 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 12: Aggregate Reports and Enforce Promotion Decisions

**Files:**

- Create: `src/huiji_rag/promotion.py`
- Modify: `src/huiji_rag/builder.py`
- Modify: `scripts/build_huiji_evb.py`
- Modify: `scripts/activate_evb_build.py`
- Create: `scripts/verify_evb_real_data.py`
- Create: `tests/test_evb_promotion.py`

**Interfaces:**

```text
evaluate_artifact_promotion(evidence: PromotionEvidence) -> PromotionDecision
evaluate_collection_promotion(evidence: PromotionEvidence) -> PromotionDecision
write_evb_reports(build_root: Path, evidence: PromotionEvidence) -> ReportManifest
write_preflight_bundle(root: Path, baseline_path: Path, expected_baseline_sha256: str, sidecars: Mapping[str, Path]) -> PreflightBundleManifest
resolve_bundle_sidecar(bundle_path: Path, expected_bundle_sha256: str, logical_name: str) -> tuple[Path, str]
write_postactivation_observation(root: Path, authorization: PromotionAuthorization, committed: ActivationJournal, before_bundle_path: Path, expected_before_bundle_sha256: str, sidecars: Mapping[str, Path], red_gates: Sequence[str]) -> PostactivationObservationBundle
write_rollback_bundle(root: Path, observation: PostactivationObservationBundle, rollback: RollbackEvidence, sidecars: Mapping[str, Path]) -> RollbackBundleManifest
write_postactivation_bundle(root: Path, observation: PostactivationObservationBundle, outcome: PromotionOutcome, rollback_bundle: RollbackBundleManifest | None) -> PostactivationBundleManifest
create_promotion_authorization(decision: PromotionDecision, report: ReportManifest, expected: ActiveBuildPointer, authorization_type: Literal["promote", "reactivate"], output: Path) -> PromotionAuthorization
validate_promotion_authorization(path: Path, expected_sha256: str, current: ActiveBuildPointer) -> PromotionAuthorization
finalize_promotion_outcome(authorization: PromotionAuthorization, committed: ActivationJournal, post_gates: GateSummary, output: Path) -> PromotionOutcome
```

```python
def evaluate_collection_promotion(evidence: PromotionEvidence) -> PromotionDecision:
    red = tuple(sorted(gate for gate, result in evidence.vector_gates.items() if result != "green"))
    selected = evidence.selected_collection if not red else None
    return PromotionDecision(
        allowed=not red and evidence.artifact_allowed,
        artifact_tuple=evidence.artifact_tuple,
        selected_collection=selected,
        red_gates=red,
        reasons=evidence.reasons_for(red),
    )
```

**Spec IDs:** `EVB-OBS-P0-01..02`, `EVB-PROMOTE-P0-01..02`, `EVB-GATE-P0-01..24`, all stop/no-promotion clauses from `EVB-DIAG-P0-01..03`, `EVB-STORE-P0-05..09`, and `EVB-VECTOR-P0-20..22`.

**Failure manifestation:** `F10`; missing, red, or inconclusive evidence makes `PromotionDecision.allowed` false.

**Expected:** RED on missing promotion/report APIs; GREEN when `C11`, `C14`, `C15`, and `C16` pass. **Real acceptance:** `R10` decision evidence.

- [ ] **Bundle-writer RED test.** Add `test_bundle_writers_are_create_new_hashed_and_acyclic`:

```python
assert set(preflight.sidecars) == REQUIRED_PREFLIGHT_SIDECARS
assert "promotion_outcome" not in observation.sidecars
assert rollback.source_observation_sha256 == observation.bundle_sha256
assert final_post.observation_sha256 == observation.bundle_sha256
```

- [ ] **Bundle-writer RED command.** Run `Invoke-ExpectedNativeFailure "bundle RED" { & $Python -m pytest tests/test_evb_promotion.py::test_bundle_writers_are_create_new_hashed_and_acyclic -q } "ImportError|AttributeError|AssertionError"`.
- [ ] **Bundle-writer minimal implementation.** Implement `write_preflight_bundle`, `resolve_bundle_sidecar`, `write_postactivation_observation`, `write_rollback_bundle`, and `write_postactivation_bundle` with exact relative sidecars, create-new files, containment, and canonical hashes. Final post bundle is written only after outcome/rollback.
- [ ] **Bundle-writer GREEN command.** Run `Invoke-NativeChecked "bundle GREEN" { & $Python -m pytest tests/test_evb_promotion.py::test_bundle_writers_are_create_new_hashed_and_acyclic -q }`.

- [ ] **Aggregate-gate RED test.** Add `test_aggregate_requires_path_and_expected_hash_for_every_gate_input` with `assert decision.allowed is False`, `assert decision.red_gates == ("missing_vector_hash",)`, and `assert external_clients.calls == []` when any expected hash is absent.
- [ ] **Aggregate-gate RED command.** Run `Invoke-ExpectedNativeFailure "aggregate RED" { & $Python -m pytest tests/test_evb_promotion.py::test_aggregate_requires_path_and_expected_hash_for_every_gate_input -q } "AssertionError|AttributeError"`.
- [ ] **Aggregate-gate minimal implementation.** Implement `evaluate_artifact_promotion`, `evaluate_collection_promotion`, and `write_evb_reports`; every preflight/build/MinIO/vector/runtime input is a path/hash pair, missing/inconclusive is red, and artifact-only promotion retains the current collection tuple.
- [ ] **Aggregate-gate GREEN command.** Run `Invoke-NativeChecked "aggregate GREEN" { & $Python -m pytest tests/test_evb_promotion.py::test_aggregate_requires_path_and_expected_hash_for_every_gate_input -q }`.

- [ ] **Authorization RED test.** Add `test_authorization_hash_tuple_pointer_and_claim_are_exact` with `assert auth.authorization_sha256 == canonical_hash_without(auth, "authorization_sha256")`, `assert auth.expected_generation == pointer.generation`, and `with pytest.raises(EvidenceAlreadyUsed): claim(auth)` after first use.
- [ ] **Authorization RED command.** Run `Invoke-ExpectedNativeFailure "authorization RED" { & $Python -m pytest tests/test_evb_promotion.py::test_authorization_hash_tuple_pointer_and_claim_are_exact -q } "AssertionError|AttributeError"`.
- [ ] **Authorization minimal implementation.** Implement `create_promotion_authorization` and `validate_promotion_authorization`; require report, expected-pointer, next-tuple, rollback-bundle when reactivating, and all expected SHA-256 values before create-new authorization/use marker.
- [ ] **Authorization GREEN command.** Run `Invoke-NativeChecked "authorization GREEN" { & $Python -m pytest tests/test_evb_promotion.py::test_authorization_hash_tuple_pointer_and_claim_are_exact -q }`.

- [ ] **Observation/rollback/outcome RED test.** Add `test_postactivation_state_machine_has_no_dependency_cycle` with `assert events == ["observation", "rollback", "outcome", "final_post_bundle"]` for red and `assert events == ["observation", "outcome", "final_post_bundle"]` for green.
- [ ] **Observation/rollback/outcome RED command.** Run `Invoke-ExpectedNativeFailure "outcome RED" { & $Python -m pytest tests/test_evb_promotion.py::test_postactivation_state_machine_has_no_dependency_cycle -q } "AssertionError|AttributeError"`.
- [ ] **Observation/rollback/outcome minimal implementation.** Implement `finalize_promotion_outcome` and postactivate orchestration: write observation first; green finalizes success; red calls rollback using observation path/hash, writes rollback bundle, then finalizes rolled-back/rollback-failed outcome and final post bundle.
- [ ] **Observation/rollback/outcome GREEN command.** Run `Invoke-NativeChecked "outcome GREEN" { & $Python -m pytest tests/test_evb_promotion.py::test_postactivation_state_machine_has_no_dependency_cycle -q }`.

- [ ] **Parser RED test.** Add `test_promotion_parsers_require_all_expected_hashes_and_bundle_roots` with `assert missing.exit_code == 2`, `assert "--expected-next-tuple-sha256" in missing.stderr`, and `assert mutation_clients.calls == []`.
- [ ] **Parser RED command.** Run `Invoke-ExpectedNativeFailure "promotion parser RED" { & $Python -m pytest tests/test_evb_promotion.py::test_promotion_parsers_require_all_expected_hashes_and_bundle_roots -q } "AssertionError|SystemExit"`.
- [ ] **Parser minimal implementation.** Implement exact `capture-preflight`, `aggregate-preactivation`, `authorize`, and `postactivate` arguments from `C17/C18/C26/C27/C30/C34`; rollback parser consumes observation bundle only.
- [ ] **Parser GREEN command.** Run `Invoke-NativeChecked "promotion parser GREEN" { & $Python -m pytest tests/test_evb_promotion.py::test_promotion_parsers_require_all_expected_hashes_and_bundle_roots -q }`, then `C11`, `C14`, `C15`, and `C16`.

- [ ] **Real acceptance `R10`.** Aggregate real preactivation reports and create authorization only after all paths/hashes/current pointer match; blocked evidence creates no authorization.
- [ ] **Commit safe staged files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-12"
$TaskFiles = @("src/huiji_rag/promotion.py", "src/huiji_rag/builder.py", "scripts/build_huiji_evb.py", "scripts/activate_evb_build.py", "scripts/verify_evb_real_data.py", "tests/test_evb_promotion.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-12 commit safe files" { & git commit -m "feat: enforce EVB promotion gates" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-12 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 13: Prove the Full Pipeline with Fake Services and Fault Injection

**Files:**

- Create: `tests/test_evb_integration.py`
- Create: `tests/test_evb_fault_matrix.py`
- Modify: `scripts/verify_evb_real_data.py`
- Modify: `scripts/verify_multi_intent_voice.py`

**Interfaces:**

```text
run_fake_pipeline(fixture: EvbIntegrationFixture) -> IntegrationEvidence
run_activation_fault_matrix(fixture: ActivationFixture) -> Sequence[FaultEvidence]
verify_no_forbidden_calls(call_log: Sequence[ExternalCall]) -> Sequence[str]
verify_p0_reports(report_root: Path) -> GateSummary
```

**Spec IDs:** all `EVB-GATE-P0-01..24`, `EVB-SEC-P0-01..05`, `EVB-OBS-P0-01..02`, `EVB-PROMOTE-P0-01..02`.

**Failure manifestation:** `F10`; any disconnected interface, forbidden call, red fault case, or real endpoint access fails the fake gate.

**Expected:** RED on the first disconnected cross-layer contract; GREEN when `C12`, `C14`, `C15`, and `C16` pass. **Real acceptance:** `R10` verifier runs read-only against captured real preflight reports.

- [ ] **Step 1: Add named RED harness tests only.** `test_fake_pipeline_emits_complete_hashed_evidence_chain`, `test_minio_plan_claim_and_vector_phase_order_are_enforced`, `test_loaded_candidate_cleanup_is_exactly_once_on_every_abort_branch`, `test_dev_bundle_covers_all_candidates_before_freeze`, `test_observation_precedes_rollback_and_final_outcome`, `test_authorization_is_required_and_single_use`, `test_post_red_automatically_rolls_back`, and `test_fault_matrix_covers_every_durable_crash_point` initially fail because integration fixtures/verifier adapters are absent.
- [ ] **Step 2: Add forbidden-call probes** for public/ordinary PUT, bucket setup, overwrite/delete, active collection writes, existing collection reuse, dangerous vectorstore helpers, pointer update before journal committing, router commit before pointer, duplicate ack write, mutable/reused evidence, build-only activation, and held-out reselection.
- [ ] **Integration RED test code.** In `test_fake_pipeline_emits_complete_hashed_evidence_chain`, assert `events.index("observation") < events.index("rollback") < events.index("outcome")`, `all(record.lifecycle_state in {"unloaded_terminal", "promotable_loaded"} for record in loaded_candidates)`, and `forbidden_calls == []`.
- [ ] **Integration RED command.** Run `Invoke-ExpectedNativeFailure "integration RED" { & $Python -m pytest tests/test_evb_integration.py::test_fake_pipeline_emits_complete_hashed_evidence_chain -q } "AssertionError|AttributeError"`.
- [ ] **Integration harness implementation only.** Implement `run_fake_pipeline(fixture: EvbIntegrationFixture) -> IntegrationEvidence` and read-only verifier adapters by composing Tasks 0-12 public interfaces; add no production fallback or behavior.
- [ ] **Integration GREEN command.** Run `Invoke-NativeChecked "integration GREEN" { & $Python -m pytest tests/test_evb_integration.py::test_fake_pipeline_emits_complete_hashed_evidence_chain -q }`.

- [ ] **Fault RED test code.** In `test_fault_matrix_covers_every_durable_crash_point`, assert every injected crash has a terminal recovery state, no mixed tuple/epoch, and no pointer write before durable journal state.
- [ ] **Fault RED command.** Run `Invoke-ExpectedNativeFailure "fault RED" { & $Python -m pytest tests/test_evb_fault_matrix.py::test_fault_matrix_covers_every_durable_crash_point -q } "AssertionError|AttributeError"`.
- [ ] **Fault harness implementation only.** Implement `run_activation_fault_matrix`, forbidden-call probes, and report verification in tests/verifier files only. Any production disconnect returns to its owner task for a focused RED/GREEN fix.
- [ ] **Fault GREEN command.** Run `Invoke-NativeChecked "fault GREEN" { & $Python -m pytest tests/test_evb_fault_matrix.py::test_fault_matrix_covers_every_durable_crash_point -q }`, then `C12`, `C14`, `C15`, and `C16`.
- [ ] **Step 6: Verify zero real service mutation.** Call logs contain no real endpoint/credential and no forbidden method.
- [ ] **Step 7: Commit safe staged test/verifier files only via Section 1; report dirty/mixed hunks as `commit_deferred` and request user review.**

```powershell
$TaskId = "task-13"
$TaskFiles = @("tests/test_evb_integration.py", "tests/test_evb_fault_matrix.py", "scripts/verify_evb_real_data.py", "scripts/verify_multi_intent_voice.py")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-13 commit safe files" { & git commit -m "test: prove EVB pipeline and fault recovery" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-13 commit_deferred: $($DeferredFiles -join ',')" }
```

## Task 14: Execute Controlled Real-Data Gates and Rollback Drill

**Files:**

- Create during execution: `eval/evb_real/**`
- Create and commit: `docs/superpowers/reports/2026-07-11-eventname-voice-binding-recovery-p0-signoff.json`
- Read only before mutation: `data/processed/huiji/dev/**`, active Milvus collection, MinIO bucket inventory, deployment inventory

**Interfaces:**

```text
capture_real_before(cfg: Config) -> RealBeforeInventory
verify_real_preflight(before: RealBeforeInventory, reports: ReportManifest) -> GateSummary
verify_real_after(before: RealBeforeInventory, after: RealAfterInventory) -> GateSummary
run_rollback_drill(committed_transaction: Path, expected_transaction_sha256: str, authorization: Path, expected_authorization_sha256: str, observation_bundle: Path, expected_observation_bundle_sha256: str, output_root: Path) -> RollbackBundleManifest
```

**Spec IDs:** every P0 ID; this task is the mandatory real-data closure for the coverage matrix.

**Failure manifestation:** `F10`; any red/inconclusive real gate stops promotion or triggers the specified rollback transaction.

**Expected:** RED or blocked before any unsafe capability; GREEN only with Task 0's completed `C13` evidence, `C17..C34` as applicable, rollback, hash-pinned reactivation, and reactivation postverification. **Real acceptance:** `R01..R10`.

- [ ] **Step 1: Set unique safe IDs and capture immutable before evidence.**

This plan reuses exactly the baseline created once by Task 0. Task 14 never captures it and never depends on Task 0's shell environment. It restores the baseline path/hash from the external create-new receipt and verifies the receipt's canonical hash. A separate future run must first choose a new safe `capture_id`, a new create-new baseline/receipt path, and propagate that new hash through every bundle/manifest/plan; it cannot overwrite or silently reuse the fixed evidence from this run.

```powershell
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$RunLocatorRoot = Join-Path $env:LOCALAPPDATA "EVB-runs/1999Search/2026-07-11-eventname-voice-binding-recovery"
$RunLocatorPath = Join-Path $RunLocatorRoot "run_locator.v1.json"
$RunLocatorShaPath = Join-Path $RunLocatorRoot "run_locator.v1.sha256"
if (-not (Test-Path $RunLocatorPath) -or -not (Test-Path $RunLocatorShaPath)) { throw "Task 0 run locator is absent; do not create a new snapshot or recapture implicitly" }
$Locator = Get-Content -Raw $RunLocatorPath | ConvertFrom-Json
$ExpectedLocatorSha = (Get-Content -Raw $RunLocatorShaPath).Trim().ToLowerInvariant()
$LocatorWithoutHash = [ordered]@{ schema_version=$Locator.schema_version; run_id=$Locator.run_id; authority_root=$Locator.authority_root; authority_manifest_sha256=$Locator.authority_manifest_sha256; execution_root=$Locator.execution_root; baseline_receipt_path=$Locator.baseline_receipt_path; baseline_receipt_sha256=$Locator.baseline_receipt_sha256 }
$LocatorCanonical = $LocatorWithoutHash | ConvertTo-Json -Depth 6 -Compress
$ActualLocatorSha = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($LocatorCanonical))).ToLowerInvariant()
if ($Locator.schema_version -ne "evb.run-locator/v1" -or $Locator.run_id -ne "2026-07-11-eventname-voice-binding-recovery" -or $ActualLocatorSha -ne $ExpectedLocatorSha -or $Locator.locator_sha256 -ne $ExpectedLocatorSha) { throw "EVB run locator hash/schema mismatch" }
$env:EVB_AUTHORITY_ROOT = $Locator.authority_root
$env:EVB_AUTHORITY_SHA256 = $Locator.authority_manifest_sha256
if ((Resolve-Path -LiteralPath $ExecutionRoot).Path -ne (Resolve-Path -LiteralPath $Locator.execution_root).Path) { throw "resume the execution root recorded by the run locator" }
$AuthorityManifestPath = Join-Path $env:EVB_AUTHORITY_ROOT "authority_manifest.v1.json"
if ((Get-FileHash $AuthorityManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $env:EVB_AUTHORITY_SHA256) { throw "run locator authority manifest mismatch" }
$ReceiptPath = $Locator.baseline_receipt_path
$ReceiptShaPath = Join-Path (Split-Path $ReceiptPath -Parent) "baseline_receipt.v1.sha256"
if (-not (Test-Path $ReceiptPath) -or -not (Test-Path $ReceiptShaPath)) { throw "Task 0 baseline receipt is absent; do not recapture implicitly" }
$Receipt = Get-Content -Raw $ReceiptPath | ConvertFrom-Json
$ExpectedReceiptSha = (Get-Content -Raw $ReceiptShaPath).Trim().ToLowerInvariant()
$ReceiptWithoutHash = [ordered]@{ schema_version=$Receipt.schema_version; baseline_relative_path=$Receipt.baseline_relative_path; baseline_sha256=$Receipt.baseline_sha256; baseline_schema_version=$Receipt.baseline_schema_version; source_inventory_sha256=$Receipt.source_inventory_sha256 }
$ReceiptCanonical = $ReceiptWithoutHash | ConvertTo-Json -Depth 6 -Compress
$ActualReceiptSha = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($ReceiptCanonical))).ToLowerInvariant()
if ($Receipt.schema_version -ne "evb.baseline-receipt/v1" -or $ActualReceiptSha -ne $ExpectedReceiptSha -or $Receipt.receipt_sha256 -ne $ExpectedReceiptSha -or $ExpectedReceiptSha -ne $Locator.baseline_receipt_sha256) { throw "baseline receipt hash/schema/locator mismatch" }
$env:EVB_BASELINE_PATH = [IO.Path]::GetFullPath((Join-Path $ExecutionRoot $Receipt.baseline_relative_path))
if (-not $env:EVB_BASELINE_PATH.StartsWith($ExecutionRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "baseline receipt path escapes execution root" }
$env:EVB_BASELINE_SHA256 = $Receipt.baseline_sha256
$BaselineResolved = (Resolve-Path -LiteralPath $env:EVB_BASELINE_PATH).Path
if ((Get-FileHash $BaselineResolved -Algorithm SHA256).Hash.ToLowerInvariant() -ne $env:EVB_BASELINE_SHA256) { throw "Task 0 baseline hash mismatch" }
$BaselineDocument = Get-Content -Raw $BaselineResolved | ConvertFrom-Json
if ($BaselineDocument.schema_version -ne $Receipt.baseline_schema_version -or $BaselineDocument.source_inventory_sha256 -ne $Receipt.source_inventory_sha256) { throw "Task 0 baseline schema/source inventory hash invalid" }
$env:EVB_REAL_BUILD = "evb-$stamp"
$env:EVB_EXPERIMENT_ID = "evbexp-$stamp"
$env:EVB_TRANSACTION_ID = "evbtx-$stamp"
$env:EVB_ROLLBACK_TRANSACTION_ID = "evbrb-$stamp"
$env:EVB_REACTIVATE_TRANSACTION_ID = "evbreact-$stamp"
$env:EVB_REACTIVATION_ROLLBACK_TRANSACTION_ID = "evbreactrb-$stamp"
$env:EVB_AUTHORIZATION_ID = "evbauth-$stamp"
$env:EVB_REACTIVATION_AUTHORIZATION_ID = "evbreauth-$stamp"
$env:EVB_MINIO_PLAN_PATH = "data/processed/huiji/$env:EVB_REAL_BUILD/operations/minio_operation_plan.v1.json"
$env:EVB_MINIO_REPORT_PATH = "data/processed/huiji/$env:EVB_REAL_BUILD/operations/minio_write_report.v1.json"
$env:EVB_AUTHORIZATION_PATH = "data/processed/huiji/activation/authorizations/$env:EVB_AUTHORIZATION_ID/promotion_authorization.v1.json"
$env:EVB_REACTIVATION_AUTHORIZATION_PATH = "data/processed/huiji/activation/authorizations/$env:EVB_REACTIVATION_AUTHORIZATION_ID/promotion_authorization.v1.json"
$env:EVB_BUILD_MANIFEST_PATH = "data/processed/huiji/$env:EVB_REAL_BUILD/build_manifest.v1.json"
if ([string]::IsNullOrWhiteSpace($env:EVB_CANDIDATE_CONFIGS)) { throw "set EVB_CANDIDATE_CONFIGS to the approved immutable candidate config JSON" }
$CandidateConfigPath = (Resolve-Path -LiteralPath $env:EVB_CANDIDATE_CONFIGS).Path
$env:EVB_CANDIDATE_CONFIGS_SHA256 = (Get-FileHash -LiteralPath $CandidateConfigPath -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "capture preflight bundle" { & $Python scripts/verify_evb_real_data.py capture-preflight --build-version $env:EVB_REAL_BUILD --baseline $env:EVB_BASELINE_PATH --expected-baseline-sha256 $env:EVB_BASELINE_SHA256 --output-root eval/evb_real/preflight }
$env:EVB_PREFLIGHT_BUNDLE_PATH = "eval/evb_real/preflight/preflight_bundle_manifest.v1.json"
$env:EVB_PREFLIGHT_BUNDLE_SHA256 = (Get-FileHash -LiteralPath $env:EVB_PREFLIGHT_BUNDLE_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
$PreflightRoot = (Resolve-Path -LiteralPath (Split-Path $env:EVB_PREFLIGHT_BUNDLE_PATH -Parent)).Path
$PreflightBundle = Get-Content -Raw $env:EVB_PREFLIGHT_BUNDLE_PATH | ConvertFrom-Json
function Resolve-BundleSidecarChecked([string]$Root, $Bundle, [string]$Name) {
  $Entry = @($Bundle.sidecars | Where-Object logical_name -eq $Name)
  if ($Entry.Count -ne 1) { throw "bundle sidecar missing or duplicate: $Name" }
  $Resolved = [IO.Path]::GetFullPath((Join-Path $Root $Entry[0].relative_path))
  if (-not $Resolved.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "bundle sidecar root escape: $Name" }
  if ((Get-FileHash $Resolved -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry[0].sha256) { throw "bundle sidecar hash mismatch: $Name" }
  return $Resolved
}
$env:EVB_MINIO_BEFORE_PATH = Resolve-BundleSidecarChecked $PreflightRoot $PreflightBundle "minio_before"
$env:EVB_MINIO_BEFORE_SHA256 = (Get-FileHash $env:EVB_MINIO_BEFORE_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
$env:EVB_RUNTIME_PREFLIGHT_PATH = Resolve-BundleSidecarChecked $PreflightRoot $PreflightBundle "runtime_preflight"
$env:EVB_RUNTIME_PREFLIGHT_SHA256 = (Get-FileHash $env:EVB_RUNTIME_PREFLIGHT_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
$env:EVB_ACTIVE_POINTER_BEFORE_PATH = Resolve-BundleSidecarChecked $PreflightRoot $PreflightBundle "active_pointer_before"
$env:EVB_ACTIVE_POINTER_BEFORE_SHA256 = (Get-FileHash $env:EVB_ACTIVE_POINTER_BEFORE_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: exit `0`; dynamic before inventories, active tuple, collection payload fingerprint, MinIO policy/object hashes, source hashes, deployment snapshot capability, and capacity evidence are present. No mutation occurs.

- [ ] **Step 2: Run all automated and fake gates.**

```powershell
Invoke-NativeChecked "full pytest" { & $Python -m pytest tests -q }
Push-Location frontend/react-app
$FrontendBefore = Get-ChildItem src -Recurse -File | Sort-Object FullName | ForEach-Object { "$(($_.FullName)):$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)" }
Invoke-NativeChecked "frontend compatibility tests" { & npm test -- src/components/chat/MessageBubble.test.tsx src/api/media.test.ts }
$FrontendOut = Join-Path $env:TEMP "evb-frontend-build-$PID"
Invoke-NativeChecked "frontend compatibility build" { & npm run build -- --outDir $FrontendOut --emptyOutDir }
$FrontendAfter = Get-ChildItem src -Recurse -File | Sort-Object FullName | ForEach-Object { "$(($_.FullName)):$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)" }
if (Compare-Object $FrontendBefore $FrontendAfter) { throw "frontend source changed during read-only compatibility gate" }
Pop-Location
$env:EVB_FAKE_BASELINE_SHA256 = (Get-FileHash tests/fixtures/evb/baseline.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
$env:EVB_FAKE_PREFLIGHT_BUNDLE_SHA256 = (Get-FileHash tests/fixtures/evb/preflight_bundle/preflight_bundle_manifest.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "offline fake build" { & $Python scripts/build_huiji_evb.py offline --build-version evb-gate --baseline tests/fixtures/evb/baseline.v1.json --expected-baseline-sha256 $env:EVB_FAKE_BASELINE_SHA256 --preflight-bundle tests/fixtures/evb/preflight_bundle/preflight_bundle_manifest.v1.json --expected-preflight-bundle-sha256 $env:EVB_FAKE_PREFLIGHT_BUNDLE_SHA256 --dry-run --output-root eval/evb_real/dry-run }
$env:EVB_VECTOR_FIXTURE_SHA256 = (Get-FileHash -LiteralPath tests/fixtures/evb/vector_pipeline.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "vector fake pipeline" { & $Python scripts/run_evb_vector_experiment.py fake-pipeline --fixture tests/fixtures/evb/vector_pipeline.v1.json --expected-fixture-sha256 $env:EVB_VECTOR_FIXTURE_SHA256 --report-root eval/evb_real/vector-fake }
$env:EVB_ACTIVATION_FIXTURE_SHA256 = (Get-FileHash -LiteralPath tests/fixtures/evb/activation_pipeline.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "activation fake matrix" { & $Python scripts/activate_evb_build.py fault-matrix --fixture tests/fixtures/evb/activation_pipeline.v1.json --expected-fixture-sha256 $env:EVB_ACTIVATION_FIXTURE_SHA256 --report eval/evb_real/activation-fake.json }
```

Expected: all exit `0`. Any failure stops the real sequence.

- [ ] **Step 3: Build the isolated real artifact set without external writes.**

```powershell
Invoke-NativeChecked "real offline build" { & $Python scripts/build_huiji_evb.py offline --build-version $env:EVB_REAL_BUILD --baseline $env:EVB_BASELINE_PATH --expected-baseline-sha256 $env:EVB_BASELINE_SHA256 --preflight-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-preflight-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --report-root eval/evb_real/build }
$env:EVB_BUILD_MANIFEST_SHA256 = (Get-FileHash -LiteralPath $env:EVB_BUILD_MANIFEST_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: complete isolated artifacts/reports, unchanged `dev`, exact runtime projection, and parity gates green.

- [ ] **Step 4: Create, hash, and consume one immutable MinIO operation plan.**

```powershell
Invoke-NativeChecked "create MinIO operation plan" { & $Python scripts/build_huiji_evb.py minio-plan --build-manifest $env:EVB_BUILD_MANIFEST_PATH --expected-build-manifest-sha256 $env:EVB_BUILD_MANIFEST_SHA256 --preflight-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-preflight-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --before-inventory $env:EVB_MINIO_BEFORE_PATH --expected-before-inventory-sha256 $env:EVB_MINIO_BEFORE_SHA256 --baseline $env:EVB_BASELINE_PATH --expected-baseline-sha256 $env:EVB_BASELINE_SHA256 --output $env:EVB_MINIO_PLAN_PATH }
$env:EVB_MINIO_PLAN_SHA256 = (Get-FileHash -LiteralPath $env:EVB_MINIO_PLAN_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "strict MinIO upload" { & $Python scripts/build_huiji_evb.py minio-upload --operation-plan $env:EVB_MINIO_PLAN_PATH --expected-plan-sha256 $env:EVB_MINIO_PLAN_SHA256 --report $env:EVB_MINIO_REPORT_PATH }
$env:EVB_MINIO_REPORT_SHA256 = (Get-FileHash -LiteralPath $env:EVB_MINIO_REPORT_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: only planned missing SHA-1 keys use conditional create; every object has audit/readback evidence. Any nonzero exit throws here before vector preparation; conflict stops writes and promotion while read-only diagnosis completes.

- [ ] **Step 5: Run the vector experiment as separate immutable phases when eligible.**

Task 14 is the sole lifecycle orchestration owner. Task 8 only emits evidence/plans; it never unloads. `$CreatedCandidates` tracks every candidate whose build evidence reports `collection_created=true`, including partial/failed collections that never reached load. Every created candidate reaches exactly one of `unloaded_terminal`, `already_unloaded_terminal`, `cleanup_failed_terminal`, or `promotable_loaded`; duplicate lifecycle claims are rejected by both state and create-new plan/report markers.

```powershell
Invoke-NativeChecked "vector prepare" { & $Python scripts/run_evb_vector_experiment.py prepare --experiment-id $env:EVB_EXPERIMENT_ID --build-manifest $env:EVB_BUILD_MANIFEST_PATH --expected-build-manifest-sha256 $env:EVB_BUILD_MANIFEST_SHA256 --preflight-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-preflight-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --candidate-configs $env:EVB_CANDIDATE_CONFIGS --expected-candidate-configs-sha256 $env:EVB_CANDIDATE_CONFIGS_SHA256 --output-root data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID }
$env:EVB_VECTOR_PREFLIGHT = "data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/vector_preflight_plan.v1.json"
$env:EVB_VECTOR_PREFLIGHT_SHA256 = (Get-FileHash -LiteralPath $env:EVB_VECTOR_PREFLIGHT -Algorithm SHA256).Hash.ToLowerInvariant()
$VectorPreflight = Get-Content -Raw $env:EVB_VECTOR_PREFLIGHT | ConvertFrom-Json
$RegistryPath = [IO.Path]::GetFullPath((Join-Path (Split-Path $env:EVB_VECTOR_PREFLIGHT -Parent) $VectorPreflight.candidate_registry.relative_path))
if ((Get-FileHash $RegistryPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $VectorPreflight.candidate_registry.sha256) { throw "candidate registry hash mismatch" }
$env:EVB_CANDIDATE_REGISTRY_PATH = $RegistryPath
$env:EVB_CANDIDATE_REGISTRY_SHA256 = (Get-FileHash $RegistryPath -Algorithm SHA256).Hash.ToLowerInvariant()
$Registry = Get-Content -Raw $RegistryPath | ConvertFrom-Json
$CreatedCandidates = [System.Collections.Generic.List[object]]::new()
function Invoke-CandidateUnload($Record, [string]$Reason) {
  if ($Record.lifecycle_state -notin @("created", "loaded")) { throw "duplicate or invalid lifecycle claim for $($Record.candidate_id): $($Record.lifecycle_state)" }
  $Record.lifecycle_state = "cleanup_claimed"
  $env:EVB_VECTOR_CANDIDATE_ROOT = $Record.root
  $env:EVB_VECTOR_INTENT = $Record.intent_path
  $env:EVB_VECTOR_INTENT_SHA256 = (Get-FileHash $Record.intent_path -Algorithm SHA256).Hash.ToLowerInvariant()
  $env:EVB_LIFECYCLE_EVIDENCE_PATH = $Record.evidence_path
  $env:EVB_LIFECYCLE_EVIDENCE_SHA256 = (Get-FileHash $Record.evidence_path -Algorithm SHA256).Hash.ToLowerInvariant()
  $env:EVB_LIFECYCLE_REASON = $Reason
  $LifecycleId = "lifecycle-" + [Guid]::NewGuid().ToString("N")
  $LifecycleRoot = Join-Path $Record.root "lifecycle/$LifecycleId"
  $env:EVB_LIFECYCLE_PLAN_PATH = Join-Path $LifecycleRoot "lifecycle_operation_plan.v1.json"
  $env:EVB_LIFECYCLE_REPORT_PATH = Join-Path $LifecycleRoot "lifecycle_evidence.v1.json"
  try {
    Invoke-NativeChecked "create lifecycle plan $Reason" { & $Python scripts/run_evb_vector_experiment.py lifecycle-plan --candidate-root $env:EVB_VECTOR_CANDIDATE_ROOT --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --intent-manifest $env:EVB_VECTOR_INTENT --expected-intent-sha256 $env:EVB_VECTOR_INTENT_SHA256 --evidence $env:EVB_LIFECYCLE_EVIDENCE_PATH --expected-evidence-sha256 $env:EVB_LIFECYCLE_EVIDENCE_SHA256 --reason $env:EVB_LIFECYCLE_REASON --output $env:EVB_LIFECYCLE_PLAN_PATH }
    $env:EVB_LIFECYCLE_PLAN_SHA256 = (Get-FileHash $env:EVB_LIFECYCLE_PLAN_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
    Invoke-NativeChecked "unload candidate $Reason" { & $Python scripts/run_evb_vector_experiment.py finalize-lifecycle --action unload --lifecycle-plan $env:EVB_LIFECYCLE_PLAN_PATH --expected-lifecycle-plan-sha256 $env:EVB_LIFECYCLE_PLAN_SHA256 --report $env:EVB_LIFECYCLE_REPORT_PATH }
    $LifecycleReportSha = (Get-FileHash $env:EVB_LIFECYCLE_REPORT_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
    $LifecycleReport = Get-Content -Raw $env:EVB_LIFECYCLE_REPORT_PATH | ConvertFrom-Json
    if ($LifecycleReport.status -notin @("unloaded_terminal", "already_unloaded_terminal") -or $LifecycleReport.lifecycle_plan_sha256 -ne $env:EVB_LIFECYCLE_PLAN_SHA256) { throw "lifecycle terminal report mismatch for $($Record.candidate_id)" }
    $Record.lifecycle_state = $LifecycleReport.status
    $Record.lifecycle_report = $env:EVB_LIFECYCLE_REPORT_PATH
    $Record.lifecycle_report_sha256 = $LifecycleReportSha
  } catch {
    $UnloadFailure = $_
    $Record.lifecycle_state = "cleanup_failed_terminal"
    if (-not (Test-Path -LiteralPath $env:EVB_LIFECYCLE_REPORT_PATH)) { throw "unload failed without immutable lifecycle evidence for $($Record.candidate_id)" }
    $FailureReportSha = (Get-FileHash $env:EVB_LIFECYCLE_REPORT_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
    $FailureReport = Get-Content -Raw $env:EVB_LIFECYCLE_REPORT_PATH | ConvertFrom-Json
    if ($FailureReport.status -ne "cleanup_failed_terminal" -or $FailureReport.lifecycle_plan_sha256 -ne $env:EVB_LIFECYCLE_PLAN_SHA256) { throw "unload failure evidence mismatch for $($Record.candidate_id)" }
    $Record.lifecycle_report = $env:EVB_LIFECYCLE_REPORT_PATH
    $Record.lifecycle_report_sha256 = $FailureReportSha
    throw $UnloadFailure
  }
}
$VectorOrchestrationSucceeded = $false
try {
  foreach ($Candidate in $Registry.candidates) {
    $env:EVB_CANDIDATE_ID = $Candidate.candidate_id
    $CandidateRoot = "data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/candidates/$env:EVB_CANDIDATE_ID"
    $IntentPath = "$CandidateRoot/intent_manifest.v1.json"
    Invoke-NativeChecked "candidate intent" { & $Python scripts/run_evb_vector_experiment.py intent --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --candidate-id $env:EVB_CANDIDATE_ID --output $IntentPath }
    $IntentSha = (Get-FileHash -LiteralPath $IntentPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Invoke-NativeChecked "candidate build-dev" { & $Python scripts/run_evb_vector_experiment.py build-dev --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --intent-manifest $IntentPath --expected-intent-sha256 $IntentSha --report-root $CandidateRoot } @(0,3,4,5)
    $BuildEvidence = Join-Path $CandidateRoot "vector_build_report.v1.json"
    $BuildResult = Get-Content -Raw $BuildEvidence | ConvertFrom-Json
    foreach ($RequiredField in @("collection_created", "collection_loaded", "requires_unload", "server_identity")) { if ($null -eq $BuildResult.$RequiredField) { throw "build evidence missing lifecycle field: $RequiredField" } }
    if ([bool]$BuildResult.collection_created) {
      $CleanupReason = if ($script:LastNativeExitCode -eq 0) { "orchestration_abort" } elseif ([int]$BuildResult.inserted_rows -gt 0) { "build_partial" } else { "build_failed" }
      $InitialLifecycleState = if ([bool]$BuildResult.collection_loaded) { "loaded" } else { "created" }
      if (-not [bool]$BuildResult.requires_unload -and $InitialLifecycleState -eq "created") { throw "created partial collection lacks requires_unload evidence" }
      $CreatedCandidates.Add([pscustomobject]@{ candidate_id=$Candidate.candidate_id; root=$CandidateRoot; intent_path=$IntentPath; evidence_path=$BuildEvidence; server_identity=$BuildResult.server_identity; lifecycle_state=$InitialLifecycleState; lifecycle_report=$null; lifecycle_report_sha256=$null; cleanup_reason=$CleanupReason })
    }
    if ($script:LastNativeExitCode -ne 0) { throw "candidate build-dev failed; cleanup all created candidates" }
  }
  $env:EVB_DEV_BUNDLE_PATH = "data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/dev_evaluation_bundle.v1.json"
  Invoke-NativeChecked "create dev evaluation bundle" { & $Python scripts/run_evb_vector_experiment.py dev-bundle --preflight-plan $env:EVB_VECTOR_PREFLIGHT --expected-preflight-sha256 $env:EVB_VECTOR_PREFLIGHT_SHA256 --candidate-registry $env:EVB_CANDIDATE_REGISTRY_PATH --expected-candidate-registry-sha256 $env:EVB_CANDIDATE_REGISTRY_SHA256 --output $env:EVB_DEV_BUNDLE_PATH }
  $env:EVB_DEV_BUNDLE_SHA256 = (Get-FileHash $env:EVB_DEV_BUNDLE_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
  $FrozenPath = "data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/frozen_decision.v1.json"
  Invoke-NativeChecked "freeze dev decision" { & $Python scripts/run_evb_vector_experiment.py freeze --dev-bundle $env:EVB_DEV_BUNDLE_PATH --expected-dev-bundle-sha256 $env:EVB_DEV_BUNDLE_SHA256 --output $FrozenPath }
  $env:EVB_FROZEN_SHA256 = (Get-FileHash $FrozenPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $Frozen = Get-Content -Raw $FrozenPath | ConvertFrom-Json
  foreach ($Record in @($CreatedCandidates | Where-Object candidate_id -ne $Frozen.selected_candidate_id)) {
    $Record.evidence_path = Join-Path $Record.root "dev_evaluation.v1.json"
    Invoke-CandidateUnload $Record "dev_unselected"
  }
  if ($null -ne $Frozen.selected_candidate_id) {
    $Selected = @($CreatedCandidates | Where-Object candidate_id -eq $Frozen.selected_candidate_id)[0]
    if ($Selected.lifecycle_state -ne "loaded") { throw "frozen candidate is not loaded" }
    $HeldOutReport = "data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/held_out_report.v1.json"
    Invoke-NativeChecked "held-out acceptance" { & $Python scripts/run_evb_vector_experiment.py held-out --frozen-candidate $FrozenPath --expected-frozen-sha256 $env:EVB_FROZEN_SHA256 --execution-marker data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/held_out_execution.v1.json --report $HeldOutReport --decision-output data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/vector_promotion_decision.v1.json } @(0,3,4,5)
    $Selected.evidence_path = $HeldOutReport
    if ($script:LastNativeExitCode -ne 0) {
      $Reason = if ($script:LastNativeExitCode -eq 3) { "held_out_inconclusive" } else { "held_out_failed" }
      Invoke-CandidateUnload $Selected $Reason
      throw "held-out did not pass"
    }
    $Selected.lifecycle_state = "promotable_loaded"
    $env:EVB_VECTOR_DECISION = "data/processed/huiji/vector/experiments/$env:EVB_EXPERIMENT_ID/vector_promotion_decision.v1.json"
  } else {
    $env:EVB_VECTOR_DECISION = $FrozenPath
  }
  $VectorOrchestrationSucceeded = $true
} finally {
  if (-not $VectorOrchestrationSucceeded) {
    $CleanupFailures = @()
    foreach ($Record in @($CreatedCandidates | Where-Object lifecycle_state -in @("created", "loaded"))) {
      try { Invoke-CandidateUnload $Record $Record.cleanup_reason } catch { $CleanupFailures += "$($Record.candidate_id):$($_.Exception.Message)" }
    }
    if ($CleanupFailures.Count -gt 0) { throw "candidate unload failures block promotion and new candidates: $($CleanupFailures -join ';')" }
  }
}
$env:EVB_VECTOR_DECISION_SHA256 = (Get-FileHash $env:EVB_VECTOR_DECISION -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: prepare fixes all hashes; build-dev records every created candidate with `collection_created`, `collection_loaded`, `requires_unload`, and server identity. The create-new dev bundle covers the complete registry and freeze consumes only its hash. Unselected, partial, and failed created candidates receive exactly one lifecycle plan and an `unloaded_terminal` or verified `already_unloaded_terminal` report. Held-out pass leaves only the selected loaded candidate `promotable_loaded`; any abort runs `finally` cleanup across all remaining created/loaded candidates.

- [ ] **Step 6: Aggregate preactivation evidence and create one immutable authorization.**

```powershell
Invoke-NativeChecked "aggregate preactivation" { & $Python scripts/verify_evb_real_data.py aggregate-preactivation --preflight-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-preflight-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --build-manifest $env:EVB_BUILD_MANIFEST_PATH --expected-build-manifest-sha256 $env:EVB_BUILD_MANIFEST_SHA256 --minio-report $env:EVB_MINIO_REPORT_PATH --expected-minio-report-sha256 $env:EVB_MINIO_REPORT_SHA256 --vector-decision $env:EVB_VECTOR_DECISION --expected-vector-decision-sha256 $env:EVB_VECTOR_DECISION_SHA256 --runtime-preflight $env:EVB_RUNTIME_PREFLIGHT_PATH --expected-runtime-preflight-sha256 $env:EVB_RUNTIME_PREFLIGHT_SHA256 --output eval/evb_real/promotion/report_manifest.v1.json }
$env:EVB_REPORT_MANIFEST_SHA256 = (Get-FileHash -LiteralPath eval/evb_real/promotion/report_manifest.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
$env:EVB_NEXT_TUPLE_PATH = "eval/evb_real/promotion/next_activation_tuple.v1.json"
$env:EVB_NEXT_TUPLE_SHA256 = (Get-FileHash $env:EVB_NEXT_TUPLE_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "authorize promotion" { & $Python scripts/verify_evb_real_data.py authorize --report-manifest eval/evb_real/promotion/report_manifest.v1.json --expected-report-manifest-sha256 $env:EVB_REPORT_MANIFEST_SHA256 --expected-pointer $env:EVB_ACTIVE_POINTER_BEFORE_PATH --expected-pointer-sha256 $env:EVB_ACTIVE_POINTER_BEFORE_SHA256 --next-tuple $env:EVB_NEXT_TUPLE_PATH --expected-next-tuple-sha256 $env:EVB_NEXT_TUPLE_SHA256 --authorization-type promote --output $env:EVB_AUTHORIZATION_PATH }
$env:EVB_AUTHORIZATION_SHA256 = (Get-FileHash -LiteralPath $env:EVB_AUTHORIZATION_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: all gate hashes and the complete expected/current and selected/next tuples are bound create-new. Missing/red/inconclusive evidence, changed pointer, or path/hash mismatch creates no authorization.

- [ ] **Step 7: Activate only through the authorization path/hash.**

```powershell
Invoke-NativeChecked "activate authorized tuple" { & $Python scripts/activate_evb_build.py activate --transaction-id $env:EVB_TRANSACTION_ID --promotion-authorization $env:EVB_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_AUTHORIZATION_SHA256 --report-root eval/evb_real/activation }
$env:EVB_COMMITTED_TRANSACTION_SHA256 = (Get-FileHash -LiteralPath eval/evb_real/activation/committed_transaction.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: one-time authorization claim precedes transaction creation; coordinator spans lifecycle; all targets prepare the full graph; durable journal/pointer/router ordering and authenticated serving acks are complete.

- [ ] **Step 8: Run postactivation verification and produce final outcome.**

```powershell
Invoke-NativeChecked "postactivate verification" { & $Python scripts/verify_evb_real_data.py postactivate --transaction-record eval/evb_real/activation/committed_transaction.v1.json --expected-transaction-sha256 $env:EVB_COMMITTED_TRANSACTION_SHA256 --promotion-authorization $env:EVB_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_AUTHORIZATION_SHA256 --before-bundle $env:EVB_PREFLIGHT_BUNDLE_PATH --expected-before-bundle-sha256 $env:EVB_PREFLIGHT_BUNDLE_SHA256 --rollback-transaction-id $env:EVB_ROLLBACK_TRANSACTION_ID --output-root eval/evb_real/postactivation } @(0,6,7)
$env:EVB_POSTACTIVATION_OBSERVATION_PATH = "eval/evb_real/postactivation/postactivation_observation_bundle.v1.json"
$env:EVB_POSTACTIVATION_OBSERVATION_SHA256 = (Get-FileHash $env:EVB_POSTACTIVATION_OBSERVATION_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
$env:EVB_POSTACTIVATION_BUNDLE_PATH = "eval/evb_real/postactivation/postactivation_bundle_manifest.v1.json"
$env:EVB_POSTACTIVATION_BUNDLE_SHA256 = (Get-FileHash $env:EVB_POSTACTIVATION_BUNDLE_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
switch ($script:LastNativeExitCode) {
  0 { }
  6 { throw "postactivation red; automatic rollback is proven, stop this run without drill or reactivation" }
  7 { throw "postactivation recovery unproven; escalate manual authoritative recovery immediately" }
  default { throw "unexpected postactivation exit code" }
}
```

Expected: success exists only with commit acks and green API/inventory evidence. Any red gate automatically enters spec rollback and exits `6` after proven rollback or `7` on unproven recovery; it never emits success.

- [ ] **Step 9: When postactivation is green, execute the explicit rollback drill with immutable inputs.**

```powershell
Invoke-NativeChecked "explicit rollback drill" { & $Python scripts/activate_evb_build.py rollback --transaction-id $env:EVB_ROLLBACK_TRANSACTION_ID --committed-transaction eval/evb_real/activation/committed_transaction.v1.json --expected-transaction-sha256 $env:EVB_COMMITTED_TRANSACTION_SHA256 --promotion-authorization $env:EVB_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_AUTHORIZATION_SHA256 --postactivation-observation-bundle $env:EVB_POSTACTIVATION_OBSERVATION_PATH --expected-postactivation-observation-bundle-sha256 $env:EVB_POSTACTIVATION_OBSERVATION_SHA256 --output-root eval/evb_real/rollback }
$env:EVB_ROLLBACK_BUNDLE_PATH = "eval/evb_real/rollback/rollback_bundle_manifest.v1.json"
$env:EVB_ROLLBACK_BUNDLE_SHA256 = (Get-FileHash $env:EVB_ROLLBACK_BUNDLE_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
$RollbackRoot = (Resolve-Path (Split-Path $env:EVB_ROLLBACK_BUNDLE_PATH -Parent)).Path
$RollbackBundle = Get-Content -Raw $env:EVB_ROLLBACK_BUNDLE_PATH | ConvertFrom-Json
$env:EVB_ROLLED_BACK_POINTER_PATH = Resolve-BundleSidecarChecked $RollbackRoot $RollbackBundle "active_pointer_rolled_back"
$env:EVB_ROLLED_BACK_POINTER_SHA256 = (Get-FileHash $env:EVB_ROLLED_BACK_POINTER_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
$env:EVB_ROLLBACK_RUNTIME_PREFLIGHT_PATH = Resolve-BundleSidecarChecked $RollbackRoot $RollbackBundle "runtime_preflight"
$env:EVB_ROLLBACK_RUNTIME_PREFLIGHT_SHA256 = (Get-FileHash $env:EVB_ROLLBACK_RUNTIME_PREFLIGHT_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: rollback consumes the committed record, authorization, and observation-bundle hashes, validates the observed complete current pointer, then writes a create-new rollback bundle. The final postactivation bundle is not a rollback input, so no evidence cycle exists.

- [ ] **Step 10: Create a fresh reactivation authorization and reactivate without a build-version shortcut.**

```powershell
Invoke-NativeChecked "aggregate reactivation" { & $Python scripts/verify_evb_real_data.py aggregate-preactivation --state-bundle $env:EVB_ROLLBACK_BUNDLE_PATH --expected-state-bundle-sha256 $env:EVB_ROLLBACK_BUNDLE_SHA256 --build-manifest $env:EVB_BUILD_MANIFEST_PATH --expected-build-manifest-sha256 $env:EVB_BUILD_MANIFEST_SHA256 --minio-report $env:EVB_MINIO_REPORT_PATH --expected-minio-report-sha256 $env:EVB_MINIO_REPORT_SHA256 --vector-decision $env:EVB_VECTOR_DECISION --expected-vector-decision-sha256 $env:EVB_VECTOR_DECISION_SHA256 --runtime-preflight $env:EVB_ROLLBACK_RUNTIME_PREFLIGHT_PATH --expected-runtime-preflight-sha256 $env:EVB_ROLLBACK_RUNTIME_PREFLIGHT_SHA256 --output eval/evb_real/reactivation/report_manifest.v1.json }
$env:EVB_REACTIVATION_REPORT_SHA256 = (Get-FileHash -LiteralPath eval/evb_real/reactivation/report_manifest.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "authorize reactivation" { & $Python scripts/verify_evb_real_data.py authorize --report-manifest eval/evb_real/reactivation/report_manifest.v1.json --expected-report-manifest-sha256 $env:EVB_REACTIVATION_REPORT_SHA256 --rollback-bundle $env:EVB_ROLLBACK_BUNDLE_PATH --expected-rollback-bundle-sha256 $env:EVB_ROLLBACK_BUNDLE_SHA256 --expected-pointer $env:EVB_ROLLED_BACK_POINTER_PATH --expected-pointer-sha256 $env:EVB_ROLLED_BACK_POINTER_SHA256 --next-tuple $env:EVB_NEXT_TUPLE_PATH --expected-next-tuple-sha256 $env:EVB_NEXT_TUPLE_SHA256 --authorization-type reactivate --output $env:EVB_REACTIVATION_AUTHORIZATION_PATH }
$env:EVB_REACTIVATION_AUTHORIZATION_SHA256 = (Get-FileHash -LiteralPath $env:EVB_REACTIVATION_AUTHORIZATION_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-NativeChecked "reactivate authorized tuple" { & $Python scripts/activate_evb_build.py activate --transaction-id $env:EVB_REACTIVATE_TRANSACTION_ID --promotion-authorization $env:EVB_REACTIVATION_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_REACTIVATION_AUTHORIZATION_SHA256 --report-root eval/evb_real/reactivation/activation }
$env:EVB_REACTIVATION_COMMITTED_SHA256 = (Get-FileHash -LiteralPath eval/evb_real/reactivation/activation/committed_transaction.v1.json -Algorithm SHA256).Hash.ToLowerInvariant()
```

Expected: the fresh authorization binds the rolled-back complete pointer and the previously verified complete new tuple; prior authorization reuse is rejected.

- [ ] **Step 11: Postverify the reactivation and create the hash-only signoff.**

```powershell
Invoke-NativeChecked "reactivation postverify" { & $Python scripts/verify_evb_real_data.py postactivate --transaction-record eval/evb_real/reactivation/activation/committed_transaction.v1.json --expected-transaction-sha256 $env:EVB_REACTIVATION_COMMITTED_SHA256 --promotion-authorization $env:EVB_REACTIVATION_AUTHORIZATION_PATH --expected-authorization-sha256 $env:EVB_REACTIVATION_AUTHORIZATION_SHA256 --before-bundle $env:EVB_ROLLBACK_BUNDLE_PATH --expected-before-bundle-sha256 $env:EVB_ROLLBACK_BUNDLE_SHA256 --rollback-transaction-id $env:EVB_REACTIVATION_ROLLBACK_TRANSACTION_ID --output-root eval/evb_real/reactivation/postactivation } @(0,6,7)
switch ($script:LastNativeExitCode) {
  0 { }
  6 { throw "reactivation postverify red; automatic rollback proven, stop" }
  7 { throw "reactivation recovery unproven; escalate manual authoritative recovery" }
  default { throw "unexpected reactivation postverify exit code" }
}
```

Expected: a green outcome proves the reactivated tuple. Red automatically returns to the rolled-back tuple. Write `docs/superpowers/reports/2026-07-11-eventname-voice-binding-recovery-p0-signoff.json` containing only schema, build/experiment/transaction IDs, `PromotionOutcome` hash, report-manifest hash, rollback/reactivation terminal hashes, and completion time; no secret, MAC, raw query, local path, or bulky report content.

- [ ] **Step 12: Commit the safe staged signoff only via Section 1; if its path is dirty/mixed, mark `commit_deferred` and request user review.**

```powershell
$TaskId = "task-14"
$TaskFiles = @("docs/superpowers/reports/2026-07-11-eventname-voice-binding-recovery-p0-signoff.json")
# Run the Section 1 cached-diff audit with this exact allowlist.
if ($Staged.Count -gt 0) { Invoke-NativeChecked "task-14 commit safe files" { & git commit -m "test: record EVB P0 real gate signoff" } }
if ($DeferredFiles.Count -gt 0) { Write-Warning "task-14 commit_deferred: $($DeferredFiles -join ',')" }
```

Failure manifestation: any red/inconclusive gate is `F10`; do not promote, or rollback through `EVB-POINTER-P0-13` if routing changed.

## 4. Global P0 Hard Gates

| Gate | Required commands | Green evidence | Red action |
|---|---|---|---|
| `HG-01 Source/Baseline` | `C01`, `C13` | Immutable evidence and dynamic inventories | Stop before build |
| `HG-02 Binding/Conflict` | `C02`, `C03` | Exact-only bindings and complete closure | Stop mutation; continue read-only diagnosis |
| `HG-03 Artifacts/Parity` | `C04`, `C14` | v2/legacy schemas, zero excluded runtime rows, projection/BM25 parity | Do not build/promote |
| `HG-04 MinIO` | `C05`, `C17`, `C19`, `C20` | SDK pin, immutable one-use operation plan, `_execute` conditional create/app audit/readback, unchanged existing objects | Stop writes, expand read-only diagnosis, deny promotion |
| `HG-05 Runtime/API` | `C06`, read-only `C06F` | Safe registry/API/pagination and unchanged frontend compatibility tests | Contract conflict; no frontend edit and no activation |
| `HG-06 Shadow/Permissions` | `C07`, `C15`, `C21..C23`, `C32`, `C33` | Immutable preflight/intent/lifecycle plan, append-only unique name, exact principals/proxy, terminal evidence for every created collection | Retain active; unload or verify already-unloaded state for every created candidate exactly once |
| `HG-07 Experiment` | `C08`, `C15`, `C35`, `C24`, `C25`, `C32`, `C33` | Complete dev bundle, dev freeze, one held-out, all statistical and cleanup gates | Retain active; no second candidate |
| `HG-08 Pointer/Transaction` | `C09`, `C10`, `C16`, `C28..C31`, `C34` | Durable pointer/journal, authorization one-time claim, coordinator, authenticated immutable acks, epoch isolation, fresh-authorized reactivation postverification | Keep/restore authoritative epoch or enter conflict |
| `HG-09 Promotion` | `C11`, `C26`, `C27`, `C18`, `C30`, `C31`, `C34` | Green authorization plus acyclic observation/rollback/outcome and reactivation postverification | Deny activation or automatically roll back |
| `HG-10 Regression` | `C12` | Full existing suite green | Task incomplete |
| `HG-11 Real Data` | `C17..C35` as applicable | `R01..R10`, immutable bundles, lifecycle evidence, rollback drill, fresh-authorized reactivation, final outcome | Rollback/retain old tuple |

## 5. Real Environment Execution Order

1. Validate the single Task 0 baseline path/SHA/schema/source-inventory hash, then capture the create-new preflight bundle containing source, dev artifact, active collection, MinIO, deployment, runtime, capacity/ACL/owner, and current active tuple before inventories. Missing baseline evidence returns execution to Task 0; Task 14 never recaptures it.
2. Run the full automated suite and fake service/fault matrix.
3. Build isolated artifacts offline and verify parity.
4. Create and hash the immutable MinIO operation plan, then conditionally create only its verified missing objects through `_execute`; any evidence drift or reuse blocks before write.
5. Run vector `prepare`; when eligible run `intent` and `build-dev` for preregistered candidates, write the complete hash-pinned dev bundle, then `freeze`, one `held-out`, and unload every unselected/failed candidate through Task 14's loaded-candidate owner. A held-out failure ends the experiment.
6. Aggregate preactivation artifact/MinIO/vector/runtime evidence, create the immutable report manifest, then create and hash one promotion authorization bound to complete expected/next tuples.
7. Activate only with authorization path/hash; claim it once, acquire global coordinator, create immutable transaction snapshot/targets, prepare standby graphs, commit pointer/router epoch, and collect serving acks.
8. Run postactivation API/pagination/inventory verification and write the immutable observation bundle first. Green then writes successful `PromotionOutcome` and final postactivation bundle; red rolls back from the observation path/hash, writes the rollback bundle, and only then writes the failed/rolled-back outcome and final postactivation bundle.
9. For the drill, consume immutable committed transaction/authorization/current-pointer hashes, verify old tuple, then aggregate again and create a fresh reactivation authorization bound to the rolled-back pointer.
10. Reactivate with the fresh authorization, postverify, write the hash-only signoff, and run coverage/workspace self-checks.

## 6. Rollback Drill Acceptance

- [ ] Old activation tuple is captured from the active pointer before forward prepare.
- [ ] Rollback consumes exact committed transaction, original authorization, and current-pointer paths/SHA-256; no build-only or mutable evidence is accepted.
- [ ] Old collection stays online, loadable, and prewarm-capable throughout candidate work.
- [ ] Rollback journal reaches `rollback_preparing` before old graph preparation and `rolling_back` before pointer CAS.
- [ ] Every old target emits immutable authenticated `rollback_prepare` and `rollback_commit` acknowledgements.
- [ ] Pointer changes to the complete previous tuple before router changes to the previous epoch.
- [ ] New requests after router commit use only the previous tuple; in-flight requests finish on their pinned epoch.
- [ ] Journal reaches `rolled_back`; failure/unselected shadow collection is released/unloaded but not deleted.
- [ ] A fresh reactivation authorization binds the rolled-back pointer and verified complete new tuple before a fresh transaction can prepare/commit it.
- [ ] External pointer/router modification produces `conflict`; no transaction overwrites authoritative external state.

## 7. Completion Self-Check

- [ ] Every row in the P0 Coverage Matrix has a task, hard gate, exact command, real acceptance, and failure code.
- [ ] `C01..C35` and read-only `C06F` applicable commands pass with captured output.
- [ ] `R01..R10` evidence is present and hashed in the final report manifest.
- [ ] Protected `dev`, active-before collection payload, existing MinIO objects/policy, and non-EVB data are unchanged.
- [ ] Runtime media artifact contains exact voice plus not-applicable non-voice only.
- [ ] No production path calls the dangerous vectorstore or MinIO helpers.
- [ ] The real rollback and reactivation transactions both reach authenticated terminal states.
- [ ] Successful `PromotionOutcome` includes commit-ack and post API/inventory hashes; a post red outcome proves automatic rollback instead.
- [ ] Every collection reported created by `build-dev`, including partial/failure evidence that never reached load, has exactly one terminal lifecycle record: unselected/failed candidates are `unloaded_terminal` or verified `already_unloaded_terminal`, unload failures block promotion, and only a held-out-passing selected loaded candidate may remain `promotable_loaded` for activation.
- [ ] Authority/task-start snapshots and cached-diff audits prove no frontend, Wiki-owned hunk, pre-existing dirty hunk, or unrelated file was staged.
- [ ] No P1/P2 item below was implemented.

## 8. Deferred / Out of Scope

These items are recorded only and must not appear in implementation tasks or commits:

- `EVB-BIND-P1-01`: audited external-authority manual repair/signature workflow.
- `EVB-OBS-P1-01`: cross-build quality trend dashboard.
- `EVB-RUNTIME-P1-01`: user language preference ordering.
- `EVB-UI-P2-01`: skin/voice-pack filtering UI.
- `EVB-STORE-P2-01`: independent object-storage audit service.
- `EVB-VECTOR-P2-01`: manual audited deletion/drop cleanup of old or shadow collections.

## 9. P0 Coverage Matrix

The matrix uses command codes `C01..C35` plus read-only `C06F`, real-evidence codes `R01..R10`, and failure codes `F01..F10` defined in Section 3.

| Spec ID | Task | Hard gate | Command | Real acceptance | Failure |
|---|---:|---|---|---|---|
| `EVB-BASELINE-P0-01` | 0 | HG-01 | C01,C13 | R01 | F01 |
| `EVB-BASELINE-P0-02` | 0 | HG-01 | C01,C13 | R01 | F01 |
| `EVB-BASELINE-P0-03` | 0 | HG-01 | C01,C13 | R01 | F01 |
| `EVB-BASELINE-P0-04` | 0 | HG-01 | C01,C13 | R01 | F01 |
| `EVB-SCOPE-P0-01` | 0 | HG-01 | C01 | R01 | F01 |
| `EVB-SCOPE-P0-02` | 1 | HG-03 | C04,C14 | R04 | F04 |
| `EVB-SCOPE-P0-03` | 7 | HG-06 | C07,C17 | R07 | F07 |
| `EVB-SCOPE-P0-04` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-IDENT-P0-01` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-IDENT-P0-02` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-IDENT-P0-03` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-NAME-P0-01` | 1 | HG-02 | C02 | R02 | F02 |
| `EVB-NAME-P0-02` | 1 | HG-02 | C02 | R02 | F02 |
| `EVB-NAME-P0-03` | 1 | HG-02 | C02 | R02 | F02 |
| `EVB-NAME-P0-04` | 1 | HG-02 | C02 | R02 | F02 |
| `EVB-NAME-P0-05` | 1 | HG-02 | C02 | R02 | F02 |
| `EVB-BUILD-P0-01` | 1 | HG-03 | C04,C14 | R04 | F04 |
| `EVB-BUILD-P0-02` | 0 | HG-03 | C04,C14 | R04 | F04 |
| `EVB-BUILD-P0-03` | 1 | HG-03 | C04,C14 | R04 | F04 |
| `EVB-BIND-P0-01` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-BIND-P0-02` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-BIND-P0-03` | 2 | HG-02 | C02,C03 | R03 | F03 |
| `EVB-BIND-P0-04` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-BIND-P0-05` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-BIND-P0-06` | 2 | HG-02 | C02 | R02 | F02 |
| `EVB-ARTIFACT-P0-01` | 4 | HG-03 | C04 | R04 | F04 |
| `EVB-ARTIFACT-P0-02` | 4 | HG-03 | C04 | R04 | F04 |
| `EVB-ARTIFACT-P0-03` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-ARTIFACT-P0-04` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-ARTIFACT-P0-05` | 4 | HG-03 | C04 | R04 | F04 |
| `EVB-ARTIFACT-P0-06` | 2 | HG-03 | C02,C04 | R04 | F04 |
| `EVB-ARTIFACT-P0-07` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-ARTIFACT-P0-08` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-ARTIFACT-P0-09` | 4 | HG-03 | C04 | R04 | F04 |
| `EVB-ARTIFACT-P0-10` | 2 | HG-03 | C02,C04 | R04 | F04 |
| `EVB-ARTIFACT-P0-11` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-ARTIFACT-P0-12` | 4 | HG-03 | C04 | R04 | F04 |
| `EVB-ARTIFACT-P0-13` | 4 | HG-03 | C04 | R04 | F04 |
| `EVB-DIAG-P0-01` | 3 | HG-02 | C03 | R03 | F03 |
| `EVB-DIAG-P0-02` | 3 | HG-02 | C03 | R03 | F03 |
| `EVB-DIAG-P0-03` | 3 | HG-02 | C03 | R03 | F03 |
| `EVB-DIAG-P0-04` | 3 | HG-02 | C03 | R03 | F03 |
| `EVB-DIAG-P0-05` | 3 | HG-02 | C03 | R03 | F03 |
| `EVB-DIAG-P0-06` | 3 | HG-02 | C03 | R03 | F03 |
| `EVB-STORE-P0-01` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-02` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-03` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-04` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-05` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-06` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-07` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-08` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-STORE-P0-09` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-PARITY-P0-01` | 4 | HG-03 | C04,C14 | R04 | F04 |
| `EVB-PARITY-P0-02` | 4 | HG-03 | C04,C14 | R04 | F04 |
| `EVB-VECTOR-P0-01` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-03` | 12 | HG-09 | C11,C26,C27,C18 | R10 | F10 |
| `EVB-VECTOR-P0-04` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-05` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-06` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-07` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-08` | 7 | HG-06 | C07,C21,C22,C23,C32,C33 | R07 | F07 |
| `EVB-VECTOR-P0-09` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-13` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-14` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-15` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-16` | 8 | HG-07 | C08,C21,C35,C24,C25,C32,C33 | R08 | F08 |
| `EVB-VECTOR-P0-17` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-18` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-19` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-20` | 8 | HG-07 | C08,C21,C35,C24,C25,C32,C33 | R08 | F08 |
| `EVB-VECTOR-P0-21` | 8 | HG-07 | C08,C10,C28,C29 | R09 | F09 |
| `EVB-VECTOR-P0-22` | 8 | HG-07 | C08,C21,C35,C24,C25,C32,C33 | R08 | F08 |
| `EVB-VECTOR-P0-23` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-24` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-25` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-26` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-27` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-28` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-29` | 7 | HG-06 | C07,C21,C22,C23,C32,C33 | R07 | F07 |
| `EVB-VECTOR-P0-30` | 7 | HG-06 | C07,C21,C22,C23,C32,C33 | R07 | F07 |
| `EVB-VECTOR-P0-31` | 8 | HG-07 | C08,C21,C35,C24,C25 | R08 | F08 |
| `EVB-VECTOR-P0-32` | 7 | HG-06 | C07,C21,C22,C23 | R07 | F07 |
| `EVB-VECTOR-P0-33` | 7 | HG-06 | C07,C21,C22,C23,C32,C33 | R07 | F07 |
| `EVB-POINTER-P0-01` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-02` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-03` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-04` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-05` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-06` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-07` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-08` | 11 | HG-08 | C10,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-09` | 11 | HG-08 | C10,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-10` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-11` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-12` | 11 | HG-08 | C10,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-13` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-14` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-15` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-16` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-17` | 9 | HG-08 | C09 | R09 | F09 |
| `EVB-POINTER-P0-18` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-19` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-20` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-21` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-POINTER-P0-22` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-RUNTIME-P0-01` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-RUNTIME-P0-02` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-RUNTIME-P0-03` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-RUNTIME-P0-04` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-RUNTIME-P0-05` | 6 | HG-05 | C06 | R06 | F06 |
| `EVB-PAGE-P0-01` | 6 | HG-05 | C06,C06F | R06 | F06 |
| `EVB-PAGE-P0-02` | 6 | HG-05 | C06,C06F | R06 | F06 |
| `EVB-PAGE-P0-03` | 6 | HG-05 | C06,C06F | R06 | F06 |
| `EVB-PAGE-P0-04` | 6 | HG-05 | C06,C06F | R06 | F06 |
| `EVB-PAGE-P0-05` | 6 | HG-05 | C06,C06F | R06 | F06 |
| `EVB-OBS-P0-01` | 12 | HG-09 | C11,C18 | R10 | F10 |
| `EVB-OBS-P0-02` | 3 | HG-02 | C03,C18 | R03 | F03 |
| `EVB-SEC-P0-01` | 1 | HG-01 | C01,C02 | R01 | F01 |
| `EVB-SEC-P0-02` | 6 | HG-05 | C06,C11 | R06 | F06 |
| `EVB-SEC-P0-03` | 6 | HG-05 | C06,C11 | R06 | F06 |
| `EVB-SEC-P0-04` | 7 | HG-06 | C07 | R07 | F07 |
| `EVB-SEC-P0-05` | 10 | HG-08 | C09,C16 | R09 | F09 |
| `EVB-PROMOTE-P0-01` | 12 | HG-09 | C11,C26,C27,C18,C30,C31,C34 | R10 | F10 |
| `EVB-PROMOTE-P0-02` | 12 | HG-09 | C11,C26,C27,C18,C30,C31,C34 | R10 | F10 |
| `EVB-GATE-P0-01` | 2 | HG-02 | C02,C18 | R02 | F02 |
| `EVB-GATE-P0-02` | 2 | HG-02 | C02,C18 | R02 | F02 |
| `EVB-GATE-P0-03` | 2 | HG-02 | C02,C18 | R02 | F02 |
| `EVB-GATE-P0-04` | 3 | HG-02 | C03,C18 | R03 | F03 |
| `EVB-GATE-P0-05` | 5 | HG-04 | C05,C17,C19,C20 | R05 | F05 |
| `EVB-GATE-P0-06` | 5 | HG-04 | C05,C19,C20,C18 | R05 | F05 |
| `EVB-GATE-P0-07` | 7 | HG-06 | C07,C15,C21,C22,C23,C32,C33 | R07 | F07 |
| `EVB-GATE-P0-08` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-GATE-P0-09` | 11 | HG-08 | C10,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-GATE-P0-10` | 6 | HG-05 | C06,C18 | R06 | F06 |
| `EVB-GATE-P0-11` | 6 | HG-05 | C06,C18 | R06 | F06 |
| `EVB-GATE-P0-12` | 4 | HG-03 | C04,C18 | R04 | F04 |
| `EVB-GATE-P0-13` | 13 | HG-11 | C11,C26,C27,C18,C30,C31,C34 | R10 | F10 |
| `EVB-GATE-P0-14` | 5 | HG-04 | C05,C19,C20,C18 | R05 | F05 |
| `EVB-GATE-P0-15` | 7 | HG-06 | C07,C21,C22,C23,C32,C33,C18 | R07 | F07 |
| `EVB-GATE-P0-16` | 4 | HG-03 | C04,C18 | R04 | F04 |
| `EVB-GATE-P0-17` | 10 | HG-08 | C09,C10,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-GATE-P0-18` | 7 | HG-06 | C07,C15,C21,C22,C23,C32,C33 | R07 | F07 |
| `EVB-GATE-P0-19` | 11 | HG-08 | C10,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-GATE-P0-20` | 8 | HG-07 | C08,C15,C21,C35,C24,C25,C32,C33 | R08 | F08 |
| `EVB-GATE-P0-21` | 8 | HG-07 | C08,C15,C21,C35,C24,C25,C32,C33 | R08 | F08 |
| `EVB-GATE-P0-22` | 8 | HG-07 | C08,C15,C21,C35,C24,C25,C32,C33 | R08 | F08 |
| `EVB-GATE-P0-23` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
| `EVB-GATE-P0-24` | 10 | HG-08 | C09,C16,C28,C29,C30,C31,C34 | R09 | F09 |
