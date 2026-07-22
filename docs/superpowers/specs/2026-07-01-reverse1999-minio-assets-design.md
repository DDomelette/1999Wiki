# Reverse:1999 MinIO 图片资产接入设计

日期：2026-07-01
项目：`1999Search`
状态：已确认实施

## 摘要

当前问答系统只能返回文本来源，无法把 Obsidian 角色文档里的立绘、神秘术图片、心相图片等一并带出。原因不是知识库没有图片，而是 RAG 清洗阶段会移除图片语法，前端聊天渲染也没有图片资产载体。

本设计采用 MinIO 对象存储作为图片访问层：数据构建阶段从原始 Obsidian Markdown 和 frontmatter 中提取图片引用，解析为本地文件，上传到 MinIO，生成 `data/processed/assets.jsonl` 映射清单；问答时在两阶段 RAG 完成文本召回和重排之后，根据 `source`、`heading_path`、`name`、`intent` 选择相关图片，以结构化 `assets` 字段返回给前端。

核心原则是：文本检索仍由 Milvus 和现有两阶段 RAG 负责，图片不进入向量检索主链路，而是作为结构化资产后挂载。

```text
Obsidian vault
  -> 原始 Markdown / frontmatter
  -> 图片资产抽取器
  -> MinIO bucket: reverse1999-assets
  -> data/processed/assets.jsonl

用户问题
  -> Stage 0 查询改写与意图识别
  -> Stage 1 实体包召回
  -> Stage 2 稳健重排
  -> AssetRegistry 按来源和意图选择图片
  -> FastAPI / SSE 返回 answer + sources + assets
  -> React 聊天窗口渲染文本和图片
```

## 目标

- 使用 MinIO 存储 Reverse:1999 知识库中的图片资源。
- 从 Obsidian 原始 Markdown 和 frontmatter 中提取图片引用。
- 支持 Obsidian 图片语法 `![[...]]`、标准 Markdown 图片语法 `![alt](...)`，以及 frontmatter 中的图片字段。
- 生成可重建的资产清单 `data/processed/assets.jsonl`。
- 在问答响应中返回结构化 `assets` 数据，而不是让 LLM 自行编造图片 Markdown。
- 支持角色立绘、神秘术图片、至终的仪式图片、心相图片、单品图片、海报图片等类型。
- 前端在聊天回答下方渲染图片资产，同时保留 Markdown 图片语法作为兜底。
- 不暴露本地 `D:\...` 路径给浏览器。

## 非目标

- 不把图片二进制写入 Milvus。
- 不把图片内容转成 embedding。
- 不要求 LLM 判断每张图片的语义内容。
- 不依赖 Base64 内嵌图片。
- 不直接把 Obsidian vault 作为静态目录暴露给浏览器。
- 不改动现有 Milvus collection schema。
- 不替换当前两阶段 RAG 文本检索方案。
- 不在本阶段接 CDN；MinIO 的 HTTP URL 先满足本地访问和浏览器缓存。

## 已知现状

当前相关代码边界如下：

- `src/utils/text_cleaner.py` 会移除 `![[...]]` 和 `![alt](url)` 图片语法。
- `src/extraction/obsidian_extractor.py` 在写入 `documents.jsonl` 前调用 `clean_markdown()`，所以向量库里的正文没有图片链接。
- `data/raw` 中保留了原始 Markdown，能看到大量立绘、神秘术、心相、海报等图片引用。
- `frontend/react-app/src/components/chat/MarkdownContent.tsx` 目前不渲染 Markdown 图片。
- `backend/schemas.py` 的 `AskResponse` 目前只有 `answer` 和 `sources`。
- 两阶段 RAG 已能根据实体名、散落引用、实际 `heading_path` 把相关文本召回并重排。

因此，图片接入不能只做“LLM 回答前 URL 替换”。因为 LLM 当前并不知道图片引用存在。正确位置是在数据构建阶段保留图片资产索引，并在检索完成后按来源挂载。

## 数据模型

资产清单使用 JSONL，每行一个图片资产。

建议字段：

```json
{
  "asset_id": "sha1-of-file",
  "name": "玛蒂尔达",
  "category": "人物",
  "source": "100-UTTU人物合辑/人类｜Human/玛蒂尔达｜Matilda Bouanich.md",
  "heading_path": "神秘术",
  "role": "skill",
  "alt": "天才习作 一阶",
  "raw_ref": "assets/玛蒂尔达｜Matilda Bouanich.assets/神秘术 天才习作1.png",
  "local_path": "D:/Obsidian_depot/Reverse1999/...",
  "object_key": "reverse1999/skill/ab/abcdef.png",
  "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/skill/ab/abcdef.png",
  "line": 64
}
```

字段含义：

