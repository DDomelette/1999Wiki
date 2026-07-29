# 线程 E：剧情 Segment 双粒度检索与预算设计

日期：2026-07-30

状态：设计方向已获用户批准；本文为用户复核候选，尚未授权实施

负责人：线程 E；规格、集成、向量重建与发布审核：线程 D

设计依赖：

- `docs/superpowers/specs/2026-07-04-character-entity-packet-routing-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-a-routing-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-b-chinese-bm25-analyzer-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-c-topic-story-media-projection-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md`
- `docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md`

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

`SCOPE-P0-01`：线程 E 只消费 C 合并后发布的公共 Atom/Parent/来源字段，不依赖 C worktree。

`SCOPE-P0-02`：本轮恢复的是剧情检索视图，不是全局核心数据模型重写。

`SCOPE-P0-03`：Reranker、Segment BM25 和全章摘要只能在独立评测与再次批准后进入后续阶段。

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

## 6. Story Segment 公共契约

建议新增独立 `story_segments.v1.jsonl`。每条 Segment 至少包含：

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
prev_segment_id
next_segment_ids
relation_kind
branch_id
heading_path
context_text
search_text
char_count
atom_count
mentioned_entity_ids
mentioned_entity_names
quality_flags
segmenter_identity
content_sha256
```

`SEGMENT-P0-01`：`ordered_atom_ids` 是 Segment 正文、顺序和引用的唯一规范来源。

`SEGMENT-P0-02`：`context_text` 由 Atom 可见正文按来源顺序确定性组成，不使用生成模型改写。

`SEGMENT-P0-03`：`search_text` 可以省略结构化确认的纯控制 Atom，但不能删除这些 Atom 与 Segment 的关系。

`SEGMENT-P0-04`：Story 标题、自然名和来源名在 Segment search text 中最多出现一次，不在每个 Atom 前重复。

`SEGMENT-P0-05`：Segment 不拥有独立于 Atom 的事实。删除 Segment 产物后必须能从同版 Atom 完整重建。

## 7. Segment 边界

Segment 边界按来源结构优先，不使用抽象主题推断。

边界优先级：

1. 显式 Story/scene/branch/choice 边界。
2. 结构化背景、场景或章节变化。
3. 跳转、分支进入和分支汇合。
4. 来源步骤连续顺序。
5. 达到长度硬上限后的 Atom 边界切分。

首轮构建参数建议：

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

`BOUNDARY-P0-05`：主线关系使用 `prev_segment_id/next_segment_ids`；分支允许一个 Segment 指向多个后继。

## 8. 稳定身份

`segment_id` 必须来自来源支持的边界证据，至少包括：

```text
story_entity_id
source_content_sha256
branch_id 或 branch fallback
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
- C 已发布的来源支持角色关系；
- 精确、已验证的角色别名到稳定 ID 映射。

`ENTITYLINK-P0-01`：不得用模糊 NER、标题相似度或 Dense 相似度生成角色到 Segment 的持久关系。

`ENTITYLINK-P0-02`：角色 Story 查询可增加一个受 `mentioned_entity_ids` 过滤的 Story Segment 补充分支；角色自身资料仍维持严格 Owner Gate。

`ENTITYLINK-P0-03`：缺少来源支持关系时不得把提到相似名称的 Story Segment 归属于该角色。

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

### 10.3 P0 不创建 Segment BM25

Segment BM25 只有在评测证明“多关键词跨 Atom 但 Dense 仍漏召回”时才进入后续设计。

`INDEX-P0-01`：Atom BM25 与 Segment Dense 使用不同的检索单元身份，不能按原始分数直接比较。

`INDEX-P0-02`：所有通道通过稳定 ID 和 RRF/归一化融合，不混用原始 BM25 与向量分数。

`INDEX-P0-03`：新 Dense collection 必须记录 embedding 模型、维度、Segmenter 身份、语料指纹和字段 schema。

`INDEX-P0-04`：线程 E 不得在真实完整语料上调用 embedding API 或创建 Milvus collection；E 的实现验证使用假向量、小型 fixture 或纯构建输入校验。

`INDEX-P0-05`：线程 D 在 E 合并后从固定提交与固定 embedding 输入创建新的影子 collection，不覆盖当前 active collection。

## 11. 查询执行链

P0 执行链：

```text
QueryPlan
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

`PIPE-P0-02`：全局 Top-K 不得在 Atom 映射到 Segment 之前执行。

`PIPE-P0-03`：同一 Segment 同时被 Dense 和多个 Atom 命中时只保留一个 Segment 候选。

`PIPE-P0-04`：最终 packer 不接受独立 Story Atom source；Story Atom 只能作为所选 Segment 的组成与引用。

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

P0 打分原则：

```text
segment_score =
  max(normalized_dense_signal, normalized_best_atom_signal)
  + capped_second_atom_contribution
  + exact_atom_match_bonus
  + approved_type/intent bonuses
