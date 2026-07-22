# 灰机 Wiki 模块修复设计

> **SUPERSEDED SOURCE CONTRACT（2026-07-20）**：本文仅作为历史恢复记录。来源、active gate、media v3 双 ID 和 MySQL 双表契约以 `2026-07-20-huiji-wiki-media-v3-compatibility-design.md` 为准；不得从 Obsidian、supplement 或 MinIO 枚举反推正式 Wiki 数据。

日期：2026-07-07  
项目：`1999Search`  
状态：待评审（2026-07-08 RAG 共享契约已确认）  
范围：Wiki 模块在前端组件大量丢失、构建源码不完整、且 RAG 修复链路已确认共享 MinIO、Milvus、processed artifacts 契约后的修复边界、模块契约与执行门槛。

## 1. 背景与目标

当前 Wiki 模块经历过文件丢失：

- 前端 `frontend/react-app/src/components/wiki` 基本只剩临时 `WikiShell.tsx`。
- `frontend/react-app/src/api/wiki.ts` 和 `frontend/react-app/src/types/wiki.ts` 仍存在，但只覆盖基础 API 客户端和 DTO。
- 后端 `backend/wiki.py`、`backend/wiki_schemas.py`、`src/huiji_wiki/models.py`、`src/huiji_wiki/repository.py` 仍存在，可读取当前 Docker MySQL 中的 Wiki 表。
- `src/huiji_wiki/builder.py`、`src/huiji_wiki/media_upload.py`、`scripts/build_huiji_wiki.py`、`scripts/verify_huiji_wiki_e2e.py` 等构建与验收源码缺失或不可依赖。
- 当前 Docker MySQL 中已有 Wiki P0 角色数据；MinIO `reverse1999-assets/reverse1999/` 中仍有当前问答媒体对象；RAG 已确认 active build_version 为 `dev`，即 `data/processed/huiji/dev`。
- 2026-07-08 只读清点显示，原始爬虫资源层已经恢复到可作为后续重建输入的状态：`pages.jsonl`、`wikitext.jsonl`、`data_pages.jsonl`、`resources_manifest.jsonl`、`crawl_state.sqlite` 和 `assets/files` 均存在，`assets/files` 约 61080 个文件、约 17.82 GiB。
- `resources_manifest.jsonl` 中的 `download_status` 字段仍可能停留在旧状态，因此资源完整性判断应以 `crawl_state.sqlite`、`resources_manifest.jsonl.local_relpath` 实际命中和只读校验脚本共同确认，不能只看 manifest 状态字段。
- RAG 修复线程已确认当前共享契约：`data/processed/huiji/dev` 为 active build，`text_child_bge_m3_v3` 为 active Milvus collection，Wiki 只读消费 RAG 确认的 source/media 字段，不直接读取 Milvus。

当前 RAG 共享契约确认值：

```text
active build_version: dev
processed artifacts: data/processed/huiji/dev
parent_count: 8246
child_count: 16010
media_count: 15758
active Milvus collection: text_child_bge_m3_v3
MinIO bucket: reverse1999-assets
MinIO object_prefix: reverse1999
MinIO public_base_url: http://127.0.0.1:9002
media index source of truth: data/processed/huiji/dev/media_assets.jsonl
```

MinIO 当前是对象池，不等于可展示资产索引。只要对象没有进入 `media_assets.jsonl`，即使存在于 MinIO，也暂时没有稳定的 `entity_id`、`child_id`、`parent_id` 和 `attach_policy` 映射，Wiki 不应自行扫描 MinIO 反推页面资源。

本设计目标分为两个层次：

1. 当前文档阶段：先把 Wiki 与 RAG 的共享数据、共享媒体和后续跳转边界写清楚，避免 Wiki 修复反向干扰 RAG 施工。
2. 后续执行阶段：基于 RAG 已确认的 MinIO、Milvus、processed artifacts 契约，恢复 Wiki 应用层。

后续 Wiki P0 应用层恢复链路为：

```text
当前确认的 MySQL + MinIO + data/processed/huiji/dev
  -> FastAPI /api/wiki/*
  -> React /wiki
  -> 只读 E2E 验证
```

Wiki P0 执行阶段以 RAG 线程确认后的 MySQL、MinIO 和 `data/processed/huiji/dev` 作为真实验收源，恢复 `/wiki`、API 契约、前端页面和只读验证脚本。构建器重跑、全量 Wiki 类目扩展、Wiki MySQL 重建和任何共享媒体写入都必须进入 P1/P2 或新的专项 plan。

## 2. 总体架构

Wiki 模块继续遵循既有原则：

```text
源数据共用，构建层分流，展示层解耦。
```

长期目标仍然是：

