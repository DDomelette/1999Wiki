# OUTDATED - 1999Search RAG 设计说明

> OUTDATED: Superseded by the July 3 Huiji crawler data and parent-child hybrid RAG specs. Keep this file for historical reference only.

日期：2026-06-25  
恢复日期：2026-07-02  
项目：`1999Search`  
状态：已按当前项目实现恢复并更新

## 摘要

`1999Search` 是面向《Reverse: 1999》本地 Obsidian 知识库的 RAG 问答系统。系统从 `D:\Obsidian_depot\Reverse1999` 读取 Markdown，解析 frontmatter，清洗 Obsidian 展示语法，按知识库六大分区打 metadata，然后构建 Milvus 向量索引。运行时由 FastAPI 提供健康检查、普通问答、SSE 流式问答、分类元数据和分类文档浏览接口，HTML、Streamlit、Gradio、React + Vite 四套前端共用同一后端。

当前运行时以以下实现为准：

- Embedding：SiliconFlow OpenAI-compatible API，模型 `BAAI/bge-m3`。
- 向量库：Milvus，数据库 `reverse1999_rag`，collection `chunks_bge_m3_v1`。
- LLM：DeepSeek OpenAI-compatible API，默认模型 `deepseek-chat`。
- 图片资产：MinIO bucket `reverse1999-assets`，结构化清单 `data/processed/assets.jsonl`。
- 后端：FastAPI，绑定 `127.0.0.1:8000`。
- React 前端：Vite 固定 `127.0.0.1:5173 --strictPort`，通过 `/api` proxy 调后端。

历史说明：最早的 2026-06-25 计划使用 Ollama `qwen3-embedding:0.6b` + Chroma。该方案已经被 SiliconFlow `BAAI/bge-m3` + Milvus 替代。本文档记录当前项目真实架构，不再把 Chroma/Ollama 作为运行时依赖。

```text
Obsidian vault (.md + assets)
  -> scripts/extract_data.py
       -> data/raw/
       -> data/processed/documents.jsonl
  -> scripts/build_assets.py
       -> MinIO reverse1999-assets
       -> data/processed/assets.jsonl
  -> scripts/build_index.py
       -> Markdown heading split
       -> recursive text split
       -> SiliconFlow BAAI/bge-m3 embeddings
       -> Milvus reverse1999_rag.chunks_bge_m3_v1

User question
  -> FastAPI /ask or /ask/stream
  -> QueryPlanner
  -> EntityPacketRetriever
  -> RobustIntentRouter
  -> RAG prompt + DeepSeek
  -> answer + sources + assets
```

## 目标

- 从本地 Obsidian vault 可重复提取 Reverse:1999 文本知识。
- 将文档按 `人物`、`心相`、`剧情`、`世界`、`阵营`、`日历` 六类建立可过滤 metadata。
- 清洗 Obsidian 特有语法，使向量索引只包含适合检索和生成的正文。
- 保留 heading 层级，支持“角色技能”“语音”“剧情”等问题精准落到文档小节。
- 使用 Milvus 支持 metadata 过滤、实体精确召回、文本 like 召回和向量召回。
- 使用 DeepSeek 生成基于检索上下文的中文回答，禁止脱离知识库编造。
- 在 API key 缺失、向量库未加载、检索失败、LLM 调用失败时给出明确降级响应。
- 通过 SSE 支持 React 前端流式输出，事件顺序稳定。
- 通过 MinIO 返回结构化图片资产 URL，不把本地磁盘路径暴露给浏览器。
- 通过一键启动脚本启动后端和四套前端，并避免 Windows 上端口漂移和 IPv6 `localhost` 问题。

## 非目标

- 不把 Obsidian vault 作为浏览器可访问的静态目录直接暴露。
- 不把图片二进制写入 Milvus，也不对图片做向量化。
- 不要求 LLM 判断图片内容，图片只按来源、heading、实体名和意图后挂载。
- 不在 RAG 主链路内实现用户登录、多用户会话持久化或权限管理。
- 不在本设计内做云端部署、CI/CD、CDN 或生产级密钥管理。
- 不支持任意第三方知识库格式；当前数据模型按 Reverse:1999 Obsidian vault 结构设计。

