# Huiji Wiki Media v3 兼容设计

日期：2026-07-20

## 1. 背景与目标

Wiki 当前生产数据仍使用 crawler-only legacy/v2 artifacts、`wiki_media_links` 和单一 `media_id`。新的 corpus builder 冻结了 `evb.media-asset/v3`：artifact 一行表示一条绑定，同一物理资源允许被多个页面、区块或角色复用。

本设计让 Wiki 在不导入未验证 candidate、不修改 active pointer、不写 MinIO/Milvus 的前提下同时兼容当前 legacy/v2 与未来 v3。正式 v3 导入必须等待 RAG candidate 通过 fidelity gates 并由用户批准 active 切换。

正式来源流固定为：

```text
crawler raw -> corpus builder -> active artifacts -> Wiki MySQL projection -> /api/wiki/* -> React
```

旧文档中将 `data/raw`、Obsidian、`wiki_page_supplements` 或 Wiki 私有 MinIO 前缀作为正式来源的条款自本设计起全部作废。

## 2. Snapshot 与 Artifact 读取模块

### 2.1 模块职责

只从配置锁定的 legacy build 或经 `active_build.v1.json` 显式激活的 build 解析 Wiki 导入快照。按 schema 选择固定媒体路径并验证 manifest，不通过字段猜测版本。

### 2.2 P0 当前必须满足

- `SNAPSHOT-P0-01`：继续支持 `evb.media-asset/v1_legacy` 与 `evb.media-asset/v2`，当前生产导入行为不变。
- `SNAPSHOT-P0-02`：支持 `evb.media-asset/v3`，媒体路径固定为 `runtime/media_assets.v3.jsonl`，manifest schema 固定为 `evb.media-artifact-manifest/v3`。
- `SNAPSHOT-P0-03`：active pointer 不存在时继续使用已配置 legacy build，不得隐式创建 generation 0、pointer 或 activation receipt。
- `SNAPSHOT-P0-04`：v3 只能由有效 active pointer 或测试显式构造的隔离 snapshot 读取；正式导入命令不得接受未激活 candidate 目录。

### 2.3 P1 可部分支持

- `SNAPSHOT-P1-01`：在独立 preview 数据库验证 hash-pinned candidate，不进入生产导入命令。

### 2.4 P2 未来演进

- `SNAPSHOT-P2-01`：远程 artifact registry 与自动保留策略。

### 2.5 关键契约与限制

v2 历史 manifest 可显式兼容 `evb.media-artifact-manifest/v2` 与 `evb.media-assets-manifest/v2`；v3 只接受一个冻结名称。任何路径、hash、schema 或 containment 校验失败均停止导入。

## 3. 媒体规范化与 MySQL 模块

### 3.1 模块职责

把 v3 一行一绑定 artifact 投影为资源实体与绑定关系。Builder 不维护第二份资源 artifact，Wiki 只在导入边界规范化。

### 3.2 P0 当前必须满足

- `MYSQL-P0-01`：新增 `wiki_media_resources`，以 `resource_id` 保存物理资源身份、兼容 `media_id`、HTTP URL、object key、哈希、MIME、尺寸和可用状态。
- `MYSQL-P0-02`：新增 `wiki_media_bindings`，以 `binding_id` 保存 page/owner/parent/child/section/role/variant/skin/event/language/source token、排序和绑定状态。
- `MYSQL-P0-03`：同一 `resource_id` 可以对应多条 binding；不得按 SHA、object key、URL、`resource_id` 或兼容 `media_id` 折叠绑定。
- `MYSQL-P0-04`：legacy/v2 继续写入 `wiki_media_links`；v3 写入资源表和绑定表。repository 根据已安装 snapshot schema 选择读取分支。
- `MYSQL-P0-05`：schema migration 默认 dry-run，只创建新表；rollback 只在新表为空或提供经验证备份证据时允许执行。
- `MYSQL-P0-06`：正式 v3 full replace 必须在一个事务中完成页面、资源、绑定和 snapshot metadata 更新；失败整体回滚。
- `MYSQL-P0-07`：v3 row 必须通过冻结字段、ID、HTTP URL、hash、非负数值和禁止 `local_relpath` 校验后才能进入 payload。

### 3.3 P1 可部分支持

- `MYSQL-P1-01`：为 legacy/v2 生成诊断用 fallback binding identity；不得伪装为 v3 `binding:sha256:*`。

### 3.4 P2 未来演进

- `MYSQL-P2-01`：增量绑定导入和历史版本查询。

### 3.5 关键契约与限制

`resource_id` 是内容身份，`binding_id` 是关系身份，兼容 `media_id` 仅是资源别名。数据库迁移不导入 candidate，不扫描 MinIO 反推关系，不删除旧表或旧数据。

## 4. API 模块

### 4.1 模块职责

向现有前端提供向后兼容的 page detail，同时完整暴露 v3 绑定语义，不泄漏本地路径或内部构建证据。

### 4.2 P0 当前必须满足

