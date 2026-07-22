# React Bits Navigation, Media, and Wiki Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the current workspace. Do not generate subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the split navigation and legacy themes, add the approved React Bits interactions to chat and Wiki media, and rebuild Wiki presentation around pinned structured content without changing RAG, Milvus, active artifacts, or shared MinIO.

**Architecture:** Keep animation algorithms in a local React Bits adaptation layer and expose business-specific wrappers for navigation, voice, images, text, and tilted media. Resolve one immutable Wiki artifact snapshot into structured `content.blocks`, persist only Wiki-owned MySQL rows and safe snapshot metadata, and consume only public HTTP media URLs in React. Real acceptance pins either one active activation tuple or one hash-pinned legacy snapshot receipt for the entire run.

**Tech Stack:** React 18.3, TypeScript 5.5, Vite 5.4, Framer Motion 11.3, GSAP 3.15.0, OGL 1.0.11, Lucide React 1.24.0, Zustand 4.5, Vitest 2, Playwright 1.61.1, FastAPI, Pydantic, PyMySQL, MySQL 8, MinIO HTTP URLs.

## Global Constraints

- Source spec: `docs/superpowers/specs/2026-07-11-reactbits-navigation-wiki-content-design.md`.
- React Bits source baseline: `DavidHDev/react-bits@271b49c3ba1db60686e53c8c9a28b7583d5477d5`.
- Work directly in the current dirty workspace. Do not stage, commit, reset, checkout, clean, or create worktrees.
- Do not generate subagents. Execute inline with a checkpoint after every task.
- Do not modify RAG query planning, retrieval, reranking, vectorization, active pointer, activation transaction, Milvus, RAG artifacts, or MinIO objects.
- Do not claim or execute the RAG/EVB C20 operation plan. Wiki media repair stops at a create-new request report.
- Do not use ordinary PUT, HEAD-then-PUT, overwrite retry, delete, bucket setup, policy mutation, or object-key inference.
- Browser-visible media uses only safe HTTP(S) `url`; never expose `object_key`, hashes, `source_url`, `local_relpath`, credentials, absolute paths, or full quality flags.
- When `active_build.v1.json` exists, pin one valid activation tuple. When it is absent, pin one create-new legacy snapshot receipt from configured `dev`; never mix the two modes in one import or acceptance run.
- Dynamic counts come from the current snapshot. Character names, page IDs, media IDs, historical counts, 3038, 7456, and 15758 are observations, not implementation constants.
- Frontend development remains `127.0.0.1:5173`; API routes remain on FastAPI `127.0.0.1:8000`; media endpoint/bucket paths are never hardcoded in React.
- Themes are exactly `storm-dark`, `manuscript-gold`, and `cold-archive`; unknown persisted values fall back to `storm-dark`.
- Main-route Card Nav primary action is `WIKI`; Wiki-route primary action is `首页`.
- Circular Gallery parameters are exactly `bend={0}` and `borderRadius={0.1}`.
- Tilted media desktop parameters are exactly `scaleOnHover={1.35}` and `rotateAmplitude={16}`, with overlay and tooltip disabled.
- `prefers-reduced-motion`, touch devices, WebGL failure, texture failure, and zero-size canvas must retain complete readable and operable content.
- A task is complete only after its named tests, neighboring regression tests, and checkpoint inspection pass. Do not weaken assertions to obtain green output.

### Execution Shell Preamble

Run this preamble at the start of every task. Every `npm` or `npx` command runs from `$Frontend`; every Python, Docker, API, and artifact command runs from `$Project`. A task must not depend on the previous task's current directory.

```powershell
$Project = "D:\PycharmProjects\nlp\LangChain\1999Search"
$Frontend = Join-Path $Project "frontend\react-app"
$Python = "D:\Anaconda32024\envs\LangChain\python.exe"
Set-Location $Project
```

---

## 1. File Responsibility Map

### Shared animation layer

- Create `frontend/react-app/src/components/animations/reactbits/AnimatedList.tsx` and `.css`: generic focus-scoped animated list.
- Create `frontend/react-app/src/components/animations/reactbits/AnimatedContent.tsx`: one-shot local GSAP content entrance.
- Create `frontend/react-app/src/components/animations/reactbits/ScrollReveal.tsx` and `.css`: block-local GSAP/ScrollTrigger text reveal.
- Create `frontend/react-app/src/components/animations/reactbits/CardNav.tsx` and `.css`: accessible expanding card navigation shell.
- Create `frontend/react-app/src/components/animations/reactbits/CircularGallery.tsx` and `.css`: OGL engine with explicit lifecycle.
- Create `frontend/react-app/src/components/animations/reactbits/README.md`: source commit, upstream URLs, license note, and local differences.

### Navigation and themes

- Create `frontend/react-app/src/components/navigation/RouteAwareCardNav.tsx`.
- Create `frontend/react-app/src/components/navigation/navigationConfig.ts`.
- Modify `frontend/react-app/src/App.tsx`, `components/wiki/WikiShell.tsx`, `store/uiStore.ts`, `store/themeStore.ts`, `types/index.ts`, `styles/themes.css`, and `styles/global.css`.
- Delete only after replacement tests pass: `components/Sidebar.tsx`, `components/TopNav.tsx`, `components/wiki/CategoryRail.tsx`, and their obsolete tests.

### Chat media

- Create `frontend/react-app/src/components/chat/AnimatedVoiceList.tsx`.
- Create `frontend/react-app/src/components/chat/CircularMediaGallery.tsx`.
- Modify `VoicePanel.tsx`, `ImagePanel.tsx`, `MessageAssets.tsx`, `api/media.ts`, and `types/index.ts`.

### Wiki build/API

- Create `src/huiji_wiki/snapshot.py`: read-only active/legacy snapshot resolver and receipt writer.
- Create `src/huiji_wiki/content_blocks.py`: deterministic structured block parser.
- Create `src/huiji_wiki/media_audit.py`: URL-only media audit and repair-request generator.
- Modify `src/huiji_wiki/importer.py`, `models.py`, `repository.py`, `scripts/import_huiji_wiki_pages.py`, `backend/wiki.py`, and `backend/wiki_schemas.py`.

### Wiki React presentation

- Create `frontend/react-app/src/components/wiki/StructuredContentRenderer.tsx` and `.css`.
- Create `frontend/react-app/src/components/wiki/WikiScrollRevealText.tsx`.
- Modify `types/wiki.ts`, `api/wiki.ts`, `WikiShell.tsx`, `WikiReader.tsx`, `PageIndex.tsx`, `PageInfo.tsx`, `wikiLayout.ts`, all Wiki templates, and `ui/TiltedImageCard.tsx`.

