# 线程 E：剧情 Segment 双粒度检索与预算 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the single supervised Thread E Codex CLI session. Do not use `superpowers:subagent-driven-development`; E must not create subagents, additional CLI workers, or third-layer delegation. Every task ends at a D review checkpoint.

**Goal:** 从线程 C 发布的规范 Story Atom 和冻结 Data:Story 来源构建可重建的剧情结构 sidecar 与 Story Segment；保留 Atom BM25、改用 Segment Dense；在 Segment 层完成受控授权、融合、Owner/上下文预算和 Atom 精确引用，并交付不含真实 embedding 或生产写入的离线候选与评测 handoff。

**Architecture:** E0 首先解析并冻结来源 step/choice/branch/entity 结构，生成与 Atom 一一闭合的 sidecar；E1 基于 sidecar 生成确定性 Segment、`SegmentContextUnit` 和 Atom spans；E2 构建同时容纳非 Story Child 与 Story Segment 的 typed Dense 离线 JSONL、schema 和假向量适配器；E3 用一次性 `RequestPlan v2` 事务和统一 `StoryAuthorizationContext` 建立受控 Story 分支，在 Segment 层完成融合与分层预算；E4 将 Context Unit、Atom 引用、AnswerScope、continuation、anchor、REST/SSE 和唯一 retrieval outcome 事实源接入现有运行时；E5 冻结离线报告、容量和 D handoff。E 不调用真实 embedding，也不写 Milvus。

**Tech Stack:** Conda `1999wiki` 中的 Python 3.11.15（`D:\Anaconda32024\envs\1999wiki\python.exe`，`sys.prefix=D:\Anaconda32024\envs\1999wiki`）、dataclasses、Pydantic v2、FastAPI、SSE、React/TypeScript、BM25、Milvus typed-row contracts、pytest 9.1.1、JSON/JSONL、SHA-256、现有 Huiji corpus builder 与 RAG execution pipeline。

## Global Constraints

- 批准的设计源头：`docs/superpowers/specs/2026-07-30-rag-story-segment-retrieval-design.md`。
- 批准基线提交：`300e4066630c6564d56157442765a4675b783590`。
- 批准 Spec SHA-256：`61bf46e1ec6f44b330913d1b1effdfd1828edf72b13ccd7ea8f60c61fa7f405d`。
- 配套 D Plan：`docs/superpowers/plans/2026-07-30-rag-story-segment-d-integration.md`。
- E 从 D0 完成后的固定 `main` 创建，分支为 `codex/rag-e-story-segment`，工作树为 `D:\1999Wiki.worktrees\rag-e-story-segment`。
- E0 → E1 → E2 → E3 → E4 → E5 严格串行；每个 Task 完成后必须停在 `completed_pending_review`，由 D 独立验收、批准提交并放行下一 Task。
- E 使用 `gpt-5.6-sol`、标准速度、`workspace-write`、`fast_mode=false`、`multi_agent=false`。
- E 禁止子代理、第二个 CLI worker、读取 C worktree、复制其他 worktree 代码或使用对话摘要作为契约。
- 所有 Python/pytest 命令必须使用 `D:\Anaconda32024\envs\1999wiki\python.exe`；禁止裸 `python`、`py`、`pytest`。
- 每次启动或恢复 E，先验证 `sys.version_info == (3, 11, 15)`、`sys.prefix == D:\Anaconda32024\envs\1999wiki`、HEAD 和 D0 dependency receipt。
- E 不调用 embedding API，不创建/写入/删除 Milvus collection，不修改 active pointer，不激活候选，不写 MinIO/MySQL，不下载媒体。
- E 可以实现和测试真实 shadow build 所需的 typed schema、序列化、反序列化和 CLI，但测试必须使用 fake embeddings/fake Milvus；真实调用由 D 合并后执行。
- Reranker 必须保持关闭；E 的测试用 spy 断言调用次数为 0。
- P0 不实现 Segment BM25、BGE sparse、因果图、全章枚举摘要、额外完整性/冲突模型、自动 hybrid 或质量硬降权。
- Story Atom 的 `child_id`、`parent_id`、正文、source refs 和规范顺序不可修改；Segment 是派生检索视图。
- Story Atom 保留 BM25，Story Atom 不进入 typed Dense JSONL；非 Story Child 保留 Dense，Story Segment 进入 Dense。
- Segment 是候选、排序、上下文和字符预算单位；Atom 是 BM25 signal、正文组成和 citation source。
- 同一请求中 Segment 正文最多封装一次；命中 Atom 不得作为第二份独立正文发送给模型。
- 现有 `entity_strict`、`topic_strict` 和 primary Owner Gate 不得放宽；Story 通过显式授权分支进入。
- Planner 只提议；Policy 的检测、assignment receipt 和 `StoryAuthorizationContext/v1` 是授权事实源。
- 质量标记在 P0 只用于诊断/反事实，纯数字、短文本、标点或异常名称形式不得被过滤或降权。
- 所有实现采用 TDD：先最小 RED，再最小 GREEN，再阶段回归，再真实快照 create-new 证据。
- 每次真实快照诊断先用 `[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')` 生成 `$RunId`，只写 ignored `eval/story_segment/runs/$RunId/`，不得覆盖旧运行目录。
- 每次提交前运行 `git diff --check`、阶段测试、`git status --short`，只暂存任务 allowlist。
- 不通过 `git reset --hard`、`git checkout --`、stash、递归删除或覆盖恢复用户/其他线程文件。

---

## 1. 文件结构与单一职责

### 1.1 新建生产文件

| 文件 | 单一职责 |
|---|---|
| `src/huiji_rag/build/story_structure.py` | Data:Story taxonomy、结构解析、精确实体注册表、Atom sidecar 和闭包验证 |
| `src/huiji_rag/build/story_segments.py` | Segment config、边界、图关系、稳定 ID、oversize 规则和 deterministic artifact |
| `src/huiji_rag/build/dense_retrieval_units.py` | `rag_dense_retrieval_unit/v1` schema、Child/Segment typed rows 和 artifact identity |
| `src/rag/story_context.py` | `SegmentContextUnit`、Atom spans、请求级引用渲染和确定性渲染成本 |
| `src/rag/story_authorization.py` | Request-level Story detector、scope assignment、统一授权上下文、continuation 和 anchor validation |
| `src/rag/story_retrieval.py` | Atom-to-Segment mapping、typed Dense dispatch、融合、Owner/Segment/字符/citation 预算 |
| `src/rag/story_answer_scope.py` | `StoryAnswerScope/v2` nullable applicability、三态归一化和生成姿态 |
| `src/rag_eval/story_segment_runner.py` | E5 离线指标、质量反事实、容量、gate 和 handoff |
| `scripts/build_huiji_typed_index.py` | D 后置执行的 create-new typed shadow builder；E 只用 fake client 测试 |
| `scripts/evaluate_story_segment_rag.py` | D 后置真实评测和 E5 fake/offline 入口 |

### 1.2 新建测试文件

```text
tests/test_story_structure.py
tests/test_story_segments.py
tests/test_story_context_units.py
tests/test_dense_retrieval_units.py
tests/test_story_authorization.py
tests/test_story_request_plan_v2.py
tests/test_story_retrieval_fusion.py
tests/test_story_retrieval_budget.py
tests/test_story_answer_scope.py
tests/test_story_segment_runtime.py
tests/test_story_segment_public_contracts.py
tests/test_story_segment_eval.py
tests/test_huiji_typed_shadow_builder.py
```

### 1.3 修改生产文件

| 文件 | 修改职责 |
|---|---|
| `src/huiji_rag/build/contracts.py` | 发布 structure/segment/typed artifact schema 和 builder input/output identities |
| `src/huiji_rag/build/orchestrator.py` | 离线 stage 顺序、manifest/provenance、blocked/readiness 闭包 |
| `src/huiji_rag/build/artifact_writer.py` | create-new artifact 写入、行数/哈希/schema/fingerprint |
| `src/rag/request_plan.py` | v2 provisional/final plan、SourceQuerySpan 和一次性 Finalizer 接线 |
| `src/rag/query_plan.py` | 仅增加 Planner Story proposal 和 branch kind；不授予权限 |
| `src/rag/route_policy.py` | 从 final envelope 构造授权上下文并保持原 Owner Gate |
| `src/rag/retriever.py` | 受控 Story branches、typed Dense dispatch 和 embedding query 复用 |
| `src/rag/retrieval_budget.py` | Segment/Owner/Topic/Page/context/citation 五类预算 |
| `src/rag/contracts.py` | BranchResult/SubtaskInfo/packet 的 nullable Story fields 和 typed Context Unit |
| `src/rag/citations.py` | Segment 一次正文、Atom sources、global citation IDs 和 span validation |
| `src/rag/execution.py` | final envelope→authorize→retrieve→freeze packet→scope→generate→commit |
| `src/rag/chain.py` | 复用统一 execution service，不创建第二条 Story pipeline |
| `src/rag/conversation.py` | ConversationTurn v2、StoryAnchorEvent、TTL、set/clear/遮蔽 |
| `src/rag/prompts.py` | 一个 grounded generator 的 AnswerScope 姿态与短范围提示 |
| `src/rag/serializers.py` | 从 RouteDecision 投影 outcome；Story scopes、Atom/Segment source、actions |
| `src/rag/vectorstore.py` | typed collection schema、row adapter、Document 反序列化和 query vector 复用 |
| `backend/schemas.py` | strict v2 action union、Story scopes、SourceItem.segment_id 和 route fields |
| `backend/sse.py` | sources/done 一致 metadata 和 turn 原子提交 |
| `backend/main.py` | `/ask` 与 `/ask/stream` 复用同一 final envelope/execution |
| `frontend/react-app/src/types/index.ts` | v2 action、Story scope、Atom source/segment fields |
| `frontend/react-app/src/api/sse.ts` | strict continuation payload 无损透传和 route/scope 解析 |
| `frontend/react-app/src/api/sse.test.ts` | REST/SSE/action round-trip |
| `frontend/react-app/src/store/chatStore.ts` | 保存/发送 v2 action，不解释授权 |
| `frontend/react-app/src/store/chatStore.test.ts` | action 字段无损、未知/缺失失败 |

