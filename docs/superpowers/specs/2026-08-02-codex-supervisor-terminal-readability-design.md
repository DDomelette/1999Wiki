# Codex Supervisor 终端可读性优化设计

## 背景

当前 supervisor 的观察窗口直接输出 Codex JSONL 事件，长行、转义字符和嵌套 JSON 混在一起，难以跟踪 worker 的对话。Dashboard 在持续模式下每秒追加一份完整表格，旧内容不会被覆盖；长分支、状态、测试摘要和大整数 token 还会挤乱列宽。

本次优化只改变观察界面的呈现。worker 的启动、停止、恢复、进程所有权、状态存储、事件存储和 Codex session 协议保持不变。

## 目标

1. Dashboard 在交互终端中原地刷新，保持固定、清晰的 A/B/C 总览。
2. Worker 观察窗口以对话为主线，显示任务、worker 回复和精简命令执行记录。
3. Worker 观察窗口保持严格只读，不向 session 写消息，不控制 worker 进程，不改写事件或状态文件。
4. 在不同终端宽度、中文内容、超长字段和异常日志下保持可读且不中断监视。
5. 保持现有 PowerShell 入口、CLI 参数、`--once` 和 `--tail` 行为兼容。

## 非目标

- 不增加向 worker 发送消息的交互能力。
- 不改变 worker 的任务执行、重试、停止或恢复逻辑。
- 不修改事件 JSONL、公开状态 JSON 或最终结果 schema。
- 不实现全屏 TUI、键盘导航、搜索或日志编辑。
- 不在观察窗口中展开完整的命令标准输出。

## 总体方案

采用“紧凑 Dashboard + 对话事件流”方案。`src/codex_supervisor/cli.py` 继续负责 CLI 调度，但把格式化和布局职责拆到小型、可独立测试的纯函数或专用呈现模块中。观察命令只从 `AtomicStateStore` 暴露的路径读取状态、任务和事件日志。

PowerShell 脚本继续调用同一个 Python CLI，不接触 session 或 worker 进程。必要的终端能力信息通过标准流是否为 TTY 和当前终端宽度推导，不增加破坏兼容性的必填参数。

## Worker 观察窗口

### 内容结构

窗口标题和首屏包含：

- `Codex Worker <A|B|C> - Observer Only`；
- 当前状态、阶段和配置分支；
- 对关闭窗口不影响 worker 的只读说明；
- 已批准任务文件的内容，标记为“任务”；
- 最近 `--tail` 条事件的格式化历史，随后实时尾随新事件。

事件流按时间顺序呈现以下内容：

1. `agent_message`：标记为 worker 回复。普通文本完整换行显示；若文本是最终结果结构 JSON，则提取状态、摘要、测试、阻塞项和下一步，避免展示转义后的嵌套 JSON。
2. `command_execution` started：显示 `▶ 命令` 和压缩成单行的命令，去除重复的 PowerShell 启动器包装，并按终端宽度截断。
3. `command_execution` completed：显示成功或失败符号和退出码。成功命令不展开输出，失败命令额外显示 `aggregated_output` 末尾的错误摘要。现有事件没有可靠时间字段，因此不伪造历史时间或耗时。
4. turn/thread/error 等事件：转换为简短、可区分的生命周期或错误提示。
5. 未识别事件：显示紧凑的类型摘要，不倾倒整行 JSON。

示例：

```text
Codex Worker C · Observer Only
状态：running   阶段：review   分支：codex/rag-c-projection

[C]
预检通过，正在启动唯一一次诊断执行。
下一步：等待进程完成。

▶ 命令
python diagnostic.product-parity.py --head 7366787…
✕ 退出码 1
ValueError: C8b taxonomy identity mismatch
```

### 只读保证

`watch` 只允许执行以下读取操作：

- `store.read(worker)`；
- 读取 `approved-task.md` 或 `approved-resume.md`；
- 读取并尾随 `<worker>.events.jsonl`；
- 读取配置中的分支名称。

呈现路径不得调用 start、resume、stop、accept、`append_event` 或任何 Codex session 写入接口。观察器关闭、异常或重开都不改变 worker 状态。

## Dashboard

### 宽屏布局

```text
Codex Supervisor · 14:32:08 · 每秒刷新

ID  Branch              Phase     Status      Tests             Tokens    Cached
A   rag-a-routing       planning  待审核      409 passed        246.7M    231.1M
B   rag-b-bm25          planning  失败        213 passed · 3⚠   122.7M    115.3M
C   rag-c-projection    planning  待审核      146 passed · 1⚠     2.35B     2.24B
```

