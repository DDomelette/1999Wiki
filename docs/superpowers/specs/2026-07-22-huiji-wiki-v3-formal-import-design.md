# Huiji Wiki v3 正式事务导入设计

日期：2026-07-22

## 1. 背景与目标

Candidate F 已作为 generation 1 active RAG，RAG 线路已签发 hash-pinned `wiki_import_handoff.v1.json`。Wiki 当前仍安装 `legacy/dev` 快照，正式库为 `reverse1999-main-mysql/reverse1999_wiki`，当前基线为 7,456 页面和 17,527 条 legacy 媒体关系。

本设计只负责把已激活的 crawler-only v3 artifact 事务化投影到 Wiki MySQL，并完成 API 与真实页面验收。它不修改 RAG active pointer、Milvus、MinIO、Builder artifact 或 RAG 配置。

正式数据流固定为：

```text
active_build.v1.json
  -> hash-pinned Candidate F artifacts
  -> Wiki 离线 payload
  -> reverse1999_wiki 事务导入
  -> /api/wiki/*
  -> React Wiki
```

## 2. 导入授权与输入门禁模块

### 2.1 模块职责

证明当前导入对象就是已提交的 RAG generation 1，并且 Wiki 具备可执行的生产回滚路径。

### 2.2 P0 当前必须满足

- `AUTH-P0-01`：正式入口必须验证 handoff 文件本身的期望 SHA-256、schema、`status=passed`、`wiki_import_allowed=true`、`wiki_import_status=not_started` 和 generation 1。
- `AUTH-P0-02`：handoff pin 的 activation receipt、active pointer、candidate manifest、media v3 manifest、compatibility receipt 和 pre-import rollback receipt 必须逐项存在且 SHA-256 相等。
- `AUTH-P0-03`：active pointer 的 generation、activation ID、build version、artifact schema 和 collection 必须与 handoff 一致；任何漂移均停止。
- `AUTH-P0-04`：pre-import rollback receipt 必须通过 canonical bytes、内部 hash、dump、sidecar、restore entrypoint 和正式 authority 校验。
- `AUTH-P0-05`：正式入口只接受项目内相对路径，不接受未激活 candidate 目录、任意 processed path 或路径逃逸。

### 2.3 P1 可部分支持

- `AUTH-P1-01`：后续可把 handoff 状态回写为独立 Wiki completion receipt；不得改写 RAG 原始 handoff。

### 2.4 P2 未来演进

- `AUTH-P2-01`：多 generation 自动编排与审批服务。

### 2.5 关键契约与限制

RAG handoff 是只读授权凭据，不是导入成功证明。Wiki 不得编辑 RAG transaction 目录中的文件。

## 3. Payload 构建与保真模块

### 3.1 模块职责

在接触 MySQL 前完整解析 active snapshot，并将一行一绑定的 v3 artifact 规范化为页面、资源和绑定多重集。

### 3.2 P0 当前必须满足

- `PAYLOAD-P0-01`：只从 active snapshot 读取 `parent_blocks.jsonl`、`child_blocks.jsonl` 和 `runtime/media_assets.v3.jsonl`。
- `PAYLOAD-P0-02`：正式导入必须是 authoritative full replace，且包含 character crawler projection；不读取 Obsidian、`data/raw` 或前端镜像。
- `PAYLOAD-P0-03`：每条 v3 row 必须通过冻结字段顺序、ID 算法、HTTP URL、hash、source refs、非负数值与禁止本地路径校验。
- `PAYLOAD-P0-04`：同一 `resource_id` 的多条 `binding_id` 必须全部保留；资源可去重，绑定不可去重。
- `PAYLOAD-P0-05`：本轮 Candidate F 的导入前基线固定为 7,456 pages、4 categories、19,132 resources、19,400 bindings；任一计数变化均需新 Spec/Plan，不得静默继续。
- `PAYLOAD-P0-06`：payload 必须验证页面 ID、route、resource ID、binding ID 唯一，binding 引用的 page/resource 全部闭环。

### 3.3 P1 可部分支持

- `PAYLOAD-P1-01`：输出分类和媒体角色分布诊断，不参与导入授权。

### 3.4 P2 未来演进

- `PAYLOAD-P2-01`：增量页面与绑定 diff。

### 3.5 关键契约与限制

Builder artifact 是唯一媒体关系权威。Wiki 不扫描 MinIO 反推绑定，也不因页面视觉需求改写 artifact。

## 4. MySQL 事务与双表切换模块

### 4.1 模块职责

安装 v3 schema，并在一个业务事务中更新页面、分类、资源、绑定和 installed snapshot。

### 4.2 P0 当前必须满足

- `MYSQL-P0-01`：DDL 只允许幂等创建 `wiki_media_resources` 与 `wiki_media_bindings`；不得 DROP、RENAME 或修改 legacy 表。
- `MYSQL-P0-02`：DDL 完成后必须确认两张 v3 表为空；非空但 installed snapshot 不是目标 snapshot 时停止。
- `MYSQL-P0-03`：页面、分类、资源、绑定和 `wiki_import_snapshots` 更新必须在单个显式事务中完成；异常显式 rollback，成功只 commit 一次。
- `MYSQL-P0-04`：installed snapshot 只在所有业务行成功写入后更新为 `active/crawler-v3-20260721t051246z/evb.media-asset/v3/generation 1`。
- `MYSQL-P0-05`：`wiki_media_links` 及其现有 17,527 行必须保留。本轮 repository 通过 installed snapshot 选择 v3 双表，不以删除 legacy 数据实现切换。
- `MYSQL-P0-06`：提交后行数必须精确为 7,456 pages、4 categories、19,132 resources、19,400 bindings；snapshot SHA 必须等于离线 snapshot。
- `MYSQL-P0-07`：操作前后不得修改 RAG、Milvus、MinIO、active pointer、candidate artifact 或 rollback dump。

