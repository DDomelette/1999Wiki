# 线程 A：路由、主题消费与复合问题编排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the existing Thread A Codex CLI session. Do not use `superpowers:subagent-driven-development`; this thread explicitly forbids subagents, additional Codex CLI workers, and third-layer delegation. Every checkbox is an inline-session checkpoint for D review.

**Goal:** 在默认禁止数据库外自由补充的前提下，建立顶层任务分类与授权、无单一角色 Owner 的 Topic/Story 检索、安全复合问题编排、全局引用、mixed packet、会话记忆及 REST/SSE 一致语义。

**Architecture:** 新增独立 `RequestPlan` 层，先将请求分类为一个或多个有序 subtask，再由 Route Policy 逐分支授权；只有 `knowledge_base` 分支创建现有 `QueryPlan` 并进入 Retriever。执行服务按“规划与授权 → 全部分支检索 → 全局 source map → 分支回答与验证 → 确定性聚合 → packet 冻结与记忆提交”推进，保留现有 Owner Gate、引用 repair/safe fallback、媒体、Voice pagination 和旧顶层响应字段。

**Tech Stack:** Conda `1999wiki` 中的 Python 3.11.15（`D:\Anaconda32024\envs\1999wiki\python.exe`，`sys.prefix=D:\Anaconda32024\envs\1999wiki`）、dataclasses、Pydantic v2、FastAPI、SSE、LangChain message contracts、pytest 9.1.1、现有 Huiji v3 child artifact 接口。

## Global Constraints

- 设计源头：`docs/superpowers/specs/2026-07-29-rag-thread-a-routing-design.md`，批准 commit `ed569ee23f5d3927f8a332e69ef4de82ac8b6c59`。
- 监督源头：`docs/superpowers/specs/2026-07-29-rag-cli-supervision-design.md` 与 `docs/superpowers/plans/2026-07-29-rag-cli-supervision.md`。
- A1 → A2 → A3 → A4 → A5 严格串行；每阶段完成对应测试并由 D 审查后才进入下一阶段。
- 使用原 Thread A 长期 Codex CLI session、`gpt-5.6-sol`、standard speed、`workspace-write`；`fast_mode=false`、`multi_agent=false`。
- A1–A5 每阶段开始前必须运行第 3.0 节 Conda `1999wiki` fail-closed 门禁；解释器必须是 `D:\Anaconda32024\envs\1999wiki\python.exe`，且 `sys.prefix` 必须是 `D:\Anaconda32024\envs\1999wiki`、版本必须是 `3.11.15`。任一不符立即停止，不运行测试或实现，并向 D 报告。
- 所有 Python/pytest 命令必须通过上述绝对解释器路径执行；不得使用裸 `python`、裸 `pytest`，也不得假设当前 PATH 或已激活 shell 恰好指向 Conda `1999wiki`。
- 禁止子代理、再次调用 Codex CLI、读取 B/C 未合并 worktree、跨 worktree 复制代码或导入类型。
- Planner 提议与 Route Policy 授权严格分离：Planner 只提议 task type/route；Route Policy 是数据库外通用回答的唯一授权者。
- 默认 `free_supplement=false`；Planner 单独输出 `general_open`/`llm_general` 不得授权通用 LLM。
- `expanded=true && free_supplement=true` 的 P0 语义是 expanded retrieval 后仅在精确 `empty` 时自由补充；`partial` 和 `failed` 不自动 Hybrid。
- P0 禁止自动并行 expanded RAG + 通用 LLM、自动 grounded/ungrounded mixed 事实回答或 LLM 全文聚合重写。
- A 只消费冻结字段 `category/entity_type/entity_id/entity_name/entity_aliases/owner_entity_id/owner_page_id/route_tags/parent_id/child_id/heading_path/section_kind/content/search_text/source_refs`。
- Topic/Story 开发只使用本线程 fixture；真实 A/C 联调由 D 在 C 合并后执行。
- 不修改 `src/rag/sparse.py`、Analyzer/词典/BM25 schema、projection/media builder、Wikitext parser、resource downloader、raw snapshot、正式候选、active pointer 或生产数据。
- 不执行抓取、下载、上传、Milvus/MySQL/MinIO 写入、正式构建或生产激活。
- 每个实现阶段采用 TDD：先加入红灯并验证预期失败，再写最小实现，先跑定向测试后跑阶段回归。
- 每次提交前运行 `git diff --check`、所有阶段测试和 `git status --short`；只暂存该阶段列出的实现与测试文件。

---

## 1. 文件结构与职责

### 1.1 新建

| 文件 | 单一职责 |
|---|---|
| `src/rag/request_plan.py` | 顶层 task type、retrieval scope、RequestPlan/PlannedSubtask schema、严格验证、LLM/fallback 分类与安全拆分 |
| `src/rag/local_responses.py` | assistant meta、小聊、general denied、out-of-scope 和模板失败的受控本地回答 |
| `tests/fixtures/rag_thread_a/topic_story_children.json` | 仅由 A 使用、遵循冻结公共字段的最小 Topic/Story/Page child fixture |
| `tests/test_request_plan.py` | task 分类、fallback、拆分边界、schema、最多 4 分支和不泄露 planner payload |
| `tests/test_local_responses.py` | 确定性身份、小聊、能力边界、无 LLM 依赖及无引用/媒体 |
| `tests/test_rag_topic_scope.py` | `none/entity_strict/topic_strict/corpus_topic`、fixture 消费、Owner Gate 与 sparse segments |
| `tests/test_rag_composite_execution.py` | 有界并发、失败隔离、ordered aggregation、动作 subtask 绑定和顶层 outcome |
| `tests/test_rag_global_citations.py` | 全局来源去重、collision、分支 source subset、重编号与顶层验证 |

### 1.2 修改

| 文件 | 修改职责 |
|---|---|
| `src/rag/query_plan.py` | 只保留 KB 内部实体/intent/query rewrite；增加显式 retrieval scope 与确定 sparse segments |
| `src/rag/route_policy.py` | 按 subtask 授权 local/KB/general/denied；冻结双开关矩阵和 route reasons |
| `src/rag/contracts.py` | 增加 BranchResult、SubtaskInfo、`not_applicable`、`local_response/composite`、`mixed/local` 和 v3 packet |
| `src/rag/execution.py` | 实现 A1-A4 统一执行流水线、分支并发、全局引用、聚合和完整 packet 后记忆候选 |
| `src/rag/chain.py` | 接入 RequestPlanner；拆分 KB branch retrieval/answer helpers；保留单任务兼容入口 |
| `src/rag/retriever.py` | 消费 retrieval scope；实现 topic/corpus 候选约束、扩大范围和稳定 sparse segments |
| `src/rag/packet_policy.py` | 为 topic/story/page 提供非角色默认 policy |
| `src/rag/conversation.py` | 支持 local/mixed turn 历史投影，按唯一 grounded entity 决定锚点 |
| `src/rag/citations.py` | 构建整轮全局 source map、identity collision 检测、分支引用子集与顶层验证 |
| `src/rag/serializers.py` | 公开 v3 顶层兼容字段和严格 `subtasks[]`；action 透传 `subtask_id` |
| `backend/schemas.py` | 扩展公开 enum、SubtaskInfo、ActionItem、timing 与 sanitizer allowlist |
| `backend/sse.py` | 复用同一冻结 packet；保持 `sources → zero-or-more token → done`；done 后才提交记忆 |
| `backend/main.py` | 同步 `/ask` 复用同一执行服务和提交 helper，不复制 planning/execution |
| 现有对应测试 | 保留既有 fixture 风格并增加回归断言 |

### 1.3 冻结接口

```text
# src/rag/request_plan.py public signatures
TaskType = Literal[
    "assistant_meta",
    "social_smalltalk",
    "knowledge_base",
    "general_open",
    "out_of_scope",
]
RetrievalScope = Literal["none", "entity_strict", "topic_strict", "corpus_topic"]
AggregationMode = Literal["ordered_sections"]

@dataclass(frozen=True)
class PlannedSubtask:
    subtask_id: str
    order: int
    task_type: TaskType
    query: str
    query_plan: QueryPlan | None
    depends_on: tuple[str, ...] = ()

@dataclass(frozen=True)
class RequestPlan:
    original_query: str
    subtasks: tuple[PlannedSubtask, ...]
    aggregation_mode: AggregationMode = "ordered_sections"
    planning_status: str = "llm"
    planning_warning: str = ""
    planning_error: str = ""
    schema_version: str = "rag.request_plan/v1"

class RequestPlanner:
    plan(self, query: str, *, category: str | None = None,
         conversation: ConversationProjection = EMPTY_PROJECTION,
         trace: RequestTrace | NullTrace | None = None) -> RequestPlan

validate_request_plan(plan: RequestPlan) -> RequestPlan
```

```text
# src/rag/route_policy.py public signatures
authorize_subtask(subtask: PlannedSubtask,
                  route_options: Mapping[str, object] | None,
                  action_payload: Mapping[str, object] | None) -> RouteAuthorization

finalize_subtask_route(authorization: RouteAuthorization,
                       outcome: RetrievalOutcome) -> RouteDecision
```

