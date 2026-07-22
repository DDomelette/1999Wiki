# Huiji RAG Candidate F Activation 实施计划

日期：2026-07-22  
状态：待用户审阅  
执行模式：在当前脏工作树单线程执行，不使用子代理，不执行 git 清理、提交或回滚。Plan 是本轮强制验收门槛；任一 P0 未闭合均不得签发 passing activation receipt 或 Wiki import handoff。

依据 Spec：`docs/superpowers/specs/2026-07-22-huiji-rag-candidate-f-activation-design.md`  
Spec SHA-256：`7d3e3829a36d0aef143aef640c133247bd8d05a399199a6ad1d2c8f4e9ed279a`

## 1. 目标与执行边界

本轮必须闭合以下 48 条 P0：

- `ACT-AUTH-P0-01..08`
- `ACT-MANIFEST-P0-01..06`
- `ACT-TXN-P0-01..10`
- `ACT-RUNTIME-P0-01..06`
- `ACT-PROC-P0-01..06`
- `ACT-VERIFY-P0-01..07`
- `ACT-WIKI-P0-01..05`

本轮唯一允许的 active tuple 变化是：

```text
generation=0 / build=dev / collection=text_child_bge_m3_v3
    ->
generation=1 / build=crawler-v3-20260721t051246z /
collection=text_child_bge_m3_shadow_crawler_v3_20260721t051246z
```

该变化必须同时更新：

1. `config/settings.yaml` 的三个已批准 scalar；
2. `data/processed/huiji/active_build.v1.json`；
3. pointer-aware runtime authority；
4. 后端进程加载的实际 collection 和 crawler-only artifacts。

完成后必须生成：

1. hash-pinned activation intent、Candidate collection manifest、deployment inventory 和 protected-state baseline；
2. hash-chain activation journal；
3. generation 1 pointer 和只修改三个 scalar 的 settings；
4. runtime、health、通用分层抽样 retrieval、voice pagination 和 protected compare 证据；
5. 48/48 P0 passing activation receipt；
6. `wiki_import_allowed=true` 的 hash-pinned Wiki import handoff；
7. 可重复执行但不改变状态的 committed recover 验证结果。

本轮禁止：

- 执行 Wiki v3 正式 MySQL 导入、restore、DDL 或 DML；
- 修改 Wiki compatibility receipt 或 pre-import rollback receipt；
- 重建、重新向量化、rename、alias、drop 或 delete Milvus collection；
- 向 MinIO 上传、删除、迁移或清理对象；
- 修改 Candidate F artifacts、generation-0 evidence 或 legacy artifacts；
- 修改 `config/provenance/huiji-dev.v1.json`；
- 停止 Milvus、MinIO、MySQL、etcd、前端或任何非目标 Python 进程；
- 持久化短期会话内存；
- 修改 `D:\1999Wiki_Backup`；
- 生成 Wiki 已完成正式导入的声明。

## 2. 冻结输入与具体输出

执行时必须重新计算全部 hash、状态和实时 fingerprint。下表任一值不一致时，inspect 在后端仍在线时停止；不得自动接受新状态或扩大 allowlist。

| 输入 | 路径或 authority | 冻结值 |
|---|---|---|
| 本 Spec | `docs/superpowers/specs/2026-07-22-huiji-rag-candidate-f-activation-design.md` | SHA-256 `7d3e3829a36d0aef143aef640c133247bd8d05a399199a6ad1d2c8f4e9ed279a` |
| Proposal | `data/processed/huiji/activation/proposals/candidate-f-review-20260722c/activation_proposal.v1.json` | SHA-256 `fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8`; review allowed；blockers empty |
| Rollback tuple | `data/processed/huiji/activation/proposals/candidate-f-review-20260722c/rollback_tuple.v1.json` | SHA-256 `07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b` |
| Current pointer | `data/processed/huiji/active_build.v1.json` | SHA-256 `95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723`; generation 0 tuple |
| Current settings | `config/settings.yaml` | SHA-256 `d5363e07a4917455b7d1b69c2e1de0a6bff02f6f95ffeab2c7821551bb99a06d` |
| Bootstrap receipt | `data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a/bootstrap_receipt.v1.json` | SHA-256 `9abae2dafc775e4e19226e172e3f42f0106e048bdb147545a0ad0666f217e7a2` |
| Candidate build | `data/processed/huiji/crawler-v3-20260721t051246z/build_manifest.json` | SHA-256 `293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f`; `state=ready_for_embedding` |
| Shadow evidence | `eval/huiji_provenance/20260721T060016Z-shadow-candidate-f-preflight/shadow-build.v1.json` | SHA-256 `0eb85ed2c60b4a500fef92ddad11e0fbbb190c32057e795a9f5a8dd4e1974cfa` |
| Full-chain evidence | `eval/huiji_candidate_full_chain/20260721T070710Z-candidate-f-shadow/full-chain.v1.json` | SHA-256 `8d95408baea543de9788a0b618e718fc202adc3cec8ecc849eb315c34f45b12c` |
| Wiki compatibility | `eval/huiji_wiki_v3_compatibility/20260720T162923Z/wiki_media_v3_compatibility_receipt.v1.json` | SHA-256 `b0c82cbaa77303819ee93f600c2f4518152984580bb36d636e0d5063a67ec56d` |
| Wiki rollback | `eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/wiki_pre_import_rollback_receipt.v1.json` | SHA-256 `e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6` |
| Legacy provenance | `config/provenance/huiji-dev.v1.json` | SHA-256 `dafd3a7b309fc96fe784945d4b5f143f3e8aec2e93a6856151e3a52fb4e8e6a4` |
| Candidate Milvus | `reverse1999_rag/text_child_bge_m3_shadow_crawler_v3_20260721t051246z` | rows `14630`; schema SHA `db9e13b98d7a1cf4116ba6647a16eb0e7daff0a77c558f66c9db2597038a6bc4`; primary IDs SHA `88dec5bd859acf331984772c21306e5655008872f305ba5f618b50ddec3b1ade`; business fields SHA `0ec89b966b64a2f6f4727c2dd6cb5ac09f01f96f3e26ec85a584e6b718374784` |
| Legacy Milvus | `reverse1999_rag/text_child_bge_m3_v3` | rows `16010`; schema SHA `db9e13b98d7a1cf4116ba6647a16eb0e7daff0a77c558f66c9db2597038a6bc4`; primary IDs SHA `35767849daf684742b66453a953837c85f93a9e8744d9c10516de7e3651ccb35`; business fields SHA `89dd551acb78f7bd3b55f7b3f284c85e8253d6f02dfb2bd8b4671d35e1c5208b` |
| Embedding identity | runtime config | model `BAAI/bge-m3`; config SHA `17787be97e63ea53e3298748adf546ebc17d5456669481349eb8bb088b336099` |

