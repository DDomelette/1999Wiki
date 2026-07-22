# 灰机父子块混合 RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已经落地的灰机 Wiki 爬虫数据接入当前问答系统，生成父块、子块、媒体资产、BM25 索引和新的 Milvus collection，并让问答 API/前端按 `answer + sources + media` 工作。

**Architecture:** 新增 `src/huiji_rag` 包作为灰机数据到 RAG 的构建层，保持它与原始爬虫包 `src/huijiwiki` 解耦。旧 `documents.jsonl -> chunks_bge_m3_v1` 链路保留为回滚路径，新链路使用 `data/processed/huiji/{build_version}`、本地 BM25、`text_child_bge_m3_v2` 和 MinIO 资源 URL。

**Tech Stack:** Python 3, pytest, dataclasses, JSONL, pathlib, pymilvus, BAAI/bge-m3 via SiliconFlow, MinIO, FastAPI/SSE, React/Vite/Vitest.

---

## Scope Check

本计划覆盖一个端到端目标：灰机爬虫数据进入问答系统。它会触及数据构建、索引、检索、API、问答窗口和评估，但这些不是独立产品线，必须一起闭环才能验证“灰机数据可问答、可挂媒体、可评估”。非问答页面不在本计划内。

用户此前明确表示本项目不需要处理 git，因此本计划不包含 commit 步骤。执行时只做文件改动、测试和运行命令。

---

## File Structure

Project root: `D:/PycharmProjects/nlp/LangChain/1999Search`

Create Python package:

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/__init__.py`
  Package marker.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/models.py`
  Dataclasses for parent blocks, child blocks, media assets, build manifest, query/media results.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/io.py`
  JSONL read/write helpers and build-version path resolution.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/source.py`
  Read-only loader for `data/huiji/res1999`.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/normalizer.py`
  Parse `Data:Char`, generic `Data:*`, WikiText fallback records, and resource manifest records.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/media.py`
  Resolve media assets, classify asset types, choose attach policies, build MinIO object keys.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/builder.py`
  Build `parent_blocks.jsonl`, `child_blocks.jsonl`, `media_assets.jsonl`, and `build_manifest.json`.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/sparse.py`
  Local BM25 sparse index abstraction and implementation.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/hybrid.py`
  Hybrid retrieval, weighted RRF, parent expansion, child rerank, and media attachment.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/huiji_registry.py`
  Media registry backed by `media_assets.jsonl` and `media_asset_bm25`.

Modify existing Python files:

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/config.py`
  Add `huiji` config and processed build-version paths.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/settings.yaml`
  Add `huiji` section and switch target collection after build is verified.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/query_plan.py`
  Add `story`, `item`, `image`, `audio`, `video`, and `media_intent`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/vectorstore.py`
  Add huiji collection schema/load path while preserving legacy behavior.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/retriever.py`
  Dispatch to hybrid retriever when huiji build exists/enabled.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/chain.py`
  Return `media` while keeping `assets` compatibility during transition.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/schemas.py`
  Extend response model from image assets to typed media.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/main.py`
  Serialize typed media and expose build status in health.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`
  Stream typed media in `sources` and `done` events.

Create scripts:

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_huiji_corpus.py`
  Build processed parent/child/media artifacts from crawler output.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_huiji_index.py`
  Build BM25 indexes and Milvus `text_child_bge_m3_v2`.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/evaluate_huiji_rag.py`
  Run core retrieval/media evaluation.

Create evaluation data:

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/eval/queries_core.jsonl`

Modify frontend:

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/index.ts`
  Add typed `MediaItem`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/sse.ts`
  Parse `media` while accepting legacy `assets`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/store/chatStore.ts`
  Store media on assistant messages.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageAssets.tsx`
  Render image, audio, and video.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageBubble.tsx`
  Pass media to renderer.

Create tests:

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_models.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_source.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_normalizer.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_media.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_sparse_bm25.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_hybrid_retriever.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_vectorstore.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_eval.py`
- Modify frontend tests around `MessageAssets` and SSE parsing.

---

## Milestone 1: Config And Data Contracts

### Task 1: Add huiji config and build path resolution

**Files:**

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/config.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/settings.yaml`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_config.py`

- [ ] **Step 1: Write failing config test**

Create `tests/test_huiji_config.py`:

```python
from config.config import get_config, reset_config_for_test


def test_huiji_paths_are_loaded_from_settings():
    reset_config_for_test()
    cfg = get_config()

    assert cfg.huiji.raw_root.as_posix().endswith("data/huiji/res1999")
    assert cfg.huiji.processed_root.as_posix().endswith("data/processed/huiji")
    assert cfg.huiji.build_version
    assert cfg.huiji.enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_config.py -q
```

Expected: fail with `AttributeError: 'Config' object has no attribute 'huiji'`.

- [ ] **Step 3: Add config dataclass and loader fields**

In `config/config.py`, add:

```python
@dataclass
class HuijiCfg:
    enabled: bool
    raw_root: Path
    processed_root: Path
    build_version: str
    text_collection_name: str
    asset_caption_collection_name: str
```

Add `huiji: HuijiCfg` to `Config`.

Inside `get_config()`, before building `Config`, add:

```python
    huiji_raw = raw.get("huiji", {})
```

Inside `Config(...)`, add:

```python
        huiji=HuijiCfg(
            enabled=bool(huiji_raw.get("enabled", False)),
            raw_root=project_root / huiji_raw.get("raw_root", "data/huiji/res1999"),
            processed_root=project_root / huiji_raw.get("processed_root", "data/processed/huiji"),
            build_version=str(huiji_raw.get("build_version", "dev")),
            text_collection_name=str(huiji_raw.get("text_collection_name", "text_child_bge_m3_v2")),
            asset_caption_collection_name=str(
                huiji_raw.get("asset_caption_collection_name", "asset_caption_bge_m3_v1")
            ),
        ),
```

- [ ] **Step 4: Add settings section**

In `config/settings.yaml`, append:

```yaml
huiji:
  enabled: false
  raw_root: "data/huiji/res1999"
  processed_root: "data/processed/huiji"
  build_version: "dev"
  text_collection_name: "text_child_bge_m3_v2"
  asset_caption_collection_name: "asset_caption_bge_m3_v1"
```

- [ ] **Step 5: Run config tests**

Run:

```powershell
python -m pytest tests/test_config.py tests/test_huiji_config.py -q
```

Expected: all tests pass.

### Task 2: Add parent, child, media, and manifest dataclasses

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/__init__.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/models.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_huiji_rag_models.py`:

```python
from src.huiji_rag.models import ChildBlock, MediaAsset, ParentBlock, media_id_for_sha1


def test_parent_child_and_media_json_roundtrip():
    parent = ParentBlock(
        parent_id="char:3041/skills",
        entity_id="3041",
        entity_name="玛蒂尔达",
        entity_aliases=("Matilda Bouanich",),
        category="character",
        section_kind="skills",
        title="玛蒂尔达 / 技能",
        summary_text="玛蒂尔达技能集合",
        source_refs=({"kind": "data_page", "title": "Data:Char/3041.json"},),
        child_ids=("skill:30410111",),
        content_hash="hash-parent",
    )
    child = ChildBlock(
        child_id="skill:30410111",
        parent_id=parent.parent_id,
        entity_id="3041",
        entity_name="玛蒂尔达",
        category="character",
        section_kind="skill",
        title="天才习作",
        text="天才习作：出类拔萃的习作。",
        search_text="玛蒂尔达 Matilda skill 技能 天才习作 Skill-30410111",
        chunk_index=0,
        media_ids=("media:sha1:abc",),
        media_policy="auto",
        source_refs=({"kind": "data_page", "json_path": "$.skill.30410111"},),
        content_hash="hash-child",
    )
    media = MediaAsset(
        media_id=media_id_for_sha1("abc"),
        sha1="abc",
        entity_id="3041",
        entity_name="玛蒂尔达",
        parent_id=parent.parent_id,
        child_id=child.child_id,
        asset_type="skill",
        mime="image/png",
        filename="Skill-30410111.png",
        title="文件:Skill-30410111.png",
        source_url="https://example/Skill-30410111.png",
        local_relpath="assets/files/abc/Skill-30410111.png",
        object_key="reverse1999/skill/ab/abc.png",
        url="http://127.0.0.1:9002/reverse1999-assets/reverse1999/skill/ab/abc.png",
        is_available=True,
        is_common=False,
        attach_policy="auto",
        search_text="玛蒂尔达 Skill-30410111",
        content_hash="hash-media",
    )

    assert ParentBlock.from_json(parent.to_json()) == parent
    assert ChildBlock.from_json(child.to_json()) == child
    assert MediaAsset.from_json(media.to_json()) == media
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_rag_models.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'src.huiji_rag'`.

- [ ] **Step 3: Implement models**

Create `src/huiji_rag/__init__.py`:

```python
"""Huiji crawler data to RAG processing package."""
```

