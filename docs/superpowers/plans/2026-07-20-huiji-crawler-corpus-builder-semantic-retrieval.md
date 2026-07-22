# Huiji Crawler Corpus Builder And Semantic Retrieval P0 Implementation Plan

> Execution mode: execute task-by-task in the existing dirty worktree without subagents, worktrees, Git cleanup or rollback. Do not write to `D:\1999Wiki_Backup`.

**Goal:** Rebuild the crawler-only corpus production path around one `HuijiCorpusBuilder`, preserve the current active corpus record-by-record, publish the frozen media v3 binding contract, add collection/Udimo retrieval, and stop after hash-pinned candidate, shadow-verification and activation-review evidence. This plan never switches active state.

**Architecture:** Four hash-pinned crawler inputs feed a staged build package. A shared `VoiceBindingStage` supplies exact voice bindings to the single corpus builder and the diagnostic EVB facade. The builder emits one immutable candidate containing parent, child, media-binding v3, BM25, provenance and fidelity artifacts. Retrieval loads an explicit candidate tuple for isolated verification. Wiki remains a separate projection and must prove v2/v3 compatibility through a receipt before activation review.

**Tech stack:** Python 3.11, dataclasses, JSON/JSONL canonical serialization, pytest, existing BM25/Milvus/MinIO/MySQL clients, PowerShell, FastAPI runtime contracts.

**Approved spec:** `docs/superpowers/specs/2026-07-20-huiji-crawler-corpus-builder-semantic-retrieval-design.md`

## 1. Current Facts And Execution Boundary

- The accepted preservation baseline is `eval/huiji_corpus_fidelity/20260720T073917Z/corpus-preservation-baseline.v2.json`, SHA-256 `8df26d9a6cd1014c82d1fdd1fa858f1b9411cb4b365101b0a12020d608db10aa`.
- Current MySQL, MinIO, active artifacts and active Milvus remain production inputs for read-only comparison only.
- `data/processed/huiji/active_build.v1.json` is currently absent. This plan must not bootstrap it implicitly.
- Historical v2 media manifests use inconsistent reader/writer labels. v3 has one frozen manifest schema: `evb.media-artifact-manifest/v3`.
- The media v3 artifact is one row per binding. Wiki may normalize it into resources and bindings; RAG must not create a second canonical resource JSONL.
- Tasks 0 through 8 implement and test code without changing business stores. The official full-data candidate in Task 9 begins only after the Wiki line publishes a valid compatibility receipt, matching the approved execution order.
- Task 10 was originally scoped as user-run. On 2026-07-21 the user explicitly authorized the agent to build the isolated shadow. That authorization does not permit writes to the active or historical collections. Any process that needs `SILICONFLOW_API_KEY` must reload it from the User environment, must not print or persist it, and must clear the process-level variable in `finally`.
- Tasks 11 and 12 remain isolated/read-only with respect to active state. Even a fully passing proposal requires a later separately approved activation plan.

## 2. P0 Requirement Map

| Requirement group | Tasks | Automated gate | Real-data gate |
|---|---:|---|---|
| `RECOVERY-P0-01..02` | 0, 2 | recovery ledger/path-write guards | source hashes recorded outside backup repository |
| `SOURCE-P0-01..05` | 0, 2, 6, 9, 12 | allowlist, containment, repeatability and drift tests | four crawler files plus protected-state pre/post comparison |
| `BUILD-P0-01..09` | 2, 3, 7 | public API/facade/CLI/static-entrypoint tests | two byte-equal candidate runs; active roots unchanged |
| `PROJECTION-P0-01..12` | 4, 6, 9 | section/ID/exclusion/fidelity tests | full active-to-candidate ledger and crawler/MySQL read-only reconciliation |
| `MEDIA-P0-01..11` | 1, 5, 6, 9 | v3 schema, ID, URL, multibinding and manifest tests | complete media multiset reconciliation and MinIO read-only inventory |
| `VOICE-P0-01..03` | 3, 5, 9, 11 | event/language/conflict/pagination tests | dynamic character/event sample plus full conflict gate |
| `ARTIFACT-P0-01..05` | 1, 6, 7, 9 | path closure, canonical bytes, BM25 parity and diff tests | two full candidate roots compare byte-for-byte for semantic files |
| `FIDELITY-P0-01..05` | 6, 9 | ledger classification and reversible mapping tests | every active parent/child/media binding/excluded/BM25 row classified once |
| `PROVENANCE-P0-01..02` | 0, 6, 9, 12 | candidate/installed-baseline isolation tests | installed runtime verifier passes before and after work |
| `RETRIEVAL-P0-01..07` | 8, 11 | intent/policy/registry/tuple-isolation tests | isolated full-chain collection, Udimo, multi-intent and voice cases |
| `VECTOR-P0-01..04` | 6, 10, 11 | handoff and shadow fingerprint tests | explicitly authorized shadow exactly matches candidate child corpus |
| `ACTIVATION-P0-01..07` | 1, 12 | receipt/pointer/proposal/rollback blocker tests | protected-state recapture and create-new proposal evidence only |

Every P0 ID is covered above. P1 and P2 appear only in Section 7 and are not implementation tasks.

### 2.1 Machine-Checkable Primary Coverage

