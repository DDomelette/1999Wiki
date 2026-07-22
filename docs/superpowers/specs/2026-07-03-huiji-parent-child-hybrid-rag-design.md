# 灰机爬虫数据父子块混合 RAG 问答系统设计

日期：2026-07-03
项目：`1999Search`
状态：待评审

## 摘要

当前问答系统已经具备 Milvus 向量检索、两阶段文本召回、MinIO 图片挂载和 React 问答窗口展示能力，但数据来源和资源挂载仍偏向早期 Obsidian 镜像方案。新的方向是全面转向灰机 Wiki 爬虫数据 `data/huiji/res1999`，以爬虫得到的 WikiText、Data JSON、资源 manifest 和本地资源文件作为唯一主数据源，重建面向问答系统的父块、子块、媒体资产和混合检索链路。

本设计采用“业务语义父块 + 可检索子块 + 独立媒体资产”的数据模型：BM25 或 embedding 命中子块后，系统扩展到对应父块，再在父块内做去重、排序和精排；每个子块可以挂载图片、音频、视频等资源，资源根据策略自动或按意图带出。第一版先实现结构化召回、本地 BM25 和文本向量召回；后续在拿到图片摘要后，再增加图片摘要向量召回。

核心原则是：原始爬虫目录只读，构建产物可重复生成；问答系统只使用灰机爬虫数据；Obsidian 代码和适配器接口保留，但当前不进入索引、问答或前端页面。

## 背景与只读检查结论

当前灰机爬虫数据位于：

```text
D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999
```

截至本次更新，灰机 Wiki 爬虫数据已经完整落地，但还没有进入当前向量库。

当前数据状态：

```text
pages / revisions: 79053
ns 0 主条目: 5746
ns 3500 Data: 72848
ns 10 模板: 284
ns 828 模块: 75
ns 14 分类: 100

resources: 61087
download_status=downloaded: 61087
资源总大小: 19,134,056,102 bytes，约 19.13 GB
```

主要原始文件和目录：

```text
wikitext.jsonl              Wiki 当前版本源码
data_pages.jsonl            Data 命名空间 JSON / 原文
pages.jsonl                 页面索引
resources_manifest.jsonl    资源清单
crawl_state.sqlite          增量状态库
assets/files/...            已下载图片、音频、视频等资源
```

只读检查得到的关键事实：

- `pages.jsonl`、`wikitext.jsonl`、`data_pages.jsonl`、`resources_manifest.jsonl`、`crawl_state.sqlite` 均存在。
- 资源已经下载完成，`resources_manifest.jsonl` 中 `download_status=downloaded` 的记录为 `61087`。
- 资源目录体积约 `19.13 GB`，后续业务代码不能直接暴露本地路径，必须通过 MinIO URL 返回。
- 普通角色 WikiText 页面较短，常以模板字段为主。
- 角色核心结构化数据在 `Data:Char/{id}.json`，例如 `Data:Char/3074.json` 是爱兹拉，包含技能、皮肤、icon、技能 ID 等。
- 资源文件名具有强检索信号，例如 `Portrait-307401.png`、`Skill-30740111.png`、`HeadIconSmall-307401.png`、`L2d_static-307401_aizila.png`。

当前向量化状态：

- 灰机 Wiki 数据尚未向量化。
- `data/processed/huiji` 当前不存在，说明新父子块构建产物还没有生成。
- 当前 `scripts/build_index.py` 仍从 `data/processed/documents.jsonl` 构建索引。
- `data/processed/documents.jsonl` 是旧 Obsidian 提取产物，不是灰机爬虫产物。
- 当前 `config/settings.yaml` 仍指向 Milvus collection `reverse1999_rag.chunks_bge_m3_v1`。
- 本地 `vectorstore/` 旧 Chroma 目录属于历史方案，不作为当前灰机数据状态判断依据。

当前代码边界和缺口：

- 现有主链路仍是 `documents.jsonl -> Milvus 文本 chunk -> AssetRegistry 按 source/heading/name 挂图`。
- 现有 `AssetRegistry` 依赖 `assets.jsonl`，尚未支持灰机资源 manifest、父子块、BM25 或媒体策略。
- 现有 Milvus collection `chunks_bge_m3_v1` schema 不适合新增父块、子块和资源策略字段。

## 规格分工与端到端交接

