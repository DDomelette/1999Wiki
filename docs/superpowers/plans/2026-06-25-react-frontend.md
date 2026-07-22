# React + Vite 前端实现计划 · 1999Search RAG

> CURRENT STATUS 2026-06-29: Historical implementation plan only. Do not copy the old `npm run dev` startup snippets from this file. Current launch scripts pin React Vite to `--host 127.0.0.1 --port 5173 --strictPort`; if port 5173 is occupied, stop the old process instead of letting Vite open 5174.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 1999Search RAG 项目新增第四套前端:基于 React 18 + Vite 5 + TypeScript 的沉浸式滚动叙事网站(首页视频 → 6 板块资料页 → 流式问答),并新增后端 SSE 流式端点与板块元数据接口。

**Architecture:** 后端新增 `/ask/stream`(SSE)、`/categories`、`/category/{key}/docs` 三个端点,复用现有 RAGChain 与向量库;前端用 Framer Motion 做进场/弹出/流式动画,Zustand 管理主题/UI/聊天状态,CSS scroll-snap 实现全屏板块切换,Vite 代理转发 /api 到后端 8000。

**Tech Stack:** React 18 + Vite 5 + TypeScript + Framer Motion 11 + Zustand 4 + Vitest 2 + FastAPI + Starlette StreamingResponse

---

## 文件结构总览

**后端(修改/新增)**:
- `backend/categories_meta.py` — 新增,6 板块元数据静态定义
- `backend/schemas.py` — 修改,新增 CategoryMeta / CategoryDoc 响应模型
- `backend/sse.py` — 新增,SSE 事件编码 + rag_stream_generator
- `backend/main.py` — 修改,新增 3 个路由 + CORS 加 5173
- `src/rag/chain.py` — 修改,新增 `_stream_llm` 方法

**前端(新增 `frontend/react-app/`)**:
- `package.json` / `vite.config.ts` / `tsconfig.json` / `index.html` — 脚手架
- `src/types/index.ts` — 共享 TS 类型
- `src/api/sse.ts` — SSE 客户端(fetch + ReadableStream)
- `src/api/http.ts` — 普通 HTTP 请求(/categories /category/{key}/docs /health)
- `src/store/themeStore.ts` — 主题(持久化)
- `src/store/uiStore.ts` — UI 状态(sidebar/topnav/section/category/categoriesMeta)
- `src/store/chatStore.ts` — 聊天状态
- `src/styles/themes.css` — 三套主题 CSS 变量
- `src/styles/global.css` — 全局样式 + 装饰元素
- `src/styles/decorative.css` — 花边/纹理 SVG
- `src/hooks/useScrollSpy.ts` — 滚动位置感知
- `src/hooks/useTopNavTrigger.ts` — 顶端导航触发
- `src/hooks/useCategoryData.ts` — 板块数据加载
- `src/components/Sidebar.tsx` — 控制栏
- `src/components/TopNav.tsx` — 顶端导航
- `src/components/ui/ThemeToggle.tsx` / `CategorySelect.tsx` / `LinkList.tsx` / `SectionDivider.tsx`
- `src/components/sections/HomeSection.tsx` — 首页
- `src/components/sections/DataSection.tsx` — 资料页容器
- `src/components/sections/CategoryPanel.tsx` — 单板块
- `src/components/sections/ChatSection.tsx` — 问答页
- `src/components/chat/MessageBubble.tsx` / `StreamingText.tsx` / `ChatInput.tsx`
- `src/App.tsx` / `src/main.tsx`
- `public/videos/.gitkeep` — 视频占位
- `public/covers/.gitkeep` — 封面占位

**测试**:
- `tests/test_sse.py` — SSE 端点测试
- `tests/test_categories.py` — 板块元数据接口测试
- `tests/conftest.py` — 修改,新增 MockChain / MockVectorstore
- `frontend/react-app/src/store/themeStore.test.ts`
- `frontend/react-app/src/store/chatStore.test.ts`
- `frontend/react-app/src/api/sse.test.ts`

**脚本与文档**:
- `scripts/generate_covers.py` — 新增,封面图片生成
- `start.ps1` / `start.bat` — 修改,增加 Vite 启动段
- `README.md` — 修改,加 React 行与 Node 要求

---

## Task 1: 后端 — 板块元数据静态定义与接口

**Files:**
- Create: `backend/categories_meta.py`
- Modify: `backend/schemas.py`
- Test: `tests/test_categories.py`

- [ ] **Step 1: 写失败测试 `tests/test_categories.py`**

```python
"""板块元数据接口测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client(monkeypatch, tmp_path):
    """构造带 mock 向量库的客户端。"""
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    # 重置单例与 _state
    main_mod._state = {"vs": None, "retriever": None, "chain": None, "loaded": False}
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    monkeypatch.setattr(main_mod, "_state", {
        "vs": MockVectorstore(doc_counts={"人物": 105, "心相": 90, "剧情": 46,
                                          "世界": 1, "阵营": 4, "日历": 506}),
        "retriever": None, "chain": None, "loaded": True,
    })
    return TestClient(main_mod.app)


def test_categories_returns_six_categories(client):
    """返回 6 类,每类含 key/title/subtitle/description/doc_count/cover_prompt。"""
    resp = client.get("/categories")
    assert resp.status_code == 200
    data = resp.json()
    cats = data["categories"]
    assert len(cats) == 6
    keys = [c["key"] for c in cats]
    assert keys == ["人物", "心相", "剧情", "世界", "阵营", "日历"]
    for c in cats:
        assert c["title"]
        assert c["subtitle"]
        assert c["description"]
        assert isinstance(c["doc_count"], int)
        assert c["doc_count"] > 0
        assert c["cover_prompt"]
    # 验证 doc_count 来自 mock
    person = next(c for c in cats if c["key"] == "人物")
    assert person["doc_count"] == 105


def test_category_docs_returns_snippets(client):
    """/category/人物/docs 返回 name/source/snippet。"""
    resp = client.get("/category/%E4%BA%BA%E7%89%A9/docs?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "人物"
    assert isinstance(data["docs"], list)
    for d in data["docs"]:
        assert d["name"]
        assert d["source"]
        assert d["snippet"]
        assert len(d["snippet"]) <= 200
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_categories.py -v`
Expected: FAIL,`/categories` 路由不存在

- [ ] **Step 3: 实现 `backend/categories_meta.py`**

```python
"""6 板块元数据静态定义(标题/简介/封面 prompt)。doc_count 运行时从向量库取。"""
from __future__ import annotations

CATEGORIES_META: list[dict] = [
    {
        "key": "人物",
        "title": "人物",
        "subtitle": "Characters",
        "description": "重返未来:1999 中的角色档案,含 UTTU 人物、神秘学家、维拉等阵营的英伦角色",
        "cover_prompt": "维多利亚时代英伦人物肖像,神秘学符号点缀,暖色调,复古油画质感",
    },
    {
        "key": "心相",
        "title": "心相",
        "subtitle": "Psychube",
        "description": "角色的精神具象武器,赋予能力与故事,每件心相都承载着神秘学家的记忆",
        "cover_prompt": "神秘学心相武器,发光符文,维多利亚装饰,暖金色调,复古插画",
    },
    {
        "key": "剧情",
        "title": "剧情",
        "subtitle": "Story",
        "description": "重返未来:1999 的主线与支线剧情,跨越不同时代的神秘学事件",
        "cover_prompt": "英伦雾都街景,神秘学事件场景,复古暖色调,油画质感",
    },
    {
        "key": "世界",
        "title": "世界",
        "subtitle": "World",
        "description": "游戏世界观设定,神秘学、暴雨、时代变迁的背景知识",
        "cover_prompt": "世界地图,维多利亚风格,神秘学符号,暖色复古",
    },
    {
        "key": "阵营",
        "title": "阵营",
        "subtitle": "Factions",
        "description": "游戏中的各大阵营组织,从基金会到神秘学家族",
        "cover_prompt": "阵营徽章,维多利亚纹章风格,金紫色,复古",
    },
    {
        "key": "日历",
        "title": "日历",
        "subtitle": "Calendar",
        "description": "箱中日历,每日一段神秘学见闻,记录圣保罗洛夫顿等地的奇闻",
        "cover_prompt": "复古日历,维多利亚装饰,神秘学符号,暖色调",
    },
]
```

- [ ] **Step 4: 修改 `backend/schemas.py` 新增模型**

在文件末尾追加:

```python
class CategoryMeta(BaseModel):
    key: str
    title: str
    subtitle: str
    description: str
    doc_count: int
    cover_prompt: str


class CategoriesResponse(BaseModel):
    categories: list[CategoryMeta]


class CategoryDoc(BaseModel):
    name: str
    source: str
    snippet: str


class CategoryDocsResponse(BaseModel):
    key: str
    docs: list[CategoryDoc]
```

- [ ] **Step 5: 修改 `backend/main.py` 新增 2 个路由**

在 `/ask` 路由之后、静态挂载之前插入:

```python
from backend.categories_meta import CATEGORIES_META
from backend.schemas import CategoriesResponse, CategoryDocsResponse

@app.get("/categories", response_model=CategoriesResponse)
async def categories():
    _ensure_loaded()
    vs = _state.get("vs")
    out = []
    for meta in CATEGORIES_META:
        doc_count = 0
        try:
            if vs is not None:
                doc_count = vs._collection.count(where={"category": meta["key"]})
        except Exception:
            pass
        out.append({
            "key": meta["key"],
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "description": meta["description"],
            "doc_count": doc_count,
            "cover_prompt": meta["cover_prompt"],
        })
    return CategoriesResponse(categories=out)


@app.get("/category/{key}/docs", response_model=CategoryDocsResponse)
async def category_docs(key: str, limit: int = 50):
    _ensure_loaded()
    vs = _state.get("vs")
    docs_out = []
    if vs is not None:
        try:
            from langchain_core.documents import Document
            results = vs.similarity_search(
                " ", k=limit, filter={"category": key}
            )
            for d in results:
                snippet = d.page_content[:200]
                docs_out.append({
                    "name": d.metadata.get("name", ""),
                    "source": d.metadata.get("source", ""),
                    "snippet": snippet,
                })
        except Exception as e:
            print(f"[backend] category_docs 查询失败: {e}")
    return CategoryDocsResponse(key=key, docs=docs_out)
```

