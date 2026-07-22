import { mkdir } from 'node:fs/promises'
import { expect, test, type Locator, type Page } from '@playwright/test'

const evidenceDir = '../../eval/stitch-wiki-p0/screenshots'

function auditReadOnlyRequests(page: Page) {
  const violations: string[] = []
  page.on('request', (request) => {
    const url = request.url()
    const method = request.method()
    if (url.includes('/api/wiki/') && method !== 'GET') violations.push(`${method} ${url}`)
    if (/:8001\b/.test(url) || /^(?:file:)|[A-Z]:\\/i.test(url)) violations.push(url)
    if (url.includes(':9002') && ['PUT', 'POST', 'DELETE', 'PATCH'].includes(method)) {
      violations.push(`${method} ${url}`)
    }
  })
  return violations
}

async function rect(locator: Locator) {
  const box = await locator.boundingBox()
  expect(box).not.toBeNull()
  return box!
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
}

async function expectLoadedImage(image: Locator) {
  await expect(image).toBeVisible({ timeout: 30_000 })
  await expect.poll(() => image.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(0)
}

test('archival selection and detail stay responsive, traceable and read-only', async ({ page }, testInfo) => {
  await mkdir(evidenceDir, { recursive: true })
  const violations = auditReadOnlyRequests(page)
  const viewport = page.viewportSize()!

  await page.goto('/wiki/character')
  const selection = page.getByTestId('wiki-character-selection')
  const index = page.getByTestId('selection-index')
  const preview = page.getByTestId('selection-preview')
  const summary = page.getByTestId('selection-summary')
  await expect(selection).toBeVisible()
  await expect(page.getByTestId('wiki-character-detail')).toHaveCount(0)
  await expect(page.getByTestId('wiki-category-rail')).toHaveCount(0)
  await expect(page.getByTestId('wiki-category-hot-zone')).toHaveCount(0)
  await expect(page.locator('.card-nav__primary')).toHaveText('首页')
  await expect(page.getByTestId('wiki-page-index')).toContainText('已载入 30 / 132')
  await expect(page.getByTestId('wiki-page-index').locator('img[src$=".mp3"]')).toHaveCount(0)
  await expectLoadedImage(preview.locator('img'))

  const indexBox = await rect(index)
  const previewBox = await rect(preview)
  const summaryBox = await rect(summary)
  if (viewport.width > 1080) {
    expect(indexBox.x + indexBox.width).toBeLessThanOrEqual(previewBox.x + 1)
    expect(previewBox.x + previewBox.width).toBeLessThanOrEqual(summaryBox.x + 1)
    expect(previewBox.width).toBeGreaterThan(indexBox.width)
    expect(previewBox.width).toBeGreaterThan(summaryBox.width)
  } else if (viewport.width > 720) {
    expect(indexBox.x + indexBox.width).toBeLessThanOrEqual(previewBox.x + 1)
    expect(summaryBox.y).toBeGreaterThanOrEqual(Math.min(indexBox.y + indexBox.height, previewBox.y + previewBox.height) - 1)
  } else {
    expect(previewBox.y).toBeGreaterThanOrEqual(indexBox.y + indexBox.height - 1)
    expect(summaryBox.y).toBeGreaterThanOrEqual(previewBox.y + previewBox.height - 1)
  }
  expect(indexBox.height).toBeLessThanOrEqual(Math.max(viewport.height, 680) + 2)
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: `${evidenceDir}/selection-${testInfo.project.name}.png`, fullPage: true })

  await page.getByRole('button', { name: '查看完整档案' }).click()
  await expect(page).toHaveURL(/\/wiki\/character\/3003$/)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  const detail = page.getByTestId('wiki-character-detail')
  await expect(detail).toBeVisible()
  await expect(page.getByTestId('wiki-character-selection')).toHaveCount(0)
  await expect(page.getByTestId('detail-inheritance')).toContainText('木秀于林')
  await expect(page.getByTestId('detail-portray')).toContainText('LV.5')
  await expect(page.getByRole('button', { name: 'Live2D（未就绪）' })).toBeDisabled()
  await expectLoadedImage(page.getByTestId('character-media-stage').locator('img'))

  const profileBox = await rect(page.getByTestId('detail-profile'))
  const mediaBox = await rect(page.getByTestId('detail-media'))
  const inheritanceBox = await rect(page.getByTestId('detail-inheritance'))
  if (viewport.width > 1120) {
    expect(profileBox.x + profileBox.width).toBeLessThanOrEqual(mediaBox.x + 1)
    expect(mediaBox.x + mediaBox.width).toBeLessThanOrEqual(inheritanceBox.x + 1)
    expect(mediaBox.width).toBeGreaterThan(profileBox.width)
  } else if (viewport.width > 720) {
    expect(profileBox.x + profileBox.width).toBeLessThanOrEqual(mediaBox.x + 1)
  } else {
    expect(mediaBox.y).toBeGreaterThanOrEqual(profileBox.y + profileBox.height - 1)
  }

  const archive = page.getByTestId('detail-archive')
  await expect(archive).toHaveAttribute('tabindex', '0')
  await expect(archive).toContainText('PAGE INFO')
  await expect(page.getByRole('link', { name: '/wiki/character/3003' })).toBeVisible()
  if (viewport.width <= 720) {
    const voiceToggle = page.getByRole('button', { name: '展开语音档案' })
    const archiveToggle = page.getByRole('button', { name: '展开档案' })
    await expect(voiceToggle).toHaveAttribute('aria-expanded', 'false')
    await expect(archiveToggle).toHaveAttribute('aria-expanded', 'false')
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThan(8_000)
    await voiceToggle.click()
    await expect(page.getByTestId('detail-voices')).toContainText('初遇')
    await page.getByRole('button', { name: '收起语音档案' }).click()
  }
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: `${evidenceDir}/detail-${testInfo.project.name}.png`, fullPage: true })

  await page.getByRole('button', { name: '返回角色索引' }).click()
  await expect(page).toHaveURL(/\/wiki\/character$/)
  await expect(page.getByRole('button', { name: '槲寄生' })).toHaveAttribute('aria-pressed', 'true')
  expect(violations).toEqual([])
})

test('Wiki search, pagination and Card Nav categories stay available', async ({ page }, testInfo) => {
  test.skip(!['stitch-desktop', 'mobile'].includes(testInfo.project.name), 'interaction matrix runs on desktop and mobile')
  const violations = auditReadOnlyRequests(page)
  await page.goto('/wiki/character')
  await expect(page.getByRole('button', { name: '加载更多档案' })).toBeVisible()
  await page.getByRole('button', { name: '加载更多档案' }).click()
  await expect(page.getByTestId('wiki-page-index')).toContainText('已载入 60 / 132')

  const search = page.getByRole('searchbox', { name: '搜索页面' })
  await search.fill('露西')
  await expect(page.getByRole('button', { name: '露西' })).toBeVisible()
  await page.getByRole('button', { name: '展开导航' }).click()
  await expect(page.getByTestId('card-nav-menu')).toBeVisible()
  await expect(page.getByTestId('card-nav-group').first()).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('card-nav-menu')).toHaveCount(0)
  expect(violations).toEqual([])
})
