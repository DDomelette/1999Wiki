# 灰机 RAG 闭环恢复与问答链路硬化设计

日期：2026-07-07

## 1. 背景与目标

项目文件曾发生大面积丢失，但 Docker MySQL、Milvus、MinIO 以及灰机处理产物仍然幸存。当前优先级已经调整为：先恢复并稳定 RAG 问答链路，Wiki 页面恢复暂停，后续 Wiki 只读兼容 RAG 侧确定的共享协议。

本设计是当前 RAG 问答系统的收口 specs，负责说明：

- 灰机爬虫数据进入 RAG 的数据边界。
- 父块、子块、实体包和媒体挂载的契约。
- `QueryPlan`、意图路由、混合召回、层级扩展和媒体返回的模块边界。
- MinIO 共享协议如何由 RAG 侧确定，并供 Wiki 后续只读消费。
- 什么时候只修运行时，什么时候允许重建处理产物、BM25 和 Milvus collection。

本设计不替代已有的父子块设计和角色实体包设计，而是在当前恢复阶段把它们整合为一条可执行、可验收的 RAG 闭环。

## 2. 总体架构

当前主链路如下：

```text
data/huiji/res1999
  -> data/processed/huiji/{build_version}
      -> parent_blocks.jsonl
      -> child_blocks.jsonl
      -> media_assets.jsonl
      -> indexes/child_text_bm25.json
      -> indexes/media_asset_bm25.json
      -> build_manifest.json / build_report.json / excluded_entities.jsonl
  -> Milvus text_child_bge_m3_*
  -> RAG runtime
      -> QueryPlan
      -> structured exact + BM25 + dense
      -> optional reranker
      -> ancestor expansion + bounded sibling expansion
      -> budget pruning
      -> answer + sources + media + actions
  -> FastAPI / SSE
  -> React chat UI
```

当前配置以 `text_child_bge_m3_v3` 为已存在参考 collection。若阶段性评估证明需要重建，新的候选 collection 使用 `text_child_bge_m3_v1`，并保留 `v3` 作为对照和回滚来源。

## 3. 数据源与处理产物

### 3.1 模块职责

灰机原始数据位于：

```text
D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999
```

处理产物位于：

```text
D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji\dev
```

这里的处理产物指由灰机爬虫数据清洗和结构化得到的 RAG 中间层，不是 MySQL，也不是 Milvus。它们是 BM25、Milvus、媒体 registry 和问答运行时共同依赖的数据契约。

### 3.2 P0 当前必须满足

- `DATA-P0-01`：RAG 当前主数据源必须是灰机爬虫数据和 `data/processed/huiji/{build_version}`，不是 Obsidian。
- `DATA-P0-02`：`parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl` 是 RAG 的核心处理产物，运行时不得绕过它们直接从原始文件拼临时数据。
- `DATA-P0-03`：`child_blocks.jsonl` 是 BM25 和 dense retrieval 的主要检索单元。
- `DATA-P0-04`：`media_assets.jsonl` 必须保存 `entity_id`、`entity_name`、`parent_id`、`child_id`、`asset_type`、`attach_policy`、`object_key`、`url` 等可挂载字段。
- `DATA-P0-05`：处理产物中的 URL 必须是浏览器可访问的 HTTP URL，不能把 `D:\`、`C:\` 或本地相对资源路径作为前端展示 URL。
- `DATA-P0-06`：`excluded_entities.jsonl` 或构建报告必须能追踪明显异常实体，例如空实体名和 `???`。

### 3.3 P1 可部分支持

- `DATA-P1-01`：如果评估证明父子块结构有缺陷，可重建 `parent_blocks.jsonl`、`child_blocks.jsonl` 和 BM25 索引。
- `DATA-P1-02`：重复媒体可在数据层加入 `canonical_asset_key`，按 `child_id + asset_type + normalized_stem` 去重。
- `DATA-P1-03`：资源下载或上传缺失时，应输出可排查报告，但不阻断非媒体文本问答。

### 3.4 P2 未来演进

- `DATA-P2-01`：增量构建处理产物。
- `DATA-P2-02`：以图片摘要、视觉标签和图片 embedding 扩展媒体资产索引。
- `DATA-P2-03`：支持从灰机数据反向重建 Obsidian 可视化库，但不进入当前问答系统。

### 3.5 关键契约与限制

原始爬虫目录只读。处理产物可以重建，但只有在评估证明运行时修复不足时才进入重建阶段。第一阶段不得盲目覆盖现有 `text_child_bge_m3_v3`。

## 4. 父块、子块与实体包

### 4.1 模块职责

实体包是运行时围绕一个实体组织的完整问答材料，不是一条单独向量记录。父块是实体包下的一级语义 section，子块是可检索、可排序、可挂媒体的最小业务单元。

角色实体包目标结构：

```text
entity_packet: char:{id}
  -> char:{id}/dossier
  -> char:{id}/profile
  -> char:{id}/skills
  -> char:{id}/items
  -> char:{id}/culture
  -> char:{id}/voice
  -> char:{id}/skins
  -> char:{id}/media
