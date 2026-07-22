import { mkdir } from 'node:fs/promises'
import { expect, test, type Locator, type Page } from '@playwright/test'

const evidenceDir = '../../eval/kimi-wiki-preview-20260717/screenshots'
const approvedViewports = [
  { name: 'wide', width: 2560, height: 1440 },
  { name: 'full-hd', width: 1920, height: 1080 },
  { name: 'desktop-standard', width: 1440, height: 900 },
  { name: 'desktop', width: 1280, height: 951 },
  { name: 'desktop-tall', width: 1280, height: 1024 },
  { name: 'mobile-small', width: 360, height: 800 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'mobile-wide', width: 412, height: 915 },
] as const

function auditReadOnlyRequests(page: Page) {
  const violations: string[] = []
  page.on('request', (request) => {
    const url = request.url()
    const method = request.method()
    if (url.includes('/api/wiki/') && method !== 'GET') violations.push(`${method} ${url}`)
    if (/:8001\b/.test(url) || /^file:/i.test(url) || /(?:^|[/\\])[A-Z]:[/\\]/i.test(url)) {
      violations.push(url)
    }
    if (/:9002\b/.test(url) && method !== 'GET') violations.push(`${method} ${url}`)
    if (/\b(?:minio|main-minio):9000\b/i.test(url)) violations.push(url)
  })
  return violations
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
}

async function expectLoadedImageOrFallback(stage: Locator) {
  const image = stage.locator('img').first()
  const fallback = stage.getByText('MEDIA UNAVAILABLE')
  await expect(image.or(fallback)).toBeVisible({ timeout: 30_000 })
  if (await image.isVisible().catch(() => false)) {
    await expect.poll(
      () => image.evaluate((node: HTMLImageElement) => node.complete ? node.naturalWidth : 0),
      { timeout: 30_000 },
    ).toBeGreaterThan(0)
  }
}

async function expectStageMediaInFirstViewport(stage: Locator) {
  const metrics = await stage.evaluate((node) => {
    const stageRect = node.getBoundingClientRect()
    const media = node.querySelector('img, .kimi-wiki-selection__media-fallback')
    const mediaRect = media?.getBoundingClientRect()
    return {
      stageBottom: stageRect.bottom,
      mediaTop: mediaRect?.top ?? Number.POSITIVE_INFINITY,
      mediaBottom: mediaRect?.bottom ?? Number.NEGATIVE_INFINITY,
      viewportHeight: window.innerHeight,
    }
  })
  expect(metrics.stageBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1)
  expect(metrics.mediaTop).toBeLessThan(metrics.viewportHeight)
  expect(metrics.mediaBottom).toBeGreaterThan(0)
}

async function expectFullWidthPersistentNav(page: Page) {
  const metrics = await page.locator('.card-nav').evaluate((node) => {
    const rect = node.getBoundingClientRect()
    return {
      left: rect.left,
      right: rect.right,
      top: rect.top,
      width: rect.width,
      viewportWidth: window.innerWidth,
    }
  })
  expect(metrics.left).toBeLessThanOrEqual(1)
  expect(metrics.right).toBeGreaterThanOrEqual(metrics.viewportWidth - 1)
  expect(metrics.width).toBeGreaterThanOrEqual(metrics.viewportWidth - 1)
  expect(metrics.top).toBeLessThanOrEqual(1)
}

