# Backend Recovery Strategy

## Context

This document covers backend recovery after untracked Huiji/wiki/RAG source files were deleted during repository cleanup.

The current backend has been made importable again with reconstructed files, but several modules were rebuilt from bytecode hints, existing call sites, and tests rather than restored from original source. Treat the current state as a recovery baseline, not as the final architecture.

Git must not be used during this recovery phase. Work only through filesystem edits, searches, and runtime/test checks.

## Scope

Backend recovery includes:

- `backend/wiki.py`
- `backend/wiki_schemas.py`
- `src/huiji_rag/io.py`
- `src/huiji_rag/text.py`
- `src/huiji_rag/media.py`
- `src/huiji_wiki/models.py`
- `src/huiji_wiki/repository.py`
- `src/assets/huiji_registry.py`

Do not spend time perfecting MySQL schema behavior yet. MySQL will be rebuilt separately.

## Current Known State

`src.huiji_rag.io` has been restored with:

- `HuijiBuildPaths`
- `build_paths`
- `iter_jsonl`
- `write_jsonl`
- `write_json`

`src.huiji_rag.text` has been restored with:

- `clean_huiji_text`
- `compact_lines`
- `short_summary`

`src.assets.huiji_registry.HuijiMediaRegistry` has been restored enough for the RAG chain to import and attach media candidates from `media_assets.jsonl`.

`backend/wiki.py` and `src.huiji_wiki.repository` are conservative compatibility implementations. They should be considered temporary until the new MySQL schema is defined.

## Main Risks

The restored Python files are not guaranteed to match the deleted original source.

`src/huiji_rag/media.py` and `src/assets/huiji_registry.py` may differ from the original media matching behavior in:

- asset type classification
- duplicate selection
- `attach_policy` handling
- audio/video intent routing
- object key and public URL generation

`src/huiji_wiki/repository.py` may differ from the original database behavior in:

- pagination
- category ordering
- page route resolution
- relation/link span queries
- fallback media lookup

`test_sse.py` cannot currently be used as a reliable recovery signal because the local Anaconda environment fails while importing `torch` through `langchain_openai` / `transformers`.

## Repair Phases

### Phase 1: Stabilize Imports

Goal: all backend modules needed by current app startup can import without missing local modules.

Checks:

```powershell
@'
import backend.wiki
import backend.wiki_schemas
import src.huiji_rag.io
import src.huiji_rag.text
import src.huiji_rag.media
import src.assets.huiji_registry
import src.huiji_wiki.models
import src.huiji_wiki.repository
print("backend recovery imports ok")
'@ | python -
```

Expected result:

```text
backend recovery imports ok
```

### Phase 2: Lock `huiji_rag.io`

Goal: ensure RAG build/read helpers are stable.

Required behavior:

- `build_paths(cfg)` resolves paths from `cfg.huiji.raw_root`, `processed_root`, and `build_version`.
- `iter_jsonl(path)` yields dict rows and silently handles missing files.
- `write_jsonl(path, rows)` creates parent directories and writes UTF-8 JSONL.
- `write_json(path, payload)` creates parent directories and writes UTF-8 JSON.

Validation:

```powershell
python -m pytest tests/test_retriever.py -q
```

### Phase 3: Lock Text Cleanup

Goal: preserve Huiji text cleanup semantics used by RAG and tests.

Required behavior:

- HTML tags are stripped.
- `<br>` and closing paragraph tags become line breaks.
- `[[target|label]]` becomes `label`.
- `[[target]]` becomes `target`.
- blank lines are compacted.
- `short_summary` respects sentence boundaries where possible.

Validation:

```powershell
python -m pytest tests/test_text_cleaner.py -q
```

### Phase 4: Repair Media Attachment

Goal: make RAG answers attach relevant images/audio/video without relying on wiki frontend reconstruction.

Primary files:

- `src/huiji_rag/media.py`
- `src/assets/huiji_registry.py`

Required checks:

- media rows with unavailable files are skipped.
- common/global assets are skipped for answer attachments.
- `media_intent=image` allows image-like assets.
- `media_intent=audio` restricts to voice assets.
- `media_intent=video` restricts to video assets.
- child match scores above parent match.
- duplicate media candidates prefer better formats.

Suggested focused tests to add later:

```python
def test_huiji_registry_prefers_child_media_over_parent_media():
    ...

def test_huiji_registry_audio_intent_returns_only_voice():
    ...

def test_huiji_registry_dedupes_same_asset_with_preferred_format():
    ...
```

### Phase 5: Keep Wiki Backend Minimal Until MySQL Rebuild

Goal: keep `/api/wiki/*` routes importable and failure-safe, without investing in final SQL behavior.

Temporary acceptable behavior:

- `/api/wiki/categories` returns an empty list when DB is unavailable.
- `/api/wiki/pages` returns an empty list when DB is unavailable.
- `/api/wiki/pages/{page_id}` returns 404 when DB is unavailable or page is missing.
- `/api/wiki/routes/resolve` returns `route: null` when DB is unavailable.

Do not expand repository behavior until the rebuilt MySQL schema is stable.

### Phase 6: Verification Set

Run this backend recovery verification set:

```powershell
python -m pytest tests/test_retriever.py tests/test_text_cleaner.py tests/test_chain_assets.py -q
```

Expected current result:

```text
18 passed
```

Do not use `test_sse.py` as a blocking check until the local `torch` DLL issue is fixed.

## Deferred Work

After MySQL is rebuilt:

- rewrite `src/huiji_wiki/repository.py` against the final schema.
- add repository tests using a fake or temporary database layer.
- add route tests for `/api/wiki/categories`, `/api/wiki/pages`, `/api/wiki/pages/{page_id}`, and `/api/wiki/routes/resolve`.

After Python environment is fixed:

- rerun `tests/test_sse.py`.
- verify FastAPI startup.
- verify `/ask/stream` returns sources, route metadata, actions, media, and done events.
