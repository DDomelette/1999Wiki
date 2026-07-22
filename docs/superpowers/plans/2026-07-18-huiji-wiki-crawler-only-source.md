# Huiji Wiki Crawler-Only Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将 Wiki 文本、结构化档案和全部角色媒体收束到灰机爬虫数据，移除运行时 Obsidian 补充层、Wiki 私有 MinIO 前缀和前端非爬虫媒体回退。

**Architecture:** `data/huiji/res1999/data_pages.jsonl` 与 `resources_manifest.jsonl` 提供原始结构和显式资源关系，`data/processed/huiji/<active>/parent_blocks.jsonl`、`child_blocks.jsonl`、`media_assets.jsonl` 提供既有处理产物。新增爬虫投影器将二者合并为一个可重复生成的 Wiki 导入载荷；MySQL 只保存该载荷，MinIO 只保存 RAG/Wiki 共用的 `reverse1999/<asset_type>/...` 对象。前端仅消费 `/api/wiki` DTO 与 HTTP 媒体 URL。

**Tech Stack:** Python 3.11、pytest、PyMySQL、MinIO Python SDK、FastAPI、React 18、TypeScript、Vitest、Playwright。

## Global Constraints

- 唯一原始数据源是 `data/huiji/res1999/**`；唯一处理数据源是配置指定的 `data/processed/huiji/<active>/**`。
- 禁止读取 `D:/Obsidian_depot/**`、`data/raw` 中的 Obsidian 镜像或任何 `obsidian_character` supplement。
- 禁止创建或保留 `reverse1999/wiki-supplement/**` 等 Wiki 私有 MinIO 对象键。
- MinIO 媒体对象必须使用 RAG/Wiki 共用前缀；关系以爬虫文档和资源 manifest 为准，不扫描对象池反推。
- 本次不写 Milvus、不重建向量、不修改 RAG `_state`。
- 所有删除均在备份、引用迁移和零引用审计通过后执行。
- 工作区包含其他任务的未提交改动；只修改本计划列出的 Wiki 文件，不执行 Git 提交或回滚。

---

### Task 1: Crawler authority and projection contract

**Files:**
- Create: `src/huiji_wiki/crawler_projection.py`
- Modify: `src/huiji_wiki/importer.py`
- Modify: `scripts/import_huiji_wiki_pages.py`
- Test: `tests/test_huiji_wiki_crawler_projection.py`
- Test: `tests/test_huiji_wiki_importer.py`

**Interfaces:**
- Consumes: `data_pages.jsonl`, `resources_manifest.jsonl`, processed `WikiImportPayload` rows.
- Produces: `build_crawler_character_projection(raw_root: Path) -> CrawlerCharacterProjection` and `build_wiki_import_payload(..., raw_root: Path | None = None)`.

- [x] Write failing tests proving `Data:Char/{id}.json` is the authoritative source for profile, `passive_skill`, `skill_ex_level`, `character_data` and `skin`.
- [x] Write failing tests proving resource selection follows explicit fields: `largeIcon -> Headicon_large-*`, `live2d/verticalDrawing/drawing -> L2d_static-* or Portrait-*`, `live2dbg -> Skin_bg-*`, collection `icon -> Belonging-*`.
- [x] Write a failing test proving Udimo resolves through crawler `Data:Item` identity and `icon -> Item-*`, with no keyword-only match when an explicit record exists.
- [x] Write failing tests rejecting source paths, source kinds and object keys containing `Obsidian`, `obsidian_character` or `wiki-supplement`.
- [x] Run the focused tests and verify they fail because the projection API does not exist.
- [x] Implement the projection module with deterministic WebP-over-PNG selection, SHA-1 verification and shared object-key generation.
- [x] Merge projected character blocks and media into the canonical import payload, assigning semantic roles `roster_avatar`, `stage_live2d`, `stage_portrait`, `skin_background`, `collection_item` and `udimo`.
- [x] Add `--raw-root` to the import script, defaulting to `cfg.huiji.raw_root`, and require it for `--include-character`.
- [x] Run focused tests and verify they pass.

### Task 2: Remove runtime supplement dependency

