# 线程 C：Topic/Story/Page 投影与 Wikitext 图片绑定设计

日期：2026-07-29

状态：用户审核候选

负责人：线程 C；规格、数据恢复与集成审核：线程 D

设计依赖：

- `docs/superpowers/specs/2026-07-29-rag-cli-supervision-design.md`
- `docs/superpowers/plans/2026-07-29-rag-cli-supervision.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-a-routing-design.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-b-chinese-bm25-analyzer-design.md`
- `docs/superpowers/specs/2026-07-20-huiji-crawler-corpus-builder-semantic-retrieval-design.md`

## 1. 背景与目标

当前 crawler source inventory 要求：

```text
pages.jsonl
wikitext.jsonl
data_pages.jsonl
resources_manifest.jsonl
```

但 `HuijiCorpusBuilder` 的语义路径当前只读取 `data_pages.jsonl` 和 `resources_manifest.jsonl`：

```text
data_pages
  → project_crawler_semantics()
  → character / generic Data projection

resources_manifest
  → Media V3 assembly
```

`pages.jsonl` 和 `wikitext.jsonl` 只进入来源 inventory 和哈希闭包，没有参与 Parent/Child、Topic/Story 自然名称或图片上下文生成。

已核实的当前实现事实：

1. `project_crawler_semantics()` 只接收 Data rows。
2. 普通 Data page 主要按标题中的 `story/episode/item/psychube` 等 marker 分类，并通常压成一个 `profile/root` child。
3. `Data:Story/304502.json` 一类剧情页保存大量剧情步骤，但标题本身不是用户自然语言。
4. `Data:ChapterElement/*`、`Data:Episode/*` 等结构化页包含章节、关卡、剧情 ID 与自然名称的显式关系，可作为可证明的名称证据。
5. `pages.jsonl` 保存自然页面标题；`wikitext.jsonl` 保存 pageid、revid、title、content SHA 和正文。
6. 普通页面索引和 Wikitext revision 并非天然一一齐全。当前快照中自然页面“今夜星光灿烂”存在于 `pages.jsonl`，但未找到其 pageid 对应的 Wikitext revision；相关其他页面仍明确链接该标题并引用 `Banner_今夜星光灿烂.png`。
7. `resources_manifest.jsonl` 保存该 Banner 的自然文件名、URL、SHA-1、size 和 local path，但状态为 `not_downloaded`，本地文件不存在。
8. 当前图片绑定只来自结构化 Data fields 生成的 `MediaBindingIntent`；`[[File:...]]`、`[[文件:...]]` 和 `<gallery>` 尚未解析。
9. Media V3 只有在本地文件存在且 SHA-1、SHA-256、size 验证通过时才能形成 runtime row。
10. 当前 canonical raw root 缺少 `data_pages.jsonl` 和 `crawl_state.sqlite`；已验证参考副本仍存在于旧项目目录。
11. `D:\1999Wiki_Backup` 没有这两个文件的直接副本，Git 因 raw data 被忽略而无法证明缺失原因。

线程 C 的目标是：

1. 在恢复后的同一 crawler snapshot 上建立 pages、revisions、Data pages 和 resources 的统一语义输入层。
2. 将普通 Wiki 页面按章节投影为稳定 Page children。
3. 将 Data Story ID 与可证明的章节、Episode 或剧情自然名称关联。
4. 生成来源支持的 Topic children，使“暴雨是什么”等问题具备可检索证据。
5. 从 Wikitext 提取图片引用、标题、章节、caption、link 和邻近上下文，并绑定到精确 child。
6. 在任何下载前生成精确引用资源 allowlist、容量和云端新增量报告。
7. 保持现有 character/item/psychube、Voice、Media V3 和 fidelity 闭包不退化。
8. 只生成隔离影子候选与诊断，不执行生产激活。

## 2. 范围与非目标

### 2.1 线程 C 负责

- 恢复 receipt 的消费和真实构建前置校验；
- pages/Wikitext/Data/resources 的统一输入契约；
- source row 去重、revision join、redirect 和诊断；
- 有界 Wikitext heading/link/file/gallery 解析；
- 普通 Page 的章节分块；
- Story 关系索引、自然名称和剧情正文投影；
- 受控 Topic catalog 和来源支持的 Topic 投影；
- Wikitext 图片到 page/section child 的绑定；
- caption、自然展示标题、link target 和上下文证据；
- exact resource filename resolution；
- 一资源多绑定；
- 引用资源 allowlist、容量和缺失资源报告；
- fixture、恢复快照 diagnostic build 和影子候选；
- 现有 character projection、Media V3 和 fidelity 回归。

### 2.2 线程 C 不负责

- Planner、Route Policy、Owner Gate 或复合问题编排；
- 中文 BM25 Analyzer、词典、payload schema 或 legacy loader；
- BGE-M3 Sparse、Dense embedding 或 reranker；
- 完整 MediaWiki 模板展开或页面渲染；
- LLM/VLM 生成 Topic 内容或图片描述；
- 根据标题相似度、向量相似度或高频词自动猜测实体关系；
- 自动下载全部 61,087 条 manifest 资源；
- 未经批准执行任何网络下载、MinIO 上传或对象覆盖；
- 正式 Milvus、MySQL、active pointer、生产 baseline 或生产激活；
- 修改线程 A/B worktree 中尚未合并的文件。

`SCOPE-P0-01`：C 生产公共 Parent/Child/Media 数据，A 只消费公共 JSON 字段。A 不依赖 C 的 Python parser、关系索引或 worktree 路径。

`SCOPE-P0-02`：C 可以实现“按 allowlist 下载”的能力或准备命令，但实际网络执行必须等待容量报告和用户单独批准；未获批准不阻止代码与 fixture 验收，只阻止真实媒体 candidate 进入 ready 状态。

`SCOPE-P0-03`：恢复 canonical raw snapshot 由线程 D 的恢复任务执行。C 只验证恢复 identity 和 receipt，不在自己的 worktree 中从外部参考目录复制大文件。

## 3. 方案选择

评估过三类方案：

| 方案 | 优点 | 主要问题 | 结论 |
|---|---|---|---|
| 继续只扩展 Data page projector | 工程量较低 | 无法消费页面标题、章节、链接和 Wikitext 图片上下文 | 不采用 |
| 完整 MediaWiki parser/renderer + 全量资源下载 | 覆盖看似最大 | 模板、Lua、HTML、网络和容量风险不可控 | 不采用 |
| 流式多源关联 + 有界 Wikitext parser + source-backed relation + 引用资源 allowlist | 可审计、可分阶段、与现有 builder 兼容 | 必须处理缺 revision、歧义关系和诊断闭包 | P0 采用 |

`DECISION-P0-01`：P0 不引入完整 MediaWiki 渲染器。实现一个只识别已冻结语法、能报告未支持模式的有界 scanner。

`DECISION-P0-02`：Topic/Story 名称和归属只接受结构化 ID 关系、精确 redirect、精确页面关系或受控 catalog selector；不使用模糊字符串相似度。

`DECISION-P0-03`：builder 保持离线。媒体下载作为 projection 之后、Media V3 assembly 之前的显式外部阶段，不能藏在 `HuijiCorpusBuilder.build()` 中。

## 4. 总体架构