```text
# src/rag/citations.py public signatures
@dataclass(frozen=True)
class GlobalSourceAllocation:
    sources: tuple[Mapping[str, object], ...]
    source_map: tuple[SourceRef, ...]
    branch_source_ids: Mapping[str, tuple[str, ...]]

build_global_source_map(
    ordered_branch_sources: Sequence[tuple[str, Sequence[Mapping[str, Any]]]]
) -> GlobalSourceAllocation

validate_global_citations(branches: Sequence[BranchResult],
                          source_map: Sequence[SourceRef],
                          answer: str) -> CitationValidation
```

```text
# src/rag/execution.py public signature
class RAGExecutionService:
    execute(self, request: AskExecutionInput,
            conversation: ConversationProjection = EMPTY_PROJECTION,
            trace: RequestTrace | NullTrace | None = None) -> ResponsePacket
```

`RAGExecutionService.execute()` 是 `/ask`、`/ask/stream` 和 `RAGChain.ask()` 的唯一业务执行入口；serializer 和 SSE 只能读取冻结 packet，不得再次规划、检索或生成。

---

## 2. 完整 P0 追踪矩阵

每一行均给出实施 Task、主要验证和强制失败表现；详细红灯、实现与命令见第 3 节。

| Spec | Task / 验证 | 失败表现 |
|---|---|---|
| `ARCH-P0-01` | A1：RequestPlanner 在 QueryPlanner 前；`test_request_planner_only_builds_query_plan_for_kb` | 非 KB 创建 QueryPlan 或调用 Retriever 时红灯 |
| `ARCH-P0-02` | A1：`authorize_subtask()` 独立授权；planner `llm_general` 对默认请求被拒 | Planner 直接授权通用 LLM 时红灯 |
| `ARCH-P0-03` | A1：单任务也产生一个 `T01` | 出现旁路单任务执行语义时红灯 |
| `ARCH-P0-04` | A3/A4：并发分支、按 order 分配 source/answer/memory | 重复运行字段顺序或编号变化时红灯 |
| `ARCH-P0-05` | A1/A3：1..4、无 nested composite、超限安全降级 | 第 5 个 subtask 被执行或递归规划时红灯 |
| `TASK-P0-01` | A1：assistant_meta 本地回答且 Retriever/LLM spy 为 0 | “你是谁”触发检索或开放 LLM 时红灯 |
| `TASK-P0-02` | A1：smalltalk 非人类模板 | 声称吃饭、睡觉、身体或现实经历时红灯 |
| `TASK-P0-03` | A1/A2：KB task 保留知识 intent | 顶层 task type 覆盖 `intro/skill/story/general_game` 时红灯 |
| `TASK-P0-04` | A1：general_open 只提议、默认 denied | 默认调用通用 LLM 时红灯 |
| `TASK-P0-05` | A1：out_of_scope 确定性边界 | 进入 Retriever/LLM 或暴露内部错误时红灯 |
| `TASK-P0-06` | A1：五条基准参数化分类 | 任一基准 task type/默认行为漂移时红灯 |
| `TASK-P0-07` | A1：`meta_question→assistant_meta`、`general_game→knowledge_base` | 兼容 intent 丢失或替代 KB intent 时红灯 |
| `TASK-P0-08` | A1：no LLM/timeout/parse/schema/api fallback | fallback 不能识别 meta、小聊、明显 KB 时红灯 |
| `TASK-P0-09` | A1：固定三段 fallback；指代/因果/比较不拆 | Planner 不可用时三段缺失，或依赖问题被拆时红灯 |
| `AUTH-P0-01` | A1：local task 使用 `local_response` | local 被伪装为 rag/general 时红灯 |
| `AUTH-P0-02` | A1：general 仅 toggle 或精确 recovery action 授权 | 无授权 general 调用 LLM 时红灯 |
| `AUTH-P0-03` | A1：Planner proposal 不授予权限 | 先空检索再“未检测到实体”时红灯 |
| `AUTH-P0-04` | A1：KB free toggle 仅 after-empty | sufficient/partial 时调用 general 时红灯 |
| `AUTH-P0-05` | A1：4×4 dual-toggle/outcome 参数化矩阵 | route/scope/shortfall 任一格不符时红灯 |
| `AUTH-P0-06` | A1：双开关先 expanded，一次检索，仅 empty fallback | partial/failed 自动 Hybrid 时红灯 |
| `AUTH-P0-07` | A1：force action 跳过检索且 reason 独立 | force 与 toggle reason 混淆时红灯 |
| `AUTH-P0-08` | A3：授权严格按 `subtask_id` | local/某 KB 授权扩散到其他分支时红灯 |
| `AUTH-P0-09` | A1/A3：冻结 route reason enum | serializer/schema 拒绝或静默丢 reason 时红灯 |
| `AUTH-P0-10` | A1：所有模板集中在 `local_responses.py` | prompt/API/异常分支出现重复身份模板时静态红灯 |
| `PLAN-P0-01` | A1：`T01..T04`、order 1..N | 重复/跳号 ID 或 order 时 schema 红灯 |
| `PLAN-P0-02` | A1：只有 KB 有 QueryPlan | 非 KB 携带 query_plan 时 ValueError |
| `PLAN-P0-03` | A1：depends_on 仅早期节点 | 后向引用/环/未知 ID 时 ValueError |
| `PLAN-P0-04` | A1/A3：固定 ordered_sections，无聚合 LLM | 聚合器调用 LLM 或改写分支时红灯 |
| `PLAN-P0-05` | A1：严格 schema 参数化非法样例 | 任一非法 plan 被接受时红灯 |
| `PLAN-P0-06` | A1/A4：公开 payload sanitizer 测试 | prompt/raw payload/异常/路径出现在 REST/SSE 时红灯 |
| `PLAN-P0-07` | A1：显式 `rag.request_plan/v1` | 版本缺失/猜测字段版本时红灯 |
| `COMPOSITE-P0-01` | A1：只拆独立无共享指代并列问题 | 语义耦合问题被拆时红灯 |
| `COMPOSITE-P0-02` | A1：指代/因果、比较、反事实保留单 KB | 任一基准被拆成多个 subtask 时红灯 |
| `COMPOSITE-P0-03` | A1：标点/“然后”不足以拆分 | 仅凭标点拆分时红灯 |
| `COMPOSITE-P0-04` | A3：有界 executor `max_workers=4` 与 topo batch | 超过 4 个活动分支或依赖提前运行时红灯 |
| `COMPOSITE-P0-05` | A3：`succeeded/empty/denied/failed` | 单分支异常终止整轮时红灯 |
| `COMPOSITE-P0-06` | A3：按 order 的确定性段落分隔 | 回答乱序、重复或 LLM 重写时红灯 |
| `COMPOSITE-P0-07` | A3/A4：至少一成功即提交；全失败 not_committable | 成功分支被吞或全失败被提交时红灯 |
| `SCOPE-P0-01` | A1/A2：非 KB scope `none` 且 Retriever 0 次 | local/general/out-of-scope 检索时红灯 |
| `SCOPE-P0-02` | A2：entity_strict 全阶段 Owner Gate | foreign/missing owner 进入 packet 时红灯 |
| `SCOPE-P0-03` | A2：已解析 topic/story/page 使用 topic_strict | 其他 topic owner 混入时红灯 |
| `SCOPE-P0-04` | A2：corpus_topic 受类型/tag/定义性/多样性约束 | 全语料解禁或伪装单一 Owner 时红灯 |
| `SCOPE-P0-05` | A2：角色 Owner Gate 回归 | 角色查询接受 owner mismatch 时红灯 |
| `SCOPE-P0-06` | A2：“暴雨是什么”使用 topic/corpus scope | 无角色实体直接 empty 时红灯 |
| `SCOPE-P0-07` | A2：十四行诗技能保持 entity_strict | 其他角色资料进入 packet 时红灯 |
| `SCOPE-P0-08` | A2：仅 A fixture；静态路径审计 | 测试/实现引用 B/C worktree 路径时红灯 |
| `SCOPE-P0-09` | A2：topic/story/page policy 与候选类型约束 | 对所有 character child 取消过滤时红灯 |
| `QUERY-P0-01` | A1/A2：task 分类在 KB QueryPlan 前 | 非 KB 调 QueryPlanner 或重写顺序逆转时红灯 |
| `QUERY-P0-02` | A2：不改 `sparse.py`，Analyzer 只在 sparse 内 | A 实现分词/词典时 diff gate 失败 |
| `QUERY-P0-03` | A2：五类 sparse segments | 任一 segment 缺失时红灯 |
| `QUERY-P0-04` | A2：稳定去空去重 | 重复实体词或输入顺序导致输出漂移时红灯 |
| `QUERY-P0-05` | A2/A5：现接口 fixture，D 负责真实 B 接线 | A 修改 Analyzer/schema/legacy loader 时文件门禁失败 |
| `TOPIC-P0-01` | A2：fixture/实现不含 `owner_type` | 新私有 owner 字段出现时静态红灯 |
| `TOPIC-P0-02` | A2：六种 entity_type 兼容参数化测试 | story/topic/page 被 schema/filter 丢弃时红灯 |
| `TOPIC-P0-03` | A2：identity 使用 type+id/parent/child | 按自然标题合并稳定身份时 collision 红灯 |
| `TOPIC-P0-04` | A2：unresolved 保留内部 ID 与诊断 | 自猜自然标题时红灯 |
| `TOPIC-P0-05` | A2/A3：invalid source/alias/ref 不进入 grounded map | 缺 source ref 的 fixture 成为引用时红灯 |
| `TOPIC-P0-06` | A2/A5：不 import C 类型/函数/路径 | A fixture 测试依赖 C 实现时静态红灯 |
| `CITE-P0-01` | A3：整轮一个 GlobalSourceAllocation | 每分支独立从 S01 编号时红灯 |
| `CITE-P0-02` | A3：order/rank 去重与 stable identity collision | 顺序漂移或不同 hash 静默合并时红灯 |
| `CITE-P0-03` | A3：branch_source_ids 白名单 | 分支引用其他分支 source 时红灯 |
| `CITE-P0-04` | A3：retrieve-all→allocate→answer→validate→aggregate | answer 在全局分配前生成时 spy 红灯 |
| `CITE-P0-05` | A3：local/denied/general strip citation tokens | 非 grounded 分支公开 `[Snn]` 时红灯 |
| `CITE-P0-06` | A3：顶层全局验证五项断言 | 重复/未知 ID、grounded 无引用时红灯 |
| `CITE-P0-07` | A4/A5：历史 citation 继续失效化 | 旧 `[Snn]` 进入当前 prompt 时红灯 |
| `PACKET-P0-01` | A3/A4：BranchResult 内部 answer/error 不直接序列化 | traceback/raw branch answer 泄露时红灯 |
| `PACKET-P0-02` | A4：v3 packet 且保留全部旧顶层字段 | schema 版本或兼容字段缺失时红灯 |
| `PACKET-P0-03` | A4：SubtaskInfo 精确 9 字段 | 多字段泄露或安全字段丢失时红灯 |
| `PACKET-P0-04` | A4：单分支真实 route，多分支 composite | route enum 不一致或 composite 未公开时红灯 |
| `PACKET-P0-05` | A4：contracts→serializer→Pydantic→sanitizer→REST→SSE | 任一层静默丢 enum/字段时红灯 |
| `PACKET-P0-06` | A1/A4：未检索为 `not_applicable` | local/general/denied 被标 `empty` 时红灯 |
| `PACKET-P0-07` | A4：只汇总 KB outcome 的五组参数化测试 | local 分支影响 retrieval outcome 时红灯 |
| `GROUND-P0-01` | A4：GroundingMode/AskResponse 增加 mixed | mixed packet 被 schema 拒绝时红灯 |
| `GROUND-P0-02` | A4：TurnOutcome 增加 mixed/local | local/mixed 被 not_committable 时红灯 |
| `GROUND-P0-03` | A3/A4：mixed 仍逐 grounded branch 验证 | mixed 跳过 citation validation 时红灯 |
| `GROUND-P0-04` | A1/A4：general denied 是 local/none | denied 被标 ungrounded 时红灯 |
| `GROUND-P0-05` | A3/A4：成功组合决定 outcome，失败仅摘要 | 部分失败导致 not_committable 时红灯 |
| `LOCAL-P0-01` | A1：受控助手身份文本 | 未说明项目助手/KB 主要能力时红灯 |
| `LOCAL-P0-02` | A1：非人类小聊基准 | 人类经历声明时红灯 |
| `LOCAL-P0-03` | A1：general denied 边界与可选操作 | 出现“实体识别失败/数据库为空”时红灯 |
| `LOCAL-P0-04` | A1：LLM 未配置仍可 local | no API key 返回配置错误时红灯 |
| `LOCAL-P0-05` | A1/A3：local 无事实引用、sources/assets/media | local 携带任一知识附件时红灯 |
| `LOCAL-P0-06` | A1：语言选择受控，事实统一配置 | Planner 生成身份事实时红灯 |
| `MEMORY-P0-01` | A4：non-KB 不创建实体锚点 | local/general/out-of-scope 写 anchor 时红灯 |
| `MEMORY-P0-02` | A4：单 grounded+valid KB 可写 anchor | 无效引用或非 grounded 写 anchor 时红灯 |
| `MEMORY-P0-03` | A4：local+唯一 grounded entity 写 anchor | 后续“她”不能继承唯一实体时红灯 |
| `MEMORY-P0-04` | A4：多实体 composite 不写 anchor | 任一实体被任意选中时红灯 |
| `MEMORY-P0-05` | A4：topic/corpus/invalid/empty/denied/failed 不写角色 anchor | Topic 或失败分支污染角色锚点时红灯 |
| `MEMORY-P0-06` | A4：local/mixed 可进历史并保留 outcome | 历史丢 outcome 或旧 citation 未失效时红灯 |
| `MEMORY-P0-07` | A4：packet 冻结和 done 后提交 | SSE 断开/中途失败提交半成品时红灯 |
| `API-P0-01` | A4：REST/SSE 都调用 `chain.execute` 一次 | handler 自行 planning/branch execution 时红灯 |
| `API-P0-02` | A4：sources→token→done；sources 含 subtasks/meta | 顺序、answer 分流或元数据缺失时红灯 |
| `API-P0-03` | A4：branch failure 进入 subtask，不发 error | 有成功分支却发送顶层 error 时红灯 |
| `API-P0-04` | A4：严格 SubtaskInfo 与扩展 enum | OpenAPI/Pydantic 契约缺失时红灯 |
| `API-P0-05` | A4：新字段 allowlist 与敏感字段 denylist | prompt/content/plan/auth/path 泄露时红灯 |
| `API-P0-06` | A4：planning/retrieval/answer/aggregation timing | 总阶段缺失或 raw trace 泄露时红灯 |
| `API-P0-07` | A4/A5：旧顶层 answer/sources/media/route 保留 | 旧客户端依赖字段被删/改名时红灯 |
| `EXEC-P0-01` | A3：检索/生成有界并发 4 | Planner 输出创建无限任务时红灯 |
| `EXEC-P0-02` | A3：分支异常转安全 BranchResult | traceback/exception object 出现在 wire 时红灯 |
| `EXEC-P0-03` | A1/A3：empty/denied/local fallback 文案分离 | 三种失败混成实体错误时红灯 |
| `EXEC-P0-04` | A3：冻结 BranchResult 后只读聚合 | 聚合器修改文本/citation token 时红灯 |
| `EXEC-P0-05` | A3：媒体/actions 仅 KB，按 order 去重 | local/general 制造媒体/action 时红灯 |
| `EXEC-P0-06` | A3/A4：恢复 action 精确绑定 subtask | 一个 action 改写全轮 route 时红灯 |
| `EXEC-P0-07` | A3/A4：ActionItem `subtask_id` 验证与回传 | composite 缺失/伪造 ID 被接受时红灯 |
| `OWN-P0-01` | A5：文件列表与 diff 审计 | 修改 B/C 文件或公共字段冲突时停止并 needs_approval |
| `OWN-P0-02` | A2/A5：A 只接 sparse segments，不改 Analyzer | `retriever.py` 接线越过接口时 diff gate 失败 |
| `AGENT-P0-01` | A1–A5 每阶段 Step 0：记录 branch/worktree/model/sandbox，并用绝对解释器验证 Conda `1999wiki` 的 `sys.prefix` 与 Python 3.11.15 | 解释器路径、`sys.prefix` 或版本任一不符时 fail-closed，停止并报告 D |
| `AGENT-P0-02` | 全程：无 subagent/CLI dispatch/B/C reads | 出现第三层任务或跨 worktree 访问时停止 |
| `AGENT-P0-03` | 全程：原 session、无人工 token budget | 因预算跳过调查/测试时 gate 失败 |
| `AGENT-P0-04` | 本 Plan + A1→A5 | D 未批准 Plan 前不得实现 |
| `TEST-P0-01` | A1 参数化分类/授权/4×4 matrix | 任一授权组合不符时阶段失败 |
| `TEST-P0-02` | A2 Topic fixture/strict owner | Topic empty 或角色串 Owner 时阶段失败 |
| `TEST-P0-03` | A3 composite/失败隔离/超限 | 分支顺序、检索边界或降级错误时阶段失败 |
| `TEST-P0-04` | A3 global citation tests | duplicate/foreign citation 时阶段失败 |
| `TEST-P0-05` | A4 grounding/memory/disconnect | mixed/local/anchor/commit 语义错误时阶段失败 |
| `TEST-P0-06` | A4 REST/SSE/schema/sanitizer/action | 线协议不一致或泄露时阶段失败 |
| `TEST-P0-07` | A5 全量相关回归 | 角色/expand/citation/memory/voice 任一退化时不得完成 |
| `PHASE-P0-01` | 每阶段提交后状态 `completed_pending_review` 等待 D | 未经 D 审查不得开始下一阶段 |