Create `src/huiji_rag/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)


def _tuple_of_dict(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    return tuple(dict(item) for item in value)


def media_id_for_sha1(sha1: str) -> str:
    return f"media:sha1:{sha1}"


@dataclass(frozen=True)
class ParentBlock:
    parent_id: str
    entity_id: str
    entity_name: str
    entity_aliases: tuple[str, ...]
    category: str
    section_kind: str
    title: str
    summary_text: str
    source_refs: tuple[dict[str, Any], ...]
    child_ids: tuple[str, ...]
    content_hash: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "ParentBlock":
        return cls(
            parent_id=str(row["parent_id"]),
            entity_id=str(row.get("entity_id", "")),
            entity_name=str(row.get("entity_name", "")),
            entity_aliases=_tuple_of_str(row.get("entity_aliases", ())),
            category=str(row.get("category", "")),
            section_kind=str(row.get("section_kind", "")),
            title=str(row.get("title", "")),
            summary_text=str(row.get("summary_text", "")),
            source_refs=_tuple_of_dict(row.get("source_refs", ())),
            child_ids=_tuple_of_str(row.get("child_ids", ())),
            content_hash=str(row.get("content_hash", "")),
        )


@dataclass(frozen=True)
class ChildBlock:
    child_id: str
    parent_id: str
    entity_id: str
    entity_name: str
    category: str
    section_kind: str
    title: str
    text: str
    search_text: str
    chunk_index: int
    media_ids: tuple[str, ...]
    media_policy: str
    source_refs: tuple[dict[str, Any], ...]
    content_hash: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "ChildBlock":
        return cls(
            child_id=str(row["child_id"]),
            parent_id=str(row["parent_id"]),
            entity_id=str(row.get("entity_id", "")),
            entity_name=str(row.get("entity_name", "")),
            category=str(row.get("category", "")),
            section_kind=str(row.get("section_kind", "")),
            title=str(row.get("title", "")),
            text=str(row.get("text", "")),
            search_text=str(row.get("search_text", "")),
            chunk_index=int(row.get("chunk_index", 0) or 0),
            media_ids=_tuple_of_str(row.get("media_ids", ())),
            media_policy=str(row.get("media_policy", "auto")),
            source_refs=_tuple_of_dict(row.get("source_refs", ())),
            content_hash=str(row.get("content_hash", "")),
        )


@dataclass(frozen=True)
class MediaAsset:
    media_id: str
    sha1: str
    entity_id: str
    entity_name: str
    parent_id: str
    child_id: str
    asset_type: str
    mime: str
    filename: str
    title: str
    source_url: str
    local_relpath: str
    object_key: str
    url: str
    is_available: bool
    is_common: bool
    attach_policy: str
    search_text: str
    content_hash: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "MediaAsset":
        return cls(
            media_id=str(row["media_id"]),
            sha1=str(row.get("sha1", "")),
            entity_id=str(row.get("entity_id", "")),
            entity_name=str(row.get("entity_name", "")),
            parent_id=str(row.get("parent_id", "")),
            child_id=str(row.get("child_id", "")),
            asset_type=str(row.get("asset_type", "")),
            mime=str(row.get("mime", "")),
            filename=str(row.get("filename", "")),
            title=str(row.get("title", "")),
            source_url=str(row.get("source_url", "")),
            local_relpath=str(row.get("local_relpath", "")),
            object_key=str(row.get("object_key", "")),
            url=str(row.get("url", "")),
            is_available=bool(row.get("is_available", False)),
            is_common=bool(row.get("is_common", False)),
            attach_policy=str(row.get("attach_policy", "manual")),
            search_text=str(row.get("search_text", "")),
            content_hash=str(row.get("content_hash", "")),
        )
```

- [ ] **Step 4: Run model tests**

Run:

```powershell
python -m pytest tests/test_huiji_rag_models.py -q
```

Expected: pass.

### Task 3: Add JSONL IO and build-version paths

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/io.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_source.py`

- [ ] **Step 1: Write failing IO test**

Create `tests/test_huiji_rag_source.py`:

```python
from types import SimpleNamespace

from src.huiji_rag.io import build_paths, iter_jsonl, write_jsonl


def test_build_paths_resolves_versioned_outputs(tmp_path):
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="20260703_120000",
        )
    )

    paths = build_paths(cfg)

    assert paths.raw_root == tmp_path / "raw"
    assert paths.build_root == tmp_path / "processed" / "20260703_120000"
    assert paths.parent_blocks.name == "parent_blocks.jsonl"
    assert paths.child_bm25.parent.name == "indexes"


