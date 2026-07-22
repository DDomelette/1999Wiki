# Wiki Recovery Summary

日期：2026-07-07

本文档用于在前端 Wiki 模块、构建脚本或相关文档发生丢失时，快速恢复项目上下文和执行顺序。它不是新的设计源头，而是对现有 specs、plans、runbook 的总索引。

## 1. 恢复目标

恢复目标是让灰机 Wiki 数据重新形成可验证链路：

```text
data/huiji/res1999
  -> 统一构建器
      -> MySQL: Wiki 页面、分类、关系、别名、关键词链接、媒体映射
      -> MinIO: 共用多模态资源
      -> RAG artifacts / Milvus: 问答系统检索链路
  -> FastAPI /api/wiki/*
  -> React /wiki
```

核心原则：

- 源数据共用，构建层分流，展示层解耦。
- Wiki 使用 MySQL 作为展示数据库，不读取 Milvus，不参与向量化。
- RAG 使用 Milvus/BM25/构建产物，不依赖 Wiki 前端页面存在。
- 多模态资源只保留一份，Wiki 与 RAG 共用 MinIO bucket `reverse1999-assets`。
- 浏览器只接收 HTTP URL，不接收本地磁盘路径。

## 2. 首要文档

恢复时优先阅读以下文档：

1. `docs/specs-and-plans-review-guide.md`
   说明 specs 与 plan 的职责边界。Specs 管架构，plan 管执行验收。

2. `docs/superpowers/specs/2026-07-04-huiji-wiki-frontend-design.md`
   Wiki 前端、API、MySQL、MinIO、RAG 跳转边界的当前设计源头。

3. `docs/superpowers/plans/2026-07-06-huiji-wiki-frontend.md`
   Wiki 模块首轮落地计划，适合恢复基础骨架。

4. `docs/superpowers/plans/2026-07-07-huiji-wiki-p0-completion.md`
   Wiki P0 补全计划，适合恢复媒体链路、模板、关键词跳转和 E2E 验收。

5. `docs/huiji-rag-runbook.md`
   构建、切换、真实数据验收命令。

6. `docs/rag-assets.md`
   MinIO bucket、访问地址和媒体 URL 约定。

## 3. 关联设计文档

RAG 与数据链路：

- `docs/superpowers/specs/2026-07-03-huiji-parent-child-hybrid-rag-design.md`
- `docs/superpowers/plans/2026-07-03-huiji-parent-child-hybrid-rag.md`

角色实体包与问答路由：

- `docs/superpowers/specs/2026-07-04-character-entity-packet-routing-design.md`
- `docs/superpowers/plans/2026-07-04-character-entity-packet-routing.md`

爬虫与源数据：

- `docs/superpowers/specs/2026-07-03-huiji-crawler-command-reference.md`
- `docs/superpowers/specs/2026-07-02-huiji-res1999-crawler-design.md`
- `docs/superpowers/plans/2026-07-02-huiji-res1999-crawler.md`

灾备策略：

- `docs/backend-recovery-strategy.md`
- `docs/frontend-recovery-strategy.md`
- `docs/superpowers/plans/2026-07-07-recover-cleaned-huiji-sources.md`

## 4. 推荐恢复顺序

### 4.1 先恢复文档和边界

确认以下边界不被破坏：

- Wiki 不写 `data/processed/documents.jsonl`。
- Wiki 不清空 Milvus collection。
- Wiki 不复用 RAG 的文本清洗逻辑删除图片语法。
- Wiki 构建只读 `data/huiji/res1999`，只写 Wiki MySQL 表和 MinIO 对象。
- RAG 与 Wiki 通过 route、source_id、entity_id、title 等稳定字段衔接。

### 4.2 再恢复后端构建层

优先恢复这些模块：

```text
src/huiji_wiki/models.py
src/huiji_wiki/builder.py
src/huiji_wiki/repository.py
src/huiji_wiki/media_upload.py
scripts/build_huiji_wiki.py
scripts/verify_huiji_wiki_e2e.py
backend/wiki.py
backend/wiki_schemas.py
```

最低验收：

- `wiki_pages` 能写入 MySQL。
- `wiki_media_links.url` 是 HTTP URL。
- `wiki_media_links` 不暴露 `local_relpath`。
- `routes/resolve` 找不到目标时返回 `route: null` 和可搜索 query。
- `verify_huiji_wiki_e2e.py` 能检查真实页面 payload。

### 4.3 再恢复前端 Wiki 页面

优先恢复这些模块：

```text
frontend/react-app/src/api/wiki.ts
frontend/react-app/src/types/wiki.ts
frontend/react-app/src/components/wiki/WikiShell.tsx
frontend/react-app/src/components/wiki/CategoryRail.tsx
frontend/react-app/src/components/wiki/PageIndex.tsx
frontend/react-app/src/components/wiki/WikiReader.tsx
frontend/react-app/src/components/wiki/PageInfo.tsx
frontend/react-app/src/components/wiki/KeywordText.tsx
frontend/react-app/src/components/wiki/templates/*
```

