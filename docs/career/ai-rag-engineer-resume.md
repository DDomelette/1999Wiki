# [姓名]

**AI 应用 / RAG 工程师｜3 年工作经验｜AI 原生研发**

[手机号码] ｜ [邮箱] ｜ [所在城市] ｜ [GitHub/个人主页]

## 个人简介

3 年软件开发经验，聚焦 AI 应用、RAG 与知识工程，能够独立完成需求规划、数据建设、检索与生成链路、前后端产品、测试评估和运行维护。独立主导 1999Search，在 **1 个月**内从零完成灰机 Wiki 数据采集、混合检索、可信问答、富媒体 Wiki、全栈交互及备份恢复体系。熟悉人工主导的 AI 原生研发方式，能够使用 Codex、Trae Solo、Kimi CLI、MCP、ACP 和多 Agent 协作加速复杂项目，同时对技术选型、架构边界、代码审查、风险控制和最终验收负责。

## 核心技能

- **AI / RAG：** LangChain、Query Planning、实体解析与消歧、多意图检索、Structured/BM25/Dense Hybrid Retrieval、BGE-M3、Milvus、Weighted RRF、Parent-Child Retrieval、Rerank、上下文预算、引用校验、RAG Evaluation
- **后端与数据：** Python、FastAPI、SSE、Pydantic、RESTful API、PyMySQL、爬虫、JSONL 数据管线、数据契约、短期会话记忆、异常降级
- **存储与基础设施：** MySQL、Milvus、MinIO、Docker Compose、Backrest、Restic、Rclone、腾讯云 COS、Provenance、Shadow Collection、备份恢复
- **前端工程：** React、TypeScript、Vite、Zustand、Vitest、Testing Library、Playwright、Framer Motion、GSAP
- **AI 原生研发：** Codex、Trae Solo、Kimi/Kimi CLI、MCP、ACP、多 Agent 编排、Obsidian 知识库、Spec-driven Development
- **开发工具：** PyCharm、VS Code、Trae、DataGrip、Git、PowerShell

## 工作经历

### [公司名称]｜[岗位名称]

[任职时间，例如：2023.07—至今]｜[所在城市]

- [填写真实业务：负责的系统、个人职责、关键技术和最终业务结果。]
- [填写量化成果：交付周期、数据规模、接口规模、稳定性、性能或人效变化。]
- [填写协作与责任：是否独立负责、跨团队协作、故障处理或上线维护。]

## 核心项目

### 1999Search｜RAG 问答与富媒体 Wiki 全栈应用

**独立主导开发 / AI 应用工程师｜2026.06—2026.07｜规划到落地 1 个月**

**技术栈：** Python、LangChain、FastAPI、React、TypeScript、BM25、BGE-M3、Milvus、MySQL、MinIO、SSE、Backrest、Restic、Rclone、Tencent COS

面向《重返未来：1999》知识场景构建本地 RAG 问答与富媒体 Wiki。项目将灰机 Wiki 爬虫快照作为唯一事实来源，通过统一数据构建层分别产出 MySQL Wiki、BM25/Milvus 检索数据和 MinIO 多媒体资源，形成从原始内容到最终问答与展示的完整产品闭环。