---

## 3. 执行任务

### 3.0 每阶段强制 Conda 环境门禁

A1、A2、A3、A4、A5 的任何测试、实现或提交动作前，都重新运行以下命令；不得复用上一阶段结果：

```powershell
$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Conda 1999wiki interpreter missing: $Python"
}
& $Python -c "import sys; expected_prefix=r'D:\Anaconda32024\envs\1999wiki'; assert sys.prefix == expected_prefix, (sys.prefix, expected_prefix); assert sys.version_info[:3] == (3, 11, 15), sys.version; print(sys.executable); print(sys.prefix); print(sys.version)"
if ($LASTEXITCODE -ne 0) {
    throw 'Conda 1999wiki environment mismatch; stop and report to D.'
}
```

Expected: 输出解释器 `D:\Anaconda32024\envs\1999wiki\python.exe`、`sys.prefix=D:\Anaconda32024\envs\1999wiki` 和 Python `3.11.15`，退出码为 0。路径、prefix、版本或命令退出码任一不符即 fail-closed；停止本阶段且不修改实现。

### Task A1：RequestPlan、任务授权、双开关矩阵与本地回答

- [ ] **Step 0：运行第 3.0 节 Conda `1999wiki` fail-closed 门禁**

**对应 Specs:** `ARCH-P0-01..05`、`TASK-P0-01..09`、`AUTH-P0-01..10`、`PLAN-P0-01..07`、`COMPOSITE-P0-01..03`、`SCOPE-P0-01`、`QUERY-P0-01`、`LOCAL-P0-01..06`、`PACKET-P0-06`、`GROUND-P0-04`、`EXEC-P0-03`、`TEST-P0-01`

