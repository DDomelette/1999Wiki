# Thread C Topic/Story/Page Projection And Wikitext Media Implementation Plan

> **Execution mode:** Execute task-by-task in the existing `codex/rag-c-projection` worktree and the original long-lived Codex session. Use `gpt-5.6-sol`, standard speed, `workspace-write`, `fast_mode=false`, and `multi_agent=false`. Do not create subagents, invoke another Codex CLI, or read unmerged A/B worktrees.

**Goal:** Extend the single offline Huiji corpus builder so one verified crawler snapshot is streamed through page/revision/Data/resource joins, source-backed Page/Story/Topic projection, bounded Wikitext parsing, exact Wikitext media binding, and read-only capacity planning without regressing existing character, Voice, Media V3, fidelity, or artifact closure.

**Architecture:** A recovery receipt gate admits exactly four frozen crawler JSONL files into `CrawlerSemanticInputs`. Streaming readers create bounded identity indexes and diagnostics; independent page, Wikitext, Story, and Topic stages produce the frozen Parent/Child contract. Wikitext media intents resolve by exact normalized filename, retain binding multiplicity, and feed the existing Media V3 assembler only when local content is verified. A separate referenced-media planner emits deterministic allowlist and capacity evidence; neither the builder nor this thread performs network, MinIO, MySQL, Milvus, or activation writes.

**Tech stack:** Python 3.12, dataclasses, incremental JSON/JSONL and SHA-256, bounded Wikitext scanner, pytest, existing canonical artifact writer, existing Media V3 contracts, PowerShell for read-only acceptance commands.

**Approved spec:** `docs/superpowers/specs/2026-07-29-rag-thread-c-topic-story-media-projection-design.md` at baseline commit `ed569ee23f5d3927f8a332e69ef4de82ac8b6c59`.

**Supervision plan:** `docs/superpowers/plans/2026-07-29-rag-cli-supervision.md`.

---

## 1. Baseline Facts And Non-Negotiable Boundaries

1. `HuijiCorpusBuilder._build_candidate()` currently reads all of `data_pages.jsonl` and `resources_manifest.jsonl` into lists, does not semantically consume `pages.jsonl` or `wikitext.jsonl`, and calls `project_crawler_semantics(data_rows)` only.
2. `project_crawler_semantics()` currently filters Data rows by title markers. `_project_generic()` catches invalid JSON and projects the invalid `content` as text. Thread C must remove that behavior specifically for crawler wrappers with `json_valid=false`: the wrapper becomes `invalid_data_wrapper` excluded evidence and its `content` is never parsed or projected.
3. `source_inventory.py` already streams and hashes all four files, but it treats duplicate source identities as globally fatal and does not provide semantic row diagnostics, bounded join indexes, recovery receipt validation, or per-stage RSS/timing.
4. `ChildBlock` currently lacks the frozen `content`, `heading_path`, and `entity_aliases` fields. These are the only public Child additions allowed in `models.py`; `content == text` is mandatory.
5. `MediaBindingIntent` and `_ResourceCatalog` currently use legacy stem matching. Wikitext intents require a separate exact-filename path; legacy structured Data stem behavior must remain intact.
6. Existing Media V3 runtime rows require a contained local file with verified SHA-1, SHA-256, and size. Not-downloaded Wikitext media therefore remains intent/allowlist/capacity evidence and keeps the candidate `diagnostic_only`; it is not emitted as a fake runtime row.
7. The canonical raw writeback of `data_pages.jsonl` and `crawl_state.sqlite` is owned by D. C never copies, restores, rewrites, or recrawls either file and never modifies canonical `crawl_state.sqlite`.
8. The one recovery wrapper with `json_valid=false` closes `REC-P0-06` only after both the fixture test and restored-snapshot diagnostic prove one excluded-evidence row and zero projected children/media intents from its invalid `content`.
9. This plan does not modify Planner, Retriever, route policy, request planning, sparse/BM25 analyzer or payload/provenance schema. B-related semantic-hash integration is deferred to D after B → C merge.
10. No task downloads media, writes MinIO/MySQL/Milvus, performs embedding, creates or switches an active pointer, rewrites production baselines, or activates a candidate.

### 1.1 Files Thread C May Change During Approved Implementation

```text
src/huiji_rag/build/projection.py
src/huiji_rag/build/page_sources.py
src/huiji_rag/build/wikitext_projection.py
src/huiji_rag/build/story_projection.py
src/huiji_rag/build/topic_projection.py
src/huiji_rag/build/media_download_plan.py
src/huiji_rag/build/media_v3.py
src/huiji_rag/build/orchestrator.py
src/huiji_rag/build/contracts.py
src/huiji_rag/models.py
src/huiji_rag/resources/topic_catalog.v1.json
src/huijiwiki/resource_downloader.py
tests/fixtures/huiji_topic_story_media_projection/*
tests/test_huiji_page_sources.py
tests/test_huiji_wikitext_projection.py
tests/test_huiji_story_projection.py
tests/test_huiji_topic_projection.py
tests/test_huiji_media_download_plan.py
tests/test_huiji_corpus_projection.py
tests/test_huiji_corpus_projection_fidelity.py
tests/test_huiji_corpus_builder.py
tests/test_huiji_corpus_builder_contracts.py
tests/test_huiji_corpus_source_inventory.py
tests/test_huiji_media_v3_builder.py
tests/test_huiji_media_v3_contract.py
tests/test_huiji_corpus_artifacts.py
tests/test_huiji_corpus_fidelity.py
tests/test_huiji_resource_downloader.py
tests/test_huiji_models.py
```

If implementation needs any file outside this allowlist or any public field beyond Section 13 of the Spec, stop with `status=needs_approval`; do not broaden scope.

### 1.2 Explicitly Forbidden Files And State

```text
src/rag/query_plan.py
src/rag/request_plan.py
src/rag/route_policy.py
src/rag/retriever.py
src/rag/chain.py
src/rag/sparse.py
src/rag/chinese_analyzer.py
BM25 payload/provenance schema
formal raw and processed data
active pointer and production baseline
Milvus collections
MySQL production tables
MinIO objects
unmerged A/B worktree files
```

---

## 2. Complete P0 Traceability

The task numbers below are the primary implementation owners. Supporting regression or real-data gates may appear in later tasks.