- [ ] **Step 6: 修改 `tests/conftest.py` 新增 MockVectorstore**

在 conftest.py 末尾追加(若文件不存在则创建):

```python
"""测试共享 fixtures 与 mocks。"""
from __future__ import annotations

from langchain_core.documents import Document


class MockVectorstore:
    """模拟 Chroma 向量库,提供 count 与 similarity_search。"""

    def __init__(self, doc_counts: dict[str, int] | None = None,
                 docs_by_category: dict[str, list[Document]] | None = None) -> None:
        self._doc_counts = doc_counts or {}
        self._docs_by_category = docs_by_category or {}
        # 默认文档
        if not self._docs_by_category:
            self._docs_by_category = {
                "人物": [
                    Document(page_content="塞梅尔维斯是维拉阵营的神秘学家,擅长使用火焰神秘术。" * 3,
                             metadata={"name": "塞梅尔维斯", "category": "人物",
                                       "source": "100-UTTU人物辑录/塞梅尔维斯.md"}),
                    Document(page_content="曲娘是神秘学家,经营一家酒馆。" * 3,
                             metadata={"name": "曲娘", "category": "人物",
                                       "source": "100-UTTU人物辑录/曲娘.md"}),
                ],
            }

    class _Collection:
        def __init__(self, outer):
            self._outer = outer

        def count(self, where=None):
            if where and "category" in where:
                return self._outer._doc_counts.get(where["category"], 0)
            return sum(self._outer._doc_counts.values())

    @property
    def _collection(self):
        return MockVectorstore._Collection(self)

    def similarity_search(self, query: str, k: int = 4, filter=None):
        cat = (filter or {}).get("category")
        docs = self._docs_by_category.get(cat, [])
        return docs[:k]

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, filter=None):
        docs = self.similarity_search(query, k=k, filter=filter)
        return [(d, 0.5) for d in docs]
```

- [ ] **Step 7: 运行测试确认通过**

Run: `D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_categories.py -v`
Expected: 2 passed

- [ ] **Step 8: 提交**

```powershell
git add backend/categories_meta.py backend/schemas.py backend/main.py tests/test_categories.py tests/conftest.py
git commit -m "feat: add /categories and /category/{key}/docs endpoints with mock vectorstore"
```

---

## Task 2: 后端 — SSE 流式问答端点

**Files:**
- Modify: `src/rag/chain.py:30-50`(新增 `_stream_llm`)
- Create: `backend/sse.py`
- Modify: `backend/main.py`(新增 `/ask/stream` 路由 + CORS 加 5173)
- Test: `tests/test_sse.py`

- [ ] **Step 1: 写失败测试 `tests/test_sse.py`**

```python
"""SSE 流式问答端点测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """解析 SSE 文本流为 (event, data) 列表。"""
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        ev = block.split("event: ", 1)[1].split("\n", 1)[0] if "event: " in block else "message"
        data_line = [l for l in block.split("\n") if l.startswith("data: ")]
        data = json.loads(data_line[0][6:]) if data_line else {}
        events.append((ev, data))
    return events


@pytest.fixture
def client_with_mock_chain(monkeypatch):
    """api_key 就绪 + mock chain 流式固定 token。"""
    from backend import main as main_mod
    from tests.conftest import MockChain, MockVectorstore

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 2}),
        "retriever": None,
        "chain": MockChain(stream_tokens=["6", "是", "一位"], llm_ready=True),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    return TestClient(main_mod.app)


@pytest.fixture
def client_no_apikey(monkeypatch):
    """api_key 空,测降级。"""
    from backend import main as main_mod
    from tests.conftest import MockChain, MockVectorstore

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 2}),
        "retriever": None,
        "chain": MockChain(stream_tokens=[], llm_ready=False),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    return TestClient(main_mod.app)


def test_ask_stream_emits_sources_then_tokens_then_done(client_with_mock_chain):
    """事件顺序:sources → N×token → done,token 拼接为完整文本。"""
    with client_with_mock_chain.stream("POST", "/ask/stream",
                                       json={"question": "6是谁", "category": "人物"}) as resp:
        assert resp.status_code == 200
        text = resp.read().decode("utf-8")
    events = _parse_sse(text)
    event_types = [e[0] for e in events]
    assert event_types[0] == "sources"
    assert event_types[-1] == "done"
    assert event_types[1:-1] == ["token", "token", "token"]
    # token 拼接
    tokens = [e[1]["token"] for e in events if e[0] == "token"]
    assert "".join(tokens) == "6是一位"
    # done 携带完整 answer
    assert events[-1][1]["answer"] == "6是一位"
    # sources 非空
    assert len(events[0][1]["sources"]) > 0


def test_ask_stream_api_key_empty_emits_fallback(client_no_apikey):
    """api_key 空:逐字发降级提示,done 仍带 sources。"""
    with client_no_apikey.stream("POST", "/ask/stream",
                                 json={"question": "test"}) as resp:
        text = resp.read().decode("utf-8")
    events = _parse_sse(text)
    tokens = [e[1]["token"] for e in events if e[0] == "token"]
    full = "".join(tokens)
    assert "DEEPSEEK_API_KEY" in full
    assert events[-1][0] == "done"
    assert events[-1][1]["answer"] == full


def test_ask_stream_category_filter_passed(client_with_mock_chain):
    """category 参数传到 retriever(通过 mock chain 记录调用)。"""
    chain = client_with_mock_chain.app.dependency_overrides  # mock chain 已在 _state
    with client_with_mock_chain.stream("POST", "/ask/stream",
                                       json={"question": "x", "category": "人物"}) as resp:
        resp.read()
    # MockChain 记录最后一次 category
    from backend import main as main_mod
    mc = main_mod._state["chain"]
    assert mc.last_category == "人物"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_sse.py -v`
Expected: FAIL,`/ask/stream` 不存在

- [ ] **Step 3: 修改 `tests/conftest.py` 新增 MockChain**

在 conftest.py 末尾追加:

```python
class MockChain:
    """模拟 RAGChain,记录调用参数,返回固定流式 token。"""

    def __init__(self, stream_tokens: list[str], llm_ready: bool = True) -> None:
        self._tokens = stream_tokens
        self._ready = llm_ready
        self.last_category: str | None = None
        self._retriever = self._MockRetriever()

    class _MockRetriever:
        def search(self, query: str, k=None, category=None):
            return [{
                "name": "塞梅尔维斯", "category": category or "人物",
                "source": "mock.md", "score": 0.6,
                "content": "模拟内容",
            }]

    def llm_ready(self) -> bool:
        return self._ready

    def _stream_llm(self, question: str, context: str):
        for t in self._tokens:
            from langchain_core.outputs import ChatGenerationChunk
            from langchain_core.messages import AIMessageChunk
            yield ChatGenerationChunk(message=AIMessageChunk(content=t))
```

- [ ] **Step 4: 修改 `src/rag/chain.py` 新增 `_stream_llm` 方法**

在 `ask` 方法之后追加:

```python
    def _stream_llm(self, question: str, context: str):
        """DeepSeek 流式生成 token(生成器)。"""
        messages = self._prompt.format_messages(context=context, question=question)
        for chunk in self._llm.stream(messages):
            yield chunk
```

- [ ] **Step 5: 创建 `backend/sse.py`**

```python
"""SSE 工具:事件编码 + RAG 流式生成器。"""
from __future__ import annotations

import json
from typing import AsyncGenerator

_API_KEY_EMPTY_MSG = "请在 .env 中配置 DEEPSEEK_API_KEY 后再提问。"


def sse_event(event: str, data: dict) -> str:
    """编码单个 SSE 事件块。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def rag_stream_generator(chain, question: str, category: str | None) -> AsyncGenerator[str, None]:
    """RAG 流式生成器:先发 sources,再逐 token,最后 done。"""
    # 1. 检索
    sources = chain._retriever.search(question, category=category)
    chain.last_category = category  # 供测试断言
    source_items = [
        {"name": s["name"], "category": s["category"],
         "source": s["source"], "score": s["score"]}
        for s in sources
    ]
    yield sse_event("sources", {"sources": source_items})

    # 2. api_key 空降级
    if not chain.llm_ready():
        for ch in _API_KEY_EMPTY_MSG:
            yield sse_event("token", {"token": ch})
        yield sse_event("done", {"answer": _API_KEY_EMPTY_MSG, "sources": source_items})
        return

    # 3. DeepSeek 流式
    context = "\n\n".join(f"[{s['name']}] {s['content']}" for s in sources)
    full: list[str] = []
    try:
        for chunk in chain._stream_llm(question, context):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            if not token:
                continue
            full.append(token)
            yield sse_event("token", {"token": token})
    except Exception as e:
        yield sse_event("error", {"message": f"LLM 调用失败: {e}"})
        return
    yield sse_event("done", {"answer": "".join(full), "sources": source_items})
```

- [ ] **Step 6: 修改 `backend/main.py` 新增 `/ask/stream` 路由 + CORS**

CORS `allow_origins` 列表追加两行:
```python
        f"http://localhost:5173",
        f"http://127.0.0.1:5173",
```

在 `/ask` 路由之后插入(顶部 import 区加 `from starlette.responses import StreamingResponse` 与 `from backend.sse import rag_stream_generator, sse_event`):

```python
@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    _ensure_loaded()
    chain = _state.get("chain")
    if chain is None:
        return JSONResponse(
            {"answer": "向量库加载失败, 请检查 Ollama 与索引。", "sources": []},
            status_code=503,
        )
    gen = rag_stream_generator(chain, req.question, req.category)
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 7: 运行测试确认通过**

Run: `D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_sse.py -v`
Expected: 3 passed

- [ ] **Step 8: 运行全部测试确认无回归**

Run: `D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/ -v`
Expected: 全部 passed(原 12 + 新 5 = 17)

- [ ] **Step 9: 提交**

```powershell
git add src/rag/chain.py backend/sse.py backend/main.py tests/test_sse.py tests/conftest.py
git commit -m "feat: add /ask/stream SSE endpoint with mock chain tests"
```

---

## Task 3: React 脚手架与配置

**Files:**
- Create: `frontend/react-app/package.json`
- Create: `frontend/react-app/vite.config.ts`
- Create: `frontend/react-app/tsconfig.json`
- Create: `frontend/react-app/tsconfig.node.json`
- Create: `frontend/react-app/index.html`
- Create: `frontend/react-app/src/main.tsx`
- Create: `frontend/react-app/src/App.tsx`(占位)
- Create: `frontend/react-app/src/vite-env.d.ts`
- Create: `frontend/react-app/public/videos/.gitkeep`
- Create: `frontend/react-app/public/covers/.gitkeep`
- Create: `frontend/react-app/.gitignore`

- [ ] **Step 1: 创建 `package.json`**

```json
{
  "name": "r1999-react-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "framer-motion": "^11.3.0",
    "zustand": "^4.5.4"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.4.0",
    "vitest": "^2.0.5",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.8",
    "jsdom": "^24.1.1"
  }
}
```

- [ ] **Step 2: 创建 `vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

