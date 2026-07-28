# 线程 B：中文 BM25 Analyzer 设计

日期：2026-07-29

状态：用户审核候选

负责人：线程 B；规格与集成审核：线程 D

设计依赖：

- `docs/superpowers/specs/2026-07-29-rag-cli-supervision-design.md`
- `docs/superpowers/plans/2026-07-29-rag-cli-supervision.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-a-routing-design.md`

## 1. 背景与目标

当前 `src/rag/sparse.py` 使用以下正则完成 BM25 分词：

```python
re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]+", text.lower())
```

连续中文会被视为一个 token。例如：

```text
槲寄生的基础资料
→ ["槲寄生的基础资料"]
```

这会导致自然语言问题与语料中的较短实体名、属性词和未登录词缺少共享 token。

已核实的当前实现事实：

1. `LocalBM25SparseIndex.build()` 和 `search()` 都调用模块级 `tokenize()`，中文索引端与查询端具有相同缺陷。
2. `LocalBM25SparseIndex.save()` 只保存 records；`load()` 使用当前代码重新分词，没有保存 Analyzer 身份。
3. 正式 child BM25 payload 使用 `huiji.bm25-index/v2`，media binding BM25 payload 使用 `huiji.media-binding-bm25/v3`，两者都保存 records、行数、ID 哈希和语义语料哈希，但没有 Analyzer 元数据。
4. Analyzer 代码或词典改变时，现有 BM25 文件字节和 provenance 可以保持不变，但运行时检索行为会改变。
5. 当前运行时依赖清单没有声明 Jieba；本机虽存在 Jieba 0.42.1，但不能把未锁定的全局环境当成项目依赖。
6. Retriever 当前只加载 child BM25；media binding BM25 仍属于正式候选闭包和 provenance，不能生成与 child 不一致的无身份索引。
7. 当前正式候选、active pointer 和生产 baseline 受保护，本线程不得直接覆盖或激活。

线程 B 的目标是：

1. 将中文整串 tokenization 替换为确定性的混合 Analyzer：

   ```text
   领域保护词 + 中文词语 + 连续中文二元组 fallback
   ```

2. 保证索引端和查询端使用同一 Analyzer 实例、配置和词典。
3. 保留英文、数字、内部 ID、文件名和中英混排的可检索性。
4. 将 Analyzer、词典、分词器版本和 BM25 参数纳入可审计的产物身份。
5. 明确新旧 BM25 产物加载规则，禁止旧文件被新 Analyzer 静默重新解释。
6. 使用独立 fixture 和影子产物证明中文召回改善，不依赖线程 A/C 未合并代码。

## 2. 范围与非目标

### 2.1 线程 B 负责

- 新增独立中文 Analyzer 模块；
- 领域保护词的稳定、版本化基础词典；
- Jieba 运行时依赖及 lock 更新；
- Unicode、英文、数字、内部 ID 和文件名归一化；
- 中文词语分割；
- 连续中文二元组 fallback；
- Analyzer token 顺序、重复项和边界规则；
- `LocalBM25SparseIndex` 的显式 Analyzer 注入；
- 索引、查询、保存和加载一致性；
- BM25 payload 中的 Analyzer 和 BM25 参数元数据；
- child/media BM25 payload parity 与 provenance 指纹；
- 旧产物 legacy Analyzer 兼容；
- Analyzer、BM25、产物和中文检索回归；
- 新旧 Analyzer 的局部对照报告和影子产物说明。

### 2.2 线程 B 不负责

- Planner、QueryPlan、Route Policy 和复合问题执行；
- Retriever 的 Owner Gate、Topic scope 或 route 选择；
- “原问题 + sparse query + entity + aliases”的运行时查询拼接；
- 线程 C 的 Topic/Story/Page/Media 投影；
- 依赖线程 C 动态生成词典才能成立的首版设计；
- BGE-M3 Sparse、Milvus sparse schema 或其他稀疏向量；
- Dense embedding、reranker 或 RRF 权重调优；
- 正式 BM25 激活、active pointer、生产 baseline 或 Milvus 写入；
- 自动抓取、资源下载或媒体上传；
- 修改线程 A/C worktree 中尚未合并的文件。

`SCOPE-P0-01`：B 可以为测试提供多段文本 Analyzer 接口，但不得修改 `retriever.py` 选择或拼接 sparse query segments 的业务逻辑。最终接线由线程 A 或 D 在 B 合并后完成。

