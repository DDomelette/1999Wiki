# Huiji Wiki Media v3 兼容实施计划

执行模式：在现有 dirty worktree 中单线程执行，不使用子代理，不清理或回滚其他线程改动。本计划不导入 candidate，不修改 MySQL 业务数据、MinIO、Milvus 或 active pointer。

## 1. 目标范围

本轮必须完成：`SNAPSHOT-P0-01..04`、`MYSQL-P0-01..07`、`API-P0-01..04`、`FRONTEND-P0-01..04`、`RECEIPT-P0-01..05`。

本轮只建立兼容能力、schema migration dry-run/apply 工具、rollback guard、测试和回执生成器。正式 v3 数据导入、active 切换和 rollback 执行不在本轮。

## 2. 强制验收门槛

| 检查点 | Specs | 自动化门槛 | 真实状态门槛 | 失败表现 |
|---|---|---|---|---|
| C1 文档边界 | 全部 | placeholder/来源词扫描 | 旧来源明确作废 | 文档仍把 Obsidian/supplement 作为正式来源则失败 |
| C2 Snapshot 双读 | `SNAPSHOT-P0-01..04` | snapshot pytest | pointer 不存在时保持 legacy | 隐式 candidate/pointer 推断则失败 |
| C3 双表规范化 | `MYSQL-P0-01..07` | importer/schema/migration pytest | dry-run 不连接或改写业务表 | 任一 binding 被资源去重折叠则失败 |
| C4 API 兼容 | `API-P0-01..04` | repository/API pytest | legacy API 仍可序列化 | 本地路径泄漏或旧字段消失则失败 |
| C5 React 身份 | `FRONTEND-P0-01..04` | Vitest | legacy 页面构建通过 | v3 相同 mediaId 多 binding 被覆盖则失败 |
| C6 回执 | `RECEIPT-P0-01..05` | receipt pytest | fixture 缺失时 blocker | fixture 缺失却发布 passing receipt 则失败 |
| C7 受保护状态 | 全部 | git/path/命令审计 | 未写 MySQL/MinIO/Milvus/active | 任一生产状态变化则失败 |

## 3. 执行步骤

### Step 1：冻结 Wiki 兼容文档

- 对应 Specs：全部 P0。
- 修改位置：本 Spec、本 Plan；旧 Wiki Spec 的 superseded 标注。
- 实现要点：crawler-only 来源、v3 双 ID、blocked activation 和不导入 candidate。
- 测试：`rg` 扫描正式来源描述和 placeholder。
- 验收：P0 编号可机械映射到本计划检查点。

### Step 2：实现严格 snapshot 分支与媒体规范化

- 对应 Specs：`SNAPSHOT-P0-01..04`、`MYSQL-P0-03`、`MYSQL-P0-07`。
- 修改位置：`src/huiji_wiki/snapshot.py`、新增 `src/huiji_wiki/media_v3.py`、`src/huiji_wiki/importer.py`。
- 实现要点：显式 v3 路径/manifest；字段、ID 和 URL 验证；一行一绑定拆分，不折叠 binding。
- 测试：`tests/test_huiji_wiki_snapshot.py`、新增 `tests/test_huiji_wiki_media_v3.py`、`tests/test_huiji_wiki_importer.py`。
- 真实验收：当前 pointer 缺失时仍解析 legacy build，且不创建 pointer。

### Step 3：实现 MySQL schema migration 与 rollback guard

- 对应 Specs：`MYSQL-P0-01..06`、`RECEIPT-P0-05`。
- 修改位置：新增 `src/huiji_wiki/media_schema.py`、`scripts/migrate_wiki_media_v3.py`、测试文件。
- 实现要点：两张新表；默认 dry-run；apply 只建表；rollback 默认拒绝，只有空表和显式参数才生成/执行 DROP。
- 测试：新增 `tests/test_huiji_wiki_media_v3_migration.py`。
- 真实验收：本轮只运行 dry-run，不对 Docker MySQL 执行 apply/rollback。

### Step 4：贯通 importer、repository、API

