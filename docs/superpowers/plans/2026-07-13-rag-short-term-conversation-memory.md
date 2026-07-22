# RAG Short-Term Conversation Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有单轮 RAG 增加单进程、6 轮、30 分钟 TTL 的短期会话记忆，使代词、section-only 追问、多意图追问和显式话题切换贯通 Planner、Retriever、回答生成、同步 API、SSE 与 React 主聊天页。

**Architecture:** 后端以独立 `ConversationMemoryStore` 持有有界内存状态，通过 per-conversation lease、generation 条件提交和 fail-open helper 同时服务 `/ask` 与 `/ask/stream`。`QueryPlanner` 在现有一次规划调用中消费结构化历史，`RAGChain` 用同一历史投影生成回答；React 只传随机 `conversation_id`，不上传消息数组。动态 evaluator 从当前 artifacts 选样，不写死角色或计数，并用真实 API、SSE、浏览器、重启和 pre/post inventory 完成硬验收。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、LangChain messages/prompts、asyncio、pytest、React 18、TypeScript、Zustand、Vitest、Playwright、内置 `sessionStorage` / `BroadcastChannel`、现有 `src.rag_eval`、Milvus/MinIO 只读证据工具。

**Approved Spec:** `docs/superpowers/specs/2026-07-13-rag-short-term-conversation-memory-design.md`

**Approved Spec SHA-256:** `0178f1f834906ba8a6b833d9963d26e9f1ce6e0b8b498c248eb5e49836b6563a`

**Review Standard:** `docs/specs-and-plans-review-guide.md`

**Status:** Ready for implementation after final plan review

## Global Constraints

- 只实施 spec P0；P1/P2 不得进入任务，包括 Redis/MySQL/SQLite、长期摘要、多 worker、账户历史、HTML/Streamlit/Gradio 适配。
- 固定默认值：最多 6 轮、TTL 30 分钟、最多 4096 会话、每会话存储投影 16000 code points、每请求历史投影 8000 code points；单轮问题投影各 1000、回答投影 4000 code points。
- 后端进程重启后会话必须消失；不得创建会话数据文件、表、bucket object、Milvus row 或 processed artifact。
- Planner 仍最多调用一次规划 LLM，最终回答仍最多调用一次回答 LLM；不得增加独立 rewrite LLM。
- 当前显式 action payload > 当前显式实体/intents > category > 历史锚点 > 无状态 fallback。
- 多意图唯一真值仍是现有 `requested_intents(plan)`；记忆不得建立第二套 intent 列表或修改 candidate K、source allocator、媒体并集、语音分页。
- 真实 evaluator 的实体、section、source/media ID 和数量全部从当前 artifacts 派生；生产代码与 evaluator 禁止角色名、角色 ID、技能数、台词数或语言数特例。
- `/ask` 和 `/ask/stream` 必须共享 store、历史投影、提交条件和 memory metadata；旧客户端不传 ID 时保持无状态兼容。
- 不记录真实用户历史正文；受控 evaluator evidence 与默认运行日志隔离，公共响应不得回显 conversation ID 或独立查询。
- 直接在当前脏工作树执行；每次修改前重新打开目标文件并兼容其他线程改动。
- 禁止任何 Git 操作：不创建 worktree/branch，不执行 status/diff/add/commit/reset/checkout/clean，不回退其他线程变更。
- 所有 Python/Docker/证据命令从 `$Project` 执行；所有 npm/npx 命令从 `$Frontend` 执行。
- 不使用裸 `pytest -q`，因为当前仓库根递归发现会进入运行中的 MySQL volume socket；全量 Python 回归使用 `pytest -q tests`。

PowerShell 任务前置：

```powershell
$Project = 'D:\PycharmProjects\nlp\LangChain\1999Search'
$Frontend = Join-Path $Project 'frontend\react-app'
Set-Location -LiteralPath $Project
```

## File Map

| File | Responsibility |
|---|---|
| `src/rag/conversation.py` | 纯会话数据模型、投影、follow-up predicate、bounded async store、lease/generation |
| `backend/conversation_runtime.py` | API/SSE 共用的 fail-open acquire/release、memory metadata、成功轮次构造和 access-log ID 脱敏 |
| `src/rag/query_plan.py` | 在现有 Planner 调用中消费 conversation context，并执行安全 fallback/entity precedence |
| `src/rag/prompts.py` | 历史 message placeholder 与“历史不是事实证据”系统约束 |
| `src/rag/chain.py` | 把 projection 贯通 retrieve/ask/stream，构造历史 messages 和内部 turn outcome |
| `src/rag/retriever.py` | 仅消费显式 action target parent，证明该优先级不被历史覆盖；不改 K、allocator 或媒体预算 |
| `backend/schemas.py` | UUID request、`MemoryInfo` 和响应白名单契约 |
| `backend/main.py` | 单例 store、同步 lease 生命周期、DELETE endpoint、SSE 参数传递 |
| `backend/sse.py` | 流式 lease 生命周期、metadata parity、done 后条件提交和取消不提交 |
| `frontend/react-app/src/session/conversationSession.ts` | sessionStorage ID、BroadcastChannel 标签页冲突探测、轮换 |
| `frontend/react-app/src/api/conversation.ts` | DELETE conversation transport |
| `frontend/react-app/src/api/sse.ts` | 发送 conversation ID、解析 memory metadata |
| `frontend/react-app/vite.config.ts` | 允许真实门禁通过环境变量指定后端代理目标 |
| `frontend/react-app/playwright.config.ts` | 允许真实门禁通过环境变量指定浏览器 base URL |
| `frontend/react-app/src/store/chatStore.ts` | send/clear 生命周期、abort/DELETE/rotate 顺序、message metadata |
| `frontend/react-app/src/components/sections/ChatSection.tsx` | `Trash2` 清空图标按钮 |
| `src/rag_eval/conversation.py` | 动态多轮轨迹、隔离/切换/多意图确定性检查 |
| `src/rag_eval/client.py` | evaluator conversation ID、DELETE 和 SSE cancel transport |
| `scripts/verify_rag_conversation_memory.py` | 真实 API/SSE、重启、pre/post snapshot 和 canonical evidence CLI |
| `frontend/react-app/e2e/conversation-memory.spec.ts` | 刷新、清空、复制标签页和真实多轮浏览器门禁 |

## P0 Coverage Matrix

| Spec IDs | Implementation | Automated test | Real gate | Blocking failure |
|---|---|---|---|---|
| `MEMORY-P0-01..12` | Tasks 1, 2, 5, 6; `conversation.py`, API/SSE runtime | `test_conversation_memory.py`, `test_conversation_api.py`, `test_sse.py` | Tasks 10, 12 restart, cancellation, capacity and pre/post evidence | persistence, stale commit, cross-session wait, unbounded capacity, or memory error blocking RAG |
| `CONTEXT-P0-01..12` | Tasks 3, 4; Planner and chain projection | `test_query_plan.py`, prompt/chain regressions | Dynamic follow-up, multi-intent, switch and full-chain tracks | wrong entity, lost explicit intent, extra LLM call, K/media/budget drift, or leaked independent query |
| `ANSWER-MEM-P0-01..08` | Task 4; prompt and chain history messages | `test_prompts.py`, `test_chain_assets.py`, `test_rag_empty_recovery.py` | Sync/SSE parity plus groundedness gate | history becomes fact/source authority, role corruption, or empty-retrieval bypass |
| `API-MEM-P0-01..11` | Tasks 5, 6; schema, shared store, DELETE, commit boundary | `test_conversation_api.py`, `test_sse.py` | Real `/ask`, `/ask/stream`, cancel, clear and sanitizer checks | schema drift, sources/done mismatch, partial commit, 5xx on memory failure, or sensitive metadata |
| `CHAT-MEM-P0-01..10` | Tasks 7, 8; session identity, transport, Zustand, `Trash2` | Vitest session/API/store/component suites | Task 11 refresh, duplicate-tab and clear Playwright tracks | copied ID collision, missing ID, wrong clear order, inaccessible control, or messages sent as history |
| `SAFETY-MEM-P0-01..06` | Tasks 1, 2, 5, 6, 7, 9, 10, 12 | isolation, sanitizer, evidence-safety tests | Interleaved real IDs and protected-store comparisons | any transcript/path/credential leak, cross-session data, or protected-store write |
| `EVAL-MEM-P0-01..12` | Tasks 1 through 10 | all focused Python/Vitest suites | Task 12 real verifier and existing full-chain run | skipped P0 case, fixed role/count expectation, or single-turn-only proof |
| `GATE-MEM-P0-01..11` | Tasks 9 through 12 | evaluator/verifier/Playwright tests | Current-artifact dynamic tracks, restart, full-chain and inventories | fewer than two eligible entities, any SEV-1/SEV-2, persistence, storage drift, or M2-M5 regression |

---

### Task 0: Freeze Read-Only Baseline and Existing Test State

**Files:**
- Read: `docs/superpowers/specs/2026-07-13-rag-short-term-conversation-memory-design.md`
- Read: all files in the File Map before their task edits
- Evidence: `eval/rag_conversation_memory/pre-implementation/**`

**Interfaces:**
- Consumes: current running Milvus `reverse1999_rag`, collection `text_child_bge_m3_v3`; current MinIO `reverse1999-assets/reverse1999`
- Produces: immutable pre-implementation Milvus/MinIO/artifact inventories and baseline test output used by Task 12

- [ ] **Step 1: Create a unique evidence directory without overwriting prior evidence**

```powershell
$Project = 'D:\PycharmProjects\nlp\LangChain\1999Search'
Set-Location -LiteralPath $Project
$Spec = Join-Path $Project 'docs\superpowers\specs\2026-07-13-rag-short-term-conversation-memory-design.md'
$SpecHash = (Get-FileHash -LiteralPath $Spec -Algorithm SHA256).Hash.ToLowerInvariant()
if ($SpecHash -ne '0178f1f834906ba8a6b833d9963d26e9f1ce6e0b8b498c248eb5e49836b6563a') { throw "Approved spec drifted: $SpecHash" }
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$Evidence = Join-Path $Project "eval\rag_conversation_memory\pre-implementation\$RunId"
if (Test-Path -LiteralPath $Evidence) { throw "Evidence path already exists: $Evidence" }
New-Item -ItemType Directory -Path $Evidence | Out-Null
$Evidence | Set-Content -LiteralPath (Join-Path $Project 'eval\rag_conversation_memory\latest-pre-implementation-path.txt') -Encoding UTF8
```

Expected: a new empty timestamped directory; no production service is stopped.

- [ ] **Step 2: Capture Milvus and MinIO read-only inventories**

```powershell
$env:MINIO_ACCESS_KEY = if ($env:MINIO_ACCESS_KEY) { $env:MINIO_ACCESS_KEY } else { [Environment]::GetEnvironmentVariable('MINIO_ACCESS_KEY', 'User') }
$env:MINIO_SECRET_KEY = if ($env:MINIO_SECRET_KEY) { $env:MINIO_SECRET_KEY } else { [Environment]::GetEnvironmentVariable('MINIO_SECRET_KEY', 'User') }
if (-not $env:MINIO_ACCESS_KEY -or -not $env:MINIO_SECRET_KEY) { throw 'MinIO inventory credentials are unavailable' }
python scripts/minio_blue_green_evidence.py milvus-inventory `
  --endpoint http://127.0.0.1:19600 `
  --database reverse1999_rag `
  --output (Join-Path $Evidence 'milvus.pre.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Milvus baseline inventory failed with exit code $LASTEXITCODE" }
python scripts/minio_blue_green_evidence.py object-inventory `
  --endpoint 127.0.0.1:9002 `
  --bucket reverse1999-assets `
  --prefix reverse1999 `
  --access-key-env MINIO_ACCESS_KEY `
  --secret-key-env MINIO_SECRET_KEY `
  --output (Join-Path $Evidence 'minio.pre.v1.json')
if ($LASTEXITCODE -ne 0) { throw "MinIO baseline inventory failed with exit code $LASTEXITCODE" }
```

