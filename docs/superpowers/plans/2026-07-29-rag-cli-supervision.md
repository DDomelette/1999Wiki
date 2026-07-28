# RAG 并行 CLI 监督与源快照恢复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in thread D. Do not use `superpowers:subagent-driven-development`; this project explicitly limits the agent topology to `D → CLI A/B/C`.

**Goal:** 在 main 工作树中建立可测试、可恢复观察窗口的 Codex CLI 监督基础设施，安全恢复 2026-07-07 灰机源快照缺失文件，并为后续 A/B/C 独立 worktree 的受控执行提供门禁。

**Architecture:** 使用 `src/codex_supervisor` 实现配置、事件归约、原子状态、精确进程身份和后台 runner，使用 `scripts/codex-supervisor/*.ps1` 提供 PowerShell 操作与观察入口。CLI 工作者由 detached runner 管理，观察窗口只读取持久化状态和日志。源快照恢复使用独立的 `src/huijiwiki/snapshot_recovery.py`，按版本化 manifest 执行审计、staging、哈希验证和无覆盖恢复。

**Tech Stack:** Python 3.12、Windows PowerShell 5.1、Codex CLI 0.142.0、pytest 9.1.1、psutil 7.2.2、Git worktree、JSON/JSONL、SQLite。

## Global Constraints

- 设计源头：`docs/superpowers/specs/2026-07-29-rag-cli-supervision-design.md`。
- 代理层级严格为 `D → CLI A/B/C`；A/B/C 禁止创建子代理。
- A/B/C 固定请求 `gpt-5.6-sol`、标准速度、`workspace-write`，并显式关闭 `fast_mode` 和 `multi_agent`。
- 不设置人为 Token budget，不限制正常调查深度、测试次数或必要返工。
- D 位于 `D:\1999Wiki`；A/B/C 各自使用独立 worktree、branch 和长期 CLI session。
- 观察窗口与工作进程生命周期解耦；关闭观察窗口不得终止工作者。
- 不使用 `--dangerously-bypass-approvals-and-sandbox`。
- `data_pages.jsonl` 与 `crawl_state.sqlite` 恢复前，C 不得执行真实全量构建或媒体下载。
- 恢复只允许从已验证旧快照复制缺失文件；拒绝覆盖已有不一致目标。
- 网络抓取、批量媒体下载、MinIO/MySQL/Milvus 写入和 active pointer 切换均不属于本计划。
- 稀疏向量、VLM 图片描述和正式生产激活不属于本计划。
- 当前用户未跟踪文件 `docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md` 不得修改、暂存或提交。

---

## 1. 目标范围与 Spec 覆盖

本计划直接实现监督和恢复基础设施，并为必须在 A/B/C 独立 Spec/Plan 中落实的跨线程条款建立启动门禁：

| 模块 | Spec 条目 |
|---|---|
| 两层监督 | `SUP-P0-01` 至 `SUP-P0-03` |
| worktree 契约 | `WT-P0-01` 至 `WT-P0-05` |
| CLI 配置 | `CLI-P0-01` 至 `CLI-P0-06` |
| 可观察性 | `OBS-P0-01` 至 `OBS-P0-08` |
| 文档门禁 | `DOC-P0-01` 至 `DOC-P0-06` |
| 文件恢复 | `REC-P0-01` 至 `REC-P0-08` |
| 公共契约门禁 | `CONTRACT-P0-01` 至 `CONTRACT-P0-04` |
| 外部操作门禁 | `DATA-P0-01` 至 `DATA-P0-05` |
| 运行与返工 | `RUN-P0-01` 至 `RUN-P0-05` |
| 合并与集成 | `INT-P0-01` 至 `INT-P0-04` |

本计划不会实现 A/B/C 线程的业务代码。A/B/C Spec 经用户批准后，各 CLI 只在自己的 worktree 中编写 Plan；D 审核 Plan 后才另行授权实施。

### 1.1 完整追踪矩阵

| Spec 条目 | 本计划落点 |
|---|---|
| `SUP-P0-01`、`SUP-P0-02`、`SUP-P0-03` | Task 1 固定配置；Task 4 启动门禁；Task 9 验证实际拓扑 |
| `WT-P0-01`、`WT-P0-02`、`WT-P0-03`、`WT-P0-04`、`WT-P0-05` | Task 1 固定 worktree 契约；Task 9 创建并验证隔离工作树 |
| `CLI-P0-01`、`CLI-P0-02`、`CLI-P0-03`、`CLI-P0-04`、`CLI-P0-05`、`CLI-P0-06` | Task 1 参数契约；Task 3 runner；Task 4 start/resume；Task 9 真实启动检查 |
| `OBS-P0-01`、`OBS-P0-02`、`OBS-P0-03`、`OBS-P0-04`、`OBS-P0-05`、`OBS-P0-06`、`OBS-P0-07`、`OBS-P0-08` | Task 2 至 Task 5；Task 8 运行手册 |
| `DOC-P0-01`、`DOC-P0-02`、`DOC-P0-03`、`DOC-P0-04`、`DOC-P0-05`、`DOC-P0-06` | Task 8 记录审核方式；Task 9 只下发 Plan 编写任务；第 5 节审核矩阵 |
| `REC-P0-01`、`REC-P0-02`、`REC-P0-03`、`REC-P0-04`、`REC-P0-05`、`REC-P0-07`、`REC-P0-08` | Task 6 恢复工具；Task 7 真实恢复和 receipt |
| `REC-P0-06` | Task 6/7 识别唯一 invalid wrapper；Task 9 强制 C Plan 实现 excluded evidence 测试 |
| `CONTRACT-P0-01`、`CONTRACT-P0-02`、`CONTRACT-P0-03`、`CONTRACT-P0-04` | Task 9 的 A/B/C Spec 前置门禁；第 5 节拒绝未冻结或跨 worktree 契约 |
| `DATA-P0-01`、`DATA-P0-02`、`DATA-P0-03`、`DATA-P0-04`、`DATA-P0-05` | Task 6/7 区分只读审计与恢复审批；Task 9 要求 C Plan 保留容量与外部写门禁 |
| `RUN-P0-01`、`RUN-P0-02`、`RUN-P0-03`、`RUN-P0-04`、`RUN-P0-05` | Task 2 至 Task 5；Task 8 回归；Task 9 plan-only 监督 |
| `INT-P0-01`、`INT-P0-02`、`INT-P0-03`、`INT-P0-04` | Task 9 保持分支隔离；第 6 节冻结合并、冲突和不激活规则 |

## 2. 文件结构

### 2.1 新建

```text
config/codex-supervisor.workers.json
config/recovery/huiji-res1999-20260707.json

src/codex_supervisor/__init__.py
src/codex_supervisor/contracts.py
src/codex_supervisor/events.py
src/codex_supervisor/state_store.py
src/codex_supervisor/processes.py
src/codex_supervisor/runner.py
src/codex_supervisor/cli.py

src/huijiwiki/snapshot_recovery.py

scripts/codex_supervisor.py
scripts/recover_huiji_snapshot.py

scripts/codex-supervisor/Start-Worker.ps1
scripts/codex-supervisor/Stop-Worker.ps1
scripts/codex-supervisor/Resume-Worker.ps1
scripts/codex-supervisor/Watch-Worker.ps1
scripts/codex-supervisor/Show-Dashboard.ps1
scripts/codex-supervisor/Open-SupervisorWindows.ps1
scripts/codex-supervisor/schemas/worker-final.schema.json

tests/fixtures/codex_supervisor/fake_codex.py
tests/fixtures/codex_supervisor/events-success.jsonl
tests/fixtures/codex_supervisor/events-failure.jsonl
tests/test_codex_supervisor_contracts.py
tests/test_codex_supervisor_events.py
tests/test_codex_supervisor_processes.py
tests/test_codex_supervisor_cli.py
tests/test_codex_supervisor_powershell.py
tests/test_codex_supervisor_e2e.py
tests/test_huiji_snapshot_recovery.py

docs/codex/cli-supervisor-runbook.md
```

