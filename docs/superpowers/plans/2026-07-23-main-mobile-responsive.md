# Production Main Pages Mobile Responsive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为生产 React 主页面 `/` 的首页、资料区和问答区建立无横向溢出、无遮挡且保留桌面视觉的移动端响应式布局。

**Architecture:** 保留现有 React 组件树、Zustand 状态、API 和路由，仅为布局节点增加语义 class，并把静态布局内联样式迁入就近 CSS。CSS 使用 980px、720px、360px 三级断点；Kimi CLI 在严格文件白名单内完成视觉首轮实现，Codex 负责测试、diff 审查、浏览器验收与额度耗尽接管。

**Tech Stack:** React 18、TypeScript 5.5、Vite 5、Framer Motion 11、Vitest 2、Testing Library、Playwright 1.61、Kimi CLI 24.15

## Global Constraints

- 对应规格：`docs/superpowers/specs/2026-07-23-main-mobile-responsive-design.md`。
- 仅修改生产主页面 `/`；不得修改 `/wiki/*`、`/wiki-preview/*`、`kimi_web`、后端、API、Store、会话或路由。
- 桌面 `>980px` 保持现有视觉和双栏行为。
- 断点固定为 `980px`、`720px`、`360px`。
- 移动视口使用 `100vh` 回退后声明 `100dvh`，并处理 `safe-area-inset-top/bottom`。
- 资料页使用已批准 A-v2：文字左下叠在图片上，不使用黑色文字背景块，主导航和分类标签保持紧凑。
- 320px 宽度下不得出现文档级横向溢出；问答工具栏可点击，输入框和发送按钮完整可见。
- Kimi CLI 每次只允许修改当前任务白名单文件，不得执行 Git 提交。
- Kimi CLI 额度耗尽、鉴权失败、非零退出、无有效 diff 或修改越界时，Codex 立即接管，不等待额度恢复。
- 不覆盖或回退用户已有改动；每次调用 Kimi 前后都检查 `git status --short` 和当前任务文件 diff。

---

## File Map

- Create `frontend/react-app/src/components/sections/HomeSection.css`: 首页桌面基线与手机竖屏规则。
- Create `frontend/react-app/src/components/sections/DataSection.css`: 资料双栏、移动海报、分类标签和 WIKI 入口。
- Create `frontend/react-app/src/components/sections/ChatSection.css`: 工具栏、消息区、气泡、输入区和移动安全区。
- Create `frontend/react-app/src/components/sections/MainResponsiveCss.test.ts`: 共享 CSS 响应式契约。
- Create `frontend/react-app/e2e/main-mobile-responsive.spec.ts`: 320/360/390/412/768/1440 多视口浏览器门禁与截图。
- Modify `frontend/react-app/src/styles/global.css`: `100dvh`、安全区变量和手机滚动吸附。
- Modify `frontend/react-app/src/components/animations/reactbits/CardNav.css`: 仅 `.card-nav--main` 的紧凑移动导航。
- Modify `frontend/react-app/src/components/sections/HomeSection.tsx`: 首页语义 class 与 CSS 导入。
- Modify `frontend/react-app/src/components/sections/HomeSection.test.tsx`: 首页结构契约。
- Modify `frontend/react-app/src/components/sections/DataSection.tsx`: 资料滚动区和分类导航 class/ARIA。
- Modify `frontend/react-app/src/components/sections/CategoryPanel.tsx`: 海报分层、分类 data 属性和 CSS 变量尺寸。
- Modify `frontend/react-app/src/components/sections/CategoryPanel.test.tsx`: 海报结构与分类属性契约。
- Modify `frontend/react-app/src/components/sections/ChatSection.tsx`: 工具栏、消息区和空状态 class。
- Modify `frontend/react-app/src/components/sections/ChatSection.test.tsx`: 可点击工具栏结构契约。
- Modify `frontend/react-app/src/components/chat/ChatInput.tsx`: 输入网格与动态模式 class。
- Modify `frontend/react-app/src/components/chat/ChatInput.test.tsx`: 输入结构契约。
- Modify `frontend/react-app/src/components/chat/MessageBubble.tsx`: 用户/助手气泡 modifier class。

---

### Task 1: Shared Dynamic Viewport and Main Card Nav

**Files:**
- Create: `frontend/react-app/src/components/sections/MainResponsiveCss.test.ts`
- Modify: `frontend/react-app/src/styles/global.css:8-15,60-66,251-255`
- Modify: `frontend/react-app/src/components/animations/reactbits/CardNav.css:59-66`

**Interfaces:**
- Produces CSS variables `--main-nav-mobile-offset` and `--main-page-bottom-safe`.
- Produces scoped selector `.card-nav--main`; Wiki navigation remains on existing generic rules.
- Later tasks consume the dynamic height and navigation offset variables.

- [ ] **Step 1: Write the failing shared CSS contract**

Create `MainResponsiveCss.test.ts` with:

```ts
// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const globalCss = readFileSync(new URL('../../styles/global.css', import.meta.url), 'utf8')
const navCss = readFileSync(new URL('../animations/reactbits/CardNav.css', import.meta.url), 'utf8')

describe('main page responsive CSS contract', () => {
  it('uses dynamic viewport units and mobile-safe snap behavior', () => {
    expect(globalCss).toContain('--main-nav-mobile-offset: 56px')
    expect(globalCss).toMatch(/\.snap-container\s*\{[^}]*height:\s*100vh[^}]*height:\s*100dvh/s)
    expect(globalCss).toMatch(/\.snap-section\s*\{[^}]*height:\s*100vh[^}]*height:\s*100dvh/s)
    expect(globalCss).toMatch(/@media \(max-width: 720px\)[\s\S]*scroll-snap-type:\s*y proximity/)
  })

  it('compacts only the main Card Nav on phones', () => {
    expect(navCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.card-nav--main \.card-nav__bar/)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__bar\s*\{[^}]*min-height:\s*40px/s)
    expect(navCss).toMatch(/\.card-nav--main \.card-nav__toggle[\s\S]*width:\s*36px[\s\S]*height:\s*36px/)
    expect(navCss).not.toMatch(/\.card-nav--wiki \.card-nav__bar\s*\{[^}]*min-height:\s*40px/s)
  })
})
```

- [ ] **Step 2: Run the contract and confirm RED**

Run:

```powershell
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/MainResponsiveCss.test.ts
```

Expected: FAIL because `100dvh`, `--main-nav-mobile-offset` and scoped compact navigation are absent.

- [ ] **Step 3: Ask Kimi CLI for the scoped baseline implementation**

Run from `D:\1999Wiki`:

```powershell
& 'D:\KIMI\Kimi_Cli\bin\kimi.exe' --auto -p @'
Implement Task 1 of docs/superpowers/plans/2026-07-23-main-mobile-responsive.md.
You may modify ONLY:
- frontend/react-app/src/styles/global.css
- frontend/react-app/src/components/animations/reactbits/CardNav.css
- frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
Do not modify Wiki-specific selectors, React/TypeScript files, APIs, stores, routes, dependencies, or Git state.
Requirements: preserve desktop styles; add 100vh then 100dvh; define --main-nav-mobile-offset: 56px and bottom safe-area variable; at max-width 720px change main snap to y proximity; compact ONLY .card-nav--main to a 40px bar with 36px toggle/theme controls and a smaller primary action. Run the focused Vitest test and report the diff and result. Do not commit.
'@
```

If Kimi cannot complete, implement the following target declarations directly:

```css
:root {
  --main-nav-mobile-offset: 56px;
  --main-page-bottom-safe: env(safe-area-inset-bottom, 0px);
}

.snap-container {
  height: 100vh;
  height: 100dvh;
}

.snap-section {
  height: 100vh;
  height: 100dvh;
}

@media (max-width: 720px) {
  .snap-container { scroll-snap-type: y proximity; }
  .snap-section { scroll-snap-stop: normal; }

  .card-nav--main {
    top: calc(env(safe-area-inset-top, 0px) + 6px);
    width: calc(100vw - 16px);
  }
  .card-nav--main .card-nav__bar {
    min-height: 40px;
    gap: 8px;
    padding: 2px 6px 2px 8px;
  }
  .card-nav--main .card-nav__toggle,
  .card-nav--main .theme-toggle { width: 36px; height: 36px; }
  .card-nav--main .card-nav__brand { font-size: .68rem; white-space: nowrap; }
  .card-nav--main .card-nav__actions { gap: 2px; }
  .card-nav--main .card-nav__primary {
    min-width: 58px;
    padding: 8px 9px;
    font-size: .76rem;
  }
}
```

- [ ] **Step 4: Review scope and run tests**

Run:

```powershell
git diff -- frontend/react-app/src/styles/global.css frontend/react-app/src/components/animations/reactbits/CardNav.css frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/MainResponsiveCss.test.ts src/components/navigation/RouteAwareCardNav.test.tsx
```

Expected: both test files PASS; diff contains no unscoped 40px Wiki navigation rule.

- [ ] **Step 5: Commit the baseline**

```powershell
git add frontend/react-app/src/styles/global.css frontend/react-app/src/components/animations/reactbits/CardNav.css frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
git commit -m "fix: add mobile viewport and main nav baseline"
```

---

### Task 2: Responsive Home Section

**Files:**
- Create: `frontend/react-app/src/components/sections/HomeSection.css`
- Modify: `frontend/react-app/src/components/sections/HomeSection.tsx:1-183`
- Modify: `frontend/react-app/src/components/sections/HomeSection.test.tsx`
- Modify: `frontend/react-app/src/components/sections/MainResponsiveCss.test.ts`

**Interfaces:**
- Produces `.home-section`, `.home-section__video`, `.home-section__content`, `.home-section__title`, `.home-section__subtitle`, `.home-section__version`, `.home-section__download`, `.home-section__cta`, `.home-section__toast`, `.home-section__scroll-cue`.
- Keeps `videoFailed`, `videoReady`, Framer Motion variants and media URLs unchanged.

- [ ] **Step 1: Add failing semantic and CSS tests**

Extend `HomeSection.test.tsx`:

```ts
it('exposes responsive home layout hooks without changing media behavior', () => {
  const { container } = render(<HomeSection />)
  expect(container.querySelector('.home-section')).toBeInTheDocument()
  expect(container.querySelector('.home-section__content')).toBeInTheDocument()
  expect(container.querySelector('.home-section__title')).toHaveTextContent('重返未来:1999')
  expect(container.querySelector('.home-section__cta')).toHaveTextContent('立即下载')
  expect(container.querySelector('.home-section__scroll-cue')).toBeInTheDocument()
})
```

Extend `MainResponsiveCss.test.ts`:

```ts
const homeCss = readFileSync(new URL('./HomeSection.css', import.meta.url), 'utf8')

it('defines phone home sizing and safe scroll cue placement', () => {
  expect(homeCss).toContain('@media (max-width: 720px)')
  expect(homeCss).toMatch(/\.home-section__video\s*\{[^}]*object-fit:\s*cover/s)
  expect(homeCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.home-section__cta\s*\{[^}]*min-height:\s*44px/s)
  expect(homeCss).toContain('env(safe-area-inset-bottom')
})
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/HomeSection.test.tsx src/components/sections/MainResponsiveCss.test.ts
```

