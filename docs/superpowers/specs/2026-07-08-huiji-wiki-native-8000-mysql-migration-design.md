# Huiji Wiki 原生 8000 与 MySQL 迁移设计

日期：2026-07-08
项目：`1999Search`
状态：RAG 侧已审核通过，等待执行计划落地

## 1. 背景与目标

当前 Wiki 模块已经完成 P0/P1 恢复，并且 `backend/main.py` 已经挂载 `backend.wiki.router`：

```python
from backend.wiki import router as wiki_router
app.include_router(wiki_router)
```

路由结构上，Wiki 已经具备并入 `127.0.0.1:8000` 的条件。之前临时使用 `127.0.0.1:8001` 是为了绕开旧的 8000 进程配置缓存问题，不应成为正式链路。

本设计目标：

- 将 Wiki 作为本项目原生模块并入 FastAPI `:8000`。
- 停止正式使用 `:8001` Wiki-only 服务。
- 前端 `/wiki` 继续作为 React 原生页面，不使用 iframe、静态 manifest 或外部转发服务。
- 新增 `GET /api/wiki/health`，独立检查 Wiki MySQL 可读性。
- 将 `reverse1999_wiki` 从 `edurag-mysql` 迁移到本项目 Docker MySQL，迁移方式为 dump/restore。
- 保持 Wiki 与 RAG 解耦：Wiki 不触碰 Milvus、RAG `_state`、向量化、MinIO 写操作或 RAG 输出格式。

## 2. 总体架构

目标链路：

```text
React /wiki
  -> /api/wiki/*
  -> FastAPI :8000
  -> backend/wiki.py
  -> src/huiji_wiki/repository.py
  -> project-owned MySQL reverse1999_wiki
  -> MinIO HTTP media URL
```

RAG 链路继续：

```text
React chat
  -> /ask 或 /ask/stream
  -> FastAPI :8000
  -> RAG chain / Retriever / Milvus / processed artifacts / MinIO
```

统一原则：

```text
同一 FastAPI 入口，数据层边界分离，配置变更以进程重启为一致性边界。
```

## 3. 原生 8000 后端模块

### 3.1 模块职责

原生 8000 后端模块负责让 `/api/wiki/*` 在 `backend.main:app` 下稳定服务，避免再依赖 8001。

### 3.2 P0 当前必须满足

- `NATIVE-P0-01`: `/api/wiki/*` 必须由 `backend.main:app` 的 8000 端口提供。
- `NATIVE-P0-02`: `backend.main` 可以继续 `include_router(wiki_router)`；Wiki router 不调用 `_ensure_loaded()`。
- `NATIVE-P0-03`: RAG 初始化失败但 MySQL 可用时，`/api/wiki/*` 仍允许继续服务。
- `NATIVE-P0-04`: 不在 Wiki 请求中调用 `reset_config_for_test()`，不清理 `get_config()` 缓存，不重置 RAG `_state`。
- `NATIVE-P0-05`: `.env`、MySQL、MinIO、Milvus 配置变更后，以重启 8000 作为一致性边界。
- `NATIVE-P0-06`: `GET /api/wiki/health` 返回 Wiki 独立健康状态，不扩展 `/health` response schema。
- `NATIVE-P0-07`: 虽然 Wiki router 不调用 `_ensure_loaded()`，但 `backend.main` startup 仍可能触发 RAG 初始化；验收必须实测 8000 冷启动到 `/api/wiki/health` 的耗时，如果 Milvus 连接长时间卡住，不得宣称原生 8000 合并完成。

### 3.3 P1 可部分支持

- `NATIVE-P1-01`: 后续可以在运维页聚合 `/health` 和 `/api/wiki/health`，但不改变现有 RAG `/health` 契约。

### 3.4 P2 未来演进

- `NATIVE-P2-01`: 未来 Docker 打包时可以把 FastAPI、React、MySQL、Milvus、MinIO 整合成统一 compose 入口。

### 3.5 关键限制

Wiki router 不得参与 RAG 生命周期管理。RAG `_state` 只由 RAG 启动、健康检查和问答请求维护。

## 4. 前端代理模块

### 4.1 模块职责

前端代理模块负责让 Vite dev 环境与正式部署路径一致。Wiki 前端永远请求相对路径 `/api/wiki/*`。

