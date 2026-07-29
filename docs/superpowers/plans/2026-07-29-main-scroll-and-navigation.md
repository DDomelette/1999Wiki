# Main Scroll and Navigation Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This repository uses a Kimi CLI worker supervised inline by Codex; do not dispatch Codex subagents.

**Goal:** Replace the nested data-page scroller with one semantic full-page scroll sequence, preserve chat-message scrolling with an approved top-boundary return gesture, keep the active page aligned across viewport changes, and make main/Wiki navigation restore the requested section reliably.

**Architecture:** `.snap-container` becomes the only page-level vertical scroll owner and observes `home`, every `data:{key}` panel, and `chat`. Small pure navigation helpers own hash encoding/parsing and explicit main-container offsets; focused hooks own viewport realignment and chat touch-boundary arbitration. Kimi CLI writes each test-first batch inside the approved worktree, while Codex enforces the whitelist, reviews every diff, reruns tests, and creates accepted commits.

**Tech Stack:** React 18, TypeScript 5.5, Zustand 4, CSS Scroll Snap, Vitest 2, Testing Library, Playwright 1.61, Kimi CLI 0.26.0.

## Global Constraints

- Work only in `D:\1999Wiki\.worktrees\main-scroll-navigation-fix` on branch `codex/main-scroll-navigation-fix`.
- Invoke Kimi CLI only through `D:\KIMI\Kimi_Cli\bin\kimi.exe --yolo --prompt`; Kimi CLI 0.26.0 rejects combining `--auto` with prompt mode.
- Kimi CLI must not commit, push, merge, rebase, reset, clean, install dependencies, edit plans/specs, or touch the main checkout.
- Page-level vertical scrolling has exactly one owner: `.snap-container`.
- Preserve a separate `.chat-section__messages` scroll owner for chat history.
- Page snap remains `y mandatory` with `scroll-snap-stop: always` at every supported width.
- Do not set global `scroll-behavior: smooth`; each navigation call chooses `smooth` or `auto`.
- Main stable URLs are `/#home`, `/#data`, `/#chat`, and `/#data/<encodeURIComponent(categoryKey)>`.
- Navigation clicks use `pushState`; passive snap synchronization uses `replaceState`; resize and async recovery do not write history.
- Kimi CLI may modify only the exact whitelist in design section 10.4.
- Preserve API, Store shapes, Wiki rendering, dependencies, lock files, build configuration, copy, visual poster design, safe areas, and reduced-motion behavior.
- Each task starts with failing tests and ends with a Codex-reviewed commit.
- Baseline: 51 Vitest files and 278 tests pass before implementation.

---

## File Map

### New focused units

- `frontend/react-app/src/navigation/mainSectionNavigation.ts`
  - Owns `MainRouteTarget`, `MainSnapId`, hash parsing/formatting, semantic target resolution, explicit scroller-relative offset calculation, history writes, and main-container navigation.
- `frontend/react-app/src/navigation/mainSectionNavigation.test.ts`
  - Covers Unicode category hashes, generic data resolution, missing targets, offset math, scroll behavior, and push/replace/none history modes.
- `frontend/react-app/src/hooks/useMainViewportAlignment.ts`
  - Debounces layout-viewport changes and realigns the active semantic snap target with `behavior: "auto"`.
- `frontend/react-app/src/hooks/useMainViewportAlignment.test.tsx`
  - Covers `window.resize`, `visualViewport.resize`, cleanup, debouncing, and unchanged chat-message `scrollTop`.
- `frontend/react-app/src/hooks/useChatPageBoundaryNavigation.ts`
  - Detects one deliberate finger-down gesture at the top of chat history and navigates once to the previous main snap target.
- `frontend/react-app/src/hooks/useChatPageBoundaryNavigation.test.tsx`
  - Covers normal inner scrolling, wrong direction, below-threshold motion, one-shot navigation, bottom boundary, and listener cleanup.

### Existing units to modify

- `frontend/react-app/src/App.tsx`
  - Installs semantic hash restoration and viewport alignment around the one main scroller.
- `frontend/react-app/src/App.wheel.test.tsx`
  - Updates the expected flat target sequence and verifies page-level scroll ownership.
- `frontend/react-app/src/styles/global.css`
  - Restores mandatory/always snap on phones and removes container-wide smooth behavior.
