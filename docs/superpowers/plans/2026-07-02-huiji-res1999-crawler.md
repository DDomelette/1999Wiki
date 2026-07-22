# 灰机 Wiki 重返未来 1999 爬虫 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个只读、API 优先、可断点续跑、可增量更新的 `res1999.huijiwiki.com` 数据采集器，第一版保存页面源码、`Data:` JSON、资源 manifest 占位和 SQLite 状态。

**Architecture:** 新增 `src/huijiwiki` 包承载爬虫核心逻辑，保持它与现有 RAG、资产和前端代码解耦。CLI 脚本只做参数解析和调用编排；核心模块分别负责 cookie、只读 API 客户端、页面枚举、revision 抓取、资源 manifest、JSONL 输出和 SQLite 状态。

**Tech Stack:** Python 3, requests, python-dotenv, sqlite3, argparse, pytest, MediaWiki API.

---

## Scope Check

本计划只覆盖已批准规格中的“爬虫数据底座”。不包含 RAG 归一化、向量索引、二进制资源下载、前端展示或网页 HTML 抓取。

## File Structure

Project root: `D:/PycharmProjects/nlp/LangChain/1999Search`

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/__init__.py`
  Package marker and public exports.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/errors.py`
  Defines typed crawler exceptions.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/models.py`
  Defines dataclasses for page index, revisions, resources, run config, and fetch decisions.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/state.py`
  Owns SQLite schema, incremental update decisions, run metadata, and resource state.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/jsonl.py`
  Writes append-only JSONL and JSON files, computes content hashes, and blocks secret-bearing records.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/cookies.py`
  Reads `D:/1999WIKI_ROBOT` cookie and env inputs without logging secret values.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/client.py`
  Wraps MediaWiki API requests with host lock, read-only action guard, retry/backoff, and Cloudflare HTML detection.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/enumerator.py`
  Scans selected namespaces with `list=allpages`.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/revisions.py`
  Fetches current revisions in batches of up to 50 page IDs and parses MediaWiki slot content.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/resources.py`
  Builds file resource manifest records from `list=allimages`.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/crawler.py`
  Orchestrates dry run, full run, resume, limit, force, and output writing.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/crawl_huiji_res1999.py`
  Thin CLI entrypoint.
- Create tests:
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_models.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_state.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_jsonl.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_cookies.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_client.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_pipeline.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_cli.py`

No dependency file change is required for the first version because `requests` and `python-dotenv` already exist in `requirements.txt`; `sqlite3`, `argparse`, `json`, `hashlib`, and `pathlib` are standard library modules.

---

### Task 1: Add crawler package models and typed errors

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/__init__.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/errors.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/models.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_huiji_models.py`:

```python
from pathlib import PurePosixPath

import pytest

from src.huijiwiki.errors import ReadOnlyViolation
from src.huijiwiki.models import (
    FetchDecision,
    PageIndexRecord,
    ResourceRecord,
    RevisionRecord,
    build_source_url,
    ensure_read_only_action,
    stable_resource_relpath,
)


def test_build_source_url_encodes_spaces_and_keeps_namespace_colon():
    assert build_source_url("槲寄生 档案") == (
        "https://res1999.huijiwiki.com/wiki/%E6%A7%B2%E5%AF%84%E7%94%9F_%E6%A1%A3%E6%A1%88"
    )
    assert build_source_url("Data:Episode/1402110.json").endswith(
        "/wiki/Data:Episode/1402110.json"
    )


def test_read_only_action_guard_accepts_query_and_rejects_write_actions():
    ensure_read_only_action({"action": "query"})
    ensure_read_only_action({})

    for action in ["edit", "upload", "delete", "move", "purge", "rollback"]:
        with pytest.raises(ReadOnlyViolation):
            ensure_read_only_action({"action": action})


def test_page_revision_and_resource_records_serialize_expected_fields():
    page = PageIndexRecord(
        site="res1999",
        pageid=10,
        ns=3500,
        title="Data:Example.json",
        lastrevid=99,
        length=123,
        touched="2026-07-02T00:00:00Z",
        seen_at="2026-07-02T08:00:00+08:00",
    )
    assert page.to_json()["source_url"].endswith("/wiki/Data:Example.json")

    rev = RevisionRecord(
        site="res1999",
        pageid=10,
        ns=3500,
        title="Data:Example.json",
        revid=99,
        timestamp="2026-07-02T00:00:00Z",
        content_model="json",
        content_format="application/json",
        content='{"name":"test"}',
        fetched_at="2026-07-02T08:00:01+08:00",
    )
    payload = rev.to_json()
    assert payload["content_sha256"]
    assert payload["content"] == '{"name":"test"}'

    relpath = stable_resource_relpath(name="角色立绘.png", sha1="abc123", pageid=None)
    assert PurePosixPath(relpath).parts == ("assets", "files", "abc123", "角色立绘.png")

    resource = ResourceRecord(
        site="res1999",
        source="huiji_file_namespace",
        title="File:角色立绘.png",
        name="角色立绘.png",
        url="https://img.example/角色立绘.png",
        descriptionurl="https://res1999.huijiwiki.com/wiki/File:%E8%A7%92%E8%89%B2",
        mime="image/png",
        size=1024,
        width=512,
        height=512,
        sha1="abc123",
        timestamp="2026-07-02T00:00:00Z",
        local_relpath=relpath,
        download_status="not_downloaded",
        seen_at="2026-07-02T08:00:00+08:00",
    )
    assert resource.to_json()["download_status"] == "not_downloaded"


def test_fetch_decision_is_explicit():
    decision = FetchDecision(pageid=10, should_fetch=True, reason="changed")
    assert decision.to_json() == {
        "pageid": 10,
        "should_fetch": True,
        "reason": "changed",
    }
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.huijiwiki'`.

- [ ] **Step 3: Implement typed errors**

Create `src/huijiwiki/errors.py`:

```python
from __future__ import annotations


class HuijiCrawlerError(RuntimeError):
    """Base error for the HuijiWiki crawler."""


class ReadOnlyViolation(HuijiCrawlerError):
    """Raised when code attempts to use a write-like MediaWiki action."""


class HostViolation(HuijiCrawlerError):
    """Raised when a request target is outside res1999.huijiwiki.com."""


class SessionExpiredError(HuijiCrawlerError):
    """Raised when cookies are missing, expired, or blocked by Cloudflare."""


class ApiResponseError(HuijiCrawlerError):
    """Raised when the MediaWiki API returns an error object."""


class SensitiveValueError(HuijiCrawlerError):
    """Raised when an output record contains secret-bearing fields."""
```

- [ ] **Step 4: Implement dataclasses and guards**