具体规则：

- 每秒重新读取 A/B/C 状态，在交互终端中移动光标并覆盖上一帧，不再向下追加表格。
- 每帧显示刷新时间，固定按 A、B、C 排序。
- 分支展示时去掉重复的 `codex/` 前缀。
- token 使用带最多两位有效小数的 `K`、`M`、`B` 缩写并右对齐。
- 测试摘要只保留 passed、failed、warnings 和耗时；其余文本按可用宽度省略。
- 状态使用中文短标签及符号，不只依赖颜色表达含义。
- 状态文件不存在时显示“未启动”。

### 响应式降级

布局按实际终端字符宽度分三档：

1. 宽屏：显示所有列。
2. 中等宽度：优先隐藏 Cached，并压缩 Branch、Phase 和 Tests。
3. 窄屏：每个 worker 使用两行布局，第一行显示 ID、分支和状态，第二行显示测试与 token。

所有截断都使用可见的省略号，关键的 Worker ID 和状态不得被截断。

### 刷新兼容性

只有持续观察且 stdout 为交互终端时才使用原地刷新。`dashboard` 非 watch 模式、`watch --once` 和输出重定向保持普通文本输出，不注入清屏控制符。若终端不支持 ANSI，使用控制台兼容的清屏/光标回退；回退失败时仍输出可读帧而不影响 worker。

## 错误处理

- JSONL 尾部出现尚未写完的半行时，暂不渲染，等待下次读取完成。
- 单条 JSON 无法解析时显示一条“无法解析事件”摘要并继续处理后续事件。
- 日志文件缩短或轮转时从新文件开头重新建立读取偏移。
- 状态或任务文件缺失时显示明确占位符，不终止持续观察。
- 未知字段、未知事件类型和缺失 usage 值使用安全默认值。
- 中文宽度和截断逻辑不得生成无效 Unicode 或拆开组合字符；终端不支持颜色时符号和文字仍保留语义。

## 代码边界

预计改动范围：

- `src/codex_supervisor/cli.py`：接入新的渲染和刷新行为；
- `src/codex_supervisor/` 下的专用呈现模块（仅在有助于保持函数边界清晰时新增）；
- `scripts/codex-supervisor/Watch-Worker.ps1` 和 `Show-Dashboard.ps1`：仅传递必要的兼容参数或改善窗口说明；
- `tests/test_codex_supervisor_cli.py` 及新增的呈现单元测试；
- `tests/test_codex_supervisor_powershell.py`；
- `docs/codex/cli-supervisor-runbook.md`。

不修改 runner、进程所有权、安全停止、session 恢复和状态契约，除非测试证明呈现层无法在不改契约的情况下读取已有数据；发生这种情况时必须先回到设计审阅。

## 测试策略

按测试驱动方式逐项实现：先写预期失败的行为测试，再写最小实现，最后重构。

自动化覆盖：

- token 缩写的边界值和对齐；
- 宽屏、中等宽度和窄屏 Dashboard；
- 超长分支、状态和测试摘要的截断；
- 缺失状态文件；
- 普通 `agent_message` 和结构化最终结果消息；
- 命令开始、成功、失败及错误摘要；
- 中文、多行文本、未知事件和损坏 JSON；
- JSONL 半行、追加、截断和轮转；
- `--once` 与非 TTY 输出不含清屏控制符；
- 持续 Dashboard 原地刷新；
- PowerShell 观察脚本仍然只读、可关闭后重开；
- 现有 supervisor 全量回归测试。

完成前还应使用真实的当前 `.codex-supervisor` 状态执行一次 `dashboard` 和 C 的 `watch --once`，人工检查窗口宽度下的呈现；该检查只读，不启动、恢复或停止任何 worker。

## 验收标准

1. Dashboard 持续运行至少三个刷新周期时，屏幕上只保留一份当前总览。
2. 80、120 和 160 字符宽度下不出现字段互相覆盖或无边界换行。
3. C 窗口能按顺序读出任务、C 回复、命令开始和命令结果，不显示原始嵌套 JSON。
4. 失败命令显示退出码和简短错误原因，成功命令不倾倒完整输出。
5. 关闭或重开任意观察窗口不会改变 worker 状态、session 文件或进程。
6. 损坏或半写入事件不会终止监视。
7. 现有 CLI、PowerShell 和 supervisor 测试全部通过。