```text
D 验证并恢复 2026-07-07 source snapshot
  │
  ▼
Recovery/Inventory Gate
  │
  ▼
CrawlerSemanticInputs
  ├─ pages metadata
  ├─ wikitext revisions
  ├─ Data pages
  └─ resource manifest
  │
  ▼
Source Join + Diagnostics
  ├─ pageid / lastrevid / revid
  ├─ redirect graph
  ├─ Data relation graph
  └─ exact resource catalog
  │
  ├───────────────┬────────────────┐
  ▼               ▼                ▼
Page Projection   Story Projection Topic Projection
  │               │                │
  └───────────────┴────────────────┘
                  │
                  ▼
      Parent / SemanticChild
                  │
                  ▼
       Wikitext Media Intents
                  │
                  ▼
 Referenced Media Plan + Capacity Report
                  │
       [独立用户审批下载]
                  │
                  ▼
          Media V3 Assembly
                  │
                  ▼
 isolated candidate / diagnostics / fidelity
```

`ARCH-P0-01`：新增统一输入对象，例如：

```text
CrawlerSemanticInputs
  pages
  revisions
  data_pages
  resources
  source_inventory
```

它只能包含 crawler snapshot 数据，不读取 MySQL 正文、MinIO 列表文本或 active artifacts 作为新事实来源。

`ARCH-P0-02`：现有 character/Data projector 作为一个 stage 保留；Page、Story relation、Topic 和 Wikitext media 使用独立模块，避免继续把所有逻辑堆入 `projection.py`。

`ARCH-P0-03`：`HuijiCorpusBuilder` 仍是唯一完整 artifact builder。C 不新增第三个生产 builder 或第二套 canonical media artifact。

`ARCH-P0-04`：MySQL 和 MinIO 只作为只读验收/可用性证据。它们不能反向生成正文、Topic 事实、图片 caption 或 owner relation。

## 5. Source snapshot 恢复门禁

### 5.1 已批准恢复身份

canonical target：

```text
D:\1999Wiki\data\huiji\res1999
```

只读参考 source：

```text
D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999
```

缺失文件身份：

| 文件 | size | rows | SHA-256 |
|---|---:|---:|---|
| `data_pages.jsonl` | 581,887,494 | 72,848 | `eb82b82e34300ee5d8beb27b13311fe530c59faeba3ae7883876b74b0eab9092` |
| `crawl_state.sqlite` | 47,710,208 | 不适用 | `cc34c6b701321b9fe59c3268577a334a3e092cd16190b59c28f98185a5866378` |

`RECOVERY-P0-01`：C 的真实全量运行必须先验证：

```text
config/recovery/huiji-res1999-20260707.json
.codex-supervisor/recovery/audit.json
.codex-supervisor/recovery/apply.json
```

以及 canonical target 中两个文件的 size/SHA/可读性。

`RECOVERY-P0-02`：缺失原因仍为未知。C 文档、日志和报告不得把它归因于某次清理、Git 操作或人为删除。

`RECOVERY-P0-03`：从已审计参考副本复制可以一比一恢复 2026-07-07 快照；重新抓取只能形成新 snapshot，不能宣称与旧文件逐字节一致。

`RECOVERY-P0-04`：恢复前允许 fixture 开发和只读 source shape 检查，禁止：

- 真实全量 Topic/Story/Page candidate；
- 真实资源批量下载；
- 基于不完整 raw root 的最终容量结论；
- 声称 source snapshot 验收通过。

`RECOVERY-P0-05`：恢复后的 `data_pages.jsonl` 中 crawler 标记的唯一 `json_valid=false` row 必须进入 excluded evidence。不能尝试解析其无效 content，也不能让该行阻断其他有效记录。

`RECOVERY-P0-06`：C 不修改恢复后的 `crawl_state.sqlite`。任何下载执行使用 staging state 或独立 receipt，canonical 状态库继续作为冻结抓取证据。

## 6. 流式读取与资源边界

四个 source 文件合计超过 1.2 GB，不能把所有原始正文同时复制到多个内存结构。

`STREAM-P0-01`：JSONL 必须逐行读取、逐行 schema 校验并记录 line/source identity。禁止 `read_text().splitlines()` 或一次性 `_read_jsonl()` 加载完整 pages/Wikitext/Data 文件。

`STREAM-P0-02`：允许保留以下有界索引：

- pageid → page metadata；
- `(pageid, revid)` → revision metadata/offset；
- Data stable ID → 关系证据；
- normalized filename → resource metadata；
- projection outputs 和 diagnostics。

不得在多个 index 中重复保存完整 Wikitext/Data content。

`STREAM-P0-03`：Story 关系需要多遍扫描时，可以对冻结文件执行确定性多遍顺序读取；不得生成未审计的永久中间真源。

`STREAM-P0-04`：每个 stage 输出读取行数、接受数、排除数、峰值内存或进程 RSS、耗时和原因计数。无法获得 RSS 时明确标记 unavailable，不伪造为 0。

`STREAM-P0-05`：单行超大、UTF-8 错误、JSON 解析错误和 schema 错误进入带 line identity 的诊断；是否阻断由第 18 节错误矩阵决定。

## 7. Page 与 revision 关联

`JOIN-P0-01`：page identity 使用 crawler `pageid`；revision identity 使用 `(pageid, revid, content_sha256)`。

`JOIN-P0-02`：相同 pageid 的完全相同 metadata row 可以去重；同一 pageid 出现冲突 title、namespace、lastrevid 或 status 时进入 `page_identity_conflict` 并阻断该 page projection。

`JOIN-P0-03`：相同 `(pageid, revid)` 的完全相同 revision 可以去重；content SHA 或 title 冲突时进入 `revision_identity_conflict`。

`JOIN-P0-04`：普通页面只投影 `status=active` 且能找到精确 `lastrevid` revision 的记录。没有 revision、revision 落后或 pageid/title 冲突时输出诊断，不使用相似标题补配。

`JOIN-P0-05`：Wikitext revision 不能在没有 matching page metadata 时自行成为 canonical Page；它可以进入 orphan revision 诊断。

`JOIN-P0-06`：normal namespace P0 只投影 `ns=0`。File、Template、Category 和 Data namespace 由各自 source/stage 处理，不混入普通 Page children。

### 7.1 Redirect

`JOIN-P0-07`：识别 `#REDIRECT [[target]]` 和等价本地重定向标记；redirect page 不生成正文 child。

`JOIN-P0-08`：只有 target 精确解析为同 snapshot 的 active page 时，redirect title 才进入 target `entity_aliases`。

`JOIN-P0-09`：dangling target、redirect cycle、跨 namespace 不支持 target 和冲突 redirect 进入诊断，不猜测。

`JOIN-P0-10`：普通 Wiki link label保留在来源 page 的可见文本和 search_text 中，但不自动成为 target alias。只有 redirect 或结构化关系能增加 alias。

## 8. Canonical source reference

Page/Wikitext source ref 固定包含：

```json
{
  "source_kind": "crawler_wikitext",
  "source_title": "页面标题",
  "source_row_id": "wikitext:<pageid>:<revid>:<section-token>:<char-start>-<char-end>",
  "source_content_sha256": "<64 hex>",
  "page_id": "123",
  "revision": "456",
  "heading_path": ["页面标题", "章节"],
  "char_start": 0,
  "char_end": 100
}
```

