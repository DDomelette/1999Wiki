# RAG Full-Chain Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a read-only, dynamically sampled RAG full-chain evaluator that classifies the system and its five modules as `PASS` or `SEV-4..SEV-0`, with production answer generation, an independent LLM judge, deterministic hard gates, and auditable evidence.

**Architecture:** A new `src/rag_eval` package owns versioned contracts, artifact-derived sampling, HTTP/SSE collection, deterministic metrics, independent answer judging, severity aggregation, and report rendering. A thin CLI runs preflight, captures immutable before/after Milvus snapshots, executes at least 48 unique real-service questions plus repeats, and writes one versioned evidence directory without mutating Milvus, MinIO, MySQL, or processed artifacts.

**Tech Stack:** Python 3.11, dataclasses, `requests`, `langchain-openai`, `pymilvus`, pytest, JSON/JSONL, Markdown, existing Huiji artifacts and FastAPI endpoints.

## Global Constraints

- Governing spec: `docs/superpowers/specs/2026-07-13-rag-full-chain-evaluation-design.md`.
- P0 scope: `READY-P0-01..04`, `RETR-P0-01..05`, `ANSWER-P0-01..06`, `MEDIA-P0-01..05`, `RELY-P0-01..04`.
- Mainline tasks contain P0 work only. P1 is listed as optional and P2 is deferred.
- Evaluation is read-only except for its own new `eval/rag_full_chain/<run_id>` evidence directory.
- Do not rebuild or write Milvus, upload/delete MinIO objects, write MySQL, or modify `data/processed/huiji/**` to make evaluation pass.
- Do not hardcode a real entity name, entity ID, child ID, skill count, voice-line count, language count, or media count in production evaluator logic or acceptance assertions.
- Expectations must be derived from the current artifacts and frozen into `sample_manifest.v1.jsonl` before the first evaluated request.
- Difficulty may lower quality-score floors only. It never lowers path-leak, cross-entity, binding, unsupported-claim, pagination, protocol, service-error, or mutation gates.
- Production answer model and judge must use different `(base_url, model)` identities. Missing or identical judge configuration is `SEV-0` and stops before evaluated requests.
- Judge temperature is `0`; judge input/output schema and prompt version are recorded.
- All HTTP clients disable inherited proxy settings for loopback requests.
- Use `D:\Anaconda32024\envs\LangChain\python.exe` for documented commands.
- Work directly in the authorized dirty worktree. Do not run git worktree, stage, commit, reset, checkout, clean, or revert operations.

---

## 1. File Structure

### New files

| File | Responsibility |
|---|---|
| `src/rag_eval/__init__.py` | Public evaluation interfaces and schema version exports |
| `src/rag_eval/contracts.py` | Difficulty, severity, event, case, result, and summary contracts |
| `src/rag_eval/inventory.py` | Read-only artifact inventory and full Milvus primary-key snapshot |
| `src/rag_eval/sampling.py` | Deterministic stratified sampling, query variants, dynamic qrels |
| `src/rag_eval/client.py` | `/health`, `/ask`, `/ask/stream`, and voice-page HTTP collection |
| `src/rag_eval/deterministic.py` | M1/M2/M4/M5 hard gates and deterministic metrics |
| `src/rag_eval/judge.py` | Independent M3 judge configuration, prompt, parse, and citation checks |
| `src/rag_eval/scoring.py` | Case/module/difficulty scoring and severity aggregation |
| `src/rag_eval/reporting.py` | Canonical JSON/JSONL evidence and concise Markdown report |
| `src/rag_eval/runner.py` | End-to-end orchestration with preflight and pre/post snapshot gates |
| `scripts/evaluate_rag_full_chain.py` | CLI entry point |
| `eval/rag_full_chain_thresholds.v1.json` | Reviewed sample, score, reliability, and performance thresholds |
| `eval/rag_full_chain_boundary_seeds.v1.jsonl` | Entity-agnostic D4 and language-noise seed definitions |
| `tests/test_rag_eval_contracts.py` | Contract and severity ordering tests |
| `tests/test_rag_eval_inventory.py` | Artifact/snapshot/read-only tests |
| `tests/test_rag_eval_sampling.py` | Dynamic coverage and no-role-sealing tests |
| `tests/test_rag_eval_client.py` | HTTP/SSE/pagination transcript tests |
| `tests/test_rag_eval_deterministic.py` | M1/M2/M4/M5 metric and hard-gate tests |
| `tests/test_rag_eval_judge.py` | Judge independence, schema, and M3 tests |
| `tests/test_rag_eval_scoring.py` | Difficulty aggregation and global severity tests |
| `tests/test_rag_eval_reporting.py` | Evidence/report shape and atomic-write tests |
| `tests/test_rag_eval_runner.py` | Full orchestration and stop-condition tests |

### Modified files

| File | Change |
|---|---|
| `.env.example` | Add empty judge-only environment variables; no secret values |
| `docs/huiji-rag-runbook.md` | Distinguish smoke evaluation from full-chain acceptance and document commands |

Existing `scripts/evaluate_huiji_rag.py`, `eval/queries_core.jsonl`, and `scripts/verify_multi_intent_voice.py` remain compatible. The 9-case evaluator remains a smoke suite; the new evaluator does not import mutable runtime state from it.

## 2. P0 Hard-Gate Matrix

| Gate | Spec IDs | Required evidence | Failure result |
|---|---|---|---|
| `GATE-01 Preflight` | `READY-P0-01..04` | healthy backend/dependencies, artifact hashes, distinct judge, before snapshot | `SEV-0` if evaluation cannot run; `SEV-1` for proven drift/mutation |
| `GATE-02 Sampling` | `RETR-P0-01..05` | 48+ unique cases, D1/D2/D3/D4 minima, all P0 intents covered, 8+ dynamic entities | `SEV-2`; no requests start with an invalid manifest |
| `GATE-03 Retrieval` | `RETR-P0-01..05` | entity/intent, Recall@K, MRR, nDCG, intent coverage, budgets | `SEV-1` cross-entity; otherwise score aggregation may yield `SEV-2/3/4` |
| `GATE-04 Answer` | `ANSWER-P0-01..06` | production answer, independent judge, citations, refusal behavior | `SEV-1` for deterministic fabrication; otherwise `SEV-2/3/4` |
| `GATE-05 Media` | `MEDIA-P0-01..05` | media binding, page/set equality, safe URLs, sync/SSE parity | `SEV-1` for binding/path leak; `SEV-2` for pagination/contract failure |
| `GATE-06 Reliability` | `RELY-P0-01..04` | success rate, repeats, retrieval/TTFT/total P95, structured errors | `SEV-0` if main path cannot execute; otherwise `SEV-2/3/4` |
| `GATE-07 Read-only close` | `READY-P0-03` | exact pre/post collection snapshot equality | `SEV-1`, acceptance blocked |
| `GATE-08 Final classification` | all P0 | module summary and Markdown report agree | accept only `PASS`, `SEV-4`, or recorded `SEV-3 accepted_with_warnings` |