Expected: both commands exit 0; this task performs no create/update/delete request.

- [ ] **Step 3: Hash current RAG artifacts**

```powershell
$ArtifactRoot = Join-Path $Project 'data\processed\huiji\dev'
$ArtifactNames = @('parent_blocks.jsonl','child_blocks.jsonl','media_assets.jsonl','build_manifest.json')
$ArtifactHashes = foreach ($Name in $ArtifactNames) {
  $Path = Join-Path $ArtifactRoot $Name
  if (-not (Test-Path -LiteralPath $Path)) { throw "Missing artifact: $Path" }
  $Hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
  [ordered]@{ name = $Name; length = (Get-Item -LiteralPath $Path).Length; sha256 = $Hash.Hash.ToLowerInvariant() }
}
$ArtifactHashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $Evidence 'artifacts.pre.v1.json') -Encoding UTF8
```

Expected: four records with non-empty SHA-256 values.

- [ ] **Step 4: Run the current touched-area baseline tests before code edits**

```powershell
$Baseline = Join-Path $Evidence 'baseline-tests.txt'
Set-Location -LiteralPath $Project
pytest -q tests/test_query_plan.py tests/test_prompts.py tests/test_chain_assets.py tests/test_sse.py 2>&1 | Tee-Object -LiteralPath $Baseline
$PythonExit = $LASTEXITCODE
Set-Location -LiteralPath $Frontend
npm test -- --run src/api/sse.test.ts src/store/chatStore.test.ts src/components/sections/ChatSection.test.tsx 2>&1 | Tee-Object -LiteralPath $Baseline -Append
$FrontendExit = $LASTEXITCODE
"python_exit=$PythonExit" | Add-Content -LiteralPath $Baseline -Encoding UTF8
"frontend_exit=$FrontendExit" | Add-Content -LiteralPath $Baseline -Encoding UTF8
if ($PythonExit -ne 0 -or $FrontendExit -ne 0) { throw "Touched-area baseline failed; inspect $Baseline" }
```

Expected: record exact baseline pass/fail counts in `$Evidence/baseline-tests.txt`. A touched-area failure must be diagnosed before implementation; an unrelated existing failure outside these files does not authorize changing its behavior.

**Review gate:** verify the evidence path is outside production data roots, inventory commands were read-only, and no application code changed.

---

### Task 1: Define Pure Conversation Contracts, Projection, and Follow-Up Rules

**Files:**
- Create: `src/rag/conversation.py`
- Create: `tests/test_conversation_memory.py`

**Interfaces:**
- Produces: `ConversationTurn`, `ConversationProjection`, `ConversationLease`, `MemoryStatus`, `RewriteMode`, `GroundingMode`, `EMPTY_PROJECTION`, `build_conversation_turn()`, `project_turns()`, `is_contextual_follow_up()`, `category_accepts_entity()`
- Consumes: no FastAPI, LLM, Retriever, filesystem, database, or network dependencies

- [ ] **Step 1: Write failing pure-contract tests**

```python
from datetime import datetime, timezone

from src.rag.conversation import (
    ConversationTurn,
    build_conversation_turn,
    category_accepts_entity,
    is_contextual_follow_up,
    project_turns,
)


def _turn(index: int, *, entity: str = "角色甲", answer_size: int = 8) -> ConversationTurn:
    return build_conversation_turn(
        original_question=f"问题{index}",
        standalone_question=f"{entity} 问题{index}",
        answer="答" * answer_size,
        entity=entity,
        entity_type="character",
        requested_intents=("skill",),
        category="人物",
        grounding_mode="grounded",
        completed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
    )


def test_projection_keeps_at_most_six_recent_complete_turns_and_8000_chars():
    projection = project_turns([_turn(i, answer_size=3000) for i in range(8)])
    assert len(projection.turns) <= 6
    assert projection.code_points <= 8000
    assert projection.turns[-1].original_question == "问题7"


def test_planner_payload_never_contains_assistant_answers():
    projection = project_turns([_turn(1)])
    payload = projection.planner_payload()
    assert "answer" not in str(payload)
    assert payload["last_entity"] == "角色甲"


def test_follow_up_and_category_rules_are_explicit():
    assert is_contextual_follow_up("她的技能和语音呢") is True
    assert is_contextual_follow_up("技能呢") is True
    assert is_contextual_follow_up("请继续详细说") is True
    assert is_contextual_follow_up("一个没有回指的新问题") is False
    assert category_accepts_entity("人物", "character") is True
    assert category_accepts_entity("心相", "character") is False
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_conversation_memory.py`

Expected: FAIL during import because `src.rag.conversation` does not exist.

- [ ] **Step 3: Implement immutable data contracts and deterministic projection**

```python
GroundingMode = Literal["grounded", "ungrounded"]
MemoryStatus = Literal["disabled", "new", "hit", "expired"]
RewriteMode = Literal["none", "planner", "fallback"]

MAX_TURNS = 6
TTL_SECONDS = 30 * 60
MAX_SESSIONS = 4096
MAX_STORED_CODE_POINTS = 16_000
MAX_PROJECTED_CODE_POINTS = 8_000
MAX_QUESTION_CODE_POINTS = 1_000
MAX_ANSWER_CODE_POINTS = 4_000
TRUNCATION_MARKER = "\n[truncated]"

@dataclass(frozen=True)
class ConversationTurn:
    original_question: str
    standalone_question: str
    answer: str
    entity: str | None
    entity_type: str | None
    requested_intents: tuple[str, ...]
    category: str | None
    grounding_mode: GroundingMode
    completed_at: datetime

@dataclass(frozen=True)
class ConversationProjection:
    turns: tuple[ConversationTurn, ...] = ()
    code_points: int = 0

    @property
    def last_entity(self) -> str | None:
        for turn in reversed(self.turns):
            if turn.entity and turn.entity_type:
                return turn.entity
        return None

    @property
    def last_entity_type(self) -> str | None:
        for turn in reversed(self.turns):
            if turn.entity and turn.entity_type:
                return turn.entity_type
        return None

    def planner_payload(self) -> dict[str, object]:
        return {
            "turns": [
                {
                    "original_question": turn.original_question,
                    "standalone_question": turn.standalone_question,
                    "requested_intents": list(turn.requested_intents),
                    "category": turn.category,
                }
                for turn in self.turns
            ],
            "last_entity": self.last_entity,
            "last_entity_type": self.last_entity_type,
        }

EMPTY_PROJECTION = ConversationProjection()
```

Implementation rules:

```text
1. Truncate each field on the right and include TRUNCATION_MARKER inside its limit.
2. Store requested_intents as ordered unique strings.
3. project_turns scans newest to oldest until adding a complete stored turn would exceed 8000, then restores chronological order.
4. last_entity scans newest to oldest and only accepts non-empty structured entity + entity_type.
5. planner_payload includes recent questions, standalone questions, requested intents and last structured entity, never answer text.
6. is_contextual_follow_up implements the spec predicate, including <=40-code-point explicit back-reference phrases.
7. category_accepts_entity allows category None and exact character <-> 人物 only; unknown entity types require category None.
```

- [ ] **Step 4: Run pure tests and verify GREEN**

Run: `pytest -q tests/test_conversation_memory.py`

Expected: PASS with no filesystem or network access.

- [ ] **Step 5: Add boundary tests for per-field and per-session truncation**

Add exact assertions for 1000/1000/4000 field limits, 16000 stored projection eviction, ordered intents, Unicode code point counting, and `ungrounded` retention without answer use in `planner_payload()`.

Run: `pytest -q tests/test_conversation_memory.py`

Expected: PASS.

**Review gate:** contract names and literals must exactly match the spec; no storage or LangChain import is allowed in this task.

---

### Task 2: Implement Bounded Async Store, Lease Isolation, TTL, LRU, and Generation CAS

**Files:**
- Modify: `src/rag/conversation.py`
- Modify: `tests/test_conversation_memory.py`

**Interfaces:**
- Consumes: Task 1 contracts and constants
- Produces:

- `ConversationMemoryStore.acquire(conversation_id: UUID | None) -> ConversationLease`
- `ConversationMemoryStore.release(lease: ConversationLease, turn: ConversationTurn | None = None) -> bool`
- `ConversationMemoryStore.clear(conversation_id: UUID) -> None`

- [ ] **Step 1: Write failing TTL, CAS, isolation, LRU, and concurrency tests**

```python
def test_clear_invalidates_an_inflight_lease_before_release():
    async def scenario():
        clock = FakeClock()
        store = ConversationMemoryStore(clock=clock)
        conversation_id = UUID("00000000-0000-4000-8000-000000000001")
        lease = await store.acquire(conversation_id)
        await store.clear(conversation_id)
        committed = await store.release(lease, _turn(1))
        next_lease = await store.acquire(conversation_id)
        try:
            assert committed is False
            assert next_lease.projection.turns == ()
        finally:
            await store.release(next_lease)
    asyncio.run(scenario())


def test_same_conversation_serializes_while_distinct_conversations_run_in_parallel():
    asyncio.run(_assert_same_id_waits_while_other_id_completes())


def test_ttl_and_capacity_do_not_evict_active_leases():
    asyncio.run(_assert_active_lease_survives_ttl_and_capacity_pressure())
```

Define `_assert_same_id_waits_while_other_id_completes()` to hold lease A1, start A2 in an `asyncio.Task`, require A2 to remain pending for one event-loop turn, acquire B1 with `asyncio.wait_for(store.acquire(B_ID), timeout=0.1)`, release B1, release A1, and then require A2 to complete. Define `_assert_active_lease_survives_ttl_and_capacity_pressure()` with `FakeClock`, `max_sessions=2`, one held lease, a 1801-second clock advance, and two other IDs; require the held entry to remain committable and only inactive entries to be evicted.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `pytest -q tests/test_conversation_memory.py`

Expected: FAIL because store methods and lease internals are absent.

- [ ] **Step 3: Implement store entry and lease lifecycle**

Implement `_Entry` with `generation`, `deque[ConversationTurn]`, `last_accessed`, `asyncio.Lock`, `active_leases`, and `invalidated_reason`. Implement `ConversationLease` with `conversation_id`, `expected_generation`, `projection`, `status`, private entry identity, and an idempotent released flag. `ConversationLease.disabled()` must return a released-safe lease with `conversation_id=None`, generation `-1`, `EMPTY_PROJECTION`, status `disabled`, and no entry. `ConversationMemoryStore.__init__()` must accept injectable monotonic `clock` and `max_sessions`, create the UUID-to-entry dictionary, and create one global `asyncio.Lock` guard.

Required lock order and behavior:

