# 线程 D：剧情 Segment 前置门、集成与向量影子构建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task in thread D. Do not use `superpowers:subagent-driven-development`; the approved topology is exactly `D → one supervised CLI E worker`, and E may not create subagents.

**Goal:** 在线程 E 启动前冻结可观察监督、评测集、阈值和可信 baseline；在线程 E 交付后由 D 独立审查、合并、执行一次 Typed Dense 影子向量构建和完整 go/no-go 评测，同时保持生产激活为独立门禁。

**Architecture:** 本计划只负责两端。线程 C 先完成 C8b、C8c、C8d、C9；D 独立验收并把 C 合并到 `main`，运行合并后真实 fidelity，生成机器可验证的 C release receipt。只有该 receipt 通过后，D0 才能在同一 `main` 中升级 Codex 监督器、冻结 Story gold/baseline/阈值并创建 E worktree；E0–E5 由独立的线程 E Plan 串行实现。E 交付后，D 校验每个 Task 的独立提交和不可变 handoff，合并至 `main`，再由 D 独占 embedding API 与 Milvus 写权限，创建全新的 typed shadow collection、运行真实评测并生成逐项 go/no-go receipt。通过评测不等于激活。

**Tech Stack:** Conda `1999wiki` 中的 Python 3.11.15（`D:\Anaconda32024\envs\1999wiki\python.exe`，`sys.prefix=D:\Anaconda32024\envs\1999wiki`）、pytest 9.1.1、Codex CLI、PowerShell 5.1、Git worktree、JSON/JSONL、SHA-256、Milvus、现有 embedding API、现有 Huiji corpus/provenance/evaluation contracts。

## Global Constraints

- 批准的设计源头：`docs/superpowers/specs/2026-07-30-rag-story-segment-retrieval-design.md`。
- 批准基线提交：`300e4066630c6564d56157442765a4675b783590`。
- 批准 Spec SHA-256：`61bf46e1ec6f44b330913d1b1effdfd1828edf72b13ccd7ea8f60c61fa7f405d`。
- 配套线程 E Plan：`docs/superpowers/plans/2026-07-30-rag-story-segment-e-implementation.md`。
- 执行顺序严格为 `C8b → C8c → C8d → C9 → D review/merge C → D post-merge C fidelity → D0 → E0 → E1 → E2 → E3 → E4 → E5 → D merge E → D post-merge candidate rebuild → D shadow embedding → D go/no-go`。
- D 在 `D:\1999Wiki` 的 `main` 工作树执行；E 使用 `codex/rag-e-story-segment` 和 `D:\1999Wiki.worktrees\rag-e-story-segment`。
- E 固定使用 `gpt-5.6-sol`、标准速度、`workspace-write`、`fast_mode=false`、`multi_agent=false`，禁止子代理和第二个 CLI worker。
- 所有 Python 和 pytest 命令使用绝对解释器 `D:\Anaconda32024\envs\1999wiki\python.exe`；禁止裸 `python`、`py` 或裸 `pytest`。
- C release receipt 未通过前不得执行任何 D0 Task 或创建 E。E Plan 未经 D 和用户审核前不得实施。
- 线程 C 的 C8b/C8c/C8d/C9 代码、决策、测试和自包含真实 fidelity 证据必须先由 D 验收并进入固定 `main` 提交；未跟踪文件、C worktree、聊天摘要和临时诊断目录均不能成为 E 输入。
- E 只能消费 C 合并后由 `main` 重建并在 C release receipt 中固定的公共 Parent、Story Atom、source refs、migration/fidelity 和 runtime artifact；不得直接引用 C 分支、C worktree 或 ignored 诊断目录。
- E 不得调用 embedding API，不得创建或写入 Milvus collection，不得下载媒体，不得修改 active pointer，不得激活候选。
- 只有 D 可调用 embedding API 和创建 Typed Dense shadow collection；D 也不得覆盖、复用或删除 active collection。
- Reranker 全程关闭，API 调用次数必须为零；不得以开启 reranker 掩盖 Segment Dense 或融合指标不足。
- P0 质量标记只生成反事实报告，不参与真实排序、过滤或 go/no-go 分数。
- Story Atom 保留 BM25，Story Atom 不进入新 Dense 输入；非 Story Child 继续进入 Dense 输入；Story Segment 是唯一 Story Dense 单元。
- D 不修改或提交用户已有的以下工作区内容：
  - `docs/huiji-crawler/plans/README.md`
  - `docs/huiji-crawler/specs/2026-07-20-windows-crawler-p2-credential-lifecycle-design.md`
  - `docs/huiji-crawler/plans/2026-07-29-windows-crawler-p2-credential-lifecycle.md`
  - `docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md`
  - `docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md`
  - `docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md`
- 每个代码任务采用 TDD：先运行最小 RED 并确认预期失败，再做最小实现，再运行定向和相邻回归。
- 每个提交前运行 `git diff --check`、阶段测试和 `git status --short`，只暂存任务列出的文件。
- 若 E worktree 的共享 Git 元数据权限阻止提交，E 停止并报告；D 可在主监督上下文精确暂存已批准文件，但不能代替测试或扩展范围。

---

## 1. 双 Plan 职责与交接

### 1.1 D 独占职责

```text
C 发布门
├─ 验收 C8b、C8c、C8d、C9 独立提交
├─ 合并 C 到 main
├─ 运行合并后真实 fidelity 与保护状态检查
└─ 生成 C release receipt

D0
├─ 扩展监督器支持 E
├─ 冻结 gold、threshold、active baseline 与 Atom 等价 receipt
├─ 绑定 C release receipt
└─ 创建并启动受监督 E worktree

E0–E5 期间
├─ 审查阶段 diff、测试、真实快照证据
├─ 接受或退回 Task 提交
└─ 不替代 E 实现

E 交付后
├─ 合并 main
├─ 固定 Typed Dense JSONL 与模型身份
├─ 调用 embedding API
├─ 创建全新 shadow collection
├─ 运行真实 Dense/端到端评测
└─ 生成 go/no-go；不自动激活
```

### 1.2 E 独占职责

```text
E0  Story structure sidecar
E1  Segment、Context Unit 与 Atom citation spans
E2  Typed Dense 离线输入、schema、假向量适配器
E3  RequestPlan v2、Story 授权、融合与预算
E4  Runtime、公开契约、AnswerScope 与记忆
E5  离线评测、容量报告和不可变 D handoff
```

E 不得把“D 后续会重建向量”当成缺少 typed schema、builder、反序列化、fake-vector 测试或 provenance 的理由。D 不得在合并后临时补写 E 应交付的业务契约。

### 1.3 Handoff 唯一契约

E5 必须先用 `[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')` 生成 `$RunId`，再在 ignored 的新目录 `eval/story_segment/handoffs/$RunId/` 写出：

```text
story_segment_e_handoff.v1.json
story_segment_e_handoff.v1.sha256
typed_dense_units.v1.jsonl.sha256
artifact_manifest.v1.json
candidate-build-input.v1.json
candidate-build-input.v1.sha256
deployment-inventory.v1.json
offline-capacity-estimate.v1.json
offline_gate_report.v1.json
protected_state_pre.v1.json
protected_state_post.v1.json
test_receipt.v1.json
```

`story_segment_e_handoff.v1.json` 的必需字段：

```json
{
  "schema_version": "rag.story-segment-e-handoff/v1",
  "spec_commit": "40-hex",
  "spec_sha256": "64-hex",
  "d0_commit": "40-hex",
  "e_commit": "40-hex",
  "source_snapshot_identity": {},
  "artifact_paths": {},
  "artifact_sha256": {},
  "schema_sha256": {},
  "ordered_row_hashes": {},
  "row_counts": {},
  "embedding_input_identity": {},
  "candidate_build_input": {"path": "", "sha256": "64-hex"},
  "deployment_inventory": {"path": "", "sha256": "64-hex"},
  "offline_capacity_estimate": {"path": "", "sha256": "64-hex"},
  "retrieval_config_identity": {},
  "story_fusion_config_identity": {},
  "offline_gate_report_sha256": "64-hex",
  "protected_state_pre_sha256": "64-hex",
  "protected_state_post_sha256": "64-hex",
  "protected_drift_count": 0,
  "task_receipt_sha256": {},
  "reranker_call_count": 0,
  "forbidden_operation_counts": {},
  "remaining_blockers": [],
  "ready_for_d_shadow_build": false
}
```

`ready_for_d_shadow_build=true` 只能表示 E 的离线门通过，不代表生产激活获批。

---

## 2. 文件职责

### 2.1 D0 新建

| 文件 | 单一职责 |
|---|---|
| `src/rag_eval/story_segment_baseline.py` | 冻结 gold schema、baseline 等价 Atom 匹配、逐项 receipt 和 baseline 汇总 |
| `scripts/capture_story_segment_baseline.py` | 只读捕获当前 active retrieval/final-context baseline，不调用生成答案作为证据 |
| `tests/test_story_segment_baseline.py` | 等价匹配、歧义、单次 span 消费、stage 隔离和确定性测试 |
| `eval/story_segment_eval.v1.jsonl` | 提交的 Story gold 查询与 required Atom/group、授权和答案范围预期 |
| `eval/story_segment_thresholds.v1.json` | 第 26.1 节全部硬阈值及 metric direction |
| `eval/story_baseline_atom_equivalence.v1.jsonl` | 当前活动系统逐 query/result/Atom 的确定性匹配 receipt |
| `eval/story_segment_baseline_receipt.v1.json` | baseline 输入、代码、活动 snapshot、输出哈希和指标 |
| `src/codex_supervisor/task_receipts.py` | allowlist tree identity、task receipt 与 D RED acceptance 的 canonical contract |
| `scripts/codex-supervisor/Write-TaskReceipt.ps1` | 在 E/D 两侧调用同一 receipt contract，不自行重算身份 |
| `tests/test_codex_supervisor_task_receipts.py` | tracked/untracked/absent tree、RED witness 和 log hash 防漂移 |