---

## 3. Task 1: Versioned Contracts and Thresholds

**Corresponding specs:** `READY-P0-04`, shared contract for all P0 gates.

**Files:**

- Create: `src/rag_eval/__init__.py`
- Create: `src/rag_eval/contracts.py`
- Create: `eval/rag_full_chain_thresholds.v1.json`
- Create: `tests/test_rag_eval_contracts.py`

**Interfaces:**

- Produces: `Severity`, `Difficulty`, `EvaluationEvent`, `EvalCase`, `CaseResult`, `ModuleResult`, `RunManifest`, `Thresholds`, `JudgeIdentity`.
- Consumed by: every later task.

- [ ] **Step 1: Write failing contract and severity tests**

Test exact ordering and OpenTelemetry mapping:

```python
def test_severity_order_is_incident_order_and_otel_mapping_is_stable():
    assert Severity.PASS.rank == 5
    assert Severity.SEV4.otel_number == 9
    assert Severity.SEV3.otel_number == 13
    assert Severity.SEV2.otel_number == 17
    assert Severity.SEV1.otel_number == 20
    assert Severity.SEV0.otel_number == 21
    assert worst_severity([Severity.SEV3, Severity.SEV1]) is Severity.SEV1


def test_contract_rejects_event_with_mismatched_module_or_severity_number():
    with pytest.raises(ValueError, match="severity_number"):
        EvaluationEvent(
            event_code="RETR.CROSS_ENTITY_SOURCE",
            module="M2",
            severity=Severity.SEV1,
            severity_number=17,
        )
```

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_contracts.py -q
```

Expected: FAIL because `src.rag_eval` does not exist.

- [ ] **Step 2: Implement immutable contracts**

Use string enums and frozen dataclasses. Keep event aggregation fields stable:

```python
class Severity(str, Enum):
    PASS = "PASS"
    SEV4 = "SEV-4"
    SEV3 = "SEV-3"
    SEV2 = "SEV-2"
    SEV1 = "SEV-1"
    SEV0 = "SEV-0"

    @property
    def rank(self) -> int:
        return {"SEV-0": 0, "SEV-1": 1, "SEV-2": 2,
                "SEV-3": 3, "SEV-4": 4, "PASS": 5}[self.value]

    @property
    def otel_number(self) -> int | None:
        return {"SEV-0": 21, "SEV-1": 20, "SEV-2": 17,
                "SEV-3": 13, "SEV-4": 9, "PASS": None}[self.value]


class Difficulty(str, Enum):
    D1 = "D1"
    D2 = "D2"
    D3 = "D3"
    D4 = "D4"


@dataclass(frozen=True)
class EvaluationEvent:
    event_code: str
    module: str
    severity: Severity
    severity_number: int | None
    case_ids: tuple[str, ...] = ()
    observed: Mapping[str, object] = field(default_factory=dict)
    expected: Mapping[str, object] = field(default_factory=dict)
    recommended_action: str = ""
```

`EvalCase` must contain `case_id`, `query`, `difficulty`, `scenario`, `expected_entity_id`, `expected_entity_name`, `expected_intents`, `expected_source_ids`, `expected_media_ids`, `forbidden_media_types`, `allow_no_sources`, `repeat_of`, and `derivation`. `CaseResult` must preserve raw route/sources/media/panels/answer/timings/events/judge result without local filesystem paths from artifact rows.

`JudgeIdentity` contains only `base_url`, `model`, and `prompt_version`; it never contains an API key. Task 2 accepts this value as an explicit preflight input, and Task 6 owns loading the secret-bearing judge client.

- [ ] **Step 3: Add the reviewed threshold file**

Create exactly:

```json
{
  "schema_version": "rag_eval.thresholds/v1",
  "p0_intents": ["intro", "profile_fact", "skill", "item", "culture", "voice", "media", "video", "psychube", "story", "general_game", "meta_question"],
  "sample_minimums": {"unique": 48, "D1": 16, "D2": 12, "D3": 12, "D4": 8, "entities": 8, "repeat_rate": 0.1},
  "difficulty": {
    "D1": {"target": 90, "floor": 85, "floor_pass_rate": 0.95},
    "D2": {"target": 85, "floor": 78, "floor_pass_rate": 0.90},
    "D3": {"target": 80, "floor": 70, "floor_pass_rate": 0.85},
    "D4": {"target": 90, "floor": 85, "floor_pass_rate": 1.0}
  },
  "weights": {
    "text": {"M2": 0.4, "M3": 0.5, "M5": 0.1},
    "media": {"M2": 0.3, "M4": 0.6, "M5": 0.1},
    "hybrid": {"M2": 0.3, "M3": 0.3, "M4": 0.3, "M5": 0.1},
    "boundary": {"M2": 0.3, "M3": 0.6, "M5": 0.1}
  },
  "reliability": {"success_rate_min": 0.98, "retrieval_p95_ms": 5000, "ttft_p95_ms": 15000, "total_p95_ms": 45000},
  "judge": {"likert_pass": 3, "human_alignment_min": 0.85},
  "sync_stream_parity_minimum": 8
}
```

Loader validation must reject missing difficulty groups, a P0 intent list different from the reviewed list, weights not summing to `1.0`, non-monotonic target/floor values, or sample minima below the spec. Legacy compatibility intents `profile` and `lore` and the generic fallback `general` remain accepted by production routing but are not substituted for the reviewed P0 intent set.

- [ ] **Step 4: Run focused tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_contracts.py -q
```