- `asset_id`：文件内容 SHA1，用于去重和稳定对象名。
- `name`：文档实体名，优先来自 frontmatter `Name`，否则用文件名。
- `category`：沿用现有分类，例如 `人物`、`心相`、`剧情`。
- `source`：vault 相对 Markdown 路径，与 RAG source 字段对齐。
- `heading_path`：图片所在标题路径。frontmatter 图片为空字符串。
- `role`：图片类型，用于问答意图筛选。
- `alt`：展示名，来自 Markdown alt、Obsidian alias、frontmatter key 或文件名。
- `raw_ref`：原始图片引用，方便排查解析错误。
- `local_path`：本地真实路径，只用于构建和诊断，不返回给前端。
- `object_key`：MinIO 对象路径。
- `url`：浏览器可访问的 HTTP URL。
- `line`：图片引用所在 Markdown 行号，frontmatter 图片为 `0`。

## 图片类型

第一版使用规则分类，不引入模型识别。

建议 role：

- `portrait`：立绘、初始立绘、本色立绘、cover。
- `skill`：神秘术图片。
- `ultimate`：至终的仪式图片。
- `psychube`：心相图片。
- `item`：单品图片。
- `poster`：海报、banner。
- `unknown`：暂时无法分类但可安全展示的图片。

分类规则来自文件名、alt 文本、frontmatter key 和 `heading_path`。

## 图片路径解析

需要支持三类引用：

```markdown
![[assets/角色.assets/立绘 角色 01.png]]
![[assets/角色.assets/立绘 角色 01.png|立绘 角色 01.png]]
![神秘术 一阶](assets/角色.assets/神秘术%20技能1.png)
```

解析顺序：

1. 去掉 Obsidian alias，例如 `a.png|显示名` 只取 `a.png`。
2. URL decode `%20` 等编码。
3. 优先按当前 Markdown 文件所在目录解析相对路径。
4. 再按 vault 根目录解析 vault 相对路径。
5. 如果仍找不到，用文件名在当前文档目录和 vault 下做受限搜索。
6. 只接受图片后缀：`.png`、`.jpg`、`.jpeg`、`.webp`、`.gif`、`.bmp`、`.svg`。

如果图片解析失败，跳过该条，并在构建日志中计数。失败不应中断整个资产构建。

## MinIO 存储

配置新增：

```yaml
assets:
  provider: "minio"
  endpoint: "127.0.0.1:9002"
  public_base_url: "http://127.0.0.1:9002"
  bucket_name: "reverse1999-assets"
  secure: false
  object_prefix: "reverse1999"
```

凭据不写入 `settings.yaml`，使用环境变量：

```powershell
$env:MINIO_ACCESS_KEY="minioadmin"
$env:MINIO_SECRET_KEY="minioadmin"
```

对象 key 使用内容哈希，避免中文路径和重名文件造成冲突：

```text
reverse1999/{role}/{sha1前两位}/{sha1}{suffix}
```

示例：

```text
reverse1999/skill/ab/abcdef123456.png
```

这样即使 Obsidian 文件移动，只要图片内容不变，MinIO 对象地址仍稳定。

## 构建流程

新增脚本：

```text
scripts/build_assets.py
```

职责：

1. 读取 `config/settings.yaml` 和 `.env`。
2. 遍历 Obsidian vault 中现有 100-600 内容目录。
3. 对每个 Markdown 文件解析 frontmatter 和正文。
4. 提取图片引用并解析为本地文件。
5. 计算 SHA1，生成 `AssetRecord`。
6. 上传图片到 MinIO。
7. 写入 `data/processed/assets.jsonl`。

该脚本可以重复运行。同一份 vault 状态下，输出应稳定。

`data/processed/assets.jsonl` 是本地生成产物，当前 `data/processed/` 已在 `.gitignore` 中，不进入 git。

## 运行时资产挂载

新增 `AssetRegistry`，在后端启动时或首次使用时读取 `data/processed/assets.jsonl`。

挂载位置：

```text
RAGChain.retrieve()
  -> QueryPlanner.plan()
  -> Retriever.search()
  -> RobustIntentRouter.rerank()
  -> AssetRegistry.find_for_retrieval(plan, sources)
  -> return { plan, sources, context, assets }
```

选择规则：

- 优先匹配 `source + heading_path`。
- 再匹配同一 `source`。
- 再匹配同一 `name`。
- 根据 `intent` 调整图片 role 排序。

意图与图片排序建议：

```text
skill    -> skill, ultimate, portrait, unknown
profile  -> portrait, poster, unknown
psychube -> psychube, portrait, unknown
lore     -> poster, portrait, unknown
voice    -> portrait, unknown
general  -> portrait, skill, psychube, unknown
```

例如用户问“玛蒂尔达的技能是什么”，文本重排后命中 `玛蒂尔达.md / 神秘术`，图片选择应优先返回该 heading 下的 `skill` 和 `ultimate` 图片，再补充角色立绘。

例如用户问“有没有温妮弗雷德的立绘”，即使文本检索只命中角色主文档，也应返回 frontmatter 或 cover 中的 `portrait` 图片。

## 后端 API

新增响应模型：

```python
class AssetItem(BaseModel):
    asset_id: str
    name: str = ""
    category: str = ""
    source: str = ""
    heading_path: str | None = None
    role: str
    alt: str
    url: str
```