Expected: FAIL because `HomeSection.css` and semantic classes do not exist.

- [ ] **Step 3: Ask Kimi CLI for the home visual implementation**

```powershell
cd D:\1999Wiki
& 'D:\KIMI\Kimi_Cli\bin\kimi.exe' --auto -p @'
Implement Task 2 of docs/superpowers/plans/2026-07-23-main-mobile-responsive.md.
You may modify ONLY:
- frontend/react-app/src/components/sections/HomeSection.tsx
- frontend/react-app/src/components/sections/HomeSection.css
- frontend/react-app/src/components/sections/HomeSection.test.tsx
- frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
Preserve the video source, poster fallback, state, animations, copy, download behavior, and desktop appearance. Move only static layout styles to semantic CSS classes. At max-width 720px use compact type/spacing, vertical-video object-position, a CTA at least 44px high, and bottom safe-area scroll cue placement. Add a max-width 360px refinement. Do not modify any other file or commit. Run the two focused tests.
'@
```

If Kimi cannot complete, replace the rendered Home section with this exact structure; keep the existing `showToast`, `videoFailed`, `videoReady` state declarations and `titleVariants` constant:

```tsx
import './HomeSection.css'

<section data-snap-section="home" className="snap-section home-section">
  <div
    className="home-section__fallback"
    aria-hidden="true"
    style={{
      backgroundImage: `linear-gradient(rgba(12, 16, 15, 0.28), rgba(12, 16, 15, 0.62)), url(${GLOBAL_BACKGROUND_IMAGE_SRC})`,
      filter: videoFailed ? 'none' : 'brightness(0.76)',
    }}
  />
  <video
    className="video-bg home-section__video"
    autoPlay
    muted
    loop
    playsInline
    poster={GLOBAL_BACKGROUND_IMAGE_SRC}
    onError={() => setVideoFailed(true)}
    onCanPlay={() => setVideoReady(true)}
    style={{ opacity: videoReady ? 1 : 0, transition: 'opacity 900ms ease' }}
  >
    <source src={HOME_VIDEO_SRC} type="video/mp4" />
  </video>
  <div className="home-section__content">
    <motion.h1 className="home-section__title" custom={0} variants={titleVariants} initial="hidden" animate="visible">重返未来:1999</motion.h1>
    <motion.h2 className="home-section__subtitle" custom={0.3} variants={titleVariants} initial="hidden" animate="visible">REVERSE: 1999</motion.h2>
    <motion.p className="home-section__version" custom={0.6} variants={titleVariants} initial="hidden" animate="visible">3.8 版本 · 世纪末尺度</motion.p>
    <motion.div className="home-section__download" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.9 }}>
      <button
        className="home-section__cta"
        onClick={() => {
          setShowToast(true)
          setTimeout(() => setShowToast(false), 2500)
        }}
      >立即下载</button>
      {showToast && (
        <motion.div className="home-section__toast" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          下载链接待补
        </motion.div>
      )}
    </motion.div>
  </div>
  <motion.div className="home-section__scroll-cue" animate={{ y: [0, 8, 0] }} transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}>↓</motion.div>
</section>
```

The CSS must reproduce current desktop values, then include:

```css
@media (max-width: 720px) {
  .home-section__video { object-position: 56% center; }
  .home-section__content { gap: 10px; padding: var(--main-nav-mobile-offset) 18px 28px; text-align: center; }
  .home-section__title { font-size: clamp(2rem, 11vw, 2.75rem); }
  .home-section__subtitle { font-size: clamp(1.2rem, 7vw, 1.8rem); }
  .home-section__version { font-size: .95rem; }
  .home-section__download { margin-top: 24px; }
  .home-section__cta { min-height: 44px; padding: 10px 32px; }
  .home-section__scroll-cue { bottom: calc(18px + env(safe-area-inset-bottom, 0px)); }
}

@media (max-width: 360px) {
  .home-section__content { padding-inline: 14px; }
  .home-section__download { margin-top: 18px; }
}
```

- [ ] **Step 4: Review and verify home tests**

```powershell
git diff -- frontend/react-app/src/components/sections/HomeSection.tsx frontend/react-app/src/components/sections/HomeSection.css frontend/react-app/src/components/sections/HomeSection.test.tsx frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/HomeSection.test.tsx src/components/sections/MainResponsiveCss.test.ts src/App.wheel.test.tsx
```

Expected: PASS; media fallback assertions remain unchanged.

- [ ] **Step 5: Commit the home section**

```powershell
git add frontend/react-app/src/components/sections/HomeSection.tsx frontend/react-app/src/components/sections/HomeSection.css frontend/react-app/src/components/sections/HomeSection.test.tsx frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
git commit -m "fix: optimize home section for phones"
```

---

### Task 3: Approved A-v2 Mobile Data Poster

**Files:**
- Create: `frontend/react-app/src/components/sections/DataSection.css`
- Modify: `frontend/react-app/src/components/sections/DataSection.tsx:1-62`
- Modify: `frontend/react-app/src/components/sections/CategoryPanel.tsx:1-140`
- Modify: `frontend/react-app/src/components/sections/CategoryPanel.test.tsx`
- Modify: `frontend/react-app/src/components/sections/MainResponsiveCss.test.ts`

