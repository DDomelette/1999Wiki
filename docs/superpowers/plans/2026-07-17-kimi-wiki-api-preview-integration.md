# Kimi Wiki 真实 API 并行预览接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. The user has explicitly selected inline execution without subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在正式 React 应用内新增 `/wiki-preview/*`，使用真实 `/api/wiki/*` 驱动 Kimi/Stitch 角色选人页与 PC/移动详情页，验收前不替换正式 `/wiki/*`。

**Architecture:** 现有 `WikiShell` 继续作为唯一 Wiki 数据控制器，新增 `current | kimi-preview` 渲染变体和 route 前缀映射。预览组件只消费纯 ViewModel；Kimi 原型的静态数据、模拟媒体表和独立应用壳不进入生产构建。正式与预览共用 API、类型、Card Nav、搜索分页、历史状态与错误语义。

**Tech Stack:** React 18、TypeScript、Vite、Vitest、Testing Library、Playwright、现有 `/api/wiki/*`、现有 CSS 语义令牌与本地字体。

## Global Constraints

- 对应规格：`docs/superpowers/specs/2026-07-17-kimi-wiki-api-preview-integration-design.md`。
- 不使用子代理；不执行 git commit、reset、checkout 或清理用户现有改动。
- 不修改 RAG、Milvus、MySQL schema、MinIO 对象、`wiki_media_links` 或后端 API 契约。
- 正式 `/wiki/*` 在本轮保持可用且视觉不变。
- 所有新增生产行为先写失败测试并确认 RED，再做最小实现。
- 所有媒体只来自 API 公开 HTTP(S) URL；不得把 `kimi_web/src/media/contract.js` 复制到正式应用。
- Card Nav 是唯一全局导航；预览页面内部轨道只负责角色档案工作区。
- 页面视觉以 2026-07-14/15 已批准截图和 `kimi_web` 当前成品为权威。

---

## 1. 目标范围

### 本轮必须完成的 P0

- `PREVIEW-ROUTE-P0-01` 至 `PREVIEW-ROUTE-P0-04`
- `PREVIEW-DATA-P0-01` 至 `PREVIEW-DATA-P0-05`
- `PREVIEW-SELECT-P0-01` 至 `PREVIEW-SELECT-P0-05`
- `PREVIEW-DETAIL-P0-01` 至 `PREVIEW-DETAIL-P0-05`
- `PREVIEW-MEDIA-P0-01` 至 `PREVIEW-MEDIA-P0-05`
- `PREVIEW-ERROR-P0-01` 至 `PREVIEW-ERROR-P0-03`
- `PREVIEW-TEST-P0-01` 至 `PREVIEW-TEST-P0-07`

### 本轮不做

- 不切换正式 `/wiki/*`。
- 不迁移首页、资料页或问答页。
- 不实现 Live2D 播放器。
- 不建立剧情、心相、世界、阵营或日历的 Kimi 专属页。
- 不修改后端数据与媒体映射。

## 2. 强制验收检查点

| 检查点 | 对应规格 | 硬性证据 |
|---|---|---|
| KP-01 | ROUTE、ERROR | 正式路由测试不变；预览选人、详情、刷新、Back/Forward 测试通过 |
| KP-02 | DATA、MEDIA | 纯 ViewModel 测试；无静态 Druvis 数据、`objectKey`、本地路径或内部 endpoint |
| KP-03 | SELECT | 真实 API mock 契约组件测试；PC/移动结构和交互完整 |
| KP-04 | DETAIL | 同一 DTO 驱动 PC/移动组件树；全部数据模块、互斥皮肤与滚动测试通过 |
| KP-05 | ERROR、MEDIA | 分类/列表/详情/媒体/supplement 状态互不混淆；正式 Wiki 可回退 |
| KP-06 | TEST | 现有 199 项回归、全部新增测试、TypeScript 与生产构建通过 |
| KP-07 | TEST、SELECT、DETAIL | 真实 8000 API、真实媒体、多视口浏览器截图与 Network 安全审计通过 |

任何检查点失败，都不能建议替换正式 Wiki。

