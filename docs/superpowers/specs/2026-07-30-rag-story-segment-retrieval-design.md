# 线程 E：剧情 Segment 双粒度检索与预算设计

日期：2026-07-30

状态：完整 P0 方向与 Policy 权威 Story 检测方案已获用户批准；本文等待最终规格复核，尚未授权实施

负责人：线程 E；规格、集成、向量重建与发布审核：线程 D

设计依赖：

- `docs/superpowers/specs/2026-07-04-character-entity-packet-routing-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-a-routing-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-b-chinese-bm25-analyzer-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-c-topic-story-media-projection-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md`
- `docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md`

最后两项目前仍是主工作区中的待审核文件，不构成已发布依赖。D0 只有在它们随线程 C 的受审提交进入 `main` 后，才能把其路径、提交和 SHA-256 写入 E 的依赖回执；不得从未跟踪工作区文件读取实施契约。

## 1. 背景

线程 C 将旧的大型 Story `profile` 表示改造成来源支持、顺序稳定的剧情原子步骤。真实快照诊断显示，新投影约包含 142,200 个 Story Atom；Atom 中位文本长度约 24 个字符，绝大多数为单行步骤。

这一变化修复了旧表示只暴露故事开头、后半段事实无法召回的问题，但也改变了最合适的检索粒度：

- Atom 适合精确对白、专名、编号和来源引用；
- Atom 太短，不适合作为主要 Dense embedding 单元；
- 一个问题可能同时命中同一剧情中的多个 Atom；
- 一个问题也可能需要比较多个剧情或引用多个剧情作为例证；
- 若直接让约 14 万 Atom 竞争全局 Top-K，剧情会挤压 Topic、Page、角色资料和其他意图；
- 若将命中的 Atom 与其扩展上下文同时发送给模型，会产生重复文本和重复引用；
- 当前全局 `context_budget_chars=9000` 和 `max_sources` 仍以 Child 行为单位，不能表达 Story Owner、Segment 和细节覆盖预算。

旧四层设计曾定义：

```text
Level 0：实体包
Level 1：父块
Level 2：主题组
Level 3：原子子块
```

当前语料不需要让所有领域恢复 Level 2，但 Story 域已经具备足够复杂度。本文将 Level 2 仅恢复为剧情专用的 `story_segment`，并避免使用 `Topic` 命名，以免与“暴雨”等世界观 Topic 实体冲突。

## 2. 目标

线程 E 的目标是：

1. 在不修改 Story Atom 稳定身份和 `parent_id` 的前提下，生成确定性的 Story Segment 检索视图。
2. 保留 Atom BM25 作为精确词汇召回与引用路径。
3. 停止为 Story Atom 逐条生成 Dense 向量，只为 Story Segment 生成剧情 Dense 向量。
4. 将 Atom BM25 和 Segment Dense 命中在 `segment_id` 层融合。
5. 防止 Segment 与 Atom 作为重复正文同时进入模型上下文。
6. 建立 Story Owner、Segment、细节覆盖和字符数的分层预算。
7. 为 Topic/Page 保留独立配额，避免剧情数量淹没世界观定义证据。
8. 支持单剧情多细节、显式多剧情比较和开放式多剧情例证。
9. 保持最终引用精确到规范 Atom 的来源路径。
10. 在新的影子产物和评测证明收益后，才由线程 D 执行一次向量重建与后续发布审核。
11. 从冻结 Story 来源发布可验证的 step/choice/分支/角色结构 sidecar，不把来源结构埋在 Segmenter 内部。
12. 以 Typed Dense Retrieval Unit 同时承载非 Story Child 和 Story Segment，禁止身份复用。
13. 通过受控 `story_required/story_mentions/story_examples` KB 分支支持显式多 Story、角色剧情和 Topic 例证，同时保持现有 Owner Gate。
14. 在真实 embedding 构建前冻结评测 gold、baseline 和 go/no-go 阈值。

## 3. 非目标

本轮明确不实现：

- Reranker；当前开关继续关闭。
- Segment BM25。
- BGE-M3 Sparse 或其他学习型稀疏向量。
- 修改 Story Atom 的 `child_id`、`parent_id`、来源路径或规范内容。
- 将角色、物品、心相、媒体等全部改造成四层结构。
- 通过 LLM 自动决定 Segment 边界或生成 Segment 摘要。
- 基于标题相似度、模糊 NER 或向量相似度猜测 Story 与角色的归属。
- 质量标记驱动的纯数字、短文本或标点硬过滤。
- “完整总结整章/整条剧情”的全量遍历摘要。
- 生产激活、活动指针切换或未经审核的 Milvus 写入。
- 在 C 工作树尚未合并时读取其内部 Python 类、临时产物或绝对路径作为运行依赖。
- 将来源 `step`、`choice`、`name`、`head_icon` 等字段未经 taxonomy 和闭包验证就解释为分支边、角色 ID 或实体归属。
- 将 `segment_id` 填入现有 `child_id`、将 Segment 伪装成 Child，或通过放宽现有 Owner Gate 兼容 Story 补充分支。

`SCOPE-P0-01`：线程 E 只消费 C 合并后发布的公共 Atom/Parent/来源字段，以及这些 `source_refs` 精确指向的同版冻结 `Data:Story` 原始记录；不依赖 C worktree。

`SCOPE-P0-02`：本轮恢复的是剧情检索视图，不是全局核心数据模型重写。

`SCOPE-P0-03`：Reranker、Segment BM25 和全章摘要只能在独立评测与再次批准后进入后续阶段。

`SCOPE-P0-04`：E0 生成的 `story_atom_structure.v1.jsonl` 是附加派生视图，不修改规范 Atom 的 `child_id`、`parent_id`、正文、来源引用或排序。

`SCOPE-P0-05`：P0 不降级为“只实现线性 Segment”。存在显式来源结构的 Story 必须验证并保留分支关系；结构缺失的 Story 才允许明确标记为 `source_order`。

`SCOPE-P0-06`：E 的所有设计依赖必须是固定 `main` 提交中可追踪的文件或已发布 artifact；未跟踪文件、其他 worktree 路径和对话摘要只能作为审查线索，不能成为实现输入。

## 4. 方案选择

评估过三种实现：

| 方案 | 优点 | 主要问题 | 结论 |
|---|---|---|---|
| 保留 Atom BM25 + Atom Dense | 实现最少 | Dense 单元过短、向量数量大、上下文碎片化 | 不采用 |
| 运行时临时拼接 Atom 窗口 | 不增加持久产物 | 窗口本身不可被 Dense 召回，稳定边界和可审计性弱 | 不采用 |
| 规范 Atom + 派生 Story Segment；Atom BM25 + Segment Dense | 精确性、完整性、可审计性和性能平衡 | 需要新产物、融合和预算契约 | P0 采用 |

`DECISION-P0-01`：Story Atom 是规范证据；Story Segment 是可确定性重建的检索视图。

`DECISION-P0-02`：P0 新增的剧情召回通道只有 Atom BM25 和 Segment Dense。Segment BM25 暂不创建。

`DECISION-P0-03`：剧情最终排序和预算单位是 Segment，不是 Atom。

`DECISION-P0-04`：Atom 只提供命中信号、上下文组成和引用，不直接占用最终 Story source 槽位。

## 5. 逻辑层级

Story 域逻辑层级为：

```text
Level 0：Story Entity Packet
└─ Level 1：Story Parent
   ├─ Level 2：Story Segment
   │  ├─ Level 3：Story Atom
   │  ├─ Level 3：Story Atom
   │  └─ Level 3：Story Atom
   └─ Level 2：Story Segment
```

各层职责：

| 层级 | 职责 | 是否直接参与文本召回 |
|---|---|---|
| Story Packet | 会话、Owner、来源包 | 否 |
| Story Parent | 规范 Story 身份、来源和闭包 | 否 |
| Story Segment | Dense、最终剧情候选和上下文 | 是 |
| Story Atom | BM25、精确命中、顺序和引用 | 是，但不直接进入最终候选列表 |

`HIER-P0-01`：新增 Segment 不得重设 Atom 的直接 Parent。

`HIER-P0-02`：一个 Atom 在一个 Segment 产物版本内必须恰好属于一个 Segment。

`HIER-P0-03`：Segment 只能引用同一 Story Owner、同一来源闭包内的 Atom。

### 5.1 E0：Story Atom 结构能力契约

当前规范 Atom 只公开来源路径和线性 `chunk_index`，不足以直接生成分支图、稳定角色关系或 `next_segment_ids`。线程 E 必须先完成 E0，不得从 E1 的 Segment 算法中临时解析或猜测这些关系。

E0 新增独立 `story_atom_structure.v1.jsonl`。它与同版规范 Story Atom 一一对应，每行至少包含：

```text
schema_version
atom_id
story_entity_id
story_parent_id
source_title
source_content_sha256
source_json_path
source_order
source_step_id
incoming_source_step_ids
next_source_step_ids
choice_target_step_ids
relation_kind
branch_id
scene_id
background_id
speaker_display_name
speaker_source_id
mentioned_entity_ids
relation_source_refs
structure_status
diagnostic_codes
content_sha256
atom_char_count
length_status
entity_link_registry_identity
structure_identity
```

允许的 `structure_status`：

| 状态 | 含义 | Segment 行为 |
|---|---|---|
| `explicit_graph` | step/choice 语义、目标和闭包均已验证 | 使用显式图和硬分支边界 |
| `source_order` | 来源没有显式图字段，但线性顺序完整 | 仅生成 `source_order` 邻接 |
| `blocked_invalid_graph` | 显式结构存在但字段、目标或闭包不合法 | 阻断该 Story 的 Segment 构建 |

E0 必须先生成只读 `story_structure_taxonomy.v1.json`，至少统计所有 Story 的字段形态、step/choice 容器、目标多重性、悬空目标、入口、出口、汇合、环、speaker/head 取值形态、可证明实体映射覆盖率，以及 Atom 字符数的 min/median/P95/P99/max 和超过 600/800/16,384 的动态计数。taxonomy、解析配置和输入快照身份必须在 E1 Segment 实现前冻结并写入 `structure_identity`。

2026-07-30 的只读风险审计使用恢复快照 `data_pages.jsonl sha256=eb82b82e34300ee5d8beb27b13311fe530c59faeba3ae7883876b74b0eab9092` 和 C 检查点 `012c7ca6b3abaa0445ccd00a8974ea4fefcbd333`，在 142,811 个可见原始 Story step 中检测到 7 个超过 800 字符，最大 1,115。该统计只证明超长边界已真实出现；E0 仍须对最终规范 Atom 重新计算，不得把这些数值硬编码为验收结果。

E0 同时生成 `story_entity_link_registry.v1.json`。注册表只能由同版规范 Parent 的稳定 `entity_id/entity_name/entity_aliases`、C 已验证关系和来源中已证明的稳定 speaker ID 构成；每个规范化精确键必须记录来源类型、目标实体 ID、歧义状态和注册表 SHA-256。

`ATOMSTRUCT-P0-01`：每个结构行必须同时匹配 Atom 的 `atom_id`、`source_title`、`source_content_sha256`、`source_json_path` 和 `content_sha256`；任何一项不一致均为闭包错误。

`ATOMSTRUCT-P0-02`：`source_step_id`、跳转边和 choice 目标只能来自经过 taxonomy 验证的明确字段位置；不得用 `chunk_index`、数组位置相似性或相邻文本推断显式边。

`ATOMSTRUCT-P0-03`：存在显式 step/choice 字段时，所有非终止目标必须唯一解析到同一 Story 的来源 step。悬空、冲突或跨 Story 未声明目标必须产生 `blocked_invalid_graph`，不得静默回退为线性顺序。