`SOURCE-P0-01`：`source_kind/source_title/source_row_id/source_content_sha256` 为所有新 source ref 必填字段，并与现有 Media V3 normalization 兼容。

`SOURCE-P0-02`：offset 相对于原始 Wikitext content；heading_path 相对于 parser 识别的当前 section；分块 source_row_id 必须包含字符区间，保证同一章节的多个 chunk 不共享标识。

`SOURCE-P0-03`：Data source ref 继续保留 title、revid、content SHA 和 json_path，并可规范为 `crawler_data_page`。

`SOURCE-P0-04`：所有 Topic、Story、Page child 至少有一个 crawler source ref。catalog、文件名、MySQL 或模型输出不能单独成为事实 source。

`SOURCE-P0-05`：source ref 不暴露本地绝对路径、cookie、下载 header、数据库连接或外部参考目录。

## 9. 有界 Wikitext parser

建议新增：

```text
src/huiji_rag/build/wikitext_projection.py
```

### 9.1 P0 支持语法

`WIKI-P0-01`：支持二至六级 heading：

```text
== Heading ==
=== Subheading ===
```

并维护有序 heading_path。

`WIKI-P0-02`：支持普通内部 link：

```text
[[Target]]
[[Target|Label]]
```

可见文本优先使用 Label，否则使用 Target。

`WIKI-P0-03`：支持图片 namespace：

```text
[[File:...]]
[[文件:...]]
[[Image:...]]
[[图像:...]]
```

大小写和本地化前缀规范化，但保留原始 filename。

`WIKI-P0-04`：支持 `<gallery>...</gallery>`，每行提取 filename、caption 和所在 heading_path。

`WIKI-P0-05`：图片 option 至少识别：

```text
thumb
frame
frameless
left/right/center/none
宽度或高度
alt=
link=
caption
```

未知 option 保留在诊断，不把它误作 caption。

`WIKI-P0-06`：识别 `{{DisplayTitle|...}}` 的简单纯文本形态，将其作为 page alias；嵌套模板或动态表达式不展开。

### 9.2 Parser 边界

`WIKI-P0-07`：scanner 必须处理 link/template nesting depth，不能仅用一个贪婪正则跨越多个 `[[...]]`。

`WIKI-P0-08`：P0 不展开 Lua、复杂模板、parser function、CSS background、裸 URL 图片或任意 HTML DOM。遇到时记录：

```text
unsupported_template_media
unsupported_html_media
unbalanced_wikilink
unclosed_gallery
dynamic_display_title
```

`WIKI-P0-09`：未支持模式不能让其他合法章节、link 或 File reference 消失；parser 以 page 为错误隔离边界。

`WIKI-P0-10`：parser 不访问网络，不查询 Wiki API，不读取 MySQL renderer 结果。

## 10. Page 章节投影

Page identity：

```text
entity_type       = page
entity_id         = <pageid>
owner_entity_id   = page:<pageid>
owner_page_id     = page:<pageid>
```

ID grammar：

```text
root parent    = page:<pageid>
section parent = page:<pageid>/section:<section-token>
child          = <section-parent>/chunk:<zero-padded-index>
```

`PAGE-P0-01`：lead section token 固定为 `lead`。其他 section token 使用 normalized heading_path 的 SHA-256 前 20 hex；重复相同 heading_path 增加 source-order occurrence suffix，并记录 fallback reason。

`PAGE-P0-02`：page title 是 canonical entity_name；精确 redirect title 和简单 DisplayTitle 进入 entity_aliases，稳定排序去重。

`PAGE-P0-03`：每个 section 的可见正文按段落优先组合：

- 目标不超过 1,200 个 Unicode characters；
- 单个不可分 block 最大 1,600；
- 超长 block 优先按句号/换行边界切分；
- 不生成 overlap；
- chunk_index 从 0 连续递增。

`PAGE-P0-04`：表格保留可读 header/cell 文本和行顺序，不要求还原视觉布局。导航、样式、空模板和纯分类标记不作为正文。

`PAGE-P0-05`：Page search_text 至少包含 page title、aliases、heading_path、可见 link labels 和正文。

`PAGE-P0-06`：普通 Page route_tags 至少包含 `page`；有明确定义句可增加 `definition`，有结构化 story/event 关系可增加 `story` 或 `event`，不能仅按关键词出现次数打标签。

`PAGE-P0-07`：页面无可见正文但有可验证图片/链接时可生成带 `sparse_text` quality flag 的最小 child；完全无可用内容时进入 exclusion。

## 11. Story 关系与自然名称

### 11.1 关系证据

P0 支持以下显式 Data 关系：

```text
Data:Story/<story-id>
Data:Episode/<episode-id>
Data:ChapterElement/<chapter-id>
Data:Chapter/<chapter-id>
```

`STORY-P0-01`：Story ID 以 Data title 中的稳定业务 ID 为 canonical entity_id，不使用扫描顺序或显示名称。

`STORY-P0-02`：自然名称证据优先级固定为：

1. Story payload 自身明确、非占位的 name/title；
2. ChapterElement 中 exact story/element ID 对应的 title/name；
3. Episode 的 `beforeStory/story/afterStory` exact ID 对应的 episode name，加受控 phase label；
4. 可验证的 normal page/Data explicit relation；
5. 原始 `Data:Story/<id>` fallback。

`STORY-P0-03`：同一优先级出现不同非空名称时进入 `story_name_conflict`；不得按最长、最新或字符串相似度任选。

`STORY-P0-04`：fallback raw ID 可以保留内容和精确 ID 检索，但必须增加 `weak_entity_name`，不能宣称已经解决自然语言映射。

`STORY-P0-05`：较低优先级且无冲突的名称进入 entity_aliases；原始 Data title 和业务 ID始终进入 search_text。

### 11.2 Story 正文

Story identity：

```text
entity_type       = story
entity_id         = <story-id>
owner_entity_id   = story:<story-id>
owner_page_id     = story:<story-id>
```

`STORY-P0-06`：Data Story 的步骤按稳定 JSON key/source order 解析，保留可见 speaker name、dialogue text、choice text 和 scene 分界。

`STORY-P0-07`：连续空步骤、纯控制字段、资源路径和布尔配置不作为正文；它们可以保留在诊断/source_fields，不进入用户回答上下文。

`STORY-P0-08`：Story child 按 scene/稳定 step token 构造 ID，source ref 精确到 json_path。缺稳定 step ID 时使用 source identity hash并记录 fallback。

`STORY-P0-09`：Story route_tags 至少包含 `story`；带 episode/chapter relation时增加 `episode`/`chapter`。正文不能因缺媒体而删除。

`STORY-P0-10`：P0 不解析 Data Story 背景、音频路径为新媒体绑定；这些属于 P1，除非当前 Media V3 已有明确结构化规则。

## 12. Topic 投影

自动从所有高频词生成 Topic 会产生大量伪概念。P0 使用版本化 selector catalog：

```text
src/huiji_rag/resources/topic_catalog.v1.json
```

catalog item 至少包含：

```text
topic_id
name
aliases
exact_page_titles
exact_heading_titles
required_route_tags
definition_patterns
```

`TOPIC-P0-01`：catalog 是来源选择规则，不是事实正文。每个 Topic child 的 content 必须来自实际 Page/Data child 和其 source refs。

`TOPIC-P0-02`：首版 catalog 至少覆盖：