### 1.4 修改现有测试

```text
tests/test_huiji_corpus_artifacts.py
tests/test_huiji_corpus_builder.py
tests/test_huiji_corpus_builder_contracts.py
tests/test_huiji_corpus_projection.py
tests/test_sparse_bm25.py
tests/test_chinese_bm25_analyzer.py
tests/test_vectorstore.py
tests/test_huiji_shadow_builder.py
tests/test_request_plan.py
tests/test_query_plan.py
tests/test_route_policy.py
tests/test_retriever.py
tests/test_retrieval_budget.py
tests/test_rag_contracts.py
tests/test_citations.py
tests/test_rag_global_citations.py
tests/test_rag_execution.py
tests/test_rag_composite_execution.py
tests/test_conversation_memory.py
tests/test_conversation_api.py
tests/test_sse.py
tests/test_rag_eval_deterministic.py
tests/test_rag_eval_scoring.py
tests/test_rag_eval_reporting.py
tests/test_rag_eval_runner.py
```

---

## 2. 冻结公共接口

### 2.1 Story structure

```python
StructureStatus = Literal[
    "explicit_graph",
    "source_order",
    "blocked_invalid_graph",
]
LengthStatus = Literal[
    "within_hard_max",
    "oversize_atom",
    "blocked_dense_limit",
]

@dataclass(frozen=True)
class StoryAtomStructure:
    schema_version: Literal["rag.story-atom-structure/v1"]
    atom_id: str
    story_entity_id: str
    story_parent_id: str
    source_title: str
    source_content_sha256: str
    source_json_path: str
    source_order: int
    source_step_id: str
    incoming_source_step_ids: tuple[str, ...]
    next_source_step_ids: tuple[str, ...]
    choice_target_step_ids: tuple[str, ...]
    relation_kind: str
    branch_id: str
    scene_id: str
    background_id: str
    speaker_display_name: str
    speaker_source_id: str
    mentioned_entity_ids: tuple[str, ...]
    relation_source_refs: tuple[Mapping[str, object], ...]
    structure_status: StructureStatus
    diagnostic_codes: tuple[str, ...]
    content_sha256: str
    atom_char_count: int
    length_status: LengthStatus
    entity_link_registry_identity: str
    structure_identity: str
```

```python
def build_story_structure_taxonomy(
    story_atoms: Sequence[Mapping[str, object]],
    data_story_rows: Sequence[Mapping[str, object]],
    *,
    source_inventory: Mapping[str, object],
    parser_config: Mapping[str, object],
) -> Mapping[str, object]: ...

def build_story_entity_link_registry(
    parents: Sequence[Mapping[str, object]],
    verified_relationships: Sequence[Mapping[str, object]],
    taxonomy: Mapping[str, object],
) -> Mapping[str, object]: ...

def build_story_atom_structure(
    story_atoms: Sequence[Mapping[str, object]],
    data_story_rows: Sequence[Mapping[str, object]],
    *,
    taxonomy: Mapping[str, object],
    entity_registry: Mapping[str, object],
) -> tuple[StoryAtomStructure, ...]: ...
```

### 2.2 Segment 与 Context Unit

```python
@dataclass(frozen=True)
class StorySegmentConfig:
    target_min_chars: int = 200
    target_max_chars: int = 600
    hard_max_chars: int = 800
    target_min_atoms: int = 8
    target_max_atoms: int = 20
    schema_version: str = "rag.story-segment-config/v1"

@dataclass(frozen=True)
class StorySegment:
    segment_id: str
    schema_version: Literal["rag.story-segment/v1"]
    story_entity_id: str
    story_entity_name: str
    story_parent_id: str
    source_title: str
    source_refs: tuple[Mapping[str, object], ...]
    source_content_sha256: str
    ordered_atom_ids: tuple[str, ...]
    first_atom_source_token: str
    last_atom_source_token: str
    sequence_index: int
    prev_segment_ids: tuple[str, ...]
    next_segment_ids: tuple[str, ...]
    relation_kind: str
    branch_ids: tuple[str, ...]
    merge_identity: str
    heading_path: tuple[str, ...]
    context_text: str
    search_text: str
    char_count: int
    atom_count: int
    mentioned_entity_ids: tuple[str, ...]
    mentioned_entity_names: tuple[str, ...]
    quality_flags: tuple[str, ...]
    atom_structure_identity: str
    segmenter_identity: str
    content_sha256: str
```

```python
@dataclass(frozen=True)
class AtomSpan:
    atom_id: str
    segment_id: str
    char_start: int
    char_end: int
    atom_content_sha256: str
    source_refs: tuple[Mapping[str, object], ...]
    citation_id: str

@dataclass(frozen=True)
class SegmentContextUnit:
    context_unit_id: str
    segment_id: str
    story_entity_id: str
    story_parent_id: str
    base_context_text: str
    atom_spans: tuple[AtomSpan, ...]
    segment_char_count: int
    atom_count: int
    content_sha256: str
```

### 2.3 Typed Dense unit

```python
RetrievalUnitType = Literal["child", "story_segment"]

@dataclass(frozen=True)
class DenseRetrievalUnit:
    schema_version: Literal["rag_dense_retrieval_unit/v1"]
    retrieval_unit_id: str
    retrieval_unit_type: RetrievalUnitType
    text: str
    child_id: str | None
    segment_id: str | None
    parent_id: str
    entity_id: str
    entity_name: str
    entity_type: str
    category: str
    section_kind: str
    title: str
    depth_level: int
    media_policy: str
    media_ids: tuple[str, ...]
    owner_entity_id: str
    owner_page_id: str
    ancestor_ids: tuple[str, ...]
    quality_flags: tuple[str, ...]
    route_tags: tuple[str, ...]
    source_ref: tuple[Mapping[str, object], ...]
    chunk_index: int | None
    segment_sequence: int | None
    content_hash: str
    artifact_identity: str
```

Identity：

```text
child:<child_id>
story_segment:<segment_id>
```

Milvus primary key 为 `retrieval_unit_id VARCHAR(256)`；`text VARCHAR(16384)`；vector 为 `FLOAT_VECTOR(1024)`；`child_id/segment_id` 保持独立 nullable 字段。

### 2.4 RequestPlan v2 与统一授权

```python
@dataclass(frozen=True)
class SourceQuerySpan:
    query_char_start: int
    query_char_end: int
    source_text_sha256: str
    schema_version: str = "rag.source-query-span/v1"

@dataclass(frozen=True)
class PlannedSubtaskV2:
    subtask_id: str
    order: int
    task_type: TaskType
    query: str
    query_plan: QueryPlan | None
    depends_on: tuple[str, ...]
    source_query_spans: tuple[SourceQuerySpan, ...]
    answer_scope_hint: Literal[
        "local_fact",
        "bounded_multi_evidence",
        "exhaustive_narrative",
    ]
    planning_outcome: Literal["ready", "boundary_story_scope_invalid"]

@dataclass(frozen=True)
class RequestPlanV2:
    original_query: str
    request_query_sha256: str
    subtasks: tuple[PlannedSubtaskV2, ...]
    aggregation_mode: Literal["ordered_sections"]
    schema_version: Literal["rag.request_plan/v2"]
```