`ATOMSTRUCT-P0-04`：来源确实不含显式结构时，按规范 Atom 顺序生成 `relation_kind=source_order`，并明确记录没有因果或分支语义。

`ATOMSTRUCT-P0-05`：选择节点的每条出边使用来源 choice/target 身份；`branch_id` 由 `story_entity_id + split_source_step_id + target_source_step_id + source_content_sha256` 的规范字节哈希派生，不使用扫描序号。

`ATOMSTRUCT-P0-06`：汇合节点使用排序后的 `incoming_source_step_ids` 形成稳定汇合身份。存在环时先计算来源 step 图的强连通分量；环内 Atom 保留同一 `cycle` 关系域，遍历必须使用 visited 集合，禁止无限展开。

`ATOMSTRUCT-P0-07`：`speaker_display_name` 和 `speaker_source_id` 只保存来源原值。`mentioned_entity_ids` 仅接受精确角色注册表 ID、C 已验证关系或精确别名映射；`name`、`head_icon` 或显示文本本身不得直接充当角色实体 ID。

`ATOMSTRUCT-P0-08`：不能精确映射角色时，保留 display/source 证据、令 `mentioned_entity_ids` 为空并记录诊断；不得为提高覆盖率使用模糊 NER、Dense 相似度或人工角色白名单。

`ATOMSTRUCT-P0-09`：同一固定 Atom、原始记录、taxonomy 和解析配置必须逐字节生成相同结构行；结构产物必须记录行数、Atom ID 顺序哈希、字段 schema 哈希和整体 SHA-256。

`ATOMSTRUCT-P0-10`：E0 必须在 E1 前通过真实快照闭包：每个 Story Atom 恰好一条结构行，显式图目标零悬空，blocked Story 有完整诊断，且规范 Atom 产物逐字节不变。

`ATOMSTRUCT-P0-11`：taxonomy 与正式结构构建必须调用同一版本化来源解析器；不得在 `eval/` 临时脚本中维护另一套字段语义后只把结论抄入产品代码。

`ATOMSTRUCT-P0-12`：实体注册表的规范化只能做 Unicode 规范化、首尾空白处理和项目已冻结的大小写规则；纯数字名称（例如 `6`、`37`）、短名称和内部 ID 必须作为普通精确键保留，不得因长度、字符类型或质量标记被排除。

`ATOMSTRUCT-P0-13`：同一精确键若映射到多个稳定实体，必须标记歧义并禁止发布到 `mentioned_entity_ids`；不得用角色白名单、查询上下文、出现频率或人工单例补丁选定目标。注册表身份必须进入结构产物、runtime snapshot 和评测 provenance。

`ATOMSTRUCT-P0-14`：`atom_char_count` 按规范 Atom 可见正文的 Unicode code point 计算；`length_status` 只能为 `within_hard_max`、`oversize_atom` 或 `blocked_dense_limit`，并参与结构产物身份。

`ATOMSTRUCT-P0-15`：正文超过 `hard_max_chars=800` 但仍满足 Typed Dense 字段和版本化 embedding 输入限制时，标记 `oversize_atom`；它不是低质量、不得从 BM25 删除，也不得触发软降权。

`ATOMSTRUCT-P0-16`：正文或确定性 Segment search text 超过 `VARCHAR(16384)` 或冻结 embedding 输入硬限制时标记 `blocked_dense_limit`，阻断该 Story 的完整 P0 snapshot readiness；不得截断、跳过该 Atom、只构建 BM25 后仍声称完整 Segment 方案可用。

## 6. Story Segment 公共契约

P0 新增独立 `story_segments.v1.jsonl`。每条 Segment 至少包含：

```text
segment_id
schema_version
story_entity_id
story_entity_name
story_parent_id
source_title
source_refs
source_content_sha256
ordered_atom_ids
first_atom_source_token
last_atom_source_token
sequence_index
prev_segment_ids
next_segment_ids
relation_kind
branch_ids
merge_identity
heading_path
context_text
search_text
char_count
atom_count
mentioned_entity_ids
mentioned_entity_names
quality_flags
atom_structure_identity
segmenter_identity
content_sha256
```

`SEGMENT-P0-01`：`ordered_atom_ids` 是 Segment 正文、顺序和引用的唯一规范来源。

`SEGMENT-P0-02`：`context_text` 由 Atom 可见正文按来源顺序确定性组成，不使用生成模型改写。

`SEGMENT-P0-03`：`search_text` 可以省略结构化确认的纯控制 Atom，但不能删除这些 Atom 与 Segment 的关系。

`SEGMENT-P0-04`：Story 标题、自然名和来源名在 Segment search text 中最多出现一次，不在每个 Atom 前重复。

`SEGMENT-P0-05`：Segment 不拥有独立于 Atom 的事实。删除 Segment 产物后必须能从同版 Atom 完整重建。

`SEGMENT-P0-06`：`prev_segment_ids`、`next_segment_ids` 和 `branch_ids` 均为按稳定 ID 排序的去重数组。来源汇合必须保留全部前驱；不得只挑一个“主前驱”来兼容旧线性字段。

### 6.1 Segment 上下文与 Atom 引用契约

Segment 是检索、排序、上下文和字符预算单位；Atom 是来源引用单位。两者不得继续共用当前“一条 Child 正文等于一个 `[Sxx]`”的隐含契约。

运行时新增不可变 `SegmentContextUnit`：

```text
context_unit_id
segment_id
story_entity_id
story_parent_id
base_context_text
atom_spans
segment_char_count
atom_count
content_sha256
```

每个 `atom_spans` 元素为：

```text
atom_id
segment_id
char_start
char_end
atom_content_sha256
source_refs
citation_id
```

`base_context_text` 使用 `ordered_atom_ids` 对应的规范 Atom 可见正文，以单个 `\n` 连接；`char_start/char_end` 是连接后、插入请求级引用标记前的 Unicode code point 半开区间 `[start, end)`。请求级 `citation_id` 在最终 Atom 顺序冻结后分配，渲染器在每个 Atom 文本后追加一个 `[Sxx]`，但不得改变基础 span 或 Segment 产物哈希。

P0 默认预算：

```text
max_segment_slots = 6
max_story_citation_atoms = 72
max_total_citation_sources = 80
```

`CITATIONUNIT-P0-01`：同一 Segment 正文在一次请求上下文中最多封装一次；Atom BM25 命中行不得以第二份独立正文再次进入上下文。

`CITATIONUNIT-P0-02`：进入 `base_context_text` 的每个非空 Atom 都必须有且仅有一个 Atom span 和请求级 citation source；不得只引用 Segment，也不得让无引用 Atom 混入可作为答案事实的正文。

`CITATIONUNIT-P0-03`：`max_segment_slots`、`max_story_citation_atoms` 和 `max_total_citation_sources` 分开计数。Segment 槽位满足但 Atom 引用预算不足时，该 Segment 不得被部分截断或无引用封装。

`CITATIONUNIT-P0-04`：显式 Story/Topic 配额优先于低优先级 Segment；引用预算不足时按同一确定性预算器替换或删除整个低优先级 Segment，并产生 `citation_atom_shortfall`。

`CITATIONUNIT-P0-05`：Source Map 中的 Story citation source 继续使用 Atom `child_id` 和 Atom `source_refs`；同时附带 `segment_id` 仅用于分组和调试，不改变引用事实身份。

`CITATIONUNIT-P0-06`：`context_unit_id` 由 `segment_id + ordered_atom_ids + base_context_text hash` 派生。请求级 `[Sxx]` 不参与稳定身份，重复执行仅允许编号因其他分支的最终顺序改变。

`CITATIONUNIT-P0-07`：REST、SSE、全局复合引用分配、引用验证和前端 source schema 必须能够传输 Atom source 与 `segment_id`；旧非 Story Child source 保持原契约。

`CITATIONUNIT-P0-08`：测试必须证明 span 无重叠、完整覆盖全部非空 Atom、正文不重复、Atom 来源闭合，并在 Segment 顺序相同的情况下生成逐字节一致的基础上下文。

`CITATIONUNIT-P0-09`：新增三个预算字段必须进入版本化 retrieval config；不得复用或静默重解释现有 `max_sources`。旧请求 schema 不新增可由调用方放宽的字段；runtime 从固定版本的 retrieval config 读取上述 P0 默认值。

## 7. Segment 边界

Segment 边界按来源结构优先，不使用抽象主题推断。

边界优先级：

1. 显式 Story/scene/branch/choice 边界。
2. 结构化背景、场景或章节变化。
3. 跳转、分支进入和分支汇合。
4. 来源步骤连续顺序。
5. 达到长度硬上限后的 Atom 边界切分。

首轮构建固定参数：

```text
target_min_chars = 200
target_max_chars = 600
hard_max_chars = 800
target_min_atoms = 8
target_max_atoms = 20
```

这些参数是 Segmenter 版本身份的一部分，评测后可以变更，但变更必须生成新产物版本。

`BOUNDARY-P0-01`：显式分支和选择边界是硬边界，即使 Segment 尚未达到最小长度也不得跨越。

`BOUNDARY-P0-02`：短 Segment 只有在 Story、分支、来源顺序和关系类型均一致时才能与相邻 Segment 合并。

`BOUNDARY-P0-03`：超过硬上限时只能在 Atom 边界切分，不得截断 Atom。

`BOUNDARY-P0-04`：缺少显式结构时允许使用来源顺序，但必须记录 `relation_kind=source_order`，不得伪称因果关系。

`BOUNDARY-P0-05`：所有关系使用 `prev_segment_ids/next_segment_ids`；分支允许一个 Segment 指向多个后继，汇合允许一个 Segment 拥有多个前驱，双向边必须闭合。

`BOUNDARY-P0-06`：Segmenter 只能消费 E0 已发布的结构行，不得再次解释原始 `step/choice` 字段或从 Atom 文本重建图。

`BOUNDARY-P0-07`：`structure_status=blocked_invalid_graph` 的 Story 不生成 Segment、Dense 输入或运行时候选，并报告结构 blocker；不得用 `source_order` 掩盖显式图错误。

`BOUNDARY-P0-08`：choice、split、merge、cycle 和 terminal 节点均为硬边界；任何 Segment 不得同时包含两个互斥 choice 分支的 Atom。

`BOUNDARY-P0-09`：单个 Atom 的 `atom_char_count > hard_max_chars` 且 `length_status=oversize_atom` 时，生成只包含该 Atom 的 Segment，并确保 `quality_flags` 包含 `oversize_atom`。这是硬上限的唯一 P0 例外；不得与前后 Atom 合并。

`BOUNDARY-P0-10`：超长单 Atom Segment 的 `char_count` 保留真实值，Atom span、source refs、citation 和 Segment 身份按普通 Segment 规则闭合；不得截断正文、拆分规范 Atom 或制造新的伪 Atom。

`BOUNDARY-P0-11`：超长 Segment 仍受 Dense schema/embedding 输入验证、Atom citation 预算和最终渲染字符预算约束。若单个 Segment 无法装入 9,000 字符上下文，运行时返回 `context_char_shortfall`，不得截断后发送；若为 `blocked_dense_limit`，构建阶段直接 `no_go`。

`BOUNDARY-P0-12`：测试必须至少包含 799、800、801 字符和超过 Dense 输入限制四个边界用例，并验证唯一例外、逐字节正文、映射闭合、预算 shortfall 和 fail-closed 行为。

## 8. 稳定身份

`segment_id` 必须来自来源支持的边界证据，至少包括：

```text
story_entity_id
source_content_sha256
atom_structure_identity
排序后的 branch_ids
merge_identity 或明确的 source_order 关系身份
first_atom_source_token
last_atom_source_token
segmenter_major_version
```

`IDENTITY-P0-01`：`sequence_index` 只用于排序，不得单独参与 Segment 身份。