**Interfaces:**
- Produces `.data-section__scroll`, `.data-section__nav`, `.data-section__nav-button` and `aria-current="page"` for the active category.
- Produces `.category-panel__layout`, `__copy`, `__media`, `__card`, `__title`, `__meta`, `__wiki-link`.
- Produces `data-category={meta.key}` for category-specific image positioning.
- Uses CSS variables `--category-cover-width`, `--category-cover-height`, `--category-cover-min-width` through `TiltedImageCard.containerStyle` so CSS can override existing inline geometry without `!important`.

- [ ] **Step 1: Write failing poster structure tests**

Extend `CategoryPanel.test.tsx`:

```ts
it('exposes the approved mobile poster layers and category identity', () => {
  const { container } = render(<CategoryPanel meta={meta} />)
  const panel = container.querySelector('.category-panel')
  expect(panel).toHaveAttribute('data-category', '人物')
  expect(container.querySelector('.category-panel__copy')).toBeInTheDocument()
  expect(container.querySelector('.category-panel__media')).toBeInTheDocument()
  expect(container.querySelector('.category-panel__card')).toBeInTheDocument()
})

it('uses CSS variables for cover geometry instead of fixed mobile-breaking widths', () => {
  const { container } = render(<CategoryPanel meta={meta} />)
  expect(container.querySelector('.category-panel__card')).toHaveStyle({
    width: 'var(--category-cover-width)',
    height: 'var(--category-cover-height)',
    minWidth: 'var(--category-cover-min-width)',
  })
})
```

Replace the old fixed-width expectation in `sizes the tilted cover card...` with the CSS-variable expectation above while preserving its desktop-layout assertion through the CSS contract.

Extend `MainResponsiveCss.test.ts`:

```ts
const dataCss = readFileSync(new URL('./DataSection.css', import.meta.url), 'utf8')

it('switches data panels to the approved transparent poster at 980px', () => {
  expect(dataCss).toContain('@media (max-width: 980px)')
  expect(dataCss).toMatch(/\.category-panel__layout\s*\{[^}]*grid-template-columns:\s*minmax\(320px, \.72fr\) minmax\(560px, 1\.45fr\)/s)
  expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.category-panel__copy\s*\{[^}]*position:\s*absolute[^}]*bottom:/s)
  expect(dataCss).toMatch(/@media \(max-width: 980px\)[\s\S]*\.data-section__nav\s*\{[^}]*overflow-x:\s*auto/s)
  const mobileCopy = dataCss.match(/@media \(max-width: 980px\)[\s\S]*?\.category-panel__copy\s*\{([^}]*)\}/)?.[1] ?? ''
  expect(mobileCopy).not.toMatch(/background(?:-color)?:/)
  expect(mobileCopy).toContain('text-shadow:')
})
```

- [ ] **Step 2: Run data tests and confirm RED**

```powershell
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/CategoryPanel.test.tsx src/components/sections/MainResponsiveCss.test.ts
```

Expected: FAIL because poster classes, CSS variables and `DataSection.css` do not exist.

- [ ] **Step 3: Ask Kimi CLI to implement the approved data visual**

```powershell
cd D:\1999Wiki
& 'D:\KIMI\Kimi_Cli\bin\kimi.exe' --auto -p @'
Implement Task 3 of docs/superpowers/plans/2026-07-23-main-mobile-responsive.md using the approved A-v2 poster design in docs/superpowers/specs/2026-07-23-main-mobile-responsive-design.md.
You may modify ONLY:
- frontend/react-app/src/components/sections/DataSection.tsx
- frontend/react-app/src/components/sections/CategoryPanel.tsx
- frontend/react-app/src/components/sections/DataSection.css
- frontend/react-app/src/components/sections/CategoryPanel.test.tsx
- frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
Do not modify TiltedImageCard, media mapping, stores, hooks, API, Wiki, dependencies, or Git state.
Preserve desktop geometry exactly. At max-width 980px: use a single-screen full visual poster; place transparent text at lower-left with text shadow and no black background block; make the image dominant; replace the vertical category nav with compact horizontally scrollable labels below the main nav; position character/psychube/story media by data-category; keep the WIKI link compact. Pass cover sizes through CSS variables in containerStyle. Prevent document-level horizontal overflow. Run the two focused tests and do not commit.
'@
```

If Kimi cannot complete, use this minimum JSX shape:

```tsx
// DataSection.tsx
import './DataSection.css'

<section data-snap-section="data" className="snap-section data-section">
  <div className="data-section__scroll native-scrollbar-hidden" data-testid="data-section-scroll">
    {categoriesMeta.map((category) => <CategoryPanel key={category.key} meta={category} />)}
  </div>
  <nav className="data-section__nav native-scrollbar-hidden" aria-label="资料分类">
    {categoriesMeta.map((category) => (
      <button
        className="data-section__nav-button"
        key={category.key}
        data-active={currentCategory === category.key || undefined}
        aria-current={currentCategory === category.key ? 'page' : undefined}
        onClick={() => {
          document
            .querySelector(`[data-snap-section="data:${category.key}"]`)
            ?.scrollIntoView({ behavior: 'smooth' })
        }}
      >{category.title}</button>
    ))}
  </nav>
</section>
```