### 2.2 D0 修改

| 文件 | 修改职责 |
|---|---|
| `.gitignore` | 只为四个版本化 Story eval/baseline 文件添加精确 negation；其余 `eval/*` 继续 ignored |
| `config/codex-supervisor.workers.json` | 升级 `codex-supervisor/v2` 并新增独立 E branch/worktree |
| `src/codex_supervisor/contracts.py` | 唯一 `SUPPORTED_WORKERS=("A","B","C","E")`、v2 配置和 worker validation |
| `src/codex_supervisor/cli.py` | 机器可读 `worker-list/worker-validate`，所有 CLI choices 使用公共集合 |
| `src/codex_supervisor/processes.py` | E 进程身份和兼容读取 |
| `src/codex_supervisor/runner.py` | E runner/request validation 和现有 A/B/C 恢复兼容 |
| `scripts/codex-supervisor/Start-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Resume-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Stop-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Watch-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Open-SupervisorWindows.ps1` | 从公共 worker list 打开 A/B/C/E 观察器 |
| `scripts/codex-supervisor/Show-Dashboard.ps1` | 维持公共 dashboard 入口 |
| `tests/test_codex_supervisor_contracts.py` | v2、A/B/C 状态兼容和 E 隔离 |
| `tests/test_codex_supervisor_cli.py` | worker-list/validate 和 E 命令 |
| `tests/test_codex_supervisor_processes.py` | E 精确进程身份 |
| `tests/test_codex_supervisor_powershell.py` | 脚本无手写 worker 集合 |
| `tests/test_codex_supervisor_e2e.py` | E 启动、关闭观察窗口、恢复和日志隔离 |

### 2.3 D 后置只读或外部写入口

线程 E 必须交付、D 只负责执行：

| 文件 | D 使用方式 |
|---|---|
| `scripts/probe_story_segment_storage.py` | 从 deployment inventory 只读探测真实云端 Milvus/artifact/staging 卷并生成容量 receipt |
| `scripts/build_huiji_typed_index.py` | 先做只读 Milvus preflight，再读取 candidate-build-input、调用 embedding 并 create-new shadow collection |
| `scripts/evaluate_story_segment_rag.py` | 先生成同提交性能 control receipt，再对指定 shadow collection 运行冻结 gold、baseline/candidate 和 go/no-go |
| `src/rag/vectorstore.py` | 使用 E 已验收的 typed schema/序列化/反序列化实现 |
| `src/rag_eval/story_segment_runner.py` | 生成逐项 numerator/denominator/baseline/candidate/delta/threshold 报告 |

D 不在后置阶段改写这些文件；若真实执行暴露产品缺陷，停止、记录新 correction gate，并退回 E 或另立受审修复，不在生产命令中打补丁。

---

## 3. C 发布依赖硬门（D0 前置）

### Task DC0：完成、验收并合并 C8b–C9

**Purpose:** 线程 E 的 Segment、引用与 baseline 必须建立在 C 已发布的 Story Atom 上。本门证明 C 的最终代码、语料契约和真实快照 fidelity 已进入 `main`；“文档存在”或“C 工作树能运行”均不算发布完成。

**Inputs:**

- `docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md`
- C8a checkpoint `012c7ca6b3abaa0445ccd00a8974ea4fefcbd333`
- 后续 C8b、C8c、C8d 独立实现提交
- C9 D-reviewed checkpoint commit 与随后生成的 merge-ready handoff

**D-owned ignored output:**

```text
eval/story_segment/dependencies/<run-id>/c-release-receipt.v1.json
eval/story_segment/dependencies/<run-id>/c-release-receipt.v1.sha256
eval/story_segment/dependencies/<run-id>/c9-intake-receipt.v1.json
eval/story_segment/dependencies/<run-id>/c9-intake-receipt.v1.sha256
eval/story_segment/dependencies/<run-id>/protected-state-diff.v1.json
eval/story_segment/dependencies/<run-id>/post-merge-fidelity.v1.json
```

- [ ] **Step 1: 验收 C8b、C8c、C8d、C9**

逐阶段验证：

```text
C8b  user-approved Story/legacy Parent-Child migration decision + implementation commit
C8c  user/D-approved legacy media classification decision + implementation commit
C8d  self-contained read-only fidelity entry point commit；入口固定为 scripts/diagnose_huiji_corpus_fidelity.py
C9   full regression + deterministic fixture closure + ownership audit；
     D 验收后创建 checkpoint commit，再从该 commit 生成 handoff
```

每个阶段必须有 D 批准的 commit SHA、文件 allowlist、RED/GREEN 命令与结果、真实快照或明确 `not_applicable` receipt。C9 正常没有 tracked 产品 diff，因此在 D 验收完整回归和 scope audit 后，必须从已验收 C8d HEAD 创建显式 checkpoint：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $C8dAcceptancePath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedC8dAcceptanceSha256
)

$ObservedC8dAcceptanceSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $C8dAcceptancePath).Hash.ToLowerInvariant()
if ($ObservedC8dAcceptanceSha -ne $ExpectedC8dAcceptanceSha256.ToLowerInvariant()) {
  throw 'C8d acceptance hash mismatch'
}
$C8dAcceptance = Get-Content -Raw -LiteralPath $C8dAcceptancePath | ConvertFrom-Json
if ($C8dAcceptance.schema_version -ne 'rag.thread-c-phase-acceptance/v1' -or $C8dAcceptance.phase -ne 'C8d') {
  throw 'Unexpected C8d acceptance'
}
$ExpectedC8dCommit = [string]$C8dAcceptance.commit
if ((git rev-parse HEAD) -ne $ExpectedC8dCommit) { throw 'C9 did not start from accepted C8d' }
if ((git status --short --untracked-files=no)) { throw 'C9 tracked tree is not clean' }
git commit --allow-empty -m "chore(rag): certify thread C regression handoff"
if ($LASTEXITCODE -ne 0) { throw 'C9 checkpoint commit failed' }
$C9Commit = (git rev-parse HEAD).Trim()
$C9Parent = (git rev-parse HEAD^).Trim()
if ($C9Parent -ne $ExpectedC8dCommit) { throw 'C9 parent is not accepted C8d' }
if ((git diff-tree --no-commit-id --name-only -r HEAD)) { throw 'C9 checkpoint unexpectedly changes tracked files' }
```

只有该 checkpoint 成功后才能生成 handoff；handoff 的 `c9_commit` 必须等于 `$C9Commit`，并固定 D 已验收的测试/fixture/protected receipts。不得先生成 handoff 再补写 commit SHA。C8c 若对缺少本地媒体字节保持 blocker，可以作为明确未解决项留在 C receipt；但只要该 blocker 会影响 E 所需的 Story Atom、Parent、source refs 或文本 fidelity，就不得放行 E。

- [ ] **Step 2: 审查 C 分支并固化 C9 intake**

D 重算 C9 handoff、所有 artifact 和测试 receipt 的 SHA-256；确认 C 分支不包含 raw snapshot、ignored run output、pytest 临时目录、supervisor state、向量、下载媒体或生产指针修改。随后把 C9 handoff 复制到本次 D-owned create-new dependency root，并写 `rag.thread-c9-intake/v1` receipt。Receipt 至少固定：

```text
c8b/c8c/c8d/c9 commit SHA
C9 handoff copied relative path / size / SHA-256
C8d entrypoint relative path / SHA-256 / schema version
source snapshot / active baseline / protected manifest relative paths and SHA-256
expected C8d output names
```

后续 C8d 命令只能从该 receipt 解析输入；不得再读取 C worktree、C supervisor state 或旧 ignored run 目录。

- [ ] **Step 3: 合并 C 到 main**

保存并保护当前用户工作区边界；非破坏性合并 C。只解决 C 已批准提交与 `main` 的真实冲突，不 stash/reset/checkout/delete 用户文件。

- [ ] **Step 4: 在合并后的 main 运行固定 C8d CLI**

C8d 必须提交且 C9 handoff 必须固定：

```text
entrypoint.relative_path == scripts/diagnose_huiji_corpus_fidelity.py
entrypoint.sha256
entrypoint.schema_version == huiji.corpus-fidelity-diagnostic/v1
source snapshot / active baseline / protected manifest paths and SHA-256
expected output file names
```

D 先验证入口来自合并后的 commit、SHA 匹配且不能 `exec()` 或 import 旧 ignored run 脚本，再运行：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $C9IntakeReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedC9IntakeReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$Project = 'D:\1999Wiki'
$C9IntakeReceiptPath = [IO.Path]::GetFullPath($C9IntakeReceiptPath)
$ObservedC9IntakeSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $C9IntakeReceiptPath).Hash.ToLowerInvariant()
if ($ObservedC9IntakeSha -ne $ExpectedC9IntakeReceiptSha256.ToLowerInvariant()) {
  throw 'C9 intake receipt hash mismatch'
}
$C9Intake = Get-Content -Raw -LiteralPath $C9IntakeReceiptPath | ConvertFrom-Json
if ($C9Intake.schema_version -ne 'rag.thread-c9-intake/v1') {
  throw 'Unexpected C9 intake schema'
}
$C8dEntrypoint = [IO.Path]::GetFullPath(
  (Join-Path $Project ([string]$C9Intake.c8d_entrypoint.relative_path))
)
if ([string]$C9Intake.c8d_entrypoint.relative_path -ne 'scripts/diagnose_huiji_corpus_fidelity.py') {
  throw 'Unexpected C8d entrypoint path'
}
$ObservedEntrypointSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $C8dEntrypoint).Hash.ToLowerInvariant()
if ($ObservedEntrypointSha -ne [string]$C9Intake.c8d_entrypoint.sha256) {
  throw 'C8d entrypoint hash mismatch'
}
$C8dRunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$C8dRunRoot = Join-Path $Project "eval\story_segment\dependencies\$C8dRunId\c8d"
$C8dLog = Join-Path $C8dRunRoot 'c8d-cli.log'
$null = New-Item -ItemType Directory -Path $C8dRunRoot
$C8dArgs = @(
  $C8dEntrypoint,
  '--project-root', $Project,
  '--c9-intake', $C9IntakeReceiptPath,
  '--expected-c9-intake-sha256', $ExpectedC9IntakeReceiptSha256,
  '--output-root', $C8dRunRoot,
  '--read-only'
)
& $Python @C8dArgs 2>&1 | Tee-Object -LiteralPath $C8dLog
if ($LASTEXITCODE -ne 0) { throw "C8d post-merge fidelity failed: $LASTEXITCODE" }
```