本 specs 是灰机爬虫数据进入问答系统的主衔接文档。爬虫 specs 只负责“如何采集、续跑、下载和维护原始数据”；本 specs 负责“爬下来之后如何清洗、建块、建索引、挂媒体、进入问答系统”。

相关文档分工：

- `2026-07-02-huiji-res1999-crawler-design.md`：灰机 Wiki 爬虫设计，负责原始数据采集和增量状态。
- `2026-07-03-huiji-crawler-command-reference.md`：爬虫和资源下载命令索引。
- `2026-07-03-huiji-parent-child-hybrid-rag-design.md`：本文件，负责灰机数据到 RAG 问答系统的处理链路。
- `2026-06-25-1999search-rag-design.md`：旧 Obsidian 时代 RAG 设计，仅保留为历史参考。

灰机数据落地后的下一步处理链路：

```text
data/huiji/res1999
  -> HuijiCrawlerDataSource 只读读取
  -> Normalizer / Resolver 解析 WikiText、Data JSON、资源 manifest
  -> data/processed/huiji/{build_version}/parent_blocks.jsonl
  -> data/processed/huiji/{build_version}/child_blocks.jsonl
  -> data/processed/huiji/{build_version}/media_assets.jsonl
  -> data/processed/huiji/{build_version}/indexes/child_text_bm25
  -> data/processed/huiji/{build_version}/indexes/media_asset_bm25
  -> MinIO reverse1999-assets
  -> Milvus reverse1999_rag.text_child_bge_m3_v2
  -> config/settings.yaml 切换到新 build version 和新 collection
  -> FastAPI 问答接口
  -> React 问答窗口
```

这意味着新系统不再把灰机数据清洗成旧的 `data/processed/documents.jsonl` 作为主产物。`documents.jsonl` 和 `chunks_bge_m3_v1` 只作为旧链路保留，用于回滚、对照和阶段性验证。

## 目标

- 全面转向灰机爬虫数据作为问答系统主数据源。
- 保留 Obsidian 适配器接口，但当前不让 Obsidian 数据进入系统。
- 构建稳定的 `parent_blocks`、`child_blocks`、`media_assets`。
- 支持父块/子块检索：命中子块后扩展父块，再对子块去重、排序和精排。
- 支持文本侧混合检索：本地 BM25 + Milvus dense embedding。
- 支持媒体侧召回：结构化规则 + BM25 `asset_search_text`。
- 支持后续增加图片摘要向量召回，不推翻当前结构。
- 支持资源迟到、资源更新、增量重建和 collection 版本切换。
- 问答 API 返回 `answer + sources + media`。
- 问答窗口兼容 Markdown，但不要求后端强制输出 Markdown。
- 第一阶段建立评估集和基础评估指标。

## 非目标

- 不在本阶段迭代首页、分类页、轮换页、图库页或资源库页面。
- 不让 Obsidian 数据进入当前问答、索引、BM25、资产或前端页面。
- 不直接暴露本地 `D:\...` 资源路径给浏览器。
- 不把图片、音频、视频二进制写入 Milvus。
- 第一版不接 Elasticsearch 或 OpenSearch。
- 第一版不要求图片摘要或图片向量召回。
- 第一版不做复杂前端产品化媒体中心。
- 不删除旧 Obsidian 代码和旧 collection；旧链路保留用于回滚和参考。

## 数据源策略

当前启用且唯一进入系统的数据源：

```text
HuijiCrawlerDataSource
  root = data/huiji/res1999
```

保留但当前禁用的数据源：

```text
ObsidianDataSource
```

要求：

- 新构建层使用 `DataSourceAdapter` 风格设计。
- 当前默认只启用 `HuijiCrawlerDataSource`。
- Obsidian 数据不进入向量库、BM25、媒体索引、问答 API 和其他前端页面。
- 未来如果要把爬虫数据重建为 Obsidian 本地可视化数据库，可通过适配器扩展，不影响当前问答系统。

## 总体架构

```text
data/huiji/res1999 只读原始数据
  -> HuijiCrawlerDataSource
  -> Normalizer / Resolver
  -> data/processed/huiji/{build_version}/parent_blocks.jsonl
  -> data/processed/huiji/{build_version}/child_blocks.jsonl
  -> data/processed/huiji/{build_version}/media_assets.jsonl
  -> data/processed/huiji/{build_version}/indexes/child_text_bm25
  -> data/processed/huiji/{build_version}/indexes/media_asset_bm25
  -> MinIO bucket: reverse1999-assets
  -> Milvus collection: text_child_bge_m3_v2

用户问题
  -> Query Planner
  -> Sparse BM25 retrieval
  -> Dense Milvus retrieval
  -> Merge + parent expansion
  -> Child rerank / dedupe
  -> Media attachment policy
  -> LLM answer generation
  -> FastAPI/SSE returns answer + sources + media
  -> React Q&A window renders text + media
```

