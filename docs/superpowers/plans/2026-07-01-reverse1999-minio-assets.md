# Reverse1999 MinIO Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach character, skill, psychube, item, and poster images from the Obsidian vault to RAG answers by uploading assets to MinIO and returning structured HTTP asset records to the frontend.

**Architecture:** Keep text retrieval in the existing two-stage RAG pipeline. Add a separate asset pipeline that parses raw Obsidian Markdown and frontmatter before text cleaning, uploads resolved local image files to MinIO, writes `data/processed/assets.jsonl`, and lets `RAGChain.retrieve()` attach matching assets after sources are ranked.

**Tech Stack:** Python 3, FastAPI, MinIO Python SDK, pytest, React 18, Zustand, Vitest, existing Milvus RAG pipeline.

---

## File Structure

Project root: `D:/PycharmProjects/nlp/LangChain/1999Search`

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/requirements.txt`
  Adds the MinIO Python SDK.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/settings.yaml`
  Adds non-secret asset storage settings.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/config.py`
  Adds `AssetStorageCfg` and environment overrides for MinIO credentials.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/__init__.py`
  Package marker.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/models.py`
  Defines `AssetRecord` and JSON serialization helpers.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/extractor.py`
  Parses image refs from raw Markdown/frontmatter, resolves local files, classifies roles, and produces `AssetRecord` objects.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/minio_store.py`
  Uploads local files to MinIO and builds public HTTP URLs.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/registry.py`
  Loads `assets.jsonl` and selects assets for ranked RAG sources.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_assets.py`
  CLI script to scan the vault, upload assets, and write the manifest.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/chain.py`
  Initializes `AssetRegistry` and includes `assets` in `retrieve()` and `ask()`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/schemas.py`
  Adds `AssetItem` and extends `AskResponse`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/main.py`
  Serializes assets in `/ask`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`
  Sends assets in `sources` and `done` SSE events.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/index.ts`
  Adds `AssetItem` and `Message.assets`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/sse.ts`
  Parses optional assets in stream events.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/store/chatStore.ts`
  Persists assets on assistant messages.
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageAssets.tsx`
  Renders returned image assets as a compact gallery.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageBubble.tsx`
  Displays `MessageAssets` under assistant answers.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MarkdownContent.tsx`
  Renders Markdown image syntax as a fallback.
- Add tests under:
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_config.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_extractor.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_registry.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_build_script.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_chain_assets.py`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/sse.test.ts`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/store/chatStore.test.ts`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageBubble.test.tsx`

---

### Task 1: Add MinIO Asset Storage Configuration

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/requirements.txt`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/settings.yaml`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/config/config.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_config.py`

- [ ] **Step 1: Write the failing config test**

Create `tests/test_asset_config.py`:

```python
from config.config import get_config, reset_config_for_test


def test_asset_storage_config_uses_yaml_and_env(monkeypatch):
    monkeypatch.setenv("MINIO_ACCESS_KEY", "test-user")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test-secret")
    reset_config_for_test()

    cfg = get_config()

    assert cfg.assets.provider == "minio"
    assert cfg.assets.endpoint == "127.0.0.1:9002"
    assert cfg.assets.public_base_url == "http://127.0.0.1:9002"
    assert cfg.assets.bucket_name == "reverse1999-assets"
    assert cfg.assets.secure is False
    assert cfg.assets.access_key == "test-user"
    assert cfg.assets.secret_key == "test-secret"


def test_asset_storage_credentials_empty_when_env_unset(monkeypatch):
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    reset_config_for_test()

    cfg = get_config()

    assert cfg.assets.access_key == ""
    assert cfg.assets.secret_key == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_config.py -q
```

Expected: fails because `Config` has no `assets` attribute.

- [ ] **Step 3: Add dependency**

Append this exact line to `requirements.txt`:

```text
minio
```

- [ ] **Step 4: Add non-secret YAML settings**

Append this block to `config/settings.yaml`:

```yaml
assets:
  provider: "minio"
  endpoint: "127.0.0.1:9002"
  public_base_url: "http://127.0.0.1:9002"
  bucket_name: "reverse1999-assets"
  secure: false
  object_prefix: "reverse1999"
```

- [ ] **Step 5: Add config dataclass and loader fields**

Modify `config/config.py`:

```python
@dataclass
class AssetStorageCfg:
    provider: str
    endpoint: str
    public_base_url: str
    bucket_name: str
    secure: bool
    object_prefix: str
    access_key: str
    secret_key: str
```

Add `assets: AssetStorageCfg` to `Config`.

Inside `get_config()`, after `vectorstore_raw = raw["vectorstore"]`, add:

```python
    assets_raw = raw["assets"]
```

Inside the `Config(...)` constructor, add:

```python
        assets=AssetStorageCfg(
            provider=assets_raw["provider"],
            endpoint=assets_raw["endpoint"],
            public_base_url=assets_raw["public_base_url"],
            bucket_name=assets_raw["bucket_name"],
            secure=bool(assets_raw.get("secure", False)),
            object_prefix=assets_raw.get("object_prefix", "reverse1999"),
            access_key=os.environ.get("MINIO_ACCESS_KEY") or assets_raw.get("access_key", "") or "",
            secret_key=os.environ.get("MINIO_SECRET_KEY") or assets_raw.get("secret_key", "") or "",
        ),
```

