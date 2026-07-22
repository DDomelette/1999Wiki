# Huiji RAG Generation-0 Bootstrap 实施计划

日期：2026-07-22  
状态：待用户审阅  
执行模式：在当前脏工作树单线程执行，不使用子代理，不执行 git 清理、提交或回滚。Plan 是本轮强制验收门槛；任一 P0 未闭合均不得签发 passing bootstrap receipt 或 activation proposal。

依据 Spec：`docs/superpowers/specs/2026-07-22-huiji-rag-generation-zero-bootstrap-design.md`  
Spec SHA-256：`fabe75fc410149aa43baed855a97a5896c67b045a918e74e40e9f3a6f94c13e1`

## 1. 目标与执行边界

本轮必须闭合以下 44 条 P0：

- `BOOT-AUTH-P0-01..06`
- `BOOT-MANIFEST-P0-01..06`
- `BOOT-POINTER-P0-01..08`
- `BOOT-APPLY-P0-01..10`
- `BOOT-VERIFY-P0-01..07`
- `BOOT-PROPOSAL-P0-01..07`

本轮唯一允许的 authority 变化是 create-new：

```text
不存在 data/processed/huiji/active_build.v1.json
    -> generation=0 / build=dev / collection=text_child_bge_m3_v3
```

该变化只能改变 authority 的表达方式，不能改变有效 RAG tuple。完成后必须生成：

1. generation-0 bootstrap intent、collection manifest、deployment inventory 和 hash-chain journal；
2. canonical generation-0 pointer；
3. pre/post effective tuple 与 protected-state 证据；
4. 44/44 P0 passing bootstrap receipt；
5. 完整 Candidate F previous-state rollback tuple；
6. `allowed_for_activation_review=true` 且无 blocker 的新 proposal；
7. `next_gate=separate_user_approved_candidate_f_activation`，不执行 Candidate F 切换。

本轮禁止：

- 把 bootstrap writer 放入 `HuijiCorpusBuilder` 或 `EvbBuilder`；
- 激活 Candidate F、修改 active Milvus collection、rename/alias/drop collection；
- 修改 `config/settings.yaml` 或 `config/provenance/huiji-dev.v1.json`；
- 修改五份 legacy runtime artifact；
- 对 MySQL、MinIO、Wiki importer/API 数据执行写入；
- 上传、删除、迁移或清理 MinIO 对象；
- 重建或重新向量化 Milvus；
- 重启 RAG、Wiki、Milvus、MinIO、MySQL 服务；
- 执行 Wiki v3 正式导入或生产 restore；
- 创建错误历史路径 `data/processed/huiji/activation/active_build.v1.json`；
- 修改 `D:\1999Wiki_Backup`。

## 2. 冻结输入与具体输出

执行时必须重新计算所有 hash 和运行态 fingerprint。下表值不一致时停止，不自动接受新状态。

| 输入 | 路径或 authority | 冻结值 |
|---|---|---|
| 本 Spec | `docs/superpowers/specs/2026-07-22-huiji-rag-generation-zero-bootstrap-design.md` | SHA-256 `fabe75fc410149aa43baed855a97a5896c67b045a918e74e40e9f3a6f94c13e1` |
| Canonical pointer | `data/processed/huiji/active_build.v1.json` | 执行前不存在 |
| Legacy build manifest | `data/processed/huiji/dev/build_manifest.json` | SHA-256 `ad886077e2aff90350480c9925686693121af9c643796131c361fde6efeed231` |
| Installed provenance | `config/provenance/huiji-dev.v1.json` | SHA-256 `dafd3a7b309fc96fe784945d4b5f143f3e8aec2e93a6856151e3a52fb4e8e6a4` |
| Active Milvus | `reverse1999_rag/text_child_bge_m3_v3` | rows `16010`; schema SHA `db9e13b98d7a1cf4116ba6647a16eb0e7daff0a77c558f66c9db2597038a6bc4`; primary IDs SHA `35767849daf684742b66453a953837c85f93a9e8744d9c10516de7e3651ccb35`; business fields SHA `89dd551acb78f7bd3b55f7b3f284c85e8253d6f02dfb2bd8b4671d35e1c5208b` |
| Embedding | runtime config | model `BAAI/bge-m3`; config SHA `17787be97e63ea53e3298748adf546ebc17d5456669481349eb8bb088b336099` |
| Candidate F | `data/processed/huiji/crawler-v3-20260721t051246z/build_manifest.json` | SHA-256 `293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f` |
| Shadow evidence | `eval/huiji_provenance/20260721T060016Z-shadow-candidate-f-preflight/shadow-build.v1.json` | SHA-256 `0eb85ed2c60b4a500fef92ddad11e0fbbb190c32057e795a9f5a8dd4e1974cfa` |
| Full-chain evidence | `eval/huiji_candidate_full_chain/20260721T070710Z-candidate-f-shadow/full-chain.v1.json` | SHA-256 `8d95408baea543de9788a0b618e718fc202adc3cec8ecc849eb315c34f45b12c` |
| Wiki compatibility | `eval/huiji_wiki_v3_compatibility/20260720T162923Z/wiki_media_v3_compatibility_receipt.v1.json` | SHA-256 `b0c82cbaa77303819ee93f600c2f4518152984580bb36d636e0d5063a67ec56d` |
| Wiki rollback | `eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/wiki_pre_import_rollback_receipt.v1.json` | SHA-256 `e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6` |
| Trusted protected compare | `eval/huiji_activation/20260722T000000Z-candidate-f-review/protected-state-current.v1.json` | SHA-256 `b78c8ca80f901f5eb1182592b91fedcbd92db5416d3865424811efa134301c17`; `status=pass`; `changes=[]` |
| Diagnostic proposal | `data/processed/huiji/activation/proposals/candidate-f-review-20260722b/activation_proposal.v1.json` | SHA-256 `08ef70fcb75010fd7e9b0b77c3f8e7ae14f307b6aad3bf724ecd647b48b5728c`; blocker 仅 `active_pointer_not_bootstrapped` |