`IDENTITY-P0-02`：不得使用构建扫描顺序、随机 UUID 或“第 N 个块”作为唯一身份。

`IDENTITY-P0-03`：相同输入、配置和 Atom 顺序必须逐字节生成相同 Segment。

`IDENTITY-P0-04`：来源 revision 或边界 Atom 改变时，Segment 身份必须改变；旧新身份由 fidelity 产物解释，不得静默覆盖。

## 9. 角色与剧情的来源支持关系

“某角色在剧情中做了什么”不能只搜索角色 Parent，也不能无条件放开到全语料。

Segment 可以保存 `mentioned_entity_ids`，但只接受：

- 结构化 speaker/actor/character ID；
- C 已发布的来源支持角色关系或 E0 通过精确注册表验证的结构化关系；
- 精确、已验证的角色别名到稳定 ID 映射。

`ENTITYLINK-P0-01`：不得用模糊 NER、标题相似度或 Dense 相似度生成角色到 Segment 的持久关系。

`ENTITYLINK-P0-02`：角色 Story 查询可增加一个受 `mentioned_entity_ids` 过滤的 Story Segment 补充分支；角色自身资料仍维持严格 Owner Gate。

`ENTITYLINK-P0-03`：缺少来源支持关系时不得把提到相似名称的 Story Segment 归属于该角色。

### 9.1 受控 Story 检索分支

不得把 Story Segment 直接塞入现有 `entity_strict` 或 `topic_strict` 结果，也不得放宽现有 Owner Gate。顶层知识任务新增受 Route Policy 授权的 `KnowledgeRetrievalBranch`：

```text
branch_id
branch_kind
query
authorization_status
authorization_reason
primary_entity_ref
planner_story_entity_refs
story_mention_detection
required_story_entity_refs
authorized_story_owner_ids
continuation_actions
allowed_retrieval_unit_types
story_filter
owner_policy
candidate_budget
context_budget
```

`authorization_status` 只允许 `proposed`、`authorized`、`denied`、`needs_continuation`。只有 Route Policy 能从 `proposed` 转换为后三种状态。

P0 冻结 `StoryBranchConfig/v1`：

```text
required_story_owner_limit = 3
planner_story_ref_limit = 32
story_owner_page_size = 3
mention_detector_name = exact_story_mention
mention_detector_version = 1
```

Planner、Detector 和 Policy 输出中的 Story 引用均使用 `StoryEntityRequestRef`：

```text
entity_ref
query_char_start
query_char_end
mention_text_sha256
resolution_kind       # exact_name | exact_alias | stable_id
entity_registry_identity
```

query span 按原问题 Unicode code point 半开区间计算；规范 mention 只能做与实体注册表相同的 Unicode/大小写规范化。

`story_mention_detection` 使用不可变 `StoryMentionDetectionReceipt/v1`：

```text
schema_version
detector_identity
query_sha256
entity_registry_identity
detection_complete
detected_story_count
detected_story_entity_refs
detected_story_refs_sha256
mention_occurrences
ambiguous_occurrences
overlap_conflicts
```

`detected_story_entity_refs` 是按原问题首次非冲突 span 排序、按 Story Owner 去重的完整数组；`mention_occurrences` 保留同一 Owner 的所有不同出现位置。receipt 不保存原问题正文，只保存规范 mention 哈希、span、resolution kind、稳定 Story ID 和诊断 reason code。

允许的 `branch_kind`：

| 分支 | 触发条件 | 过滤与所有权 |
|---|---|---|
| `primary_owner` | 现有非 Story 实体或 Topic 知识任务 | 保持 `entity_strict/topic_strict/corpus_topic` |
| `story_required` | 原问题明确点名 Story，包括跨 Story 比较 | 1～3 个时只检索获批 Owner 集合并保证配额；4～32 个时只生成继续动作 |
| `story_mentions` | 查询明确要求某角色在剧情中的行为/经历，且角色稳定 ID 已解析 | 只检索 `story_segment`，且 `mentioned_entity_ids` 精确包含角色 ID；存在显式 Story mention 时再与获批 Owner allowlist 取交集 |
| `story_examples` | Topic/Page 问题明确要求剧情例证、影响或出现位置 | 只检索 Story 域；存在显式 Story mention 时只消费获批 Owner allowlist；Topic/Page 主分支先满足定义配额 |

`STORYBRANCH-P0-01`：Planner 只能提出分支类型、查询和实体引用；Route Policy 必须根据任务意图、稳定实体解析、E0 能力和用户原问题作最终授权。

`STORYBRANCH-P0-02`：普通角色介绍、技能、语音、物品等查询不得自动开启 `story_mentions`。角色 Story 意图必须由原问题明确表达，不能由 Dense 命中反向授权。

`STORYBRANCH-P0-03`：`story_mentions` 必须通过精确 `mentioned_entity_ids` 过滤。没有结构化角色关系时返回覆盖 shortfall，不得退化为显示名模糊搜索后声称属于该角色。

`STORYBRANCH-P0-04`：`story_examples` 可以使用查询文本执行 Atom BM25 和 Segment Dense，但它是独立 Story 域分支；不得将 Story Owner 改写为 Topic Owner。

`STORYBRANCH-P0-05`：Topic/Page 主分支未获得有效定义证据时，Story 例证不得将整体检索标为 `sufficient`，也不得以剧情片段代替世界观定义。

`STORYBRANCH-P0-06`：每个分支独立记录候选、Owner、预算、shortfall、来源和失败状态；一个补充分支失败不吞掉已验证主分支。

`STORYBRANCH-P0-07`：补充分支仍是 grounded KB 路线，不获得 `llm_general` 权限，也不改变自由补充双开关的既有授权语义。

`STORYBRANCH-P0-08`：RequestPlan、Route Policy、Retriever、全局引用、REST/SSE 和会话记忆均须显式识别这些分支；只有 `primary_owner` 可以更新角色/Topic 会话锚点。单 Owner 的 `story_required` 可更新 Story 锚点，2～3 Owner 时不得选择一个伪单一锚点；Story 补充分支不能覆盖主实体锚点。

`STORYBRANCH-P0-09`：每个知识子任务最多包含一个主分支（`primary_owner` 或 `story_required`）和一个获批 Story 补充分支（`story_mentions` 或 `story_examples`）；分支 ID、顺序和授权原因必须确定性生成并进入 trace。

`STORYBRANCH-P0-10`：`planner_story_entity_refs` 是 Planner 的不可信提案，不是授权事实来源。它是从原问题提出的有序去重数组，最多 32 个；每个引用必须携带 `entity_type=story`、稳定 `entity_id`、规范名称和原问题 span。自由文本 Story 名不能直接进入该数组。

`STORYBRANCH-P0-11`：Route Policy 在处理每个知识子任务时，必须使用同版 E0 实体注册表和固定 `StoryMentionDetector/v1` 独立扫描原问题。Detector 不能读取 `planner_story_entity_refs`、Planner span、Planner 解析结果、会话锚点、BM25/Dense 命中或 LLM 输出作为候选提示。

`STORYBRANCH-P0-12`：Detector 必须枚举全部精确 Story 规范名、别名和稳定 ID 出现位置，而不是复用只返回最长单一 Owner 的 EntityLexicon `match/resolve` 接口。中文键按规范 Unicode 字符串精确匹配；ASCII、数字和内部 ID 还必须满足版本化标识符边界，避免把较长标识中的子串误判为独立 Story。

`STORYBRANCH-P0-13`：同一 span、同一 Owner 的重复 name/alias/ID 匹配按 `stable_id > exact_name > exact_alias` 选择一种规范表示；同一 Owner 的嵌套 span 选择来源支持的最长 span并保留其他 occurrence 证据。不同 Owner 的同 span或重叠 span、一个精确键映射多个 Owner、以及不能唯一归属的边界冲突必须记录歧义并令整个分支 `denied`。

`STORYBRANCH-P0-14`：Detector 必须扫描完整原问题后才写 `detection_complete=true`。`detected_story_count` 等于完整 Owner 去重数组长度；数组顺序固定为 `(query_char_start, query_char_end, entity_id)`，`detected_story_refs_sha256` 对规范数组字节取哈希。不得为了适配 32 个 Planner 上限而提前停止扫描、截断数组或把“至少 33 个”伪装成精确数量。

`STORYBRANCH-P0-15`：`story_required` 始终使用下表；`story_mentions/story_examples` 在 Detector 发现显式 Story scope 时也使用同一表，并把获批 Owner 作为附加过滤。任何未列组合均 `denied`，不得执行 Retriever。没有 Story mention 的普通非 Story 知识任务，以及没有显式 Story scope 的开放式 `story_mentions/story_examples`，继续按其原有分支授权，不套用本表：

| 检测与提案状态 | `authorization_status` | `authorization_reason` | Policy 输出 |
|---|---|---|---|
| 检测不完整 | `denied` | `story_mention_detection_incomplete` | required/authorized 为空 |
| `story_required` 检测为零，或任一 detected Story 无法唯一回查 Parent | `denied` | `story_owner_resolution_shortfall` | required/authorized 为空 |
| 歧义或不同 Owner span 冲突 | `denied` | `story_mention_ambiguous` | required/authorized 为空 |
| 检测 1～32 个，但 Planner 提案与检测数组不完全一致 | `denied` | `story_mention_set_mismatch` | required/authorized 为空 |
| 检测 1～3 个且提案完全一致 | `authorized` | `authorized_story_owner_set` | detected 同序复制为 required/authorized |
| 检测 4～32 个且提案完全一致 | `needs_continuation` | `too_many_required_story_owners` | required/authorized 为空，生成分页动作 |
| 检测超过 32 个 | `denied` | `narrow_story_scope` | required/authorized 为空，只生成 narrowing action |

`STORYBRANCH-P0-16`：1～32 个时，Planner 与 Detector 的“完全一致”要求数组长度、Owner ID、首次规范 span、mention hash、resolution kind、注册表 identity 和顺序逐项一致。遗漏、额外项、重复冲突或重排均是 `story_mention_set_mismatch`；Policy 不自动修正 Planner 后继续授权，也不得只授权双方交集。

`STORYBRANCH-P0-17`：Retriever 只能消费 `authorization_status=authorized` 的 `authorized_story_owner_ids`，并将它作为严格 allowlist。BM25、Dense 命中、Planner 自由文本、Detector 的未授权结果或上下文记忆均不能在 Route Policy 之后追加或替换 Story Owner。

`STORYBRANCH-P0-18`：显式 2～3 Story 查询保留为线程 A 定义的一个不可拆分 KB 任务、一个 `story_required` 主分支；不得拆成多个 subtask 后进行跨分支比较综合。`story_required` 只有在全部授权 Owner 至少获得一个可提交 Segment 时才能把比较覆盖标为完整。

`STORYBRANCH-P0-19`：显式请求 4～32 个 Story 时，P0 不创建 Composite 比较。Route Policy 只能从已完成且与 Planner 完全一致的 detected 数组生成每页最多 3 个 Owner 的确定性继续动作；初始分支不执行检索。单页结果必须标注范围，不得声称已完成跨全部 Story 的比较。

`STORYBRANCH-P0-20`：每个分页动作固定包含 `action_type=continue_story_owner_page`、原 query SHA-256、detected 数组顺序哈希、page index/count、最多 3 个 `StoryEntityRequestRef`、Detector identity 和 Route Policy identity；`action_id` 由这些规范字段哈希生成。用户触发后必须对原问题、检测回执、页面引用和当前注册表重新校验，不能直接获得 Retriever 权限。

`STORYBRANCH-P0-21`：检测超过 32 个时必须明确使用 `authorization_status=denied` 和 `authorization_reason=narrow_story_scope`。`narrow_story_scope` 不是第五种授权状态，也不能复用 `needs_continuation`；Policy 不比较被上限截断的 Planner 提案，也不生成任何 Owner 检索页。