```text
1. Under _guard, reserve/increment active_leases before awaiting entry.lock so LRU cannot evict a waiter.
2. Acquire entry.lock outside _guard; then re-enter _guard to evaluate TTL and snapshot current turns.
3. clear increments generation under _guard immediately, before waiting for entry.lock; this invalidates an in-flight expected_generation.
4. release only appends when entry identity and generation both match, then enforces 6-turn and 16000-code-point limits.
5. release is idempotent and always releases entry.lock/decrements active_leases exactly once.
6. LRU only removes inactive entries; expired/tombstone entries are preferred. If every slot is active, acquire returns a disabled lease.
7. clear on an unknown UUID returns without creating an entry; clear on an inactive entry removes it; clear on an active entry increments generation immediately and retains only a tombstone until every reserved/active lease releases.
8. An expired acquire drops old turns, increments generation, returns an empty projection with status expired, and remains eligible to commit the new completed turn.
9. No method opens files, imports database clients, or logs question/answer text.
```

- [ ] **Step 4: Run store tests and verify GREEN**

Run: `pytest -q tests/test_conversation_memory.py`

Expected: PASS.

- [ ] **Step 5: Run a deterministic 4096-session and failure-release stress test**

Add a test that acquires/releases 4097 UUIDs with `max_sessions=4096`, verifies oldest inactive eviction, then raises inside simulated request handling and calls `release(lease, turn=None)` to prove the lock is reusable.

Run: `pytest -q tests/test_conversation_memory.py`

Expected: PASS without sleeps longer than a scheduler tick.

**Review gate:** inspect every exit path for one release, no lock-order inversion, no unbounded dictionary/deque, and no stale generation commit.

---

### Task 3: Make Query Planner Context-Aware Without Adding an LLM Call

**Files:**
- Modify: `src/rag/query_plan.py`
- Modify: `tests/test_query_plan.py`

**Interfaces:**
- Consumes: `ConversationProjection`, `EMPTY_PROJECTION`, `is_contextual_follow_up()`, `category_accepts_entity()`
- Produces:

- Add `QueryPlan.context_rewrite_mode: Literal["none", "planner", "fallback"]` with default `"none"`.
- Add `QueryPlan.target_parent_id: str | None` with default `None`; Planner/history leave it unset and only explicit action handling may populate it.
- Extend `QueryPlanner.plan` with `conversation: ConversationProjection | None = None` after `category` and preserve its `QueryPlan` return type.

- [ ] **Step 1: Write failing Planner context tests**

```python
def test_planner_receives_context_but_preserves_current_explicit_multi_intents():
    llm = CountingLLM(_minimal_payload("voice", entity="角色甲"))
    projection = project_turns([_completed_turn(entity="角色甲", intents=("intro",))])
    plan = QueryPlanner(llm, entity_lexicon=_lexicon("角色甲", "角色乙")).plan(
        "她的技能和语音呢", category="人物", conversation=projection
    )
    assert llm.call_count == 1
    assert plan.entity == "角色甲"
    assert requested_intents(plan) == ("skill", "voice")
    assert plan.context_rewrite_mode == "planner"


def test_explicit_new_entity_overrides_history():
    projection = project_turns([_completed_turn(entity="角色甲")])
    plan = QueryPlanner(_FakeLLM(_minimal_payload("skill", entity="角色甲")), _lexicon("角色甲", "角色乙")).plan(
        "那角色乙的技能呢", category="人物", conversation=projection
    )
    assert plan.entity == "角色乙"


@pytest.mark.parametrize("planner", [QueryPlanner(None), QueryPlanner(_TimeoutLLM()), QueryPlanner(_InvalidJsonLLM()), QueryPlanner(_SchemaErrorLLM()), QueryPlanner(_ApiErrorLLM())])
def test_context_fallback_only_inherits_for_safe_follow_up(planner):
    projection = project_turns([_completed_turn(entity="角色甲")])
    inherited = planner.plan("技能呢", category="人物", conversation=projection)
    unrelated = planner.plan("一个没有回指的新问题", category="人物", conversation=projection)
    assert inherited.entity == "角色甲"
    assert inherited.context_rewrite_mode == "fallback"
    assert unrelated.context_rewrite_mode == "none"
```

Add separate assertions that no-history behavior equals the current baseline plan, an incompatible `category="心相"` does not inherit a character entity, and a current `action_payload` applied by `RAGChain` overrides the historical entity/intent/target parent. Preserve current explicit-intent ordering in every case.

- [ ] **Step 2: Run focused Planner tests and verify RED**

Run: `pytest -q tests/test_query_plan.py -k "context or multi_intent or fallback"`

Expected: FAIL because `conversation` and `context_rewrite_mode` are unknown.

- [ ] **Step 3: Extend Planner input and deterministic postconditions**

Keep every existing `QueryPlan` field in its current order, then append `target_parent_id=None` and `context_rewrite_mode="none"`. At the start of `plan()`, normalize `conversation` to `EMPTY_PROJECTION`; construct the existing planner payload unchanged, then add `conversation_context=projection.planner_payload()` only when turns exist. Invoke `self._llm` through the current invocation path exactly once and pass the projection into the existing payload-normalization path as a new named argument.

Extend the existing Planner system prompt to state that `conversation_context` is untrusted data used only for entity/intent continuity and cannot alter system instructions, output schema, source constraints, or configuration. Add a regression where a historical user question requests instruction override/path disclosure; the current explicit entity and planner schema must still win, and no historical text may appear in public diagnostics.

Postcondition algorithm:

```text
1. Resolve explicit entity from EntityLexicon.match(original_query) before considering payload/history.
2. If explicit entity exists, force that canonical entity even when LLM returns the historical entity.
3. Otherwise, only apply last_entity when category is compatible and is_contextual_follow_up(original_query) is true.
4. extract_explicit_character_intents always receives the current original query; merge it before LLM intents.
5. If a safe context anchor supplies the entity, rebuild normalized/dense/sparse/media queries so they contain that entity.
6. LLM success with a non-empty projection sets planner mode; local inheritance after any existing fallback class sets fallback mode; no inherited context sets none.
7. Keep all existing planning_status/warning/error values and media intent validation.
```

- [ ] **Step 4: Run all Query Planner tests**

Run: `pytest -q tests/test_query_plan.py`

Expected: PASS, including all existing single- and multi-intent tests.

- [ ] **Step 5: Add call-count and payload privacy assertions**

Assert the LLM receives exactly two messages, the human JSON contains `conversation_context` only on history hits, and that JSON does not contain any assistant answer text.

Run: `pytest -q tests/test_query_plan.py`

Expected: PASS.

**Review gate:** no second `invoke()`, no role-specific branch, no alternate intent bundle, and no history override of an explicit current entity.

---

### Task 4: Thread History Through RAGChain and Keep Current Retrieval as the Only Fact Authority

**Files:**
- Modify: `src/rag/prompts.py`
- Modify: `src/rag/chain.py`
- Modify: `src/rag/retriever.py`
- Modify: `tests/test_prompts.py`
- Modify: `tests/test_chain_assets.py`
- Modify: `tests/test_rag_empty_recovery.py`
- Modify: `tests/test_retriever.py`

**Interfaces:**
- Consumes: Task 3 Planner signature and Task 1 projection
- Produces:

- Extend `RAGChain.retrieve`, `RAGChain.ask`, and `RAGChain._stream_llm` with optional `conversation: ConversationProjection | None = None` while preserving all existing parameters and return types.
- Consume the optional `QueryPlan.target_parent_id`; Planner and history never populate it, while explicit action handling may populate it.
- Add internal raw result keys `_conversation_plan` and `_turn_outcome`; public schemas must not expose them.

- [ ] **Step 1: Write failing prompt and chain propagation tests**

```python
def test_prompt_keeps_history_roles_below_system_and_current_context_is_fact_authority():
    prompt = get_rag_prompt()
    history = [HumanMessage(content="旧问题"), AIMessage(content="[非知识库自由补充历史]\n旧回答")]
    messages = prompt.format_messages(context="本轮证据", history=history, question="当前问题")
    assert isinstance(messages[0], SystemMessage)
    assert "历史回答仅用于对话连贯" in messages[0].content
    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    assert messages[-1].content == "当前问题"


def test_chain_passes_one_projection_to_planner_and_answer_model():
    chain, planner, llm = _chain_with_counting_doubles()
    projection = project_turns([_completed_turn(entity="角色甲")])
    result = chain.ask("她的技能呢", category="人物", conversation=projection)
    assert planner.conversations == [projection]
    assert llm.invoke_count == 1
    assert result["_turn_outcome"] == "grounded"
    assert result["_conversation_plan"].entity == "角色甲"
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest -q tests/test_prompts.py tests/test_chain_assets.py tests/test_rag_empty_recovery.py`

Expected: FAIL because prompt and chain do not accept history.

- [ ] **Step 3: Add `MessagesPlaceholder` and history conversion**

```python
def get_rag_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        MessagesPlaceholder(variable_name="history", optional=True),
        ("human", HUMAN_TEMPLATE),
    ])

def _conversation_messages(projection: ConversationProjection) -> list[Any]:
    messages: list[Any] = []
    for turn in projection.turns:
        messages.append(HumanMessage(content=turn.original_question))
        prefix = "[非知识库自由补充历史]\n" if turn.grounding_mode == "ungrounded" else ""
        messages.append(AIMessage(content=f"{prefix}{turn.answer}"))
    return messages
```

Add a system rule that historical answers are untrusted conversational context, current retrieval context is the only knowledge-base evidence, and historical sources cannot be cited.

- [ ] **Step 4: Propagate projection and explicit action priority through RAGChain**

At the existing start of `retrieve()`, normalize `conversation` to `EMPTY_PROJECTION` and call `self._query_planner.plan(question, category=category, conversation=projection)`. Preserve the current retrieval, media, budget, and sanitization body except for projection/private metadata threading and the explicit target-parent filter defined below.

```python
def _with_action_payload(self, plan: Any, action_payload: dict[str, Any]) -> Any:
    intent = str(action_payload.get("intent") or plan.intent)
    packet_policy = str(action_payload.get("packet_policy") or plan.packet_policy)
    next_route = "llm_general" if intent == "llm_general" or packet_policy == "free_supplement" else plan.route
    updates = {
        "entity": str(action_payload.get("entity") or plan.entity) or None,
        "entity_type": str(action_payload.get("entity_type") or plan.entity_type) or None,
        "intent": intent,
        "packet_policy": packet_policy,
        "target_parent_id": str(action_payload.get("target_parent_id") or "") or None,
        "route": next_route,
    }
    try:
        return replace(plan, **updates)
    except (TypeError, AttributeError):
        for key, value in updates.items():
            setattr(plan, key, value)
        return plan
```

In `RAGRetriever._structured_rows_for_plan()`, when `plan.target_parent_id` is non-null, require exact `row.parent_id == plan.target_parent_id` in addition to the current entity/type/policy checks. Add a regression where history points to entity A but an action payload names entity B and one parent under B; every returned structured source must use entity B and that parent. Do not alter `calculate_candidate_k`, `allocate_sources`, voice page size, context budget, or media attachment.

`ask()` and `_stream_llm()` must pass `_conversation_messages(projection)` to both grounded and free-supplement prompts. Add internal result metadata only:

```python
private_meta = {
    "_conversation_plan": retrieved["plan"],
    "_turn_outcome": turn_outcome,
}
```

`turn_outcome` must be exactly one of `grounded`, `ungrounded`, or `not_committable`.