- **一个月完成端到端交付：** 独立完成需求拆解、技术选型、架构设计、任务编排、爬虫、语料加工、RAG、后端、React 前端、数据库、对象存储、测试评估、灾备和文档，将概念验证推进为可运行、可诊断、可恢复的全栈应用。
- **构建统一知识数据底座：** 处理 7,456 个 Wiki 实体页面，生成 8,246 个父块、16,010 个子块与 15,758 条媒体绑定；统一维护 source、entity、parent、child、event 和 media 身份，使同一份权威数据同时服务检索问答、结构化 Wiki 与富媒体展示。
- **实现多阶段混合检索：** 设计“确定性规则 + LLM”查询规划器，支持实体识别、别名归一、同名消歧、主/次意图和媒体意图；融合结构化精确取数、BM25 与 BGE-M3/Milvus 稠密检索，通过 Weighted RRF、Owner Gate、层级扩展、兄弟窗口与字符预算稳定分配上下文。
- **建立可信回答执行链：** 最终检索结果按请求生成 S01、S02 等来源编号，回答生成后执行引用合法性、证据支持与无依据声明检查；失败时进行一次修复或安全回退，并冻结 Retrieval/Response Packet，保证同步 JSON 与 SSE 消费同一份校验后结果。
- **实现会话与服务化能力：** 使用 FastAPI 提供同步问答、SSE、会话清理、分类、Wiki、媒体与语音分页 API；设计带 Lease、TTL、LRU、并发隔离和完成后提交的短期记忆，使超时、失败或客户端中断不会污染后续会话。
- **交付富媒体 React 产品：** 使用 React、TypeScript、Zustand 构建聊天、分类导航、人物选择、详情阅读、搜索及 Wiki/RAG 联动，支持立绘、技能图、语音、视频、Live2D 降级、主题切换、响应式布局和 Reduced Motion。
- **建立数据一致性与安全门禁：** 使用 Hash-pinned Provenance 固定 crawler snapshot、processed artifacts、BM25 与活动 Milvus collection；启动验证失败时进入 Health-only 并令问答接口返回 503，禁止运行时自动重建、覆盖或删除活动集合，只允许创建显式命名的 Shadow Collection。
- **建立自动化验证与证据体系：** 项目包含 200 余个测试文件，覆盖 Python 单元/契约/API、前端组件/状态/API 与 E2E；已有记录的两组聚焦验证共 368 项通过，并沉淀设计规格、实施计划、架构文档、Runbook、评测报告和可复算审计证据。

<div style="page-break-after: always;"></div>

# [姓名]｜AI 应用 / RAG 工程师（技术续页）

## 1999Search 技术深度

### RAG 查询、检索与可信执行

- **分意图规划：** 将角色介绍、基础资料、技能、单品、文化档案、语音、图片、视频、剧情等意图拆分为独立检索策略；显式意图优先于 LLM 推断，LLM 失败时使用确定性规则降级，多意图不得被模型静默删除。
- **实体所有权：** 使用 `(entity_type, entity_id)` 作为 Owner 身份，明确实体后同时约束候选、父块和最终来源；同名、多匹配或无法解析时宁可返回 Shortfall/澄清，也不执行全局猜测，降低跨角色串线风险。
- **混合召回与排序：** 结构化精确结果、BM25 和 Dense 候选在统一身份体系中融合；使用 Weighted RRF、实体/意图奖励、质量惩罚、稳定 ID Tie-break 和可选 Reranker，避免仅靠扩大 Top-K 掩盖排序问题。
- **父子块与预算：** Child 用于精确召回，Parent 和 Sibling Window 用于补全上下文；先满足各意图最低配额，再按来源数、字符预算和 Packet Policy 进行确定性裁剪，输出 Coverage 与 Shortfall 诊断。
- **路由与安全失败：** 将 Proposed Route、用户授权、Retrieval Outcome 和 Final Route 分离；自由补充只在用户授权且无证据时进入 Ungrounded 路径，检索异常不得伪装成正常知识库回答。
- **可观测性：** 使用单调时钟记录 Planning、Retrieval、模型、校验和传输阶段；通过结构化 Span、错误码和公开 Timing 区分检索慢、模型慢、媒体异常与链路失败。

### 五模块 RAG 评测体系

| 模块 | 评估范围 | 核心指标与门禁 |
|---|---|---|
| **M1 就绪与一致性** | 服务、模型、Artifacts、Milvus、MinIO、数据快照 | Dependency Readiness、Artifact/Index 一致性、评测前后 Protected Snapshot 相等；失败时其他质量结果无效 |
| **M2 查询理解与检索** | 实体、主/次意图、候选召回、排序与预算 | Entity Accuracy、Intent Exact/F1、Recall@K、MRR、nDCG、Intent Coverage、Shortfall、Cross-entity Leak |
| **M3 回答与证据** | 最终回答、事实支撑、引用、拒答 | Groundedness、Relevance、Completeness、Citation Validity/Support、Refusal Correctness；独立 LLM Judge + 确定性规则 |
| **M4 媒体与响应契约** | 图片/语音/视频绑定、分页、JSON/SSE | Media Intent Precision、Binding Exactness、Page/Set Equality、Local Path Leak、Sync/Stream Parity |
| **M5 可靠性与性能** | 请求执行、重复稳定性、异常和时延 | Success Rate、Repeat Consistency、Structured Failure、Retrieval/TTFT/Total P95 |