具体 create-new ID：

```text
bootstrap_id=legacy-dev-generation-0-20260722a
bootstrap_root=data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a
bootstrap_lock=data/processed/huiji/.generation-zero-bootstrap.lock
proposal_id=candidate-f-review-20260722c
proposal_root=data/processed/huiji/activation/proposals/candidate-f-review-20260722c
```

这两个目录和 canonical pointer 在 Plan 编写时均不存在。执行时若任一已存在，停止并诊断，不自动更换 ID。

本轮新增 evidence schema 固定为：

| 文件 | Schema |
|---|---|
| `bootstrap_intent.v1.json` | `huiji.generation-zero-bootstrap-intent/v1` |
| `collection_manifest.v1.json` | `evb.collection-manifest/v1` |
| `deployment_inventory.v1.json` | `huiji.generation-zero-deployment-inventory/v1` |
| `bootstrap_journal.v1.jsonl` 每个 event | `huiji.generation-zero-bootstrap-journal-event/v1` |
| effective tuple payload | `huiji.effective-runtime-tuple/v1` |
| `protected_state.before.v1.json` | `rag_eval.protected_snapshot/v2` |
| `protected_state.after.v1.json` | `huiji.protected_compare/v1`；必须包含 `status`、`changes` 和完整 `after` snapshot |
| `bootstrap_receipt.v1.json` | `huiji.generation-zero-bootstrap-receipt/v1`，`status=passed` |
| `bootstrap_failure.v1.json` | `huiji.generation-zero-bootstrap-failure/v1`，不能通过 passing validator |

所有 JSON 使用 UTF-8、LF、排序键和尾随单换行；所有 JSONL event 单行 canonical 且以 LF 结尾。除 journal 在 operation 未终态前只能 append 外，其余文件全部 create-new。

## 3. 计划修改位置

| 位置 | 用途 |
|---|---|
| `src/huiji_rag/active_pointer.py` | strict JSON loader、full pointer schema、generation-0 约束、canonical path/manifest 定位与纯 validator |
| `src/huiji_rag/generation_zero.py` | authority inspect、legacy collection manifest、effective tuple、deployment inventory、advisory lock、journal、CAS、recover、receipt |
| `src/huiji_rag/runtime_artifacts.py` | generation-0 pointer/manifest/provenance 严格解析；pointer 存在后 fail closed |
| `src/huiji_rag/build/contracts.py` | 从 shared pointer contract 重导出 schema 常量，避免第二套定义 |
| `src/huiji_rag/build/activation_evidence.py` | 严格消费 bootstrap receipt，生成完整 rollback tuple 和固定 next gate |
| `src/huiji_wiki/snapshot.py` | 复用 shared pointer validator，保持 legacy/v2/v3 snapshot 能力 |
| `src/huiji_wiki/mysql_rollback.py` | 纠正未来保护面使用的 canonical pointer 常量；不重写已签发 Receipt |
| `scripts/bootstrap_huiji_generation_zero.py` | `inspect`、`apply`、`recover` 三个独立命令入口 |
| `scripts/build_huiji_corpus.py` | proposal 增加 bootstrap receipt 与完整 rollback tuple 参数/校验 |
| `tests/test_huiji_active_pointer.py` | strict schema、duplicate key、路径、alias、generation/capability 测试 |
| `tests/test_huiji_generation_zero.py` | manifest、tuple、authority、lock、journal、CAS、recover、补偿与 mutation spy 测试 |
| `tests/test_huiji_generation_zero_cli.py` | 三个 CLI 的参数、确认文本、退出码、create-new 和密钥泄漏测试 |
| `tests/test_huiji_runtime_artifacts.py` | generation-0 resolution、legacy 等价、fail-closed 与 v2/v3 回归 |
| `tests/test_huiji_wiki_snapshot.py` | RAG/Wiki 共用 full pointer contract 与 legacy/v2/v3 回归 |
| `tests/test_huiji_activation_proposal.py` | bootstrap Receipt、Wiki validator、完整 rollback tuple 和 blocker 测试 |
| `tests/test_huiji_corpus_cli.py` | proposal CLI 新参数、hash pin 和零 active mutation 测试 |

不修改 Retriever、QueryPlan、media registry、Wiki importer/repository/API/React、Builder projection 或 embedding/index writer。

## 4. 强制检查点