## 知识库分区

Obsidian vault 的顶级目录决定文档 category。

| 目录前缀 | category | 用途 |
|---|---|---|
| `100-UTTU人物合辑` | `人物` | 角色档案、技能、传承、语音、单品 |
| `200-相从心生` | `心相` | 心相档案、效果、材料 |
| `300-以影像之` | `剧情` | 主线、支线、活动剧情 |
| `400-箱外世界` | `世界` | 世界观设定、时间线、地点 |
| `500-箱外阵营` | `阵营` | 组织、阵营、势力设定 |
| `600-箱中日历` | `日历` | 事件日期、纪念日、时间记录 |

跳过规则：

- 跳过 `.obsidian`。
- 跳过顶层 `assets`。
- 跳过 `000-箱的构造/templates`、`script`、`插件`、`README`。
- 跳过 `1999 Wiki&Note Obsidian Vault.md`。
- 跳过 frontmatter 或正文中可识别的 kanban 文件。
- 跳过清洗后正文为空的 Markdown。

## 配置设计

配置入口是 `config/settings.yaml`，运行时由 `config/config.py` 加载并用 `.env` 环境变量覆盖密钥。

核心配置：

```yaml
obsidian:
  vault_path: "D:\\Obsidian_depot\\Reverse1999"
embedding:
  provider: "siliconflow"
  base_url: "https://api.siliconflow.cn/v1"
  model: "BAAI/bge-m3"
  api_key: ""
llm:
  provider: "deepseek"
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-chat"
  api_key: ""
rag:
  chunk_size: 500
  chunk_overlap: 50
  top_k: 20
server:
  backend_port: 8000
  streamlit_port: 8501
  gradio_port: 7860
  frontend_delay_seconds: 3
vectorstore:
  provider: "milvus"
  uri: "http://127.0.0.1:19530"
  db_name: "reverse1999_rag"
  collection_name: "chunks_bge_m3_v1"
assets:
  provider: "minio"
  endpoint: "127.0.0.1:9002"
  public_base_url: "http://127.0.0.1:9002"
  bucket_name: "reverse1999-assets"
  secure: false
  object_prefix: "reverse1999"
```

环境变量：

- `SILICONFLOW_API_KEY` 覆盖 `embedding.api_key`。
- `DEEPSEEK_API_KEY` 覆盖 `llm.api_key`。
- `MINIO_ACCESS_KEY` 覆盖 MinIO access key。
- `MINIO_SECRET_KEY` 覆盖 MinIO secret key。
- `INDEX_BATCH_SIZE` 控制索引构建时的 embedding 批大小，默认 `64`。

配置加载结果是一个 `Config` dataclass，包含 `obsidian`、`embedding`、`llm`、`rag`、`server`、`vectorstore`、`assets`、`paths`。`paths` 统一派生 `project_root`、`data_raw`、`data_processed`、`vectorstore`、`frontend_html`。

## 数据提取设计

入口：`scripts/extract_data.py`  
核心模块：`src/extraction/obsidian_extractor.py`、`src/utils/text_cleaner.py`

提取流程：

1. 读取 `cfg.obsidian.vault_path`。
2. 遍历所有 `.md` 文件。
3. 根据相对路径执行跳过规则和 category 映射。
4. 用 `python-frontmatter` 解析 frontmatter；解析失败时手动剥离开头的 `--- ... ---` 块作为回退。
5. 通过 `clean_markdown()` 清洗正文。
6. 生成文档对象并写入 `data/processed/documents.jsonl`。
7. 将原始 Markdown 复制到 `data/raw/` 镜像目录，便于排查和资产抽取。

单篇文档输出结构：

