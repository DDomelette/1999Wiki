import { expect, test, type Locator, type Page } from '@playwright/test'

const categories = [
  { key: '人物', title: '人物', subtitle: 'Characters', description: 'Character archives.', doc_count: 105, cover_prompt: '' },
  { key: '心相', title: '心相', subtitle: 'Psychube', description: 'Psychube archives.', doc_count: 96, cover_prompt: '' },
  { key: '剧情', title: '剧情', subtitle: 'Story', description: 'Story archives.', doc_count: 80, cover_prompt: '' },
]

const mainSectionOrder = ['home', 'data:人物', 'data:心相', 'data:剧情', 'chat']

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
  await page.route('**/api/wiki/categories', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ categories: [] }),
  }))
  await page.route('**/api/wiki/pages', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ items: [], nextCursor: null }),
  }))
}

async function jump(page: Page, id: string) {
  await page.locator(`[data-snap-section="${id}"]`).evaluate((element) => {
    element.scrollIntoView({ block: 'start' })
  })
  await page.waitForTimeout(450)
}

async function mainScrollState(page: Page) {
  return page.locator('.snap-container').evaluate((element) => ({
    scrollTop: element.scrollTop,
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }))
}

async function expectSnapAligned(page: Page, id: string) {
  await expect
    .poll(
      () => page.locator('.snap-container').evaluate((element, sectionId) => {
        const section = element.querySelector(`[data-snap-section="${sectionId}"]`)
        if (!section) return Number.POSITIVE_INFINITY
        return Math.abs(section.getBoundingClientRect().top - element.getBoundingClientRect().top)
      }, id),
      { timeout: 3_000 },
    )
    .toBeLessThanOrEqual(1)
}

async function installAskStream(page: Page) {
  await page.route('**/api/ask/stream', (route) => route.fulfill({
    contentType: 'text/event-stream',
    body: `event: done\ndata: ${JSON.stringify({
      answer: '这是一段用于验证移动端消息滚动的较长回答。'.repeat(8),
      sources: [], assets: [], media: [],
    })}\n\n`,
  }))
}

async function fillChatUntilOverflow(page: Page) {
  const input = page.locator('.chat-input__field')
  const send = page.locator('.chat-input__send')
  const messages = page.locator('.chat-section__messages')
  for (let index = 0; index < 8; index += 1) {
    await input.fill(`e2e 溢出验证问题 ${index + 1}`)
    await send.click()
    await expect(page.locator('.message-bubble--assistant')).toHaveCount(index + 1)
    if (await messages.evaluate((element) => element.scrollHeight > element.clientHeight)) {
      return messages.evaluate((element) => {
        element.scrollTop = element.scrollHeight - element.clientHeight
        return element.scrollTop
      })
    }
  }
  throw new Error('chat messages did not overflow after 8 sends')
}

async function dispatchTouchSequence(locator: Locator, startY: number, endY: number) {
  // 只验证应用 touch hook:dispatchEvent 派发的是合成 TouchEvent,不代表原生手势或惯性滚动。
  const box = await locator.boundingBox()
  if (!box) throw new Error('dispatchTouchSequence target has no bounding box')
  const clientX = box.x + box.width / 2
  const touch = (clientY: number) => [{ identifier: 1, clientX, clientY }]
  await locator.dispatchEvent('touchstart', { touches: touch(startY), changedTouches: touch(startY), bubbles: true, cancelable: true })
  await locator.dispatchEvent('touchmove', { touches: touch((startY + endY) / 2), changedTouches: touch((startY + endY) / 2), bubbles: true, cancelable: true })
  await locator.dispatchEvent('touchmove', { touches: touch(endY), changedTouches: touch(endY), bubbles: true, cancelable: true })
  await locator.dispatchEvent('touchend', { touches: [], changedTouches: touch(endY), bubbles: true, cancelable: true })
}

async function expectNoDocumentOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
}

async function expectHitTarget(locator: Locator) {
  await expect(locator).toBeVisible()
  expect(await locator.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
    return hit === element || element.contains(hit)
  })).toBe(true)
}

