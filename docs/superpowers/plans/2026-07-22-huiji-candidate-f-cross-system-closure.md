# Huiji Candidate F 跨系统融合闭环实施计划

日期：2026-07-22
状态：已执行完成

依据 Spec：`docs/superpowers/specs/2026-07-22-huiji-candidate-f-cross-system-closure-design.md`
Spec SHA-256：`657aa6a8f48d35b2d0e3cc7c8df3b9d26dc3cd8bc5d4a06e8dbe474338cd1798`

执行模式：在当前 dirty worktree 单线程执行，不使用子代理，不执行 git 清理、提交或回滚。Plan 只包含本轮 P0；任一 P0 未闭合均不得生成 passing closure receipt。

## 1. 目标范围

本轮必须完成以下 23 个 P0：

- `CLOSE-AUTH-P0-01..04`
- `CLOSE-RUNTIME-P0-01..05`
- `CLOSE-WIKI-P0-01..04`
- `CLOSE-ROLLBACK-P0-01..02`
- `CLOSE-MUTATION-P0-01..03`
- `CLOSE-EVIDENCE-P0-01..05`

本轮只读核验 RAG、Wiki、MySQL、Milvus authority、MinIO evidence 和 rollback authority。禁止重新构建、重新 embedding、重新导入 Wiki、修改 active pointer/settings、写 Milvus/MinIO、执行 rollback/restore 或改写任何既有 evidence。

## 2. 冻结输入与输出

| 项目 | 冻结值 |
|---|---|
| activation ID | `candidate-f-generation-1-20260722d` |
| build | `crawler-v3-20260721t051246z` |
| generation | `1` |
| collection | `text_child_bge_m3_shadow_crawler_v3_20260721t051246z` |
| activation receipt SHA-256 | `78310c7f0009c6df88413f5a888940d4aa404073b81ef001ebc9d1a6eb3d7f58` |
| Wiki handoff SHA-256 | `884e6ae0ef10911564a84ec3c3ec5b3f57939fc47475ab68599d04ca14d4e90a` |
| active pointer SHA-256 | `87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e` |
| settings SHA-256 | `d2b25e7dfbb41a0b1c13e7d3964dbcf286380c0bdf2cc5ee920c1e0d1be5d473` |
| formal import receipt | `eval/huiji_wiki_v3_import/candidate-f-generation-1-20260722d/formal_import_receipt.v1.json` |
| formal import receipt SHA-256 | `76909a9cbb85ce81e4e4a746a780b8836423ee9b6e921c503249cade1a87a23f` |
| installed snapshot SHA-256 | `7529288166e2304d2e31cad7777a5fb8173e830ece13d340fae0650d08f019a1` |
| RAG generation-0 rollback tuple SHA-256 | `07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b` |
| Wiki pre-import rollback receipt SHA-256 | `e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6` |
| pages/categories | `7456 / 4` |
| resources/bindings | `19132 / 19400` |
| retained legacy links | `17527` |
| RAG doc count | `14630` |

唯一业务输出：

```text
eval/huiji_candidate_closure/candidate-f-generation-1-20260722d/
  candidate_f_closure_receipt.v1.json
  candidate_f_closure_receipt.v1.json.sha256
```

## 3. 强制验收矩阵

