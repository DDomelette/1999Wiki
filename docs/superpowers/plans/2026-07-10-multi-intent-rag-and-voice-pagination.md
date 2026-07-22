# Multi-Intent RAG and Voice Pagination P0 Implementation Plan

> **For Codex:** REQUIRED SUB-SKILLS: use `superpowers:test-driven-development` for every behavior change, `superpowers:systematic-debugging` for unexpected failures, and `superpowers:verification-before-completion` before claiming any gate passes.

Date: 2026-07-10  
Status: ready for review; implementation not started  
Design source: `docs/superpowers/specs/2026-07-10-multi-intent-rag-and-voice-pagination-design.md`  
Review rule: `docs/specs-and-plans-review-guide.md`

**Goal:** Restore the complete multi-intent character RAG path and add server-side voice-line pagination without rebuilding artifacts, re-vectorizing data, or changing the active Milvus collection.

**Architecture:** Keep `QueryPlan.intent` as the primary compatibility field and derive one ordered `requested_intents` tuple from it plus `secondary_intents`. Compose existing packet policies for candidate recall, calculate a bounded candidate K from text-source quotas, and use an intent-aware allocator for the final context. Derive media types from the same intent bundle. Group playable voice media by voice child, return only the first page through Ask/SSE, and serve later pages from the already loaded media registry through opaque cursors.

**Tech stack:** Python 3.11, dataclasses, FastAPI/Pydantic, existing BM25/Milvus/RRF/reranker stack, React 18, TypeScript, Vitest, Testing Library.

## 1. Execution Rules and Boundaries

This plan contains P0 work only. Skin or voice-pack inference, skin filtering, prefetching, remembered language preferences, intent-specific Dense subqueries, artifact rebuilds, vectorization, and data migrations are outside this execution.

The repository was reconstructed after file loss and Git history is not an authority for this task. Do not use Git history, checkout, reset, or revert as recovery evidence. Before editing any listed file, reopen its current contents and work with changes from the other RAG task instead of overwriting them.

Hard read/write boundary:

- Allowed writes: source files, tests, this plan's evaluator, and generated reports under `eval/`.
- Read only: `data/processed/huiji/**`, Milvus, MinIO, MySQL, and existing build manifests.
- Forbidden commands: `scripts/build_index.py`, any embedding/vectorization command, any artifact builder, collection drop/create/insert/upsert/delete, MinIO write/delete, and database migration commands.
- The active text collection must remain `text_child_bge_m3_v3` with unchanged schema and row count across this implementation window.
- No expected role name, role ID, skill count, voice-line count, language count, or media count may be written into production code, tests, fixtures, or evaluation assertions.

Use this interpreter for backend commands:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe
```

Use `frontend/react-app` as the working directory for frontend commands.

## 2. P0 Hard-Gate Matrix

| Gate | Spec coverage | Required evidence | Failure means |
|---|---|---|---|
| `P0-GATE-00` | read/write boundary | pre/post Milvus snapshots match; no builder or vectorization command was run | implementation is unsafe |
| `P0-GATE-01` | `PLAN-P0-01..07` | QueryPlan tests pass for LLM and all fallback paths | Stage 0 is still single-intent |
| `P0-GATE-02` | `RETR-P0-01..05` | policy and candidate-K tests pass | downstream still ignores intents or media drives K |
| `P0-GATE-03` | `RETR-P0-06..12` | allocator/retriever tests pass with coverage diagnostics | final context can still erase an intent |
| `P0-GATE-04` | `MEDIA-P0-01..12` | registry, grouping, pagination, and cursor tests pass | voice media is incomplete, duplicated, or unbounded |
| `P0-GATE-05` | `API-P0-01..04` | Ask/SSE/page API tests pass, including 400/409 and no retrieval on next page | transport contract is incomplete |
| `P0-GATE-06` | `CHAT-P0-01..07` | frontend API/component/store tests and TypeScript build pass | the client cannot safely consume pages |
| `P0-GATE-07` | `EVAL-P0-01..11` | all focused and existing single-intent suites pass | regression coverage is incomplete |
| `P0-GATE-08` | `GATE-P0-01..09` | deterministic real-data report plus real Ask/SSE/page/UI evidence passes | mock or single-role evidence is insufficient |

No task below is complete when only its implementation exists. Its test command and acceptance assertions must also pass.

## 3. Task P0-0: Add Read-Only Guard and Dynamic Artifact Inventory

**Files:**

- Create: `scripts/verify_multi_intent_voice.py`
- Create: `tests/test_multi_intent_voice_eval.py`
- Read only: `src/huiji_rag/io.py`
- Read only: `data/processed/huiji/dev/child_blocks.jsonl`
- Read only: `data/processed/huiji/dev/media_assets.jsonl`

### Step 1: Write failing inventory and collection-snapshot tests

Add tests for these public functions:

```python
@dataclass(frozen=True)
class CharacterInventory:
    entity_id: str
    entity_name: str
    skill_child_ids: tuple[str, ...]
    voice_text_child_ids: tuple[str, ...]
    playable_voice_line_ids: tuple[str, ...]
    playable_media_ids: tuple[str, ...]
    languages: tuple[str, ...]