Use `not_committable` for API key missing, empty retrieval, and any LLM error. These keys are consumed before public sanitization and never enter `AskResponse`.

- [ ] **Step 5: Run chain/prompt tests and all existing retrieval regressions**

```powershell
pytest -q tests/test_prompts.py tests/test_chain_assets.py tests/test_rag_empty_recovery.py tests/test_query_plan.py tests/test_retriever.py tests/test_retrieval_budget.py
```

Expected: PASS.

**Review gate:** history remains typed user/assistant messages, no historical context/source enters the current source list, and action payload/entity precedence is verified.

---

### Task 5: Add API Memory Schemas, Shared Runtime Helpers, Sync Commit, and Idempotent Clear

**Files:**
- Create: `backend/conversation_runtime.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Create: `tests/test_conversation_api.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: Task 2 store and Task 4 internal plan/outcome metadata
- Produces: optional `AskRequest.conversation_id`, `MemoryInfo`, `normalize_memory_info()`, `DELETE /conversations/{conversation_id}`, sync request lease lifecycle, Uvicorn conversation-path redaction filter

- [ ] **Step 1: Write failing schema and sync endpoint tests**

```python
def test_ask_request_accepts_uuid_and_rejects_invalid_id():
    valid = AskRequest.model_validate({"question": "q", "conversation_id": "00000000-0000-4000-8000-000000000001"})
    assert str(valid.conversation_id).endswith("0001")
    with pytest.raises(ValidationError):
        AskRequest.model_validate({"question": "q", "conversation_id": "not-a-uuid"})


def test_sync_ask_commits_only_after_valid_success_response(client_with_memory_chain):
    first = client_with_memory_chain.post("/ask", json={"question": "介绍角色甲", "conversation_id": CONVERSATION_ID})
    second = client_with_memory_chain.post("/ask", json={"question": "她的技能呢", "conversation_id": CONVERSATION_ID})
    assert first.json()["memory"] == {"status": "new", "turns_used": 0, "rewrite_mode": "none"}
    assert second.json()["memory"]["status"] == "hit"
    assert second.json()["memory"]["turns_used"] == 1


def test_delete_is_idempotent_and_invalidates_old_history(client_with_memory_chain):
    assert client_with_memory_chain.delete(f"/conversations/{CONVERSATION_ID}").status_code == 204
    assert client_with_memory_chain.delete(f"/conversations/{CONVERSATION_ID}").status_code == 204
```

In `tests/conftest.py`, define `CONVERSATION_ID = "00000000-0000-4000-8000-000000000001"` and a `client_with_memory_chain` fixture that replaces `_state["memory"]` with a fresh store and `_state["chain"]` with a deterministic double. The double must return a grounded answer, one sanitized source, a plan whose entity is `角色甲`, and `context_rewrite_mode="none"` on the first explicit turn; on a follow-up projection it must return the same entity and `context_rewrite_mode="planner"`. Restore both `_state` entries in fixture teardown.

- [ ] **Step 2: Run API tests and verify RED**

Run: `pytest -q tests/test_conversation_api.py`

Expected: FAIL because request/response memory contracts and endpoint do not exist.

- [ ] **Step 3: Implement explicit public schemas and whitelist normalization**

```python
class MemoryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["disabled", "new", "hit", "expired"]
    turns_used: int = Field(ge=0)
    rewrite_mode: Literal["none", "planner", "fallback"]

class AskRequest(BaseModel):
    question: str
    conversation_id: UUID | None = None
    category: str | None = None
    route_options: RouteOptions = Field(default_factory=RouteOptions)
    action_payload: ActionItem | None = None

class AskResponse(BaseModel):
    # existing fields
    memory: MemoryInfo = Field(default_factory=lambda: MemoryInfo(status="disabled", turns_used=0, rewrite_mode="none"))
```

`normalize_memory_info()` must construct `MemoryInfo` from explicit scalar fields; it must never pass arbitrary mappings through.

- [ ] **Step 4: Implement shared fail-open runtime helpers**

```python
async def acquire_lease(store: ConversationMemoryStore, conversation_id: UUID | None) -> ConversationLease:
    try:
        return await store.acquire(conversation_id)
    except Exception:
        return ConversationLease.disabled()

async def release_lease(store: ConversationMemoryStore, lease: ConversationLease, turn: ConversationTurn | None) -> bool:
    try:
        return await store.release(lease, turn)
    except Exception:
        return False

async def clear_memory(store: ConversationMemoryStore, conversation_id: UUID) -> bool:
    try:
        await store.clear(conversation_id)
        return True
    except Exception:
        return False

def memory_info_for(lease: ConversationLease, plan: object | None) -> MemoryInfo:
    return MemoryInfo(
        status=lease.status,
        turns_used=len(lease.projection.turns),
        rewrite_mode=getattr(plan, "context_rewrite_mode", "none"),
    )
```

The helper may log only exception class plus aggregate operation name; never conversation ID, question, answer, plan, or prompt.

In the same module, add `redact_conversation_path(path: str) -> str` and an idempotent `install_uvicorn_access_log_filter()`. Match only a canonical UUID immediately following `/conversations/`, replace it with `sha256:` plus the first 12 lowercase hex characters of SHA-256, preserve any query suffix, and mutate only Uvicorn's path argument. Unit-test a real `logging.LogRecord` shaped like `uvicorn.access`, require the digest to be stable, and require the raw UUID to be absent. Call the installer once from `backend/main.py`; do not disable unrelated access logs.

- [ ] **Step 5: Wire one store instance, sync lifecycle, and clear endpoint**

```python
_state = {
    "vs": None,
    "retriever": None,
    "chain": None,
    "memory": ConversationMemoryStore(),
    "loaded": False,
}

def _memory_store() -> ConversationMemoryStore:
    store = _state.get("memory")
    if not isinstance(store, ConversationMemoryStore):
        store = ConversationMemoryStore()
        _state["memory"] = store
    return store

@app.delete("/conversations/{conversation_id}", status_code=204)
async def clear_conversation(conversation_id: UUID) -> Response:
    await clear_memory(_memory_store(), conversation_id)
    return Response(status_code=204)
```

In `/ask`, acquire before calling chain, extract `_conversation_plan` and `_turn_outcome`, build and validate `AskResponse`, then create `ConversationTurn` only for grounded/ungrounded outcomes. Release in `finally`; because return executes after `finally`, commit occurs after schema validation and before response return.

- [ ] **Step 6: Prove fail-open, no-ID compatibility, no-commit branches, and no leakage**

Add tests for store acquire/release/clear exceptions, missing conversation ID, TTL-expired status, API-key missing, empty retrieval, LLM error, invalid response schema, ungrounded success, response sanitizer, access-log redaction, and absence of `conversation_id`, `_conversation_plan`, independent query, prompt, local paths, and answer history from `memory` and ordinary logs. A clear exception still returns 204 because the browser rotates away from the old ID.

Run: `pytest -q tests/test_conversation_api.py tests/test_sse.py`

Expected: PASS.

**Review gate:** one store per process, DELETE works while RAG is unavailable, response validates before commit, and no string comparison decides success.

---

### Task 6: Integrate the Same Lease and Commit Contract into SSE

**Files:**
- Modify: `backend/sse.py`
- Modify: `backend/main.py`
- Modify: `tests/test_sse.py`
- Modify: `tests/test_conversation_api.py`

**Interfaces:**
- Consumes: `backend.conversation_runtime` helpers and Task 4 chain projection signatures
- Produces: `rag_stream_generator` with optional `memory_store` and `conversation_id` parameters, sources/done memory parity, and post-done conditional commit

- [ ] **Step 1: Write failing streaming lifecycle tests**

```python
def test_sse_sources_and_done_have_identical_memory_metadata(client_with_memory_chain):
    events = _stream_events(client_with_memory_chain, "她的技能呢", CONVERSATION_ID)
    sources = next(data for event, data in events if event == "sources")
    done = next(data for event, data in events if event == "done")
    assert sources["memory"] == done["memory"]


def test_cancel_before_done_does_not_commit():
    async def scenario():
        store = ConversationMemoryStore()
        gen = rag_stream_generator(SlowChain(), "问题", None, memory_store=store, conversation_id=UUID(CONVERSATION_ID))
        async for block in gen:
            if block.startswith("event: token"):
                await gen.aclose()
                break
        lease = await store.acquire(UUID(CONVERSATION_ID))
        try:
            assert lease.projection.turns == ()
        finally:
            await store.release(lease)
    asyncio.run(scenario())
```

Add `_stream_events(client, question, conversation_id)` as a test-only parser that POSTs `/ask/stream`, splits SSE frames on blank lines, JSON-decodes every `data:` line, and returns ordered `(event_name, payload)` tuples. Add `SlowChain` as a deterministic async-stream double: retrieval returns one grounded source and a plan for `角色甲`; token generation yields one token, waits on a test-controlled `asyncio.Event`, then yields the final token. The cancellation test closes the generator before releasing that event.

- [ ] **Step 2: Run SSE tests and verify RED**

Run: `pytest -q tests/test_sse.py -k "memory or cancel or done"`

Expected: FAIL because generator does not acquire/release memory.

- [ ] **Step 3: Wrap the full generator in one lease lifecycle**

Extend the existing `rag_stream_generator` signature by appending `memory_store: ConversationMemoryStore | None = None` and `conversation_id: UUID | None = None`. Use the supplied process store; when it is absent, use `ConversationLease.disabled()` rather than allocating an unreachable temporary store. Acquire once before retrieval, pass `lease.projection` into `chain.retrieve()` and `_stream_llm()`, preserve the private plan before transport sanitization, derive one immutable `MemoryInfo`, and insert its serialized value into both `sources` and `done`. Initialize `completed_turn=None`; only after control resumes following `yield sse_event("done", done_payload)` may the generator call `build_conversation_turn()` with the original question, plan standalone query/entity/type/requested intents/category, complete answer, outcome-derived grounding mode, and current UTC time. In `finally`, call `release_lease(memory_store, lease, completed_turn)` only when `memory_store` is non-null; the disabled no-store path performs no release.

Exact branch rules:

```text
retrieval exception -> error, no turn
API key missing -> existing token/done fallback, no turn
empty sources without free supplement -> existing token/done fallback, no turn
LLM stream exception -> error, no turn
grounded full stream -> yield done, then construct grounded turn
free supplement full stream -> yield done, then construct ungrounded turn
GeneratorExit/CancelledError before resuming after done yield -> no turn
```

- [ ] **Step 4: Pass the process store and UUID from `/ask/stream`**

```python
gen = rag_stream_generator(
    chain,
    req.question,
    req.category,
    route_options=_model_to_dict(req.route_options),
    action_payload=_model_to_dict(req.action_payload) if req.action_payload else None,
    memory_store=_memory_store(),
    conversation_id=req.conversation_id,
)
```

- [ ] **Step 5: Add clear/commit race and sync/stream parity tests**

Test that `clear()` advances generation while a stream is active, old release returns false, subsequent request has no old turn, and `/ask` versus `/ask/stream` on separate fresh IDs returns the same memory status/entity/requested intents/source semantics.

Run: `pytest -q tests/test_sse.py tests/test_conversation_api.py`

Expected: PASS.

**Review gate:** plan is captured before sanitization, sources/done metadata is identical, partial tokens never commit, and the temporary no-ID path does not create an unreachable store entry.