```text
storm / 暴雨
reverse-1999 / 重返未来：1999
```

fixture 必须提供对应定义来源；真实快照没有合格证据时输出 topic evidence shortfall，不能用 catalog 名称制造答案。

`TOPIC-P0-03`：Topic identity：

```text
entity_type       = topic
entity_id         = <topic_id>
owner_entity_id   = topic:<topic-id>
owner_page_id     = topic:<topic-id>
```

`TOPIC-P0-04`：eligible evidence 至少满足一种：

- exact page title/redirect；
- exact heading title；
- catalog 允许的明确结构化 relation；
- eligible section 中匹配受控定义句。

仅在角色语音或正文中零散提及 Topic 名称不能生成 Topic child。

`TOPIC-P0-05`：Topic child 可以复制一个来源 section 的可见 content 到 Topic owner，但必须保留原 page/story owner 信息于 source_fields 和 source_refs；不得把多个来源先由 LLM 综合成无来源段落。

`TOPIC-P0-06`：Topic search_text 包含 canonical name、aliases、source page title、heading_path 和 content；route_tags 至少包含 `topic`，定义性证据增加 `definition/worldview`。

`TOPIC-P0-07`：同一 source child 被多个 Topic 引用时可以产生多个 source-backed Topic children，但每个 child ID 和 source_fields 必须能追溯原 child，不得按文本哈希误删合法多重关系。

## 13. 与线程 A 的公共 Child 契约

线程 C 对 A 输出以下稳定字段：

```text
category           string
entity_type        string
entity_id          string
entity_name        string
entity_aliases     array<string>
owner_entity_id    string
owner_page_id      string
route_tags         array<string>
parent_id          string
child_id           string
heading_path       array<string>
section_kind       string
content            string
search_text        string
source_refs        array<object>
```

`CONTRACT-P0-01`：`entity_type` 至少兼容：

```text
character
item
psychube
story
topic
page
```

`CONTRACT-P0-02`：不新增私有 `owner_type`。Owner 语义只通过 entity/owner 四字段表达。

`CONTRACT-P0-03`：`content` 与现有 `text` 在 P0 中必须完全相同；`text` 保留兼容，A 使用冻结的 `content` 字段。

`CONTRACT-P0-04`：`heading_path` 是非空字符串数组。Data/character legacy child 也必须填充确定性 path，不能只为新 Page 行提供。

`CONTRACT-P0-05`：`entity_aliases` 在 child row 中显式存在。角色 alias 使用现有 alias map；Page/Story/Topic 使用本 Spec 的来源规则。

`CONTRACT-P0-06`：增加 `content/heading_path/entity_aliases` 只属于 schema enrichment，不能改写现有 character 正文、Owner 或 section。fidelity diff 必须区分新增字段和内容变化。

`CONTRACT-P0-07`：C 分支不修改 B 的 Analyzer、BM25 payload 或 provenance 字段。D 按 B → C 顺序合并后，将新增 Child 字段纳入 B 的 canonical semantic hash 和集成测试。

## 14. Wikitext 图片绑定

### 14.1 Binding identity

Wikitext 图片 relation token：

```text
wiki:<pageid>:<section-token>:<filename-sha20>:<occurrence>
```

其中 occurrence 只在同一 section 内同一规范 filename 重复出现时递增。

`MEDIA-P0-01`：relation token 不包含 revid、caption 或抓取时间；同一页面同一 section 的相同图片在 revision 更新后尽量保持关系身份。

`MEDIA-P0-02`：每个图片 intent 绑定精确 owner_page_id、parent_id、child_id、heading_path、filename 和 source ref。图片不能只绑定到 page root 而丢失章节。

`MEDIA-P0-03`：同一图片出现在多个页面、章节或 Topic source 时保留多条 binding。physical resource 可以去重，binding 不得按 SHA/file/object key 折叠。

### 14.2 Caption 与自然展示标题

展示 title precedence：

1. 显式 File/gallery caption；
2. 同一 source container 中紧邻的可见 link label；
3. 当前 heading；
4. page title；
5. normalized filename。

`MEDIA-P0-04`：必须保存 title 的来源类型：

```text
explicit_caption
adjacent_link_label
heading
page_title
filename_fallback
```

不得把派生 title 伪装成原始 caption。

`MEDIA-P0-05`：source ref 额外保存原始 filename、原始 caption、link target、heading_path、char offsets、display title source 和邻近上下文 SHA-256。

`MEDIA-P0-06`：邻近上下文取同一 section 内图片前后各最多 200 个可见字符，不跨 heading；完整上下文位于所属 child content，source ref 只保存摘要字段和 hash，避免重复膨胀。

### 14.3 media_role

P0 role 规则：

| 来源证据 | media_role |
|---|---|
| `<gallery>` | `gallery_image` |
| lead section、显著大图或明确 Banner 布局 | `banner` |
| 显式 caption/heading 标记海报 | `poster` |
| 普通 section inline image | `page_image` |

`MEDIA-P0-07`：role 由 source location/options/caption 决定，不能只按 filename 前缀决定。

`MEDIA-P0-08`：宽高小于 96px、导航模板、旗帜/图标等弱证据图片可以进入 `decorative_media_excluded` 诊断，不进入 runtime media；阈值和原因进入 parser config fingerprint。

`MEDIA-P0-09`：没有 VLM 描述。已有 caption、link label、heading 和 page title 按来源优先级使用。

## 15. Resource resolution

`RESOURCE-P0-01`：Wikitext filename 规范化执行：

- File/文件/Image/图像前缀移除；
- URL decode；
- Unicode NFKC；
- 空格与下划线等价；
- 扩展名大小写归一；
- 其余文件名字符保留。

`RESOURCE-P0-02`：Wikitext intent 必须先按完整规范 filename 精确匹配 manifest `name/title`。禁止仅按 stem 模糊匹配。

`RESOURCE-P0-03`：exact filename 对应多个完全相同 SHA-1/size 记录时合并来源证据；对应不同 SHA-1 或 size 时进入 `resource_filename_conflict` 并阻断该 binding。

`RESOURCE-P0-04`：现有结构化 Data intents 可以继续使用其已验证 stem 兼容规则；Wikitext exact resolver 与 legacy stem resolver 必须在代码和诊断中区分。

`RESOURCE-P0-05`：manifest 无资源时记录 `referenced_resource_missing`；manifest 有记录但本地文件不存在时记录 `referenced_resource_not_downloaded`。两者不能混为同一错误。

`RESOURCE-P0-06`：本地文件存在时继续验证 containment、SHA-1、SHA-256 和 size。任何不一致不得生成 runtime binding。

## 16. 引用资源计划与容量门禁

建议新增产物：

```text
referenced_media_plan.v1.json
referenced_media_allowlist.v1.jsonl
media_capacity_report.v1.json
```

plan schema：

```text
schema_version = huiji.referenced-media-plan/v1
source_inventory_fingerprint
projection_fingerprint
phase = p0 | p1
selection_policy_sha256
media_budget_baseline_inventory_sha256
media_budget_bytes
minimum_free_after_commit_bytes
unique resources
binding IDs
filename/url/sha1/size/local_relpath
download status
MinIO presence evidence
capacity totals
projected_free_after_commit_bytes
budget_excluded_binding_count
budget_excluded_resource_count
overflow_media_new_bytes
projected_free_if_overflow_committed_bytes
free_space_shortfall_bytes
minimum_disk_expansion_bytes
recommended_disk_expansion_bytes
```