build_character_inventory(child_rows, media_rows) -> list[CharacterInventory]
select_stratified_characters(inventory, limit: int = 8) -> list[CharacterInventory]
capture_collection_snapshot(cfg) -> dict[str, object]
compare_collection_snapshots(before, after) -> list[str]
```

The fixtures must use synthetic IDs and varying counts. Assert that inventory includes only HTTP, available voice variants; text-only voice children remain in `voice_text_child_ids` but not `playable_voice_line_ids`; sampling is deterministic; low/median/high playable-line strata are selected; count/language variation is included when available; and snapshot comparison reports collection name, schema, or row-count changes.

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_multi_intent_voice_eval.py -q
```

Expected: FAIL because the evaluator module does not exist.

### Step 2: Implement only the read-only inventory and snapshot layer

Implement JSONL loading through `build_paths()` and `iter_jsonl()`. Group by artifact `entity_id`; derive all expected sets from current rows. Sort IDs and sample ties deterministically by `entity_id`. Select `min(8, eligible_count)` from entities that have skill text, voice text, and playable voice media. Add one anomaly sample when the current artifacts contain missing voice media or a requested section, without removing the required eligible strata.

`capture_collection_snapshot()` may call only read APIs for collection metadata, schema, and row count. The CLI must support:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe scripts/verify_multi_intent_voice.py inventory --output eval/multi_intent_voice_inventory.json
D:\Anaconda32024\envs\LangChain\python.exe scripts/verify_multi_intent_voice.py snapshot --output eval/multi_intent_voice_collection_before.json
```

The inventory report must list sampled entity IDs/names and dynamic values `S`, `T`, `V`, `M`, and languages. It must not contain fixed expected counts in code.

### Step 3: Verify the guard

Run the focused test and both CLI commands. Confirm the snapshot names `text_child_bge_m3_v3` and contains no mutation result. Preserve `eval/multi_intent_voice_collection_before.json` for Task P0-8.

## 4. Task P0-1: Make Stage 0 Produce One Ordered Intent Bundle

**Files:**

- Modify: `src/rag/query_plan.py`
- Modify: `tests/test_query_plan.py`

### Step 1: Write failing QueryPlan contract tests

Add table-driven tests for:

- `技能和语音` -> primary `skill`, secondary `("voice",)`.
- `单品和图片` -> primary `item`, secondary `("media",)`.
- `文化、技能及语音` -> primary `culture`, secondary `("skill", "voice")`.
- repeated keywords -> ordered unique intents.
- a generic discourse verb such as `介绍一下` plus specific section terms -> discard generic `intro` from the bundle.
- an LLM payload returning only `voice` for an explicit `skill + voice` query -> retain both explicit intents in query order.
- no LLM, timeout, malformed JSON, invalid schema, and API error -> the same intent tuple as the LLM path.
- a single-intent question -> no invented secondary intent.

Test these public helpers directly:

```python
extract_explicit_character_intents(query: str) -> tuple[str, ...]
requested_intents(plan: QueryPlan) -> tuple[str, ...]
```

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_query_plan.py -q
```