async function expectVisibleArtwork(panel: Locator, viewport: { width: number; height: number }) {
  const image = panel.locator('.category-panel__card img')
  await expect(image).toBeVisible()
  await expect.poll(
    () => panel.locator('.category-panel__media').evaluate((element) => Number(getComputedStyle(element).opacity)),
    { timeout: 3_000 },
  ).toBeGreaterThan(0.95)
  await expect.poll(
    () => panel.locator('.category-panel__media').evaluate((element) => getComputedStyle(element).filter),
    { timeout: 3_000 },
  ).toBe('blur(0px)')
  const state = await image.evaluate((element) => {
    const imageElement = element as HTMLImageElement
    const rect = imageElement.getBoundingClientRect()
    const media = imageElement.closest('.category-panel__media') as Element
    const panel = imageElement.closest('.category-panel') as Element
    const mediaStyle = getComputedStyle(media)
    const mediaRect = media.getBoundingClientRect()
    const panelRect = panel.getBoundingClientRect()
    return {
      currentSrc: imageElement.currentSrc,
      naturalWidth: imageElement.naturalWidth,
      naturalHeight: imageElement.naturalHeight,
      width: rect.width,
      height: rect.height,
      mediaOpacity: Number(mediaStyle.opacity),
      mediaRect: { top: mediaRect.top, bottom: mediaRect.bottom },
      panelRect: { top: panelRect.top, bottom: panelRect.bottom },
    }
  })
  expect(state.currentSrc).not.toBe('')
  expect(state.naturalWidth).toBeGreaterThan(0)
  expect(state.naturalHeight).toBeGreaterThan(0)
  expect(state.width).toBeGreaterThan(viewport.width * 0.15)
  expect(state.height).toBeGreaterThan(viewport.height * 0.25)
  expect(state.mediaOpacity, JSON.stringify(state)).toBeGreaterThan(0.5)
}

test('main pages remain usable across approved mobile and tablet viewports', async ({ page }, testInfo) => {
  // WebKit serially renders five viewport/artwork states more slowly than Chromium.
  test.setTimeout(testInfo.project.name === 'mobile-webkit' ? 180_000 : 90_000)
  test.skip(!['desktop', 'mobile', 'mobile-webkit'].includes(testInfo.project.name), 'explicit responsive matrix runs in desktop and touch projects')
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
    await expect(page.locator('.category-panel')).toHaveCount(3)

    await jump(page, 'home')
    const navBar = page.locator('.card-nav--main .card-nav__bar')
    await expect(navBar).toBeVisible()
    if (viewport.width <= 720) {
      expect((await navBar.boundingBox())!.height).toBeLessThanOrEqual(42)
    }
    await expectNoDocumentOverflow(page)

    await jump(page, 'data:人物')
    const character = page.locator(`[data-snap-section="data:${categories[0].key}"]`)
    await expect(character.locator('.category-panel__copy')).toBeVisible()
    await expect(character.locator('.category-panel__media')).toBeVisible()
    await expectVisibleArtwork(character, viewport)
    const copyBackground = await character.locator('.category-panel__copy').evaluate(
      (element) => getComputedStyle(element).backgroundColor,
    )
    expect(copyBackground).toBe('rgba(0, 0, 0, 0)')
    const categoryButtons = page.locator('.data-section__nav-button')
    await expect(categoryButtons).toHaveCount(3)
    if (viewport.width <= 980) {
      for (const button of await categoryButtons.all()) {
        expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44)
      }
    }
    await expectNoDocumentOverflow(page)

    if (viewport.width === 390) {
      for (const category of categories.slice(1)) {
        await jump(page, `data:${category.key}`)
        const panel = page.locator(`[data-snap-section="data:${category.key}"]`)
        await expect(panel.locator('.category-panel__copy')).toBeVisible()
        await expect(panel.locator('.category-panel__media')).toBeVisible()
        await expectVisibleArtwork(panel, viewport)
      }
      const story = categories[categories.length - 1]
      const storyPanel = page.locator(`[data-snap-section="data:${story.key}"]`)
      const wikiLink = storyPanel.locator('.category-panel__wiki-link')
      await expectHitTarget(wikiLink)
    }

    await jump(page, 'chat')
    const toolbar = page.locator('.chat-section__toolbar')
    const select = page.getByRole('combobox')
    for (const control of [select, page.locator('.chat-section__clear'), page.locator('.chat-section__home')]) {
      await expectHitTarget(control)
    }
    if (viewport.width <= 720) {
      const navBox = await navBar.boundingBox()
      const selectBox = await select.boundingBox()
      expect(selectBox!.y).toBeGreaterThanOrEqual(navBox!.y + navBox!.height)
    }
    await expect(toolbar).toBeVisible()
    const inputBox = await page.locator('.chat-input__field').boundingBox()
    const sendBox = await page.locator('.chat-input__send').boundingBox()
    expect(inputBox).not.toBeNull()
    expect(sendBox).not.toBeNull()
    expect(inputBox!.x).toBeGreaterThanOrEqual(0)
    expect(sendBox!.x + sendBox!.width).toBeLessThanOrEqual(viewport.width)
    if (viewport.width <= 720) expect(sendBox!.height).toBeGreaterThanOrEqual(44)
    await expectNoDocumentOverflow(page)
  }
})

