# Huiji RAG P1/P2 清理后内容缺口分析

日期：2026-07-20

## 1. 结论

P1 与 P2 已完成。RAG 运行时已经收束为 `huiji_crawler`，旧 Obsidian 处理链和持久数据候选已从生产路径与 MinIO 业务桶中移除。清理后的 MySQL、Milvus、`a-bucket` 与非计划 MinIO 对象均通过全量后验比对。

当前问答质量仍有明确的可迭代空间，但根因不再是 Obsidian 数据污染，而是 **RAG processed artifacts 停留在 2026-07-07，未消费 2026-07-18 已落地到 Wiki 的 crawler 语义投影**。这导致：

1. crawler 到版本化 RAG artifact 的正式重建入口缺失。
2. 角色单品和文化分区语义错位。
3. `collection_item`、`udimo`、`roster_avatar`、`skin_background` 尚未进入 RAG media artifact。
4. 传承、塑造和丰富角色资料已存在于 crawler/Wiki 投影，但不在当前 child blocks 中。
5. 查询规划器不识别“藏品”，也没有独立的“尤提姆”意图。

因此下一轮不应只调 K 值或在媒体分页层补规则。建议先恢复通用、可重复、版本化的 crawler artifact builder，再补语义分区、媒体角色和路由策略。

## 2. P1/P2 执行结果

### 2.1 P1 来源收束

- 运行时要求 `huiji.enabled=true` 且 `source_mode=huiji_crawler`。
- retriever 不再读取 `data/processed/documents.jsonl`，也不存在旧 vector adapter 或 entity packet fallback。
- chain 只构造 `HuijiMediaRegistry`。
- 旧 Obsidian 构建 CLI 与 asset registry 已移除。
- P1 保护面对比无变化。

### 2.2 P2 持久数据清理

动态集合公式：

```text
delete_candidates = remote ∩ legacy - active_rag - current_wiki - probes
```

执行结果：

| 项目 | 结果 |
|---|---:|
| 清理前 `reverse1999-assets` 对象 | 19,154 |
| 当前 Wiki 唯一对象 key | 16,481 |
| 当前 RAG 唯一对象 key | 15,383 |
| 精确删除的旧对象 | 1,291 |
| 保留的 residual orphan | 1,379 |
| 保留的 capability probe | 3 |
| 清理后业务桶对象 | 17,863 |
| 删除的本地旧路径 | 3 |
| MySQL mutation | 0 |

本地删除路径为：

```text
data/raw
data/processed/documents.jsonl
data/processed/assets.jsonl
```

1,291 个 MinIO 对象在删除前完成逐对象 SHA-1、SHA-256、size 校验和隔离下载，并写入 restic 快照 `fd249e9a5d2758ba8617c3d4e9b70fc9ad24bd894ce617625cb7e9c59fac31b6`。独立恢复测试覆盖全部 765,296,657 字节。

关键证据：

- operation plan SHA-256：`000b825bf878a0a2abc2d103d0a202c06f82953337248353685ba6259a84ccf5`
- apply receipt SHA-256：`78c8c647d1bc658e61980da531233565ea3b3f33a121eb87aedc8f7bf9095695`
- P2 acceptance SHA-256：`c6b8506879d4bee348cf515ea899541695bcb24f986782d4a92a6100ed5747e4`
- runtime final SHA-256：`f0775492f73b9f666aa1fc7e5a95eb82cd233ad858d87a3fd858559276b94a4f`

完整测试结果：`1069 passed, 1 skipped, 2 warnings`。pytest 退出码为 0。Windows 环境中的独立 import 探针退出时仍会打印既有的 `torch` DLL access violation 栈，不影响本轮断言结果，但应作为环境问题单独处理。

## 3. 清理后数据面

### 3.1 MySQL 页面

| page_type | 页面数 | 当前 RAG 文本覆盖 |
|---|---:|---|
| story | 6,413 | 已有 |
| item | 906 | 已有 |
| character | 132 | 部分，缺新结构化分区 |
| psychube | 5 | 已有，但覆盖量较低 |

MySQL 中 `obsidian_refs=0`，132 个 character 页面全部带 crawler projection 标记。`wiki_import_snapshots.source_mode=legacy` 是无 active pointer 时的 processed-artifact fallback 标签，不代表当前页面重新消费了 Obsidian；不过该标签语义容易误导，后续版本化构建应消除这一歧义。

### 3.2 当前 RAG artifacts

构建时间为 2026-07-07：

| artifact | 行数 |
|---|---:|
| parent blocks | 8,246 |
| child blocks | 16,010 |
| media rows | 15,758 |
| media 唯一 object key | 15,383 |

当前 child section：