- [ ] **Step 3: 创建 `tsconfig.json` 与 `tsconfig.node.json`**

`tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: 创建 `index.html`**

```html
<!doctype html>
<html lang="zh-CN" data-theme="dark-warm">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>1999Search · 重返未来 1999 RAG</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://cdn.jsdelivr.net">
    <link href="https://cdn.jsdelivr.net/npm/lxgw-wenkai-webfont@1.7.0/style.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap" rel="stylesheet">
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: 创建 `src/main.tsx`**

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/global.css'
import './styles/themes.css'
import './styles/decorative.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

- [ ] **Step 6: 创建 `src/App.tsx` 占位**

```typescript
export default function App() {
  return <div style={{ padding: 40 }}>1999Search React 前端 — 脚手架就绪</div>
}
```

- [ ] **Step 7: 创建 `src/vite-env.d.ts` 与 `src/test-setup.ts`**

`src/vite-env.d.ts`:
```typescript
/// <reference types="vite/client" />
```

`src/test-setup.ts`:
```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 8: 创建空样式占位文件**

`src/styles/global.css`:
```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: var(--font-body, 'LXGW WenKai', serif); background: var(--bg-base, #1a1410); color: var(--text-primary, #e8d9c0); }
```

`src/styles/themes.css`:
```css
/* 主题占位,Task 5 填充完整 */
:root { --font-body: 'LXGW WenKai', serif; --bg-base: #1a1410; --text-primary: #e8d9c0; }
```

`src/styles/decorative.css`:
```css
/* 装饰元素占位,Task 5 填充 */
```

- [ ] **Step 9: 创建占位目录与 .gitignore**

`public/videos/.gitkeep`(空文件)
`public/covers/.gitkeep`(空文件)

`frontend/react-app/.gitignore`:
```
node_modules
dist
*.local
.vitest
```

- [ ] **Step 10: 安装依赖并验证 dev server 启动**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```
Expected: Vite 启动在 http://localhost:5173,浏览器显示"1999Search React 前端 — 脚手架就绪"。Ctrl+C 退出。

- [ ] **Step 11: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/
git commit -m "feat: scaffold React+Vite+TS frontend with fonts and proxy config"
```

---

## Task 4: 前端 — 类型定义与 API 客户端

**Files:**
- Create: `frontend/react-app/src/types/index.ts`
- Create: `frontend/react-app/src/api/http.ts`
- Create: `frontend/react-app/src/api/sse.ts`
- Test: `frontend/react-app/src/api/sse.test.ts`

- [ ] **Step 1: 创建 `src/types/index.ts`**

```typescript
export interface SourceItem {
  name: string
  category: string
  source: string
  score: number
}

export interface CategoryMeta {
  key: string
  title: string
  subtitle: string
  description: string
  doc_count: number
  cover_prompt: string
}

export interface CategoryDoc {
  name: string
  source: string
  snippet: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceItem[]
  streaming?: boolean
}

export type Theme = 'dark-warm' | 'parchment' | 'mystic-purple'
```

- [ ] **Step 2: 创建 `src/api/http.ts`**

```typescript
import type { CategoryMeta, CategoryDoc } from '../types'

export async function fetchCategories(): Promise<CategoryMeta[]> {
  const res = await fetch('/api/categories')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.categories as CategoryMeta[]
}

export async function fetchCategoryDocs(key: string, limit = 5): Promise<CategoryDoc[]> {
  const res = await fetch(`/api/category/${encodeURIComponent(key)}/docs?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.docs as CategoryDoc[]
}

export async function fetchHealth(): Promise<{ status: string; doc_count: number; llm_ready: boolean }> {
  const res = await fetch('/health')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
```

- [ ] **Step 3: 写失败测试 `src/api/sse.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { streamAsk } from './sse'
import type { SourceItem } from '../types'

function mockFetchResponse(chunks: string[]) {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      chunks.forEach(c => controller.enqueue(encoder.encode(c)))
      controller.close()
    },
  })
  return {
    ok: true,
    body: stream,
    status: 200,
  } as Response
}

describe('streamAsk SSE 解析', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('正确解析 sources → tokens → done 事件序列', async () => {
    const chunks = [
      'event: sources\ndata: {"sources":[{"name":"塞梅尔维斯","category":"人物","source":"x.md","score":0.6}]}\n\n',
      'event: token\ndata: {"token":"6"}\n\n',
      'event: token\ndata: {"token":"是"}\n\n',
      'event: done\ndata: {"answer":"6是","sources":[]}\n\n',
    ]
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse(chunks))

    const tokens: string[] = []
    let sources: SourceItem[] = []
    let doneAnswer = ''
    await streamAsk('6', null, {
      onSources: s => { sources = s },
      onToken: t => { tokens.push(t) },
      onDone: (a) => { doneAnswer = a },
      onError: () => {},
    })
    expect(sources).toHaveLength(1)
    expect(sources[0].name).toBe('塞梅尔维斯')
    expect(tokens).toEqual(['6', '是'])
    expect(doneAnswer).toBe('6是')
  })

  it('正确处理跨 chunk 拼接的事件块', async () => {
    const chunks = [
      'event: tok',
      'en\ndata: {"token":"6"}\n\nevent: do',
      'ne\ndata: {"answer":"6","sources":[]}\n\n',
    ]
    vi.mocked(fetch).mockResolvedValueOnce(mockFetchResponse(chunks))
    const tokens: string[] = []
    let done = false
    await streamAsk('q', null, {
      onSources: () => {},
      onToken: t => tokens.push(t),
      onDone: () => { done = true },
      onError: () => {},
    })
    expect(tokens).toEqual(['6'])
    expect(done).toBe(true)
  })

  it('HTTP 错误抛异常', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 503 } as Response)
    await expect(streamAsk('q', null, {
      onSources: () => {}, onToken: () => {}, onDone: () => {}, onError: () => {}
    })).rejects.toThrow('HTTP 503')
  })
})
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd frontend\react-app && npx vitest run src/api/sse.test.ts`
Expected: FAIL,`streamAsk` 不存在

- [ ] **Step 5: 创建 `src/api/sse.ts`**

```typescript
import type { SourceItem } from '../types'

export interface StreamCallbacks {
  onSources: (sources: SourceItem[]) => void
  onToken: (token: string) => void
  onDone: (answer: string, sources: SourceItem[]) => void
  onError: (msg: string) => void
}

export async function streamAsk(
  question: string,
  category: string | null,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, category }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      if (!block.trim()) continue
      const eventMatch = block.match(/^event: (.+)$/m)
      const dataMatch = block.match(/^data: (.+)$/m)
      const event = eventMatch ? eventMatch[1] : 'message'
      const data = dataMatch ? JSON.parse(dataMatch[1]) : {}
      if (event === 'sources') callbacks.onSources(data.sources as SourceItem[])
      else if (event === 'token') callbacks.onToken(data.token as string)
      else if (event === 'done') callbacks.onDone(data.answer as string, data.sources as SourceItem[])
      else if (event === 'error') callbacks.onError(data.message as string)
    }
  }
}
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd frontend\react-app && npx vitest run src/api/sse.test.ts`
Expected: 3 passed

- [ ] **Step 7: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/types/ frontend/react-app/src/api/
git commit -m "feat: add TS types and SSE/HTTP API clients with tests"
```

---

## Task 5: 前端 — Zustand Store 与主题样式

**Files:**
- Create: `frontend/react-app/src/store/themeStore.ts`
- Create: `frontend/react-app/src/store/uiStore.ts`
- Create: `frontend/react-app/src/store/chatStore.ts`
- Modify: `frontend/react-app/src/styles/themes.css`
- Modify: `frontend/react-app/src/styles/global.css`
- Modify: `frontend/react-app/src/styles/decorative.css`
- Test: `frontend/react-app/src/store/themeStore.test.ts`
- Test: `frontend/react-app/src/store/chatStore.test.ts`

- [ ] **Step 1: 写失败测试 `src/store/themeStore.test.ts`**

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useThemeStore } from './themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    useThemeStore.getState().set('dark-warm')
    localStorage.clear()
  })

  it('cycle 顺序:dark-warm → parchment → mystic-purple → dark-warm', () => {
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('parchment')
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('mystic-purple')
    useThemeStore.getState().cycle()
    expect(useThemeStore.getState().theme).toBe('dark-warm')
  })

  it('cycle 后 <html data-theme> 同步更新', () => {
    useThemeStore.getState().cycle()
    expect(document.documentElement.getAttribute('data-theme')).toBe('parchment')
  })

  it('set 直接设置主题并同步 <html>', () => {
    useThemeStore.getState().set('mystic-purple')
    expect(useThemeStore.getState().theme).toBe('mystic-purple')
    expect(document.documentElement.getAttribute('data-theme')).toBe('mystic-purple')
  })
})
```

- [ ] **Step 2: 写失败测试 `src/store/chatStore.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'
import * as sse from '../api/sse'

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.getState().clear()
    vi.restoreAllMocks()
  })

  it('send 推入用户消息后流式追加 assistant 消息', async () => {
    vi.spyOn(sse, 'streamAsk').mockImplementation(async (_q, _c, cb) => {
      cb.onSources([{ name: '塞梅尔维斯', category: '人物', source: 'x.md', score: 0.6 }])
      cb.onToken('6')
      cb.onToken('是')
      cb.onDone('6是', [{ name: '塞梅尔维斯', category: '人物', source: 'x.md', score: 0.6 }])
    })
    await useChatStore.getState().send('6是谁')
    const msgs = useChatStore.getState().messages
    expect(msgs).toHaveLength(2)
    expect(msgs[0].role).toBe('user')
    expect(msgs[0].content).toBe('6是谁')
    expect(msgs[1].role).toBe('assistant')
    expect(msgs[1].content).toBe('6是')
    expect(msgs[1].streaming).toBe(false)
    expect(msgs[1].sources).toHaveLength(1)
    expect(useChatStore.getState().sending).toBe(false)
  })

  it('setCategory 更新 category', () => {
    useChatStore.getState().setCategory('人物')
    expect(useChatStore.getState().category).toBe('人物')
    useChatStore.getState().setCategory(null)
    expect(useChatStore.getState().category).toBeNull()
  })

  it('clear 清空消息', () => {
    useChatStore.setState({ messages: [{ id: '1', role: 'user', content: 'x' }] })
    useChatStore.getState().clear()
    expect(useChatStore.getState().messages).toHaveLength(0)
  })
})
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd frontend\react-app && npx vitest run src/store/`
Expected: FAIL,store 文件不存在

- [ ] **Step 4: 创建 `src/store/themeStore.ts`**

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Theme } from '../types'

const ORDER: Theme[] = ['dark-warm', 'parchment', 'mystic-purple']

interface ThemeState {
  theme: Theme
  cycle: () => void
  set: (t: Theme) => void
}

function applyTheme(t: Theme) {
  document.documentElement.setAttribute('data-theme', t)
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'dark-warm',
      cycle: () => {
        const next = ORDER[(ORDER.indexOf(get().theme) + 1) % ORDER.length]
        set({ theme: next })
        applyTheme(next)
      },
      set: (t) => {
        set({ theme: t })
        applyTheme(t)
      },
    }),
    {
      name: 'r1999-theme',
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme)
      },
    },
  ),
)
```

- [ ] **Step 5: 创建 `src/store/uiStore.ts`**

```typescript
import { create } from 'zustand'
import type { CategoryMeta } from '../types'

