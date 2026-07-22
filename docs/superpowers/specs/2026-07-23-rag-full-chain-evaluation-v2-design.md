# RAG 全链路评估体系 v2 设计

日期：2026-07-23

状态：已批准，待实施

适用范围：1999Wiki 当前 generation-based Huiji crawler-only RAG、Wiki v3 媒体链路与本地运行环境

## 1. 背景

现有全链路评估体系建立于 2026-07-13，使用 M1–M5、D1–D4、48 个以上动态样本、独立 LLM judge 和分级严重度评估问答系统。该体系的质量模型仍然有效，但项目随后完成了以下迁移：

- Huiji crawler 成为唯一 RAG 数据源，旧 Obsidian 路径退出运行时。
- generation 0 回滚 authority、generation 1 active pointer 与 Candidate F 激活落地。
- RAG 与 Wiki 完成 crawler v3 跨系统闭环。
- Wiki 媒体升级为 resource/binding 双层 v3 契约。
- 生产回答模型迁移到 DeepSeek v4 Flash。
- 启动器增加固定 Python 环境、基础设施等待和有界 provenance 验证。

迁移后，现行评估出现两个确定性失配：

1. 评估器对整个 MinIO bucket 做全量 inventory，并在对象缺少 hash 元数据时下载正文计算哈希。当前媒体规模下，该操作已不适合作为每次问答评估的前置门禁。
2. 旧 smoke 数据仍要求 `item` section，但当前正式语义契约已将 `item` intent 映射到 `collection` section，造成正确检索被判为失败。

因此 v2 不降低现有质量门槛，而是升级发布身份、受保护快照、意图 taxonomy、媒体契约、报告聚合和版本适用性。

## 2. 目标与非目标

### 2.1 目标

- 保留现有 M1–M5、D1–D4、严重度顺序、动态采样和确定性硬门禁。
- 新增 `rag_eval.thresholds/v2`，同时保持 v1 历史阈值、报告和 evidence 可读取。
- 将 M1 扩展为发布身份与数据一致性门禁。
- 使用 active manifests 派生精确 MinIO 保护集，避免每次评估扫描或下载整个 bucket。
- 使 intent/section、generation、artifact schema 和媒体 binding 期望从当前运行时 authority 派生。
- 生成一份集中式人类可读指标总表和一份日期化全量评估报告。
- 修复 M1 后重新执行不少于 48 个唯一问题的真实全链路评估。
- 在前端迭代期间保持文件、端口、进程和构建隔离。

### 2.2 非目标

- 不降低 D1–D4 质量分、98% 成功率、零路径泄漏或零跨实体串线门槛。
- 不重建、覆盖、删除或切换 Milvus collection。
- 不上传、删除或改写 MinIO 对象。
- 不修改 MySQL 业务数据、active pointer、provenance baseline 或 processed artifacts。
- 不把全 bucket 存储清理审计并入每次问答质量评估。
- 不修改 React 前端或运行 npm、Vite、Playwright 和前端构建。
- 不伪造人工复核结果。

## 3. 兼容与版本策略

采用兼容式 v2，而不是原地改写 v1。

- 保留 `eval/rag_full_chain_thresholds.v1.json`、旧报告和旧 run 目录。
- 新增 `eval/rag_full_chain_thresholds.v2.json`，schema 为 `rag_eval.thresholds/v2`。
- 当前 evidence contract 可继续使用既有文件格式；run manifest 必须新增或记录 `policy_version`、active release identity 和适用 schema。
- v1 读取路径保持可用，但新的正式运行默认选择 v2。
- v2 不回填或重写历史 evidence。
- 指标总表明确列出 v1 的适用时期、当前失效原因和历史报告索引。

## 4. 总体架构

### 4.1 执行数据流

```text
active_build.v1.json
  -> resolve runtime artifact snapshot
  -> validate provenance / closure / rollback / crawler-only authority
  -> validate RAG and Wiki joint health
  -> derive exact protected MinIO keys from active manifests
  -> capture pre snapshot: Milvus + MySQL + artifacts + scoped MinIO
  -> freeze v2 sample manifest
  -> execute 48+ real sync/SSE cases and repeats
  -> deterministic M2/M4/M5 checks + independent M3 judge
  -> capture equivalent post snapshot
  -> compare protected state
  -> write immutable automatic evidence and consolidated report
  -> finalize only when required human review is complete
```

### 4.2 组件边界

现有 `src/rag_eval` 模块职责保持稳定，新增能力放在对应边界内：

- `contracts.py`：v2 policy、release identity 和序列化字段。
- `inventory.py`：release identity、scoped MinIO snapshot 和受保护状态比较。
- `sampling.py`：当前 P0 intent、动态 section taxonomy 和 schema-bound derivation。
- `deterministic.py`：generation、binding identity、RAG/Wiki 媒体一致性门禁。
- `reporting.py`：集中式指标展开、迁移身份和前端隔离附录。
- `runner.py`：v2 默认策略、细分预检错误、执行顺序和 immutable evidence。