Create `src/huijiwiki/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import quote

from .errors import ReadOnlyViolation

SITE_KEY = "res1999"
API_URL = "https://res1999.huijiwiki.com/api.php"
WIKI_BASE_URL = "https://res1999.huijiwiki.com/wiki/"
READ_ONLY_ACTIONS = {"query"}
WRITE_ACTIONS = {
    "edit",
    "upload",
    "delete",
    "move",
    "purge",
    "rollback",
    "protect",
    "block",
    "unblock",
    "patrol",
    "mergehistory",
    "import",
}


def ensure_read_only_action(params: dict[str, object]) -> None:
    action = str(params.get("action", "query")).lower()
    if action in WRITE_ACTIONS or action not in READ_ONLY_ACTIONS:
        raise ReadOnlyViolation(f"Blocked MediaWiki action: {action}")


def build_source_url(title: str) -> str:
    normalized = title.replace(" ", "_")
    return WIKI_BASE_URL + quote(normalized, safe=":/()_-.,")


def content_sha256(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def stable_resource_relpath(name: str, sha1: str | None, pageid: int | None) -> str:
    key = sha1 or (f"pageid-{pageid}" if pageid is not None else "unknown")
    return str(PurePosixPath("assets") / "files" / key / name)


@dataclass(frozen=True)
class PageIndexRecord:
    site: str
    pageid: int
    ns: int
    title: str
    lastrevid: int
    length: int
    touched: str
    seen_at: str
    status: str = "active"

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_url"] = build_source_url(self.title)
        return payload


@dataclass(frozen=True)
class RevisionRecord:
    site: str
    pageid: int
    ns: int
    title: str
    revid: int
    timestamp: str
    content_model: str
    content_format: str
    content: str
    fetched_at: str

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_url"] = build_source_url(self.title)
        payload["content_sha256"] = content_sha256(self.content)
        return payload


@dataclass(frozen=True)
class ResourceRecord:
    site: str
    source: str
    title: str
    name: str
    url: str
    descriptionurl: str
    mime: str | None
    size: int | None
    width: int | None
    height: int | None
    sha1: str | None
    timestamp: str | None
    local_relpath: str
    download_status: str
    seen_at: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FetchDecision:
    pageid: int
    should_fetch: bool
    reason: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)
```

Create `src/huijiwiki/__init__.py`:

```python
from .models import API_URL, SITE_KEY

__all__ = ["API_URL", "SITE_KEY"]
```

- [ ] **Step 5: Run the model test**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/__init__.py LangChain/1999Search/src/huijiwiki/errors.py LangChain/1999Search/src/huijiwiki/models.py LangChain/1999Search/tests/test_huiji_models.py
git commit -m "feat: add huiji crawler models"
```

---

### Task 2: Add SQLite crawl state store

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/state.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_state.py`

- [ ] **Step 1: Write failing state tests**

Create `tests/test_huiji_state.py`:

```python
from src.huijiwiki.models import PageIndexRecord, ResourceRecord
from src.huijiwiki.state import CrawlStateStore


def _page(pageid: int, revid: int, title: str = "Example") -> PageIndexRecord:
    return PageIndexRecord(
        site="res1999",
        pageid=pageid,
        ns=0,
        title=title,
        lastrevid=revid,
        length=100,
        touched="2026-07-02T00:00:00Z",
        seen_at="2026-07-02T08:00:00+08:00",
    )


def test_state_decides_new_changed_unchanged_and_force(tmp_path):
    db = tmp_path / "crawl_state.sqlite"
    store = CrawlStateStore(db)
    store.initialize()

    assert store.should_fetch(pageid=1, remote_lastrevid=10).reason == "new"

    store.upsert_page_index(_page(1, 10))
    assert store.should_fetch(pageid=1, remote_lastrevid=10).reason == "not_fetched"

    store.mark_revision_fetched(pageid=1, revid=10, content_sha256="abc", stored_in="wikitext.jsonl")
    assert store.should_fetch(pageid=1, remote_lastrevid=10).should_fetch is False
    assert store.should_fetch(pageid=1, remote_lastrevid=10).reason == "unchanged"

    assert store.should_fetch(pageid=1, remote_lastrevid=11).reason == "changed"
    assert store.should_fetch(pageid=1, remote_lastrevid=10, force=True).reason == "force"


def test_state_tracks_renamed_and_missing_pages(tmp_path):
    store = CrawlStateStore(tmp_path / "crawl_state.sqlite")
    store.initialize()
    store.upsert_page_index(_page(2, 20, "Old Title"))
    store.mark_revision_fetched(pageid=2, revid=20, content_sha256="abc", stored_in="wikitext.jsonl")

    store.upsert_page_index(_page(2, 20, "New Title"))
    row = store.get_page(2)
    assert row["title"] == "New Title"
    assert store.should_fetch(pageid=2, remote_lastrevid=20).should_fetch is False

    run_id = store.start_run({"namespaces": [0]})
    store.mark_namespace_scan_started(run_id, 0)
    store.mark_namespace_scan_completed(run_id, 0, seen_pageids=set())
    assert store.get_page(2)["status"] == "missing"


def test_state_upserts_resource_manifest_status(tmp_path):
    store = CrawlStateStore(tmp_path / "crawl_state.sqlite")
    store.initialize()

    resource = ResourceRecord(
        site="res1999",
        source="huiji_file_namespace",
        title="File:Example.png",
        name="Example.png",
        url="https://img.example/Example.png",
        descriptionurl="https://res1999.huijiwiki.com/wiki/File:Example.png",
        mime="image/png",
        size=1024,
        width=512,
        height=512,
        sha1="abc123",
        timestamp="2026-07-02T00:00:00Z",
        local_relpath="assets/files/abc123/Example.png",
        download_status="not_downloaded",
        seen_at="2026-07-02T08:00:00+08:00",
    )
    store.upsert_resource(resource)

    row = store.get_resource("Example.png")
    assert row["sha1"] == "abc123"
    assert row["download_status"] == "not_downloaded"
```

- [ ] **Step 2: Run the failing state tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_state.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.huijiwiki.state'`.

- [ ] **Step 3: Implement SQLite schema and state API**

Create `src/huijiwiki/state.py` with these public methods:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import FetchDecision, PageIndexRecord, ResourceRecord


class CrawlStateStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    pageid INTEGER PRIMARY KEY,
                    ns INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    lastrevid INTEGER NOT NULL,
                    length INTEGER NOT NULL,
                    touched TEXT NOT NULL,
                    status TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_fetched_revid INTEGER
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    revid INTEGER PRIMARY KEY,
                    pageid INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    stored_in TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS resources (
                    name TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    mime TEXT,
                    size INTEGER,
                    width INTEGER,
                    height INTEGER,
                    sha1 TEXT,
                    timestamp TEXT,
                    local_relpath TEXT NOT NULL,
                    download_status TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS namespace_scans (
                    run_id INTEGER NOT NULL,
                    ns INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    seen_pageids_json TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY (run_id, ns)
                );
                """
            )

    def start_run(self, config: dict[str, object]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (status, config_json) VALUES (?, ?)",
                ("running", json.dumps(config, ensure_ascii=False, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, summary: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status=?, finished_at=CURRENT_TIMESTAMP, summary_json=? WHERE run_id=?",
                (status, json.dumps(summary, ensure_ascii=False, sort_keys=True), run_id),
            )

    def upsert_page_index(self, record: PageIndexRecord) -> None:
        with self._connect() as conn:
            existing = conn.execute("SELECT first_seen_at, last_fetched_revid FROM pages WHERE pageid=?", (record.pageid,)).fetchone()
            first_seen_at = existing["first_seen_at"] if existing else record.seen_at
            last_fetched_revid = existing["last_fetched_revid"] if existing else None
            conn.execute(
                """
                INSERT OR REPLACE INTO pages
                (pageid, ns, title, lastrevid, length, touched, status, first_seen_at, last_seen_at, last_fetched_revid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.pageid,
                    record.ns,
                    record.title,
                    record.lastrevid,
                    record.length,
                    record.touched,
                    record.status,
                    first_seen_at,
                    record.seen_at,
                    last_fetched_revid,
                ),
            )

    def should_fetch(self, pageid: int, remote_lastrevid: int, force: bool = False) -> FetchDecision:
        if force:
            return FetchDecision(pageid=pageid, should_fetch=True, reason="force")
        row = self.get_page(pageid)
        if row is None:
            return FetchDecision(pageid=pageid, should_fetch=True, reason="new")
        fetched = row["last_fetched_revid"]
        if fetched is None:
            return FetchDecision(pageid=pageid, should_fetch=True, reason="not_fetched")
        if int(fetched) != int(remote_lastrevid):
            return FetchDecision(pageid=pageid, should_fetch=True, reason="changed")
        return FetchDecision(pageid=pageid, should_fetch=False, reason="unchanged")

    def mark_revision_fetched(self, pageid: int, revid: int, content_sha256: str, stored_in: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO revisions (revid, pageid, content_sha256, stored_in) VALUES (?, ?, ?, ?)",
                (revid, pageid, content_sha256, stored_in),
            )
            conn.execute("UPDATE pages SET last_fetched_revid=? WHERE pageid=?", (revid, pageid))

    def mark_namespace_scan_started(self, run_id: int, ns: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO namespace_scans (run_id, ns, status, seen_pageids_json) VALUES (?, ?, ?, ?)",
                (run_id, ns, "running", "[]"),
            )

    def mark_namespace_scan_completed(self, run_id: int, ns: int, seen_pageids: set[int]) -> None:
        seen_json = json.dumps(sorted(seen_pageids))
        with self._connect() as conn:
            conn.execute(
                "UPDATE namespace_scans SET status=?, seen_pageids_json=? WHERE run_id=? AND ns=?",
                ("completed", seen_json, run_id, ns),
            )
            if seen_pageids:
                placeholders = ",".join("?" for _ in seen_pageids)
                conn.execute(
                    f"UPDATE pages SET status='missing' WHERE ns=? AND pageid NOT IN ({placeholders})",
                    (ns, *sorted(seen_pageids)),
                )
            else:
                conn.execute("UPDATE pages SET status='missing' WHERE ns=?", (ns,))

    def upsert_resource(self, record: ResourceRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO resources
                (name, title, url, mime, size, width, height, sha1, timestamp, local_relpath, download_status, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.name,
                    record.title,
                    record.url,
                    record.mime,
                    record.size,
                    record.width,
                    record.height,
                    record.sha1,
                    record.timestamp,
                    record.local_relpath,
                    record.download_status,
                    record.seen_at,
                ),
            )

    def get_page(self, pageid: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM pages WHERE pageid=?", (pageid,)).fetchone()

    def get_resource(self, name: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM resources WHERE name=?", (name,)).fetchone()
```

- [ ] **Step 4: Run state tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/state.py LangChain/1999Search/tests/test_huiji_state.py
git commit -m "feat: add huiji crawl state store"
```

---

### Task 3: Add safe JSON and JSONL output writers

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/jsonl.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_jsonl.py`

- [ ] **Step 1: Write failing JSONL tests**

Create `tests/test_huiji_jsonl.py`:

```python
import json

import pytest

from src.huijiwiki.errors import SensitiveValueError
from src.huijiwiki.jsonl import JsonlWriter, write_json_file


def test_jsonl_writer_appends_utf8_records(tmp_path):
    path = tmp_path / "pages.jsonl"
    writer = JsonlWriter(path)
    writer.write({"title": "槲寄生", "pageid": 1})
    writer.write({"title": "Data:Example.json", "pageid": 2})

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"title": "槲寄生", "pageid": 1},
        {"title": "Data:Example.json", "pageid": 2},
    ]


def test_json_writer_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "siteinfo.json"
    write_json_file(path, {"query": {"general": {"sitename": "重返未来1999WIKI"}}})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["query"]["general"]["sitename"] == "重返未来1999WIKI"


def test_jsonl_writer_rejects_secret_like_keys(tmp_path):
    writer = JsonlWriter(tmp_path / "errors.jsonl")
    with pytest.raises(SensitiveValueError):
        writer.write({"cookie": "secret-cookie-value"})
    with pytest.raises(SensitiveValueError):
        writer.write({"nested": {"password": "secret-password"}})
```

- [ ] **Step 2: Run the failing JSONL tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_jsonl.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.huijiwiki.jsonl'`.

- [ ] **Step 3: Implement JSON writers with secret-field blocking**

Create `src/huijiwiki/jsonl.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import SensitiveValueError

SENSITIVE_KEY_PARTS = ("password", "passwd", "cookie", "secret", "token")
SAFE_KEY_EXCEPTIONS = {"content_sha256", "sha1", "download_status"}


def _assert_no_sensitive_fields(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered not in SAFE_KEY_EXCEPTIONS and any(part in lowered for part in SENSITIVE_KEY_PARTS):
                raise SensitiveValueError(f"Refusing to write sensitive field: {path + str(key)}")
            _assert_no_sensitive_fields(item, f"{path}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_sensitive_fields(item, f"{path}{index}.")


class JsonlWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict[str, Any]) -> None:
        _assert_no_sensitive_fields(record)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def write_json_file(path: str | Path, payload: dict[str, Any]) -> None:
    _assert_no_sensitive_fields(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
```

