# Huiji v3 MinIO 一次性 Operation Plan 执行计划

日期：2026-07-21  
状态：已完成（一次性 Plan 已生成且未认领；实际上传仍未授权）  
批准 Spec：`docs/superpowers/specs/2026-07-21-huiji-v3-minio-operation-plan-design.md`  
批准 Spec SHA-256：`46ae3199c19a4b3ccfa0c13a767eda3eef9fa44ea2b56ba6b40e248bcdc622fe`

## 1. 目标范围

本轮只完成以下结果：

1. 让现有 strict MinIO tooling 显式读取 crawler corpus media v3 candidate；
2. 从 manifest-pinned runtime 与 binding inventory 动态派生唯一物理对象集合；
3. 重新采集 read-only MinIO inventory 并复核已批准 missing set；
4. 在 candidate root 外生成一次 create-new、hash-pinned operation plan；
5. 停在 plan 未认领、MinIO 零写入、Candidate E 仍 immutable blocked 的状态。

本轮不执行 `minio-upload`，不生成 claim marker 或 write report，不重建 Candidate F，不生成 embedding handoff，不向量化，不创建 shadow Milvus，不修改 active pointer、MySQL 或 Wiki 数据。

## 2. 冻结输入与当前批准事实

```text
Project root
  D:\PycharmProjects\nlp\LangChain\1999Search

Python
  D:\Anaconda32024\envs\langchain\python.exe

Candidate E manifest
  data/processed/huiji/crawler-v3-20260720t210135z/build_manifest.json
  fc9af6198f7a32910af258499614817bfe895a7320addc1e3f1dc98e9b971924

Fidelity baseline
  eval/huiji_corpus_fidelity/20260720T073917Z/corpus-preservation-baseline.v2.json
  8df26d9a6cd1014c82d1fdd1fa858f1b9411cb4b365101b0a12020d608db10aa

Capability evidence
  data/processed/huiji/evidence/minio-migration-20260712/minio_capability.v1.json
  c51e709311a92c8c50a8a8844927b73992f686495c8798516236d4988920901f

Approved reconciliation
  eval/huiji_corpus_builder/20260720t211224z-current-minio/analysis/candidate-e-current-minio-reconciliation.v1.json
  b0855db6463e7f4968ae4255d4e739239ca4fa153290693a7657bf52c5ec2e5a

Approved before object-state SHA-256
  f0af3adcc4b57d4ca024d92fd36fffd3e049d14e8841461317f792ef89d77128

Approved ordered missing object-key SHA-256
  614dd1a83effe7f39a77c3453593e7021113a64f0e5e5f58c38fafa19919e9f6
```

当前 evidence 中的 `3,443`、`3,436`、`7`、`15,689` 和 `2,174` 只用于真实数据验收，不进入 production adapter 常量。

## 3. P0 Requirement Map

| Spec IDs | Tasks | 实现位置 | 真实验收 |
| --- | --- | --- | --- |
| `V3ADAPTER-P0-01..06` | 1, 2, 4, 5 | `src/huiji_rag/builder.py`, `scripts/build_huiji_evb.py` | Candidate E manifest-pinned v3 join 和批准 authority 矩阵 |
| `RECONCILE-P0-01..07` | 0, 2, 4, 6 | `src/huiji_rag/builder.py`, `scripts/minio_blue_green_evidence.py` | fresh inventory 四类对账、missing-key hash 和零 mismatch |
| `PREFLIGHT-P0-01..04` | 0, 3, 4, 6 | `src/huiji_rag/minio_strict.py`, evidence script, EVB CLI | capability/reconciliation sidecar 和四个核心 evidence pin |
| `OPERATION-P0-01..06` | 3, 4, 5, 6 | `src/huiji_rag/minio_strict.py`, `scripts/build_huiji_evb.py` | global authority、create-new plan、无 marker/report/upload |

## 4. 强制验收门槛