`CAPACITY-P0-01`：只计划 P0 projection 实际引用且未被 decorative/unsupported policy 排除的资源。不得把全部 manifest 当作下载集合。

`CAPACITY-P0-02`：报告至少计算：

```text
referenced_binding_count
unique_resource_count
declared_bytes_total
existing_valid_local_bytes
missing_local_bytes
largest_missing_resource_bytes
concurrent_part_peak_bytes
candidate_artifact_estimate_bytes
local_required_peak_bytes
MinIO_existing_object_bytes
MinIO_new_object_bytes
cloud_required_peak_bytes
media_budget_bytes
selected_media_new_bytes
projected_free_after_commit_bytes
actual_free_after_commit_bytes
minimum_free_after_commit_bytes
budget_excluded_binding_count
budget_excluded_resource_count
overflow_media_new_bytes
projected_free_if_overflow_committed_bytes
free_space_shortfall_bytes
minimum_disk_expansion_bytes
recommended_disk_expansion_bytes
```

`CAPACITY-P0-03`：本地安全门槛：

```text
local_subtotal_bytes =
  missing_local_bytes
  + concurrent_part_peak_bytes
  + candidate_artifact_estimate_bytes

free_local_bytes >=
  local_subtotal_bytes
  + max(2 GiB, 0.20 * local_subtotal_bytes)
```

`CAPACITY-P0-04`：云端安全门槛：

```text
known_cloud_free_or_quota_bytes >=
  MinIO_new_object_bytes
  + max(1 GiB, 20% of MinIO_new_object_bytes)
```

如果云端 quota/free space 无法可靠读取，状态为 `unknown_capacity`，不能回答“容量足够”。

`CAPACITY-P0-05`：MinIO existing/new 判断只能使用同 key + SHA/size 的只读 inventory。仅 filename 或 ETag 推测不能减少新增容量。

`CAPACITY-P0-06`：报告必须分别说明：

- 关系与 metadata 新增量；
- 本地下载新增量；
- MinIO 真实新对象量；
- candidate/rollback 临时峰值；
- 未下载或冲突 blocker。

### 16.1 服务器硬预算

2026-07-29 只读检查得到当前生产服务器基线：

```text
captured_at                        2026-07-29T03:20:04+08:00
filesystem                         /dev/vda2
filesystem_size_bytes              42,156,257,280
filesystem_used_bytes              23,098,384,384
filesystem_available_bytes         17,216,012,288
filesystem_available_gib           16.03
current_minio_directory_bytes       5,218,361,320
current_docker_directory_bytes      3,583,373,864
```

该服务器为单系统盘；MinIO、Milvus、MySQL、Docker 和应用共享根分区。以上数字只是规划基线，不能替代上传前的实时 `df -B1`。

冻结预算：

```text
P0_MEDIA_NEW_BYTES_MAX              268,435,456      # 256 MiB
P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX   2,147,483,648    # 2 GiB
MIN_FREE_AFTER_COMMIT_BYTES         12,884,901,888   # 12 GiB
```

当前快照的只读规划样本为：

```text
P0 one-representative-per-main-page
  468 unique objects
  186,067,585 declared bytes

P1 up-to-three-per-main-page
  1,060 unique objects
  577,660,183 declared bytes

P1 up-to-two-Data-Story-backgrounds
  702 unique objects
  1,096,270,832 declared bytes
```

这些数字用于证明预算具备可行空间，不是最终 allowlist，也不能覆盖实际 MinIO reuse、artifact/index 估算和提交前实时容量检查。

`CAPACITY-P0-07`：D 在首次 P0 写入前生成 metadata-only MinIO inventory receipt，并冻结 `media_budget_baseline_inventory_sha256`。P0 与 P1 共用该基线；P1 不得在 P0 上传后重新选基线以规避累计预算。`selected_media_new_bytes` 只计算该基线中同 object key + SHA/size 尚不存在的真实新对象。基线已有物理对象可以被多个 binding 复用，不重复计费或上传。

`CAPACITY-P0-08`：P0 物理资源选择固定为：

1. 所有合法图片先建立 source-backed binding metadata；
2. 每个主命名空间 Page、Activity 或 Chapter 最多实体化一张代表图；
3. 优先级为显式 caption 的 banner/poster/cover/title，其次为有章节语义的正文图；
4. Data Story 背景、CG、对话头像只保留来源路径或复用关系，不在 P0 新增物理对象；
5. 导航、边框、按钮、Buff、货币和重复小图标不进入 P0 物理集合。

P0 最终 `selected_media_new_bytes` 不得超过 256 MiB。核心代表图集合自身超过预算时状态为 `capacity_blocked`，不得随机截断。

`CAPACITY-P0-09`：P1 在新的用户批准和独立 Plan 下，使用累计预算：

1. 每个 Page 最多三张物理图，包含 P0 已选代表图；
2. 每个 Story 最多两张去重后的背景或 CG；
3. 对话 `head_icon` 复用已有角色头像，不按 Story step 生成新对象；
4. Item、Psychube、Episode、地图和活动插图各实体最多一张代表图；
5. SkinVideo 外链截图、外链视频、战斗/Buff/UI 图标和全部 manifest 下载不计入获准 P1 集合；如未来纳入，必须重新审批预算。

P1 相对修订前生产基线的累计 `selected_media_new_bytes` 不得超过 2 GiB。达到预算后，低优先级资源保留 binding metadata 并进入 `capacity_budget_excluded` 诊断，不能静默丢弃关系。

`CAPACITY-P0-10`：每次 P0/P1 提交前必须满足：

```text
projected_free_after_commit_bytes >= 12,884,901,888
```

`projected_free_after_commit_bytes` 必须扣除本阶段全部已知新增项，而不只是媒体：

- MinIO 新对象和上传临时峰值；
- Parent/Child/Media artifacts；
- BM25 artifact；
- 计划中的 Milvus 增量及其索引开销；
- MySQL 增量；
- candidate、rollback 和 operation receipt；
- Docker release 增量中无法安全复用的部分。

任一项未知时不得按零计算；应使用经记录的保守上界，或返回 `unknown_capacity`。

本节的 `commit` 指批准的对象/候选存储阶段原子提交和状态接受，不是 Git commit。

`CAPACITY-P0-11`：提交完成后重新读取同一文件系统的实际 available bytes。若：

```text
actual_free_after_commit_bytes < 12,884,901,888
```

则阶段不得标记 accepted/ready。不得通过删除现有 MinIO、Milvus、MySQL、Docker image、release 或备份来临时满足门槛；任何清理必须另立计划并获得批准。

`CAPACITY-P0-12`：禁止以下“全量”模式：

- 全部 40,420 个 manifest 图片；
- 全部 6,321 个已匹配 Wikitext 图片；
- 全部 Data Story 背景/CG；
- 同时保存等价 PNG、WebP 和新衍生图；
- 在服务器保留完整媒体下载 staging 副本。

下载和转码在本地或独立构建环境完成；服务器只接收批准 allowlist 中的最终对象。服务器端单对象 `.part`/multipart 临时量仍必须进入峰值计算。

