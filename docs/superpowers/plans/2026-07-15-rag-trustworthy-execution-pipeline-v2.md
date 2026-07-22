# RAG Trustworthy Execution Pipeline V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 RAG 改造成实体所有权、开放回答权限、引用、同步/SSE、短期记忆和性能均可验证的可信执行管线，并通过真实全链路 P0 硬门禁。

**Architecture:** 新的不可变 RAG contracts 统一 `EntityRef`、route 授权/决策、source map、检索 packet 和响应 packet。`RAGExecutionService` 每个请求只规划、检索、挂载媒体和生成回答一次；同步 JSON 与 SSE 仅序列化同一类已验证 packet。现有全链路 evaluator 扩展为 ownership、route、citation、memory 三组配对和阶段 span 的最终验收器。

**Tech Stack:** Python 3.11、frozen dataclasses、LangChain `ChatOpenAI`、FastAPI、Pydantic v2、Milvus、MinIO、MySQL、pytest、React、TypeScript、Vitest、Playwright、现有 `src/rag_eval`。

## Global Constraints

- Governing spec: `docs/superpowers/specs/2026-07-15-rag-trustworthy-execution-pipeline-v2-design.md`.
- Mainline scope contains P0 only: `OWN-P0-01..09`, `ROUTE-P0-01..10`, `CITE-P0-01..11`, `EXEC-P0-01..08`, `TRACE-P0-01..08`, `MEMQ-P0-01..08`, `SAFE-TRUST-P0-01..05`, `EVAL-TRUST-P0-01..09`, `GATE-TRUST-P0-01..12`.
- 保留既有多意图、动态 candidate K、source allocator、媒体类型并集、语音按台词分页、6 轮/30 分钟非持久记忆和 M1-M5 评估契约。
- `requested_intents(plan)` 是唯一 semantic intent 真值；`llm_general` 只能是 execution route。
- 明确实体的所有权键固定为 `(entity_type, entity_id)`；不得使用名称、标题或全局结果填满 `top_k`。
- `free_supplement=false` 只禁止无证据开放回答，不禁用 Planner、问题重述、grounded answer LLM 或短期记忆。
- 普通自由补充开关只授权 `empty` 后 fallback；`partial` 保持 grounded，`failed` 返回结构化错误；只有显式 recovery action 可直接进入开放回答。
- Grounded 回答只接受本轮 `[S01]..[Snn]`；无效草稿不得进入 JSON、SSE、memory 或普通日志。
- P0 SSE 发送完整答案验证后的 token；模型首 token 与用户可见首 token 必须分别记录。
- Planner temperature 固定为 `0`，稳定排序使用稳定 ID tie-break；answer LLM 温度不因本计划强制改为 `0`。
- 工作直接在用户授权的脏工作树中进行。不得运行 git worktree、stage、commit、reset、checkout、clean 或 revert。
- 本计划中的所有 Python 命令均以 `conda run -n 1999wiki python` 开头；不得在执行中自行安装依赖。发现缺包时停止该命令并把安装命令交给用户。
- 实施和验收期间 Milvus、MinIO、MySQL 与 `data/processed/huiji/**` 只读；只允许写测试临时目录和新的 `eval/rag_full_chain/{run_id}` evidence 目录。
- 不重建 Milvus、不重新向量化、不改写 artifacts、不上传或删除 MinIO 对象、不改写 MySQL 业务表。
- 不在生产逻辑或真实验收断言中写死角色名、实体 ID、技能数、台词数、语言数、source 数或 media 数。
- 每个任务按 TDD 执行，并在实现审阅和代码质量审阅均通过后进入下一任务。

---

## 1. File Structure

### New files

| File | Responsibility |
|---|---|
| `src/rag/contracts.py` | `EntityRef`、route、source map、冻结 retrieval/response packet 与公共枚举 |
| `src/rag/ownership.py` | 通用 ownership key、候选/parent/media 所有权过滤与聚合诊断 |
| `src/rag/route_policy.py` | 两阶段 Route Authorization/Finalizer 和 retrieval outcome 分类 |
| `src/rag/citations.py` | `S01..Snn` source map、context、确定性引用验证、格式归一化与安全 fallback |
| `src/rag/execution.py` | 单次 `plan -> retrieve -> answer -> validate -> packet` 执行服务 |
| `src/rag/serializers.py` | 纯 JSON/SSE transport adapter 和公共白名单投影 |
| `src/rag/tracing.py` | 本地 OpenTelemetry 语义兼容 request/span collector |
| `tests/test_rag_contracts.py` | 冻结 contracts、schema 与深层不可变性测试 |
| `tests/test_entity_ownership.py` | 全实体类型 ownership、歧义解析、parent/media/action 门禁测试 |
| `tests/test_route_policy.py` | 开关、Planner 提案、四类 outcome 与显式 action 决策矩阵 |
| `tests/test_citations.py` | 短引用、验证、修复上限、ungrounded 和历史引用隔离测试 |
| `tests/test_rag_execution.py` | 单次执行调用计数、packet 冻结、失败分支与 memory commit 边界测试 |
| `tests/test_rag_tracing.py` | span 父子关系、异常闭合、计时对账与敏感字段测试 |

### Modified files

| File | Change |
|---|---|
| `src/rag/entity_lexicon.py` | lexicon 保留 entity ID/type，同名多 owner 不再合并或任意选择 |
| `src/rag/query_plan.py` | `QueryPlan` 增加 `entity_id`/`resolution_mode`，Planner 与 fallback 产生规范 EntityRef 信息 |
| `src/rag/retriever.py` | 所有候选在 RRF 前和 allocation 后执行通用 owner gate，删除 `exact or ranked` |
| `src/rag/layered_expansion.py` | sibling/parent expansion 和 omitted actions 保留完整 owner 信息 |
| `src/rag/retrieval_budget.py` | 稳定 ID tie-break，并保持 owner 过滤后的真实 shortfall |
| `src/rag/hybrid.py` | RRF/扩展相同分数使用稳定 ID，不能重新引入其他 owner |
| `src/rag/prompts.py` | context 改为 `[Snn]`，明确多来源独立引用和历史非证据规则 |
| `src/rag/conversation.py` | 历史锚点增加 `entity_id`，所有 assistant 历史标记为非本轮证据 |
| `src/rag/chain.py` | 缩减为兼容 facade，委托 `RAGExecutionService`，分离 Planner/answer LLM 配置 |
| `src/assets/huiji_registry.py` | 文本、媒体、分页 cursor 使用相同 ownership key |
| `backend/schemas.py` | 公共 EntityRef/route/source/citation/action/response schema 与白名单校验 |
| `backend/main.py` | `/ask` 调用统一执行服务与 JSON serializer |
| `backend/sse.py` | `/ask/stream` 只消费已验证 packet，不再独立 retrieve/stream LLM |
| `frontend/react-app/src/types/index.ts` | entity ID、citation ID、route decision、grounding mode 和 action type 类型 |
| `frontend/react-app/src/api/sse.ts` | 发送规范 recovery action，解析冻结 packet 元数据 |
| `frontend/react-app/src/store/chatStore.ts` | 状态由 validated SSE events 更新，保留既有自由补充开关 |
| `frontend/react-app/src/components/chat/MessageBubble.tsx` | sources 显示 `[Snn]`，ungrounded 回答保持明确标记 |
| `src/rag_eval/contracts.py` | v2 case/result/manifest 增加 route、citation、span、memory mode 与 protected snapshot 字段 |
| `src/rag_eval/client.py` | 收集完整 packet、validated TTFT、stage spans 和 SSE 事件一致性 |
| `src/rag_eval/inventory.py` | 动态 entity type/owner 清单和 Milvus/MinIO/MySQL/artifact 只读快照 |
| `src/rag_eval/sampling.py` | ownership、route、citation、memory 三组与 D1-D4 分层样本 |
| `src/rag_eval/conversation.py` | memory-off/on/oracle standalone 三组真实执行与 M3 输入 |
| `src/rag_eval/deterministic.py` | 新增跨 owner、route、citation、packet parity、span 和敏感字段硬门禁 |
| `src/rag_eval/judge.py` | M3 读取短引用 source map 并评分多轮 groundedness/完整性/引用支持 |
| `src/rag_eval/runner.py` | 编排 v2 样本、三组多轮、随机人工抽样和完整 protected snapshot 对账 |
| `src/rag_eval/reporting.py` | 输出 trust gate、memory pairing、阶段 P95 与随机抽样 manifest |
| `eval/rag_full_chain_thresholds.v1.json` | 保留固定性能阈值，仅增加 v2 硬门禁配置，不降低现有分数线 |
| `tests/test_query_plan.py`、`tests/test_retriever.py`、`tests/test_huiji_media_registry.py` | 新 contracts 的现有模块回归测试 |
| `tests/test_sse.py`、`tests/test_conversation_api.py` | JSON/SSE 统一执行、取消和 commit 边界测试 |
| `tests/test_rag_eval_*.py` | evaluator v2 contracts、采样、deterministic、judge、runner 与 evidence 测试 |
| `frontend/react-app/src/api/sse.test.ts`、`frontend/react-app/src/store/chatStore.test.ts`、`frontend/react-app/src/components/chat/MessageBubble.test.tsx` | transport、action、引用显示和 ungrounded 展示回归 |

现有 `src/rag/source_labels.py` 在 Task 3 后不再参与生产引用生成；保留一个兼容周期，任何调用都只能用于展示文本，不能用于 citation validation。

---

## 2. P0 Hard-Gate Matrix

| Gate | Spec IDs | Required evidence | Failure result |
|---|---|---|---|
| `TRUST-01 Baseline/Contracts` | `TRACE-P0-01`, `SAFE-TRUST-P0-01..05` | baseline evidence hash、冻结 schema、只读边界 | schema 泄漏/数据写入为 `SEV-1`；baseline 缺失阻断实施对比 |
| `TRUST-02 Ownership` | `OWN-P0-01..09` | 每个动态 entity type 的 source/media owner mismatch 为 0 | 任一跨 owner 为 `SEV-1` |
| `TRUST-03 Route` | `ROUTE-P0-01..10` | 开关/四类 outcome/action/meta_question 矩阵 | 未授权开放回答为 `SEV-1`；intent loss 为 `SEV-2` |
| `TRUST-04 Citation` | `CITE-P0-01..11` | 本轮 source map、100% 合法 ID、repair/fallback 证据 | 无效/历史/未支持引用进入 transport 为 `SEV-1` |
| `TRUST-05 Execution/Parity` | `EXEC-P0-01..08` | 调用计数、JSON/SSE packet parity、取消/commit 证据 | 重复执行或 parity 失败为 `SEV-2` |
| `TRUST-06 Trace` | `TRACE-P0-02..08` | 所有 stage span、四类时间、P95、敏感字段扫描 | span 缺失/不可对账或 P95 超标为 `SEV-2` |
| `TRUST-07 Memory Quality` | `MEMQ-P0-01..08` | off/on/oracle 三组、M3、错误传播和隔离结果 | 历史无依据事实/引用传播为 `SEV-1`；质量或性能回退按现有规则至少 `SEV-2` |
| `TRUST-08 Automated Coverage` | `EVAL-TRUST-P0-01..09` | 单元、集成、真实 endpoint、兼容性测试 | 任一未执行或失败阻断 P0 |
| `TRUST-09 Real Acceptance` | `GATE-TRUST-P0-01..12` | 动态样本、分层随机人工复核、M1-M5、protected snapshot equality | 只接受 `PASS/SEV-4/accepted SEV-3`，不得存在 `SEV-1/SEV-2` |

---

## 3. Task 0: Freeze Baseline, Core Contracts, and Trace Foundation

**Corresponding specs:** `TRACE-P0-01`, `TRACE-P0-03`, `TRACE-P0-06`, `SAFE-TRUST-P0-01`, `SAFE-TRUST-P0-04`, shared interfaces for every later P0 task.

**Files:**

- Create: `src/rag/contracts.py`
- Create: `src/rag/tracing.py`
- Create: `tests/test_rag_contracts.py`
- Create: `tests/test_rag_tracing.py`
- Modify: `src/rag/__init__.py`

