# 线程 D：剧情 Segment 前置门、集成与向量影子构建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task in thread D. Do not use `superpowers:subagent-driven-development`; the approved topology is exactly `D → one supervised CLI E worker`, and E may not create subagents.

**Goal:** 在线程 E 启动前冻结可观察监督、评测集、阈值和可信 baseline；在线程 E 交付后由 D 独立审查、合并、执行一次 Typed Dense 影子向量构建和完整 go/no-go 评测，同时保持生产激活为独立门禁。

**Architecture:** 本计划只负责两端。D0 在 `main` 中升级 Codex 监督器、冻结 Story gold/baseline/阈值、验证 C 的发布依赖并创建 E worktree；E0–E5 由独立的线程 E Plan 串行实现。E 交付后，D 校验每个 Task 的独立提交和不可变 handoff，合并至 `main`，再由 D 独占 embedding API 与 Milvus 写权限，创建全新的 typed shadow collection、运行真实评测并生成逐项 go/no-go receipt。通过评测不等于激活。

**Tech Stack:** Conda `1999wiki` 中的 Python 3.11.15（`D:\Anaconda32024\envs\1999wiki\python.exe`，`sys.prefix=D:\Anaconda32024\envs\1999wiki`）、pytest 9.1.1、Codex CLI、PowerShell 5.1、Git worktree、JSON/JSONL、SHA-256、Milvus、现有 embedding API、现有 Huiji corpus/provenance/evaluation contracts。

## Global Constraints

- 批准的设计源头：`docs/superpowers/specs/2026-07-30-rag-story-segment-retrieval-design.md`。
- 批准基线提交：`300e4066630c6564d56157442765a4675b783590`。
- 批准 Spec SHA-256：`61bf46e1ec6f44b330913d1b1effdfd1828edf72b13ccd7ea8f60c61fa7f405d`。
- 配套线程 E Plan：`docs/superpowers/plans/2026-07-30-rag-story-segment-e-implementation.md`。
- 执行顺序严格为 `D0 → E0 → E1 → E2 → E3 → E4 → E5 → D merge → D shadow embedding → D go/no-go`。
- D 在 `D:\1999Wiki` 的 `main` 工作树执行；E 使用 `codex/rag-e-story-segment` 和 `D:\1999Wiki.worktrees\rag-e-story-segment`。
- E 固定使用 `gpt-5.6-sol`、标准速度、`workspace-write`、`fast_mode=false`、`multi_agent=false`，禁止子代理和第二个 CLI worker。
- 所有 Python 和 pytest 命令使用绝对解释器 `D:\Anaconda32024\envs\1999wiki\python.exe`；禁止裸 `python`、`py` 或裸 `pytest`。
- D0 未完成前不得启动 E。E Plan 未经 D 和用户审核前不得实施。
- 线程 C 的代码、Story migration decision 和 closure gate 必须先进入固定 `main` 提交；未跟踪文件、C worktree、聊天摘要和临时诊断目录均不能成为 E 输入。
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
D0
├─ 扩展监督器支持 E
├─ 冻结 gold、threshold、active baseline 与 Atom 等价 receipt
├─ 验证 C 依赖已发布
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
  "retrieval_config_identity": {},
  "story_fusion_config_identity": {},
  "offline_gate_report_sha256": "64-hex",
  "protected_state_pre_sha256": "64-hex",
  "protected_state_post_sha256": "64-hex",
  "protected_drift_count": 0,
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

### 2.2 D0 修改

| 文件 | 修改职责 |
|---|---|
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
| `scripts/build_huiji_typed_index.py` | 读取 E handoff 中已固定的 typed JSONL，调用 embedding 并创建新 shadow collection |
| `scripts/evaluate_story_segment_rag.py` | 对指定 shadow collection 运行冻结 gold、baseline/candidate 和 go/no-go |
| `src/rag/vectorstore.py` | 使用 E 已验收的 typed schema/序列化/反序列化实现 |
| `src/rag_eval/story_segment_runner.py` | 生成逐项 numerator/denominator/baseline/candidate/delta/threshold 报告 |

D 不在后置阶段改写这些文件；若真实执行暴露产品缺陷，停止、记录新 correction gate，并退回 E 或另立受审修复，不在生产命令中打补丁。

---

## 3. D0：监督器与评测基线

### Task D0.1：升级监督器为独立 E worker

**Spec coverage:** `THREAD-P0-05` 至 `THREAD-P0-10`、`SUPERVISOR-P0-01` 至 `SUPERVISOR-P0-04`、`REVIEW-P0-01`、`REVIEW-P0-02`

**Files:**