固定真实 execution identity：

```text
activation_id=candidate-f-generation-1-20260722a
activation_root=data/processed/huiji/activation/transactions/candidate-f-generation-1-20260722a
activation_lock=data/processed/huiji/.candidate-activation.lock
bootstrap_lock=data/processed/huiji/.generation-zero-bootstrap.lock
```

Plan 编写时 transaction root 不存在。inspect 运行时若已存在则停止并诊断，不自动更换 ID。

新增 evidence schema 固定为：

| 文件 | Schema |
|---|---|
| `activation_intent.v1.json` | `huiji.activation-intent/v1` |
| `collection_manifest.v1.json` | `evb.collection-manifest/v1` |
| `deployment_inventory.v1.json` | `huiji.activation-deployment-inventory/v1` |
| `protected_state.before.v1.json` | `rag_eval.protected_snapshot/v2` |
| `activation_journal.v1.jsonl` 每个 event | `huiji.activation-journal-event/v1` |
| `protected_state.after.v1.json` | `huiji.protected_compare/v1` |
| `activation_receipt.v1.json` | `huiji.activation-receipt/v1`，`status=passed` |
| `wiki_import_handoff.v1.json` | `huiji.wiki-import-handoff/v1`，`wiki_import_allowed=true` |
| `activation_failure.v1.json` | `huiji.activation-failure/v1` |

JSON 使用 canonical UTF-8、LF、排序键和尾随单换行；JSONL event 为单行 canonical JSON 并以 LF 结尾。journal 在未终态前只能 append；其余 transaction evidence 全部 create-new。`settings.before.yaml` 和 `settings.candidate.yaml` 保留 YAML 格式并分别生成 SHA-256 sidecar。

## 3. 计划修改位置

| 位置 | 用途 |
|---|---|
| `src/huiji_rag/active_pointer.py` | 扩展 full pointer validator 的 generation 1 固定契约与通用 evidence resolver |
| `src/huiji_rag/runtime_artifacts.py` | generation 1 pointer/manifest/artifact 严格解析；保持 legacy 和 generation 0 分支 |
| `src/huiji_rag/provenance.py` | pointer-aware runtime verifier；generation 1 改用 Candidate collection manifest，不改 legacy provenance |
| `src/huiji_rag/activation.py` | authority inspect、Candidate manifest、settings/pointer transaction、journal、recover、验证、receipt 和 handoff |
| `src/huiji_rag/backend_process.py` | Windows 127.0.0.1:8000 目标进程只读识别、精确停止、同命令重启和超时处理 |
| `requirements.txt` | 固定 `ruamel.yaml==0.17.21` 与 `psutil==7.2.2`，保证 YAML round-trip 和 Windows 进程 identity API 可复现 |
| `src/huiji_wiki/snapshot.py` | 复用 generation 1 shared pointer resolver；保持 legacy/v2/v3 双读契约 |
| `backend/main.py` | startup/health 继续消费统一 pointer-aware verifier；不增加 activation 写入口 |
| `scripts/activate_huiji_candidate.py` | `inspect`、`apply`、`recover` 三个独立 CLI |
| `scripts/verify_huiji_runtime.py` | 输出 generation/build/collection identity，保持 fail closed 与 hash-pinned evidence |
| `tests/test_huiji_active_pointer.py` | generation 1 schema、固定 tuple、path 和 tamper 测试 |
| `tests/test_huiji_runtime_artifacts.py` | legacy/generation-0/generation-1 三分支与混合 tuple 拒绝测试 |
| `tests/test_huiji_provenance.py` | generation-aware verifier、实时 Milvus 和 legacy provenance 不变测试 |
| `tests/test_huiji_activation.py` | authority、manifest、settings、journal、CAS、recover、receipt、handoff 和 mutation spies |
| `tests/test_huiji_activation_cli.py` | 三个命令的参数、确认文本、退出码、create-new 和敏感信息测试 |
| `tests/test_huiji_backend_process.py` | PID/command/port 白名单、停止/启动超时和单 PID 所有权测试 |
| `tests/test_backend_provenance_gate.py` | backend startup/health generation 1 与 invalid pointer fail-closed 回归 |
| `tests/test_huiji_wiki_snapshot.py` | Wiki reader 对 generation 1 v3 pointer 的兼容回归；不执行 MySQL import |

不修改 Retriever 的检索策略、QueryPlan、Builder、embedding/index writer、Wiki importer/repository/API DTO/React 或 MySQL schema。

## 4. 强制检查点

| 检查点 | Specs | 自动化门槛 | 真实数据门槛 | 失败表现 |
|---|---|---|---|---|
| C1 Authority 冻结 | `ACT-AUTH-P0-01..08` | 固定 proposal/rollback/receipt/hash/path/schema/tuple 测试 | 逐引用复算；fresh protected inventory 无未知漂移；两个 collection 实时指纹匹配 | 任一 authority、sidecar、状态、路径或业务 inventory 漂移即停在 inspect |
| C2 Candidate manifest | `ACT-MANIFEST-P0-01..06` | artifacts/BM25/Milvus/embedding/canonical bytes/tamper 测试 | manifest 与 Candidate bytes、handoff、shadow/full-chain evidence、实时 Milvus 一致 | 缺字段、计数替代内容 hash、collection drift、密钥字段或不可复现 bytes 即失败 |
| C3 Runtime authority | `ACT-RUNTIME-P0-01..06` | pointer absent/g0/g1 三分支、mixed tuple 和 invalid pointer 测试 | g0 pre-runtime 通过；g1 post-runtime 指向 14630-row Candidate；legacy provenance bytes 不变 | invalid pointer fallback、Candidate 使用 legacy provenance、settings/pointer 混用或组件 snapshot 分叉即失败 |
| C4 双文件事务 | `ACT-TXN-P0-01..10` | lock、journal、条件替换、每个 crash point recover 和 conflict 测试 | 后端离线窗口内只按顺序写 settings 后 pointer；旧 evidence/collection 保留 | 未停后端写文件、外部 SHA 被覆盖、非法 journal 迁移或 recover 猜测 operation 即失败 |
| C5 后端进程 | `ACT-PROC-P0-01..06` | PID 白名单、命令解析、停止/启动超时、只停 owned PID 测试 | 动态捕获真实解释器/cwd/args；停止后 PID 退出且 8000 无监听；新 PID 健康并保留运行 | 端口 owner 不匹配、停止不完整、命令被 shell 重组、新 PID 提前退出或 timeout 即失败/补偿 |
| C6 验证与补偿 | `ACT-VERIFY-P0-01..07` | 任一 post-write gate 注入失败均回滚；unknown SHA 进入 conflict | health、分层抽样 retrieval、voice cursor、Wiki health、protected compare 全通过；失败演练恢复 g0 | 可归属失败未恢复 g0、unknown state 被覆盖、passing/failure 并存或业务存储变化即失败 |
| C7 Wiki handoff | `ACT-WIKI-P0-01..05` | committed-only handoff、hash pins、无 importer/restore 调用测试 | handoff pins active Candidate 和两个 Wiki receipts；Wiki 正式导入仍未发生 | rolled_back/conflict 生成 handoff、预写 Wiki 成功或 RAG 修改 Wiki MySQL 即失败 |
| C8 回归与交付 | 全部 P0 | 新增目标测试、RAG/Wiki 回归、全量 pytest、48/48 matrix | committed recover 幂等；active tuple 完整；旧 collection 可用；服务在线 | 任一测试/P0/真实门禁未闭合，不得交付 handoff |