| 检查点 | Specs | 实现位置 | 自动测试 | 真实只读验收 | 失败表现 |
|---|---|---|---|---|---|
| C1 固定授权 | `CLOSE-AUTH-P0-01..04` | `src/huiji_rag/closure.py` | path/hash/schema/status/tamper tests | 逐文件复算 frozen SHA | 任一漂移时无输出 |
| C2 RAG 身份 | `CLOSE-RUNTIME-P0-01..02` | `closure.py`、runtime resolver | generation/build/collection/artifact mismatch tests | `/health` + strict runtime snapshot | 不一致立即停止 |
| C3 Wiki 身份 | `CLOSE-RUNTIME-P0-03..05` | `closure.py` | health/count/stale/write-spy tests | `/api/wiki/health` 精确计数 | health 或身份错误时停止 |
| C4 导入完成 | `CLOSE-WIKI-P0-01..04` | `closure.py` | formal receipt/MySQL drift/status transition tests | 只读查询 id=1 snapshot 与表计数 | 不生成 completed 状态 |
| C5 回滚可追溯 | `CLOSE-ROLLBACK-P0-01..02` | `closure.py`、既有 validators | tuple/receipt/sidecar/entrypoint tamper tests | 深度验证两条 rollback authority，不执行 | 引用失效时停止 |
| C6 无写入边界 | `CLOSE-MUTATION-P0-01..03` | `closure.py` | forbidden dependency/mutation spy tests | 验证 formal protected compare；闭环前后 canonical hashes 不变 | 检测写调用或漂移即失败 |
| C7 单一 Receipt | `CLOSE-EVIDENCE-P0-01..05` | `closure.py`、`scripts/close_huiji_candidate.py` | canonical/create-new/partial/conflict/already_closed tests | close 后独立 validate，再次 close 幂等 | 不覆盖、不补写、不生成第二份业务证据 |

## 4. 执行步骤

### Step 0：冻结真实只读基线

- 对应 Specs：`CLOSE-AUTH-P0-01..04`、`CLOSE-MUTATION-P0-01`。
- 确认输出 Receipt 和 sidecar 均不存在；若只存在其中一个则停止，不删除或补写。
- 复算 Spec、formal receipt、activation receipt、handoff、pointer、settings、rollback tuple 和 Wiki rollback receipt SHA。
- 读取 formal receipt 引用的 `import_commit`、`api_smoke`、`rag_smoke`、`protected_compare`、`p0_matrix` 和 Playwright evidence，逐项复算 SHA 并检查 passing schema/status。
- 采集当前 RAG/Wiki health、strict runtime snapshot 和只读 MySQL state，但不写 evidence。
- 验收：所有冻结值等于第 2 节；输出目录仍不存在。

### Step 1：RED 测试定义固定授权与路径闭锁

- 对应 Specs：`CLOSE-AUTH-P0-01..04`、`CLOSE-WIKI-P0-01`。
- 创建 `tests/test_huiji_candidate_closure.py`。
- 测试 activation/formal receipt/handoff/pointer 的期望 SHA、schema、状态、activation ID、build、generation 和 collection。
- 测试 formal receipt 每个 evidence 引用缺失、hash 漂移、路径逃逸和未固定路径均 fail closed。
- 测试原 handoff 必须保持 `not_started`，validator 不接受被原地修改成 `completed` 的 handoff。
- RED 验收命令：

```powershell
python -m pytest -q tests/test_huiji_candidate_closure.py -k "authority or path or hash or formal"
```

### Step 2：实现 authority、runtime 与 Wiki state inspector

- 对应 Specs：`CLOSE-AUTH-P0-01..04`、`CLOSE-RUNTIME-P0-01..05`、`CLOSE-WIKI-P0-01..04`。
- 创建 `src/huiji_rag/closure.py`，复用而不复制以下既有能力：
  - `validate_activation_receipt()`、`validate_wiki_handoff()`；
  - `resolve_runtime_artifact_snapshot()`；
  - `validate_passing_receipt()`；
  - `query_database_state()`；
  - canonical JSON 与项目内路径约束。
- inspector 只允许 HTTP GET、runtime artifact 读取和 MySQL SELECT；不构造 Retriever、LLM、Builder、importer 或 storage client。
- MySQL current snapshot 必须逐字段等于 formal receipt 的 snapshot，尤其是 `snapshot_sha256`、`manifest_sha256`、`activation_epoch`、`source_mode`、`build_version` 和 `imported_at_utc`。
- current counts 必须等于 formal receipt counts；完成状态在内存中表示为 `not_started -> completed`。
- GREEN 验收命令：

