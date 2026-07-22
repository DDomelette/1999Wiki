import { mkdir } from 'node:fs/promises'
import { expect, test, type Locator, type Page } from '@playwright/test'

const evidenceDir = '../../eval/stitch-character-detail-20260715/screenshots'
const detailRoute = '/wiki/character/3003'

function auditReadOnlyRequests(page: Page) {
  const violations: string[] = []
  page.on('request', (request) => {
    const url = request.url()
    const method = request.method()
    if (url.includes('/api/wiki/') && method !== 'GET') violations.push(`${method} ${url}`)
    if (url.includes(':9002') && method !== 'GET') violations.push(`${method} ${url}`)
    if (/:8001\b/.test(url) || /^file:/i.test(url) || /(?:^|[/\\])[A-Z]:[/\\]/i.test(url)) {
      violations.push(url)
    }
  })
  return violations
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
}

async function expectLoadedImages(images: Locator, expected: number) {
  await expect(images).toHaveCount(expected)
  for (let index = 0; index < expected; index += 1) {
    const image = images.nth(index)
    await expect.poll(
      () => image.evaluate((node: HTMLImageElement) => node.complete ? node.naturalWidth : 0),
      { timeout: 30_000 },
    ).toBeGreaterThan(0)
  }
}

async function box(locator: Locator) {
  const value = await locator.boundingBox()
  expect(value).not.toBeNull()
  return value!
}

async function captureAnchor(page: Page, name: string, locator: Locator) {
  const top = await locator.evaluate((node) => node.getBoundingClientRect().top + window.scrollY)
  await page.evaluate((target) => window.scrollTo(0, Math.max(0, target - 64)), top)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(Math.max(0, top - 65))
  await page.screenshot({
    path: `${evidenceDir}/detail-final-mobile-${name}.png`,
    animations: 'disabled',
  })
}