**Files:**
- Modify: `src/huiji_wiki/repository.py`
- Modify: `backend/wiki_schemas.py`
- Modify: `scripts/verify_huiji_wiki_e2e.py`
- Test: `tests/test_huiji_wiki_repository.py`
- Test: `tests/test_huiji_wiki_api.py`

**Interfaces:**
- Consumes: canonical `wiki_pages` and `wiki_media_links` only.
- Produces: unchanged `/api/wiki/pages/{page_id}` envelope without supplement merge.

- [x] Write failing tests proving page detail never queries `wiki_page_supplements` and returns canonical crawler content/media unchanged.
- [x] Write a failing test proving roster thumbnails come only from canonical `media_role='roster_avatar'`, followed by image-compatible canonical fallbacks.
- [x] Write failing health/E2E tests proving Wiki readiness is independent of supplement tables.
- [x] Remove `raw_character_enrichment` imports, supplement merge/query code and supplement health gating from the repository.
- [x] Keep deprecated response fields optional only if removing them would break existing API clients; they must not affect readiness.
- [x] Update the E2E verifier to assert crawler provenance and reject private object prefixes.
- [x] Run repository/API/E2E unit tests and verify they pass.

### Task 3: Safe MySQL and shared MinIO migration

**Files:**
- Create: `scripts/migrate_wiki_to_crawler_source.py`
- Test: `tests/test_migrate_wiki_to_crawler_source.py`
- Test: `tests/test_huiji_wiki_crawler_media_migration.py`
- Evidence: `eval/wiki-crawler-only-migration/**`

**Interfaces:**
- Consumes: projection from Task 1, existing Wiki MySQL, crawler files, configured shared MinIO bucket.
- Produces: UTF-8 SQL backup, dry-run report, apply receipt and zero-private-reference audit.

- [x] Write failing tests for dry-run default, UTF-8 SQL backup encoding, SHA-1 verification, shared-key upload-before-reference, transaction rollback and delete-after-zero-reference ordering.
- [x] Implement a migration script whose default is read-only and whose `--apply` path backs up `wiki_pages`, `wiki_media_links`, `wiki_page_supplements` and `wiki_supplement_snapshots` before mutation.
- [x] Upload missing crawler files to shared keys without overwriting mismatched objects.
- [x] Import the full crawler Wiki payload in one MySQL transaction and verify page/media counts plus source provenance.
- [x] Delete `obsidian_character` supplement rows only after canonical pages contain the required blocks and roles.
- [x] Verify no MySQL/API row references `reverse1999/wiki-supplement/**`, then delete that MinIO prefix.
- [x] Emit a receipt containing counts, digests and deleted private-object keys; never include credentials.
- [x] Run migration unit tests, then run dry-run against the configured Docker MySQL/MinIO.
- [x] Apply only if dry-run has zero blockers, then rerun the audit.

### Task 4: Frontend canonical media consumption