```text
data/huiji/res1999
  -> 统一构建器
      -> MySQL: Wiki 页面、分类、关系、别名、关键词链接、媒体映射
      -> MinIO: 共用多模态资源
      -> RAG artifacts / Milvus: 问答系统检索链路
  -> FastAPI /api/wiki/*
  -> React /wiki
```

本次修复阶段的执行边界收窄为：

```text
当前仅允许:
  docs/specs 更新
  read-only inventory / read-only verification

RAG 已确认共享契约后允许:
  Docker MySQL: reverse1999_wiki wiki_* tables
  MinIO: reverse1999-assets/reverse1999/**
  data/processed/huiji/dev/*.jsonl
    -> FastAPI /api/wiki/*
    -> React /wiki
```

Wiki 在任何阶段都不清空、不覆盖、不重建以下内容，除非 RAG 线程或后续专项 plan 明确把权限移交给 Wiki：

- Docker MySQL 中已有 Wiki 表数据。
- MinIO bucket 或 prefix。
- Milvus collection。
- `data/processed/huiji/dev` 中的 RAG artifacts。
- 原始爬虫数据目录。

当前与 RAG 线程的协调门槛已经具备确认值：

- `GATE-P0-01`：RAG 已确认 MinIO bucket 为 `reverse1999-assets`、object prefix 为 `reverse1999`、HTTP URL 规则为 `http://127.0.0.1:9002/reverse1999-assets/reverse1999/<asset_type>/<sha-prefix>/<sha>.<ext>`。
- `GATE-P0-02`：RAG 已确认 active build_version 为 `dev`，当前 `data/processed/huiji/dev/media_assets.jsonl` 为 Wiki P0 的媒体索引事实来源。
- `GATE-P0-03`：RAG 已确认 active Milvus collection 为 `text_child_bge_m3_v3`；Wiki 只记录该值用于排查，不直接读取 Milvus。
- `GATE-P0-04`：RAG 已确认 Wiki 可以只读消费 `parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl`、MinIO `url/object_key` 和 source/entity 字段，不会影响问答链路。
- `GATE-P0-05`：RAG 已确认 Wiki 可以基于以上共享契约进入 P0 应用层恢复；执行时仍不得写共享数据层。

## 3. 数据恢复边界模块

### 3.1 模块职责

数据恢复边界模块定义 Wiki 修复时可以读取什么、不能写什么，以及何时允许重跑构建器。它不是构建器实现规范，而是保护当前可用数据和 RAG 施工现场的安全边界。

### 3.2 P0 当前必须满足

- `DATA-P0-01`：Wiki P0 执行必须以 Docker MySQL、MinIO 和 RAG 已确认的 `data/processed/huiji/dev` 为真实数据源。
- `DATA-P0-02`：P0 代码和验收只能只读检查 `data/processed/huiji/dev`，不得改写 `parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl` 或索引文件。
- `DATA-P0-03`：P0 不执行会替换 Wiki MySQL 表的构建动作；如需读取 MySQL，只通过 API 或 repository 查询。
- `DATA-P0-04`：P0 不清空、不覆盖、不迁移 MinIO bucket 或 `reverse1999/` prefix。
- `DATA-P0-05`：P0 不创建、不删除、不重建 Milvus collection。
- `DATA-P0-06`：P0 验收必须明确当前数据范围是“RAG 契约稳定后的 Wiki 可消费数据”，不能宣称 Wiki 已经拥有独立的数据重建权。
- `DATA-P0-07`：原始爬虫资源虽然已恢复，但 Wiki P0 不因此获得重跑构建器、覆盖 MySQL 或上传 MinIO 的权限。
- `DATA-P0-08`：Wiki 不直接消费 Milvus，也不参与向量化；如需从 RAG 侧获得跳转字段，只通过 API/metadata 契约间接消费。
- `DATA-P0-09`：Wiki 页面资源选择以 `data/processed/huiji/dev/media_assets.jsonl` 为准，不直接遍历 MinIO 反推页面资源。
- `DATA-P0-10`：当前 `data/processed/huiji/dev/parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl` 可作为只读输入；active Milvus collection `text_child_bge_m3_v3` 只记录用于排查。

### 3.3 P1 可部分支持

- `DATA-P1-01`：在当前 RAG 共享契约基础上，若后续专项批准 Wiki 构建层恢复，则恢复 `src/huiji_wiki/builder.py`、`src/huiji_wiki/media_upload.py` 和 `scripts/build_huiji_wiki.py`。
- `DATA-P1-02`：在完整 `resources_manifest.jsonl`、`assets/files` 和后续专项执行许可同时满足后，允许以可审计方式重跑 Wiki builder，并只覆盖 Wiki 自己的 MySQL 表。
- `DATA-P1-03`：构建器输出 build report，记录页面数、媒体数、缺失资源数、跳过资源数和异常样本。
- `DATA-P1-04`：Wiki builder 如果需要引用 MinIO，只能复用 RAG 固定的 object key/URL 规则；上传逻辑必须幂等，且不得覆盖 RAG 已确认对象。

