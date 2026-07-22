# 灰机数据 Wiki 前端模块迭代设计

> **SUPERSEDED SOURCE CONTRACT（2026-07-20）**：本文保留历史布局决策，但其中旧 raw 路径、单 `media_id` 与单表媒体契约已由 `2026-07-20-huiji-wiki-media-v3-compatibility-design.md` 替代。当前唯一正式来源为冻结 crawler artifacts；v3 使用 `resource_id + binding_id`。

日期：2026-07-04  
项目：`1999Search`  
状态：待评审  
范围：React + Vite 独立 `/wiki` 工作区、Wiki 数据服务契约、与 RAG 跳转的预留边界。

## 摘要

当前前端已有首页、资料页、问答页三屏滚轮结构。新的 Wiki 模块不作为第四个滚轮页面，而是新增独立 `/wiki` 工作区，用于浏览灰机 Wiki 爬虫数据构建出的本地百科页面。Wiki 首期目标是验证灰机数据在角色、心相、剧情三类高价值页面上的展示质量、媒体挂载和页面跳转结构；动效暂时只预留挂点，后续再按 ReactBits 组件逐区接入。

本设计替代 2026-07-01 的 Obsidian 静态 Wiki 方案。旧方案中的交互意图可以保留，但数据源、构建方式和 API 契约需要重写：

- 数据源从 Obsidian vault 改为 `data/huiji/res1999` 灰机爬虫数据。
- Wiki 页面数据存入 MySQL，由 FastAPI `/api/wiki/*` 提供给 React。
- 多模态资源共用现有 MinIO，不复制第二份大体量图片、音频或 Live2D 相关资源。
- Wiki 不读 Milvus，不参与向量化；Milvus 仍属于 RAG 检索链路。
- RAG 后续通过 `wiki_route`、`entity_id`、`source_id` 跳转到 Wiki，不要求 Wiki 等待 RAG 链路完成。

核心原则简述：

```text
源数据共用，构建层分流，展示层解耦。

data/huiji/res1999 只读原始数据
  -> 统一构建器
       -> MySQL: Wiki 页面、路由、媒体映射、关系、关键词链接
       -> MinIO: 共用多模态资源
       -> RAG artifacts / Milvus: 后续问答检索
  -> FastAPI /api/wiki/*
  -> React /wiki
```

统一构建器的目的是让后续数据更新仍然是“一次更新”：爬虫更新后执行一次构建流程，分别刷新 Wiki MySQL、MinIO 资源引用、RAG blocks、BM25/Milvus，而不是手工维护多套数据。

## 当前项目背景

现有 React 前端入口：

```text
frontend/react-app/src/App.tsx
  -> Sidebar
  -> TopNav
  -> HomeSection
  -> DataSection
  -> ChatSection
```

当前主界面通过滚轮逐屏访问首页、资料页和问答页。Wiki 模块需要脱离该滚轮容器，避免 Wiki 内部长列表、阅读区滚动、媒体切换和未来动效与现有 scroll snap 抢事件。

当前灰机数据位于：

```text
D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999
```

已确认的关键事实：

- `pages.jsonl`、`wikitext.jsonl`、`data_pages.jsonl`、`resources_manifest.jsonl`、`crawl_state.sqlite` 均存在。
- 实际资源文件已落地到 `assets/files`，资源体量约 19.13 GB。
- 当前本地检查发现 `resources_manifest.jsonl` 的 `download_status` 字段不能作为唯一可信依据；资源可用性应以实际文件存在、sha1/local path 解析和构建器校验为准。
- `data/processed/huiji` 尚未生成，说明新的 Wiki/RAG 构建产物仍待落地。

## 目标

- 新增独立 `/wiki` 工作区，不影响现有首页、资料页、问答页。
- 使用 MySQL 作为 Wiki 展示数据库，FastAPI 提供 `/api/wiki/*`。
- 使用共用 MinIO 存储和访问图片、音频、Live2D 相关资源，不建立第二份多模态资源库。
- 首期优先展示角色、心相、剧情三类高价值页面。
- 其他 ns 0 页面和边缘内容不丢弃，可通过搜索或通用模板兜底逐步开放。
- Data namespace 不直接作为页面展示，但作为角色、心相、剧情等页面的主要结构化数据来源。
- Wiki 正文中的高置信关键词可以渲染为蓝色链接，点击跳转到对应 Wiki 页面。
- 为 RAG 后续来源跳转预留稳定路由和解析 API。
- 为每个主要区域预留动效配置接口，但首期不绑定具体 ReactBits 组件。

