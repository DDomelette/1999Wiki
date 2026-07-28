# 线程 A：路由、主题消费与复合问题编排设计

日期：2026-07-29

状态：用户审核候选

负责人：线程 A；规格与集成审核：线程 D

设计依赖：

- `docs/superpowers/specs/2026-07-29-rag-cli-supervision-design.md`
- `docs/superpowers/plans/2026-07-29-rag-cli-supervision.md`

## 1. 背景与目标

当前 RAG 运行时以“一个请求、一个知识意图、一个实体 Owner、一次检索、一个回答包”为核心。该结构适合“十四行诗的技能是什么”，但对以下问题表现僵硬或直接返回空检索：

```text
你是谁
你晚饭吃了吗
暴雨是什么
你好，你是谁，请介绍一下十四行诗
```

已核实的当前实现事实：

1. `src/rag/query_plan.py` 的 `QueryPlan` 同时承载知识意图和执行路线，没有顶层任务类型。
2. `src/rag/route_policy.py` 允许 Planner 提议 `llm_general`，但默认关闭自由补充时，空检索仍被压回 grounded。
3. `src/rag/retriever.py` 的 `_ENTITY_FREE_INTENTS` 只有 `general`；无实体且 intent 不在该集合时直接返回空结果。
4. `src/rag/execution.py` 每次只执行一个 `QueryPlan` 并生成一个 `ResponsePacket`。
5. `src/rag/contracts.py` 的 `GroundingMode` 只有 `grounded/ungrounded/none`，没有混合回答语义。
6. `src/rag/citations.py` 在单次来源列表冻结后从 `S01` 编号，两个独立回答直接拼接会产生重复 ID。
7. `src/rag/conversation.py` 的每个 turn 只有一个实体锚点。
8. `backend/schemas.py`、`src/rag/serializers.py` 和 `backend/sse.py` 只公开单路响应契约。
9. 前端已经允许 `expanded` 与 `free_supplement` 同时开启并传入后端；当前 Route Policy 的组合语义是先执行扩大检索，只有 retrieval outcome 为 `empty` 时才自由补充。遗留 `hybrid_answer` 会被归一化为 grounded route，当前不存在自动并行混合回答。

线程 A 的目标是：

1. 将任务类型与知识库内部 intent 分离。
2. 在不放开默认自由补充的前提下，自然回答助手身份和社交小聊。
3. 允许没有单一角色 Owner 的 Topic/Story 知识问题进入受控知识库检索。
4. 对安全、独立的复合问题进行有限拆分、并行执行和确定性聚合。
5. 为整轮请求统一分配引用，并保持同步 API、SSE、记忆和公开 schema 一致。
6. 保留角色实体 Owner Gate、引用验证和默认防幻觉边界。
7. 冻结“扩大检索”和“自由补充”的双开关组合语义，避免 UI 状态、请求参数和执行路线各自成立但组合行为未定义。

## 2. 范围与非目标

### 2.1 线程 A 负责

- 顶层任务分类；
- Planner 提议与 Route Policy 授权分离；
- 助手身份、小聊、拒答和能力边界的本地回答；
- Topic/Story 的无单一角色 Owner 检索消费；
- 安全复合问题拆分；
- 分支执行、失败隔离和确定性聚合；
- 全局来源去重和引用编号；
- 混合 grounding、turn outcome 和记忆规则；
- 同步 API、SSE、serializer 和 Pydantic schema；
- 双开关组合授权矩阵及对应 Route Policy 回归；
- A 自带 fixture 的路由、执行、引用、记忆和 API 回归。

### 2.2 线程 A 不负责

- 中文 BM25 Analyzer 的实现、词典和索引格式；
- BGE-M3 Sparse 或其他稀疏向量；
- pages/wikitext/data_pages/resources 的语义投影；
- Story/Topic 自然标题和别名的生产；
- Wikitext 图片解析、媒体下载或媒体绑定生产；
- 正式候选构建、Milvus 写入、active pointer 或生产激活；
- 修改线程 B/C worktree 中尚未合并的代码；
- 开放式 LLM 对所有数据库外问题自动作答。
- 在 P0 中自动并行执行 expanded RAG 与通用 LLM，或自动混合 grounded 与 ungrounded 段落。

## 3. 总体架构

```text
用户原始问题
  │
  ▼
Request Planner
  ├─ 识别单任务或安全复合任务
  ├─ 为每个分支分配 task_type
  └─ 仅为 knowledge_base 分支生成 QueryPlan
  │
  ▼
Route Policy
  ├─ local：assistant_meta / social_smalltalk / out_of_scope
  ├─ grounded：knowledge_base
  ├─ gated：general_open
  └─ denied：未授权 general_open
  │
  ▼
Branch Executor
  ├─ 本地分支直接回答
  ├─ KB 分支检索
  └─ 已授权 general_open 调用通用 LLM
  │
  ▼
Global Source Allocator
  ├─ 来源去重
  ├─ 全局 S01...Snn
  └─ 回填每个 grounded 分支
  │
  ▼
Branch Answer + Validation
  │
  ▼
Deterministic Aggregator
  ├─ 保持原问题顺序
  ├─ 隔离分支失败
  └─ 不调用开放 LLM 重写全部答案
  │
  ▼
ResponsePacket / REST / SSE / Memory
```

