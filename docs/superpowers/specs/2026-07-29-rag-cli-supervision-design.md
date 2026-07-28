# RAG 并行 CLI 监督与集成设计

日期：2026-07-29

状态：用户审核候选

负责人：线程 D
适用仓库：`D:\1999Wiki`

## 1. 背景与目标

当前 RAG 迭代拆分为三个相互隔离的实现线程：

- 线程 A：路由、主题消费与复合问题编排；
- 线程 B：中文 BM25 Analyzer；
- 线程 C：主题/剧情投影与图片绑定。

线程 D 位于 main 工作树，负责规格治理、CLI 调度、实时监督、计划审核、跨线程契约、数据恢复、合并和最终验收。A、B、C 各自在独立 Git worktree 中由一个 Codex CLI 会话执行。

本设计的目标是：

1. 让用户能够通过 PowerShell 实时观察每个工作线程，而不是等待黑盒式最终结果。
2. 即使用户关闭观察窗口，CLI 工作者也继续运行，并可重新打开观察窗口恢复查看。
3. 严格维持两层结构 `D → A/B/C`，禁止 A、B、C 再创建子代理。
4. 统一跨线程规格，同时让每个执行线程根据自身工作树的真实代码编写实施计划。
5. 将缺失的 `data_pages.jsonl` 与 `crawl_state.sqlite` 恢复设为线程 C 的前置 P0 门槛。
6. 在不限制正常推理深度的前提下，通过标准速度、会话复用和减少重复上下文控制 Token 消耗。
7. 保证任何抓取、媒体批量下载、正式索引激活和生产数据变更都经过显式门禁。

## 2. 范围与非目标

### 2.1 本设计包含

- D/A/B/C 的职责和文档所有权；
- worktree、分支、CLI 会话和运行状态的隔离；
- 后台工作进程与可见 PowerShell 观察窗口的解耦；
- CLI 模型、速度、沙箱和多代理限制；
- Spec、Plan、实施、审核、合并与返工流程；
- `data_pages.jsonl` 和同批次爬虫状态的恢复闭包；
- A/B/C 的公共输入输出边界；
- 外部数据操作和媒体容量的审批门槛；
- 失败恢复、日志、Token 和验收证据。

### 2.2 本设计不包含

- A、B、C 的代码级实施步骤；
- BGE-M3 Sparse 或其他稀疏向量方案；
- 自动激活生产 BM25、Milvus collection 或 active pointer；
- 自动全量下载 61,087 个资源；
- 允许 CLI 绕过沙箱、审批或仓库文件所有权；
- 第三层及更深层的代理委派。

## 3. 总体架构

```text
用户
  │
  ▼
线程 D / main: D:\1999Wiki
  ├─ 规格与计划审核
  ├─ CLI 进程监督
  ├─ 数据恢复与外部操作门禁
  ├─ 合并、冲突处理与集成回归
  │
  ├─ CLI A / 独立 worktree / 独立 branch / 独立 session
  ├─ CLI B / 独立 worktree / 独立 branch / 独立 session
  └─ CLI C / 独立 worktree / 独立 branch / 独立 session
```

### 3.1 两层限制

`SUP-P0-01`：代理拓扑必须严格为 `D → A/B/C`。A、B、C 不得创建子代理、子任务代理或再次调用 Codex CLI 分派实现工作。

`SUP-P0-02`：每个 CLI 工作者启动时必须显式关闭 `multi_agent`；线程指令也必须重复声明禁止委派。功能开关和任务契约形成双重约束。

`SUP-P0-03`：D 只能向 A、B、C 下发其已批准 Spec 和 Plan 范围内的工作。扩大模块范围、执行外部写操作或修改公共契约必须先暂停并重新审核。

### 3.2 工作树与分支

`WT-P0-01`：D 始终在 `D:\1999Wiki` main 工作树中工作，不将 main 当作任一工作线程的开发工作树。

`WT-P0-02`：A、B、C 分别使用独立 worktree 和分支。建议稳定命名如下：