`STORYBRANCH-P0-22`：narrowing action 固定包含 `action_type=narrow_story_scope`、原 query SHA-256、完整 detected count、detected 数组哈希、`planner_story_ref_limit=32`、`required_story_owner_limit=3`、Detector/Policy identity 和 `requires_new_user_query=true`。它不得自动挑选前 3/32 个 Story、携带 Retriever allowlist 或在点击后复用旧授权；用户必须提交收窄后的新问题。

`STORYBRANCH-P0-23`：字段闭包固定为：获批且具有显式 Story scope 的 Story-bearing 分支，其 planner/detected/required/authorized 四组同序且数量为 1 至 3；其中 `story_required.primary_entity_ref` 为空，`story_mentions/story_examples.primary_entity_ref` 保留其角色或 Topic/Page 引用。`needs_continuation` 的 planner/detected 为 4 至 32、required/authorized 为空且分页动作非空；`authorization_status=denied` 且 `authorization_reason=narrow_story_scope` 时 detected 大于 32、required/authorized 为空且仅有 narrowing action。开放式 `story_mentions/story_examples` 的四组 Story 数组为空。schema 验证失败时不得执行 Retriever。

`STORYBRANCH-P0-24`：`story_mention_detection` 对所有知识子任务运行。存在歧义或跨 Owner 重叠时，任何 Planner 分支形态都固定 `denied/story_mention_ambiguous`；明确检测到非歧义 Story 时，必须恰好有一个 Story-bearing 分支（`story_required`、`story_mentions` 或 `story_examples`）提交与 detected refs 完全一致的 Planner 提案。没有分支、多个分支竞争同一 scope 或任一分支只解释子集时，Route Policy 返回 `denied/story_scope_unaccounted`。Policy 不得仅凭 Detector 自动把非 Story 分支升级为 Story 检索权限。

`STORYBRANCH-P0-25`：Story 本身是主问题或需要跨 Story 比较时使用 `story_required`；角色经历问题使用 `primary_owner + story_mentions`，Topic/Page 剧情例证使用 `primary_owner + story_examples`。后两类存在显式 Story scope 时，补充分支必须同时满足角色/Topic 语义过滤和 `authorized_story_owner_ids`，不能降为无约束 Story 搜索，也不能把补充分支提升为跨 Owner 比较结论。

`STORYBRANCH-P0-26`：本节所有检测规范、边界规则、数量限制、状态机、分页算法和 action schema 均属于 `StoryBranchConfig/v1` 与 Detector identity；Planner、Route Policy、Retriever、前端、trace 和 provenance 必须读取同一版本化配置，禁止分别维护常量或匹配规则。

`STORYBRANCH-P0-27`：`needs_continuation`、`narrow_story_scope`、`story_mention_set_mismatch` 和 `story_scope_unaccounted` 均不属于检索 `empty`；它们产生确定性边界响应、`retrieval_outcome=not_applicable` 和适用的恢复 action，不得触发自由补充 empty fallback。

`STORYBRANCH-P0-28`：Route Policy 必须从 `query_char_start/end` 重新读取原问题 mention、验证 mention hash 与注册表 identity，并按 Detector 规范顺序比较；span 越界、hash 不符、Planner 顺序与 detected 顺序不一致或检测回执 query hash 不符时 fail-closed。

`STORYBRANCH-P0-29`：测试必须覆盖 Planner 遗漏第 1/中间/最后一个 Story、额外 Story、重排、重复、精确别名、同 Owner 多次出现、不同 Owner span 重叠、歧义键、2/3 Owner 配额、4/32 分页、33+ narrowing、分支整体遗漏、角色在指定 Story、Topic 在指定 Story、两个分支竞争同一 scope、动作重验、Retriever allowlist 和“Dense 命中不能扩充授权集合”。

`STORYBRANCH-P0-30`：Detector 单元测试必须使用包含长短名称、嵌套 alias、ASCII/数字边界和四个不同 Story 的注册表，证明它是完整多匹配扫描而非 longest-match 复用；真实评测必须记录 detected/Planner 一致率、拒绝 reason 分布和 Detector P95，不得只测试 Planner 给出完整数组的顺利路径。

## 10. 索引与产物

### 10.1 Atom BM25

- 保留 Story Atom 于 Child BM25。
- 使用线程 B 已批准的 Analyzer 与产物身份。
- Atom BM25 负责专名、数字实体、内部 ID、精确对白和来源词汇。
- Atom BM25 返回后立即映射到 `segment_id`。

### 10.2 Segment Dense

- Story Dense 只为 Segment 建向量。
- Story Atom 不进入新的 Dense candidate collection。
- 非 Story 的现有 Dense 记录保持原策略。
- Topic、Page 和其他需要语义检索的类型不得因 Story Dense 改造被删除。
- 线程 E 只生成版本化 embedding 输入、collection schema、构建适配器和测试证据。
- 完整语料的 embedding API 调用、影子 Milvus collection 创建和向量写入只由线程 D 在 E 合并后执行。

#### 10.2.1 Typed Dense Retrieval Unit

E 先生成不含向量值的 `rag_dense_retrieval_unit/v1` embedding 输入 JSONL，不再假设每一行都是 Child。冻结字段包括：

```text
retrieval_unit_id
retrieval_unit_type      # child | story_segment
text
child_id
segment_id
parent_id
entity_id
entity_name
entity_type
category
section_kind
title
depth_level
media_policy
media_ids
owner_entity_id
owner_page_id
ancestor_ids
quality_flags
route_tags
source_ref
chunk_index
segment_sequence_index
content_hash
artifact_identity
```

稳定 ID 规则：

```text
child row:         retrieval_unit_id = "child:" + child_id
story segment row: retrieval_unit_id = "story_segment:" + segment_id
```

线程 D 调用 embedding API 后，按一行输入对应一个向量的规则创建 `rag_dense_milvus_schema/v1`：

| 字段 | Milvus 类型 | 约束 |
|---|---|---|
| `retrieval_unit_id` | `VARCHAR(256)` | primary key，`auto_id=false` |
| `retrieval_unit_type` | `VARCHAR(32)` | `child` 或 `story_segment` |
| `embedding` | `FLOAT_VECTOR(1024)` | 本轮冻结的 BGE-M3 Dense 维度 |
| `text` | `VARCHAR(16384)` | 与 embedding 输入逐字节一致 |
| `child_id`、`segment_id`、`parent_id` | 各 `VARCHAR(256)` | ID 互斥规则见下文 |
| `entity_id` | `VARCHAR(256)` | 不用旧 `64` 长度限制解释新类型 |
| `entity_name`、`title` | 各 `VARCHAR(512)` | UTF-8 字符串 |
| `entity_type`、`category`、`section_kind` | 各 `VARCHAR(64)` | 枚举值 |
| `depth_level` | `INT64` | 非负 |
| `media_policy` | `VARCHAR(64)` | 保留非 Story Child 现有字段 |
| `media_ids` | `VARCHAR(4096)` | 规范 JSON 数组 |
| `owner_entity_id`、`owner_page_id` | 各 `VARCHAR(256)` | 不适用时为空字符串 |
| `ancestor_ids` | `VARCHAR(2048)` | 规范 JSON 数组 |
| `quality_flags`、`route_tags` | 各 `VARCHAR(1024)` | 规范 JSON 数组 |
| `source_ref` | `VARCHAR(16384)` | 规范 JSON source-ref 数组，可容纳一个 Segment 的 Atom 来源闭包 |
| `chunk_index`、`segment_sequence_index` | 各 `INT64` | 不适用时为 `-1` |
| `content_hash`、`artifact_identity` | 各 `VARCHAR(128)` | 小写十六进制身份 |

collection 固定 `enable_dynamic_field=false`、`consistency_level=Bounded`，向量索引固定 `AUTOINDEX + COSINE`。任何字段、长度、向量维度、索引或一致性级别变化都生成新的 schema 版本和新 collection，不能原地兼容。

`DENSEUNIT-P0-01`：`retrieval_unit_type=child` 时 `child_id` 必须非空、`segment_id` 必须为空；`retrieval_unit_type=story_segment` 时规则相反。违反互斥约束的行不得写入。

`DENSEUNIT-P0-02`：Story Atom 不允许以 `child` 行进入新 Dense collection；非 Story Child 继续使用 `child` 类型，Story Segment 使用 `story_segment` 类型。

`DENSEUNIT-P0-03`：不得把 `segment_id` 写入 `child_id`、把 Segment 构造成伪 Child，或依赖旧 `id -> child_id` fallback 反序列化新行。

`DENSEUNIT-P0-04`：查询反序列化返回显式 tagged union：`DenseChildHit` 或 `DenseStorySegmentHit`。两类命中只能经各自适配器进入现有 Child 融合或新的 Segment 融合。

`DENSEUNIT-P0-05`：Milvus schema、字段上限、必填/可空规则、类型计数、排序后的 `retrieval_unit_id` 哈希、embedding 输入哈希和业务字段哈希必须进入 provenance。

`DENSEUNIT-P0-06`：影子 collection 使用新的 schema/collection 身份；旧活动 collection 在 D 单独批准激活前保持只读，不做原地 schema 迁移。

`DENSEUNIT-P0-07`：构建器必须验证 `retrieval_unit_id` 全局唯一、类型与业务 ID 一致、Segment 行能够回查同版 Segment artifact，Child 行能够回查同版 Child artifact。

`DENSEUNIT-P0-08`：快照验证必须按类型比较期望行数和 ID 哈希；总行数相等但类型构成、ID 或 artifact identity 不同仍判定失败。

`DENSEUNIT-P0-09`：E 交付的 JSONL 不包含 `embedding` 字段。D 必须验证 API 返回向量数与输入行数一一相等、维度恰为 1024、值均为有限数，再按原始行序附加向量；不得跳行、补零或重新排序。

`DENSEUNIT-P0-10`：Child 行使用现有 `chunk_index` 并令 `segment_sequence_index=-1`；Story Segment 行使用 `segment_sequence_index` 并令 `chunk_index=-1`。不得让一个字段在两种 unit 中具有两套隐含语义。

`DENSEUNIT-P0-11`：写入前必须按最终规范 JSON 序列化验证所有 `VARCHAR` 边界，并用同版 Milvus 客户端完成最大边界、超界拒绝和查询反序列化 smoke test；不得沿用只适用于旧 Child schema 的字符长度检查器。

### 10.3 P0 不创建 Segment BM25

Segment BM25 只有在评测证明“多关键词跨 Atom 但 Dense 仍漏召回”时才进入后续设计。

`INDEX-P0-01`：Atom BM25 与 Segment Dense 使用不同的检索单元身份，不能按原始分数直接比较。

`INDEX-P0-02`：所有通道通过稳定 ID 和 RRF/归一化融合，不混用原始 BM25 与向量分数。

`INDEX-P0-03`：新 Dense collection 必须记录 embedding 模型、维度、Segmenter 身份、语料指纹和字段 schema。

`INDEX-P0-04`：线程 E 不得在真实完整语料上调用 embedding API 或创建 Milvus collection；E 的实现验证使用假向量、小型 fixture 或纯构建输入校验。

`INDEX-P0-05`：线程 D 在 E 合并后从固定提交与固定 embedding 输入创建新的影子 collection，不覆盖当前 active collection。

`INDEX-P0-06`：D 的真实向量构建输入只能是 E 已冻结的 `rag_dense_retrieval_unit/v1` JSONL；不得在 D 运行时重新拼接或改写 Child/Segment 行。

## 11. 查询执行链

P0 执行链：