- **统一严重度：** 建立 PASS、SEV-4、SEV-3、SEV-2、SEV-1、SEV-0 六级门禁；全局等级取五模块最严重事件，模块高均分不能抵消跨实体、虚构来源、无依据生成或数据漂移等硬失败。
- **分难度宽容度：** 将问题分为 D1 标准、D2 复合、D3 噪声、D4 边界/拒答，并设置不同目标分、最低分和最低通过比例；D3 仅放宽相关性与完整性阈值，不放宽错误引用、路径泄漏、跨实体和无依据断言。
- **分场景权重：** 文本、纯媒体、文本+媒体、边界/拒答采用不同的 M2/M3/M4/M5 权重，未适用模块不按零分处理；每个 P0 Intent 至少覆盖标准样本和复合/噪声样本。
- **动态评测集：** 从当前 Artifacts 与活动 collection 动态生成不少于 48 个唯一问题，并增加至少 10% 重复请求验证稳定性；使用固定 Seed、Pairwise Coverage、前后快照和版本化报告保证可复现。
- **问题驱动优化：** 按 M1 → M2 → M3/M4 → M5 顺序修复，避免通过改 Prompt、扩大上下文或调低 Judge 阈值掩盖数据、实体、意图或检索根因。

### 备份、恢复与云端灾备

- **Backrest + Restic 分层备份：** 将代码与大体量数据拆分为两个本地 Restic 仓库，覆盖源码、语料、前端媒体、Milvus/etcd/MinIO/MySQL Volumes、向量存储与项目素材；`D:\1999Wiki_Backup` 当前本地仓库约 **24.5 GiB**。
- **保留与完整性策略：** 配置小时 24、每日 30、每月 12 的时间桶保留策略，以及代码最近 10 份、数据最近 3 份的 Forget 策略；配套 Prune、Repository Check、Auto Unlock、Quarantine、Staging 与 Restore Test 工作区。
- **可恢复性验证：** 对清理前的 1,291 个对象执行逐对象 SHA-1、SHA-256 和 Size 固化，生成 Restic Snapshot 后恢复到独立目录，对 **765,296,657 字节**进行完整对账；任一下载、快照、恢复或哈希不一致都会阻断删除计划。
- **腾讯云 COS 备份目标：** 通过 S3 兼容 Endpoint 为 Backrest/Restic 配置腾讯云 COS 远端仓库，并使用 Rclone 接入 TencentCOS 指定桶；采用 Bucket 级最小权限，不在代码、日志和简历中暴露账号、桶名与密钥。
- **数据变更保护：** 在索引迁移、MinIO 清理和 Wiki MySQL 导入前建立只读 Inventory、不可覆盖备份、隔离恢复演练、Operation Plan、审批点和 Post-check，使“存在备份”升级为“已证明能够恢复”。

### AI 原生研发与个人责任

- 采用人工主导的 Vibe Coding：本人负责产品目标、技术路线、系统边界、数据模型、任务拆解、风险判断、代码审查与最终验收，AI 负责局部实现、并行分析、测试补全和文档辅助。
- 熟练使用 Trae、VS Code、PyCharm、DataGrip，以及 Trae Solo、Codex、Kimi/Kimi CLI 等 AI Harness；通过 MCP 接入终端、文件、工具和 Obsidian 知识库。
- 使用 Codex 经 ACP 连接 Kimi CLI 进行多 Agent 协同，将复杂任务拆为可独立验证的子任务，再通过契约、测试、真实数据和审计证据统一收口。
- 通过 Spec → Plan → Implementation → Test → Evidence 的闭环减少 Agent 上下文漂移；项目一个月交付效率来自清晰架构、并行编排和短反馈周期，而不是跳过设计与测试。

## 教育经历

### [学校名称]｜[专业名称]｜[学历]

[入学年月—毕业年月]

## 补充信息

- 项目地址：[1999Search GitHub 地址或演示地址]
- 技术文章：[博客、Obsidian 发布页或项目架构文章]
- 语言能力：[按真实情况填写]