```json
{
  "id": "100-UTTU人物合辑/神秘学家｜Arcanists/样本｜Sample",
  "source": "100-UTTU人物合辑/神秘学家｜Arcanists/样本｜Sample.md",
  "name": "样本",
  "category": "人物",
  "metadata": {
    "Name": "样本",
    "exonym": "Sample"
  },
  "text": "清洗后的正文"
}
```

正文清洗规则：

- 移除 Obsidian 图片嵌入 `![[...]]`。
- 移除 Markdown 图片语法 `![alt](url)`。
- 展开 wikilink：`[[维尔汀]] -> 维尔汀`，`[[维尔汀|司辰]] -> 司辰`。
- 移除 callout 标题行，保留 callout 内容。
- 移除脚注引用和脚注定义。
- 移除 HTML 标签，保留标签内文本。
- 折叠过多空行，清理行尾空白。

提取脚本输出文档总数和各 category 数量。`documents.jsonl` 是后续 Milvus 构建、实体名加载、分类文档浏览的共同数据源。

## 图片资产设计

入口：`scripts/build_assets.py`  
核心模块：`src/assets/extractor.py`、`src/assets/minio_store.py`、`src/assets/registry.py`

文本清洗会移除图片语法，因此图片不能依赖 LLM 从上下文中生成链接。图片链路独立于文本向量链路：

1. 从原始 Markdown 和 frontmatter 中提取图片引用。
2. 解析 Obsidian `![[...]]`、Markdown `![alt](...)`、frontmatter 图片字段。
3. 在当前 Markdown 目录和 vault 根目录中解析本地图片路径。
4. 计算图片文件 SHA1，作为 `asset_id`。
5. 按引用、alt、heading、frontmatter key 分类 role。
6. 上传到 MinIO，object key 格式为 `reverse1999/{role}/{sha1-prefix}/{sha1}.{suffix}`。
7. 写入 `data/processed/assets.jsonl`。

支持的 role：

- `portrait`：立绘、cover。
- `ultimate`：至终的仪式。
- `skill`：神秘术图片。
- `psychube`：心相图片。
- `item`：单品图片。
- `poster`：海报、banner。
- `unknown`：无法稳定分类但可解析的图片。

资产记录结构：

```json
{
  "asset_id": "sha1",
  "name": "玛蒂尔达",
  "category": "人物",
  "source": "100-UTTU人物合辑/.../玛蒂尔达.md",
  "heading_path": "玛蒂尔达 > 神秘术",
  "role": "skill",
  "alt": "神秘术 天才习作",
  "raw_ref": "神秘术 天才习作.png",
  "local_path": "D:\\Obsidian_depot\\Reverse1999\\...",
  "object_key": "reverse1999/skill/ab/abcdef.png",
  "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/skill/ab/abcdef.png",
  "line": 60
}
```

运行时 `AssetRegistry.find_for_retrieval()` 根据 `QueryPlan.intent`、`entity`、检索结果的 `source`、`heading_path` 和 `name` 选择最多 8 张图片。排序优先级：

1. heading 精确匹配。
2. source 匹配。
3. role 与 intent 匹配。
4. 清单中的稳定顺序。

例如 `intent=skill` 时优先 `skill`、`ultimate`，再考虑 `portrait` 和 `unknown`。

## 向量索引设计

入口：`scripts/build_index.py`  
核心模块：`src/rag/vectorstore.py`、`src/rag/embeddings.py`

Milvus collection 必须已由基础设施准备好。项目提供 `infra/milvus/docker-compose.yml`，包含：

- etcd。
- MinIO，宿主机端口 `9002` 和 console 端口 `9003`。
- Milvus standalone，宿主机 gRPC 端口 `19530`，健康端口映射到 `127.0.0.1:19091`。
- Attu，宿主机端口 `30001`。

索引构建流程：