### 16.2 阻断后的剩余媒体与扩容预测

触发 `capacity_blocked` 后必须继续完成只读预测，但不得继续下载、上传或提交对象。

`CAPACITY-P0-13`：overflow forecast 至少分成三个互斥集合：

```text
selected_within_budget
  已进入当前批准 allowlist 的对象

phase_overflow
  语义合法、仅因 phase byte budget 或 12 GiB 门槛被排除的对象

not_eligible
  decorative、unsupported、conflict、missing manifest、外链未授权、
  视频或超出当前 P0/P1 语义范围的对象
```

只有 `phase_overflow` 用于“是否放弃、部分放行或扩容”的决策。`not_eligible` 不能借扩容名义自动进入下载集合。

`CAPACITY-P0-14`：报告必须对 `phase_overflow` 同时给出：

- resource/binding 数量；
- 去重后的真实新对象字节；
- 按 Page/Story/Item/Psychube/Episode/Map/Activity 等类别分组；
- 按代表图、captioned supporting、background/CG、guide/map 等优先级分组；
- 已有 MinIO 对象可复用字节；
- 若全部加入后的 `projected_free_if_overflow_committed_bytes`；
- 相对 12 GiB 门槛的 `free_space_shortfall_bytes`；
- 不包含 overflow 时的 projected/actual free；
- 最大单对象和上传临时峰值。

公式：

```text
projected_free_if_overflow_committed_bytes =
  projected_free_after_commit_bytes
  - overflow_media_new_bytes
  - overflow_storage_overhead_bytes
  - overflow_candidate_index_growth_bytes

free_space_shortfall_bytes =
  max(
    0,
    MIN_FREE_AFTER_COMMIT_BYTES
    - projected_free_if_overflow_committed_bytes
  )

minimum_disk_expansion_bytes =
  free_space_shortfall_bytes

recommended_disk_expansion_bytes =
  0, if free_space_shortfall_bytes = 0
  otherwise round_up_to_5_gib(
    free_space_shortfall_bytes
    + max(2 GiB, 0.20 * overflow_media_new_bytes)
  )
```

`minimum_disk_expansion_bytes` 仅表示数学上刚好维持 12 GiB 的下限；实际扩容评估使用 `recommended_disk_expansion_bytes`，为未来索引、Docker release、日志和文件系统波动保留余量。若 `free_space_shortfall_bytes = 0`，报告应明确“无需扩盘，但需要提高 phase media budget 并重新批准”，不能自动放行。

`CAPACITY-P0-15`：阻断后的决策只允许：

1. `abandon_overflow`：保持 metadata binding，放弃下载全部 overflow；
2. `approve_partial_overflow`：按冻结优先级选择显式子集，重新生成 allowlist、预算和 SHA；
3. `expand_storage_then_replan`：先完成独立扩容计划和验证，再基于新容量重新生成 allowlist；
4. `defer_decision`：保持 blocked，不改变生产状态。

系统不得自行选择决策，不得以删除现有对象、数据库、镜像或备份代替扩容，也不得在旧 allowlist 上追加资源。每次选择都需要新的用户批准和 operation receipt。

## 17. 下载、上传和激活边界

`DOWNLOAD-P0-01`：任何实际下载前必须固定 allowlist SHA-256、source inventory SHA、预计 bytes、worker 数和目标 root，并获得用户对该精确计划的批准。

`DOWNLOAD-P0-02`：下载器只能消费 allowlist；URL host 继续受现有 allowlist 约束。不得在执行中重新查询并扩大到其他 manifest rows。

`DOWNLOAD-P0-03`：canonical `crawl_state.sqlite` 不可修改。需要状态写入时使用 staging copy 或独立 download receipt。

`DOWNLOAD-P0-04`：每个资源使用 `.part`、size/SHA-1 验证和原子完成；失败不提交最终文件，不删除原有合法文件。

`DOWNLOAD-P0-05`：builder 本身不访问网络。未执行下载时可以生成 diagnostic projection、allowlist 和容量报告，但 Media V3 candidate 保持 `diagnostic_only/blocked`。

`DOWNLOAD-P0-06`：线程 C 不上传 MinIO。若容量报告显示需要新对象，D 另行编写上传方案并再次请求用户批准。

`DOWNLOAD-P0-07`：通过 fixture、下载或 shadow build 均不授权 active pointer、Milvus、MySQL 或生产 baseline 变更。

## 18. Builder 集成与状态

`BUILD-P0-01`：orchestrator 必须读取并实际消费四个 source 文件，不再只把 pages/Wikitext 作为 inventory 条目。

`BUILD-P0-02`：source join、Page、Story、Topic 和 Wikitext media stage 均进入 code fingerprint 和 config fingerprint。

`BUILD-P0-03`：projection diagnostics 至少包含：

```text
page/revision conflicts
missing latest revisions
redirect errors
unsupported Wikitext modes
Story name conflicts/fallbacks
Topic evidence shortfall
media parse exclusions
resource missing/not-downloaded/conflicts
invalid Data wrapper
```

`BUILD-P0-04`：状态规则：

| 条件 | 允许状态 |
|---|---|
| source recovery 未通过 | `blocked` |
| projection 可完成但 referenced media 未下载 | `diagnostic_only` |
| identity/resource conflict 未解释 | `blocked` |
| text/media/fidelity 闭包通过且无 protected-state drift | `ready_for_embedding` |

`BUILD-P0-05`：builder 只写新的隔离 build root，不能复用现有 build version、`dev` 或 active build。

`BUILD-P0-06`：C 不执行 embedding 或 shadow Milvus 写入。`ready_for_embedding` 只是 handoff 状态，不是 activation approval。

## 19. Fidelity、provenance 与非退化

`FIDELITY-P0-01`：当前 character/item/psychube Parent、Child、Voice 和 Media 投影必须继续运行。新增 Page/Story/Topic 不能删除或改 owner。

`FIDELITY-P0-02`：现有 active parent/child/media 每条仍必须分类为：

```text
preserved_exact
preserved_rekeyed
corrected_semantics
removed_with_source_reason
```

`unexplained_missing` 和 `unexplained_binding_loss` 必须为 0。

`FIDELITY-P0-03`：新增 `content/heading_path/entity_aliases` 导致的 schema enrichment 与正文/Owner 变化分开报告。

`FIDELITY-P0-04`：同一资源的多个页面/章节 binding 按多重集保留；resource 去重不能减少 binding count。

`FIDELITY-P0-05`：重复构建在同 source inventory、config 和 code fingerprint 下产生相同 ID、顺序、content hash、source refs 和 projection fingerprint。

`FIDELITY-P0-06`：任何 active artifact、Milvus、MySQL 或 MinIO protected inventory 的未解释漂移停止真实候选验收。

## 20. 错误隔离

`ERROR-P0-01`：单个 page 的 Wikitext 不平衡、单个 Data row invalid 或单个 resource 缺失不能吞掉其他合法页面；它们进入精确 exclusion/diagnostic。

`ERROR-P0-02`：以下属于局部 exclusion：

- missing latest revision；
- unsupported template media；
- 无正文 page；
- Story raw-ID fallback；
- Topic evidence shortfall；
- decorative media；
- referenced resource not downloaded。

`ERROR-P0-03`：以下属于 blocker：

