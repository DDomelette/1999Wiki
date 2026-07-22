# Huiji Wiki P0 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐灰机 Wiki 模块 P0 缺口，让真实灰机数据、共享 MinIO、MySQL、FastAPI 和 React `/wiki` 形成可验收的端到端链路。

**Architecture:** 本计划延续已落地的 Wiki 骨架，不重写整套模块。重点把媒体资产字段从 `MediaAsset` 贯通到 `wiki_media_links`、API 响应和前端图片渲染，同时补齐 Wiki build 的 MinIO 上传报告、PageIndex 搜索富卡片、布局比例、模板基础数据面、关键词多 span 渲染和真实数据验收门槛。

**Tech Stack:** Python 3, pytest, FastAPI, Pydantic, PyMySQL, MinIO, dataclasses, JSON/JSONL, React 18, TypeScript, Vite, Vitest, Testing Library.

---

## 1. 目标范围

### 1.1 依据

Specs:

```text
docs/superpowers/specs/2026-07-04-huiji-wiki-frontend-design.md
```

Plan 规范:

```text
docs/specs-and-plans-review-guide.md
```

旧 plan 参考:

```text
docs/superpowers/plans/2026-07-06-huiji-wiki-frontend.md
```

### 1.2 已落地基线

以下内容来自旧 plan，当前作为基线，不在本计划中重做：

- `FRONTEND-P0-01` `/wiki` 已独立于三屏滚轮结构。
- `FRONTEND-P0-02` TopNav 已有 Wiki 入口。
- `FRONTEND-P0-03` Sidebar 已有 Wiki 入口。
- `FRONTEND-P0-04` 日历页已有 `进入WIKI` 入口。
- `FRONTEND-P0-05` 三个入口均指向 `/wiki`。
- `FRONTEND-P0-06` `/wiki` 已有四区骨架。
- `FRONTEND-P0-08` `CategoryRail` 已实现左边界唤出。
- `FRONTEND-P0-09` 唤出延迟已抽出共享常量。
- `API-P0-01` MySQL 配置已加入。
- `API-P0-02` 至 `API-P0-06` Wiki API 路由已存在。
- `RAGLINK-P0-01` 至 `RAGLINK-P0-03` 基础边界已建立。
- `ANIMATION-P0-01` 当前未绑定具体 ReactBits 组件。

### 1.3 本轮强制完成的 P0

本计划主线只覆盖仍未完整落地或需要加强验收的 P0：

- `BUILD-P0-03`、`BUILD-P0-04`、`BUILD-P0-05`、`BUILD-P0-08`
- `MEDIA-P0-01` 至 `MEDIA-P0-09`
- `API-P0-07`、`API-P0-09`
- `FRONTEND-P0-07`、`FRONTEND-P0-10` 至 `FRONTEND-P0-15`
- `TEMPLATE-P0-01` 至 `TEMPLATE-P0-08`
- `LINK-P0-01` 至 `LINK-P0-04`
- `RAGLINK-P0-04`
- `ANIMATION-P0-02`

### 1.4 本轮不做

以下内容不进入执行步骤：

- ReactBits 具体动效组件接入。
- Live2D 真播放器。
- RAG 答案来源卡片和指定段落跳转。
- Wiki 后台管理、版本管理、增量构建 UI。
- CDN、私有 bucket、预签名 URL。

---

## 2. 文件结构

### Backend / Build

- Modify: `src/huiji_wiki/models.py`  
  扩展 `WikiMediaLink` 字段，保持 API camelCase 输出。
- Modify: `src/huiji_wiki/builder.py`  
  从 RAG `MediaAsset` 行补齐 `object_key`、`url`、`asset_type`、`mime`、`title`、`sha1`，并生成列表缩略图。
- Modify: `src/huiji_wiki/repository.py`  
  更新 MySQL schema、insert/select、in-memory repository detail，保证 media URL 进入 API。
- Create: `src/huiji_wiki/media_upload.py`  
  Wiki build 专用媒体上传报告，不重复定义 object key 规则。
- Modify: `scripts/build_huiji_wiki.py`  
  接入 MinIO 上传报告并打印审计摘要。
- Modify: `backend/wiki.py`  
  列表页 thumbnail 从页面媒体推导，错误态保持局部失败。
- Modify: `backend/wiki_schemas.py`  
  明确 `mediaLinks` 字段结构允许真实 URL 字段。

### Frontend