`ARCH-P0-01`：顶层 Request Planner 必须先分类任务和决定是否安全拆分；现有 `QueryPlanner` 只在 `knowledge_base` 分支内部执行实体、知识 intent、查询重述和检索计划。

`ARCH-P0-02`：Planner 只能提出 task type 和 route 候选，不能直接授予数据库外自由回答权限。Route Policy 是唯一授权者。

`ARCH-P0-03`：单任务和复合任务必须走同一个顶层 `RequestPlan` 契约。单任务表现为一个 subtask，避免维护两套执行语义。

`ARCH-P0-04`：分支内部可以并行，但最终来源编号、回答顺序、公开字段顺序和记忆更新必须确定。

`ARCH-P0-05`：第一版最多接受 4 个 subtask，不允许嵌套 composite。超过限制或无法可靠拆分时保留为一个知识库任务或返回明确边界，不递归规划。

## 4. 顶层任务类型

```text
assistant_meta
social_smalltalk
knowledge_base
general_open
out_of_scope
```

`TASK-P0-01`：`assistant_meta` 处理助手身份、能力和使用方式，例如“你是谁”“你能做什么”。它不执行数据库检索，不调用开放 LLM。

`TASK-P0-02`：`social_smalltalk` 处理问候、礼貌表达和轻量社交问题，例如“你好”“你晚饭吃了吗”。它不声称拥有身体、饮食、现实经历或人类身份。

`TASK-P0-03`：`knowledge_base` 处理游戏角色、技能、剧情、世界观、主题、媒体和资料问题。它继续使用现有 `intro/profile_fact/skill/story/...` 知识 intent。

`TASK-P0-04`：`general_open` 处理数据库外、非助手身份、非小聊的通用事实或开放问题。Planner 只能提出该类型；默认不能作答。

`TASK-P0-05`：`out_of_scope` 处理无法安全执行、被产品能力明确排除或包含不受支持操作的问题，返回确定性能力边界。

`TASK-P0-06`：以下基准分类必须稳定：

| 输入 | task type | 默认行为 |
|---|---|---|
| `你是谁` | `assistant_meta` | 本地助手说明 |
| `你晚饭吃了吗` | `social_smalltalk` | 本地非人类小聊 |
| `暴雨是什么` | `knowledge_base` | Topic/Story 检索 |
| `十四行诗的技能是什么` | `knowledge_base` | 严格实体检索 |
| `中国的首都是什么` | `general_open` | 默认拒绝自由回答 |

`TASK-P0-07`：现有 `meta_question` 兼容映射到 `assistant_meta`；`general_game` 映射到 `knowledge_base`；知识库内部 intent 不得被顶层 task type 替代。

`TASK-P0-08`：LLM Planner 不可用、超时、解析失败或 schema 错误时，fallback 至少能稳定识别显式 meta、小聊、明显游戏知识和单一知识问题。fallback 对复合问题必须保守，不可靠时不拆分。

`TASK-P0-09`：fallback 必须能处理“问候/助手身份/一个明确 KB 请求”这种固定独立组合，因此基准“你好，你是谁，请介绍一下十四行诗”在 Planner LLM 不可用时仍能形成三个分支。包含指代、因果或比较时继续不拆分。

### 4.1 P1

`TASK-P1-01`：可以增加更多受控小聊模板和语言风格，但不得以开放 LLM 替代本地身份事实。

### 4.2 P2

`TASK-P2-01`：个性化长期助手人格、跨会话偏好学习和开放社交代理不进入本轮。

## 5. 回答授权矩阵

| task type | 检索 | 默认是否允许 | 回答来源 |
|---|---:|---:|---|
| `assistant_meta` | 否 | 是 | 本地确定性模板 |
| `social_smalltalk` | 否 | 是 | 本地受控模板 |
| `knowledge_base` | 是 | 是 | Grounded RAG |
| `general_open` | 否 | 否 | 仅显式授权后的通用 LLM |
| `out_of_scope` | 否 | 是 | 本地边界说明 |

`AUTH-P0-01`：`assistant_meta`、`social_smalltalk` 和 `out_of_scope` 必须新增 `local_response` effective route，不能伪装成 `llm_general` 或 `rag_grounded`。

`AUTH-P0-02`：`general_open` 不执行知识库检索，只有在以下任一现有显式授权成立时才能进入 `llm_general`：

- `route_options.free_supplement=true`；
- 用户触发已存在的 `force_free_supplement` 恢复 action。

`AUTH-P0-03`：Planner 输出 `general_open` 或 `llm_general` 本身不能授权自由回答。默认关闭自由补充时必须生成边界说明，不能先执行空检索再报“未检测到实体”。

`AUTH-P0-04`：`knowledge_base` 分支中的普通 `free_supplement=true` 只表示 `allow_free_supplement_after_empty`，不表示跳过检索或始终生成通用回答。该分支仍必须先完成本轮授权范围内的正常检索。

`AUTH-P0-05`：常驻双开关的 P0 组合矩阵固定为：