### Verification

- Create focused unit tests adjacent to new frontend components.
- Create `tests/test_huiji_wiki_snapshot.py`, `tests/test_huiji_wiki_content_blocks.py`, and `tests/test_huiji_wiki_media_audit.py`.
- Create `frontend/react-app/playwright.config.ts` and `frontend/react-app/e2e/wiki-reactbits.spec.ts`.
- Extend `scripts/verify_huiji_wiki_e2e.py` to emit one final JSON report under `eval/wiki-reactbits-p0/`.

## 2. P0 Coverage Matrix

| Task | Spec IDs | Hard result |
|---|---|---|
| 0 | `COORD-P0-01..07` | Immutable baseline proves one source snapshot and zero RAG/MinIO mutation authority |
| 1 | `MOTION-P0-01..06` | Local animation primitives, scoped cleanup, responsive/reduced-motion contracts |
| 2 | `THEME-P0-01..05` | Three new themes and persisted-value migration |
| 3 | `NAV-P0-01..10` | One route-aware Card Nav; Sidebar, TopNav, CategoryRail removed |
| 4 | `VOICE-UI-P0-01..11` | Animated voice list preserves playback/pagination and exact language/cursor rules |
| 5 | `IMAGE-UI-P0-01..10` | Lazy OGL gallery plus functional DOM fallback |
| 6 | `WIKI-CONTENT-P0-02..07`, `P0-11..13` | Pinned snapshot and deterministic content blocks |
| 7 | `WIKI-CONTENT-P0-01`, `P0-08..10`, `P0-14` | Idempotent MySQL import, safe API, traceable health |
| 8 | `WIKI-TEXT-P0-01..07` | Structured renderer and block-scoped reveal |
| 9 | `WIKI-LAYOUT-P0-01..08`, `TILT-P0-01..07` | Three-pane responsive Wiki, image/name index, transparent tilted media |
| 10 | `MEDIA-P0-01..11` | Read-only media audit and create-new repair request; zero storage writes |
| 11 | `QUALITY-P0-01..08` | Accessibility, lazy loading, responsive and canvas/browser evidence |
| 12 | all P0 IDs | Full regression, real MySQL/MinIO/API/React proof, and final self-check |

### Exact P0 Traceability

The following list is the machine-checkable ownership map. Every P0 definition in the source spec appears exactly once here; EVB/RAG cross-reference IDs are external dependencies and are not claimed by this plan.

- Task 0: `COORD-P0-01`, `COORD-P0-02`, `COORD-P0-03`, `COORD-P0-04`, `COORD-P0-05`, `COORD-P0-06`, `COORD-P0-07`.
- Task 1: `MOTION-P0-01`, `MOTION-P0-02`, `MOTION-P0-03`, `MOTION-P0-04`, `MOTION-P0-05`, `MOTION-P0-06`.
- Task 2: `THEME-P0-01`, `THEME-P0-02`, `THEME-P0-03`, `THEME-P0-04`, `THEME-P0-05`.
- Task 3: `NAV-P0-01`, `NAV-P0-02`, `NAV-P0-03`, `NAV-P0-04`, `NAV-P0-05`, `NAV-P0-06`, `NAV-P0-07`, `NAV-P0-08`, `NAV-P0-09`, `NAV-P0-10`.
- Task 4: `VOICE-UI-P0-01`, `VOICE-UI-P0-02`, `VOICE-UI-P0-03`, `VOICE-UI-P0-04`, `VOICE-UI-P0-05`, `VOICE-UI-P0-06`, `VOICE-UI-P0-07`, `VOICE-UI-P0-08`, `VOICE-UI-P0-09`, `VOICE-UI-P0-10`, `VOICE-UI-P0-11`.
- Task 5: `IMAGE-UI-P0-01`, `IMAGE-UI-P0-02`, `IMAGE-UI-P0-03`, `IMAGE-UI-P0-04`, `IMAGE-UI-P0-05`, `IMAGE-UI-P0-06`, `IMAGE-UI-P0-07`, `IMAGE-UI-P0-08`, `IMAGE-UI-P0-09`, `IMAGE-UI-P0-10`.
- Task 6: `WIKI-CONTENT-P0-02`, `WIKI-CONTENT-P0-03`, `WIKI-CONTENT-P0-04`, `WIKI-CONTENT-P0-05`, `WIKI-CONTENT-P0-06`, `WIKI-CONTENT-P0-07`, `WIKI-CONTENT-P0-11`, `WIKI-CONTENT-P0-12`, `WIKI-CONTENT-P0-13`.
- Task 7: `WIKI-CONTENT-P0-01`, `WIKI-CONTENT-P0-08`, `WIKI-CONTENT-P0-09`, `WIKI-CONTENT-P0-10`, `WIKI-CONTENT-P0-14`.
- Task 8: `WIKI-TEXT-P0-01`, `WIKI-TEXT-P0-02`, `WIKI-TEXT-P0-03`, `WIKI-TEXT-P0-04`, `WIKI-TEXT-P0-05`, `WIKI-TEXT-P0-06`, `WIKI-TEXT-P0-07`.
- Task 9: `WIKI-LAYOUT-P0-01`, `WIKI-LAYOUT-P0-02`, `WIKI-LAYOUT-P0-03`, `WIKI-LAYOUT-P0-04`, `WIKI-LAYOUT-P0-05`, `WIKI-LAYOUT-P0-06`, `WIKI-LAYOUT-P0-07`, `WIKI-LAYOUT-P0-08`, `TILT-P0-01`, `TILT-P0-02`, `TILT-P0-03`, `TILT-P0-04`, `TILT-P0-05`, `TILT-P0-06`, `TILT-P0-07`.
- Task 10: `MEDIA-P0-01`, `MEDIA-P0-02`, `MEDIA-P0-03`, `MEDIA-P0-04`, `MEDIA-P0-05`, `MEDIA-P0-06`, `MEDIA-P0-07`, `MEDIA-P0-08`, `MEDIA-P0-09`, `MEDIA-P0-10`, `MEDIA-P0-11`.
- Task 11: `QUALITY-P0-01`, `QUALITY-P0-02`, `QUALITY-P0-03`, `QUALITY-P0-04`, `QUALITY-P0-05`, `QUALITY-P0-06`, `QUALITY-P0-07`, `QUALITY-P0-08`.
- Task 12: re-runs and proves all 104 P0 definitions above; it owns no additional design requirement.

---

### Task 0: Freeze the Execution Baseline and Mutation Boundary