- `frontend/react-app/src/hooks/useScrollSpy.ts`
  - Uses `.snap-container` as the explicit IntersectionObserver root and observes only leaf snap targets.
- `frontend/react-app/src/hooks/useScrollSpy.test.tsx`
  - Verifies root selection and state updates for flat data targets.
- `frontend/react-app/src/hooks/useWheelSnapNavigation.ts`
  - Uses the shared semantic target list and preserves chat/description inner-wheel priority.
- `frontend/react-app/src/hooks/useWheelSnapNavigation.test.tsx`
  - Covers the shared target-order helper if extraction makes standalone hook coverage clearer.
- `frontend/react-app/src/components/navigation/navigationConfig.ts`
  - Routes every main action through `navigateToMainSection` and keeps Wiki “问答” at `/#chat`.
- `frontend/react-app/src/components/navigation/RouteAwareCardNav.tsx`
  - Keeps existing menu behavior while consuming unified navigation actions.
- `frontend/react-app/src/components/navigation/RouteAwareCardNav.test.tsx`
  - Verifies main actions, Wiki chat URL, menu closure, and history semantics.
- `frontend/react-app/src/components/sections/DataSection.tsx`
  - Becomes a non-scrolling semantic group with a loading panel, leaf category snap targets, and an overlay/sticky category nav.
- `frontend/react-app/src/components/sections/DataSection.css`
  - Removes nested overflow/snap and keeps desktop/mobile nav visuals within the full data sequence.
- `frontend/react-app/src/components/sections/ChatSection.tsx`
  - Installs approved chat touch-boundary navigation and uses unified home navigation.
- `frontend/react-app/src/components/sections/ChatSection.css`
  - Preserves one-screen flex layout and local message overflow.
- `frontend/react-app/src/components/sections/ChatSection.test.tsx`
  - Verifies unified home action, local scroll ownership, and boundary hook wiring.
- `frontend/react-app/src/components/sections/MainResponsiveCss.test.ts`
  - Replaces proximity-snap expectations with mandatory/always and no nested data scroll.
- `frontend/react-app/e2e/main-mobile-responsive.spec.ts`
  - Adds semantic navigation, resize, sequence, chat-boundary, history, and cross-route coverage.

---

### Task 1: Semantic Section Navigation and URL Restoration

**Kimi batch:** 1 of 4

**Files:**
- Create: `frontend/react-app/src/navigation/mainSectionNavigation.ts`
- Create: `frontend/react-app/src/navigation/mainSectionNavigation.test.ts`
- Modify: `frontend/react-app/src/components/navigation/navigationConfig.ts`
- Modify: `frontend/react-app/src/components/navigation/RouteAwareCardNav.test.tsx`
- Modify: `frontend/react-app/src/App.tsx`
- Modify: `frontend/react-app/src/App.wiki.test.tsx` is not allowed by the approved whitelist; do not touch it. Put route restoration coverage in `mainSectionNavigation.test.ts` and the existing allowed E2E file.

**Interfaces:**
- Produces:

```ts
export type MainSnapId = 'home' | 'chat' | 'data:loading' | `data:${string}`

export type MainRouteTarget =
  | { kind: 'home' }
  | { kind: 'chat' }
  | { kind: 'data'; categoryKey?: string }

export interface NavigateMainOptions {
  behavior?: ScrollBehavior
  history?: 'push' | 'replace' | 'none'
}

export function mainTargetToHash(target: MainRouteTarget): string
export function parseMainHash(hash: string): MainRouteTarget | null
export function resolveMainSnapId(
  target: MainRouteTarget,
  availableSnapIds: readonly MainSnapId[],
): MainSnapId | null
export function mainSnapIdToTarget(snapId: MainSnapId): MainRouteTarget
export function getMainSnapIds(root?: ParentNode): MainSnapId[]
export function navigateToMainSection(
  target: MainRouteTarget,
  options?: NavigateMainOptions,
): boolean
```

- `navigateToMainSection` returns `false` without scrolling or history writes when `.snap-container` or the resolved leaf target is unavailable.
- Generic `{ kind: "data" }` resolves to the first real `data:{key}` target, then `data:loading` if real categories are unavailable.
- Offset calculation is:

```ts
targetRect.top - scrollerRect.top + scroller.scrollTop
```

  This remains correct when a snap target is nested inside the non-scrolling `DataSection` group.

- Main action clicks choose behavior with:

```ts
const behavior: ScrollBehavior =
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ? 'auto'
    : 'smooth'
```

  and call `navigateToMainSection(target, { behavior, history: "push" })`.
- App startup and `hashchange` call the same entry point with `{ behavior: "auto", history: "none" }`.

- [ ] **Step 1: Write failing pure navigation tests**

Create table-driven tests containing these exact cases:

```ts
expect(mainTargetToHash({ kind: 'home' })).toBe('#home')
expect(mainTargetToHash({ kind: 'data' })).toBe('#data')
expect(mainTargetToHash({ kind: 'chat' })).toBe('#chat')
expect(mainTargetToHash({ kind: 'data', categoryKey: '人物 档案' }))
  .toBe('#data/%E4%BA%BA%E7%89%A9%20%E6%A1%A3%E6%A1%88')

expect(parseMainHash('#chat')).toEqual({ kind: 'chat' })
expect(parseMainHash('#data/%E4%BA%BA%E7%89%A9')).toEqual({
  kind: 'data',
  categoryKey: '人物',
})
expect(parseMainHash('#unknown')).toBeNull()
expect(parseMainHash('#data/%E0%A4%A')).toBeNull()

expect(resolveMainSnapId(
  { kind: 'data' },
  ['home', 'data:人物', 'data:心相', 'chat'],
)).toBe('data:人物')
expect(resolveMainSnapId(
  { kind: 'data' },
  ['home', 'data:loading', 'chat'],
)).toBe('data:loading')
```

Add a DOM test where `.snap-container` has `scrollTop = 400`, the scroller rect top is `20`, the chat rect top is `620`, and navigation to chat calls:

```ts
expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: 'smooth' })
```

Assert `pushState`, `replaceState`, and `none` separately. Assert a missing target returns `false` and does not write history.

- [ ] **Step 2: Run the navigation test and verify failure**

Run:

```powershell
npm test -- --run src/navigation/mainSectionNavigation.test.ts
```

Expected: FAIL because `mainSectionNavigation.ts` and its exports do not exist.

- [ ] **Step 3: Implement the minimal navigation module**

Implement only the declared interfaces. Use `decodeURIComponent` inside `try/catch`; reject an empty category key. Query only within `.snap-container` for `[data-snap-section]`. Use an exact attribute match by filtering the returned elements rather than interpolating an unescaped category key into a CSS selector.

History behavior:

```ts
const url = `${window.location.pathname}${window.location.search}${mainTargetToHash(target)}`
if (history === 'push') window.history.pushState({}, '', url)
if (history === 'replace') window.history.replaceState({}, '', url)
```

Do not use `scrollIntoView`.

- [ ] **Step 4: Route main and Wiki navigation through the shared contract**

In `navigationConfig.ts`:

- Replace the local `jump()` implementation with actions that call `navigateToMainSection`.
- Keep Wiki’s “问答” link exactly `/#chat`.
- Do not modify Wiki category selection or content-anchor actions.

In `App.tsx`:

- On initial main-app mount, parse `window.location.hash`.
- If valid, attempt immediate navigation.
- Retry when `categoriesMeta` changes so `#data` and category hashes can resolve after async loading.
- Listen to `hashchange`; clean up the listener.
- Do not run hash restoration on `/wiki/*`.

- [ ] **Step 5: Add navigation component assertions**

Extend `RouteAwareCardNav.test.tsx` to assert:

```ts
expect(screen.getByRole('link', { name: '问答' })).toHaveAttribute('href', '/#chat')
```

for Wiki mode.

For main mode, mount unique `home`, `data:人物`, and `chat` targets inside `.snap-container`, click the menu’s “问答” button, and assert the scroller’s `scrollTo` receives the chat offset and the menu closes. Use the exact accessible labels already present in the component.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
npm test -- --run `
  src/navigation/mainSectionNavigation.test.ts `
  src/components/navigation/RouteAwareCardNav.test.tsx