调用者必须显式传入已验收的 `C9IntakeReceiptPath` 和期望 SHA-256；wrapper 与 C8d CLI 都先验哈希再解析。C8d 自身从 intake 解析并逐项验证 C9 handoff、source snapshot、active baseline、protected manifest 和 expected outputs，不接受这些对象的重复 CLI 参数；若 wrapper 所见 entrypoint 与 C8d 所见 intake 身份不一致则停止。运行完整恢复快照后要求：

```text
diagnostic status == completed
FidelityResult returned normally and its exact payload SHA-256 is recorded
every FidelityResult blocker is classified exactly once as story_dependency or non_story_media
story_dependency_blockers == []
Story Parent/Atom/source-ref closure == true
all candidate Story records have an approved fidelity class
protected identity count == 32
protected drift count == 0
network/download/embedding/vector/activation/pointer/production write count == 0
```

若仍有媒体证据 blocker，`FidelityResult.passed` 可以为 false，但这些 blocker 必须逐项进入 `non_story_media_blockers`，不得猜测核销，并证明不改变 E 所需的 Story 文本/Atom 输入；分类并集必须与原始 blocker 多重集合完全一致且交集为空。任何 Story 文本、Atom、source-ref 或 migration blocker 立即停止。

- [ ] **Step 5: 生成 C release receipt**

Receipt 至少包含：

```json
{
  "schema_version": "rag.thread-c-release/v1",
  "c_phase_commits": {
    "c8a": "40-hex",
    "c8b": "40-hex",
    "c8c": "40-hex",
    "c8d": "40-hex",
    "c9": "40-hex",
    "c9_handoff_sha256": "64-hex"
  },
  "approved_decisions": {
    "c8b_story_migration_sha256": "64-hex",
    "c8c_legacy_media_sha256": "64-hex"
  },
  "c_merge_commit": "40-hex",
  "c8d_execution": {
    "command_schema_version": "rag.c8d-post-merge-command/v1",
    "entrypoint_relative_path": "scripts/diagnose_huiji_corpus_fidelity.py",
    "entrypoint_sha256": "64-hex",
    "c9_intake_receipt_sha256": "64-hex",
    "c9_handoff_sha256": "64-hex",
    "argv": [],
    "exit_code": 0,
    "log_sha256": "64-hex",
    "output_manifest_sha256": "64-hex",
    "output_files": []
  },
  "source_snapshot_identity": {},
  "published_artifacts": {
    "parent_blocks": {"path": "", "sha256": "64-hex", "row_count": 0},
    "story_atoms": {"path": "", "sha256": "64-hex", "row_count": 0},
    "source_refs": {"path": "", "sha256": "64-hex", "row_count": 0},
    "build_manifest": {"path": "", "sha256": "64-hex"}
  },
  "fidelity_result_sha256": "64-hex",
  "fidelity_passed": false,
  "fidelity_blocker_multiset_sha256": "64-hex",
  "classified_blocker_multiset_sha256": "64-hex",
  "test_receipts": [],
  "protected_identity_count": 32,
  "protected_drift_count": 0,
  "story_dependency_blockers": [],
  "non_story_media_blockers": [],
  "e_dependency_ready": false
}
```

`e_dependency_ready=true` 仅当：

- C8b–C9 全部验收并合并；
- 合并后重建与 fidelity 正常返回；
- `story_dependency_blockers == []`，即 Story Parent/Atom/source-ref/migration 无 blocker；
- 所有发布路径均位于 `main` 的固定 build root，哈希与行数闭合；
- 保护状态零漂移且 forbidden counters 全零。

`non_story_media_blockers` 可以保留 C8c 中证据不足的旧媒体关系，但必须逐类计数并证明不改变 Story 文本/Atom/source-ref。它们不能被重命名为“已核销”，也不能被 E 消费或用来放宽媒体运行时。

- [ ] **Step 6: 绑定后续 D0**

D0.2、D0.3 和 D0.4 必须接收 `c-release-receipt.v1.json` 的绝对路径及期望 SHA-256，重新验证 schema、artifact hashes 和 `e_dependency_ready=true`。合并祖先关系必须实际执行：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $CReleaseReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedCReleaseReceiptSha256
)

$Project = 'D:\1999Wiki'
$ObservedReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $CReleaseReceiptPath).Hash.ToLowerInvariant()
if ($ObservedReceiptSha -ne $ExpectedCReleaseReceiptSha256.ToLowerInvariant()) {
  throw 'C release receipt hash mismatch'
}
$CRelease = Get-Content -Raw -LiteralPath $CReleaseReceiptPath | ConvertFrom-Json
if ($CRelease.schema_version -ne 'rag.thread-c-release/v1' -or -not $CRelease.e_dependency_ready) {
  throw 'C release receipt is not E-ready'
}
$CMergeCommit = [string]$CRelease.c_merge_commit
git -C $Project merge-base --is-ancestor $CMergeCommit HEAD
if ($LASTEXITCODE -ne 0) { throw 'C merge commit is not an ancestor of HEAD' }
```

`$CMergeCommit` 必须由已验证 receipt 解析，不得手填。任一不符时停止；不得重新从 C worktree 补取文件。

---

## 4. D0：监督器与评测基线

### Task D0.1：升级监督器为独立 E worker

**Spec coverage:** `THREAD-P0-05` 至 `THREAD-P0-10`、`SUPERVISOR-P0-01` 至 `SUPERVISOR-P0-04`、`REVIEW-P0-01`、`REVIEW-P0-02`

**Files:**

- Modify: `config/codex-supervisor.workers.json`
- Modify: `src/codex_supervisor/contracts.py`
- Modify: `src/codex_supervisor/cli.py`
- Modify: `src/codex_supervisor/processes.py`
- Modify: `src/codex_supervisor/runner.py`
- Create: `src/codex_supervisor/task_receipts.py`
- Modify: `scripts/codex-supervisor/Start-Worker.ps1`
- Modify: `scripts/codex-supervisor/Resume-Worker.ps1`
- Modify: `scripts/codex-supervisor/Stop-Worker.ps1`
- Modify: `scripts/codex-supervisor/Watch-Worker.ps1`
- Modify: `scripts/codex-supervisor/Open-SupervisorWindows.ps1`
- Modify: `scripts/codex-supervisor/Show-Dashboard.ps1`
- Create: `scripts/codex-supervisor/Write-TaskReceipt.ps1`
- Modify: `tests/test_codex_supervisor_contracts.py`
- Modify: `tests/test_codex_supervisor_cli.py`
- Modify: `tests/test_codex_supervisor_processes.py`
- Modify: `tests/test_codex_supervisor_powershell.py`
- Modify: `tests/test_codex_supervisor_e2e.py`
- Create: `tests/test_codex_supervisor_task_receipts.py`

**Frozen interface:**

```python
SUPPORTED_WORKERS: tuple[str, ...] = ("A", "B", "C", "E")
WorkerName = Literal["A", "B", "C", "E"]

def validate_worker_name(value: object) -> WorkerName: ...
def supported_workers_json() -> dict[str, object]: ...

def compute_allowed_tree_identity(
    *,
    repository_root: Path,
    base_commit: str,
    allowed_relative_paths: Sequence[str],
) -> AllowedTreeIdentity: ...

def verify_task_receipt(receipt: Mapping[str, object]) -> None: ...
```

`AllowedTreeIdentity` 使用以下唯一算法：把 allowlist 规范化为无重复、升序 POSIX 相对路径；对每个路径记录 `state=absent|file`，file 时记录 raw-byte `size_bytes` 与小写 SHA-256；未跟踪文件和已跟踪文件同等计入，删除项以 `absent` 计入。将 `schema_version=codex.allowed-tree-identity/v1`、`base_commit` 和完整 entries 用 UTF-8、keys 升序、无额外空白的 canonical JSON 编码后取 SHA-256。目录、符号链接、越出仓库路径、allowlist 外变化或同路径不同大小/哈希均拒绝。

CLI：

```text
codex-supervisor worker-list --json
codex-supervisor worker-validate --worker E --json
```

PowerShell 脚本不得保留 `ValidateSet("A","B","C","E")` 或独立数组；它们调用 `worker-validate`，窗口启动器调用 `worker-list`。

- [ ] **Step 1: 写 RED tests**

测试必须先证明：

- v1 配置被明确拒绝，v2 必须精确包含 A/B/C/E；
- A/B/C 既有 state 路径和内容原样读取，不重写迁移；
- E 使用独立 branch、worktree、state、event、stderr、session、lock；
- Python CLI 和六个 PowerShell 入口只消费公共 worker list；
- `running + pid=null` 不被 status/inspect 判定为可信存活；
- E 观察窗口关闭后 worker 仍在；
- E 原 session 可恢复；
- E 不能映射到 C 的目录或 session；
- RED/GREEN tree identity 包含 allowlist 内未跟踪测试和实现文件；
- 相同 base/bytes 生成相同 canonical identity，absent/file、额外文件或日志哈希漂移均被拒绝；
- D 的 RED acceptance 必须绑定 pre-implementation tree identity 与 RED log SHA-256。

Run RED:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_codex_supervisor_task_receipts.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-supervisor-red-' + [Guid]::NewGuid().ToString('N')))
```