Expected: PASS.

**Task acceptance:** Contracts serialize with `schema_version`; severity ordering is unambiguous; reviewed thresholds cannot be silently weakened below the spec.

---

## 4. Task 2: Read-Only Inventory, Preflight, and Full Milvus Snapshot

**Corresponding specs:** `READY-P0-01..04`.

**Files:**

- Create: `src/rag_eval/inventory.py`
- Create: `tests/test_rag_eval_inventory.py`

**Interfaces:**

- Consumes: `Config`, `HuijiBuildPaths`, `Thresholds`, `JudgeIdentity | None`.
- Produces: `EvaluationInventory`, `MilvusSnapshot`, `PreflightResult`, `capture_inventory(cfg)`, `capture_milvus_snapshot(cfg)`, `compare_snapshots(before, after)`, `reconstruct_context(inventory, observed_sources)`.

- [ ] **Step 1: Write failing inventory and snapshot tests**

Tests must prove:

```python
def test_inventory_derives_entities_intents_and_media_from_rows():
    inventory = build_inventory(parent_rows, child_rows, media_rows)
    entity = inventory.entities["entity-1"]
    assert entity.child_ids_by_intent["skill"] == ("fixture:entity-1/skill:0001",)
    assert entity.media_ids_by_type["voice"] == ("media:sha1:" + "a" * 40,)


def test_snapshot_hashes_all_primary_ids_without_requesting_vectors():
    snapshot = capture_milvus_snapshot_from_client(client, "collection")
    assert snapshot.primary_field == "id"
    assert snapshot.primary_id_count == 3
    assert snapshot.primary_ids_sha256 == sha256_lines(["a", "b", "c"])
    assert all(call["output_fields"] == ["id"] for call in client.query_calls)


def test_snapshot_comparison_detects_same_count_different_ids():
    assert compare_snapshots(before, after) == ["primary_ids_sha256 changed"]
```

Run the focused test and confirm failure before implementation.

- [ ] **Step 2: Build the artifact-derived inventory**

Read `parent_blocks.jsonl`, `child_blocks.jsonl`, `media_assets.jsonl`, and `build_manifest.json` through `build_paths(cfg)` and `iter_jsonl()`. Build immutable indexes by entity and child. Derive intent membership from `route_tags` first and `CHARACTER_POLICIES.sections` second. Retain child text in the in-memory inventory because the public `/ask` and SSE source contracts omit source content. Keep only artifact IDs and public transport fields in sample manifests; never serialize `local_relpath`.

`reconstruct_context()` must resolve every observed `child_id`, preserve returned source order, and reproduce `RAGChain._format_context()` labels and separators from frozen artifact fields. An unresolved source ID is an evaluation/data-contract error, not an empty context fallback. Store the reconstructed context SHA-256 and judge-visible source excerpts in case evidence so M3 can be reproduced without exposing local paths.

The inventory validator must report, not repair:

- missing required artifact files;
- duplicate parent/child/media IDs;
- parent-child reference mismatches;
- media child IDs not present in child blocks;
- blank entity identity for rows used by sampling;
- malformed HTTP media URLs;
- activity collection mismatch between `vectorstore.collection_name` and `huiji.text_collection_name`.

- [ ] **Step 3: Implement a full primary-key snapshot**

Use the active collection schema to discover the primary field. Iterate primary IDs in bounded batches, sort them, and hash newline-delimited UTF-8 IDs. Request only the primary field; never request vectors or document text.

Snapshot fields:

```json
{
  "schema_version": "rag_eval.milvus_snapshot/v1",
  "collection_name": "",
  "schema_sha256": "",
  "row_count": 0,
  "primary_field": "id",
  "primary_id_count": 0,
  "primary_ids_sha256": "",
  "load_state": {},
  "captured_at_utc": ""
}
```

Comparison ignores `captured_at_utc` and requires exact equality for every other field.

- [ ] **Step 4: Implement preflight severity rules**

`preflight()` must call backend `/health` and MinIO `/minio/health/ready`, verify required artifact files, load inventory, capture the before snapshot, verify answer-model credentials, and validate the explicit `JudgeIdentity` contract. It returns `SEV-0` and `allowed_to_run=false` when the full evaluator cannot run. Artifact/index inconsistency that proves current results are untrustworthy is `SEV-1`. It must not start any evaluated query when `allowed_to_run=false`.

- [ ] **Step 5: Run focused tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_inventory.py tests/test_rag_eval_contracts.py -q
```

Expected: PASS.

**Task acceptance:** M1 can distinguish unavailable, inconsistent, and ready states; same-count primary-key drift is detected; no vectors or local paths enter evidence.

---

## 5. Task 3: Dynamic Stratified Sampling and Qrels

**Corresponding specs:** `RETR-P0-01..05`; sampling portion of all answer/media gates.

**Files:**

- Create: `src/rag_eval/sampling.py`
- Create: `eval/rag_full_chain_boundary_seeds.v1.jsonl`
- Create: `tests/test_rag_eval_sampling.py`

**Interfaces:**

- Consumes: `EvaluationInventory`, `Thresholds`, integer seed.
- Produces: `build_sample_manifest(inventory, thresholds, seed) -> tuple[EvalCase, ...]`, `validate_sample_manifest(...)`.

- [ ] **Step 1: Write failing deterministic sampling tests**

Cover exact requirements:

```python
def test_manifest_meets_difficulty_entity_intent_and_repeat_minima():
    cases = build_sample_manifest(inventory, thresholds, seed=1999)
    unique = [case for case in cases if case.repeat_of is None]
    assert len(unique) >= 48
    counts = Counter(case.difficulty for case in unique)
    assert counts[Difficulty.D1] >= 16
    assert counts[Difficulty.D2] >= 12
    assert counts[Difficulty.D3] >= 12
    assert counts[Difficulty.D4] >= 8
    assert len({case.expected_entity_id for case in unique if case.expected_entity_id}) >= 8
    assert len([case for case in cases if case.repeat_of]) >= math.ceil(len(unique) * 0.1)


def test_manifest_is_deterministic_and_expectations_come_from_inventory():
    assert build_sample_manifest(inventory, thresholds, 1999) == build_sample_manifest(inventory, thresholds, 1999)
    assert all(case.derivation["inventory_sha256"] == inventory.sha256 for case in cases)