### 4.2 P0 当前必须满足

- `PROXY-P0-01`: Vite 默认 `/api/wiki` 代理目标必须是 `apiTarget`，即 `http://127.0.0.1:8000`。
- `PROXY-P0-02`: `VITE_WIKI_API_TARGET` 只作为临时调试覆盖项，不作为默认值。
- `PROXY-P0-03`: 停止正式使用 8001 后，刷新 `/wiki` 必须仍能加载真实页面。

### 4.3 P1 可部分支持

- `PROXY-P1-01`: 保留 `VITE_WIKI_API_TARGET` 可覆盖能力，用于未来隔离调试，但文档中标明不是正式链路。

### 4.4 P2 未来演进

- `PROXY-P2-01`: Docker 部署时可移除 Vite dev proxy，改由反向代理或 FastAPI 静态服务统一入口。

### 4.5 关键限制

前端不得写死 8001，也不得把 Wiki 数据来源切回静态 manifest。

## 5. MySQL 迁移模块

### 5.1 模块职责

MySQL 迁移模块负责把 Wiki 展示库 `reverse1999_wiki` 从 `edurag-mysql` 迁移到本项目 Docker MySQL，方便后续项目整体打包部署。

### 5.2 P0 当前必须满足

- `MYSQL-P0-01`: 迁移方式必须是 `mysqldump`/`mysql restore`，不得复制 MySQL volume 文件。
- `MYSQL-P0-02`: 迁移只覆盖 `reverse1999_wiki`，不得迁移或删除 `subjects_kg` 等其他项目库。
- `MYSQL-P0-03`: 目标 MySQL 使用本项目 Docker 服务，初始 host 端口使用 `3307:3306`，避免与 `edurag-mysql:3306` 冲突。
- `MYSQL-P0-04`: 迁移完成前不得停止或删除 `edurag-mysql`。
- `MYSQL-P0-05`: 迁移后必须校验核心表行数：`wiki_pages`、`wiki_categories`、`wiki_media_links`、`wiki_link_spans`、`wiki_aliases`。
- `MYSQL-P0-06`: `.env` 切到项目 MySQL 后必须重启 8000。
- `MYSQL-P0-07`: 如果任一 Wiki 或 RAG 冒烟验证失败，必须将 `.env` 回滚到旧 MySQL，并重启 8000。
- `MYSQL-P0-08`: 源库 `edurag-mysql` 密码不得写死默认值，必须来自显式参数、环境变量或 Docker 容器环境；解析不到源库密码时迁移脚本必须中止。

### 5.3 P1 可部分支持

- `MYSQL-P1-01`: 后续可把 MySQL 初始化 SQL、用户权限和备份目录纳入统一 Docker runbook。
- `MYSQL-P1-02`: 后续可为 Wiki builder 添加只覆盖 Wiki 表的 migration guard。

### 5.4 P2 未来演进

- `MYSQL-P2-01`: 支持版本化 schema migration 工具，例如 Alembic 或 Flyway。
- `MYSQL-P2-02`: 支持定时备份与恢复演练。

### 5.5 风险判断

风险可控。Wiki MySQL 数据量很小，风险主要来自错误地迁移整个容器或直接复制 volume。只要坚持 dump/restore、保留旧库、逐项验收、失败回滚，风险低于直接 volume 迁移。

## 6. 共享媒体与 RAG 边界模块

### 6.1 模块职责

该模块确保 Wiki 原生化不会扩大到 RAG 媒体构建或 MinIO 写入。

### 6.2 P0 当前必须满足

- `MEDIA-RAG-P0-01`: Wiki 继续只消费 MySQL 中已有 HTTP URL 和 `media_assets.jsonl` 派生字段。
- `MEDIA-RAG-P0-02`: Wiki 不扫描 MinIO 对象池反推资源。
- `MEDIA-RAG-P0-03`: Wiki 不上传、删除、迁移 MinIO 对象。
- `MEDIA-RAG-P0-04`: RAG 当前媒体契约仍以 `data/processed/huiji/dev/media_assets.jsonl` 为准。

### 6.3 P1 可部分支持

- `MEDIA-RAG-P1-01`: 后续可把媒体覆盖巡检加入定期命令，但仍只读。

### 6.4 P2 未来演进

