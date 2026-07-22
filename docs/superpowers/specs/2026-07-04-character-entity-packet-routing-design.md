# 角色实体包与问答路由修正设计

日期：2026-07-04

## 背景

当前灰机数据已经进入 `data/huiji/res1999`，并构建出 `data/processed/huiji/dev/parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl` 和 BM25 索引。

只读抽样确认了一个关键问题：当前角色构建基本只生成两个父块：

- `char:{id}/profile`
- `char:{id}/skills`

例如 `十四行诗`、`玛蒂尔达`、`温妮弗雷德` 均只有极短的 `profile` 子块和 3 个技能子块。原始 `Data:Char/{id}.json` 中的 `character_data` 没有进入角色子块，导致：

- “介绍一下角色”只命中稀有度、职业、伤害类型等极薄信息。
- “单品”“文化”“角色故事”类问题会漂移到泛化 story/item 数据。
- 图片资源跟随错误文本结果挂载，即使图片匹配逻辑正确，也会显示错误图片。
- `???` 等占位角色进入候选池，污染来源和回答。

本设计暂停修补 top_k、局部降权和单点 prompt，先重新定义角色实体包、层级扩展、问答路由和输入区开关。

## 目标

- “介绍一下角色”默认走完整角色实体包，而不是单个 `profile` 子块。
- 明确顶层、父块、子块、深层子块的关系，避免“拉父块”含义不清。
- 问题重述升级为多路规划，让 BM25、embedding、媒体检索使用不同信号。
- 未展开内容通过输入区按钮继续追问，不直接丢弃。
- 图片自动挂载，语音和视频按需挂载。
- `BAAI/bge-reranker-v2-m3` 作为可选精排层，默认关闭，评估通过后开启。
- 异常实体可过滤、可追溯、可统计。
- 后续加入心相、物品、剧情等实体类型时，不推翻主链路。

## 非目标

- 本设计不实现前端首页、浏览页、图鉴页等非问答页面。
- 本设计不要求第一版接入 LangGraph 循环。
- 本设计不要求第一版对心相、物品、剧情建立完整实体包。
- 本设计不要求第一版启用图片摘要向量库。

## 核心术语

### 顶层实体包

顶层实体包是围绕一个实体运行时组装的完整资料集合，不是一条向量库记录。

示例：

```text
entity_packet: char:3023
entity_name: 十四行诗
entity_type: character
```

它可以包含：

- 档案
- 基础资料
- 技能
- 单品
- 文化故事
- 语音
- 皮肤
- 图片和其他媒体

### 父块

父块是顶层实体包下的一级语义 section。

角色第一版父块：

```text
char:{id}/dossier
char:{id}/profile
char:{id}/skills
char:{id}/items
char:{id}/culture
char:{id}/voice
char:{id}/skins
char:{id}/media
```

### 子块

子块是最小检索和排序单元。

示例：

```text
char:3023/item:302301
char:3023/culture:5
char:3023/skill:30230111
char:3023/voice:default:greeting
```

子块参与 BM25、dense embedding、reranker 和规则排序，并挂载对应媒体。

### 深层

深层表示父块之下更细的层级。

第一版推荐 4 层：

```text
Level 0 顶层实体包：char:3023
Level 1 父块：profile / dossier / skills / items / culture / voice / skins / media
Level 2 主题组：某组技能、某组单品、某组文化访谈、某套皮肤语音
Level 3 原子子块：单个技能、单件单品、单条语音、单段故事
```

## 角色数据归一化

第一版完整实体包只针对 `entity_type=character`。

### `character_data` 映射

`Data:Char/{id}.json` 中的 `character_data` 应进入角色实体包。

建议映射：

| 原始字段 | 目标父块 | 子块粒度 |
| --- | --- | --- |
| `type=1` | `dossier` | 角色档案一个或少量子块 |
| `type=2` | `items` | 每个单品一个子块 |
| `type=3` | `culture` | 每个文化/访谈/故事标题一个子块 |

`skill` 字段继续进入 `skills` 父块，但一个技能的一二三星效果应聚合为同一个技能子块，至终仪式单独作为一个子块。

`skin` 和立绘资源进入 `skins/media` 相关结构；文本描述可作为 `skins` 子块，图片资源作为 media record。

### 子块字段

推荐子块字段：

```text
child_id
parent_id
entity_id
entity_type
entity_name
entity_aliases
category
section_kind
depth_level
title
text
search_text
chunk_index
media_ids
media_policy
quality_flags
source_refs
content_hash
```

### 父块字段

推荐父块字段：

```text
parent_id
entity_id
entity_type
entity_name
entity_aliases
category
section_kind
depth_level
title
summary_text
child_ids
quality_flags
source_refs
content_hash
```

