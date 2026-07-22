# Huiji Wiki RAG-Gated Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 RAG 线程已确认的共享 MinIO、`data/processed/huiji/dev`、`text_child_bge_m3_v3` 与 source/media 契约，恢复灰机 Wiki P0 应用层，形成只读、可验收的 `/api/wiki/*` + React `/wiki` 浏览链路。

**Architecture:** 本计划采用 RAG-gated 执行方式：第一任务记录 RAG 已确认的 `GATE-P0-*` 共享契约，后续任务只能只读消费这些契约。后端只读消费 Wiki MySQL 与 RAG 确认的媒体 URL，前端恢复独立 `/wiki` 四区工作区，验证脚本只请求 API 与 HTTP 媒体 URL，不写 MySQL、MinIO、Milvus 或 processed artifacts。

**Tech Stack:** Python 3, pytest, FastAPI, Pydantic, PyMySQL, React 18, TypeScript, Vite, Vitest, Testing Library, Framer Motion, Docker MySQL, MinIO.

## Global Constraints

- 本计划当前状态为待审核；审核通过前不得执行代码修改。
- `GATE-P0-01` 至 `GATE-P0-05` 已由 RAG 线程确认；执行前必须先写入 `docs/wiki-rag-contract-record.md` 作为本轮审计记录。
- Wiki P0 执行必须以 Docker MySQL、MinIO 和 RAG 已确认的 `data/processed/huiji/dev` 为真实数据源。
- P0 代码和验收只能只读检查 `data/processed/huiji/dev`，不得改写 `parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl` 或索引文件。
- P0 不执行会替换 Wiki MySQL 表的构建动作；如需读取 MySQL，只通过 API 或 repository 查询。
- P0 不清空、不覆盖、不迁移 MinIO bucket 或 `reverse1999/` prefix。
- P0 不创建、不删除、不重建 Milvus collection。
- 原始爬虫资源虽然已恢复，但 Wiki P0 不因此获得重跑构建器、覆盖 MySQL 或上传 MinIO 的权限。
- Wiki 不直接消费 Milvus，也不参与向量化；如需从 RAG 侧获得跳转字段，只通过 API/metadata 契约间接消费。
- Active Milvus collection 为 `text_child_bge_m3_v3`，Wiki 只记录该值用于排查。
- 页面资源选择以 `data/processed/huiji/dev/media_assets.jsonl` 为准，不直接遍历 MinIO，不消费未进入 `media_assets.jsonl` 的额外对象。
- `image`、`portrait`、`skill` 默认可展示；`voice` 只在折叠语音面板、独立 Tab 或明确语音入口展示；`video` 只在视频面板、独立 Tab 或明确 video 入口展示。
- API payload 中不得出现 `D:\`、`C:\`、`local_relpath` 等本地路径泄露。
- Wiki 修复不得修改 RAG 检索链路、入库流程、向量化流程或聊天输出格式。
- 前端不直接读本地文件系统，不读取 `public/wiki/**` 静态 manifest 作为主数据源，不在浏览器端做复杂实体识别。
- 动效不能阻塞 P0 数据面恢复；本轮不接入具体 ReactBits 组件。
- 本项目当前不使用 git 作为执行门槛；每个任务完成后用测试与验收记录代替提交检查。

---

## 1. 目标范围

本轮主线只覆盖 specs 的 P0 条目：

- `GATE-P0-01` 至 `GATE-P0-05`
- `DATA-P0-01` 至 `DATA-P0-10`
- `MEDIA-P0-01` 至 `MEDIA-P0-10`
- `API-P0-01` 至 `API-P0-11`
- `FRONTEND-P0-01` 至 `FRONTEND-P0-12`
- `TEMPLATE-P0-01` 至 `TEMPLATE-P0-10`
- `LINK-P0-01` 至 `LINK-P0-05`
- `RAGLINK-P0-01` 至 `RAGLINK-P0-05`
- `ANIMATION-P0-01` 至 `ANIMATION-P0-03`
- `VERIFY-P0-01` 至 `VERIFY-P0-10`

本轮不做：

- 不运行 `scripts/build_huiji_wiki.py`。
- 不恢复或执行 `src/huiji_wiki/builder.py`、`src/huiji_wiki/media_upload.py` 的写入链路。
- 不覆盖 Wiki MySQL 表。
- 不上传、删除、迁移或重命名 MinIO 对象。
- 不创建、删除、重建或切换 Milvus collection。
- 不修改 RAG 问答链路、向量化链路或聊天前端输出格式。
- 不接入 Live2D 真播放器。
- 不接入具体 ReactBits 动效组件。
- 不实现 P2 项。

## 2. 文件结构

### 2.1 Gate 与验收记录

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/docs/wiki-rag-contract-record.md`  
  记录 RAG 线程确认的 MinIO 协议、processed artifacts build_version、Milvus collection、可消费 source/media 字段和 Wiki 执行许可。

### 2.2 Backend / API / Repository

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/models.py`  
  保持 Wiki 数据模型到 API DTO 的 camelCase 转换，补齐媒体、关系、链接字段序列化。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`  
  只读读取当前 Docker MySQL 中的 Wiki 表，禁止 P0 路径执行 schema 写入或 replace 操作。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`  
  明确 `categories`、`pages`、`page detail`、`routes/resolve`、`search` 的 response schema。
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`  
  保持 `/api/wiki/*` 路由只读，修正错误态、route resolve fallback 和本地路径防护。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`

### 2.3 Read-Only Verification

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/verify_huiji_wiki_e2e.py`  
  只请求 Wiki API 和抽样检查 HTTP 媒体 URL，不写任何数据库、对象存储或索引。
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_e2e_script.py`

### 2.4 Frontend API / Route / Entry Points

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/wiki.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/Sidebar.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.test.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.wiki.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.wiki.test.tsx`

### 2.5 Frontend Wiki Workspace

- Replace: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.tsx`
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
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageIndex.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageInfo.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/WikiTemplates.test.tsx`

## 3. 强制验收门槛

| Specs 编号 | 实现位置 | 测试或验收 | 失败表现 |
|---|---|---|---|
| `GATE-P0-01` 至 `GATE-P0-05` | `docs/wiki-rag-contract-record.md` | 人工审查 RAG 线程确认记录；`rg -n "GATE-P0" docs/wiki-rag-contract-record.md` | 没有 RAG 确认记录就开始改代码。 |
| `DATA-P0-01` 至 `DATA-P0-10` | `src/huiji_wiki/repository.py`, `backend/wiki.py` | 代码审查 + `pytest tests/test_huiji_wiki_repository.py -q` | Wiki 代码写 MySQL、MinIO、Milvus 或 processed artifacts，或直接扫 MinIO 反推页面资源。 |
| `MEDIA-P0-01` 至 `MEDIA-P0-10` | `backend/wiki.py`, `src/huiji_wiki/models.py`, `scripts/verify_huiji_wiki_e2e.py` | `pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_e2e_script.py -q` + 真实 URL 抽样 | API 返回本地路径、非 HTTP URL、消费未进入 `media_assets.jsonl` 的 MinIO 对象，或默认铺开大量语音。 |
| `API-P0-01` 至 `API-P0-11` | `backend/wiki.py`, `backend/wiki_schemas.py`, `src/huiji_wiki/repository.py` | `pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q` | 字段缺失、camelCase 不匹配、resolve 抛出前端无法处理的异常，或 payload 泄露 `local_relpath`。 |
| `FRONTEND-P0-01` 至 `FRONTEND-P0-12` | `frontend/react-app/src/App.tsx`, `frontend/react-app/src/components/wiki/**` | `npm run test -- --run src/components/wiki src/App.wiki.test.tsx` + `/wiki` 浏览器验收 | `/wiki` 进入三屏 snap，四区缺失，图片失败导致布局跳动。 |
| `TEMPLATE-P0-01` 至 `TEMPLATE-P0-10` | `frontend/react-app/src/components/wiki/templates/**` | `npm run test -- --run src/components/wiki/templates` | 角色媒体窗口太小、Live2D 入口缺失、raw JSON 直接暴露，或语音默认批量展开。 |
| `LINK-P0-01` 至 `LINK-P0-05` | `frontend/react-app/src/components/wiki/KeywordText.tsx` | `npm run test -- --run src/components/wiki/KeywordText.test.tsx` | 同段多关键词丢失、重复关键词只渲染一次、空 route 生成空链接。 |
| `RAGLINK-P0-01` 至 `RAGLINK-P0-05` | `backend/wiki.py`, `frontend/react-app/src/api/wiki.ts` | route resolve 测试 + 代码审查确认未改 `src/rag/**` | Wiki 修复依赖 RAG 入库或修改 RAG 检索代码。 |
| `ANIMATION-P0-01` 至 `ANIMATION-P0-03` | `frontend/react-app/src/components/wiki/**`, `frontend/react-app/src/types/wiki.ts` | 代码审查：无 ReactBits 组件名硬编码，保留 `animationProfile/templateGroup/themeToken` | 动效组件侵入业务，或动效阻断数据面。 |
| `VERIFY-P0-01` 至 `VERIFY-P0-10` | `scripts/verify_huiji_wiki_e2e.py`, `tests/test_huiji_wiki_e2e_script.py`, `docs/wiki-rag-contract-record.md` | 只读 E2E 脚本 + 手动真实数据验收记录 | 只靠 mock 单测宣称完成，验收脚本写数据，或未验证 `media_assets.jsonl` 与 MinIO 的引用命中关系。 |

## 4. 执行步骤

### Task 0: RAG 协调门槛记录

**对应 specs:** `GATE-P0-01` 至 `GATE-P0-05`, `VERIFY-P0-01`

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/docs/wiki-rag-contract-record.md`

**Interfaces:**
- Consumes: RAG 线程已确认的 MinIO 协议、processed artifacts build_version、Milvus collection、source/media 字段。
- Produces: 后续任务开始条件文档。

- [ ] **Step 1: 创建门槛记录文档**

写入以下结构：

```markdown
# Wiki / RAG Shared Contract Record

日期：2026-07-08
状态：RAG 共享契约已确认

## GATE-P0 确认

- [x] `GATE-P0-01`: MinIO bucket、object prefix、object key 和 HTTP URL 规则稳定。
- [x] `GATE-P0-02`: processed artifacts build_version 与 `media_assets.jsonl` 字段契约稳定。
- [x] `GATE-P0-03`: Milvus 当前 collection 已确认；Wiki 不读取 Milvus。
- [x] `GATE-P0-04`: Wiki 可只读消费媒体 URL 和 source/entity 字段，不影响问答链路。
- [x] `GATE-P0-05`: Wiki plan 获准基于已确认共享契约进入代码落地。

## RAG 确认内容

MinIO:
- bucket: `reverse1999-assets`
- public_base_url: `http://127.0.0.1:9002`
- object_prefix: `reverse1999`
- url_rule: `http://127.0.0.1:9002/reverse1999-assets/reverse1999/<asset_type>/<sha-prefix>/<sha>.<ext>`

Processed artifacts:
- build_version: `dev`
- path: `D:/PycharmProjects/nlp/LangChain/1999Search/data/processed/huiji/dev`
- required_files: `parent_blocks.jsonl`, `child_blocks.jsonl`, `media_assets.jsonl`
- parent_count: `8246`
- child_count: `16010`
- media_count: `15758`
- media index source of truth: `data/processed/huiji/dev/media_assets.jsonl`

Milvus:
- active_collection: `text_child_bge_m3_v3`
- wiki_access: `none`

Media display policy:
- default visible: `image`, `portrait`, `skill`
- gated visible: `voice` only in folded voice panel, dedicated tab, or explicit voice entry
- gated visible: `video` only in video panel, dedicated tab, or explicit video entry
- ignored: MinIO objects that are not referenced by `media_assets.jsonl`

API payload whitelist:
- allowed media fields: `media_id`, `asset_id`, `asset_type`, `mime`, `url`, `title`, `alt`, `role`, `attach_policy`, `child_id`, `parent_id`, `panel_group`, `sort_order`, `duration_ms`
- forbidden media field: `local_relpath`

Wiki allowed actions:
- read MySQL wiki_* tables through repository/API
- read API-safe HTTP media URL
- read `data/processed/huiji/dev/parent_blocks.jsonl`
- read `data/processed/huiji/dev/child_blocks.jsonl`
- read `data/processed/huiji/dev/media_assets.jsonl`
- render `/wiki`
- run read-only verification

Wiki forbidden actions:
- rebuild Milvus
- upload/delete/migrate MinIO object
- overwrite Wiki MySQL tables
- rerun Wiki builder
- scan MinIO directly to infer page resources
- modify RAG retrieval/vectorization/chat output
```

- [ ] **Step 2: 审查门槛是否全部满足**

Run:

```powershell
rg -n "GATE-P0|build_version|active_collection|reverse1999-assets|forbidden" D:\PycharmProjects\nlp\LangChain\1999Search\docs\wiki-rag-contract-record.md
```

Expected:

```text
能看到 5 个已勾选的 GATE-P0 条目、MinIO 协议、build_version `dev`、active_collection `text_child_bge_m3_v3`、media display policy 和 forbidden actions。
```

- [ ] **Step 3: 停止条件**

如果 `docs/wiki-rag-contract-record.md` 没有记录以上已确认值，则停止执行 Task 1 及后续任务，向用户报告缺失项，不改代码。

### Task 1: 后端只读 API 契约

**对应 specs:** `DATA-P0-01` 至 `DATA-P0-10`, `MEDIA-P0-01` 至 `MEDIA-P0-10`, `API-P0-01` 至 `API-P0-11`, `RAGLINK-P0-01` 至 `RAGLINK-P0-05`

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/models.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`

**Interfaces:**
- Consumes: existing `MySQLWikiRepository`, `wiki_pages`, `wiki_media_links`, `wiki_aliases`, `wiki_link_spans`, `wiki_categories`, `wiki_relations`.
- Produces:
  - `GET /api/wiki/categories -> { categories: WikiCategoryItem[] }`
  - `GET /api/wiki/pages?category=&q=&type=&limit=&cursor= -> { items: WikiPageListItem[], nextCursor: string | null }`
  - `GET /api/wiki/pages/{page_id} -> WikiPageDetailResponse`
  - `GET /api/wiki/routes/resolve?source_id=&entity_id=&title= -> { route: string | null, query: string }`
  - `GET /api/wiki/search?q= -> WikiPageListResponse`

- [ ] **Step 1: 写 API contract 失败测试**

Create `tests/test_huiji_wiki_api.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import wiki


class FakeRepo:
    def list_categories(self):
        return [type("Category", (), {"to_json": lambda self: {"key": "character", "label": "角色", "count": 1}})()]

    def list_pages(self, category="", q="", page_type="", limit=30, cursor=""):
        page = type(
            "Page",
            (),
            {
                "page_id": "char:3074",
                "page_type": "character",
                "title": "爱兹拉",
                "subtitle": "Ezra Theodore",
                "category": "角色",
                "route": "/wiki/char/3074",
                "content_json": {"summary": "角色摘要"},
            },
        )()
        return [page], None

    def first_media_url_by_page(self, page_ids):
        return {"char:3074": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/asset.webp"}

    def get_page_detail(self, page_id):
        return {
            "pageId": page_id,
            "pageType": "character",
            "title": "爱兹拉",
            "subtitle": "Ezra Theodore",
            "category": "角色",
            "route": "/wiki/char/3074",
            "sourcePageid": 3074,
            "sourceTitle": "Data:Char/3074.json",
            "content": {"summary": "角色摘要"},
            "mediaLinks": [
                {
                    "pageId": page_id,
                    "sectionKey": "media",
                    "mediaId": "media:sha1:abc",
                    "mediaRole": "portrait",
                    "displayOrder": 1,
                    "objectKey": "reverse1999/image/aa/asset.webp",
                    "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/asset.webp",
                    "assetType": "image",
                    "mime": "image/webp",
                    "title": "立绘",
                    "sha1": "abc",
                    "width": 900,
                    "height": 1400,
                }
            ],
            "relations": [],
            "linkSpans": [
                {
                    "pageId": page_id,
                    "sectionKey": "summary",
                    "text": "维尔汀",
                    "targetRoute": "/wiki/char/3001",
                    "confidence": 0.95,
                }
            ],
        }

    def resolve_route(self, entity_id="", source_id="", title=""):
        if entity_id == "3074" or title == "爱兹拉":
            return "/wiki/char/3074"
        return None


def make_client(monkeypatch):
    app = FastAPI()
    app.include_router(wiki.router)
    monkeypatch.setattr(wiki, "get_wiki_repository", lambda: FakeRepo())
    return TestClient(app)


def test_pages_return_camel_case_thumbnail_and_summary(monkeypatch):
    client = make_client(monkeypatch)
    body = client.get("/api/wiki/pages?category=character").json()
    assert body["items"][0]["pageId"] == "char:3074"
    assert body["items"][0]["thumbnail"].startswith("http://127.0.0.1:9002/")
    assert body["items"][0]["summary"] == "角色摘要"


def test_detail_rejects_local_path_leak(monkeypatch):
    client = make_client(monkeypatch)
    body = client.get("/api/wiki/pages/char:3074").json()
    serialized = str(body)
    assert "D:\\" not in serialized
    assert "C:\\" not in serialized
    assert "local_relpath" not in serialized
    assert body["mediaLinks"][0]["url"].startswith("http://")


def test_detail_uses_media_whitelist(monkeypatch):
    client = make_client(monkeypatch)
    body = client.get("/api/wiki/pages/char:3074").json()
    allowed = {
        "pageId",
        "sectionKey",
        "mediaId",
        "mediaRole",
        "displayOrder",
        "objectKey",
        "url",
        "assetType",
        "mime",
        "title",
        "sha1",
        "width",
        "height",
    }
    assert set(body["mediaLinks"][0]).issubset(allowed)


def test_route_resolve_falls_back_to_query(monkeypatch):
    client = make_client(monkeypatch)
    found = client.get("/api/wiki/routes/resolve?entity_id=3074").json()
    missing = client.get("/api/wiki/routes/resolve?title=不存在").json()
    assert found == {"route": "/wiki/char/3074", "query": "3074"}
    assert missing == {"route": None, "query": "不存在"}
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py -q
```

Expected:

```text
测试在当前缺失字段或 schema 不匹配处失败；如果全部通过，记录为现有后端契约已满足。
```

- [ ] **Step 3: 修正后端 DTO 与路由**

实现要求：

```text
backend/wiki.py:
- /categories 返回 categories。
- /pages 返回 pageId/pageType/title/subtitle/category/route/thumbnail/summary/nextCursor。
- /pages/{page_id} 返回 content/mediaLinks/relations/linkSpans/sourcePageid/sourceTitle。
- /routes/resolve 未命中时返回 route=null 与 query，不抛 500。
- 不访问 Milvus。

src/huiji_wiki/repository.py:
- P0 ensure_schema 保持 no-op 或只读检查，不执行 CREATE/DROP/REPLACE/TRUNCATE。
- 所有读取异常降级为空列表或 404，不触发写入修复。
- media url 必须是 HTTP URL；object_key 可保留为调试字段。
- 不直接遍历 MinIO 反推页面资源；页面媒体只来自 MySQL 或 `data/processed/huiji/dev/media_assets.jsonl` 的稳定映射。
- 不把 `local_relpath` 序列化给 API payload。
```

- [ ] **Step 4: 补 repository 只读测试**

Create `tests/test_huiji_wiki_repository.py`:

```python
from src.huiji_wiki.repository import MySQLWikiRepository


class DummyConfig:
    class mysql:
        host = "127.0.0.1"
        port = 3306
        user = "root"
        password = ""
        database = "reverse1999_wiki"
        charset = "utf8mb4"


def test_ensure_schema_is_noop_for_p0(monkeypatch):
    repo = MySQLWikiRepository(DummyConfig())
    called = {"connect": False}

    def fail_connect():
        called["connect"] = True
        raise AssertionError("ensure_schema must not connect or write in P0")

    monkeypatch.setattr(repo, "_connect", fail_connect)
    repo.ensure_schema()
    assert called["connect"] is False
```

- [ ] **Step 5: 运行后端测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q
```

Expected:

```text
全部通过。
```

### Task 2: 只读 Wiki E2E 验收脚本

**对应 specs:** `MEDIA-P0-03` 至 `MEDIA-P0-10`, `VERIFY-P0-02` 至 `VERIFY-P0-10`

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/verify_huiji_wiki_e2e.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_e2e_script.py`

**Interfaces:**
- Consumes: running FastAPI base URL, Wiki API JSON payload.
- Produces: exit code 0 for safe payload and reachable sampled HTTP media; non-zero for local path leaks or missing required fields.

- [ ] **Step 1: 写脚本单测**

Create `tests/test_huiji_wiki_e2e_script.py`:

```python
from scripts.verify_huiji_wiki_e2e import (
    find_local_path_leaks,
    first_media_url,
    validate_detail_payload,
    validate_media_asset_minio_coverage,
)


def test_find_local_path_leaks_detects_windows_paths():
    payload = {"mediaLinks": [{"url": "D:\\assets\\bad.png"}]}
    leaks = find_local_path_leaks(payload)
    assert leaks


def test_validate_detail_payload_accepts_http_media():
    payload = {
        "pageId": "char:3074",
        "title": "爱兹拉",
        "mediaLinks": [{"url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/a.webp"}],
    }
    validate_detail_payload(payload)
    assert first_media_url(payload).startswith("http://")


def test_validate_media_asset_minio_coverage_rejects_missing_key():
    media_rows = [{"object_key": "reverse1999/image/aa/missing.webp", "url": "http://127.0.0.1/x"}]
    minio_keys = set()
    try:
        validate_media_asset_minio_coverage(media_rows, minio_keys)
    except ValueError as exc:
        assert "missing object_key" in str(exc)
    else:
        raise AssertionError("expected missing object_key failure")
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_e2e_script.py -q
```

Expected:

```text
因为脚本函数尚不存在而失败。
```

- [ ] **Step 3: 实现只读脚本**

Create `scripts/verify_huiji_wiki_e2e.py` with these exported functions and CLI behavior:

```python
LOCAL_PATH_MARKERS = ("D:\\", "C:\\", "local_relpath")


def find_local_path_leaks(payload: object) -> list[str]:
    text = repr(payload)
    return [marker for marker in LOCAL_PATH_MARKERS if marker in text]


def validate_detail_payload(payload: dict) -> None:
    for key in ("pageId", "title", "mediaLinks"):
        if key not in payload:
            raise ValueError(f"missing required key: {key}")
    leaks = find_local_path_leaks(payload)
    if leaks:
        raise ValueError(f"local path leak detected: {', '.join(leaks)}")


def first_media_url(payload: dict) -> str:
    for item in payload.get("mediaLinks", []):
        url = str(item.get("url", ""))
        if url.startswith("http://") or url.startswith("https://"):
            return url
    return ""


def validate_media_asset_minio_coverage(media_rows: list[dict], minio_keys: set[str]) -> None:
    missing = sorted({str(row.get("object_key") or "") for row in media_rows if row.get("object_key")} - minio_keys)
    if missing:
        raise ValueError(f"missing object_key in MinIO: {missing[:5]}")
```

CLI requirements:

```text
--base-url defaults to http://127.0.0.1:8000
--page-id optional; absent means script uses first item from /api/wiki/pages
--check-media performs GET or HEAD against first media URL
--media-assets defaults to data/processed/huiji/dev/media_assets.jsonl
--minio-object-list optionally points to a newline-delimited object_key inventory generated by a separate read-only MinIO list command
--check-minio-coverage verifies every media_assets object_key exists in --minio-object-list
Output includes checked pageId, media URL, leak count, and status.
Script must not import pymysql, minio, pymilvus, or any builder module.
```

- [ ] **Step 4: 运行脚本单测**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_e2e_script.py -q
```

Expected:

```text
全部通过。
```

### Task 3: 前端 Wiki DTO、API client 与入口

**对应 specs:** `API-P0-01` 至 `API-P0-10`, `FRONTEND-P0-01` 至 `FRONTEND-P0-02`, `RAGLINK-P0-02` 至 `RAGLINK-P0-05`

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/wiki.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/Sidebar.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.test.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.wiki.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.wiki.test.tsx`

**Interfaces:**
- Consumes: `/api/wiki/*` responses from Task 1.
- Produces: typed frontend API functions and three `/wiki` entry points.

- [ ] **Step 1: 写 API client 测试**

Create `frontend/react-app/src/api/wiki.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { fetchWikiPageDetail, resolveWikiRoute } from './wiki'

describe('wiki api client', () => {
  it('fetches page detail with mediaLinks', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      pageId: 'char:3074',
      pageType: 'character',
      title: '爱兹拉',
      content: { summary: '角色摘要' },
      mediaLinks: [{ url: 'http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/aa/a.webp' }],
      relations: [],
      linkSpans: [],
    }))))
    const detail = await fetchWikiPageDetail('char:3074')
    expect(detail.mediaLinks[0].url).toMatch(/^http:/)
  })

  it('resolves route fallback without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ route: null, query: '爱兹拉' }))))
    await expect(resolveWikiRoute({ title: '爱兹拉' })).resolves.toEqual({ route: null, query: '爱兹拉' })
  })
})
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/api/wiki.test.ts
```

Expected:

```text
缺失 fetchWikiPageDetail 或 resolveWikiRoute 时失败。
```

- [ ] **Step 3: 补齐 `types/wiki.ts` 和 `api/wiki.ts`**

Required exported types:

```ts
export interface WikiMediaLink {
  pageId: string
  sectionKey?: string
  mediaId?: string
  mediaRole?: string
  displayOrder?: number
  objectKey?: string
  url: string
  assetType?: string
  mime?: string
  title?: string
  sha1?: string
  width?: number
  height?: number
}

export interface WikiPageDetail {
  pageId: string
  pageType: string
  title: string
  subtitle?: string
  category?: string
  route?: string
  sourcePageid?: number | string
  sourceTitle?: string
  content?: Record<string, unknown>
  mediaLinks: WikiMediaLink[]
  relations: WikiRelation[]
  linkSpans: WikiLinkSpan[]
}
```

Required exported API functions:

```ts
fetchWikiCategories(): Promise<WikiCategoryItem[]>
fetchWikiPages(params: WikiPageQuery): Promise<WikiPageListResponse>
fetchWikiPageDetail(pageId: string): Promise<WikiPageDetail>
resolveWikiRoute(params: { sourceId?: string; entityId?: string; title?: string }): Promise<WikiRouteResolveResponse>
searchWikiPages(q: string): Promise<WikiPageListResponse>
```

- [ ] **Step 4: 写入口测试**

Create `frontend/react-app/src/App.wiki.test.tsx` and `frontend/react-app/src/components/TopNav.wiki.test.tsx`:

```ts
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('/wiki route', () => {
  it('renders WikiShell outside the three-screen snap flow', () => {
    window.history.pushState({}, '', '/wiki')
    render(<App />)
    expect(screen.getByTestId('wiki-shell')).toBeInTheDocument()
  })
})
```

```ts
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TopNav } from './TopNav'

describe('wiki nav entry', () => {
  it('contains a /wiki link', () => {
    render(<TopNav />)
    expect(screen.getByRole('link', { name: /wiki/i })).toHaveAttribute('href', '/wiki')
  })
})
```

- [ ] **Step 5: 运行前端入口测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/api/wiki.test.ts src/App.wiki.test.tsx src/components/TopNav.wiki.test.tsx
```

Expected:

```text
全部通过。
```

### Task 4: Wiki 四区工作区

**对应 specs:** `FRONTEND-P0-03` 至 `FRONTEND-P0-12`, `ANIMATION-P0-01` 至 `ANIMATION-P0-03`

**Files:**
- Replace: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageIndex.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiReader.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageInfo.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/wikiLayout.ts`
- Create tests listed in section 2.5.

**Interfaces:**
- Consumes: `WikiCategoryItem`, `WikiPageListItem`, `WikiPageDetail`.
- Produces: `CategoryRail(hidden) | PageIndex | WikiReader | PageInfo` layout.

- [ ] **Step 1: 写布局与列表测试**

Create `WikiShell.test.tsx`, `CategoryRail.test.tsx`, `PageIndex.test.tsx`, `PageInfo.test.tsx` with these assertions:

```ts
expect(screen.getByTestId('wiki-category-rail')).toBeInTheDocument()
expect(screen.getByTestId('wiki-page-index')).toBeInTheDocument()
expect(screen.getByTestId('wiki-reader')).toBeInTheDocument()
expect(screen.getByTestId('wiki-page-info')).toBeInTheDocument()
```

```ts
expect(screen.getByTestId('wiki-layout')).toHaveStyle({
  gridTemplateColumns: expect.stringContaining('minmax'),
})
```

```ts
expect(screen.getByRole('button', { name: '角色' })).toBeInTheDocument()
expect(screen.getByPlaceholderText('搜索页面')).toBeInTheDocument()
expect(screen.getByText('1 image mapped')).toBeInTheDocument()
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/components/wiki/WikiShell.test.tsx src/components/wiki/CategoryRail.test.tsx src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx
```

Expected:

```text
当前临时 WikiShell 缺少四区结构，测试失败。
```

- [ ] **Step 3: 实现四区组件**

Required layout constants in `wikiLayout.ts`:

```ts
export const WIKI_LAYOUT_COLUMNS = 'minmax(0, 0.52fr) minmax(320px, 0.52fr) minmax(560px, 1.7fr) minmax(220px, 0.38fr)'
export const WIKI_RAIL_HOVER_DELAY_MS = 220
```

Required test ids:

```text
wiki-shell
wiki-layout
wiki-category-rail
wiki-page-index
wiki-reader
wiki-page-info
```

Implementation requirements:

```text
CategoryRail 平时隐藏在左边界；鼠标贴近左边界或 hover 延迟后唤出。
PageIndex 常驻显示，包含搜索输入、分类状态、标题、副标题、类型、缩略图、摘要。
WikiReader 占最大空间，负责选择模板。
PageInfo 为窄右栏，显示来源、媒体数、关系数、链接数、route 和 outline。
API/MySQL 失败时显示 Wiki 错误态，不影响主站其他页面。
MinIO 图片不可用时使用固定尺寸占位。
```

- [ ] **Step 4: 运行工作区测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/components/wiki
```

Expected:

```text
Wiki 工作区相关测试通过。
```

### Task 5: 页面模板与 CharacterMediaStage

**对应 specs:** `TEMPLATE-P0-01` 至 `TEMPLATE-P0-10`, `MEDIA-P0-06`, `MEDIA-P0-08`, `MEDIA-P0-10`

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/PsychubePage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/StoryPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/GenericWikiPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/WikiTemplates.test.tsx`

**Interfaces:**
- Consumes: `WikiPageDetail.mediaLinks`, `WikiPageDetail.content`, `WikiPageDetail.pageType`.
- Produces: `CharacterPage`, `PsychubePage`, `StoryPage`, `GenericWikiPage`.

- [ ] **Step 1: 写模板测试**

Create template tests asserting:

```ts
expect(screen.getByRole('button', { name: '立绘' })).toBeInTheDocument()
expect(screen.getByRole('button', { name: 'Live2D' })).toBeInTheDocument()
expect(screen.getByTestId('character-media-stage')).toHaveStyle({ minHeight: '520px' })
expect(screen.getByText('Live2D 暂不可用')).toBeInTheDocument()
```

For generic page:

```ts
expect(screen.queryByText(/"raw"/)).not.toBeInTheDocument()
expect(screen.getByText('来源')).toBeInTheDocument()
```

For voice media:

```ts
expect(screen.getByRole('button', { name: '语音' })).toBeInTheDocument()
expect(screen.queryByTestId('voice-list-expanded')).not.toBeInTheDocument()
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/components/wiki/templates
```

Expected:

```text
模板组件尚不存在，测试失败。
```

- [ ] **Step 3: 实现模板**

Implementation requirements:

```text
WikiReader 根据 pageType 选择 CharacterPage/PsychubePage/StoryPage/GenericWikiPage。
CharacterMediaStage 将立绘、Live2D、皮肤放在同一窗口，用按钮切换。
Live2D 未就绪时显示同尺寸 fallback，不隐藏入口。
真实 URL 存在时显示大图，不只显示缩略图。
fallback 不改变媒体窗口尺寸。
PsychubePage 展示大图、基础资料、效果或故事字段；缺字段显示稳定空状态。
StoryPage 展示封面或章节视觉、基础资料、正文或章节字段；缺字段显示稳定空状态。
GenericWikiPage 展示整理后的标题、来源、摘要或结构化内容，不直接暴露 Data namespace 原始 JSON。
voice 资源只进入折叠面板、独立 Tab 或明确入口；页面加载时不批量展开语音列表。
```

- [ ] **Step 4: 运行模板测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/components/wiki/templates
```

Expected:

```text
全部通过。
```

### Task 6: 关键词链接与 route fallback

**对应 specs:** `LINK-P0-01` 至 `LINK-P0-05`, `RAGLINK-P0-02` 至 `RAGLINK-P0-05`

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.test.tsx`

**Interfaces:**
- Consumes: `text: string`, `spans: WikiLinkSpan[]`.
- Produces: linked React nodes using only API-provided spans.

- [ ] **Step 1: 写关键词测试**

Create `KeywordText.test.tsx`:

```ts
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { KeywordText } from './KeywordText'

describe('KeywordText', () => {
  it('renders multiple and repeated spans from API data', () => {
    render(
      <KeywordText
        text="维尔汀见到维尔汀和十四行诗。"
        spans={[
          { text: '维尔汀', targetRoute: '/wiki/char/3001', confidence: 0.95 },
          { text: '维尔汀', targetRoute: '/wiki/char/3001', confidence: 0.95 },
          { text: '十四行诗', targetRoute: '/wiki/char/3002', confidence: 0.95 },
        ]}
      />,
    )
    expect(screen.getAllByRole('link', { name: '维尔汀' })).toHaveLength(2)
    expect(screen.getByRole('link', { name: '十四行诗' })).toHaveAttribute('href', '/wiki/char/3002')
  })

  it('does not create empty links for missing routes', () => {
    render(<KeywordText text="未知实体" spans={[{ text: '未知实体', targetRoute: '', confidence: 0.2 }]} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('未知实体')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/components/wiki/KeywordText.test.tsx
```

Expected:

```text
KeywordText 缺失时失败。
```

- [ ] **Step 3: 实现 KeywordText**

Implementation requirements:

```text
只使用 API 提供的 spans。
同一段文本多个关键词都能渲染。
重复关键词按 span 次数渲染，不只匹配第一个。
有 targetRoute 时渲染蓝色链接。
缺 targetRoute 时降级为普通文本或搜索 fallback，不生成空 href。
```

- [ ] **Step 4: 运行关键词测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/components/wiki/KeywordText.test.tsx
```

Expected:

```text
全部通过。
```

### Task 7: 全链路只读验收

**对应 specs:** 所有 P0 条目，尤其 `VERIFY-P0-02` 至 `VERIFY-P0-10`

**Files:**
- Modify only if needed: `D:/PycharmProjects/nlp/LangChain/1999Search/docs/wiki-rag-contract-record.md`

**Interfaces:**
- Consumes: completed Task 0-6.
- Produces: final acceptance record in the task output.

- [ ] **Step 1: 运行后端测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_e2e_script.py -q
```

Expected:

```text
全部通过。
```

- [ ] **Step 2: 运行前端测试**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/api/wiki.test.ts src/App.wiki.test.tsx src/components/TopNav.wiki.test.tsx src/components/wiki
```

Expected:

```text
全部通过。
```

- [ ] **Step 3: 运行前端构建**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run build
```

Expected:

```text
TypeScript 编译通过，Vite build 成功。
```

- [ ] **Step 4: 生成只读 MinIO object_key 清单**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
$env:MINIO_ACCESS_KEY="minioadmin"
$env:MINIO_SECRET_KEY="minioadmin"
@'
import os
from pathlib import Path
from minio import Minio

client = Minio("127.0.0.1:9002", access_key=os.environ["MINIO_ACCESS_KEY"], secret_key=os.environ["MINIO_SECRET_KEY"], secure=False)
out = Path(os.environ["TEMP"]) / "reverse1999_minio_object_keys.txt"
with out.open("w", encoding="utf-8") as f:
    for obj in client.list_objects("reverse1999-assets", prefix="reverse1999/", recursive=True):
        f.write(obj.object_name + "\n")
print(out)
'@ | python -
```

Expected:

```text
生成 `%TEMP%\reverse1999_minio_object_keys.txt`。该命令只读 MinIO，不上传、不删除、不迁移对象，也不写 `data/processed`。
```

- [ ] **Step 5: 运行只读 Wiki E2E**

Run after backend is running:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --check-media --media-assets data/processed/huiji/dev/media_assets.jsonl --minio-object-list "$env:TEMP\reverse1999_minio_object_keys.txt" --check-minio-coverage
```

Expected:

```text
输出真实 pageId、至少一个 HTTP media URL、local path leak count 为 0、missing object_key count 为 0。
```

- [ ] **Step 6: 浏览器手动验收**

Manual checks:

```text
/wiki 独立打开，不进入三屏 scroll snap。
TopNav、Sidebar、资料页日历入口都能进入 /wiki。
CategoryRail 平时隐藏，鼠标贴近左边界或 hover 延迟后唤出。
PageIndex 显示真实条目、缩略图、页面类型、副标题和摘要。
WikiReader 打开至少一个真实角色页。
主媒体区域显示真实 MinIO 图片；失败时固定尺寸占位。
Live2D 切换入口存在，播放器未接入时同窗口 fallback。
语音资源只在折叠面板、独立 Tab 或明确入口展示，不在页面加载时批量铺开。
同段多关键词和重复关键词可点击或稳定降级。
PageInfo 显示来源、媒体数、关系数、链接数、route 和 outline。
```

## 5. 可选任务（P1，只在 P0 通过后执行）

- `API-P1-01`：完善 alias fallback、分页游标、分类排序和搜索排序。执行条件：P0 API 与真实页面验收全部通过。
- `API-P1-03`：增加 `/api/wiki/pages/by-route`。执行条件：前端需要从 route 直接刷新详情页。
- `FRONTEND-P1-01`：Category metadata 传递 `animationProfile`、`templateGroup`、`themeToken`。执行条件：用户明确指定第一组动效接入区域。
- `FRONTEND-P1-03`：移动端 PageIndex/Reader 优先布局。执行条件：桌面 P0 验收通过后再做移动端。
- `LINK-P1-02`：点击前 route resolve 校验。执行条件：真实数据中发现 targetRoute 缺失较多。
- `VERIFY-P1-03`：将 MinIO object_key 与 `media_assets.jsonl` 全量一致性检查做成定期巡检。执行条件：P0 的一次性覆盖检查已通过，并且后续需要长期监控。

## 6. Deferred / Out of Scope

- `DATA-P2-01` 至 `DATA-P2-03`：统一构建器、增量构建、构建任务 UI。
- `MEDIA-P2-01` 至 `MEDIA-P2-03`：CDN、权限策略、媒体中心、Live2D 资源包预加载。
- `API-P2-01` 至 `API-P2-02`：专用全文索引、后台编辑、版本管理。
- `FRONTEND-P2-01` 至 `FRONTEND-P2-02`：高级筛选、收藏、浏览历史、复杂响应式密度配置。
- `TEMPLATE-P2-01` 至 `TEMPLATE-P2-04`：关系图谱、完整 Live2D 播放器、媒体中心、高度定制动效。
- `RAGLINK-P2-01` 至 `RAGLINK-P2-03`：RAG 答案内嵌媒体、跳转具体段落、上下文返回栈。
- `ANIMATION-P2-01` 至 `ANIMATION-P2-03`：按 ReactBits 逐区接入动效。

## 7. 完成后自检表

### Gate

- [ ] `GATE-P0-01`: RAG 已确认 MinIO bucket、object prefix、object key 和 HTTP URL 规则稳定。
- [ ] `GATE-P0-02`: RAG 已确认 processed artifacts build_version 与 `media_assets.jsonl` 字段契约稳定。
- [ ] `GATE-P0-03`: RAG 已确认 Milvus collection 状态；Wiki 不读取 Milvus。
- [ ] `GATE-P0-04`: RAG 已确认 Wiki 可只读消费媒体 URL 和 source/entity 字段。
- [ ] `GATE-P0-05`: Wiki plan 获准进入代码落地。

### Data / Media / API

- [ ] `DATA-P0-01` 至 `DATA-P0-10`: 没有重跑 builder、覆盖 MySQL、上传 MinIO、重建 Milvus、写 processed artifacts 或直接扫描 MinIO 反推页面资源。
- [ ] `MEDIA-P0-01` 至 `MEDIA-P0-10`: API 和前端只使用 HTTP media URL，本地路径泄露为 0；未进入 `media_assets.jsonl` 的 MinIO 对象不展示；语音不默认批量展开。
- [ ] `API-P0-01` 至 `API-P0-11`: categories、pages、detail、resolve、search API 可用，字段为 camelCase，且 payload 不泄露 `local_relpath`。

### Frontend / Template / Link

- [ ] `FRONTEND-P0-01` 至 `FRONTEND-P0-12`: `/wiki` 独立四区工作区、三个入口、错误态、固定尺寸图片 fallback 可用。
- [ ] `TEMPLATE-P0-01` 至 `TEMPLATE-P0-10`: 四类模板入口、角色大媒体窗口、Live2D fallback、通用页无 raw JSON 暴露，语音通过折叠面板/独立 Tab/明确入口展示。
- [ ] `LINK-P0-01` 至 `LINK-P0-05`: 多关键词、重复关键词、targetRoute、空 route 降级全部通过。
- [ ] `RAGLINK-P0-01` 至 `RAGLINK-P0-05`: Wiki 保留 route/resolve，不修改 RAG 链路。
- [ ] `ANIMATION-P0-01` 至 `ANIMATION-P0-03`: 未写死 ReactBits 组件名，保留动效挂点和 metadata 字段。

### Verification

- [ ] `VERIFY-P0-01` 至 `VERIFY-P0-10`: 单测、构建、只读 E2E、media_assets-MinIO 覆盖检查、浏览器真实数据验收全部有记录。
- [ ] P1 未执行项已标记为未执行或延期。
- [ ] P2 未进入执行范围。