| 检查点 | Specs | 自动化门槛 | 真实数据门槛 | 失败表现 |
|---|---|---|---|---|
| C1 Authority 冻结 | `BOOT-AUTH-P0-01..06` | ID/path/symlink、Receipt、配置、provenance、protected baseline 测试 | frozen hash 全部复算；pointer 缺失；正式 Wiki validator 通过；fresh protected compare 无未知变化 | 错误路径、旧 Receipt、泛化 status 检查、unknown drift 或任一 authority 不一致即停止 |
| C2 Legacy manifest | `BOOT-MANIFEST-P0-01..06` | 五 artifact、BM25、Milvus、embedding、canonical bytes 与 tamper 测试 | manifest 与 installed provenance、磁盘字节、实时 Milvus 三方一致 | 只信任旧计数、缺 hash/size、密钥泄漏或 collection identity 不一致即失败 |
| C3 Pointer contract | `BOOT-POINTER-P0-01..08` | 严格字段、重复键、alias、类型、path、v2/v3 reader 回归 | pointer 解析为 generation 0；新 snapshot 与旧 tuple 相等；无 fallback | `collection_name` alias、额外字段、错误路径、无效 pointer 回退 `dev` 或 reader 分叉即失败 |
| C4 Atomic apply | `BOOT-APPLY-P0-01..10` | advisory lock、hash-chain journal、hard-link CAS、crash/recover/compensate fault injection | 仅 canonical pointer 与 bootstrap evidence 新增；journal 终态 `committed` | overwrite/replace fallback、外部 lock 删除、未知 pointer 删除、非同 operation 恢复或未终态继续 proposal 即失败 |
| C5 等价与保护面 | `BOOT-VERIFY-P0-01..07` | effective tuple、mutation spies、protected compare、receipt/failure 互斥测试 | pre/post tuple 相等；MySQL/两个 MinIO scope 零差异；active Milvus 和五 artifacts 不变 | 业务存储任一差异、tuple 不等价、失败 evidence 冒充 passing 或无 sidecar 即失败 |
| C6 Proposal/rollback | `BOOT-PROPOSAL-P0-01..07` | strict bootstrap/Wiki receipt、完整 previous tuple、缺引用 blocker 测试 | 新 proposal 无 blocker；rollback tuple 引用闭合；Candidate F 仍未 active | 残缺 tuple、`20260721a` 被接受、generic Receipt 检查或 next gate 可直接切换即失败 |
| C7 回归与交付 | 全部 P0 | 新增测试、RAG/Wiki 回归、全量 pytest、44/44 matrix | runtime verifier、只读 retrieval、Wiki health 通过；无服务重启和业务写入 | 任一测试失败、P0 少于 44、健康异常或越界 mutation 即不得交付 |

## 5. TDD 实施步骤

每个实现步骤固定遵循：先写失败测试并确认失败原因正确，再做最小实现，随后运行目标测试并记录检查点。禁止先改真实 pointer 再补实现或测试。

### Step 0：执行前只读基线

- 对应 Specs：全部 P0 的前置条件。
- 只读检查：
  - 复算 Spec、legacy manifest、installed provenance、Candidate F、Wiki Receipt 和 trusted protected compare hash；
  - 确认 canonical pointer、bootstrap root、proposal root 均不存在；
  - 确认错误历史 pointer 路径不存在且代码不会将其作为 RAG authority；
  - 运行当前 installed runtime verifier；
  - 调用 `validate_passing_receipt()` 和 restore CLI dry-run；
  - 读取 active/shadow Milvus collection identity、容器状态和 Wiki health；
  - 记录当前脏工作树，仅防止覆盖用户改动，不执行 git 操作。
- 命令：

```powershell
$Spec = 'docs/superpowers/specs/2026-07-22-huiji-rag-generation-zero-bootstrap-design.md'
$Pointer = 'data/processed/huiji/active_build.v1.json'
$BootstrapRoot = 'data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a'
$ProposalRoot = 'data/processed/huiji/activation/proposals/candidate-f-review-20260722c'
$WikiReceipt = 'eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/wiki_pre_import_rollback_receipt.v1.json'
$PreRuntime = 'eval/huiji_generation_zero/legacy-dev-generation-0-20260722a-pre-runtime'
$PostRuntime = 'eval/huiji_generation_zero/legacy-dev-generation-0-20260722a-post-runtime'
$ActiveSample = 'eval/huiji_generation_zero/legacy-dev-generation-0-20260722a-active-sample.v1.json'

if ((Get-FileHash -Algorithm SHA256 $Spec).Hash.ToLower() -ne 'fabe75fc410149aa43baed855a97a5896c67b045a918e74e40e9f3a6f94c13e1') { throw 'Spec hash drift' }
if (Test-Path -LiteralPath $Pointer) { throw 'Canonical pointer already exists' }
if (Test-Path -LiteralPath $BootstrapRoot) { throw 'Bootstrap root already exists' }
if (Test-Path -LiteralPath $ProposalRoot) { throw 'Proposal root already exists' }
if (Test-Path -LiteralPath $PreRuntime) { throw 'Pre-runtime evidence already exists' }
if (Test-Path -LiteralPath $PostRuntime) { throw 'Post-runtime evidence already exists' }
if (Test-Path -LiteralPath $ActiveSample) { throw 'Active-sample evidence already exists' }

python scripts/verify_huiji_runtime.py --run-dir $PreRuntime
python scripts/restore_wiki_mysql_from_receipt.py --receipt $WikiReceipt --expected-receipt-sha256 e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6
```

- 门槛：C1 前置通过；任何 drift 停止，不改白名单。

### Step 1：TDD 冻结 shared pointer contract