### 3.4 P2 未来演进

- `DATA-P2-01`：统一构建器一次刷新 Wiki MySQL、RAG blocks、BM25/Milvus 和 MinIO 引用。
- `DATA-P2-02`：增量构建，根据 page revision、content hash 和 media sha1 只更新变更实体。
- `DATA-P2-03`：构建任务 UI 或管理后台。

### 3.5 关键契约与限制

P0 阶段任何脚本都不得以“修复 Wiki”为理由执行 destructive 操作。尤其不得执行清库、清 bucket、重建 Milvus、删除 processed artifacts 或用 raw 资源覆盖当前 MySQL。

## 4. MinIO 媒体模块

### 4.1 模块职责

MinIO 媒体模块负责保证 Wiki 与 RAG 共用同一份多模态资源，并且浏览器只接收可访问 HTTP URL。当前 MinIO 共享协议由 RAG 线程主导，Wiki 只能只读消费。

当前 RAG 侧共享协议：

```text
bucket: reverse1999-assets
public_base_url: http://127.0.0.1:9002
object_prefix: reverse1999
url: http://127.0.0.1:9002/reverse1999-assets/reverse1999/<asset_type>/<sha-prefix>/<sha>.<ext>
```

当前 RAG 确认的媒体消费策略：

```text
image / portrait / skill: 默认可展示
voice: 只在语音面板、专门入口或明确语音 intent 下展示
video: 只在视频面板、专门入口或明确 video intent 下展示
```

当前 `media_assets.jsonl` 引用的对象已全量命中 MinIO。MinIO 中未被 `media_assets.jsonl` 引用的对象暂时忽略，不作为 Wiki 页面资源来源。

### 4.2 P0 当前必须满足