`SCOPE-P0-02`：BGE-M3 Sparse 已明确搁置，不得以“便于未来迁移”为由引入模型下载、向量字段或新的检索服务。

## 3. 方案选择

评估过三类方案：

| 方案 | 优点 | 主要问题 | 结论 |
|---|---|---|---|
| 仅正则 + 中文二元组 | 依赖少、工程量最低 | 缺少词语级语义，常见词和专名只能靠局部重叠 | 不采用 |
| 领域保护词 + Jieba 词语 + 二元组 fallback | 兼顾精确专名、正常词语和未登录词召回 | 需要锁定依赖、词典和重复 token 规则 | P0 采用 |
| BGE-M3 Sparse 等模型稀疏检索 | 语义和词汇能力更强 | 构建、存储、运行时和评估工程量显著扩大 | 本轮排除 |

`DECISION-P0-01`：默认实现使用实例级 Jieba 0.42.1，关闭 HMM，新建独立 `Tokenizer` 实例。禁止调用 `jieba.add_word()`、`jieba.load_userdict()` 等会修改进程级默认分词器的接口。

`DECISION-P0-02`：二元组不是只在词典失败时临时启用，而是对每个连续中文 span 稳定生成，保证未登录词在词语分割变化时仍有局部召回能力。

`DECISION-P0-03`：首版不增加 BM25 字段权重、channel boost、停用词表或学习排序。P0 先建立正确且可复现的 token 基础，权重调优必须使用独立评估后再批准。

## 4. 总体架构

```text
原始文本或查询 segments
  │
  ▼
文本归一化
  ├─ Unicode NFKC
  ├─ ASCII lowercase
  └─ 稳定空白/标点边界
  │
  ▼
受保护原子识别
  ├─ 领域词
  ├─ Data:Story/304502
  ├─ Skill-30410111
  └─ 文件名/英文/数字
  │
  ▼
中文词语分割（Jieba instance，HMM=false）
  │
  ▼
连续中文二元组 fallback
  │
  ▼
按位置合并并去除跨 channel 重复
  │
  ├─ build(records) → doc terms
  └─ search(query)  → query terms
  │
  ▼
LocalBM25SparseIndex
  │
  ▼
带 Analyzer 身份的 BM25 payload / provenance
```

`ARCH-P0-01`：Analyzer 是独立模块，BM25 只依赖稳定的 `analyze()` 契约，不在 `sparse.py` 中继续堆叠中文规则、词典加载和哈希逻辑。

`ARCH-P0-02`：Analyzer 配置必须是不可变、可序列化对象。一个 `LocalBM25SparseIndex` 构造后只能使用其持有的 Analyzer；build 和 search 不得分别从全局配置重新创建 Analyzer。

`ARCH-P0-03`：新 BM25 文件仍保存 records，并在加载时确定性重建内存倒排统计；P0 不保存 Python pickle 或新的二进制倒排格式。可复现性由 records、Analyzer 元数据和 BM25 参数共同保证。

## 5. Analyzer 公共契约

建议新增：

```text
src/rag/chinese_analyzer.py
src/rag/resources/bm25_domain_terms.v1.txt
```

核心接口：

```python
class AnalyzerConfig:
    name
    version
    unicode_normalization
    ascii_lowercase
    segmenter_name
    segmenter_version
    segmenter_hmm
    emit_han_bigrams
    preserve_identifiers
    preserve_filenames
    technical_pattern_version
    merge_rule_version

class AnalyzerIdentity:
    schema_version
    name
    version
    config
    config_sha256
    dictionary_terms
    dictionary_sha256
    fingerprint_sha256

class ChineseBM25Analyzer:
    identity

    def analyze(self, text: str) -> list[str]
    def analyze_segments(self, segments: Iterable[str]) -> list[str]
```

`ANALYZER-P0-01`：默认 Analyzer 名称固定为 `zh-domain-word-bigram`，首版算法版本固定为 `1`。算法行为发生变化时必须递增 version，不能只修改实现而保留身份。

`ANALYZER-P0-02`：`analyze()` 输入和输出均为普通字符串/token 列表，不暴露 Jieba 内部对象。调用者不需要知道具体分词库。

`ANALYZER-P0-03`：`analyze_segments()` 分别分析每个非空 segment，再按输入顺序拼接 token。不同 segment 之间不得生成跨边界中文二元组。