后续图片摘要就绪后新增：

```text
media_assets + visual_caption + visual_tags
  -> Milvus collection: asset_caption_bge_m3_v1
  -> Asset dense retrieval
```

## 父块与子块模型

父块是业务语义单元，不直接等同于原始页面或数据文件。原始页面和 JSON 文件只作为 `source_ref` 保留。

推荐父块示例：

```text
char:3074/profile
char:3074/skills
char:3074/inheritance
char:3074/portraits
char:3074/skins
char:3074/voice
char:3074/story

story:100532/dialogue
story:100532/scene

psychube:1444/profile
psychube:1444/story

item:110101/profile
```

推荐子块示例：

```text
skill:30740111
skill:30740121
ultimate:30740131
voice:610011480
story:100532:step:0005
portrait:307401
asset:sha1:82d0e2d...
```

父块字段：

```json
{
  "parent_id": "char:3074/skills",
  "entity_id": "3074",
  "entity_name": "爱兹拉",
  "entity_aliases": ["Ezra Theodore"],
  "category": "character",
  "section_kind": "skills",
  "title": "爱兹拉 / 技能",
  "summary_text": "技能父块的简短摘要或拼接文本",
  "source_refs": [
    {
      "kind": "data_page",
      "title": "Data:Char/3074.json",
      "revid": 123,
      "content_sha256": "..."
    }
  ],
  "child_ids": ["skill:30740111", "skill:30740121"],
  "content_hash": "..."
}
```

子块字段：

```json
{
  "child_id": "skill:30740111",
  "parent_id": "char:3074/skills",
  "entity_id": "3074",
  "entity_name": "爱兹拉",
  "category": "character",
  "section_kind": "skill",
  "title": "看护于躯壳",
  "text": "技能说明、效果、描述等规范化文本",
  "search_text": "爱兹拉 Ezra Theodore 技能 看护于躯壳 Skill-30740111 ...",
  "chunk_index": 0,
  "media_ids": ["media:sha1:151861..."],
  "media_policy": "auto",
  "source_refs": [
    {
      "kind": "data_page",
      "title": "Data:Char/3074.json",
      "json_path": "$.skill.30740111",
      "content_sha256": "..."
    }
  ],
  "content_hash": "..."
}
```

## 数据覆盖优先级

第一版不是只做角色数据；剧情、心相、物品也必须进入可检索数据集，但调优优先级分层。

P0 必须高质量解析和调优：

- 角色基础信息 `profile`
- 角色技能 `skills`
- 角色立绘、头像、皮肤 `portraits/skins`
- 角色语音 `voice/audio`
- 角色媒体挂载
- 问答结果 `sources + media`

P1 第一版进入索引，但可以先用通用解析：

- 剧情 `story/dialogue`
- 心相 `psychube`
- 物品 `item`
- 传承、洞悉、塑造等角色养成信息

P2 可先入库但不重点调优，或后续增强：

- 活动页
- 版本页
- 成就
- 荒原、房间和其他玩法数据

这样后续优化剧情和心相时可以全局重建向量库，但不会出现第一版完全没有相关数据的覆盖缺口。

## 媒体资产模型

资源统一进入 MinIO，前端只接收 HTTP URL。

不直接暴露：

```text
D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\assets\files
```

媒体资产字段：

```json
{
  "media_id": "media:sha1:151861f204511618dbbba74d2df8a0aab7e7e4b3",
  "sha1": "151861f204511618dbbba74d2df8a0aab7e7e4b3",
  "entity_id": "3074",
  "entity_name": "爱兹拉",
  "parent_id": "char:3074/skills",
  "child_id": "skill:30740111",
  "asset_type": "skill",
  "mime": "image/png",
  "filename": "Skill-30740111.png",
  "title": "文件:Skill-30740111.png",
  "source_url": "https://huiji-public.huijistatic.com/...",
  "local_relpath": "assets/files/15.../Skill-30740111.png",
  "object_key": "reverse1999/skill/15/151861...png",
  "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/skill/15/151861...png",
  "is_available": true,
  "is_common": false,
  "attach_policy": "auto",
  "search_text": "爱兹拉 Ezra Theodore skill 技能 看护于躯壳 Skill-30740111.png",
  "content_hash": "..."
}
```