```

### 4.2 P0 当前必须满足

- `BLOCK-P0-01`：`intro` 类问题必须走角色实体包策略，不得只返回极薄 `profile` 子块。
- `BLOCK-P0-02`：父块至少通过 `parent_id`、`entity_id`、`entity_name`、`section_kind`、`child_ids` 与子块关联。
- `BLOCK-P0-03`：子块必须通过 `child_id`、`parent_id`、`entity_id`、`section_kind`、`title`、`text/search_text`、`media_ids` 或等价字段支持检索和媒体挂载。
- `BLOCK-P0-04`：技能子块应表达一个技能的完整语义。一二三星效果属于同一个技能子块；至终仪式可作为独立技能子块。
- `BLOCK-P0-05`：单品、文化、档案、语音等内容应拥有可定位的 section 或 parent，不得只漂移到泛化 story/item 数据。
- `BLOCK-P0-06`：当实体包内容超过回答预算时，被裁剪 section 必须转为 `omitted_actions`，供用户点击继续追问。

### 4.3 P1 可部分支持

- `BLOCK-P1-01`：如果现有处理产物缺少 `dossier/items/culture/voice/skins/media` 等父块，可在第二阶段补齐并重建。
- `BLOCK-P1-02`：子块可加入 `depth_level`、`source_refs`、`content_hash`、`quality_flags` 等字段提升调试能力。
- `BLOCK-P1-03`：可为心相、物品、剧情等非角色实体建立实体包，但第一版完整实体包只要求角色可用。

### 4.4 P2 未来演进

- `BLOCK-P2-01`：多层深度实体包循环检索。
- `BLOCK-P2-02`：LangGraph 节点循环式多轮 expansion。
- `BLOCK-P2-03`：角色关系图谱和跨实体证据链。

### 4.5 关键契约与限制

“拉父块”在本系统中不是只拉上一层。运行时可以从深层命中点向上扩展到父块和实体包，但必须受预算和 section policy 控制。

## 5. QueryPlan 与意图路由

### 5.1 模块职责

Stage 0 负责把用户原始问题转为结构化 `QueryPlan`。它不是简单问题重述，而是为 dense、BM25、媒体挂载、实体包策略和 fallback 行为生成多路信号。

### 5.2 P0 当前必须满足

- `QUERY-P0-01`：`QueryPlanner` 必须优先调用 LLM 输出 JSON 规划。
- `QUERY-P0-02`：只有 LLM 未配置、超时、API 错误、JSON 解析失败或 schema 校验失败时才允许 fallback。
- `QUERY-P0-03`：fallback 必须暴露 `planning_status`、`planning_warning`、`planning_error`，不得静默降级。
- `QUERY-P0-04`：`QueryPlan` 必须包含面向不同召回路的 `dense_query`、`sparse_query`、`media_query`。
- `QUERY-P0-05`：fallback 实体识别必须使用灰机实体词典做最长匹配和别名归一化，不能靠无限增加噪声词规则解决。
- `QUERY-P0-06`：意图集合必须覆盖 `intro`、`profile_fact`、`skill`、`item`、`culture`、`voice`、`media`、`video`、`psychube`、`story`、`general_game`、`meta_question`，并保留 `profile`、`lore` 兼容。
- `QUERY-P0-07`：当 Stage 0 给出 `general` 或低置信度结果时，稳健 Intent Router 必须结合用户问题关键词和召回到的 `heading_path/section_kind` 二次确认目标 section。

### 5.3 P1 可部分支持

- `QUERY-P1-01`：可选接入 `BAAI/bge-reranker-v2-m3` 作为候选子块精排，不替代 QueryPlan。
- `QUERY-P1-02`：可记录用户点击 `omitted_actions`、失败补救按钮和检索模式开关，用于未来训练意图分类器。
- `QUERY-P1-03`：当未找到合适内容时，可提示扩大范围重新搜索，而不是直接自由发挥。

### 5.4 P2 未来演进

- `QUERY-P2-01`：训练轻量 BERT/RoBERTa/MacBERT 多标签意图分类器，作为 Stage 0 的意图先验。
- `QUERY-P2-02`：多链路并行：严格 RAG、扩大范围 RAG、自由补充 LLM。
- `QUERY-P2-03`：复杂追问和跨实体问题的多轮规划。

### 5.5 关键契约与限制

LLM 规划成功时，即使置信度不高，也不得被本地 fallback 静默覆盖。fallback 是故障降级，不是默认规划路径。

## 6. 混合召回、精排与层级扩展

### 6.1 模块职责

检索层负责从结构化命中、BM25 和 dense embedding 中取回候选子块，融合排序后扩展上下文，并裁剪到 LLM 可用预算。

### 6.2 P0 当前必须满足

- `RETR-P0-01`：召回顺序必须是 `structured exact + BM25 + dense` 获取候选子块，再合并去重。
- `RETR-P0-02`：结构化精确命中主实体和目标 section 时，不得被 BM25 或 dense 的跨实体相似结果覆盖。
- `RETR-P0-03`：融合排序默认使用加权 RRF 或等价可解释融合方法，不直接相加不同量纲的原始分数。
- `RETR-P0-04`：可选 reranker 必须发生在 ancestor expansion 和 bounded sibling expansion 之前。
- `RETR-P0-05`：`intro` 必须返回多个角色 section，并把未进入预算的同实体 section 输出为 `omitted_actions`。
- `RETR-P0-06`：`item`、`voice`、`video` 等明确意图必须优先进入对应 section，不得被 `intro/profile/story` 抢占。
- `RETR-P0-07`：检索结果必须输出可调试信息，至少能说明命中实体、意图、候选来源、最终 sources 和裁剪原因。

### 6.3 P1 可部分支持

- `RETR-P1-01`：启用 `BAAI/bge-reranker-v2-m3` 前必须有开关、超时、限流和 fallback。
- `RETR-P1-02`：可引入 BGE-M3 sparse 作为第三路 sparse 召回，并通过评估集决定是否进入默认链路。
- `RETR-P1-03`：可加入更细的 section 权重和质量分。

### 6.4 P2 未来演进

- `RETR-P2-01`：Cross-Encoder 或 LLM reranker 只用于最终 top candidates 精排，不承担第一阶段召回。
- `RETR-P2-02`：多轮检索和自适应预算。

### 6.5 关键契约与限制

阶段 1 先修运行时链路，不强制重建 Milvus。只有当评估证明 `child_blocks`、`media_assets` 或 schema 本身有结构性问题时，才进入数据层重建。

## 7. MinIO 与媒体挂载

### 7.1 模块职责

RAG 侧主导 MinIO 共享协议。Wiki 暂停期间不得改写 MinIO；后续 Wiki 只读消费 RAG 确定的 `media_assets.jsonl`、`object_key` 和 HTTP URL。

当前共享协议：

```text
bucket: reverse1999-assets
public_base_url: http://127.0.0.1:9002
object_prefix: reverse1999
url: http://127.0.0.1:9002/reverse1999-assets/reverse1999/<asset_type>/<sha-prefix>/<sha>.<ext>
```

### 7.2 P0 当前必须满足

- `MEDIA-P0-01`：MinIO bucket、object prefix、object key 和 URL 规则由 RAG 侧固定。
- `MEDIA-P0-02`：RAG 和未来 Wiki 必须共享同一 MinIO bucket 和对象命名规则。
- `MEDIA-P0-03`：API 返回媒体只能使用 HTTP URL，不能泄露本地路径。
- `MEDIA-P0-04`：媒体挂载必须优先依赖最终保留 sources 的 `child_id/parent_id`，不能从全库按文件名随意拉图。
- `MEDIA-P0-05`：图片可随 `profile/media/skill/item` 等合适回答自动挂载；语音和视频默认只在明确 intent、按钮触发或用户明确提问时返回。
- `MEDIA-P0-06`：`voice` 返回 voice panel 数据，`video` 返回 video panel 数据，不与普通图片卡片混在同一展示结构。
- `MEDIA-P0-07`：非 voice intent 不得自动泄露大批语音；非 video intent 不得自动泄露视频。
- `MEDIA-P0-08`：MinIO 可访问性必须能被抽样验证，失败时不应导致纯文本回答崩溃。

### 7.3 P1 可部分支持

- `MEDIA-P1-01`：返回阶段可按 `canonical_asset_key` 做保险去重，避免同一视觉资源的 `.png/.webp` 同时展示。
- `MEDIA-P1-02`：数据层可在生成 `media_assets.jsonl` 时按 `child_id + asset_type + normalized_stem` 去重，优先级为 `webp > png > jpg/jpeg > gif`。
- `MEDIA-P1-03`：可为语音按语言、皮肤和台词类别分组。

### 7.4 P2 未来演进

- `MEDIA-P2-01`：图片摘要向量库 `asset_caption_bge_m3_v1`。
- `MEDIA-P2-02`：CDN、私有 bucket、预签名 URL。
- `MEDIA-P2-03`：媒体中心和资源管理 UI。

### 7.5 关键契约与限制

原始资源文件不删除。重复媒体去重第一阶段不作为硬验收，先保证媒体跟随正确文本 sources。

## 8. 后端问答输出契约

### 8.1 模块职责

后端负责把 RAG 检索、LLM 回答、sources、media、omitted actions、failure actions 和 planning diagnostics 通过普通接口或 SSE 传给前端。

### 8.2 P0 当前必须满足

- `API-P0-01`：回答 payload 必须包含 `answer`、`sources`、`media`、`omitted_actions`、`failure_actions` 或等价字段。
- `API-P0-02`：payload 必须包含 `planning_status` 或可被前端展示/日志记录的降级信息。
- `API-P0-03`：`sources` 必须保留实体、parent、child、section、title 等足以调试的字段。
- `API-P0-04`：`media` 必须包含 `url`、`asset_type`、`title`、`child_id/parent_id`、`attach_policy` 或等价字段。
- `API-P0-05`：`failure_actions` 只在没有有效 sources 时返回。
- `API-P0-06`：API 和 SSE 均不得输出本地资源路径。

### 8.3 P1 可部分支持

- `API-P1-01`：可输出更完整的 ranking debug，例如 BM25 rank、dense rank、RRF score、reranker score。
- `API-P1-02`：可输出 Wiki route resolve 所需的稳定字段，但 Wiki 跳转不是当前 RAG P0。

### 8.4 P2 未来演进

- `API-P2-01`：回答内嵌来源卡片。
- `API-P2-02`：跳转到 Wiki 指定段落。

### 8.5 关键契约与限制

后端不得为了让前端能显示图片而直接暴露本地文件路径。浏览器只接收 HTTP URL。

## 9. 聊天前端

### 9.1 模块职责

聊天前端负责展示 RAG 输出，包括 Markdown 兼容文本、媒体、voice/video panel、常驻检索模式按钮和失败后的补救动作。

### 9.2 P0 当前必须满足

- `CHAT-P0-01`：聊天窗口兼容 Markdown，但不得强制后端必须返回 Markdown。
- `CHAT-P0-02`：输入框底部常驻按钮默认关闭，至少包含 `扩大检索` 和 `自由补充` 两个互相解耦的状态。
- `CHAT-P0-03`：失败后的临时补救按钮名称为 `扩大范围重新搜索` 和 `使用自由补充重答`，样式应区别于常驻按钮。
- `CHAT-P0-04`：`omitted_actions` 必须以按钮形式展示，点击后触发规范化追问。
- `CHAT-P0-05`：voice panel 是独立组件，每条台词可点击播放，播放进度使用背景层表现，并预留文字动效挂点。
- `CHAT-P0-06`：video panel 是独立组件，不混入普通 image grid。
- `CHAT-P0-07`：`MessageBubble` 的外壳、正文、媒体和 actions 分层，保留动画挂点，同时不得造成明显流式闪烁。

### 9.3 P1 可部分支持

- `CHAT-P1-01`：语音按语言和皮肤分组。
- `CHAT-P1-02`：视频分组、折叠和预览图。
- `CHAT-P1-03`：自由补充和扩大检索可作为请求参数进入后端路由。

### 9.4 P2 未来演进

- `CHAT-P2-01`：复杂消息动效。
- `CHAT-P2-02`：多链路并行结果并排展示。

### 9.5 关键契约与限制

聊天前端属于 RAG 问答链路。本轮可修改 `frontend/react-app/src/components/chat/**`、`frontend/react-app/src/api/sse.ts`、`frontend/react-app/src/types/index.ts`、`frontend/react-app/src/store/chatStore.ts`。Wiki 页面组件不属于本 specs 的执行范围。

## 10. 评估与重建门槛

### 10.1 模块职责

评估层负责判断问题来自运行时还是数据层。只有评估证明处理产物或 Milvus 结构阻碍效果时，才进入重建阶段。

### 10.2 P0 当前必须满足

- `EVAL-P0-01`：必须创建核心 query 评估集，覆盖角色介绍、技能、单品、立绘、语音、通用游戏问题和异常召回。
- `EVAL-P0-02`：评估输出必须包含 `planning_status`、`entity`、`intent`、`dense_query`、`sparse_query`、top sources、media count、omitted actions、failure actions。
- `EVAL-P0-03`：必须检查本地路径泄露、未知实体泄露、语音自动泄露和错误媒体挂载。
- `EVAL-P0-04`：阶段 1 完成后，必须用当前 `text_child_bge_m3_v3` 和现有处理产物跑评估。
- `EVAL-P0-05`：只有当评估证明数据层结构性问题存在时，才允许进入父子块、media_assets、BM25 和 Milvus 重建。

### 10.3 P1 可部分支持

- `EVAL-P1-01`：可设硬阈值，例如 Entity Accuracy、Intent Accuracy、Parent Recall@5、Voice Auto Leak Rate、Local Path Leakage。
- `EVAL-P1-02`：可记录每条失败样本的预期、实际、top sources 和媒体结果。

### 10.4 P2 未来演进

- `EVAL-P2-01`：自动化 A/B 比较 `v3`、`v1`、reranker on/off、BGE-M3 sparse on/off。
- `EVAL-P2-02`：用户点击日志回流为训练集。

### 10.5 关键契约与限制

不能只用单测通过宣称 RAG 修复完成。至少需要一组真实 processed artifacts + Milvus + MinIO 的评估结果。

## 11. Milvus collection 策略

### 11.1 模块职责

Milvus 存储 dense embedding。当前重点是保护已有参考 collection，同时允许在必要时建立新的候选运行 collection。

### 11.2 P0 当前必须满足

- `MILVUS-P0-01`：当前 `text_child_bge_m3_v3` 必须保留，作为参考和回滚来源。
- `MILVUS-P0-02`：阶段 1 不重建 Milvus，除非运行时无法评估。
- `MILVUS-P0-03`：若进入重建阶段，目标 collection 使用 `text_child_bge_m3_v1`。
- `MILVUS-P0-04`：如果旧 `text_child_bge_m3_v1` 已存在，允许先删除后重建。
- `MILVUS-P0-05`：如果 `v1` 评估优于 `v3`，允许把运行配置切换到 `text_child_bge_m3_v1`。

### 11.3 P1 可部分支持

- `MILVUS-P1-01`：保留 `v3` 与 `v1` 的 schema 对照报告。
- `MILVUS-P1-02`：构建脚本输出插入数量、字段长度异常、load 状态和失败记录。

### 11.4 P2 未来演进

- `MILVUS-P2-01`：以构建版本号命名 collection，例如 `text_child_bge_m3_YYYYMMDD`.
- `MILVUS-P2-02`：自动化 collection 切换和回滚脚本。

### 11.5 关键契约与限制

重建 Milvus 不等于清空 MinIO，也不等于重爬灰机数据。向量库重建只处理 text child embedding。

## 12. 与 Wiki、Obsidian 和旧方案的关系

### 12.1 模块职责

本模块定义当前 RAG 工作与其他历史或暂停模块的边界。

### 12.2 P0 当前必须满足

- `BOUNDARY-P0-01`：Wiki 页面恢复暂停，不作为当前 RAG 修复的并行约束。
- `BOUNDARY-P0-02`：Wiki 后续只读消费 RAG 侧固定的 MinIO bucket、object key、URL 和资源清单契约。
- `BOUNDARY-P0-03`：Obsidian 适配接口可以保留，但当前不进入问答索引、BM25、Milvus、媒体挂载、RAG API 或聊天前端。
- `BOUNDARY-P0-04`：旧 `data/processed/documents.jsonl`、`chunks_bge_m3_v1` 和旧 Obsidian MinIO 方案只作为历史参考，不作为当前主链路。
- `BOUNDARY-P0-05`：不恢复旧 `src/huiji_rag/builder.py` 文件名作为本轮 P0；如果需要异常记录，应落到当前实际构建入口或处理模块。

### 12.3 P1 可部分支持

- `BOUNDARY-P1-01`：RAG sources 后续可提供 Wiki route resolve 所需字段。
- `BOUNDARY-P1-02`：Wiki 可以复用 RAG 的媒体 URL，但不得覆盖 RAG 的 MinIO 对象。

### 12.4 P2 未来演进

- `BOUNDARY-P2-01`：RAG 与 Wiki 互相跳转到具体段落。
- `BOUNDARY-P2-02`：灰机数据重建为 Obsidian 本地可视化数据库。

### 12.5 关键契约与限制

当前系统以 RAG 问答效果为最高优先级。Wiki 的恢复不能反向要求 RAG 改动已固定的媒体协议。

## 13. 跨模块数据流

```text
User Query
  -> QueryPlanner
      -> QueryPlan(dense_query, sparse_query, media_query, intent, entity, planning_status)
  -> EntityLexicon / Intent Router
  -> structured exact candidates
  -> BM25 candidates
  -> dense candidates from Milvus
  -> merge + weighted RRF
  -> optional reranker
  -> ancestor expansion
  -> bounded sibling expansion
  -> budget pruning
  -> selected sources
  -> HuijiMediaRegistry(child_id/parent_id)
  -> answer generation
  -> payload(answer, sources, media, omitted_actions, failure_actions, planning diagnostics)
  -> SSE / API
  -> Chat UI
```

## 14. 错误处理原则

- LLM 规划错误必须显式降级并记录状态。
- MinIO 单个媒体不可访问时，不阻断文本回答。
- 查询没有可靠 sources 时，返回 `failure_actions`，不默认自由发挥。
- 异常实体、公共素材泄露、语音自动泄露和本地路径泄露都必须进入评估检查。
- 处理产物重建失败不得覆盖可回滚的 `v3` collection。

## 15. 测试与验收方向

测试分三层：

1. 单元测试：`QueryPlan`、EntityLexicon、Intent Router、RRF、layered expansion、media registry、chat actions。
2. 集成测试：RAG chain 输出 `sources/media/omitted_actions/failure_actions/planning_status`。
3. 真实数据评估：使用当前 `data/processed/huiji/dev`、MinIO 和 Milvus collection 跑核心 query。

最小验收方向：

- 角色介绍不再只返回极薄 profile。
- 技能、单品、语音、视频问题能进入对应 section。
- 图片、语音、视频只随正确 sources 返回。
- API 和前端不出现本地路径。
- `text_child_bge_m3_v3` 保留；如果重建 `v1`，必须评估后再切换。

## 16. 与现有 plan 的关系

本 specs 是 `2026-07-07-huiji-rag-planning-fallback-hardening.md` 的上层设计来源。该 plan 应按本 specs 调整：

- 不再把 Wiki 并行作为限制。
- 将 MinIO 共享协议明确为 RAG 主导。
- 将 `src/huiji_rag/builder.py` 从 P0 文件要求中移除，改为“当前实际构建入口或处理模块”。
- 将重复媒体去重降级为 P1，第一阶段不作为硬验收。
- 将 Milvus 重建策略改为保留 `text_child_bge_m3_v3`，必要时重建 `text_child_bge_m3_v1`。