- [ ] **Step 6: Run config tests**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_config.py tests/test_config.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit checkpoint**

```powershell
git add requirements.txt config/settings.yaml config/config.py tests/test_asset_config.py
git commit -m "feat: add MinIO asset storage config"
```

---

### Task 2: Extract Image Asset Records from Obsidian Markdown

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/__init__.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/models.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/extractor.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_extractor.py`

- [ ] **Step 1: Write failing extractor tests**

Create `tests/test_asset_extractor.py`:

```python
from pathlib import Path

from src.assets.extractor import extract_assets_for_file, resolve_asset_path


def test_extracts_frontmatter_portraits_and_heading_skill_images(tmp_path):
    vault = tmp_path / "vault"
    md = vault / "100-UTTU人物合辑" / "人类｜Human" / "温妮弗雷德｜Eternity.md"
    asset_dir = md.parent / "assets" / "温妮弗雷德｜Eternity.assets"
    asset_dir.mkdir(parents=True)
    portrait = asset_dir / "立绘 温妮弗雷德 01.png"
    skill = asset_dir / "神秘术 空中来信1.png"
    portrait.write_bytes(b"portrait")
    skill.write_bytes(b"skill")
    md.write_text(
        """---
Name: 温妮弗雷德
初始立绘: "[[assets/温妮弗雷德｜Eternity.assets/立绘 温妮弗雷德 01.png]]"
---
# 温妮弗雷德

## 神秘术

> ![空中来信 一阶|100](assets/温妮弗雷德｜Eternity.assets/神秘术%20空中来信1.png)
""",
        encoding="utf-8",
    )

    records = extract_assets_for_file(md, vault, category="人物")

    roles = {record.role for record in records}
    assert roles == {"portrait", "skill"}
    skill_record = next(record for record in records if record.role == "skill")
    assert skill_record.heading_path == "神秘术"
    assert skill_record.name == "温妮弗雷德"
    assert skill_record.source == "100-UTTU人物合辑/人类｜Human/温妮弗雷德｜Eternity.md"
    assert skill_record.local_path.endswith("神秘术 空中来信1.png")


def test_resolve_asset_path_prefers_md_directory_then_vault_root(tmp_path):
    vault = tmp_path / "vault"
    md = vault / "folder" / "角色.md"
    local_asset = vault / "folder" / "assets" / "local.png"
    root_asset = vault / "assets" / "root.png"
    local_asset.parent.mkdir(parents=True)
    root_asset.parent.mkdir(parents=True)
    local_asset.write_bytes(b"local")
    root_asset.write_bytes(b"root")
    md.write_text("# x", encoding="utf-8")

    assert resolve_asset_path("assets/local.png", md, vault) == local_asset
    assert resolve_asset_path("assets/root.png", md, vault) == root_asset
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_extractor.py -q
```

Expected: import error because `src.assets.extractor` does not exist.

- [ ] **Step 3: Create asset models**

Create `src/assets/__init__.py` as an empty file.

Create `src/assets/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    name: str
    category: str
    source: str
    heading_path: str
    role: str
    alt: str
    raw_ref: str
    local_path: str
    object_key: str
    url: str
    line: int

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "AssetRecord":
        return cls(
            asset_id=str(row.get("asset_id", "")),
            name=str(row.get("name", "")),
            category=str(row.get("category", "")),
            source=str(row.get("source", "")),
            heading_path=str(row.get("heading_path", "")),
            role=str(row.get("role", "")),
            alt=str(row.get("alt", "")),
            raw_ref=str(row.get("raw_ref", "")),
            local_path=str(row.get("local_path", "")),
            object_key=str(row.get("object_key", "")),
            url=str(row.get("url", "")),
            line=int(row.get("line", 0) or 0),
        )
```

- [ ] **Step 4: Create extractor implementation**

Create `src/assets/extractor.py` with these functions and constants:

```python
from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote

import frontmatter

from src.assets.models import AssetRecord

_OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
_FRONTMATTER_IMAGE_KEYS = {"初始立绘", "本色立绘", "cover", "banner", "image", "图片"}