```python
AuthorizationOrigin = Literal[
    "direct_query",
    "verified_continuation",
    "validated_conversation_anchor",
]
AuthorizationStatus = Literal[
    "proposed",
    "authorized",
    "denied",
    "needs_continuation",
]
AuthorizationCoverage = Literal[
    "complete",
    "page_partial",
    "anchor_follow_up",
    "open_story_domain",
]

@dataclass(frozen=True)
class StoryAuthorizationContext:
    schema_version: Literal["rag.story-authorization-context/v1"]
    subtask_id: str
    authorization_origin: AuthorizationOrigin
    authorization_status: AuthorizationStatus
    authorization_reason: str
    authorization_coverage_scope: AuthorizationCoverage | None
    request_query_sha256: str
    source_query_spans_sha256: str
    request_detection_receipt_sha256: str
    story_scope_assignment_receipt_sha256: str
    subtask_detected_story_entity_refs: tuple[Mapping[str, str], ...]
    planner_story_entity_refs: tuple[Mapping[str, str], ...]
    required_story_entity_refs: tuple[Mapping[str, str], ...]
    authorized_story_owner_ids: tuple[str, ...]
    source_receipt_type: str
    source_receipt_sha256: str
    registry_identity: str
    policy_identity: str
```

Invariant：

```text
status=authorized -> coverage 必须非空且为四个有效值之一
status=proposed|denied|needs_continuation -> coverage 必须为 null
```

```python
BranchKind = Literal[
    "primary_owner",
    "story_required",
    "story_mentions",
    "story_examples",
]

@dataclass(frozen=True)
class KnowledgeRetrievalBranch:
    branch_id: str
    branch_kind: BranchKind
    query: str
    primary_entity_ref: EntityRef | None
    story_authorization_context: StoryAuthorizationContext | None
    continuation_actions: tuple[Mapping[str, object], ...]
    allowed_retrieval_unit_types: tuple[RetrievalUnitType, ...]
    story_filter: Mapping[str, object]
    owner_policy: str
    candidate_budget: Mapping[str, int]
    context_budget: Mapping[str, int]
```

Story authorization status/reason 只存在于 `story_authorization_context`，branch 顶层不得保存镜像。一个知识子任务最多一个主分支（`primary_owner` 或 `story_required`）和一个获批补充分支（`story_mentions` 或 `story_examples`）。

```python
@dataclass(frozen=True)
class StoryBranchConfig:
    required_story_owner_limit: int = 3
    planner_story_ref_limit: int = 32
    story_owner_page_size: int = 3
    mention_detector_name: str = "exact_story_mention"
    mention_detector_version: int = 2
    request_plan_schema: str = "rag.request_plan/v2"
    request_plan_finalizer_schema: str = "RequestPlanFinalizer/v1"
    assignment_receipt_schema: str = "StoryScopeAssignmentReceipt/v1"
    authorization_envelope_schema: str = "RequestAuthorizationEnvelope/v2"
    authorization_context_schema: str = "StoryAuthorizationContext/v1"
    continuation_action_schema: str = "StoryContinuationActionPayload/v1"
    continuation_action_max_canonical_json_bytes: int = 65536
    story_anchor_schema: str = "StoryConversationAnchor/v1"
    story_anchor_event_schema: str = "StoryAnchorEvent/v1"
    conversation_turn_schema: str = "ConversationTurn/v2"
    story_anchor_ttl_seconds: int = 1800
    story_answer_scope_schema: str = "StoryAnswerScope/v2"
    schema_version: str = "rag.story-branch-config/v2"
```

```python
@dataclass(frozen=True)
class StoryMentionDetectionReceipt:
    schema_version: Literal["StoryMentionDetectionReceipt/v2"]
    detector_identity: str
    query_sha256: str
    entity_registry_identity: str
    detection_complete: bool
    detected_story_count: int
    detected_story_entity_refs: tuple[Mapping[str, object], ...]
    detected_story_refs_sha256: str
    mention_occurrences: tuple[Mapping[str, object], ...]
    ambiguous_occurrences: tuple[Mapping[str, object], ...]
    overlap_conflicts: tuple[Mapping[str, object], ...]

@dataclass(frozen=True)
class RequestAuthorizationEnvelope:
    schema_version: Literal["RequestAuthorizationEnvelope/v2"]
    final_request_plan_v2: RequestPlanV2
    final_request_plan_v2_sha256: str
    request_plan_finalization_receipt: Mapping[str, object]
    story_mention_detection_receipt: StoryMentionDetectionReceipt
    story_scope_assignment_receipt: Mapping[str, object]
    story_authorization_contexts: tuple[StoryAuthorizationContext, ...]
```

### 2.5 Fusion、预算和答案范围

```python
@dataclass(frozen=True)
class StoryFusionConfig:
    atom_bm25_k: int = 80
    story_segment_dense_k: int = 30
    rrf_k: int = 60
    atom_weight: float = 1.2
    dense_weight: float = 1.0
    second_atom_factor: float = 0.25
    second_segment_factor: float = 0.25
    topic_page_candidate_reserve: int = 10
    max_seed_segments: int = 8
    schema_version: str = "rag.story-fusion-config/v1"
```

```text
dense_signal =
  0                                   if dense_rank absent
  dense_weight / (rrf_k + dense_rank) otherwise

best_atom_signal =
  0                                      if best_atom_rank absent
  atom_weight / (rrf_k + best_atom_rank) otherwise

second_atom_signal =
  0 if second_atom_rank absent
  second_atom_factor * atom_weight / (rrf_k + second_atom_rank) otherwise

segment_score = max(dense_signal, best_atom_signal) + second_atom_signal
story_score = best_segment_score + second_segment_factor * second_segment_score
```

Runtime budget config：

```text
max_segment_slots = 6
max_story_citation_atoms = 72
max_total_citation_sources = 80
global_context_chars = 9000
```

```python
@dataclass(frozen=True)
class StoryAnswerScope:
    schema_version: Literal["rag.story-answer-scope/v2"]
    subtask_id: str
    claim_scope: Literal[
        "local_fact",
        "bounded_multi_evidence",
        "exhaustive_narrative",
    ]
    evidence_state: Literal["sufficient", "partial", "empty"]
    answer_posture: Literal["best_effort_grounded", "strict_grounded"]
    authorization_coverage_scope: AuthorizationCoverage
    narrative_coverage: Literal["local", "bounded", "non_exhaustive"]
    shortfall_codes: tuple[str, ...]
```

只有 ready + authorized + completed retrieval + frozen packet 时该对象非空。

---

## 3. E0：Story structure sidecar

### Task E0.0：环境、依赖和禁止操作预检

**Files:** no tracked changes

- [ ] 读取并验证 Spec、D Plan、E Plan 和 `.codex-supervisor/workers/E/dependency-receipt.v1.json`。
- [ ] 验证工作树 HEAD 等于 D0 receipt 的 `main_commit`。
- [ ] 验证所有设计依赖已被 Git 跟踪，且 commit/SHA-256 与 receipt 一致。
- [ ] 验证解释器：

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -c `
  "import sys; assert sys.version_info[:3] == (3,11,15); assert sys.prefix == r'D:\Anaconda32024\envs\1999wiki'"
```

- [ ] 验证 reranker disabled、Milvus/embedding 环境只读，不运行网络探针。
- [ ] 记录 `git status --short`；E worktree 必须无非预期 tracked 改动。
- [ ] 向 D 报告预检结果；未通过即停止。

### Task E0.1：实现统一 taxonomy parser 与精确实体注册表

**Spec coverage:** `SCOPE-P0-01`、`SCOPE-P0-04` 至 `SCOPE-P0-06`、`ATOMSTRUCT-P0-02` 至 `ATOMSTRUCT-P0-08`、`ATOMSTRUCT-P0-11` 至 `ATOMSTRUCT-P0-16`、`ENTITYLINK-P0-01` 至 `ENTITYLINK-P0-03`、`QUALITY-P0-01` 至 `QUALITY-P0-07`

**Files:**

- Create: `src/huiji_rag/build/story_structure.py`
- Create: `tests/test_story_structure.py`
- Modify only for shared schema types: `src/huiji_rag/build/contracts.py`

- [ ] **Step 1: 写 RED fixtures/tests**

Fixture 必须覆盖：

- 明确 step/choice/target；
- 多出口、汇合、terminal、SCC/cycle；
- source 完全无图字段；
- 悬空目标、跨 Story 目标、重复 step、冲突目标；
- display speaker 与稳定 speaker ID；
- 精确 alias、纯数字 `6/37`、短名称、内部 ID；
- 跨类型同名和歧义 alias；
- 24、600、800、801、1115、16384、16385 code points；
- 控制 Atom 与短对白；
- 同一输入重复构建。

Run RED:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_structure.py -q `
  --basetemp .pytest-story-e0-structure-red
```

Expected: import/contract tests fail。

- [ ] **Step 2: 实现单一 parser**

Taxonomy 与正式 sidecar 必须调用同一个版本化 parser。不得在 `eval/` 脚本中另写字段解释。

- [ ] **Step 3: 实现 registry**

只允许 Unicode 规范化、首尾空白和项目已冻结大小写规则。歧义键不发布实体 ID；不得按频率、上下文、白名单或 Dense 选择。

- [ ] **Step 4: 实现 graph validation**