资源可用性：

- `is_available` 由 `local_relpath` 文件是否存在决定。
- `download_status` 只作为参考，不作为可用性判断依据。
- 资源未下载时仍保留 `media_assets` 记录，但 `is_available=false`。
- 不可用资源默认不返回前端。
- 资源后续下载完成后，增量上传 MinIO 并更新资产索引。

媒体挂载策略：

```text
auto:
  立绘、头像、技能图、终仪图、心相封面，可自动随回答返回。

on_intent:
  语音、剧情音频、视频、大批量媒体，仅用户明确询问时返回。

manual:
  公共图标、货币图标、Buff/Debuff 小图、UI 素材，默认不随问答返回。
```

示例：

- `玛蒂尔达的技能有什么`：自动返回技能图和终仪图。
- `看看爱兹拉的图片`：自动返回立绘或头像，过滤公共素材。
- `播放玛蒂尔达语音`：返回语音音频。
- `玛蒂尔达的技能有什么`：不自动返回所有语音。

## 检索设计

### Query Planner

Query Planner 输出：

```json
{
  "normalized_query": "玛蒂尔达的技能有什么",
  "entity": "玛蒂尔达",
  "aliases": ["Matilda"],
  "intent": "skill",
  "media_intent": "skill_image",
  "section_hints": ["skills", "ultimate"],
  "sparse_terms": ["玛蒂尔达", "技能", "神秘术", "至终的仪式"],
  "dense_query": "玛蒂尔达 技能 神秘术 至终的仪式",
  "confidence": 0.9
}
```

需要新增或明确的意图：

```text
profile
skill
voice
story
psychube
item
image
video
audio
general
```

`image/audio/video` 可以作为 `media_intent`，不一定替代文本 `intent`。

### 文本侧召回

文本侧使用混合检索：

```text
Sparse BM25(child.search_text)
Dense Milvus(child.text/search_text embedding)
```

第一版不使用 BGE-M3 自带 sparse 向量替代 BM25。当前项目的高价值关键词主要是角色名、别名、技能名、资源文件名、资源 ID 和页面标题，这些信号更适合用可解释、可调权重的 BM25 或结构化精确匹配处理。BGE-M3 sparse 可以作为后续增强项，但不作为第一版关键词召回主链路。

流程：

```text
1. BM25 返回 top_k_sparse 子块
2. Milvus 返回 top_k_dense 子块
3. 合并去重
4. 通过 parent_id 扩展父块
5. 父块内对子块重排
6. 选 final top_k 子块作为 LLM 上下文
```

排序信号：

- BM25 score
- dense score
- entity 精确匹配
- intent 与 `section_kind` 匹配
- parent 内邻近子块
- `media_policy` 与媒体意图匹配
- source 可信度
- 负向噪音惩罚

融合排序选型：

第一版文本侧采用 `加权 RRF + 规则加减分 + 父块扩展后二次排序`。

不直接把 `BM25 score` 和 `dense score` 相加，原因是两者量纲不同：BM25 受词频、字段长度和分词影响，dense score 受 embedding 模型和相似度分布影响，直接相加会让权重很难解释。RRF 只依赖各路召回的排名，第一版更稳定、更容易调试，也方便后续把 `BGE-M3 sparse` 作为第三路召回接入。

推荐初始公式：

```text
child_base_score =
  w_bm25  / (k + bm25_rank)
+ w_dense / (k + dense_rank)
+ exact_entity_bonus
+ alias_bonus
+ intent_section_bonus
- wrong_section_penalty
- common_noise_penalty
```

初始参数：

```text
k = 60
w_bm25  = 1.2
w_dense = 1.0

exact_entity_bonus     = +0.30
alias_bonus            = +0.20
intent_section_bonus   = +0.25
wrong_section_penalty  = -0.20
common_noise_penalty   = -0.30
```

父块排序不直接使用单个子块分数，而是聚合父块内命中的子块：

```text
parent_score =
  max(child_base_score in parent)
+ 0.15 * top_n_child_hit_count
+ parent_entity_bonus
+ parent_section_bonus
```

最终上下文选择顺序：