---

### Task 1: 建立并行 route 与共享控制器模式

**Files:**
- Modify: `frontend/react-app/src/components/wiki/wikiRoutes.ts`
- Modify: `frontend/react-app/src/components/wiki/wikiRoutes.test.ts`
- Modify: `frontend/react-app/src/App.tsx`
- Modify: `frontend/react-app/src/App.wiki.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.test.tsx`

**Interfaces:**
- Produces: `WikiShellVariant = 'current' | 'kimi-preview'`
- Produces: `parseWikiLocation(pathname, basePath?)`
- Produces: `toCanonicalWikiRoute(route, basePath)`、`toVisibleWikiRoute(route, basePath)`
- Preserves: existing `/wiki/*` behavior and `WikiSelectionHistoryState`

- [x] **Step 1: 写 route RED 测试**

在 `wikiRoutes.test.ts` 增加：

```ts
it('maps preview routes to API-owned canonical wiki routes without changing the suffix', () => {
  expect(parseWikiLocation('/wiki-preview/character', '/wiki-preview')).toEqual({ kind: 'character-selection' })
  expect(parseWikiLocation('/wiki-preview/char/3003', '/wiki-preview')).toEqual({
    kind: 'detail',
    route: '/wiki-preview/char/3003',
  })
  expect(toCanonicalWikiRoute('/wiki-preview/char/3003', '/wiki-preview')).toBe('/wiki/char/3003')
  expect(toVisibleWikiRoute('/wiki/character/3003', '/wiki-preview')).toBe('/wiki-preview/character/3003')
})
```

- [x] **Step 2: 运行 route 测试并确认因新接口缺失而失败**

Run:

```powershell
npm test -- src/components/wiki/wikiRoutes.test.ts
```

Expected: FAIL，报告 `toCanonicalWikiRoute`/`toVisibleWikiRoute` 未导出或 `basePath` 不受支持。

- [x] **Step 3: 实现最小 route 映射**

实现要求：

```ts
export type WikiRouteBase = '/wiki' | '/wiki-preview'

export function toCanonicalWikiRoute(route: string, basePath: WikiRouteBase): string {
  return basePath === '/wiki-preview' ? route.replace(/^\/wiki-preview(?=\/|$)/, '/wiki') : route
}

export function toVisibleWikiRoute(route: string, basePath: WikiRouteBase): string {
  return basePath === '/wiki-preview' ? route.replace(/^\/wiki(?=\/|$)/, '/wiki-preview') : route
}
```

`parseWikiLocation()` 使用传入 `basePath` 判断精确选人入口，但保留完整浏览器 route，不提前改写 API route。

- [x] **Step 4: 写 App/WikiShell RED 测试**

新增断言：

```tsx
window.history.replaceState({}, '', '/wiki-preview/character')
render(<App />)
expect(await screen.findByTestId('wiki-shell')).toHaveAttribute('data-wiki-variant', 'kimi-preview')
```

详情断言必须证明：

```tsx
window.history.replaceState({}, '', '/wiki-preview/char/3003')
render(<WikiShell variant="kimi-preview" />)
await waitFor(() => expect(wikiApi.fetchWikiPageByRoute).toHaveBeenCalledWith('/wiki/char/3003'))
expect(window.location.pathname).toBe('/wiki-preview/char/3003')
```

- [x] **Step 5: 运行测试并确认预览分支尚不存在**

Run:

```powershell
npm test -- src/App.wiki.test.tsx src/components/wiki/WikiShell.test.tsx
```

Expected: FAIL，预览仍落入主站或 `WikiShell` 尚不支持 variant。

- [x] **Step 6: 为 App 和 WikiShell 增加 variant，不复制 API 状态机**

实现边界：

```tsx
if (pathname.startsWith('/wiki-preview')) return <WikiShell variant="kimi-preview" />
if (pathname.startsWith('/wiki')) return <WikiShell variant="current" />
```

`WikiShell` 内统一计算：

```ts
const basePath: WikiRouteBase = variant === 'kimi-preview' ? '/wiki-preview' : '/wiki'
const selectionRoute = `${basePath}/character`
```