不新建重复的第二套 evaluator，也不把发布验证、检索、judge 和报告重新耦合到一个大模块。

## 5. M1 发布身份与数据一致性

M1 从一般 readiness 扩展为当前发布状态的唯一前置门禁。

### 5.1 P0 条件

- 评估所需 MinIO、MySQL、生产模型和 judge 凭据存在。
- MinIO 凭据具备读取受保护对象 metadata 的权限。
- `huiji.enabled=true` 且 `source_mode=huiji_crawler`。
- active pointer 的 generation、activation ID、build version、artifact schema 和 collection 合法。
- provenance runtime verifier 通过。
- Candidate closure receipt、sidecar、rollback authority 和当前状态重新验证通过。
- RAG health 与 Wiki health 指向同一 generation/build/schema authority。
- Milvus collection 与 active pointer 一致并已加载。
- 当前 artifacts 与 active manifest 的 hash/row count/ID 契约一致。
- 前后受保护快照完全相等。

### 5.2 错误分类

预检至少区分：

- `READY.CREDENTIAL_MISSING`
- `READY.PERMISSION_DENIED`
- `READY.RELEASE_IDENTITY_MISMATCH`
- `READY.PROVENANCE_BLOCKED`
- `READY.CLOSURE_INVALID`
- `READY.JOINT_HEALTH_MISMATCH`
- `READY.PROTECTED_SNAPSHOT_FAILED`

上述错误不得全部折叠成 `READY.DATA_UNAVAILABLE`。M1 硬失败时在发送样本请求前停止，并保留可审计 evidence。

## 6. Scoped MinIO 保护集

### 6.1 保护范围

受保护对象集合只能从当前 active build manifest、media manifest 和明确的运行时 consumer references 派生。每个对象记录：

- bucket 与 object key；
- size；
- ETag；
- version ID（若启用）；
-已有 SHA-1/SHA-256 metadata；
- manifest 中的期望 hash 或 binding identity。

### 6.2 禁止行为

- 不枚举与 active release 无关的整个 bucket。
- 不因缺少 metadata 而在每次评估中下载完整对象正文。
- 不把 `a-bucket` 等 Milvus-owned 范围纳入问答评估的 MinIO 内容校验。
- 不通过上传 metadata、复制对象或修改 policy 使评估通过。

缺少对象 hash metadata 时，应使用已 hash-pinned 的 active manifest 作为内容 authority，并以 ETag/version/size 做当前对象身份验证。需要全内容重算时，转交独立存储审计，不允许隐式扩大本次评估范围。

## 7. M2 查询理解与检索

### 7.1 正式 P0 intent

v2 覆盖：

```text
intro, profile_fact, skill, item, culture, udimo,
voice, media, video, psychube, story, general_game, meta_question
```

`general` 是执行降级行为，`profile/lore` 是迁移兼容 intent；三者不作为新的正式 P0 能力计数。

### 7.2 动态 taxonomy

- `item` intent 的当前 canonical section 为 `collection`。
- intent 到 section 的映射从当前 runtime schema 与正式代码契约派生并冻结进 sample manifest。
- sample manifest 记录 policy version、artifact schema、build version 和 taxonomy digest。
- generation/schema 变化后，旧 manifest 必须被识别为 stale。

### 7.3 保留指标

继续计算 entity accuracy、intent precision/recall/F1、Recall@K、MRR、nDCG、intent coverage、预算 shortfall 和 cross-entity leak。任何 difficulty 都不能降低跨实体、路径泄漏或伪造命中门禁。

## 8. M3 回答与证据一致性

保留 groundedness、relevance、completeness、citation validity/support、refusal correctness 和不受支持断言门禁。

每次运行额外记录：

- production 模型 base URL、model 和可用 revision；
- judge base URL、model、revision、温度和 prompt version；
- judge 与 production identity 的独立性；
- judge 原始 JSON 与失败重试；
- human audit 状态和 agreement；未完成时不得伪造百分比。

judge/production 调用失败必须形成结构化失败，不能被回答文本当作正常事实继续评分。

## 9. M4 媒体与响应契约

在原有 media intent、语音分页、路径安全和 sync/SSE parity 基础上增加 v3 契约：

- 每个当前 v3 媒体项具有合法 `binding_id` 与 `resource_id`。
- 同一 resource 的多个 binding 不得在 API 或评估归一化中丢失。
- entity、parent、child、event/text 与 binding identity 一致。
- RAG media registry、Wiki v3 repository 和 active media manifest 指向同一 generation/schema authority。
- URL 为可序列化 HTTP(S) URL，不暴露 object key、本地路径或内部存储字段。

## 10. M5 可靠性与性能