def test_no_real_entity_or_count_is_required_by_sampling_source():
    source = Path("src/rag_eval/sampling.py").read_text(encoding="utf-8")
    assert "char:" not in source
    assert not re.search(r"expected_(skill|voice|language)_count\s*=\s*\d+", source)
```

- [ ] **Step 2: Define entity-agnostic query families**

Implement template families, not one template per error:

```python
QUERY_FAMILIES = {
    Difficulty.D1: ("介绍一下{entity}", "{entity}的{intent_label}是什么"),
    Difficulty.D2: ("介绍{entity}的{intent_a}和{intent_b}", "比较{entity_a}和{entity_b}的{intent_label}"),
    Difficulty.D3: ("想问下 {entity} {noisy_intent} 都有啥", "{alias}{fragment}"),
}
```

D3 noise transformations are deterministic and bounded: spacing/punctuation loss, repeated character, one intent-keyword typo, colloquial filler, alias substitution, and one entity-character deletion/transposition when the name length permits. Preserve the unmodified expected entity in the manifest.

Boundary seed rows use generic placeholders or synthetic nonexistent names only:

```json
{"seed_id":"unknown_entity","difficulty":"D4","query_template":"介绍一下不存在的角色评估样本甲","expected_behavior":"no_fabrication"}
{"seed_id":"unsupported_fact","difficulty":"D4","query_template":"请说明{entity}在资料中没有记载的获奖年份","expected_behavior":"insufficient_evidence"}
{"seed_id":"out_of_domain","difficulty":"D4","query_template":"请用知识库资料证明一个与游戏无关的实时新闻结论","expected_behavior":"no_fabrication"}
{"seed_id":"clarification","difficulty":"D4","query_template":"那个角色的技能怎么样","expected_behavior":"clarify_or_failure_action"}
```

- [ ] **Step 3: Derive qrels and expected media sets**

For each selected entity/intent:

- derive relevant child IDs from route tags and policy sections;
- `skill` qrels include all available skill/ultimate children;
- `voice` source qrels include up to configured first-page distinct playable child IDs while the full media expectation includes all playable voice media grouped by child;
- other detail intents require at least one matching child and preserve all relevant IDs for Recall@K/nDCG;
- media expectations include only available, non-common, intent-allowed HTTP assets;
- comparison cases store separate qrels per entity and forbid sources from third entities;
- no-answer cases use empty qrels plus an explicit expected failure/refusal behavior.

- [ ] **Step 4: Apply deterministic pairwise coverage and volume strata**

Select at least eight entities spanning low/median/high child count and, where applicable, playable media count. Cover every `p0_intents` entry from the reviewed threshold file in at least one D1 and one D2/D3 case. Entity-free intents such as `general_game` and `meta_question` use fixed language templates without real-role expectations. If current artifacts contain no eligible evidence for a data-backed P0 intent, emit a sampling/data-coverage failure instead of silently removing that intent. Add cases beyond 48 when minima conflict; never drop intent coverage to preserve the base count.

- [ ] **Step 5: Validate and freeze the manifest before requests**

`validate_sample_manifest()` must reject duplicate case IDs, missing derivation, unmet minima, unavailable expected IDs, an unsupported intent, or a repeated case whose query/config differs from its original. Write the manifest before the runner sends the first evaluated request.

- [ ] **Step 6: Run focused tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_sampling.py tests/test_rag_eval_inventory.py -q
```

Expected: PASS.

**Task acceptance:** The sample set is diverse, deterministic, generic, dynamically grounded, and large enough for all difficulty and intent gates without a role-specific seal.

---

## 6. Task 4: Real HTTP, SSE, Pagination, and Timing Collector

**Corresponding specs:** `MEDIA-P0-03..05`, `RELY-P0-01..04`.

**Files:**

- Create: `src/rag_eval/client.py`
- Create: `tests/test_rag_eval_client.py`

**Interfaces:**

- Consumes: `EvalCase`, base URL, timeouts.
- Produces: `ObservedExchange`, `SSETranscript`, `TimingObservation`; `RagEvalClient.ask()`, `.ask_stream()`, `.collect_voice_pages()`.

- [ ] **Step 1: Write failing client tests with a local fake session**

Test:

- `Session.trust_env is False`;
- `/ask` response size and JSON shape limits;
- SSE ordering `sources -> token* -> done`;
- `error` without `done` is a structured failed exchange;
- TTFT starts at request start and ends at first non-empty token;
- voice cursors are followed until `has_more=false` with a 512-page hard cap;
- repeated cursor, duplicate page, malformed JSON, or local-path-bearing cursor is rejected.

Run and verify failure before implementation.

- [ ] **Step 2: Implement bounded loopback HTTP collection**

Use `requests.Session()` with `trust_env=False`, explicit connect/read timeout, maximum JSON/SSE bytes, and no retry for non-idempotent answer requests. Record `started_at_utc`, HTTP status, retrieval/meta arrival time, TTFT, total time, and structured client error.

`ask()` posts `{"question": case.query}` to `/ask`. `ask_stream()` parses event blocks without using browser state. Do not write response content outside the run evidence directory.

- [ ] **Step 3: Implement voice-page collection**

For every returned voice panel with `next_cursor`, call `/api/media/voice/page?cursor=...` until complete. Preserve pages in order and separately compute the union of line IDs and media IDs. Stop with a structured `MEDIA.PAGINATION_LOOP` event on repeated cursor or page cap; do not retry indefinitely.

- [ ] **Step 4: Define parity and repeat subsets**

Collect `/ask/stream` as the primary full-chain execution for every unique case and every repeat so retrieval/meta arrival, TTFT, and total latency are measured across the full sample. Also collect synchronous `/ask` for at least eight deterministically selected parity cases covering all four difficulty levels, one text-only case, one media case, one hybrid case, and one no-answer case. The SSE `done.answer` is the primary answer passed to M3; the synchronous answer is additional parity evidence.