Expected: v2/E/public-worker-list 测试因当前只支持 A/B/C 而失败；task receipt 测试因 canonical tree identity 与 RED acceptance contract 尚不存在而失败。

- [ ] **Step 2: 实现唯一 worker 集合、配置 v2 与 task receipt**

只替换 worker identity/config/CLI/PowerShell 验证来源，并实现独立的 canonical tree/task receipt 模块；不重构事件归约、状态语义或 token 统计。

- [ ] **Step 3: 运行 GREEN 与相邻回归**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_codex_supervisor_events.py `
  tests/test_codex_supervisor_task_receipts.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-supervisor-green-' + [Guid]::NewGuid().ToString('N')))
```

Expected: exit code 0。

- [ ] **Step 4: 静态拒绝手写集合**

```powershell
rg -n 'A.*B.*C|ValidateSet|choices=' `
  src/codex_supervisor `
  scripts/codex-supervisor
```

逐项确认所有命中只剩 `SUPPORTED_WORKERS` 定义、测试预期或与 worker 无关的文本。

- [ ] **Step 5: 提交**

```powershell
git diff --check
git add -- `
  config/codex-supervisor.workers.json `
  src/codex_supervisor/contracts.py `
  src/codex_supervisor/cli.py `
  src/codex_supervisor/processes.py `
  src/codex_supervisor/runner.py `
  src/codex_supervisor/task_receipts.py `
  scripts/codex-supervisor/Start-Worker.ps1 `
  scripts/codex-supervisor/Resume-Worker.ps1 `
  scripts/codex-supervisor/Stop-Worker.ps1 `
  scripts/codex-supervisor/Watch-Worker.ps1 `
  scripts/codex-supervisor/Open-SupervisorWindows.ps1 `
  scripts/codex-supervisor/Show-Dashboard.ps1 `
  scripts/codex-supervisor/Write-TaskReceipt.ps1 `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_codex_supervisor_task_receipts.py
git commit -m "feat(codex): add supervised story segment worker"
```

### Task D0.2：冻结 Story gold、等价 Atom 匹配器和阈值

**Spec coverage:** `EVALSET-P0-01` 至 `EVALSET-P0-18`、`EVAL-P0-01` 至 `EVAL-P0-03`、`GATE-P0-01` 至 `GATE-P0-06`、`REVIEW-P0-04`、`REVIEW-P0-09` 至 `REVIEW-P0-12`

**Files:**

- Modify: `.gitignore`
- Create: `src/rag_eval/story_segment_baseline.py`
- Create: `scripts/capture_story_segment_baseline.py`
- Create: `tests/test_story_segment_baseline.py`
- Create: `eval/story_segment_eval.v1.jsonl`
- Create: `eval/story_segment_thresholds.v1.json`
- Read-only required input: accepted C release receipt and its published Story Atom artifact

- [ ] **Step 0: 只开放四个版本化 eval 文件**

在现有 `eval/*` 规则后增加且只增加：

```gitignore
!eval/story_segment_eval.v1.jsonl
!eval/story_segment_thresholds.v1.json
!eval/story_baseline_atom_equivalence.v1.jsonl
!eval/story_segment_baseline_receipt.v1.json
```

不得开放 `eval/story_segment/`、run/handoff/receipt 临时目录或其他 `eval/*`。创建文件后逐项执行 `git check-ignore --no-index -q -- <path>`，四个版本化文件都必须返回非零；另用一个 `eval/story_segment/runs/probe.json` 证明普通运行产物仍被 ignore。

同一步先重验 C release receipt；gold 中每个 Atom ID/path/hash 必须来自 receipt 固定的合并后 Story Atom artifact。C release 未通过或 artifact hash 不符时，本 Task 不得创建 gold。

**Frozen baseline API:**

```python
@dataclass(frozen=True)
class AtomEvidenceTarget:
    query_id: str
    atom_id: str
    required_atom_group: str
    source_title: str
    source_json_path: str
    source_content_sha256: str
    normalized_evidence_sha256: str

@dataclass(frozen=True)
class AtomEquivalenceMatch:
    query_id: str
    stage: Literal["retrieval_at_k", "final_context"]
    result_rank: int
    atom_id: str
    match_rule: Literal[
        "exact_atom_id",
        "exact_source_path_revision_hash",
        "unique_exact_text_span",
        "unmatched",
        "ambiguous",
    ]
    matched_span: tuple[int, int] | None
    matched: bool
    reason_code: str

def match_active_evidence_to_atoms(
    active_results: Sequence[Mapping[str, object]],
    gold_atoms: Sequence[AtomEvidenceTarget],
    *,
    stage: Literal["retrieval_at_k", "final_context"],
) -> tuple[AtomEquivalenceMatch, ...]: ...
```

匹配顺序严格为：

1. exact Atom ID；
2. exact source JSON path + 同 source revision/content hash；
3. 同来源版本中的唯一规范证据文本 span；
4. 否则 unmatched/ambiguous。

一个活动 span 最多消费一次；migration expansion group 本身不产生覆盖。

- [ ] **Step 1: 写 baseline matcher RED tests**

覆盖：

- 精确 Atom ID；
- 精确 path/revision/hash；
- 唯一 exact text span；
- 重复文本歧义；
- source version 不同；
- 仅有 migration group；
- 空 source ref；
- Unicode/空白规范化边界；
- 同一 span 不可消费多个 Atom；
- `retrieval_at_k` 与 `final_context` 完全隔离；
- LLM answer、Planner rewrite 和 summary 永不作为覆盖证据。

Run RED:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_baseline.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-baseline-red-' + [Guid]::NewGuid().ToString('N')))
```

Expected: import/contract tests fail because matcher does not exist。

- [ ] **Step 2: 实现最小 matcher 与 canonical receipt**

Receipt 按 `query_id, stage, rank, atom_id` 排序；JSON 使用 UTF-8、sorted keys、有限数字和 LF。

- [ ] **Step 3: 冻结评测集**

`eval/story_segment_eval.v1.jsonl` 至少包含：

- 精确对白/专名/内部 ID；
- `6`、`37` 和其他纯数字或短实体；
- 单 Story 局部事实；
- 单 Story 多细节；
- 中后段剧情事实；
- “伊索尔德是在哪一章出现的”；
- “伊索尔德是怎么疯掉的”；
- 显式 2、3、4、5、32、33 Story；
- 角色技能 + Story 介绍复合请求；
- Story continuation 与 anchor；
- `暴雨是什么` Topic 定义；
- Story 例证补充分支；
- 分支互斥、汇合和 cycle；
- oversize Atom；
- local fact、bounded multi-evidence、exhaustive narrative；
- 非 Story 的短 alias、长词子串、跨类型同名负例；
- continuation 篡改/stale/oversize action；
- `not_applicable`、failed、empty 和 mixed composite 状态。

Gold 每行必须引用同版固定 Atom artifact 身份，不写自由文本“应该差不多命中”。

- [ ] **Step 4: 冻结阈值**

`eval/story_segment_thresholds.v1.json` 逐项编码 Spec 第 26.1 节阈值、方向、零容忍属性和 denominator definition。不得使用一个 `pass_rate` 代替逐项门槛。

- [ ] **Step 5: 运行 GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_baseline.py `
  tests/test_rag_eval_contracts.py `
  tests/test_rag_eval_deterministic.py `
  tests/test_rag_eval_scoring.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-baseline-green-' + [Guid]::NewGuid().ToString('N')))
```

Expected: exit code 0。

- [ ] **Step 6: 提交 matcher、gold 和 thresholds**

```powershell
git diff --check
git add -- `
  .gitignore `
  src/rag_eval/story_segment_baseline.py `
  scripts/capture_story_segment_baseline.py `
  tests/test_story_segment_baseline.py `
  eval/story_segment_eval.v1.jsonl `
  eval/story_segment_thresholds.v1.json