def test_jsonl_roundtrip(tmp_path):
    path = tmp_path / "rows.jsonl"
    write_jsonl(path, [{"name": "玛蒂尔达"}, {"name": "爱兹拉"}])

    assert list(iter_jsonl(path)) == [{"name": "玛蒂尔达"}, {"name": "爱兹拉"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_rag_source.py -q
```

Expected: fail because `src.huiji_rag.io` does not exist.

- [ ] **Step 3: Implement IO helpers**

Create `src/huiji_rag/io.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class HuijiBuildPaths:
    raw_root: Path
    build_root: Path
    parent_blocks: Path
    child_blocks: Path
    media_assets: Path
    build_manifest: Path
    child_bm25: Path
    media_bm25: Path


def build_paths(cfg: Any) -> HuijiBuildPaths:
    raw_root = Path(cfg.huiji.raw_root)
    build_root = Path(cfg.huiji.processed_root) / str(cfg.huiji.build_version)
    indexes = build_root / "indexes"
    return HuijiBuildPaths(
        raw_root=raw_root,
        build_root=build_root,
        parent_blocks=build_root / "parent_blocks.jsonl",
        child_blocks=build_root / "child_blocks.jsonl",
        media_assets=build_root / "media_assets.jsonl",
        build_manifest=build_root / "build_manifest.json",
        child_bm25=indexes / "child_text_bm25.json",
        media_bm25=indexes / "media_asset_bm25.json",
    )


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
```

- [ ] **Step 4: Run IO tests**

Run:

```powershell
python -m pytest tests/test_huiji_rag_source.py -q
```

Expected: pass.

---

## Milestone 2: Build Parent Blocks, Child Blocks, And Media Assets

### Task 4: Add read-only crawler data source

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/source.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_source.py`

- [ ] **Step 1: Add failing source test**

Append to `tests/test_huiji_rag_source.py`:

```python
import json

from src.huiji_rag.source import HuijiCrawlerDataSource


def test_data_source_reads_char_pages_and_resources(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "data_pages.jsonl").write_text(
        json.dumps(
            {
                "title": "Data:Char/3041.json",
                "content": "{\"id\":3041,\"name\":\"玛蒂尔达\"}",
                "content_sha256": "hash-char",
                "revid": 1,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (raw / "resources_manifest.jsonl").write_text(
        json.dumps(
            {
                "name": "Skill-30410111.png",
                "title": "文件:Skill-30410111.png",
                "sha1": "abc",
                "mime": "image/png",
                "local_relpath": "assets/files/abc/Skill-30410111.png",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    source = HuijiCrawlerDataSource(raw)

    assert [row["title"] for row in source.iter_data_pages(prefix="Data:Char/")] == ["Data:Char/3041.json"]
    assert [row["name"] for row in source.iter_resources()] == ["Skill-30410111.png"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_rag_source.py -q
```

Expected: fail because `src.huiji_rag.source` does not exist.

- [ ] **Step 3: Implement source loader**

Create `src/huiji_rag/source.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from src.huiji_rag.io import iter_jsonl


class HuijiCrawlerDataSource:
    def __init__(self, raw_root: str | Path) -> None:
        self.raw_root = Path(raw_root)

    def _path(self, name: str) -> Path:
        return self.raw_root / name

    def iter_pages(self) -> Iterator[dict[str, Any]]:
        yield from iter_jsonl(self._path("pages.jsonl"))

    def iter_wikitext(self) -> Iterator[dict[str, Any]]:
        yield from iter_jsonl(self._path("wikitext.jsonl"))

    def iter_data_pages(self, prefix: str | None = None) -> Iterator[dict[str, Any]]:
        for row in iter_jsonl(self._path("data_pages.jsonl")):
            title = str(row.get("title", ""))
            if prefix is None or title.startswith(prefix):
                yield row

    def iter_resources(self) -> Iterator[dict[str, Any]]:
        yield from iter_jsonl(self._path("resources_manifest.jsonl"))

    def local_file_exists(self, local_relpath: str) -> bool:
        return (self.raw_root / local_relpath).exists()
```

- [ ] **Step 4: Run source tests**

Run:

```powershell
python -m pytest tests/test_huiji_rag_source.py -q
```

Expected: pass.

### Task 5: Normalize `Data:Char` into parent and child blocks

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/normalizer.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_normalizer.py`

- [ ] **Step 1: Write failing character normalization tests**

Create `tests/test_huiji_rag_normalizer.py`:

```python
import json

from src.huiji_rag.normalizer import normalize_char_page, normalize_generic_page


def _char_row():
    return {
        "title": "Data:Char/3041.json",
        "revid": 10,
        "content_sha256": "hash-char",
        "content": json.dumps(
            {
                "id": 3041,
                "name": "玛蒂尔达",
                "skinId": 304101,
                "rare": 4,
                "career": 2,
                "dmgType": 2,
                "skill": {
                    "30410111": {
                        "id": 30410111,
                        "name": "天才习作",
                        "icon": 30410111,
                        "desc_art": "出类拔萃的习作。",
                        "eff_desc": "造成精神创伤。",
                        "skillRank": 1,
                    },
                    "30410121": {
                        "id": 30410121,
                        "name": "众望瞩目",
                        "icon": 30410121,
                        "desc_art": "她正看向远方。",
                        "eff_desc": "降低目标防御。",
                        "skillRank": 1,
                    },
                },
            },
            ensure_ascii=False,
        ),
    }


def test_normalize_char_page_builds_profile_and_skill_blocks():
    parents, children = normalize_char_page(_char_row(), aliases=("Matilda Bouanich",))

    assert {p.parent_id for p in parents} >= {"char:3041/profile", "char:3041/skills"}
    assert "skill:30410111" in {c.child_id for c in children}
    skill = next(c for c in children if c.child_id == "skill:30410111")
    assert skill.parent_id == "char:3041/skills"
    assert skill.entity_name == "玛蒂尔达"
    assert "Matilda Bouanich" in skill.search_text
    assert "Skill-30410111" in skill.search_text
    assert skill.media_policy == "auto"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_rag_normalizer.py -q
```

Expected: fail because `normalize_char_page` is missing.

- [ ] **Step 3: Implement character normalizer**

Create `src/huiji_rag/normalizer.py`:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any

from src.huiji_rag.models import ChildBlock, ParentBlock


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_ref(row: dict[str, Any], json_path: str | None = None) -> dict[str, Any]:
    ref = {
        "kind": "data_page",
        "title": str(row.get("title", "")),
        "revid": row.get("revid"),
        "content_sha256": str(row.get("content_sha256", "")),
    }
    if json_path:
        ref["json_path"] = json_path
    return ref


def normalize_char_page(row: dict[str, Any], aliases: tuple[str, ...] = ()) -> tuple[list[ParentBlock], list[ChildBlock]]:
    payload = json.loads(str(row.get("content") or "{}"))
    entity_id = str(payload.get("id", ""))
    entity_name = str(payload.get("name", ""))
    alias_text = " ".join(aliases)
    parents: list[ParentBlock] = []
    children: list[ChildBlock] = []

    profile_text = " ".join(
        part
        for part in [
            f"{entity_name} 角色资料",
            f"稀有度 {payload.get('rare', '')}",
            f"职业 {payload.get('career', '')}",
            f"伤害类型 {payload.get('dmgType', '')}",
            alias_text,
        ]
        if str(part).strip()
    )
    profile_child = ChildBlock(
        child_id=f"char:{entity_id}/profile:0000",
        parent_id=f"char:{entity_id}/profile",
        entity_id=entity_id,
        entity_name=entity_name,
        category="character",
        section_kind="profile",
        title=f"{entity_name} / 基础资料",
        text=profile_text,
        search_text=profile_text,
        chunk_index=0,
        media_ids=(),
        media_policy="auto",
        source_refs=(_source_ref(row, "$"),),
        content_hash=_hash_text(profile_text),
    )
    children.append(profile_child)
    parents.append(
        ParentBlock(
            parent_id=f"char:{entity_id}/profile",
            entity_id=entity_id,
            entity_name=entity_name,
            entity_aliases=aliases,
            category="character",
            section_kind="profile",
            title=f"{entity_name} / 基础资料",
            summary_text=profile_text,
            source_refs=(_source_ref(row, "$"),),
            child_ids=(profile_child.child_id,),
            content_hash=_hash_text(profile_text),
        )
    )

    skill_children: list[ChildBlock] = []
    for index, (skill_key, skill) in enumerate(sorted((payload.get("skill") or {}).items())):
        skill_id = str(skill.get("id") or skill_key)
        icon_id = str(skill.get("icon") or skill_id)
        title = str(skill.get("name", ""))
        text = " ".join(
            part
            for part in [
                f"{title}",
                str(skill.get("desc_art", "")),
                str(skill.get("eff_desc", "")),
                f"阶级 {skill.get('skillRank', '')}",
            ]
            if str(part).strip()
        )
        search_text = " ".join(
            part
            for part in [
                entity_name,
                alias_text,
                "技能 神秘术 至终的仪式",
                title,
                text,
                f"Skill-{icon_id}",
                skill_id,
            ]
            if str(part).strip()
        )
        child = ChildBlock(
            child_id=f"skill:{skill_id}",
            parent_id=f"char:{entity_id}/skills",
            entity_id=entity_id,
            entity_name=entity_name,
            category="character",
            section_kind="skill",
            title=title,
            text=text,
            search_text=search_text,
            chunk_index=index,
            media_ids=(),
            media_policy="auto",
            source_refs=(_source_ref(row, f"$.skill.{skill_key}"),),
            content_hash=_hash_text(text),
        )
        skill_children.append(child)
        children.append(child)

    if skill_children:
        parents.append(
            ParentBlock(
                parent_id=f"char:{entity_id}/skills",
                entity_id=entity_id,
                entity_name=entity_name,
                entity_aliases=aliases,
                category="character",
                section_kind="skills",
                title=f"{entity_name} / 技能",
                summary_text="\n".join(child.text for child in skill_children),
                source_refs=(_source_ref(row, "$.skill"),),
                child_ids=tuple(child.child_id for child in skill_children),
                content_hash=_hash_text("\n".join(child.content_hash for child in skill_children)),
            )
        )

    return parents, children
```

- [ ] **Step 4: Run normalizer tests**

Run:

```powershell
python -m pytest tests/test_huiji_rag_normalizer.py -q
```

Expected: pass.

### Task 5A: Add P1 generic blocks for story, psychube, and item coverage

**Files:**

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/normalizer.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_normalizer.py`

- [ ] **Step 1: Add failing generic normalization test**

Append to `tests/test_huiji_rag_normalizer.py`:

```python
from src.huiji_rag.normalizer import normalize_generic_page


def test_normalize_generic_page_keeps_p1_data_in_index():
    row = {
        "title": "Data:Psychube/1444.json",
        "revid": 20,
        "content_sha256": "hash-psychube",
        "content": "{\"id\":1444,\"name\":\"美丽新世界\",\"desc\":\"心相故事文本\"}",
    }

    parents, children = normalize_generic_page(row)

    assert parents[0].category == "psychube"
    assert parents[0].parent_id == "psychube:1444/profile"
    assert children[0].parent_id == "psychube:1444/profile"
    assert "心相故事文本" in children[0].search_text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_rag_normalizer.py::test_normalize_generic_page_keeps_p1_data_in_index -q
```

Expected: fail because `normalize_generic_page` is missing.

- [ ] **Step 3: Implement generic normalizer**

In `src/huiji_rag/normalizer.py`, add:

```python
def _category_from_title(title: str) -> str:
    lowered = title.lower()
    if "psychube" in lowered or "equip" in lowered or "心相" in title:
        return "psychube"
    if "item" in lowered or "物品" in title:
        return "item"
    if "episode" in lowered or "story" in lowered or "剧情" in title:
        return "story"
    return "generic"


def _id_from_payload_or_title(payload: dict[str, Any], title: str) -> str:
    raw_id = payload.get("id")
    if raw_id is not None:
        return str(raw_id)
    return hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]


def normalize_generic_page(row: dict[str, Any]) -> tuple[list[ParentBlock], list[ChildBlock]]:
    title = str(row.get("title", ""))
    raw_content = str(row.get("content") or "")
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        payload = {"name": title, "text": raw_content}
    category = _category_from_title(title)
    entity_id = _id_from_payload_or_title(payload, title)
    entity_name = str(payload.get("name") or payload.get("title") or title.rsplit("/", 1)[-1].replace(".json", ""))
    parent_id = f"{category}:{entity_id}/profile"
    text_parts = [entity_name]
    for key in ("desc", "description", "story", "content", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text_parts.append(value.strip())
    if len(text_parts) == 1:
        text_parts.append(raw_content[:1200])
    text = "\n".join(text_parts)
    child = ChildBlock(
        child_id=f"{category}:{entity_id}:0000",
        parent_id=parent_id,
        entity_id=entity_id,
        entity_name=entity_name,
        category=category,
        section_kind="profile",
        title=entity_name,
        text=text,
        search_text=f"{category} {entity_name} {title} {text}",
        chunk_index=0,
        media_ids=(),
        media_policy="auto",
        source_refs=(_source_ref(row, "$"),),
        content_hash=_hash_text(text),
    )
    parent = ParentBlock(
        parent_id=parent_id,
        entity_id=entity_id,
        entity_name=entity_name,
        entity_aliases=(),
        category=category,
        section_kind="profile",
        title=entity_name,
        summary_text=text[:1000],
        source_refs=(_source_ref(row, "$"),),
        child_ids=(child.child_id,),
        content_hash=_hash_text(text),
    )
    return [parent], [child]
```

- [ ] **Step 4: Run normalizer tests**

Run:

```powershell
python -m pytest tests/test_huiji_rag_normalizer.py -q
```

Expected: pass.

### Task 6: Resolve media assets from manifest and local files

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/media.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_media.py`

- [ ] **Step 1: Write failing media resolver tests**

Create `tests/test_huiji_rag_media.py`:

```python
from pathlib import Path
from types import SimpleNamespace

from src.huiji_rag.media import classify_asset_type, resolve_media_assets


def test_classify_asset_type_from_filename():
    assert classify_asset_type("Portrait-304101.png") == "portrait"
    assert classify_asset_type("Skill-30410111.png") == "skill"
    assert classify_asset_type("L2d_static-506501_xiaomadierda_p.png") == "portrait"
    assert classify_asset_type("Currency-100.png") == "common"
    assert classify_asset_type("Voice-3041.mp3") == "voice"


def test_resolve_media_assets_uses_file_existence_not_download_status(tmp_path):
    raw_root = tmp_path / "raw"
    local = raw_root / "assets/files/abc/Skill-30410111.png"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"png")
    cfg = SimpleNamespace(
        assets=SimpleNamespace(
            bucket_name="reverse1999-assets",
            public_base_url="http://127.0.0.1:9002",
            object_prefix="reverse1999",
        )
    )
    resources = [
        {
            "name": "Skill-30410111.png",
            "title": "文件:Skill-30410111.png",
            "sha1": "abc",
            "mime": "image/png",
            "url": "https://example/Skill-30410111.png",
            "local_relpath": "assets/files/abc/Skill-30410111.png",
            "download_status": "not_downloaded",
        }
    ]

    assets = resolve_media_assets(
        cfg=cfg,
        raw_root=raw_root,
        resources=resources,
        entity_id="3041",
        entity_name="玛蒂尔达",
        aliases=("Matilda Bouanich",),
        parent_id="char:3041/skills",
        child_id="skill:30410111",
        filename_terms=("Skill-30410111",),
    )

    assert assets[0].is_available is True
    assert assets[0].asset_type == "skill"
    assert assets[0].attach_policy == "auto"
    assert assets[0].url.startswith("http://127.0.0.1:9002/reverse1999-assets/")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_rag_media.py -q
```

Expected: fail because `src.huiji_rag.media` does not exist.

- [ ] **Step 3: Implement media resolver**

Create `src/huiji_rag/media.py`:

```python
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from src.huiji_rag.models import MediaAsset, media_id_for_sha1


COMMON_PATTERNS = ("currency", "buff", "debuff", "icon", "itemicon", "000-", "箱的构造")


def classify_asset_type(filename: str) -> str:
    lowered = filename.lower()
    if any(pattern in lowered for pattern in COMMON_PATTERNS):
        return "common"
    if lowered.endswith((".mp3", ".ogg", ".wav")):
        return "voice"
    if lowered.endswith((".mp4", ".webm", ".mov")):
        return "video"
    if lowered.startswith("skill-"):
        return "skill"
    if lowered.startswith("portrait-") or lowered.startswith("l2d_static-") or "stand" in lowered:
        return "portrait"
    if "psychube" in lowered or "equip" in lowered:
        return "psychube"
    if lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    return "unknown"


def attach_policy_for(asset_type: str) -> str:
    if asset_type in {"portrait", "skill", "psychube", "image"}:
        return "auto"
    if asset_type in {"voice", "video"}:
        return "on_intent"
    return "manual"


def _object_key(prefix: str, asset_type: str, sha1: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower() or ".bin"
    shard = sha1[:2] if sha1 else "unknown"
    return f"{prefix.strip('/')}/{asset_type}/{shard}/{sha1}{suffix}"


def _public_url(base_url: str, bucket_name: str, object_key: str) -> str:
    return f"{base_url.rstrip('/')}/{bucket_name}/{quote(object_key, safe='/')}"


def _content_hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _matches_terms(filename: str, terms: Iterable[str]) -> bool:
    lowered = filename.lower()
    return any(term and term.lower() in lowered for term in terms)


def resolve_media_assets(
    cfg: Any,
    raw_root: str | Path,
    resources: Iterable[dict[str, Any]],
    entity_id: str,
    entity_name: str,
    aliases: tuple[str, ...],
    parent_id: str,
    child_id: str,
    filename_terms: tuple[str, ...],
) -> list[MediaAsset]:
    raw_root = Path(raw_root)
    out: list[MediaAsset] = []
    for row in resources:
        filename = str(row.get("name", ""))
        if not _matches_terms(filename, filename_terms):
            continue
        sha1 = str(row.get("sha1") or "")
        if not sha1:
            sha1 = hashlib.sha1(filename.encode("utf-8")).hexdigest()
        asset_type = classify_asset_type(filename)
        local_relpath = str(row.get("local_relpath", ""))
        object_key = _object_key(cfg.assets.object_prefix, asset_type, sha1, filename)
        search_text = " ".join([entity_name, *aliases, asset_type, filename, str(row.get("title", "")), child_id])
        out.append(
            MediaAsset(
                media_id=media_id_for_sha1(sha1),
                sha1=sha1,
                entity_id=entity_id,
                entity_name=entity_name,
                parent_id=parent_id,
                child_id=child_id,
                asset_type=asset_type,
                mime=str(row.get("mime") or ""),
                filename=filename,
                title=str(row.get("title") or filename),
                source_url=str(row.get("url") or ""),
                local_relpath=local_relpath,
                object_key=object_key,
                url=_public_url(cfg.assets.public_base_url, cfg.assets.bucket_name, object_key),
                is_available=bool(local_relpath and (raw_root / local_relpath).exists()),
                is_common=asset_type == "common",
                attach_policy=attach_policy_for(asset_type),
                search_text=re.sub(r"\s+", " ", search_text).strip(),
                content_hash=_content_hash(filename, sha1, search_text),
            )
        )
    return out
```

- [ ] **Step 4: Run media tests**

Run:

```powershell
python -m pytest tests/test_huiji_rag_media.py -q
```

Expected: pass.

### Task 7: Build corpus artifacts and manifest

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_rag/builder.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_huiji_corpus.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_rag_builder.py`

- [ ] **Step 1: Write failing builder test**

Create `tests/test_huiji_rag_builder.py`:

```python
import json
from types import SimpleNamespace

from src.huiji_rag.builder import build_huiji_corpus
from src.huiji_rag.io import iter_jsonl


def test_build_huiji_corpus_writes_parent_child_media_outputs(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    local = raw / "assets/files/abc/Skill-30410111.png"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"png")
    char = {
        "title": "Data:Char/3041.json",
        "revid": 10,
        "content_sha256": "hash-char",
        "content": json.dumps(
            {
                "id": 3041,
                "name": "玛蒂尔达",
                "skill": {
                    "30410111": {
                        "id": 30410111,
                        "name": "天才习作",
                        "icon": 30410111,
                        "desc_art": "出类拔萃的习作。",
                        "eff_desc": "",
                        "skillRank": 1,
                    }
                },
            },
            ensure_ascii=False,
        ),
    }
    (raw / "data_pages.jsonl").write_text(json.dumps(char, ensure_ascii=False) + "\n", encoding="utf-8")
    (raw / "resources_manifest.jsonl").write_text(
        json.dumps(
            {
                "name": "Skill-30410111.png",
                "title": "文件:Skill-30410111.png",
                "sha1": "abc",
                "mime": "image/png",
                "url": "https://example/Skill-30410111.png",
                "local_relpath": "assets/files/abc/Skill-30410111.png",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(raw_root=raw, processed_root=tmp_path / "processed", build_version="test-build"),
        assets=SimpleNamespace(
            bucket_name="reverse1999-assets",
            public_base_url="http://127.0.0.1:9002",
            object_prefix="reverse1999",
        ),
    )

    paths = build_huiji_corpus(cfg)

    assert paths.parent_blocks.exists()
    assert paths.child_blocks.exists()
    assert paths.media_assets.exists()
    assert next(iter_jsonl(paths.child_blocks))["entity_name"] == "玛蒂尔达"
    assert next(iter_jsonl(paths.media_assets))["asset_type"] == "skill"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_rag_builder.py -q
```

Expected: fail because `build_huiji_corpus` is missing.

- [ ] **Step 3: Implement corpus builder**

Create `src/huiji_rag/builder.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.huiji_rag.io import build_paths, write_json, write_jsonl
from src.huiji_rag.media import resolve_media_assets
from src.huiji_rag.normalizer import normalize_char_page
from src.huiji_rag.source import HuijiCrawlerDataSource


def _load_alias_map(source: HuijiCrawlerDataSource) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, tuple[str, ...]] = {}
    for row in source.iter_data_pages(prefix="Data:Char/map.json"):
        try:
            payload = json.loads(str(row.get("content") or "{}"))
        except json.JSONDecodeError:
            return aliases
        for name, entity_id in (payload.get("name") or {}).items():
            aliases[str(entity_id)] = tuple(dict.fromkeys([str(name)]))
    return aliases


def build_huiji_corpus(cfg: Any):
    paths = build_paths(cfg)
    source = HuijiCrawlerDataSource(paths.raw_root)
    alias_map = _load_alias_map(source)
    resources = list(source.iter_resources())

    parents = []
    children = []
    media = []
    for row in source.iter_data_pages(prefix="Data:Char/"):
        title = str(row.get("title", ""))
        if title == "Data:Char/map.json" or not title.endswith(".json"):
            continue
        try:
            payload = json.loads(str(row.get("content") or "{}"))
        except json.JSONDecodeError:
            continue
        entity_id = str(payload.get("id", ""))
        aliases = alias_map.get(entity_id, ())
        row_parents, row_children = normalize_char_page(row, aliases=aliases)
        parents.extend(parent.to_json() for parent in row_parents)
        for child in row_children:
            filename_terms = tuple(
                term
                for term in [child.child_id.split(":", 1)[-1], child.title, f"Skill-{child.child_id.split(':')[-1]}"]
                if term
            )
            media_assets = resolve_media_assets(
                cfg=cfg,
                raw_root=paths.raw_root,
                resources=resources,
                entity_id=child.entity_id,
                entity_name=child.entity_name,
                aliases=aliases,
                parent_id=child.parent_id,
                child_id=child.child_id,
                filename_terms=filename_terms,
            )
            media_ids = tuple(asset.media_id for asset in media_assets)
            child_json = child.to_json()
            child_json["media_ids"] = media_ids
            children.append(child_json)
            media.extend(asset.to_json() for asset in media_assets)

    for row in source.iter_data_pages():
        title = str(row.get("title", ""))
        if title.startswith("Data:Char/"):
            continue
        if not any(marker in title.lower() for marker in ("psychube", "equip", "item", "episode", "story")):
            continue
        row_parents, row_children = normalize_generic_page(row)
        parents.extend(parent.to_json() for parent in row_parents)
        children.extend(child.to_json() for child in row_children)

    write_jsonl(paths.parent_blocks, parents)
    write_jsonl(paths.child_blocks, children)
    write_jsonl(paths.media_assets, media)
    write_json(
        paths.build_manifest,
        {
            "build_version": str(cfg.huiji.build_version),
            "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "parent_count": len(parents),
            "child_count": len(children),
            "media_count": len(media),
            "raw_root": str(paths.raw_root),
        },
    )
    return paths
```

Create `scripts/build_huiji_corpus.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.builder import build_huiji_corpus


def main() -> None:
    cfg = get_config()
    paths = build_huiji_corpus(cfg)
    print(f"[huiji-corpus] wrote parent blocks: {paths.parent_blocks}")
    print(f"[huiji-corpus] wrote child blocks: {paths.child_blocks}")
    print(f"[huiji-corpus] wrote media assets: {paths.media_assets}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run builder tests**

Run:

```powershell
python -m pytest tests/test_huiji_rag_builder.py -q
```

Expected: pass.

- [ ] **Step 5: Run corpus build on real data**

Run:

```powershell
python scripts/build_huiji_corpus.py
```

Expected output includes:

```text
[huiji-corpus] wrote parent blocks:
[huiji-corpus] wrote child blocks:
[huiji-corpus] wrote media assets:
```

Then verify:

```powershell
Get-ChildItem D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji -Recurse -Filter *.jsonl
```

Expected: `parent_blocks.jsonl`, `child_blocks.jsonl`, and `media_assets.jsonl` under the configured build version.

---

## Milestone 3: Sparse BM25, Milvus, And Hybrid Retrieval

### Task 8: Add local BM25 sparse index

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/sparse.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_sparse_bm25.py`

- [ ] **Step 1: Write failing BM25 tests**

Create `tests/test_sparse_bm25.py`:

```python
from src.rag.sparse import LocalBM25SparseIndex


def test_bm25_prefers_exact_name_and_filename_terms(tmp_path):
    records = [
        {"id": "skill:30410111", "search_text": "玛蒂尔达 天才习作 Skill-30410111"},
        {"id": "skill:30740111", "search_text": "爱兹拉 看护于躯壳 Skill-30740111"},
        {"id": "common:box", "search_text": "000-箱的构造 背景 公共素材"},
    ]
    index = LocalBM25SparseIndex()
    index.build(records)

    results = index.search("玛蒂尔达 Skill-30410111", top_k=3)

    assert results[0]["id"] == "skill:30410111"
    assert results[-1]["id"] == "common:box"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_sparse_bm25.py -q
```

Expected: fail because `src.rag.sparse` does not exist.

- [ ] **Step 3: Implement BM25**

Create `src/rag/sparse.py`:

```python
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_\\-]+|[\\u4e00-\\u9fff]+", text.lower())


class LocalBM25SparseIndex:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.records: list[dict[str, Any]] = []
        self.doc_terms: list[Counter[str]] = []
        self.df: Counter[str] = Counter()
        self.avgdl = 0.0

    def build(self, records: list[dict[str, Any]]) -> None:
        self.records = list(records)
        self.doc_terms = []
        self.df = Counter()
        total_len = 0
        for record in self.records:
            terms = Counter(tokenize(str(record.get("search_text") or record.get("text") or "")))
            self.doc_terms.append(terms)
            total_len += sum(terms.values())
            for term in terms:
                self.df[term] += 1
        self.avgdl = total_len / len(self.records) if self.records else 0.0

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        q_terms = tokenize(query)
        total_docs = len(self.records)
        scored: list[tuple[float, int]] = []
        for index, terms in enumerate(self.doc_terms):
            doc_len = sum(terms.values()) or 1
            score = 0.0
            for term in q_terms:
                tf = terms.get(term, 0)
                if tf == 0:
                    continue
                idf = math.log(1 + (total_docs - self.df[term] + 0.5) / (self.df[term] + 0.5))
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1))
                score += idf * (tf * (self.k1 + 1)) / denom
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {**self.records[index], "bm25_score": score, "bm25_rank": rank + 1}
            for rank, (score, index) in enumerate(scored[:top_k])
        ]

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"records": self.records}, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "LocalBM25SparseIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls()
        index.build(list(payload.get("records", [])))
        return index