- 对应 Specs：`BOOT-POINTER-P0-01..06`。
- 先写失败测试：
  - 缺字段、额外字段、重复 JSON key、非小写 SHA、布尔 generation/epoch、非 `Z` 时间均拒绝；
  - `collection_name`、camelCase、任意 manifest/path override 和未知 capability 均拒绝；
  - generation 0 的 build、previous build、collection、schema、embedding 与 artifact capability 任一不符均拒绝；
  - project-root 逃逸、symlink/junction 和错误历史 pointer 路径均拒绝；
  - RAG 与 Wiki 对同一 fixture 必须给出同一通过/失败结论。
- 最小实现：
  - 新建 stdlib-only `src/huiji_rag/active_pointer.py`；
  - 提供 strict bytes loader、pure payload validator、canonical pointer resolver 和 generation-0 evidence resolver；
  - `build/contracts.py` 只重导出 schema 常量，不保留第二份字段定义；
  - `runtime_artifacts.py` 与 `huiji_wiki/snapshot.py` 调用同一个 validator；
  - 修正 `mysql_rollback.py` 未来 protected-state 常量，但不修改 `20260721b` Receipt 字节。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_active_pointer.py tests/test_huiji_runtime_artifacts.py tests/test_huiji_wiki_snapshot.py
```

- 门槛：C3 schema/reader 部分通过。

### Step 2：TDD 实现 legacy collection manifest 与 effective tuple

- 对应 Specs：`BOOT-MANIFEST-P0-01..06`、`BOOT-VERIFY-P0-01..02`、`BOOT-VERIFY-P0-04..05`。
- 先写失败测试：
  - 五份 artifact 的 path/hash/size 任一改变即失败；
  - old build manifest 计数正确但 artifact bytes 错误仍失败；
  - provenance、实时 Milvus 与 manifest 的 database/collection/schema/rows/primary IDs/business fields 任一不一致即失败；
  - embedding model/config drift、secret-like 字段和 non-canonical JSON 均拒绝；
  - pre/post tuple 只改变 `source_mode` 时相等，改变任一业务身份时不等；
  - generation-0 runtime 不能只做“文件存在”检查。
- 最小实现：
  - 在 `generation_zero.py` 中复用 provenance fingerprint API，不重复实现 Milvus/JSONL/BM25 哈希算法；
  - schema 固定为 `evb.collection-manifest/v1` 和 `evb.media-asset/v1_legacy`；
  - tuple canonical payload 只包含 Spec 第 8.1 节字段；
  - runtime generation-0 分支验证 pointer、manifest、provenance 与 artifact pins；健康验证另外复核实时 Milvus。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_generation_zero.py -k "manifest or tuple or milvus or embedding or artifact"
python -m pytest -q tests/test_huiji_runtime_artifacts.py
```

- 门槛：C2、C5 tuple 部分通过。

### Step 3：TDD 实现 inspect authority 与输入冻结

- 对应 Specs：`BOOT-AUTH-P0-01..06`、`BOOT-APPLY-P0-01..02`、`BOOT-APPLY-P0-05`。
- CLI 契约：

```text
python scripts/bootstrap_huiji_generation_zero.py inspect
  --bootstrap-id legacy-dev-generation-0-20260722a
  --trusted-protected-compare eval/huiji_activation/20260722T000000Z-candidate-f-review/protected-state-current.v1.json
  --expected-trusted-protected-compare-sha256 b78c8ca80f901f5eb1182592b91fedcbd92db5416d3865424811efa134301c17
  --wiki-rollback-receipt eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/wiki_pre_import_rollback_receipt.v1.json
  --expected-wiki-rollback-receipt-sha256 e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6
```

- 先写失败测试：
  - 非法 ID、已有 root/pointer、错误 cwd/root、path escape、symlink/junction、未终态 journal 均拒绝；
  - configured build/collection 双配置不一致、installed verifier 失败、frozen hash drift 均拒绝；
  - generic `status=pass`、test-only Receipt、`20260721a`、损坏 sidecar/dump/restore pin 均拒绝；
  - trusted compare 非 pass、`changes` 非空、after 缺 scope 或 fresh state 出现 unknown drift 均拒绝；
  - mutation spies 证明 inspect 不创建 pointer、不写业务 store、不修改配置/provenance/artifacts。
- 最小实现：
  - inspect 先在内存完成全部 authority 与 fresh protected-state 检查，再 create-new bootstrap root；
  - trusted compare 只以 hash-pinned `after` 作为比较基线，不继承宽松白名单；
  - 输出 canonical intent、collection manifest、deployment inventory、protected before 及 sidecars；
  - 输出摘要仅包含相对路径、hash、status 和 blocker，不输出凭据或环境变量值。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_generation_zero.py -k "authority or inspect or receipt or protected or path"
