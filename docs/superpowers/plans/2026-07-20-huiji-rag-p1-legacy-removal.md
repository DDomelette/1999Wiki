# Huiji RAG P1 Legacy Removal Implementation Plan

> Execution mode: run task-by-task in the existing dirty worktree. Do not use Git rollback, worktrees or subagents. Stop only on a hard gate that cannot be resolved safely.

**Goal:** Remove every executable legacy RAG fallback while preserving the active Huiji runtime, provenance gate and shadow-only rebuild path.

**Architecture:** Runtime construction becomes unconditional Huiji construction after the existing provenance verifier passes. Legacy local documents, asset registries and destructive build helpers disappear from code and configuration. Persistent data remains untouched for the separate P2 plan.

**Tech stack:** Python 3.11, pytest, pymilvus, FastAPI, JSON provenance evidence.

## 1. Scope

This plan implements the following individually tracked requirements:

- `RUNTIME-SOURCE-P0-01`, `RUNTIME-SOURCE-P0-02`, `RUNTIME-SOURCE-P0-03`, `RUNTIME-SOURCE-P0-04`, `RUNTIME-SOURCE-P0-05`
- `LEGACY-CODE-P0-01`, `LEGACY-CODE-P0-02`, `LEGACY-CODE-P0-03`, `LEGACY-CODE-P0-04`, `LEGACY-CODE-P0-05`, `LEGACY-CODE-P0-06`
- `DOCS-P0-01`, `DOCS-P0-02`, `DOCS-P0-03`, `DOCS-P0-04`

This plan does not delete local files under `data/**`, MinIO objects, MySQL rows or Milvus collections. It does not implement new retrieval content.

## 2. Hard Gates

1. The installed Huiji runtime verifier passes before any edit and after all edits.
2. Active Milvus collection name, schema, row count and fingerprints remain equal.
3. Both MinIO buckets (`reverse1999-assets` and Milvus-owned `a-bucket`) and MySQL canonical counts remain equal across the implementation window.
4. Production code has zero legacy source fallback references.
5. The complete Python test suite passes, except unrelated failures that are identified with exact ownership and do not touch this plan's files.

Any protected-state drift blocks completion and must be investigated before continuing.

## 3. Execution Tasks

### Task 0: Capture A Read-Only Protected-State Baseline

**Corresponding specs:** `RUNTIME-SOURCE-P0-05`, all no-mutation constraints

**Files:**

- Create: `eval/huiji_source_cleanup/<run-id>/p1/protected.pre.v1.json`
- Create: `eval/huiji_source_cleanup/<run-id>/p1/runtime.pre/`

- [ ] Set a unique run directory and run the installed verifier:

```powershell
$Python = 'D:\Anaconda32024\envs\langchain\python.exe'
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-huiji-p1'
$RunDir = Join-Path 'eval\huiji_source_cleanup' $RunId
New-Item -ItemType Directory -Force -Path "$RunDir\p1" | Out-Null
& $Python scripts\verify_huiji_runtime.py --run-dir "$RunDir\p1\runtime.pre"
```

- [ ] Capture active Milvus metadata/fingerprints, MinIO bucket counts, MySQL table counts and protected artifact hashes into `protected.pre.v1.json`. Use the existing read-only provenance helpers; do not write any business store.
- [ ] Hash the evidence file and record the hash beside it.

**Failure:** verifier failure, an unavailable protected store, or a mismatch with the installed baseline blocks edits.

### Task 1: Make Retriever And Media Construction Huiji-Only

**Corresponding specs:** `RUNTIME-SOURCE-P0-01`, `RUNTIME-SOURCE-P0-02`, `RUNTIME-SOURCE-P0-03`, `RUNTIME-SOURCE-P0-04`

**Files:**

