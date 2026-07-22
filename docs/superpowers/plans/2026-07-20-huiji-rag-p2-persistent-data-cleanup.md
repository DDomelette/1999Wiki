# Huiji RAG P2 Persistent Data Cleanup Implementation Plan

> Execution mode: begin only after the P1 acceptance matrix passes. Run in the existing dirty worktree without Git operations or subagents. The controller may proceed automatically through green gates; it must stop on drift, mismatch, backup failure or partial mutation.

**Goal:** Remove only persistent data proven to belong exclusively to the retired RAG pipeline, with complete backup, exact-key plans and post-delete reconciliation.

**Architecture:** A one-time cleanup controller captures MinIO, RAG and Wiki inventories; derives exact set differences; backs up every candidate; emits a hash-pinned operation plan; rechecks drift; applies exact deletions; and reconciles every retained consumer.

**Tech stack:** Python 3.11, pytest, MinIO Python SDK, PyMySQL, restic, canonical JSON/SHA-256 evidence.

## 1. Scope

This plan implements the following individually tracked requirements:

- `CLEAN-INVENTORY-P0-01`, `CLEAN-INVENTORY-P0-02`, `CLEAN-INVENTORY-P0-03`, `CLEAN-INVENTORY-P0-04`, `CLEAN-INVENTORY-P0-05`, `CLEAN-INVENTORY-P0-06`
- `CLEAN-BACKUP-P0-01`, `CLEAN-BACKUP-P0-02`, `CLEAN-BACKUP-P0-03`, `CLEAN-BACKUP-P0-04`, `CLEAN-BACKUP-P0-05`, `CLEAN-BACKUP-P0-06`, `CLEAN-BACKUP-P0-07`
- `CLEAN-PLAN-P0-01`, `CLEAN-PLAN-P0-02`
- `CLEAN-APPLY-P0-01`, `CLEAN-APPLY-P0-02`, `CLEAN-APPLY-P0-03`, `CLEAN-APPLY-P0-04`, `CLEAN-APPLY-P0-05`
- `CLEAN-VERIFY-P0-01`, `CLEAN-VERIFY-P0-02`, `CLEAN-VERIFY-P0-03`, `CLEAN-VERIFY-P0-04`, `CLEAN-VERIFY-P0-05`, `CLEAN-VERIFY-P0-06`

It does not delete residual orphan objects, probes, Milvus data/collections, stopped containers or current Wiki/RAG content.

## 2. Hard Gates

1. P1 acceptance status is pass and production source scans show zero old consumers.
2. Restic repository and password file are available; `restic check` and full candidate restore test pass.
3. Current MinIO inventory, active RAG manifest and current Wiki export are newly captured and hash-pinned.
4. All active consumer objects exist; any key/hash mismatch triggers expanded diagnosis and stops plan generation.
5. Every remote deletion candidate has a verified object-level backup and verified restic restore.
6. Apply requires an explicit operation-plan SHA-256 and a no-drift recapture.
7. Post-delete active RAG, Wiki, MinIO retained sets and Milvus fingerprints are unchanged.

## 3. Execution Tasks

### Task 0: Build And Test The One-Time Cleanup Controller

**Corresponding specs:** all inventory, plan, apply and verify contracts

**Files:**

- Create: `scripts/cleanup_legacy_rag_p2.py`
- Create: `tests/test_cleanup_legacy_rag_p2.py`
- Evidence: `eval/huiji_source_cleanup/<run-id>/p2/**`

- [ ] Write failing tests for canonical serialization, path containment, complete object fields, set classification, active-key missing, hash mismatch, stale-plan rejection, conditional restore, append-only receipts and exact-key-only deletion.
- [ ] Add tests proving `a-bucket`, capability probes, residual orphans and all Milvus collections are ineligible.
- [ ] Add tests proving a hash mismatch stops plan generation and emits an expanded diagnostic scope.
- [ ] Implement subcommands `inventory`, `verify-local-backup`, `backup-minio`, `plan`, `apply`, `verify` and `restore-partial`. Default invocation and `inventory` are read-only; mutation subcommands require explicit hashes. `restore-partial` additionally requires a separately generated restore-plan SHA-256 and conditional-create capability.
- [ ] Run:

```powershell
$Python = 'D:\Anaconda32024\envs\langchain\python.exe'
& $Python -m pytest tests\test_cleanup_legacy_rag_p2.py -q
```

**Failure:** any path/prefix-wide deletion API, implicit overwrite or unpinned apply blocks the task.

### Task 1: Initialize The Operation And Verify P1

**Corresponding specs:** `CLEAN-PLAN-P0-01`, source-consumer boundary

- [ ] Set immutable operation paths:

```powershell
$OperationId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-huiji-p2'
$RunDir = Join-Path 'eval\huiji_source_cleanup' "$OperationId\p2"
$Quarantine = Join-Path 'D:\1999Wiki_Backup\Quarantine\1999Search-p2' $OperationId
$Repo = 'D:\1999Wiki_Backup\Repositories\1999wiki-data-local'
$env:RESTIC_PASSWORD_FILE = [Environment]::GetEnvironmentVariable('RESTIC_PASSWORD_FILE','User')
New-Item -ItemType Directory -Force -Path $RunDir,$Quarantine | Out-Null
```

- [ ] Require `Test-Path $env:RESTIC_PASSWORD_FILE`, P1 acceptance pass and runtime verifier pass.
- [ ] Capture source files and configuration hashes. Do not continue if `documents.jsonl`, `assets.jsonl` or `data/raw` has a production consumer.

### Task 2: Prove Local Restic Recovery

**Corresponding specs:** `CLEAN-BACKUP-P0-01`, `CLEAN-BACKUP-P0-02`, `CLEAN-BACKUP-P0-03`

The read-only audit selected full snapshot ID `e8960e88b350e510afcceccc43c7d90062c462b1180cb97142bfa877c96e4327`, which contains all three local candidates. Revalidate its contents and restored hashes rather than trusting recency alone.

- [ ] Run:

```powershell
$LocalSnapshot = 'e8960e88b350e510afcceccc43c7d90062c462b1180cb97142bfa877c96e4327'
restic -r $Repo snapshots --json | Out-File "$RunDir\restic.snapshots.json" -Encoding utf8
restic -r $Repo check
restic -r $Repo ls $LocalSnapshot | Out-File "$RunDir\restic.local.files.txt" -Encoding utf8
$LocalRestore = Join-Path $RunDir 'local-restore-test'
restic -r $Repo restore $LocalSnapshot --target $LocalRestore `
  --include '/D/PycharmProjects/nlp/LangChain/1999Search/data/raw/**' `
  --include '/D/PycharmProjects/nlp/LangChain/1999Search/data/processed/documents.jsonl' `
  --include '/D/PycharmProjects/nlp/LangChain/1999Search/data/processed/assets.jsonl'