- Modify: `config/codex-supervisor.workers.json`
- Modify: `src/codex_supervisor/contracts.py`
- Modify: `src/codex_supervisor/cli.py`
- Modify: `src/codex_supervisor/processes.py`
- Modify: `src/codex_supervisor/runner.py`
- Modify: `scripts/codex-supervisor/Start-Worker.ps1`
- Modify: `scripts/codex-supervisor/Resume-Worker.ps1`
- Modify: `scripts/codex-supervisor/Stop-Worker.ps1`
- Modify: `scripts/codex-supervisor/Watch-Worker.ps1`
- Modify: `scripts/codex-supervisor/Open-SupervisorWindows.ps1`
- Modify: `scripts/codex-supervisor/Show-Dashboard.ps1`
- Modify: `tests/test_codex_supervisor_contracts.py`
- Modify: `tests/test_codex_supervisor_cli.py`
- Modify: `tests/test_codex_supervisor_processes.py`
- Modify: `tests/test_codex_supervisor_powershell.py`
- Modify: `tests/test_codex_supervisor_e2e.py`

**Frozen interface:**

```python
SUPPORTED_WORKERS: tuple[str, ...] = ("A", "B", "C", "E")
WorkerName = Literal["A", "B", "C", "E"]

def validate_worker_name(value: object) -> WorkerName: ...
def supported_workers_json() -> dict[str, object]: ...
```

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
- E 不能映射到 C 的目录或 session。

Run RED:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py -q `
  --basetemp .pytest-story-segment-d0-supervisor-red
```

Expected: 新增 v2/E/public-worker-list 测试因当前只支持 A/B/C 而失败。

- [ ] **Step 2: 实现唯一 worker 集合和配置 v2**

只替换 worker identity/config/CLI/PowerShell 验证来源，不重构事件归约、状态语义或 token 统计。

- [ ] **Step 3: 运行 GREEN 与相邻回归**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_codex_supervisor_events.py -q `
  --basetemp .pytest-story-segment-d0-supervisor-green
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
  scripts/codex-supervisor/Start-Worker.ps1 `
  scripts/codex-supervisor/Resume-Worker.ps1 `
  scripts/codex-supervisor/Stop-Worker.ps1 `
  scripts/codex-supervisor/Watch-Worker.ps1 `
  scripts/codex-supervisor/Open-SupervisorWindows.ps1 `
  scripts/codex-supervisor/Show-Dashboard.ps1 `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py
git commit -m "feat(codex): add supervised story segment worker"
```

### Task D0.2：冻结 Story gold、等价 Atom 匹配器和阈值

**Spec coverage:** `EVALSET-P0-01` 至 `EVALSET-P0-18`、`EVAL-P0-01` 至 `EVAL-P0-03`、`GATE-P0-01` 至 `GATE-P0-06`、`REVIEW-P0-04`、`REVIEW-P0-09` 至 `REVIEW-P0-12`

**Files:**

- Create: `src/rag_eval/story_segment_baseline.py`
- Create: `scripts/capture_story_segment_baseline.py`
- Create: `tests/test_story_segment_baseline.py`
- Create: `eval/story_segment_eval.v1.jsonl`
- Create: `eval/story_segment_thresholds.v1.json`

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
  --basetemp .pytest-story-segment-baseline-red
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
  --basetemp .pytest-story-segment-baseline-green
```

Expected: exit code 0。

- [ ] **Step 6: 提交 matcher、gold 和 thresholds**

```powershell
git diff --check
git add -- `
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
- No production code change unless Task D0.2 tests reveal a separately reviewed matcher defect

- [ ] **Step 1: 验证固定依赖均已进入 main**

对 Spec 顶部每个 design dependency 执行：

```powershell
git ls-files --error-unmatch -- 'docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md'
git ls-files --error-unmatch -- 'docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md'
git log -1 --format='%H' -- 'docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md'
git log -1 --format='%H' -- 'docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md'
```

任一文件未跟踪、未合并或无法获得提交时立即停止；不得从当前未跟踪副本读取实施契约。

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
C dependency commits and sha256
gold/threshold/baseline receipt sha256
Conda interpreter/version/prefix
reranker disabled
approved branch/worktree
```

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

## 4. E 阶段监督门

### Task D1：逐 Task 接受 E0–E5

**Files:** no implementation edits in D

每个 E Task 都是阶段内的独立小门，必须按以下顺序：

1. E 在已批准文件范围内写 RED test。
2. E 报告 RED 命令和预期失败。
3. E 完成最小实现并运行阶段 GREEN。
4. E 运行该阶段规定的相邻回归。
5. E 停在 `completed_pending_review`，不提交下一阶段。
6. D 独立检查：
   - `git diff --check`
   - `git diff --name-only`
   - `git status --short`
   - 代码与 Spec contract
   - E 的测试命令
   - 真实快照证据和 protected pre/post
   - forbidden operation counters
7. D 接受后才允许精确 Task 提交。
8. 下一 Task 使用同一 E worktree；若 session 上下文过重，可在 Task 提交后新开 E session，但仍只有一个 E worker。

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

要求 E0–E5 的每个 Task 都有一个独立、可追踪提交；提交不得包含 ignored real-run outputs、原始 snapshot、pytest basetemp、supervisor state 或用户文件。

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

---

## 5. D 合并与真实向量影子构建

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

使用新 basetemp，至少包含 supervisor、build、BM25、vectorstore、request plan、route policy、retriever、budget、citations、execution、conversation、serializer、backend、SSE、frontend 和 rag_eval。