- [ ] **Step 4: Run JSONL tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_jsonl.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/jsonl.py LangChain/1999Search/tests/test_huiji_jsonl.py
git commit -m "feat: add huiji jsonl writers"
```

---

### Task 4: Add cookie and environment loading

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/cookies.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_cookies.py`

- [ ] **Step 1: Write failing cookie loader tests**

Create `tests/test_huiji_cookies.py`:

```python
import json

from src.huijiwiki.cookies import CookieLoader


def test_cookie_loader_reads_json_config_without_exposing_values(tmp_path):
    robot_root = tmp_path / "robot"
    config_dir = robot_root / "huijiwiki_bot_gui_v0.3.46"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.dat"
    config_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "huiji_session", "value": "session-value", "domain": ".huijiwiki.com"},
                    {"name": "__cf_bm", "value": "cf-value", "domain": ".huijiwiki.com"},
                    {"name": "huijiUserName", "value": "POTATO BOT", "domain": ".huijiwiki.com"},
                ]
            }
        ),
        encoding="utf-8",
    )

    loader = CookieLoader(robot_root)
    cookies = loader.load_cookies()

    assert cookies["huiji_session"] == "session-value"
    assert cookies["__cf_bm"] == "cf-value"
    assert "session-value" not in loader.describe()
    assert "cf-value" not in loader.describe()
    assert "huiji_session" in loader.describe()


def test_cookie_loader_reads_env_credentials_without_logging_values(tmp_path):
    robot_root = tmp_path / "robot"
    robot_root.mkdir()
    (robot_root / ".env").write_text("USER_NAME=POTATO BOT\nPASSWORD=secret-password\n", encoding="utf-8")

    loader = CookieLoader(robot_root)
    creds = loader.load_credentials()

    assert creds["USER_NAME"] == "POTATO BOT"
    assert creds["PASSWORD"] == "secret-password"
    assert "secret-password" not in loader.describe()


def test_cookie_loader_accepts_explicit_config_path(tmp_path):
    config_path = tmp_path / "config.dat"
    config_path.write_text("huiji_session=line-session\n__cf_bm=line-cf\n", encoding="utf-8")

    loader = CookieLoader(tmp_path / "missing-root", config_path=config_path)
    assert loader.load_cookies() == {"huiji_session": "line-session", "__cf_bm": "line-cf"}
```

- [ ] **Step 2: Run the failing cookie tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_cookies.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.huijiwiki.cookies'`.

- [ ] **Step 3: Implement cookie loader**

Create `src/huijiwiki/cookies.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


class CookieLoader:
    def __init__(self, robot_root: str | Path, config_path: str | Path | None = None, env_path: str | Path | None = None) -> None:
        self.robot_root = Path(robot_root)
        self.config_path = Path(config_path) if config_path else self.robot_root / "huijiwiki_bot_gui_v0.3.46" / "config.dat"
        self.env_path = Path(env_path) if env_path else self.robot_root / ".env"
        self._cookie_names: list[str] = []
        self._credential_keys: list[str] = []

    def load_cookies(self) -> dict[str, str]:
        text = self.config_path.read_text(encoding="utf-8")
        cookies = self._parse_config_text(text)
        self._cookie_names = sorted(cookies)
        return cookies

    def load_credentials(self) -> dict[str, str]:
        values = {key: str(value) for key, value in dotenv_values(self.env_path).items() if value is not None}
        self._credential_keys = sorted(values)
        return values

    def describe(self) -> str:
        return (
            f"CookieLoader(config_path={self.config_path}, "
            f"cookie_names={self._cookie_names}, credential_keys={self._credential_keys})"
        )

    def _parse_config_text(self, text: str) -> dict[str, str]:
        stripped = text.strip()
        if not stripped:
            return {}
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return self._parse_line_cookies(stripped)
        return self._parse_json_cookies(payload)

    def _parse_json_cookies(self, payload: Any) -> dict[str, str]:
        cookies: dict[str, str] = {}
        if isinstance(payload, dict):
            if isinstance(payload.get("cookies"), list):
                for item in payload["cookies"]:
                    if isinstance(item, dict) and item.get("name") and item.get("value") is not None:
                        cookies[str(item["name"])] = str(item["value"])
            else:
                for key, value in payload.items():
                    if isinstance(value, str):
                        cookies[str(key)] = value
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("name") and item.get("value") is not None:
                    cookies[str(item["name"])] = str(item["value"])
        return cookies

    def _parse_line_cookies(self, text: str) -> dict[str, str]:
        cookies: dict[str, str] = {}
        for line in text.splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
                continue
            name, value = cleaned.split("=", 1)
            cookies[name.strip()] = value.strip()
        return cookies
```

- [ ] **Step 4: Run cookie tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_cookies.py -q
```

Expected: PASS.

- [ ] **Step 5: Run a local cookie-shape probe without printing values**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -c "from src.huijiwiki.cookies import CookieLoader; l=CookieLoader(r'D:\1999WIKI_ROBOT'); c=l.load_cookies(); print(sorted(c)); print(l.describe())"
```

Expected: prints cookie names and loader description only. Output must not contain cookie values or password values.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/cookies.py LangChain/1999Search/tests/test_huiji_cookies.py
git commit -m "feat: add huiji cookie loader"
```

---

### Task 5: Add read-only MediaWiki API client

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/client.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_client.py`

- [ ] **Step 1: Write failing API client tests**

Create `tests/test_huiji_client.py`:

```python
import pytest

from src.huijiwiki.client import HuijiApiClient
from src.huijiwiki.errors import ApiResponseError, HostViolation, ReadOnlyViolation, SessionExpiredError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else ""
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


def test_client_blocks_write_action_and_wrong_host():
    client = HuijiApiClient(session=FakeSession([]), sleep_fn=lambda _: None)

    with pytest.raises(ReadOnlyViolation):
        client.query({"action": "edit"})

    with pytest.raises(HostViolation):
        client._guard_url("https://example.com/api.php")


def test_client_defaults_to_query_and_returns_json():
    session = FakeSession([FakeResponse(payload={"query": {"general": {"sitename": "x"}}})])
    client = HuijiApiClient(session=session, sleep_fn=lambda _: None)

    payload = client.query({"meta": "siteinfo"})

    assert payload["query"]["general"]["sitename"] == "x"
    assert session.calls[0][1]["action"] == "query"
    assert session.calls[0][1]["format"] == "json"


def test_client_detects_cloudflare_html_and_403():
    html = "<html><title>Just a moment...</title></html>"
    client = HuijiApiClient(session=FakeSession([FakeResponse(status_code=403, text=html, headers={"content-type": "text/html"})]), sleep_fn=lambda _: None)

    with pytest.raises(SessionExpiredError):
        client.query({"meta": "siteinfo"})


def test_client_raises_mediawiki_api_error():
    client = HuijiApiClient(session=FakeSession([FakeResponse(payload={"error": {"code": "badvalue", "info": "Bad value"}})]), sleep_fn=lambda _: None)

    with pytest.raises(ApiResponseError):
        client.query({"meta": "siteinfo"})


def test_client_retries_transient_status_then_succeeds():
    sleeps = []
    session = FakeSession([
        FakeResponse(status_code=503, payload={"error": "temporary"}),
        FakeResponse(payload={"query": {"ok": True}}),
    ])
    client = HuijiApiClient(session=session, sleep_fn=sleeps.append, max_retries=2)

    assert client.query({"meta": "siteinfo"}) == {"query": {"ok": True}}
    assert sleeps == [1.0]
    assert len(session.calls) == 2
```

