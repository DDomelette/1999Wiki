# 灰机 Wiki 前端模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于灰机爬虫数据实现独立 `/wiki` 工作区：Wiki 数据进入 MySQL，媒体复用 RAG 的 MinIO 资产规则，React 前端可浏览角色、心相、剧情和通用页面，同时为 RAG 来源跳转预留稳定接口。

**Architecture:** 首期采用 MySQL + FastAPI Wiki API + React `/wiki`。构建层从 `data/huiji/res1999` 和现有 `src/huiji_rag` 媒体模型生成 Wiki 页面、关系、别名、媒体映射和关键词链接；Wiki 不读 Milvus，不参与向量化；MinIO 与 RAG 共用 `reverse1999-assets/reverse1999/...` 命名规则。

**Tech Stack:** Python 3, pytest, FastAPI, Pydantic, PyMySQL, MinIO, dataclasses, JSON/JSONL, React 18, TypeScript, Vite, Vitest, Testing Library, Zustand, Framer Motion.

---

## Scope Check

本计划覆盖一个可独立验证的 Wiki 首期纵切面：共享媒体安全边界、Wiki 数据构建、MySQL 存储、FastAPI API、React `/wiki` 页面和三个入口。它不实现 RAG 检索链路、不重建 Milvus、不要求问答页 source 输出格式在本计划内完成。RAG 只通过 `wiki_route`、`entity_id`、`source_id` 预留跳转接口。

当前工作树有大量与本任务无关的修改和未跟踪数据。执行本计划时只改本计划列出的文件；不要清理、重置或提交无关文件。执行提交时每个任务只暂存本任务涉及的文件。

---

## File Structure

Project root: `D:/PycharmProjects/nlp/LangChain/1999Search`

### Backend And Build Layer

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/requirements.txt`  
  Add `pymysql`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/settings.yaml`  
  Add `mysql` and `wiki` sections.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/config.py`  
  Add `MysqlCfg` and `WikiCfg`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/minio_store.py`  
  Add idempotent upload and conflict detection for shared bucket usage.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/__init__.py`  
  Package marker.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/models.py`  
  Wiki dataclasses and JSON helpers.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/builder.py`  
  Transform Huiji corpus outputs into Wiki pages, categories, media links, aliases, relations and link spans.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`  
  Repository protocol, in-memory repository for tests, MySQL repository for runtime, schema creation SQL.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_huiji_wiki.py`  
  CLI for building Wiki MySQL rows and printing an audit summary.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`  
  Pydantic response models for `/api/wiki/*`.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`  
  FastAPI router and repository dependency.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/main.py`  
  Include Wiki router.

### Frontend

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/constants/layout.ts`  
  Export shared hover reveal delay.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/hooks/useTopNavTrigger.ts`  
  Use the shared delay constant.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/wiki.ts`  
  Wiki-specific API types.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.ts`  
  Wiki API client.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.tsx`  
  Top-level `/wiki` route switch without adding a router dependency.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.tsx`  
  Route-level Wiki workspace.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.tsx`  
  Hidden left edge category rail.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageIndex.tsx`  
  Search and page list.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiReader.tsx`  
  Template switch.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/PageInfo.tsx`  
  Right info rail.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/KeywordText.tsx`  
  Blue keyword link renderer.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/PsychubePage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/StoryPage.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/GenericWikiPage.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.tsx`  
  Add Wiki entry.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/Sidebar.tsx`  
  Add Wiki entry.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.tsx`  
  Add calendar page Wiki CTA when category is 日历/calendar.

### Tests

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_wiki_config.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_minio_shared_upload.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_models.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_builder.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.test.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/CategoryRail.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/WikiShell.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.wiki.test.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/hooks/useTopNavTrigger.test.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.test.tsx`

---

## Task 1: Add Wiki And MySQL Config

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/requirements.txt`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/settings.yaml`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/config.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_wiki_config.py`

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_wiki_config.py`:

```python
from config.config import get_config, reset_config_for_test