- [ ] **Step 5: Run focused tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_client.py -q
```

Expected: PASS.

**Task acceptance:** Real-service transcripts are bounded, complete, timing-aware, proxy-independent, and sufficient to test sync/SSE parity, repeats, and all voice pages.

---

## 7. Task 5: Deterministic M1, M2, M4, and M5 Evaluation

**Corresponding specs:** `READY-P0-01..04`, `RETR-P0-01..05`, `MEDIA-P0-01..05`, `RELY-P0-01..04`.

**Files:**

- Create: `src/rag_eval/deterministic.py`
- Create: `tests/test_rag_eval_deterministic.py`

**Interfaces:**

- Consumes: `EvalCase`, `ObservedExchange`, `EvaluationInventory`, thresholds.
- Produces: `evaluate_deterministic(...) -> DeterministicResult` containing M1/M2/M4/M5 scores, metrics, and aggregated events.

- [ ] **Step 1: Write failing metric and hard-gate tests**

Include exact metric fixtures:

```python
def test_rank_metrics_use_dynamic_qrels():
    ranked = ["x", "b", "a"]
    relevant = {"a": 2.0, "b": 1.0}
    assert recall_at_k(ranked, relevant, 3) == 1.0
    assert mrr(ranked, relevant) == 0.5
    assert 0.0 < ndcg_at_k(ranked, relevant, 3) <= 1.0


def test_cross_entity_source_is_sev1_and_cannot_be_averaged():
    result = evaluate_retrieval(case, exchange_with_third_entity, inventory)
    assert any(e.event_code == "RETR.CROSS_ENTITY_SOURCE" and e.severity is Severity.SEV1 for e in result.events)


def test_local_path_or_wrong_child_binding_is_sev1():
    assert evaluate_media(case, leaked_exchange, inventory).severity is Severity.SEV1
```

- [ ] **Step 2: Implement M2 planning and retrieval metrics**

Compute:

- entity accuracy using route entity plus returned source identity;
- primary/secondary intent exact match and set F1;
- Recall@K, MRR, nDCG@K from manifest qrels;
- requested-intent coverage using `route.requested_intents` and `retrieval_debug.intent_retained`;
- source and character budget consistency;
- cross-entity and unexpected-third-entity leakage;
- no-source/failure-action correctness.

Create stable event families such as `RETR.WRONG_ENTITY`, `RETR.INTENT_LOSS`, `RETR.QREL_MISS`, `RETR.CROSS_ENTITY_SOURCE`, and `RETR.BUDGET_SHORTFALL`. Aggregate all same-code cases into one event at report time.

- [ ] **Step 3: Implement M4 media and transport gates**

Recursively inspect every key/value in route, sources, media, panels, cursors, and SSE/done payload. Reject Windows drive paths, `file:`, backslashes in URL payloads, traversal, forbidden local-path field names, and non-HTTP media URLs.

Compare observed media IDs to the manifest expectation and verify each observed media ID maps to the expected entity/parent/child in the independent inventory. For voice, compare:

- first-page line/media IDs;
- dynamic `total_lines`, page size, and `has_more`;
- every page cursor transition;
- full line/media union by exact set equality;
- duplicate line/media counts;
- variants grouped under the correct line.

Sync/SSE deterministic parity compares route entity/intents, source-ID set, media-ID set, panel summary, answer presence, and structured failure state. Exact answer text equality is not required because the model is sampled twice. Task 6 judges whether both answers are grounded and semantically consistent; disagreement on entity, numeric facts, or requested-intent conclusions is `ANSWER.SYNC_STREAM_DIVERGENCE`. A wrong binding or path leak is `SEV-1`; incomplete pagination or deterministic contract parity failure is `SEV-2`.

- [ ] **Step 4: Implement M5 reliability metrics**

Compute request success rate, structured failure rate, repeat consistency, and nearest-rank P50/P95 for retrieval/meta, TTFT, and total time. A successful HTTP status with malformed/empty protocol output is a failed request. If the main answer path cannot execute for the sample set, emit `SEV-0`; below 98% success or any performance hard limit breach emits at least `SEV-2` unless the spec's quality aggregation yields a more severe event.

Repeat consistency requires exact entity, requested-intent set, key source set, and media set. Answer wording may differ, but deterministic claim extraction must flag contradictory numeric/factual statements for M3 review.

- [ ] **Step 5: Convert deterministic metrics to normalized module scores**

M2 score uses entity/intent correctness, retrieval recall/rank, and intent coverage. M4 score uses media precision, binding, pagination, and parity. M5 score uses success, consistency, and latency. Any hard event preserves its severity independently of score.

- [ ] **Step 6: Run focused tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_deterministic.py tests/test_rag_eval_client.py tests/test_multi_intent_voice_eval.py tests/test_huiji_eval.py -q
```

Expected: PASS; existing evaluators remain green.

**Task acceptance:** Retrieval, media, transport, and reliability failures map to one of the five modules and stable event families; severe facts cannot disappear into average scores.

---

## 8. Task 6: Independent M3 Judge, Citation, and Refusal Evaluation

**Corresponding specs:** `ANSWER-P0-01..06`.

**Files:**

- Create: `src/rag_eval/judge.py`
- Create: `tests/test_rag_eval_judge.py`
- Modify: `.env.example`

**Interfaces:**

- Consumes: production `Config`, `EvalCase`, answer, actual context/sources.
- Produces: `JudgeConfig`, `JudgeResult`, `load_judge_config()`, `evaluate_answer()`, `evaluate_answer_pair()`.

- [ ] **Step 1: Write failing judge configuration and parse tests**

Tests must require:

- all judge environment variables present;
- `(judge.base_url, judge.model) != (production.base_url, production.model)`;
- temperature exactly zero;
- response keys and scores `1..5` validated;
- malformed JSON retried once with a repair instruction, then returned as a structured judge failure;
- fake citations detected without a judge call;
- judge score cannot clear deterministic `SEV-1`.
- sync/SSE answer pairs that contradict on entity, numeric facts, or requested-intent conclusions fail semantic parity.

- [ ] **Step 2: Add judge-only environment names**

Append empty values only:

```dotenv
# Independent model used only by the full-chain evaluator.
RAG_EVAL_JUDGE_BASE_URL=
RAG_EVAL_JUDGE_MODEL=
RAG_EVAL_JUDGE_API_KEY=
```

Never log or serialize the API key.

- [ ] **Step 3: Implement the fixed judge prompt and schema**