1. 读取 `data/processed/documents.jsonl`。
2. 使用 `MarkdownHeaderTextSplitter` 保留 `#`、`##`、`###` heading metadata。
3. 用 `RecursiveCharacterTextSplitter` 继续分块。
4. 分隔符按中文文本优化：`\n\n`、`\n`、`。`、`；`、`，`、空格、空字符串。
5. 每个 chunk 写入稳定 id：`{doc_id}#chunk-0000`。当 id 超过 256 字符时使用 SHA1 压缩前缀。
6. 每个 chunk metadata 包含 `source`、`name`、`category`、`heading_path`、`chunk_index`。
7. 调用 SiliconFlow embedding API 生成 `BAAI/bge-m3` 向量。
8. 清空已有 collection 实体，再按 batch 写入 Milvus。
9. 每个 batch 上报进度，失败时输出 batch 编号、范围、耗时和错误。

Milvus 字段约定：

| 字段 | 含义 |
|---|---|
| `id` | 主键，稳定 chunk id |
| `text` | chunk 正文 |
| `embedding` | 向量 |
| `source` | 原 Markdown 相对路径 |
| `name` | 文档名或 frontmatter `Name` |
| `category` | 六大分区 |
| `heading_path` | heading 路径，如 `玛蒂尔达 > 神秘术` |
| `chunk_index` | 文档内 chunk 顺序 |

检索使用 COSINE。索引参数使用 Milvus `AUTOINDEX`。

## 检索设计

核心模块：`src/rag/query_plan.py`、`src/rag/entity_packet.py`、`src/rag/retriever.py`、`src/rag/reranker.py`

当前检索不是单纯的 top-k 向量搜索，而是三段式稳健检索。

### Stage 0：查询规划

`QueryPlanner` 使用回答 LLM 将用户问题规整为 `QueryPlan`：

```python
QueryPlan(
    original_query="玛蒂儿达技能是啥",
    normalized_query="玛蒂尔达的技能、神秘术、传承和塑造是什么？",
    entity="玛蒂尔达",
    aliases=("玛蒂尔达", "Matilda Bouanich"),
    intent="skill",
    section_hints=("神秘术", "传承", "塑造"),
    scatter_terms=("玛蒂尔达", "Matilda Bouanich"),
    confidence=0.92,
)
```

合法 intent：

- `skill`
- `profile`
- `voice`
- `lore`
- `psychube`
- `general`

当 LLM 不可用或规划失败时，fallback 通过关键词推断 intent，并从问题中抽取散落词。fallback 不阻断问答，只降低召回精度。

### Stage 1：实体包召回

`EntityPacketRetriever` 收集候选：

- 如果 `plan.entity` 存在，用 Milvus filter `name == "{entity}"` 查询该实体的所有 chunk。
- 对 `plan.scatter_terms` 使用 `text like "%term%"` 收集散落命中。
- 对 `plan.normalized_query` 做向量召回，数量为 `max(top_k * 3, 12)`。
- 如果用户选择了 category，所有查询叠加 `category == "{category}"`。
- 候选按 id 或内容键去重。

这样做的原因是角色文档很长，技能、语音、单品、剧情片段可能分散在多个 heading，仅靠 top-k 向量召回容易把“语音”等噪声段排到前面。

### Stage 2：意图确认、重排、上下文打包

`RobustIntentRouter` 按 `(source, heading_path)` 将候选分组，并综合以下信号打分：

- heading 是否命中 intent 的 section hints。
- 用户问题关键词是否同时出现在 heading 或内容中。
- 组内最高向量分。
- 是否匹配规划出的实体名。
- 同一 heading 下多个相邻 chunk 的 adjacency bonus。
- 非 voice 意图下对 `语音`、`单品`、`箱中日历` 等噪声 heading 施加 penalty。

最终输出最多 `top_k` 个 chunk，并保留 debug 信息：

- `retrieval_stage`
- `intent`
- `router_intent`
- `section_score`
- `keyword_score`
- `vector_score`
- `entity_score`
- `adjacency_bonus`
- `noise_penalty`