## 非目标

- 不复刻灰机 Wiki 的视觉风格和旧页面交互；灰机页面只作为信息结构参考。
- 不把 Wiki 做成现有三屏结构的第四屏。
- 不让 Wiki 读取 Milvus 或参与向量化。
- 不要求 RAG 问答页在 Wiki 首期完成前完成入库、检索和输出格式调整。
- 不直接暴露本地 `D:\...` 资源路径给浏览器。
- 不把 `Data:`、模板页、模块页、分类页作为首期可直接浏览页面。
- 不在首期完成复杂动效、Live2D 播放器完整接入或媒体中心产品化。
- 不将大规模 Wiki 数据写死到 `frontend/react-app/public/wiki/**` 作为主方案。

## 总体架构

```text
data/huiji/res1999
  pages.jsonl
  wikitext.jsonl
  data_pages.jsonl
  resources_manifest.jsonl
  assets/files/**
        |
        v
Huiji Wiki Builder
  - 读取原始数据，只读
  - 解析 Data JSON、WikiText、资源 manifest 和本地资源
  - 生成页面、关系、关键词链接和媒体映射
        |
        +--> MySQL wiki_* tables
        +--> MinIO reverse1999-assets
        +--> RAG parent/child blocks and Milvus collection, later

FastAPI
  /api/wiki/categories
  /api/wiki/pages
  /api/wiki/pages/{page_id}
  /api/wiki/routes/resolve
  /api/wiki/search
        |
        v
React + Vite
  /wiki 独立工作区
```

Wiki 和 RAG 的共享边界是构建器、实体 ID、媒体 ID 和路由映射，不共享页面渲染状态，也不共享 Milvus 查询结果。Wiki 可以先独立落地；RAG 今后只要在 sources 或 media 中携带 `wiki_route`，前端即可跳转。

## 数据库选择

Wiki 展示数据使用 MySQL。理由：

- 项目已在 Docker 中使用 MySQL，后续整体 Docker 打包时可以复用服务。
- Wiki 页面需要精确查询、分页、排序、分类筛选、关系查询和路由解析，这些更适合关系型数据库。
- SQLite 更适合原型和单文件分发，但本项目已经具备 MySQL 环境，引入 SQLite 会增加一套重复存储。
- Milvus 适合语义向量检索，不适合作为页面展示数据库。

## MySQL 数据模型

采用混合模型：页面基础字段结构化，正文内容保留 JSON 弹性，媒体和关系单独拆表。

### `wiki_pages`

页面主表。`content_json` 存储模板渲染所需的结构化内容。

```text
page_id            varchar, primary key
page_type          character | psychube | story | generic
title              varchar
subtitle           varchar
category           varchar
route              varchar, unique
source_pageid      bigint nullable
source_title       varchar nullable
content_json       json
updated_at         datetime
```

推荐路由：

```text
/wiki/char/{char_id}
/wiki/psychube/{psychube_id}
/wiki/story/{story_id}
/wiki/page/{pageid}
```

中文标题、英文名和别名只用于展示和搜索，不作为主路由键。

### `wiki_media_links`

页面、章节与 MinIO 媒体资源的映射。媒体文件只存一份，Wiki 和 RAG 通过 `media_id` 共用。

```text
id                 bigint, primary key
page_id            varchar
section_key        varchar
media_id           varchar
media_role         portrait | live2d | skin | cover | skill | gallery | audio | video
display_order      int
fallback_media_id  varchar nullable
```

角色页中，立绘、Live2D、皮肤属于同一个媒体窗口的不同切换状态，不拆成分散区域。

### `wiki_relations`

页面之间的显式关系。

```text
id                 bigint, primary key
from_page_id       varchar
to_page_id         varchar
relation_type      varchar
label              varchar
confidence         decimal
```

关系示例：

- 角色 -> 相关剧情
- 心相 -> 适配角色
- 剧情 -> 上一篇 / 下一篇
- 剧情 -> 出场角色

### `wiki_aliases`

实体别名表，用于搜索、关键词链接和 RAG 跳转解析。