- [ ] **Step 2: Run the failing API client tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_client.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.huijiwiki.client'`.

- [ ] **Step 3: Implement API client guards, retries, and JSON parsing**

Create `src/huijiwiki/client.py`:

```python
from __future__ import annotations

import time
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from .errors import ApiResponseError, HostViolation, SessionExpiredError
from .models import API_URL, ensure_read_only_action

TRANSIENT_STATUS_CODES = {429, 502, 503, 504}


class HuijiApiClient:
    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        session: Any | None = None,
        api_url: str = API_URL,
        timeout: float = 30.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_retries: int = 5,
    ) -> None:
        self.api_url = api_url
        self.timeout = timeout
        self.sleep_fn = sleep_fn
        self.max_retries = max_retries
        self.session = session or requests.Session()
        if cookies and hasattr(self.session, "cookies"):
            self.session.cookies.update(cookies)
        if hasattr(self.session, "headers"):
            self.session.headers.update({"User-Agent": "1999SearchHuijiCrawler/1.0 read-only"})

    def _guard_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "res1999.huijiwiki.com" or parsed.path != "/api.php":
            raise HostViolation(f"Blocked API host: {url}")

    def query(self, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        request_params.setdefault("action", "query")
        request_params.setdefault("format", "json")
        request_params.setdefault("formatversion", "2")
        ensure_read_only_action(request_params)
        self._guard_url(self.api_url)

        for attempt in range(self.max_retries + 1):
            response = self.session.get(self.api_url, params=request_params, timeout=self.timeout)
            if response.status_code in TRANSIENT_STATUS_CODES and attempt < self.max_retries:
                self.sleep_fn(float(2**attempt))
                continue
            return self._parse_response(response)
        raise SessionExpiredError("Request retry loop ended without a usable response")

    def _parse_response(self, response: Any) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "") if hasattr(response, "headers") else ""
        text = getattr(response, "text", "")
        if response.status_code == 403 or "Just a moment" in text or "cloudflare" in text.lower():
            raise SessionExpiredError("Cloudflare or login session blocked the API response")
        if "html" in content_type.lower() and "json" not in content_type.lower():
            raise SessionExpiredError("Expected JSON but received HTML")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SessionExpiredError("Expected JSON but response could not be decoded") from exc
        if isinstance(payload, dict) and "error" in payload:
            error = payload["error"]
            if isinstance(error, dict):
                raise ApiResponseError(f"{error.get('code')}: {error.get('info')}")
            raise ApiResponseError(str(error))
        if response.status_code >= 400:
            raise ApiResponseError(f"HTTP {response.status_code}")
        return payload

    def get_siteinfo(self) -> dict[str, Any]:
        return self.query(
            {
                "meta": "siteinfo",
                "siprop": "general|namespaces|statistics",
            }
        )
```

- [ ] **Step 4: Run API client tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_client.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/client.py LangChain/1999Search/tests/test_huiji_client.py
git commit -m "feat: add read-only huiji api client"
```

---

### Task 6: Add namespace enumeration and revision fetching

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/enumerator.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/revisions.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_pipeline.py`

- [ ] **Step 1: Write failing enumerator and revision tests**

Create `tests/test_huiji_pipeline.py` with these first tests:

```python
from src.huijiwiki.enumerator import PageEnumerator
from src.huijiwiki.revisions import RevisionFetcher, parse_revision_page


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.params = []

    def query(self, params):
        self.params.append(dict(params))
        return self.responses.pop(0)


def test_page_enumerator_follows_allpages_continue():
    client = FakeClient(
        [
            {
                "continue": {"apcontinue": "B"},
                "query": {"allpages": [{"pageid": 1, "ns": 0, "title": "A", "lastrevid": 10, "length": 5, "touched": "2026-07-02T00:00:00Z"}]},
            },
            {
                "query": {"allpages": [{"pageid": 2, "ns": 0, "title": "B", "lastrevid": 20, "length": 6, "touched": "2026-07-02T00:00:00Z"}]},
            },
        ]
    )
    records = list(PageEnumerator(client, seen_at_fn=lambda: "2026-07-02T08:00:00+08:00").iter_namespace(0))

    assert [record.pageid for record in records] == [1, 2]
    assert client.params[0]["aplimit"] == "500"
    assert client.params[1]["apcontinue"] == "B"


def test_revision_fetcher_batches_by_50_and_parses_slots():
    pages = [
        {
            "pageid": 1,
            "ns": 0,
            "title": "A",
            "revisions": [
                {
                    "revid": 10,
                    "timestamp": "2026-07-02T00:00:00Z",
                    "slots": {"main": {"contentmodel": "wikitext", "contentformat": "text/x-wiki", "content": "hello"}},
                }
            ],
        }
    ]
    client = FakeClient([{"query": {"pages": pages}}])

    records = list(RevisionFetcher(client, fetched_at_fn=lambda: "2026-07-02T08:00:00+08:00").fetch_pageids([1]))

    assert records[0].content == "hello"
    assert records[0].revid == 10
    assert client.params[0]["pageids"] == "1"
    assert client.params[0]["rvprop"] == "ids|timestamp|content"


def test_parse_revision_page_accepts_legacy_star_content():
    page = {
        "pageid": 2,
        "ns": 10,
        "title": "Template:X",
        "revisions": [{"revid": 30, "timestamp": "2026-07-02T00:00:00Z", "*": "legacy content"}],
    }

    record = parse_revision_page(page, fetched_at="2026-07-02T08:00:00+08:00")

    assert record.content == "legacy content"
    assert record.content_model == "wikitext"
```

- [ ] **Step 2: Run failing pipeline tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_pipeline.py -q
```

Expected: FAIL with missing `enumerator` and `revisions` modules.

- [ ] **Step 3: Implement namespace enumeration**

Create `src/huijiwiki/enumerator.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