**Files:**
- Modify: `frontend/react-app/src/components/wiki/wikiViewModel.ts`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.tsx`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterSelectionPage.tsx`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterDetailPage.tsx`
- Delete: `frontend/react-app/src/media/characterStandees.ts`
- Test: relevant `*.test.tsx` and `wikiViewModel.test.ts`

**Interfaces:**
- Consumes: `/api/wiki` `mediaLinks` semantic roles from Task 1.
- Produces: roster cards use only `roster_avatar`; stage uses only `stage_live2d`/`stage_portrait`; skin changes update stage and background together.

- [x] Write failing tests proving `roster_avatar` is never eligible for the main stage.
- [x] Write failing tests proving roster cards prefer `roster_avatar` and stage skin tabs preserve crawler skin order.
- [x] Write failing tests proving selection/detail pages do not import local character standees or private supplement URLs.
- [x] Update view models and both production/preview page variants to consume semantic API roles.
- [x] Remove active hard-coded character standee fallback imports.
- [x] Run focused Vitest suites and the production build.

### Task 5: Remove non-crawler public media and legacy active entry points

**Files:**
- Delete: `scripts/enrich_wiki_from_raw.py`
- Delete: `scripts/import_wiki_roster_avatars.py`
- Modify: `frontend/react-app/src/media/assets.ts`
- Modify: `frontend/react-app/src/styles/global.css`
- Modify: `frontend/react-app/src/styles/archival.css`
- Delete after audit: non-crawler files under `frontend/react-app/public/images/**`
- Test: `tests/test_huiji_wiki_crawler_provenance.py`
- Test: `frontend/react-app/src/media/assets.test.ts`

**Interfaces:**
- Consumes: crawler manifest SHA-1 allowlist and source scan results.
- Produces: zero active Obsidian/Wiki-private references and no non-crawler runtime image dependencies.

- [x] Write failing provenance tests scanning active Python/TypeScript/config code for Obsidian Wiki source roots and `wiki-supplement` object keys.
- [x] Write a failing file audit comparing every retained `public/images` binary SHA-1 with the crawler resource manifest.
- [x] Disable/remove the Obsidian supplement import entry points and update diagnostics to identify them as unsupported legacy commands if retained for recovery documentation.
- [x] Replace non-crawler decorative image dependencies with crawler-backed or CSS-native equivalents.
- [x] Delete public image binaries absent from the crawler manifest after generating a deletion receipt.
- [x] Run provenance and asset tests; verify zero active-source violations.

### Task 6: End-to-end acceptance

**Files:**
- Modify: `scripts/verify_wiki_media.py`
- Evidence: `eval/wiki-crawler-only-migration/final/**`

**Interfaces:**
- Consumes: Docker MySQL, shared MinIO, FastAPI `:8000`, Vite Wiki UI.
- Produces: machine-readable and visual acceptance evidence.

- [x] Run all targeted backend Wiki tests and confirm no Obsidian supplement test is part of the active gate.
- [x] Run frontend Vitest and `npm run build`.
- [x] Start or reuse FastAPI `:8000` and Vite, then verify category list, character selection, character detail and skin switching with real API data.
- [x] Sample at least five characters including multiple skins; verify roster avatar, stage media, background, collection and Udimo roles.
- [x] Query MySQL and MinIO for `obsidian_character`, `wiki-supplement` and deleted local-image URLs; all active references must be zero.
- [x] Capture desktop/mobile screenshots and API/MinIO audit JSON.
- [x] Record that Milvus collection and RAG processed artifacts were not modified.

## Hard Acceptance Gates

- [x] Active source scan contains zero Obsidian Wiki inputs.
- [x] MySQL canonical pages expose crawler profile, inheritance, portray, collection, culture and skin data where present upstream.
- [x] Roster avatar and main-stage media are distinct semantic roles for every sampled character.
- [x] Shared MinIO objects have crawler-manifest provenance; private Wiki supplement prefix has zero references and zero objects.
- [x] Frontend active code has no hard-coded character media fallback and retained public binaries all match crawler manifest SHA-1 values.
- [x] Backend tests, frontend tests, build and real-data browser smoke all pass.
- [x] Milvus/RAG state is unchanged.

## Execution Evidence (2026-07-19)

- Wiki MySQL: `7456` pages, `132` character pages, `17527` media links; crawler-only migration backup: `.local/wiki-backups/wiki-crawler-migration-20260719-162506.sql`.
- Shared MinIO: `1763` crawler media objects present, `0` missing, `0` conflicts, `0` legacy private objects; see `eval/wiki-crawler-only-migration/final/minio-preflight/preflight.json`.
- Five-character role audit: all sampled media URLs reachable, roster/stage roles disjoint, collection IDs and URLs unique; see `eval/wiki-crawler-only-migration/final/five-character-audit.json`.
- API E2E: crawler contract, page list/search, HTTP media and local-path leak checks passed; see `eval/wiki-crawler-only-migration/final/api-e2e.json`.
- Content audit: `7456` pages, `0` issues; see `eval/wiki-crawler-only-migration/final/wiki-content-v2.json`.
- Frontend public media: `400/400` files match the crawler manifest; see `eval/wiki-crawler-only-migration/final/frontend-images.json`.
- Browser evidence: `eval/wiki-crawler-only-migration/browser/wiki-selection-desktop.png`, `wiki-detail-desktop.png`, `wiki-selection-mobile.png`, `wiki-detail-mobile.png`.
- Automated gates: `81` targeted backend tests and `223` frontend tests passed; production build passed with only the existing chunk-size warning.
- RAG boundary: read-only audit confirms `text_child_bge_m3_v3 = 16010` and `child_blocks.jsonl = 16010`; see `eval/wiki-crawler-only-migration/final/rag-unchanged.json`.