```powershell
python -m pytest -q tests/test_huiji_candidate_closure.py -k "authority or runtime or wiki or snapshot or health"
```

### Step 3：实现 rollback 深度验证与 mutation assertions

- 对应 Specs：`CLOSE-ROLLBACK-P0-01..02`、`CLOSE-MUTATION-P0-01..03`。
- RAG rollback：验证 activation receipt pin 的 rollback tuple、previous pointer/settings、generation-zero collection manifest、deployment inventory、Milvus fingerprint 和 restore authority；只读验证，不调用 recover。
- Wiki rollback：通过既有 canonical/internal-hash/sidecar validator，并确认 restore entrypoint、source authority 和 dump 引用仍可追溯；不调用 restore。
- formal protected compare 必须为 pass，且其固定字段证明 active pointer、Milvus、MinIO scope 和 Candidate artifacts 无未授权变化。
- mutation spies 禁止以下调用：Milvus insert/delete/drop/alias、MinIO put/delete、embedding、Builder、Wiki importer/restore、MySQL DDL/DML。
- GREEN 验收命令：

```powershell
python -m pytest -q tests/test_huiji_candidate_closure.py -k "rollback or mutation or protected or forbidden"
```

### Step 4：实现单一 Receipt、严格 validator 与 CLI

- 对应 Specs：`CLOSE-EVIDENCE-P0-01..05`。
- 创建 `scripts/close_huiji_candidate.py`，只提供：
  - `inspect`：运行全部只读门禁，JSON 结果写 stdout，不创建文件；
  - `close`：重新运行全部门禁后 create-new 写 Receipt 和 sidecar；
  - `validate`：复算 sidecar、canonical bytes、23/23 matrix、全部历史引用和当前只读状态。
- Receipt schema 为 `huiji.candidate-f-cross-system-closure/v1`，状态为 `closed`；requirement matrix 精确 `23/23`。
- create-new 顺序固定为 Receipt 后 sidecar。若本次 operation 的 sidecar 发布失败，只能在 Receipt 实际 SHA 仍等于本次 canonical bytes 且 sidecar 不存在时条件删除本次刚创建的 Receipt，恢复到零输出；任一 SHA 或所有权不明则报 conflict 并保留现场。启动时发现预存单边文件一律 conflict，不自动补写、删除或覆盖。
- `close` 发现 Receipt 与 sidecar 均存在时必须完整 validate；通过返回 `already_closed`，失败返回 conflict。
- Receipt 只记录相对路径、SHA、结构化 identity/health/counts、布尔 mutation assertions 和 UTC 时间，不记录密钥、绝对路径、响应正文或本地媒体路径。
- GREEN 验收命令：

```powershell
python -m pytest -q tests/test_huiji_candidate_closure.py -k "receipt or canonical or create_new or sidecar or already_closed or cli"
```

### Step 5：目标回归、全量回归与静态边界检查

- 对应 Specs：全部 P0 的代码门禁。
- 命令：

```powershell
python -m pytest -q tests/test_huiji_candidate_closure.py
python -m pytest -q tests/test_huiji_activation.py tests/test_huiji_wiki_formal_import.py tests/test_huiji_runtime_artifacts.py tests/test_rag_eval_isolated.py
python -m pytest -q
python -m pip check
```

- 使用源码 AST/import 检查和 mutation spies 证明 closure 模块与 CLI 未导入或调用写入型 Builder、embedding、storage mutation、Wiki import/restore API。
- 测试失败时不进入真实 `close`。

### Step 6：真实 inspect 与最终人工前置复核

- 对应 Specs：全部 P0 的真实只读门禁。
- 命令：