| `expanded` | `free_supplement` | KB 检索范围 | `sufficient` | `partial` | `empty` | `failed` |
|---:|---:|---|---|---|---|---|
| false | false | 默认范围 | grounded | grounded + shortfall | grounded 不足提示 | 结构化检索错误 |
| true | false | 扩大范围 | expanded grounded | expanded grounded + shortfall | grounded 不足提示 | 结构化检索错误 |
| false | true | 默认范围 | grounded | grounded + shortfall | `llm_general` | 结构化检索错误 |
| true | true | 扩大范围 | expanded grounded | expanded grounded + shortfall | `llm_general` | 结构化检索错误 |

`AUTH-P0-06`：双开关同时开启时，P0 必须先执行一次 expanded retrieval；有任意可提交证据时不自动创建自由补充分支。只有 outcome 精确为 `empty` 才能使用本轮已有自由补充许可。`failed` 不是 `empty`，不得伪装成资料为空后进入通用回答。

`AUTH-P0-07`：`force_free_supplement` 是用户对精确恢复 action 的直接授权，可以跳过知识库重试；它与常驻 `free_supplement` 的 empty fallback 语义必须使用不同的公开 route reason。

`AUTH-P0-08`：复合请求中的授权按分支执行。一个 `assistant_meta` 分支合法，不会为同轮 `general_open` 分支扩展权限；一个 KB 分支的 empty fallback 也不会授权其他 KB 或 general 分支。

`AUTH-P0-09`：公开 route reason 至少增加或保留：

```text
local_assistant_meta
local_social_smalltalk
local_out_of_scope
general_open_denied
toggle_allows_empty_fallback
authorized_empty_fallback
explicit_recovery_action
retrieval_failed
composite_mixed
composite_partial
```

`AUTH-P0-10`：本地回答必须在代码中集中管理，不把身份声明、能力边界和非人类小聊规则散落在 Planner prompt、API handler 或异常分支中。

### 5.1 P1 显式补充缺失部分

`AUTH-P1-01`：当 KB 分支 outcome 为 `partial` 时，可以返回“自由补充缺失部分”恢复 action，但不得因常驻开关已开启而自动执行。

`AUTH-P1-02`：该 action 必须绑定原 KB `subtask_id`、规范化 query、semantic intents 和原检索 scope；明确实体问题同时携带 EntityRef，无单一实体的 Topic/Story 保留其 scope mode。用户点击后，ungrounded 补充必须与既有 grounded 结果分区显示，不得改写、吞并或移除已验证的 grounded 文本与引用。

`AUTH-P1-03`：自由补充段落不得携带 `[Snn]`、sources、media 或“来自知识库”的声明；失败只影响补充分支。

### 5.2 P2 自动 Hybrid

`AUTH-P2-01`：自动并行执行 expanded RAG 与通用 LLM、再发布 `mixed` 回答属于 P2，不进入本轮 A 的实施 Plan。

`AUTH-P2-02`：未来启用自动 Hybrid 前，必须新增明确的用户可见说明和版本化线协议授权，例如 `hybrid_mode=parallel`。不得仅根据遗留请求中的 `expanded=true && free_supplement=true` 静默扩大授权语义。

`AUTH-P2-03`：Hybrid 的 grounded 与 ungrounded 分支必须分别生成和验证，按固定分区聚合；通用 LLM 不得获得改写 grounded 事实或引用的权限。顶层可标记 `mixed`，但只有 grounded 分支进入 source map 和实体事实记忆。

## 6. RequestPlan 和 Subtask 契约

新增独立模块 `src/rag/request_plan.py`，不继续扩大 `query_plan.py` 的职责。

```text
RequestPlan
  original_query
  subtasks[]
  aggregation_mode
  planning_status
  planning_warning
  planning_error

PlannedSubtask
  subtask_id
  order
  task_type
  query
  query_plan
  depends_on[]
```

`PLAN-P0-01`：`subtask_id` 为请求内稳定 ID，例如 `T01`；`order` 从 1 连续递增。

`PLAN-P0-02`：只有 `knowledge_base` subtask 可以持有现有 `QueryPlan`。其他 task type 的 `query_plan` 必须为空，避免无意义实体门禁。

`PLAN-P0-03`：`depends_on` 第一版只用于标记不能并行的显式依赖；无法安全表示的依赖问题不拆分。

`PLAN-P0-04`：`aggregation_mode` 第一版固定为 `ordered_sections`。聚合器不调用 LLM 改写已验证分支答案。

`PLAN-P0-05`：Request Plan 必须通过严格 schema 验证：

- task type 在固定枚举内；
- subtask 数为 1 至 4；
- order 唯一且连续；
- subtask ID 唯一；
- depends_on 只能引用当前 plan 中较早任务；
- 不允许环；
- KB 分支必须有 QueryPlan；
- 非 KB 分支不得携带实体、route override 或检索参数；
- 分支 query 必须是原始问题的语义子集，不能注入新的用户请求。

`PLAN-P0-06`：Planner 原始输出、prompt、解析异常和内部路径不得进入公开 response。

`PLAN-P0-07`：`RequestPlan` schema version 第一版固定为 `rag.request_plan/v1`。序列化和测试必须显式验证版本，不能根据字段存在与否猜测版本。

## 7. 复合问题拆分

