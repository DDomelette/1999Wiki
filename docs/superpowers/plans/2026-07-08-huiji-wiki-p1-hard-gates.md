# Huiji Wiki P1 Hard-Gate Implementation Plan

Date: 2026-07-08
Scope: Wiki P1 recovery after P0 verification
Rule: this plan is the hard acceptance checklist. A task is not complete until its listed verification passes.

Status: completed. Follow-up native 8000 and MySQL migration work is tracked in `docs/superpowers/plans/2026-07-08-huiji-wiki-native-8000-mysql-migration.md`.

## 1. Scope

This plan starts only after Wiki P0 has passed backend tests, frontend tests, build, read-only E2E, and browser verification.

P1 tasks in scope:

- `API-P1-01`: category metadata, alias fallback, cursor pagination, and search ordering.
- `API-P1-03`: add `GET /api/wiki/pages/by-route`.
- `FRONTEND-P1-01`: pass category metadata to the frontend workspace as animation/template/theme hooks.
- `FRONTEND-P1-03`: add a basic mobile layout where index and reader remain primary, while rail/info can collapse.
- `LINK-P1-02`: validate Wiki keyword target routes before navigation when validation is enabled.
- `VERIFY-P1-03`: make media coverage verification repeatable as a read-only inspection.
- `DB-P1-PLAN`: document the project-owned MySQL migration path. This plan does not migrate data.

Out of scope:

- No MinIO upload, delete, migration, or direct object-pool scan for Wiki rendering.
- No Milvus rebuild, collection switch, or vectorization.
- No RAG retrieval, ingestion, SSE, or chat-output changes.
- No Wiki builder rerun or overwrite of `wiki_*` tables.
- No Docker MySQL migration execution until a separate migration plan is approved.

## 2. Hard Acceptance Gates

| Gate | Implementation | Required verification | Failure means |
|---|---|---|---|
| `P1-GATE-00` | Read-only boundary | `git status --short -- src/rag backend/main.py data/processed/huiji/dev` reviewed; no new edits from Wiki work | Wiki work touched RAG or processed artifacts |
| `P1-GATE-01` | API-P1-01 | `python -m pytest tests/test_huiji_wiki_repository.py -q` | Search/category behavior not proven |
| `P1-GATE-02` | API-P1-03 | `python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q` | `/api/wiki/pages/by-route` contract not proven |
| `P1-GATE-03` | Frontend API | `npm run test -- --run src/api/wiki.test.ts` | frontend cannot consume new API |
| `P1-GATE-04` | Metadata/mobile layout | `npm run test -- --run src/components/wiki/WikiShell.test.tsx src/components/wiki/CategoryRail.test.tsx` | metadata hooks or mobile layout not proven |
| `P1-GATE-05` | Keyword route validation | `npm run test -- --run src/components/wiki/KeywordText.test.tsx` | keyword links can navigate to unchecked or empty routes |
| `P1-GATE-06` | Read-only media inspection | `python -m pytest tests/test_huiji_wiki_e2e_script.py -q` | inspection script cannot be reused safely |
| `P1-GATE-07` | Full Wiki regression | backend Wiki pytest + frontend Wiki vitest + `npm run build` + real read-only E2E | implementation is incomplete |
| `P1-GATE-08` | DB migration plan only | this document records source, target, dump/restore, rollback, and non-execution boundary | MySQL migration risk is not reviewable |

## 3. Execution Steps

### Step P1-0: P0 self-check

Status: completed before P1 implementation.

Required evidence:

- Backend Wiki pytest passed.
- Frontend Wiki vitest passed.
- Vite build passed.
- Read-only Wiki E2E passed.
- Browser `/wiki` check showed all four zones and real HTTP media.

### Step P1-1: API search/category enhancement

Status: completed.

Implementation:

- `src/huiji_wiki/repository.py`
- `tests/test_huiji_wiki_repository.py`

Verification:

- `python -m pytest tests/test_huiji_wiki_repository.py -q`

Acceptance:

- `wiki_categories` metadata is returned.
- alias search is supported.
- title matches rank before alias fallback.
- cursor pagination uses the extra fetched row.

### Step P1-DB: MySQL migration plan

Status: plan only. No database migration is executed in this P1 pass.

Current finding:

- Wiki DB currently lives in Docker container `edurag-mysql`.
- Database name: `reverse1999_wiki`.
- The Wiki MySQL data is small; the large storage is MinIO, not MySQL.

Recommended future migration:

1. Add a project-owned MySQL service to this project's Docker compose.
2. Bind it to a temporary host port such as `3307:3306` to avoid `edurag-mysql`.
3. Dump only `reverse1999_wiki` from `edurag-mysql`.
4. Restore the dump into the project-owned MySQL.
5. Point `.env` to the new port and credentials.
6. Run all Wiki hard gates and real read-only E2E.
7. Keep `edurag-mysql` as backup until the new stack is verified.

Hard migration rules:

- Do not copy MySQL volume files directly.
- Do not delete or stop the old container during verification.
- Do not migrate MinIO in this database step.
- Do not repoint RAG until the RAG thread confirms its own database boundary.
- If any Wiki gate fails after repointing, roll `.env` back to the old MySQL connection.

### Step P1-2: Add `/api/wiki/pages/by-route`

Implementation targets:

- `src/huiji_wiki/repository.py`
- `backend/wiki.py`
- `backend/wiki_schemas.py` only if response schema changes.
- `tests/test_huiji_wiki_api.py`
- `tests/test_huiji_wiki_repository.py`
- `frontend/react-app/src/api/wiki.ts`
- `frontend/react-app/src/api/wiki.test.ts`

Acceptance:

- `GET /api/wiki/pages/by-route?route=/wiki/char/3074` returns the same detail payload as `GET /api/wiki/pages/char:3074`.
- Unknown routes return HTTP 404.
- The static route must be declared before `/api/wiki/pages/{page_id:path}`.
- No local media path is returned.

### Step P1-3: Category metadata and mobile layout

Implementation targets:

- `frontend/react-app/src/components/wiki/WikiShell.tsx`
- `frontend/react-app/src/components/wiki/CategoryRail.tsx`
- `frontend/react-app/src/components/wiki/wikiLayout.ts`
- related tests

Acceptance:

- Active category metadata is available on the layout through stable `data-*` attributes or props.
- CategoryRail exposes `templateGroup`, `animationProfile`, and `themeToken` as future animation hooks.
- On narrow screens the layout switches to an index/reader-first arrangement; PageInfo and CategoryRail do not force desktop columns.
- The desktop ratio remains `right info < category rail = page index < reader`.

### Step P1-4: Keyword route validation

Implementation targets:

- `frontend/react-app/src/components/wiki/KeywordText.tsx`
- `frontend/react-app/src/components/wiki/KeywordText.test.tsx`

Acceptance:

- Existing direct links still work by default.
- When a `validateRoute` callback is provided, click is prevented until validation finishes.
- Valid routes navigate to the returned route.
- Missing routes degrade to `/wiki?q=<keyword>` search fallback.
- Empty routes still render as plain text and do not create empty anchors.

### Step P1-5: Repeatable media inspection

Implementation targets:

- `scripts/verify_huiji_wiki_e2e.py`
- `tests/test_huiji_wiki_e2e_script.py`
- documentation in final report

Acceptance:

- The script can print or write a media coverage summary without modifying MySQL, MinIO, Milvus, or processed artifacts.
- The script can be run repeatedly against `data/processed/huiji/dev/media_assets.jsonl`.
- Local path leak count remains `0`.

## 4. Final Verification

Run from `D:/PycharmProjects/nlp/LangChain/1999Search`:

```powershell
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_e2e_script.py -q
```

Run from `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app`:

```powershell
npm run test -- --run src/api/wiki.test.ts src/App.wiki.test.tsx src/components/TopNav.wiki.test.tsx src/components/Sidebar.wiki.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/wiki
npm run build
```

Run with the Wiki API server available:

```powershell
python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --check-media --media-sample-limit 200 --media-assets data/processed/huiji/dev/media_assets.jsonl
```

## 5. Completion Checklist

- [x] `P1-GATE-00`: RAG files and processed artifacts were not touched by Wiki work. Existing RAG-thread changes remain visible in git status and were not edited here.
- [x] `P1-GATE-01`: API-P1-01 verified.
- [x] `P1-GATE-02`: `/api/wiki/pages/by-route` verified by tests and real API call.
- [x] `P1-GATE-03`: frontend API client verified.
- [x] `P1-GATE-04`: category metadata and mobile layout verified.
- [x] `P1-GATE-05`: keyword route validation verified.
- [x] `P1-GATE-06`: repeatable media inspection verified.
- [x] `P1-GATE-07`: full Wiki regression verified.
- [x] `P1-GATE-08`: MySQL migration remains plan-only and reviewable.
