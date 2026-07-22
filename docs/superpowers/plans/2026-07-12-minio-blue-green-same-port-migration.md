# MinIO Blue-Green Same-Port Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current MinIO `RELEASE.2023-03-20T20-16-18Z` with the pinned and capability-proven `RELEASE.2025-09-07T16-13-09Z` while retaining host ports `9002/9003`, preserving every existing MinIO and Milvus object, and keeping a byte-for-byte rollback path.

**Architecture:** Perform two independent cold clones of the original MinIO data directory. Use the first clone for a full-data rehearsal on temporary ports; discard it from the cutover path after testing. During the final write-freeze window, create a fresh cutover clone, start the upgraded MinIO against only that clone on the original ports, and leave the old data directory untouched for rollback. Generate no 3,038-object upload plan until the upgraded target passes full inventory, Milvus, media-read, policy, and conditional-create capability gates.

**Tech Stack:** Windows PowerShell, Docker Compose, Docker Engine, MinIO `RELEASE.2023-03-20T20-16-18Z`, MinIO `RELEASE.2025-09-07T16-13-09Z`, `minio==7.2.20`, SHA-1/SHA-256, existing EVB R05/C19 tooling.

## Global Constraints

- Do not use `latest`; the only migration target is `minio/minio:RELEASE.2025-09-07T16-13-09Z`.
- Do not start the old MinIO binary against a directory that has ever been opened by the new binary.
- Do not start the new MinIO binary against the original `infra/milvus/volumes/minio` directory.
- Do not delete, overwrite, rename, or modify any existing object, bucket, bucket policy, lifecycle, versioning setting, ACL, or Docker volume.
- Capability probes use only registered keys under `_evb_capability_probe/`; probe objects remain registered and are not deleted.
- Preserve the Docker service/network identity `minio:9000` and application endpoint URLs `127.0.0.1:9002/9003` at final cutover.
- Preserve the current Compose publication semantics `9002:9000` and `9003:9001` (all host interfaces). Loopback-only binding is a separate security task and is not combined with this migration.
- Preserve the current MinIO credentials during migration. Credential rotation is a separate security task.
- The backup authority is restic repository `D:\1999Wiki_Backup\Repositories\1999wiki-data-local`, snapshot `3b23f722`; never inspect the repository as a plain restored directory.
- Preserve both current buckets, `.minio.sys`, and every object under `a-bucket` and `reverse1999-assets`.
- The authoritative pre-migration inventory is `eval/evb_real/minio_inventory/e9b97c6a24c4415aa6b071d79aec91b4/inventory.v1.json`, SHA-256 `d524f382a4bc95ebbf02a2022b1d92904fb26f97b11b9bfdebef439b6ebd9ba8`.
- The authoritative expanded reconciliation is SHA-256 `325afc748cc67af342848bbb22c0c4db96561d48cc2f0c9eef1f16de27f18714`: `same_hash=11819`, `missing_remote=3038`, `hash_mismatch=0`, `orphan_remote=6234`.
- The target prefix currently contains 18,054 objects: the original 18,053 plus the registered unconditional diagnostic control object.
- The 1,769 preliminary mismatches are diagnosed false positives caused by missing nonvoice `content_sha256`; they never enter conflict or upload-plan counts.
- The 6,234 orphan objects remain diagnostic-only and are never removed.
- Any hash mismatch, object disappearance, unregistered object addition, policy drift, Milvus failure, or capability failure immediately stops the migration and triggers rollback.
- Work directly in the current dirty tree without git staging, commits, reset, checkout, clean, or worktrees.

## File Structure

- Create during execution: `infra/milvus/docker-compose.minio-2025.yml` - temporary Compose override for the upgraded MinIO image and cutover data path.
- Create before service mutation: `scripts/minio_blue_green_evidence.py` - one-time typed CLI for canonical filesystem/object inventories, comparisons, capability probes, and receipts.
- Create before service mutation: `tests/test_minio_blue_green_evidence.py` - fake-client and filesystem tests for every evidence command.
- Create during execution: `infra/milvus/volumes/minio-2025-09-07-rehearsal/**` - disposable rehearsal clone; never used for final cutover.
- Create during execution: `infra/milvus/volumes/minio-2025-09-07-cutover/**` - fresh final clone; only the upgraded production MinIO may use it.
- Modify only after final acceptance: `infra/milvus/docker-compose.yml` - pin the accepted image and cutover volume path.
- Create evidence: `data/processed/huiji/evidence/minio-migration-20260712/**` - immutable migration, inventory, capability, cutover, and rollback receipts.
- Read only: `infra/milvus/volumes/minio/**` - original rollback data.
- Read only: `eval/evb_real/minio_inventory/e9b97c6a24c4415aa6b071d79aec91b4/**` - authoritative baseline inventory/reconciliation.

---

### Task 0: Implement the One-Time Evidence CLI

**Files:**
- Create: `scripts/minio_blue_green_evidence.py`
- Create: `tests/test_minio_blue_green_evidence.py`

**Interfaces:**
- Produces `filesystem-inventory --root PATH --output PATH` with canonical sorted `relative_path|size|sha256` records and create-new output.
- Produces `object-inventory --endpoint HOST:PORT --bucket NAME --prefix PREFIX --access-key-env NAME --secret-key-env NAME --output PATH` with key, size, SHA-1, SHA-256, ETag, nullable version/audit IDs, and policy summary.
- Produces `compare-files --expected PATH --actual PATH --output PATH` and `compare-objects --expected PATH --actual PATH --allow-added-key KEY --output PATH`; any unapproved addition, deletion, content/policy drift, duplicate, or malformed evidence exits 5.
- Produces `capability-probe --endpoint HOST:PORT --bucket NAME --prefix PREFIX --access-key-env NAME --secret-key-env NAME --output PATH`; it performs exactly one first conditional create and one same-key conflict request, retains/registers the object, and writes hash-pinned capability evidence only on complete success.
- Produces `receipt --schema NAME --status NAME --input LABEL=PATH --field NAME=VALUE --output PATH`; it verifies and embeds every input file SHA-256, rejects duplicate labels/fields, and writes a canonical create-new receipt.
- Produces `milvus-inventory --endpoint URI --database NAME --output PATH` with sorted collection names, schema/index fingerprints, row counts, load state, and a deterministic read-only query fingerprint derived from the first stored vector/document ID; `compare-milvus --expected PATH --actual PATH --output PATH` rejects any difference.
- Produces `media-samples --inventory PATH --base-url URL --asset-type voice --asset-type image --asset-type portrait --asset-type skill --output PATH`; it deterministically selects the lexically first key per type, performs HTTP GET, and verifies size/SHA-1/SHA-256 against inventory.
- Produces `reconcile-build --runtime-media PATH --raw-root PATH --inventory PATH --output PATH`; it computes local file SHA-1/SHA-256/size, classifies `same_hash`, `missing_remote`, `hash_mismatch`, and `orphan_remote`, records absent declared nonvoice SHA-256 separately, and exits 5 on any real mismatch.
- Produces `prepare-c19-evidence --artifact-root PATH --baseline PATH --current-inventory PATH --capability PATH --reconciliation PATH --output-root PATH`; it verifies all input hashes, copies the immutable R04 artifact set create-new, writes the exact build wrapper and MinIO-only preflight bundle with relative hash-pinned sidecars, and prints their paths/hashes.
- Every command writes canonical UTF-8 JSON with a trailing newline via create-new mode, prints the ordinary file SHA-256, and never calls delete, bucket setup, policy mutation, ordinary business PUT, or upload-plan code.