- Task 0: `RECOVERY-P0-01`, `RECOVERY-P0-02`, `SOURCE-P0-05`, `PROVENANCE-P0-01`.
- Task 2: `SOURCE-P0-01`, `SOURCE-P0-02`, `SOURCE-P0-03`, `SOURCE-P0-04`, `BUILD-P0-01`, `BUILD-P0-02`, `BUILD-P0-05`, `BUILD-P0-06`, `BUILD-P0-07`, `BUILD-P0-09`.
- Task 3: `BUILD-P0-03`, `BUILD-P0-04`, `VOICE-P0-01`, `VOICE-P0-02`, `VOICE-P0-03`.
- Task 4: `PROJECTION-P0-01`, `PROJECTION-P0-02`, `PROJECTION-P0-03`, `PROJECTION-P0-04`, `PROJECTION-P0-05`, `PROJECTION-P0-06`, `PROJECTION-P0-07`, `PROJECTION-P0-08`, `PROJECTION-P0-09`, `PROJECTION-P0-10`, `PROJECTION-P0-11`, `PROJECTION-P0-12`.
- Task 5: `MEDIA-P0-01`, `MEDIA-P0-02`, `MEDIA-P0-03`, `MEDIA-P0-04`, `MEDIA-P0-05`, `MEDIA-P0-06`, `MEDIA-P0-07`, `MEDIA-P0-08`, `MEDIA-P0-09`, `MEDIA-P0-10`, `MEDIA-P0-11`.
- Task 6: `ARTIFACT-P0-01`, `ARTIFACT-P0-02`, `ARTIFACT-P0-03`, `ARTIFACT-P0-04`, `ARTIFACT-P0-05`, `FIDELITY-P0-01`, `FIDELITY-P0-02`, `FIDELITY-P0-03`, `FIDELITY-P0-04`, `FIDELITY-P0-05`, `PROVENANCE-P0-02`, `VECTOR-P0-01`.
- Task 7: `BUILD-P0-08`.
- Task 8: `RETRIEVAL-P0-01`, `RETRIEVAL-P0-02`, `RETRIEVAL-P0-03`, `RETRIEVAL-P0-04`, `RETRIEVAL-P0-05`, `RETRIEVAL-P0-06`, `RETRIEVAL-P0-07`.
- Task 10: `VECTOR-P0-02`, `VECTOR-P0-03`.
- Task 11: `VECTOR-P0-04`.
- Task 12: `ACTIVATION-P0-01`, `ACTIVATION-P0-02`, `ACTIVATION-P0-03`, `ACTIVATION-P0-04`, `ACTIVATION-P0-05`, `ACTIVATION-P0-06`, `ACTIVATION-P0-07`.

Task 1 freezes contracts used by the primary implementation tasks; Tasks 9 and 13 perform full-data and final cross-requirement acceptance. The generated acceptance matrix still contains one row per requirement, even when a requirement has supporting gates in multiple tasks.

## 3. Non-Negotiable Gates

1. **Baseline gate:** the baseline file and sidecar must exist and hash to the approved SHA before edits and before the full-data build.
2. **Crawler-only gate:** production build reads only `data_pages.jsonl`, `resources_manifest.jsonl`, `pages.jsonl` and `wikitext.jsonl` from the configured raw root.
3. **Create-new gate:** build root, run directory, evidence, shadow collection and proposal directory must not already exist. Failed outputs are retained and never repaired in place.
4. **Conflict gate:** unresolved EVB conflict, source drift, path escape, duplicate identity, missing required media or MinIO hash mismatch yields `blocked`; no pagination or dedup workaround is permitted.
5. **Fidelity gate:** `unexplained_missing=0` and `unexplained_binding_loss=0`; every active identity is classified exactly once with source-backed evidence.
6. **Media identity gate:** resource deduplication may occur only in a consumer projection. Runtime JSONL, BM25 comparison, diff and UI-facing selection all preserve `binding_id` multiplicity.
7. **Protected-state gate:** active artifacts, active Milvus, MySQL and both MinIO buckets must not drift unexpectedly during implementation and candidate verification.
8. **Wiki compatibility gate:** Task 9 requires a receipt with schema `huiji.wiki-media-v3-compatibility-receipt/v1` whose fixture hashes equal the frozen RAG fixture.
9. **Embedding gate:** embedding requires explicit user authorization and may target only a new non-active collection. The verifier rejects active, historical or existing names before loading the embedding model. Credentials remain process-local and are cleared after use.
10. **No-activation gate:** no task writes `active_build.v1.json`, installed provenance, active collection configuration, Wiki business tables or MinIO business objects.

## 4. Planned File Layout

### Create

- `src/huiji_rag/build/__init__.py`: public corpus-build API only.
- `src/huiji_rag/build/contracts.py`: request/result/stage contracts, status enums and frozen schema constants.
- `src/huiji_rag/build/source_inventory.py`: crawler allowlist, containment, hashes and source drift checks.
- `src/huiji_rag/build/projection.py`: canonical parent/child/section/owner projection.
- `src/huiji_rag/build/voice_stage.py`: reusable EVB stage adapter.
- `src/huiji_rag/build/media_v3.py`: resource/binding IDs and media v3 rows/schema.
- `src/huiji_rag/build/fidelity.py`: active-to-candidate multiset ledger and semantic diff.
- `src/huiji_rag/build/artifact_writer.py`: create-new canonical artifact assembly and manifest closure.
- `src/huiji_rag/build/orchestrator.py`: `HuijiCorpusBuilder` stage orchestration.
- `src/huiji_rag/build/activation_evidence.py`: receipt validation and proposal/rollback evidence only.
- `scripts/build_huiji_corpus.py`: `candidate`, `verify` and `proposal` subcommands.
- `tests/fixtures/contracts/huiji_media_v3/*`: frozen schema and cross-line examples.
- Focused tests named in each task below.