**Interfaces:**

- Produces: `EntityRef`, `RouteAuthorization`, `RouteDecision`, `SourceRef`, `CitationValidation`, `FrozenRetrievalPacket`, `ResponsePacket`, `RetrievalOutcome`, `ExecutionRoute`, `GroundingMode`.
- Produces: `RequestTrace`, `StageSpan`, `TraceSnapshot`, `NullTrace`, `safe_trace_attributes()`.
- Consumed by: Tasks 1-8.

- [ ] **Step 1: Capture the immutable pre-change baseline**

Use the currently running backend and the existing evaluator before changing behavior:

```powershell
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BaselineRoot = "eval/rag_full_chain/trust-v2-baseline-$RunStamp"
New-Item -ItemType Directory -Path $BaselineRoot -ErrorAction Stop | Out-Null
conda run -n 1999wiki python scripts/evaluate_rag_full_chain.py preflight `
  --base-url http://127.0.0.1:8000 `
  --output "$BaselineRoot/preflight.v1.json"
$BaselinePreflight = Get-Content -LiteralPath "$BaselineRoot/preflight.v1.json" -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $BaselinePreflight.allowed_to_run) { throw 'Baseline preflight rejected the run' }
conda run -n 1999wiki python scripts/evaluate_rag_full_chain.py run `
  --base-url http://127.0.0.1:8000 `
  --seed 1999 `
  --output-root $BaselineRoot
$BaselineExitCode = $LASTEXITCODE
@{
  schema_version = 'rag_eval.trust_v2_baseline/v1'
  evaluator_exit_code = $BaselineExitCode
  seed = 1999
} | ConvertTo-Json | Set-Content -LiteralPath "$BaselineRoot/baseline-run.v1.json" -Encoding UTF8
Get-ChildItem -LiteralPath $BaselineRoot -Recurse -File |
  Get-FileHash -Algorithm SHA256 |
  Sort-Object Path |
  ConvertTo-Json -Depth 4 |
  Set-Content -LiteralPath "$BaselineRoot/baseline-files.sha256.json" -Encoding UTF8
```

Expected: preflight is allowed; the full run may retain the already observed `SEV-1/SEV-2` findings, but it must produce immutable evidence. A missing preflight dependency stops Task 0; a quality failure does not authorize editing evidence or weakening thresholds.

- [ ] **Step 2: Write failing contract and deep-freeze tests**

Add tests that define exact field names and prove nested payloads cannot be mutated:

```python
def test_entity_ref_uses_type_and_id_as_ownership_key():
    ref = EntityRef("fixture_type", "fixture-1", "示例", ("Example",), "current_exact")
    assert ref.ownership_key == ("fixture_type", "fixture-1")


def test_response_packet_deep_freezes_nested_public_values():
    packet = response_packet_fixture()
    with pytest.raises(TypeError):
        packet.retrieval_packet.diagnostics["candidate_k"] = 99
    with pytest.raises(dataclasses.FrozenInstanceError):
        packet.answer = "changed"


def test_route_and_intent_are_separate_contracts():
    authorization = RouteAuthorization(
        semantic_intents=("meta_question",),
        proposed_route="llm_general",
        allow_free_supplement_after_empty=False,
        force_free_supplement=False,
        authorization_reason="default_closed",
    )
    assert authorization.semantic_intents == ("meta_question",)
    assert authorization.proposed_route == "llm_general"
```

Run:

```powershell
conda run -n 1999wiki python -m pytest tests/test_rag_contracts.py -q
```

Expected: FAIL because `src.rag.contracts` does not exist.

- [ ] **Step 3: Implement versioned immutable contracts**

Use frozen dataclasses and recursively frozen mappings/tuples. The public signatures are fixed for later tasks:

```python
RetrievalOutcome = Literal["sufficient", "partial", "empty", "failed"]
ExecutionRoute = Literal["rag_grounded", "expanded_rag", "llm_general"]
GroundingMode = Literal["grounded", "ungrounded", "none"]


@dataclass(frozen=True)
class EntityRef:
    entity_type: str
    entity_id: str
    entity_name: str
    aliases: tuple[str, ...] = ()
    resolution_mode: str = "unresolved"

    @property
    def ownership_key(self) -> tuple[str, str]:
        return self.entity_type, self.entity_id


@dataclass(frozen=True)
class RouteAuthorization:
    semantic_intents: tuple[str, ...]
    proposed_route: str
    allow_free_supplement_after_empty: bool
    force_free_supplement: bool
    authorization_reason: str


@dataclass(frozen=True)
class RouteDecision:
    authorization: RouteAuthorization
    retrieval_outcome: RetrievalOutcome
    effective_route: ExecutionRoute
    route_reason: str


@dataclass(frozen=True)
class SourceRef:
    citation_id: str
    entity_type: str
    entity_id: str
    child_id: str
    parent_id: str
    display_name: str
    heading_path: str


@dataclass(frozen=True)
class CitationValidation:
    valid: bool
    used_ids: tuple[str, ...] = ()
    invalid_ids: tuple[str, ...] = ()
    duplicate_ids: tuple[str, ...] = ()
    missing_required: bool = False
    normalized: bool = False
    repair_attempts: int = 0
    warnings: tuple[str, ...] = ()
```

`FrozenRetrievalPacket` stores plan, EntityRef, RouteDecision, requested intents, frozen sources/source map/media/panels/context/diagnostics/actions/planning metadata. `ResponsePacket` stores retrieval packet, answer, grounding mode, citation validation, frozen memory info and `turn_outcome`. `freeze_value()` recursively converts dict to `MappingProxyType`, list to tuple and set to sorted tuple before packet construction.

- [ ] **Step 4: Write failing trace lifecycle and redaction tests**

```python
def test_request_trace_closes_failed_span_and_uses_monotonic_duration(monkeypatch):
    trace = RequestTrace(clock_ns=sequence_clock(100, 250))
    with pytest.raises(RuntimeError):
        with trace.span("planner.llm"):
            raise RuntimeError("boom")
    span = trace.snapshot().spans[0]
    assert span.status == "error"
    assert span.duration_ms == pytest.approx(0.00015)
    assert span.error_class == "RuntimeError"


def test_trace_rejects_sensitive_or_free_text_attributes():
    with pytest.raises(ValueError, match="attribute"):
        safe_trace_attributes({"question": "真实问题"})
    with pytest.raises(ValueError, match="attribute"):
        safe_trace_attributes({"local_path": "D:\\secret"})
```

- [ ] **Step 5: Implement the local trace foundation**

Implement a context manager with no external collector requirement:

```python
@dataclass(frozen=True)
class StageSpan:
    name: str
    parent_name: str | None
    start_offset_ms: float
    duration_ms: float
    status: Literal["ok", "error"]
    attributes: Mapping[str, object]
    error_class: str = ""


class RequestTrace:
    @contextmanager
    def span(self, name: str, **attributes: object) -> Iterator[None]:
        safe = safe_trace_attributes(attributes)
        started = self._clock_ns()
        status = "ok"
        error_class = ""
        try:
            yield
        except Exception as error:
            status = "error"
            error_class = type(error).__name__
            raise
        finally:
            self._append_span(name, safe, started, self._clock_ns(), status, error_class)

    def mark_model_first_token(self) -> None:
        self._mark_once("model_first_token_ms")

    def mark_validated_ready(self) -> None:
        self._mark_once("validated_ready_ms")

    def mark_visible_first_token(self) -> None:
        self._mark_once("visible_first_token_ms")

    def mark_completed(self) -> None:
        self._mark_once("completed_ms")

    def snapshot(self) -> TraceSnapshot:
        return TraceSnapshot(tuple(self._spans), **self._marks)
```

The implementation must use `time.perf_counter_ns`, close spans in `finally`, store only allow-listed scalar/count attributes, and return `NullTrace` when instrumentation creation fails. Trace failure records a warning but never changes the answer path.

- [ ] **Step 6: Run Task 0 tests and review the baseline hash**

```powershell
conda run -n 1999wiki python -m pytest tests/test_rag_contracts.py tests/test_rag_tracing.py -q
Get-ChildItem -LiteralPath eval/rag_full_chain -Directory |
  Where-Object Name -Like 'trust-v2-baseline-*' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
```

Expected: focused tests PASS; the printed baseline directory contains `preflight.v1.json`, one evaluator run/evidence directory and `baseline-files.sha256.json`.

**Task acceptance:** immutable contracts and trace foundation are reviewable in isolation; pre-change evidence is hash-pinned; no business behavior has changed; no protected store was written.

---

## 4. Task 1: Generic Entity Ownership Gate

**Corresponding specs:** `OWN-P0-01..09`, `SAFE-TRUST-P0-02`, `SAFE-TRUST-P0-03`.

**Files:**

- Create: `src/rag/ownership.py`
- Create: `tests/test_entity_ownership.py`
- Modify: `src/rag/entity_lexicon.py`
- Modify: `src/rag/query_plan.py`
- Modify: `src/rag/retriever.py`
- Modify: `src/rag/layered_expansion.py`
- Modify: `src/rag/retrieval_budget.py`
- Modify: `src/rag/hybrid.py`
- Modify: `src/assets/huiji_registry.py`
- Modify: `tests/test_entity_lexicon.py`
- Modify: `tests/test_query_plan.py`
- Modify: `tests/test_retriever.py`
- Modify: `tests/test_huiji_media_registry.py`

**Interfaces:**

- Consumes: `EntityRef`, current parent/child/media artifacts and `requested_intents(plan)`.
- Produces: `EntityResolution`, `OwnershipDiagnostics`, `ownership_key(row)`, `filter_owned_rows(rows, entity_ref, stage)`, `validate_target_parent(parent_id, entity_ref, rows)`, `validate_owned_media(media, entity_ref)`.
- Produces compatibility fields: `QueryPlan.entity`, `QueryPlan.entity_type`, plus new `QueryPlan.entity_id` and `QueryPlan.resolution_mode`.

- [ ] **Step 1: Write failing lexicon and generic ownership tests**

Cover all ownership semantics without a real role constant:

```python
def test_lexicon_keeps_same_name_different_owner_ambiguous():
    lexicon = EntityLexicon.from_records([
        {"entity_name": "同名", "entity_type": "character", "entity_id": "c1"},
        {"entity_name": "同名", "entity_type": "story", "entity_id": "s1"},
    ])
    resolution = lexicon.resolve("介绍同名", entity_type_hint=None)
    assert resolution.entity_ref is None
    assert {item.ownership_key for item in resolution.ambiguous} == {
        ("character", "c1"), ("story", "s1")
    }


@pytest.mark.parametrize("stage", ["structured", "bm25", "dense", "rerank", "expand", "allocate"])
def test_owner_gate_removes_other_owner_without_backfill(stage):
    kept, diagnostics = filter_owned_rows(rows_for_two_owners(), entity_ref("type-a", "id-a"), stage)
    assert [row["child_id"] for row in kept] == ["a-1"]
    assert diagnostics.owner_mismatch == 1
    assert diagnostics.after_count == 1


def test_missing_owner_metadata_is_not_owned():
    kept, diagnostics = filter_owned_rows([{"child_id": "unknown"}], entity_ref("x", "1"), "dense")
    assert kept == []
    assert diagnostics.missing_owner_metadata == 1


def test_empty_exact_owner_does_not_fall_back_to_ranked_other_owner(retriever):
    result = retriever.search("q", query_plan=plan_for("type-a", "missing"), k=20)
    assert result == []
    assert retriever.last_route_debug["owner_mismatch"] > 0
```

Run and confirm failure:

```powershell
conda run -n 1999wiki python -m pytest tests/test_entity_ownership.py tests/test_entity_lexicon.py tests/test_retriever.py -q
```

- [ ] **Step 2: Preserve owner identity in the lexicon and planner**

Change `EntityMatch` and add a non-arbitrary resolution result:

```python
@dataclass(frozen=True)
class EntityMatch:
    canonical: str
    matched_text: str
    aliases: tuple[str, ...]
    entity_type: str
    entity_id: str

    def to_ref(self, resolution_mode: str) -> EntityRef:
        return EntityRef(self.entity_type, self.entity_id, self.canonical, self.aliases, resolution_mode)


@dataclass(frozen=True)
class EntityResolution:
    entity_ref: EntityRef | None
    ambiguous: tuple[EntityRef, ...] = ()
```

`EntityLexicon.from_records()` groups by `(entity_type, entity_id)`, never canonical name alone. `resolve(query, entity_type_hint)` first selects the longest matched term, then applies a server-derived category/entity-type hint; it returns an owner only when one key remains. Ties across owners without a valid hint return `entity_ref=None` and all sorted candidates. Keep `match(query)` as a compatibility wrapper that returns the unique `EntityMatch` or `None`.

Extend `QueryPlan` with:

```python
entity_id: str | None = None
resolution_mode: str = "unresolved"
```

Planner/action/current explicit entity/history precedence remains unchanged, but each accepted anchor must carry all three `entity`, `entity_type`, `entity_id`. Remove the fallback that defaults every resolved entity to `character`; unresolved entity data remains `None` rather than guessed.

- [ ] **Step 3: Implement owner filtering and remove role-only fallback**

Implement the generic row gate:

```python
def ownership_key(row: Mapping[str, object]) -> tuple[str, str] | None:
    entity_type = str(row.get("entity_type") or "").strip()
    entity_id = str(row.get("entity_id") or "").strip()
    return (entity_type, entity_id) if entity_type and entity_id else None


def filter_owned_rows(
    rows: Iterable[Mapping[str, object]],
    owner: EntityRef | None,
    stage: str,
) -> tuple[list[dict[str, object]], OwnershipDiagnostics]:
    if owner is None:
        materialized = [dict(row) for row in rows]
        return materialized, OwnershipDiagnostics(stage, len(materialized), len(materialized), 0, 0)
    # Keep only exact ownership_key matches; count missing and mismatch separately.
```

In `Retriever._search_huiji()` apply the same owner gate to structured rows, BM25 rows and Dense rows before `weighted_rrf`; verify again after rerank, expansion and allocation. Replace `_filter_to_primary_character()` with `_filter_to_owner()` and return the exact filtered list even when empty. Do not use `exact or ranked`.

Stable ordering keys end with `child_id`, then `parent_id`; set iteration must not determine final source order. `last_route_debug` adds `owner_before`, `owner_after`, `missing_owner_metadata`, `owner_mismatch`, `owner_shortfall` and `ownership_key`.

- [ ] **Step 4: Gate expansion, omitted actions, target parent, media and cursors**

Every action carries owner identity:

```python
{
    "action_type": "expand_parent",
    "entity": entity_ref.entity_name,
    "entity_type": entity_ref.entity_type,
    "entity_id": entity_ref.entity_id,
    "semantic_intents": list(requested_intents),
    "target_parent_id": parent_id,
}
```

`validate_target_parent()` must find the parent in current rows and require the same owner. `expand_ranked_children()` receives `EntityRef | None` instead of deriving owner from `ranked[0].entity_name`. `make_omitted_actions()` copies the verified owner.

`HuijiMediaRegistry.find_bundle_for_retrieval()` rejects any media, binding or panel whose `(entity_type, entity_id)` differs from the packet owner. Voice `next_cursor` must encode and later revalidate the same owner; a mismatched or incomplete cursor raises the existing safe pagination error rather than opening a global page.

- [ ] **Step 5: Add post-condition assertions and full regression tests**

Add one final reusable assertion before packet freeze:

```python
def assert_packet_ownership(
    entity_ref: EntityRef | None,
    sources: Sequence[Mapping[str, object]],
    media: Sequence[Mapping[str, object]],
) -> None:
    if entity_ref is None:
        return
    mismatches = [item for item in (*sources, *media) if ownership_key(item) != entity_ref.ownership_key]
    if mismatches:
        raise OwnershipViolation("final packet contains owner mismatch")
```

Run:

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_entity_ownership.py `
  tests/test_entity_lexicon.py `
  tests/test_query_plan.py `
  tests/test_retriever.py `
  tests/test_hybrid_retriever.py `
  tests/test_retrieval_budget.py `
  tests/test_chain_assets.py `
  tests/test_huiji_media_registry.py `
  tests/test_voice_pagination.py -q
```

Expected: PASS; tests explicitly prove an owner with fewer results than `top_k` returns fewer results, and every mismatch count is observable without exposing content/path.

**Task acceptance:** all retrieval/media stages use `(entity_type, entity_id)`; ambiguous identities do not select an arbitrary owner; no cross-owner backfill remains; failure produces truthful empty/shortfall diagnostics.

---

## 5. Task 2: Route Authorization and Free-Supplement Policy

**Corresponding specs:** `ROUTE-P0-01..10`, `SAFE-TRUST-P0-02`.

**Files:**

- Create: `src/rag/route_policy.py`
- Create: `tests/test_route_policy.py`
- Modify: `src/rag/query_plan.py`
- Modify: `src/rag/chain.py`
- Modify: `src/rag/retriever.py`
- Modify: `backend/schemas.py`
- Modify: `tests/test_rag_empty_recovery.py`
- Modify: `tests/test_query_plan.py`
- Modify: `tests/test_retriever.py`

**Interfaces:**

- Consumes: `QueryPlan`, `requested_intents(plan)`, validated `route_options`, validated `action_payload`, retrieval sources and coverage shortfall.
- Produces: `authorize_route(plan, route_options, action_payload) -> RouteAuthorization`, `classify_retrieval_outcome(sources, coverage_shortfall, failed=False) -> RetrievalOutcome`, `finalize_route(authorization, outcome) -> RouteDecision`.
- Produces action types: `expand_search`, `force_free_supplement`, `expand_parent`; legacy `intent=llm_general` is normalized only at the API boundary.

- [ ] **Step 1: Write the complete failing route matrix**

Use table tests instead of scattered condition tests:

```python
@pytest.mark.parametrize(
    ("toggle", "force", "outcome", "expected_route"),
    [
        (False, False, "sufficient", "rag_grounded"),
        (False, False, "partial", "rag_grounded"),
        (False, False, "empty", "rag_grounded"),
        (False, False, "failed", "rag_grounded"),
        (True, False, "sufficient", "rag_grounded"),
        (True, False, "partial", "rag_grounded"),
        (True, False, "empty", "llm_general"),
        (True, False, "failed", "rag_grounded"),
        (False, True, "empty", "llm_general"),
    ],
)
def test_route_matrix(toggle, force, outcome, expected_route):
    auth = authorization(toggle=toggle, force=force, proposed="llm_general")
    assert finalize_route(auth, outcome).effective_route == expected_route


def test_meta_question_intent_survives_planner_llm_general_proposal():
    auth = authorize_route(plan(intent="meta_question", route="llm_general"), {}, None)
    decision = finalize_route(auth, "empty")
    assert auth.semantic_intents == ("meta_question",)
    assert decision.effective_route == "rag_grounded"


def test_expanded_route_remains_grounded_and_does_not_become_general():
    auth = authorize_route(
        plan(intent="skill", route="rag_grounded"),
        {"expanded": True, "free_supplement": False},
        None,
    )
    decision = finalize_route(auth, "sufficient")
    assert decision.effective_route == "expanded_rag"
    assert auth.semantic_intents == ("skill",)


def test_legacy_hybrid_answer_is_normalized_to_grounded_route():
    auth = authorize_route(plan(intent="skill", route="hybrid_answer"), {}, None)
    assert auth.proposed_route == "rag_grounded"


def test_failed_dependency_never_becomes_empty_fallback():
    decision = finalize_route(authorization(toggle=True), "failed")
    assert decision.effective_route == "rag_grounded"
    assert decision.route_reason == "retrieval_failed"


def test_dense_dependency_failure_is_not_reported_as_empty(retriever_with_failed_vectorstore):
    with pytest.raises(RetrievalExecutionError, match="retrieval.dense"):
        retriever_with_failed_vectorstore.search("q", query_plan=resolved_plan())
```

Run:

```powershell
conda run -n 1999wiki python -m pytest tests/test_route_policy.py tests/test_rag_empty_recovery.py -q
```

Expected: FAIL because route policy functions do not exist and current toggle bypasses retrieval.

- [ ] **Step 2: Implement pre-retrieval authorization**

Implement strict option/action normalization:

```python
def authorize_route(
    plan: QueryPlan,
    route_options: Mapping[str, object],
    action_payload: Mapping[str, object] | None,
) -> RouteAuthorization:
    action_type = str((action_payload or {}).get("action_type") or "")
    force = action_type == "force_free_supplement"
    allow_after_empty = bool(route_options.get("free_supplement"))
    expanded = action_type == "expand_search" or bool(route_options.get("expanded"))
    planner_route = "rag_grounded" if plan.route == "hybrid_answer" else plan.route
    proposed_route = "expanded_rag" if expanded else planner_route
    return RouteAuthorization(
        semantic_intents=requested_intents(plan),
        proposed_route=proposed_route,
        allow_free_supplement_after_empty=allow_after_empty,
        force_free_supplement=force,
        authorization_reason="explicit_recovery_action" if force else (
            "toggle_allows_empty_fallback" if allow_after_empty else "default_closed"
        ),
    )
```

Client values never directly set `effective_route`. Validate action field lengths/enums and require its EntityRef/parent to pass Task 1 ownership checks. History, Planner output and action labels are never authorization sources.

- [ ] **Step 3: Implement retrieval outcome and final route decision**

```python
def classify_retrieval_outcome(
    sources: Sequence[object],
    coverage_shortfall: Mapping[str, int],
    *,
    failed: bool = False,
) -> RetrievalOutcome:
    if failed:
        return "failed"
    if not sources:
        return "empty"
    return "partial" if any(value > 0 for value in coverage_shortfall.values()) else "sufficient"


def finalize_route(auth: RouteAuthorization, outcome: RetrievalOutcome) -> RouteDecision:
    if auth.force_free_supplement:
        return RouteDecision(auth, outcome, "llm_general", "explicit_recovery_action")
    if outcome == "empty" and auth.allow_free_supplement_after_empty:
        return RouteDecision(auth, outcome, "llm_general", "authorized_empty_fallback")
    grounded_route = "expanded_rag" if auth.proposed_route == "expanded_rag" else "rag_grounded"
    reason = "retrieval_failed" if outcome == "failed" else f"grounded_{outcome}"
    return RouteDecision(auth, outcome, grounded_route, reason)
```

`partial` returns a grounded answer plus shortfall/failure actions. `failed` returns a structured retrieval error and does not invoke free answer. `empty` with default-closed returns the existing insufficiency response plus recovery actions.

Add `RetrievalExecutionError(stage, error_class)` in `retriever.py`. When a required retrieval stage exhausts its documented fallback, propagate this structured exception instead of returning `[]`; specifically, `_dense_rows_for_plan()` may fall back from `similarity_search_with_relevance_scores()` to `similarity_search()`, but if both fail it raises `RetrievalExecutionError("retrieval.dense", type(error).__name__)`. The chain catches this type, classifies `failed`, and never treats it as an empty knowledge base. A healthy stage that truthfully returns zero rows remains `empty`, not `failed`.

- [ ] **Step 4: Replace legacy action semantics without breaking old clients**

Extend `ActionItem` with `action_type`, `entity_id`, `semantic_intents`. New server-generated free action is:

```python
ActionItem(
    label="使用自由补充重答",
    query=question,
    action_type="force_free_supplement",
    entity=entity_ref.entity_name if entity_ref else "",
    entity_type=entity_ref.entity_type if entity_ref else "",
    entity_id=entity_ref.entity_id if entity_ref else "",
    semantic_intents=list(requested_intents),
    target_parent_id=None,
)
```

At `AskRequest` validation only, map a legacy action with `intent="llm_general"` or `packet_policy="free_supplement"` to `action_type="force_free_supplement"`; map legacy `intent="expanded_rag"` or `packet_policy="expanded"` to `action_type="expand_search"`. Reconstruct semantic intents from the current question/plan, then discard all legacy route-as-intent values internally. Normalize legacy Planner `hybrid_answer` to grounded `rag_grounded`; it is never a semantic intent or open-answer authorization.

- [ ] **Step 5: Integrate policy into retrieval without unifying endpoints yet**

Change the chain retrieval flow to:

```text
plan -> authorize
force action -> skip retrieval -> finalize -> free answer path
expanded action/option -> retrieve once with expanded policy -> classify -> grounded final route
otherwise -> retrieve once -> classify sufficient/partial/empty/failed -> finalize
```

Delete `_is_free_supplement()` as an authorization oracle and delete `_with_route_options()` behavior that rewrites `plan.route`. `_route_info()` reports `semantic_intents`, `proposed_route`, `effective_route`, `retrieval_outcome` and enum `route_reason`; it never reports `intent=llm_general`.

- [ ] **Step 6: Run route and compatibility tests**

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_route_policy.py `
  tests/test_rag_empty_recovery.py `
  tests/test_query_plan.py `
  tests/test_chain_assets.py `
  tests/test_sse.py -q
```