1. **Spec gate**：批准 Spec 文件 SHA-256 必须仍为 `46ae3199c19a4b3ccfa0c13a767eda3eef9fa44ea2b56ba6b40e248bcdc622fe`。
2. **Candidate gate**：Candidate E manifest SHA-256 和 candidate filesystem inventory 在本轮前后相同；不得原地补文件。
3. **Artifact gate**：runtime 与 binding inventory 必须由 manifest artifact entries 定位并通过 schema、path、SHA、size、row-count 验证。
4. **Join gate**：两侧 `binding_id` 集合一对一相等；共享资源只合并 physical request，不丢 binding。
5. **Authority gate**：missing 对象只允许 `voice|voice|exact|audio/mpeg|.mp3` 与 `skill|skill|not_applicable|image/png|.png`。
6. **Conflict gate**：任何 hash mismatch、unknown blocker/status/type/role、identity disagreement、path escape、local-byte mismatch 均在 plan 文件创建前停止。
7. **Drift gate**：fresh MinIO object-state 和 ordered missing-key hash 必须与批准 reconciliation 相同；不得按漂移后的新集合静默生成 plan。
8. **Create-new gate**：run/evidence/operation ID 必须全新；失败目录保留，不修补、不覆盖，重试使用新 ID。
9. **Plan-only gate**：所有 planned object disposition 都是 `conditional_create`；不存在 use marker、write report、upload/readback evidence。
10. **Protected-state gate**：MinIO、active Milvus、MySQL、active artifacts/config/provenance 无漂移；`D:\1999Wiki_Backup` 零写入。

## 5. 计划修改位置

### 修改

- `src/huiji_rag/builder.py`
  - 显式 legacy v2 / corpus v3 dispatch；
  - v3 manifest resolver、binding join、physical identity consolidation 和 reconciliation summary。
- `src/huiji_rag/minio_strict.py`
  - global operation authority path；
  - operation preflight sidecar 全量哈希验证；
  - plan-only evidence cross-check。
- `scripts/build_huiji_evb.py`
  - v3 plan authority 参数与 resolution report；
  - 保留原 `offline`、legacy `minio-plan`、`minio-upload` 行为。
- `scripts/minio_blue_green_evidence.py`
  - create-new v3 operation preflight evidence preparation。
- `scripts/verify_huiji_provenance_acceptance.py`
  - protected-state compare 增加 exact create-new artifact path/SHA-256/size 允许项；不允许目录级或前缀级放行。
- `tests/test_evb_builder.py`
- `tests/test_evb_minio_strict.py`
- `tests/test_minio_blue_green_evidence.py`
- `tests/test_huiji_source_docs.py`

### 只创建运行证据

```text
eval/huiji_corpus_builder/<run_id>-v3-minio-plan/
data/processed/huiji/operations/<operation_id>/
```

### 禁止修改

- `data/processed/huiji/crawler-v3-20260720t210135z/**`
- `data/processed/huiji/active_build.v1.json`
- active artifacts、installed provenance、active Milvus collection
- Wiki MySQL 和 Wiki candidate import 状态
- MinIO 任一业务对象或 orphan object
- `D:\1999Wiki_Backup/**`

## 6. 执行任务

### Task 0：重验批准输入并冻结保护面

**对应 Specs：** `RECONCILE-P0-01`, `PREFLIGHT-P0-01..04`, `OPERATION-P0-03..04`

**执行：**

- [x] 逐个复算 Spec、Candidate E manifest、fidelity baseline、capability evidence、approved reconciliation 的 SHA-256。
- [x] 创建全新的 `$RunDir`，不得复用 `20260720t211224z-current-minio` 或任何失败 run。
- [x] 对 Candidate E 生成 create-new filesystem inventory。
- [x] 使用现有 protected-state snapshot 工具只读采集 active artifacts、Milvus、MySQL 和两个 MinIO scope；若凭据不足，先从运行中 MinIO container 的环境映射到当前 PowerShell 进程，禁止打印值。
- [x] 确认 global `$OperationRoot` 不存在，Candidate E 内也不存在新增 `operations` 目录。

**命令骨架：**