- [ ] **Step 1: Add named RED tests**

Add tests named:

```python
def test_filesystem_inventory_is_sorted_canonical_and_create_new(): ...
def test_object_inventory_hashes_streamed_content_and_policy(): ...
def test_compare_files_rejects_any_delta(): ...
def test_compare_objects_allows_only_registered_probe_additions(): ...
def test_capability_probe_requires_200_then_precondition_and_metadata_readback(): ...
def test_capability_probe_failure_writes_no_capability_sidecar(): ...
def test_cli_rejects_missing_credential_env_before_client(): ...
def test_receipt_hash_pins_every_named_input(): ...
def test_milvus_inventory_and_comparison_are_read_only_and_deterministic(): ...
def test_media_samples_are_deterministic_and_hash_verified(): ...
def test_reconcile_build_hashes_actual_local_bytes_and_separates_missing_declared_sha256(): ...
def test_prepare_c19_evidence_is_create_new_relative_and_hash_pinned(): ...
def test_source_contains_no_delete_or_bucket_mutation_calls(): ...
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_minio_blue_green_evidence.py -q
```

Expected: named tests fail because the CLI module does not exist.

- [ ] **Step 3: Implement the minimal CLI**

Use `argparse`, `hashlib`, canonical `json.dumps(..., sort_keys=True, separators=(",", ":"))`, `Path.open("xb")`, MinIO `list_objects/stat_object/get_object/get_bucket_policy`, and only the strict conditional `_execute` transport for the dedicated capability key. Credential values are read by environment-variable name and are never serialized or printed.

- [ ] **Step 4: Run GREEN and static gates**

```powershell
python -m pytest tests/test_minio_blue_green_evidence.py tests/test_evb_minio_strict.py tests/test_minio_shared_upload.py -q
python -m ruff check scripts/minio_blue_green_evidence.py tests/test_minio_blue_green_evidence.py
python -m py_compile scripts/minio_blue_green_evidence.py tests/test_minio_blue_green_evidence.py
```

Expected: all tests pass, Ruff passes, and py_compile exits 0. Do not continue to Task 1 while any gate is red.

### Task 0B: Align Historical Inventory Audit Semantics

**Files:**
- Modify: `src/huiji_rag/minio_strict.py`
- Modify: `tests/test_evb_minio_strict.py`

**Interfaces:**
- Historical/current `InventoryObject.application_operation_id` remains nullable and is preserved as `null` when absent.
- Probe and uploaded `ObjectEvidence.operation_audit_id` remains mandatory and exact.
- Bucket policy, ETag, key, size, SHA-1, and SHA-256 remain mandatory for every inventory object.

- [ ] **Step 1: Add RED tests**

```python
def test_historical_inventory_allows_missing_application_operation_id_but_keeps_etag_policy_and_hashes(): ...
def test_capture_inventory_preserves_missing_historical_audit_as_null(): ...
def test_probe_and_uploaded_evidence_still_require_operation_audit_id(): ...
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_evb_minio_strict.py -q
```

Expected: historical inventory cases fail under the old all-objects audit requirement.

- [ ] **Step 3: Implement the minimal contract correction**

Remove only the all-inventory-object application-ID rejection from JSON loading and live inventory capture. Do not weaken ETag/policy/hash requirements and do not change `attach_operation_evidence()` or uploaded/probe evidence validation.

- [ ] **Step 4: Run GREEN and neighboring gates**

```powershell
python -m pytest tests/test_evb_minio_strict.py tests/test_minio_shared_upload.py tests/test_minio_blue_green_evidence.py -q
python -m ruff check src/huiji_rag/minio_strict.py tests/test_evb_minio_strict.py scripts/minio_blue_green_evidence.py tests/test_minio_blue_green_evidence.py
python -m py_compile src/huiji_rag/minio_strict.py scripts/minio_blue_green_evidence.py
```

Expected: all gates pass before any service stop.

### Task 1: Freeze Inputs and Verify Backup

**Files:**
- Read: `infra/milvus/docker-compose.yml`
- Read: `infra/milvus/volumes/minio/**`
- Read: `eval/evb_real/minio_inventory/e9b97c6a24c4415aa6b071d79aec91b4/**`
- Create: `data/processed/huiji/evidence/minio-migration-20260712/preflight.v1.json`

**Interfaces:**
- Consumes: original data root, authoritative inventory hash, completed external backup.
- Produces: immutable preflight receipt authorizing rehearsal only.

- [ ] **Step 1: Define and resolve exact authorities**

```powershell
$Project = (Resolve-Path "D:\PycharmProjects\nlp\LangChain\1999Search").Path
$Compose = Join-Path $Project "infra\milvus\docker-compose.yml"
$Original = (Resolve-Path (Join-Path $Project "infra\milvus\volumes\minio")).Path
$ResticRepo = "D:\1999Wiki_Backup\Repositories\1999wiki-data-local"
$ResticSnapshot = "3b23f722"
$RestoreTest = "D:\1999Wiki_Backup\Restore_Tests\data\snapshot-3b23f722-volume-verify"
$BaselineInventory = Join-Path $Project "eval\evb_real\minio_inventory\e9b97c6a24c4415aa6b071d79aec91b4\inventory.v1.json"
$Evidence = Join-Path $Project "data\processed\huiji\evidence\minio-migration-20260712"
$Rehearsal = Join-Path $Project "infra\milvus\volumes\minio-2025-09-07-rehearsal"
$Cutover = Join-Path $Project "infra\milvus\volumes\minio-2025-09-07-cutover"
if (-not (Test-Path -LiteralPath (Join-Path $ResticRepo "config") -PathType Leaf)) { throw "Restic repository is missing" }
if ([string]::IsNullOrWhiteSpace($env:RESTIC_PASSWORD_FILE) -or -not (Test-Path -LiteralPath $env:RESTIC_PASSWORD_FILE -PathType Leaf)) { throw "RESTIC_PASSWORD_FILE is not configured" }
if ((Get-FileHash -LiteralPath $BaselineInventory -Algorithm SHA256).Hash.ToLowerInvariant() -ne "d524f382a4bc95ebbf02a2022b1d92904fb26f97b11b9bfdebef439b6ebd9ba8") { throw "Baseline inventory hash mismatch" }
if (Test-Path -LiteralPath $Rehearsal) { throw "Rehearsal target already exists" }
if (Test-Path -LiteralPath $Cutover) { throw "Cutover target already exists" }
New-Item -ItemType Directory -Path $Evidence -ErrorAction Stop | Out-Null
```

Expected: all paths resolve; restic repository and password-file authority exist; both clone destinations do not exist; evidence directory is create-new.

- [ ] **Step 2: Verify snapshot identity and required paths**