---

### Task 7: Add Browser-Tab Conversation Identity and Transport Contracts

**Files:**
- Create: `frontend/react-app/src/session/conversationSession.ts`
- Create: `frontend/react-app/src/session/conversationSession.test.ts`
- Create: `frontend/react-app/src/api/conversation.ts`
- Create: `frontend/react-app/src/api/conversation.test.ts`
- Modify: `frontend/react-app/src/types/index.ts`
- Modify: `frontend/react-app/src/api/sse.ts`
- Modify: `frontend/react-app/src/api/sse.test.ts`

**Interfaces:**
- Produces: `MemoryInfo`, `ConversationSession`, singleton `conversationSession`, `clearConversation(id)`, optional final `conversationId` parameter to `streamAsk()`
- Consumes: backend UUID and memory wire schema from Task 5

- [ ] **Step 1: Write failing session identity and wire tests**

```typescript
it('reuses the same id after refresh-like reconstruction', async () => {
  const storage = new MemoryStorage()
  const first = new ConversationSession(storage, fakeChannels, () => UUID_A)
  expect(await first.ready()).toBe(UUID_A)
  first.close()
  const refreshed = new ConversationSession(storage, fakeChannels, () => UUID_B)
  expect(await refreshed.ready()).toBe(UUID_A)
})

it('rotates a copied sessionStorage id when an existing tab answers the probe', async () => {
  const original = new ConversationSession(storageWith(UUID_A), fakeChannels, () => UUID_B)
  expect(await original.ready()).toBe(UUID_A)
  const duplicate = new ConversationSession(storageWith(UUID_A), fakeChannels, () => UUID_C)
  expect(await duplicate.ready()).toBe(UUID_C)
  expect(original.currentId()).toBe(UUID_A)
})

it('sends conversation_id and parses memory metadata', async () => {
  await streamAsk('技能呢', null, callbacks, undefined, modes, null, UUID_A)
  expect(JSON.parse(fetchBody)).toMatchObject({ conversation_id: UUID_A })
  expect(doneMeta.memory).toEqual({ status: 'hit', turns_used: 1, rewrite_mode: 'planner' })
})
```

Define test constants `UUID_A`, `UUID_B`, and `UUID_C` as distinct RFC 4122 version-4 strings. Define `MemoryStorage` as a `Map`-backed implementation of the `Storage` interface, `storageWith(id)` as a new `MemoryStorage` seeded at `rag.conversation_id`, and `fakeChannels` as an in-memory `BroadcastChannel` factory that asynchronously broadcasts structured messages to all open peers except the sender and supports `close()`.

- [ ] **Step 2: Run frontend tests and verify RED**

```powershell
Set-Location -LiteralPath 'D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app'
npm test -- --run src/session/conversationSession.test.ts src/api/conversation.test.ts src/api/sse.test.ts
```

Expected: FAIL because the modules and wire field do not exist.

- [ ] **Step 3: Implement sessionStorage plus BroadcastChannel probe**

Implement `ConversationSession` with constructor dependencies `Storage`, `(name: string) => BroadcastChannel`, UUID factory, and a default 40 ms probe window. `currentId()` reads `rag.conversation_id`, validates it with the browser UUID pattern, and otherwise generates/stores one UUID. The first `ready()` call creates one shared promise, sends a probe containing the current ID and per-tab instance ID, waits exactly one probe window, rotates only if a matching ack from another instance arrived, and returns the final ID; later calls return the current settled identity without another probe. `rotate()` always generates and stores a different ID and atomically replaces the cached ready result with `Promise.resolve(newId)`, so every later send observes the new ID. `close()` removes message listeners, closes the channel once, and never calls the server.

Wire messages contain only `{type, conversationId, instanceId}`. They never contain questions or answers. Register `pagehide` to close the singleton channel. Existing tab responds to a matching probe but does not rotate; the probing newcomer rotates when any ack arrives.

- [ ] **Step 4: Implement DELETE transport and memory types**

```typescript
export interface MemoryInfo {
  status: 'disabled' | 'new' | 'hit' | 'expired'
  turns_used: number
  rewrite_mode: 'none' | 'planner' | 'fallback'
}

export async function clearConversation(conversationId: string): Promise<void> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE' })
  if (response.status !== 204) throw new Error(`HTTP ${response.status}`)
}
```

Extend the existing `RouteInfo` interface with optional `requested_intents?: string[]` because the real browser gate consumes the already-whitelisted route field; do not add a second top-level intent list.

Extend `StreamMeta`, `metaFromPayload`, and the `streamAsk` body with the exact snake_case backend schema. Do not send `messages`.

- [ ] **Step 5: Run frontend contract tests and TypeScript build**

```powershell
npm test -- --run src/session/conversationSession.test.ts src/api/conversation.test.ts src/api/sse.test.ts
npm run build
```

Expected: PASS; build exits 0.

**Review gate:** refresh reuse and duplicate-tab divergence are both tested; random ID is not described as authentication; transport contains no history array.

---

### Task 8: Integrate Conversation Lifecycle into Zustand and Add the Clear Icon Command

**Files:**
- Modify: `frontend/react-app/src/store/chatStore.ts`
- Modify: `frontend/react-app/src/store/chatStore.test.ts`
- Modify: `frontend/react-app/src/components/sections/ChatSection.tsx`
- Modify: `frontend/react-app/src/components/sections/ChatSection.test.tsx`
- Modify: `frontend/react-app/src/types/index.ts`

**Interfaces:**
- Consumes: Task 7 `conversationSession`, `clearConversation`, `MemoryInfo`, and updated `streamAsk`
- Produces: `ChatState.clear(): Promise<void>`, memory metadata on assistant messages, accessible `Trash2` command

- [ ] **Step 1: Write failing Zustand and UI lifecycle tests**

```typescript
it('uses one id for send, action and retry', async () => {
  vi.spyOn(conversationSession, 'ready').mockResolvedValue(UUID_A)
  await useChatStore.getState().send('技能呢')
  expect(sse.streamAsk).toHaveBeenCalledWith(
    '技能呢', null, expect.anything(), expect.anything(), expect.anything(), null, UUID_A,
  )
})

it('clear aborts, deletes old id, clears messages and rotates even when DELETE fails', async () => {
  const order: string[] = []
  useChatStore.setState({ messages: [_assistantMessage()], abort: () => order.push('abort') })
  const unsubscribe = useChatStore.subscribe((state, previous) => {
    if (previous.messages.length > 0 && state.messages.length === 0) order.push('clear')
  })
  vi.spyOn(conversationSession, 'ready').mockResolvedValue(UUID_A)
  vi.spyOn(api, 'clearConversation').mockImplementation(async () => { order.push('delete'); throw new Error('offline') })
  vi.spyOn(conversationSession, 'rotate').mockImplementation(() => { order.push('rotate'); return UUID_B })
  await useChatStore.getState().clear()
  unsubscribe()
  expect(order).toEqual(['abort', 'delete', 'clear', 'rotate'])
  expect(useChatStore.getState().messages).toEqual([])
})

it('renders an accessible stable clear icon button', () => {
  render(<ChatSection />)
  expect(screen.getByRole('button', { name: '清空对话' })).toHaveAttribute('title', '清空对话')
})
```

Add one regression test that a completed message has no retry command, a failed message retry reuses the current session ID exactly once, omitted/failure actions call the same `send()` path, and two concurrent `send()` calls still produce one network request through the existing `sending` gate.

Add a clear-then-send regression using the real `ConversationSession` test double: the clear request uses UUID A, `rotate()` returns UUID B, and the next `send()` request body must contain UUID B with no later reference to UUID A.

- [ ] **Step 2: Run tests and verify RED**

```powershell
npm test -- --run src/store/chatStore.test.ts src/components/sections/ChatSection.test.tsx
```

Expected: FAIL on missing async lifecycle and clear control.

- [ ] **Step 3: Pass the ready ID through every send path and retain memory diagnostics**

```typescript
send: async (question, actionPayload = null) => {
  if (get().sending) return
  set({ sending: true })
  const conversationId = await conversationSession.ready()
  const controller = new AbortController()
  set({ abortController: controller })
  await streamAsk(question, get().category, callbacks, controller.signal, routeOptions, actionPayload, conversationId)
}
```

Both `onSources` and `onDone` update `message.memory`. `runAction` and retry continue calling `send`, so they cannot bypass the ID. No second concurrency flag is introduced.

- [ ] **Step 4: Implement clear ordering without resetting category or route modes**

```typescript
clear: async () => {
  const currentId = await conversationSession.ready()
  get().abort()
  try {
    await clearConversation(currentId)
  } catch {
    // Rotation below is the isolation boundary; no raw request data is logged.
  } finally {
    set({ messages: [], sending: false, abortController: null })
    conversationSession.rotate()
  }
}
```

Tests must assert `category` and `routeOptions` remain unchanged.

- [ ] **Step 5: Add the icon button using the installed library**

```tsx
import { Trash2 } from 'lucide-react'

<button
  type="button"
  title="清空对话"
  aria-label="清空对话"
  onClick={() => void clear()}
  style={{ width: 36, height: 36, display: 'grid', placeItems: 'center' }}
>
  <Trash2 aria-hidden="true" size={18} />
</button>
```

Place it in the chat header without adding feature-explanation copy. Keep text and controls within the existing header at mobile widths.

- [ ] **Step 6: Run all frontend unit tests and build**

```powershell
npm test -- --run
npm run build
```

Expected: PASS; no TypeScript errors.

**Review gate:** clear rotates even on DELETE failure, no old ID reaches a new send, existing category/modes persist, and the button is icon-based and accessible.

---

### Task 9: Extend the Read-Only Evaluator with Dynamic Multi-Turn Tracks

**Files:**
- Modify: `src/rag_eval/client.py`
- Create: `src/rag_eval/conversation.py`
- Create: `tests/test_rag_eval_conversation.py`
- Modify: `tests/test_rag_eval_client.py`

**Interfaces:**
- Consumes: existing `EvaluationInventory`, `EntityRecord`, `EvalCase`, `ObservedExchange`, `RagEvalClient`
- Produces: optional conversation ID on client methods, `clear_conversation()`, `cancel_stream_after_first_token()`, `ConversationTrack`, `build_conversation_tracks()`, `evaluate_conversation_tracks()`

- [ ] **Step 1: Write failing client and dynamic sampling tests**

```python
def test_eval_client_only_adds_conversation_id_when_requested(fake_session):
    client = RagEvalClient("http://example", session=fake_session)
    client.ask(_case("q"), conversation_id=UUID_A)
    assert fake_session.posts[-1]["json"]["conversation_id"] == UUID_A
    client.ask(_case("q2"))
    assert "conversation_id" not in fake_session.posts[-1]["json"]


def test_tracks_are_dynamic_stratified_and_require_two_entities():
    inventory = _synthetic_inventory(
        entities=[
            _entity("char:a", "角色甲", intents=("skill", "voice"), volume=3),
            _entity("char:b", "角色乙", intents=("item", "culture"), volume=30),
        ]
    )
    tracks = build_conversation_tracks(inventory, seed=20260713, limit=8)
    assert {track.initial_entity_id for track in tracks} == {"char:a", "char:b"}
    assert all(track.switch_entity_id != track.initial_entity_id for track in tracks)
    assert all(len(track.multi_intents) >= 2 for track in tracks)
```