Expected: FAIL because explicit queries are collapsed by `_strong_intent_from_query()` and fallback clears `secondary_intents`.

### Step 2: Implement ordered extraction and merge

Replace the single strong-intent override with an extractor that records the first character offset for every recognized P0 section intent and sorts by `(offset, stable_pattern_order)`. When any specific section intent exists, treat `介绍/简介/概览` as discourse framing and omit `intro`. Keep `intro` for a genuinely generic character-introduction query.

Normalize and merge intents in this order:

1. explicit intents from the original query;
2. LLM primary intent when not already present;
3. LLM secondary intents in payload order.

When explicit intents exist, the first explicit intent is primary. Otherwise retain the LLM/fallback primary. Store the remaining unique valid values in `secondary_intents`. `requested_intents(plan)` must be the sole downstream constructor and return an ordered unique tuple from `(plan.intent, *plan.secondary_intents)`.

Keep scalar `media_intent` for compatibility. Do not turn it into the authoritative media-type set.

### Step 3: Verify QueryPlan regressions

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_query_plan.py tests/test_entity_lexicon.py -q
```

Acceptance: all planning-status diagnostics remain unchanged, all multi-intent cases have identical LLM/fallback bundles, and no role-specific branch exists.

## 5. Task P0-2: Compose Packet Policies and Calculate Bounded Candidate K

**Files:**

- Modify: `src/rag/packet_policy.py`
- Create: `src/rag/retrieval_budget.py`
- Modify: `config/config.py`
- Modify: `config/settings.yaml`
- Create: `tests/test_retrieval_budget.py`
- Modify: `tests/test_config.py`

### Step 1: Write failing policy and candidate-budget tests

Define the expected interfaces in tests:

```python
@dataclass(frozen=True)
class IntentPolicyBundle:
    requested_intents: tuple[str, ...]
    policies: tuple[PacketPolicy, ...]
    sections: tuple[str, ...]
    media_types: tuple[str, ...]
    context_budget_chars: int

compose_packet_policies(entity_type, intents) -> IntentPolicyBundle
calculate_required_source_count(bundle, exact_rows_by_intent, voice_page_size) -> int
calculate_candidate_k(configured_k, required_source_count, oversample, hard_max) -> int
```

Assert:

- all requested intents are represented once and sections/media types are ordered unions;
- `skill` uses `all_available` and its required count follows the available exact skill rows;
- `voice` uses a fixed target capped by configured voice page size and available text rows;
- other P0 section intents require at least one available exact source without assuming section counts;
- `candidate_k = min(100, max(configured_k, 4 * required_source_count))` with defaults;
- changing playable media count does not change required source count or candidate K;
- config defaults are `candidate_oversample=4`, `candidate_k_max=100`, `voice_page_size=8`, and `voice_page_size_max=20`.

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_retrieval_budget.py tests/test_config.py -q
```

Expected: FAIL because policy composition and budget configuration do not exist.

### Step 2: Add explicit coverage metadata and composition

Extend `PacketPolicy` with backward-compatible defaults:

```python
coverage_mode: str = "at_least_one"
source_target: int = 1
```

Set `skill` to `coverage_mode="all_available"`; set `voice` to `coverage_mode="fixed"`, `source_target=8`. Keep current section/output/media behavior for every single-intent policy.

`compose_packet_policies()` must call `get_packet_policy()` once per requested intent, preserve intent order, deduplicate sections/media types, and produce a composite expansion policy for `expand_ranked_children()`. Media types are the union of each policy's `auto_media_types` and `intent_media_types`; scalar `media_intent` is not an intersection filter.

### Step 3: Add retrieval budget configuration

Add the four numeric fields to `RetrievalCfg`, load them from YAML with the defaults above, and clamp voice page size at use sites to `1..voice_page_size_max`. Keep `rag.top_k=20` as the global final-source maximum; do not create a second conflicting max-sources setting.

### Step 4: Verify policy/config behavior