- Modify: `frontend/react-app/src/types/wiki.ts`  
  扩展媒体字段类型。
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`  
  增加搜索 state、空状态、not found 状态。
- Modify: `frontend/react-app/src/components/wiki/CategoryRail.tsx`  
  唤出宽度与 PageIndex 对齐。
- Modify: `frontend/react-app/src/components/wiki/PageIndex.tsx`  
  增加搜索框、缩略图、页面类型、摘要。
- Modify: `frontend/react-app/src/components/wiki/PageInfo.tsx`  
  增加来源、更新时间、媒体数、关系数、链接数、目录和 RAG route 信息。
- Modify: `frontend/react-app/src/components/wiki/KeywordText.tsx`  
  支持多 span、重复词和缺失目标 fallback。
- Modify: `frontend/react-app/src/components/wiki/templates/*.tsx`  
  补齐角色、心相、剧情、通用模板的 P0 数据面。
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`  
  使用真实 URL，Live2D 缺失时保持同窗口 fallback。

### Tests

- Modify: `tests/test_huiji_wiki_models.py`
- Modify: `tests/test_huiji_wiki_builder.py`
- Modify: `tests/test_huiji_wiki_repository.py`
- Modify: `tests/test_huiji_wiki_build_script.py`
- Modify: `tests/test_huiji_wiki_api.py`
- Create: `tests/test_huiji_wiki_media_upload.py`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/CategoryRail.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/PageIndex.test.tsx`
- Create: `frontend/react-app/src/components/wiki/PageInfo.test.tsx`
- Create: `frontend/react-app/src/components/wiki/KeywordText.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`
- Create: `frontend/react-app/src/components/wiki/templates/WikiTemplates.test.tsx`

---

## 3. 强制验收门槛

| Specs 编号 | 验收方式 |
|---|---|
| `MEDIA-P0-05` | API 响应中不存在 `D:\`、`C:\` 或 `local_relpath` 字段，媒体字段只返回 HTTP URL 或安全标识。 |
| `MEDIA-P0-06` | `GET /api/wiki/pages/{page_id}` 的 `mediaLinks[0].url` 可被前端 `<img>` 使用。 |
| `MEDIA-P0-07` | 重复运行 Wiki build 时同一 object key 被跳过，不覆盖冲突对象。 |
| `FRONTEND-P0-07` | 左分类唤出宽度等于条目列表宽度，右信息栏更窄，主阅读区 `flex: 1`。 |
| `FRONTEND-P0-11` | PageIndex 有搜索输入，输入 query 后调用 `/api/wiki/pages?q=...`。 |
| `FRONTEND-P0-12` | PageIndex 卡片展示标题、副标题、页面类型、缩略图、摘要。 |
| `TEMPLATE-P0-02` | 角色页媒体窗口大尺寸显示，真实 URL 时展示图片。 |
| `TEMPLATE-P0-04` | Live2D 入口存在，缺播放器时显示同尺寸 fallback。 |
| `LINK-P0-01` | 多个关键词都能变蓝并跳转。 |
| `LINK-P0-04` | 缺失目标 route 的关键词显示为普通文本或搜索 fallback。 |
| `RAGLINK-P0-04` | `routes/resolve` 失败时返回 `route: null` 和可搜索 `query`。 |
| 真实端到端 | 真实灰机数据 -> MinIO -> MySQL -> API -> React `/wiki`，至少一个角色或心相页面显示真实图片。 |

---

## 4. 执行步骤

### Task 1: 扩展 Wiki 媒体契约

**对应 specs:** `MEDIA-P0-03`、`MEDIA-P0-04`、`MEDIA-P0-05`、`MEDIA-P0-06`、`API-P0-07`

**Files:**

- Modify: `src/huiji_wiki/models.py`
- Modify: `src/huiji_wiki/builder.py`
- Modify: `src/huiji_wiki/repository.py`
- Modify: `backend/wiki_schemas.py`
- Modify: `tests/test_huiji_wiki_models.py`
- Modify: `tests/test_huiji_wiki_builder.py`
- Modify: `tests/test_huiji_wiki_repository.py`
- Modify: `tests/test_huiji_wiki_api.py`

- [ ] **Step 1: 写失败测试，证明 media link 必须带 URL 和安全字段**

在 `tests/test_huiji_wiki_models.py` 添加：

```python
def test_media_link_api_includes_safe_minio_fields():
    link = WikiMediaLink(
        page_id="char:3074",
        section_key="media",
        media_id="media:sha1:abc",
        media_role="portrait",
        display_order=0,
        fallback_media_id="",
        object_key="reverse1999/portrait/ab/abc.png",
        url="http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/ab/abc.png",
        asset_type="portrait",
        mime="image/png",
        title="爱兹拉立绘",
        sha1="abc",
    )

    api = link.to_api()

    assert api["objectKey"] == "reverse1999/portrait/ab/abc.png"
    assert api["url"].startswith("http://127.0.0.1:9002/")
    assert api["assetType"] == "portrait"
    assert "local" not in "".join(api.keys()).lower()
```

运行：

```powershell
python -m pytest tests/test_huiji_wiki_models.py::test_media_link_api_includes_safe_minio_fields -q
```

Expected: fail，因为 `WikiMediaLink` 当前没有这些字段。

- [ ] **Step 2: 扩展 `WikiMediaLink` dataclass**

在 `src/huiji_wiki/models.py` 中把 `WikiMediaLink` 扩展为：

```python
@dataclass(frozen=True)
class WikiMediaLink:
    page_id: str
    section_key: str
    media_id: str
    media_role: str
    display_order: int
    fallback_media_id: str = ""
    object_key: str = ""
    url: str = ""
    asset_type: str = ""
    mime: str = ""
    title: str = ""
    sha1: str = ""
    width: int = 0
    height: int = 0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_api(self) -> dict[str, Any]:
        return _camelize(self.to_json())

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "WikiMediaLink":
        return cls(
            page_id=str(row.get("page_id", "")),
            section_key=str(row.get("section_key", "")),
            media_id=str(row.get("media_id", "")),
            media_role=str(row.get("media_role", "")),
            display_order=int(row.get("display_order", 0) or 0),
            fallback_media_id=str(row.get("fallback_media_id", "")),
            object_key=str(row.get("object_key", "")),
            url=str(row.get("url", "")),
            asset_type=str(row.get("asset_type", "")),
            mime=str(row.get("mime", "")),
            title=str(row.get("title", "")),
            sha1=str(row.get("sha1", "")),
            width=int(row.get("width", 0) or 0),
            height=int(row.get("height", 0) or 0),
        )
```

- [ ] **Step 3: 更新 builder 媒体映射测试**

在 `tests/test_huiji_wiki_builder.py` 中让测试 media asset 包含：

```python
media_assets = [
    {
        "media_id": "media:sha1:abc",
        "sha1": "abc",
        "asset_type": "portrait",
        "mime": "image/png",
        "filename": "ezra.png",
        "title": "爱兹拉立绘",
        "object_key": "reverse1999/portrait/ab/abc.png",
        "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/ab/abc.png",
        "is_available": True,
    }
]
```

断言：

```python
assert dataset.media_links[0].url.startswith("http://127.0.0.1:9002/")
assert dataset.media_links[0].object_key == "reverse1999/portrait/ab/abc.png"
assert dataset.media_links[0].asset_type == "portrait"
```

运行：

```powershell
python -m pytest tests/test_huiji_wiki_builder.py -q
```

Expected: fail，因为 builder 尚未传递这些字段。

- [ ] **Step 4: 更新 `build_wiki_dataset()` 传递媒体字段**

在 `src/huiji_wiki/builder.py` 创建 `WikiMediaLink` 时使用：

```python
WikiMediaLink(
    page_id=page.page_id,
    section_key="media",
    media_id=str(media_id),
    media_role=role,
    display_order=len(media_links),
    fallback_media_id="",
    object_key=str(media.get("object_key", "")),
    url=str(media.get("url", "")),
    asset_type=str(media.get("asset_type", "")),
    mime=str(media.get("mime", "")),
    title=str(media.get("title") or media.get("filename") or ""),
    sha1=str(media.get("sha1", "")),
)
```

过滤规则：

```python
if not media or not bool(media.get("is_available", True)):
    continue
```

- [ ] **Step 5: 更新 MySQL schema 与 repository**

在 `src/huiji_wiki/repository.py` 的 `wiki_media_links` schema 中加入：

```sql
object_key VARCHAR(512) NOT NULL DEFAULT '',
url TEXT NOT NULL,
asset_type VARCHAR(64) NOT NULL DEFAULT '',
mime VARCHAR(128) NOT NULL DEFAULT '',
title VARCHAR(255) NOT NULL DEFAULT '',
sha1 VARCHAR(64) NOT NULL DEFAULT '',
width INT NOT NULL DEFAULT 0,
height INT NOT NULL DEFAULT 0
```

更新 insert 字段：

```sql
(page_id, section_key, media_id, media_role, display_order, fallback_media_id,
 object_key, url, asset_type, mime, title, sha1, width, height)
```

更新 select 字段：

```sql
SELECT page_id, section_key, media_id, media_role, display_order, fallback_media_id,
       object_key, url, asset_type, mime, title, sha1, width, height
FROM wiki_media_links WHERE page_id = %s ORDER BY display_order ASC
```

为已存在旧表增加迁移保护，在 MySQL repository 初始化时执行：

```python
def _ensure_media_link_columns(self, cur) -> None:
    required = {
        "object_key": "ALTER TABLE wiki_media_links ADD COLUMN object_key VARCHAR(512) NOT NULL DEFAULT ''",
        "url": "ALTER TABLE wiki_media_links ADD COLUMN url TEXT NOT NULL",
        "asset_type": "ALTER TABLE wiki_media_links ADD COLUMN asset_type VARCHAR(64) NOT NULL DEFAULT ''",
        "mime": "ALTER TABLE wiki_media_links ADD COLUMN mime VARCHAR(128) NOT NULL DEFAULT ''",
        "title": "ALTER TABLE wiki_media_links ADD COLUMN title VARCHAR(255) NOT NULL DEFAULT ''",
        "sha1": "ALTER TABLE wiki_media_links ADD COLUMN sha1 VARCHAR(64) NOT NULL DEFAULT ''",
        "width": "ALTER TABLE wiki_media_links ADD COLUMN width INT NOT NULL DEFAULT 0",
        "height": "ALTER TABLE wiki_media_links ADD COLUMN height INT NOT NULL DEFAULT 0",
    }
    cur.execute("SHOW COLUMNS FROM wiki_media_links")
    existing = {str(row["Field"] if isinstance(row, dict) else row[0]) for row in cur.fetchall()}
    for column, ddl in required.items():
        if column not in existing:
            cur.execute(ddl)
```

- [ ] **Step 6: 更新 API 测试，禁止本地路径并要求 URL**

在 `tests/test_huiji_wiki_api.py` 增加：

```python
def test_wiki_page_detail_returns_media_url_without_local_path(monkeypatch):
    repo = InMemoryWikiRepository()
    repo.replace_all(
        categories=[],
        pages=[WikiPage(page_id="char:1", page_type="character", title="角色", subtitle="", category="角色", route="/wiki/char/1", source_pageid=1, source_title="Data:Char/1.json", content_json={"summary": "x"}, updated_at="")],
        media_links=[WikiMediaLink(page_id="char:1", section_key="media", media_id="media:sha1:abc", media_role="portrait", display_order=0, url="http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/ab/abc.png", object_key="reverse1999/portrait/ab/abc.png", asset_type="portrait", mime="image/png", sha1="abc")],
        relations=[],
        aliases=[],
        link_spans=[],
    )
    monkeypatch.setattr("backend.wiki.get_wiki_repository", lambda: repo)

    response = TestClient(app).get("/api/wiki/pages/char:1")

    assert response.status_code == 200
    body = response.json()
    assert body["mediaLinks"][0]["url"].startswith("http://127.0.0.1:9002/")
    assert "D:\\" not in str(body)
```

运行：

```powershell
python -m pytest tests/test_huiji_wiki_models.py tests/test_huiji_wiki_builder.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py -q
```

Expected: all pass.

---

### Task 2: 接入 Wiki build 的 MinIO 上传报告

**对应 specs:** `MEDIA-P0-01`、`MEDIA-P0-02`、`MEDIA-P0-07`、`MEDIA-P0-08`、`BUILD-P0-08`

**Files:**

- Create: `src/huiji_wiki/media_upload.py`
- Modify: `scripts/build_huiji_wiki.py`
- Create: `tests/test_huiji_wiki_media_upload.py`
- Modify: `tests/test_huiji_wiki_build_script.py`

- [ ] **Step 1: 写上传报告测试**

Create `tests/test_huiji_wiki_media_upload.py`:

```python
from pathlib import Path

from src.huiji_wiki.media_upload import upload_wiki_media_assets


class FakeStorage:
    def __init__(self):
        self.uploaded = []

    def upload_file(self, local_path: Path, object_key: str, sha1: str = "") -> str:
        self.uploaded.append((local_path, object_key, sha1))
        return f"http://minio/{object_key}"


def test_upload_wiki_media_assets_counts_uploaded_skipped_and_missing(tmp_path):
    available = tmp_path / "assets" / "ok.png"
    available.parent.mkdir()
    available.write_bytes(b"image")
    storage = FakeStorage()

    report = upload_wiki_media_assets(
        media_assets=[
            {"media_id": "media:sha1:abc", "sha1": "abc", "local_relpath": "ok.png", "object_key": "reverse1999/image/ab/abc.png", "is_available": True},
            {"media_id": "media:sha1:def", "sha1": "def", "local_relpath": "missing.png", "object_key": "reverse1999/image/de/def.png", "is_available": True},
            {"media_id": "media:sha1:off", "sha1": "off", "local_relpath": "off.png", "object_key": "reverse1999/image/of/off.png", "is_available": False},
        ],
        asset_root=available.parent,
        storage=storage,
    )

    assert report.uploaded == 1
    assert report.missing_local_files == 1
    assert report.unavailable == 1
    assert storage.uploaded[0][1] == "reverse1999/image/ab/abc.png"
```

- [ ] **Step 2: 实现 `media_upload.py`**

Create `src/huiji_wiki/media_upload.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class WikiMediaStorage(Protocol):
    def upload_file(self, local_path: Path, object_key: str, sha1: str = "") -> str: ...


@dataclass(frozen=True)
class WikiMediaUploadReport:
    uploaded: int = 0
    missing_local_files: int = 0
    unavailable: int = 0
    conflicts: int = 0

    def lines(self) -> list[str]:
        return [
            f"[huiji-wiki] media_uploaded={self.uploaded}",
            f"[huiji-wiki] media_missing_local_files={self.missing_local_files}",
            f"[huiji-wiki] media_unavailable={self.unavailable}",
            f"[huiji-wiki] media_conflicts={self.conflicts}",
        ]


def upload_wiki_media_assets(media_assets: list[dict[str, Any]], asset_root: Path, storage: WikiMediaStorage) -> WikiMediaUploadReport:
    uploaded = 0
    missing = 0
    unavailable = 0
    conflicts = 0
    seen: set[str] = set()
    for row in media_assets:
        if not bool(row.get("is_available", True)):
            unavailable += 1
            continue
        object_key = str(row.get("object_key", ""))
        if not object_key or object_key in seen:
            continue
        seen.add(object_key)
        local_relpath = str(row.get("local_relpath", ""))
        local_path = asset_root / local_relpath
        if not local_relpath or not local_path.exists():
            missing += 1
            continue
        try:
            storage.upload_file(local_path, object_key, sha1=str(row.get("sha1", "")))
            uploaded += 1
        except RuntimeError:
            conflicts += 1
            raise
    return WikiMediaUploadReport(uploaded=uploaded, missing_local_files=missing, unavailable=unavailable, conflicts=conflicts)
```

- [ ] **Step 3: 接入 build 脚本**

Modify `scripts/build_huiji_wiki.py`:

```python
from src.assets.minio_store import MinioAssetStorage
from src.huiji_wiki.media_upload import upload_wiki_media_assets
```

在 `main()` 中保留 media assets 列表，避免重复读取：

```python
media_assets = list(iter_jsonl(paths.media_assets))
upload_report = upload_wiki_media_assets(
    media_assets=media_assets,
    asset_root=cfg.huiji.raw_root / "assets" / "files",
    storage=MinioAssetStorage(cfg.assets),
)
dataset = build_wiki_dataset(
    parents=list(iter_jsonl(paths.parent_blocks)),
    children=list(iter_jsonl(paths.child_blocks)),
    media_assets=media_assets,
)
```

打印报告：

```python
for line in upload_report.lines():
    print(line)
```

- [ ] **Step 4: 更新 build script 测试**

在 `tests/test_huiji_wiki_build_script.py` 中断言 summary 包含：

```python
assert "[huiji-wiki] media_uploaded=" in output
assert "[huiji-wiki] media_missing_local_files=" in output
assert "[huiji-wiki] media_conflicts=" in output
```

运行：

```powershell
python -m pytest tests/test_huiji_wiki_media_upload.py tests/test_huiji_wiki_build_script.py tests/test_minio_shared_upload.py -q
```

Expected: all pass.

---

### Task 3: 补齐 PageIndex 搜索、富卡片和布局比例

**对应 specs:** `FRONTEND-P0-07`、`FRONTEND-P0-10`、`FRONTEND-P0-11`、`FRONTEND-P0-12`、`FRONTEND-P0-15`

**Files:**

- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/components/wiki/CategoryRail.tsx`
- Modify: `frontend/react-app/src/components/wiki/PageIndex.tsx`
- Modify: `frontend/react-app/src/components/wiki/PageInfo.tsx`
- Create: `frontend/react-app/src/components/wiki/PageIndex.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/CategoryRail.test.tsx`

- [ ] **Step 1: 写 PageIndex 富卡片测试**

Create `frontend/react-app/src/components/wiki/PageIndex.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PageIndex } from './PageIndex'

describe('PageIndex', () => {
  it('renders search, thumbnail, page type, subtitle and summary', () => {
    const onSearch = vi.fn()
    const onSelect = vi.fn()
    render(
      <PageIndex
        query=""
        onQueryChange={onSearch}
        pages={[{ pageId: 'char:1', pageType: 'character', title: '爱兹拉', subtitle: 'Ezra', category: '角色', route: '/wiki/char/1', thumbnail: '/thumb.png', summary: '角色摘要' }]}
        selectedPageId=""
        onSelect={onSelect}
      />,
    )

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '爱兹拉' } })

    expect(onSearch).toHaveBeenCalledWith('爱兹拉')
    expect(screen.getByAltText('爱兹拉')).toHaveAttribute('src', '/thumb.png')
    expect(screen.getByText('character')).toBeInTheDocument()
    expect(screen.getByText('Ezra')).toBeInTheDocument()
    expect(screen.getByText('角色摘要')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 修改 PageIndex props 和渲染**

Update `PageIndex.tsx`:

```tsx
export function PageIndex({
  query,
  onQueryChange,
  pages,
  selectedPageId,
  onSelect,
}: {
  query: string
  onQueryChange: (value: string) => void
  pages: WikiPageListItem[]
  selectedPageId: string
  onSelect: (pageId: string) => void
}) {
  return (
    <aside data-testid="wiki-page-index" style={{ width: 280, borderRight: '1px solid var(--border-subtle)', padding: 16, overflowY: 'auto' }}>
      <input role="searchbox" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索 Wiki" />
      {pages.map((page) => (
        <button key={page.pageId} onClick={() => onSelect(page.pageId)} style={{ display: 'grid', gridTemplateColumns: '64px 1fr', gap: 12, width: '100%', textAlign: 'left', padding: 12 }}>
          {page.thumbnail ? <img src={page.thumbnail} alt={page.title} style={{ width: 64, height: 64, objectFit: 'cover' }} /> : <span aria-label={`${page.title} placeholder`} />}
          <span>
            <strong>{page.title}</strong>
            <small>{page.pageType}</small>
            <span>{page.subtitle || page.category}</span>
            <p>{page.summary}</p>
          </span>
        </button>
      ))}
    </aside>
  )
}
```

- [ ] **Step 3: 更新 WikiShell 搜索行为**

Add state:

```tsx
const [query, setQuery] = useState('')
```

Change page fetch:

```tsx
fetchWikiPages({ category: selectedCategory, q: query })
```

Dependency:

```tsx
}, [selectedCategory, query])
```

Pass props:

```tsx
<PageIndex query={query} onQueryChange={setQuery} pages={pages} selectedPageId={selectedPageId} onSelect={setSelectedPageId} />
```

Empty state:

```tsx
if (!categories.length && !error) {
  return <main data-testid="wiki-shell">Wiki 数据为空，请先运行 Wiki 构建器。</main>
}
```

- [ ] **Step 4: 修正布局比例**

In `CategoryRail.tsx`:

```tsx
width: open ? 280 : 28
```

In `PageIndex.tsx` keep:

```tsx
width: 280
```

In `PageInfo.tsx` keep or reduce:

```tsx
width: 220
```

`WikiReader` must remain:

```tsx
flex: 1
```

- [ ] **Step 5: 更新测试并运行**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/components/wiki/PageIndex.test.tsx src/components/wiki/WikiShell.test.tsx src/components/wiki/CategoryRail.test.tsx --run
```

Expected: all pass.

---

### Task 4: 补齐 PageInfo 和模板 P0 数据面

**对应 specs:** `TEMPLATE-P0-01` 至 `TEMPLATE-P0-08`、`FRONTEND-P0-14`、`ANIMATION-P0-02`

**Files:**

- Modify: `frontend/react-app/src/components/wiki/PageInfo.tsx`
- Create: `frontend/react-app/src/components/wiki/PageInfo.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/PsychubePage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/StoryPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/GenericWikiPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`
- Create: `frontend/react-app/src/components/wiki/templates/WikiTemplates.test.tsx`

- [ ] **Step 1: 写 PageInfo 测试**

Create `PageInfo.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PageInfo } from './PageInfo'

describe('PageInfo', () => {
  it('renders source, media count, relation count, link count and route', () => {
    render(
      <PageInfo
        page={{
          pageId: 'char:1',
          pageType: 'character',
          title: '爱兹拉',
          subtitle: '',
          category: '角色',
          route: '/wiki/char/1',
          content: { sections: [{ title: '技能' }] },
          mediaLinks: [{ pageId: 'char:1', sectionKey: 'media', mediaId: 'm1', mediaRole: 'portrait', displayOrder: 0 }],
          relations: [{ fromPageId: 'char:1', toPageId: 'story:1', relationType: 'appears_in', label: '剧情', confidence: 1 }],
          linkSpans: [{ pageId: 'char:1', sectionKey: 'summary', text: '维尔汀', targetRoute: '/wiki/char/2', confidence: 0.9 }],
          sourceTitle: 'Data:Char/1.json',
        }}
      />,
    )

    expect(screen.getByText('Data:Char/1.json')).toBeInTheDocument()
    expect(screen.getByText('1 media')).toBeInTheDocument()
    expect(screen.getByText('1 relation')).toBeInTheDocument()
    expect(screen.getByText('1 link')).toBeInTheDocument()
    expect(screen.getByText('/wiki/char/1')).toBeInTheDocument()
    expect(screen.getByText('技能')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 实现 PageInfo**

Render these fields:

```tsx
const sections = Array.isArray(page?.content.sections) ? (page?.content.sections as Array<{ title?: string }>) : []
```

Output:

```tsx
<strong>{page.sourceTitle || page.route}</strong>
<p>{page.mediaLinks.length} media</p>
<p>{page.relations.length} relation{page.relations.length === 1 ? '' : 's'}</p>
<p>{page.linkSpans.length} link{page.linkSpans.length === 1 ? '' : 's'}</p>
<p>{page.route}</p>
{sections.map((section) => section.title ? <li key={section.title}>{section.title}</li> : null)}
```

- [ ] **Step 3: 写模板基础数据面测试**

Create `WikiTemplates.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WikiPageDetail } from '../../../types/wiki'
import { GenericWikiPage } from './GenericWikiPage'
import { PsychubePage } from './PsychubePage'
import { StoryPage } from './StoryPage'

const base = {
  pageId: 'p1',
  subtitle: 'Sub',
  category: '角色',
  route: '/wiki/page/1',
  mediaLinks: [],
  relations: [],
  linkSpans: [],
}

describe('wiki templates', () => {
  it('renders psychube cover and effect fields', () => {
    const page = { ...base, pageType: 'psychube', title: '心相', content: { summary: '摘要', effect: '效果', story: '故事' } } as WikiPageDetail
    render(<PsychubePage page={page} />)
    expect(screen.getByText('效果')).toBeInTheDocument()
    expect(screen.getByText('故事')).toBeInTheDocument()
  })

  it('renders story body and related metadata', () => {
    const page = { ...base, pageType: 'story', title: '剧情', content: { summary: '摘要', body: '正文', chapter: '章节' } } as WikiPageDetail
    render(<StoryPage page={page} />)
    expect(screen.getByText('正文')).toBeInTheDocument()
    expect(screen.getByText('章节')).toBeInTheDocument()
  })

  it('renders generic page without raw Data JSON dump', () => {
    const page = { ...base, pageType: 'generic', title: '通用', content: { summary: '摘要', raw: { hidden: true } } } as WikiPageDetail
    render(<GenericWikiPage page={page} />)
    expect(screen.getByText('摘要')).toBeInTheDocument()
    expect(screen.queryByText(/hidden/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 4: 实现模板字段**

Rules:

- CharacterPage: keep `CharacterMediaStage`, render skills and summary.
- PsychubePage: render summary, effect, amplification, story and media cover if present.
- StoryPage: render summary, body, chapter, episode list if present.
- GenericWikiPage: render title, source-safe summary and structured sections; do not render raw object JSON.

Use helper pattern:

```tsx
const text = (value: unknown) => (typeof value === 'string' ? value : '')
```

- [ ] **Step 5: 运行模板测试**

```powershell
npm test -- src/components/wiki/PageInfo.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx --run
```

Expected: all pass.

---

### Task 5: 修正关键词多 span 渲染和 fallback

**对应 specs:** `LINK-P0-01`、`LINK-P0-02`、`LINK-P0-03`、`LINK-P0-04`

**Files:**

- Modify: `frontend/react-app/src/components/wiki/KeywordText.tsx`
- Create: `frontend/react-app/src/components/wiki/KeywordText.test.tsx`

- [ ] **Step 1: 写多关键词和重复词测试**

Create `KeywordText.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { KeywordText } from './KeywordText'

describe('KeywordText', () => {
  it('renders multiple keyword links without dropping text', () => {
    render(
      <KeywordText
        text="维尔汀遇见爱兹拉，维尔汀再次出现。"
        spans={[
          { pageId: 'p', sectionKey: 's', text: '维尔汀', targetRoute: '/wiki/char/vertin', confidence: 0.9 },
          { pageId: 'p', sectionKey: 's', text: '爱兹拉', targetRoute: '/wiki/char/ezra', confidence: 0.9 },
        ]}
      />,
    )

    expect(screen.getAllByRole('link', { name: '维尔汀' })).toHaveLength(2)
    expect(screen.getByRole('link', { name: '爱兹拉' })).toHaveAttribute('href', '/wiki/char/ezra')
    expect(screen.getByText(/再次出现/)).toBeInTheDocument()
  })

  it('renders missing target as plain text', () => {
    render(<KeywordText text="未知角色" spans={[{ pageId: 'p', sectionKey: 's', text: '未知角色', targetRoute: '', confidence: 0.9 }]} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('未知角色')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 实现安全分段渲染**

Replace current split logic with:

```tsx
export function KeywordText({ text, spans }: KeywordTextProps) {
  if (!spans.length) return <>{text}</>
  const candidates = spans.filter((span) => span.text && text.includes(span.text)).sort((a, b) => b.text.length - a.text.length)
  const nodes: React.ReactNode[] = []
  let index = 0
  while (index < text.length) {
    const matched = candidates.find((span) => text.startsWith(span.text, index))
    if (!matched) {
      nodes.push(text[index])
      index += 1
      continue
    }
    const key = `${matched.text}-${index}`
    if (matched.targetRoute) {
      nodes.push(<a key={key} href={matched.targetRoute} style={{ color: 'var(--accent-blue)' }}>{matched.text}</a>)
    } else {
      nodes.push(<span key={key}>{matched.text}</span>)
    }
    index += matched.text.length
  }
  return <>{nodes}</>
}
```

Add import:

```tsx
import type React from 'react'
```

- [ ] **Step 3: 运行关键词测试**

```powershell
npm test -- src/components/wiki/KeywordText.test.tsx --run
```

Expected: pass.

---

### Task 6: 列表 thumbnail 与 API detail 一致性

**对应 specs:** `API-P0-07`、`FRONTEND-P0-12`、`MEDIA-P0-06`

**Files:**

- Modify: `backend/wiki.py`
- Modify: `src/huiji_wiki/repository.py`
- Modify: `tests/test_huiji_wiki_api.py`

- [ ] **Step 1: 写列表 thumbnail API 测试**

In `tests/test_huiji_wiki_api.py` add:

```python
def test_wiki_pages_uses_first_media_url_as_thumbnail(monkeypatch):
    repo = InMemoryWikiRepository()
    repo.replace_all(
        categories=[],
        pages=[WikiPage(page_id="char:1", page_type="character", title="角色", subtitle="", category="角色", route="/wiki/char/1", source_pageid=1, source_title="", content_json={"summary": "摘要"}, updated_at="")],
        media_links=[WikiMediaLink(page_id="char:1", section_key="media", media_id="media:sha1:abc", media_role="portrait", display_order=0, url="http://minio/portrait.png")],
        relations=[],
        aliases=[],
        link_spans=[],
    )
    monkeypatch.setattr("backend.wiki.get_wiki_repository", lambda: repo)

    body = TestClient(app).get("/api/wiki/pages?category=角色").json()

    assert body["items"][0]["thumbnail"] == "http://minio/portrait.png"
    assert body["items"][0]["summary"] == "摘要"
```

- [ ] **Step 2: Add repository helper for thumbnails**

Add to repository protocol and implementations:

```python
def first_media_url_by_page(self, page_ids: list[str]) -> dict[str, str]: ...
```

In memory implementation:

```python
return {
    page_id: next((link.url for link in sorted(self.media_links, key=lambda item: item.display_order) if link.page_id == page_id and link.url), "")
    for page_id in page_ids
}
```

In MySQL implementation:

```sql
SELECT page_id, url
FROM wiki_media_links
WHERE page_id IN (...) AND url <> ''
ORDER BY page_id, display_order ASC
```

Keep the first URL per page in Python.

- [ ] **Step 3: Use thumbnails in `wiki_pages()`**

In `backend/wiki.py`:

```python
thumbnail_by_page = repo.first_media_url_by_page([page.page_id for page in page_list.items])
```

Then:

```python
thumbnail=thumbnail_by_page.get(page.page_id, ""),
```

- [ ] **Step 4: Run API tests**

```powershell
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q
```

Expected: all pass.

---

### Task 7: 真实数据端到端验收脚本和手动检查门槛

**对应 specs:** `BUILD-P0-*`、`MEDIA-P0-*`、`API-P0-*`、`FRONTEND-P0-*`

**Files:**

- Create: `scripts/verify_huiji_wiki_e2e.py`
- Create: `tests/test_huiji_wiki_e2e_script.py`
- Modify: `docs/huiji-rag-runbook.md`

- [ ] **Step 1: 写验收脚本测试**

Create `tests/test_huiji_wiki_e2e_script.py`:

```python
from scripts.verify_huiji_wiki_e2e import validate_page_payload


def test_validate_page_payload_rejects_local_paths():
    result = validate_page_payload({"mediaLinks": [{"url": "D:\\bad\\image.png"}]})
    assert result.ok is False
    assert "local path" in result.message


def test_validate_page_payload_accepts_http_media_url():
    result = validate_page_payload({"mediaLinks": [{"url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/ab/abc.png"}]})
    assert result.ok is True
```

- [ ] **Step 2: 创建验收脚本**

Create `scripts/verify_huiji_wiki_e2e.py`:

```python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any
from urllib.request import urlopen


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str


def validate_page_payload(payload: dict[str, Any]) -> ValidationResult:
    text = str(payload)
    if "D:\\" in text or "C:\\" in text:
        return ValidationResult(False, "payload contains local path")
    media_links = payload.get("mediaLinks") or []
    if not any(str(item.get("url", "")).startswith(("http://", "https://")) for item in media_links):
        return ValidationResult(False, "payload has no http media url")
    return ValidationResult(True, "payload has safe http media url")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--page-id", required=True)
    args = parser.parse_args()
    import json

    with urlopen(f"{args.api.rstrip('/')}/api/wiki/pages/{args.page_id}", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = validate_page_payload(payload)
    if not result.ok:
        raise SystemExit(result.message)
    print(result.message)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 记录手动验收命令**

Append to `docs/huiji-rag-runbook.md`:

```markdown
## Wiki P0 真实数据验收

1. 构建 Wiki:
   `python scripts/build_huiji_wiki.py`
2. 启动后端:
   `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
3. 启动前端:
   `cd frontend/react-app && npm run dev -- --host 127.0.0.1 --port 5173`
4. 打开:
   `http://127.0.0.1:5173/wiki`
5. 选择一个角色或心相页面，确认主媒体区域显示真实图片。
6. 运行:
   `python scripts/verify_huiji_wiki_e2e.py --page-id <真实 page_id>`
```

- [ ] **Step 4: 运行脚本测试**

```powershell
python -m pytest tests/test_huiji_wiki_e2e_script.py -q
```

Expected: pass.

---

## 5. 可选任务

以下 P1 只有在所有 P0 验收通过后执行。

### Optional A: 最小构建报告增强

**Specs:** `BUILD-P1-03`、`MEDIA-P1-01`

- 输出页面异常数量、media missing 明细文件、sha1 conflict 明细文件。
- 文件建议：`src/huiji_wiki/media_upload.py`、`scripts/build_huiji_wiki.py`。

### Optional B: PageInfo RAG 跳转信息增强

**Specs:** `FRONTEND-P1-02`、`RAGLINK-P1-01`、`RAGLINK-P1-02`

- 在 `PageInfo` 显示 `route`、`sourcePageid`、`sourceTitle` 和 resolve query。
- 不接 RAG 页面输出格式。

### Optional C: Alias fallback 增强

**Specs:** `API-P1-02`

- 扩展 `routes/resolve` 的别名匹配。
- 增加英文名、source title 和 alias priority 测试。

---

## 6. Deferred / Out of Scope

- `BUILD-P2-01` 至 `BUILD-P2-03`: 增量构建、构建任务 UI、管理后台。
- `MEDIA-P2-01` 至 `MEDIA-P2-03`: CDN、私有 bucket、媒体中心。
- `API-P2-01` 至 `API-P2-03`: 专用搜索索引、后台编辑、migration 管理。
- `FRONTEND-P2-01` 至 `FRONTEND-P2-03`: 专属动效、收藏、布局个性化。
- `TEMPLATE-P2-01` 至 `TEMPLATE-P2-04`: 复杂模板、关系图谱、Live2D 播放器、媒体中心。
- `LINK-P2-01` 至 `LINK-P2-04`: 自动链接词表、消歧和人工修正。
- `RAGLINK-P2-01` 至 `RAGLINK-P2-03`: RAG 来源卡片、段落跳转、媒体字段联动。
- `ANIMATION-P2-01`、`ANIMATION-P2-02`: ReactBits 具体组件接入和 profile 驱动。

---

## 7. 完成后自检表

执行结束后逐项填写：

| Specs 编号 | 状态 | 证据 |
|---|---|---|
| `BUILD-P0-03` | 未执行 | 需要 `python scripts/build_huiji_wiki.py` 输出页面数。 |
| `BUILD-P0-04` | 未执行 | 需要搜索或通用模板覆盖非重点页面。 |
| `BUILD-P0-05` | 未执行 | 需要确认 Data namespace 未直接展示。 |
| `BUILD-P0-08` | 未执行 | 需要构建报告显示 missing/unavailable。 |
| `MEDIA-P0-01` | 未执行 | 需要 MinIO bucket 配置和上传报告。 |
| `MEDIA-P0-02` | 未执行 | 需要 object key 前缀检查。 |
| `MEDIA-P0-03` | 未执行 | 需要 media_id sha1 测试。 |
| `MEDIA-P0-04` | 未执行 | 需要 object_key 格式测试。 |
| `MEDIA-P0-05` | 未执行 | 需要 API payload 无本地路径测试。 |
| `MEDIA-P0-06` | 未执行 | 需要真实图片 URL 和前端渲染验收。 |
| `MEDIA-P0-07` | 未执行 | 需要幂等上传测试。 |
| `MEDIA-P0-08` | 未执行 | 需要确认无 delete/clear bucket 操作。 |
| `MEDIA-P0-09` | 未执行 | 需要图片缺失占位测试。 |
| `API-P0-07` | 未执行 | 需要 page detail 完整字段测试。 |
| `API-P0-09` | 未执行 | 需要 API 失败不影响主站的前端错误态测试。 |
| `FRONTEND-P0-07` | 未执行 | 需要布局比例测试或截图验收。 |
| `FRONTEND-P0-10` | 未执行 | 需要分类 API 测试。 |
| `FRONTEND-P0-11` | 未执行 | 需要搜索输入测试。 |
| `FRONTEND-P0-12` | 未执行 | 需要富卡片测试。 |
| `FRONTEND-P0-13` | 已落地基线 | `WikiReader` 主区域存在，执行时复测。 |
| `FRONTEND-P0-14` | 未执行 | 需要 PageInfo 测试。 |
| `FRONTEND-P0-15` | 未执行 | 需要服务不可用错误态测试。 |
| `TEMPLATE-P0-01` | 已落地基线 | 模板文件已存在，执行时复测。 |
| `TEMPLATE-P0-02` | 未执行 | 需要真实图片渲染验收。 |
| `TEMPLATE-P0-03` | 已落地基线 | `CharacterMediaStage` 同窗口存在，执行时复测。 |
| `TEMPLATE-P0-04` | 已落地基线 | Live2D fallback 存在，执行时复测。 |
| `TEMPLATE-P0-05` | 已落地基线 | 媒体窗口最小高度测试存在，执行时复测。 |
| `TEMPLATE-P0-06` | 未执行 | 需要心相模板测试。 |
| `TEMPLATE-P0-07` | 未执行 | 需要剧情模板测试。 |
| `TEMPLATE-P0-08` | 未执行 | 需要通用页不暴露 raw JSON 测试。 |
| `LINK-P0-01` | 未执行 | 需要多关键词跳转测试。 |
| `LINK-P0-02` | 已落地基线 | `wiki_link_spans` 表存在，执行时复测。 |
| `LINK-P0-03` | 已落地基线 | 前端使用 API spans，执行时复测。 |
| `LINK-P0-04` | 未执行 | 需要 missing target fallback 测试。 |
| `RAGLINK-P0-04` | 未执行 | 需要 resolve fail query 测试。 |
| `ANIMATION-P0-02` | 未执行 | 需要组件结构保留挂点的代码审查记录。 |

---

## 8. 最终验证命令

- [ ] **Backend targeted tests**

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_models.py tests/test_huiji_wiki_builder.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py tests/test_huiji_wiki_media_upload.py tests/test_huiji_wiki_build_script.py tests/test_minio_shared_upload.py tests/test_huiji_wiki_e2e_script.py -q
```

- [ ] **Frontend targeted tests**

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx src/components/wiki/KeywordText.test.tsx src/components/wiki/WikiShell.test.tsx src/components/wiki/CategoryRail.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx --run
```

- [ ] **Frontend build**

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run build
```

- [ ] **Real data smoke**

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python scripts\build_huiji_wiki.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open:

```text
http://127.0.0.1:5173/wiki
```

Expected:

- `/wiki` loads outside snap container.
- Left rail opens after hover delay.
- Left rail open width equals PageIndex width.
- PageIndex supports search and shows thumbnail/type/subtitle/summary.
- At least one character or psychube page displays real MinIO image.
- Live2D tab remains visible and fallback does not resize frame.
- Keyword links render more than one link in one paragraph.
- `scripts/verify_huiji_wiki_e2e.py --page-id <真实 page_id>` prints `payload has safe http media url`.