```powershell
python scripts/close_huiji_candidate.py inspect `
  --formal-import-receipt eval/huiji_wiki_v3_import/candidate-f-generation-1-20260722d/formal_import_receipt.v1.json `
  --expected-formal-import-receipt-sha256 76909a9cbb85ce81e4e4a746a780b8836423ee9b6e921c503249cade1a87a23f
```

- inspect 必须返回 `ready_to_close`、23/23、共同 build/generation/collection/snapshot、联合 health 与 rollback traceability。
- inspect 后重新确认输出 Receipt/sidecar 均不存在，所有 canonical hashes 未变化。
- 任一异常停止，不以人工编辑 evidence 绕过。

### Step 7：create-new 最终闭环 Receipt

- 对应 Specs：全部 23 个 P0。
- 仅在 Step 6 全部通过后执行：

```powershell
python scripts/close_huiji_candidate.py close `
  --formal-import-receipt eval/huiji_wiki_v3_import/candidate-f-generation-1-20260722d/formal_import_receipt.v1.json `
  --expected-formal-import-receipt-sha256 76909a9cbb85ce81e4e4a746a780b8836423ee9b6e921c503249cade1a87a23f
```

- 期望首次结果：`status=closed`，输出唯一 Receipt path、file SHA-256 和 `23/23`。
- 不在命令行传递或输出 API key、MySQL 密码、MinIO 凭据。

### Step 8：独立 validate、幂等复核与 Plan 回填

- 对应 Specs：`CLOSE-EVIDENCE-P0-01..05` 及整体完成判定。
- 从首次 `close` 实际输出读取 Receipt SHA，不手写预估值：

```powershell
$Receipt = 'eval/huiji_candidate_closure/candidate-f-generation-1-20260722d/candidate_f_closure_receipt.v1.json'
$ReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Receipt).Hash.ToLower()
python scripts/close_huiji_candidate.py validate --receipt $Receipt --expected-receipt-sha256 $ReceiptSha
python scripts/close_huiji_candidate.py close `
  --formal-import-receipt eval/huiji_wiki_v3_import/candidate-f-generation-1-20260722d/formal_import_receipt.v1.json `
  --expected-formal-import-receipt-sha256 76909a9cbb85ce81e4e4a746a780b8836423ee9b6e921c503249cade1a87a23f
```

- validate 必须返回 `valid`；第二次 close 必须返回 `already_closed`。
- 第二次 close 前后 Receipt、sidecar、pointer、settings、activation receipt、handoff 和 formal receipt SHA 必须完全不变。
- 再做一次 RAG/Wiki health，确认服务仍在线且共同指向 Candidate F。
- 回填本 Plan：真实 Receipt path/SHA、23/23、测试数、health、MySQL counts、幂等结果和所有无写入声明。

## 5. P1/P2 与 Out of Scope

本轮 Plan 主线不执行任何 P1/P2：

- 通用多 generation closure schema registry；
- Wiki 主动 acknowledgement 服务；
- 持续观察窗口与 SLO controller；
- 跨系统两阶段提交、签名和远程审计存储；
- 自动联合回滚；
- RAG/Wiki 存储层或运行层融合；
- 重新 Builder、embedding、Milvus 切换或 Wiki import；
- MinIO/Milvus/MySQL 清理和 legacy data 退役。

## 6. 完成后自检表

- [x] `CLOSE-AUTH-P0-01..04`：全部固定 authority、引用和项目内路径通过。
- [x] `CLOSE-RUNTIME-P0-01..05`：RAG/Wiki 联合健康与共同 runtime identity 通过。
- [x] `CLOSE-WIKI-P0-01..04`：formal receipt、当前 MySQL snapshot/counts 和 `not_started -> completed` 证据通过。
- [x] `CLOSE-ROLLBACK-P0-01..02`：RAG/Wiki rollback authority 可追溯且未执行。
- [x] `CLOSE-MUTATION-P0-01..03`：formal protected evidence 通过，本次闭环零存储写入、零 embedding、零 import。
- [x] `CLOSE-EVIDENCE-P0-01..05`：单一 Receipt、sidecar、23/23 validator 和 `already_closed` 幂等通过。
- [x] 目标测试、关联回归、全量 pytest 与 `pip check` 通过。
- [x] 最终 RAG/Wiki health 通过；pointer/settings 和所有输入 evidence SHA 无漂移。
- [x] Plan 已回填真实结果，Candidate F 跨系统切换正式关闭。