`COMPOSITE-P0-01`：第一版只拆分语义独立、可以分别回答且不存在共享指代的并列问题。

必须拆分的基准：

```text
你好，你是谁，请介绍一下十四行诗
```

得到：

```text
T01 social_smalltalk  "你好"
T02 assistant_meta    "你是谁"
T03 knowledge_base    "请介绍一下十四行诗"
```

`COMPOSITE-P0-02`：以下问题默认不拆分：

```text
十四行诗是谁，她为什么加入基金会
比较十四行诗和槲寄生
如果十四行诗没有加入基金会，她后来会怎样
```

原因分别是共享指代/因果、跨实体比较和反事实依赖。它们保留为单个 KB 任务，由知识问答链统一处理；若当前能力不支持，则返回明确不足。

`COMPOSITE-P0-03`：标点、逗号和“然后”不能单独作为拆分依据。拆分结果必须经过独立性检查。

`COMPOSITE-P0-04`：两个及以上安全独立分支必须通过有界执行器并行执行，最大并行度不超过 4。带 depends_on 的分支按拓扑顺序执行。

`COMPOSITE-P0-05`：一个分支失败、为空或被拒绝不能吞掉其他成功分支。公开 subtask status 至少包括：

```text
succeeded
empty
denied
failed
```

`COMPOSITE-P0-06`：最终回答按原问题顺序拼接；每个分支只出现一次。第一版使用确定性段落分隔，不增加一个开放聚合 LLM。

`COMPOSITE-P0-07`：如果所有分支均无可提交回答，顶层 turn 为 `not_committable`；如果至少一个分支有合法本地、grounded 或已授权回答，则提交成功分支并公开失败摘要。

### 7.1 P1

`COMPOSITE-P1-01`：可以支持显式 depends_on 的两阶段任务，但必须有单独评测，不能扩大第一版拆分范围。

### 7.2 P2

`COMPOSITE-P2-01`：跨分支推理、比较综合、反事实、多轮任务图和 LLM 全文润色不进入本轮。

## 8. 检索 Scope 与 Owner Gate

现有 `_ENTITY_FREE_INTENTS` 白名单不足以表达角色、主题和本地任务的区别。应引入显式检索 scope：

```text
none
entity_strict
topic_strict
corpus_topic
```

`SCOPE-P0-01`：`none` 用于所有非 KB 任务，不调用 Retriever。

`SCOPE-P0-02`：`entity_strict` 用于已经解析出角色、心相、物品等实体的查询。所有 structured、BM25、dense、fusion、rerank、expand、allocate 阶段继续执行现有 Owner Gate。

`SCOPE-P0-03`：`topic_strict` 用于已经解析出 `topic/story/page` Owner 的查询，按对应 `entity_type/entity_id` 严格过滤。

`SCOPE-P0-04`：`corpus_topic` 用于知识库任务明确属于游戏概念或剧情主题、但没有单一可解析 Owner 的情况。它可以跨 Owner 检索，但必须：

- 使用 Topic/Story/Page 的 `entity_type`、`route_tags`、标题、别名和章节信号；
- 优先定义性内容、标题和主题块；
- 对角色页零散提及降权；
- 对页面/Owner 做多样性限制；
- 保留每个来源自己的 owner 和 source ref；
- 不把跨页面结果伪装成同一 Owner。

`SCOPE-P0-05`：不能通过删除现有 Owner Gate 实现 `corpus_topic`。角色实体问题仍必须严格隔离，任何 owner mismatch 或缺失 owner metadata 继续进入诊断。

`SCOPE-P0-06`：`暴雨是什么` 必须进入 `knowledge_base + corpus_topic` 或已解析 Topic 的 `topic_strict`，不能因缺少角色实体直接返回空。

`SCOPE-P0-07`：`十四行诗的技能是什么` 必须进入 `entity_strict`，不得因 Topic 线路开放而混入其他角色资料。

`SCOPE-P0-08`：线程 A 使用自带最小 JSON fixture 验证 Topic/Story 检索；不能在 Plan 编写或首轮开发中读取线程 C worktree 的未合并产物。

`SCOPE-P0-09`：`packet_policy.py` 必须为 `topic/story/page` 提供非角色默认 policy。corpus_topic 候选必须先限制在受支持的游戏语义类型或明确 route tags，不能简单对全部角色 child 取消过滤。

## 9. 与 B 的 Analyzer 和查询重述边界

`QUERY-P0-01`：任务分类和安全拆分发生在知识 QueryPlan 之前；KB 分支完成查询重述和语义查询组装后，才进入 Retriever。

`QUERY-P0-02`：BM25 Analyzer 位于稀疏检索内部，对最终送入 BM25 的查询字段进行分析。线程 A 不分词、不维护词典、不复制 B 的 Analyzer。

`QUERY-P0-03`：线程 A 负责形成稳定的 sparse query segments，至少支持：

```text
KB 子问题原文
Planner sparse_query
entity_name
entity_aliases
知识 intent section hints
```

Analyzer 如何将 segments 变成 token 由线程 B 决定。

`QUERY-P0-04`：segment 合并必须确定、去空和去重，不能让同一实体词因在多个字段重复出现而无上限加权。