- 对应 Specs：`MYSQL-P0-04..07`、`API-P0-01..04`。
- 修改位置：`src/huiji_wiki/importer.py`、`src/huiji_wiki/models.py`、`src/huiji_wiki/repository.py`、`backend/wiki_schemas.py`。
- 实现要点：legacy/v2 走旧表，v3 走双表 join；DTO 增量字段；health 分表计数；事务更新 snapshot。
- 测试：`tests/test_huiji_wiki_importer.py`、`tests/test_huiji_wiki_repository.py`、`tests/test_huiji_wiki_api.py`。
- 真实验收：现有 legacy fixtures 的响应保持兼容。

### Step 5：贯通 React binding identity

- 对应 Specs：`FRONTEND-P0-01..04`。
- 修改位置：`frontend/react-app/src/types/wiki.ts`、`wikiViewModel.ts`、`characterDetailViewModel.ts` 及相关测试。
- 实现要点：统一 `wikiMediaBindingKey()`；v3 优先 `bindingId`；不按资源身份折叠关系。
- 测试：相关 Vitest suites 和 `npm run build`。
- 真实验收：相同 `mediaId`、不同 `bindingId` 的两条媒体均进入 view model。

### Step 6：实现 compatibility receipt

- 对应 Specs：`RECEIPT-P0-01..05`。
- 修改位置：新增 `src/huiji_wiki/compatibility_receipt.py`、`scripts/build_wiki_media_v3_compatibility_receipt.py` 和测试。
- 实现要点：固定四 fixture 路径、SHA-256、规范化计数与多绑定证明；create-new evidence；禁止 fixture 缺失时 passing。
- 测试：新增 `tests/test_huiji_wiki_media_v3_compatibility_receipt.py`。
- 真实验收：若 RAG Task 1 fixture 尚不存在，命令返回 `blocked_shared_fixture_missing`，不生成 passing receipt。

### Step 7：全量自检

- 对应 Specs：全部 P0。
- 测试：后端 Wiki pytest、前端 Vitest、TypeScript build、migration dry-run、receipt blocker/成功 fixture 测试。
- 真实验收：确认未执行 importer、migration apply、rollback、MinIO/Milvus 命令或 active pointer 写入。

## 4. 可选任务

本轮不执行 P1。candidate preview、legacy fallback binding 诊断和 provenance UI 仅保留设计接口。

## 5. Deferred / Out of Scope

- 正式 candidate 构建、embedding、shadow collection 和 active 切换。
- v3 candidate 正式导入 Wiki MySQL。
- 删除旧 `wiki_media_links`、MinIO orphan 或任何已有业务对象。
- Wiki 视觉布局、动效和顶层分类调整。
- 自动 activation orchestration 和历史版本 UI。

## 6. 完成后自检表

- [x] `SNAPSHOT-P0-01..04`：legacy/v2/v3 显式分支和 active gate 完成。
- [x] `MYSQL-P0-01..07`：双表 schema、规范化、事务和 dry-run/rollback guard 完成。
- [x] `API-P0-01..04`：双 ID 与语义字段贯通，旧 API 和 URL 安全不回归。
- [x] `FRONTEND-P0-01..04`：binding identity 贯通，不折叠共享资源绑定。
- [x] `RECEIPT-P0-01..05`：回执工具完成；共享 fixture 缺失时保持 blocked。
- [x] 所有自动化测试与构建通过。
- [x] MySQL、MinIO、Milvus、active pointer 和现有 artifacts 未被修改。

## 7. 执行结果（2026-07-20）

- 后端 Wiki 全量回归：`97 passed`。
- 前端 Vitest 全量回归：`48` 个测试文件、`233 passed`。
- 前端 TypeScript 与 Vite 构建：通过；仅保留非阻塞的 chunk size 提示。
- migration：仅执行默认 dry-run，未连接或写入 Docker MySQL。
- compatibility receipt：真实运行返回 `blocked_shared_fixture_missing`，缺少 RAG 冻结的四个共享 fixture；退出码为 `2`，且未生成 passing receipt。
- 受保护状态：`active_build.v1.json` 不存在，passing receipt 不存在；未执行 importer apply、migration apply/rollback、MinIO、Milvus 或 active 切换命令。