| P0 IDs | Primary task | Automated/real gate |
|---|---:|---|
| `SCOPE-P0-01`, `SCOPE-P0-02`, `SCOPE-P0-03` | 0, 5, 6 | public JSON-only contract; D-owned recovery; approval-bound downloader |
| `DECISION-P0-01`, `DECISION-P0-02`, `DECISION-P0-03` | 2, 3, 4, 6 | bounded scanner; exact relations; offline builder |
| `ARCH-P0-01`, `ARCH-P0-02`, `ARCH-P0-03`, `ARCH-P0-04` | 1, 2, 3, 4, 7 | unified inputs, separate stages, one builder, read-only stores |
| `RECOVERY-P0-01`, `RECOVERY-P0-02`, `RECOVERY-P0-03`, `RECOVERY-P0-04`, `RECOVERY-P0-05`, `RECOVERY-P0-06` | 0, 1, 8 | receipt identity gate; no causation claim; invalid-wrapper exclusion; frozen SQLite |
| `STREAM-P0-01`, `STREAM-P0-02`, `STREAM-P0-03`, `STREAM-P0-04`, `STREAM-P0-05` | 1, 8 | incremental reader spies, bounded indexes, deterministic passes, metrics, line diagnostics |
| `JOIN-P0-01`, `JOIN-P0-02`, `JOIN-P0-03`, `JOIN-P0-04`, `JOIN-P0-05`, `JOIN-P0-06`, `JOIN-P0-07`, `JOIN-P0-08`, `JOIN-P0-09`, `JOIN-P0-10` | 1, 2 | exact page/revision join and redirect graph tests |
| `SOURCE-P0-01`, `SOURCE-P0-02`, `SOURCE-P0-03`, `SOURCE-P0-04`, `SOURCE-P0-05` | 1, 2, 3, 4 | canonical crawler refs, offsets, JSON paths, no local secrets |
| `WIKI-P0-01`, `WIKI-P0-02`, `WIKI-P0-03`, `WIKI-P0-04`, `WIKI-P0-05`, `WIKI-P0-06`, `WIKI-P0-07`, `WIKI-P0-08`, `WIKI-P0-09`, `WIKI-P0-10` | 2 | bounded scanner fixture matrix and network spy |
| `PAGE-P0-01`, `PAGE-P0-02`, `PAGE-P0-03`, `PAGE-P0-04`, `PAGE-P0-05`, `PAGE-P0-06`, `PAGE-P0-07` | 2 | deterministic section/chunk projection tests |
| `STORY-P0-01`, `STORY-P0-02`, `STORY-P0-03`, `STORY-P0-04`, `STORY-P0-05`, `STORY-P0-06`, `STORY-P0-07`, `STORY-P0-08`, `STORY-P0-09`, `STORY-P0-10` | 3 | exact relation/name priority and story-step tests |
| `TOPIC-P0-01`, `TOPIC-P0-02`, `TOPIC-P0-03`, `TOPIC-P0-04`, `TOPIC-P0-05`, `TOPIC-P0-06`, `TOPIC-P0-07` | 4 | catalog selector and source-backed topic tests |
| `CONTRACT-P0-01`, `CONTRACT-P0-02`, `CONTRACT-P0-03`, `CONTRACT-P0-04`, `CONTRACT-P0-05`, `CONTRACT-P0-06`, `CONTRACT-P0-07` | 3, 4, 7 | exact Child fields/types, legacy enrichment diff, D-owned B integration |
| `MEDIA-P0-01`, `MEDIA-P0-02`, `MEDIA-P0-03`, `MEDIA-P0-04`, `MEDIA-P0-05`, `MEDIA-P0-06`, `MEDIA-P0-07`, `MEDIA-P0-08`, `MEDIA-P0-09` | 5 | stable relation token, exact child, multibinding, title/context/role/decorative rules |
| `RESOURCE-P0-01`, `RESOURCE-P0-02`, `RESOURCE-P0-03`, `RESOURCE-P0-04`, `RESOURCE-P0-05`, `RESOURCE-P0-06` | 5 | exact filename catalog separated from legacy stem resolver |
| `CAPACITY-P0-01`, `CAPACITY-P0-02`, `CAPACITY-P0-03`, `CAPACITY-P0-04`, `CAPACITY-P0-05`, `CAPACITY-P0-06`, `CAPACITY-P0-07`, `CAPACITY-P0-08`, `CAPACITY-P0-09`, `CAPACITY-P0-10`, `CAPACITY-P0-11`, `CAPACITY-P0-12`, `CAPACITY-P0-13`, `CAPACITY-P0-14`, `CAPACITY-P0-15` | 6 | deterministic allowlist, formulas, hard budgets, three-set overflow and approval-only decisions |
| `DOWNLOAD-P0-01`, `DOWNLOAD-P0-02`, `DOWNLOAD-P0-03`, `DOWNLOAD-P0-04`, `DOWNLOAD-P0-05`, `DOWNLOAD-P0-06`, `DOWNLOAD-P0-07` | 6, 7 | pinned allowlist support only; staging receipt; no execution/upload/activation |
| `BUILD-P0-01`, `BUILD-P0-02`, `BUILD-P0-03`, `BUILD-P0-04`, `BUILD-P0-05`, `BUILD-P0-06` | 7 | four semantic sources, fingerprints, diagnostics, state matrix, create-new roots, no embedding |
| `FIDELITY-P0-01`, `FIDELITY-P0-02`, `FIDELITY-P0-03`, `FIDELITY-P0-04`, `FIDELITY-P0-05`, `FIDELITY-P0-06` | 7, 8 | active-row classifications, enrichment split, multiset preservation, deterministic rebuild, protected-state check |
| `ERROR-P0-01`, `ERROR-P0-02`, `ERROR-P0-03`, `ERROR-P0-04`, `ERROR-P0-05` | 1, 2, 3, 4, 5, 7 | local exclusions vs blockers, sanitized diagnostics, no automatic scope expansion |
| `TEST-P0-01`, `TEST-P0-02`, `TEST-P0-03`, `TEST-P0-04`, `TEST-P0-05`, `TEST-P0-06`, `TEST-P0-07` | 1 through 9 | named fixture, focused and regression commands |
| `REAL-P0-01`, `REAL-P0-02`, `REAL-P0-03`, `REAL-P0-04`, `REAL-P0-05`, `REAL-P0-06`, `REAL-P0-07`, `REAL-P0-08` | 8 | restored-snapshot streaming diagnostics and capacity forecast only |
| `OWN-P0-01`, `OWN-P0-02`, `OWN-P0-03` | 0, 3, 9 | frozen fields only; no B hash code; stop on extra public fields |
| `AGENT-P0-01`, `AGENT-P0-02`, `AGENT-P0-03`, `AGENT-P0-04`, `AGENT-P0-05` | all tasks | original standard-speed single session; no subagents; plan review and recovery gates |
| `PHASE-P0-01` | 1 through 9 | D review after each phase commit before continuing |

Coverage count: 155 unique P0 IDs. No P0 requirement is assigned to P1/P2.

---

## 3. Frozen Contracts And Failure Taxonomy

### 3.1 Public Child Contract

Every serialized child must expose these fields with stable types:

```text
category           string
entity_type        string
entity_id          string
entity_name        string
entity_aliases     array<string>
owner_entity_id    string
owner_page_id      string
route_tags         array<string>
parent_id          string
child_id           string
heading_path       array<string>
section_kind       string
content            string
text               string
search_text        string
source_refs        array<object>
```

`content` and `text` are byte-for-byte equal strings. `heading_path` is non-empty. Existing character/item/psychube rows receive deterministic compatibility values without content, owner, section, or route changes. `owner_type` is forbidden.

### 3.2 Source Reference Minimums

All new source refs contain:

```text
source_kind
source_title
source_row_id
source_content_sha256
```

Wikitext refs additionally carry page/revision, heading path and original character offsets. Data refs retain revision and JSON path. Public refs never include absolute paths, cookies, headers, database details, or external recovery locations.

### 3.3 Local Exclusions

Local exclusions preserve other valid rows:

```text
invalid_data_wrapper
missing_latest_revision
orphan_revision
unsupported_template_media
unsupported_html_media
unbalanced_wikilink
unclosed_gallery
dynamic_display_title
page_without_visible_content
story_raw_id_fallback
topic_evidence_shortfall
decorative_media_excluded
referenced_resource_missing
referenced_resource_not_downloaded
capacity_budget_excluded
```

### 3.4 Build Blockers

The candidate remains `blocked` for:

```text
source_recovery_invalid
source_inventory_drift
page_identity_conflict
revision_identity_conflict
story_name_conflict
resource_filename_conflict
source_identity_collision
parent_child_media_closure_broken
protected_state_drift
unexplained_fidelity_loss
capacity_blocked
unknown_capacity
```

No failure automatically expands parser syntax, fuzzy joins, download range, media budget, or writable stores.

---

## 4. Task 0 — Revalidate Session, Recovery Ownership, And Clean Baseline

**Corresponding P0:** `SCOPE-P0-03`, `RECOVERY-P0-01..06`, `OWN-P0-01..03`, `AGENT-P0-01..05`.

**Files:** no implementation files; read-only checks only.

### Step 1: Confirm execution identity

Run:

```powershell
git status --short --branch
git log -1 --format="%H %s"
git diff --name-only
```

Expected:

- branch is `codex/rag-c-projection`;
- baseline contains approved Spec commit ancestry;
- worktree is clean before implementation;
- no A/B worktree path is read.

### Step 2: Confirm D-owned recovery inputs without restoring

Check only the existence and JSON shape of:

```text
config/recovery/huiji-res1999-20260707.json
D:\1999Wiki\.codex-supervisor\recovery\audit.json
D:\1999Wiki\.codex-supervisor\recovery\apply.json
```

The C preflight introduced in Task 1 will perform cryptographic validation. At this task, do not copy `data_pages.jsonl`, do not copy `crawl_state.sqlite`, do not recrawl, and do not open SQLite in write mode.

### Step 3: Record blocked conditions

If either receipt is absent, not completed, or inconsistent, fixture implementation may proceed through Task 7, but Task 8 remains blocked. Report `source_recovery_invalid`; do not infer why files were missing.

**Failure manifestation:** wrong branch, dirty out-of-scope files, missing approved Spec ancestry, need for extra public fields, or need to modify a forbidden file yields `status=needs_approval`.

**Commit:** none.

---

## 5. Task 1 — Add Streaming Inputs, Recovery Gate, Join Diagnostics, And Invalid-Wrapper Exclusion

**Corresponding P0:** `ARCH-P0-01`, `RECOVERY-P0-01..06`, `STREAM-P0-01..05`, `JOIN-P0-01..06`, `SOURCE-P0-01`, `SOURCE-P0-03..05`, `ERROR-P0-01..04`, `TEST-P0-01`.

**Files:**

- Create `src/huiji_rag/build/page_sources.py`.
- Modify `src/huiji_rag/build/contracts.py`.
- Modify `src/huiji_rag/build/projection.py`.
- Modify `src/huiji_rag/build/orchestrator.py`.
- Create `tests/fixtures/huiji_topic_story_media_projection/pages.jsonl`.
- Create `tests/fixtures/huiji_topic_story_media_projection/wikitext.jsonl`.
- Create `tests/fixtures/huiji_topic_story_media_projection/data_pages.jsonl`.
- Create `tests/fixtures/huiji_topic_story_media_projection/resources_manifest.jsonl`.
- Create `tests/test_huiji_page_sources.py`.
- Modify `tests/test_huiji_corpus_projection.py`.
- Modify `tests/test_huiji_corpus_builder.py`.
- Modify `tests/test_huiji_corpus_source_inventory.py`.

### Step 1: Write RED tests for streaming and recovery identity

Add named tests:

```text
test_semantic_inputs_stream_exactly_four_crawler_files
test_recovery_gate_requires_pinned_manifest_audit_apply_and_file_identity
test_recovery_gate_never_writes_or_opens_canonical_sqlite_for_write
test_stream_reader_never_calls_path_read_text_or_splitlines
test_stream_reader_reports_utf8_json_schema_and_oversize_line_identity
test_stream_metrics_report_rows_accept_exclude_rss_or_unavailable_and_elapsed
test_bounded_indexes_do_not_duplicate_wikitext_or_data_content
test_identical_source_rows_dedupe_but_conflicting_page_or_revision_blocks
test_latest_revision_join_rejects_missing_stale_or_title_conflict
test_orphan_revision_and_nonzero_namespace_do_not_project_page
```

Use monkeypatch spies on `Path.read_text`, list-returning `_read_jsonl`, network functions, and SQLite connections. Build a fixture with identical duplicates, conflicting duplicates, stale revisions, orphan revisions, and one `ns != 0` page.

Run:

```powershell
python -m pytest tests/test_huiji_page_sources.py tests/test_huiji_corpus_source_inventory.py -q
```

Expected RED:

- `page_sources` module does not exist;
- orchestrator still calls list-returning `_read_jsonl`;
- no recovery semantic gate exists.

### Step 2: Write the mandatory RED invalid-wrapper test

Add exactly one fixture wrapper:

```json
{
  "site": "res1999",
  "pageid": 9001,
  "revid": 9002,
  "title": "Data:Story/invalid.json",
  "json_valid": false,
  "json_error": "fixture invalid payload",
  "content": "{\"id\":\"must-not-project\","
}
```

Add:

```text
test_json_valid_false_wrapper_emits_excluded_evidence_without_parsing_content
test_invalid_wrapper_does_not_block_valid_neighbors
test_invalid_wrapper_cannot_create_parent_child_story_or_media_intent
```

Patch `json.loads` with a sentinel that fails if called with the invalid wrapper `content`. Assert one `ProjectionExclusion` with reason `invalid_data_wrapper`, source title/revision/content hash/line identity, sanitized JSON error metadata, and no invalid content bytes in public diagnostics.

Run:

```powershell
python -m pytest tests/test_huiji_corpus_projection.py -k "json_valid_false or invalid_wrapper" -q
```

Expected RED: `_project_generic()` currently catches `JSONDecodeError` and projects invalid content as fallback text.

`REC-P0-06` remains open after this RED test and remains open after fixture GREEN; it closes only in Task 8 when the restored snapshot also produces exactly one excluded row.

### Step 3: Implement minimal streaming contracts

Add immutable contracts for:

```text
CrawlerSemanticInputs
SemanticSourceMetrics
SourceDiagnostic
PageMetadata
RevisionMetadata
JoinedPageRevision
RecoveryGateEvidence
```

Implement binary/UTF-8 incremental JSONL iteration with:

- one line at a time;
- source filename and 1-based line number;
- byte/character size guard;
- schema validation;
- file signature before/after;
- explicit accepted/excluded counters;
- peak RSS from `psutil` when available, otherwise literal `unavailable`;
- elapsed monotonic time;
- no permanent intermediate source.

Allowed indexes contain metadata/offsets only. If a later stage needs content, it rereads the frozen file deterministically by recorded offset or performs a deterministic second sequential pass.

### Step 4: Implement recovery preflight

Validate:

- manifest schema and exact expected file identities;
- audit/apply receipt snapshot ID and completed state;
- `invalid_payload_rows == 1`;
- canonical `data_pages.jsonl` size/SHA/readability;
- canonical `crawl_state.sqlite` size/SHA/readability and read-only `PRAGMA quick_check`;
- no receipt or source path leaks into public output.