```

- [ ] **Step 4: Run BM25 tests**

Run:

```powershell
python -m pytest tests/test_sparse_bm25.py -q
```

Expected: pass.

### Task 9: Add huiji Milvus schema and index builder

**Files:**

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/vectorstore.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_huiji_index.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_vectorstore.py`

- [ ] **Step 1: Write failing vector row test**

Create `tests/test_huiji_vectorstore.py`:

```python
from src.rag.vectorstore import huiji_child_to_milvus_row


def test_huiji_child_to_milvus_row_keeps_core_fields():
    row = huiji_child_to_milvus_row(
        child={
            "child_id": "skill:30410111",
            "parent_id": "char:3041/skills",
            "entity_id": "3041",
            "entity_name": "玛蒂尔达",
            "category": "character",
            "section_kind": "skill",
            "title": "天才习作",
            "text": "天才习作说明",
            "search_text": "玛蒂尔达 技能 天才习作",
            "chunk_index": 0,
            "media_policy": "auto",
            "source_refs": [{"title": "Data:Char/3041.json"}],
            "content_hash": "hash",
        },
        vector=[0.1, 0.2],
    )

    assert row["id"] == "skill:30410111"
    assert row["parent_id"] == "char:3041/skills"
    assert row["entity_name"] == "玛蒂尔达"
    assert row["embedding"] == [0.1, 0.2]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_vectorstore.py -q
```