普通向量 fallback 仍保留：如果没有 query plan 或没有实体/散落词，`Retriever.search()` 会根据 query、category、已知实体名执行相似度搜索。

## 生成设计

核心模块：`src/rag/chain.py`、`src/rag/prompts.py`

`RAGChain.ask()` 流程：

1. 调用 `retrieve(question, category)`。
2. 将 sources 格式化为上下文：`[name / heading_path] content`。
3. 用 `AssetRegistry` 查找相关图片资产。
4. 如果 `DEEPSEEK_API_KEY` 缺失，直接返回固定提示、sources 和 assets。
5. 如果没有 sources，返回 `知识库中未找到相关内容。`。
6. 调用 DeepSeek 生成回答。
7. 捕获 LLM 异常，返回 `调用 LLM 失败: ...`，同时保留 sources 和 assets。

固定空 key 提示：

```text
请在 .env 中配置 DEEPSEEK_API_KEY 后再提问。
```

系统提示词约束：

- 只使用已知信息，不编造设定、数值、剧情或人物关系。
- 资料不足时先说明资料不足，再基于已有信息做有限总结。
- 完全没有相关内容时才回答“知识库中未找到相关内容”。
- 优先整合成自然解释，不逐条复述检索片段。
- 可用要点列表。
- 引用来源时在句末用 `[来源名]` 标注。

## 后端 API 设计

核心模块：`backend/main.py`、`backend/schemas.py`、`backend/sse.py`

FastAPI 启动时调用 `_ensure_loaded()` 加载 Milvus vectorstore、Retriever 和 RAGChain。加载失败时后端仍可启动，但 `/health` 返回 `status=error`，问答接口返回明确 503。

### `GET /health`

返回：

```json
{
  "status": "ok",
  "vectorstore_loaded": true,
  "llm_ready": true,
  "doc_count": 1234
}
```

`doc_count` 对 Milvus 来自 collection stats 的 `row_count`。

### `POST /ask`

请求：

```json
{
  "question": "玛蒂尔达的技能是什么？",
  "category": "人物"
}
```

响应：

```json
{
  "answer": "回答正文",
  "sources": [
    {
      "name": "玛蒂尔达",
      "category": "人物",
      "source": "100-UTTU人物合辑/.../玛蒂尔达.md",
      "score": 86.4,
      "heading_path": "玛蒂尔达 > 神秘术",
      "chunk_index": 2,
      "retrieval_stage": "entity_name"
    }
  ],
  "assets": [
    {
      "asset_id": "sha1",
      "name": "玛蒂尔达",
      "category": "人物",
      "source": "100-UTTU人物合辑/.../玛蒂尔达.md",
      "heading_path": "玛蒂尔达 > 神秘术",
      "role": "skill",
      "alt": "神秘术 天才习作",
      "url": "http://127.0.0.1:9002/reverse1999-assets/..."
    }
  ]
}
```

### `POST /ask/stream`

使用 `text/event-stream`。React 端用 `fetch + ReadableStream`，不使用 `EventSource`，因为 EventSource 不能带 POST body。

事件顺序：

```text
event: sources
data: {"sources":[...],"assets":[...]}

event: token
data: {"token":"玛"}

event: token
data: {"token":"蒂"}

event: done
data: {"answer":"完整回答","sources":[...],"assets":[...]}
```

异常事件：

```text
event: error
data: {"message":"检索失败: ..."}
```

如果 `DEEPSEEK_API_KEY` 缺失，SSE 逐字发送固定提示，最后仍发送 `done`，并携带 sources 和 assets。

### `GET /categories`

返回六大 category 的静态元数据和当前索引里的文档块数量。前端资料页用它渲染分类面板。

### `GET /category/{key}/docs?limit=50`

从 Milvus 查询指定 category 的文档块，生成展示 snippet。snippet 会再次清理 dataview、表格行和 Obsidian 展示标记，避免前端资料卡显示噪声。

## 前端设计

### HTML、Streamlit、Gradio