- explicit graph 的所有非 terminal target 必须同 Story 唯一解析；
- cycle 使用 SCC 和 visited；
- source 无图字段才允许 `source_order`；
- 显式字段损坏必须 `blocked_invalid_graph`，不降级线性。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_structure.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_huiji_corpus_builder_contracts.py -q `
  --basetemp .pytest-story-e0-structure-green
```

Expected: exit code 0。

- [ ] **Step 6: 停在 D review**

不提交 E0.2。D 接受后提交：

```text
feat(rag): parse story source structure
```

### Task E0.2：生成 Atom structure artifact、真实 taxonomy 和闭包

**Spec coverage:** `ATOMSTRUCT-P0-01`、`ATOMSTRUCT-P0-09`、`ATOMSTRUCT-P0-10`、`HIER-P0-01` 至 `HIER-P0-03`、`FAILURE-P0-01` 至 `FAILURE-P0-03`、`PROVENANCE-P0-01` 至 `PROVENANCE-P0-03`

**Files:**

- Modify: `src/huiji_rag/build/story_structure.py`
- Modify: `src/huiji_rag/build/contracts.py`
- Modify: `src/huiji_rag/build/orchestrator.py`
- Modify: `src/huiji_rag/build/artifact_writer.py`
- Modify: `tests/test_story_structure.py`
- Modify: `tests/test_huiji_corpus_artifacts.py`
- Modify: `tests/test_huiji_corpus_builder.py`
- Modify: `tests/test_huiji_corpus_builder_contracts.py`

- [ ] **Step 1: RED artifact tests**

断言正式候选包含：

```text
story_structure_taxonomy.v1.json
story_entity_link_registry.v1.json
story_atom_structure.v1.jsonl
story_atom_structure.v1.schema.json
```

Manifest 必须记录 schema、row count、Atom ID order hash、input/config/code/registry/structure identities 和 SHA-256。

- [ ] **Step 2: 接入 builder**

Stage 顺序：

```text
canonical Parent/Atom projection
→ taxonomy
→ entity registry
→ Atom structure sidecar
→ closure verification
→ artifact write
```

不修改规范 Atom。

- [ ] **Step 3: 小 fixture deterministic build**

在两个新临时 root 运行两次，比较所有业务 artifact 字节、ID、顺序和 hashes。

- [ ] **Step 4: 真实恢复快照只读诊断**

创建新 run root，重新计算真实 Atom 长度分布和 graph taxonomy；不得硬编码旧审计的 7/1115。

通过条件：

- 每个 Story Atom 恰好一条 structure；
- Atom identity/source/content 全匹配；
- explicit target 零悬空；
- blocked Story 有 bounded diagnostics；
- numeric/short entity 保留；
- canonical Atom pre/post SHA-256 相同；
- 网络/下载/embedding/Milvus/active writes 为 0。

- [ ] **Step 5: E0 回归**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_structure.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_builder.py `
  tests/test_huiji_corpus_builder_contracts.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_sparse_bm25.py `
  tests/test_chinese_bm25_analyzer.py -q `
  --basetemp .pytest-story-e0-regression
```

- [ ] **Step 6: 停在 D review**

不提交 E1。D 接受后提交：

```text
feat(rag): publish story atom structure sidecar
```

---

## 4. E1：Segment、Context Unit 与 Atom 引用

### Task E1.1：实现确定性 Segment 边界、图关系和身份

**Spec coverage:** `DECISION-P0-01` 至 `DECISION-P0-04`、`SEGMENT-P0-01` 至 `SEGMENT-P0-06`、`BOUNDARY-P0-01` 至 `BOUNDARY-P0-12`、`IDENTITY-P0-01` 至 `IDENTITY-P0-04`、`RELATION-P0-01` 至 `RELATION-P0-03`

**Files:**

- Create: `src/huiji_rag/build/story_segments.py`
- Create: `tests/test_story_segments.py`
- Modify: `src/huiji_rag/build/contracts.py`
- Modify: `src/huiji_rag/build/orchestrator.py`
- Modify: `src/huiji_rag/build/artifact_writer.py`
- Modify: `tests/test_huiji_corpus_artifacts.py`
- Modify: `tests/test_huiji_corpus_builder.py`

- [ ] **Step 1: RED boundary matrix**

覆盖：

- 200/600/800 和 8/20 软目标；
- speaker/scene/background/heading 变化；
- split/choice/merge/terminal/cycle；
- source-order Story；
- 801/1115 oversize 单 Atom Segment；
- Dense limit blocker；
- 同 Story 全 Atom 恰好一次；
- 禁止跨 Story/互斥 branch；
- prev/next 多前驱/多后继；
- 同输入字节稳定。

- [ ] **Step 2: 实现 greedy-with-hard-boundaries**

硬边界优先于软目标；不得截断 Atom、不得把 oversize Atom 与其他 Atom 合并、不得为满足目标跨选择边。

- [ ] **Step 3: 稳定身份**

`segment_id` 由版本化 namespace、Story ID、source hash、ordered Atom IDs、边界/branch identity 和 segmenter config canonical bytes 哈希派生；不使用输出序号作为事实身份。

- [ ] **Step 4: 图闭包**

Segment prev/next 从 Atom graph 投影；source-order 只标记邻接，不声明因果；所有 ID sorted/dedup。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segments.py `
  tests/test_story_structure.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_builder.py -q `
  --basetemp .pytest-story-e1-segments
```

- [ ] **Step 6: 停在 D review**

不提交 E1.2。D 接受后提交：

```text
feat(rag): build deterministic story segments
```

### Task E1.2：实现 SegmentContextUnit、Atom spans 和双预算

**Spec coverage:** `CITATIONUNIT-P0-01` 至 `CITATIONUNIT-P0-09`、`CONTEXTBUDGET-P0-05` 至 `CONTEXTBUDGET-P0-08`、`FAILURE-P0-07`

**Files:**

- Create: `src/rag/story_context.py`
- Create: `tests/test_story_context_units.py`
- Modify: `src/rag/contracts.py`
- Modify: `src/rag/citations.py`
- Modify: `tests/test_citations.py`
- Modify: `tests/test_rag_global_citations.py`

- [ ] **Step 1: RED span tests**

必须证明：

- `base_context_text` 为 ordered Atom 文本单换行连接；
- `[start,end)` 使用 Unicode code points；
- spans 无重叠并覆盖所有非空 Atom；
- 每个非空 Atom 一个 source/citation；
- citation IDs 不参与 context unit identity；
- Segment 正文只出现一次；
- 预算不足删除整个 Segment；
- 非 Story source 先占 citation source；
- 最终渲染成本包含标题/分隔符/`[Sxx]`。

- [ ] **Step 2: 实现不可变 Context Unit**

Source Map 继续以 Atom child/source refs 为事实身份，附加 `segment_id` 只用于分组。

- [ ] **Step 3: 实现 deterministic render-cost**

选择阶段先计算最终 code-point 成本；禁止封装后截断。

- [ ] **Step 4: artifact integration**

发布 `story_segments.v1.jsonl`、schema、config、atom-to-segment mapping、Context Unit fixture identity 和 manifest hashes。

- [ ] **Step 5: E1 全阶段回归与真实重建**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segments.py `
  tests/test_story_context_units.py `
  tests/test_citations.py `
  tests/test_rag_global_citations.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_builder.py -q `
  --basetemp .pytest-story-e1-regression
```

真实快照必须证明 Atom 完整覆盖、oversize 闭包、两次 Segment bytes 一致和 canonical Atom 零变化。

- [ ] **Step 6: 停在 D review**

D 接受后提交：

```text
feat(rag): map story segments to atom citations
```

---

## 5. E2：Typed Dense 离线输入与假向量适配器

### Task E2.1：生成 typed Dense artifact

**Spec coverage:** `INDEX-P0-01` 至 `INDEX-P0-06`、`DENSEUNIT-P0-01` 至 `DENSEUNIT-P0-04`、`DENSEUNIT-P0-08` 至 `DENSEUNIT-P0-11`、`FAILURE-P0-01`、`FAILURE-P0-02`、`FAILURE-P0-08`

**Files:**

- Create: `src/huiji_rag/build/dense_retrieval_units.py`
- Create: `tests/test_dense_retrieval_units.py`
- Modify: `src/huiji_rag/build/contracts.py`
- Modify: `src/huiji_rag/build/orchestrator.py`
- Modify: `src/huiji_rag/build/artifact_writer.py`
- Modify: `tests/test_huiji_corpus_artifacts.py`
- Modify: `tests/test_huiji_corpus_builder.py`

- [ ] **Step 1: RED typed-row tests**

断言：

- 非 Story Child → `child:<child_id>`，child_id 非空、segment_id null；
- Story Segment → `story_segment:<segment_id>`，segment_id 非空、child_id null；
- Story Atom → 0 Dense rows；
- retrieval unit ID 全局唯一；
- text/search_text 不超过 16384；
- unknown/mixed-null/type mismatch fail-closed；
- row order deterministic；
- schema/config/artifact identity 完整。

- [ ] **Step 2: 实现 builder**