## 5. TDD 实施步骤

每个实现步骤必须先写失败测试并确认失败原因正确，再做最小实现，随后运行目标测试。禁止先修改真实 settings、pointer 或后端进程再补实现。

### Step 0：执行前只读基线

- 对应 Specs：全部 P0 的前置条件。
- 只读检查：
  - 复算第 2 节全部文件 SHA；
  - 确认 transaction root 不存在；
  - 验证 proposal、rollback tuple、bootstrap receipt 和两个 Wiki receipts；
  - 运行 generation-0 runtime verifier；
  - 读取两个 Milvus collection fingerprint；
  - 采集当前 `/health` 和 `/api/wiki/health`；
  - 动态识别 127.0.0.1:8000 listener，但不发送停止信号；
  - 记录脏工作树，仅用于保护用户改动，不执行 git 操作。
- 命令：

```powershell
$Spec = 'docs/superpowers/specs/2026-07-22-huiji-rag-candidate-f-activation-design.md'
$Proposal = 'data/processed/huiji/activation/proposals/candidate-f-review-20260722c/activation_proposal.v1.json'
$Rollback = 'data/processed/huiji/activation/proposals/candidate-f-review-20260722c/rollback_tuple.v1.json'
$Pointer = 'data/processed/huiji/active_build.v1.json'
$Settings = 'config/settings.yaml'
$ActivationId = 'candidate-f-generation-1-20260722a'
$ActivationRoot = "data/processed/huiji/activation/transactions/$ActivationId"
$PreRuntime = 'eval/huiji_activation/candidate-f-generation-1-20260722a-pre-runtime'

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Spec).Hash.ToLower() -ne '7d3e3829a36d0aef143aef640c133247bd8d05a399199a6ad1d2c8f4e9ed279a') { throw 'Spec hash drift' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Proposal).Hash.ToLower() -ne 'fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8') { throw 'Proposal hash drift' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Rollback).Hash.ToLower() -ne '07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b') { throw 'Rollback tuple hash drift' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Pointer).Hash.ToLower() -ne '95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723') { throw 'Pointer hash drift' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Settings).Hash.ToLower() -ne 'd5363e07a4917455b7d1b69c2e1de0a6bff02f6f95ffeab2c7821551bb99a06d') { throw 'Settings hash drift' }
if (Test-Path -LiteralPath $ActivationRoot) { throw 'Activation root already exists' }
if (Test-Path -LiteralPath $PreRuntime) { throw 'Pre-runtime evidence already exists' }

python scripts/verify_huiji_runtime.py --run-dir $PreRuntime
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 15 | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/wiki/health' -TimeoutSec 15 | ConvertTo-Json -Depth 8
```

- 门槛：C1/C3 前置通过。任何 drift 停止，不写 transaction root。

### Step 1：TDD 扩展 generation 1 pointer 和 runtime artifact resolver

- 对应 Specs：`ACT-MANIFEST-P0-06`、`ACT-RUNTIME-P0-01..06`。
- 先写失败测试：
  - generation 1 缺 `previous_build_version`、epoch 不为 1、Candidate 固定 tuple 任一字段错误时拒绝；
  - pointer 不存在只走 legacy fallback；generation 0 只走 bootstrap manifest；generation 1 只走 Candidate manifest；
  - invalid pointer 不回退、unknown generation 不猜测、settings 与 pointer 三字段任一不一致即失败；
  - Candidate parent/child/media/BM25 的 path/hash/size/schema/rows 任一漂移即失败；
  - Retriever、EntityLexicon、media registry、voice pagination 和 Wiki snapshot 使用同一 resolved snapshot identity；
  - generation 0 和现有 Wiki legacy/v2/v3 fixtures 全部保持通过。
- 最小实现：
  - `active_pointer.py` 增加通用 activation evidence resolver，不把固定 transaction path写入 pointer；
  - generation 1 pointer 由 `activation_id` 定位 transaction 内 manifest/inventory；
  - `runtime_artifacts.py` 严格校验 Candidate build manifest 和全部 runtime artifact；
  - `huiji_wiki/snapshot.py` 复用 shared validator，不复制 generation 1 schema；
  - resolved snapshot 显式携带 generation/build/collection/pointer SHA/manifest SHA，供全部消费者检查。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_active_pointer.py tests/test_huiji_runtime_artifacts.py tests/test_huiji_wiki_snapshot.py
python -m pytest -q tests/test_retriever.py tests/test_voice_pagination.py tests/test_huiji_only_runtime_policy.py
```

- 门槛：C3 resolver 部分通过；不得修改真实 pointer。

### Step 2：TDD 实现 Candidate collection manifest 与 activation authority inspect

- 对应 Specs：`ACT-AUTH-P0-01..08`、`ACT-MANIFEST-P0-01..05`。
- CLI 契约：

```text
python scripts/activate_huiji_candidate.py inspect
  --activation-id candidate-f-generation-1-20260722a
  --proposal <path> --expected-proposal-sha256 <sha>
  --rollback-tuple <path> --expected-rollback-tuple-sha256 <sha>
  --expected-pointer-sha256 <sha>
  --expected-settings-sha256 <sha>