- Modify: `src/rag/retriever.py`
- Modify: `src/rag/chain.py`
- Modify: `src/assets/huiji_registry.py` only if typing/import cleanup requires it
- Create: `tests/test_huiji_only_runtime_policy.py`
- Modify: `tests/test_retriever.py`
- Modify: `tests/test_chain_assets.py`
- Modify: `tests/test_sse.py`

- [ ] Add failing tests proving missing Huiji artifacts fail closed and cannot call legacy document or vector-result adapters.
- [ ] Add failing tests proving `RAGChain` constructs only `HuijiMediaRegistry` and rejects unsupported source configuration.
- [ ] Remove `_load_entity_names`, legacy entity detection, `_legacy_vector_search`, the legacy result adapter and the `AssetRegistry` branch.
- [ ] Make Huiji artifact loading explicit: invalid paths or empty required artifacts raise a deterministic initialization error after the provenance boundary, rather than returning an empty fallback state.
- [ ] Run:

```powershell
& $Python -m pytest tests\test_huiji_only_runtime_policy.py tests\test_retriever.py tests\test_chain_assets.py tests\test_sse.py -q
```

**Real acceptance:** instantiate the configured retriever against the active collection and run a deterministic sampled query set; every returned source must have `retrieval_stage=huiji_hybrid`.

**Failure:** any old document read, non-Huiji media registry or silent empty-artifact fallback blocks the task.

### Task 2: Remove Legacy Build And Asset Modules

**Corresponding specs:** `LEGACY-CODE-P0-01`, `LEGACY-CODE-P0-02`, `LEGACY-CODE-P0-03`, `LEGACY-CODE-P0-05`

**Files:**

- Delete: `scripts/extract_data.py`
- Delete: `scripts/build_index.py`
- Delete: `scripts/build_assets.py`
- Delete: `src/assets/registry.py`
- Delete: `src/assets/models.py`
- Delete: `src/extraction/__init__.py`
- Modify: `src/rag/vectorstore.py`
- Modify: `src/utils/text_cleaner.py`
- Delete or rewrite: `tests/test_asset_build_script.py`
- Delete or rewrite: `tests/test_asset_registry.py`
- Modify: `tests/test_legacy_rag_cli_blocked.py`
- Modify: `tests/test_vectorstore.py`

- [ ] Write a static test that requires the legacy files to be absent and forbids their imports from production code.
- [ ] Remove the legacy JSONL loader, Markdown chunking path, broad collection delete and `build_vectorstore()` while preserving `MilvusVectorstore`, `load_vectorstore()` and `build_huiji_shadow_collection()`.
- [ ] Remove old-only tests; replace tombstone-exit assertions with absence and import-scan assertions.
- [ ] Rewrite the text cleaner module contract as source-neutral display normalization; do not remove behavior still used by `/categories`.
- [ ] Run:

```powershell
& $Python -m pytest tests\test_legacy_rag_cli_blocked.py tests\test_vectorstore.py tests\test_text_cleaner.py tests\test_categories.py -q
```

**Real acceptance:** run `scripts/build_huiji_index.py --help` and prove the shadow-only CLI still imports without touching embeddings or Milvus.

**Failure:** loss of the shadow builder, any reintroduction of active-collection mutation, or a remaining runnable legacy entry point blocks the task.

### Task 3: Remove Legacy Runtime Configuration

**Corresponding specs:** `LEGACY-CODE-P0-04`, `LEGACY-CODE-P0-06`, `RUNTIME-SOURCE-P0-01`

**Files:**

- Modify: `config/config.py`
- Modify: tests and isolated evaluation fixtures that construct `PathsCfg`
- Modify: `tests/test_config.py`

- [ ] Add failing tests proving `PathsCfg` has no `data_raw` or `data_processed` fields and production config has no old source selector.
- [ ] Remove those fields and update current Huiji/evaluation fixtures to use explicit Huiji paths.
- [ ] Run:

```powershell
& $Python -m pytest tests\test_config.py tests\test_rag_eval_deterministic.py tests\test_rag_eval_runner.py -q
```