The preflight has no apply/copy/repair method.

### Step 5: Implement page/revision identity indexes

Use crawler `pageid` and `(pageid, revid, content_sha256)`. Deduplicate byte/canonical-equal rows. Record conflicts rather than overwriting. Only `status=active`, `ns=0`, exact `lastrevid` joins are eligible for Page projection. Preserve missing/stale/orphan diagnostics.

### Step 6: Implement invalid-wrapper exclusion before any payload parser

At the earliest Data row boundary:

```text
if wrapper.json_valid is false:
    emit invalid_data_wrapper exclusion
    do not call json.loads(wrapper.content)
    continue
```

Do not apply `_project_generic()` fallback to this wrapper. Other valid rows continue.

### Step 7: Run focused GREEN and regressions

```powershell
python -m pytest `
  tests/test_huiji_page_sources.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_huiji_corpus_projection_fidelity.py `
  tests/test_huiji_corpus_source_inventory.py `
  tests/test_huiji_snapshot_recovery.py `
  -q
```

Expected GREEN: all join/stream tests pass; one invalid wrapper produces one exclusion and zero semantic outputs.

**Failure manifestation:** receipt mismatch blocks real runs; per-row parse/schema errors produce line diagnostics; identity conflicts block affected projection; one invalid wrapper never blocks valid neighbors.

**Commit boundary:**

```text
feat(rag): join crawler pages revisions and Data relations
```

Before Task 2, stop for D review of tests, file ownership, recovery non-write behavior, and this commit.

---

## 6. Task 2 — Implement Bounded Wikitext Scanner, Redirects, And Page Section Projection

**Corresponding P0:** `DECISION-P0-01`, `ARCH-P0-02`, `JOIN-P0-07..10`, `SOURCE-P0-01..05`, `WIKI-P0-01..10`, `PAGE-P0-01..07`, `ERROR-P0-01..05`, `TEST-P0-02`.

**Files:**

- Create `src/huiji_rag/build/wikitext_projection.py`.
- Modify `src/huiji_rag/build/page_sources.py`.
- Modify `src/huiji_rag/build/projection.py`.
- Create `tests/test_huiji_wikitext_projection.py`.
- Modify the four-file fixture.

### Step 1: Write RED scanner tests

Add named tests:

```text
test_scanner_tracks_lead_h2_h3_through_h6_heading_paths_and_offsets
test_internal_links_keep_label_as_visible_text_without_aliasing_target
test_file_namespaces_and_gallery_preserve_original_filename_and_context
test_file_options_separate_caption_alt_link_layout_and_unknown_options
test_simple_display_title_adds_alias_but_dynamic_form_is_diagnostic
test_nested_links_and_templates_do_not_cross_consume_tokens
test_unsupported_template_html_unbalanced_link_and_unclosed_gallery_are_isolated
test_scanner_never_calls_network_wiki_api_mysql_or_renderer
test_table_projection_preserves_header_cell_and_row_order
```

Run:

```powershell
python -m pytest tests/test_huiji_wikitext_projection.py -q
```

Expected RED: module/API absent.

### Step 2: Implement the bounded scanner

Implement a state machine, not one greedy regex:

- heading levels 2–6 and ordered paths;
- ordinary `[[Target]]` and `[[Target|Label]]`;
- File/文件/Image/图像 links;
- `<gallery>` line parsing;
- recognized image options and unknown-option diagnostics;
- simple pure-text `DisplayTitle`;
- basic table visible text;
- balanced link/template depth;
- exact source character offsets.

Unsupported Lua, complex templates, parser functions, CSS background, bare image URLs and arbitrary HTML remain diagnostics. A malformed token affects only its page/container and never erases later valid sections.

### Step 3: Write RED redirect and Page tests

```text
test_exact_redirect_adds_alias_and_emits_no_redirect_body_child
test_dangling_cycle_cross_namespace_and_conflicting_redirect_are_diagnostic
test_page_ids_use_pageid_heading_sha20_occurrence_and_zero_padded_chunk
test_page_chunking_targets_1200_caps_indivisible_blocks_at_1600_and_has_no_overlap
test_page_search_text_contains_title_alias_heading_link_labels_and_content
test_page_route_tags_require_structured_definition_story_or_event_evidence
test_sparse_page_child_requires_verified_link_or_image_and_empty_page_is_excluded
test_repeated_build_has_equal_page_ids_order_content_hash_and_source_refs
```

Run:

```powershell
python -m pytest tests/test_huiji_wikitext_projection.py -k "redirect or page or chunk" -q
```

Expected RED: scanner output is not yet projected.

### Step 4: Implement redirect graph and Page projection

- Detect local redirect markers before body projection.
- Resolve only exact active snapshot titles.
- Add redirect aliases only after cycle/dangling/namespace/conflict checks.
- Use `page:<pageid>`, `page:<pageid>/section:<token>`, and zero-padded chunk IDs.
- `lead` is fixed; other tokens are SHA-256 heading-path prefix plus deterministic duplicate occurrence suffix.
- Chunk visible text by paragraph, then sentence/newline, with no overlap.
- Populate frozen public fields and canonical Wikitext source refs.
- Store image references from scanner output for Task 5, but do not resolve resources yet.

### Step 5: Run focused GREEN

```powershell
python -m pytest `
  tests/test_huiji_page_sources.py `
  tests/test_huiji_wikitext_projection.py `
  tests/test_huiji_corpus_projection.py `
  -q
```

**Failure manifestation:** unsupported/malformed syntax is a sanitized page-local diagnostic; page/revision identity conflict remains a blocker; no fuzzy title matching or template expansion is introduced.

**Commit:** held with Tasks 3–4 for the C2 projection commit after all public Child projections are green.

---

## 7. Task 3 — Freeze Child Enrichment And Project Source-Backed Story Names And Content

**Corresponding P0:** `DECISION-P0-02`, `STORY-P0-01..10`, `CONTRACT-P0-01..07`, `SOURCE-P0-03..05`, `ERROR-P0-01..05`, `TEST-P0-03`, `OWN-P0-01..03`.

**Files:**

- Create `src/huiji_rag/build/story_projection.py`.
- Modify `src/huiji_rag/build/projection.py`.
- Modify `src/huiji_rag/models.py` only for `content`, `heading_path`, `entity_aliases`.
- Modify `src/huiji_rag/build/contracts.py`.
- Create `tests/test_huiji_story_projection.py`.
- Modify `tests/test_huiji_models.py`.
- Modify `tests/test_huiji_corpus_projection.py`.
- Modify `tests/test_huiji_corpus_projection_fidelity.py`.

### Step 1: Write RED public-contract tests

```text
test_child_json_has_exact_frozen_common_fields_and_no_owner_type
test_content_equals_text_for_legacy_and_new_children
test_every_child_has_nonempty_heading_path_and_explicit_entity_aliases
test_legacy_character_enrichment_does_not_change_text_owner_section_or_route
test_schema_enrichment_is_separate_from_semantic_fidelity_change
```

Run:

```powershell
python -m pytest tests/test_huiji_models.py tests/test_huiji_corpus_projection_fidelity.py -k "content or heading_path or entity_aliases or enrichment" -q
```