Run the focused tests. Also run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_config.py tests/test_query_plan.py -q
```

Acceptance: policy composition is generic across all P0 character section intents and no media count enters candidate-K calculation.

## 6. Task P0-3: Allocate Final Sources Per Intent and Integrate the Retriever

**Files:**

- Modify: `src/rag/retrieval_budget.py`
- Modify: `src/rag/retriever.py`
- Modify: `src/rag/layered_expansion.py`
- Modify: `tests/test_retrieval_budget.py`
- Modify: `tests/test_retriever.py`
- Modify: `tests/test_hybrid_retriever.py`

### Step 1: Write failing allocator tests

Add these data contracts:

```python
@dataclass(frozen=True)
class IntentCoverage:
    intent: str
    available: int
    target: int
    retained: int
    shortfall: int

@dataclass(frozen=True)
class AllocationResult:
    sources: list[dict[str, object]]
    omitted_rows: list[dict[str, object]]
    coverage: tuple[IntentCoverage, ...]
    chars_used: int

def allocate_sources(
    ranked_rows,
    exact_rows_by_intent,
    bundle,
    *,
    max_sources,
    context_budget_chars,
    voice_page_size,
) -> AllocationResult
```

Tests must prove:

- rows deduplicate by `child_id` while preserving all `matched_intents`;
- the allocator first reserves one available row per requested intent, then completes each target, then fills spare slots by fused score;
- all available skills survive when skill plus other minimum targets fit source and character budgets;
- voice text contributes at most the configured page-size count of distinct children;
- when budgets cannot satisfy all targets, every available requested intent remains represented where physically possible and `shortfall` is nonzero;
- an unavailable section reports shortfall instead of borrowing duplicate rows from another intent;
- omitted rows contain only genuinely trimmed rows;
- no final unconditional slice is applied after allocation.

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_retrieval_budget.py tests/test_retriever.py -q
```

Expected: FAIL because the retriever still uses one policy and `expanded.sources[:top_k]`.

### Step 2: Collect and tag exact candidates per intent

In `_search_huiji()`:

1. call `requested_intents(plan)` and `compose_packet_policies()`;
2. collect exact structured rows independently for each intent;
3. add/merge `matched_intents` on each row;
4. compute required source count and candidate K before BM25/Dense;
5. run shared BM25 and Dense with that candidate K;
6. run existing RRF, primary-entity filtering, and optional reranker;
7. infer `matched_intents` for shared candidates from section-policy matches;
8. expand with the composite section policy;
9. allocate final sources with the new allocator.

Use `candidate_k` for BM25 and Dense. Use `max(configured_rerank_k, candidate_k, required_source_count)` for reranker input, still bounded by the candidate pool. Do not create one Dense query per intent in this P0.

### Step 3: Replace blind final truncation and repair diagnostics

Delete the final `expanded.sources[:top_k]` behavior. Build `omitted_actions` only from `AllocationResult.omitted_rows` plus expansion rows already removed by the character budget. Suppress an omitted action for a requested intent whose target was satisfied.

Expose in `last_route_debug`:

```python
requested_intents: list[str]
candidate_k: int
required_source_count: int
intent_candidates: dict[str, int]
intent_targets: dict[str, int]
intent_retained: dict[str, int]
coverage_shortfall: dict[str, int]
chars_used: int
max_sources: int
```

Propagate `matched_intents` through `_row_to_result()` debug metadata. Never put prompts, secrets, local paths, or full document contents in route debug.

### Step 4: Verify retrieval and single-intent compatibility

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_retrieval_budget.py tests/test_retriever.py tests/test_hybrid_retriever.py tests/test_reranker.py -q
```

Acceptance: synthetic skill counts above three are retained when budgets permit; multi-intent results include every requested intent; existing single-intent ranking tests still pass.

## 7. Task P0-4: Group Voice Lines and Serve Stable Registry Pages

**Files:**

- Create: `src/assets/voice_pagination.py`
- Modify: `src/assets/huiji_registry.py`
- Modify: `tests/test_huiji_media_registry.py`
- Create: `tests/test_voice_pagination.py`

### Step 1: Write failing grouping and cursor tests

Define:

```python
@dataclass(frozen=True)
class VoiceLineGroup:
    voice_line_id: str
    title: str
    variants: tuple[dict[str, object], ...]