python -m pytest -q tests/test_huiji_generation_zero_cli.py -k "inspect or secret or create_new"
```

- 门槛：C1、C2 inspect 部分通过。

### Step 4：TDD 实现 advisory lock、journal、create-new CAS 与 recover

- 对应 Specs：`BOOT-APPLY-P0-03..04`、`BOOT-APPLY-P0-07..10`。
- 先写失败测试：
  - 同进程/跨进程 lock 竞争被阻断，遗留空 lock 文件不会被误判为持锁；
  - journal sequence 跳号、previous hash 错误、非法状态迁移、重复 key 或 intent/pointer hash 改变均拒绝；
  - target 已存在、hard-link 不支持、不同卷、temp 未 fsync 和 CAS race 均不退化为 overwrite/replace；
  - 在 `prepared`、`pointer_written`、`verified` 后模拟 crash，recover 只续做同一 operation；
  - pointer SHA 不同、journal 与 pointer 组合未知、存在 committed event 时补偿均进入 conflict；
  - post-write 失败仅在精确补偿条件下移除本次 pointer；外部 pointer 永不删除。
- 最小实现：
  - 固定 lock 文件使用 Windows OS advisory lock，进程退出自动释放；
  - journal 每行 canonical JSON，append 后 flush/fsync，终态生成文件 sidecar；
  - pointer bytes 在 `prepared` 前冻结，journal 固定 expected SHA；
  - 同目录 temp 完整写入并 fsync，再以 hard-link create-new CAS 建立 canonical pointer；
  - `recover` 重新取得 lock、严格回放 journal 并按 Spec 状态机继续或 conflict；
  - `finally` 只清理本进程 temp、释放 lock，保留 journal/evidence。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_generation_zero.py -k "lock or journal or cas or recover or compensate or conflict"
python -m pytest -q tests/test_huiji_generation_zero_cli.py -k "apply or recover or confirmation or exit_code"
```

- 门槛：C4 通过。

### Step 5：TDD 实现 post-write 验证与 passing Receipt

- 对应 Specs：`BOOT-POINTER-P0-07..08`、`BOOT-APPLY-P0-06`、`BOOT-VERIFY-P0-01..07`。
- 先写失败测试：
  - pointer 存在后无效时 RAG/Wiki fail closed，不能回退 configured `dev`；
  - pre/post effective tuple 任一差异阻断 committed；
  - active Milvus、MySQL、任一 MinIO scope、settings、provenance、legacy artifacts 出现差异即失败；
  - project artifacts 只允许 intent 中固定的 bootstrap evidence 与 canonical pointer；
  - runtime verifier/retrieval smoke 失败不能生成 passing Receipt；
  - receipt/failure 同时存在、缺 sidecar、journal 未 committed、内部/文件 hash 不符均拒绝；
  - 已正确验证 pointer 但 Receipt 写入中断时，只允许 recover 完成 evidence，不误删 pointer。
- 最小实现：
  - apply 创建 pointer 后通过新 reader 重新解析，不复用 pre-bootstrap snapshot 对象；
  - 运行 installed verifier、实时 Milvus fingerprint 和代表性只读 retrieval；
  - fresh protected compare 对 MySQL/两个 MinIO scope 要求零变化；
  - `protected_state.after.v1.json` 写为 `huiji.protected_compare/v1` wrapper，`status=pass`、`changes=[]`，完整 fresh snapshot 位于 `after`；不得把裸 snapshot 冒充 compare evidence；
  - Wiki health 只读检查，允许旧 import snapshot 变 stale，不触发 import；
  - passing Receipt 包含 44 条 P0 matrix、journal terminal hash、补偿状态和全部 pin；
  - `committed` 是 proposal builder 接受 bootstrap 的必要条件。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_generation_zero.py -k "post or receipt or fail_closed or protected or smoke or mutation"
python -m pytest -q tests/test_huiji_runtime_artifacts.py tests/test_huiji_wiki_snapshot.py
```

- 门槛：C3、C5 通过。

### Step 6：TDD 扩展 proposal 与完整 rollback tuple

- 对应 Specs：`BOOT-PROPOSAL-P0-01..07`。
- 先写失败测试：
  - bootstrap receipt 缺失、非 committed、文件/内部 hash 错、pointer/tuple/protected ref 不一致均生成确定性 blocker；
  - Wiki Receipt 必须通过 `validate_passing_receipt()`，`20260721a`、test-only、generic status 均拒绝；
  - previous pointer payload/path/hash、legacy manifest、collection manifest、provenance、settings、deployment inventory、Milvus、Wiki restore、两个 MinIO refs 缺任一项时不生成 rollback tuple；
  - protected evidence 不是 bootstrap 后 fresh evidence时阻断；
  - 成功 proposal 固定 `next_gate=separate_user_approved_candidate_f_activation` 且不调用任何 active writer。
- 最小实现：
  - `build_activation_review()` 增加 strict bootstrap Receipt 输入；
  - rollback tuple 保存 generation-0 pointer 完整 payload 与 hash-pinned references，不复制 dump 或凭据；
  - proposal CLI 增加 `--bootstrap-receipt` 和对应 expected SHA；
  - 旧 `candidate-f-review-20260722b` 保留诊断，不覆盖。
- 测试命令：

```powershell
python -m pytest -q tests/test_huiji_activation_proposal.py tests/test_huiji_corpus_cli.py
```

- 门槛：C6 通过。

### Step 7：故障注入、回归与静态边界检查

- 对应 Specs：全部 P0。
- 执行：
  - 对 writer 注入每个 journal 边界的 crash、I/O error、CAS race 和 validation drift；
  - 对 Milvus、MinIO、MySQL、settings、provenance、artifact writer 使用 mutation spies；
  - 扫描 bootstrap/proposal 模块，禁止 `drop/delete/upload/import/restore/restart` 业务调用；
  - 运行新增测试、RAG/Wiki 相关回归和全量测试；
  - 编译所有修改的 Python 文件。
- 命令：

```powershell
python -m pytest -q tests/test_huiji_active_pointer.py tests/test_huiji_generation_zero.py tests/test_huiji_generation_zero_cli.py tests/test_huiji_runtime_artifacts.py tests/test_huiji_activation_proposal.py tests/test_huiji_corpus_cli.py tests/test_huiji_wiki_snapshot.py
python -m pytest -q tests/test_huiji_wiki_mysql_rollback.py tests/test_huiji_wiki_mysql_rollback_scripts.py tests/test_huiji_wiki_media_v3.py tests/test_huiji_wiki_importer.py tests/test_huiji_wiki_api.py
python -m pytest -q
python -m compileall -q src/huiji_rag src/huiji_wiki scripts/bootstrap_huiji_generation_zero.py scripts/build_huiji_corpus.py
rg -n "activation/active_build\.v1\.json|collection_name.*pointer|os\.replace|Path\.replace|unlink|drop_collection|delete|upload|restore" src/huiji_rag/active_pointer.py src/huiji_rag/generation_zero.py scripts/bootstrap_huiji_generation_zero.py
```

- 门槛：C1-C7 自动化部分全部通过；`rg` 命中必须逐条说明，不能仅凭命中数宣称失败或通过。

## 6. 真实 Generation-0 执行

本节只在 Step 0-7 全部通过且用户批准本 Plan 后执行。Plan 批准构成对本节 hash-pinned generation-0 apply 的显式授权；CLI 仍必须要求精确确认文本。正常门禁通过时不增加额外人工暂停；只有第 8 节阻断条件触发时停止。

### Step 8：运行只读 inspect 并冻结 intent

```powershell
python scripts/bootstrap_huiji_generation_zero.py inspect `
  --bootstrap-id legacy-dev-generation-0-20260722a `
  --trusted-protected-compare eval/huiji_activation/20260722T000000Z-candidate-f-review/protected-state-current.v1.json `
  --expected-trusted-protected-compare-sha256 b78c8ca80f901f5eb1182592b91fedcbd92db5416d3865424811efa134301c17 `
  --wiki-rollback-receipt eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/wiki_pre_import_rollback_receipt.v1.json `
  --expected-wiki-rollback-receipt-sha256 e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6
```