三套轻量前端保留，用于快速本地访问和调试：

- HTML 同源挂载在 FastAPI 根路径。
- Streamlit 运行在 `:8501`。
- Gradio 运行在 `:7860`。

它们共用后端 `/ask` 或 HTTP 问答接口，不拥有独立 RAG 逻辑。

### React + Vite

React 前端运行在 `127.0.0.1:5173`。Vite 配置必须：

- `host: "127.0.0.1"`
- `port: 5173`
- `strictPort: true`
- proxy `/api` 到 `127.0.0.1:8000`

关键前端契约：

- `src/api/sse.ts` 负责解析 `/api/ask/stream` 的 SSE 事件。
- `src/store/chatStore.ts` 在 `sources` 事件后把 assistant 状态设为“DeepSeek 正在根据检索来源生成回答...”。
- token 事件逐步追加到最后一条 assistant 消息。
- done 事件写入最终 answer、sources、assets，并关闭 streaming 状态。
- error 事件把 assistant 消息置为错误文本。
- `MessageBubble` 渲染 assistant Markdown、来源和图片 assets。

## 启动设计

入口：`start.ps1`、`start.bat`

Windows 上不能依赖非交互 shell 的 `conda activate`，启动脚本先解析 conda 环境 `langchain` 的 Python 解释器绝对路径：

```powershell
conda run -n langchain python -c "import sys; print(sys.executable)"
```

启动流程：

1. 切到项目根。
2. 定位 conda `langchain` 环境 Python。
3. 如果 `data/processed/documents.jsonl` 不存在，执行 `scripts/extract_data.py` 和 `scripts/build_index.py`。
4. 检查 `8000` 和 `5173` 关键端口是否已被占用。
5. 启动 FastAPI：`python -m uvicorn backend.main:app --port 8000 --host 127.0.0.1`。
6. 轮询 `http://127.0.0.1:8000/health`，并要求 JSON `status == "ok"`。
7. 延迟启动 Streamlit。
8. 延迟启动 Gradio。
9. 如 React `node_modules` 不存在，执行 `npm install`。
10. 启动 React Vite：`npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`。
11. 打印四个访问地址。

设计约束：

- 健康检查固定使用 `127.0.0.1`，避免 Windows 上 `localhost` 解析到 IPv6 `::1`。
- Vite 不允许自动 fallback 到 `5174`，避免 proxy、CORS 和用户访问地址不一致。
- 启动脚本不再检查 `vectorstore\chroma.sqlite3`，也不再检查 Ollama。
- `start.ps1` 在退出时清理它启动的子进程。
- `start.bat` 会启动最小化窗口，停止服务时关闭对应窗口。

## 错误处理和降级

| 场景 | 行为 |
|---|---|
| Obsidian vault 不存在 | `extract_data.py` 抛出 `FileNotFoundError`，启动脚本停止 |
| frontmatter 解析失败 | 手动剥离 frontmatter 块，继续抽正文 |
| `documents.jsonl` 缺失 | `build_index.py` 提示先运行 `extract_data.py` |
| Milvus collection 不存在 | 后端 `_ensure_loaded()` 失败，`/health` 为 `error` |
| 后端加载失败 | `/ask` 返回 503 和“向量库加载失败...” |
| `SILICONFLOW_API_KEY` 缺失 | 索引构建或检索 embedding 调用失败，错误由脚本/API 暴露 |
| `DEEPSEEK_API_KEY` 缺失 | 返回固定提示，保留 sources/assets |
| 检索阶段异常 | SSE 返回 `error` 事件，不让连接静默中断 |
| LLM 调用异常 | 普通问答返回 `调用 LLM 失败: ...`，SSE 返回 `error` |
| assets 清单缺失 | `AssetRegistry` 返回空数组，不影响文本问答 |
| MinIO 凭据缺失 | `build_assets.py` 抛出明确凭据错误 |

## 安全和边界