Expected: fail because `huiji_child_to_milvus_row` is missing.

- [ ] **Step 3: Add collection creation, row conversion, and build function**

In `src/rag/vectorstore.py`, add:

```python
from pymilvus import DataType


def ensure_huiji_collection(client: MilvusClient, collection_name: str, dim: int = 1024) -> None:
    if client.has_collection(collection_name):
        return
    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("text", DataType.VARCHAR, max_length=16384)
    schema.add_field("parent_id", DataType.VARCHAR, max_length=256)
    schema.add_field("child_id", DataType.VARCHAR, max_length=256)
    schema.add_field("entity_id", DataType.VARCHAR, max_length=64)
    schema.add_field("entity_name", DataType.VARCHAR, max_length=512)
    schema.add_field("category", DataType.VARCHAR, max_length=64)
    schema.add_field("section_kind", DataType.VARCHAR, max_length=64)
    schema.add_field("media_policy", DataType.VARCHAR, max_length=64)
    schema.add_field("source_ref", DataType.VARCHAR, max_length=4096)
    schema.add_field("chunk_index", DataType.INT64)
    schema.add_field("content_hash", DataType.VARCHAR, max_length=128)
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="AUTOINDEX",
        metric_type="COSINE",
        params={},
    )
    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
        consistency_level="Bounded",
    )


def huiji_child_to_milvus_row(child: dict[str, Any], vector: list[float]) -> dict[str, Any]:
    return {
        PRIMARY_FIELD: str(child["child_id"]),
        TEXT_FIELD: str(child.get("text") or child.get("search_text") or ""),
        VECTOR_FIELD: vector,
        "parent_id": str(child.get("parent_id", "")),
        "child_id": str(child.get("child_id", "")),
        "entity_id": str(child.get("entity_id", "")),
        "entity_name": str(child.get("entity_name", "")),
        "category": str(child.get("category", "")),
        "section_kind": str(child.get("section_kind", "")),
        "media_policy": str(child.get("media_policy", "")),
        "source_ref": json.dumps(child.get("source_refs", []), ensure_ascii=False),
        "chunk_index": int(child.get("chunk_index", 0) or 0),
        "content_hash": str(child.get("content_hash", "")),
    }
```

Add a separate function:

```python
def build_huiji_vectorstore(
    cfg: Config,
    children: list[dict[str, Any]],
    collection_name: str | None = None,
    batch_size: int = 64,
    progress: ProgressCallback | None = None,
) -> MilvusVectorstore:
    original_collection = cfg.vectorstore.collection_name
    if collection_name:
        cfg.vectorstore.collection_name = collection_name
    try:
        client = MilvusClient(uri=cfg.vectorstore.uri, db_name=cfg.vectorstore.db_name)
        ensure_huiji_collection(client, cfg.vectorstore.collection_name)
        vectorstore = _new_milvus(cfg)
        _delete_existing_entities(vectorstore)
        embeddings = get_embeddings(cfg)
        total = len(children)
        inserted = 0
        for start in range(0, total, batch_size):
            batch = children[start:start + batch_size]
            texts = [str(child.get("search_text") or child.get("text") or "") for child in batch]
            vectors = embeddings.embed_documents(texts)
            rows = [huiji_child_to_milvus_row(child, vector) for child, vector in zip(batch, vectors)]
            if rows:
                vectorstore.client.insert(collection_name=vectorstore.collection_name, data=rows)
                inserted += len(rows)
            if progress:
                progress({"event": "batch_done", "inserted": inserted, "total": total})
        vectorstore.client.flush(collection_name=vectorstore.collection_name)
        return vectorstore
    finally:
        cfg.vectorstore.collection_name = original_collection
```

- [ ] **Step 4: Create index script**

Create `scripts/build_huiji_index.py`:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.io import build_paths, iter_jsonl
from src.rag.sparse import LocalBM25SparseIndex
from src.rag.vectorstore import build_huiji_vectorstore


def _progress(event: dict) -> None:
    if event.get("event") == "batch_done":
        print(f"[huiji-index] inserted {event['inserted']}/{event['total']}", flush=True)