def resolve_asset_path(ref: str, md_path: Path, vault_root: Path) -> Path | None:
    cleaned = unquote(ref).strip().strip("'\"")
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0].strip()
    cleaned = cleaned.replace("\\", "/")
    if not cleaned:
        return None

    candidates = [
        md_path.parent / cleaned,
        vault_root / cleaned,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    basename = Path(cleaned).name
    if not basename:
        return None
    for root in (md_path.parent, vault_root):
        matches = sorted(root.rglob(basename), key=lambda item: len(str(item)))
        for match in matches:
            if match.is_file():
                return match
    return None


def _sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_key(prefix: str, role: str, local_path: Path, asset_id: str) -> str:
    suffix = local_path.suffix.lower()
    safe_role = role or "unknown"
    return f"{prefix}/{safe_role}/{asset_id[:2]}/{asset_id}{suffix}"


def _classify_role(ref: str, alt: str, heading_path: str, metadata_key: str = "") -> str:
    text = f"{metadata_key} {ref} {alt} {heading_path}"
    if any(word in text for word in ["初始立绘", "本色立绘", "立绘", "cover"]):
        return "portrait"
    if "至终的仪式" in text:
        return "ultimate"
    if "神秘术" in text:
        return "skill"
    if "心相" in text or "相从心生" in text:
        return "psychube"
    if "单品" in text:
        return "item"
    if "海报" in text or "banner" in text:
        return "poster"
    return "unknown"


def _heading_path_for_line(line: str, stack: list[tuple[int, str]]) -> str:
    match = _HEADING_RE.match(line.strip())
    if not match:
        return " > ".join(title for _, title in stack)
    level = len(match.group(1))
    title = match.group(2).strip()
    stack[:] = [(lvl, txt) for lvl, txt in stack if lvl < level]
    stack.append((level, title))
    return " > ".join(title for _, title in stack)


def _iter_body_refs(body: str) -> list[tuple[int, str, str, str]]:
    refs: list[tuple[int, str, str, str]] = []
    stack: list[tuple[int, str]] = []
    for line_no, line in enumerate(body.splitlines(), start=1):
        heading_path = _heading_path_for_line(line, stack)
        for match in _OBSIDIAN_IMAGE_RE.finditer(line):
            raw = match.group(1).strip()
            target, alt = (raw.split("|", 1) + [""])[:2] if "|" in raw else (raw, "")
            refs.append((line_no, target, alt, heading_path))
        for match in _MARKDOWN_IMAGE_RE.finditer(line):
            alt = match.group(1).strip()
            target = match.group(2).strip()
            refs.append((line_no, target, alt, heading_path))
    return refs


def _iter_frontmatter_refs(metadata: dict) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if key not in _FRONTMATTER_IMAGE_KEYS:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item)
            obsidian = _OBSIDIAN_IMAGE_RE.search(f"!{text}") or re.search(r"\[\[([^\]]+)\]\]", text)
            if obsidian:
                refs.append((key, obsidian.group(1)))
            elif Path(text).suffix.lower() in _IMAGE_SUFFIXES:
                refs.append((key, text))
    return refs


def extract_assets_for_file(
    md_path: Path,
    vault_root: Path,
    category: str,
    public_base_url: str = "",
    bucket_name: str = "",
    object_prefix: str = "reverse1999",
) -> list[AssetRecord]:
    raw_text = md_path.read_text(encoding="utf-8", errors="replace")
    post = frontmatter.loads(raw_text)
    rel_source = md_path.relative_to(vault_root).as_posix()
    name = str(post.metadata.get("Name") or md_path.stem)
    records: list[AssetRecord] = []
    seen_ids: set[str] = set()

    def add_record(line_no: int, ref: str, alt: str, heading_path: str, metadata_key: str = "") -> None:
        local = resolve_asset_path(ref, md_path, vault_root)
        if local is None or local.suffix.lower() not in _IMAGE_SUFFIXES:
            return
        asset_id = _sha1_file(local)
        if asset_id in seen_ids:
            return
        seen_ids.add(asset_id)
        role = _classify_role(ref, alt, heading_path, metadata_key)
        key = _object_key(object_prefix, role, local, asset_id)
        url = ""
        if public_base_url and bucket_name:
            url = f"{public_base_url.rstrip('/')}/{bucket_name}/{key}"
        records.append(AssetRecord(
            asset_id=asset_id,
            name=name,
            category=category,
            source=rel_source,
            heading_path=heading_path,
            role=role,
            alt=alt or local.stem,
            raw_ref=ref,
            local_path=str(local),
            object_key=key,
            url=url,
            line=line_no,
        ))

    for key, ref in _iter_frontmatter_refs(post.metadata):
        add_record(0, ref, key, "", metadata_key=key)

    for line_no, ref, alt, heading_path in _iter_body_refs(post.content):
        add_record(line_no, ref, alt, heading_path)

    records.sort(key=lambda record: (record.source, record.line, record.role, record.alt))
    return records
```

- [ ] **Step 5: Run extractor tests**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_extractor.py -q
```

Expected: tests pass.

- [ ] **Step 6: Commit checkpoint**

```powershell
git add src/assets tests/test_asset_extractor.py
git commit -m "feat: extract Obsidian image asset records"
```

---

### Task 3: Upload Assets to MinIO and Write Manifest

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/minio_store.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/build_assets.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_build_script.py`

- [ ] **Step 1: Write failing build script tests**

Create `tests/test_asset_build_script.py`:

```python
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.build_assets import build_asset_manifest


class FakeStorage:
    def upload_file(self, local_path: Path, object_key: str) -> str:
        return f"http://assets.local/reverse1999-assets/{object_key}"


