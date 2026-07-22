# Huiji Candidate F 跨系统融合闭环设计

日期：2026-07-22
状态：已批准，待实施

## 1. 背景与目标

Candidate F 已作为 generation 1 active RAG，Wiki 也已完成 crawler v3 正式事务导入。两条运行链路仍按职责分离：RAG 读取 Milvus/BM25，Wiki 读取 MySQL；两者共享同一个 crawler build，但不共享运行时存储实现。

当前缺口位于控制层。原 `wiki_import_handoff.v1.json` 是导入前不可变授权，固定记录 `wiki_import_status=not_started`。正式 Wiki import receipt 已证明导入完成，但尚无一份 RAG 所有、可独立验证的最终证据把 activation、handoff、Wiki import、联合健康和 rollback authority 连接成完整审计链。

本设计新增且只新增一份业务 Receipt：

```text
eval/huiji_candidate_closure/candidate-f-generation-1-20260722d/
  candidate_f_closure_receipt.v1.json
  candidate_f_closure_receipt.v1.json.sha256
```

SHA sidecar 只用于固定 Receipt 字节，不是第二份业务证据。闭环过程不重新构建、不向量化，不修改 active pointer、settings、Milvus、MinIO、Wiki MySQL 或任何既有 receipt/handoff。

## 2. 最终授权与引用验证模块

### 2.1 模块职责

把已签发的 RAG activation authority 与 Wiki 正式导入结果绑定到同一个 activation ID，并拒绝任一历史证据漂移。

### 2.2 P0 当前必须满足

- `CLOSE-AUTH-P0-01`：只接受 activation ID `candidate-f-generation-1-20260722d`、formal import receipt 路径 `eval/huiji_wiki_v3_import/candidate-f-generation-1-20260722d/formal_import_receipt.v1.json` 和期望 SHA-256 `76909a9cbb85ce81e4e4a746a780b8836423ee9b6e921c503249cade1a87a23f`。
- `CLOSE-AUTH-P0-02`：activation receipt、Wiki handoff、formal import receipt 及 formal receipt 引用的全部 evidence 必须逐项存在且 SHA-256 匹配；activation receipt 必须是 committed、48/48 passing，handoff 必须仍为 `not_started`。
- `CLOSE-AUTH-P0-03`：active pointer 文件 SHA、generation、activation ID、build、artifact schema 和 collection 必须与 activation receipt、handoff、formal receipt 完全一致。
- `CLOSE-AUTH-P0-04`：所有输入路径必须位于项目根内；拒绝路径逃逸、任意 candidate、latest 目录推断和未固定 SHA 的引用。

### 2.3 P1 可部分支持

- `CLOSE-AUTH-P1-01`：未来可参数化支持后续 generation；本轮 validator 固定 Candidate F authority，避免把一次性闭环工具误用为通用发布器。

### 2.4 P2 未来演进

- `CLOSE-AUTH-P2-01`：远程签名、跨主机审计存储和多方审批。

### 2.5 关键契约与限制

原 handoff 的 `not_started` 是历史事实，不是待修复字段。最终 Receipt 通过 `status_transition={from:not_started,to:completed}` 表达后续状态，不得编辑 handoff 或 activation receipt。

## 3. 运行身份与联合健康模块

### 3.1 模块职责

证明闭环时 RAG 和 Wiki 同时在线，并且各自安装的运行身份仍来自同一 Candidate F build。

### 3.2 P0 当前必须满足

- `CLOSE-RUNTIME-P0-01`：RAG `/health` 必须为 `status=ok`、`vectorstore_loaded=true`、`provenance_status=pass`、`doc_count=14630`。
- `CLOSE-RUNTIME-P0-02`：严格 runtime snapshot 必须解析为 generation 1、build `crawler-v3-20260721t051246z`、collection `text_child_bge_m3_shadow_crawler_v3_20260721t051246z`，且 artifact hashes 与 active pointer 一致。
- `CLOSE-RUNTIME-P0-03`：Wiki `/api/wiki/health` 必须为 ready、source mode `active`、build `crawler-v3-20260721t051246z`、artifact schema `evb.media-asset/v3`、activation epoch 1、stale=false。
- `CLOSE-RUNTIME-P0-04`：Wiki health 必须报告 7,456 pages、4 categories、19,132 media resources、19,400 media bindings；legacy 17,527 media links 可保留但不得作为当前 v3 binding authority。
- `CLOSE-RUNTIME-P0-05`：联合健康采集必须只使用 GET、runtime resolver 和只读 SQL；不得调用问答生成模型、Wiki importer、restore、Builder、embedding 或存储写接口。

### 3.3 P1 可部分支持

- `CLOSE-RUNTIME-P1-01`：未来可加入持续观察窗口；本轮只做单次原子时间窗口内的联合健康快照。