### 4.3 P1 可部分支持

- `MYSQL-P1-01`：正式稳定期结束后可单独规划 legacy links 退役；本轮不执行。

### 4.4 P2 未来演进

- `MYSQL-P2-01`：蓝绿 Wiki schema 和零停机 metadata pointer。

### 4.5 关键契约与限制

MySQL DDL 会隐式提交，因此 DDL 与业务 DML 分为两个阶段。DDL 只创建空表，完整业务状态仍由后续单事务保证。提交后验收失败时，使用已验证 rollback receipt 恢复完整 legacy 数据库，不做局部人工修补。

## 5. API 与页面验收模块

### 5.1 模块职责

证明安装 snapshot 后 repository 实际走 v3 双表，且 8000 上的 Wiki API 与 React 页面可消费真实数据。

### 5.2 P0 当前必须满足

- `VERIFY-P0-01`：重启 8000 以清除 `get_config()` 单例缓存与连接状态，不在请求中 reset RAG `_state`。
- `VERIFY-P0-02`：`/api/wiki/health` 必须 ready，报告 v3 schema、7,456 pages、19,132 resources、19,400 bindings，且 snapshot 不 stale。
- `VERIFY-P0-03`：抽验角色、心相、剧情和 item 页面；detail DTO 不得出现 `local_relpath`、Windows 路径或 MinIO object key。
- `VERIFY-P0-04`：槲寄生及至少两个共享媒体/多皮肤角色必须返回非空 `bindingId`、`resourceId`、HTTP URL，且同资源多绑定不丢失。
- `VERIFY-P0-05`：React `/wiki/character` 与角色详情页必须能加载选人列表、正式立绘、皮肤/语音/藏品/尤提姆中已有的 v3 绑定；失败不得宣称导入完成。
- `VERIFY-P0-06`：RAG `/health` 与一次只读问答 smoke 必须保持通过；Wiki 验收不得触发向量化、collection 切换或 MinIO 写入。

### 5.3 P1 可部分支持

- `VERIFY-P1-01`：扩大到所有页面类型的截图回归与媒体抽样。

### 5.4 P2 未来演进

- `VERIFY-P2-01`：持续化 Wiki/RAG 联合发布门禁。

### 5.5 关键契约与限制

自动化测试通过不能替代真实 MySQL、API 和浏览器链路验收。

## 6. 证据与恢复模块

### 6.1 模块职责

为 dry-run、正式 apply、提交后验收和失败状态输出 create-new、hash-pinned 证据。

### 6.2 P0 当前必须满足

- `EVIDENCE-P0-01`：dry-run receipt 记录全部输入 pin、payload 计数、当前 MySQL inventory 和无写入声明。
- `EVIDENCE-P0-02`：apply receipt 记录事务前后 inventory、installed snapshot、提交状态、API smoke 和 P0 matrix。
- `EVIDENCE-P0-03`：失败只能产生 failure receipt，不得覆盖 passing receipt 或 RAG handoff。
- `EVIDENCE-P0-04`：重复执行在目标 snapshot 已安装且行数/hash 一致时返回 `already_installed`；发现部分状态或未知漂移时停止。
- `EVIDENCE-P0-05`：证据不得包含数据库密码、API key、绝对外部路径或本地媒体路径。

### 6.3 P1 可部分支持

- `EVIDENCE-P1-01`：生成供下一次 RAG activation 使用的 Wiki installed receipt。

### 6.4 P2 未来演进

- `EVIDENCE-P2-01`：签名发布清单与远程审计存储。

## 7. 跨模块执行顺序

```text
validate handoff and rollback authority
  -> resolve immutable active snapshot
  -> build and validate full payload
  -> emit dry-run receipt
  -> create empty v3 tables
  -> revalidate all pins and MySQL pre-state
  -> one DML transaction
  -> verify MySQL post-state
  -> restart 8000
  -> API + React + RAG smoke
  -> emit passing apply receipt
```

## 8. 与旧方案的关系

- 继承 `2026-07-20-huiji-wiki-media-v3-compatibility-design.md` 的双 ID、双表、crawler-only 和 repository 双读契约。
- 继承 `2026-07-21-huiji-wiki-pre-import-rollback-design.md` 的正式 authority 与 restore receipt。
- 只读消费 `2026-07-22-huiji-rag-candidate-f-activation-design.md` 的 handoff，不修改其文件。
- 本设计专门补足此前明确 deferred 的“v3 candidate 正式导入 Wiki MySQL”。

## 9. 完成判定

只有全部 P0 条目具有代码、测试和真实链路证据，且 apply receipt 为 passing，才能声明 Wiki 已切换到 v3。保留 legacy links 不代表仍在使用 legacy；读取权威由 installed snapshot schema 决定。
