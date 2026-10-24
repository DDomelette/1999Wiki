# 1999Search GitHub 双语 README 与 RAG 展示设计

**日期：** 2026-08-12

**状态：** 已获用户设计批准，待书面审阅

**目标文件：** `README.md`、`README_EN.md`

## 1. 背景与目标

现有 `README.md` 已说明项目定位、当前数据流、本地启动和索引维护，但更接近运行状态记录，尚未完整承担开源项目首页的职责：GitHub 访问者不容易在首屏识别项目价值，也缺少在线查询、可信引用和二次开发边界的完整导航。

本次改写面向两类开源使用者：

- 希望在本地部署完整 Wiki 与 RAG 服务的使用者；
- 希望替换模型、数据源、检索策略、媒体存储或前端的开发者。

成功标准如下：

1. 读者能在首屏理解项目是什么、核心能力是什么，以及从哪里开始；
2. 读者能通过两张图分别理解离线数据/索引链路与在线问答/可信引用链路；
3. 部署命令、默认地址、配置字段和当前 collection 与代码及配置一致；
4. 二次开发章节给出明确的模块入口、扩展点和不可绕过的信任边界；
5. 中文、英文 README 信息等价，图、表、命令和链接保持同一口径；
6. 不把设计目标、历史实验或尚未通过验收的能力写成当前事实。

## 2. 文档组织方案

采用两份完整 README，共享同一信息架构：

- `README.md`：简体中文完整版，默认 GitHub 首页；
- `README_EN.md`：英文完整版；
- 两份文件顶部提供显眼的语言切换链接；
- Mermaid 图的结构、节点和技术名一致，仅解释文字翻译；
- 命令、配置键、API 路径、文件路径和端口完全一致。

不采用逐段中英并排方案，原因是完整部署和 RAG 说明较长，会降低扫描效率。不采用精简英文版，原因是英文开发者同样需要完整的部署、扩展和排障信息。

## 3. 首屏信息架构

两份 README 的首屏均按以下顺序组织：

1. 项目名 `1999Search`；
2. 一句话定位：面向《重返未来：1999》的本地知识库、Wiki 与可追溯 RAG 问答系统；
3. 语言切换；
4. 仅使用可由仓库事实支撑的技术标签；
5. 三项能力摘要：
   - 可追溯：请求级 `S01...` 来源映射和引用校验；
   - 防串线：实体 owner 门禁、意图路由和结构化检索；
   - 可运维：provenance 校验、shadow collection、健康降级；
6. 页内快捷链接：快速开始、RAG 设计、二次开发；
7. 当前状态提示，明确唯一正式数据源和运行时 fail-closed 语义。

首屏不堆叠无法自动维持的测试数量、覆盖率或性能徽章，也不添加未配置目标地址的在线演示按钮。

## 4. 系统架构呈现

README 先给一张高层系统图，说明浏览器、FastAPI、RAG/Wiki 服务、Milvus、MySQL、MinIO 和外部模型服务的职责与数据方向。该图回答“系统由什么组成”，不展开检索内部阶段。

组件说明紧随其后，用表格明确：

| 组件 | 职责 | 默认实现 |
|---|---|---|
| Web | Wiki 浏览、问答、媒体和会话交互 | React + Vite |
| API | 同步问答、SSE、Wiki、媒体、健康检查 | FastAPI |
| RAG runtime | 规划、检索、生成、引用、记忆与响应冻结 | `src/rag/` |
| Corpus build | crawler snapshot 到父子块、媒体和检索产物 | `src/huiji_rag/` |
| Vector store | child dense retrieval | Milvus |
| Sparse index | 中文 BM25 候选 | 本地构建产物 |
| Wiki store | Wiki 结构化页面 | MySQL |
| Asset store | 图片、视频、语音对象 | MinIO |
| Model services | embedding、planner 和 answer generation | 配置驱动的兼容 API |

## 5. RAG 设计：两条链路

### 5.1 离线数据与索引链路

第一张 Mermaid 图专注数据如何变成可加载的可信运行时资产：