```tsx
// CategoryPanel.tsx
import './DataSection.css'

<section
  ref={ref}
  data-snap-section={`data:${meta.key}`}
  data-category={meta.key}
  className="snap-section category-panel"
>
  <div className="category-bar category-panel__bar" />
  <motion.div
    className="category-panel__layout"
    data-testid="category-panel-layout"
    variants={panelVariants}
    initial="hidden"
    animate={inView ? 'visible' : 'hidden'}
  >
    <div className="category-panel__copy">
      <motion.h2 className="category-panel__title" variants={titleVariants}>{meta.title}</motion.h2>
      <motion.p className="category-panel__meta" variants={titleVariants}>{meta.subtitle} · {meta.doc_count} 篇</motion.p>
      <ScrollableDescription text={description} start={inView} />
      {loading && <p className="category-panel__loading">加载中...</p>}
    </div>
    <motion.div className="category-panel__media" variants={imageVariants}>
      <TiltedImageCard
        className="category-panel__card"
        src={coverUrl}
        alt={meta.title}
        hoverScale={1.15}
        containerStyle={{
          width: 'var(--category-cover-width)',
          height: 'var(--category-cover-height)',
          minWidth: 'var(--category-cover-min-width)',
        }}
        onImageError={(event) => { event.currentTarget.style.display = 'none' }}
      />
    </motion.div>
  </motion.div>
  {(meta.key === '剧情' || meta.title === '剧情' || meta.key.toLowerCase() === 'story') && (
    <a className="category-panel__wiki-link" href="/wiki" aria-label="进入WIKI">
      <span>进入WIKI</span><span aria-hidden="true">→</span>
    </a>
  )}
</section>
```

The CSS must keep the current desktop grid and implement these mobile invariants:

```css
.category-panel {
  --category-cover-width: min(42vw, 680px);
  --category-cover-height: min(64vh, 620px);
  --category-cover-min-width: 320px;
}

@media (max-width: 980px) {
  .data-section__scroll { overflow-x: clip; scroll-snap-type: y proximity; }
  .data-section__nav {
    top: 82px;
    right: 12px; left: 12px;
    display: flex; gap: 6px;
    overflow-x: auto;
    transform: none;
  }
  .category-panel {
    --category-cover-width: 100%;
    --category-cover-height: 90%;
    --category-cover-min-width: 0px;
    padding: 0 16px;
    overflow: hidden;
  }
  .category-panel__layout { position: relative; display: block; min-width: 0; height: 100%; }
  .category-panel__copy {
    position: absolute;
    bottom: calc(24px + env(safe-area-inset-bottom, 0px));
    left: 6px;
    z-index: 4;
    width: min(64%, 310px);
    text-shadow: 0 2px 3px rgba(0,0,0,.98), 0 5px 18px rgba(0,0,0,.88);
  }
  .category-panel__media { position: absolute; inset: 70px -12% 0 18%; justify-content: flex-end; align-items: flex-end; }
  .category-panel__bar { display: none; }
}

@media (max-width: 720px) {
  .data-section__nav {
    top: calc(env(safe-area-inset-top, 0px) + var(--main-nav-mobile-offset));
  }
}
```

Add category-specific selectors for both Chinese and English keys; character media stays right/bottom, psychube is centered, and story uses a wider centered frame.

- [ ] **Step 4: Review and verify data tests**

```powershell
git diff -- frontend/react-app/src/components/sections/DataSection.tsx frontend/react-app/src/components/sections/CategoryPanel.tsx frontend/react-app/src/components/sections/DataSection.css frontend/react-app/src/components/sections/CategoryPanel.test.tsx frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/CategoryPanel.test.tsx src/components/sections/MainResponsiveCss.test.ts src/App.wheel.test.tsx
```

Expected: PASS; no modified file outside the Task 3 whitelist.

- [ ] **Step 5: Commit the data poster**

```powershell
git add frontend/react-app/src/components/sections/DataSection.tsx frontend/react-app/src/components/sections/CategoryPanel.tsx frontend/react-app/src/components/sections/DataSection.css frontend/react-app/src/components/sections/CategoryPanel.test.tsx frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
git commit -m "fix: add approved mobile data poster layout"
```

---

### Task 4: Mobile Chat Toolbar, Messages, and Input

**Files:**
- Create: `frontend/react-app/src/components/sections/ChatSection.css`
- Modify: `frontend/react-app/src/components/sections/ChatSection.tsx:1-134`
- Modify: `frontend/react-app/src/components/sections/ChatSection.test.tsx`
- Modify: `frontend/react-app/src/components/chat/ChatInput.tsx:1-146`
- Modify: `frontend/react-app/src/components/chat/ChatInput.test.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageBubble.tsx:35-55`
- Modify: `frontend/react-app/src/components/sections/MainResponsiveCss.test.ts`

**Interfaces:**
- Produces `.chat-section__toolbar`, `__toolbar-label`, `__clear`, `__home`, `__message-shell`, `__messages`, `__empty`.
- Produces `.chat-input`, `.chat-input__form`, `__row`, `__field`, `__send`, `__modes`, `__mode`.
- Produces `.message-bubble--user` and `.message-bubble--assistant`.
- Preserves all send, retry, clear, route-mode, streaming and auto-scroll logic.

- [ ] **Step 1: Write failing chat structure and CSS tests**

Extend `ChatSection.test.tsx`:

```ts
it('exposes a responsive toolbar and scroll layout', () => {
  const { container } = render(<ChatSection />)
  expect(container.querySelector('.chat-section')).toBeInTheDocument()
  expect(container.querySelector('.chat-section__toolbar')).toBeInTheDocument()
  expect(screen.getByRole('combobox').closest('.chat-section__toolbar')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '清空对话' })).toHaveClass('chat-section__clear')
  expect(screen.getByRole('button', { name: '返回首页' })).toHaveClass('chat-section__home')
})
```

Extend `ChatInput.test.tsx`:

```ts
it('exposes a shrinkable input row and stable action hooks', () => {
  const { container } = render(<ChatInput />)
  expect(container.querySelector('.chat-input__row')).toBeInTheDocument()
  expect(screen.getByPlaceholderText('输入问题...')).toHaveClass('chat-input__field')
  expect(screen.getByRole('button', { name: '发送' })).toHaveClass('chat-input__send')
  expect(container.querySelector('.chat-input__modes')).toBeInTheDocument()
})
```

Extend `MainResponsiveCss.test.ts`:

```ts
const chatCss = readFileSync(new URL('./ChatSection.css', import.meta.url), 'utf8')

it('keeps the mobile chat toolbar below navigation and the input shrinkable', () => {
  expect(chatCss).toContain('@media (max-width: 720px)')
  expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.chat-section__toolbar\s*\{[^}]*padding-top:\s*calc\([^}]*--main-nav-mobile-offset/s)
  expect(chatCss).toMatch(/\.chat-input__row\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) auto/s)
  expect(chatCss).toMatch(/\.chat-input__field\s*\{[^}]*min-width:\s*0/s)
  expect(chatCss).toMatch(/@media \(max-width: 720px\)[\s\S]*\.message-bubble\s*\{[^}]*max-width:\s*88%/s)
  expect(chatCss).toMatch(/\.markdown-message (?:pre|table)[\s\S]*overflow-x:\s*auto/)
})
```

- [ ] **Step 2: Run chat tests and confirm RED**

```powershell
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/ChatSection.test.tsx src/components/chat/ChatInput.test.tsx src/components/chat/MessageBubble.test.tsx src/components/sections/MainResponsiveCss.test.ts
```

Expected: FAIL because responsive chat classes and CSS are absent.

- [ ] **Step 3: Ask Kimi CLI for the chat visual implementation**

```powershell
cd D:\1999Wiki
& 'D:\KIMI\Kimi_Cli\bin\kimi.exe' --auto -p @'
Implement Task 4 of docs/superpowers/plans/2026-07-23-main-mobile-responsive.md.
You may modify ONLY:
- frontend/react-app/src/components/sections/ChatSection.tsx
- frontend/react-app/src/components/sections/ChatSection.css
- frontend/react-app/src/components/sections/ChatSection.test.tsx
- frontend/react-app/src/components/chat/ChatInput.tsx
- frontend/react-app/src/components/chat/ChatInput.test.tsx
- frontend/react-app/src/components/chat/MessageBubble.tsx
- frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
Do not modify chatStore, SSE/API, conversation session, SuggestedQuestions component/CSS, media components, Wiki, dependencies, or Git state.
Preserve all behavior and desktop appearance. Move static layout styles to semantic classes. At max-width 720px place the toolbar below the 56px main-nav offset, keep controls clickable, use 88% message bubbles, make code/table overflow local, and use minmax(0,1fr)+auto for the input row with a 44px-high send button. Override suggested-question mobile presentation from ChatSection.css so it remains a compact one-line horizontal scroller. Add a max-width 360px refinement. Run focused tests and do not commit.
'@
```

If Kimi cannot complete, use these key structures:

```tsx
// ChatSection.tsx
import './ChatSection.css'

<section data-snap-section="chat" className="snap-section chat-section">
  <div className="chat-section__toolbar">
    <span className="chat-section__toolbar-label">检索范围:</span>
    <CategorySelect />
    <button className="chat-section__clear" type="button" title="清空对话" aria-label="清空对话" onClick={() => void clear()}><Trash2 aria-hidden="true" size={18} /></button>
    <button className="chat-section__home" onClick={jumpHome}>返回首页</button>
  </div>
  <div className="chat-section__message-shell">
    <div ref={scrollRef} className="chat-section__messages native-scrollbar-hidden" data-page-wheel-lock="true" data-testid="chat-message-scroll">
      {messages.length === 0 && (
        <div className="chat-section__empty">
          <p className="chat-section__empty-title">神秘学问答</p>
          <p>问问关于人物、心相、剧情、世界、阵营或日历的任何问题</p>
        </div>
      )}
      {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
    </div>
    <AutoHideScrollbar targetRef={scrollRef} testId="chat-message-scrollbar" variant="local" />
  </div>
  <ChatInput />
</section>
```

```tsx
// ChatInput.tsx
<div className="chat-input">
  {lastError && (
    <div className="chat-input__error">
      <span>{lastError}</span>
      <button type="button" onClick={onRetry} disabled={sending}>重试</button>
    </div>
  )}
  <form className="chat-input__form" onSubmit={onSubmit}>
    <SuggestedQuestions disabled={sending} onSelect={selectSuggestedQuestion} />
    <div className="chat-input__row">
      <input
        ref={inputRef}
        className="chat-input__field"
        type="text"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="输入问题..."
      />
      <button className="chat-input__send" type="submit" disabled={sending || !value.trim()}>发送</button>
    </div>
    <div className="chat-input__modes">
      {modeButton('expanded', '扩大检索')}
      {modeButton('freeSupplement', '自由补充')}
    </div>
  </form>
</div>
```

Replace the `modeButton` return value with this exact button so active styling is CSS-driven:

```tsx
<button
  type="button"
  className="chat-input__mode"
  aria-pressed={active}
  data-active={active || undefined}
  data-action-kind="route-mode"
  onClick={() => setRouteOption(key, !active)}
>
  {label}
</button>
```

```tsx
// MessageBubble.tsx motion shell only
className={`message-bubble message-bubble--${isUser ? 'user' : 'assistant'}`}
```

