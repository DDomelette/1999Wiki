import { expect, test, type Locator, type Page } from '@playwright/test'

const categories = [
  { key: '\u4eba\u7269', title: '\u4eba\u7269', subtitle: 'Characters', description: 'Character archives.', doc_count: 105, cover_prompt: '' },
  { key: '\u5fc3\u76f8', title: '\u5fc3\u76f8', subtitle: 'Psychube', description: 'Psychube archives.', doc_count: 96, cover_prompt: '' },
  { key: '\u5267\u60c5', title: '\u5267\u60c5', subtitle: 'Story', description: 'Story archives.', doc_count: 80, cover_prompt: '' },
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

async function jump(page: Page, id: string) {
  await page.locator(`[data-snap-section="${id}"]`).evaluate((element) => {
    element.scrollIntoView({ block: 'start' })
  })
  await page.waitForTimeout(450)
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
  ).toBeGreaterThan(0.98)
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
    await expect(page.locator('.category-panel')).toHaveCount(3)

    await jump(page, 'home')
    const navBar = page.locator('.card-nav--main .card-nav__bar')
    await expect(navBar).toBeVisible()
    if (viewport.width <= 720) {
      expect((await navBar.boundingBox())!.height).toBeLessThanOrEqual(42)
    }
    await expectNoDocumentOverflow(page)
    await page.screenshot({ path: testInfo.outputPath(`home-${viewport.width}x${viewport.height}.png`) })

    await jump(page, 'data')
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
    await page.screenshot({ path: testInfo.outputPath(`data-${viewport.width}x${viewport.height}.png`) })

    if (viewport.width === 390) {
      for (const category of categories.slice(1)) {
        await jump(page, `data:${category.key}`)
        const panel = page.locator(`[data-snap-section="data:${category.key}"]`)
        await expect(panel.locator('.category-panel__copy')).toBeVisible()
        await expect(panel.locator('.category-panel__media')).toBeVisible()
        await expectVisibleArtwork(panel, viewport)
        await page.screenshot({ path: testInfo.outputPath(`data-${category.subtitle.toLowerCase()}-390x844.png`) })
      }
      const wikiLink = page.locator('.category-panel__wiki-link')
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
    await page.screenshot({ path: testInfo.outputPath(`chat-${viewport.width}x${viewport.height}.png`) })
  }
})

test('desktop geometry remains intact', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'desktop regression runs once')
  await installRoutes(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await expect(page.locator('.category-panel')).toHaveCount(3)

  await jump(page, 'data')
  const character = page.locator(`[data-snap-section="data:${categories[0].key}"]`)
  await expect(page.locator('[data-testid="category-panel-layout"]').first()).toHaveCSS('display', 'grid')
  await expectVisibleArtwork(character, { width: 1440, height: 900 })
  await expect(page.locator('.data-section__nav')).toHaveCSS('flex-direction', 'column')
  await expectNoDocumentOverflow(page)
  await page.screenshot({ path: testInfo.outputPath('data-1440x900.png') })

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
  await page.screenshot({ path: testInfo.outputPath('chat-1440x900.png') })

  await jump(page, 'home')
  await page.screenshot({ path: testInfo.outputPath('home-1440x900.png') })
})
