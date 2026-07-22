# 1999Search 项目结构

> 本文件是项目的「结构地图」:以目录树为主体,逐项标注每个目录与关键文件的职责。
> 与 [architecture.md](../architecture.md) 互补——后者讲数据流与模块协作,本文件讲代码落点。
>
> 当前运行时(2026-06-29):Embedding 用 SiliconFlow `BAAI/bge-m3`,向量库用 Milvus(`reverse1999_rag.chunks_bge_m3_v1`)。启动以项目根 `start.ps1` / `start.bat` 为准。

## 0. 项目根目录速览

```
1999Search/
├── config/              统一配置层
├── src/                 核心库(extraction / rag / utils)
├── scripts/             数据提取与索引构建脚本
├── backend/             FastAPI 后端
├── frontend/            四套前端(html / streamlit / gradio / react-app)
├── tests/               单元测试 + fixtures
├── infra/               基础设施(Milvus docker-compose)
├── docs/                文档(本文件所在)
├── 动效预选/            React 前端动效参考图集
├── start.ps1            PowerShell 一键启动(推荐)
├── start.bat            CMD 一键启动
├── requirements.txt     Python 依赖
├── .env.example         环境变量样例(DEEPSEEK_API_KEY 等)
├── .gitignore
├── .gitattributes
└── README.md            项目说明
```

| 根级文件 / 目录 | 职责 |
|------|------|
| `config/` | 加载 `settings.yaml` + `.env`,单例 Config |
| `src/` | 核心业务库:Obsidian 提取、RAG 链、文本清洗 |
| `scripts/` | 一次性运维脚本:提取 vault 数据、建索引、生成板块封面 |
| `backend/` | FastAPI 应用,托管 RAG 接口与 HTML 前端 |
| `frontend/` | 四套前端 UI,统一调用后端 |
| `tests/` | pytest 单元测试 + 模拟 vault fixtures |
| `infra/` | Milvus 的 docker-compose 编排 |
| `docs/` | 架构文档 + superpowers specs/plans + 本结构文档 |
| `动效预选/` | React 前端设计阶段的动效参考截图(7 张 png) |
| `start.ps1` / `start.bat` | 一键启动:解析 conda 解释器 → (缺失时)提取+建索引 → 启后端 → 健康检查 → 延迟启动前端 |
| `requirements.txt` | Python 依赖清单 |
| `.env.example` | 环境变量样例;复制为 `.env` 填入 `DEEPSEEK_API_KEY` |
| `README.md` | 项目对外说明 |

---

## 1. 配置层 `config/`

```
config/
├── __init__.py
├── config.py
└── settings.yaml
```

| 文件 | 职责 |
|------|------|
| `config.py` | 单例 Config:加载 `settings.yaml`,用 `.env` 中的 `DEEPSEEK_API_KEY` 覆盖 yaml 空值;对外暴露统一配置对象 |
| `settings.yaml` | 全部可调项集中于此:obsidian.vault_path、embedding(provider/base_url/model/api_key)、llm、rag(chunk_size/overlap/top_k)、server(各端口)、vectorstore(milvus uri/db/collection) |
| `__init__.py` | 导出 Config 单例 |

---

## 2. 数据处理层

含三个目录:`src/extraction/`(提取器)、`src/utils/`(清洗)、`scripts/`(运维脚本)。

```
src/extraction/
├── __init__.py
└── obsidian_extractor.py

src/utils/
├── __init__.py
└── text_cleaner.py

scripts/
├── extract_data.py
├── build_index.py
└── generate_covers.py
```

| 文件 | 职责 |
|------|------|
| `src/extraction/obsidian_extractor.py` | 递归遍历 Obsidian vault,解析 frontmatter,按 `000~600` 六大类分类,落盘到 `data/raw`(镜像)与 `data/processed/documents.jsonl`(清洗+metadata) |
| `src/utils/text_cleaner.py` | Obsidian markdown 正文清洗纯函数:去 wikilink / embed / callout / 脚注 / HTML,保留可检索文本 |
| `scripts/extract_data.py` | 运行入口:调用 obsidian_extractor 产出 `data/` 目录 |
| `scripts/build_index.py` | 运行入口:`RecursiveCharacterTextSplitter` 切分 → embedding → 写入 Milvus collection |
| `scripts/generate_covers.py` | 一次性脚本:调用文生图接口生成 6 板块封面 png,入 `frontend/react-app/public/covers/` |