## QueryPlan 多路规划

当前单一 `normalized_query` 不再足够。Stage 0 应输出多路字段。

示例：

```json
{
  "original_query": "介绍一下十四行诗",
  "entity": "十四行诗",
  "entity_type": "character",
  "intent": "intro",
  "dense_query": "十四行诗的角色介绍、背景、技能和代表物品",
  "sparse_query": "十四行诗 Sonetto char:3023 档案 基础资料 技能 单品 文化",
  "media_query": "十四行诗 立绘 头像 皮肤",
  "aliases": ["Sonetto"],
  "scatter_terms": ["十四行诗", "Sonetto"],
  "packet_policy": "intro_full",
  "target_levels": ["entity", "parent", "child"],
  "media_intent": "none",
  "confidence": 0.9,
  "route": "rag_grounded"
}
```

### 意图集合

第一版意图：

```text
intro
profile_fact
skill
item
culture
voice
media
psychube
story
general
general_game
meta_question
```

关键拆分：

- `intro`：介绍角色，走实体包。
- `profile_fact`：生日、星级、职业、属性、伤害类型等基础事实，只查基础资料。

## 策略注册表

不应把角色逻辑写死进检索链路。应使用策略注册表：

```text
packet_policy_registry[entity_type][intent]
```

角色第一版策略：

```text
character.intro:
  sections: dossier, profile, culture, skills, items, media
  output: 百科摘要型
  omitted: 父块级按钮 + 高分未展开子标题按钮

character.profile_fact:
  sections: profile, dossier
  output: 精确字段回答

character.skill:
  sections: skills
  output: 技能详情，自动挂技能图

character.item:
  sections: items
  output: 单品详情，自动挂单品图

character.culture:
  sections: culture, dossier
  output: 文化故事和背景

character.voice:
  sections: voice
  output: voice panel
```

后续新增 `psychube`、`item`、`story`、`event` 时，只新增 normalizer 和策略，不重写检索主链路。

## 分层召回与扩展

第一版采用确定性分层扩展，不引入 LangGraph 循环。

流程：

```text
1. Stage 0 QueryPlan 多路规划
2. structured exact + BM25 + dense 召回子块候选
3. 合并去重
4. 可选 reranker 精排子块候选
5. ancestor expansion
6. bounded sibling expansion
7. 规则加减分和预算裁剪
8. 生成正文、sources、media、omitted_actions
```

### 扩展策略

采用均衡扩展：

```text
命中深层子块后，拉取：
- 顶层实体摘要
- 命中父块完整内容
- 同父块内高相关兄弟子块
```

未进入正文的内容不丢弃，进入 `omitted_actions`。

### intro 默认输出

`intro` 默认采用百科摘要型：

```text
dossier
profile
culture summary
skills overview
representative items
media portrait
```

正文只展开预算内最重要子块。剩余子块以按钮形式保留。

## 未展开内容和按钮

未展开按钮以父块级按钮为主，子标题为辅。

示例：

```text
父块级：
[全部技能] [全部单品] [文化故事] [立绘/皮肤] [语音]

高分未展开子标题：
[菱格发带] [基金会的孩子们] [写实之外的具象画]
```

每个按钮携带规范化 payload，而不是仅携带显示文本。

示例：

```json
{
  "query": "介绍十四行诗的技能详情",
  "entity": "十四行诗",
  "entity_type": "character",
  "intent": "skill",
  "packet_policy": "section_detail",
  "target_parent_id": "char:3023/skills"
}
```

## 输入区开关与失败补救

按钮放在聊天输入框底部，不放进回答气泡。

### 常驻模式按钮

常驻按钮：

```text
[扩大检索] [自由补充]
```

规则：

- 初始默认关闭。
- 点击后持续保留，直到用户手动关闭。
- 文字不变，通过颜色和填充状态表示开启或关闭。
- 两个按钮状态互相独立，不做隐式联动。

### 临时补救按钮

当 RAG 无可靠结果时，输入框底部出现临时补救按钮：

```text
[扩大范围重新搜索] [使用自由补充重答]
```

规则：

- 形态应与常驻按钮不同，使用更矮的圆角方框。
- 只作用于上一条问题。
- 不改变 `[扩大检索]` 或 `[自由补充]` 的常驻开关状态。
- “使用自由补充重答”不能叫“开启自由补充重答”，避免用户误解为会打开常驻开关。

### route

问答路线：

```text
rag_grounded:
  默认知识库回答，要求 sources。

expanded_rag:
  开启扩大检索或点击临时扩大按钮时使用，仍要求 sources。

llm_general:
  用户开启自由补充、点击临时自由补充，或问题为 general_game/meta_question 时使用。
  回答必须明确标注非知识库精确来源。

hybrid_answer:
  两个开关都开启时使用。第一版可预留，默认不作为主路径。
```

