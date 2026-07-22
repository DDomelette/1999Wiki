# Huiji Wiki Module Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 恢复灰机 Wiki P0 应用层，让当前已有 Docker MySQL、MinIO 和 `data/processed/huiji/dev` 通过 FastAPI `/api/wiki/*` 和 React `/wiki` 形成只读、可验收的真实数据浏览链路。

**Architecture:** 本计划只恢复应用层与只读验收层，不重跑 Wiki builder，不覆盖 MySQL，不上传或删除 MinIO 对象，不重建 Milvus。后端读取当前 `reverse1999_wiki` MySQL 表并返回安全 camelCase API；前端重建 `/wiki` 四区工作区、模板、关键词链接和入口；验证脚本只请求 API 与抽样 URL。

**Tech Stack:** Python 3, pytest, FastAPI, Pydantic, PyMySQL, JSON/JSONL, React 18, TypeScript, Vite, Vitest, Testing Library, Framer Motion.

## Global Constraints

- P0 修复以当前 Docker MySQL、MinIO 和 `data/processed/huiji/dev` 为真实数据源，不要求 raw crawler 资源完整。
- P0 代码和验收只能只读检查 `data/processed/huiji/dev`，不得改写 `parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl` 或索引文件。
- P0 不执行会替换 Wiki MySQL 表的构建动作；如需读取 MySQL，只通过 API 或 repository 查询。
- P0 不清空、不覆盖、不迁移 MinIO bucket 或 `reverse1999/` prefix。
- P0 不创建、不删除、不重建 Milvus collection。
- API payload 中不得出现 `D:\`、`C:\`、`local_relpath` 等本地路径泄露。
- Wiki 不能依赖 RAG 页面完成入库、检索、输出格式调整后才能工作。
- 动效不能阻塞 P0 数据面恢复。
- 本计划不使用 git 提交步骤；用户已要求本地完成优先。

---

## 1. 目标范围

本轮主线只覆盖 specs 的 P0：

- `DATA-P0-01` 至 `DATA-P0-06`
- `MEDIA-P0-01` 至 `MEDIA-P0-07`
- `API-P0-01` 至 `API-P0-08`
- `FRONTEND-P0-01` 至 `FRONTEND-P0-12`
- `TEMPLATE-P0-01` 至 `TEMPLATE-P0-09`
- `LINK-P0-01` 至 `LINK-P0-05`
- `RAGLINK-P0-01` 至 `RAGLINK-P0-04`
- `ANIMATION-P0-01` 至 `ANIMATION-P0-03`
- `VERIFY-P0-01` 至 `VERIFY-P0-07`

本轮不做：

- 不运行 `scripts/build_huiji_wiki.py`。
- 不恢复或执行 `src/huiji_wiki/builder.py`、`src/huiji_wiki/media_upload.py` 的构建写入链路。
- 不重爬或校验完整 raw crawler 资源。
- 不清空或覆盖 MySQL、MinIO、Milvus、`data/processed/huiji/dev`。
- 不接入 Live2D 真播放器。
- 不接入具体 ReactBits 动效组件。

## 2. 文件结构

### Backend / API / Verification

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/models.py`  
  保持 Wiki DTO camelCase 转换，补足媒体、关系、链接字段的安全序列化。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`  
  只读读取当前 MySQL 表，保持 API 所需字段完整，禁止在 P0 初始化时执行写 schema 或 replace 操作。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`  
  明确 API response 字段结构，尤其是 `mediaLinks[].url/objectKey/assetType/mime/sha1/width/height`。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`  
  保持 `/api/wiki/*` 路由只读，修正 route resolve 失败 fallback。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`  
  API contract 和安全字段测试。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`  
  repository 只读行为和字段转换测试。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/verify_huiji_wiki_e2e.py`  
  只读真实 API 验收脚本。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_e2e_script.py`  
  验收脚本 payload 校验单测。

### Frontend API / Route / Entry Points

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/wiki.ts`  
  补齐 `WikiMediaLink`、`WikiRelation`、`WikiLinkSpan`、`WikiSource` 等类型。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.ts`  
  保持 categories、pages、detail、resolve、search 客户端。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.tsx`  
  复测 `/wiki` 早返回，不进入 snap container。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.tsx`  
  复测顶部 Wiki 入口。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/Sidebar.tsx`  
  复测侧栏 Wiki 入口。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.tsx`  
  复测日历页 `进入WIKI` 入口。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.test.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.wiki.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.wiki.test.tsx`

### Frontend Wiki Workspace

- Replace: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.tsx`  
  从临时列表页改为 Wiki route 容器。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageIndex.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiReader.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageInfo.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/wikiLayout.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/PsychubePage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/StoryPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/GenericWikiPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageIndex.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageInfo.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/WikiTemplates.test.tsx`

## 3. 强制验收门槛

| Specs 编号 | 验收方式 | 失败表现 |
|---|---|---|
| `DATA-P0-01` 至 `DATA-P0-06` | 审查 plan 执行记录和命令历史；只出现 API、前端、只读验证脚本命令，不出现 build、delete、drop、reset、Milvus rebuild。 | 当前 MySQL、MinIO、Milvus 或 processed artifacts 被覆盖或重建。 |
| `MEDIA-P0-01` 至 `MEDIA-P0-07` | `tests/test_huiji_wiki_api.py`、`scripts/verify_huiji_wiki_e2e.py --page-id <真实 page_id>`、浏览器真实图片验收。 | API payload 有本地路径、图片只显示占位、URL 不是 HTTP。 |
| `API-P0-01` 至 `API-P0-08` | `python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q`。 | API 字段缺失、字段命名不匹配、resolve 失败抛错。 |
| `FRONTEND-P0-01` 至 `FRONTEND-P0-12` | Wiki 组件测试、`npm run build`、浏览器打开 `/wiki`。 | `/wiki` 进入 snap container，四区缺失，布局比例错误，错误态崩溃。 |
| `TEMPLATE-P0-01` 至 `TEMPLATE-P0-09` | `WikiTemplates.test.tsx`、`CharacterMediaStage.test.tsx`、真实角色页浏览器验收。 | 角色媒体太小、Live2D 入口缺失、fallback 改变尺寸、raw JSON 直接暴露。 |
| `LINK-P0-01` 至 `LINK-P0-05` | `KeywordText.test.tsx`。 | 同段多关键词丢失、重复关键词只渲染一次、空 route 生成空链接。 |
| `RAGLINK-P0-01` 至 `RAGLINK-P0-04` | API route resolve 测试和代码审查；确认未改 RAG 检索链路。 | Wiki 修复依赖 RAG 入库或修改 RAG 检索代码。 |
| `ANIMATION-P0-01` 至 `ANIMATION-P0-03` | 代码审查：组件保留区域边界和 metadata 字段，不绑定 ReactBits 组件名。 | 业务组件写死第三方动效组件，或动效阻断数据面。 |
| `VERIFY-P0-01` 至 `VERIFY-P0-07` | 只读 E2E 脚本、手动真实数据验收记录。 | 只靠 mock 单测宣称完成，或验收脚本写数据。 |

## 4. 执行步骤

### Task 1: 锁定后端只读 API 契约

**对应 specs:** `DATA-P0-01` 至 `DATA-P0-06`、`MEDIA-P0-01` 至 `MEDIA-P0-05`、`API-P0-01` 至 `API-P0-08`、`RAGLINK-P0-01` 至 `RAGLINK-P0-04`

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/models.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`

**Interfaces:**
- Consumes: existing `WikiPage`, `WikiCategory`, `WikiMediaLink`, `WikiRelation`, `WikiLinkSpan`, `MySQLWikiRepository`.
- Produces:
  - `GET /api/wiki/categories -> { categories: WikiCategoryItem[] }`
  - `GET /api/wiki/pages -> { items: WikiPageListItem[], nextCursor: string | null }`
  - `GET /api/wiki/pages/{page_id} -> WikiPageDetailResponse`
  - `GET /api/wiki/routes/resolve -> { route: string | null, query: string }`
  - `GET /api/wiki/search -> WikiPageListResponse`

- [ ] **Step 1: 写 API contract 失败测试**

Create `tests/test_huiji_wiki_api.py` with tests that monkeypatch `backend.wiki.get_wiki_repository` to return a fake repository:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import wiki
from src.huiji_wiki.models import WikiCategory, WikiLinkSpan, WikiMediaLink, WikiPage, WikiRelation


class FakeWikiRepository:
    def list_categories(self):
        return [WikiCategory(key="character", label="角色", count=1, template_group="character", animation_profile="entity-list", theme_token="character")]

    def list_pages(self, category="", q="", page_type="", limit=30, cursor=""):
        return [
            WikiPage(
                page_id="char:3074",
                page_type="character",
                title="爱兹拉",
                subtitle="Ezra Theodore",
                category="角色",
                route="/wiki/char/3074",
                source_pageid=3074,
                source_title="Data:Char/3074.json",
                content_json={"summary": "角色摘要"},
                updated_at="2026-07-07T00:00:00",
            )
        ], None

    def first_media_url_by_page(self, page_ids):
        return {"char:3074": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/asset.webp"}

    def get_page_detail(self, page_id):
        page = self.list_pages()[0][0]
        media = WikiMediaLink(
            page_id=page_id,
            section_key="media",
            media_id="media:sha1:abc",
            media_role="portrait",
            display_order=1,
            object_key="reverse1999/image/aa/asset.webp",
            url="http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/asset.webp",
            asset_type="image",
            mime="image/webp",
            title="立绘",
            sha1="abc",
            width=900,
            height=1400,
        )
        relation = WikiRelation("char:3074", "char:3001", "appears_with", "关联角色", 0.9)
        span = WikiLinkSpan("char:3074", "summary", "维尔汀", "/wiki/char/3001", 0.95)
        return {**page.to_api(), "mediaLinks": [media.to_api()], "relations": [relation.to_json()], "linkSpans": [span.to_json()]}

    def resolve_route(self, entity_id="", source_id="", title=""):
        if entity_id == "3074" or title == "爱兹拉":
            return "/wiki/char/3074"
        return None


def make_client(monkeypatch):
    app = FastAPI()
    app.include_router(wiki.router)
    monkeypatch.setattr(wiki, "get_wiki_repository", lambda: FakeWikiRepository())
    return TestClient(app)


def test_wiki_pages_returns_thumbnail_and_summary(monkeypatch):
    client = make_client(monkeypatch)
    body = client.get("/api/wiki/pages?category=character").json()
    assert body["items"][0]["pageId"] == "char:3074"
    assert body["items"][0]["thumbnail"].startswith("http://127.0.0.1:9002/")
    assert body["items"][0]["summary"] == "角色摘要"


def test_wiki_page_detail_has_safe_media_and_no_local_paths(monkeypatch):
    client = make_client(monkeypatch)
    body = client.get("/api/wiki/pages/char:3074").json()
    serialized = str(body)
    assert "D:\\" not in serialized
    assert "C:\\" not in serialized
    assert "local_relpath" not in serialized
    assert body["mediaLinks"][0]["url"].startswith("http://")
    assert body["mediaLinks"][0]["objectKey"] == "reverse1999/image/aa/asset.webp"
    assert body["linkSpans"][0]["targetRoute"] == "/wiki/char/3001"


def test_route_resolve_failure_returns_query(monkeypatch):
    client = make_client(monkeypatch)
    body = client.get("/api/wiki/routes/resolve?title=未知角色").json()
    assert body == {"route": None, "query": "未知角色"}
```

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py -q
```

Expected before implementation: FAIL if schemas or route fallback fields are missing.

- [ ] **Step 2: 写 repository 只读行为测试**

Create `tests/test_huiji_wiki_repository.py` with a fake PyMySQL connection wrapper that records SQL and rejects write statements:

```python
import pytest

from config.config import get_config
from src.huiji_wiki.repository import MySQLWikiRepository


class RecordingCursor:
    def __init__(self):
        self.queries = []
        self.rows = []

    def execute(self, sql, params=None):
        lowered = " ".join(sql.lower().split())
        self.queries.append(lowered)
        forbidden = ("insert ", "update ", "delete ", "drop ", "truncate ", "create ", "alter ", "replace ")
        assert not lowered.startswith(forbidden)
        if "from wiki_pages" in lowered and "count" not in lowered:
            self.rows = [
                {
                    "page_id": "char:3074",
                    "page_type": "character",
                    "title": "爱兹拉",
                    "subtitle": "Ezra Theodore",
                    "category": "角色",
                    "route": "/wiki/char/3074",
                    "source_pageid": 3074,
                    "source_title": "Data:Char/3074.json",
                    "content_json": '{"summary":"角色摘要"}',
                    "updated_at": "2026-07-07T00:00:00",
                }
            ]
        elif "from wiki_media_links" in lowered:
            self.rows = [{"page_id": "char:3074", "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/asset.webp"}]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class RecordingConnection:
    def __init__(self):
        self.cursor_obj = RecordingCursor()

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_mysql_repository_list_pages_is_read_only(monkeypatch):
    repo = MySQLWikiRepository(get_config())
    conn = RecordingConnection()
    monkeypatch.setattr(repo, "_connect", lambda: conn)
    pages, next_cursor = repo.list_pages(q="爱兹拉")
    assert pages[0].page_id == "char:3074"
    assert next_cursor is None
    assert all(query.startswith("select ") for query in conn.cursor_obj.queries)


def test_first_media_url_by_page_returns_http_url(monkeypatch):
    repo = MySQLWikiRepository(get_config())
    conn = RecordingConnection()
    monkeypatch.setattr(repo, "_connect", lambda: conn)
    urls = repo.first_media_url_by_page(["char:3074"])
    assert urls["char:3074"].startswith("http://")
```

Run:

```powershell
python -m pytest tests/test_huiji_wiki_repository.py -q
```

Expected before implementation: FAIL if repository performs schema writes or drops fields.

- [ ] **Step 3: 补齐 schemas 与 models**

Update `backend/wiki_schemas.py` so response fields match frontend DTO:

```python
class WikiMediaLinkItem(BaseModel):
    pageId: str = ""
    sectionKey: str = ""
    mediaId: str = ""
    mediaRole: str = ""
    displayOrder: int = 0
    fallbackMediaId: str = ""
    objectKey: str = ""
    url: str = ""
    assetType: str = ""
    mime: str = ""
    title: str = ""
    sha1: str = ""
    width: int = 0
    height: int = 0


class WikiRelationItem(BaseModel):
    fromPageId: str = ""
    toPageId: str = ""
    relationType: str = ""
    label: str = ""
    confidence: float = 0.0


class WikiLinkSpanItem(BaseModel):
    pageId: str = ""
    sectionKey: str = ""
    text: str = ""
    targetRoute: str = ""
    confidence: float = 0.0
```

Then change `WikiPageDetailResponse` to use those lists:

```python
mediaLinks: list[WikiMediaLinkItem] = []
relations: list[WikiRelationItem] = []
linkSpans: list[WikiLinkSpanItem] = []
```

Keep `src/huiji_wiki/models.py` camelCase mapping for `object_key -> objectKey`, `asset_type -> assetType`, `target_route -> targetRoute`, and `fallback_media_id -> fallbackMediaId`.

- [ ] **Step 4: 保持 repository 只读并补齐 fallback**

In `src/huiji_wiki/repository.py`:

- Keep `ensure_schema()` as a no-op for P0.
- Ensure all public methods catch connection errors and return stable empty results where list endpoints can degrade.
- Ensure `get_page_detail()` raises `KeyError` only for missing/unavailable detail.
- Ensure `first_media_url_by_page()` filters empty URL rows.
- Ensure no method issues SQL starting with `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `CREATE`, `ALTER`, or `REPLACE`.

In `backend/wiki.py`, keep route resolve response:

```python
return WikiRouteResolveResponse(route=route, query=entity_id or source_id or title)
```

For `wiki_search`, reuse `wiki_pages(q=q, limit=limit)` and do not return Data namespace raw pages outside repository results.

- [ ] **Step 5: Run backend contract tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q
```

Expected: PASS.

### Task 2: 补齐前端 Wiki API 类型和路由隔离测试

**对应 specs:** `API-P0-01` 至 `API-P0-08`、`FRONTEND-P0-01`、`FRONTEND-P0-02`、`RAGLINK-P0-02` 至 `RAGLINK-P0-04`

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/wiki.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.test.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.wiki.test.tsx`

**Interfaces:**
- Consumes: `/api/wiki/categories`, `/api/wiki/pages`, `/api/wiki/pages/{page_id}`, `/api/wiki/routes/resolve`, `/api/wiki/search`.
- Produces: typed frontend functions `fetchWikiCategories`, `fetchWikiPages`, `fetchWikiPage`, `resolveWikiRoute`, `searchWikiPages`.

- [ ] **Step 1: 写 API client 失败测试**

Create `frontend/react-app/src/api/wiki.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchWikiCategories, fetchWikiPage, fetchWikiPages, resolveWikiRoute, searchWikiPages } from './wiki'

describe('wiki api client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('fetches categories and pages with encoded params', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ categories: [{ key: 'character', label: '角色', count: 1 }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [], nextCursor: null }) })
    vi.stubGlobal('fetch', fetchMock)

    await fetchWikiCategories()
    await fetchWikiPages({ category: '角色', q: '爱兹拉', limit: 10 })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/wiki/categories')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/wiki/pages?category=%E8%A7%92%E8%89%B2&q=%E7%88%B1%E5%85%B9%E6%8B%89&limit=10')
  })

  it('fetches detail and route resolve', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ pageId: 'char:3074', pageType: 'character', title: '爱兹拉', subtitle: '', category: '角色', route: '/wiki/char/3074', content: {}, mediaLinks: [], relations: [], linkSpans: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ route: null, query: '未知' }) })
    vi.stubGlobal('fetch', fetchMock)

    await fetchWikiPage('char:3074')
    const resolved = await resolveWikiRoute({ title: '未知' })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/wiki/pages/char%3A3074')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/wiki/routes/resolve?title=%E6%9C%AA%E7%9F%A5')
    expect(resolved).toEqual({ route: null, query: '未知' })
  })

  it('uses the search endpoint for global search', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], nextCursor: null }) })
    vi.stubGlobal('fetch', fetchMock)
    await searchWikiPages('维尔汀')
    expect(fetchMock).toHaveBeenCalledWith('/api/wiki/search?q=%E7%BB%B4%E5%B0%94%E6%B1%80')
  })

  it('throws useful errors for failed requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    await expect(fetchWikiCategories()).rejects.toThrow('HTTP 503')
  })
})
```

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/api/wiki.test.ts --run
```

Expected before implementation: FAIL if `searchWikiPages` or field typing is missing.

- [ ] **Step 2: 补齐 TypeScript DTO**

Update `frontend/react-app/src/types/wiki.ts`:

```ts
export interface WikiMediaLink {
  pageId: string
  sectionKey: string
  mediaId: string
  mediaRole: string
  displayOrder: number
  fallbackMediaId?: string
  objectKey?: string
  url?: string
  assetType?: string
  mime?: string
  title?: string
  sha1?: string
  width?: number
  height?: number
}

export interface WikiRelation {
  fromPageId: string
  toPageId: string
  relationType: string
  label: string
  confidence: number
}

export interface WikiLinkSpan {
  pageId: string
  sectionKey: string
  text: string
  targetRoute?: string
  confidence: number
}

export interface WikiPageDetail extends WikiPageListItem {
  content: Record<string, unknown>
  mediaLinks: WikiMediaLink[]
  relations: WikiRelation[]
  linkSpans: WikiLinkSpan[]
  sourcePageid?: number | null
  sourceTitle?: string
}
```

Keep the existing category and list item names to avoid changing current imports.

- [ ] **Step 3: 补齐 API helper**

Update `frontend/react-app/src/api/wiki.ts` with:

```ts
export async function searchWikiPages(q: string, limit = 30): Promise<WikiPageListResponse> {
  const search = new URLSearchParams()
  if (q) search.set('q', q)
  if (limit) search.set('limit', String(limit))
  return fetchJson<WikiPageListResponse>(`/api/wiki/search?${search.toString()}`)
}
```

Keep existing `fetchWikiPage(pageId)` with `encodeURIComponent(pageId)`.

- [ ] **Step 4: 写 `/wiki` 路由隔离测试**

Create `frontend/react-app/src/App.wiki.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./components/wiki/WikiShell', () => ({
  WikiShell: () => <main data-testid="wiki-shell">Wiki Shell</main>,
}))

describe('App wiki route', () => {
  it('renders WikiShell outside the snap container on /wiki', () => {
    window.history.pushState({}, '', '/wiki')
    const { container } = render(<App />)
    expect(screen.getByTestId('wiki-shell')).toBeInTheDocument()
    expect(container.querySelector('.snap-container')).not.toBeInTheDocument()
  })
})
```

Run:

```powershell
npm test -- src/App.wiki.test.tsx src/api/wiki.test.ts --run
```

Expected: PASS after DTO and helper updates.

### Task 3: 重建 WikiShell 四区布局和列表交互

**对应 specs:** `FRONTEND-P0-03` 至 `FRONTEND-P0-12`、`ANIMATION-P0-01` 至 `ANIMATION-P0-03`

**Files:**
- Replace: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/wikiLayout.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageIndex.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageInfo.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiReader.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageIndex.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageInfo.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.test.tsx`

**Interfaces:**
- Consumes: `WikiCategoryItem`, `WikiPageListItem`, `WikiPageDetail`, `fetchWikiCategories`, `fetchWikiPages`, `fetchWikiPage`.
- Produces:
  - `CategoryRail({ categories, activeCategory, onSelect })`
  - `PageIndex({ query, onQueryChange, pages, selectedPageId, onSelect })`
  - `WikiReader({ page })`
  - `PageInfo({ page })`

- [ ] **Step 1: 建立布局常量**

Create `wikiLayout.ts`:

```ts
export const WIKI_RAIL_CLOSED_WIDTH = 28
export const WIKI_RAIL_OPEN_WIDTH = 280
export const WIKI_INDEX_WIDTH = 280
export const WIKI_INFO_WIDTH = 220
export const WIKI_READER_MIN_WIDTH = 420
```

- [ ] **Step 2: 写 CategoryRail 测试**

Create `CategoryRail.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HOVER_REVEAL_DELAY_MS } from '../../constants/layout'
import { CategoryRail } from './CategoryRail'
import { WIKI_RAIL_OPEN_WIDTH } from './wikiLayout'

describe('CategoryRail', () => {
  it('reveals after the shared hover delay and selects categories', () => {
    vi.useFakeTimers()
    const onSelect = vi.fn()
    render(<CategoryRail categories={[{ key: 'character', label: '角色', count: 132 }]} activeCategory="" onSelect={onSelect} />)

    const rail = screen.getByTestId('wiki-category-rail')
    expect(rail).toHaveStyle({ width: '28px' })

    fireEvent.mouseEnter(rail)
    vi.advanceTimersByTime(HOVER_REVEAL_DELAY_MS)

    expect(rail).toHaveStyle({ width: `${WIKI_RAIL_OPEN_WIDTH}px` })
    fireEvent.click(screen.getByRole('button', { name: /角色/ }))
    expect(onSelect).toHaveBeenCalledWith('character')
    vi.useRealTimers()
  })
})
```

- [ ] **Step 3: 实现 CategoryRail**

`CategoryRail.tsx` must:

- import `HOVER_REVEAL_DELAY_MS` from `../../constants/layout`.
- use closed width `28px`, open width `280px`.
- render categories from props.
- call `onSelect(category.key)` only; do not render page content.
- expose `data-testid="wiki-category-rail"`.
- keep `animationProfile`, `templateGroup`, `themeToken` as pass-through metadata, not concrete ReactBits bindings.

- [ ] **Step 4: 写 PageIndex 测试**

Create `PageIndex.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PageIndex } from './PageIndex'
import { WIKI_INDEX_WIDTH } from './wikiLayout'

describe('PageIndex', () => {
  it('renders search and rich cards', () => {
    const onQueryChange = vi.fn()
    const onSelect = vi.fn()
    render(
      <PageIndex
        query=""
        onQueryChange={onQueryChange}
        pages={[{ pageId: 'char:3074', pageType: 'character', title: '爱兹拉', subtitle: 'Ezra', category: '角色', route: '/wiki/char/3074', thumbnail: 'http://127.0.0.1:9002/thumb.webp', summary: '角色摘要' }]}
        selectedPageId=""
        onSelect={onSelect}
      />,
    )
    expect(screen.getByTestId('wiki-page-index')).toHaveStyle({ width: `${WIKI_INDEX_WIDTH}px` })
    expect(screen.getByRole('textbox', { name: '搜索 Wiki 页面' })).toBeInTheDocument()
    expect(screen.getByText('character')).toBeInTheDocument()
    expect(screen.getByText('Ezra')).toBeInTheDocument()
    expect(screen.getByText('角色摘要')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '爱兹拉' })).toHaveAttribute('src', 'http://127.0.0.1:9002/thumb.webp')

    fireEvent.change(screen.getByRole('textbox', { name: '搜索 Wiki 页面' }), { target: { value: '维尔汀' } })
    expect(onQueryChange).toHaveBeenCalledWith('维尔汀')
    fireEvent.click(screen.getByRole('button', { name: /爱兹拉/ }))
    expect(onSelect).toHaveBeenCalledWith('char:3074')
  })
})
```

- [ ] **Step 5: 实现 PageIndex**

`PageIndex.tsx` must:

- expose `data-testid="wiki-page-index"`.
- use fixed width `280px`.
- render search input with `aria-label="搜索 Wiki 页面"`.
- render rich cards with thumbnail, page type, title, subtitle, summary.
- use fixed thumbnail dimensions and a fixed-size placeholder when `thumbnail` is missing.
- call `onSelect(page.pageId)`.

- [ ] **Step 6: 写 PageInfo 测试**

Create `PageInfo.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PageInfo } from './PageInfo'
import { WIKI_INFO_WIDTH } from './wikiLayout'

describe('PageInfo', () => {
  it('shows source and counts without taking reader space', () => {
    render(
      <PageInfo
        page={{
          pageId: 'char:3074',
          pageType: 'character',
          title: '爱兹拉',
          subtitle: 'Ezra',
          category: '角色',
          route: '/wiki/char/3074',
          content: { sections: [{ title: '基础资料' }, { title: '技能' }] },
          mediaLinks: [{ pageId: 'char:3074', sectionKey: 'media', mediaId: 'm', mediaRole: 'portrait', displayOrder: 1, url: 'http://127.0.0.1:9002/a.webp' }],
          relations: [{ fromPageId: 'char:3074', toPageId: 'char:1', relationType: 'x', label: '关联', confidence: 1 }],
          linkSpans: [{ pageId: 'char:3074', sectionKey: 'summary', text: '维尔汀', targetRoute: '/wiki/char/1', confidence: 1 }],
          sourcePageid: 3074,
          sourceTitle: 'Data:Char/3074.json',
        }}
      />,
    )
    expect(screen.getByTestId('wiki-page-info')).toHaveStyle({ width: `${WIKI_INFO_WIDTH}px` })
    expect(screen.getByText('Data:Char/3074.json')).toBeInTheDocument()
    expect(screen.getByText('/wiki/char/3074')).toBeInTheDocument()
    expect(screen.getByText('1 media')).toBeInTheDocument()
    expect(screen.getByText('1 relation')).toBeInTheDocument()
    expect(screen.getByText('1 link')).toBeInTheDocument()
    expect(screen.getByText('基础资料')).toBeInTheDocument()
  })
})
```

- [ ] **Step 7: 实现 PageInfo**

`PageInfo.tsx` must:

- expose `data-testid="wiki-page-info"`.
- use fixed width `220px`.
- show `sourceTitle`, `sourcePageid`, `route`, media count, relation count, link count.
- derive outline from `content.sections` if it is an array of objects with `title`.

- [ ] **Step 8: 写 WikiShell 集成测试**

Create `WikiShell.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WikiShell } from './WikiShell'

vi.mock('../../api/wiki', () => ({
  fetchWikiCategories: vi.fn().mockResolvedValue([{ key: 'character', label: '角色', count: 1 }]),
  fetchWikiPages: vi.fn().mockResolvedValue({ items: [{ pageId: 'char:3074', pageType: 'character', title: '爱兹拉', subtitle: 'Ezra', category: '角色', route: '/wiki/char/3074', thumbnail: 'http://127.0.0.1:9002/thumb.webp', summary: '角色摘要' }], nextCursor: null }),
  fetchWikiPage: vi.fn().mockResolvedValue({ pageId: 'char:3074', pageType: 'character', title: '爱兹拉', subtitle: 'Ezra', category: '角色', route: '/wiki/char/3074', content: { summary: '角色摘要' }, mediaLinks: [], relations: [], linkSpans: [] }),
}))

describe('WikiShell', () => {
  it('renders the four-region workspace and loads first detail', async () => {
    render(<WikiShell />)
    await waitFor(() => expect(screen.getByTestId('wiki-category-rail')).toBeInTheDocument())
    expect(screen.getByTestId('wiki-page-index')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-reader')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-page-info')).toBeInTheDocument()
    expect(screen.getByText('爱兹拉')).toBeInTheDocument()
  })
})
```

- [ ] **Step 9: 实现 WikiShell 和 WikiReader skeleton**

`WikiShell.tsx` must:

- load categories on mount.
- load pages when category or query changes.
- select the first page when list changes.
- load detail via `fetchWikiPage(selectedPageId)`.
- render four regions in one viewport-height workspace.
- show error state when API fails.
- include a visible return link to `/`.

`WikiReader.tsx` must:

- expose `data-testid="wiki-reader"`.
- select templates by `page.pageType`.
- show empty state when no page is selected.

- [ ] **Step 10: Run layout tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/components/wiki/CategoryRail.test.tsx src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx src/components/wiki/WikiShell.test.tsx --run
```

Expected: PASS.

### Task 4: 重建模板和主媒体窗口

**对应 specs:** `MEDIA-P0-06`、`FRONTEND-P0-12`、`TEMPLATE-P0-01` 至 `TEMPLATE-P0-09`、`ANIMATION-P0-02`

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/PsychubePage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/StoryPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/GenericWikiPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/WikiTemplates.test.tsx`

**Interfaces:**
- Consumes: `WikiPageDetail`, `WikiMediaLink`.
- Produces: page template components used by `WikiReader`.

- [ ] **Step 1: 写 CharacterMediaStage 测试**

Create `CharacterMediaStage.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CharacterMediaStage } from './CharacterMediaStage'

describe('CharacterMediaStage', () => {
  it('uses one large frame for portrait and live2d fallback', () => {
    render(
      <CharacterMediaStage
        media={[
          { pageId: 'char:1', sectionKey: 'media', mediaId: 'portrait', mediaRole: 'portrait', displayOrder: 1, url: 'http://127.0.0.1:9002/portrait.webp', title: '立绘' },
          { pageId: 'char:1', sectionKey: 'media', mediaId: 'live2d', mediaRole: 'live2d', displayOrder: 2, title: 'Live2D' },
        ]}
      />,
    )
    const frame = screen.getByTestId('character-media-stage')
    expect(frame).toHaveStyle({ minHeight: '560px' })
    expect(screen.getByRole('img', { name: '立绘' })).toHaveAttribute('src', 'http://127.0.0.1:9002/portrait.webp')

    fireEvent.click(screen.getByRole('button', { name: 'Live2D' }))
    expect(frame).toHaveStyle({ minHeight: '560px' })
    expect(screen.getByText('Live2D 暂未接入')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 实现 CharacterMediaStage**

`CharacterMediaStage.tsx` must:

- group roles `portrait`, `live2d`, `skin` into one tabbed frame.
- keep `minHeight: 560px`.
- render real `<img>` when selected media has `url`.
- show fixed-size fallback when selected media lacks `url` or is `live2d`.
- keep the Live2D button visible even without a player.

- [ ] **Step 3: 写模板测试**

Create `WikiTemplates.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CharacterPage } from './CharacterPage'
import { GenericWikiPage } from './GenericWikiPage'
import { PsychubePage } from './PsychubePage'
import { StoryPage } from './StoryPage'

const basePage = {
  pageId: 'char:1',
  pageType: 'character',
  title: '爱兹拉',
  subtitle: 'Ezra',
  category: '角色',
  route: '/wiki/char/1',
  content: { summary: '角色摘要', profile: { rarity: '6星', inspiration: '星' }, skills: [{ name: '技能一', description: '技能描述' }] },
  mediaLinks: [{ pageId: 'char:1', sectionKey: 'media', mediaId: 'portrait', mediaRole: 'portrait', displayOrder: 1, url: 'http://127.0.0.1:9002/portrait.webp', title: '立绘' }],
  relations: [],
  linkSpans: [],
}

describe('wiki templates', () => {
  it('renders character data face and media stage', () => {
    render(<CharacterPage page={basePage} />)
    expect(screen.getByTestId('character-media-stage')).toBeInTheDocument()
    expect(screen.getByText('角色摘要')).toBeInTheDocument()
    expect(screen.getByText('6星')).toBeInTheDocument()
    expect(screen.getByText('技能一')).toBeInTheDocument()
  })

  it('renders psychube and story stable data faces', () => {
    render(<PsychubePage page={{ ...basePage, pageType: 'psychube', title: '心相', category: '心相' }} />)
    expect(screen.getByText('心相')).toBeInTheDocument()
    render(<StoryPage page={{ ...basePage, pageType: 'story', title: '剧情', category: '剧情' }} />)
    expect(screen.getByText('剧情')).toBeInTheDocument()
  })

  it('does not expose raw json in generic pages', () => {
    render(<GenericWikiPage page={{ ...basePage, pageType: 'generic', content: { summary: '整理后的摘要', raw: { nested: true } } }} />)
    expect(screen.getByText('整理后的摘要')).toBeInTheDocument()
    expect(screen.queryByText(/"nested"/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 4: 实现四类模板**

Each template must:

- accept `page: WikiPageDetail`.
- render title, subtitle, summary.
- use stable empty states for missing fields.
- use `CharacterMediaStage` for character media.
- avoid dumping raw `content` JSON.
- preserve visible regions for future animation wrappers without importing ReactBits.

- [ ] **Step 5: Wire templates into WikiReader**

Update `WikiReader.tsx`:

```tsx
switch (page.pageType) {
  case 'character':
    return <CharacterPage page={page} />
  case 'psychube':
    return <PsychubePage page={page} />
  case 'story':
    return <StoryPage page={page} />
  default:
    return <GenericWikiPage page={page} />
}
```

- [ ] **Step 6: Run template tests**

Run:

```powershell
npm test -- src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx --run
```

Expected: PASS.

### Task 5: 实现关键词链接多 span 渲染

**对应 specs:** `LINK-P0-01` 至 `LINK-P0-05`

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.test.tsx`

**Interfaces:**
- Consumes: `text: string`, `spans: WikiLinkSpan[]`.
- Produces: text nodes and anchor nodes with stable fallback.

- [ ] **Step 1: 写 KeywordText 测试**

Create `KeywordText.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { KeywordText } from './KeywordText'

describe('KeywordText', () => {
  it('renders multiple and repeated keyword links', () => {
    render(
      <KeywordText
        text="维尔汀遇见爱兹拉，维尔汀再次出现。"
        spans={[
          { pageId: 'p', sectionKey: 's', text: '维尔汀', targetRoute: '/wiki/char/vertin', confidence: 0.9 },
          { pageId: 'p', sectionKey: 's', text: '爱兹拉', targetRoute: '/wiki/char/ezra', confidence: 0.9 },
          { pageId: 'p', sectionKey: 's', text: '维尔汀', targetRoute: '/wiki/char/vertin', confidence: 0.9 },
        ]}
      />,
    )
    expect(screen.getAllByRole('link', { name: '维尔汀' })).toHaveLength(2)
    expect(screen.getByRole('link', { name: '爱兹拉' })).toHaveAttribute('href', '/wiki/char/ezra')
  })

  it('does not create empty links for missing target routes', () => {
    render(<KeywordText text="未知角色" spans={[{ pageId: 'p', sectionKey: 's', text: '未知角色', targetRoute: '', confidence: 0.9 }]} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('未知角色')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 实现 KeywordText**

Implementation rule:

- Iterate through spans in the order they should appear.
- For repeated text, search from the last consumed index, not from the start.
- Render unmatched text as plain text.
- Render span with `targetRoute` as `<a href={targetRoute} className="wiki-keyword-link">`.
- Render span without `targetRoute` as plain text.
- Do not scan all text for entities outside the provided spans.

- [ ] **Step 3: Use KeywordText in templates**

In templates, use `KeywordText` for summary and section text where the section key matches current API spans. If the content shape is not sectioned, pass all page-level spans to the summary block.

- [ ] **Step 4: Run keyword tests**

Run:

```powershell
npm test -- src/components/wiki/KeywordText.test.tsx --run
```

Expected: PASS.

### Task 6: 复测并补齐三个 Wiki 入口

**对应 specs:** `FRONTEND-P0-01`、`FRONTEND-P0-02`

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/Sidebar.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.wiki.test.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.test.tsx`

**Interfaces:**
- Produces links to `/wiki` from TopNav, Sidebar, calendar page.

- [ ] **Step 1: 写 TopNav Wiki 入口测试**

Create `TopNav.wiki.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useUIStore } from '../store/uiStore'
import { TopNav } from './TopNav'

describe('TopNav wiki entry', () => {
  it('links to /wiki', () => {
    useUIStore.getState().setTopNav(true)
    render(<TopNav />)
    expect(screen.getByRole('link', { name: 'Wiki' })).toHaveAttribute('href', '/wiki')
  })
})
```

- [ ] **Step 2: 确认 Sidebar 和 CategoryPanel 入口测试存在**

Keep or extend current `CategoryPanel.test.tsx` case:

```tsx
const link = screen.getByRole('link', { name: /进入WIKI/ })
expect(link).toHaveAttribute('href', '/wiki')
```

Add a Sidebar assertion to the most suitable existing or new test file if no Sidebar test exists:

```tsx
expect(screen.getByRole('link', { name: /进入WIKI/ })).toHaveAttribute('href', '/wiki')
```

- [ ] **Step 3: 补齐入口实现 only if tests fail**

Current code already has TopNav and Sidebar Wiki links and CategoryPanel calendar CTA. Only edit if tests show a regression:

- TopNav link text: `Wiki`, `href="/wiki"`.
- Sidebar link text: `进入WIKI →`, `href="/wiki"`.
- Calendar CTA accessible name includes `进入WIKI`, `href="/wiki"`.

- [ ] **Step 4: Run entry tests**

Run:

```powershell
npm test -- src/App.wiki.test.tsx src/components/TopNav.wiki.test.tsx src/components/sections/CategoryPanel.test.tsx --run
```

Expected: PASS.

### Task 7: 恢复只读真实数据验收脚本

**对应 specs:** `DATA-P0-01` 至 `DATA-P0-06`、`MEDIA-P0-03` 至 `MEDIA-P0-07`、`VERIFY-P0-01` 至 `VERIFY-P0-04`、`VERIFY-P0-07`

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/verify_huiji_wiki_e2e.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_e2e_script.py`

**Interfaces:**
- CLI:
  - `python scripts/verify_huiji_wiki_e2e.py --page-id char:3074 --api http://127.0.0.1:8000`
- Functions:
  - `validate_page_payload(payload: dict) -> list[str]`
  - `first_http_media_url(payload: dict) -> str`

- [ ] **Step 1: 写验收脚本单测**

Create `tests/test_huiji_wiki_e2e_script.py`:

```python
import pytest

from scripts.verify_huiji_wiki_e2e import first_http_media_url, validate_page_payload


def test_validate_page_payload_rejects_local_paths():
    payload = {"mediaLinks": [{"url": "D:\\bad\\image.png"}]}
    issues = validate_page_payload(payload)
    assert any("local path" in issue for issue in issues)


def test_validate_page_payload_accepts_http_media_url():
    payload = {
        "pageId": "char:3074",
        "mediaLinks": [{"url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/a.webp"}],
    }
    assert validate_page_payload(payload) == []
    assert first_http_media_url(payload).startswith("http://127.0.0.1:9002/")


def test_first_http_media_url_fails_without_media():
    with pytest.raises(ValueError, match="no http media url"):
        first_http_media_url({"mediaLinks": [{"url": ""}]})
```

- [ ] **Step 2: 实现只读脚本**

Create `scripts/verify_huiji_wiki_e2e.py`:

```python
from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.request import Request, urlopen


LOCAL_PATH_MARKERS = ("D:\\", "C:\\", "local_relpath")


def validate_page_payload(payload: dict[str, Any]) -> list[str]:
    serialized = json.dumps(payload, ensure_ascii=False)
    issues: list[str] = []
    for marker in LOCAL_PATH_MARKERS:
        if marker in serialized:
            issues.append(f"local path marker leaked: {marker}")
    media_links = payload.get("mediaLinks") or []
    if not isinstance(media_links, list):
        issues.append("mediaLinks is not a list")
        return issues
    http_urls = [str(item.get("url", "")) for item in media_links if isinstance(item, dict) and str(item.get("url", "")).startswith(("http://", "https://"))]
    if not http_urls:
        issues.append("no http media url in mediaLinks")
    return issues


def first_http_media_url(payload: dict[str, Any]) -> str:
    for item in payload.get("mediaLinks") or []:
        if isinstance(item, dict):
            url = str(item.get("url", ""))
            if url.startswith(("http://", "https://")):
                return url
    raise ValueError("no http media url")


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def check_url(url: str) -> int:
    request = Request(url, method="HEAD")
    with urlopen(request, timeout=10) as response:
        return int(response.status)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Huiji Wiki API and media verifier")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--skip-url-check", action="store_true")
    args = parser.parse_args()

    payload = fetch_json(f"{args.api.rstrip('/')}/api/wiki/pages/{args.page_id}")
    issues = validate_page_payload(payload)
    if issues:
        for issue in issues:
            print(f"[wiki-e2e] FAIL {issue}")
        return 1

    url = first_http_media_url(payload)
    if not args.skip_url_check:
        status = check_url(url)
        if status >= 400:
            print(f"[wiki-e2e] FAIL media url returned HTTP {status}: {url}")
            return 1

    print("[wiki-e2e] payload has safe http media url")
    print(f"[wiki-e2e] media url: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

This script only performs HTTP GET/HEAD. It does not import MinIO, PyMySQL, Milvus, or builder code.

- [ ] **Step 3: Run script tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_e2e_script.py -q
```

Expected: PASS.

### Task 8: 全量测试、构建和真实数据验收

**对应 specs:** all P0 items, especially `VERIFY-P0-05` 至 `VERIFY-P0-07`

**Files:**
- No code files should be edited in this task unless verification exposes a defect in earlier tasks.

**Interfaces:**
- Consumes all previous tasks.
- Produces final acceptance record in this plan's self-check table during execution.

- [ ] **Step 1: Run backend target tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_e2e_script.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend target tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/api/wiki.test.ts src/App.wiki.test.tsx src/components/TopNav.wiki.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/wiki/CategoryRail.test.tsx src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx src/components/wiki/KeywordText.test.tsx src/components/wiki/WikiShell.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx --run
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run build
```

Expected: TypeScript and Vite build succeed.

- [ ] **Step 4: Start backend against Docker MySQL without writing data**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
$mysqlPassword = (docker inspect edurag-mysql --format '{{range .Config.Env}}{{println .}}{{end}}' | Where-Object { $_ -like 'MYSQL_ROOT_PASSWORD=*' } | Select-Object -First 1) -replace '^MYSQL_ROOT_PASSWORD=', ''
if (-not $mysqlPassword) { $mysqlPassword = (docker inspect edurag-mysql --format '{{range .Config.Env}}{{println .}}{{end}}' | Where-Object { $_ -like 'MYSQL_PASSWORD=*' } | Select-Object -First 1) -replace '^MYSQL_PASSWORD=', '' }
$env:MYSQL_PASSWORD = $mysqlPassword
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Expected: backend starts. Keep this terminal running for the next steps.

- [ ] **Step 5: Pick a real page id from MySQL through API**

In another terminal:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/wiki/pages?limit=1' | ConvertTo-Json -Depth 8
```

Expected: first item includes a real `pageId`, likely `char:*`, and a thumbnail HTTP URL.

- [ ] **Step 6: Run read-only E2E script**

Use the `pageId` from Step 5:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python scripts/verify_huiji_wiki_e2e.py --page-id <真实 page_id> --api http://127.0.0.1:8000
```

Expected:

```text
[wiki-e2e] payload has safe http media url
```

- [ ] **Step 7: Start frontend and manually inspect `/wiki`**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open:

```text
http://127.0.0.1:5173/wiki
```

Manual checks:

- `/wiki` loads outside the snap container.
- Left rail opens after the shared hover delay.
- Left rail open width equals PageIndex width.
- PageIndex supports search and shows thumbnail, page type, subtitle, summary.
- Reader opens at least one real page.
- Character or psychube main media area displays a real MinIO image.
- Live2D tab remains visible and fallback does not resize the frame.
- PageInfo shows source, media count, relation count, link count, route and outline.
- A paragraph with multiple keyword spans renders multiple blue links.
- TopNav, Sidebar, and Calendar CTA all navigate to `/wiki`.

## 5. 可选任务

Only execute these after every P0 acceptance gate passes.

### Optional A: Alias fallback polish

**Specs:** `API-P1-01`, `RAGLINK-P1-02`

Execution condition: route resolve P0 works and real MySQL aliases are available. Add focused tests for title alias fallback ordering.

### Optional B: Query parameter deep links

**Specs:** `FRONTEND-P1-02`

Execution condition: basic `/wiki` page selection works. Add support for `/wiki?q=爱兹拉` and `/wiki?pageId=char:3074`.

### Optional C: Minimal CSS transitions

**Specs:** `ANIMATION-P1-01`

Execution condition: all layout tests and browser checks pass. Add lightweight CSS transitions for rail reveal and card hover without importing new animation libraries.

## 6. Deferred / Out of Scope

- `DATA-P1-01` 至 `DATA-P1-03`: raw 资源恢复后再恢复 builder、media upload 和 build report。
- `DATA-P2-01` 至 `DATA-P2-03`: 统一构建器、增量构建、构建任务 UI。
- `MEDIA-P1-01` 至 `MEDIA-P1-03`: MinIO 上传报告、幂等上传、衍生图。
- `MEDIA-P2-01` 至 `MEDIA-P2-03`: CDN、权限策略、媒体中心、Live2D 资源预加载。
- `API-P2-01` 至 `API-P2-02`: 专用搜索索引、后台编辑、版本管理。
- `FRONTEND-P2-01` 至 `FRONTEND-P2-02`: 高级筛选、复杂响应式布局。
- `TEMPLATE-P2-01` 至 `TEMPLATE-P2-04`: 关系图谱、Live2D 真播放器、媒体中心、复杂转场。
- `LINK-P2-01` 至 `LINK-P2-03`: 禁用词表、同名消歧 UI、人工修正表。
- `RAGLINK-P1-01`、`RAGLINK-P1-03`: RAG source card 实际跳转入口。
- `RAGLINK-P2-01` 至 `RAGLINK-P2-03`: RAG 媒体共用组件、段落跳转、上下文返回栈。
- `ANIMATION-P2-01` 至 `ANIMATION-P2-03`: ReactBits 逐区动效接入。
- `VERIFY-P2-01` 至 `VERIFY-P2-03`: Playwright 截图、性能预算、自动巡检。

## 7. 完成后自检表

Execution must update the Status and Evidence columns before claiming completion.

| Specs 编号 | Task | Status | Evidence |
|---|---:|---|---|
| `DATA-P0-01` | 8 | Not checked | Real data source is current MySQL + MinIO + processed artifacts. |
| `DATA-P0-02` | 7, 8 | Not checked | E2E script only reads API and URL; no processed writes. |
| `DATA-P0-03` | 1, 8 | Not checked | No build script or MySQL replace executed. |
| `DATA-P0-04` | 7, 8 | Not checked | No MinIO write/delete commands executed. |
| `DATA-P0-05` | 1, 8 | Not checked | No Milvus command or vector rebuild executed. |
| `DATA-P0-06` | 8 | Not checked | Final notes state current scope is processed P0 Wiki data only. |
| `MEDIA-P0-01` | 1, 8 | Not checked | API/real data uses `reverse1999-assets`. |
| `MEDIA-P0-02` | 8 | Not checked | No second media store introduced. |
| `MEDIA-P0-03` | 1, 7 | Not checked | API media fields include HTTP `url`. |
| `MEDIA-P0-04` | 1, 7 | Not checked | Tests reject `D:\`, `C:\`, `local_relpath`. |
| `MEDIA-P0-05` | 1 | Not checked | `objectKey` preserved while rendering uses `url`. |
| `MEDIA-P0-06` | 3, 4, 8 | Not checked | PageIndex and media stage render real URL or fixed placeholder. |
| `MEDIA-P0-07` | 7, 8 | Not checked | Read-only E2E checks a real image URL. |
| `API-P0-01` | 1 | Not checked | Categories endpoint test. |
| `API-P0-02` | 1, 2 | Not checked | Pages endpoint/client test. |
| `API-P0-03` | 1, 2 | Not checked | Detail endpoint/client test. |
| `API-P0-04` | 1, 2 | Not checked | Resolve failure returns `route: null` and `query`. |
| `API-P0-05` | 1, 2 | Not checked | Search helper and endpoint test. |
| `API-P0-06` | 1, 3 | Not checked | API errors render Wiki error state only. |
| `API-P0-07` | 1 | Not checked | Repository reads current table fields. |
| `API-P0-08` | 1, 2 | Not checked | camelCase DTO tests. |
| `FRONTEND-P0-01` | 2, 8 | Not checked | App.wiki test and browser check. |
| `FRONTEND-P0-02` | 6, 8 | Not checked | TopNav, Sidebar, Calendar CTA tests/manual check. |
| `FRONTEND-P0-03` | 3 | Not checked | WikiShell four-region test. |
| `FRONTEND-P0-04` | 3, 8 | Not checked | layout constants and browser check. |
| `FRONTEND-P0-05` | 3 | Not checked | CategoryRail reveal test. |
| `FRONTEND-P0-06` | 3 | Not checked | CategoryRail only selects category. |
| `FRONTEND-P0-07` | 3 | Not checked | PageIndex search test. |
| `FRONTEND-P0-08` | 3 | Not checked | PageIndex rich card test. |
| `FRONTEND-P0-09` | 3, 4 | Not checked | WikiReader template switch. |
| `FRONTEND-P0-10` | 3 | Not checked | PageInfo count/source/route test. |
| `FRONTEND-P0-11` | 3 | Not checked | WikiShell error state test or manual check. |
| `FRONTEND-P0-12` | 3, 4 | Not checked | fixed placeholder behavior. |
| `TEMPLATE-P0-01` | 4 | Not checked | four template tests. |
| `TEMPLATE-P0-02` | 4, 8 | Not checked | large real image media stage. |
| `TEMPLATE-P0-03` | 4 | Not checked | same `CharacterMediaStage` tabs. |
| `TEMPLATE-P0-04` | 4 | Not checked | Live2D fallback test. |
| `TEMPLATE-P0-05` | 4 | Not checked | fallback frame size test. |
| `TEMPLATE-P0-06` | 4 | Not checked | character data face test. |
| `TEMPLATE-P0-07` | 4 | Not checked | psychube stable render test. |
| `TEMPLATE-P0-08` | 4 | Not checked | story stable render test. |
| `TEMPLATE-P0-09` | 4 | Not checked | generic page does not dump raw JSON. |
| `LINK-P0-01` | 5 | Not checked | multiple link test. |
| `LINK-P0-02` | 5 | Not checked | repeated link test. |
| `LINK-P0-03` | 5 | Not checked | targetRoute anchor test. |
| `LINK-P0-04` | 5 | Not checked | missing target fallback test. |
| `LINK-P0-05` | 5 | Not checked | component only consumes provided spans. |
| `RAGLINK-P0-01` | 1, 8 | Not checked | no RAG retrieval files modified. |
| `RAGLINK-P0-02` | 1, 2 | Not checked | route shape preserved. |
| `RAGLINK-P0-03` | 1 | Not checked | resolve uses entity/source/title. |
| `RAGLINK-P0-04` | 1 | Not checked | resolve fallback query test. |
| `ANIMATION-P0-01` | 3, 4 | Not checked | no ReactBits component names imported. |
| `ANIMATION-P0-02` | 3, 4, 5 | Not checked | visible component boundaries. |
| `ANIMATION-P0-03` | 1, 3 | Not checked | metadata fields preserved. |
| `VERIFY-P0-01` | 7 | Not checked | script exists and is read-only. |
| `VERIFY-P0-02` | 7 | Not checked | script rejects local paths. |
| `VERIFY-P0-03` | 7 | Not checked | script requires HTTP media URL. |
| `VERIFY-P0-04` | 7, 8 | Not checked | script checks real URL. |
| `VERIFY-P0-05` | 3, 4, 5, 8 | Not checked | frontend target tests pass. |
| `VERIFY-P0-06` | 8 | Not checked | browser manual checks recorded. |
| `VERIFY-P0-07` | 8 | Not checked | final evidence includes real data E2E. |

## 8. 最终验证命令

Run all target checks:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_e2e_script.py -q
```

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/api/wiki.test.ts src/App.wiki.test.tsx src/components/TopNav.wiki.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/wiki/CategoryRail.test.tsx src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx src/components/wiki/KeywordText.test.tsx src/components/wiki/WikiShell.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx --run
npm run build
```

Then run the real read-only chain:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python scripts/verify_huiji_wiki_e2e.py --page-id <真实 page_id> --api http://127.0.0.1:8000
```

Expected final evidence:

```text
[wiki-e2e] payload has safe http media url
```

