# 1999Wiki Production Container Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce reproducible Backend and Frontend images, a server-local persistent infrastructure stack, and a tested blue/green deployment workflow whose runtime behavior is controlled by environment variables.

**Architecture:** GitHub Actions builds two immutable GHCR images from one commit. The server runs persistent MySQL, MinIO, etcd, and Milvus separately from two interchangeable application slots. Host Caddy publishes the active slot and proxies same-origin `/media/` requests to local MinIO; browser media URLs are projected from stable object keys at response time.

**Tech Stack:** Python 3.11, FastAPI/Uvicorn, React/Vite, Caddy, Docker BuildKit/Compose, MySQL 8, MinIO, etcd 3.5, Milvus 2.5, GitHub Actions/GHCR, pytest, Vitest.

## Global Constraints

- Work only on `codex/container-production-readiness` until integration is requested.
- Use test-driven development for every behavior change: demonstrate the focused test failing, implement the smallest change, then rerun it.
- Preserve the active RAG artifact closure byte-for-byte; never rewrite hash-pinned artifacts to replace old URLs.
- Never commit credentials, server environment files, persistent data, or generated runtime artifacts.
- Never run destructive volume or global Docker cleanup commands.
- Backend and Frontend images must use the same source commit and the tag format `sha-<7-char-git-sha>`.
- The production server pulls images; it does not build, crawl, package, or vectorize.
- COS remains backup-only and is not part of normal request handling.
- Run all Python commands in the `1999wiki` Conda environment.
- Before each task commit, inspect `git diff --check` and stage only files named by that task.

---

## Task 1: Make a Clean Checkout Reproducible

**Files:**

- Modify: `.gitattributes`
- Modify: `src/rag/chain.py`
- Modify: `src/rag_eval/isolated.py`
- Test: `tests/test_huiji_crawler_cmd_launchers.py`
- Test: `tests/test_huiji_start_script.py`
- Test: `tests/test_rag_eval_isolated.py`

- [ ] **Step 1: Confirm the clean-worktree failures**

Run:

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_huiji_crawler_cmd_launchers.py `
  tests/test_huiji_start_script.py `
  tests/test_rag_eval_isolated.py
```

Expected: three failures—two line-ending assertions and one isolated RAG probe that reads ignored local artifacts.

- [ ] **Step 2: Enforce Windows launcher line endings**

Append to `.gitattributes`:

```gitattributes
*.bat text eol=crlf
*.cmd text eol=crlf
```

Normalize only tracked launchers:

```powershell
git add --renormalize -- '*.bat' '*.cmd'
```

- [ ] **Step 3: Add explicit RAGChain dependency injection**

Change `RAGChain.__init__` in `src/rag/chain.py` to accept keyword-only test/runtime dependencies:

```python
def __init__(
    self,
    cfg: Config,
    retriever: Retriever,
    *,
    entity_lexicon: EntityLexicon | None = None,
    asset_registry: HuijiMediaRegistry | None = None,
) -> None:
    require_huiji_runtime_source(cfg)
    artifact_snapshot = getattr(retriever, "artifact_snapshot", None)
    resolved_lexicon = entity_lexicon or EntityLexicon.from_huiji(
        cfg,
        artifact_snapshot,
    )
    self._query_planner = QueryPlanner(
        self._planner_llm,
        entity_lexicon=resolved_lexicon,
    )
    self._asset_registry = asset_registry or HuijiMediaRegistry(
        cfg,
        artifact_snapshot=artifact_snapshot,
    )
```

Preserve all existing constructor initialization not shown above.

- [ ] **Step 4: Make the isolated evaluation probe inject fixtures**

In `src/rag_eval/isolated.py`, import `EntityLexicon`, add a probe registry that returns empty media results for every registry method used by `RAGChain`, and construct the chain with:

```python
chain = RAGChain(
    cfg,
    retriever,
    entity_lexicon=EntityLexicon(()),
    asset_registry=_ProbeAssetRegistry(),
)
```

The probe must not create or read `data/`, `vectorstore/`, or the active artifact pointer.

- [ ] **Step 5: Verify the focused baseline**

Run the command from Step 1.

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git diff --check
git add .gitattributes src/rag/chain.py src/rag_eval/isolated.py `
  tests/test_huiji_crawler_cmd_launchers.py `
  tests/test_huiji_start_script.py `
  tests/test_rag_eval_isolated.py
git commit -m "test: make clean checkout reproducible"
```

---

## Task 2: Retire Preview and Legacy Frontends

**Files:**

- Create: `frontend/react-app/src/retiredFrontendScope.test.ts`
- Modify: `frontend/react-app/src/App.tsx`
- Modify: `frontend/react-app/src/App.wiki.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/wikiRoutes.ts`
- Modify: `frontend/react-app/src/components/wiki/wikiRoutes.test.ts`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css.test.ts`
- Delete: `kimi_web/`
- Delete: `frontend/streamlit_app.py`
- Delete: `frontend/gradio_app.py`
- Delete: `frontend/html/`
- Delete: `frontend/react-app/src/components/wiki-preview/`
- Delete: `frontend/react-app/e2e/wiki-kimi-preview.spec.ts`

- [ ] **Step 1: Add a production-scope guard**