def test_build_asset_manifest_writes_uploaded_urls(tmp_path):
    vault = tmp_path / "vault"
    md = vault / "100-UTTU人物合辑" / "人类｜Human" / "角色.md"
    asset_dir = md.parent / "assets" / "角色.assets"
    asset_dir.mkdir(parents=True)
    image = asset_dir / "立绘 角色 01.png"
    image.write_bytes(b"image")
    md.write_text(
        """---
Name: 角色
初始立绘: "[[assets/角色.assets/立绘 角色 01.png]]"
---
# 角色
""",
        encoding="utf-8",
    )
    processed = tmp_path / "processed"
    cfg = SimpleNamespace(
        obsidian=SimpleNamespace(vault_path=str(vault)),
        assets=SimpleNamespace(
            public_base_url="http://assets.local",
            bucket_name="reverse1999-assets",
            object_prefix="reverse1999",
        ),
        paths=SimpleNamespace(data_processed=processed),
    )

    manifest_path = build_asset_manifest(cfg, storage=FakeStorage())

    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["name"] == "角色"
    assert rows[0]["role"] == "portrait"
    assert rows[0]["url"].startswith("http://assets.local/reverse1999-assets/reverse1999/portrait/")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_build_script.py -q
```

Expected: import error because `scripts.build_assets` does not exist.

- [ ] **Step 3: Create MinIO storage wrapper**

Create `src/assets/minio_store.py`:

```python
from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import quote

from minio import Minio

from config.config import AssetStorageCfg


class MinioAssetStorage:
    def __init__(self, cfg: AssetStorageCfg) -> None:
        if not cfg.access_key or not cfg.secret_key:
            raise ValueError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set in the environment")
        self._cfg = cfg
        self._client = Minio(
            cfg.endpoint,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            secure=cfg.secure,
        )
        if not self._client.bucket_exists(cfg.bucket_name):
            self._client.make_bucket(cfg.bucket_name)

    def upload_file(self, local_path: Path, object_key: str) -> str:
        content_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
        self._client.fput_object(
            self._cfg.bucket_name,
            object_key,
            str(local_path),
            content_type=content_type,
        )
        quoted_key = quote(object_key, safe="/")
        return f"{self._cfg.public_base_url.rstrip('/')}/{self._cfg.bucket_name}/{quoted_key}"
```

- [ ] **Step 4: Create build script**

Create `scripts/build_assets.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.extraction.obsidian_extractor import _category_for
from src.assets.extractor import extract_assets_for_file
from src.assets.minio_store import MinioAssetStorage


def build_asset_manifest(cfg: Any, storage: Any | None = None) -> Path:
    vault_root = Path(cfg.obsidian.vault_path)
    out_path = Path(cfg.paths.data_processed) / "assets.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    storage = storage or MinioAssetStorage(cfg.assets)

    rows: list[dict] = []
    for md_path in sorted(vault_root.rglob("*.md")):
        rel = md_path.relative_to(vault_root).as_posix()
        category = _category_for(rel)
        if category is None:
            continue
        records = extract_assets_for_file(
            md_path,
            vault_root,
            category=category,
            public_base_url=cfg.assets.public_base_url,
            bucket_name=cfg.assets.bucket_name,
            object_prefix=cfg.assets.object_prefix,
        )
        for record in records:
            url = storage.upload_file(Path(record.local_path), record.object_key)
            row = record.to_json()
            row["url"] = url
            rows.append(row)

    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[assets] wrote {len(rows)} assets to {out_path}")
    return out_path


def main() -> None:
    build_asset_manifest(get_config())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run build script tests**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_build_script.py tests/test_asset_extractor.py -q
```

Expected: tests pass.

- [ ] **Step 6: Commit checkpoint**

```powershell
git add src/assets/minio_store.py scripts/build_assets.py tests/test_asset_build_script.py
git commit -m "feat: build MinIO asset manifest"
```

---

### Task 4: Select Assets for Ranked RAG Sources

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/src/assets/registry.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_asset_registry.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_asset_registry.py`:

```python
import json
from types import SimpleNamespace

from src.assets.registry import AssetRegistry


def test_registry_prefers_matching_source_and_heading(tmp_path):
    manifest = tmp_path / "assets.jsonl"
    rows = [
        {
            "asset_id": "a1",
            "name": "玛蒂尔达",
            "category": "人物",
            "source": "100/玛蒂尔达.md",
            "heading_path": "",
            "role": "portrait",
            "alt": "立绘 玛蒂尔达 01",
            "raw_ref": "立绘.png",
            "local_path": "D:/x/portrait.png",
            "object_key": "reverse1999/portrait/a1.png",
            "url": "http://minio/a1.png",
            "line": 0,
        },
        {
            "asset_id": "a2",
            "name": "玛蒂尔达",
            "category": "人物",
            "source": "100/玛蒂尔达.md",
            "heading_path": "神秘术",
            "role": "skill",
            "alt": "神秘术 天才习作",
            "raw_ref": "skill.png",
            "local_path": "D:/x/skill.png",
            "object_key": "reverse1999/skill/a2.png",
            "url": "http://minio/a2.png",
            "line": 60,
        },
    ]
    manifest.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    cfg = SimpleNamespace(paths=SimpleNamespace(data_processed=tmp_path))
    registry = AssetRegistry(cfg)
    plan = SimpleNamespace(intent="skill", entity="玛蒂尔达")
    sources = [{"name": "玛蒂尔达", "source": "100/玛蒂尔达.md", "heading_path": "神秘术"}]

    assets = registry.find_for_retrieval(plan, sources)

    assert [asset["asset_id"] for asset in assets] == ["a2", "a1"]


def test_registry_returns_empty_when_manifest_missing(tmp_path):
    cfg = SimpleNamespace(paths=SimpleNamespace(data_processed=tmp_path))
    registry = AssetRegistry(cfg)

    assert registry.find_for_retrieval(SimpleNamespace(intent="profile", entity="任意"), []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_registry.py -q
```