```

Expected: both files pass.

- [ ] **Step 7: Codex batch-1 supervision gate**

Codex runs:

```powershell
git status --short
git diff --check
git diff -- `
  frontend/react-app/src/navigation/mainSectionNavigation.ts `
  frontend/react-app/src/navigation/mainSectionNavigation.test.ts `
  frontend/react-app/src/components/navigation/navigationConfig.ts `
  frontend/react-app/src/components/navigation/RouteAwareCardNav.test.tsx `
  frontend/react-app/src/App.tsx
npm test -- --run `
  src/navigation/mainSectionNavigation.test.ts `
  src/components/navigation/RouteAwareCardNav.test.tsx `
  src/App.wiki.test.tsx
```

Reject any `scrollIntoView` added to main navigation, any changed Wiki rendering code, or any file outside the whitelist.

- [ ] **Step 8: Commit accepted batch**

Only Codex runs:

```powershell
git add -- `
  frontend/react-app/src/navigation/mainSectionNavigation.ts `
  frontend/react-app/src/navigation/mainSectionNavigation.test.ts `
  frontend/react-app/src/components/navigation/navigationConfig.ts `
  frontend/react-app/src/components/navigation/RouteAwareCardNav.test.tsx `
  frontend/react-app/src/App.tsx
git commit -m "fix: unify main section navigation"
```

---

### Task 2: Flatten the Data Sequence and Unify Scroll Observation

**Kimi batch:** 2 of 4

**Files:**
- Modify: `frontend/react-app/src/components/sections/DataSection.tsx`
- Modify: `frontend/react-app/src/components/sections/DataSection.css`
- Modify: `frontend/react-app/src/styles/global.css`
- Modify: `frontend/react-app/src/components/sections/MainResponsiveCss.test.ts`
- Modify: `frontend/react-app/src/App.wheel.test.tsx`
- Modify: `frontend/react-app/src/hooks/useScrollSpy.ts`
- Modify: `frontend/react-app/src/hooks/useScrollSpy.test.tsx`
- Modify: `frontend/react-app/src/hooks/useWheelSnapNavigation.ts`
- Create: `frontend/react-app/src/hooks/useWheelSnapNavigation.test.tsx`

**Interfaces:**
- `DataSection` produces a non-scrolling group marked `data-main-data-sequence`.
- Real leaf panels keep `data-snap-section="data:{key}"`.
- Empty/loading metadata produces exactly one leaf `data-snap-section="data:loading"`.
- `.snap-container` contains the visual sequence through descendant leaf targets and is the only page-level element with `overflow-y: scroll`.
- `getMainSnapIds()` from Task 1 is the source of wheel target order.
- `useScrollSpy` observes exactly `[data-snap-section]` leaf targets and constructs `IntersectionObserver` with `.snap-container` as `root`.

- [ ] **Step 1: Update CSS contract tests to fail on the old design**

Replace the mobile proximity expectation with:

```ts
expect(globalCss).toMatch(
  /\.snap-container\s*\{[^}]*scroll-snap-type:\s*y mandatory/s,
)
expect(globalCss).toMatch(
  /\.snap-section\s*\{[^}]*scroll-snap-stop:\s*always/s,
)
expect(globalCss).not.toMatch(
  /@media \(max-width: 720px\)[\s\S]*scroll-snap-type:\s*y proximity/,
)
expect(globalCss).not.toContain('scroll-behavior: smooth')
expect(dataCss).not.toMatch(
  /\.data-section__scroll\s*\{[^}]*overflow-y:\s*(?:scroll|auto)/s,
)
expect(dataCss).not.toMatch(
  /\.data-section__scroll\s*\{[^}]*scroll-snap-type:/s,
)
```

Add a `DataSection` component assertion in `App.wheel.test.tsx`:

```ts
expect(dataScroller.scrollHeight).toBe(dataScroller.clientHeight)
expect(dataScroller).not.toHaveStyle({ overflowY: 'scroll' })
expect(document.querySelector('[data-snap-section="data"]')).toBeNull()
expect(document.querySelector('[data-snap-section="data:人物"]')).toBeInTheDocument()
```

For the pending API case, assert `data:loading` exists and is the next target after home.

- [ ] **Step 2: Run the CSS and App tests to verify failure**

Run:

```powershell
npm test -- --run `
  src/components/sections/MainResponsiveCss.test.ts `
  src/App.wheel.test.tsx
```

