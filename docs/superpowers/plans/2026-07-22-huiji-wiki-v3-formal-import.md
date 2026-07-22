# Huiji Wiki v3 正式事务导入实施计划

依据 Spec：`docs/superpowers/specs/2026-07-22-huiji-wiki-v3-formal-import-design.md`

执行模式：单线程执行，不使用子代理；在 dirty worktree 中只修改 Wiki 正式导入相关文件，不清理其他线程改动。Plan 是本轮强制验收门槛。

## 1. 目标范围

本轮必须完成：`AUTH-P0-01..05`、`PAYLOAD-P0-01..06`、`MYSQL-P0-01..07`、`VERIFY-P0-01..06`、`EVIDENCE-P0-01..05`。

禁止修改：RAG active pointer、RAG transaction 文件、Milvus collection、MinIO 对象、candidate artifacts、rollback dump、前端视觉设计。

## 2. 冻结输入与预期输出

| 输入 | 冻结值 |
|---|---|
| activation ID | `candidate-f-generation-1-20260722d` |
| build | `crawler-v3-20260721t051246z` |
| handoff SHA-256 | `884e6ae0ef10911564a84ec3c3ec5b3f57939fc47475ab68599d04ca14d4e90a` |
| activation receipt SHA-256 | `78310c7f0009c6df88413f5a888940d4aa404073b81ef001ebc9d1a6eb3d7f58` |
| active pointer SHA-256 | `87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e` |
| rollback receipt SHA-256 | `e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6` |
| pages/categories | `7456 / 4` |
| resources/bindings | `19132 / 19400` |
| legacy links retained | `17527` |

## 3. 强制验收门槛

| 检查点 | Specs | 实现位置 | 自动化与真实验收 | 失败表现 |
|---|---|---|---|---|
| C1 授权闭环 | `AUTH-P0-01..05` | `src/huiji_wiki/formal_import.py` | tamper/path/hash pytest；真实 handoff inspect | 任一 pin 漂移即无 dry-run/apply receipt |
| C2 Payload 保真 | `PAYLOAD-P0-01..06` | `formal_import.py`、`importer.py` | frozen count/closure pytest；真实 payload 计数 | 计数、唯一性或闭环不符即停止 |
| C3 双表安装 | `MYSQL-P0-01..02` | `media_schema.py`、formal import CLI | migration pytest；正式库 SHOW TABLES/COUNT | DROP/RENAME、未知非空表即失败 |
| C4 单事务切换 | `MYSQL-P0-03..06` | `importer.py`、`formal_import.py` | commit/rollback pytest；真实 inventory before/after | 多次 commit、snapshot 早写、legacy links 删除即失败 |
| C5 受保护状态 | `MYSQL-P0-07` | evidence capture | before/after SHA 与 MinIO/Milvus只读状态 | RAG/MinIO/Milvus/candidate 漂移即失败 |
| C6 API 验收 | `VERIFY-P0-01..04` | 8000 Wiki API | health + 分类/详情请求 | stale、计数错误、URL/双 ID 缺失即失败 |
| C7 页面与 RAG | `VERIFY-P0-05..06` | React + 8000 | Playwright/HTTP smoke；RAG health/ask | Wiki 白屏或 RAG 回归即失败 |
| C8 证据与幂等 | `EVIDENCE-P0-01..05` | formal import CLI/evidence | receipt schema/hash pytest；重复 inspect | 覆盖证据、泄密、部分状态冒充成功即失败 |

## 4. 执行步骤

### Step 1：实现正式授权与 payload inspector

- 对应 Specs：`AUTH-P0-01..05`、`PAYLOAD-P0-01..06`、`EVIDENCE-P0-01`。
- 创建：`src/huiji_wiki/formal_import.py`、`scripts/import_huiji_wiki_v3.py`。
- 测试：`tests/test_huiji_wiki_formal_import.py`、`tests/test_huiji_wiki_formal_import_cli.py`。
- 验收：真实 `--inspect` 输出 frozen inputs、payload counts、MySQL pre-state；不执行 DDL/DML。

### Step 2：修正 importer 事务与 legacy 保留契约

- 对应 Specs：`MYSQL-P0-03..06`。
- 修改：`src/huiji_wiki/importer.py`、相关 importer/media v3 tests。
- 实现：显式 begin/rollback；成功一次 commit；v3 不清空 `wiki_media_links`；snapshot 最后写。
- 验收：SQL 序列断言和正式导入前 legacy count baseline 均为 17,527。

### Step 3：实现 create-new evidence 与幂等状态机

- 对应 Specs：`MYSQL-P0-01..02`、`EVIDENCE-P0-01..05`。
- 实现：`inspect -> prepared -> committed -> verified`；失败 create-new failure receipt；目标 snapshot 完整时 `already_installed`。
- 验收：tamper、重复运行、部分双表状态、未知 snapshot 全部 fail closed。

### Step 4：运行自动化测试与正式 dry-run

- 对应 Specs：全部 P0 的代码门槛。
- 命令：Wiki focused pytest、全量 pytest、前端 Vitest/build。
- 真实验收：执行 `--inspect`，确认 7,456/4/19,132/19,400、legacy 17,527、v3 表尚未安装。
- 失败时：不执行 apply。