`QUERY-P0-05`：线程 A 不修改 B 的 Analyzer 版本、词典哈希、BM25 schema 或 legacy 加载策略。B 合并前，A fixture 使用现有 Retriever 接口；真实接线由 D 集成验证。

## 10. 与 C 的 Topic/Story 公共契约

线程 A 只消费 D 总体 Spec 冻结的公共字段：

```text
category
entity_type
entity_id
entity_name
entity_aliases
owner_entity_id
owner_page_id
route_tags
parent_id
child_id
heading_path
section_kind
content
search_text
source_refs
```

`TOPIC-P0-01`：线程 A 不新增私有 `owner_type` 字段。Owner 语义通过 `entity_type/entity_id/owner_entity_id/owner_page_id` 表达。

`TOPIC-P0-02`：`entity_type` 至少兼容：

```text
character
item
psychube
story
topic
page
```

`TOPIC-P0-03`：自然标题和别名只作为检索与展示信号；稳定身份仍使用 `entity_type + entity_id`、parent ID 和 child ID。

`TOPIC-P0-04`：A 不假设 `Data:Story/304502` 一定有自然标题。C 未提供可证明映射时，A 必须保留内部 ID 并将 unresolved 情况写入诊断，不自行猜标题。

`TOPIC-P0-05`：C 产物中 invalid source、无法证明的别名和缺失 source ref 不能被 A 当作 grounded 来源。

`TOPIC-P0-06`：真实 A/C 联调只在 C 合并后由 D 执行。A 的开发和测试不依赖 C 的实现类、解析函数或本地路径。

## 11. 全局来源和引用

复合请求不能把多个分别从 `S01` 开始的回答直接拼接。

`CITE-P0-01`：整轮请求必须只有一个全局 source map。来源在任何 grounded 分支生成答案前完成合并和编号。

`CITE-P0-02`：全局来源按 subtask 原始顺序、分支内部最终 rank 排序。去重优先使用：

```text
entity_type
entity_id
child_id
parent_id
source_refs 中的 site/title/revid/content_sha256
```

同一 child 被多个分支使用时共享一个 citation ID。

如果同一稳定 identity 对应不同 content 或不同 source hash，必须报告 source identity collision 并拒绝静默合并。

`CITE-P0-03`：每个 grounded 分支只获得其允许引用的全局 source ref 子集。分支不得引用其他分支未分配给自己的来源。

`CITE-P0-04`：执行顺序必须为：

1. 完成所有 KB 分支检索；
2. 合并并去重来源；
3. 分配全局 `S01...Snn`；
4. 构建每个 grounded 分支上下文；
5. 生成分支答案；
6. 分支级引用验证；
7. 确定性聚合；
8. 顶层全局引用验证。

`CITE-P0-05`：local、denied 和已授权 general 分支不得产生来源引用。引用样式 token 必须按现有 ungrounded 规则清除。

`CITE-P0-06`：顶层验证必须保证：

- 所有 citation ID 存在于全局 map；
- ID 在公开 sources 中唯一；
- 每个 grounded 成功分支至少有合法引用；
- 非 grounded 分支不含 citation token；
- 分支失败说明不伪造引用。

`CITE-P0-07`：历史对话中的旧 citation 继续在进入 prompt 前失效化，不能与本轮全局编号混淆。

## 12. BranchResult 与 ResponsePacket

增加不可变内部契约：

```text
BranchResult
  subtask_id
  order
  task_type
  query
  effective_route
  retrieval_outcome
  grounding_mode
  status
  answer
  source_ids
  entity_ref
  citation_validation
  public_error
```

`PACKET-P0-01`：`BranchResult.answer` 和内部错误不直接无条件公开；serializer 只暴露安全字段和最终聚合 answer。

`PACKET-P0-02`：现有 `ResponsePacket` 升级版本但保留顶层兼容字段：

```text
answer
grounding_mode
sources
assets
media
media_panels
route
planning_status
planning_warning
planning_error
citation_warning
omitted_actions
failure_actions
memory
timing
```

并增加：

```text
subtasks[]
```

`FrozenRetrievalPacket` 和 `ResponsePacket` 的新 schema version 分别固定为：

```text
rag.retrieval_packet/v3
rag.response_packet/v3
```

`PACKET-P0-03`：公开 subtask 只包含：

```text
subtask_id
order
task_type
query
effective_route
retrieval_outcome
grounding_mode
status
citation_ids
```

不公开 Planner prompt、QueryPlan 原始 payload、内部异常栈、上下文、LLM 原始输出或本地路径。

`PACKET-P0-04`：顶层 route 对多分支使用 `composite`；单分支继续公开其实际 route。`ExecutionRoute` 和后端 schema 必须增加：

```text
local_response
composite
```

`PACKET-P0-05`：所有公共 enum 改动必须一次贯通：

- dataclass/type alias；
- frozen packet；
- serializer；
- Pydantic response；
- sanitizer allowlist；
- REST；
- SSE；
- tests。

不能只修改内部契约后让 API 静默丢字段。

`PACKET-P0-06`：`RetrievalOutcome` 增加 `not_applicable`。local、out_of_scope、denied 和 general_open 分支没有执行检索时必须使用它，不能把“未检索”伪装成 `empty`。

`PACKET-P0-07`：composite 顶层 retrieval outcome 只汇总 KB 分支：