```text
RequestPlan / KnowledgeRetrievalBranch
  │
  ├─ Structured Exact（现有）
  ├─ Atom BM25
  └─ Dense
       ├─ Story Segment
       └─ 现有非 Story 语义记录

Atom hits
  → atom_id 查 segment_id
  → 生成 Segment 级 evidence signals

Segment Dense hits + Atom-derived Segment signals
  → segment_id 去重
  → Story Owner 分组
  → 类型/Owner/细节覆盖预算
  → 相邻 Segment 扩展
  → 最终上下文封装
  → Atom 级引用
```

`PIPE-P0-01`：Reranker 调用路径仍存在但保持关闭；线程 E 不修改其默认开关。

`PIPE-P0-02`：Atom BM25 和 Segment Dense 必须各自执行通道内 Top-K；Atom 命中映射到 Segment 前，不得执行跨通道融合后的最终 Top-K、全局 source 截断或上下文预算裁切。

`PIPE-P0-03`：同一 Segment 同时被 Dense 和多个 Atom 命中时只保留一个 Segment 候选。

`PIPE-P0-04`：最终 packer 不接受独立 Story Atom source；Story Atom 只能作为所选 Segment 的组成与引用。

`PIPE-P0-05`：Dense 命中必须先按 `retrieval_unit_type` 分派；`child` 行继续进入现有 Child 路径，`story_segment` 行只进入 Segment 路径，未知类型 fail-closed。

`PIPE-P0-06`：`primary_owner`、`story_required`、`story_mentions` 和 `story_examples` 分支分别执行授权和过滤，再在预算层合并；不得先混合全部 Owner 后调用现有 Owner Gate。

`PIPE-P0-07`：同一知识子任务中，相同规范化 Dense query 与同一模型身份只能调用一次 query embedding API，向量在 Child/Story 过滤搜索间复用；每个子任务最多允许两个不同的 Dense query embedding，实际调用次数必须进入 trace 和延迟报告。

## 12. Segment 融合与打分

一个 Segment 的 evidence signals 至少包括：

```text
dense_rank
best_atom_rank
second_atom_rank
matched_atom_ids
exact_atom_match
matched_query_terms
matched_intents
```

P0 使用冻结的 `StoryFusionConfig/v1`：

```text
atom_bm25_k = 80
story_segment_dense_k = 30
rrf_k = 60
atom_weight = 1.2
dense_weight = 1.0
second_atom_factor = 0.25
second_segment_factor = 0.25
topic_page_candidate_reserve = 10
max_seed_segments = 8
```

单个 Segment 的信号：

```text
dense_signal =
  0                                      if dense_rank is absent
  dense_weight / (rrf_k + dense_rank)    otherwise

best_atom_signal =
  0                                      if best_atom_rank is absent
  atom_weight / (rrf_k + best_atom_rank) otherwise

second_atom_signal =
  0                                                if second_atom_rank is absent
  second_atom_factor * atom_weight
    / (rrf_k + second_atom_rank)                   otherwise

segment_score =
  max(dense_signal, best_atom_signal)
  + second_atom_signal
```

同一 Story 的 Owner 信号：

```text
story_score =
  best_segment_score
  + second_segment_factor * second_segment_score
```

精确 Atom、显式 Story、分支类型和 Topic/Page 保护不再作为未定义的浮点 bonus；它们通过“强制保留资格、Owner 配额和候选 reserve”实现。P0 不允许额外隐藏加分。

`FUSION-P0-01`：不得累加一个 Segment 中全部 Atom 分数。

`FUSION-P0-02`：最多使用排名最好的两个不同 Atom；第二个 Atom 贡献固定为 `second_atom_factor=0.25`，其余 Atom 只进入 matched evidence，不增加分数。

`FUSION-P0-03`：查询精确包含某 Atom 文本、稳定实体名或受保护标识时，其所属 Segment 获得保留资格。

`FUSION-P0-04`：同一文本出现在不同 Story 时不得按内容哈希跨 Story 去重。

`FUSION-P0-05`：rank 从 1 开始；缺失信号为 0；非有限数、零/负 rank、重复通道 rank 或未知 unit type 必须 fail-closed。

`FUSION-P0-06`：Segment 总排序固定为 `(-segment_score, story_entity_id, sequence_index, segment_id)`；Story 排序固定为 `(-story_score, story_entity_id)`。

`FUSION-P0-07`：精确 Atom 保留资格保证其所属 Segment 在预算前进入 seed 候选，但不能绕过 Story/Topic 配额、引用预算、Owner 授权或最终字符预算。

`FUSION-P0-08`：`StoryFusionConfig/v1` 的规范 JSON 和 SHA-256 必须写入 Segment runtime snapshot、影子报告和 provenance；任何参数变化均生成新评测身份。

`FUSION-P0-09`：实现测试必须使用完整给定 rank 表断言逐项分数和最终稳定顺序，不得只测试“某结果大致排在前面”。

## 13. 候选预算

首轮影子固定值：

```text
atom_bm25_k = 80
story_segment_dense_k = 30
topic_page_candidate_reserve = 10
max_seed_segments = 8
```

`CANDIDATE-P0-01`：这些数值是通道局部候选上限，不是最终上下文 source 数。

`CANDIDATE-P0-02`：精确 Atom 命中的所属 Segment 不因未进入 Dense Top-K 而丢失。

`CANDIDATE-P0-03`：Topic/Page 预留候选必须在 Story 填充全局候选前保留。

`CANDIDATE-P0-04`：本节数值仅复述 `StoryFusionConfig/v1` 的候选字段；runtime、测试和 provenance 必须读取同一份版本化配置，禁止再维护第二组常量。

## 14. Story Owner 与 Segment 分层预算

最终分配采用：

```text
全局意图预算
└─ Story Owner 预算
   └─ 每个 Story 的 Segment 预算
      └─ Atom 组成与引用
```

Story Owner 分数：

```text
story_score =
  best_segment_score
  + second_segment_factor * second_segment_score
```

不得累加一个 Story 的全部 Segment 分数。显式点名 Story 通过配额保证覆盖，不使用额外浮点 bonus。

`OWNERBUDGET-P0-01`：`story_required` 中经 Route Policy 授权的 1 至 3 个 Story 必须全部获得最小配额；候选排序不得替换或删除该集合。

`OWNERBUDGET-P0-02`：开放式推断查询最多自动选择 3 个 Story Owner。

`OWNERBUDGET-P0-03`：选择顺序先给每个需要覆盖的 Story 一个 Seed Segment，再轮询分配剩余 Segment。

`OWNERBUDGET-P0-04`：一个长 Story 不得在其他显式 Story 获得首个 Segment 前占用第二个 Segment。

`OWNERBUDGET-P0-05`：显式请求 4 个以上 Story 时只返回第 9.1 节定义的分页/继续动作；P0 不创建 Composite 比较，也不在一个排行榜中静默裁掉 Story。

## 15. 最终上下文预算

当前全局来源文本预算保持 9,000 字符。首轮策略：

| 查询类型 | Story Owner | Segment 上限 | Story 字符预算 | Topic/Page 保护 |
|---|---:|---:|---:|---|
| 精确对白/单点事实 | 1 | 1～2 | 2,500 | 按意图 |
| 单剧情经过/原因/关系 | 1 | 最多 6 | 6,000 | 保留其他请求意图 |
| 显式比较 2～3 个剧情 | 2～3 | 两个时每个 1～3；三个时每个 1～2；总计最多 6 | 6,000 | 按意图 |
| 开放式多剧情例证 | 最多 3 | 每个 1～2 | 5,000～6,000 | 按意图 |
| 世界观定义 + 剧情例证 | 最多 3 | 通常每个 1 | Story 最多 3,000 | 至少 2 条 Topic/Page |
| 复合问题 | 按分支 | Story 最多 4 | 不超过全局预算 60% | 每个其他意图先保留一条 |

`CONTEXTBUDGET-P0-01`：Segment 数量和字符数必须同时满足；只满足其中一个不能进入上下文。

`CONTEXTBUDGET-P0-02`：相邻 Segment 扩展计入总 Segment 数和字符预算。

`CONTEXTBUDGET-P0-03`：世界观定义问题先满足 Topic/Page 配额，再使用 Story 例证填充剩余预算。

`CONTEXTBUDGET-P0-04`：未用完的某类配额可以在所有强制覆盖完成后释放，但不得提前挤掉强制覆盖。

`CONTEXTBUDGET-P0-05`：最终选择必须同时满足 Story Owner、Segment、Story 字符、全局字符和 Atom citation 五类预算；任一预算超限均不得封装。

`CONTEXTBUDGET-P0-06`：预算器不得截断 Segment 内 Atom 或只移除其 citation；只能以整个 Segment 为单位替换、删除并报告对应 shortfall。

`CONTEXTBUDGET-P0-07`：非 Story Topic/Page/Child source 先占用其 citation source 名额；Story 最多使用剩余名额且不超过 `max_story_citation_atoms=72`。

`CONTEXTBUDGET-P0-08`：9,000 字符全局硬预算按最终渲染后的 Unicode code point 计数，包含 Story/Segment 标题、分隔符和 `[Sxx]` 标记；预算器必须在选择阶段计算确定性的渲染成本，禁止封装后再截断正文或引用。

## 16. 单剧情多细节

例如：

```text
谁启动装置、谁试图阻止，最后结果如何？
```

选择顺序：

1. 覆盖不同精确 Atom/关键词簇命中的 Segment。
2. 合并落入同一 Segment 的多个细节。
3. 不同 Segment 的细节锚点优先全部保留。
4. 细节覆盖完成后才扩展前后 Segment。
5. 最终按 Story 来源顺序排列。

`DETAIL-P0-01`：首期优先消费线程 A 已产生的独立知识子任务和查询词命中，不新增通用 LLM evidence-facet 协议。

`DETAIL-P0-02`：若同一知识任务仍包含多个相关细节，使用不同 Atom 锚点和 Segment 多样性选择，不能只返回最高分 Segment 的连续邻居。

`DETAIL-P1-01`：只有评测证明显式列举细节仍经常丢失时，才设计正式 `evidence_facets` 契约。

## 17. 多剧情封装

最终上下文和答案按 Story 分组：

```text
Story A
  Segment A1
  Segment A2

Story B
  Segment B1
```

每个 Story 内按来源顺序排列，不按检索完成顺序排列。

`MULTISTORY-P0-01`：不同 Story 的相同对白或内容不得跨 Owner 去重。

`MULTISTORY-P0-02`：引用必须同时保留 Story 身份、Segment 身份和 Atom 来源路径。

`MULTISTORY-P0-03`：一个 Story 分支失败不得吞掉其他 Story 的已验证证据，但响应必须报告覆盖缺口。

`MULTISTORY-P0-04`：显式比较的 Story 分组顺序使用 `required_story_entity_refs` 的原问题顺序，不按 Owner 分数、实体 ID 或检索完成顺序重排。

`MULTISTORY-P0-05`：比较回答只能综合当前 `story_required` 分支中全部获批 Owner 的可提交证据；分页继续动作产生的是范围受限的独立结果，不得跨页自动合并成 P0 比较结论。

## 18. 上下文关系

相邻扩展只允许：

- 同一 Story；
- 同一兼容分支；
- 显式 `prev/next` 或标记为 `source_order` 的邻接；
- 未跨越选择硬边界；
- 仍在 Segment 和字符预算内。

`RELATION-P0-01`：不得因位置相邻而推断因果。

`RELATION-P0-02`：因果类问题可以请求前后 Segment，但回答只能基于文本证据描述，不将邻接标签作为因果证据。

`RELATION-P0-03`：分支剧情使用 `next_segment_ids` 图关系，不强制线性化所有分支。

## 19. 质量标记安全策略

质量标记是元数据，不等于硬过滤。

P0 允许的处置：