```text
Huiji crawler snapshot
  -> source inventory / 清洗与结构化投影
  -> parent_blocks + child_blocks + media_assets
  -> 中文 BM25 + BGE-M3 embeddings
  -> 显式命名的 Milvus shadow collection
  -> fidelity / closure / provenance 审计
  -> hash-pinned baseline
  -> 人工批准后显式激活
```

图下必须解释以下约束：

- Huiji crawler 是正式数据源，历史数据链路不是回滚路径；
- parent/child 分层用于 child 检索与 parent/相邻块上下文扩展；
- 索引构建只创建显式命名且不存在的 shadow collection；
- 构建过程不覆盖、不删除、不自动激活 collection；
- 运行时不会自动生成 artifacts 或修复索引；
- 数据、BM25、collection 或 provenance baseline 不一致时，服务保持 health-only，问答接口返回 503。

### 5.2 在线问答与可信引用链路

第二张 Mermaid 图专注一次问题如何变成经校验的响应：

```text
用户问题 + 安全会话投影
  -> Query Planner：追问改写、意图、实体、owner
  -> packet policy + retrieval budget
  -> 结构化检索 + 中文 BM25 + Milvus dense
  -> owner gate + RRF 融合 + 分层扩展
  -> context budget + 稳定来源排序
  -> 请求级 S01... source map
  -> LLM 生成
  -> 引用校验 / 一次修复 / citation-safe fallback
  -> frozen ResponsePacket
  -> 同步 JSON 或校验后 SSE
```

图和配套文字需突出项目区别于简单向量检索示例的能力：

- 多意图请求按意图分配检索预算；
- owner 身份用于限制跨角色、跨实体污染；
- structured、BM25、dense 三路候选经 RRF 融合；
- 来源 ID 仅在最终排序后分配，并在请求内稳定；
- 历史对话用于安全改写和连贯性，不作为本轮事实证据；
- grounded 与用户显式授权的 ungrounded 回答边界清楚；
- 同步与 SSE 消费同一个冻结响应包，检索不会重复执行；
- 当前 SSE 是“完整生成与引用校验后切片发送”，不能宣传为模型原生 token streaming。

## 6. 部署与快速开始

快速开始采用“先决条件 → 配置 → 启动 → 验证”的最短闭环：

1. 列出 Python、Node.js、Docker Desktop/Compose 以及模型 API 凭据；
2. 从仓库实际示例文件说明 `.env` 与 `config/settings.yaml` 的配置责任；
3. 优先展示项目统一启动器 `start.ps1` / `start.bat`；
4. 列出默认 Web/API、React dev、Milvus、MinIO 和 MySQL 地址；
5. 提供 `/health` 检查和一个同步/SSE 请求示例；
6. 将手动后端、前端启动和生产 Compose 放在后续章节，避免首个路径过长。

README 必须明确当前脚本含 Windows/本机路径假设；不能把特定开发机上的 Conda 绝对路径描述为普适要求。若项目当前没有跨平台的一键开发脚本，则应如实说明，并提供可移植的手动启动方式或指向运行手册。

密钥仅通过环境变量或本地 `.env` 注入，示例中不写真实凭据。

## 7. API 与响应契约

README 只展示最有代表性的公共入口，并指向源代码或详细文档：

- 健康检查；
- 同步问答；
- SSE 流式问答；
- 清除会话；
- Wiki 页面与分类入口；
- 媒体/语音分页入口。

问答响应示例应展示 `answer`、`sources`、请求级引用、grounding/coverage 信息与 `conversation_id`，但以当前 schema 为准，不手写不存在的字段。API 方法、路径和字段从 `backend/main.py`、`backend/schemas.py` 与测试中核验后写入。

## 8. 二次开发导航

采用“我要改什么 → 从哪里开始 → 必须保持什么契约”的表格：