Expected RED: `ChildBlock` lacks the three frozen fields.

### Step 2: Implement minimal compatible Child enrichment

Append defaulted fields without reordering or refactoring Media/Voice models. `from_json()` accepts old rows and derives deterministic compatibility values; `to_json()` emits explicit values. Stop if another public field appears necessary.

### Step 3: Write RED Story relation/name tests

```text
test_story_uses_payload_name_before_all_relation_names
test_story_uses_exact_chapter_element_name_when_payload_has_no_name
test_story_uses_episode_before_main_after_name_with_controlled_phase_label
test_story_accepts_exact_page_or_data_relation_but_never_fuzzy_similarity
test_same_priority_story_name_conflict_blocks_only_affected_story
test_lower_priority_names_become_sorted_aliases
test_raw_story_id_fallback_sets_weak_entity_name_and_remains_searchable
test_story_steps_keep_scene_speaker_dialogue_choice_order_and_json_paths
test_story_control_fields_resource_paths_and_booleans_do_not_enter_content
test_story_missing_media_never_removes_text_child
test_story_ids_use_business_id_scene_or_stable_step_and_hash_fallback_evidence
```

Run:

```powershell
python -m pytest tests/test_huiji_story_projection.py -q
```

Expected RED: story module/API absent and generic projection still collapses Story into one profile/root child.

### Step 4: Implement deterministic multi-pass Story relation index

Perform bounded sequential passes over Data wrappers:

1. collect Story stable IDs and direct non-placeholder names;
2. collect exact ChapterElement/Chapter/Episode relations;
3. resolve fixed-priority names and conflicts;
4. project Story steps/scenes in source order.

Do not retain all Data payloads in multiple indexes. Preserve original Data source refs and exact JSON paths. Resource paths, background/CG/audio, and control fields remain source metadata or P1 diagnostics, not P0 media.

### Step 5: Run focused GREEN and legacy projection regression

```powershell
python -m pytest `
  tests/test_huiji_story_projection.py `
  tests/test_huiji_models.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_huiji_corpus_projection_fidelity.py `
  -q
```

**Failure manifestation:** same-priority name conflict blocks that Story; raw-ID fallback is visible and weak; malformed Story excludes only that row; no missing media deletes text.

**Commit:** held for Task 4.

---

## 8. Task 4 — Project Catalog-Selected, Source-Backed Topics

**Corresponding P0:** `DECISION-P0-02`, `ARCH-P0-02`, `TOPIC-P0-01..07`, `CONTRACT-P0-01..07`, `SOURCE-P0-04..05`, `ERROR-P0-01..05`, `TEST-P0-04`.

**Files:**

- Create `src/huiji_rag/build/topic_projection.py`.
- Create `src/huiji_rag/resources/topic_catalog.v1.json`.
- Modify `src/huiji_rag/build/projection.py`.
- Create `tests/test_huiji_topic_projection.py`.
- Modify the four-file fixture.

### Step 1: Write RED catalog schema and selector tests

```text
test_topic_catalog_v1_contains_storm_and_reverse_1999_selectors
test_catalog_is_selector_metadata_not_fact_content
test_topic_accepts_exact_page_title_redirect_heading_or_controlled_definition
test_scattered_character_voice_mentions_do_not_create_topic_children
test_topic_child_copies_one_source_child_and_preserves_original_owner_and_refs
test_one_source_child_can_bind_multiple_topics_without_text_hash_dedup
test_topic_without_eligible_evidence_emits_shortfall_not_synthetic_content
test_topic_page_story_rows_share_exact_public_child_contract
```

Run:

```powershell
python -m pytest tests/test_huiji_topic_projection.py -q
```

Expected RED: module/catalog absent.

### Step 2: Implement versioned catalog validation

Require `topic_id`, name, aliases, exact titles/headings, route constraints and controlled definition patterns. Canonicalize order and fingerprint catalog bytes. Reject duplicate IDs, ambiguous aliases within the catalog, empty selectors, and unknown fields that alter selection behavior.

### Step 3: Implement eligible evidence selection

Select only from already projected Page/Data/Story children:

- exact page/redirect title;
- exact heading;
- explicit allowed structured relation;
- controlled definition sentence in an eligible section.

Create a Topic child per source child/evidence relation. Preserve source owner and source child IDs in private `source_fields`, and preserve original crawler refs publicly. Never call LLM/VLM or aggregate sources into invented prose.

### Step 4: Run C2 focused GREEN

```powershell
python -m pytest `
  tests/test_huiji_wikitext_projection.py `
  tests/test_huiji_story_projection.py `
  tests/test_huiji_topic_projection.py `
  tests/test_huiji_models.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_huiji_corpus_projection_fidelity.py `
  -q
```

Expected: Page, Story and Topic use the same frozen public contract; legacy content/owner fidelity is unchanged.

**Failure manifestation:** evidence shortfall is local exclusion; conflicting catalog identity is a blocker; scattered mentions never dominate Topic output.

**Commit boundary:**

```text
feat(rag): project source-backed Page Story and Topic children
```

Stop for D review before Task 5.

---

## 9. Task 5 — Bind Wikitext Media To Exact Children And Resolve Exact Resources

**Corresponding P0:** `MEDIA-P0-01..09`, `RESOURCE-P0-01..06`, `DOWNLOAD-P0-05`, `FIDELITY-P0-04`, `ERROR-P0-01..05`, `TEST-P0-05`.

**Files:**

- Modify `src/huiji_rag/build/wikitext_projection.py`.
- Modify `src/huiji_rag/build/projection.py`.
- Modify `src/huiji_rag/build/media_v3.py`.
- Modify `tests/test_huiji_wikitext_projection.py`.
- Modify `tests/test_huiji_media_v3_builder.py`.
- Modify `tests/test_huiji_media_v3_contract.py`.

### Step 1: Write RED Wikitext binding tests

```text
test_wikitext_relation_token_is_stable_without_revision_caption_or_time
test_file_and_gallery_bind_exact_page_section_chunk_and_heading_path
test_same_filename_in_same_section_increments_occurrence_only
test_same_resource_across_pages_sections_and_topics_preserves_all_bindings
test_display_title_precedence_records_explicit_adjacent_heading_page_filename_source
test_media_source_ref_keeps_filename_caption_link_offsets_title_source_and_context_hash
test_context_uses_at_most_200_visible_chars_each_side_without_crossing_heading
test_media_role_uses_location_options_and_caption_not_filename_prefix_only
test_small_navigation_icon_is_decorative_exclusion_with_fingerprinted_threshold
```

### Step 2: Write RED exact resource tests

```text
test_wikitext_filename_normalizes_prefix_url_nfkc_space_underscore_and_extension_case
test_wikitext_resolver_matches_full_filename_and_never_stem
test_identical_exact_filename_sha1_size_rows_merge_source_evidence
test_exact_filename_with_different_sha1_or_size_blocks_binding
test_legacy_data_intents_keep_separate_stem_resolver
test_manifest_missing_and_local_not_downloaded_are_distinct
test_local_present_requires_containment_sha1_sha256_and_size
test_media_v3_rejects_unknown_child_and_invalid_source_ref_closure
```

Run:

```powershell
python -m pytest `
  tests/test_huiji_wikitext_projection.py -k "media or file or gallery" `
  tests/test_huiji_media_v3_builder.py -k "exact or shared or missing or conflict" `
  -q
```

Expected RED: no Wikitext intents; catalog has stem-only lookup; not-downloaded is currently reported as local-file invalid rather than a distinct planning status.

### Step 3: Extend internal media intent without changing frozen runtime fields

Add internal-only exact filename, original filename, title source, adjacent context digest, options, and resolver mode as needed. Serialize traceability through existing `source_refs`/diagnostic inventory, not new public Media V3 fields.

### Step 4: Add exact Wikitext catalog path

Maintain:

```text
by_exact_normalized_filename
by_legacy_stem
```

Wikitext uses only the first. Structured Data continues current verified stem behavior. Exact duplicates with same content merge refs; content conflicts block only affected binding and candidate readiness.

### Step 5: Preserve intent/binding multiplicity

Create one intent per valid occurrence. Resource deduplication may share `resource_id`, but binding identity/count remains a multiset. Unavailable local files do not emit runtime rows; they emit exact unresolved/planning evidence.

### Step 6: Run focused GREEN and Media V3 regression

```powershell
python -m pytest `
  tests/test_huiji_wikitext_projection.py `
  tests/test_huiji_media_v3_builder.py `
  tests/test_huiji_media_v3_contract.py `
  tests/test_huiji_corpus_fidelity.py `
  -q
```

**Failure manifestation:** missing manifest is local exclusion; not-downloaded is diagnostic-only; filename content conflict is blocker; local hash/containment mismatch cannot produce runtime binding; valid multibindings remain.

**Commit boundary:**

```text
feat(rag): bind Wikitext media to exact sections and resources
```

Stop for D review before Task 6.

---

## 10. Task 6 — Emit Referenced-Media Allowlist, Capacity Forecast, And Approval-Bound Download Support

**Corresponding P0:** `SCOPE-P0-02`, `DECISION-P0-03`, `CAPACITY-P0-01..15`, `DOWNLOAD-P0-01..07`, `TEST-P0-06`.

**Files:**

- Create `src/huiji_rag/build/media_download_plan.py`.
- Modify `src/huiji_rag/build/contracts.py`.
- Modify `src/huijiwiki/resource_downloader.py` only for exact allowlist/staging-state consumption.
- Create `tests/test_huiji_media_download_plan.py`.
- Modify `tests/test_huiji_resource_downloader.py`.

### Step 1: Write RED plan/allowlist tests

```text
test_allowlist_contains_only_referenced_eligible_exact_resources
test_capacity_totals_separate_declared_local_missing_minio_new_and_peak_bytes
test_local_margin_uses_max_2gib_or_twenty_percent
test_cloud_margin_uses_max_1gib_or_twenty_percent
test_unknown_cloud_or_other_storage_growth_is_not_zero_or_sufficient
test_exact_existing_minio_key_sha_size_reuses_without_new_byte_charge
test_selection_policy_and_allowlist_sha_are_deterministic
test_p0_selects_at_most_one_representative_per_main_page_activity_or_chapter
test_story_background_cg_avatar_and_decorative_icons_are_not_p0_physical_objects
```

### Step 2: Write RED hard-budget and overflow tests

```text
test_p0_over_256_mib_returns_capacity_blocked_without_random_truncation
test_p1_cumulative_over_2_gib_returns_capacity_blocked_against_frozen_baseline
test_projected_or_actual_free_below_12_gib_never_accepts_or_readies
test_capacity_blocked_partitions_selected_overflow_and_not_eligible
test_overflow_forecast_reports_resource_binding_groups_reuse_and_peak
test_overflow_forecast_computes_projected_free_shortfall_minimum_and_5gib_roundup
test_zero_shortfall_recommends_budget_approval_not_disk_expansion
test_partial_overflow_creates_new_allowlist_and_sha_instead_of_appending
test_abandon_partial_expand_and_defer_are_no_write_until_new_approval
test_budget_excluded_binding_metadata_is_preserved
```

Run:

```powershell
python -m pytest tests/test_huiji_media_download_plan.py -q
```

Expected RED: module/contracts absent.

### Step 3: Implement deterministic planning artifacts

Produce canonical:

```text
referenced_media_plan.v1.json
referenced_media_allowlist.v1.jsonl
media_capacity_report.v1.json
```

Calculate every field required by Spec Section 16. Deduplicate physical bytes by object identity while retaining binding IDs. Pin:

- source inventory fingerprint;
- projection fingerprint;
- phase;
- selection policy SHA;
- D-provided `media_budget_baseline_inventory_sha256`;
- exact allowlist SHA.

Use hard constants:

```text
P0_MEDIA_NEW_BYTES_MAX = 268435456
P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX = 2147483648
MIN_FREE_AFTER_COMMIT_BYTES = 12884901888
```

P1 is calculation/test support only. Executing P1 requires a new approved Plan.

### Step 4: Implement read-only overflow forecast and approval state

When `capacity_blocked`, continue only read-only calculation of:

```text
selected_within_budget
phase_overflow
not_eligible
overflow_media_new_bytes
projected_free_if_overflow_committed_bytes
free_space_shortfall_bytes
minimum_disk_expansion_bytes
recommended_disk_expansion_bytes
```

Then stop and wait for explicit user choice among:

1. `abandon_overflow`;
2. `approve_partial_overflow` with a newly generated smaller allowlist/SHA;
3. `expand_storage_then_replan`;
4. `defer_decision`.

The user request calls the three active alternatives “放弃、缩小 allowlist、扩容后重规划”; defer remains a valid no-change state. Never auto-select, delete existing production data, expand the budget, or append to an old allowlist.

### Step 5: Add allowlist-only downloader support without executing it

The downloader must:

- require an exact allowlist path and SHA;
- reject jobs not in the allowlist;
- retain HTTPS host checks;
- write only under a separate staging root;
- use independent staging receipt/state, never canonical `crawl_state.sqlite`;
- use `.part`, size/SHA-1 validation and atomic replace;
- require explicit approval metadata before `run()`.

Unit tests use fake responses only. Do not execute network.

### Step 6: Run focused GREEN

```powershell
python -m pytest `
  tests/test_huiji_media_download_plan.py `
  tests/test_huiji_resource_downloader.py `
  -q