### Modify

- `src/huiji_rag/builder.py`, `artifacts.py`, `io.py`, `models.py`, `source.py`, `voice_binding.py`, `diagnostics.py`: compatibility facades or shared primitives; no second orchestration path.
- `scripts/build_huiji_evb.py`: diagnostic wrapper only.
- `scripts/build_huiji_index.py`: require a hash-pinned embedding handoff and explicit new shadow target.
- `src/rag/query_plan.py`, `packet_policy.py`, `retriever.py`, `hybrid.py`, `route_policy.py`, `retrieval_budget.py`: canonical section and multi-intent consumption.
- `src/assets/huiji_registry.py`, `voice_pagination.py`: binding-aware semantic media selection and unchanged line pagination.
- Existing relevant tests and runbooks only where the new public contract requires it.

### Must Not Modify In This Plan

- `src/huiji_wiki/**`, `frontend/react-app/src/components/wiki/**`, Wiki MySQL tables or Wiki import data.
- `data/processed/huiji/active_build.v1.json`, `config/settings.yaml` active tuple fields or installed provenance baseline.
- MinIO objects, `a-bucket`, active Milvus collections or any path under `D:\1999Wiki_Backup`.

## 5. Execution Tasks

### Task 0: Revalidate Baseline And Capture Protected Pre-State

**Corresponding specs:** `RECOVERY-P0-01`, `RECOVERY-P0-02`, `SOURCE-P0-05`, `PROVENANCE-P0-01`, `ACTIVATION-P0-01`

**Files:** create only a unique `eval/huiji_corpus_builder/<run-id>/pre/` evidence directory.

- [ ] Initialize paths and verify the approved baseline hash:

```powershell
$Python = 'D:\Anaconda32024\envs\langchain\python.exe'
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-corpus-v3'
$RunDir = Join-Path 'eval\huiji_corpus_builder' $RunId
$Baseline = 'eval\huiji_corpus_fidelity\20260720T073917Z\corpus-preservation-baseline.v2.json'
$ExpectedBaselineSha = '8df26d9a6cd1014c82d1fdd1fa858f1b9411cb4b365101b0a12020d608db10aa'
if ((Get-FileHash -LiteralPath $Baseline -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedBaselineSha) { throw 'Fidelity baseline hash mismatch' }
if (Test-Path -LiteralPath $RunDir) { throw 'Run directory already exists' }
New-Item -ItemType Directory -Path "$RunDir\pre" | Out-Null
```

- [ ] Run the installed runtime verifier and current fidelity audit in read-only mode. Capture active artifact, Milvus, MySQL, `reverse1999-assets` and `a-bucket` fingerprints using the same collectors as the approved baseline.
- [ ] Record hashes for any recovered builder source considered during implementation in `$RunDir\pre\recovery-source-ledger.v1.json`; record original path as a sanitized project-relative or external-read-only label. Never restore into or write beside the restic repository.
- [ ] Run `scripts/audit_external_paths.py` and assert that build/evidence output roots resolve under the project.

**Tests:** `tests/test_huiji_provenance.py`, `tests/test_runtime_path_audit.py`.

**Real acceptance:** pre-state agrees with the approved baseline or has a separately explained newer crawler snapshot; all protected stores are read-only.

**Failure:** hash mismatch, unexplained protected drift, unavailable protected store or any planned write under the backup root blocks implementation.

### Task 1: Implement Frozen Media v3 Contracts And Shared Fixture

**Corresponding specs:** `MEDIA-P0-03`, `MEDIA-P0-07..11`, `ARTIFACT-P0-02`, `ACTIVATION-P0-03..04`

**Files:**

- Create `src/huiji_rag/build/contracts.py`.
- Create `tests/fixtures/contracts/huiji_media_v3/media_assets.v3.schema.json`.
- Create `tests/fixtures/contracts/huiji_media_v3/media_assets.v3.jsonl`.
- Create `tests/fixtures/contracts/huiji_media_v3/expected_resources.json`.
- Create `tests/fixtures/contracts/huiji_media_v3/expected_bindings.json`.
- Create `tests/test_huiji_media_v3_contract.py`.

- [ ] Write failing tests for the exact field order, row/schema/manifest labels, ID regexes, no `local_relpath`, and canonical JSON bytes.
- [ ] Add fixtures covering one resource with multiple bindings, cross-owner reuse, one voice line with multiple languages, empty variant/skin, collection, Udimo and repeated compatibility `media_id`.
- [ ] Implement exact ID functions from Spec Section 6.5. Prove sorting, display names, filenames and URLs do not change IDs; prove a relationship or resource-content change does.
- [ ] Make fixture normalization produce the expected resource and binding projections without dropping any input row.
- [ ] Hash all four fixture files and expose a deterministic contract fingerprint helper for the Wiki receipt validator.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_media_v3_contract.py -q
```

**Real acceptance:** a standalone fixture verifier reports exact input binding count, distinct binding count, distinct resource count and at least one resource-to-many-bindings group.

**Failure:** either identity uses array position/display text, any duplicate binding is folded by resource ID, or schema labels differ from the Spec.

### Task 2: Establish The Single Build Package And Source Inventory

**Corresponding specs:** `RECOVERY-P0-01..02`, `SOURCE-P0-01..04`, `BUILD-P0-01..03`, `BUILD-P0-05..07`, `BUILD-P0-09`

**Files:** create `src/huiji_rag/build/__init__.py`, `source_inventory.py`, `orchestrator.py`; modify `src/huiji_rag/source.py`, `models.py`, `io.py`; create `tests/test_huiji_corpus_builder_contracts.py` and `tests/test_huiji_corpus_source_inventory.py`.

- [ ] Define immutable `CorpusBuildRequest`, `CorpusBuildResult`, `VoiceBindingInput` and `VoiceBindingResult`. Restrict result states to `blocked`, `diagnostic_only` and `ready_for_embedding`.
- [ ] Validate build IDs with `^[a-z0-9][a-z0-9_-]{0,63}$`; reject `dev`, current active/configured build, path punctuation and existing roots before parsing source rows.
- [ ] Build a source inventory from exactly four allowlisted filenames. Pin relative path, SHA-256, size, row count and canonical inventory SHA-256.
- [ ] Reject symlinks/path escapes, duplicate source identities, missing files, mid-read drift and any source label for Obsidian, `documents.jsonl`, `assets.jsonl`, MySQL content, MinIO enumeration or `.pyc`.
- [ ] Calculate code fingerprints from the participating source-file bytes, not Git metadata.
- [ ] Add mutation spies proving inventory/build contract construction cannot initialize Milvus writers, MinIO mutators, Wiki repositories or MySQL writers.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_corpus_builder_contracts.py tests\test_huiji_corpus_source_inventory.py tests\test_evb_source.py -q
```