Expected: FAIL because mobile proximity rules and nested data overflow still exist, the parent `data` target still exists, and no `data:loading` target is rendered.

- [ ] **Step 3: Flatten `DataSection`**

Render this responsibility split:

```tsx
<section className="data-section" data-main-data-sequence>
  <div className="data-section__nav-shell">
    <nav className="data-section__nav" aria-label="资料分类">
      {/* existing buttons */}
    </nav>
  </div>
  <div className="data-section__panels" data-testid="data-section-scroll">
    {/* loading leaf or CategoryPanel leaves */}
  </div>
</section>
```

Rules:

- Remove `data-snap-section="data"` and `snap-section` from the group.
- Keep the existing test id temporarily to avoid breaking unrelated diagnostics, but it no longer denotes a scroll owner.
- When `categoriesMeta.length === 0`, render:

```tsx
<section
  className="snap-section category-panel data-section__loading-panel"
  data-snap-section="data:loading"
  aria-label="资料加载中"
>
  <p>资料加载中…</p>
</section>
```

- Category buttons call `navigateToMainSection({ kind: "data", categoryKey: c.key }, { behavior, history: "push" })`.
- Preserve existing category copy, artwork, Wiki link, and mobile poster markup.

- [ ] **Step 4: Replace nested-scroll CSS with a sticky overlay**

Implement:

```css
.data-section {
  position: relative;
}

.data-section__panels {
  overflow: visible;
}

.data-section__nav-shell {
  position: sticky;
  top: 0;
  z-index: 5;
  height: 0;
  pointer-events: none;
}

.data-section__nav {
  pointer-events: auto;
}
```

Keep desktop nav at the left-center of the viewport and mobile nav below the global nav. Do not put `overflow`, `transform`, `filter`, or `contain` on a data-sequence ancestor when it would break sticky positioning. Keep clipping inside each category panel.

In `global.css`:

- Keep `height: 100vh; height: 100dvh`.
- Keep `overflow-y: scroll`.
- Keep `scroll-snap-type: y mandatory`.
- Remove container-wide `scroll-behavior: smooth`.
- Keep every `.snap-section` at `scroll-snap-stop: always`.
- Delete the phone override that changes either property.

- [ ] **Step 5: Root `ScrollSpy` in the main container**

Construct:

```ts
const root = document.querySelector<HTMLElement>('.snap-container')
if (!root) return

const observer = new IntersectionObserver(callback, {
  root,
  threshold: [0.5, 0.75],
})
```

Observe leaf targets returned under the root. Ignore `data:loading` for category selection but set `currentSection` to `data` and `currentCategory` to `null`. Preserve MutationObserver support for async categories and disconnect both observers on cleanup.

Update the test’s IntersectionObserver stub to capture constructor options and assert `options.root === scroller`.

- [ ] **Step 6: Share flat target order with wheel navigation**

Replace local document-wide target discovery with `getMainSnapIds(scroller)` plus exact element resolution inside the scroller. The sequence must be:

```text
home → data:loading or every data:{key} → chat
```

Do not restore a synthetic `data` parent target. Preserve:

- delta threshold;
- ctrl-wheel bypass;
- one-page lock;
- nested `[data-page-wheel-lock="true"]` priority;
- fallback to closest visible leaf when Zustand state is stale.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
npm test -- --run `
  src/components/sections/MainResponsiveCss.test.ts `
  src/hooks/useScrollSpy.test.tsx `
  src/App.wheel.test.tsx `
  src/components/sections/CategoryPanel.test.tsx
```

Expected: all files pass.

- [ ] **Step 8: Codex batch-2 supervision gate**

Codex checks:

```powershell
git status --short
git diff --check
rg -n "overflow-y:\\s*(scroll|auto)|scroll-snap-type" `
  frontend/react-app/src/components/sections/DataSection.css
rg -n "data-snap-section=\"data\"" `
  frontend/react-app/src
npm test -- --run `
  src/components/sections/MainResponsiveCss.test.ts `
  src/hooks/useScrollSpy.test.tsx `
  src/App.wheel.test.tsx `
  src/components/sections/CategoryPanel.test.tsx `
  src/components/navigation/RouteAwareCardNav.test.tsx
```