**Files:**
- Read only: `data/processed/huiji/active_build.v1.json`
- Read only: `data/processed/huiji/dev/build_manifest.json`
- Read only: `config/settings.yaml`
- Read only: `docs/superpowers/specs/2026-07-11-eventname-voice-binding-recovery-design.md`
- Read only: `docs/superpowers/plans/2026-07-12-minio-blue-green-same-port-migration.md`
- Create during execution: `eval/wiki-reactbits-p0/baseline.v1.json`

**Interfaces:**
- Consumes: current filesystem, Docker status, optional active pointer.
- Produces: one baseline with `source_mode`, snapshot paths/hashes, MinIO image/ports, Milvus collection inventory, and forbidden mutation list.

- [ ] **Step 1: Capture current source mode without mutation**

```powershell
$Project = "D:\PycharmProjects\nlp\LangChain\1999Search"
$Python = "D:\Anaconda32024\envs\LangChain\python.exe"
Set-Location $Project
$Pointer = Join-Path $Project "data\processed\huiji\active_build.v1.json"
$SourceMode = if (Test-Path $Pointer) { "active" } else { "legacy" }
if ($SourceMode -eq "legacy" -and -not (Test-Path "data/processed/huiji/dev/build_manifest.json")) { throw "No valid Wiki artifact source" }
Get-FileHash data/processed/huiji/dev/build_manifest.json -Algorithm SHA256
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
```

Expected: source mode is explicit; MinIO is healthy on host `9002/9003`; no service or file changes.

- [ ] **Step 2: Prove no unfinished EVB transaction is active**

```powershell
$Transactions = "data/processed/huiji/activation/transactions"
if (Test-Path $Transactions) {
  Get-ChildItem $Transactions -Recurse -Filter journal.v1.json | ForEach-Object {
    $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
    if ($j.state -notin @("committed", "rolled_back", "aborted", "conflict")) { throw "Unfinished EVB transaction: $($_.FullName)" }
  }
}
```

Expected: no `preparing`, `prepared`, `committing`, `rollback_preparing`, or `rolling_back` journal.

- [ ] **Step 3: Capture read-only Milvus and MinIO evidence**

```powershell
& $Python scripts/minio_blue_green_evidence.py media-samples --inventory eval/evb_real/minio_inventory/e9b97c6a24c4415aa6b071d79aec91b4/inventory.v1.json --base-url http://127.0.0.1:9002/reverse1999-assets/ --asset-type voice --asset-type image --asset-type portrait --asset-type skill --output eval/wiki-reactbits-p0/media-baseline.v1.json
& $Python scripts/minio_blue_green_evidence.py milvus-inventory --endpoint http://127.0.0.1:19530 --database default --output eval/wiki-reactbits-p0/milvus-before.v1.json
```

Expected: commands are read-only and produce hash-verified evidence. If the inventory path has moved, stop and resolve the current RAG-owned evidence path; do not scan or repair MinIO.

- [ ] **Step 4: Write the baseline receipt**

Use canonical JSON containing only relative paths, hashes, versions, counts derived from evidence, and `forbidden_mutations=["rag_artifacts","active_pointer","milvus","minio"]`. Write with create-new semantics; an existing receipt requires a new evidence directory.

- [ ] **Step 5: Checkpoint**

Record the baseline SHA-256 in the execution log. Do not continue if source mode is ambiguous or any external mutation is active.

---

### Task 1: Install Dependencies and Build the Local React Bits Adaptation Layer

**Files:**
- Modify: `frontend/react-app/package.json`
- Modify: `frontend/react-app/package-lock.json`
- Create: `frontend/react-app/src/components/animations/reactbits/AnimatedList.tsx`
- Create: `frontend/react-app/src/components/animations/reactbits/AnimatedList.css`
- Create: `frontend/react-app/src/components/animations/reactbits/AnimatedContent.tsx`
- Create: `frontend/react-app/src/components/animations/reactbits/ScrollReveal.tsx`
- Create: `frontend/react-app/src/components/animations/reactbits/ScrollReveal.css`
- Create: `frontend/react-app/src/components/animations/reactbits/README.md`
- Test: `frontend/react-app/src/components/animations/reactbits/ReactBitsAdapters.test.tsx`

**Interfaces:**

```ts
export interface AnimatedListProps<T> {
  items: readonly T[]
  itemKey: (item: T) => string
  renderItem: (item: T, index: number) => React.ReactNode
  selectedKey?: string | null
  onItemSelect?: (item: T, index: number) => void
  displayScrollbar?: boolean
  ariaLabel: string
}

export interface AnimatedContentProps extends React.HTMLAttributes<HTMLDivElement> {
  direction?: 'vertical' | 'horizontal'
  distance?: number
  scrollContainer?: Element | null
  once?: boolean
}

export interface ScrollRevealProps {
  text: string
  scrollContainer: HTMLElement | null
  baseRotation: 0
  enabled: boolean
}
```

- [ ] **Step 1: Add RED adapter tests**

Test generic ReactNode rows, focus-scoped ArrowUp/ArrowDown, no global Tab interception, hidden-scrollbar class, reduced-motion immediate rendering, one component unmount not killing another ScrollTrigger, and responsive styles without fixed demo width.

```tsx
it('does not intercept document arrows while the list is unfocused', () => {
  render(<AnimatedList items={['a']} itemKey={String} renderItem={String} ariaLabel="voices" />)
  const event = new KeyboardEvent('keydown', { key: 'ArrowDown', cancelable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(false)
})
```

- [ ] **Step 2: Run RED**

```powershell
Set-Location frontend/react-app
npm run test -- --run src/components/animations/reactbits/ReactBitsAdapters.test.tsx
```

Expected: FAIL because adapters do not exist.

- [ ] **Step 3: Install exact dependencies**

```powershell
npm install --save-exact gsap@3.15.0 ogl@1.0.11 lucide-react@1.24.0
npm install --save-dev --save-exact @playwright/test@1.61.1
```

- [ ] **Step 4: Implement minimal adapters**

Port the TS/CSS algorithms from the pinned React Bits commit. Import motion APIs from `framer-motion`, bind keyboard handlers to the list element, hold each GSAP timeline/trigger in a local ref/context, and use CSS variables instead of source-demo colors. `ScrollReveal` must create and kill only its own triggers.

- [ ] **Step 5: Document provenance and differences**

`README.md` must contain the six upstream URLs, pinned commit, dependency substitutions, scoped-keyboard change, scoped-cleanup change, reduced-motion behavior, and responsive-size change.

- [ ] **Step 6: Run GREEN and build**