立即机械复核：

```powershell
$BootstrapRoot = 'data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a'
$Intent = Join-Path $BootstrapRoot 'bootstrap_intent.v1.json'
$IntentSha = ((Get-Content -Raw -Encoding ASCII "$Intent.sha256") -split '\s+')[0]
$Manifest = Join-Path $BootstrapRoot 'collection_manifest.v1.json'
$Inventory = Join-Path $BootstrapRoot 'deployment_inventory.v1.json'

if ((Get-FileHash -Algorithm SHA256 $Intent).Hash.ToLower() -ne $IntentSha) { throw 'Intent sidecar mismatch' }
if (Test-Path -LiteralPath 'data/processed/huiji/active_build.v1.json') { throw 'Inspect wrote pointer' }
if ((Get-Content -Raw -Encoding UTF8 $Manifest | ConvertFrom-Json).build_version -ne 'dev') { throw 'Manifest build mismatch' }
if ((Get-Content -Raw -Encoding UTF8 $Inventory | ConvertFrom-Json).effective_runtime_tuple_sha256 -eq '') { throw 'Missing effective tuple' }
```

验收：

- intent、manifest、inventory、protected before 及 sidecars 均 create-new；
- Wiki Receipt 严格验证通过；
- fresh authority 无 drift；
- pointer 仍不存在；
- stdout/stderr 无凭据。

### Step 9：执行 apply 或中断恢复

正常 apply：

```powershell
$BootstrapRoot = 'data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a'
$Intent = Join-Path $BootstrapRoot 'bootstrap_intent.v1.json'
$IntentSha = ((Get-Content -Raw -Encoding ASCII "$Intent.sha256") -split '\s+')[0]

python scripts/bootstrap_huiji_generation_zero.py apply `
  --intent $Intent `
  --expected-intent-sha256 $IntentSha `
  --expected-pointer-absence `
  --confirmation 'BOOTSTRAP HUIJI LEGACY DEV GENERATION 0'
```

只有进程中断且 journal 未终态时使用 recover；不得删除目录、pointer 或 journal后重跑 inspect：

```powershell
python scripts/bootstrap_huiji_generation_zero.py recover `
  --bootstrap-id legacy-dev-generation-0-20260722a `
  --expected-intent-sha256 $IntentSha
```

post-apply 验收：

```powershell
$Pointer = 'data/processed/huiji/active_build.v1.json'
$Receipt = Join-Path $BootstrapRoot 'bootstrap_receipt.v1.json'
$PointerJson = Get-Content -Raw -Encoding UTF8 $Pointer | ConvertFrom-Json
$ReceiptJson = Get-Content -Raw -Encoding UTF8 $Receipt | ConvertFrom-Json

if ($PointerJson.generation -ne 0) { throw 'Pointer generation mismatch' }
if ($PointerJson.build_version -ne 'dev') { throw 'Pointer build mismatch' }
if ($PointerJson.milvus_collection_name -ne 'text_child_bge_m3_v3') { throw 'Pointer collection mismatch' }
if ($ReceiptJson.status -ne 'passed') { throw 'Bootstrap receipt not passing' }
if ($ReceiptJson.p0_matrix.expected_count -ne 44) { throw 'P0 matrix expected count mismatch' }
if ($ReceiptJson.p0_matrix.passed_count -ne 44) { throw 'P0 matrix incomplete' }

python scripts/verify_huiji_runtime.py --run-dir eval/huiji_generation_zero/legacy-dev-generation-0-20260722a-post-runtime
python scripts/verify_huiji_provenance_acceptance.py sample-active --output eval/huiji_generation_zero/legacy-dev-generation-0-20260722a-active-sample.v1.json
```