Expected:

- no nested vertical data scroll owner;
- no parent `data` snap target;
- one flat ordered target list;
- all focused tests pass.

- [ ] **Step 9: Commit accepted batch**

Only Codex stages the exact changed Task 2 files and runs:

```powershell
git commit -m "fix: flatten main data scroll sequence"
```

---

### Task 3: Chat Boundary Gesture and Viewport Realignment

**Kimi batch:** 3 of 4

**Files:**
- Create: `frontend/react-app/src/hooks/useMainViewportAlignment.ts`
- Create: `frontend/react-app/src/hooks/useMainViewportAlignment.test.tsx`
- Create: `frontend/react-app/src/hooks/useChatPageBoundaryNavigation.ts`
- Create: `frontend/react-app/src/hooks/useChatPageBoundaryNavigation.test.tsx`
- Modify: `frontend/react-app/src/App.tsx`
- Modify: `frontend/react-app/src/components/sections/ChatSection.tsx`
- Modify: `frontend/react-app/src/components/sections/ChatSection.css`
- Modify: `frontend/react-app/src/components/sections/ChatSection.test.tsx`

**Interfaces:**
- Produces:

```ts
export function useMainViewportAlignment(
  scrollerRef: React.RefObject<HTMLElement>,
  activeSnapId: MainSnapId,
  delayMs?: number,
): void

export const CHAT_PAGE_GESTURE_THRESHOLD_PX = 64

export function useChatPageBoundaryNavigation(
  messageRef: React.RefObject<HTMLElement>,
  thresholdPx?: number,
): void
```

- Viewport alignment listens to `window.resize` and optional `window.visualViewport.resize`, debounces to one callback, and calls:

```ts
navigateToMainSection(mainSnapIdToTarget(activeSnapId), {
  behavior: 'auto',
  history: 'none',
})
```

- It never reads or writes `.chat-section__messages.scrollTop`.
- Chat boundary navigation triggers only when:
  - touch starts with `messageRef.current.scrollTop <= 1`;
  - finger movement is downward by at least 64 CSS pixels;
  - horizontal movement is smaller than vertical movement;
  - the gesture has not already triggered.
- It navigates to the leaf snap target immediately preceding `chat` in `getMainSnapIds()`, with smooth/auto motion policy and `history: "replace"`.
- A gesture at the bottom, in the wrong direction, under threshold, or while chat can still scroll toward the top does nothing.

- [ ] **Step 1: Write failing viewport-alignment tests**

Use a small harness with a `.snap-container`, `home`, `data:人物`, and `chat`. Stub `scrollTo`, fake timers, and a controllable `visualViewport` EventTarget.

Assert:

```ts
window.dispatchEvent(new Event('resize'))
vi.advanceTimersByTime(119)
expect(scrollTo).not.toHaveBeenCalled()
vi.advanceTimersByTime(1)
expect(scrollTo).toHaveBeenCalledWith({ top: expectedChatTop, behavior: 'auto' })
```

Dispatch several resize events inside the debounce window and expect one call. Dispatch `visualViewport.resize` and expect alignment. Unmount and verify later resize events do nothing.

Set chat messages to `scrollTop = 321`; after alignment assert it remains `321`.

- [ ] **Step 2: Write failing chat-boundary tests**

Render a message element with controllable `scrollTop`, `scrollHeight`, and `clientHeight`. Dispatch:

```ts
fireEvent.touchStart(messages, {
  touches: [{ clientX: 120, clientY: 200 }],
})
fireEvent.touchMove(messages, {
  touches: [{ clientX: 122, clientY: 270 }],
})
fireEvent.touchEnd(messages)
```

At `scrollTop = 0`, expect one navigation to the preceding data target. Repeat `touchMove` and `touchEnd` during the same gesture and still expect one call.

Also assert no navigation for:

- `scrollTop = 40`;
- movement from `clientY: 200` to `150`;
- movement from `200` to `250`;
- horizontal movement larger than vertical movement;
- a touch cancel;
- chat as the only target;
- movement beginning at the bottom.

- [ ] **Step 3: Run new hook tests and verify failure**

Run:

```powershell
npm test -- --run `
  src/hooks/useMainViewportAlignment.test.tsx `
  src/hooks/useChatPageBoundaryNavigation.test.tsx
```