test('PC 1280x951 detail matches the approved single-viewport dossier contract', async ({ page }) => {
  await mkdir(evidenceDir, { recursive: true })
  await page.setViewportSize({ width: 1280, height: 951 })
  const violations = auditReadOnlyRequests(page)
  await page.goto(detailRoute, { waitUntil: 'networkidle' })

  const detail = page.getByTestId('wiki-character-detail')
  const dossier = page.getByTestId('desktop-character-dossier')
  const leftRail = page.getByTestId('profile-skill-rail')
  const stage = page.getByTestId('character-portrait-stage')
  const rightRail = page.getByTestId('inheritance-voice-rail')
  await expect(detail).toBeVisible()
  await expect(dossier).toBeVisible()
  await expect(page.getByTestId('mobile-character-dossier')).toHaveCount(0)

  const navBox = await box(page.locator('.card-nav__bar'))
  const dossierBox = await box(dossier)
  const leftBox = await box(leftRail)
  const stageBox = await box(stage)
  const rightBox = await box(rightRail)
  expect(navBox.height).toBeCloseTo(64, 0)
  expect(dossierBox.y).toBeCloseTo(64, 0)
  expect(dossierBox.height).toBeCloseTo(887, 0)
  expect(leftBox.x).toBeGreaterThanOrEqual(35)
  expect(leftBox.x).toBeLessThanOrEqual(45)
  expect(leftBox.x + leftBox.width).toBeLessThanOrEqual(stageBox.x + 1)
  expect(stageBox.x + stageBox.width).toBeLessThanOrEqual(rightBox.x + 1)
  expect(stageBox.width).toBeGreaterThan(leftBox.width)
  expect(stageBox.width).toBeGreaterThan(rightBox.width)
  expect(stageBox.height).toBeGreaterThanOrEqual(800)

  const profileBox = await box(page.locator('.desktop-character-dossier .character-profile-data'))
  const skillsBox = await box(page.locator('.desktop-character-dossier .character-skill-cards'))
  const wardrobeBox = await box(page.locator('.desktop-character-dossier .character-portrait-stage__wardrobe'))
  const udimoBox = await box(page.locator('.desktop-character-dossier .character-portrait-stage__udimo'))
  const portraitBox = await box(page.locator('.desktop-character-dossier .character-portrait-stage__images img.is-active'))
  const inheritanceBox = await box(page.locator('.desktop-character-dossier .character-progression--inheritance'))
  const portrayBox = await box(page.locator('.desktop-character-dossier .character-progression--portray'))
  const voiceBox = await box(page.locator('.desktop-character-dossier .character-voice-records'))
  expect(profileBox.height).toBeGreaterThanOrEqual(250)
  expect(skillsBox.y).toBeGreaterThanOrEqual(525)
  expect(skillsBox.y).toBeLessThanOrEqual(540)
  expect(wardrobeBox.x).toBeGreaterThanOrEqual(510)
  expect(wardrobeBox.x).toBeLessThanOrEqual(525)
  expect(wardrobeBox.y).toBeGreaterThanOrEqual(810)
  expect(wardrobeBox.y).toBeLessThanOrEqual(830)
  expect(udimoBox.y).toBeGreaterThanOrEqual(760)
  expect(udimoBox.y).toBeLessThanOrEqual(780)
  expect(portraitBox.x).toBeGreaterThanOrEqual(392)
  expect(portraitBox.x).toBeLessThanOrEqual(398)
  expect(portraitBox.y).toBeGreaterThanOrEqual(68)
  expect(portraitBox.y).toBeLessThanOrEqual(74)
  expect(portraitBox.height).toBeGreaterThanOrEqual(875)
  expect(portraitBox.height).toBeLessThanOrEqual(885)
  expect(inheritanceBox.height).toBeGreaterThanOrEqual(215)
  expect(inheritanceBox.height).toBeLessThanOrEqual(225)
  expect(portrayBox.height).toBeGreaterThanOrEqual(185)
  expect(portrayBox.height).toBeLessThanOrEqual(195)
  expect(voiceBox.y).toBeGreaterThanOrEqual(540)
  expect(voiceBox.y).toBeLessThanOrEqual(555)

  const visibleProfileRows = page.locator('.desktop-character-dossier .character-profile-data [data-profile-key]:visible')
  await expect(visibleProfileRows).toHaveCount(4)
  await expect(page.locator('.desktop-character-dossier .character-profile-data blockquote')).toBeVisible()
  await expectLoadedImages(page.getByTestId('character-portrait-image'), 2)
  await expectLoadedImages(page.getByTestId('character-skill-card').locator('img'), 3)
  await expectLoadedImages(page.getByTestId('character-collection-item').locator('img'), 6)

  const leftScroll = await leftRail.evaluate((node) => ({
    client: node.clientHeight,
    scroll: node.scrollHeight,
    overflowY: getComputedStyle(node).overflowY,
  }))
  expect(leftScroll.overflowY).toBe('auto')
  expect(leftScroll.scroll).toBeGreaterThan(leftScroll.client)
  const voiceScroll = page.getByTestId('character-voice-scroll')
  const voiceOwner = await voiceScroll.evaluate((node) => ({
    client: node.clientHeight,
    scroll: node.scrollHeight,
    overflowY: getComputedStyle(node).overflowY,
  }))
  expect(voiceOwner.overflowY).toBe('auto')
  expect(voiceOwner.scroll).toBeGreaterThan(voiceOwner.client)
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(952)
  await expectNoHorizontalOverflow(page)

  await page.getByRole('button', { name: '切换到洞悉' }).click()
  await expect(page.getByRole('button', { name: '切换到洞悉' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '切换到初始' }).click()
  await expect(page.getByRole('button', { name: '切换到初始' })).toHaveAttribute('aria-pressed', 'true')
  await page.screenshot({ path: `${evidenceDir}/detail-final-1280x951.png`, animations: 'disabled' })
  expect(violations).toEqual([])
})

test('mobile 375x850 detail covers all nine approved anchors without gaps', async ({ page }) => {
  await mkdir(evidenceDir, { recursive: true })
  await page.setViewportSize({ width: 375, height: 850 })
  const violations = auditReadOnlyRequests(page)
  await page.goto(detailRoute, { waitUntil: 'networkidle' })

  const mobile = page.getByTestId('mobile-character-dossier')
  await expect(mobile).toBeVisible()
  await expect(page.getByTestId('desktop-character-dossier')).toHaveCount(0)
  await expect(page.locator('.character-summary-card--damageType')).toContainText('DAMAGE_TYPE')
  await expect(page.locator('.character-summary-card--damageType')).toContainText('Mental')
  await expect(page.locator('.character-summary-card--inspiration')).toContainText('INSPIRATION')
  await expect(page.locator('.character-summary-card--inspiration')).toContainText('Plant')
  await expect(page.getByTestId('character-udimo-archive')).toContainText('20th Century Early')
  await expect(page.getByTestId('character-udimo-archive')).toContainText('Oct 23 (Autumn)')

  const modules = page.locator('[data-mobile-module]')
  await expect(modules).toHaveCount(11)
  expect(await modules.evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-mobile-module')))).toEqual([
    'hero',
    'summary',
    'profile',
    'inheritance',
    'portray',
    'skills',
    'ultimate',
    'voices',
    'culture',
    'collection',
    'technical',
  ])
  const moduleBoxes = await modules.evaluateAll((nodes) => nodes.map((node) => {
    const value = node.getBoundingClientRect()
    return { top: value.top + window.scrollY, bottom: value.bottom + window.scrollY }
  }))
  for (let index = 1; index < moduleBoxes.length; index += 1) {
    expect(Math.abs(moduleBoxes[index].top - moduleBoxes[index - 1].bottom)).toBeLessThanOrEqual(1)
  }

  const navBox = await box(page.locator('.card-nav__bar'))
  const tabs = page.getByRole('navigation', { name: '移动档案导航' })
  const tabsBox = await box(tabs)
  expect(navBox.height).toBeCloseTo(64, 0)
  expect(tabsBox.height).toBeCloseTo(64, 0)
  expect(tabsBox.y + tabsBox.height).toBeCloseTo(850, 0)
  const heroBox = await box(page.locator('[data-mobile-module="hero"]'))
  const mobileStageBox = await box(page.locator('[data-mobile-module="hero"] [data-testid="character-portrait-stage"]'))
  const summaryBox = await box(page.locator('[data-mobile-module="summary"]'))
  expect(heroBox.height).toBeCloseTo(658, 0)
  expect(mobileStageBox.y).toBeCloseTo(92, 0)
  expect(mobileStageBox.height).toBeCloseTo(577, 0)
  expect(summaryBox.y).toBeCloseTo(722, 0)
  expect((await box(page.locator('.character-summary__cards'))).y).toBeCloseTo(746, 0)

  await expectLoadedImages(page.getByTestId('character-portrait-image'), 2)
  await expectLoadedImages(page.getByTestId('character-skill-card').locator('img'), 3)
  await expectLoadedImages(page.getByTestId('character-collection-item').locator('img'), 6)
  await expectLoadedImages(page.getByTestId('character-udimo-media'), 1)
  await expect(page.locator('.character-detail__nested-scroll')).toHaveCount(1)
  await expect(page.locator('.character-detail__nested-scroll')).toHaveAttribute('data-testid', 'character-voice-scroll')
  await expectNoHorizontalOverflow(page)

  await captureAnchor(page, 'hero', page.locator('[data-mobile-module="hero"]'))
  await captureAnchor(page, 'summary', page.locator('[data-mobile-module="summary"]'))
  await captureAnchor(page, 'inheritance-portray', page.locator('[data-mobile-module="inheritance"]'))
  await captureAnchor(page, 'skills', page.locator('[data-mobile-module="skills"]'))
  await captureAnchor(page, 'ultimate', page.locator('[data-mobile-module="ultimate"]'))
  await captureAnchor(page, 'voice-culture', page.locator('[data-mobile-module="voices"]'))
  await captureAnchor(page, 'culture-continuation', page.locator('.character-culture-entry').nth(1))
  await captureAnchor(page, 'collection-top', page.locator('[data-mobile-module="collection"]'))
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await page.screenshot({ path: `${evidenceDir}/detail-final-mobile-collection-footer.png`, animations: 'disabled' })

  const voiceScroll = page.getByTestId('character-voice-scroll')
  await voiceScroll.scrollIntoViewIfNeeded()
  await voiceScroll.evaluate((node) => { node.scrollTop = node.scrollHeight })
  const beforeWheel = await page.evaluate(() => window.scrollY)
  await voiceScroll.hover()
  await page.mouse.wheel(0, 420)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(beforeWheel)
  expect(violations).toEqual([])
})