The CSS must contain:

```css
.chat-input__row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.chat-input__field { min-width: 0; }
.markdown-message pre { max-width: 100%; overflow-x: auto; }
.markdown-message table { display: block; max-width: 100%; overflow-x: auto; }

@media (max-width: 720px) {
  .chat-section__toolbar {
    min-height: calc(var(--main-nav-mobile-offset) + 48px);
    padding: calc(var(--main-nav-mobile-offset) + env(safe-area-inset-top, 0px)) 12px 8px;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) 36px auto;
    gap: 8px;
  }
  .chat-section__messages { padding: 12px; }
  .message-bubble { max-width: 88%; padding: 10px 12px; }
  .chat-input__form { padding: 10px 12px calc(10px + env(safe-area-inset-bottom, 0px)); }
  .chat-input__send { min-height: 44px; padding-inline: 18px; }
  .suggested-questions { display: flex; flex-direction: row; align-items: center; gap: 8px; padding: 6px 8px; }
  .suggested-questions__list { width: auto; }
}

@media (max-width: 360px) {
  .chat-section__toolbar-label { display: none; }
  .chat-section__toolbar { grid-template-columns: minmax(0, 1fr) 36px auto; }
  .chat-input__send { padding-inline: 14px; }
}
```

- [ ] **Step 4: Review and verify chat tests**

```powershell
git diff -- frontend/react-app/src/components/sections/ChatSection.tsx frontend/react-app/src/components/sections/ChatSection.css frontend/react-app/src/components/sections/ChatSection.test.tsx frontend/react-app/src/components/chat/ChatInput.tsx frontend/react-app/src/components/chat/ChatInput.test.tsx frontend/react-app/src/components/chat/MessageBubble.tsx frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/ChatSection.test.tsx src/components/chat/ChatInput.test.tsx src/components/chat/MessageBubble.test.tsx src/components/chat/SuggestedQuestions.test.tsx src/components/sections/MainResponsiveCss.test.ts
```

Expected: PASS; send/retry/clear/suggestion behavior tests remain unchanged.

- [ ] **Step 5: Commit the chat section**

```powershell
git add frontend/react-app/src/components/sections/ChatSection.tsx frontend/react-app/src/components/sections/ChatSection.css frontend/react-app/src/components/sections/ChatSection.test.tsx frontend/react-app/src/components/chat/ChatInput.tsx frontend/react-app/src/components/chat/ChatInput.test.tsx frontend/react-app/src/components/chat/MessageBubble.tsx frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
git commit -m "fix: make chat controls usable on phones"
```

---

### Task 5: Multi-Viewport Browser Gate and Visual Evidence

**Files:**
- Create: `frontend/react-app/e2e/main-mobile-responsive.spec.ts`
- Create evidence at runtime: `frontend/react-app/test-results/main-mobile-responsive-*/`
- Verify: all Task 1–4 files

**Interfaces:**
- Consumes semantic classes and responsive CSS from Tasks 1–4.
- Produces browser evidence for 320×568, 360×800, 390×844, 412×915, 768×1024 and 1440×900.

- [ ] **Step 1: Write the failing Playwright gate**

Create `main-mobile-responsive.spec.ts`:

```ts
import { expect, test, type Page } from '@playwright/test'

const categories = [
  { key: '人物', title: '人物', subtitle: 'Characters', description: '人物档案与神秘学家记录。', doc_count: 105, cover_prompt: '' },
  { key: '心相', title: '心相', subtitle: 'Psychube', description: '角色精神具象学器与记忆。', doc_count: 96, cover_prompt: '' },
  { key: '剧情', title: '剧情', subtitle: 'Story', description: '主线与支线剧情记录。', doc_count: 80, cover_prompt: '' },
]

async function installRoutes(page: Page) {
  await page.route('**/api/categories', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ categories }),
  }))
  await page.route('**/api/category/**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ docs: [] }),
  }))
  await page.route('**/api/conversations/**', (route) => route.fulfill({ status: 204 }))
}

async function jump(page: Page, id: 'home' | 'data' | 'chat') {
  await page.evaluate((sectionId) => {
    document.querySelector(`[data-snap-section="${sectionId}"]`)?.scrollIntoView()
  }, id)
  await page.waitForTimeout(350)
}

async function expectNoDocumentOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
}

test('main pages remain usable across approved mobile and tablet viewports', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'explicit responsive matrix runs once')
  await installRoutes(page)

  for (const viewport of [
    { width: 320, height: 568 },
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 412, height: 915 },
    { width: 768, height: 1024 },
  ]) {
    await page.setViewportSize(viewport)
    await page.goto('/')

    await jump(page, 'home')
    await expectNoDocumentOverflow(page)
    await page.screenshot({ path: testInfo.outputPath(`home-${viewport.width}x${viewport.height}.png`) })

    await jump(page, 'data')
    await expect(page.locator('[data-snap-section="data:人物"] .category-panel__copy')).toBeVisible()
    await expect(page.locator('[data-snap-section="data:人物"] .category-panel__media')).toBeVisible()
    const copyBackground = await page.locator('[data-snap-section="data:人物"] .category-panel__copy').evaluate(
      (element) => getComputedStyle(element).backgroundColor,
    )
    expect(copyBackground).toBe('rgba(0, 0, 0, 0)')
    await expectNoDocumentOverflow(page)
    await page.screenshot({ path: testInfo.outputPath(`data-${viewport.width}x${viewport.height}.png`) })

    await jump(page, 'chat')
    for (const control of [
      page.getByRole('combobox'),
      page.getByRole('button', { name: '清空对话' }),
      page.getByRole('button', { name: '返回首页' }),
    ]) {
      await expect(control).toBeVisible()
      expect(await control.evaluate((element) => {
        const rect = element.getBoundingClientRect()
        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
        return hit === element || element.contains(hit)
      })).toBe(true)
    }
    const inputBox = await page.getByPlaceholder('输入问题...').boundingBox()
    const sendBox = await page.getByRole('button', { name: '发送' }).boundingBox()
    expect(inputBox).not.toBeNull()
    expect(sendBox).not.toBeNull()
    expect(inputBox!.left).toBeGreaterThanOrEqual(0)
    expect(sendBox!.x + sendBox!.width).toBeLessThanOrEqual(viewport.width)
    await expectNoDocumentOverflow(page)
    await page.screenshot({ path: testInfo.outputPath(`chat-${viewport.width}x${viewport.height}.png`) })
  }
})

test('desktop geometry remains intact', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'desktop regression runs once')
  await installRoutes(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await jump(page, 'data')
  await expect(page.locator('[data-testid="category-panel-layout"]').first()).toHaveCSS('display', 'grid')
  await expect(page.locator('.data-section__nav')).toHaveCSS('flex-direction', 'column')
  await page.screenshot({ path: testInfo.outputPath('data-1440x900.png') })
  await jump(page, 'chat')
  await expect(page.locator('.message-bubble').first()).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('chat-1440x900.png') })
  await jump(page, 'home')
  await page.screenshot({ path: testInfo.outputPath('home-1440x900.png') })
})
```