| 线程 | worktree | branch |
|---|---|---|
| A | `D:\1999Wiki.worktrees\rag-a-routing` | `codex/rag-a-routing` |
| B | `D:\1999Wiki.worktrees\rag-b-bm25` | `codex/rag-b-bm25` |
| C | `D:\1999Wiki.worktrees\rag-c-projection` | `codex/rag-c-projection` |

`WT-P0-03`：worktree 必须从包含已批准线程 Spec 的同一 main commit 创建。任何线程不得读取另一个线程 worktree 中尚未合并的文件。

`WT-P0-04`：共享原始爬虫快照属于只读外部输入，不属于某个线程的实现产物。线程可以读取经 D 验证的同一快照，但不能直接修改该快照。

`WT-P0-05`：线程间通过已冻结的字段、JSON fixture、schema 和提交记录协作，不通过跨 worktree 导入 Python 模块或复制未提交代码协作。

## 4. CLI 执行策略

### 4.1 模型与速度

`CLI-P0-01`：A、B、C 使用 `gpt-5.6-sol`。启动前必须执行可用性预检；若当前账户或 CLI 使用不同的精确模型标识，D 必须报告差异，不能自行换用其他模型。

`CLI-P0-02`：使用标准速度并显式关闭 Fast Mode。不得通过人为 Token budget、极短输出限制、减少允许测试次数或限制正常调查深度来节省 Token。

`CLI-P0-03`：允许工作线程像正常开发任务一样阅读代码、推理、运行必要测试、修正实现和重复验证。Token 优化仅来自：

- 复用已有 CLI session；
- 使用 `resume` 继续返工；
- 避免重复粘贴全量项目背景；
- 将稳定约束保存在 Spec 和 Plan 中；
- D 读取结构化状态、测试摘要和必要日志，而非重复吞入全部输出；
- 不创建第三层代理。

### 4.2 启动参数

计划中的工作线程启动基线以 A 为例：

```powershell
$Worktree = "D:\1999Wiki.worktrees\rag-a-routing"
$StatusSchema = "D:\1999Wiki\scripts\codex-supervisor\schemas\worker-status.schema.json"
$TaskPrompt = Get-Content `
  -LiteralPath "D:\1999Wiki\.codex-supervisor\workers\A\approved-task.md" `
  -Raw

codex exec `
  -m gpt-5.6-sol `
  --disable fast_mode `
  --disable multi_agent `
  --sandbox workspace-write `
  --json `
  --output-schema $StatusSchema `
  --cd $Worktree `
  $TaskPrompt
```

`CLI-P0-04`：不得使用 `--dangerously-bypass-approvals-and-sandbox`。如某个真实验收必须访问 worktree 外部资源，由 D 针对精确路径和动作设计最小权限方案，不能把整个磁盘加入可写范围。

`CLI-P0-05`：每个线程只有一个长期 session。修订和返工优先读取该线程 `sessions\<worker>.json` 中的 `session_id`，再执行 `codex exec resume $SessionId`；不得为普通返工重新创建无上下文会话。

`CLI-P0-06`：CLI 的结构化最终报告只约束状态通信，不限制内部调查、命令执行或正常回答长度。

## 5. 可观察性与 PowerShell 窗口

### 5.1 进程与窗口解耦

`OBS-P0-01`：CLI 工作者必须作为独立后台进程运行，不能把其生命周期绑定到用户看到的 PowerShell 窗口。

`OBS-P0-02`：PowerShell 窗口是只读观察器。关闭观察窗口不得终止、暂停或向工作者发送 EOF。

`OBS-P0-03`：重新打开观察窗口时，必须先显示持久化状态和最近日志，再继续流式显示新事件。

`OBS-P0-04`：停止工作者必须通过独立、显式的停止命令完成。观察脚本不得包含隐式停止逻辑。

### 5.2 运行状态目录

监督运行时状态使用被 Git 忽略的目录：

```text
D:\1999Wiki\.codex-supervisor\
├─ workers\
│  ├─ A\state.json
│  ├─ B\state.json
│  └─ C\state.json
├─ logs\
│  ├─ A.events.jsonl
│  ├─ B.events.jsonl
│  └─ C.events.jsonl
├─ sessions\
│  ├─ A.json
│  ├─ B.json
│  └─ C.json
└─ locks\
```

