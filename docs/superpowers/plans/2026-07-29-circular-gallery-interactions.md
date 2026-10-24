# Circular Gallery Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the chat image gallery’s full-screen close control unobstructed, keep navigation buttons stationary, and add natural Shift-wheel, touchpad, and touch-drag navigation with distance-aware linear snapping.

**Architecture:** Keep gallery state local to `CircularGallery`, extract swipe target and duration calculations into a pure helper module, and render the full-screen viewer through a body-level React Portal. Pointer Events drive a temporary pixel offset across the existing previous/current/next DOM slots; release animates that offset to a measured slot center before committing the new index.

**Tech Stack:** React 18, TypeScript 5.5, CSS custom properties, Vitest, Testing Library, Playwright.

## Global Constraints

- Execute all implementation work in a new `codex/circular-gallery-interactions` branch and a dedicated Git worktree.
- Do not modify, delete, stage, or move unrelated files from `D:\1999Wiki`.
- Desktop image navigation uses `Shift + wheel`; `Ctrl + wheel` remains browser zoom.
- Native touchpad horizontal scrolling navigates images; ordinary vertical scrolling remains available to the page.
- Touch dragging follows the pointer and snaps with a distance-derived `180ms`–`420ms` linear animation.
- `prefers-reduced-motion: reduce` removes the post-release animation.
- Previous and next controls retain fixed viewport positions when the caption changes.
- The full-screen viewer must escape ancestor stacking contexts and the close control must remain hit-testable below the fixed navigation bar.

## Execution Prerequisite: Isolated Worktree

Run from `D:\1999Wiki` after this plan has been committed:

```powershell
git worktree add "D:\1999Wiki\.worktrees\circular-gallery-interactions" -b "codex/circular-gallery-interactions" HEAD
git -C "D:\1999Wiki\.worktrees\circular-gallery-interactions" status --short --branch
```

Expected: the second command reports branch `codex/circular-gallery-interactions` and no implementation changes. Run every remaining command from `D:\1999Wiki\.worktrees\circular-gallery-interactions`.

## File Structure

- Create `frontend/react-app/src/components/animations/reactbits/circularGalleryMotion.ts`: pure swipe target, boundary, resistance, and snap-duration calculations.
- Create `frontend/react-app/src/components/animations/reactbits/circularGalleryMotion.test.ts`: literal boundary cases for the pure calculations.
- Modify `frontend/react-app/src/components/animations/reactbits/CircularGallery.tsx`: Pointer Events, wheel/keyboard routing, stable controls, Portal viewer, and focus cleanup.
- Modify `frontend/react-app/src/components/animations/reactbits/CircularGallery.css`: drag offset variables, linear snapping, fixed side controls, caption layout, safe full-screen geometry, and reduced motion.
- Modify `frontend/react-app/src/components/animations/reactbits/CircularGallery.test.tsx`: observable component behavior for wheel, pointer, controls, Portal, focus, and boundaries.
- Modify `frontend/react-app/src/components/chat/CircularMediaGallery.test.tsx`: retain the integration contract through the wrapper.
- Create `frontend/react-app/e2e/circular-gallery-interactions.spec.ts`: deterministic desktop and mobile geometry, hit testing, wheel, and drag verification with mocked SSE media.

---

### Task 1: Pure Swipe and Snap Policy

**Files:**
- Create: `frontend/react-app/src/components/animations/reactbits/circularGalleryMotion.ts`
- Create: `frontend/react-app/src/components/animations/reactbits/circularGalleryMotion.test.ts`

**Interfaces:**
- Produces:
  - `resolveGalleryTarget(input: GalleryReleaseInput): number`
  - `applyEdgeResistance(offsetPx: number, currentIndex: number, itemCount: number): number`
  - `calculateGallerySnapDuration(distancePx: number, reducedMotion: boolean): number`
  - `GalleryReleaseInput` with `currentIndex`, `itemCount`, `offsetPx`, `stepPx`, and `velocityPxPerMs`.

- [ ] **Step 1: Write failing policy tests with hand-derived literals**