Create `_entity(entity_id, display_name, intents, volume)` by constructing the existing `EntityRecord` with one synthetic child ID per requested intent and no real asset names. Create `_synthetic_inventory(entities)` with the existing `EvaluationInventory` constructor and empty media/parent maps. The same test must assert that a one-entity inventory raises `ConversationEvaluationError` and that two runs with the same seed serialize identically.

- [ ] **Step 2: Run evaluator tests and verify RED**

Run: `pytest -q tests/test_rag_eval_client.py tests/test_rag_eval_conversation.py`

Expected: FAIL because conversation methods and track module are absent.

- [ ] **Step 3: Extend client transport without changing existing callers**

Extend `RagEvalClient.ask()` and `ask_stream()` with keyword-only `conversation_id: str | None = None`. Build their request body through the existing code and add `conversation_id` only when non-null. Add `clear_conversation(conversation_id: str) -> int`, which sends DELETE and returns the status code after requiring 204. Add `cancel_stream_after_first_token(case, *, conversation_id: str) -> tuple[str, ...]`, which uses the same SSE parser and timeout configuration as `ask_stream()`.

`cancel_stream_after_first_token()` closes the response immediately after observing the first non-empty token and never waits for done. It returns event names only, not partial answer text.

- [ ] **Step 4: Build deterministic tracks from artifact inventory**

```python
@dataclass(frozen=True)
class ConversationTrack:
    track_id: str
    initial_entity_id: str
    initial_entity_name: str
    initial_query: str
    follow_intent: str
    follow_up_query: str
    multi_intents: tuple[str, ...]
    multi_intent_query: str
    switch_entity_id: str
    switch_entity_name: str
    switch_query: str
    derivation: Mapping[str, object]
```

Add `build_conversation_tracks(inventory: EvaluationInventory, *, seed: int, limit: int = 8) -> tuple[ConversationTrack, ...]`. Query strings must be generated from the selected inventory names and the evaluator's canonical intent-label mapping: initial `介绍一下{initial_entity_name}`, follow-up `它的{follow_intent_label}呢`, multi-intent `再说说它的{label_1}和{label_2}`, and switch `那么{switch_entity_name}的{follow_intent_label}呢`. Each `sample_manifest.v1.jsonl` record contains `track_id`, all four query fields, both entity IDs/names, `expected_follow_intents`, `expected_multi_intents`, allowed child/parent/media IDs derived from inventory, and derivation SHA-256 values so browser tests do not synthesize assumptions.

Selection rules:

```text
eligible = character entities with at least two non-empty supported P0 section intent sets
count = min(8, eligible count), but fewer than 2 raises ConversationEvaluationError
sort deterministically by text/media volume and entity_id
cover low/mid/high quantiles before filling remaining seeded positions
choose follow/multi intents only from actual child_ids_by_intent
switch target is a different selected entity
queries use generic intent templates; expected IDs come from inventory
serialized evidence uses track_id and entity IDs, never runtime conversation UUID
```

- [ ] **Step 5: Implement deterministic result checks**

Each track verifies:

```text
first explicit turn: memory new, expected entity
pronoun/section follow-up: memory hit, same entity, no cross-entity sources
multi-intent follow-up: requested_intents exact ordered set, both intent source coverage, and media/page-set policy equal to the existing inventory-derived evaluator expectation
explicit switch: new entity, no old entity sources/media
two interleaved IDs: same follow-up text resolves to each own entity
clear: next request does not inherit old entity
cancel: next successful request sees no partial turn
sync/stream: memory/entity/intents/sources semantics match on separate IDs
```

Any cross-session/entity leak produces `SEV-1`; missing inheritance, lost intent, or stale clear produces `SEV-2`.

- [ ] **Step 6: Run evaluator tests**

Run: `pytest -q tests/test_rag_eval_client.py tests/test_rag_eval_conversation.py`

Expected: PASS with synthetic entities only; no production role literal appears in `src/rag_eval/conversation.py`.

**Review gate:** scan production/evaluator source for hard-coded real entities/counts, verify conversation UUID never enters serialized results, and preserve existing client behavior without ID.

---

### Task 10: Build Canonical Real-Environment Verifier and Restart-Loss Probe

**Files:**
- Create: `scripts/verify_rag_conversation_memory.py`
- Create: `tests/test_verify_rag_conversation_memory.py`

**Interfaces:**
- Consumes: Task 9 track evaluator, current config/inventory/snapshot helpers, running API
- Produces CLI subcommands:

```text
run --base-url --seed --output-root
restart-probe --host --port --seed --output-root
finalize-coverage --conversation-run --gate-root --full-chain-run --playwright-report
```

- [ ] **Step 1: Write failing CLI/evidence tests**

```python
def test_run_writes_canonical_evidence_without_runtime_conversation_ids(tmp_path, fake_dependencies):
    exit_code = main(["run", "--base-url", "http://example", "--seed", "20260713", "--output-root", str(tmp_path)])
    assert exit_code == 0
    summary = json.loads(next(tmp_path.rglob("summary.v1.json")).read_text(encoding="utf-8"))
    assert summary["schema_version"] == "rag_conversation_memory.summary/v1"
    assert summary["global_severity"] in {"PASS", "SEV-4", "SEV-3"}
    assert "conversation_id" not in json.dumps(summary)


def test_restart_probe_requires_second_process_to_return_new_status(tmp_path, fake_process_factory):
    fake_process_factory.enqueue_health_and_response(status="new", entity="角色甲")
    fake_process_factory.enqueue_health_and_response(status="new", entity=None)
    exit_code = main(["restart-probe", "--host", "127.0.0.1", "--port", "8011", "--seed", "20260713", "--output-root", str(tmp_path)])
    assert exit_code == 0
    report = json.loads(next(tmp_path.rglob("restart-probe.v1.json")).read_text(encoding="utf-8"))
    assert report["after_restart"]["memory_status"] == "new"
    assert report["after_restart"]["inherited_entity"] is None
```

`fake_process_factory` must record two distinct process objects, provide deterministic health responses and API exchanges, and fail the test unless both processes are terminated and waited exactly once.

- [ ] **Step 2: Run script tests and verify RED**

Run: `pytest -q tests/test_verify_rag_conversation_memory.py`

Expected: FAIL because script does not exist.

- [ ] **Step 3: Implement canonical `run` evidence**

Output exactly:

```text
eval/rag_conversation_memory/
  one child named from UTC yyyyMMddTHHmmssZ plus a random suffix
    run_manifest.v1.json
    sample_manifest.v1.jsonl
    track_results.v1.jsonl
    summary.v1.json
    p0-coverage.partial.v1.json
    artifacts.pre.v1.json
    artifacts.post.v1.json
    milvus.pre.v1.json
    milvus.post.v1.json
```

The `run` command captures inventory and Milvus snapshot before requests, executes all dynamic tracks and isolation/cancel/clear/parity checks, captures post evidence, compares artifact SHA/size and Milvus schema/row/primary-ID fingerprint, then writes canonical JSON using sorted keys, UTF-8, and atomic replace. It writes one partial-coverage entry for every approved P0 ID with status, test/evidence path, SHA-256, observed value, expected value, and failure behavior. Requirements whose real gates occur in Tasks 11-12 remain `pending`; executed failures set `failed`, and only executed successful gates set `passed`. Every P1/P2 range is present with `status="deferred"`. Any mismatch or failed executed gate sets `SEV-1` and exit code 1, but later `pending` gates do not make Task 10 fail.

Implement `finalize-coverage` now, but call it only in Task 12. It must read the partial document plus the named conversation, gate, full-chain, and Playwright evidence roots; reject missing/hash-invalid evidence; require all real gates; and create `p0-coverage.final.v1.json` with all 82 P0 entries passed and P1/P2 deferred. It must use create-new semantics and must never upgrade a failed or missing requirement to passed.

- [ ] **Step 4: Implement isolated two-process restart probe**

Implement `run_restart_probe(project_root: Path, host: str, port: int, seed: int, output_root: Path) -> int` as an isolated two-process state machine. Build one dynamic track from the current inventory, create a random UUID, start `sys.executable -m uvicorn backend.main:app` with `shell=False`, hidden Windows creation flags, explicit host/port, and `project_root` as cwd. Poll `/health` with a 120-second deadline that raises on timeout. Send the track's initial grounded query and require `memory.status="new"`; terminate and wait for process 1. Start a distinct process on the same address, repeat the health gate, send the track's follow-up with the original UUID, and require `memory.status="new"` plus no inherited old entity. Terminate and wait for whichever process exists in `finally`, including assertion-failure paths.

The report stores only SHA-256 of the controlled UUID. Use `creationflags=subprocess.CREATE_NO_WINDOW` on Windows and always terminate/wait in `finally`; never touch the production backend process.

- [ ] **Step 5: Add evidence safety and no-write assertions**

Tests assert no output contains API keys, local source paths, prompts, runtime UUID, hidden plan, or real user transcripts. Capture restart subprocess stdout/stderr in the controlled run directory and assert the raw probe UUID is absent while its approved SHA-256 digest is present only in diagnostic evidence. The script must import no MinIO write client and execute no artifact write outside the unique timestamped child directory it creates under `eval/rag_conversation_memory`.

Add a `finalize-coverage` unit test that supplies hash-pinned synthetic evidence for every required later gate and produces 82 passed P0 entries, plus one test where a missing Playwright report leaves the command nonzero and creates no final file.

Run: `pytest -q tests/test_verify_rag_conversation_memory.py tests/test_rag_eval_conversation.py`

Expected: PASS.

**Review gate:** subprocess cleanup is unconditional, health loops throw on timeout, evidence is append-by-new-run rather than overwrite, and restart loss is actually observed across two processes.

---

### Task 11: Add Real Browser Refresh, Clear, and Duplicate-Tab Gates

**Files:**
- Create: `frontend/react-app/e2e/conversation-memory.spec.ts`
- Modify: `frontend/react-app/vite.config.ts`
- Modify: `frontend/react-app/playwright.config.ts`

**Interfaces:**
- Consumes: Task 10 `sample_manifest.v1.jsonl` path through `RAG_MEMORY_SAMPLE_MANIFEST`, live backend and Vite frontend
- Produces: Playwright evidence proving browser lifecycle and real SSE route/memory behavior

- [ ] **Step 1: Write the browser spec using a dynamic sample manifest**