git commit -m "test(rag): freeze story segment evaluation contracts"
```

### Task D0.3：捕获当前活动 baseline 与依赖 receipt

**Spec coverage:** `EVALSET-P0-03` 至 `EVALSET-P0-14`、`PROVENANCE-P0-01` 至 `PROVENANCE-P0-06`、`THREAD-P0-03`、`THREAD-P0-10`、`SCOPE-P0-01`、`SCOPE-P0-06`

**Files:**

- Create: `eval/story_baseline_atom_equivalence.v1.jsonl`
- Create: `eval/story_segment_baseline_receipt.v1.json`
- Read-only required input: D-owned `c-release-receipt.v1.json` and `.sha256`
- No production code change unless Task D0.2 tests reveal a separately reviewed matcher defect

- [ ] **Step 1: 验证 C release receipt 与固定依赖**

不得再用“两个 C 文档已被跟踪”替代 C 发布验证。先读取 DC0 的 receipt 路径与期望 SHA-256，验证：

```text
schema_version == rag.thread-c-release/v1
e_dependency_ready == true
c_merge_commit is an ancestor of current main
C8a/C8b/C8c/C8d commit identities match the reviewed commits
published Parent/Story Atom/source-ref/build-manifest paths are inside the fixed main build root
every published artifact size/row_count/SHA-256 matches
post-merge fidelity receipt hash matches
protected_identity_count == 32
protected_drift_count == 0
Story-text/Atom/source-ref remaining blockers == []
```

然后确认 C migration decision、closure-gates plan 和 C8d 自包含诊断入口均由该合并提交跟踪。任一项不符立即停止；不得从当前未跟踪副本、C worktree 或旧 run 目录读取实施契约或数据。

- [ ] **Step 2: 只读验证活动产物**

使用现有 provenance verifier 验证 active Parent/Child/BM25/Milvus 指针和 source snapshot。记录：

```text
path
size
row_count
sha256
schema_version
build_version
active_pointer_sha256
collection_name
collection_schema_sha256
```

- [ ] **Step 3: 捕获 baseline**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' `
  scripts/capture_story_segment_baseline.py `
  --queries eval/story_segment_eval.v1.jsonl `
  --thresholds eval/story_segment_thresholds.v1.json `
  --equivalence-output eval/story_baseline_atom_equivalence.v1.jsonl `
  --receipt-output eval/story_segment_baseline_receipt.v1.json `
  --reranker-disabled
```

要求：

- 只读 active collection；
- 记录 retrieval-at-k 和 final-context 两种 stage；
- 不把最终答案计为 Atom evidence；
- reranker call count 为 0；
- 输出逐行 canonical；
- 不修改 active pointer、collection 或 corpus artifact。
- gold 与等价匹配只引用 C release receipt 固定的 Story Atom artifact；不得把 C 分支、旧 run 目录或旧活动聚合 Story Child 当作新 Atom 事实源。

- [ ] **Step 4: 重跑并验证字节一致**

第二次输出到新临时目录；比较两次 JSONL 和 receipt 的业务内容哈希。仅 `captured_at_utc`、run ID 等显式非身份字段允许变化，且不得进入 baseline identity。

- [ ] **Step 5: 提交 baseline**

```powershell
git diff --check
git add -- `
  eval/story_baseline_atom_equivalence.v1.jsonl `
  eval/story_segment_baseline_receipt.v1.json
git commit -m "test(rag): capture story segment active baseline"
```

### Task D0.4：创建 E worktree 并只下发已批准 E Plan

**Spec coverage:** `THREAD-P0-01` 至 `THREAD-P0-10`、`SUPERVISOR-P0-01` 至 `SUPERVISOR-P0-04`

**Files:**

- Runtime only: `.codex-supervisor/workers/E/approved-task.md`
- Runtime only: `.codex-supervisor/workers/E/dependency-receipt.v1.json`
- No tracked source change

- [ ] **Step 1: 生成 D0 dependency receipt**

Receipt 必须包含：

```text
main_commit
spec_commit/spec_sha256
D Plan sha256
E Plan sha256
C release receipt path/sha256/schema
C8a/C8b/C8c/C8d/C9 and C merge commit identities
C post-merge fidelity and published Parent/Story Atom/source-ref artifact sha256
gold/threshold/baseline receipt sha256
Conda interpreter/version/prefix
reranker disabled
approved branch/worktree
```

Receipt 生成器必须重新验证 C release receipt 和所有发布 artifact；不得只复制其中字段。`main_commit` 必须包含 `c_merge_commit`，且与即将创建 E worktree 的基线完全相同。

- [ ] **Step 2: 验证目标路径**

解析绝对路径并确认：

```text
D:\1999Wiki.worktrees\rag-e-story-segment
```

不存在同名脏 worktree、branch 或 supervisor state。若存在，停止并审计；不得删除或覆盖。

- [ ] **Step 3: 创建 worktree**

```powershell
$EBaseCommit = (git rev-parse HEAD).Trim()
git worktree add `
  -b codex/rag-e-story-segment `
  'D:\1999Wiki.worktrees\rag-e-story-segment' `
  $EBaseCommit
```

创建后立即验证 E 的 `HEAD == $EBaseCommit`，并在 E worktree 中重新读取 D0 receipt；若 C release receipt 或任一发布 artifact 哈希不同，删除动作不获授权，E 保持未启动并报告 blocker。

- [ ] **Step 4: 写 approved task**

任务必须引用已提交的 E Plan、Spec、D0 receipt，明确：

```text
Plan phase: E0 only
Subagents: forbidden
Embedding API: forbidden
Milvus writes: forbidden
Production activation: forbidden
Allowed files: E0 allowlist only
Stop state: completed_pending_review
```

- [ ] **Step 5: 启动并验证可观察性**

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File 'D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1' `
  -Worker E
```

重新打开观察窗口命令：

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass `
  -File 'D:\1999Wiki\scripts\codex-supervisor\Watch-Worker.ps1' `
  -Worker E
```

关闭观察窗口后用 OS PID/create-time、event log 最后时间和 state heartbeat 三项确认 worker 仍运行。

---

## 5. E 阶段监督门

### Task D1：逐 Task 接受 E0–E5

**Files:** no implementation edits in D

E0.0 是不提交的 preflight。E0.1–E5.3 共 16 个 implementation Task 都是阶段内的独立小门，必须按以下顺序：

1. E 只在已批准测试文件内写 RED test，不写实现，并停在 `red_pending_d_witness`。
2. E 运行表中精确 RED argv，保存 raw log，使用 D0.1 的 canonical 算法计算包含未跟踪测试文件的 `red_tree_identity`。
3. D 在同一未实现 tree 上检查 allowlist/diff，独立复跑同一 RED argv；只有观察到表中业务失败后，D 才写 hash-pinned `rag.story-segment-red-acceptance/v1`，固定 task/base、E/D RED logs、`red_tree_identity` 和预期/实际失败。收集错误、环境错误或测试名不存在均拒绝。
4. D 将 RED acceptance 路径/SHA-256 写入 resume 指令，才允许 E 做最小实现和运行阶段 GREEN。
5. E 运行该阶段规定的相邻回归和真实证据门，计算 `green_tree_identity` 与 GREEN log SHA-256。
6. E 写 `rag.story-segment-task-receipt/v1`，分别固定 RED/GREEN tree/log、D RED acceptance、真实证据 required/not_applicable、protected drift、forbidden counters 和文件范围。
7. E 停在 `completed_pending_review`，不提交下一阶段。
8. D 独立检查：
   - `git diff --check`
   - `git diff --name-only`
   - `git status --short`
   - 代码与 Spec contract
   - E 的测试命令
   - 真实快照证据和 protected pre/post
   - forbidden operation counters
9. D 重算 task receipt/tree/log/RED acceptance hashes，复跑 GREEN suite，并核对真实证据或表中明确的 `not_applicable` 理由。D 不在实现后把已转绿的 test 伪称为 RED 复跑。
10. D 接受后才允许精确 Task 提交。下一 Task 使用同一 E worktree；若 session 上下文过重，可在 Task 提交后新开 E session，但仍只有一个 E worker。

每份 D RED acceptance 使用：

```json
{
  "schema_version": "rag.story-segment-red-acceptance/v1",
  "task_id": "E0.1",
  "base_commit": "40-hex",
  "allowed_tree_identity_sha256": "64-hex",
  "allowed_tree_manifest_sha256": "64-hex",
  "expected_business_failure": "",
  "e_red": {"argv": [], "exit_code": 1, "log_sha256": "64-hex", "observed_failure": ""},
  "d_red": {"argv": [], "exit_code": 1, "log_sha256": "64-hex", "observed_failure": ""},
  "observed_changed_files": [],
  "outside_allowlist_change_count": 0,
  "accepted_at_utc": "RFC3339 UTC",
  "d_supervision_commit": "40-hex"
}
```

Acceptance 写入后即不可变；E 的 resume prompt 只携带路径和期望 SHA-256。若 tree、base、argv、日志或 allowlist 后续变化，必须废弃本次 acceptance 并从新的 RED gate 开始，不能在原 receipt 上补字段。

D 不接受：

- 只报测试数量、不提供命令和新鲜输出；
- fixture 通过但真实快照闭包失败；
- 为旧 schema 猜测兼容 Segment；
- 将 `segment_id` 填入 `child_id`；
- 放宽 Owner Gate；
- 通过质量硬标签删除短/数字内容；
- 在 E 中调用真实 embedding 或 Milvus；
- 未经审查将多个阶段堆进一个提交。

### Task D2：审查 E5 handoff

- [ ] **Step 1: 验证 E 分支提交链**

要求 E0.0 只有预检 receipt、不提交；E0.1–E5.3 共 16 个 implementation Task 各有一个独立、可追踪提交。提交不得包含 ignored real-run outputs、原始 snapshot、pytest basetemp、supervisor state 或用户文件。

- [ ] **Step 2: 验证 handoff schema 和哈希**

重算所有文件 SHA-256、row count、ordered ID hash、schema hash 和 config identity。

- [ ] **Step 3: 验证 typed Dense 行集合**

必须证明：

```text
all non-Story Child -> retrieval_unit_type=child
all Story Segment -> retrieval_unit_type=story_segment
no Story Atom -> typed Dense input
no segment_id copied into child_id
retrieval_unit_id globally unique
exact field is segment_sequence_index; segment_sequence is absent
child segment_sequence_index == -1; story_segment chunk_index == -1
text length <= 16384
reranker call count == 0
```

- [ ] **Step 4: 验证无外部漂移**

比较 protected pre/post：