**Real acceptance:** inventory the configured raw root twice and require equal canonical inventory SHA-256 without changing source mtimes or protected stores.

**Failure:** a fifth source becomes readable, a build root can be reused, or a blocked condition returns a ready state.

### Task 3: Extract The Shared VoiceBindingStage And Preserve EVB Diagnostics

**Corresponding specs:** `BUILD-P0-03..04`, `VOICE-P0-01..03`

**Files:** create `src/huiji_rag/build/voice_stage.py`; modify `src/huiji_rag/voice_binding.py`, `builder.py`, `diagnostics.py`, `scripts/build_huiji_evb.py`; modify/create focused EVB tests.

- [ ] Move exact EventName-to-resource matching behind `VoiceBindingStage.run(VoiceBindingInput) -> VoiceBindingResult` without changing conflict evidence semantics.
- [ ] Convert `EvbBuilder` to a thin diagnostic wrapper that delegates matching to the stage while retaining baseline, preflight, quarantine, conflict expansion and hash-pinned evidence.
- [ ] Preserve one voice child per stable event/line and one binding per language resource. Derive language/event/skin counts from records.
- [ ] Stop and expand diagnostics when `cross_child_sha`, `same_sha_different_event_or_text` or an unknown conflict first appears. A later immutable build may clear the ready gate only after full closure proves no fatal/unknown cause and runtime projection contains zero quarantined rows; preserve overlapping occurrence counts rather than mutually exclusive totals.
- [ ] Add a static/import test proving no second voice matching implementation exists outside `VoiceBindingStage`.

**Run:**

```powershell
& $Python -m pytest tests\test_evb_voice_binding.py tests\test_evb_builder.py tests\test_evb_diagnostics.py tests\test_evb_artifacts.py -q
```

**Real acceptance:** run diagnostic binding against the pinned full crawler snapshot and compare occurrence classifications to the existing EVB evidence. Any changed classification must list old/new source IDs and a reason.

**Failure:** conflicts are hidden by quarantine totals, language variants merge into one binding, or EVB and corpus paths produce different matching results for identical input.

### Task 4: Build Canonical Crawler Semantic Projection

**Corresponding specs:** `PROJECTION-P0-01..12`

**Files:** create `src/huiji_rag/build/projection.py`, `tests/test_huiji_corpus_projection.py`, `tests/test_huiji_corpus_projection_fidelity.py`; reuse neutral crawler fixtures without importing Wiki repositories.

- [ ] Implement canonical character sections `profile`, `dossier`, `skills`, `collection`, `culture_dossier`, `udimo`, `voice`, `media`; retain existing supported non-character entity sections.
- [ ] Map current `culture` children to `collection` and current `item` children/`items` parents to `culture_dossier` only when the raw record proves that meaning.
- [ ] Project collection names, English names, valuation, description, ordinal, source refs and optional media relations. Keep text rows when media is absent.
- [ ] Project Udimo only from explicit crawler owner relations; reject title-based guessing.
- [ ] Generate parent/child IDs from scoped entity identity, canonical section and stable source token. Record every fallback source-token hash.
- [ ] Dynamically derive excluded records with reason code/source hash; do not hardcode current IDs, counts or names.
- [ ] Emit old/new semantic records sufficient to classify every active parent and child as exact, rekeyed, corrected or source-backed removal.
- [ ] Add fixture-level contract checks against neutral expected crawler facts for entity ID, section, Udimo owner, object key and no-image behavior.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_corpus_projection.py tests\test_huiji_corpus_projection_fidelity.py tests\test_huiji_wiki_crawler_projection.py -q
```

The Wiki test is read-only compatibility coverage; this task must not edit Wiki code to make it pass.

**Real acceptance:** full source projection covers every supported crawler entity and produces a source-backed record for every active parent/child; current snapshot counts remain evidence, not assertions in source code.

**Failure:** unexplained coverage loss, duplicate final collection/culture block, inferred Udimo ownership or hardcoded character/count exceptions.

### Task 5: Assemble Binding-Preserving Media v3

**Corresponding specs:** `MEDIA-P0-01..11`, `VOICE-P0-01..03`

**Files:** create `src/huiji_rag/build/media_v3.py`; modify `src/huiji_rag/media.py`, `models.py`; create `tests/test_huiji_media_v3_builder.py` and `tests/test_huiji_media_v3_minio_gate.py`.

- [ ] Join projected children to crawler resource evidence using explicit source tokens and owner relations only.
- [ ] Emit exactly one runtime row per binding with all frozen v3 fields. Emit local paths only in diagnostic inventory.
- [ ] Preserve crawler `variant`, `skin_id`, owner/page IDs, section and semantic role when present; use empty values rather than filename inference when absent.
- [ ] Require lowercase SHA-1/SHA-256, deterministic size/dimensions, public HTTP(S) URL and exact/not-applicable runtime status.
- [ ] Preserve all old media occurrences through old-row-to-resource/binding mapping. Group by resource only for diagnostics and Wiki expected projection, never for runtime row elimination.
- [ ] Read MinIO inventory only for declared object keys. Missing objects block readiness; same key with different hash/size stops and expands owner/prefix/consumer diagnostics. Orphans remain diagnostic and untouched.
- [ ] Ensure collection and Udimo roles bind only to their explicit children; no generic portrait fallback.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_media_v3_contract.py tests\test_huiji_media_v3_builder.py tests\test_huiji_media_v3_minio_gate.py tests\test_evb_minio_strict.py -q
```