```

`FUSION-P0-01`：不得累加一个 Segment 中全部 Atom 分数。

`FUSION-P0-02`：第二个 Atom 贡献必须有上限，防止 Atom 较多的 Segment 天然占优。

`FUSION-P0-03`：查询精确包含某 Atom 文本、稳定实体名或受保护标识时，其所属 Segment获得保留资格。

`FUSION-P0-04`：同一文本出现在不同 Story 时不得按内容哈希跨 Story 去重。

## 13. 候选预算

建议的首轮影子默认值：

```text
atom_bm25_k = 80
story_segment_dense_k = 30
topic_page_candidate_reserve = 10
max_seed_segments = 8
```

`CANDIDATE-P0-01`：这些数值是通道局部候选上限，不是最终上下文 source 数。

`CANDIDATE-P0-02`：精确 Atom 命中的所属 Segment 不因未进入 Dense Top-K 而丢失。

`CANDIDATE-P0-03`：Topic/Page 预留候选必须在 Story 填充全局候选前保留。

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
  best_segment_signal
  + capped_second_segment_contribution
  + explicit_story_match_bonus
```

不得累加一个 Story 的全部 Segment 分数。

`OWNERBUDGET-P0-01`：显式点名的 1 至 3 个 Story 必须全部获得最小配额。

`OWNERBUDGET-P0-02`：开放式推断查询最多自动选择 3 个 Story Owner。

`OWNERBUDGET-P0-03`：选择顺序先给每个需要覆盖的 Story 一个 Seed Segment，再轮询分配剩余 Segment。

`OWNERBUDGET-P0-04`：一个长 Story 不得在其他显式 Story 获得首个 Segment 前占用第二个 Segment。

`OWNERBUDGET-P0-05`：显式请求 4 个以上 Story 时，由 Composite 分支或分页恢复动作处理，不在一个排行榜中静默裁掉 Story。

## 15. 最终上下文预算

当前全局来源文本预算保持 9,000 字符。首轮策略：

| 查询类型 | Story Owner | Segment 上限 | Story 字符预算 | Topic/Page 保护 |
|---|---:|---:|---:|---|
| 精确对白/单点事实 | 1 | 1～2 | 2,500 | 按意图 |
| 单剧情经过/原因/关系 | 1 | 最多 6 | 6,000 | 保留其他请求意图 |
| 显式比较两个剧情 | 2 | 每个 1～3；总计最多 6 | 6,000 | 按意图 |
| 开放式多剧情例证 | 最多 3 | 每个 1～2 | 5,000～6,000 | 按意图 |
| 世界观定义 + 剧情例证 | 最多 3 | 通常每个 1 | Story 最多 3,000 | 至少 2 条 Topic/Page |
| 复合问题 | 按分支 | Story 最多 4 | 不超过全局预算 60% | 每个其他意图先保留一条 |

`CONTEXTBUDGET-P0-01`：Segment 数量和字符数必须同时满足；只满足其中一个不能进入上下文。

`CONTEXTBUDGET-P0-02`：相邻 Segment 扩展计入总 Segment 数和字符预算。

`CONTEXTBUDGET-P0-03`：世界观定义问题先满足 Topic/Page 配额，再使用 Story 例证填充剩余预算。

`CONTEXTBUDGET-P0-04`：未用完的某类配额可以在所有强制覆盖完成后释放，但不得提前挤掉强制覆盖。

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

P0 分类：

| 类型 | 行为 |
|---|---|
| `diagnostic_only` | 记录但不改变排序 |
| `soft_penalty` | 可逆轻微降权 |
| `context_only` | 不独立竞争，但随 Segment 保留 |
| `deduplicate` | 仅同一来源身份且完全相同 payload |
| `invalid_source` | 来源损坏，保留诊断并阻止作为正文 |

`QUALITY-P0-01`：纯数字、短文本、单词、标点或异常名称形式不得成为硬过滤依据。

`QUALITY-P0-02`：`6`、`37` 等数字实体通过稳定实体字段和词典正常解析，不使用角色白名单补丁。

`QUALITY-P0-03`：精确实体、别名、Atom 文本、结构化字段或受保护标识命中时，相关记录免除文本形态质量惩罚。

`QUALITY-P0-04`：只有结构化来源明确证明是控制事件时才能设为 `context_only`；仅凭“渐黑”“转场”等字符串启发式时首期只做诊断。

`QUALITY-P0-05`：短对白不得因 `short_text` 从 BM25 中删除。

`QUALITY-P0-06`：P0 不新增质量标记驱动的硬过滤；新标记先在影子报告中观察。

## 20. Coverage Shortfall

预算不足时不得静默丢弃显式 Story 或问题细节。调试与公共恢复动作至少区分：