- 没有 KB 分支 → `not_applicable`；
- KB 全部 sufficient → `sufficient`；
- 至少一个 KB 成功且存在 partial/empty/failed → `partial`；
- KB 全部 empty → `empty`；
- KB 全部 failed → `failed`。

## 13. Grounding 和 Turn Outcome

Branch grounding：

```text
knowledge_base 成功且引用有效 → grounded
已授权 general_open         → ungrounded
local/denied/out_of_scope    → none
失败或空且无可提交回答       → none
```

顶层 grounding：

| 成功分支组合 | 顶层 grounding_mode |
|---|---|
| 全部 grounded | `grounded` |
| 全部已授权 general | `ungrounded` |
| 全部 local/denied | `none` |
| grounded + local | `mixed` |
| grounded + ungrounded | `mixed` |
| local + ungrounded | `mixed` |

`GROUND-P0-01`：`GroundingMode` 和公开 AskResponse 增加 `mixed`。

`GROUND-P0-02`：`TurnOutcome` 增加：

```text
mixed
local
```

保留：

```text
grounded
ungrounded
not_committable
```

`GROUND-P0-03`：顶层 `mixed` 不能跳过 branch-level citation validation。它表示回答组成混合，不表示 grounded 要求降低。

`GROUND-P0-04`：`general_open` 被拒绝后返回的能力边界属于 local 可提交结果，不得标成 `ungrounded` 通用事实回答。

`GROUND-P0-05`：只要存在一个成功分支，其他 empty/denied/failed 分支以安全摘要公开，顶层 outcome 由成功分支组合决定；全部不可提交时才是 `not_committable`。

## 14. 本地回答

新增 `src/rag/local_responses.py`。

`LOCAL-P0-01`：助手身份回答必须确定性说明它是本项目的 AI 助手，主要基于已接入知识库回答《重返未来：1999》相关问题。

`LOCAL-P0-02`：小聊不得声称吃饭、睡觉、看见现实环境、拥有身体或个人生活。基准回答“你晚饭吃了吗”应自然表达“我不吃饭，但可以陪你聊聊或继续查资料”。

`LOCAL-P0-03`：默认关闭自由补充时，`general_open` 返回简洁边界和可选操作提示，不能使用“实体识别失败”“数据库为空”等内部错误措辞。

`LOCAL-P0-04`：本地回答不依赖 LLM readiness。即使通用模型未配置，“你是谁”和小聊仍应可用。

`LOCAL-P0-05`：本地模板不包含具体数据库事实，不携带 citations、sources、assets 或 media。

`LOCAL-P0-06`：本地回答的语言可以根据用户问题语言选择，但身份和能力事实来自同一受控配置，不允许 Planner 自行编造。

## 15. 会话记忆

`MEMORY-P0-01`：`assistant_meta`、`social_smalltalk`、`general_open` 和 `out_of_scope` 不创建实体锚点。

`MEMORY-P0-02`：单个成功、引用验证通过的 grounded KB 分支可以更新实体锚点。

`MEMORY-P0-03`：复合请求包含本地分支和恰好一个明确 grounded 实体时，可以写入该实体锚点。例如“你好，介绍十四行诗”可以让后续“她的技能呢”继承十四行诗。

`MEMORY-P0-04`：复合请求涉及多个不同实体时，不写入单一实体锚点。后续指代必须重新澄清或重新解析。

`MEMORY-P0-05`：Topic/Story 无单一实体、corpus_topic、引用验证失败、empty、denied 或 failed 分支不能写入角色锚点。

`MEMORY-P0-06`：成功 local 和 mixed turn 可以进入对话历史，但历史投影必须保存顶层 outcome，并继续失效化旧 citation。

`MEMORY-P0-07`：记忆提交只能发生在完整 ResponsePacket 冻结、引用验证和聚合结束之后。SSE 断开或执行中途失败不能写入半成品 turn。

## 16. REST、SSE 和序列化

`API-P0-01`：`/ask` 和 `/ask/stream` 必须调用同一执行服务，获得同一个冻结 ResponsePacket 语义，不允许各自重新规划或重新执行分支。

`API-P0-02`：SSE 事件顺序保持：

```text
sources
token...
done
```

`sources` 事件包含全局 sources、route、subtasks 和非 answer 元数据；token 只传最终聚合 answer；done 传完整公开响应。

`API-P0-03`：分支失败但仍有成功分支时，不发送顶层 SSE `error`；失败状态进入对应 subtask。只有 RequestPlan 无法建立或整个执行服务异常时才发送 `error`。

`API-P0-04`：`AskResponse` 增加严格的 `SubtaskInfo` schema，并扩展 grounding、route reason 和 effective route enum。

`API-P0-05`：transport sanitizer 必须允许新增安全字段，同时继续删除 prompt、content、plan、query_plan、authorization、凭据和本地路径。

`API-P0-06`：timing 至少能表达 request planning、branch retrieval、branch answer 和 aggregation 的总阶段；不公开每个内部 prompt 或模型原始 trace。

`API-P0-07`：旧客户端忽略 `subtasks` 时仍能使用顶层 answer、sources、media 和 route；不得删除或重命名现有顶层字段。