**Real acceptance:** full-data multiset comparison reports every old binding exactly once, all declared MinIO objects available, zero local paths in runtime rows and preserved shared-resource groups.

**Failure:** a repeated `resource_id` is collapsed, any browser URL is local, or a missing/conflicting object still permits `ready_for_embedding`.

### Task 6: Write Immutable Artifacts, BM25 And Fidelity Ledger

**Corresponding specs:** `ARTIFACT-P0-01..05`, `FIDELITY-P0-01..05`, `PROVENANCE-P0-01..02`, `PROJECTION-P0-07..12`, `MEDIA-P0-08`

**Files:** create `src/huiji_rag/build/artifact_writer.py`, `fidelity.py`; modify `src/huiji_rag/artifacts.py`, `io.py`, `provenance.py`; create `tests/test_huiji_corpus_artifacts.py`, `tests/test_huiji_corpus_fidelity.py`.

- [ ] Implement the exact candidate path table from Spec Section 7.5. Do not emit root-level `media_assets.jsonl` for v3.
- [ ] Write semantic artifacts with canonical UTF-8/newline/sort rules. Keep timestamps only in reports/receipts.
- [ ] Emit media row schema `evb.media-asset/v3`, schema document `evb.media-assets/v3` and manifest `evb.media-artifact-manifest/v3`.
- [ ] Generate child BM25 directly from child rows and media-binding BM25 directly from v3 binding rows. Pin ordered IDs, row count and semantic corpus hashes.
- [ ] Build a manifest closure check that fails on missing referenced files, extra canonical files, wrong hashes, duplicate paths or nonexistent paths. Explicitly test the historical v2 missing-schema failure shape.
- [ ] Generate full fidelity ledger categories and reversible rekey maps for parent, child, media binding, excluded and BM25 records.
- [ ] Permit only the Spec whitelist. Require zero unexplained parent/child loss and zero unexplained binding loss.
- [ ] Create the embedding handoff only after all source, media, EVB, artifact, fidelity and protected-state gates pass.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_corpus_artifacts.py tests\test_huiji_corpus_fidelity.py tests\test_sparse_bm25.py tests\test_huiji_provenance.py -q
```

**Real acceptance:** build identical test input into two distinct temporary roots; every semantic artifact SHA matches, while receipt timestamps may differ.

**Failure:** count-only fidelity, set-based media comparison, reused old BM25, unresolved manifest path or handoff emitted for a blocked candidate.

### Task 7: Complete Builder Orchestration, Facade And CLI

**Corresponding specs:** `BUILD-P0-01..09`, `SOURCE-P0-04`, `ARTIFACT-P0-02`

**Files:** finalize `src/huiji_rag/build/orchestrator.py`, `src/huiji_rag/builder.py`, `scripts/build_huiji_corpus.py`, `scripts/build_huiji_evb.py`; create `tests/test_huiji_corpus_builder.py`, `tests/test_huiji_corpus_cli.py`.

- [ ] Run stages in fixed order: source inventory, projection, voice, media, fidelity, artifact assembly, readiness.
- [ ] Make `HuijiCorpusBuilder` the only public full-artifact builder. Keep `src.huiji_rag.builder` as a documented import facade and `EvbBuilder` as diagnostic-only.
- [ ] Implement `candidate`, `verify` and `proposal` subcommands with required expected SHA arguments. Print build root, state, row counts, hashes, conflict/exclusion counts and next gate; never embed or activate.
- [ ] Catch expected gate failures into deterministic blocked reports while preserving unexpected exceptions as errors. Never convert an exception to ready.
- [ ] Add static scans proving there is no third corpus builder/CLI and no builder code writes pointer, settings, installed provenance, Milvus, MySQL or MinIO.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_corpus_builder.py tests\test_huiji_corpus_cli.py tests\test_evb_builder.py tests\test_legacy_rag_cli_blocked.py -q
& $Python scripts\build_huiji_corpus.py --help
& $Python scripts\build_huiji_evb.py --help
```

**Real acceptance:** a fixture candidate and its second independent rebuild have equal semantic hashes and distinct immutable roots; active/config files retain their pre-task hashes.

**Failure:** CLI continues automatically, an old build root is mutated, or two complete builders remain callable.

### Task 8: Consume Canonical Sections And Binding IDs In RAG