def test_mysql_and_wiki_config_defaults_are_loaded(monkeypatch):
    monkeypatch.delenv("MYSQL_HOST", raising=False)
    monkeypatch.delenv("MYSQL_PORT", raising=False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("MYSQL_USER", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    reset_config_for_test()

    cfg = get_config()

    assert cfg.mysql.host == "127.0.0.1"
    assert cfg.mysql.port == 3306
    assert cfg.mysql.database == "reverse1999_wiki"
    assert cfg.mysql.user == "root"
    assert cfg.wiki.enabled is True
    assert cfg.wiki.default_page_limit == 30


def test_mysql_config_environment_overrides(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "mysql")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_DATABASE", "wiki_test")
    monkeypatch.setenv("MYSQL_USER", "potato")
    monkeypatch.setenv("MYSQL_PASSWORD", "secret")
    reset_config_for_test()

    cfg = get_config()

    assert cfg.mysql.host == "mysql"
    assert cfg.mysql.port == 3307
    assert cfg.mysql.database == "wiki_test"
    assert cfg.mysql.user == "potato"
    assert cfg.mysql.password == "secret"
```

- [ ] **Step 2: Run the config tests and verify they fail**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_wiki_config.py -q
```

Expected: fail with `AttributeError: 'Config' object has no attribute 'mysql'`.

- [ ] **Step 3: Add PyMySQL dependency**

Append this line to `requirements.txt`:

```text
pymysql
```

- [ ] **Step 4: Add settings sections**

Add to `config/settings.yaml`:

```yaml
mysql:
  host: "127.0.0.1"
  port: 3306
  database: "reverse1999_wiki"
  user: "root"
  password: ""
  charset: "utf8mb4"

wiki:
  enabled: true
  default_page_limit: 30
```

- [ ] **Step 5: Add config dataclasses and loader logic**

In `config/config.py`, add near the other dataclasses:

```python
@dataclass
class MysqlCfg:
    host: str
    port: int
    database: str
    user: str
    password: str
    charset: str


@dataclass
class WikiCfg:
    enabled: bool
    default_page_limit: int
```

Add fields to `Config`:

```python
    mysql: MysqlCfg
    wiki: WikiCfg
```

Inside `get_config()`, after `retrieval_raw = raw.get("retrieval", {})`, add:

```python
    mysql_raw = raw.get("mysql", {})
    wiki_raw = raw.get("wiki", {})
```

Inside the `Config(...)` construction, add:

```python
        mysql=MysqlCfg(
            host=os.environ.get("MYSQL_HOST") or str(mysql_raw.get("host", "127.0.0.1")),
            port=int(os.environ.get("MYSQL_PORT") or mysql_raw.get("port", 3306)),
            database=os.environ.get("MYSQL_DATABASE") or str(mysql_raw.get("database", "reverse1999_wiki")),
            user=os.environ.get("MYSQL_USER") or str(mysql_raw.get("user", "root")),
            password=os.environ.get("MYSQL_PASSWORD") or str(mysql_raw.get("password", "")),
            charset=str(mysql_raw.get("charset", "utf8mb4")),
        ),
        wiki=WikiCfg(
            enabled=bool(wiki_raw.get("enabled", True)),
            default_page_limit=int(wiki_raw.get("default_page_limit", 30)),
        ),
```

- [ ] **Step 6: Run config regression tests**

Run:

```powershell
python -m pytest tests/test_config.py tests/test_huiji_config.py tests/test_wiki_config.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit checkpoint**

```powershell
git add requirements.txt config/settings.yaml config/config.py tests/test_wiki_config.py
git commit -m "feat: add wiki mysql config"
```

---

## Task 2: Harden Shared MinIO Uploads

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/minio_store.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_minio_shared_upload.py`

- [ ] **Step 1: Write failing tests for idempotent upload and conflict detection**

Create `tests/test_minio_shared_upload.py`:

```python
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from config.config import AssetStorageCfg


class FakeStat:
    def __init__(self, size: int, metadata: dict[str, str] | None = None) -> None:
        self.size = size
        self.metadata = metadata or {}


class FakeMinioClient:
    existing: dict[str, FakeStat] = {}
    uploads: list[tuple[str, str, str, dict[str, str]]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def bucket_exists(self, bucket_name: str) -> bool:
        return True

    def make_bucket(self, bucket_name: str) -> None:
        raise AssertionError("bucket already exists in fake")

    def set_bucket_policy(self, bucket_name: str, policy: str) -> None:
        pass

    def stat_object(self, bucket_name: str, object_key: str) -> FakeStat:
        if object_key not in self.existing:
            raise FileNotFoundError(object_key)
        return self.existing[object_key]

    def fput_object(self, bucket_name: str, object_key: str, local_path: str, content_type: str, metadata=None) -> None:
        self.uploads.append((bucket_name, object_key, local_path, metadata or {}))
        self.existing[object_key] = FakeStat(Path(local_path).stat().st_size, metadata or {})


@pytest.fixture(autouse=True)
def fake_minio_module(monkeypatch):
    FakeMinioClient.existing = {}
    FakeMinioClient.uploads = []
    module = types.SimpleNamespace(Minio=FakeMinioClient)
    monkeypatch.setitem(sys.modules, "minio", module)


def _cfg() -> AssetStorageCfg:
    return AssetStorageCfg(
        provider="minio",
        endpoint="127.0.0.1:9002",
        public_base_url="http://127.0.0.1:9002",
        bucket_name="reverse1999-assets",
        secure=False,
        object_prefix="reverse1999",
        access_key="minioadmin",
        secret_key="minioadmin",
    )


def test_upload_file_skips_existing_matching_object(tmp_path):
    from src.assets.minio_store import MinioAssetStorage

    local = tmp_path / "asset.png"
    local.write_bytes(b"same")
    object_key = "reverse1999/image/ab/abc.png"
    FakeMinioClient.existing[object_key] = FakeStat(
        size=4,
        metadata={"X-Amz-Meta-Sha1": "abc"},
    )

    storage = MinioAssetStorage(_cfg())
    url = storage.upload_file(local, object_key, sha1="abc")

    assert url == "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/ab/abc.png"
    assert FakeMinioClient.uploads == []


def test_upload_file_raises_on_existing_different_sha1(tmp_path):
    from src.assets.minio_store import MinioAssetStorage, MinioObjectConflictError

    local = tmp_path / "asset.png"
    local.write_bytes(b"new")
    object_key = "reverse1999/image/ab/abc.png"
    FakeMinioClient.existing[object_key] = FakeStat(
        size=3,
        metadata={"X-Amz-Meta-Sha1": "different"},
    )

    storage = MinioAssetStorage(_cfg())

    with pytest.raises(MinioObjectConflictError):
        storage.upload_file(local, object_key, sha1="abc")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_minio_shared_upload.py -q
```

Expected: fail because `upload_file()` does not accept `sha1` and `MinioObjectConflictError` is undefined.

- [ ] **Step 3: Implement idempotent upload**

Modify `src/assets/minio_store.py`:

```python
class MinioObjectConflictError(RuntimeError):
    pass


class MinioAssetStorage:
    ...
    def upload_file(self, local_path: Path, object_key: str, sha1: str = "") -> str:
        content_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
        metadata = {"sha1": sha1} if sha1 else {}
        try:
            stat = self._client.stat_object(self._cfg.bucket_name, object_key)
        except Exception:
            stat = None

        if stat is not None:
            remote_sha1 = ""
            if hasattr(stat, "metadata") and stat.metadata:
                remote_sha1 = stat.metadata.get("X-Amz-Meta-Sha1", "") or stat.metadata.get("sha1", "")
            if sha1 and remote_sha1 and remote_sha1 != sha1:
                raise MinioObjectConflictError(
                    f"object_key conflict: {object_key} remote_sha1={remote_sha1} local_sha1={sha1}"
                )
            if int(getattr(stat, "size", -1)) == local_path.stat().st_size:
                quoted_key = quote(object_key, safe="/")
                return f"{self._cfg.public_base_url.rstrip('/')}/{self._cfg.bucket_name}/{quoted_key}"

        self._client.fput_object(
            self._cfg.bucket_name,
            object_key,
            str(local_path),
            content_type=content_type,
            metadata=metadata,
        )
        quoted_key = quote(object_key, safe="/")
        return f"{self._cfg.public_base_url.rstrip('/')}/{self._cfg.bucket_name}/{quoted_key}"
```

Keep the existing public-read policy behavior unchanged.

- [ ] **Step 4: Update existing build script to pass sha1 when available**

Modify `scripts/build_assets.py`:

```python
url = storage.upload_file(Path(record.local_path), record.object_key, sha1=record.asset_id)
```

If the current file already computes a different field name, pass the SHA1 field that corresponds to the object key.

- [ ] **Step 5: Run asset tests**

Run:

```powershell
python -m pytest tests/test_minio_shared_upload.py tests/test_asset_build_script.py tests/test_asset_extractor.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit checkpoint**

```powershell
git add src/assets/minio_store.py scripts/build_assets.py tests/test_minio_shared_upload.py
git commit -m "feat: guard shared minio uploads"
```

---

## Task 3: Add Wiki Domain Models

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/__init__.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/models.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_huiji_wiki_models.py`:

```python
from src.huiji_wiki.models import (
    WikiAlias,
    WikiCategory,
    WikiLinkSpan,
    WikiMediaLink,
    WikiPage,
    WikiRelation,
)


def test_wiki_page_round_trip_keeps_content_json():
    page = WikiPage(
        page_id="char:3074",
        page_type="character",
        title="爱兹拉",
        subtitle="Ezra Theodore",
        category="角色",
        route="/wiki/char/3074",
        source_pageid=116433,
        source_title="Data:Char/3074.json",
        content_json={"profile": {"star": 6}, "skills": [{"name": "菌毯"}]},
        updated_at="2026-07-06T10:00:00+08:00",
    )

    row = page.to_json()

    assert row["route"] == "/wiki/char/3074"
    assert WikiPage.from_json(row).content_json["profile"]["star"] == 6


def test_media_link_supports_live2d_fallback():
    link = WikiMediaLink(
        page_id="char:3074",
        section_key="media",
        media_id="media:sha1:live2d",
        media_role="live2d",
        display_order=2,
        fallback_media_id="media:sha1:portrait",
    )

    assert link.to_json()["fallback_media_id"] == "media:sha1:portrait"
    assert WikiMediaLink.from_json(link.to_json()).media_role == "live2d"


def test_category_and_link_models_have_animation_and_route_fields():
    category = WikiCategory(key="character", label="角色", count=3, template_group="character", animation_profile="entity-list", theme_token="character")
    relation = WikiRelation(from_page_id="char:3074", to_page_id="story:100532", relation_type="appears_in", label="出场剧情", confidence=0.95)
    alias = WikiAlias(page_id="char:3074", alias="爱兹拉", alias_type="canonical", priority=100)
    span = WikiLinkSpan(page_id="char:3074", section_key="story", text="维尔汀", target_route="/wiki/char/3001", confidence=0.9)

    assert category.to_json()["animationProfile"] == "entity-list"
    assert relation.to_json()["toPageId"] == "story:100532"
    assert alias.to_json()["priority"] == 100
    assert span.to_json()["targetRoute"] == "/wiki/char/3001"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_models.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'src.huiji_wiki'`.

- [ ] **Step 3: Create package marker**

Create `src/huiji_wiki/__init__.py`:

```python
"""Wiki display data built from Huiji crawler output."""
```

- [ ] **Step 4: Add dataclasses**

Create `src/huiji_wiki/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def _camel(row: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "page_id": "pageId",
        "page_type": "pageType",
        "source_pageid": "sourcePageid",
        "source_title": "sourceTitle",
        "content_json": "content",
        "template_group": "templateGroup",
        "animation_profile": "animationProfile",
        "theme_token": "themeToken",
        "section_key": "sectionKey",
        "media_id": "mediaId",
        "media_role": "mediaRole",
        "display_order": "displayOrder",
        "fallback_media_id": "fallbackMediaId",
        "from_page_id": "fromPageId",
        "to_page_id": "toPageId",
        "relation_type": "relationType",
        "alias_type": "aliasType",
        "target_route": "targetRoute",
    }
    return {mapping.get(key, key): value for key, value in row.items()}


@dataclass(frozen=True)
class WikiPage:
    page_id: str
    page_type: str
    title: str
    subtitle: str
    category: str
    route: str
    source_pageid: int | None
    source_title: str
    content_json: dict[str, Any]
    updated_at: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_api(self) -> dict[str, Any]:
        return _camel(self.to_json())

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "WikiPage":
        return cls(
            page_id=str(row["page_id"]),
            page_type=str(row.get("page_type", "generic")),
            title=str(row.get("title", "")),
            subtitle=str(row.get("subtitle", "")),
            category=str(row.get("category", "")),
            route=str(row.get("route", "")),
            source_pageid=row.get("source_pageid"),
            source_title=str(row.get("source_title", "")),
            content_json=dict(row.get("content_json", {})),
            updated_at=str(row.get("updated_at", "")),
        )


@dataclass(frozen=True)
class WikiCategory:
    key: str
    label: str
    count: int
    template_group: str
    animation_profile: str
    theme_token: str

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class WikiMediaLink:
    page_id: str
    section_key: str
    media_id: str
    media_role: str
    display_order: int
    fallback_media_id: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_api(self) -> dict[str, Any]:
        return _camel(self.to_json())

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "WikiMediaLink":
        return cls(
            page_id=str(row["page_id"]),
            section_key=str(row.get("section_key", "")),
            media_id=str(row.get("media_id", "")),
            media_role=str(row.get("media_role", "")),
            display_order=int(row.get("display_order", 0) or 0),
            fallback_media_id=str(row.get("fallback_media_id", "")),
        )


@dataclass(frozen=True)
class WikiRelation:
    from_page_id: str
    to_page_id: str
    relation_type: str
    label: str
    confidence: float

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class WikiAlias:
    page_id: str
    alias: str
    alias_type: str
    priority: int

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class WikiLinkSpan:
    page_id: str
    section_key: str
    text: str
    target_route: str
    confidence: float

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))
```

- [ ] **Step 5: Run model tests**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_models.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit checkpoint**

```powershell
git add src/huiji_wiki/__init__.py src/huiji_wiki/models.py tests/test_huiji_wiki_models.py
git commit -m "feat: add huiji wiki data models"
```

---

## Task 4: Build Wiki Dataset From Huiji Corpus Artifacts

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/builder.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_builder.py`

- [ ] **Step 1: Write failing builder tests**

Create `tests/test_huiji_wiki_builder.py`:

```python
from src.huiji_wiki.builder import build_wiki_dataset


def test_build_wiki_dataset_prioritizes_character_pages_and_media():
    parents = [
        {
            "parent_id": "char:3074",
            "entity_id": "3074",
            "entity_name": "爱兹拉",
            "entity_aliases": ["Ezra Theodore"],
            "category": "character",
            "section_kind": "entity",
            "title": "爱兹拉",
            "summary_text": "爱兹拉 角色资料",
            "source_refs": [{"kind": "data_page", "title": "Data:Char/3074.json", "pageid": 116433}],
            "child_ids": ["char:3074/profile", "char:3074/skill:30740111"],
            "content_hash": "hash",
        }
    ]
    children = [
        {
            "child_id": "char:3074/profile",
            "parent_id": "char:3074/profile",
            "entity_id": "3074",
            "entity_name": "爱兹拉",
            "category": "character",
            "section_kind": "profile",
            "title": "基础资料",
            "text": "爱兹拉基础资料",
            "search_text": "爱兹拉 Ezra Theodore",
            "chunk_index": 0,
            "media_ids": ["media:sha1:portrait"],
            "media_policy": "auto",
            "source_refs": [{"kind": "data_page", "title": "Data:Char/3074.json"}],
            "content_hash": "hash-profile",
        },
        {
            "child_id": "char:3074/skill:30740111",
            "parent_id": "char:3074/skills",
            "entity_id": "3074",
            "entity_name": "爱兹拉",
            "category": "character",
            "section_kind": "skill",
            "title": "菌毯",
            "text": "造成精神创伤。",
            "search_text": "爱兹拉 技能 菌毯",
            "chunk_index": 1,
            "media_ids": ["media:sha1:skill"],
            "media_policy": "auto",
            "source_refs": [{"kind": "data_page", "title": "Data:Char/3074.json"}],
            "content_hash": "hash-skill",
        },
    ]
    media = [
        {
            "media_id": "media:sha1:portrait",
            "sha1": "portrait",
            "asset_type": "portrait",
            "filename": "Portrait-307401.png",
            "title": "Portrait-307401.png",
            "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/po/portrait.png",
            "is_available": True,
            "object_key": "reverse1999/portrait/po/portrait.png",
        },
        {
            "media_id": "media:sha1:skill",
            "sha1": "skill",
            "asset_type": "skill",
            "filename": "Skill-30740111.png",
            "title": "Skill-30740111.png",
            "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/skill/sk/skill.png",
            "is_available": True,
            "object_key": "reverse1999/skill/sk/skill.png",
        },
    ]

    dataset = build_wiki_dataset(parents=parents, children=children, media_assets=media)

    assert [category.key for category in dataset.categories] == ["character"]
    assert dataset.pages[0].page_id == "char:3074"
    assert dataset.pages[0].route == "/wiki/char/3074"
    assert dataset.pages[0].content_json["skills"][0]["title"] == "菌毯"
    assert [link.media_role for link in dataset.media_links] == ["portrait", "skill"]


def test_build_wiki_dataset_adds_high_confidence_keyword_links():
    dataset = build_wiki_dataset(
        parents=[
            {
                "parent_id": "char:3001",
                "entity_id": "3001",
                "entity_name": "维尔汀",
                "entity_aliases": ["Vertin"],
                "category": "character",
                "section_kind": "entity",
                "title": "维尔汀",
                "summary_text": "维尔汀",
                "source_refs": [],
                "child_ids": [],
                "content_hash": "a",
            },
            {
                "parent_id": "char:3074",
                "entity_id": "3074",
                "entity_name": "爱兹拉",
                "entity_aliases": [],
                "category": "character",
                "section_kind": "entity",
                "title": "爱兹拉",
                "summary_text": "爱兹拉与维尔汀同行。",
                "source_refs": [],
                "child_ids": ["char:3074/profile"],
                "content_hash": "b",
            },
        ],
        children=[
            {
                "child_id": "char:3074/profile",
                "parent_id": "char:3074/profile",
                "entity_id": "3074",
                "entity_name": "爱兹拉",
                "category": "character",
                "section_kind": "profile",
                "title": "基础资料",
                "text": "爱兹拉与维尔汀同行。",
                "search_text": "爱兹拉 维尔汀",
                "chunk_index": 0,
                "media_ids": [],
                "media_policy": "auto",
                "source_refs": [],
                "content_hash": "c",
            }
        ],
        media_assets=[],
    )

    assert dataset.link_spans[0].text == "维尔汀"
    assert dataset.link_spans[0].target_route == "/wiki/char/3001"
```

- [ ] **Step 2: Run builder tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_builder.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'src.huiji_wiki.builder'`.

- [ ] **Step 3: Implement dataset builder**

Create `src/huiji_wiki/builder.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.huiji_wiki.models import WikiAlias, WikiCategory, WikiLinkSpan, WikiMediaLink, WikiPage, WikiRelation


@dataclass(frozen=True)
class WikiDataset:
    categories: list[WikiCategory]
    pages: list[WikiPage]
    media_links: list[WikiMediaLink]
    relations: list[WikiRelation]
    aliases: list[WikiAlias]
    link_spans: list[WikiLinkSpan]


def _route_for(parent: dict[str, Any]) -> str:
    category = str(parent.get("category", ""))
    entity_id = str(parent.get("entity_id", ""))
    if category == "character" and entity_id:
        return f"/wiki/char/{entity_id}"
    if category == "psychube" and entity_id:
        return f"/wiki/psychube/{entity_id}"
    if category == "story" and entity_id:
        return f"/wiki/story/{entity_id}"
    source_refs = parent.get("source_refs") or []
    pageid = ""
    if source_refs and isinstance(source_refs[0], dict):
        pageid = str(source_refs[0].get("pageid") or "")
    return f"/wiki/page/{pageid or parent.get('parent_id', 'unknown')}"


def _page_type_for(parent: dict[str, Any]) -> str:
    category = str(parent.get("category", ""))
    return {"character": "character", "psychube": "psychube", "story": "story"}.get(category, "generic")


def _category_label(key: str) -> str:
    return {"character": "角色", "psychube": "心相", "story": "剧情"}.get(key, key)


def _media_role(asset_type: str, filename: str) -> str:
    lowered = filename.lower()
    if asset_type == "portrait" and "l2d" in lowered:
        return "live2d"
    if asset_type == "portrait":
        return "portrait"
    if asset_type == "psychube":
        return "cover"
    return asset_type


def build_wiki_dataset(
    parents: list[dict[str, Any]],
    children: list[dict[str, Any]],
    media_assets: list[dict[str, Any]],
) -> WikiDataset:
    entity_parents = [row for row in parents if str(row.get("section_kind", "")) == "entity"]
    page_by_id: dict[str, WikiPage] = {}
    aliases: list[WikiAlias] = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    children_by_entity: dict[str, list[dict[str, Any]]] = {}
    media_by_id = {str(row.get("media_id", "")): row for row in media_assets}

    for child in children:
        children_by_entity.setdefault(str(child.get("entity_id", "")), []).append(child)

    for parent in entity_parents:
        page_id = f"{str(parent.get('category', 'page'))}:{parent.get('entity_id')}"
        route = _route_for(parent)
        page_children = sorted(children_by_entity.get(str(parent.get("entity_id", "")), []), key=lambda row: int(row.get("chunk_index", 0) or 0))
        content = {
            "summary": str(parent.get("summary_text", "")),
            "sections": [
                {
                    "sectionKey": str(child.get("section_kind", "")),
                    "title": str(child.get("title", "")),
                    "text": str(child.get("text", "")),
                    "mediaIds": list(child.get("media_ids") or []),
                }
                for child in page_children
            ],
            "skills": [
                {
                    "title": str(child.get("title", "")),
                    "text": str(child.get("text", "")),
                    "mediaIds": list(child.get("media_ids") or []),
                }
                for child in page_children
                if str(child.get("section_kind", "")) in {"skill", "ultimate"}
            ],
        }
        source_refs = parent.get("source_refs") or []
        source_ref = source_refs[0] if source_refs and isinstance(source_refs[0], dict) else {}
        page = WikiPage(
            page_id=page_id,
            page_type=_page_type_for(parent),
            title=str(parent.get("entity_name") or parent.get("title") or ""),
            subtitle=" / ".join(str(alias) for alias in parent.get("entity_aliases", []) if str(alias).strip()),
            category=_category_label(str(parent.get("category", ""))),
            route=route,
            source_pageid=source_ref.get("pageid"),
            source_title=str(source_ref.get("title", "")),
            content_json=content,
            updated_at=now,
        )
        page_by_id[page.page_id] = page
        aliases.append(WikiAlias(page_id=page.page_id, alias=page.title, alias_type="canonical", priority=100))
        for alias in parent.get("entity_aliases", []) or []:
            aliases.append(WikiAlias(page_id=page.page_id, alias=str(alias), alias_type="alias", priority=80))

    media_links: list[WikiMediaLink] = []
    for page in page_by_id.values():
        entity_id = page.page_id.split(":", 1)[1] if ":" in page.page_id else ""
        order = 0
        for child in children_by_entity.get(entity_id, []):
            for media_id in child.get("media_ids") or []:
                media = media_by_id.get(str(media_id))
                if not media:
                    continue
                role = _media_role(str(media.get("asset_type", "")), str(media.get("filename", "")))
                media_links.append(
                    WikiMediaLink(
                        page_id=page.page_id,
                        section_key=str(child.get("section_kind", "")),
                        media_id=str(media_id),
                        media_role=role,
                        display_order=order,
                        fallback_media_id="",
                    )
                )
                order += 1

    categories: list[WikiCategory] = []
    for key in sorted({str(parent.get("category", "")) for parent in entity_parents}):
        count = sum(1 for page in page_by_id.values() if page.page_type == _page_type_for({"category": key}))
        categories.append(
            WikiCategory(
                key=key,
                label=_category_label(key),
                count=count,
                template_group=_page_type_for({"category": key}),
                animation_profile="entity-list",
                theme_token=key,
            )
        )

    route_by_title = {page.title: page.route for page in page_by_id.values()}
    link_spans: list[WikiLinkSpan] = []
    for page in page_by_id.values():
        for section in page.content_json.get("sections", []):
            text = str(section.get("text", ""))
            for title, route in route_by_title.items():
                if title and title != page.title and title in text:
                    link_spans.append(
                        WikiLinkSpan(
                            page_id=page.page_id,
                            section_key=str(section.get("sectionKey", "")),
                            text=title,
                            target_route=route,
                            confidence=0.9,
                        )
                    )

    return WikiDataset(
        categories=categories,
        pages=list(page_by_id.values()),
        media_links=media_links,
        relations=[],
        aliases=aliases,
        link_spans=link_spans,
    )
```

- [ ] **Step 4: Run builder tests**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_builder.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit checkpoint**

```powershell
git add src/huiji_wiki/builder.py tests/test_huiji_wiki_builder.py
git commit -m "feat: build wiki dataset from huiji corpus"
```

---

## Task 5: Add Wiki Repository And MySQL Schema

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/test_huiji_wiki_repository.py`:

```python
from src.huiji_wiki.models import WikiAlias, WikiCategory, WikiLinkSpan, WikiMediaLink, WikiPage, WikiRelation
from src.huiji_wiki.repository import InMemoryWikiRepository, schema_sql


def _page() -> WikiPage:
    return WikiPage(
        page_id="char:3074",
        page_type="character",
        title="爱兹拉",
        subtitle="Ezra Theodore",
        category="角色",
        route="/wiki/char/3074",
        source_pageid=116433,
        source_title="Data:Char/3074.json",
        content_json={"summary": "爱兹拉"},
        updated_at="2026-07-06T10:00:00+08:00",
    )


def test_schema_contains_required_wiki_tables():
    sql = "\n".join(schema_sql())

    assert "CREATE TABLE IF NOT EXISTS wiki_categories" in sql
    assert "CREATE TABLE IF NOT EXISTS wiki_pages" in sql
    assert "CREATE TABLE IF NOT EXISTS wiki_media_links" in sql
    assert "CREATE TABLE IF NOT EXISTS wiki_relations" in sql
    assert "CREATE TABLE IF NOT EXISTS wiki_aliases" in sql
    assert "CREATE TABLE IF NOT EXISTS wiki_link_spans" in sql


def test_in_memory_repository_lists_categories_and_pages():
    repo = InMemoryWikiRepository()
    repo.replace_all(
        categories=[WikiCategory("character", "角色", 1, "character", "entity-list", "character")],
        pages=[_page()],
        media_links=[],
        relations=[],
        aliases=[WikiAlias("char:3074", "爱兹拉", "canonical", 100)],
        link_spans=[],
    )

    assert repo.list_categories()[0].label == "角色"
    assert repo.list_pages(category="character", q="", page_type="", limit=30, cursor="").items[0].title == "爱兹拉"
    assert repo.get_page("char:3074").route == "/wiki/char/3074"
    assert repo.resolve_route(entity_id="3074", source_id="", title="") == "/wiki/char/3074"


def test_in_memory_repository_resolves_alias_to_route():
    repo = InMemoryWikiRepository()
    repo.replace_all(
        categories=[],
        pages=[_page()],
        media_links=[WikiMediaLink("char:3074", "media", "media:sha1:portrait", "portrait", 0)],
        relations=[WikiRelation("char:3074", "char:3001", "related", "关联", 0.9)],
        aliases=[WikiAlias("char:3074", "Ezra", "english", 80)],
        link_spans=[WikiLinkSpan("char:3074", "summary", "维尔汀", "/wiki/char/3001", 0.9)],
    )

    assert repo.resolve_route(entity_id="", source_id="", title="Ezra") == "/wiki/char/3074"
    detail = repo.get_page_detail("char:3074")
    assert detail["mediaLinks"][0]["mediaId"] == "media:sha1:portrait"
    assert detail["linkSpans"][0]["targetRoute"] == "/wiki/char/3001"
```

- [ ] **Step 2: Run repository tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_repository.py -q
```

Expected: fail with missing `src.huiji_wiki.repository`.

- [ ] **Step 3: Implement schema and repository**

Create `src/huiji_wiki/repository.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from config.config import Config
from src.huiji_wiki.models import WikiAlias, WikiCategory, WikiLinkSpan, WikiMediaLink, WikiPage, WikiRelation


@dataclass(frozen=True)
class PageList:
    items: list[WikiPage]
    next_cursor: str | None = None


class WikiRepository(Protocol):
    def replace_all(self, categories: list[WikiCategory], pages: list[WikiPage], media_links: list[WikiMediaLink], relations: list[WikiRelation], aliases: list[WikiAlias], link_spans: list[WikiLinkSpan]) -> None: ...
    def list_categories(self) -> list[WikiCategory]: ...
    def list_pages(self, category: str, q: str, page_type: str, limit: int, cursor: str) -> PageList: ...
    def get_page(self, page_id: str) -> WikiPage: ...
    def get_page_detail(self, page_id: str) -> dict: ...
    def resolve_route(self, entity_id: str, source_id: str, title: str) -> str | None: ...


def schema_sql() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS wiki_categories (
          category_key VARCHAR(64) PRIMARY KEY,
          label VARCHAR(128) NOT NULL,
          page_count INT NOT NULL,
          template_group VARCHAR(64) NOT NULL,
          animation_profile VARCHAR(64) NOT NULL,
          theme_token VARCHAR(64) NOT NULL
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS wiki_pages (
          page_id VARCHAR(128) PRIMARY KEY,
          page_type VARCHAR(32) NOT NULL,
          title VARCHAR(255) NOT NULL,
          subtitle VARCHAR(255) NOT NULL,
          category VARCHAR(64) NOT NULL,
          route VARCHAR(255) NOT NULL UNIQUE,
          source_pageid BIGINT NULL,
          source_title VARCHAR(255) NULL,
          content_json JSON NOT NULL,
          updated_at VARCHAR(64) NOT NULL
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS wiki_media_links (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          page_id VARCHAR(128) NOT NULL,
          section_key VARCHAR(64) NOT NULL,
          media_id VARCHAR(128) NOT NULL,
          media_role VARCHAR(32) NOT NULL,
          display_order INT NOT NULL,
          fallback_media_id VARCHAR(128) NOT NULL DEFAULT '',
          INDEX idx_wiki_media_page (page_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS wiki_relations (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          from_page_id VARCHAR(128) NOT NULL,
          to_page_id VARCHAR(128) NOT NULL,
          relation_type VARCHAR(64) NOT NULL,
          label VARCHAR(128) NOT NULL,
          confidence DECIMAL(5,4) NOT NULL,
          INDEX idx_wiki_relation_from (from_page_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS wiki_aliases (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          page_id VARCHAR(128) NOT NULL,
          alias VARCHAR(255) NOT NULL,
          alias_type VARCHAR(32) NOT NULL,
          priority INT NOT NULL,
          INDEX idx_wiki_alias (alias)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS wiki_link_spans (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          page_id VARCHAR(128) NOT NULL,
          section_key VARCHAR(64) NOT NULL,
          text VARCHAR(255) NOT NULL,
          target_route VARCHAR(255) NOT NULL,
          confidence DECIMAL(5,4) NOT NULL,
          INDEX idx_wiki_span_page (page_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
    ]


class InMemoryWikiRepository:
    def __init__(self) -> None:
        self.categories: list[WikiCategory] = []
        self.pages: dict[str, WikiPage] = {}
        self.media_links: list[WikiMediaLink] = []
        self.relations: list[WikiRelation] = []
        self.aliases: list[WikiAlias] = []
        self.link_spans: list[WikiLinkSpan] = []

    def replace_all(self, categories, pages, media_links, relations, aliases, link_spans) -> None:
        self.categories = list(categories)
        self.pages = {page.page_id: page for page in pages}
        self.media_links = list(media_links)
        self.relations = list(relations)
        self.aliases = list(aliases)
        self.link_spans = list(link_spans)

    def list_categories(self) -> list[WikiCategory]:
        return self.categories

    def list_pages(self, category: str, q: str, page_type: str, limit: int, cursor: str) -> PageList:
        items = list(self.pages.values())
        if category:
            items = [page for page in items if page.page_type == category or page.category == category]
        if page_type:
            items = [page for page in items if page.page_type == page_type]
        if q:
            items = [page for page in items if q in page.title or q.lower() in page.subtitle.lower()]
        return PageList(items=items[:limit], next_cursor=None)

    def get_page(self, page_id: str) -> WikiPage:
        return self.pages[page_id]

    def get_page_detail(self, page_id: str) -> dict:
        page = self.get_page(page_id)
        return {
            **page.to_api(),
            "mediaLinks": [link.to_api() for link in self.media_links if link.page_id == page_id],
            "relations": [rel.to_json() for rel in self.relations if rel.from_page_id == page_id],
            "linkSpans": [span.to_json() for span in self.link_spans if span.page_id == page_id],
        }

    def resolve_route(self, entity_id: str, source_id: str, title: str) -> str | None:
        if entity_id:
            for page in self.pages.values():
                if page.page_id.endswith(f":{entity_id}"):
                    return page.route
        if source_id:
            for page in self.pages.values():
                if page.source_title == source_id:
                    return page.route
        if title:
            for alias in sorted(self.aliases, key=lambda item: item.priority, reverse=True):
                if alias.alias == title:
                    return self.pages[alias.page_id].route
        return None
```

Add `MySQLWikiRepository` in the same file after tests pass, using PyMySQL:

```python
class MySQLWikiRepository(InMemoryWikiRepository):
    def __init__(self, cfg: Config) -> None:
        import pymysql

        self._cfg = cfg
        self._pymysql = pymysql

    def _connect(self):
        return self._pymysql.connect(
            host=self._cfg.mysql.host,
            port=self._cfg.mysql.port,
            user=self._cfg.mysql.user,
            password=self._cfg.mysql.password,
            database=self._cfg.mysql.database,
            charset=self._cfg.mysql.charset,
            autocommit=True,
            cursorclass=self._pymysql.cursors.DictCursor,
        )

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for sql in schema_sql():
                    cur.execute(sql)
```

`MySQLWikiRepository` 的读取方法也必须在构建脚本任务中落地；FastAPI runtime 不能依赖空的内存字段。

- [ ] **Step 4: Run repository tests**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_repository.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit checkpoint**

```powershell
git add src/huiji_wiki/repository.py tests/test_huiji_wiki_repository.py
git commit -m "feat: add wiki repository contracts"
```

---

## Task 6: Add Wiki Build CLI

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_huiji_wiki.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_build_script.py`

- [ ] **Step 1: Write failing script test**

Create `tests/test_huiji_wiki_build_script.py`:

```python
from types import SimpleNamespace

from scripts.build_huiji_wiki import format_wiki_build_summary


def test_format_wiki_build_summary_reports_counts():
    dataset = SimpleNamespace(
        categories=[1, 2],
        pages=[1, 2, 3],
        media_links=[1],
        relations=[],
        aliases=[1, 2, 3, 4],
        link_spans=[1],
    )

    assert format_wiki_build_summary(dataset) == [
        "[huiji-wiki] categories=2",
        "[huiji-wiki] pages=3",
        "[huiji-wiki] media_links=1",
        "[huiji-wiki] relations=0",
        "[huiji-wiki] aliases=4",
        "[huiji-wiki] link_spans=1",
    ]
```

- [ ] **Step 2: Run script test and verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_build_script.py -q
```

Expected: fail because `scripts.build_huiji_wiki` is missing.

- [ ] **Step 3: Implement full MySQL replace logic**

Extend `MySQLWikiRepository` in `src/huiji_wiki/repository.py` with helpers, `replace_all()`, and SQL-backed readers:

```python
    def _row_to_page(self, row: dict) -> WikiPage:
        content = row.get("content_json") or "{}"
        if isinstance(content, str):
            content_json = json.loads(content)
        else:
            content_json = dict(content)
        return WikiPage(
            page_id=str(row["page_id"]),
            page_type=str(row.get("page_type", "generic")),
            title=str(row.get("title", "")),
            subtitle=str(row.get("subtitle", "")),
            category=str(row.get("category", "")),
            route=str(row.get("route", "")),
            source_pageid=row.get("source_pageid"),
            source_title=str(row.get("source_title", "")),
            content_json=content_json,
            updated_at=str(row.get("updated_at", "")),
        )

    def replace_all(self, categories, pages, media_links, relations, aliases, link_spans) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                for table in ("wiki_link_spans", "wiki_aliases", "wiki_relations", "wiki_media_links", "wiki_categories", "wiki_pages"):
                    cur.execute(f"DELETE FROM {table}")
                for category in categories:
                    cur.execute(
                        """
                        INSERT INTO wiki_categories
                        (category_key, label, page_count, template_group, animation_profile, theme_token)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            category.key,
                            category.label,
                            category.count,
                            category.template_group,
                            category.animation_profile,
                            category.theme_token,
                        ),
                    )
                for page in pages:
                    cur.execute(
                        """
                        INSERT INTO wiki_pages
                        (page_id, page_type, title, subtitle, category, route, source_pageid, source_title, content_json, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            page.page_id,
                            page.page_type,
                            page.title,
                            page.subtitle,
                            page.category,
                            page.route,
                            page.source_pageid,
                            page.source_title,
                            json.dumps(page.content_json, ensure_ascii=False),
                            page.updated_at,
                        ),
                    )
                for link in media_links:
                    cur.execute(
                        """
                        INSERT INTO wiki_media_links
                        (page_id, section_key, media_id, media_role, display_order, fallback_media_id)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (link.page_id, link.section_key, link.media_id, link.media_role, link.display_order, link.fallback_media_id),
                    )
                for rel in relations:
                    cur.execute(
                        """
                        INSERT INTO wiki_relations
                        (from_page_id, to_page_id, relation_type, label, confidence)
                        VALUES (%s,%s,%s,%s,%s)
                        """,
                        (rel.from_page_id, rel.to_page_id, rel.relation_type, rel.label, rel.confidence),
                    )
                for alias in aliases:
                    cur.execute(
                        """
                        INSERT INTO wiki_aliases
                        (page_id, alias, alias_type, priority)
                        VALUES (%s,%s,%s,%s)
                        """,
                        (alias.page_id, alias.alias, alias.alias_type, alias.priority),
                    )
                for span in link_spans:
                    cur.execute(
                        """
                        INSERT INTO wiki_link_spans
                        (page_id, section_key, text, target_route, confidence)
                        VALUES (%s,%s,%s,%s,%s)
                        """,
                        (span.page_id, span.section_key, span.text, span.target_route, span.confidence),
                    )

    def list_categories(self) -> list[WikiCategory]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT category_key, label, page_count, template_group, animation_profile, theme_token
                    FROM wiki_categories
                    ORDER BY page_count DESC, label ASC
                    """
                )
                rows = cur.fetchall()
        return [
            WikiCategory(
                key=str(row["category_key"]),
                label=str(row["label"]),
                count=int(row["page_count"] or 0),
                template_group=str(row["template_group"]),
                animation_profile=str(row["animation_profile"]),
                theme_token=str(row["theme_token"]),
            )
            for row in rows
        ]

    def list_pages(self, category: str, q: str, page_type: str, limit: int, cursor: str) -> PageList:
        self.ensure_schema()
        filters = []
        params: list[object] = []
        if category:
            filters.append("(page_type = %s OR category = %s)")
            params.extend([category, category])
        if page_type:
            filters.append("page_type = %s")
            params.append(page_type)
        if q:
            filters.append("(title LIKE %s OR subtitle LIKE %s)")
            params.extend([f"%{q}%", f"%{q}%"])
        where = " WHERE " + " AND ".join(filters) if filters else ""
        sql = (
            "SELECT page_id, page_type, title, subtitle, category, route, source_pageid, "
            "source_title, content_json, updated_at FROM wiki_pages"
            f"{where} ORDER BY page_type ASC, title ASC LIMIT %s"
        )
        params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return PageList(items=[self._row_to_page(row) for row in rows], next_cursor=None)

    def get_page(self, page_id: str) -> WikiPage:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT page_id, page_type, title, subtitle, category, route, source_pageid,
                           source_title, content_json, updated_at
                    FROM wiki_pages
                    WHERE page_id = %s
                    """,
                    (page_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(page_id)
        return self._row_to_page(row)

    def get_page_detail(self, page_id: str) -> dict:
        page = self.get_page(page_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT page_id, section_key, media_id, media_role, display_order, fallback_media_id
                    FROM wiki_media_links WHERE page_id = %s ORDER BY display_order ASC
                    """,
                    (page_id,),
                )
                media_links = [WikiMediaLink.from_json(row).to_api() for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT from_page_id, to_page_id, relation_type, label, confidence
                    FROM wiki_relations WHERE from_page_id = %s
                    """,
                    (page_id,),
                )
                relations = [
                    WikiRelation(
                        from_page_id=str(row["from_page_id"]),
                        to_page_id=str(row["to_page_id"]),
                        relation_type=str(row["relation_type"]),
                        label=str(row["label"]),
                        confidence=float(row["confidence"]),
                    ).to_json()
                    for row in cur.fetchall()
                ]
                cur.execute(
                    """
                    SELECT page_id, section_key, text, target_route, confidence
                    FROM wiki_link_spans WHERE page_id = %s
                    """,
                    (page_id,),
                )
                link_spans = [
                    WikiLinkSpan(
                        page_id=str(row["page_id"]),
                        section_key=str(row["section_key"]),
                        text=str(row["text"]),
                        target_route=str(row["target_route"]),
                        confidence=float(row["confidence"]),
                    ).to_json()
                    for row in cur.fetchall()
                ]
        return {**page.to_api(), "mediaLinks": media_links, "relations": relations, "linkSpans": link_spans}

    def resolve_route(self, entity_id: str, source_id: str, title: str) -> str | None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                if entity_id:
                    cur.execute("SELECT route FROM wiki_pages WHERE page_id LIKE %s LIMIT 1", (f"%:{entity_id}",))
                    row = cur.fetchone()
                    if row:
                        return str(row["route"])
                if source_id:
                    cur.execute("SELECT route FROM wiki_pages WHERE source_title = %s LIMIT 1", (source_id,))
                    row = cur.fetchone()
                    if row:
                        return str(row["route"])
                if title:
                    cur.execute(
                        """
                        SELECT p.route
                        FROM wiki_aliases a
                        JOIN wiki_pages p ON p.page_id = a.page_id
                        WHERE a.alias = %s
                        ORDER BY a.priority DESC
                        LIMIT 1
                        """,
                        (title,),
                    )
                    row = cur.fetchone()
                    if row:
                        return str(row["route"])
        return None
```

- [ ] **Step 4: Implement build script**

Create `scripts/build_huiji_wiki.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.builder import build_huiji_corpus
from src.huiji_rag.io import iter_jsonl
from src.huiji_wiki.builder import build_wiki_dataset
from src.huiji_wiki.repository import MySQLWikiRepository


def format_wiki_build_summary(dataset) -> list[str]:
    return [
        f"[huiji-wiki] categories={len(dataset.categories)}",
        f"[huiji-wiki] pages={len(dataset.pages)}",
        f"[huiji-wiki] media_links={len(dataset.media_links)}",
        f"[huiji-wiki] relations={len(dataset.relations)}",
        f"[huiji-wiki] aliases={len(dataset.aliases)}",
        f"[huiji-wiki] link_spans={len(dataset.link_spans)}",
    ]


def main() -> None:
    cfg = get_config()
    paths = build_huiji_corpus(cfg)
    dataset = build_wiki_dataset(
        parents=list(iter_jsonl(paths.parent_blocks)),
        children=list(iter_jsonl(paths.child_blocks)),
        media_assets=list(iter_jsonl(paths.media_assets)),
    )
    repo = MySQLWikiRepository(cfg)
    repo.replace_all(
        categories=dataset.categories,
        pages=dataset.pages,
        media_links=dataset.media_links,
        relations=dataset.relations,
        aliases=dataset.aliases,
        link_spans=dataset.link_spans,
    )
    for line in format_wiki_build_summary(dataset):
        print(line)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run script tests**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_build_script.py tests/test_huiji_wiki_repository.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit checkpoint**

```powershell
git add src/huiji_wiki/repository.py scripts/build_huiji_wiki.py tests/test_huiji_wiki_build_script.py
git commit -m "feat: add huiji wiki mysql build script"
```

---

## Task 7: Add FastAPI Wiki API

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/main.py`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_huiji_wiki_api.py`:

```python
from fastapi.testclient import TestClient

from backend import wiki as wiki_mod
from src.huiji_wiki.models import WikiAlias, WikiCategory, WikiPage
from src.huiji_wiki.repository import InMemoryWikiRepository


def _repo() -> InMemoryWikiRepository:
    repo = InMemoryWikiRepository()
    repo.replace_all(
        categories=[WikiCategory("character", "角色", 1, "character", "entity-list", "character")],
        pages=[
            WikiPage(
                page_id="char:3074",
                page_type="character",
                title="爱兹拉",
                subtitle="Ezra Theodore",
                category="角色",
                route="/wiki/char/3074",
                source_pageid=116433,
                source_title="Data:Char/3074.json",
                content_json={"summary": "爱兹拉"},
                updated_at="2026-07-06T10:00:00+08:00",
            )
        ],
        media_links=[],
        relations=[],
        aliases=[WikiAlias("char:3074", "Ezra", "english", 80)],
        link_spans=[],
    )
    return repo


def test_wiki_categories_endpoint(monkeypatch):
    monkeypatch.setattr(wiki_mod, "get_wiki_repository", lambda: _repo())
    from backend.main import app

    client = TestClient(app)
    res = client.get("/api/wiki/categories")

    assert res.status_code == 200
    assert res.json()["categories"][0]["label"] == "角色"


def test_wiki_pages_and_detail_endpoints(monkeypatch):
    monkeypatch.setattr(wiki_mod, "get_wiki_repository", lambda: _repo())
    from backend.main import app

    client = TestClient(app)
    list_res = client.get("/api/wiki/pages?category=character")
    detail_res = client.get("/api/wiki/pages/char:3074")

    assert list_res.status_code == 200
    assert list_res.json()["items"][0]["route"] == "/wiki/char/3074"
    assert detail_res.status_code == 200
    assert detail_res.json()["title"] == "爱兹拉"


def test_wiki_route_resolve_endpoint(monkeypatch):
    monkeypatch.setattr(wiki_mod, "get_wiki_repository", lambda: _repo())
    from backend.main import app

    client = TestClient(app)
    res = client.get("/api/wiki/routes/resolve?title=Ezra")

    assert res.status_code == 200
    assert res.json()["route"] == "/wiki/char/3074"
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_api.py -q
```

Expected: fail because `backend.wiki` is missing.

- [ ] **Step 3: Add Wiki Pydantic schemas**

Create `backend/wiki_schemas.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WikiCategoryItem(BaseModel):
    key: str
    label: str
    count: int
    templateGroup: str
    animationProfile: str
    themeToken: str


class WikiCategoriesResponse(BaseModel):
    categories: list[WikiCategoryItem]


class WikiPageListItem(BaseModel):
    pageId: str
    pageType: str
    title: str
    subtitle: str
    category: str
    route: str
    thumbnail: str = ""
    summary: str = ""


class WikiPageListResponse(BaseModel):
    items: list[WikiPageListItem]
    nextCursor: str | None = None


class WikiPageDetailResponse(BaseModel):
    pageId: str
    pageType: str
    title: str
    subtitle: str
    category: str
    route: str
    content: dict[str, Any]
    mediaLinks: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    linkSpans: list[dict[str, Any]] = []
    sourcePageid: int | None = None
    sourceTitle: str = ""


class WikiRouteResolveResponse(BaseModel):
    route: str | None = None
    query: str = ""
```

- [ ] **Step 4: Add router**

Create `backend/wiki.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.wiki_schemas import (
    WikiCategoriesResponse,
    WikiPageDetailResponse,
    WikiPageListItem,
    WikiPageListResponse,
    WikiRouteResolveResponse,
)
from config.config import get_config
from src.huiji_wiki.repository import MySQLWikiRepository, WikiRepository

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


def get_wiki_repository() -> WikiRepository:
    return MySQLWikiRepository(get_config())


@router.get("/categories", response_model=WikiCategoriesResponse)
async def wiki_categories() -> WikiCategoriesResponse:
    repo = get_wiki_repository()
    return WikiCategoriesResponse(categories=[category.to_json() for category in repo.list_categories()])


@router.get("/pages", response_model=WikiPageListResponse)
async def wiki_pages(category: str = "", q: str = "", type: str = "", limit: int = 30, cursor: str = "") -> WikiPageListResponse:
    repo = get_wiki_repository()
    page_list = repo.list_pages(category=category, q=q, page_type=type, limit=limit, cursor=cursor)
    items = [
        WikiPageListItem(
            pageId=page.page_id,
            pageType=page.page_type,
            title=page.title,
            subtitle=page.subtitle,
            category=page.category,
            route=page.route,
            thumbnail="",
            summary=str(page.content_json.get("summary", ""))[:180],
        )
        for page in page_list.items
    ]
    return WikiPageListResponse(items=items, nextCursor=page_list.next_cursor)


@router.get("/pages/{page_id:path}", response_model=WikiPageDetailResponse)
async def wiki_page_detail(page_id: str) -> WikiPageDetailResponse:
    repo = get_wiki_repository()
    try:
        detail = repo.get_page_detail(page_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    return WikiPageDetailResponse(**detail)


@router.get("/routes/resolve", response_model=WikiRouteResolveResponse)
async def wiki_route_resolve(source_id: str = "", entity_id: str = "", title: str = "") -> WikiRouteResolveResponse:
    repo = get_wiki_repository()
    route = repo.resolve_route(entity_id=entity_id, source_id=source_id, title=title)
    return WikiRouteResolveResponse(route=route, query=title or entity_id or source_id)


@router.get("/search", response_model=WikiPageListResponse)
async def wiki_search(q: str = "", limit: int = 30) -> WikiPageListResponse:
    return await wiki_pages(q=q, limit=limit)
```

- [ ] **Step 5: Include router in backend main**

Modify `backend/main.py`:

```python
from backend.wiki import router as wiki_router
...
app.include_router(wiki_router)
```

Place `app.include_router(wiki_router)` after CORS setup and before endpoint definitions.

- [ ] **Step 6: Run API tests**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_api.py tests/test_sse.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit checkpoint**

```powershell
git add backend/wiki_schemas.py backend/wiki.py backend/main.py tests/test_huiji_wiki_api.py
git commit -m "feat: add wiki api routes"
```

---

## Task 8: Add Frontend Wiki API Types And Route Split

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/wiki.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/wiki.test.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.tsx`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/App.wiki.test.tsx`

- [ ] **Step 1: Write failing frontend API test**

Create `frontend/react-app/src/api/wiki.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchWikiCategories, fetchWikiPage, fetchWikiPages, resolveWikiRoute } from './wiki'

describe('wiki api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('fetches dynamic wiki categories', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ categories: [{ key: 'character', label: '角色', count: 1, templateGroup: 'character', animationProfile: 'entity-list', themeToken: 'character' }] }),
    } as Response)

    const categories = await fetchWikiCategories()

    expect(fetch).toHaveBeenCalledWith('/api/wiki/categories')
    expect(categories[0].label).toBe('角色')
  })

  it('fetches pages and details with encoded ids', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ pageId: 'char:3074', title: '爱兹拉' }], nextCursor: null }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ pageId: 'char:3074', title: '爱兹拉', content: {} }) } as Response)

    await fetchWikiPages({ category: 'character', q: '爱兹拉' })
    await fetchWikiPage('char:3074')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/wiki/pages?category=character&q=%E7%88%B1%E5%85%B9%E6%8B%89')
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/wiki/pages/char%3A3074')
  })

  it('resolves a wiki route for rag source jumps', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ route: '/wiki/char/3074', query: 'Ezra' }),
    } as Response)

    const result = await resolveWikiRoute({ title: 'Ezra' })

    expect(fetch).toHaveBeenCalledWith('/api/wiki/routes/resolve?title=Ezra')
    expect(result.route).toBe('/wiki/char/3074')
  })
})
```

- [ ] **Step 2: Write failing route split test**

Create `frontend/react-app/src/App.wiki.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./components/wiki/WikiShell', () => ({
  WikiShell: () => <div data-testid="wiki-shell">Wiki</div>,
}))