```text
1. 先选 top parent。
2. 每个 parent 内优先保留命中子块。
3. 补充命中子块相邻内容。
4. 同一 parent 内按原始 chunk_index 恢复局部顺序。
5. 按 token budget 截断。
```

该方案的选型原因：

- 能同时保留 BM25 的强词面匹配和 dense 的语义召回。
- 避免不同检索器分数不可比导致排序漂移。
- 规则加减分可以明确压制公共素材、错误 section 和低相关块。
- 父块扩展可以解决角色文档被切散后上下文不足的问题。
- 后续新增 `BGE-M3 sparse` 时只需要增加一路 RRF 项，不必推翻排序框架。

融合排序迭代方案简述：

1. 第一版固定权重上线，记录每次查询的 BM25 rank、dense rank、规则加减分、parent_score 和最终入选原因。
2. 用 `eval/queries_core.jsonl` 调整固定权重，优先优化 `Parent Recall@5`、`Child Recall@10`、`Noise Rate`。
3. 加入 `BGE-M3 sparse` 作为实验召回路，使用 A/B 评估，不直接替换 BM25。
4. 如果 sparse 提升召回且不恶化媒体误召回，再进入默认融合链路：

```text
RRF =
  w_exact  / (k + exact_rank)
+ w_bm25   / (k + bm25_rank)
+ w_sparse / (k + bge_m3_sparse_rank)
+ w_dense  / (k + dense_rank)
```

5. 当固定规则遇到明显瓶颈后，再评估 Cross-Encoder 或 LLM reranker；它只做最终 top candidates 精排，不承担第一阶段召回。

### 媒体侧召回

第一版媒体侧使用：

```text
结构化规则 + BM25(media.search_text)
```

结构化规则包括：

- `entity_name == plan.entity`
- `asset_type` 与 `intent/media_intent` 匹配
- `child_id` 或 `parent_id` 来自命中文本子块
- `is_available == true`
- `attach_policy` 允许自动或按意图返回

BM25 负责：

- 文件名命中
- 技能名命中
- 角色名命中
- 英文名、别名命中
- 资源 title 命中
- raw id 命中

媒体最终排序：

```text
final_score =
  structure_score
  + bm25_score
  + filename_entity_bonus
  + child_match_bonus
  + parent_match_bonus
  + media_intent_bonus
  - common_asset_penalty
  - unavailable_penalty
```

后续图片摘要就绪后，再增加：

```text
Dense(visual_caption + visual_tags)
```

## BM25 实现策略

第一版使用本地轻量 BM25，不接 Elasticsearch 或 OpenSearch。

现阶段采用 BM25 的原因：

- 角色名、别名、文件名、技能名和资源 ID 属于强词面匹配，BM25 比语义稀疏向量更直观。
- 图片资源召回需要精确控制 `entity_id`、`entity_name`、`asset_type`、`filename`、`source_page`、`is_common_asset` 和 `media_policy`，BM25 与结构化规则更容易调试。
- 当前最重要的问题是避免公共素材、货币图标、Buff/Debuff 小图和 `000-箱的构造` 这类低相关资源误召回，负向规则和字段权重比黑盒 sparse score 更可靠。
- 本地数据规模不大，本地 BM25 的实现成本、重建成本和排查成本都更低。
- BM25 可以作为稳定基线，方便后续评估 BGE-M3 sparse 是否真的提升召回，而不是把召回变化混在一次大改里。

BGE-M3 sparse 的定位：

- 不删除可能性，预留 `MilvusSparseVectorIndex` 或同类实现接口。
- 后续只在评估集上做 A/B 测试，不直接替换 BM25。
- 如果 BGE-M3 sparse 能提升 `Parent Recall@5`、`Child Recall@10` 或别名/错别字查询召回，且不恶化 `Asset Precision@5`、`Common Asset Leakage` 和 `Voice Auto Leak Rate`，再考虑纳入融合排序。
- 推荐形态是 `structured exact + BM25 + BGE-M3 sparse + BGE-M3 dense` 的多路融合，而不是用 BGE-M3 sparse 单独承担关键词匹配。

抽象接口：

```text
SparseIndex
  build(records)
  search(query, filters, top_k)
```

第一版实现：

```text
LocalBM25SparseIndex
```

可替换实现：

```text
OpenSearchSparseIndex
MilvusSparseVectorIndex
```

索引产物：

```text
data/processed/huiji/{build_version}/indexes/child_text_bm25
data/processed/huiji/{build_version}/indexes/media_asset_bm25
```