**Corresponding specs:** `RETRIEVAL-P0-01..07`, `VOICE-P0-01..02`, `MEDIA-P0-01..02`, `MEDIA-P0-11`

**Files:** modify query planning, packet policy, retriever, hybrid, route policy, retrieval budget, `src/assets/huiji_registry.py`, `voice_pagination.py`; create/modify retrieval and media tests.

- [ ] Route collection synonyms to `item` intent plus `collection` section and route “尤提姆” to `udimo` intent/section.
- [ ] Preserve primary plus secondary intents and guarantee per-intent minimum section coverage before shared budget trimming.
- [ ] Use canonical `collection` and `culture_dossier`; do not rely on old swapped names.
- [ ] Index/select media by `binding_id`, then owner, source binding, asset type and role. Keep `resource_id` for fetch/cache identity only.
- [ ] Keep voice pagination line-based with language variants under each line. Text K stays independent from media-page budget.
- [ ] Add explicit loader branches for installed legacy, v2 and v3 manifest capability. Do not infer schema from fields.
- [ ] Require candidate artifacts, BM25, collection and retrieval policy to share one verified candidate tuple in shadow tests.

**Run:**

```powershell
& $Python -m pytest tests\test_route_policy.py tests\test_retrieval_budget.py tests\test_hybrid_retriever.py tests\test_huiji_media_registry.py tests\test_voice_pagination.py tests\test_multi_intent_voice_eval.py -q
```

**Real acceptance:** isolated fixtures prove collection+voice and Udimo+skill retain both requested sections; a shared resource with two bindings remains selectable in both semantic positions.

**Failure:** single-intent collapse, resource-ID map overwrite, generic image fallback or fixed text-K inflation for audio.

### Task 9: Build And Audit The Official Full-Data Candidate

**Corresponding specs:** all `SOURCE`, `BUILD`, `PROJECTION`, `MEDIA`, `VOICE`, `ARTIFACT`, `FIDELITY` and `PROVENANCE` P0 requirements.

**Entry gate:** Tasks 0-8 pass and `$env:HUIJI_WIKI_V3_COMPAT_RECEIPT` names a file outside the candidate root whose schema and four fixture hashes pass Task 1 validation. This checks compatibility only; it must not be evidence of a candidate import.

- [ ] Validate and hash the Wiki receipt, then derive create-new names:

```powershell
$WikiReceipt = (Resolve-Path -LiteralPath $env:HUIJI_WIKI_V3_COMPAT_RECEIPT).Path
$WikiReceiptSha = (Get-FileHash -LiteralPath $WikiReceipt -Algorithm SHA256).Hash.ToLowerInvariant()
$BuildVersion = 'crawler-v3-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ').ToLowerInvariant()
$CandidateRoot = Join-Path 'data\processed\huiji' $BuildVersion
if (Test-Path -LiteralPath $CandidateRoot) { throw 'Candidate root already exists' }
```

- [ ] Run the candidate command with the approved baseline and an explicit unique evidence directory:

```powershell
& $Python scripts\build_huiji_corpus.py candidate `
  --build-version $BuildVersion `
  --fidelity-baseline $Baseline `
  --expected-fidelity-baseline-sha256 $ExpectedBaselineSha `
  --run-dir "$RunDir\candidate"
if ($LASTEXITCODE -ne 0) { throw 'Candidate build blocked or failed; inspect evidence before retrying with a new build version' }
```

- [ ] Run `verify` against the emitted build manifest hash, then perform full crawler/MySQL read-only reconciliation, MinIO declared-key validation and protected-state comparison.
- [ ] Build a second candidate with a new version against the same source inventory and code/config fingerprint; require byte-equal semantic artifact hashes.
- [ ] Review dynamic high-change samples selected by diff magnitude across entity types and sections, not a named character or fixed count.

**Real acceptance:** all fidelity categories are source-backed, no active binding is lost, no current supported entity coverage declines unexplained, media multiset retains shared-resource groups, and the result is `ready_for_embedding`.

**Failure:** keep the candidate as diagnostic evidence, do not patch it, identify the cause and rerun under a new build version only after correction.

### Task 10: Build An Explicitly Authorized Shadow And Verify It

**Corresponding specs:** `VECTOR-P0-01..03`, `RETRIEVAL-P0-07`

**Files:** modify `scripts/build_huiji_index.py`, shadow builder tests and handoff verifier.

- [ ] Require `--handoff-manifest`, `--expected-handoff-sha256` and an explicit target. Verify candidate child path/hash/count/ordered-ID hash, embedding model/config fingerprint and forbidden target set before model loading or Milvus mutation.
- [ ] Emit the exact command with a new shadow collection name. Run it only after explicit user authorization; otherwise pause at this boundary.
- [ ] In the same PowerShell process, reload `SILICONFLOW_API_KEY` from the User environment, never print it, and clear the process-level variable in `finally`.
- [ ] After the authorized embedding completes, capture collection schema, row count, primary-ID hash, business-row content hash, model/config fingerprint and input manifest linkage.
- [ ] Reject missing, extra, duplicate or content-different rows and retain the shadow for diagnosis without overwrite/delete.

**Run before handoff:**

```powershell
& $Python -m pytest tests\test_huiji_shadow_builder.py tests\test_huiji_corpus_handoff.py -q
```

**Real acceptance:** the explicitly authorized shadow matches the handoff exactly and active collection fingerprints remain unchanged.

**Failure:** any mismatch blocks Task 11; a retry uses a new shadow name and new evidence.

### Task 11: Run Isolated Candidate Full-Chain Acceptance