```powershell
npm run test -- --run src/components/animations/reactbits/ReactBitsAdapters.test.tsx
npm run build
```

Expected: PASS; no `motion` or `react-icons` package is installed.

---

### Task 2: Replace the Theme Seeds and Migrate Persisted State

**Files:**
- Modify: `frontend/react-app/src/types/index.ts`
- Modify: `frontend/react-app/src/store/themeStore.ts`
- Modify: `frontend/react-app/src/store/themeStore.test.ts`
- Modify: `frontend/react-app/src/styles/themes.css`
- Modify: `frontend/react-app/src/components/ui/ThemeToggle.tsx`
- Test: `frontend/react-app/src/styles/themes.test.ts`

**Interfaces:**

```ts
export type Theme = 'storm-dark' | 'manuscript-gold' | 'cold-archive'
export const THEME_ORDER: readonly Theme[] = ['storm-dark', 'manuscript-gold', 'cold-archive']
export function migrateTheme(value: unknown): Theme
```

- [ ] **Step 1: Write RED migration and token tests**

Assert old-name mappings, unknown fallback, cycle order, `data-theme`, all required CSS variables, and icon accessible names.

```ts
expect(migrateTheme('dark-warm')).toBe('storm-dark')
expect(migrateTheme('parchment')).toBe('manuscript-gold')
expect(migrateTheme('mystic-purple')).toBe('cold-archive')
expect(migrateTheme('broken')).toBe('storm-dark')
```

- [ ] **Step 2: Run RED**

```powershell
npm run test -- --run src/store/themeStore.test.ts src/styles/themes.test.ts
```

- [ ] **Step 3: Implement versioned Zustand migration**

Use persist `version: 2` and a `migrate` callback. Apply the migrated theme during hydration. ThemeToggle renders Lucide `Moon`, `Sun`, and `SunMoon`, with `title` and `aria-label` containing the current theme name.

- [ ] **Step 4: Replace CSS tokens exactly**

Use the three seed tables from the spec. Preserve shared font and background variables; do not reintroduce purple-dominant tokens.

- [ ] **Step 5: Run GREEN and neighboring tests**

```powershell
npm run test -- --run src/store/themeStore.test.ts src/styles/themes.test.ts src/styles/global-background.test.ts
npm run build
```

---

### Task 3: Replace TopNav, Sidebar, and CategoryRail with Route-Aware Card Nav

**Files:**
- Create: `frontend/react-app/src/components/animations/reactbits/CardNav.tsx`
- Create: `frontend/react-app/src/components/animations/reactbits/CardNav.css`
- Create: `frontend/react-app/src/components/navigation/navigationConfig.ts`
- Create: `frontend/react-app/src/components/navigation/RouteAwareCardNav.tsx`
- Test: `frontend/react-app/src/components/navigation/RouteAwareCardNav.test.tsx`
- Modify: `frontend/react-app/src/App.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/store/uiStore.ts`
- Modify: `frontend/react-app/src/hooks/useTopNavTrigger.ts`
- Delete after GREEN: `frontend/react-app/src/components/Sidebar.tsx`
- Delete after GREEN: `frontend/react-app/src/components/TopNav.tsx`
- Delete after GREEN: `frontend/react-app/src/components/wiki/CategoryRail.tsx`
- Replace obsolete tests: `Sidebar.wiki.test.tsx`, `TopNav.wiki.test.tsx`, `CategoryRail.test.tsx`

**Interfaces:**

```ts
export type NavMode = 'main' | 'wiki'
export interface CardNavGroup { label: string; links: Array<{ label: string; href?: string; action?: () => void; disabled?: boolean }> }
export interface RouteAwareCardNavProps {
  mode: NavMode
  categories?: WikiCategoryItem[]
  activeCategory?: string
  onCategorySelect?: (key: string) => void
  availableAnchors?: ReadonlySet<'content' | 'media' | 'info'>
}
```

- [ ] **Step 1: Write RED route/menu tests**

Assert main primary `WIKI`, Wiki primary `首页`, exact three groups per route, theme button immediately before primary action, dynamic Wiki categories/counts, disabled missing anchors, Escape close, keyboard activation, mobile class, and main scroll-snap actions.

- [ ] **Step 2: Write RED removal tests**

Render `/` and `/wiki`; assert no Sidebar, no legacy TopNav, no CategoryRail hot zone, and no reserved category column.

- [ ] **Step 3: Run RED**

```powershell
npm run test -- --run src/components/navigation/RouteAwareCardNav.test.tsx src/App.wiki.test.tsx src/components/wiki/WikiShell.test.tsx
```

- [ ] **Step 4: Implement Card Nav and route config**

Port the pinned GSAP Card Nav, replacing `react-icons` with Lucide. Preserve the existing top-edge visibility trigger, but keep menu state local. Main groups are Page (`首页/资料/问答`), Data (current categories), Project (`官方网站/数据状态/Wiki`). Wiki groups are Browse (API categories), Current Page (`正文/媒体/资料`), Project (`首页/问答/官方网站`).

- [ ] **Step 5: Wire one category state source**

Render Wiki Card Nav inside `WikiShell` with its existing `activeCategory/setActiveCategory`. Do not add a second store. Main Card Nav stays inside `MainApp` and invokes existing scroll-snap targets.

- [ ] **Step 6: Remove legacy components and state**

Only after replacement tests pass, remove imports, files, `sidebarOpen/toggleSidebar/setSidebar`, and obsolete tests. Keep only top-nav visibility state needed by Card Nav.

- [ ] **Step 7: Run GREEN**

```powershell
npm run test -- --run src/components/navigation/RouteAwareCardNav.test.tsx src/App.wiki.test.tsx src/App.wheel.test.tsx src/hooks/useTopNavTrigger.test.tsx src/components/wiki/WikiShell.test.tsx
npm run build
```

---

### Task 4: Render Voice Pages through Animated List without Contract Drift

**Files:**
- Create: `frontend/react-app/src/components/chat/AnimatedVoiceList.tsx`
- Create: `frontend/react-app/src/components/chat/VoicePanel.test.tsx`
- Modify: `frontend/react-app/src/components/chat/VoicePanel.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageAssets.tsx`
- Modify: `frontend/react-app/src/api/media.ts`
- Modify: `frontend/react-app/src/api/media.test.ts`
- Modify: `frontend/react-app/src/types/index.ts`
- Modify: `frontend/react-app/src/components/chat/MessageBubble.test.tsx`

**Interfaces:**