`OBS-P0-05`：`state.json` 必须原子更新，至少包含：

```text
worker
worktree
branch
session_id
pid
phase
status
current_action
last_event_at
files_changed
tests_summary
blocker
needs_approval
input_tokens
cached_input_tokens
output_tokens
reasoning_output_tokens
elapsed_seconds
last_commit
```

`OBS-P0-06`：原始 JSONL 日志必须保留，PowerShell 默认展示人类可读摘要。用户可以按需查看原始事件，但 D 不把全部日志自动注入监督上下文。

`OBS-P0-07`：展示内容包括阶段、工具和命令、测试、文件变化、错误、等待审批、完成状态和 Token 使用；不声称展示模型内部隐藏思维链。

### 5.3 观察命令契约

监督脚本实施后，以下命令必须可直接运行：

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass `
  -File "D:\1999Wiki\scripts\codex-supervisor\Watch-Worker.ps1" `
  -Worker A
```

将 `A` 替换成 `B` 或 `C` 可观察对应线程。

打开 D 汇总面板：

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass `
  -File "D:\1999Wiki\scripts\codex-supervisor\Show-Dashboard.ps1"
```

一次打开 A/B/C 和 D 全部观察窗口：

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File "D:\1999Wiki\scripts\codex-supervisor\Open-SupervisorWindows.ps1"
```

`OBS-P0-08`：上述命令必须同时写入运行手册。观察器意外关闭后，用户不需要查找 PID 或 session ID，只需重新执行同一命令。

`OBS-P1-01`：可以提供仅负责调用上述命令的可双击 `.cmd` 入口；它不能成为唯一入口。

## 6. 文档治理

### 6.1 文档所有权

`DOC-P0-01`：D 统一编写并维护：

- 本总体监督与集成 Spec；
- D 监督与集成 Plan；
- A、B、C 三份线程 Spec；
- 跨线程公共契约和最终集成验收矩阵。

`DOC-P0-02`：A、B、C 在各自 worktree 中根据已批准线程 Spec 编写本线程 Plan。执行者必须先检查本工作树真实代码、测试和依赖，再确定文件级步骤。

`DOC-P0-03`：D 审核每份线程 Plan。Plan 未获 D 批准前，该 CLI 只能调查和修订计划，不能修改实现代码。

`DOC-P0-04`：线程不得自行改变 Spec 范围。若代码事实与 Spec 冲突，Plan 必须记录精确证据并进入 `needs_approval`，由 D 修改 Spec 或给出边界裁决。

### 6.2 审核顺序

```text
D 总体 Spec
  → 用户审核
D 监督与集成 Plan
  → 用户审核
D 编写 A/B/C 独立 Spec
  → 用户逐份审核
创建 A/B/C worktree
  → A/B/C 各自编写 Plan
  → D 审核与要求修订
  → D 授权执行
实施、阶段验收和独立复核
  → D 合并
  → main 集成验收
```

`DOC-P0-05`：Plan 必须使用稳定 Spec 编号建立追踪关系。每个 P0 至少包含实现位置、测试命令、真实数据验收方式和失败表现。

`DOC-P0-06`：A/B/C Plan 必须明确采用单一 CLI 会话内联执行，禁止引用“由本线程继续分派子代理”的执行方式。

## 7. 原始数据恢复

### 7.1 已核实事实

2026-07-29 的只读审计确认：

1. 当前目录 `D:\1999Wiki\data\huiji\res1999` 缺少：
   - `data_pages.jsonl`
   - `crawl_state.sqlite`
2. 参考目录 `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999` 中存在同名文件。
3. 两个目录中现存的 `pages.jsonl`、`wikitext.jsonl`、`resources_manifest.jsonl`、`siteinfo.json` 和 `errors.jsonl` 的大小、时间戳和 SHA-256 分别完全相同，证明它们来自同一批本地快照。
4. 参考 `data_pages.jsonl` 的身份为：