test('mobile chat survives touch input, long messages, and keyboard-height contraction', async ({ page }, testInfo) => {
  test.skip(!['mobile', 'mobile-webkit'].includes(testInfo.project.name), 'mobile browser regression only')
  await installRoutes(page)
  await page.route('**/api/ask/stream', (route) => route.fulfill({
    contentType: 'text/event-stream',
    body: `event: done\ndata: ${JSON.stringify({
      answer: '这是一段用于验证移动端消息滚动的较长回答。'.repeat(8),
      sources: [], assets: [], media: [],
    })}\n\n`,
  }))
  await page.goto('/')
  await jump(page, 'chat')

  const input = page.locator('.chat-input__field')
  const send = page.locator('.chat-input__send')
  await page.locator('.suggested-questions__item').first().tap()
  await expect(input).toBeFocused()

  for (let index = 0; index < 5; index += 1) {
    await input.fill(`移动端测试问题 ${index + 1}`)
    await send.tap()
    await expect(page.locator('.message-bubble--assistant')).toHaveCount(index + 1)
  }

  const messageScroll = page.locator('.chat-section__messages')
  const scrollMetrics = await messageScroll.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }))
  expect(scrollMetrics.scrollHeight).toBeGreaterThan(scrollMetrics.clientHeight)
  const mainScrollTop = await page.locator('.snap-container').evaluate((element) => element.scrollTop)
  await messageScroll.evaluate((element) => { element.scrollTop = 0 })
  expect(await messageScroll.evaluate((element) => element.scrollTop)).toBe(0)
  expect(await page.locator('.snap-container').evaluate((element) => element.scrollTop)).toBe(mainScrollTop)

  await input.focus()
  await page.setViewportSize({ width: 390, height: 568 })
  const visualHeight = await page.evaluate(() => window.visualViewport?.height ?? window.innerHeight)
  const rowBox = await page.locator('.chat-input__row').boundingBox()
  expect(rowBox).not.toBeNull()
  expect(rowBox!.y).toBeGreaterThanOrEqual(0)
  expect(rowBox!.y + rowBox!.height).toBeLessThanOrEqual(visualHeight)
  await expectHitTarget(send)
  await expectNoDocumentOverflow(page)
  await page.screenshot({ path: testInfo.outputPath('chat-keyboard-height-390x568.png') })
})

test('desktop geometry remains intact', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'desktop regression runs once')
  await installRoutes(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await expect(page.locator('.category-panel')).toHaveCount(3)

  await jump(page, 'data:人物')
  const character = page.locator(`[data-snap-section="data:${categories[0].key}"]`)
  await expect(page.locator('[data-testid="category-panel-layout"]').first()).toHaveCSS('display', 'grid')
  await expectVisibleArtwork(character, { width: 1440, height: 900 })
  await expect(page.locator('.data-section__nav')).toHaveCSS('flex-direction', 'column')
  await expectNoDocumentOverflow(page)

  await jump(page, 'chat')
  const desktopNav = page.locator('.card-nav--main .card-nav__bar')
  const desktopSelect = page.getByRole('combobox')
  await expect(page.locator('.chat-section__toolbar')).toHaveCSS('display', 'flex')
  await expectHitTarget(desktopSelect)
  await expectHitTarget(page.locator('.chat-section__clear'))
  await expectHitTarget(page.locator('.chat-section__home'))
  const desktopNavBox = await desktopNav.boundingBox()
  const desktopSelectBox = await desktopSelect.boundingBox()
  expect(desktopSelectBox!.y).toBeGreaterThanOrEqual(desktopNavBox!.y + desktopNavBox!.height)

  await jump(page, 'home')
})