---

## 3. RAG 核心层 `src/rag/`

```
src/rag/
├── __init__.py
├── embeddings.py
├── vectorstore.py
├── retriever.py
├── chain.py
└── prompts.py
```

| 文件 | 职责 |
|------|------|
| `embeddings.py` | Embedding 封装,当前接 SiliconFlow `BAAI/bge-m3`(历史曾用 Ollama `qwen3-embedding:0.6b`) |
| `vectorstore.py` | Milvus collection 构建 / 加载 + 文本切分(`RecursiveCharacterTextSplitter`);自动检测缺失并触发重建 |
| `retriever.py` | 相似度搜索 + category metadata 过滤(人物/心相/剧情/世界/阵营/日历) |
| `chain.py` | RAG 链编排:retrieve → prompt → LLM;`api_key` 空时降级返回提示而非崩溃;新增 `_stream_llm` 支持 SSE 流式 |
| `prompts.py` | RAG prompt 模板(`get_rag_prompt`),含 system + human 消息构造 |

---

## 4. 后端服务 `backend/`

```
backend/
├── __init__.py
├── main.py
├── schemas.py
├── sse.py
└── categories_meta.py
```

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 应用:启动加载向量库,路由 `/health` `/ask` `/ask/stream` `/categories` `/category/{key}/docs`;CORS 放行各前端端口;同源托管 HTML 前端 |
| `schemas.py` | Pydantic 模型:`AskRequest` / `CategoryMeta` / `CategoryDoc` / `StreamEvent` 等 |
| `sse.py` | SSE 事件编码 + `rag_stream_generator`(sources → N×token → done 事件序列) |
| `categories_meta.py` | 6 板块元数据静态定义(key/title/subtitle/description/cover_prompt) |

---

## 5. 前端层 `frontend/`

四套前端,统一调用后端 RAG 接口。

```
frontend/
├── html/                  # 5.1 HTML+JS(同源托管,后端 :8000)
├── streamlit_app.py       # 5.2 Streamlit(:8501)
├── gradio_app.py          # 5.3 Gradio(:7860)
└── react-app/             # 5.4 React+Vite 沉浸式滚动叙事(:5173)
```

### 5.1 HTML+JS `frontend/html/`

```
frontend/html/
├── index.html
├── app.js
└── style.css
```

| 文件 | 职责 |
|------|------|
| `index.html` | 单页结构,后端 :8000 同源托管 |
| `app.js` | 调用 `/ask`,渲染问答与来源 |
| `style.css` | Reverse:1999 深色金紫主题 |

### 5.2 Streamlit `frontend/streamlit_app.py`

| 文件 | 职责 |
|------|------|
| `streamlit_app.py` | Streamlit UI,HTTP 调后端 `/ask`,运行于 :8501 |

### 5.3 Gradio `frontend/gradio_app.py`

| 文件 | 职责 |
|------|------|
| `gradio_app.py` | Gradio UI,HTTP 调后端 `/ask`,运行于 :7860 |

### 5.4 React+Vite `frontend/react-app/`