- `API-P0-01`：媒体 DTO 增加 `bindingId`、`resourceId`、`ownerEntityId`、`ownerPageId`、`skinId`、`eventName`、`language`、`sourceBindingToken` 和 `bindingStatus`。
- `API-P0-02`：继续返回 `mediaId`、`assetId`、`role`、`variant`、`sectionKey` 和现有渲染字段，legacy/v2 客户端不破坏。
- `API-P0-03`：仅返回 HTTP(S) URL；不返回 `objectKey`、local path、source refs 或凭据。
- `API-P0-04`：`/api/wiki/health` 分别报告 legacy link、resource、binding 数量和当前 schema；当前 legacy 生产状态仍可 ready。

### 4.3 P1 可部分支持

- `API-P1-01`：按 binding/role/skin 的服务端媒体筛选。

### 4.4 P2 未来演进

- `API-P2-01`：媒体管理与版本 diff API。

### 4.5 关键契约与限制

API 增量扩展字段，不删除现有字段。v3 DTO 中 `bindingId` 必须存在；legacy/v2 DTO 允许前端回退到 `mediaId` 作为渲染 key。

## 5. React 消费模块

### 5.1 模块职责

使用绑定身份渲染列表、建立映射和选择媒体，保留同一资源的多个合法关系。

### 5.2 P0 当前必须满足

- `FRONTEND-P0-01`：`WikiMediaLink` 类型包含双 ID 和 v3 语义字段。
- `FRONTEND-P0-02`：列表 key、媒体 Map、去重与选择优先使用 `bindingId`；legacy/v2 才回退 `mediaId`/`assetId`。
- `FRONTEND-P0-03`：不得按 `resourceId`、URL、SHA 或兼容 `mediaId` 去重 v3 binding。
- `FRONTEND-P0-04`：现有角色选人页、详情页、皮肤、语音、藏品和尤提姆渲染在 legacy/v2 数据下保持兼容。

### 5.3 P1 可部分支持

- `FRONTEND-P1-01`：显示媒体 provenance 和 binding 调试面板。

### 5.4 P2 未来演进

- `FRONTEND-P2-01`：跨版本媒体差异可视化。

### 5.5 关键契约与限制

本轮不改变 Wiki 视觉布局和动效，只修改身份处理与 DTO 消费。

## 6. 迁移、回滚与兼容回执模块

### 6.1 模块职责

在业务存储不变的条件下证明 Wiki 已具备 v2/v3 双读能力，并为 RAG candidate gate 提供 hash-pinned evidence。

### 6.2 P0 当前必须满足

- `RECEIPT-P0-01`：兼容回执 schema 固定为 `huiji.wiki-media-v3-compatibility-receipt/v1`，记录 RAG 四个共享 fixture 的相对路径与 SHA-256。
- `RECEIPT-P0-02`：回执必须证明输入 binding 数、唯一 binding 数、资源数和 resource-to-many-binding 关系均按 fixture 完整保留。
- `RECEIPT-P0-03`：四个共享 fixture 缺失、hash 变化、schema 不一致或测试失败时不得发布通过回执，只输出确定性 blocker。
- `RECEIPT-P0-04`：回执生成测试不得连接生产 MySQL、写 MinIO/Milvus、导入 candidate 或修改 active pointer。
- `RECEIPT-P0-05`：migration 与 rollback evidence 不得包含数据库密码或绝对备份仓库写路径。

### 6.3 P1 可部分支持

- `RECEIPT-P1-01`：candidate 激活后的 Wiki pre-import rollback receipt。

### 6.4 P2 未来演进

- `RECEIPT-P2-01`：自动 activation orchestration。

### 6.5 关键契约与限制

RAG 负责共享 fixture 与 receipt validator；Wiki 负责规范化实现和回执生成。当前 fixture 尚未由 RAG Task 1 创建时，兼容实现可以完成，但状态必须是 `blocked_shared_fixture_missing`。

## 7. 测试与验收方向

- snapshot 分支必须覆盖 legacy、两个 v2 manifest 历史名称、严格 v3 和非法 candidate。
- v3 fixture 必须覆盖同资源多绑定、跨 owner 复用、多语言语音、空 variant/skin、collection 和 Udimo。
- MySQL 测试必须按多重集比较 binding，不允许 set/map 折叠。
- API 测试必须同时验证旧字段、双 ID 和本地路径过滤。
- React 测试必须证明相同 `mediaId` 的两条不同 binding 同时存在。
- 本轮结束必须证明 MySQL、MinIO、Milvus、active pointer 和现有 artifacts 未被修改。

## 8. 与旧方案的关系

- 保留 `2026-07-18-huiji-wiki-crawler-only-source.md` 的 crawler-only、共享 MinIO 和不修改 RAG 状态边界。
- 本设计取代旧 Wiki Specs 中所有 `data/raw`、Obsidian 和 supplement 正式来源条款。
- 本设计补充而不替代 2026-07-20 Builder Spec；出现冲突时，以 Builder 冻结的 media v3 字段、ID 算法、schema 和 fixture 为共享契约权威。