- `MEDIA-P0-01`：Wiki 与 RAG 共用同一个 MinIO 实例和 bucket `reverse1999-assets`，并遵循 RAG 固定的 `reverse1999/` object prefix。
- `MEDIA-P0-02`：P0 不新建第二套大体量 Wiki 媒体库。
- `MEDIA-P0-03`：API 返回给前端的媒体字段必须包含浏览器可用 HTTP URL，不能只返回本地路径或 object key。
- `MEDIA-P0-04`：API payload 中不得出现 `D:\`、`C:\`、`local_relpath` 等本地路径泄露。
- `MEDIA-P0-05`：`wiki_media_links.object_key` 必须保留为调试和一致性检查字段，但前端渲染图片以 `url` 为准。
- `MEDIA-P0-06`：前端主媒体区和 PageIndex 缩略图必须优先使用真实 MinIO URL；URL 不可用时显示固定尺寸占位。
- `MEDIA-P0-07`：P0 验收脚本必须能抽样检查 MySQL 中的媒体 URL 是否为 HTTP URL，并能对至少一个真实图片 URL 发起可用性检查。
- `MEDIA-P0-08`：如果未来 RAG 重建导致 object key 或 URL 规则变化，Wiki 必须按 RAG 新契约适配 API/DTO，不得自行迁移或重写 MinIO 对象。
- `MEDIA-P0-09`：Wiki 不直接遍历 MinIO 对象池，也不消费未进入 `media_assets.jsonl` 的额外对象；缺少 `entity_id/child_id/parent_id/attach_policy` 映射的对象不得展示。
- `MEDIA-P0-10`：Wiki 默认展示 `image`、`portrait`、`skill`；`voice` 必须进入折叠语音面板、独立 Tab 或明确语音入口，不得默认铺开大量语音；`video` 同理必须进入视频面板、独立 Tab 或明确 video 入口。

### 4.3 P1 可部分支持

- `MEDIA-P1-01`：在 RAG 确认允许后恢复 Wiki 侧媒体引用报告，区分 existing、missing、conflict、unresolved；是否包含 uploaded 由 RAG 共享协议决定。
- `MEDIA-P1-02`：如确需恢复上传逻辑，必须使用 RAG 固定 object key 规则；同一 sha1/object key 已存在时跳过，不覆盖冲突对象。
- `MEDIA-P1-03`：支持 thumbnail、derived webp 或尺寸字段，但不得替代原始媒体引用。

### 4.4 P2 未来演进

- `MEDIA-P2-01`：CDN、私有 bucket、签名 URL 或权限策略。
- `MEDIA-P2-02`：媒体中心、资源巡检 UI、批量重传工具。
- `MEDIA-P2-03`：Live2D 资源包结构化解析和播放器资源预加载。

### 4.5 关键契约与限制

P0 不上传、不删除、不覆盖 MinIO 对象。P0 只消费 RAG 确认可用的 URL，并用只读脚本验证 MySQL/API 引用和 MinIO 对象大体可用。

## 5. MySQL 与 FastAPI API 模块

### 5.1 模块职责

MySQL 与 API 模块负责把 Wiki 展示表稳定暴露给前端，不参与 RAG 检索，不写向量库。Wiki MySQL 是展示数据库，不是 RAG 的事实来源；RAG 侧 source/media 契约稳定后，Wiki 可以通过后续构建器把同源数据映射到展示表。

### 5.2 P0 当前必须满足

- `API-P0-01`：`GET /api/wiki/categories` 返回动态分类，分类来自 MySQL 当前数据，不写死旧 Obsidian 六分类。
- `API-P0-02`：`GET /api/wiki/pages?category=&q=&type=&limit=&cursor=` 返回列表所需字段：`pageId`、`pageType`、`title`、`subtitle`、`category`、`route`、`thumbnail`、`summary`。
- `API-P0-03`：`GET /api/wiki/pages/{page_id}` 返回详情所需字段：基础页面字段、`content`、`mediaLinks`、`relations`、`linkSpans`、`sourcePageid`、`sourceTitle`。
- `API-P0-04`：`GET /api/wiki/routes/resolve?source_id=&entity_id=&title=` 返回 `route` 和 `query`；无法解析时返回 `route: null` 和可搜索 `query`，不得抛出前端无法处理的异常。
- `API-P0-05`：`GET /api/wiki/search?q=` 可作为 pages 搜索入口，返回 Wiki 可展示页面，不直接返回 Data namespace 原始页。
- `API-P0-06`：API 失败时只影响 `/wiki` 当前区域，不影响首页、资料页、问答页。
- `API-P0-07`：repository 读取当前 MySQL 表时必须兼容现有字段：`wiki_pages`、`wiki_media_links`、`wiki_aliases`、`wiki_link_spans`、`wiki_categories`、`wiki_relations`。
- `API-P0-08`：API 响应采用前端 TypeScript DTO 使用的 camelCase 字段。
- `API-P0-09`：API 不得访问 Milvus，也不得以 Wiki 请求触发 RAG processed artifacts、MinIO 或向量库重建。
- `API-P0-10`：如果 RAG 线程后续调整 source/entity/media 字段，Wiki API 只能在自身 repository/DTO 层适配，不反向要求 RAG 为 Wiki 修改 P0 问答链路。
- `API-P0-11`：Wiki API 和 DTO 必须使用白名单字段输出媒体信息，不得向前端返回 `local_relpath`；可参考 RAG `MediaItem` 字段：`media_id`、`asset_id`、`asset_type`、`mime`、`url`、`title`、`alt`、`role`、`attach_policy`、`child_id`、`parent_id`、`panel_group`、`sort_order`、`duration_ms`。

### 5.3 P1 可部分支持

- `API-P1-01`：完善 alias fallback、分页游标、分类排序和搜索排序。
- `API-P1-02`：恢复 MySQL schema creation 和 migration guard，但只在明确执行构建或迁移任务时使用。
- `API-P1-03`：增加 `/api/wiki/pages/by-route` 或 route fallback，支持从 URL route 解析 page detail。

### 5.4 P2 未来演进

- `API-P2-01`：专用搜索索引、全文检索优化或拼音/别名搜索。
- `API-P2-02`：后台编辑、版本管理、人工修正表。

### 5.5 关键契约与限制

API 层不得访问 Milvus；不得以 Wiki 请求触发数据构建、MinIO 上传或 destructive migration。Wiki API 的职责是展示与跳转，不是 RAG 数据生产入口。

## 6. 前端 Wiki 工作区模块

### 6.1 模块职责

前端 Wiki 工作区负责恢复 `/wiki` 独立浏览体验，并与现有首页、资料页、问答页三屏滚轮结构隔离。

### 6.2 P0 当前必须满足

- `FRONTEND-P0-01`：`/wiki` 独立于三屏 scroll snap，不作为首页、资料页、问答页后的第四屏。
- `FRONTEND-P0-02`：TopNav 入口、Sidebar 入口、资料页“日历”最后页右下角 `进入WIKI` 入口都跳转到 `/wiki`。
- `FRONTEND-P0-03`：Wiki 页面采用四区结构：`CategoryRail(hidden) | PageIndex | WikiReader | PageInfo`。
- `FRONTEND-P0-04`：布局比例满足 `右信息栏 < 左分类唤出宽度 = 条目列表 < 主阅读区`。
- `FRONTEND-P0-05`：`CategoryRail` 平时隐藏在左边界；鼠标贴近左边界或悬停达到与顶部导航一致的延迟后唤出。
- `FRONTEND-P0-06`：`CategoryRail` 展示 API 返回的动态分类，只改变筛选条件，不直接渲染页面正文。
- `FRONTEND-P0-07`：`PageIndex` 常驻显示，支持搜索输入、当前分类筛选状态和页面列表。
- `FRONTEND-P0-08`：`PageIndex` 卡片显示标题、副标题、页面类型、缩略图和摘要。
- `FRONTEND-P0-09`：`WikiReader` 是最大阅读区域，负责根据 `pageType` 选择模板。
- `FRONTEND-P0-10`：`PageInfo` 为窄右栏，显示来源、媒体数、关系数、链接数、route 和 outline，不抢主阅读区空间。
- `FRONTEND-P0-11`：MySQL/API 不可用时，`/wiki` 显示稳定错误状态，并保留返回主站入口。
- `FRONTEND-P0-12`：MinIO 图片不可用时，前端使用固定尺寸占位，避免布局跳动。

### 6.3 P1 可部分支持

- `FRONTEND-P1-01`：Category metadata 传递 `animationProfile`、`templateGroup`、`themeToken`，为后续分类切换动效和差异化模板预留接口。
- `FRONTEND-P1-02`：支持从 query 参数进入指定搜索词或指定 pageId。
- `FRONTEND-P1-03`：移动端适配为 PageIndex/Reader 优先，PageInfo 和 CategoryRail 可折叠。

### 6.4 P2 未来演进

- `FRONTEND-P2-01`：高级筛选、排序、收藏、浏览历史。
- `FRONTEND-P2-02`：复杂响应式布局和多列内容密度配置。

### 6.5 关键契约与限制

前端不直接读本地文件系统，不读取 `public/wiki/**` 静态 manifest 作为主数据源，不在浏览器端做复杂实体识别。

## 7. Wiki 页面模板模块

### 7.1 模块职责

模板模块负责把 API detail payload 渲染为可观察的数据面。P0 重在基础可读、字段正确、媒体足够大，不追求最终视觉和复杂动效。

### 7.2 P0 当前必须满足

- `TEMPLATE-P0-01`：`WikiReader` 至少支持 `CharacterPage`、`PsychubePage`、`StoryPage`、`GenericWikiPage` 四类模板入口。
- `TEMPLATE-P0-02`：角色页主媒体窗口足够大，真实 URL 存在时展示图片，而不是只显示小缩略图。
- `TEMPLATE-P0-03`：角色页立绘、Live2D、皮肤属于同一个 `CharacterMediaStage`，通过切换按钮切换显示。
- `TEMPLATE-P0-04`：Live2D 资源解析或播放器未就绪时，不隐藏 Live2D 入口；点击后显示同尺寸 fallback。
- `TEMPLATE-P0-05`：媒体 fallback 不改变媒体窗口尺寸。
- `TEMPLATE-P0-06`：角色页展示基础资料、摘要、技能或结构化内容中当前 API 能提供的字段。
- `TEMPLATE-P0-07`：心相页展示大图、基础资料、效果或故事字段；缺字段时显示稳定空状态。
- `TEMPLATE-P0-08`：剧情页展示封面或章节视觉、基础资料、正文或关卡/章节字段；缺字段时显示稳定空状态。
- `TEMPLATE-P0-09`：通用页能展示标题、来源、摘要或结构化内容，但不得把 Data namespace 原始 JSON 直接暴露为未整理的代码块。
- `TEMPLATE-P0-10`：页面模板默认渲染图片类资源；语音资源只能以折叠面板、独立 Tab 或明确入口呈现，不得在页面加载时批量铺开。

### 7.3 P1 可部分支持

- `TEMPLATE-P1-01`：扩展物品、活动、敌人、机制、资源等模板组。
- `TEMPLATE-P1-02`：模板根据 category metadata 调整局部布局和字段优先级。
- `TEMPLATE-P1-03`：更多媒体 role 的优先级排序，例如 portrait、skin、cover、skill、gallery、voice。

### 7.4 P2 未来演进

- `TEMPLATE-P2-01`：复杂关系图谱。
- `TEMPLATE-P2-02`：完整 Live2D 播放器。
- `TEMPLATE-P2-03`：媒体中心式皮肤、语音、视频浏览。
- `TEMPLATE-P2-04`：高度定制的页面动效和转场。

### 7.5 关键契约与限制

模板只消费 API 返回的 `content`、`mediaLinks`、`relations`、`linkSpans`。模板不得自行访问 MySQL、MinIO SDK 或本地磁盘。

## 8. 关键词链接模块

### 8.1 模块职责

关键词链接模块负责把 API 返回的 `linkSpans` 渲染为蓝色可点击链接，并在目标缺失时稳定降级。

### 8.2 P0 当前必须满足

- `LINK-P0-01`：同一段文本中多个关键词都能渲染为蓝色链接。
- `LINK-P0-02`：同一段文本中重复关键词可以按 span 信息多次渲染，不只匹配第一个。
- `LINK-P0-03`：有 `targetRoute` 的关键词点击跳转到对应 Wiki 页面。
- `LINK-P0-04`：缺失 `targetRoute` 的关键词降级为普通文本或搜索 fallback，不生成空链接。
- `LINK-P0-05`：前端只渲染 API 提供的 spans，不在浏览器端扫描全文做复杂实体识别。

### 8.3 P1 可部分支持

- `LINK-P1-01`：支持低置信 span 的样式差异或禁用。
- `LINK-P1-02`：支持 alias fallback 和 route resolve 点击前校验。
- `LINK-P1-03`：支持跳转后高亮目标页面段落。

### 8.4 P2 未来演进

- `LINK-P2-01`：禁用自动链接词表。
- `LINK-P2-02`：同名实体消歧 UI。
- `LINK-P2-03`：人工确认关系修正表。

### 8.5 关键契约与限制

蓝色链接只能表达高置信页面跳转，不能为了视觉密度把低置信词全部染蓝。

## 9. RAG 跳转边界模块

### 9.1 模块职责

RAG 跳转边界模块只定义 Wiki 为后续问答来源跳转提供什么接口，不要求当前问答链路立即改造。当前 RAG 线程优先修复问答链路，Wiki 跳转字段属于后续兼容项。

### 9.2 P0 当前必须满足

- `RAGLINK-P0-01`：Wiki P0 修复不得修改 RAG 检索链路、入库流程、向量化流程或聊天输出格式。
- `RAGLINK-P0-02`：Wiki 保留稳定 route，例如 `/wiki/char/{id}`、`/wiki/psychube/{id}`、`/wiki/story/{id}`、`/wiki/page/{id}`。
- `RAGLINK-P0-03`：`routes/resolve` 能用 `entity_id`、`source_id`、`title` 中的可用字段尝试解析 Wiki route。
- `RAGLINK-P0-04`：解析失败时返回 search fallback 所需 query，不中断前端。
- `RAGLINK-P0-05`：RAG 线程未提供 `wiki_route` 或稳定 source 字段前，Wiki 只保留 resolve API 契约，不把 RAG source card 跳转纳入当前验收。

### 9.3 P1 可部分支持

- `RAGLINK-P1-01`：当 RAG 输出 sources 后，前端可通过 `wiki_route` 直接跳转。
- `RAGLINK-P1-02`：当 RAG 只有 `source_id`、`entity_id` 或 `title` 时，前端调用 `/api/wiki/routes/resolve` 后跳转。
- `RAGLINK-P1-03`：RAG source card 展示 Wiki 入口按钮。

### 9.4 P2 未来演进

- `RAGLINK-P2-01`：RAG 答案内嵌媒体和 Wiki 页面共用媒体组件。
- `RAGLINK-P2-02`：来源跳转到指定段落。
- `RAGLINK-P2-03`：问答页与 Wiki 页之间的上下文返回栈。

### 9.5 关键契约与限制

Wiki 不能依赖 RAG 页面完成入库、检索、输出格式调整后才能工作。RAG 也不能依赖 Wiki 前端页面存在才能回答问题。双方只通过稳定 route、source/entity 字段和 HTTP 媒体 URL 做低耦合对接。

## 10. 动效扩展模块

### 10.1 模块职责

动效扩展模块负责保留 ReactBits 或其他动效组件的接入位置。本阶段不选择具体 ReactBits 组件。

### 10.2 P0 当前必须满足

- `ANIMATION-P0-01`：业务组件不得写死具体 ReactBits 组件名。
- `ANIMATION-P0-02`：`CategoryRail`、`PageIndex`、`WikiReader`、`CharacterMediaStage`、`PageInfo` 和关键词链接保留可识别的区域边界，便于后续接入动效。
- `ANIMATION-P0-03`：category metadata 中允许保留 `animationProfile`、`templateGroup`、`themeToken` 字段，即使 P0 不使用复杂动效。

### 10.3 P1 可部分支持

- `ANIMATION-P1-01`：为页面切换和列表入场实现最小 CSS transition，不引入大型新依赖。
- `ANIMATION-P1-02`：为 ReactBits 组件建立 wrapper 层，避免业务组件直接绑定第三方组件 API。

### 10.4 P2 未来演进

- `ANIMATION-P2-01`：按用户指定的 ReactBits 组件逐区接入动效。
- `ANIMATION-P2-02`：不同分类或模板使用不同动效 profile。
- `ANIMATION-P2-03`：媒体切换、页面转场、列表 hover 和 PageInfo 更新动效统一编排。

### 10.5 关键契约与限制

动效不能阻塞 P0 数据面恢复。任何动效都不能破坏图片尺寸稳定、关键词可点击性、阅读区滚动和可访问性。

## 11. 验证模块

### 11.1 模块职责

验证模块负责把当前修复闭环从“组件能渲染”提升到“真实 MySQL + MinIO + API + React 可用”。在 RAG 施工期间，验证只允许文档核对和只读数据清点；进入 Wiki 执行阶段后，P0 验证必须只读。

### 11.2 P0 当前必须满足

- `VERIFY-P0-01`：Wiki 执行前必须记录 RAG 已确认的 active build_version `dev`、active Milvus collection `text_child_bge_m3_v3`、MinIO 协议和媒体消费策略。
- `VERIFY-P0-02`：进入 Wiki 执行阶段后，恢复只读 `scripts/verify_huiji_wiki_e2e.py`，它只请求 API 和抽样检查 URL，不写 MySQL、MinIO、Milvus 或 processed artifacts。
- `VERIFY-P0-03`：验收脚本能验证 page detail payload 中不存在本地路径泄露。
- `VERIFY-P0-04`：验收脚本能验证至少一个 `mediaLinks[].url` 是 HTTP URL。
- `VERIFY-P0-05`：验收脚本能对至少一个真实图片 URL 执行可用性检查，并输出明确结果。
- `VERIFY-P0-06`：前端单测覆盖 PageIndex 富卡片、CategoryRail 唤出状态、PageInfo、KeywordText、CharacterMediaStage fallback 和 WikiShell 错误态。
- `VERIFY-P0-07`：浏览器手动验收覆盖 `/wiki` 加载真实条目、主阅读区显示真实 MinIO 图片、Live2D 同窗口 fallback、多个关键词链接、三个入口跳转。
- `VERIFY-P0-08`：完成判定不得只依赖单测通过，必须包含至少一条真实数据链路验收记录。
- `VERIFY-P0-09`：只读验收必须确认 `media_assets.jsonl` 引用的 `object_key` 在 MinIO 中可命中，且 Wiki 不消费 MinIO 中未被 `media_assets.jsonl` 引用的对象。
- `VERIFY-P0-10`：只读验收必须确认 Wiki API payload 不包含 `local_relpath`，并确认语音资源不会在默认页面批量展开。

### 11.3 P1 可部分支持

- `VERIFY-P1-01`：后续构建阶段加入 `verify_huiji_res1999` 和 Wiki builder report 的联动检查。
- `VERIFY-P1-02`：恢复构建器单测、repository 集成测试和 API contract tests。
- `VERIFY-P1-03`：将 MinIO object_key 与 `media_assets.jsonl` 全量一致性检查升级为定期巡检；P0 只做一次性只读覆盖验收。

### 11.4 P2 未来演进

- `VERIFY-P2-01`：Playwright 截图验收桌面和移动端布局。
- `VERIFY-P2-02`：性能预算、图片加载失败率、API 延迟监控。
- `VERIFY-P2-03`：自动巡检 Wiki 页面样本集。

### 11.5 关键契约与限制

P0 验证脚本必须默认安全，只读运行；任何会改写数据的验证都必须另列为 P1 后续构建验收。

## 12. 跨模块数据流

RAG 共享契约确认后的 Wiki P0 数据流：

```text
Docker MySQL wiki_* tables
data/processed/huiji/dev/parent_blocks.jsonl
data/processed/huiji/dev/child_blocks.jsonl
data/processed/huiji/dev/media_assets.jsonl
  -> src/huiji_wiki/repository.py
  -> backend/wiki.py
  -> /api/wiki/categories
  -> /api/wiki/pages
  -> /api/wiki/pages/{page_id}
  -> /api/wiki/routes/resolve
  -> React /wiki
```

媒体数据流：

```text
wiki_media_links.object_key/url
data/processed/huiji/dev/media_assets.jsonl object_key/url
  -> API mediaLinks + list thumbnail
  -> PageIndex thumbnail
  -> CharacterMediaStage / template media
  -> fixed-size fallback if unavailable
```

RAG 后续跳转流：

```text
RAG source or keyword
  -> wiki_route if present
  -> /api/wiki/routes/resolve if only source_id/entity_id/title exists
  -> /wiki search fallback if unresolved
```

## 13. 错误处理原则

| 场景 | P0 行为 |
|---|---|
| MySQL 不可用 | `/wiki` 显示“Wiki 数据服务未启动”或等价错误态，不影响主站其他页面 |
| 分类为空 | 显示空状态，提示当前 Wiki 数据不可用 |
| 页面不存在 | 保留列表和搜索，阅读区显示未找到 |
| API 请求失败 | 当前区域显示错误态，其他区域保持可用 |
| MinIO 图片不可用 | 显示固定尺寸占位，不改变媒体窗口尺寸 |
| Live2D 不可用 | 同媒体窗口显示 fallback，不隐藏切换入口 |
| 关键词目标不存在 | 降级为普通文本或搜索 fallback |
| RAG route 无法解析 | 跳转 `/wiki` 搜索 fallback，不中断 |

## 14. 测试与验收方向

后续 plan 应只把本 specs 的 P0 作为主线任务，并为每个 P0 条目提供实现位置、测试命令、真实数据验收方式和失败表现。当前已有 Wiki plan 在 RAG 线程施工期间只能作为历史参考和待重写清单；正式执行前必须先核对 `GATE-P0-*`，再按本 specs 重新生成或修订 plan。

P0 最小验收集合：

- `GATE-P0-*` 全部满足，并记录 RAG 线程确认的 MinIO 协议、processed artifacts build_version 和可消费字段。
- 记录 active build_version 为 `dev`，active Milvus collection 为 `text_child_bge_m3_v3`。
- 后端 API 能从当前 Docker MySQL 读取 categories、pages、page detail 和 route resolve。
- API payload 不包含本地路径泄露。
- API payload 不包含 `local_relpath`。
- PageIndex 列表展示真实缩略图、页面类型、副标题和摘要。
- WikiReader 能打开至少一个真实角色页面。
- 主媒体区域能显示真实 MinIO 图片。
- Live2D 切换入口存在，播放器未接入时显示同窗口 fallback。
- KeywordText 支持同一段中多个关键词和重复关键词。
- `/wiki` 不进入三屏 scroll snap。
- TopNav、Sidebar、日历页三个入口均进入 `/wiki`。
- 只读 E2E 验证脚本能对真实页面输出安全媒体 URL 检查结果。
- 只读 E2E 验证脚本能确认 `media_assets.jsonl` 引用对象在 MinIO 命中，且未引用的 MinIO 对象不会进入 Wiki 页面资源。

## 15. 与旧方案的关系

本设计继承 `2026-07-04-huiji-wiki-frontend-design.md` 的核心方向：

- 灰机数据 + MySQL + FastAPI + React `/wiki`。
- Wiki 不读 Milvus，不参与向量化。
- Wiki 与 RAG 共用 MinIO。
- `/wiki` 是独立工作区。
- 四区布局、左分类隐藏唤出、三个入口、关键词链接、Live2D fallback、动效挂点。

本设计修正旧 specs 的组织方式：

- 按模块组织，并在模块内划分 P0/P1/P2。
- 使用稳定编号，便于后续 plan 引用。
- 把当前代码丢失、爬虫资源已恢复、RAG 已确认共享数据/媒体契约纳入设计事实。
- 把 Wiki P0 应用层恢复限定为只读消费 `data/processed/huiji/dev`、MinIO HTTP URL 和 Wiki MySQL/API，不写共享数据层。

`2026-07-01-reverse1999-wiki-browser-design.md` 继续视为 OUTDATED。它只保留历史交互意图，不再作为当前数据源、构建方式或 API 契约依据。

## 16. 与 RAG 修复线程的关系

RAG 修复线程是共享数据层的主导方，负责 MinIO、Milvus、向量化、processed artifacts、问答 API 和聊天前端的闭环。RAG 已确认 Wiki 可以只读消费 `data/processed/huiji/dev`、MinIO `url/object_key` 和 source/entity 字段；Wiki 模块仍不得写入这些共享资源。

Wiki 当前允许执行：

- 修改本 specs。
- 读取 RAG specs、RAG plan 和 review guide。
- 只读清点 `data/huiji/res1999`、`data/processed/huiji/dev`、MySQL 和 MinIO 状态。
- 基于已确认契约执行 Wiki P0 应用层恢复。

Wiki 当前不允许执行：

- 编写或恢复 Wiki 前后端代码。
- 重跑 Wiki builder。
- 覆盖 Wiki MySQL 表。
- 上传、删除、迁移或重命名 MinIO 对象。
- 创建、删除、重建或切换 Milvus collection。
- 修改 RAG 问答链路、向量化链路或聊天前端输出格式。

当前 plan 已按 RAG 确认的共享契约重写；执行时必须把本 specs 中的 `GATE-P0-*` 作为第一组强制验收门槛，并记录具体确认值。

当前 RAG 已确认的 API/SSE 媒体白名单字段为：

```text
media_id, asset_id, asset_type, mime, url, title, alt, role,
attach_policy, child_id, parent_id, panel_group, sort_order, duration_ms
```

`local_relpath` 只允许停留在处理产物内部，不得进入 Wiki API、RAG API/SSE 或浏览器 payload。