通用 LLM 不应掩盖实体识别和索引问题。明确实体类问题即使低置信度，也不自动自由发挥，除非用户开启或点击自由补充。

## 媒体策略

### 图片

图片按 intent 自动挂载：

- `intro`：立绘、代表图。
- `skill`：技能图、至终仪式图。
- `item`：单品图。
- `culture`：相关插图。

### 音频

语音只在 `voice` intent 或用户点击语音按钮时返回。

语音使用 `voice panel`，而不是普通图片/音频列表。

`voice panel` 是前端渲染组件；`voice intent` 是检索意图。

voice panel 规则：

- 高度约 2 到 3 行，可内部滚动。
- 台词文字独立一层。
- 播放进度使用背景层显示，不改台词颜色。
- 背景层和台词层分离，预留后续台词动效挂点。
- 默认按皮肤分组，基础皮肤优先。
- 用户明确问某组语音时，组间按意图排序，组内保留数据原始顺序。

### 视频

视频只在 `video` intent、明确提问或按钮触发时返回。

视频使用 `video panel`，而不是普通链接列表。

`video panel` 是前端渲染组件；`video intent` 是检索意图。

video panel 规则：

- 默认显示视频标题、来源说明、封面或首帧占位。
- 点击后在面板内播放，避免跳出聊天上下文。
- 支持播放/暂停、进度条、音量、全屏入口。
- 如果一个回答命中多个视频，默认展示最相关 1 个，其余折叠为可切换条目或按钮。
- 视频不自动播放，必须由用户点击触发。
- 视频面板与文本内容分层，预留封面动画、加载态和播放态挂点。

## Reranker

可选精排模型：

```text
BAAI/bge-reranker-v2-m3
provider: SiliconFlow
```

第一版策略：

- 配置可选，默认关闭。
- 评估通过后再默认开启。
- 只重排子块候选。
- 不替代 BM25、dense、structured exact。
- 不替代规则过滤。

候选规模：

```text
BM25 top 40
dense top 40
structured exact 少量必选
merge + dedupe 后最多 rerank 60 个子块
```

reranker 分数作为强排序信号，但仍保留：

- entity exact bonus / hard filter
- intent section bonus
- noise penalty
- quality_flags penalty
- media_policy 约束

## 异常实体与质量标记

采用两级策略：

```text
hard_exclude:
  严重异常不进入默认问答索引。

soft_flag:
  轻微异常进入索引，但记录质量标记并参与降权。
```

### hard_exclude

示例：

- `entity_name == "???"`
- 空名称
- 缺少有效 id
- 明显测试或占位实体

排除记录写入：

```text
data/processed/huiji/{build_version}/excluded_entities.jsonl
```

示例：

```json
{
  "entity_id": "9996",
  "entity_name": "???",
  "entity_type": "character",
  "reason": "placeholder_name",
  "source_title": "Data:Char/9996.json",
  "source_sha256": "...",
  "raw_refs": ["Data:Char/9996.json"],
  "detected_at": "build time"
}
```

构建日志示例：

```text
[huiji-corpus] excluded entity: id=9996 name=??? reason=placeholder_name source=Data:Char/9996.json
```

### soft_flag

示例：

- `short_text`
- `raw_html_noise`
- `missing_media`
- `weak_entity_name`
- `large_raw_json`

`quality_flags` 默认不展示给普通用户，但参与排序和评估 debug。

## 前端组件边界

建议解耦：

```text
ChatBubbleShell:
  气泡外框、宽度、入场动画、主题。

AnswerContent:
  文本、Markdown、媒体、voice panel。

ComposerActionBar:
  输入框底部常驻开关、临时补救按钮、omitted actions。
```

避免闪烁的原则：

- 流式回答保持稳定 `message_id`。
- token 到达时 append 内容，不整体替换气泡组件。
- 按钮状态独立于消息内容 key。
- 动画挂在 shell 或具体媒体组件上，避免外框和内容同时重排。

## 评估要求

第一版至少覆盖以下评估查询：

```text
介绍一下十四行诗
十四行诗的技能是什么
介绍一下十四行诗的单品
十四行诗有哪些文化故事
播放十四行诗语音
介绍一下玛蒂尔达
玛蒂尔达的技能是什么
介绍一下温妮弗雷德
1999是什么游戏
不存在角色的技能是什么
```

检查项：

- `intro` 是否返回实体包，而不是极薄 profile。
- `item` 是否命中角色单品子块，而不是泛 story。
- `skill` 是否保留一二三星效果。
- `voice` 是否返回 voice panel 数据结构。
- `???` 是否不进入默认 sources。
- 无可靠结果时是否只显示输入区临时补救按钮。
- 开关状态是否不互相联动。
- reranker 开关关闭时链路仍可运行。
- reranker 开关开启时输出可解释 debug 分数。