Expected: route unit tests PASS; legacy request tests remain accepted; tests assert toggle-on still calls retrieval once and that dependency exceptions cannot become free answers.

**Task acceptance:** Planner route is only a proposal; the default switch is closed; `partial/empty/failed` have distinct behavior; `meta_question` and all other semantic intents survive every route decision.

---

## 6. Task 3: Stable Source Map and Citation Validation

**Corresponding specs:** `CITE-P0-01..11`, `SAFE-TRUST-P0-03`.

**Files:**

- Create: `src/rag/citations.py`
- Create: `tests/test_citations.py`
- Modify: `src/rag/prompts.py`
- Modify: `src/rag/chain.py`
- Modify: `src/rag/conversation.py`
- Modify: `backend/schemas.py`
- Modify: `tests/test_prompts.py`

**Interfaces:**

- Consumes: final owner-validated source order, answer draft, grounding mode, current source map.
- Produces: `build_source_map()`, `format_citation_context()`, `normalize_citation_format()`, `validate_citations()`, `validate_or_repair_answer()`.
- Produces: source `citation_id` fields and `CitationValidation`; repair callback signature `Callable[[str, str, tuple[SourceRef, ...]], str]`.

- [ ] **Step 1: Write failing source-map and validator tests**

```python
def test_source_map_assigns_local_ids_in_final_source_order():
    sources, source_map = build_source_map(final_sources())
    assert [row["citation_id"] for row in sources] == ["S01", "S02"]
    assert source_map[0].child_id == sources[0]["child_id"]


@pytest.mark.parametrize("answer", ["结论 [S99]", "结论 [标题]", "结论 [S01,S02]"])
def test_validator_rejects_unknown_or_noncanonical_labels(answer):
    result = validate_citations(answer, source_map_fixture(), "grounded")
    assert result.valid is False


def test_multiple_sources_use_multiple_independent_tokens():
    result = validate_citations("结论 [S01][S02]", source_map_fixture(), "grounded")
    assert result.valid is True
    assert result.used_ids == ("S01", "S02")


def test_ungrounded_answer_cannot_claim_source_ids():
    result = validate_citations("自由回答 [S01]", source_map_fixture(), "ungrounded")
    assert result.valid is False
```

Run:

```powershell
conda run -n 1999wiki python -m pytest tests/test_citations.py tests/test_prompts.py -q
```

Expected: FAIL because the citation module does not exist and prompts still use long labels.

- [ ] **Step 2: Build the source map only after allocation**

Implement stable, per-packet IDs:

```python
def build_source_map(
    sources: Sequence[Mapping[str, object]],
) -> tuple[tuple[Mapping[str, object], ...], tuple[SourceRef, ...]]:
    public_sources = []
    refs = []
    for index, source in enumerate(sources, start=1):
        citation_id = f"S{index:02d}"
        public_sources.append(freeze_value({**source, "citation_id": citation_id}))
        refs.append(SourceRef(
            citation_id=citation_id,
            entity_type=str(source.get("entity_type") or ""),
            entity_id=str(source.get("entity_id") or ""),
            child_id=str(source.get("child_id") or ""),
            parent_id=str(source.get("parent_id") or ""),
            display_name=str(source.get("name") or ""),
            heading_path=str(source.get("heading_path") or ""),
        ))
    return tuple(public_sources), tuple(refs)
```

`format_citation_context()` emits `"[S01] 证据正文"`; it never emits long source labels inside brackets. Public source metadata includes `citation_id`, owner, child, parent, display name and heading, but excludes content, prompt, local path and credentials.

- [ ] **Step 3: Implement deterministic validation and safe normalization**

The validator recognizes only `\[S\d{2,}\]`. It reports ordered used, invalid, duplicate IDs and `missing_required`. Safe normalization may only split a bracket composed entirely of existing IDs, for example `[S01, S02] -> [S01][S02]`; it must not invent IDs, map titles, or alter prose.

```python
def validate_citations(
    answer: str,
    source_map: Sequence[SourceRef],
    grounding_mode: GroundingMode,
) -> CitationValidation:
    valid_ids = {item.citation_id for item in source_map}
    tokens = tuple(_CITATION_TOKEN_RE.findall(answer))
    invalid = tuple(dict.fromkeys(token for token in tokens if token not in valid_ids))
    used = tuple(dict.fromkeys(token for token in tokens if token in valid_ids))
    duplicates = tuple(dict.fromkeys(token for token in tokens if tokens.count(token) > 1))
    malformed = tuple(_BRACKET_RE.findall(_CITATION_TOKEN_RE.sub("", answer)))
    missing = grounding_mode == "grounded" and bool(source_map) and not used
    return CitationValidation(
        valid=not invalid and not malformed and not missing,
        used_ids=used,
        invalid_ids=tuple((*invalid, *malformed)),
        duplicate_ids=duplicates,
        missing_required=missing,
    )


def normalize_citation_format(
    answer: str,
    valid_ids: frozenset[str],
) -> tuple[str, bool]:
    def replace(match: re.Match[str]) -> str:
        ids = tuple(part.strip() for part in match.group(1).split(","))
        return "".join(f"[{item}]" for item in ids) if ids and all(item in valid_ids for item in ids) else match.group(0)
    normalized = _COMBINED_CITATION_RE.sub(replace, answer)
    return normalized, normalized != answer
```

For grounded factual answers with non-empty sources, no valid citation is `missing_required=True`. For ungrounded answers, remove S-like tokens before transport and record `ungrounded_citation_removed`.

- [ ] **Step 4: Add one bounded repair and a deterministic safe fallback**

`validate_or_repair_answer()` performs exactly:

```text
draft validation
  -> safe format normalization
  -> validation
  -> at most one context/source-map constrained repair or regenerate call
  -> validation
  -> safe fallback if still invalid
```

Tests use a counting repair callback:

```python
answer, validation = validate_or_repair_answer(
    draft="无效 [不存在]",
    context=context,
    source_map=source_map,
    grounding_mode="grounded",
    repair=repair_spy,
)
assert repair_spy.call_count == 1
assert validation.repair_attempts == 1
assert "无效 [不存在]" not in answer
```

Safe fallback states that a reliable cited answer could not be generated and leaves real public sources available. It does not return the invalid draft and does not call Planner/Retriever again.

- [ ] **Step 5: Update prompts and history projection**

Replace prompt citation rules with:

```text
每个知识库事实必须在句末使用本轮证据 ID，例如 [S01]。
综合多个来源时分别使用多个 ID，例如 [S01][S03]。
只能复制已知信息中出现的 S ID；不能生成标题引用、组合标签或未知 ID。
所有历史 assistant 内容仅用于连贯，均不是本轮证据；历史中的引用标记已失效。
```

Change `_conversation_messages()` so every assistant turn receives the non-current-evidence prefix, regardless of old grounding mode. Neutralize historical `[Snn]` as `[历史引用已失效]` before prompt injection. Do not alter stored user/assistant roles.

- [ ] **Step 6: Integrate validation into synchronous answer generation**

The grounded chain creates source map/context before answer generation, validates before returning, and marks a turn committable only after validation. Free answers have empty source map and `grounding_mode="ungrounded"`. Add `citation_validation` to private/internal packet metadata and only expose aggregate warning fields through the public schema.

- [ ] **Step 7: Run focused citation and answer regressions**

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_citations.py `
  tests/test_prompts.py `
  tests/test_chain_assets.py `
  tests/test_conversation_memory.py `
  tests/test_rag_empty_recovery.py -q
```

Expected: PASS; repair callback count never exceeds one; no invalid draft appears in returned answer fixtures or stored turns.

**Task acceptance:** every grounded answer uses a current local source map; deterministic validity and M3 semantic support remain separate; invalid drafts are blocked before transport/memory.

---

## 7. Task 4: Single Execution Service, JSON/SSE Serializers, and React Contract

**Corresponding specs:** `EXEC-P0-01..08`, `CITE-P0-07`, `CITE-P0-09`, `SAFE-TRUST-P0-01..03`.

**Files:**

- Create: `src/rag/execution.py`
- Create: `src/rag/serializers.py`
- Create: `tests/test_rag_execution.py`
- Modify: `src/rag/chain.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Modify: `backend/sse.py`
- Modify: `tests/test_sse.py`
- Modify: `tests/test_conversation_api.py`
- Modify: `frontend/react-app/src/types/index.ts`
- Modify: `frontend/react-app/src/api/sse.ts`
- Modify: `frontend/react-app/src/api/sse.test.ts`
- Modify: `frontend/react-app/src/store/chatStore.ts`
- Modify: `frontend/react-app/src/store/chatStore.test.ts`
- Modify: `frontend/react-app/src/components/chat/MessageBubble.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageBubble.test.tsx`

**Interfaces:**

- Produces: `AskExecutionInput`, `RAGExecutionService.execute(input, projection, trace) -> ResponsePacket`.
- Produces: `response_packet_to_ask_response(packet)`, `response_packet_to_sse_events(packet, token_chunk_size=32)`.
- `RAGChain.execute()` delegates to the service; `RAGChain.ask()` remains a compatibility adapter during this plan.

- [ ] **Step 1: Write failing single-execution and serializer tests**

```python
def test_execute_calls_each_business_stage_once(service_with_spies):
    packet = service_with_spies.execute(request_fixture(), EMPTY_PROJECTION, RequestTrace())
    assert service_with_spies.planner.plan.call_count == 1
    assert service_with_spies.retriever.search.call_count == 1
    assert service_with_spies.media.find_bundle_for_retrieval.call_count == 1
    assert service_with_spies.answer_llm.invoke.call_count == 1
    assert packet.citation_validation.valid


def test_serializers_do_not_call_business_dependencies(packet, dependency_spies):
    json_payload = response_packet_to_public_dict(packet)
    events = list(response_packet_to_sse_events(packet, token_chunk_size=3))
    assert dependency_spies.total_calls == 0
    assert "".join(event.data["token"] for event in events if event.event == "token") == packet.answer
    assert [event for event in events if event.event == "done"][0].data["answer"] == packet.answer


def test_invalid_draft_is_never_an_sse_token(service_with_invalid_first_draft):
    packet = service_with_invalid_first_draft.execute(request_fixture(), EMPTY_PROJECTION, RequestTrace())
    wire = "".join(response_packet_to_sse_strings(packet))
    assert service_with_invalid_first_draft.invalid_draft not in wire
```

Run:

```powershell
conda run -n 1999wiki python -m pytest tests/test_rag_execution.py tests/test_sse.py -q
```

Expected: FAIL because sync and SSE still maintain separate generation paths.

- [ ] **Step 2: Move the complete pipeline into `RAGExecutionService`**

Define the request contract:

```python
@dataclass(frozen=True)
class AskExecutionInput:
    question: str
    category: str | None
    route_options: Mapping[str, bool]
    action_payload: Mapping[str, object] | None
    memory_status: Literal["disabled", "new", "hit", "expired"] = "disabled"
    memory_turns_used: int = 0


class RAGExecutionService:
    def execute(
        self,
        request: AskExecutionInput,
        conversation: ConversationProjection = EMPTY_PROJECTION,
        trace: RequestTrace | NullTrace | None = None,
    ) -> ResponsePacket:
        active_trace = trace or NullTrace()
        return self._execute_once(request, conversation, active_trace)
```