```text
id                 bigint, primary key
page_id            varchar
alias              varchar
alias_type         canonical | english | nickname | source_title
priority           int
```

### `wiki_link_spans`

页面正文中的蓝色关键词链接。首期由构建器生成，前端只负责渲染和点击跳转。

```text
id                 bigint, primary key
page_id            varchar
section_key        varchar
text               varchar
target_route       varchar
confidence         decimal
```

链接策略采用混合模式：

- 明确关系一定链接。
- 角色名、心相名、剧情名、重要物品名等高置信实体自动链接。
- 低置信词不自动链接，避免页面被过度染蓝或误跳转。

## MinIO 和媒体策略

MinIO 使用共用实例和 bucket，不为 Wiki 单独复制资源。

推荐对象组织：

```text
reverse1999-assets/
  huiji/original/{sha1...}
  huiji/derived/thumbs/{sha1...}
  huiji/derived/webp/{sha1...}
```

媒体可用性判断：

- 不只相信 `resources_manifest.jsonl.download_status`。
- 构建器应校验本地文件存在、sha1、mime、文件大小和可上传状态。
- MySQL 只保存 `media_id`、角色、顺序、fallback 和可访问 URL 或 URL 派生信息。
- 浏览器不接收本地路径。

Live2D 规则：

- `Live2D` 是角色媒体窗口的正式切换项。
- 如果 Live2D 资源解析、播放器或运行时未就绪，不隐藏入口。
- 点击 Live2D 后显示同尺寸兜底：同皮肤静态立绘、Live2D 封面图、皮肤图，或明确的“Live2D 暂未接入”占位。
- 兜底不能改变媒体窗口尺寸，避免页面跳动。
- 后续接入 Live2D 播放器时，只替换该切换项内部实现，不改角色页结构。

## FastAPI API 设计

首期 API 只服务 Wiki 页面展示和 RAG 跳转解析，不参与 RAG 检索。

### `GET /api/wiki/categories`

返回动态分类，不写死旧 Obsidian 六分类。

```json
{
  "categories": [
    {
      "key": "character",
      "label": "角色",
      "count": 120,
      "templateGroup": "character",
      "animationProfile": "entity-list",
      "themeToken": "character"
    }
  ]
}
```

分类由构建器根据灰机数据和页面类型生成。首期至少覆盖角色、心相、剧情；其他分类以实际数据为准，例如物品、活动、敌人、机制、资源等。

### `GET /api/wiki/pages?category=&q=&type=&limit=&cursor=`

返回页面列表卡片的轻量字段。

```json
{
  "items": [
    {
      "pageId": "char:3074",
      "pageType": "character",
      "title": "爱兹拉",
      "subtitle": "Ezra Theodore",
      "category": "角色",
      "route": "/wiki/char/3074",
      "thumbnail": "https://...",
      "summary": "角色摘要"
    }
  ],
  "nextCursor": null
}
```

首期列表优先推荐角色、心相、剧情。边缘 ns 0 页面可通过搜索出现。

### `GET /api/wiki/pages/{page_id}`

返回完整页面详情。

```json
{
  "pageId": "char:3074",
  "pageType": "character",
  "title": "爱兹拉",
  "subtitle": "Ezra Theodore",
  "route": "/wiki/char/3074",
  "content": {},
  "mediaGroups": [],
  "relations": [],
  "linkSpans": [],
  "source": {
    "pageid": 123,
    "title": "爱兹拉"
  }
}
```

`content` 对应 MySQL `content_json`。前端根据 `pageType` 选择模板渲染。

### `GET /api/wiki/routes/resolve?source_id=&entity_id=&title=`

为 RAG 来源跳转预留。解析顺序：

1. `entity_id`
2. `source_id`
3. `title`
4. alias fallback

解析失败时返回可用于搜索页的 query，而不是让前端中断。

### `GET /api/wiki/search?q=`

全局搜索。首期可以使用 MySQL `LIKE` 或 fulltext；后续可优化为专门搜索索引。搜索只返回 Wiki 可展示页面，不直接返回 Data namespace 原始页。

## 前端路由和入口

新增 `/wiki` 独立工作区。它不挂在现有 `.snap-container` 内。

入口：

- `TopNav` 增加 Wiki 按钮。
- `Sidebar` 增加 Wiki 按钮。
- `DataSection` 的 `日历` 最后一页右下角增加 `进入WIKI` 和向右箭头。