```ts
export const VOICE_LANGUAGE_ORDER = ['zh', 'zh-hant', 'en', 'jp', 'kr'] as const
export type VoicePageFailure = 'retry' | 'reload-first-page' | null
export function canonicalVariantLanguage(item: MediaItem): string | null
```

- [ ] **Step 1: Add RED tests**

Cover explicit `zh-hant`, no filename/title/URL inference, 400 local retry, 409 stop audio and discard cursor, no automatic stale-cursor replay, only new page rows animate, scoped keyboard, hidden scrollbar, gradients, language override preservation, duplicate suppression, and forbidden-field fixture rejection.

- [ ] **Step 2: Run RED**

```powershell
npm run test -- --run src/api/media.test.ts src/components/chat/VoicePanel.test.tsx src/components/chat/MessageBubble.test.tsx
```

- [ ] **Step 3: Extract AnimatedVoiceList**

Pass `VoiceLineGroup[]` to generic `AnimatedList` using `voice_line_id` keys. Keep playback coordinator, merge logic, cursor request controller, and error state in `VoicePanel`; animation must not own business state.

- [ ] **Step 4: Implement exact language and cursor behavior**

`canonicalVariantLanguage` returns normalized explicit `item.language` or null. Null variants do not produce playable language controls. HTTP 409 aborts requests, calls `playback.stop()`, clears `nextCursor`, and shows reload-first-page. HTTP 400 preserves rows and shows retry without recursive automatic requests.

- [ ] **Step 5: Run GREEN and RAG compatibility tests**

```powershell
npm run test -- --run src/api/media.test.ts src/components/chat/VoicePanel.test.tsx src/components/chat/MessageBubble.test.tsx src/api/sse.test.ts src/store/chatStore.test.ts
& $Python -m pytest tests/test_voice_pagination.py tests/test_sse.py -q
npm run build
```

---

### Task 5: Replace the Chat Image Strip with Lazy Circular Gallery

**Files:**
- Create: `frontend/react-app/src/components/animations/reactbits/CircularGallery.tsx`
- Create: `frontend/react-app/src/components/animations/reactbits/CircularGallery.css`
- Create: `frontend/react-app/src/components/chat/CircularMediaGallery.tsx`
- Create: `frontend/react-app/src/components/chat/ImagePanel.test.tsx`
- Modify: `frontend/react-app/src/components/chat/ImagePanel.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageAssets.tsx`

**Interfaces:**

```ts
export interface CircularGalleryItem { image: string; text: string; id: string; alt: string }
export interface CircularGalleryEngine { destroy(): void; resize(): void }
export type CircularGalleryFactory = (host: HTMLElement, items: readonly CircularGalleryItem[], options: { bend: 0; borderRadius: 0.1 }) => CircularGalleryEngine
```

- [ ] **Step 1: Write RED component tests**

Assert no-image responses do not import OGL, options are exact, safe URL/alt/title mapping, stable responsive height, single texture failure isolation, engine-init failure fallback, reduced-motion fallback, context-lost fallback, accessible current-item text, and no visible scrollbar.

- [ ] **Step 2: Run RED**

```powershell
npm run test -- --run src/components/chat/ImagePanel.test.tsx src/components/chat/MessageBubble.test.tsx
```

- [ ] **Step 3: Port the OGL engine with explicit lifecycle**

Use the pinned React Bits shader and drag/wheel logic. Accept injected factory in tests, observe container size, cancel animation frames, remove listeners, release textures/renderer on destroy, and fire `onFailure(reason)` once. Do not construct URLs from object identity.

- [ ] **Step 4: Implement the React wrapper and DOM fallback**

Dynamic-import `CircularGallery` only when `items.length > 0`, hover-capable motion is allowed, and the host has nonzero dimensions. Fallback renders the same images in a keyboard-scrollable, scrollbar-hidden DOM strip.

- [ ] **Step 5: Run GREEN and build**

```powershell
npm run test -- --run src/components/chat/ImagePanel.test.tsx src/components/chat/MessageBubble.test.tsx
npm run build
```

Expected: the production bundle contains a separate lazy OGL chunk; no-image render does not request it.

---

### Task 6: Resolve One Wiki Artifact Snapshot and Build Deterministic Content Blocks

**Files:**
- Create: `src/huiji_wiki/snapshot.py`
- Create: `src/huiji_wiki/content_blocks.py`
- Create: `tests/test_huiji_wiki_snapshot.py`
- Create: `tests/test_huiji_wiki_content_blocks.py`
- Modify: `src/huiji_wiki/importer.py`
- Modify: `tests/test_huiji_wiki_importer.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class WikiArtifactSnapshot:
    source_mode: Literal["active", "legacy"]
    build_version: str
    artifact_schema_version: str
    parent_blocks: Path
    child_blocks: Path
    media_assets: Path
    manifest_sha256: str
    input_sha256: Mapping[str, str]
    activation_id: str | None
    activation_epoch: int | None
    snapshot_sha256: str

resolve_wiki_snapshot(cfg: Config, project_root: Path, evidence_root: Path) -> WikiArtifactSnapshot
build_content_blocks(page_id: str, children: Sequence[Mapping[str, object]]) -> list[dict[str, object]]
```

- [ ] **Step 1: Write RED snapshot tests**

Cover active pointer validation, pointer-absent configured legacy build, manifest absence, path traversal, wrong hashes, v1/v2 media exclusivity, create-new receipt, repeat verification, pointer/config change after capture, and no writes outside evidence root.

- [ ] **Step 2: Write RED block parser tests**

Cover headings, facts with both colon forms, Markdown lists/quotes/tables, JSON object/array parsing, zero/false retention, empty-value omission, recursion depth three plus collapsible detail, 240-code-point split threshold, stable IDs, character sections/skills, voice separation, and media IDs.

- [ ] **Step 3: Run RED**

```powershell
& $Python -m pytest tests/test_huiji_wiki_snapshot.py tests/test_huiji_wiki_content_blocks.py tests/test_huiji_wiki_importer.py -q
```

- [ ] **Step 4: Implement snapshot resolution**

Active mode validates pointer grammar and build-manifest hashes, then resolves parent/child/media paths from the pinned build wrapper/artifact root with containment checks. Legacy mode uses configured build standard files and hashes them into `data/processed/huiji/evidence/wiki-import/{snapshot_sha256}/wiki_import_snapshot.v1.json` using create-new semantics. Never write an active pointer.

- [ ] **Step 5: Implement deterministic blocks**

Normalize CRLF/NFC, preserve child order from parent `child_ids`, derive block IDs from page/section/child/stable index, parse structured syntax before fallback segmentation, and set `paragraph.reveal` only at 180 code points or fewer with no table/code syntax.