验收：

- journal 最终状态为 `committed`，journal sidecar 可复核；
- pre/post effective tuple SHA 完全相同；
- active Milvus 指纹、settings、provenance、五 artifacts 不变；
- MySQL 和两个 MinIO scope 零变化；
- Wiki health 可读且未执行 import；
- Candidate F 与 shadow 仍非 active。

### Step 10：生成新 proposal 与完整 rollback tuple

```powershell
$BootstrapReceipt = 'data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a/bootstrap_receipt.v1.json'
$BootstrapReceiptSha = (Get-FileHash -Algorithm SHA256 $BootstrapReceipt).Hash.ToLower()
$ProtectedBefore = 'data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a/protected_state.before.v1.json'
$ProtectedBeforeSha = (Get-FileHash -Algorithm SHA256 $ProtectedBefore).Hash.ToLower()
$ProtectedAfter = 'data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a/protected_state.after.v1.json'
$ProtectedAfterSha = (Get-FileHash -Algorithm SHA256 $ProtectedAfter).Hash.ToLower()

python scripts/build_huiji_corpus.py proposal `
  --proposal-id candidate-f-review-20260722c `
  --candidate-build-root data/processed/huiji/crawler-v3-20260721t051246z `
  --expected-build-manifest-sha256 293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f `
  --shadow-evidence eval/huiji_provenance/20260721T060016Z-shadow-candidate-f-preflight/shadow-build.v1.json `
  --expected-shadow-evidence-sha256 0eb85ed2c60b4a500fef92ddad11e0fbbb190c32057e795a9f5a8dd4e1974cfa `
  --full-chain-evidence eval/huiji_candidate_full_chain/20260721T070710Z-candidate-f-shadow/full-chain.v1.json `
  --expected-full-chain-evidence-sha256 8d95408baea543de9788a0b618e718fc202adc3cec8ecc849eb315c34f45b12c `
  --protected-baseline $ProtectedBefore `
  --expected-protected-baseline-sha256 $ProtectedBeforeSha `
  --protected-compare-evidence $ProtectedAfter `
  --expected-protected-compare-evidence-sha256 $ProtectedAfterSha `
  --wiki-compatibility-receipt eval/huiji_wiki_v3_compatibility/20260720T162923Z/wiki_media_v3_compatibility_receipt.v1.json `
  --expected-wiki-compatibility-receipt-sha256 b0c82cbaa77303819ee93f600c2f4518152984580bb36d636e0d5063a67ec56d `
  --wiki-rollback-receipt eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/wiki_pre_import_rollback_receipt.v1.json `
  --expected-wiki-rollback-receipt-sha256 e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6 `
  --bootstrap-receipt $BootstrapReceipt `
  --expected-bootstrap-receipt-sha256 $BootstrapReceiptSha
```

最终机械复核：

```powershell
$Proposal = 'data/processed/huiji/activation/proposals/candidate-f-review-20260722c/activation_proposal.v1.json'
$Rollback = 'data/processed/huiji/activation/proposals/candidate-f-review-20260722c/rollback_tuple.v1.json'
$ProposalJson = Get-Content -Raw -Encoding UTF8 $Proposal | ConvertFrom-Json
$RollbackJson = Get-Content -Raw -Encoding UTF8 $Rollback | ConvertFrom-Json