- active pointer；
- active Milvus collection/schema/row count；
- source snapshot；
- active BM25；
- MinIO/MySQL 状态；
- runtime config；
- production provenance。

任何 drift 阻断合并。

- [ ] **Step 5: 固化 D-owned handoff intake**

E handoff 只能在 E5.3 已提交、E HEAD clean 且 `e_commit == HEAD` 后生成。D 将 handoff 列出的文件逐个复制到 create-new ignored 目录：

```text
eval/story_segment/intake/<run-id>/
```

随后重算 SHA-256，并写 `d-e-handoff-intake.v1.json`。Receipt 固定 E branch/commit、原 handoff path/hash、复制后相对路径/hash/size、typed artifact、candidate-build-input、离线容量估算、test/protected receipts。此时不存在真实 collection，因此 intake 不得声称包含最终 runtime snapshot。后续 D3–D5 只消费 intake，不再依赖 E worktree 文件；E worktree 的后续变化使 intake 作废。

---

## 6. D 合并与真实向量影子构建

### Task D3：合并 E 到 main 并运行合并后回归

**Spec coverage:** `THREAD-P0-02`、`THREAD-P0-04`、`REVIEW-P0-01` 至 `REVIEW-P0-18`

- [ ] **Step 1: 保存 main 用户工作区边界**

记录 `git status --short`，确认用户文件不与 E 提交冲突。不得 stash、reset、checkout 或删除用户改动。

- [ ] **Step 2: 审查 E 提交**

```powershell
git log --oneline --decorate --no-merges main..codex/rag-e-story-segment
git diff --stat main...codex/rag-e-story-segment
git diff --check main...codex/rag-e-story-segment
```

- [ ] **Step 3: 合并**

使用非破坏性 merge。发生冲突时只解决 E 与已批准 D0 代码的真实冲突；不改无关用户文件。

- [ ] **Step 4: 运行 E Plan 的完整测试矩阵**

使用 OS 临时目录下的 create-new basetemp，至少包含 supervisor、build、runtime artifacts、BM25、vectorstore、request plan、route policy、retriever、budget、citations、execution、conversation、serializer、backend、SSE、frontend 和 rag_eval。

- [ ] **Step 5: 创建合并后 candidate-build-input**

在 create-new build version 下离线重建 Story structure、Segment 和 typed Dense JSONL；比较 E handoff 的 schema/config identity，允许数据 build version 变化但不允许算法身份漂移。本步骤只生成 `rag.story-candidate-build-input/v1`，因为真实 collection 尚不存在；禁止生成 `rag.runtime-artifact-snapshot/v2`。

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $DIntakeReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedDIntakeReceiptSha256,
  [Parameter(Mandatory = $true)]
  [string] $CReleaseReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedCReleaseReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$CandidateRunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$CandidateRunRoot = Join-Path 'D:\1999Wiki\eval\story_segment\runs' $CandidateRunId
$ObservedDIntakeSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $DIntakeReceiptPath).Hash.ToLowerInvariant()
$ObservedCReleaseSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $CReleaseReceiptPath).Hash.ToLowerInvariant()
if ($ObservedDIntakeSha -ne $ExpectedDIntakeReceiptSha256.ToLowerInvariant()) {
  throw 'D handoff intake hash mismatch'
}
if ($ObservedCReleaseSha -ne $ExpectedCReleaseReceiptSha256.ToLowerInvariant()) {
  throw 'C release receipt hash mismatch'
}
& $Python scripts/build_story_segment_candidate.py `
  --handoff-intake $DIntakeReceiptPath `
  --expected-handoff-intake-sha256 $ExpectedDIntakeReceiptSha256 `
  --c-release-receipt $CReleaseReceiptPath `
  --expected-c-release-receipt-sha256 $ExpectedCReleaseReceiptSha256 `
  --output-root $CandidateRunRoot `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Candidate build-input generation failed' }
```

命令必须在 embedding provider/Milvus constructor 之前退出，输出：

```text
candidate-build-input.v1.json
candidate-build-input.v1.sha256
deployment-inventory.v1.json
offline-capacity-estimate.v1.json
candidate-build-receipt.v1.json
```

D 重新验证 candidate-build-input 的完整 artifact tuple、expected typed collection schema、typed input、C/D0/E identities 和 protected state。命令还必须把 D intake 固定的 deployment inventory 复制为同一 candidate root 内的不可变 `deployment-inventory.v1.json`，并在 `rag.story-candidate-build-receipt/v1` 中记录相对路径/SHA-256。`candidate-build-input.v1.json` 必须由该命令实际生成，不能手工拼接；其 schema 明确禁止 actual collection name、observed schema、observed row count 和 shadow build receipt。

`deployment-inventory.v1.json` 的 Milvus/RBAC 部分是唯一授权事实源，必须由 D intake producer 机器生成并由 D3 原字节复制，不允许 D3、D4 或 E 手填、补默认值或从 `describe_role()` 结果反推策略。它至少精确固定：remote host 与 host-key fingerprint、三个允许的绝对 storage path 及预期 device、Milvus URI/database/principal、允许的精确 role 集、以及每项允许 grant 的 `role_name/database/object_type/object_name/privilege` 五元组。`object_name` 可以是本轮唯一 `$ShadowCollection` 的受约束模板；database/global wildcard 只有在 inventory 中作为完整五元组显式列出时才被接受。D4 只把 read-only observed RBAC facts 与这些五元组比较；主体、role、database、object type/name、privilege 任一缺失、未知或超出 allowlist 均 fail-closed。D intake 缺少该 exact schema 时不得生成 E5.3 的真实 handoff、进入 D3 或执行 D4，也不得在 D4 临时补写；E2.2 只能使用同 schema 的 synthetic fixture 实现与测试 parser/preflight。

### Task D4：预检并执行一次 Typed Dense shadow build

**Spec coverage:** `INDEX-P0-01` 至 `INDEX-P0-06`、`DENSEUNIT-P0-01` 至 `DENSEUNIT-P0-11`、`PERF-P0-01` 至 `PERF-P0-09`、`PROVENANCE-P0-01` 至 `PROVENANCE-P0-06`

**External write authorization:** 仅本任务可调用 embedding API 和创建新 Milvus shadow collection。仍禁止 active pointer、生产激活、active collection 覆盖或删除。

- [ ] **Step 1: 从 D3 receipt 固定运行身份**

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $CandidateBuildReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedCandidateBuildReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$RunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$RunRoot = Join-Path 'D:\1999Wiki\eval\story_segment\shadow-runs' $RunId
$null = New-Item -ItemType Directory -Path $RunRoot
$ObservedBuildReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $CandidateBuildReceiptPath).Hash.ToLowerInvariant()
if ($ObservedBuildReceiptSha -ne $ExpectedCandidateBuildReceiptSha256.ToLowerInvariant()) {
  throw 'Candidate build receipt hash mismatch'
}
$CandidateReceipt = Get-Content -Raw -LiteralPath $CandidateBuildReceiptPath | ConvertFrom-Json
if ($CandidateReceipt.schema_version -ne 'rag.story-candidate-build-receipt/v1') {
  throw 'Unexpected candidate build receipt schema'
}
$CandidateRoot = Split-Path -Parent $CandidateBuildReceiptPath
$CandidateBuildInput = [IO.Path]::GetFullPath(
  (Join-Path $CandidateRoot ([string]$CandidateReceipt.candidate_build_input.relative_path))
)
$CandidateBuildInputSha = [string]$CandidateReceipt.candidate_build_input.sha256
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $CandidateBuildInput).Hash.ToLowerInvariant() -ne $CandidateBuildInputSha) {
  throw 'Candidate build input hash mismatch'
}
$DeploymentInventoryPath = [IO.Path]::GetFullPath(
  (Join-Path $CandidateRoot ([string]$CandidateReceipt.deployment_inventory.relative_path))
)
$ExpectedDeploymentInventorySha256 = [string]$CandidateReceipt.deployment_inventory.sha256
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $DeploymentInventoryPath).Hash.ToLowerInvariant() -ne $ExpectedDeploymentInventorySha256) {
  throw 'Deployment inventory hash mismatch'
}
$ShadowCollection = "huiji_story_segment_shadow_$RunId"
```

Candidate receipt 必须来自 D3，schema 为 `rag.story-candidate-build-receipt/v1`，并固定 typed JSONL/schema、row/order hashes、expected Milvus schema、embedding identity、source/artifact/config identities。`$ShadowCollection` 是本阶段唯一新 collection 名。

- [ ] **Step 2: 生成远端存储容量 receipt**

在构造 embedding provider 或 Milvus client 前，用 hash-pinned deployment inventory 中的 SSH 目标和 host-key fingerprint 对真实服务器做只读探针：

```powershell
$RemoteCapacityReceipt = Join-Path $RunRoot 'remote-storage-capacity.v1.json'
& $Python scripts/probe_story_segment_storage.py `
  --candidate-build-input $CandidateBuildInput `
  --expected-candidate-build-input-sha256 $CandidateBuildInputSha `
  --deployment-inventory $DeploymentInventoryPath `
  --expected-deployment-inventory-sha256 $ExpectedDeploymentInventorySha256 `
  --remote-path /srv/1999wiki/milvus `
  --remote-path /srv/1999wiki/rag-artifacts `
  --remote-path /srv/1999wiki/import-staging `
  --max-story-segment-rows 25000 `
  --minimum-projected-free-bytes 12884901888 `
  --receipt-ttl-seconds 900 `
  --output $RemoteCapacityReceipt