```text
story_owner_shortfall
story_segment_shortfall
detail_coverage_shortfall
topic_page_shortfall
context_char_shortfall
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

`FAILURE-P0-01`：Segment artifact、Atom 映射、Dense collection 和 provenance 必须作为同一 runtime snapshot 验证。

`FAILURE-P0-02`：版本或哈希不一致时，新候选不得启动；保留上一活动版本，不在单次查询中混合新旧产物。

`FAILURE-P0-03`：Atom 命中但缺少 Segment 映射属于产物闭包错误，记录 blocker，不把 Atom 临时当成 Segment 正文。

`FAILURE-P0-04`：Dense 暂时不可用时，影子评测可以报告 Atom BM25-only 结果，但不得把该结果声称为新方案完整行为。

`FAILURE-P0-05`：Reranker 关闭状态不能被 Planner 或线程 E 动态绕过。

## 23. 产物身份与 Provenance

Segment 和 Dense 产物身份至少包含：

- C 合并后的 Parent/Atom artifact 哈希；
- source snapshot 身份；
- Segmenter 名称、主版本和完整配置；
- Atom-to-Segment mapping 哈希；
- Story Segment JSONL 哈希和行数；
- embedding 模型、维度和服务身份；
- Dense collection schema 和 index 参数；
- Analyzer/BM25 产物身份；
-代码提交；
- 构建时间和 shadow run ID。

`PROVENANCE-P0-01`：Segmenter 配置变化必须生成新 Segment artifact 和 Dense collection。

`PROVENANCE-P0-02`：Atom 文本未变不代表 Segment Dense 可复用；Segment 边界或 search text 改变必须重建向量。

`PROVENANCE-P0-03`：线程 D 是唯一获准执行最终向量重建的线程。

`PROVENANCE-P0-04`：向量重建成功不自动授权生产激活。

`PROVENANCE-P0-05`：线程 E 交付的 embedding 输入必须有独立 schema、行数、顺序哈希和逐行稳定 ID；D 不得从未固定的运行时对象临时拼接全量重建输入。

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

## 25. 评测集

新增评测至少覆盖：

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
- 四个以上显式 Story 触发 Composite/继续动作。

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

## 27. 线程与工作树

采用：

```text
线程 C
  → 完成 C8b/C8c/C8d/C9
  → 合并 main

线程 D
  → 编写并审核本 Spec
  → C 合并后创建线程 E worktree
  → 审核 E Plan 与阶段交付

线程 E
  → E1 Segment 构建与身份
  → E2 Atom BM25 / Segment Dense 输入、schema 与构建适配器
  → E3 融合、Owner 配额与预算
  → E4 上下文、引用、短缺和 fixture/离线评测
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

## 28. 阶段交付建议

### E1：Segment Artifact

- 公共 schema；
- 确定性边界；
- Atom 完整覆盖；
- 分支关系；
- 稳定身份；
- 两次构建字节一致。

### E2：索引

- Atom BM25 保留；
- 版本化 Segment embedding 输入；
- Story Atom 从新 Dense 输入中排除；
- Dense collection schema 与构建适配器；
- 假向量/小 fixture 集成测试；
- 非 Story Dense 不退化；
- provenance 闭合。

### E3：融合与预算

- Atom-to-Segment 映射；
- Segment 去重；
- Story Owner 分组；
- 单/多 Story 配额；
- Topic/Page 保护；
- context budget 和 shortfall。

### E4：上下文与评测

- Segment 一次封装；
- Atom 引用；
- 顺序和分支；
- 质量标记影子报告；
- fixture 与不调用真实 embedding API 的离线问答集；
- 预测索引规模、构建输入和本地阶段性能报告；
- 交给 D 执行的真实 Dense 评测清单。

每阶段由 D 独立复核后才能进入下一阶段。

## 29. 完成标准

线程 E 只有同时满足以下条件才可交付：

1. 每个规范 Story Atom 在本版映射中恰好属于一个 Segment。
2. Segment 构建确定且来源闭合。
3. Story Atom 不再进入 E 交付的新 Dense embedding 输入；D 创建的影子 collection 中也不得出现 Story Atom。
4. Atom BM25 精确命中能稳定提升其所属 Segment。
5. Segment 与 Atom 不作为重复正文进入上下文。
6. 显式 1～3 个 Story 的覆盖配额有效。
7. 单 Story 多细节不会只保留一个局部邻接簇。
8. `暴雨是什么` 等 Topic 查询保留 Topic/Page 定义证据。
9. 数字实体和短对白评测零退化。
10. Reranker 保持关闭。
11. 影子产物不修改 active pointer。
12. E 的完整回归、fixture 和离线评测通过。
13. D 已审查 diff、产物身份、embedding 输入和容量报告。
14. D 合并后执行的真实 Dense 影子构建和端到端评测通过。
15. 激活仍停在独立 D 门禁。

## 30. 后续候选

只有 P0 稳定后才评估：

- P1：Segment BM25；
- P1：正式 evidence facets；
- P1：完整章节/整条剧情的分批摘要；
- P1：受评测支持的质量软降权；
- P2：条件式 reranker；
- P2：其他复杂语料恢复中间层。

这些候选不得在 P0 实施中以“顺便支持”为由提前加入。