| 类型 | 行为 |
|---|---|
| `diagnostic_only` | 记录但不改变排序 |
| `context_only` | 不独立竞争，但随 Segment 保留 |
| `deduplicate` | 仅同一来源身份且完全相同 payload |
| `invalid_source` | 来源损坏，保留诊断并阻止作为正文 |

`soft_penalty` 只保留为 P1 候选名称；P0 可以计算反事实排序，但 runtime 不得应用其分数。

`QUALITY-P0-01`：纯数字、短文本、单词、标点或异常名称形式不得成为硬过滤依据。

`QUALITY-P0-02`：`6`、`37` 等数字实体通过稳定实体字段和词典正常解析，不使用角色白名单补丁。

`QUALITY-P0-03`：反事实报告必须单列精确实体、别名、Atom 文本、结构化字段和受保护标识命中；这些记录在 P0 runtime 中不接受任何文本形态质量惩罚。

`QUALITY-P0-04`：只有结构化来源明确证明是控制事件时才能设为 `context_only`；仅凭“渐黑”“转场”等字符串启发式时首期只做诊断。

`QUALITY-P0-05`：短对白不得因 `short_text` 从 BM25 中删除。

`QUALITY-P0-06`：P0 不新增质量标记驱动的硬过滤；新标记先在影子报告中观察。

`QUALITY-P0-07`：`context_only`、`deduplicate` 和 `invalid_source` 只能由可验证结构/来源契约触发，不是质量模型打分结果；除这些结构动作外，P0 的质量标记不得改变召回、融合、配额或上下文顺序。

## 20. Coverage Shortfall

预算不足时不得静默丢弃显式 Story 或问题细节。调试与公共恢复动作至少区分：

```text
story_owner_shortfall
story_segment_shortfall
detail_coverage_shortfall
topic_page_shortfall
context_char_shortfall
citation_atom_shortfall
story_relation_shortfall
story_entity_link_shortfall
story_owner_resolution_shortfall
story_mention_detection_incomplete
story_mention_ambiguous
story_mention_set_mismatch
story_scope_unaccounted
too_many_required_story_owners
narrow_story_scope
```

`SHORTFALL-P0-01`：显式 Story 未覆盖时，回答必须说明未覆盖范围并提供继续/展开动作。

`SHORTFALL-P0-02`：世界观 Topic 配额未满足时，不得用大量 Story 例证伪装为完整定义答案。

`SHORTFALL-P0-03`：预算不足不是检索为空；两者必须使用不同 outcome。

## 21. 全章总结边界

“完整总结某章/整条剧情”需要枚举全部 Segment、分批摘要和最终合并，不属于普通 Top-K RAG。

`SUMMARY-P0-01`：P0 不通过扩大 Top-K 或上下文预算声称完整总结全章。

`SUMMARY-P0-02`：P0 可回答与查询最相关的剧情片段，但必须避免“完整覆盖”措辞。

`SUMMARY-P1-01`：全章摘要另立设计，采用确定性 Segment 枚举和分批生成。

## 22. 故障与回退

`FAILURE-P0-01`：Atom structure、Segment artifact、Atom 映射、Typed Dense collection、融合配置和 provenance 必须作为同一 runtime snapshot 验证。

`FAILURE-P0-02`：版本或哈希不一致时，新候选不得启动；保留上一活动版本，不在单次查询中混合新旧产物。

`FAILURE-P0-03`：Atom 命中但缺少 Segment 映射属于产物闭包错误，记录 blocker，不把 Atom 临时当成 Segment 正文。

`FAILURE-P0-04`：Dense 暂时不可用时，影子评测可以报告 Atom BM25-only 结果，但不得把该结果声称为新方案完整行为。

`FAILURE-P0-05`：Reranker 关闭状态不能被 Planner 或线程 E 动态绕过。

`FAILURE-P0-06`：Story 补充分支所需结构关系缺失时只关闭对应补充分支并报告 shortfall；不得放宽主 Owner Gate 或改用模糊实体关系。

`FAILURE-P0-07`：Atom span、Segment 正文或 Source Map 任一闭包不一致时，该上下文单元不得发送给模型。

`FAILURE-P0-08`：新 Dense 行缺失或携带未知 `retrieval_unit_type` 时视为 snapshot/schema 错误，不得按旧 Child fallback 解释。

## 23. 产物身份与 Provenance

Segment 和 Dense 产物身份至少包含：

- C 合并后的 Parent/Atom artifact 哈希；
- source snapshot 身份；
- Story structure taxonomy、结构配置和结构产物身份；
- Segmenter 名称、主版本和完整配置；
- Atom-to-Segment mapping 哈希；
- Story Segment JSONL 哈希和行数；
- SegmentContextUnit/AtomSpan schema 身份；
- StoryFusionConfig/v1 身份；
- `StoryBranchConfig/v1` 与 Story 分支授权策略身份；
- Story mention Detector、同版实体注册表和检测 receipt schema 身份；
- embedding 模型、维度和服务身份；
- Typed Dense collection schema、unit 类型计数和 index 参数；
- Analyzer/BM25 产物身份；
- 代码提交；
- 构建时间和 shadow run ID。

`PROVENANCE-P0-01`：Segmenter 配置变化必须生成新 Segment artifact 和 Dense collection。

`PROVENANCE-P0-02`：Atom 文本未变不代表 Segment Dense 可复用；Segment 边界或 search text 改变必须重建向量。

`PROVENANCE-P0-03`：线程 D 是唯一获准执行最终向量重建的线程。

`PROVENANCE-P0-04`：向量重建成功不自动授权生产激活。

`PROVENANCE-P0-05`：线程 E 交付的 embedding 输入必须有独立 schema、行数、顺序哈希和逐行稳定 ID；D 不得从未固定的运行时对象临时拼接全量重建输入。

`PROVENANCE-P0-06`：E0 结构解析规则、引用渲染规则、Dense typed-row 规则、融合常数或补充分支授权条件任一变化，均必须改变 runtime snapshot 身份并重新执行对应影子评测。

## 24. 性能预期与门槛

按每个 Segment 8～20 个 Atom 估算，约 142,200 个 Story Atom 将形成约 7,000～18,000 个 Segment。

预期：

- Story Dense 行数相对 Atom Dense 下降约 8～20 倍；
- Atom BM25 规模基本保持；
- 本地 `story_id/segment_id` 分组只处理有界候选；
- P0 不增加 reranker 网络调用；
- 查询主要新增成本是一次本地映射、聚合和有界展开。

`PERF-P0-01`：影子评测必须记录各阶段 P50/P95、候选数量、最终 Segment 数和字符使用。

`PERF-P0-02`：不得仅报告端到端平均延迟。

`PERF-P0-03`：Atom-to-Segment 聚合不得对全量 Atom 做查询时扫描，必须使用预建映射。

`PERF-P0-04`：在同一固定提交、机器、配置和查询集上，先运行当前活动系统 baseline，再运行候选；每个用例至少 1 次 warm-up 和 5 次计时，P95 使用所有正式重复样本。

`PERF-P0-05`：候选 retrieval P95 必须同时不超过 5,000 ms，且不超过：

```text
max(1.20 * baseline_retrieval_p95_ms,
    baseline_retrieval_p95_ms + 200 ms)
```

`PERF-P0-06`：新增的本地 Atom 映射、Segment 聚合、Owner 配额和 context packing 合计 P95 不得超过 100 ms；TTFT P95 仍不得超过 15,000 ms，总响应 P95 仍不得超过 45,000 ms。

`PERF-P0-07`：Story Segment 行数超过 25,000、任一查询时全量扫描 Story Atom/Segment，或新的影子 collection 落地后服务器预计剩余低于 12 GiB，均为 go/no-go blocker。

`PERF-P0-08`：容量估算必须同时包含旧活动 collection、新影子 collection、Milvus 索引/元数据和构建峰值临时空间；容量未知时不得执行真实向量构建。

## 25. 评测集

新增评测至少覆盖：

线程 D 在任何真实候选 embedding 构建前冻结 `eval/story_segment_eval.v1.jsonl` 和 `eval/story_segment_thresholds.v1.json`。评测集至少包含 60 个唯一人工复核用例：

| 分层 | 最少用例 |
|---|---:|
| 精确 Atom、数字实体、短对白和内部标识 | 12 |
| 单 Story 单点事实、首/中/末段 | 10 |
| 单 Story 多细节、原因/经过/关系 | 10 |
| 分支、choice、merge、cycle 或 terminal 边界 | 8 |
| 显式 2～3 Story 与开放式多 Story | 8 |
| Topic/Page 定义 + Story 例证 | 8 |
| 角色 Story mentions 与缺少精确关系的 shortfall | 4 |

每个用例冻结 query、查询类型、期望 Story Owner 集合及原问题顺序、来源支持的 `required_atom_groups`、必要 Topic/Page source、禁止 Owner、分支边界、允许 shortfall 和来源相关性等级。D0 不预写尚不存在的 Segment ID；E1 后使用冻结规则从 Atom-to-Segment mapping 派生 relevant Segment。标签不得在观察候选检索结果后修改；修订标签必须生成新评测版本并同时重跑 baseline。

### 25.1 精确性

- `6是谁？`
- `37有什么技能？`
- 精确短对白查询；
- 数字、内部 ID、专名和文件式标识；
- 同一句对白在不同 Story 中重复出现。

### 25.2 单剧情

- 一个 Story 的单点事实；
- 一个 Story 的多个细节；
- 原因、经过、关系；
- 命中首段、中段和末段；
- 分支前后不得错误串联。

### 25.3 多剧情

- 显式比较两个 Story；
- 开放式寻找多个剧情例证；
- 一个高频 Story 不得挤掉另一个显式 Story；
- 三个 Story 达到配额；
- 四个以上显式 Story 只触发确定性分页/继续动作，不创建 Composite 比较。
- Planner 在四个 Story 中遗漏首个、中间或末尾 Story时均被 Policy 拒绝；
- 33 个以上 Story 只产生非授权 narrowing action。

### 25.4 Topic 与 Story

- `暴雨是什么？`
- `暴雨在哪些剧情中造成了影响？`
- Topic/Page 定义优先，Story 作为例证；
- Story 数量不得淹没 Topic。

### 25.5 上下文

- Dense 与 Atom 同时命中同一 Segment，不重复正文；
- 相邻扩展不越过选择边界；
- 最终引用落到 Atom；
- coverage shortfall 可见。

`EVALSET-P0-01`：同一固定评测版本先对当前活动系统生成 baseline receipt；receipt 记录活动 Parent/Child/BM25/Milvus 身份、运行提交、配置、模型和逐用例结果哈希。

`EVALSET-P0-02`：当前 `rag_full_chain_thresholds.v1.json` 的全链评测继续执行；Story Segment 专用评测是新增门禁，不替代现有可靠性、路由和安全评测。

`EVALSET-P0-03`：不能从现有活动系统直接得到 Segment 标签不构成跳过理由；Segment/Atom gold 必须由冻结来源人工复核，baseline 只能按第 25.6 节的机器可执行规则记录活动系统是否实际返回等价 Atom 证据。

`EVALSET-P0-04`：D 必须在创建真实影子向量前提交评测集、阈值、baseline receipt 及其 SHA-256，防止根据候选表现移动门槛。

`EVALSET-P0-05`：一个 `required_atom_group` 被覆盖，当且仅当所选 Segment 至少包含该组一个 gold Atom；多细节用例包含多个独立 group，必须分别覆盖。relevant Segment ID 只能由固定 mapping 机械派生，禁止人工查看候选分数后补写。

### 25.6 Baseline 等价 Atom 证据

D0 生成 `story_baseline_atom_equivalence.v1.jsonl`。每个 gold Atom 先冻结：

```text
atom_id
source_title
source_revision_id
source_content_sha256
source_json_path
canonical_evidence_text_sha256
```

