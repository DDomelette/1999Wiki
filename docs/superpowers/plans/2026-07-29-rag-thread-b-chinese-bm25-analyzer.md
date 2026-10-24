# 线程 B：中文 BM25 Analyzer Implementation Plan

> **状态：** 待线程 D 审核
> **执行模式：** 单一长期 Codex CLI session 内联执行；禁止子代理、禁止再次调用 Codex CLI、禁止读取 A/C 未合并 worktree
> **批准 Spec：** `docs/superpowers/specs/2026-07-29-rag-thread-b-chinese-bm25-analyzer-design.md`
> **批准基线：** `ed569ee23f5d3927f8a332e69ef4de82ac8b6c59`
> **执行技能：** 实施时使用 `superpowers:executing-plans`；不得使用 subagent-driven 或任何多代理执行方式。

## 1. 目标

在不修改 Planner、Retriever 路由、Owner Gate、query 选择或线程 A/C 文件的前提下，串行交付：

1. 确定性的 `领域保护词 + Jieba 实例级精确词 + 连续中文二元组 fallback` Analyzer；
2. 索引端和查询端持有并使用同一 Analyzer 实例；
3. analyzer/config/dictionary/segmenter/BM25 参数的稳定身份与哈希；
4. child v3、media binding v4、local v2 payload 及严格 loader/parity/provenance；
5. records-only、child v2、media v3 对 `legacy-regex/v1` 的精确兼容；
6. 英文、数字、内部 ID、文件名和多 segment API 非退化；
7. 仅使用本线程 fixture 或只读候选的影子对照报告。

本计划不包含 BGE-M3 Sparse、Milvus sparse schema、任何稀疏向量迁移、字段权重、channel boost、停用词、learned sparse、正式索引激活、active pointer 或生产 baseline 更新。

## 2. 已核实代码事实

- `src/rag/sparse.py:58` 的 `tokenize()` 仍使用 legacy regex；`build()` 与 `search()` 分别调用模块级函数。
- `src/rag/sparse.py:113` 的本地 `save()` 只保存 records，`load()` 使用当前代码重新分词。
- `src/huiji_rag/build/artifact_writer.py:216` 直接生成 child v2 与 media binding v3；`_verify_bm25_parity()` 只校验 records、ID、行数和 semantic hash。
- `src/huiji_rag/build/artifact_writer.py:346` 的 embedding handoff 尚未携带 Analyzer fingerprint。
- `src/huiji_rag/provenance.py:54` 的 `Bm25Fingerprint` 尚未记录 payload schema、Analyzer、segmenter、config/dictionary hash、`k1` 或 `b`。
- `src/rag/retriever.py:263` 已通过 `LocalBM25SparseIndex.load()` 加载 child BM25；不需要也不得修改其路由或 query 选择逻辑。
- `src/huiji_rag/io.py` 与 `src/huiji_rag/runtime_artifacts.py` 已保留 `indexes/child_text_bm25.json` 和 `indexes/media_binding_bm25.v3.json` 路径；本计划不修改这两个文件。
- D 已核实唯一允许的执行环境为 Conda `1999wiki`：解释器 `D:\Anaconda32024\envs\1999wiki\python.exe`，`sys.prefix=D:\Anaconda32024\envs\1999wiki`，Python 3.11.15；该环境的 pip 为 25.2、pip-tools 为 7.5.1，与现有 lock 头一致。当前该环境未安装 Jieba，因此依赖测试应先红灯。
- 当前定向基线有 36 项通过；其余 42 项在产品断言前因默认 pytest 临时目录位于沙箱外而 setup 失败。后续命令统一使用工作区内 `.tmp/pytest-rag-b-*` 作为 `--basetemp`，测试后确认该目录未被 Git 跟踪并清理。

## 3. 全局执行约束

### 3.1 Conda `1999wiki` fail-closed 门禁

每次 session resume，以及 B1、B2、B3、B4、B5 每个阶段开始前，必须在该阶段同一个 PowerShell 进程中执行：

```powershell
$Python1999Wiki = "D:\Anaconda32024\envs\1999wiki\python.exe"
$Expected1999WikiPrefix = "D:\Anaconda32024\envs\1999wiki"

if (-not (Test-Path -LiteralPath $Python1999Wiki -PathType Leaf)) {
    throw "Conda 1999wiki interpreter is missing: $Python1999Wiki"
}

& $Python1999Wiki -c @"
import os
import sys

expected_executable = os.path.normcase(os.path.abspath(r"D:\Anaconda32024\envs\1999wiki\python.exe"))
expected_prefix = os.path.normcase(os.path.abspath(r"D:\Anaconda32024\envs\1999wiki"))
actual_executable = os.path.normcase(os.path.abspath(sys.executable))
actual_prefix = os.path.normcase(os.path.abspath(sys.prefix))
actual_version = ".".join(str(part) for part in sys.version_info[:3])

if actual_executable != expected_executable:
    raise SystemExit(f"unexpected sys.executable: {sys.executable}")
if actual_prefix != expected_prefix:
    raise SystemExit(f"unexpected sys.prefix: {sys.prefix}")
if actual_version != "3.11.15":
    raise SystemExit(f"unexpected Python version: {actual_version}")
"@
if ($LASTEXITCODE -ne 0) {
    throw "Conda 1999wiki environment verification failed"
}
```

门禁通过后，该阶段所有 Python、pip、pytest、pip-tools、compileall 和临时 `--target` 安装命令都必须使用 `& $Python1999Wiki ...`。禁止使用裸 `python`、`pip`、`pytest` 或依赖当前 `PATH`/已激活 shell 恰好正确。解释器路径、`sys.executable`、`sys.prefix` 或 Python 3.11.15 任一不符时立即停止并报告 D，不运行测试、不生成 lock、不安装依赖。

### 3.2 串行阶段与审核停点

严格按以下顺序执行，不并行拆分：

```text
B1 Analyzer contract + normalization + token tests
  → D 审核 B1 提交
B2 LocalBM25SparseIndex integration + legacy loader
  → D 审核 B2 提交
B3 payload schema + artifact parity + provenance
  → D 审核 B3 提交
B4 dependency locks + affected regression
  → D 审核 B4 提交
B5 shadow comparison report
  → D 最终审核
```

每个阶段结束后：

