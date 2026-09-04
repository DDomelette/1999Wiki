# 线程 E：剧情 Segment 双粒度检索与预算 Implementation Plan

> **当前执行依据（2026-09-05）：** 用户已批准 1A + 2A，保留功能、质量和安全约束，允许收敛实现与验收流程。后续执行先遵循 [D Plan 的 2026-09-05 收敛修订](2026-07-30-rag-story-segment-d-integration.md#2026-09-05保留功能收敛实现与验收流程)，其流程要求优先于本文件的历史步骤。保持现有 `D → E` 两层及现有工作树/会话；E 沿用用户最后设置的 `gpt-5.6-sol / max / fast`。当前只按 D 明确放行的收敛批次执行，不重新启动 C/D0，不因普通重构新增逐修复审批回执。

**Goal:** 从线程 C 发布的规范 Story Atom 和冻结 Data:Story 来源构建可重建的剧情结构 sidecar 与 Story Segment；保留 Atom BM25、改用 Segment Dense；在 Segment 层完成受控授权、融合、Owner/上下文预算和 Atom 精确引用，并交付不含真实 embedding 或生产写入的离线候选与评测 handoff。

**Architecture:** E0 首先解析并冻结来源 step/choice/branch/entity 结构，生成与 Atom 一一闭合的 sidecar；E1 基于 sidecar 生成确定性 Segment、`SegmentContextUnit` 和 Atom spans；E2 构建同时容纳非 Story Child 与 Story Segment 的 typed Dense 离线 JSONL、schema 和假向量适配器；E3 用一次性 `RequestPlan v2` 事务和统一 `StoryAuthorizationContext` 建立受控 Story 分支，在 Segment 层完成融合与分层预算；E4 将 Context Unit、Atom 引用、AnswerScope、continuation、anchor、REST/SSE 和唯一 retrieval outcome 事实源接入现有运行时；E5 冻结离线报告、容量和 D handoff。E 不调用真实 embedding，也不写 Milvus。

**Tech Stack:** Conda `1999wiki` 中的 Python 3.11.15（`D:\Anaconda32024\envs\1999wiki\python.exe`，`sys.prefix=D:\Anaconda32024\envs\1999wiki`）、dataclasses、Pydantic v2、FastAPI、SSE、React/TypeScript、BM25、Milvus typed-row contracts、pytest 9.1.1、JSON/JSONL、SHA-256、现有 Huiji corpus builder 与 RAG execution pipeline。

## Global Constraints

- 批准的设计源头：`docs/superpowers/specs/2026-07-30-rag-story-segment-retrieval-design.md`。
- 批准基线提交：`300e4066630c6564d56157442765a4675b783590`。
- 批准 Spec SHA-256：`61bf46e1ec6f44b330913d1b1effdfd1828edf72b13ccd7ea8f60c61fa7f405d`。
- 配套 D Plan：`docs/superpowers/plans/2026-07-30-rag-story-segment-d-integration.md`。
- E 从 C8b–C9 已完成、D 已合并 C、合并后 C fidelity 已通过且 D0 完成后的固定 `main` 创建，分支为 `codex/rag-e-story-segment`，工作树为 `D:\1999Wiki.worktrees\rag-e-story-segment`。
- E0 → E1 → E2 → E3 → E4 → E5 严格串行；每个 Task 完成后必须停在 `completed_pending_review`，由 D 独立验收、批准提交并放行下一 Task。
- E 使用 `gpt-5.6-sol`、标准速度、`workspace-write`、`fast_mode=false`、`multi_agent=false`。
- E 禁止子代理、第二个 CLI worker、读取 C worktree、复制其他 worktree 代码或使用对话摘要作为契约。
- 所有 Python/pytest 命令必须使用 `D:\Anaconda32024\envs\1999wiki\python.exe`；禁止裸 `python`、`py`、`pytest`。
- 每次启动或恢复 E，先验证 `sys.version_info == (3, 11, 15)`、`sys.prefix == D:\Anaconda32024\envs\1999wiki`、HEAD、D0 dependency receipt 及其绑定的 C release receipt。
- C release receipt 必须证明 C8b/C8c/C8d/C9 已验收、C 已合并到 `main`、合并后真实 fidelity 正常返回、Story Parent/Atom/source refs 无 blocker；否则 E0.0 立即停止。
- E 只消费 C release receipt 固定的 `main` build root 与公共 artifact；不得从 C branch、C worktree、ignored 诊断目录或聊天摘要补取字段。
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
- 所有实现采用 TDD：E 只写 RED test 并停下，D 在实现前独立复跑并签发 RED acceptance，E 才做最小 GREEN、阶段回归和真实快照 create-new 证据。
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
| `src/rag_eval/story_segment_runner.py` | E5 离线指标、质量反事实、离线容量估算、gate 和 handoff |
| `scripts/build_story_segment_candidate.py` | 合并后由 D 调用的 create-new 离线候选重建入口；输出 `rag.story-candidate-build-input/v1`，不伪造 runtime snapshot，不调用 embedding/Milvus |
| `scripts/probe_story_segment_storage.py` | D 后置只读探测 hash-pinned 云端 Milvus/artifact/staging 卷并生成容量 receipt；E 只用 fake SSH/subprocess 测试 |
| `scripts/build_huiji_typed_index.py` | D 后置执行的只读 Milvus preflight 与 create-new typed shadow builder；E 只用 fake client 测试 |
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
| `src/huiji_rag/runtime_artifacts.py` | 保持 active v1 行为不变；新增显式 typed-story v2 isolated snapshot capability、完整文件元组和 fail-closed selector |
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
tests/test_huiji_runtime_artifacts.py
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
    chunk_index: int
    segment_sequence_index: int
    content_hash: str
    artifact_identity: str
```

Identity：

```text
child:<child_id>
story_segment:<segment_id>
```

Milvus primary key 为 `retrieval_unit_id VARCHAR(256)`；`text VARCHAR(16384)`；vector 为 `FLOAT_VECTOR(1024)`；`child_id/segment_id` 保持独立 nullable 字段。`chunk_index` 与 `segment_sequence_index` 都是非 nullable `INT64`：Child 的 `segment_sequence_index=-1`，Story Segment 的 `chunk_index=-1`；适用字段必须 `>=0`。不得在存储层把 `None`、空串或缺字段当作 `-1`。

### 2.3.1 Candidate build input 与最终 runtime snapshot

现有 `RuntimeArtifactSnapshot` 的 child/media v1–v3 capability 不能靠“附加几个可选路径”静默变成 Story typed snapshot。离线产物与真实 Milvus 状态必须分成两个不可混淆的身份层。

E2.1 定义并验证预向量输入：

```text
schema_version = rag.story-candidate-build-input/v1
story_retrieval_capability = typed_story_v2
```

`rag.story-candidate-build-input/v1` 必须固定：

```text
Parent/Child/media/BM25 legacy tuple
Story structure artifact
Story Segment artifact
Atom-to-Segment mapping
SegmentContextUnit/Atom span artifact
typed Dense JSONL + schema + manifest
Story registry/config identities
RequestPlan/Policy/Fusion/AnswerScope config identities
expected typed Milvus schema fingerprint
embedding provider/model/dimension/normalization identity
complete ordered tuple SHA-256
```

它不得包含尚未创建的 collection 名、实际 collection schema、实际 row count 或 build receipt，也不得被 runtime selector 消费。

D4 在真实 shadow collection 创建、写入和只读验证完成后，才生成最终运行快照：

```text
snapshot_schema_version = rag.runtime-artifact-snapshot/v2
story_retrieval_capability = typed_story_v2
```

该 v2 snapshot 必须包含 candidate-build-input 的完整身份，并额外固定：

```text
actual collection name
observed collection schema fingerprint
observed row count and retrieval-unit type counts
shadow build receipt path and SHA-256
embedding build identity and ordered primary-key hash
protected active inventory identity
complete ordered runtime tuple SHA-256
```

规则：

- E2.1 实现两个 schema/parser/validator；E2.2 的 fake builder 只能在 fake collection 写入和验证完成后生成测试用 v2 snapshot；
- E5.3 与 D3 只能生成 `rag.story-candidate-build-input/v1`，不得伪造最终 v2 snapshot；
- active v1/v2/v3 解析和 `resolve_runtime_artifact_snapshot()` 行为逐字节兼容；
- 只有 `resolve_isolated_story_candidate_snapshot_v2()` 可解析 D4 已验证的 typed Story v2 snapshot；
- selector 只读取 manifest 声明的 schema/capability，不从字段存在性推断；
- 任一必需文件、哈希、schema、实际 row count、collection capability 或 build receipt 缺失和 active overlap 均 fail-closed；
- v2 snapshot 在激活前只能用于显式传入的 isolated evaluator/runtime probe，不能替换 active pointer。

### 2.4 RequestPlan v2 与统一授权

```python
@dataclass(frozen=True)
class SourceQuerySpan:
    query_char_start: int
    query_char_end: int
    source_text_sha256: str
    schema_version: Literal["SourceQuerySpan/v1"] = "SourceQuerySpan/v1"

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
    schema_version: Literal["StoryAuthorizationContext/v1"]
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
    schema_version: Literal["StoryAnswerScope/v2"]
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

**Spec coverage:** `SCOPE-P0-01` 至 `SCOPE-P0-03`、`SCOPE-P0-06`、`THREAD-P0-04` 至 `THREAD-P0-10`

**Files:** no tracked changes

- [ ] 读取并验证 Spec、D Plan、E Plan 和 `.codex-supervisor/workers/E/dependency-receipt.v1.json`。
- [ ] 验证工作树 HEAD 等于 D0 receipt 的 `main_commit`。
- [ ] 从 D0 receipt 取得 C release receipt 路径/期望 SHA-256，重新验证 `rag.thread-c-release/v1`、`e_dependency_ready=true`、C merge commit 为 HEAD 祖先、C8b–C9 identities、Story Parent/Atom/source-ref/build-manifest hashes、32 项保护状态零漂移。
- [ ] 验证所有设计依赖已被 Git 跟踪，且 commit/SHA-256 与 receipt 一致；任何 E 输入路径都不得落在 C worktree 或 ignored `eval/task8-c-*`。
- [ ] 验证解释器：

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -c `
  "import sys; assert sys.version_info[:3] == (3,11,15); assert sys.prefix == r'D:\Anaconda32024\envs\1999wiki'"
```

- [ ] 验证 reranker disabled、Milvus/embedding 环境只读，不运行网络探针。
- [ ] 验证本轮只增加剧情派生检索视图；全局核心数据模型未被重写，reranker、Segment BM25 和全章摘要均保持禁止。
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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e0-structure-red-' + [Guid]::NewGuid().ToString('N')))
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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e0-structure-green-' + [Guid]::NewGuid().ToString('N')))
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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e0-regression-' + [Guid]::NewGuid().ToString('N')))
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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e1-segments-' + [Guid]::NewGuid().ToString('N')))
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
- Modify: `src/huiji_rag/build/contracts.py`
- Modify: `src/huiji_rag/build/orchestrator.py`
- Modify: `src/huiji_rag/build/artifact_writer.py`
- Modify: `src/rag/contracts.py`
- Modify: `src/rag/citations.py`
- Modify: `tests/test_citations.py`
- Modify: `tests/test_rag_global_citations.py`
- Modify: `tests/test_huiji_corpus_artifacts.py`
- Modify: `tests/test_huiji_corpus_builder.py`
- Modify: `tests/test_huiji_corpus_builder_contracts.py`

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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e1-regression-' + [Guid]::NewGuid().ToString('N')))
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
- Modify: `src/huiji_rag/runtime_artifacts.py`
- Modify: `tests/test_huiji_corpus_artifacts.py`
- Modify: `tests/test_huiji_corpus_builder.py`
- Modify: `tests/test_huiji_runtime_artifacts.py`

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
- exact field set 使用 `segment_sequence_index`，不存在 `segment_sequence`；两个 index 字段均为 INT64 且非适用值只能是 `-1`。
- active v1 snapshot 行为完全不变；
- complete candidate-build-input 固定所有离线 Story artifact、config、typed rows 和 expected collection schema；
- candidate-build-input 若携带伪造 actual collection/row count/build receipt 则拒绝；
- incomplete/field-inferred/active-overlap typed Story v2 snapshot fail-closed；
- fake D4 runtime snapshot fixture 的 actual collection、observed schema/rows 和 build receipt identities 闭合。

- [ ] **Step 2: 实现 builder**

不读取 BM25 排名或质量 flag 决定是否删除 Story Atom；Story Atom 的排除只由 `entity_type=story + canonical Atom section contract` 决定。

- [ ] **Step 3: 发布 artifact**

```text
dense_retrieval_units.v1.jsonl
dense_retrieval_units.v1.schema.json
dense_retrieval_units.v1.manifest.json
```

Manifest 包含 Child/Segment counts、Story Atom excluded count、ordered ID hash、text hash、schema/config/code/source identities，并发布 `rag.story-candidate-build-input/v1` 所需的完整离线 tuple 和 expected typed Milvus schema。不得把 Segment 路径塞进旧 snapshot 的 Child 字段，也不得在尚未构建 collection 时生成最终 v2 runtime snapshot。

- [ ] **Step 4: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_dense_retrieval_units.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_builder.py `
  tests/test_huiji_runtime_artifacts.py `
  tests/test_sparse_bm25.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e2-artifact-' + [Guid]::NewGuid().ToString('N')))
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
- Modify only for the acyclic final-receipt field set and active-v1 resolver source-byte contract: `src/huiji_rag/runtime_artifacts.py`
- Create: `scripts/probe_story_segment_storage.py`
- Create: `scripts/build_huiji_typed_index.py`
- Create: `tests/test_huiji_typed_shadow_builder.py`
- Modify only for the acyclic final-receipt fixture/contract: `tests/test_dense_retrieval_units.py`
- Modify: `tests/test_vectorstore.py`
- Modify: `tests/test_huiji_shadow_builder.py`

- [ ] **Step 1: RED schema/adapter tests**

Fake Milvus 必须断言：

- PK 为 `retrieval_unit_id`；
- type/child/segment nullable invariant；
- schema fields/limits/dimension；
- Milvus exact field names/types/nullability/default sentinel 与 `rag_dense_retrieval_unit/v1` 完全一致；
- typed row round-trip；
- `milvus_entity_to_document()` 保留 unit type 和 ID；
- unknown type fails；
- active legacy collection loader 仍能读 active v1；
- active v1 string-search filter/result ordering 与既有测试逐项一致；委托 query-by-vector 不改变外部返回契约；
- fake builder 拒绝 active/forbidden/existing target；
- remote storage receipt 的 host/device/path/input/TTL 任一未知、stale 或不一致时，在 embedding/Milvus client 构造前拒绝；
- Story Segment row count `>25000` 或任一受影响云端设备 projected free space `<12 GiB` 时，在 embedding/Milvus client 构造前拒绝；
- 只读 Milvus preflight 只有在 remote storage receipt 通过后才可构造 client，且 write count 为 0；
- missing/stale/unknown/failed Milvus preflight receipt 在 embedding provider/写 client 构造前拒绝；
- fake collection 写入完成前不得生成 `rag.runtime-artifact-snapshot/v2`；
- 成功 fake build 的 v2 snapshot 固定 actual collection/schema/row counts/build receipt；
- `resolve_active_runtime_snapshot_source_v1(cfg)` 的同一次调用返回已验证的 active snapshot 与 exact canonical source bytes；成功 fake build 输出的 `active-control-runtime-snapshot.v1.json` 必须与该 source bytes 逐字节相同，禁止从 dataclass 或 typed-v2 字段再次序列化；
- shadow build receipt 的 `active_control_snapshot` 固定该 copy 的相对路径、size 和 SHA-256；receipt 不得包含 `candidate_runtime_snapshot` 或最终 v2 snapshot 的 raw-byte SHA-256；
- 最终 v2 snapshot 单向固定 shadow build receipt 的相对路径与 raw-byte SHA-256，`runtime-artifact-snapshot.v2.sha256` 再固定最终 snapshot 的 raw-byte SHA-256；禁止 receipt 与 snapshot 互相包含对方最终 raw-byte SHA-256；
- v2 resolver 与测试 fixture 必须使用同一个精确 receipt field set：包含 `active_control_snapshot`，不包含 `candidate_runtime_snapshot`；不得同时接受两套未版本化 field set 或按字段猜测版本；
- active-control capture 前后 active pointer/config/collection inventory 逐字节一致；
- deployment inventory 的 principal/allowed roles/allowed grant 五元组任一缺失、主体或作用域漂移、未显式批准 wildcard 时，在写 client 构造前拒绝；
- success receipt 精确包含 `status`、`protected_state_before`、`protected_state_after` 和严格的 `execution_observations`，并记录 embedding/Milvus API calls、batch/retry/token-safe/timing/paged closure；缺失、额外或伪造字段均拒绝；
- D4 已存在且含两个 preflight receipts 的 RunRoot 可被使用，但任何最终输出文件或 failure receipt 已存在、为 symlink/reparse target 或越出 project root 时，在外部调用前拒绝；
- embedding/insert 使用确定性有界 batch 和有限 retry；写后验证使用分页/iterator，不得提交超过服务端 limit 的单次 query；
- embedding failure 保留 shadow 和 failure receipt；
- fake embedding 不重复处理同一 ordered row；
- query-by-vector path never calls embedding；
- string search delegates through exactly one `embed_query()` call；
- the same immutable query vector can be reused for Child and Story Segment filters without re-embedding；
- 无真实网络或 Milvus。

- [ ] **Step 2: 实现 typed schema/adapter**

不要把 Segment 塞入现有 child-only helper；新增 typed helper，并保持旧 helper 行为不变直到独立激活。

冻结 query reuse 接口：

```python
def embed_query(self, query: str) -> tuple[float, ...]: ...

def similarity_search_by_vector_with_relevance_scores(
    self,
    query_vector: Sequence[float],
    *,
    k: int,
    retrieval_unit_types: tuple[RetrievalUnitType, ...],
    owner_ids: tuple[str, ...] = (),
) -> list[tuple[Document, float]]: ...
```

现有 string search 只能调用一次 `embed_query()` 后委托 query-by-vector。query-by-vector 必须校验维度和有限数值，不得调用 embedding provider。E3.4 对一个知识子任务先取一次 immutable vector，再分别查询 Child 与 Story Segment；spy 断言相同 query/model identity 的 embedding call count 为 1。

- [ ] **Step 3: 实现 D 后置三段门**

`scripts/probe_story_segment_storage.py` 与 typed-index CLI 共同提供三个严格串行入口：

```text
storage probe      读取 candidate-build-input 和 hash-pinned deployment inventory；
                   通过 fake SSH/真实 D 只读 SSH 探测 /srv/1999wiki/milvus、
                   /srv/1999wiki/rag-artifacts、/srv/1999wiki/import-staging；
                   禁止构造 embedding/Milvus client
milvus-preflight   必须重验通过且未过期的 remote storage receipt；
                   只读验证 collection absence、active/forbidden inventory 和 RBAC；
                   write count 必须为 0
build              必须同时重验 storage 与 Milvus preflight receipts；
                   此后才可构造 embedding provider/写 Milvus client；
                   成功写入验证后生成最终 runtime snapshot v2
```

三个入口都要求同一 `rag.story-candidate-build-input/v1` 路径和期望 SHA-256。Storage receipt 固定 deployment inventory、远端 host key、路径/device、逐设备峰值公式和 `ttl_seconds=900`；硬门为 `story_segment_rows <= 25000` 且所有受影响设备 `projected_free_bytes >= 12 GiB`。Milvus preflight receipt 固定只读 inventory/RBAC、collection 名、写计数和 `ttl_seconds=300`。Deployment inventory 的 exact RBAC policy 固定 `principal`、无重复升序 `allowed_roles`，以及 `role_name/database/object_type/object_name/privilege` 五元组集合；目标 collection 只能由 inventory 中受约束的 shadow-name 模板实例化，任何 wildcard 必须作为完整允许五元组显式出现。Observed user/role/grant 必须规范化为同一类型后精确比较，不能把 `object_name` 当 privilege，也不能从 observed grants 反推允许策略。Builder 默认拒绝缺少 active/forbidden inventory、两个 receipt 身份不一致、任一 receipt 超时或时钟倒退；最终 v2 snapshot 不可作为 build 输入。成功 build 的固定输出契约为：

```text
shadow-build-receipt.v1.json
active-control-runtime-snapshot.v1.json
runtime-artifact-snapshot.v2.json
runtime-artifact-snapshot.v2.sha256
```

`src/huiji_rag/runtime_artifacts.py` 新增 `resolve_active_runtime_snapshot_source_v1(cfg) -> tuple[RuntimeArtifactSnapshot, bytes]`。该接口在一次 active-v1 resolution 内生成 exact `rag.active-control-runtime-snapshot/v1` canonical source bytes；其内容只能来自同一次调用已验证的 active pointer、runtime config、artifact tuple、collection identity 与 source raw-byte hashes。`active-control-runtime-snapshot.v1.json` 必须逐字节复制这份 bytes，不得由 typed v2 字段、返回的 dataclass 或第二次序列化反推。Receipt 固定 `active_control_snapshot`，并以 `protected_state_before`/`protected_state_after` 证明 active pointer/config/collection inventory 零漂移；最终 v2 snapshot 固定 receipt 的相对路径与 raw-byte SHA-256，配套 `.sha256` 文件固定最终 snapshot。该单向证据链不得通过互相嵌入 raw-byte SHA-256 重新形成环。

成功 `rag.story-shadow-build-receipt/v1` 的 exact top-level fields 为：`schema_version/status/candidate_build_input_sha256/actual_collection_name/observed_collection_schema_fingerprint/observed_row_count/observed_retrieval_unit_type_counts/embedding_build_identity/ordered_primary_key_sha256/active_control_snapshot/protected_state_before/protected_state_after/execution_observations`。`execution_observations` 只包含三个 exact object：`embedding`、`milvus_write`、`closure_verification`；它们分别固定 API call/batch/max-batch/retry/token-safe/timing，create/insert/index/load/query-page/retry/timing，以及 observed count/PK/type/schema identities。所有 count 为非负整数、elapsed 为有限非负数，row totals 必须与 candidate 和 observed closure 相等。Failure receipt 使用独立 schema，记录失败 phase、collection-created、shadow-preserved 和 protected post；按 D Plan 保留 shadow，不自动 drop。

CLI 必须把 candidate artifact root 固定为 `candidate-build-input.v1.json` 的父目录，把公共 containment/runtime evidence root 固定为 `cfg.paths.project_root`。D4 的 RunRoot 已由前两段门创建；Builder 只独占最终输出文件名，不要求 RunRoot 不存在。Provider/client、create、bounded embedding/insert batches、index/load、分页/iterator closure、active-control 与 receipt/snapshot publication 全部进入统一 failure handling；任一已存在 collection/output、race、symlink/reparse escape 或 publication failure 均 fail-closed 且不覆盖既有证据。Dry-run 仍执行全部本地 schema/path/hash/receipt/active-control/gate 验证，只禁止外部连接、写入和最终输出。

- [ ] **Step 4: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_dense_retrieval_units.py `
  tests/test_huiji_typed_shadow_builder.py `
  tests/test_huiji_runtime_artifacts.py `
  tests/test_vectorstore.py `
  tests/test_huiji_shadow_builder.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e2-vectorstore-' + [Guid]::NewGuid().ToString('N')))
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
- v1/v2 不猜测兼容；
- `SourceQuerySpan/v1` 与 `rag.request_plan/v2` exact schema name/field set，拒绝旧前缀别名和额外字段。

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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e3-request-plan-' + [Guid]::NewGuid().ToString('N')))
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
- 零显式 Story + 已授权 character/Topic filter 的 `story_mentions/story_examples` 产生 `direct_query/open_story_domain`，四个 Story 数组为空；
- open domain 缺 filter、未授权 filter、跨类型歧义、Planner-only filter 或 anchor-derived filter 均拒绝；
- `StoryAuthorizationContext/v1` exact schema name/field set，拒绝 `rag.story-authorization-context/v1` 镜像、额外字段和不合法 coverage/status 组合；
- detector deterministic identity；
- 本地步骤 P95 测量接口。

- [ ] **Step 2: 实现 request-level detector**

Detector 只扫描 original query 一次；不读取 Planner refs 或 conversation anchor；输出 occurrence IDs、ranges、registry identity、ambiguity 和 full count。

- [ ] **Step 3: 实现 direct authorization**

```text
0 explicit Story:
  non-Story branch -> no Story context
  proposed story_required -> denied unless anchor path later validates
  proposed story_mentions|story_examples + one Policy-authorized character/Topic filter
    -> authorized/direct_query/open_story_domain
       detected/planner/required Story refs and authorized_story_owner_ids all empty

1..3:
  exact planner/detected ordered-set match -> authorized/complete

4..32:
  needs_continuation, coverage=null, no retriever

33+:
  denied/narrow_story_scope, coverage=null, no retriever
```

Planner omission/extra/reorder/ambiguity fail-closed。Retriever 只能消费 `authorized_story_owner_ids`。

`open_story_domain` 不是无界 Owner 放行：它没有 Story Owner allowlist，只允许 `story_filter` 中一个已经通过原 entity/topic Policy 的 canonical character 或 Topic identity；不能来自 Planner 自报字符串、conversation anchor 或 fuzzy alias。若该 filter 缺失、歧义、跨类型冲突或未获 primary Policy 授权，则拒绝 Story 补充分支。

- [ ] **Step 4: 保持原 Owner Gate**

`primary_owner` 仍走 entity/topic strict；显式 Story 的 `story_mentions/story_examples` 使用独立已授权 Owner allowlist；`open_story_domain` 只按已授权 character/Topic filter 检索 Story mentions/examples。两者都不把 Story row 混入 primary Owner Gate，也不能读取 anchor 扩大范围。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_authorization.py `
  tests/test_story_request_plan_v2.py `
  tests/test_route_policy.py `
  tests/test_query_plan.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e3-authorization-' + [Guid]::NewGuid().ToString('N')))
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

- [ ] **Step 1: RED continuation tests**

覆盖：

- 4/5/32 Story 每页最多 3；
- next page 可跨新 HTTP 请求进入 authorized/page_partial；
- Planner 0 calls；
- 完整原 query/final plan/detection/assignment/continuation receipts 可重验；
- canonical JSON <= 65536 bytes；
- unknown/missing/tampered/stale/oversize fail；
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
- pure turn-event reducer 对未提交/失败 turn 不产生可消费 anchor；
- most recent clear shadows old set。

- [ ] **Step 3: 实现 continuation**

Action payload 是不可信完整输入，不是授权 token；Policy 重算 hash、Detector 和当前 registry allowlist，不调用 Planner。

- [ ] **Step 4: 实现 anchor data model、projection 与 resolver**

`ConversationTurn.story_anchor_event` 是唯一事实；`_Entry` 不双写。E3.3 只实现不可变 event、纯 projection/reducer、TTL 和 follow-up resolver，不接线 answer/citation/SSE 的最终提交；该原子提交由 E4.1/E4.3 在统一 execution 中完成。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_authorization.py `
  tests/test_conversation_memory.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e3-continuation-anchor-' + [Guid]::NewGuid().ToString('N')))
```

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

先运行两个精确 RED node：

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_retrieval_fusion.py::test_real_atom_and_segment_channels_fuse_with_one_query_embedding `
  tests/test_retriever.py::test_open_story_domain_consumes_only_authorized_canonical_filter -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e3-fusion-red-' + [Guid]::NewGuid().ToString('N')))
```

第一个使用完整 rank tables 断言每项浮点值和排序；覆盖缺 rank、rank=0、负值、NaN/Inf、重复 channel rank、unknown unit type、同文本跨 Story、不累加第三 Atom/Segment。第二个证明 `open_story_domain` Retriever 只消费 Policy 已授权的 canonical character/Topic filter，显式 Story allowlist 为空、不得读取 conversation anchor、返回 Owner 最多 3 个；Planner proposal、模糊名称或未授权 filter 均不能进入搜索。

- [ ] **Step 2: 实现 channel-local candidates**

Atom BM25 Top-80 和 Segment Dense Top-30 先在各通道产生；Atom 命中先映射 Segment；映射前不得执行跨通道最终截断。Topic/Page reserve=10，seed segments<=8。

- [ ] **Step 3: 实现 typed Dense dispatch/query reuse**

一个知识子任务相同 query/model identity 通过 E2.2 的 `embed_query()` 只 embed 一次，并把同一个不可变 vector 传给 Child/Segment 两次 query-by-vector 搜索；最多两个不同 Dense query，trace 记录 query/model identity、vector identity 和调用数。测试 spy 必须证明 string helper 未被两个通道分别调用。

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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e3-retrieval-' + [Guid]::NewGuid().ToString('N')))
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
- Modify: `src/rag/conversation.py`
- Modify: `backend/sse.py`
- Create: `tests/test_story_segment_runtime.py`
- Modify: `tests/test_rag_contracts.py`
- Modify: `tests/test_citations.py`
- Modify: `tests/test_rag_global_citations.py`
- Modify: `tests/test_rag_execution.py`
- Modify: `tests/test_rag_composite_execution.py`
- Modify: `tests/test_conversation_memory.py`
- Modify: `tests/test_sse.py`

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
- answer + citation validation + ConversationTurn + StoryAnchorEvent 在同一 lease-lock commit 中原子成功；
- generation/citation/aggregation/SSE interruption 任一失败都不写 partial anchor event；
- single Story cited success set，multi/page-partial/empty/denied/failed clear，local/meta/smalltalk no-op；
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
→ decide StoryAnchorEvent
→ atomic turn + event commit
```

- [ ] **Step 3: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_runtime.py `
  tests/test_rag_contracts.py `
  tests/test_citations.py `
  tests/test_rag_global_citations.py `
  tests/test_rag_execution.py `
  tests/test_rag_composite_execution.py `
  tests/test_conversation_memory.py `
  tests/test_sse.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e4-runtime-' + [Guid]::NewGuid().ToString('N')))
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
- `StoryAnswerScope/v2` exact schema name/field set，拒绝 `rag.story-answer-scope/v2` 镜像或别名；
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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e4-answer-scope-' + [Guid]::NewGuid().ToString('N')))
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

同组 RED 还必须覆盖 continuation/narrow action strict union `extra=forbid`、完整不可信 envelope 跨 REST/SSE/frontend round-trip 字节等价、tampered/stale/oversize action 拒绝，以及 SSE 中断不提交 E4.1 的 StoryAnchorEvent。

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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e4-public-' + [Guid]::NewGuid().ToString('N')))
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

`scripts/evaluate_story_segment_rag.py` 必须提供两个显式子命令：

```text
performance-control  在同一 commit/host/process config/query set/timer 下运行
                     active v1 与 isolated typed v2；输出原始 timing 和
                     rag.story-segment-performance-control/v1
evaluate             消费 hash-pinned performance-control receipt、D0 baseline、
                     thresholds 和 candidate runtime snapshot；不得自行重测或重算对照
```

两个子命令都禁止独立 `--collection-name` / `--candidate-collection-name`；active/candidate collection 只能分别从已验证的 active-v1 和最终 v2 runtime snapshot 解析。Shadow build receipt 仅用于交叉验证 v2 snapshot 固定的 build receipt identity，不能覆盖 collection。

报告：

- structure/segment/typed row counts；
- Story Atom Dense removed count；
- predicted vector bytes；
- build peak RSS；
- local detector/finalizer/fusion/packer P50/P95；
- query embedding calls；
- context chars/segments/citations；
- no reranker。

RED/GREEN 必须覆盖 `performance-control` 子命令的参数闭包、`>=1` warmup、每 query `>=5` timed samples、原始样本/P50/P95、同机同提交校验，以及 `evaluate` 拒绝缺失、stale、不同 commit/host/query/config 的 receipt。

- [ ] **Step 5: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_eval.py `
  tests/test_rag_eval_deterministic.py `
  tests/test_rag_eval_scoring.py `
  tests/test_rag_eval_reporting.py `
  tests/test_rag_eval_runner.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e5-eval-' + [Guid]::NewGuid().ToString('N')))
```

- [ ] **Step 6: 停在 D review**

不提交 E5.1。D 接受后提交：

```text
test(rag): add story segment gate evaluator
```

### Task E5.2：生成质量标记反事实，不改变 runtime

**Spec coverage:** `QUALITY-P0-01` 至 `QUALITY-P0-07`、`EVAL-P0-01`、`EVAL-P0-02`、`GATE-P0-04`

**Files:**

- Modify: `src/rag_eval/story_segment_runner.py`
- Modify: `tests/test_story_segment_eval.py`
- No runtime ranking file change

- [ ] **Step 1: RED**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_eval.py::test_quality_counterfactual_does_not_change_runtime_bytes -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e5-quality-red-' + [Guid]::NewGuid().ToString('N')))
```

Expected: 断言失败，因为反事实报告和 runtime-byte identity 尚未实现；不能接受无测试、测试名错误或环境错误作为 RED。

- [ ] **Step 2: 实现只读反事实**

- 对同一候选模拟 soft penalty，仅报告排名变化。
- 单列 numeric、short text、exact entity/alias/ID、structured fields。
- 证明 P0 runtime 输出在启用/禁用反事实计算时逐字节相同。
- 证明 `context_only/deduplicate/invalid_source` 只来自结构契约，不来自质量分。

- [ ] **Step 3: GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_eval.py `
  tests/test_rag_eval_deterministic.py `
  tests/test_rag_eval_reporting.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e5-quality-green-' + [Guid]::NewGuid().ToString('N')))
```

- [ ] **Step 4: 停在 D review**

不提交 E5.2。D 接受后提交：

```text
test(rag): report story quality counterfactuals
```

### Task E5.3：完整回归、真实离线产物和不可变 handoff

**Spec coverage:** 全部 `FAILURE-*`、`PROVENANCE-*`、`PERF-*`、`THREAD-P0-04`、`THREAD-P0-05`、`REVIEW-P0-01` 至 `REVIEW-P0-18`

**Files:**

- Modify: `src/rag_eval/story_segment_runner.py`
- Create: `scripts/build_story_segment_candidate.py`
- Modify: `scripts/evaluate_story_segment_rag.py`
- Modify: `tests/test_story_segment_eval.py`
- Ignored output only: `eval/story_segment/handoffs/$RunId/`

- [ ] **Step 1: 写并见证 E5.3 RED**

只新增 handoff closure test，先运行：

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_eval.py::test_clean_head_handoff_closes_all_artifact_identities -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e5-handoff-red-' + [Guid]::NewGuid().ToString('N')))
```

Expected: 业务断言失败，因为 candidate-build-input producer、clean-head handoff emitter 和完整 identity closure 尚不存在。E 停在 `red_pending_d_witness`；D 按第 9 节独立见证并签发 RED acceptance 后才能继续。

- [ ] **Step 2: 实现离线 builder 与 handoff emitter**

实现 `scripts/build_story_segment_candidate.py` 和 evaluator/handoff contract。Producer 输出 structure、Segment、mapping、typed JSONL、`rag.story-candidate-build-input/v1`、hash-pinned deployment-inventory raw-byte copy、offline capacity estimate、quality counterfactual、offline gates 和 `rag.story-candidate-build-receipt/v1`；不输出最终 `rag.runtime-artifact-snapshot/v2`，不调用 embedding/Milvus/network。Deployment inventory 只能来自 D intake 的 hash-pinned exact schema，必须固定 remote host/key/storage devices、Milvus database/principal/allowed roles/allowed grant 五元组；Producer 不得补默认值、手写策略或从测试/observed RBAC 反推。Handoff emitter 支持测试中的 synthetic clean-head fixture，并在真实使用时强制 `e_commit == HEAD` 与 tracked tree clean。

- [ ] **Step 3: 定向 GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_eval.py::test_clean_head_handoff_closes_all_artifact_identities `
  tests/test_story_segment_eval.py::test_candidate_build_input_excludes_unbuilt_runtime_identity -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e5-handoff-green-' + [Guid]::NewGuid().ToString('N')))
```

- [ ] **Step 4: 全量 E focused regression**

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
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-e5-focused-' + [Guid]::NewGuid().ToString('N')))
```

- [ ] **Step 5: 相邻回归**

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

- [ ] **Step 6: deterministic fixture 与真实恢复快照 build x2**

两个 create-new roots 比较：

- structure/segment/typed bytes；
- IDs/order hashes；
- schema/config/provenance；
- source maps/context units；
- fake retrieval and AnswerScope bytes。

随后用完整恢复快照在两个 create-new root 运行同一 producer。`candidate-build-input.v1.json` 必须固定 typed input path/SHA、expected collection schema、schema/config identities、row/order hashes、C/D0 receipts 和离线容量估算；禁止 actual collection/observed rows/build receipt。除 run ID/timestamp/absolute output root 等显式非身份字段外，两份业务身份必须一致。缺任一 artifact/hash 时 fail-closed，不能留下 `ready_for_d_shadow_build=true`。

- [ ] **Step 7: protected pre/post**

要求 active pointer、active collection inventory、source snapshot、BM25、MinIO/MySQL/config 全部零漂移。

- [ ] **Step 8: D 审查 E5.3 tracked diff**

不创建 Milvus，不调用 embedding，不激活。D 独立复跑 E5.3 测试、真实离线 build 和 protected-state 检查；此时只审查 tracked 代码，尚不生成最终 handoff。

- [ ] **Step 9: 提交 E5.3 并冻结 clean HEAD**

```text
test(rag): produce story segment offline handoff
```

提交后要求：

```text
git status --short --untracked-files=no == empty
e_commit == git rev-parse HEAD
no further tracked mutation
```

- [ ] **Step 10: 从 clean HEAD 生成不可变 handoff**

不得复用 Step 6 的 pre-commit run。必须从刚提交的 clean HEAD 在第三个 create-new root 重新运行 producer；其 canonical 业务身份必须与 D 已接受的 pre-commit build x2 一致，而 code identity 必须等于当前 `e_commit`。再按 D Plan 1.3 写完整文件并计算 handoff 自身 SHA-256。`e_commit` 必须是刚提交的 E5.3 clean HEAD；artifact/candidate-build-input/test receipt 的代码身份都必须包含该提交。`ready_for_d_shadow_build` 仅在所有不依赖真实 embedding 的 hard gate 通过且 remaining blockers 为空时为 true。

- [ ] **Step 11: D 验证并接收 handoff**

D 重新计算 handoff、artifact、candidate-build-input 和测试 receipt 哈希，确认 E HEAD 仍等于 `e_commit` 且无后续 tracked 改动。真实 handoff 输出不提交；D 将其复制到 D-owned create-new intake 目录并生成 intake receipt。任何差异都废弃本次 handoff，不能在 JSON 中手改提交号。

---

## 9. 每 Task RED/GREEN、真实证据与退出回执

E0.0 是不提交的 preflight。其余 16 个 implementation Task 必须使用下表中精确 test node 建立 RED，再运行该 Task 正文列出的 GREEN suite；缺 test node、收集错误、解释器错误、权限错误和临时目录错误都不算 RED。

标准 RED 命令：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $TaskId,
  [Parameter(Mandatory = $true)]
  [string[]] $RedTargets
)