```

- 先写失败测试：
  - 非法 ID、已有 transaction root、错误 project root、path escape、symlink/junction、已有未终态 journal 均拒绝；
  - proposal ID/schema/status/blockers/next gate/rollback flag 任一错误即拒绝；
  - rollback tuple 缺 previous pointer/settings/Milvus/artifacts/provenance/Wiki restore/两个 MinIO scope 任一项即拒绝；
  - proposal 引用的 shadow/full-chain/bootstrap/Wiki receipts/protected evidence 任一 path/hash/schema/status 漂移即拒绝；
  - Candidate manifest/artifact/handoff/实时 Milvus 任一 fingerprint 漂移即拒绝；
  - fresh MySQL、两个 MinIO scope、legacy/Candidate Milvus 和 protected artifacts 出现未知变化即拒绝；
  - manifest 不 canonical、缺 sidecar、包含 secret-like field 或只验证 row count 时拒绝；
  - mutation spies 证明 inspect 不改 settings/pointer、不停后端、不写业务 store。
- 最小实现：
  - `activation.py` 在内存完成全部 authority 校验后才 create-new transaction root；
  - 复用现有 strict receipt validators、protected-state collector、Milvus fingerprint 和 canonical writer；
  - collection manifest pin Candidate build、parent、child、media v3、两个 BM25、embedding handoff、shadow/full-chain evidence和实时 collection identity；
  - deployment inventory pin settings before、pointer before、后端 process identity 和允许变化边界；
  - inspect 用 `ruamel.yaml` round-trip 生成 `settings.candidate.yaml`，只改三个 scalar；
  - inspect 生成 generation 1 pointer candidate，但不替换 canonical pointer；
  - intent pin 所有输入和全部 candidate bytes SHA。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_activation.py -k "authority or inspect or manifest or settings or protected"
python -m pytest -q tests/test_huiji_activation_cli.py -k "inspect or create_new or secret"
```

- 门槛：C1/C2 通过；真实 backend/settings/pointer 未变化。

### Step 3：TDD 改造 pointer-aware runtime verifier

- 对应 Specs：`ACT-MANIFEST-P0-06`、`ACT-RUNTIME-P0-01..05`。
- 先写失败测试：
  - pointer absent、generation 0、generation 1 三条路径分别选择正确 authority；
  - generation 1 不读取 `huiji-dev.v1.json` 作为 Candidate baseline；
  - settings build、vectorstore collection、Huiji collection 与 pointer 任一不一致时返回 blocked；
  - Candidate artifact、BM25、manifest、Milvus schema/rows/IDs/business fields 任一漂移时 fail closed；
  - invalid pointer、unsupported generation 或混合 tuple 时 backend startup 不加载 vectorstore；
  - generation 0 verifier 回归通过，legacy provenance 文件 bytes 不变。
- 最小实现：
  - `verify_runtime()` 先解析统一 runtime snapshot，再按 snapshot generation 分支；
  - generation 0 保留 installed provenance + bootstrap manifest；generation 1 使用 transaction collection manifest + live Milvus；
  - public result 增加非敏感 generation/build/collection identity；
  - `backend/main.py` 仍只有读取 gate，不新增 activation endpoint。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_provenance.py tests/test_backend_provenance_gate.py
python -m pytest -q tests/test_huiji_runtime_artifacts.py tests/test_huiji_wiki_snapshot.py
```

- 门槛：C3 全部自动化门禁通过。

### Step 4：TDD 实现 Windows backend process controller

- 对应 Specs：`ACT-TXN-P0-04..05`、`ACT-TXN-P0-08`、`ACT-PROC-P0-01..06`。
- 先写失败测试：
  - inspect 仅识别 listener，不发停止信号；
  - 只接受 local address `127.0.0.1`、port `8000`、单 listener、`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`；
  - PID、executable、cwd、argv、listener 任一在 inspect/apply 间漂移即拒绝；
  - 不接受 shell wrapper、不同 app、不同 port、多个 listener、缺失 executable 或 path escape；
  - stop timeout 时不写 settings/pointer；start timeout 或提前退出时进入补偿；
  - restart 使用参数数组而非 shell 字符串，保留已验证解释器/cwd/argv，不记录环境变量值；
  - post-write 失败只终止本 operation 启动的 PID；不按进程名批量终止；
  - activation CLI 成功退出后新 PID 继续运行。
- 最小实现：
  - `requirements.txt` 增加当前已验证版本 `ruamel.yaml==0.17.21` 和 `psutil==7.2.2`；
  - `backend_process.py` 使用 `psutil.net_connections(kind="tcp")` 解析唯一 listener，并用 `Process.exe()`、`cwd()`、`cmdline()`、`create_time()` 获取不依赖 shell 文本解析的 identity；
  - argv 与固定 uvicorn grammar 比较，PID 复用由 create time 共同防护；
  - apply 重新读取并匹配 frozen process identity 后精确停止 PID，等待 PID 退出和 8000 无监听；
  - 使用 `subprocess.Popen(frozen_argv, cwd=frozen_cwd, shell=False, creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS)` 和 create-new stdout/stderr 文件启动；环境来自 apply 进程，密钥仅在内存继承，不从旧进程导出；
  - 启动后先验证新 PID 拥有 8000，再运行 health gates；停止、启动和健康等待均有单调时钟超时并在超时后抛错。
- 测试命令：

```powershell
python -m pip check
python -m pytest -q tests/test_huiji_backend_process.py
python -m pytest -q tests/test_huiji_activation.py -k "process or backend or timeout"
```

- 门槛：C5 通过；不得在自动化测试中停止真实 backend。

### Step 5：TDD 实现 settings/pointer 事务、journal 与 recover

- 对应 Specs：`ACT-TXN-P0-01..10`、`ACT-VERIFY-P0-03..06`。
- 先写失败测试：
  - apply 缺 intent SHA、proposal SHA、rollback SHA、pointer SHA、settings SHA 或精确确认文本时拒绝；
  - activation lock 与 bootstrap lock 互斥；遗留空 lock file 不冒充持锁；
  - journal sequence/hash chain/状态迁移错误时拒绝；
  - settings 仅三个 scalar 改变，注释、顺序、换行和其余解析结构不变；
  - settings/pointer 替换前 target SHA 漂移进入 conflict，不覆盖未知状态；
  - `backend_stopped`、`settings_written`、`pointer_written`、`backend_started`、`verified` 各 crash point 可由同 activation ID + intent SHA 恢复；
  - settings-only 和 pointer-only 中间状态不对外服务；
  - post-write 可归属失败先停 new PID，再按精确 after SHA 恢复 pointer/settings，然后重启并验证 g0；
  - target 为未知 SHA 时进入 conflict、保留后端离线和全部 evidence；
  - committed recover 幂等，不重写 canonical files、不重启 backend、不生成第二份 receipt；
  - generation-0 evidence、legacy/Candidate collection 和 rollback tuple 永不删除。
- 最小实现：
  - advisory lock 使用 OS file lock，activation 和 bootstrap 入口互相探测；
  - journal 状态固定为 Spec 的成功/失败分支，event append 后 flush/fsync；
  - 两个 candidate 文件分别在目标同卷目录完整写入、flush/fsync，再在替换前复核 frozen target SHA；
  - 写入顺序固定为 settings 后 pointer；恢复顺序固定为 pointer 后 settings，保证启动前恢复完整 g0 tuple；
  - journal 和 target 实际 SHA 是 recover 的唯一决策依据，不选择 latest transaction；
  - passing/failure/conflict evidence 互斥；failure 写入 `$FailedGate` 等价字段 `failed_gate`。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_activation.py -k "journal or lock or transaction or recover or rollback or conflict"
python -m pytest -q tests/test_huiji_activation_cli.py -k "apply or recover or confirmation"
```