vi.mock('./api/http', () => ({
  fetchCategories: vi.fn().mockResolvedValue([]),
}))

describe('App wiki route split', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/wiki')
  })

  it('renders the wiki shell outside the snap container on /wiki', () => {
    const { container } = render(<App />)

    expect(screen.getByTestId('wiki-shell')).toBeInTheDocument()
    expect(container.querySelector('.snap-container')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run frontend tests and verify they fail**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/api/wiki.test.ts src/App.wiki.test.tsx --run
```

Expected: fail because `api/wiki` and `WikiShell` do not exist and `App` does not branch on `/wiki`.

- [ ] **Step 4: Add Wiki types**

Create `frontend/react-app/src/types/wiki.ts`:

```ts
export interface WikiCategory {
  key: string
  label: string
  count: number
  templateGroup: string
  animationProfile: string
  themeToken: string
}

export interface WikiPageListItem {
  pageId: string
  pageType: 'character' | 'psychube' | 'story' | 'generic' | string
  title: string
  subtitle: string
  category: string
  route: string
  thumbnail?: string
  summary?: string
}

export interface WikiMediaLink {
  pageId: string
  sectionKey: string
  mediaId: string
  mediaRole: string
  displayOrder: number
  fallbackMediaId?: string
  url?: string
  title?: string
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
  targetRoute: string
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

- [ ] **Step 5: Add Wiki API client**

Create `frontend/react-app/src/api/wiki.ts`:

```ts
import type { WikiCategory, WikiPageDetail, WikiPageListItem } from '../types/wiki'

async function readJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export async function fetchWikiCategories(): Promise<WikiCategory[]> {
  const data = await readJson<{ categories: WikiCategory[] }>('/api/wiki/categories')
  return data.categories
}

export async function fetchWikiPages(params: { category?: string; q?: string; type?: string; limit?: number; cursor?: string } = {}): Promise<{ items: WikiPageListItem[]; nextCursor: string | null }> {
  const search = new URLSearchParams()
  if (params.category) search.set('category', params.category)
  if (params.q) search.set('q', params.q)
  if (params.type) search.set('type', params.type)
  if (params.limit) search.set('limit', String(params.limit))
  if (params.cursor) search.set('cursor', params.cursor)
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return readJson(`/api/wiki/pages${suffix}`)
}

export async function fetchWikiPage(pageId: string): Promise<WikiPageDetail> {
  return readJson(`/api/wiki/pages/${encodeURIComponent(pageId)}`)
}

export async function resolveWikiRoute(params: { sourceId?: string; entityId?: string; title?: string }): Promise<{ route: string | null; query: string }> {
  const search = new URLSearchParams()
  if (params.sourceId) search.set('source_id', params.sourceId)
  if (params.entityId) search.set('entity_id', params.entityId)
  if (params.title) search.set('title', params.title)
  return readJson(`/api/wiki/routes/resolve?${search.toString()}`)
}
```

- [ ] **Step 6: Add temporary WikiShell and App route split**

Create `frontend/react-app/src/components/wiki/WikiShell.tsx`:

```tsx
export function WikiShell() {
  return (
    <main data-testid="wiki-shell" style={{ minHeight: '100vh', background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      Wiki
    </main>
  )
}
```

Modify `frontend/react-app/src/App.tsx`:

```tsx
import { WikiShell } from './components/wiki/WikiShell'
...
export default function App() {
  if (window.location.pathname.startsWith('/wiki')) {
    return <WikiShell />
  }
  ...
}
```

- [ ] **Step 7: Run frontend route/API tests**

Run:

```powershell
npm test -- src/api/wiki.test.ts src/App.wiki.test.tsx --run
```

Expected: all tests pass.

- [ ] **Step 8: Commit checkpoint**

```powershell
git add src/types/wiki.ts src/api/wiki.ts src/api/wiki.test.ts src/App.tsx src/App.wiki.test.tsx src/components/wiki/WikiShell.tsx
git commit -m "feat: add wiki frontend route and api client"
```

---

## Task 9: Implement Wiki Workspace Components

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/constants/layout.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/hooks/useTopNavTrigger.ts`
- Create/Modify: files under `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/**`
- Test: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/wiki/*.test.tsx`

- [ ] **Step 1: Write failing CategoryRail test**

Create `frontend/react-app/src/components/wiki/CategoryRail.test.tsx`:

```tsx
import { act, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CategoryRail } from './CategoryRail'

const categories = [
  { key: 'character', label: '角色', count: 1, templateGroup: 'character', animationProfile: 'entity-list', themeToken: 'character' },
]

describe('CategoryRail', () => {
  it('reveals after the same 700ms hover delay as the top nav', () => {
    vi.useFakeTimers()
    render(<CategoryRail categories={categories} selectedKey="" onSelect={vi.fn()} />)

    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 4 }))
    act(() => vi.advanceTimersByTime(699))
    expect(screen.getByTestId('wiki-category-rail')).toHaveAttribute('data-open', 'false')

    act(() => vi.advanceTimersByTime(1))
    expect(screen.getByTestId('wiki-category-rail')).toHaveAttribute('data-open', 'true')

    vi.useRealTimers()
  })
})
```

- [ ] **Step 2: Write failing CharacterMediaStage test**

Create `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CharacterMediaStage } from './CharacterMediaStage'

describe('CharacterMediaStage', () => {
  it('keeps one stable media frame while switching portrait and live2d fallback', () => {
    render(
      <CharacterMediaStage
        media={[
          { pageId: 'char:3074', sectionKey: 'media', mediaId: 'media:sha1:portrait', mediaRole: 'portrait', displayOrder: 0, url: '/portrait.png', title: '立绘' },
          { pageId: 'char:3074', sectionKey: 'media', mediaId: 'media:sha1:live2d', mediaRole: 'live2d', displayOrder: 1, fallbackMediaId: 'media:sha1:portrait', title: 'Live2D' },
        ]}
      />,
    )

    const frame = screen.getByTestId('character-media-stage')
    expect(frame).toHaveStyle({ minHeight: '58vh' })
    expect(screen.getByAltText('立绘')).toHaveAttribute('src', '/portrait.png')

    fireEvent.click(screen.getByRole('button', { name: 'Live2D' }))

    expect(screen.getByTestId('live2d-fallback')).toBeInTheDocument()
    expect(screen.getByTestId('character-media-stage')).toBe(frame)
  })
})
```

- [ ] **Step 3: Write failing WikiShell test**

Create `frontend/react-app/src/components/wiki/WikiShell.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WikiShell } from './WikiShell'

vi.mock('../../api/wiki', () => ({
  fetchWikiCategories: vi.fn().mockResolvedValue([{ key: 'character', label: '角色', count: 1, templateGroup: 'character', animationProfile: 'entity-list', themeToken: 'character' }]),
  fetchWikiPages: vi.fn().mockResolvedValue({ items: [{ pageId: 'char:3074', pageType: 'character', title: '爱兹拉', subtitle: 'Ezra', category: '角色', route: '/wiki/char/3074', summary: 'summary' }], nextCursor: null }),
  fetchWikiPage: vi.fn().mockResolvedValue({ pageId: 'char:3074', pageType: 'character', title: '爱兹拉', subtitle: 'Ezra', category: '角色', route: '/wiki/char/3074', content: { summary: 'summary', skills: [] }, mediaLinks: [], relations: [], linkSpans: [] }),
}))

describe('WikiShell', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/wiki')
  })

  it('renders the four wiki workspace regions', async () => {
    render(<WikiShell />)

    await waitFor(() => expect(screen.getByText('爱兹拉')).toBeInTheDocument())
    expect(screen.getByTestId('wiki-category-rail')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-page-index')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-reader')).toBeInTheDocument()
    expect(screen.getByTestId('wiki-page-info')).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Run tests and verify they fail**

Run:

```powershell
npm test -- src/components/wiki/CategoryRail.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/WikiShell.test.tsx --run
```

Expected: fail because components are missing or the temporary shell does not render regions.

- [ ] **Step 5: Extract shared hover delay constant**

Modify `frontend/react-app/src/constants/layout.ts`:

```ts
export const TOP_NAV_HEIGHT = 56
export const HOVER_REVEAL_DELAY_MS = 700
```

Modify `frontend/react-app/src/hooks/useTopNavTrigger.ts`:

```ts
import { HOVER_REVEAL_DELAY_MS, TOP_NAV_HEIGHT } from '../constants/layout'
...
}, HOVER_REVEAL_DELAY_MS)
```

Remove the local `TOP_NAV_HOVER_DELAY_MS`.

- [ ] **Step 6: Implement CategoryRail**

Create `frontend/react-app/src/components/wiki/CategoryRail.tsx`:

```tsx
import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { HOVER_REVEAL_DELAY_MS } from '../../constants/layout'
import type { WikiCategory } from '../../types/wiki'

export function CategoryRail({ categories, selectedKey, onSelect }: { categories: WikiCategory[]; selectedKey: string; onSelect: (key: string) => void }) {
  const [open, setOpen] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    const clear = () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
      timer.current = null
    }
    const onMouseMove = (event: MouseEvent) => {
      if (event.clientX <= 12) {
        if (timer.current === null && !open) {
          timer.current = window.setTimeout(() => {
            timer.current = null
            setOpen(true)
          }, HOVER_REVEAL_DELAY_MS)
        }
      } else if (event.clientX > 260) {
        clear()
        setOpen(false)
      }
    }
    window.addEventListener('mousemove', onMouseMove)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      clear()
    }
  }, [open])

  return (
    <aside data-testid="wiki-category-rail" data-open={open ? 'true' : 'false'} style={{ width: open ? 240 : 28, transition: 'width 0.2s', borderRight: '1px solid var(--border-subtle)' }}>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ x: -24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -24, opacity: 0 }} style={{ padding: 16 }}>
            <div style={{ color: 'var(--text-muted)', marginBottom: 12 }}>CATEGORIES</div>
            {categories.map((category) => (
              <button key={category.key} onClick={() => onSelect(category.key)} style={{ display: 'block', width: '100%', padding: '10px 12px', color: selectedKey === category.key ? 'var(--accent-gold)' : 'var(--text-primary)', textAlign: 'left' }}>
                {category.label} · {category.count}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </aside>
  )
}
```

- [ ] **Step 7: Implement core Wiki components**

Create `PageIndex.tsx`, `PageInfo.tsx`, `WikiReader.tsx`, `KeywordText.tsx`, and templates with this minimum behavior:

```tsx
// PageIndex.tsx
import type { WikiPageListItem } from '../../types/wiki'

export function PageIndex({ pages, selectedPageId, onSelect }: { pages: WikiPageListItem[]; selectedPageId: string; onSelect: (pageId: string) => void }) {
  return (
    <aside data-testid="wiki-page-index" style={{ width: 280, borderRight: '1px solid var(--border-subtle)', padding: 16, overflowY: 'auto' }}>
      {pages.map((page) => (
        <button key={page.pageId} onClick={() => onSelect(page.pageId)} style={{ display: 'block', width: '100%', textAlign: 'left', padding: 12, color: selectedPageId === page.pageId ? 'var(--accent-gold)' : 'var(--text-primary)' }}>
          <strong>{page.title}</strong>
          <br />
          <span>{page.subtitle || page.category}</span>
        </button>
      ))}
    </aside>
  )
}
```

```tsx
// PageInfo.tsx
import type { WikiPageDetail } from '../../types/wiki'

export function PageInfo({ page }: { page: WikiPageDetail | null }) {
  return (
    <aside data-testid="wiki-page-info" style={{ width: 220, borderLeft: '1px solid var(--border-subtle)', padding: 16 }}>
      <div>PAGE INFO</div>
      {page && (
        <>
          <strong>{page.sourceTitle || page.route}</strong>
          <p>{page.mediaLinks.length} media</p>
          <p>{page.relations.length} relations</p>
        </>
      )}
    </aside>
  )
}
```

```tsx
// WikiReader.tsx
import type { WikiPageDetail } from '../../types/wiki'
import { CharacterPage } from './templates/CharacterPage'
import { GenericWikiPage } from './templates/GenericWikiPage'
import { PsychubePage } from './templates/PsychubePage'
import { StoryPage } from './templates/StoryPage'

export function WikiReader({ page }: { page: WikiPageDetail | null }) {
  if (!page) return <main data-testid="wiki-reader" style={{ flex: 1, padding: 24 }}>请选择页面</main>
  const template = page.pageType === 'character' ? <CharacterPage page={page} /> : page.pageType === 'psychube' ? <PsychubePage page={page} /> : page.pageType === 'story' ? <StoryPage page={page} /> : <GenericWikiPage page={page} />
  return <main data-testid="wiki-reader" style={{ flex: 1, padding: 24, overflowY: 'auto' }}>{template}</main>
}
```

- [ ] **Step 8: Implement CharacterMediaStage and templates**

Create `CharacterMediaStage.tsx`:

```tsx
import { useMemo, useState } from 'react'
import type { WikiMediaLink } from '../../../types/wiki'

export function CharacterMediaStage({ media }: { media: WikiMediaLink[] }) {
  const ordered = [...media].sort((a, b) => a.displayOrder - b.displayOrder)
  const [role, setRole] = useState(ordered[0]?.mediaRole || 'portrait')
  const active = useMemo(() => ordered.find((item) => item.mediaRole === role) || ordered[0], [ordered, role])
  const roles = Array.from(new Set(ordered.map((item) => item.mediaRole))).concat(ordered.some((item) => item.mediaRole === 'live2d') ? [] : ['live2d'])

  return (
    <section data-testid="character-media-stage" style={{ minHeight: '58vh', border: '1px solid var(--border-card)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: 16 }}>
      <div>
        {roles.map((item) => (
          <button key={item} onClick={() => setRole(item)} style={{ marginRight: 8, color: role === item ? 'var(--accent-gold)' : 'var(--text-secondary)' }}>
            {item === 'portrait' ? '立绘' : item === 'live2d' ? 'Live2D' : item}
          </button>
        ))}
      </div>
      {active?.url ? (
        <img src={active.url} alt={active.title || active.mediaRole} style={{ maxHeight: '52vh', width: '100%', objectFit: 'contain' }} />
      ) : (
        <div data-testid={role === 'live2d' ? 'live2d-fallback' : 'media-fallback'} style={{ minHeight: '52vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {role === 'live2d' ? 'Live2D 暂未接入' : '媒体暂不可用'}
        </div>
      )}
    </section>
  )
}
```

Create `CharacterPage.tsx`:

```tsx
import type { WikiPageDetail } from '../../../types/wiki'
import { CharacterMediaStage } from './CharacterMediaStage'

export function CharacterPage({ page }: { page: WikiPageDetail }) {
  return (
    <article>
      <h1>{page.title}</h1>
      <p>{page.subtitle}</p>
      <CharacterMediaStage media={page.mediaLinks} />
      <section>
        <h2>技能</h2>
        {(page.content.skills as Array<{ title: string; text: string }> | undefined || []).map((skill) => (
          <div key={skill.title}>
            <h3>{skill.title}</h3>
            <p>{skill.text}</p>
          </div>
        ))}
      </section>
    </article>
  )
}
```

Create simple readable templates for `PsychubePage.tsx`, `StoryPage.tsx`, and `GenericWikiPage.tsx`:

```tsx
import type { WikiPageDetail } from '../../../types/wiki'

export function GenericWikiPage({ page }: { page: WikiPageDetail }) {
  return (
    <article>
      <h1>{page.title}</h1>
      <p>{String(page.content.summary || '')}</p>
    </article>
  )
}
```

For `PsychubePage` and `StoryPage`, use the same structure but different exported function names.

- [ ] **Step 9: Replace the temporary WikiShell**

Modify `WikiShell.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { fetchWikiCategories, fetchWikiPage, fetchWikiPages } from '../../api/wiki'
import type { WikiCategory, WikiPageDetail, WikiPageListItem } from '../../types/wiki'
import { CategoryRail } from './CategoryRail'
import { PageIndex } from './PageIndex'
import { PageInfo } from './PageInfo'
import { WikiReader } from './WikiReader'

export function WikiShell() {
  const [categories, setCategories] = useState<WikiCategory[]>([])
  const [selectedCategory, setSelectedCategory] = useState('')
  const [pages, setPages] = useState<WikiPageListItem[]>([])
  const [selectedPageId, setSelectedPageId] = useState('')
  const [page, setPage] = useState<WikiPageDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchWikiCategories()
      .then((items) => {
        setCategories(items)
        setSelectedCategory(items[0]?.key || '')
      })
      .catch(() => setError('Wiki 数据服务未启动'))
  }, [])

  useEffect(() => {
    if (!selectedCategory) return
    fetchWikiPages({ category: selectedCategory })
      .then((data) => {
        setPages(data.items)
        setSelectedPageId(data.items[0]?.pageId || '')
      })
      .catch(() => setError('Wiki 页面列表加载失败'))
  }, [selectedCategory])

  useEffect(() => {
    if (!selectedPageId) return
    fetchWikiPage(selectedPageId)
      .then(setPage)
      .catch(() => setError('Wiki 页面加载失败'))
  }, [selectedPageId])

  return (
    <main data-testid="wiki-shell" style={{ minHeight: '100vh', display: 'flex', background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      <CategoryRail categories={categories} selectedKey={selectedCategory} onSelect={setSelectedCategory} />
      <PageIndex pages={pages} selectedPageId={selectedPageId} onSelect={setSelectedPageId} />
      {error ? <section data-testid="wiki-reader" style={{ flex: 1, padding: 24 }}>{error}</section> : <WikiReader page={page} />}
      <PageInfo page={page} />
    </main>
  )
}
```

- [ ] **Step 10: Run Wiki component tests**

Run:

```powershell
npm test -- src/components/wiki/CategoryRail.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/WikiShell.test.tsx src/hooks/useTopNavTrigger.test.tsx --run
```

Expected: all tests pass.

- [ ] **Step 11: Commit checkpoint**

```powershell
git add src/constants/layout.ts src/hooks/useTopNavTrigger.ts src/components/wiki src/hooks/useTopNavTrigger.test.tsx
git commit -m "feat: build wiki workspace shell"
```

---

## Task 10: Add Wiki Entry Points

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/TopNav.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/Sidebar.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/sections/CategoryPanel.test.tsx`

- [ ] **Step 1: Write failing entry point tests**

Append to `CategoryPanel.test.tsx`:

```tsx
it('renders a wiki CTA on the calendar page', () => {
  const calendarMeta: CategoryMeta = {
    key: '日历',
    title: '日历',
    subtitle: 'Calendar',
    description: '时间记录',
    doc_count: 12,
    cover_prompt: '',
  }

  render(<CategoryPanel meta={calendarMeta} />)

  const link = screen.getByRole('link', { name: /进入WIKI/ })
  expect(link).toHaveAttribute('href', '/wiki')
})
```

Create `frontend/react-app/src/components/TopNav.wiki.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TopNav } from './TopNav'
import { useUIStore } from '../store/uiStore'

describe('TopNav wiki entry', () => {
  it('links to /wiki', () => {
    useUIStore.setState({ topNavVisible: true })
    render(<TopNav />)

    expect(screen.getByRole('link', { name: 'Wiki' })).toHaveAttribute('href', '/wiki')
  })
})
```

- [ ] **Step 2: Run entry point tests and verify they fail**

Run:

```powershell
npm test -- src/components/sections/CategoryPanel.test.tsx src/components/TopNav.wiki.test.tsx --run
```

Expected: fail because links are missing.

- [ ] **Step 3: Add TopNav Wiki link**

Modify `TopNav.tsx`: after existing nav buttons, add:

```tsx
<a
  href="/wiki"
  style={{
    padding: '6px 16px',
    color: 'var(--accent-gold)',
    fontFamily: 'var(--font-body)',
    fontSize: '0.95rem',
    textDecoration: 'none',
  }}
>
  Wiki
</a>
```

- [ ] **Step 4: Add Sidebar Wiki link**

Modify `Sidebar.tsx`: after `LinkList` or before `板块速达`, add:

```tsx
<SectionDivider label="Wiki" />
<a
  href="/wiki"
  style={{
    display: 'block',
    padding: '8px 12px',
    color: 'var(--accent-gold)',
    textDecoration: 'none',
  }}
>
  进入WIKI →
</a>
```

- [ ] **Step 5: Add Calendar CTA**

Modify `CategoryPanel.tsx` inside the returned `<section>` after the main `motion.div`:

```tsx
{(meta.key === '日历' || meta.title === '日历' || meta.key.toLowerCase() === 'calendar') && (
  <a
    href="/wiki"
    aria-label="进入WIKI"
    style={{
      position: 'absolute',
      right: 48,
      bottom: 40,
      color: 'var(--accent-gold)',
      textDecoration: 'none',
      fontFamily: 'var(--font-display)',
      letterSpacing: '0.08em',
    }}
  >
    <span style={{ display: 'block', marginBottom: 6 }}>进入WIKI</span>
    <span aria-hidden="true" style={{ fontSize: 32 }}>→</span>
  </a>
)}
```

- [ ] **Step 6: Run entry point tests**

Run:

```powershell
npm test -- src/components/sections/CategoryPanel.test.tsx src/components/TopNav.wiki.test.tsx --run
```

Expected: all tests pass.

- [ ] **Step 7: Commit checkpoint**

```powershell
git add src/components/TopNav.tsx src/components/TopNav.wiki.test.tsx src/components/Sidebar.tsx src/components/sections/CategoryPanel.tsx src/components/sections/CategoryPanel.test.tsx
git commit -m "feat: add wiki entry points"
```

---

## Final Verification

- [ ] **Run backend tests for Wiki and shared media**

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_wiki_config.py tests/test_minio_shared_upload.py tests/test_huiji_wiki_models.py tests/test_huiji_wiki_builder.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_build_script.py tests/test_huiji_wiki_api.py -q
```

Expected: all selected tests pass.

- [ ] **Run existing RAG/media regression tests touched by this plan**

```powershell
python -m pytest tests/test_huiji_rag_media.py tests/test_huiji_rag_builder.py tests/test_asset_build_script.py tests/test_sse.py -q
```

Expected: all selected tests pass.

- [ ] **Run frontend Wiki tests**

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- src/api/wiki.test.ts src/App.wiki.test.tsx src/components/wiki/CategoryRail.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/WikiShell.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/TopNav.wiki.test.tsx --run
```

Expected: all selected tests pass.

- [ ] **Run frontend build**

```powershell
npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Manual smoke after MySQL is available**

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python scripts\build_huiji_wiki.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
cd frontend\react-app
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173/wiki`.

Expected:

- `/wiki` loads without the snap-container.
- CategoryRail appears after a 700ms left-edge hover.
- PageIndex lists at least one page from MySQL.
- Character page shows a large media frame.
- Live2D tab shows a same-size fallback if no player is available.
- TopNav, Sidebar, and Calendar CTA all navigate to `/wiki`.
- Existing `/ask` and `/ask/stream` endpoints remain usable.

---

## Self-Review Checklist

- Spec coverage:
  - MySQL storage: Task 1, Task 5, Task 6.
  - Shared MinIO and no duplicate prefix: Task 2, Task 4, Task 6 final verification.
  - Wiki API: Task 7.
  - Independent `/wiki`: Task 8.
  - Four-region layout: Task 9.
  - Character media stage and Live2D fallback: Task 9.
  - Three entry points: Task 10.
  - RAG jump reservation: Task 7 route resolve and Task 8 client helper.
  - No Milvus usage for Wiki: all Wiki tasks use MySQL/repository only.
- Red-flag marker scan:
  - No red-flag marker remains in implementation steps.
  - No unspecified "add tests" step without concrete test code.
- Type consistency:
  - Backend API uses camelCase response fields matching `types/wiki.ts`.
  - `pageId`, `pageType`, `mediaLinks`, `linkSpans`, `targetRoute` are consistent across backend and frontend.
  - MinIO key generation remains `reverse1999/{asset_type}/{sha1前两位}/{sha1}.{ext}` from existing `src.huiji_rag.media`.