$RedBase = Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-' + $TaskId.Replace('.','-') + '-red-' + [Guid]::NewGuid().ToString('N'))
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest @RedTargets -q --basetemp $RedBase
```

每个 `approved-task.md` 必须把 `$TaskId/$RedTargets` 固定为下表中的字面值。E 写完 RED test 后立即停止；D 必须在任何实现写入前按 D Plan D1 复跑相同 argv 并签发 `rag.story-segment-red-acceptance/v1`。执行 receipt 记录完整 argv，不能遗漏第二个 target。

| Task | RED target | 预期业务失败 | GREEN suite | 真实证据 |
|---|---|---|---|---|
| E0.1 | `tests/test_story_structure.py::test_parses_story_taxonomy_and_exact_registry` | parser/registry contract 尚不存在 | E0.1 Step 5 | `not_applicable`：只验证 parser fixture；E0.2 负责真实快照 |
| E0.2 | `tests/test_story_structure.py::test_real_snapshot_structure_artifact_closes_over_every_atom` | sidecar/artifact/closure 尚不存在 | E0.2 Step 5 | required：完整恢复快照 structure/registry/Atom closure |
| E1.1 | `tests/test_story_segments.py::test_real_story_atoms_map_to_deterministic_segments` | Segment builder 尚不存在 | E1.1 Step 5 | required：真实 Atom 长度、boundary、oversize、graph |
| E1.2 | `tests/test_story_context_units.py::test_real_segments_render_once_with_atom_spans` | ContextUnit/span mapping 尚不存在 | E1.2 Step 5 | required：真实 Segment/Atom 双预算与引用闭包 |
| E2.1 | `tests/test_dense_retrieval_units.py::test_real_candidate_publishes_typed_units_and_candidate_build_input` | typed artifact/candidate-build-input 尚不存在 | E2.1 Step 4 | required：真实 candidate typed rows/build-input tuple |
| E2.2 | `tests/test_huiji_typed_shadow_builder.py::test_storage_and_milvus_preflight_precede_external_writes`；`tests/test_huiji_typed_shadow_builder.py::test_fake_build_publishes_active_control_snapshot_without_pointer_drift` | typed adapter/query-by-vector/三段 gate/active control snapshot 尚不存在 | E2.2 Step 4 | required：真实 typed artifact + fake SSH/embedding/Milvus，未授权外部写 0 |
| E3.1 | `tests/test_story_request_plan_v2.py::test_finalizes_composite_request_once_with_exact_spans` | v2 transaction/finalizer 尚不存在 | E3.1 Step 4 | `not_applicable`：纯 request corpus；receipt 固定 query corpus hash |
| E3.2 | `tests/test_story_authorization.py::test_authorizes_direct_and_open_story_domains_fail_closed` | detector/context/open domain 尚不存在 | E3.2 Step 5 | required：真实 registry + 冻结正负 query corpus |
| E3.3 | `tests/test_story_authorization.py::test_continuation_and_anchor_projection_are_deterministic` | continuation verifier/anchor reducer 尚不存在 | E3.3 Step 5 | `not_applicable`：纯 action/clock/turn fixtures，固定 registry identity |
| E3.4 | `tests/test_story_retrieval_fusion.py::test_real_atom_and_segment_channels_fuse_with_one_query_embedding`；`tests/test_retriever.py::test_open_story_domain_consumes_only_authorized_canonical_filter` | fusion/budget/query reuse/open-domain consumption 尚不存在 | E3.4 Step 7 | required：真实 Atom/Segment candidate + fake vector ranks |
| E4.1 | `tests/test_story_segment_runtime.py::test_runtime_v2_commits_turn_and_anchor_atomically` | unified ContextUnit execution/atomic event 尚不存在 | E4.1 Step 3 | required：isolated v2 snapshot + fake generator/vector |
| E4.2 | `tests/test_story_answer_scope.py::test_real_evidence_packet_normalizes_scope_without_overclaim` | scope v2/姿态尚不存在 | E4.2 Step 4 | required：真实候选产生的 bounded evidence packets |
| E4.3 | `tests/test_story_segment_public_contracts.py::test_rest_sse_and_internal_outcome_are_identical` | unique source/public projection 尚不存在 | E4.3 Step 5 | required：isolated v2 REST/SSE query corpus |
| E5.1 | `tests/test_story_segment_eval.py::test_reports_every_hard_gate_with_denominator`；`tests/test_story_segment_eval.py::test_performance_control_produces_hash_pinned_receipt` | evaluator/gates/performance producer 尚不存在 | E5.1 Step 5 | required：完整离线 candidate + D0 gold/baseline |
| E5.2 | `tests/test_story_segment_eval.py::test_quality_counterfactual_does_not_change_runtime_bytes` | counterfactual/runtime identity 尚不存在 | E5.2 Step 3 | required：与 E5.1 同一 candidate identity |
| E5.3 | `tests/test_story_segment_eval.py::test_clean_head_handoff_closes_all_artifact_identities` | candidate producer/clean-head handoff closure 尚不存在 | E5.3 Step 3 | required：完整恢复快照 build x2、protected pre/post |

每个 Task 在 D review 前写 create-new ignored receipt：

```text
eval/story_segment/task-receipts/<run-id>/<task-id>.v1.json
eval/story_segment/task-receipts/<run-id>/<task-id>.v1.sha256
eval/story_segment/task-receipts/<run-id>/<task-id>.red-acceptance.v1.json
eval/story_segment/task-receipts/<run-id>/<task-id>.red-acceptance.v1.sha256
```

RED acceptance 由 D 写入，E 只能只读消费其路径和期望 SHA-256；E 不得生成、覆盖或修订该文件。

Receipt schema 至少包含：

```json
{
  "schema_version": "rag.story-segment-task-receipt/v1",
  "task_id": "E0.1",
  "base_commit": "40-hex",
  "red_tree_identity": {
    "manifest_path": "",
    "manifest_sha256": "64-hex",
    "identity_sha256": "64-hex"
  },
  "red_log_sha256": "64-hex",
  "d_red_acceptance": {"path": "", "sha256": "64-hex"},
  "red": {"argv": [], "expected_failure": "", "observed_failure": "", "passed_gate": true},
  "green_tree_identity": {
    "manifest_path": "",
    "manifest_sha256": "64-hex",
    "identity_sha256": "64-hex"
  },
  "green_log_sha256": "64-hex",
  "green": {"argv": [], "exit_code": 0, "passed": 0, "failed": 0, "skipped": 0},
  "real_evidence": {
    "status": "required",
    "reason": "",
    "input_identity": {},
    "output_sha256": "64-hex"
  },
  "protected_drift_count": 0,
  "forbidden_operation_counts": {},
  "allowed_files": [],
  "observed_changed_files": []
}
```

两个 tree identity 都使用 D0.1 的 `codex.allowed-tree-identity/v1` 算法，并计入 allowlist 内所有未跟踪文件。`d_red_acceptance` 必须绑定同一 base、`red_tree_identity`、E RED log 和 D 独立 RED log；实现开始后不得补签。`real_evidence.status` 只能为 `required` 或 `not_applicable`；`not_applicable` 必须与表中理由完全相同。D 独立验证 receipt、实际日志、diff 和 OS/产物状态后才允许提交。

---

## 10. E Task 提交与监督协议

E0.0 只生成 preflight receipt。下列 16 个 implementation Task 都是独立 D review gate；前一提交被 D 接受前不得开始后一 Task。提交边界：

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

## 11. 完整 Spec 追踪矩阵

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

## 12. E 完成标准

1. C release receipt 已复验：C8b–C9 已合并，Story Parent/Atom/source refs 来自固定 `main` artifact，E 不读取 C worktree。
2. 每个规范 Story Atom 恰好一条 structure sidecar；显式图闭合、source-order 明确、invalid graph 阻断。
3. 纯数字、短文本、内部 ID 和歧义 alias 按统一 registry 规则处理，无逐实体补丁。
4. 每个 Atom 在一个 Segment 版本中恰好一次；Atom parent/ID/content/source 不变。
5. oversize Atom 形成单 Atom Segment，Dense limit fail-closed，不截断。
6. Segment 两次构建字节一致，prev/next/branch/merge 闭合。
7. Segment 正文一次封装；每个非空 Atom 一个 span 和 citation source。
8. Story Atom 仍在 BM25，typed Dense 输入中 Story Atom 数为 0。
9. 非 Story Child 和 Story Segment 使用显式 typed IDs/fields；`segment_sequence_index`/sentinel 契约精确，Segment 不冒充 Child。
10. `rag.story-candidate-build-input/v1` 与写后 `rag.runtime-artifact-snapshot/v2` 身份分离；fake builder 证明最终 v2 只能在 actual collection/schema/rows/build receipt 齐全后解析，active v1 行为不变。
11. RequestPlan v2 只运行一次 Detector 和至多一次本地 fallback；所有 Story occurrence 唯一归属。
12. Direct、continuation、anchor 三来源共享一个授权上下文和 Retriever 入口；open Story domain 只消费已授权 character/Topic filter。
13. 1–3 Story 获准且全覆盖；4–32 可分页且每页可达 authorized；33+ narrowing；无 Composite 比较。
14. 原 Owner Gate 未放宽，角色/Topic Story 补充分支只消费授权 allowlist/关系。
15. 融合公式、排序、Owner 配额和五类预算完全确定；Topic/Page 不被 Story 淹没；同一 query vector 跨 Child/Segment 复用。
16. 有可提交证据的 shortfall 输出非空 grounded answer；授权边界、failed、empty 不混淆。
17. AnswerScope 只在适用 Story 分支存在；不新增模型调用。
18. 请求级唯一 retrieval outcome 来自 `ResponsePacket.retrieval_packet.route_decision.retrieval_outcome`；REST/SSE 一致。
19. Reranker 调用为 0；质量反事实不改变 runtime。
20. 16 个 implementation Task 均有 D 在实现前见证的 RED acceptance、独立 RED/GREEN tree/log 和真实证据 receipt；全部 focused/adjacent tests 通过，真实离线 snapshot protected drift 为 0。
21. E handoff 在 E5.3 clean commit 后生成，包含 candidate-build-input 与离线容量估算，不包含未构建的 v2 runtime snapshot；`ready_for_d_shadow_build` 的含义仅为可交 D。
22. E 未调用 embedding、未写 Milvus、未激活；后续真实向量重建只由 D 执行。