- 门槛：C4 和 C6 补偿部分通过。

### Step 6：TDD 实现真实验收、activation receipt 与 Wiki handoff

- 对应 Specs：`ACT-VERIFY-P0-01..07`、`ACT-WIKI-P0-01..05`。
- 先写失败测试：
  - `/health` 必须 `status=ok`、`provenance_status=pass`、`vectorstore_loaded=true`、`doc_count=14630`；
  - 动态分层抽样从 Candidate inventory 选择多个不同 entity，覆盖 profile、skill、voice、skill+voice、collection、culture dossier 和 Udimo；禁止按单一角色写死；
  - 每个 retrieval source 都属于 Candidate resolved snapshot，不能出现 Obsidian、`data/raw`、legacy build 或 foreign parent；
  - voice 首屏按台词分页，后续 cursor 的 build identity 为 Candidate，跨页无重复 line/binding，语言变体保持在台词内；
  - Wiki health pre/post 的 ready/page/media inventory 不变化，且不调用 importer/restore；
  - MySQL、两个 MinIO scope、legacy/Candidate Milvus 和 immutable artifacts 只允许 transaction evidence、settings 三字段、pointer 替换；
  - P0 matrix 缺任一 48 ID 不得 passing；
  - journal 非 committed、failure/rollback/conflict 时不得写 passing receipt 或 handoff；
  - handoff pins pointer、Candidate build、media v3 manifest、Wiki compatibility、Wiki rollback 和 activation receipt；
  - receipt/handoff 不包含“Wiki import succeeded”或任何密钥值。
- 最小实现：
  - activation post-verifier 复用 Candidate full-chain 的动态 sample selector，不复制角色清单；
  - API health、offline runtime、retrieval、voice traversal、Wiki health 和 protected compare 分别写 hash-pinned evidence；
  - 任一 gate 失败设置 `failed_gate` 并调用统一 compensation；
  - 只有全部 gate 通过后 append `committed`，再 create-new passing receipt 和 handoff；
  - handoff 明确 `wiki_import_allowed=true` 仅授权 Wiki 进入自己的 import Plan，不代表导入已经执行。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_activation.py -k "verify or receipt or handoff or sample or voice or mutation"
python -m pytest -q tests/test_huiji_activation_cli.py
python -m pytest -q tests/test_backend_provenance_gate.py tests/test_voice_pagination.py tests/test_huiji_wiki_snapshot.py
```

- 门槛：C6/C7 自动化门禁通过。

### Step 7：故障注入、回归与静态边界检查

- 对应 Specs：全部 P0。
- 故障注入：对每个 journal 写后 crash point、后端停止/启动 timeout、health/runtime/retrieval/voice/Wiki/protected gate 失败和 target SHA conflict 逐项运行。
- mutation spies：断言没有 Milvus insert/delete/drop/rename/alias、MinIO put/delete、MySQL DDL/DML、Wiki importer/restore、legacy provenance write 或 Candidate artifact write。
- 回归命令：

```powershell
python -m pytest -q tests/test_huiji_active_pointer.py tests/test_huiji_runtime_artifacts.py tests/test_huiji_provenance.py tests/test_huiji_activation.py tests/test_huiji_activation_cli.py tests/test_huiji_backend_process.py tests/test_backend_provenance_gate.py tests/test_huiji_wiki_snapshot.py tests/test_retriever.py tests/test_voice_pagination.py
python -m pytest -q tests/test_huiji_generation_zero.py tests/test_huiji_generation_zero_cli.py tests/test_huiji_activation_proposal.py tests/test_huiji_corpus_cli.py
python -m pytest -q
rg -n "insert|upsert|delete|drop_collection|rename|create_alias|alter_alias|put_object|remove_object|import_huiji_wiki|restore_wiki" src/huiji_rag/activation.py src/huiji_rag/backend_process.py scripts/activate_huiji_candidate.py
```

- 静态门槛：命中必须逐条证明仅为 denylist/mutation-spy/错误消息；生产 activation 路径不得持有这些写能力。
- 门槛：C1-C8 自动化部分全部通过后，才允许真实 inspect。

## 6. 真实 Candidate F Activation

### Step 8：运行只读 inspect 并冻结 intent

- 前置：Plan 已另行得到用户执行批准；Step 0-7 全部通过；后端仍为 generation 0 且在线。
- 命令：

```powershell
$ActivationId = 'candidate-f-generation-1-20260722a'
$ActivationRoot = "data/processed/huiji/activation/transactions/$ActivationId"
$Proposal = 'data/processed/huiji/activation/proposals/candidate-f-review-20260722c/activation_proposal.v1.json'
$Rollback = 'data/processed/huiji/activation/proposals/candidate-f-review-20260722c/rollback_tuple.v1.json'

python scripts/activate_huiji_candidate.py inspect `
  --activation-id $ActivationId `
  --proposal $Proposal `
  --expected-proposal-sha256 fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8 `
  --rollback-tuple $Rollback `
  --expected-rollback-tuple-sha256 07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b `
  --expected-pointer-sha256 95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723 `
  --expected-settings-sha256 d5363e07a4917455b7d1b69c2e1de0a6bff02f6f95ffeab2c7821551bb99a06d

$Intent = "$ActivationRoot/activation_intent.v1.json"
$IntentSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Intent).Hash.ToLower()
$IntentSidecar = (Get-Content -LiteralPath "$Intent.sha256" -Raw -Encoding UTF8).Trim().Split(' ')[0].ToLower()
if ($IntentSha -ne $IntentSidecar) { throw 'Intent sidecar mismatch' }

$CandidateSettingsSha = (Get-FileHash -Algorithm SHA256 -LiteralPath "$ActivationRoot/settings.candidate.yaml").Hash.ToLower()
$CandidatePointerSha = (Get-FileHash -Algorithm SHA256 -LiteralPath "$ActivationRoot/active_build.candidate.v1.json").Hash.ToLower()
$CollectionManifestSha = (Get-FileHash -Algorithm SHA256 -LiteralPath "$ActivationRoot/collection_manifest.v1.json").Hash.ToLower()
if (-not $IntentSha -or -not $CandidateSettingsSha -or -not $CandidatePointerSha -or -not $CollectionManifestSha) { throw 'Inspect evidence incomplete' }
```