三个入口都跳转同一个 `/wiki`。

从 RAG 跳转时，后续使用：

```text
source / media / keyword click
  -> wiki_route if present
  -> /api/wiki/routes/resolve if only source_id/entity_id/title exists
  -> /wiki search fallback
```

## `/wiki` 页面结构

Wiki 工作区采用四区结构：

```text
CategoryRail(hidden) | PageIndex | WikiReader | PageInfo
```

空间优先级：

```text
右信息栏 < 左分类唤出宽度 = 条目列表 < 主阅读区
```

### `WikiShell`

路由级容器，负责：

- 当前分类、搜索、选中页面、加载状态。
- 调用 `/api/wiki/*`。
- 根据 page type 选择模板。
- 根据 category metadata 传递动效 profile、模板组和主题 token。
- 提供返回主站或返回问答入口。

### `CategoryRail`

默认隐藏在左边界。鼠标贴近左边界或悬停达到与顶部导航一致的延迟后唤出。当前顶部导航延迟是 `700ms`，实现时应抽出共享常量，例如 `HOVER_REVEAL_DELAY_MS`。

职责：

- 展示 API 返回的动态分类。
- 改变当前分类筛选。
- 发出分类切换状态。
- 不直接渲染页面正文。

后续动效扩展：

```ts
category.animationProfile
category.templateGroup
category.themeToken
```

如果某些分类需要专属页面切换动效，由 `WikiShell` 和 `WikiReader` 根据分类元数据驱动，不让 `CategoryRail` 承担正文渲染。

### `PageIndex`

常驻显示，职责：

- 搜索输入。
- 当前分类筛选状态。
- 页面列表卡片。
- 标题、英文名/副标题、页面类型、缩略图和摘要。

首期列表优先展示角色、心相、剧情。其他页面通过搜索或通用模板逐步开放。

### `WikiReader`

最大区域，负责模板渲染。

首期模板：

- `CharacterPage`
- `PsychubePage`
- `StoryPage`
- `GenericWikiPage`

首期重点是基础可读、字段正确、媒体够大、数据面可观察。动效只预留区域，不绑定具体 ReactBits 组件。

### `PageInfo`

窄右栏，职责：

- 来源页面。
- 更新时间。
- 媒体数量。
- 关系数量。
- 页面目录。
- RAG 跳转信息。

`PageInfo` 只做辅助，不抢主阅读区空间。

## 首期页面模板

### 角色页 `CharacterPage`

重点：

- 大尺寸媒体窗口：立绘 / Live2D / 皮肤切换。
- 基础资料：中文名、英文名、星级、灵感、伤害类型、角色定位、版本。
- 技能：神秘术、至终仪式、传承、塑造。
- 扩展：皮肤、语音、故事、关联剧情入口。

主媒体区要求：

- 立绘和图片尽量足够大，参考灰机角色页的视觉占比。
- 立绘、Live2D、皮肤是同一个 `CharacterMediaStage` 的切换状态。
- Live2D 不可用时显示同尺寸兜底。
- 技能、传承、故事等内容放在媒体区下方或侧边结构化区域，避免压缩立绘。

数据字段应能承接灰机 Data 中的相关字段，例如：

```text
drawing
live2d
verticalDrawing
skin
showSwitchBtn
```

### 心相页 `PsychubePage`

重点：

- 大图封面。
- 基础资料：名称、稀有度、属性、适配角色或标签。
- 心相效果、增幅效果、故事文本。
- 关联角色或来源。

### 剧情页 `StoryPage`

重点：

- 封面或章节视觉。
- 基础资料：章节名、英文名、版本、类型、开放时间。
- 剧情正文、对话或关卡列表。
- 上下篇、关联角色、关联事件。

### 通用页 `GenericWikiPage`

用于非首期重点页面。要求：

- 能显示标题、来源、正文摘要或结构化内容。
- 能显示媒体占位和基本关联。
- 不以 Data namespace 原始 JSON 形式直接暴露给用户。

## 关键词链接

Wiki 正文中的部分关键词会变蓝，点击跳转到对应 Wiki 页面。

策略：