- API key 不写入代码，优先从 `.env` 环境变量读取。
- 浏览器只接收 MinIO HTTP URL，不接收本地 `D:\...` 路径。
- FastAPI CORS 仅允许本地前端端口。
- Milvus 和 MinIO 默认绑定本地开发端口，不作为公网服务暴露。
- LLM prompt 明确限制只能基于检索上下文回答。

## 测试策略

Python 测试覆盖：

- `tests/test_config.py`：配置加载和环境变量覆盖。
- `tests/test_text_cleaner.py`：Obsidian Markdown 清洗。
- `tests/test_extractor.py`：分类、跳过规则、frontmatter 回退。
- `tests/test_vectorstore.py`：heading path、稳定 chunk id、batch progress。
- `tests/test_retriever.py`：实体精确召回、category filter、query plan 召回。
- `tests/test_query_plan.py`：LLM JSON 规划和 fallback。
- `tests/test_entity_packet.py`：实体包收集和去重。
- `tests/test_reranker.py`：意图重排、技能 section 优先于语音噪声。
- `tests/test_sse.py`：SSE 事件顺序、空 key 降级、category 传递、检索错误、assets 返回。
- `tests/test_categories.py`：分类元数据和分类文档 snippet。
- `tests/test_asset_*.py`：图片抽取、MinIO 上传清单、AssetRegistry 排序。
- `tests/test_start_scripts.py`：IPv4 health check、React Vite strict port、移除 Chroma/Ollama 旧检查。
- `tests/test_milvus_compose.py`：Milvus/MinIO compose 端口约束。

React 测试覆盖：

- SSE 解析。
- chat store 流式消息状态。
- MessageBubble Markdown、sources、assets 渲染。
- 分类面板数据加载和 fallback。
- 主题切换。
- scroll snap、顶部导航、滚轮节流和内部滚动区域。

推荐验证命令：

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests -v
cd frontend\react-app
npm test -- --run
```

需要真实外部服务的端到端验证：

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\infra\milvus
docker compose up -d

cd D:\PycharmProjects\nlp\LangChain\1999Search
$env:SILICONFLOW_API_KEY="..."
$env:DEEPSEEK_API_KEY="..."
$env:MINIO_ACCESS_KEY="minioadmin"
$env:MINIO_SECRET_KEY="minioadmin"

D:\anaconda32024\envs\LangChain\python.exe scripts\extract_data.py
D:\anaconda32024\envs\LangChain\python.exe scripts\build_assets.py
D:\anaconda32024\envs\LangChain\python.exe scripts\build_index.py
.\start.ps1
```

验收检查：

- `GET http://127.0.0.1:8000/health` 返回 `status=ok`。
- `POST /ask` 能返回 answer、sources 和 assets 字段。
- `POST /ask/stream` 事件顺序为 `sources -> token* -> done`。
- category 为 `人物` 时，sources 的 category 均为 `人物`。
- `DEEPSEEK_API_KEY` 为空时返回固定提示而不是 500。
- `GET /categories` 返回六个分类。
- `GET /category/人物/docs` 返回可展示 snippet。
- React 固定运行在 `http://localhost:5173`，不漂移到 `5174`。
- 聊天回答下方能显示相关图片资产；assets 清单缺失时文本问答仍可用。

## 当前文件职责

本 spec 是 RAG 系统的顶层设计说明，覆盖数据、检索、生成、API、前端契约、启动和验证。更细的专项设计由以下文档补充：

- `docs/superpowers/specs/2026-06-25-react-frontend-design.md`：React + Vite 前端体验设计。
- `docs/superpowers/specs/2026-07-01-reverse1999-minio-assets-design.md`：MinIO 图片资产接入设计。
- `docs/superpowers/specs/2026-07-01-reverse1999-wiki-browser-design.md`：独立 Wiki 浏览体验设计。
- `docs/architecture.md`：当前运行时架构简版说明。
- `docs/rag-assets.md`：图片资产构建和 MinIO 访问说明。