- source inventory/hash 不符；
- page/revision identity conflict；
- Story 同优先级名称冲突；
- exact filename 对应不同内容；
- child/parent/media closure 断裂；
- source identity collision；
- protected state drift；
- unexplained fidelity loss。

`ERROR-P0-04`：公开诊断不包含完整 Wikitext/Data content、绝对本地路径、凭据或 traceback；内部 run evidence 可以保存安全相对路径和 source identity。

`ERROR-P0-05`：失败后不得自动扩大 parser 支持、下载范围或 fuzzy relation。需要扩大范围时暂停并请求 D/用户批准。

## 21. Fixture 与单元验收

线程 C 自带最小四文件 fixture，不读取线程 A/B worktree。

### 21.1 Source join

`TEST-P0-01`：

- pageid/lastrevid/revid 精确 join；
- identical duplicate 去重；
- conflicting duplicate blocker；
- missing revision diagnostic；
- redirect alias、dangling redirect 和 cycle；
- orphan Wikitext 不投影；
- invalid Data wrapper 进入 exclusion；
- streaming reader 不调用整文件 `read_text()`。

### 21.2 Wikitext/Page

`TEST-P0-02`：

- lead、H2、H3 heading_path；
- 普通 link 可见 label；
- simple DisplayTitle alias；
- deterministic section/chunk IDs；
- 1,200/1,600 字符分块边界；
- table visible text；
- unsupported template/HTML diagnostics；
- malformed link 不影响其他合法 section。

### 21.3 Story

`TEST-P0-03`：

- Data Story 自身 name 优先；
- ChapterElement exact ID 名称；
- Episode before/main/after relation；
- 同优先级冲突 blocker；
- raw ID fallback + weak flag；
- step/scene 文本、speaker、choice 和 json_path；
- 控制字段不进入正文；
- 缺媒体不删除剧情 child。

### 21.4 Topic

`TEST-P0-04`：

- “暴雨” exact title/heading/definition evidence；
- `重返未来：1999` Topic evidence；
- 角色台词零散提及不能单独生成 Topic；
- Topic child 保留原 owner/source child/source ref；
- 无证据 catalog item 产生 shortfall 而非虚构 content；
- Topic/Page/Story 公共字段完整。

### 21.5 Wikitext media

`TEST-P0-05`：

- File/文件/Image/图像；
- gallery；
- caption、alt、link、heading 和 context hash；
- display title precedence 与来源类型；
- exact filename normalization；
- same resource 多 page/section binding；
- filename conflict blocker；
- manifest missing 与 not_downloaded 分离；
- decorative exclusion；
- Media V3 unknown child 和 source ref closure。

### 21.6 容量与外部操作

`TEST-P0-06`：

- allowlist 只包含实际引用资源；
- declared/existing/missing/new cloud bytes 正确；
- local/cloud safety margin；
- P0 新媒体超过 256 MiB 时返回 `capacity_blocked`；
- P1 累计新媒体超过 2 GiB 时返回 `capacity_blocked`；
- projected 或 actual free space 低于 12 GiB 时不得 accepted/ready；
- 未知 artifact/Milvus/MySQL/Docker 增量不能按零计；
- exact existing MinIO object 可以复用且不重复计费；
- 超出预算的低优先级 binding 保留 metadata 和 `capacity_budget_excluded`；
- 同一输入的代表图选择和 selection policy SHA 确定；
- capacity_blocked 后只读生成 selected/phase_overflow/not_eligible 三集合；
- overflow forecast 的剩余空间、12 GiB shortfall 和扩容公式正确；
- shortfall 为零时只建议提高预算，不误报必须扩盘；
- partial overflow 会生成新的显式 allowlist 和 SHA，不追加旧 allowlist；
- abandon/defer/expand 决策均保持生产对象零写入，直到新的用户批准；
- unknown cloud capacity 不报告 sufficient；
- downloader 拒绝 allowlist 外 job；
- canonical state DB 不被修改；
- builder 不访问网络；
- 无 approval 时不下载、不上传、不激活。

### 21.7 回归

`TEST-P0-07`：

- 现有 character projection 测试；
- collection/culture/Udimo/Voice tests；
- Media V3 resource/binding tests；
- corpus builder/artifact/fidelity/provenance tests；
- repeated build byte equality；
- parent-child-media closure；
- B 合并后的 BM25 child schema由 D 集成验证，C 分支不复制 B 实现。

## 22. 真实快照验收

恢复门禁通过后，C 执行只读/离线 diagnostic run。

`REAL-P0-01`：报告四个 source 文件 identity、rows、读取/接受/排除计数和 stage timings；必须识别 snapshot manifest 声明的唯一 invalid Data wrapper。

`REAL-P0-02`：“今夜星光灿烂”验收区分三类事实：

1. page index 中存在自然标题；
2. 相关 Wikitext 页面存在自然 link label 和 Banner 引用；
3. resource manifest 存在 Banner metadata，但本地状态为 not_downloaded。

不得声称当前 snapshot 已具备该自然页面自身的 Wikitext revision。

`REAL-P0-03`：相关 Page child 的 search_text 能包含“今夜星光灿烂”，Banner binding 保存来源 page、heading、title source 和 resource identity；未下载时进入 allowlist/容量报告。

`REAL-P0-04`：动态抽样 Data Story：

- 有明确自然名称；
- 只有 Episode/Chapter relation；
- raw ID fallback；
- name conflict 如存在；
- 短/中/长 Story 正文。

不得只验证一个写死 Story ID。

`REAL-P0-05`：“暴雨”必须找到 catalog 允许的真实来源证据或明确报告 evidence shortfall；角色页零散提及不得占据全部 Topic children。

`REAL-P0-06`：容量报告必须给出实际 referenced unique resources、missing local bytes、MinIO new bytes、phase budget 和 projected free after commit。只有能读取可靠 cloud free/quota evidence 时才能判断云端是否足够；P0/P1 的 projected free 和提交后 actual free 均不得低于 12 GiB。

`REAL-P0-07`：没有用户下载批准时，真实 run 到 diagnostic/allowlist/capacity 即停止；这不是媒体实现失败，但 candidate 不得报告 ready。

`REAL-P0-08`：如真实 run 触发容量阻断，必须输出 `phase_overflow` 的真实资源数、去重字节、全部加入后的预计剩余空间、12 GiB shortfall、最小扩容量和按 5 GiB 档位取整的建议扩容量；报告生成过程对 MinIO、MySQL、Milvus、Docker 和文件系统为只读。

## 23. 文件所有权

线程 C 可以修改：

```text
src/huiji_rag/build/projection.py
src/huiji_rag/build/page_sources.py
src/huiji_rag/build/wikitext_projection.py
src/huiji_rag/build/story_projection.py
src/huiji_rag/build/topic_projection.py
src/huiji_rag/build/media_download_plan.py
src/huiji_rag/build/media_v3.py
src/huiji_rag/build/orchestrator.py
src/huiji_rag/build/contracts.py
src/huiji_rag/models.py（仅冻结公共 Child 字段）
src/huiji_rag/resources/topic_catalog.v1.json
src/huijiwiki/resource_downloader.py（仅 allowlist/staging-state 支持）
对应 projection/media/orchestrator/resource tests
线程 C fixture、diagnostics 和容量报告
```

线程 C 禁止修改：