## 迭代路线

第一阶段：

- 重建角色 normalizer，补齐 `character_data`、voice、skins/media 基础结构。
- 引入 `intro` 与 `profile_fact`。
- 实现角色策略注册表。
- 实现均衡分层扩展和 omitted actions。
- 实现异常实体 hard_exclude 与 soft_flag。

第二阶段：

- 输入区常驻开关和临时补救按钮。
- voice panel 数据结构和前端组件。
- MinIO 媒体挂载修正。

第三阶段：

- 接入 `BAAI/bge-reranker-v2-m3` 可选配置。
- 基于评估集决定是否默认开启。

第四阶段：

- 扩展 `psychube`、`item`、`story`、`event` 实体包策略。
- 评估 BGE-M3 sparse 作为第三路召回。
- 如单轮分层扩展仍频繁漏召回，再考虑 LangGraph 检索循环。

第五阶段：

- 当真实用户 query 和人工标注样本足够后，评估可插拔 intent classifier。
- intent classifier 只辅助 `intent`、`secondary_intents` 和 `route` 判断。
- 它不替代实体识别、别名归一化、错别字纠正、查询重述、媒体查询生成和策略注册表。
- 第一版只预留日志和接口，不训练、不接入默认链路。

## 后续增强：可插拔意图分类器

BERT、中文 RoBERTa、MacBERT 等轻量分类模型适合在后续阶段作为 Stage 0 的意图先验。

它适合判断：

```text
intro
profile_fact
skill
item
voice
culture
media
general_game
meta_question
```

它不适合单独承担：

```text
实体标准名识别
别名归一化
错别字纠正
多实体问题拆解
BM25 / dense / media_query 重述
策略注册表选择
```

推荐成熟路线：

```text
1. 第一版继续使用规则 + LLM JSON 规划 + fallback。
2. 记录用户问题、Stage 0 结果、最终命中 intent、route、点击按钮、重试行为和人工修正。
3. 积累真实样本后人工校正标签。
4. 训练轻量多标签意图分类器。
5. 分类器输出 intent_probs 和 route_probs。
6. 高置信度时作为 QueryPlan 先验；低置信度仍交给 LLM 规划或澄清。
```

数据量参考：

```text
每个主要 intent 100-200 条标注样本：可开始实验
总量 1000-3000 条：可做有参考价值的离线评估
总量 5000+ 条：再考虑进入默认链路
```

分类器应支持多标签，而不是只输出一个硬分类。

示例：

```json
{
  "question": "介绍一下十四行诗的技能和单品",
  "primary_intent": "intro",
  "secondary_intents": ["skill", "item"],
  "intent_probs": {
    "intro": 0.82,
    "skill": 0.76,
    "item": 0.69
  }
}
```

该能力属于后续增强，不进入第一版实现范围。

## 当前确认结论

- “介绍一下角色”采用完整实体包方案。
- 扩展采用均衡扩展。
- 未展开内容保留为输入区按钮。
- 问题规划升级为多路字段。
- `profile` 拆为 `intro` 和 `profile_fact`。
- 媒体策略为图片自动，音视频按需。
- 语音使用 voice panel，背景层显示播放进度。
- 第一版完整实体包只做角色，但数据模型预留其他实体类型。
- 策略注册表必须引入。
- 通用 LLM 回答作为受控 fallback，不自动掩盖知识库失败。
- 输入区按钮默认关闭，状态持续保留。
- 临时补救按钮不改变常驻开关。
- reranker 可选、默认关闭、重排子块候选。
- 异常数据采用 hard_exclude + soft_flag 两级策略。

## 2026-07-08 补充：语音面板返回契约

本补充只约束 RAG 问答页的 `voice panel`，不涉及 Wiki 页面。

- 当 `intent=voice` 或 `media_intent=audio` 时，媒体召回应按命中的 `parent_id` 返回同一语音父块下的完整可用语音，而不是沿用普通媒体 `top_k` 截断。
- 语音条目标题优先使用清洗后的子块台词：`(中文)台词`、`(EN)line`、`(日)台词`、`(韩)台词`。如果原始数据缺少台词，再回退到文件名。
- 语种优先从音频文件名前缀识别，例如 `Zh/En/Jp/Kr`；文本台词从对应 `child_blocks.text` 的语言标签解析。
- 前端点击下一条语音时，上一条语音必须自动暂停并重置播放进度，避免多条语音同时播放。
- `voice panel` 的文字层和背景进度层保持分离，便于后续加入台词动画或播放进度动画。