详情请求前调用 `toCanonicalWikiRoute()`；API 返回 route 写入浏览器前调用 `toVisibleWikiRoute()`；选人状态、分页和错误状态继续使用原有逻辑。Task 1 暂时沿用现有选人/详情渲染组件，只建立可独立通过测试的预览 route 与共享控制器；Task 3/4 再替换预览渲染分支。

- [x] **Step 7: 验证 Task 1 GREEN**

Run:

```powershell
npm test -- src/components/wiki/wikiRoutes.test.ts src/App.wiki.test.tsx src/components/wiki/WikiShell.test.tsx
```

Expected: PASS，且原正式 route 测试仍通过。

---

### Task 2: 建立 Kimi 纯 ViewModel 与媒体白名单

**Files:**
- Create: `frontend/react-app/src/components/wiki-preview/kimiWikiPreviewViewModel.ts`
- Create: `frontend/react-app/src/components/wiki-preview/kimiWikiPreviewViewModel.test.ts`
- Reuse: `frontend/react-app/src/components/wiki/wikiViewModel.ts`
- Reuse: `frontend/react-app/src/components/wiki/characterDetailViewModel.ts`

**Interfaces:**
- Consumes: `WikiPageListItem[]`、`WikiPageViewModel | null`
- Produces: `KimiWikiSelectionViewModel`
- Produces: `KimiWikiDetailViewModel`
- Produces: `buildKimiWikiPreviewViewModel(...)`

- [x] **Step 1: 写 ViewModel RED 测试**

测试 fixture 包含两个角色、一个规范 route、一个初始立绘、一个洞悉立绘、一个 backdrop、技能、传承、塑造、文化和藏品。断言：

```ts
const result = buildKimiWikiPreviewViewModel(pages, 'char:3003', buildWikiPageViewModel(detail))
expect(result.selected?.title).toBe('槲寄生')
expect(result.selected?.canonicalRoute).toBe('/wiki/char/3003')
expect(result.selected?.portrait?.url).toBe('https://media.test/initial.webp')
expect(result.selected?.backdrop?.url).toBe('https://media.test/backdrop.webp')
expect(result.detail?.character.inheritance?.title).toBe('木秀于林')
expect(result.detail?.character.portray?.levels.map((item) => item.level)).toEqual(['LV.1', 'LV.5'])
expect(JSON.stringify(result)).not.toMatch(/objectKey|local_relpath|file:\/\//i)
```

另写失败媒体测试：相对 URL、`file://`、本地盘符和非 HTTP URL 不得进入输出。

- [x] **Step 2: 运行测试并确认模块不存在**

Run:

```powershell
npm test -- src/components/wiki-preview/kimiWikiPreviewViewModel.test.ts
```

Expected: FAIL，找不到模块。

- [x] **Step 3: 实现白名单 ViewModel**

核心结构：

```ts
export interface KimiPreviewMedia {
  id: string
  url: string
  title: string
  role: string
  variant: string
}

export interface KimiWikiSelectionEntry {
  pageId: string
  title: string
  subtitle: string
  summary: string
  canonicalRoute: string
  thumbnail: string
  selected: boolean
}

export interface KimiWikiPreviewViewModel {
  entries: KimiWikiSelectionEntry[]
  selected: null | KimiWikiSelectionEntry & {
    portrait: KimiPreviewMedia | null
    backdrop: KimiPreviewMedia | null
  }
  detail: null | {
    character: CharacterDetailViewModel
    backdrop: KimiPreviewMedia | null
  }
}
```

媒体选择只看 API 显式 `role`、`sectionKey`、`variant` 和 HTTP(S) URL；不看文件名、拼音或编号。详情主体复用 `buildCharacterDetailViewModel()`，避免建立第二套 section parser。

- [x] **Step 4: 验证 ViewModel GREEN**

Run:

```powershell
npm test -- src/components/wiki-preview/kimiWikiPreviewViewModel.test.ts src/components/wiki/characterDetailViewModel.test.ts
```

Expected: PASS。

---