Expected: import error because `src.assets.registry` does not exist.

- [ ] **Step 3: Create registry implementation**

Create `src/assets/registry.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.config import Config
from src.assets.models import AssetRecord

_INTENT_ROLE_ORDER = {
    "skill": ["skill", "ultimate", "portrait", "unknown"],
    "profile": ["portrait", "poster", "unknown"],
    "psychube": ["psychube", "portrait", "unknown"],
    "lore": ["poster", "portrait", "unknown"],
    "voice": ["portrait", "unknown"],
    "general": ["portrait", "skill", "psychube", "unknown"],
}


class AssetRegistry:
    def __init__(self, cfg: Config) -> None:
        self._manifest_path = Path(cfg.paths.data_processed) / "assets.jsonl"
        self._records = self._load_records()

    def _load_records(self) -> list[AssetRecord]:
        if not self._manifest_path.exists():
            return []
        records: list[AssetRecord] = []
        with open(self._manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(AssetRecord.from_json(json.loads(line)))
        return records

    def find_for_retrieval(self, plan: Any, sources: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        if not self._records:
            return []
        intent = getattr(plan, "intent", "general") or "general"
        entity = getattr(plan, "entity", "") or ""
        role_order = _INTENT_ROLE_ORDER.get(intent, _INTENT_ROLE_ORDER["general"])
        source_pairs = {
            (str(source.get("source", "")), str(source.get("heading_path", "")))
            for source in sources
        }
        source_names = {str(source.get("name", "")) for source in sources}
        scored: list[tuple[tuple[int, int, int, int], AssetRecord]] = []
        for index, record in enumerate(self._records):
            if entity and record.name != entity and record.name not in source_names:
                continue
            source_match = any(record.source == src for src, _ in source_pairs)
            heading_match = any(
                record.source == src and record.heading_path and record.heading_path == heading
                for src, heading in source_pairs
            )
            if not source_match and record.name not in source_names and record.name != entity:
                continue
            role_rank = role_order.index(record.role) if record.role in role_order else len(role_order)
            score = (
                0 if heading_match else 1,
                0 if source_match else 1,
                role_rank,
                index,
            )
            scored.append((score, record))
        scored.sort(key=lambda item: item[0])
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _, record in scored:
            if record.asset_id in seen:
                continue
            seen.add(record.asset_id)
            deduped.append({
                "asset_id": record.asset_id,
                "name": record.name,
                "category": record.category,
                "source": record.source,
                "heading_path": record.heading_path,
                "role": record.role,
                "alt": record.alt,
                "url": record.url,
            })
            if len(deduped) >= limit:
                break
        return deduped
```

- [ ] **Step 4: Run registry tests**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_registry.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit checkpoint**

```powershell
git add src/assets/registry.py tests/test_asset_registry.py
git commit -m "feat: select assets for RAG sources"
```

---

### Task 5: Attach Assets in RAGChain

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/rag/chain.py`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_chain_assets.py`

- [ ] **Step 1: Write failing chain test**

Create `tests/test_chain_assets.py`:

```python
from types import SimpleNamespace

from src.rag.chain import RAGChain


class FakePlanner:
    def plan(self, question, category=None):
        return SimpleNamespace(normalized_query=question, intent="skill", entity="玛蒂尔达")


class FakeRetriever:
    def search(self, query, category=None, query_plan=None):
        return [{
            "name": "玛蒂尔达",
            "category": "人物",
            "source": "100/玛蒂尔达.md",
            "score": 1.0,
            "content": "神秘术内容",
            "heading_path": "神秘术",
            "chunk_index": 1,
            "retrieval_stage": "entity_packet",
        }]


class FakeRegistry:
    def find_for_retrieval(self, plan, sources):
        return [{"asset_id": "a2", "role": "skill", "url": "http://minio/a2.png", "alt": "神秘术"}]


def test_chain_retrieve_returns_assets(monkeypatch, tmp_path):
    cfg = SimpleNamespace(
        llm=SimpleNamespace(api_key=""),
        paths=SimpleNamespace(data_processed=tmp_path),
    )
    chain = RAGChain(cfg, FakeRetriever())
    chain._query_planner = FakePlanner()
    chain._asset_registry = FakeRegistry()

    result = chain.retrieve("玛蒂尔达的技能是什么", category="人物")

    assert result["assets"] == [{"asset_id": "a2", "role": "skill", "url": "http://minio/a2.png", "alt": "神秘术"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_chain_assets.py -q
```

Expected: fails because `RAGChain.retrieve()` does not return `assets`.

- [ ] **Step 3: Update RAGChain**

Modify `src/rag/chain.py` imports:

```python
from src.assets.registry import AssetRegistry
```