规范证据文本只执行 Unicode NFC 和 `CRLF/CR -> LF`；不折叠空白、不删除标点、不做分词、摘要或语义相似匹配。

“同一精确来源版本”定义为：`source_title` 相同，且双方非空 `source_content_sha256` 相同；只有活动 artifact 确实不保存内容哈希时，才允许双方非空 `source_revision_id` 相同作为替代。双方同时携带 revision 与哈希时两者都必须一致；字段缺失或互相冲突均不匹配。

旧活动结果覆盖某个 gold Atom 只允许以下规则，按顺序判定：

1. `exact_atom_identity`：活动结果已携带相同 `atom_id` 和规范内容哈希。
2. `exact_source_path`：活动结果 source ref 与 gold Atom 属于同一精确来源版本，且 `source_json_path` 和规范证据文本哈希全部一致。
3. `unique_exact_text_span`：活动结果与 gold Atom 属于同一精确来源版本，gold Atom 的规范证据文本在活动结果规范正文中恰好出现一次；receipt 必须记录 Unicode code point 半开 span 和匹配文本哈希。

第三条只证明旧结果正文实际包含该 Atom 证据，不把旧聚合 Child 自动等同于整个 Story。

`EVALSET-P0-06`：仅有同一 Story、同一 source title、Parent/Child migration link、`corrected_semantics` expansion group 或一对多候选集合，均不能自动算作覆盖任一或全部 Atom。

`EVALSET-P0-07`：`unique_exact_text_span` 出现零次或多次均不计覆盖；不得使用模糊子串、分词重叠、编辑距离、Dense 相似度、LLM 判断或“旧块足够大”推断。

`EVALSET-P0-08`：每条 baseline receipt 必须逐项记录 `query_id`、结果 rank、目标 `atom_id`、匹配规则、活动 source ref、目标 source ref、匹配 span、规范文本哈希和布尔结论；未匹配也必须记录确定性 reason code。

`EVALSET-P0-09`：`required_atom_group` 的 baseline 覆盖率只由其成员 Atom 的上述逐项匹配汇总，migration expansion group 本身不增加分子。

`EVALSET-P0-10`：等价匹配器、规范化配置、活动检索结果、gold Atom artifact 和 receipt 必须有 schema、代码提交与 SHA-256；这些身份在首次候选检索前冻结。

`EVALSET-P0-11`：测试必须覆盖精确路径命中、唯一 span 命中、重复文本歧义、source version 不同、仅 migration group、空 source ref 和规范化边界，确保 baseline 不能被一对多迁移高估。

`EVALSET-P0-12`：同一个活动结果文本 span 最多消费一次。若同一来源版本中多个 gold Atom 具有相同规范证据文本且活动结果缺少精确 path，相关 Atom 全部保持歧义，不得把一个唯一字符串位置重复计给多个目标。

`EVALSET-P0-13`：receipt 必须区分 `retrieval_at_k` 与 `final_context`。前者只读取对应 K 内、通过活动 snapshot 验证的检索 Child 正文与 source refs；后者只读取经过当前 packer/预算后实际发送给生成模型的 grounded source 文本及其真实可见 span。

`EVALSET-P0-14`：最终证据 Recall 只消费 `stage=final_context` 的匹配；未进入上下文或在最终渲染中不可见的旧 Child 内容不计覆盖。LLM 最终回答、Planner 重述、摘要文本或模型复述在任何阶段都不得作为 baseline Atom 覆盖证据。

## 26. 指标

至少记录：

- Atom BM25 Recall@K；
- Segment Dense Recall@K；
- 融合后 Segment Recall@K；
- 最终证据 Recall@K；
- MRR、nDCG；
- 显式 Story 覆盖率；
- 多细节覆盖率；
- Topic/Page 保留率；
- 重复上下文率；
- 引用到 Atom 的闭合率；
- context chars 与 Segment 数；
- P50/P95 延迟；
- Dense 行数和构建时间；
- quality flag 反事实排序变化；
- protected numeric/short-text query 零退化率。

`EVAL-P0-01`：质量标记影子报告必须给出“若启用惩罚会改变哪些结果”，P0 不以模型主观判断替代。

`EVAL-P0-02`：数字实体、短对白和精确标识不得相对当前可信基线退化。

`EVAL-P0-03`：完整章节总结不计入 P0 成功率。

### 26.1 Go/No-Go 阈值

候选必须同时满足下列硬门槛：

| 指标 | P0 通过阈值 |
|---|---:|
| 精确词汇子集 Atom BM25 Recall@80 | `>= 0.95` 且不低于 baseline |
| 语义剧情子集 Segment Dense Recall@30 | `>= 0.85` |
| 融合后 Segment Recall@8 | `>= 0.90` |
| 最终证据 Recall | `>= 0.90` 且不低于 baseline |
| 当前系统难以召回的中/末段子集最终证据 Recall 提升 | baseline `< 0.90` 时至少 `+0.10`；否则不退化 |
| 融合后 MRR、nDCG@8 | 各自不低于 baseline `-0.02` |
| 显式 1～3 Story Owner 覆盖率 | `1.00` |
| Required Story Owner 授权精确率 | `1.00` |
| Policy Story mention 检测完整率 | `1.00` |
| Planner 遗漏/额外/重排后错误授权次数 | `0` |
| Story mention 歧义或不完整检测后的 Retriever 调用次数 | `0` |
| 4+ Story 分页/继续动作正确率 | `1.00`，Composite 比较次数为 `0` |
| 单 Story 多细节覆盖率 | `>= 0.85` |
| Topic/Page 必要来源保留率 | `1.00` |
| Story 重复正文率 | `0` |
| Atom 引用闭合率 | `1.00` |
| 跨互斥分支错误扩展率 | `0` |
| Owner Gate 越权率 | `0` |
| 已发布角色关系精确率 | `1.00` |
| 可评测精确角色关系召回率 | `>= 0.90` |
| protected numeric/short-text/ID 查询不退化率 | `1.00` |
| Baseline 等价 Atom 错误计覆盖数 | `0` |
| 超长 Atom 映射、正文和引用闭合率 | `1.00` |
| 全链成功率 | `>= 0.98` |
| 每个知识子任务的 Dense query embedding API 调用 | `<= 2`，相同 query 不得重复调用 |
| Reranker API 调用次数 | `0` |

`GATE-P0-01`：任一硬门槛失败即 `no_go`；不得用其他指标平均分、人工主观印象或生成回答流畅度抵消。

`GATE-P0-02`：引用闭合、重复正文、分支越界、Owner 越权、Policy Story mention 完整检测、required Story 授权、baseline 等价证据误判、超长 Atom 闭合、protected 零退化、容量和 provenance 属于零容忍门槛。

`GATE-P0-03`：若 Segment Dense 未达阈值，允许保留 E 的代码与影子报告继续诊断，但不得重建为可激活候选，也不得临时开启 Reranker 掩盖问题。

`GATE-P0-04`：质量标记只有反事实报告，不参与本轮 go/no-go 排名；若未来启用软降权，必须生成新的阈值版本和独立评测。

`GATE-P0-05`：D 的验收报告必须逐项给出 numerator、denominator、baseline、candidate、delta、阈值和通过状态，禁止只给汇总“通过率”。

`GATE-P0-06`：通过影子 go/no-go 只允许进入“申请激活”阶段，不等于授权生产 collection 切换。

## 27. 线程与工作树

采用：

```text
线程 C
  → 完成 C8b/C8c/C8d/C9
  → 合并 main

线程 D
  → 编写并审核本 Spec
  → D0 扩展监督器以支持独立 E worker
  → 冻结 Story 评测集、阈值和当前活动 baseline
  → C 合并后创建线程 E worktree
  → 审核 E Plan 与阶段交付

线程 E
  → E0 Story structure taxonomy 与公共结构 sidecar
  → E1 Segment 构建、身份与上下文引用单元
  → E2 Atom BM25 / Segment Dense 输入、schema 与构建适配器
  → E3 受控 Story 分支、融合、Owner 配额与预算
  → E4 上下文、引用、短缺和 runtime 契约
  → E5 fixture、离线评测与 D handoff
  → 交付 D

线程 D
  → 合并 main
  → 固定 embedding 输入和模型身份
  → 一次性调用 embedding API 并创建影子向量 collection
  → 运行真实 Dense 与端到端影子验证
  → 单独申请激活
```

`THREAD-P0-01`：线程 C 不实施本功能，避免将 fidelity closure 扩大为运行时改造。

`THREAD-P0-02`：线程 D 不承担线程 E 的主要实现，以保持独立审核。

`THREAD-P0-03`：线程 E 从 C 已合并的 main 创建工作树，不读取 C worktree 数据。

`THREAD-P0-04`：Segment builder、索引、Runtime 融合和评测放在同一线程 E 内串行完成，避免跨线程生产者/消费者依赖。

`THREAD-P0-05`：E 使用 GPT-5.6 Sol 标准速度、Conda `1999wiki`，禁止创建子代理。

`THREAD-P0-06`：E 使用独立分支 `codex/rag-e-story-segment` 和工作树 `D:\1999Wiki.worktrees\rag-e-story-segment`；不得复用 C worker 名称、状态目录、日志、session 或工作树。

`THREAD-P0-07`：E 启动前，监督器的 `WorkerName`、配置解析、CLI choices、Start/Resume/Stop/Status/Inspect/Accept/Watch/Dashboard 和四个 PowerShell worker 脚本必须支持 E。

`THREAD-P0-08`：监督器测试必须证明 E 使用独立状态、event/stderr/session/lock 文件，关闭观察窗口不终止 worker，误中断后从原 session 恢复，且 A/B/C 兼容行为不变。

`THREAD-P0-09`：`running + pid=null` 不构成可信运行状态。D 在监督器完整记录 runner/worker PID、创建时间、最后心跳、最后输出和当前 run ID 前，继续使用 OS 进程与产物时间戳双重核验。

`THREAD-P0-10`：D0 监督器扩展和评测基线冻结必须在 E CLI 启动前完成；E 首个 turn 只能检查 Spec 并编写 Implementation Plan，Plan 经 D 和用户批准前不得实施。

`SUPERVISOR-P0-01`：监督配置升级为 `codex-supervisor/v2`，允许的 worker 集合固定为 `A/B/C/E`；配置必须包含 E 的独立 branch/worktree，不能把 E 映射到 C。

`SUPERVISOR-P0-02`：Python `WorkerName`、初始状态校验、配置闭包和 argparse choices，以及 PowerShell `ValidateSet` 必须来自同一受测 worker 集合，禁止多处手写列表再次漂移。

`SUPERVISOR-P0-03`：v2 继续按原路径读取 A/B/C 既有状态，但不得复制、重编号或写回迁移这些状态；E 必须使用独立目录并从空状态启动。

`SUPERVISOR-P0-04`：Python 定义唯一的 `SUPPORTED_WORKERS=("A","B","C","E")` 并提供机器可读 worker-list/validate 命令；四个 PowerShell worker 脚本、Dashboard 和窗口启动器必须调用该公共入口或共享验证 helper，不得各自保留 `ValidateSet("A","B","C","E")` 手写副本。

## 28. 阶段交付门禁

### D0：启动前置门

- 将监督器扩展为独立 E worker 并完成恢复/窗口测试；
- 冻结 `story_segment_eval.v1.jsonl`；
- 冻结 `story_segment_thresholds.v1.json`；
- 运行当前活动系统 baseline；
- 生成并验证 `story_baseline_atom_equivalence.v1.jsonl`；
- 提交评测、等价匹配器身份与 baseline receipt；
- 验证所有设计依赖已进入固定 `main` 提交，未跟踪 C 文档不得作为输入；
- 创建 E worktree；
- E 只编写 Plan，等待审核。