| section_kind | 行数 |
|---|---:|
| profile | 7,456 |
| voice | 6,804 |
| culture | 813 |
| skill | 407 |
| item | 396 |
| dossier | 134 |

当前 media artifact 只有 `voice`、`portrait`、`image`、`skill` 四类，没有 `media_role` 维度。

### 3.3 Wiki 语义媒体与 RAG 差集

| Wiki media_role | 唯一 key | 已在 RAG | 未在 RAG | MinIO 缺失 |
|---|---:|---:|---:|---:|
| collection_item | 810 | 0 | 810 | 0 |
| udimo | 22 | 0 | 22 | 0 |
| roster_avatar | 129 | 0 | 129 | 0 |
| skin_background | 137 | 0 | 137 | 0 |
| stage_live2d | 280 | 280 | 0 | 0 |
| stage_portrait | 385 | 385 | 0 | 0 |
| portrait | 779 | 779 | 0 | 0 |
| image | 594 | 594 | 0 | 0 |
| skill | 396 | 396 | 0 | 0 |
| voice | 13,614 | 13,614 | 0 | 0 |

新增到 RAG 所需的 1,098 个唯一媒体 key 已全部存在于 MinIO，不需要再次上传，也不需要覆盖现有对象。

## 4. 已确认的链路缺口

### 4.1 P0：crawler artifact builder 源码在恢复过程中被替换

当前仓库没有 `scripts/build_huiji_corpus.py`，`src/huiji_rag.builder` 也没有可从 raw crawler snapshot 生成完整 parent/child/media/BM25 artifact 的生产入口。现有 `build_huiji_index.py` 只能对已存在的 child artifact 建 shadow collection，不能修复文本和媒体投影。

这不是“从未落地”。`scripts/__pycache__/build_huiji_corpus.cpython-312.pyc` 证明该 CLI 在 2026-07-05 已实际编译，入口会调用 `src.huiji_rag.builder.build_huiji_corpus` 并统计 parent、child、media 与 excluded 产物。2026-07-07 的恢复方案随后已将原 `src/huiji_rag/builder.py` 视为不在当前工作树，2026-07-11 的 EventName 语音绑定恢复方案又以 `Create` 方式在同一路径建立仅负责 EVB 隔离构建的 `EvbBuilder`。当前文件的创建时间和内容与这条时间线一致。

因此更准确的根因是：完整 corpus builder 在早期文件损失后没有被纳入 P0 恢复，后续 EVB 任务复用了同名模块路径，却没有恢复或合并原 `build_huiji_corpus` 能力；旧 CLI 源码也未回到工作树。P1/P2 的删除清单不包含这两个 crawler builder 文件。当前 active artifacts 可验证、可运行，但无法从同一 crawler snapshot 通用重现。

下一轮必须先恢复此入口，且只能读取：

```text
data/huiji/res1999/data_pages.jsonl
data/huiji/res1999/resources_manifest.jsonl
data/huiji/res1999/pages.jsonl
data/huiji/res1999/wikitext.jsonl
```

MySQL 只可作为独立验收投影，不能成为 RAG 第二来源。MinIO 只保存对象，不可由运行时扫描反推语义。

### 4.2 P0：单品与文化语义错位

以槲寄生为例：

- 真正单品：“1900橡木铃”“术杖‘他方世界’”“一束槲寄生”等 9 条，当前标为 `culture`。
- 真正文化内容：“咆哮的1920年代”“喀斯卡特的秋天”“她的世界”等 3 条，当前标为 `item`。

全库计数同样证明该问题是通用映射错误：

- crawler `collection` structured blocks：813。
- crawler `culture_dossier` structured blocks：396。
- 当前 RAG `culture` children：813。
- 当前 RAG `item` children：396。

因此不能通过交换 packet policy 临时掩盖。应在新 build 中生成正确的稳定 section ID，并提供旧 ID 到新 ID 的迁移/对比清单。

### 4.3 P0：单品图片未绑定到可召回 child

132 个角色中，collection image 分布为：

| 每角色图片数 | 角色数 |
|---:|---:|
| 0 | 1 |
| 3 | 29 |
| 6 | 69 |
| 9 | 29 |
| 12 | 4 |

共有 813 条单品 structured block，810 条有图片。3 条无图记录都属于维尔汀，应保留文本并允许 media 为空，不能因缺图丢弃文本。

### 4.4 P0：尤提姆缺角色级关系与路由

- 906 个 item 页面中有 42 个标题包含“尤提姆”。其中也包括背景、装饰和重复命名族，不能全部按角色关系处理。
- crawler 已证明 22 条 character profile 到 Udimo item 的明确映射，并为这 22 个角色提供 `udimo` image。
- 当前 RAG character children 中包含“尤提姆”的记录为 0。
- 当前独立 item children 能检索“尤提姆贴纸·槲寄生”等条目，但 character owner gate 会阻止它们满足“槲寄生的尤提姆”查询。