```powershell
$Snapshots = restic -r $ResticRepo --password-file $env:RESTIC_PASSWORD_FILE snapshots --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not ($Snapshots | Where-Object { $_.short_id -eq $ResticSnapshot -or $_.id.StartsWith($ResticSnapshot) })) { throw "Restic snapshot 3b23f722 is missing" }
$SnapshotPaths = restic -r $ResticRepo --password-file $env:RESTIC_PASSWORD_FILE ls $ResticSnapshot --json | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.struct_type -eq "node" } | ForEach-Object { $_.path }
foreach ($required in @(
    "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/minio",
    "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/etcd",
    "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/milvus",
    "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/mysql"
)) {
    if (-not ($SnapshotPaths | Where-Object { $_ -eq $required -or $_.StartsWith($required + "/") })) { throw "Snapshot is missing $required" }
}
```

Expected: exact snapshot exists and contains all four required data roots.

- [ ] **Step 3: Run repository integrity check**

```powershell
restic -r $ResticRepo --password-file $env:RESTIC_PASSWORD_FILE check
if ($LASTEXITCODE -ne 0) { throw "restic check failed" }
```

Expected: restic reports repository integrity success.

- [ ] **Step 4: Perform an isolated four-root file restore test**

```powershell
if (Test-Path -LiteralPath $RestoreTest) { throw "Full restore-test target already exists" }
restic -r $ResticRepo --password-file $env:RESTIC_PASSWORD_FILE restore $ResticSnapshot --target $RestoreTest `
  --include "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/minio" `
  --include "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/etcd" `
  --include "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/milvus" `
  --include "/D/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/volumes/mysql"
if ($LASTEXITCODE -ne 0) { throw "restic restore test failed" }
$RestoredVolumes = Join-Path $RestoreTest "D\PycharmProjects\nlp\LangChain\1999Search\infra\milvus\volumes"
foreach ($name in "minio", "etcd", "milvus", "mysql") {
    if (-not (Test-Path -LiteralPath (Join-Path $RestoredVolumes $name) -PathType Container)) { throw "Restore test is missing $name" }
}
python scripts/minio_blue_green_evidence.py filesystem-inventory --root (Join-Path $RestoredVolumes "minio") --output (Join-Path $Evidence "restic-restored-minio-files.v1.json")
```

Expected: all four roots restore as files into the isolated target; restored MinIO contains `.minio.sys`, `a-bucket`, and `reverse1999-assets`; canonical restored-file inventory is written. This does not prove that the restored etcd, Milvus, or MySQL data can boot, and must not be reported as a complete database recovery acceptance test.

- [ ] **Step 5: Verify the current container and endpoint identity**

```powershell
$Current = docker inspect milvus-main-minio | ConvertFrom-Json
if ($Current[0].Config.Image -ne "minio/minio:RELEASE.2023-03-20T20-16-18Z") { throw "Unexpected current MinIO image" }
if (($Current[0].Args -join " ") -notmatch "server /minio_data") { throw "Unexpected MinIO data authority" }
docker compose -f $Compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Current Compose config is invalid" }
```

Expected: old image and `/minio_data` authority match the diagnosed deployment.

Capture the pre-migration Milvus evidence while the current stack is healthy:

```powershell
python scripts/minio_blue_green_evidence.py milvus-inventory --endpoint http://127.0.0.1:19530 --database reverse1999_rag --output (Join-Path $Evidence "milvus-before.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Pre-migration Milvus inventory failed" }
```

- [ ] **Step 6: Pull and pin the exact target image**

```powershell
docker pull minio/minio:RELEASE.2025-09-07T16-13-09Z
if ($LASTEXITCODE -ne 0) { throw "Pinned MinIO image pull failed" }
$TargetImageId = docker image inspect minio/minio:RELEASE.2025-09-07T16-13-09Z --format "{{.Id}}"
if ([string]::IsNullOrWhiteSpace($TargetImageId)) { throw "Pinned MinIO image ID is unavailable" }
```

Expected: exact release tag is locally available; record its immutable image ID in preflight evidence.

- [ ] **Step 7: Write and hash the preflight receipt**

```powershell
python scripts/minio_blue_green_evidence.py receipt --schema evb.minio-migration-preflight/v1 --status ready_for_rehearsal `
  --input "restored_minio=$(Join-Path $Evidence 'restic-restored-minio-files.v1.json')" `
  --input "baseline_inventory=$BaselineInventory" `
  --input "milvus_before=$(Join-Path $Evidence 'milvus-before.v1.json')" `
  --field restic_repository=$ResticRepo `
  --field restic_snapshot=$ResticSnapshot `
  --field target_image_id=$TargetImageId `
  --field "compose_sha256=$((Get-FileHash -LiteralPath $Compose -Algorithm SHA256).Hash.ToLowerInvariant())" `
  --output (Join-Path $Evidence "preflight.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Preflight receipt failed" }
```

Expected: receipt and sidecar hash exist; no container or object mutation has occurred.

### Task 2: Create a Cold Rehearsal Clone

**Files:**
- Read only: `infra/milvus/volumes/minio/**`
- Create: `infra/milvus/volumes/minio-2025-09-07-rehearsal/**`
- Create: `data/processed/huiji/evidence/minio-migration-20260712/rehearsal-clone.v1.json`

**Interfaces:**
- Consumes: Task 1 preflight receipt.
- Produces: a consistent clone isolated from both original and final cutover roots.

- [ ] **Step 1: Stop services in strict dependency order and freeze source evidence**

```powershell
$Preflight = Join-Path $Evidence "preflight.v1.json"
$ExpectedPreflightSha = "0d75653c47e4a66955970308de87e9221876899db0e3a8f4e028327fdd455dce"
$ActualPreflightSha = (Get-FileHash -LiteralPath $Preflight -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualPreflightSha -ne $ExpectedPreflightSha) { throw "Task 1 preflight hash mismatch" }
$PreflightPayload = Get-Content -LiteralPath $Preflight -Raw | ConvertFrom-Json
if ($PreflightPayload.schema_version -ne "evb.minio-migration-preflight/v1" -or $PreflightPayload.status -ne "ready_for_rehearsal") { throw "Task 1 preflight does not authorize rehearsal" }
docker compose -f $Compose stop attu
if ($LASTEXITCODE -ne 0) { throw "Attu stop failed" }
docker compose -f $Compose stop -t 120 standalone
if ($LASTEXITCODE -ne 0) { throw "Milvus stop failed" }
$MilvusState = docker inspect milvus-main-standalone | ConvertFrom-Json
if ($MilvusState[0].State.Running -or $MilvusState[0].State.ExitCode -ne 0) { throw "Milvus did not stop cleanly" }
$OldInspect = docker inspect milvus-main-minio | ConvertFrom-Json
$EnvMap = @{}
foreach ($entry in $OldInspect[0].Config.Env) { $parts = $entry -split "=", 2; if ($parts.Count -eq 2) { $EnvMap[$parts[0]] = $parts[1] } }
$env:EVB_MIGRATION_ACCESS_KEY = $EnvMap["MINIO_ACCESS_KEY"]
$env:EVB_MIGRATION_SECRET_KEY = $EnvMap["MINIO_SECRET_KEY"]
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rehearsal-source-reverse1999.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Frozen reverse1999 source inventory failed" }
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket a-bucket --prefix "" --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rehearsal-source-a-bucket.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Frozen a-bucket source inventory failed" }
docker compose -f $Compose stop -t 120 minio
if ($LASTEXITCODE -ne 0) { throw "MinIO stop failed" }
$MinioState = docker inspect milvus-main-minio | ConvertFrom-Json
if ($MinioState[0].State.Running -or $MinioState[0].State.ExitCode -ne 0) { throw "MinIO did not stop cleanly" }
python scripts/minio_blue_green_evidence.py filesystem-inventory --root $Original --output (Join-Path $Evidence "rehearsal-source-files.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Frozen source filesystem inventory failed" }
```