- [ ] **Step 5: 创建合并后候选产物**

在 create-new build version 下离线重建 Story structure、Segment、typed Dense JSONL 和 runtime snapshot；比较 E handoff 的 schema/config identity，允许数据 build version 变化但不允许算法身份漂移。

### Task D4：预检并执行一次 Typed Dense shadow build

**Spec coverage:** `INDEX-P0-01` 至 `INDEX-P0-06`、`DENSEUNIT-P0-01` 至 `DENSEUNIT-P0-11`、`PERF-P0-01` 至 `PERF-P0-09`、`PROVENANCE-P0-01` 至 `PROVENANCE-P0-06`

**External write authorization:** 仅本任务可调用 embedding API 和创建新 Milvus shadow collection。仍禁止 active pointer、生产激活、active collection 覆盖或删除。

- [ ] **Step 1: 固定运行身份**

```powershell
$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$RunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$RunRoot = Join-Path 'D:\1999Wiki\eval\story_segment\runs' $RunId
$ShadowCollection = "huiji_story_segment_shadow_$RunId"
```

读取合并后 handoff，固定：

- typed JSONL 路径和 SHA-256；
- typed schema SHA-256；
- row count 与 order hash；
- embedding provider/model/dimension/normalization；
- batch/retry config；
- active collection names；
- retrieval/fusion config；
- source/artifact identities。

- [ ] **Step 2: 容量与保护预检**

要求：

- shadow collection 名称不存在；
- 与所有 active/forbidden collection 名称不同；
- 目标数据库、账号和 schema 有创建权限；
- API token 可用但不写入日志；
- 预计 Dense 行数、向量字节、Milvus overhead 和峰值 staging 在预算内；
- embedding 输入无 Story Atom；
- active pointer/config hash 已捕获；
- reranker disabled。

- [ ] **Step 3: 执行 shadow build**

```powershell
& $Python scripts/build_huiji_typed_index.py `
  --handoff (Join-Path $RunRoot 'd-shadow-input.v1.json') `
  --collection-name $ShadowCollection `
  --receipt-root $RunRoot `
  --reranker-disabled
```

脚本必须：

- create-new collection；
- 按 typed retrieval-unit 顺序调用 embedding；
- 相同 query/build 输入不重复 embedding；
- 写入后验证 row count、PK uniqueness、schema 和随机/边界样本；
- 失败时保留 shadow collection 和 failure receipt，不自动 drop；
- 不改 runtime config 或 active pointer。

- [ ] **Step 4: 验证影子 collection**

检查：

```text
retrieval_unit_type counts
child/story_segment nullable invariants
vector dimension
text and metadata limits
row count
primary-key uniqueness
artifact identity
collection schema SHA-256
active collection unchanged
```

- [ ] **Step 5: 保存 build receipt**

Receipt 记录 API call/batch/retry/token-safe timing、row counts、collection schema、typed input identity、失败/成功状态和 protected post。

### Task D5：运行真实评测并生成 go/no-go

**Spec coverage:** 全部 `EVAL-*`、`EVALSET-*`、`GATE-*`、`PERF-*`、`ANSWER-*`、`QUALITY-*`，以及第 26.1 节全部阈值

- [ ] **Step 1: 运行 candidate retrieval**

```powershell
& $Python scripts/evaluate_story_segment_rag.py `
  --queries eval/story_segment_eval.v1.jsonl `
  --thresholds eval/story_segment_thresholds.v1.json `
  --baseline eval/story_segment_baseline_receipt.v1.json `
  --equivalence eval/story_baseline_atom_equivalence.v1.jsonl `
  --collection-name $ShadowCollection `
  --output-root $RunRoot `
  --reranker-disabled
```

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

## 6. D Plan 完成标准

1. 监督器 v2 由单一 worker 集合支持 A/B/C/E，A/B/C 状态兼容且 E 完全隔离。
2. E 观察窗口可关闭重开，worker 继续运行并可恢复原 session。
3. Story gold、threshold、baseline matcher 和逐 Atom receipt 在 E 实现前提交冻结。
4. C 的全部依赖来自固定 main 提交；无未跟踪或 worktree 输入。
5. E worktree 从 D0 完成后的固定 main 创建。
6. E0–E5 每个 Task 由 D 独立审查后才提交和继续。
7. E handoff 的 schema、artifact、typed row、config、测试和 protected state 闭合。
8. E 不调用 embedding/Milvus；D 合并后才执行一次真实 shadow build。
9. 新 collection 使用 typed retrieval unit，不包含 Story Atom Dense 行。
10. 所有 go/no-go 指标逐项输出，不以平均分抵消硬失败。
11. Reranker 调用次数为零，质量标记不影响 P0 排序。
12. active pointer、active collection、生产配置、MinIO/MySQL 和 source snapshot 在整个流程中不变。
13. 即使结果为 go，也只进入独立激活审核，不自动发布。

---

## 7. 跨 Plan Spec 追踪

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