### 3.4 P2 未来演进

- `CLOSE-RUNTIME-P2-01`：持续发布控制器与自动流量回滚。

### 3.5 关键契约与限制

联合健康证明控制层身份一致，不表示 Milvus 与 MySQL 已合并，也不要求两者保存相同形态的数据。

## 4. Wiki 完成状态与 MySQL 稳定性模块

### 4.1 模块职责

将 Wiki 正式导入的不可变结果登记为 handoff 的后续完成状态，并确认闭环采集期间没有发生第二次导入。

### 4.2 P0 当前必须满足

- `CLOSE-WIKI-P0-01`：formal import receipt 必须为 `huiji.wiki-v3-formal-import-receipt/v1`、`status=passed`，且 activation ID、build、collection 与 active tuple 一致。
- `CLOSE-WIKI-P0-02`：formal receipt 的 installed snapshot SHA `7529288166e2304d2e31cad7777a5fb8173e830ece13d340fae0650d08f019a1`、manifest SHA、generation、source mode 和 import timestamp 必须与当前 MySQL `wiki_import_snapshots` id=1 完全一致。
- `CLOSE-WIKI-P0-03`：当前 MySQL 计数必须与 formal receipt 完全一致；snapshot identity、import timestamp 或计数任一漂移都停止，不生成闭环 Receipt。
- `CLOSE-WIKI-P0-04`：Receipt 必须显式记录 `status_transition.from=not_started`、`status_transition.to=completed`、formal completion timestamp 和本次 closure timestamp，不把原 handoff 描述为已被修改。

### 4.3 P1 可部分支持

- `CLOSE-WIKI-P1-01`：未来 Wiki 可主动签发通用 acknowledgement；本轮由 RAG 闭环 validator 只读消费 formal receipt。

### 4.4 P2 未来演进

- `CLOSE-WIKI-P2-01`：跨系统两阶段提交和双向状态服务。

### 4.5 关键契约与限制

“无额外 MySQL import”只表示 formal receipt 所固定的 installed snapshot、导入时间和业务计数至闭环采集时未变化；不声称数据库从未接收任何无关只读连接或运维操作。

## 5. Rollback 可追溯性与无写入声明模块

### 5.1 模块职责

证明 RAG generation-0 rollback authority 和 Wiki pre-import rollback receipt 仍可由原始哈希链定位，同时限定闭环工具自身的副作用。

### 5.2 P0 当前必须满足

- `CLOSE-ROLLBACK-P0-01`：RAG activation receipt 引用的 rollback tuple、previous pointer/settings 和 generation-0 collection evidence 必须存在且 SHA 匹配；不执行 RAG rollback。
- `CLOSE-ROLLBACK-P0-02`：Wiki handoff 引用的 pre-import rollback receipt 必须通过 canonical bytes、内部 hash、sidecar 和 restore entrypoint 校验；不执行 MySQL restore。
- `CLOSE-MUTATION-P0-01`：formal import receipt 的 protected compare 必须通过，并证明 Wiki 正式导入未修改 Milvus、MinIO、active pointer 或 Candidate artifacts。
- `CLOSE-MUTATION-P0-02`：闭环 CLI 的可调用依赖中不得包含 Builder、embedding、Milvus insert/delete/drop/alias、MinIO put/delete、Wiki importer/restore 或 MySQL DDL/DML。
- `CLOSE-MUTATION-P0-03`：最终 Receipt 必须记录 `milvus_writes=false`、`minio_writes=false`、`embedding_runs=false`、`mysql_imports=false`；这些字段表示本次 closure operation 的行为，并引用 formal protected evidence 支撑历史切换边界。

### 5.3 P1 可部分支持

- `CLOSE-ROLLBACK-P1-01`：未来可定期演练两条 rollback；本轮只验证 authority 可追溯，不制造停机或数据回退。

### 5.4 P2 未来演进

- `CLOSE-ROLLBACK-P2-01`：RAG 与 Wiki 的联合自动回滚策略。

### 5.5 关键契约与限制

rollback authority 可追溯不等于此刻执行 rollback。闭环完成后若 Wiki 或 RAG 出现新故障，仍应分别按原 rollback Plan 审查，不由本 Receipt 自动触发。

## 6. 单一 Receipt 与幂等模块

### 6.1 模块职责

输出一个可独立验证的最终跨系统状态，不制造 acknowledgement、health 和 closure 三套业务文件。

### 6.2 P0 当前必须满足