Expected: Attu stops first; Milvus exits 0 within 120 seconds; both API inventories are captured after Milvus stops; MinIO exits 0 within 120 seconds; frozen filesystem inventory is captured while MinIO is stopped.

- [ ] **Step 2: Create the rehearsal clone while the old server is stopped**

```powershell
New-Item -ItemType Directory -Path $Rehearsal -ErrorAction Stop | Out-Null
robocopy $Original $Rehearsal /MIR /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XJ
if ($LASTEXITCODE -gt 7) { throw "Rehearsal clone failed with robocopy exit $LASTEXITCODE" }
foreach ($name in ".minio.sys", "a-bucket", "reverse1999-assets") {
    if (-not (Test-Path -LiteralPath (Join-Path $Rehearsal $name))) { throw "Rehearsal clone is missing $name" }
}
```

Expected: the clone contains all three roots and is independent of the original path.

- [ ] **Step 3: Restart only the old production path after cloning**

```powershell
docker compose -f $Compose up -d minio standalone attu
if ($LASTEXITCODE -ne 0) { throw "Failed to restore old production services after clone" }
```

Expected: old MinIO returns on `9002/9003` using the untouched original directory.

- [ ] **Step 4: Compare the clone with frozen source evidence**

```powershell
python scripts/minio_blue_green_evidence.py filesystem-inventory --root $Rehearsal --output (Join-Path $Evidence "rehearsal-clone-files.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal clone inventory failed" }
python scripts/minio_blue_green_evidence.py compare-files --expected (Join-Path $Evidence "rehearsal-source-files.v1.json") --actual (Join-Path $Evidence "rehearsal-clone-files.v1.json") --output (Join-Path $Evidence "rehearsal-clone-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal clone differs from frozen source" }
```

Expected: source and clone file sets, sizes, and SHA-256 values are identical. Later rehearsal comparisons use the frozen API inventories, never the restarted production instance.

- [ ] **Step 5: Write the hash-pinned rehearsal clone receipt**

```powershell
python scripts/minio_blue_green_evidence.py receipt --schema evb.minio-rehearsal-clone/v1 --status rehearsal_clone_ready `
  --input "preflight=$(Join-Path $Evidence 'preflight.v1.json')" `
  --input "reverse1999_source=$(Join-Path $Evidence 'rehearsal-source-reverse1999.v1.json')" `
  --input "a_bucket_source=$(Join-Path $Evidence 'rehearsal-source-a-bucket.v1.json')" `
  --input "source_files=$(Join-Path $Evidence 'rehearsal-source-files.v1.json')" `
  --input "clone_files=$(Join-Path $Evidence 'rehearsal-clone-files.v1.json')" `
  --input "clone_comparison=$(Join-Path $Evidence 'rehearsal-clone-comparison.v1.json')" `
  --field source_path=infra/milvus/volumes/minio `
  --field clone_path=infra/milvus/volumes/minio-2025-09-07-rehearsal `
  --output (Join-Path $Evidence "rehearsal-clone.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal clone receipt failed" }