## 17. 执行与错误处理

`EXEC-P0-01`：独立分支的检索和生成使用最大并行度 4 的有界执行器；不能按 Planner 任意输出创建无限任务。

`EXEC-P0-02`：每个分支捕获自己的检索、LLM 和引用错误，转换为安全 BranchResult；不得把异常对象或 traceback 公开。

`EXEC-P0-03`：KB 分支 `empty` 使用知识库不足措辞；general denied 使用权限边界措辞；local 模板失败使用统一本地 fallback。三者不能混为“未检测到实体”。

`EXEC-P0-04`：所有 branch result 先冻结再聚合。聚合器不能修改已经验证的分支文本和 citation token。

`EXEC-P0-05`：媒体和 omitted/failure actions 只来自对应 KB 分支；合并时按 subtask 顺序去重，不让 local/general 分支制造媒体或扩展 action。

`EXEC-P0-06`：复合请求中的显式恢复 action 必须绑定精确 subtask。不能用一个 action 将整轮所有分支改成 `llm_general`。

`EXEC-P0-07`：`ActionItem` 增加可选 `subtask_id`。单任务请求缺省时绑定唯一 subtask；复合请求中的 expand、force free supplement 和 expand_parent 必须携带合法 subtask ID，否则拒绝执行。公开 omitted/failure action 也必须回传该 ID。

## 18. 文件所有权

线程 A 可以修改：

```text
src/rag/request_plan.py
src/rag/local_responses.py
src/rag/query_plan.py
src/rag/route_policy.py
src/rag/contracts.py
src/rag/execution.py
src/rag/chain.py
src/rag/retriever.py
src/rag/packet_policy.py
src/rag/conversation.py
src/rag/citations.py
src/rag/serializers.py
backend/schemas.py
backend/sse.py
backend/main.py
对应的路由、执行、引用、记忆、serializer、API 和 SSE 测试
线程 A 自带的 Topic/Story JSON fixture
```

线程 A 禁止修改：

```text
src/rag/sparse.py
中文 Analyzer 和领域词典
BM25 新旧产物 schema 与 provenance
src/huiji_rag/build/projection.py
src/huiji_rag/build/media_v3.py
src/huiji_rag/build/orchestrator.py 的语义投影
Wikitext 解析
resource_downloader.py
正式 raw snapshot
正式候选和 active pointer
BGE-M3 Sparse
线程 B/C worktree 文件
```

`OWN-P0-01`：如果 B/C 合并导致公共字段或构建 schema 变化，线程 A 不直接修改 B/C 分支；由 D 在 main 决定集成补丁归属。

`OWN-P0-02`：`retriever.py` 属于 A 的高冲突文件。B 只提供 Analyzer 接口，运行时 sparse query segments 接线由 A 实施并由 D 集成审核。

## 19. CLI 执行约束

`AGENT-P0-01`：线程 A 由一个长期 Codex CLI session 在 `codex/rag-a-routing` 独立 worktree 中执行，模型固定请求 `gpt-5.6-sol`，使用标准速度和 `workspace-write`。

`AGENT-P0-02`：启动参数必须显式关闭 `fast_mode` 和 `multi_agent`。禁止创建子代理、再次调用 Codex CLI 分派任务或读取 B/C 未合并 worktree。

启动基线：

```powershell
codex exec `
  -m gpt-5.6-sol `
  --disable fast_mode `
  --disable multi_agent `
  --sandbox workspace-write `
  --json `
  --cd "D:\1999Wiki.worktrees\rag-a-routing"
```

`AGENT-P0-03`：不设置人为 Token budget，不限制正常代码调查、测试次数和必要返工；通过 session resume、结构化状态和避免重复上下文控制消耗。

`AGENT-P0-04`：线程 A 首轮只编写自己的 Implementation Plan。Plan 经 D 审核前不得修改实现代码；Plan 必须按 A1 至 A5 串行执行。

## 20. 测试与验收

### 20.1 任务分类与授权

`TEST-P0-01`：

- “你是谁”不调用 Retriever，不调用开放 LLM；
- “你晚饭吃了吗”不伪装人类经历；
- “中国首都是什么”默认不调用通用 LLM；
- 显式开启 free supplement 后，general_open 才调用通用 LLM；
- Planner 单独输出 llm_general 不能绕过授权；
- `expanded=false, free_supplement=false` 的 KB empty 返回 grounded 不足；
- `expanded=true, free_supplement=false` 的 KB 查询使用扩大范围，empty 仍不自由补充；
- `expanded=false, free_supplement=true` 的 KB 查询先使用默认范围，只有 empty 才自由补充；
- `expanded=true, free_supplement=true` 的 KB 查询先使用扩大范围，只有 empty 才自由补充；
- 四种开关组合下的 `partial` 均保留 grounded 证据和 shortfall，不自动混合自由补充；
- 四种开关组合下的 `failed` 均返回结构化检索错误，不进入自由补充；
- 遗留 `hybrid_answer` 不能绕过 P0 授权矩阵。

### 20.2 Owner 与 Topic

`TEST-P0-02`：