- `CLOSE-EVIDENCE-P0-01`：业务输出只能是 `candidate_f_closure_receipt.v1.json`；另有一个同名 `.sha256` 字节 sidecar。
- `CLOSE-EVIDENCE-P0-02`：Receipt schema 固定为 `huiji.candidate-f-cross-system-closure/v1`，顶层包含 `activation`、`wiki_import`、`runtime_identity`、`joint_health`、`rollback`、`mutation_assertions`、`requirement_matrix` 和 `closed_at_utc`。
- `CLOSE-EVIDENCE-P0-03`：Receipt 必须使用 canonical JSON、项目相对路径、完整 SHA-256 和 create-new 写入；不得包含密钥、数据库密码、环境变量值、绝对路径、正文或媒体本地路径。
- `CLOSE-EVIDENCE-P0-04`：validator 必须重新验证全部输入和当前只读状态，不只验证 Receipt 自身 sidecar；requirement matrix 必须逐项覆盖本 Spec 的 23 个 P0 条目并达到 `23/23`。
- `CLOSE-EVIDENCE-P0-05`：首次成功返回 `closed`；若目标 Receipt 已存在且 validator 通过，返回 `already_closed` 且不重写文件；存在单边文件、sidecar 冲突、Receipt 无效或当前状态漂移时 fail closed。

### 6.3 P1 可部分支持

- `CLOSE-EVIDENCE-P1-01`：未来可加入通用 schema registry；本轮使用模块内严格 validator。

### 6.4 P2 未来演进

- `CLOSE-EVIDENCE-P2-01`：外部透明日志和加密签名。

### 6.5 Receipt 结构

```text
candidate_f_closure_receipt.v1.json
  schema_version / status / activation_id / closed_at_utc
  activation
    activation_receipt / wiki_handoff / active_pointer
  wiki_import
    formal_import_receipt
    status_transition: not_started -> completed
    installed_snapshot
  runtime_identity
    rag: generation / build / collection / artifacts
    wiki: generation / build / snapshot
  joint_health
    rag_health / wiki_health / inventory_counts
  rollback
    rag_generation_zero_authority / wiki_pre_import_rollback
  mutation_assertions
    milvus_writes / minio_writes / embedding_runs / mysql_imports
    formal_protected_compare
  requirement_matrix
```

## 7. 跨模块数据流

```text
immutable activation receipt + immutable handoff
  -> validate generation-1 active tuple
formal Wiki import receipt + all pinned evidence
  -> validate current MySQL snapshot and counts
RAG health/runtime + Wiki health
  -> validate one shared build identity
RAG rollback tuple + Wiki rollback receipt
  -> validate traceability without execution
all P0 gates pass
  -> create-new candidate_f_closure_receipt.v1.json + SHA sidecar
```

## 8. 错误处理原则

- 输入 path/hash/schema/status 漂移：停止，不生成任何输出。
- RAG/Wiki build、generation、collection 或 snapshot 不一致：停止并扩大只读检查。
- 当前 MySQL snapshot 或计数与 formal receipt 不一致：停止；不自动重导入或回滚。
- health 不通过：停止；不修改服务、端口或存储。
- 输出目标只存在 Receipt 或 sidecar 之一：视为冲突，不补写另一半。
- 已存在且验证通过：返回 `already_closed`；不得更新时间戳或生成第二份 Receipt。

## 9. 测试与真实验收方向

- 单元测试覆盖路径逃逸、hash/schema/status 篡改、build/generation/collection 漂移、formal evidence 漂移、MySQL snapshot/计数漂移、rollback 引用失效、health 失败、create-new 冲突和 `already_closed`。
- mutation spy 断言闭环模块不调用任何写存储、Builder、embedding、import 或 restore API。
- 真实验收复算给定 formal receipt SHA，读取当前 active pointer、runtime snapshot、MySQL snapshot、RAG/Wiki health，并生成后立即用独立 validator 复核最终 Receipt。
- 最终再运行相关目标测试和全量 pytest；测试通过不能替代真实联合健康与哈希门禁。

## 10. 与既有方案的关系

- 落地 `2026-07-22-huiji-rag-candidate-f-activation-design.md` 的 `ACT-WIKI-P1-01`。
- 落地 `2026-07-22-huiji-wiki-v3-formal-import-design.md` 的 `AUTH-P1-01` 和 `EVIDENCE-P1-01`。
- 不修改原 activation Plan 的 P0 结果，不改变原 handoff 的历史语义。
- 不替代 RAG activation receipt、Wiki formal import receipt 或任一 rollback receipt；最终 Receipt 只做追加式聚合与当前状态验证。

## 11. 完成判定

只有所有 P0 条目均有实现、自动测试和真实只读证据，最终 Receipt 与 sidecar create-new 成功并通过独立 validator，且 RAG/Wiki 仍共同指向 Candidate F generation 1，才能宣称 Candidate F 的 RAG 与 Wiki 正式切换流程整体关闭。