### 2.2 修改

```text
.gitignore
```

`.gitignore` 只新增：

```gitignore
.codex-supervisor/
```

不修改运行时依赖锁。`psutil` 已存在于 `requirements/dev.in` 和 `requirements/dev.lock.txt`，监督脚本使用当前项目开发环境。

## 3. 强制验收门槛

### Gate D0：代码前置

- main HEAD 包含已批准总体 Spec。
- 工作区除已知蓝绿计划文件外无意外变更。
- `codex --version` 可运行。
- `gpt-5.6-sol` 可用性在真实 worker 启动前验证。
- Windows PowerShell 5.1 可运行。

### Gate D1：监督核心

- 单元测试覆盖状态、事件、进程身份和参数构造。
- 假 Codex E2E 证明启动 PowerShell 返回后 worker 仍运行。
- 关闭观察器不改变 worker PID 和 create time。
- 重开观察器能看到历史尾部和新事件。
- 精确停止拒绝 PID 复用或命令漂移。

### Gate D2：恢复工具

- dry-run 不写目标。
- staging 文件哈希不一致时不发布。
- 已有一致目标视为幂等成功。
- 已有不一致目标硬失败且不覆盖。
- 中途失败后可安全重跑。

### Gate D3：真实恢复

- 用户在 Plan 审核后另行授权执行恢复动作。
- `data_pages.jsonl` 恢复为 581,887,494 字节、72,848 行和固定 SHA-256。
- `crawl_state.sqlite` 恢复为 47,710,208 字节和固定 SHA-256。
- 仓库 verifier 返回 `ok: true`、零错误、零警告。
- 恢复 receipt 写入本地监督目录。

### Gate D4：工作树调度

- A/B/C 独立 Spec 均已获用户批准。
- 三个 worktree 从同一个批准后的 main commit 创建。
- 三个 worker 首轮只获授权编写自己的 Plan。
- D 审核通过前不能进入实现状态。

## 4. 执行任务

### Task 1：冻结监督配置、状态契约和最终报告 Schema

**对应 Specs:** `SUP-P0-01`、`SUP-P0-02`、`WT-P0-01` 至 `WT-P0-05`、`CLI-P0-01` 至 `CLI-P0-06`、`RUN-P0-01`

**Files:**

- Create: `config/codex-supervisor.workers.json`
- Create: `src/codex_supervisor/__init__.py`
- Create: `src/codex_supervisor/contracts.py`
- Create: `scripts/codex-supervisor/schemas/worker-final.schema.json`
- Create: `tests/test_codex_supervisor_contracts.py`
- Modify: `.gitignore`

**Interfaces:**

- Produces: `WorkerName`, `WorkerPhase`, `WorkerStatus`, `UsageTotals`, `WorkerConfig`, `WorkerState`
- Produces: `load_supervisor_config(project_root: Path) -> SupervisorConfig`
- Produces: `build_codex_base_args(config: WorkerConfig, final_schema: Path) -> tuple[str, ...]`
- Consumes later: `events.py`, `state_store.py`, `processes.py`, `runner.py`, `cli.py`

- [ ] **Step 1：编写失败的配置与状态契约测试**

在 `tests/test_codex_supervisor_contracts.py` 覆盖：

```python
from pathlib import Path

import pytest

from src.codex_supervisor.contracts import (
    UsageTotals,
    WorkerState,
    build_codex_base_args,
    load_supervisor_config,
)


def test_worker_config_enforces_two_layers_and_standard_speed(tmp_path: Path) -> None:
    config = load_supervisor_config(Path.cwd())
    worker = config.workers["A"]
    args = build_codex_base_args(
        worker,
        Path("scripts/codex-supervisor/schemas/worker-final.schema.json"),
    )

    assert args[:2] == ("codex", "exec")
    assert ("-m", "gpt-5.6-sol") == args[2:4]
    assert "--disable" in args
    assert "fast_mode" in args
    assert "multi_agent" in args
    assert ("--sandbox", "workspace-write") in tuple(zip(args, args[1:]))
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    assert worker.allow_subagents is False


def test_worker_state_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unsupported worker status"):
        WorkerState.initial("A").with_status("invented")


def test_usage_totals_accumulate_cached_and_reasoning_tokens() -> None:
    usage = UsageTotals().add(
        input_tokens=100,
        cached_input_tokens=60,
        output_tokens=20,
        reasoning_output_tokens=8,
    )
    assert usage.to_json() == {
        "input_tokens": 100,
        "cached_input_tokens": 60,
        "output_tokens": 20,
        "reasoning_output_tokens": 8,
    }
```