- inspect 后机械复核：
  - `settings.before.yaml` SHA 等于 frozen settings；
  - candidate settings 解析后仅三个批准字段变化；
  - candidate pointer 为 generation/epoch 1 且 pin 同 transaction manifest/inventory；
  - process identity 是当前唯一 8000 listener；
  - protected before 无未知 drift；
  - canonical settings/pointer 和 backend PID 均未变化。
- 门槛：任一不符停止，不进入 apply；保留 create-new inspect evidence用于诊断。

### Step 9：执行受控切换；失败时自动补偿

- apply 固定完成以下单一控制流，不依赖人工在离线窗口逐步批准：
  1. 重新验证所有 frozen hashes、intent 和 process identity；
  2. 获取双 lock；
  3. 精确停止 frozen backend PID并确认 8000 无 listener；
  4. 条件替换 settings；
  5. 条件替换 pointer；
  6. 用 frozen executable/cwd/argv 启动新 backend；
  7. 执行全部 post-write gates；
  8. 成功则 committed；失败则统一自动补偿并验证 generation 0；未知 SHA conflict 才保持离线停止。
- 命令：

```powershell
$Confirmation = "ACTIVATE $ActivationId FROM 95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723 TO crawler-v3-20260721t051246z"
$UserApiKey = [Environment]::GetEnvironmentVariable('SILICONFLOW_API_KEY', 'User')
if ([string]::IsNullOrWhiteSpace($UserApiKey)) { throw 'User SILICONFLOW_API_KEY is unavailable' }
$env:SILICONFLOW_API_KEY = $UserApiKey
try {
  python scripts/activate_huiji_candidate.py apply `
    --intent $Intent `
    --expected-intent-sha256 $IntentSha `
    --expected-proposal-sha256 fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8 `
    --expected-rollback-tuple-sha256 07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b `
    --expected-pointer-sha256 95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723 `
    --expected-settings-sha256 d5363e07a4917455b7d1b69c2e1de0a6bff02f6f95ffeab2c7821551bb99a06d `
    --confirmation $Confirmation
  $ActivationExit = $LASTEXITCODE
} finally {
  Remove-Item Env:SILICONFLOW_API_KEY -ErrorAction SilentlyContinue
  Remove-Variable UserApiKey -ErrorAction SilentlyContinue
}
```

该变量只在运行 apply 的 PowerShell 进程及其新 backend 子进程中继承；CLI、日志和 evidence 只能记录密钥变量名存在，不得记录值或值的 hash。父 PowerShell 在 apply 返回后立即清除进程级变量。

- 退出处理：
  - exit `0`：只表示 committed receipt 和 handoff 已通过 validator；继续 Step 10；
  - exit `2`：已自动 rolled back 且 generation 0 健康；保留 failure evidence，停止本 Plan；
  - exit `3`：conflict 或 rollback verification failure；后端保持离线，立即运行同 ID recover 诊断，不手工覆盖文件；
  - 进程被外部中断：运行以下 recover，不重新运行 apply。

```powershell
python scripts/activate_huiji_candidate.py recover `
  --activation-id $ActivationId `
  --expected-intent-sha256 $IntentSha
```

- recover 若仍为 conflict，停止并扩大只读检查范围；不得用复制命令手工恢复 settings/pointer。

### Step 10：committed 真实验收与幂等复核

- 仅在 Step 9 exit `0` 后执行：

```powershell
$PostRuntime = 'eval/huiji_activation/candidate-f-generation-1-20260722a-post-runtime'
$RetrievalEvidence = 'eval/huiji_activation/candidate-f-generation-1-20260722a-retrieval.v1.json'
$Receipt = "$ActivationRoot/activation_receipt.v1.json"
$Handoff = "$ActivationRoot/wiki_import_handoff.v1.json"

python scripts/verify_huiji_runtime.py --run-dir $PostRuntime
python scripts/verify_multi_intent_voice.py evaluate --output $RetrievalEvidence --limit 8 --base-url http://127.0.0.1:8000

$Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 15
if ($Health.status -ne 'ok' -or -not $Health.vectorstore_loaded -or $Health.provenance_status -ne 'pass' -or $Health.doc_count -ne 14630) { throw 'Candidate health gate failed' }
$WikiHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/wiki/health' -TimeoutSec 15
if (-not $WikiHealth.ready) { throw 'Wiki health gate failed' }

if (-not (Test-Path -LiteralPath $Receipt) -or -not (Test-Path -LiteralPath "$Receipt.sha256")) { throw 'Activation receipt missing' }
if (-not (Test-Path -LiteralPath $Handoff) -or -not (Test-Path -LiteralPath "$Handoff.sha256")) { throw 'Wiki handoff missing' }

python scripts/activate_huiji_candidate.py recover `
  --activation-id $ActivationId `
  --expected-intent-sha256 $IntentSha