Expected: FAIL because both hook modules do not exist.

- [ ] **Step 4: Implement viewport alignment**

Use one timer ref. On each relevant event:

```ts
if (timer !== null) window.clearTimeout(timer)
timer = window.setTimeout(align, delayMs)
```

Use `activeSnapId` captured from the latest effect render. Clean up the timeout and both listeners. Do not align on ordinary scroll events.

In `App.tsx`, derive the active ID:

```ts
const activeSnapId: MainSnapId =
  currentSection === 'data'
    ? currentCategory
      ? `data:${currentCategory}`
      : 'data:loading'
    : currentSection
```

Call the hook with `snapContainerRef`.

- [ ] **Step 5: Implement touch-boundary arbitration**

Use native `touchstart`, `touchmove`, `touchend`, and `touchcancel` listeners on the message element. Keep listeners passive because navigation occurs after threshold detection and no normal chat scroll is prevented.

Track:

```ts
type GestureState = {
  startX: number
  startY: number
  eligible: boolean
  triggered: boolean
}
```

On touch move, compute `deltaX` and `deltaY`. Trigger once when `eligible`, `deltaY >= thresholdPx`, and `Math.abs(deltaY) > Math.abs(deltaX)`.

In `ChatSection.tsx`:

- Pass `scrollRef` to the hook.
- Replace `jumpHome`’s `scrollIntoView` with `navigateToMainSection({ kind: "home" }, { behavior, history: "push" })`.
- Keep message auto-scroll on appended messages.
- Keep `data-page-wheel-lock="true"`.

- [ ] **Step 6: Preserve one-screen chat layout**

Verify CSS retains:

```css
.chat-section {
  display: flex;
  flex-direction: column;
}

.chat-section__message-shell {
  flex: 1;
  min-height: 0;
}

.chat-section__messages {
  height: 100%;
  overflow-y: auto;
}
```

Do not add page-level overflow to `.chat-section`. Preserve safe-area input padding.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
npm test -- --run `
  src/hooks/useMainViewportAlignment.test.tsx `
  src/hooks/useChatPageBoundaryNavigation.test.tsx `
  src/components/sections/ChatSection.test.tsx `
  src/App.wheel.test.tsx
```

Expected: all files pass.

- [ ] **Step 8: Codex batch-3 supervision gate**

Codex reviews listener cleanup, touch direction, threshold, no `preventDefault`, no chat `scrollTop` mutation in viewport alignment, and no new page scroll owner.

Run:

```powershell
git status --short
git diff --check
npm test -- --run `
  src/hooks/useMainViewportAlignment.test.tsx `
  src/hooks/useChatPageBoundaryNavigation.test.tsx `
  src/components/sections/ChatSection.test.tsx `
  src/App.wheel.test.tsx `
  src/components/chat/ChatInput.test.tsx
```

- [ ] **Step 9: Commit accepted batch**

Only Codex stages the exact Task 3 files and runs:

```powershell
git commit -m "fix: stabilize chat and viewport scroll boundaries"
```

---

### Task 4: Browser Regression Matrix and Final Verification

**Kimi batch:** 4 of 4

**Files:**
- Modify: `frontend/react-app/e2e/main-mobile-responsive.spec.ts`
- Modify only when an E2E-discovered defect requires an in-spec correction: previously approved implementation files from Tasks 1–3.

**Interfaces:**
- Consumes all Task 1–3 contracts.
- Produces executable browser evidence for flat sequence geometry, semantic URLs, viewport recovery, chat scroll isolation, touch-boundary navigation, and history restoration.

- [ ] **Step 1: Add a bounded geometry helper**

Add:

```ts
async function mainScrollState(page: Page) {
  return page.locator('.snap-container').evaluate((scroller) => ({
    clientHeight: scroller.clientHeight,
    scrollHeight: scroller.scrollHeight,
    scrollTop: scroller.scrollTop,
    targets: [...scroller.querySelectorAll<HTMLElement>('[data-snap-section]')]
      .map((element) => {
        const scrollerRect = scroller.getBoundingClientRect()
        const targetRect = element.getBoundingClientRect()
        return {
          id: element.dataset.snapSection,
          top: targetRect.top - scrollerRect.top + scroller.scrollTop,
          height: targetRect.height,
        }
      }),
  }))
}
```