The method owns, in order: plan, EntityRef, authorization, optional retrieval, ownership, outcome/final route, media, source map/context, answer/free/insufficiency/error, citation validation/repair, sanitizer, packet freeze. No endpoint or serializer may call these dependencies.

`RAGChain.execute()` is the compatibility facade with the exact signature:

```python
def execute(
    self,
    question: str,
    category: str | None = None,
    route_options: Mapping[str, bool] | None = None,
    action_payload: Mapping[str, object] | None = None,
    conversation: ConversationProjection | None = None,
    memory_status: str = "disabled",
    memory_turns_used: int = 0,
    trace: RequestTrace | NullTrace | None = None,
) -> ResponsePacket:
    request = AskExecutionInput(
        question=question,
        category=category,
        route_options=freeze_value(route_options or {}),
        action_payload=freeze_value(action_payload) if action_payload else None,
        memory_status=normalize_memory_status(memory_status),
        memory_turns_used=max(0, memory_turns_used),
    )
    return self._execution_service.execute(request, conversation or EMPTY_PROJECTION, trace)
```

After planning, the execution service freezes `memory_info={status, turns_used, rewrite_mode}` into `ResponsePacket`; endpoints do not append or recompute memory metadata. Each endpoint derives `memory_status/turns_used` from the acquired lease and passes them to `chain.execute()`.

Split LLM construction in `RAGChain`:

```python
planner_llm = ChatOpenAI(
    base_url=self._cfg.llm.base_url,
    api_key=self._cfg.llm.api_key,
    model=self._cfg.llm.model,
    temperature=0,
)
answer_llm = ChatOpenAI(
    base_url=self._cfg.llm.base_url,
    api_key=self._cfg.llm.api_key,
    model=self._cfg.llm.model,
    temperature=getattr(self._cfg.llm, "temperature", 0.3),
)
```

Use the configured answer temperature when a current config field exists; the Planner remains exactly `0`.

- [ ] **Step 3: Implement one public projection and two pure serializers**

`response_packet_to_public_dict()` uses explicit fields, never `dataclasses.asdict()` on an internal packet:

```python
return {
    "answer": packet.answer,
    "grounding_mode": packet.grounding_mode,
    "sources": [source_to_public(row) for row in retrieval.sources],
    "media": [media_to_public(row) for row in retrieval.media],
    "media_panels": [panel_to_public(row) for row in retrieval.media_panels],
    "route": route_to_public(retrieval.route_decision),
    "omitted_actions": actions_to_public(retrieval.omitted_actions),
    "failure_actions": actions_to_public(retrieval.failure_actions),
    "memory": dict(packet.memory_info),
}
```

SSE emits `sources`, validated `token` chunks and `done`. The concatenated tokens equal `done.answer` exactly. It may emit status before validation, but status cannot contain draft text. `sources` and `done` reuse the same frozen public values.

- [ ] **Step 4: Replace both FastAPI endpoint implementations**

`/ask`:

```text
acquire lease -> execute once -> validate AskResponse -> mark completed turn -> release -> return
```

`/ask/stream`:

```text
acquire lease -> execute once -> serialize validated packet -> check disconnect between events/chunks
-> yield done -> mark completed turn -> release
```

Delete `_chain_retrieve()` and `_chain_stream_llm()` from `backend/sse.py`. Delete endpoint TypeError fallbacks that silently call reduced signatures in production; test doubles must implement the explicit `execute` protocol. Preserve the current cancellation rule: disconnect before `done` does not commit a turn.

- [ ] **Step 5: Expand Pydantic and TypeScript public contracts**

Add fields without removing legacy display fields:

```text
SourceItem: citation_id, entity_type, entity_id
RouteInfo: semantic_intents, proposed_route, effective_route, retrieval_outcome, route_reason
ActionItem: action_type, entity_id, semantic_intents
AskResponse/Message: grounding_mode
```

`frontend/react-app/src/api/sse.ts` sends `action_type/entity_id/semantic_intents`. Existing `freeSupplement` remains the UI toggle and defaults false. `MessageBubble` displays each source as `[S01] 展示名称`; it does not infer citation IDs from array indices. Ungrounded text keeps the server-generated explicit prefix and has no source list.

- [ ] **Step 6: Test parity, call counts, cancellation and old clients**

Add tests that compare normalized `/ask` and `/ask/stream` output for entity, semantic intents, route decision, source IDs/order, source map, media IDs, actions and memory metadata. Independent requests may differ in answer wording, but each endpoint must use one execution internally.

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_rag_execution.py `
  tests/test_sse.py `
  tests/test_conversation_api.py `
  tests/test_chain_assets.py `
  tests/test_rag_empty_recovery.py -q
npm --prefix frontend/react-app test -- `
  src/api/sse.test.ts `
  src/store/chatStore.test.ts `
  src/components/chat/MessageBubble.test.tsx
npm --prefix frontend/react-app run build
```

Expected: all commands PASS; source events contain no answer draft; cancellation before done leaves memory generation unchanged; a legacy request without conversation/citation/free options still returns answer/sources/media.

**Task acceptance:** both endpoints are adapters over one execution protocol; serializers are pure; packet parity is structural and testable; P0 SSE never exposes pre-validation model tokens.

---

## 8. Task 5: Short-Term Memory Evidence Isolation and Entity Anchors

**Corresponding specs:** `MEMQ-P0-01..03`, `MEMQ-P0-07..08`, `CITE-P0-10`, `EXEC-P0-08`.

**Files:**

- Modify: `src/rag/conversation.py`
- Modify: `src/rag/query_plan.py`
- Modify: `src/rag/execution.py`
- Modify: `backend/main.py`
- Modify: `backend/sse.py`
- Modify: `tests/test_conversation_memory.py`
- Modify: `tests/test_conversation_api.py`
- Modify: `tests/test_sse.py`
- Modify: `scripts/verify_rag_conversation_memory.py`
- Modify: `tests/test_verify_rag_conversation_memory.py`

**Interfaces:**

- Consumes: validated `ResponsePacket`, `EntityRef`, current `requested_intents` and existing `ConversationMemoryStore` lease/generation semantics.
- Produces: `ConversationTurn.entity_id`, `ConversationProjection.last_entity_ref`, `neutralize_historical_citations()`, `history_messages()`.
- Preserves: six turns, 30-minute TTL, process-local storage, one worker, generation-safe clear/cancel and no persistence.

- [ ] **Step 1: Write failing history isolation and EntityRef tests**

```python
def test_every_assistant_history_message_is_marked_non_current_evidence():
    grounded = turn(answer="旧事实 [S01]", grounding_mode="grounded")
    ungrounded = turn(answer="旧开放回答 [S02]", grounding_mode="ungrounded")
    messages = history_messages(project_turns([grounded, ungrounded]))
    assistant_text = [message.content for message in messages if isinstance(message, AIMessage)]
    assert all(text.startswith("[历史对话，仅用于连贯，非本轮证据]") for text in assistant_text)
    assert all("[S01]" not in text and "[S02]" not in text for text in assistant_text)


def test_history_anchor_requires_entity_type_and_entity_id():
    projection = project_turns([turn(entity="同名", entity_type="story", entity_id="s-1")])
    assert projection.last_entity_ref.ownership_key == ("story", "s-1")
    incomplete = project_turns([turn(entity="同名", entity_type="story", entity_id=None)])
    assert incomplete.last_entity_ref is None


def test_unvalidated_answer_is_not_committed(memory_store, invalid_packet):
    release_with_packet(memory_store, invalid_packet)
    assert memory_store_snapshot(memory_store).turns == ()
```

Run:

```powershell
conda run -n 1999wiki python -m pytest tests/test_conversation_memory.py tests/test_conversation_api.py -q
```

Expected: FAIL because current turns lack `entity_id` and grounded assistant history has no explicit non-evidence marker.

- [ ] **Step 2: Extend conversation contracts with complete owner identity**

Add `entity_id` to `ConversationTurn` and `build_conversation_turn()`:

```python
@dataclass(frozen=True)
class ConversationTurn:
    original_question: str
    standalone_question: str
    answer: str
    entity: str | None
    entity_type: str | None
    entity_id: str | None
    requested_intents: tuple[str, ...]
    category: str | None
    grounding_mode: GroundingMode
    completed_at: datetime
```

`ConversationProjection.last_entity_ref` scans newest-to-oldest and returns a ref only when name, type and ID are all present. `planner_payload()` includes `last_entity_id`; old in-memory turns created by compatibility fixtures remain readable but cannot become strict ownership anchors without the ID.

- [ ] **Step 3: Centralize historical message projection**

Move history construction out of `chain.py` into `conversation.py`:

```python
_HISTORY_PREFIX = "[历史对话，仅用于连贯，非本轮证据]\n"
_STALE_CITATION_RE = re.compile(r"\[S\d{2,}\]")


def neutralize_historical_citations(answer: str) -> str:
    return _STALE_CITATION_RE.sub("[历史引用已失效]", answer)


def history_messages(projection: ConversationProjection) -> list[BaseMessage]:
    messages = []
    for turn in projection.turns:
        messages.append(HumanMessage(content=turn.original_question))
        messages.append(AIMessage(content=_HISTORY_PREFIX + neutralize_historical_citations(turn.answer)))
    return messages
```

No history source map/context/media is injected. Current explicit action > current explicit entity/intents > category > reliable history anchor remains the planner precedence. History never sets route authorization fields.

- [ ] **Step 4: Enforce one commit function for sync and SSE**

Add a helper that accepts only a validated packet:

```python
def build_completed_turn(
    request: AskExecutionInput,
    packet: ResponsePacket,
    completed_at: datetime,
) -> ConversationTurn | None:
    if packet.turn_outcome not in {"grounded", "ungrounded"}:
        return None
    if packet.grounding_mode == "grounded" and not packet.citation_validation.valid:
        return None
    entity_ref = packet.retrieval_packet.entity_ref
    return build_conversation_turn(
        original_question=request.question,
        standalone_question=packet.retrieval_packet.plan.normalized_query,
        answer=packet.answer,
        entity=entity_ref.entity_name if entity_ref else None,
        entity_type=entity_ref.entity_type if entity_ref else None,
        entity_id=entity_ref.entity_id if entity_ref else None,
        requested_intents=packet.retrieval_packet.requested_intents,
        category=request.category,
        grounding_mode=packet.grounding_mode,
        completed_at=completed_at,
    )
```

Both endpoints call this helper only after public schema validation. SSE calls it only after yielding `done`; cancellation, serializer failure, repair intermediate output and error packets do not commit.

- [ ] **Step 5: Preserve lifecycle and non-persistence gates**

Extend existing tests for TTL expiry, clear generation, concurrent lease, cancel, 6-turn trimming, session isolation and process restart. Add a write-spy test that fails if conversation code imports or calls Milvus, MinIO, MySQL, artifact writers or evaluator corpus writers.

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_conversation_memory.py `
  tests/test_conversation_api.py `
  tests/test_sse.py `
  tests/test_verify_rag_conversation_memory.py -q
```

Expected: PASS; every stored owner anchor has a complete key or is explicitly unusable for strict inheritance; all assistant history is non-current evidence.

**Task acceptance:** memory improves continuity without becoming evidence or authorization; old citations cannot validate a new answer; only fully validated, transport-complete turns enter process-local memory.

---

## 9. Task 6: Complete Stage Spans and Performance Accounting

**Corresponding specs:** `TRACE-P0-02..08`, remaining `TRACE-P0-03/06`, `OWN-P0-09`, `ROUTE-P0-10`.

**Files:**