In `RAGChain.__init__`, after `self._prompt = get_rag_prompt()`, add:

```python
        self._asset_registry = AssetRegistry(cfg)
```

In `retrieve()`, replace the return with:

```python
        context = self._format_context(sources)
        assets = self._asset_registry.find_for_retrieval(plan, sources)
        return {"plan": plan, "sources": sources, "context": context, "assets": assets}
```

In `ask()`, make every return include `assets`:

```python
        assets = retrieved["assets"]
        if not self.llm_ready():
            return {"answer": _API_KEY_EMPTY_MSG, "sources": sources, "assets": assets}

        if not sources:
            return {"answer": "知识库中未找到相关内容。", "sources": [], "assets": []}
```

At the final success return:

```python
        return {"answer": answer, "sources": sources, "assets": assets}
```

At the LLM exception return:

```python
            return {"answer": f"调用 LLM 失败: {e}", "sources": sources, "assets": assets}
```

- [ ] **Step 4: Run chain and existing RAG tests**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_chain_assets.py tests/test_retriever.py -q
```

Expected: tests pass. SSE serialization is covered in Task 6.

- [ ] **Step 5: Commit checkpoint**

```powershell
git add src/rag/chain.py tests/test_chain_assets.py
git commit -m "feat: attach image assets to RAG retrieval"
```

---

### Task 6: Return Assets from FastAPI and SSE

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/schemas.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/main.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/sse.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_sse.py`

- [ ] **Step 1: Extend backend schema**

In `backend/schemas.py`, add:

```python
class AssetItem(BaseModel):
    asset_id: str
    name: str = ""
    category: str = ""
    source: str = ""
    heading_path: Optional[str] = None
    role: str
    alt: str
    url: str
```

Modify `AskResponse`:

```python
class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    assets: list[AssetItem] = []
```

- [ ] **Step 2: Update `/ask` serialization**

In `backend/main.py`, import `AssetItem`.

After `sources = [...]`, add:

```python
    assets = [
        AssetItem(
            asset_id=a["asset_id"],
            name=a.get("name", ""),
            category=a.get("category", ""),
            source=a.get("source", ""),
            heading_path=a.get("heading_path"),
            role=a["role"],
            alt=a.get("alt", ""),
            url=a["url"],
        )
        for a in result.get("assets", [])
    ]
```

Replace the response line with:

```python
    return AskResponse(answer=result["answer"], sources=sources, assets=assets)
```

- [ ] **Step 3: Update SSE payloads**

In `backend/sse.py`, after `source_items = [...]`, add:

```python
    asset_items = retrieved.get("assets", []) if "retrieved" in locals() else []
```

Change the `sources` event:

```python
    yield sse_event("sources", {"sources": source_items, "assets": asset_items})
```

Change both `done` events:

```python
        yield sse_event("done", {"answer": _API_KEY_EMPTY_MSG, "sources": source_items, "assets": asset_items})
```

```python
    yield sse_event("done", {"answer": "".join(full), "sources": source_items, "assets": asset_items})
```

- [ ] **Step 4: Update SSE tests**

Add this test to `tests/test_sse.py`:

```python
def test_ask_stream_emits_assets_with_sources_and_done(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    class Chain:
        def retrieve(self, question, category=None):
            return {
                "sources": [{
                    "name": "玛蒂尔达",
                    "category": "人物",
                    "source": "100/玛蒂尔达.md",
                    "score": 1.0,
                    "heading_path": "神秘术",
                    "chunk_index": 1,
                    "retrieval_stage": "entity_packet",
                }],
                "context": "ctx",
                "assets": [{"asset_id": "a2", "role": "skill", "url": "http://minio/a2.png", "alt": "神秘术"}],
            }

        def llm_ready(self):
            return False

    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 1}),
        "retriever": None,
        "chain": Chain(),
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    with client.stream("POST", "/ask/stream", json={"question": "q", "category": "人物"}) as resp:
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)

    assert events[0][0] == "sources"
    assert events[0][1]["assets"][0]["asset_id"] == "a2"
    assert events[-1][0] == "done"
    assert events[-1][1]["assets"][0]["url"] == "http://minio/a2.png"
```

- [ ] **Step 5: Run backend API/SSE tests**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_sse.py tests/test_chain_assets.py tests/test_categories.py -q
```

Expected: tests pass.

- [ ] **Step 6: Commit checkpoint**

```powershell
git add backend/schemas.py backend/main.py backend/sse.py tests/test_sse.py
git commit -m "feat: return RAG image assets from API"
```

---

### Task 7: Render Assets in the React Chat UI

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/types/index.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/sse.ts`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/store/chatStore.ts`
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageAssets.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageBubble.tsx`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MarkdownContent.tsx`
- Modify tests:
  - `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/api/sse.test.ts`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/store/chatStore.test.ts`
  - `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/src/components/chat/MessageBubble.test.tsx`

- [ ] **Step 1: Extend frontend types**

In `frontend/react-app/src/types/index.ts`, add:

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

Modify `Message`:

```ts
  assets?: AssetItem[]
```

- [ ] **Step 2: Update SSE parser API**

In `frontend/react-app/src/api/sse.ts`, change the type import:

```ts
import type { AssetItem, SourceItem } from '../types'
```

Change callback types:

```ts
  onSources: (sources: SourceItem[], assets?: AssetItem[]) => void
  onDone: (answer: string, sources: SourceItem[], assets?: AssetItem[]) => void
```

Change event handling:

```ts
      if (event === 'sources') callbacks.onSources(data.sources as SourceItem[], data.assets as AssetItem[] | undefined)
      else if (event === 'token') callbacks.onToken(data.token as string)
      else if (event === 'done') callbacks.onDone(data.answer as string, data.sources as SourceItem[], data.assets as AssetItem[] | undefined)
```

- [ ] **Step 3: Update chat store**

In `frontend/react-app/src/store/chatStore.ts`, update callbacks:

```ts
        onSources: (sources: SourceItem[], assets = []) =>
          updateLast({ sources, assets, status: 'DeepSeek 正在根据检索来源生成回答...' }),
```

```ts
        onDone: (answer, sources, assets = []) =>
          updateLast({ content: answer, sources, assets, streaming: false, status: undefined }),
```

- [ ] **Step 4: Create MessageAssets component**

Create `frontend/react-app/src/components/chat/MessageAssets.tsx`:

```tsx
import type { AssetItem } from '../../types'

export function MessageAssets({ assets }: { assets: AssetItem[] }) {
  if (assets.length === 0) return null

  return (
    <div
      className="message-assets"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
        gap: 10,
        marginTop: 12,
      }}
    >
      {assets.map((asset) => (
        <figure
          key={asset.asset_id}
          style={{
            margin: 0,
            border: '1px solid var(--border-subtle)',
            borderRadius: 8,
            overflow: 'hidden',
            background: 'rgba(0, 0, 0, 0.18)',
          }}
        >
          <img
            src={asset.url}
            alt={asset.alt || asset.role}
            loading="lazy"
            style={{
              display: 'block',
              width: '100%',
              maxHeight: 180,
              objectFit: 'contain',
              background: 'rgba(0, 0, 0, 0.12)',
            }}
          />
          <figcaption
            style={{
              padding: '6px 8px',
              color: 'var(--text-secondary)',
              fontSize: '0.75rem',
              lineHeight: 1.35,
            }}
          >
            {asset.alt || asset.role}
          </figcaption>
        </figure>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Render assets under assistant messages**

In `MessageBubble.tsx`, import:

```ts
import { MessageAssets } from './MessageAssets'
```

After `<MarkdownContent ... />`, add:

```tsx
          {!message.streaming && message.assets && <MessageAssets assets={message.assets} />}
```

- [ ] **Step 6: Add Markdown image fallback**

In `MarkdownContent.tsx`, add an inline parser before `parseLink(text, from)`:

```tsx
    parseImage(text, from),
```

Add this function before `parseLink`:

```tsx
function parseImage(text: string, from: number) {
  const start = text.indexOf('![', from)
  if (start === -1) {
    return null
  }
  const labelEnd = text.indexOf(']', start + 2)
  if (labelEnd === -1 || text[labelEnd + 1] !== '(') {
    return null
  }
  const srcEnd = text.indexOf(')', labelEnd + 2)
  if (srcEnd === -1) {
    return null
  }
  const alt = text.slice(start + 2, labelEnd)
  const src = sanitizeHref(text.slice(labelEnd + 2, srcEnd))
  return {
    start,
    end: srcEnd + 1,
    node: (key: string) =>
      src ? (
        <img
          key={key}
          src={src}
          alt={alt}
          loading="lazy"
          style={{ maxWidth: '100%', maxHeight: 220, objectFit: 'contain', display: 'block', margin: '8px 0' }}
        />
      ) : (
        <span key={key}>{alt}</span>
      ),
  }
}
```

- [ ] **Step 7: Update frontend tests**

In `frontend/react-app/src/api/sse.test.ts`, extend the existing sources/done fixture so `sources` and `done` include:

```ts
assets: [{ asset_id: 'a2', role: 'skill', alt: '神秘术', url: 'http://minio/a2.png' }]
```

Assert:

```ts
expect(assets[0].asset_id).toBe('a2')
```

In `frontend/react-app/src/store/chatStore.test.ts`, assert the final assistant message stores assets:

```ts
expect(msgs[1].assets?.[0].url).toBe('http://minio/a2.png')
```

In `frontend/react-app/src/components/chat/MessageBubble.test.tsx`, add:

```tsx
it('renders assistant image assets below the answer', () => {
  render(
    <MessageBubble
      message={{
        id: 'a',
        role: 'assistant',
        content: '这里是技能说明',
        assets: [{ asset_id: 'a2', role: 'skill', alt: '神秘术', url: 'http://minio/a2.png' }],
      }}
    />
  )

  const image = screen.getByRole('img', { name: '神秘术' })
  expect(image).toHaveAttribute('src', 'http://minio/a2.png')
})
```

- [ ] **Step 8: Run frontend tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run
```

Expected: all Vitest tests pass.

- [ ] **Step 9: Commit checkpoint**