Use it to assert, for three mocked categories:

```ts
expect(state.targets.map((item) => item.id)).toEqual([
  'home',
  'data:人物',
  'data:心相',
  'data:剧情',
  'chat',
])
expect(state.scrollHeight).toBe(state.clientHeight * 5)
```

Allow at most one physical pixel of rounding tolerance.

- [ ] **Step 2: Replace direct-jump-only coverage with sequence assertions**

Keep direct semantic jump helpers for setup, but add a test that advances one target at a time and asserts the visible target after every transition. In Chromium mobile, issue a large wheel/scroll gesture from the main viewport and assert it cannot go from `home` directly to `chat`.

Do not claim synthetic DOM events prove native inertia. Name the test according to the mechanism it actually uses. The final manual Browser validation will cover a real mobile-like scroll gesture.

- [ ] **Step 3: Add navigation and history coverage**

Cover:

1. `page.goto('/#chat')` lands with chat top within one pixel of the scroller top;
2. reload preserves chat;
3. main menu “资料” lands on `data:人物`;
4. main menu “问答” lands on chat and URL ends in `#chat`;
5. navigate to `/wiki/character`, open Wiki nav, click “问答”, and arrive at `/#chat`;
6. browser back returns to the previous semantic URL and aligned page.

Use accessible names from a fresh rendered page and verify locator uniqueness before interaction.

- [ ] **Step 4: Add resize and keyboard-height coverage**

At `390×844`, navigate to `data:心相`, resize to `390×568`, and assert the same target is aligned after the debounce. Repeat for chat and assert:

- chat top is within one pixel of main scroller top;
- data bottom does not enter the visible viewport;
- message `scrollTop` remains unchanged;
- input row remains within `visualViewport.height`.

- [ ] **Step 5: Add chat local-scroll and boundary coverage**

Populate enough messages for overflow. Verify:

- changing message `scrollTop` does not change main `scrollTop`;
- ordinary upward/downward chat scrolling does not leave chat;
- a top-boundary touch sequence exceeding 64px returns to `data:剧情`;
- a 50px sequence does not return;
- bottom-boundary forward intent leaves main scroll at chat.

Use `locator.dispatchEvent` only to test the application’s touch-boundary hook. Keep the geometry/scroll-snap assertions separate.

- [ ] **Step 6: Run the focused E2E matrix**

Start Vite in the worktree and run:

```powershell
npx playwright test e2e/main-mobile-responsive.spec.ts `
  --project=desktop `
  --project=mobile `
  --project=mobile-webkit
```

Expected: all main responsive tests pass in all selected projects.

- [ ] **Step 7: Codex browser supervision**

Codex independently starts the worktree app and validates at least:

- 390×844 home → first data panel;
- every data panel appears in order;
- a strong initial scroll does not land directly on chat;
- chat message scrolling remains local;
- chat top-boundary deliberate drag returns one panel;
- 390×844 → 390×568 keeps chat aligned;
- Wiki “问答” arrives at `/#chat`.

Record DOM geometry before and after resize. A screenshot alone is insufficient for scroll ownership.

- [ ] **Step 8: Run complete verification**

Codex runs:

```powershell
npm test
npm run build
npx playwright test e2e/main-mobile-responsive.spec.ts `
  --project=desktop `
  --project=mobile `
  --project=mobile-webkit
git diff --check
git status --short
```

Expected:

- 51 existing plus new Vitest files all pass;
- production build succeeds;
- selected Playwright matrix passes;
- no whitespace errors;
- changed files are within the approved whitelist;
- no generated reports, screenshots, dependency changes, or runtime files are staged.

- [ ] **Step 9: Commit browser coverage**

Only Codex stages the E2E file and any approved Task 4 correction files:

```powershell
git commit -m "test: cover main scroll and navigation regressions"
```

- [ ] **Step 10: Final branch handoff**

Codex reports:

- worktree and branch;
- accepted commit list;
- exact Vitest/build/Playwright results;
- manual browser geometry evidence;
- any remaining platform limitation;
- confirmation that `D:\1999Wiki` main checkout was not modified by implementation;
- integration options, without merging or pushing until the user chooses.