- [ ] **Step 6: Integrate blocks into payload construction**

`build_wiki_import_payload(snapshot, include_character)` reads only snapshot paths and sets `contentVersion=1`, `blocks`, summary, and existing compatibility fields. It never opens raw roots, diagnostic inventories, or MinIO.

- [ ] **Step 7: Run GREEN**

```powershell
& $Python -m pytest tests/test_huiji_wiki_snapshot.py tests/test_huiji_wiki_content_blocks.py tests/test_huiji_wiki_importer.py -q
```

---

### Task 7: Persist Snapshot Metadata and Extend Wiki API Safely

**Files:**
- Modify: `src/huiji_wiki/importer.py`
- Modify: `src/huiji_wiki/models.py`
- Modify: `src/huiji_wiki/repository.py`
- Modify: `scripts/import_huiji_wiki_pages.py`
- Modify: `backend/wiki_schemas.py`
- Modify: `backend/wiki.py`
- Modify: `tests/test_huiji_wiki_importer.py`
- Modify: `tests/test_huiji_wiki_repository.py`
- Modify: `tests/test_huiji_wiki_api.py`
- Modify: `frontend/react-app/src/types/wiki.ts`
- Modify: `frontend/react-app/src/api/wiki.ts`
- Modify: `frontend/react-app/src/api/wiki.test.ts`

**Interfaces:**

```python
class WikiHealthResponse(BaseModel):
    ready: bool
    pageCount: int = 0
    categoryCount: int = 0
    mediaLinkCount: int = 0
    linkSpanCount: int = 0
    aliasCount: int = 0
    sourceMode: str = ""
    buildVersion: str = ""
    artifactSchemaVersion: str = ""
    activationEpoch: int | None = None
    manifestSha256Prefix: str = ""
    stale: bool = False
    error: str = ""
```

- [ ] **Step 1: Write RED MySQL/API tests**

Assert `wiki_import_snapshots` schema, singleton upsert in the same transaction as pages, rollback on failure, idempotent repeat, health safe fields, 12-character lowercase manifest prefix, no paths/internal fields, and unchanged category/page contracts.

- [ ] **Step 2: Run RED**

```powershell
& $Python -m pytest tests/test_huiji_wiki_importer.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py -q
npm run test -- --run src/api/wiki.test.ts
```

- [ ] **Step 3: Add the Wiki-owned metadata table**

Create only through the importer transaction:

```sql
CREATE TABLE IF NOT EXISTS wiki_import_snapshots (
  id TINYINT NOT NULL PRIMARY KEY,
  source_mode VARCHAR(16) NOT NULL,
  build_version VARCHAR(64) NOT NULL,
  artifact_schema_version VARCHAR(64) NOT NULL,
  activation_epoch BIGINT NULL,
  manifest_sha256 CHAR(64) NOT NULL,
  input_sha256_json JSON NOT NULL,
  snapshot_sha256 CHAR(64) NOT NULL,
  imported_at_utc VARCHAR(40) NOT NULL,
  CHECK (id = 1)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

- [ ] **Step 4: Update CLI and repository**

CLI resolves the snapshot instead of accepting an unchecked processed directory. Preserve an explicit test-only `--legacy-build` option that still creates and verifies a receipt. Repository health reads metadata read-only and compares the current pointer/config snapshot identity to set `stale` without calling RAG `_state`.

- [ ] **Step 5: Keep public media sanitized**

Continue the existing `sanitize_media_item` allowlist. Add tests that v2 internal fields and local paths never survive page detail or health serialization.

- [ ] **Step 6: Run GREEN**

```powershell
& $Python -m pytest tests/test_huiji_wiki_importer.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py -q
npm run test -- --run src/api/wiki.test.ts
```

---

### Task 8: Render Structured Wiki Blocks with Scoped Scroll Reveal

**Files:**
- Create: `frontend/react-app/src/components/wiki/StructuredContentRenderer.tsx`
- Create: `frontend/react-app/src/components/wiki/StructuredContentRenderer.css`
- Create: `frontend/react-app/src/components/wiki/StructuredContentRenderer.test.tsx`
- Create: `frontend/react-app/src/components/wiki/WikiScrollRevealText.tsx`
- Modify: `frontend/react-app/src/types/wiki.ts`
- Modify: `frontend/react-app/src/components/wiki/WikiReader.tsx`
- Modify: all files under `frontend/react-app/src/components/wiki/templates/`
- Modify: `frontend/react-app/src/styles/global.css`

**Interfaces:**

```ts
export type WikiContentBlock =
  | { id: string; type: 'heading'; text: string; level: 1 | 2 | 3 }
  | { id: string; type: 'paragraph'; text: string; reveal: boolean }
  | { id: string; type: 'facts'; items: Array<{ label: string; value: string }> }
  | { id: string; type: 'list'; ordered: boolean; items: string[] }
  | { id: string; type: 'quote'; text: string }
  | { id: string; type: 'table'; headers: string[]; rows: string[][] }
  | { id: string; type: 'media'; mediaIds: string[] }
  | { id: string; type: 'voice'; sectionKey: string }
```

- [ ] **Step 1: Write RED renderer tests**

Cover every block type, heading levels, facts semantics, ordered/unordered lists, table overflow, media lookup, voice exclusion from prose, invalid-block isolation, legacy sections/summary fallback, safe empty-page fallback, reveal only for eligible headings/summary/paragraphs, and reduced-motion immediate text.

- [ ] **Step 2: Run RED**

```powershell
npm run test -- --run src/components/wiki/StructuredContentRenderer.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx
```

- [ ] **Step 3: Implement renderer and local ScrollTrigger lifecycle**

Pass the actual Wiki reader scroll element into `WikiScrollRevealText`. Set `baseRotation={0}`. Key all GSAP contexts by page ID and block ID; page changes revert only the previous page context. Facts, tables, controls, voice, and paragraphs over 180 code points never split into animated words.

- [ ] **Step 4: Replace template string dumping**

Templates retain only page-specific composition and media stage selection. All body blocks go through `StructuredContentRenderer`; remove generic `Object.entries(...).map(String)` output that produces unformatted text.

- [ ] **Step 5: Run GREEN**

```powershell
npm run test -- --run src/components/wiki/StructuredContentRenderer.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx src/components/wiki/WikiShell.test.tsx
npm run build
```

---

### Task 9: Complete the Three-Pane Wiki, Animated Index, and Tilted Media

**Files:**
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/components/wiki/wikiLayout.ts`
- Modify: `frontend/react-app/src/components/wiki/PageIndex.tsx`
- Modify: `frontend/react-app/src/components/wiki/PageInfo.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiReader.tsx`
- Modify: `frontend/react-app/src/components/ui/TiltedImageCard.tsx`
- Modify: `frontend/react-app/src/components/sections/CategoryPanel.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`
- Modify: other Wiki templates
- Test: corresponding existing tests plus `frontend/react-app/src/components/ui/TiltedImageCard.test.tsx`