```

**Failure manifestation:** over-budget or below-margin returns `capacity_blocked`; unknown capacity returns `unknown_capacity`; no approval returns a no-write refusal; downloader rejects allowlist drift and canonical state DB paths.

**Commit boundary:**

```text
feat(rag): report referenced media capacity and download allowlist
```

Stop for D review. This commit adds capability/tests only; it performs no media download.

---

## 11. Task 7 — Integrate Stages Into The Single Offline Builder And Artifact/Fidelity Gates

**Corresponding P0:** `ARCH-P0-03..04`, `BUILD-P0-01..06`, `DOWNLOAD-P0-05..07`, `FIDELITY-P0-01..06`, `CONTRACT-P0-06..07`, `TEST-P0-07`.

**Files:**

- Modify `src/huiji_rag/build/orchestrator.py`.
- Modify `src/huiji_rag/build/contracts.py`.
- Modify `src/huiji_rag/build/projection.py`.
- Modify `src/huiji_rag/build/media_v3.py`.
- Modify `tests/test_huiji_corpus_builder.py`.
- Modify `tests/test_huiji_corpus_builder_contracts.py`.
- Modify `tests/test_huiji_corpus_artifacts.py`.
- Modify `tests/test_huiji_corpus_fidelity.py`.

### Step 1: Write RED fixed-stage and offline tests

```text
test_builder_consumes_pages_wikitext_data_and_resources_semantically
test_builder_no_longer_uses_list_read_jsonl_for_large_sources
test_builder_stage_order_is_recovery_join_page_story_topic_media_capacity_fidelity
test_new_stage_code_and_config_enter_fingerprints
test_diagnostics_include_every_frozen_projection_reason_family
test_unrecovered_source_is_blocked
test_projection_with_not_downloaded_media_is_diagnostic_only
test_identity_or_resource_conflict_is_blocked
test_ready_for_embedding_requires_text_media_fidelity_and_no_protected_drift
test_builder_writes_only_create_new_isolated_roots
test_builder_never_imports_or_calls_network_minio_mysql_milvus_or_embedding_writers
```

Run:

```powershell
python -m pytest tests/test_huiji_corpus_builder.py tests/test_huiji_corpus_builder_contracts.py -q
```

Expected RED: current builder list-loads Data/resources, skips pages/Wikitext semantic stages, and has no `diagnostic_only` path for planned unavailable media.

### Step 2: Compose one `CorpusProjection`

Keep the existing character/Data projector as one stage. Merge new Page/Story/Topic parents, children, exclusions, record links and media intents deterministically. Validate globally unique parent/child/source identities and closure before artifact writing.

### Step 3: Integrate state and diagnostics

State rules:

```text
recovery invalid                         -> blocked
projection valid, referenced media absent -> diagnostic_only
identity/resource conflict              -> blocked
all text/media/fidelity gates pass       -> ready_for_embedding handoff only
```

Write sanitized diagnostics for page/revision conflicts, missing revisions, redirects, unsupported Wikitext, Story names/fallbacks, Topic shortfalls, media exclusions, resource missing/not-downloaded/conflicts, invalid Data wrapper, capacity and stream metrics.

### Step 4: Extend fingerprints

Add all C stage files, topic catalog bytes, parser config, decorative threshold, selection policy and capacity constants to code/config fingerprints. Do not modify B’s sparse analyzer or BM25 payload/provenance hash implementation.

### Step 5: Extend fidelity without recategorizing existing rows

- Existing character/item/psychube/Voice/Media rows remain exact/rekeyed/corrected/source-removed with zero unexplained loss.
- New fields are reported as schema enrichment separate from content/owner change.
- New Page/Story/Topic rows are `new_source_record`.
- Media resource dedup never reduces binding multiset.
- Repeated fixture builds produce equal IDs, ordering, content hashes, source refs and projection fingerprints.

### Step 6: Run focused integration GREEN

```powershell
python -m pytest `
  tests/test_huiji_corpus_builder_contracts.py `
  tests/test_huiji_corpus_builder.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_fidelity.py `
  tests/test_huiji_media_v3_builder.py `
  -q
```

**Failure manifestation:** expected source/semantic failures create immutable blocked evidence; unexpected exceptions propagate; partial candidate roots are never repaired/reused; no handoff is created for blocked/diagnostic-only state.

**Commit:** held for Task 8’s diagnostic/fidelity commit.

---

## 12. Task 8 — Run Restored-Snapshot Streaming Diagnostics Without Download Or Full Candidate Activation

**Corresponding P0:** `RECOVERY-P0-01..06`, `STREAM-P0-01..05`, `REAL-P0-01..08`, `FIDELITY-P0-01..06`, `CAPACITY-P0-01..15`, `DOWNLOAD-P0-05..07`, `AGENT-P0-05`.

**Files:** only new isolated diagnostic output under an ignored or D-approved run directory; no raw/processed/production modification. Any committed fixture expectation must remain dynamic and must not hardcode snapshot counts.

### Gate 8.0: Require D recovery closure

Before any full-source diagnostic pass, verify:

- manifest, audit and apply receipt identities;
- canonical `data_pages.jsonl` and `crawl_state.sqlite` size/SHA;
- read-only SQLite quick check;
- all four JSONL inventory identities;
- `invalid_payload_rows == 1`.

If any check fails, stop with `source_recovery_invalid`. Do not restore or recrawl.

### Step 1: Capture protected pre-state read-only evidence

Hash/stat only the approved active artifact and local raw identities needed for drift checks. If MinIO/cloud free evidence is unavailable, mark `unknown_capacity`; do not query or write production services beyond D-approved read-only metadata checks.

### Step 2: Run streaming semantic diagnostics only

Invoke the orchestrator’s read-only diagnostic entry point, not a media downloader, embedding writer, Milvus writer, MySQL importer, active-pointer writer, or formal activation path.

The run must report:

- four source file hashes, sizes and row counts;
- per-stage read/accepted/excluded counts, elapsed time and RSS/unavailable;
- page/revision conflict and missing-latest counts;
- Page/Story/Topic parent/child counts;
- media intent, unique exact resource, missing manifest, not-downloaded and conflict counts;
- capacity/overflow report;
- deterministic projection fingerprint.

### Step 3: Close the invalid-wrapper gate

Assert all of the following from the restored snapshot:

```text
manifest invalid_payload_rows == 1
semantic diagnostics invalid_data_wrapper == 1
excluded artifact/evidence invalid_data_wrapper == 1
projected parent/child/media rows from that wrapper == 0
neighbor valid rows continue
```

Inspect only wrapper metadata and hashes. Do not print or parse invalid `content`.

Only after these assertions pass may C report `REC-P0-06` projection exclusion closure.

### Step 4: Validate “今夜星光灿烂” without inventing a revision

Prove separately:

1. page index has the natural title;
2. related Wikitext has exact visible link label and Banner reference;
3. manifest has Banner metadata with `not_downloaded`.

Verify related Page child `search_text`, Banner binding source page/heading/title-source/resource identity, and allowlist/capacity inclusion. Explicitly report that the natural page itself lacks a matched latest Wikitext revision if that remains true.

### Step 5: Dynamically sample Story strata

Select samples by computed strata, not hardcoded IDs:

- direct natural name;
- Episode/Chapter-only name;
- raw-ID fallback;
- name conflict if present;
- short/medium/long content quantiles.

For each, trace Data wrapper → relation evidence → Story owner/child → source refs. Missing conflict strata are reported as zero discovered, not fabricated.

### Step 6: Validate “暴雨”

Require eligible catalog-backed real evidence or explicit `topic_evidence_shortfall`. Report source type and original owner. Verify scattered character mentions do not constitute all Topic children.

### Step 7: Validate capacity read-only

Report actual referenced unique resources, missing local bytes, MinIO new bytes when a reliable D-provided metadata inventory exists, phase budget, projected free, unknown non-media growth handling, and 12 GiB gate.

No download approval exists in this plan, so stop at diagnostics/allowlist/capacity. Candidate state remains `diagnostic_only/blocked`; do not claim `ready_for_embedding`.

If `capacity_blocked`:

- output real `phase_overflow` resource/binding counts and deduplicated bytes;
- output projected free if all overflow were committed;
- output 12 GiB shortfall, minimum expansion and rounded 5 GiB recommendation;
- present `abandon_overflow`, `approve_partial_overflow`, and `expand_storage_then_replan` plus defer;
- stop and wait for new user approval.

### Step 8: Confirm protected post-state

Rehash/re-stat the same protected identities. Require no raw, active artifact, MinIO, MySQL, Milvus, Docker, baseline or pointer drift attributable to C.

**Failure manifestation:** recovery mismatch blocks the run; identity/resource conflicts block candidate status; not-downloaded media remains diagnostic; unknown cloud evidence cannot become sufficient; any protected drift stops acceptance.

**Commit boundary:**

```text
test(rag): verify projection fidelity and real snapshot diagnostics
```

The commit may contain implementation/test adjustments and committed small fixture/expectation changes only. It must not contain real raw data, receipts, diagnostic runs, capacity reports with sensitive paths, or generated candidate artifacts.

Stop for D review before final regression.

---

## 13. Task 9 — Run Focused And Regression Suites, Verify Ownership, And Hand Off

**Corresponding P0:** `TEST-P0-01..07`, `FIDELITY-P0-01..06`, `PHASE-P0-01`, `OWN-P0-01..03`, `AGENT-P0-01..05`.

### Step 1: Run all new focused tests

```powershell
python -m pytest `
  tests/test_huiji_page_sources.py `
  tests/test_huiji_wikitext_projection.py `
  tests/test_huiji_story_projection.py `
  tests/test_huiji_topic_projection.py `
  tests/test_huiji_media_download_plan.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_huiji_corpus_projection_fidelity.py `
  tests/test_huiji_corpus_builder.py `
  tests/test_huiji_corpus_builder_contracts.py `
  tests/test_huiji_corpus_source_inventory.py `
  tests/test_huiji_media_v3_builder.py `
  tests/test_huiji_media_v3_contract.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_fidelity.py `
  tests/test_huiji_resource_downloader.py `
  tests/test_huiji_models.py `
  -q
```