**Files:**

- Create: `src/rag/request_plan.py`
- Create: `src/rag/local_responses.py`
- Create: `tests/test_request_plan.py`
- Create: `tests/test_local_responses.py`
- Modify: `src/rag/query_plan.py`
- Modify: `src/rag/route_policy.py`
- Modify: `src/rag/contracts.py`
- Modify: `src/rag/chain.py`
- Modify: `src/rag/execution.py`
- Modify: `tests/test_query_plan.py`
- Modify: `tests/test_route_policy.py`
- Modify: `tests/test_rag_contracts.py`
- Modify: `tests/test_rag_empty_recovery.py`

**Interfaces:**

- Produces: `TaskType`, `RetrievalScope`, `PlannedSubtask`, `RequestPlan`, `RequestPlanner`, `validate_request_plan`
- Produces: `authorize_subtask()` and `finalize_subtask_route()`
- Produces: `render_local_response(task_type, query, *, reason) -> str`
- Preserves: `QueryPlanner.plan()` as KB-only planner and existing `authorize_route()` compatibility wrapper for old single-KB tests
- Consumed by A2: `QueryPlan.retrieval_scope`
- Consumed by A3: validated ordered subtasks and branch-level authorization

- [ ] **Step 1：写 RequestPlan schema 与 fallback 分类红灯**

在 `tests/test_request_plan.py` 用 spy QueryPlanner 覆盖：

```python
def test_single_local_task_uses_the_same_request_plan_contract():
    plan = RequestPlanner(None, query_planner=BombQueryPlanner()).plan("你是谁")
    assert plan.schema_version == "rag.request_plan/v1"
    assert [(task.subtask_id, task.order, task.task_type) for task in plan.subtasks] == [
        ("T01", 1, "assistant_meta"),
    ]
    assert plan.subtasks[0].query_plan is None


def test_fallback_splits_only_the_approved_independent_triplet():
    plan = RequestPlanner(None, query_planner=FixtureQueryPlanner()).plan(
        "你好，你是谁，请介绍一下十四行诗"
    )
    assert [(task.task_type, task.query) for task in plan.subtasks] == [
        ("social_smalltalk", "你好"),
        ("assistant_meta", "你是谁"),
        ("knowledge_base", "请介绍一下十四行诗"),
    ]
    assert [task.subtask_id for task in plan.subtasks] == ["T01", "T02", "T03"]


@pytest.mark.parametrize("query", [
    "十四行诗是谁，她为什么加入基金会",
    "比较十四行诗和槲寄生",
    "如果十四行诗没有加入基金会，她后来会怎样",
    "十四行诗，然后呢",
])
def test_dependent_or_punctuation_only_questions_are_not_split(query):
    assert len(RequestPlanner(None, FixtureQueryPlanner()).plan(query).subtasks) == 1
```

增加非法 plan 参数化断言：0/5 subtasks、重复/跳号 order、重复 ID、未知/后向 depends_on、环、KB 无 QueryPlan、非 KB 有 QueryPlan、非 KB route/retrieval payload、subquery 注入原请求外语义、版本非 v1，全部 `ValueError`。

- [ ] **Step 2：运行 RequestPlan 红灯**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest tests/test_request_plan.py -q
```

Expected: FAIL，提示 `src.rag.request_plan` 不存在；不得因导入错误以外的现有测试失败继续实现。

- [ ] **Step 3：写本地回答与 no-LLM 红灯**

在 `tests/test_local_responses.py` 覆盖：

```python
def test_assistant_meta_is_deterministic_and_project_scoped():
    answer = render_local_response("assistant_meta", "你是谁", reason="local_assistant_meta")
    assert "AI 助手" in answer
    assert "重返未来：1999" in answer
    assert "知识库" in answer


def test_smalltalk_never_claims_human_experience():
    answer = render_local_response("social_smalltalk", "你晚饭吃了吗", reason="local_social_smalltalk")
    assert "不吃饭" in answer
    assert not any(marker in answer for marker in ("我吃了", "我睡", "我看见", "我的身体"))


def test_denied_general_uses_a_capability_boundary_not_an_entity_error():
    answer = render_local_response("general_open", "中国首都是什么", reason="general_open_denied")
    assert "自由补充" in answer
    assert "实体识别失败" not in answer
    assert "数据库为空" not in answer
```

集成 spy 断言 “你是谁”/“你晚饭吃了吗” 在 `chain._llm=None` 时仍成功，Retriever 和开放 LLM 都为 0，sources/assets/media/citation IDs 均为空。

- [ ] **Step 4：运行本地回答红灯**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest tests/test_local_responses.py -q
```

Expected: FAIL，提示 `src.rag.local_responses` 不存在。

- [ ] **Step 5：扩展 route policy 的 4×4 授权矩阵红灯**

修改 `tests/test_route_policy.py`，参数化 `expanded/free_supplement × sufficient/partial/empty/failed`，精确断言 retrieval scope、effective route 和 reason：

```python
@pytest.mark.parametrize(
    ("expanded", "free", "outcome", "route", "reason"),
    [
        (False, False, "sufficient", "rag_grounded", "grounded_sufficient"),
        (False, False, "partial", "rag_grounded", "grounded_partial"),
        (False, False, "empty", "rag_grounded", "grounded_empty"),
        (False, False, "failed", "rag_grounded", "retrieval_failed"),
        (True, False, "sufficient", "expanded_rag", "grounded_sufficient"),
        (True, False, "partial", "expanded_rag", "grounded_partial"),
        (True, False, "empty", "expanded_rag", "grounded_empty"),
        (True, False, "failed", "rag_grounded", "retrieval_failed"),
        (False, True, "sufficient", "rag_grounded", "grounded_sufficient"),
        (False, True, "partial", "rag_grounded", "grounded_partial"),
        (False, True, "empty", "llm_general", "authorized_empty_fallback"),
        (False, True, "failed", "rag_grounded", "retrieval_failed"),
        (True, True, "sufficient", "expanded_rag", "grounded_sufficient"),
        (True, True, "partial", "expanded_rag", "grounded_partial"),
        (True, True, "empty", "llm_general", "authorized_empty_fallback"),
        (True, True, "failed", "rag_grounded", "retrieval_failed"),
    ],
)
def test_dual_toggle_matrix(knowledge_plan, expanded, free, outcome, route, reason):
    authorization = authorize_route(
        knowledge_plan,
        {"expanded": expanded, "free_supplement": free},
        None,
    )
    decision = finalize_route(authorization, outcome)
    assert decision.effective_route == route
    assert decision.route_reason == reason
```

另加 `general_open` 默认 denied、显式 toggle authorized、force recovery 跳过 retrieval 且 reason 为 `explicit_recovery_action`、遗留 `hybrid_answer` 归一化 grounded、授权不跨 subtask 的红灯。

- [ ] **Step 6：运行授权红灯**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest tests/test_route_policy.py tests/test_rag_empty_recovery.py -q
```

Expected: FAIL，至少显示 local/general task route、`not_applicable` 或双开关 expanded+free 断言尚未满足。

- [ ] **Step 7：实现最小 RequestPlan 与本地模板**

实现要点：

1. `RequestPlanner` 的 LLM schema 只允许 task type、query、order、depends_on；不接受 route authorization。
2. 对每个 `knowledge_base` subtask 才调用 `QueryPlanner.plan()`；根据已解析 owner 设置 `entity_strict/topic_strict`，明确游戏 Topic 但无 owner 设置 `corpus_topic`。
3. fallback 先匹配显式 assistant meta、小聊，再匹配固定三段基准；其余保守生成单 task。
4. `validate_request_plan()` 校验 1..4、TNN/order、depends_on、无环、query 语义子集、KB/非 KB payload 边界。
5. `local_responses.py` 使用一个冻结能力配置和按语言选择的模板映射；不读 LLM readiness，不含数据库具体事实。
6. `QueryPlan` 增加 `retrieval_scope: RetrievalScope`，但 QueryPlanner 仍只负责 KB intent、owner 和 query rewrite。

- [ ] **Step 8：实现最小授权与单分支兼容执行**

`authorize_subtask()`：

- local/out_of_scope → `local_response` + `not_applicable`；
- knowledge_base → 复用现有 `authorize_route()`，expanded 只改变检索范围，free 仅记录 after-empty；
- general_open 无明确授权 → `local_response/general_open_denied/not_applicable`；
- general_open 有 toggle 或精确 force action → `llm_general/not_applicable`；
- Planner route 只进入 proposal，不改变许可位。

先让单 subtask 通过同一个 `RequestPlan` 路径；A1 不实现多分支并发，只允许一个分支执行，三分支测试仅验证 plan。`chain.retrieve()` 和现有单 KB `chain.ask()` 保持兼容。

- [ ] **Step 9：运行 A1 定向测试**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_request_plan.py `
  tests/test_local_responses.py `
  tests/test_query_plan.py `
  tests/test_route_policy.py `
  tests/test_rag_contracts.py `
  tests/test_rag_empty_recovery.py `
  -q
```