不读取 BM25 排名或质量 flag 决定是否删除 Story Atom；Story Atom 的排除只由 `entity_type=story + canonical Atom section contract` 决定。

- [ ] **Step 3: 发布 artifact**

```text
dense_retrieval_units.v1.jsonl
dense_retrieval_units.v1.schema.json
dense_retrieval_units.v1.manifest.json
```

Manifest 包含 Child/Segment counts、Story Atom excluded count、ordered ID hash、text hash、schema/config/code/source identities。

- [ ] **Step 4: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_dense_retrieval_units.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_builder.py `
  tests/test_sparse_bm25.py -q `
  --basetemp .pytest-story-e2-artifact
```

- [ ] **Step 5: 停在 D review**

不提交 E2.2。D 接受后提交：

```text
feat(rag): publish typed dense retrieval units
```

### Task E2.2：实现 typed Milvus schema、适配器和 fake shadow CLI

**Spec coverage:** `DENSEUNIT-P0-05` 至 `DENSEUNIT-P0-11`、`PIPE-P0-05`、`PIPE-P0-07`、`PERF-P0-03`、`PERF-P0-06`

**Files:**

- Modify: `src/rag/vectorstore.py`
- Create: `scripts/build_huiji_typed_index.py`
- Create: `tests/test_huiji_typed_shadow_builder.py`
- Modify: `tests/test_vectorstore.py`
- Modify: `tests/test_huiji_shadow_builder.py`

- [ ] **Step 1: RED schema/adapter tests**

Fake Milvus 必须断言：

- PK 为 `retrieval_unit_id`；
- type/child/segment nullable invariant；
- schema fields/limits/dimension；
- typed row round-trip；
- `milvus_entity_to_document()` 保留 unit type 和 ID；
- unknown type fails；
- active legacy collection loader 仍能读 active v1；
- fake builder 拒绝 active/forbidden/existing target；
- embedding failure 保留 shadow 和 failure receipt；
- fake embedding 不重复处理同一 ordered row；
- 无真实网络或 Milvus。

- [ ] **Step 2: 实现 typed schema/adapter**

不要把 Segment 塞入现有 child-only helper；新增 typed helper，并保持旧 helper 行为不变直到独立激活。

- [ ] **Step 3: 实现 D 后置 CLI**

CLI 必须要求 handoff、typed artifact hash、schema hash、collection name、receipt root；默认拒绝缺少 active/forbidden inventory。

- [ ] **Step 4: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_dense_retrieval_units.py `
  tests/test_huiji_typed_shadow_builder.py `
  tests/test_vectorstore.py `
  tests/test_huiji_shadow_builder.py -q `
  --basetemp .pytest-story-e2-vectorstore
```

- [ ] **Step 5: E2 无外部写探针**

运行 CLI 的 `--dry-run`/fake client 测试，确认 embedding provider、Milvus constructor 和 network spy 调用均为 0。

- [ ] **Step 6: 停在 D review**

D 接受后提交：

```text
feat(rag): add typed dense shadow adapter
```

---

## 6. E3：RequestPlan v2、统一授权、融合与预算

### Task E3.1：实现 provisional→final 一次性 RequestPlan v2 事务

**Spec coverage:** `REQUESTPLAN2-P0-01` 至 `REQUESTPLAN2-P0-13`、`PIPE-P0-08`、`REVIEW-P0-07`、`REVIEW-P0-13` 至 `REVIEW-P0-15`

**Files:**

- Modify: `src/rag/request_plan.py`
- Create: `tests/test_story_request_plan_v2.py`
- Modify: `tests/test_request_plan.py`
- Modify only for proposal fields: `src/rag/query_plan.py`
- Modify: `tests/test_query_plan.py`

- [ ] **Step 1: RED transaction tests**

覆盖：

- SourceQuerySpan bounds/hash/order/no-overlap；
- Detector 每请求恰好一次；
- occurrence 恰归一个 KB subtask；
- 角色 KB + Story KB 复合请求；
- local/meta/smalltalk 保留；
- 一次 deterministic knowledge-scope merge；
- query 由原 span 精确文本机械连接；
- hint conflict → bounded；
- boundary 只影响相关 KB；
- boundary overlap → request planning failure；
- fallback 后第二次 Planner/Detector/Finalizer 为 0；
- provisional 永不进入 serializer/retriever/memory/action；
- v1/v2 不猜测兼容。

- [ ] **Step 2: 实现 v2 types/finalizer**

Detector receipt 与 assignment receipt 分离；final plan hash 只在 assignment closed 后生成。

- [ ] **Step 3: 保持 v1 active 行为**

影子 snapshot 显式选择 v2。不得在同一 snapshot 双写 v1/v2 或自动将 v1 query 当全 span。

- [ ] **Step 4: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_request_plan_v2.py `
  tests/test_request_plan.py `
  tests/test_query_plan.py -q `
  --basetemp .pytest-story-e3-request-plan
```

- [ ] **Step 5: 停在 D review**

不提交 E3.2。D 接受后提交：

```text
feat(rag): finalize request plan v2
```

### Task E3.2：实现 Story detector、direct authorization 与多 Story 状态机

**Spec coverage:** `STORYBRANCH-P0-01` 至 `STORYBRANCH-P0-30`、`STORYBRANCH-P0-41` 至 `STORYBRANCH-P0-45`、`AUTHCTX-P0-01` 至 `AUTHCTX-P0-06`、`ENTITYLINK-P0-01` 至 `ENTITYLINK-P0-03`

**Files:**

- Create: `src/rag/story_authorization.py`
- Create: `tests/test_story_authorization.py`
- Modify: `src/rag/route_policy.py`
- Modify: `tests/test_route_policy.py`
- Modify: `src/rag/query_plan.py`
- Modify: `tests/test_query_plan.py`

- [ ] **Step 1: RED detector boundary tests**

覆盖：

- canonical exact、safe alias、quoted/whole span、stable ID；
- 短中文、纯数字、ASCII/ID 边界；
- 长词内子串；
- 跨类型同名；
- 规范标题 + 助词；
- Planner omission/extra/reorder；
- span assignment mismatch；
- 非 Story KB 零误拒；
- detector deterministic identity；
- 本地步骤 P95 测量接口。

- [ ] **Step 2: 实现 request-level detector**

Detector 只扫描 original query 一次；不读取 Planner refs 或 conversation anchor；输出 occurrence IDs、ranges、registry identity、ambiguity 和 full count。

- [ ] **Step 3: 实现 direct authorization**

```text
0 explicit Story:
  non-Story branch -> no Story context
  proposed story_required -> denied unless anchor path later validates

1..3:
  exact planner/detected ordered-set match -> authorized/complete

4..32:
  needs_continuation, coverage=null, no retriever

33+:
  denied/narrow_story_scope, coverage=null, no retriever
```

Planner omission/extra/reorder/ambiguity fail-closed。Retriever 只能消费 `authorized_story_owner_ids`。

- [ ] **Step 4: 保持原 Owner Gate**

`primary_owner` 仍走 entity/topic strict；`story_mentions/story_examples` 使用独立已授权 allowlist，不把 Story row 混入 primary Owner Gate。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_authorization.py `
  tests/test_story_request_plan_v2.py `
  tests/test_route_policy.py `
  tests/test_query_plan.py -q `
  --basetemp .pytest-story-e3-authorization
```

- [ ] **Step 6: 停在 D review**

不提交 E3.3。D 接受后提交：

```text
feat(rag): authorize story retrieval scope
```

### Task E3.3：实现 self-contained continuation 与 Story anchor 生命周期

**Spec coverage:** `STORYBRANCH-P0-31` 至 `STORYBRANCH-P0-40`、`STORYBRANCH-P0-46` 至 `STORYBRANCH-P0-49`、`REVIEW-P0-05`、`REVIEW-P0-08`

**Files:**

- Modify: `src/rag/story_authorization.py`
- Modify: `tests/test_story_authorization.py`
- Modify: `src/rag/conversation.py`
- Modify: `tests/test_conversation_memory.py`
- Modify: `tests/test_conversation_api.py`
- Modify: `backend/schemas.py`
- Modify: `frontend/react-app/src/types/index.ts`
- Modify: `frontend/react-app/src/api/sse.ts`
- Modify: `frontend/react-app/src/api/sse.test.ts`
- Modify: `frontend/react-app/src/store/chatStore.ts`
- Modify: `frontend/react-app/src/store/chatStore.test.ts`

- [ ] **Step 1: RED continuation tests**

覆盖：

- 4/5/32 Story 每页最多 3；
- next page 可跨新 HTTP 请求进入 authorized/page_partial；
- Planner 0 calls；
- 完整原 query/final plan/detection/assignment/continuation receipts 可重验；
- canonical JSON <= 65536 bytes；
- unknown/missing/tampered/stale/oversize fail；
- action strict union `extra=forbid`；
- frontend round-trip byte-equivalent fields；
- 失败不退回 direct query，不消费部分 owners。

- [ ] **Step 2: RED anchor tests**

覆盖：

- single Story successful cited turn → set；
- A→B 替换；
- A→B/C、page partial、empty/denied/failed、引用失败 → clear；
- local/meta/smalltalk 不清除；
- UTC 1800 seconds TTL；
- snapshot/registry/policy mismatch；
- process restart memory loss；
- follow-up local resolver；
- no referential language denied；
- SSE uncommitted turn no partial anchor；
- most recent clear shadows old set。

- [ ] **Step 3: 实现 continuation**

Action payload 是不可信完整输入，不是授权 token；Policy 重算 hash、Detector 和当前 registry allowlist，不调用 Planner。

- [ ] **Step 4: 实现 turn-event anchor**

`ConversationTurn.story_anchor_event` 是唯一事实；`_Entry` 不双写。Answer、citation validation、turn 和 event 在 lease lock 内原子追加。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_authorization.py `
  tests/test_conversation_memory.py `
  tests/test_conversation_api.py -q `
  --basetemp .pytest-story-e3-continuation-anchor