`ANALYZER-P0-04`：空字符串、纯空白和纯标点返回空 token 列表；不抛出分词异常。

`ANALYZER-P0-05`：Analyzer 不读取进程环境变量、当前工作目录、在线资源或运行时可变全局状态。

`ANALYZER-P0-06`：首版 config 值固定为：

```json
{
  "unicode_normalization": "NFKC",
  "ascii_lowercase": true,
  "segmenter_hmm": false,
  "emit_han_bigrams": true,
  "preserve_identifiers": true,
  "preserve_filenames": true,
  "technical_pattern_version": "1",
  "merge_rule_version": "1"
}
```

## 6. 文本归一化

`NORM-P0-01`：所有输入先执行 Unicode NFKC。归一化只用于 token 生成，不修改 records 中保存的原始 `text/search_text`。

`NORM-P0-02`：ASCII 字母使用 Unicode-safe lowercase；中文字符保持原字形，不进行简繁转换、拼音转换或同义词扩写。

`NORM-P0-03`：连续空白归一为边界。普通标点作为 token 边界，不产生空 token。

`NORM-P0-04`：以下技术标识应保留完整归一 token，同时允许其可安全拆分部分参与匹配：

```text
Data:Story/304502
Skill-30410111
000-box-construction
Banner_今夜星光灿烂.png
```

完整技术 token 不得因 `:`、`/`、`-`、`_` 或文件扩展名被完全丢失。

`NORM-P0-05`：URL、Windows 路径和任意长无空格文本不作为首版通用原子规则。只保护受控内部 ID 和文件名形态，避免把整段噪声重新变成一个巨型 token。

`NORM-P0-06`：所有字符 offset 都相对于归一化后的 segment，不映射回原始字符串。Analyzer 只公开 token；offset 仅供内部去重和测试。

## 7. 三类中文 token

### 7.1 领域保护词

`TOKEN-P0-01`：领域词典按 UTF-8 文本文件保存，一行一个词。加载时执行 NFKC、trim、去空行、去重复并按 Unicode code point 排序。

`TOKEN-P0-02`：基础词典只包含稳定且可审查的项目词，例如角色名、核心世界观词、常用资料字段和已确认内部术语。首版至少覆盖 `十四行诗`、`槲寄生`、`暴雨`、`重返未来：1999`、`神秘学家`、`基础资料`、`技能` 和 `艺术品`。禁止把整句描述、用户历史或抓取顺序写入词典。

`TOKEN-P0-03`：调用者可以显式注入额外保护词。额外词与基础词合并后的完整规范词表必须进入 AnalyzerIdentity，不能只记录外部文件路径。

`TOKEN-P0-04`：保护词匹配允许重叠，但相同起止位置和相同 token 只保留一次。更长保护词优先排序，短词仍可通过中文词语或二元组获得匹配。

### 7.2 中文词语

`TOKEN-P0-05`：Jieba 使用独立实例，`HMM=False`。基础词典和显式额外词只加载到该实例，不改变默认全局 Tokenizer。

`TOKEN-P0-06`：单字分词结果保留。查询“雨”“她”等单字不得因只生成二元组而变成空查询。

`TOKEN-P0-07`：分词结果必须携带或恢复稳定字符位置，供跨 channel 去重和输出排序使用。

### 7.3 二元组 fallback

`TOKEN-P0-08`：对每个连续 Han span 长度 `n >= 2` 生成 `n - 1` 个相邻二元组。例如：

```text
槲寄生的基础资料
→ 槲寄、寄生、生的、的基、基础、础资、资料
```

`TOKEN-P0-09`：二元组不能跨越空格、普通标点、segment 边界或非中文技术标识边界。

`TOKEN-P0-10`：不得生成全组合 n-gram、跳字组合或无限长度子串。二元组阶段必须保持 O(n) 输出规模。

## 8. token 顺序与重复规则

同一个词可能同时来自保护词、Jieba 和二元组。如果直接将三个 channel 相加，会无意中把 channel 重叠当成 BM25 权重。

`MERGE-P0-01`：token 以字符位置为基础合并。去重键固定为：

```text
(segment_index, start_offset, end_offset, normalized_token)
```

`MERGE-P0-02`：同一文本位置、同一 token 即使被多个 channel 产生，也只计一次；相同 token 在文本不同位置真实重复出现时保留多次，从而保留文档 term frequency。