```text
size:       581,887,494 bytes
row count:  72,848
SHA-256:    eb82b82e34300ee5d8beb27b13311fe530c59faeba3ae7883876b74b0eab9092
timestamp:  2026-07-07T12:01:27.3185063Z
```

5. 该 SHA-256 和行数与 `docs/reports/2026-07-20-huiji-corpus-fidelity-audit.md` 中的正式审计记录一致。
6. 使用当前仓库的 `verify_huiji_res1999.py` 对参考快照执行完整性检查，在跳过资源文件实体和资源哈希扫描的条件下结果为：

```text
ok: true
error_count: 0
warning_count: 0
data_pages_lines: 72,848
data_pages_unique_revisions: 72,848
data_pages_duplicates: 0
```

7. 参考 `crawl_state.sqlite` 的身份为：

```text
size:       47,710,208 bytes
SHA-256:    cc34c6b701321b9fe59c3268577a334a3e092cd16190b59c28f98185a5866378
timestamp:  2026-07-07T16:43:14.8330230Z
```

8. 在 `D:\1999Wiki_Backup` 中未发现名为 `data_pages.jsonl` 的直接备份副本。
9. `data/huiji/` 被 `.gitignore` 排除，Git 历史不能解释该本地文件何时或为何缺失；当前没有足够审计证据把缺失归因于某一次清理、迁移或人为删除。

### 7.2 恢复原则

`REC-P0-01`：优先从已验证的旧项目快照执行字节级恢复，而不是重新抓取。该文件可以按已知 SHA-256 一比一恢复。

`REC-P0-02`：“一比一恢复”仅指恢复参考目录中的 2026-07-07 快照。重新请求灰机 Wiki 会产生新的抓取时间、可能不同的 revision 和远端内容，不能承诺与旧文件逐字节一致。

`REC-P0-03`：恢复流程必须先复制到临时 staging 路径，验证大小、SHA-256、行数、JSONL 可读性和爬虫完整性，再以明确的原子步骤放入当前 canonical raw root。

`REC-P0-04`：恢复不得覆盖参考目录中的旧文件，不得修改参考 `crawl_state.sqlite`，不得在验证前删除任何当前文件。

`REC-P0-05`：`data_pages.jsonl` 与 `crawl_state.sqlite` 必须按同一快照闭包审计。即使 corpus builder 只强制消费四个 JSONL，状态数据库仍需恢复或另行留存为可复现和增量抓取证据。

`REC-P0-06`：恢复完成后必须重新运行：

- 精确 SHA-256 和 size 比较；
- JSONL 行数与唯一 revision 检查；
- `verify_huiji_res1999.py` 完整性验证；
- 四个 corpus source 文件的 inventory/provenance 验证；
- 已知 crawler 标记的无效 JSON payload 排除测试。

`REC-P0-07`：恢复报告必须保存来源路径、目标路径、文件身份、验证命令、验证结果和时间。只报告“复制成功”不能通过门禁。

`REC-P0-08`：在 `REC-P0-01` 至 `REC-P0-07` 全部通过前：

- C 不得执行真实全量 Topic/Story 候选构建；
- C 不得执行资源批量下载；
- D 不得接受依赖不完整 raw root 的媒体容量结论；
- fixture 开发可以继续，但不能宣称真实快照验收通过。

`REC-P1-01`：恢复并冻结旧快照后，可以另行创建新目录执行增量或全量重新抓取，用于比较远端变化。新抓取不得覆盖已恢复快照，且不属于本轮 P0。

### 7.3 恢复完成标准

恢复只有在以下条件同时满足时才完成：

| 项目 | 要求 |
|---|---|
| `data_pages.jsonl` | size、72,848 行和 SHA-256 与已审计参考完全一致 |
| `crawl_state.sqlite` | size 和 SHA-256 与参考一致，SQLite 可打开 |
| 同批次 JSONL | pages、wikitext、data_pages、resources manifest 可被完整性工具共同验证 |
| 引用闭包 | Data 页面 latest revision 不缺失 |
| 审计记录 | 来源、目标、命令和结果已持久化 |
| 安全 | 参考副本和当前其他文件未被覆盖或删除 |

## 8. 线程边界和公共契约