test('main snap geometry keeps five full-height sections in strict order across approved projects', async ({ page }, testInfo) => {
  test.skip(!['desktop', 'mobile', 'mobile-webkit'].includes(testInfo.project.name), 'geometry regression runs in desktop and touch projects')
  await installRoutes(page)
  await page.goto('/')
  await expect(page.locator('.category-panel')).toHaveCount(3)

  const sectionIds = await page.locator('.snap-container [data-snap-section]').evaluateAll(
    (elements) => elements.map((element) => element.getAttribute('data-snap-section')),
  )
  expect(sectionIds).toEqual(mainSectionOrder)

  const state = await mainScrollState(page)
  expect(Math.abs(state.scrollHeight - state.clientHeight * mainSectionOrder.length)).toBeLessThanOrEqual(1)
  for (const id of mainSectionOrder) {
    const height = await page.locator(`[data-snap-section="${id}"]`).evaluate((element) => (element as HTMLElement).offsetHeight)
    expect(Math.abs(height - state.clientHeight)).toBeLessThanOrEqual(1)
  }
})

test('app wheel handler (not native inertia) advances exactly one leaf per gesture after the 850ms lock', async ({ page }, testInfo) => {
  test.skip(!['desktop', 'mobile'].includes(testInfo.project.name), 'mouse.wheel is unsupported in mobile WebKit')
  await installRoutes(page)
  await page.goto('/')
  await expect(page.locator('.category-panel')).toHaveCount(3)

  const viewport = page.viewportSize() ?? { width: 1280, height: 720 }
  await page.mouse.move(viewport.width / 2, viewport.height / 2)
  await jump(page, 'home')
  await expectSnapAligned(page, 'home')

  const leafOrder = ['data:人物', 'data:心相', 'data:剧情', 'chat']
  for (const [index, id] of leafOrder.entries()) {
    await page.mouse.wheel(0, 1_200)
    await expectSnapAligned(page, id)
    const state = await mainScrollState(page)
    expect(Math.abs(state.scrollTop - (index + 1) * state.clientHeight)).toBeLessThanOrEqual(1)
    await page.waitForTimeout(850)
  }
})