## 7. 完成判定

只有第 6 节全部勾选，最终 Receipt 与 sidecar 均存在且通过独立 validator，第二次 close 返回 `already_closed`，并且 RAG/Wiki 仍共同指向 Candidate F generation 1，才能宣称整体流程关闭。任何单测通过、单次 health 通过、只生成 Receipt 未验证 sidecar，或只读取 formal receipt，均不能单独构成完成。

## 8. 实际执行记录

执行日期：2026-07-22。

- Step 0：输出目录不存在；activation receipt、handoff、pointer、settings、formal import receipt、RAG rollback tuple 和 Wiki rollback receipt 的冻结 SHA 全部匹配。
- formal evidence：`api_smoke`、`import_commit`、`p0_matrix`、`playwright`、`protected_compare`、`rag_smoke` 六个引用逐项复算通过；protected compare 为 pass。
- Windows 兼容：Wiki formal Receipt 和 sidecar 的既有 canonical 行尾为 `CRLF`。输入 validator 只兼容 `LF/CRLF` 两种等价结尾；新 closure Receipt 与 sidecar 固定写为二进制 `LF`。
- 只读 MySQL：闭环模块没有导入 formal importer，使用 `START TRANSACTION READ ONLY` 加 `SHOW/SELECT` 读取 installed snapshot 和计数，完成后 rollback 只读事务。
- 历史 rollback：未复用要求当前 pointer 为 generation 0 的激活前 validator；改为验证 bootstrap receipt 自身内部 hash、44/44 matrix、terminal journal、activation transaction 保存的 generation-0 pointer/settings 和 live legacy Milvus 指纹。
- 目标测试：`21 passed`；关联回归曾为 `36 passed`；最终全量回归为 `1360 passed, 2 skipped, 3 warnings`；`pip check` 无损坏依赖。
- 真实 inspect：`ready_to_close`、`23/23`；RAG/Wiki health 均 pass；rollback authority 为 `traceable_not_executed`；`writes_performed=false`。
- 首次 close：`status=closed`，完成时间 `2026-07-22T13:15:38Z`。
- 最终 Receipt：`eval/huiji_candidate_closure/candidate-f-generation-1-20260722d/candidate_f_closure_receipt.v1.json`。
- Receipt SHA-256：`6cc9f0687a708c995eb9cc5b9efe1bb069a9b4c6b007e291719e50fb6ec1a5b1`。
- Sidecar SHA-256：`c96e6c8cab806cbb45f15cb5f8e25a0087c92b1071fccca595add4582a9d9e35`；sidecar 内容精确 pin Receipt SHA 和文件名。
- 独立 validate：`status=valid`、`23/23`；第二次 close：`status=already_closed`。
- 幂等前后比较：Receipt、sidecar、pointer、settings、activation receipt、handoff 和 formal import receipt 的 SHA 变化为 `[]`。
- 最终 RAG health：`status=ok`、`vectorstore_loaded=true`、`provenance_status=pass`、`doc_count=14630`。
- 最终 Wiki health：`ready=true`、`sourceMode=active`、build `crawler-v3-20260721t051246z`、epoch 1、stale=false；`7456` pages、`4` categories、`19132` resources、`19400` bindings、`17527` retained legacy links。
- 最终 Receipt 记录 `not_started -> completed`；RAG/Wiki rollback 仅验证可追溯，未执行；本次 closure operation 的 Milvus writes、MinIO writes、embedding runs 和 MySQL imports 均为 false。