Create `frontend/react-app/src/retiredFrontendScope.test.ts`:

```typescript
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = process.cwd()

describe('formal frontend scope', () => {
  it('does not ship retired frontend implementations', () => {
    const retired = [
      '../../kimi_web',
      '../streamlit_app.py',
      '../gradio_app.py',
      '../html',
      'src/components/wiki-preview',
      'e2e/wiki-kimi-preview.spec.ts',
    ]

    for (const relativePath of retired) {
      expect(existsSync(join(root, relativePath)), relativePath).toBe(false)
    }

    const app = readFileSync(join(root, 'src/App.tsx'), 'utf8')
    const shell = readFileSync(
      join(root, 'src/components/wiki/WikiShell.tsx'),
      'utf8',
    )
    expect(app).not.toContain('/wiki-preview')
    expect(app).not.toContain('kimi-preview')
    expect(shell).not.toContain('wiki-preview')
    expect(shell).not.toContain('kimi-preview')
  })
})
```

- [ ] **Step 2: Show the guard failing**

Run:

```powershell
npm --prefix frontend/react-app test -- --run src/retiredFrontendScope.test.ts
```

Expected: failure because the retired paths and route still exist.

- [ ] **Step 3: Remove retired runtime trees and route variants**

Delete the listed directories/files with Git-aware removal. In `App.tsx`, remove the `/wiki-preview` branch. In `WikiShell.tsx` and `wikiRoutes.ts`, remove the `kimi-preview` variant, preview imports, preview-only rendering branches, and preview URL conversions. Update the named tests so they assert only `/wiki/*` formal routes.

Do not remove:

- `/wiki`
- `/wiki/characters/*`
- chat suggested questions
- mobile layout behavior
- any of the 17 referenced `public/` shell assets

- [ ] **Step 4: Verify frontend tests and production build**

```powershell
npm --prefix frontend/react-app test -- --run
npm --prefix frontend/react-app run build
```

Expected: 53-or-fewer test files pass, all remaining tests pass, and Vite emits `dist/`. The existing large-chunk warning is non-blocking.

- [ ] **Step 5: Scan the tracked production scope**

```powershell
git grep -n -I -E "wiki-preview|kimi-preview|KimiWiki|streamlit|gradio" -- `
  frontend/react-app frontend kimi_web
```

Expected: no matches in existing production inputs; Git may report that deleted pathspecs do not exist.

- [ ] **Step 6: Commit**

```powershell
git diff --check
git add -A -- kimi_web frontend
git commit -m "refactor: retire preview and legacy frontends"
```

---

## Task 3: Add the Runtime Environment Contract

**Files:**

- Modify: `config/config.py`
- Modify: `config/settings.yaml`
- Test: `tests/test_config.py`
- Test: `tests/test_asset_config.py`

- [ ] **Step 1: Add failing environment-override tests**

Add tests that set the complete production environment and assert:

```python
assert cfg.vectorstore.uri == "http://standalone:19530"
assert cfg.vectorstore.db_name == "reverse1999_rag"
assert cfg.vectorstore.collection_name == "prod_collection"
assert cfg.assets.endpoint == "minio:9000"
assert cfg.assets.secure is False
assert cfg.assets.bucket_name == "reverse1999-assets"
assert cfg.assets.public_base_url == "/media"
assert cfg.huiji.processed_root == Path("/runtime/rag/huiji")
```

Add parametrized invalid cases for:

- `MINIO_SECURE=perhaps`
- `MEDIA_PUBLIC_BASE_URL=ftp://media.example.com`
- `MEDIA_PUBLIC_BASE_URL=/media/../secret`
- `MEDIA_PUBLIC_BASE_URL=https://user:pass@example.com/media`
- `MEDIA_PUBLIC_BASE_URL=/media?token=value`

Each invalid case must raise `ValueError` naming the variable but not echoing credentials.