```

再运行：

```powershell
& npm.cmd --prefix `
  'D:\1999Wiki.worktrees\rag-e-story-segment\frontend\react-app' `
  test -- `
  src/api/sse.test.ts `
  src/store/chatStore.test.ts
```

两类测试都必须 exit 0。

- [ ] **Step 6: 停在 D review**

不提交 E3.4。D 接受后提交：

```text
feat(rag): validate story continuation and anchors
```

### Task E3.4：实现 Atom/Segment 融合、Owner 配额和五类预算

**Spec coverage:** `PIPE-P0-01` 至 `PIPE-P0-08`、`FUSION-P0-01` 至 `FUSION-P0-09`、`CANDIDATE-P0-01` 至 `CANDIDATE-P0-04`、`OWNERBUDGET-P0-01` 至 `OWNERBUDGET-P0-05`、`CONTEXTBUDGET-P0-01` 至 `CONTEXTBUDGET-P0-08`、`DETAIL-P0-01` 至 `DETAIL-P0-02`、`MULTISTORY-P0-01` 至 `MULTISTORY-P0-05`、`RELATION-P0-01` 至 `RELATION-P0-03`

**Files:**

- Create: `src/rag/story_retrieval.py`
- Create: `tests/test_story_retrieval_fusion.py`
- Create: `tests/test_story_retrieval_budget.py`
- Modify: `src/rag/retriever.py`
- Modify: `src/rag/retrieval_budget.py`
- Modify: `tests/test_retriever.py`
- Modify: `tests/test_retrieval_budget.py`
- Modify: `tests/test_hybrid_retriever.py`

- [ ] **Step 1: RED exact numeric fusion tests**

使用完整 rank tables 断言每项浮点值和排序；覆盖缺 rank、rank=0、负值、NaN/Inf、重复 channel rank、unknown unit type、同文本跨 Story、不累加第三 Atom/Segment。

- [ ] **Step 2: 实现 channel-local candidates**

Atom BM25 Top-80 和 Segment Dense Top-30 先在各通道产生；Atom 命中先映射 Segment；映射前不得执行跨通道最终截断。Topic/Page reserve=10，seed segments<=8。

- [ ] **Step 3: 实现 typed Dense dispatch/query reuse**

一个知识子任务相同 query/model identity 只 embed 一次，并在 Child/Segment 搜索复用；最多两个不同 Dense query，trace 记录调用数。

- [ ] **Step 4: 实现 Owner allocation**

先给每个 required Owner 一个 seed，再轮询；2/3 Story 保证原问题顺序；4+ 不进入排行榜；开放式最多 3。

- [ ] **Step 5: 实现 context/citation budget**

同时满足 Owner、Segment、Story chars、global chars、Atom citations。世界观定义先保留 Topic/Page；预算不足整 Segment 删除并发 shortfall。

- [ ] **Step 6: 实现 detail diversity 与 graph expansion**

不同 Atom anchors 优先于最高分邻居；扩展只能沿 compatible explicit/source-order edges，不能把邻接当因果。

- [ ] **Step 7: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_retrieval_fusion.py `
  tests/test_story_retrieval_budget.py `
  tests/test_retriever.py `
  tests/test_retrieval_budget.py `
  tests/test_hybrid_retriever.py -q `
  --basetemp .pytest-story-e3-retrieval
```

- [ ] **Step 8: E3 阶段回归与 D review**

运行 RequestPlan、Policy、Retriever、Budget、Conversation、frontend action 全部测试；reranker/embedding spies 满足契约。D 接受后按审查边界形成独立提交：

```text
feat(rag): fuse and budget story segments
```

---

## 7. E4：Runtime、Atom 引用、AnswerScope 与公开契约

### Task E4.1：接入统一 execution、Segment Context 和分支失败隔离

**Spec coverage:** `PIPE-P0-01` 至 `PIPE-P0-09`、`CITATIONUNIT-P0-01` 至 `CITATIONUNIT-P0-09`、`MULTISTORY-P0-01` 至 `MULTISTORY-P0-05`、`FAILURE-P0-01` 至 `FAILURE-P0-10`

**Files:**

- Modify: `src/rag/contracts.py`
- Modify: `src/rag/citations.py`
- Modify: `src/rag/execution.py`
- Modify: `src/rag/chain.py`
- Modify: `src/rag/retriever.py`
- Create: `tests/test_story_segment_runtime.py`
- Modify: `tests/test_rag_contracts.py`
- Modify: `tests/test_citations.py`
- Modify: `tests/test_rag_global_citations.py`
- Modify: `tests/test_rag_execution.py`
- Modify: `tests/test_rag_composite_execution.py`

- [ ] **Step 1: RED full packet tests**

覆盖：

- final envelope before retriever；
- boundary/denied/continuation no retriever；
- Segment once + Atom sources；
- source ID global allocation；
- branch source whitelist；
- multi-Story order；
- one Story branch failure preserves others；
- no partial Segment；
- span/source mismatch rejects Context Unit；
- snapshot type/config/hash mismatch blocks candidate；
- BM25-only diagnostic not called full scheme；
- reranker zero。

- [ ] **Step 2: 接入统一 RAGExecutionService**

不创建第二个 Story chain。执行顺序固定：

```text
provisional plan
→ detector/finalizer/envelope
→ route authorization
→ all retrieval branches
→ fusion/budget
→ global Atom source map
→ frozen packet
→ nullable answer scope
→ grounded generation
→ citation validation
→ deterministic aggregation
→ atomic turn commit
```

- [ ] **Step 3: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_runtime.py `
  tests/test_rag_contracts.py `
  tests/test_citations.py `
  tests/test_rag_global_citations.py `
  tests/test_rag_execution.py `
  tests/test_rag_composite_execution.py -q `
  --basetemp .pytest-story-e4-runtime
```

- [ ] **Step 4: 停在 D review**

不提交 E4.2。D 接受后提交：

```text
feat(rag): execute story segment context units
```

### Task E4.2：实现 StoryAnswerScope/v2 和尽力 grounded 回答

**Spec coverage:** `SHORTFALL-P0-01` 至 `SHORTFALL-P0-05`、`ANSWER-P0-01` 至 `ANSWER-P0-10`、`SUMMARY-P0-01` 至 `SUMMARY-P0-03`、`REVIEW-P0-10` 至 `REVIEW-P0-12`、`REVIEW-P0-15` 至 `REVIEW-P0-16`

**Files:**

- Create: `src/rag/story_answer_scope.py`
- Create: `tests/test_story_answer_scope.py`
- Modify: `src/rag/contracts.py`
- Modify: `src/rag/prompts.py`
- Modify: `src/rag/execution.py`
- Modify: `tests/test_prompts.py`
- Modify: `tests/test_rag_execution.py`

- [ ] **Step 1: RED applicability/state matrix**

六类必测：

1. 非 Story KB；
2. Story denied；
3. Story needs-continuation；
4. boundary + successful KB；
5. authorized Story retrieval failed；
6. authorized Story with zero ContextUnit。

另测：

- nonempty/no material shortfall → sufficient；
- nonempty/material shortfall → partial + nonempty answer；
- local fact 单个短 Atom仍 sufficient；
- strict grounded 不拒绝事实；
- exhaustive → non_exhaustive；
- page_partial/sufficient/bounded 正交；
- same packet repeated bytes equal；
- no extra model/reranker calls。

- [ ] **Step 2: 实现 nullable scope**

Scope 不回流改变授权、候选或预算。Material shortfall 只接受固定八个 evidence codes，不接受授权 reason、debug count、short/quality heuristics。

- [ ] **Step 3: 修改一个 grounded prompt**

提示要求：

- 先回答可支持结论；
- 推断明确标记；
- 禁止完整/唯一/必然过度表述；
- shortfall 只在末尾一句；
- strict posture 禁止未直接支持推断但保留事实；
- 无第二次 LLM。