`AskResponse` 变为：

```python
class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    assets: list[AssetItem] = []
```

SSE 事件也携带 `assets`：

```json
event: sources
data: {"sources": [...], "assets": [...]}

event: done
data: {"answer": "...", "sources": [...], "assets": [...]}
```

`token` 事件不携带图片，避免每个 token 重复发送资产数据。

## 前端展示

前端消息类型新增：

```ts
export interface AssetItem {
  asset_id: string
  name?: string
  category?: string
  source?: string
  heading_path?: string | null
  role: string
  alt: string
  url: string
}
```

`Message` 新增：

```ts
assets?: AssetItem[]
```

展示方式：

- `MessageBubble` 在 assistant 文本下方渲染图片资产。
- 新增 `MessageAssets` 组件，用紧凑 gallery 展示图片。
- 图片使用 `loading="lazy"`。
- 图片 `object-fit: contain`，避免立绘或技能图被裁切。
- `MarkdownContent` 增加 Markdown 图片语法兜底，但结构化 `assets` 是主路径。

前端不处理本地路径，只接受 `http://127.0.0.1:9002/...` 这样的 HTTP URL。

## 错误处理

资产构建阶段：

- 单个图片解析失败：记录失败数量，继续处理其他图片。
- MinIO 凭据缺失：构建脚本直接报错，提示设置 `MINIO_ACCESS_KEY` 和 `MINIO_SECRET_KEY`。
- bucket 不存在：脚本自动创建 bucket。
- 上传失败：当前构建失败退出，避免生成半可信清单。

运行时：

- `assets.jsonl` 不存在：问答正常返回文本，`assets` 为空数组。
- 某个 asset URL 无法加载：前端只显示浏览器图片加载失败，不影响回答文本。
- RAG 未命中文本：不单独做全库图片搜索，仍返回“未找到相关内容”。
- 前端收到未知 role：按普通图片展示。

## 安全与边界

- 不把 MinIO 密钥写入 `settings.yaml`。
- 不把本地 `D:\...` 路径返回给前端。
- 不允许任意文件路径通过 API 读取。
- 资产 URL 只来自构建过的 manifest。
- MinIO bucket 可以在本地开发阶段设为可读；后续如果部署到公网，需要改成反向代理或预签名 URL。

## 测试策略

后端测试：

- 配置测试：确认 MinIO 设置从 YAML 读取，密钥从环境变量覆盖。
- 图片抽取测试：覆盖 frontmatter 立绘、正文神秘术图、Obsidian alias、Markdown 图片路径。
- 路径解析测试：覆盖相对路径、vault 相对路径、URL decode。
- manifest 构建测试：使用 fake storage 验证 URL 写入。
- registry 测试：验证 `source + heading_path` 优先级和 intent role 排序。
- chain 测试：验证 `RAGChain.retrieve()` 返回 `assets`。
- SSE 测试：验证 `sources` 和 `done` 事件携带 `assets`。

前端测试：

- SSE parser 能解析 `assets`。
- chat store 能把 `assets` 保存到 assistant message。
- `MessageBubble` 能渲染图片。
- `MarkdownContent` 能渲染 Markdown 图片兜底。

手工验收：

```text
有没有温妮弗雷德的立绘
```

预期：回答下方出现至少一张温妮弗雷德立绘。

```text
玛蒂尔达的技能是什么
```

预期：文本优先回答技能内容，图片区优先出现神秘术或至终的仪式图片；如果源文档缺少技能图，则至少不错误展示其他角色图片。

## 实施顺序

1. 添加 MinIO 配置和环境变量读取。
2. 实现资产模型和 Obsidian 图片抽取器。
3. 实现 MinIO 上传和 `assets.jsonl` 构建脚本。
4. 实现 `AssetRegistry`。
5. 在 `RAGChain.retrieve()` 中挂载 assets。
6. 扩展 FastAPI `/ask` 和 `/ask/stream` 响应。
7. 扩展前端类型、SSE parser、chat store。
8. 实现前端图片 gallery 和 Markdown 图片兜底。
9. 构建资产清单并做端到端验证。

## 与现有计划的关系

实施计划位于：

```text
docs/superpowers/plans/2026-07-01-reverse1999-minio-assets.md
```

本 specs 文档定义“要做什么”和“为什么这么做”；计划文档定义“按哪些步骤改哪些文件”。

## 开放问题

- MinIO bucket 是否长期保持公开读，还是后续改成后端代理或预签名 URL。
- 是否需要为图片资产增加缩略图版本，降低前端加载大图时的带宽和布局压力。
- 是否需要在后续把资产清单迁移到 SQLite 或其他轻量数据库。目前 JSONL 足够支撑 MVP。

## 自检

- 覆盖了 MinIO、图片抽取、资产清单、RAG 挂载、API/SSE、前端展示和验证流程。
- 没有要求修改 Milvus schema，也没有把图片混入向量检索主链路。
- 明确了本地路径只用于构建，不返回给浏览器。
- 明确了结构化 `assets` 是主路径，Markdown 图片替换只是兜底。