type Section = 'home' | 'data' | 'chat'

interface UIState {
  sidebarOpen: boolean
  topNavVisible: boolean
  currentSection: Section
  currentCategory: string | null
  categoriesMeta: CategoryMeta[]
  toggleSidebar: () => void
  setSidebar: (v: boolean) => void
  setTopNav: (v: boolean) => void
  setSection: (s: Section) => void
  setCategory: (c: string | null) => void
  setCategoriesMeta: (m: CategoryMeta[]) => void
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  topNavVisible: false,
  currentSection: 'home',
  currentCategory: null,
  categoriesMeta: [],
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebar: (v) => set({ sidebarOpen: v }),
  setTopNav: (v) => set({ topNavVisible: v }),
  setSection: (s) => set({ currentSection: s }),
  setCategory: (c) => set({ currentCategory: c }),
  setCategoriesMeta: (m) => set({ categoriesMeta: m }),
}))
```

- [ ] **Step 6: 创建 `src/store/chatStore.ts`**

```typescript
import { create } from 'zustand'
import type { Message, SourceItem } from '../types'
import { streamAsk } from '../api/sse'

interface ChatState {
  messages: Message[]
  category: string | null
  sending: boolean
  abortController: AbortController | null
  send: (question: string) => Promise<void>
  abort: () => void
  setCategory: (c: string | null) => void
  clear: () => void
}

function makeId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  category: null,
  sending: false,
  abortController: null,
  send: async (question: string) => {
    if (get().sending) return
    const userMsg: Message = { id: makeId(), role: 'user', content: question }
    const assistantMsg: Message = { id: makeId(), role: 'assistant', content: '', streaming: true }
    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      sending: true,
    }))
    const controller = new AbortController()
    set({ abortController: controller })
    const updateLast = (patch: Partial<Message>) =>
      set((s) => ({
        messages: s.messages.map((m, i) =>
          i === s.messages.length - 1 ? { ...m, ...patch } : m
        ),
      }))
    try {
      await streamAsk(question, get().category, {
        onSources: (sources: SourceItem[]) => updateLast({ sources }),
        onToken: (token: string) =>
          set((s) => ({
            messages: s.messages.map((m, i) =>
              i === s.messages.length - 1
                ? { ...m, content: m.content + token }
                : m
            ),
          })),
        onDone: (answer, sources) =>
          updateLast({ content: answer, sources, streaming: false }),
        onError: (msg) => updateLast({ content: `错误: ${msg}`, streaming: false }),
      }, controller.signal)
    } catch (e) {
      updateLast({ content: `请求失败: ${(e as Error).message}`, streaming: false })
    } finally {
      set({ sending: false, abortController: null })
    }
  },
  abort: () => {
    const c = get().abortController
    if (c) c.abort()
    set((s) => ({
      sending: false,
      abortController: null,
      messages: s.messages.map((m, i) =>
        i === s.messages.length - 1 ? { ...m, streaming: false } : m
      ),
    }))
  },
  setCategory: (c) => set({ category: c }),
  clear: () => set({ messages: [] }),
}))
```

- [ ] **Step 7: 完整填充 `src/styles/themes.css`**

```css
/* 主题1:深色复古暖(默认) */
[data-theme="dark-warm"] {
  --bg-base: #1a1410;
  --bg-elevated: #241c16;
  --bg-overlay: rgba(26, 20, 16, 0.85);
  --text-primary: #e8d9c0;
  --text-secondary: #b8a888;
  --text-muted: #7a6a52;
  --accent-gold: #d4af37;
  --accent-purple: #7b5ea7;
  --accent-rust: #a85432;
  --border-subtle: #3a2e22;
  --border-card: #4a3a2a;
  --border-glow: rgba(212, 175, 55, 0.4);
  --shadow-card: 0 4px 20px rgba(0, 0, 0, 0.5), 0 0 1px var(--border-card);
  --shadow-glow: 0 0 20px var(--border-glow);
  --font-body: 'LXGW WenKai', 'Noto Serif SC', serif;
  --font-display: 'Oswald', 'LXGW WenKai', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

/* 主题2:浅色羊皮纸 */
[data-theme="parchment"] {
  --bg-base: #f4ead5;
  --bg-elevated: #fbf5e6;
  --bg-overlay: rgba(244, 234, 213, 0.9);
  --text-primary: #3a2818;
  --text-secondary: #6b5236;
  --text-muted: #9a8260;
  --accent-gold: #b8860b;
  --accent-purple: #6b4c8a;
  --accent-rust: #8b3a1f;
  --border-subtle: #d9c9a8;
  --border-card: #b8a072;
  --border-glow: rgba(184, 134, 11, 0.35);
  --shadow-card: 0 2px 12px rgba(120, 80, 40, 0.15), 0 0 1px var(--border-card);
  --shadow-glow: 0 0 16px var(--border-glow);
  --font-body: 'LXGW WenKai', 'Noto Serif SC', serif;
  --font-display: 'Oswald', 'LXGW WenKai', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

/* 主题3:神秘紫夜间 */
[data-theme="mystic-purple"] {
  --bg-base: #120a1f;
  --bg-elevated: #1c1230;
  --bg-overlay: rgba(18, 10, 31, 0.88);
  --text-primary: #d9c9f0;
  --text-secondary: #a890c8;
  --text-muted: #6a5488;
  --accent-gold: #e8c547;
  --accent-purple: #9d7ec9;
  --accent-rust: #c4628a;
  --border-subtle: #2e1f48;
  --border-card: #3e2a5e;
  --border-glow: rgba(157, 126, 201, 0.5);
  --shadow-card: 0 4px 24px rgba(0, 0, 0, 0.6), 0 0 1px var(--border-card);
  --shadow-glow: 0 0 24px var(--border-glow);
  --font-body: 'LXGW WenKai', 'Noto Serif SC', serif;
  --font-display: 'Oswald', 'LXGW WenKai', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

- [ ] **Step 8: 完整填充 `src/styles/global.css`**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

html, body, #root {
  height: 100%;
  width: 100%;
}

body {
  font-family: var(--font-body);
  background: var(--bg-base);
  color: var(--text-primary);
  overflow: hidden;
  transition: background 0.4s ease, color 0.4s ease;
}

/* 羊皮纸噪声纹理叠加 */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.04;
  z-index: 1000;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");
  mix-blend-mode: overlay;
}

button {
  font-family: inherit;
  cursor: pointer;
  border: none;
  background: none;
  color: inherit;
}

a { color: var(--accent-gold); text-decoration: none; }
a:hover { text-shadow: 0 0 8px var(--border-glow); }

/* scroll-snap 主容器 */
.snap-container {
  height: 100vh;
  overflow-y: scroll;
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
}

.snap-section {
  height: 100vh;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  position: relative;
}

/* 卡片基础样式 */
.card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-card);
  border-radius: 4px;
  box-shadow: var(--shadow-card);
  padding: 24px;
}

/* 滚动条 */
.snap-container::-webkit-scrollbar { width: 6px; }
.snap-container::-webkit-scrollbar-track { background: var(--bg-base); }
.snap-container::-webkit-scrollbar-thumb { background: var(--border-card); border-radius: 3px; }
```

- [ ] **Step 9: 完整填充 `src/styles/decorative.css`**

```css
/* PKMer 风格花边卡片角花 */
.card-ornate {
  position: relative;
}
.card-ornate::before,
.card-ornate::after {
  content: '';
  position: absolute;
  width: 24px;
  height: 24px;
  border: 2px solid var(--accent-gold);
  opacity: 0.6;
}
.card-ornate::before {
  top: 8px; left: 8px;
  border-right: none; border-bottom: none;
}
.card-ornate::after {
  bottom: 8px; right: 8px;
  border-left: none; border-top: none;
}

/* AnuPpuccin 风格板块标识竖条 */
.category-bar {
  width: 4px;
  height: 100%;
  background: linear-gradient(180deg, var(--accent-gold), var(--accent-purple), var(--accent-rust));
  border-radius: 2px;
}

/* 花边分割线 */
.divider-ornate {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--accent-gold);
  opacity: 0.6;
}
.divider-ornate::before,
.divider-ornate::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent-gold), transparent);
}
.divider-ornate .diamond {
  width: 8px;
  height: 8px;
  background: var(--accent-gold);
  transform: rotate(45deg);
}