```
frontend/react-app/
├── index.html                 # 字体 preconnect + link(LXGW WenKai / Oswald)
├── package.json               # react@18 / vite@5 / framer-motion@11 / zustand@4 / vitest@2
├── package-lock.json
├── vite.config.ts             # proxy /api → 127.0.0.1:8000,port 5173 strictPort
├── tsconfig.json
├── tsconfig.node.json
├── .gitignore
├── public/
│   ├── videos/                # pv.mp4 + pv_old.mp4 + .gitkeep(首页视频背景)
│   ├── covers/                # 12 张板块封面 png(6 板块 × 中英双语)+ psychubes/(90+ 心相封面)
│   └── images/                # 角色立绘 standees/(180+) + assets/ 图标 + 心相印刻材料图
└── src/
    ├── App.tsx                # 根:scroll-snap 容器 + 3 大区(Home/Data/Chat)+ 全局 hook
    ├── main.tsx               # React 入口
    ├── vite-env.d.ts
    ├── test-setup.ts          # Vitest 测试 setup
    ├── api/
    │   ├── http.ts            # /health /ask /categories /category/{key}/docs
    │   ├── sse.ts             # fetch + ReadableStream 手动解析 SSE(非 EventSource)
    │   └── sse.test.ts
    ├── components/
    │   ├── Sidebar.tsx        # 左侧覆盖式控制栏(主题/板块速达/外链)
    │   ├── TopNav.tsx         # 顶端浮现导航(贴顶/滚到顶触发)
    │   ├── ScrollableDescription.tsx
    │   ├── StreamingDescription.tsx
    │   ├── ScrollableDescription.test.tsx
    │   ├── sections/
    │   │   ├── HomeSection.tsx        # 首页(视频背景 + 下载)
    │   │   ├── HomeSection.test.tsx
    │   │   ├── DataSection.tsx        # 资料页容器(scroll-snap 父,嵌 6 CategoryPanel)
    │   │   ├── CategoryPanel.tsx      # 单板块(进场动画 + 流式描述)
    │   │   ├── CategoryPanel.test.tsx
    │   │   └── ChatSection.tsx        # 问答页
    │   ├── chat/
    │   │   ├── MessageBubble.tsx      # 消息气泡(用户弹出 + LLM 流式)
    │   │   ├── MessageBubble.test.tsx
    │   │   ├── StreamingText.tsx      # 流式逐字 reveal
    │   │   └── ChatInput.tsx          # 输入框 + 发送
    │   └── ui/
    │       ├── ThemeToggle.tsx        # 三套主题循环切换
    │       ├── CategorySelect.tsx     # 顶部 category 下拉
    │       ├── LinkList.tsx           # 引用网站列表
    │       ├── SectionDivider.tsx     # SVG 花边分割线
    │       ├── AutoHideScrollbar.tsx  # 自动隐藏滚动条
    │       └── TiltedImageCard.tsx    # 倾斜悬浮图片卡
    ├── store/
    │   ├── themeStore.ts      # Zustand 持久化主题(localStorage r1999-theme)
    │   ├── themeStore.test.ts
    │   ├── uiStore.ts         # sidebar / topNav / currentSection / categoriesMeta
    │   ├── chatStore.ts       # messages / send / abort / setCategory
    │   └── chatStore.test.ts
    ├── hooks/
    │   ├── useScrollSpy.ts            # IntersectionObserver 监听 snap section
    │   ├── useScrollSpy.test.tsx
    │   ├── useTopNavTrigger.ts        # 贴顶 mousemove + scrollY 触发 TopNav
    │   ├── useTopNavTrigger.test.tsx
    │   └── useWheelSnapNavigation.ts  # 滚轮跨 section snap 控制
    ├── media/
    │   ├── assets.ts                  # 静态资源路径映射
    │   ├── assets.test.ts
    │   ├── characterStandees.ts       # 角色立绘清单
    │   └── psychubeCovers.ts          # 心相封面清单
    ├── data/
    │   └── fallbackCategories.ts      # /categories 拉取失败时的兜底元数据
    ├── styles/
    │   ├── global.css         # 全局基础样式
    │   ├── themes.css         # 3 套主题 CSS 变量(dark-warm / parchment / mystic-purple)
    │   └── decorative.css     # 神秘学花边/纹理装饰
    └── types/
        └── index.ts           # 共享 TS 类型(SourceItem / Message / CategoryMeta / Doc)
```

**React 前端关键说明**:
- **三段式滚动**:`App.tsx` 外层 `scroll-snap-type: y mandatory`,Home → Data(内嵌 6 CategoryPanel 各自 snap)→ Chat
- **SSE 流式**:不用 EventSource(只支持 GET),用 `fetch` + `ReadableStream` 手动解析 `sse.ts`
- **主题**:三套 CSS 变量经 `data-theme` 属性切换,`themeStore` 持久化到 localStorage
- **资源目录**:`public/covers/` 与 `public/images/` 含数百张图片(角色立绘 180+、心相封面 90+、板块封面 12 张中英双语),不入文档逐项列出,见各清单文件 `characterStandees.ts` / `psychubeCovers.ts`

---

## 6. 测试 `tests/`

```
tests/
├── conftest.py                # MockChain / MockVectorstore / fixtures
├── fixtures/
│   └── sample_vault/          # 模拟 Obsidian vault(含 .obsidian/ 000/ 100/ 600/ 四分区)
├── test_config.py
├── test_extractor.py
├── test_text_cleaner.py
├── test_prompts.py
├── test_vectorstore.py
├── test_retriever.py
├── test_categories.py
├── test_sse.py
├── test_milvus_compose.py
└── test_start_scripts.py
```