### Step 5：执行 schema apply 与事务化正式导入

- 对应 Specs：`MYSQL-P0-01..07`、`EVIDENCE-P0-02..05`。
- 前置：再次验证所有冻结 SHA、正式 authority 和 rollback receipt。
- 执行：幂等创建双表；确认空表；单事务 full replace；写 installed snapshot；生成 post inventory。
- 验收：精确行数和 snapshot SHA，legacy links 保持 17,527。
- 失败时：事务内异常自动 rollback；提交后异常按 receipt 执行完整 restore，不做局部修补。

### Step 6：重启 8000 并执行真实 API/页面/RAG 验收

- 对应 Specs：`VERIFY-P0-01..06`。
- 验收：Wiki health、分类、角色/心相/剧情/item detail、多绑定媒体、React 选人/详情；RAG health 和一次只读 ask。
- 页面重点：槲寄生、至少一个多皮肤角色、至少一个共享媒体页面。
- 失败时：生成 failure receipt 并按提交状态决定 restore。

### Step 7：封存 passing receipt 与回填 Plan

- 对应 Specs：`EVIDENCE-P0-01..05`。
- 输出目录：`eval/huiji_wiki_v3_import/candidate-f-generation-1-20260722d/`。
- 输出：inspect、pre/post inventory、API smoke、protected compare、P0 matrix、formal import receipt 及 SHA sidecar。
- 回填：逐项记录实际命令、测试数、行数、URL 和结果。

## 5. 可选任务

本轮不执行 P1。legacy links 退役、全站截图回归和通用多 generation orchestration 仅保留接口。

## 6. Deferred / Out of Scope

- 新一轮 Builder、embedding 或 Milvus 切换。
- MinIO 上传、删除、迁移或 orphan 清理。
- Wiki 视觉重构和动效调整。
- 自动删除 legacy tables/data。
- 修改 RAG handoff 或 activation receipt。

## 7. 完成后自检表

- [x] C1 `AUTH-P0-01..05`：正式授权闭环通过。
- [x] C2 `PAYLOAD-P0-01..06`：真实 payload 精确且闭环。
- [x] C3 `MYSQL-P0-01..02`：双表安全安装。
- [x] C4 `MYSQL-P0-03..06`：单事务提交且 legacy links 保留。
- [x] C5 `MYSQL-P0-07`：受保护状态无漂移。
- [x] C6 `VERIFY-P0-01..04`：8000 Wiki API v3 验收通过。
- [x] C7 `VERIFY-P0-05..06`：React Wiki 与 RAG smoke 通过。
- [x] C8 `EVIDENCE-P0-01..05`：passing receipt、幂等和失败闭锁通过。

## 8. 实际执行记录

执行日期：2026-07-22。

- 正式 inspect：通过；导入前 MySQL 为 `legacy/dev`，`7456` 页面、`4` 分类、`17527` legacy 媒体关系，inventory SHA-256 与 rollback receipt 一致。
- 后端门禁：项目环境全量 `1338 passed, 2 skipped`；正式导入相关聚焦回归 `14 passed`。
- 前端门禁：Vitest `48` files / `234` tests 全部通过；`tsc && vite build` 通过。
- 正式导入：使用确认词 `IMPORT WIKI CANDIDATE F GENERATION 1` 一次事务提交成功。
- 正式库结果：`7456` 页面、`4` 分类、`19132` 媒体资源、`19400` 媒体绑定；`17527` legacy links 保留。
- installed snapshot：`active / crawler-v3-20260721t051246z / evb.media-asset/v3 / epoch 1`，snapshot SHA-256 为 `7529288166e2304d2e31cad7777a5fb8173e830ece13d340fae0650d08f019a1`。
- 8000 重启后 RAG health：`ok`，Milvus active 文档数 `14630`，provenance `pass`。
- Wiki API：health、4 类计数、角色/心相/剧情/item detail 通过；槲寄生返回 `229` 条 v3 binding，DTO 含 `bindingId/resourceId` 且不暴露 `objectKey/localRelpath`。
- 浏览器门禁：正式 `/wiki` 选人和详情在 desktop/mobile 共 `2 passed`，真实立绘、传承和塑造模块均完成加载。
- RAG 只读问答：`介绍一下十四行诗` 返回 grounded answer、来源与媒体，未触发 failure action。
- 受保护状态：active pointer、handoff、activation receipt、candidate manifest、media v3 manifest 与 rollback receipt 的冻结 SHA 全部不变；本轮 MinIO/Milvus/RAG pointer 写操作均为 `0`。
- P0 matrix：`8/8 passed`。
- 重复 inspect：返回 `already_installed`，未执行 DDL/DML；结果单独封存为 `inspection.post-import.v1.json`，未复用导入前证据路径。
- 正式 receipt：`eval/huiji_wiki_v3_import/candidate-f-generation-1-20260722d/formal_import_receipt.v1.json`，SHA-256 `76909a9cbb85ce81e4e4a746a780b8836423ee9b6e921c503249cade1a87a23f`。