Create `circularGalleryMotion.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import {
  applyEdgeResistance,
  calculateGallerySnapDuration,
  resolveGalleryTarget,
} from './circularGalleryMotion'

describe('resolveGalleryTarget', () => {
  it.each([
    [{ currentIndex: 2, itemCount: 5, offsetPx: -130, stepPx: 400, velocityPxPerMs: -0.1 }, 3],
    [{ currentIndex: 2, itemCount: 5, offsetPx: 130, stepPx: 400, velocityPxPerMs: 0.1 }, 1],
    [{ currentIndex: 2, itemCount: 5, offsetPx: -40, stepPx: 400, velocityPxPerMs: -0.6 }, 3],
    [{ currentIndex: 2, itemCount: 5, offsetPx: 40, stepPx: 400, velocityPxPerMs: 0.6 }, 1],
    [{ currentIndex: 2, itemCount: 5, offsetPx: -40, stepPx: 400, velocityPxPerMs: -0.1 }, 2],
    [{ currentIndex: 0, itemCount: 5, offsetPx: 180, stepPx: 400, velocityPxPerMs: 0.8 }, 0],
    [{ currentIndex: 4, itemCount: 5, offsetPx: -180, stepPx: 400, velocityPxPerMs: -0.8 }, 4],
    [{ currentIndex: 0, itemCount: 0, offsetPx: -180, stepPx: 400, velocityPxPerMs: -0.8 }, 0],
  ])('selects the bounded target for %#', (input, expected) => {
    expect(resolveGalleryTarget(input)).toBe(expected)
  })
})

describe('applyEdgeResistance', () => {
  it('damps outward movement at each boundary without damping inward movement', () => {
    expect(applyEdgeResistance(120, 0, 4)).toBe(42)
    expect(applyEdgeResistance(-120, 0, 4)).toBe(-120)
    expect(applyEdgeResistance(-120, 3, 4)).toBe(-42)
    expect(applyEdgeResistance(120, 3, 4)).toBe(120)
  })
})

describe('calculateGallerySnapDuration', () => {
  it('clamps distance-derived duration and disables it for reduced motion', () => {
    expect(calculateGallerySnapDuration(30, false)).toBe(180)
    expect(calculateGallerySnapDuration(360, false)).toBe(240)
    expect(calculateGallerySnapDuration(900, false)).toBe(420)
    expect(calculateGallerySnapDuration(360, true)).toBe(0)
  })
})
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```powershell
npm test -- --run src/components/animations/reactbits/circularGalleryMotion.test.ts
```

Expected: FAIL because `./circularGalleryMotion` does not exist.

- [ ] **Step 3: Implement the minimal pure policy**

Create `circularGalleryMotion.ts`:

```ts
export interface GalleryReleaseInput {
  currentIndex: number
  itemCount: number
  offsetPx: number
  stepPx: number
  velocityPxPerMs: number
}

const DISTANCE_RATIO = 0.25
const FLICK_VELOCITY = 0.45
const EDGE_RESISTANCE = 0.35

export function resolveGalleryTarget({
  currentIndex,
  itemCount,
  offsetPx,
  stepPx,
  velocityPxPerMs,
}: GalleryReleaseInput): number {
  if (itemCount <= 0) return 0
  const distanceIntent = Math.abs(offsetPx) >= Math.max(1, stepPx) * DISTANCE_RATIO
  const velocityIntent = Math.abs(velocityPxPerMs) >= FLICK_VELOCITY
  const direction = distanceIntent || velocityIntent ? (offsetPx < 0 || velocityPxPerMs < -FLICK_VELOCITY ? 1 : -1) : 0
  return Math.min(itemCount - 1, Math.max(0, currentIndex + direction))
}

export function applyEdgeResistance(offsetPx: number, currentIndex: number, itemCount: number): number {
  const beyondStart = currentIndex <= 0 && offsetPx > 0
  const beyondEnd = currentIndex >= itemCount - 1 && offsetPx < 0
  return beyondStart || beyondEnd ? offsetPx * EDGE_RESISTANCE : offsetPx
}