- [ ] **Step 2: Start the app and run the new E2E gate**

Terminal A:

```powershell
cd D:\1999Wiki\frontend\react-app
npm run dev -- --host 127.0.0.1
```

Terminal B:

```powershell
cd D:\1999Wiki\frontend\react-app
npx playwright test e2e/main-mobile-responsive.spec.ts --project=desktop
```

Expected: the test executes all six explicit viewport sizes. Any failure identifies the remaining overflow, overlap or selector mismatch for Step 3. If all assertions pass, proceed directly to screenshot review; do not invent a code change merely to force a RED result.

- [ ] **Step 3: Apply only evidence-driven final adjustments**

Use the failing assertion or screenshot to adjust only the owning Task 1–4 CSS/JSX file. Do not introduce a new breakpoint or change APIs. Re-run the single failing Playwright test after each adjustment.

Examples of allowed adjustments:

```css
/* data image still clips at 320px */
@media (max-width: 360px) {
  .category-panel__media { right: -18%; left: 12%; }
  .category-panel__copy { width: 66%; bottom: calc(18px + env(safe-area-inset-bottom, 0px)); }
}

/* chat toolbar action is still covered */
@media (max-width: 720px) {
  .chat-section__toolbar { position: relative; z-index: 2; }
}
```

- [ ] **Step 4: Run focused and full frontend verification**

```powershell
cd D:\1999Wiki\frontend\react-app
npm test -- src/components/sections/HomeSection.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/sections/ChatSection.test.tsx src/components/chat/ChatInput.test.tsx src/components/chat/MessageBubble.test.tsx src/components/chat/SuggestedQuestions.test.tsx src/components/navigation/RouteAwareCardNav.test.tsx src/components/sections/MainResponsiveCss.test.ts
npm run build
npx playwright test e2e/main-mobile-responsive.spec.ts e2e/suggested-questions.spec.ts --project=desktop
```

Expected: all Vitest files PASS, TypeScript/Vite build exits 0, both Playwright specs PASS.

- [ ] **Step 5: Inspect screenshots at original resolution**

Review every `test-results/main-mobile-responsive-*/*.png` and confirm:

- A-v2 data text has no black panel and does not hide the image subject.
- Main Card Nav is visually compact and balanced.
- All data/category imagery remains visible for 人物、心相、剧情.
- Chat toolbar is visible below Card Nav.
- 320px input and send button fit without clipping.
- 1440×900 remains visually unchanged except semantic refactoring.

- [ ] **Step 6: Commit browser coverage and final adjustments**

```powershell
git add -- frontend/react-app/e2e/main-mobile-responsive.spec.ts frontend/react-app/src/styles/global.css frontend/react-app/src/components/animations/reactbits/CardNav.css frontend/react-app/src/components/sections/HomeSection.tsx frontend/react-app/src/components/sections/HomeSection.css frontend/react-app/src/components/sections/DataSection.tsx frontend/react-app/src/components/sections/CategoryPanel.tsx frontend/react-app/src/components/sections/DataSection.css frontend/react-app/src/components/sections/ChatSection.tsx frontend/react-app/src/components/sections/ChatSection.css frontend/react-app/src/components/chat/ChatInput.tsx frontend/react-app/src/components/chat/MessageBubble.tsx frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
git commit -m "test: gate main page mobile responsiveness"
```

- [ ] **Step 7: Final scope audit**

```powershell
git status --short
git diff HEAD~5..HEAD --name-only
git diff --check HEAD~5..HEAD
```

Expected: changed production files are limited to the File Map; no API, Store, Wiki, backend, dependency or `kimi_web` files appear.

---

## Execution Notes

At each Kimi step, capture its terminal result in the task log. A quota message is a handoff signal, not a blocker: inspect the current diff, retain only valid in-scope changes, and continue with the explicit fallback code in that task.

Do not run multiple Kimi sessions concurrently because all tasks share the same worktree and CSS contract file. Execute Tasks 1–5 sequentially and commit only after the listed verification passes.
