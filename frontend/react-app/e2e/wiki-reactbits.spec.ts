import { expect, test } from '@playwright/test'

test('Wiki uses one route-aware Card Nav without the retired rail', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'navigation structure runs once')
  await page.goto('/wiki/character')
  await expect(page.getByTestId('wiki-character-selection')).toBeVisible()
  await expect(page.getByTestId('wiki-page-index')).toBeVisible()
  await expect(page.getByTestId('wiki-category-rail')).toHaveCount(0)
  await expect(page.getByTestId('wiki-category-hot-zone')).toHaveCount(0)
  await expect(page.locator('.card-nav__primary')).toHaveText('首页')
  await page.getByRole('button', { name: '展开导航' }).click()
  await expect(page.getByTestId('card-nav-group')).toHaveCount(3)
  await page.getByRole('button', { name: '收起导航' }).click()

  const image = page.getByTestId('wiki-page-index').locator('img').first()
  await expect(image).toBeVisible()
  await expect.poll(() => image.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(0)
  const previewImage = page.getByTestId('selection-preview').locator('img')
  await expect(previewImage).toBeVisible({ timeout: 30_000 })
  await expect.poll(() => previewImage.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(0)

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})

test('route-aware navigation and themes remain keyboard operable', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.card-nav__primary')).toHaveText('WIKI')
  const theme = page.locator('.theme-toggle')
  await theme.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'manuscript-gold')
  await page.getByRole('button', { name: '展开导航' }).click()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('card-nav-menu')).toHaveCount(0)
})

test('development motion preview and recent Wiki route remain available', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'development and direct-route checks run once')
  await page.goto('/__motion-preview')
  await expect(page.getByRole('heading', { name: 'Motion Preview' })).toBeVisible()
  await expect(page.getByText(/Texture budget/)).toBeVisible()

  await page.goto('/wiki/character')
  await expect(page.getByTestId('selection-preview').locator('img')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: '查看完整档案' }).click()
  await expect(page.getByTestId('character-media-stage').locator('img')).toBeVisible({ timeout: 30_000 })
  await page.locator('.card-nav__toggle').click()
  const recent = page.getByTestId('card-nav-menu').locator('a[href^="/wiki/"]').first()
  await expect(recent).toBeVisible()
  const href = await recent.getAttribute('href')
  await page.goto(href!)
  await expect(page.getByTestId('character-media-stage').locator('img')).toBeVisible({ timeout: 30_000 })
  await expect(page).toHaveURL(new RegExp(`${href!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`))
})

test('real RAG image answer produces a nonblank gallery canvas or complete fallback', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'real RAG Canvas request is exercised once on desktop')
  await page.goto('/')
  await page.evaluate(() => document.querySelector('[data-snap-section="chat"]')?.scrollIntoView())
  const input = page.locator('form input[type="text"]')
  await input.fill('介绍一下槲寄生')
  await input.press('Enter')
  const gallery = page.locator('.circular-gallery').last()
  await expect(gallery).toBeVisible({ timeout: 75_000 })
  await expect.poll(() => gallery.getAttribute('data-gallery-status'), { timeout: 30_000 }).not.toBe('loading')
  const status = await gallery.getAttribute('data-gallery-status')
  if (status === 'ready') {
    const nonzero = await gallery.locator('canvas').evaluate((canvas: HTMLCanvasElement) => {
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
      if (!gl) return 0
      const pixels = new Uint8Array(canvas.width * canvas.height * 4)
      gl.readPixels(0, 0, canvas.width, canvas.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels)
      return pixels.reduce((count, value) => count + Number(value !== 0), 0)
    })
    expect(nonzero).toBeGreaterThan(100)
    const canvas = gallery.locator('canvas')
    const before = await gallery.getAttribute('data-gallery-offset')
    const box = await canvas.boundingBox()
    if (box) {
      await page.mouse.move(box.x + box.width * .7, box.y + box.height * .5)
      await page.mouse.down()
      await page.mouse.move(box.x + box.width * .3, box.y + box.height * .5, { steps: 8 })
      await page.mouse.up()
      await expect.poll(() => gallery.getAttribute('data-gallery-offset')).not.toBe(before)
    }
  } else {
    await expect(gallery.locator('.circular-gallery__fallback img').first()).toBeVisible()
  }
  await gallery.getByRole('button', { name: 'Open current image' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('forced WebGL failure keeps the complete image fallback', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'webgl-fallback', 'forced failure runs in its dedicated project')
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      type: string,
      ...args: unknown[]
    ) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') return null
      return original.call(this, type as '2d', ...args as [])
    } as typeof HTMLCanvasElement.prototype.getContext
  })
  await page.goto('/')
  await page.evaluate(() => document.querySelector('[data-snap-section="chat"]')?.scrollIntoView())
  const input = page.locator('form input[type="text"]')
  await input.fill('介绍一下槲寄生')
  await input.press('Enter')
  const gallery = page.locator('.circular-gallery').last()
  await expect(gallery).toHaveAttribute('data-gallery-status', 'fallback', { timeout: 75_000 })
  await expect(gallery.locator('.circular-gallery__fallback img').first()).toBeVisible()
})