1. 运行该阶段定向测试和已完成阶段回归；
2. 检查 `git diff --check`、`git status --short` 和文件所有权；
3. 创建一个小提交；
4. 输出 `awaiting_plan_review` 并等待 D 审核，未经 D 接续批准不进入下一阶段。

### 3.3 TDD 纪律

每个 Task 固定采用：

1. 添加最小失败测试；
2. 运行精确 node/test，确认因目标行为缺失而红，不接受 import、fixture、权限或语法错误冒充红灯；
3. 写满足当前测试的最小实现；
4. 运行定向测试至绿；
5. 运行本阶段回归；
6. 只提交本阶段文件。

### 3.4 测试临时目录

所有 pytest 命令使用：

```powershell
$env:PYTEST_ADDOPTS = "--basetemp=.tmp/pytest-rag-b"
```

执行前要求 `.tmp/pytest-rag-b` 不存在；执行后只清理该精确工作区内路径。若无法安全清理，不运行会产生该目录的命令并向 D 报告，不扩大沙箱。

### 3.5 停止条件

立即停止并返回 `needs_approval`：

- Conda `1999wiki` 的绝对解释器、`sys.executable`、`sys.prefix` 或 Python 3.11.15 门禁不匹配；
- Jieba 0.42.1 无法由 Conda `1999wiki` 的 Python 3.11.15 和现有 pip-tools 解析闭包安装或锁定；
- 新 schema 需要修改 `src/huiji_rag/io.py`、activation、部署脚本、正式路径或生产 baseline；
- 需要修改 `src/rag/retriever.py` 的路由、Owner Gate、query 选择，或任何 Planner/QueryPlan/RequestPlan 文件；
- 需要读取或复制 A/C 未合并 worktree 文件；
- child/media schema 字段与 D 冻结契约冲突；
- 核心中文 fixture 无改善，或英文/ID/文件名发生退化；
- 任何测试要求构建、覆盖或激活正式索引。

## 4. B1 — Analyzer 契约、词典、归一化与 token

**对应 Specs：** `SCOPE-P0-01`、`SCOPE-P0-02`、`DECISION-P0-01` 至 `DECISION-P0-03`、`ARCH-P0-01`、`ARCH-P0-02`、`ANALYZER-P0-01` 至 `ANALYZER-P0-06`、`NORM-P0-01` 至 `NORM-P0-06`、`TOKEN-P0-01` 至 `TOKEN-P0-10`、`MERGE-P0-01` 至 `MERGE-P0-05`、`IDENTITY-P0-01` 至 `IDENTITY-P0-06`、`QUERY-P0-01` 至 `QUERY-P0-04`、`ERROR-P0-01`、`ERROR-P0-06`、`TEST-P0-01`、`TEST-P0-02`、`OWN-P0-03`。

**执行前置：** 先通过 3.1 的 Conda `1999wiki` 门禁。该环境尚未安装 Jieba；先运行 B1 红灯并确认唯一依赖失败为 `jieba` 缺失，随后使用 `& $Python1999Wiki -m pip install --no-deps --target .tmp/rag-b-site jieba==0.42.1` 将批准版本安装到工作区临时 target，并仅在 B1–B3 测试命令中显式设置 `$env:PYTHONPATH = (Resolve-Path ".tmp/rag-b-site").Path`。该命令只能由 `D:\Anaconda32024\envs\1999wiki\python.exe` 执行，不得调用其他 Conda 环境的 pip；临时 target 不提交、不进入 Analyzer identity，B4 完成正式 inputs/locks 后删除。若精确版本无法下载、导入或在该环境的 Python 3.11.15 下运行，停止并向 D 报告；若证据表明版本不兼容，状态为 `needs_approval`，不得换版本。

### Task B1.1：先锁定公共契约和身份哈希红灯

**Files**

- Create: `src/rag/chinese_analyzer.py`
- Create: `src/rag/resources/bm25_domain_terms.v1.txt`
- Create: `tests/test_chinese_bm25_analyzer.py`

**红灯**

在 `tests/test_chinese_bm25_analyzer.py` 先添加：

- config 为不可变、可序列化对象，固定 name/version/config；
- identity 完整包含 schema、segmenter、规范词表和三个 SHA-256；
- 词典 NFKC、trim、去空、去重、Unicode code point 排序；
- dictionary bytes 使用“一词一行且末尾 LF”；
- config/fingerprint 使用 canonical UTF-8 JSON；
- 额外词进入完整 identity，改变 dictionary/analyzer fingerprint；
- records 或输入文本变化不改变 Analyzer fingerprint；
- 缺词典、非法 UTF-8、控制字符明确失败；
- Analyzer 不读取 CWD、环境变量、网络或用户缓存。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py -k "identity or config or dictionary or invalid"
```

Expected red：模块或契约不存在；不得因 Jieba 尚未安装而在 collection 阶段失败。测试用 `pytest.importorskip` 是禁止的；依赖缺失必须是明确红灯。

**最小实现**

- 用 frozen dataclass（或等价不可变结构）实现 `AnalyzerConfig`、`AnalyzerIdentity`。
- 固定：
  - `schema_version="rag.bm25-analyzer/v1"`；
  - `name="zh-domain-word-bigram"`；
  - `version="1"`；
  - segmenter `jieba/0.42.1/HMM=false`；
  - Spec 固定 config 七项。
- 实现仅接受显式 `Path`/terms 的词典加载与 identity 重建；不使用 CWD 搜索或环境变量。
- 将基础词典写为 UTF-8 一词一行，至少包含八个批准术语；不写整句、用户历史或抓取顺序。
- 提供单一 canonical JSON/hash helper，校验三个 hash 后才接受 serialized identity。

**绿灯**

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py -k "identity or config or dictionary or invalid"
```

**失败表现**

- 错误指出 dictionary/config/identity 类别和安全字段，不打印词典全文；
- 缺文件、编码错、控制字符、hash 错均 fail closed，不回退空词典。

### Task B1.2：实现位置化四 channel Analyzer

**红灯**

继续添加参数化测试：