from .models import PageIndexRecord, SITE_KEY


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class PageEnumerator:
    def __init__(self, client, seen_at_fn: Callable[[], str] = now_local_iso) -> None:
        self.client = client
        self.seen_at_fn = seen_at_fn

    def iter_namespace(self, namespace: int) -> Iterator[PageIndexRecord]:
        params: dict[str, object] = {
            "list": "allpages",
            "apnamespace": namespace,
            "aplimit": "500",
            "apfilterredir": "nonredirects",
            "approp": "ids|title",
        }
        while True:
            payload = self.client.query(params)
            for page in payload.get("query", {}).get("allpages", []):
                yield PageIndexRecord(
                    site=SITE_KEY,
                    pageid=int(page["pageid"]),
                    ns=int(page.get("ns", namespace)),
                    title=str(page["title"]),
                    lastrevid=int(page.get("lastrevid", 0)),
                    length=int(page.get("length", 0)),
                    touched=str(page.get("touched", "")),
                    seen_at=self.seen_at_fn(),
                )
            cont = payload.get("continue", {})
            if "apcontinue" not in cont:
                break
            params["apcontinue"] = cont["apcontinue"]
```

If a live dry run shows `list=allpages` does not return `lastrevid`, `length`, or `touched` with this parameter set, adjust `PageEnumerator` in the implementation task to follow enumeration with a batched `prop=info` call. Keep the public output fields unchanged.

- [ ] **Step 4: Implement current revision fetching**

Create `src/huijiwiki/revisions.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from datetime import datetime

from .models import RevisionRecord, SITE_KEY


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def batched(values: Iterable[int], size: int) -> Iterator[list[int]]:
    batch: list[int] = []
    for value in values:
        batch.append(int(value))
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def parse_revision_page(page: dict, fetched_at: str) -> RevisionRecord:
    revisions = page.get("revisions") or []
    rev = revisions[0] if revisions else {}
    slot = (rev.get("slots") or {}).get("main") or {}
    content = slot.get("content", rev.get("*", ""))
    return RevisionRecord(
        site=SITE_KEY,
        pageid=int(page["pageid"]),
        ns=int(page.get("ns", 0)),
        title=str(page["title"]),
        revid=int(rev.get("revid", 0)),
        timestamp=str(rev.get("timestamp", "")),
        content_model=str(slot.get("contentmodel", page.get("contentmodel", "wikitext"))),
        content_format=str(slot.get("contentformat", "text/x-wiki")),
        content=str(content),
        fetched_at=fetched_at,
    )


class RevisionFetcher:
    def __init__(self, client, fetched_at_fn: Callable[[], str] = now_local_iso, batch_size: int = 50) -> None:
        self.client = client
        self.fetched_at_fn = fetched_at_fn
        self.batch_size = batch_size

    def fetch_pageids(self, pageids: Iterable[int]) -> Iterator[RevisionRecord]:
        for batch in batched(pageids, self.batch_size):
            payload = self.client.query(
                {
                    "prop": "revisions",
                    "pageids": "|".join(str(pageid) for pageid in batch),
                    "rvprop": "ids|timestamp|content",
                    "rvslots": "main",
                }
            )
            pages = payload.get("query", {}).get("pages", [])
            if isinstance(pages, dict):
                pages = pages.values()
            for page in pages:
                yield parse_revision_page(page, fetched_at=self.fetched_at_fn())
```

- [ ] **Step 5: Run pipeline tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/enumerator.py LangChain/1999Search/src/huijiwiki/revisions.py LangChain/1999Search/tests/test_huiji_pipeline.py
git commit -m "feat: add huiji page and revision readers"
```

---

### Task 7: Add resource manifest builder

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/resources.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_pipeline.py`

- [ ] **Step 1: Add failing resource manifest tests**

Append to `tests/test_huiji_pipeline.py`:

```python
from src.huijiwiki.resources import ResourceManifestBuilder


def test_resource_manifest_builder_follows_allimages_continue_and_does_not_download():
    client = FakeClient(
        [
            {
                "continue": {"aicontinue": "B"},
                "query": {
                    "allimages": [
                        {
                            "name": "A.png",
                            "title": "File:A.png",
                            "url": "https://img.example/A.png",
                            "descriptionurl": "https://res1999.huijiwiki.com/wiki/File:A.png",
                            "mime": "image/png",
                            "size": 100,
                            "width": 64,
                            "height": 64,
                            "sha1": "sha-a",
                            "timestamp": "2026-07-02T00:00:00Z",
                        }
                    ]
                },
            },
            {"query": {"allimages": []}},
        ]
    )

    resources = list(ResourceManifestBuilder(client, seen_at_fn=lambda: "2026-07-02T08:00:00+08:00").iter_resources())

    assert len(resources) == 1
    assert resources[0].download_status == "not_downloaded"
    assert resources[0].local_relpath == "assets/files/sha-a/A.png"
    assert client.params[0]["aiprop"] == "url|size|mime|dimensions|sha1|timestamp"
    assert client.params[1]["aicontinue"] == "B"
```

- [ ] **Step 2: Run failing resource test**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_pipeline.py::test_resource_manifest_builder_follows_allimages_continue_and_does_not_download -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.huijiwiki.resources'`.

- [ ] **Step 3: Implement resource manifest builder**

Create `src/huijiwiki/resources.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

from .models import ResourceRecord, SITE_KEY, stable_resource_relpath


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ResourceManifestBuilder:
    def __init__(self, client, seen_at_fn: Callable[[], str] = now_local_iso) -> None:
        self.client = client
        self.seen_at_fn = seen_at_fn

    def iter_resources(self) -> Iterator[ResourceRecord]:
        params: dict[str, object] = {
            "list": "allimages",
            "ailimit": "500",
            "aiprop": "url|size|mime|dimensions|sha1|timestamp",
        }
        while True:
            payload = self.client.query(params)
            for item in payload.get("query", {}).get("allimages", []):
                name = str(item["name"])
                sha1 = item.get("sha1")
                yield ResourceRecord(
                    site=SITE_KEY,
                    source="huiji_file_namespace",
                    title=str(item.get("title", f"File:{name}")),
                    name=name,
                    url=str(item.get("url", "")),
                    descriptionurl=str(item.get("descriptionurl", "")),
                    mime=item.get("mime"),
                    size=int(item["size"]) if item.get("size") is not None else None,
                    width=int(item["width"]) if item.get("width") is not None else None,
                    height=int(item["height"]) if item.get("height") is not None else None,
                    sha1=str(sha1) if sha1 else None,
                    timestamp=item.get("timestamp"),
                    local_relpath=stable_resource_relpath(name=name, sha1=str(sha1) if sha1 else None, pageid=None),
                    download_status="not_downloaded",
                    seen_at=self.seen_at_fn(),
                )
            cont = payload.get("continue", {})
            if "aicontinue" not in cont:
                break
            params["aicontinue"] = cont["aicontinue"]
```