/* SVG 花边 strokeDashoffset 绘制动画(装饰角花) */
.ornate-corner-svg {
  position: absolute;
  width: 40px;
  height: 40px;
  pointer-events: none;
}
.ornate-corner-svg path {
  stroke: var(--accent-gold);
  stroke-width: 1.5;
  fill: none;
  stroke-dasharray: 100;
  stroke-dashoffset: 100;
  animation: draw-stroke 1.2s ease-out forwards;
  animation-delay: 0.5s;
}
@keyframes draw-stroke {
  to { stroke-dashoffset: 0; }
}
.ornate-tl { top: 0; left: 0; }
.ornate-tr { top: 0; right: 0; transform: scaleX(-1); }
.ornate-bl { bottom: 0; left: 0; transform: scaleY(-1); }
.ornate-br { bottom: 0; right: 0; transform: scale(-1, -1); }

/* 神秘学符号(Blue Topaz 风格) */
.mystic-icon {
  width: 16px;
  height: 16px;
  fill: var(--accent-gold);
  opacity: 0.8;
}
```

- [ ] **Step 10: 运行测试确认通过**

Run: `cd frontend\react-app && npx vitest run src/store/`
Expected: 6 passed(themeStore 3 + chatStore 3)

- [ ] **Step 11: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/store/ frontend/react-app/src/styles/
git commit -m "feat: add Zustand stores (theme/ui/chat) and 3-theme CSS with decorative elements"
```

---

## Task 6: 前端 — Hooks(滚动感知、顶端导航触发、板块数据)

**Files:**
- Create: `frontend/react-app/src/hooks/useScrollSpy.ts`
- Create: `frontend/react-app/src/hooks/useTopNavTrigger.ts`
- Create: `frontend/react-app/src/hooks/useCategoryData.ts`

- [ ] **Step 1: 创建 `src/hooks/useScrollSpy.ts`**

```typescript
import { useEffect } from 'react'
import { useUIStore } from '../store/uiStore'

/** 监听所有 [data-snap-section] 元素可见性,写入 uiStore.currentSection / currentCategory。 */
export function useScrollSpy() {
  useEffect(() => {
    const sections = document.querySelectorAll('[data-snap-section]')
    if (sections.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
            const section = entry.target.getAttribute('data-snap-section') || ''
            if (section.startsWith('data:')) {
              useUIStore.getState().setSection('data')
              useUIStore.getState().setCategory(section.split(':')[1])
            } else if (section === 'home' || section === 'data' || section === 'chat') {
              useUIStore.getState().setSection(section)
              if (section !== 'data') useUIStore.getState().setCategory(null)
            }
          }
        }
      },
      { threshold: [0.5, 0.75] },
    )
    sections.forEach((s) => observer.observe(s))
    return () => observer.disconnect()
  }, [])
}
```

- [ ] **Step 2: 创建 `src/hooks/useTopNavTrigger.ts`**

```typescript
import { useEffect } from 'react'
import { useUIStore } from '../store/uiStore'

/** 鼠标贴顶端(y<8px)或滚到顶(scrollY<50)时显示 TopNav。 */
export function useTopNavTrigger() {
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      const atTop = window.scrollY < 50
      const nearEdge = e.clientY < 8
      useUIStore.getState().setTopNav(atTop || nearEdge)
    }
    const onScroll = () => {
      if (window.scrollY < 50) useUIStore.getState().setTopNav(true)
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('scroll', onScroll)
    }
  }, [])
}
```

- [ ] **Step 3: 创建 `src/hooks/useCategoryData.ts`**

```typescript
import { useEffect, useState } from 'react'
import type { CategoryDoc, CategoryMeta } from '../types'
import { fetchCategoryDocs } from '../api/http'
import { useUIStore } from '../store/uiStore'

interface CategoryData {
  docs: CategoryDoc[]
  meta: CategoryMeta | null
  loading: boolean
  error: string | null
}

/** 板块进入视口时加载文档列表,meta 取 uiStore 缓存。 */
export function useCategoryData(key: string | null): CategoryData {
  const [state, setState] = useState<CategoryData>({
    docs: [], meta: null, loading: false, error: null,
  })
  const categoriesMeta = useUIStore((s) => s.categoriesMeta)

  useEffect(() => {
    if (!key) {
      setState({ docs: [], meta: null, loading: false, error: null })
      return
    }
    let cancelled = false
    const meta = categoriesMeta.find((c) => c.key === key) || null
    setState({ docs: [], meta, loading: true, error: null })
    fetchCategoryDocs(key, 5)
      .then((docs) => {
        if (!cancelled) setState({ docs, meta, loading: false, error: null })
      })
      .catch((e) => {
        if (!cancelled) setState({ docs: [], meta, loading: false, error: String(e) })
      })
    return () => { cancelled = true }
  }, [key, categoriesMeta])

  return state
}
```

- [ ] **Step 4: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/hooks/
git commit -m "feat: add useScrollSpy/useTopNavTrigger/useCategoryData hooks"
```

---

## Task 7: 前端 — 通用 UI 组件(主题切换/分类选择/链接列表/分割线)

**Files:**
- Create: `frontend/react-app/src/components/ui/ThemeToggle.tsx`
- Create: `frontend/react-app/src/components/ui/CategorySelect.tsx`
- Create: `frontend/react-app/src/components/ui/LinkList.tsx`
- Create: `frontend/react-app/src/components/ui/SectionDivider.tsx`

- [ ] **Step 1: 创建 `src/components/ui/ThemeToggle.tsx`**

```typescript
import { useThemeStore } from '../../store/themeStore'

const LABELS: Record<string, string> = {
  'dark-warm': '深色复古暖',
  'parchment': '浅色羊皮纸',
  'mystic-purple': '神秘紫夜间',
}

export function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme)
  const cycle = useThemeStore((s) => s.cycle)
  return (
    <button
      onClick={cycle}
      title={`当前: ${LABELS[theme]}(点击切换)`}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 12px', width: '100%',
        color: 'var(--text-primary)', fontSize: '0.95rem',
        borderRadius: 4, transition: 'background 0.2s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-elevated)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <span style={{ fontSize: '1.2rem' }}>◐</span>
      <span>{LABELS[theme]}</span>
    </button>
  )
}
```

- [ ] **Step 2: 创建 `src/components/ui/CategorySelect.tsx`**

```typescript
import { useChatStore } from '../../store/chatStore'

const OPTIONS: { value: string | null; label: string }[] = [
  { value: null, label: '全部' },
  { value: '人物', label: '人物' },
  { value: '心相', label: '心相' },
  { value: '剧情', label: '剧情' },
  { value: '世界', label: '世界' },
  { value: '阵营', label: '阵营' },
  { value: '日历', label: '日历' },
]

export function CategorySelect() {
  const category = useChatStore((s) => s.category)
  const setCategory = useChatStore((s) => s.setCategory)
  return (
    <select
      value={category ?? ''}
      onChange={(e) => setCategory(e.target.value || null)}
      style={{
        padding: '6px 12px',
        background: 'var(--bg-elevated)',
        color: 'var(--text-primary)',
        border: '1px solid var(--border-card)',
        borderRadius: 4,
        fontFamily: 'var(--font-body)',
        fontSize: '0.95rem',
        cursor: 'pointer',
      }}
    >
      {OPTIONS.map((o) => (
        <option key={o.label} value={o.value ?? ''}>{o.label}</option>
      ))}
    </select>
  )
}
```

- [ ] **Step 3: 创建 `src/components/ui/LinkList.tsx`**

```typescript
interface LinkItem {
  label: string
  url: string
  icon?: string
}

const DEFAULT_LINKS: LinkItem[] = [
  { label: '重返未来1999 官网', url: 'https://1999buey.com/', icon: '✦' },
]