Use prompt version `rag-answer-judge/v1` and the contract from the spec. The system instruction must state:

```text
Evaluate only the supplied query, expected task, retrieved context, and answer.
Do not use outside game knowledge. A fact that may be true but is absent from
the context is ungrounded. Score groundedness, relevance, completeness, and
refusal_correctness from 1 to 5. Return JSON only. List exact unsupported claims
and missing requirements. Do not reward style or length.
```

Pass `query`, `scenario`, `difficulty`, expected intents/behavior, normalized context with source IDs/names, and production answer. Do not expose local artifact paths or hidden model reasoning.

- [ ] **Step 4: Add deterministic citation and refusal checks**

Parse `[来源名]` citations and require each cited name to exist in returned sources. Record citation validity and support coverage separately from judge scores. For D4, verify the answer does not assert the requested unsupported fact and either states insufficient evidence, asks for clarification, returns failure actions, or explicitly marks free supplementation.

Deterministic fake citation, explicit source contradiction, or judge `groundedness=1` creates a `SEV-1` candidate and an adjudication-queue row. Scores below 3 without a hard contradiction remain quality failures for `SEV-2/3` aggregation.

For each parity case, evaluate the synchronous answer against the same reconstructed context and call `evaluate_answer_pair()` with both judged answers. The pair check returns `equivalent`, `contradictions`, and `reason`; it ignores style, length, and wording. A contradiction emits `ANSWER.SYNC_STREAM_DIVERGENCE` and prevents `MEDIA-P0-05` from passing.

- [ ] **Step 5: Add human-review queue generation**

Select all `SEV-1/2` candidates, all rule/judge conflicts, and a deterministic 10% stratified sample. Store case ID, displayed evidence, judge result, and blank reviewer fields in `adjudication_queue.v1.jsonl`; do not rewrite automatic results.

- [ ] **Step 6: Run focused tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_judge.py tests/test_prompts.py -q
```

Expected: PASS with fake clients; no external judge call occurs in unit tests.

**Task acceptance:** M3 measures real final answers with an independent, reproducible judge while deterministic evidence retains authority.

---

## 9. Task 7: Scoring, Severity Aggregation, and Reports

**Corresponding specs:** all P0 completion and reporting requirements.

**Files:**

- Create: `src/rag_eval/scoring.py`
- Create: `src/rag_eval/reporting.py`
- Create: `tests/test_rag_eval_scoring.py`
- Create: `tests/test_rag_eval_reporting.py`

**Interfaces:**

- Consumes: case results, thresholds, pre/post snapshots.
- Produces: `score_case()`, `summarize_modules()`, `classify_run()`, `write_run_evidence()`.

- [ ] **Step 1: Write failing aggregation tests**

Prove these non-negotiable outcomes:

```python
def test_hard_event_dominates_high_average_score():
    summary = classify_run(cases=[case(score=99, events=[sev1_event])], thresholds=t)
    assert summary.global_severity is Severity.SEV1
    assert summary.accepted is False


def test_d3_can_be_warning_without_lowering_hard_gates():
    summary = classify_difficulty(Difficulty.D3, scores=[72] * 12, thresholds=t)
    assert summary.severity is Severity.SEV3


def test_d4_requires_every_case_to_reach_floor():
    summary = classify_difficulty(Difficulty.D4, scores=[95] * 7 + [84], thresholds=t)
    assert summary.severity is Severity.SEV2
```

- [ ] **Step 2: Implement scenario-weighted case scores**

Apply the exact spec weights for text, media, hybrid, and boundary cases. Reject missing applicable module scores rather than treating them as zero. Store both raw component values and normalized score.

- [ ] **Step 3: Implement difficulty and module classification**

For each difficulty group, compare mean score and floor pass rate to the reviewed thresholds. Map target met to `PASS/SEV-4`, between target and floor to `SEV-3`, and floor/floor-pass-rate failure to `SEV-2`. Aggregate each module independently, then take the worst module/event severity as global severity.

Acceptance values are exact:

```python
accepted = global_severity in {Severity.PASS, Severity.SEV4}
accepted_with_warnings = global_severity is Severity.SEV3
```

`SEV-3` requires an explicit warning list and remediation action. `SEV-2..0` always fails.

- [ ] **Step 4: Implement atomic, canonical evidence writing**

Write to a new run directory only. Use temporary files plus `Path.replace()` for each completed artifact. Never overwrite an existing `run_id`. Required outputs:

```text
run_manifest.v1.json
sample_manifest.v1.jsonl
case_results.v1.jsonl
module_summary.v1.json
evaluation_report.v1.md
pre_snapshot.v1.json
post_snapshot.v1.json
adjudication_queue.v1.jsonl
```

Every JSON document includes schema version and SHA-256 references to predecessor evidence. The report must not contain API keys, local paths, full prompts with secrets, or hidden model reasoning.

- [ ] **Step 5: Render the concise five-module report**

The Markdown first page contains only:

1. global severity and acceptance;
2. one row each for M1-M5 with score, severity, worst event;
3. D1-D4 counts/mean/floor pass rate;
4. at most five aggregated failure clusters;
5. ordered remediation and focused re-run commands.

All per-case detail stays in JSONL evidence.

- [ ] **Step 6: Run focused tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_scoring.py tests/test_rag_eval_reporting.py -q
```

Expected: PASS.

**Task acceptance:** One global result can always be traced to a module, event cluster, cases, raw evidence, and a remediation entry; no scattered errors require manual interpretation.

---

## 10. Task 8: CLI Orchestration and Stop Conditions

**Corresponding specs:** all P0 requirements.

**Files:**

- Create: `src/rag_eval/runner.py`
- Create: `scripts/evaluate_rag_full_chain.py`
- Create: `tests/test_rag_eval_runner.py`

**Interfaces:**

- Consumes: all prior modules.
- Produces: CLI commands `preflight`, `sample`, `run`, `finalize`, `compare-snapshots`.

- [ ] **Step 1: Write failing orchestration tests**

Verify the exact order:

```text
load thresholds -> preflight -> before snapshot -> freeze sample manifest ->
collect production exchanges -> deterministic evaluation -> judge -> score/report ->
after snapshot -> compare -> finalize acceptance
```

Tests must prove:

- failed preflight writes evidence and performs zero evaluated requests;
- invalid sample manifest performs zero evaluated requests;
- one case failure does not abort remaining safe samples;
- post-snapshot drift forces `SEV-1` even when all quality scores pass;
- a judge outage becomes structured failure and cannot produce an accepted report;
- `finalize` refuses incomplete adjudication coverage and never edits automatic case results;
- the runner never calls Milvus insert/upsert/delete, MinIO put/remove, or MySQL write methods.

- [ ] **Step 2: Implement CLI arguments and exit codes**

Required commands:

```powershell
python scripts/evaluate_rag_full_chain.py preflight --base-url http://127.0.0.1:8000 --output <path>
python scripts/evaluate_rag_full_chain.py sample --seed 1999 --output <path>
python scripts/evaluate_rag_full_chain.py run --base-url http://127.0.0.1:8000 --seed 1999 --output-root eval/rag_full_chain
python scripts/evaluate_rag_full_chain.py finalize --run-dir <path> --adjudication <path>
python scripts/evaluate_rag_full_chain.py compare-snapshots --before <path> --after <path>
```

Exit `0` for `PASS/SEV-4`, `3` for `SEV-3 accepted_with_warnings`, `2` for `SEV-2`, `1` for `SEV-1`, and `10` for `SEV-0`/preflight fatal. Unexpected evaluator bugs use a distinct nonzero exit and preserve partial evidence.

`run` writes immutable automatic results and an adjudication queue. `finalize` validates that every required queue row has a reviewer decision, computes judge/human agreement, and writes `module_summary.final.v1.json` plus `evaluation_report.final.v1.md`; it never modifies `case_results.v1.jsonl`, the automatic summary, or the automatic report. Final acceptance uses the final files when an adjudication queue is non-empty.

- [ ] **Step 3: Implement bounded continuation after case failures**

After preflight and manifest gates pass, collect remaining cases after a per-case error so impact scope is known. Stop early only for an evaluator-wide fatal condition: backend becomes wholly unavailable, evidence output cannot be safely written, judge identity changes during the run, or read-only mutation is detected.