| 扩展目标 | 入口 | 必须保持的边界 |
|---|---|---|
| 替换 embedding/LLM | `config/settings.yaml`、模型适配代码 | 不把密钥写入仓库，保持公共响应契约 |
| 改查询规划/意图 | `src/rag/query_plan.py` | owner、歧义拒绝、会话安全投影 |
| 改混合检索 | `src/rag/retriever.py`、`src/rag/hybrid.py` | 稳定排序、预算、失败分类与来源映射 |
| 增加语料投影 | `src/huiji_rag/build/` | source refs、父子关系、provenance 与 fidelity |
| 增加媒体类型 | `src/assets/` | owner/source 绑定和公共 URL 安全 |
| 扩展 Wiki UI | `frontend/react-app/src/components/wiki/` | API 类型、路由和移动端行为 |
| 替换存储 | vector/MySQL/MinIO 适配边界 | 健康检查、启动门禁和 fail-closed 语义 |

此外给出：

- 开发测试的聚焦命令；
- 目录导航；
- 配置优先级和环境变量说明；
- 索引维护与生产部署 runbook 链接；
- 与 RAG 可信执行相关的重点测试文件。

## 9. 失败处理与排障呈现

README 不复制完整 runbook，而提供高频现象到首查入口的简表：

- `/health` error 或问答 503：检查 Milvus、模型、artifact 与 provenance；
- 检索为空：检查 planner、owner、三路候选与预算；
- 引用失败：检查 source map、citation validator 和 fallback；
- 同步/SSE 不一致：检查 frozen packet 与公共 serializer；
- 图片/语音串实体：检查媒体 registry 的 owner/source 绑定；
- 启动脚本失败：检查固定 Python 路径、Docker 和前端依赖。

详细恢复、影子索引构建、激活与生产切换继续链接至现有 runbook，不在 README 重复危险操作。

## 10. 测试与验证策略

实施完成后执行以下文档验证：

1. 扫描两份 README 的相对链接，确认目标存在；
2. 比较两份 README 的标题结构、代码块数量、Mermaid 图数量及核心命令，确认双语等价；
3. 从配置和代码核对端口、collection、模型、API 路径、字段名和目录；
4. 用 Mermaid CLI 或可用的渲染器验证语法；若环境无渲染器，则至少进行代码块提取和语法静态检查；
5. 运行与启动文档、配置、API 和 RAG 契约最相关的现有测试；
6. 查看 `git diff --check`，保证无尾随空格和格式问题；
7. 确认仅修改 `README.md`、新增 `README_EN.md` 以及本设计/后续计划文件，不覆盖工作区现有的无关改动。

命令示例若会调用外部模型或写入真实索引，只验证其参数和 `--help`，不在文档改写任务中执行有成本或有状态的操作。

## 11. 内容真实性与维护规则

- 当前事实以代码、`config/settings.yaml`、provenance baseline 和测试为准；
- README 顶部的日期型“当前状态”改为无日期或低维护成本的运行时契约描述；
- 不展示容易过期的完整活动 collection 名称；需要时说明它由 `huiji.text_collection_name` 与 provenance baseline 锁定，并在配置示例中展示当前值；
- 不把 reranker 描述为默认主路径，因为当前配置默认关闭；
- 不声称已通过新的生产级全链路评测，除非仓库存在对应且最新的验收证据；
- 数据来源、游戏素材归属、非官方项目性质和仓库许可证按仓库实际情况说明；若缺少 LICENSE，则只说明缺失，不自行授予许可；
- README 的架构摘要保持稳定，易变的运维细节下沉到 runbook。

## 12. 实施范围

本任务包含：

- 重写 `README.md`；
- 新增完整英文版 `README_EN.md`；
- 增加 Mermaid 架构图与 RAG 链路图；
- 增加开源部署、API、二次开发、测试与排障导航；
- 修正现有 README 与当前配置不一致的描述。

本任务不包含：

- 修改后端、前端或 RAG 行为；
- 重建、激活或删除 Milvus collection；
- 调用外部 LLM 重新跑完整评测；
- 发布 GitHub release、部署在线演示或添加 CI；
- 补发项目许可证或更改素材授权。