- Modify: `src/rag/tracing.py`
- Modify: `src/rag/execution.py`
- Modify: `src/rag/retriever.py`
- Modify: `src/rag/reranker.py`
- Modify: `src/assets/huiji_registry.py`
- Modify: `src/rag/citations.py`
- Modify: `src/rag/serializers.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Modify: `backend/sse.py`
- Modify: `tests/test_rag_tracing.py`
- Modify: `tests/test_rag_execution.py`
- Modify: `tests/test_sse.py`

**Interfaces:**

- Consumes: the `RequestTrace` created by each endpoint and count-only module diagnostics.
- Produces: complete `TraceSnapshot` containing stage spans plus `model_first_token_ms`, `validated_ready_ms`, `visible_first_token_ms`, `completed_ms`.
- Public transport exposes only sanitized timing/count/status fields; frontend may ignore them.

- [ ] **Step 1: Write failing full-span and timing tests**

```python
REQUIRED_STAGE_SPANS = {
    "memory.acquire", "planner.llm", "planner.normalize", "entity.resolve", "route.resolve",
    "retrieval.structured", "retrieval.bm25", "retrieval.dense", "retrieval.fusion",
    "retrieval.rerank", "retrieval.expand", "retrieval.allocate", "media.attach",
    "source_map.build", "answer.llm", "citation.validate", "citation.repair",
    "response.serialize",
}


def test_success_trace_contains_all_applicable_stage_spans(executed_trace):
    names = {span.name for span in executed_trace.spans}
    assert REQUIRED_STAGE_SPANS - {"citation.repair"} <= names
    assert executed_trace.validated_ready_ms <= executed_trace.visible_first_token_ms
    assert executed_trace.visible_first_token_ms <= executed_trace.completed_ms


@pytest.mark.parametrize("failure_stage", ["planner.llm", "retrieval.dense", "citation.repair", "response.serialize"])
def test_failed_stage_is_closed_and_request_duration_reconciles(failure_stage):
    snapshot = execute_failure_fixture(failure_stage)
    assert exactly_one_error_span(snapshot, failure_stage)
    assert all(span.duration_ms >= 0 for span in snapshot.spans)
    assert snapshot.completed_ms >= max(span.end_offset_ms for span in snapshot.spans)
```

- [ ] **Step 2: Instrument execution and retrieval stages**

Pass `trace` explicitly; do not use hidden module-global request state. Wrap each named stage at the narrowest real operation. `planner.llm` covers only model I/O, while `planner.normalize` covers JSON/schema/fallback. Retrieval sub-spans expose only:

```python
{
    "candidate_k": int,
    "result_count": int,
    "owner_before": int,
    "owner_after": int,
    "owner_mismatch": int,
    "missing_owner_metadata": int,
    "chars_used": int,
    "coverage_shortfall_count": int,
}
```

`route.resolve` exposes enumerated proposed/effective route, outcome and reason. `citation.validate/repair` expose source count, used/invalid count and repair attempts. No span includes entity name, question, answer, context, prompt, source content, conversation ID, local path or credentials.

- [ ] **Step 3: Account for answer and transport timing correctly**

Record model first token in the answer LLM callback/stream adapter even though P0 buffers the answer. Mark `validated_ready` after citation validation and packet freeze. In `/ask`, mark visible first token immediately before returning the validated response. In SSE, mark it immediately before the first validated `token` event. Mark completed immediately before the final response/done serialization boundary.

The endpoint creates the request trace before acquiring memory and retains it separately from the frozen `ResponsePacket`:

```python
trace = RequestTrace()
with trace.span("memory.acquire"):
    lease = await acquire_lease(memory_store, req.conversation_id)
packet = chain.execute(
    question=req.question,
    category=req.category,
    route_options=req.route_options.model_dump(),
    action_payload=req.action_payload.model_dump() if req.action_payload else None,
    conversation=lease.projection,
    memory_status=lease.status,
    memory_turns_used=len(lease.projection.turns),
    trace=trace,
)
with trace.span("response.serialize"):
    payload = response_packet_to_public_dict(packet)
trace.mark_visible_first_token()
trace.mark_completed()
payload["trace"] = trace_snapshot_to_public(trace.snapshot())
```

SSE creates the final `done` event after the transport marks. Serializers remain pure because they consume a frozen `TraceSnapshot`; they never mutate the trace or call business services.

- [ ] **Step 4: Implement trace fail-open and acceptance fail-closed**

Any internal trace exception replaces tracing with `NullTrace`, adds `trace_warning="trace_unavailable"`, and allows the production answer to continue. The evaluator treats missing/incomplete/non-reconcilable spans as `SEV-2`; production does not turn a tracing outage into a fabricated knowledge answer.

- [ ] **Step 5: Run trace, serializer and sensitive-field tests**

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_rag_tracing.py `
  tests/test_rag_execution.py `
  tests/test_retriever.py `
  tests/test_sse.py `
  tests/test_conversation_api.py -q
```

Then scan the public fixtures and trace snapshots:

```powershell
rg -n "question|answer|prompt|context|conversation_id|local_relpath|[A-Za-z]:\\|api_key|secret" `
  tests/fixtures eval/rag_full_chain `
  -g '*trace*.json' -g '*response*.json'
```

Expected: tests PASS; scan returns no real transcript/path/credential value. Schema field names in source code are not a failure; generated evidence containing those sensitive values is.

- [ ] **Step 6: Produce a comparable post-instrumentation timing sample**

Run a deterministic sample manifest against the same hardware/model/data as Task 0:

```powershell
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
conda run -n 1999wiki python scripts/evaluate_rag_full_chain.py sample `
  --seed 1999 `
  --output "eval/rag_full_chain/trust-v2-span-sample-$RunStamp.jsonl"
```

Expected: sample creation is read-only and deterministic for the same inventory/seed. Do not optimize K/reranker/validation at this stage; optimization waits until Task 8 shows trustworthy M2/M3/M4 gates pass and identifies the dominant P95 span.

**Task acceptance:** every applicable stage is measurable and closed on success/error; model, validation, user-visible and total times are distinct; instrumentation cannot leak content or silently make acceptance pass.

---

## 10. Task 7: Evaluator V2 for Ownership, Route, Citation, Memory, and Protected Snapshots

**Corresponding specs:** `MEMQ-P0-04..06`, `EVAL-TRUST-P0-01..09`, `GATE-TRUST-P0-01..09`, `GATE-TRUST-P0-12`.

**Files:**

- Modify: `src/rag_eval/contracts.py`
- Modify: `src/rag_eval/client.py`
- Modify: `src/rag_eval/inventory.py`
- Modify: `src/rag_eval/sampling.py`
- Modify: `src/rag_eval/conversation.py`
- Modify: `src/rag_eval/deterministic.py`
- Modify: `src/rag_eval/judge.py`
- Modify: `src/rag_eval/scoring.py`
- Modify: `src/rag_eval/reporting.py`
- Modify: `src/rag_eval/runner.py`
- Modify: `scripts/evaluate_rag_full_chain.py`
- Modify: `eval/rag_full_chain_thresholds.v1.json`
- Modify: `tests/test_rag_eval_contracts.py`
- Modify: `tests/test_rag_eval_client.py`
- Modify: `tests/test_rag_eval_inventory.py`
- Modify: `tests/test_rag_eval_sampling.py`
- Modify: `tests/test_rag_eval_conversation.py`
- Modify: `tests/test_rag_eval_deterministic.py`
- Modify: `tests/test_rag_eval_judge.py`
- Modify: `tests/test_rag_eval_scoring.py`
- Modify: `tests/test_rag_eval_reporting.py`
- Modify: `tests/test_rag_eval_runner.py`

**Interfaces:**

- Extends `EvalCase` with `expected_ownership_key`, `route_options`, `action_payload`, `expected_retrieval_outcome`, `expected_effective_route`, `conversation_mode`.
- Extends `ObservedExchange` with owner-aware sources/media, citation/source map, grounding mode, route decision, stage trace and four timing boundaries.
- Produces `ProtectedDataSnapshot` for Milvus, configured MinIO buckets/prefixes, protected MySQL tables and processed artifact hashes.
- Produces memory triplets: `memory_off`, `memory_on`, `oracle_standalone`.
- Produces immutable automatic evidence files: `run_manifest.v2.json`, `sample_manifest.v2.jsonl`, `case_results.v2.jsonl`, `module_summary.v2.json`, `evaluation_report.v2.md`, `pre_protected_snapshot.v2.json`, `post_protected_snapshot.v2.json`, `memory_pair_results.v1.jsonl`, `stage_latency.v1.json`, `adjudication_queue.v2.jsonl`, and `human_audit_manifest.v1.jsonl`.

- [ ] **Step 1: Write failing v2 contract and sample-coverage tests**

```python
def test_v2_sample_manifest_covers_every_available_entity_type_and_route_mode(inventory, thresholds):
    cases = build_sample_manifest(inventory, thresholds, seed=1999)
    available_types = {entity.entity_type for entity in inventory.entities.values() if entity.child_ids}
    sampled_types = {case.expected_ownership_key[0] for case in cases if case.expected_ownership_key}
    assert available_types <= sampled_types
    assert {(False, "empty"), (True, "empty"), (True, "partial"), (True, "failed")} <= {
        (bool(case.route_options.get("free_supplement")), case.expected_retrieval_outcome)
        for case in cases if case.expected_retrieval_outcome
    }


def test_samples_do_not_contain_fixed_real_entity_expectations(sample_source_text):
    assert not re.search(r"char:\d+", sample_source_text)
    assert not re.search(r"EXPECTED_(ROLE|ENTITY|SKILL|VOICE)", sample_source_text)


def test_human_audit_size_is_stratified_and_reproducible():
    first = select_human_audit(case_ids, seed=1999)
    second = select_human_audit(case_ids, seed=1999)
    assert first == second
    assert len(first) == max(12, math.ceil(0.20 * len(set(case_ids))))
```

Run:

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_rag_eval_contracts.py `
  tests/test_rag_eval_sampling.py `
  tests/test_rag_eval_conversation.py -q
```

Expected: FAIL because existing contracts do not model route options, owner type+ID or memory triplets.

- [ ] **Step 2: Upgrade inventory identity and read-only protected snapshots**

Key entities by `(entity_type, entity_id)`, retaining aliases, child IDs by intent, parent ownership and media ownership. Dynamic samples select each available type and low/medium/high data volume; no production assertion contains a fixed entity.

Add:

```python
@dataclass(frozen=True)
class ProtectedDataSnapshot:
    milvus: MilvusSnapshot
    minio_inventories: Mapping[str, Mapping[str, object]]
    mysql_tables: Mapping[str, Mapping[str, object]]
    artifacts: Mapping[str, Mapping[str, object]]


def capture_protected_snapshot(cfg: Config) -> ProtectedDataSnapshot:
    return ProtectedDataSnapshot(
        milvus=capture_milvus_snapshot(cfg),
        minio_inventories=capture_configured_minio_inventories(cfg),
        mysql_tables=capture_mysql_table_digests(cfg),
        artifacts=capture_artifact_digests(cfg),
    )


def compare_protected_snapshots(
    before: ProtectedDataSnapshot,
    after: ProtectedDataSnapshot,
) -> list[str]:
    changes = compare_snapshots(before.milvus, after.milvus)
    for section in ("minio_inventories", "mysql_tables", "artifacts"):
        if getattr(before, section) != getattr(after, section):
            changes.append(f"{section} changed")
    return changes