- [ ] **Step 4: Run orchestration tests**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_runner.py tests/test_rag_eval_contracts.py tests/test_rag_eval_inventory.py tests/test_rag_eval_sampling.py tests/test_rag_eval_client.py tests/test_rag_eval_deterministic.py tests/test_rag_eval_judge.py tests/test_rag_eval_scoring.py tests/test_rag_eval_reporting.py -q
```

Expected: PASS.

**Task acceptance:** The complete evaluator has deterministic stop/continue rules, meaningful exit codes, and always leaves reviewable evidence.

---

## 11. Task 9: Regression, Runbook, and Real P0 Acceptance

**Corresponding specs:** all P0 requirements and final completion criteria.

**Files:**

- Modify: `docs/huiji-rag-runbook.md`
- Generate only at runtime: `eval/rag_full_chain/<run_id>/**`

- [ ] **Step 1: Run code-quality and focused regression**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m compileall -q src/rag_eval scripts/evaluate_rag_full_chain.py
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests/test_rag_eval_contracts.py tests/test_rag_eval_inventory.py tests/test_rag_eval_sampling.py tests/test_rag_eval_client.py tests/test_rag_eval_deterministic.py tests/test_rag_eval_judge.py tests/test_rag_eval_scoring.py tests/test_rag_eval_reporting.py tests/test_rag_eval_runner.py tests/test_huiji_eval.py tests/test_multi_intent_voice_eval.py tests/test_query_plan.py tests/test_retrieval_budget.py tests/test_retriever.py tests/test_hybrid_retriever.py tests/test_huiji_media_registry.py tests/test_voice_pagination.py tests/test_chain_assets.py tests/test_sse.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the complete repository test directory safely**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests -q
```

Expected: PASS. Use `tests` explicitly so pytest does not recurse into live Docker volume sockets under `infra/milvus/volumes`.

- [ ] **Step 3: Start and verify real services**

Use the existing runbook and current migrated MinIO/Milvus stack. Verify:

```powershell
curl.exe --noproxy "*" http://127.0.0.1:8000/health
curl.exe --noproxy "*" http://127.0.0.1:9002/minio/health/ready
```

Expected: backend reports the configured Huiji collection loaded; MinIO returns success. Do not rebuild an index or upload media to satisfy health.

- [ ] **Step 4: Verify independent judge configuration without exposing secrets**

```powershell
@'
import os
from config.config import get_config
cfg = get_config()
required = ("RAG_EVAL_JUDGE_BASE_URL", "RAG_EVAL_JUDGE_MODEL", "RAG_EVAL_JUDGE_API_KEY")
assert all(os.environ.get(name) for name in required), "judge env missing"
assert (os.environ["RAG_EVAL_JUDGE_BASE_URL"].rstrip("/"), os.environ["RAG_EVAL_JUDGE_MODEL"]) != (cfg.llm.base_url.rstrip("/"), cfg.llm.model)
print("judge configuration: distinct and present")
'@ | D:\Anaconda32024\envs\LangChain\python.exe -
```

Expected: prints only `judge configuration: distinct and present`.

- [ ] **Step 5: Run preflight and inspect the gate**

```powershell
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$EvidenceRoot = "eval/rag_full_chain/$RunStamp"
D:\Anaconda32024\envs\LangChain\python.exe scripts/evaluate_rag_full_chain.py preflight --base-url http://127.0.0.1:8000 --output "$EvidenceRoot/preflight.v1.json"
```

Expected: `allowed_to_run=true`, active collection exists and is loaded, artifact inventory is valid, judge is distinct, and a full primary-ID snapshot is present. If false, stop before the full run and use its M1 event.

- [ ] **Step 6: Run the full real-service evaluation**

```powershell
D:\Anaconda32024\envs\LangChain\python.exe scripts/evaluate_rag_full_chain.py run --base-url http://127.0.0.1:8000 --seed 1999 --output-root eval/rag_full_chain
```

Expected evidence:

- at least 48 unique cases with D1/D2/D3/D4 minima;
- at least 8 dynamically selected entities and every supported P0 intent covered;
- at least 10% repeat cases;
- all unique and repeat cases execute real production answers through SSE;
- at least 8 cases additionally execute synchronous `/ask` parity;
- all applicable voice pages are traversed;
- every answer is scored by the distinct judge;
- pre/post snapshot equality is exact.

Acceptable exit codes are `0` (`PASS/SEV-4`) or `3` (`SEV-3` with explicit warnings). Exit `1`, `2`, or `10` fails P0 acceptance and must not be relabeled as a pass.

- [ ] **Step 7: Perform the bounded adjudication review**

Review all `SEV-1/2` candidates, all deterministic/judge conflicts, and the deterministic 10% calibration sample in `adjudication_queue.v1.jsonl`. Record decisions in a separate `adjudication_results.v1.jsonl`; do not edit `case_results.v1.jsonl`.

Finalize the run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe scripts/evaluate_rag_full_chain.py finalize --run-dir <run-directory> --adjudication <run-directory>/adjudication_results.v1.jsonl
```

The command computes judge/human agreement. Required: `>= 85%`. If below, M3 remains at most `SEV-2`; calibrate the judge prompt/model and rerun the whole M3 sample, not only the disagreements. The automatic report remains immutable and the final report records its SHA-256 predecessor.

- [ ] **Step 8: Check genericity and read-only behavior**

```powershell
rg -n "EXPECTED_(ENTITY|ROLE|SKILL_COUNT|VOICE_COUNT|LANGUAGE_COUNT)|expected_(entity|role|skill_count|voice_count|language_count)\s*=\s*[0-9]+|char:[0-9]+" src/rag_eval scripts/evaluate_rag_full_chain.py tests -g 'test_rag_eval_*.py'
rg -n "insert\(|upsert\(|delete\(|drop_collection|create_collection|put_object|remove_object|DELETE FROM|UPDATE |INSERT INTO" src/rag_eval scripts/evaluate_rag_full_chain.py
```

Expected: no real-role sealing and no data-write operation. Synthetic test IDs may exist only in fixtures whose expectations derive from that fixture.

- [ ] **Step 9: Update the runbook**

Document:

- `scripts/evaluate_huiji_rag.py` as quick smoke evaluation;
- `scripts/evaluate_rag_full_chain.py run` as the P0 full-chain acceptance command;
- judge environment prerequisites;
- exit-code meanings;
- evidence directory layout;
- `PASS/SEV-4/SEV-3` acceptance and `SEV-2..0` rejection rules;
- focused rerun by failed module before repeating the complete run.

- [ ] **Step 10: Final mechanical self-check**

Verify the final module summary/report (or automatic pair when no adjudication is required) agree on run ID, global severity, acceptance, M1-M5 severities, sample counts, judge/human agreement, and snapshot equality. Verify every P0 spec ID appears in the report's machine-readable coverage map.

**Task acceptance:** The real P0 run produces auditable evidence, classifies the current system at one level, localizes defects to M1-M5, and meets the approved acceptance rules without data mutation.

---

## 12. Optional P1 Tasks

These are not part of P0 execution. Consider them only after Task 9 passes:

- dependency image/model revision capture and trend comparison;
- BM25/dense/reranker ablation reports;
- claim-level unsupported-span highlighting;
- sampled media HEAD/GET playback checks;
- trace-stage latency breakdown and small concurrency curves.

No P1 task may be used to delay or redefine a failed P0 gate.

## 13. Deferred / Out of Scope

- online shadow traffic and continuous drift monitoring;
- dashboard or evaluation management UI;
- user-feedback-derived qrels;
- long-term curated human gold corpus;
- continuous load testing and SLO burn-rate alerts;
- voice skin filtering before reliable skin annotations exist;
- automatic Milvus rebuild, MinIO repair, artifact rewrite, or production remediation.

## 14. Completion Self-Check

- [ ] `READY-P0-01`: backend, Milvus, MinIO, answer model, and judge are reachable.
- [ ] `READY-P0-02`: artifacts and references pass read-only integrity checks.
- [ ] `READY-P0-03`: full primary-key pre/post snapshots are exactly equal.
- [ ] `READY-P0-04`: run/model/config/build/seed/timestamps are recorded.
- [ ] `RETR-P0-01`: entity and complete intent set are evaluated.
- [ ] `RETR-P0-02`: every requested intent is consumed downstream.
- [ ] `RETR-P0-03`: Recall@K, MRR, nDCG, coverage, and shortfall are reported.
- [ ] `RETR-P0-04`: cross-entity leakage is zero; no-source behavior is truthful.
- [ ] `RETR-P0-05`: source/character budgets retain minimum intent coverage.
- [ ] `ANSWER-P0-01`: groundedness is evaluated against actual context.
- [ ] `ANSWER-P0-02`: relevance and task completion meet difficulty floors.
- [ ] `ANSWER-P0-03`: multi-intent completeness and insufficiency disclosure are checked.
- [ ] `ANSWER-P0-04`: citations exist and support claims.
- [ ] `ANSWER-P0-05`: refusal/free-supplement behavior is truthful.
- [ ] `ANSWER-P0-06`: distinct judge identity, temperature 0, schema, prompt version, and reasons are recorded.
- [ ] `MEDIA-P0-01`: media intent precision and voice auto-leak are checked.
- [ ] `MEDIA-P0-02`: entity/parent/child/event binding is exact.
- [ ] `MEDIA-P0-03`: all voice pages equal the dynamic artifact set without duplicates.
- [ ] `MEDIA-P0-04`: local-path and unsafe-URL leakage is zero.
- [ ] `MEDIA-P0-05`: sync/SSE outputs are semantically equivalent.
- [ ] `RELY-P0-01`: request success rate is at least 98%.
- [ ] `RELY-P0-02`: repeated routing, sources, media, and conclusions are stable.
- [ ] `RELY-P0-03`: retrieval, TTFT, and total P95 meet fixed limits.
- [ ] `RELY-P0-04`: external failures are structured and never masquerade as grounded answers.
- [ ] Sample manifest has 48+ unique cases, D1/D2/D3/D4 minima, 8+ dynamic entities, all P0 intents, and 10% repeats.
- [ ] Judge/human calibration agreement is at least 85%.
- [ ] Global result is `PASS`, `SEV-4`, or explicitly recorded `SEV-3 accepted_with_warnings`.
- [ ] P1/P2 work did not enter P0 execution.