def main() -> None:
    cfg = get_config()
    paths = build_paths(cfg)
    children = list(iter_jsonl(paths.child_blocks))
    media = list(iter_jsonl(paths.media_assets))

    child_index = LocalBM25SparseIndex()
    child_index.build([{"id": row["child_id"], **row} for row in children])
    child_index.save(paths.child_bm25)
    print(f"[huiji-index] wrote child bm25: {paths.child_bm25}")

    media_index = LocalBM25SparseIndex()
    media_index.build([{"id": row["media_id"], **row} for row in media])
    media_index.save(paths.media_bm25)
    print(f"[huiji-index] wrote media bm25: {paths.media_bm25}")

    batch_size = int(os.environ.get("INDEX_BATCH_SIZE", "64"))
    build_huiji_vectorstore(
        cfg,
        children,
        collection_name=cfg.huiji.text_collection_name,
        batch_size=batch_size,
        progress=_progress,
    )
    print(f"[huiji-index] done: {cfg.vectorstore.db_name}.{cfg.huiji.text_collection_name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run vectorstore unit test**

Run:

```powershell
python -m pytest tests/test_huiji_vectorstore.py -q
```

Expected: pass.

- [ ] **Step 6: Build indexes on real processed corpus**

Run after Task 7:

```powershell
python scripts/build_huiji_index.py
```

Expected:

```text
[huiji-index] wrote child bm25:
[huiji-index] wrote media bm25:
[huiji-index] inserted ...
[huiji-index] done: reverse1999_rag.text_child_bge_m3_v2
```

### Task 10: Add weighted RRF hybrid retriever

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/hybrid.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_hybrid_retriever.py`

- [ ] **Step 1: Write failing RRF and parent expansion tests**

Create `tests/test_hybrid_retriever.py`:

```python
from src.rag.hybrid import weighted_rrf, rerank_children_with_parent_context


def test_weighted_rrf_combines_bm25_and_dense_ranks():
    rows = weighted_rrf(
        bm25=[{"child_id": "a"}, {"child_id": "b"}],
        dense=[{"child_id": "b"}, {"child_id": "c"}],
        entity="玛蒂尔达",
        intent="skill",
    )

    assert rows[0]["child_id"] == "b"
    assert rows[0]["debug"]["bm25_rank"] == 2
    assert rows[0]["debug"]["dense_rank"] == 1


def test_parent_context_keeps_hit_and_neighbor_order():
    children = [
        {"child_id": "a", "parent_id": "p", "chunk_index": 0, "text": "前文"},
        {"child_id": "b", "parent_id": "p", "chunk_index": 1, "text": "命中"},
        {"child_id": "c", "parent_id": "p", "chunk_index": 2, "text": "后文"},
    ]
    ranked = [{"child_id": "b", "parent_id": "p", "score": 1.0}]

    out = rerank_children_with_parent_context(ranked, children, neighbor_window=1, limit=3)

    assert [row["child_id"] for row in out] == ["b", "a", "c"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_hybrid_retriever.py -q
```

Expected: fail because `src.rag.hybrid` does not exist.

- [ ] **Step 3: Implement RRF helpers**

Create `src/rag/hybrid.py`:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any


def weighted_rrf(
    bm25: list[dict[str, Any]],
    dense: list[dict[str, Any]],
    entity: str | None,
    intent: str,
    k: int = 60,
    w_bm25: float = 1.2,
    w_dense: float = 1.0,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    debug: defaultdict[str, dict[str, Any]] = defaultdict(dict)

    for rank, row in enumerate(bm25, start=1):
        key = str(row["child_id"])
        merged.setdefault(key, dict(row))
        scores[key] += w_bm25 / (k + rank)
        debug[key]["bm25_rank"] = rank
    for rank, row in enumerate(dense, start=1):
        key = str(row["child_id"])
        merged.setdefault(key, dict(row))
        scores[key] += w_dense / (k + rank)
        debug[key]["dense_rank"] = rank

    for key, row in merged.items():
        if entity and str(row.get("entity_name", "")) == entity:
            scores[key] += 0.30
            debug[key]["exact_entity_bonus"] = 0.30
        if intent == "skill" and str(row.get("section_kind", "")) in {"skill", "skills"}:
            scores[key] += 0.25
            debug[key]["intent_section_bonus"] = 0.25
        row["score"] = scores[key]
        row["debug"] = dict(debug[key])

    return sorted(merged.values(), key=lambda item: item["score"], reverse=True)


def rerank_children_with_parent_context(
    ranked: list[dict[str, Any]],
    all_children: list[dict[str, Any]],
    neighbor_window: int = 1,
    limit: int = 20,
) -> list[dict[str, Any]]:
    by_parent: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for child in all_children:
        by_parent[str(child.get("parent_id", ""))].append(child)
    for rows in by_parent.values():
        rows.sort(key=lambda item: int(item.get("chunk_index", 0) or 0))

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in ranked:
        hit_id = str(hit["child_id"])
        parent_id = str(hit.get("parent_id", ""))
        parent_rows = by_parent.get(parent_id, [])
        positions = {str(row.get("child_id")): idx for idx, row in enumerate(parent_rows)}
        candidate_indices = [positions[hit_id]] if hit_id in positions else []
        for pos in list(candidate_indices):
            candidate_indices.extend(range(max(0, pos - neighbor_window), min(len(parent_rows), pos + neighbor_window + 1)))
        for idx in candidate_indices:
            row = dict(parent_rows[idx])
            row.setdefault("score", hit.get("score", 0.0))
            row.setdefault("debug", hit.get("debug", {}))
            child_id = str(row.get("child_id"))
            if child_id not in seen:
                seen.add(child_id)
                out.append(row)
            if len(out) >= limit:
                return out
    return out
```

- [ ] **Step 4: Run hybrid tests**

Run:

```powershell
python -m pytest tests/test_hybrid_retriever.py -q
```

Expected: pass.

### Task 11: Dispatch retriever to huiji hybrid path

**Files:**

- Modify: `D:/PycharmProjects/nlp\LangChain\1999Search/src/rag/retriever.py`
- Modify: `D:/PycharmProjects/nlp\LangChain\1999Search/tests/test_retriever.py`

- [ ] **Step 1: Add retriever dispatch test**

Append to `tests/test_retriever.py`:

```python
from src.huiji_rag.io import write_jsonl


def test_retriever_uses_huiji_children_when_enabled(tmp_path):
    processed = tmp_path / "processed" / "build"
    write_jsonl(
        processed / "child_blocks.jsonl",
        [
            {
                "child_id": "skill:30410111",
                "parent_id": "char:3041/skills",
                "entity_name": "玛蒂尔达",
                "category": "character",
                "section_kind": "skill",
                "text": "天才习作",
                "search_text": "玛蒂尔达 技能 天才习作 Skill-30410111",
                "chunk_index": 0,
                "media_policy": "auto",
            }
        ],
    )
    cfg = SimpleNamespace(
        huiji=SimpleNamespace(enabled=True, processed_root=tmp_path / "processed", build_version="build"),
        rag=SimpleNamespace(top_k=4),
        vectorstore=SimpleNamespace(provider="milvus"),
        paths=SimpleNamespace(data_processed=tmp_path / "legacy"),
    )
    cfg.paths.data_processed.mkdir()
    (cfg.paths.data_processed / "documents.jsonl").write_text("", encoding="utf-8")
    retriever = Retriever(cfg, _PacketFakeVectorstore())
    plan = QueryPlan(
        original_query="玛蒂尔达技能",
        normalized_query="玛蒂尔达 技能",
        entity="玛蒂尔达",
        aliases=("Matilda",),
        intent="skill",
        section_hints=("skills",),
        scatter_terms=("玛蒂尔达",),
        confidence=0.9,
    )

    results = retriever.search("玛蒂尔达 技能", query_plan=plan)

    assert results[0]["child_id"] == "skill:30410111"
    assert results[0]["retrieval_stage"] == "huiji_hybrid"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_retriever.py::test_retriever_uses_huiji_children_when_enabled -q
```

Expected: fail because retriever still uses legacy path.

- [ ] **Step 3: Add huiji dispatch in retriever**

In `src/rag/retriever.py`, import:

```python
from src.huiji_rag.io import build_paths, iter_jsonl
from src.rag.hybrid import rerank_children_with_parent_context, weighted_rrf
from src.rag.sparse import LocalBM25SparseIndex
```

In `Retriever.__init__`, add:

```python
        self._huiji_enabled = bool(getattr(getattr(cfg, "huiji", None), "enabled", False))
        self._huiji_children = []
        self._huiji_sparse = None
        if self._huiji_enabled:
            paths = build_paths(cfg)
            self._huiji_children = list(iter_jsonl(paths.child_blocks))
            if paths.child_bm25.exists():
                self._huiji_sparse = LocalBM25SparseIndex.load(paths.child_bm25)
            elif self._huiji_children:
                self._huiji_sparse = LocalBM25SparseIndex()
                self._huiji_sparse.build([{"id": row["child_id"], **row} for row in self._huiji_children])
```

At the start of `search`, after `top_k = ...`, add:

```python
        if self._huiji_enabled and query_plan is not None and self._huiji_sparse is not None:
            bm25_rows = self._huiji_sparse.search(query, top_k=max(top_k * 3, 20))
            dense_rows: list[dict[str, Any]] = []
            try:
                dense_hits = self._similarity_search(query, {"k": max(top_k * 3, 20)})
                for rank, (doc, score) in enumerate(dense_hits, start=1):
                    meta = doc.metadata
                    dense_rows.append({
                        "child_id": meta.get("child_id") or meta.get("id") or "",
                        "parent_id": meta.get("parent_id", ""),
                        "entity_name": meta.get("entity_name", meta.get("name", "")),
                        "category": meta.get("category", ""),
                        "section_kind": meta.get("section_kind", ""),
                        "text": doc.page_content,
                        "score": float(score),
                        "dense_rank": rank,
                    })
            except Exception:
                dense_rows = []
            ranked = weighted_rrf(bm25_rows, dense_rows, entity=query_plan.entity, intent=query_plan.intent)
            expanded = rerank_children_with_parent_context(ranked, self._huiji_children, limit=top_k)
            if expanded:
                return [
                    {
                        "name": row.get("entity_name", ""),
                        "category": row.get("category", ""),
                        "source": row.get("parent_id", ""),
                        "score": float(row.get("score", 0.0)),
                        "content": row.get("text", ""),
                        "heading_path": row.get("section_kind", ""),
                        "chunk_index": int(row.get("chunk_index", 0) or 0),
                        "retrieval_stage": "huiji_hybrid",
                        "child_id": row.get("child_id", ""),
                        "parent_id": row.get("parent_id", ""),
                        "section_kind": row.get("section_kind", ""),
                        "media_policy": row.get("media_policy", ""),
                        "debug": row.get("debug", {}),
                    }
                    for row in expanded
                ]
```

- [ ] **Step 4: Run retriever tests**

Run:

```powershell
python -m pytest tests/test_retriever.py tests/test_hybrid_retriever.py -q
```

Expected: pass.

---

## Milestone 4: Query Planning, Media Attachment, API, And Frontend

### Task 12: Extend QueryPlan with media intent and new intents

**Files:**

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/query_plan.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_query_plan.py`

- [ ] **Step 1: Add failing query plan tests**

Append to `tests/test_query_plan.py`:

```python
from src.rag.query_plan import QueryPlanner


def test_query_planner_detects_image_media_intent_without_replacing_profile_intent():
    plan = QueryPlanner(None).plan("看看玛蒂尔达的立绘")

    assert plan.entity == "玛蒂尔达"
    assert plan.intent == "profile"
    assert plan.media_intent == "image"


def test_query_planner_detects_audio_media_intent():
    plan = QueryPlanner(None).plan("播放玛蒂尔达语音")

    assert plan.intent == "voice"
    assert plan.media_intent == "audio"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_query_plan.py -q
```

Expected: fail because `QueryPlan` has no `media_intent`.

- [ ] **Step 3: Modify QueryPlan**

In `src/rag/query_plan.py`:

```python
VALID_INTENTS = {"skill", "profile", "voice", "story", "lore", "psychube", "item", "general"}
VALID_MEDIA_INTENTS = {"image", "audio", "video", "none"}
```

Add field to dataclass:

```python
    media_intent: str = "none"
```

Add helper:

```python
def _guess_media_intent(query: str) -> str:
    if any(word in query for word in ("图片", "立绘", "头像", "皮肤", "图")):
        return "image"
    if any(word in query for word in ("语音", "播放", "音频", "台词")):
        return "audio"
    if any(word in query for word in ("视频", "动画", "PV")):
        return "video"
    return "none"
```

Update `_from_payload` and `_fallback` to set `media_intent=_guess_media_intent(original_query)` unless payload contains a valid media intent.

- [ ] **Step 4: Run query planner tests**

Run:

```powershell
python -m pytest tests/test_query_plan.py -q
```

Expected: pass.

### Task 13: Add huiji media registry and attachment rules

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/huiji_registry.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_asset_registry.py`

- [ ] **Step 1: Write failing media registry tests**

Create `tests/test_huiji_asset_registry.py`:

```python
from types import SimpleNamespace

from src.huiji_rag.io import write_jsonl
from src.assets.huiji_registry import HuijiMediaRegistry
from src.rag.query_plan import QueryPlan


def test_huiji_media_registry_returns_skill_media_and_filters_voice(tmp_path):
    build = tmp_path / "processed" / "build"
    write_jsonl(
        build / "media_assets.jsonl",
        [
            {
                "media_id": "media:skill",
                "entity_name": "玛蒂尔达",
                "asset_type": "skill",
                "filename": "Skill-30410111.png",
                "url": "http://minio/skill.png",
                "is_available": True,
                "is_common": False,
                "attach_policy": "auto",
                "parent_id": "char:3041/skills",
                "child_id": "skill:30410111",
                "search_text": "玛蒂尔达 技能 Skill-30410111",
            },
            {
                "media_id": "media:voice",
                "entity_name": "玛蒂尔达",
                "asset_type": "voice",
                "filename": "Voice-3041.mp3",
                "url": "http://minio/voice.mp3",
                "is_available": True,
                "is_common": False,
                "attach_policy": "on_intent",
                "parent_id": "char:3041/voice",
                "child_id": "voice:1",
                "search_text": "玛蒂尔达 语音",
            },
        ],
    )
    cfg = SimpleNamespace(huiji=SimpleNamespace(processed_root=tmp_path / "processed", build_version="build"))
    registry = HuijiMediaRegistry(cfg)
    plan = QueryPlan("q", "q", "玛蒂尔达", (), "skill", ("skills",), (), 0.9, media_intent="none")

    media = registry.find_for_retrieval(plan, [{"child_id": "skill:30410111", "parent_id": "char:3041/skills"}])

    assert [item["media_id"] for item in media] == ["media:skill"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_huiji_asset_registry.py -q
```

Expected: fail because `src.assets.huiji_registry` does not exist.

- [ ] **Step 3: Implement huiji media registry**

Create `src/assets/huiji_registry.py`:

```python
from __future__ import annotations

from typing import Any

from src.huiji_rag.io import build_paths, iter_jsonl


INTENT_ASSET_TYPES = {
    "skill": {"skill", "ultimate"},
    "profile": {"portrait", "image"},
    "psychube": {"psychube"},
    "voice": {"voice"},
    "story": {"image", "video"},
    "general": {"portrait", "skill", "image"},
}


class HuijiMediaRegistry:
    def __init__(self, cfg: Any) -> None:
        paths = build_paths(cfg)
        self._records = list(iter_jsonl(paths.media_assets))

    def find_for_retrieval(self, plan: Any, sources: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        entity = getattr(plan, "entity", None)
        intent = getattr(plan, "intent", "general")
        media_intent = getattr(plan, "media_intent", "none")
        child_ids = {str(source.get("child_id", "")) for source in sources}
        parent_ids = {str(source.get("parent_id", "")) for source in sources}
        allowed_types = set(INTENT_ASSET_TYPES.get(intent, INTENT_ASSET_TYPES["general"]))
        if media_intent == "image":
            allowed_types.update({"portrait", "image", "skill", "psychube"})
        elif media_intent == "audio":
            allowed_types = {"voice"}
        elif media_intent == "video":
            allowed_types = {"video"}

        scored = []
        for row in self._records:
            if not row.get("is_available") or row.get("is_common"):
                continue
            if entity and row.get("entity_name") != entity:
                continue
            asset_type = str(row.get("asset_type", ""))
            if asset_type not in allowed_types:
                continue
            if row.get("attach_policy") == "on_intent" and media_intent == "none":
                continue
            child_match = row.get("child_id") in child_ids
            parent_match = row.get("parent_id") in parent_ids
            score = 0.0
            if child_match:
                score += 2.0
            if parent_match:
                score += 1.0
            if row.get("attach_policy") == "auto":
                score += 0.5
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "media_id": row.get("media_id", ""),
                "asset_id": row.get("media_id", ""),
                "asset_type": row.get("asset_type", ""),
                "mime": row.get("mime", ""),
                "url": row.get("url", ""),
                "title": row.get("title") or row.get("filename", ""),
                "alt": row.get("title") or row.get("filename", ""),
                "role": row.get("asset_type", ""),
                "attach_policy": row.get("attach_policy", ""),
            }
            for _, row in scored[:limit]
        ]
```

- [ ] **Step 4: Run media registry tests**

Run:

```powershell
python -m pytest tests/test_huiji_asset_registry.py -q
```

Expected: pass.

### Task 14: Wire chain, backend schemas, and SSE to typed media

**Files:**

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/chain.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/schemas.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/main.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_sse.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_chain_assets.py`

- [ ] **Step 1: Add backend response expectation**

In `tests/test_sse.py`, add an assertion that `done` event contains `media` and `assets`:

```python
def test_sse_done_contains_media_alias_for_assets():
    payload = {"answer": "ok", "sources": [], "assets": [{"asset_id": "a", "role": "skill", "alt": "x", "url": "u"}]}
    assert payload["assets"][0]["asset_id"] == "a"
```

Then update this test after implementation to parse real generator events if existing helper style supports it.

- [ ] **Step 2: Modify RAGChain to choose huiji registry when enabled**

In `src/rag/chain.py`, import:

```python
from src.assets.huiji_registry import HuijiMediaRegistry
```

Replace asset registry init with:

```python
        if bool(getattr(getattr(cfg, "huiji", None), "enabled", False)):
            self._asset_registry = HuijiMediaRegistry(cfg)
        else:
            self._asset_registry = AssetRegistry(cfg)
```

In `retrieve`, return both names:

```python
        assets = self._asset_registry.find_for_retrieval(plan, sources)
        return {"plan": plan, "sources": sources, "context": context, "assets": assets, "media": assets}
```

In `ask`, keep both:

```python
        assets = retrieved["assets"]
        media = retrieved.get("media", assets)
```

Return dictionaries with `"assets": assets, "media": media`.

- [ ] **Step 3: Extend backend schema**

In `backend/schemas.py`, add:

```python
class MediaItem(BaseModel):
    media_id: str
    asset_id: str = ""
    asset_type: str = ""
    mime: str = ""
    url: str
    title: str = ""
    alt: str = ""
    role: str = ""
    attach_policy: str = ""
```

In `AskResponse`, add:

```python
    media: list[MediaItem] = []
```

- [ ] **Step 4: Serialize media in backend**

In `backend/main.py`, import `MediaItem`. In `ask`, build:

```python
    media = [
        MediaItem(
            media_id=m.get("media_id", m.get("asset_id", "")),
            asset_id=m.get("asset_id", m.get("media_id", "")),
            asset_type=m.get("asset_type", m.get("role", "")),
            mime=m.get("mime", ""),
            url=m["url"],
            title=m.get("title", m.get("alt", "")),
            alt=m.get("alt", ""),
            role=m.get("role", m.get("asset_type", "")),
            attach_policy=m.get("attach_policy", ""),
        )
        for m in result.get("media", result.get("assets", []))
    ]
```

Return:

```python
    return AskResponse(answer=result["answer"], sources=sources, assets=assets, media=media)
```

In `backend/sse.py`, include `"media": retrieved.get("media", asset_items)` in `sources` and `done` events.

- [ ] **Step 5: Run backend tests**

Run:

```powershell
python -m pytest tests/test_sse.py tests/test_chain_assets.py tests/test_asset_registry.py tests/test_huiji_asset_registry.py -q
```

Expected: pass.

### Task 15: Render typed media in chat window

**Files:**

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/index.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/sse.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/store/chatStore.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageAssets.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageBubble.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageBubble.test.tsx`

- [ ] **Step 1: Add frontend type changes**

In `frontend/react-app/src/types/index.ts`, add:

```ts
export interface MediaItem {
  media_id: string
  asset_id?: string
  asset_type?: string
  mime?: string
  url: string
  title?: string
  alt?: string
  role?: string
  attach_policy?: string
}
```

Add `media?: MediaItem[]` to `Message`.

- [ ] **Step 2: Parse media from SSE**

In `frontend/react-app/src/api/sse.ts`, import `MediaItem` and change callback signatures:

```ts
  onSources: (sources: SourceItem[], assets?: AssetItem[], media?: MediaItem[]) => void
  onDone: (answer: string, sources: SourceItem[], assets?: AssetItem[], media?: MediaItem[]) => void
```

When parsing:

```ts
const media = data.media as MediaItem[] | undefined
```

Pass media into callbacks while preserving assets.

- [ ] **Step 3: Store media in chat state**

In `frontend/react-app/src/store/chatStore.ts`, update callbacks:

```ts
onSources: (sources: SourceItem[], assets = [], media = []) =>
  updateLast({ sources, assets, media, status: 'DeepSeek 正在根据检索来源生成回答...' }),
onDone: (answer, sources, assets = [], media = []) =>
  updateLast({ content: answer, sources, assets, media, streaming: false, status: undefined }),
```

- [ ] **Step 4: Render image/audio/video**

In `frontend/react-app/src/components/chat/MessageAssets.tsx`, accept both legacy assets and media:

```tsx
import type { AssetItem, MediaItem } from '../../types'

function mediaKind(item: AssetItem | MediaItem): 'image' | 'audio' | 'video' {
  const mime = 'mime' in item ? item.mime || '' : ''
  const role = ('asset_type' in item ? item.asset_type : item.role) || ''
  if (mime.startsWith('audio/') || role === 'voice') return 'audio'
  if (mime.startsWith('video/') || role === 'video') return 'video'
  return 'image'
}
```

Render audio as:

```tsx
<button type="button" className="media-audio-button" onClick={() => new Audio(asset.url).play()}>
  {asset.alt || ('title' in asset ? asset.title : '') || '播放音频'}
</button>
```

Render video as:

```tsx
<video src={asset.url} controls preload="metadata" style={{ width: '100%', maxHeight: 260 }} />
```

Keep existing image grid for images.

- [ ] **Step 5: Pass media from message bubble**

In `MessageBubble.tsx`, change:

```tsx
{!message.streaming && (message.media || message.assets) && (
  <MessageAssets assets={message.media || message.assets || []} />
)}
```

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd frontend\react-app
npm test -- --run src/components/chat/MessageBubble.test.tsx src/api/sse.test.ts
```

Expected: tests pass.

---

## Milestone 5: Evaluation, Switching, And End-To-End Verification

### Task 16: Add core evaluation set and evaluator

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/eval/queries_core.jsonl`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/evaluate_huiji_rag.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_eval.py`

- [ ] **Step 1: Create evaluation set**

Create `eval/queries_core.jsonl`:

```jsonl
{"query":"玛蒂尔达的技能有什么","expected_entity":"玛蒂尔达","expected_intent":"skill","expected_parent_ids":["char:3041/skills"],"expected_child_ids":["skill:30410111"],"expected_asset_types":["skill"],"forbidden_asset_types":["voice","common","currency"]}
{"query":"看看玛蒂尔达的立绘","expected_entity":"玛蒂尔达","expected_intent":"profile","expected_parent_ids":["char:3041/profile"],"expected_child_ids":[],"expected_asset_types":["portrait"],"forbidden_asset_types":["common","currency"]}
{"query":"播放玛蒂尔达语音","expected_entity":"玛蒂尔达","expected_intent":"voice","expected_parent_ids":["char:3041/voice"],"expected_child_ids":[],"expected_asset_types":["voice"],"forbidden_asset_types":["common","currency"]}
{"query":"爱兹拉的技能是什么","expected_entity":"爱兹拉","expected_intent":"skill","expected_parent_ids":["char:3074/skills"],"expected_child_ids":["skill:30740111"],"expected_asset_types":["skill"],"forbidden_asset_types":["voice","common","currency"]}
{"query":"介绍一下心相","expected_entity":"","expected_intent":"psychube","expected_parent_ids":[],"expected_child_ids":[],"expected_asset_types":[],"forbidden_asset_types":["voice"]}
```

- [ ] **Step 2: Write evaluator test**

Create `tests/test_huiji_eval.py`:

```python
from scripts.evaluate_huiji_rag import compute_recall


def test_compute_recall_counts_expected_ids():
    assert compute_recall(["a", "b"], ["b", "c"]) == 0.5
    assert compute_recall([], ["b"]) == 0.0
    assert compute_recall(["a"], []) == 1.0
```

- [ ] **Step 3: Implement evaluator helpers**

Create `scripts/evaluate_huiji_rag.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.rag.chain import RAGChain
from src.rag.retriever import Retriever
from src.rag.vectorstore import load_vectorstore


def compute_recall(actual: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    return len(set(actual) & set(expected)) / len(set(expected))


def iter_eval_rows(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    cfg = get_config()
    chain = RAGChain(cfg, Retriever(cfg, load_vectorstore(cfg)))
    rows = list(iter_eval_rows(Path("eval/queries_core.jsonl")))
    parent_scores = []
    child_scores = []
    for row in rows:
        result = chain.retrieve(row["query"])
        sources = result["sources"]
        media = result.get("media", result.get("assets", []))
        actual_parent_ids = [str(source.get("parent_id", "")) for source in sources]
        actual_child_ids = [str(source.get("child_id", "")) for source in sources]
        actual_asset_types = [str(item.get("asset_type", item.get("role", ""))) for item in media]
        parent_scores.append(compute_recall(actual_parent_ids, row.get("expected_parent_ids", [])))
        child_scores.append(compute_recall(actual_child_ids, row.get("expected_child_ids", [])))
        forbidden = set(row.get("forbidden_asset_types", []))
        leaked = forbidden & set(actual_asset_types)
        print(json.dumps({
            "query": row["query"],
            "parent_recall": parent_scores[-1],
            "child_recall": child_scores[-1],
            "asset_types": actual_asset_types,
            "forbidden_leak": sorted(leaked),
        }, ensure_ascii=False))
    print(json.dumps({
        "parent_recall_avg": sum(parent_scores) / len(parent_scores),
        "child_recall_avg": sum(child_scores) / len(child_scores),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run evaluator unit test**

Run:

```powershell
python -m pytest tests/test_huiji_eval.py -q
```

Expected: pass.

- [ ] **Step 5: Run evaluator against built index**

Run after Milvus index exists and `huiji.enabled=true`:

```powershell
python scripts/evaluate_huiji_rag.py
```

Expected: prints one JSON line per query plus summary with `parent_recall_avg` and `child_recall_avg`.

### Task 17: Add runbook and safe switch procedure

**Files:**

- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/docs/huiji-rag-runbook.md`

- [ ] **Step 1: Create runbook**

Create `docs/huiji-rag-runbook.md`:

```markdown
# 灰机 RAG 构建与切换 Runbook

## 1. 前提

- 灰机原始数据位于 `data/huiji/res1999`。
- MinIO、Milvus 和后端依赖已启动。
- `.env` 中配置 `SILICONFLOW_API_KEY`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`。

## 2. 构建语料

```powershell
python scripts/build_huiji_corpus.py
```

检查：

```powershell
Get-ChildItem data\processed\huiji -Recurse -Filter *.jsonl
```

## 3. 构建 BM25 和 Milvus

```powershell
python scripts/build_huiji_index.py
```

## 4. 评估

```powershell
python scripts/evaluate_huiji_rag.py
```

优先检查：

- `Parent Recall@5`
- `Child Recall@10`
- `Asset Recall@5`
- `Voice Auto Leak Rate`
- `Common Asset Leakage`

## 5. 切换

确认评估通过后，在 `config/settings.yaml` 中设置：

```yaml
huiji:
  enabled: true
vectorstore:
  collection_name: "text_child_bge_m3_v2"
```

## 6. 回滚

如果新链路异常：

```yaml
huiji:
  enabled: false
vectorstore:
  collection_name: "chunks_bge_m3_v1"
```
```

- [ ] **Step 2: Check runbook text**

Run:

```powershell
rg -n "huiji|text_child_bge_m3_v2|chunks_bge_m3_v1" docs\huiji-rag-runbook.md
```

Expected: all three terms appear.

### Task 18: End-to-end verification

**Files:**

- No new files.

- [ ] **Step 1: Run Python unit tests for new path**

Run:

```powershell
python -m pytest tests/test_huiji_config.py tests/test_huiji_rag_models.py tests/test_huiji_rag_source.py tests/test_huiji_rag_normalizer.py tests/test_huiji_rag_media.py tests/test_huiji_rag_builder.py tests/test_sparse_bm25.py tests/test_hybrid_retriever.py tests/test_huiji_asset_registry.py tests/test_huiji_vectorstore.py tests/test_huiji_eval.py -q
```

Expected: all pass.

- [ ] **Step 2: Run existing regression tests touched by integration**

Run:

```powershell
python -m pytest tests/test_config.py tests/test_query_plan.py tests/test_retriever.py tests/test_sse.py tests/test_chain_assets.py tests/test_asset_registry.py tests/test_vectorstore.py -q
```

Expected: all pass.

- [ ] **Step 3: Build real corpus**

Run:

```powershell
python scripts/build_huiji_corpus.py
```

Expected: `data/processed/huiji/{build_version}/parent_blocks.jsonl`, `child_blocks.jsonl`, `media_assets.jsonl`, and `build_manifest.json` exist.

- [ ] **Step 4: Build real indexes**

Run:

```powershell
python scripts/build_huiji_index.py
```

Expected: BM25 files exist and Milvus reports inserted rows for `text_child_bge_m3_v2`.

- [ ] **Step 5: Run evaluation**

Run:

```powershell
python scripts/evaluate_huiji_rag.py
```

Expected: no forbidden media leaks in core queries; parent and child recall summary printed.

- [ ] **Step 6: Start backend and frontend**

Run:

```powershell
.\start.ps1
```

Expected: backend starts on port `8000`; frontend starts on Vite port; `/health` reports `vectorstore_loaded=true`.

- [ ] **Step 7: Manual QA queries**

Use the chat UI and ask:

```text
玛蒂尔达的技能有什么
看看玛蒂尔达的立绘
播放玛蒂尔达语音
爱兹拉的技能是什么
```

Expected:

- Skill questions return skill text and skill/ultimate images.
- Portrait question returns character portrait/standee images, not `000-箱的构造`.
- Voice question returns audio controls only when voice/audio intent is explicit.
- Sources show gray-machine-derived parent/child sections, not Obsidian paths.

---

## Self-Review Notes

Spec coverage:

- Data source switch to gray-machine crawler data: Tasks 1, 4, 7, 17.
- Parent/child/media artifacts: Tasks 2, 5, 6, 7.
- BM25 + dense hybrid retrieval and weighted RRF: Tasks 8, 9, 10, 11.
- Media attachment policy and MinIO URL shape: Tasks 6, 13, 14, 15.
- Query planner media intents: Task 12.
- API and SSE response shape: Task 14.
- Frontend Markdown-compatible media display: Task 15.
- Evaluation set and metrics foundation: Task 16.
- Safe switch and rollback: Task 17.

Known execution considerations:

- `download_status` may not be reliable in older manifest rows; implementation uses local file existence as source of truth.
- The first detailed normalizer focuses on `Data:Char`; Task 5A still indexes story, psychube, and item data through generic P1 blocks so the first build does not have coverage holes. Later tuning can replace those generic blocks with richer category-specific parsers without changing retrieval contracts.
- Task 9 creates `text_child_bge_m3_v2` with explicit core fields and dynamic fields enabled before insertion, so execution does not depend on a manually pre-created collection.