布局要求：

```text
右信息栏 < 左分类唤出宽度 = 条目列表 < 主阅读区
```

当前推荐宽度：

- CategoryRail 收起：`28px`
- CategoryRail 唤出：`280px`
- PageIndex：`280px`
- PageInfo：`220px`
- Reader：`flex: 1`

入口要求：

- 顶部导航栏入口。
- 侧边栏入口。
- 资料页“日历”最后页右下角 `进入WIKI` 入口。

### 4.4 最后恢复测试和验收

后端目标测试：

```powershell
python -m pytest tests/test_huiji_wiki_models.py tests/test_huiji_wiki_builder.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py tests/test_huiji_wiki_media_upload.py tests/test_huiji_wiki_build_script.py tests/test_minio_shared_upload.py tests/test_huiji_wiki_e2e_script.py -q
```

前端目标测试：

```powershell
cd frontend/react-app
npm test -- src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx src/components/wiki/KeywordText.test.tsx src/components/wiki/WikiShell.test.tsx src/components/wiki/CategoryRail.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx --run
```

前端构建：

```powershell
cd frontend/react-app
npm run build
```

真实数据验收：

```powershell
python scripts/build_huiji_wiki.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
cd frontend/react-app
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

打开：

```text
http://127.0.0.1:5173/wiki
```

至少确认：

- `/wiki` 能加载。
- PageIndex 显示缩略图、页面类型、副标题、摘要。
- 主阅读区显示真实 MinIO 图片。
- Live2D 与立绘共用同一媒体窗口，播放器缺失时显示 fallback。
- 关键词可以变蓝并跳转。
- PageInfo 显示 source、media 数、relation 数、link 数和 outline。

## 5. 必须保留的 P0 行为

后端：

- MySQL 目标库不存在时可自动创建。
- `wiki_media_links` 包含 `object_key`、`url`、`asset_type`、`mime`、`title`、`sha1`、`width`、`height`。
- API 列表页 thumbnail 来自页面第一张可用媒体 URL。
- API 详情页 mediaLinks 返回浏览器可用 HTTP URL。
- API payload 不出现 `D:\`、`C:\`、`local_relpath`。

前端：

- `/wiki` 是独立工作区，不是三屏 scroll snap 的第四屏。
- 左分类平时隐藏在左边界，鼠标贴近左边界或悬停后唤出。
- 条目列表支持搜索。
- 角色页主媒体区域足够大，图片不只作为小缩略图显示。
- Live2D 与立绘用同一窗口，通过切换按钮切换。
- `KeywordText` 支持一段中多个关键词和重复关键词。
- 缺失 target route 时关键词降级为普通文本，不生成空链接。

## 6. 当前已知风险

- 如果 `data/huiji/res1999/assets/files` 不完整，构建报告会出现大量 `media_missing_local_files`。这属于源资源完整性问题，不应通过复制旧前端图片目录解决。
- 如果 `.env` 缺少 `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 或 `MYSQL_PASSWORD`，真实构建会失败。优先修环境变量，不把密钥写进代码。
- 如果 MySQL 容器不是本项目 Docker 中的 `edurag-mysql`，需要先确认 `config/settings.yaml` 和 `.env` 指向正确实例。
- 如果前端代码丢失，不要从旧 Obsidian 静态 Wiki exporter 回退；当前正式方向是灰机数据 + MySQL + FastAPI + React `/wiki`。

## 7. 不应恢复的旧方案

以下旧方案只作为历史参考，不应作为当前恢复方向：

- Base64 内嵌图片。
- 前端直接读本地磁盘图片路径。
- 使用 `data/raw` 作为 Wiki 数据源。
- 复用 RAG `clean_markdown()` 作为 Wiki 展示清洗逻辑。
- 把 Wiki 数据混入 `documents.jsonl` 或 Milvus 文本块。
- 为 Wiki 和 RAG 分别保存两套大体量图片资源。

## 8. 最小恢复完成定义

满足以下条件时，可以认为 Wiki 恢复到 P0 可继续迭代状态：

- Wiki specs 和 plans 均存在并可读。
- `python scripts/build_huiji_wiki.py` 能成功写入 Docker MySQL。
- 至少一个真实页面通过 `scripts/verify_huiji_wiki_e2e.py`。
- `/wiki` 浏览器页面能加载真实条目和真实 MinIO 图片。
- 后端目标测试、前端目标测试和 `npm run build` 通过。
- RAG 构建、Milvus collection 和问答页面未因 Wiki 恢复被重置或破坏。