`MERGE-P0-03`：输出顺序固定为：

```text
segment_index
→ start_offset
→ channel priority（protected、word、bigram、technical）
→ end_offset 降序
→ normalized_token
```

`MERGE-P0-04`：channel priority 只决定确定性顺序，不构成额外得分权重。P0 不通过重复 token 隐式模拟 boost。

`MERGE-P0-05`：同一输入、配置和词典在重复调用、不同进程和保存/加载后必须产生完全相同的 token 序列。

## 9. 词典、配置与身份哈希

AnalyzerIdentity 的 JSON 形态固定为：

```json
{
  "schema_version": "rag.bm25-analyzer/v1",
  "name": "zh-domain-word-bigram",
  "version": "1",
  "segmenter": {
    "name": "jieba",
    "version": "0.42.1",
    "hmm": false
  },
  "config": {},
  "config_sha256": "<sha256>",
  "dictionary_terms": [],
  "dictionary_sha256": "<sha256>",
  "fingerprint_sha256": "<sha256>"
}
```

`IDENTITY-P0-01`：`dictionary_sha256` 对规范化、排序、去重后的词表按“一词一行并以换行结束”的 UTF-8 bytes 计算。

`IDENTITY-P0-02`：`config_sha256` 对不包含任何 hash 字段的 canonical config JSON 计算。

`IDENTITY-P0-03`：`fingerprint_sha256` 对以下 canonical JSON 计算：

```text
schema_version
name
version
segmenter
config
config_sha256
dictionary_terms
dictionary_sha256
```

`IDENTITY-P0-04`：加载时重新计算三个哈希并逐项比较。缺字段、哈希错误、segmenter 版本不支持或 config 不受支持时拒绝加载，不使用当前默认值猜测。

`IDENTITY-P0-05`：新 payload 嵌入完整规范 `dictionary_terms`，以保证离开原工作树后仍能重建。词典文件路径不进入可移植身份。

`IDENTITY-P0-06`：基础词典或额外词变化必须改变 dictionary 和 analyzer fingerprint；只调整 records 不应改变 Analyzer fingerprint。

## 10. LocalBM25SparseIndex 集成

建议契约：

```python
LocalBM25SparseIndex(
    analyzer: TextAnalyzer,
    *,
    k1: float = 1.5,
    b: float = 0.75,
)
```

`INDEX-P0-01`：`build()` 对每个 record 的 `search_text`，缺失时再使用 `text`，调用实例 Analyzer。

`INDEX-P0-02`：`search()` 使用同一实例 Analyzer。禁止通过模块级默认 Analyzer 重新解释 query。

`INDEX-P0-03`：`k1` 和 `b` 必须校验为有限合法数值并进入 payload；加载后使用文件值，不能使用代码当前默认值。

`INDEX-P0-04`：为现有 `LocalBM25SparseIndex()` 无参数调用保留 legacy 默认，以保证只部署代码而未切换产物时行为不变。新中文 index 必须显式传入 `ChineseBM25Analyzer`，或由新 schema loader 从文件身份重建；不得依赖构造器默认值启用新 Analyzer。

`INDEX-P0-05`：模块级 `tokenize()` 在迁移期保留并精确绑定 legacy regex；新增明确的 `legacy_tokenize()` 实现，`tokenize()` 作为受控兼容别名。新中文路径只能调用 Analyzer 对象，不得借用该别名。

`INDEX-P0-06`：保持现有 BM25 公式、正分排序、稳定 tie-break 和不足 `top_k` 时补零分记录的行为。Analyzer 线程不借机改变融合或排序语义。

`INDEX-P0-07`：build 空 records、空 query、纯标点 query 和单字 query 的行为必须确定；空 query 返回空结果，不能用零分 records 填充。

## 11. 新旧产物 schema

### 11.1 新 schema

P0 新 payload 至少包含：

```json
{
  "schema_version": "huiji.bm25-index/v3",
  "record_kind": "child",
  "analyzer": {},
  "bm25": {
    "k1": 1.5,
    "b": 0.75
  },
  "id_field": "child_id",
  "row_count": 0,
  "ordered_ids_sha256": "<sha256>",
  "semantic_corpus_sha256": "<sha256>",
  "records": []
}
```

schema 约定：