### E0：Story Structure

- 真实快照字段 taxonomy；
- step/choice/merge/cycle/terminal 语义验证；
- `story_atom_structure.v1.jsonl` 公共 schema；
- 每个 Atom 一条结构行；
- Atom 长度分布、超长计数和 `length_status`；
- 超长单 Atom/Dense limit 边界证据；
- 精确角色关系与未解析诊断；
- 显式图闭包、blocked Story 和 source-order fallback；
- 两次构建逐字节一致；
- 不修改规范 Atom。

### E1：Segment、Context Unit 与引用

- Segment 公共 schema；
- 确定性边界；
- Atom 完整覆盖；
- 分支关系；
- 稳定身份；
- `SegmentContextUnit + atom_spans`；
- Segment/Atom 双预算；
- Atom source map 与请求级引用渲染；
- 两次构建字节一致。

### E2：索引

- Atom BM25 保留；
- 版本化 Segment embedding 输入；
- Story Atom 从新 Dense 输入中排除；
- `rag_dense_retrieval_unit/v1` typed schema 与构建适配器；
- `child/story_segment` 反序列化；
- 假向量/小 fixture 集成测试；
- 非 Story Dense 不退化；
- provenance 闭合。

### E3：受控分支、融合与预算

- `primary_owner/story_required/story_mentions/story_examples` Route Policy 授权；
- Policy 自有 `StoryMentionDetector/v1`、完整检测回执和 Planner 提案一致性门禁；
- 1～3 个 required Story Owner allowlist；
- 4～32 Story 分页/继续动作、33+ narrowing action，且均不创建 Composite 比较；
- 现有 Owner Gate 保持严格；
- Atom-to-Segment 映射；
- Segment 去重；
- `StoryFusionConfig/v1` 精确公式与稳定排序；
- Story Owner 分组；
- 单/多 Story 配额；
- Topic/Page 保护；
- context budget 和 shortfall。

### E4：Runtime 上下文与公开契约

- Segment 一次封装；
- Atom span、Source Map 和引用；
- 顺序和分支；
- RequestPlan、Route Policy、Retriever、REST/SSE、记忆与 serializer；
- `continue_story_owner_page` 与非授权 `narrow_story_scope` 公共 action schema；旧 action 类型不得被静默重解释；
- 分支级失败隔离；
- coverage shortfall；
- 同步/流式响应一致。

### E5：离线评测与 D Handoff

- 质量标记影子报告；
- 使用假向量和冻结 gold 的离线问答集；
- 全部 Story 专用硬门槛中不依赖真实 Dense 的部分；
- 预测索引规模、构建输入和本地阶段性能报告；
- 固定 typed embedding JSONL、schema、顺序哈希和容量报告；
- 交给 D 执行的真实 Dense 评测清单。

每阶段由 D 独立复核后才能进入下一阶段。

## 29. 完成标准

线程 E 只有同时满足以下条件才可交付：

1. D0 已为监督器增加独立 E worker，启动、恢复、停止、观察窗口和日志隔离测试通过。
2. Story 专用评测集、阈值和当前活动 baseline 已在真实候选 embedding 前冻结并提交。
3. Baseline 等价匹配器和逐 Atom receipt 已冻结；一对多 migration group 未被自动计为覆盖。
4. 每个规范 Story Atom 恰好对应一条 E0 结构行；显式图零悬空，长度分布完整，结构异常 Story 明确阻断，规范 Atom 零修改。
5. 超过 800 字符的 Atom 只形成单 Atom Segment，`oversize_atom`、Dense limit 和上下文 shortfall 边界全部通过测试。
6. 每个可用规范 Story Atom 在本版映射中恰好属于一个 Segment。
7. Segment 构建确定、分支正确且来源闭合。
8. `SegmentContextUnit`、Atom spans、Segment/Atom 双预算和请求级引用逐项闭合。
9. Story Atom 不再进入 E 交付的新 Dense embedding 输入；D 创建的影子 collection 中也不得出现 Story Atom。
10. 新 Dense 行全部满足 typed retrieval-unit schema；Segment 不冒充 Child，类型计数和 ID 哈希正确。
11. Atom BM25 精确命中能稳定提升其所属 Segment，且通道内 Top-K 不被误当作跨通道最终截断。
12. Segment 与 Atom 不作为重复正文进入上下文。
13. `primary_owner/story_required/story_mentions/story_examples` 经 Route Policy 独立授权；Policy 自有 Detector 完整枚举原问题 Story，Planner 提案遗漏、额外、重排或歧义均不得进入 Retriever，现有 Owner Gate 未被放宽。
14. `StoryFusionConfig/v1` 常数、公式、tie-break 和 provenance 已冻结并通过精确数值测试。
15. 显式 1～3 个 Story 的授权集合、原问题顺序和覆盖配额有效。
16. 4～32 个显式 Story 只产生确定性分页/继续动作；33 个以上明确拒绝并产生非授权 narrowing action，不创建 Composite 比较或虚假完整结论。
17. 单 Story 多细节不会只保留一个局部邻接簇。
18. `暴雨是什么` 等 Topic 查询保留 Topic/Page 定义证据。
19. 数字实体、短对白、精确标识和角色关系评测达到零退化/精度门槛。
20. 重复正文、引用闭合、分支越界、Owner 越权和所有 go/no-go 指标达到第 26.1 节硬阈值。
21. Reranker 保持关闭且调用次数为零。
22. 影子产物不修改 active pointer。
23. E 的完整回归、fixture 和离线评测通过。
24. D 已审查 diff、产物身份、embedding 输入、容量报告和 baseline/candidate 逐项指标。
25. D 合并后执行的真实 Typed Dense 影子构建和端到端评测通过。
26. 激活仍停在独立 D 门禁。

## 30. 后续候选

只有 P0 稳定后才评估：

- P1：Segment BM25；
- P1：正式 evidence facets；
- P1：完整章节/整条剧情的分批摘要；
- P1：受评测支持的质量软降权；
- P2：条件式 reranker；
- P2：其他复杂语料恢复中间层。

这些候选不得在 P0 实施中以“顺便支持”为由提前加入。

## 31. 线程 D 审查闭环

线程 D 提出的七项阻断均已提升为 P0 前置契约，而不是留给 Implementation Plan 或实现阶段临时解释：

| 审查项 | 本 Spec 的闭环位置 | 实施前门禁 |
|---|---|---|
| Segment 输入条件不存在 | 第 5.1 节 `ATOMSTRUCT-P0-*`、第 7 节边界规则 | E0 必须先发布完整结构 sidecar；显式图异常的 Story 阻断，不允许退化为线性猜测 |
| Atom 级引用契约缺失 | 第 6.1 节 `CITATIONUNIT-P0-*` | `SegmentContextUnit + atom_spans`、Segment/Atom 双预算和公开响应契约先通过测试 |
| Dense collection 缺少混合记录契约 | 第 10.2 节 `DENSEUNIT-P0-*` | 新影子 collection 只消费 typed retrieval-unit JSONL；Segment 不得冒充 Child |
| 角色/Topic 的 Story 补充分支会被 Owner Gate 拦截 | 第 9.1 节 `STORYBRANCH-P0-*`、第 11 节 `PIPE-P0-*` | Route Policy 显式授权独立 KB 分支；原 Owner Gate 保持严格 |
| 融合公式和 Top-K 语义不确定 | 第 12 节 `FUSION-P0-*`、第 13 节 `CANDIDATE-P0-*` | 固定公式、常数、tie-break、通道局部 Top-K 和 provenance 数值测试 |
| 监督器不能管理 E | 第 27 节 `THREAD-P0-*`、`SUPERVISOR-P0-*` | D0 先扩展并验证独立 E worker，之后才允许启动 E CLI |
| 缺少上线 go/no-go 阈值 | 第 25、26 节 `EVALSET-P0-*`、`GATE-P0-*`、性能与容量门禁 | 真实 embedding 前冻结 gold、baseline 和阈值；任一硬门槛失败即 `no_go` |

`REVIEW-P0-01`：上述七项不是可延后的建议。D0 和 E0 未完成时不得开始 E1；E0 至 E5 任一阶段不得通过实现细节绕开对应前置契约。

`REVIEW-P0-02`：本次全量 P0 仍采用“先固定输入、身份、授权、预算和验收，再实现”的顺序。不得以兼容旧 schema、复用 `child_id`、放宽 Owner Gate、模糊角色映射、临时 reranker 或人工挑选评测样本来缩短落地路径。

### 31.1 第二轮重审闭环

| 重审项 | 本 Spec 的闭环位置 | 结果 |
|---|---|---|
| 多 Story 问题无法表达 | 第 9.1 节 `STORYBRANCH` 第 10～30 条、第 14/17 节 | 单个不可拆分 KB 任务携带 1～3 个授权 Story Owner；4～32 分页继续，33+ 要求收窄，不创建 Composite 比较 |
| Baseline 等价 Atom 未定义 | 第 25.6 节 `EVALSET` 第 6～14 条 | 只接受精确 Atom、精确路径或同版本唯一文本 span；migration group 本身不计覆盖 |
| 单个超长 Atom 无规则 | 第 5.1 节 `ATOMSTRUCT` 第 14～16 条、第 7 节 `BOUNDARY` 第 9～12 条 | 单 Atom 超长 Segment 是唯一 800 字符例外；Dense/上下文超限继续 fail-closed |
| Owner 公式重复常量 | 第 12/14 节 | 两处均引用唯一 `StoryFusionConfig/v1.second_segment_factor` |

`REVIEW-P0-03`：线程 A 的不可拆分跨实体比较规则保持不变；线程 E 只在线程 A 已保留的单个 KB 任务内部增加受授权 Story Owner 集合，不引入 P2 跨分支聚合。

`REVIEW-P0-04`：D0 未生成 baseline 等价 receipt，或 E0 未完成长度 taxonomy 与超长 Atom 边界测试时，不得启动真实候选 embedding 构建。

### 31.2 第三轮授权根因审查

线程 D 第三轮审查确认：仅逐项验证 Planner 提交的 Story 引用，无法证明 Planner 没有遗漏原问题中的其他 Story。第 9.1 节因此不再把 Planner 数组当作授权事实，而采用“Planner 提案 + Policy 独立完整检测 + 严格一致性门禁”。

| 审查项 | 根因修复 | 禁止的补丁式处理 |
|---|---|---|
| Planner 可遗漏第 4 个 Story 并绕过分页 | `StoryMentionDetector/v1` 独立枚举全部精确 Story，检测回执为 Policy 权威证据 | 不允许只检查 Planner 数量、只校验已提交项或自动授权交集 |
| 32 个上限之外状态不完整 | 检测仍完整运行；33+ 固定为 `denied/narrow_story_scope` 和非授权 narrowing action | 不新增第五种授权状态，不截断为前 32 个后继续检索 |
| 整个 Story-bearing 分支或其中部分 scope 可被 Planner 省略 | Detector 对所有知识子任务运行；显式 Story scope 必须由恰好一个 Story-bearing 分支完整解释 | Policy 不自动猜测语义并升级权限，也不允许多个分支各自消费 scope 子集 |

`REVIEW-P0-05`：Story 授权的单一事实来源是 Policy 生成的完整检测回执；Planner、Retriever、Dense 结果和会话记忆均不是 Story Owner 授权源。这个职责边界不得在 Implementation Plan 中降级为现有 EntityLexicon longest-match 的兼容调用。

`REVIEW-P0-06`：严格一致性可能把 Planner 漏报转化为可见拒绝，但这是可恢复的可用性代价，不是允许错误完整回答的理由。影子评测必须量化 mismatch 拒绝率；任何放宽只能通过新版本 Policy、独立评测和再次批准，不能按个别查询加入白名单。