## Milvus collection 设计

新建 collection，不在旧 `chunks_bge_m3_v1` 上迁移：

```text
text_child_bge_m3_v2
```

后续图片摘要向量召回：

```text
asset_caption_bge_m3_v1
```

旧 collection：

```text
chunks_bge_m3_v1
```

旧 collection 保留一段时间，等新系统评估通过后再决定是否删除。

`text_child_bge_m3_v2` 显式核心字段：

```text
id                 VarChar primary key
embedding          FloatVector(1024)
text               VarChar
parent_id          VarChar
child_id           VarChar
entity_id          VarChar
entity_name        VarChar
category           VarChar
section_kind       VarChar
media_policy       VarChar
source_ref         VarChar
chunk_index        Int64
content_hash       VarChar
```

可以开启 Milvus 动态字段作为兜底，但业务主链路不依赖动态字段。

动态字段只用于：

- crawler extra metadata
- 游戏版本
- 稀有度等非统一字段
- 临时实验字段
- 不参与主检索排序的补充信息

不能放入动态字段的核心字段：

- `parent_id`
- `child_id`
- `entity_name`
- `section_kind`
- `asset_type`
- `media_policy`
- `source_ref`
- `content_hash`

如果某个动态字段后续成为稳定过滤或排序条件，应升级为显式字段并重建 collection。

## 可持续构建与增量策略

原始目录只读：

```text
data/huiji/res1999
```

构建产物目录：

```text
data/processed/huiji/{build_version}
```

推荐构建产物：

```text
parent_blocks.jsonl
child_blocks.jsonl
media_assets.jsonl
build_manifest.json
indexes/child_text_bm25
indexes/media_asset_bm25
```

稳定 ID 规则：

- 父块 ID 由业务类型、实体 ID、section kind 生成。
- 子块 ID 由业务类型、原始 ID、json path 或 step 编号生成。
- 媒体 ID 由 sha1 生成。
- 不使用数组顺序作为唯一 ID，除非原始数据确实没有稳定 ID。

变化检测：

- WikiText/Data JSON 使用 `content_sha256`、`revid`、`timestamp`。
- 资源使用 `sha1`、`local_relpath`、文件存在状态、文件大小。
- 构建器记录 `build_manifest.json`，包含输入文件 hash、产物数量、索引版本和 collection 名称。

资源迟到：

- 文本已构建但资源未下载时，生成 `is_available=false` 的媒体记录。
- 资源下载完成后，可以只运行资源同步任务：
  - 检查 `local_relpath` 是否存在。
  - 上传 MinIO。
  - 更新 `media_assets.jsonl` 或生成新 build version。
  - 重建 `media_asset_bm25`。
  - 不强制重建文本向量库。

内容更新：

- 如果文本内容变化，重建相关父块和子块。
- 如果 child text 变化，重新向量化相关子块。
- 如果 schema 或切块策略变化，新建 collection。
- 允许全局重建，优先保证最佳效果和一致性。

切换策略：

- 新 build version 构建完成后先运行评估。
- 评估通过后修改配置指向新 build version 和新 Milvus collection。
- 旧版本保留一段时间用于回滚。

## 问答 API 与前端显示

API 返回：

```json
{
  "answer": "...",
  "sources": [
    {
      "parent_id": "char:3074/skills",
      "child_id": "skill:30740111",
      "entity_name": "爱兹拉",
      "section_kind": "skill",
      "content": "...",
      "score": 0.91
    }
  ],
  "media": [
    {
      "media_id": "media:sha1:...",
      "asset_type": "skill",
      "mime": "image/png",
      "url": "http://127.0.0.1:9002/...",
      "title": "看护于躯壳",
      "attach_policy": "auto"
    }
  ]
}
```

问答窗口要求：

- 兼容 Markdown，但不强制后端输出 Markdown。
- 普通文本也要有合理换行和段落显示。
- 图片资源使用网格或卡片排版。
- 音频资源以长方形小按钮或条形控件呈现，点击后播放。
- 视频先做基础卡片或播放器展示，后续根据体验再调整。
- 只处理问答系统所需的最小展示，不扩展到其他页面。

## 评估方案

第一阶段必须包含评估集：

```text
eval/queries_core.jsonl
```

样例：