| record kind | 旧 schema | 新 schema | 文件路径 |
|---|---|---|---|
| child | `huiji.bm25-index/v2` | `huiji.bm25-index/v3` | `indexes/child_text_bm25.json` |
| media binding | `huiji.media-binding-bm25/v3` | `huiji.media-binding-bm25/v4` | 暂保持 `indexes/media_binding_bm25.v3.json` |
| local roundtrip fixture | 无显式 schema/records-only | `rag.local-bm25/v2` | 调用者指定 |

`SCHEMA-P0-01`：media 文件名暂不随 payload schema 改名，避免线程 B 扩大修改 activation、runtime path 和部署脚本。manifest 中记录的 schema_version 必须为 v4，不能从文件名推断 payload schema。

`SCHEMA-P0-02`：child 和 media payload 使用同一个 AnalyzerIdentity 与 BM25 参数结构。即使 media BM25 当前未被 Retriever 加载，也不能继续生成无 Analyzer 身份的正式闭包文件。

`SCHEMA-P0-03`：`semantic_corpus_sha256` 只表示 records 语义，不包含 Analyzer、词典或 BM25 参数；Analyzer 改变时该值可以不变，但 payload SHA、Analyzer fingerprint 和 provenance 必须改变。

`SCHEMA-P0-04`：正式构建器、build manifest、embedding handoff 和构建后 parity 必须携带或验证 child/media Analyzer fingerprint，不能仅验证 records 相等。

### 11.2 legacy 加载

`COMPAT-P0-01`：以下文件明确绑定 `legacy-regex/v1`：

- records-only 的旧本地文件；
- `huiji.bm25-index/v2`；
- `huiji.media-binding-bm25/v3`。

`COMPAT-P0-02`：legacy Analyzer 精确保留当前正则行为：

```text
[A-Za-z0-9_\-]+ | [\u4e00-\u9fff]+
```

不得向旧 schema 注入 Jieba、领域词或二元组。

`COMPAT-P0-03`：新代码部署但仍加载旧活动 v2 child BM25 时，检索结果必须保持 legacy 行为。新中文 Analyzer 只有加载新 v3 payload或显式构建新 index 时才生效。

`COMPAT-P0-04`：新 schema 缺少 Analyzer/BM25 元数据、哈希不匹配或版本未知时 fail closed；不得降级为 legacy，也不得使用当前默认中文 Analyzer。

`COMPAT-P0-05`：loader 不支持“用户传入 Analyzer 覆盖文件 Analyzer”。如果需要重新分析，必须显式构建并保存一个新 payload。

## 12. 构建器、parity 与 provenance

`BUILD-P0-01`：`artifact_writer.py` 的 BM25 payload 生成必须接收明确 AnalyzerIdentity 和 BM25 参数，不读取运行时 Retriever 状态。

`BUILD-P0-02`：child/media 构建使用同一 Analyzer 配置快照；如未来确需不同配置，必须使用不同 fingerprint 并升级 Spec，不能首版隐式分叉。

`BUILD-P0-03`：构建后 parity 除现有 records、row_count、ordered IDs 和 semantic corpus 外，至少验证：

- payload schema；
- record kind；
- Analyzer schema/name/version；
- segmenter name/version/HMM；
- config/dictionary/analyzer fingerprint；
- BM25 k1/b；
- Analyzer 对固定 probe strings 的输出摘要。

`BUILD-P0-04`：probe strings 至少包含：

```text
槲寄生的基础资料
十四行诗的技能是什么
Data:Story/304502
Skill-30410111
Banner_今夜星光灿烂.png
```

probe 输出摘要对“按上述固定顺序组成的 token arrays”执行 canonical JSON UTF-8 SHA-256。它用于发现 loader 与 writer 的解释漂移，不替代完整 Analyzer fingerprint。

`PROV-P0-01`：`Bm25Fingerprint` 增加 payload schema、Analyzer fingerprint、config SHA、dictionary SHA、segmenter identity、k1 和 b。baseline 比较必须能指出具体是哪一类身份发生变化。

`PROV-P0-02`：provenance 继续验证 BM25 records 与 source artifact 语义一致；新增 Analyzer 身份验证不能削弱现有 ID、row count、semantic hash 或路径安全检查。

`PROV-P0-03`：Analyzer 变化后的影子候选必须产生新的 BM25 文件 SHA 和 provenance。线程 B 不更新活动生产 baseline，不改 active pointer。

`PROV-P0-04`：旧 baseline 可以继续验证 legacy payload，但结果必须公开标记 `legacy-regex/v1`；不能把 Analyzer 身份留空解释为“与当前默认相同”。