### 8.1 线程 A

负责：

- 安全任务分类和回答授权；
- meta/smalltalk 的本地确定性回答；
- 无单一角色 Owner 的主题检索消费；
- 复合问题拆分、并行执行、引用统一和结果聚合。

不得负责：

- BM25 Analyzer；
- crawler semantic projection；
- 媒体下载和绑定生产；
- 稀疏向量。

### 8.2 线程 B

负责：

- 领域保护词、中文词语和二字 fallback 的混合 BM25 Analyzer；
- Analyzer 在索引端和查询端的一致性；
- Analyzer 版本、配置哈希和产物兼容；
- 中文检索回归。

不得负责：

- Planner、Route Policy 和复合执行；
- Topic/Story 语料生产；
- BGE-M3 Sparse；
- 正式索引激活。

### 8.3 线程 C

负责：

- pages、wikitext、data_pages 和 resources 的统一关联；
- Story/Topic/Page 的自然标题、别名、章节和来源投影；
- Wikitext 图片引用、caption、章节和资源 manifest 绑定；
- 影子候选、未下载资源清单和媒体容量报告。

不得负责：

- 路由和 Owner Gate；
- BM25 Analyzer；
- 正式下载全部资源；
- 正式候选激活。

### 8.4 公共数据契约

`CONTRACT-P0-01`：C 产出、A 消费的最小稳定字段必须在 A/C Spec 中保持一致：

```text
category
entity_type
entity_id
entity_name
entity_aliases
owner_entity_id
owner_page_id
route_tags
parent_id
child_id
heading_path
section_kind
content
search_text
source_refs
```

`CONTRACT-P0-02`：A 不依赖 C 的内部 Python 类型或 worktree 文件。联调前使用冻结 JSON fixture；真实产物只在 C 合并后由 D 验证。

`CONTRACT-P0-03`：B 不依赖 C 动态生成领域词典作为首版成立条件。额外领域词可以通过稳定、版本化的输入扩展，但 B 必须能独立测试和构建。

`CONTRACT-P0-04`：B 与 C 如需同时修改构建产物 schema，必须由 D 冻结字段归属和合并顺序，禁止各自定义同名但不同语义的字段。

## 9. 外部操作与媒体容量门禁

`DATA-P0-01`：只读扫描、哈希、行数统计和本地 fixture 构建可由线程自行执行。

`DATA-P0-02`：以下操作必须进入 `needs_approval` 并由 D 向用户报告后再执行：

- 网络重新抓取；
- 批量下载媒体；
- 写入 canonical raw snapshot；
- 上传 MinIO；
- 写入生产 MySQL；
- 修改正式 Milvus collection；
- 切换 active pointer；
- 删除、移动或覆盖现有数据。

`DATA-P0-03`：C 在申请媒体下载前必须先输出只读容量报告，至少包含：

```text
正文实际引用的唯一资源数
已下载并通过哈希的资源数
缺失资源数
manifest 声明总字节数
预计新增本地字节数
预计新增 MinIO 字节数
可通过内容哈希复用的对象数
无法确定大小的资源数
目标磁盘当前可用空间
安全余量
```

`DATA-P0-04`：容量未知、目标路径不明确、磁盘安全余量不足或资源集合未由正文引用闭包限定时，不得开始批量下载。

`DATA-P0-05`：已有 MinIO 对象按内容哈希复用，不得因新增页面绑定重复上传同一媒体实体；一个资源可以保留多个来源绑定。

## 10. 监督、失败与返工

`RUN-P0-01`：工作线程状态至少包括：

```text
planning
awaiting_plan_review
approved
running
testing
needs_approval
blocked
failed
completed_pending_review
accepted
```

`RUN-P0-02`：进程异常结束时，D 必须保存最后事件、退出码、未提交 diff、当前测试状态和 session ID。能恢复时使用原 session 继续，不从头重复任务。

`RUN-P0-03`：工作线程声称完成后，D 必须独立检查：

- 修改是否在文件所有权内；
- Spec P0 是否逐项覆盖；
- 实际 diff 与提交；
- 定向测试和线程级回归；
- 是否存在静默 fallback、空实现或仅 fixture 成功；
- 是否包含未批准的数据或基础设施写操作。