test('navigation and history keep hash targets snap-aligned across approved projects', async ({ page }, testInfo) => {
  test.skip(!['desktop', 'mobile', 'mobile-webkit'].includes(testInfo.project.name), 'navigation regression runs in desktop and touch projects')
  await installRoutes(page)

  await page.goto('/#chat')
  await expectSnapAligned(page, 'chat')
  await page.reload()
  await expectSnapAligned(page, 'chat')

  const navToggle = page.locator('.card-nav__toggle')
  await expect(navToggle).toHaveCount(1)
  await navToggle.click()
  const dataMenuButton = page.getByRole('button', { name: '资料', exact: true })
  await expect(dataMenuButton).toHaveCount(1)
  await dataMenuButton.click()
  await expect(page).toHaveURL(/#data$/)
  await expectSnapAligned(page, 'data:人物')

  await expect(navToggle).toHaveCount(1)
  await navToggle.click()
  const chatMenuButton = page.getByRole('button', { name: '问答', exact: true })
  await expect(chatMenuButton).toHaveCount(1)
  await chatMenuButton.click()
  await expect(page).toHaveURL(/#chat$/)
  await expectSnapAligned(page, 'chat')

  await page.goBack()
  await expect(page).toHaveURL(/#data$/)
  await expectSnapAligned(page, 'data:人物')

  await page.goto('/wiki/character')
  await expect(navToggle).toHaveCount(1)
  await navToggle.click()
  const wikiChatLink = page.getByRole('link', { name: '问答', exact: true })
  await expect(wikiChatLink).toHaveCount(1)
  await expect(wikiChatLink).toHaveAttribute('href', '/#chat')
  await wikiChatLink.click()
  await expect(page).toHaveURL(/#chat$/)
  await expectSnapAligned(page, 'chat')
})

test('viewport resize keeps snap alignment, message scroll position, and chat input in view', async ({ page }, testInfo) => {
  test.skip(!['desktop', 'mobile', 'mobile-webkit'].includes(testInfo.project.name), 'resize regression runs in desktop and touch projects')
  await installRoutes(page)
  await installAskStream(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.locator('.category-panel')).toHaveCount(3)

  await jump(page, 'data:心相')
  await expectSnapAligned(page, 'data:心相')
  await page.setViewportSize({ width: 390, height: 568 })
  await page.waitForTimeout(300)
  await expectSnapAligned(page, 'data:心相')

  await page.setViewportSize({ width: 390, height: 844 })
  await jump(page, 'chat')
  await expectSnapAligned(page, 'chat')
  const messages = page.locator('.chat-section__messages')
  const recordedScrollTop = await fillChatUntilOverflow(page)
  expect(recordedScrollTop).toBeGreaterThan(0)

  await page.setViewportSize({ width: 390, height: 568 })
  await page.waitForTimeout(300)
  await expectSnapAligned(page, 'chat')
  const storyPeek = await page.locator('.snap-container').evaluate((element) => {
    const story = element.querySelector('[data-snap-section="data:剧情"]')
    return story ? story.getBoundingClientRect().bottom - element.getBoundingClientRect().top : Number.POSITIVE_INFINITY
  })
  expect(storyPeek).toBeLessThanOrEqual(1)
  expect(await messages.evaluate((element) => element.scrollTop)).toBe(recordedScrollTop)
  const visualHeight = await page.evaluate(() => window.visualViewport?.height ?? window.innerHeight)
  const rowBox = await page.locator('.chat-input__row').boundingBox()
  expect(rowBox).not.toBeNull()
  expect(rowBox!.y).toBeGreaterThanOrEqual(0)
  expect(rowBox!.y + rowBox!.height).toBeLessThanOrEqual(visualHeight)
})

test('chat local scroll and boundary hooks keep the chat leaf (synthetic dispatchEvent verifies app hooks only, not native inertia)', async ({ page }, testInfo) => {
  test.skip(!['mobile', 'mobile-webkit'].includes(testInfo.project.name), 'chat boundary regression runs in touch projects')
  await installRoutes(page)
  await installAskStream(page)
  await page.goto('/')
  await jump(page, 'chat')
  await expectSnapAligned(page, 'chat')
  await fillChatUntilOverflow(page)

  const messages = page.locator('.chat-section__messages')
  const mainScrollTop = (await mainScrollState(page)).scrollTop

  // 本地滚动:修改 messages.scrollTop 不得改变主容器 scrollTop。
  const middleScrollTop = await messages.evaluate((element) => {
    element.scrollTop = Math.floor((element.scrollHeight - element.clientHeight) / 2)
    return element.scrollTop
  })
  expect(middleScrollTop).toBeGreaterThan(0)
  expect((await mainScrollState(page)).scrollTop).toBe(mainScrollTop)

  // dispatchEvent 只验证应用 wheel hook 的边界判定,不代表原生滚轮或惯性滚动;中间位置正/负 delta 都必须保持 chat。
  await messages.dispatchEvent('wheel', { deltaY: 240, bubbles: true, cancelable: true })
  await page.waitForTimeout(850)
  await expectSnapAligned(page, 'chat')
  await messages.dispatchEvent('wheel', { deltaY: -240, bubbles: true, cancelable: true })
  await page.waitForTimeout(850)
  await expectSnapAligned(page, 'chat')
  expect((await mainScrollState(page)).scrollTop).toBe(mainScrollTop)

  // touch 序列同样只验证应用 touch hook(合成 TouchEvent),不代表原生手势。
  const messagesBox = await messages.boundingBox()
  expect(messagesBox).not.toBeNull()

  // 顶部向下拉 90px(超过阈值)→ 回到上一叶 data:剧情。
  await messages.evaluate((element) => { element.scrollTop = 0 })
  await dispatchTouchSequence(messages, messagesBox!.y + 30, messagesBox!.y + 120)
  await expectSnapAligned(page, 'data:剧情')

  // 重新 jump chat 后,顶部向下 50px(低于阈值)不返回上一叶。
  await jump(page, 'chat')
  await expectSnapAligned(page, 'chat')
  await messages.evaluate((element) => { element.scrollTop = 0 })
  await dispatchTouchSequence(messages, messagesBox!.y + 30, messagesBox!.y + 80)
  await page.waitForTimeout(850)
  await expectSnapAligned(page, 'chat')

  // 底部手指向上 100px:chat 已是最后一叶,保持 chat。
  await messages.evaluate((element) => { element.scrollTop = element.scrollHeight - element.clientHeight })
  await dispatchTouchSequence(messages, messagesBox!.y + messagesBox!.height - 30, messagesBox!.y + messagesBox!.height - 130)
  await page.waitForTimeout(850)
  await expectSnapAligned(page, 'chat')
})