- 明确关系一定链接。
- 高置信实体自动链接。
- 低置信词不自动链接。
- 构建器生成 `linkSpans` 或 link candidates。
- 前端只负责渲染和点击跳转，不在浏览器端扫描全文做复杂实体识别。

后续可增加：

- 禁用自动链接词表。
- 别名优先级。
- 同名实体消歧规则。
- 用户手动确认的关系修正表。

## 动效扩展点

首期不选择具体 ReactBits 组件，但保留区域和状态：

- `CategoryRail` reveal/hide。
- 分类项入场。
- `PageIndex` 页面卡片列表入场。
- 页面卡片 hover。
- `WikiReader` 页面切换。
- `CharacterMediaStage` 立绘 / Live2D / 皮肤切换。
- 媒体 hover。
- `PageInfo` 更新。
- 日历页 `进入WIKI` 箭头。
- 蓝色关键词 hover/click。

动效配置应由页面类型、分类 metadata 或区域状态驱动，避免把具体动效写死在业务组件里。

## 错误处理

| 场景 | 行为 |
|---|---|
| MySQL 不可用 | `/wiki` 显示“Wiki 数据服务未启动”，不影响首页、资料页、问答页 |
| 分类为空 | 显示空状态，提示需要运行 Wiki 构建器 |
| 页面不存在 | 保留列表和搜索，阅读区显示未找到 |
| MinIO 图片不可用 | 显示固定尺寸占位，不让布局跳动 |
| Live2D 不可用 | 同媒体窗口显示静态图或占位 |
| 关键词目标不存在 | 关键词保持普通文本或跳到搜索 fallback |
| RAG 跳转无法解析 | 跳到 `/wiki` 搜索结果，不报错中断 |
| API 请求失败 | 当前区域显示错误状态，其他区域保持可用 |

## 测试策略

### 构建器和后端

- 能从 `data/huiji/res1999` 构建 Wiki MySQL 数据。
- 能生成 categories、pages、page detail、relations、media links。
- Data namespace 不直接作为 Wiki 页面展示。
- 角色、心相、剧情至少各有可打开样例。
- MinIO `media_id` 或 URL 能挂到页面。
- `routes/resolve` 能把 `entity_id`、`source_id` 或 title 映射到 `wiki_route`。
- `resources_manifest.download_status` 不作为唯一可用性判断。

### 前端

- `/wiki` 独立加载，不进入三屏滚轮 snap。
- 三个入口都能跳转 `/wiki`。
- `CategoryRail` 延迟唤出行为与顶部导航一致。
- 分类来自 API，不写死旧六类。
- 搜索和列表能打开页面。
- 角色页媒体窗口大尺寸显示。
- 立绘 / Live2D / 皮肤可切换。
- Live2D 不可用时有同尺寸兜底。
- 蓝色关键词点击能跳转。
- MySQL、MinIO、页面不存在时有稳定错误状态。

## 验收标准

- `/wiki` 能独立浏览 Wiki 页面。
- Wiki 数据来自 MySQL，媒体来自共用 MinIO。
- Wiki 不读 Milvus，不参与向量化。
- 首期优先展示角色、心相、剧情。
- 其他页面可搜索或通用模板兜底，不直接展示 Data namespace 原始页。
- 页面结构遵循：右信息栏 < 左分类唤出宽度 = 条目列表 < 主阅读区。
- 角色页主媒体窗口足够大，立绘 / Live2D / 皮肤在同一窗口切换。
- Live2D 不可用时有同尺寸兜底。
- 关键词链接采用混合策略。
- specs 明确保留后续动效扩展点，但不绑定具体 ReactBits 组件。
- 不修改 RAG 问答链路，不要求 RAG 数据在 Wiki 首期完成前完成入库。

## 与旧 Wiki 方案的关系

`2026-07-01-reverse1999-wiki-browser-design.md` 已标记为 OUTDATED。它只保留以下历史交互意图：

- 独立 Wiki 工作区。
- 四区布局。
- 左分类隐藏唤出。
- 三个入口进入 Wiki。
- 动效挂点按区域预留。

其余内容被本设计替代：

- Obsidian exporter。
- `frontend/react-app/public/wiki/manifest.json` 主数据方案。
- `/wiki/pages/*.json` 页面文件契约。
- Obsidian Markdown 模板优先级。
- Obsidian 资产复制策略。

本设计是后续 Wiki 前端模块实施计划的基准。