| 文件 | 职责 |
|------|------|
| `conftest.py` | 共享 fixtures:`MockChain`(`llm_ready` / `_retriever.search` / `_stream_llm`)、`MockVectorstore`(`_collection.count` / `similarity_search`)、sample_vault 路径 |
| `fixtures/sample_vault/` | 最小化模拟 vault:含 `.obsidian/app.json`、`000-箱的构造/templates/模板.md`、`100-UTTU人物合辑/神秘学家｜Arcanists/样本｜Sample.md`、`600-箱中日历/2023-06-01.md` |
| `test_config.py` | Config 加载与 .env 覆盖 |
| `test_extractor.py` | obsidian_extractor 分类与落盘 |
| `test_text_cleaner.py` | 清洗纯函数(wikilink/callout/HTML 去除) |
| `test_prompts.py` | RAG prompt 模板构造 |
| `test_vectorstore.py` | Milvus 构建/加载 + 缺失自动重建 |
| `test_retriever.py` | 相似度搜索 + category 过滤 |
| `test_categories.py` | `/categories` 返回 6 类 + `/category/{key}/docs` snippet |
| `test_sse.py` | `/ask/stream` 事件序列(sources → token → done)+ api_key 空降级 |
| `test_milvus_compose.py` | `infra/milvus/docker-compose.yml` 校验 |
| `test_start_scripts.py` | `start.ps1` / `start.bat` 结构校验 |

---

## 7. 基础设施与启动

```
infra/
└── milvus/
    └── docker-compose.yml     # Milvus 单机编排(uri: http://127.0.0.1:19530)

动效预选/                       # React 前端设计阶段动效参考截图(7 张 png)
├── 卡片及海报偏转动效.png
├── 卡片鼠标悬浮模糊.png
├── 数字加载.png
├── 最新资讯.png
├── 海报墙及卡片入场加载动画.png
├── 滚轮下滑模糊浮现.png
└── 边框高亮.png
```

| 文件 / 目录 | 职责 |
|------|------|
| `infra/milvus/docker-compose.yml` | Milvus + etcd + minio 单机编排,向量库后端 |
| `动效预选/` | React 前端动效设计参考图(非运行时依赖,仅设计阶段参考) |
| `start.ps1` | PowerShell 一键启动(推荐):解析 conda `langchain` 解释器路径 → 向量库缺失时 extract+build → uvicorn 后端 :8000 → 健康检查(60s 超时,固定 127.0.0.1 防 IPv6)→ 延迟启动 Streamlit/Gradio/React |
| `start.bat` | CMD 版同等流程 |
| `.env.example` | 环境变量样例;复制为 `.env` 填 `DEEPSEEK_API_KEY`,不填也能启动(`/ask` 降级提示) |

**启动时序**:
1. `conda run -n langchain python -c "..."` 解析 python.exe 绝对路径(绕过 `conda activate` 在非交互 shell 的限制)
2. 向量库缺失 → `extract_data.py` → `build_index.py`
3. uvicorn 启后端 :8000(绑定 127.0.0.1)
4. 轮询 `http://127.0.0.1:8000/health`(60s 超时)
5. 延迟 N 秒启动 Streamlit :8501 / Gradio :7860 / React :5173
6. 打印四个访问地址

---

## 8. 运行时生成目录(不入库)

以下目录由脚本/服务运行时生成,`.gitignore` 已忽略,不出现在仓库中,但运行后会出现:

| 目录 | 生成来源 | 内容 |
|------|----------|------|
| `data/raw/` | `scripts/extract_data.py` | Obsidian vault 镜像(原 markdown) |
| `data/processed/documents.jsonl` | `scripts/extract_data.py` | 清洗后文档 + metadata,一行一文档 |
| `vectorstore/`(历史) | `scripts/build_index.py` | 旧 Chroma 索引;当前已切 Milvus,此目录不再生成 |
| Milvus collection | `scripts/build_index.py` | `reverse1999_rag.chunks_bge_m3_v1`,存于 Milvus 实例内 |

> 重建索引:删 Milvus collection 后重跑 `python scripts/build_index.py`。