Expected: PASS.

### Step 2: Run existing projection/media/Voice regressions

```powershell
python -m pytest `
  tests/test_huiji_wiki_crawler_projection.py `
  tests/test_huiji_wiki_crawler_only_policy.py `
  tests/test_huiji_media_v3_minio_gate.py `
  tests/test_evb_voice_binding.py `
  tests/test_evb_builder.py `
  tests/test_evb_diagnostics.py `
  tests/test_evb_artifacts.py `
  tests/test_huiji_provenance.py `
  -q
```

Expected: PASS. Do not modify Wiki, Planner, Retriever, analyzer, or B-owned schema to force a pass.

### Step 3: Verify deterministic artifact closure

Build the small four-file fixture twice under two new temporary roots and compare semantic bytes/fingerprints for:

```text
parent blocks
child blocks
excluded evidence
media intents/bindings
referenced media plan/allowlist/capacity
projection fingerprint
```

Require parent-child-media/source-ref closure and equal ordered IDs.

### Step 4: Run static ownership checks

```powershell
git diff --check
git status --short
git diff --name-only
git diff -- src/rag/query_plan.py src/rag/request_plan.py src/rag/route_policy.py src/rag/retriever.py src/rag/chain.py src/rag/sparse.py src/rag/chinese_analyzer.py
```

Expected:

- no whitespace errors;
- only Thread C allowlisted files changed;
- forbidden-file diff is empty;
- no raw data, processed artifact, receipt, candidate, capacity evidence, active pointer or A/B file is tracked.

### Step 5: Prepare D handoff

Report:

- five small commits and their SHAs;
- P0 traceability status;
- focused/regression commands and results;
- restored-snapshot diagnostic identity and invalid-wrapper closure;
- actual capacity state and whether cloud evidence was reliable;
- explicit confirmation of zero downloads/uploads/production writes/activation;
- any remaining D integration work for B → C semantic hash.

**Failure manifestation:** any failed focused test, unexplained fidelity loss, closure break, nondeterminism, capacity violation, protected drift, or out-of-scope diff stops handoff. Do not amend earlier reviewed commits to hide failures; add a small corrective commit after D approval.

---

## 14. Commit And Review Sequence

The implementation sequence is serial and each phase requires D review before the next:

```text
1. feat(rag): join crawler pages revisions and Data relations
2. feat(rag): project source-backed Page Story and Topic children
3. feat(rag): bind Wikitext media to exact sections and resources
4. feat(rag): report referenced media capacity and download allowlist
5. test(rag): verify projection fidelity and real snapshot diagnostics
```

Each commit includes its RED tests, minimal implementation, GREEN focused tests, and no unrelated cleanup. If a phase needs a corrective commit after review, keep it narrow and record the superseding SHA; do not squash without D instruction.

---

## 15. Capacity And External-Operation Stop Rules

1. P0 selected physical new media must be at most 256 MiB.
2. P1, only under a future approved Plan, is cumulative against the frozen pre-P0 MinIO baseline and at most 2 GiB.
3. Before every approved storage commit, projected server free space must remain at least 12 GiB after all known media, artifact, BM25, Milvus/index, MySQL, candidate/rollback/receipt and Docker release growth.
4. After every approved storage commit, D must re-read actual free space; below 12 GiB cannot be accepted/ready.
5. Unknown capacity inputs use a conservative recorded upper bound or `unknown_capacity`, never zero.
6. `capacity_blocked` first produces the remaining-media increment forecast and then waits for approval among abandoning overflow, shrinking to a new explicit allowlist, or expanding storage and replanning; defer is the no-change option.
7. No task in this plan executes a real media download, MinIO upload, MySQL/Milvus write, full production build, formal candidate activation, or active pointer switch.

---

## 16. Definition Of P0 Completion

Thread C may report implementation `completed_pending_review` only when:

1. D recovery receipts and canonical identities are consumed read-only.
2. The restored snapshot’s only `json_valid=false` wrapper appears exactly once in excluded evidence, its invalid `content` is never parsed/projected, and `REC-P0-06` is not closed earlier.
3. All four crawler files are semantically consumed with streaming/bounded memory behavior.
4. Exact page/revision join, redirect, conflict and namespace rules pass.
5. Page sections/chunks, Story names/content and Topic evidence satisfy frozen identities and source refs.
6. Public Child fields are complete and existing character semantics are unchanged except explicit schema enrichment.
7. Wikitext image context binds exact page/section children, exact filenames resolve without stem fuzziness, and resource multibinding is preserved.
8. Missing, not-downloaded and conflicting resources are distinct.
9. Allowlist/capacity output is deterministic, within P0 budget or hard-blocked with full overflow forecast.
10. Builder remains offline, isolated and non-activating.
11. Existing character/item/psychube, Voice, Media V3, artifact, provenance and fidelity regressions pass with zero unexplained loss.
12. “今夜星光灿烂”, “暴雨”, and dynamic Story strata are validated against real restored evidence without invented facts.
13. No A/B unmerged code or forbidden state is read/modified.
14. D accepts files, tests, data identity, capacity evidence and all five commits.

If media download approval is absent, parser/projection/binding intent/allowlist/capacity/diagnostic P0 can complete, but the real media candidate remains `diagnostic_only/blocked` and must not be called `ready_for_embedding`.