- [ ] **Step 4: Run full pipeline tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/resources.py LangChain/1999Search/tests/test_huiji_pipeline.py
git commit -m "feat: add huiji resource manifest builder"
```

---

### Task 8: Add crawler orchestration and CLI

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huijiwiki/crawler.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/crawl_huiji_res1999.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_cli.py`

- [ ] **Step 1: Write failing orchestration and CLI tests**

Create `tests/test_huiji_cli.py`:

```python
import json

from src.huijiwiki.crawler import CrawlConfig, run_crawl


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_siteinfo(self):
        return {"query": {"general": {"sitename": "重返未来1999WIKI"}, "statistics": {"pages": 140334}}}

    def query(self, params):
        self.calls.append(dict(params))
        if params.get("list") == "allpages":
            return {
                "query": {
                    "allpages": [
                        {"pageid": 1, "ns": 0, "title": "槲寄生", "lastrevid": 10, "length": 100, "touched": "2026-07-02T00:00:00Z"}
                    ]
                }
            }
        if params.get("prop") == "revisions":
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "ns": 0,
                            "title": "槲寄生",
                            "revisions": [
                                {
                                    "revid": 10,
                                    "timestamp": "2026-07-02T00:00:00Z",
                                    "slots": {"main": {"contentmodel": "wikitext", "contentformat": "text/x-wiki", "content": "角色资料"}},
                                }
                            ],
                        }
                    ]
                }
            }
        if params.get("list") == "allimages":
            return {
                "query": {
                    "allimages": [
                        {
                            "name": "A.png",
                            "title": "File:A.png",
                            "url": "https://img.example/A.png",
                            "descriptionurl": "https://res1999.huijiwiki.com/wiki/File:A.png",
                            "mime": "image/png",
                            "size": 100,
                            "width": 64,
                            "height": 64,
                            "sha1": "sha-a",
                            "timestamp": "2026-07-02T00:00:00Z",
                        }
                    ]
                }
            }
        raise AssertionError(params)


def test_run_crawl_writes_expected_outputs_and_resume_skips_unchanged(tmp_path):
    out = tmp_path / "res1999"
    config = CrawlConfig(
        robot_root=tmp_path / "robot",
        out=out,
        namespaces=[0],
        include_file_manifest=True,
        sleep=0.0,
        resume=True,
        dry_run=False,
        limit=None,
        force=False,
    )

    first = run_crawl(config, client=FakeClient())
    second = run_crawl(config, client=FakeClient())

    assert first["fetched_revisions"] == 1
    assert second["fetched_revisions"] == 0
    assert json.loads((out / "siteinfo.json").read_text(encoding="utf-8"))["query"]["statistics"]["pages"] == 140334
    assert (out / "pages.jsonl").exists()
    assert (out / "wikitext.jsonl").exists()
    assert (out / "data_pages.jsonl").exists()
    assert (out / "resources_manifest.jsonl").exists()
    assert (out / "errors.jsonl").exists()
    assert (out / "crawl_state.sqlite").exists()
    assert "角色资料" in (out / "wikitext.jsonl").read_text(encoding="utf-8")
    assert "not_downloaded" in (out / "resources_manifest.jsonl").read_text(encoding="utf-8")


def test_dry_run_writes_siteinfo_but_no_revision_content(tmp_path):
    out = tmp_path / "res1999"
    config = CrawlConfig(
        robot_root=tmp_path / "robot",
        out=out,
        namespaces=[0],
        include_file_manifest=False,
        sleep=0.0,
        resume=True,
        dry_run=True,
        limit=None,
        force=False,
    )

    summary = run_crawl(config, client=FakeClient())

    assert summary["dry_run"] is True
    assert (out / "siteinfo.json").exists()
    assert not (out / "wikitext.jsonl").exists()
```

- [ ] **Step 2: Run failing orchestration tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_cli.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.huijiwiki.crawler'`.

- [ ] **Step 3: Implement crawler orchestration**

Create `src/huijiwiki/crawler.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .client import HuijiApiClient
from .cookies import CookieLoader
from .enumerator import PageEnumerator
from .jsonl import JsonlWriter, write_json_file
from .models import content_sha256
from .resources import ResourceManifestBuilder
from .revisions import RevisionFetcher
from .state import CrawlStateStore


@dataclass(frozen=True)
class CrawlConfig:
    robot_root: Path
    out: Path
    namespaces: list[int]
    include_file_manifest: bool
    sleep: float
    resume: bool
    dry_run: bool
    limit: int | None
    force: bool
    config_path: Path | None = None

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["robot_root"] = str(self.robot_root)
        payload["out"] = str(self.out)
        payload["config_path"] = str(self.config_path) if self.config_path else None
        return payload


def build_default_client(config: CrawlConfig) -> HuijiApiClient:
    loader = CookieLoader(config.robot_root, config_path=config.config_path)
    cookies = loader.load_cookies()
    return HuijiApiClient(cookies=cookies)


def run_crawl(config: CrawlConfig, client: HuijiApiClient | None = None) -> dict[str, object]:
    out = Path(config.out)
    out.mkdir(parents=True, exist_ok=True)
    state = CrawlStateStore(out / "crawl_state.sqlite")
    state.initialize()
    run_id = state.start_run(config.to_json())

    api = client or build_default_client(config)
    siteinfo = api.get_siteinfo()
    write_json_file(out / "siteinfo.json", siteinfo)

    summary = {
        "dry_run": config.dry_run,
        "namespaces": config.namespaces,
        "indexed_pages": 0,
        "fetch_candidates": 0,
        "fetched_revisions": 0,
        "resources_indexed": 0,
    }
    if config.dry_run:
        state.finish_run(run_id, "completed", summary)
        return summary

    pages_writer = JsonlWriter(out / "pages.jsonl")
    wikitext_writer = JsonlWriter(out / "wikitext.jsonl")
    data_writer = JsonlWriter(out / "data_pages.jsonl")
    errors_writer = JsonlWriter(out / "errors.jsonl")

    enumerator = PageEnumerator(api)
    fetcher = RevisionFetcher(api)
    pageids_to_fetch: list[int] = []

    try:
        for ns in config.namespaces:
            seen: set[int] = set()
            state.mark_namespace_scan_started(run_id, ns)
            for page in enumerator.iter_namespace(ns):
                pages_writer.write(page.to_json())
                state.upsert_page_index(page)
                seen.add(page.pageid)
                summary["indexed_pages"] += 1
                decision = state.should_fetch(page.pageid, page.lastrevid, force=config.force)
                if decision.should_fetch:
                    pageids_to_fetch.append(page.pageid)
                    summary["fetch_candidates"] += 1
                    if config.limit is not None and len(pageids_to_fetch) >= config.limit:
                        break
            state.mark_namespace_scan_completed(run_id, ns, seen)
            if config.limit is not None and len(pageids_to_fetch) >= config.limit:
                break

        for revision in fetcher.fetch_pageids(pageids_to_fetch):
            payload = revision.to_json()
            wikitext_writer.write(payload)
            if revision.ns == 3500 or revision.title.startswith("Data:"):
                data_payload = dict(payload)
                try:
                    json.loads(revision.content)
                    data_payload["json_valid"] = True
                    data_payload["json_error"] = None
                except json.JSONDecodeError as exc:
                    data_payload["json_valid"] = False
                    data_payload["json_error"] = str(exc)
                data_writer.write(data_payload)
            state.mark_revision_fetched(
                pageid=revision.pageid,
                revid=revision.revid,
                content_sha256=content_sha256(revision.content),
                stored_in="wikitext.jsonl",
            )
            summary["fetched_revisions"] += 1

        if config.include_file_manifest:
            resource_writer = JsonlWriter(out / "resources_manifest.jsonl")
            for resource in ResourceManifestBuilder(api).iter_resources():
                resource_writer.write(resource.to_json())
                state.upsert_resource(resource)
                summary["resources_indexed"] += 1

        state.finish_run(run_id, "completed", summary)
        return summary
    except Exception as exc:
        errors_writer.write({"stage": "run_crawl", "error_type": type(exc).__name__, "message": str(exc)})
        state.finish_run(run_id, "failed", summary)
        raise
```