## 13. 依赖与可复现性

`DEP-P0-01`：在 `requirements/runtime.in` 声明 `jieba==0.42.1`，并使用仓库既有依赖锁流程更新 `runtime.lock.txt` 和受影响的 dev lock。

`DEP-P0-02`：测试不得因为开发机已全局安装 Jieba 而通过。依赖审计必须证明 runtime/dev lock 中存在精确版本；锁文件继续使用仓库当前不生成 wheel hash 的 pip-compile 策略，本线程不得顺带改变全仓依赖锁格式。

`DEP-P0-03`：Analyzer 初始化不得下载模型、访问网络或依赖用户目录缓存。

`DEP-P0-04`：如果锁依赖流程证明 Jieba 0.42.1 与项目 Python 运行时不兼容，线程 B 必须暂停并向 D 报告证据；不得擅自换用未审查分词器或省略中文词语 channel。

## 14. 查询组合边界

线程 A 可能需要组合：

```text
用户原始问题
Planner sparse_query
entity_name
aliases
```

`QUERY-P0-01`：线程 B 只提供 `analyze_segments()`，不决定哪些字段进入查询。

`QUERY-P0-02`：调用者传入多个 segment 时，每段独立分析，保留段落顺序，不在边界生成二元组。

`QUERY-P0-03`：B 的 fixture 可以证明多 segment API 可用，但不得修改 `retriever.py`、`query_plan.py` 或线程 A 的 RequestPlan。

`QUERY-P0-04`：领域保护词属于 Analyzer 配置；query segments 属于每次请求。不得把用户问题或会话历史临时写入词典。

## 15. 错误处理

`ERROR-P0-01`：词典文件不存在、编码错误或包含非法控制字符时，显式失败并指出词典身份问题，不回退到空词典。

`ERROR-P0-02`：新 payload Analyzer/BM25 metadata 缺失、hash 错误或 schema 不支持时拒绝加载，错误消息不得包含完整 records 或用户查询。

`ERROR-P0-03`：legacy schema 只有在精确识别时才能进入 legacy loader；未知 schema 不按 records-only 猜测。

`ERROR-P0-04`：Analyzer 对单条文本失败时，index build 整体失败并保留原 index 状态，不能提交半构建 doc_terms/df。

`ERROR-P0-05`：正式 artifact writer 继续使用 create-new 写入；本地 `save()` 使用同目录临时文件和原子替换保持现有可覆盖语义。失败不得留下可被 loader 误认为完整的新 schema 文件。

`ERROR-P0-06`：超长文本处理必须保持线性，不使用灾难性回溯正则或全子串生成。P0 不静默截断 index 文本；资源上限问题以显式异常和测试暴露。

## 16. 测试与验收

### 16.1 Analyzer 单元测试

`TEST-P0-01`：

- `槲寄生的基础资料` 不再成为单一中文长 token；
- 输出包含保护词 `槲寄生`；
- 输出包含正常中文词语；
- 输出包含 `槲寄/寄生/.../资料` 二元组；
- `十四行诗的技能是什么` 包含完整角色名和问题关键词；
- 单字中文可检索；
- 空文本、纯标点返回空；
- 全角 ASCII 经 NFKC 后与半角一致；
- 同位置跨 channel token 只计一次；
- 相同词在不同位置保留真实重复；
- 不同进程输出完全一致；
- 两个 Analyzer 实例的额外词典互不污染；
- 全局 Jieba 默认 Tokenizer 未被修改。

### 16.2 技术标识与混排

`TEST-P0-02`：

- `Data:Story/304502` 保留完整技术 token；
- `Skill-30410111` 保留完整技术 token；
- `000-box-construction` 保留；
- `Banner_今夜星光灿烂.png` 保留完整文件名并产生中文可检索 token；
- 英文大小写归一；
- 中文、英文、数字、下划线、连字符和文件扩展名混排稳定；
- URL 或无边界噪声不会退化为任意长巨型 token。

### 16.3 BM25 检索

`TEST-P0-03`：

- “槲寄生的基础资料”命中包含“槲寄生 基础资料”的目标文档；
- “槲寄生 基础资料”和自然问句的首要目标一致；
- “十四行诗的技能是什么”命中十四行诗技能 fixture；
- 未登录词可通过二元组命中包含相邻字的文档；
- 内部 ID 和图片文件名精确查询不退化；
- empty query 不补零分记录；
- build/search 使用完全相同 Analyzer identity；
- 保存/加载后的 token、BM25 参数、score 和稳定排序一致。

