# Codex CLI 并行监督运行手册

本手册用于 D 线程在 `D:\1999Wiki` 主工作树中监督 A/B/C 三个 Codex CLI
worker。架构固定为两层：`D → CLI A/B/C`，禁止第三层代理。每个 worker
使用独立 branch、独立 worktree 和独立可恢复 session。

固定执行配置为：

```text
model: gpt-5.6-sol
speed: standard
sandbox: workspace-write
--disable fast_mode
--disable multi_agent
```

不设置人为 token budget。首轮任务只允许 worker 编写自己的实施 Plan；在 D
审核并取得用户批准前，不允许修改业务代码。

## 初次启动

批准任务保存在：

```text
.codex-supervisor/workers/A/approved-task.md
.codex-supervisor/workers/B/approved-task.md
.codex-supervisor/workers/C/approved-task.md
```

逐个启动：

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1" -Worker A
powershell.exe -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1" -Worker B
powershell.exe -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1" -Worker C
```

`Start-Worker.ps1` 仅启动隐藏的 detached runner，随后立即返回。runner 才拥有
Codex child；窗口本身不拥有 worker。

## 打开或重新打开监视窗口

一次打开 A/B/C 和 Dashboard 四个可见 PowerShell 窗口：

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Open-SupervisorWindows.ps1"
```

单独重新打开：

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Watch-Worker.ps1" -Worker A
powershell.exe -NoExit -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Watch-Worker.ps1" -Worker B
powershell.exe -NoExit -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Watch-Worker.ps1" -Worker C
powershell.exe -NoExit -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Show-Dashboard.ps1"
```

关闭观察窗口不会停止 worker。观察器只读取
`.codex-supervisor/workers/*/state.json` 和
`.codex-supervisor/logs/*.events.jsonl`；重开时先显示历史尾部，再继续显示新事件。

Dashboard 固定按 A、B、C 顺序显示 branch、phase、status、测试摘要、总 token
与 cached input。总 token 为 input、output 与 reasoning output 之和；cached
input 单独保留。

## 判断 worker 是否仍在运行

查看公开状态：

```powershell
python "D:\1999Wiki\scripts\codex_supervisor.py" status --worker A
python "D:\1999Wiki\scripts\codex_supervisor.py" inspect --worker A
```

`inspect` 同时显示 runner 与 Codex child 的精确身份。身份包括 PID、创建时间、
可执行文件、工作目录和参数；任一项漂移都会阻止停止操作，避免误杀复用 PID。

## 安全停止

只允许显式停止一个 worker：

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Stop-Worker.ps1" -Worker A
```

停止顺序是 Codex child 后 runner。不存在 `all` 批量停止，也不使用 `taskkill`。
自然结束的进程视为幂等；身份不符则拒绝。

## 从原 session 接续

runner 会从 `thread.started` 事件持久化 session ID。准备经过批准的接续说明：

```text
.codex-supervisor/workers/A/approved-resume.md
```

然后执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\1999Wiki\scripts\codex-supervisor\Resume-Worker.ps1" -Worker A
```

`Resume-Worker.ps1` 使用记录的 session ID 调用 `codex exec resume`，只允许从
`failed`、`blocked` 或 `needs_approval` 接续。历史事件、状态和 usage 继续累计，
不会创建无法关联的新任务。若 CLI session 本身仍存在，Codex 的 resume 机制会
接续原上下文；若 session ID 缺失，监督器会明确拒绝。

## Plan 审核闸门

worker 最终报告必须包含 status、phase、summary、files_changed、tests_run、
tests_passed、blockers、needs_approval、last_commit 和 next_action。

D 审核时检查：

1. 只修改该 worker 的 Plan 及明确允许的文档。
2. Plan 完整引用已批准 Spec。
3. 没有业务代码、raw data、生产索引或 active pointer 变更。
4. 没有启用 subagent、fast mode 或第三层任务。
5. A/B/C 公共字段以冻结契约为准，不读取其他未合并 worktree。

审核通过后仍需用户明确批准，才能另写 `approved-resume.md` 或实施任务文件。

## 日志、故障与误关闭恢复

运行时文件全部位于被 Git 忽略的 `.codex-supervisor/`：

```text
workers/<A|B|C>/state.json
logs/<A|B|C>.events.jsonl
logs/<A|B|C>.stderr.log
sessions/<A|B|C>.json
locks/<A|B|C>.lock
```

观察窗口误关闭：直接重开，不影响 worker。PowerShell 控制窗口误关闭：detached
runner 仍继续工作。Codex 异常退出：状态变为 `failed`，检查 stderr 和公开
blocker，写入批准的 resume 指令后接续。机器重启或 runner 被中断：陈旧锁只在
PID/创建时间确认失效后回收；原 session ID 仍保留。

## 原始数据与外部写入禁区

监督器不会授权网络重抓、批量媒体下载、MinIO/MySQL/Milvus 写入、正式索引激活
或 active pointer 切换。快照恢复 CLI 默认仅 audit；必须显式 `--apply`，且没有
force/overwrite 选项。`data_pages.jsonl` 与 `crawl_state.sqlite` 的真实恢复需在
audit 后取得独立用户授权。C 的媒体下载还必须遵守 P0/P1 容量上限和 12 GiB
服务器剩余空间闸门。