```

- committed recover 前后复算 canonical settings、pointer、receipt、handoff 和 backend PID；必须完全不变。
- 最终真实门槛：
  - pointer 为 generation 1，settings 三字段与 pointer 一致；
  - runtime identity 为 Candidate F，doc count 14630；
  - retrieval evidence 使用动态多角色/多 section 抽样，全部 sources 为 crawler-only Candidate；
  - voice pagination 全页遍历无重复并 pin Candidate build；
  - MySQL、两个 MinIO scope、legacy/Candidate Milvus、legacy provenance 和 immutable artifacts 无未授权变化；
  - journal `committed`；receipt P0 matrix 为 48/48；
  - Wiki handoff validator 通过，但 Wiki MySQL 正式导入尚未执行；
  - 旧 `text_child_bge_m3_v3` collection 保留且指纹不变。

### Step 11：向 Wiki 线路交付唯一 handoff

- 交付值必须来自文件实际 SHA，不手写预估值：

```powershell
$ReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Receipt).Hash.ToLower()
$HandoffSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Handoff).Hash.ToLower()
"rag_activation_receipt_path=$Receipt"
"rag_activation_receipt_file_sha256=$ReceiptSha"
"wiki_import_handoff_path=$Handoff"
"wiki_import_handoff_file_sha256=$HandoffSha"
```

- Wiki 线路只能消费这四个值，并仍须执行自己的事务化 MySQL import、双表切换、页面验收和 rollback gate。
- RAG 线路在交付后不代替 Wiki 执行 import，也不因为 Wiki import 失败自动回滚 generation 1；该决定必须另行审查。

## 7. 失败、恢复与停止规则

| 阶段 | 失败状态 | 自动动作 | 是否人工介入 |
|---|---|---|---|
| Step 0-2 inspect 前 | authority/hash/schema/drift 错误 | 不创建或只保留 create-new诊断 evidence；后端保持 g0 在线 | 仅在原因无法从 evidence 定位时 |
| 后端停止前 | PID/command/port/lock 漂移 | 不发送停止信号，不写 canonical files | 仅 process owner 不明确时 |
| 后端停止失败 | `backend_stop_failed` | 不写 settings/pointer；确认原 backend 状态 | 只有端口状态未知时 |
| settings/pointer 写后 | 可归属 operation 的 gate 失败 | 停 new PID，条件恢复 pointer 后 settings，重启并验证 g0 | 自动补偿成功则无需中途审核 |
| 任一 canonical target 未知 SHA | `conflict` | 不覆盖；后端保持离线；保留 evidence | 必须只读扩大检查范围后决定 |
| generation-0 rollback 验证失败 | `rollback_verification_failed` | 后端保持离线；不生成 handoff | 必须诊断，不伪造恢复成功 |
| committed 后 | recover 重复执行 | 只读验证并返回 already committed | 无需人工介入 |

不允许以手工 `Copy-Item`、文本编辑、删除 transaction root、删除 lock 文件或启动另一个 8000 backend 绕过 recover。

## 8. P0 覆盖矩阵

| Specs | 实施步骤 | 自动测试 | 真实 evidence |
|---|---|---|---|
| `ACT-AUTH-P0-01..08` | Step 0、2、8 | activation authority/CLI/protected tests | intent、deployment inventory、protected before |
| `ACT-MANIFEST-P0-01..06` | Step 1-3、8 | manifest/runtime/tamper tests | collection manifest、live Candidate fingerprint |
| `ACT-TXN-P0-01..10` | Step 4-5、9-10 | lock/journal/CAS/crash/recover tests | journal、before/candidate files、committed recover |
| `ACT-RUNTIME-P0-01..06` | Step 1、3、6、10 | three-branch runtime/backend/consumer tests | pre/post runtime、health、retrieval identity |
| `ACT-PROC-P0-01..06` | Step 4、8-10 | process identity/timeout/ownership tests | before/new process identity、logs、port checks |
| `ACT-VERIFY-P0-01..07` | Step 5-7、9-10 | compensation/receipt/P0/mutation tests | post gates、protected after、passing receipt |
| `ACT-WIKI-P0-01..05` | Step 6、10-11 | handoff/receipt/no-import tests | hash-pinned handoff、unchanged Wiki health/MySQL |

Receipt 中每个 P0 条目必须记录：Spec ID、status、实现位置、自动测试引用、真实 evidence path/hash 和失败码。静态计数或整组 `passed=true` 不能替代逐项条目。

执行完成后必须按以下 48 项逐项自检，不允许用范围表达替代 receipt 中的独立条目：

| Spec ID | 完成条件 |
|---|---|
| `ACT-AUTH-P0-01` | 固定 ID/root，inspect create-new |
| `ACT-AUTH-P0-02` | 固定 proposal hash、状态和 next gate 通过 |
| `ACT-AUTH-P0-03` | rollback tuple 全引用和两个 MinIO scope 通过 |
| `ACT-AUTH-P0-04` | previous pointer SHA 与 generation-0 tuple 通过 |
| `ACT-AUTH-P0-05` | Candidate manifest、state 和全部 artifact pins 通过 |
| `ACT-AUTH-P0-06` | shadow/full-chain/Wiki/bootstrap receipts 逐项复核通过 |
| `ACT-AUTH-P0-07` | Candidate live Milvus 四类 fingerprint 通过 |
| `ACT-AUTH-P0-08` | fresh protected inventory 无未知 drift |
| `ACT-MANIFEST-P0-01` | parent/child/media/BM25 path/hash/size/schema/rows 完整 |
| `ACT-MANIFEST-P0-02` | Candidate Milvus identity 完整 |
| `ACT-MANIFEST-P0-03` | embedding identity 固定且无密钥落盘 |
| `ACT-MANIFEST-P0-04` | build/handoff/shadow/full-chain 引用无漂移 |
| `ACT-MANIFEST-P0-05` | canonical manifest 和 sidecar 通过 |
| `ACT-MANIFEST-P0-06` | generation-1 reader 对 artifact/live Milvus fail closed |
| `ACT-TXN-P0-01` | apply 的全部 SHA 和确认文本参数齐全 |
| `ACT-TXN-P0-02` | activation/bootstrap advisory lock 互斥 |
| `ACT-TXN-P0-03` | journal 成功/失败状态机与 hash chain 完整 |
| `ACT-TXN-P0-04` | frozen PID/executable/cwd/argv/port identity 完整 |
| `ACT-TXN-P0-05` | PID 退出且 8000 无 listener 后才写入 |
| `ACT-TXN-P0-06` | 同卷临时文件、fsync 和写前 SHA 复核通过 |
| `ACT-TXN-P0-07` | settings 后 pointer 顺序和逐 event fsync 通过 |
| `ACT-TXN-P0-08` | 使用 frozen argv 无 shell 重启且不泄漏环境值 |
| `ACT-TXN-P0-09` | recover 只接受同 ID 和 intent SHA 并按实际 SHA 决策 |
| `ACT-TXN-P0-10` | generation-0 evidence、两个 collection 和 rollback tuple 保留 |
| `ACT-RUNTIME-P0-01` | absent/g0/g1 三个 verifier 分支明确 |
| `ACT-RUNTIME-P0-02` | settings 三字段与 pointer 完全一致 |
| `ACT-RUNTIME-P0-03` | Candidate artifacts、BM25 和 live Milvus 全验证 |
| `ACT-RUNTIME-P0-04` | legacy provenance activation 前后字节不变 |
| `ACT-RUNTIME-P0-05` | backend/RAG/Wiki/offline verifier 共用 strict validator |
| `ACT-RUNTIME-P0-06` | Retriever/lexicon/media/voice 使用同一 resolved snapshot |
| `ACT-PROC-P0-01` | inspect 只读，apply 只停 frozen PID |
| `ACT-PROC-P0-02` | 未停止非目标服务/进程且未调用 Wiki importer |
| `ACT-PROC-P0-03` | stop/start/health timeout 有确定失败状态 |
| `ACT-PROC-P0-04` | 新 PID 隐藏启动，evidence 不含环境变量值 |
| `ACT-PROC-P0-05` | 失败时只停止本 operation 新 PID |
| `ACT-PROC-P0-06` | 成功后 backend 在 CLI 退出后继续运行 |
| `ACT-VERIFY-P0-01` | receipt 的全部 authority/evidence 引用 hash-pinned |
| `ACT-VERIFY-P0-02` | receipt 独立记录 48 条 P0 |
| `ACT-VERIFY-P0-03` | post-write 失败按 owned new PID、pointer、settings 顺序补偿 |
| `ACT-VERIFY-P0-04` | rollback 后 generation-0 runtime/health/retrieval 恢复 |
| `ACT-VERIFY-P0-05` | unknown target SHA 进入 conflict 且保持离线 |
| `ACT-VERIFY-P0-06` | passing/rollback/failure/conflict evidence 互斥 |
| `ACT-VERIFY-P0-07` | protected compare 仅含获批变化且业务存储零差异 |
| `ACT-WIKI-P0-01` | 仅 committed passing receipt 可生成 handoff |
| `ACT-WIKI-P0-02` | handoff pin pointer/build/media/Wiki receipts/activation receipt |
| `ACT-WIKI-P0-03` | handoff 声明 generation 1 和独立 Wiki import gate |
| `ACT-WIKI-P0-04` | RAG 未修改 Wiki MySQL、未调用 import/restore、未预写成功 |
| `ACT-WIKI-P0-05` | Wiki rollback 与 RAG rollback 决策保持解耦 |

## 9. P1/P2 与 Deferred

本 Plan 主线只包含 P0。以下不进入执行任务：

- P1：支持任意未来 Candidate proposal、请求 drain、维护页、持续观察窗口、Wiki import acknowledgement；
- P2：远程审批、多签、Milvus alias、蓝绿多后端、跨主机锁、自动流量回滚、在线多 generation；
- Wiki v3 正式导入和页面验收；
- collection 清理或重命名；
- MinIO orphan 清理；
- 重新向量化；
- 长期 SLO/性能调优。

## 10. 完成判定与交付

只有以下条件全部成立，才能宣布 Candidate F activation 完成：

1. 48 条 P0 均有实现、自动测试和真实 evidence；
2. active pointer、settings、Candidate artifacts 和 active Milvus 组成完整 generation 1 tuple；
3. backend 以原已验证解释器/cwd/argv 重启并持续运行；
4. runtime、health、动态分层抽样 retrieval 和 voice pagination 全部通过；
5. MySQL、两个 MinIO scope、legacy/Candidate Milvus、legacy provenance 和 immutable artifacts 无未授权变化；
6. journal 为 `committed`，committed recover 幂等；
7. activation receipt 和 Wiki handoff 都存在、hash-pinned 且通过 strict validator；
8. generation-0 rollback authority 和旧 collection 保持可用；
9. Wiki v3 正式导入仍未执行。

仅完成代码、仅通过单测、仅修改 settings、仅替换 pointer、仅重启 backend、仅 health 通过或仅生成 handoff，均不能单独宣称 activation 完成。

## 11. 执行记录（2026-07-22）

### 11.1 不可变尝试历史

计划中的 `candidate-f-generation-1-20260722a` 已作为第一次 create-new operation 保留，未覆盖或删除。后续每次重试均使用新的 operation ID：

| Operation | 结果 | 失败门禁 / 处置 | Intent SHA-256 |
|---|---|---|---|
| `candidate-f-generation-1-20260722a` | `rolled_back` | `retrieval_smoke`；修正 evaluator 对 legacy media path 的假设后扩大回归 | `fc9ea4c71243da3a85e7b1c70e86680852154541c44bf4aa49c2845791f22fcb` |
| `candidate-f-generation-1-20260722b` | `rolled_back` | `voice_pagination`；修正 typed scope 与 API owner identity、`binding_id` 身份规则 | `5ed9f3ada392045aa95fc52364207a94660b712be99d0ecca1266f969d7c08fb` |
| `candidate-f-generation-1-20260722c` | `rolled_back` | `voice_pagination`；修正配额感知的 text-only anomaly 判定 | `1aed68fc1288646b029561c3eaadb34131656d82174a33c11efd3a1b1eeb5b0e` |
| `candidate-f-generation-1-20260722d` | `committed` | 全部 post-write gates 通过 | `b1fc77f45322acaa581b3e00fb25e1b49694e4a419ccb2b01f9d66ed1adeb87b` |

a/b/c 的 failure、journal、before/candidate files 和 hash sidecar 均原样保留。三次失败都由统一补偿流程恢复 generation 0，未留下非终态 journal；最终 d 未复用任何失败 transaction root。

### 11.2 最终 active tuple

- activation ID：`candidate-f-generation-1-20260722d`
- active generation：`1`
- build：`crawler-v3-20260721t051246z`
- collection：`text_child_bge_m3_shadow_crawler_v3_20260721t051246z`
- active rows：`14630`
- active pointer SHA-256：`87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e`
- settings SHA-256：`d2b25e7dfbb41a0b1c13e7d3964dbcf286380c0bdf2cc5ee920c1e0d1be5d473`
- activation receipt：`data/processed/huiji/activation/transactions/candidate-f-generation-1-20260722d/activation_receipt.v1.json`
- activation receipt SHA-256：`78310c7f0009c6df88413f5a888940d4aa404073b81ef001ebc9d1a6eb3d7f58`
- Wiki handoff：`data/processed/huiji/activation/transactions/candidate-f-generation-1-20260722d/wiki_import_handoff.v1.json`
- Wiki handoff SHA-256：`884e6ae0ef10911564a84ec3c3ec5b3f57939fc47475ab68599d04ca14d4e90a`

### 11.3 最终验收

- activation receipt：`status=passed`，P0 matrix `48/48`。
- journal：terminal state `committed`；同 ID committed recover 返回 `already_committed`，canonical pointer、settings、receipt、handoff 和 backend PID 均未变化。
- runtime：`status=ok`、`vectorstore_loaded=true`、`provenance_status=pass`、`doc_count=14630`。
- voice evaluator：动态抽样 9 个实体、59 页，失败数 0；媒体身份按 `binding_id -> asset_id -> media_id` 解析。
- protected compare：`passed=true`，未知变化为空；legacy collection `16010` 行和 Candidate collection `14630` 行均保持固定指纹。
- active 状态全量回归：`1333 passed, 2 skipped, 3 warnings`；`pip check` 无损坏依赖。
- post-activation 回归发现 3 个测试仍硬编码 legacy collection；已改为验证当前 settings 和 active snapshot 一致性，未放宽运行时 fail-closed 门禁。
- `audit_credential_secrecy.py` 仅接受新版 crawler `credential.json`；当前该文件不存在，现用受保护 `config.dat` 也不属于其 schema，因此该工具在本次执行中不适用。activation evidence 字段扫描仅发现空的 `api_key`/`password` 配置项，未发现密钥值落盘。
- Wiki health 仍为 legacy/dev：`ready=true`、`pageCount=7456`、`mediaLinkCount=17527`；RAG 未执行 Wiki importer、DDL 或 DML。

### 11.4 交付状态

Candidate F generation 1 activation 已完成。Wiki 线路现在可以只消费 11.2 中的 receipt 与 handoff 路径及 SHA-256，进入其独立的事务化 v3 import、双表切换、页面验收和 rollback gate；RAG 不代替 Wiki 执行正式导入。