```

Reuse read-only MinIO listing/hash collection from `src.huiji_rag.minio_strict.capture_object_inventory`; do not call upload/delete APIs. Snapshot configured production buckets/prefixes used by RAG, including `reverse1999-assets/reverse1999` and active Milvus object storage scope when configured. For MySQL, begin a read-only transaction before any snapshot query and record each protected wiki table's row count plus deterministic ordered primary-key/content digest; if read-only mode cannot be established, preflight fails before evaluation. Never emit password or row content. Artifacts record relative path, size and SHA-256 for evaluator inputs and `data/processed/huiji/**`.

- [ ] **Step 3: Extend HTTP/SSE collection and deterministic trust gates**

Client collection must preserve:

```text
entity_ref/ownership_key
semantic_intents
proposed/effective route + outcome + reason
source IDs/order + citation IDs + source map
media IDs + owner fields + panels/cursors
grounding_mode + answer
failure/omitted actions
memory metadata
stage spans + model/validated/visible/total timing
```

Because P0 buffers and validates the full answer before the SSE `sources` event, evaluator `retrieval_ms` must be derived from the server's retrieval stage spans, not from HTTP time-to-sources. HTTP time-to-sources is recorded separately as `packet_ready_ms`; user-visible TTFT remains the externally observed first validated token time.

Add deterministic events with these exact severities:

```text
RETR.CROSS_ENTITY_SOURCE           SEV-1
MEDIA.CROSS_ENTITY_MEDIA           SEV-1
ROUTE.UNAUTHORIZED_GENERAL         SEV-1
ROUTE.INTENT_OVERWRITTEN           SEV-2
CITE.UNKNOWN_OR_STALE_ID           SEV-1
CITE.INVALID_DRAFT_TRANSPORTED     SEV-1
CITE.SAFE_FALLBACK_USED            SEV-2
RELY.SYNC_STREAM_PACKET_DIVERGENCE SEV-2
RELY.STAGE_SPAN_INCOMPLETE         SEV-2
READY.READ_ONLY_DRIFT              SEV-1
```

Parity compares entity, intents, route, source IDs/order, citation map, media IDs, actions and memory metadata. It does not require two independent requests to share an in-memory object or produce byte-identical natural language.

- [ ] **Step 4: Add route, citation and shortfall samples**

Derive route cases from current artifacts plus existing D4 seeds:

- default closed + Planner proposal `llm_general`;
- toggle on with sufficient, partial and empty evidence;
- isolated endpoint integration with a deterministic failing Retriever, using the real `/ask` and `/ask/stream` handlers but no production fault-injection switch;
- explicit `force_free_supplement` recovery action;
- `meta_question`, nonexistent entity, false premise and out-of-KB request;
- an owner whose available sources are below global `top_k`, selected dynamically or covered by a synthetic automated fixture when no natural sample exists.

Grounded cases require valid current citations. Ungrounded cases require the explicit disclaimer, empty knowledge source map and no `[Snn]`. Partial cases require shortfall disclosure and no automatic ungrounded mixture.

- [ ] **Step 5: Execute memory off/on/oracle triplets through M3**

For each dynamic conversation track:

```text
memory_off:       follow-up sent without conversation_id
memory_on:        original turn + follow-up share one new conversation_id
oracle_standalone: follow-up rewritten with explicit entity/intents and no history
```

Run the existing independent M3 judge for all three final answers. Report entity accuracy, intent exact/F1, source ownership, groundedness, relevance, completeness, citation validity/support, refusal correctness, Planner P95, retrieval P95, validated TTFT P95 and total P95. Memory-on must pass absolute gates; quality gain over memory-off and gap to oracle are descriptive comparisons, not permission for memory-off to be intentionally broken.

Add controlled tracks where the first assistant answer contains an ungrounded/error fixture. The follow-up must not repeat it as a fact or current citation; current retrieval evidence wins.

- [ ] **Step 6: Add reproducible stratified human-audit evidence**

After automatic gates, create `human_audit_manifest.v1.jsonl` with exactly `max(12, ceil(20% * unique_case_count))` unique cases, stratified across entity type, D1-D4, JSON/SSE, memory mode and free-supplement mode. Store seed, case IDs and evidence references, not duplicated transcript bodies. Extend finalize to accept `human_audit_results.v1.jsonl` and require every selected case to have a reviewed disposition.

Each result line uses this reviewed schema:

```json
{"schema_version":"rag_eval.human_audit/v1","case_id":"case-id-from-manifest","reviewer":"local-review","decision":"pass","severity":"PASS","notes":"evidence reviewed","evidence_sha256":"64-lowercase-hex"}
```

`decision` is `pass` or `fail`; `severity` is `PASS` or `SEV-4..SEV-0`; `evidence_sha256` must match the referenced immutable case result. Finalize rejects missing/duplicate case IDs, unknown cases, invalid hashes or a selected failure that is absent from final severity aggregation.

Each adjudication result line uses:

```json
{"schema_version":"rag_eval.adjudication_result/v2","case_id":"case-id-from-queue","event_code":"CITE.UNKNOWN_OR_STALE_ID","decision":"confirm","severity":"SEV-1","reason":"automatic evidence confirmed","reviewer":"local-review"}
```

`decision` is `confirm`, `dismiss` or `adjust`; `adjust` requires a reviewed severity. Finalize rejects a result not present in the immutable queue and records every dismissal/adjustment in the final report rather than modifying `case_results.v2.jsonl`.

- [ ] **Step 7: Preserve fixed thresholds and report stage P95**

Keep these values unchanged:

```json
{
  "retrieval_p95_ms": 5000,
  "ttft_p95_ms": 15000,
  "total_p95_ms": 45000
}
```

Add `validated_ready_p95_ms` and individual stage P95 as diagnostics without using them to weaken fixed gates. Report before/after baseline, dominant stage and whether complete-answer citation buffering changed visible TTFT.

- [ ] **Step 8: Run the entire evaluator test suite**

```powershell
conda run -n 1999wiki python -m pytest `
  tests/test_rag_eval_contracts.py `
  tests/test_rag_eval_inventory.py `
  tests/test_rag_eval_sampling.py `
  tests/test_rag_eval_client.py `
  tests/test_rag_eval_deterministic.py `
  tests/test_rag_eval_judge.py `
  tests/test_rag_eval_conversation.py `
  tests/test_rag_eval_scoring.py `
  tests/test_rag_eval_reporting.py `
  tests/test_rag_eval_runner.py -q
```

Expected: PASS; tests prove preflight stops before requests when protected snapshot capture or judge identity fails, and that any post-run snapshot drift forces `SEV-1`.

**Task acceptance:** evaluator expectations are artifact-derived and entity-generic; route/citation/memory/trace failures have stable severity; all protected state is snapshotted read-only before and after; random audit is reproducible.

---

## 11. Task 8: Full Regression, Real-Service Acceptance, and Performance Remediation

**Corresponding specs:** `GATE-TRUST-P0-01..12`, `GATE-TRUST-P0-10..11`, all P0 completion criteria.

**Files:**

- Modify only when a failing gate identifies a root cause in files owned by Tasks 0-7.
- Modify: `docs/huiji-rag-runbook.md` with final commands, evidence layout, route/citation semantics and failure handling.
- Evidence output only: `eval/rag_full_chain/{unique-run-id}/**`.

**Interfaces:**

- Consumes: reviewed implementation from Tasks 0-7, live backend at `127.0.0.1:8000`, live React page, configured distinct judge and current read-only data.
- Produces: one final immutable automatic evidence directory, completed human audit, final report and P0 self-check.

- [ ] **Step 1: Run all automated backend and frontend regressions**

```powershell
conda run -n 1999wiki python -m pytest tests -q
npm --prefix frontend/react-app test
npm --prefix frontend/react-app run build
```

Expected: all tests PASS and frontend production build completes. Any skipped trust test must name a genuine unavailable external dependency; ownership, route, citation, execution, memory and serializer unit/integration tests may not be skipped.

- [ ] **Step 2: Run static genericity, write-operation and legacy-route scans**

```powershell
rg -n "char:[0-9]+|EXPECTED_(ROLE|ENTITY|SKILL_COUNT|VOICE_COUNT|LANGUAGE_COUNT)|exact or ranked" `
  src/rag src/rag_eval scripts/evaluate_rag_full_chain.py
rg -n "intent\s*[:=].*llm_general|requested_intents.*llm_general|packet_policy.*free_supplement" `
  src/rag backend frontend/react-app/src
rg -n "insert\(|upsert\(|delete\(|drop_collection|create_collection|put_object|remove_object|DELETE FROM|UPDATE |INSERT INTO" `
  src/rag_eval scripts/evaluate_rag_full_chain.py
```

Expected: no production hardcoded entity/count, no `exact or ranked`, no internal route-as-intent, and no data-write operation in evaluator code. Compatibility normalization may mention legacy strings only in the explicit API-boundary adapter and its tests.

- [ ] **Step 3: Verify runtime prerequisites and run v2 preflight**

```powershell
$Health = Invoke-RestMethod -Uri http://127.0.0.1:8000/health -Method Get -TimeoutSec 10
if ($Health.status -ne 'ok') { throw 'Backend health is not ok' }
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$EvidenceRoot = "eval/rag_full_chain/trust-v2-final-$RunStamp"
New-Item -ItemType Directory -Path $EvidenceRoot -ErrorAction Stop | Out-Null
conda run -n 1999wiki python scripts/evaluate_rag_full_chain.py preflight `
  --base-url http://127.0.0.1:8000 `
  --output "$EvidenceRoot/preflight.v2.json"
$Preflight = Get-Content -LiteralPath "$EvidenceRoot/preflight.v2.json" -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Preflight.allowed_to_run) { throw 'RAG trust-v2 preflight rejected the run' }
```

Expected: backend, Milvus, MinIO, MySQL, artifacts, answer model and distinct judge are reachable; protected snapshot is complete; no evaluated request starts if preflight rejects.

- [ ] **Step 4: Run the complete real-service evaluator**

```powershell
conda run -n 1999wiki python scripts/evaluate_rag_full_chain.py run `
  --base-url http://127.0.0.1:8000 `
  --seed 1999 `
  --output-root $EvidenceRoot
$AutomaticExitCode = $LASTEXITCODE
$RunDir = Get-ChildItem -LiteralPath $EvidenceRoot -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
if (-not $RunDir) { throw 'Evaluator did not create a run directory' }
@{
  schema_version = 'rag_eval.automatic_exit/v1'
  exit_code = $AutomaticExitCode
  run_dir = $RunDir
} | ConvertTo-Json | Set-Content -LiteralPath "$EvidenceRoot/automatic-exit.v1.json" -Encoding UTF8
Write-Output $RunDir
```

Required evidence:

- every current entity type with retrievable data is dynamically sampled;
- low/medium/high volume, D1-D4, single/multi-intent and media present/absent are represented;
- explicit owner cross-source/media count is zero;
- current live service covers default/toggle/explicit recovery and `sufficient/partial/empty`; the same run links the isolated real-endpoint integration evidence for `failed`, without exposing a production fault-injection control;
- grounded citation ID validity is 100%, and no invalid draft appears in transport evidence;
- `/ask` and `/ask/stream` packet fields are semantically equal;
- every applicable case has complete stage spans and four timing boundaries;
- memory-off/on/oracle tracks all receive M3 results;
- pre/post Milvus, MinIO, MySQL and artifact snapshots are equal.

- [ ] **Step 5: Complete the stratified human audit and finalize**

Review every row in `$RunDir/human_audit_manifest.v1.jsonl`. Record one result per selected case in `$RunDir/human_audit_results.v1.jsonl` using the evaluator's reviewed schema and evidence references. Review all automatic `SEV-1/SEV-2` candidates and deterministic/judge conflicts in `adjudication_queue.v2.jsonl`, then write `adjudication_results.v2.jsonl`; do not edit automatic case results.

```powershell
conda run -n 1999wiki python scripts/evaluate_rag_full_chain.py finalize `
  --run-dir $RunDir `
  --adjudication "$RunDir/adjudication_results.v2.jsonl" `
  --human-audit "$RunDir/human_audit_results.v1.jsonl"
```

Expected: selected case count equals `max(12, ceil(20% * unique_case_count))`; seed/strata/case IDs are preserved; judge/human agreement remains at least the existing 85% gate. A disagreement is resolved in the final evidence without rewriting automatic artifacts.

- [ ] **Step 6: Gate performance only after trust gates pass**

Read `module_summary.v2.json` and stage P95. If M2/M3/M4 or TRUST ownership/route/citation gates fail, fix those first and rerun directed tests plus the full evaluation. Only when those gates pass may the dominant span be optimized.

Permitted P0 remediation is limited to implementation defects already in this plan, such as duplicate stage calls, unnecessary repeated serialization, unstable tie-breaks or avoidable local scans. Do not lower the fixed thresholds, remove owner/citation/media checks, enlarge K without span evidence, disable reranker, rebuild vectors or modify data.

After any remediation, rerun Steps 1-5. Required final thresholds:

```text
retrieval P95 <= 5000 ms
user-visible TTFT P95 <= 15000 ms
total P95 <= 45000 ms
```

- [ ] **Step 7: Exercise the real React page**

Use Playwright against the current React chat page and dynamically selected evaluator cases. Verify:

- free supplement defaults off and toggle-on still shows retrieval status before any empty fallback;
- grounded answers show `[Snn]` in answer and matching source labels;
- partial evidence shows shortfall actions, not automatic free text;
- empty default mode offers a “自由补充重答” action;
- clicking that action returns an explicit ungrounded answer with no sources/citations;
- SSE content does not reveal an invalid citation draft and no UI fields contain local paths;
- clear/cancel behavior still prevents stale memory commits.

Run the automated browser contract:

```powershell
npm --prefix frontend/react-app run test:e2e -- conversation-memory.spec.ts
```

Expected: PASS. Record screenshot/network evidence paths in the human audit result; do not hardcode the sampled entity in the test source.

- [ ] **Step 8: Verify final report, hashes and runbook**

Update `docs/huiji-rag-runbook.md` with the exact 1999wiki commands, switch semantics, citation contract, severity meanings, evidence files and rerun rules.

```powershell
$Summary = Get-Content -LiteralPath "$RunDir/module_summary.v2.json" -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Summary.global_severity -in @('SEV-1', 'SEV-2', 'SEV-0')) { throw 'P0 acceptance failed' }
if (-not $Summary.snapshot_equal) { throw 'Protected snapshots drifted' }
Get-ChildItem -LiteralPath $RunDir -Recurse -File |
  Get-FileHash -Algorithm SHA256 |
  Sort-Object Path |
  ConvertTo-Json -Depth 4 |
  Set-Content -LiteralPath "$RunDir/final-files.sha256.json" -Encoding UTF8
```

Expected: global result is `PASS`, `SEV-4`, or explicitly accepted `SEV-3`; there is no `SEV-1/SEV-2`; report/run manifest/case results/human audit/snapshot equality agree; final hash inventory exists.

**Task acceptance:** real current data and both endpoints pass all trust gates; the React workflow matches server policy; fixed P95 gates pass; protected state is unchanged; evidence is complete and hash-pinned.

---

## 12. Deferred / Out of Scope

The following spec P1/P2 work is not an execution task in this plan:

- Milvus ownership expression pushdown, schema rebuild, entity index migration or re-embedding.
- Structured ambiguity selection UI beyond the P0 safe unresolved/insufficient behavior.
- Mixed grounded/ungrounded answer sections in one automatic response.
- Versioned local system-capability source for system meta questions.
- Sentence/paragraph-level validated streaming; P0 buffers and validates the complete answer.
- Online claim-level verifier, second-judge arbitration and long-term human gold set.
- Persistent execution replay, distributed packet cache and cross-worker queue.
- External OpenTelemetry collector, continuous SLO, alerting and concurrency load curves.
- Long-term conversation history, account persistence, cross-device memory and user profiles.
- Cross-entity comparison graph and relation-aware multi-entity subqueries.
- MinIO/Milvus/MySQL/artifact repair or migration triggered by evaluation findings.

No deferred item may be used to relabel a failed P0 requirement as complete.

---

## 13. P0 Traceability Matrix

| Spec IDs | Primary implementation | Automated verification | Real acceptance | Failure manifestation |
|---|---|---|---|---|
| `OWN-P0-01..02` | `contracts.py`, `entity_lexicon.py`, `query_plan.py` | `test_rag_contracts.py`, `test_entity_ownership.py`, `test_entity_lexicon.py`, `test_query_plan.py` | `GATE-TRUST-P0-01` dynamic entity types/ambiguity | unresolved identity is guessed or same-name owners merge |
| `OWN-P0-03..06` | `ownership.py`, `retriever.py`, `layered_expansion.py`, `huiji_registry.py` | ownership/retriever/media/pagination tests | `GATE-TRUST-P0-01..02` | source/media owner mismatch or other owner fills `top_k` |
| `OWN-P0-07..09` | owner action validation and retrieval diagnostics | ownership/action/debug schema tests | route/action samples and span evidence | foreign parent accepted, missing metadata hidden, shortfall not reported |
| `ROUTE-P0-01..04` | `route_policy.py`, `query_plan.py` | complete route table tests | `GATE-TRUST-P0-03..04` | route overwrites intent or toggle bypasses retrieval |
| `ROUTE-P0-05..10` | route action adapter, finalizer, public schema | route/action/compatibility tests | explicit recovery/meta/history/D4 samples | history/Planner authorizes open answer or route details leak free text |
| `CITE-P0-01..06` | `citations.py`, `prompts.py` | source-map/format/support-boundary tests | `GATE-TRUST-P0-05` + M3 | unknown/title/combined IDs or unsupported claims |
| `CITE-P0-07..11` | bounded repair, execution, serializers, history projection | citation/execution/SSE/memory tests | transport evidence and random audit | invalid draft or stale/ungrounded citation reaches user/memory |
| `EXEC-P0-01..05` | `execution.py`, `serializers.py`, backend endpoints | call-count/parity/serializer tests | `GATE-TRUST-P0-06` | endpoint repeats business stages or packet fields diverge |
| `EXEC-P0-06..08` | split Planner LLM config, stable tie-break, commit helper | repeat/cancel/commit tests | repeat cases and memory evidence | nondeterministic IDs, false replay claim or invalid turn commit |
| `TRACE-P0-01..04` | baseline, `tracing.py`, stage integration | trace lifecycle/attribute tests | baseline hash and `GATE-TRUST-P0-07` | no baseline, missing/error span or unobservable owner/route counts |
| `TRACE-P0-05..08` | endpoint transport timing and trace fallback | timing/redaction/failure tests | fixed P95 and complete span evidence | model TTFT passed off as visible TTFT, sensitive text, missing trace |
| `MEMQ-P0-01..03` | `conversation.py`, planner history anchor | memory/history/entity tests | memory-on track inspection | old assistant/citation treated as current evidence or owner ID absent |
| `MEMQ-P0-04..08` | conversation evaluator, M3, commit/lifecycle gates | evaluator conversation/runner tests | `GATE-TRUST-P0-08` | no final-answer judge, history error propagation, persistence/isolation failure |
| `SAFE-TRUST-P0-01..05` | frozen contracts, Pydantic/public serializers, trace redaction, snapshots | schema/sanitizer/write-spy/snapshot tests | pre/post protected snapshot equality | internal dict/path/credential leak or protected write |
| `EVAL-TRUST-P0-01..09` | evaluator v2 modules and compatibility adapters | complete `test_rag_eval_*.py` plus frontend tests | full run and React page | missing matrix dimension, unstable result, incomplete old-client support |
| `GATE-TRUST-P0-01..09` | runner sampling, triplets, random audit | sampling/runner/reporting tests | final automatic run + human audit | fixed role sample, missing stratum, no audit or non-reproducible evidence |
| `GATE-TRUST-P0-10..12` | M1-M5 aggregation, fixed thresholds, protected snapshot | scoring/reliability/inventory tests | final severity/P95/snapshot report | `SEV-1/2`, threshold breach or state drift |

---

## 14. Completion Self-Check

- [ ] `OWN-P0-01..09`: complete ownership key is propagated and every source/media/action stage enforces it without backfill.
- [ ] `ROUTE-P0-01..10`: semantic intent and route are separate; switch/action/outcome matrix matches the approved policy.
- [ ] `CITE-P0-01..11`: all grounded citations are current valid S IDs; invalid drafts never reach transport or memory.
- [ ] `EXEC-P0-01..08`: one request executes each business stage once; JSON/SSE consume the same packet contract; commit boundaries hold.
- [ ] `TRACE-P0-01..08`: baseline exists, all spans/timing boundaries are complete, fixed P95 gates pass and no sensitive content is recorded.
- [ ] `MEMQ-P0-01..08`: history is explicitly non-evidence, anchors include entity ID, memory triplets receive M3 and lifecycle/non-persistence gates pass.
- [ ] `SAFE-TRUST-P0-01..05`: public schemas are allow-listed and protected Milvus/MinIO/MySQL/artifact snapshots are equal.
- [ ] `EVAL-TRUST-P0-01..09`: all automated contract, matrix, call-count, failure, repeat, memory, compatibility and frontend tests pass.
- [ ] `GATE-TRUST-P0-01..12`: dynamic real samples, `/ask`, `/ask/stream`, React, stratified audit, M1-M5, fixed P95 and read-only close all pass.
- [ ] No real entity/count sealing, `exact or ranked`, internal `llm_general` intent, invalid citation transport or evaluator write operation remains.
- [ ] Final global severity is `PASS`, `SEV-4`, or explicitly accepted `SEV-3`; no `SEV-1/SEV-2` exists.
- [ ] P1/P2/deferred work did not enter the P0 implementation or acceptance claim.

---

## 15. Mechanical P0 ID Index

This index is intentionally explicit so plan review can mechanically prove that every governing P0 requirement has an owning task and final gate.

- Task 1 / TRUST-02: `OWN-P0-01`, `OWN-P0-02`, `OWN-P0-03`, `OWN-P0-04`, `OWN-P0-05`, `OWN-P0-06`, `OWN-P0-07`, `OWN-P0-08`, `OWN-P0-09`.
- Task 2 / TRUST-03: `ROUTE-P0-01`, `ROUTE-P0-02`, `ROUTE-P0-03`, `ROUTE-P0-04`, `ROUTE-P0-05`, `ROUTE-P0-06`, `ROUTE-P0-07`, `ROUTE-P0-08`, `ROUTE-P0-09`, `ROUTE-P0-10`.
- Task 3 / TRUST-04: `CITE-P0-01`, `CITE-P0-02`, `CITE-P0-03`, `CITE-P0-04`, `CITE-P0-05`, `CITE-P0-06`, `CITE-P0-07`, `CITE-P0-08`, `CITE-P0-09`, `CITE-P0-10`, `CITE-P0-11`.
- Tasks 4-5 / TRUST-05: `EXEC-P0-01`, `EXEC-P0-02`, `EXEC-P0-03`, `EXEC-P0-04`, `EXEC-P0-05`, `EXEC-P0-06`, `EXEC-P0-07`, `EXEC-P0-08`.
- Tasks 0 and 6 / TRUST-01 and TRUST-06: `TRACE-P0-01`, `TRACE-P0-02`, `TRACE-P0-03`, `TRACE-P0-04`, `TRACE-P0-05`, `TRACE-P0-06`, `TRACE-P0-07`, `TRACE-P0-08`.
- Tasks 5 and 7 / TRUST-07: `MEMQ-P0-01`, `MEMQ-P0-02`, `MEMQ-P0-03`, `MEMQ-P0-04`, `MEMQ-P0-05`, `MEMQ-P0-06`, `MEMQ-P0-07`, `MEMQ-P0-08`.
- Tasks 0-7 / TRUST-01..08: `SAFE-TRUST-P0-01`, `SAFE-TRUST-P0-02`, `SAFE-TRUST-P0-03`, `SAFE-TRUST-P0-04`, `SAFE-TRUST-P0-05`.
- Task 7 / TRUST-08: `EVAL-TRUST-P0-01`, `EVAL-TRUST-P0-02`, `EVAL-TRUST-P0-03`, `EVAL-TRUST-P0-04`, `EVAL-TRUST-P0-05`, `EVAL-TRUST-P0-06`, `EVAL-TRUST-P0-07`, `EVAL-TRUST-P0-08`, `EVAL-TRUST-P0-09`.
- Task 8 / TRUST-09: `GATE-TRUST-P0-01`, `GATE-TRUST-P0-02`, `GATE-TRUST-P0-03`, `GATE-TRUST-P0-04`, `GATE-TRUST-P0-05`, `GATE-TRUST-P0-06`, `GATE-TRUST-P0-07`, `GATE-TRUST-P0-08`, `GATE-TRUST-P0-09`, `GATE-TRUST-P0-10`, `GATE-TRUST-P0-11`, `GATE-TRUST-P0-12`.