### Task 3: 实现真实数据驱动的 Kimi 选人预览

**Files:**
- Create: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterSelectionPage.tsx`
- Create: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterSelectionPage.test.tsx`
- Create: `frontend/react-app/src/components/wiki-preview/KimiWikiPreview.css`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`

**Interfaces:**
- Consumes: `KimiWikiPreviewViewModel`
- Consumes: query/loading/error/pagination/history state from `WikiShell`
- Produces callbacks: query change、select、load more、retry、scroll position、open detail

- [x] **Step 1: 写选人页 RED 测试**

覆盖以下行为：

```tsx
render(<KimiWikiCharacterSelectionPage model={model} query="" totalCount={132} ... />)
expect(screen.getByTestId('wiki-character-selection-preview')).toBeInTheDocument()
expect(screen.getByText('ARCHIVE INDEX')).toBeInTheDocument()
expect(screen.getByText('132')).toBeInTheDocument()
expect(screen.getByRole('button', { name: '槲寄生' })).toHaveAttribute('aria-pressed', 'true')
fireEvent.change(screen.getByRole('searchbox', { name: '搜索页面' }), { target: { value: '露西' } })
expect(onQueryChange).toHaveBeenCalledWith('露西')
fireEvent.click(screen.getByRole('button', { name: '查看完整档案' }))
expect(onOpenDetail).toHaveBeenCalledTimes(1)
```

再覆盖 loading、空结果、列表 503、局部媒体 fallback 和 load-more 失败后保留已加载条目。

- [x] **Step 2: 运行测试并确认组件不存在**

Run:

```powershell
npm test -- src/components/wiki-preview/KimiWikiCharacterSelectionPage.test.tsx
```

Expected: FAIL，找不到组件。

- [x] **Step 3: 实现 PC/移动共用语义结构**

PC DOM 区域固定为：

```text
ArchiveSectionRail | CharacterRoster | CharacterStage | PersonnelSummary
```

移动 DOM 顺序固定为：

```text
ArchiveIndex + independent roster scroll
CharacterStage
PersonnelSummary + CTA
```

条目使用 `<button>`，搜索使用 `<input type="search">`，CTA 在无规范 route 时禁用。舞台只显示当前角色 ViewModel 的 backdrop/portrait；缺失时显示固定尺寸 `MEDIA UNAVAILABLE`。

- [x] **Step 4: 将 WikiShell 预览 selection 分支接到新组件**

`variant === 'kimi-preview'` 时传入同一套真实状态和事件；`variant === 'current'` 继续渲染原 `WikiCharacterSelectionPage`。

- [x] **Step 5: 验证选人页 GREEN 与正式页不回归**

Run:

```powershell
npm test -- src/components/wiki-preview/KimiWikiCharacterSelectionPage.test.tsx src/components/wiki/WikiShell.test.tsx src/components/wiki/WikiCharacterSelectionPage.test.tsx
```

Expected: PASS。

---

### Task 4: 实现真实数据驱动的 Kimi PC/移动详情预览

**Files:**
- Create: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterDetailPage.tsx`
- Create: `frontend/react-app/src/components/wiki-preview/KimiDesktopCharacterDossier.tsx`
- Create: `frontend/react-app/src/components/wiki-preview/KimiMobileCharacterDossier.tsx`
- Create: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterDetailPage.test.tsx`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiPreview.css`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Reuse: `frontend/react-app/src/components/wiki/character-detail/*`

**Interfaces:**
- Consumes: `KimiWikiDetailViewModel`
- Produces: mutually exclusive desktop/mobile dossier trees
- Preserves: existing child renderers for skills、progression、voices、culture、collection

- [x] **Step 1: 写详情页 RED 测试**

桌面测试断言：

```tsx
expect(screen.getByTestId('kimi-desktop-character-dossier')).toBeInTheDocument()
expect(screen.getByTestId('kimi-character-stage')).toBeInTheDocument()
expect(screen.getByText('木秀于林')).toBeInTheDocument()
expect(screen.getByText('LV.5')).toBeInTheDocument()
expect(screen.getAllByTestId('character-skill-card')).toHaveLength(3)
```