```powershell
git add frontend/react-app/src/types/index.ts frontend/react-app/src/api/sse.ts frontend/react-app/src/store/chatStore.ts frontend/react-app/src/components/chat/MessageAssets.tsx frontend/react-app/src/components/chat/MessageBubble.tsx frontend/react-app/src/components/chat/MarkdownContent.tsx frontend/react-app/src/api/sse.test.ts frontend/react-app/src/store/chatStore.test.ts frontend/react-app/src/components/chat/MessageBubble.test.tsx
git commit -m "feat: render RAG image assets in chat"
```

---

### Task 8: Build Assets and Verify End-to-End

**Files:**
- Create: `D:/PycharmProjects/nlp/LangChain/1999Search/docs/rag-assets.md`
- Runtime output: `D:/PycharmProjects/nlp/LangChain/1999Search/data/processed/assets.jsonl`

- [ ] **Step 1: Install dependency**

Run:

```powershell
D:\anaconda32024\envs\LangChain\python.exe -m pip install minio
```

Expected: pip reports `Successfully installed minio` or `Requirement already satisfied`.

- [ ] **Step 2: Set MinIO credentials for the current terminal**

Use the credentials configured for the local MinIO instance:

```powershell
$env:MINIO_ACCESS_KEY="minioadmin"
$env:MINIO_SECRET_KEY="minioadmin"
```

Expected: no output.

- [ ] **Step 3: Build and upload asset manifest**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\anaconda32024\envs\LangChain\python.exe scripts\build_assets.py
```

Expected: output like:

```text
[assets] wrote 1000 assets to D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\assets.jsonl
```

The exact asset count depends on the current Obsidian vault.

- [ ] **Step 4: Spot-check manifest for character and skill assets**

Run:

```powershell
Select-String -Path D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\assets.jsonl -Pattern '"name": "玛蒂尔达"','"role": "skill"','"role": "portrait"' | Select-Object -First 20
```

Expected: lines include `玛蒂尔达`, `portrait`, and at least one `skill` asset when the source Markdown contains those images.

- [ ] **Step 5: Run backend tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_config.py tests/test_asset_extractor.py tests/test_asset_registry.py tests/test_asset_build_script.py tests/test_chain_assets.py tests/test_sse.py tests/test_config.py tests/test_retriever.py tests/test_reranker.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run
npm run build
```

Expected: Vitest passes and Vite build succeeds.

- [ ] **Step 7: Manual browser verification**

Start the backend and frontend using the existing start script:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
.\start.ps1
```

Ask:

```text
有没有温妮弗雷德的立绘
```

Expected: answer contains text plus at least one image card whose `src` starts with `http://127.0.0.1:9002/reverse1999-assets/`.

Ask:

```text
玛蒂尔达的技能是什么
```

Expected: answer prioritizes skill text and shows skill or ultimate images when those images are present in the source Markdown.

- [ ] **Step 8: Document operations**

Create `docs/rag-assets.md`:

````markdown
# RAG Image Assets

Images are extracted from the Obsidian vault before Markdown cleaning, uploaded to MinIO, and stored in `data/processed/assets.jsonl`.

Required environment variables:

```powershell
$env:MINIO_ACCESS_KEY="minioadmin"
$env:MINIO_SECRET_KEY="minioadmin"
```

Build or refresh assets:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\anaconda32024\envs\LangChain\python.exe scripts\build_assets.py
```

The frontend only receives HTTP URLs. Local `D:\...` paths are retained in the manifest for rebuild diagnostics and are not sent to the browser.
````

- [ ] **Step 9: Commit checkpoint**

```powershell
git add docs/rag-assets.md
git commit -m "docs: add RAG image asset operations"
```

`data/processed/assets.jsonl` remains a local generated file because `data/processed/` is already ignored.

---

## Final Verification

Run all relevant automated checks:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\anaconda32024\envs\LangChain\python.exe -m pytest tests/test_asset_config.py tests/test_asset_extractor.py tests/test_asset_registry.py tests/test_asset_build_script.py tests/test_chain_assets.py tests/test_sse.py tests/test_config.py tests/test_retriever.py tests/test_reranker.py tests/test_vectorstore.py -q
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run
npm run build
```

Expected:

```text
pytest: all selected tests pass
vitest: all tests pass
vite build: build succeeds
```

Manual checks:

- `有没有温妮弗雷德的立绘` returns portrait assets.
- `玛蒂尔达的技能是什么` returns skill-focused text and skill assets when present in the vault.
- Browser network panel shows image requests to `http://127.0.0.1:9002/reverse1999-assets/...`.
- No response sent to the frontend contains a local `D:\...` filesystem path.

## Self-Review

- Spec coverage: MinIO storage, raw Markdown/frontmatter image extraction, URL mapping, RAG source attachment, API/SSE transport, frontend rendering, and manual verification are covered by Tasks 1-8.
- Placeholder scan: no open implementation slots remain; every task names files, code snippets, commands, and expected results.
- Type consistency: backend `AssetItem`, frontend `AssetItem`, `RAGChain.retrieve()["assets"]`, and SSE `assets` payloads use the same core fields: `asset_id`, `role`, `alt`, `url`, `name`, `category`, `source`, and `heading_path`.