- `槲寄生的基础资料` 不再是单一长 token；
- 包含保护词、Jieba 词、全部相邻 Han bigram；
- `十四行诗的技能是什么` 保留角色名和关键词；
- 单字、空白、纯标点、全角 ASCII；
- protected/word/bigram/technical 相同位置去重；
- 相同词不同位置保留真实 TF；
- 固定排序键；
- `Data:Story/304502`、`Skill-30410111`、`000-box-construction`、`Banner_今夜星光灿烂.png`；
- 文件名同时保留完整 technical token 和内部中文可检索 token；
- 英文大小写、数字、下划线、连字符、扩展名混排；
- URL、Windows 路径、长无边界噪声不成为任意巨型 token；
- bigram 不跨空格、标点、technical atom 或 segment；
- 长 Han span 的 bigram 数量为 `n-1`，证明线性输出；
- 两个独立 Analyzer 的额外词互不污染；
- 默认 Jieba Tokenizer 词典状态不变。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py -k "token or normalize or technical or bigram or instance"
```

Expected red：`analyze()` 尚未实现或输出不符合位置/去重规则。

**最小实现**

- 每个 `ChineseBM25Analyzer` 新建独立 `jieba.Tokenizer()`，只向该实例精确注入规范领域词，调用 `tokenize(..., HMM=False)`/等价位置 API。
- 先 NFKC，再 lowercase ASCII；records 原文不在 Analyzer 中改写。
- 在归一 segment 上提取：
  1. 可重叠 protected terms；
  2. Jieba word tokens；
  3. 每个连续 Han span 的相邻 bigrams；
  4. 受控内部 ID/文件名 technical atoms 及安全拆分 token。
- 内部 token 记录 `segment_index/start/end/channel/normalized_token`。
- 用 `(segment_index,start,end,token)` 去重；按 Spec priority 和稳定 tie-break 排序。
- 不增加 channel boost、停用词、同义词、简繁、拼音或全子串。

**绿灯**

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py
```

### Task B1.3：多 segment、跨进程确定性与 B1 回归

**红灯**

添加：

- `analyze_segments(["槲寄生", "基础资料"])` 等于两段独立分析后拼接；
- 不产生 `生基` 等跨 segment bigram；
- 空 segment 被忽略但 segment 顺序稳定；
- query text 不能临时写入词典；
- 子进程对固定 probes 输出完全相同 canonical token arrays；
- 重复调用和两个进程的 identity/token 完全一致。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py -k "segments or process or deterministic"
```

**最小实现**

- `analyze()` 委托单 segment 内部实现；
- `analyze_segments()` 对每个非空输入独立分析并按输入顺序拼接；
- 不缓存请求输入，不变更词典或 Tokenizer。

**B1 回归**

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py tests/test_sparse_bm25.py
& $Python1999Wiki -m compileall -q src/rag/chinese_analyzer.py
git diff --check
```

**真实/影子验收**

- 仅分析批准的五个 probe strings 和本线程 fixture；
- 输出 token arrays、identity 和 hash 到测试断言，不读取生产 `data_pages.jsonl`；
- 性能测试只用生成的长 Han 字符串，验证 token 数 O(n)，不设未经批准的生产 SLA。

**B1 提交**

```text
feat(rag): add deterministic Chinese BM25 analyzer
```

提交仅含 B1 三个文件。提交后等待 D 审核。

## 5. B2 — LocalBM25SparseIndex、payload loader 与 legacy

**对应 Specs：** `ARCH-P0-03`、`INDEX-P0-01` 至 `INDEX-P0-07`、`SCHEMA-P0-01` 至 `SCHEMA-P0-03`、`COMPAT-P0-01` 至 `COMPAT-P0-05`、`ERROR-P0-02` 至 `ERROR-P0-05`、`TEST-P0-03`、`TEST-P0-04` 中 loader/legacy 条目。

### Task B2.1：冻结 legacy 行为和构造器兼容

**Files**

- Modify: `src/rag/sparse.py`
- Modify: `tests/test_sparse_bm25.py`
- Use: `src/rag/chinese_analyzer.py`

**红灯**

先添加测试：

- `legacy_tokenize()` 精确等于当前 regex；
- `tokenize()` 是其兼容别名；
- `LocalBM25SparseIndex()` 无参数使用 frozen `legacy-regex/v1`；
- 现有英文、数字、`Skill-30410111`、`000-box-construction` 排序不变；
- 非有限/非法 `k1`、`b` 被拒绝；
- build 失败时旧 records/doc_terms/df/avgdl 保持不变；
- empty records、empty query、纯标点 query、单字 query 行为明确；
- empty query 不补零分 records；
- 相同分数继续按原 record 顺序稳定 tie-break，正分不足 `top_k` 时补零分行为不变。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_sparse_bm25.py -k "legacy or parameters or atomic or empty or tie"
```

**最小实现**

- 新增 `TextAnalyzer` protocol/最小契约和 frozen legacy analyzer；
- 构造器接受 `analyzer=None, *, k1=1.5, b=0.75`；`None` 只绑定 legacy；
- build 先在局部变量完成全部分析和统计，再一次性提交状态；
- search 只调用实例 Analyzer；
- 保持 BM25 公式和排序代码语义不变；
- query tokens 为空时立即返回 `[]`。

**绿灯**

```powershell
& $Python1999Wiki -m pytest -q tests/test_sparse_bm25.py -k "legacy or parameters or atomic or empty or tie"
```

### Task B2.2：中文 build/search 同实例与检索红灯

**红灯**

添加本线程多记录 fixture：

- 自然问句和空格关键词都首排槲寄生资料；
- 十四行诗技能问题首排技能记录；
- 未登录词通过相邻 bigram 命中；
- 单字 query 可命中；
- 内部 ID 和文件名精确查询不退化；
- build/search 的 Analyzer object/identity 相同；
- records 继续保存原 `text/search_text`；
- 多 segment API fixture 直接调用 Analyzer，不修改 Retriever。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_sparse_bm25.py -k "chinese or unknown or identifier or filename or same_analyzer"
```

**最小实现**

- 中文路径必须显式传入 `ChineseBM25Analyzer`；
- `build()` 选择 `search_text`，仅缺失/空时回退 `text`；
- `search()` 不重建 Analyzer、不读取默认词典。

**绿灯**

```powershell
& $Python1999Wiki -m pytest -q tests/test_sparse_bm25.py -k "chinese or unknown or identifier or filename or same_analyzer"
```

### Task B2.3：新旧 payload、严格 loader 与原子 save

**红灯**

添加 roundtrip/malformed matrix：