- “暴雨是什么”不因无角色实体返回空；
- Topic fixture 可以跨多个来源回答并引用；
- 已解析 Topic 使用 topic_strict；
- 无实体 Topic 使用 corpus_topic；
- “十四行诗的技能是什么”继续严格 Owner Gate；
- 其他角色资料不能进入十四行诗 packet。

### 20.3 Composite

`TEST-P0-03`：

- “你好，你是谁，请介绍一下十四行诗”生成三个有序分支；
- 只有 KB 分支检索；
- 只有 KB 分支带引用；
- 本地分支失败不影响 KB 分支；
- KB empty 不影响合法本地分支；
- general denied 不影响 KB 分支；
- local/general 分支的 retrieval outcome 为 `not_applicable`；
- 依赖、比较、因果和反事实问题不被盲目拆分；
- subtask 数超过 4 时安全降级。

### 20.4 引用

`TEST-P0-04`：

- 多个 KB 分支共享一个全局 citation map；
- 两个分支不会同时从 `S01` 独立编号；
- 同一 child 跨分支只公开一次 source；
- grounded 分支不能引用未分配来源；
- local/general 分支的 citation-like token 被移除；
- 聚合后顶层引用验证通过。

### 20.5 Grounding 与记忆

`TEST-P0-05`：

- grounded + local → `mixed`；
- local only → `none + local outcome`；
- general authorized only → `ungrounded`；
- 多实体 composite 不写单一实体锚点；
- local + 单实体 grounded 可以写该实体锚点；
- failed/empty/denied 不更新锚点；
- SSE 断开不提交半成品 turn。

### 20.6 REST/SSE

`TEST-P0-06`：

- `/ask` 与 `/ask/stream` 最终公开 payload 语义一致；
- SSE 顺序为 `sources → token → done`；
- sources 事件包含全局 sources 和 subtasks；
- 分支级失败不产生顶层 error；
- composite action 缺少或伪造 subtask ID 时被拒绝；
- schema、serializer 和 sanitizer 不泄露 prompt、plan、content、异常栈和本地路径；
- 旧顶层字段全部保留。

### 20.7 回归

`TEST-P0-07`：

- 现有角色 intro/profile/skill/item/culture/voice/media/video 用例不退化；
- 现有显式 expand 和 force free supplement 行为仍受授权；
- 现有 citation repair 和 safe fallback 行为不退化；
- 现有 conversation TTL、lease 和并发保护不退化；
- 现有 Voice pagination 不受 composite 改动影响。

## 21. 实施阶段与提交边界

线程 A 内部按以下顺序串行推进：

```text
A1 RequestPlan + task authorization + dual-toggle matrix + local responses
  → A2 retrieval scope + Topic/Story fixture 消费
  → A3 global sources + composite execution
  → A4 mixed packet + memory + REST/SSE
  → A5 完整线程 A 回归
```

原因：

- A1 冻结顶层任务和授权语义；
- A2 依赖 A1 的 knowledge_base 和 scope；
- A3 依赖单分支行为稳定；
- A4 必须消费 A3 的 BranchResult；
- 多阶段同时修改 contracts/execution/serializer 会造成高冲突。

建议提交：

```text
feat(rag): authorize local and knowledge task routes
feat(rag): support scoped owner-free topic retrieval
feat(rag): execute composite request plans with global citations
feat(rag): publish mixed responses and safe memory
```

`PHASE-P0-01`：每个阶段必须先完成对应测试和 D 审查再进入下一阶段。线程 A 不创建子代理，不把阶段拆成额外 CLI worker。

## 22. P1 与 P2 汇总

P1 可选：

- 更丰富但仍受控的小聊模板；
- partial KB 回答后的显式“自由补充缺失部分”恢复 action；
- 显式两阶段 depends_on；
- 更细粒度 Topic diversity 和定义性内容排序；
- 前端对 subtask 状态的专门展示。

P2 延后：

- 跨分支比较推理；
- 反事实和任务图；
- 版本化授权后的 expanded RAG + 通用 LLM 自动 Hybrid；
- LLM 聚合全文重写；
- 开放式长期助手人格；
- 稀疏向量；
- VLM 图片描述。

P1 只有全部 P0 完成且获得新批准后才可进入 Plan；P2 不得进入本轮实施任务。

## 23. 完成判定

线程 A 只有同时满足以下条件才能声明完成：

1. task type 与知识 intent 已分层。
2. Planner 不能自行授权数据库外自由回答。
3. “你是谁”和“你晚饭吃了吗”不再触发无实体错误。
4. “暴雨是什么”可以走 Topic/Story 知识检索。
5. 角色实体 Owner Gate 没有放宽。
6. 安全复合问题可以拆分、并行和按序聚合。
7. 全局 citation ID 唯一并通过分支和顶层验证。
8. 分支失败被隔离。
9. mixed grounding、turn outcome 和记忆规则贯通。
10. `/ask`、`/ask/stream`、serializer 和 schema 一致。
11. 不依赖线程 B/C 未合并工作树。
12. 未修改 Analyzer、投影、媒体下载、正式候选或生产激活。
13. P0 测试和现有相关回归全部通过。
14. 双开关四种组合在 sufficient/partial/empty/failed 下均符合冻结矩阵，P0 不自动生成 Hybrid。
15. D 审核 diff、测试、公共契约和文件所有权后接受提交。