test('real Wiki API drives three distinct preview selections and canonical detail routing', async ({ page }) => {
  const violations = auditReadOnlyRequests(page)
  const apiFailures: string[] = []
  page.on('response', (response) => {
    if (response.url().includes('/api/wiki/') && response.status() >= 400) {
      apiFailures.push(`${response.status()} ${response.url()}`)
    }
  })

  await page.goto('/wiki-preview/character', { waitUntil: 'networkidle' })
  await expect(page.getByTestId('wiki-shell')).toHaveAttribute('data-wiki-variant', 'kimi-preview')
  await expect(page.getByTestId('wiki-character-selection-preview')).toBeVisible()
  await expectStageMediaInFirstViewport(page.getByTestId('kimi-character-stage'))
  await expectFullWidthPersistentNav(page)

  await expect(page.getByTestId('card-nav-menu')).toHaveCount(0)
  const navToggle = page.locator('.card-nav__toggle')
  await navToggle.click()
  await expect(page.getByTestId('card-nav-menu')).toBeVisible()
  await expect(page.getByTestId('card-nav-group')).toHaveCount(3)
  const menuWidth = await page.getByTestId('card-nav-menu').evaluate((node) => node.getBoundingClientRect().width)
  expect(menuWidth).toBeGreaterThanOrEqual((await page.evaluate(() => window.innerWidth)) - 1)
  await navToggle.click()
  await expect(page.getByTestId('card-nav-menu')).toHaveCount(0)

  const rosterItems = page.getByTestId('kimi-character-roster').locator('button.kimi-wiki-selection__roster-item')
  await expect(rosterItems).toHaveCount(30)
  const firstAvatar = rosterItems.first().locator('img')
  await expect(firstAvatar).toBeVisible()
  await expect(firstAvatar).toHaveAttribute('src', /\/reverse1999\/portrait\/[a-f0-9]{2}\/[a-f0-9]{40}\./)
  await expect.poll(
    () => firstAvatar.evaluate((node: HTMLImageElement) => node.complete ? node.naturalWidth : 0),
    { timeout: 30_000 },
  ).toBeGreaterThan(0)
  await expect(page.getByTestId('kimi-personnel-facts').locator('div')).toHaveCount(8)
  const sampledNames: string[] = []
  for (let index = 0; index < 3; index += 1) {
    const item = rosterItems.nth(index)
    const name = await item.getAttribute('aria-label')
    expect(name).toBeTruthy()
    sampledNames.push(name!)
    await item.click()
    await expect(item).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('kimi-personnel-summary').locator('h2')).toHaveText(name!)
    await expectLoadedImageOrFallback(page.getByTestId('kimi-character-stage'))
  }
  expect(new Set(sampledNames).size).toBe(3)

  await page.getByRole('button', { name: '加载更多档案' }).click()
  await expect(rosterItems).toHaveCount(60)
  const search = page.getByRole('searchbox', { name: '搜索页面' })
  await search.fill('槲寄生')
  await expect(page.getByRole('button', { name: '槲寄生', exact: true })).toBeVisible()
  await search.fill('')
  await expect(rosterItems).toHaveCount(30)

  await rosterItems.first().click()
  await page.getByRole('button', { name: '查看完整档案' }).click()
  await expect(page).toHaveURL(/\/wiki-preview\/(?:char|character)\/3003$/)
  await expect(page.getByTestId(/kimi-(?:desktop|mobile)-character-dossier/)).toBeVisible()
  await expectLoadedImageOrFallback(page.getByTestId('kimi-character-stage'))
  await expectNoHorizontalOverflow(page)
  await expectFullWidthPersistentNav(page)

  const leftRail = page.locator('[data-scroll-owner="profile-skill-rail"]')
  const utility = page.locator('.kimi-desktop-character-dossier__utility')
  await leftRail.evaluate((node) => { node.scrollTop = node.scrollHeight })
  await expect(utility).toBeVisible()
  const stickyMetrics = await utility.evaluate((node) => {
    const rect = node.getBoundingClientRect()
    return { bottom: rect.bottom, viewportHeight: window.innerHeight }
  })
  expect(stickyMetrics.bottom).toBeLessThanOrEqual(stickyMetrics.viewportHeight + 1)

  const udimoBounds = await page.getByTestId('character-udimo-media').evaluate((node) => {
    const image = node.getBoundingClientRect()
    const rightColumn = node.closest('.kimi-desktop-character-dossier__right')?.getBoundingClientRect()
    return {
      imageLeft: image.left,
      imageRight: image.right,
      columnLeft: rightColumn?.left ?? Number.POSITIVE_INFINITY,
      columnRight: rightColumn?.right ?? Number.NEGATIVE_INFINITY,
    }
  })
  expect(udimoBounds.imageLeft).toBeGreaterThanOrEqual(udimoBounds.columnLeft - 1)
  expect(udimoBounds.imageRight).toBeLessThanOrEqual(udimoBounds.columnRight + 1)

  expect(apiFailures).toEqual([])
  expect(violations).toEqual([])
})

test('roster avatars never replace switchable character stage media', async ({ page }) => {
  for (const entityId of ['3007', '3065']) {
    await page.goto(`/wiki-preview/character/${entityId}`, { waitUntil: 'networkidle' })
    await expect(page.getByTestId('kimi-desktop-character-dossier')).toBeVisible()

    const portraits = page.getByTestId('kimi-character-stage').locator('img[data-testid="kimi-character-portrait"]')
    expect(await portraits.count()).toBeGreaterThanOrEqual(2)
    const sources = await portraits.evaluateAll((nodes) => (
      nodes.map((node) => (node as HTMLImageElement).src)
    ))
    expect(sources.every((source) => /\/reverse1999\/(?:image|portrait)\/[a-f0-9]{2}\/[a-f0-9]{40}\./.test(source))).toBe(true)
    expect(new Set(sources).size).toBeGreaterThanOrEqual(2)

    const switches = page.getByRole('group', { name: '角色立绘' }).getByRole('button')
    expect(await switches.count()).toBeGreaterThanOrEqual(2)
    await switches.nth(1).click()
    await expect(switches.nth(1)).toHaveAttribute('aria-pressed', 'true')
    await expect.poll(
      () => portraits.nth(1).evaluate((node: HTMLImageElement) => node.complete ? node.naturalWidth : 0),
      { timeout: 30_000 },
    ).toBeGreaterThan(0)
  }
})

test('approved desktop and mobile viewports remain complete and screenshot-ready', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'the visual matrix runs once with explicit approved viewports')
  await mkdir(evidenceDir, { recursive: true })
  const violations = auditReadOnlyRequests(page)

  for (const viewport of approvedViewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/wiki-preview/character', { waitUntil: 'networkidle' })
    await expect(page.getByTestId('wiki-character-selection-preview')).toBeVisible()
    await expectLoadedImageOrFallback(page.getByTestId('kimi-character-stage'))
    if (viewport.width > 760) {
      await expectStageMediaInFirstViewport(page.getByTestId('kimi-character-stage'))
    }
    await expectNoHorizontalOverflow(page)
    await page.screenshot({
      path: `${evidenceDir}/selection-${viewport.name}-${viewport.width}x${viewport.height}.png`,
      fullPage: true,
      animations: 'disabled',
    })

    await page.getByRole('button', { name: '查看完整档案' }).click()
    const expectedDossier = viewport.width <= 760
      ? page.getByTestId('kimi-mobile-character-dossier')
      : page.getByTestId('kimi-desktop-character-dossier')
    await expect(expectedDossier).toBeVisible()
    await expectLoadedImageOrFallback(page.getByTestId('kimi-character-stage'))
    await expectNoHorizontalOverflow(page)
    await page.screenshot({
      path: `${evidenceDir}/detail-${viewport.name}-${viewport.width}x${viewport.height}.png`,
      fullPage: true,
      animations: 'disabled',
    })
  }

  expect(violations).toEqual([])
})