- [ ] Run the production source scan:

```powershell
rg -n -i "documents\.jsonl|assets\.jsonl|data[/\\]raw|obsidian|AssetRegistry|scripts[/\\](extract_data|build_index|build_assets)" `
  backend src scripts config start.ps1 start.bat --glob '!*.pyc'
```

Expected: no active legacy-source reference. Explicit rejection constants may remain only where the provenance policy needs them.

### Task 4: Correct Current Documentation

**Corresponding specs:** `DOCS-P0-01`, `DOCS-P0-02`, `DOCS-P0-03`, `DOCS-P0-04`

**Files:**

- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/huiji-rag-runbook.md`
- Modify: `tests/test_huiji_source_docs.py`

- [ ] Remove obsolete product claims, tree entries and command examples.
- [ ] Replace the historical active-flow diagram with the Huiji crawler, processed artifacts, BM25, Milvus, MinIO and runtime gate flow.
- [ ] State that the old CLI files are absent and are not a rollback mechanism.
- [ ] Preserve historical evidence links without rewriting immutable evidence.
- [ ] Run:

```powershell
& $Python -m pytest tests\test_huiji_source_docs.py -q
rg -n -i "run scripts/(extract_data|build_index|build_assets)|based on.*obsidian|Obsidian vault.*source" `
  README.md docs\architecture.md docs\huiji-rag-runbook.md
```

Expected: tests pass and the scan returns no instruction treating the old pipeline as active.

### Task 5: Full P1 Acceptance

**Corresponding specs:** all P1 design P0 requirements

- [ ] Run the installed verifier again:

```powershell
& $Python scripts\verify_huiji_runtime.py --run-dir "$RunDir\p1\runtime.post"
```

- [ ] Run focused policy and provenance suites:

```powershell
& $Python -m pytest tests\test_huiji_only_runtime_policy.py tests\test_huiji_provenance.py `
  tests\test_huiji_shadow_builder.py tests\test_huiji_source_docs.py -q
```

- [ ] Run the full suite:

```powershell
& $Python -m pytest tests -q
```

- [ ] Capture `protected.post.v1.json` with the same collector as Task 0 and compare it with `protected.pre.v1.json`. Require no active Milvus, MinIO, MySQL or formal artifact drift.
- [ ] Write `p1-acceptance.v1.json` with one record per spec ID, implementation path, tests, real evidence and status.
- [ ] Scan new evidence for credentials, absolute local paths and source/answer text.

**Completion:** every requirement passes and the protected-state comparison is equal. Only then may the P2 plan begin.

## 4. Deferred / Out Of Scope

- Persistent data deletion is exclusively in the approved P2 plan.
- New collection-item, Udimo and image-role retrieval is deferred to a later quality spec after the requested analysis report.
- MinIO credentials and host bindings remain unchanged.

## 5. Completion Self-Check

- [ ] `RUNTIME-SOURCE-P0-01`, `RUNTIME-SOURCE-P0-02`, `RUNTIME-SOURCE-P0-03`, `RUNTIME-SOURCE-P0-04` and `RUNTIME-SOURCE-P0-05` pass.
- [ ] `LEGACY-CODE-P0-01`, `LEGACY-CODE-P0-02`, `LEGACY-CODE-P0-03`, `LEGACY-CODE-P0-04`, `LEGACY-CODE-P0-05` and `LEGACY-CODE-P0-06` pass.
- [ ] `DOCS-P0-01`, `DOCS-P0-02`, `DOCS-P0-03` and `DOCS-P0-04` pass.
- [ ] The old CLI, registry and old build files are absent.
- [ ] Runtime cannot read old local artifacts or enter an alternate corpus.
- [ ] Huiji runtime and shadow builder remain functional.
- [ ] Protected persistent state is unchanged.
- [ ] Full pytest and the requirement matrix pass.