### 16.4 schema 与兼容

`TEST-P0-04`：

- 新 child v3 和 media v4 payload 包含完整 Analyzer/BM25 元数据；
- records-only、child v2 和 media v3 使用 `legacy-regex/v1`；
- 旧文件在新代码下仍产生 legacy token 和排序；
- 新文件不会被 legacy loader 接受；
- 新 schema 缺字段、未知 version、config/dictionary/fingerprint hash 错误均拒绝；
- 显式 Analyzer 不能覆盖文件 Analyzer；
- child/media parity 校验识别身份漂移；
- semantic corpus hash 不因只改变 Analyzer 而改变；
- payload SHA 和 provenance 会因 Analyzer 或词典变化而改变。

### 16.5 构建与 provenance

`TEST-P0-05`：

- candidate writer 生成正确 payload schema 和 manifest entry；
- embedding handoff 携带 child Analyzer fingerprint；
- provenance 输出完整 Analyzer/BM25 identity；
- legacy baseline 明确标记 legacy Analyzer；
- 现有 records/ID/semantic parity 继续生效；
- 重复构建在相同 records/config/dictionary 下字节一致；
- 不修改正式 active pointer、生产 baseline 或活动索引文件。

### 16.6 依赖与回归

`TEST-P0-06`：

- runtime/dev lock 含精确 Jieba 版本，且未擅自改变现有 lock 格式；
- `tests/test_sparse_bm25.py` 全部通过；
- 受影响的 corpus artifact、provenance、runtime artifact 测试全部通过；
- Retriever 的现有英文、数字和 ID BM25 用例不退化；
- B 不需要线程 A/C worktree 或真实 `data_pages.jsonl`。

## 17. 对照报告

线程 B 必须输出一个可审查的局部对照报告，至少记录：

```text
Analyzer identity
dictionary identity
fixture/candidate identity
legacy 与新 Analyzer 的 token 对照
典型中文 query 的 top-k 对照
内部 ID/文件名非退化结果
索引构建耗时
查询耗时
payload 大小
token 数量分布
测试命令与结果
未覆盖风险
```

`REPORT-P0-01`：报告使用线程 B 自带 fixture 或只读影子候选，不以生产激活证明效果。

`REPORT-P0-02`：不得只报告改善样本；必须包含中文无改善、排序变化、ID/英文非退化和 token 膨胀情况。

`REPORT-P0-03`：如果新 Analyzer 在已批准核心中文 fixture 上没有改善，或 ID/文件名出现退化，线程 B 不得以“测试大部分通过”声明完成。

## 18. 文件所有权

线程 B 可以修改：

```text
src/rag/chinese_analyzer.py
src/rag/resources/bm25_domain_terms.v1.txt
src/rag/sparse.py
requirements/runtime.in
requirements/runtime.lock.txt
requirements/dev.lock.txt
src/huiji_rag/build/artifact_writer.py 中 BM25 payload/parity 部分
src/huiji_rag/provenance.py 中 Bm25Fingerprint/验证部分
tests/test_chinese_bm25_analyzer.py
tests/test_sparse_bm25.py
BM25 相关 artifact/provenance tests
线程 B 自带 fixture 和对照报告
```

线程 B 禁止修改：

```text
src/rag/query_plan.py
src/rag/route_policy.py
src/rag/request_plan.py
src/rag/execution.py
src/rag/chain.py
src/rag/retriever.py 的路由、Owner Gate 和 query 选择
src/huiji_rag/build/projection.py
src/huiji_rag/build/media_v3.py
src/huiji_rag/build/orchestrator.py 的语义投影
src/huiji_rag/models.py 的 Topic/Story/Media 公共字段
正式 processed artifacts
active pointer
生产 provenance baseline
Milvus collection
线程 A/C worktree 文件
```

`OWN-P0-01`：如果新 payload schema 需要修改 `src/huiji_rag/io.py`、activation 路径或部署脚本，线程 B 必须暂停并提交 D 审核。P0 默认通过保持现有文件路径避免扩大共享文件范围。

`OWN-P0-02`：`artifact_writer.py` 和 `provenance.py` 只允许修改 BM25 相关局部。线程 B 不处理 C 的 projection、media binding 语义或来源恢复。