```

- [ ] Hash the snapshot listing and prove it contains `data/raw/**`, `data/processed/documents.jsonl` and `data/processed/assets.jsonl`.
- [ ] Restore all three candidates into `$RunDir\local-restore-test` using exact include paths from the snapshot listing.
- [ ] Run:

```powershell
& $Python scripts\cleanup_legacy_rag_p2.py verify-local-backup `
  --live-root . `
  --restore-root "$RunDir\local-restore-test" `
  --output "$RunDir\local-backup-receipt.v1.json"
```

Expected: identical relative paths, counts, sizes and SHA-256 fingerprints. Hash and retain the receipt.

**Failure:** missing snapshot path, restic error or any file mismatch blocks all deletion.

### Task 3: Capture Fresh MinIO And Consumer Inventories

**Corresponding specs:** `CLEAN-INVENTORY-P0-01`, `CLEAN-INVENTORY-P0-02`, `CLEAN-INVENTORY-P0-03`, `CLEAN-INVENTORY-P0-04`, `CLEAN-INVENTORY-P0-05`, `CLEAN-INVENTORY-P0-06`

- [ ] Run the read-only inventory command:

```powershell
& $Python scripts\cleanup_legacy_rag_p2.py inventory `
  --bucket reverse1999-assets `
  --legacy-manifest data\processed\assets.jsonl `
  --rag-media data\processed\huiji\dev\media_assets.jsonl `
  --provenance-baseline config\provenance\huiji-dev.v1.json `
  --mysql-current `
  --output-dir "$RunDir\inventory.pre"
```

- [ ] Require the output to contain a canonical full object inventory, current Wiki media export, consumer union, legacy candidates, retained classes and expanded diagnostics.
- [ ] Compare the new inventory with current stores, not the stale 18,168-row inventory from 2026-07-17.
- [ ] Require zero `hash_mismatch`, zero missing active consumer and zero overlap between delete candidates and active consumers.
- [ ] Record but do not enforce the observed counts as constants. Material changes are acceptable only when set derivation remains internally consistent and all protected references resolve.

**Failure:** mismatch, missing active media or malformed source row stops here and expands the audit to related keys, manifest rows and prefixes.

### Task 4: Back Up Every Remote Candidate And Prove Restore

**Corresponding specs:** `CLEAN-BACKUP-P0-04`, `CLEAN-BACKUP-P0-05`, `CLEAN-BACKUP-P0-06`, `CLEAN-BACKUP-P0-07`

- [ ] Download exact candidates without changing MinIO:

```powershell
& $Python scripts\cleanup_legacy_rag_p2.py backup-minio `
  --inventory "$RunDir\inventory.pre\inventory.v1.json" `
  --candidate-set "$RunDir\inventory.pre\legacy-delete-candidates.v1.json" `
  --backup-root $Quarantine `
  --output "$RunDir\minio-backup-receipt.v1.json"
```

- [ ] Require full per-object SHA-1, SHA-256, size, ETag and version evidence. Hash the receipt.
- [ ] Back up the quarantine directory to restic:

```powershell
restic -r $Repo backup $Quarantine `
  --tag 'plan:huiji-rag-p2' `
  --tag "operation:$OperationId" `
  --json | Out-File "$RunDir\minio-backup-restic.v1.json" -Encoding utf8
$MinioSnapshot = (Get-Content "$RunDir\minio-backup-restic.v1.json" -Raw | ConvertFrom-Json).snapshot_id
if (-not $MinioSnapshot) { throw 'restic did not return a quarantine snapshot ID' }
$MinioRestore = Join-Path $RunDir 'minio-restore-test'
restic -r $Repo restore $MinioSnapshot --target $MinioRestore `
  --include "/D/1999Wiki_Backup/Quarantine/1999Search-p2/$OperationId/**"
& $Python scripts\cleanup_legacy_rag_p2.py verify-local-backup `
  --live-root $Quarantine `
  --restore-root $MinioRestore `
  --output "$RunDir\minio-restic-restore-receipt.v1.json"
```

- [ ] Restore that exact new snapshot to `$RunDir\minio-restore-test` and compare the complete candidate fingerprint with `minio-backup-receipt.v1.json`.

**Failure:** any download, content hash, restic backup or restore mismatch blocks plan generation. Do not upload or delete objects.

### Task 5: Generate And Pin The Operation Plan

**Corresponding specs:** `CLEAN-PLAN-P0-01`, `CLEAN-PLAN-P0-02`

- [ ] Generate canonical plan only from prior passed evidence:

```powershell
& $Python scripts\cleanup_legacy_rag_p2.py plan `
  --inventory "$RunDir\inventory.pre\inventory.v1.json" `
  --local-backup-receipt "$RunDir\local-backup-receipt.v1.json" `
  --minio-backup-receipt "$RunDir\minio-backup-receipt.v1.json" `
  --restic-receipt "$RunDir\minio-backup-restic.v1.json" `
  --output "$RunDir\operation-plan.v1.json"
$PlanSha256 = (Get-FileHash "$RunDir\operation-plan.v1.json" -Algorithm SHA256).Hash.ToLowerInvariant()
$PlanSha256 | Set-Content "$RunDir\operation-plan.v1.sha256" -Encoding ascii
```

- [ ] Mechanically verify that every delete key belongs to the legacy candidate set, no retained key appears, and the plan contains no credentials or local source content.
- [ ] Recapture current inventory into `inventory.apply` and require protected/candidate fingerprints equal to `inventory.pre`.

**Failure:** any drift invalidates this plan. Return to Task 3 with a new operation ID; do not patch the plan in place.

### Task 6: Apply Exact Local And MinIO Deletions

**Corresponding specs:** `CLEAN-APPLY-P0-01`, `CLEAN-APPLY-P0-02`, `CLEAN-APPLY-P0-03`, `CLEAN-APPLY-P0-04`, `CLEAN-APPLY-P0-05`

- [ ] Apply with the explicit plan hash:

```powershell
& $Python scripts\cleanup_legacy_rag_p2.py apply `
  --operation-plan "$RunDir\operation-plan.v1.json" `
  --expected-plan-sha256 $PlanSha256 `
  --receipt "$RunDir\apply-receipt.v1.jsonl"
```

The controller must:

1. repeat all plan/hash/path checks before the first mutation;
2. delete only the three exact local candidate paths;
3. delete remote keys one at a time using the planned version where available;
4. fsync/flush an append-only receipt after each successful deletion;
5. perform no MySQL mutation and record the zero-supplement audit;
6. stop immediately on the first unexpected result.

**Failure:** retain the partial receipt, recapture inventory and block completion. Do not continue through remaining keys and do not automatically overwrite during restoration.

### Task 7: Reconcile All Protected State

**Corresponding specs:** `CLEAN-VERIFY-P0-01`, `CLEAN-VERIFY-P0-02`, `CLEAN-VERIFY-P0-03`, `CLEAN-VERIFY-P0-04`, `CLEAN-VERIFY-P0-05`, `CLEAN-VERIFY-P0-06`

- [ ] Run:

```powershell
& $Python scripts\cleanup_legacy_rag_p2.py verify `
  --operation-plan "$RunDir\operation-plan.v1.json" `
  --expected-plan-sha256 $PlanSha256 `
  --apply-receipt "$RunDir\apply-receipt.v1.jsonl" `
  --output-dir "$RunDir\verification.final"
& $Python scripts\verify_huiji_runtime.py --run-dir "$RunDir\runtime.final"
```

- [ ] Require planned local/remote candidates absent and every retained/active key unchanged.
- [ ] Require Wiki MySQL page/media counts, crawler-only source checks and relevant API smoke tests unchanged.
- [ ] Require active Milvus v3 and retained v2/shadow collection schema/row fingerprints unchanged.
- [ ] Run focused and full tests:

```powershell
& $Python -m pytest tests\test_cleanup_legacy_rag_p2.py tests\test_huiji_provenance.py `
  tests\test_huiji_wiki_crawler_only_policy.py -q
& $Python -m pytest tests -q
```

- [ ] Write `p2-acceptance.v1.json` with one record per spec ID and hashes linking all evidence.
- [ ] Independently scan evidence for missing references, credential leaks, absolute source paths and inconsistent counts.

**Completion:** all gates pass. The unplanned orphan set, probes, Milvus stores and current consumers remain unchanged.

## 4. Deferred / Out Of Scope

- Classification and possible cleanup of the retained orphan set requires another inventory and approval.
- Cleanup of stopped containers, old MinIO directories and Milvus v2/shadow collections is separate infrastructure work.
- RAG collection-item, Udimo and additional image retrieval is a separate quality iteration.
- MinIO credential rotation and loopback-only port binding are deferred security work.

## 5. Completion Self-Check

- [ ] P1 acceptance passed before P2 began.
- [ ] `CLEAN-INVENTORY-P0-01` through `CLEAN-INVENTORY-P0-06` each pass with a fresh inventory and individual matrix record.
- [ ] `CLEAN-BACKUP-P0-01` through `CLEAN-BACKUP-P0-07` each pass, including two real restore tests.
- [ ] `CLEAN-PLAN-P0-01` and `CLEAN-PLAN-P0-02` pass and apply used the recorded SHA-256.
- [ ] `CLEAN-APPLY-P0-01` through `CLEAN-APPLY-P0-05` each pass with a complete append-only receipt.
- [ ] `CLEAN-VERIFY-P0-01` through `CLEAN-VERIFY-P0-06` each pass with an individual matrix record.
- [ ] No active RAG/Wiki object, retained orphan, probe, MySQL row or Milvus object changed.
- [ ] Full tests, runtime verifier and final requirement matrix pass.