`RUN-P0-04`：一个线程失败不自动取消其他独立线程。只有公共契约发生变化或共享输入被判定无效时，D 才暂停受影响线程。

`RUN-P0-05`：CLI 请求用户审批或遇到范围外决策时保持暂停，由 D 汇总精确动作、影响和替代方案后交给用户决定。

## 11. 合并与集成

`INT-P0-01`：D 只合并已通过线程级验收且工作树清洁的提交。不得直接复制工作树文件到 main 代替 Git 合并。

`INT-P0-02`：默认集成顺序为：

```text
B：Analyzer 与 BM25 产物契约
  → C：Topic/Story/Page/Media 生产
  → A：路由、主题消费与复合编排
  → D：公共 schema、真实快照和全链回归
```

若实际提交依赖图证明顺序需要调整，D 必须在合并前记录理由。

`INT-P0-03`：D 负责解决跨线程冲突，A/B/C 不直接修改其他线程分支。冲突解决后必须重新运行受影响线程的测试。

`INT-P0-04`：本轮只生成影子产物和验收报告。正式激活需要独立批准，不能被“集成测试通过”隐含授权。

## 12. 测试与验收方向

### 12.1 监督基础设施

- 关闭观察窗口后 worker PID 仍存活；
- 重新打开后能显示历史尾部和新事件；
- A/B/C 状态互不覆盖；
- session ID、PID 和 branch 与实际进程一致；
- `turn.completed` Token 用量被正确累计；
- worker 完成、失败和等待审批均能进入正确状态；
- 禁用 multi-agent 的启动参数可被审计；
- 停止命令只影响精确指定的 worker。

### 12.2 数据恢复

- 已恢复文件与已知 SHA-256 一致；
- verifier 返回 `ok: true`；
- corpus source inventory 能读取四个必需 JSONL；
- 恢复前 C 的真实构建门禁会失败；
- 恢复后门禁开放但不会自动下载媒体；
- 新抓取目录无法覆盖冻结旧快照。

### 12.3 A/B/C 集成

- B 的中文 Analyzer 改善自然语言 BM25 召回且旧产物不会被静默重新解释；
- C 能生产自然 Story/Topic 名称和来源支持的图片绑定；
- A 能回答 meta/smalltalk，并在默认关闭自由补充时继续阻止数据库外事实幻觉；
- “暴雨是什么”能够进行无单一角色 Owner 的知识库检索；
- “你好，你是谁，请介绍一下十四行诗”能够按顺序聚合，只有知识库分支带引用；
- 同步 API 与 SSE 保持契约一致；
- 不激活生产索引也能完成影子全链验收。

## 13. P1 与未来演进

以下能力不属于本轮 P0：

- 浏览器式图形监督面板；
- 远程服务器集中日志；
- 自动重启失败 worker；
- 自动 PR 创建和云端部署；
- 新旧全量爬虫快照差异平台；
- BGE-M3 Sparse；
- 基于 VLM 的图片描述生成；
- 自动生产激活。

这些能力不得作为 P0 完成的必要条件，也不得在 A/B/C Plan 主线中实现。

## 14. 完成判定

本设计对应的迭代只有在以下条件全部满足时才能声明完成：

1. D/A/B/C 两层拓扑和三个独立 worktree 已实际执行。
2. PowerShell 观察窗口可关闭、重开，且不影响工作者。
3. 用户能查看每个线程和 D 汇总状态。
4. `data_pages.jsonl` 与 `crawl_state.sqlite` 已按审计身份恢复并通过完整性检查。
5. A/B/C Spec 与 Plan 均经过规定的审核门禁。
6. A/B/C 各自 P0 完成且通过线程级验证。
7. D 完成合并、冲突后回归和真实快照影子验收。
8. 没有执行未经批准的网络抓取、批量媒体下载或生产激活。
9. P1/P2 未完成项明确记录，没有被误报为已完成。
10. 最终报告包含提交、测试、数据身份、Token、耗时、返工和已知风险。