**Interfaces:**

```ts
export const WIKI_LAYOUT_COLUMNS = 'minmax(220px, 0.62fr) minmax(0, 1.9fr) minmax(180px, 0.42fr)'
export interface TiltedImageCardProps {
  scaleOnHover?: number
  rotateAmplitude?: number
  displayOverlayContent?: false
  showTooltip?: false
  // existing image and style props remain
}
```

- [ ] **Step 1: Write RED layout/index tests**

Assert exactly three desktop areas, no CategoryRail/hot zone/reserved column, `PageInfo < PageIndex < WikiReader`, PageIndex image+name only, stable thumbnail ratio/placeholder, classification update animates list once, page selection does not replay all rows, global page scroll, local index/info scroll with hidden bars, and one-column mobile order.

- [ ] **Step 2: Write RED tilt tests**

Assert exact desktop parameters, transparent/no-border/no-shadow surfaces, `object-fit: contain`, reserved hover space and z-index isolation, touch/reduced-motion no tilt, and Character portrait/Live2D sharing one stage.

- [ ] **Step 3: Run RED**

```powershell
npm run test -- --run src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx src/components/wiki/WikiShell.test.tsx src/components/ui/TiltedImageCard.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx
```

- [ ] **Step 4: Implement responsive three-pane layout**

Remove the 1760px fixed-box dependency as the sizing authority; use responsive container width, minmax columns, and mobile grid areas. Keep body/global scroll available on `/wiki`; local panels use overscroll containment and hidden native bars.

- [ ] **Step 5: Implement AnimatedContent index rows**

Render thumbnail/placeholder and title only. Use page ID keys and horizontal AnimatedContent on query/category result replacement, not on selected-page state changes.

- [ ] **Step 6: Apply one TiltedImageCard implementation everywhere**

Set desktop defaults to 1.35/16, overlay false, tooltip false. Reserve transform space with stable aspect ratio and isolated stacking context. Remove image card backgrounds, frames, and shadows from Wiki and DataSection.

- [ ] **Step 7: Run GREEN**

```powershell
npm run test -- --run src/components/wiki/PageIndex.test.tsx src/components/wiki/PageInfo.test.tsx src/components/wiki/WikiShell.test.tsx src/components/ui/TiltedImageCard.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/App.wiki.test.tsx
npm run build
```

---

### Task 10: Add Read-Only Wiki Media Audit and Repair-Request Handoff

**Files:**
- Create: `src/huiji_wiki/media_audit.py`
- Create: `scripts/verify_wiki_media.py`
- Create: `tests/test_huiji_wiki_media_audit.py`
- Modify: `scripts/verify_huiji_wiki_e2e.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class WikiMediaAuditResult:
    status: Literal["verified", "missing", "repair-requested", "conflict", "blocked-by-evb", "stale-activation", "unverified-content-sha256"]
    media_id: str
    url: str
    http_status: int | None
    mime: str

audit_media(snapshot: WikiArtifactSnapshot, media_rows: Iterable[Mapping[str, object]], output: Path) -> dict[str, object]
write_repair_request(snapshot: WikiArtifactSnapshot, missing_rows: Sequence[Mapping[str, object]], output: Path) -> Path
```

- [ ] **Step 1: Write RED audit tests**

Use fake HTTP transport to cover verified bytes, 404, unsafe URL, SHA-1/size mismatch, absent nonvoice SHA-256, stale snapshot, create-new output, sanitized repair request, and batch stop. Assert zero imports/calls to MinIO clients, strict uploader, PUT, DELETE, bucket APIs, active pointer writer, or RAG state.

- [ ] **Step 2: Run RED**

```powershell
& $Python -m pytest tests/test_huiji_wiki_media_audit.py -q
```

- [ ] **Step 3: Implement URL-only streaming audit**

Accept rows only from the pinned snapshot. Verify HTTP(S), status, mime, decode/readback, size, and declared hashes. `content_sha256` absence maps only to `unverified-content-sha256`; it never becomes same-hash, conflict, or upload-eligible.

- [ ] **Step 4: Implement create-new repair request**

Write `wiki_media_repair_request.v1.json` containing source mode, build/snapshot identity, stable media IDs, expected object identity from internal artifact, missing evidence, and provenance. Sanitize all absolute paths and secrets. Do not create an operation plan or call C20.

- [ ] **Step 5: Run GREEN and static forbidden-call scan**

```powershell
& $Python -m pytest tests/test_huiji_wiki_media_audit.py tests/test_huiji_wiki_e2e_script.py -q
rg -n "put_object|fput_object|_execute\(|remove_object|delete|make_bucket|set_bucket|C20|minio-upload" src/huiji_wiki/media_audit.py scripts/verify_wiki_media.py
```

Expected: tests pass; scan contains no executable write path.

---

### Task 11: Add Browser-Level Accessibility, Responsive, and Canvas Hard Gates

**Files:**
- Create: `frontend/react-app/playwright.config.ts`
- Create: `frontend/react-app/e2e/wiki-reactbits.spec.ts`
- Modify: `frontend/react-app/package.json` scripts
- Create during execution: `eval/wiki-reactbits-p0/ui-evidence/**`

**Interfaces:**
- `npm run test:e2e` starts against an already running Vite/API pair.
- Evidence records viewport, route, selected real entity/page, canvas pixel count, screenshots, and fallback result.

- [ ] **Step 1: Add Playwright config and script**

Use Chromium projects for `1440x900`, `1024x768`, and `390x844`. Set retries to zero locally, trace on failure, and screenshot only on failure plus explicit evidence captures.

- [ ] **Step 2: Write E2E tests**

Cover Card Nav route labels/groups/theme cycle/Escape; no Sidebar/CategoryRail; Wiki three-pane and mobile order; PageIndex image+name; real content blocks; transparent tilted image; voice list hidden scrollbar and pagination; gallery drag; WebGL failure fallback; reduced motion; no text overlap by bounding-box assertions.

- [ ] **Step 3: Add Canvas pixel check**