export function LinkList({ links = DEFAULT_LINKS }: { links?: LinkItem[] }) {
  return (
    <ul style={{ listStyle: 'none', padding: 0 }}>
      {links.map((l) => (
        <li key={l.url}>
          <a
            href={l.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 12px',
              color: 'var(--text-primary)',
              borderRadius: 4,
              transition: 'background 0.2s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-elevated)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            {l.icon && <span style={{ color: 'var(--accent-gold)' }}>{l.icon}</span>}
            <span>{l.label}</span>
          </a>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 4: 创建 `src/components/ui/SectionDivider.tsx`**

```typescript
export function SectionDivider({ label }: { label?: string }) {
  return (
    <div className="divider-ornate" style={{ margin: '24px 0' }}>
      <span className="diamond" />
      {label && (
        <span style={{ fontSize: '0.85rem', letterSpacing: '0.1em' }}>{label}</span>
      )}
      <span className="diamond" />
    </div>
  )
}
```

- [ ] **Step 5: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/components/ui/
git commit -m "feat: add ThemeToggle/CategorySelect/LinkList/SectionDivider UI components"
```

---

## Task 8: 前端 — Sidebar 控制栏与 TopNav 顶端导航

**Files:**
- Create: `frontend/react-app/src/components/Sidebar.tsx`
- Create: `frontend/react-app/src/components/TopNav.tsx`

- [ ] **Step 1: 创建 `src/components/Sidebar.tsx`**

```typescript
import { AnimatePresence, motion } from 'framer-motion'
import { useUIStore } from '../store/uiStore'
import { ThemeToggle } from './ui/ThemeToggle'
import { LinkList } from './ui/LinkList'
import { SectionDivider } from './ui/SectionDivider'

const CATEGORY_LINKS = [
  { key: '人物', label: '人物' },
  { key: '心相', label: '心相' },
  { key: '剧情', label: '剧情' },
  { key: '世界', label: '世界' },
  { key: '阵营', label: '阵营' },
  { key: '日历', label: '日历' },
]

export function Sidebar() {
  const open = useUIStore((s) => s.sidebarOpen)
  const setSidebar = useUIStore((s) => s.setSidebar)

  const jumpToCategory = (key: string) => {
    const el = document.querySelector(`[data-snap-section="data:${key}"]`)
    el?.scrollIntoView({ behavior: 'smooth' })
    setSidebar(false)
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.5 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setSidebar(false)}
            style={{
              position: 'fixed', inset: 0,
              background: 'var(--bg-overlay)',
              zIndex: 99,
            }}
          />
          <motion.aside
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', stiffness: 260, damping: 30 }}
            style={{
              position: 'fixed', top: 0, left: 0, bottom: 0,
              width: '280px',
              background: 'var(--bg-elevated)',
              borderRight: '1px solid var(--border-card)',
              boxShadow: 'var(--shadow-card)',
              padding: 24,
              zIndex: 100,
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ fontFamily: 'var(--font-display)', color: 'var(--accent-gold)', letterSpacing: '0.1em' }}>CONTROL</h3>
              <button onClick={() => setSidebar(false)} style={{ fontSize: '1.4rem', color: 'var(--text-secondary)' }}>×</button>
            </div>

            <SectionDivider label="主题" />
            <ThemeToggle />

            <SectionDivider label="引用网站" />
            <LinkList />

            <SectionDivider label="板块速达" />
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {CATEGORY_LINKS.map((c) => (
                <li key={c.key}>
                  <button
                    onClick={() => jumpToCategory(c.key)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '8px 12px', width: '100%',
                      color: 'var(--text-primary)',
                      borderRadius: 4, textAlign: 'left',
                      transition: 'background 0.2s',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-base)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <span style={{ color: 'var(--accent-gold)' }}>◆</span>
                    <span>{c.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 2: 创建 `src/components/TopNav.tsx`**

```typescript
import { AnimatePresence, motion } from 'framer-motion'
import { useUIStore } from '../store/uiStore'

const NAV_ITEMS: { key: string; label: string; target: string }[] = [
  { key: 'home', label: '首页', target: 'home' },
  { key: 'data', label: '资料', target: 'data' },
  { key: 'chat', label: '问答', target: 'chat' },
]

export function TopNav() {
  const visible = useUIStore((s) => s.topNavVisible)
  const currentSection = useUIStore((s) => s.currentSection)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)

  const jumpTo = (target: string) => {
    const el = document.querySelector(`[data-snap-section="${target}"]`)
    el?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.nav
          initial={{ y: -60, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -60, opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          style={{
            position: 'fixed', top: 0, left: 0, right: 0,
            height: 56,
            background: 'var(--bg-overlay)',
            backdropFilter: 'blur(12px)',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex', alignItems: 'center', gap: 24,
            padding: '0 24px',
            zIndex: 90,
          }}
        >
          <button
            onClick={toggleSidebar}
            style={{ fontSize: '1.2rem', color: 'var(--accent-gold)' }}
            title="打开控制栏"
          >
            ☰
          </button>
          <div style={{ flex: 1 }} />
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => jumpTo(item.target)}
              style={{
                padding: '6px 16px',
                color: currentSection === item.key ? 'var(--accent-gold)' : 'var(--text-secondary)',
                borderBottom: currentSection === item.key ? '2px solid var(--accent-gold)' : '2px solid transparent',
                transition: 'color 0.2s, border-color 0.2s',
                fontFamily: 'var(--font-body)',
                fontSize: '0.95rem',
              }}
            >
              {item.label}
            </button>
          ))}
        </motion.nav>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 3: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/components/Sidebar.tsx frontend/react-app/src/components/TopNav.tsx
git commit -m "feat: add Sidebar control panel and TopNav with framer-motion animations"
```

---

## Task 9: 前端 — 首页 HomeSection(视频背景 + 标题动画 + 下载按钮)

**Files:**
- Create: `frontend/react-app/src/components/sections/HomeSection.tsx`

- [ ] **Step 1: 创建 `src/components/sections/HomeSection.tsx`**

```typescript
import { motion } from 'framer-motion'
import { useState } from 'react'

const titleVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (delay: number) => ({
    opacity: 1, y: 0,
    transition: { duration: 0.8, ease: 'easeOut' as const, delay },
  }),
}

export function HomeSection() {
  const [showToast, setShowToast] = useState(false)
  // 视频占位:无 pv.mp4 时用 CSS 渐变兜底
  const videoExists = false  // 实际可检测 public/videos/pv.mp4 是否存在,这里先固定 false

  return (
    <section
      data-snap-section="home"
      className="snap-section"
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      {/* 背景层:视频或 CSS 渐变兜底 */}
      {videoExists ? (
        <>
          <video
            className="video-bg"
            autoPlay muted loop
            style={{
              position: 'absolute', inset: 0, objectFit: 'cover',
              WebkitMask: 'radial-gradient(ellipse 50% 50% at center, #000 30%, transparent 75%)',
              mask: 'radial-gradient(ellipse 50% 50% at center, #000 30%, transparent 75%)',
            }}
          >
            <source src="/videos/pv.mp4" type="video/mp4" />
          </video>
          <video
            autoPlay muted loop
            style={{
              position: 'absolute', inset: 0, objectFit: 'cover',
              filter: 'blur(24px) brightness(0.6)',
              transform: 'scale(1.1)',
              zIndex: -1,
            }}
          >
            <source src="/videos/pv.mp4" type="video/mp4" />
          </video>
        </>
      ) : (
        <div
          style={{
            position: 'absolute', inset: 0,
            background: 'radial-gradient(ellipse at center, var(--accent-purple) 0%, var(--bg-base) 70%)',
            opacity: 0.4,
          }}
        />
      )}

      {/* 内容层 */}
      <div
        style={{
          position: 'relative', zIndex: 10,
          height: '100%', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 16,
        }}
      >
        <motion.h1
          custom={0}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          style={{
            fontFamily: 'var(--font-body)',
            fontWeight: 700,
            fontSize: 'clamp(2.5rem, 6vw, 4.5rem)',
            color: 'var(--text-primary)',
            textShadow: '0 4px 24px rgba(0,0,0,0.6)',
          }}
        >
          重返未来:1999
        </motion.h1>

        <motion.h2
          custom={0.3}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: 'clamp(1.5rem, 4vw, 3rem)',
            color: 'var(--accent-gold)',
            letterSpacing: '0.1em',
          }}
        >
          REVERSE: 1999
        </motion.h2>

        <motion.p
          custom={0.6}
          variants={titleVariants}
          initial="hidden"
          animate="visible"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 500,
            fontSize: '1.25rem',
            color: 'var(--accent-gold)',
            opacity: 0.9,
          }}
        >
          3.8 版本 · 世纪末尺度
        </motion.p>

        {/* 下载按钮 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.9 }}
          style={{ marginTop: 48 }}
        >
          <button
            onClick={() => {
              setShowToast(true)
              setTimeout(() => setShowToast(false), 2500)
            }}
            style={{
              padding: '12px 48px',
              border: '1px solid var(--accent-gold)',
              borderRadius: 4,
              background: 'transparent',
              color: 'var(--accent-gold)',
              fontFamily: 'var(--font-body)',
              fontSize: '1.1rem',
              letterSpacing: '0.1em',
              cursor: 'pointer',
              transition: 'all 0.3s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '0 0 20px var(--border-glow)'
              e.currentTarget.style.background = 'rgba(212, 175, 55, 0.1)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = 'none'
              e.currentTarget.style.background = 'transparent'
            }}
          >
            立即下载
          </button>
          {showToast && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                marginTop: 12, padding: '8px 16px',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-card)',
                borderRadius: 4,
                color: 'var(--text-secondary)',
                fontSize: '0.9rem',
              }}
            >
              下载链接待补
            </motion.div>
          )}
        </motion.div>
      </div>

      {/* 滚轮提示 */}
      <motion.div
        animate={{ y: [0, 8, 0] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        style={{
          position: 'absolute', bottom: 32, left: '50%',
          transform: 'translateX(-50%)',
          color: 'var(--text-muted)',
          fontSize: '1.5rem',
        }}
      >
        ↓
      </motion.div>
    </section>
  )
}
```

- [ ] **Step 2: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/components/sections/HomeSection.tsx
git commit -m "feat: add HomeSection with video background placeholder and title animations"
```

---

## Task 10: 前端 — 资料页 DataSection 与 CategoryPanel(进场动画 + 流式逐字)

**Files:**
- Create: `frontend/react-app/src/components/sections/DataSection.tsx`
- Create: `frontend/react-app/src/components/sections/CategoryPanel.tsx`
- Create: `frontend/react-app/src/components/StreamingDescription.tsx`

- [ ] **Step 1: 创建 `src/components/StreamingDescription.tsx`(流式逐字 reveal)**

```typescript
import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

/** 文本逐字 reveal,每字 18ms,每字 opacity 0→1 + y 8→0。 */
export function StreamingDescription({ text, start }: { text: string; start: boolean }) {
  const [visibleCount, setVisibleCount] = useState(0)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!start || !text) return
    setVisibleCount(0)
    let i = 0
    timerRef.current = window.setInterval(() => {
      i++
      setVisibleCount(i)
      if (i >= text.length) {
        if (timerRef.current) window.clearInterval(timerRef.current)
      }
    }, 18)
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [start, text])

  const chars = Array.from(text.slice(0, visibleCount))
  return (
    <p
      style={{
        fontFamily: 'var(--font-body)',
        fontSize: '1.125rem',
        lineHeight: 1.9,
        color: 'var(--text-secondary)',
      }}
    >
      {chars.map((ch, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {ch}
        </motion.span>
      ))}
    </p>
  )
}
```

- [ ] **Step 2: 创建 `src/components/sections/CategoryPanel.tsx`**

```typescript
import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import type { CategoryMeta } from '../../types'
import { useCategoryData } from '../../hooks/useCategoryData'
import { StreamingDescription } from '../StreamingDescription'

const panelVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.3 } },
}
const titleVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.8, ease: 'easeOut' as const } },
}
const imageVariants = {
  hidden: { opacity: 0, scale: 1.1, y: 40, filter: 'blur(8px)' },
  visible: {
    opacity: 1, scale: 1, y: 0, filter: 'blur(0px)',
    transition: { duration: 1.2, ease: 'easeOut' as const },
  },
}

export function CategoryPanel({ meta }: { meta: CategoryMeta }) {
  const { docs, loading } = useCategoryData(meta.key)
  const [inView, setInView] = useState(false)
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && entry.intersectionRatio > 0.5) setInView(true)
      },
      { threshold: 0.5 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const description = docs.map((d) => d.snippet).join(' ')
  const coverUrl = `/covers/${meta.key}.png`

  return (
    <section
      ref={ref}
      data-snap-section={`data:${meta.key}`}
      className="snap-section"
      style={{ display: 'flex', alignItems: 'center', padding: '0 8%' }}
    >
      {/* 板块标识竖条 */}
      <div className="category-bar" style={{ position: 'absolute', left: 0, top: '20%', height: '60%' }} />

      <motion.div
        variants={panelVariants}
        initial="hidden"
        animate={inView ? 'visible' : 'hidden'}
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 48,
          width: '100%',
          maxWidth: 1200,
          margin: '0 auto',
        }}
      >
        {/* 左:文字 */}
        <div>
          <motion.h2
            variants={titleVariants}
            style={{
              fontFamily: 'var(--font-body)',
              fontWeight: 700,
              fontSize: 'clamp(2rem, 5vw, 3.5rem)',
              color: 'var(--accent-gold)',
              marginBottom: 8,
            }}
          >
            {meta.title}
          </motion.h2>
          <motion.p
            variants={titleVariants}
            style={{
              fontFamily: 'var(--font-display)',
              color: 'var(--text-muted)',
              letterSpacing: '0.1em',
              marginBottom: 24,
            }}
          >
            {meta.subtitle} · {meta.doc_count} 篇
          </motion.p>
          <StreamingDescription text={description} start={inView} />
          {loading && <p style={{ color: 'var(--text-muted)', marginTop: 16 }}>加载中...</p>}
        </div>

        {/* 右:封面图 */}
        <motion.div variants={imageVariants} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img
            src={coverUrl}
            alt={meta.title}
            loading="lazy"
            style={{
              maxWidth: '100%',
              maxHeight: '60vh',
              objectFit: 'cover',
              borderRadius: 4,
              boxShadow: 'var(--shadow-card)',
              border: '1px solid var(--border-card)',
            }}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        </motion.div>
      </motion.div>
    </section>
  )
}
```

- [ ] **Step 3: 创建 `src/components/sections/DataSection.tsx`**

```typescript
import { useUIStore } from '../../store/uiStore'
import { CategoryPanel } from './CategoryPanel'