export function calculateGallerySnapDuration(distancePx: number, reducedMotion: boolean): number {
  if (reducedMotion) return 0
  return Math.min(420, Math.max(180, Math.round(Math.abs(distancePx) / 1.5)))
}
```

- [ ] **Step 4: Run policy tests and verify GREEN**

Run:

```powershell
npm test -- --run src/components/animations/reactbits/circularGalleryMotion.test.ts
```

Expected: all policy tests PASS.

- [ ] **Step 5: Commit the policy**

```powershell
git add frontend/react-app/src/components/animations/reactbits/circularGalleryMotion.ts frontend/react-app/src/components/animations/reactbits/circularGalleryMotion.test.ts
git commit -m "feat: define gallery swipe policy"
```

---

### Task 2: Wheel, Keyboard, and Pointer Navigation

**Files:**
- Modify: `frontend/react-app/src/components/animations/reactbits/CircularGallery.tsx`
- Modify: `frontend/react-app/src/components/animations/reactbits/CircularGallery.test.tsx`

**Interfaces:**
- Consumes:
  - `resolveGalleryTarget(input: GalleryReleaseInput): number`
  - `applyEdgeResistance(offsetPx, currentIndex, itemCount): number`
  - `calculateGallerySnapDuration(distancePx, reducedMotion): number`
- Produces:
  - `.circular-gallery__viewport[tabindex="0"]`
  - `data-gallery-dragging="true|false"` and `data-gallery-snapping="true|false"` on the gallery root
  - CSS variables `--gallery-drag-offset` and `--gallery-snap-duration`.

- [ ] **Step 1: Add failing wheel and keyboard behavior tests**

Append tests that:

```ts
it('uses Shift-wheel and horizontal touchpad intent without consuming zoom or vertical scroll', () => {
  const { container } = render(<CircularGallery items={items.slice(0, 4)} bend={0} borderRadius={0.1} />)
  const viewport = container.querySelector('.circular-gallery__viewport')!

  fireEvent.wheel(viewport, { shiftKey: true, deltaY: 120 })
  expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')

  const ctrlWheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, ctrlKey: true, deltaY: 120 })
  expect(viewport.dispatchEvent(ctrlWheel)).toBe(true)
  expect(ctrlWheel.defaultPrevented).toBe(false)

  const verticalWheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 120 })
  expect(viewport.dispatchEvent(verticalWheel)).toBe(true)
  expect(verticalWheel.defaultPrevented).toBe(false)

  fireEvent.keyDown(viewport, { key: 'ArrowRight' })
  expect(screen.getByRole('img', { name: 'Alt 2' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
  fireEvent.keyDown(viewport, { key: 'ArrowLeft' })
  expect(screen.getByRole('img', { name: 'Alt 1' }).closest('[data-gallery-position]')).toHaveAttribute('data-gallery-position', 'current')
})
```

Reset the fake performance clock or wheel lock between wheel operations so each assertion observes a separate gesture.

- [ ] **Step 2: Run the component test and verify RED**

Run:

```powershell
npm test -- --run src/components/animations/reactbits/CircularGallery.test.tsx
```

Expected: FAIL because Shift-wheel and arrow-key routing are not implemented.

- [ ] **Step 3: Implement wheel and keyboard routing**

Change wheel handling to this decision order:

```ts
if (event.ctrlKey) return
const horizontalDelta = Math.abs(event.deltaX) > Math.abs(event.deltaY)
  ? event.deltaX
  : event.shiftKey
    ? event.deltaY
    : 0
if (horizontalDelta === 0) return
event.preventDefault()
// existing 260ms lock, then moveTo(safeIndex + Math.sign(horizontalDelta))
```

Make the viewport focusable and route `ArrowLeft`/`ArrowRight` through `moveTo`, calling `preventDefault()` only for those two keys.

- [ ] **Step 4: Verify wheel and keyboard GREEN**

Run the same focused Vitest command. Expected: PASS.

- [ ] **Step 5: Add failing pointer drag tests**

Add a test that stubs the current and next slide rectangles 400px apart, fires `pointerDown`, `pointerMove` from `clientX: 300` to `clientX: 160`, and asserts:

```ts
expect(container.querySelector('.circular-gallery')).toHaveAttribute('data-gallery-dragging', 'true')
expect(viewport).toHaveStyle({ '--gallery-drag-offset': '-140px' })
```

After `pointerUp`, assert snapping is active; fire a `transitionEnd` with `propertyName: 'transform'` from the previously current slide and assert that `Alt 1` is current. Add separate tests for:

- a 40px slow drag returning to `Alt 0`;
- an outward first-slide drag exposing a resisted `42px` offset from a raw `120px`;
- reduced motion committing the target immediately without `data-gallery-snapping="true"`;
- `pointerCancel` clearing the transient offset without changing index.

- [ ] **Step 6: Run pointer tests and verify RED**

Run:

```powershell
npm test -- --run src/components/animations/reactbits/CircularGallery.test.tsx
```

Expected: the new pointer tests FAIL because the component has no pointer handlers or drag state.

- [ ] **Step 7: Implement the minimal pointer state machine**

Use a ref with:

```ts
interface DragSample {
  pointerId: number
  startX: number
  lastX: number
  lastTime: number
  velocityPxPerMs: number
  stepPx: number
}
```

On pointer down, measure the center distance between the current slide and the available adjacent slide, capture the pointer, and initialize the sample. On move, update velocity using the last sample and set `dragOffset` through `applyEdgeResistance`. On release:

1. Resolve the bounded target with `resolveGalleryTarget`.
2. If unchanged, animate from the current offset to `0`.
3. If changed, animate to `-stepPx` for next or `stepPx` for previous.
4. Calculate duration from the remaining pixel distance.
5. On the current slide’s transform transition end, commit the target index, disable transition, and reset the offset to `0`.
6. With reduced motion, commit and reset immediately.

On pointer cancel, reset to the current center. Guard `setPointerCapture`/`releasePointerCapture` for JSDOM compatibility.

- [ ] **Step 8: Run all gallery component tests and verify GREEN**

Run:

```powershell
npm test -- --run src/components/animations/reactbits/circularGalleryMotion.test.ts src/components/animations/reactbits/CircularGallery.test.tsx src/components/chat/CircularMediaGallery.test.tsx
```

Expected: all focused tests PASS without warnings.

- [ ] **Step 9: Commit input interactions**

```powershell
git add frontend/react-app/src/components/animations/reactbits/CircularGallery.tsx frontend/react-app/src/components/animations/reactbits/CircularGallery.test.tsx
git commit -m "feat: add natural gallery navigation"
```

---

### Task 3: Stable Controls and Body-Level Viewer

**Files:**
- Modify: `frontend/react-app/src/components/animations/reactbits/CircularGallery.tsx`
- Modify: `frontend/react-app/src/components/animations/reactbits/CircularGallery.css`
- Modify: `frontend/react-app/src/components/animations/reactbits/CircularGallery.test.tsx`
- Modify: `frontend/react-app/src/components/chat/CircularMediaGallery.test.tsx`

**Interfaces:**
- Produces:
  - `.circular-gallery__previous` and `.circular-gallery__next` as fixed side controls.
  - `.circular-gallery__caption` containing the title, index, and full-screen opener.
  - `.circular-gallery__lightbox` mounted as a direct `document.body` child through `createPortal`.

- [ ] **Step 1: Add failing structure and Portal tests**

Add component assertions:

```ts
const previous = screen.getByRole('button', { name: '上一张图片' })
const next = screen.getByRole('button', { name: '下一张图片' })
expect(previous).toHaveClass('circular-gallery__previous')
expect(next).toHaveClass('circular-gallery__next')
expect(previous.parentElement).toHaveClass('circular-gallery__viewport')
expect(next.parentElement).toHaveClass('circular-gallery__viewport')
expect(screen.getByText('Image 0')).toHaveClass('circular-gallery__title')
```

After opening the viewer:

```ts
const dialog = screen.getByRole('dialog', { name: 'Image 0' })
expect(dialog.parentElement).toBe(document.body)
expect(dialog).toContainElement(within(dialog).getByRole('button', { name: 'Close image viewer' }))
```

Keep the existing Escape and focus-restoration assertions. Add a `CircularMediaGallery.test.tsx` assertion that opening through the wrapper also creates a body-level dialog.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
npm test -- --run src/components/animations/reactbits/CircularGallery.test.tsx src/components/chat/CircularMediaGallery.test.tsx
```

Expected: FAIL because controls are in one flex group and the dialog remains inside the gallery.

- [ ] **Step 3: Implement the stable markup and Portal**

Import `createPortal` from `react-dom`. Render previous and next controls as children of the viewport, render the caption separately, and wrap the dialog expression:

```tsx
{viewerOpen && items[safeIndex] && createPortal(
  <div className="circular-gallery__lightbox" role="dialog" aria-modal="true" aria-label={items[safeIndex].title}>
    <button className="circular-gallery__lightbox-close" type="button" onClick={() => setViewerOpen(false)} aria-label="Close image viewer">
      <X aria-hidden="true" />
    </button>
    <img src={items[safeIndex].image} alt={items[safeIndex].alt} />
  </div>,
  document.body,
)}
```

Preserve overlay click-to-close by checking `event.target === event.currentTarget`.

- [ ] **Step 4: Implement layout and motion CSS**

Apply these layout contracts:

```css
.circular-gallery__viewport {
  touch-action: pan-y;
  cursor: grab;
}

.circular-gallery[data-gallery-dragging="true"] .circular-gallery__viewport {
  cursor: grabbing;
}

.circular-gallery__slide {
  --gallery-slot-offset: 0px;
  transform: translateX(calc(-50% + var(--gallery-slot-offset) + var(--gallery-drag-offset, 0px))) scale(var(--gallery-slot-scale, .72));
  transition-duration: var(--gallery-snap-duration, 480ms);
  transition-timing-function: linear;
}

.circular-gallery__previous,
.circular-gallery__next {
  position: absolute;
  z-index: 7;
  top: 50%;
  width: 44px;
  height: 44px;
  transform: translateY(-50%);
}

.circular-gallery__previous { left: clamp(8px, 3vw, 24px); }
.circular-gallery__next { right: clamp(8px, 3vw, 24px); }

.circular-gallery__caption {
  position: absolute;
  right: 8px;
  bottom: 4px;
  left: 8px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
}

.circular-gallery__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

Express previous/next slot positions through `--gallery-slot-offset` while preserving their existing masks, opacity, and scale. Remove the old centered controls flex rules.

Use body-level viewer geometry:

```css
.circular-gallery__lightbox {
  z-index: 10000;
  padding: max(92px, calc(env(safe-area-inset-top, 0px) + 76px)) 24px 24px;
}

.circular-gallery__lightbox-close {
  top: max(84px, calc(env(safe-area-inset-top, 0px) + 76px));
  right: max(16px, env(safe-area-inset-right, 0px));
}

.circular-gallery__lightbox img {
  max-height: calc(100dvh - max(116px, calc(env(safe-area-inset-top, 0px) + 100px)));
}
```

In reduced motion, force `--gallery-snap-duration: 0ms`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the same focused Vitest command. Expected: PASS.

- [ ] **Step 6: Build to catch TypeScript and CSS integration errors**

Run:

```powershell
npm run build
```

Expected: TypeScript and Vite complete with exit code 0.

- [ ] **Step 7: Commit viewer and layout**

```powershell
git add frontend/react-app/src/components/animations/reactbits/CircularGallery.tsx frontend/react-app/src/components/animations/reactbits/CircularGallery.css frontend/react-app/src/components/animations/reactbits/CircularGallery.test.tsx frontend/react-app/src/components/chat/CircularMediaGallery.test.tsx
git commit -m "fix: stabilize gallery controls and viewer"
```

---

### Task 4: Deterministic Desktop and Mobile Regression Coverage

**Files:**
- Create: `frontend/react-app/e2e/circular-gallery-interactions.spec.ts`

**Interfaces:**
- Consumes the public DOM and accessible labels from Tasks 2–3.
- Produces Playwright evidence for desktop, narrow, mobile, mobile-webkit, and reduced-motion projects.

- [ ] **Step 1: Write the deterministic mocked gallery fixture**

In the new spec, install routes for categories, conversations, and `/api/ask/stream`. Return a `done` SSE event with three complete `AssetItem` objects whose `url` values are SVG data URLs and whose alt text lengths differ substantially:

```ts
const assets = [
  { asset_id: 'one', role: 'image', alt: '短标题', url: svgDataUrl('#8a4b2a', '1') },
  { asset_id: 'two', role: 'image', alt: '这是一个用于验证按钮不会跟随文件名移动的非常长的图片标题', url: svgDataUrl('#365f57', '2') },
  { asset_id: 'three', role: 'image', alt: '第三张', url: svgDataUrl('#65507c', '3') },
]
```

The fixture must navigate to `[data-snap-section="chat"]`, submit a question, and wait for `.circular-gallery`.

- [ ] **Step 2: Add failing desktop geometry and wheel assertions**

For the `desktop` project:

1. Record previous and next button bounding boxes.
2. Click next and assert the long caption is current.
3. Re-read button boxes and assert their `x` and `y` values differ by no more than 1px.
4. Hold Shift, call `page.mouse.wheel(0, -120)`, release Shift, and assert the previous image becomes current.
5. Dispatch a cancelable `WheelEvent` with `ctrlKey: true` in the viewport and assert both `defaultPrevented === false` and the current image is unchanged.
6. Open the viewer, assert the dialog is a direct body child, and use `document.elementFromPoint()` at the close button center to prove the close button is the hit target.
7. Compare the navigation bar and close button rectangles and assert the close button starts below the bar’s bottom edge.

- [ ] **Step 3: Add failing mobile drag and snap assertions**

For `mobile` and `mobile-webkit`:

1. Obtain the current slide bounding box.
2. Drag from 70% to 25% of its width with 10 steps.
3. Assert the second image becomes `aria-current="true"`.
4. Poll until `--gallery-drag-offset` is `0px`.
5. Assert the current slide center is within 1px of the viewport center.
6. Capture a screenshot named `circular-gallery-mobile-snapped.png`.

For `reduced-motion`, perform the same drag and assert computed transition duration is `0s`.

- [ ] **Step 4: Run the new spec and verify RED against the pre-change commit**

Before applying Tasks 2–3, or by temporarily checking the test against their parent commit, run:

```powershell
npx playwright test e2e/circular-gallery-interactions.spec.ts --project=desktop --project=mobile
```

Expected: failures identify moving controls, missing Shift-wheel/touch drag behavior, or the trapped viewer.

- [ ] **Step 5: Run the completed E2E matrix and verify GREEN**

With Tasks 2–3 restored:

```powershell
npx playwright test e2e/circular-gallery-interactions.spec.ts --project=desktop --project=narrow --project=mobile --project=mobile-webkit --project=reduced-motion
```

Expected: all applicable tests PASS and the mobile screenshot artifact is generated.

- [ ] **Step 6: Commit regression coverage**

```powershell
git add frontend/react-app/e2e/circular-gallery-interactions.spec.ts
git commit -m "test: cover gallery interactions across viewports"
```

---

### Task 5: Full Verification and Visual Review

**Files:**
- Verify only; modify files only if a failing check exposes a scoped gallery defect, then repeat the relevant RED/GREEN cycle.

**Interfaces:**
- Consumes all deliverables from Tasks 1–4.
- Produces fresh evidence that the branch satisfies the design without unrelated regressions.

- [ ] **Step 1: Run the complete frontend unit suite**

```powershell
npm test
```

Expected: all Vitest tests PASS with zero failures.

- [ ] **Step 2: Run the production build**

```powershell
npm run build
```

Expected: `tsc` and `vite build` exit 0.

- [ ] **Step 3: Run focused desktop/mobile Playwright coverage**

```powershell
npx playwright test e2e/circular-gallery-interactions.spec.ts e2e/main-mobile-responsive.spec.ts --project=desktop --project=mobile --project=mobile-webkit
```

Expected: all applicable Playwright tests PASS.

- [ ] **Step 4: Inspect generated screenshots**

Open the desktop and mobile screenshots and verify:

- side buttons are visually aligned with the image viewport;
- the long caption is truncated without moving buttons;
- the close control is below the fixed bar and visibly clickable;
- the snapped mobile image is centered;
- no horizontal page overflow appears at 390×844, 900×900, or 1440×900.

- [ ] **Step 5: Audit scope and worktree state**

```powershell
git status --short
git diff --stat main...HEAD
git diff --check main...HEAD
git log --oneline --decorate main..HEAD
```

Expected: only the files listed in this plan are changed, `git diff --check` is clean, and the implementation commits are present on `codex/circular-gallery-interactions`.

- [ ] **Step 6: Request code review before integration**

Invoke `superpowers:requesting-code-review`, address any scoped findings through new failing tests, and rerun Steps 1–5 before claiming completion.