- `MEDIA-RAG-P2-01`: 后续可以在统一资源中心展示媒体健康状态。

### 6.5 关键限制

MySQL 迁移不是 MinIO 迁移。MinIO 仍沿用当前共享实例和 bucket。

## 7. 验证模块

### 7.1 模块职责

验证模块负责证明合并后 Wiki 是 8000 原生模块，并且 RAG 功能没有被破坏。

### 7.2 P0 当前必须满足

- `VERIFY-NATIVE-P0-01`: `GET http://127.0.0.1:8000/api/wiki/health` 返回 `ready: true` 和 `pageCount > 0`。
- `VERIFY-NATIVE-P0-02`: `GET http://127.0.0.1:8000/api/wiki/pages?limit=3` 返回非空 `items`。
- `VERIFY-NATIVE-P0-03`: `GET http://127.0.0.1:8000/api/wiki/pages/by-route?route=/wiki/char/<id>` 返回详情。
- `VERIFY-NATIVE-P0-04`: `GET http://127.0.0.1:8000/health` 可返回 RAG 自身状态；若 RAG 初始化失败，不能阻止 `/api/wiki/*` 在 MySQL 可用时服务。
- `VERIFY-NATIVE-P0-05`: 前端 `http://127.0.0.1:5173/wiki` 显示真实页面，不显示 `0 pages`。
- `VERIFY-NATIVE-P0-06`: `/ask` 或 `/ask/stream` 至少完成一次 RAG 冒烟验证。
- `VERIFY-NATIVE-P0-07`: 停止 8001 后，`/wiki` 仍可用。
- `VERIFY-NATIVE-P0-08`: 重启 8000 后，`/api/wiki/health` 必须在约定启动超时时间内返回；如果 RAG 初始化依赖长时间卡住，该验收失败。

### 7.3 P1 可部分支持

- `VERIFY-NATIVE-P1-01`: 后续可以加入浏览器截图或 Playwright 稳定视觉回归。

### 7.4 P2 未来演进

- `VERIFY-NATIVE-P2-01`: 完整 Docker 环境下做冷启动到页面可用的端到端测试。

### 7.5 关键限制

不能只凭单元测试宣布迁移完成。必须包含真实 8000、真实 MySQL、真实 `/wiki` 页面验证。

## 8. 数据流

迁移前：

```text
React /wiki
  -> /api/wiki/*
  -> FastAPI :8000 或临时 :8001
  -> edurag-mysql:3306/reverse1999_wiki
```

迁移后：

```text
React /wiki
  -> /api/wiki/*
  -> FastAPI :8000
  -> project MySQL :3307/reverse1999_wiki
```

RAG 不变：

```text
React chat
  -> FastAPI :8000
  -> Milvus text_child_bge_m3_v3
  -> data/processed/huiji/dev
  -> MinIO reverse1999-assets
```

## 9. 错误处理原则

| 场景 | 行为 |
|---|---|
| RAG 初始化失败 | `/health.status` 可为 `error`，但 `/api/wiki/*` 在 MySQL 可用时继续服务 |
| RAG 初始化长时间卡住 | 8000 启动到 `/api/wiki/health` 的耗时验收失败，先修启动策略或依赖可用性，不把 Wiki 合并判定为完成 |
| Wiki MySQL 不可用 | `/api/wiki/health` 返回 `ready: false`，前端 Wiki 显示局部错误态 |
| 目标 MySQL 迁移后行数不一致 | 不切换 `.env`，保留旧库 |
| 切换 `.env` 后 Wiki 验证失败 | 回滚 `.env` 到旧 MySQL，重启 8000 |
| RAG 冒烟失败 | 暂停迁移完成判定，回滚 MySQL 配置 |
| 8001 仍在运行 | 不作为失败，但正式验收必须证明停止 8001 后 Wiki 可用 |

## 10. 与旧方案关系

`8001 Wiki-only` 只保留为历史调试手段，不再作为正式链路。当前原生化设计取代此前“临时双后端”做法。

旧的 P1 hard-gate plan 已完成的 API、前端、媒体巡检能力继续保留；新的执行计划应聚焦：

- 8000 原生入口收束；
- `/api/wiki/health`；
- Vite 默认代理回到 8000；
- project-owned MySQL dump/restore 迁移；
- 停止 8001 后真实验收。