@dataclass(frozen=True)
class VoicePanelPage:
    type: str
    grouping: str
    entity_id: str
    lines: tuple[VoiceLineGroup, ...]
    page_size: int
    total_lines: int
    has_more: bool
    next_cursor: str | None

InvalidVoiceCursor(ValueError)
VoiceCursorBuildMismatch(ValueError)
```

Use synthetic media with unequal language sets, text-only children, duplicate formats, non-HTTP URLs, and multiple entities/parents. Assert:

- grouping key is `child_id`, not filename or language;
- only available HTTP audio variants produce playable rows;
- variant order is `zh`, `en`, `jp`, `kr`, then other language code;
- title preference is zh transcript, any transcript, stable media title;
- line order is parent, numeric voice-line suffix, then existing `sort_order`;
- page size clamps to `1..20`, defaults to 8, and final page returns null cursor;
- repeated cursor requests return byte-equivalent page data;
- cursor scope binds build version, entity, parent, and last line without path, secret, or naked offset;
- invalid cursor raises `InvalidVoiceCursor`; old build raises `VoiceCursorBuildMismatch`;
- another entity's media can never enter the page.

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_voice_pagination.py tests/test_huiji_media_registry.py -q
```

Expected: FAIL because the registry returns a flat full-parent list.

### Step 2: Implement an opaque bounded cursor store

Implement `VoiceCursorStore` as a bounded in-memory mapping with a maximum of 4096 states. A public cursor contains only a base64url wrapper with current build version plus a random token. The server-side state binds `entity_id`, `parent_id`, `last_voice_line_id`, and `page_size`; no offset or path is sent to the client. Keep reverse state-to-token mapping so the same next state yields the same token and repeated cursor calls are idempotent.

Decode order:

1. validate wrapper shape;
2. compare wrapper build version and raise build mismatch before token lookup;
3. resolve token from the bounded server store;
4. validate the resolved entity/parent/last-line state against the current voice index.

A same-build server restart may invalidate a cursor with 400; a different-build cursor must produce 409.

### Step 3: Add a media bundle interface to the registry

Add:

```python
@dataclass(frozen=True)
class MediaRetrievalBundle:
    items: tuple[dict[str, object], ...]
    panels: tuple[dict[str, object], ...]

find_bundle_for_retrieval(plan, sources, limit=8, voice_page_size=8) -> MediaRetrievalBundle
get_voice_page(cursor: str) -> dict[str, object]
```

Derive allowed media types from `requested_intents(plan)` and the composed policy union. Keep scalar `media_intent` additive for compatibility; it must never replace the union. Preserve final-source child/parent matching and entity matching.

For voice scope, build all playable groups from the matching voice parent but put only current-page variants into `bundle.items` and the structured page into `bundle.panels`. Keep non-voice items subject to the existing response limit. Remove the `VOICE_PANEL_LIMIT=1024` full-return behavior. Keep `find_for_retrieval()` as a compatibility wrapper returning only `bundle.items` for older callers/tests.

### Step 4: Verify registry behavior

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_voice_pagination.py tests/test_huiji_media_registry.py tests/test_asset_registry.py -q
```

Acceptance: the first bundle contains no full voice duplicate, all pages together equal the dynamically constructed playable sets, and missing media produces no empty player row.

## 8. Task P0-5: Wire Ask, SSE, and the Read-Only Page API

**Files:**

- Modify: `src/rag/chain.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Modify: `backend/sse.py`
- Modify: `tests/test_chain_assets.py`
- Modify: `tests/test_sse.py`

### Step 1: Write failing chain/API tests

Add tests that assert:

- Huiji `RAGChain.retrieve()` consumes `MediaRetrievalBundle`, returns first-page voice variants only, and forwards the structured voice page in `media_panels`;
- a mixed `skill + voice` result keeps both skill images and first-page voice variants;
- route metadata exposes `requested_intents` and retrieval-budget debug;
- Ask and SSE sources/done events carry the same first-page metadata;
- `GET /api/media/voice/page?cursor=<opaque>` returns typed page fields;
- malformed/unknown cursor returns 400;
- build mismatch returns 409 with a first-page reload instruction;
- a spy planner, retriever, LLM, embedding client, and vectorstore receive zero calls during page requests;
- serialized output contains no `file://`, drive-letter path, `local_relpath`, prompt, or secret.

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_chain_assets.py tests/test_sse.py -q
```

Expected: FAIL because the chain builds flat panels and the page endpoint does not exist.

### Step 2: Add typed response schemas

Add Pydantic models for `VoiceLineGroup` and `VoicePanelPage`. Replace only the voice-panel portion of `media_panels` with this typed contract; preserve video panel compatibility. Extend `RouteInfo` with optional `requested_intents` and `retrieval_debug` fields so existing clients remain valid.

### Step 3: Wire the chain without re-retrieval

When Huiji is enabled, call `find_bundle_for_retrieval()` once after final sources are allocated. Set top-level `assets/media` from `bundle.items` and `media_panels` from `bundle.panels` plus any existing video panel. Add `RAGChain.get_voice_page(cursor)` as a direct registry forwarder. It must not call `QueryPlanner.plan()`, `Retriever.search()`, `_format_context()`, the LLM, embeddings, or Milvus.

Include the same route/debug object in synchronous Ask and SSE source/done events. Do not expose the full `QueryPlan` object.

### Step 4: Add the read-only endpoint

Add:

```python
GET /api/media/voice/page?cursor=<opaque>
response_model = VoicePanelPage
```

Call `_ensure_loaded()`, obtain the existing chain, and forward the cursor. Map `InvalidVoiceCursor` to 400 and `VoiceCursorBuildMismatch` to 409. Do not add page-size or entity query parameters; those values are bound by the cursor.

### Step 5: Verify transport regressions

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_chain_assets.py tests/test_sse.py tests/test_rag_empty_recovery.py -q
```

Acceptance: first-page payload size is bounded by voice lines, subsequent pages use registry-only reads, and non-voice questions still have no voice panel.

## 9. Task P0-6: Render Line-Grouped Voice Pages in React

**Files:**

- Modify: `frontend/react-app/src/types/index.ts`
- Create: `frontend/react-app/src/api/media.ts`
- Create: `frontend/react-app/src/api/media.test.ts`
- Modify: `frontend/react-app/src/components/chat/VoicePanel.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageAssets.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageBubble.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageBubble.test.tsx`
- Modify: `frontend/react-app/src/store/chatStore.test.ts`
- Modify: `frontend/react-app/src/api/sse.test.ts`

### Step 1: Write failing API and component tests

Add TypeScript contracts matching the backend `VoiceLineGroup` and `VoicePanelPage` shapes. Test `fetchVoicePage(cursor)` for encoded query construction, successful parsing, 400 errors, and 409 reload-required errors.

Component tests must prove:

- one row renders per `voice_line_id`, not per media variant;
- only existing language controls render;
- initial variant preference is zh, en, jp, kr, then stable other-language order;
- changing language stops/reset the active audio before selecting the new URL;
- playing another line stops/reset the previous audio;
- Load More appears only for `has_more`, disables during request, appends instead of replacing, and sends exactly one request per click;
- duplicate line IDs and media IDs from repeated pages are ignored;
- a page failure preserves loaded rows and shows a local retry command;
- the panel has a fixed max-height/overflow scroll region after append;
- `MessageBubble` consumes `message.mediaPanels` and does not render compatible top-level voice media a second time.

Run:

```powershell
npm run test -- --run src/api/media.test.ts src/components/chat/MessageBubble.test.tsx src/store/chatStore.test.ts src/api/sse.test.ts
```

Expected: FAIL because `MediaPanel` is flat and `MessageBubble` ignores it.

### Step 2: Implement the typed API client

Create `fetchVoicePage(cursor, signal?)` using `GET /api/media/voice/page?cursor=${encodeURIComponent(cursor)}`. Throw a typed error carrying `status` and `reloadFirstPage=true` for 409. Do not accept entity, offset, parent, or page-size parameters.

### Step 3: Implement grouped playback and local paging state