```powershell
$Project = 'D:\PycharmProjects\nlp\LangChain\1999Search'
$Python = 'D:\Anaconda32024\envs\langchain\python.exe'
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$RunDir = Join-Path $Project "eval\huiji_corpus_builder\$RunId-v3-minio-plan"
$OperationId = "crawler-v3-20260720t210135z-minio-fill-$($RunId.ToLowerInvariant())"
$OperationRoot = Join-Path $Project "data\processed\huiji\operations\$OperationId"
if ((Test-Path -LiteralPath $RunDir) -or (Test-Path -LiteralPath $OperationRoot)) {
    throw 'create-new run or operation root already exists'
}
New-Item -ItemType Directory -Path (Join-Path $RunDir 'pre') | Out-Null

& $Python scripts\minio_blue_green_evidence.py filesystem-inventory `
  --root data\processed\huiji\crawler-v3-20260720t210135z `
  --output "$RunDir\pre\candidate-files.v1.json"
if ($LASTEXITCODE -ne 0) { throw 'candidate filesystem inventory failed' }

& $Python scripts\verify_huiji_provenance_acceptance.py snapshot `
  --output "$RunDir\pre\protected-state.v1.json"
if ($LASTEXITCODE -ne 0) { throw 'protected pre-state capture failed' }
```

**自动测试：** 无代码修改前先运行现有相关测试，记录基线。

```powershell
& $Python -m pytest tests\test_evb_builder.py tests\test_evb_minio_strict.py tests\test_minio_blue_green_evidence.py -q
```

**真实验收：** 所有批准 hash 相符，pre-state evidence 及其 hash sidecar 存在，Candidate E inventory 可读且 operation root 不存在。

**失败表现：** 任一 hash、路径或 protected snapshot 不成立时停在 Task 0，不编辑代码、不创建 operation root。

### Task 1：先建立 v3 Adapter 与 Authority 失败测试

**对应 Specs：** `V3ADAPTER-P0-01..06`, `RECONCILE-P0-02..07`, `OPERATION-P0-01..05`

**修改位置：** `tests/test_evb_builder.py`, `tests/test_evb_minio_strict.py`, `tests/test_minio_blue_green_evidence.py`

- [x] 构造最小 v3 manifest fixture，runtime 不含 `local_relpath`，binding inventory 通过 `binding_id` 提供本地证据。
- [x] 覆盖同一 resource 的多个 binding、多个相同内容 local path、voice 与 skill 两类 missing、same-hash 和 orphan。
- [x] 覆盖 artifact pin/row-count/path escape、duplicate/extra/missing binding、resource/object identity 分歧。
- [x] 覆盖 runtime quarantine/fatal/unknown status、unknown blocker/type/role/MIME/suffix。
- [x] 覆盖 remote hash mismatch、本地路径逃逸/缺失/哈希变化，以及所有 local bytes 必须在写 plan 前通过。
- [x] 覆盖 legacy authority、global authority 和任意近似路径拒绝。
- [x] 覆盖 plan-only 不创建 marker/report、不调用 MinIO mutation。

**测试：** 先确认新增测试在未实现时因预期能力缺失而失败，再进入 Task 2。

**真实验收：** fixture 的 expected missing set 由 fixture 动态派生，不出现 Candidate E 数量或角色名。

**失败表现：** 测试因 fixture 自身无效而失败时先修 fixture；不得降低断言迁就现有 v2-only 行为。

### Task 2：实现 manifest-pinned v3 Adapter 与对象对账

**对应 Specs：** `V3ADAPTER-P0-01..06`, `RECONCILE-P0-02..06`

**修改位置：** `src/huiji_rag/builder.py`, `tests/test_evb_builder.py`

- [x] 保留 `strict_object_requests_from_build_manifest()` 兼容入口，内部增加显式 schema dispatch；legacy v2 路径不改变。
- [x] 新增 typed resolution result，记录唯一 candidate objects、missing requests、四类计数、authority 计数、ordered missing-key hash 和 blocker closure。
- [x] 从 manifest `artifacts` 精确定位 v3 runtime/binding inventory，验证 path、schema、SHA-256、size、row count 后才解析 JSONL。
- [x] 以 `binding_id` 建立一对一 map；校验双 ID 算法和两侧重叠 identity 字段。
- [x] 对所有 binding 做结构/containment 验证；按 object key 聚合时要求 physical identity 完全一致。
- [x] 以 fresh inventory 分类所有 candidate object 和 orphan；hash mismatch 抛出阻断错误。
- [x] 仅对 missing objects 应用 preflight-pinned authority matrix，并为每个 unique key 选择确定性 source path。

**测试：**

```powershell
& $Python -m pytest tests\test_evb_builder.py -q
```

**真实验收：** 用 Candidate E + 已批准 inventory 只读调用 resolver，动态得到 19,132 个 candidate unique resources、3,443 个 missing、零 mismatch，并通过 blocker closure；不写任何 evidence 或 candidate 文件。

**失败表现：** resolver 不返回部分结果；错误中至少包含失败类别和 object/binding identity，不吞掉异常转为空集合。

### Task 3：扩展 Operation Preflight 与 Global Authority

**对应 Specs：** `PREFLIGHT-P0-01..04`, `OPERATION-P0-01..03`

**修改位置：** `src/huiji_rag/minio_strict.py`, `scripts/minio_blue_green_evidence.py`, corresponding tests

- [x] `validate_operation_plan_authority_path()` 精确接受两种且仅两种布局：legacy `<build>/operations/plan` 与 v3 `operations/<operation_id>/plan`。
- [x] global `operation_id` 执行安全 ID 校验；resolve 后仍须位于 processed root。
- [x] 增加 v3 preflight evidence writer：byte-identical copy capability/reconciliation sidecars，记录来源 hash、四个核心 evidence hash、before object-state、approved missing-key hash 和 authority matrix。
- [x] preflight loader 验证 schema、relative containment、重复 path/hash、每个 sidecar bytes、candidate/inventory/reconciliation cross-reference。
- [x] 保持 legacy `evb.preflight-bundle/v1` capability 加载兼容，不允许 v3 strict path 绕过新增 cross-check。

**测试：**

```powershell
& $Python -m pytest tests\test_evb_minio_strict.py tests\test_minio_blue_green_evidence.py -q
```

**真实验收：** 在临时目录生成 v3 preflight，确认 capability/reconciliation copy 的 SHA 与源文件相同；不创建 plan、不连接 MinIO 写接口。

**失败表现：** 任何 stale/mismatched sidecar 或 authority path 使命令非零退出，目标 plan 不存在。

### Task 4：贯通 Plan-only CLI 与 Resolution Evidence

**对应 Specs：** `V3ADAPTER-P0-01..06`, `RECONCILE-P0-04..07`, `PREFLIGHT-P0-02..04`, `OPERATION-P0-03..06`

**修改位置：** `scripts/build_huiji_evb.py`, `src/huiji_rag/minio_strict.py`, tests

- [x] `minio-plan` 从 verified v3 preflight 读取 authority matrix 和 approved reconciliation，不接受 CLI 隐式默认放行。
- [x] 调用 v3 resolver 后要求 fresh inventory hash/object-state、candidate manifest hash、missing-key hash 和分类计数与 approved reconciliation 闭合。
- [x] 所有 missing local paths 先完成 containment/SHA-1/SHA-256/size/object-key/MIME/suffix 验证，再调用 create-new plan writer。
- [x] 固定写 create-new sibling `minio_plan_resolution.v1.json`，记录动态统计和两个 object-set hash；不得包含凭据或本地绝对文件内容。
- [x] plan 只包含 unique missing requests，所有 disposition 为 `conditional_create`；`used_by_operation_id=null`。
- [x] 保留 `minio-upload` 现有显式入口，但本轮不调用，也不让 `minio-plan` 级联调用。

**测试：**

```powershell
& $Python -m pytest tests\test_evb_builder.py tests\test_evb_minio_strict.py tests\test_minio_blue_green_evidence.py -q
```

**真实验收：** 使用 approved tuple 在全新临时 operation root 运行 plan-only dry acceptance，确认 fake/spy client 没有 mutation call，resolution 与 plan object set 完全相等。

**失败表现：** 不产生可认领 plan；若已有 diagnostic/preflight 文件则原样保留，重试必须换 operation ID。

### Task 5：执行自动化回归与静态边界检查

**对应 Specs：** 所有 P0

- [x] 运行 focused strict tooling tests。
- [x] 运行 Builder/media/artifact 相关广集，证明 v3 adapter 不改变 candidate schema 与 Builder 输出。
- [x] 运行 legacy EVB tests，证明 v2 request extraction 和 upload safety 不回归。
- [x] 静态扫描 `minio-plan` 路径，确认不存在 `conditional_create()`、`upload_sequence()`、delete、active pointer、Milvus/MySQL writer 调用。
- [x] 检查源码和文档中没有 Candidate E 数量常量、角色名验收、未完成占位标记或凭据。

**命令：**

```powershell
& $Python -m pytest `
  tests\test_evb_builder.py `
  tests\test_evb_minio_strict.py `
  tests\test_minio_blue_green_evidence.py `
  tests\test_huiji_media_v3_contract.py `
  tests\test_huiji_media_v3_builder.py `
  tests\test_huiji_media_v3_minio_gate.py `
  tests\test_huiji_corpus_builder.py `
  tests\test_huiji_corpus_artifacts.py -q