移动测试把 `matchMedia('(max-width: 760px)')` 设为 true，并断言模块顺序：

```ts
['hero', 'summary', 'profile', 'inheritance', 'portray', 'skills', 'ultimate', 'voices', 'culture', 'collection', 'technical']
```

皮肤测试点击 Initial/Insight，断言只有对应图片具备 active/visible 状态；Live2D 按钮存在且为不可用状态。

- [x] **Step 2: 运行测试并确认组件不存在**

Run:

```powershell
npm test -- src/components/wiki-preview/KimiWikiCharacterDetailPage.test.tsx
```

Expected: FAIL，找不到组件。

- [x] **Step 3: 实现 Kimi desktop 顶层几何**

桌面区域：

```text
左：身份卡、纸张 profile、技能、文化，可独立滚动
中：共享 backdrop、初始/洞悉立绘、状态叠层、Wardrobe 切换
右：身份摘要、传承、塑造、语音、藏品，可独立到达
```

复用现有 `CharacterProfileData`、`CharacterSkillCards`、`CharacterProgression`、`CharacterVoiceRecords`、`CharacterCulture`、`CharacterCollection`，但由 Kimi 顶层模块树控制位置；不得渲染静态 `PROFILE_ROWS`、`SKILLS` 或 `COMP_*`。

- [x] **Step 4: 实现 Kimi mobile 长文档流**

移动端不缩放桌面；只保留语音为内部滚动拥有者，其他模块进入自然全局文档流。底栏 `DOSSIER/ARCHIVE/COMBAT` 分别保持当前、返回选人和定位技能。

- [x] **Step 5: 将 WikiShell 预览 detail 分支接到新组件**

`variant === 'kimi-preview'` 且 `pageType === 'character'` 时渲染 Kimi 详情；非角色详情继续使用现有 Generic Wiki，避免角色视觉误套其他模板。

- [x] **Step 6: 验证详情 GREEN 与正式详情不回归**

Run:

```powershell
npm test -- src/components/wiki-preview/KimiWikiCharacterDetailPage.test.tsx src/components/wiki/WikiCharacterDetailPage.test.tsx src/components/wiki/WikiShell.test.tsx
```

Expected: PASS。

---

### Task 5: 完成 namespaced 像素样式、字体和错误状态

**Files:**
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiPreview.css`
- Modify: `frontend/react-app/src/styles/fonts.css` only if an approved local font face is missing
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.test.tsx`
- Modify: preview component tests

**Interfaces:**
- Consumes existing semantic theme tokens and local font files
- Produces `.kimi-wiki-preview*` namespaced styles

- [x] **Step 1: 写 CSS/错误状态 RED 检查**

测试读取 CSS 并断言：

```ts
expect(css).toContain('.kimi-wiki-preview')
expect(css).toContain('grid-template-columns: 256px 128px minmax(0, 1fr) 400px')
expect(css).toContain('@media (max-width: 760px)')
expect(css).toContain('backdrop-filter')
expect(css).not.toMatch(/https?:\/\//)
```

组件测试分别注入分类失败、列表失败、详情 404、详情 503、媒体失败，断言状态文案和重试按钮不同。另在 `WikiShell.test.tsx` mock `fetchWikiHealth()`：

```tsx
vi.mocked(wikiApi.fetchWikiHealth).mockResolvedValue({
  ready: true,
  pageCount: 132,
  categoryCount: 6,
  mediaLinkCount: 1,
  linkSpanCount: 0,
  aliasCount: 0,
  sourceMode: 'mysql',
  buildVersion: 'dev',
  artifactSchemaVersion: '1',
  manifestSha256Prefix: 'abc123',
  stale: false,
  supplementReady: false,
  supplementStale: true,
  error: '',
})
render(<WikiShell variant="kimi-preview" />)
expect(await screen.findByText(/SUPPLEMENT STALE/i)).toBeInTheDocument()
```

- [x] **Step 2: 运行测试并确认固定几何和状态尚未完成**

Run:

```powershell
npm test -- src/components/wiki-preview
```