**Corresponding specs:** `VECTOR-P0-04`, `RETRIEVAL-P0-01..07`, `VOICE-P0-01..02`

**Files:** extend isolated evaluation helpers/tests; create evidence only under `$RunDir\full-chain`.

- [ ] Construct one isolated tuple from candidate parent/child/media/BM25 plus the verified shadow. Refuse any path or collection from the active tuple.
- [ ] Run deterministic multi-intent, collection, culture dossier, Udimo, skill and voice queries selected from the current candidate inventory.
- [ ] Verify source coverage before budget trimming, citation identity, binding-aware media selection, line pagination and language variants.
- [ ] Run negative cases: no dedicated Udimo image, shared resource across bindings, missing role, unsupported schema and attempted mixed tuple.
- [ ] Compare the active runtime verifier before/after and prove normal production requests still use the old active tuple.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_candidate_full_chain.py tests\test_multi_intent_voice_eval.py tests\test_rag_execution.py tests\test_citations.py -q
```

**Real acceptance:** isolated full-chain evidence passes without fixed character/count expectations and without any active-state write.

**Failure:** candidate remains non-active and proposal generation records `full_chain_not_verified`.

### Task 12: Generate Activation-Review Evidence Without Activating

**Corresponding specs:** `ACTIVATION-P0-01..07`, `PROVENANCE-P0-01`, `RETRIEVAL-P0-07`

**Files:** finalize `src/huiji_rag/build/activation_evidence.py`, `scripts/build_huiji_corpus.py proposal`, `tests/test_huiji_activation_proposal.py`; create only a unique proposal directory.

- [ ] Re-capture active artifacts, active Milvus, MySQL and both MinIO bucket inventories and compare them with Task 0. Record deterministic blockers for unexplained drift.
- [ ] Verify candidate build/shadow/full-chain evidence and Wiki compatibility receipt by path and SHA. Never inspect arbitrary candidate directories or latest-by-name.
- [ ] Read and validate `active_build.v1.json` if present. If absent, add `active_pointer_not_bootstrapped`; do not create generation 0.
- [ ] Validate a Wiki pre-import rollback receipt if supplied. If absent, add `wiki_rollback_receipt_missing`.
- [ ] Always create a hash-pinned `activation_proposal.v1.json` and protected-state inventory. Create `rollback_tuple.v1.json` only when the complete previous pointer and Wiki rollback receipt exist.
- [ ] Require `allowed_for_activation_review=false` whenever any blocker exists. Even when true, print that a separate user-approved activation plan is required and exit without mutation.
- [ ] Run a mutation-spy test covering pointer, settings, provenance, Milvus active collection, MySQL and MinIO writers.

**Run:**

```powershell
& $Python -m pytest tests\test_huiji_activation_proposal.py tests\test_huiji_provenance.py tests\test_huiji_wiki_snapshot.py -q
& $Python scripts\build_huiji_corpus.py proposal --help
```

**Real acceptance:** given the currently absent pointer, the expected result is a valid blocked proposal with `active_pointer_not_bootstrapped` and no fabricated rollback tuple. If another approved line has established a verified pointer and rollback receipt by then, a complete proposal/rollback pair may be produced, but active remains unchanged.

**Failure:** any implicit bootstrap, incomplete rollback tuple, unpinned receipt, pointer write or claim that activation occurred is a P0 failure.

### Task 13: Final Mechanical Check And Independent Review

**Corresponding specs:** all 72 P0 requirements.

- [ ] Run focused suites from every task, then the full Python suite:

```powershell
& $Python -m pytest tests -q
```

- [ ] Run source, output-path, credentials and forbidden-writer scans. Confirm Wiki source code and business data were not changed by this plan.
- [ ] Compare Task 0 and final protected-state inventories. Require active artifacts, active Milvus, MySQL and both MinIO buckets to be equal unless a separately authorized external line changed them and the baseline was formally renewed.
- [ ] Generate `$RunDir\acceptance\p0-requirement-matrix.v1.json` with one row per P0 ID: implementation paths, test IDs, real evidence paths/SHA, status and failure behavior.
- [ ] Verify the matrix contains all 72 unique P0 IDs, no unknown IDs and no passing row without both automated and real evidence.
- [ ] Perform an independent read-only review of Spec, Plan, requirement matrix and candidate manifests. Findings must be resolved in code or recorded as blockers; review prose cannot override a failed machine gate.
- [ ] Scan documents and evidence for unfinished placeholder markers, credentials, absolute backup paths used as outputs, fixed character-specific acceptance and claims that active was switched.

**Completion:** the Builder/retrieval P0 implementation may be marked complete when all implementation and candidate/shadow/full-chain gates pass and the proposal behavior is correct. Activation readiness is a separate status and may remain blocked by the known pointer/bootstrap or Wiki rollback precondition.

## 6. Wiki Handoff Contract

The Wiki line may begin its compatibility work after this Spec and Plan are approved. It owns these changes and evidence:

- Correct old Wiki Specs so the formal source flow is crawler raw -> corpus builder -> active artifacts -> Wiki MySQL projection -> `/api/wiki/*`; remove `data/raw`, Obsidian and supplement tables as formal sources.
- Add v2/v3 snapshot branches and normalize v3 binding rows into `wiki_media_resources` plus `wiki_media_bindings`.
- Preserve `resourceId`, `bindingId`, compatibility `mediaId`, role, variant, section, owner/page IDs, skin ID and sort order through importer, repository, API and React.
- Use `bindingId` for list keys/maps and never collapse rows by SHA, object key, URL, `resourceId` or compatibility `mediaId`.
- Create migration/rollback scripts and tests without importing an unverified candidate.
- Publish `eval/huiji_wiki_v3_compatibility/<run-id>/wiki_media_v3_compatibility_receipt.v1.json`, pinning all four shared fixture hashes and proving dual-read compatibility.

RAG owns the frozen schema/fixture and receipt validator. Wiki owns database/API/frontend compatibility. Neither line may declare the other's tests passed without reading hash-pinned evidence.

## 7. Deferred / Out Of Scope

- P1 inheritance/portray retrieval and richer profile labels.
- P1 roster/stage/skin-background semantic filters beyond preserving explicit v3 fields.
- P2 skin-level voice/media filtering, psychube expansion, remote build service and cache.
- Deleting 1,382 MinIO orphan objects or scanning MinIO to infer page relationships.
- Uploading/migrating media, rebuilding or deleting active Milvus, or embedding into any active, historical or pre-existing collection.
- Wiki MySQL/API/frontend implementation, candidate import or top-level Wiki category changes.
- Active pointer bootstrap, active switch, runtime traffic commit, Wiki formal import and rollback execution.
- Any write, restore target, lock or maintenance action under `D:\1999Wiki_Backup`.

## 8. Completion Self-Check

- [ ] All 72 P0 IDs appear exactly once in the acceptance matrix and map to implementation, tests, real evidence and failure behavior.
- [ ] The four crawler files are the only corpus inputs; MySQL/MinIO/active artifacts are comparison surfaces only.
- [ ] `HuijiCorpusBuilder` is the only full builder and `EvbBuilder` delegates to `VoiceBindingStage`.
- [ ] Media v3 uses the frozen fields, labels, paths and deterministic resource/binding IDs.
- [ ] Shared resources retain every binding; no consumer map or BM25 comparison folds them.
- [ ] Collection, culture dossier and Udimo sections are source-backed and preserve the rest of the active corpus.
- [ ] Every active parent, child, media binding, excluded row and BM25 record is classified exactly once; unexplained losses are zero.
- [ ] Candidate artifacts and BM25 are deterministic, manifest-complete and immutable.
- [ ] Retrieval consumes primary/secondary intents, canonical sections and binding-aware media while preserving voice pagination.
- [ ] User-built shadow and isolated full-chain evidence match the candidate tuple exactly.
- [ ] Wiki compatibility evidence is hash-pinned; absent pointer/rollback evidence yields a blocked proposal.
- [ ] Active artifacts, active Milvus, MySQL, MinIO and installed provenance remain unchanged by this plan.
- [ ] No active pointer switch, candidate Wiki import, MinIO mutation or backup-repository write occurred.

## 9. 2026-07-21 Execution Record

The approved implementation plan was executed in the existing dirty worktree without subagents or writes to `D:\1999Wiki_Backup`.

- Candidate F is `data/processed/huiji/crawler-v3-20260721t051246z`; its manifest SHA-256 is `293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f`. It contains 8,268 parents, 14,630 children, 19,132 resources and 19,400 binding rows and is `ready_for_embedding` with zero blockers.
- Candidate G is `data/processed/huiji/crawler-v3-20260721t054535z`. Its semantic artifacts, ordered IDs, code/config fingerprints and source inventory match Candidate F. The reproducibility receipt is `eval/huiji_corpus_builder/20260721T051246Z-candidate-f/acceptance/reproducibility.v1.json`, SHA-256 `0574f02be330d602842f5f41dc05ad4846ba60dab371f64ff7dc98013c552499`.
- The hash-pinned embedding handoff SHA-256 is `3c8aa20985ad0f8979a6b0d07e0bfd7a1aeb454ac0860eb33d98e7caedecb2a6`. The authorized shadow `text_child_bge_m3_shadow_crawler_v3_20260721t051246z` contains exactly 14,630 rows. Shadow evidence SHA-256 is `0eb85ed2c60b4a500fef92ddad11e0fbbb190c32057e795a9f5a8dd4e1974cfa`.
- Isolated full-chain evidence is `eval/huiji_candidate_full_chain/20260721T070710Z-candidate-f-shadow/full-chain.v1.json`, SHA-256 `8d95408baea543de9788a0b618e718fc202adc3cec8ecc849eb315c34f45b12c`. It passed generic multi-intent, collection, culture dossier, Udimo, skill, voice pagination, shared-binding and negative fallback checks.
- Final protected-state comparison passed. The active collection remains `text_child_bge_m3_v3` with 16,010 rows; the new shadow remains 14,630 rows. No active pointer, Wiki import, MySQL mutation, MinIO business-object mutation or active collection write was performed.
- The activation proposal is intentionally blocked by `active_pointer_not_bootstrapped` and `wiki_rollback_receipt_missing`. Proposal SHA-256 is `ce5e6966b80f0b9f1c2300e95866a7d0b9b8d9e108333311f0f92a8d27af1536`; no rollback tuple or active pointer was fabricated.
- The persisted full-suite result is 1,299 passed, 1 skipped and zero failures. The 72-row machine-checkable matrix is `eval/huiji_corpus_builder/20260721T051246Z-candidate-f/acceptance/p0-requirement-matrix.v1.json`, SHA-256 `dccb4d9cd374415e2957c38fa00e4bbe73e4b3dd8cb338198a897dfd7e2a1c2f`.
- The independent mechanical review is recorded at `eval/huiji_corpus_builder/20260721T051246Z-candidate-f/acceptance/independent-review.v1.json`. Activation remains a separate, explicitly approved operation.