应由 crawler 构建期建立 `character_id -> udimo item -> optional media` 的显式关系，不应在 retriever 中按名称运行时猜测。

### 4.5 P1：传承与塑造内容未进入 child artifacts

Wiki crawler projection 已有：

- 132 个 inheritance heading/table 组。
- 132 个 portray heading/table 组。

Query planner 已把“传承”“塑造”路由到 skill intent，但 skill packet 目前只能召回 3 条主动技能/至终仪式。真实查询会返回主动技能，而不是传承或塑造效果。

### 4.6 P1：媒体角色已有语义，但 registry 仍按粗粒度 asset_type

Wiki 已能区分 `roster_avatar`、`stage_live2d`、`stage_portrait`、`skin_background`、`collection_item` 和 `udimo`。RAG media registry 仍把它们压成 `portrait` 或 `image`，所以“藏品图片”“尤提姆图片”等请求会返回普通立绘。

建议在 media artifact 中同时保留：

```text
asset_type = image / portrait / voice / skill
media_role = collection_item / udimo / roster_avatar / stage_live2d / ...
```

不要把 storage MIME 类别与展示/检索语义混成一个字段。

## 5. 当前真实召回复现

以下结果使用当前 artifacts、规则规划器、BM25/structured retrieval 和空 dense adapter，未调用最终 LLM：

| 查询 | 当前规划 | 当前结果 |
|---|---|---|
| `槲寄生的单品` | `item` | 返回“她的世界”“咆哮的1920年代”“喀斯卡特的秋天”，类别错误 |
| `看看槲寄生的藏品图片` | `media/image` | 只返回 profile source，媒体为普通 portrait/image |
| `槲寄生的尤提姆是什么` | `general` | 返回 profile/item/culture/skill/dossier 混合内容，无 Udimo relation |
| `展示槲寄生的尤提姆图片` | `media/image` | 返回普通立绘，不返回已存在的 Udimo object |
| `槲寄生的传承` | `skill` | 返回 3 条主动技能，无 inheritance table |
| `槲寄生的塑造` | `skill` | 返回 3 条主动技能，无 portray table |
| `颤颤之齿是什么` | `general/item entity` | 正确返回独立 item profile，但无媒体 |

## 6. 建议的下一轮范围

### P0 验收硬指标

1. 恢复 crawler-only、可重复、隔离输出的完整 artifact builder。
2. 生成新 build version，不覆盖 `dev`，不改 active pointer，不直接改 active Milvus。
3. 正确生成 `collection`、`culture_dossier`、`udimo` child 与显式 owner relation。
4. 将 810 个 collection image 和 22 个 Udimo image 绑定到对应 child；允许明确无图记录。
5. 增加 `藏品/收藏品` 到 item intent 词表，增加独立 Udimo 路由或等价的明确策略。
6. media artifact 增加 `media_role`，registry 按 role 过滤，禁止以文件名运行时猜测。
7. 重建 parent/child/media/BM25 与 provenance evidence，并输出旧/新 ID、section、媒体 key 差异报告。
8. 由用户执行 embedding 和 shadow Milvus build；本轮代码只交付可验证 artifact 与明确命令。
9. 用动态、分层抽样验收，不写死单一角色：覆盖 collection 数量为 0/3/6/9/12、Udimo 有图/无图、不同角色与独立 item 实体。
10. active 切换前必须证明旧 build、v3 collection、MySQL、MinIO 和 `a-bucket` 未漂移。

### P1

1. 将 inheritance/portray 建为可单独覆盖的 skill 子意图和 packet section。
2. 丰富 character profile 字段，保留可读标签，避免只输出职业/伤害类型数字 ID。
3. 使用 `roster_avatar`、`stage_live2d`、`stage_portrait`、`skin_background` 改善图片类请求的语义筛选。
4. 为 906 个独立 item 页面评估可证明的 item icon 关系；没有明确关系时不猜测。

### P2

1. 皮肤筛选和皮肤级媒体组合。
2. 5 个 psychube 页面覆盖率调查与扩充。
3. 1,379 个 residual orphan 的独立分类、备份与清理方案。
4. Windows `torch` DLL import probe 的环境稳定性修复。

## 7. 是否可以开始写 spec

可以。建议下一份 spec 聚焦“crawler-only RAG artifact rebuild + collection/Udimo semantic retrieval”，把构建链恢复和单品/尤提姆正确召回设为同一个 P0 闭环。传承/塑造和更细媒体筛选可以在同一设计中保留 schema 扩展点，但按 P1 实施，避免一次激活扩大过多变量。