if (-not $ProposalJson.allowed_for_activation_review) { throw 'Proposal remains blocked' }
if ($ProposalJson.blockers.Count -ne 0) { throw 'Proposal has blockers' }
if (-not $ProposalJson.rollback_tuple_created) { throw 'Rollback tuple missing' }
if ($ProposalJson.next_gate -ne 'separate_user_approved_candidate_f_activation') { throw 'Unexpected next gate' }
if ($RollbackJson.previous_pointer.payload.generation -ne 0) { throw 'Rollback pointer is not generation 0' }
if ((Get-Content -Raw -Encoding UTF8 'data/processed/huiji/active_build.v1.json' | ConvertFrom-Json).build_version -ne 'dev') { throw 'Candidate F was activated unexpectedly' }
```

验收：C6、C7 通过；生成 proposal 和 rollback tuple 后立即停止，不执行 Candidate F active 切换。

## 7. 失败、恢复与停止规则

以下情况必须停止，不能通过扩大 allowlist 或修改业务数据绕过：

- frozen hash、Wiki Receipt、restore pin、配置、provenance 或 legacy artifact drift；
- active Milvus fingerprint 与冻结值不一致；
- MySQL 或任一 MinIO scope 出现变化；
- trusted/fresh protected compare 出现 unknown drift；
- canonical pointer、bootstrap root 或 proposal root 提前存在；
- OS advisory lock 无法取得；
- hard-link create-new CAS 不受支持或发生竞争；
- pointer bytes、journal 或 intent hash 组合不属于状态机；
- pre/post effective tuple 不相等；
- post-write reader、runtime verifier、retrieval smoke 或 Wiki health 失败；
- 44/44 matrix 不完整；
- proposal 或 rollback tuple 缺引用。

可以自动处理而无需额外人工审核的情况：

- 临时文件清理和本进程 advisory lock 释放；
- journal 证明同一 operation 在 `prepared`、`pointer_written` 或 `verified` 后中断时，按 `recover` 继续；
- post-write 验证失败且 pointer SHA、generation、journal 状态完全满足 Spec 时执行受限补偿；
- bootstrap 已 committed、proposal 生成失败时，保留 generation-0 pointer，修复 proposal 代码后使用同一固定 proposal ID 的前提是目录尚未创建；若目录已部分创建则停止诊断。

严禁手工删除 canonical pointer、journal、外部 lock、业务对象或 collection 来“恢复”。进入 `conflict` 时只输出 failure evidence 和受影响范围。

## 8. P0 覆盖矩阵

| Plan 步骤 | 覆盖 Specs | 主要证据 |
|---|---|---|
| Step 0、3、8 | `BOOT-AUTH-P0-01..06` | intent、strict Wiki validation、fresh protected before |
| Step 2、8 | `BOOT-MANIFEST-P0-01..06` | collection manifest、三方 fingerprint、runtime verification |
| Step 1、5、9 | `BOOT-POINTER-P0-01..08` | shared contract tests、canonical pointer、新 snapshot |
| Step 3、4、5、9 | `BOOT-APPLY-P0-01..10` | CLI authorization、lock、journal、CAS、recover/fault tests |
| Step 2、5、9 | `BOOT-VERIFY-P0-01..07` | pre/post tuple、protected after、44/44 Receipt |
| Step 6、10 | `BOOT-PROPOSAL-P0-01..07` | strict proposal、complete rollback tuple、fixed next gate |

Receipt 中必须逐条列出 44 个稳定 ID、状态、测试引用、真实 evidence 引用和失败表现。按范围汇总但缺逐项记录不合格。

## 9. P1/P2 与 Deferred

P1/P2 不进入本轮执行任务：

- 不实现现有 generation-0 pointer 的通用 `inspect-existing` 产品功能；
- 不实现 NTFS 以外未经证明的 CAS backend；
- 不生成 Candidate F active collection manifest；
- 不实现线上多实例 epoch ack、远程签名、分布式锁或 consensus；
- 不实现 activation prepare/commit/rollback controller；
- 不实现自动批准、定时切换或无人值守 Wiki restore。

## 10. 完成判定与交付

本 Plan 只有在以下条件全部成立时完成：

1. 44 条 P0 全部有实现、自动测试和真实 evidence；
2. canonical pointer 是唯一 pointer，full schema/hash 可复核，generation/build/collection 分别为 `0/dev/text_child_bge_m3_v3`；
3. pre/post effective runtime tuple 完全相等；
4. active Milvus、shadow、MySQL、两个 MinIO scope、settings、provenance、五 artifacts 和 Wiki 业务数据无未授权变化；
5. journal 为 `committed`，bootstrap receipt 为 passing，P0 matrix 为 44/44；
6. `candidate-f-review-20260722c` proposal 无 blocker并生成完整 rollback tuple；
7. Candidate F 仍未 active，Wiki v3 仍未正式导入；
8. 新增测试、RAG/Wiki 回归和全量 pytest 全部通过。

最终只交付以下值及 SHA-256，不交付凭据、dump 内容或绝对备份路径：

```text
generation_zero_pointer_path
generation_zero_pointer_file_sha256
bootstrap_receipt_path
bootstrap_receipt_file_sha256
activation_proposal_path
activation_proposal_file_sha256
rollback_tuple_path
rollback_tuple_file_sha256
```

仅完成代码、仅创建 pointer、仅通过单测或仅生成 proposal，都不能单独宣称本 Plan 完成。

## 11. 执行结果（2026-07-22）

状态：完成。Candidate F 未激活，Wiki v3 未正式导入。

- generation-0 pointer 已通过 create-new CAS 提交，tuple 为 `0/dev/text_child_bge_m3_v3`；
- bootstrap journal 终态为 `committed`，Receipt P0 matrix 为 `44/44`；
- post runtime verifier、active retrieval sample 和 Wiki health 全部通过；
- Candidate F proposal 为 `allowed_for_activation_review=true`、`blockers=[]`，next gate 为 `separate_user_approved_candidate_f_activation`；
- 最终 live protected compare 为 `changes=[]`，覆盖 9 张 MySQL 表、两个 MinIO scope 和 active Milvus；
- 全量回归为 `1322 passed, 2 skipped`。

执行期间修复了 Windows byte-range lock 解锁位置、operational lock 被 artifact inventory 自读、MinIO scope canonical key、generation-0 trusted shadow authorization 继承，以及隔离探针 collection fixture。所有修复均已纳入回归。

```text
generation_zero_pointer_path=data/processed/huiji/active_build.v1.json
generation_zero_pointer_file_sha256=95e682a6d3ae3000bc98dc3c616e7aaefea157d9c42128d15c5f764262862723
bootstrap_receipt_path=data/processed/huiji/activation/bootstrap/legacy-dev-generation-0-20260722a/bootstrap_receipt.v1.json
bootstrap_receipt_file_sha256=9abae2dafc775e4e19226e172e3f42f0106e048bdb147545a0ad0666f217e7a2
activation_proposal_path=data/processed/huiji/activation/proposals/candidate-f-review-20260722c/activation_proposal.v1.json
activation_proposal_file_sha256=fdeed5cddc1769805479d22aed49f88494d544736d6ce9ab64282a0679fb9fb8
rollback_tuple_path=data/processed/huiji/activation/proposals/candidate-f-review-20260722c/rollback_tuple.v1.json
rollback_tuple_file_sha256=07bf3f7c2c085a4f81518b3a1cb756ff9d74dae669d25978c604868b753e019b
```