if ($LASTEXITCODE -ne 0) { throw 'P0 regression suite failed' }
```

**真实验收：** 测试完成后重新复算 Candidate E manifest hash，仍与批准值一致。

**失败表现：** 不进入 Task 6，不通过缩小测试集或修改 Candidate E 规避失败。

### Task 6：Fresh Inventory、生成一次性 Plan 并立即停止

**对应 Specs：** `RECONCILE-P0-01..07`, `PREFLIGHT-P0-01..04`, `OPERATION-P0-01..06`

**执行：**

- [x] 从运行中 `milvus-main-minio` container 读取 root credential 到当前进程专用环境变量，禁止打印值；确认 endpoint `127.0.0.1:9002`、bucket `reverse1999-assets`、prefix `reverse1999`。
- [x] 采集 fresh create-new inventory 到 `$RunDir\pre`，并与 approved inventory 做全字段零漂移比较。
- [x] 运行 v3 preflight evidence writer，在全新 `$OperationRoot\preflight` 复制 capability/reconciliation 并生成 bundle。
- [x] 运行 `build_huiji_evb.py minio-plan`，输出 fixed global plan 和 resolution report。
- [x] 复核 plan 内部 hash、file SHA、四个 evidence pins、before object-state、3,443 unique objects、voice 3,436、skill 7、ordered missing-key hash 和全部 `conditional_create`。
- [x] 明确检查 use marker、write report 和任何 upload evidence 均不存在。
- [x] 再采集 MinIO inventory 和 Candidate E filesystem inventory，与 Task 0/fresh-before 完全比较。
- [x] 执行 protected-state compare，要求 active artifacts、Milvus、MySQL 和两个 MinIO scope 无变化。
- [x] 清除当前进程临时 MinIO credential 环境变量；不删除 evidence、operation root 或 capability test object。

**命令骨架：**

```powershell
$Container = docker inspect milvus-main-minio | ConvertFrom-Json
$EnvMap = @{}
foreach ($Entry in $Container[0].Config.Env) {
    $Pair = $Entry -split '=', 2
    if ($Pair.Count -eq 2) { $EnvMap[$Pair[0]] = $Pair[1] }
}
$env:MINIO_PLAN_ROOT_USER = $EnvMap['MINIO_ROOT_USER']
$env:MINIO_PLAN_ROOT_PASSWORD = $EnvMap['MINIO_ROOT_PASSWORD']
if (-not $env:MINIO_PLAN_ROOT_USER -or -not $env:MINIO_PLAN_ROOT_PASSWORD) {
    throw 'MinIO root credentials were not available in the current process'
}
$PreviousMinioAccessKey = $env:MINIO_ACCESS_KEY
$PreviousMinioSecretKey = $env:MINIO_SECRET_KEY
$env:MINIO_ACCESS_KEY = $env:MINIO_PLAN_ROOT_USER
$env:MINIO_SECRET_KEY = $env:MINIO_PLAN_ROOT_PASSWORD