Expected: PASS；特别确认 16 个 toggle/outcome case 全部通过，`partial`/`failed` 没有 general LLM 调用。

- [ ] **Step 10：运行 A1 相邻回归**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_execution.py `
  tests/test_chain_assets.py `
  tests/test_citations.py `
  tests/test_conversation_memory.py `
  -q
```

Expected: PASS；现有 single-KB citation repair、safe fallback、memory 和媒体行为不退化。

- [ ] **Step 11：检查失败表现与范围**

验证：

- Planner timeout/parse/schema/api error 只产生安全 fallback 和 planning diagnostics；
- local 模板异常使用统一 fallback，不进入 Retriever/LLM；
- general denied 不暴露 entity/database 内部错误；
- `failed` 永不转换成 `empty`；
- `rg -n "subagent|codex exec|rag-b-bm25|rag-c-projection" src tests` 不出现新增委派或跨 worktree 路径；
- `git diff --name-only` 仅包含 A1 文件。

- [ ] **Step 12：提交 A1**

```powershell
git add `
  src/rag/request_plan.py `
  src/rag/local_responses.py `
  src/rag/query_plan.py `
  src/rag/route_policy.py `
  src/rag/contracts.py `
  src/rag/chain.py `
  src/rag/execution.py `
  tests/test_request_plan.py `
  tests/test_local_responses.py `
  tests/test_query_plan.py `
  tests/test_route_policy.py `
  tests/test_rag_contracts.py `
  tests/test_rag_empty_recovery.py
git commit -m "feat(rag): authorize local and knowledge task routes"
```

提交后状态设为 `completed_pending_review`，等待 D 审核；未经批准不进入 A2。

---

### Task A2：Retrieval Scope、Topic/Story fixture 与 Owner Gate

- [ ] **Step 0：运行第 3.0 节 Conda `1999wiki` fail-closed 门禁**

**对应 Specs:** `SCOPE-P0-02..09`、`QUERY-P0-02..05`、`TOPIC-P0-01..06`、`OWN-P0-02`、`TEST-P0-02`

**Files:**

- Create: `tests/fixtures/rag_thread_a/topic_story_children.json`
- Create: `tests/test_rag_topic_scope.py`
- Modify: `src/rag/query_plan.py`
- Modify: `src/rag/retriever.py`
- Modify: `src/rag/packet_policy.py`
- Modify: `tests/test_query_plan.py`
- Modify: `tests/test_retriever.py`
- Modify: `tests/test_entity_packet.py`
- Modify: `tests/test_retrieval_budget.py`

**Interfaces:**

- Consumes: `QueryPlan.retrieval_scope`
- Produces: `build_sparse_query_segments(plan: QueryPlan) -> tuple[str, ...]`
- Produces: topic/story/page PacketPolicy
- Preserves: `LocalBM25SparseIndex.search(query: str, top_k: int)` interface; does not modify Analyzer
- Produces for A3: valid raw source rows retaining owner/source identity and `source_refs`

- [ ] **Step 1：创建冻结字段 Topic/Story fixture**

fixture 至少含：

1. `topic:storm` 两个定义性 child，来自不同 parent/page，均有有效 `source_refs`；
2. 一个已解析 `story` owner；
3. 一个 character page 对“暴雨”的零散提及，用于降权/多样性测试；
4. 十四行诗和另一角色的 skill child，用于 Owner Gate；
5. 缺失 `source_refs`、invalid source、无法证明 alias 的拒绝样例；
6. `Data:Story/304502` 仅有内部 ID、无自然标题的 unresolved 样例。

每行只使用冻结公共字段；不得增加 `owner_type` 或 C 私有字段。

- [ ] **Step 2：写 scope 与 Topic 消费红灯**

在 `tests/test_rag_topic_scope.py`：

```python
def test_owner_free_game_topic_uses_corpus_topic_and_crosses_valid_topic_sources(
    request_planner,
    topic_retriever,
):
    plan = request_planner.plan("暴雨是什么").subtasks[0].query_plan
    assert plan.retrieval_scope == "corpus_topic"
    results = retriever.search(plan.normalized_query, query_plan=plan)
    assert {row["entity_type"] for row in results} <= {"topic", "story", "page"}
    assert len({row["parent_id"] for row in results}) >= 2
    assert all(row["source_refs"] for row in results)


def test_resolved_topic_uses_topic_strict(resolved_topic_plan, topic_retriever):
    results = topic_retriever.search(
        resolved_topic_plan.normalized_query,
        query_plan=resolved_topic_plan,
    )
    assert resolved_topic_plan.retrieval_scope == "topic_strict"
    assert {row["entity_id"] for row in results} == {"topic:storm"}


def test_character_skill_keeps_entity_strict_owner_gate(
    sonetto_skill_plan,
    topic_retriever,
):
    plan = sonetto_skill_plan
    results = topic_retriever.search(plan.normalized_query, query_plan=plan)
    assert plan.retrieval_scope == "entity_strict"
    assert {row["entity_id"] for row in results} == {"character:sonetto"}
```

加入 invalid source/ref 不可 grounded、unresolved title 保留 ID 与 diagnostics、六种 entity_type 兼容、没有 `owner_type` 的静态断言。

- [ ] **Step 3：写 sparse segments 红灯**

断言 segments 按固定顺序包含且去重：

```python
assert build_sparse_query_segments(plan) == (
    "暴雨是什么",
    plan.sparse_query,
    "暴雨",
    "暴雨事件",
    "story",
    "剧情",
    "故事",
)
```

同一实体/alias/hint 重复只保留一次；空字符串移除；传入 BM25 的 joined query 保持 deterministic。静态断言 `src/rag/sparse.py` 未修改。

- [ ] **Step 4：运行 A2 红灯**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_topic_scope.py `
  tests/test_retriever.py `
  tests/test_entity_packet.py `
  tests/test_retrieval_budget.py `
  -q
```

Expected: FAIL，当前无实体非 `general` 直接 empty，且没有 topic/corpus scope 或 Topic policy。

- [ ] **Step 5：实现最小 scope-aware Retriever**

实现：

1. `none` 在进入 Retriever 前被执行层拒绝；Retriever 收到 `none` 视为结构化调用错误。
2. `entity_strict` 完全复用现有 `filter_owned_rows()` 和 `assert_packet_ownership()`。
3. `topic_strict` 构造 topic/story/page `EntityRef` 并在 structured/BM25/dense/fusion/rerank/expand/allocate 各阶段严格过滤。
4. `corpus_topic` 只允许 `entity_type in {"topic","story","page"}` 或明确 topic/story route tag；角色零散提及仅可作为低优先候选且不能挤掉定义性 Topic/Story source。
5. 对 page/owner 设置上限，优先不同 parent；保留每个 row 自己的 `entity_type/entity_id/owner_entity_id/owner_page_id/source_refs`。
6. 缺失/invalid `source_refs` 的行进入 diagnostics，不进入 grounded result。
7. expanded mode 只扩大已有 topic/entity 候选范围和 limit，不取消类型/owner/source-ref gate。

- [ ] **Step 6：实现 Topic/Story/Page policy 与 sparse segments**

在 `packet_policy.py` 增加非角色 policy：

```python
TOPIC_POLICIES = {
    "story": PacketPolicy("topic_story", ("story", "plot", "lore"), "rag", source_target=2),
    "general_game": PacketPolicy("corpus_topic", (), "rag", source_target=3),
}
```

实际选择同时考虑 entity_type 和 intent；不改变 character policies。`build_sparse_query_segments()` 输出原子 segments，`_sparse_query_for_plan()` 仅确定性 join，Analyzer 继续由 `LocalBM25SparseIndex` 内部处理。

- [ ] **Step 7：运行 A2 定向测试**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_topic_scope.py `
  tests/test_query_plan.py `
  tests/test_retriever.py `
  tests/test_entity_packet.py `
  tests/test_retrieval_budget.py `
  -q