Refactor `VoicePanel` to accept a `VoicePanelPage`. Maintain loaded lines, selected language per line, loading/error state, and one `HTMLAudioElement` ref. Deduplicate lines by `voice_line_id` and variants by `media_id`. Stop/reset the current audio before language change, next-page request, retry, or another playback.

Keep the current compact message layout: use one bounded scroll area and do not grow the message body without limit. The language selector is a compact segmented control. Playback is one familiar play/pause control with an accessible label; do not add feature-explanation text to the interface.

### Step 4: Consume `mediaPanels` exactly once

In `MessageBubble`, render structured voice panels from `message.mediaPanels`. When one exists, filter voice items out of the compatibility `media/assets` list before passing it to `MessageAssets`; continue rendering images and video normally. Keep `MessageAssets` legacy voice rendering only for responses that do not contain a structured voice panel.

### Step 5: Verify frontend P0

Run:

```powershell
npm run test -- --run src/api/media.test.ts src/components/chat/MessageBubble.test.tsx src/store/chatStore.test.ts src/api/sse.test.ts
npm run test -- --run
npm run build
```

Acceptance: all tests pass, TypeScript discriminated-union narrowing succeeds, and pagination does not duplicate or unbound the message layout.

## 10. Task P0-7: Complete the Dynamic Real-Data Evaluator

**Files:**

- Modify: `scripts/verify_multi_intent_voice.py`
- Modify: `tests/test_multi_intent_voice_eval.py`
- Modify: `tests/test_huiji_eval.py`
- Read only: `eval/queries_core.jsonl`

### Step 1: Write failing response-evaluation tests

Add pure functions that evaluate synthetic Ask/SSE/page transcripts against `CharacterInventory`:

```python
evaluate_sources(inventory, source_ids, route_debug, page_size, budgets) -> list[str]
evaluate_first_voice_page(inventory, panel) -> list[str]
evaluate_all_voice_pages(inventory, pages) -> list[str]
evaluate_media_union(route_debug, media) -> list[str]
```

Test exact set equality, duplicate detection, foreign-entity media, dynamic skill/voice quotas, over-budget shortfall, text-only voice children, missing sections, and language variation. Assertions must derive expected values from fixture rows, not fixture count literals tied to a role.

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_multi_intent_voice_eval.py tests/test_huiji_eval.py -q
```

Expected: FAIL because network/report evaluation is not implemented.

### Step 2: Add deterministic Ask/SSE/page evaluation

Extend the CLI with:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe scripts/verify_multi_intent_voice.py evaluate --base-url http://127.0.0.1:8000 --output eval/multi_intent_voice_report.json
```

For each selected eligible entity, generate the query from its artifact `entity_name` and a generic `技能和语音` template. Parse the real SSE sources event and first voice page, then follow every `next_cursor` until completion. Compare:

- requested intents against `("skill", "voice")`;
- source skill IDs against `S` and distinct voice text IDs against `T` under current budgets;
- first-page line/media IDs and dynamic `total_lines` against `V` and `M`;
- all pages by exact set equality and duplicate counts;
- media strategy/debug for both skill media and voice;
- every URL/path field against the no-local-path rules.

When an anomaly sample exists, evaluate it separately and require truthful shortfall/no-empty-player behavior. The JSON report must contain configuration, collection snapshot reference, selected entities, dynamic expectations, observed IDs/counts, failures, and an overall pass flag.

### Step 3: Keep the existing core evaluator green

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_huiji_eval.py -q
```

Then run the existing evaluator command documented in `docs/huiji-rag-runbook.md`. Existing single-intent cases must pass their current thresholds, and cases forbidding voice media must still report no voice leak.

## 11. Task P0-8: Run Full Regression and Real End-to-End Hard Gates

**Files:**

- Modify only if a failure exposes a P0 defect in files already listed above.
- Generate: `eval/multi_intent_voice_report.json`
- Generate: `eval/multi_intent_voice_collection_after.json`
- Generate: `eval/multi_intent_voice_ui_evidence.md`

### Step 1: Run complete backend regression

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_query_plan.py tests/test_retrieval_budget.py tests/test_retriever.py tests/test_hybrid_retriever.py tests/test_reranker.py tests/test_voice_pagination.py tests/test_huiji_media_registry.py tests/test_chain_assets.py tests/test_sse.py tests/test_multi_intent_voice_eval.py tests/test_huiji_eval.py -q
D:\Anaconda32024\envs\LangChain\python.exe -m pytest -q
```