```json
{
  "query": "玛蒂尔达的技能有什么",
  "expected_entity": "玛蒂尔达",
  "expected_intent": "skill",
  "expected_parent_ids": ["char:3041/skills"],
  "expected_child_ids": ["skill:30410111", "skill:30410121"],
  "expected_asset_types": ["skill", "ultimate"],
  "forbidden_asset_types": ["voice", "common", "currency"]
}
```

覆盖类型：

- 角色介绍
- 角色技能
- 角色立绘
- 技能图挂载
- 语音按需挂载
- 剧情问答
- 心相问答
- 物品问答
- 错别字和别名
- 公共素材不应泄露
- 没有数据时的拒答

召回指标：

- Entity Accuracy
- Intent Accuracy
- Parent Recall@5
- Child Recall@10
- MRR
- nDCG@K
- Duplicate Rate
- Noise Rate

媒体指标：

- Asset Recall@5
- Asset Precision@5
- Asset Type Accuracy
- Common Asset Leakage
- Voice Auto Leak Rate
- URL Availability

生成指标：

- Faithfulness
- Answer Correctness
- Completeness
- Citation Accuracy
- Refusal Accuracy
- Hallucination Rate
- Media Relevance

MVP 通过线：

```text
Parent Recall@5 >= 95%
Child Recall@10 >= 90%
Asset Recall@5 >= 90%
Voice Auto Leak Rate = 0%
Common Asset Leakage <= 5%
URL Availability >= 98%
```

评估顺序必须是先召回，后生成。召回不正确时，不把生成失败归咎于 LLM。

## 简化迭代路线

阶段 1：新数据基座

- 全面转向灰机爬虫数据。
- Obsidian 不进入系统，但保留适配器接口。
- 构建 `parent_blocks`、`child_blocks`、`media_assets`。
- P0 高质量解析角色、技能、立绘、语音。
- P1 让剧情、心相、物品进入索引。
- 资源上传 MinIO。
- 问答系统返回 `sources + media`。

阶段 2：混合检索增强

- 文本侧：BM25 + dense + parent expansion + child rerank。
- 融合排序采用加权 RRF，不直接相加 BM25 和 dense 原始分数。
- 在 RRF 结果上叠加 entity、alias、section、media_policy 和噪音惩罚等可解释规则。
- 记录每次查询的召回排名、规则加减分、父块聚合分和最终入选原因，方便评估调权。
- 资源侧：结构化规则 + BM25 `asset_search_text`。
- 解决角色立绘、技能图、语音按需挂载问题。
- 建立召回和生成评估。

阶段 3：多模态增强

- 接入图片摘要 `visual_caption / visual_tags`。
- 新增图片资产向量索引。
- 支持“按视觉描述找图”。
- 评估 BGE-M3 sparse 作为第三路文本稀疏召回；如果通过 A/B 评估，则以第三路 RRF 项进入默认链路。
- 允许全局重建向量库。

阶段 4：深度调优

- 剧情与角色反链。
- 心相与角色、机制、推荐关系关联。
- 更细的意图识别。
- Cross-Encoder 或 LLM reranker 只用于最终候选精排，不承担第一阶段召回。
- 问答窗口资源体验按需增强，但不扩大到非问答页面。

## 风险与约束

- 灰机爬虫数据和多模态资源已落地，但未来仍可能增量更新，构建器必须容忍资源新增、变更和缺失。
- manifest 中 `download_status` 当前不可信，必须用文件存在性判断。
- `Data:*` JSON 体积大且结构差异多，不能直接全部塞入一个父块。
- 剧情和语音数量大，默认全量带出会影响体验和性能。
- 本地 BM25 对中文分词质量敏感，第一版可先用轻量分词，后续再优化词典。
- MinIO 上传需要幂等，重复 sha1 不应重复上传同一对象。
- 动态字段只能作为兜底，不应成为核心检索契约。

## 验收标准

- 系统默认数据源为灰机爬虫数据，Obsidian 不进入问答系统。
- 能从灰机数据构建父块、子块和媒体资产。
- 媒体资源统一通过 MinIO URL 返回。
- 对角色图片、角色技能、角色语音三类核心问题，资源挂载策略正确。
- 文本检索支持 BM25 + dense 合并。
- 命中子块后可以扩展父块，并在父块内重新排序子块。
- 语音不会在非语音意图下自动泄露。
- 公共图标、货币图标、Buff/Debuff 小图不会默认出现在角色图片结果中。
- 第一阶段评估集和指标可运行，且达到 MVP 通过线。