```ts
const nonZeroPixels = await page.locator('[data-testid="circular-gallery"] canvas').evaluate(async canvas => {
  await new Promise(requestAnimationFrame)
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
  if (!gl) return 0
  const pixels = new Uint8Array(canvas.width * canvas.height * 4)
  gl.readPixels(0, 0, canvas.width, canvas.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels)
  let count = 0
  for (let i = 0; i < pixels.length; i += 4) if (pixels[i] || pixels[i + 1] || pixels[i + 2] || pixels[i + 3]) count++
  return count
})
expect(nonZeroPixels).toBeGreaterThan(100)
```

- [ ] **Step 4: Install Chromium once and run against real services**

```powershell
Set-Location frontend/react-app
npx playwright install chromium
npm run test:e2e
```

Expected: all viewports pass, canvas is nonblank, drag changes rendered pixels/active item, forced failure renders DOM images, and no required control is occluded.

---

### Task 12: Run Full Regression and Real End-to-End Acceptance

**Files:**
- Modify only if a failure exposes a P0 defect in files already owned by Tasks 1-11.
- Generate: `eval/wiki-reactbits-p0/final-report.v1.json`
- Generate: `eval/wiki-reactbits-p0/milvus-after.v1.json`
- Generate: `eval/wiki-reactbits-p0/spec-coverage.md`

- [ ] **Step 1: Run complete frontend regression and build**

```powershell
Set-Location frontend/react-app
npm run test -- --run
npm run build
```

Expected: all Vitest tests pass and TypeScript/Vite build succeeds.

- [ ] **Step 2: Run Wiki and transport backend regression**

```powershell
Set-Location $Project
& $Python -m pytest tests/test_huiji_wiki_snapshot.py tests/test_huiji_wiki_content_blocks.py tests/test_huiji_wiki_importer.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py tests/test_huiji_wiki_media_audit.py tests/test_huiji_wiki_e2e_script.py tests/test_voice_pagination.py tests/test_sse.py tests/test_chain_assets.py -q
```

Expected: PASS; no RAG expectation is weakened.

- [ ] **Step 3: Resolve and import one real snapshot**

```powershell
& $Python scripts/import_huiji_wiki_pages.py --include-character
& $Python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --output eval/wiki-reactbits-p0/final-report.v1.json
```

Expected: import report identifies exactly one source mode/snapshot; `/api/wiki/health` matches it and `stale=false`.

- [ ] **Step 4: Run dynamic real-data checks**

Select character, story, item, and psychube pages from current API data, not hardcoded IDs. Verify one real Wiki main image, one real chat gallery, and a real multi-page voice entity. Confirm response scans contain no internal fields or local paths.

- [ ] **Step 5: Run Playwright hard gates**

```powershell
Set-Location frontend/react-app
npm run test:e2e
```

- [ ] **Step 6: Prove external state remained unchanged**

```powershell
Set-Location $Project
& $Python scripts/minio_blue_green_evidence.py milvus-inventory --endpoint http://127.0.0.1:19530 --database default --output eval/wiki-reactbits-p0/milvus-after.v1.json
& $Python scripts/minio_blue_green_evidence.py compare-milvus --expected eval/wiki-reactbits-p0/milvus-before.v1.json --actual eval/wiki-reactbits-p0/milvus-after.v1.json --output eval/wiki-reactbits-p0/milvus-comparison.v1.json
```

Also compare the pinned artifact files, active pointer presence/hash, and MinIO inventory evidence captured in Task 0. Expected: Milvus and RAG artifacts/pointer are unchanged; MinIO has no Wiki-authored additions.

- [ ] **Step 7: Produce the exact spec coverage report**

For every P0 ID in the source spec, record task, code path, automated test, real acceptance evidence, and pass/fail. Any missing or partial row keeps the plan incomplete.

- [ ] **Step 8: Run forbidden-pattern scans**

```powershell
rg -n "dark-warm|parchment|mystic-purple|CategoryRail|sidebarOpen|toggleSidebar|setSidebar" frontend/react-app/src
rg -n "object_key|local_relpath|source_url|file://|[A-Z]:\\" frontend/react-app/src backend/wiki.py backend/wiki_schemas.py
rg -n "put_object|fput_object|remove_object|make_bucket|minio-upload" src/huiji_wiki scripts/verify_wiki_media.py
```

Expected: no production legacy theme/sidebar/category rail reference; no browser/public path leak; no Wiki storage write path. Test fixtures may contain forbidden strings only to assert rejection.

## 3. Optional P1 Tasks

Do not start these until every P0 task and real hard gate is green. Each requires separate user approval:

- `MOTION-P1-01..02`: animation preview and performance-based degradation.
- `NAV-P1-01..02`: page-type menu accents and recent Wiki links.
- `VOICE-UI-P1-01..02`: progress UI and session language preference.
- `IMAGE-UI-P1-01..02`: full-image viewer and texture windowing.
- `WIKI-LAYOUT-P1-01..02`: page-type animation profiles and mobile index drawer.
- `WIKI-CONTENT-P1-01..03`: specialized section mappings, keyword route links, and low-quality reports.
- `WIKI-TEXT-P1-01`, `TILT-P1-01`, `MEDIA-P1-01..02`, `QUALITY-P1-01`: optional refinements only.

## 4. Deferred / Out of Scope

No P2 implementation step is permitted in this plan. Deferred items include custom navigation layouts, cross-page shared transitions, voice waveforms, image-source linking, relationship graphs, Live2D player, CDN, media administration, visual-regression service, and device-performance dashboards.

## 5. Completion Self-Check

- [ ] All 104 P0 definitions in the source spec have a PASS row in `spec-coverage.md`.
- [ ] All frontend unit tests, backend focused tests, complete frontend suite, and production build pass.
- [ ] Playwright passes desktop, narrow, mobile, reduced-motion, WebGL, and fallback scenarios.
- [ ] Real MySQL/API pages cover character, story, item, and psychube from one pinned snapshot.
- [ ] Real voice pagination covers explicit language, `zh-hant` when eligible, 400, and 409 behavior.
- [ ] Real gallery canvas has nonzero pixels and drag changes observable state.
- [ ] Sidebar, legacy TopNav, and CategoryRail are absent with no layout reservation.
- [ ] Themes migrate and render using only the three approved seeds.
- [ ] Public payloads contain no internal object identity, local paths, credentials, or unsafe URL.
- [ ] Wiki wrote no RAG artifact, active pointer, Milvus row, MinIO object, bucket setting, or C20 marker.
- [ ] External-state before/after evidence matches, or any external change is reported as stale and the acceptance run is repeated.
- [ ] P1 items are either explicitly approved and separately tracked or left unexecuted; every P2 item remains deferred.