- records-only、child v2、media v3 精确绑定 legacy；
- legacy 文件在新代码下 token、score、排序不变；
- local save 生成 `rag.local-bm25/v2`，包含 analyzer 和 BM25；
- child v3/media v4 可从嵌入词表重建中文 Analyzer；
- save/load 后 tokens、identity、`k1/b`、scores、排序一致；
- loader 不接受传入 Analyzer 覆盖文件身份；
- 新 schema 缺 analyzer/bm25、未知 schema/version、segmenter 不支持、config/hash 错均拒绝；
- 未知 schema 不按 records-only 猜测；
- 新文件不能被 legacy 分支接受；
- save 使用同目录临时文件 + `os.replace`，写失败不留下完整假文件并保留旧目标。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_sparse_bm25.py -k "roundtrip or schema or malformed or override or atomic_save"
```

Expected red：当前 save 为 records-only 且 loader 无 schema 分派。

**最小实现**

- 定义明确 schema dispatch：
  - 无 `schema_version` 且 payload 只有合法 records 形态 → legacy records-only；
  - child v2/media v3 → frozen legacy；
  - local v2/child v3/media v4 → 严格校验 analyzer + BM25；
  - 其他 → fail closed。
- 新 payload 从完整 `dictionary_terms` 重建 Analyzer，不读取词典路径。
- `k1/b` 使用文件值并校验有限合法范围。
- 新 schema 错误只报告 schema/identity 类别，不输出 records/query。
- local save 写 canonical UTF-8 JSON 到目标同目录唯一临时文件，flush/close 后原子 replace；异常清理精确临时文件。

**B2 定向与回归**

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py tests/test_sparse_bm25.py
& $Python1999Wiki -m pytest -q tests/test_retriever.py -k "bm25 or sparse"
git diff --check
```

若 `tests/test_retriever.py -k` 未选择任何测试，则运行整个 `tests/test_retriever.py`；只验证 Retriever 仍能加载 legacy child 文件和英文/数字/ID 路径，不修改 Retriever。

**真实/影子验收**

- 在 `tmp_path` 生成 records-only、v2/v3 legacy、local v2、child v3、media v4 fixture；
- 对同一 records 同时构建 legacy 与中文 index，保存后重载再比较；
- 不写 `data/processed`、正式 candidate、active pointer 或 baseline。

**B2 提交**

```text
feat(rag): integrate analyzers with local BM25 loading
```

提交仅含 `src/rag/sparse.py`、`tests/test_sparse_bm25.py` 和 B2 必需的 B1 局部修正。提交后等待 D 审核。

## 6. B3 — 正式 payload、parity、handoff 与 provenance

**对应 Specs：** `SCHEMA-P0-01` 至 `SCHEMA-P0-04`、`BUILD-P0-01` 至 `BUILD-P0-04`、`PROV-P0-01` 至 `PROV-P0-04`、`ERROR-P0-02`、`ERROR-P0-03`、`ERROR-P0-05`、`TEST-P0-04`、`TEST-P0-05`、`OWN-P0-01`、`OWN-P0-02`。

### Task B3.1：candidate writer 使用单一 Analyzer/BM25 快照

**Files**

- Modify BM25-only sections: `src/huiji_rag/build/artifact_writer.py`
- Modify: `tests/test_huiji_corpus_artifacts.py`
- Use: `src/rag/chinese_analyzer.py`
- Use: `src/rag/sparse.py`

**红灯**

在候选 artifact tests 添加：

- `CandidateArtifactInput`/writer 接收明确 Analyzer identity 与 BM25 参数；
- child payload schema 为 `huiji.bm25-index/v3`；
- media payload schema 为 `huiji.media-binding-bm25/v4`，文件名仍为 `media_binding_bm25.v3.json`；
- 两个 payload 的 analyzer 与 bm25 结构完全相同；
- manifest artifact entry schema 使用 v3/v4；
- manifest semantic metrics 增加 analyzer fingerprint、probe hash、BM25 参数；
- embedding handoff 携带 child analyzer fingerprint；
- 相同 records/config/dictionary 重复构建的 BM25 bytes 相同；
- 只改变 analyzer/词典时 semantic corpus hash 不变，payload SHA 和 manifest/provenance 输入变化。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_huiji_corpus_artifacts.py -k "bm25 or handoff or analyzer or deterministic"
```

**最小实现**

- writer 入口只接收冻结 Analyzer identity/BM25 快照，不读取 Retriever；
- 在开始创建 build root 前完成 identity、`k1/b` 和 probe hash 校验，避免半构建；
- `_bm25_payload()` 对 child/media 复用同一 snapshot；
- `semantic_corpus_sha256` 继续只覆盖 records 语义；
- handoff 只新增 child analyzer fingerprint，不改变 embedding 或 collection 语义；
- 保持 create-new 写入和现有文件路径。

**绿灯**

```powershell
& $Python1999Wiki -m pytest -q tests/test_huiji_corpus_artifacts.py -k "bm25 or handoff or analyzer or deterministic"
```

### Task B3.2：严格 parity 与固定 probes

**红灯**

添加篡改矩阵，分别改变：

- payload schema/record kind；
- analyzer schema/name/version；
- segmenter name/version/HMM；
- config/dictionary/analyzer hash；
- `k1/b`；
- probe output SHA；
- child/media 其中一方 identity；
- records、row count、ordered IDs、semantic hash。

每项都必须被 `verify_candidate_manifest()` 拒绝，并保留现有 records/ID/semantic/path 检查。

固定 probes：

```text
槲寄生的基础资料
十四行诗的技能是什么
Data:Story/304502
Skill-30410111
Banner_今夜星光灿烂.png
```

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_huiji_corpus_artifacts.py -k "parity or probe or drift"
```

**最小实现**

- probe SHA 对固定顺序 token arrays 的 canonical JSON UTF-8 bytes 计算；
- parity 先校验 schema/identity/BM25/probe，再校验 records/ID/semantic；
- child/media fingerprint 必须相等；
- manifest metrics 与重新计算结果精确相等。

### Task B3.3：provenance 新身份与 legacy baseline 解释

**Files**

- Modify BM25-only sections: `src/huiji_rag/provenance.py`
- Modify BM25 tests: `tests/test_huiji_provenance.py`

**红灯**

添加：