- [ ] **Step 2: Show the tests failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_config.py tests/test_asset_config.py
```

Expected: new override and validation assertions fail.

- [ ] **Step 3: Implement typed environment parsing**

In `config/config.py`, implement:

```python
def _env_bool(name: str, fallback: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return fallback
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
```

Apply environment overrides when constructing the configuration:

```python
VectorstoreCfg(
    uri=os.getenv("MILVUS_URI", vectorstore_yaml["uri"]),
    db_name=os.getenv("MILVUS_DB_NAME", vectorstore_yaml["db_name"]),
    collection_name=os.getenv(
        "MILVUS_COLLECTION_NAME",
        vectorstore_yaml["collection_name"],
    ),
)
```

```python
AssetStorageCfg(
    endpoint=os.getenv("MINIO_ENDPOINT", assets_yaml["endpoint"]),
    public_base_url=os.getenv(
        "MEDIA_PUBLIC_BASE_URL",
        assets_yaml["public_base_url"],
    ),
    bucket_name=os.getenv("MINIO_BUCKET", assets_yaml["bucket_name"]),
    secure=_env_bool("MINIO_SECURE", bool(assets_yaml["secure"])),
    object_prefix=assets_yaml["object_prefix"],
    access_key=os.getenv("MINIO_ACCESS_KEY", ""),
    secret_key=os.getenv("MINIO_SECRET_KEY", ""),
)
```

Resolve `HUIJI_PROCESSED_ROOT` directly as an absolute runtime path when set; retain the repository-local YAML resolution only when it is unset.

- [ ] **Step 4: Verify configuration behavior**

Run the command from Step 2.

Expected: all configuration tests pass.

- [ ] **Step 5: Commit**

```powershell
git diff --check
git add config/config.py config/settings.yaml tests/test_config.py tests/test_asset_config.py
git commit -m "feat: configure runtime services from environment"
```

---

## Task 4: Project Public Media URLs from Object Keys

**Files:**

- Create: `src/assets/public_url.py`
- Modify: `src/assets/huiji_registry.py`
- Modify: `src/assets/voice_pagination.py`
- Modify: `src/huiji_wiki/models.py`
- Modify: `src/huiji_wiki/repository.py`
- Create: `tests/test_public_media_url.py`
- Test: `tests/test_huiji_media_registry.py`
- Test: `tests/test_voice_pagination.py`
- Test: `tests/test_huiji_wiki_repository.py`
- Test: `tests/test_huiji_wiki_api.py`
- Test: `tests/test_chain_assets.py`

- [ ] **Step 1: Specify the projector with failing tests**

Create tests for:

```python
assert build_public_media_url(
    "/media",
    "reverse1999-assets",
    "reverse1999/portrait/角色 图.webp",
) == "/media/reverse1999-assets/reverse1999/portrait/%E8%A7%92%E8%89%B2%20%E5%9B%BE.webp"

assert build_public_media_url(
    "https://media.example.com/base",
    "reverse1999-assets",
    "voice/en/file.ogg",
) == "https://media.example.com/base/reverse1999-assets/voice/en/file.ogg"
```

Also assert rejection of empty keys, traversal segments, backslashes, leading
slashes, query/fragment content, and control characters. Assert
`project_media_row` ignores a stored
`http://127.0.0.1:9002/reverse1999-assets/stale.webp` URL and emits the
configured URL from `object_key`.

- [ ] **Step 2: Show projector tests failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_public_media_url.py
```

Expected: import failure because the projector does not exist.

- [ ] **Step 3: Implement the shared projector**

Implement `src/assets/public_url.py` with this complete behavior:

```python
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

def _validate_component(value: str, *, label: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError(f"{label} must not be empty")
    if "\\" in candidate or any(ord(char) < 32 for char in candidate):
        raise ValueError(f"{label} contains unsafe characters")
    if any(segment in {".", ".."} for segment in candidate.split("/")):
        raise ValueError(f"{label} contains traversal segments")
    return candidate

def normalize_public_media_base(value: str) -> str:
    candidate = _validate_component(value, label="MEDIA_PUBLIC_BASE_URL")
    parsed = urlsplit(candidate)
    if parsed.query or parsed.fragment:
        raise ValueError("MEDIA_PUBLIC_BASE_URL must not contain query or fragment")
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("MEDIA_PUBLIC_BASE_URL must use HTTP or HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("MEDIA_PUBLIC_BASE_URL must not contain credentials")
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
        )
    if parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise ValueError(
            "MEDIA_PUBLIC_BASE_URL must be a same-origin path or HTTP(S) URL"
        )
    return parsed.path.rstrip("/") or "/"

def build_public_media_url(
    base_url: str,
    bucket_name: str,
    object_key: str,
) -> str:
    base = normalize_public_media_base(base_url)
    bucket = _validate_component(bucket_name, label="MINIO_BUCKET")
    key = _validate_component(object_key, label="object_key")
    if key.startswith("/") or "?" in key or "#" in key:
        raise ValueError("object_key must be a safe relative object key")
    suffix = f"{quote(bucket, safe='-._~')}/{quote(key, safe='/-._~')}"
    return f"{base.rstrip('/')}/{suffix}"

def is_safe_public_media_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if parsed.query or parsed.fragment:
            return False
        if parsed.scheme:
            return (
                parsed.scheme in {"http", "https"}
                and bool(parsed.netloc)
                and parsed.username is None
                and parsed.password is None
            )
        return parsed.path.startswith("/") and not parsed.path.startswith("//")
    except ValueError:
        return False

def project_media_row(
    row: Mapping[str, Any],
    *,
    base_url: str,
    bucket_name: str,
) -> dict[str, Any] | None:
    object_key = str(row.get("object_key") or "").strip()
    if not object_key:
        return None
    try:
        public_url = build_public_media_url(base_url, bucket_name, object_key)
    except ValueError:
        return None
    projected = dict(row)
    projected["url"] = public_url
    return projected
```

Keep the tests as the authority for percent-encoding and unsafe-input behavior.

- [ ] **Step 4: Apply projection at both data boundaries**

In `MySQLWikiRepository`, select `object_key` wherever public media rows or first-media thumbnails are loaded. Project each record before passing it to `WikiMediaLink.from_json`. Omit records whose key is unsafe.

In `HuijiMediaRegistry`, project each loaded artifact row once during registry construction using `cfg.assets.public_base_url` and `cfg.assets.bucket_name`. This makes RAG panels and voice pagination domain-neutral without mutating the artifact.

Replace duplicate absolute-HTTP-only URL checks in voice pagination and Wiki
models with `is_safe_public_media_url`, which accepts projected same-origin
media paths.

- [ ] **Step 5: Add boundary regression tests**

Add assertions that:

- Wiki list thumbnails use `/media/<bucket>/<key>`.
- Wiki detail media omit unsafe/missing keys.
- a stored loopback URL is never returned.
- RAG registry output and voice pages use projected URLs.
- absolute HTTPS media bases remain supported.

- [ ] **Step 6: Verify all media paths**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_public_media_url.py `
  tests/test_huiji_media_registry.py `
  tests/test_voice_pagination.py `
  tests/test_huiji_wiki_repository.py `
  tests/test_huiji_wiki_api.py `
  tests/test_chain_assets.py
```

Then run:

```powershell
git grep -n "127.0.0.1:9002" -- backend src config
```

Expected: tests pass; no production response decision depends on the old
loopback URL. The exact stale loopback fixture above remains only in the
projector regression test that proves replacement.

- [ ] **Step 7: Commit**

```powershell
git diff --check
git add src/assets/public_url.py src/assets/huiji_registry.py `
  src/assets/voice_pagination.py src/huiji_wiki/models.py `
  src/huiji_wiki/repository.py tests
git commit -m "feat: project public media urls at response time"
```

---

## Task 5: Remove the Milvus Query Window Violation

**Files:**

- Modify: `backend/main.py`
- Modify: `tests/test_categories.py`

- [ ] **Step 1: Add iterator and failure-observability tests**

Use a fake Milvus iterator whose `next()` returns two non-empty batches and then an empty batch. Assert `_count_by_category` returns the total, requests `batch_size=1000` and `limit=-1`, and calls `close()` even if `next()` raises. Assert the old `query(limit=100000)` method is never called.

- [ ] **Step 2: Show the new test failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_categories.py
```

Expected: the iterator assertions fail against the current implementation.

- [ ] **Step 3: Implement bounded iteration**

Replace the large query with:

```python
iterator = vs.client.query_iterator(
    collection_name=vs.collection_name,
    batch_size=1000,
    limit=-1,
    filter=f'category == "{escaped_category}"',
    output_fields=["id"],
)
try:
    count = 0
    while True:
        batch = iterator.next()
        if not batch:
            return count
        count += len(batch)
finally:
    iterator.close()
```

Reuse the repository’s established Milvus filter escaping helper. If no helper exists, escape backslashes and double quotes locally and cover both cases in tests. Log query exceptions with the category key and re-raise them to the existing endpoint-level diagnostic path.

- [ ] **Step 4: Verify**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_categories.py
git grep -n "limit=100000" -- backend src
```

Expected: tests pass and the scan has no production match.

- [ ] **Step 5: Commit**

```powershell
git diff --check
git add backend/main.py tests/test_categories.py
git commit -m "fix: count Milvus categories with an iterator"
```

---

## Task 6: Split and Lock Python Dependencies

**Files:**

- Create: `requirements/runtime.in`
- Create: `requirements/runtime.lock.txt`
- Create: `requirements/dev.in`
- Create: `requirements/dev.lock.txt`
- Modify: `requirements.txt`
- Create: `tests/test_runtime_requirements.py`

- [ ] **Step 1: Add a failing runtime-boundary test**

Create `tests/test_runtime_requirements.py` that parses `requirements/runtime.in` and asserts the normalized package set excludes:

```python
{
    "streamlit",
    "gradio",
    "playwright",
    "pytest",
    "chromadb",
    "langchain-chroma",
}
```

Also assert `requirements.txt` contains exactly:

```text
-r requirements/dev.lock.txt
```

- [ ] **Step 2: Show the test failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_runtime_requirements.py
```

Expected: failure because the split files do not exist.

- [ ] **Step 3: Define direct runtime and development inputs**

Build `requirements/runtime.in` from imports reachable from:

- `backend/main.py`
- `config/config.py`
- `src/rag/`
- `src/assets/`
- `src/huiji_wiki/`
- runtime health/readiness modules

Put only direct packages in the input. Use compatible direct constraints already proven by the `1999wiki` environment. Define `requirements/dev.in` as:

```text
-r runtime.in
pytest
pytest-asyncio
httpx
pip-tools
```

Add any repository test tool discovered by `rg -n "^(import|from) " tests` only if tests import it directly.

- [ ] **Step 4: Generate deterministic Python 3.11 locks**

```powershell
conda run -n 1999wiki python -m pip install "pip-tools==7.5.1"
conda run -n 1999wiki python -m piptools compile `
  --resolver=backtracking `
  --strip-extras `
  --output-file requirements/runtime.lock.txt `
  requirements/runtime.in
conda run -n 1999wiki python -m piptools compile `
  --resolver=backtracking `
  --strip-extras `
  --output-file requirements/dev.lock.txt `
  requirements/dev.in
```

Replace root `requirements.txt` with the one-line development-lock include.

- [ ] **Step 5: Verify in a temporary virtual environment**

```powershell
py -3.11 -m venv .tmp-runtime-venv
.\.tmp-runtime-venv\Scripts\python.exe -m pip install `
  -r requirements/runtime.lock.txt
.\.tmp-runtime-venv\Scripts\python.exe -c `
  "import backend.main; print('runtime-import-ok')"
Remove-Item -LiteralPath .tmp-runtime-venv -Recurse -Force
conda run -n 1999wiki python -m pytest -q tests/test_runtime_requirements.py
```

Expected: `runtime-import-ok` and the boundary test passes. Verify the absolute temporary path is inside the worktree before removing it.

- [ ] **Step 6: Commit**

```powershell
git diff --check
git add requirements.txt requirements tests/test_runtime_requirements.py
git commit -m "build: split and lock Python dependencies"
```

---

## Task 7: Add Production Docker Images

**Files:**

- Create: `.dockerignore`
- Create: `docker/Dockerfile.backend`
- Create: `docker/Dockerfile.frontend`
- Create: `docker/frontend.Caddyfile`
- Create: `tests/test_docker_packaging.py`

- [ ] **Step 1: Add failing packaging-contract tests**

Test that:

- both Dockerfiles exist;
- Backend installs only `requirements/runtime.lock.txt`;
- Backend copies `backend`, runtime-only Python modules, and runtime config;
- Backend runs as a non-root user with one Uvicorn worker;
- Frontend has a Node build stage and Caddy runtime stage;
- `.dockerignore` excludes `.git`, `.worktrees`, `.env`, `data`, `vectorstore`, `node_modules`, `dist`, tests, crawler outputs, logs, and backups;
- neither image Dockerfile copies MySQL, MinIO, Milvus, RAG artifact payloads, crawler inputs, evaluation outputs, or local credentials.

- [ ] **Step 2: Show packaging tests failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_docker_packaging.py
```

Expected: missing-file failures.

- [ ] **Step 3: Implement the Backend image**

Use `python:3.11.15-slim-bookworm` with a dependency stage and runtime stage. The final stage must:

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY backend ./backend
COPY config/config.py config/settings.yaml ./config/
COPY config/provenance ./config/provenance
COPY src/__init__.py ./src/
COPY src/rag ./src/rag
COPY src/assets ./src/assets
COPY src/utils ./src/utils
COPY src/huiji_wiki/__init__.py src/huiji_wiki/models.py \
     src/huiji_wiki/repository.py ./src/huiji_wiki/
COPY src/huijiwiki/__init__.py src/huijiwiki/models.py \
     src/huijiwiki/project_paths.py ./src/huijiwiki/
COPY src/huiji_rag/__init__.py src/huiji_rag/active_pointer.py \
     src/huiji_rag/io.py src/huiji_rag/media.py src/huiji_rag/models.py \
     src/huiji_rag/normalizer.py src/huiji_rag/provenance.py \
     src/huiji_rag/runtime_artifacts.py src/huiji_rag/source.py \
     ./src/huiji_rag/
COPY src/huiji_rag/build/__init__.py src/huiji_rag/build/contracts.py \
     ./src/huiji_rag/build/
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

Install `requirements/runtime.lock.txt` into `/opt/venv` in the dependency stage.
The packaging test must import `backend.main` from the built image so this
explicit module allow-list fails immediately if a runtime dependency is absent.

- [ ] **Step 4: Implement the Frontend image**

Use `node:22.23.1-alpine` for the build stage and `caddy:2.11.4-alpine` for
runtime. Run `npm ci` and `npm run build`, then copy only `dist/` plus
`docker/frontend.Caddyfile`.

The container Caddyfile must:

```caddyfile
:8080 {
	handle /health {
		reverse_proxy backend:8000
	}
	handle /api/* {
		reverse_proxy backend:8000
	}
	handle {
		root * /srv
		try_files {path} /index.html
		file_server
	}
}
```

- [ ] **Step 5: Verify Docker definitions and clean-context builds**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_docker_packaging.py
docker build -f docker/Dockerfile.backend -t 1999wiki-backend:test .
docker build -f docker/Dockerfile.frontend -t 1999wiki-frontend:test .
docker run --rm 1999wiki-backend:test sh -c `
  "test ! -e /app/tests && test ! -e /app/data && test ! -e /app/vectorstore"
docker run --rm 1999wiki-frontend:test sh -c `
  "test ! -e /srv/src && test ! -e /srv/node_modules"
```

Expected: both builds succeed and forbidden paths are absent.

- [ ] **Step 6: Commit**

```powershell
git diff --check
git add .dockerignore docker tests/test_docker_packaging.py
git commit -m "build: add production application images"
```

---

## Task 8: Add Persistent Infrastructure and Application Compose

**Files:**

- Create: `deploy/compose.infra.yml`
- Create: `deploy/compose.app.yml`
- Create: `deploy/env/infra.env.example`
- Create: `deploy/env/app.env.example`
- Create: `deploy/env/release.env.example`
- Create: `tests/test_production_compose.py`

- [ ] **Step 1: Add failing Compose contract tests**

Parse both YAML files and assert:

- infra owns MySQL, MinIO, etcd, and Milvus;
- every infra service has a pinned image, healthcheck, and `restart: unless-stopped`;
- Milvus depends on healthy etcd and MinIO;
- MinIO API binds only to loopback;
- secrets use required interpolation and have no default password;
- app Backend and Frontend have healthchecks, bounded JSON logs, and restart policy;
- Backend mounts `/srv/1999wiki/rag-artifacts:/runtime/rag/huiji:ro`;
- Frontend and Backend share a slot-private network;
- only Backend joins external `1999wiki-infra`;
- app images are supplied by `BACKEND_IMAGE` and `FRONTEND_IMAGE`.

- [ ] **Step 2: Show the tests failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_production_compose.py
```

Expected: missing-file failures.

- [ ] **Step 3: Implement persistent infrastructure Compose**

Use the already proven repository versions:

```yaml
mysql: mysql:8.0.46-bookworm
minio: minio/minio:RELEASE.2025-09-07T16-13-09Z
etcd: quay.io/coreos/etcd:v3.5.25
standalone: milvusdb/milvus:v2.5.27
```

Mount:

```text
/srv/1999wiki/mysql
/srv/1999wiki/minio
/srv/1999wiki/etcd
/srv/1999wiki/milvus
```

Create the external network as `1999wiki-infra`. Bind MinIO API as `127.0.0.1:${MINIO_HOST_PORT:-19000}:9000`. Keep MinIO Console, MySQL, Milvus, and diagnostic UI ports unpublished by default.

- [ ] **Step 4: Implement slot-local application Compose**

Backend joins the slot default network and `1999wiki-infra`; Frontend joins only the slot default network. Add:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

Use loopback slot ports:

```yaml
backend:
  ports:
    - "127.0.0.1:${BACKEND_PORT}:8000"
frontend:
  ports:
    - "127.0.0.1:${FRONTEND_PORT}:8080"
```

Use `app.env` only for non-release runtime settings and `release.env` for immutable image references and slot ports. Do not put secret values in examples.

- [ ] **Step 5: Render both Compose configurations**

Create an ignored temporary validation environment with non-secret dummy values, then run:

```powershell
docker network inspect 1999wiki-infra *> $null
if ($LASTEXITCODE -ne 0) { docker network create 1999wiki-infra }
docker compose --env-file deploy/env/infra.env.example `
  -f deploy/compose.infra.yml config
docker compose --env-file deploy/env/release.env.example `
  -f deploy/compose.app.yml config
conda run -n 1999wiki python -m pytest -q tests/test_production_compose.py
```

Expected: both renders succeed and tests pass. Examples use recognizable non-secret validation values and comments instruct operators to replace them outside Git.

- [ ] **Step 6: Commit**

```powershell
git diff --check
git add deploy/compose.infra.yml deploy/compose.app.yml deploy/env `
  tests/test_production_compose.py
git commit -m "ops: add persistent production compose stacks"
```

---

## Task 9: Add Host Caddy and Blue/Green Operations

**Files:**

- Create: `deploy/Caddyfile`
- Create: `deploy/caddy/active-upstream.caddy.example`
- Create: `deploy/env/caddy.env.example`
- Create: `deploy/bin/preflight.sh`
- Create: `deploy/bin/deploy.sh`
- Create: `deploy/bin/switch.sh`
- Create: `deploy/bin/rollback.sh`
- Create: `deploy/bin/smoke-test.sh`
- Create: `deploy/bin/cleanup.sh`
- Create: `tests/test_deploy_scripts.py`

- [ ] **Step 1: Add failing static operation-safety tests**

Assert every script uses `set -Eeuo pipefail`, quotes variable expansions, and contains neither:

```text
docker compose down -v
docker system prune
docker volume prune
cat *.env
docker inspect
```

Assert switching validates Caddy before atomic replacement, deployment never switches before smoke tests, and rollback does not touch the infra Compose file.

- [ ] **Step 2: Show the safety tests failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_deploy_scripts.py
```

Expected: missing-file failures.

- [ ] **Step 3: Implement host Caddy routing**

Create `deploy/Caddyfile`:

```caddyfile
{$SITE_ADDRESS} {
	handle_path /media/* {
		reverse_proxy {$MINIO_PROXY_UPSTREAM}
	}

	handle {
		import /etc/caddy/active-upstream.caddy
	}
}
```

Create the initial upstream fragment:

```caddyfile
reverse_proxy 127.0.0.1:18080
```

The example environment is:

```dotenv
SITE_ADDRESS=:80
MINIO_PROXY_UPSTREAM=127.0.0.1:19000
```

Changing `SITE_ADDRESS` to the bound domain is the only routing change needed after DNS is ready.

- [ ] **Step 4: Implement deployment and switch scripts**

`preflight.sh` must validate Docker/Compose/Caddy availability, required files, at least 8 GiB free disk, memory visibility, image tag format, RAG closure existence, and target slot inactivity.

`deploy.sh` must:

1. accept the release SHA tag and target slot;
2. pull exactly the two image references;
3. start the target with `docker compose -p "1999wiki-${slot}"`;
4. wait for Backend and Frontend health;
5. call `smoke-test.sh`;
6. stop without switching if smoke tests fail;
7. call `switch.sh` only after all checks pass.

`switch.sh` must write a temporary `reverse_proxy 127.0.0.1:${FRONTEND_PORT}` fragment, run `caddy validate`, save the previous fragment, atomically `mv` the candidate, reload Caddy, and record the active slot/release.

`rollback.sh` must restart the recorded previous app project if stopped, restore the prior fragment atomically, validate, reload, and leave data services untouched.

- [ ] **Step 5: Implement smoke and targeted cleanup**

`smoke-test.sh` must validate:

- `/health`
- formal React shell asset response
- `/api` reachability
- Wiki list and one detail request
- one RAG request including SSE termination
- a returned media URL begins with `/media/` or configured HTTPS base
- the returned media object is retrievable through host Caddy

`cleanup.sh` may remove only explicitly named old app projects and explicitly named old `sha-*` images after confirmation. It must not prune global Docker state.

- [ ] **Step 6: Verify scripts**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_deploy_scripts.py
docker run --rm -v "${PWD}/deploy:/deploy:ro" koalaman/shellcheck:v0.10.0 `
  /deploy/bin/preflight.sh `
  /deploy/bin/deploy.sh `
  /deploy/bin/switch.sh `
  /deploy/bin/rollback.sh `
  /deploy/bin/smoke-test.sh `
  /deploy/bin/cleanup.sh
```

Expected: tests and ShellCheck pass.

- [ ] **Step 7: Commit**

```powershell
git diff --check
git add deploy/Caddyfile deploy/caddy deploy/env/caddy.env.example deploy/bin `
  tests/test_deploy_scripts.py
git commit -m "ops: add blue green deployment controls"
```

---

## Task 10: Add Manual GHCR Publishing

**Files:**

- Create: `.github/workflows/publish-images.yml`
- Create: `tests/test_ghcr_workflow.py`

- [ ] **Step 1: Add a failing workflow contract test**

Assert the workflow:

- has only `workflow_dispatch`;
- grants `contents: read` and `packages: write`;
- checks out with Git LFS;
- runs Python and frontend tests/build before publishing;
- uses Buildx;
- logs into `ghcr.io` with `GITHUB_TOKEN`;
- publishes exactly:
  - `ghcr.io/ddomelette/1999wiki-backend:sha-<7-char-sha>`
  - `ghcr.io/ddomelette/1999wiki-frontend:sha-<7-char-sha>`
- builds both from the same checked-out SHA;
- writes both image digests to the job summary;
- contains no SSH or deployment step.

- [ ] **Step 2: Show the test failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_ghcr_workflow.py
```

Expected: missing workflow failure.

- [ ] **Step 3: Implement the workflow**

Use pinned major action releases:

```yaml
actions/checkout@v4
actions/setup-python@v5
actions/setup-node@v4
docker/setup-buildx-action@v3
docker/login-action@v3
docker/build-push-action@v6
```

Compute the tag in one shell step:

```bash
short_sha="${GITHUB_SHA::7}"
echo "tag=sha-${short_sha}" >> "$GITHUB_OUTPUT"
```

Build the Backend and Frontend from `docker/Dockerfile.backend` and `docker/Dockerfile.frontend`, both with context `.`, and enable GitHub Actions cache. Check out and pull LFS before tests. Publish only after all verification jobs succeed.

- [ ] **Step 4: Verify workflow syntax and contract**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_ghcr_workflow.py
docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:1.7.7
```

Expected: tests and actionlint pass.

- [ ] **Step 5: Commit**

```powershell
git diff --check
git add .github/workflows/publish-images.yml tests/test_ghcr_workflow.py
git commit -m "ci: publish immutable application images to GHCR"
```

---

## Task 11: Add Production Readiness and Artifact-Closure Gates

**Files:**

- Modify: `backend/main.py`
- Modify: `backend/schemas.py`
- Create: `tests/test_production_readiness.py`
- Create: `deploy/bin/verify-rag-closure.py`
- Modify: `deploy/bin/preflight.sh`

- [ ] **Step 1: Add failing readiness tests**

Add tests for production mode that assert readiness fails distinctly when:

- Milvus configuration is missing or still points to a loopback endpoint;
- MinIO credentials are missing;
- MySQL credentials are missing;
- the active RAG pointer is missing;
- any of the 10 files referenced by the pointer/manifests is missing or hash-mismatched.

Assert the response identifies only the failing subsystem and does not expose secret values.

- [ ] **Step 2: Show readiness tests failing**

```powershell
conda run -n 1999wiki python -m pytest -q tests/test_production_readiness.py
```

Expected: new readiness distinctions fail.

- [ ] **Step 3: Implement explicit production readiness**

Use an explicit `APP_ENV=production` switch. In production, validate:

```text
configuration
rag_artifacts
milvus
minio
mysql
```

Return non-200 readiness until all required dependencies are usable. Keep liveness lightweight and separate if the existing `/health` contract is used by the container; otherwise add `/health/live` and `/health/ready` and update Docker/Compose/Caddy tests consistently.

Implement `verify-rag-closure.py` to start from `active_build.v1.json`, follow only relative paths declared by the active pointer and manifests, reject paths escaping the mounted root, verify all recorded hashes/sizes, and assert the expected current closure count is 11. Do not hardcode artifact content hashes in source; read them from signed-in-Git manifests and the mounted pointer.

- [ ] **Step 4: Connect preflight to closure verification**

Call:

```bash
python3 deploy/bin/verify-rag-closure.py \
  --root /srv/1999wiki/rag-artifacts
```

before pulling or starting a candidate slot.

- [ ] **Step 5: Verify readiness**

```powershell
conda run -n 1999wiki python -m pytest -q `
  tests/test_production_readiness.py `
  tests/test_backend_provenance_gate.py
conda run -n 1999wiki python deploy/bin/verify-rag-closure.py `
  --root data/processed/huiji
```

Expected: health tests pass and the current local closure reports exactly 11
verified files totaling 222,789,868 bytes.

- [ ] **Step 6: Commit**

```powershell
git diff --check
git add backend/main.py backend/schemas.py deploy/bin/preflight.sh `
  deploy/bin/verify-rag-closure.py tests/test_production_readiness.py `
  tests/test_backend_provenance_gate.py
git commit -m "feat: enforce production readiness gates"
```

---

## Task 12: Run the Full Release Verification

**Files:**

- Modify: `docs/superpowers/specs/2026-07-23-production-container-readiness-design.md`
- Modify: `docs/codex/specs/2026-07-17-1999wiki-migration-container-blue-green-deployment-draft.md`
- Create: `docs/codex/production-deployment-runbook.md`

- [ ] **Step 1: Verify from the feature worktree**

```powershell
conda run -n 1999wiki python -m pytest -q
npm --prefix frontend/react-app test -- --run
npm --prefix frontend/react-app run build
git diff --check
git status --short
```

Expected baseline:

- Python: all tests pass with only the two intentionally skipped tests and documented warnings.
- Frontend: all remaining tests pass.
- Frontend production build succeeds.
- No whitespace errors.

- [ ] **Step 2: Run production-input scans**

```powershell
git grep -n -I -E "wiki-preview|kimi-preview|KimiWiki|127\\.0\\.0\\.1:9002|127\\.0\\.0\\.1:19600|limit=100000" -- `
  backend src config frontend/react-app docker deploy
git ls-files | rg "^(kimi_web/|frontend/(streamlit_app\\.py|gradio_app\\.py|html/)|frontend/react-app/src/components/wiki-preview/)"
```

Expected: no output, except intentional loopback host binds in deployment configuration; those must be `127.0.0.1` host diagnostics and never Backend service-discovery endpoints.

- [ ] **Step 3: Rebuild and inspect images**

```powershell
$sha = (git rev-parse --short=7 HEAD)
docker build --pull -f docker/Dockerfile.backend `
  -t "ghcr.io/ddomelette/1999wiki-backend:sha-$sha" .
docker build --pull -f docker/Dockerfile.frontend `
  -t "ghcr.io/ddomelette/1999wiki-frontend:sha-$sha" .
docker image inspect "ghcr.io/ddomelette/1999wiki-backend:sha-$sha" `
  "ghcr.io/ddomelette/1999wiki-frontend:sha-$sha"
```

Expected: both images build from the same commit and have no embedded data volumes, secrets, test trees, or development frontends.

- [ ] **Step 4: Run a local Compose smoke deployment**

Use temporary local directories and non-production test credentials. Start infra, wait for health, start one app slot, seed only the minimum test database/bucket/artifact fixture needed for smoke tests, and run:

```powershell
bash deploy/bin/smoke-test.sh `
  --base-url http://127.0.0.1 `
  --expected-media-base /media
```

Expected: `/health`, `/api`, Wiki, RAG/SSE, shell assets, and `/media` all pass. Tear down only the named test projects without `-v`; remove only explicitly created temporary directories after verifying their resolved absolute paths are inside the worktree.

- [ ] **Step 5: Update operator documentation**

Document:

- server directory layout under `/srv/1999wiki`;
- one-time Docker, Compose, and host Caddy installation;
- GHCR login and pull;
- infrastructure startup;
- application and release environment creation;
- IP-only `SITE_ADDRESS=:80`;
- later DNS A/AAAA binding and `SITE_ADDRESS=wiki.example.com`;
- candidate deploy, switch, observation, rollback, and targeted cleanup;
- backup ownership and the rule that COS is not in the runtime path;
- no Codex CLI requirement on the production server.

Mark the original container spec as an initial draft and link the final design, implementation plan, and runbook.

- [ ] **Step 6: Commit documentation and verification evidence**

```powershell
git diff --check
git add docs
git commit -m "docs: add production deployment runbook"
```

- [ ] **Step 7: Review the complete branch**

```powershell
git log --oneline --decorate main..HEAD
git diff --stat main...HEAD
git status --short
```

Expected: a clean worktree and a task-by-task commit series ready for code review. Do not merge or push this feature branch until the user requests the integration step.

---

## Final Review Checklist

- [ ] Every requirement in `2026-07-23-production-container-readiness-design.md` maps to at least one task above.
- [ ] Every behavior change has a focused failing test before implementation.
- [ ] Clean-checkout line endings and ignored-artifact isolation are fixed first.
- [ ] Runtime data remains outside images and is mounted read-only where appropriate.
- [ ] Media delivery is local to the server and domain-neutral.
- [ ] Both blue and green slots share persistent infrastructure without sharing their private app networks.
- [ ] No server build, crawler, vectorizer, COS fetch, SSH-from-CI, or automatic deployment path was introduced.
- [ ] Rollback changes only the active application upstream and never mutates data services.
- [ ] Publishing uses immutable `sha-*` Backend and Frontend tags from one commit.