```typescript
import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const manifestPath = process.env.RAG_MEMORY_SAMPLE_MANIFEST
if (!manifestPath) throw new Error('RAG_MEMORY_SAMPLE_MANIFEST is required')
const sample = JSON.parse(readFileSync(manifestPath, 'utf8').trim().split(/\r?\n/)[0])

function parseSse(text: string) {
  return text.trim().split(/\r?\n\r?\n/).map((frame) => {
    const event = frame.split(/\r?\n/).find((line) => line.startsWith('event:'))?.slice(6).trim()
    const data = frame.split(/\r?\n/).find((line) => line.startsWith('data:'))?.slice(5).trim()
    return { event, data: data ? JSON.parse(data) : null }
  })
}

async function sendThroughUi(page, query: string) {
  const input = page.locator('form input[type="text"]')
  const responsePromise = page.waitForResponse((response) => response.url().includes('/api/ask/stream'))
  await input.fill(query)
  await input.press('Enter')
  const response = await responsePromise
  expect(response.ok()).toBe(true)
  return parseSse(await response.text())
}

test('same tab refresh retains memory and clear rotates it', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'real conversation gate runs once')
  await page.goto('/')
  await page.evaluate(() => document.querySelector('[data-snap-section="chat"]')?.scrollIntoView())
  const first = await sendThroughUi(page, sample.initial_query)
  expect(first.find((item) => item.event === 'done')?.data.memory.status).toBe('new')
  const beforeReload = await page.evaluate(() => sessionStorage.getItem('rag.conversation_id'))
  expect(beforeReload).toMatch(/^[0-9a-f-]{36}$/i)
  await page.reload()
  expect(await page.evaluate(() => sessionStorage.getItem('rag.conversation_id'))).toBe(beforeReload)
  const follow = await sendThroughUi(page, sample.follow_up_query)
  const followSources = follow.find((item) => item.event === 'sources')?.data
  const followDone = follow.find((item) => item.event === 'done')?.data
  expect(followDone.memory.status).toBe('hit')
  expect(followSources.memory).toEqual(followDone.memory)
  expect(followDone.route.entity).toBe(sample.initial_entity_name)
  expect(followDone.route.requested_intents).toEqual(sample.expected_follow_intents)
  for (const source of followDone.sources) {
    expect(sample.allowed_follow_child_ids).toContain(source.child_id)
    expect(sample.allowed_follow_parent_ids).toContain(source.parent_id)
  }
  expect(JSON.stringify(followDone)).not.toMatch(/[A-Z]:\\|file:\/\/|local_relpath/i)
  const deleteResponse = page.waitForResponse((response) => response.request().method() === 'DELETE' && response.url().includes('/api/conversations/'))
  await page.getByRole('button', { name: '清空对话' }).click()
  expect((await deleteResponse).status()).toBe(204)
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('rag.conversation_id'))).not.toBe(beforeReload)
  const afterClear = await sendThroughUi(page, sample.follow_up_query)
  const afterClearDone = afterClear.find((item) => item.event === 'done')?.data
  expect(afterClearDone.memory.status).toBe('new')
  expect(afterClearDone.route?.entity).not.toBe(sample.initial_entity_name)
})

test('duplicated tabs rotate copied session identity', async ({ context }) => {
  const copiedId = '00000000-0000-4000-8000-000000000010'
  const pageA = await context.newPage()
  const pageB = await context.newPage()
  await Promise.all([pageA, pageB].map((page) => page.addInitScript((id) => sessionStorage.setItem('rag.conversation_id', id), copiedId)))
  await pageA.goto('/')
  await expect.poll(() => pageA.evaluate(() => sessionStorage.getItem('rag.conversation_id'))).toBe(copiedId)
  await pageA.waitForTimeout(100)
  await pageB.goto('/')
  await expect.poll(async () => {
    const ids = await Promise.all([pageA, pageB].map((page) => page.evaluate(() => sessionStorage.getItem('rag.conversation_id'))))
    return ids[0] !== ids[1]
  }).toBe(true)
  expect(await pageA.evaluate(() => sessionStorage.getItem('rag.conversation_id'))).toBe(copiedId)
})
```

Type the `page` helper parameter as Playwright `Page`. Extend the assertions to inspect both real SSE `sources` and `done` payloads for identical memory metadata, expected entity/requested intents, and absence of local paths. In `playwright.config.ts`, set `baseURL` to `process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'`; when `PLAYWRIGHT_JSON_OUTPUT_FILE` is set, configure the JSON reporter with that exact `outputFile`. In `vite.config.ts`, set the `/api` proxy target to `process.env.VITE_RAG_API_TARGET || 'http://127.0.0.1:8000'` while preserving the existing `/api/media` rewrite. These environment overrides are test/runtime wiring only and must not enter browser bundles.

- [ ] **Step 2: Run TypeScript compilation for the new E2E file**

```powershell
Set-Location -LiteralPath 'D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app'
npx tsc --noEmit
```

Expected: exit 0.

- [ ] **Step 3: Run Playwright against live services**

```powershell
$RunDirectory = Get-ChildItem -LiteralPath 'D:\PycharmProjects\nlp\LangChain\1999Search\eval\rag_conversation_memory' -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'sample_manifest.v1.jsonl') } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $RunDirectory) { throw 'No conversation-memory run contains sample_manifest.v1.jsonl' }
$env:RAG_MEMORY_SAMPLE_MANIFEST = Join-Path $RunDirectory.FullName 'sample_manifest.v1.jsonl'
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:5173'
npx playwright test e2e/conversation-memory.spec.ts --project=desktop
```

Expected: PASS; never hard-code an entity in the E2E file.

**Review gate:** refresh keeps ID, clear rotates after abort/DELETE, duplicate tabs diverge, route metadata proves server memory rather than only UI state, and the page has no overlap at desktop/mobile unit-tested widths.

---

### Task 12: Run Final Mechanical, Regression, Real-Data, and No-Write Gates

**Files:**
- Verify: all files in the File Map
- Evidence: unique timestamped child directory under `eval/rag_conversation_memory`
- Evidence: unique timestamped child directory under `eval/rag_full_chain`

**Interfaces:**
- Consumes: all prior tasks and Task 0 pre-inventories
- Produces: final P0 acceptance record; no code changes unless a failed gate is root-caused and repaired through the relevant earlier task

- [ ] **Step 1: Run focused Python tests**

```powershell
$Project = 'D:\PycharmProjects\nlp\LangChain\1999Search'
Set-Location -LiteralPath $Project
pytest -q `
  tests/test_conversation_memory.py `
  tests/test_query_plan.py `
  tests/test_prompts.py `
  tests/test_chain_assets.py `
  tests/test_rag_empty_recovery.py `
  tests/test_retriever.py `
  tests/test_retrieval_budget.py `
  tests/test_conversation_api.py `
  tests/test_sse.py `
  tests/test_rag_eval_client.py `
  tests/test_rag_eval_conversation.py `
  tests/test_verify_rag_conversation_memory.py
```

Expected: all pass, zero skipped memory P0 tests.

- [ ] **Step 2: Run full repository test collection from the tests directory boundary**

```powershell
pytest -q tests
```

Expected: PASS. Do not replace this with bare `pytest -q` from the repository root.

- [ ] **Step 3: Run Python syntax and lint gates on touched files**

```powershell
python -m py_compile `
  src/rag/conversation.py `
  src/rag/query_plan.py `
  src/rag/prompts.py `
  src/rag/chain.py `
  src/rag/retriever.py `
  backend/conversation_runtime.py `
  backend/schemas.py `
  backend/main.py `
  backend/sse.py `
  src/rag_eval/conversation.py `
  src/rag_eval/client.py `
  scripts/verify_rag_conversation_memory.py
ruff check `
  src/rag/conversation.py src/rag/query_plan.py src/rag/prompts.py src/rag/chain.py src/rag/retriever.py `
  backend/conversation_runtime.py backend/schemas.py backend/main.py backend/sse.py `
  src/rag_eval/conversation.py src/rag_eval/client.py scripts/verify_rag_conversation_memory.py `
  tests/test_conversation_memory.py tests/test_conversation_api.py tests/test_retriever.py tests/test_rag_eval_conversation.py tests/test_verify_rag_conversation_memory.py
```

Expected: both commands exit 0.

- [ ] **Step 4: Run all frontend unit/build gates**

```powershell
Set-Location -LiteralPath 'D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app'
npm test -- --run
npm run build
```

Expected: all Vitest suites pass and Vite build exits 0.

- [ ] **Step 5: Start dedicated healthy local services without stopping existing listeners**

```powershell
function Test-TcpPort([int]$Port) {
  $Client = [System.Net.Sockets.TcpClient]::new()
  try { $Client.Connect('127.0.0.1', $Port); return $true } catch { return $false } finally { $Client.Dispose() }
}
function Get-FreeTcpPort {
  $Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  $Listener.Start()
  try { return ([System.Net.IPEndPoint]$Listener.LocalEndpoint).Port } finally { $Listener.Stop() }
}

$BackendPort = if (Test-TcpPort 8000) { Get-FreeTcpPort } else { 8000 }
Start-Process -FilePath python -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',"$BackendPort") -WorkingDirectory $Project -WindowStyle Hidden
$BackendUrl = "http://127.0.0.1:$BackendPort"

$FrontendPort = if (Test-TcpPort 5173) { Get-FreeTcpPort } else { 5173 }
$env:VITE_RAG_API_TARGET = $BackendUrl
Start-Process -FilePath npm.cmd -ArgumentList @('run','dev','--','--host','127.0.0.1','--port',"$FrontendPort",'--strictPort') -WorkingDirectory $Frontend -WindowStyle Hidden
$FrontendUrl = "http://127.0.0.1:$FrontendPort"

$Deadline = (Get-Date).AddSeconds(120)
do {
  try {
    $Health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 3
    $OpenApi = Invoke-RestMethod -Uri "$BackendUrl/openapi.json" -TimeoutSec 3
    $AskProperties = $OpenApi.components.schemas.AskRequest.properties
    $BackendReady = $Health.status -eq 'ok' -and $Health.llm_ready -eq $true -and $OpenApi.info.title -eq '1999Search RAG' -and $null -ne $AskProperties.conversation_id -and $null -ne $OpenApi.paths.'/conversations/{conversation_id}'
  } catch { $BackendReady = $false }
  if (-not $BackendReady) { Start-Sleep -Seconds 2 }
} while (-not $BackendReady -and (Get-Date) -lt $Deadline)
if (-not $BackendReady) { throw "Backend health timed out: $BackendUrl" }

$Deadline = (Get-Date).AddSeconds(120)
do {
  try {
    $FrontendResponse = Invoke-WebRequest -Uri $FrontendUrl -TimeoutSec 3
    $FrontendReady = $FrontendResponse.StatusCode -eq 200 -and $FrontendResponse.Content.Contains('1999Search · 重返未来 1999 RAG')
  } catch { $FrontendReady = $false }
  if (-not $FrontendReady) { Start-Sleep -Seconds 2 }
} while (-not $FrontendReady -and (Get-Date) -lt $Deadline)
if (-not $FrontendReady) { throw "Frontend health timed out: $FrontendUrl" }
```

Expected: both explicit health gates pass; an unrelated listener is left untouched and causes allocation of a free alternate port.

- [ ] **Step 6: Capture fresh pre-run MinIO inventory and execute the real conversation verifier**