```

Expected: receipt status is `rehearsal_clone_ready` and every Task 2 authority is bound by SHA-256 before Task 3.

### Task 3: Rehearse the Upgrade on Temporary Ports

**Files:**
- Create: `data/processed/huiji/evidence/minio-migration-20260712/rehearsal-validation.v1.json`
- Read/write only in rehearsal clone: `infra/milvus/volumes/minio-2025-09-07-rehearsal/**`

**Interfaces:**
- Consumes: rehearsal clone.
- Produces: proof that the pinned image can open the copied storage and preserve both buckets.

- [ ] **Step 1: Start the pinned image against the rehearsal clone**

```powershell
$OldInspect = docker inspect milvus-main-minio | ConvertFrom-Json
$EnvMap = @{}
foreach ($entry in $OldInspect[0].Config.Env) { $parts = $entry -split "=", 2; if ($parts.Count -eq 2) { $EnvMap[$parts[0]] = $parts[1] } }
docker run -d --name evb-minio-full-rehearsal --network milvus-main-network -p 127.0.0.1:19012:9000 -p 127.0.0.1:19013:9001 `
  -e "MINIO_ROOT_USER=$($EnvMap['MINIO_ACCESS_KEY'])" `
  -e "MINIO_ROOT_PASSWORD=$($EnvMap['MINIO_SECRET_KEY'])" `
  -v "${Rehearsal}:/minio_data" minio/minio:RELEASE.2025-09-07T16-13-09Z server /minio_data --console-address ":9001"
if ($LASTEXITCODE -ne 0) { throw "Failed to start rehearsal MinIO" }
```

Expected: only the rehearsal container binds `19012/19013`; production remains on `9002/9003`.

- [ ] **Step 2: Verify readiness and image identity**

```powershell
$RehearsalHealthy = $false
for ($i = 0; $i -lt 30; $i++) {
    curl.exe --noproxy "*" --fail --silent "http://127.0.0.1:19012/minio/health/live" | Out-Null; if ($LASTEXITCODE -eq 0) { $RehearsalHealthy = $true; break }; Start-Sleep -Seconds 2
}
if (-not $RehearsalHealthy) { throw "Rehearsal MinIO health check timed out" }
$RehearsalInspect = docker inspect evb-minio-full-rehearsal | ConvertFrom-Json
if ($RehearsalInspect[0].Config.Image -ne "minio/minio:RELEASE.2025-09-07T16-13-09Z") { throw "Rehearsal image drift" }
```

Expected: health endpoint succeeds and image is exactly pinned.

- [ ] **Step 3: Run full read-only inventory on both buckets**

```powershell
$env:EVB_MIGRATION_ACCESS_KEY = $EnvMap["MINIO_ACCESS_KEY"]
$env:EVB_MIGRATION_SECRET_KEY = $EnvMap["MINIO_SECRET_KEY"]
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:19012 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rehearsal-target-reverse1999.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal reverse1999 inventory failed" }
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:19012 --bucket a-bucket --prefix "" --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rehearsal-target-a-bucket.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal a-bucket inventory failed" }
python scripts/minio_blue_green_evidence.py compare-objects --expected (Join-Path $Evidence "rehearsal-source-reverse1999.v1.json") --actual (Join-Path $Evidence "rehearsal-target-reverse1999.v1.json") --output (Join-Path $Evidence "rehearsal-reverse1999-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal reverse1999 comparison failed" }
python scripts/minio_blue_green_evidence.py compare-objects --expected (Join-Path $Evidence "rehearsal-source-a-bucket.v1.json") --actual (Join-Path $Evidence "rehearsal-target-a-bucket.v1.json") --output (Join-Path $Evidence "rehearsal-a-bucket-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal a-bucket comparison failed" }
```

Expected:

```text
reverse1999/ prefix object count = 18054
original 18053 objects = unchanged
registered unconditional control object = present and exact
unregistered additions = 0
missing objects = 0
hash mismatches = 0
policy drift = 0
```

For `a-bucket`, use only the frozen `$Evidence\rehearsal-source-a-bucket.v1.json` captured after Milvus stopped; never compare against restarted production state.

- [ ] **Step 4: Run a rehearsal capability probe**

```powershell
python scripts/minio_blue_green_evidence.py capability-probe --endpoint 127.0.0.1:19012 --bucket reverse1999-assets --prefix reverse1999/_evb_capability_probe --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rehearsal-minio-capability.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal capability probe failed" }
```

Expected: all capability checks pass. Failure stops the plan before final cutover.

- [ ] **Step 5: Verify the complete Milvus object-store projection**

Use the already generated `$Evidence\rehearsal-a-bucket-comparison.v1.json`, which compares against the frozen source inventory by bucket policy, sorted object-key set, size, SHA-1, SHA-256, ETag presence, and nullable version ID. Do not start a temporary Milvus against production etcd and do not modify any Milvus collection.

Expected: complete `a-bucket` object and policy delta is zero. This proves storage migration fidelity only; the real Milvus process/query gate remains mandatory during the reversible same-port cutover window in Task 5.

- [ ] **Step 6: Write rehearsal validation evidence**

```powershell
python scripts/minio_blue_green_evidence.py receipt --schema evb.minio-rehearsal-validation/v1 --status allowed_for_cutover `
  --input "source_files=$(Join-Path $Evidence 'rehearsal-source-files.v1.json')" `
  --input "clone_comparison=$(Join-Path $Evidence 'rehearsal-clone-comparison.v1.json')" `
  --input "reverse1999_comparison=$(Join-Path $Evidence 'rehearsal-reverse1999-comparison.v1.json')" `
  --input "a_bucket_comparison=$(Join-Path $Evidence 'rehearsal-a-bucket-comparison.v1.json')" `
  --input "capability=$(Join-Path $Evidence 'rehearsal-minio-capability.v1.json')" `
  --field target_image=minio/minio:RELEASE.2025-09-07T16-13-09Z `
  --output (Join-Path $Evidence "rehearsal-validation.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rehearsal receipt failed" }
$RehearsalReceipt = Join-Path $Evidence "rehearsal-validation.v1.json"
$RehearsalPin = Join-Path $Evidence "rehearsal-validation.v1.json.sha256"
$RehearsalSha = (Get-FileHash -LiteralPath $RehearsalReceipt -Algorithm SHA256).Hash.ToLowerInvariant()
$PinStream = [System.IO.File]::Open($RehearsalPin, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
try {
    $PinBytes = [System.Text.Encoding]::ASCII.GetBytes($RehearsalSha + "`n")
    $PinStream.Write($PinBytes, 0, $PinBytes.Length)
} finally { $PinStream.Dispose() }
```

Expected: receipt status is exactly `allowed_for_cutover`; cutover is forbidden if any named evidence is absent or red.

### Task 4: Create the Final Cutover Clone Under Write Freeze

**Files:**
- Read only: `infra/milvus/volumes/minio/**`
- Create: `infra/milvus/volumes/minio-2025-09-07-cutover/**`
- Create: `infra/milvus/docker-compose.minio-2025.yml`
- Create: `data/processed/huiji/evidence/minio-migration-20260712/cutover-clone.v1.json`

**Interfaces:**
- Consumes: `allowed_for_cutover=true` rehearsal evidence.
- Produces: fresh final clone and same-port Compose override.

- [ ] **Step 1: Verify rehearsal authorization and stop all MinIO consumers**

Verify the rehearsal evidence file hash and `allowed_for_cutover` status with these executable gates, then run:

```powershell
$RehearsalReceipt = Join-Path $Evidence "rehearsal-validation.v1.json"
$RehearsalPin = Join-Path $Evidence "rehearsal-validation.v1.json.sha256"
$ExpectedRehearsalSha = (Get-Content -LiteralPath $RehearsalPin -Raw).Trim()
if ($ExpectedRehearsalSha -notmatch '^[0-9a-f]{64}$') { throw "Invalid rehearsal authorization hash pin" }
$ActualRehearsalSha = (Get-FileHash -LiteralPath $RehearsalReceipt -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualRehearsalSha -ne $ExpectedRehearsalSha) { throw "Rehearsal authorization hash mismatch" }
$RehearsalAuthorization = Get-Content -LiteralPath $RehearsalReceipt -Raw | ConvertFrom-Json
if ($RehearsalAuthorization.schema_version -ne "evb.minio-rehearsal-validation/v1" -or $RehearsalAuthorization.status -ne "allowed_for_cutover") { throw "Rehearsal is not authorized for cutover" }
docker compose -f $Compose stop attu
if ($LASTEXITCODE -ne 0) { throw "Attu stop failed" }
docker compose -f $Compose stop -t 120 standalone
if ($LASTEXITCODE -ne 0) { throw "Milvus stop failed" }
$MilvusState = docker inspect milvus-main-standalone | ConvertFrom-Json
if ($MilvusState[0].State.Running -or $MilvusState[0].State.ExitCode -ne 0) { throw "Milvus did not stop cleanly" }
$OldInspect = docker inspect milvus-main-minio | ConvertFrom-Json
$EnvMap = @{}
foreach ($entry in $OldInspect[0].Config.Env) { $parts = $entry -split "=", 2; if ($parts.Count -eq 2) { $EnvMap[$parts[0]] = $parts[1] } }
$env:EVB_MIGRATION_ACCESS_KEY = $EnvMap["MINIO_ACCESS_KEY"]
$env:EVB_MIGRATION_SECRET_KEY = $EnvMap["MINIO_SECRET_KEY"]
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "cutover-source-reverse1999.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Final reverse1999 source inventory failed" }
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket a-bucket --prefix "" --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "cutover-source-a-bucket.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Final a-bucket source inventory failed" }
docker compose -f $Compose stop -t 120 minio
if ($LASTEXITCODE -ne 0) { throw "MinIO stop failed" }
$MinioState = docker inspect milvus-main-minio | ConvertFrom-Json
if ($MinioState[0].State.Running -or $MinioState[0].State.ExitCode -ne 0) { throw "MinIO did not stop cleanly" }
```

Expected: final write freeze is active. Do not restart the old services before the cutover decision.

- [ ] **Step 2: Capture final source inventory before copying**

```powershell
python scripts/minio_blue_green_evidence.py filesystem-inventory --root $Original --output (Join-Path $Evidence "cutover-source-files.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Final source filesystem inventory failed" }
```

Expected: `.minio.sys`, `a-bucket`, and `reverse1999-assets` are present; no files change during capture.

- [ ] **Step 3: Create a fresh final clone**

```powershell
New-Item -ItemType Directory -Path $Cutover -ErrorAction Stop | Out-Null
robocopy $Original $Cutover /MIR /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XJ
if ($LASTEXITCODE -gt 7) { throw "Cutover clone failed with robocopy exit $LASTEXITCODE" }
```

```powershell
python scripts/minio_blue_green_evidence.py filesystem-inventory --root $Cutover --output (Join-Path $Evidence "cutover-clone-files.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Cutover clone inventory failed" }
python scripts/minio_blue_green_evidence.py compare-files --expected (Join-Path $Evidence "cutover-source-files.v1.json") --actual (Join-Path $Evidence "cutover-clone-files.v1.json") --output (Join-Path $Evidence "cutover-clone-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Cutover clone differs from frozen source" }
```

Expected: source and clone file inventories are byte-identical.

- [ ] **Step 4: Create and validate the temporary Compose override**

Create `infra/milvus/docker-compose.minio-2025.yml` with exactly:

```yaml
services:
  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - ./volumes/minio-2025-09-07-cutover:/minio_data
```

Then run:

```powershell
$Override = Join-Path $Project "infra\milvus\docker-compose.minio-2025.yml"
docker compose -f $Compose -f $Override config --quiet
if ($LASTEXITCODE -ne 0) { throw "Merged cutover Compose is invalid" }
docker compose -f $Compose -f $Override config | Select-String "RELEASE.2025-09-07T16-13-09Z|minio-2025-09-07-cutover|9002:9000|9003:9001"
```

Expected: merged config retains service name `minio`, network `milvus-main-network`, container name `milvus-main-minio`, and original host ports.

### Task 5: Same-Port Cutover and Hard Gates

**Files:**
- Create: `data/processed/huiji/evidence/minio-migration-20260712/cutover-validation.v1.json`
- Create on success: hash-pinned `minio_capability.v1.json` in the R05 preflight bundle.
- Execute: `scripts/minio_blue_green_cutover.ps1`

**Interfaces:**
- Consumes: byte-identical final clone and valid Compose override.
- Produces: accepted upgraded MinIO at the unchanged endpoint or an immediate rollback decision.

The only executable Task 5 entry point is:

```powershell
& (Join-Path $Project "scripts\minio_blue_green_cutover.ps1") -Project $Project -Evidence $Evidence
if ($LASTEXITCODE -ne 0) { throw "Cutover wrapper failed after automatic rollback handling" }
```

The wrapper assigns `$FailedGate` before each gate and executes all steps below inside one `try/catch`. Its catch invokes `scripts/minio_blue_green_rollback.ps1 -FailedGate $FailedGate`; the inline commands below are audit documentation and must not be executed independently.

- [ ] **Step 1: Recreate MinIO with the pinned image and unchanged ports**

```powershell
docker compose -f $Compose -f $Override up -d --force-recreate minio
if ($LASTEXITCODE -ne 0) { throw "New MinIO failed to start" }
```

Expected: only one container named `milvus-main-minio` exists; it uses the pinned image, cutover clone, `9002/9003`, and network alias `minio`.

- [ ] **Step 2: Verify health before starting Milvus**

```powershell
$CutoverMinioHealthy = $false
for ($i = 0; $i -lt 30; $i++) {
    curl.exe --noproxy "*" --fail --silent "http://127.0.0.1:9002/minio/health/live" | Out-Null; if ($LASTEXITCODE -eq 0) { $CutoverMinioHealthy = $true; break }; Start-Sleep -Seconds 2
}
if (-not $CutoverMinioHealthy) { throw "Cutover MinIO health check timed out" }
$Running = docker inspect milvus-main-minio | ConvertFrom-Json
if ($Running[0].Config.Image -ne "minio/minio:RELEASE.2025-09-07T16-13-09Z") { throw "Cutover image mismatch" }
```

Expected: health succeeds and image identity is exact.

- [ ] **Step 3: Capture and compare full post-upgrade inventory**

```powershell
$RunningEnv = @{}
foreach ($entry in $Running[0].Config.Env) { $parts = $entry -split "=", 2; if ($parts.Count -eq 2) { $RunningEnv[$parts[0]] = $parts[1] } }
$env:EVB_MIGRATION_ACCESS_KEY = $RunningEnv["MINIO_ROOT_USER"]
$env:EVB_MIGRATION_SECRET_KEY = $RunningEnv["MINIO_ROOT_PASSWORD"]
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "cutover-target-reverse1999-before-probe.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Cutover reverse1999 inventory failed" }
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket a-bucket --prefix "" --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "cutover-target-a-bucket.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Cutover a-bucket inventory failed" }
python scripts/minio_blue_green_evidence.py compare-objects --expected (Join-Path $Evidence "cutover-source-reverse1999.v1.json") --actual (Join-Path $Evidence "cutover-target-reverse1999-before-probe.v1.json") --output (Join-Path $Evidence "cutover-reverse1999-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Cutover reverse1999 drift" }
python scripts/minio_blue_green_evidence.py compare-objects --expected (Join-Path $Evidence "cutover-source-a-bucket.v1.json") --actual (Join-Path $Evidence "cutover-target-a-bucket.v1.json") --output (Join-Path $Evidence "cutover-a-bucket-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Cutover a-bucket drift" }
```

Expected:

```text
original 18053 reverse1999/ objects unchanged
registered unconditional control object unchanged
unregistered additions = 0
missing objects = 0
hash mismatches = 0
a-bucket object/hash/policy delta = 0
```

Any difference immediately invokes Task 6 rollback.

- [ ] **Step 4: Run the final target capability probe**

```powershell
python scripts/minio_blue_green_evidence.py capability-probe --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999/_evb_capability_probe --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "minio_capability.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Final capability probe failed" }
```

Expected: generate hash-pinned `minio_capability.v1.json` only when all checks pass. The new registered probe is the only allowed post-inventory addition.

- [ ] **Step 5: Start Milvus and verify health/readability**

```powershell
docker compose -f $Compose -f $Override up -d standalone attu
if ($LASTEXITCODE -ne 0) { throw "Milvus or Attu failed to start" }
$MilvusHealthy = $false
for ($i = 0; $i -lt 45; $i++) {
    curl.exe --noproxy "*" --fail --silent "http://127.0.0.1:19091/healthz" | Out-Null; if ($LASTEXITCODE -eq 0) { $MilvusHealthy = $true; break }; Start-Sleep -Seconds 2
}
if (-not $MilvusHealthy) { throw "Milvus health check timed out" }
python scripts/minio_blue_green_evidence.py milvus-inventory --endpoint http://127.0.0.1:19530 --database reverse1999_rag --output (Join-Path $Evidence "milvus-after.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Post-cutover Milvus inventory failed" }
python scripts/minio_blue_green_evidence.py compare-milvus --expected (Join-Path $Evidence "milvus-before.v1.json") --actual (Join-Path $Evidence "milvus-after.v1.json") --output (Join-Path $Evidence "milvus-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Milvus post-cutover drift" }
```

Expected: health succeeds; collection names, schemas, indexes, row counts, load states, and deterministic query fingerprints match pre-cutover evidence.

- [ ] **Step 6: Verify project media reads at the unchanged endpoint**

```powershell
python scripts/minio_blue_green_evidence.py media-samples --inventory (Join-Path $Evidence "cutover-target-reverse1999-before-probe.v1.json") --base-url http://127.0.0.1:9002/reverse1999-assets --asset-type voice --asset-type image --asset-type portrait --asset-type skill --output (Join-Path $Evidence "media-samples-after.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Post-cutover media sample verification failed" }
```

Expected: endpoint and URLs are unchanged; all samples match.

- [ ] **Step 7: Write cutover validation evidence**

```powershell
python scripts/minio_blue_green_evidence.py receipt --schema evb.minio-cutover-validation/v1 --status cutover_accepted `
  --input "reverse1999_comparison=$(Join-Path $Evidence 'cutover-reverse1999-comparison.v1.json')" `
  --input "a_bucket_comparison=$(Join-Path $Evidence 'cutover-a-bucket-comparison.v1.json')" `
  --input "capability=$(Join-Path $Evidence 'minio_capability.v1.json')" `
  --input "milvus_comparison=$(Join-Path $Evidence 'milvus-comparison.v1.json')" `
  --input "media_samples=$(Join-Path $Evidence 'media-samples-after.v1.json')" `
  --field target_image=minio/minio:RELEASE.2025-09-07T16-13-09Z `
  --field host_ports=9002:9000,9003:9001 `
  --output (Join-Path $Evidence "cutover-validation.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Cutover receipt failed" }
```

### Task 6: Roll Back on Any Red Gate

**Files:**
- Create only on rollback: `data/processed/huiji/evidence/minio-migration-20260712/rollback.v1.json`
- Read only: `infra/milvus/volumes/minio/**`
- Execute: `scripts/minio_blue_green_rollback.ps1`
- Read only: `infra/milvus/docker-compose.minio-2023-rollback.yml`

**Interfaces:**
- Consumes: any red cutover gate.
- Produces: restored old MinIO at the original ports using the untouched original data directory.

The canonical rollback entry point is:

```powershell
& (Join-Path $Project "scripts\minio_blue_green_rollback.ps1") -Project $Project -Evidence $Evidence -FailedGate $FailedGate
if ($LASTEXITCODE -ne 0) { throw "Rollback procedure failed" }
```

The following steps document that script's required behavior. Do not substitute the mutable base Compose.

- [ ] **Step 1: Stop upgraded consumers and MinIO**

```powershell
docker compose -f $Compose -f $Override stop attu
docker compose -f $Compose -f $Override stop -t 120 standalone
$MilvusState = docker inspect milvus-main-standalone | ConvertFrom-Json
if ($MilvusState[0].State.Running -or $MilvusState[0].State.ExitCode -ne 0) { throw "Milvus did not stop cleanly during rollback" }
docker compose -f $Compose -f $Override stop -t 120 minio
$MinioState = docker inspect milvus-main-minio | ConvertFrom-Json
if ($MinioState[0].State.Running -or $MinioState[0].State.ExitCode -ne 0) { throw "MinIO did not stop cleanly during rollback" }
```

- [ ] **Step 2: Recreate the old service from the immutable rollback Compose**

```powershell
$RollbackCompose = Join-Path $Project "infra\milvus\docker-compose.minio-2023-rollback.yml"
docker compose -f $RollbackCompose up -d --force-recreate minio standalone attu
if ($LASTEXITCODE -ne 0) { throw "Rollback service recreation failed" }
```

Expected: old image is restored on `9002/9003`, using only `infra/milvus/volumes/minio`.

- [ ] **Step 3: Verify rollback state**

```powershell
$RollbackMinioHealthy = $false
for ($i = 0; $i -lt 30; $i++) {
    curl.exe --noproxy "*" --fail --silent "http://127.0.0.1:9002/minio/health/live" | Out-Null; if ($LASTEXITCODE -eq 0) { $RollbackMinioHealthy = $true; break }; Start-Sleep -Seconds 2
}
if (-not $RollbackMinioHealthy) { throw "Rollback MinIO health check timed out" }
$RollbackMilvusHealthy = $false
for ($i = 0; $i -lt 45; $i++) {
    curl.exe --noproxy "*" --fail --silent "http://127.0.0.1:19091/healthz" | Out-Null; if ($LASTEXITCODE -eq 0) { $RollbackMilvusHealthy = $true; break }; Start-Sleep -Seconds 2
}
if (-not $RollbackMilvusHealthy) { throw "Rollback Milvus health check timed out" }
$RollbackInspect = docker inspect milvus-main-minio | ConvertFrom-Json
if ($RollbackInspect[0].Config.Image -ne "minio/minio:RELEASE.2023-03-20T20-16-18Z") { throw "Rollback image mismatch" }
$RollbackEnv = @{}
foreach ($entry in $RollbackInspect[0].Config.Env) { $parts = $entry -split "=", 2; if ($parts.Count -eq 2) { $RollbackEnv[$parts[0]] = $parts[1] } }
$env:EVB_MIGRATION_ACCESS_KEY = $RollbackEnv["MINIO_ACCESS_KEY"]
$env:EVB_MIGRATION_SECRET_KEY = $RollbackEnv["MINIO_SECRET_KEY"]
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rollback-minio-inventory.v1.json")
python scripts/minio_blue_green_evidence.py compare-objects --expected (Join-Path $Evidence "cutover-source-reverse1999.v1.json") --actual (Join-Path $Evidence "rollback-minio-inventory.v1.json") --output (Join-Path $Evidence "rollback-minio-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rollback MinIO inventory differs" }
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket a-bucket --prefix "" --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rollback-a-bucket-inventory.v1.json")
python scripts/minio_blue_green_evidence.py compare-objects --expected (Join-Path $Evidence "cutover-source-a-bucket.v1.json") --actual (Join-Path $Evidence "rollback-a-bucket-inventory.v1.json") --output (Join-Path $Evidence "rollback-a-bucket-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rollback a-bucket inventory differs" }
python scripts/minio_blue_green_evidence.py milvus-inventory --endpoint http://127.0.0.1:19530 --database reverse1999_rag --output (Join-Path $Evidence "rollback-milvus-inventory.v1.json")
python scripts/minio_blue_green_evidence.py compare-milvus --expected (Join-Path $Evidence "milvus-before.v1.json") --actual (Join-Path $Evidence "rollback-milvus-inventory.v1.json") --output (Join-Path $Evidence "rollback-milvus-comparison.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rollback Milvus inventory differs" }
python scripts/minio_blue_green_evidence.py media-samples --inventory (Join-Path $Evidence "rollback-minio-inventory.v1.json") --base-url http://127.0.0.1:9002/reverse1999-assets --asset-type voice --asset-type image --asset-type portrait --asset-type skill --output (Join-Path $Evidence "rollback-media-samples.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rollback media samples failed" }
```

Do not copy any file from the upgraded cutover directory back into the original directory.

- [ ] **Step 4: Write rollback receipt**

```powershell
python scripts/minio_blue_green_evidence.py receipt --schema evb.minio-migration-rollback/v1 --status rollback_complete `
  --input "minio=$(Join-Path $Evidence 'rollback-minio-comparison.v1.json')" `
  --input "a_bucket=$(Join-Path $Evidence 'rollback-a-bucket-comparison.v1.json')" `
  --input "milvus=$(Join-Path $Evidence 'rollback-milvus-comparison.v1.json')" `
  --input "media=$(Join-Path $Evidence 'rollback-media-samples.v1.json')" `
  --field failed_gate=$FailedGate `
  --field old_image=minio/minio:RELEASE.2023-03-20T20-16-18Z `
  --field endpoint=127.0.0.1:9002 `
  --output (Join-Path $Evidence "rollback.v1.json")
if ($LASTEXITCODE -ne 0) { throw "Rollback receipt failed" }
```

Stop execution; do not generate capability evidence or an operation plan.

### Task 7: Finalize Compose and Generate the Read-Only Operation Plan Gate

**Files:**
- Modify after acceptance: `infra/milvus/docker-compose.yml`
- Retain: `infra/milvus/docker-compose.minio-2025.yml`
- Retain unchanged: `infra/milvus/docker-compose.minio-2023-rollback.yml`
- Create: R05 preflight bundle sidecar `minio_capability.v1.json`
- Create: `data/processed/huiji/r04-20e578e292904eec951ac43f2e090899/operations/minio_operation_plan.v1.json`

**Interfaces:**
- Consumes: `cutover_accepted=true`, final inventory, capability sidecar, expanded reconciliation SHA-256.
- Produces: durable Compose configuration and one immutable, unused operation plan.

- [ ] **Step 1: Make the accepted Compose configuration durable**

In `infra/milvus/docker-compose.yml`, change only:

```yaml
image: minio/minio:RELEASE.2025-09-07T16-13-09Z
```

replace the legacy MinIO credential variable names with:

```yaml
MINIO_ROOT_USER: minioadmin
MINIO_ROOT_PASSWORD: minioadmin
```

and change the volume to:

```yaml
- ./volumes/minio-2025-09-07-cutover:/minio_data
```

Run `docker compose -f $Compose config --quiet`, then compare the resolved MinIO service against the accepted override configuration. They must be identical before the override is no longer required.

Before and after modifying the base Compose, verify the SHA-256 of `docker-compose.minio-2023-rollback.yml` is unchanged and its resolved MinIO service still pins `RELEASE.2023-03-20T20-16-18Z` with `./volumes/minio:/minio_data`. Task 7 acceptance is forbidden if the independent rollback authority drifts.

- [ ] **Step 2: Re-capture current inventory immediately before planning**

```powershell
$BuildId = "r04-20e578e292904eec951ac43f2e090899"
$ArtifactRoot = Join-Path $Project "eval\task-4-r04\20e578e292904eec951ac43f2e090899\r04-20e578e292904eec951ac43f2e090899"
$RuntimeMedia = Join-Path $ArtifactRoot "runtime\media_assets.v2.jsonl"
$RawRoot = Join-Path $Project "data\huiji\res1999"
$CurrentInventory = Join-Path $Evidence "current-reverse1999-for-c19.v1.json"
$CurrentReconciliation = Join-Path $Evidence "current-reconciliation-for-c19.v1.json"
python scripts/minio_blue_green_evidence.py object-inventory --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output $CurrentInventory
if ($LASTEXITCODE -ne 0) { throw "Current C19 inventory failed" }
python scripts/minio_blue_green_evidence.py reconcile-build --runtime-media $RuntimeMedia --raw-root $RawRoot --inventory $CurrentInventory `
  --predecessor-sha256 325afc748cc67af342848bbb22c0c4db96561d48cc2f0c9eef1f16de27f18714 `
  --output $CurrentReconciliation
if ($LASTEXITCODE -ne 0) { throw "Current C19 reconciliation failed" }
```

Require all original 18,053 objects unchanged plus the registered diagnostic control and two retained production probe objects. The reconciliation must cite expanded evidence SHA-256 `325afc748cc67af342848bbb22c0c4db96561d48cc2f0c9eef1f16de27f18714` as its predecessor.

Expected:

```text
same_hash = 11819
missing_remote = 3038
hash_mismatch = 0
orphan_remote = 6237 (original 6234 plus one diagnostic control and two retained production probes)
```

The currently measured 1,777 nonvoice missing-`content_sha256` records remain a separately recorded data-integrity issue and do not block this voice-only plan.

- [ ] **Step 3: Generate exactly one immutable operation plan**

```powershell
$Baseline = Join-Path $Project "data\processed\huiji\evidence\eventname_voice_binding_baseline.v1.json"
$Capability = Join-Path $Evidence "minio_capability.v1.json"
$ProcessedBuild = Join-Path $Project "data\processed\huiji\$BuildId"
python scripts/minio_blue_green_evidence.py prepare-c19-evidence --artifact-root $ArtifactRoot --baseline $Baseline --current-inventory $CurrentInventory --capability $Capability --reconciliation $CurrentReconciliation --output-root $ProcessedBuild
if ($LASTEXITCODE -ne 0) { throw "C19 evidence preparation failed" }
$BuildManifest = Join-Path $ProcessedBuild "build_manifest.json"
$PreflightBundle = Join-Path $ProcessedBuild "preflight\preflight_bundle_manifest.v1.json"
$PlanPath = Join-Path $ProcessedBuild "operations\minio_operation_plan.v1.json"
$BuildManifestSha = (Get-FileHash -LiteralPath $BuildManifest -Algorithm SHA256).Hash.ToLowerInvariant()
$PreflightBundleSha = (Get-FileHash -LiteralPath $PreflightBundle -Algorithm SHA256).Hash.ToLowerInvariant()
$CurrentInventorySha = (Get-FileHash -LiteralPath $CurrentInventory -Algorithm SHA256).Hash.ToLowerInvariant()
$BaselineSha = (Get-FileHash -LiteralPath $Baseline -Algorithm SHA256).Hash.ToLowerInvariant()
python scripts/build_huiji_evb.py minio-plan --build-manifest $BuildManifest --expected-build-manifest-sha256 $BuildManifestSha --preflight-bundle $PreflightBundle --expected-preflight-bundle-sha256 $PreflightBundleSha --before-inventory $CurrentInventory --expected-before-inventory-sha256 $CurrentInventorySha --baseline $Baseline --expected-baseline-sha256 $BaselineSha --output $PlanPath
if ($LASTEXITCODE -ne 0) { throw "C19 operation-plan generation failed" }
```

The fixed output is `data/processed/huiji/r04-20e578e292904eec951ac43f2e090899/operations/minio_operation_plan.v1.json`.

Expected plan assertions:

```text
planned object count = 3038
every object asset_type = voice
every disposition = conditional_create
every key appears in missing_remote
no orphan key appears
no false-conflict/nonvoice key appears
used_by_operation_id = null
use marker absent
upload report absent
```

- [ ] **Step 4: Hash and independently review the plan**

Record canonical operation-plan SHA-256, ordinary file SHA-256, current inventory SHA-256, capability sidecar SHA-256, object-set SHA-256, and source containment result. Independent review must return spec compliance PASS and code quality/evidence PASS.

- [ ] **Step 5: Stop before C20**

Do not claim the plan and do not run `minio-upload`. Report that migration and R05/C19 are complete while C20 remains a separate explicitly approved operation.

## Final Acceptance

The migration is complete only when all conditions are true:

- The upgraded MinIO uses `RELEASE.2025-09-07T16-13-09Z` and host ports `9002/9003`.
- Docker service/network identity remains `minio:9000` for Milvus.
- The original data directory remains untouched and startable by the old Compose for rollback.
- Every original object and bucket policy is unchanged; only registered probe objects were added.
- Milvus and representative vector queries match pre-cutover evidence.
- Project media URLs and bytes match pre-cutover evidence.
- Final capability probe passes and produces hash-pinned evidence.
- The one-time plan contains exactly 3,038 voice `missing_remote` objects and remains unclaimed.
- No delete API, ordinary business PUT, bucket mutation, operation-plan claim, or C20 upload occurred.