Expected: FAIL 于缺失的布局 token 或状态结构。

- [x] **Step 3: 从 Kimi 成品翻译为 namespaced CSS**

要求：

- 不引入 Tailwind runtime 或全局 reset。
- 使用现有本地 `Libre Caslon Text`、`JetBrains Mono`、Material Symbols/Lucide。
- 使用现有 `/images/wiki/natural-paper.png` 与全局背景；不复制远程 CDN URL。
- PC 选人参考网格为 `256px 128px minmax(0, 1fr) 400px`。
- PC 详情保持 64px Card Nav 下单视口工作台；移动详情自然纵向滚动。
- 亚克力面板使用半透明表面和 `backdrop-filter`，其下必须有实际共享背景。
- `prefers-reduced-motion` 下取消非必要转场。

`WikiShell` 仅在 `kimi-preview` variant 挂载时调用现有 `fetchWikiHealth()`，把 `supplementReady`、`supplementStale` 和 health error 转换为预览诊断条；正式 `current` variant 不增加该请求。health 失败不阻止 canonical 页面渲染，但 KP-05/KP-07 验收失败。

- [x] **Step 4: 验证 namespaced 样式和错误状态 GREEN**

Run:

```powershell
npm test -- src/components/wiki-preview
```

Expected: PASS，正式 Wiki CSS 不被选择器覆盖。

---

### Task 6: 全量自动化回归与生产构建

**Files:**
- Modify only files required by failures caused by Tasks 1-5

**Interfaces:**
- Produces buildable frontend with current and preview Wiki variants

- [x] **Step 1: 运行全部前端单测**

Run:

```powershell
npm test
```

Expected: 全部通过；基线为 44 test files / 199 tests，加上本轮新增测试。不得忽略 React warning。

- [x] **Step 2: 运行 TypeScript 与生产构建**

Run:

```powershell
npm run build
```

Expected: PASS。既有 chunk-size warning 可记录，但不得新增编译、CSS 或资源错误。

- [x] **Step 3: 扫描生产源码和产物中的禁出字段**

Run:

```powershell
rg -n "BACKEND_ONLY|WIKI_MEDIA_LINKS|objectKey|local_relpath|file://|127\.0\.0\.1:9002|localhost:9002|:8001" src dist
```

Expected: 预览运行时代码和 `dist` 无命中；测试 fixture 若刻意包含禁出字段，只能出现在测试文件并必须验证被剥离。

---

### Task 7: 真实 API、浏览器与截图验收

**Files:**
- Create: `frontend/react-app/e2e/wiki-kimi-preview.spec.ts`
- Create evidence: `eval/kimi-wiki-preview-20260717/screenshots/*.png`
- Modify: `docs/superpowers/plans/2026-07-17-kimi-wiki-api-preview-integration.md` checkbox/status only after evidence exists

**Interfaces:**
- Consumes running FastAPI `:8000` and Vite dev server
- Produces read-only integration evidence and replacement recommendation

- [x] **Step 1: 写真实浏览器 E2E**

测试必须：

```ts
await page.goto('/wiki-preview/character', { waitUntil: 'networkidle' })
await expect(page.getByTestId('wiki-character-selection-preview')).toBeVisible()
await expect(page.getByTestId('kimi-character-roster')).toContainText('槲寄生')
await page.getByRole('button', { name: '槲寄生' }).click()
await page.getByRole('button', { name: '查看完整档案' }).click()
await expect(page).toHaveURL(/\/wiki-preview\/(?:char|character)\/3003$/)
await expect(page.getByTestId(/kimi-(?:desktop|mobile)-character-dossier/)).toBeVisible()
```

并记录所有 `/api/wiki/*` 非 GET、`:8001`、`file://`、盘符路径、内部 MinIO URL 为违规。

- [x] **Step 2: 启动或复用 8000 与空闲 Vite 端口**

先读取当前终端和端口；只启动缺失服务，不停止或重置 RAG。Vite 通过现有代理访问 8000。

- [x] **Step 3: 运行桌面与移动 E2E**

Run:

```powershell
npx playwright test e2e/wiki-kimi-preview.spec.ts --project=stitch-desktop --project=desktop --project=mobile
```

Expected: PASS。

- [x] **Step 4: 扩展相邻视口人工/脚本验收**

依次检查：

```text
1280x1024
1440x900
1920x1080
360x800
390x844
412x915
```

每个视口断言：无横向溢出、无重叠、媒体 `naturalWidth > 0`、正文与滚动区域可达。

- [x] **Step 5: 真实角色抽样**

除槲寄生外，从真实 API 当前角色列表选择至少两名角色，确认切换后姓名、route、立绘、技能和档案内容全部同步变化；无媒体角色必须显示自己的 fallback，不能保留上一角色图片。

- [x] **Step 6: 截图对照与证据归档**

输出：

```text
selection-1280x1024.png
selection-390x844.png
detail-1280x951.png
detail-390x844-hero.png
detail-390x844-inheritance.png
detail-390x844-skills.png
detail-390x844-collection.png
```

将关键模块与批准截图逐项对照。缺少任何详情模块、错误背景层或错误滚动边界均判定失败。

- [x] **Step 7: 输出替换结论但不切换正式路由**

结论只能是：

```text
建议替换：KP-01 至 KP-07 全部通过
暂不替换：列出未通过检查点、证据和下一修复动作
```

---

## 3. 可选任务（P1，不在本轮自动执行）

- `PREVIEW-ROUTE-P1-01`、`PREVIEW-DATA-P1-01`、`PREVIEW-TEST-P1-01`：用户批准预览后，把 Kimi 组件切到正式 `/wiki/*`，保留短期回退开关。
- `PREVIEW-SELECT-P1-01`：正式替换后保存最近访问与选人滚动位置。
- `PREVIEW-DETAIL-P1-01`：RAG 来源跳转到 Wiki 规范 route 和目标段落。
- `PREVIEW-MEDIA-P1-01`：媒体缺失只读报告。

## 4. Deferred / Out of Scope

- 所有规格 P2。
- 首页、资料页和问答页全面 Kimi 化。
- 非角色 Wiki 专属模板。
- Live2D 播放器。
- 任何后端、数据库或对象存储写操作。

## 5. 完成后自检表

- [x] KP-01：正式 `/wiki/*` 未改变，预览路由/历史完整。
- [x] KP-02：只使用正式 API 与白名单 ViewModel，无静态角色/内部媒体字段。
- [x] KP-03：PC/移动选人页完整、真实、可搜索分页。
- [x] KP-04：PC/移动详情全部模块真实驱动且可达。
- [x] KP-05：错误状态区分清楚，媒体失败不串角色，正式 Wiki 可回退。
- [x] KP-06：新增与既有测试、TypeScript、构建和产物扫描通过。
- [x] KP-07：真实 API、真实媒体、多视口截图和 Network 审计通过。
- [x] 未执行任何 P1 正式替换或 P2 项目。

## 6. 2026-07-17 执行证据

- `npm test`：48 个测试文件、220 项测试全部通过，无 React warning。
- `npm run build`：TypeScript 与 Vite 生产构建通过；仅保留既有的单 chunk 超过 500 kB 提示。
- 生产源码与 `dist` 禁出字段扫描：0 命中。
- `GET /api/wiki/health`：`ready=true`、`pageCount=7456`、`supplementReady=true`、`supplementStale=false`。
- `wiki-kimi-preview.spec.ts`：真实 8000 API 下 2 项 E2E 全部通过，覆盖三角色抽样、搜索、分页、规范详情 route 和只读 Network 审计。
- 截图证据：`eval/kimi-wiki-preview-20260717/screenshots/` 下共 16 张，覆盖 2560x1440、1920x1080、1440x900、1280x951、1280x1024、360x800、390x844、412x915 的选人页与详情页。
- 浏览器检查发现并修复桌面选人舞台被 roster 撑到 6303.5px 的问题；新增首屏媒体可见性断言后复验通过。

**执行结论：建议替换，KP-01 至 KP-07 全部通过；本轮未切换正式 `/wiki/*`。**