Expected: PASS. Any failure must be debugged before continuing; do not weaken an assertion to make the gate pass.

### Step 2: Run complete frontend regression and build

```powershell
npm run test -- --run
npm run build
```

Expected: PASS with no TypeScript errors.

### Step 3: Start the real services

Start the backend using the existing project runbook, then start the React dev server on an unused port. Confirm `/health` reports the active collection loaded before evaluation. Do not rebuild any index or artifact to make health pass.

### Step 4: Run the dynamic real-data evaluator

```powershell
D:\Anaconda32024\envs\LangChain\python.exe scripts/verify_multi_intent_voice.py evaluate --base-url http://127.0.0.1:8000 --output eval/multi_intent_voice_report.json
```

Expected: report `overall_pass=true`; sample count is `min(8, eligible_character_count)`; selected entities cover required strata; all expected sets are calculated from current artifacts; any available anomaly sample passes its shortfall assertions.

### Step 5: Verify the React workflow with sampled real entities

Use entity names from the generated report, not a hardcoded role. In the real React UI:

1. submit at least one low-, median-, and high-playable-line sampled query;
2. confirm the answer sources include both requested intents;
3. confirm one row per line and language switching within a row;
4. load through at least two pages for a `has_more` sample;
5. confirm rows append without duplicate audio, only one audio plays, and the panel remains bounded;
6. confirm a non-voice single-intent sample has no voice panel.

Record the report entity IDs, tested URLs, observed page/line totals, and pass/fail results in `eval/multi_intent_voice_ui_evidence.md`. Screenshots may accompany the report but do not replace the assertions.

### Step 6: Prove the collection remained unchanged

```powershell
D:\Anaconda32024\envs\LangChain\python.exe scripts/verify_multi_intent_voice.py snapshot --output eval/multi_intent_voice_collection_after.json
D:\Anaconda32024\envs\LangChain\python.exe scripts/verify_multi_intent_voice.py compare-snapshots --before eval/multi_intent_voice_collection_before.json --after eval/multi_intent_voice_collection_after.json
```

Expected: PASS with identical collection name, schema, and row count. If it differs, stop and report the external state change; do not repair it by rebuilding or writing to Milvus.

### Step 7: Final self-review against this plan

Check every row in the hard-gate matrix and every acceptance assertion. Search production code, tests, and the evaluator for accidental role-specific sealing:

```powershell
rg -n "EXPECTED_(ENTITY|ROLE|SKILL_COUNT|VOICE_COUNT|LANGUAGE_COUNT)|expected_(entity|role|skill_count|voice_count|language_count)|char:[0-9]+" src backend frontend/react-app/src scripts/verify_multi_intent_voice.py tests/test_multi_intent_voice_eval.py tests/test_retrieval_budget.py tests/test_voice_pagination.py
rg -n "sources\[:top_k\]|VOICE_PANEL_LIMIT|local_relpath|file://" src backend frontend/react-app/src
```

Expected: no role-specific production/evaluation expectation, no blind final source slice, no full voice panel limit, and no local path in serialized output. Existing unrelated synthetic fixtures may use IDs/counts only when their assertions derive expectations from fixture data rather than a real role.

## 12. Completion Criteria

Implementation is complete only when all nine P0 gates pass together, the real-data report and UI evidence are present, and pre/post collection snapshots match. Passing unit tests alone is insufficient.

The resulting behavior must be generic:

- all explicit P0 character section intents survive Stage 0 and are consumed downstream;
- candidate K adapts only to text-source quotas and remains capped;
- final context allocation preserves intent coverage under source/character budgets;
- voice media is grouped by real child IDs and paged server-side;
- all counts and samples come from current artifacts;
- no implementation branch names or special-cases a particular role;
- no artifact, vector collection, MinIO object, or database row is modified.