```

Expected: PASS；“暴雨是什么”有跨来源 Topic 引用候选，“十四行诗的技能是什么”无 foreign owner。

- [ ] **Step 8：运行 A2 检索回归**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_hybrid_retriever.py `
  tests/test_reranker.py `
  tests/test_huiji_only_runtime_policy.py `
  tests/test_backend_provenance_gate.py `
  -q
```

Expected: PASS；旧 artifact、provenance gate、fusion、rerank 行为不退化。

- [ ] **Step 9：检查失败表现与所有权**

确认：

- owner mismatch/missing metadata 仍进入 diagnostics；
- invalid source/ref 不被静默当 grounded；
- unresolved natural title 不猜测；
- `git diff -- src/rag/sparse.py src/huiji_rag/build/projection.py src/huiji_rag/build/media_v3.py` 为空；
- fixture 与实现中无 `owner_type`、无 B/C worktree 路径。

- [ ] **Step 10：提交 A2**

```powershell
git add `
  src/rag/query_plan.py `
  src/rag/retriever.py `
  src/rag/packet_policy.py `
  tests/fixtures/rag_thread_a/topic_story_children.json `
  tests/test_rag_topic_scope.py `
  tests/test_query_plan.py `
  tests/test_retriever.py `
  tests/test_entity_packet.py `
  tests/test_retrieval_budget.py
git commit -m "feat(rag): support scoped owner-free topic retrieval"
```

提交后等待 D 审核；未经批准不进入 A3。

---

### Task A3：全局来源、复合执行、失败隔离与确定性聚合

- [ ] **Step 0：运行第 3.0 节 Conda `1999wiki` fail-closed 门禁**

**对应 Specs:** `ARCH-P0-04..05`、`AUTH-P0-08`、`PLAN-P0-04`、`COMPOSITE-P0-04..07`、`CITE-P0-01..06`、`PACKET-P0-01`、`GROUND-P0-03/05`、`EXEC-P0-01..07`、`TEST-P0-03/04`

**Files:**

- Create: `tests/test_rag_composite_execution.py`
- Create: `tests/test_rag_global_citations.py`
- Modify: `src/rag/contracts.py`
- Modify: `src/rag/citations.py`
- Modify: `src/rag/execution.py`
- Modify: `src/rag/chain.py`
- Modify: `src/rag/serializers.py`
- Modify: `backend/schemas.py`
- Modify: `tests/test_citations.py`
- Modify: `tests/test_rag_execution.py`
- Modify: `tests/test_chain_assets.py`

**Interfaces:**

- Produces: immutable `BranchResult`
- Produces: `GlobalSourceAllocation`
- Produces: `execute_request_plan()` internal phase pipeline
- Produces: `ActionItem.subtask_id`
- Consumed by A4: ordered branch results, aggregate answer, global source map, action/media collections

- [ ] **Step 1：写 BranchResult 与有界并发红灯**

在 `tests/test_rag_composite_execution.py` 使用 barrier/spies：

```python
def test_approved_triplet_executes_only_the_kb_branch_through_retrieval():
    packet = service.execute(request("你好，你是谁，请介绍一下十四行诗"))
    assert retriever.queries == [("T03", "请介绍一下十四行诗")]
    assert [item.subtask_id for item in packet.subtasks] == ["T01", "T02", "T03"]


def test_branch_failure_isolated_and_answer_order_is_original_order():
    packet = service.execute(fixture_plan_with_local_failure_and_kb_success())
    assert packet.answer.index("T01") < packet.answer.index("T03")
    assert packet.subtasks[0].status == "failed"
    assert packet.subtasks[2].status == "succeeded"
    assert "Traceback" not in packet.answer


def test_executor_never_exceeds_four_active_branches():
    assert concurrency_probe.maximum_active <= 4
```

覆盖 KB empty + local success、general denied + KB success、all noncommittable、depends_on topo 顺序、超限 plan 不执行、local/general `not_applicable`。

- [ ] **Step 2：写全局 source map 红灯**

在 `tests/test_rag_global_citations.py`：

```python
def test_two_kb_branches_share_one_global_sequence():
    allocation = build_global_source_map([
        ("T01", [source("child-a"), source("shared")]),
        ("T02", [source("child-b"), source("shared")]),
    ])
    assert [row["citation_id"] for row in allocation.sources] == ["S01", "S02", "S03"]
    assert allocation.branch_source_ids["T01"] == ("S01", "S02")
    assert allocation.branch_source_ids["T02"] == ("S03", "S02")


def test_same_identity_with_different_content_hash_is_rejected():
    with pytest.raises(SourceIdentityCollision):
        build_global_source_map([
            ("T01", [source("shared", sha="a" * 64)]),
            ("T02", [source("shared", sha="b" * 64)]),
        ])
```

覆盖 branch 引用未分配 ID、local/general citation-like token 清除、grounded 每分支至少一个合法引用、global source ID 唯一、顶层聚合验证。

- [ ] **Step 3：运行 A3 红灯**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_composite_execution.py `
  tests/test_rag_global_citations.py `
  tests/test_citations.py `
  tests/test_rag_execution.py `
  -q
```

Expected: FAIL，当前服务只执行单 QueryPlan，每个 source map 独立从 S01 开始。

- [ ] **Step 4：实现分阶段复合执行**

执行顺序必须编码为独立私有 helper，并由测试 spy 顺序：

1. `_plan_and_authorize()`；
2. `_retrieve_branches_bounded(max_workers=4)`；
3. `build_global_source_map()`；
4. `_answer_branches_bounded(max_workers=4)`；
5. `_freeze_branch_results()`；
6. `_aggregate_ordered_sections()`；
7. `validate_global_citations()`；
8. `_freeze_response_packet()`。

带 depends_on 的分支按 topo batch；没有依赖的分支并发。每个 branch 捕获 retrieval、LLM、citation 异常，转换为不含 traceback 的 `BranchResult(status="failed", public_error=<安全分类>)`。

- [ ] **Step 5：实现全局引用分配与分支上下文**

identity key 按 Spec 字段组合；先按 subtask order、branch rank 排序，再去重。`source_refs` 的 site/title/revid/content_sha256 参与稳定 identity/collision 检测。每个 grounded branch 只用 `branch_source_ids[subtask_id]` 构建 context 和 validate；不允许 answer helper看到其他 branch source。

- [ ] **Step 6：实现确定性聚合和分支资源合并**

聚合器：

- 只读取冻结 BranchResult；
- 按 order 一次性拼接，每个分支一个固定 section；
- 不调用 LLM；
- 不修改 branch answer/citation token；
- local/general 无 source/media/action；
- KB media、omitted/failure action 按 subtask order 去重；
- action 增加 `subtask_id`；单任务缺省可绑定唯一 task，composite 缺失/伪造 ID 直接拒绝。

- [ ] **Step 7：运行 A3 定向测试**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_composite_execution.py `
  tests/test_rag_global_citations.py `
  tests/test_citations.py `
  tests/test_rag_execution.py `
  tests/test_chain_assets.py `
  -q
```

Expected: PASS；重复执行相同 fixture 的 answer/source/subtask/action 顺序完全一致。

- [ ] **Step 8：运行 A3 单分支兼容回归**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_empty_recovery.py `
  tests/test_route_policy.py `
  tests/test_retriever.py `
  tests/test_hybrid_retriever.py `
  tests/test_voice_pagination.py `
  -q
```

Expected: PASS；single-KB 行为、显式 expand/force free、Voice pagination 均不退化。

- [ ] **Step 9：验证失败表现**

显式检查：

- local branch 模板异常只使该 branch failed；
- KB empty 不影响合法 local；
- general denied 不影响 KB；
- branch-level source collision 只返回安全失败摘要，不公开 hash/path；
- all branches 不可提交时顶层 `not_committable`；
- 至少一个合法 branch 时保留成功 answer 并公开失败 subtask status；
- composite action 缺失/伪造 `subtask_id` 被拒绝且不改变任何 branch route。

- [ ] **Step 10：提交 A3**

```powershell
git add `
  src/rag/contracts.py `
  src/rag/citations.py `
  src/rag/execution.py `
  src/rag/chain.py `
  src/rag/serializers.py `
  backend/schemas.py `
  tests/test_rag_composite_execution.py `
  tests/test_rag_global_citations.py `
  tests/test_citations.py `
  tests/test_rag_execution.py `
  tests/test_chain_assets.py