if ($LASTEXITCODE -ne 0) { throw 'Remote storage capacity gate failed' }
$RemoteCapacityReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $RemoteCapacityReceipt).Hash.ToLowerInvariant()
```

`rag.story-shadow-storage-capacity/v1` 固定 probe UTC、TTL、远端 host identity/host-key fingerprint、每个路径的 resolved path/device ID/free bytes、active + shadow vectors + index metadata + staging + safety margin 的逐设备峰值公式、Story Segment/typed row count 和 projected free bytes。若三个目录跨设备，分别计算各设备峰值；不得把本机 `D:` 空间当作云端容量。硬门为 Story Segment `<=25000` 且所有受影响远端设备构建后 projected free `>=12 GiB`。未知、stale、路径缺失、device 不明或输入不闭合均失败；本步骤的 embedding/Milvus client/write 计数必须为 0。

- [ ] **Step 3: 生成只读 Milvus preflight receipt**

仅在 Step 2 receipt 通过并重验后，允许构造只读 Milvus client：

```powershell
$MilvusPreflightReceipt = Join-Path $RunRoot 'milvus-preflight.v1.json'
& $Python scripts/build_huiji_typed_index.py milvus-preflight `
  --candidate-build-input $CandidateBuildInput `
  --expected-candidate-build-input-sha256 $CandidateBuildInputSha `
  --remote-capacity-receipt $RemoteCapacityReceipt `
  --expected-remote-capacity-receipt-sha256 $RemoteCapacityReceiptSha `
  --deployment-inventory $DeploymentInventoryPath `
  --expected-deployment-inventory-sha256 $ExpectedDeploymentInventorySha256 `
  --collection-name $ShadowCollection `
  --max-capacity-receipt-age-seconds 900 `
  --receipt-ttl-seconds 300 `
  --receipt $MilvusPreflightReceipt `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Milvus read-only preflight failed' }
$MilvusPreflightReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $MilvusPreflightReceipt).Hash.ToLowerInvariant()
```

`rag.story-shadow-milvus-preflight/v1` 必须证明 collection 不存在且不与 active/forbidden inventory 重叠、目标 database/schema 与 RBAC create/insert/index privilege 可见、active pointer/config/inventory 已 hash-pinned、read-only write count 为 0。权限不能只读证明时 fail-closed，不得以试建 collection 探测。

- [ ] **Step 4: 执行一次 shadow build 并生成最终 v2 snapshot**

只有两个 receipt 都通过、仍在 TTL 内且其输入 identity 完全一致后，才允许验证 embedding 凭证并构造 embedding provider/写 Milvus client：

```powershell
& $Python scripts/build_huiji_typed_index.py build `
  --candidate-build-input $CandidateBuildInput `
  --expected-candidate-build-input-sha256 $CandidateBuildInputSha `
  --remote-capacity-receipt $RemoteCapacityReceipt `
  --expected-remote-capacity-receipt-sha256 $RemoteCapacityReceiptSha `
  --milvus-preflight-receipt $MilvusPreflightReceipt `
  --expected-milvus-preflight-receipt-sha256 $MilvusPreflightReceiptSha `
  --deployment-inventory $DeploymentInventoryPath `
  --expected-deployment-inventory-sha256 $ExpectedDeploymentInventorySha256 `
  --collection-name $ShadowCollection `
  --max-capacity-receipt-age-seconds 900 `
  --max-milvus-preflight-receipt-age-seconds 300 `
  --receipt-root $RunRoot `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Typed Dense shadow build failed' }
```

脚本必须 create-new collection，按 typed retrieval-unit 顺序调用 embedding，写后验证 row count、PK uniqueness、observed schema、类型计数与边界样本；失败时保留 shadow 和 failure receipt，不自动 drop，不改 runtime config/active pointer。

成功后才写：

```text
shadow-build-receipt.v1.json
active-control-runtime-snapshot.v1.json
runtime-artifact-snapshot.v2.json
runtime-artifact-snapshot.v2.sha256
```

`active-control-runtime-snapshot.v1.json` 是当前合并提交中 active-v1 resolver 生成的不可变 source bytes 的逐字节副本，不修改 active pointer。E2.2 必须提供单一 `resolve_active_runtime_snapshot_source_v1(cfg)` 接口：同一次调用返回已验证的 `RuntimeArtifactSnapshot` 与 exact `rag.active-control-runtime-snapshot/v1` canonical bytes；bytes 只由该次 resolver 已验证的 active pointer、runtime config、artifact tuple、collection identity 和 source raw-byte hashes 产生。Builder 必须在任何 embedding/Milvus 写调用前捕获这一份 bytes，之后只能原样写出，禁止从 dataclass、typed-v2 字段或第二次序列化重建。写后再次运行 resolver，并要求 source bytes、active pointer、config 与 collection inventory identities 全部逐字节/逐哈希相等。最终 `rag.runtime-artifact-snapshot/v2` 固定实际 collection 名、observed schema fingerprint、observed row/type counts、embedding build identity、ordered PK hash、shadow build receipt SHA-256 和 protected active inventory；缺任一项不得生成成功 snapshot。

- [ ] **Step 5: 验证并固化 build receipt**

D 重验 retrieval-unit type counts、nullable/sentinel invariants、vector dimension、text/metadata limits、row count、PK uniqueness、artifact identity、实际 collection schema、最终 v2 snapshot 及 active collection 零漂移。成功 `rag.story-shadow-build-receipt/v1` 使用一个精确字段集：既有 candidate/collection/schema/row/type/embedding/ordered-PK/active-control 字段之外，必须包含 `status="succeeded"`、`protected_state_before`、`protected_state_after` 与 `execution_observations`。`execution_observations` 又使用 exact schema，分别记录 embedding 与 Milvus 的 API call count、batch count、最大 batch size、有限 retry count、token-safe input 上限、各阶段 monotonic elapsed milliseconds、分页验证次数，以及写后 count/PK/type/schema closure；不得把这些事实放入未受校验的自由字典。Resolver 与测试 fixture 只接受这一套字段集。Receipt 不得反向固定 candidate-v2 runtime snapshot；最终 v2 snapshot 单向固定 receipt 的相对路径与 raw-byte SHA-256，固定文件名 `runtime-artifact-snapshot.v2.sha256` 再固定 snapshot 的 raw-byte SHA-256，禁止两个 JSON 互相包含对方最终 raw-byte SHA-256。

`$RunRoot` 在 build 前已经存在，并包含 hash-pinned storage 与 Milvus preflight receipts；Builder 不得因此拒绝整个目录。它必须在任何 provider/client/外部调用前重验 RunRoot containment、拒绝 symlink/reparse escape，并以 create-new/exclusive 语义独占四个最终输出文件名以及 failure-receipt 文件名；已存在任一目标文件即 fail-closed，且不得覆盖 receipt。真实 collection 仍为 create-new，检查与创建之间的 race 也必须报告 AlreadyExists。构建失败时按本计划保留已创建的 shadow collection并发布 create-new failure receipt，禁止自动 drop；active pointer/config/active collection 始终零漂移。

### Task D5：运行真实评测并生成 go/no-go

**Spec coverage:** 全部 `EVAL-*`、`EVALSET-*`、`GATE-*`、`PERF-*`、`ANSWER-*`、`QUALITY-*`，以及第 26.1 节全部阈值

- [ ] **Step 0: 同提交、同机性能控制**

在当前合并提交、同一机器、相同进程配置、相同 query set 和相同计时器下分别运行：

```text
active v1 control: >= 1 warmup + 5 timed samples/query
typed Story v2 candidate: >= 1 warmup + 5 timed samples/query
```

不得把 D0 在旧提交捕获的语义 baseline 延迟当作性能对照。使用 E5.1 提交的固定 producer：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $ShadowBuildReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedShadowBuildReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$ObservedBuildSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ShadowBuildReceiptPath).Hash.ToLowerInvariant()
if ($ObservedBuildSha -ne $ExpectedShadowBuildReceiptSha256.ToLowerInvariant()) {
  throw 'Shadow build receipt hash mismatch'
}
$BuildReceipt = Get-Content -Raw -LiteralPath $ShadowBuildReceiptPath | ConvertFrom-Json
$BuildRoot = Split-Path -Parent $ShadowBuildReceiptPath
$ActiveRuntimeSnapshot = [IO.Path]::GetFullPath(
  (Join-Path $BuildRoot ([string]$BuildReceipt.active_control_snapshot.relative_path))
)
$ActiveRuntimeSnapshotSha = [string]$BuildReceipt.active_control_snapshot.sha256
$CandidateRuntimeSnapshot = [IO.Path]::GetFullPath(
  (Join-Path $BuildRoot 'runtime-artifact-snapshot.v2.json')
)
$CandidateRuntimeSnapshotShaFile = [IO.Path]::GetFullPath(
  (Join-Path $BuildRoot 'runtime-artifact-snapshot.v2.sha256')
)
$CandidateRuntimeSnapshotSha = (Get-Content -Raw -LiteralPath $CandidateRuntimeSnapshotShaFile).Trim().ToLowerInvariant()
if ($CandidateRuntimeSnapshotSha -notmatch '^[0-9a-f]{64}$') {
  throw 'Candidate runtime snapshot SHA-256 sidecar is invalid'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $ActiveRuntimeSnapshot).Hash.ToLowerInvariant() -ne $ActiveRuntimeSnapshotSha) {
  throw 'Active control snapshot hash mismatch'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $CandidateRuntimeSnapshot).Hash.ToLowerInvariant() -ne $CandidateRuntimeSnapshotSha) {
  throw 'Candidate runtime snapshot hash mismatch'
}
$CandidateSnapshot = Get-Content -Raw -LiteralPath $CandidateRuntimeSnapshot | ConvertFrom-Json
if ([string]$CandidateSnapshot.shadow_build_receipt.relative_path -ne 'shadow-build-receipt.v1.json') {
  throw 'Candidate runtime snapshot receipt path mismatch'
}
if ([string]$CandidateSnapshot.shadow_build_receipt.sha256 -ne $ExpectedShadowBuildReceiptSha256.ToLowerInvariant()) {
  throw 'Candidate runtime snapshot receipt SHA-256 mismatch'
}
$PerformanceReceipt = Join-Path $BuildRoot 'performance-control.v1.json'

& $Python scripts/evaluate_story_segment_rag.py performance-control `
  --queries eval/story_segment_eval.v1.jsonl `
  --active-runtime-snapshot $ActiveRuntimeSnapshot `
  --expected-active-runtime-snapshot-sha256 $ActiveRuntimeSnapshotSha `
  --candidate-runtime-snapshot $CandidateRuntimeSnapshot `
  --expected-candidate-runtime-snapshot-sha256 $CandidateRuntimeSnapshotSha `
  --warmup-count 1 `
  --timed-samples-per-query 5 `
  --output $PerformanceReceipt `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Performance control failed' }
$PerformanceReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $PerformanceReceipt).Hash.ToLowerInvariant()
```

`rag.story-segment-performance-control/v1` 记录 commit、机器/CPU/内存、进程配置、query set hash、两个 runtime snapshot hashes、warmup 数、sample 数、每次原始 timing 和 P50/P95。Candidate collection 只能由已验证的最终 v2 snapshot 解析；CLI 不接受独立 collection-name 参数。

- [ ] **Step 1: 运行 candidate retrieval**

```powershell
& $Python scripts/evaluate_story_segment_rag.py evaluate `
  --queries eval/story_segment_eval.v1.jsonl `
  --thresholds eval/story_segment_thresholds.v1.json `
  --baseline eval/story_segment_baseline_receipt.v1.json `
  --equivalence eval/story_baseline_atom_equivalence.v1.jsonl `
  --runtime-snapshot $CandidateRuntimeSnapshot `
  --expected-runtime-snapshot-sha256 $CandidateRuntimeSnapshotSha `
  --shadow-build-receipt $ShadowBuildReceiptPath `
  --expected-shadow-build-receipt-sha256 $ExpectedShadowBuildReceiptSha256 `
  --performance-control-receipt $PerformanceReceipt `
  --expected-performance-control-receipt-sha256 $PerformanceReceiptSha `
  --output-root $BuildRoot `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Story Segment evaluation failed' }
```

Evaluator 从最终 v2 snapshot 取得唯一 actual collection，并验证 snapshot 内的 shadow-build-receipt SHA-256 等于显式传入 receipt；两者不一致时 fail-closed，receipt 中重复出现的 collection name 只能作为被交叉验证的诊断字段，不能覆盖 snapshot。

- [ ] **Step 2: 验证 hard gates**

报告每项必须包含：

```text
metric
numerator
denominator
baseline
candidate
delta
threshold
direction
passed
sample_failures
```

不得只输出整体通过率。

- [ ] **Step 3: 验证零容忍项**

尤其检查：

- Owner 越权；
- 分支越界；
- 重复 Story 正文；
- Atom 引用不闭合；
- Topic/Page 必要来源丢失；
- 数字/短文本/ID 退化；
- Planner/Detector/continuation/anchor 授权错误；
- `not_applicable` 误触发 empty fallback；
- RouteDecision/REST/SSE outcome 漂移；
- 有证据 partial 被错误拒答；
- 非穷尽答案过度声称；
- baseline 等价 Atom 误计；
- oversize Atom 丢失；
- reranker/API 额外调用；
- active state drift。

- [ ] **Step 4: 生成最终判定**

任一硬门失败：

```text
decision = no_go
activation_allowed = false
```

全部硬门通过：

```text
decision = go_for_activation_review
activation_allowed = false
```

本计划永不输出 `activated=true`。

### Task D6：交付而不激活

- [ ] **Step 1: 写 D final receipt**

输出：

```text
eval/story_segment/runs/$RunId/d_final_gate.v1.json
eval/story_segment/runs/$RunId/d_final_gate.v1.sha256
eval/story_segment/runs/$RunId/protected_state_diff.v1.json
```

- [ ] **Step 2: 报告用户**

报告：

- E 合并提交；
- typed artifact 和 shadow collection 身份；
- embedding API 调用、耗时和成本可见信息；
- 逐项 go/no-go；
- 剩余 blocker；
- active pointer/config/collection 零变化；
- 是否建议另行申请激活。

- [ ] **Step 3: 停止**

不运行 `scripts/activate_huiji_candidate.py`，不切换 collection，不更新 active pointer，不删除 shadow 或 active collection。

---

## 7. D Plan 完成标准

1. C8b、C8c、C8d、C9 已分别验收，C 已合并 `main`，合并后真实 fidelity 正常返回。
2. C release receipt 固定 C 提交链、发布 Parent/Story Atom/source refs、测试、保护状态和零 Story blocker；E 不读取 C worktree。
3. 监督器 v2 由单一 worker 集合支持 A/B/C/E，A/B/C 状态兼容且 E 完全隔离。
4. E 观察窗口可关闭重开，worker 继续运行并可恢复原 session。
5. Story gold、threshold、baseline matcher 和逐 Atom receipt 在 E 实现前提交冻结。
6. E worktree 从包含 C merge、C release receipt 与 D0 的固定 main 创建。
7. E0.0 预检后，16 个 implementation Task 均有 D 在实现前见证的 RED acceptance、独立 RED/GREEN tree/log、真实证据 receipt，并由 D 审查后才提交和继续。
8. E handoff 在 E5.3 clean commit 后生成；D-owned intake 的 schema、artifact、typed row、candidate-build-input、config、测试和 protected state 闭合，不伪造未构建 runtime。
9. E 不调用 embedding/Milvus；D 合并后重建 candidate-build-input，远端容量与只读 Milvus preflight 分别通过后执行一次真实 shadow build，并在写后验证完成时生成最终 `rag.runtime-artifact-snapshot/v2`。
10. 新 collection 使用 typed retrieval unit，不包含 Story Atom Dense 行。
11. 远端存储容量 receipt 在任何 embedding/Milvus constructor 前通过；只读 Milvus preflight 仅在容量通过后运行且写计数为 0；Story Segment <=25,000 且所有受影响云端设备 projected free >=12 GiB。
12. 所有 go/no-go 指标逐项输出，不以平均分抵消硬失败。
13. Reranker 调用次数为零，质量标记不影响 P0 排序。
14. active pointer、active collection、生产配置、MinIO/MySQL 和 source snapshot 在整个流程中不变。
15. 即使结果为 go，也只进入独立激活审核，不自动发布。

---

## 8. 跨 Plan Spec 追踪

Spec 的 307 个稳定条款由 305 个 P0 和 2 个明确延后的 P1 组成。两份 Plan 共同覆盖全部 P0，并把两个 P1 固定为非目标：

| Spec 范围 | 主要 Plan 落点 |
|---|---|
| `SCOPE-P0-01..06`、`DECISION-P0-01..04`、`HIER-P0-01..03` | E0/E1；D0 依赖门和 D handoff 审查 |
| `ATOMSTRUCT-P0-01..16` | E0；D 的真实快照和 artifact 审查 |
| `SEGMENT-P0-01..06`、`BOUNDARY-P0-01..12`、`IDENTITY-P0-01..04` | E1；D deterministic rebuild |
| `CITATIONUNIT-P0-01..09` | E1/E4；D 全链引用与重复正文门 |
| `ENTITYLINK-P0-01..03`、`RELATION-P0-01..03` | E0/E3；D 精确率和分支越界门 |
| `INDEX-P0-01..06`、`DENSEUNIT-P0-01..11` | E2 adapter；D 真实 embedding/shadow build |
| `REQUESTPLAN2-P0-01..13`、`STORYBRANCH-P0-01..49`、`AUTHCTX-P0-01..06` | E3/E4；D 授权评测 |
| `PIPE-P0-01..09`、`FUSION-P0-01..09`、`CANDIDATE-P0-01..04` | E3；D 真实 retrieval 评测 |
| `OWNERBUDGET-P0-01..05`、`CONTEXTBUDGET-P0-01..08` | E3/E4；D budget/coverage 门 |
| `DETAIL-P0-01..02`、`MULTISTORY-P0-01..05`、`RELATION-P0-01..03` | E3/E4；D single/multi-story gold |
| `QUALITY-P0-01..07` | E5 shadow report；D 验证真实排序未消费 |
| `SHORTFALL-P0-01..05`、`ANSWER-P0-01..13`、`SUMMARY-P0-01..03` | E4；D answer usability/overclaim 门 |
| `FAILURE-P0-01..10` | E0–E4 fail-closed；D failure receipts |
| `PROVENANCE-P0-01..06`、`PERF-P0-01..09` | E artifact/handoff；D real build/perf |
| `EVALSET-P0-01..18`、`EVAL-P0-01..03`、`GATE-P0-01..06` | D0 baseline + E5 runner + D real go/no-go |
| `THREAD-P0-01..10`、`SUPERVISOR-P0-01..04` | D0 和双 Plan 拓扑 |
| `REVIEW-P0-01..18` | 两份 Plan 的接口、拒绝方案和 D 独立验收 |
| `DETAIL-P1-01`、`SUMMARY-P1-01` | P0 不实施；只有本轮通过后另立 Spec、评测和批准 |

该表是责任路由；线程 E Plan 的逐任务追踪矩阵必须把每个范围进一步落到具体测试和失败表现。