export function DataSection() {
  const categoriesMeta = useUIStore((s) => s.categoriesMeta)
  const currentCategory = useUIStore((s) => s.currentCategory)

  return (
    <section
      data-snap-section="data"
      className="snap-section"
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      {/* 内嵌 6 板块的滚动容器 */}
      <div
        style={{
          height: '100%',
          overflowY: 'scroll',
          scrollSnapType: 'y mandatory',
          scrollBehavior: 'smooth',
        }}
      >
        {categoriesMeta.map((c) => (
          <CategoryPanel key={c.key} meta={c} />
        ))}
      </div>

      {/* 左侧固定板块导航 */}
      <nav
        style={{
          position: 'absolute', left: 24, top: '50%',
          transform: 'translateY(-50%)',
          zIndex: 5,
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        {categoriesMeta.map((c) => (
          <button
            key={c.key}
            onClick={() => {
              const el = document.querySelector(`[data-snap-section="data:${c.key}"]`)
              el?.scrollIntoView({ behavior: 'smooth' })
            }}
            style={{
              padding: '6px 12px',
              color: currentCategory === c.key ? 'var(--accent-gold)' : 'var(--text-muted)',
              borderLeft: currentCategory === c.key ? '2px solid var(--accent-gold)' : '2px solid transparent',
              fontFamily: 'var(--font-body)',
              fontSize: '0.9rem',
              transition: 'color 0.2s, border-color 0.2s',
              textAlign: 'left',
            }}
          >
            {c.title}
          </button>
        ))}
      </nav>
    </section>
  )
}
```

- [ ] **Step 4: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/components/sections/DataSection.tsx frontend/react-app/src/components/sections/CategoryPanel.tsx frontend/react-app/src/components/StreamingDescription.tsx
git commit -m "feat: add DataSection with 6 CategoryPanels and streaming description animation"
```

---

## Task 11: 前端 — 问答页 ChatSection(流式字符动画 + 消息弹出)

**Files:**
- Create: `frontend/react-app/src/components/chat/StreamingText.tsx`
- Create: `frontend/react-app/src/components/chat/MessageBubble.tsx`
- Create: `frontend/react-app/src/components/chat/ChatInput.tsx`
- Create: `frontend/react-app/src/components/sections/ChatSection.tsx`

- [ ] **Step 1: 创建 `src/components/chat/StreamingText.tsx`(LLM 流式逐字)**

```typescript
import { motion } from 'framer-motion'

/** LLM 回答逐字动画,每字 opacity 0→1 + scale 0.5→1,200ms。 */
export function StreamingText({ text, streaming }: { text: string; streaming: boolean }) {
  const chars = Array.from(text)
  return (
    <span>
      {chars.map((ch, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2 }}
          style={{ display: 'inline-block' }}
        >
          {ch}
        </motion.span>
      ))}
      {streaming && (
        <motion.span
          animate={{ opacity: [1, 0, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
          style={{ display: 'inline-block', marginLeft: 2, color: 'var(--accent-gold)' }}
        >
          ▌
        </motion.span>
      )}
    </span>
  )
}
```

- [ ] **Step 2: 创建 `src/components/chat/MessageBubble.tsx`**

```typescript
import { motion } from 'framer-motion'
import type { Message } from '../../types'
import { StreamingText } from './StreamingText'

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  return (
    <motion.div
      layoutId={isUser ? 'last-input' : undefined}
      initial={isUser ? { scale: 1.3, opacity: 0 } : { opacity: 0 }}
      animate={isUser ? { scale: 1, opacity: 1 } : { opacity: 1 }}
      transition={isUser ? { type: 'spring', stiffness: 300, damping: 20 } : { duration: 0.3 }}
      style={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '70%',
        padding: '12px 16px',
        background: isUser ? 'var(--accent-purple)' : 'var(--bg-elevated)',
        color: isUser ? '#fff' : 'var(--text-primary)',
        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        border: isUser ? 'none' : '1px solid var(--border-card)',
        fontFamily: 'var(--font-body)',
        fontSize: '1rem',
        lineHeight: 1.6,
        marginBottom: 12,
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {isUser ? (
        message.content
      ) : (
        <StreamingText text={message.content} streaming={!!message.streaming} />
      )}
      {!isUser && message.sources && message.sources.length > 0 && !message.streaming && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          style={{
            marginTop: 8, paddingTop: 8,
            borderTop: '1px solid var(--border-subtle)',
            fontSize: '0.875rem',
            color: 'var(--text-secondary)',
          }}
        >
          <span style={{ color: 'var(--accent-gold)' }}>来源:</span>{' '}
          {message.sources.map((s, i) => (
            <span key={i}>
              {s.name}
              {i < message.sources!.length - 1 ? ' · ' : ''}
            </span>
          ))}
        </motion.div>
      )}
    </motion.div>
  )
}
```

- [ ] **Step 3: 创建 `src/components/chat/ChatInput.tsx`**

```typescript
import { motion } from 'framer-motion'
import { useState } from 'react'
import { useChatStore } from '../../store/chatStore'

export function ChatInput() {
  const [value, setValue] = useState('')
  const send = useChatStore((s) => s.send)
  const sending = useChatStore((s) => s.sending)
  const messages = useChatStore((s) => s.messages)
  const [lastError, setLastError] = useState<string | null>(null)
  const [lastQuestion, setLastQuestion] = useState('')

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const v = value.trim()
    if (!v || sending) return
    setLastQuestion(v)
    setLastError(null)
    setValue('')
    send(v).then(() => {
      const last = useChatStore.getState().messages.slice(-1)[0]
      if (last && last.content.startsWith('请求失败:') || last?.content.startsWith('错误:')) {
        setLastError(last.content)
      }
    })
  }

  const onRetry = () => {
    if (!lastQuestion || sending) return
    setLastError(null)
    // 移除最后两条失败消息后重发
    useChatStore.setState((s) => ({ messages: s.messages.slice(0, -2) }))
    send(lastQuestion)
  }

  return (
    <div>
      {lastError && (
        <div style={{ padding: '8px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--accent-rust)', color: '#fff' }}>
          <span style={{ fontSize: '0.85rem' }}>{lastError}</span>
          <button
            onClick={onRetry}
            disabled={sending}
            style={{
              padding: '4px 12px',
              background: 'rgba(255,255,255,0.2)',
              color: '#fff',
              border: '1px solid rgba(255,255,255,0.4)',
              borderRadius: 3,
              cursor: sending ? 'not-allowed' : 'pointer',
            }}
          >
            重试
          </button>
        </div>
      )}
      <form
        onSubmit={onSubmit}
        style={{
          display: 'flex', gap: 8, padding: 16,
          background: 'var(--bg-overlay)',
          backdropFilter: 'blur(12px)',
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <motion.span
          layoutId="last-input"
          style={{ display: 'none' }}
        />
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="输入问题..."
          style={{
            flex: 1, padding: '10px 14px',
            background: 'var(--bg-elevated)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-card)',
            borderRadius: 4,
            fontFamily: 'var(--font-body)',
            fontSize: '1rem',
          }}
        />
        <button
          type="submit"
          disabled={sending || !value.trim()}
          style={{
            padding: '10px 24px',
            background: 'var(--accent-gold)',
            color: 'var(--bg-base)',
            border: 'none', borderRadius: 4,
            fontFamily: 'var(--font-body)', fontWeight: 500,
            cursor: sending ? 'not-allowed' : 'pointer',
            opacity: sending || !value.trim() ? 0.5 : 1,
          }}
        >
          发送
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: 创建 `src/components/sections/ChatSection.tsx`**

```typescript
import { useEffect, useRef } from 'react'
import { useChatStore } from '../../store/chatStore'
import { CategorySelect } from '../ui/CategorySelect'
import { MessageBubble } from '../chat/MessageBubble'
import { ChatInput } from '../chat/ChatInput'

export function ChatSection() {
  const messages = useChatStore((s) => s.messages)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  return (
    <section
      data-snap-section="chat"
      className="snap-section"
      style={{
        display: 'flex', flexDirection: 'column',
        background: 'var(--bg-base)',
      }}
    >
      {/* 顶部分类选择 */}
      <div
        style={{
          padding: '12px 24px',
          display: 'flex', alignItems: 'center', gap: 12,
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>检索范围:</span>
        <CategorySelect />
      </div>

      {/* 消息区 */}
      <div
        ref={scrollRef}
        style={{
          flex: 1, overflowY: 'auto',
          padding: 24,
          display: 'flex', flexDirection: 'column',
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              margin: 'auto',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontFamily: 'var(--font-body)',
            }}
          >
            <p style={{ fontSize: '1.5rem', marginBottom: 8, color: 'var(--accent-gold)' }}>
              神秘学问答
            </p>
            <p style={{ fontSize: '0.95rem' }}>
              问问关于人物、心相、剧情、世界、阵营或日历的任何问题
            </p>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>

      {/* 输入区 */}
      <ChatInput />
    </section>
  )
}
```

- [ ] **Step 5: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/components/chat/ frontend/react-app/src/components/sections/ChatSection.tsx
git commit -m "feat: add ChatSection with streaming text, message bubble animation and chat input"
```

---

## Task 12: 前端 — App 根组件组装与启动加载

**Files:**
- Modify: `frontend/react-app/src/App.tsx`

- [ ] **Step 1: 完整重写 `src/App.tsx`**

```typescript
import { useEffect } from 'react'
import { useUIStore } from './store/uiStore'
import { useScrollSpy } from './hooks/useScrollSpy'
import { useTopNavTrigger } from './hooks/useTopNavTrigger'
import { fetchCategories } from './api/http'
import { Sidebar } from './components/Sidebar'
import { TopNav } from './components/TopNav'
import { HomeSection } from './components/sections/HomeSection'
import { DataSection } from './components/sections/DataSection'
import { ChatSection } from './components/sections/ChatSection'

export default function App() {
  const setCategoriesMeta = useUIStore((s) => s.setCategoriesMeta)
  useScrollSpy()
  useTopNavTrigger()

  useEffect(() => {
    fetchCategories()
      .then(setCategoriesMeta)
      .catch((e) => console.error('[App] 加载板块元数据失败:', e))
  }, [setCategoriesMeta])

  return (
    <>
      <Sidebar />
      <TopNav />
      <main className="snap-container">
        <HomeSection />
        <DataSection />
        <ChatSection />
      </main>
    </>
  )
}
```

- [ ] **Step 2: 启动 dev server 验证**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```
打开 http://localhost:5173,验证:
- 首页显示标题 + 渐变背景 + 下载按钮(toast)
- 鼠标贴顶端 → TopNav 滑入
- 点左上角 ☰ → Sidebar 滑入(需先让 TopNav 显示)
- 滚动到资料页 → 6 板块逐个显示(需后端运行)
- 滚动到问答页 → 输入框可用

后端启动(另一个终端):
```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
D:\anaconda32024\envs\LangChain\python.exe -m uvicorn backend.main:app --port 8000
```

- [ ] **Step 3: 运行全部前端测试**

Run: `cd frontend\react-app && npx vitest run`
Expected: 全部 passed

- [ ] **Step 4: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add frontend/react-app/src/App.tsx
git commit -m "feat: assemble App root with scroll-snap, sidebar, topnav and 3 sections"
```

---

## Task 13: 封面图片生成脚本

**Files:**
- Create: `scripts/generate_covers.py`

- [ ] **Step 1: 创建 `scripts/generate_covers.py`**

```python
"""一次性生成 6 板块封面图片到 frontend/react-app/public/covers/。

手动运行:
    conda run -n langchain python scripts/generate_covers.py

依赖:requests(已在 langchain 环境中)
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

import requests

from backend.categories_meta import CATEGORIES_META

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "frontend" / "react-app" / "public" / "covers"
API_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image"


def generate_one(prompt: str, out_path: Path) -> None:
    params = {
        "prompt": prompt,
        "image_size": "landscape_16_9",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    print(f"[cover] 生成: {out_path.name}  prompt={prompt[:30]}...")
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        print(f"[cover] 错误 {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        return
    out_path.write_bytes(resp.content)
    print(f"[cover] 完成: {out_path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for meta in CATEGORIES_META:
        out = OUT_DIR / f"{meta['key']}.png"
        if out.exists():
            print(f"[cover] 已存在,跳过: {out.name}")
            continue
        generate_one(meta["cover_prompt"], out)
    print("[cover] 全部完成")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行生成封面**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
D:\anaconda32024\envs\LangChain\python.exe scripts\generate_covers.py
```
Expected: 6 张 png 生成到 `frontend/react-app/public/covers/`

- [ ] **Step 3: 提交脚本与封面**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add scripts/generate_covers.py frontend/react-app/public/covers/
git commit -m "feat: add cover image generation script and 6 generated covers"
```

---

## Task 14: 启动脚本集成与 README 更新

**Files:**
- Modify: `start.ps1`
- Modify: `start.bat`
- Modify: `README.md`

- [ ] **Step 1: 修改 `start.ps1` 增加 Vite 启动段**

在 Gradio 启动段之后、`while ($true)` 循环之前插入:

```powershell
# 检测并启动 React Vite
if (-not (Test-Path "frontend\react-app\node_modules")) {
    Write-Host "[step] 首次启动, 安装 React 前端依赖..." -ForegroundColor Yellow
    Push-Location frontend\react-app
    & npm install
    Pop-Location
}
Write-Host "[step] ${delay}s 后启动 React Vite :5173 ..." -ForegroundColor Yellow
Start-Sleep -Seconds $delay
$jobs += Start-Process -PassThru -WindowStyle Minimized -FilePath "npm.cmd" -ArgumentList "--prefix","frontend\react-app","run","dev","--","--host","127.0.0.1","--port","5173","--strictPort"
```

并在打印访问地址段增加:
```powershell
Write-Host "   React+Vite : http://localhost:5173"
```

- [ ] **Step 2: 修改 `start.bat` 增加对应段**

在 Gradio 启动后增加:
```batch
echo [step] 启动 React Vite :5173 ...
timeout /t 3 /nobreak >nul
start "React Vite" /min cmd /c "cd frontend\react-app && npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort"
```

并在打印地址段增加:
```batch
echo    React+Vite : http://localhost:5173
```

- [ ] **Step 3: 修改 `README.md`**

在三前端地址表后增加一行:

```markdown
| React+Vite | http://localhost:5173 |
```

在"环境准备"第 1 条 conda 环境后增加:

```markdown
5. **Node.js 18+ / npm**(React 前端用):
   ```powershell
   node --version   # 需 18+
   npm --version
   ```
   首次启动脚本会自动 `npm install`。
```

在"手动分步运行"末尾增加:

```powershell
cd frontend\react-app
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort        # React 前端 :5173
```

- [ ] **Step 4: 提交**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
git add start.ps1 start.bat README.md
git commit -m "feat: integrate React Vite into startup scripts and README"
```

---

## Task 15: 端到端验证

**Files:** none

- [ ] **Step 1: 启动后端**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
D:\anaconda32024\envs\LangChain\python.exe -m uvicorn backend.main:app --port 8000
```

- [ ] **Step 2: 启动 React 前端(另一终端)**

```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

- [ ] **Step 3: 验证 4 个 URL 可访问**

打开浏览器:
- http://localhost:5173 → React 首页显示(标题动画 + 渐变背景 + 下载按钮)
- http://localhost:8000/health → `{"status":"ok",...}`
- http://localhost:8000/categories → 6 类 JSON
- http://localhost:8000/category/人物/docs?limit=5 → 文档列表 JSON

- [ ] **Step 4: 验证首页交互**

- 标题渐变浮现(t=0/0.3s/0.6s)
- 点"立即下载" → toast"下载链接待补"
- 鼠标贴顶端 → TopNav 滑入
- 点 TopNav 左上角 ☰ → Sidebar 滑入
- Sidebar 主题切换 ◐ → 三套循环,刷新后保留
- Sidebar "板块速达" → 点击跳到对应板块

- [ ] **Step 5: 验证资料页**

- 滚动到资料页 → 左侧板块导航显示
- 6 板块逐个进场:标题(t=0)、描述流式逐字(t=300ms, 18ms/字)、图片渐变浮出(t=500ms)
- 左侧导航点击 → 跳转对应板块
- 第 6 板块(日历)再下滑 → 进入问答页

- [ ] **Step 6: 验证问答页**

- 顶部 category 下拉默认"全部"
- 输入"6是谁" → 发送 → 用户消息弹出动画(scale 1.3→1)
- LLM 流式逐字出现(每字 scale 0.5→1,光标闪烁)
- 回答结束 → 来源条淡入
- 切换 category 为"人物" → 重新提问 → sources 全为人物

- [ ] **Step 7: 验证 api_key 降级**

确认 `.env` 无 `DEEPSEEK_API_KEY`(或为空),提问 → 流式逐字出现"请在 .env 中配置 DEEPSEEK_API_KEY 后再提问。"

- [ ] **Step 8: 运行全部后端测试**

Run: `D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/ -v`
Expected: 全部 passed(原 12 + test_categories 2 + test_sse 3 = 17)

- [ ] **Step 9: 运行全部前端测试**

Run: `cd frontend\react-app && npx vitest run`
Expected: 全部 passed

- [ ] **Step 10: 验证 start.ps1 一键启动**

停止所有服务,运行:
```powershell
cd d:\PycharmProjects\nlp\LangChain\1999Search
.\start.ps1
```
Expected: 4 端口(8000/8501/7860/5173)均启动并打印访问地址。Ctrl+C 退出后所有子进程终止。

- [ ] **Step 11: 最终 git 状态确认**

```powershell
git log --oneline -20
git status --short
```
Expected: 15+ commits,工作树干净(1999Search 范围内)。

---

## 验收标准(来自 spec §8)

1. ✅ `start.ps1` 启动后 4 端口可访问 — Task 15 Step 10
2. ✅ 首页视频占位背景显示,标题渐变浮现 — Task 15 Step 4
3. ✅ 鼠标贴顶端 → TopNav 滑入;移开 → 滑出 — Task 15 Step 4
4. ✅ Sidebar 覆盖滑入,z-index 高于 TopNav — Task 15 Step 4
5. ✅ 主题切换循环 3 套,localStorage 持久化 — Task 15 Step 4 + themeStore.test
6. ✅ 滚动 snap 流畅 — Task 15 Step 5
7. ✅ 6 板块进场动画时序正确 — Task 15 Step 5
8. ✅ 第 6 板块再下滑 → 问答页 — Task 15 Step 5
9. ✅ 用户消息弹出 + LLM 流式逐字 — Task 15 Step 6
10. ✅ category 过滤生效 — Task 15 Step 6
11. ✅ 流式中断无残留 — chatStore.abort 测试
12. ✅ api_key 空降级提示 — Task 15 Step 7
13. ✅ 三套主题不破坏布局 — Task 15 Step 4
14. ✅ 后端测试全过 — Task 15 Step 8
15. ✅ 前端测试全过 — Task 15 Step 9