- [ ] **Step 4: Implement CLI entrypoint**

Create `scripts/crawl_huiji_res1999.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huijiwiki.crawler import CrawlConfig, run_crawl


def parse_namespaces(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only crawler for res1999.huijiwiki.com")
    parser.add_argument("--robot-root", type=Path, default=Path(r"D:\1999WIKI_ROBOT"))
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "huiji" / "res1999")
    parser.add_argument("--namespaces", type=parse_namespaces, default=parse_namespaces("0,3500,10,828,14"))
    parser.add_argument("--include-file-manifest", action="store_true")
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = CrawlConfig(
        robot_root=args.robot_root,
        out=args.out,
        namespaces=args.namespaces,
        include_file_manifest=args.include_file_manifest,
        sleep=args.sleep,
        resume=args.resume,
        dry_run=args.dry_run,
        limit=args.limit,
        force=args.force,
        config_path=args.config,
    )
    summary = run_crawl(config)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run orchestration tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Run all crawler unit tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_*.py -q
```

Expected: PASS for all `test_huiji_*.py` tests.

- [ ] **Step 7: Commit Task 8**

Run:

```powershell
git add LangChain/1999Search/src/huijiwiki/crawler.py LangChain/1999Search/scripts/crawl_huiji_res1999.py LangChain/1999Search/tests/test_huiji_cli.py
git commit -m "feat: add huiji crawler cli"
```

---

### Task 9: Validate against the live read-only API with small runs

**Files:**
- No code files created.
- Output directory created by commands: `D:/PycharmProjects/nlp/LangChain/1999Search/data/huiji/res1999`

- [ ] **Step 1: Run the crawler test suite again before live API use**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_*.py -q
```

Expected: PASS.

- [ ] **Step 2: Run dry run**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python scripts\crawl_huiji_res1999.py --robot-root D:\1999WIKI_ROBOT --out data\huiji\res1999 --namespaces 0,3500 --dry-run --resume
```

Expected: JSON summary with `"dry_run": true`; `data/huiji/res1999/siteinfo.json` exists; no revision content file is required for dry run.

- [ ] **Step 3: Run a 20-page limited crawl**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python scripts\crawl_huiji_res1999.py --robot-root D:\1999WIKI_ROBOT --out data\huiji\res1999 --namespaces 0,3500 --include-file-manifest --limit 20 --sleep 1.0 --resume
```

Expected: summary reports `fetched_revisions` between 1 and 20; output directory contains `pages.jsonl`, `wikitext.jsonl`, `data_pages.jsonl`, `resources_manifest.jsonl`, `errors.jsonl`, and `crawl_state.sqlite`.

- [ ] **Step 4: Run the same 20-page command again to verify skip behavior**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python scripts\crawl_huiji_res1999.py --robot-root D:\1999WIKI_ROBOT --out data\huiji\res1999 --namespaces 0,3500 --include-file-manifest --limit 20 --sleep 1.0 --resume
```

Expected: summary reports `fetched_revisions` as `0` when the first 20 page `lastrevid` values have not changed.

- [ ] **Step 5: Inspect output for forbidden secret strings**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
rg -n "PASSWORD|USER_NAME|huiji_session|__cf_bm|huijiToken|cookie" data\huiji\res1999
```

Expected: no matches for secret-bearing values. A match on field names in code or docs is not relevant here because the command scans the crawl output directory only.

- [ ] **Step 6: Commit validation notes if code needed a live API adjustment**

If live API response shape required a code change, run the relevant `test_huiji_*.py` test file, then commit only the adjusted crawler files and tests:

```powershell
git status --short
git add LangChain/1999Search/src/huijiwiki LangChain/1999Search/tests/test_huiji_*.py LangChain/1999Search/scripts/crawl_huiji_res1999.py
git commit -m "fix: align huiji crawler with api response shape"
```

Expected: commit is needed only when implementation changed. If no code changed, skip this commit step.

---

## Final Verification

Run from repository root:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python -m pytest tests/test_huiji_*.py -q
```

Expected: all crawler unit tests pass.

Run the dry run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python scripts\crawl_huiji_res1999.py --robot-root D:\1999WIKI_ROBOT --out data\huiji\res1999 --namespaces 0,3500 --dry-run --resume
```

Expected: command exits with status 0 and writes `data/huiji/res1999/siteinfo.json`.

Run the limited crawl:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda run -n 1999wiki python scripts\crawl_huiji_res1999.py --robot-root D:\1999WIKI_ROBOT --out data\huiji\res1999 --namespaces 0,3500 --include-file-manifest --limit 20 --sleep 1.0 --resume
```

Expected: command exits with status 0 and writes the first-version output files without downloading binary assets.

## Requirement Coverage

- Read-only guard: Task 1 and Task 5.
- Target host lock: Task 5.
- Cookie and `.env` handling without secret logging: Task 4 and Task 9.
- Siteinfo output: Task 8 and Task 9.
- Namespace page index: Task 6 and Task 8.
- Current revision source output: Task 6 and Task 8.
- `Data:` JSON parse status: Task 8.
- Resource manifest without binary download: Task 7 and Task 8.
- SQLite incremental skip by `lastrevid`: Task 2 and Task 8.
- Resume validation: Task 8 and Task 9.
- Cloudflare/session HTML detection: Task 5.
- Small live validation before full crawl: Task 9.