try {
    & $Python scripts\minio_blue_green_evidence.py object-inventory `
      --endpoint 127.0.0.1:9002 `
      --bucket reverse1999-assets `
      --prefix reverse1999 `
      --access-key-env MINIO_PLAN_ROOT_USER `
      --secret-key-env MINIO_PLAN_ROOT_PASSWORD `
      --output "$RunDir\pre\minio.reverse1999.fresh.v1.json"
    if ($LASTEXITCODE -ne 0) { throw 'fresh MinIO inventory failed' }

    & $Python scripts\minio_blue_green_evidence.py compare-objects `
      --expected eval\huiji_corpus_builder\20260720t211224z-current-minio\pre\minio.reverse1999.current.v1.json `
      --actual "$RunDir\pre\minio.reverse1999.fresh.v1.json" `
      --output "$RunDir\pre\minio-approved-drift-check.v1.json"
    if ($LASTEXITCODE -ne 0) { throw 'MinIO object state drifted; do not generate a plan' }

    & $Python scripts\minio_blue_green_evidence.py prepare-v3-operation-evidence `
      --build-manifest data\processed\huiji\crawler-v3-20260720t210135z\build_manifest.json `
      --expected-build-manifest-sha256 fc9af6198f7a32910af258499614817bfe895a7320addc1e3f1dc98e9b971924 `
      --baseline eval\huiji_corpus_fidelity\20260720T073917Z\corpus-preservation-baseline.v2.json `
      --expected-baseline-sha256 8df26d9a6cd1014c82d1fdd1fa858f1b9411cb4b365101b0a12020d608db10aa `
      --current-inventory "$RunDir\pre\minio.reverse1999.fresh.v1.json" `
      --capability data\processed\huiji\evidence\minio-migration-20260712\minio_capability.v1.json `
      --expected-capability-sha256 c51e709311a92c8c50a8a8844927b73992f686495c8798516236d4988920901f `
      --reconciliation eval\huiji_corpus_builder\20260720t211224z-current-minio\analysis\candidate-e-current-minio-reconciliation.v1.json `
      --expected-reconciliation-sha256 b0855db6463e7f4968ae4255d4e739239ca4fa153290693a7657bf52c5ec2e5a `
      --allow-media-authority 'voice|voice|exact|audio/mpeg|.mp3' `
      --allow-media-authority 'skill|skill|not_applicable|image/png|.png' `
      --output-root "$OperationRoot\preflight"
    if ($LASTEXITCODE -ne 0) { throw 'v3 operation preflight failed' }

    $Bundle = "$OperationRoot\preflight\preflight_bundle.v1.json"
    $BundleSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Bundle).Hash.ToLowerInvariant()
    $InventorySha = (Get-FileHash -Algorithm SHA256 -LiteralPath "$RunDir\pre\minio.reverse1999.fresh.v1.json").Hash.ToLowerInvariant()

    & $Python scripts\build_huiji_evb.py minio-plan `
      --build-manifest data\processed\huiji\crawler-v3-20260720t210135z\build_manifest.json `
      --expected-build-manifest-sha256 fc9af6198f7a32910af258499614817bfe895a7320addc1e3f1dc98e9b971924 `
      --preflight-bundle $Bundle `
      --expected-preflight-bundle-sha256 $BundleSha `
      --before-inventory "$RunDir\pre\minio.reverse1999.fresh.v1.json" `
      --expected-before-inventory-sha256 $InventorySha `
      --baseline eval\huiji_corpus_fidelity\20260720T073917Z\corpus-preservation-baseline.v2.json `
      --expected-baseline-sha256 8df26d9a6cd1014c82d1fdd1fa858f1b9411cb4b365101b0a12020d608db10aa `
      --resolution-report "$OperationRoot\minio_plan_resolution.v1.json" `
      --output "$OperationRoot\minio_operation_plan.v1.json"
    if ($LASTEXITCODE -ne 0) { throw 'operation plan generation failed; no upload is authorized' }
} finally {
    if ($null -eq $PreviousMinioAccessKey) {
        Remove-Item Env:MINIO_ACCESS_KEY -ErrorAction SilentlyContinue
    } else {
        $env:MINIO_ACCESS_KEY = $PreviousMinioAccessKey
    }
    if ($null -eq $PreviousMinioSecretKey) {
        Remove-Item Env:MINIO_SECRET_KEY -ErrorAction SilentlyContinue
    } else {
        $env:MINIO_SECRET_KEY = $PreviousMinioSecretKey
    }
    Remove-Item Env:MINIO_PLAN_ROOT_USER -ErrorAction SilentlyContinue
    Remove-Item Env:MINIO_PLAN_ROOT_PASSWORD -ErrorAction SilentlyContinue
}
```

**真实验收：** 本轮 approved tuple 必须得到当前 evidence 数字和 hash；production 代码仍动态派生。所有 protected-state compare 均为 `pass`。

**执行记录修正：** 首次广域 protected-state compare 将本任务按批准路径新建的 5 个 operation evidence 文件计为 `artifacts changed` 并正确返回 blocked。复核确认除此之外无变化后，compare 工具增加 exact path/SHA-256/size 允许项；最终重新采集当前状态并得到 `status=pass, changes=none`。初次 blocked evidence 保留，未删除或覆盖。

**失败表现：** 保留失败 evidence，确保 plan 未认领且 MinIO 未写；只有 mismatch/unknown/drift 时才停下调查，不能改用覆盖上传或删除 orphan。

### Task 7：最终机械检查和独立只读复审

**对应 Specs：** 所有 P0

- [x] 按 23 个 P0 IDs 生成 completion matrix：实现位置、测试、真实 evidence、状态、失败表现。
- [x] 复算 Spec/Plan、operation plan、resolution report、preflight bundle 和 sidecars SHA-256。
- [x] 验证 operation plan `used_by_operation_id=null`，fixed sibling marker/report 均不存在。
- [x] 验证 MinIO before/after object-state、Candidate E before/after inventory、protected state compare 全部相等。
- [x] 搜索未完成占位标记、凭据、角色特例、固定 snapshot production constants 和 active/upload 完成误报。
- [x] 将本 Plan 状态与 checklist 回填为真实结果；失败 P0 不得标为完成。
- [x] 最终报告明确给出下一边界：actual C20 conditional upload 需要用户单独明确授权。

**失败表现：** 任一证据缺失或不可复算时整体保持未完成；不因单测通过而放行。

## 7. 可选任务

本轮没有 P1 可选任务。P0 完成后也不自动扩展 media authority 或执行上传。

## 8. Deferred / Out of Scope

- 为 voice/skill 之外的媒体类型开放补齐 authority；
- 接受 MinIO object-state 漂移后的自动重算或自动批准；
- `minio-upload`、plan claim、conditional PUT、readback 和 after-upload report；
- Candidate F 重建、availability 更新和 embedding handoff；
- 向量化、shadow Milvus、full-chain acceptance 和 active activation；
- 删除或迁移 orphan remote；
- 修改 Wiki MySQL、API、前端或执行 candidate import；
- 修改、恢复或维护 `D:\1999Wiki_Backup`。

## 9. 完成后自检表

- [x] `V3ADAPTER-P0-01..06`：v2/v3 dispatch、artifact pins、binding join、local evidence、status/blocker 和 authority matrix 全部通过。
- [x] `RECONCILE-P0-01..07`：fresh inventory、四类对账、零 mismatch、exact missing set、本地字节和 drift gate 全部通过。
- [x] `PREFLIGHT-P0-01..04`：capability、sidecars、四个核心 evidence 和只读执行边界全部通过。
- [x] `OPERATION-P0-01..06`：global/legacy authority、create-new、plan-only、conditional-create-only 和后续授权边界全部通过。
- [x] 当前真实 evidence 为 3,443 unique missing objects，voice 3,436、skill 7，ordered key hash 与批准值一致。
- [x] Candidate E、MinIO、active Milvus、MySQL、active artifacts/config/provenance 无漂移。
- [x] 不存在 use marker、write report、upload evidence、Candidate F、embedding handoff 或新 shadow collection。
- [x] Plan 已生成但未使用；实际上传仍未授权。