git commit -m "feat(rag): execute composite request plans with global citations"
```

提交后等待 D 审核；未经批准不进入 A4。

---

### Task A4：v3 mixed packet、记忆、REST/SSE 与 sanitizer 一致性

- [ ] **Step 0：运行第 3.0 节 Conda `1999wiki` fail-closed 门禁**

**对应 Specs:** `PACKET-P0-02..07`、`GROUND-P0-01..05`、`MEMORY-P0-01..07`、`CITE-P0-07`、`API-P0-01..07`、`TEST-P0-05/06`

**Files:**

- Modify: `src/rag/contracts.py`
- Modify: `src/rag/execution.py`
- Modify: `src/rag/conversation.py`
- Modify: `src/rag/serializers.py`
- Modify: `src/rag/citations.py`
- Modify: `backend/schemas.py`
- Modify: `backend/sse.py`
- Modify: `backend/main.py`
- Modify: `tests/test_rag_contracts.py`
- Modify: `tests/test_rag_execution.py`
- Modify: `tests/test_conversation_memory.py`
- Modify: `tests/test_conversation_api.py`
- Modify: `tests/test_sse.py`
- Modify: `tests/test_citations.py`

**Interfaces:**

- Produces: `SubtaskInfo`
- Produces: `GroundingMode` with `mixed`; `TurnOutcome` with `mixed/local`
- Produces: `RetrievalOutcome` with `not_applicable`
- Produces: `ExecutionRoute` with `local_response/composite`
- Produces: `rag.retrieval_packet/v3` and `rag.response_packet/v3`
- Produces: `aggregate_grounding_mode(branch_modes: Sequence[GroundingMode]) -> GroundingMode`
- Produces: `aggregate_retrieval_outcome(kb_outcomes: Sequence[RetrievalOutcome]) -> RetrievalOutcome`
- Produces: shared `build_completed_turn()` selection over all branch results

- [ ] **Step 1：写 v3 packet/enum/aggregation 红灯**

在 `tests/test_rag_contracts.py` 参数化：

```python
@pytest.mark.parametrize(
    ("branch_modes", "expected"),
    [
        (("grounded",), "grounded"),
        (("ungrounded",), "ungrounded"),
        (("none",), "none"),
        (("grounded", "none"), "mixed"),
        (("grounded", "ungrounded"), "mixed"),
        (("none", "ungrounded"), "mixed"),
    ],
)
def test_top_level_grounding_matrix(branch_modes, expected):
    assert aggregate_grounding_mode(branch_modes) == expected


@pytest.mark.parametrize(
    ("kb_outcomes", "expected"),
    [
        ((), "not_applicable"),
        (("sufficient", "sufficient"), "sufficient"),
        (("sufficient", "partial"), "partial"),
        (("sufficient", "empty"), "partial"),
        (("sufficient", "failed"), "partial"),
        (("empty", "empty"), "empty"),
        (("failed", "failed"), "failed"),
    ],
)
def test_composite_retrieval_outcome_ignores_non_kb_branches(kb_outcomes, expected):
    assert aggregate_retrieval_outcome(kb_outcomes) == expected
```

断言 v3 schema、旧顶层字段、SubtaskInfo 精确 allowlist、single route 与 composite route。

- [ ] **Step 2：写记忆选择与 commit 时机红灯**

在 `tests/test_conversation_memory.py`/`tests/test_conversation_api.py` 覆盖：

- local-only turn 可存历史但无 entity anchor；
- local + 唯一 valid grounded entity 写该 anchor；
- 两个不同 grounded entity 不写 anchor；
- corpus_topic/story 无单一角色不写 anchor；
- empty/denied/failed/invalid citation 不写 anchor；
- mixed 历史保存顶层 outcome；
- 旧 citations 在 history prompt 中失效。

在 `tests/test_sse.py` 保留并扩展断开测试：sources 后断开、任一 token 后断开、branch failure 后有成功但 done 前断开，均不提交。

- [ ] **Step 3：写 REST/SSE 同 packet 语义红灯**

增加 fixture chain 的 execute call counter：

```python
def test_rest_and_sse_each_execute_once_and_publish_equivalent_done_payload(
    client,
    execution_spy,
):
    request_json = {
        "question": "介绍十四行诗，再问你是谁",
        "conversation_id": "00000000-0000-0000-0000-000000000001",
    }
    sync_response = client.post("/ask", json=request_json)
    assert sync_response.status_code == 200
    sync_payload = sync_response.json()

    with client.stream("POST", "/ask/stream", json=request_json) as response:
        assert response.status_code == 200
        events = _parse_sse(response.read().decode("utf-8"))

    event_names = [event_name for event_name, _payload in events]
    assert event_names[0] == "sources"
    assert event_names[-1] == "done"
    assert all(event_name == "token" for event_name in event_names[1:-1])

    sources_payload = next(payload for name, payload in events if name == "sources")
    done_payload = next(payload for name, payload in events if name == "done")
    for field in ("answer", "sources", "source_map", "subtasks", "route", "grounding_mode"):
        assert sync_payload[field] == done_payload[field]
    assert sources_payload["subtasks"] == done_payload["subtasks"]
    assert execution_spy.calls == 2
```

branch failure + success 只在 `subtasks[].status`，不发 `error`；RequestPlan 建立失败/整个 service exception 才发顶层 error。OpenAPI 断言 `SubtaskInfo`、mixed、local_response、composite、not_applicable。

- [ ] **Step 4：写 sanitizer/timing 红灯**

向 nested branch/public metadata 注入 `prompt/content/plan/query_plan/authorization/traceback/credential/local path`，断言 REST、sources、done 全部不含。允许 `subtasks` 九字段、`subtask_id` action、四个总阶段：

```text
request.planning
branch.retrieval
branch.answer
response.aggregation
```

不允许每个 prompt、模型原始 trace 或内部 exception class/message。

- [ ] **Step 5：运行 A4 红灯**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_contracts.py `
  tests/test_conversation_memory.py `
  tests/test_conversation_api.py `
  tests/test_sse.py `
  -q
```

Expected: FAIL，当前 public enums 无 mixed/local/composite/not_applicable/subtasks，记忆仅支持 grounded/ungrounded。

- [ ] **Step 6：升级 contracts 与 serializer 到 v3**

实现：

- `FrozenRetrievalPacket.schema_version = "rag.retrieval_packet/v3"`；
- `ResponsePacket.schema_version = "rag.response_packet/v3"`；
- 保留所有旧顶层 public fields，新增 `subtasks`；
- `SubtaskInfo` 只含 Spec 九字段；
- route/grounding/outcome 按冻结矩阵聚合；
- serializer 不公开 BranchResult.answer、public_error 之外错误、RequestPlan/QueryPlan/raw prompt/context。

- [ ] **Step 7：实现唯一实体锚点与 turn 历史**

`build_completed_turn()`：

1. packet 必须完整冻结且顶层 outcome 属于 `grounded/ungrounded/mixed/local`；
2. 收集 `status=succeeded`、`grounding=grounded`、citation valid 的 KB entity refs；
3. 恰好一个 unique character ownership key 才写 anchor；
4. 多实体、topic/story/page、corpus_topic 或无 valid grounded branch 时 entity fields 为 None；
5. local/mixed turn 仍保存 answer、requested intents 和顶层 outcome；
6. `ConversationTurn.grounding_mode` 扩展为顶层 outcome-compatible 值，projection 继续 neutralize 历史 `[Snn]`。

- [ ] **Step 8：统一 REST/SSE 冻结 packet 与提交 helper**

同步和 SSE 都：

1. acquire lease；
2. 构造同一 `AskExecutionInput`；
3. 调 `chain.execute(question, category, route_options, action_payload, projection, memory_status=lease.status, memory_turns_used=len(projection.turns), trace=trace)` 一次；
4. 用同一 serializer/Pydantic 验证；
5. 只有完整 response 对客户端可见后构造 completed turn；
6. finally release lease。

SSE 在 done 前断开则 `completed_turn=None`。branch failure 不抛到顶层；只有 plan/service 级异常发送 `error`。

- [ ] **Step 9：运行 A4 定向测试**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_contracts.py `
  tests/test_rag_execution.py `
  tests/test_conversation_memory.py `
  tests/test_conversation_api.py `
  tests/test_sse.py `
  tests/test_citations.py `
  -q
```

Expected: PASS；sources/token/done 顺序稳定，REST 与 done payload 除 lifecycle timing 外语义等价。

- [ ] **Step 10：运行 API/媒体回归**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_chain_assets.py `
  tests/test_voice_pagination.py `
  tests/test_backend_provenance_gate.py `
  tests/test_rag_eval_client.py `
  tests/test_rag_eval_contracts.py `
  -q
```

Expected: PASS；旧客户端字段、Voice page endpoint、provenance gate 和 eval contract 不退化。

- [ ] **Step 11：验证失败表现**

确认：

- mixed 不跳过 grounded branch citation validation；
- general denied 为 `none + local`，不是 ungrounded；
- branch failure 有成功时无 SSE error；
- plan/service exception 发送一个 sanitized error；
- SSE 断开不提交；
- sanitizer 不因新增 subtasks 放宽 prompt/content/plan/path；
- timing 只公开总阶段。

- [ ] **Step 12：提交 A4**

```powershell
git add `
  src/rag/contracts.py `
  src/rag/execution.py `
  src/rag/conversation.py `
  src/rag/serializers.py `
  src/rag/citations.py `
  backend/schemas.py `
  backend/sse.py `
  backend/main.py `
  tests/test_rag_contracts.py `
  tests/test_rag_execution.py `
  tests/test_conversation_memory.py `
  tests/test_conversation_api.py `
  tests/test_sse.py `
  tests/test_citations.py