### 10.1 保留门槛

- 唯一样本请求成功率 `>= 98%`。
- retrieval P95 `<= 5s`。
- TTFT P95 `<= 15s`。
- total P95 `<= 45s`。
- 路由、关键 source、媒体集合和事实结论的重复一致性保持 100%。

本轮不得为通过评估临时放宽门槛。

### 10.2 新增记录维度

- 冷启动与热请求分开。
- readiness、planning、retrieval、TTFT、total 分开。
- 生产模型、judge、数据库、Milvus 与序列化失败分开。
- 记录硬件、Python、容器和模型环境摘要。

完成三次同环境有效 v2 全量运行后，才能单独评审性能阈值是否需要重标定；重标定不得追溯修改已经生成的报告。

## 11. 报告与指标集中展示

### 11.1 指标总表

新增 `docs/evaluation/rag-full-chain-v2.md`，作为唯一的人类可读当前指标入口，集中列出：

- M1–M5 全部指标与 P0 ID；
- D1–D4 目标、最低线和通过率；
- 样本规模、intent 覆盖和重复率；
- 严重度、验收和退出码规则；
- release identity、快照与只读边界；
- 前端隔离边界；
- 定向复测命令；
- v1 历史版本与报告索引。

### 11.2 本次全量评估报告

新增 `docs/reports/2026-07-23-project-full-evaluation-v2.md`，包含：

- 全局严重度和验收结论；
- M1–M5 状态、分数和最严重事件；
- D1–D4 计数、均分和 floor pass rate；
- 实际阈值与实测值；
- generation/build/schema/collection/Wiki snapshot 身份；
- 前后快照是否相等；
- 自动测试和真实运行命令结果；
- 主要失败簇、影响范围和整改顺序；
- 原始 evidence 链接；
- human audit 是否完成。

报告必须展开关键指标，不能要求读者在多个 JSON 和 spec 中自行拼接结论。

## 12. 前端并发边界

当前移动端响应式任务在 `.worktrees/main-mobile-responsive` 隔离工作树中执行。v2 实施遵循：

- 不修改 `frontend/**` 或 `kimi_web/**`。
- 不运行 npm、Vite、Playwright 或前端 build。
- 不占用 5173、3000、3007 等前端端口。
- 评估后检查前端任务状态、工作树隔离和当前工作区 diff。
- 前端任务完成后，可追加只读 API/DTO 兼容检查和独立 UI 报告；其结果不改变本轮 RAG M1–M5 严重度。

## 13. 错误处理和停止条件

- M1 硬失败：写 evidence，发送零个正式样本请求。
- 单个 M2–M5 case 失败：继续剩余安全样本，确定影响范围。
- 受保护状态漂移：立即停止，至少 `SEV-1`。
- judge outage：结构化 M3 失败，不生成虚假正常分数。
- evidence 无法 create-new：停止，禁止覆盖旧 run。
- human audit 队列非空且未完成：自动报告有效，最终 acceptance 标记为 pending review。

## 14. 测试与真实验收

### 14.1 自动化测试

先写失败测试，再实现：

- scoped MinIO key derivation 与 metadata-only snapshot；
- credential missing、permission denied 和 snapshot failure 分类；
- active release identity、closure、rollback 和 joint health；
- v1/v2 policy 共存与 v1 历史读取；
- `item -> collection` 和 `udimo` P0 覆盖；
- stale schema/build manifest 拒绝；
- v3 binding/resource、多绑定保留和跨系统一致性；
- 集中式报告渲染与历史索引；
- read-only operation guard。

执行全部 `tests/test_rag_eval_*.py` 和仓库 Python `tests`；前端测试在其独立任务完成前不运行。

### 14.2 真实运行

1. 在独立后端端口启动服务，不占用前端端口。
2. 使用 v2 preflight 验证 release identity 和 scoped snapshot。
3. 冻结不少于 48 个唯一 case，满足 D1/D2/D3/D4、8 个实体、全部 P0 intent 和 10% repeats。
4. 执行真实 sync/SSE、production answer 和独立 judge。
5. 遍历适用语音分页并执行 sync/SSE parity。
6. 比较前后受保护快照。
7. 生成自动报告和 human audit 队列。
8. 只有必要人工复核完成且 agreement `>= 85%` 后，才生成最终 acceptance。

## 15. 完成标准

v2 完成必须同时满足：

- v2 阈值、release identity、scoped snapshot、动态 taxonomy 和 v3 binding 门禁已实现。
- v1 文件和历史报告未被修改。
- 全量 Python 测试通过。
- 真实 v2 preflight 通过且正式样本已执行。
- pre/post 受保护快照相等。
- 集中式指标总表与日期化评估报告已生成。
- 报告不隐藏 M1 阻断、未完成的人工复核或性能超标。
- 前端工作树和文件未被本任务修改。