```text
src/rag/query_plan.py
src/rag/request_plan.py
src/rag/route_policy.py
src/rag/retriever.py
src/rag/chain.py
src/rag/sparse.py
src/rag/chinese_analyzer.py
BM25 payload/provenance schema
正式 raw source files
正式 processed artifacts
active pointer
生产 baseline
Milvus collection
MySQL 正式表
MinIO 对象
线程 A/B worktree 文件
```

`OWN-P0-01`：`models.py` 只允许增加 D 冻结的 `content/heading_path/entity_aliases` Child 公共字段及兼容序列化，不得顺带重构 Media/Voice 模型。

`OWN-P0-02`：如果 B/C 同时影响 artifact semantic hash，C 不修改 B 分支的 hash 实现；D 在按 B → C 合并后完成小型集成补丁并重跑双方测试。

`OWN-P0-03`：如果 Page/Topic/Story 需要新增超出第 13 节的公共字段，C 必须暂停并请求 D 冻结契约。

## 24. CLI 执行约束

`AGENT-P0-01`：线程 C 由一个长期 Codex CLI session 在 `codex/rag-c-projection` 独立 worktree 中执行，模型固定请求 `gpt-5.6-sol`，使用标准速度和 `workspace-write`。

`AGENT-P0-02`：启动参数必须显式关闭 `fast_mode` 和 `multi_agent`。禁止创建子代理、再次调用 Codex CLI 分派任务或读取 A/B 未合并 worktree。

启动基线：

```powershell
codex exec `
  -m gpt-5.6-sol `
  --disable fast_mode `
  --disable multi_agent `
  --sandbox workspace-write `
  --json `
  --cd "D:\1999Wiki.worktrees\rag-c-projection"
```

`AGENT-P0-03`：不设置人为 Token budget，不限制正常调查深度、测试次数和必要返工；通过 session resume、结构化状态和避免重复上下文控制消耗。

`AGENT-P0-04`：线程 C 首轮只编写自己的 Implementation Plan。Plan 经 D 审核前不得修改实现代码。

`AGENT-P0-05`：恢复 receipt 未通过时，C Plan 可以安排 fixture 阶段，但必须把真实 snapshot run、下载计划和容量结论标为 blocked。

## 25. 实施阶段与提交边界

线程 C 内部按以下顺序串行推进：

```text
C0 recovery receipt + source identity preflight
  → C1 streaming source join + Wikitext parser
  → C2 Page/Story/Topic projection + public Child contract
  → C3 Wikitext media binding + exact resource resolution
  → C4 allowlist + capacity report + optional approved download support
  → C5 offline shadow diagnostics + fidelity regression
```

原因：

- C1 依赖 C0 的 source identity；
- C2 依赖稳定 page/revision/Data relation；
- C3 依赖 C1 heading parser 和 C2 child IDs；
- C4 依赖最终 binding/resource集合；
- C5 依赖所有前置 projection；
- projection、media 和 orchestrator 高度共享，同一 C 线程内继续拆工作树会造成间接串行与冲突。

建议提交：

```text
feat(rag): join crawler pages revisions and Data relations
feat(rag): project source-backed Page Story and Topic children
feat(rag): bind Wikitext media to exact sections and resources
feat(rag): report referenced media capacity and download allowlist
test(rag): verify projection fidelity and real snapshot diagnostics
```

`PHASE-P0-01`：每个阶段必须先完成对应 fixture 测试和 D 审查再进入下一阶段。线程 C 不创建子代理，不把阶段拆成额外 CLI worker。

## 26. P1 与 P2 汇总

P1 可选：

- Data Story 背景、CG 和音频路径的结构化媒体绑定；图片每个 Story 最多实体化两张，音频不自动下载；
- Page 图片从 P0 的每页一张扩展到累计每页最多三张；
- Item、Psychube、Episode、地图和活动插图每实体最多一张代表图；
- 对话头像复用已有角色头像，不按 Story step 新增物理对象；
- 模板背景图和受控 HTML image；
- inheritance/portray Page section；
- 更丰富但仍 source-backed 的 Topic catalog；
- 增量 revision build；
- 下载批准后的真实引用资源补全；
- P1 新媒体相对修订前生产基线累计不超过 2 GiB，且提交后根分区至少剩余 12 GiB。

P2 延后：

- 完整 MediaWiki/Lua renderer；
- VLM 图片描述；
- LLM 自动 Topic 合成；
- fuzzy page/Data relation；
- 全部 manifest 资源下载；
- 皮肤级复杂媒体组合；
- 正式生产自动激活。

P1 只有全部 P0 完成、获得新批准并通过累计 2 GiB 媒体预算和 12 GiB 最低剩余空间检查后才可进入 Plan；P2 不得进入本轮实施任务。

## 27. 完成判定

线程 C 只有同时满足以下条件才能声明代码与 projection P0 完成：

1. C 消费并验证 D 的恢复 receipt；未恢复时真实阶段保持 blocked。
2. snapshot 中唯一 invalid Data wrapper 进入 excluded evidence。
3. pages/Wikitext/Data/resources 均被语义 stage 实际消费。
4. 大文件使用流式读取，不同时复制全部正文。
5. Page/revision join、redirect 和 conflict 规则确定。
6. 普通 Page 按 heading_path 形成稳定 section/chunk。
7. Data Story 自然名称只来自可证明关系，冲突和 raw fallback 可见。
8. Topic 只聚合 source-backed evidence，不由高频提及或模型生成。
9. A 冻结的 Child 公共字段完整且类型一致。
10. Wikitext File/gallery 绑定到精确 page/section child。
11. caption、link、heading、title source 和 context hash 可追踪。
12. exact resource resolution 区分 missing、not_downloaded 和 conflict。
13. 同一 resource 的多个合法 binding 不丢失。
14. allowlist 只含实际引用资源。
15. 容量报告给出本地、candidate、MinIO new、phase budget、projected/actual free 和安全余量；未知云容量不报告 sufficient。
16. builder 不访问网络，未经批准不下载、不上传、不激活。
17. 现有 character/item/psychube、Voice 和 Media V3 没有 unexplained regression。
18. parent-child-media closure、重复构建和 fidelity gate 通过。
19. “今夜星光灿烂”“暴雨”与动态 Story 分层样本按真实证据验收。
20. 不依赖线程 A/B 未合并代码。
21. 未修改正式 raw、processed、MySQL、MinIO、Milvus、baseline 或 active pointer。
22. D 审核 diff、测试、数据身份、容量和文件所有权后接受提交。
23. P0 新媒体不超过 256 MiB，代表图选择确定且超限时硬阻断。
24. P1 如获批准，相对修订前生产基线的累计新媒体不超过 2 GiB。
25. P0/P1 提交前 projected free 和提交后 actual free 均不低于 12 GiB。
26. 超预算图片保留 binding metadata 和可审计排除原因，不通过删除既有生产数据腾挪空间。
27. capacity_blocked 后生成剩余合格媒体的空间下降量、shortfall 和扩容建议，而不是只返回布尔失败。
28. 放弃、部分放行、扩容或延期均由用户重新批准，系统不自动扩预算或写入对象。

若用户未批准真实资源下载，C 仍可完成 parser、projection、binding intent、allowlist、容量和 diagnostic P0；但真实 media candidate 必须保持 `diagnostic_only/blocked`，不得声明 `ready_for_embedding`。