- [ ] **Step 4: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_answer_scope.py `
  tests/test_prompts.py `
  tests/test_rag_execution.py -q `
  --basetemp .pytest-story-e4-answer-scope
```

- [ ] **Step 5: 停在 D review**

不提交 E4.3。D 接受后提交：

```text
feat(rag): normalize grounded story answer scope
```

### Task E4.3：统一内部/REST/SSE outcome、actions、scopes 和 Atom sources

**Spec coverage:** `ANSWER-P0-11` 至 `ANSWER-P0-13`、`REQUESTPLAN2-P0-12`、`STORYBRANCH-P0-46` 至 `STORYBRANCH-P0-49`、`CITATIONUNIT-P0-07`、`REVIEW-P0-17`、`REVIEW-P0-18`

**Files:**

- Modify: `src/rag/contracts.py`
- Modify: `src/rag/serializers.py`
- Modify: `backend/schemas.py`
- Modify: `backend/sse.py`
- Modify: `backend/main.py`
- Modify: `frontend/react-app/src/types/index.ts`
- Modify: `frontend/react-app/src/api/sse.ts`
- Modify: `frontend/react-app/src/api/sse.test.ts`
- Modify: `frontend/react-app/src/store/chatStore.ts`
- Modify: `frontend/react-app/src/store/chatStore.test.ts`
- Create: `tests/test_story_segment_public_contracts.py`
- Modify: `tests/test_sse.py`
- Modify: `tests/test_conversation_api.py`

- [ ] **Step 1: RED unique-fact-source tests**

故意让 `diagnostics["route"].retrieval_outcome` 与 `RouteDecision` 冲突；断言内部唯一值、REST route、SSE sources route、SSE done route 全部来自：

```text
ResponsePacket.retrieval_packet.route_decision.retrieval_outcome
```

REST 与 SSE 的唯一公开位置固定为 `route.retrieval_outcome`；不得新增 JSON 顶层镜像，也不得从 `diagnostics["route"]` 独立重算。

- [ ] **Step 2: 修改 aggregate**

进入 `aggregate_retrieval_outcome()` 前过滤 `not_applicable`：

```text
filtered empty -> not_applicable
all sufficient -> sufficient
all empty -> empty
all failed -> failed
otherwise -> partial
```

`failed/not_applicable` 不转为 empty。

- [ ] **Step 3: strict public schemas**

公开：

- nullable `SubtaskInfo.story_answer_scope`；
- ordered `story_subtask_scopes[]`；
- Atom `SourceItem.segment_id`；
- v2 continuation/narrow action union；
- shortfall codes；
- route outcome。

未知 action fields 失败；不使用 `extra=ignore`。

- [ ] **Step 4: SSE/REST consistency**

Scope 在 generator 前冻结并出现在 sources metadata；done 不反转此前 completeness。连接中断不提交 anchor。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_public_contracts.py `
  tests/test_sse.py `
  tests/test_conversation_api.py `
  tests/test_rag_contracts.py `
  tests/test_rag_composite_execution.py -q `
  --basetemp .pytest-story-e4-public
```

运行 frontend tests，要求 exit 0。

```powershell
& npm.cmd --prefix `
  'D:\1999Wiki.worktrees\rag-e-story-segment\frontend\react-app' `
  test -- `
  src/api/sse.test.ts `
  src/store/chatStore.test.ts
```

- [ ] **Step 6: E4 全阶段回归与 D review**

运行 request/authorization/retrieval/runtime/answer/public/anchor 全部测试。D 接受后提交：

```text
feat(rag): expose story segment public contracts
```

---

## 8. E5：离线评测、质量反事实和 D handoff

### Task E5.1：实现离线 Story evaluator 与固定 gate 报告

**Spec coverage:** `EVALSET-P0-01` 至 `EVALSET-P0-18`、`EVAL-P0-01` 至 `EVAL-P0-03`、`GATE-P0-01` 至 `GATE-P0-06`、`PERF-P0-01` 至 `PERF-P0-09`

**Files:**

- Create: `src/rag_eval/story_segment_runner.py`
- Create: `scripts/evaluate_story_segment_rag.py`
- Create: `tests/test_story_segment_eval.py`
- Modify: `tests/test_rag_eval_deterministic.py`
- Modify: `tests/test_rag_eval_scoring.py`
- Modify: `tests/test_rag_eval_reporting.py`
- Modify: `tests/test_rag_eval_runner.py`

- [ ] **Step 1: RED metric contracts**

测试每项输出：

```text
metric
numerator
denominator
baseline
candidate
delta
threshold
direction
passed
```

零 denominator 不得默认为通过。Hard gate 任一失败 → no_go。

- [ ] **Step 2: 实现离线 fake Dense runner**

读取 D0 gold/threshold/baseline，使用确定性 fake vectors/fixture ranks 测全 pipeline；不得把 fake Dense 指标报告为真实 candidate。

- [ ] **Step 3: 实现 authorization/answer gates**

记录 Planner/Detector/Retriever/embedding/reranker 调用数、span assignment、continuation/anchor、partial refusal、overclaim 和 outcome projection。

- [ ] **Step 4: 实现 performance/capacity**

报告：

- structure/segment/typed row counts；
- Story Atom Dense removed count；
- predicted vector bytes；
- build peak RSS；
- local detector/finalizer/fusion/packer P50/P95；
- query embedding calls；
- context chars/segments/citations；
- no reranker。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_eval.py `
  tests/test_rag_eval_deterministic.py `
  tests/test_rag_eval_scoring.py `
  tests/test_rag_eval_reporting.py `
  tests/test_rag_eval_runner.py -q `
  --basetemp .pytest-story-e5-eval
```

- [ ] **Step 6: 停在 D review**

不提交 E5.2。D 接受后提交：

```text
test(rag): add story segment gate evaluator
```

### Task E5.2：生成质量标记反事实，不改变 runtime

**Spec coverage:** `QUALITY-P0-01` 至 `QUALITY-P0-07`、`EVAL-P0-01`、`EVAL-P0-02`、`GATE-P0-04`

**Files:**

- Modify: `src/rag_eval/story_segment_runner.py`
- Modify: `tests/test_story_segment_eval.py`
- No runtime ranking file change

- [ ] 对同一候选模拟 soft penalty，仅报告排名变化。
- [ ] 单列 numeric、short text、exact entity/alias/ID、structured fields。
- [ ] 证明 P0 runtime 输出在启用/禁用反事实计算时逐字节相同。
- [ ] 证明 `context_only/deduplicate/invalid_source` 只来自结构契约，不来自质量分。

- [ ] **停在 D review**

不提交 E5.3。D 接受后提交：

```text
test(rag): report story quality counterfactuals
```

### Task E5.3：完整回归、真实离线产物和不可变 handoff

**Spec coverage:** 全部 `FAILURE-*`、`PROVENANCE-*`、`PERF-*`、`THREAD-P0-04`、`THREAD-P0-05`、`REVIEW-P0-01` 至 `REVIEW-P0-18`

**Files:**

- Modify: `src/rag_eval/story_segment_runner.py`
- Modify: `scripts/evaluate_story_segment_rag.py`
- Modify: `tests/test_story_segment_eval.py`
- Ignored output only: `eval/story_segment/handoffs/$RunId/`

- [ ] **Step 1: 全量 E focused regression**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_structure.py `
  tests/test_story_segments.py `
  tests/test_story_context_units.py `
  tests/test_dense_retrieval_units.py `
  tests/test_huiji_typed_shadow_builder.py `
  tests/test_story_request_plan_v2.py `
  tests/test_story_authorization.py `
  tests/test_story_retrieval_fusion.py `
  tests/test_story_retrieval_budget.py `
  tests/test_story_segment_runtime.py `
  tests/test_story_answer_scope.py `
  tests/test_story_segment_public_contracts.py `
  tests/test_story_segment_eval.py -q `
  --basetemp .pytest-story-e5-focused
```

- [ ] **Step 2: 相邻回归**

运行：

```text
Huiji corpus artifacts/builder/contracts/projection/fidelity
BM25/analyzer
vectorstore/shadow builder
request/query plan
route policy/retriever/budget
citations/execution/composite
conversation/API/SSE
rag_eval deterministic/scoring/reporting/runner
frontend SSE/store
```

全部 exit 0；任何失败进入单独 correction gate，不能折叠进 handoff。

- [ ] **Step 3: deterministic fixture build x2**

两个 create-new roots 比较：

- structure/segment/typed bytes；
- IDs/order hashes；
- schema/config/provenance；
- source maps/context units；
- fake retrieval and AnswerScope bytes。

- [ ] **Step 4: 真实恢复快照离线 build**

生成最终 structure、Segment、mapping、typed JSONL、runtime snapshot、capacity、quality counterfactual 和 offline gates。禁止 embedding/Milvus/network。

- [ ] **Step 5: protected pre/post**

要求 active pointer、active collection inventory、source snapshot、BM25、MinIO/MySQL/config 全部零漂移。

- [ ] **Step 6: handoff**