`OWN-P0-03`：线程 B 不读取线程 C 动态词典。额外保护词只能来自本线程 fixture、已提交基础词典或调用者显式、可哈希输入。

## 19. CLI 执行约束

`AGENT-P0-01`：线程 B 由一个长期 Codex CLI session 在 `codex/rag-b-bm25` 独立 worktree 中执行，模型固定请求 `gpt-5.6-sol`，使用标准速度和 `workspace-write`。

`AGENT-P0-02`：启动参数必须显式关闭 `fast_mode` 和 `multi_agent`。禁止创建子代理、再次调用 Codex CLI 分派任务或读取 A/C 未合并 worktree。

启动基线：

```powershell
codex exec `
  -m gpt-5.6-sol `
  --disable fast_mode `
  --disable multi_agent `
  --sandbox workspace-write `
  --json `
  --cd "D:\1999Wiki.worktrees\rag-b-bm25"
```

`AGENT-P0-03`：不设置人为 Token budget，不限制正常调查深度、测试次数和必要返工；通过 session resume、结构化状态和避免重复上下文控制消耗。

`AGENT-P0-04`：线程 B 首轮只编写自己的 Implementation Plan。Plan 经 D 审核前不得修改实现代码；Plan 必须按 B1 至 B5 串行执行。

## 20. 实施阶段与提交边界

线程 B 内部按以下顺序串行推进：

```text
B1 Analyzer contract + normalization + token tests
  → B2 LocalBM25SparseIndex integration + legacy loader
  → B3 payload schema + artifact parity + provenance
  → B4 dependency locks + affected regression
  → B5 shadow comparison report
```

原因：

- B2 必须使用 B1 已冻结的 Analyzer identity；
- B3 必须使用 B2 的序列化和 loader 契约；
- B4 在完整调用路径稳定后验证环境闭包；
- B5 必须比较最终产物，而不是中间实现；
- 同时拆分多个 BM25 工作树会造成 `sparse.py`、artifact writer 和 provenance 冲突。

建议提交：

```text
feat(rag): add deterministic Chinese BM25 analyzer
feat(rag): version BM25 analyzer payloads and legacy loading
test(rag): verify Chinese BM25 retrieval and provenance
docs(rag): report legacy and Chinese BM25 comparison
```

`PHASE-P0-01`：每个阶段必须先完成对应测试和 D 审查再进入下一阶段。线程 B 不创建子代理，不把阶段拆成额外 CLI worker。

## 21. P1 与 P2 汇总

P1 可选：

- 基于评估的 token channel 权重；
- 受控停用词；
- C 合并后从稳定 entity/topic 字段构建额外词典；
- 更大真实查询集上的 Recall@K、MRR 和延迟门槛；
- 独立的词典发布与审查工具。

P2 延后：

- BGE-M3 Sparse；
- learned sparse retrieval；
- 模型分词与 BM25 混合权重学习；
- 在线词典学习；
- 查询日志驱动的自动扩词；
- 正式生产自动激活。

P1 只有全部 P0 完成且获得新批准后才可进入 Plan；P2 不得进入本轮实施任务。

## 22. 完成判定

线程 B 只有同时满足以下条件才能声明完成：

1. 中文自然问题不再整串成为一个 token。
2. 领域保护词、中文词语和连续中文二元组三类 token 均按规范产生。
3. 索引和查询使用同一个 Analyzer identity。
4. 英文、数字、内部 ID 和文件名没有核心 fixture 退化。
5. Analyzer、词典、segmenter 和 BM25 参数进入 payload 与 provenance。
6. 新 child/media BM25 schema 通过严格 parity。
7. records-only、child v2 和 media v3 继续绑定 legacy Analyzer。
8. 旧活动 BM25 不会被新代码静默重新解释。
9. 新 schema 缺失或身份不一致时 fail closed。
10. 依赖和 lock 文件可复现。
11. Analyzer、BM25、artifact、provenance 和受影响回归全部通过。
12. 对照报告同时记录改善、无改善、排序变化、非退化和 token 膨胀。
13. 不依赖线程 A/C 未合并代码或 `data_pages.jsonl`。
14. 未修改正式索引、生产 baseline、active pointer 或 Milvus。
15. 未引入 BGE-M3 Sparse 或任何新模型服务。
16. D 审核 diff、测试、产物兼容和文件所有权后接受提交。