- [ ] **Step 2：运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_codex_supervisor_contracts.py -q
```

Expected: FAIL，提示 `src.codex_supervisor` 不存在。

- [ ] **Step 3：实现配置与状态契约**

`config/codex-supervisor.workers.json` 固定以下语义：

```json
{
  "schema_version": "codex-supervisor/v1",
  "runtime_root": ".codex-supervisor",
  "model": "gpt-5.6-sol",
  "sandbox": "workspace-write",
  "fast_mode": false,
  "multi_agent": false,
  "workers": {
    "A": {
      "branch": "codex/rag-a-routing",
      "worktree": "../1999Wiki.worktrees/rag-a-routing"
    },
    "B": {
      "branch": "codex/rag-b-bm25",
      "worktree": "../1999Wiki.worktrees/rag-b-bm25"
    },
    "C": {
      "branch": "codex/rag-c-projection",
      "worktree": "../1999Wiki.worktrees/rag-c-projection"
    }
  }
}
```

`WorkerState` 必须显式支持：

```python
ALLOWED_STATUSES = (
    "planning",
    "awaiting_plan_review",
    "approved",
    "running",
    "testing",
    "needs_approval",
    "blocked",
    "failed",
    "completed_pending_review",
    "accepted",
)
```

`build_codex_base_args()` 必须生成：

```text
codex exec
-m gpt-5.6-sol
--disable fast_mode
--disable multi_agent
--sandbox workspace-write
--json
--output-schema $StatusSchema
--cd $Worktree
```

最终报告 Schema 必须要求：

```text
status
phase
summary
files_changed
tests_run
tests_passed
blockers
needs_approval
last_commit
next_action
```

- [ ] **Step 4：加入运行目录忽略规则**

仅向 `.gitignore` 加入 `.codex-supervisor/`。运行：

```powershell
git diff -- .gitignore
```

Expected: 只有一条新忽略规则，无其他数据目录规则变化。

- [ ] **Step 5：运行契约测试**

Run:

```powershell
python -m pytest tests/test_codex_supervisor_contracts.py -q
```

Expected: PASS。

- [ ] **Step 6：提交**

```powershell
git add .gitignore config/codex-supervisor.workers.json src/codex_supervisor/__init__.py src/codex_supervisor/contracts.py scripts/codex-supervisor/schemas/worker-final.schema.json tests/test_codex_supervisor_contracts.py
git commit -m "feat: define Codex supervisor contracts"
```

### Task 2：实现原子状态存储和 Codex JSONL 事件归约

**对应 Specs:** `OBS-P0-03`、`OBS-P0-05` 至 `OBS-P0-07`、`RUN-P0-01` 至 `RUN-P0-05`

**Files:**

- Create: `src/codex_supervisor/events.py`
- Create: `src/codex_supervisor/state_store.py`
- Create: `tests/fixtures/codex_supervisor/events-success.jsonl`
- Create: `tests/fixtures/codex_supervisor/events-failure.jsonl`
- Create: `tests/test_codex_supervisor_events.py`

**Interfaces:**

- Consumes: `WorkerState`, `UsageTotals`
- Produces: `apply_event(state: WorkerState, event: Mapping[str, Any]) -> WorkerState`
- Produces: `AtomicStateStore.read(worker: WorkerName) -> WorkerState`
- Produces: `AtomicStateStore.write(state: WorkerState) -> None`
- Produces: `append_event(worker: WorkerName, raw_line: str) -> None`
- Test helper: `reduce_fixture(worker: WorkerName, filename: str) -> WorkerState`

- [ ] **Step 1：编写事件归约失败测试**

成功 fixture 至少包含：

```json
{"type":"thread.started","thread_id":"thread-a"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"cmd-1","type":"command_execution","command":"python -m pytest tests/test_x.py -q"}}
{"type":"item.completed","item":{"id":"cmd-1","type":"command_execution","exit_code":0,"aggregated_output":"2 passed"}}
{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":700,"output_tokens":200,"reasoning_output_tokens":80}}
```

失败 fixture 至少包含：

```json
{"type":"thread.started","thread_id":"thread-c"}
{"type":"turn.started"}
{"type":"turn.failed","error":{"message":"source snapshot missing"}}
```

测试：

```python
def test_success_events_capture_session_action_test_and_usage() -> None:
    state = reduce_fixture("A", "events-success.jsonl")
    assert state.session_id == "thread-a"
    assert state.current_action == "python -m pytest tests/test_x.py -q"
    assert state.tests_summary == "2 passed"
    assert state.usage.cached_input_tokens == 700
    assert state.status == "completed_pending_review"


def test_failure_event_preserves_public_error_without_traceback() -> None:
    state = reduce_fixture("C", "events-failure.jsonl")
    assert state.status == "failed"
    assert state.blocker == "source snapshot missing"
    assert "Traceback" not in json.dumps(state.to_public_json())
```

- [ ] **Step 2：编写原子状态测试**

覆盖：

- 写入使用同目录临时文件和 `os.replace()`；
- JSON 序列化失败不破坏已有 `state.json`；
- 读取不存在状态时返回明确错误；
- A/B/C 路径严格隔离；
- raw JSONL 与 public state 分开保存；
- 重复 `turn.completed` 事件不会把同一 usage 累加两次。

- [ ] **Step 3：运行测试确认失败**

```powershell
python -m pytest tests/test_codex_supervisor_events.py -q
```

Expected: FAIL，缺少 `events.py` 和 `state_store.py`。

- [ ] **Step 4：实现事件归约**

只消费已知字段。未知事件原样写入 JSONL，但不得使 runner 失败。事件到状态的核心映射：

| 事件 | 状态变化 |
|---|---|
| `thread.started` | 写入 `session_id` |
| `turn.started` | `status=running` |
| command `item.started` | 更新 `current_action` |
| command `item.completed` | 更新退出码和测试摘要 |
| agent message completed | 更新短摘要，不覆盖原始日志 |
| `turn.completed` | 累加 usage；若结构化最终报告没有更具体状态，则进入 `completed_pending_review` |
| `turn.failed` | `failed` 并保存公开错误 |
| `error` | 记录错误；是否终止由 runner 决定 |

usage 去重键使用：

```python
(session_id, turn_ordinal, event_ordinal)
```

状态中只保存累计值和已消费事件游标，不保存隐藏推理内容。

- [ ] **Step 5：实现原子存储**

运行目录：

```text
.codex-supervisor/workers/A/state.json
.codex-supervisor/logs/A.events.jsonl
.codex-supervisor/logs/A.stderr.log
.codex-supervisor/sessions/A.json
.codex-supervisor/locks/A.lock
```

临时状态文件命名为 `state.json.$PID.tmp`，写入、flush、`os.fsync()` 后执行 `os.replace()`。

- [ ] **Step 6：运行事件测试**

```powershell
python -m pytest tests/test_codex_supervisor_contracts.py tests/test_codex_supervisor_events.py -q
```

Expected: PASS。

- [ ] **Step 7：提交**

```powershell
git add src/codex_supervisor/events.py src/codex_supervisor/state_store.py tests/fixtures/codex_supervisor/events-success.jsonl tests/fixtures/codex_supervisor/events-failure.jsonl tests/test_codex_supervisor_events.py
git commit -m "feat: persist Codex worker event state"
```

### Task 3：实现精确后台进程身份和 worker runner

**对应 Specs:** `OBS-P0-01`、`OBS-P0-02`、`OBS-P0-04`、`CLI-P0-04`、`CLI-P0-05`、`RUN-P0-02`

**Files:**

- Create: `src/codex_supervisor/processes.py`
- Create: `src/codex_supervisor/runner.py`
- Create: `tests/fixtures/codex_supervisor/fake_codex.py`
- Create: `tests/test_codex_supervisor_processes.py`

**Interfaces:**

- Consumes: `WorkerConfig`, `WorkerState`, `AtomicStateStore`, `apply_event`
- Produces: `ProcessIdentity`
- Produces: `ProcessSnapshot`
- Produces: `RunnerRequest`
- Produces: `validate_process_identity(identity: ProcessIdentity, observed: ProcessSnapshot) -> None`
- Produces: `windows_detach_flags() -> int`
- Produces: `inspect_owned_process(identity: ProcessIdentity) -> psutil.Process`
- Produces: `start_detached_runner(request: RunnerRequest) -> ProcessIdentity`
- Produces: `stop_owned_worker(identity: ProcessIdentity, timeout_seconds: float) -> None`
- Produces: `run_worker(request: RunnerRequest) -> int`

- [ ] **Step 1：编写进程身份失败测试**

复用 `src/huiji_rag/backend_process.py` 的安全模式，但不要让 supervisor 依赖激活模块。

测试覆盖：

```python
def test_process_identity_rejects_pid_reuse() -> None:
    identity = ProcessIdentity(
        pid=42,
        create_time=100.0,
        executable="python.exe",
        cwd="D:/worktree",
        argv=("python.exe", "runner.py", "--worker", "A"),
        worker="A",
        role="runner",
    )
    observed = ProcessSnapshot(
        pid=42,
        create_time=101.0,
        executable="python.exe",
        cwd="D:/worktree",
        argv=("python.exe", "runner.py", "--worker", "A"),
    )
    with pytest.raises(RuntimeError, match="PID was reused"):
        validate_process_identity(identity, observed)


def test_stop_refuses_command_or_worktree_drift() -> None:
    identity = ProcessIdentity(
        pid=42,
        create_time=100.0,
        executable="codex.exe",
        cwd="D:/1999Wiki.worktrees/rag-a-routing",
        argv=("codex.exe", "exec", "-m", "gpt-5.6-sol"),
        worker="A",
        role="codex",
    )
    observed = ProcessSnapshot(
        pid=42,
        create_time=100.0,
        executable="codex.exe",
        cwd="D:/1999Wiki.worktrees/rag-b-bm25",
        argv=("codex.exe", "exec", "-m", "gpt-5.6-sol"),
    )
    with pytest.raises(RuntimeError, match="working directory drifted"):
        validate_process_identity(identity, observed)


def test_detached_runner_uses_no_stdin_and_windows_detach_flags() -> None:
    flags = windows_detach_flags()
    assert flags & subprocess.CREATE_NEW_PROCESS_GROUP
    assert flags & subprocess.DETACHED_PROCESS
    assert flags & subprocess.CREATE_NO_WINDOW
```

必须断言 Windows flags 包含：

```python
subprocess.CREATE_NEW_PROCESS_GROUP
subprocess.DETACHED_PROCESS
subprocess.CREATE_NO_WINDOW
```

- [ ] **Step 2：编写假 Codex runner 测试**

`fake_codex.py` 接受与真实命令相似的参数，逐行输出成功 fixture，并支持：

```text
--fake-delay-seconds
--fake-exit-code
--fake-session-id
--fake-wait-file
```

测试证明：

- runner 逐行写事件，不等进程退出才写；
- stderr 独立保存；
- stdin 是 `DEVNULL`；
- runner 将 child PID 和自身 PID 都写入 session identity；
- child 异常退出进入 `failed`；
- 已存在有效 worker 时拒绝重复启动；
- lock 的所有者已不存在时可以安全回收；
- 停止顺序为 child 后 runner；
- child 已自然结束时 stop 为幂等成功。

- [ ] **Step 3：运行测试确认失败**

```powershell
python -m pytest tests/test_codex_supervisor_processes.py -q
```

Expected: FAIL，缺少进程与 runner 模块。

- [ ] **Step 4：实现 ProcessIdentity**

身份至少保存：

```text
pid
create_time
executable
cwd
argv
worker
role: runner | codex
```

验证顺序：

1. PID 存在；
2. create time 误差不超过 0.01 秒；
3. executable basename 符合已记录值；
4. cwd 等于精确 worktree；
5. argv 包含该 worker 允许的 branch/worktree/model/feature 参数；
6. 只有全部一致才允许停止。

- [ ] **Step 5：实现 detached runner**

PowerShell 启动命令只启动 runner。runner 再启动 Codex child：

```python
process = subprocess.Popen(
    argv,
    cwd=worker.worktree,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=stderr_file,
    text=True,
    encoding="utf-8",
    errors="replace",
    shell=False,
    creationflags=codex_creationflags(),
)
```

runner 对 stdout 每一行执行：

1. 追加 raw JSONL；
2. 尝试解析；
3. 更新 state；
4. flush；
5. 未知或格式错误行记录诊断但不中断后续事件。

- [ ] **Step 6：运行进程测试**

```powershell
python -m pytest tests/test_codex_supervisor_processes.py tests/test_codex_supervisor_events.py -q
```

Expected: PASS。

- [ ] **Step 7：提交**

```powershell
git add src/codex_supervisor/processes.py src/codex_supervisor/runner.py tests/fixtures/codex_supervisor/fake_codex.py tests/test_codex_supervisor_processes.py
git commit -m "feat: run exact detached Codex workers"
```

### Task 4：实现 supervisor CLI 和 PowerShell 操作入口

**对应 Specs:** `OBS-P0-03`、`OBS-P0-04`、`OBS-P0-08`、`CLI-P0-05`、`RUN-P0-03` 至 `RUN-P0-05`

**Files:**

- Create: `src/codex_supervisor/cli.py`
- Create: `scripts/codex_supervisor.py`
- Create: `scripts/codex-supervisor/Start-Worker.ps1`
- Create: `scripts/codex-supervisor/Stop-Worker.ps1`
- Create: `scripts/codex-supervisor/Resume-Worker.ps1`
- Create: `tests/test_codex_supervisor_cli.py`
- Create: `tests/test_codex_supervisor_powershell.py`

**Interfaces:**

- Produces CLI: `start`, `resume`, `stop`, `status`, `inspect`, `accept`
- Produces: `build_resume_args(config: WorkerConfig, session_id: str, prompt: str, final_schema: Path) -> tuple[str, ...]`
- PowerShell consumes Python CLI only；PowerShell 不复制业务逻辑
- Test helpers: `invoke_cli(argv: list[str]) -> CliResult`、`write_session(runtime: Path, worker: str, session_id: str, status: str) -> None`

- [ ] **Step 1：编写 CLI 参数与门禁失败测试**

覆盖：

- worker 只能是 A/B/C；
- start 必须提供已批准任务文件；
- task 文件必须位于 `.codex-supervisor/workers/A|B|C/approved-task.md` 对应的精确 worker 目录；
- task 文件必须包含 Spec 路径、Plan 路径、允许文件和禁止子代理声明；
- resume 必须读取已有 session ID；
- stop 必须提供精确 worker，不支持 `all`；
- accept 只能从 `completed_pending_review` 转为 `accepted`；
- CLI 不接受任意 `--model`、`--sandbox` 或 bypass 参数覆盖。

示例：

```python
def test_start_rejects_unapproved_prompt_path(tmp_path: Path) -> None:
    result = invoke_cli(["start", "--worker", "A", "--task-file", str(tmp_path / "free.txt")])
    assert result.exit_code == 2
    assert "approved-task.md" in result.stderr


def test_resume_uses_recorded_session_and_standard_flags(fake_runtime: Path) -> None:
    write_session(
        fake_runtime,
        worker="A",
        session_id="thread-a",
        status="failed",
    )
    config = load_supervisor_config(Path.cwd())
    argv = build_resume_args(
        config=config.workers["A"],
        session_id="thread-a",
        prompt="修复已批准的测试失败",
        final_schema=Path("scripts/codex-supervisor/schemas/worker-final.schema.json"),
    )
    assert argv[:3] == ("codex", "exec", "resume")
    assert "thread-a" in argv
    assert "--disable" in argv
    assert "multi_agent" in argv
```

- [ ] **Step 2：编写 PowerShell 静态测试**

`tests/test_codex_supervisor_powershell.py` 检查：

- 每个脚本以 `$ErrorActionPreference = "Stop"` 开始；
- 使用 `$PSScriptRoot` 解析仓库路径；
- 参数包含 `[ValidateSet("A", "B", "C")]`；
- 不包含密码、cookie、API key；
- 不调用 `taskkill`；
- 不使用 `danger-full-access`；
- `Start-Worker.ps1` 和 `Resume-Worker.ps1` 不等待 Codex 完成；
- `Stop-Worker.ps1` 不支持无目标批量终止；
- Unicode 和空格路径通过数组参数传递，不拼接 shell 命令字符串。

- [ ] **Step 3：运行测试确认失败**

```powershell
python -m pytest tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_powershell.py -q
```

Expected: FAIL，CLI 和脚本不存在。

- [ ] **Step 4：实现 Python CLI**

`scripts/codex_supervisor.py` 只负责把项目根加入 `sys.path` 并调用：

```python
from src.codex_supervisor.cli import main

raise SystemExit(main())
```

`start` 执行：

1. 读取配置；
2. 验证 branch/worktree；
3. 验证任务文件；
4. 验证没有活动 worker；
5. 启动 detached runner；
6. 输出 runner PID、状态文件和观察命令；
7. 立即返回。

`resume` 执行：

1. 验证原 worker 已停止；
2. 读取 session ID；
3. 读取批准的修订指令文件；
4. 使用 `codex exec resume $SessionId`；
5. 继续累计相同 worker 的 usage 和日志 segment。

`stop` 执行：

1. 读取双进程身份；
2. 验证 child；
3. 终止 child 并等待；
4. 验证 runner；
5. 终止 runner并等待；
6. 更新 `blocked` 或显式 stopped 诊断，不伪装为完成。

- [ ] **Step 5：实现 PowerShell 薄入口**

以 `Start-Worker.ps1` 为例：

```powershell
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Worker
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$TaskFile = Join-Path $ProjectRoot ".codex-supervisor\\workers\\$Worker\\approved-task.md"
& $Python (Join-Path $ProjectRoot "scripts\\codex_supervisor.py") start --worker $Worker --task-file $TaskFile
exit $LASTEXITCODE
```

实际实现使用与 `crawl_huiji_res1999.ps1` 相同的可移植 Python 发现顺序：

1. `CODEX_SUPERVISOR_PYTHON`；
2. `py.exe -3.12-64`；
3. PATH 中的 `python.exe`。

- [ ] **Step 6：运行 CLI 与 PowerShell 测试**

```powershell
python -m pytest tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_powershell.py -q
```

Expected: PASS。

- [ ] **Step 7：提交**

```powershell
git add src/codex_supervisor/cli.py scripts/codex_supervisor.py scripts/codex-supervisor/Start-Worker.ps1 scripts/codex-supervisor/Stop-Worker.ps1 scripts/codex-supervisor/Resume-Worker.ps1 tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_powershell.py
git commit -m "feat: control Codex workers from PowerShell"
```

### Task 5：实现可重开观察器、D Dashboard 和完整假进程 E2E

**对应 Specs:** `OBS-P0-01` 至 `OBS-P0-08`

**Files:**

- Create: `scripts/codex-supervisor/Watch-Worker.ps1`
- Create: `scripts/codex-supervisor/Show-Dashboard.ps1`
- Create: `scripts/codex-supervisor/Open-SupervisorWindows.ps1`
- Modify: `src/codex_supervisor/cli.py`
- Create: `tests/test_codex_supervisor_e2e.py`
- Modify: `tests/test_codex_supervisor_cli.py`
- Modify: `tests/test_codex_supervisor_powershell.py`

**Interfaces:**

- Consumes CLI: `status --worker`
- Produces CLI: `watch --worker --tail 50`、`dashboard --watch`
- Produces exact user commands frozen by `OBS-P0-08`
- Test helpers: `start_fake_worker()`、`inspect_identity()`、`run_observer()`、`append_fake_event()`、`release_fake_worker()`

- [ ] **Step 1：编写观察器失败测试**

使用 fake Codex 的 wait-file 模式：

```python
def test_observer_can_exit_without_stopping_worker(tmp_path: Path) -> None:
    worker = start_fake_worker(tmp_path, worker="A", wait=True)
    before = inspect_identity(worker)

    observer = subprocess.Popen(
        powershell_watch_args("A", once=True),
        stdout=subprocess.PIPE,
        text=True,
    )
    observer.wait(timeout=10)

    after = inspect_identity(worker)
    assert after.pid == before.pid
    assert after.create_time == before.create_time
    release_fake_worker(tmp_path, "A")


def test_reopened_observer_prints_history_then_new_event(tmp_path: Path) -> None:
    worker = start_fake_worker(tmp_path, worker="A", wait=True)
    first_output = run_observer(tmp_path, worker="A", once=True)
    append_fake_event(
        tmp_path,
        worker="A",
        event={
            "type": "item.started",
            "item": {
                "id": "cmd-2",
                "type": "command_execution",
                "command": "python -m pytest tests/test_x.py -q",
            },
        },
    )
    reopened_output = run_observer(tmp_path, worker="A", once=True)
    release_fake_worker(tmp_path, "A")
    assert "thread.started" in first_output
    assert "thread.started" in reopened_output
    assert "python -m pytest" in reopened_output
```

Dashboard 测试必须证明 A/B/C 状态来自三个独立 state 文件，按固定顺序展示，缺少某一 worker 状态时显示 `not_started` 而不是报错。

- [ ] **Step 2：运行测试确认失败**

```powershell
python -m pytest tests/test_codex_supervisor_e2e.py -q
```

Expected: FAIL，观察器不存在。

- [ ] **Step 3：实现单 worker 观察器**

`Watch-Worker.ps1`：

- 默认先显示最近 50 条人类可读事件；
- 随后每 500ms 读取新增状态；
- 标题固定为 `Codex Worker A/B/C - Observer Only`；
- 明确显示“关闭本窗口不会停止 worker”；
- `Ctrl+C` 只退出观察器；
- `-Once` 供测试和一次性查看；
- 状态文件暂时不存在时显示 `not_started` 并继续等待；
- 不持有 worker lock。

- [ ] **Step 4：实现 Dashboard**

`Show-Dashboard.ps1` 每秒刷新：

```text
Worker  Branch                 Phase      Status       Tests       Tokens  Elapsed
A       codex/rag-a-routing    planning   running      -           1,280   00:03:18
B       codex/rag-b-bm25       testing    running      25/27       9,420   00:41:06
C       codex/rag-c-projection recovery   blocked      -           4,012   00:19:45
```

Token 默认显示：

```text
input + output + reasoning_output
```

同时单列 cached input；不得把 cached tokens 从 usage 中删除或误报为零。

- [ ] **Step 5：实现一次打开全部窗口**

`Open-SupervisorWindows.ps1` 使用显式可见窗口：

```powershell
Start-Process powershell.exe -ArgumentList $AArgs
Start-Process powershell.exe -ArgumentList $BArgs
Start-Process powershell.exe -ArgumentList $CArgs
Start-Process powershell.exe -ArgumentList $DashboardArgs
```

每组参数使用字符串数组，不构造可执行命令字符串。打开窗口失败时报告精确 worker；已经打开的其他窗口不关闭。

- [ ] **Step 6：运行 E2E**

```powershell
python -m pytest tests/test_codex_supervisor_e2e.py tests/test_codex_supervisor_powershell.py -q
```

Expected: PASS，测试结束后不存在 fake worker 遗留进程。

- [ ] **Step 7：提交**

```powershell
git add src/codex_supervisor/cli.py scripts/codex-supervisor/Watch-Worker.ps1 scripts/codex-supervisor/Show-Dashboard.ps1 scripts/codex-supervisor/Open-SupervisorWindows.ps1 tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_e2e.py tests/test_codex_supervisor_powershell.py
git commit -m "feat: observe Codex workers without owning them"
```

### Task 6：实现可审计、无覆盖的灰机源快照恢复工具

**对应 Specs:** `REC-P0-01` 至 `REC-P0-08`、`DATA-P0-01`、`DATA-P0-02`

**Files:**

- Create: `config/recovery/huiji-res1999-20260707.json`
- Create: `src/huijiwiki/snapshot_recovery.py`
- Create: `scripts/recover_huiji_snapshot.py`
- Create: `tests/test_huiji_snapshot_recovery.py`

**Interfaces:**

- Produces: `SnapshotManifest`
- Produces: `audit_snapshot(source_root: Path, target_root: Path, manifest: SnapshotManifest) -> RecoveryAudit`
- Produces: `recover_missing_files(audit: RecoveryAudit, receipt_path: Path) -> RecoveryReceipt`
- CLI defaults to audit-only；`--apply` 才允许复制
- Test helper: `RecoveryFixture` 和 `make_recovery_fixture(tmp_path: Path) -> RecoveryFixture`

- [ ] **Step 1：编写 manifest**

`config/recovery/huiji-res1999-20260707.json` 固定：

```json
{
  "schema_version": "huiji-source-recovery/v1",
  "snapshot_id": "res1999-20260707",
  "files": {
    "pages.jsonl": {
      "size": 39803538,
      "sha256": "98f24e6a674257cc5465c865cab60e0d8174104e8c14f9a4a362c9b349dd4b6b"
    },
    "wikitext.jsonl": {
      "size": 588748233,
      "sha256": "7767c589217dcde17d7a0fca3e8f6dae45e8adb46c3a6768cb81cad2493aa721"
    },
    "data_pages.jsonl": {
      "size": 581887494,
      "rows": 72848,
      "invalid_payload_rows": 1,
      "sha256": "eb82b82e34300ee5d8beb27b13311fe530c59faeba3ae7883876b74b0eab9092"
    },
    "resources_manifest.jsonl": {
      "size": 41514051,
      "sha256": "20dfc072c2099f356d6a2b4b2572691054919b83dc9cbcc058a237109d373aa6"
    },
    "siteinfo.json": {
      "size": 14763,
      "sha256": "ef0b79b127f938224a75e016fe20c5dc37b54541634f532f15e78d8af1c0290"
    },
    "crawl_state.sqlite": {
      "size": 47710208,
      "sha256": "cc34c6b701321b9fe59c3268577a334a3e092cd16190b59c28f98185a5866378"
    },
    "errors.jsonl": {
      "size": 299,
      "sha256": "79e252aed70bf122849a02751dd53dfe1fe3c6cbfd3223ea3abd19651d209e07"
    }
  },
  "recover": [
    "data_pages.jsonl",
    "crawl_state.sqlite"
  ]
}
```

- [ ] **Step 2：编写恢复失败测试**

使用小型 fixture 动态生成 manifest，不复制真实大文件。至少覆盖：

```python
def test_audit_only_does_not_create_target(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    audit = audit_snapshot(
        fixture.source,
        fixture.target,
        fixture.manifest,
    )
    assert audit.status == "ready"
    assert not (fixture.target / "data_pages.jsonl").exists()


def test_apply_recovers_only_manifest_recover_files(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    existing_sibling = fixture.target / "pages.jsonl"
    original_mtime_ns = existing_sibling.stat().st_mtime_ns
    source_bytes = (fixture.source / "data_pages.jsonl").read_bytes()
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    recover_missing_files(audit, fixture.receipt)
    assert (fixture.target / "data_pages.jsonl").read_bytes() == source_bytes
    assert (fixture.target / "crawl_state.sqlite").exists()
    assert existing_sibling.stat().st_mtime_ns == original_mtime_ns


def test_mismatched_existing_target_is_never_overwritten(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    target_file = fixture.target / "data_pages.jsonl"
    target_file.write_bytes(b"user data")
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    with pytest.raises(RuntimeError, match="target mismatch"):
        recover_missing_files(audit, fixture.receipt)
    assert target_file.read_bytes() == b"user data"


def test_staging_hash_mismatch_never_publishes(monkeypatch, tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)

    def corrupt_copy(source: Path, staging: Path) -> None:
        staging.write_bytes(b"corrupt")

    monkeypatch.setattr(recovery, "_copy_to_staging", corrupt_copy)
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    with pytest.raises(RuntimeError, match="staging hash mismatch"):
        recover_missing_files(audit, fixture.receipt)
    assert not (fixture.target / "data_pages.jsonl").exists()


def test_partial_previous_success_is_idempotent(tmp_path: Path) -> None:
    fixture = make_recovery_fixture(tmp_path)
    shutil.copyfile(
        fixture.source / "data_pages.jsonl",
        fixture.target / "data_pages.jsonl",
    )
    audit = audit_snapshot(fixture.source, fixture.target, fixture.manifest)
    receipt = recover_missing_files(audit, fixture.receipt)
    assert receipt.files["data_pages.jsonl"].status == "already_present"
    assert receipt.files["crawl_state.sqlite"].status == "recovered"
```

SQLite fixture 创建：

```python
with sqlite3.connect(source / "crawl_state.sqlite") as connection:
    connection.execute("CREATE TABLE crawl_runs (id INTEGER PRIMARY KEY)")
```

并验证恢复后 `PRAGMA quick_check` 返回 `ok`。

测试 fixture 的 `data_pages.jsonl` 必须包含一条顶层 JSONL 合法但 `json_valid=false` 的 crawler wrapper。audit 只统计并报告该行，不把其 `content` 当成可投影 JSON。

- [ ] **Step 3：运行测试确认失败**

```powershell
python -m pytest tests/test_huiji_snapshot_recovery.py -q
```

Expected: FAIL，恢复模块不存在。

- [ ] **Step 4：实现 audit**

audit 必须：

1. resolve source 和 target；
2. 拒绝 source 与 target 相同；
3. 验证 source 所有 manifest 文件的 size 和 SHA-256；
4. 验证 target 已有同批次 sibling；
5. 将目标分为 `already_present`、`missing`、`mismatch`；
6. mismatch 存在时禁止 apply；
7. 检查 source SQLite `PRAGMA quick_check`；
8. 验证 `data_pages.jsonl` 行数和 `json_valid=false` wrapper 数量；
9. 不执行网络访问。

- [ ] **Step 5：实现 apply**

对每个 missing 文件：

1. 在目标目录内部创建 `.recovery-staging-$RecoveryId`；
2. `shutil.copyfileobj()` 复制；
3. flush 和 `os.fsync()`；
4. 验证 staged size、hash 和行数；
5. 再次确认最终目标仍不存在；
6. 使用 `os.replace()` 发布；
7. 发布后重新验证；
8. 写原子 receipt。

任一步失败：

- 保留已发布且哈希正确的文件；
- 删除本次未发布 staging；
- 不删除或覆盖任何已有目标；
- receipt 标为 `failed` 并记录公开错误；
- 重跑时把正确已发布文件识别为 `already_present`。

- [ ] **Step 6：实现 CLI**

审计：

```powershell
python scripts/recover_huiji_snapshot.py `
  --source-root "D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999" `
  --target-root "D:\1999Wiki\data\huiji\res1999" `
  --manifest "config\recovery\huiji-res1999-20260707.json" `
  --receipt "D:\1999Wiki\.codex-supervisor\recovery\audit.json"
```

应用必须额外显式提供：

```powershell
--apply
```

CLI 不提供 `--force`、`--overwrite` 或跳过哈希参数。

- [ ] **Step 7：运行恢复工具测试**

```powershell
python -m pytest tests/test_huiji_snapshot_recovery.py -q
```

Expected: PASS。

- [ ] **Step 8：提交**

```powershell
git add config/recovery/huiji-res1999-20260707.json src/huijiwiki/snapshot_recovery.py scripts/recover_huiji_snapshot.py tests/test_huiji_snapshot_recovery.py
git commit -m "feat: restore verified Huiji source snapshots"
```

### Task 7：执行真实文件恢复并关闭源文件身份门禁

**对应 Specs:** `REC-P0-01` 至 `REC-P0-05`、`REC-P0-07`、`REC-P0-08`；为 `REC-P0-06` 生产已核验异常记录计数

**Files:**

- Write ignored data: `data/huiji/res1999/data_pages.jsonl`
- Write ignored data: `data/huiji/res1999/crawl_state.sqlite`
- Write ignored receipt: `.codex-supervisor/recovery/audit.json`
- Write ignored receipt: `.codex-supervisor/recovery/apply.json`
- No Git commit for raw data or local receipt

**Interfaces:**

- Consumes: approved recovery tool and manifest
- Produces: verified canonical raw snapshot for C and D integration

- [ ] **Step 1：重新确认精确路径和磁盘空间**

```powershell
Get-Item -LiteralPath `
  "D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\data_pages.jsonl", `
  "D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\crawl_state.sqlite"

Get-PSDrive -Name D
```

Expected:

- source 文件存在；
- target 两文件仍缺失或已经与 manifest 完全一致；
- D 盘可用空间大于 1.5 GiB，覆盖 staging、目标和安全余量。

- [ ] **Step 2：执行 audit-only**

```powershell
python scripts/recover_huiji_snapshot.py `
  --source-root "D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999" `
  --target-root "D:\1999Wiki\data\huiji\res1999" `
  --manifest "config\recovery\huiji-res1999-20260707.json" `
  --receipt "D:\1999Wiki\.codex-supervisor\recovery\audit.json"
```

Expected:

```text
status: ready
missing: data_pages.jsonl, crawl_state.sqlite
mismatch: none
invalid_payload_rows: 1
```

若 target 状态与预期不同，停止并向用户报告，不进入 apply。

- [ ] **Step 3：获得恢复动作授权**

向用户报告：

- source 和 target；
- 待新增 629,597,702 字节；
- 两个 expected SHA-256；
- 不覆盖策略；
- audit receipt；
- D 盘剩余空间。

只有用户明确回复执行恢复后进入下一步。批准本 Plan 本身不替代本门禁。

- [ ] **Step 4：执行 apply**

```powershell
python scripts/recover_huiji_snapshot.py `
  --source-root "D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999" `
  --target-root "D:\1999Wiki\data\huiji\res1999" `
  --manifest "config\recovery\huiji-res1999-20260707.json" `
  --receipt "D:\1999Wiki\.codex-supervisor\recovery\apply.json" `
  --apply
```

Expected: 两个文件发布成功，其他 sibling 未改变。

- [ ] **Step 5：运行仓库完整性检查**

```powershell
python scripts/verify_huiji_res1999.py `
  --out "D:\1999Wiki\data\huiji\res1999" `
  --db "D:\1999Wiki\data\huiji\res1999\crawl_state.sqlite" `
  --skip-resource-files `
  --skip-resource-hash `
  --issue-limit 20 `
  --json
```

Expected:

```text
ok: true
error_count: 0
warning_count: 0
data_pages_lines: 72848
data_pages_unique_revisions: 72848
data_pages_duplicates: 0
```

恢复工具的 audit/apply receipt 还必须报告 `invalid_payload_rows: 1`。这证明已知异常 wrapper 被识别；C 的正式候选构建仍须按其独立 Spec/Plan 将该行写入 excluded evidence，完成前不得宣称 `REC-P0-06` 的投影排除闭包已经关闭。

- [ ] **Step 6：验证精确身份**

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath `
  "D:\1999Wiki\data\huiji\res1999\data_pages.jsonl"

Get-FileHash -Algorithm SHA256 -LiteralPath `
  "D:\1999Wiki\data\huiji\res1999\crawl_state.sqlite"
```

Expected:

```text
data_pages.jsonl:
EB82B82E34300EE5D8BEB27B13311FE530C59FAEBA3AE7883876B74B0EAB9092

crawl_state.sqlite:
CC34C6B701321B9FE59C3268577A334A3E092CD16190B59C28F98185A5866378
```

- [ ] **Step 7：确认 Git 不包含 raw data**

```powershell
git status --short
git check-ignore -v data/huiji/res1999/data_pages.jsonl
git check-ignore -v data/huiji/res1999/crawl_state.sqlite
```

Expected: 两个恢复文件均被 `data/huiji/` 规则忽略；没有新增 staged 文件。

### Task 8：编写运行手册和执行完整监督回归

**对应 Specs:** `OBS-P0-08`、`DOC-P0-01` 至 `DOC-P0-06`、`RUN-P0-01` 至 `RUN-P0-05`

**Files:**

- Create: `docs/codex/cli-supervisor-runbook.md`
- Modify: `tests/test_codex_supervisor_powershell.py`

**Interfaces:**

- Produces用户可复制的固定命令
- Produces D 的故障恢复和审核清单

- [ ] **Step 1：编写运行手册测试**

测试要求文档包含：

```text
Start-Worker.ps1
Stop-Worker.ps1
Resume-Worker.ps1
Watch-Worker.ps1
Show-Dashboard.ps1
Open-SupervisorWindows.ps1
关闭观察窗口不会停止 worker
gpt-5.6-sol
--disable fast_mode
--disable multi_agent
workspace-write
禁止第三层代理
```

并包含 A/B/C 三个重新打开命令和 D Dashboard 命令。

- [ ] **Step 2：运行测试确认失败**

```powershell
python -m pytest tests/test_codex_supervisor_powershell.py -q
```

Expected: FAIL，运行手册不存在。

- [ ] **Step 3：编写运行手册**

章节：

1. 架构和两层限制；
2. 初次启动；
3. 打开全部窗口；
4. 单独重开 A/B/C；
5. Dashboard 字段；
6. 如何判断 worker 仍存活；
7. 如何安全 stop；
8. 如何 resume 原 session；
9. Plan 审核门禁；
10. 请求用户审批；
11. 日志和 Token；
12. 故障恢复；
13. 原始数据与生产写操作禁区。

- [ ] **Step 4：执行监督完整回归**

```powershell
python -m pytest `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_events.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_huiji_snapshot_recovery.py `
  -q
```

Expected: PASS，零失败、零 fake worker 遗留进程。

- [ ] **Step 5：运行相关现有回归**

```powershell
python -m pytest `
  tests/test_huiji_start_script.py `
  tests/test_huiji_crawler_cmd_launchers.py `
  tests/test_huiji_integrity.py `
  tests/test_huiji_corpus_source_inventory.py `
  -q
```

Expected: PASS。

- [ ] **Step 6：执行静态和工作区检查**

```powershell
git diff --check
git status --short
```

Expected:

- 无 whitespace error；
- 只有本 Task 预期文档/测试改动；
- 已知未跟踪蓝绿计划仍未暂存；
- raw snapshot 和 `.codex-supervisor` 运行状态不出现在 Git diff。

- [ ] **Step 7：提交**

```powershell
git add docs/codex/cli-supervisor-runbook.md tests/test_codex_supervisor_powershell.py
git commit -m "docs: add Codex supervisor runbook"
```

### Task 9：A/B/C Spec 批准后创建隔离 worktree，并只下发 Plan 编写任务

**对应 Specs:** `WT-P0-01` 至 `WT-P0-05`、`DOC-P0-01` 至 `DOC-P0-06`、`INT-P0-01`

**Files:**

- Create runtime only: `.codex-supervisor/workers/A/approved-task.md`
- Create runtime only: `.codex-supervisor/workers/B/approved-task.md`
- Create runtime only: `.codex-supervisor/workers/C/approved-task.md`
- Create Git worktrees outside main
- No implementation code changes in this Task

**Interfaces:**

- Consumes: 用户批准的 A/B/C Spec
- Produces: 三个 plan-only CLI sessions

- [ ] **Step 1：验证文档门禁**

必须存在且已提交：

```text
docs/superpowers/specs/2026-07-29-rag-thread-a-routing-design.md
docs/superpowers/specs/2026-07-29-rag-thread-b-chinese-bm25-design.md
docs/superpowers/specs/2026-07-29-rag-thread-c-topic-media-projection-design.md
```

逐份确认用户批准记录。任一缺失时不创建任何 worker。

- [ ] **Step 2：使用 worktree 安全流程创建三个工作树**

执行本步骤前使用 `superpowers:using-git-worktrees` 检查路径、分支和基线。

```powershell
git worktree add `
  "D:\1999Wiki.worktrees\rag-a-routing" `
  -b "codex/rag-a-routing" `
  HEAD

git worktree add `
  "D:\1999Wiki.worktrees\rag-b-bm25" `
  -b "codex/rag-b-bm25" `
  HEAD

git worktree add `
  "D:\1999Wiki.worktrees\rag-c-projection" `
  -b "codex/rag-c-projection" `
  HEAD
```

创建前必须确认路径不存在或是精确、可复用的目标 worktree；不得删除未知现有目录。

- [ ] **Step 3：为每个 worker 生成 plan-only 任务**

每份 `approved-task.md` 必须包含：

```text
只调查并编写本线程 Implementation Plan
禁止修改实现代码
禁止创建子代理
模型 gpt-5.6-sol，标准速度
Spec 的绝对路径和 commit
本线程允许/禁止文件
Plan 输出路径
完成后状态 awaiting_plan_review
发现 Spec 冲突时 status=needs_approval
```

C 的任务还必须明确要求：对恢复快照中唯一的 `json_valid=false` wrapper 生成 excluded evidence，不得静默跳过或解析其无效 `content`；该测试通过后才能关闭 `REC-P0-06`。

- [ ] **Step 4：启动三个 worker**

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File "D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1" `
  -Worker A

powershell.exe -ExecutionPolicy Bypass `
  -File "D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1" `
  -Worker B

powershell.exe -ExecutionPolicy Bypass `
  -File "D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1" `
  -Worker C
```

- [ ] **Step 5：打开全部观察窗口**

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File "D:\1999Wiki\scripts\codex-supervisor\Open-SupervisorWindows.ps1"
```

- [ ] **Step 6：验证两层与 plan-only 状态**

```powershell
python scripts/codex_supervisor.py inspect --worker A
python scripts/codex_supervisor.py inspect --worker B
python scripts/codex_supervisor.py inspect --worker C
```

Expected:

- model 为 `gpt-5.6-sol`；
- `fast_mode=false`；
- `multi_agent=false`；
- sandbox 为 `workspace-write`；
- branch/worktree 精确匹配；
- task mode 为 `plan_only`；
- 没有第三层 session；
- 未修改实现文件。

## 5. D 对 A/B/C Plan 的审核矩阵

每份 Plan 必须逐项通过：

| 检查项 | 通过标准 |
|---|---|
| Spec 追踪 | 每个 P0 有稳定编号和对应 Task |
| 文件所有权 | 不修改其他线程拥有的文件 |
| 测试 | 每个 Task 有失败测试、最小实现、通过测试和回归 |
| 真实数据 | 不只依赖 mock；真实验收动作与安全门禁明确 |
| 两层限制 | 明确禁止子代理和 CLI 再委派 |
| 外部操作 | 抓取、下载、上传、激活均进入审批 |
| 兼容 | schema、序列化、provenance、旧产物策略一致 |
| 失败表现 | 空数据、异常、部分失败和恢复路径明确 |
| 提交 | 小而可审查，不包含其他 worktree 文件 |
| 完成判定 | 不能只用“测试通过”替代 Spec 验收 |

未通过时，D 将审查意见写入该 worker 的批准修订指令文件，并使用原 session 执行 `Resume-Worker.ps1`。不得创建新 worker 绕过原上下文。

## 6. 集成与合并运行规则

本计划只建立规则，不在 A/B/C 业务实现前执行合并。

默认顺序：

```text
B
→ D 验证 Analyzer/产物兼容
→ C
→ D 验证 Topic/Story/Media 生产
→ A
→ D 验证路由/主题消费/复合回答
→ main 全链影子回归
```

每次合并：

1. worker 分支状态 clean；
2. worker 最终提交已由 D 审核；
3. main 记录合并前 HEAD；
4. 非交互 Git 合并；
5. 运行该线程定向回归；
6. 运行前序已合并线程回归；
7. 冲突只由 D 在 main 解决；
8. 冲突后重新运行双方测试；
9. 不修改 active pointer。

## 7. 可选任务

仅在所有 P0 完成后考虑：

- `OBS-P1-01`：提供可双击 `.cmd` 观察入口。
- `REC-P1-01`：在新目录执行新抓取并生成与 2026-07-07 快照的差异报告。

未获得新批准时不执行。

## 8. Deferred / Out of Scope

- 图形化浏览器 Dashboard；
- 远程日志服务器；
- worker 自动无限重启；
- 云端部署和 PR 自动发布；
- BGE-M3 Sparse；
- VLM 图片描述；
- 全量媒体下载；
- MinIO、MySQL、Milvus 正式写入；
- active pointer 切换；
- A/B/C 业务实现细节。

## 9. 完成后自检表

- [ ] `SUP-P0-01` 至 `SUP-P0-03`：只有 D 和三个直接 CLI worker。
- [ ] `WT-P0-01` 至 `WT-P0-05`：main 与 A/B/C worktree 隔离，无跨工作树代码依赖。
- [ ] `CLI-P0-01` 至 `CLI-P0-06`：模型、标准速度、沙箱、会话复用和无 Token budget 均已验证。
- [ ] `OBS-P0-01` 至 `OBS-P0-08`：关闭/重开窗口不影响 worker，固定命令可用。
- [ ] `DOC-P0-01` 至 `DOC-P0-06`：Spec 和 Plan 审核顺序被实际执行。
- [ ] `REC-P0-01` 至 `REC-P0-05`、`REC-P0-07`、`REC-P0-08`：两个缺失文件按固定身份恢复并通过 verifier。
- [ ] `REC-P0-06`：恢复工具确认唯一 invalid wrapper，C Plan 已包含 excluded evidence 测试门禁。
- [ ] `DATA-P0-01` 至 `DATA-P0-05`：未执行未经批准的外部写操作。
- [ ] `RUN-P0-01` 至 `RUN-P0-05`：状态、失败、恢复、审批和完成审核可追踪。
- [ ] `INT-P0-01` 至 `INT-P0-04`：只建立安全集成流程，未隐含生产激活。
- [ ] 所有新增 supervisor 和 recovery 测试通过。
- [ ] 相关现有 crawler/integrity 测试通过。
- [ ] 没有 fake worker、锁或测试临时进程遗留。
- [ ] `.codex-supervisor` 和 raw data 未进入 Git。
- [ ] 用户未跟踪蓝绿计划未修改、未暂存、未提交。

## 10. 失败时表现

| 场景 | 必须表现 |
|---|---|
| 模型不可用 | worker 不启动，D 报告精确错误，不自动换模型 |
| worktree/branch 不匹配 | worker 不启动 |
| task 未批准 | worker 不启动 |
| 观察窗口关闭 | worker 保持运行 |
| watcher 读取到半写状态 | 保留上个原子状态并重试 |
| Codex 输出未知事件 | raw log 保留，runner 继续 |
| Codex 退出非零 | `status=failed`，保留 session 和 diff |
| PID 被复用 | stop 拒绝终止 |
| source 哈希不符 | 恢复 audit 失败，不复制 |
| target 已有不同文件 | 恢复失败，不覆盖 |
| staging 哈希不符 | 不发布最终文件 |
| 完整性 verifier 失败 | REC Gate 不关闭，C 继续禁止真实构建 |
| C 请求下载媒体 | 进入 `needs_approval`，先提交容量报告 |
| worker 修改越界文件 | D 拒绝接受，原 session 返工 |
| 合并后测试退化 | 停止后续合并，D 修复或回退该合并提交 |