按 D Plan 1.3 写完整文件，并计算 handoff 自身 SHA-256。`ready_for_d_shadow_build` 仅在所有不依赖真实 embedding 的 hard gate 通过且 remaining blockers 为空时为 true。

- [ ] **Step 7: 停在 D review**

不创建 Milvus，不调用 embedding，不激活。D 接受后提交 E5 代码：

```text
test(rag): produce story segment offline handoff
```

真实 handoff 输出不提交。

---

## 9. E Task 提交与监督协议

每个下列 Task 都是独立 D review gate；前一提交被 D 接受前不得开始后一 Task。建议提交边界：

```text
E0.1  feat(rag): parse story source structure
E0.2  feat(rag): publish story atom structure sidecar
E1.1  feat(rag): build deterministic story segments
E1.2  feat(rag): map story segments to atom citations
E2.1  feat(rag): publish typed dense retrieval units
E2.2  feat(rag): add typed dense shadow adapter
E3.1  feat(rag): finalize request plan v2
E3.2  feat(rag): authorize story retrieval scope
E3.3  feat(rag): validate story continuation and anchors
E3.4  feat(rag): fuse and budget story segments
E4.1  feat(rag): execute story segment context units
E4.2  feat(rag): normalize grounded story answer scope
E4.3  feat(rag): expose story segment public contracts
E5.1  test(rag): add story segment gate evaluator
E5.2  test(rag): report story quality counterfactuals
E5.3  test(rag): produce story segment offline handoff
```

每个 Task：

1. 只修改本阶段 allowlist。
2. RED 输出先报告 D。
3. GREEN 和相邻回归完成后停下。
4. D 独立检查 diff、测试、真实证据和 forbidden counters。
5. D 批准后才提交。
6. 提交后再接收下一阶段 `approved-resume.md`。

同一阶段若因规模需要多个提交，必须由 D 先批准边界；不得为了“整齐”危险拆分已互相依赖的 hunks，也不得把后续阶段提前塞入。

---

## 10. 完整 Spec 追踪矩阵

| Spec 范围 | E Plan Task | RED/Gate |
|---|---|---|
| `SCOPE-P0-01..06` | E0.0–E0.2、E5.3 | 依赖 receipt、Atom 零修改、无 worktree 输入 |
| `DECISION-P0-01..04` | E1.1、E2.1、E3.4 | Atom 规范、Segment 视图、两通道和 Segment ranking |
| `HIER-P0-01..03` | E0.2、E1.1 | Parent 不变、Atom 恰属一个 Segment、同 Owner 闭包 |
| `ATOMSTRUCT-P0-01..16` | E0.1–E0.2 | parser/registry/graph/length/real snapshot |
| `SEGMENT-P0-01..06` | E1.1 | ordered atoms、正文、search、图关系 |
| `CITATIONUNIT-P0-01..09` | E1.2、E4.1、E4.3 | Segment once、Atom spans/source、双预算和 public schema |
| `BOUNDARY-P0-01..12` | E1.1 | hard boundaries、soft targets、oversize、cycle/merge |
| `IDENTITY-P0-01..04` | E1.1–E1.2 | canonical hash、input/config identity、determinism |
| `ENTITYLINK-P0-01..03` | E0.1、E3.2、E3.4 | exact registry、mentioned filter、no fuzzy ownership |
| `REQUESTPLAN2-P0-01..13` | E3.1、E4.1 | provisional/final transaction、span/assignment/envelope |
| `STORYBRANCH-P0-01..30` | E3.2 | direct detection、1–3、4–32、33+、Owner allowlist |
| `STORYBRANCH-P0-31..40` | E3.3 | continuation + anchor lifecycle |
| `STORYBRANCH-P0-41..49` | E3.2–E3.3、E4.3 | detection boundaries、strict actions、stale/tamper |
| `AUTHCTX-P0-01..06` | E3.2–E3.3 | one context schema、origin/status/coverage invariants |
| `INDEX-P0-01..06` | E2.1 | Atom BM25、Segment Dense input、no Segment BM25 |
| `DENSEUNIT-P0-01..11` | E2.1–E2.2 | typed JSONL/schema/adapter/fake collection |
| `PIPE-P0-01..09` | E3.4、E4.1–E4.2 | dispatch/order/query reuse/scope after packet |
| `FUSION-P0-01..09` | E3.4 | exact numeric formula/config/tie-break |
| `CANDIDATE-P0-01..04` | E3.4 | channel-local K、exact Atom map、Topic reserve |
| `OWNERBUDGET-P0-01..05` | E3.4 | required owners/round-robin/4+ continuation |
| `CONTEXTBUDGET-P0-01..08` | E1.2、E3.4 | five budgets、render cost、whole Segment removal |
| `DETAIL-P0-01..02` | E3.4 | multi-anchor diversity、no facet LLM |
| `MULTISTORY-P0-01..05` | E3.4、E4.1 | Owner grouping/order/failure/continuation limits |
| `RELATION-P0-01..03` | E1.1、E3.4 | graph adjacency without causal inference |
| `QUALITY-P0-01..07` | E0.1、E5.2 | no hard quality effects、counterfactual only |
| `SHORTFALL-P0-01..05` | E3.4、E4.2 | evidence vs authorization、partial answer |
| `ANSWER-P0-01..10` | E4.2 | nullable scope、three states、best effort/strict/non-exhaustive |
| `ANSWER-P0-11..13` | E4.3 | unique RouteDecision fact、REST/SSE consistency |
| `SUMMARY-P0-01..03` | E4.2 | no exhaustive claim、still answer usefully |
| `FAILURE-P0-01..10` | E0.2、E1.2、E2.2、E4.1、E5.3 | snapshot/hash/type/closure/fallback blockers |
| `PROVENANCE-P0-01..06` | E0.2、E1.2、E2.1、E5.3 | source/code/config/model/artifact identities |
| `PERF-P0-01..09` | E3.4、E5.1、E5.3 | row/call/latency/capacity and fixed P95 measures |
| `EVALSET-P0-01..18` | E5.1、D0 baseline | frozen gold/equivalence/auth/answer cases |
| `EVAL-P0-01..03` | E5.1–E5.2 | quality shadow/protected no-regression/no full-summary metric |
| `GATE-P0-01..06` | E5.1–E5.3、D real eval | hard no-go, explicit receipts, no activation |
| `THREAD-P0-01..10` | E0.0、阶段协议、D Plan | single E worktree/session, D review and D vector build |
| `SUPERVISOR-P0-01..04` | D0 only；E0.0 consumes | E only validates D0 receipt and independent state |
| `REVIEW-P0-01..18` | 全阶段 | root-cause contracts, no compatibility guessing, deterministic gates |
| `DETAIL-P1-01`、`SUMMARY-P1-01` | 不实施 | evidence facets 与全章分批摘要必须另立 Spec、评测和批准 |

---

## 11. E 完成标准

1. 每个规范 Story Atom 恰好一条 structure sidecar；显式图闭合、source-order 明确、invalid graph 阻断。
2. 纯数字、短文本、内部 ID 和歧义 alias 按统一 registry 规则处理，无逐实体补丁。
3. 每个 Atom 在一个 Segment 版本中恰好一次；Atom parent/ID/content/source 不变。
4. oversize Atom 形成单 Atom Segment，Dense limit fail-closed，不截断。
5. Segment 两次构建字节一致，prev/next/branch/merge 闭合。
6. Segment 正文一次封装；每个非空 Atom 一个 span 和 citation source。
7. Story Atom 仍在 BM25，typed Dense 输入中 Story Atom 数为 0。
8. 非 Story Child 和 Story Segment 使用显式 typed IDs/fields；Segment 不冒充 Child。
9. RequestPlan v2 只运行一次 Detector 和至多一次本地 fallback；所有 Story occurrence 唯一归属。
10. Direct、continuation、anchor 三来源共享一个授权上下文和 Retriever 入口。
11. 1–3 Story 获准且全覆盖；4–32 可分页且每页可达 authorized；33+ narrowing；无 Composite 比较。
12. 原 Owner Gate 未放宽，角色/Topic Story 补充分支只消费授权 allowlist/关系。
13. 融合公式、排序、Owner 配额和五类预算完全确定；Topic/Page 不被 Story 淹没。
14. 有可提交证据的 shortfall 输出非空 grounded answer；授权边界、failed、empty 不混淆。
15. AnswerScope 只在适用 Story 分支存在；不新增模型调用。
16. 请求级唯一 retrieval outcome 来自 `ResponsePacket.retrieval_packet.route_decision.retrieval_outcome`；REST/SSE 一致。
17. Reranker 调用为 0；质量反事实不改变 runtime。
18. 全部 focused/adjacent tests 通过，真实离线 snapshot protected drift 为 0。
19. E handoff 完整且 `ready_for_d_shadow_build` 的含义仅为可交 D。
20. E 未调用 embedding、未写 Milvus、未激活；后续真实向量重建只由 D 执行。