```powershell
Set-Location -LiteralPath $Project
$env:MINIO_ACCESS_KEY = if ($env:MINIO_ACCESS_KEY) { $env:MINIO_ACCESS_KEY } else { [Environment]::GetEnvironmentVariable('MINIO_ACCESS_KEY', 'User') }
$env:MINIO_SECRET_KEY = if ($env:MINIO_SECRET_KEY) { $env:MINIO_SECRET_KEY } else { [Environment]::GetEnvironmentVariable('MINIO_SECRET_KEY', 'User') }
if (-not $env:MINIO_ACCESS_KEY -or -not $env:MINIO_SECRET_KEY) { throw 'MinIO inventory credentials are unavailable' }
$RunStamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$GateRoot = Join-Path $Project "eval\rag_conversation_memory\gate-$RunStamp"
if (Test-Path -LiteralPath $GateRoot) { throw "Gate path already exists: $GateRoot" }
New-Item -ItemType Directory -Path $GateRoot | Out-Null
python scripts/minio_blue_green_evidence.py object-inventory `
  --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 `
  --access-key-env MINIO_ACCESS_KEY --secret-key-env MINIO_SECRET_KEY `
  --output (Join-Path $GateRoot 'minio.pre.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Pre-gate MinIO inventory failed with exit code $LASTEXITCODE" }
python scripts/verify_rag_conversation_memory.py run `
  --base-url $BackendUrl `
  --seed 20260713 `
  --output-root (Join-Path $Project 'eval\rag_conversation_memory')
if ($LASTEXITCODE -ne 0) { throw "Conversation verifier failed with exit code $LASTEXITCODE" }
$RestartProbePort = 8011
if (Test-TcpPort $RestartProbePort) { $RestartProbePort = Get-FreeTcpPort }
python scripts/verify_rag_conversation_memory.py restart-probe `
  --host 127.0.0.1 --port $RestartProbePort --seed 20260713 `
  --output-root (Join-Path $Project 'eval\rag_conversation_memory')
if ($LASTEXITCODE -ne 0) { throw "Restart probe failed with exit code $LASTEXITCODE" }
```

Expected: both verifier commands exit 0; dynamic eligible count is at least 2; no `SEV-1/SEV-2`; restart probe reports `status=new` and no inherited old entity.

- [ ] **Step 7: Run existing full-chain evaluation to detect M2/M3/M4/M5 regressions**

```powershell
$FullChainRoot = Join-Path $Project 'eval\rag_full_chain'
python -m src.rag_eval.runner run `
  --base-url $BackendUrl `
  --seed 20260713 `
  --output-root $FullChainRoot
if ($LASTEXITCODE -ne 0) { throw "Full-chain evaluator failed with exit code $LASTEXITCODE" }
$FullChainRun = Get-ChildItem -LiteralPath $FullChainRoot -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'module_summary.v1.json') } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $FullChainRun) { throw 'Full-chain evaluator produced no immutable run directory' }
```

Expected: exit 0; global result is PASS, SEV-4, or explicitly accepted SEV-3, with no cross-entity leak, lost explicit intent, grounding failure, media binding/page-set failure, or P95 regression beyond existing thresholds.

- [ ] **Step 8: Run real Playwright memory lifecycle gate**

```powershell
$LatestRun = Get-ChildItem -LiteralPath (Join-Path $Project 'eval\rag_conversation_memory') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'sample_manifest.v1.jsonl') } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $LatestRun) { throw 'No conversation memory sample manifest found' }
$env:RAG_MEMORY_SAMPLE_MANIFEST = Join-Path $LatestRun.FullName 'sample_manifest.v1.jsonl'
$env:PLAYWRIGHT_BASE_URL = $FrontendUrl
$env:PLAYWRIGHT_JSON_OUTPUT_FILE = Join-Path $GateRoot 'playwright.v1.json'
Set-Location -LiteralPath $Frontend
npx playwright test e2e/conversation-memory.spec.ts --project=desktop
if ($LASTEXITCODE -ne 0) { throw "Playwright memory gate failed with exit code $LASTEXITCODE" }
if (-not (Test-Path -LiteralPath $env:PLAYWRIGHT_JSON_OUTPUT_FILE)) { throw 'Playwright JSON evidence was not created' }
```

Expected: PASS with a dynamically selected entity.

- [ ] **Step 9: Capture post-run MinIO inventory and compare every protected store**

```powershell
Set-Location -LiteralPath $Project
python scripts/minio_blue_green_evidence.py object-inventory `
  --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 `
  --access-key-env MINIO_ACCESS_KEY --secret-key-env MINIO_SECRET_KEY `
  --output (Join-Path $GateRoot 'minio.post.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Post-gate MinIO inventory failed with exit code $LASTEXITCODE" }
python scripts/minio_blue_green_evidence.py compare-objects `
  --expected (Join-Path $GateRoot 'minio.pre.v1.json') `
  --actual (Join-Path $GateRoot 'minio.post.v1.json') `
  --output (Join-Path $GateRoot 'minio.compare.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Immediate MinIO comparison failed with exit code $LASTEXITCODE" }

$ConversationRun = Get-ChildItem -LiteralPath (Join-Path $Project 'eval\rag_conversation_memory') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'summary.v1.json') } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $ConversationRun) { throw 'No completed conversation-memory verifier run found' }
python scripts/minio_blue_green_evidence.py compare-milvus `
  --expected (Join-Path $ConversationRun.FullName 'milvus.pre.v1.json') `
  --actual (Join-Path $ConversationRun.FullName 'milvus.post.v1.json') `
  --output (Join-Path $GateRoot 'milvus.compare.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Immediate Milvus comparison failed with exit code $LASTEXITCODE" }

$ArtifactPre = Get-Content -LiteralPath (Join-Path $ConversationRun.FullName 'artifacts.pre.v1.json') -Raw -Encoding UTF8
$ArtifactPost = Get-Content -LiteralPath (Join-Path $ConversationRun.FullName 'artifacts.post.v1.json') -Raw -Encoding UTF8
if ($ArtifactPre -cne $ArtifactPost) { throw 'Protected RAG artifact SHA/size inventory drifted' }
$ArtifactPre | Set-Content -LiteralPath (Join-Path $GateRoot 'artifacts.compare.v1.json') -Encoding UTF8

$BaselinePathFile = Join-Path $Project 'eval\rag_conversation_memory\latest-pre-implementation-path.txt'
if (-not (Test-Path -LiteralPath $BaselinePathFile)) { throw 'Task 0 baseline pointer is missing' }
$BaselineRoot = (Get-Content -LiteralPath $BaselinePathFile -Raw -Encoding UTF8).Trim()
if (-not (Test-Path -LiteralPath $BaselineRoot)) { throw "Task 0 baseline directory is missing: $BaselineRoot" }
python scripts/minio_blue_green_evidence.py compare-objects `
  --expected (Join-Path $BaselineRoot 'minio.pre.v1.json') `
  --actual (Join-Path $GateRoot 'minio.post.v1.json') `
  --output (Join-Path $GateRoot 'minio.implementation-window.compare.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Implementation-window MinIO comparison failed with exit code $LASTEXITCODE" }
python scripts/minio_blue_green_evidence.py compare-milvus `
  --expected (Join-Path $BaselineRoot 'milvus.pre.v1.json') `
  --actual (Join-Path $ConversationRun.FullName 'milvus.post.v1.json') `
  --output (Join-Path $GateRoot 'milvus.implementation-window.compare.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Implementation-window Milvus comparison failed with exit code $LASTEXITCODE" }

$BaselineArtifacts = Get-Content -LiteralPath (Join-Path $BaselineRoot 'artifacts.pre.v1.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$FinalArtifacts = Get-Content -LiteralPath (Join-Path $ConversationRun.FullName 'artifacts.post.v1.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$FinalByName = @{}
foreach ($Item in $FinalArtifacts) { $FinalByName[$Item.name] = $Item }
foreach ($ExpectedItem in $BaselineArtifacts) {
  $ActualItem = $FinalByName[$ExpectedItem.name]
  if ($null -eq $ActualItem -or $ActualItem.length -ne $ExpectedItem.length -or $ActualItem.sha256 -ne $ExpectedItem.sha256) { throw "Implementation-window artifact drift: $($ExpectedItem.name)" }
}
if ($FinalArtifacts.Count -ne $BaselineArtifacts.Count) { throw 'Implementation-window artifact inventory cardinality drifted' }
```

Expected: both the immediate evaluation window and the full Task 0-to-Task 12 implementation window show MinIO equality, Milvus collection/schema/row/primary-fingerprint equality, and all four artifact SHA/size pairs equal. Any drift is a blocking `SEV-1`; stop, identify the writer, and expand the inventory before proceeding.

- [ ] **Step 10: Run the spec coverage audit**

Finalize and validate the coverage document only after all later evidence exists:

```powershell
Set-Location -LiteralPath $Project
python scripts/verify_rag_conversation_memory.py finalize-coverage `
  --conversation-run $ConversationRun.FullName `
  --gate-root $GateRoot `
  --full-chain-run $FullChainRun.FullName `
  --playwright-report (Join-Path $GateRoot 'playwright.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Coverage finalization failed with exit code $LASTEXITCODE" }
$CoveragePath = Join-Path $ConversationRun.FullName 'p0-coverage.final.v1.json'
if (-not (Test-Path -LiteralPath $CoveragePath)) { throw "Missing coverage evidence: $CoveragePath" }
$Coverage = Get-Content -LiteralPath $CoveragePath -Raw -Encoding UTF8 | ConvertFrom-Json
$RequiredPrefixes = @('MEMORY-P0-','CONTEXT-P0-','ANSWER-MEM-P0-','API-MEM-P0-','CHAT-MEM-P0-','SAFETY-MEM-P0-','EVAL-MEM-P0-','GATE-MEM-P0-')
$P0 = @($Coverage.requirements | Where-Object { $Id = $_.id; $RequiredPrefixes | Where-Object { $Id.StartsWith($_) } })
if ($P0.Count -ne 82) { throw "Coverage P0 cardinality is $($P0.Count), expected 82" }
$FailedP0 = @($P0 | Where-Object { $_.status -ne 'passed' -or -not $_.evidence_path -or -not $_.sha256 -or $null -eq $_.observed -or $null -eq $_.expected -or -not $_.failure_behavior })
if ($FailedP0.Count -gt 0) { throw "Coverage has $($FailedP0.Count) incomplete P0 entries" }
$DeferredViolation = @($Coverage.requirements | Where-Object { $_.priority -in @('P1','P2') -and $_.status -ne 'deferred' })
if ($DeferredViolation.Count -gt 0) { throw "Coverage marks deferred requirements incorrectly: $($DeferredViolation.Count)" }
```

Expected: all 82 P0 requirement IDs are present and passed with hash-pinned evidence; every P1/P2 entry is deferred.

**Final review gate:** perform two-stage review: first spec compliance, then code quality/security. Do not mark the plan complete while any P0 is missing, mocked in place of its required real gate, or supported only by one fixed entity.

## Deferred / Out of Scope

- All spec P1/P2 items.
- Redis/MySQL/SQLite or filesystem session persistence.
- Multi-worker shared memory and authenticated account binding.
- Long-term summaries, user profiles, preferences, export, session list, cross-device recovery.
- HTML, Streamlit and Gradio memory support.
- New LLM rewrite call, dedicated co-reference model, clarification UI.
- Milvus rebuild/re-embedding, artifact rebuild, MinIO upload/delete, media budget or voice pagination changes.

## Completion Checklist

- [ ] Task 0 immutable baseline exists.
- [ ] Tasks 1-2 bounded store, TTL, LRU, lock, generation and fail-open tests pass.
- [ ] Tasks 3-4 planner/answer use one shared projection with no extra LLM call.
- [ ] Tasks 5-6 sync/SSE/DELETE contracts and commit boundaries pass.
- [ ] Tasks 7-8 React ID, duplicate-tab, clear and icon tests/build pass.
- [ ] Tasks 9-10 dynamic evaluator, cancellation, isolation, restart and evidence gates pass.
- [ ] Task 11 real browser refresh/clear/duplicate-tab gate passes.
- [ ] Task 12 targeted/full tests, lint/build, full-chain evaluation and no-write comparisons pass.
- [ ] Every spec P0 ID has hash-pinned test/evidence; every P1/P2 remains deferred.