- `Bm25Fingerprint` 包含 payload schema、Analyzer fingerprint、config SHA、dictionary SHA、segmenter identity、`k1/b`；
- child v3/media v4 完整指纹；
- records-only/child v2/media v3 输出显式 frozen `legacy-regex/v1` 身份；
- legacy baseline 可继续验证 legacy payload；
- analyzer/config/dictionary/segmenter/`k1/b` 各自漂移产生可区分 issue code；
- 新 schema 缺字段/hash 错/unknown version fail closed；
- records/ID/semantic/path 安全检查仍生效；
- Analyzer 或词典变化导致 payload SHA 和 provenance 变化；
- public error 不包含 records 或 query。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_huiji_provenance.py -k "bm25 or baseline"
```

**最小实现**

- provenance 调用与 runtime loader 共用同一 BM25 metadata/identity validator，避免两套解释；
- 新 schema 按 payload 的 `id_field` 从 records 校验 ID；legacy provenance fixture 继续执行既有 derived `id == source_id_field` 规则，不能为迁移新 schema 而削弱旧 ID 检查；
- 对精确认出的 legacy schema 生成内建、确定的 legacy descriptor；读取缺少新增 identity 字段的旧 baseline 时，仅当 baseline 对应文件也被精确识别为 records-only/child v2/media v3，才为 expected side 合成同一 legacy descriptor，使旧 baseline 继续验证并在新 evidence 中公开标记 `legacy-regex/v1`；
- 不把旧 baseline 的空字段解释为当前默认；旧 baseline 对新 schema、未知 schema 或中文 Analyzer payload 一律不能兼容放行；
- `_compare_bm25_fingerprint()` 为 schema/analyzer/config/dictionary/segmenter/parameters 分别产生稳定 issue；
- 不修改 Milvus、source refs、media 语义或 baseline 安装流程；
- 不更新仓库中的 `config/provenance/*.json`。

**B3 定向与回归**

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py tests/test_sparse_bm25.py
& $Python1999Wiki -m pytest -q tests/test_huiji_corpus_artifacts.py tests/test_huiji_provenance.py
& $Python1999Wiki -m pytest -q tests/test_backend_provenance_gate.py
git diff --check
```

**真实/影子验收**

- 只用 `tests/test_huiji_corpus_artifacts.py` 的 candidate fixture 在 `tmp_path` create-new；
- 验证磁盘路径仍为 child 原路径和 media `.v3.json` 文件名；
- 记录构建前后 `git status --short`，确认 active pointer、生产 baseline、正式 processed artifacts 未变化；
- 不调用 activation、Milvus client 写接口或 baseline install。

**B3 提交**

```text
feat(rag): version BM25 payloads and provenance
```

提交仅含 BM25 writer/provenance 局部及对应测试。提交后等待 D 审核。

## 7. B4 — Jieba 依赖锁与受影响回归

**对应 Specs：** `DEP-P0-01` 至 `DEP-P0-04`、`TEST-P0-06`、`AGENT-P0-01` 至 `AGENT-P0-04`、`PHASE-P0-01`。

### Task B4.1：依赖审计先红灯

**Files**

- Modify: `requirements/runtime.in`
- Modify generated: `requirements/runtime.lock.txt`
- Modify generated: `requirements/dev.lock.txt`
- Modify: `tests/test_runtime_requirements.py`

**红灯**

先在 `tests/test_runtime_requirements.py` 增加：

- `jieba` 是允许且必须的 runtime direct dependency；
- runtime input 精确 pin 为 0.42.1；
- runtime/dev lock 都精确包含 0.42.1；
- lock 仍无 hash/index/option，保持当前 pip-compile 格式；
- dev input 仍只 include runtime input 一次。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_runtime_requirements.py -k "runtime_input or runtime_lock or development_lock"
```

Expected red：runtime input/locks 缺少 Jieba。

### Task B4.2：锁定依赖并验证兼容

**最小实现**

1. 在 `requirements/runtime.in` 增加 `jieba==0.42.1`。
2. 使用锁头记录的 Python/pip/pip-tools 和仓库既有命令：

```powershell
& $Python1999Wiki -m piptools compile `
  --resolver=backtracking `
  --strip-extras `
  --allow-unsafe `
  --no-emit-index-url `
  --output-file requirements/runtime.lock.txt `
  requirements/runtime.in

& $Python1999Wiki -m piptools compile `
  --verbose `
  --resolver=backtracking `
  --strip-extras `
  --allow-unsafe `
  --no-emit-index-url `
  --output-file requirements/dev.lock.txt `
  requirements/dev.in
```

3. 审查 lock diff：只允许 Jieba 及解析器确实需要的来源注释变化；若发生无关版本漂移，先用现有精确环境重试，不手工伪造 lock。
4. 在隔离测试环境安装 lock 后验证：

```powershell
& $Python1999Wiki -c "import jieba; assert jieba.__version__ == '0.42.1'"
```

若解析/安装证明 0.42.1 不兼容，立即 `needs_approval`，不得改版本或删除 word channel。

**绿灯**

```powershell
& $Python1999Wiki -m pytest -q tests/test_runtime_requirements.py
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_analyzer.py tests/test_sparse_bm25.py
```

### Task B4.3：受影响回归与文件所有权审计

Run:

```powershell
& $Python1999Wiki -m pytest -q `
  tests/test_chinese_bm25_analyzer.py `
  tests/test_sparse_bm25.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_provenance.py `
  tests/test_runtime_requirements.py `
  tests/test_backend_provenance_gate.py

& $Python1999Wiki -m pytest -q tests/test_retriever.py tests/test_hybrid_retriever.py
& $Python1999Wiki -m pytest -q tests/test_config.py tests/test_runtime_dependencies.py
git diff --check
git status --short
```

**验收**

- 全部 Analyzer/BM25/artifact/provenance/依赖测试绿；
- Retriever 英文、数字、ID 路径不退化；
- 不依赖 A/C worktree 或真实 `data_pages.jsonl`；
- `git diff --name-only` 只包含 Spec 允许文件；
- 不存在 BGE-M3、sparse vector、Milvus schema 新增。

**失败表现**

- 环境安装失败与产品断言失败分开报告；
- 测试若因临时目录权限失败，使用已批准工作区 `--basetemp` 重跑，不修改测试绕过；
- 无关既有回归只记录，不在本线程顺手修复；若阻断验收则交 D 裁决。

**B4 提交**

```text
build(rag): lock jieba for Chinese BM25 analysis
```

提交仅含 dependency inputs/locks 和 dependency test。提交后等待 D 审核。

## 8. B5 — 影子对照与完成证据

**对应 Specs：** `REPORT-P0-01` 至 `REPORT-P0-03`、`PROV-P0-03`、`TEST-P0-03`、`TEST-P0-05`、`TEST-P0-06`、完成判定 1–16。

### Task B5.1：建立独立影子 fixture 与报告生成测试

**Files**

- Create: `tests/fixtures/bm25_shadow/records.v1.json`
- Create: `tests/fixtures/bm25_shadow/queries.v1.json`
- Create: `tests/test_chinese_bm25_shadow.py`
- Create: `docs/superpowers/reports/2026-07-29-rag-thread-b-bm25-shadow-comparison.md`

fixture 至少覆盖：

- 槲寄生基础资料；
- 十四行诗技能；
- 一个批准未登录词相邻字样本；
- 中文无改善样本；
- 排序变化样本；
- 英文、数字、内部 ID、文件名非退化；
- 多 segment API；
- 零结果/纯标点。

**红灯**

测试先要求报告数据包含：

- Analyzer/config/dictionary identity；
- fixture identity；
- legacy/new token arrays；
- 每个 query 的 top-k IDs/scores；
- 改善、无改善、排序变化、非退化分类；
- build/query elapsed time；
- payload bytes；
- 每文档 token 数分布与膨胀比；
- 测试命令、结果和未覆盖风险；
- 明确 `shadow_only=true`、未激活证明。

Run:

```powershell
& $Python1999Wiki -m pytest -q tests/test_chinese_bm25_shadow.py
```

### Task B5.2：生成并审核最终影子结果

**最小实现**

- 在 pytest `tmp_path` 中对同一 records 构建 legacy 与中文 index；
- 分别生成 records-only legacy 和 local v2/new child v3 shadow payload；
- 重载后再测，避免只比较内存对象；
- 用 `perf_counter()` 记录局部耗时，仅作为样本事实，不设生产 SLA；
- 生成稳定 Markdown 表格；时间值可在报告中按环境样本记录，但确定性断言只覆盖结构、IDs、tokens、hashes 和分类；
- 不生成或激活正式 candidate，不触碰 active pointer/baseline/Milvus。

**通过门禁**

- 核心两条中文问句首要目标改善或保持已批准正确目标；
- 未登录词能通过 bigram 命中；
- ID/文件名/英文无退化；
- 报告同时列出无改善和排序变化；
- token 膨胀可见且与 O(n) 设计一致；
- Analyzer/词典变化使 payload SHA/provenance 改变，semantic corpus hash 保持不变。

若核心中文无改善或技术标识退化，停止并返回 `needs_approval`，不以其余测试通过宣告完成。

### Task B5.3：最终回归与边界审计

```powershell
& $Python1999Wiki -m pytest -q `
  tests/test_chinese_bm25_analyzer.py `
  tests/test_sparse_bm25.py `
  tests/test_chinese_bm25_shadow.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_provenance.py `
  tests/test_runtime_requirements.py `
  tests/test_backend_provenance_gate.py `
  tests/test_retriever.py `
  tests/test_hybrid_retriever.py

rg -n "BGE-M3|bge-m3|sparse_vector|SPARSE_FLOAT_VECTOR" `
  src/rag/chinese_analyzer.py `
  src/rag/sparse.py `
  src/huiji_rag/build/artifact_writer.py `
  src/huiji_rag/provenance.py `
  requirements `
  tests/test_chinese_bm25_analyzer.py `
  tests/test_chinese_bm25_shadow.py

git diff --check
git status --short
git diff --name-only ed569ee23f5d3927f8a332e69ef4de82ac8b6c59...HEAD
```

Expected：

- pytest 全绿；
- `rg` 无命中；
- diff 不含 Planner、Retriever 实现、A/C、`io.py`、activation、生产 baseline、正式 artifacts；
- 工作树除报告提交外 clean。

**B5 提交**

```text
docs(rag): report legacy and Chinese BM25 comparison
```

提交仅含 shadow fixture/test/report。提交后输出 `completed_pending_review`，由 D 独立复核并决定是否合并；本线程不执行生产激活。

## 9. P0 完整追踪矩阵

下表中的“真实验收”均指本线程 fixture、`tmp_path` create-new candidate 或只读影子输入；不得用生产激活代替。

| P0 编号 | 实现位置 / Task | 定向测试 | 真实验收与失败表现 |
|---|---|---|---|
| `ENV-GATE-1999WIKI` | 3.1；每次 resume 与 B1–B5 开始前 | `& $Python1999Wiki -c` 校验 `sys.executable`、`sys.prefix`、3.11.15 | 必须为 `D:\Anaconda32024\envs\1999wiki\python.exe` / `D:\Anaconda32024\envs\1999wiki`；任一不符立即停止并报告 D |
| `SCOPE-P0-01` | B1.3 多 segment API；不改 Retriever | `test_chinese_bm25_analyzer.py -k segments` | fixture 不跨 segment bigram；若需改路由则 `needs_approval` |
| `SCOPE-P0-02` | 全局约束、B5.3 扫描 | `rg` forbidden terms | 任意 sparse vector/model 命中即失败 |
| `DECISION-P0-01` | B1.2 独立 Jieba 0.42.1/HMM false | `-k instance` | 两实例及全局 Tokenizer 隔离；污染即失败 |
| `DECISION-P0-02` | B1.2 每个 Han span 恒发 bigram | `-k bigram` | 已登录/未登录 span 都有 bigram；条件式 fallback 即失败 |
| `DECISION-P0-03` | B1/B2 不加 boost/stopword | token/score 回归 | channel 重叠不增加 TF；排序语义变化即失败 |
| `ARCH-P0-01` | `chinese_analyzer.py` 独立模块 | Analyzer tests | `sparse.py` 不承载中文词典规则；耦合即失败 |
| `ARCH-P0-02` | B1 identity + B2 实例注入 | `-k same_analyzer` | build/search object/identity 相同；全局重建即失败 |
| `ARCH-P0-03` | B2.3 records + metadata 重建 | `-k roundtrip` | 无 pickle，重载结果一致；不可复现即失败 |
| `ANALYZER-P0-01` | B1.1 fixed name/version | `-k identity` | identity 精确匹配；算法改变未升版即失败 |
| `ANALYZER-P0-02` | B1.2 `analyze()->list[str]` | Analyzer API tests | 不暴露 Jieba 对象；类型泄漏即失败 |
| `ANALYZER-P0-03` | B1.3 `analyze_segments()` | `-k segments` | 独立段拼接；跨边界 token 即失败 |
| `ANALYZER-P0-04` | B1.2 空/标点处理 | `-k empty` | 返回空列表；异常或空 token 即失败 |
| `ANALYZER-P0-05` | B1.1 显式输入 | `-k environment` | 改 CWD/env 输出不变；隐式状态依赖即失败 |
| `ANALYZER-P0-06` | B1.1 frozen config | `-k config` | 七项值精确；猜默认即失败 |
| `NORM-P0-01` | B1.2 NFKC，仅 token view | `-k normalize` | 原 records 字节不变；改原文即失败 |
| `NORM-P0-02` | B1.2 lowercase，无简繁/拼音 | `-k normalize` | ASCII case 等价、中文字形保留；扩写即失败 |
| `NORM-P0-03` | B1.2 whitespace/punctuation boundary | `-k boundary` | 无空 token/跨标点 bigram；越界即失败 |
| `NORM-P0-04` | B1.2 technical atoms | `-k technical` | 四个批准样本完整 token；丢失即失败 |
| `NORM-P0-05` | B1.2 受控 pattern | `-k noise` | URL/path/长噪声不成为巨型 token；过宽即失败 |
| `NORM-P0-06` | B1.2 归一 segment offset | offset tests | NFKC 后 offset 稳定；映射原文或错位即失败 |
| `TOKEN-P0-01` | B1.1 词典 loader | `-k dictionary` | UTF-8/NFKC/排序/去重；非法输入 fail closed |
| `TOKEN-P0-02` | 基础词典 v1 | `-k base_terms` | 八个批准词存在、无整句；缺失/污染即失败 |
| `TOKEN-P0-03` | B1.1 extra terms | `-k extra_terms` | 完整合并词表进入 hash；只记路径即失败 |
| `TOKEN-P0-04` | B1.2 overlap matcher | `-k protected_overlap` | 长词优先且同位去重；短词不可恢复即失败 |
| `TOKEN-P0-05` | B1.2 instance tokenizer | `-k instance` | HMM false、无全局 API；污染即失败 |
| `TOKEN-P0-06` | B1.2 保留单字 | `-k single_han` | “雨/她”非空且可搜；丢弃即失败 |
| `TOKEN-P0-07` | B1.2 word offsets | `-k offsets` | 位置可复现；跨 channel 无法去重即失败 |
| `TOKEN-P0-08` | B1.2 相邻 bigrams | `-k bigram` | n-1 顺序完整；缺/多即失败 |
| `TOKEN-P0-09` | B1.2 span boundaries | `-k boundary` | 不跨空格/标点/segment/technical；越界即失败 |
| `TOKEN-P0-10` | B1.2 O(n) | `-k linear` | 长度增长线性；组合子串即失败 |
| `MERGE-P0-01` | B1.2 固定 dedupe key | `-k dedupe` | 精确四元组；错误合并即失败 |
| `MERGE-P0-02` | B1.2 同位去重/异位保留 | `-k term_frequency` | 真实重复 TF 保留；channel boost 即失败 |
| `MERGE-P0-03` | B1.2 稳定排序键 | `-k order` | token arrays 精确；进程漂移即失败 |
| `MERGE-P0-04` | B1/B2 不以重复加权 | token + score tests | channel priority 只排序；隐式 boost 即失败 |
| `MERGE-P0-05` | B1.3/B2.3 确定性 | `-k deterministic or roundtrip` | 进程/重载完全一致；漂移即失败 |
| `IDENTITY-P0-01` | B1.1 dictionary hash | `-k dictionary_sha` | 一词一行末尾 LF；字节不符即失败 |
| `IDENTITY-P0-02` | B1.1 config hash | `-k config_sha` | canonical config 且无 hash 字段；自引用即失败 |
| `IDENTITY-P0-03` | B1.1 fingerprint hash | `-k fingerprint` | 固定字段 canonical JSON；字段遗漏即失败 |
| `IDENTITY-P0-04` | B1.1/B2.3 validator | malformed matrix | 缺字段/错 hash/unsupported 拒绝；猜测即失败 |
| `IDENTITY-P0-05` | B1.1/B2.3 embed terms | roundtrip tests | 离开工作树仍重建；依赖路径即失败 |
| `IDENTITY-P0-06` | B1.1 mutation tests | `-k identity_change` | 词典变则 fingerprint 变、records 变则不变 |
| `INDEX-P0-01` | B2.2 build text selection | `-k build_text` | `search_text` 优先；错误字段即失败 |
| `INDEX-P0-02` | B2.1/B2.2 same analyzer | `-k same_analyzer` | query 不走模块默认；身份分叉即失败 |
| `INDEX-P0-03` | B2.1/B2.3 BM25 params | `-k parameters` | 文件值重载；非法/默认覆盖即失败 |
| `INDEX-P0-04` | B2.1 legacy constructor | `-k legacy_default` | 无参结果不变；默认启用中文即失败 |
| `INDEX-P0-05` | B2.1 legacy alias | `-k legacy_tokenize` | regex 字节行为一致；混入中文规则即失败 |
| `INDEX-P0-06` | B2.1 score/tie regression | `-k score or tie` | 公式/补零/排序不变；差异即失败 |
| `INDEX-P0-07` | B2.1 edge states | `-k empty or single` | 空 query 空结果；补零即失败 |
| `SCHEMA-P0-01` | B3.1 media v4 payload/旧文件名 | artifact tests | manifest schema v4 且路径不变；需改 io 即审批 |
| `SCHEMA-P0-02` | B3.1 shared snapshot | `-k child_media_identity` | child/media identity+params 相同；分叉即失败 |
| `SCHEMA-P0-03` | B3.1/B5 hash comparison | shadow tests | semantic hash 不变、payload SHA 变；反之失败 |
| `SCHEMA-P0-04` | B3.1/B3.2 manifest/handoff/parity | artifact tests | 三处携带/验证 fingerprint；遗漏即失败 |
| `COMPAT-P0-01` | B2.3 schema dispatch | legacy matrix | 三类旧文件都显式 legacy；空身份即失败 |
| `COMPAT-P0-02` | B2.1 frozen regex | legacy tokenize tests | 精确 regex；Jieba/bigram 渗入即失败 |
| `COMPAT-P0-03` | B2.3 legacy ranking | roundtrip/ranking tests | 旧活动 fixture 排序不变；重解释即失败 |
| `COMPAT-P0-04` | B2.3 fail closed | malformed matrix | 新 schema 不降级；接受即失败 |
| `COMPAT-P0-05` | B2.3 no override | `-k override` | 传 Analyzer 被拒绝；覆盖即失败 |
| `BUILD-P0-01` | B3.1 explicit writer input | artifact writer tests | 不读 Retriever；隐式状态即失败 |
| `BUILD-P0-02` | B3.1 one snapshot | child/media parity | 两产物相同；隐式分叉即失败 |
| `BUILD-P0-03` | B3.2 strict parity | tamper matrix | 所列全部身份项可检出；漏检即失败 |
| `BUILD-P0-04` | B3.2 fixed probe SHA | `-k probe` | 固定顺序 token arrays；顺序/算法漂移即失败 |
| `PROV-P0-01` | B3.3 fingerprint fields/issues | provenance tests | 各类漂移可区分；只报通用空值即失败 |
| `PROV-P0-02` | B3.3 preserve semantic checks | existing + new tests | ID/row/semantic/path 仍阻断；削弱即失败 |
| `PROV-P0-03` | B3/B5 shadow candidate | shadow hash tests | 新 SHA/provenance 且不激活；生产写入即失败 |
| `PROV-P0-04` | B3.3 frozen legacy descriptor | legacy baseline tests | 公开 `legacy-regex/v1`；空身份即失败 |
| `DEP-P0-01` | B4.2 inputs/locks | runtime requirements | 两 lock 含 0.42.1；缺失即失败 |
| `DEP-P0-02` | B4.1/B4.2 lock audit | runtime requirements | 不依赖全局包且格式不变；跳过/改格式即失败 |
| `DEP-P0-03` | B1.1/B4 import tests | environment tests | 初始化零网络/缓存；访问即失败 |
| `DEP-P0-04` | B4 stop gate | compile/install preflight | 不兼容即 `needs_approval`，不换库 |
| `QUERY-P0-01` | B1.3 only API | segment tests | Analyzer 不选字段；业务逻辑出现即失败 |
| `QUERY-P0-02` | B1.3 independent segments | segment tests | 顺序保留且无跨边界 bigram |
| `QUERY-P0-03` | B1.3 fixture only | segment fixture | 不改 Retriever/QueryPlan；越界即审批 |
| `QUERY-P0-04` | B1 immutable dictionary | request mutation tests | query/history 不进入 identity；变化即失败 |
| `ERROR-P0-01` | B1.1 dictionary errors | invalid dictionary tests | 明确失败不空回退 |
| `ERROR-P0-02` | B2.3/B3.3 metadata errors | malformed/provenance tests | 安全错误且无 records/query 泄漏 |
| `ERROR-P0-03` | B2.3 exact legacy detection | unknown schema tests | 未知 schema 拒绝，不猜 records-only |
| `ERROR-P0-04` | B2.1 atomic build | `-k atomic_build` | 失败后旧 index 完整；半状态即失败 |
| `ERROR-P0-05` | B2.3 local atomic/B3 create-new | atomic save/artifact tests | 无假完整文件；覆盖生产即失败 |
| `ERROR-P0-06` | B1.2 linear implementation | long span tests | 无灾难 regex/全子串/静默截断 |
| `TEST-P0-01` | B1 Analyzer suite | full analyzer test file | 全部中文/确定性/隔离断言通过 |
| `TEST-P0-02` | B1 technical suite | `-k technical or mixed` | ID/文件名/混排全通过 |
| `TEST-P0-03` | B2 retrieval + B5 shadow | sparse/shadow tests | 中文改善且 ID/文件名不退化 |
| `TEST-P0-04` | B2/B3 schema matrix | sparse/artifact tests | 新旧 schema/identity/parity 全覆盖 |
| `TEST-P0-05` | B3/B5 writer/provenance | artifact/provenance/shadow | create-new、handoff、legacy baseline、字节一致 |
| `TEST-P0-06` | B4 full affected regression | B4.3 commands | locks、Retriever、artifact 全绿且不依赖 A/C/data_pages |
| `REPORT-P0-01` | B5 shadow-only report | shadow test | fixture/tmp only；生产激活即失败 |
| `REPORT-P0-02` | B5 report categories | report structure test | 必含无改善/排序/非退化/膨胀 |
| `REPORT-P0-03` | B5 hard outcome gate | core query assertions | 核心无改善或技术退化即停止 |
| `OWN-P0-01` | 全局停止条件 | diff path audit | 需要 io/activation/deploy 即 `needs_approval` |
| `OWN-P0-02` | B3 BM25-only hunks | diff review + tests | 触及 C projection/media 语义即失败 |
| `OWN-P0-03` | B1 explicit terms only | dictionary tests | 不读 C 动态词典；依赖即失败 |
| `AGENT-P0-01` | 全局执行约束 | D session inspection | 单 session、指定模型/速度/沙箱；不符即暂停 |
| `AGENT-P0-02` | 全局执行约束 | D session inspection | fast/multi-agent false，无子代理/跨 worktree |
| `AGENT-P0-03` | 全局执行约束 | 状态报告 | 无人为 token/test 限制 |
| `AGENT-P0-04` | 本 Plan + B1→B5 | D 审核记录 | Plan 未批准不改实现；越序即失败 |
| `PHASE-P0-01` | 每阶段提交/审核停点 | 各阶段回归 | 未经 D 审核不进入下一阶段 |

## 10. 小提交与最终交付

计划提交边界：

```text
feat(rag): add deterministic Chinese BM25 analyzer
feat(rag): integrate analyzers with local BM25 loading
feat(rag): version BM25 payloads and provenance
build(rag): lock jieba for Chinese BM25 analysis
docs(rag): report legacy and Chinese BM25 comparison
```

每个提交必须：

- 只包含该阶段文件；
- 不包含 A/C、Planner、Retriever 实现、activation、生产 baseline、正式 artifacts；
- 在提交前通过该阶段定向测试和前序回归；
- 提交后工作树 clean；
- 由 D 审核后才继续。

线程 B 最终只交付代码、测试、锁文件、fixture 和影子报告；不构建/激活正式索引，不更新生产 baseline，不写 Milvus。