git commit -m "feat(rag): publish mixed responses and safe memory"
```

提交后等待 D 审核；未经批准不进入 A5。

---

### Task A5：完整 Thread A 回归、P0 验收与提交边界审计

- [ ] **Step 0：运行第 3.0 节 Conda `1999wiki` fail-closed 门禁**

**对应 Specs:** `TEST-P0-01..07`、`OWN-P0-01..02`、`AGENT-P0-01..04`、`PHASE-P0-01` 及全部完成判定

**Files:**

- Modify only if a Thread A P0 regression requires a minimal fix in an already allowed A file
- No new production feature
- No P1/P2 implementation
- No new commit unless a regression fix is required; any fix commit must name the exact P0 regression

- [ ] **Step 1：运行分类与授权验收**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_request_plan.py `
  tests/test_local_responses.py `
  tests/test_query_plan.py `
  tests/test_route_policy.py `
  tests/test_rag_empty_recovery.py `
  -q
```

Expected: PASS；“你是谁”“你晚饭吃了吗”“中国首都是什么”、显式 free、Planner llm_general 绕过、legacy hybrid、4×4 toggle/outcome 全覆盖。

- [ ] **Step 2：运行 Topic/Owner 验收**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_topic_scope.py `
  tests/test_retriever.py `
  tests/test_entity_packet.py `
  tests/test_retrieval_budget.py `
  tests/test_hybrid_retriever.py `
  -q
```

Expected: PASS；“暴雨是什么”跨合法 Topic source，“十四行诗技能”严格 Owner Gate。

- [ ] **Step 3：运行 composite/global citation 验收**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_composite_execution.py `
  tests/test_rag_global_citations.py `
  tests/test_citations.py `
  tests/test_rag_execution.py `
  -q
```

Expected: PASS；三分支基准、失败隔离、最大并行 4、全局 S01..Snn、source collision 和顶层验证全部通过。

- [ ] **Step 4：运行 packet/memory/API/SSE 验收**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_rag_contracts.py `
  tests/test_conversation_memory.py `
  tests/test_conversation_api.py `
  tests/test_sse.py `
  -q
```

Expected: PASS；mixed/local/outcome、唯一实体锚点、断开不提交、REST/SSE schema/sanitizer 一致。

- [ ] **Step 5：运行现有角色、媒体与 Voice 回归**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_chain_assets.py `
  tests/test_voice_pagination.py `
  tests/test_reranker.py `
  tests/test_huiji_only_runtime_policy.py `
  tests/test_backend_provenance_gate.py `
  -q
```

Expected: PASS；intro/profile/skill/item/culture/voice/media/video、citation safe fallback、expand/force action、Voice pagination 均不退化。

- [ ] **Step 6：运行会话 TTL/lease/并发与 eval contract 回归**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_verify_rag_conversation_memory.py `
  tests/test_rag_eval_conversation.py `
  tests/test_rag_eval_deterministic.py `
  tests/test_rag_eval_client.py `
  tests/test_rag_eval_contracts.py `
  -q
```

Expected: PASS；TTL、lease、clear、并发、历史 citation 失效和 eval 公共字段稳定。

- [ ] **Step 7：运行 Thread A 合并前测试集合**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_request_plan.py `
  tests/test_local_responses.py `
  tests/test_rag_topic_scope.py `
  tests/test_rag_composite_execution.py `
  tests/test_rag_global_citations.py `
  tests/test_query_plan.py `
  tests/test_route_policy.py `
  tests/test_rag_contracts.py `
  tests/test_rag_execution.py `
  tests/test_retriever.py `
  tests/test_citations.py `
  tests/test_conversation_memory.py `
  tests/test_conversation_api.py `
  tests/test_sse.py `
  tests/test_rag_empty_recovery.py `
  tests/test_entity_packet.py `
  tests/test_chain_assets.py `
  tests/test_voice_pagination.py `
  tests/test_hybrid_retriever.py `
  tests/test_retrieval_budget.py `
  tests/test_huiji_only_runtime_policy.py `
  tests/test_backend_provenance_gate.py `
  -q
```

Expected: PASS，零失败；若存在与 Thread A diff 无关的环境失败，保存精确命令、首个失败、环境证据并报告 D，不修改无关模块。

- [ ] **Step 8：执行 P0 编号与 deferred 静态审计**

Run:

```powershell
$spec = Get-Content -Raw -Encoding UTF8 `
  "docs/superpowers/specs/2026-07-29-rag-thread-a-routing-design.md"
$plan = Get-Content -Raw -Encoding UTF8 `
  "docs/superpowers/plans/2026-07-29-rag-thread-a-routing.md"
$ids = [regex]::Matches($spec, '([A-Z]+-P0-\d+)') |
  ForEach-Object { $_.Groups[1].Value } |
  Sort-Object -Unique
$missing = $ids | Where-Object { $plan -notmatch [regex]::Escape($_) }
if ($missing) { throw "Missing P0 IDs: $($missing -join ', ')" }
```

再检查实现不存在自动 Hybrid/全文聚合 LLM 分支；`mixed` 只能来自已批准的成功 branch 组合，而不是自动 expanded RAG + general LLM。

- [ ] **Step 9：执行文件所有权和越界审计**

```powershell
git diff --name-only ed569ee23f5d3927f8a332e69ef4de82ac8b6c59..HEAD
git diff --check ed569ee23f5d3927f8a332e69ef4de82ac8b6c59..HEAD
git status --short
```

Expected:

- 仅出现 Thread A Spec 允许的实现、测试和 A fixture；
- `src/rag/sparse.py`、projection/media builder、resource downloader、raw/candidate/active pointer 不在 diff；
- 无 B/C worktree 路径、无生产数据、无下载产物；
- 工作树 clean。

- [ ] **Step 10：检查四个阶段提交**

```powershell
git log --oneline ed569ee23f5d3927f8a332e69ef4de82ac8b6c59..HEAD
```

Expected 按顺序仅含：

```text
feat(rag): authorize local and knowledge task routes
feat(rag): support scoped owner-free topic retrieval
feat(rag): execute composite request plans with global citations
feat(rag): publish mixed responses and safe memory
```

若 A5 发现 P0 回归并必须修复，新增一个小提交，格式为 `fix(rag): enforce <exact-p0-boundary>`；不得 amend 已经由 D 审查的阶段提交。

- [ ] **Step 11：输出完成证据并等待 D 最终审核**

最终报告必须包含：

- status `completed_pending_review`；
- phase `review`；
- 四个阶段提交 SHA；
- changed files；
- 每条测试命令及通过数量；
- P0 coverage audit 结果；
- 文件所有权和 deferred audit；
- 已知风险与 D 真实 A/B/C 联调项；
- `needs_approval=false`，除非发现公共契约变化、越界文件需求或 Spec 冲突。

---

## 4. Deferred / 明确不实施

以下条目只记录，不得加入 A1-A5 实现或测试成功条件：

| Deferred | 原因与边界 |
|---|---|
| `TASK-P1-01` | 更丰富小聊模板需新批准；P0 只做受控最小模板 |
| `TASK-P2-01` | 长期人格、跨会话偏好和开放社交代理不属于本轮 |
| `AUTH-P1-01..03` | partial 后显式“补充缺失部分” action 属 P1；常驻开关不得自动执行 |
| `AUTH-P2-01..03` | expanded RAG + 通用 LLM 自动并行与自动 mixed 属 P2；双开关不得静默授权 |
| `COMPOSITE-P1-01` | 通用显式两阶段 depends_on 需独立评测；P0 只支持 schema/topo 安全边界 |
| `COMPOSITE-P2-01` | 跨分支比较、因果综合、反事实、任务图、全文润色不实施 |
| 更细 Topic diversity/定义性排序 | P1；P0 只做最小受控类型、source-ref 和多样性 gate |
| 前端 subtask 专门展示 | P1；本轮只保证旧客户端兼容和 wire schema |
| BGE-M3 Sparse、稀疏向量 | P2/其他线程；A 只形成 sparse segments |
| VLM 图片描述 | P2/其他线程 |
| 正式候选构建、下载、上传、生产激活 | 未授权外部/生产操作 |

特别禁止把顶层 `grounding_mode="mixed"` 误解为自动 Hybrid。P0 的 mixed 仅表示用户请求本身包含多个已独立授权并成功的 branch（例如 grounded KB + local assistant meta）；不得为同一 KB shortfall 自动创建通用 LLM branch。

---

## 5. D 审核门禁

每阶段 D 至少检查：

1. 本阶段 P0 编号均有红灯、最小实现、定向测试、回归和失败表现；
2. Planner proposal 与 Route Policy authorization 没有合并；
3. 默认数据库外自由回答仍关闭；
4. 双开关四种组合在 sufficient/partial/empty/failed 下完全符合矩阵；
5. Topic/Story 使用冻结字段和 A fixture，不依赖 C 实现；
6. 角色 Owner Gate 没有因 corpus_topic 放宽；
7. global source ID、branch allowlist 和顶层 citation validation 完整；
8. BranchResult/ResponsePacket/serializer/Pydantic/sanitizer/REST/SSE enum 一次贯通；
9. memory 只在完整 packet 和传输完成后提交；
10. 无 P1/P2、跨 worktree、Analyzer、projection、媒体生产或激活动作；
11. 提交小而可审查，工作树 clean；
12. 下一阶段只有在 D 明确批准后开始。

若代码事实与 Spec 冲突、冻结字段不足、必须修改禁止文件或公共契约需要变化，立即停止，保持当前 diff，不自行扩大范围，并以 `status=needs_approval` 报告精确证据、受影响 P0、最小选项和替代方案。
